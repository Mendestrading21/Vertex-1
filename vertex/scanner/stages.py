"""vertex.scanner.stages — évaluateurs d'étages du scanner institutionnel (§22).

## ⚠ CE MODULE N'EST BRANCHÉ SUR AUCUN CHEMIN DE PRODUCTION — NON_IMPLÉMENTÉ

Mesuré le 2026-09-06, balayage des imports du dépôt : `STAGE_ORDER` et les huit
évaluateurs ne sont référencés QUE par `tests/test_scanner_institutional.py`.
Le paquet `vertex.scanner` n'est importé qu'à travers `daily` et `weekly`
(`terminal.py:42`, `app/routes/weekly_api.py:29`) ; aucun appelant n'exécute ces
étages. Le scanner réel ne note donc PAS les candidats de cette façon.

Il faut le dire ici, en tête, parce qu'un test vert et un commentaire
« ordre OBLIGATOIRE des étages — testé » donnent exactement l'impression
inverse : celle d'une capacité vivante. Une capacité sans exécuteur réel
s'appelle NON_IMPLÉMENTÉ (invariant 8), elle ne se déguise pas en automatisation
en attente.

Le vocabulaire d'entrée le confirme : un balayage des lectures et des écritures
montre que `has_catalyst`, `crowding_extreme`, `improves_quality`,
`adds_correlation` et `quality_flags` ne sont écrits NULLE PART dans le dépôt.
Aucun producteur ne remplit les blocs que ces étages attendent.

Le module n'est pas supprimé : il porte un contrat de notation cohérent et une
suite de tests, et la doctrine interdit de supprimer sans preuve d'absence de
consommateur, de migration et de rollback. Il est CONSERVÉ et ÉTIQUETÉ, en
attendant qu'un producteur existe ou qu'une décision humaine tranche.

## Contrat des étages, si un jour ils sont branchés

Chaque étage reçoit le paquet candidat (dict) et rend :
  {'passed': bool, 'score': 0..100 | None, 'reasons': [...], 'missing': [...]}
Une donnée absente ne fabrique JAMAIS un score : elle apparaît dans `missing`
et l'étage passe en mode dégradé documenté (score None) ou refuse.
"""

from __future__ import annotations
#: État réel de la capacité, lisible par un programme autant que par un humain.
ETAT = 'NON_IMPLÉMENTÉ'
#: Ce qui manque pour l'activer, mesuré et non supposé.
MANQUE = (
    'aucun appelant de production n’exécute STAGE_ORDER',
    'aucun producteur n’écrit has_catalyst, crowding_extreme, improves_quality, '
    'adds_correlation ni quality_flags',
)


def _res(passed, score=None, reasons=None, missing=None):
    return {'passed': bool(passed), 'score': score,
            'reasons': list(reasons or []), 'missing': list(missing or [])}


def fundamental_stage(candidate: dict) -> dict:
    f = candidate.get('fundamentals') or {}
    if not f:
        # sans fondamental, un candidat peut continuer en RADAR mais jamais ACTIONABLE
        return _res(True, None, ['fondamentaux indisponibles — plafonné à RADAR/WATCH'],
                    ['fundamentals'])
    reasons, score = [], 50.0
    growth = f.get('revenue_growth')
    margin = f.get('margin')
    if growth is not None:
        if growth >= 0.15:
            score += 20
            reasons.append(f'croissance CA {growth:.0%}')
        elif growth < 0:
            score -= 25
            reasons.append(f'CA en contraction ({growth:.0%})')
    if margin is not None and margin >= 0.15:
        score += 10
        reasons.append(f'marge {margin:.0%}')
    if f.get('quality_flags'):
        score -= 20
        reasons.append(f"drapeaux qualité: {f['quality_flags']}")
    pe, sector_pe = f.get('pe'), f.get('sector_median_pe')
    if pe and sector_pe and pe / sector_pe > 3:
        score -= 10
        reasons.append('valorisation très au-dessus du secteur')
    score = max(0.0, min(100.0, score))
    return _res(score >= 35, score, reasons)


def catalyst_stage(candidate: dict) -> dict:
    c = candidate.get('catalysts') or {}
    if not c:
        return _res(True, None, ['catalyseurs inconnus'], ['catalysts'])
    has = bool(c.get('has_catalyst'))
    reasons = []
    if has:
        reasons.append('catalyseur identifié: ' +
                       (c.get('next_events') or [{}])[0].get('type', 'earnings'))
    else:
        reasons.append('aucun catalyseur sous 30-45 j')
    return _res(True, 70.0 if has else 40.0, reasons)


def technical_stage(candidate: dict) -> dict:
    t = candidate.get('technical') or {}
    if not t:
        return _res(False, None, ['technique indisponible — étage refusé'], ['technical'])
    score, reasons = 50.0, []
    if t.get('trend') == 'UP':
        score += 20
        reasons.append('tendance haussière')
    elif t.get('trend') == 'DOWN':
        score -= 25
        reasons.append('tendance baissière')
    rs = t.get('relative_strength')
    if rs is not None:
        score += (rs - 50) * 0.4
        reasons.append(f'force relative {rs}')
    if t.get('overextended'):
        score -= 20
        reasons.append('surétendu — ne pas poursuivre le prix')
    rr = t.get('reward_risk')
    if rr is not None:
        if rr >= 2:
            score += 15
            reasons.append(f'R:R structurel {rr}')
        elif rr < 2:
            # Sous le minimum stratégie 2:1 → pénalisé (plus de zone 1,5–2,0 neutre).
            score -= 20
            reasons.append(f'R:R {rr} sous le minimum 2:1')
    score = max(0.0, min(100.0, score))
    return _res(score >= 45, score, reasons)


def sentiment_stage(candidate: dict) -> dict:
    s = candidate.get('sentiment') or {}
    if not s:
        return _res(True, None, ['sentiment/positionnement inconnus'], ['sentiment'])
    score, reasons = 50.0, []
    if s.get('crowding_extreme'):
        score -= 20
        reasons.append('positionnement surchargé (proxy de crowding)')
    if s.get('news_tone') == 'NEGATIVE':
        score -= 10
        reasons.append('flux de news négatif')
    elif s.get('news_tone') == 'POSITIVE':
        score += 10
        reasons.append('flux de news porteur')
    return _res(True, max(0.0, min(100.0, score)), reasons)


def anomaly_stage(candidate: dict) -> dict:
    anomalies = candidate.get('anomalies') or []
    blocking = [a for a in anomalies if getattr(a, 'blocking', False) or
                (isinstance(a, dict) and a.get('blocking'))]
    if blocking:
        codes = [getattr(a, 'code', None) or a.get('code') for a in blocking]
        return _res(False, 0.0, [f'anomalies bloquantes: {codes}'])
    interesting = [getattr(a, 'code', None) or a.get('code') for a in anomalies]
    return _res(True, 60.0 if interesting else 50.0,
                [f'anomalies: {interesting[:6]}'] if interesting else [])


def portfolio_stage(candidate: dict) -> dict:
    fit = candidate.get('portfolio_fit') or {}
    if not fit:
        return _res(True, None, ['compatibilité portefeuille non évaluée'], ['portfolio_fit'])
    if fit.get('blocked'):
        return _res(False, 0.0, [fit.get('reason', 'portefeuille incompatible')])
    score = 70.0 if fit.get('improves_quality') else 50.0
    if fit.get('adds_correlation'):
        score -= 15
    return _res(True, score, [])


def options_stage(candidate: dict) -> dict:
    opt = candidate.get('option_selection') or {}
    if not opt:
        return _res(True, None, ['pas de volet options (action seule)'], ['options'])
    primary = opt.get('primary')
    if not primary:
        return _res(True, 40.0, ['aucun contrat exploitable — idée action seulement'])
    return _res(True, min(100.0, primary.get('score', 0)),
                [f"contrat {primary.get('category')} score {primary.get('score')}"])


def risk_stage(candidate: dict) -> dict:
    risk = candidate.get('risk') or {}
    if risk.get('no_new_risk'):
        return _res(False, 0.0, [risk.get('reason', 'NO_NEW_RISK actif')])
    dq = candidate.get('data_quality') or {}
    if dq and not dq.get('actionable_allowed', True):
        return _res(True, 30.0, ['qualité de données insuffisante — plafonné sous ACTIONABLE'])
    return _res(True, 60.0, [])


# Ordre OBLIGATOIRE des étages (§22) — testé.
STAGE_ORDER = (
    ('fundamental', fundamental_stage),
    ('catalysts', catalyst_stage),
    ('technical', technical_stage),
    ('sentiment', sentiment_stage),
    ('anomalies', anomaly_stage),
    ('portfolio', portfolio_stage),
    ('options', options_stage),
    ('risk', risk_stage),
)
