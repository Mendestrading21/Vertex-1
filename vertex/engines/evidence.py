"""
vertex/engines/evidence.py — LE COMITÉ D'ANALYSTES (couche de preuves).

Chaque analyste est indépendant et ne connaît qu'un domaine (marché, structure,
technique, momentum, options, risque, qualité de données). Il produit des
PREUVES atomiques — jamais une décision. La DecisionStack synthétise ensuite.

Règle non négociable (Ch. IV / Loi 14) : les CONTRADICTIONS sont exposées,
jamais cachées. Chaque preuve porte sa force, son domaine, son signe.
"""

POSITIVE = 'positive'
NEGATIVE = 'negative'
NEUTRAL = 'neutral'
UNKNOWN = 'unknown'
CONTRADICTORY = 'contradictory'


def _ev(kind, text, strength, source):
    return {'kind': kind, 'text': text, 'strength': int(max(0, min(100, strength))), 'source': source}


def _num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def rr_mesure(d):
    """R:R MESURÉ du plan (``plan['rr_res']``) ou None — LECTEUR CANONIQUE.

    Une seule autorité pour « quel est le rapport gain/risque de ce plan ? » :
    `evidence.risk_analyst` et `decision_stack` (règle 5 + points de bascule)
    lisaient la même clé avec deux conversions différentes, toutes deux fondées
    sur un défaut 0.0 qui rendait l'absence indiscernable d'un zéro mesuré.
    `evidence` est la couche basse (`decision_stack` l'importe déjà) : le
    lecteur vit donc ici et le moteur de décision le réutilise.

    Un 0.0 MESURÉ traverse (c'est le pire cas de ``analysis.py:252``, pas une
    absence) ; une clé absente, une chaîne, un booléen, NaN ou l'infini rendent
    None, et chaque appelant NOMME alors l'inconnue.
    """
    v = (d.get('plan') or {}).get('rr_res') if isinstance(d, dict) else None
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float('inf'), float('-inf')) else None


def market_analyst(market):
    if not market:
        return []
    out = []
    if market.get('roro') == 'RISK-ON':
        out.append(_ev(POSITIVE, 'Marché RISK-ON — appétit pour le risque', 70, 'Marché'))
    if market.get('roro') == 'RISK-OFF':
        out.append(_ev(NEGATIVE, 'Marché RISK-OFF — aversion au risque', 80, 'Marché'))
    if market.get('spy_regime') == 'TREND':
        out.append(_ev(POSITIVE, 'Régime de marché en tendance', 60, 'Marché'))
    if market.get('spy_regime') == 'CHOP':
        out.append(_ev(NEGATIVE, 'Marché en range — cassures fragiles', 55, 'Marché'))
    return out


def structure_analyst(d):
    out = []
    phy = (d.get('physics') or {}).get('state')
    if phy == 'TENDANCE FRACTALE':
        out.append(_ev(POSITIVE, 'Structure fractale persistante (mémoire longue)', 65, 'Physique'))
    elif phy == 'CHAOS':
        out.append(_ev(NEGATIVE, 'Structure chaotique — mouvement imprévisible', 70, 'Physique'))
    mtf = (d.get('mtf') or {}).get('state')
    if mtf == 'ALIGNÉ HAUSSIER':
        out.append(_ev(POSITIVE, 'Journalier et hebdomadaire alignés à la hausse', 75, 'Multi-horizons'))
    elif mtf == 'REBOND CONTRE-TENDANCE':
        out.append(_ev(NEGATIVE, 'Rebond à contre-courant de l\'hebdo baissier', 65, 'Multi-horizons'))
    elif mtf == 'ALIGNÉ BAISSIER':
        out.append(_ev(NEGATIVE, 'Journalier et hebdomadaire alignés à la baisse', 75, 'Multi-horizons'))
    return out


def technical_analyst(d):
    out = []
    sig = d.get('signals') or {}
    if sig.get('stacked'):
        out.append(_ev(POSITIVE, 'Moyennes mobiles empilées (tendance propre)', 65, 'Technique'))
    if d.get('breakout'):
        out.append(_ev(POSITIVE, 'Cassure confirmée par le volume', 70, 'Technique'))
    if d.get('pullback'):
        out.append(_ev(POSITIVE, 'Repli sain sur tendance (meilleur R:R)', 68, 'Technique'))
    if not sig.get('above200', True):
        out.append(_ev(NEGATIVE, 'Sous la MM200 — tendance de fond fragile', 70, 'Technique'))
    if d.get('distribution'):
        out.append(_ev(NEGATIVE, 'Distribution cachée (OBV/prix divergents)', 65, 'Technique'))
    if _num(d.get('ext_atr')) >= 4:
        out.append(_ev(NEGATIVE, f'Sur-étendu ({_num(d.get("ext_atr")):.1f} ATR)', 60, 'Technique'))
    return out


def momentum_analyst(d):
    out = []
    rs = _num(d.get('rs'), 50)
    if rs >= 70:
        out.append(_ev(POSITIVE, f'Surperforme le marché (force relative {int(rs)})', 65, 'Momentum'))
    elif rs <= 35:
        out.append(_ev(NEGATIVE, f'Sous-performe le marché (force relative {int(rs)})', 60, 'Momentum'))
    if d.get('rsi_div') == 'bear':
        out.append(_ev(NEGATIVE, 'Divergence RSI baissière', 55, 'Momentum'))
    return out


def options_analyst(option):
    if not option:
        return []
    out = []
    if _num(option.get('quality')) >= 65:
        out.append(_ev(POSITIVE, 'Option de bonne qualité disponible', 55, 'Options'))
    if _num(option.get('iv')) >= 90:
        out.append(_ev(NEGATIVE, 'IV élevée — options coûteuses', 60, 'Options'))
    sp = option.get('spread')
    if sp is not None and _num(sp) > 8:
        out.append(_ev(NEGATIVE, 'Option illiquide (spread large)', 55, 'Options'))
    return out


def risk_analyst(d, portfolio):
    out = []
    #  `_num(..., 0.0)` puis `if rr and …` : un R:R MESURÉ à 0.0 tombait entre
    #  les deux branches et l'analyste risque restait MUET. Mesuré sur
    #  `risk_analyst({'plan': {'rr_res': X}}, None)` :
    #      rr_res 0.1 -> 1 preuve NEGATIVE force 65
    #      rr_res 0.0 -> 0 preuve      (le pire R:R possible, aucune preuve)
    #      rr_res absent -> 0 preuve   (indiscernable du zéro mesuré)
    #  Le silence remontait tel quel dans `_committee` (`lean = pos/(pos+neg)`)
    #  : la preuve négative la plus forte du domaine Risque disparaissait, donc
    #  l'accord et la confiance du comité MONTAIENT au pire cas. Le zéro mesuré
    #  est désormais une preuve négative comme les autres, et l'absence est une
    #  INCONNUE nommée — jamais un silence qui se lit « rien à signaler ».
    rr = rr_mesure(d)
    if rr is None:
        #  Un PLAN existe mais sans ratio mesuré : l'inconnue est nommée dans le
        #  canal prévu (`gather()['unknown']`, « ce que nous ne savons pas »).
        #  Sans plan du tout, l'analyste reste muet comme tous les autres — un
        #  détail vide ne fabrique aucune preuve (test_evidence_edges).
        if (d or {}).get('plan'):
            out.append(_ev(UNKNOWN, 'Risque/récompense non mesuré au plan', 50, 'Risque'))
    elif rr >= 2:
        out.append(_ev(POSITIVE, f'Risque/récompense favorable ({rr:.1f}:1)', 60, 'Risque'))
    else:
        # Sous le minimum stratégie (2:1) : preuve négative — jamais de zone
        # 1,5–2,0 « acceptable » qui contredirait le hard gate.
        out.append(_ev(NEGATIVE, f'Risque/récompense sous le minimum 2:1 ({rr:.1f}:1)', 65, 'Risque'))
    if d.get('anomaly_lvl') == 'ALERTE':
        out.append(_ev(NEGATIVE, 'Radar ALERTE — comportement hors-norme', 60, 'Risque'))
    if portfolio and _num(portfolio.get('max_correlation')) >= 0.8:
        out.append(_ev(NEGATIVE, 'Corrélation élevée avec le portefeuille', 70, 'Portefeuille'))
    return out


def fundamental_analyst(d):
    """Le fondamental : la société est-elle solide RELATIVEMENT à son secteur ?"""
    out = []
    fs = _num((d.get('sub') or {}).get('fundamental'))
    if fs >= 70:
        out.append(_ev(POSITIVE, f'Fondamentaux solides vs secteur (note {int(fs)})', 55, 'Fondamental'))
    elif 0 < fs <= 35:
        out.append(_ev(NEGATIVE, f'Fondamentaux fragiles vs secteur (note {int(fs)})', 55, 'Fondamental'))
    return out


def catalyst_analyst(d):
    """Le catalyseur : un comportement inhabituel (volume/gap) signale un événement possible."""
    vz = _num(d.get('vol_z'))
    gap = abs(_num(d.get('gap_pct')))
    if vz >= 2.5 or gap >= 4:
        why = 'volume anormal' if vz >= 2.5 else 'gap marqué'
        return [_ev(NEUTRAL, f'Activité inhabituelle ({why}) — catalyseur possible à vérifier', 45, 'Catalyseur')]
    return []


def relative_analyst(context):
    """L'analyste transversal : où se situe le titre PARMI l'univers scanné (Ch. IX)."""
    if not context:
        return []
    out = []
    sc = next((d for d in context.get('dimensions', []) if d['key'] == 'score'), None)
    if sc and sc.get('pct_universe') is not None:
        if sc['standing'] == 'leader':
            out.append(_ev(POSITIVE, f'Parmi les meilleurs de l\'univers scanné (top {100 - sc["pct_universe"]}%)',
                           55, 'Transversal'))
        elif sc['standing'] == 'retardataire':
            out.append(_ev(NEGATIVE, f'Parmi les plus faibles de l\'univers scanné (bas {sc["pct_universe"]}%)',
                           50, 'Transversal'))
    if context.get('sector_rank') == 1 and (context.get('sector_n') or 0) >= 3:
        out.append(_ev(POSITIVE, f'Leader de son secteur ({context.get("sector")})', 50, 'Transversal'))
    return out


def data_quality_analyst(dq):
    if not dq:
        return []
    if dq.get('missing_fields'):
        return [_ev(UNKNOWN, 'Champs de données manquants', 50, 'Qualité données')]
    if dq.get('stale'):
        return [_ev(NEGATIVE, 'Données rassies — confiance réduite', 45, 'Qualité données')]
    return []


def _contradictions(d, items):
    """Expose les tensions internes (jamais cachées) — Loi 14."""
    out = []
    strong_price = _num(d.get('pos52'), 0) >= 80 or (d.get('signals') or {}).get('above200')
    weak_mom = _num(d.get('rs'), 50) <= 40 or d.get('rsi_div') == 'bear'
    if strong_price and weak_mom:
        out.append(_ev(CONTRADICTORY, 'Prix fort mais momentum faible — tension à surveiller', 60, 'Synthèse'))
    if (d.get('physics') or {}).get('state') == 'CHAOS' and (d.get('signals') or {}).get('stacked'):
        out.append(_ev(CONTRADICTORY, 'Tendance affichée mais structure chaotique', 55, 'Synthèse'))
    return out


# ─── Pondération par régime : un même signal ne pèse pas pareil selon le marché ───
# En tendance, la structure/le momentum comptent plus ; en range, ils comptent moins et
# le risque compte plus ; en RISK-OFF, toute preuve négative est amplifiée (prudence).
_REGIME_WEIGHTS = {
    'TREND':   {'Momentum': 1.2, 'Multi-horizons': 1.2, 'Physique': 1.15, 'Technique': 1.1},
    'CHOP':    {'Momentum': 0.75, 'Technique': 0.8, 'Multi-horizons': 0.85,
                'Risque': 1.2, 'Portefeuille': 1.15},
    'NEUTRAL': {},
}


def _apply_regime(items, market):
    """Ajuste la force de chaque preuve selon le régime et le risk-on/off (jamais < 0, borné 100)."""
    if not market:
        return items
    regime = market.get('spy_regime')
    risk_off = market.get('roro') == 'RISK-OFF'
    weights = _REGIME_WEIGHTS.get(regime, {})
    for it in items:
        mult = weights.get(it['source'], 1.0)
        if risk_off and it['kind'] == NEGATIVE:
            mult *= 1.25
        if mult != 1.0:
            it['strength'] = int(max(0, min(100, round(it['strength'] * mult))))
            it['regime_weighted'] = True
    return items


def gather(detail, *, market=None, option=None, portfolio=None, data_quality=None, context=None):
    """Réunit toutes les preuves des analystes, catégorisées, pondérées par régime, avec contradictions."""
    d = detail or {}
    items = (market_analyst(market) + structure_analyst(d) + technical_analyst(d)
             + momentum_analyst(d) + fundamental_analyst(d) + catalyst_analyst(d)
             + relative_analyst(context) + options_analyst(option) + risk_analyst(d, portfolio)
             + data_quality_analyst(data_quality))
    items = _apply_regime(items, market)
    items += _contradictions(d, items)          # les tensions ne sont pas pondérées
    buckets = {POSITIVE: [], NEGATIVE: [], NEUTRAL: [], UNKNOWN: [], CONTRADICTORY: []}
    for it in items:
        buckets[it['kind']].append(it)
    for k in buckets:
        buckets[k].sort(key=lambda x: x['strength'], reverse=True)
    buckets['balance'] = (sum(x['strength'] for x in buckets[POSITIVE])
                          - sum(x['strength'] for x in buckets[NEGATIVE]))
    buckets['has_contradiction'] = bool(buckets[CONTRADICTORY])
    buckets['regime'] = (market or {}).get('spy_regime')
    return buckets


__all__ = ['gather', 'rr_mesure',
           'POSITIVE', 'NEGATIVE', 'NEUTRAL', 'UNKNOWN', 'CONTRADICTORY']
