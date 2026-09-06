"""Le desk des positions dit la même chose que le reste du produit.

Cinq défauts mesurés le 6 septembre 2026, tous sur des données RÉELLEMENT
servies, tous fermés ici. Chaque banc porte sa mesure AVANT/APRÈS ; aucun ne
passerait sur le corps d'avant correction.

## 1. Deux autorités de décision contradictoires sur le même titre

Sur le MÊME `scan_state` (AAPL, `detail.sub.fundamental = 72`, `market_ctx`
{'spy_regime':'TREND','vix':15.0,'breadth':{'above200':68},'roro':'RISK-ON'}) :

| | régime | new_risk_allowed | fondamental | bloquants |
| --- | --- | --- | --- | --- |
| `/api/strategy/decision` | TREND_UP | True | 72.0 | (paquet incomplet) |
| `positions/recalculator` | UNKNOWN | False | None | REGIME_BLOCKS_NEW_RISK |

Deux causes distinctes, toutes deux dans `recalculator.py` : le régime était
classé sur `scan_state['market']`, qui est l'HORLOGE de séance (clés réelles
['et','open','session']) et ne porte aucune dimension ; et le fondamental était
lu sur `st_fund` / `fund_score`, deux clés SANS producteur sur le `detail` du
scan. Résultat servi : `decision: ATTENDRE` sur toutes les positions détenues,
en permanence, pendant que la même donnée rendait RENFORCER par l'autre route.
CLAUDE.md interdit explicitement deux autorités pour une même capacité.

## 2. Une note fondamentale MESURÉE déclarée inconnue

`thesis_health.assess()` lisait les deux mêmes clés mortes. MESURÉ avec
`detail['sub']['fundamental'] = 72` : unknowns ['fondamental'], confidence 0.67
— sur des positions DÉCLARÉES par l'utilisateur. Une mesure présentée comme une
absence viole l'invariant 5 aussi sûrement qu'un chiffre inventé.

## 3. La convention de marque perdue avec le contrat

Le repli du board (`desk._scan_fallback_quote`) ne transmettait que `mark`. Le
bloc de provenance de `/api/pos-quotes` recalcule le milieu depuis bid/ask, n'en
trouvait aucun, et `source_de_marque(6.20, mid=None)` rendait INDETERMINEE —
« convention non renseignée » à l'écran — alors que le chiffre EST le milieu de
fourchette du board. `spread_pct` restait null pour la même raison.

## 4. Deux mesures vraies de stress inatteignables en production

`/api/portfolio/team` ne transmettait pas `options_open` à `run_stress_tests`.
Le moteur ne pouvait donc pas séparer « aucune option » de « options sans greeks
broker », et rendait `impact_pct: None` dans les deux cas. Sur un desk sans
aucune option (KO 88,07 $ + 25 000 $ de cash), IV_CRUSH vaut un 0,0 % VRAI et
VIX_PLUS_50 -0,01 % : deux chiffres justes qu'aucun chemin servi n'atteignait.

## 5. Un vocabulaire d'état que personne n'émet

`vertex/app/caches.py` documentait « 'UNKNOWN' | 'OK' | 'UNAVAILABLE' ». `OK`
n'a jamais été écrit par aucun émetteur — c'est l'origine plausible de la liste
blanche morte de la page Système (cinq sources saines affichées « dégradé »).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))


# ── Formes RÉELLES du produit (jamais un vocabulaire que personne n'émet) ──

def _scan_reel():
    """`market` = horloge de séance ; les dimensions vivent dans `market_ctx`.

    Troisième tour : la fixture porte aussi `data_quality` et `reconciliation`.
    Ce ne sont pas des ornements — `scan_evidence.build_scan` les pose sur
    CHAQUE titre scanné (vérifié chez le producteur), et le recalculateur les
    fabriquait à la main, dont un `actionable_allowed: True` affirmé sans
    mesure. Une fixture qui ne les portait pas ne pouvait pas voir ce défaut.
    Le témoin du cas contraire — preuve absente ou en désaccord — vit dans
    tests/test_desk_positions_une_seule_autorite.py.
    """
    return {'source': 'ibkr',
            'market': {'et': '10:31', 'open': True, 'session': 'REGULAR'},
            'market_ctx': {'spy_regime': 'TREND', 'vix': 15.0,
                           'breadth': {'above200': 68}, 'roro': 'RISK-ON'},
            'detail': {'AAPL': {'price': 210.0, 'score': 72, 'rs': 72, 'rr': 4.5,
                                'earnings_dte': 20, 'sector': 'Technology',
                                'sub': {'fundamental': 72,
                                        'fundamental_is_proxy': False},
                                'data_quality': {'overall': 'RECENT',
                                                 'actionable_allowed': True},
                                'reconciliation': {'available': True,
                                                   'actionable_allowed': True}}}}


def _desk_une_action():
    return {'data': {'myTrades': json.dumps([
        {'id': 1, 'sym': 'AAPL', 'type': 'STK', 'qty': 10, 'cost': 2000,
         'entrySnap': {'stop': 190.0, 'tgt': 300.0, 'thesis': 'thèse déclarée'}}])}}


# ── 1. Une seule autorité de décision ──────────────────────────────────────

def test_le_regime_des_positions_ne_se_lit_plus_sur_l_horloge_de_seance():
    """MESURÉ : régime UNKNOWN d'un côté, TREND_UP de l'autre, même scan."""
    from vertex.engines.market_context import regime_inputs
    from vertex.market.regime_engine import classify_regime
    from vertex.strategy import decision_packet

    scan = _scan_reel()
    #  Ce que lisait le recalculateur : les trois entrées de l'horloge.
    horloge = scan['market']
    assert horloge.get('spy_trend') is None and horloge.get('vix') is None, (
        "scan_state['market'] est l'horloge de séance — s'il portait vraiment "
        'des dimensions de régime, le constat 7 n’aurait pas eu lieu')
    ancien = classify_regime({'index_trend': horloge.get('spy_trend'),
                              'breadth_pct': horloge.get('breadth'),
                              'vix': horloge.get('vix')})
    assert ancien['regime'] == 'UNKNOWN'           # l'état d'avant, reproduit

    #  Ce que lit le paquet canonique, et désormais le recalculateur aussi.
    paquet = decision_packet.build('AAPL', scan['detail']['AAPL'], scan)
    nouveau = classify_regime(regime_inputs(scan))
    assert nouveau['regime'] == paquet['market_regime']['regime'] == 'TREND_UP'
    assert (nouveau['adjustments']['new_risk_allowed']
            is paquet['market_regime']['adjustments']['new_risk_allowed'] is True)


def test_les_deux_autorites_de_decision_rendent_le_meme_fondamental():
    """MESURÉ : {'score': None} contre {'score': 72.0} pour la MÊME donnée."""
    from vertex.strategy import decision_packet

    detail = _scan_reel()['detail']['AAPL']
    #  L'ancien lecteur, remis en mémoire : deux clés sans producteur.
    assert (detail.get('st_fund') or detail.get('fund_score')) is None
    #  Le lecteur canonique, celui que les deux autorités partagent désormais.
    assert decision_packet.read_fundamental(detail) == {'score': 72.0,
                                                        'is_proxy': False}


def test_une_position_detenue_n_est_plus_bloquee_par_un_regime_fabrique():
    """Bout en bout : `REGIME_BLOCKS_NEW_RISK` s'allumait sur TOUTES les
    positions détenues, quel que soit le marché. MESURE AVANT :
    `decision: ATTENDRE`, `decision_blocking: ['REGIME_BLOCKS_NEW_RISK']`.
    MESURE APRÈS : `RENFORCER`, aucun bloquant — la garde dure cesse d'être
    neutralisée en se faisant passer pour active."""
    from vertex.positions import recalculator

    out = recalculator.recalculate_all(_scan_reel(), _desk_une_action())
    p = out['positions'][0]
    assert 'REGIME_BLOCKS_NEW_RISK' not in p['decision_blocking']
    assert p['decision'] == 'RENFORCER'


def test_sans_dimension_servie_la_garde_dure_reste_fermee():
    """Témoin négatif — le correctif ne doit RIEN ouvrir sur une absence.

    Un scan sans `market_ctx` ni `market.regime` ne mesure aucune dimension :
    le régime doit rester UNKNOWN et le nouveau risque interdit. Sans ce
    contrôle, « lire la bonne clé » pourrait se transformer en « autoriser par
    défaut », qui serait un défaut bien pire que celui corrigé."""
    from vertex.engines.market_context import regime_inputs
    from vertex.market.regime_engine import classify_regime
    from vertex.positions import recalculator

    vide = {'source': 'ibkr', 'market': {'et': '10:31', 'open': True},
            'detail': {'AAPL': {'price': 210.0, 'score': 72, 'rs': 72, 'rr': 4.5,
                                'sub': {'fundamental': 72}}}}
    r = classify_regime(regime_inputs(vide))
    assert r['regime'] == 'UNKNOWN'
    assert r['adjustments']['new_risk_allowed'] is False
    p = recalculator.recalculate_all(vide, _desk_une_action())['positions'][0]
    assert 'REGIME_BLOCKS_NEW_RISK' in p['decision_blocking']


def test_un_moteur_de_verdict_en_panne_nomme_sa_cause(monkeypatch):
    """Une absence sans cause nommée est muette. MESURÉ en faisant lever le
    lecteur de catalyseurs : `recalculate_all` rendait `decision: None` sur
    TOUTES les positions, sans trace, sans champ, sans exception — le desk
    passait de « verdict moteur » à « rien » en silence.

    Troisième tour : le desk ne lit plus les blocs un par un, il appelle le
    CONSTRUCTEUR canonique `decision_packet.build`. C'est donc lui qu'on fait
    tomber — le point de panne a changé de nom, la propriété mesurée non : une
    décision absente doit nommer sa cause.
    """
    from vertex.positions import recalculator
    from vertex.strategy import decision_packet

    nominal = recalculator.recalculate_all(_scan_reel(), _desk_une_action())
    assert nominal['decision_engine'] == {'available': True, 'reason': None}

    def _leve(*_a, **_k):
        raise RuntimeError('constructeur indisponible')

    monkeypatch.setattr(decision_packet, 'build', _leve)
    casse = recalculator.recalculate_all(_scan_reel(), _desk_une_action())
    assert casse['positions'][0].get('decision') is None
    assert casse['decision_engine']['available'] is False
    assert 'RuntimeError' in casse['decision_engine']['reason']


# ── 2. La santé de thèse lit le fondamental chez son producteur ────────────

def test_le_fondamental_mesure_n_est_plus_une_inconnue_de_la_these():
    """MESURÉ : avec `sub.fundamental = 72`, `assess()` rendait
    unknowns ['fondamental'] et confidence 0.67 — une note existante déclarée
    inconnue sur une position DÉCLARÉE par l'utilisateur."""
    from vertex.positions import thesis_health

    detail = _scan_reel()['detail']['AAPL']
    p = {'thesis_text': 'thèse déclarée', 'current_price': 210.0,
         'stop': 190.0, 'remaining_rr': 4.5}
    th = thesis_health.assess(p, detail)
    assert 'fondamental' not in th['unknowns']
    assert 'fondamental 72' in th['positive_evidence']
    assert th['confidence'] == 1.0                 # valait 0.75 avec l'inconnue


def test_un_fondamental_de_proxy_ne_se_lit_pas_comme_une_mesure_comptable():
    """Invariant 6 — le lignage voyage avec la note. Trois états DISTINCTS :
    mesure directe, proxy technique, producteur muet."""
    from vertex.positions import thesis_health

    p = {'thesis_text': 't', 'current_price': 210.0, 'stop': 190.0}
    direct = thesis_health.assess(p, {'sub': {'fundamental': 72,
                                              'fundamental_is_proxy': False}})
    proxy = thesis_health.assess(p, {'sub': {'fundamental': 72,
                                             'fundamental_is_proxy': True}})
    assert direct['positive_evidence'] == ['fondamental 72']
    assert proxy['positive_evidence'] == ['fondamental 72 (proxy technique)']
    #  Sémantique 0 conservée : « fondamentaux non branchés », donc ABSENT —
    #  jamais « fondamental faible 0 », qui serait un jugement inventé.
    zero = thesis_health.assess(p, {'sub': {'fundamental': 0}})
    assert 'fondamental' in zero['unknowns']
    assert zero['negative_evidence'] == []


# ── 3. La marque du board garde sa convention ──────────────────────────────

def _client_desk_sans_cotation_broker():
    """Le worker IBKR ne rend rien : la route bascule sur le repli du scan."""
    from flask import Flask

    from vertex.app.routes import desk
    app = Flask(__name__)
    app.register_blueprint(desk.make_blueprint(
        opt_job=lambda kind, args, timeout: {}, ibkr_enabled=True))
    return app.test_client()


def test_le_repli_du_board_transmet_la_convention_de_marque(monkeypatch):
    """MESURÉ sur NVDA 2026-10-23 245 C, board 6,00 / 6,40 (milieu 6,20) :
    AVANT `mark_source: 'INDETERMINEE'` et `spread_pct: null` ;
    APRÈS `MILIEU_FOURCHETTE` et 6,45 %. Le milieu du board EST la convention
    de marque — la perdre en route rendait la valorisation non auditable."""
    from vertex.app import state as _state

    monkeypatch.setitem(_state.scan_state, 'detail', {'NVDA': {'price': 180.0}})
    monkeypatch.setitem(_state.scan_state, 'options_board', [
        {'sym': 'NVDA', 'type': 'CALL', 'exp': '2026-10-23', 'strike': 245.0,
         'mid': 6.2, 'bid': 6.0, 'ask': 6.4}])
    j = _client_desk_sans_cotation_broker().post('/api/pos-quotes', json={
        'positions': [{'sym': 'NVDA', 'exp': '2026-10', 'strike': 245,
                       'right': 'C'}]}).get_json()
    q = j['results']['NVDA|2026-10|245|C']
    assert q['mark'] == 6.2
    assert q['mark_source'] == 'MILIEU_FOURCHETTE'   # valait INDETERMINEE
    assert q['spread_pct'] == 6.45                   # valait None
    assert q['delayed'] is True                      # la cote reste différée


def test_un_contrat_du_board_sans_fourchette_reste_sans_spread(monkeypatch):
    """Témoin négatif : on transmet ce que le board publie, JAMAIS plus. Sans
    bid/ask, aucune fourchette n'est reconstruite — la convention reste connue
    (le milieu est servi), le spread reste absent."""
    from vertex.app import state as _state

    monkeypatch.setitem(_state.scan_state, 'detail', {'NVDA': {'price': 180.0}})
    monkeypatch.setitem(_state.scan_state, 'options_board', [
        {'sym': 'NVDA', 'type': 'CALL', 'exp': '2026-10-23', 'strike': 245.0,
         'mid': 6.2}])
    j = _client_desk_sans_cotation_broker().post('/api/pos-quotes', json={
        'positions': [{'sym': 'NVDA', 'exp': '2026-10', 'strike': 245,
                       'right': 'C'}]}).get_json()
    q = j['results']['NVDA|2026-10|245|C']
    assert q.get('bid') is None and q.get('ask') is None
    assert q['mark_source'] == 'MILIEU_FOURCHETTE'
    assert q['spread_pct'] is None


# ── 4. Le stress reçoit enfin son périmètre options ────────────────────────

def _team(body):
    import os

    os.environ.setdefault('VERTEX_CODE', '')
    from vertex.runtime import app
    r = app.test_client().post('/api/portfolio/team', json=body)
    assert r.status_code == 200
    return r.get_json()['stress']


def test_les_scenarios_vrais_d_un_desk_sans_option_ne_sont_plus_perdus():
    """MESURE AVANT (signature exacte de la route) : IV_CRUSH `impact_pct: None`
    ET VIX_PLUS_50 `impact_pct: None`. MESURE APRÈS : 0,0 % et -0,01 %.

    Le 0,0 % de l'IV crush n'est pas un zéro inventé : sans aucune option
    ouverte, une contraction d'IV est sans effet, et c'est un FAIT. Le -0,01 %
    du VIX est le volet actions mesuré (poids KO 88,07/25 088,07 = 0,351 % ×
    bêta de repli 1,0 × -4 %)."""
    s = _team({'positions': [{'symbol': 'KO', 'quantity': 1, 'avg_cost': 88.07,
                              'last_price': 88.07, 'sector': 'Consumer Defensive'}],
               'cash': 25000.0})
    assert s['coverage']['options_open'] == 0      # valait None : périmètre perdu
    assert s['scenarios']['IV_CRUSH']['impact_pct'] == 0.0
    assert s['scenarios']['VIX_PLUS_50']['impact_pct'] == -0.01
    assert 'aucune option' in s['scenarios']['IV_CRUSH']['note']


def test_le_perimetre_options_decide_de_la_phrase_pas_la_veracite_du_vega():
    """MESURÉ avec `options_vega_value=0.0, options_open=2` : la note disait
    « aucune option déclarée, donc aucun volet vega » dans la MÊME réponse qui
    portait `coverage.options_open: 2` et l'avertissement « 2 option(s) hors
    base de stress ». Un vega agrégé nul sur des options réelles est un fait
    mesuré, pas l'absence d'options."""
    from vertex.portfolio import stress_tests
    from vertex.portfolio.models import PortfolioSnapshot, Position
    from vertex.strategy import constitution

    snap = PortfolioSnapshot(positions=[Position(symbol='KO', quantity=1,
                                                 avg_cost=88.07, last_price=88.07)],
                             cash=25000.0)
    r = stress_tests.run_stress_tests(snap, constitution.load_profile(),
                                      options_vega_value=0.0, options_open=2)
    for cle in ('IV_CRUSH', 'VIX_PLUS_50'):
        note = r['scenarios'][cle]['note']
        assert 'aucune option déclarée' not in note, (cle, note)
        assert 'aucune option ouverte déclarée' not in note, (cle, note)
    assert '2 option(s)' in r['scenarios']['IV_CRUSH']['note']
    assert r['coverage']['options_open'] == 2


def test_la_parenthese_du_desk_sans_option_ne_s_adresse_qu_a_qui_l_ignore():
    """« sans option ouverte, l'impact serait 0 % » décrit un desk qui n'est
    pas celui du lecteur dès qu'il a 2 options déclarées. Elle n'est servie que
    lorsque le périmètre lui-même est inconnu."""
    from vertex.portfolio import stress_tests
    from vertex.portfolio.models import PortfolioSnapshot, Position
    from vertex.strategy import constitution

    snap = PortfolioSnapshot(positions=[Position(symbol='KO', quantity=1,
                                                 avg_cost=88.07, last_price=88.07)],
                             cash=25000.0)
    prof = constitution.load_profile()
    avec = stress_tests.run_stress_tests(snap, prof, options_vega_value=None,
                                         options_open=2)
    sans_perimetre = stress_tests.run_stress_tests(snap, prof,
                                                   options_vega_value=None)
    assert 'sans option ouverte' not in avec['scenarios']['IV_CRUSH']['note']
    assert 'sans option ouverte' in sans_perimetre['scenarios']['IV_CRUSH']['note']


# ── 5. Vocabulaires : ce qui est documenté est ce qui est émis ─────────────

def _etats_reellement_ecrits() -> set[str]:
    """Dérivé des ÉCRIVAINS, jamais recopié — une liste écrite à la main ici se
    périmerait au premier état ajouté, exactement la dérive à l'origine du
    défaut."""
    etats = {'UNKNOWN'}                            # valeur initiale du magasin
    for fichier in ('terminal.py', 'vertex/data_sources/stooq.py'):
        src = (RACINE / fichier).read_text(encoding='utf-8')
        for ligne in re.findall(r'_SOURCE_BUDGET_STATE\[[^\]]+\] = [^\n]+', src):
            etats |= set(re.findall(r"'([A-Z][A-Z_]{2,})'", ligne))
    return etats


def test_le_commentaire_des_caches_nomme_les_etats_reellement_emis():
    """MESURÉ : `vertex/app/caches.py` documentait « 'UNKNOWN' | 'OK' |
    'UNAVAILABLE' » alors que les écrivains émettent AVAILABLE / CACHED /
    NOT_COLLECTED / UNAVAILABLE. `OK` n'a jamais existé comme valeur écrite :
    c'est un vocabulaire inventé par la documentation, sur lequel la page
    Système avait bâti sa liste blanche de sources saines — cinq sources à
    AVAILABLE affichées « dégradé » en permanence."""
    src = (RACINE / 'vertex' / 'app' / 'caches.py').read_text(encoding='utf-8')
    bloc = re.search(r'# Valeurs RÉELLEMENT écrites.*?\n(.*?)\n#\n', src, re.S)
    assert bloc, ('le bloc « Valeurs RÉELLEMENT écrites » a disparu de '
                  'caches.py — sans lui, rien ne garde ce vocabulaire')
    documentes = set(re.findall(r"'([A-Z][A-Z_]{2,})'", bloc.group(1)))
    emis = _etats_reellement_ecrits()
    assert len(emis) >= 5, emis                    # dénominateur non vide
    assert documentes == emis, (
        'le commentaire et les émetteurs ne disent plus la même chose : '
        'documentés %s, émis %s' % (sorted(documentes), sorted(emis)))


# ── 6. Une donnée malformée est NOMMÉE, jamais fatale ─────────────────────

def _option_declaree(**extra):
    base = {'position_id': 'p1', 'symbol': 'MSFT', 'asset_type': 'OPTION',
            'quantity': 1, 'capital_committed': 600, 'currency': 'USD',
            'source': 'MANUAL', 'strike': 500.0, 'right': 'CALL',
            'thesis_text': 'thèse déclarée', 'expiration': '2027-01-15'}
    base.update(extra)
    return base


def test_une_echeance_declaree_sous_forme_de_liste_ne_fait_plus_tomber_l_audit():
    """MESURÉ : `/api/positions/audit` levait `TypeError: unhashable type:
    'list'` — la clé d'identité contenait l'échéance BRUTE. L'audit d'intégrité
    est la route censée SURVIVRE à une donnée malformée pour la nommer."""
    from vertex.positions.audit import audit_positions

    r = audit_positions([_option_declaree(expiration=['2027-01-15'])])
    assert r['status'] == 'DEGRADED'
    assert r['findings'][0]['errors'] == ['EXPIRATION_ILLISIBLE']


def test_deux_echeances_illisibles_restent_distinguees_l_une_de_l_autre():
    """Témoin des deux sens : aucune identité n'est devinée, aucun doublon
    n'est inventé. Deux formes illisibles IDENTIQUES → doublon ; deux formes
    illisibles DIFFÉRENTES → deux contrats."""
    from vertex.positions.audit import audit_positions

    memes = audit_positions([_option_declaree(expiration=['2027-01-15']),
                             _option_declaree(position_id='p2',
                                              expiration=['2027-01-15'])])
    assert memes['status'] == 'CRITICAL'
    assert 'DUPLICATE_IDENTITY' in memes['findings'][1]['errors']

    autres = audit_positions([_option_declaree(expiration=['2027-01-15']),
                              _option_declaree(position_id='p3',
                                               expiration=['2028-01-15'])])
    assert autres['status'] == 'DEGRADED'
    assert all('DUPLICATE_IDENTITY' not in f['errors'] for f in autres['findings'])


def test_le_badge_de_qualite_ne_dit_plus_OK_par_dessus_un_defaut_nomme():
    """MESURÉ sur une option à échéance illisible avec marque 6,00 :
    `overall: 'OK'`, `issues: ['EXPIRATION_ILLISIBLE']`, `dte: None` — la
    synthèse contredisait son propre détail, sur un défaut qui laisse les gates
    de cycle de vie désarmés jusqu'au jour de l'expiration."""
    from vertex.positions import calculator, models

    def _enrichie(exp, quote):
        p = models.option_position({'id': 1, 'sym': 'MSFT', 'type': 'OPT',
                                    'qty': 1, 'cost': 600, 'strike': 500,
                                    'right': 'C', 'exp': exp,
                                    'entrySnap': {'thesis': 't'}})
        calculator.enrich_option(p, quote, None, None, {})
        return p

    illisible = _enrichie('demain', {'mark': 6.0})
    assert illisible['data_quality']['issues'] == ['EXPIRATION_ILLISIBLE']
    assert illisible['data_quality']['overall'] == 'DEGRADED'   # valait 'OK'
    assert illisible.get('dte') is None
    #  Témoins : rien n'est dégradé sans défaut, et les états connus restent
    #  distincts (invariant 5 — absence, périmé et erreur ne se confondent pas).
    assert _enrichie('2027-01-15', {'mark': 6.0})['data_quality']['overall'] == 'OK'
    assert _enrichie('2027-01-15', {'mark': None})['data_quality']['overall'] == 'MISSING_MARK'
    assert _enrichie('2027-01-15', {'mark': 6.0, 'stale': True})[
        'data_quality']['overall'] == 'STALE'


def test_une_detection_qui_n_a_pas_eu_lieu_ne_vaut_pas_zero(monkeypatch, tmp_path):
    """La route corrigeait déjà ces deux compteurs à la frontière ; le MOTEUR
    fabriquait toujours le zéro en amont, et écrivait « IBKR hors ligne » —
    une panne courtier supposée là où il n'y a qu'un choix de produit (IBKR =
    données de marché uniquement). Sortie SERVIE inchangée."""
    from vertex.positions import detector
    from vertex.services import persist

    monkeypatch.setattr(persist, 'load_json', lambda *a, **k: {'ids': {}})
    monkeypatch.setattr(persist, 'save_json', lambda *a, **k: None)
    r = detector.startup_position_report(_desk_une_action(), ibkr_online=False)
    assert r['missing_positions'] is None            # valait 0
    assert r['closed_positions_detected'] is None    # valait 0
    assert 'hors ligne' not in (r['note'] or '')
    assert 'Aucune comparaison au courtier' in r['note']


def test_le_repli_ACTION_porte_la_meme_marque_de_differe_que_le_repli_OPTION():
    """CONSTAT 27, RACINE. Deux écritures du MÊME fait dans la MÊME charge
    `/api/pos-quotes` : le repli OPTION posait `delayed: true`, le repli ACTION
    ne posait que `mode: 'DELAYED'`. Une page qui n'en lit qu'une annonce du
    temps réel sur un prix de scan. Témoin négatif inclus : une cotation LIVE
    ne reçoit aucun `delayed`."""
    from vertex.data_sources.cotation_unifiee import (
        en_charge_client, resoudre_cotation,
    )

    repli = en_charge_client(resoudre_cotation(
        broker=None, secondaire={'spot': 180.0, 'spot_chg': 1.2}))
    assert repli['mode'] == 'DELAYED'
    assert repli['fallback_used'] is True
    assert repli['delayed'] is True                # n'existait pas

    live = en_charge_client(resoudre_cotation(
        broker={'spot': 181.0}, secondaire={'spot': 180.0}))
    assert live['mode'] == 'LIVE'
    assert 'delayed' not in live                   # rien n'est affirmé de faux
