"""
LOT 174 — Caractérisation HTTP du TICKET DE PRÉPARATION D'ORDRE
(`vertex/app/routes/planning_api.py` — /api/planning/ticket, couvert
seulement par un test de robustesse aux grands nombres) et de la
RECHERCHE (`feeds.py` — /api/search, seule route de feeds à logique
propre, couverte seulement par un smoke 200). Le moteur order_ticket
a ses tests directs ; ceux-ci figent le CÂBLAGE HTTP : plan repris du
scan, overrides du body, refus honnêtes du dimensionnement, et le
DISCLAIMER READONLY qui ouvre chaque ticket.
"""
import pytest

import terminal
from vertex.app.state import scan_state


@pytest.fixture()
def client():
    scan_state.setdefault('detail', {})['TSTQ'] = {
        'price': 100.0,
        'plan': {'entry': 100.0, 'stop': 95.0, 'tp1': 106.0,
                 'tp2': 112.0, 'tp3': 118.0, 'rr_res': 3.0}}
    yield terminal.app.test_client()
    scan_state['detail'].pop('TSTQ', None)


def _ticket(client, **body):
    body.setdefault('symbol', 'TSTQ')
    return client.post('/api/planning/ticket', json=body).get_json()


# ── /api/planning/ticket : préparation READONLY, jamais une transmission ─────

def test_sans_symbole_400(client):
    r = client.post('/api/planning/ticket', json={})
    assert r.status_code == 400
    assert r.get_json() == {'error': 'symbol requis'}


def test_plan_du_scan_repris_et_dimensionnement_exact(client):
    # 100 k, risque 1 % = 1 000 ; risque unitaire 5 (100−95) → 200 actions.
    t = _ticket(client, symbol='tstq', account_value=100000, risk_pct=1)
    assert t['side'] == 'ACHAT' and t['is_option'] is False
    assert t['limit_price'] == 100.0                # entrée du plan du scan
    assert t['qty'] == 200
    assert t['sizing']['per_unit_risk'] == 5.0
    assert t['sizing']['capital_at_risk'] == 1000.0
    assert t['reward_risk'] == 3.0                  # rr_res du plan, transmis tel quel


def test_concentration_bloque_meme_avec_budget_de_risque_correct(client):
    # 200 × 100 = 20 000 = 20 % du compte > plafond 15 % : le ticket est
    # produit mais BLOQUÉ — le garde-fou de concentration prime sur le budget.
    t = _ticket(client, account_value=100000, risk_pct=1)
    assert t['blocked'] is True
    assert t['blockers'] == ['poids projeté 20.0 % > 15 %']


def test_body_prime_sur_le_plan_du_scan(client):
    t = _ticket(client, entry=200, stop=190, account_value=100000, risk_pct=1)
    assert t['limit_price'] == 200.0                # override du body
    assert t['sizing']['per_unit_risk'] == 10.0
    assert t['qty'] == 100                          # 1 000 / 10


def test_refus_honnetes_du_dimensionnement(client):
    # Sans compte : pas de sizing, pas de quantité inventée, pas de blocage.
    sans = _ticket(client)
    assert sans['qty'] is None and sans['sizing'] is None
    assert sans['blocked'] is False
    # Stop au-dessus de l'entrée : risque non défini → refus expliqué.
    inv = _ticket(client, entry=100, stop=105, account_value=100000, risk_pct=1)
    assert inv['qty'] is None
    assert inv['sizing']['reason'] == "stop au-dessus de l'entrée — risque non défini"
    # Option sans prime : impossible de dimensionner → refus expliqué.
    opt = _ticket(client, is_option=True, account_value=100000, risk_pct=1)
    assert opt['qty'] is None
    assert opt['sizing']['reason'] == 'prime indisponible — dimensionnement impossible'


def test_option_dimensionnee_sur_la_prime(client):
    # Budget 1 000 ; risque par contrat = prime 2.5 × 100 = 250 → 4 contrats.
    t = _ticket(client, is_option=True, premium=2.5, right='C', strike=105,
                expiry='2026-12-18', account_value=100000, risk_pct=1)
    assert t['is_option'] is True and t['qty'] == 4
    assert 'TYPE: OPTION C' in t['copy_text']
    assert 'STRIKE: 105' in t['copy_text']


def test_disclaimer_readonly_ouvre_chaque_ticket(client):
    # INVARIANT PRODUIT : le texte à copier commence par le rappel lecture
    # seule, et le stop est explicitement « non transmis ».
    t = _ticket(client, account_value=100000, risk_pct=1)
    assert t['readonly'] is True
    assert t['copy_text'].startswith('# PRÉPARATION UNIQUEMENT — Vertex est en '
                                     'lecture seule et ne transmet aucun ordre.')
    assert 'STOP (référence, non transmis)' in t['copy_text']
    assert t['disclaimer'] in t['copy_text']


# ── /api/search : la recherche de tickers ────────────────────────────────────

def test_recherche_vide_et_sous_chaine_insensible_casse(client):
    """Sans terme, la recherche EXPLIQUE au lieu de rendre une liste vide.

    Ce banc épinglait `== []`. Mesuré le 2026-09-06 en exerçant les 184 règles
    du runtime : une liste vide ne peut porter aucun motif, donc l'appelant ne
    pouvait pas distinguer « aucun terme fourni » de « aucun résultat » ni de
    « l'univers n'est pas chargé ». La forme AVEC résultats, elle, ne change
    pas — c'est celle dont un consommateur pourrait dépendre.
    """
    vide = client.get('/api/search').get_json()
    assert isinstance(vide, dict), vide
    assert vide['resultats'] == []
    assert 'q=' in vide['usage'], vide
    assert client.get('/api/search?q=aapl').get_json() == [{'ticker': 'AAPL'}]


def test_recherche_plafonnee_a_20(client):
    assert len(client.get('/api/search?q=A').get_json()) == 20  # cap dur


# ── Invariant produit : les modules sont bien LECTURE SEULE ──────────────────

def test_modules_sans_verbe_d_ordre():
    import inspect
    from vertex.app.routes import planning_api, feeds
    for mod in (planning_api, feeds):
        src = inspect.getsource(mod).lower()
        for verb in ('placeorder', 'submit_order', 'transmit('):
            assert verb not in src
