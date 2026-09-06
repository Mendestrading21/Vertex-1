"""
LOT 149 — Caractérisation étendue du prisme marché
(`vertex/engines/market_lens.py`, ratio 0.66 — source unique du score
marché /100, servie par feeds.py, decision_api.py et command.py) et
des statistiques d'agrégation (`vertex/engines/stats.py`, ratio 0.77 —
Spearman de l'edge + médianes de valorisation par secteur).

Les tests existants figent les chemins dorés ; ces tests figent les
bornes exactes, les gardes et les comportements limites observés —
les changer devient une décision explicite.
"""

from vertex.engines import market_lens as ml
from vertex.engines import stats


# ═══ market_lens.climate : bornes EXACTES des bandes ═══

def test_climat_arithmetique_exacte_du_cas_porteur():
    # TREND 35 + RISK-ON 25 + breadth 70 → 18 + calme 15 = 93.
    c = ml.climate({'spy_regime': 'TREND', 'roro': 'RISK-ON',
                    'vix_band': 'calme', 'breadth': {'above50': 70}})
    assert c == {'score': 93, 'label': 'FAVORABLE', 'col': c['col']}


def test_climat_borne_favorable_65_proprietaire_unique():
    """CONSTAT 48 — la borne FAVORABLE avait TROIS propriétaires divergents.

    Ce test épinglait auparavant 62 en DOCUMENTANT la divergence (« le tilt de
    strategy_fit exige 65 sur la même formule »). Documenter une contradiction
    ne la corrige pas : mesuré avec mc={'spy_regime':'TREND','roro':'RISK-ON',
    'vix_band':'stress'}, above50 ∈ {0, 4, 8} donnait des scores 62/63/64
    étiquetés FAVORABLE par `market_lens.climate` et NEUTRE par
    /api/market/summary, au même instant sur la même donnée — une métrique,
    deux verdicts. 65 est retenu parce que c'est la borne des deux propriétaires
    réellement servis à l'écran : le comportement affiché ne bouge pas, seule la
    bande 62-64 du JSON /api/decision s'aligne. La borne vit désormais dans
    `CLIMAT_FAVORABLE_MIN` pour que la dérive ne puisse pas se reproduire.
    """
    c65 = ml.climate({'spy_regime': 'TREND', 'roro': None,
                      'vix_band': 'calme', 'breadth': {'above50': 12}})
    c64 = ml.climate({'spy_regime': 'TREND', 'roro': None,
                      'vix_band': 'calme', 'breadth': {'above50': 8}})
    assert c65['score'] == 65 and c65['label'] == 'FAVORABLE'
    assert c64['score'] == 64 and c64['label'] == 'NEUTRE'
    assert ml.CLIMAT_FAVORABLE_MIN == 65


def test_climat_feu_marche_partage_la_borne_du_label():
    """CONSTAT 48 — `lights['market']` était un QUATRIÈME propriétaire (62).

    Un feu « marché » vert sur un climat étiqueté NEUTRE se lisait comme deux
    lectures contradictoires du même score dans le même dictionnaire.
    """
    at64 = {'spy_regime': 'TREND', 'roro': None, 'vix_band': 'calme',
            'breadth': {'above50': 8}}
    at65 = {'spy_regime': 'TREND', 'roro': None, 'vix_band': 'calme',
            'breadth': {'above50': 12}}
    S = [{'sector': 'A', 'avg_score': 80}]
    assert ml.build(market=at64, sectors=S, sector_name='A',
                    stock_pct=50)['lights']['market'] is False
    assert ml.build(market=at65, sectors=S, sector_name='A',
                    stock_pct=50)['lights']['market'] is True


def test_climat_largeur_absente_est_distincte_d_une_largeur_a_50():
    """CONSTAT 30 — l'absence de largeur était indiscernable d'une mesure à 50.

    MESURE d'origine, base={'spy_regime':'NEUTRAL','roro':'RISK-ON',
    'vix_band':'calme'} :
        breadth vide  → {'score': 70, 'label': 'FAVORABLE', 'col': '#22C55E'}
        above50=None  → {'score': 70, 'label': 'FAVORABLE', 'col': '#22C55E'}
        above50=50    → {'score': 70, 'label': 'FAVORABLE', 'col': '#22C55E'}
        above50=0     → 58 NEUTRE   |   above50=100 → 83 FAVORABLE
    Identiques au bit près alors que la composante participation pèse 25 points
    sur 100 et peut faire basculer le label. Chemin atteignable : un scan
    partiel laisse `breadth={}` (vertex/market/context.py:34, bloc de calcul
    sous `except Exception: pass`) pendant que régime, RORO et VIX restent
    renseignés — le MÊME dictionnaire disait alors honnêtement
    « participation ?% » dans le verdict tout en servant un label chiffré dérivé
    d'une participation inventée à 50.
    """
    base = {'spy_regime': 'NEUTRAL', 'roro': 'RISK-ON', 'vix_band': 'calme'}
    vide = ml.climate(dict(base, breadth={}))
    none = ml.climate(dict(base, breadth={'above50': None}))
    mesure = ml.climate(dict(base, breadth={'above50': 50}))
    # Le score n'est pas retouché : seule la COUVERTURE devient lisible.
    assert vide['score'] == none['score'] == mesure['score'] == 70
    assert vide != mesure and none != mesure
    for absent in (vide, none):
        assert absent['breadth_status'] == 'MISSING'
        assert absent['partiel'] is True
        assert 'partiel' in absent['note']
    # Couverture complète → forme historique STRICTE, aucun marqueur parasite.
    assert set(mesure) == {'score', 'label', 'col'}


def test_climat_borne_dangereux_40_exacte():
    c40 = ml.climate({'spy_regime': 'NEUTRAL', 'roro': None,
                      'vix_band': None, 'breadth': {'above50': 8}})
    c39 = ml.climate({'spy_regime': 'NEUTRAL', 'roro': None,
                      'vix_band': None, 'breadth': {'above50': 4}})
    assert c40['score'] == 40 and c40['label'] == 'NEUTRE'
    assert c39['score'] == 39 and c39['label'] == 'DANGEREUX'


def test_climat_sans_marche_none_dict_vide_compris():
    # None ET {} (falsy) → None : pas de climat inventé sans données.
    assert ml.climate(None) is None
    assert ml.climate({}) is None


# ═══ market_lens.sector_standing : tiers porteur et honnêteté ═══

def test_secteur_tiers_superieur_porteur():
    S = [{'sector': 'A', 'avg_score': 80}, {'sector': 'B', 'avg_score': 'zz'},
         {'sector': 'C', 'avg_score': 60}, {'sector': 'D', 'avg_score': 50},
         {'sector': 'E', 'avg_score': 40}, {'sector': 'F', 'avg_score': 30}]
    # n=6 → tiers = 2 premiers rangs porteurs.
    assert ml.sector_standing(S, 'A')['in_favor'] is True
    assert ml.sector_standing(S, 'C')['in_favor'] is True
    assert ml.sector_standing(S, 'D')['in_favor'] is False


def test_secteur_score_non_numerique_classe_dernier_honnete():
    S = [{'sector': 'A', 'avg_score': 80}, {'sector': 'B', 'avg_score': 'zz'},
         {'sector': 'C', 'avg_score': 60}]
    b = ml.sector_standing(S, 'B')
    assert b['rank'] == 3            # score illisible → trié en dernier
    assert b['avg_score'] is None    # jamais un chiffre inventé
    assert b['in_favor'] is False


def test_secteur_inconnu_none_et_petit_univers():
    S2 = [{'sector': 'A', 'avg_score': 80}, {'sector': 'B', 'avg_score': 40}]
    assert ml.sector_standing(S2, 'X') is None       # secteur hors scan
    # n=2 → max(1, 2//3)=1 : seul le rang 1 est porteur.
    assert ml.sector_standing(S2, 'A')['in_favor'] is True
    assert ml.sector_standing(S2, 'B')['in_favor'] is False


# ═══ market_lens.build : frontières d'alignement ═══

def test_frontiere_titre_fort_70_stricte():
    bull = {'spy_regime': 'TREND', 'roro': 'RISK-ON',
            'vix_band': 'calme', 'breadth': {'above50': 70}}
    S = [{'sector': 'A', 'avg_score': 80}, {'sector': 'E', 'avg_score': 40}]
    assert ml.build(market=bull, sectors=S, sector_name='E',
                    stock_pct=69.9)['lights']['stock'] is False
    assert ml.build(market=bull, sectors=S, sector_name='E',
                    stock_pct=70)['lights']['stock'] is True


def test_deux_verts_partiellement_aligne_meme_si_titre_fort():
    # 2 feux verts (dont le titre) → « partiellement aligné », PAS
    # « à contre-courant » (réservé au titre fort SEUL).
    bull = {'spy_regime': 'TREND', 'roro': 'RISK-ON',
            'vix_band': 'calme', 'breadth': {'above50': 70}}
    S = [{'sector': 'A', 'avg_score': 80}, {'sector': 'E', 'avg_score': 40}]
    r = ml.build(market=bull, sectors=S, sector_name='E', stock_pct=90)
    assert r['lights'] == {'market': True, 'sector': False, 'stock': True}
    assert r['alignment'] == 'partiellement aligné' and r['tone'] == 'blue'


# ═══ stats.spearman : frontières et limite documentée ═══

def test_spearman_frontiere_8_points_exacte():
    assert stats.spearman(list(range(7)), list(range(7))) is None
    assert stats.spearman(list(range(8)), list(range(8))) == 1.0


def test_spearman_serie_constante_limite_documentee():
    # Comportement limite DOCUMENTÉ : les rangs sont ordinaux (double
    # argsort, tri stable) — pas de rangs fractionnaires pour les
    # égalités. Une série CONSTANTE reçoit donc les rangs 0..n-1 dans
    # l'ordre d'apparition et « corrèle » parfaitement avec une série
    # croissante (1.0 au lieu d'un indéfini statistique). Pathologique
    # en réel (scores d'edge jamais tous identiques) ; le changer =
    # décision explicite (rangs fractionnaires).
    assert stats.spearman([5] * 10, list(range(10))) == 1.0


# ═══ stats.sector_medians : filtres de bornes et exclusions ═══

def test_medianes_bornes_pe_strictes_0_et_250_exclus():
    by = {'B': {'sector': 'S2', 'pe': 250, 'fwd_pe': 20},
          'C': {'sector': 'S2', 'pe': -5, 'fwd_pe': 10}}
    sec = stats.sector_medians(by)
    # pe=250 (borne haute stricte) et pe=-5 exclus → median_pe None ;
    # fwd_pe valides → 15.0 ; n compte TOUS les membres du secteur.
    assert sec['S2']['median_pe'] is None
    assert sec['S2']['median_fwd_pe'] == 15.0
    assert sec['S2']['n'] == 2


def test_medianes_secteur_sans_aucun_pe_entierement_absent():
    # Un secteur sans pe NI fwd_pe n'apparaît pas du tout — même si
    # marge/croissance existent (pas de fiche valorisation sans
    # valorisation).
    by = {'A': {'sector': 'S1', 'margin': 0.2, 'growth': 0.1}}
    assert stats.sector_medians(by) == {}
