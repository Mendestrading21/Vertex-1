"""vertex.options.horizon_scanners — scanners déterministes par univers d’échéance.

Les univers restent strictement séparés. `SWING_3_6M` est le mandat opérationnel
pour les positions détenues une à trois semaines avec une échéance de trois à six
mois : fenêtre admissible 75–210 DTE et fenêtre préférée 90–180 DTE par défaut.
Le scanner ne donne aucun ordre et ne filtre jamais silencieusement un contrat hors
mandat : chaque candidat porte son statut de conformité, ses raisons et sa base de
sélection.
"""
from __future__ import annotations

from itertools import islice

from vertex.options import board_fields as _bf
from vertex.options import iv_units

_FALLBACK_UNIVERSES = {
    'TACTICAL': [20, 60],
    'SWING': [60, 180],
    'SWING_3_6M': [75, 210],
    'LEAPS': [180, 540],
}

_FALLBACK_SWING_3_6M = {
    'preferred_dte': [90, 180],
    'target_dte': 135,
    'holding_plan_sessions': [5, 10, 15],
    'delta_abs_min': 0.30,
    'delta_abs_max': 0.60,
    'open_interest_min': 500,
    'volume_min': 50,
    'spread_pct_max': 8.0,
    'max_quote_age_seconds': 900,
}
MAX_BOARD_CONTRACTS = 5000


def _universes(profile=None):
    """Retourne les fenêtres d’univers avec un fallback stable et documenté."""
    try:
        if profile is None:
            from vertex.strategy.constitution import load_profile
            profile = load_profile()
        raw = (profile.options_profile or {}).get('universes') or {}
        universes = {
            key: list(value) for key, value in raw.items()
            if isinstance(value, (list, tuple)) and len(value) == 2
        }
        for key, value in _FALLBACK_UNIVERSES.items():
            universes.setdefault(key, list(value))
        return universes, profile, {
            'available': True,
            'status': 'PROFILE_AVAILABLE',
            'read_only': True,
        }
    except Exception:
        # Le scan reste borné et descriptif avec ses fenêtres internes, sans
        # révéler l’exception ni présenter ce repli comme le profil actif.
        return dict(_FALLBACK_UNIVERSES), None, {
            'available': False,
            'status': 'PROFILE_FALLBACK',
            'read_only': True,
        }


def _swing_3_6m_config(profile=None) -> dict:
    """Lit le mandat 3–6 mois du profil sans rendre le scanner indisponible."""
    config = dict(_FALLBACK_SWING_3_6M)
    if profile is not None:
        raw = (profile.options_profile or {}).get('swing_3_6m') or {}
        if isinstance(raw, dict):
            config.update(raw)
    return config


def _in_window(dte, universe, window):
    lo, hi = window
    if universe == 'LEAPS':
        return lo <= dte <= hi
    return lo <= dte < hi


def _value_in_range(value, lo, hi):
    if value is None:
        return None
    try:
        return bool(lo <= abs(float(value)) <= hi)
    except (TypeError, ValueError):
        return None


def _minimum_ok(value, minimum):
    if value is None:
        return None
    try:
        return bool(float(value) >= float(minimum))
    except (TypeError, ValueError):
        return None


def _maximum_ok(value, maximum):
    if value is None:
        return None
    try:
        return bool(float(value) <= float(maximum))
    except (TypeError, ValueError):
        return None


def _quote_age(contract):
    """Compatibilité avec les noms historiques sans jamais inventer une fraîcheur."""
    for key in ('quote_age_seconds', 'age_seconds', 'quote_age_s'):
        value = contract.get(key)
        if value is not None:
            return value
    return None


def _quote_freshness(age, maximum):
    if age is None:
        return {'available': False, 'status': 'QUOTE_FRESHNESS_UNAVAILABLE', 'read_only': True}
    try:
        age = float(age)
    except (TypeError, ValueError):
        return {'available': False, 'status': 'QUOTE_FRESHNESS_UNAVAILABLE', 'read_only': True}
    return {'available': True, 'status': 'QUOTE_FRESH' if age <= maximum else 'QUOTE_STALE',
            'age_seconds': age, 'max_age_seconds': maximum, 'read_only': True}


#  Liquidité : lire le champ que le board publie RÉELLEMENT.
#  Les lectures directes des noms `spread_pct` / `volume` ne trouvaient rien sur
#  le board de production (`legacy_engine` publie `spread` et `vol`) : mesure du
#  2026-09-06, Scanner LEAPS 33/33 lignes motivées « spread indisponible » et
#  SWING_3_6M 74/74 « volume indisponible », `IN_MANDATE` structurellement
#  inatteignable quelle que soit la liquidité. Pire, la fausse absence PROMOUT :
#  `rank` classe PARTIAL_MANDATE (1) avant OUT_OF_MANDATE (2), donc 22 des 31
#  candidats étiquetés « partiel » étaient mesurablement hors mandat, dont la
#  tête du mandat 3–6 mois (CPAY, vol 1 et spread 14,2 % sur sa ligne de board).
#  `board_fields` refuse en outre de rendre la pénalité 99.0 ou un volume imputé
#  à 0 : une absence reste une absence, jamais une conformité ni un rejet faux.
def _leaps_mandate(contract, profile):
    category = profile.category('LEAPS') if profile is not None else {}
    d_min = category.get('delta_min', 0.70)
    d_max = category.get('delta_max', 0.90)
    oi_min = category.get('open_interest_min', 500)
    spread_max = category.get('spread_pct_max', 5.0)
    return {
        'delta_ok': _value_in_range(contract.get('delta'), d_min, d_max),
        'oi_ok': _minimum_ok(contract.get('oi'), oi_min),
        'spread_ok': _maximum_ok(_bf.spread_pct(contract), spread_max),
        'bounds': {
            'delta': [d_min, d_max],
            'oi_min': oi_min,
            'spread_pct_max': spread_max,
        },
    }


def _swing_3_6m_mandate(contract, config):
    age = _quote_age(contract)
    return {
        'delta_ok': _value_in_range(contract.get('delta'), config['delta_abs_min'], config['delta_abs_max']),
        'oi_ok': _minimum_ok(contract.get('oi'), config['open_interest_min']),
        'volume_ok': _minimum_ok(_bf.volume(contract), config['volume_min']),
        'spread_ok': _maximum_ok(_bf.spread_pct(contract), config['spread_pct_max']),
        'quote_fresh_ok': _maximum_ok(age, config['max_quote_age_seconds']),
        'bounds': {
            'delta_abs': [config['delta_abs_min'], config['delta_abs_max']],
            'oi_min': config['open_interest_min'],
            'volume_min': config['volume_min'],
            'spread_pct_max': config['spread_pct_max'],
            'max_quote_age_seconds': config['max_quote_age_seconds'],
            'preferred_dte': list(config['preferred_dte']),
            'target_dte': config['target_dte'],
            'holding_plan_sessions': list(config['holding_plan_sessions']),
        },
    }


def _mandate_status(mandate):
    checks = [value for key, value in mandate.items() if key.endswith('_ok')]
    if any(value is False for value in checks):
        return 'OUT_OF_MANDATE'
    if any(value is None for value in checks):
        return 'PARTIAL_MANDATE'
    return 'IN_MANDATE'


def _mandate_reasons(mandate):
    return [key.removesuffix('_ok') + ' indisponible' if value is None else key.removesuffix('_ok') + ' hors mandat'
            for key, value in mandate.items() if key.endswith('_ok') and value is not True]


def _candidate_mandate(contract, universe, profile, swing_config):
    if universe == 'LEAPS':
        return _leaps_mandate(contract, profile)
    if universe == 'SWING_3_6M':
        return _swing_3_6m_mandate(contract, swing_config)
    return {}


def _dte_distance(dte, universe, swing_config):
    if universe != 'SWING_3_6M':
        return 0
    return abs(float(dte) - float(swing_config['target_dte']))


def scan(board, universe, sym=None, profile=None):
    """Retourne les calls et puts longs d’un univers, avec conformité explicite.

    Les données manquantes ne sont jamais transformées en conformité positive : elles
    produisent le statut `PARTIAL_MANDATE`, visible dans les raisons du candidat.
    """
    universes, profile, profile_coverage = _universes(profile)
    universe = (universe or '').upper()
    if universe not in universes:
        return {
            'available': False,
            'universe': universe,
            'candidates': [],
            'reason': 'univers inconnu : %r (attendu %s)' % (universe, sorted(universes)),
            'profile_coverage': profile_coverage,
        }

    source = board or []
    try:
        input_total = len(source)
        bounded_board = source[:MAX_BOARD_CONTRACTS]
        input_truncated = input_total > MAX_BOARD_CONTRACTS
    except TypeError:
        bounded_board = list(islice(source, MAX_BOARD_CONTRACTS + 1))
        input_truncated = len(bounded_board) > MAX_BOARD_CONTRACTS
        if input_truncated:
            bounded_board = bounded_board[:MAX_BOARD_CONTRACTS]
        input_total = None
    window = universes[universe]
    swing_config = _swing_3_6m_config(profile)
    candidates = []
    for raw in bounded_board:
        if not isinstance(raw, dict):
            continue
        if sym and str(raw.get('sym', '')).upper() != str(sym).upper():
            continue
        option_type = str(raw.get('type', '')).upper()
        if option_type not in ('CALL', 'PUT'):
            continue
        dte = raw.get('dte')
        if not isinstance(dte, (int, float)) or not _in_window(dte, universe, window):
            continue

        iv_dec, _, iv_warning = iv_units.from_legacy_board(raw.get('iv'))
        mandate = _candidate_mandate(raw, universe, profile, swing_config)
        status = _mandate_status(mandate) if mandate else 'NOT_APPLICABLE'
        candidate = {
            'sym': raw.get('sym'),
            'type': option_type,
            'strike': raw.get('strike'),
            'exp': raw.get('exp'),
            'dte': dte,
            'delta': raw.get('delta'),
            'iv': iv_dec,
            'iv_unit': 'DECIMAL' if iv_dec is not None else None,
            'oi': raw.get('oi'),
            'volume': _bf.volume(raw),
            'spread_pct': _bf.spread_pct(raw),
            'quote_age_seconds': _quote_age(raw),
            'quote_freshness': _quote_freshness(_quote_age(raw), swing_config['max_quote_age_seconds']),
            'cost': raw.get('cost'),
            'spot': raw.get('spot'),
            'quality': raw.get('quality'),
            'warnings': [warning for warning in [iv_warning] if warning],
            'mandate': mandate or None,
            'mandate_status': status,
            'mandate_reasons': _mandate_reasons(mandate) if mandate else [],
            'hors_mandat': status == 'OUT_OF_MANDATE',
            'dte_distance_to_target': _dte_distance(dte, universe, swing_config),
        }
        candidates.append(candidate)

    rank = {'IN_MANDATE': 0, 'NOT_APPLICABLE': 0, 'PARTIAL_MANDATE': 1, 'OUT_OF_MANDATE': 2}
    candidates.sort(key=lambda candidate: (
        rank.get(candidate['mandate_status'], 3),
        candidate['dte_distance_to_target'],
        -(candidate.get('quality') or 0),
        candidate.get('strike') if candidate.get('strike') is not None else float('inf'),
    ))
    preferred_window = list(swing_config['preferred_dte']) if universe == 'SWING_3_6M' else None
    note = (
        'Mandat 3–6 mois : contrat admissible %s, préférence %s, plan de détention %s séances ; '
        'la conformité de liquidité et de fraîcheur est affichée sans filtre silencieux.'
        % (window, preferred_window, swing_config['holding_plan_sessions'])
        if universe == 'SWING_3_6M' else
        'Univers strictement séparés ; un contrat hors mandat reste affiché et étiqueté.'
    )
    return {
        'available': bool(candidates),
        'universe': universe,
        'window': list(window),
        'preferred_window': preferred_window,
        'n': len(candidates),
        'input_contracts_inspected': len(bounded_board),
        'input_contracts_total': input_total,
        'input_truncated': input_truncated,
        'input_limit': MAX_BOARD_CONTRACTS,
        'profile_coverage': profile_coverage,
        'candidates': candidates,
        'generator': 'deterministic',
        'note': note,
        'reason': None if candidates else 'aucun contrat %s dans la fenêtre %s pour ce filtre' % (universe, window),
    }


def swing_3_6m_context(board, sym=None, profile=None, historical_closes=None):
    """Point d’entrée canonique pour le mandat options 3–6 mois de Skyler."""
    return options_context(scan(board, 'SWING_3_6M', sym=sym, profile=profile),
                           historical_closes=historical_closes)


def options_context(scan_result, historical_closes=None):
    """Construit un contexte minimal mais traçable à partir d’un scan réel."""
    if not scan_result or not scan_result.get('available'):
        return {
            'available': False,
            'reason': (scan_result or {}).get('reason') or 'scan options indisponible',
        }
    best = scan_result['candidates'][0]
    from vertex.options import iv_hv
    iv_pct = best['iv'] * 100.0 if isinstance(best.get('iv'), (int, float)) else None
    iv_hv_context = iv_hv.describe(iv_pct, iv_hv.realized_volatility_20d(historical_closes))
    return {
        'available': True,
        'universe': scan_result['universe'],
        'window': scan_result['window'],
        'preferred_window': scan_result.get('preferred_window'),
        'n': scan_result['n'],
        'input_truncated': bool(scan_result.get('input_truncated')),
        'input_limit': scan_result.get('input_limit'),
        'input_contracts_total': scan_result.get('input_contracts_total'),
        'profile_coverage': scan_result.get('profile_coverage'),
        'best': best,
        'best_in_mandate': best['mandate_status'] == 'IN_MANDATE',
        'mandate_status': best['mandate_status'],
        'selection_basis': {
            'status': best['mandate_status'],
            'reasons': list(best['mandate_reasons']),
            'dte_distance_to_target': best['dte_distance_to_target'],
        },
        'iv_hv_context': iv_hv_context,
        'generator': 'deterministic',
    }


__all__ = ['scan', 'options_context', 'swing_3_6m_context']
