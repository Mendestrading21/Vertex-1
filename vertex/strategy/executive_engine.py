"""vertex.strategy.executive_engine — LA seule couche de décision finale (§27).

La DecisionStack reste le socle analytique ; ce moteur exécutif est LE point
unique qui produit la décision utilisateur finale, dans le vocabulaire de la
constitution : ACHETER / RENFORCER / ATTENDRE / REDUIRE / REFUSER.
Déterministe : mêmes entrées → même décision. Aucune autre couche (comité,
scorecard, options_lab, recommandation) n'a le droit de publier une décision
finale — leurs sorties sont des ENTRÉES de ce moteur.
"""
from __future__ import annotations

from vertex.strategy import constitution as _constitution

FINAL_DECISIONS = _constitution.ALLOWED_FINAL_DECISIONS  # ACHETER RENFORCER ATTENDRE REDUIRE REFUSER

# Règles bloquantes reconnues (chacune plafonne ou force la décision)
BLOCKING_TO_MAX_DECISION = {
    'RR_BELOW_MINIMUM': 'ATTENDRE',
    'REGIME_BLOCKS_NEW_RISK': 'ATTENDRE',
    'DATA_QUALITY': 'ATTENDRE',
    'SOURCE_DISAGREEMENT': 'ATTENDRE',
    'BLOCKING_ANOMALY': 'ATTENDRE',
    'NO_NEW_RISK': 'ATTENDRE',
    'PORTFOLIO_DRAWDOWN_LIMIT': 'ATTENDRE',
    'MAX_OPTIONS_REACHED': 'ATTENDRE',
    'PORTFOLIO_FULL_NO_REPLACEMENT': 'ATTENDRE',
    'DECISION_PACKET_INCOMPLETE': 'ATTENDRE',
    'THESIS_INVALIDATED': 'REDUIRE',
}

_ORDER = ('REFUSER', 'REDUIRE', 'ATTENDRE', 'RENFORCER', 'ACHETER')


def _cap(decision: str, ceiling: str) -> str:
    """Plafonne une décision (ACHETER plafonné à ATTENDRE → ATTENDRE)."""
    return decision if _ORDER.index(decision) <= _ORDER.index(ceiling) else ceiling


def decide(packet: dict, profile=None) -> dict:
    """packet — dossier complet du symbole :
    {'symbol','asset_type','fundamental','catalysts','technical','sentiment',
     'anomalies','institutional_context','portfolio_fit','option_selection',
     'scenarios','data_quality','reconciliation','guard','position_held',
     'position_pl_pct','scores':{...}}.

    Sortie : structure §27, final_decision ∈ constitution uniquement.
    """
    profile = profile or _constitution.load_profile()
    symbol = packet.get('symbol', '')
    audit: list[str] = []
    blocking: list[str] = []
    unknowns: list[str] = []

    # ── 1. Règles bloquantes (hard gates) ─────────────────────────────
    dq = packet.get('data_quality') or {}
    if dq and not dq.get('actionable_allowed', True):
        blocking.append('DATA_QUALITY')
        audit.append(f"qualité de données {dq.get('overall', '?')} — ACTIONABLE interdit")
    rec = packet.get('reconciliation') or {}
    if rec and not rec.get('actionable_allowed', True):
        blocking.append('SOURCE_DISAGREEMENT')
        audit.append('sources non réconciliées — décision maximale ATTENDRE')
    anomalies = packet.get('anomalies') or []
    if any((a.get('blocking') if isinstance(a, dict) else getattr(a, 'blocking', False))
           for a in anomalies):
        blocking.append('BLOCKING_ANOMALY')
        audit.append('anomalie bloquante détectée')
    guard = packet.get('guard') or {}
    for rule in guard.get('blocking_rules') or []:
        if rule in BLOCKING_TO_MAX_DECISION:
            blocking.append(rule)
            if rule == 'DECISION_PACKET_INCOMPLETE':
                missing = ', '.join(guard.get('missing_sections') or []) or 'sections critiques'
                audit.append(f'paquet décisionnel incomplet: {missing}')
            else:
                audit.append(f'garde-fou portefeuille: {rule}')
    fit = packet.get('portfolio_fit') or {}
    if fit.get('blocked'):
        blocking.append('PORTFOLIO_FULL_NO_REPLACEMENT')
        audit.append('portefeuille plein sans remplacement — aucune 11e position automatique')
    tech = packet.get('technical') or {}
    if tech.get('thesis_invalidated'):
        blocking.append('THESIS_INVALIDATED')
        audit.append('thèse invalidée')
    # Hard gate constitution : R:R structurel < 2:1 → jamais ACHETER/RENFORCER.
    _rr_gate = tech.get('reward_risk')
    if _rr_gate is not None and float(_rr_gate) < 2.0:
        blocking.append('RR_BELOW_MINIMUM')
        audit.append(f'R:R {_rr_gate} < 2:1 — ACHETER/RENFORCER interdits (constitution)')
    # Hard gate régime : UNKNOWN ou nouveau risque bloqué par le régime.
    regime_ctx = packet.get('market_regime') or {}
    _adj = regime_ctx.get('adjustments') or {}
    if regime_ctx and (_adj.get('new_risk_allowed') is False
                       or regime_ctx.get('regime') == 'UNKNOWN'):
        blocking.append('REGIME_BLOCKS_NEW_RISK')
        audit.append(f"régime {regime_ctx.get('regime', '?')} — nouveau risque bloqué")

    # ── 2. Scores agrégés (déterministes) ─────────────────────────────
    def _score(block: dict | None, key: str = 'score'):
        if not block:
            return None
        v = block.get(key)
        return float(v) if v is not None else None

    conviction_parts = []
    for name in ('fundamental', 'catalysts', 'technical', 'sentiment'):
        s = _score(packet.get(name))
        if s is None:
            unknowns.append(name)
        else:
            conviction_parts.append(s)
    conviction = round(sum(conviction_parts) / len(conviction_parts), 1) \
        if conviction_parts else 0.0
    rr = tech.get('reward_risk')
    asym = 0.0
    if rr is not None:
        asym = round(min(100.0, max(0.0, (rr - 1.0) * 40)), 1)
    else:
        unknowns.append('reward_risk')
    dq_score = {'FRESH': 100, 'RECENT': 75, 'STALE': 30,
                'EXPIRED': 0, 'MISSING': 0}.get(dq.get('overall'), 50)
    risk_score = 100.0
    if guard.get('blocking_rules'):
        risk_score = 0.0
    elif guard.get('mandatory_reviews'):
        risk_score = 40.0
    timing = _score(tech, 'timing_score')
    if timing is None:
        # Le neutre 50.0 est une SUBSTITUTION, pas une mesure : publié nu dans
        # `scores`, il était indiscernable d'un timing réellement calculé (mesure :
        # `scores.timing = 50.0` sur des titres dont aucune note de timing n'existe,
        # `timing_score` n'ayant aucun producteur dans le dépôt). On garde la valeur
        # pour ne déplacer aucun seuil, mais l'absence est NOMMÉE dans `unknowns` —
        # le canal d'ignorance déjà servi à l'utilisateur dans l'audit_trail.
        # `unknowns_critical` ne retient que fundamental/technical : aucune décision
        # ne change, seule l'honnêteté du dossier change.
        timing = 50.0 if tech else 0.0
        unknowns.append('timing')
        audit.append('timing non mesuré — neutre 50.0 substitué (aucune note de '
                     'timing calculée pour ce titre)')
    scores = {'conviction': conviction, 'risk': risk_score, 'timing': timing,
              'asymmetry': asym, 'data_quality': dq_score}

    # ── 3. Décision de base ───────────────────────────────────────────
    held = bool(packet.get('position_held'))
    pl = packet.get('position_pl_pct')
    if held and (tech.get('thesis_invalidated')
                 or (pl is not None and profile is not None
                     and pl <= profile.stock_max_drawdown_pct)):
        decision = 'REDUIRE'
        audit.append('position détenue avec thèse invalidée ou drawdown titre dépassé → REDUIRE')
    elif conviction >= 70 and asym >= 40 and timing >= 50 and not unknowns_critical(unknowns):
        decision = 'RENFORCER' if held else 'ACHETER'
        audit.append(f'conviction {conviction}, asymétrie {asym}, timing {timing}')
    elif conviction >= 55:
        decision = 'ATTENDRE'
        audit.append(f'conviction {conviction} intéressante mais dossier incomplet '
                     f'(asym {asym}, timing {timing}, inconnues {unknowns})')
    elif conviction > 0:
        decision = 'REFUSER'
        audit.append(f'conviction {conviction} insuffisante')
    else:
        decision = 'ATTENDRE'
        audit.append('dossier vide — impossible de refuser ou d’acheter, ATTENDRE')

    # ── 4. Application des plafonds bloquants ─────────────────────────
    for rule in blocking:
        ceiling = BLOCKING_TO_MAX_DECISION[rule]
        if rule == 'THESIS_INVALIDATED' and held:
            decision = 'REDUIRE'
        else:
            capped = _cap(decision, ceiling)
            if capped != decision:
                audit.append(f'{rule}: {decision} plafonné à {capped}')
                decision = capped

    assert decision in FINAL_DECISIONS
    return {
        'symbol': symbol,
        'asset_type': packet.get('asset_type', 'STOCK'),
        'analysis_order': list(profile.analysis_order),
        'fundamental': packet.get('fundamental') or {},
        'catalysts': packet.get('catalysts') or {},
        'technical': tech,
        'sentiment': packet.get('sentiment') or {},
        'anomalies': [a if isinstance(a, dict) else a.to_dict() for a in anomalies],
        'institutional_context': packet.get('institutional_context') or {},
        'portfolio_fit': fit,
        'option_selection': packet.get('option_selection') or {},
        'scenarios': packet.get('scenarios') or {},
        'execution_plan': packet.get('execution_plan') or {},
        'scores': scores,
        'blocking_rules': blocking,
        'unknowns': unknowns,
        'audit_trail': audit,
        'final_decision': decision,
    }


def unknowns_critical(unknowns: list[str]) -> bool:
    return bool({'fundamental', 'technical'} & set(unknowns))
