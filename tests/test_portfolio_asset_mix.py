"""tests/test_portfolio_asset_mix.py — mix d'actifs et HONNÊTETÉ DE LA VALORISATION.

Deux mesures d'origine gèlent ce banc :

1. `/api/portfolio/context` rendait `total_value 4256.59` sur un desk de
   7 contrats MSFT + 2 contrats GOOG + 1 action KO, soit exactement
   `7 × 499,70 + 2 × 335,31 + 88,07` : le moteur multipliait un NOMBRE DE
   CONTRATS par le prix du SOUS-JACENT. 3 497,90 $ pour MSFT n'était ni la
   prime (marque absente), ni le capital engagé (9 800 $), ni le notionnel
   (349 800 $) — et `valuation_note` valait `null`, donc l'API affirmait avoir
   tout valorisé au marché. Attendu après correction : 14 188,07
   (14 100 déclarés + 88,07 au marché), cohérent avec `value_at_cost: 14100`
   de `/api/positions/state` et `excluded_cost: 14100` de `/api/portfolio/stress`.

2. Une option de 50 000 $ engagés sans cote sortait à `value 0.0`,
   `weight_pct 0.0`, `hhi 1.0`, sous la note « 1 position(s) valorisée(s) au
   coût » : l'absence était convertie en zéro ET l'honnêteté proclamée.
   Cause : `p.get('cost_basis') or 0.0`, alors que le modèle canonique écrit
   `capital_committed` sur une option (vertex/positions/models.py:151).
"""
from vertex.engines import portfolio_context


class _Profile:
    portfolio_min_positions = 1
    portfolio_max_positions = 10
    max_stock_weight_pct = 30
    raw = {'position_rules': {}, 'conviction_levels': {}}


class _ProfileAvecNiveaux(_Profile):
    #  Le sizing S+/S/A/B tire ses fourchettes en dollars de `sizing.base` :
    #  une base fabriquée produit des montants d'aide au sizing fabriqués.
    raw = {'position_rules': {}, 'conviction_levels': {'S': {'allocation_pct': [10, 15]}}}


def _option_canonique(symbol, quantity, capital_committed, mark=None):
    """Forme RÉELLEMENT produite par vertex.positions.models.option_position :
    `capital_committed` porte le coût, `cost_basis` n'existe pas, `mark` est
    None tant qu'aucune cotation de contrat n'est revenue."""
    return {'symbol': symbol, 'asset_type': 'OPTION', 'quantity': quantity,
            'multiplier': 100.0, 'strike': 500.0, 'right': 'CALL', 'mark': mark,
            'capital_committed': capital_committed, 'status': 'OPEN', 'is_real': True}


def test_portfolio_context_reports_declared_multi_asset_mix():
    positions = [
        {'symbol': 'SPY', 'asset_type': 'ETF', 'quantity': 2, 'cost_basis': 900, 'status': 'OPEN'},
        {'symbol': 'NVDA', 'asset_type': 'STOCK', 'quantity': 1, 'cost_basis': 100, 'status': 'OPEN'},
        _option_canonique('NVDA', 1, 50),
    ]
    out = portfolio_context.build(positions, quotes={'SPY': 500, 'NVDA': 110}, profile=_Profile())
    assert out['asset_mix']['ETF']['positions'] == 1
    assert out['asset_mix']['STOCK']['positions'] == 1
    assert out['asset_mix']['OPTION']['positions'] == 1
    assert out['asset_mix']['ETF']['weight_pct'] > out['asset_mix']['OPTION']['weight_pct']


def test_portfolio_context_keeps_undeclared_asset_type_explicit():
    positions = [{'symbol': 'XYZ', 'quantity': 1, 'cost_basis': 100, 'status': 'OPEN'}]
    out = portfolio_context.build(positions, profile=_Profile())
    assert out['asset_mix']['UNCLASSIFIED']['positions'] == 1
    assert 'sans type' in out['asset_mix_note']


# ── Constat 2 : la cote du sous-jacent ne valorise JAMAIS un contrat ─────────

def test_option_nest_jamais_valorisee_par_la_cote_du_sous_jacent():
    """MESURE : 7 contrats MSFT × spot 499,70 $ = 3 497,90 $ comptés comme
    valeur de marché, GOOG 2 × 335,31 = 670,62 $, total 4 256,59 $ et
    `valuation_note: null`. Aucun de ces montants n'existe financièrement."""
    positions = [
        _option_canonique('MSFT', 7.0, 9800.0),
        _option_canonique('GOOG', 2.0, 4300.0),
        {'symbol': 'KO', 'asset_type': 'STOCK', 'quantity': 1.0, 'cost_basis': 80.0,
         'status': 'OPEN', 'is_real': True},
    ]
    out = portfolio_context.build(positions, quotes={'MSFT': 499.7, 'GOOG': 335.31, 'KO': 88.07},
                                  profile=_Profile())
    assert out['total_value'] == 14188.07          # 14 100 déclarés + 88,07 au marché
    assert out['asset_mix']['OPTION']['value'] == 14100.0
    assert out['weights']['MSFT'] != 82.18         # l'ancien poids fabriqué
    assert out['weights']['MSFT'] == 69.07
    assert out['hhi'] == 0.569                     # 0,7005 « concentré » était calculé sur la fable
    # La note ne peut plus valoir None : deux options sont au capital engagé.
    assert out['valuation_note'] and 'capital engagé' in out['valuation_note']
    assert out['valuation'] == {'at_market': 1, 'at_cost': 0, 'at_committed': 2,
                                'unvalued': 0, 'total_positions': 3, 'read_only': True,
                                'method': out['valuation']['method']}
    # Le sizing ne part plus d'une base fabriquée : 4 256,59 → 14 188,07.
    sized = portfolio_context.build(positions, quotes={'MSFT': 499.7, 'GOOG': 335.31, 'KO': 88.07},
                                    profile=_ProfileAvecNiveaux())
    assert sized['sizing']['base'] == 14188.07
    assert sized['sizing']['levels']['S']['amount_range'] == [1418.81, 2128.21]


def test_option_avec_marque_utilise_marque_multiplicateur_quantite():
    """La marque du CONTRAT est la seule valorisation de marché admise :
    14,00 × 100 × 7 = 9 800, jamais 7 × 499,70."""
    out = portfolio_context.build([_option_canonique('MSFT', 7.0, 9100.0, mark=14.0)],
                                  quotes={'MSFT': 499.7}, profile=_Profile())
    assert out['total_value'] == 9800.0
    assert out['valuation']['at_market'] == 1
    assert out['valuation_note'] is None           # rien n'a été replié : rien à signaler


def test_pnl_du_candidat_ne_compare_pas_un_spot_a_un_cout_par_contrat():
    """9 800 $ / 7 contrats = 1 400 $ ; face à un spot de 499,70 $ cela ferait
    −64,3 % — un P&L inventé. Inconnu reste inconnu, donc renforcement non
    autorisé (jamais un oui par défaut)."""
    out = portfolio_context.build([_option_canonique('MSFT', 7.0, 9800.0)],
                                  quotes={'MSFT': 499.7}, sym='MSFT', profile=_Profile())
    assert out['candidate']['pnl_pct'] is None
    assert out['candidate']['reinforcement_allowed'] is None
    assert 'marque du contrat' in out['candidate']['pnl_note']   # l'inconnu est motivé


# ── Constat 3 : absence ≠ zéro ───────────────────────────────────────────────

def test_position_sans_marque_ni_cout_est_exclue_et_nommee_jamais_zero():
    """MESURE : `ZZZQ` (option, 50 000 $ engagés non déclarés) sortait à
    value 0.0 / weight 0.0 / hhi 1.0 avec la note « valorisée au coût ».
    Attendu : exclue du total ET nommée dans `unvalued_positions`."""
    positions = [
        {'symbol': 'ZZZQ', 'asset_type': 'OPTION', 'quantity': 10.0, 'multiplier': 100.0,
         'status': 'OPEN', 'is_real': True},
        {'symbol': 'KO', 'asset_type': 'STOCK', 'quantity': 1.0, 'cost_basis': 80.0,
         'status': 'OPEN', 'is_real': True},
    ]
    out = portfolio_context.build(positions, quotes={'KO': 88.07}, profile=_Profile())
    assert 'ZZZQ' not in out['weights']            # ni 0 %, ni un poids fabriqué
    assert out['weights'] == {'KO': 100.0}
    assert out['total_value'] == 88.07
    assert [u['symbol'] for u in out['unvalued_positions']] == ['ZZZQ']
    assert 'sous-jacent' in out['unvalued_positions'][0]['reason']
    assert out['valuation']['unvalued'] == 1
    assert 'exclue(s)' in out['valuation_note']
    assert 'au coût' not in out['valuation_note']  # plus de fausse déclaration d'honnêteté


def test_option_canonique_sans_cost_basis_nest_pas_valorisee_zero():
    """`cost_basis` est None sur toute option canonique : lire cette clé faisait
    tomber la ligne à 0 (`p.get('cost_basis') or 0.0`). La clé propriétaire est
    `capital_committed`, comme dans vertex/positions/audit.py:18."""
    out = portfolio_context.build([_option_canonique('MSFT', 7.0, 9800.0)],
                                  quotes={}, profile=_Profile())
    assert out['available'] is True
    assert out['total_value'] == 9800.0
    assert out['valuation']['at_committed'] == 1


def test_portefeuille_entierement_non_valorisable_reste_honnete():
    """Aucune ligne valorisable : `available: false` avec la raison NOMMÉE, et
    surtout jamais un total de 0 $ présenté comme la valeur du portefeuille."""
    out = portfolio_context.build([{'symbol': 'ZZZQ', 'asset_type': 'OPTION',
                                    'quantity': 10.0, 'status': 'OPEN', 'is_real': True}],
                                  quotes={}, profile=_Profile())
    assert out['available'] is False
    assert 'sans marque ni coût' in out['reason']
    assert [u['symbol'] for u in out['unvalued_positions']] == ['ZZZQ']
