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


def force_event(domain):
    """L'événement de forçage d'un domaine (créé au premier accès)."""
    ev = _FORCE.get(domain)
    if ev is None:
        ev = _FORCE[domain] = threading.Event()
    return ev


def wait_force(domain, timeout):
    """Attente interruptible pour les boucles : dort `timeout` s OU se réveille
    immédiatement si le Sync Center force le domaine. Renvoie True si forcé."""
    ev = force_event(domain)
    forced = ev.wait(timeout)
    if forced:
        ev.clear()
    return forced

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
    """
    asked = [d for d in (domains or ['all']) if d]
    all_ = 'all' in asked
    doms = _domains()
    lines = []
    kicked = False
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
            action = 'relancé — recalcul complet en cours (≈10-30 s)'
        elif k == 'options':
            action = ('relancé avec le scan (démo)' if _CFG['demo']
                      else 'planifié au prochain cycle options (≤5 min, chaînes réelles)')
        elif k == 'news':
            if _CFG['demo']:
                action = 'indisponible en démo (aucun réseau)'
            else:
                force_event('news').set()
                action = 'cycle forcé — nouvelles fraîches sous ≈60 s'
        elif k == 'calendar':
            if _CFG['demo']:
                action = 'indisponible en démo (aucun réseau)'
            else:
                force_event('calendar').set()
                action = 'cycle forcé — la boucle earnings se réveille immédiatement'
        else:
            action = 'cache hebdo — se régénère à l\'ouverture des fiches'
        lines.append({'domain': k, 'icon': d['icon'], 'label': d['label'],
                      'count': d['count'], 'before': before, 'action': action,
                      'state': d['state']})
    _LAST_REPORT.update({'ts': round(time.time()), 'requested': asked, 'lines': lines})
    return {'ok': True, 'kicked': kicked, 'requested': asked, 'report': _LAST_REPORT}


def report():
    """Le dernier rapport de synchronisation."""
    return _LAST_REPORT


__all__ = ['configure', 'status', 'refresh', 'report', 'mode', 'calculate_freshness',
           'force_event', 'wait_force']
