# -*- coding: utf-8 -*-
"""Un champ de liquidité ABSENT n'est jamais servi comme un zéro observé.

Le producteur du tableau d'options publie quatre témoins dans
`liquidity_coverage` — `bid_present`, `ask_present`, `volume_present`,
`open_interest_present` — précisément parce que `legacy_engine._i` et `_f`
convertissent un champ absent en `0` pour couper la propagation de NaN. Le
paquet porte même la phrase « champ absent ≠ zéro observé ; aucune liquidité
n'est imputée ».

Mesure du 2026-09-06, balayage du dépôt : **un seul** des quatre témoins avait
un lecteur (`volume_present`). Les trois autres étaient servis et jamais lus.
Conséquences mesurées, toutes sur des chiffres montrés à l'utilisateur :

- verdict de liquidité d'une structure : `o or 0.0` écrasait l'absence, la note
  affirmait « OI 0 » et le palier tombait à « Insuffisante » — la même faute que
  la sentinelle « spread 99.0 % » corrigée un tour plus tôt, sur l'autre axe ;
- portes du scanner : `_minimum_ok(0, 500)` rend `False`, un REJET affirmé, là
  où `_minimum_ok(None, 500)` rend `None`, « non mesurable » ;
- carte « OI moyen » : la moyenne intégrait des zéros imputés ;
- exposition gamma : un contrat sans intérêt ouvert reporté pesait 0 $, donc
  comme un contrat sans position ouverte, et le total ne disait pas combien de
  lignes n'avaient rien reporté.

Aucun réseau : contrats synthétiques, les deux états côte à côte.
"""
from vertex.options import board_fields as bf
from vertex.options import gex, horizon_scanners, overview, structure_verdict


def _contrat(present: bool, **extra):
    """Un contrat dont TOUS les champs valent zéro, reportés ou imputés.

    C'est le cas décisif : les deux contrats sont identiques champ pour champ,
    seuls les témoins changent. Tout écart de sortie vient donc du témoin.
    """
    c = {'sym': 'NVDA', 'type': 'CALL', 'strike': 100.0, 'exp': '2026-12-18',
         'oi': 0, 'vol': 0, 'bid': 0.0, 'ask': 0.0, 'delta': 0.8,
         'gamma': 0.02, 'iv': 0.30, 'dte': 100,
         'liquidity_coverage': {'bid_present': present, 'ask_present': present,
                                'volume_present': present,
                                'open_interest_present': present}}
    c.update(extra)
    return c


# ── 1. Les accesseurs ────────────────────────────────────────────────────────

def test_les_quatre_champs_distinguent_l_absence_du_zero():
    absent, reporte = _contrat(False), _contrat(True)
    assert (bf.open_interest(absent), bf.bid(absent),
            bf.ask(absent), bf.volume(absent)) == (None, None, None, None)
    assert (bf.open_interest(reporte), bf.bid(reporte),
            bf.ask(reporte), bf.volume(reporte)) == (0, 0.0, 0.0, 0)


def test_un_board_sans_temoin_ne_declare_ni_present_ni_absent():
    """Fixtures anciennes et board de démonstration : on ne sait pas, on le dit."""
    assert bf.couverture_liquidite({'oi': 5}) == {
        'bid_present': None, 'ask_present': None,
        'volume_present': None, 'open_interest_present': None}


# ── 2. Le verdict de liquidité ───────────────────────────────────────────────

def test_un_interet_ouvert_absent_ne_se_lit_pas_OI_zero():
    etat = structure_verdict.etat_liquidite(None, 2.0)
    assert 'non reporté' in etat['note'], etat['note']
    assert 'OI 0' not in etat['note']
    assert etat['oi_mesure'] is False
    #  Prudence conservée : sans OI reporté, aucun palier positif.
    assert etat['key'] == 'insuffisante'


def test_un_interet_ouvert_de_zero_REPORTE_reste_une_mesure():
    """Contre-épreuve : le correctif ne doit pas effacer un vrai zéro."""
    etat = structure_verdict.etat_liquidite(0, 2.0)
    assert 'OI 0' in etat['note'], etat['note']
    assert etat['oi_mesure'] is True


def test_le_verdict_lit_l_accesseur_et_non_le_champ_brut():
    board = [_contrat(False)]
    etat = structure_verdict.liquidite_strategie(
        board, 'NVDA', '2026-12-18', [{'type': 'CALL', 'strike': 100.0}])
    assert etat['oi_mesure'] is False, etat


# ── 3. Les portes du scanner ─────────────────────────────────────────────────

def test_une_porte_sur_un_champ_absent_rend_NON_MESURABLE_pas_REJET():
    absent = horizon_scanners._leaps_mandate(_contrat(False), None)
    reporte = horizon_scanners._leaps_mandate(_contrat(True), None)
    assert absent['oi_ok'] is None, (
        'un intérêt ouvert absent produisait un rejet affirmé : le scanner '
        'écartait le contrat pour une raison qu’il n’avait pas mesurée')
    assert reporte['oi_ok'] is False, 'un zéro REPORTÉ reste un rejet mesuré'


# ── 4. Les agrégats affichés ─────────────────────────────────────────────────

def test_la_moyenne_d_interet_ouvert_ignore_les_zeros_imputes():
    board = [_contrat(False), _contrat(True, oi=4000)]
    c = overview.summarize(board)
    compteurs = c.get('counters') or c
    assert compteurs['avg_oi'] == 4000.0, compteurs['avg_oi']
    assert compteurs['oi_reported_count'] == 1
    assert compteurs['oi_total_count'] == 2, (
        'sans le total, une moyenne sur un contrat se lit comme une moyenne '
        'sur tout le tableau')


def test_l_exposition_gamma_compte_les_lignes_sans_interet_ouvert():
    board = [_contrat(False), _contrat(True, strike=105.0, oi=1000)]
    r = gex.compute(board, spot=102.0)
    assert r['contracts_used'] == 1
    assert r['contracts_sans_oi_reporte'] == 1, (
        'un contrat sans intérêt ouvert reporté pesait 0 $ de gamma, donc '
        'exactement comme un contrat sans position ouverte, et rien ne le disait')


def test_aucun_consommateur_du_paquet_ne_lit_plus_l_interet_ouvert_brut():
    """Anti-régression de STRUCTURE sur les quatre sites corrigés."""
    import inspect
    for module in (structure_verdict, horizon_scanners, overview):
        src = inspect.getsource(module)
        assert "get('oi')" not in src, (
            '%s lit de nouveau `oi` brut : le zéro imputé revient dans un '
            'verdict, une porte ou une moyenne' % module.__name__)


# ── 5. L'écran ───────────────────────────────────────────────────────────────

def test_le_tableau_d_options_n_imprime_pas_un_interet_ouvert_impute():
    """La colonne « OI » lisait `c.oi` nu, comme la colonne « Vol » avant elle."""
    import os
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'vertex', 'static', 'vertex', 'js', 'charts', 'option-chain.js')
    with open(chemin, encoding='utf-8') as f:
        src = f.read()
    assert 'function oiObserve(' in src, (
        'le tableau n’a plus de lecteur honnête pour l’intérêt ouvert')
    assert "open_interest_present" in src
    assert "{ k: 'oi', label: 'OI', num: true, d: 0 }" not in src, (
        'la colonne OI est revenue à la lecture brute : un contrat sans '
        'intérêt ouvert reporté réimprime « 0 »')
    #  Le pied compte les lignes concernées, comme pour le volume.
    assert 'sans intérêt ouvert reporté' in src


def test_les_deux_colonnes_de_liquidite_emploient_le_meme_vocabulaire():
    """Deux mots pour un même état seraient deux autorités à l'écran."""
    import os
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'vertex', 'static', 'vertex', 'js', 'charts', 'option-chain.js')
    with open(chemin, encoding='utf-8') as f:
        src = f.read()
    assert src.count('sans volume reporté') == 1
    assert src.count('sans intérêt ouvert reporté') == 1
    assert src.count('n’est pas une observation') >= 2, (
        'les deux colonnes doivent expliquer le tiret de la même façon')
