"""vertex/options/gex.py — EXPOSITION GAMMA DES DEALERS (GEX) · analyse d'options.

Calcule, pour UN sous-jacent, le profil d'exposition gamma des teneurs de marché
à partir de la chaîne d'options DÉJÀ chargée (options_board : OI + gamma + strike
par contrat, données réelles IBKR/scan). AUCUN chiffre inventé : un contrat sans
OI ou sans gamma exploitable est simplement ignoré ; chaîne vide → profil vide honnête.

Rôle (comme les desks pro type GEX/dealer-positioning) :
- GEX par strike : call GEX (+), put GEX (−), net GEX, GEX normalisé (% du |total|).
- Net GEX total : positif = dealers LONG gamma (amortissent la volatilité, effet
  d'aimant/pinning) ; négatif = dealers SHORT gamma (amplifient les mouvements).
- Niveau de bascule (« zero-gamma flip ») : strike où le net GEX cumulé change de
  signe — au-dessus, régime stabilisant ; en dessous, régime accélérateur.
- Mur call / mur put : strikes de plus forte concentration (aimant / support).
- Biais : concentration du GEX au-dessus vs sous le spot.

Convention de signe (naïve, standard desk) : les dealers sont supposés SHORT les
calls (+gamma) et LONG les puts (−gamma). Net GEX > 0 ⇒ gamma positif dominant.

Invariants VERTEX : lecture seule, aucun ordre ; fonction pure (aucune I/O, aucun
Flask) ; donnée absente → None honnête, jamais estimée. Le gamma consommé est celui
DÉJÀ produit par le moteur (Black-Scholes / IBKR) — ce module ne recalcule aucun grec.
"""
from __future__ import annotations

import math
from vertex.options import board_fields as _bf

CONTRACT_MULTIPLIER = 100          # 1 contrat = 100 actions (equity options US)
_R = 0.045                         # taux sans risque (même valeur que constants.R)


def _num(x):
    """Nombre fini exploitable, sinon None (jamais de bool, jamais NaN/inf)."""
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float('inf'), float('-inf')):   # NaN / inf
        return None
    return v


def _spot_of(contracts, spot):
    """Spot réel : argument explicite sinon 1er spot présent sur un contrat. Jamais inventé."""
    s = _num(spot)
    if s and s > 0:
        return s
    for c in contracts:
        s = _num(c.get('spot'))
        if s and s > 0:
            return s
    return None


def _iv_frac(iv):
    """IV en fraction : accepte 32.5 (pour-cent) ou 0.325 (fraction). None si inexploitable."""
    v = _num(iv)
    if v is None or v <= 0:
        return None
    return v / 100.0 if v > 3 else v


def _contract_vanna(strike, spot, iv, dte, oi, is_call):
    """Exposition VANNA $ d'un contrat (variation du delta-dollar pour +1 pt d'IV),
    Black-Scholes depuis les données réelles (spot/strike/IV/DTE/OI). Convention de
    signe naïve IDENTIQUE au GEX (call +, put −). None si une donnée manque."""
    k, s, o, d = _num(strike), _num(spot), _num(oi), _num(dte)
    sig = _iv_frac(iv)
    if None in (k, s, o, d) or sig is None or s <= 0 or k <= 0 or d <= 0:
        return None
    t = d / 365.0
    srt = sig * math.sqrt(t)
    if srt <= 0:
        return None
    try:
        d1 = (math.log(s / k) + (_R + sig * sig / 2) * t) / srt
    except ValueError:
        return None
    d2 = d1 - srt
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    vanna = -pdf * d2 / sig                                  # ∂Δ/∂σ (par action, par unité de vol)
    mag = vanna * 0.01 * o * CONTRACT_MULTIPLIER * s         # $ de delta pour +1 pt d'IV
    return mag if is_call else -mag


def _contract_charm(strike, spot, iv, dte, oi, is_call):
    """Exposition CHARM $ d'un contrat (dérive du delta-dollar PAR JOUR qui passe),
    Black-Scholes depuis les données réelles. Convention de signe naïve IDENTIQUE
    au GEX (call +, put −). None si une donnée manque. Charm négatif sur un call
    OTM : son delta fond vers 0 avec le temps → les dealers rachètent/vendent le
    sous-jacent chaque jour rien que par l'écoulement du temps."""
    k, s, o, d = _num(strike), _num(spot), _num(oi), _num(dte)
    sig = _iv_frac(iv)
    if None in (k, s, o, d) or sig is None or s <= 0 or k <= 0 or d <= 0:
        return None
    t = d / 365.0
    srt = sig * math.sqrt(t)
    if srt <= 0:
        return None
    try:
        d1 = (math.log(s / k) + (_R + sig * sig / 2) * t) / srt
    except ValueError:
        return None
    d2 = d1 - srt
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    charm = -pdf * (2 * _R * t - d2 * srt) / (2 * t * srt)   # ∂Δ/∂t (par an, call)
    mag = (charm / 365.0) * o * CONTRACT_MULTIPLIER * s      # $ de delta par JOUR
    return mag if is_call else -mag


def _contract_gex(gamma, oi, spot, is_call):
    """GEX $ d'un contrat (par mouvement de 1 % du sous-jacent), signé par la
    convention dealer. Retourne None si une donnée réelle manque."""
    g, o = _num(gamma), _num(oi)
    if g is None or o is None or not spot:
        return None
    # gamma (par action) × OI × 100 × spot² × 1 % — exposition dollar au move de 1 %
    mag = g * o * CONTRACT_MULTIPLIER * spot * spot * 0.01
    return mag if is_call else -mag


def compute(contracts, *, spot=None, symbol=None):
    """Profil GEX d'un sous-jacent depuis ses contrats (liste d'items du board).

    contracts : items {type:'CALL'|'PUT', strike, oi, gamma, spot?} — données réelles.
    Retourne un dict JSON-sérialisable ; profil vide honnête si rien d'exploitable.
    """
    contracts = [c for c in (contracts or []) if isinstance(c, dict)]
    sp = _spot_of(contracts, spot)

    per_strike = {}          # strike -> {'call': gex, 'put': gex, 'vanna': $|None}
    used = 0
    sans_oi = 0              # contrats écartés faute d'intérêt ouvert REPORTÉ
    vanna_any = False
    charm_any = False
    for c in contracts:
        k = _num(c.get('strike'))
        if k is None:
            continue
        is_call = str(c.get('type', '')).upper() != 'PUT'
        #  L'INTÉRÊT OUVERT EST LE MULTIPLICATEUR DE TOUTE L'EXPOSITION.
        #  Mesuré le 2026-09-06 : `oi` brut porte le zéro imputé par
        #  `legacy_engine._i` quand le courtier ne reporte rien. Un contrat non
        #  reporté contribuait donc 0 $ de gamma — arithmétiquement identique à
        #  un contrat sans position ouverte — et le total s'annonçait calculé
        #  sur `contracts_used` lignes sans dire que certaines n'avaient aucun
        #  intérêt ouvert MESURÉ. Les contrats sans OI reporté sont désormais
        #  écartés du calcul et COMPTÉS à part : la couverture voyage avec le
        #  chiffre (invariant 6).
        oi = _bf.open_interest(c)
        if oi is None:
            sans_oi += 1
            continue
        gx = _contract_gex(c.get('gamma'), oi, sp, is_call)
        if gx is None:
            continue
        slot = per_strike.setdefault(k, {'call': 0.0, 'put': 0.0, 'vanna': 0.0, 'charm': 0.0})
        slot['call' if is_call else 'put'] += gx
        vn = _contract_vanna(k, sp, c.get('iv'), c.get('dte'), oi, is_call)
        if vn is not None:
            slot['vanna'] += vn
            vanna_any = True
        ch = _contract_charm(k, sp, c.get('iv'), c.get('dte'), oi, is_call)
        if ch is not None:
            slot['charm'] += ch
            charm_any = True
        used += 1

    if not per_strike or not sp:
        return {
            'symbol': (symbol or None), 'spot': sp, 'empty': True,
            'contracts_used': used, 'contracts_sans_oi_reporte': sans_oi,
            'strikes': [],
            'net_gex_total': None, 'call_gex_total': None, 'put_gex_total': None,
            'net_vanna_total': None, 'net_charm_total': None,
            'max_pain': None, 'iv_skew_pts': None,
            'zero_gamma': None, 'call_wall': None, 'put_wall': None,
            'bias': None, 'regime': None, 'generator': 'deterministic',
            'reason': ('aucun spot réel' if not sp else
                       'aucun contrat avec OI + gamma exploitables (données réelles absentes)'),
        }

    strikes = []
    for k in sorted(per_strike):
        call_gex = per_strike[k]['call']
        put_gex = per_strike[k]['put']
        strikes.append({'strike': k, 'call_gex': call_gex, 'put_gex': put_gex,
                        'net_gex': call_gex + put_gex,
                        'vanna': (per_strike[k]['vanna'] if vanna_any else None),
                        'charm': (per_strike[k]['charm'] if charm_any else None)})

    total_abs = sum(abs(s['net_gex']) for s in strikes) or None
    for s in strikes:
        s['normalized'] = round(100 * s['net_gex'] / total_abs, 2) if total_abs else None

    call_total = sum(s['call_gex'] for s in strikes)
    put_total = sum(s['put_gex'] for s in strikes)
    net_total = call_total + put_total

    # Mur call = plus forte concentration call GEX (aimant/résistance).
    # Mur put  = plus forte concentration |put GEX| (support).
    call_wall = max(strikes, key=lambda s: s['call_gex'])['strike'] if strikes else None
    put_wall = min(strikes, key=lambda s: s['put_gex'])['strike'] if strikes else None

    # Niveau de bascule (zero-gamma) : strike où le net GEX CUMULÉ (bas→haut) traverse 0.
    zero_gamma = _zero_gamma(strikes)

    # Biais directionnel : part du net GEX (positif) au-dessus vs sous le spot.
    above = sum(s['net_gex'] for s in strikes if s['strike'] >= sp)
    below = sum(s['net_gex'] for s in strikes if s['strike'] < sp)
    if net_total > 0:
        regime = 'stabilisant'      # dealers long gamma → volatilité amortie
    elif net_total < 0:
        regime = 'accelerateur'     # dealers short gamma → mouvements amplifiés
    else:
        regime = 'neutre'
    if above > 0 and above >= abs(below):
        bias = 'haussier'           # gamma positif concentré au-dessus → aimant haussier
    elif below < 0 and abs(below) > abs(above):
        bias = 'baissier'
    else:
        bias = 'neutre'

    return {
        'symbol': (symbol or None), 'spot': sp, 'empty': False,
        'contracts_used': used, 'contracts_sans_oi_reporte': sans_oi,
        'strikes': strikes,
        'net_gex_total': net_total, 'call_gex_total': call_total, 'put_gex_total': put_total,
        'zero_gamma': zero_gamma, 'call_wall': call_wall, 'put_wall': put_wall,
        'gex_above_spot': above, 'gex_below_spot': below,
        # VANNA nette ($ de delta pour +1 pt d'IV) — Black-Scholes sur IV/DTE réels,
        # convention de signe naïve identique au GEX. None si IV/DTE indisponibles.
        'net_vanna_total': (sum(s['vanna'] for s in strikes if s['vanna'] is not None)
                            if vanna_any else None),
        # CHARM net ($ de delta qui dérive PAR JOUR par le seul écoulement du temps) —
        # même base Black-Scholes/convention. None si IV/DTE indisponibles.
        'net_charm_total': (sum(s['charm'] for s in strikes if s['charm'] is not None)
                            if charm_any else None),
        # MAX PAIN (aimant d'expiration, OI réels) + SKEW D'IV put/call (prime de peur).
        'max_pain': max_pain(contracts),
        'iv_skew_pts': iv_skew(contracts, sp),
        'bias': bias, 'regime': regime, 'generator': 'deterministic',
    }


def max_pain(contracts):
    """MAX PAIN : le prix d'expiration qui MINIMISE le payout total aux détenteurs
    d'options (calls: OI×max(0,P−K) ; puts: OI×max(0,K−P)) — l'« aimant d'expiration »
    classique. Évalué sur la grille des strikes réels. None si OI/strikes absents."""
    rows = []
    for c in (contracts or []):
        if not isinstance(c, dict):
            continue
        k, o = _num(c.get('strike')), _num(c.get('oi'))
        if k is None or o is None or o <= 0:
            continue
        rows.append((k, o, str(c.get('type', '')).upper() != 'PUT'))
    if not rows:
        return None
    grid = sorted({k for k, _, _ in rows})
    best_k, best_pain = None, None
    for p in grid:
        pain = sum(o * (max(0.0, p - k) if is_call else max(0.0, k - p))
                   for k, o, is_call in rows) * CONTRACT_MULTIPLIER
        if best_pain is None or pain < best_pain:
            best_k, best_pain = p, pain
    return best_k


def iv_skew(contracts, spot):
    """SKEW D'IV put/call (points d'IV) : médiane des IV des PUTS OTM (K<spot) moins
    médiane des IV des CALLS OTM (K>spot). Positif = les puts se paient plus cher
    → prime de peur. None si un des deux côtés n'a pas d'IV réelle exploitable."""
    sp = _num(spot)
    if not sp or sp <= 0:
        return None
    puts, calls = [], []
    for c in (contracts or []):
        if not isinstance(c, dict):
            continue
        k = _num(c.get('strike'))
        iv = _iv_frac(c.get('iv'))
        if k is None or iv is None:
            continue
        if str(c.get('type', '')).upper() == 'PUT' and k < sp:
            puts.append(iv)
        elif str(c.get('type', '')).upper() != 'PUT' and k > sp:
            calls.append(iv)
    if not puts or not calls:
        return None
    puts.sort()
    calls.sort()
    med_p, med_c = puts[len(puts) // 2], calls[len(calls) // 2]
    return round((med_p - med_c) * 100, 1)          # points d'IV


def _zero_gamma(strikes):
    """Niveau de bascule : interpolation linéaire du strike où le net GEX cumulé
    (des strikes bas vers hauts) traverse zéro. None si pas de traversée nette."""
    cum = 0.0
    prev_k, prev_cum = None, None
    for s in strikes:
        cum += s['net_gex']
        if prev_cum is not None and (prev_cum < 0) != (cum < 0) and (cum - prev_cum) != 0:
            frac = -prev_cum / (cum - prev_cum)                 # position du zéro entre les 2 strikes
            return round(prev_k + frac * (s['strike'] - prev_k), 2)
        prev_k, prev_cum = s['strike'], cum
    return None


__all__ = ['compute', 'max_pain', 'iv_skew']
