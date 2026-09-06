"""
LOT 171 — Caractérisation de la couche HTTP Position Intelligence
(`vertex/app/routes/positions_api.py` — 4 endpoints à ZÉRO test :
/api/positions/state, /report, /audit, /reconcile + /<id>/changes).
Les moteurs sous-jacents (repository, recalculator, audit, reconciler)
ont 41 tests directs ; ceux-ci figent le CÂBLAGE HTTP et son honnêteté :
desk vide/corrompu → réponses honnêtes, IBKR hors ligne → aucune clôture
automatique, introuvable → erreur explicite. Les changer devient une
décision explicite.
"""
import json

import pytest

import terminal
from vertex.app.state import scan_state
from vertex.services import persist


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(persist, 'cache_path', lambda name: str(tmp_path / name))
    yield terminal.app.test_client()
    scan_state.setdefault('detail', {}).pop('TSTP', None)


def _desk(client_trades):
    persist.save_json('desk_data.json', {'ts': 1, 'data': {
        'myTrades': json.dumps(client_trades)}})


def _one_stock():
    # coût 1500 / qty 10 → PRU 150 ; cible 180 déjà dépassée au prix scan 200.
    _desk([{'id': 'p1', 'sym': 'TSTP', 'type': 'STK', 'qty': 10, 'cost': 1500,
            'added': '2026-01-01',
            'entrySnap': {'stop': 140, 'tgt': 180, 'thesis': 'x'}}])
    scan_state.setdefault('detail', {})['TSTP'] = {'price': 200.0}


# ── /api/positions/state : l'état recalculé, jamais un chiffre inventé ───────

def test_state_desk_vide_honnete_jamais_zero_invente(client):
    _desk([])
    d = client.get('/api/positions/state').get_json()
    assert d['live'] is False                       # pas d'IBKR en test → dit
    assert d['positions'] == []
    pf = d['portfolio']
    assert pf['stocks_count'] == 0 and pf['options_count'] == 0
    assert pf['unrealized_pnl'] is None             # absent = None, jamais 0
    assert pf['delta_global'] is None and pf['theta_global'] is None
    assert pf['positions_needing_action'] == []


def test_state_position_reelle_recalculee_au_prix_du_scan(client):
    _one_stock()
    d = client.get('/api/positions/state').get_json()
    p = d['positions'][0]
    assert p['source'] == 'MANUAL' and p['is_readonly'] is True
    assert p['current_price'] == 200.0              # prix RÉEL du scan
    assert p['unrealized_pnl'] == 500.0             # (200 − 150) × 10
    na = d['portfolio']['positions_needing_action'][0]
    # Cible dépassée → statut TARGET_REACHED, action DESCRIPTIVE « SÉCURISER »
    # mais décision ATTENDRE : Vertex n'exécute JAMAIS (lecture seule).
    assert na['status'] == 'TARGET_REACHED'
    assert na['action'] == 'SÉCURISER'
    assert na['decision'] == 'ATTENDRE'
    assert na['priority'] == 'P1_HIGH'


def test_state_desk_corrompu_pas_de_crash(client):
    persist.save_json('desk_data.json', {'ts': 1, 'data': {'myTrades': '{corrompu'}})
    r = client.get('/api/positions/state')
    assert r.status_code == 200
    assert r.get_json()['positions'] == []          # illisible → vide honnête


# ── /report et /reconcile : le courtier n'est JAMAIS lu ──────────────────────

def test_report_courtier_jamais_lu_conserve_les_locales(client):
    _one_stock()
    r = client.get('/api/positions/report').get_json()
    assert r['ibkr_online'] is False
    assert r['positions_detected'] == 1
    assert r['closed_positions_detected'] == 0
    assert 'aucune clôture automatique' in r['note']


def test_la_cause_servie_est_la_frontiere_et_non_une_panne_reseau(client):
    """MESURE (processus rejouant la configuration live : socket connectée,
    ticks temps réel frais) : `ibkr_connected=True`, `ibkr_live=True` sur
    /healthz, et EN MÊME TEMPS « IBKR hors ligne » servi par ces deux routes.

    Le littéral `ibkr_online=False` n'est pas un état de session mesuré, c'est
    la frontière produit (IBKR = données de marché uniquement). Servir une
    absence VOLONTAIRE sous la cause d'une PANNE réseau confond deux choses que
    l'invariant 5 exige de garder distinctes, et « aucune clôture automatique »
    seul laissait entendre qu'une reprise viendrait au retour d'IBKR — que
    l'invariant 3 interdit définitivement.
    """
    _one_stock()
    for route in ('/api/positions/report', '/api/positions/reconcile'):
        r = client.get(route).get_json()
        assert r['broker_positions_read'] is False, route
        assert r['boundary'] == 'MARKET_DATA_ONLY', route
        assert 'jamais lues' in r['note'], route
        assert 'hors ligne' not in r['note'], (
            '%s affirme une panne de session alors que la session peut être '
            'vivante : la cause servie est inventée' % route)


def test_reconcile_courtier_jamais_lu_zero_reparation(client):
    _one_stock()
    r = client.get('/api/positions/reconcile').get_json()
    assert r['ibkr_online'] is False
    assert r['issues'] == [] and r['repairs_required'] == 0


# ── /audit : intégrité ───────────────────────────────────────────────────────

def test_audit_desk_vide_healthy(client):
    _desk([])
    a = client.get('/api/positions/audit').get_json()
    assert a['status'] == 'HEALTHY'
    assert a['positions_checked'] == 0 and a['findings'] == []


# ── /<id>/changes : baseline puis diff, introuvable explicite ────────────────

def test_changes_introuvable_erreur_explicite_http_200(client):
    # COMPORTEMENT DOCUMENTÉ : l'introuvable répond 200 avec une erreur
    # explicite (pas 404) — le client UI lit `error` sans casse réseau.
    r = client.get('/api/positions/inconnue/changes')
    assert r.status_code == 200
    d = r.get_json()
    assert d == {'error': 'position introuvable', 'changed': False}


def test_changes_baseline_puis_diff_majeur_et_snapshot_ecrit(client, tmp_path):
    _one_stock()
    d1 = client.get('/api/positions/p1/changes').get_json()
    assert d1['changed'] is True                    # 1er appel = baseline
    cp = next(c for c in d1['changes'] if c['field'] == 'current_price')
    assert cp['before'] is None and cp['after'] == 200.0
    assert cp['source'] == 'scan'
    assert (tmp_path / 'position_snap_p1.json').exists()   # snapshot persisté
    scan_state['detail']['TSTP'] = {'price': 210.0}
    d2 = client.get('/api/positions/p1/changes').get_json()
    cp2 = next(c for c in d2['changes'] if c['field'] == 'current_price')
    assert cp2['before'] == 200.0 and cp2['after'] == 210.0
    assert cp2['change_pct'] == 5.0
    assert cp2['materiality'] == 'MAJOR'            # ≥ seuil → majeur


# ── /api/portfolio/stress : desk corrompu → refus honnête ────────────────────

def test_stress_desk_corrompu_vide_honnete(client):
    persist.save_json('desk_data.json', {'ts': 1, 'data': {'myTrades': '{corrompu'}})
    d = client.get('/api/portfolio/stress').get_json()
    assert d['empty'] is True and d['positions'] == []
    assert 'aucune position action avec prix réel' in d['reason']
    assert d['generator'] == 'deterministic'


# ── Invariant produit : la couche HTTP est bien LECTURE SEULE ────────────────

def test_module_routes_sans_verbe_d_ordre():
    import inspect
    from vertex.app.routes import positions_api
    src = inspect.getsource(positions_api).lower()
    for verb in ('placeorder', 'place_order', 'submit_order', 'transmit'):
        assert verb not in src
