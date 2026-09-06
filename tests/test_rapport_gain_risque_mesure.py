"""Vertex Test 1.0 — LE R:R DE LA CONSTITUTION ÉTAIT UNE CONSTANTE, ET SA GARDE MORTE.

`CLAUDE.md`, invariant 5 : « Aucune donnée financière inventée. Absence, zéro,
estimation, retard, fallback, démo et erreur restent distincts. » Invariant 7 :
l'IA « ne contourne jamais un hard gate ». La constitution (profil
`vertex_strategy_v*.json`, `reward_risk_min = 2.0`) fait du rapport gain/risque
la garde dure la plus citée du produit : sans R:R ≥ 2:1, jamais ACHETER ni
RENFORCER.

## Le défaut, mesuré le 6 septembre 2026 (instance QA 5003, NO_IBKR=1)

`vertex/engines/analysis.py:265` écrit dans le plan, en dur :

```python
'tp3': round(last + 3 * risk, 2), 'rr': 3.0, 'atr': round(atr, 2),
```

`plan['rr']` n'est donc PAS une mesure : c'est la reformulation de la
construction de TP3 (`tp3 = entrée + 3 × risque`). Le vrai rapport mesuré est
`plan['rr_res'] = (résistance 40 barres − dernier cours) / risque`.

`vertex/strategy/decision_packet.py` lisait `detail['rr'] or plan['rr']`. Or le
dict retourné par `analysis.analyse` ne porte AUCUNE clé `rr` de premier
niveau : le repli sur la constante était le chemin NORMAL, pour tout l'univers.

`/api/strategy/decision/<sym>` contre `/api/ticker/<sym>`, huit titres :

| titre | `technical.reward_risk` servi | `scores.asymmetry` | `plan.rr_res` MESURÉ |
|---|---|---|---|
| AAPL  | 3.0 | 80.0 | 1.3 |
| MSFT  | 3.0 | 80.0 | 0.7 |
| NVDA  | 3.0 | 80.0 | **0.2** |
| TSLA  | 3.0 | 80.0 | 1.4 |
| AMD   | 3.0 | 80.0 | 1.7 |
| META  | 3.0 | 80.0 | 1.4 |
| GOOGL | 3.0 | 80.0 | 2.3 |
| AMZN  | 3.0 | 80.0 | 1.7 |

8/8 servaient la même constante ; **7/8 étaient en réalité sous le minimum
2:1**. `RR_BELOW_MINIMUM` s'est allumé **0 fois sur 8** — une garde qui ne
s'allume jamais ne distingue plus rien — et `scores.asymmetry` valait la
constante `(3.0 − 1) × 40 = 80.0` partout, ce qui satisfaisait en permanence la
condition `asym >= 40` de la branche ACHETER/RENFORCER.

## Le zéro mesuré éteignait trois autres gardes

`rr_res` vaut 0.0 chez son producteur quand le risque est nul ou que le cours a
rejoint la résistance des 40 barres : « aucune marge vers la cible », le pire
cas mesurable. Trois lectures le confondaient avec une absence
(`_num(..., 0.0)` puis `if rr and rr < 2.0`) :

| moteur | rr_res 0.1 | rr_res **0.0** | rr_res absent |
|---|---|---|---|
| `decision_stack.evaluate` | WATCH_BREAKOUT | **STRONG_BUY** | **STRONG_BUY** |
| `decision_stack._tipping_points` | 1 point | **aucun** | **aucun** |
| `evidence.risk_analyst` | 1 preuve NEGATIVE (65) | **0 preuve** | **0 preuve** |
| `decide.decide` (repli `plan['rr']`) | SURVEILLER | SURVEILLER | **ACHETER FORT** |

Non monotone : 0.1 dégradait, 0.0 — strictement pire — passait en achat fort.
Et le silence de `risk_analyst` remontait dans `_committee` (`lean = pos /
(pos + neg)`) : au pire R:R possible, l'accord et la confiance du comité
MONTAIENT.

## Ce que ce lot ne corrige pas

Il ne réconcilie pas les quatre nombres nommés « rr » servis par le produit
(voir `test_le_mot_rr_recouvre_quatre_notions`) : il branche la décision sur le
seul qui mesure quelque chose. `vertex/positions/recalculator.py:191` refait le
même repli sur la constante — hors périmètre, décrit au rapport de lot.
"""
from __future__ import annotations

from vertex.engines import decide as _decide
from vertex.engines import decision_stack as ds
from vertex.engines import evidence as ev
from vertex.strategy import decision_packet as dp
from vertex.strategy import executive_engine as ee

#  Forme RÉELLE du `detail` d'un scan : pas de clé `rr` au premier niveau,
#  `plan['rr']` littéral 3.0 à côté du `rr_res` mesuré (analysis.py:252-266).
def _detail_scan(rr_res=1.3, **kw):
    d = {'price': 100.0, 'score': 78, 'rs': 70, 'sub': {'fundamental': 82},
         'plan': {'entry': 100.0, 'stop': 95.0, 'tp1': 105.0, 'tp2': 110.0,
                  'tp3': 115.0, 'rr': 3.0, 'resistance': 106.5}}
    if rr_res is not None:
        d['plan']['rr_res'] = rr_res
    d.update(kw)
    return d


# ── 1. Le paquet de décision ne sert plus la constante ────────────────────────

def test_le_packet_lit_le_rr_mesure_et_jamais_le_litteral_3_0():
    """AAPL mesuré 1.3 était servi 3.0. Le paquet lit `plan['rr_res']`."""
    for mesure in (0.2, 0.7, 1.3, 1.7, 2.3):
        paquet = dp.build('ZZ', _detail_scan(rr_res=mesure), {'source': 'live'})
        assert paquet['technical']['reward_risk'] == mesure, mesure
        assert paquet['technical']['reward_risk'] != 3.0


def test_la_garde_dure_rr_s_allume_sur_les_titres_reellement_sous_le_minimum():
    """0/8 allumages mesurés le 6 sept. ; les 7 titres sous 2:1 doivent l'allumer."""
    mesures_du_6_septembre = {'AAPL': 1.3, 'MSFT': 0.7, 'NVDA': 0.2, 'TSLA': 1.4,
                              'AMD': 1.7, 'META': 1.4, 'GOOGL': 2.3, 'AMZN': 1.7}
    allumes = set()
    for sym, rr in mesures_du_6_septembre.items():
        verdict = ee.decide(dp.build(sym, _detail_scan(rr_res=rr), {'source': 'live'}))
        if 'RR_BELOW_MINIMUM' in verdict['blocking_rules']:
            allumes.add(sym)
    assert allumes == {'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMD', 'META', 'AMZN'}, allumes


def test_l_asymetrie_n_est_plus_la_constante_80():
    """`scores.asymmetry` valait 80.0 sur 8/8 titres : (3.0 − 1) × 40."""
    notes = {ee.decide(dp.build('ZZ', _detail_scan(rr_res=rr), {'source': 'live'}))
             ['scores']['asymmetry']
             for rr in (0.2, 0.7, 1.3, 1.7, 2.3)}
    assert len(notes) > 1, 'une note qui ne varie pas avec la mesure ne mesure rien'
    assert 80.0 not in notes


def test_un_rr_absent_devient_une_inconnue_nommee_pas_un_neutre():
    paquet = dp.build('ZZ', _detail_scan(rr_res=None), {'source': 'live'})
    assert paquet['technical']['reward_risk'] is None
    verdict = ee.decide(paquet)
    assert 'reward_risk' in verdict['unknowns']
    assert verdict['scores']['asymmetry'] == 0.0
    assert verdict['final_decision'] not in ('ACHETER', 'RENFORCER')


def test_un_rr_mesure_a_zero_traverse_le_lecteur_et_allume_la_garde():
    """0.0 est le pire cas mesurable, pas une absence : il ne doit pas devenir None."""
    paquet = dp.build('ZZ', _detail_scan(rr_res=0.0), {'source': 'live'})
    assert paquet['technical']['reward_risk'] == 0.0
    verdict = ee.decide(paquet)
    assert 'RR_BELOW_MINIMUM' in verdict['blocking_rules']
    assert 'reward_risk' not in verdict['unknowns']


def test_le_lecteur_canonique_est_exporte_et_ignore_le_litteral():
    """`read_reward_risk` — pour que le desk n'en écrive pas un quatrième."""
    assert dp.read_reward_risk({'plan': {'rr': 3.0}}) is None
    assert dp.read_reward_risk({'plan': {'rr': 3.0, 'rr_res': 1.1}}) == 1.1
    assert dp.read_reward_risk({'rr': 4.5, 'plan': {'rr': 3.0, 'rr_res': 1.1}}) == 4.5
    #  Un R:R illisible n'est pas un R:R : chaîne, booléen, NaN → inconnue.
    assert dp.read_reward_risk({'plan': {'rr_res': 'n/d'}}) is None
    assert dp.read_reward_risk({'plan': {'rr_res': True}}) is None
    assert dp.read_reward_risk({'plan': {'rr_res': float('nan')}}) is None


# ── 2. Le zéro mesuré n'éteint plus les gardes ────────────────────────────────

def _stack(rr_res):
    d = {'price': 100, 'score': 85, 'verdict': 'BUY', 'confidence': 70,
         'plan': {'entry': 100, 'stop': 95, 'tp1': 105, 'tp2': 110, 'tp3': 115}}
    if rr_res is not None:
        d['plan']['rr_res'] = rr_res
    return ds.evaluate(d, symbol='ZZ')


def test_decision_stack_degrade_au_rr_mesure_zero():
    """0.1 dégradait, 0.0 — strictement pire — passait STRONG_BUY."""
    assert _stack(0.0)['final_decision'] == 'WATCH_BREAKOUT'
    assert _stack(0.1)['final_decision'] == 'WATCH_BREAKOUT'
    assert _stack(1.9)['final_decision'] == 'WATCH_BREAKOUT'
    assert _stack(2.0)['final_decision'] == 'STRONG_BUY'


def test_decision_stack_le_rr_absent_ne_vaut_pas_un_feu_vert():
    absent = _stack(None)
    assert absent['final_decision'] not in ('STRONG_BUY', 'BUY')
    assert any('non mesuré' in a for a in absent['audit_trail'])


def test_les_points_de_bascule_nomment_le_zero_et_l_absence():
    assert any('0.0' in t for t in _stack(0.0)['tipping_points'])
    assert any('MESURÉ' in t for t in _stack(None)['tipping_points'])


def test_l_analyste_risque_ne_se_tait_plus_au_pire_rr():
    """Le silence faisait MONTER l'accord du comité au pire R:R possible."""
    def _kinds(rr_res):
        plan = {'entry': 100, 'stop': 95}
        if rr_res is not None:
            plan['rr_res'] = rr_res
        return [e['kind'] for e in ev.risk_analyst({'plan': plan}, None)]

    assert _kinds(0.0) == [ev.NEGATIVE]
    assert _kinds(0.1) == [ev.NEGATIVE]
    assert _kinds(2.0) == [ev.POSITIVE]
    assert _kinds(None) == [ev.UNKNOWN], 'absence ≠ zéro mesuré ≠ silence'


def test_le_comite_penche_enfin_au_pire_rr_au_lieu_de_rester_neutre():
    """Le silence de `risk_analyst` rendait le pire R:R indiscernable d'un vide.

    Mesuré sur ce même détail synthétique (`lean = pos / (pos + neg)`) :

        rr_res 0.0 AVANT -> lean 50, vue « Équilibré »   (analyste muet)
        rr_res 0.0 APRÈS -> lean  0, vue « Négatif »
        rr_res 2.5       -> lean 100, vue « Constructif »
    """
    pire = _stack(0.0)['committee']
    bon = _stack(2.5)['committee']
    assert pire['lean'] < bon['lean'], (pire['lean'], bon['lean'])
    assert pire['view'] == 'Négatif', pire['view']
    assert pire['lean'] != 50, 'un pire cas mesuré ne doit pas se lire « équilibré »'


def test_le_verdict_de_scan_ne_franchit_plus_la_garde_avec_le_litteral():
    """`decide.py` repliait sur `plan['rr']` = 3.0 quand `rr_res` manquait."""
    def _verdict(plan):
        return _decide.decide({'score': 82, 'trend': 70, 'regime': 'TREND',
                               'setup_quality': 70, 'confidence': 70, 'rsi': 55,
                               'pos52': 80, 'rs': 70, 'volx': 1.4,
                               'signals': {'above50': True, 'above200': True,
                                           'stacked': True},
                               'plan': plan})

    sans_mesure = _verdict({'entry': 100, 'stop': 95, 'rr': 3.0})
    assert sans_mesure['decision'] not in ('ACHETER', 'ACHETER FORT')
    assert any('non confirmé' in c for c in sans_mesure['cons'])

    zero = _verdict({'entry': 100, 'stop': 95, 'rr': 3.0, 'rr_res': 0.0})
    assert zero['decision'] not in ('ACHETER', 'ACHETER FORT')

    conforme = _verdict({'entry': 100, 'stop': 95, 'rr': 3.0, 'rr_res': 2.5})
    assert conforme['decision'] in ('ACHETER', 'ACHETER FORT')


# ── 3. Un seul lecteur, pas quatre ────────────────────────────────────────────

def test_le_mot_rr_recouvre_quatre_notions_la_tautologie_porte_sa_base():
    """Quatre nombres nommés « rr » circulent — celui de l'espérance est constant.

    Mesuré le 6 sept. 2026 (5003), mêmes 8 titres :

    | champ | ce que c'est | valeurs mesurées |
    |---|---|---|
    | `plan.rr` | littéral `3.0` (analysis.py:265) | 3.0 sur 8/8 |
    | `plan.rr_res` | ratio MESURÉ vers la résistance | 0.2 → 2.3 |
    | `vertex.rr` | NOTE /100 (`rr_score`, « 2:1→64 ») | 8, 22, 41, 44, 55, 64 |
    | `vertex.ev.rr` | `gain/loss` du plan, TP2/stop | 2.0 sur 8/8 |

    Le dernier est arithmétiquement juste mais tautologique (`tp2 = entrée +
    2 × risque`) : il ne peut pas valoir autre chose que 2.0. Il reste servi,
    avec sa base, pour qu'il ne se lise pas comme le R:R du dossier.
    """
    from vertex.engines import quant_engine as qe
    detail = {'plan': {'entry': 100.0, 'stop': 92.0, 'tp2': 116.0}}
    ev_bloc = qe.expected_value(detail, 0.6)
    assert ev_bloc['rr'] == 2.0
    assert 'rr_res' in ev_bloc['rr_basis'] and 'construction' in ev_bloc['rr_basis']


def test_un_seul_lecteur_du_rr_du_plan_pour_les_moteurs_de_decision():
    """`decision_stack` réutilise l'objet d'`evidence` — pas une seconde copie."""
    assert ds.rr_mesure is ev.rr_mesure


def test_aucun_moteur_de_decision_ne_replie_sur_le_litteral_plan_rr():
    """Garde de non-régression MESURÉE sur l'AST, pas sur une chaîne de texte.

    Un `plan['rr']` lu dans un moteur de décision est, par construction, la
    constante 3.0 d'`analysis.py:265`. On cherche donc, dans l'arbre syntaxique,
    tout `<qqch>.get('rr')` ou `<qqch>['rr']` appliqué à une expression dont le
    nom contient `plan` — ce qui attrape le repli quel que soit son écriture.
    """
    import ast
    import pathlib

    racine = pathlib.Path(__file__).resolve().parent.parent
    moteurs = ['vertex/strategy/decision_packet.py', 'vertex/engines/decide.py',
               'vertex/engines/decision_stack.py', 'vertex/engines/evidence.py']

    def _porte_sur_un_plan(noeud):
        while isinstance(noeud, (ast.Attribute, ast.Subscript, ast.Call)):
            if isinstance(noeud, ast.Call):
                noeud = noeud.func
            elif isinstance(noeud, ast.Attribute):
                if 'plan' in noeud.attr.lower():
                    return True
                noeud = noeud.value
            else:
                noeud = noeud.value
        return isinstance(noeud, ast.Name) and 'plan' in noeud.id.lower()

    fautes = []
    for rel in moteurs:
        arbre = ast.parse((racine / rel).read_text(encoding='utf-8'))
        for noeud in ast.walk(arbre):
            cle = cible = None
            if (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
                    and noeud.func.attr == 'get' and len(noeud.args) >= 1
                    and isinstance(noeud.args[0], ast.Constant)):
                cle, cible = noeud.args[0].value, noeud.func.value
            elif (isinstance(noeud, ast.Subscript)
                  and isinstance(noeud.slice, ast.Constant)):
                cle, cible = noeud.slice.value, noeud.value
            if cle == 'rr' and cible is not None and _porte_sur_un_plan(cible):
                fautes.append('%s:%d' % (rel, noeud.lineno))
    assert not fautes, ("repli sur le littéral plan['rr'] (= 3.0) dans un moteur "
                        'de décision : %s' % ', '.join(fautes))
