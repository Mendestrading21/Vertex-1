"""Construction déterministe du paquet de décision servi par Strategy OS.

Ce module interdit la complétude implicite : une route peut dériver des éléments
purement descriptifs à partir du scan, mais les preuves critiques absentes
(réconciliation des sources ou risque portefeuille) restent visibles et plafonnent
la décision à ``ATTENDRE``. Il ne déclenche aucun ordre et ne conserve aucune donnée.
"""
from __future__ import annotations

from vertex.engines.anomaly_context import build as build_anomaly_context
from vertex.engines.market_context import regime_inputs
from vertex.market.regime_engine import classify_regime

INCOMPLETE_PACKET_RULE = 'DECISION_PACKET_INCOMPLETE'
CRITICAL_SECTIONS = ('data_quality', 'reconciliation', 'guard')


def _source_quality(scan_state: dict, detail: dict) -> tuple[dict, bool]:
    supplied = detail.get('data_quality') or scan_state.get('data_quality')
    if isinstance(supplied, dict) and 'actionable_allowed' in supplied:
        out = dict(supplied)
        out.setdefault('overall', 'MISSING')
        out['derived'] = False
        return out, True
    source = scan_state.get('source') or ''
    overall = 'DEMO' if source == 'demo' else ('RECENT' if source else 'MISSING')
    return {
        'overall': overall,
        'actionable_allowed': bool(source and source != 'demo'),
        'derived': True,
        'warning': 'qualité dérivée du scan global — paquet valeur par valeur absent',
    }, False


def _reconciliation(scan_state: dict, detail: dict) -> tuple[dict, bool]:
    supplied = detail.get('reconciliation') or scan_state.get('reconciliation')
    if isinstance(supplied, dict) and 'actionable_allowed' in supplied:
        out = dict(supplied)
        out['derived'] = False
        return out, True
    return {
        'actionable_allowed': False,
        'derived': True,
        'warning': 'réconciliation spot/chaîne/contrat absente — décision actionnable interdite',
    }, False


def _guard(scan_state: dict, detail: dict) -> tuple[dict, bool]:
    supplied = detail.get('guard') or scan_state.get('guard')
    if isinstance(supplied, dict):
        out = dict(supplied)
        out.setdefault('blocking_rules', [])
        out.setdefault('mandatory_reviews', [])
        out['derived'] = False
        return out, True
    return {
        'blocking_rules': [],
        'mandatory_reviews': [],
        'derived': True,
        'warning': 'risque portefeuille non calculé pour ce paquet',
    }, False


def _actual_anomalies(symbol: str, detail: dict) -> list[dict]:
    context = build_anomaly_context(symbol, detail)
    return context.get('events') or []


def _fundamental(detail: dict) -> dict:
    """Note fondamentale du scan, lue chez son SEUL producteur : ``detail['sub']``.

    Ce lecteur remplace ``detail['st_fund'] or detail['fund_score']``, deux clés
    SANS producteur sur le detail du scan : `fund_score` n'est assignée nulle part
    dans le dépôt, et `st_fund` n'est posée que sur la LIGNE de tableau
    (terminal.py:609), jamais sur le dict `detail` que reçoit ce module. Mesure du
    défaut : sur un scan réel de 513 titres, `/api/ticker/NVDA` servait
    ``sub = {'fundamental': 100, 'fundamental_is_proxy': False, ...}`` pendant que
    le paquet publiait ``fundamental.score = None`` ; 40/40 titres balayés
    portaient donc 'fundamental' dans `unknowns`, et `unknowns_critical` rendait
    la branche ACHETER/RENFORCER inatteignable pour TOUT l'univers, en permanence.
    Une valeur MESURÉE présentée comme une absence viole l'invariant 5 aussi
    sûrement qu'un chiffre inventé. ``evidence.fundamental_analyst`` lisait déjà
    le bon emplacement : ce module s'aligne sur ce propriétaire canonique.

    Sémantique 0 conservée (tests/test_evidence_edges.py:40) : une note à 0
    signifie « fondamentaux non branchés », donc absente — jamais « mauvaise ».
    `is_proxy` voyage avec la note (invariant 6) : un fondamental dérivé d'un
    proxy technique ne doit pas se lire comme une mesure comptable directe.
    """
    sub = detail.get('sub') or {}
    raw = sub.get('fundamental')
    if isinstance(raw, bool):        # un booléen n'est pas une note sur 100
        return {'score': None, 'is_proxy': None}
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return {'score': None, 'is_proxy': None}
    # NaN/inf : une note illisible reste une inconnue, jamais un chiffre servi.
    if value != value or value in (float('inf'), float('-inf')) or value == 0.0:
        return {'score': None, 'is_proxy': None}
    #  Second tour — le lignage ABSENT ne se lit plus « mesure directe ».
    #  Mesure : `bool(sub.get('fundamental_is_proxy'))` rendait `is_proxy: False`
    #  pour un producteur MUET (clé absente du `sub`) exactement comme pour un
    #  producteur qui affirme « note comptable directe ». Deux états distincts
    #  (invariant 5) servis sous le même faux booléen ; `None` dit l'ignorance.
    #  Aucun seuil ne bouge : les consommateurs testent la vérité du drapeau, et
    #  None est falsy comme l'était False.
    proxy = sub.get('fundamental_is_proxy')
    return {'score': value, 'is_proxy': (None if proxy is None else bool(proxy))}


def _catalysts(detail: dict) -> dict:
    """Catalyseur : proximité de résultats DÉCRITE, jamais notée d'un chiffre inventé.

    Le code posait ``60 if detail.get('earnings_dte') is not None else None``.
    Mesure : `earnings_dte` valant -400 (résultats vieux de 400 jours), 20 ou 9999
    (dans 27 ans) rendait le MÊME 60 — la valeur ne mesurait rien. Pire que le
    chiffre lui-même, il RETIRAIT 'catalysts' de `unknowns` (mesuré : unknowns
    ['catalysts'] → [] dès que le champ est peuplé) et entrait dans `conviction`
    comme un quart d'un score affiché, sans aucun marqueur de lignage.
    Le scanner écarte déjà les titres à 0-7 jours de résultats pour le risque de
    gap (vertex/scanner/weekly.py:167) : noter identiquement un catalyseur à 2
    jours et à 300 jours inverserait un risque que le reste du code respecte.
    Tant qu'aucun moteur ne MESURE la nature, la nouveauté et le pricing du
    catalyseur, la note reste None et l'échéance reste une métadonnée descriptive.

    Second tour — le texte est CONDITIONNEL à l'échéance. Mesuré sur
    ``build('ZZ', {'score': 78}, ...)`` (aucune date) : le bloc rendait
    ``earnings_dte: None`` sous le warning « proximité de résultats CONNUE » et
    ``derived: True``. Deux affirmations fausses au même endroit : rien n'était
    connu et rien n'avait été dérivé. Une absence décrite comme une proximité
    connue est une donnée SUPPOSÉE, interdite au même titre qu'un chiffre
    inventé. Une échéance non numérique (chaîne, booléen) n'est pas une échéance :
    elle est ramenée à None plutôt que servie telle quelle.
    """
    dte = detail.get('earnings_dte')
    connue = isinstance(dte, (int, float)) and not isinstance(dte, bool)
    return {
        'score': None,
        'earnings_dte': dte if connue else None,
        # `derived` = « ce bloc a été dérivé d'une donnée réelle ». Sans échéance,
        # rien n'a été dérivé : le drapeau doit le dire.
        'derived': connue,
        'warning': ('proximité de résultats connue (J%+d) mais notation de catalyseur '
                    'non calculée (nature, nouveauté et pricing non évalués)' % dte)
        if connue else
        ('aucune échéance de résultats dans ce paquet — ni proximité connue, '
         'ni catalyseur noté'),
    }


def _num(x):
    """Nombre fini ou None — un 0.0 MESURÉ traverse, une chaîne/NaN devient None."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float('inf'), float('-inf')) else None


def _reward_risk(detail: dict) -> float | None:
    """Rapport gain/risque MESURÉ, lu chez son producteur : ``plan['rr_res']``.

    Le corps précédent lisait ``detail['rr'] or plan['rr']``. Or ``plan['rr']``
    est un LITTÉRAL : ``vertex/engines/analysis.py:265`` écrit ``'rr': 3.0`` en
    dur, à côté de ``tp3 = last + 3 * risk`` — c'est la reformulation de la
    construction de TP3, pas une mesure du titre. Et le `detail` d'un scan ne
    porte AUCUNE clé `rr` de premier niveau (vérifié sur le dict retourné par
    ``analysis.analyse`` : `rr` n'y figure pas ; seule la LIGNE de tableau la
    reçoit, via ``strategy_fit._attach_strategy``). Le repli était donc le
    chemin NORMAL, pour tout l'univers.

    Mesure du défaut, instance 5003, 2026-09-06, 8 titres —
    ``/api/strategy/decision/<sym>`` contre ``/api/ticker/<sym>`` :

        symbole  technical.reward_risk  scores.asymmetry  plan.rr_res (mesuré)
        AAPL     3.0                    80.0              1.3
        MSFT     3.0                    80.0              0.7
        NVDA     3.0                    80.0              0.2
        TSLA     3.0                    80.0              1.4
        AMD      3.0                    80.0              1.7
        META     3.0                    80.0              1.4
        GOOGL    3.0                    80.0              2.3
        AMZN     3.0                    80.0              1.7

    8/8 servaient la même constante ; 7/8 étaient en réalité SOUS le minimum
    2:1 de la constitution. Conséquences dans ``executive_engine`` :
      - ``RR_BELOW_MINIMUM`` (``3.0 < 2.0`` faux) ne s'est allumé 0 fois sur 8
        — la garde dure la plus citée du produit était morte sur tout l'univers,
        franchie par une valeur SUPPOSÉE et non mesurée ;
      - ``scores.asymmetry = (3.0 - 1) * 40 = 80.0`` était une constante servie
        comme une note, et la condition ``asym >= 40`` de la branche
        ACHETER/RENFORCER était donc satisfaite en permanence.

    ``plan['rr_res'] = (résistance 40 barres − dernier cours) / risque`` est le
    propriétaire canonique déjà lu par ``decision_stack``, ``evidence``,
    ``committee``, ``skyler_core`` et ``scanner/weekly``. ``detail['rr']`` reste
    prioritaire (les LIGNES et le desk le posent depuis ce même `rr_res`), mais
    par test NUMÉRIQUE et non par `or` : un R:R mesuré à 0.0 est le pire cas
    possible, pas une absence, et il ne doit plus glisser vers le repli suivant.
    Sans mesure, la valeur reste None : ``executive_engine`` nomme alors
    `reward_risk` dans ``unknowns`` et l'asymétrie tombe à 0 — une inconnue,
    jamais un neutre.
    """
    detail = detail or {}
    direct = _num(detail.get('rr'))
    if direct is not None:
        return direct
    plan = detail.get('plan')
    return _num(plan.get('rr_res')) if isinstance(plan, dict) else None


def _market_regime(scan_state: dict) -> dict:
    """Régime de marché via le mapping CANONIQUE ``market_context.regime_inputs``.

    Le corps précédent lisait ``scan_state['market'].{regime,spy_trend,breadth,vix}``.
    Mesure : `scan_state['market']` est l'HORLOGE de séance produite par
    ``market_clock.market_status()`` — clés réelles ['et','open','session'] — et ne
    porte aucune dimension de régime. Les quatre entrées arrivaient donc None, le
    classifieur dégradait honnêtement en UNKNOWN (confidence 0.0, dimensions []),
    et `REGIME_BLOCKS_NEW_RISK` s'allumait sur 15/15 des titres du scan avec un
    audit « régime UNKNOWN — nouveau risque bloqué ». Au même instant et sur le
    même `scan_state`, `/api/market/regime` rendait CHOP, confidence 0.6, quatre
    dimensions et `new_risk_allowed: True` : deux autorités contradictoires pour
    une même capacité. La garde dure la plus visible du produit était neutralisée
    en se faisant passer pour active — si le marché passait réellement en PANIC,
    rien ne l'aurait distingué du blocage permanent.
    `regime_inputs` sait lire `market_ctx`/`macro` et accepte l'ancienne forme
    `market.{regime,breadth,vix,risk}` en repli : aucun seuil, aucun moteur et
    aucune donnée ne changent, seule l'entrée cesse d'être vide par construction.
    """
    try:
        return classify_regime(regime_inputs(scan_state))
    except Exception as exc:  # un classifieur indisponible ne doit jamais autoriser un trade
        return {'regime': 'UNKNOWN', 'adjustments': {'new_risk_allowed': False},
                'warning': 'classifieur de régime indisponible: %s' % type(exc).__name__}


def build(symbol: str, detail: dict | None, scan_state: dict | None) -> dict:
    """Construit un paquet prêt pour ``executive_engine.decide``.

    Le statut `complete` signifie que les trois preuves critiques proviennent d’un
    calcul explicite. Les métriques descriptives peuvent rester disponibles lorsque
    le paquet est incomplet, mais une entrée nouvelle est alors bloquée.
    """
    detail = detail or {}
    scan_state = scan_state or {}
    data_quality, quality_complete = _source_quality(scan_state, detail)
    reconciliation, reconciliation_complete = _reconciliation(scan_state, detail)
    guard, guard_complete = _guard(scan_state, detail)
    completeness = {
        'data_quality': quality_complete,
        'reconciliation': reconciliation_complete,
        'guard': guard_complete,
    }
    missing = [name for name in CRITICAL_SECTIONS if not completeness[name]]
    blocking_rules = list(guard.get('blocking_rules') or [])
    if missing and INCOMPLETE_PACKET_RULE not in blocking_rules:
        blocking_rules.append(INCOMPLETE_PACKET_RULE)
    guard['blocking_rules'] = blocking_rules
    guard['packet_complete'] = not missing
    guard['missing_sections'] = missing

    return {
        'symbol': symbol,
        'fundamental': _fundamental(detail),
        'catalysts': _catalysts(detail),
        'technical': {
            'score': detail.get('score'),
            # Lecteur canonique — JAMAIS `plan['rr']`, littéral 3.0 (voir
            # `_reward_risk`). Une absence reste None, nommée par le moteur.
            'reward_risk': _reward_risk(detail),
            # `st_timing` n'a AUCUN producteur (0 assignation dans le dépôt, 2
            # lectures) : la clé est absente des 66 clés du detail d'un scan réel.
            # Aucune note de timing 0-100 n'est calculée aujourd'hui — scorecard
            # produit un ÉTAT ('timing.state'), pas une note. L'absence est donc
            # dite, et `executive_engine` la nomme dans `unknowns` au lieu de
            # publier son neutre 50.0 comme s'il s'agissait d'une mesure.
            'timing_score': None,
            'timing_status': 'NON_IMPLEMENTE',
            'overextended': (detail.get('ext_atr') or 0) >= 2.5,
            'thesis_invalidated': bool(detail.get('thesis_invalidated')),
        },
        'sentiment': {'score': detail.get('rs')},
        'anomalies': _actual_anomalies(symbol, detail),
        'data_quality': data_quality,
        'reconciliation': reconciliation,
        'guard': guard,
        'market_regime': _market_regime(scan_state),
        'option_selection': detail.get('option_selection') or {},
        'decision_packet': {
            'complete': not missing,
            'missing_sections': missing,
            'completeness': completeness,
            'source': scan_state.get('source') or None,
        },
    }


#  Lecteurs CANONIQUES exportés. Le constat 5 nommait TROIS sites jumeaux qui
#  dupliquaient `detail['st_fund'] or detail['fund_score']` — deux clés sans
#  producteur sur le `detail` du scan. Le paquet est corrigé ; les autres sites
#  doivent RÉUTILISER ce lecteur au lieu d'en écrire une quatrième version.
#  `vertex/app/routes/ai_api.py` (paquet de l'analyste) le fait depuis ce lot ;
#  `vertex/positions/thesis_health.py` et `vertex/positions/recalculator.py`
#  restent à brancher (hors périmètre de ce lot).
read_fundamental = _fundamental
read_catalysts = _catalysts
#  `vertex/positions/recalculator.py:191` ÉCRASE `technical.reward_risk` avec
#  `p['remaining_rr'] or d['rr'] or plan['rr']` : le même repli vers le littéral
#  3.0, sur le plan de travail des positions détenues. Hors périmètre de ce lot,
#  mais le lecteur canonique est exporté pour qu'il n'en écrive pas un second.
read_reward_risk = _reward_risk

__all__ = ['build', 'read_fundamental', 'read_catalysts', 'read_reward_risk',
           'INCOMPLETE_PACKET_RULE', 'CRITICAL_SECTIONS']
