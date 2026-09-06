"""
vertex/services/live_engine.py — VERTEX LIVE ENGINE (moteur central de synchronisation).

LE moteur dont dépendent toutes les pages : il connaît chaque domaine de
données (prix/scan, options, entreprises, news, calendrier, hebdo, IA),
sa source, son timestamp, sa fraîcheur et son état — et sait déclencher
les mises à jour.

Architecture réelle de Vertex (honnêteté d'abord) :
- la SOURCE DE VÉRITÉ serveur est `scan_state` (+ news/cal/weekly states),
  mutée en place par les boucles de fond de terminal.py ;
- le connecteur broker est ib_async → TWS/Gateway (ib_reader.py), en
  LECTURE SEULE ; sur le cloud (NO_IBKR=1) les prix viennent de yfinance
  (delayed ~15 min) ou du mode démo (synthétique, marqué) ;
- ce moteur ORCHESTRE : il lit les états, calcule la fraîcheur, déclenche
  le re-scan (l'événement réveille la boucle qui recalcule prix,
  indicateurs, scores Vertex, comité, stratégie options, risques,
  recommandations — toute la chaîne), et produit le RAPPORT DE SYNC.
- une éventuelle migration vers l'API Client Portal IBKR (HTTP+WebSocket)
  se brancherait ICI, derrière les mêmes domaines/états, sans toucher
  aux pages.

⛔ Analyse uniquement, lecture seule — ce moteur rafraîchit des données,
il ne transmet jamais d'ordre.
"""

import os
import threading
import time

# câblé par terminal.py au démarrage (configure) — aucune importation circulaire
_CFG = {
    'scan_state': None, 'news_state': None, 'cal_state': None,
    'weekly_state': None, 'rescan_event': None,
    'ibkr_enabled': False, 'demo': False,
}
_LAST_REPORT = {'ts': None, 'requested': [], 'lines': []}
_FORCE = {}                                   # domaine -> threading.Event (forçage de cycle)


#: Domaine -> (instant du dernier passage en attente, timeout demandé).
#: LA SEULE PREUVE qu'un exécutant existe dans CE processus pour ce domaine.
#: Voir `boucle_a_l_ecoute` : le rapport de synchronisation s'en sert au lieu
#: d'affirmer qu'un cycle a été déclenché.
_ECOUTES: dict = {}
#: Marge au-delà du timeout annoncé avant de considérer le signal périmé : une
#: boucle qui redemande `wait_force(domain, 60)` toutes les 60 s reste vue comme
#: vivante, une boucle morte cesse d'être comptée peu après son échéance.
_ECOUTE_MARGE_S = 30.0


def force_event(domain):
    """L'événement de forçage d'un domaine (créé au premier accès)."""
    ev = _FORCE.get(domain)
    if ev is None:
        ev = _FORCE[domain] = threading.Event()
    return ev


def wait_force(domain, timeout):
    """Attente interruptible pour les boucles : dort `timeout` s OU se réveille
    immédiatement si le Sync Center force le domaine. Renvoie True si forcé.

    Le passage est NOTÉ (`_ECOUTES`) : c'est ici, et nulle part ailleurs, qu'un
    exécutant se manifeste. Sans cette note, `refresh()` ne peut que supposer.
    """
    ev = force_event(domain)
    _ECOUTES[domain] = (time.time(), float(timeout or 0))
    forced = ev.wait(timeout)
    if forced:
        ev.clear()
    return forced


def boucle_a_l_ecoute(domain, maintenant=None) -> bool:
    """Une boucle attend-elle RÉELLEMENT un forçage sur ce domaine, ici ?

    Mesure, jamais supposition : `wait_force` note son passage et le timeout
    qu'elle a demandé ; le signal vaut jusqu'à cette échéance plus une marge.
    Une boucle qui n'existe pas dans cette configuration — ou qui est morte —
    ne note rien, et `refresh()` cesse alors de promettre un cycle.
    """
    vu = _ECOUTES.get(domain)
    if not vu:
        return False
    quand, timeout = vu
    return ((maintenant or time.time()) - quand) <= (timeout + _ECOUTE_MARGE_S)

# seuils de fraîcheur par domaine (secondes) : (frais, rassis) — au-delà : hors ligne
_THRESH = {
    'prices':    (300, 1800),
    'options':   (3600, 6 * 3600),
    'companies': (48 * 3600, 8 * 86400),
    'news':      (2 * 3600, 12 * 3600),
    'calendar':  (86400, 4 * 86400),
    'weekly':    (8 * 86400, 15 * 86400),
    'ai':        (300, 1800),          # dérivée du scan (comité/brief à la demande)
}

_LABELS = {
    'prices':    ('📈', 'Prix & scores', 'scan complet : prix, indicateurs, scores Vertex, comité, risques'),
    'options':   ('💎', 'Options', 'board d\'options : chaînes, qualité, stratégie par horizons'),
    'companies': ('🏢', 'Entreprises', 'profils : fondamentaux, consensus, description'),
    'news':      ('📰', 'News', 'flux d\'actualités traduites'),
    'calendar':  ('📅', 'Calendrier', 'résultats à venir (earnings)'),
    'weekly':    ('🗓️', 'Hebdo', 'watchlist de la semaine'),
    'ai':        ('🧠', 'Analyses IA', 'brief, comité, lectures — recalculées sur les données du scan'),
}


def configure(**kw):
    """Câblage depuis terminal.py : états partagés + événement de re-scan."""
    _CFG.update(kw)


def calculate_freshness(age_s, domain='prices'):
    """(état, libellé humain) pour un âge donné — la règle unique de fraîcheur."""
    if age_s is None:
        return 'offline', 'jamais synchronisé'
    fresh, stale = _THRESH.get(domain, (600, 3600))
    if age_s < 60:
        lab = 'il y a %ds' % int(age_s)
    elif age_s < 3600:
        lab = 'il y a %d min' % (age_s // 60)
    elif age_s < 86400:
        lab = 'il y a %d h' % (age_s // 3600)
    else:
        lab = 'il y a %d j' % (age_s // 86400)
    return ('ok' if age_s < fresh else 'stale' if age_s < stale else 'offline'), lab


def _age(ts):
    return None if not ts else max(0, time.time() - ts)


def _company_ts():
    try:
        from vertex.services import persist
        p = persist.cache_path('company_cache.json')
        return os.path.getmtime(p) if os.path.exists(p) else None
    except Exception:
        return None


def _company_count():
    """Combien d'entreprises le cache porte-t-il vraiment ?

    Le decompte etait fige a None alors que la donnee existe : le Sync Center
    montrait « companies · ok » sans jamais dire sur combien de profils, seul
    domaine dans ce cas. Lecture defensive — un cache illisible rend None, ce
    qui reste plus honnete qu'un zero invente (QUALITY_STANDARD §1).
    """
    try:
        from vertex.services import persist
        cache = persist.load_json('company_cache.json', None)
        return len(cache) if isinstance(cache, dict) else None
    except Exception:
        return None


def _domains():
    st = _CFG['scan_state'] or {}
    news = _CFG['news_state'] or {}
    cal = _CFG['cal_state'] or {}
    wk = _CFG['weekly_state'] or {}
    scan_ts = st.get('scan_ts')
    opt_ts = None
    board = st.get('options_board') or []
    if board:
        opt_ts = st.get('scan_ts')                     # publié par le cycle de scan en démo
    try:
        from vertex.services import persist
        oc = persist.load_json('options_cache.json', None)
        if oc and oc.get('ts'):
            opt_ts = oc['ts']
    except Exception:
        pass

    def _upd_ts(state):
        # states news/cal portent 'updated' en horodatage humain — on garde le ts du scan sinon
        return state.get('ts') or (scan_ts if state.get('items') or state.get('data') else None)

    counts = {
        'prices': len(st.get('rows') or []),
        'options': len(board),
        'companies': _company_count(),
        'news': len(news.get('items') or []),
        'calendar': len(cal.get('items') or []),
        'weekly': len(((wk.get('data') or {}).get('picks') or [])) or (1 if wk.get('data') else 0),
        'ai': len((st.get('committee') or {}).get('decisions') or []),
    }
    tss = {
        'prices': scan_ts, 'options': opt_ts, 'companies': _company_ts(),
        'news': _upd_ts(news), 'calendar': _upd_ts(cal),
        'weekly': scan_ts if wk.get('data') else None, 'ai': scan_ts,
    }
    # Source HONNÊTE du domaine prix : les scores/tableaux du scan viennent du
    # téléchargement daily (yfinance/stooq) même en mode IBKR — le live IBKR
    # alimente l'overlay /quotes et les options. On affiche la vraie chaîne.
    scan_src = st.get('source')
    #  « temps réel » n'est écrit que sur PREUVE de socket (`ibkr_state.sync`
    #  pose `ibkr_live` quand un tick récent arrive en type 1) — plus jamais
    #  depuis le seul drapeau de configuration `ibkr_enabled`.
    ibkr_live = bool(st.get('ibkr_live'))
    src = ('démo (synthétique)' if _CFG['demo']
           else ('scan %s + cotations IBKR temps réel' % scan_src) if (ibkr_live and scan_src and scan_src != 'demo')
           else ('scan %s (IBKR configuré, socket sans tick récent)' % scan_src) if (_CFG['ibkr_enabled'] and scan_src and scan_src != 'demo')
           else 'IBKR configuré — aucune cotation reçue' if _CFG['ibkr_enabled'] else 'yfinance (delayed ~15 min)')
    sources = {
        'prices': src, 'options': ('démo' if _CFG['demo'] else 'chaînes IBKR/yfinance'),
        'companies': 'yfinance + cache hebdo',
        #  La SOURCE REELLE du fil, pas une etiquette figee : « depeches
        #  ibkr » et « depeches web » ne se lisent pas pareil, et un fil
        #  qui bascule entierement sur le web doit se voir.
        'news': ('depeches %s (traduites)' % news['source']) if news.get('source')
                else 'flux traduits',
        'calendar': 'yfinance earnings', 'weekly': 'scan hebdo', 'ai': 'moteurs Vertex (sur scan)',
    }
    out = {}
    for k, (icon, label, detail) in _LABELS.items():
        age = _age(tss[k])
        state, fresh_label = calculate_freshness(age, k)
        out[k] = {'icon': icon, 'label': label, 'detail': detail,
                  'source': sources[k], 'ts': tss[k], 'age_s': None if age is None else round(age),
                  'freshness': fresh_label, 'state': state, 'count': counts[k]}
    return out


def mode():
    """Mode global : live · delayed · demo · offline."""
    st = _CFG['scan_state'] or {}
    if not st.get('scan_ts'):
        return 'offline'
    if _CFG['demo']:
        return 'demo'
    #  Preuve de socket, pas configuration : sans tick récent, c'est du différé.
    return 'live' if (_CFG['ibkr_enabled'] and st.get('ibkr_live')) else 'delayed'


def status():
    """L'état complet du système — ce que le Sync Center affiche."""
    doms = _domains()
    errors = []
    st = _CFG['scan_state'] or {}
    if st.get('error'):
        errors.append({'domain': 'prices', 'error': str(st['error'])[:200]})
    for k, d in doms.items():
        if d['state'] == 'offline' and k in ('prices',):
            errors.append({'domain': k, 'error': 'domaine jamais synchronisé — le scan n\'a pas encore tourné'})
    return {
        'mode': mode(),
        'ibkr': bool(_CFG['ibkr_enabled']),
        'demo': bool(_CFG['demo']),
        'domains': doms,
        'errors': errors,
        'last_refresh': _LAST_REPORT['ts'],
        'generated': round(time.time()),
    }


def refresh(domains=None):
    """Déclenche la mise à jour. `domains` None/['all'] = tout.

    Le re-scan couvre TOUTE la chaîne dépendante du scan : prix →
    indicateurs → scores Vertex → comité → stratégie options → risques →
    recommandations → analyses (brief/comité recalculés à la lecture).
    Les domaines à boucle propre (options réelles, news, calendrier) se
    resynchronisent à leur prochain cycle — le rapport le dit clairement.

    ## Ce que ce rapport n'a plus le droit d'affirmer (mesuré le 6 sept. 2026)

    Le rapport annonçait une action, jamais un fait. Sur un processus où
    `configure(rescan_event=None)` — aucune boucle de scan câblée :

    ```text
    kicked = False                      <- RIEN n'a été déclenché
    prices   → « relancé — recalcul complet en cours (≈10-30 s) »
    weekly   → « relancé — recalcul complet en cours (≈10-30 s) »
    ai       → « relancé — recalcul complet en cours (≈10-30 s) »
    news     → « cycle forcé — nouvelles fraîches sous ≈60 s »
    calendar → « cycle forcé — la boucle earnings se réveille immédiatement »
    ```

    Trois promesses de recalcul « en cours » sans exécutant, et deux cycles
    « forcés » vers des boucles dont rien n'atteste l'existence : poser un
    `threading.Event` réussit toujours, y compris quand personne ne l'attend.
    C'est l'invariant 6 — une capacité sans exécuteur réel se nomme, elle ne se
    déguise pas en automatisation en attente.

    Chaque ligne porte donc `executant`, et la phrase suit la mesure :
    `evenement_de_scan` (l'objet est câblé), `boucle_a_l_ecoute` (une boucle a
    signalé son attente via `wait_force`), `aucun_executant_observe`, `demo`
    ou `non_applicable`.
    """
    asked = [d for d in (domains or ['all']) if d]
    all_ = 'all' in asked
    doms = _domains()
    lines = []
    kicked = False
    scan_cable = _CFG['rescan_event'] is not None
    for k, d in doms.items():
        if not all_ and k not in asked:
            continue
        before = d['freshness']
        if k in ('prices', 'ai', 'weekly', 'options' if _CFG['demo'] else '') and not kicked:
            ev = _CFG['rescan_event']
            if ev is not None:
                ev.set()
                kicked = True
        if k in ('prices', 'ai', 'weekly'):
            executant = 'evenement_de_scan' if scan_cable else 'aucun_executant_observe'
            action = ('relancé — recalcul complet en cours (≈10-30 s)' if scan_cable
                      else 'NON_IMPLÉMENTÉ ici — aucune boucle de scan n\'est câblée '
                           'dans ce processus : rien n\'a été relancé')
        elif k == 'options':
            executant = ('demo' if _CFG['demo']
                         else 'boucle_a_l_ecoute' if boucle_a_l_ecoute('options')
                         else 'aucun_executant_observe')
            action = ('relancé avec le scan (démo)' if _CFG['demo']
                      else 'planifié au prochain cycle options (≤5 min, chaînes réelles)')
        elif k in ('news', 'calendar'):
            if _CFG['demo']:
                executant, action = 'demo', 'indisponible en démo (aucun réseau)'
            else:
                force_event(k).set()
                ecoute = boucle_a_l_ecoute(k)
                executant = 'boucle_a_l_ecoute' if ecoute else 'aucun_executant_observe'
                if ecoute:
                    action = ('cycle forcé — nouvelles fraîches sous ≈60 s' if k == 'news'
                              else 'cycle forcé — la boucle earnings se réveille immédiatement')
                else:
                    #  Le signal EST posé (c'est mesuré) ; ce qui ne l'est pas,
                    #  c'est qu'un exécutant le consomme. On dit les deux.
                    action = ('signal posé, mais aucune boucle %s n\'a signalé '
                              'qu\'elle écoute dans ce processus : rien ne sera '
                              'forcé tant qu\'elle ne tourne pas' % k)
        else:
            executant = 'non_applicable'
            action = 'cache hebdo — se régénère à l\'ouverture des fiches'
        lines.append({'domain': k, 'icon': d['icon'], 'label': d['label'],
                      'count': d['count'], 'before': before, 'action': action,
                      'state': d['state'], 'executant': executant})
    _LAST_REPORT.update({'ts': round(time.time()), 'requested': asked, 'lines': lines})
    return {'ok': True, 'kicked': kicked, 'requested': asked, 'report': _LAST_REPORT}


def report():
    """Le dernier rapport de synchronisation."""
    return _LAST_REPORT


__all__ = ['configure', 'status', 'refresh', 'report', 'mode', 'calculate_freshness',
           'force_event', 'wait_force', 'boucle_a_l_ecoute']
