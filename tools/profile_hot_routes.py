"""tools/profile_hot_routes.py — PROFILAGE des routes chaudes (SKYLER LOT 50).

Mesure p50/p95 (time.perf_counter, N requêtes après chauffe) des routes
chaudes et des 8 pages HTML sur le serveur démo local, PUIS micro-bench
in-process des étages du cœur décisionnel (build_packet / score40 /
red_team.review / decide) sur fixtures FIXES — pour vérifier l'hypothèse
« double build_packet + score40 recalculé » AVANT toute optimisation.

Usage : serveur démo lancé (DEMO=1 NO_IBKR=1 START_ON_IMPORT=1), puis
  python tools/profile_hot_routes.py
Sortie : tableau texte (ms) — aucune écriture, aucun changement produit.
"""
import os
import statistics
import sys
import time
import urllib.request

# exécutable depuis n'importe où : la racine du repo porte le paquet vertex
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#  PORT DE MESURE PAR DÉFAUT : 5003, l'instance de VÉRIFICATION.
#
#  Mesuré le 2026-09-06 : ces outils visaient 5002 par défaut, c'est-à-dire, sur
#  le poste de l'auteur, l'instance RÉELLE branchée sur le courtier et protégée
#  par un code d'accès. Un outil de mesure qui frappe l'instance de travail lui
#  vole des requêtes, la ralentit, et sur une machine tierce sonde un port dont
#  il ne sait rien. L'instance de vérification (5003) existe précisément pour
#  ça : sans IBKR, sans code, sans desk. `VERTEX_MESURE_BASE` reste le moyen de
#  viser autre chose, explicitement.
BASE = os.environ.get('VERTEX_MESURE_BASE', 'http://127.0.0.1:5003')
WARMUP = 2
N = 20

ROUTES = [
    '/api/skyler/AAPL',
    '/api/skyler/memory',
    '/api/skyler/memory/export',
    '/api/command',
    '/api/market/summary',
    '/', '/markets', '/opportunities', '/analysis',
    '/portfolio', '/options', '/journal', '/system',
]


def _get(path):
    t0 = time.perf_counter()
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        r.read()
        status = r.status
    return (time.perf_counter() - t0) * 1000.0, status


def bench_routes():
    print('%-28s %8s %8s %8s  %s' % ('cible', 'p50 ms', 'p95 ms', 'max ms', 'HTTP'))
    rows = []
    for path in ROUTES:
        for _ in range(WARMUP):
            _get(path)
        samples, status = [], None
        for _ in range(N):
            ms, status = _get(path)
            samples.append(ms)
        samples.sort()
        p50 = statistics.median(samples)
        p95 = samples[max(0, int(round(0.95 * N)) - 1)]
        print('%-28s %8.1f %8.1f %8.1f  %s' % (path, p50, p95, samples[-1], status))
        rows.append((path, p50, p95))
    return rows


def bench_engine_stages():
    """Micro-bench in-process des étages du cœur — fixtures FIXES (mêmes formes
    que tests/test_skyler_core.py), 200 itérations, moyenne en ms."""
    from vertex.engines import red_team as RT
    from vertex.engines import skyler_core as SK

    detail = {'price': 100.0, 'score': 72, 'verdict': 'ACHETER', 'trend': 80,
              'rsi': 55, 'regime': 'TREND', 'setup_quality': 70, 'atr_pct': 2.0,
              'confidence': 62,
              'plan': {'entry': 100.0, 'stop': 94.0, 'tp1': 106.0, 'tp2': 112.0,
                       'tp3': 118.0, 'rr': 3.0, 'rr_res': 3.0,
                       'resistance': 115.0, 'atr': 2.0}}
    market = {'regime': {'label': 'TREND_UP', 'confidence': 0.7,
                         'adjustments': {'new_risk_allowed': True},
                         'transition': {'from': None, 'to': 'TREND_UP',
                                        'changed': None}},
              'conflicts': [], 'as_of': '10:00:00',
              'dimensions': {'vix': {'value': 15.0, 'status': 'LIVE'}}}
    events = {'events': [{'kind': 'earnings', 'label': 'Resultats TST', 'dte': 12,
                          'category': 'fact', 'source': 'calendar.earnings'}],
              'n': 1, 'revisions': {'available': False}}

    def timeit(label, fn, n=200):
        fn()                                   # chauffe
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        ms = (time.perf_counter() - t0) * 1000.0 / n
        print('%-28s %8.3f ms/appel' % (label, ms))
        return ms

    print()
    print('Micro-bench étages du cœur (fixtures fixes, moyenne sur 200) :')
    packet = SK.build_packet('TST', detail, market=market, events=events,
                             as_of='10:00:00')
    t_bp = timeit('build_packet', lambda: SK.build_packet(
        'TST', detail, market=market, events=events, as_of='10:00:00'))
    t_sc = timeit('score40', lambda: SK.score40(packet))
    t_rt = timeit('red_team.review', lambda: RT.review(packet, SK.score40(packet)))
    t_de = timeit('decide (complet)', lambda: SK.decide(
        'TST', detail, market=market, events=events, as_of='10:00:00'))
    dup = t_bp + t_sc                          # ce que la route paie EN DOUBLE
    print('%-28s %8.3f ms/appel  (build_packet + score40 dupliqués)'
          % ('surcoût double connu', dup))
    print('%-28s %7.1f %%       (surcoût / decide complet)'
          % ('part du surcoût', 100.0 * dup / t_de if t_de else 0.0))


if __name__ == '__main__':
    bench_routes()
    bench_engine_stages()
