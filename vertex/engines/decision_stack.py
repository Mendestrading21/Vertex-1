"""
vertex/engines/decision_stack.py — LA DÉCISION STACK : la vérité unique de VERTEX.

Un seul objet. Aucune page n'invente sa propre logique : toutes consomment la
sortie de ce moteur. Il ingère marché + titre + scoring + physique + options +
risque + qualité de données, et produit une décision NORMALISÉE, EXPLICABLE,
avec piste d'audit — jamais une certitude, toujours une aide à la décision.

Analyse uniquement. Aucune exécution. Chaque règle appliquée est tracée.
"""

from vertex.engines import evidence, reasoning

# ─── Décisions autorisées (label + tonalité UI) ────────────────────────────
DECISIONS = {
    'STRONG_BUY':        ('Achat fort', 'strong-green'),
    'BUY':               ('Achat', 'green'),
    'BUY_PULLBACK':      ('Achat sur repli', 'blue'),
    'WATCH_BREAKOUT':    ('Surveiller la cassure', 'amber'),
    'WAIT':              ('Attendre', 'amber'),
    'TOO_LATE':          ('Trop tard', 'amber'),
    'AVOID':             ('Éviter', 'red'),
    'NO_NEW_RISK':       ('Pas de risque nouveau', 'red'),
    'DATA_INSUFFICIENT': ('Données insuffisantes', 'gray'),
}

_BUYISH = {'STRONG_BUY', 'BUY', 'BUY_PULLBACK'}


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


#  LECTEUR UNIQUE du R:R du plan — défini chez `evidence` (couche basse déjà
#  importée ici), réutilisé tel quel : deux conversions de la même clé, c'était
#  déjà deux autorités pour un seul nombre.
#
#  Ce module lisait ``_num(plan['rr_res'])`` — défaut 0.0 — puis testait
#  ``if rr and rr < 2.0`` dans la règle 5 ET dans `_tipping_points`. Un 0.0 est
#  faux en Python : la garde s'éteignait exactement au pire cas mesurable.
#  Mesuré sur ``evaluate({'price':100,'score':85,'verdict':'BUY',
#  'confidence':70,'plan':{entry 100, stop 95, tp1 105, tp2 110, tp3 115,
#  'rr_res': X}})`` :
#
#      rr_res absent -> STRONG_BUY      (aucun audit, aucun point de bascule)
#      rr_res 0.0    -> STRONG_BUY      (aucun audit, aucun point de bascule)
#      rr_res 0.1    -> WATCH_BREAKOUT
#      rr_res 1.9    -> WATCH_BREAKOUT
#      rr_res 2.0    -> STRONG_BUY
#
#  Non monotone : 0.1 dégradait, 0.0 — strictement pire — passait en achat fort.
#  Chez son producteur (`analysis.py:252`), ``rr_res`` vaut 0.0 quand le risque
#  est nul ou que le cours a rejoint la résistance des 40 barres : « aucune
#  marge vers la cible », la mesure la plus défavorable, jamais une absence.
rr_mesure = evidence.rr_mesure


def assess_data_quality(detail, *, scan_age_s=None, demo=False):
    """Qualité de donnée du titre : chaque décision porte cette métadonnée."""
    missing = [f for f in ('price', 'score', 'plan') if not detail.get(f)]
    stale = scan_age_s is not None and scan_age_s > 900
    penalty = (25 if missing else 0) + (15 if stale else 0)
    grade = 'A' if not missing and not stale else ('C' if missing else 'B')
    return {
        'source': 'demo-synthetic' if demo else 'scan',
        'age_seconds': scan_age_s,
        'stale': bool(stale),
        'missing_fields': missing,
        'confidence_penalty': min(60, penalty),
        'grade': grade,
        'blocks_decision': bool(missing),
        'warning': ('données synthétiques (démo)' if demo else
                    ('champs manquants' if missing else ('scan rassis' if stale else None))),
    }


def _timing(d):
    if d.get('pullback'):
        return 'PULLBACK'
    if _num(d.get('ext_atr')) >= 4 or _num(d.get('rsi')) >= 78 or _num(d.get('pos52')) >= 95:
        return 'EXTENDED'
    if d.get('breakout'):
        return 'BREAKOUT'
    return 'NEUTRAL'


def _base_decision(d):
    """Décision de base, avant règles de dégradation."""
    v, sc = d.get('verdict'), _num(d.get('score'))
    if v == 'AVOID':
        return 'AVOID'
    if v == 'BUY' and sc >= 80:
        return 'STRONG_BUY'
    if v == 'BUY' and sc >= 66:
        return 'BUY'
    if v in ('BUY', 'WATCH') and sc >= 56:
        return 'WATCH_BREAKOUT'
    if v == 'WAIT':
        return 'WAIT'
    return 'WAIT'


def _market_permission(market, audit):
    """Le marché autorise-t-il la prise de risque ? (vent dominant top-down)."""
    if not market:
        return True
    roro = market.get('roro')
    regime = market.get('spy_regime')
    if roro == 'RISK-OFF':
        audit.append('Marché RISK-OFF → permission de risque réduite.')
        return False
    if regime == 'CHOP':
        audit.append('Marché en range (CHOP) → cassures dégradées.')
    return True


def _apply_rules(decision, d, market, option, portfolio, permission, audit):
    """Applique les règles institutionnelles de dégradation (ordre = priorité)."""
    timing = _timing(d)
    rr = rr_mesure(d)

    # 1. Corrélation portefeuille excessive → aucun risque nouveau.
    if portfolio and _num(portfolio.get('max_correlation')) >= 0.8 and decision in _BUYISH:
        audit.append('Corrélation portefeuille élevée → NO_NEW_RISK.')
        return 'NO_NEW_RISK'

    # 2. Sur-extension → trop tard, ou achat seulement sur repli.
    if timing == 'EXTENDED' and decision in _BUYISH:
        if _num(d.get('score')) >= 72:
            audit.append('Sur-étendu mais qualité forte → achat sur repli.')
            decision = 'BUY_PULLBACK'
        else:
            audit.append('Sur-étendu → trop tard pour poursuivre.')
            return 'TOO_LATE'

    # 3. Marché sans permission → pas d'achat fort.
    if not permission and decision in _BUYISH:
        audit.append('Sans permission marché → dégradé en surveillance.')
        return 'WATCH_BREAKOUT'

    # 4. Range (CHOP) → une cassure ne se poursuit pas : surveiller.
    if market and market.get('spy_regime') == 'CHOP' and timing == 'BREAKOUT' and decision in _BUYISH:
        audit.append('Cassure en marché de range → surveiller, ne pas poursuivre.')
        decision = 'WATCH_BREAKOUT'

    # 5. Risque/récompense insuffisant → pas d'achat. Seuil canonique = 2.0
    #    (aligné sur le hard gate ExecutiveEngine — jamais 1,5 concurrent).
    #    Un R:R mesuré à 0.0 est le pire cas, pas une absence : il DOIT dégrader
    #    (voir `rr_mesure`). Un R:R absent ne se suppose pas conforme.
    if decision in {'STRONG_BUY', 'BUY'}:
        if rr is None:
            audit.append('R:R du plan non mesuré → achat non confirmé, surveiller.')
            decision = 'WATCH_BREAKOUT'
        elif rr < 2.0:
            audit.append(f'R:R {rr:.1f} < 2.0 (minimum stratégie) → pas d\'achat, surveiller.')
            decision = 'WATCH_BREAKOUT'

    # 6. Marché RISK-OFF → jamais d'achat FORT.
    if market and market.get('roro') == 'RISK-OFF' and decision == 'STRONG_BUY':
        audit.append('RISK-OFF → achat fort interdit, dégradé en achat.')
        decision = 'BUY'

    # 7. Distribution cachée → prudence forte.
    if d.get('distribution') and decision in _BUYISH:
        audit.append('Distribution cachée détectée → dégradé en surveillance.')
        decision = 'WATCH_BREAKOUT'

    return decision


def _select_vehicle(d, option, audit):
    """Action vs Option : l'option doit MIEUX coller à la vue que le sous-jacent."""
    if not option:
        return 'ACTION'
    spread, oi = option.get('spread'), option.get('oi')
    iv, iv_rank = _num(option.get('iv')), option.get('iv_rank')
    # On ne pénalise QUE si la donnée de liquidité est réellement connue.
    if (spread is not None and _num(spread) > 8) or (oi is not None and _num(oi) < 200):
        audit.append('Option illiquide (spread/OI) → véhicule ACTION.')
        return 'ACTION'
    if (iv_rank is not None and _num(iv_rank) >= 80) or iv >= 90:
        audit.append('IV chère → véhicule ACTION (option coûteuse).')
        return 'ACTION'
    if d.get('profile') == 'OFFENSIF' and _num(option.get('quality')) >= 60:
        return 'OPTION'
    return 'ACTION'


def _conviction(d):
    return int(max(0, min(100, round(_num(d.get('score'))))))


_SUB_LABELS = {'technical': 'Technique', 'momentum': 'Momentum',
               'fundamental': 'Fondamental', 'risk': 'Risque', 'options': 'Options'}


def _decomposition(d):
    """Traçabilité du score (Ch. XVIII) : sous-scores + ajustements structurels."""
    sub = d.get('sub') or {}
    subscores = [{'label': _SUB_LABELS[k], 'value': int(sub[k]),
                  'is_proxy': bool(k == 'fundamental' and sub.get('fundamental_is_proxy'))}
                 for k in ('technical', 'momentum', 'fundamental', 'risk', 'options')
                 if isinstance(sub.get(k), (int, float))]
    adjustments = []
    pa, ma = int(_num(d.get('phys_adj'))), int(_num(d.get('mtf_adj')))
    if pa:
        adjustments.append({'label': 'Physique (structure du mouvement)', 'delta': pa})
    if ma:
        adjustments.append({'label': 'Multi-horizons (tendance hebdo)', 'delta': ma})
    return {
        'base_score': int(_num(d.get('base_score'), _num(d.get('score')))),
        'final_score': int(_num(d.get('score'))),
        'subscores': subscores, 'adjustments': adjustments,
        'note': ('Le score compose technique / momentum / fondamental / risque, '
                 'puis la structure (physique + multi-horizons) le tempère ou le renforce.'),
    }


def _size_hint(decision, profile):
    table = {
        'STRONG_BUY': {'OFFENSIF': '5-8%', 'DÉFENSIF': '4-6%', 'ÉQUILIBRÉ': '4-7%'},
        'BUY': {'OFFENSIF': '3-5%', 'DÉFENSIF': '3-5%', 'ÉQUILIBRÉ': '3-5%'},
        'BUY_PULLBACK': {'OFFENSIF': "2-4% à l'entrée sur repli", 'DÉFENSIF': '2-4%', 'ÉQUILIBRÉ': '2-4%'},
    }
    return table.get(decision, {}).get(profile or 'ÉQUILIBRÉ', '0% — observer')


def _tipping_points(decision, d, market, portfolio):
    """Conditions CONCRÈTES et mesurables qui amélioreraient le verdict (Ch. XVIII).

    Le complément des invalidations : au lieu de « ce qui tuerait la thèse »,
    « ce qui la renforcerait ». Dérivé des mêmes seuils que les règles."""
    if decision in ('STRONG_BUY', 'DATA_INSUFFICIENT'):
        return []
    out = []
    rr = rr_mesure(d)
    if rr is None:
        out.append('Un ratio risque/récompense MESURÉ au plan (aucun aujourd’hui)')
    elif rr < 2.0:
        out.append(f'Un ratio risque/récompense ≥ 2.0 (actuellement {rr:.1f})')
    if _timing(d) == 'EXTENDED':
        out.append('Un repli vers la zone d\'entrée (le titre est sur-étendu)')
    if not (d.get('signals') or {}).get('above200', True):
        out.append('Une reprise durable au-dessus de la MM200')
    if market and market.get('roro') == 'RISK-OFF':
        out.append('Le retour du marché en RISK-ON (permission de risque)')
    if market and market.get('spy_regime') == 'CHOP':
        out.append('La sortie du régime de range (une tendance qui se réinstalle)')
    if d.get('distribution'):
        out.append('La fin de la distribution (le volume qui confirme la hausse)')
    if portfolio and _num(portfolio.get('max_correlation')) >= 0.8:
        out.append('Une corrélation portefeuille plus basse (diversifier le panier)')
    return out[:4]


def _member_stances(ev):
    """Vote net de chaque analyste du comité, par domaine."""
    by = {}
    for e in ev.get('positive', []):
        by[e['source']] = by.get(e['source'], 0) + e['strength']
    for e in ev.get('negative', []):
        by[e['source']] = by.get(e['source'], 0) - e['strength']
    members = [{'member': s, 'stance': ('Favorable' if n > 30 else 'Défavorable' if n < -30 else 'Neutre'),
                'net': int(n)} for s, n in by.items()]
    return sorted(members, key=lambda m: m['net'], reverse=True)


def _committee(ev):
    """Le Président : synthèse des avis, accord mesuré, contradictions exposées (Ch. IX/XVI)."""
    pos = sum(x['strength'] for x in ev.get('positive', []))
    neg = sum(x['strength'] for x in ev.get('negative', []))
    lean = pos / (pos + neg) if (pos + neg) else 0.5
    view = ('Constructif' if lean >= 0.66 else 'Modérément constructif' if lean >= 0.54
            else 'Équilibré' if lean >= 0.44 else 'Prudent' if lean >= 0.30 else 'Négatif')
    agreement = abs(lean - 0.5) * 2
    conf = int(max(20, min(95, round(45 + agreement * 45 - (15 if ev.get('has_contradiction') else 0)))))
    opposing = ev.get('negative', [])[:1]     # Avocat du diable : preuve adverse la plus forte.
    return {
        'view': view, 'confidence': conf, 'lean': round(lean * 100),
        'agreement': round(agreement * 100),
        'members': _member_stances(ev),
        'has_contradiction': ev.get('has_contradiction', False),
        'devils_advocate': opposing[0]['text'] if opposing else None,
        'positive': ev.get('positive', [])[:5],
        'negative': ev.get('negative', [])[:5],
        'contradictory': ev.get('contradictory', []),
        'unknown': ev.get('unknown', []),
        'watch_signals': ev.get('neutral', []),      # catalyseurs à vérifier (directionless)
        'regime': ev.get('regime'),
    }


def evaluate(detail, *, symbol=None, market=None, option=None, portfolio=None,
             scan_age_s=None, demo=False, context=None):
    """Point d'entrée unique : détail d'un titre → DecisionResult (vue du comité)."""
    d = detail or {}
    audit = []
    dq = assess_data_quality(d, scan_age_s=scan_age_s, demo=demo)
    ev = evidence.gather(d, market=market, option=option, portfolio=portfolio,
                         data_quality=dq, context=context)
    committee = _committee(ev)

    if dq['blocks_decision']:
        return _result('DATA_INSUFFICIENT', d, dq, committee, symbol=symbol, market=market,
                       vehicle='—', conviction=0, confidence=0, audit=audit, context=context,
                       explanation='Données insuffisantes pour décider : '
                                   + ', '.join(dq['missing_fields']) + '.')

    permission = _market_permission(market, audit)
    decision = _apply_rules(_base_decision(d), d, market, option, portfolio, permission, audit)
    vehicle = 'ACTION' if decision not in _BUYISH else _select_vehicle(d, option, audit)
    conviction = _conviction(d)
    # Confiance = accord scoring + accord du comité, moins la pénalité qualité de données.
    base_conf = _num(d.get('confidence'), 55)
    confidence = int(max(0, min(100, round((base_conf + committee['confidence']) / 2
                                           - dq.get('confidence_penalty', 0)))))
    tipping = _tipping_points(decision, d, market, portfolio)
    return _result(decision, d, dq, committee, symbol=symbol, market=market, vehicle=vehicle,
                   conviction=conviction, confidence=confidence, audit=audit,
                   permission=permission, context=context, tipping=tipping)


def _result(decision, d, dq, committee, *, symbol, market, vehicle, conviction,
            confidence, audit, permission=True, explanation=None, context=None, tipping=None):
    label, tone = DECISIONS[decision]
    plan = d.get('plan') or {}
    pros = [e['text'] for e in committee.get('positive', [])][:5]
    cons = [e['text'] for e in committee.get('negative', [])][:5]
    blockers = ['Signal Vertex à ÉVITER (sous la MM200)'] if d.get('verdict') == 'AVOID' else []
    flags = [e['text'] for e in committee.get('contradictory', [])]
    if dq.get('warning'):
        flags = flags + [dq['warning']]
    unknowns = [e['text'] for e in committee.get('unknown', [])][:5]
    expl = explanation or _explain(decision, committee, confidence, audit)
    reason = (reasoning.build(d, committee, decision)
              if decision != 'DATA_INSUFFICIENT' else None)
    breakdown = _decomposition(d) if decision != 'DATA_INSUFFICIENT' else None
    return {
        'symbol': symbol or d.get('symbol'),
        'final_decision': decision,
        'decision_label': label,
        'decision_tone': tone,
        'conviction': conviction,
        'confidence': confidence,
        'grade': d.get('grade'),
        'market_permission': bool(permission),
        'vehicle': vehicle,
        'timing': _timing(d) if decision != 'DATA_INSUFFICIENT' else None,
        'entry': plan.get('entry'),
        'stop': plan.get('stop'),
        'targets': {'tp1': plan.get('tp1'), 'tp2': plan.get('tp2'), 'tp3': plan.get('tp3')},
        'invalidation': plan.get('stop'),
        'position_size_hint': _size_hint(decision, d.get('profile')),
        'committee': committee,
        'pros': pros,
        'cons': cons,
        'blockers': blockers,
        'risk_flags': flags[:6],
        'unknowns': unknowns,          # « ce que nous ne savons pas » (Ch. XVI)
        'reasoning': reason,           # scénarios + invalidations (Ch. XVIII)
        'score_breakdown': breakdown,  # traçabilité du score (Ch. XVIII)
        'tipping_points': tipping or [],  # ce qui améliorerait le verdict (Ch. XVIII)
        'context': context,            # situation transversale (percentiles, rang secteur)
        'data_quality': dq,
        'explanation': expl,
        'audit_trail': audit,
    }


def _explain(decision, committee, confidence, audit):
    label = DECISIONS[decision][0]
    head = f'{label} — vue du comité : {committee["view"]}, confiance {confidence}/100.'
    if committee.get('has_contradiction'):
        head += ' ⚠ Contradictions internes exposées.'
    devil = committee.get('devils_advocate')
    contra = f' Avocat du diable : {devil}.' if devil else ''
    why = audit[0] if audit else "Les domaines d'analyse sont cohérents avec le verdict."
    return f'{head} {why}{contra} Analyse éducative — aucune certitude, aucun ordre.'
