"""vertex.positions.calculator — calculs canoniques (§10-§12).

Règles : donnée absente → None (jamais 0) ; multiplicateur appliqué UNE
fois ; Greeks positionnels signés (long CALL Δ>0, long PUT Δ<0, theta
généralement <0, gamma/vega >0 pour un long) ; toute incohérence de signe
est signalée dans data_quality.
"""
from __future__ import annotations


def _n(v):
    return v is not None


def enrich_stock(p: dict, quote: dict | None, spy_change: float | None = None,
                 detail: dict | None = None) -> dict:
    """quote: {price, source, ts, stale}. detail: contexte scan (atr, rsi…)."""
    q = quote or {}
    price = q.get('price')
    p['current_price'] = price
    p['price_source'] = q.get('source')
    p['price_stale'] = bool(q.get('stale'))
    qty, cost = p.get('quantity'), p.get('cost_basis')
    if _n(price) and _n(qty):
        p['market_value'] = round(price * qty, 2)
    if _n(p.get('market_value')) and _n(cost):
        p['unrealized_pnl'] = round(p['market_value'] - cost, 2)
        p['unrealized_pnl_pct'] = round(p['unrealized_pnl'] / cost * 100, 2) if cost else None
    # Distances plan
    stop, tp1 = p.get('stop'), p.get('tp1')
    if _n(price) and _n(stop):
        p['risk_to_stop_pct'] = round((stop / price - 1) * 100, 2)
        if _n(qty):
            p['risk_to_stop'] = round((price - stop) * qty, 2)
        atr = (detail or {}).get('atr')
        p['stop_distance_atr'] = round((price - stop) / atr, 2) if atr else None
    if _n(price) and _n(tp1):
        p['reward_to_tp1'] = round((tp1 / price - 1) * 100, 2)
    for k, tp in (('reward_to_tp2', p.get('tp2')), ('reward_to_tp3', p.get('tp3'))):
        p[k] = round((tp / price - 1) * 100, 2) if (_n(price) and _n(tp)) else None
    # R:R restant = potentiel vers TP1 / risque vers stop (au cours ACTUEL)
    if (_n(price) and _n(stop) and _n(tp1) and price > stop):
        p['remaining_rr'] = round((tp1 - price) / (price - stop), 2)
    d = detail or {}
    p['rsi'] = d.get('rsi')
    p['rel_volume'] = d.get('rvol')
    p['ext_atr'] = d.get('ext_atr')
    p['sector'] = d.get('sector') or p.get('sector')
    if d.get('earnings_dte') is not None:
        p['days_to_earnings'] = d['earnings_dte']
    p['data_quality']['overall'] = ('STALE' if p['price_stale'] else
                                    'OK' if _n(price) else 'MISSING_PRICE')
    return p


#: D'où vient la marque d'une option. Trois conventions coexistent chez le
#: courtier lui-même, et elles ne donnent pas le même chiffre — mesuré sur
#: URA 20270115 C 50 le 24 août 2026 : dernier échange 3,70, milieu 3,90,
#: clôture 3,88, marque IBKR 3,8546, sur un marché 3,50/4,30.
#:
#: Vertex NE TRANCHE PAS entre elles (D-041) : il dit laquelle il a utilisée.
#: Une valorisation dont on ignore la convention n'est pas auditable.
MARQUE_DERNIER_ECHANGE = 'DERNIER_ECHANGE'
MARQUE_MILIEU = 'MILIEU_FOURCHETTE'
MARQUE_CLOTURE = 'CLOTURE_VEILLE'
MARQUE_ABSENTE = 'ABSENTE'
#: Une marque EXISTE mais aucune référence (dernier échange, clôture, milieu)
#: n'a été fournie avec elle : la convention est INCONNUE, pas « le dernier
#: échange ». Une provenance fausse est pire qu'une provenance absente — le
#: client sait déjà écrire « convention non renseignée ».
MARQUE_INDETERMINEE = 'INDETERMINEE'

#: Au-delà de ce spread relatif, la valorisation est incertaine d'environ la
#: moitié — afficher un P&L au centime donnerait une précision que la donnée
#: n'a pas. 10 % : au-dessous, les conventions se rejoignent à peu près.
SPREAD_INCERTAIN_PCT = 10.0


def source_de_marque(mark, *, last=None, close=None, mid=None) -> str:
    """D'où vient cette marque ? Fonction PURE, partagée serveur ET route.

    Écrite une seule fois : la dupliquer côté client la ferait diverger au
    premier ajustement, et l'écran finirait par annoncer une provenance que le
    calcul ne pratique plus.

    L'ordre du test suit celui de la production : `last` d'abord — c'est la
    priorité de `read_tk` —, puis la clôture, puis le milieu. Une marque qui
    ne correspond à AUCUN des trois, alors qu'au moins un a été fourni, vient
    quand même d'un prix échangé.

    MESURE : sur le repli scan d'une option, l'appelant ne transmettait NI
    bid/ask, NI mid, NI last — juste `mark`. La branche finale affirmait alors
    « dernier échange », et l'écran imprimait « Source de la marque : dernier
    échange » pour un MILIEU de fourchette (NVDA 2026-10-23 245 C :
    (6,00 + 6,40) / 2 = 6,20 ; GEN : 1,18 ; MPC : 23,95 — trois sur trois des
    milieux du board). Sans aucune référence, la convention est INDÉTERMINÉE.
    """
    if mark is None:
        return MARQUE_MILIEU if mid is not None else MARQUE_ABSENTE
    if last is not None and mark == last:
        return MARQUE_DERNIER_ECHANGE
    if close is not None and mark == close:
        return MARQUE_CLOTURE
    if mid is not None and round(float(mark), 4) == round(float(mid), 4):
        return MARQUE_MILIEU
    if last is None and close is None and mid is None:
        return MARQUE_INDETERMINEE
    return MARQUE_DERNIER_ECHANGE


def enrich_option(p: dict, quote: dict | None, underlying_quote: dict | None = None,
                  greeks: dict | None = None, detail: dict | None = None) -> dict:
    """quote: {mark, bid, ask, iv, volume, oi, source}. greeks: broker/model
    avec étiquette. Tout absent = None honnête."""
    q = quote or {}
    mult = p.get('multiplier') or 100.0
    qty = p.get('quantity')
    for k in ('bid', 'ask', 'last', 'iv', 'volume'):
        if q.get(k) is not None:
            p[k] = q[k]
    if q.get('oi') is not None:
        p['open_interest'] = q['oi']
    #  Le dernier échange est TRANSMIS, plus perdu. Avant, `_quote_for_option`
    #  ne le passait pas : l'écran montrait `mark 3,70` avec `last: None`, donc
    #  un chiffre sans origine lisible.
    if q.get('last') is not None and p.get('last') is None:
        p['last'] = q['last']

    #  Le MILIEU se calcule dès que les deux côtés existent, même quand la
    #  marque vient d'ailleurs. Sans lui, impossible de comparer le prix d'un
    #  échange au milieu du marché courant — l'écart entre les deux EST
    #  l'information sur un contrat peu liquide.
    if _n(p.get('bid')) and _n(p.get('ask')):
        p['mid'] = round((p['bid'] + p['ask']) / 2, 4)

    mark = q.get('mark') if q.get('mark') is not None else q.get('last')
    source = source_de_marque(mark, last=q.get('last'), close=q.get('close'),
                              mid=p.get('mid'))
    if mark is None and p.get('mid') is not None:
        mark = p['mid']
    p['mark'] = mark
    p['mark_source'] = source
    if _n(mark) and _n(qty):
        p['market_value'] = round(mark * mult * qty, 2)
    cap = p.get('capital_committed')
    if _n(p.get('market_value')) and _n(cap):
        p['unrealized_pnl'] = round(p['market_value'] - cap, 2)
        p['unrealized_pnl_pct'] = round(p['unrealized_pnl'] / cap * 100, 2) if cap else None
    if _n(p.get('bid')) and _n(p.get('ask')):
        p['spread_absolute'] = round(p['ask'] - p['bid'], 4)
        mid = (p['ask'] + p['bid']) / 2
        p['spread_pct'] = round(p['spread_absolute'] / mid * 100, 2) if mid else None
        #  Un marché large rend TOUTE convention de marque incertaine : à
        #  20,5 % de spread, dernier échange, milieu et marque du courtier
        #  s'écartent de plusieurs pour cent. Le dire vaut mieux qu'un P&L au
        #  centime qui promet une précision inexistante.
        p['valorisation_incertaine'] = (
            bool(p['spread_pct'] >= SPREAD_INCERTAIN_PCT)
            if p.get('spread_pct') is not None else None)
    else:
        #  Sans fourchette, l'incertitude est INCONNUE — pas faible. Rendre
        #  False ferait passer une ignorance pour une garantie.
        p['spread_pct'] = p.get('spread_pct')
        p['valorisation_incertaine'] = None
    if _n(p.get('volume')) and _n(p.get('open_interest')) and p['open_interest']:
        p['volume_oi_ratio'] = round(p['volume'] / p['open_interest'], 3)

    u = underlying_quote or {}
    spot = u.get('price')
    p['underlying_price'] = spot
    K, right, avg = p.get('strike'), p.get('right'), p.get('average_cost')
    if _n(spot) and _n(K):
        intr = max(0.0, spot - K) if right == 'CALL' else max(0.0, K - spot)
        p['intrinsic_value'] = round(intr, 4)
        if _n(mark):
            p['extrinsic_value'] = round(mark - intr, 4)
        p['moneyness'] = round(spot / K, 4)
    if _n(K) and _n(avg):
        p['breakeven'] = round(K + avg, 4) if right == 'CALL' else round(K - avg, 4)

    # Greeks POSITIONNELS : par-option × multiplicateur × quantité (signés)
    g = greeks or {}
    p['greeks_source'] = g.get('source', 'UNAVAILABLE')
    issues = p['data_quality'].setdefault('issues', [])
    #  Une échéance ILLISIBLE n'est pas une échéance absente. Mesuré sur le desk
    #  réel : `expiration: '2027.01.15'` → `dte: None`, `issues: []`, donc
    #  strictement indistinguable d'une ligne sans échéance — et les gates
    #  EXPIRED / DTE_WARNING / THETA_WARNING (lifecycle.py) restaient désarmés
    #  en silence, jusqu'au jour de l'expiration. On NOMME le défaut ; la
    #  déclaration de l'utilisateur, elle, n'est jamais réécrite.
    from vertex.positions.models import echeance_normalisee as _echeance
    #  `not in issues` : mesuré, deux enrichissements du MÊME dict empilaient
    #  'EXPIRATION_ILLISIBLE' deux fois, et `data_quality.issues` est publié tel
    #  quel. Un défaut listé deux fois n'est pas deux défauts. (Le motif
    #  `issues.append` sans dédoublonnage préexiste sur les drapeaux de signe ;
    #  seul le drapeau ajouté au constat 29 est traité ici.)
    if (p.get('expiration') and _echeance(p['expiration']) is None
            and 'EXPIRATION_ILLISIBLE' not in issues):
        issues.append('EXPIRATION_ILLISIBLE')
    for name in ('delta', 'gamma', 'theta', 'vega'):
        per = g.get(name)
        # Quantité inconnue → Greek positionnel INCONNU (None), jamais 0 fabriqué
        # (règle de vérité : absent ≠ zéro). On garde tout de même la valeur
        # unitaire par option si elle existe.
        if per is None or qty is None:
            p[name] = None
            if per is not None:
                p[f'{name}_per_option'] = per
            continue
        p[name] = round(per * mult * qty, 4)
        p[f'{name}_per_option'] = per
    # Cohérence des signes (long uniquement — le desk modélise l'achat)
    dpo = g.get('delta')
    if dpo is not None:
        if right == 'CALL' and dpo < 0:
            issues.append('DELTA_SIGN_INCONSISTENT')
        if right == 'PUT' and dpo > 0:
            issues.append('DELTA_SIGN_INCONSISTENT')
    if g.get('gamma') is not None and g['gamma'] < 0:
        issues.append('GAMMA_SIGN_INCONSISTENT')
    if g.get('vega') is not None and g['vega'] < 0:
        issues.append('VEGA_SIGN_INCONSISTENT')

    # Divergence broker/modèle (§12)
    bd, md = g.get('broker_delta'), g.get('model_delta')
    if bd is not None and md is not None and abs(bd - md) >= 0.12:
        issues.append('BROKER_MODEL_GREEK_DIVERGENCE')

    #  UNE SYNTHÈSE QUI CONTREDIT SON PROPRE DÉTAIL. Mesuré sur une option à
    #  échéance illisible avec marque 6,00 : `overall: 'OK'`,
    #  `issues: ['EXPIRATION_ILLISIBLE']`, `dte: None` — le badge disait « OK »
    #  pendant que la liste juste à côté nommait une échéance dont les gates de
    #  cycle de vie ne s'armeront jamais. Un badge ne peut pas être plus propre
    #  que ce qu'il résume. `DEGRADED` n'invente rien : il est VRAI dès qu'un
    #  défaut est listé, et il disparaît dès que la liste est vide.
    #  Ni `alerts.py` (== 'STALE') ni `thesis_health` (STALE/MISSING_*) ne lisent
    #  cet état : l'ajout est additif, aucun seuil ne bouge.
    if not _n(mark):
        p['data_quality']['overall'] = 'MISSING_MARK'
    else:
        p['data_quality']['overall'] = 'DEGRADED' if issues else 'OK'
    if q.get('stale'):
        p['data_quality']['overall'] = 'STALE'
    return p


def portfolio_weights(positions: list[dict]) -> list[dict]:
    """Poids = valeur (ou coût si non cotée, étiqueté) / total."""
    total = 0.0
    for p in positions:
        v = p.get('market_value')
        if v is None:
            v = p.get('cost_basis') or p.get('capital_committed')
        if v is not None:
            total += v
    for p in positions:
        v = p.get('market_value')
        based_on_cost = v is None
        if v is None:
            v = p.get('cost_basis') or p.get('capital_committed')
        p['weight_pct'] = round(v / total * 100, 2) if (v is not None and total) else None
        p['weight_based_on_cost'] = based_on_cost if p['weight_pct'] is not None else None
    return positions


def mae_mfe(cost_basis: float, values: list[float]) -> dict:
    """MAE/MFE en % depuis la série de valeurs de la position (déclarée).

    **Le calcul de MAE/MFE n'est plus fait ici** : il est délégué à
    `vertex.tracking.returns.mae_mfe`, seule implémentation vivante de cette
    notion dans le produit (3 sites d'appel ; celle-ci n'en avait aucun). Deux
    calculs de la même mesure, ce n'est pas de la duplication de code — c'est
    **deux réponses possibles à la même question**, et elles divergeaient :

    | entrée | ici, avant | `tracking.returns` |
    | --- | --- | --- |
    | base **négative** | `mae -220 · mfe -200` | `None · None` |
    | `None` dans la série | `TypeError` | valeurs filtrées |
    | chaîne numérique | `TypeError` | coercée |

    La première ligne est la vraie faute : `if not cost_basis` rejette `0` et
    `None` mais **laisse passer un négatif**, et rend alors un chiffre
    parfaitement plausible tiré d'une entrée absurde — exactement ce que
    l'invariant « aucune donnée financière inventée » interdit.

    `drawdown_from_peak` reste calculé ici, et ce n'est pas un oubli :
    `tracking.drawdown_from_high` rend le drawdown **courant** (depuis le plus
    haut jusqu'à la dernière valeur), celui-ci rend le drawdown **maximal**
    subi sur le chemin. Deux métriques, pas deux implémentations.
    """
    #  Import local : `tracking` est la couche canonique, `positions` ne doit
    #  pas en dependre au chargement du module.
    from vertex.tracking.returns import _num, mae_mfe as _canonique

    mm = _canonique(cost_basis, values)
    if mm['mae_pct'] is None:
        return {'mae': None, 'mfe': None, 'drawdown_from_peak': None}

    #  Meme coercion que la couche canonique : sans elle, cette fonction
    #  accepterait des series que le calcul delegue a deja acceptees, puis
    #  leverait ici — le pire des deux mondes.
    vals = [v for v in (_num(x) for x in (values or [])) if v is not None]
    peak, dd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        if peak:
            dd = min(dd, (v / peak - 1) * 100)
    return {'mae': mm['mae_pct'], 'mfe': mm['mfe_pct'],
            'drawdown_from_peak': round(dd, 2)}


__all__ = ['enrich_stock', 'enrich_option', 'portfolio_weights', 'mae_mfe']
