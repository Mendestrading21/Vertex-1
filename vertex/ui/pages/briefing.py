"""vertex.ui.pages.briefing — le cockpit (§20-22) + MARCHÉS fusionné.

Question : « Que dois-je comprendre et surveiller aujourd'hui ? »
Le Dashboard EST la page Marchés : l'ancienne page /markets est fusionnée ici
(indices & cross-asset, graphique principal interactif, comparaison d'indices,
courbe des taux, appétit pour le risque, secteurs/rotation, breadth, VIX).

Ordre de lecture : l'essentiel → brief → marchés → actus → mouvements →
secteurs → pouls → opportunités → portefeuille.
Système visuel VERROUILLÉ : 3 hauteurs de graphique (160 compact · 240
standard · 320 héros), 2 ratios de rangée (8/4 et 6/6) + bandeaux span-2/3.
Données réelles uniquement — « — » honnête si absent, jamais un chiffre inventé.
"""
from __future__ import annotations

import contextlib
import time

from vertex.ui.shell import render_shell


def _instant_scan(scan_state: dict) -> str | None:
    """L'instant du scan SOUS UNE FORME QUE LE CLIENT SAIT LIRE, ou `None`.

    Le client n'a qu'un seul analyseur d'horodatage, `VX.freshness._ms`, et il
    ne lit que ce que `new Date(x)` accepte. Mesuré dans Chromium le
    06/09/2026 sur le `vx-core.js` servi :

        _ms('2026-09-06T18:32:24Z')  -> 1788719544000
        _ms('1788719544.6501086')    -> null   (new Date -> « Invalid Date »)
        _ms('20:32:24')              -> null

    Une époque écrite telle quelle dans un attribut HTML devient donc une
    CHAÎNE que le client ne sait pas dater — tout en restant *truthy*, donc en
    autorisant l'affirmation d'un mode servi. C'est exactement le défaut que ce
    lot corrigeait ailleurs, et la conversion existait déjà dans
    `build_editorial` seulement : `render()` posait `data-scan-ts` sans elle et
    rendait « Âge inconnu · comité — daté du scan qui l'a produit Différé »,
    `data-mode="delayed"`, `data-ts` ABSENT (mesuré). Les deux appelants
    partagent désormais la même conversion, pour qu'il n'existe plus un endroit
    où l'on convertit et un endroit où l'on oublie.

    Rend `None` — jamais une chaîne vide, jamais « maintenant » — quand le scan
    ne date rien : l'absence reste l'absence (invariant 4).
    """
    horodatage = (scan_state or {}).get('scan_ts_h')
    if horodatage:
        return str(horodatage)
    epoch = (scan_state or {}).get('scan_ts')
    if epoch is not None:
        with contextlib.suppress(Exception):
            return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(float(epoch)))
    return None


# ── Brief Vertex éditorial (§21) — paquet structuré → ~10 lignes ────────
def build_editorial(scan_state: dict) -> dict:
    """Brief déterministe composé UNIQUEMENT depuis les données moteur.

    Si la couche IA est disponible elle peut reformuler ce même paquet ;
    sinon ce texte déterministe est servi tel quel. Jamais de texte générique
    sans rapport avec les données.
    """
    # market (horloge de séance : et/open/session) FUSIONNÉ avec market_ctx
    # (régime/vix/breadth) — un simple `or` masquait tout le contexte.
    m = {**(scan_state.get('market') or {}), **(scan_state.get('market_ctx') or {})}
    sectors = scan_state.get('sectors') or []
    committee = scan_state.get('committee') or {}
    counts = committee.get('counts') or {}
    source = scan_state.get('source') or 'aucune'
    lines: list[str] = []
    missing: list[str] = []

    _fr = {'TREND': 'TENDANCE', 'NEUTRAL': 'NEUTRE', 'CHOP': 'SANS DIRECTION',
           'DOWN': 'BAISSIER', 'UP': 'HAUSSIER', 'UNKNOWN': 'INDÉTERMINÉ'}
    regime = m.get('spy_regime') or m.get('regime')
    regime = _fr.get(str(regime or '').upper(), regime)
    roro = m.get('roro')
    if regime or roro:
        lines.append(f"Régime : {regime or 'n/d'}"
                     + (f" · {roro}" if roro else '') + '.')
    else:
        missing.append('régime')
    idx = scan_state.get('indices') or []
    by_name = {i.get('name'): i for i in idx if isinstance(i, dict)} \
        if isinstance(idx, list) else {}
    parts = []
    for name in ('S&P 500', 'Nasdaq'):
        entry = by_name.get(name) or {}
        if entry.get('change') is not None:
            parts.append(f"{name} {entry['change']:+.1f} %")
    if parts:
        lines.append('Indices : ' + ' · '.join(parts) + '.')
    vix = m.get('vix')
    if vix is not None:
        band = m.get('vix_band') or ''
        lines.append(f'Volatilité : VIX {vix}' + (f' ({band})' if band else '') + '.')
    else:
        missing.append('volatilité')
    breadth = m.get('breadth')
    if isinstance(breadth, dict):          # market_ctx.breadth = {above50, above200, …}
        breadth = breadth.get('above50', breadth.get('above200'))
    if breadth is not None:
        lines.append(f'Participation : {round(breadth)} % des valeurs leaders au-dessus de leur moyenne mobile — '
                     + ('participation large, mouvement soutenu.' if breadth >= 55 else
                        'participation étroite, sélectivité obligatoire.'))
    if sectors:
        top = sectors[0] if isinstance(sectors[0], dict) else None
        weak = sectors[-1] if len(sectors) > 1 and isinstance(sectors[-1], dict) else None
        if top:
            lines.append(f"Secteur leader : {top.get('sector', 'n/d')} "
                         f"(score {top.get('avg_score', 'n/d')}).")
        if weak and weak is not top:
            lines.append(f"Secteur faible : {weak.get('sector', 'n/d')}.")
    if counts:
        na = counts.get('ACHETER', 0)
        nv = counts.get('ÉVITER', counts.get('EVITER', 0))
        lines.append(f"Comité : {na} dossier{'s' if na != 1 else ''} d'achat, "
                     f"{counts.get('ATTENDRE', 0)} en surveillance, "
                     f"{nv} à éviter.")
    decisions = committee.get('decisions') or []
    prio = next((d for d in decisions if d.get('verdict') in ('ACHETER', 'RENFORCER')), None)
    if prio:
        lines.append(f"Opportunité prioritaire : {prio.get('symbol')} — dossier complet à valider avant toute décision.")
    lines.append('Discipline du jour : aucune improvisation — le fondamental prime sur '
                 'le technique, décision finale unique, stops dérivés du sous-jacent.')

    #  `scan_state['daily_changes']` n'était produit par personne : la liste
    #  restait vide à vie (Vertex IA › delta du brief). Le propriétaire du
    #  « depuis la session précédente » est market_context (base persistée).
    #  L'INSTANT DU SCAN, SOUS UNE FORME EXPLOITABLE.
    #  `scan_state['updated']` est une HEURE MURALE nue : mesure du 06/09/2026
    #  sur 5003, il vaut '19:49:23' — ni date, ni fuseau. Le pied de « Brief du
    #  marché » le passe à `VX.updateIndicator`, dont `VX.freshness._ms()` ne
    #  peut rien parser : la carte centrale d'Aujourd'hui affichait « Âge
    #  inconnu · … Différé », sans info-bulle, pendant que ses huit voisines
    #  affichaient « Il y a 24 min » depuis le MÊME instant. Un mode servi sans
    #  âge mesurable est ce que l'invariant 5 interdit.
    #  Ordre de préférence : `scan_ts_h` (déjà une chaîne ISO — c'est celui que
    #  `_trace_aujourdhui` retient plus bas), puis `scan_ts` (époque) CONVERTIE
    #  en ISO, puis `updated` inchangé. La conversion n'est pas cosmétique :
    #  `as_of` est lu ailleurs comme un TEXTE (`'Daté du '+esc(d.as_of)`), et y
    #  servir un flottant afficherait « Daté du 1788716963.687278 ».
    #  La conversion vit dans `_instant_scan` : `render()` en a besoin du mot
    #  pour mot, et l'avoir écrite ici seulement a produit un `data-scan-ts`
    #  illisible par le client (voir la mesure dans ce docstring).
    as_of = (_instant_scan(scan_state) or scan_state.get('updated')
             or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))

    changed = []
    with contextlib.suppress(Exception):
        from vertex.engines import market_context as _mcx
        from vertex.services import persist as _persist
        prev = _persist.load_json('market_context_last.json', None)
        changed = _mcx.build(scan_state, prev=prev).get('changes_since_prev') or []
    return {
        'lines': lines[:12],
        'word_count': sum(len(l.split()) for l in lines[:12]),
        'changed_since_yesterday': changed[:3] if isinstance(changed, list) else [],
        'as_of': as_of,
        'sources': [source],
        'generator': 'deterministic',
        'missing': missing,
        'demo': source == 'demo',
    }



# ── Vertex 2.0 : le point focal d'Aujourd'hui ────────────────────────────────
#
# La page ouvrait sur douze tuiles d'indices de poids RIGOUREUSEMENT ÉGAL. Douze
# choses également importantes, c'est zéro hiérarchie : rien ne dit par où
# commencer. Le premier écran porte désormais une DecisionTrace —
# Donnée → Moteur → Décision → Portefeuille — qui répond en cinq secondes à
# « où en est-on, et qu'est-ce qui bloque ? ».
#
# Elle ne calcule RIEN. Chaque nœud lit `scan_state`, déjà produit par les
# moteurs. Un nœud sans donnée porte `—` et le ton « missing » : il ne devient
# ni zéro, ni vert, ni rassurant.

_REGIME_FR = {'TREND': 'Tendance', 'NEUTRAL': 'Neutre', 'CHOP': 'Sans direction',
              'DOWN': 'Baissier', 'UP': 'Haussier', 'UNKNOWN': 'Indéterminé'}


def _trace_aujourdhui(scan_state: dict) -> str:
    """DecisionTrace du jour, rendue côté serveur depuis `scan_state`."""
    from vertex.ui import vx2

    st = scan_state or {}
    m = {**(st.get('market') or {}), **(st.get('market_ctx') or {})}
    committee = st.get('committee') or {}
    counts = committee.get('counts') or {}

    # ── Donnée : d'où vient ce qu'on regarde, et de quand ────────────────
    source = st.get('source')
    updated = st.get('scan_ts_h') or st.get('updated')
    #  `unavailable` est le jeton INTERNE de terminal.py (scan tourné, zéro
    #  contributeur) : il ne fuit jamais brut à l'écran — mesuré au navigateur
    #  à 390 px pendant la vérification du lot 14.
    if not source or source in ('aucune', 'unavailable'):
        n_donnee = {'label': 'Donnée', 'valeur': 'Aucune source',
                    'meta': ('aucune source n\'a répondu au scan'
                             if source == 'unavailable' else 'aucun scan servi'),
                    'tone': 'negative'}
    else:
        n_donnee = {'label': 'Donnée', 'valeur': str(source),
                    'meta': f'mise à jour {updated}' if updated else 'horodatage —',
                    'tone': 'neutral' if updated else 'caution'}

    # ── Moteur : quel régime a-t-il lu ? ─────────────────────────────────
    brut = m.get('spy_regime') or m.get('regime')
    regime = _REGIME_FR.get(str(brut or '').upper(), brut)
    roro = m.get('roro')
    if not regime:
        n_moteur = {'label': 'Moteur', 'valeur': 'Régime indéterminé',
                    'meta': 'aucun signal de marché', 'tone': 'caution'}
    else:
        # Le ton suit ce que le moteur DIT, il ne le réinterprète pas.
        tone = {'RISK-ON': 'positive', 'RISK-OFF': 'negative'}.get(
            str(roro or '').upper(), 'neutral')
        n_moteur = {'label': 'Moteur', 'valeur': str(regime),
                    'meta': str(roro) if roro else 'orientation —', 'tone': tone}

    # ── Décision : ce que le comité a réellement conclu ───────────────────
    if counts:
        achat = counts.get('ACHETER', 0)
        eviter = counts.get('ÉVITER', counts.get('EVITER', 0))
        n_decision = {
            'label': 'Décision',
            'valeur': (f"{achat} dossier{'s' if achat != 1 else ''} d'achat"
                       if achat else 'Aucun dossier d\'achat'),
            'meta': f"{counts.get('ATTENDRE', 0)} en surveillance · {eviter} à éviter",
            'tone': 'positive' if achat else 'caution'}
    else:
        n_decision = {'label': 'Décision', 'valeur': 'Comité sans verdict',
                      'meta': 'aucun dossier évalué', 'tone': 'missing'}

    # ── Portefeuille : rempli côté client depuis les positions déclarées.
    # Le serveur ne les connaît pas ici : il ne suppose donc rien.
    # L'identifiant est porté par le nœud lui-même : `loadPortfolio` le complète
    # sans que rien n'ait à deviner de quel nœud il s'agit.
    n_portefeuille = {'label': 'Portefeuille', 'valeur': '—',
                      'meta': 'lecture des positions…', 'tone': 'missing',
                      'ident': 'vx-trace-portefeuille'}

    return vx2.decision_trace(
        [n_donnee, n_moteur, n_decision, n_portefeuille],
        emplacement='aujourdhui-hero')


def _hero_aujourdhui(scan_state: dict) -> str:
    from vertex.ui import vx2
    return vx2.surface(
        _trace_aujourdhui(scan_state),
        titre='Où en est-on maintenant ?',
        question='De la donnée au portefeuille, en une lecture.',
        hero=True)

_CONTENT = """
<div class="vx-page-header"%%SCANTS%%>
  <div><p class="vx2-eyebrow">Piloter</p><h1>Aujourd’hui</h1>
  <div class="vx-sub">Que dois-je comprendre, surveiller et revoir maintenant ?</div></div>
  <div class="vx-actions">
    <button class="vx-btn vx-btn-sm vx-btn-ghost" id="vx-context-btn" aria-pressed="false" title="Afficher/replier le contexte marché (Marchés · Pouls · Secteurs · Actus · Mouvements)">+ Contexte marché</button>
    <button class="vx-btn vx-btn-sm vx-btn-ghost" id="vx-customize-btn">Personnaliser</button>
    <div class="vx-segmented" role="group" aria-label="Densité">
      <button data-density-btn="compact" aria-pressed="false">Compact</button>
      <button data-density-btn="confort" aria-pressed="true">Confort</button>
      <button data-density-btn="dense" aria-pressed="false">Dense</button>
    </div>
  </div>
</div>
<div id="vx-demo-banner"></div>
%%HERO%%

<!-- Ancres de section : navigation fluide dans le Dashboard -->
<style>
  [data-block]{scroll-margin-top:118px}
  #vx-dash-anchors{position:sticky;top:calc(var(--vx-topbar-h) + 4px);z-index:15;
    display:flex;flex-wrap:wrap;gap:.35rem;padding:8px 0 10px;
    background:linear-gradient(180deg,var(--vx-app) 78%,transparent)}
  #vx-dash-anchors .vx-chip[aria-pressed="true"]{border-color:var(--vx-brand);color:var(--vx-brand-strong)}
  /* Têtes de section : rythme visuel de la page unique (fusion Marchés) */
  .vx-sect{display:flex;align-items:baseline;gap:.7rem;margin:26px 0 2px}
  .vx-sect b{font-size:12px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
    color:var(--vx-brand,#c9cdd4)}
  .vx-sect b i{font-style:normal;opacity:.45;margin-right:.5rem;font-variant-numeric:tabular-nums}
  #vx-backtop{position:fixed;right:22px;bottom:76px;z-index:30;display:none;
    padding:9px 13px;border-radius:999px;border:1px solid var(--vx-border,#26221e);
    background:var(--vx-surface-1,#141513);color:var(--vx-text-secondary,#b7b3ad);
    font-size:12px;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.35)}
  #vx-backtop:hover{border-color:var(--vx-brand,#c9cdd4);color:var(--vx-brand,#c9cdd4)}
  /* Tuiles météo XL de la Situation : lisibles de loin, ton par liseré + halo */
  #vx-ess-body .vx-statrow{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
  #vx-ess-body .vx-stat{padding:13px 15px;border-radius:12px;background:var(--vx-surface-0,#0d100e);
    border:1px solid var(--vx-border,#26221e);border-left-width:3px;min-width:0}
  #vx-ess-body .vx-stat[data-tone="pos"]{border-left-color:var(--vx-positive,#36c889);box-shadow:inset 0 0 26px rgba(54,200,137,.05)}
  #vx-ess-body .vx-stat[data-tone="neg"]{border-left-color:var(--vx-negative,#ed655c);box-shadow:inset 0 0 26px rgba(237,101,92,.05)}
  #vx-ess-body .vx-stat[data-tone="brand"]{border-left-color:var(--vx-brand,#c9cdd4);box-shadow:inset 0 0 26px rgba(201,205,212,.06)}
  #vx-ess-body .vx-stat-v{font-size:19px !important;font-weight:700;letter-spacing:.01em}
  #vx-ess-body .vx-stat-sub{white-space:normal;line-height:1.4}
  @media (max-width:1100px){#vx-ess-body .vx-statrow{grid-template-columns:repeat(3,1fr)}}
  @media (max-width:640px){#vx-ess-body .vx-statrow{grid-template-columns:repeat(2,1fr)}}
  /* Survol des tuiles indices : réaction visuelle (page vivante) */
  .vx-idx-tile{transition:border-color .15s ease,transform .15s ease}
  .vx-idx-tile:hover{border-color:var(--vx-brand,#c9cdd4);transform:translateY(-1px)}
  /* Brief repliable : lecture confortable, la page reste équilibrée */
  #vx-brief-clamp[data-clamped="1"]{max-height:560px;overflow:hidden;
    -webkit-mask-image:linear-gradient(180deg,#000 80%,transparent);
    mask-image:linear-gradient(180deg,#000 80%,transparent)}
  /* Brief : typographie de lecture */
  #vx-brief-body p{font-size:16px !important;line-height:1.85 !important}
  #vx-brief-body .vx-brief-lines{margin-top:.6rem}
  #vx-brief-body .vx-brief-lines .bl{display:flex;gap:9px;padding:5px 0;align-items:flex-start;font-size:13.5px;line-height:1.6;color:var(--vx-text-secondary,#b7b3ad)}
  #vx-brief-body .vx-brief-lines .bl::before{content:"";flex:0 0 6px;height:6px;border-radius:99px;background:var(--vx-brand,#c9cdd4);margin-top:8px}
  /* Actus : liseré sentiment par article */
  #vx-news-body article{border-left:2px solid transparent;padding-left:9px !important;transition:border-color .15s}
  #vx-news-body article[data-senti="1"]{border-left-color:var(--vx-positive,#36c889)}
  #vx-news-body article[data-senti="-1"]{border-left-color:var(--vx-negative,#ed655c)}
  #vx-news-body article:hover{border-left-color:var(--vx-brand,#c9cdd4)}
  /* Portefeuille : cartes design (fini les lignes) */
  #vx-portfolio .vx-pf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
  #vx-portfolio .vx-pf-card{background:var(--vx-surface-0,#0d100e);border:1px solid var(--vx-border,#26221e);
    border-radius:12px;padding:12px 13px;display:flex;flex-direction:column;gap:5px;min-width:0;
    transition:border-color .15s ease,transform .15s ease}
  #vx-portfolio .vx-pf-card:hover{border-color:var(--vx-brand,#c9cdd4);transform:translateY(-1px)}
  #vx-portfolio .vx-pf-card .pf-pl{font:700 21px/1.1 var(--vx-font-mono,monospace);font-variant-numeric:tabular-nums}
  /* AA mesuré par le gardien navigateur (4,46:1 < 4,5 avec text-dim) : jeton muted (≥ 4,5:1). */
  #vx-portfolio .vx-pf-card .pf-sub{font-size:11.5px;color:var(--vx-text-muted,#828892)}
  .vx-sect span{font-size:11.5px;color:var(--vx-text-dim,#817d77)}
  .vx-sect::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--vx-border,#26221e),transparent)}
  /* Bandeau indices : tuiles KPI denses, sparkline intégrée. Responsive :
     6/rangée desktop → 3/rangée tablette → 2/rangée mobile (lisibilité). */
  .vx-idx-tile{position:relative;overflow:hidden}
  .vx-idx-tile .vx-kpi-value{font-variant-numeric:tabular-nums}
  /*  `#vx-market-grid` MANQUAIT de ces deux listes. C'est le troisième
     conteneur de tuiles — « L'essentiel du jour », arrivé après les deux
     bandeaux — et il n'avait jamais reçu la règle mobile. Ses tuiles gardaient
     donc leur `grid-column:span 2` en ligne : 51 px pour 92 px de contenu à
     390 px, mesuré. « 44 000 » demande 76 px et en recevait 17 : la valeur
     de chaque indice était illisible sur téléphone.
     Le défaut ne se voyait que l'application PEUPLÉE — sur un scan vide, il
     n'y a aucune tuile à écraser. */
  @media (max-width:900px){
    #vx-market-strip .vx-idx-tile,#vx-cross-strip .vx-idx-tile,
    #vx-market-grid .vx-idx-tile{grid-column:span 4 !important}
  }
  @media (max-width:560px){
    #vx-market-strip .vx-idx-tile,#vx-cross-strip .vx-idx-tile,
    #vx-market-grid .vx-idx-tile{grid-column:span 6 !important}
  }
  /* Posture 3 états (lecture moteur — jamais un pourcentage inventé) */
  .vx-posture{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}
  .vx-posture span{padding:9px 6px;text-align:center;border-radius:8px;font-size:11.5px;
    font-weight:700;letter-spacing:.05em;text-transform:uppercase;
    background:var(--vx-surface-0);color:var(--vx-text-dim);border:1px solid transparent}
  .vx-posture span[data-on="def"]{background:rgba(237,101,92,.14);color:var(--vx-negative);border-color:var(--vx-negative)}
  .vx-posture span[data-on="neu"]{background:rgba(221,162,59,.14);color:var(--vx-warning);border-color:var(--vx-warning)}
  .vx-posture span[data-on="att"]{background:rgba(54,200,137,.14);color:var(--vx-positive);border-color:var(--vx-positive)}

  /* ══════════════ ARGENT LUMINEUX — direction graphique (maquette) ══════════════
     Cartes plus profondes + liseré haut lumineux, tuiles KPI façon terminal argent,
     chiffres tabulaires, titres capitales espacées. Vert/rouge réservés au SENS. */
  [data-block] .vx-card{position:relative;overflow:hidden;border-radius:16px;
    border:1px solid rgba(255,255,255,.075);
    background:linear-gradient(180deg,#14151a 0%,#0c0d11 100%);
    box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 26px 56px -40px #000}
  [data-block] .vx-card::after{content:"";position:absolute;left:16px;right:16px;top:0;height:1px;
    background:linear-gradient(90deg,transparent,rgba(255,255,255,.20),transparent);opacity:.55;pointer-events:none}
  [data-block] .vx-card--premium,[data-block] .vx-card--accent{background:linear-gradient(180deg,#16171d 0%,#0d0e12 100%)}
  [data-block] .vx-card-title{font-size:12.5px !important;font-weight:640;letter-spacing:.09em;
    text-transform:uppercase;color:var(--vx-text-secondary,#c2c7cf)}
  /* Tuiles KPI marché (bandeau L'essentiel) */
  [data-block] .vx-idx-tile{border-radius:14px;background:linear-gradient(180deg,#131419,#0b0c10)}
  [data-block] .vx-idx-tile .vx-kpi-label{font-size:11px !important;letter-spacing:.05em;
    text-transform:uppercase;color:var(--vx-text-muted,#7c828c)}
  [data-block] .vx-idx-tile .vx-kpi-value{font-size:21px !important;font-weight:640;letter-spacing:-.02em;
    color:var(--vx-ink);font-variant-numeric:tabular-nums;white-space:nowrap}
  [data-block] .vx-idx-tile .vx-kpi-delta{font-weight:600;font-size:12.5px}
  [data-block] .vx-idx-tile:hover{border-color:rgba(255,255,255,.2);transform:translateY(-1px)}
  /* Lignes clé-valeur (régime, drivers, portefeuille) */
  [data-block] .vx-kv{padding:7px 0;border-bottom:1px solid rgba(255,255,255,.05)}
  [data-block] .vx-kv .k{color:var(--vx-text-secondary,#c2c7cf);font-size:12.5px}
  [data-block] .vx-kv .v{font-weight:640;font-variant-numeric:tabular-nums}
  /* Chiffres : tabulaires partout */
  [data-block] .vx-num,[data-block] .vx-stat-v,[data-block] .vx-metric-v,[data-block] .vx-kpi-value{font-variant-numeric:tabular-nums}
  /* Tableaux (top/flop, comité, positions) : lignes fines, survol argent */
  [data-block] table{border-collapse:collapse;width:100%}
  [data-block] table th{font-size:10px;letter-spacing:.08em;text-transform:uppercase;
    color:var(--vx-text-muted,#7c828c);font-weight:600}
  [data-block] table td,[data-block] table th{border-color:rgba(255,255,255,.05) !important}
  [data-block] table tbody tr{transition:background .12s}
  [data-block] table tbody tr:hover{background:rgba(255,255,255,.025)}
  /* Tuiles météo (lecture en clair) : fond plus profond, halo doux conservé */
  [data-block] #vx-ess-body .vx-stat{background:linear-gradient(180deg,#131419,#0c0d10);border-color:rgba(255,255,255,.06)}
  /* Puces d'alerte + insight : liseré argent par défaut */
  [data-block] .vx-insight{border-radius:12px}
  /* Jauge de régime → bille BLANCHE lumineuse (maquette) : la « needle » (dernier
     cercle du SVG) devient une bille blanche à halo, comme le curseur de référence. */
  [data-block] #vx-regime-gauge .vx-gauge svg circle{
    r:7px;fill:#ffffff;
    filter:drop-shadow(0 0 9px rgba(255,255,255,.85)) drop-shadow(0 0 3px #fff)}
  [data-block] #vx-regime-gauge .vx-gauge svg text[font-size="30"]{fill:var(--vx-ink) !important}
  /* ── Polish transversal : survols de carte, chips argent, badges nets ── */
  [data-block] .vx-card{transition:border-color .18s ease,box-shadow .18s ease}
  [data-block] .vx-card:hover{border-color:rgba(255,255,255,.16);
    box-shadow:0 1px 0 rgba(255,255,255,.06) inset,0 30px 64px -38px #000}
  [data-block] .vx-chip,#vx-dash-anchors .vx-chip{border-radius:9px;
    border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.025);
    color:var(--vx-text-secondary,#c2c7cf);transition:border-color .15s ease,color .15s ease,background .15s ease}
  [data-block] .vx-chip:hover,#vx-dash-anchors .vx-chip:hover{border-color:rgba(255,255,255,.24);color:#f5f7fa}
  [data-block] .vx-chip[aria-pressed="true"],#vx-dash-anchors .vx-chip[aria-pressed="true"]{
    border-color:rgba(255,255,255,.34);color:#fff;background:rgba(255,255,255,.07)}
  [data-block] .vx-badge{border-radius:7px}
  /* Boutons fantômes : liseré argent au survol */
  [data-block] .vx-btn-ghost:hover{border-color:rgba(255,255,255,.22);color:#f5f7fa}
  /* Segmented densité : fond profond cohérent */
  .vx-segmented{background:linear-gradient(180deg,#14151a,#0c0d11);border-color:rgba(255,255,255,.08)}

  /* ═══════════ SOBRE & ESSENTIEL — cartes épurées, hiérarchie forte ═══════════
     Cartes plus calmes (liseré discret), et tout le SECONDAIRE (méta, sous-titres,
     pieds, badges de contexte) recule au second plan pour laisser respirer l'essentiel.
     Aucune donnée supprimée — la fraîcheur et l'indicateur « démo » restent lisibles. */
  [data-block] .vx-card{border-color:rgba(255,255,255,.055)}
  [data-block] .vx-card::after{opacity:.28}
  [data-block] .vx-card-header{margin-bottom:12px}
  /* Sous-titres / questions de carte : discrets */
  /* opacité RETIRÉE (lot 30) : elle abaissait le jeton AA à ~3,8:1 — mesuré
     Lighthouse. La hiérarchie vient du jeton, de la taille et de l'italique. */
  [data-block] .vx-chart-question{font-size:11px;font-style:italic}
  /* Méta, pieds, indicateurs de fraîcheur : au second plan (mais lisibles) */
  [data-block] .vx-meta{font-size:10.5px;color:var(--vx-text-muted,#7c828c)}
  [data-block] .vx-card-footer,[data-block] .vx-card-foot{opacity:.7}
  [data-block] .vx-card-footer .vx-badge{font-size:10px}
  /* Badges de CONTEXTE (méta gris) : discrets — les badges de décision colorés
     (ACHETER, RISK-OFF…) gardent toute leur force car ils portent une couleur. */
  [data-block] .vx-badge:not([style*="color"]){background:rgba(255,255,255,.03);
    border-color:rgba(255,255,255,.07);color:var(--vx-text-muted,#7c828c);font-weight:500}
  /* Valeurs clés : bien présentes, pleine lumière */
  [data-block] .vx-kpi-value,[data-block] .vx-stat-v,[data-block] .vx-num{color:#f5f7fa}
  /* Titres de tuiles « lecture en clair » : plus d'air */
  [data-block] #vx-ess-body .vx-statrow{gap:12px}
  [data-block] #vx-ess-body .vx-stat{padding:15px 16px}

  /* ── BRIEF PRO : phrase-titre + encart « Essentiels de la journée » ── */
  [data-block] .vx-brief-lead{font-size:17.5px;line-height:1.62;font-weight:600;color:#f5f7fa;margin:2px 0 14px}
  [data-block] .vx-brief-ess{margin:0 0 6px;padding:14px 16px;border-radius:13px;
    background:rgba(255,255,255,.022);border:1px solid rgba(255,255,255,.06)}
  [data-block] .vx-brief-ess-k{font-size:10px;letter-spacing:.12em;text-transform:uppercase;
    color:var(--vx-text-muted,#7c828c);margin-bottom:9px}
  [data-block] .vx-brief-ess .be{display:flex;gap:10px;align-items:flex-start;padding:4px 0;
    font-size:13.5px;color:var(--vx-text-secondary,#c2c7cf);line-height:1.5}
  [data-block] .vx-brief-ess .be-dot{flex:0 0 6px;height:6px;border-radius:99px;background:#d8dde4;
    margin-top:7px;box-shadow:0 0 6px rgba(216,221,228,.5)}
  /* Détail replié par défaut (BREF) — « Lire la suite » révèle le reste */
  [data-block] #vx-brief-clamp[data-clamped="1"]{max-height:0 !important;overflow:hidden;opacity:0;margin:0;
    -webkit-mask-image:none !important;mask-image:none !important}
  [data-block] #vx-brief-clamp{transition:opacity .2s ease}
  /* Cartes un poil plus grandes & plus belles (hors tuiles KPI compactes) */
  [data-block] .vx-card:not(.vx-card--compact):not(.vx-idx-tile){border-radius:18px}
  [data-block] .vx-card--premium,[data-block] .vx-card--hero{padding:22px 24px}

  /* ═══════════ CONCENTRÉ & BEAU — cartes/listes plus denses et raffinées ═══════════ */
  /* En-tête de carte : compact + filet fin (structure nette) */
  [data-block] .vx-card-header{padding-bottom:9px;margin-bottom:13px;
    border-bottom:1px solid rgba(255,255,255,.05)}
  /* Movers (Top 10) & opportunités : cartes qui REMPLISSENT la largeur (auto-fit), plus grandes */
  [data-block] .vx-movergrid{grid-template-columns:repeat(auto-fit,minmax(184px,1fr)) !important;gap:12px}
  /* Opportunités : cartes nettement plus grandes (priorité id + !important sur la règle ci-dessus) */
  [data-block] #vx-opp-stocks .vx-movergrid{grid-template-columns:repeat(auto-fit,minmax(262px,1fr)) !important}
  [data-block] #vx-opp-options .vx-movergrid{grid-template-columns:repeat(auto-fit,minmax(234px,1fr)) !important}
  [data-block] .vx-mover{border-radius:14px;padding:14px 15px;
    background:linear-gradient(180deg,#14161c,#0b0c10);border:1px solid rgba(255,255,255,.07);
    transition:border-color .15s ease,transform .15s ease,box-shadow .15s ease}
  [data-block] .vx-mover:hover{border-color:rgba(255,255,255,.22);transform:translateY(-2px);
    box-shadow:0 8px 22px -12px rgba(0,0,0,.7)}
  [data-block] .vx-mover .mv-sym{font-weight:690;font-size:15px;letter-spacing:.01em}
  [data-block] .vx-mover .mv-chg{font-size:21px;font-weight:660;margin-top:3px;font-variant-numeric:tabular-nums}
  [data-block] .vx-mover .mv-sub{font-size:11px;color:var(--vx-text-muted,#7c828c);margin-top:2px}
  /* Tables : lignes denses, séparateurs fins */
  [data-block] table td{padding:9px 8px}
  [data-block] table tbody tr:first-child td{border-top:0}
  /* Cartes portefeuille : grille plus concentrée */
  [data-block] #vx-portfolio .vx-pf-grid{grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
  [data-block] #vx-portfolio .vx-pf-card{border-radius:14px;padding:14px 16px;
    background:linear-gradient(180deg,#14161c,#0b0c10)}
  /* Opportunités options : cartes compactes */
  [data-block] #vx-opp-options .vx-mover{padding:11px 13px}

  /* ── KPI MODERNE — prix + variation (flèche), sans mini-courbe ── */
  [data-block] .vx-idx-tile{padding:15px 16px}
  [data-block] #vx-market-grid .vx-idx-tile .vx-kpi-value{font-size:23px !important;margin-top:3px;line-height:1.1}
  [data-block] .vx-idx-tile .vx-kpi-delta{display:inline-flex;align-items:center;gap:5px;
    font-size:12.5px;font-weight:600;margin-top:4px}
  [data-block] .vx-idx-tile .vx-arw{font-style:normal;font-size:8.5px;line-height:1;opacity:.9}

  /* ═══════════ DESIGN DES MODULES — en-têtes de section & de carte ═══════════ */
  /* En-tête de SECTION : le numéro devient une pastille encadrée (repère net) */
  [data-block] .vx-sect{align-items:center;margin:32px 0 8px;gap:.7rem}
  [data-block] .vx-sect b{display:inline-flex;align-items:center;gap:.6rem;color:#eef1f5;font-size:12px;letter-spacing:.13em}
  [data-block] .vx-sect b i{font-style:normal;opacity:1;font-weight:600;font-size:10.5px;
    display:inline-grid;place-items:center;min-width:24px;height:24px;padding:0 5px;border-radius:8px;
    border:1px solid rgba(255,255,255,.15);background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,.02));
    color:var(--vx-text-secondary,#c2c7cf);margin-right:0;box-shadow:0 1px 0 rgba(255,255,255,.06) inset}
  [data-block] .vx-sect span{font-size:11.5px;color:var(--vx-text-muted,#7c828c)}
  [data-block] .vx-sect::after{height:1px;background:linear-gradient(90deg,rgba(255,255,255,.11),transparent)}
  /* En-tête de CARTE : titre + accent argent net, méta/actions alignées à droite */
  [data-block] .vx-card-header{align-items:center;gap:10px}
  [data-block] .vx-card-header .vx-actions{margin-left:auto}
</style>
<nav id="vx-dash-anchors" aria-label="Sections du Dashboard"></nav>

<!-- ═══ 1. L'ESSENTIEL — le marché en langage simple + posture du moteur ═══ -->
<div data-block="essential" data-anchor-label="L’essentiel">
<div class="vx-sect"><b><i>01</i>L’essentiel du jour</b><span>indices · devises · matières · crypto — le marché au coup d’œil</span></div>
<div class="vx-grid vx-mt2" id="vx-market-grid" aria-label="L’essentiel du jour — indices, devises, matières &amp; crypto"></div>
<div class="vx-grid vx-mt2">
  <section class="vx-card vx-col-12 vx-card--premium" id="vx-essential" aria-label="L’essentiel du jour">
    <div class="vx-card-header"><span class="vx-card-title">Lecture en clair — tendance, volatilité, humeur</span>
      <span class="vx-chart-question">Que fait le marché, sans jargon ?</span>
      <span class="vx-actions vx-meta" id="vx-ess-meta"></span></div>
    <div id="vx-ess-body">%%LOADING%%</div>
  </section>
</div>
</div>

<!-- ═══ 2. OPPORTUNITÉS ACTIVES (décision-first) : actions · options · entonnoir ═══ -->
<div data-block="opportunities" data-anchor-label="Opportunités">
  <div class="vx-sect"><b><i>02</i>Opportunités actives</b><span>ce que le comité retient — avec le POURQUOI de chaque idée</span></div>
  <div class="vx-grid vx-mt2">
    <section class="vx-card vx-col-6" aria-label="Opportunités actions">
      <div class="vx-card-header"><span class="vx-card-title">Opportunités actions</span>
        <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities?view=stocks">Tout voir →</a></span></div>
      <div id="vx-opp-stocks">%%LOADING%%</div>
      <div id="vx-opp-rr" class="vx-mt2"></div>
    </section>
    <section class="vx-card vx-col-6" aria-label="Opportunités options">
      <div class="vx-card-header"><span class="vx-card-title">Opportunités options</span>
        <span class="vx-badge" style="color:var(--vx-violet)">Vertex Dynamic Options</span>
        <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities?view=options">Tout voir →</a></span></div>
      <div id="vx-opp-options">%%LOADING%%</div>
    </section>
  </div>
  <div class="vx-grid vx-mt4">
    <section class="vx-card vx-col-4 vx-card--accent" aria-label="Entonnoir de sélection">
      <div class="vx-card-header"><span class="vx-card-title">Entonnoir</span>
        <span class="vx-chart-question">Combien de dossiers survivent au tri ?</span></div>
      <div id="vx-opp-funnel">%%LOADING%%</div>
    </section>
    <div class="vx-col-8" id="vx-opp-posture"></div>
  </div>
</div>

<!-- ═══ PORTEFEUILLE ═══ -->
<div data-block="portfolio" data-anchor-label="Portefeuille">
  <div class="vx-sect"><b><i>07</i>Portefeuille</b><span>tes positions déclarées — synthèse d’équipe</span></div>
  <div class="vx-grid vx-mt2">
    <section class="vx-card vx-col-12" aria-label="Portefeuille">
      <div class="vx-card-header"><span class="vx-card-title">Portefeuille — Équipe Vertex</span>
        <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/portfolio">Ouvrir →</a></span></div>
      <div id="vx-portfolio">%%LOADING%%</div>
    </section>
  </div>
</div>

<!-- ═══ ALERTES DE LA JOURNÉE ═══ -->
<div data-block="alerts" data-anchor-label="Alertes">
  <div class="vx-sect"><b><i>08</i>Alertes de la journée</b><span>risque · cassures · invalidations · catalyseurs imminents</span></div>
  <div class="vx-grid vx-mt2">
    <section class="vx-card vx-col-12" aria-label="Alertes prioritaires">
      <div class="vx-card-header"><span class="vx-card-title">Radar d’alertes</span>
        <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities?view=radar">Radar →</a></span></div>
      <div id="vx-alerts">%%LOADING%%</div>
    </section>
  </div>
</div>

<!-- ═══ 4. BRIEF VERTEX + CE QUI COMPTE ═══ -->
<div data-block="brief" data-anchor-label="Brief">
<div class="vx-sect"><b><i>04</i>Brief du marché</b><span>la synthèse écrite du jour — composée uniquement des données moteur</span></div>
<div class="vx-grid vx-mt2">
  <section class="vx-card vx-card--hero vx-col-8" id="vx-brief" aria-label="Brief Vertex">
    <div class="vx-card-header"><span class="vx-card-title">Brief du marché — Vertex</span>
      <span class="vx-actions" id="vx-brief-meta"></span></div>
    <div id="vx-brief-body">%%LOADING%%</div>
  </section>
  <section class="vx-card vx-col-4" id="vx-brief-side" aria-label="Ce qui compte aujourd’hui">
    <div class="vx-card-header"><span class="vx-card-title">Ce qui compte</span></div>
    <div id="vx-brief-side-body">%%LOADING%%</div>
  </section>
  <!-- `vx-col-12` MANQUAIT : sans classe de portée, un enfant direct de
       `.vx-grid` occupe UNE colonne sur douze. « Ce qui a changé » était
       donc servie à 95 px à 1600 px et à 20 px à 390 px — un ruban de
       texte illisible, à toutes les largeurs, depuis sa création. -->
  <aside class="vx-insight-rail vx-col-12" style="grid-template-columns:minmax(0,1fr)" aria-label="Changements depuis la dernière visite">
    <section class="vx-card">
      <div class="vx-card-header"><span class="vx-card-title">Ce qui a changé</span></div>
      <div id="vx-diff">%%LOADING%%</div>
    </section>
  </aside>
</div>
</div>

<!-- ═══ RÉGIME DE MARCHÉ (verdict + drivers + que faire) ═══ -->
<div data-block="regime" data-anchor-label="Régime">
  <div class="vx-sect"><b><i>04</i>Régime de marché</b><span>peut-on attaquer, attendre ou protéger — et pourquoi</span></div>
  <div class="vx-grid vx-mt2">
    <section class="vx-card vx-col-5 vx-card--premium" id="vx-regime" aria-label="Verdict du régime">
      <div class="vx-card-header"><span class="vx-card-title">Verdict du régime</span></div>
      <div id="vx-regime-body">%%LOADING%%</div>
    </section>
    <section class="vx-card vx-col-7 vx-card--accent" aria-label="Ce qui porte le régime">
      <div class="vx-card-header"><span class="vx-card-title">Ce qui porte le régime</span>
        <span class="vx-chart-question">Quelles forces sont pour ou contre aujourd’hui ?</span></div>
      <div id="vx-regime-drivers">%%LOADING%%</div>
      <div id="vx-regime-todo" class="vx-mt3"></div>
    </section>
  </div>
</div>

<!-- ═══ CALENDRIER DU JOUR / SEMAINE ═══ -->
<div data-block="calendar" data-anchor-label="Calendrier">
  <div class="vx-sect"><b><i>05</i>Calendrier du jour / semaine</b><span>macro · résultats · Fed — et les dates de tes actions</span></div>
  <div class="vx-grid vx-mt2">
    <div class="vx-col-12" id="vx-calendar"></div>
  </div>
</div>

<!-- ═══ ACTUS & CATALYSEURS (queue analytique) ═══ -->
<div data-block="news" data-anchor-label="Actus">
  <div class="vx-sect"><b><i>10</i>Actus &amp; catalyseurs</b><span>l’information du jour · sources publiques assainies</span></div>
  <div class="vx-grid vx-mt2">
    <section class="vx-card vx-col-12" id="vx-news" aria-label="Actualités marquantes">
      <div class="vx-card-header"><span class="vx-card-title">Actualités marquantes</span>
        <span class="vx-chart-question">Qu’est-ce qui fait bouger le marché aujourd’hui ?</span></div>
      <div id="vx-news-body" style="max-height:430px;overflow-y:auto">%%LOADING%%</div>
    </section>
  </div>
</div>

<!-- ═══ 3. MARCHÉS (fusion) : indices · graphique héros · comparaison · taux ═══ -->
<div data-block="markets" data-anchor-label="Marchés">
  <div class="vx-sect"><b><i>06</i>Marchés</b><span>indices avec mini-courbes · devises, matières &amp; crypto · taux</span></div>
  <div class="vx-grid vx-mt2" id="vx-market-strip" aria-label="Indices"></div>
  <div class="vx-grid vx-mt2" id="vx-cross-strip" aria-label="Cross-asset"></div>
  <div class="vx-grid vx-mt4">
    <div class="vx-col-8" id="vx-market-chart"></div>
    <div class="vx-col-4" id="vx-market-compare"></div>
  </div>
  <div class="vx-grid vx-mt4">
    <div class="vx-col-8" id="vx-yield"></div>
    <section class="vx-card vx-col-4" id="vx-roro-card" aria-label="Appétit pour le risque">
      <div class="vx-card-header"><span class="vx-card-title">Appétit pour le risque</span>
        <span class="vx-chart-question">Risk-on ou risk-off ?</span></div>
      <div id="vx-roro-body">%%LOADING%%</div>
    </section>
  </div>
</div>

<!-- ═══ 7. POULS : jauges VIX/breadth/régime + posture + internals ═══ -->
<div data-block="pulse" data-anchor-label="Pouls">
  <div class="vx-sect"><b><i>07</i>Pouls du marché</b><span>volatilité · participation · santé — tous les indicateurs internes</span></div>
  <div class="vx-grid vx-mt2">
    <section class="vx-card vx-col-8 vx-card--accent" aria-label="Pouls du marché">
      <div class="vx-card-header"><span class="vx-card-title">Pouls du marché</span>
        <span class="vx-actions vx-meta" id="vx-pulse-meta"></span></div>
      <div class="vx-flex vx-wrap" style="gap:1rem;align-items:flex-start;justify-content:space-around">
        <div id="vx-gauge-vix" style="flex:1;min-width:170px">%%LOADING%%</div>
        <div id="vx-gauge-breadth" style="flex:1;min-width:170px"></div>
        <div id="vx-gauge-trend" style="flex:1;min-width:170px"></div>
      </div>
    </section>
    <section class="vx-card vx-col-4 vx-card--accent" aria-label="Positionnement du régime">
      <div class="vx-card-header"><span class="vx-card-title">Positionnement</span></div>
      <div id="vx-regime-rail">%%LOADING%%</div>
    </section>
  </div>
  <div class="vx-grid vx-mt4">
    <section class="vx-card vx-col-6 vx-card--premium" id="vx-breadth-internals-card" aria-label="Breadth internals">
      <div class="vx-card-header"><span class="vx-card-title">Participation</span>
        <span class="vx-chart-question">La hausse est-elle portée par beaucoup de titres, ou par une poignée ?</span></div>
      <div id="vx-breadth-internals">%%LOADING%%</div>
    </section>
    <section class="vx-card vx-col-6 vx-card--accent" id="vx-breadth-rings-card" aria-label="Composite de participation">
      <div class="vx-card-header"><span class="vx-card-title">Composite de participation</span></div>
      <div id="vx-breadth-rings">%%LOADING%%</div>
      <div class="vx-card-foot"><span class="vx-meta">Anneaux = part des titres au-dessus des moyennes et ratio d’avancées, sur l’univers scanné.</span></div>
    </section>
  </div>
  <div class="vx-grid vx-mt4">
    <div class="vx-col-6" id="vx-breadth-trend"></div>
    <section class="vx-card vx-col-6" id="vx-score-dist-card" aria-label="Distribution des scores">
      <div class="vx-card-header"><span class="vx-card-title">Scores de l’univers</span>
        <span class="vx-chart-question">Le marché est-il globalement fort ou faible ?</span></div>
      <div id="vx-score-dist">%%LOADING%%</div>
      <div class="vx-card-foot"><span class="vx-meta">Nombre de titres par tranche de score Vertex (0-100). Décalage à droite = univers globalement fort.</span></div>
    </section>
  </div>
  <div class="vx-grid vx-mt4">
    <section class="vx-card vx-col-12" id="vx-health-card" aria-label="Composition de la santé du marché">
      <div class="vx-card-header"><span class="vx-card-title">Santé du marché</span>
        <span class="vx-chart-question">Quelles composantes portent (ou plombent) la santé du jour ?</span></div>
      <div id="vx-health-wf" style="height:230px">%%LOADING%%</div>
      <div class="vx-card-foot"><span class="vx-meta">Santé = 30 % (&gt; moy. 50 j) + 25 % (&gt; moy. 200 j) + 25 % (participation) + 20 % (avancées/déclins) — pondérations réelles du moteur d’internals.</span></div>
    </section>
  </div>
</div>

<!-- ═══ 5. MOUVEMENTS : top / flop de la séance ═══ -->
<div data-block="topflop" data-anchor-label="Top 10">
  <div class="vx-sect"><b><i>06</i>Top 10 hausse / baisse</b><span>plus fortes hausses et baisses de l’univers scanné</span></div>
  <div class="vx-grid vx-mt2">
    <div class="vx-col-12" id="vx-move-summary"></div>
    <section class="vx-card vx-col-6" aria-label="Top 10 hausse">
      <div class="vx-card-header"><span class="vx-card-title">Top 10 hausse</span>
        <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities?view=stocks">Univers →</a></span></div>
      <div id="vx-top10">%%LOADING%%</div>
    </section>
    <section class="vx-card vx-col-6" aria-label="Top 10 baisse">
      <div class="vx-card-header"><span class="vx-card-title">Top 10 baisse</span>
        <span class="vx-actions"><span class="vx-meta">plus fortes baisses · univers scanné</span></span></div>
      <div id="vx-flop10">%%LOADING%%</div>
    </section>
  </div>
</div>

<!-- ═══ 6. SECTEURS & ROTATION ═══ -->
<div data-block="sectors" data-anchor-label="Secteurs">
  <div class="vx-sect"><b><i>09</i>Secteurs &amp; rotation</b><span>où va le capital — cliquer un secteur ouvre ses opportunités</span></div>
  <div class="vx-grid vx-mt2">
    <div class="vx-col-8" id="vx-sectors-quadrant"></div>
    <div class="vx-col-4" id="vx-rotation"></div>
  </div>
  <div class="vx-grid vx-mt4">
    <div class="vx-col-12" id="vx-sectors-heat"></div>
  </div>
  <div class="vx-grid vx-mt4">
    <section class="vx-card vx-col-12" aria-label="Poids et performance par secteur">
      <div class="vx-card-header"><span class="vx-card-title">Poids &amp; performance par secteur</span>
        <span class="vx-chart-question">Où se concentre l’univers, et qui performe ?</span></div>
      <div id="vx-sectors-tree" style="height:300px">%%LOADING%%</div>
      <div class="vx-card-foot"><span class="vx-meta">Taille = nombre de titres scannés du secteur · couleur = variation moyenne du jour (vert entrant / rouge sortant).</span></div>
    </section>
  </div>
</div>

<button id="vx-backtop" aria-label="Remonter en haut">↑ Haut</button>

"""

_JS = r"""
<script src="/static/vertex/js/charts/sparkline.js" defer></script>
<script src="/static/vertex/js/charts/line-area-chart.js" defer></script>
<script src="/static/vertex/js/charts/breadth-chart.js" defer></script>
<script src="/static/vertex/js/charts/sector-chart.js" defer></script>
<script src="/static/vertex/js/charts/bar-chart.js" defer></script>
<script src="/static/vertex/js/charts/donut-chart.js" defer></script>
<script src="/static/vertex/js/charts/heatmap.js" defer></script>
<script src="/static/vertex/js/charts/timeline-chart.js" defer></script>
<script>
(function(){
'use strict';
const $=(id)=>document.getElementById(id);
const E=()=>window.VXEntities;
function esc(s){return String(s??'').replace(/[<>&"]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));}
/* MODE des données du scan (8 pieds de cette page). « live » n'y est pas
   prouvable : /scan ne transporte que des BARRES QUOTIDIENNES (terminal.py :
   fetch_universe_bars(duration='1 Y') côté courtier, yf.download(interval='1d')
   côté web) et la route le dit (scan_api.py : « le badge LIVE IBKR reste piloté
   par l'overlay /quotes — lui seul voit les ticks »). Mesure du 06/09/2026 :
   quand le courtier sert TOUT l'univers, scan.source vaut exactement 'ibkr' et
   ces pieds annonçaient « ibkr Live » sur des clôtures. Le pied « Essentiels »
   (loadEssential) pratiquait déjà la forme honnête ; elle devient la règle. */
function modeOf(scan){return scan&&scan.data_source==='demo'?'fallback':'delayed';}
/* Hauteurs STANDARD des graphiques : compact 160 · standard 240 · héros 320 */
const H_CPT=160,H_STD=240,H_HERO=320;

/* Personnalisation contrôlée des blocs (§43 — vxDashboardLayout.hidden).
   ORDRE CANONIQUE du Dashboard (refonte §skill) : l'essentiel → brief → régime →
   calendrier → opportunités → top 10 → portefeuille → alertes, puis la queue
   analytique (actus, marchés, pouls, secteurs). reorderBlocks() applique cet ordre au DOM. */
const BLOCK_ORDER=['essential','brief','regime','calendar','opportunities','topflop',
  'portfolio','alerts','news','markets','pulse','sectors'];
const BLOCKS=[['essential','L’essentiel du jour'],['brief','Brief du marché'],
  ['regime','Régime de marché'],['calendar','Calendrier du jour / semaine'],
  ['opportunities','Opportunités actives'],['topflop','Top 10 hausse / baisse'],
  ['portfolio','Portefeuille'],['alerts','Alertes de la journée'],
  ['news','Actus & catalyseurs'],['markets','Marchés (contexte)'],
  ['pulse','Pouls du marché'],['sectors','Secteurs & rotation']];
/* Dashboard « cockpit » : les 8 sections du skill sont visibles par défaut ; seule
   la queue analytique fine (actus, marchés détaillés, pouls, secteurs) reste repliée,
   ré-affichable via « Contexte marché » ou « Personnaliser ». Rien n'est supprimé. */
const DEFAULT_HIDDEN=['news','markets','pulse','sectors'];
/* Réordonne les blocs dans l'ordre canonique + renumérote les pastilles de section. */
function reorderBlocks(){
  const map={};document.querySelectorAll('[data-block]').forEach(b=>map[b.dataset.block]=b);
  const first=BLOCK_ORDER.map(id=>map[id]).find(Boolean);if(!first)return;
  const parent=first.parentNode,anchor=parent.querySelector('#vx-backtop');
  BLOCK_ORDER.forEach(id=>{if(map[id])parent.insertBefore(map[id],anchor);});
  let n=0;BLOCK_ORDER.forEach(id=>{const b=map[id];if(!b)return;
    const num=b.querySelector('.vx-sect i');if(num){n++;num.textContent=(n<10?'0':'')+n;}});
}
function layoutGet(){try{return JSON.parse(localStorage.getItem('vxDashboardLayout')||'{}')}catch(e){return{}}}
function layoutSet(l){try{localStorage.setItem('vxDashboardLayout',JSON.stringify(l))}catch(e){}}
function effectiveHidden(){const l=layoutGet();return (l.hidden!==undefined)?l.hidden:DEFAULT_HIDDEN.slice();}
function applyBlocks(){
  const hidden=effectiveHidden();
  document.querySelectorAll('[data-block]').forEach(el=>{
    el.style.display=hidden.includes(el.dataset.block)?'none':'';});
  document.querySelectorAll('#vx-dash-anchors [data-anchor]').forEach(b=>{
    b.style.display=hidden.includes(b.dataset.anchor)?'none':'';});
  const btn=document.getElementById('vx-context-btn');
  if(btn){const tailHidden=DEFAULT_HIDDEN.some(b=>hidden.includes(b));
    btn.textContent=tailHidden?'+ Contexte marché':'– Réduire au poste';
    btn.setAttribute('aria-pressed',String(!tailHidden));}
}
document.getElementById('vx-context-btn')?.addEventListener('click',()=>{
  const l=layoutGet(),hidden=effectiveHidden();
  const tailHidden=DEFAULT_HIDDEN.some(b=>hidden.includes(b));
  l.hidden=tailHidden?hidden.filter(b=>!DEFAULT_HIDDEN.includes(b))
                     :Array.from(new Set([...hidden,...DEFAULT_HIDDEN]));
  layoutSet(l);applyBlocks();
});
document.getElementById('vx-customize-btn')?.addEventListener('click',()=>{
  const hidden=effectiveHidden();
  VX.shell.openModal('Personnaliser le Dashboard',
    BLOCKS.map(([id,label])=>`<label class="vx-checkbox" style="padding:5px 0">
      <input type="checkbox" data-blk="${id}" ${hidden.includes(id)?'':'checked'}> ${label}</label>`).join('')
    +'<div class="vx-help vx-mt2">Grille contrôlée — l’ordre des rangées reste fixe. Enregistré sur cet appareil.</div>',
    '<button class="vx-btn" id="vx-layout-reset">Réinitialiser</button>'
    +'<button class="vx-btn vx-btn-primary" id="vx-layout-save">Enregistrer</button>');
  document.getElementById('vx-layout-save').addEventListener('click',()=>{
    const l=layoutGet();
    l.hidden=[...document.querySelectorAll('[data-blk]')].filter(c=>!c.checked).map(c=>c.dataset.blk);
    layoutSet(l);applyBlocks();VX.shell.closeModal();VX.toast('Dashboard personnalisé','success');});
  document.getElementById('vx-layout-reset').addEventListener('click',()=>{
    const l=layoutGet();delete l.hidden;layoutSet(l);applyBlocks();VX.shell.closeModal();
    VX.toast('Disposition réinitialisée');});
});

/* Densité (vxDashboardLayout §43) */
(function(){
  let layout={};try{layout=JSON.parse(localStorage.getItem('vxDashboardLayout')||'{}')}catch(e){}
  const mode=layout.density||'confort';
  if(mode!=='confort')document.body.dataset.density=mode==='compact'?'compact':'dense';
  document.querySelectorAll('[data-density-btn]').forEach(b=>{
    b.setAttribute('aria-pressed',String(b.dataset.densityBtn===mode));
    b.addEventListener('click',()=>{
      layout.density=b.dataset.densityBtn;
      try{localStorage.setItem('vxDashboardLayout',JSON.stringify(layout))}catch(e){}
      document.body.dataset.density=layout.density==='compact'?'compact':(layout.density==='dense'?'dense':'');
      document.querySelectorAll('[data-density-btn]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
    });
  });
})();

/* ── Cross-asset UNIFIÉ (ex-page Marchés) : indices actions (scan.indices :
   .price/.change %), matières & crypto (scan.commodities : .price/.change %),
   taux & dollar (scan.macro : .value + .chg en POINTS absolus). Normalise les
   noms (WTI→Pétrole, Dollar (DXY)→DXY). Aucun point inventé. ── */
function crossAsset(scan){
  const m={};
  ((scan&&scan.indices)||[]).forEach(i=>{if(i&&i.name)m[i.name]={last:i.price,change:i.change,series:i.spark};});
  ((scan&&scan.commodities)||[]).forEach(c=>{if(c&&c.name){const nm=(c.name==='WTI')?'Pétrole':c.name;
    m[nm]={last:c.price,change:c.change,series:c.spark};}});
  ((scan&&scan.macro)||[]).forEach(x=>{if(x&&x.name){const nm=(x.name==='Dollar (DXY)')?'DXY':x.name;
    m[nm]={last:x.value,change:x.chg,unit:x.unit,deltaUnit:'pts',deltaNeutral:true};}});
  return m;
}
function sparkSvg(vals,pos,neutral){
  if(!Array.isArray(vals)||vals.length<2)return '';
  const w=200,h=46,pad=3,mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rng=(mx-mn)||1;
  const P=vals.map((v,i)=>[pad+(i/(vals.length-1))*(w-pad*2), h-pad-((v-mn)/rng)*(h-pad*2)]);
  /* courbe lissée (Catmull-Rom → bézier) — plus premium qu'une polyligne */
  let d='M '+P[0][0].toFixed(1)+' '+P[0][1].toFixed(1);
  for(let i=0;i<P.length-1;i++){const p0=P[i-1]||P[i],p1=P[i],p2=P[i+1],p3=P[i+2]||p2;
    const c1x=p1[0]+(p2[0]-p0[0])/6,c1y=p1[1]+(p2[1]-p0[1])/6,c2x=p2[0]-(p3[0]-p1[0])/6,c2y=p2[1]-(p3[1]-p1[1])/6;
    d+=` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;}
  /* neutral : VIX/taux/DXY → ARGENT (la direction ne code pas « bon/mauvais ») */
  const col=neutral?'#d8dde4':(pos?'var(--vx-positive,#36c889)':'var(--vx-negative,#ed655c)');
  const gid='sg'+Math.abs((''+d).split('').reduce((a,c)=>((a<<5)-a+c.charCodeAt(0))|0,0));
  const lp=P[P.length-1];
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" width="100%" height="42" style="margin-top:8px;display:block" aria-hidden="true">
    <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${col}" stop-opacity=".22"/><stop offset="72%" stop-color="${col}" stop-opacity=".05"/><stop offset="100%" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <path d="${d} L ${w-pad} ${h-pad} L ${pad} ${h-pad} Z" fill="url(#${gid})"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round" opacity=".42" style="filter:drop-shadow(0 0 4px ${col})"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
    <circle cx="${lp[0].toFixed(1)}" cy="${lp[1].toFixed(1)}" r="1.8" fill="#fff" vector-effect="non-scaling-stroke"/></svg>`;
}
/* Tuile KPI du bandeau (indice, matière, taux). deltaNeutral : la variation ne
   code pas « bon/mauvais » (VIX, taux, DXY) → neutre. */
function kpiCell(label,d,scan,span){
  const val=d&&(d.last??d.price??d.close);const chg=d?d.change:null;
  const neu=!!(d&&d.deltaNeutral);
  const dcls=neu?'vx-muted':(chg>0?'vx-pos':chg<0?'vx-neg':'vx-muted');
  const arrow=(chg==null||neu)?'':(chg>0?'▲':chg<0?'▼':'');
  const dtxt=(chg===null||chg===undefined)?'n/d'
    :((d&&d.deltaUnit)?((chg>0?'+':'')+VX.fmt.num(chg,2)+' '+d.deltaUnit):VX.fmt.pct(chg));
  const absent=(val===null||val===undefined);
  const vtxt=absent?'—':(VX.fmt.price(val)+((d&&d.unit)?' '+d.unit:''));
  /*  TIRET EXPLIQUÉ. `loadStrip` filtre les instruments absents avant de
      rendre ses tuiles ; `loadMarketGrid` rend les DOUZE de sa table quoi
      qu'il arrive. Mesure du 06/09/2026 sur 5003 : SMI, USD/CHF et ETH
      sortaient en « — / n/d » avec zéro attribut `title` — un tiret muet, que
      rien ne distingue d'un zéro, d'une panne ou d'un oubli. La cause est
      pourtant mesurable sans rien supposer : l'instrument n'est pas dans la
      charge du scan, et le scan dit qui l'a servie. On la nomme. */
  const cause=absent?(label+' n’est pas servi par le dernier scan'
    +((scan&&scan.source)?' (source : '+scan.source+')':'')
    +' — aucune valeur n’est estimée à la place.'):'';
  const dtxt2=absent?'non servi':dtxt;
  /* KPI moderne : prix + variation (flèche), sans mini-courbe (page plus épurée). */
  return `<div class="vx-card vx-card--compact vx-kpi vx-idx-tile" style="grid-column:span ${span||2}" aria-label="${esc(label)}"${absent?` data-absent="1" title="${esc(cause)}"`:''}>
    <span class="vx-kpi-label">${esc(label)}</span>
    <span class="vx-kpi-value">${vtxt}</span>
    <span class="vx-kpi-delta ${dcls}">${arrow?`<i class="vx-arw">${arrow}</i>`:''}${dtxt2}</span></div>`;
}
async function loadStrip(){
  let scan=null;
  try{scan=await VX.fetch('/scan',{ttl:120000});}catch(e){}
  const by=crossAsset(scan);
  if(by['VIX'])by['VIX'].deltaNeutral=true;
  const ROW1=['S&P 500','Nasdaq','Dow Jones','Russell 2000','VIX','Taux 10 ans'];
  const ROW2=['DXY','Pétrole','Or','Bitcoin'];
  const strip=$('vx-market-strip'),cross=$('vx-cross-strip');
  const known1=ROW1.filter(n=>by[n]&&by[n].last!=null);
  if(strip)strip.innerHTML=known1.length?known1.map(n=>kpiCell(n,by[n],scan,2)).join('')
    :'<div class="vx-card vx-col-12">'+VX.states.empty('Indices indisponibles — lancer un scan depuis Système.','<a class="vx-btn vx-btn-sm" href="/system?view=data">Système / Données</a>')+'</div>';
  if(cross)cross.innerHTML=ROW2.filter(n=>by[n]&&by[n].last!=null).map(n=>kpiCell(n,by[n],scan,3)).join('');
  if(scan&&scan.data_source==='demo')
    ($('vx-demo-banner')||{}).innerHTML='<div class="vx-demo-banner"><span class="vx-badge-demo">Démo</span> Données synthétiques clairement identifiées — jamais présentées comme réelles.</div>';
  return scan;
}

/* ── L'ESSENTIEL DU JOUR : grille marché complète en tête de Dashboard.
   12 instruments dans l'ordre canonique (indices US · SMI · devise · matières ·
   crypto). Alias de noms tolérés (le scan peut servir 'Bitcoin' ou 'BTC').
   Donnée absente → tuile 'n/d' honnête, jamais un chiffre inventé. ── */
const MARKET_GRID=[
  ['Dow Jones',['Dow Jones','Dow']],
  ['S&P 500',['S&P 500','SPX','S&P500']],
  ['Nasdaq',['Nasdaq','Nasdaq 100','NDX']],
  ['Russell 2000',['Russell 2000','Russell']],
  ['VIX',['VIX']],
  ['SMI',['SMI']],
  ['USD/CHF',['USD/CHF','USDCHF']],
  ['Or',['Or','Gold','XAU']],
  ['Pétrole',['Pétrole','WTI','Brent']],
  ['Silver',['Silver','Argent','XAG']],
  ['BTC',['Bitcoin','BTC']],
  ['ETH',['Ethereum','ETH']],
];
const GRID_NEUTRAL={'VIX':1,'USD/CHF':1};
function loadMarketGrid(scan){
  const host=$('vx-market-grid');if(!host)return;
  const by=crossAsset(scan||{});
  const cells=MARKET_GRID.map(([label,keys])=>{
    const key=keys.find(k=>by[k]&&by[k].last!=null);
    const d=key?Object.assign({},by[key]):{};
    if(GRID_NEUTRAL[label])d.deltaNeutral=true;
    return kpiCell(label,d,scan,2);
  }).join('');
  host.innerHTML=cells;
}

/* ── Brief Vertex (§21) : narratif à gauche, « ce qui compte » à droite ── */
async function loadBrief(){
  try{
    const b=await VX.fetch('/api/briefing/editorial',{ttl:60000});
    const daily=b.daily||{};
    const kindLabel={PRE_MARKET:'Pré-marché',INTRADAY:'Intraday',CLOSE:'Clôture',WEEKLY:'Hebdo'}[daily.kind]||'';
    const domSec=(daily.sections||[]).find(x=>x.label==='Actualité dominante');
    const ed=b.editorial||{};
    /* BRIEF PRO & BREF : une phrase-titre + « Essentiels du jour » toujours visibles,
       le reste (narratif complet, prixé, actualité) replié derrière « Lire la suite ». */
    const narr=String(ed.narrative||'').trim();
    const fd=narr.indexOf('. ');
    const lead=fd>0?narr.slice(0,fd+1):narr;
    const rest=fd>0?narr.slice(fd+2).trim():'';
    const leadHtml=lead?'<p class="vx-brief-lead">'+esc(lead)+'</p>':'';
    const essHtml=(b.lines&&b.lines.length)?'<div class="vx-brief-ess"><div class="vx-brief-ess-k">Essentiels de la journée</div>'
      +b.lines.slice(0,4).map(l=>'<div class="be"><span class="be-dot"></span><span>'+esc(l)+'</span></div>').join('')+'</div>':'';
    const detailHtml='<div id="vx-brief-clamp" data-clamped="1">'
      +(rest?'<p style="font-size:14.5px;line-height:1.8;color:var(--vx-text-secondary,#b7bcc4);margin:.2rem 0 .6rem">'+esc(rest)+'</p>':'')
      +(ed.prices_mainly?'<div class="vx-insight vx-mt1"><b>Ce que le marché prixe</b><div class="vx-mt1">'+esc(ed.prices_mainly)+'</div></div>':'')
      +((ed.calls_impact||ed.news_available===false)?'<div class="vx-flex vx-wrap vx-mt2" style="gap:.4rem">'
        +(ed.calls_impact?'<span class="vx-badge" style="color:var(--vx-option,#85609f)">Calls : '+esc(ed.calls_impact)+'</span>':'')
        +(ed.news_available===false?'<span class="vx-badge">Brief data-only</span>':'')+'</div>':'')
      +(domSec?`<div class="vx-insight vx-mt2"><b>Actualité dominante</b><div class="vx-mt1">${esc(domSec.text)}</div></div>`:'')
      +'</div>';
    ($('vx-brief-body')||{}).innerHTML=leadHtml+essHtml+detailHtml
      +'<div id="vx-brief-morewrap" style="text-align:center;margin-top:8px"><button class="vx-btn vx-btn-sm vx-btn-ghost" id="vx-brief-more">Lire la suite ↓</button></div>'
      +`<div class="vx-card-footer">
         ${VX.updateIndicator(b.as_of,(b.sources||[]).join(', '),b.demo?'fallback':'delayed')}
         <span class="vx-badge">${b.generator==='deterministic'?'Déterministe (moteurs)':'IA validé'}</span>
         ${kindLabel?`<span class="vx-badge" style="color:var(--vx-amber)">${kindLabel}</span>`:''}
         <button class="vx-btn vx-btn-sm vx-btn-ghost vx-right" data-scrollto="markets">Voir les preuves ↓</button></div>`;
    ($('vx-brief-meta')||{}).innerHTML=`<span class="vx-meta">${(daily.word_count||b.word_count)} mots · lecture 30 s</span>`;
    const cl=$('vx-brief-clamp'),moreBtn=$('vx-brief-more'),moreWrap=$('vx-brief-morewrap');
    if(cl&&moreBtn){
      if(cl.scrollHeight<60){if(moreWrap)moreWrap.style.display='none';cl.dataset.clamped='0';}
      moreBtn.addEventListener('click',function(){
        const c=cl.dataset.clamped==='1';cl.dataset.clamped=c?'0':'1';
        this.textContent=c?'Réduire ↑':'Lire la suite ↓';});
    }
    /* Carte latérale : posture du comité (chiffres réels) + risque + opportunité + changements */
    const side=$('vx-brief-side-body');
    if(side){
      let comite='';
      try{
        const cmd=await VX.fetch('/api/command',{ttl:60000});
        const cn=(cmd&&cmd.counts)||{};
        const chip=(label,v,col)=>v?`<span class="vx-badge" style="color:${col}">${v} ${label}</span>`:'';
        const row=chip('achat(s)',cn.ACHETER,'var(--vx-positive)')+chip('renforcer',cn.RENFORCER,'var(--vx-positive)')
          +chip('en attente',cn.ATTENDRE,'var(--vx-warning)')+chip('à éviter',cn['ÉVITER']||cn.EVITER,'var(--vx-negative)');
        if(row)comite=`<div class="vx-metric-k" style="margin-bottom:5px">Le comité aujourd’hui</div><div class="vx-flex vx-wrap" style="gap:.35rem;margin-bottom:10px">${row}</div>`;
      }catch(e){}
      const changed=(b.changed_since_yesterday||[]).map(c=>`<li>${esc(c)}</li>`).join('');
      const news=(b.what_changed_today||[]).map(x=>`<li>${esc(x)}</li>`).join('');
      const h=comite+(b.main_risk?`<div class="vx-insight" data-tone="risk"><b>Risque principal</b><div class="vx-mt1">${esc(b.main_risk)}</div></div>`:'')
        +(b.main_opportunity?`<div class="vx-insight vx-mt2"><b>Opportunité principale</b><div class="vx-mt1">${esc(b.main_opportunity)}</div></div>`:'')
        +(news?`<div class="vx-insight vx-mt2"><b>Ce qui a changé (sourcé)</b><ul class="vx-mt1" style="margin:0;padding-left:18px">${news}</ul></div>`:'')
        +(changed?`<div class="vx-insight vx-mt2"><b>Depuis hier (moteurs)</b><ul class="vx-mt1" style="margin:0;padding-left:18px">${changed}</ul></div>`:'');
      side.innerHTML=h||VX.states.empty('Aucun risque ni changement saillant remonté par les moteurs.');
    }
  }catch(e){($('vx-brief-body')||{}).innerHTML=VX.states.error('Brief indisponible ('+e.message+')');}
}

/* ── Régime : vocabulaire moteur → français CLAIR (aucun code à l'écran) ── */
const REG_FR={TREND_UP:['TENDANCE HAUSSIÈRE','le marché suit une direction montante — accompagner la tendance'],
 TREND_DOWN:['TENDANCE BAISSIÈRE','direction baissière — défense d’abord'],
 CHOP:['SANS DIRECTION','le marché oscille — jouer les excès, éviter de courir après'],
 MEAN_REVERSION:['RETOUR À LA MOYENNE','les excès se corrigent — replis achetables, extensions à alléger'],
 RISK_ON:['APPÉTIT POUR LE RISQUE','l’argent va vers les actifs risqués'],
 RISK_OFF:['AVERSION AU RISQUE','l’argent cherche la sécurité'],
 PANIC:['PANIQUE','stress extrême — préserver le capital avant tout'],
 EUPHORIA:['EUPHORIE','excès haussier — ne pas courir après le mouvement'],
 TRANSITION:['TRANSITION','changement de régime en cours — attendre la confirmation'],
 VOLATILITY_COMPRESSION:['VOLATILITÉ COMPRIMÉE','calme inhabituel — un grand mouvement se prépare souvent'],
 VOLATILITY_EXPANSION:['VOLATILITÉ EN EXPANSION','les mouvements s’élargissent — réduire la taille'],
 UNKNOWN:['INDÉTERMINÉ','données insuffisantes — prudence par défaut']};
const SETUP_FR={BALANCED:'équilibré',BREAKOUT_PULLBACK:'cassures & replis',DEFENSIVE:'défensif',
 MEAN_REVERSION:'retour à la moyenne',MOMENTUM:'momentum',QUALITY_DEFENSIVE:'qualité défensive',
 CAPITAL_PRESERVATION:'préservation du capital',TAKE_PROFITS:'prise de profits',BREAKOUT_WATCH:'surveiller les cassures'};
const regFr=(code)=>REG_FR[code]||[code||'—','—'];
/* ── Régime (§20) — S1, col-4 ── */
async function loadRegime(){
  try{
    const r=await VX.fetch('/api/market/regime',{ttl:120000});
    const adj=r.adjustments||{};
    //  `||0` transformait une confiance ABSENTE en « 0 % » affiche comme
    //  une mesure — la pire lecture possible : 0 % de confiance se lit
    //  « le moteur est sur qu'il ne sait pas », alors que la verite est
    //  « le moteur n'a rien rendu ». `null` traverse et la surface rend
    //  n/d.
    const conf=r.confidence!=null?Math.round(r.confidence*100):null;
    ($('vx-regime-body')||{}).innerHTML=
      `<div id="vx-regime-gauge" class="vx-mb2"></div>
      <div class="vx-kpi vx-mb3" style="text-align:center"><span class="vx-kpi-value" style="font-size:17px" data-regime="${r.regime}">${regFr(r.regime)[0]}</span>
       <span class="vx-kpi-delta vx-muted" style="white-space:normal;line-height:1.45">${regFr(r.regime)[1]}</span>
       <span class="vx-kpi-delta vx-muted">${(r.dimensions_used||[]).length} dimensions évaluées</span></div>
      <div class="vx-kv"><span class="k">Nouveau risque</span><span class="v ${adj.new_risk_allowed?'vx-pos':'vx-neg'}">${adj.new_risk_allowed?'autorisé':'BLOQUÉ'}</span></div>
      <div class="vx-kv"><span class="k">Priorité setups</span><span class="v">${SETUP_FR[adj.setup_priority]||VX.fmt.nd(adj.setup_priority)}</span></div>
      <div class="vx-kv"><span class="k">Confirmations exigées</span><span class="v">${VX.fmt.nd(adj.confirmation_required)}</span></div>
      <div class="vx-card-footer">${VX.updateIndicator(r.ts?r.ts*1000:(r.as_of||null),'Moteur de régimes','delayed')}
      <button class="vx-btn vx-btn-sm vx-btn-ghost vx-right" data-scrollto="pulse">Pouls ↓</button></div>`;
    if(window.VXCharts&&VXCharts.gauge){
      const CO=(window.VXCharts&&VXCharts.colors)||{};
      //  `conf` peut valoir null : sans ce cas, `null>=70` est faux, `null>=40`
      //  aussi, et l'absence se lisait « Signal faible — prudence accrue ».
      //  Un jugement rendu sur rien.
      const reading=conf==null?'Confiance non rendue par le moteur'
        :conf>=70?'Signal net — régime lisible'
        :conf>=40?'Signal modéré — confirmations utiles'
        :'Signal faible — prudence accrue';
      if(conf==null){($('vx-regime-gauge')||{}).innerHTML=
        VX.states.empty('Confiance non rendue');}
      else{VXCharts.gauge('vx-regime-gauge',{value:conf,min:0,max:100,unit:' %',label:'confiance',reading:reading,
        bands:[{to:40,color:CO.negative},{to:70,color:CO.warning},{to:100,color:CO.positive}]});}
    }
  }catch(e){($('vx-regime-body')||{}).innerHTML=VX.states.error('Régime indisponible');}
}

/* ── Drivers du régime : forces réelles (tendance, participation, volatilité,
   momentum, macro, leadership) + « Que faire maintenant ? ». Le badge « moteur »
   marque les dimensions réellement évaluées par le moteur de régimes. ── */
async function loadRegimeDrivers(){
  const host=$('vx-regime-drivers');if(!host)return;
  let s={},r={};
  try{s=await VX.fetch('/api/market/summary',{ttl:60000})||{};}catch(e){}
  try{r=await VX.fetch('/api/market/regime',{ttl:120000})||{};}catch(e){}
  const dims=r.dimensions_used||[];
  const reg=r.regime||'';
  const up=/TREND_UP|RISK_ON|EUPHORIA/.test(reg),dn=/TREND_DOWN|RISK_OFF|PANIC/.test(reg);
  const vix=s.vix;
  const bd=(s.breadth&&typeof s.breadth==='object')?s.breadth:{};
  const b50=(bd.above50!=null)?Number(bd.above50):(typeof s.breadth==='number'?Number(s.breadth):null);
  const b200=(bd.above200!=null)?Number(bd.above200):null;
  const roro=String(s.roro||'').toUpperCase();
  const sec=(s.best_sector&&s.best_sector.sector)||null;
  const mom=(b50!=null&&b200!=null)?(b50-b200):null;
  const rows=[
    {k:'Tendance',dim:'index_trend',txt:up?'haussière':dn?'baissière':'sans direction',tone:up?'pos':dn?'neg':'',pct:up?85:dn?18:50},
    {k:'Participation',dim:'breadth_pct',txt:b50==null?'n/d':Math.round(b50)+' % > MM50',tone:b50==null?'':(b50>=55?'pos':b50>=45?'':'neg'),pct:b50},
    {k:'Volatilité',dim:'vix',txt:vix==null?'n/d':((vix<15?'calme':vix<25?'normale':'tendue')+' · VIX '+VX.fmt.num(vix,1)),tone:vix==null?'':(vix<15?'pos':vix<25?'':'neg'),pct:vix==null?null:Math.max(6,Math.min(100,100-vix*2.6))},
    {k:'Momentum',dim:null,txt:mom==null?'n/d':((mom>=0?'en amélioration':'en dégradation')+' ('+(mom>=0?'+':'')+Math.round(mom)+' pts 50-200)'),tone:mom==null?'':(mom>=0?'pos':'neg'),pct:mom==null?null:Math.max(6,Math.min(100,50+mom))},
    {k:'Macro / risque',dim:null,txt:roro==='RISK-ON'?'appétit pour le risque':roro==='RISK-OFF'?'aversion au risque':roro==='NEUTRE'?'neutre':'n/d',tone:roro==='RISK-ON'?'pos':roro==='RISK-OFF'?'neg':'',pct:roro==='RISK-ON'?82:roro==='RISK-OFF'?18:50},
    {k:'Leadership',dim:'leadership',txt:sec?(sec+' mène'):'n/d',tone:sec?'pos':'',pct:sec?72:null},
  ];
  const barCol=(t)=>t==='pos'?'var(--vx-positive,#36c889)':t==='neg'?'var(--vx-negative,#ed655c)':'var(--vx-text-dim,#8f8a83)';
  host.innerHTML=rows.map(d=>{
    const used=d.dim&&dims.includes(d.dim);
    const w=(d.pct==null)?0:Math.round(d.pct);
    return `<div class="vx-flex" style="align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--vx-border-soft)">
      <span style="flex:0 0 128px;font-size:12.5px;color:var(--vx-text-secondary)">${d.k}${used?' <span class="vx-badge" style="font-size:9px;padding:0 4px" title="dimension évaluée par le moteur">moteur</span>':''}</span>
      <span style="flex:1;height:7px;border-radius:99px;background:var(--vx-surface-0,rgba(255,255,255,.06));overflow:hidden"><span style="display:block;height:100%;width:${w}%;background:${barCol(d.tone)};border-radius:99px"></span></span>
      <span class="vx-${d.tone||'muted'}" style="flex:0 0 auto;font-size:12px;min-width:154px;text-align:right">${esc(d.txt)}</span>
    </div>`;
  }).join('');
  const adj=r.adjustments||{};
  const todo=$('vx-regime-todo');
  if(todo){
    const ok=adj.new_risk_allowed;
    const setup=SETUP_FR[adj.setup_priority]||adj.setup_priority||'les meilleurs setups';
    const line=ok?('Nouveau risque autorisé — privilégier '+setup+', '+VX.fmt.nd(adj.confirmation_required)+' confirmation(s) exigée(s) avant d’entrer.')
                 :'Nouveau risque BLOQUÉ — défense d’abord : protéger le capital, alléger le risque, attendre la confirmation.';
    todo.innerHTML=`<div class="vx-insight" data-tone="${ok?'':'risk'}"><b>Que faire maintenant ?</b><div class="vx-mt1">${esc(line)}</div></div>`;
  }
}

/* ── MARCHÉS : graphique héros (héros 320) avec périodes 1M/3M/6M/Max ──
   Clôtures + MM20/50/200 RÉELLES du scan — jamais recalculées côté client. */
let MK_TF=(function(){try{return localStorage.getItem('vxDashMkTf')||'6m'}catch(e){return '6m'}})();
const MK_TFS=[['1m',21],['3m',63],['6m',126],['max',0]];
function tfControls(){
  return MK_TFS.map(([id])=>
    `<button class="vx-chip" data-mktf="${id}" aria-pressed="${id===MK_TF}">${id.toUpperCase()}</button>`).join('');
}
function loadMainChart(scan){
  scan=scan||{};const host=$('vx-market-chart');if(!host)return;
  /* Re-rendu (chips 1M/3M/6M/Max) : détruire l'ancien Chart avant d'écraser le
     canvas, sinon les instances s'accumulent (fuite mémoire). */
  const oldCv=host.querySelector('canvas');
  if(oldCv&&window.Chart&&Chart.getChart){const inst=Chart.getChart(oldCv);if(inst)inst.destroy();}
  const cc=(window.VXCharts&&VXCharts.colors)||{};
  /* Contexte = market ⊕ market_ctx (le statut horaire seul masquerait régime/verdict). */
  const m=Object.assign({},scan.market||{},scan.market_ctx||{});
  const det=(scan&&scan.detail)||{};
  const okSeries=(k)=>det[k]&&det[k].series&&Array.isArray(det[k].series.close)&&det[k].series.close.length>10;
  const hasSpy=okSeries('SPY');
  /* Priorité : SPY du scan (série + MM complètes) → INDICE S&P 500 (série 120
     séances + MM calculées serveur) → dernier recours, 1er titre du scan
     étiqueté proxy. Jamais un graphique vide si une vraie série existe. */
  const spx=((scan&&scan.indices)||[]).find(i=>i&&i.name==='S&P 500');
  const hasIdx=!hasSpy&&spx&&Array.isArray(spx.series)&&spx.series.length>10;
  const key=hasSpy?'SPY':(hasIdx?'S&P 500':Object.keys(det).find(okSeries));
  if(!key){host.innerHTML='<div class="vx-card">'+VX.states.empty('Série marché indisponible — lancer un scan depuis Système.','<a class="vx-btn vx-btn-sm" href="/system?view=data">Système / Données</a>')+'</div>';return;}
  const S=hasIdx?{close:spx.series,dates:spx.dates,ema20:spx.ema20,sma50:spx.sma50,sma200:spx.sma200}
               :(det[key].series||{});
  const n=(MK_TFS.find(x=>x[0]===MK_TF)||[])[1]||0;
  const cut=(arr)=>(Array.isArray(arr)?(n?arr.slice(-n):arr):null);
  const closes=cut(S.close)||[];
  const dates=cut(S.dates);
  /* Dates : l'indice sert 'YYYY-MM-DD' (→ MM-DD), le détail du scan sert déjà
     'MM-DD' — slice(5) aveugle viderait les étiquettes. */
  const labels=(dates&&dates.length===closes.length)
    ?dates.map(d=>{const x=String(d);return x.length>7?x.slice(5):x;})
    :closes.map((_,i)=>i-closes.length);
  const mm=(data,label,color,dash)=>{const dd=cut(data);
    return (dd&&dd.some(x=>x!=null))?[{label,data:dd,borderColor:color,borderWidth:1.2,borderDash:dash,pointRadius:0,tension:.2,fill:false}]:[];};
  VXCharts.card('vx-market-chart',{
    unit:'points d’indice',
    title:(hasSpy?'S&P 500 (SPY) — tendance & moyennes'
          :(hasIdx?'S&P 500 — tendance & moyennes'
                  :'Marché — série de référence · '+key+' (S&P 500 absent du scan)')),
    timeframe:closes.length+' séances',controlsHtml:tfControls(),
    question:'La tendance de fond reste-t-elle exploitable ?',
    conclusion:(spx&&spx.price!=null?('S&P 500 '+VX.fmt.price(spx.price)+' ('+(spx.change>=0?'+':'')+VX.fmt.num(spx.change,2)+' %) · '):'')
      +({TREND:'tendance intacte',NEUTRAL:'marché neutre',CHOP:'sans direction',DOWN:'tendance baissière'}[m.spy_regime]||('régime '+(m.spy_regime||'n/d')))+(m.verdict?' — '+m.verdict:''),
    height:H_HERO,source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
    legend:[{label:hasSpy?'SPY':key,color:cc.brand}]
      .concat((S.ema20&&S.ema20.some(x=>x!=null))?[{label:'MM20',color:cc.amber}]:[])
      .concat((S.sma50&&S.sma50.some(x=>x!=null))?[{label:'MM50',color:cc.beige}]:[])
      .concat((S.sma200&&S.sma200.some(x=>x!=null))?[{label:'MM200',color:cc.neutral}]:[]),
    explain:{shows:'Les clôtures de la référence marché et ses moyennes mobiles 20/50/200 calculées par le scan.',
      why:'La Stratégie Vertex n’attaque qu’en environnement porteur : le régime module seuils et tailles.',
      confirm:'Clôtures au-dessus des MM50/MM200 ascendantes avec breadth > 55 %.',
      invalidate:'Cassure des MM avec expansion de volatilité.'},
    render:(cv)=>{
      /* Plus-haut / plus-bas RÉELS de la fenêtre affichée (annotation de niveau) */
      const vals=closes.filter(x=>x!=null&&isFinite(x));
      const hi=vals.length?Math.max.apply(null,vals):null;
      const lo=vals.length?Math.min.apply(null,vals):null;
      return VXCharts.mount(cv,{type:'line',
      data:{labels,datasets:[
        {label:hasSpy?'SPY':key,data:closes,borderColor:cc.brand,borderWidth:1.9,pointRadius:0,tension:.22,fill:true,
         backgroundColor:(ctx)=>{const g=ctx.chart.ctx.createLinearGradient(0,0,0,ctx.chart.height||H_HERO);
           g.addColorStop(0,(cc.brand||'#c9cdd4')+'33');g.addColorStop(1,(cc.brand||'#c9cdd4')+'00');return g;}},
        ...mm(S.ema20,'MM20',cc.amber,[]),...mm(S.sma50,'MM50',cc.beige,[5,3]),...mm(S.sma200,'MM200',cc.neutral,[2,3])]},
      options:{scales:VXCharts.axes({yFmt:(v)=>VX.fmt.price(v)}),interaction:{mode:'index',intersect:false},
        plugins:{legend:{display:false}}},
      plugins:(hi!=null&&VXCharts.levelLines)?[VXCharts.levelLines([
        {value:hi,label:'plus haut',kind:'resistance'},
        {value:lo,label:'plus bas',kind:'support'}])]:[]});
    }});
  host.querySelectorAll('[data-mktf]').forEach(b=>b.addEventListener('click',()=>{
    MK_TF=b.dataset.mktf;try{localStorage.setItem('vxDashMkTf',MK_TF)}catch(e){}
    loadMainChart(scan);}));
}

/* ── « Ce qui a changé » : changes_since_prev du contexte marché (§ jamais
   inventé — produit par market_context sur DEUX sessions réelles). Mesuré au
   navigateur : cette carte restait un squelette perpétuel, personne ne la
   remplissait. Trois états honnêtes : pas de base · rien de notable · liste. ── */
async function loadDiff(scan){
  const host=$('vx-diff');if(!host)return;
  /* `scan.market_ctx` est le contexte BRUT du scan : il ne porte jamais de
     diff. Le propriétaire du « depuis la dernière session » est
     /api/market/context (moteur market_context + base persistée) — mesuré :
     la carte restait « pas de base » à vie en lisant le mauvais objet. */
  let ctx=null;
  try{ctx=await VX.fetch('/api/market/context',{ttl:120000});}catch(e){}
  if(!ctx){host.innerHTML=VX.states.error('Contexte marché indisponible.');return;}
  const ch=ctx.changes_since_prev;
  const pied=`<div class="vx-card-footer">${VX.updateIndicator(ctx.as_of||null,'market_context',ctx.demo?'demo':'delayed')}</div>`;
  if(!ctx.changes_base||!Array.isArray(ch)){
    host.innerHTML=VX.states.empty('Pas de base de comparaison — la première session pose la base, la suivante dira ce qui a changé.')+pied;
    return;}
  if(!ch.length){
    /* Un diff vide SUR UNE BASE est un résultat (état positif), pas une absence de donnée. */
    host.innerHTML='<div class="vx-insight vx-mt1">Aucun changement notable depuis la session précédente'+(ctx.prev_as_of?' ('+VX.esc(String(ctx.prev_as_of))+')':'')+'.</div>'+pied;
    return;}
  host.innerHTML='<ul class="vx-mt1" style="margin:0;padding-left:18px;line-height:1.9">'
    +ch.slice(0,8).map(c=>'<li>'+VX.esc(String(c))+'</li>').join('')+'</ul>'
    +(ctx.prev_as_of?`<div class="vx-meta vx-mt1">Comparé au contexte du ${VX.esc(String(ctx.prev_as_of))}</div>`:'')+pied;
}

/* ── MARCHÉS : indices comparés, rebasés à 0 % (héros 320, col-4) ── */
function loadCompare(scan){
  const host=$('vx-market-compare');if(!host)return;
  const cc=(window.VXCharts&&VXCharts.colors)||{};
  const by={};((scan&&scan.indices)||[]).forEach(i=>{if(i&&i.name)by[i.name]=i;});
  const wanted=['S&P 500','Nasdaq','Dow Jones','Russell 2000'];
  const sets=wanted.map(n=>({n,spark:(by[n]&&by[n].spark)||[]})).filter(x=>x.spark.length>5);
  if(!sets.length){host.innerHTML='<div class="vx-card">'+VX.states.empty('Séries indices indisponibles dans le dernier scan.')+'</div>';return;}
  const len0=Math.min(...sets.map(x=>x.spark.length));
  /* base de rebasage nulle/absente → série OMISE (jamais un 0 % fabriqué) */
  const usable=sets.filter(x=>{const b=x.spark[x.spark.length-len0];return b!=null&&b>0;});
  if(!usable.length){host.innerHTML='<div class="vx-card">'+VX.states.empty('Séries indices inexploitables (bases nulles).')+'</div>';return;}
  sets.length=0;usable.forEach(x=>sets.push(x));
  const len=len0;
  const labels=Array.from({length:len},(_,i)=>i-len);
  /* Performance finale rebasée → visible directement dans la légende */
  const finPct=(x)=>{const b=x.spark[x.spark.length-len];const v=x.spark[x.spark.length-1];
    return (b&&v!=null)?(v/b-1)*100:null;};
  VXCharts.card('vx-market-compare',{
    title:'Qui mène ?',unit:'%',timeframe:len+' points',
    question:'Large caps, tech ou small caps ?',
    conclusion:(function(){
      const ranked=sets.map(x=>({n:x.n,f:finPct(x)})).filter(x=>x.f!=null).sort((a,b)=>b.f-a.f);
      return ranked.length?(ranked[0].n+' mène ('+(ranked[0].f>=0?'+':'')+ranked[0].f.toFixed(1)+' %) · chaque indice rebasé à 0 %'):'Chaque indice rebasé à 0 %.';
    })(),
    height:H_HERO,source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
    legend:sets.map((x,i)=>{const f=finPct(x);
      return {label:x.n+(f!=null?' '+(f>=0?'+':'')+f.toFixed(1)+' %':''),color:((window.VXCharts&&VXCharts.colors.series)||[])[i%6]};}),
    explain:{shows:'Les séries d’indices du scan, rebasées à 0 % pour comparer la force relative.',
      why:'Le leadership (tech vs small caps) qualifie l’appétit pour le risque.',
      confirm:'Small caps et tech au-dessus des large caps — appétit confirmé.',
      invalidate:'Défensives seules en tête — régime prudent.'},
    render:(cv)=>VXCharts.multiLine(cv,labels,
      sets.map(x=>({label:x.n,data:x.spark.slice(-len).map(v=>x.spark[x.spark.length-len]?(v/x.spark[x.spark.length-len]-1)*100:0)})),
      {yFmt:(v)=>v.toFixed(1)+' %'})});
}

/* ── MARCHÉS : courbe des taux US (4 maturités réelles, jamais interpolées) ── */
function loadYield(scan){
  const el=$('vx-yield');if(!el||!window.VXCharts)return;
  const macro=(scan&&scan.macro)||[];const byId={};macro.forEach(m=>{byId[m.id]=m;});
  const mats=[['^IRX','3M'],['^FVX','5A'],['^TNX','10A'],['^TYX','30A']];
  const pts=mats.filter(m=>byId[m[0]]&&byId[m[0]].value!=null);
  if(pts.length<2){el.innerHTML='<div class="vx-card">'+VX.states.empty('Courbe des taux indisponible — maturités non fournies par le scan.')+'</div>';return;}
  const labels=pts.map(m=>m[1]);
  const cur=pts.map(m=>byId[m[0]].value);
  /* prev absent → null (point omis par Chart.js), jamais la valeur du jour
     déguisée en « séance précédente ». */
  const prev=pts.map(m=>byId[m[0]].prev!=null?byId[m[0]].prev:null);
  const t10=byId['^TNX'],t3=byId['^IRX'];
  const spread=(t10&&t3&&t10.value!=null&&t3.value!=null)?(t10.value-t3.value):null;
  const cc=VXCharts.colors;
  VXCharts.card('vx-yield',{
    title:'Courbe des taux US',unit:'%',timeframe:'clôture',
    question:'Normale ou inversée ?',
    conclusion:spread!=null?('Spread 10a-3m '+(spread>=0?'+':'')+spread.toFixed(2)+' pt — '+(spread<0?'INVERSÉE (signal de récession)':'pentue / normale')):'—',
    height:H_STD,source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
    limits:'4 maturités réelles (3M/5A/10A/30A) — non interpolées',
    legend:[{label:'Actuelle',color:cc.teal||cc.brand},{label:'Séance préc.',color:cc.neutral}],
    explain:{shows:'Le rendement du Trésor US par maturité (points réels du scan, non interpolés).',
      why:'Une courbe inversée (court > long) précède souvent les récessions et module l’appétit pour le risque.',
      confirm:'Repentification : le spread 10a-3m remonte durablement.',invalidate:'Inversion qui s’aggrave.'},
    render:(cv)=>VXCharts.multiLine(cv,labels,[
      {label:'Actuelle',data:cur,borderColor:cc.teal||cc.brand,borderWidth:2.2,pointRadius:3,pointBackgroundColor:cc.teal||cc.brand,fill:false},
      {label:'Séance préc.',data:prev,borderColor:cc.neutral,borderWidth:1.4,borderDash:[4,3],pointRadius:0,fill:false}
    ],{yFmt:(v)=>v+' %'})});
}

/* ── MARCHÉS : appétit pour le risque (roro + gap du moteur — réel) ── */
async function loadRoro(){
  const el=$('vx-roro-body');if(!el)return;
  let s=null;try{s=await VX.fetch('/api/market/summary',{ttl:60000});}catch(e){}
  if(!s||(!s.roro&&s.roro_gap==null)){el.innerHTML=VX.states.empty('Appétit pour le risque non calculé par le moteur.');return;}
  const gap=(typeof s.roro_gap==='number')?s.roro_gap:null,roro=s.roro||'—';
  const pos=gap!=null&&gap>=0,mag=gap==null?0:Math.min(100,Math.abs(gap)/25*100);
  const bar='<div style="position:relative;height:16px;background:var(--vx-surface-3);border-radius:6px;overflow:hidden;margin:10px 0 6px">'
    +'<div style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--vx-border-strong)"></div>'
    +(gap==null?'':'<div style="position:absolute;top:2px;bottom:2px;'+(pos?'left:50%':'right:50%')+';width:'+(mag/2).toFixed(0)+'%;background:'+(pos?'var(--vx-positive)':'var(--vx-negative)')+';border-radius:3px"></div>')+'</div>';
  el.innerHTML='<div style="font-size:24px;font-weight:700;color:'+(pos?'var(--vx-positive)':'var(--vx-negative)')+'">'+esc(roro)+'</div>'+bar
    +'<div class="vx-flex" style="justify-content:space-between"><span class="vx-meta">RISK-OFF</span><span class="vx-meta">écart '+(gap==null?'n/d':(gap>0?'+':'')+gap)+'</span><span class="vx-meta">RISK-ON</span></div>'
    +(s.vix_band?'<div class="vx-kv vx-mt3"><span class="k">Bande VIX</span><span class="v">'+esc(s.vix_band)+'</span></div>':'')
    +(s.regime?'<div class="vx-kv"><span class="k">Régime</span><span class="v">'+esc(s.regime)+'</span></div>':'')
    +'<div class="vx-card-footer"><span class="vx-meta">Écart risk-on/risk-off du moteur (positif = appétit). Aucune valeur inventée.</span></div>';
}

/* ── SECTEURS : quadrant force × momentum + rotation + heatmap (ex-Marchés) ── */
function loadSectorsBlock(scan){
  const sectors=(scan&&scan.sectors)||[];
  const mode=modeOf(scan);
  if(!sectors.length){
    ['vx-sectors-quadrant','vx-rotation','vx-sectors-heat'].forEach(id=>{
      const el=$(id);if(el)el.innerHTML='<div class="vx-card">'+VX.states.empty('Secteurs non calculés par le dernier scan.')+'</div>';});
    return;
  }
  /* Quadrant RRG-like : force relative (score) × momentum (variation du jour) */
  if(window.VXCharts&&sectors.length>=2){
    const cc2=VXCharts.colors;
    const maxN=Math.max.apply(null,sectors.map(x=>x.n||1));
    const pts=sectors.map(s=>({x:(s.avg_score!=null?s.avg_score:(s.score||50)),y:(s.avg_change!=null?s.avg_change:0),label:s.sector||'',n:(s.n||1)}));
    const quadCol=(x,y)=>x>=50?(y>=0?cc2.positive:cc2.warning):(y>=0?cc2.neutral:cc2.negative);
    VXCharts.card('vx-sectors-quadrant',{
      title:'Rotation — force relative × momentum',
      question:'Quels secteurs mènent, lesquels s’essoufflent ?',
      conclusion:'Haut-droit = Leaders · bas-gauche = Retardataires — cliquer un secteur',
      height:H_HERO,source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode,
      limits:'force = score moyen · momentum = variation du jour · taille de bulle = nombre de titres',
      explain:{shows:'Chaque secteur placé par sa force relative (score moyen) et son momentum (variation moyenne du jour).',
        why:'La stratégie surpondère la zone « Leading » (haut-droit) et se méfie du « Lagging » (bas-gauche).',
        confirm:'Un secteur qui migre vers le haut-droit sur plusieurs séances.',invalidate:'Bascule vers le bas-gauche.'},
      render:(cv)=>VXCharts.mount(cv,{type:'scatter',
        data:{datasets:[{data:pts,
          pointRadius:(ctx)=>ctx.raw?Math.max(6,Math.round(6+10*Math.sqrt((ctx.raw.n||1)/maxN))):7,
          pointHoverRadius:(ctx)=>ctx.raw?Math.max(10,Math.round(9+11*Math.sqrt((ctx.raw.n||1)/maxN))):11,
          pointBackgroundColor:(ctx)=>ctx.raw?quadCol(ctx.raw.x,ctx.raw.y):cc2.neutral,
          pointBorderColor:'rgba(255,255,255,.22)',pointBorderWidth:1}]},
        options:{scales:{
          x:{title:{display:true,text:'Force relative (score moyen) →'},min:0,max:100,grid:{color:'rgba(255,255,255,.06)'}},
          y:{title:{display:true,text:'Momentum (var. moy. %) ↑'},grid:{color:'rgba(255,255,255,.06)'}}},
          plugins:{tooltip:{callbacks:{label:(ctx)=>ctx.raw.label+' · force '+VX.fmt.num(ctx.raw.x,0)+' · momentum '+VX.fmt.pct(ctx.raw.y,1)+' · '+(ctx.raw.n||1)+' titres'}}},
          onClick:(evt,els,chart)=>{const p=chart.getElementsAtEventForMode(evt,'nearest',{intersect:true},true);
            if(p.length){const d=chart.data.datasets[0].data[p[0].index];VX.context.save();location.href='/opportunities?view=stocks&sector='+encodeURIComponent(d.label);}}},
        plugins:[{id:'vxQuad',afterDatasetsDraw(chart){const a=chart.chartArea,sx=chart.scales.x,sy=chart.scales.y;const xc=sx.getPixelForValue(50),y0=sy.getPixelForValue(0);const g=chart.ctx;
          g.save();g.strokeStyle='rgba(255,255,255,.12)';g.setLineDash([4,4]);g.beginPath();
          if(xc>a.left&&xc<a.right){g.moveTo(xc,a.top);g.lineTo(xc,a.bottom);}
          if(y0>a.top&&y0<a.bottom){g.moveTo(a.left,y0);g.lineTo(a.right,y0);}g.stroke();g.setLineDash([]);
          g.font='10px sans-serif';g.fillStyle='rgba(255,255,255,.32)';
          g.fillText('LEADING',a.right-58,a.top+14);g.fillText('IMPROVING',a.left+6,a.top+14);
          g.fillText('WEAKENING',a.right-66,a.bottom-8);g.fillText('LAGGING',a.left+6,a.bottom-8);
          g.fillStyle='#bab4ac';g.font='9px sans-serif';
          chart.data.datasets[0].data.forEach((d,i)=>{const m2=chart.getDatasetMeta(0).data[i];if(m2)g.fillText(String(d.label).slice(0,11),m2.x+9,m2.y+3);});
          g.restore();}}]})});
  }
  /* Rotation en barres (score moyen par secteur, clic = opportunités du secteur) */
  VXCharts.sectorCard('vx-rotation',{
    title:'Rotation sectorielle',unit:'%',question:'Où va le capital en ce moment ?',
    conclusion:'Leader : '+(sectors[0].sector||'n/d'),
    labels:sectors.slice(0,9).map(s=>s.sector),
    values:sectors.slice(0,9).map(s=>s.avg_score??s.score??0),height:H_HERO,
    source:scan.source,timestamp:scan.scan_ts||scan.updated,mode,
    onSector:(name)=>{VX.context.save();location.href='/opportunities?view=stocks&sector='+encodeURIComponent(name);},
    explain:{shows:'Score moyen par secteur (moteur de rotation).',
      why:'La stratégie suit les secteurs qui attirent le capital.',
      confirm:'Leadership stable sur plusieurs séances.',invalidate:'Rotation défensive brutale.'}});
  /* Heatmap : variation, score, RVOL, titres — lignes cliquables */
  VXCharts.heatmapCard('vx-sectors-heat',{
    title:'Performance et momentum par secteur',unit:'%',
    question:'Quels secteurs attirent le capital aujourd’hui ?',
    conclusion:'Vert = flux entrant, rouge = flux sortant (variation moyenne du jour).',
    columns:['Var. moyenne %','Score','Vol. relatif','Titres'],
    rows:sectors.map(sec=>({label:esc(sec.sector||'n/d'),cells:[
      {value:sec.avg_change??null,onclick:'/opportunities?view=stocks&sector='+encodeURIComponent(sec.sector||'')},
      {value:sec.avg_score??null,label:VX.fmt.nd(sec.avg_score)},
      {value:null,label:VX.fmt.nd(sec.avg_rvol)},
      {value:null,label:String(sec.n??'—')}]})),
    min:-3,max:3,fmt:(v)=>v===null?'—':VX.fmt.pct(v),
    source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode,
    limits:'univers = leaders scannés'});
  /* Treemap : poids (nb de titres) x performance (couleur) par secteur */
  const treeEl=$('vx-sectors-tree');
  if(treeEl&&window.VXCharts&&VXCharts.treemap){
    const cc3=VXCharts.colors;
    const col=(ch)=>ch==null?cc3.neutral:(ch>=0.3?cc3.positive:ch<=-0.3?cc3.negative:cc3.warning);
    const w=(treeEl.clientWidth)||900;
    VXCharts.treemap(treeEl,{width:w,height:300,unit:'titres par secteur',
      question:'Où le capital scanné se concentre-t-il, et quels secteurs montent ?',
      source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:mode,
      limits:'aire = nombre de titres scannés · couleur = variation moyenne',
      items:sectors.map(x=>({label:x.sector||'n/d',value:(x.n||x.avg_score||1),
        sub:(x.avg_change!=null?((x.avg_change>=0?'+':'')+Number(x.avg_change).toFixed(1)+'%'):''),
        color:col(x.avg_change)})),
      fmt:(v)=>v+' titres'});
  }else if(treeEl){treeEl.innerHTML=VX.states.empty('Poids sectoriels non calculés.');}
}

/* ── POULS : jauges radiales + posture 3 états + rail VIX calme↔stress ── */
async function loadPulse(scan){
  scan=scan||{};
  let sum={};try{sum=await VX.fetch('/api/market/summary',{ttl:60000})||{};}catch(e){}
  const G=window.VXCharts&&VXCharts.gauge;const CO=(window.VXCharts&&VXCharts.colors)||{};
  const mode=modeOf(scan);
  /* VIX — jauge + rail calme↔stress (ex-vue Volatilité de Marchés) */
  let vix=(sum.vix!=null&&!isNaN(sum.vix))?Number(sum.vix):null;
  if(vix==null){const vi=(scan.indices||[]).find(i=>i&&i.name==='VIX');if(vi&&vi.price!=null)vix=Number(vi.price);}
  if(G&&vix!=null){
    ($('vx-gauge-vix')||{}).innerHTML='<div id="vx-gauge-vix-g"></div><div id="vx-gauge-vix-rail"></div>';
    VXCharts.gauge('vx-gauge-vix-g',{value:vix,min:0,max:50,unit:'',label:'VIX',
      reading:vix<15?'Calme — primes bon marché':vix<25?'Normal':'Tendu — prudence',
      bands:[{to:15,color:CO.positive},{to:25,color:CO.warning},{to:50,color:CO.negative}]});
    ($('vx-gauge-vix-rail')||{}).innerHTML=
      `<div class="vx-rail vx-rail--stress vx-mt2" style="--vx-rail-pos:${Math.max(0,Math.min(100,(vix-10)/30*100)).toFixed(0)}%"><span class="vx-rail-mark"></span></div>`
      +`<div class="vx-rail-scale"><span>10</span><span>25</span><span>40+</span></div>`;
  }
  else ($('vx-gauge-vix')||{}).innerHTML=VX.states.empty('VIX non calculé.');
  /* Breadth — participation */
  let br=null;const sb=sum.breadth;
  if(sb!=null&&typeof sb==='object')br=(sb.above50!=null)?Number(sb.above50):(sb.above200!=null?Number(sb.above200):null);
  else if(sb!=null&&!isNaN(sb))br=Number(sb);
  if(G&&br!=null){VXCharts.gauge('vx-gauge-breadth',{value:br,min:0,max:100,unit:' %',label:'Participation',
    reading:br>=55?'Hausse partagée — saine':'Étroite — portée par peu de titres',
    bands:[{to:40,color:CO.negative},{to:55,color:CO.warning},{to:100,color:CO.positive}]});}
  else ($('vx-gauge-breadth')||{}).innerHTML=VX.states.empty('Breadth non calculée.');
  /* Régime — confiance + POSTURE 3 ÉTATS (lecture moteur, jamais un % inventé) */
  try{
    const r=await VX.fetch('/api/market/regime',{ttl:120000});
    //  `||0` transformait une confiance ABSENTE en « 0 % » affiche comme
    //  une mesure — la pire lecture possible : 0 % de confiance se lit
    //  « le moteur est sur qu'il ne sait pas », alors que la verite est
    //  « le moteur n'a rien rendu ». `null` traverse et la surface rend
    //  n/d.
    const conf=r.confidence!=null?Math.round(r.confidence*100):null;
    const allowed=r.adjustments&&r.adjustments.new_risk_allowed;
    if(G&&conf!=null){VXCharts.gauge('vx-gauge-trend',{value:conf,min:0,max:100,unit:' %',label:'Régime',
      reading:regFr(r.regime)[0]+' · '+(allowed?'risque autorisé':'risque bloqué'),
      bands:[{to:40,color:CO.negative},{to:70,color:CO.warning},{to:100,color:CO.positive}]});}
    /* Posture = lecture DIRECTE du moteur : risque bloqué → Défense ;
       autorisé + confiance ≥ 55 → Attaque ; autorisé sinon → Neutre. */
    //  `conf==null` tombe en Neutre, pas en Attaque : une posture offensive
    //  ne se prend pas sur une confiance qu'on n'a pas.
    const st=!allowed?'def':(conf!=null&&conf>=55?'att':'neu');
    ($('vx-regime-rail')||{}).innerHTML=
      '<div class="vx-stat-xl-label">Lecture moteur</div>'
      +`<div class="vx-posture" role="img" aria-label="Posture ${st==='def'?'défense':st==='att'?'attaque':'neutre'}">
        <span ${st==='def'?'data-on="def"':''}>Défense</span>
        <span ${st==='neu'?'data-on="neu"':''}>Neutre</span>
        <span ${st==='att'?'data-on="att"':''}>Attaque</span></div>`
      +'<div class="vx-meta vx-mt3">Régime <b>'+esc(regFr(r.regime)[0])+'</b> · confiance '
      +(conf==null?'n/d':conf+' %')+' · '
      +(allowed?'<span class="vx-pos">nouveau risque autorisé</span>':'<span class="vx-neg">nouveau risque BLOQUÉ</span>')+'</div>'
      +'<div class="vx-card-footer">'+VX.updateIndicator(r.ts?r.ts*1000:(r.as_of||null),'Moteur de régimes','delayed')+'</div>';
  }catch(e){
    if($('vx-gauge-trend'))($('vx-gauge-trend')||{}).innerHTML=VX.states.empty('Régime non calculé.');
    if($('vx-regime-rail'))($('vx-regime-rail')||{}).innerHTML=VX.states.error('Positionnement indisponible');
  }
  ($('vx-pulse-meta')||{}).innerHTML=VX.updateIndicator(scan.scan_ts||scan.updated,scan.source||'scan',mode);
  loadBreadthBlock(scan,sum);
}

/* ── POULS : internals de breadth + anneaux composites ── */
function loadBreadthBlock(scan,sum){
  scan=scan||{};sum=sum||{};
  const mode=modeOf(scan);
  const m=Object.assign({},scan.market||{},scan.market_ctx||{});
  const bdRaw=(sum.breadth&&typeof sum.breadth==='object')?sum.breadth
    :((m.breadth&&typeof m.breadth==='object')?m.breadth:null);
  const el=$('vx-breadth-internals');
  if(el){
    if(bdRaw&&(bdRaw.adv!=null||bdRaw.nh!=null||bdRaw.above200!=null||bdRaw.above50!=null)){
      const mbar=(k,v)=>{const tone=v==null?'':(v>=55?'pos':(v<40?'neg':'warn'));
        return `<div class="vx-metric" data-tone="${tone}"><span class="vx-metric-k">${k}</span>`
          +`<span class="vx-metric-v">${v==null?'—':Math.round(v)}${v==null?'':`<span class="vx-metric-u">%</span>`}</span>`
          +`<div class="vx-metric-bar"><i style="width:${v==null?0:Math.max(3,Math.min(100,v))}%"></i><b style="left:55%"></b></div></div>`;};
      const dbar=(la,a,lb,bv)=>{const tot=(a||0)+(bv||0)||1;const pa=Math.round((a||0)/tot*100);
        return `<div class="vx-mt3"><div style="display:flex;justify-content:space-between;font:600 11px/1 var(--vx-font);margin-bottom:5px">`
          +`<span style="color:var(--vx-positive)">${la} · ${a==null?'—':a}</span>`
          +`<span style="color:var(--vx-negative)">${bv==null?'—':bv} · ${lb}</span></div>`
          +`<div style="display:flex;height:9px;border-radius:99px;overflow:hidden;background:var(--vx-surface-0)">`
          +`<i style="width:${pa}%;background:var(--vx-positive)"></i><i style="flex:1;background:var(--vx-negative)"></i></div></div>`;};
      let h='<div class="vx-metricgrid" style="grid-template-columns:1fr 1fr">'+mbar('&gt; moyenne 50 séances',bdRaw.above50)+mbar('&gt; moyenne 200 séances',bdRaw.above200)+'</div>';
      if(bdRaw.adv!=null||bdRaw.dec!=null)h+=dbar('Avancées',bdRaw.adv,'Déclins',bdRaw.dec);
      if(bdRaw.nh!=null||bdRaw.nl!=null)h+=dbar('Nouveaux hauts',bdRaw.nh,'Nouveaux bas',bdRaw.nl);
      /* Température de l'univers : RSI moyen + parts en surachat / survente (réel) */
      const inter=(scan&&scan.internals)||{};
      const tchips=[];
      if(inter.avg_rsi!=null)tchips.push(`<span class="vx-badge">RSI moyen ${Math.round(inter.avg_rsi)}</span>`);
      if(inter.pct_ob!=null)tchips.push(`<span class="vx-badge" style="color:var(--vx-warning)">${Math.round(inter.pct_ob)} % en surachat</span>`);
      if(inter.pct_os!=null)tchips.push(`<span class="vx-badge" style="color:var(--vx-positive)">${Math.round(inter.pct_os)} % en survente</span>`);
      if(tchips.length)h+=`<div class="vx-flex vx-wrap vx-mt3" style="gap:.35rem">${tchips.join('')}</div>`;
      el.innerHTML=h+'<div class="vx-card-footer">'+VX.updateIndicator(scan.scan_ts||scan.updated,scan.source||'scan',mode)
        +'<span class="vx-meta">participation mesurée sur les leaders scannés (univers partiel)</span></div>';
    }else el.innerHTML=VX.states.empty('Breadth non calculée par le dernier scan.');
  }
  /* Anneaux : > MM50 / > MM200 / avancées — composite visuel */
  const host=$('vx-breadth-rings');
  if(host){
    const CO=(window.VXCharts&&VXCharts.colors)||{};
    if(bdRaw&&window.VXCharts&&VXCharts.rings){
      const advPct=(bdRaw.adv!=null&&bdRaw.dec!=null&&(bdRaw.adv+bdRaw.dec)>0)?Math.round(bdRaw.adv/(bdRaw.adv+bdRaw.dec)*100):null;
      const items=[];
      if(bdRaw.above50!=null)items.push({label:'Titres > MM50',value:Math.round(bdRaw.above50),color:CO.brand});
      if(bdRaw.above200!=null)items.push({label:'Titres > MM200',value:Math.round(bdRaw.above200),color:CO.cyan});
      if(advPct!=null)items.push({label:'Avancées / total',value:advPct,color:CO.positive});
      const center=(bdRaw.above50!=null)?Math.round(bdRaw.above50):'—';
      if(items.length){VXCharts.rings('vx-breadth-rings',{items,size:180,centerValue:center,centerLabel:'participation',ariaLabel:'Composite de participation'});}
      else host.innerHTML=VX.states.empty('Composite non calculable sur ce scan.');
    }else host.innerHTML=VX.states.empty('Composite non calculable sur ce scan.');
  }
}

/* ── POULS : tendance de participation + distribution des scores + santé ── */
function loadPulseExtra(scan){
  const inter=(scan&&scan.internals)||{};
  const mode=modeOf(scan);
  /* Tendance de participation (historique réel, 1 point/scan/jour) */
  const H=(inter.history)||[];
  const tEl=$('vx-breadth-trend');
  if(tEl){
    if(H.length>2&&window.VXCharts&&VXCharts.card&&VXCharts.multiLine){
      VXCharts.card('vx-breadth-trend',{title:'Tendance de participation',unit:'% de titres',
        question:'La participation s\u2019améliore-t-elle ou se dégrade-t-elle ?',
        conclusion:(H[H.length-1].a50>=H[0].a50?'En amélioration':'En dégradation')+' sur '+H.length+' séances',
        height:H_STD,source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode,
        limits:'historique de l\u2019univers scanné — se construit à chaque scan quotidien',
        explain:{shows:'L\u2019évolution jour après jour de la part des titres au-dessus de leurs moyennes et du score de santé.',
          why:'Une hausse d\u2019indice avec participation en baisse est fragile — la divergence prévient avant le prix.',
          confirm:'Participation et santé qui montent ensemble.',invalidate:'Divergence indices en hausse / participation en baisse.'},
        render:(cv)=>VXCharts.multiLine(cv,H.map(x=>x.d),[
          {label:'> moy. 50 j %',data:H.map(x=>x.a50)},
          {label:'> moy. 200 j %',data:H.map(x=>x.a200)},
          {label:'Santé',data:H.map(x=>x.health)}],{yFmt:(v)=>Math.round(v)+' %'})});
    }else tEl.innerHTML='<div class="vx-card">'+VX.states.empty('L\u2019historique de participation se construit à chaque scan quotidien ('+H.length+' point(s) pour l\u2019instant).')+'</div>';
  }
  /* Distribution des scores (10 tranches, réel) */
  const dEl=$('vx-score-dist');
  if(dEl){
    const dist=inter.dist||[];
    /* Score moyen approché depuis la distribution réelle (milieux de tranches) */
    const totN=dist.reduce((a,b)=>a+(b||0),0);
    const avgScore=totN?Math.round(dist.reduce((a,b,i)=>a+(b||0)*(i*10+5),0)/totN):null;
    if(dist.length&&dist.some(v=>v>0)){
      const maxN=Math.max(1,...dist);
      dEl.innerHTML='<div style="display:flex;gap:4px;align-items:flex-end;padding:8px 2px">'+dist.map((n,i)=>{
        const hh=Math.round(n/maxN*100);
        const col=i>=7?'var(--vx-positive)':i<=2?'var(--vx-negative)':'var(--vx-warning)';
        return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:3px" role="img" aria-label="score ${i*10}-${i*10+10} : ${n} titres" title="${n} titre(s) entre ${i*10} et ${i*10+10}">
          <span style="font-size:9.5px;color:var(--vx-text-dim)">${n||''}</span>
          <span style="width:100%;height:120px;display:flex;align-items:flex-end"><span style="width:100%;height:${hh}%;background:${col};border-radius:3px 3px 0 0;min-height:2px;opacity:.85"></span></span>
          <span style="font-size:9px;color:var(--vx-text-muted);font-variant-numeric:tabular-nums">${i*10}</span></div>`;
      }).join('')+'</div>'
      +(avgScore!=null?`<div class="vx-meta" style="text-align:center;margin-top:4px">score moyen de l’univers : <b>${avgScore}</b> / 100 · ${totN} titres</div>`:'');
    }else dEl.innerHTML=VX.states.empty('Distribution non calculée par le dernier scan.');
  }
  /* Santé : contributions pondérées (waterfall réel du moteur) */
  const wEl=$('vx-health-wf');
  if(wEl){
    if(window.VXCharts&&VXCharts.waterfall&&inter.health!=null&&inter.pct_a50!=null){
      VXCharts.waterfall('vx-health-wf',{ariaLabel:'Composition de la santé du marché',unit:'points de santé (0-100)',
        question:'Qu’est-ce qui compose la santé du marché aujourd’hui ?',
        source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:mode,
        limits:'contributions pondérées des internes du marché',
        items:[
          {label:'> moy. 50 j',value:0.30*(inter.pct_a50||0)},
          {label:'> moy. 200 j',value:0.25*(inter.pct_a200||0)},
          {label:'Participation',value:0.25*(inter.breadth!=null?inter.breadth:0)},
          {label:'Avancées/Déclins',value:0.20*(inter.advpct||0)},
          {label:'Santé',value:inter.health,isTotal:true}],
        fmt:(v)=>Math.round(v)});
    }else wEl.innerHTML=VX.states.empty('Santé non calculée par le dernier scan.');
  }
}

/* ── MOUVEMENTS : top / flop en tuiles avec sparklines réelles ── */
function sparkTile(closes,up){
  const v=(closes||[]).filter(x=>x!=null&&isFinite(x)).slice(-40);
  if(v.length<8)return '';
  const w=100,h=22,mn=Math.min.apply(null,v),mx=Math.max.apply(null,v),rng=(mx-mn)||1;
  const pts=v.map((x,i)=>(i/(v.length-1)*w).toFixed(1)+','+(h-1-((x-mn)/rng)*(h-2)).toFixed(1)).join(' ');
  const col=up?'var(--vx-positive)':'var(--vx-negative)';
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" width="100%" height="22" style="display:block;margin-top:7px;opacity:.9" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}
function moversHtml(rows,dir,detail){
  const signed=rows.filter(r=>r.change!==null&&r.change!==undefined&&(dir==='top'?r.change>0:r.change<0));
  const sorted=signed.slice().sort((a,b)=>dir==='top'?(b.change-a.change):(a.change-b.change)).slice(0,6);
  if(!sorted.length)return VX.states.empty(dir==='top'?'Aucune hausse dans le dernier scan.':'Aucune baisse dans le dernier scan.');
  return '<div class="vx-movergrid">'+sorted.map(function(r){
    const det2=detail&&detail[r.symbol];
    const ser=det2&&det2.series;
    const p52=det2&&det2.pos52!=null&&isFinite(det2.pos52)?Math.max(0,Math.min(100,det2.pos52)):null;
    return `<button class="vx-mover" data-open-analysis="${esc(r.symbol)}" aria-label="${esc(r.symbol)} ${VX.fmt.pct(r.change,1)}">
      <div class="vx-flex" style="justify-content:space-between;gap:6px"><span class="mv-sym">${esc(r.symbol)}</span>
        ${r.score!==null&&r.score!==undefined?`<span class="vx-badge" title="Score Vertex">${VX.fmt.num(r.score,0)}</span>`:''}</div>
      <div class="mv-chg ${r.change>0?'vx-pos':'vx-neg'}">${VX.fmt.pct(r.change,1)}</div>
      <div class="mv-sub">${esc(r.sector||'—')}${r.price!==null&&r.price!==undefined?' · '+VX.fmt.price(r.price):''}${r.rvol!=null&&isFinite(r.rvol)?` · vol ×${VX.fmt.num(r.rvol,1)}`:''}</div>
      ${p52!=null?`<div class="vx-flex" style="gap:6px;align-items:center;margin-top:7px"><span class="vx-meta" style="flex:0 0 auto;font-size:9.5px">52 sem.</span><span style="flex:1;height:4px;border-radius:99px;background:var(--vx-surface-0);position:relative"><i style="position:absolute;left:${p52}%;top:-2px;width:8px;height:8px;margin-left:-4px;border-radius:99px;background:var(--vx-beige,#c0b79f)"></i></span></div>`:''}
    </button>`;}).join('')+'</div>';
}
function loadTopFlop(scan){
  const rows=(scan&&scan.rows)||[];
  const t=$('vx-top10'),f=$('vx-flop10');
  /* Résumé de séance : combien montent, combien baissent (barre divergente) */
  const sm=$('vx-move-summary');
  if(sm){
    const up=rows.filter(r=>r.change>0).length,dn=rows.filter(r=>r.change<0).length;
    const tot=up+dn;
    if(tot){
      const pu=Math.round(up/tot*100);
      sm.innerHTML=`<div class="vx-card vx-card--compact" role="img" aria-label="${up} hausses contre ${dn} baisses">
        <div class="vx-flex" style="justify-content:space-between;font:700 12px/1 var(--vx-font);margin-bottom:6px">
          <span style="color:var(--vx-positive)">▲ ${up} en hausse (${pu} %)</span>
          <span class="vx-meta">séance de l\u2019univers scanné</span>
          <span style="color:var(--vx-negative)">${dn} en baisse (${100-pu} %) ▼</span></div>
        <div style="display:flex;height:10px;border-radius:99px;overflow:hidden;background:var(--vx-surface-0)">
          <i style="width:${pu}%;background:var(--vx-positive)"></i><i style="flex:1;background:var(--vx-negative)"></i></div></div>`;
    }else sm.innerHTML='';
  }
  const foot=`<div class="vx-card-footer">${VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))} · ${rows.length} titres scannés</div>`;
  if(t)t.innerHTML=moversHtml(rows,'top',scan&&scan.detail)+foot;
  if(f)f.innerHTML=moversHtml(rows,'flop',scan&&scan.detail)+foot;
}

/* ── OPPORTUNITÉS : recommandations + entonnoir + posture ── */
async function loadOpportunities(){
  try{
    const c=await VX.fetch('/api/command',{ttl:60000});
    //  L'horodatage de la CHARGE. `VX.fetch` sert un cache de 60 s : dater
    //  la carte de `Date.now()` annoncait « maintenant » sur une reponse
    //  pouvant avoir une minute, et le re-rendu la rajeunissait sans fin.
    /*  Mesure du 06/09/2026 sur 5003 : `/api/command` ne sert NI `as_of`,
        NI `ts`, NI `updated` — `cTs` valait donc toujours `null` et la carte
        « Posture du comité » rendait « Âge inconnu · comité Différé », un mode
        affirmé sur une charge dont l'âge n'était pas mesuré.
        Repli MESURÉ, pas supposé : `command.py` ne lit que `scan_state`, donc
        cette charge a exactement l'âge du scan, que le serveur pose dans
        `[data-scan-ts]` à la construction de la page. Le pied nomme cette
        provenance au lieu de la faire passer pour l'heure de l'endpoint. */
    const hdr=document.querySelector('[data-scan-ts]');
    const tsScan=hdr?hdr.getAttribute('data-scan-ts'):null;
    const cTs=(c&&(c.as_of||c.ts||c.updated))||tsScan||null;
    const cSrc=(c&&(c.as_of||c.ts||c.updated))?'comité':(tsScan?'comité — daté du scan qui l’a produit':'comité');
    const stocks=(c.top_stocks||[]).slice(0,6);
    ($('vx-opp-stocks')||{}).innerHTML=stocks.length?'<div class="vx-movergrid" style="grid-template-columns:repeat(auto-fill,minmax(250px,1fr))">'+stocks.map(s=>{
      const vx=s.vertex||{};
      const chips=[];
      if(vx.p_win!=null)chips.push(`<span class="vx-badge" style="color:var(--vx-positive)" title="probabilité que le trade soit gagnant (moteur Monte-Carlo)">proba. gain ${Math.round(vx.p_win*100)} %</span>`);
      if(vx.edge!=null)chips.push(`<span class="vx-badge" title="avantage statistique du dossier (0-100)">edge ${Math.round(vx.edge)}</span>`);
      if(s.rr!=null)chips.push(`<span class="vx-badge" title="rapport gain potentiel / risque">gain/risque ${VX.fmt.num(s.rr,1)}×</span>`);
      if(s.conviction!=null)chips.push(`<span class="vx-badge">conviction ${VX.fmt.num(s.conviction,0)}/100</span>`);
      return `
      <div class="vx-mover" data-open-analysis="${esc(s.symbol)}" role="button" tabindex="0" aria-label="Ouvrir ${esc(s.symbol)}" style="border-left:3px solid ${s.verdict==='ACHETER'||s.verdict==='RENFORCER'?'var(--vx-positive)':'var(--vx-warning)'}">
        <div class="vx-flex" style="justify-content:space-between;gap:6px"><span class="mv-sym">${esc(s.symbol)}</span>
          <span class="vx-badge vx-badge-decision" data-decision="${esc(s.verdict||'')}">${esc(s.verdict||'')}</span></div>
        <div class="mv-chg" style="font-size:15px;color:var(--vx-text-primary)">${s.price!=null?VX.fmt.price(s.price):'—'}</div>
        <div class="vx-flex vx-wrap" style="gap:.3rem;margin:4px 0">${chips.join('')}</div>
        ${s.note?`<div class="mv-sub" style="white-space:normal;line-height:1.45;max-height:6.2em;overflow:hidden"><b style="color:var(--vx-text-secondary)">Pourquoi :</b> ${esc(s.note)}</div>`:''}
        <div class="vx-flex" style="gap:.4rem;margin-top:8px;align-items:center"><button class="vx-btn vx-btn-sm vx-btn-ghost" data-inspect="${esc(s.symbol)}" title="Aperçu rapide">Aperçu</button>
          <span class="mv-sub" style="color:var(--vx-brand);white-space:nowrap">Dossier →</span></div>
      </div>`;}).join('')+'</div>':VX.states.empty('Aucune opportunité action retenue par le comité.');
    /* Comparatif du comité : proba de gain + conviction par titre, en barres HTML
       (taille déterministe — remplace l'ancien graphique R:R illisible). */
    const rrHost=$('vx-opp-rr');
    if(rrHost){
      const comp=stocks.filter(x=>(x.vertex&&x.vertex.p_win!=null)||x.conviction!=null);
      if(comp.length){
        const row=(sym,label,v,col)=>`<div class="vx-flex" style="gap:8px;align-items:center;padding:2px 0">
          <span class="vx-mono" style="flex:0 0 46px;font-weight:700;font-size:11.5px">${sym}</span>
          <span class="vx-meta" style="flex:0 0 86px">${label}</span>
          <span style="flex:1;height:7px;border-radius:99px;background:var(--vx-surface-0);overflow:hidden">
            <i style="display:block;height:100%;width:${Math.max(3,Math.min(100,v))}%;background:${col};border-radius:99px"></i></span>
          <b class="vx-mono" style="flex:0 0 34px;text-align:right;font-size:11.5px">${Math.round(v)}</b></div>`;
        rrHost.innerHTML='<div class="vx-kpi-label vx-mb1">Comparatif du comité — proba de gain & conviction</div>'
          +comp.map(x=>{
            const pw=x.vertex&&x.vertex.p_win!=null?Math.round(x.vertex.p_win*100):null;
            return (pw!=null?row(esc(x.symbol),'proba. de gain',pw,'var(--vx-positive)'):'')
              +(x.conviction!=null?row(esc(x.symbol),'conviction',x.conviction,'var(--vx-brand)'):'');
          }).join('');
      } else rrHost.innerHTML='';
    }
    const opts=(c.top_options||[]).slice(0,6);
    ($('vx-opp-options')||{}).innerHTML=opts.length?'<div class="vx-movergrid" style="grid-template-columns:repeat(auto-fit,minmax(234px,1fr))">'+opts.map(o=>{
      const isPut=(o.dir||'').toUpperCase()==='PUT';
      const prob=(o.prob!=null&&isFinite(o.prob))?Math.round(o.prob):null;
      /* Moneyness RÉELLE (spot vs strike). ITM = dans la monnaie. Rien inventé : si pas de spot → omis. */
      let moneyTag='';
      if(o.spot!=null&&o.strike!=null){
        const itm=isPut?(o.spot<o.strike):(o.spot>o.strike);
        const dist=Math.abs(o.spot/o.strike-1)*100;
        moneyTag=`<span class="vx-badge" title="position du strike vs cours ${VX.fmt.nd(o.spot)}" style="color:${itm?'var(--vx-positive)':'var(--vx-text-muted)'}">${itm?'ITM':'OTM'} ${dist.toFixed(1)}%</span>`;
      }
      /* Ligne de faits : delta · DTE · point mort — uniquement les champs présents */
      const facts=[];
      if(o.delta!=null)facts.push(`Δ <b>${VX.fmt.num(o.delta,2)}</b>`);
      if(o.dte!=null)facts.push(`<b>${o.dte}</b> j`);
      if(o.breakeven!=null)facts.push(`point mort <b>${VX.fmt.nd(o.breakeven)}</b>`);
      return `
      <button class="vx-mover" onclick="location.href='/options/dossier/${esc(o.symbol)}'" aria-label="Dossier options ${esc(o.symbol)}" style="border-left:3px solid var(--vx-violet)">
        <div class="vx-flex" style="justify-content:space-between;gap:6px;align-items:center"><span class="mv-sym">${esc(o.symbol)}</span>
          <span class="vx-badge" style="color:${isPut?'var(--vx-negative)':'var(--vx-positive)'}">${esc((o.dir||'CALL').toUpperCase())}</span>
          <span class="vx-badge" style="color:var(--vx-violet)">${esc(o.label||'')}</span>${moneyTag}</div>
        <div class="mv-sub" style="margin-top:7px;font-size:12px">strike <b style="color:var(--vx-text-secondary)">${VX.fmt.nd(o.strike)}</b> · prime <b style="color:var(--vx-text-secondary)">${VX.fmt.nd(o.premium)} $</b></div>
        ${facts.length?`<div class="mv-sub vx-mono" style="margin-top:4px;font-size:11px;color:var(--vx-text-muted)">${facts.join(' · ')}</div>`:''}
        ${prob!=null?`<div class="vx-flex" style="gap:7px;align-items:center;margin-top:8px">
          <span class="vx-meta" style="flex:0 0 auto">proba. profit</span>
          <span style="flex:1;height:6px;border-radius:99px;background:var(--vx-surface-0);overflow:hidden">
            <i style="display:block;height:100%;width:${Math.max(3,Math.min(100,prob))}%;background:${prob>=50?'var(--vx-positive)':'var(--vx-warning)'};border-radius:99px"></i></span>
          <b class="vx-mono" style="font-size:11.5px">${prob} %</b></div>`:''}
        <div class="mv-sub" style="color:var(--vx-violet);margin-top:8px">Dossier options →</div>
      </button>`;}).join('')+'</div>':VX.states.empty('Aucun contrat retenu — le sélecteur ne force jamais une idée.');
    /* Posture du comité : gros compteurs + barre empilée (HTML sur mesure,
       taille déterministe — fini le donut qui prenait toute la page). */
    const posture=$('vx-opp-posture');
    if(posture){
      const counts=c.counts||{};
      const _ck=Object.keys(counts).filter(k=>counts[k]>0);
      if(!_ck.length){posture.innerHTML='';}
      else{
        const tone={'ACHETER':'var(--vx-positive)','RENFORCER':'var(--vx-positive)','ATTENDRE':'var(--vx-warning)','WAIT':'var(--vx-warning)',
          'ÉVITER':'var(--vx-negative)','AVOID':'var(--vx-negative)','ALLÉGER':'var(--vx-negative)','ALLEGER':'var(--vx-negative)'};
        const total=_ck.reduce((a,k)=>a+counts[k],0)||1;
        const isDemo=!!(window.__vxStatus&&window.__vxStatus.demo);
        posture.classList.add('vx-card');
        posture.innerHTML=`<div class="vx-card-header"><span class="vx-card-title">Posture du comité</span>
            <span class="vx-chart-question">Comment se répartissent les verdicts aujourd’hui ?</span></div>
          <div class="vx-flex vx-wrap" style="gap:12px;margin:6px 0 12px">
            ${_ck.map(k=>`<div style="flex:1;min-width:110px;padding:11px 13px;border-radius:11px;background:var(--vx-surface-0);border:1px solid var(--vx-border);border-left:3px solid ${tone[k]||'var(--vx-text-dim)'}">
              <div style="font:700 24px/1.1 var(--vx-font-mono,monospace);color:${tone[k]||'var(--vx-text-dim)'}">${counts[k]}</div>
              <div class="vx-meta" style="margin-top:3px">${esc(k)}</div>
              <div class="vx-meta">${Math.round(counts[k]/total*100)} % des dossiers</div></div>`).join('')}
          </div>
          <div style="display:flex;height:12px;border-radius:99px;overflow:hidden;background:var(--vx-surface-0)" role="img" aria-label="Répartition des verdicts du comité">
            ${_ck.map(k=>`<i style="width:${(counts[k]/total*100).toFixed(1)}%;background:${tone[k]||'var(--vx-text-dim)'}"></i>`).join('')}
          </div>
          <div class="vx-card-footer">${VX.updateIndicator(cTs,isDemo?'démo':cSrc,isDemo?'fallback':(cTs?'delayed':''))}
            <span class="vx-meta">${total} dossier(s) passés en revue par le comité</span></div>`;
      }
    }
  }catch(e){
    ($('vx-opp-stocks')||{}).innerHTML=VX.states.error('Opportunités indisponibles');
    ($('vx-opp-options')||{}).innerHTML=VX.states.error('Opportunités indisponibles');
  }
}
/* Entonnoir de sélection : univers → notés → dossiers → achats (données du scan) */
function loadFunnel(scan){
  const host=$('vx-opp-funnel');if(!host)return;
  const rows=(scan&&scan.rows)||[];
  const CO=(window.VXCharts&&VXCharts.colors)||{};
  if(!(window.VXCharts&&VXCharts.funnel)||!rows.length){
    host.innerHTML=VX.states.empty('Univers non scanné.');return;
  }
  const scanned=rows.length;
  const noted=rows.filter(r=>r.score!==null&&r.score!==undefined).length;
  /* Le scan parle anglais (BUY/WATCH/WAIT/AVOID), le comité français — accepter
     les deux vocabulaires, sinon l'entonnoir affiche 0 achat à tort. */
  const isBuy=v=>['ACHETER','RENFORCER','BUY','STRONG_BUY'].includes((v||'').toUpperCase());
  const isAct=v=>{const u=(v||'').toUpperCase();return !!u&&!['ÉVITER','EVITER','AVOID','SELL','STRONG_SELL'].includes(u);};
  const dossiers=rows.filter(r=>isAct(r.verdict||r.decision)).length;
  const buys=rows.filter(r=>isBuy(r.verdict||r.decision)).length;
  VXCharts.funnel('vx-opp-funnel',{ariaLabel:'Entonnoir de sélection',fmt:v=>v,
    stages:[{label:'Univers scanné',value:scanned,color:CO.neutral},
      {label:'Notés',value:noted,color:CO.info},
      {label:'Dossiers actionnables',value:dossiers,color:CO.warning},
      {label:'Achats',value:buys,color:CO.positive}]});
  host.insertAdjacentHTML('beforeend',
    '<div class="vx-help vx-mt2">Chaque étape resserre l’univers jusqu’aux verdicts d’achat du comité. Un entonnoir plat = marché hostile.</div>');
}

/* ── ALERTES ── */
async function loadAlerts(){
  try{
    /*  `fired` etait LU et defini NULLE PART : `fired.fields` levait un
        ReferenceError a chaque chargement, que la page ait des donnees ou non.
        Le `catch` en dessous l'avalait et affichait « Alertes indisponibles » —
        un etat d'apparence honnete qui masquait un bug. La carte Alertes de la
        page d'accueil n'a donc JAMAIS fonctionne.

        Le serveur sert pourtant exactement la forme attendue :
        `/api/alerts/status` -> {fired:{…}}. Le fetch qui devait l'alimenter
        n'avait simplement jamais ete ecrit. */
    const [mine,cmd,fired]=await Promise.all([
      Promise.resolve((E()&&E().alerts())||[]),
      VX.fetch('/api/command',{ttl:30000}).catch(()=>({})),
      VX.fetch('/api/alerts/status',{ttl:30000}).catch(()=>({}))]);
    const firedMap=(fired&&fired.fired)||{};
    const srv=((cmd&&cmd.alerts)||[]).map(a=>{
      const icon=a[0]||'⚠', danger=(icon==='🔴');
      return `<div class="vx-flex" style="padding:6px 0;border-bottom:1px dashed var(--vx-border-soft)">
        <span aria-hidden="true">${esc(icon)}</span>
        <span class="vx-grow vx-dim" style="font-size:12px">${esc(a[2]||a[1]||'')}</span>
        <span class="vx-badge" style="color:var(--vx-${danger?'negative':'warning'})">${esc(a[1]||'alerte')}</span>
      </div>`;}).join('');
    const actives=mine.filter(a=>a.active);
    const rows=actives.slice(0,6).map(a=>{
      const hit=Object.values(firedMap).find(f=>f.id===a.id);
      /*  Une alerte DÉCLENCHÉE sans date se lit comme une alerte déclenchée
          maintenant. La boucle de `terminal.py` persiste pourtant `ts`
          (époque) et `price` au moment du franchissement : un déclenchement
          d'il y a trois jours rendait exactement le même badge qu'un
          déclenchement d'il y a une minute. On sert ce que le serveur a
          mesuré, et rien de plus. */
      const quand=hit&&hit.ts?VX.fmt.ago(hit.ts):'';
      const aQuel=(hit&&hit.price!=null)?(' à '+VX.fmt.price(hit.price)):'';
      return `<div class="vx-flex" style="padding:6px 0;border-bottom:1px dashed var(--vx-border-soft)">
        <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(a.sym)}">${esc(a.sym)}</button>
        <span class="vx-grow vx-dim" style="font-size:12px">${a.cond==='above'?'franchit':'casse'} ${VX.fmt.price(a.level)} ${esc(a.note||'')}</span>
        ${hit?`<span class="vx-badge" style="color:var(--vx-warning)" title="${esc('déclenchée'+aQuel+(quand?' · '+quand:''))}">déclenchée${quand?' · '+esc(quand):''}${esc(aQuel)}</span>`
             :'<span class="vx-badge">armée</span>'}
      </div>`;}).join('');
    /*  PIED DATÉ. Mesure du 06/09/2026 sur 5003 : la carte « Radar d'alertes »
        rendait deux alertes de risque et zéro `.vx-update`, quand douze autres
        cartes de la MÊME page en portaient un. Un radar sans heure ne dit pas
        si le balayage date de la minute ou de la veille.
        `/api/alerts/status` sert déjà `ts` (horloge serveur du dernier
        balayage, évalué toutes les 60 s) : c'est un âge MESURÉ, pas supposé, et
        c'est lui qui date la carte. Les alertes de risque viennent de
        `/api/command`, qui ne date pas sa charge — la ligne le nomme au lieu
        de laisser croire que tout partage la même heure. */
    const nSrv=((cmd&&cmd.alerts)||[]).length;
    const pied='<div class="vx-card-footer">'
      +VX.updateIndicator((fired&&fired.ts)||null,'balayage des alertes',fired&&fired.ts?'delayed':'')
      /*  Le chemin d'API ne s'affiche pas : « issues de /api/command » était
          le SEUL texte visible du produit à nommer une route (relevé .py/.js
          du 06/09/2026 ; l'autre occurrence, analysis_page.py:1402, est une
          URL de webhook que l'utilisateur doit recopier). Le contrat demande
          du français clair ; le propriétaire de ces alertes a un nom en
          français — `command.py` les documente comme « alertes du risk
          manager ». La provenance reste donc dite, sans jargon. */
      +` <span class="vx-meta">${nSrv} alerte(s) du moteur de risque — leur source ne les date pas`
      +` · ${actives.length} alerte(s) déclarée(s) active(s)${actives.length>6?' — 6 affichées':''}</span></div>`;
    ($('vx-alerts')||{}).innerHTML=((srv+rows)||VX.states.empty('Aucune alerte active.'))
      +'<div class="vx-mt2"><button class="vx-btn vx-btn-sm vx-btn-ghost" onclick="VXEntities.openAddModal(\'\',\'alert\')">+ Créer une alerte</button></div>'
      +pied;
  }catch(e){
    /*  Nommer la cause : un « indisponible » nu se lit comme une absence de
        donnee alors que c'etait un defaut de code. Un an durant, personne
        n'avait de quoi faire la difference. */
    ($('vx-alerts')||{}).innerHTML=VX.states.error('Alertes indisponibles — '+(e&&e.message?e.message:'cause inconnue'));}
}

/* ── Portefeuille + calendrier ── */
/* Dernier noeud de la DecisionTrace : le serveur ne connait pas les positions
   declarees, il ne suppose donc rien. Le client les lit et complete le noeud.
   Aucune valeur n'est calculee ici : on compte des positions deja enregistrees. */
function majTracePortefeuille(pos){
  const n=document.getElementById('vx-trace-portefeuille');
  if(!n)return;
  const val=n.querySelector('.vx2-trace-value');
  const meta=n.querySelector('.vx2-trace-meta');
  if(!pos||!pos.length){
    n.setAttribute('data-tone','missing');
    if(val)val.textContent='Aucune position';
    if(meta)meta.textContent='rien \u00e0 exposer';
    return;
  }
  const opts=pos.filter(t=>t.type&&t.type!=='STK').length;
  n.setAttribute('data-tone','neutral');
  if(val)val.textContent=pos.length+(pos.length>1?' positions':' position');
  if(meta)meta.textContent=opts?(opts+(opts>1?' options':' option')+' incluses'):'actions seulement';
}

async function loadPortfolio(){
  const pos=(E()&&E().positions())||[];
  majTracePortefeuille(pos);
  if(!pos.length){
    ($('vx-portfolio')||{}).innerHTML=VX.states.emptyDesk('Aucune position déclarée.',
      '<button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal(\'\',\'position\')">Déclarer une position</button>');
    return;
  }
  let quotes={};
  /* `null` = jamais mesuré (fetch en échec) — distinct de `false` (socket
     absente), distinct de `true`. Sans cette distinction, le pied de carte
     affirmait « IBKR temps réel/desk » sur la seule absence de `q.delayed`. */
  let pfLive=null,pfRepli=false;
  try{
    const body=pos.map(t=>({sym:t.sym,exp:t.exp,strike:t.strike,right:t.right}));
    const r=await fetch('/api/pos-quotes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({positions:body})});
    const j=await r.json();
    pfLive=!!j.live;pfRepli=!!j.fallback_used;
    const res=j.results||{};
    pos.forEach(t=>{const key=[String(t.sym).toUpperCase(),t.exp||'',
      (t.strike!==null&&t.strike!==undefined)?t.strike:'',(t.right||'').toUpperCase()].join('|');
      if(res[key])quotes[t.id]=res[key];});
  }catch(e){}
  /* Cartes design : symbole + P&L en grand, détail au-dessous — un clic ouvre la fiche. */
  ($('vx-portfolio')||{}).innerHTML='<div class="vx-pf-grid">'+pos.slice(0,8).map(t=>{
    const q=quotes[t.id]||{};const isOpt=t.type!=='STK';
    const mark=isOpt?(q.mark??q.last??null):(q.spot??q.mark??q.last??null);
    const value=mark!==null?(isOpt?mark*100*t.qty:mark*t.qty):null;
    const pl=value!==null&&t.cost?((value-t.cost)/t.cost*100):null;
    const plCol=pl>0?'var(--vx-positive)':pl<0?'var(--vx-negative)':'var(--vx-text-dim)';
    const totCost=pos.reduce((a,x)=>a+(x.cost||0),0)||1;
    const wgt=Math.round((t.cost||0)/totCost*100);
    const dte=(isOpt&&t.exp)?Math.max(0,Math.round((new Date(t.exp).getTime()-Date.now())/864e5)):null;
    return `<div class="vx-pf-card" style="border-left:3px solid ${plCol}">
      <div class="vx-flex" style="justify-content:space-between;gap:6px">
        <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(t.sym)}" style="font-weight:700;padding:0 4px">${esc(t.sym)}</button>
        <span class="vx-badge" ${isOpt?'style="color:var(--vx-violet)"':''}>${esc(t.type)}${t.strike?' '+esc(t.strike):''}</span></div>
      <div class="pf-pl" style="color:${plCol}">${pl!==null?((pl>0?'+':'')+VX.fmt.num(pl,1)+' %'):'n/d'}</div>
      <div class="pf-sub">${esc(t.qty)} × ${VX.fmt.price(t.cost)} $${t.exp?' · éch. '+esc(t.exp)+(dte!=null?' ('+dte+' j)':''):''}</div>
      <div class="pf-sub">${value!==null?('valeur '+VX.fmt.price(value)+' $'+(VX.quotes.differee(q)?' · différé':'')):'marque indisponible'}</div>
      <div class="vx-flex" style="gap:6px;align-items:center"><span class="vx-meta" style="flex:0 0 auto;font-size:9.5px">poids</span><span style="flex:1;height:4px;border-radius:99px;background:var(--vx-surface-1)"><i style="display:block;height:100%;width:${Math.max(3,Math.min(100,wgt))}%;background:var(--vx-brand);border-radius:99px"></i></span><b class="vx-mono" style="font-size:10px">${wgt} %</b></div>
      <div class="vx-flex" style="justify-content:flex-end;margin-top:auto">
        <button class="vx-btn vx-btn-icon vx-btn-ghost" data-entity-menu="${esc(t.sym)}" aria-label="Actions ${esc(t.sym)}">⋯</button></div>
    </div>`;
  }).join('')+'</div>'
  /* PROVENANCE DES MARQUES (constat 27 du 06/09/2026) : le pied affirmait
     « IBKR temps réel/desk » dès qu'aucune cote ne portait `delayed` — or le
     repli ACTION de /api/pos-quotes ne pose PAS ce drapeau (il ne pose que
     source/mode/fallback_used), et la réponse peut valoir `live:true` alors
     que toutes les marques viennent du scan (repro : file d'attente > 1,5 s,
     `fallback_used:true`). Deux témoins servis et jamais lus corrigent le
     mensonge sans rien recalculer ici : `fallback_used` (au moins une marque
     de repli) et `live` (preuve de socket). `pfLive===null` = non mesuré :
     on ne prétend ni live ni hors ligne.
     Second tour : le témoin de CARTE était corrigé, la ligne PAR POSITION ne
     l'était pas — « valeur 4 512 $ » restait muette sur une marque de scan,
     parce qu'elle testait encore `q.delayed` seul. Or chaque cote de repli
     ACTION porte `mode:'DELAYED'` et `fallback_used:true` (cotation_unifiee
     .en_charge_client) : le différé est lisible POSITION PAR POSITION sans
     rien attendre du serveur. La règle est dans VX.quotes.differee. */
  +`<div class="vx-card-footer">${pos.length} position(s) · marques ${Object.keys(quotes).length
      ?((Object.values(quotes).some(q=>VX.quotes.differee(q))||pfRepli)?'différées (scan)'
        :(pfLive===true?'IBKR temps réel/desk':pfLive===false?'desk — IBKR hors ligne':'provenance non mesurée'))
      :'indisponibles'}</div>`;
}
/* Calendrier avec filtre Tout · Macro · Résultats */
let CAL_FILTER='all',CAL_RANGE='week';
/* Symboles « à moi » : positions + favoris + watchlist + suivis (pour le filtre
   « Mes actions » du calendrier). Jamais bloquant si le desk est vide. */
function myCalSyms(){
  const E=window.VXEntities;const s=new Set();if(!E)return s;
  const add=(a,f)=>{try{(a||[]).forEach(x=>{const v=f(x);if(v)s.add(String(v).toUpperCase());});}catch(e){}};
  add(E.positions&&E.positions(),t=>t&&t.sym);
  add(E.favorites&&E.favorites(),x=>x);
  add(E.watchlist&&E.watchlist(),w=>w&&w.sym);
  add(E.follows&&E.follows(),r=>r&&r.sym);
  return s;
}

/* ── Session d'analyse : fraîcheur compacte, sans répéter les KPI du hero. ── */
function sessAge(s){if(s==null)return'';if(s<60)return'il y a '+s+' s';if(s<3600)return'il y a '+Math.round(s/60)+' min';return'il y a '+Math.round(s/3600)+' h';}
function sessRender(d){
  const el=$('vx-asess');if(!el)return;
  const st=d.state||'analyzing';
  const live=st==='ready';
  const stLabel=live?'Analyse à jour':st==='restored'?'Analyse restaurée · rafraîchissement…':'Analyse en cours…';
  const when=d.as_of?esc(String(d.as_of)):sessAge(d.age_s);
  const confidence=d.confidence!=null?('couverture '+esc(d.confidence)+' %'):'couverture n/d';
  el.innerHTML='<div class="vx-ss-card" data-state="'+st+'">'
    +'<div class="vx-ss-head"><span class="vx-ss-dot'+(live?' live':'')+'" aria-hidden="true"></span>'
    +'<span class="vx-ss-title">Fraîcheur de l’analyse</span>'
    +'<span class="vx-ss-state">'+stLabel+'</span>'
    +'<span class="vx-grow"></span>'
    +'<span class="vx-meta">'+when+' · '+confidence+(d.demo?' · démo':' · moteurs')+' · lecture seule</span></div></div>';
}
async function loadSession(){
  try{
    const cal=await VX.fetch('/cal-feed',{ttl:300000});
    const today=new Date().toISOString().slice(0,10);
    const horizon=CAL_RANGE==='day'?0:7;
    const mine=myCalSyms();
    const macro=(cal.macro||[]).map(m=>({when:m.date,dte:(m.dte==null?null:m.dte),
      kind:(m.date===today?'AUJOURD’HUI':(m.kind||'Économie')),
      label:m.label+(m.note?' — '+m.note:''),cat:'macro',mine:false}));
    const earn=(cal.items||[]).map(it=>({when:it.date,dte:it.dte,kind:'Résultats',
      label:`résultats dans ${it.dte} j`,sym:it.sym,cat:'earnings',
      mine:mine.has(String(it.sym||'').toUpperCase())}));
    const items=[...macro,...earn]
      .filter(i=>{
        if(i.dte!=null&&i.dte>horizon)return false;
        if(CAL_FILTER==='mine')return i.mine;
        return CAL_FILTER==='all'||i.cat===CAL_FILTER;})
      .sort((a,b)=>String(a.when).localeCompare(String(b.when))).slice(0,CAL_RANGE==='day'?10:16);
    const rangeCtl='<span class="vx-flex" style="gap:.3rem;margin-right:12px">'
      +[['day','Jour'],['week','Semaine']].map(([id,l])=>
        `<button class="vx-chip" data-calr="${id}" aria-pressed="${id===CAL_RANGE}">${l}</button>`).join('')+'</span>';
    const filtCtl=[['all','Tous'],['macro','Macro'],['earnings','Résultats'],['mine','Mes actions']].map(([id,l])=>
        `<button class="vx-chip" data-calf="${id}" aria-pressed="${id===CAL_FILTER}">${l}</button>`).join('');
    VXCharts.timelineCard('vx-calendar',{title:'Calendrier & catalyseurs',unit:'événements',
      question:'Quels catalyseurs arrivent '+(CAL_RANGE==='day'?'aujourd’hui':'cette semaine')+' ?',
      controlsHtml:rangeCtl+filtCtl,
      items,source:'calendrier moteur',timestamp:cal.ts?cal.ts*1000:null,mode:'delayed',
      emptyText:CAL_FILTER==='mine'?'Aucun catalyseur sur tes actions dans cet horizon.':'Aucun événement dans cet horizon.'});
    document.querySelectorAll('[data-calf]').forEach(b=>b.addEventListener('click',()=>{
      CAL_FILTER=b.dataset.calf;loadSession();}));
    document.querySelectorAll('[data-calr]').forEach(b=>b.addEventListener('click',()=>{
      CAL_RANGE=b.dataset.calr;loadSession();}));
  }catch(e){($('vx-calendar')||{}).innerHTML='<div class="vx-card">'+VX.states.error('Calendrier indisponible')+'</div>';}
}

/* Séance & scan : l'état RÉEL de la machine, en badges (heure NY, séance,
   couverture du scan, source des prix) — jamais un chiffre inventé. */
function sessionLine(scan){
  const sess=(scan&&scan.market)||{};
  const SESS_FR={open:'ouverte',closed:'fermée',pre:'pré-marché',premarket:'pré-marché',
    'pre-market':'pré-marché',after:'après-clôture',post:'après-clôture',
    afterhours:'après-clôture','after-hours':'après-clôture'};
  const b=[];
  if(sess.session)b.push(`<span class="vx-badge">Séance : ${esc(SESS_FR[String(sess.session).toLowerCase()]||sess.session)}</span>`);
  if(sess.et)b.push(`<span class="vx-badge">New York ${esc(sess.et)}</span>`);
  if(scan&&scan.scanned_n)b.push(`<span class="vx-badge">${scan.scanned_n}${scan.universe_n?' / '+scan.universe_n:''} titres scannés</span>`);
  if(scan&&scan.source)b.push(`<span class="vx-badge">prix : ${esc(scan.source==='ibkr'?'IBKR temps réel':scan.source)}</span>`);
  return b.length?`<div class="vx-flex vx-wrap vx-mt3" style="gap:.4rem">${b.join('')}</div>`:'';
}
/* ── L'ESSENTIEL : le marché en langage simple, au coup d'œil ── */
async function loadEssential(scan){
  const el=$('vx-ess-body');if(!el)return;
  let sum={};try{sum=await VX.fetch('/api/market/summary',{ttl:60000})||{};}catch(e){}
  let ed=null;try{ed=await VX.fetch('/api/briefing/editorial',{ttl:120000});}catch(e){}
  const idx=((scan&&scan.indices)||[]);
  const spx=idx.find(i=>i&&i.name==='S&P 500')||{};
  const chg=spx.change;
  const tTone=chg>0.15?'pos':chg<-0.15?'neg':'';
  const tWord=(chg===null||chg===undefined)?'—':(chg>0.15?'EN HAUSSE':chg<-0.15?'EN BAISSE':'STABLE');
  const tSub=(chg===null||chg===undefined)?'S&P 500 indisponible':('S&P 500 '+VX.fmt.pct(chg,1)+' aujourd’hui');
  const roro=String(sum.roro||'').toUpperCase();
  const aWord=roro==='RISK-ON'?'APPÉTIT':roro==='RISK-OFF'?'PRUDENCE':(roro==='NEUTRE'?'NEUTRE':'—');
  const aTone=roro==='RISK-ON'?'pos':roro==='RISK-OFF'?'neg':'';
  const aSub=roro==='RISK-ON'?'l’argent va vers les actifs risqués':roro==='RISK-OFF'?'les investisseurs privilégient la sécurité':(roro==='NEUTRE'?'ni appétit ni aversion marqués':'appétit pour le risque non fourni');
  const vix=sum.vix;
  const vWord=vix==null?'—':(vix<15?'CALME':vix<25?'NORMALE':'NERVEUSE');
  const vTone=vix==null?'':(vix<15?'pos':vix<25?'':'neg');
  const vSub=vix==null?'VIX indisponible':('VIX '+VX.fmt.num(vix,1)+' — '+(vix<15?'pas de stress visible':vix<25?'nervosité ordinaire':'protection recherchée'));
  const bs=(sum.best_sector&&sum.best_sector.sector)||null;
  /* Participation (breadth > MM50) en 5e tuile météo */
  let br=null;const sb=sum.breadth;
  if(sb!=null&&typeof sb==='object')br=(sb.above50!=null)?Number(sb.above50):null;
  else if(sb!=null&&!isNaN(sb))br=Number(sb);
  const bWord=br==null?'—':(br>=55?'PARTAGÉE':br>=45?'MOYENNE':'ÉTROITE');
  const bTone=br==null?'':(br>=55?'pos':br>=45?'':'neg');
  const bSub=br==null?'participation indisponible':(Math.round(br)+' % des titres > MM50');
  // Builder partagé (CMP-02) — tuile .vx-stat canonique (vfs=17). Repli inline si VX.tile absent.
  const tile=(k,v,sub,tone,extra)=>(window.VX&&VX.tile)?VX.tile.stat({k:k,v:v,sub:sub,tone:tone,extra:extra,vfs:17})
    :`<div class="vx-stat" data-tone="${tone||''}"><div class="vx-stat-k">${k}</div><div class="vx-stat-v" style="font-size:17px">${v}</div><div class="vx-stat-sub">${sub}</div>${extra||''}</div>`;
  const spxSpark=(spx.spark&&spx.spark.length>2)?sparkSvg(spx.spark,(chg==null?true:chg>=0)):'';
  const vixIdx=idx.find(i=>i&&i.name==='VIX')||{};
  const vixSpark=(vixIdx.spark&&vixIdx.spark.length>2)?sparkSvg(vixIdx.spark,true,true):'';
  const rows=(scan&&scan.rows)||[];
  const ups=rows.filter(r=>r.change>0).sort((a,b)=>b.change-a.change);
  const downs=rows.filter(r=>r.change<0).sort((a,b)=>a.change-b.change);
  const mv=(r,pos)=>r?`<button class="vx-chip" data-open-analysis="${esc(r.symbol)}" style="color:${pos?'var(--vx-positive)':'var(--vx-negative)'}"><b>${esc(r.symbol)}</b>&nbsp;${VX.fmt.pct(r.change,1)}</button>`:'';
  /*  « A retenir » rendait `ed.lines.slice(0,3)` — exactement les memes
      premieres lignes que « Essentiels de la journee » dans la carte Brief,
      juste a cote. Deux cartes, un seul texte : l'utilisateur lisait la meme
      phrase deux fois sur un ecran. Cette carte garde ce qu'elle SEULE porte,
      cinq mesures lisibles d'un coup d'oeil, et renvoie au proprietaire de la
      prose.  */
  const nLignes=((ed&&ed.lines)||[]).length;
  el.innerHTML=
    `<div class="vx-statrow">${tile('Tendance',tWord,tSub,tTone,spxSpark)}${tile('Ambiance',aWord,aSub,aTone)}${tile('Volatilité',vWord,vSub,vTone,vixSpark)}${tile('Participation',bWord,bSub,bTone)}${tile('Secteur fort',bs?esc(bs):'—',bs?'meneur du jour':'aucun secteur classé par le scan',bs?'brand':'')}</div>`
    +(nLignes?`<p class="vx2-stamp vx-mt3">La lecture rédigée — ${nLignes} ligne${nLignes>1?'s':''} — vit dans <b>Brief du marché</b>, ci-dessous.</p>`:'')
    /* « Mouvements du jour » retiré — doublon avec la section Top 10 (épuré : seulement l'essentiel) */
    +sessionLine(scan);
  const meta=$('vx-ess-meta');
  if(meta)meta.innerHTML=VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',(scan&&scan.data_source==='demo')?'fallback':'delayed');
}

/* ── Actualités marquantes : news RÉELLES (assainies serveur, ré-échappées).
   HTML VALIDE : le lien source (↗) et le bouton ticker sont FRÈRES — jamais
   de bouton imbriqué dans un lien. ── */
let NEWS_FILTER='all';
/* Plafond d'affichage du fil — UN SEUL endroit (il était écrit dans le `slice`
   et le pied ne le nommait pas : 8 lignes sur 45 servies, sans le dire). */
const NEWS_MAX=8;
const NEWS_LIB={all:'Tout',pos:'Positives',neg:'Négatives'};
async function loadNews(){
  const el=$('vx-news-body');if(!el)return;
  /* `err` séparé de « rien servi » : le contrat produit exige que l'ERREUR,
     l'ABSENCE et le ZÉRO restent distincts. Avant, un fetch en échec et un fil
     vide rendaient le MÊME texte, qui affirmait de surcroît une cause jamais
     mesurée (« hors ligne dans cet environnement »). */
  let d=null,err=null;
  try{d=await VX.fetch('/news-feed',{ttl:120000});}catch(e){err=e;}
  /* Filtre de sentiment : côté affichage uniquement (le flux reste complet) */
  const all=((d&&d.items)||[]);
  const head=el.closest('section').querySelector('.vx-card-header');
  if(head&&!head.querySelector('[data-newsf]')){
    /* Les chips et le pied nomment le filtre depuis la MÊME table : deux listes
       de libellés finissent toujours par diverger, et le pied doit dire
       exactement le filtre que le lecteur a cliqué. */
    head.insertAdjacentHTML('beforeend','<span class="vx-actions">'
      +Object.keys(NEWS_LIB).map(id=>
        `<button class="vx-chip" data-newsf="${id}" aria-pressed="${id===NEWS_FILTER}">${NEWS_LIB[id]}</button>`).join('')+'</span>');
    head.querySelectorAll('[data-newsf]').forEach(b=>b.addEventListener('click',()=>{
      NEWS_FILTER=b.dataset.newsf;
      head.querySelectorAll('[data-newsf]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      loadNews();}));
  }
  const retenus=all.filter(n=>{const v=+n.senti||0;
    return NEWS_FILTER==='all'||(NEWS_FILTER==='pos'?v>0:v<0);});
  const items=retenus.slice(0,NEWS_MAX);
  /* PIED DATÉ, dans TOUTES les branches. Mesure du 06/09/2026 : l'early-return
     ci-dessous était à l'offset 63 de la fonction et le pied à l'offset 3993 —
     autrement dit le cas dégradé (fetch en échec, fil vide, filtre sans
     résultat) rendait une carte à ZÉRO `.vx-update`, exactement le défaut que
     le pied était censé corriger, et précisément quand le lecteur a besoin de
     savoir de quand date ce qu'il ne voit pas. */
  const pied=newsPied(d,items.length,retenus.length,all.length);
  if(!items.length){
    el.innerHTML=(err
      ?VX.states.error('Fil d’actualités injoignable — '+esc(err.message||'requête en échec'))
      :VX.states.empty(all.length
        ?('Aucun titre ne correspond au filtre « '+NEWS_LIB[NEWS_FILTER]+' » — '+all.length+' titre(s) servis, aucun de ce sentiment.')
        :'Le fil n’a servi aucun titre. Ni la cause ni la disponibilité chez la source ne sont mesurées ici : le pied ci-dessous dit l’âge et la provenance de ce fil.'))
      +pied;
    return;
  }
  el.innerHTML=items.map(n=>{
    /* Titres/éditeurs DÉJÀ échappés côté serveur (news_plus._clean_text :
       ' → &#39; etc.) — les ré-échapper affichait « d&#39;intelligence ».
       On insère tels quels ; seuls les champs utilisés en ATTRIBUT passent esc(). */
    const t=String(n.fr||n.title||'—');
    const src=String(n.publisher||n.pub||'');
    const sym=n.sym||'';
    const link=n.link||'';
    /* Heure de PUBLICATION (source, normalisée) ; l'heure de réception reste
       en titre de l'info-bulle. Plusieurs agences pour un même fait = dit.
       L'ancienne regex `(\d{2}:\d{2})` rendait « 13:05 » NU : le `Z` d'un
       published_at UTC était jeté et la DATE perdue (mesure du 06/09/2026 :
       une dépêche de 12 min se lisait vieille de 2 h 12 face à l'horloge du
       lecteur, un item du 04/09 s'affichait « 23:42 » comme s'il datait du
       jour). `VX.fmt.instantSource` convertit quand la source déclare son
       fuseau, et marque « fuseau n/d » quand elle n'en déclare aucun. */
    const iso=(n.published_at||n.time)||'';
    const hm=VX.fmt.instantSource(iso,{style:'ago'});
    const nsrc=(+n.n_sources||0)>1?` · ${n.n_sources} sources`:'';
    const s=+n.senti||0;
    const dot=s?`<span style="display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:5px;vertical-align:1px;background:${s>0?'var(--vx-positive)':'var(--vx-negative)'}"></span>`:'';
    return `<article data-senti="${s>0?1:s<0?-1:0}" style="padding:7px 0;border-bottom:1px dashed var(--vx-border-soft)">
      <div style="font-size:12.5px;line-height:1.45;color:var(--vx-text-secondary)">${dot}${t}</div>
      <div class="vx-meta vx-mt1">
        ${sym?`<button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(sym)}" style="padding:0 4px">${esc(sym)}</button> · `:''}
        <span title="${esc(VX.fmt.instantSourceNote(iso))}${n.received_at?' · reçu par Vertex '+esc(n.received_at):''}">${src}${hm?` · ${hm}`:''}${nsrc}</span>
        ${link?` · <a href="${esc(link)}" target="_blank" rel="noopener noreferrer" aria-label="Ouvrir la source">source ↗</a>`:''}
      </div></article>`;
  }).join('')
  +pied
  +`<div class="vx-meta vx-mt2">Sources publiques, assainies côté serveur — de l’information, jamais un conseil.</div>`;
}
/* PIED DATÉ du fil (constat 43 du 06/09/2026) : la carte rendait 8 titres sur
   45 sans un seul `.vx-update`, quand 19 autres tampons vivaient sur la MÊME
   page (« Il y a 25 min · yfinance Différé ») — et /news-feed sert déjà `ts`,
   `as_of`, `source` et `source_detail` {ibkr, web} que personne n'affichait.
   Sans âge ni provenance, un onglet laissé ouvert présente des titres figés
   sous un intertitre qui promet « aujourd'hui ». `d` nul (fetch en échec) →
   « Âge inconnu » : l'absence reste dite, et ce pied est rendu AUSSI dans les
   branches dégradées, qui n'en avaient aucun.
   Le compte disait « 8 sur 45 servis » sans nommer NI le plafond NI le filtre :
   avec « Positives » actif, le lecteur ne pouvait pas savoir si 8 était la
   récolte du filtre ou une troncature. Les trois nombres sont désormais
   distincts — affichés, retenus par le filtre, servis par le fil. */
function newsPied(d,nAffiches,nRetenus,nServis){
  const compte=nAffiches+' titre(s) affiché(s)'
    +(nRetenus>nAffiches?' sur '+nRetenus+' retenu(s) — plafond d’affichage '+NEWS_MAX:'')
    +(NEWS_FILTER!=='all'?' · filtre « '+NEWS_LIB[NEWS_FILTER]+' »':'')
    +' · '+nServis+' servi(s) par le fil';
  /* MODE MESURÉ, jamais posé d'office. `d` nul = la requête a échoué : AUCUNE
     charge n'a été servie, donc il n'y a pas de mode à qualifier. Coder
     'delayed' en dur collait l'étiquette d'une donnée servie (« Différé ») sur
     une ABSENCE de donnée — mesure du 06/09/2026 : newsPied(null,0,0,0) rendait
     « Âge inconnu · fil source inconnue Différé ». Le contrat exige que
     l'erreur, l'absence et le zéro restent distincts ; c'est la règle que
     `pfModeMarques` applique déjà côté Portefeuille (mode '' quand rien n'est
     mesuré). Charge servie → 'delayed' est MESURÉ et non supposé : /news-feed
     ne transporte aucun tick, seulement des dépêches déjà publiées. */
  const mode=d?'delayed':'';
  return `<div class="vx-card-footer">${VX.updateIndicator((d&&(d.ts?d.ts*1000:d.as_of))||null,
      'fil '+((d&&d.source)||'source inconnue')
      +((d&&d.source_detail)?` (courtier ${d.source_detail.ibkr||0} · web ${d.source_detail.web||0})`:''),
      mode)} · ${compte}</div>`;
}

/* ── Ancres de section : générées DEPUIS le DOM (ordre chips = ordre DOM,
   l'inversion devient impossible par construction) + chip actif au scroll ── */
function buildAnchors(){
  const nav=$('vx-dash-anchors');if(!nav)return;
  reorderBlocks();
  const blocks=[...document.querySelectorAll('[data-block]')].filter(el=>el.dataset.anchorLabel);
  nav.innerHTML=blocks.map(el=>
    `<button class="vx-chip" data-anchor="${el.dataset.block}" aria-pressed="false">${el.dataset.anchorLabel}</button>`).join('');
  nav.querySelectorAll('[data-anchor]').forEach(b=>b.addEventListener('click',()=>{
    const t=document.querySelector('[data-block='+b.dataset.anchor+']');
    if(t)t.scrollIntoView({behavior:'smooth',block:'start'});}));
  if('IntersectionObserver' in window){
    const io=new IntersectionObserver((ents)=>{
      ents.forEach(e=>{if(!e.isIntersecting)return;
        const k=e.target.dataset.block;
        nav.querySelectorAll('[data-anchor]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.anchor===k)));});
    },{rootMargin:'-120px 0px -60% 0px'});
    blocks.forEach(t=>io.observe(t));
  }
  applyBlocks();
}
/* Boutons « ↓ » : défilement vers un bloc (délégué — présent dans plusieurs cartes) */
document.addEventListener('click',(ev)=>{
  const b=ev.target.closest('[data-scrollto]');if(!b)return;
  const t=document.querySelector('[data-block='+b.dataset.scrollto+']');
  if(t)t.scrollIntoView({behavior:'smooth',block:'start'});
});
/* Ancien /markets?view=… → /#ancre : on honore le hash à l'arrivée ET quand il
   change sans rechargement (palette de commandes ouverte depuis le Dashboard). */
function hashScroll(){
  const h=(location.hash||'').replace('#','');
  if(!h)return;
  const t=document.querySelector('[data-block='+CSS.escape(h)+']');
  if(t)setTimeout(()=>t.scrollIntoView({behavior:'smooth',block:'start'}),300);
}
window.addEventListener('hashchange',hashScroll);

/* ── Orchestration ── */
async function boot(){
  buildAnchors();
  loadBrief();loadRegime();loadRegimeDrivers();loadOpportunities();loadAlerts();loadPortfolio();loadSession();loadNews();loadRoro();
  const scan=await loadStrip();
  loadMarketGrid(scan);loadDiff(scan);
  loadEssential(scan);loadMainChart(scan);loadCompare(scan);loadYield(scan);
  loadSectorsBlock(scan);loadPulse(scan);loadPulseExtra(scan);loadTopFlop(scan);loadFunnel(scan);
  hashScroll();
  /* Bouton « remonter » : visible après un vrai défilement, quel que soit le
     conteneur qui défile (fenêtre ou .vx-content). */
  const bt=$('vx-backtop');
  if(bt){
    const y=()=>{const sc=document.querySelector('.vx-content');
      return Math.max(window.scrollY||0,(sc&&sc.scrollTop)||0);};
    document.addEventListener('scroll',()=>{bt.style.display=y()>900?'block':'none';},true);
    bt.addEventListener('click',()=>{const sc=document.querySelector('.vx-content');
      if(sc)sc.scrollTo({top:0,behavior:'smooth'});
      window.scrollTo({top:0,behavior:'smooth'});});
  }
}
function whenChartsReady(fn){
  if(window.VXCharts&&window.Chart)return fn();
  window.addEventListener('load',fn,{once:true});
}
whenChartsReady(boot);
/* EN DIRECT : toutes les 2 min, re-scan complet de la page (bandeau, situation,
   héros, pouls, mouvements) — quand TWS est ouvert, la source passe en IBKR
   temps réel automatiquement. */
VX.refresh.register(async()=>{
  const s=await loadStrip();
  loadMarketGrid(s);
  loadEssential(s);loadMainChart(s);loadCompare(s);loadPulse(s);loadPulseExtra(s);loadTopFlop(s);
},120000,'marchés');
VX.refresh.register(loadAlerts,60000,'alerts');
/* Le fil d'actualités n'était rejoué NULLE PART (mesuré : loadNews n'apparaît
   qu'au boot et au clic de filtre ; 4 s après `VX.liveReact('news')`, zéro
   requête /news-feed supplémentaire). Un onglet ouvert affichait donc les
   titres de l'heure du chargement.
   CE QUE CET ENREGISTREMENT APPORTE RÉELLEMENT — le commentaire précédent
   attribuait le gain à la cadence, la mesure dit autre chose : `/news-feed`
   n'est pas dans LIVE_TTL, et vx-core `_effTtl` relève son TTL à
   SESSION_TTL = 1 800 000 ms dès que `session_status === 'ready'`. Le tour de
   120 s re-rend donc la carte SANS refetch pendant 30 min (l'âge du pied, lui,
   continue de vieillir honnêtement). Le vrai déblocage est l'entrée dans
   `VX.refresh.runTasks()` : live-updates.js invalide le préfixe '/news' —
   `VX.fetch.invalidate` est bien préfixe — PUIS rejoue les tâches de la page.
   C'est l'événement serveur qui rafraîchit ce canal, pas l'horloge. */
VX.refresh.register(loadNews,120000,'actualités');
VX.refresh.register(loadSession,45000,'session-digest');
VX.bus.on('vx:position-changed',loadPortfolio);
VX.bus.on('vx:alert-changed',loadAlerts);
VX.bus.on('vx:data-refreshed',()=>{loadBrief();loadRegime();loadRegimeDrivers();});
})();
</script>
"""


def render(scan_state: dict | None = None) -> str:
    content = _CONTENT.replace('%%LOADING%%',
                               '<div class="vx-skeleton" style="height:60px"></div>')
    content = content.replace('%%HERO%%', _hero_aujourdhui(scan_state or {}))
    #  L'INSTANT DU SCAN, POSÉ DANS LA PAGE.
    #  `/api/command` ne sert aucun horodatage : mesure du 06/09/2026 sur 5003,
    #  ses clés sont exactement {alerts, controls_availability, counts,
    #  decision, exposure, portfolio_score, regime, risk, top_options,
    #  top_stocks, validation} — ni `ts`, ni `as_of`, ni `updated`. La carte
    #  « Posture du comité » lisait donc `cTs = null` et affichait
    #  « Âge inconnu · comité Différé » : un mode servi affirmé sur une charge
    #  dont l'âge n'était pas mesuré.
    #  Cet âge est pourtant connu sans le moindre appel réseau : `command.py`
    #  ne lit QUE `scan_state` (market_ctx, committee, strategy, detail), donc
    #  la charge du comité a exactement l'âge du scan qui l'a produite. Le
    #  serveur la pose ici ; le client la lit en repli, et le pied dit d'où
    #  vient cette date plutôt que de la faire passer pour celle de l'endpoint.
    #  Attribut ABSENT quand le scan ne date rien : jamais une chaîne vide.
    #  L'instant part sous la forme QUE LE CLIENT SAIT LIRE : `scan_ts` brute
    #  (une époque) devenait la chaîne « 1788719544.6501086 », que
    #  `VX.freshness._ms` rend `null` — truthy pour `cTs`, donc « Différé »
    #  affirmé, mais « Âge inconnu » affiché et `data-ts` absent (mesuré dans
    #  Chromium). `_instant_scan` convertit, comme `build_editorial`.
    ts_scan = _instant_scan(scan_state or {})
    content = content.replace(
        '%%SCANTS%%',
        f' data-scan-ts="{ts_scan}"' if ts_scan else '')
    # `page_label` reste « Dashboard » : le routeur client et plusieurs bancs s'y
    # adossent. L'espace, lui, s'appelle Aujourd'hui — c'est ce que l'utilisateur lit.
    return render_shell(title='Aujourd’hui', active='briefing',
                        space_label='Aujourd’hui',
                        sub_label='Marchés US', content=content, page_js=_JS,
                        page_label='Dashboard')
