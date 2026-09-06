"""
LOT 164 — Caractérisation du risque de panier
(`vertex/portfolio/legacy_basket_risk.py` — VIVANT : servi par
analysis_api, command et risk_engine ; 0 test direct). Le « no-trade
de concentration » : corrélations, HHI, exposition sectorielle,
sizing inverse-vol capé.

Ces tests figent les gardes, les drapeaux et le fail-open sur erreur
— les changer devient une décision explicite. Séries déterministes
(graines fixes).

DEUX limites autrefois figées ici ont été LEVÉES, mesures à l'appui :
le cap infaisable ne tronque plus l'allocation (la somme des poids
valait 0,15 × n sous 7 lignes) et la concentration sectorielle se
détecte enfin sur un petit panier (2 titres 100 % semi-conducteurs
étaient annoncés à 30 %, sous la limite de 40 %). Les tests qui les
documentaient sont conservés, retournés en assertions de la nouvelle
vérité : la preuve reste, la limite a disparu.
"""

import numpy as np

from vertex.portfolio import legacy_basket_risk as lbr


def _detail(series_map):
    return {s: {'series': {'close': list(v)}} for s, v in series_map.items()}


def _walk(seed, n=120):
    return np.cumsum(np.random.default_rng(seed).normal(0, 1, n)) + 200


# ── Gardes : panier trop petit, séries courtes exclues ───────────────────────

def test_panier_trop_petit_honnete_sans_blocage():
    r = lbr.build([], {})
    assert r == {'n': 0, 'symbols': [], 'flags': [], 'no_new_risk': False,
                 'note': 'panier trop petit pour une analyse de corrélation'}


def test_serie_trop_courte_exclue_moins_de_40_points():
    base = _walk(9)
    r = lbr.build(['NVDA', 'AMD'], _detail({'NVDA': base, 'AMD': base[:30]}))
    assert 'panier trop petit' in r['note']    # AMD exclu → 1 seul titre


# ── Drapeau de corrélation : le no-trade du panier cloné ─────────────────────

def test_paire_quasi_identique_correlation_elevee_bloque():
    rng = np.random.default_rng(9)
    base = _walk(9)
    d = _detail({'NVDA': base, 'AMD': base + rng.normal(0, 0.3, 120)})
    r = lbr.build(['NVDA', 'AMD'], d)
    assert r['avg_corr'] > 0.65
    assert 'correlation_panier_elevee' in r['flags']
    #  Les deux autres drapeaux ne sont pas apparus par hasard : 2 lignes qui
    #  somment à 100 % pèsent 50 % chacune (> plafond 15 %) et sont toutes deux
    #  Semiconducteurs (> plafond 40 %). Avant la renormalisation, l'API
    #  annonçait 30 % d'exposition sectorielle et n'armait aucun des deux.
    assert set(r['flags']) == {'correlation_panier_elevee',
                               'concentration_sectorielle', 'ligne_trop_grosse'}
    assert r['no_new_risk'] is True
    assert r['top_pair'][:2] == ['NVDA', 'AMD']   # la paire coupable expliquée


def test_panier_diversifie_decorrele_sans_drapeau_de_correlation():
    d = _detail({'NVDA': _walk(1), 'MSFT': _walk(2), 'JPM': _walk(3),
                 'XOM': _walk(4), 'LLY': _walk(5)})
    r = lbr.build(['NVDA', 'MSFT', 'JPM', 'XOM', 'LLY'], d)
    assert abs(r['avg_corr']) < 0.3
    assert 'correlation_panier_elevee' not in r['flags']
    assert 'concentration_sectorielle' not in r['flags']
    #  5 lignes ne peuvent pas peser 15 % chacune ET représenter le panier :
    #  le plafond est infaisable, donc dépassé, donc DIT. Avant, la somme
    #  tombait à 75 % et la diversification affichait 89 au lieu de 80.
    #  Le drapeau est STRUCTUREL : cinq lignes ne peuvent pas peser 15 % chacune.
    #  Il est DIT, mais il ne bloque plus le risque neuf — sinon Vertex
    #  interdirait d'ajouter une ligne exactement quand ajouter est le remede a
    #  la concentration (regression mesuree le 2026-09-06 par le controle
    #  adverse ; voir tests/test_risque_panier_flags.py).
    assert r['flags'] == ['ligne_trop_grosse']
    assert r['flags_structurels'] == ['ligne_trop_grosse'] and r['flags_bloquants'] == []
    assert r['no_new_risk'] is False
    assert r['diversification'] == 80             # 1 − HHI de 5 lignes égales


# ── LIMITE LEVÉE : le cap infaisable est renormalisé, plus tronqué ──────────

def test_cap_infaisable_renormalise_a_100_et_dit_le_depassement():
    """MESURE d'origine (poids inverse-vol égaux, cap 15 %) : n=1 somme 0,15 ·
    n=2 0,30 · n=3 0,45 · n=4 0,60 · n=5 0,75 · n=6 0,90 — `_cap_weights`
    sortait par `break` en laissant `n × cap`, contre sa propre docstring.
    Sur 5 titres, l'allocation servie totalisait 75 % du panier.

    Désormais la somme vaut 100 % et le dépassement du plafond par ligne
    (20 % > 15 %) est DIT par `ligne_trop_grosse` au lieu d'être masqué par
    une allocation tronquée."""
    d = _detail({'NVDA': _walk(1), 'MSFT': _walk(2), 'JPM': _walk(3),
                 'XOM': _walk(4), 'LLY': _walk(5)})
    r = lbr.build(['NVDA', 'MSFT', 'JPM', 'XOM', 'LLY'], d)
    assert round(sum(r['weights'].values()), 1) == 100.0
    assert r['max_weight'] == 20.0                       # 1/5 : le cap est infaisable
    assert 'ligne_trop_grosse' in r['flags']


def test_concentration_sectorielle_detectee_sur_petit_panier_mono_secteur():
    """MESURE d'origine : `POST /api/risk {"symbols":["NVDA","AMD"]}` rendait
    `sectors {"Semiconducteurs": 30.0}`, `max_sector 30.0`, `flags []`,
    `no_new_risk false` — 100 % d'exposition annoncée à 30 %, donc sous la
    limite de 40 % affichée dans la même carte. Le gate ne pouvait
    structurellement jamais s'armer sur un panier de 2 à 6 lignes."""
    rng = np.random.default_rng(9)
    base = _walk(9)
    r = lbr.build(['NVDA', 'AMD'],
                  _detail({'NVDA': base, 'AMD': base + rng.normal(0, 0.3, 120)}))
    assert r['sectors'] == {'Semiconducteurs': 100.0}
    assert r['max_sector'] == 100.0
    assert 'concentration_sectorielle' in r['flags']
    assert r['no_new_risk'] is True


def test_les_poids_somment_a_100_pour_tout_panier_de_2_a_12_lignes():
    """Non-régression du défaut mesuré : la somme des poids ne doit plus
    dépendre de la TAILLE du panier (0,15 × n sous 7 lignes)."""
    series = {'S%02d' % i: _walk(i) for i in range(1, 13)}
    for n in range(2, 13):
        syms = sorted(series)[:n]
        r = lbr.build(syms, _detail({s: series[s] for s in syms}))
        #  Tolérance 0,5 : les poids sont publiés arrondis à 0,1 % (3 lignes
        #  égales → 33,3 × 3 = 99,9). C'est l'arrondi d'affichage, pas la
        #  troncature mesurée, qui valait 0,15 × n (45 % pour 3 lignes).
        assert abs(sum(r['weights'].values()) - 100.0) <= 0.5, n
        assert abs(sum(r['sectors'].values()) - 100.0) <= 0.5, n


def test_erreur_fail_open_documente():
    # LIMITE DOCUMENTÉE : une entrée illisible → dict d'erreur avec
    # no_new_risk False (FAIL-OPEN : l'analyse de panier ne bloque pas
    # le risque quand elle ne peut pas conclure — l'erreur est exposée).
    bad = {'NVDA': {'series': {'close': ['x'] * 50}},
           'AMD': {'series': {'close': list(_walk(9))}}}
    r = lbr.build(['NVDA', 'AMD'], bad)
    assert 'error' in r and r['error'].startswith('ValueError')
    assert r['no_new_risk'] is False


# ── _cap_weights : redistribution ────────────────────────────────────────────

def test_cap_weights_redistribue_et_somme_1_quand_faisable():
    w = lbr._cap_weights([0.5, 0.3, 0.1, 0.1], 0.3)
    assert round(float(w.sum()), 3) == 1.0
    # tolérance d'itération : léger dépassement possible (≤ 1 %)
    assert float(w.max()) <= 0.31
    assert list(lbr._cap_weights([0, 0], 0.15)) == [0.0, 0.0]  # tout nul → nul
