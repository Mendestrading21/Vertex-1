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
    return {'score': value, 'is_proxy': bool(sub.get('fundamental_is_proxy'))}


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
    """
    return {
        'score': None,
        'earnings_dte': detail.get('earnings_dte'),
        'derived': True,
        'warning': 'proximité de résultats connue mais notation de catalyseur non '
                   'calculée (nature, nouveauté et pricing non évalués)',
    }


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
    plan = detail.get('plan') or {}
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
            'reward_risk': detail.get('rr') or (plan.get('rr') if isinstance(plan, dict) else None),
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


__all__ = ['build', 'INCOMPLETE_PACKET_RULE', 'CRITICAL_SECTIONS']
