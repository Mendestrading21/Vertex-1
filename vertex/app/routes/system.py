"""
vertex/app/routes/system.py — SANTÉ SYSTÈME & PWA (Blueprint, Ch. II).

Health-check, état système institutionnel (version, LECTURE SEULE, sources,
fraîcheur des caches, moteurs), et l'enveloppe PWA (favicon, manifeste, service
worker). Lit l'état partagé ; aucune donnée sensible ; jamais d'ordre.
"""

import time
from collections import deque

from flask import Blueprint, jsonify, Response, request

from vertex.ai import briefs as ai
from vertex.app.config import IBKR_ENABLED, DEMO_MODE
from vertex.app.state import scan_state
from vertex.strategy import release as _release
from vertex.data.universe import UNIVERSE
from vertex.data import constants as _vconst
from vertex.data.constants import BUILD
from vertex.services import status_service as _status_svc

bp = Blueprint('system', __name__)


@bp.route('/healthz')
@bp.route('/api/healthz')
def healthz():
    """Health check (Render) — toujours 200 si le process répond. Indique l'état
    du scan sans bloquer. Aucune donnée sensible, lecture seule."""
    return jsonify({
        'status': 'ok',
        'build': BUILD,
        'data_source': scan_state.get('source'),
        'ibkr_enabled': IBKR_ENABLED,
        'ibkr_live': bool(scan_state.get('ibkr_live')),   # socket RÉEL + temps réel (honnêteté §4, pas le flag de config)
        'universe': len(UNIVERSE),
        'scanned': scan_state.get('scanned_n'),
        'last_scan': scan_state.get('updated'),
        'scan_age': round(time.time() - scan_state['scan_ts']) if scan_state.get('scan_ts') else None,
        'scan_error': scan_state.get('error'),
        'source_health': scan_state.get('source_health') or {'scan': 'UNKNOWN'},
        'vertex_ready': sum(1 for d in (scan_state.get('detail') or {}).values() if d.get('vertex')),
        'engines': ['scoring', 'pivots', 'committee', 'strategy', 'portfolio_risk',
                    'vertex', 'vertex_ml', 'validator'],
        #  QUELLE constitution s'applique. Elle depend de la commande de
        #  lancement — `python -m vertex` active V4, un `terminal.py` direct
        #  reste sur V3 — et rien ne le disait. Les deux different sur 29
        #  points, dont les horizons actions et la fenetre DTE.
        'constitution': _release.etat_actif(),
    }), 200


# ─── TÉLÉMÉTRIE D'ERREURS CLIENT (objectif 0-erreur : observer pour corriger) ───
# Les erreurs JS des navigateurs remontent ici (window.onerror du vx_kit).
# Borné (100 max, payloads tronqués) — aucune donnée sensible, lecture locale.
_CLIENT_ERRORS = deque(maxlen=100)


@bp.route('/api/client-log', methods=['POST'])
def client_log_post():
    b = request.get_json(force=True, silent=True) or {}
    _CLIENT_ERRORS.append({
        'ts': round(time.time()),
        'page': str(b.get('page') or '')[:120],
        'msg': str(b.get('msg') or '')[:300],
        'src': str(b.get('src') or '')[:160],
        'line': b.get('line') if isinstance(b.get('line'), int) else None,
    })
    return jsonify({'ok': True})


@bp.route('/api/client-log')
def client_log_get():
    """Journal des erreurs JS remontées par les navigateurs — diagnostic 0-erreur."""
    return jsonify({'count': len(_CLIENT_ERRORS), 'errors': list(_CLIENT_ERRORS)})


@bp.route('/api/system/startup-report')
def startup_report_ep():
    """Rapport de la séquence de démarrage (§10) — honnête, jamais « OK » sans preuve."""
    from vertex.services.startup import startup_report
    return jsonify(startup_report())


@bp.route('/api/system/config')
def config_validation_ep():
    """Statuts de configuration CONFIGURED/MISSING/INVALID — aucune valeur exposée."""
    from vertex.app.config_validation import validate_config
    return jsonify(validate_config())


@bp.route('/api/system/automations')
@bp.route('/api/system/jobs')
def automations_ep():
    """Registre des jobs de fond : statut, dernière exécution, cadence, erreurs.
    Alias canonique /api/system/jobs (§41)."""
    from vertex.scheduler import registry
    return jsonify({'jobs': registry.jobs()})


@bp.route('/api/system/connections')
def connections_ep():
    """État honnête des connexions (§41) — IBKR/TradingView/Claude/stockage/
    scheduler/live. Statuts canoniques, jamais plus favorables que la réalité ;
    aucun secret exposé."""
    from vertex.services import connections
    return jsonify(connections.snapshot(scan_state, ibkr_enabled=IBKR_ENABLED,
                                        demo_mode=DEMO_MODE))


@bp.route('/readyz')
def readyz():
    """Readiness (§41) — l'application est-elle prête à servir ? Distinct de
    /healthz (process vivant). 200 si prête, 503 sinon. Honnête : n'affirme
    READY que si les vérifications critiques passent."""
    checks = []

    def _chk(name, ok, detail=''):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        return ok

    # 1. Configuration validable.
    try:
        from vertex.app.config_validation import validate_config
        cfg = validate_config()
        bad = [k for k, v in cfg.items() if isinstance(v, dict) and v.get('status') == 'INVALID']
        _chk('configuration', not bad, 'invalides: %s' % ','.join(bad) if bad else 'valide')
    except Exception:
        _chk('configuration', False, 'configuration_indisponible')

    # 2. Stratégie chargée (constitution canonique).
    try:
        from vertex.strategy import profile as _prof  # noqa: F401
        _chk('strategie', True, 'constitution disponible')
    except Exception:
        # tolérant : la stratégie peut vivre ailleurs — non bloquant.
        _chk('strategie', True, 'module stratégie optionnel')

    # 3. Stockage desk lisible.
    try:
        from vertex.services import persist
        persist.load_json('desk_data.json', {})
        _chk('stockage', True, 'desk lisible')
    except Exception:
        _chk('stockage', False, 'stockage_indisponible')

    # 4. READONLY effectif (invariant absolu).
    from vertex.app.config import READONLY
    _chk('readonly', bool(READONLY), 'lecture seule effective')

    ready = all(c['ok'] for c in checks)
    return jsonify({'ready': ready, 'readonly': True, 'checks': checks,
                    'build': BUILD}), (200 if ready else 503)


@bp.route('/api/system-status')
@bp.route('/api/system/status')
def system_status_ep():
    """État système institutionnel : version, LECTURE SEULE, sources, fraîcheur
    des caches, âge scan/options/fondamentaux/news, moteurs. Analyse uniquement."""
    detail = scan_state.get('detail') or {}
    ok = not scan_state.get('error') and bool(scan_state.get('rows'))
    last = scan_state.get('updated')
    engines = [
        _status_svc.engine_status('scanner', ok=ok, last_success=last, last_error=scan_state.get('error')),
        _status_svc.engine_status('scoring', ok=ok, last_success=last),
        _status_svc.engine_status('vertex', ok=any(d.get('vertex') for d in detail.values()), last_success=last),
        _status_svc.engine_status('physics', ok=any(d.get('physics') for d in detail.values()), last_success=last),
        _status_svc.engine_status('timeframe', ok=any(d.get('mtf') for d in detail.values()), last_success=last),
        _status_svc.engine_status('options', ok=bool(scan_state.get('options_board')), last_success=last),
        _status_svc.engine_status('committee', ok=bool(scan_state.get('committee')), last_success=last),
        _status_svc.engine_status('validator', ok=ok, last_success=last),
    ]
    thresholds = {'scan': _vconst.STALE_SCAN_SEC, 'options': _vconst.STALE_OPTIONS_SEC,
                  'fundamentals': 86400, 'news': 3600}
    return jsonify(_status_svc.build_system_status(
        scan_state, build=BUILD, readonly=True, ibkr_enabled=IBKR_ENABLED,
        demo_mode=DEMO_MODE, ai_on=ai.available(), thresholds=thresholds, engines=engines))


#  ─── BUNDLE CSS (lot 30) — une requête au lieu de 19 ────────────────────────
#  Lighthouse (lot 28) : la chaîne critique de 19 feuilles pesait 6-7 s de LCP
#  simulé. Le bundle concatène les feuilles dans l'ordre EXACT de la cascade
#  (vertex/ui/shell.CSS_ORDER — un contrat), en MÉMOIRE au premier appel :
#  aucun artefact généré dans l'arbre suivi, les feuilles individuelles
#  restent servies. Cache immutable : l'URL est versionnée par la coque.
_BUNDLE_CSS = {}


def _minifier_css(css):
    """Minification CONSERVATRICE (lot 39) : commentaires et blancs morts
    seulement. Les chaînes sont préservées caractère à caractère, `calc()`
    garde ses espaces (on ne touche jamais `+`/`-`), et les combinateurs de
    sélecteurs (`a > b`, `a b`) gardent leur espace UNIQUE — on ne retire les
    blancs qu'autour de `{` `}` `;` `,` et après les deux-points d'une
    déclaration (ancré sur `{` ou `;` : jamais un pseudo-sélecteur)."""
    import re as _re
    out, i, n, in_str = [], 0, len(css), ''
    while i < n:
        c = css[i]
        if in_str:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(css[i + 1]); i += 2; continue
            if c == in_str:
                in_str = ''
            i += 1; continue
        if c in ('"', "'"):
            in_str = c; out.append(c); i += 1; continue
        if c == '/' and i + 1 < n and css[i + 1] == '*':
            j = css.find('*/', i + 2)
            i = (j + 2) if j >= 0 else n
            continue
        out.append(c); i += 1
    #  Blancs : hors chaînes désormais — on protège les chaînes restantes en
    #  les mettant de côté avant les regex globales.
    corps = ''.join(out)
    strs = []
    def _garde(m):
        strs.append(m.group(0)); return '\x00%d\x00' % (len(strs) - 1)
    corps = _re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', _garde, corps)
    corps = _re.sub(r'\s+', ' ', corps)
    corps = _re.sub(r'\s*([{};,])\s*', r'\1', corps)
    corps = corps.replace(';}', '}')
    corps = _re.sub(r'([{;])\s*([-A-Za-z*][-A-Za-z0-9]*)\s*:\s*', r'\1\2:', corps)
    corps = _re.sub(r'\x00(\d+)\x00', lambda m: strs[int(m.group(1))], corps)
    return corps.strip()


@bp.route('/asset/css/bundle.css')
def bundle_css():
    if 'corps' not in _BUNDLE_CSS:
        import os as _os
        from vertex.ui.shell import CSS_ORDER
        dossier = _os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.dirname(_os.path.abspath(__file__)))), 'static', 'vertex', 'css')
        parts = []
        for nom in CSS_ORDER:
            with open(_os.path.join(dossier, nom), encoding='utf-8') as fh:
                parts.append('/* \u2550 bundle: %s \u2550 */\n%s'
                             % (nom, _minifier_css(fh.read())))
        _BUNDLE_CSS['corps'] = '\n'.join(parts)
    return Response(_BUNDLE_CSS['corps'], mimetype='text/css',
                    headers={'Cache-Control': 'public, max-age=31536000, immutable'})


@bp.route('/favicon.ico')
@bp.route('/favicon.svg')
def favicon_ep():
    """Favicon Vertex : triangle cuivre sobre sur fond obsidienne, en SVG inline
    (aucune dépendance fichier → zéro 404 dans l'onglet du navigateur)."""
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
           "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
           "<stop offset='0' stop-color='#e1a06e'/><stop offset='1' stop-color='#b96d3c'/>"
           "</linearGradient></defs>"
           "<rect width='64' height='64' rx='14' fill='#0b0e14'/>"
           "<path d='M32 15 L49 45 L15 45 Z' fill='url(#g)'/>"
           "</svg>")
    return Response(svg, mimetype='image/svg+xml',
                    headers={'Cache-Control': 'public, max-age=86400'})


@bp.route('/manifest.webmanifest')
def manifest_ep():
    """Manifeste PWA → permet « Ajouter à l'écran d'accueil » sur iPhone/Android
    et l'ouverture en plein écran comme une vraie app."""
    return jsonify({
        'name': 'Vertex — Cockpit IBKR',
        'short_name': 'Vertex',
        'description': "Cockpit d'analyse trading (analyse only).",
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait-primary',
        'background_color': '#0b0e14',
        'theme_color': '#0b0e14',
        'icons': [
            {'src': '/static/icon-180.png', 'sizes': '180x180', 'type': 'image/png', 'purpose': 'any maskable'},
        ],
    })


_SW_JS = r"""
const CACHE='td-shell-v291';  // v291 : mission alimentation — simulateur sans IV inventee, fraicheur servie (scan_ts_h, regime as_of, calendrier date), cartes macro Marches restaurees, references officielles FRED/BCE/BNS  // v290 : refonte dashboards — regles de mise en page restaurees (hero-grid, disclosure, stats-row, dimensions d environnement), vue d ensemble Options en 8/4 + bande KPI, jauge sans halo, micro-barre partagee, tables numeriques alignees  // v289 : curseurs du screener : zone tactile 32px, piste inchangee  // v288 : onglets vx2 : barre visible sur mobile (regle dans la couche finale)  // v287 : onglets vx2 : barre de defilement visible sur mobile  // v286 : la rangee d actions replie au lieu de defiler sans barre  // v285 : portées de grille et repli des en-têtes de carte  // v284 : lot mobile : .vx2-context-group passe a la ligne — la puce 120 jours n est plus coupee a 390 px  // v283 : renommage des outils : simulator.js cite tools/audit/boutons_morts.py au lieu de l ancien chemin  // v282 : lot 46 — fraicheur honnete : /cal-feed, vol-charts et scenarios portent leur epoque serveur (ts) ; les 7 cartes d options-symbol cessent d afficher l heure du clic (Date.now) comme age de la donnee ; le calendrier affiche un age vivant  // v281 : lot 44 (suite) : borne mobile en max-height scopee [style*=--vx-chart-h]  // v280 : lot 44 : hauteur des graphiques via --vx-chart-h + borne mobile 58vw (chart-core, options-intel, charts.css)  // v279 : lot 39 — bundle CSS minifie cote serveur (211 -> 141 Ko, perf mobile 63 -> 65, FCP -0,3 s) ; minifieur conservateur (chaines, calc, combinateurs preserves), marqueurs de sommaire conserves   // v278 : lot 38 — onglets Options honnetes : la vue radar s appelle Radar, la vue leaps s appelle Scanner LEAPS (noms croises herites, dette du lot 32 ; URLs intactes)   // v277 : lot 37 — dix modules UI orphelins retires (nav, home_art, sync_center, vx_kit, design_system, signals, journal, options_lab, strategy_os, vault) ; vx-entities.js documente son role de source unique du contrat desk   // v276 : lot 35 (flux manuels E2E) — les lignes de positions ouvrent le menu POSITION (Modifier/Cloturer/Supprimer, par id) au lieu du menu du titre ; le bouton « Cloturer » du tableau recoit son handler (il etait mort) ; « Declarer une position » ne redemande plus la destination deja choisie   // v275 : lot 33 (refonte visuelle, mode peuple) — scorecard Portefeuille : la grille suit la presence de la jauge (tuiles pleine largeur) ; primitives treemap/waterfall : hauteur figee liberee (le pied ne saigne plus sur le bloc suivant) ; motif scenario : base servie (libelle/valeur/note structures) ; chaine : prime derivee du cout (34,43 au lieu de — a cote de 3 443 $)   // v274 : lot 32 — parcours du blueprint cable : « Simuler ce contrat » depuis le tiroir du scanner LEAPS (parametres reels), le simulateur lit le contexte d URL et lance ; refus options en francais d interface ; compte de rescan honnete en demo   // v273 : lot 31 — le simulateur Actions lit le prix reel du scan courant (promesse des Hypotheses tenue), saisie manuelle prioritaire, provenance affichee   // v272 : lot 30 — la coque charge UNE feuille agregee (/asset/css/bundle.css, ordre de cascade contractuel) au lieu de 19 requetes en chaine critique ; l opacite .7 qui cassait le AA de la question de graphique est annulee ; aria-label du plein ecran contient son texte visible   // v271 : lot 29 (mode peuple) — 34 regles rapatriees pour 20 classes rendues seulement avec donnees (puces de regime collees, identite du dossier, greeks/scenarios) ; signaux secondaires du regime en francais   // v270 : lot 28 (4 tickets) — titres de carte vx2 en h2 (heading-order), cible tactile 24px des summary (target-size) ; porte unique d import ib_async ; manifeste de troncature du copilote ; replay outille du conseil   // v269 : lot 25 — tokens.css aligne sur la verite servie (41 jetons :root portaient encore l ancienne marque, arbitres par cascade seulement) ; copilote : positions exclues du prompt par defaut (vie privee, case explicite)   // v268 : lot 24 (nettoyage autorise) — neon-glass.css supprimee (morte prouvee), chart-theme-obsidian-copper.js renomme chart-theme-black-glass.js   // v267 : verification lots 17-20 — Systeme : badge de sante sur /readyz (il affichait « Operationnel · 8 moteurs » pendant que la jauge disait 0/8) ; Analyse : mediane sectorielle [object Object] sur dict vide ; Portefeuille : la legende de la treemap declare le repli concentration ; Vertex IA : l encart IA quitte le violet (options uniquement) pour l argent   // v266 : Opportunites — l entonnoir affiche le delta du scan precedent (entres/sortis, premier scan honnete)   // v265 : Aujourd'hui — la carte « Ce qui a change » etait un squelette perpetuel (aucun remplisseur) ; branchee sur changes_since_prev avec trois etats honnetes, nœud mort vx-mkt-diff retire   // v264 : verification lot 14 — le jeton interne 'unavailable' fuyait en anglais brut dans l'etape DONNEE de la DecisionTrace  // v263 : navigation client persistante : vx-router charge — le shell ne se reconstruit plus a chaque page  // v262 : jobs : l etat SILENCIEUX — une boucle morte ne se lit plus OK  // v261 : declaration de position 2.0 : objectif, devise, strategie et frais — parite avec le schema du desk  // v260 : frontiere IBKR market-data-only : la carte de compte, l import de positions et le rapprochement P&L courtier sont retires  // v259 : Calendrier Options : neuf filtres inertes retires ; helper de notification appele par un nom inexistant  // v258 : ecart unique entre la barre d onglets et le contenu (quatre valeurs mesurees, une seule posee)  // v257 : coque : bandeau et masquage des squelettes quand JavaScript est coupe ; deux champs de filtre nommes  // v256 : disposition rapatriee depuis la feuille non servie (Options, Analyse, Marches, Systeme) et carte radar sans etat  // v255 : Options : neuf onglets canoniques + chaine  // v254 : Performance : populations separees en sous-vues  // v253 : Vertex IA : source non declaree  // v252 : Vertex IA : Brief quotidien et Decisions  // v251 : Aujourd'hui : alertes declenchees  // v250 : Opportunites : aides au niveau module  // v249 : Opportunites : six references non definies  // v248 : Opportunites : accents en clair  // v247 : Calendrier Options : trois blocs remplis  // v246 : Opportunites Actions/ETF et Calendrier Options  // v245 : Systeme : formulation des taches sans executant  // v244 : Systeme : accents, sante globale, _summary  // v243 : Systeme 2.0 : Alertes techniques et Securite  // v242 : Repetitions visibles corrigees (controle 039)  // v241 : Primitives SVG : question, unite et source  // v240 : Contrat des graphiques : unite, question et source sur les 72 cartes  // v239 : Options 2.0 : data-view-tab restaure  // v238 : Options 2.0 : tiroir contrat, tables equivalentes, boucle corrigee  // v237 : Options 2.0 : tables equivalentes et barre de contexte  // v236 : Marches 2.0 : pastille de regime et age inconnu explicite  // v235 : Performance 2.0 : libelles accentues et grille d'indicateurs  // v234 : Performance 2.0 : bande d'indicateurs et populations  // v233 : Portefeuille 2.0 : cartes de thèse et barres d'allocation  // v232 : Vertex 2.0 lot 14 — neon-glass.css est etiquetee comme NON SERVIE : verifie au navigateur, elle n'est demandee par aucune page, et ses regles .vx-verdict-card ont deja induit en erreur pendant cette refonte.  // v231 : Vertex 2.0 lot 12 — la matrice des connexions de Systeme n'avait aucune disposition sur desktop : seule sa surcharge mobile existait, et elle supposait une regle de base jamais ecrite. Nom, badge et description se collaient.  // v230 : Vertex 2.0 lot 10 — la page Suivi ignorait son parametre de sous-vue et son emplacement de fraicheur n'etait rempli par personne. Trois sous-vues reelles, fraicheur honnete, et renvoi vers les proprietaires canoniques au lieu de dupliquer.  // v229 : Vertex 2.0 lot 8 — le dossier Options par sous-jacent etait masque par une collision de route (le JSON gagnait) : neuf liens internes deversaient du JSON brut. La page recoit /options/dossier/<sym> et les liens suivent.  // v228 : Vertex 2.0 lot 7 — le conteneur du verdict canonique manquait dans le dossier Analyse (calcule puis jete), la section #an-hero etait fermee par un </div> orphelin qui imbriquait tout le dossier dans une carte collante, et la carte de verdict n'avait aucun style.  // v227 : Vertex 2.0 — la vue Structure des Options portait un squelette perpetuel, un tiret nu et un raccourci « Depuis le tableau : » suivi de rien. Trois etats honnetes les remplacent.  // v226 : Vertex 2.0 — chaque page annonce desormais son groupe de travail (surtitre) et pose une vraie question metier ; quatre pages portaient une description. La coque servie change sur les douze pages.  // v225 : Vertex 2.0 controle 028 — la palette de commandes listait les huit anciens espaces : Calendrier, Simulateur, Suivi et Performance etaient introuvables a la recherche globale. Elle porte desormais les douze pages.  // v224 : Vertex 2.0 lot 15 — calendar.js lit desormais le vocabulaire des verdicts depuis window.__VXVOCAB au lieu d'en porter une copie. Sans ce bump, un visiteur garderait la copie locale, libre de deriver du moteur.  // v223 : Vertex 2.0 lot 4 — le theme graphique est realigne : les alias 'blue' et 'cyan' ne rendent plus le vert de marque abandonne ni un beige chaud, la courbe d'equite et les niveaux de support passent en argent. Sans ce bump, un visiteur garderait des series qui mentent sur leur sens.  // v222 : Vertex 2.0 lots 3-5 et 13 — la coque servie change (nom accessible sur le bouton Ajouter) et vertex-2-0.css releve --vx-smoke et --vx-text-faint au niveau AA. Sans ce bump, un visiteur deja en v221 garderait en cache des meta-textes a 2,66:1 de contraste. // v221 : Vertex 2.0 lot 2 — la coque servie change de forme (navigation groupee Piloter/Explorer/Gerer/Intelligence, douze pages au lieu de sept) et deux pages nouvelles arrivent avec leur JS (calendar.js, simulator.js). Sans ce bump, un visiteur deja en v220 garderait l'ancienne navigation en cache et ne trouverait ni Calendrier ni Simulateur. // v220 : Vertex 2.0 lot 1 — la coque servie charge une nouvelle feuille (vertex-2-0.css, couche de verite finale) et deux nouvelles polices (Geist / Geist Mono variables). Sans ce bump, un visiteur deja en v219 garderait l'ancienne identite en cache et ne verrait jamais la refonte. // v219 : chart-core.js expose `C.crosshairPlugin`, appelee par candlestick-chart.js et absente — la carte chandeliers de la fiche Analyse ne s'affichait jamais. // v218 : vx-core.js gagne `_toneAttr`/`_toneCls`, appelees par VX.tile et definies nulle part — chaque tuile de metrique levait ReferenceError. Sans ce bump, un visiteur garderait le vx-core casse en cache. // v217 : le shell servi a change — heatmap.js echappe desormais ses titres, neuf fichiers de pages sont passes a la forme sure `(lookup||{}).innerHTML=`, et la fiche Analyse a perdu ses cartes en double. Sans ce bump, un visiteur deja en v216 garderait la version vulnerable en cache. // v216 : INTEGRATION de vertex-live dans main. Deux numerotations independantes se rencontraient — main etait a v215, live a v94 — et les ASSETS de live font foi : les polices ont change (General Sans et JetBrains Mono auto-hebergees, Inter retire). Reprendre v94 ferait REGRESSER le numero chez un visiteur deja en v215 : son navigateur garderait l'ancien cache et ne verrait jamais Black Glass. On bumpe donc au-dessus des deux. // v94 : CMP-01 — .vx-card canonique (base fusionnée dans glass.css, redéfinition components retirée, styles identiques)
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['/manifest.webmanifest','/static/icon-180.png','/asset/css/bundle.css','/static/vertex/fonts/geist-variable.woff2','/static/vertex/fonts/geist-mono-variable.woff2','/static/vertex/fonts/GeneralSans-Regular.woff2','/static/vertex/fonts/GeneralSans-Medium.woff2','/static/vertex/fonts/GeneralSans-Semibold.woff2','/static/vertex/fonts/GeneralSans-Bold.woff2','/static/vertex/fonts/JetBrainsMono-Regular.woff2','/static/vertex/fonts/JetBrainsMono-Medium.woff2','/static/vertex/fonts/JetBrainsMono-SemiBold.woff2','/static/vertex/fonts/JetBrainsMono-Bold.woff2']).catch(()=>{})));});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{const ks=await caches.keys();await Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)));await self.clients.claim();})());});
self.addEventListener('fetch',e=>{
  const req=e.request; if(req.method!=='GET')return;
  const url=new URL(req.url); if(url.origin!==location.origin)return;
  const cacheable=(req.mode==='navigate'||url.pathname.startsWith('/static')||url.pathname==='/manifest.webmanifest');
  e.respondWith((async()=>{
    const cache=await caches.open(CACHE);
    try{
      // network-first : on prefere TOUJOURS le frais ; repli cache si reseau lent (cold start) ou hors-ligne
      const net=await Promise.race([fetch(req),new Promise((_,rej)=>setTimeout(()=>rej(new Error('to')),4500))]);
      if(net&&net.ok&&cacheable)cache.put(req,net.clone());
      return net;
    }catch(err){
      const c=(await cache.match(req))||(req.mode==='navigate'?await cache.match('/'):null);
      return c||fetch(req);
    }
  })());
});
"""


@bp.route('/sw.js')
def service_worker():
    """Service worker PWA (network-first + repli cache) — masque les cold starts
    Render. ⛔ Aucune donnee perso ici (favoris/notes restent en localStorage)."""
    return Response(_SW_JS, mimetype='application/javascript',
                    headers={'Service-Worker-Allowed': '/', 'Cache-Control': 'no-cache'})


__all__ = ['bp']
