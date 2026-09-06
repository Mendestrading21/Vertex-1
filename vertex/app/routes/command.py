"""
vertex/app/routes/command.py — COMMAND CENTER (Blueprint, Ch. II).

Les deux vues de commandement : /api/command (régime, top actions/options,
alertes du risk manager, décision du jour, exposition) et /api/portefeuille
(portefeuille d'options construit sur un capital donné).

Les moteurs (risk manager, validateur, stratégie options) viennent des moteurs purs `vertex.*` —
modules purs, sans Flask ; l'état partagé vient de `vertex.app.state`.

Machine de décision — lecture seule, aucun ordre. Logique déplacée verbatim.
"""

from flask import Blueprint, jsonify, request

from vertex.portfolio import legacy_basket_risk as portfolio_risk
from vertex.strategy import legacy_adapter as strategy
from vertex.validation import out_of_sample as validator
from vertex.app.state import scan_state
from vertex.engines import market_lens

bp = Blueprint('command', __name__)

CAPITAL_MIN = 5_000
CAPITAL_MAX = 1_000_000
CAPITAL_DEFAULT = 100_000


def _climat(mc):
    """Le climat de marché COMPLET — score ET marqueurs de couverture.

    Remplace `_market_score`, qui ne rendait QUE le nombre (aucun autre
    appelant dans le dépôt : relevé .py/.js du 2026-09-06, la seule autre
    définition du nom vit dans `vertex/engines/session_digest.py` et lui est
    propre). Un accesseur qui laisse le nombre partir sans ce qui le qualifie
    est précisément ce qui a produit le défaut ci-dessous : il n'est pas
    conservé « au cas où ».

    MESURE DU 2026-09-06 : la route ne lisait que `cl['score']`. Or
    `market_lens.climate` substitue 50 % à une largeur de marché ABSENTE — la
    composante participation pèse 25 points sur 100 — et le dit dans le même
    dictionnaire (`partiel`, `breadth_status`, `note`). Résultat servi :
    largeur mesurée à 50 % et largeur absente rendaient le MÊME `score: 74`,
    sans qu'aucun champ ne distingue une mesure d'une substitution. Le contrat
    interdit la valeur supposée servie comme une valeur mesurée : les trois
    marqueurs partent désormais avec le score.
    """
    return market_lens.climate(mc)


@bp.route('/api/command')
def api_command():
    """VERTEX COMMAND CENTER : consolide régime, top actions/options, alertes,
    décision du jour, exposition. Machine de décision — lecture seule, aucun ordre."""
    mc = scan_state.get('market_ctx') or {}
    cm = scan_state.get('committee') or {}
    st = scan_state.get('strategy') or {}
    detail = scan_state.get('detail') or {}
    climat = _climat(mc)
    score = climat['score'] if climat else None
    reg, roro = mc.get('spy_regime'), mc.get('roro')
    # régime final
    if roro == 'RISK-OFF':
        regime = {'label': '🔴 RISK-OFF', 'color': '#EF4444'}
    elif roro == 'RISK-ON' and reg != 'CHOP':
        regime = {'label': '🟢 RISK-ON', 'color': '#22C55E'}
    else:
        regime = {'label': '🟡 NEUTRE', 'color': '#FFB23F'}
    regime.update({'score': score, 'spy_regime': reg, 'roro': roro})
    #  Les marqueurs ne sont posés QUE dans le cas dégradé : à couverture
    #  complète, `regime` garde exactement sa forme historique — c'est la
    #  convention du moteur, tenue jusqu'ici.
    if climat and climat.get('partiel'):
        regime.update({'score_partiel': True,
                       'breadth_status': climat.get('breadth_status'),
                       'score_note': climat.get('note')})
    # top 5 actions (comité actionnable) + bloc VERTEX (edge probabiliste)
    decisions = cm.get('decisions') or []

    def _vtx(sym):
        v = (detail.get(sym) or {}).get('vertex') or {}
        mc2 = v.get('mc') or {}
        return {'verdict': v.get('verdict'), 'edge': v.get('edge'),
                'p_win': (v.get('ml') or {}).get('p_win'),
                'p_tp1': mc2.get('p_hit_tp1'), 'edge_bps': mc2.get('edge_mean_bps'),
                'no_trade': v.get('no_trade')}
    top_stocks = [{'symbol': d['symbol'], 'verdict': d['verdict'], 'color': d['color'],
                   'conviction': d['conviction'], 'price': d['price'],
                   'rr': (d.get('plan') or {}).get('rr'), 'note': d['note'],
                   'vertex': _vtx(d['symbol'])}
                  for d in decisions if d['verdict'] in ('ACHETER', 'RENFORCER')][:5]
    # top 5 options (meilleure échéance 6 mois)
    top_options = []
    for p in (st.get('picks') or [])[:5]:
        d = p.get('primary', 'CALL')
        legs = (p.get('put') if d == 'PUT' else p.get('call')) or []
        leg = next((l for l in legs if l.get('key') == 'm6'), legs[0] if legs else None)
        if leg:
            sc = leg.get('scenarios') or {}
            top_options.append({'symbol': p['symbol'], 'dir': d, 'label': leg['label'],
                                'strike': leg['strike'], 'premium': leg['premium'],
                                'prob': (sc.get('prob') or {}).get('pct'),
                                'except': (sc.get('except') or {}).get('pct'),
                                # champs RÉELS du moteur (jamais inventés) → carte enrichie
                                'dte': leg.get('dte'), 'delta': leg.get('delta'),
                                'breakeven': leg.get('breakeven'), 'spot': p.get('price')})
    # alertes rouges (risk manager, niveau marché)
    alerts = []
    if roro == 'RISK-OFF':
        alerts.append(['🔴', 'RISK-OFF', "Marché risk-off — réduire l'exposition, pas de nouveau pari agressif."])
    if reg == 'CHOP':
        alerts.append(['🟠', 'RANGE', 'Marché sans tendance (chop) — les cassures échouent, patience.'])
    vix = mc.get('vix')
    if vix and vix > 22:
        alerts.append(['🟠', 'VOLATILITÉ', f'VIX {round(vix)} élevé — options chères, dimensionner petit.'])
    overext = sum(1 for dd in detail.values() if (dd.get('ext_atr') or 0) >= 3)
    if overext >= 5:
        alerts.append(['🟠', 'EUPHORIE', f'{overext} titres très étendus — ne pas chasser, attendre les replis.'])
    # décision du jour
    n_act = len(top_stocks)
    if roro == 'RISK-OFF' or reg == 'CHOP':
        decision = {'action': 'RÉDUIRE / DÉFENSIF', 'color': '#EF4444',
                    'msg': 'Préserver le capital : cash + couvertures. On n\'attaque pas.'}
    elif n_act >= 2 and (score or 0) >= 55:
        decision = {'action': 'ATTAQUER', 'color': '#22C55E',
                    'msg': f'{n_act} setups validés en marché porteur — déployer avec discipline (R:R ≥ 2:1).'}
    else:
        decision = {'action': 'ATTENDRE / SÉLECTIF', 'color': '#FFB23F',
                    'msg': 'Peu d\'avantage statistique — n\'acheter que l\'exceptionnel, garder du cash.'}
    #  Ces deux branches-ci COMPARENT le score (seuil 55) ; la branche
    #  défensive, elle, ne dépend que du roro/régime. Quand la largeur manque,
    #  le score comparé porte une participation SUBSTITUÉE (50 %) : la phrase
    #  servie le dit, au lieu d'affirmer un « marché porteur » mesuré.
    if climat and climat.get('partiel') and decision['action'] != 'RÉDUIRE / DÉFENSIF':
        decision = {**decision, 'score_partiel': True,
                    'msg': decision['msg'] + ' Score de marché PARTIEL : largeur de '
                                             'marché non mesurée (25 pts sur 100).'}
    # RISK MANAGER portefeuille (corrélation / concentration / secteurs)
    risk_availability = {'available': False, 'status': 'PORTFOLIO_RISK_UNAVAILABLE',
                         'read_only': True,
                         'reason': 'contrôle de risque portefeuille indisponible'}
    try:
        risk = portfolio_risk.build([r['symbol'] for r in (cm.get('decisions') or [])
                                     if r['verdict'] in ('ACHETER', 'RENFORCER')][:8] or
                                    [r['symbol'] for r in (scan_state.get('rows') or [])[:8]],
                                    detail)
        risk_availability = {'available': True, 'status': 'PORTFOLIO_RISK_AVAILABLE',
                             'read_only': True}
    except Exception:
        risk = None
    if risk:
        #  DEUX FAMILLES DE DRAPEAUX, ET L'ÉCRAN N'EN VOYAIT QU'UNE.
        #
        #  Le moteur (`legacy_basket_risk`) sépare depuis le tour 1 ce qui
        #  BLOQUE le risque neuf (corrélation, concentration sectorielle) de ce
        #  qui est ARITHMÉTIQUE (`ligne_trop_grosse` : avec un plafond de 15 %
        #  par ligne, cinq lignes valent 20 % chacune). La condition d'entrée
        #  était `risk.get('no_new_risk')`, qui ne suit plus que la première
        #  famille : le drapeau structurel — VRAI, servi, et le seul armé sur
        #  tout panier de 2 à 6 lignes — ne pouvait donc plus produire aucune
        #  ligne à l'écran. Mesure : sur un panier de 3 titres, `flags` porte
        #  `ligne_trop_grosse`, `max_weight` vaut 33,3 % pour `limits.max_pos`
        #  15 %, et `alerts` était vide.
        #
        #  Il est DIT, jamais transformé en blocage : pastille distincte, et le
        #  texte nomme l'arithmétique et rappelle qu'ajouter reste permis —
        #  ajouter une ligne est précisément le remède à ce poids-là.
        #
        #  Les deux alertes bloquantes ne changent pas de comportement : leur
        #  drapeau est ce qui arme `no_new_risk`, la garde extérieure était
        #  redondante pour elles.
        _bloquants = risk.get('flags_bloquants')
        if _bloquants is None:                    # moteur antérieur à la séparation
            _bloquants = risk.get('flags') or []
        _structurels = risk.get('flags_structurels') or []
        _lim = risk.get('limits') or {}
        if 'correlation_panier_elevee' in _bloquants:
            alerts.append(['🟠', 'CORRÉLATION', f"Panier trop corrélé ({risk['avg_corr']}) — diversifier avant d'ajouter du risque."])
        if 'concentration_sectorielle' in _bloquants:
            alerts.append(['🟠', 'CONCENTRATION', f"Secteur {risk.get('max_sector_name')} à {risk.get('max_sector')}% — trop concentré."])
        if 'ligne_trop_grosse' in _bloquants:
            alerts.append(['🟠', 'POIDS DE LIGNE',
                           f"Ligne la plus lourde à {risk.get('max_weight')} % pour un plafond de "
                           f"{_lim.get('max_pos')} % — concentration subie sur {risk.get('n')} lignes."])
        if 'ligne_trop_grosse' in _structurels:
            alerts.append(['🟡', 'RÉPARTITION',
                           f"Ligne la plus lourde à {risk.get('max_weight')} % pour un plafond de "
                           f"{_lim.get('max_pos')} % : arithmétique de {risk.get('n')} lignes "
                           f"({risk.get('n')} × {_lim.get('max_pos')} % < 100 %), pas une "
                           "concentration subie — n'interdit pas d'ajouter une ligne."])
    validation_availability = {'available': False, 'status': 'PORTFOLIO_VALIDATION_UNAVAILABLE',
                               'read_only': True,
                               'reason': 'validation portefeuille indisponible'}
    try:
        valid = validator.build((scan_state.get('portfolio') or {}).get('equity') or [])
        validation_availability = {'available': True, 'status': 'PORTFOLIO_VALIDATION_AVAILABLE',
                                   'read_only': True}
    except Exception:
        valid = None
    return jsonify({'regime': regime, 'portfolio_score': score, 'decision': decision,
                    'top_stocks': top_stocks, 'top_options': top_options, 'alerts': alerts,
                    'counts': cm.get('counts') or {}, 'risk': risk, 'validation': valid,
                    'controls_availability': {'risk': risk_availability,
                                              'validation': validation_availability,
                                              'does_not_change_decision': True,
                                              'read_only': True},
                    'exposure': {'actions': '70-90%', 'options': '10-20%', 'etf': 'tampon / cash'}})


@bp.route('/api/portefeuille')
def api_portefeuille():
    """Portefeuille d'options construit sur un capital (50k/100k/200k…). Analyse only."""
    try:
        cap = int(float(request.args.get('capital', CAPITAL_DEFAULT)))
    except Exception:
        cap = CAPITAL_DEFAULT
    cap = max(CAPITAL_MIN, min(cap, CAPITAL_MAX))
    rows = scan_state.get('rows')
    if not rows:
        #  `{}` nu ne disait pas si le portefeuille était vide ou si le calcul
        #  n'avait pas tourné. Mesuré le 2026-09-06 : la charge vide ne portait
        #  aucune clé. Le capital demandé est rendu, pour qu'un appelant sache
        #  que sa requête a bien été comprise.
        return jsonify({'disponible': False, 'read_only': True,
                        'motif': 'aucune ligne dans le dernier scan — le '
                                 'portefeuille d’options ne peut pas être '
                                 'construit',
                        'capital': cap, 'scan': scan_state.get('scan_ts_h')})
    try:
        return jsonify(strategy.build_portfolio(
            rows, scan_state.get('detail'),
            market=scan_state.get('market_ctx'), capital=cap,
            board=scan_state.get('options_board') or []))
    except Exception as e:                            # noqa: BLE001
        #  Une panne se nomme AUTREMENT qu'une absence : `disponible` reste
        #  absent ici, et `error` porte un code STABLE.
        #
        #  Le type de l'exception a été servi un instant, puis retiré : le
        #  gardien `test_aucune_exception_servie` l'a refusé, et il a raison —
        #  un nom de classe est un détail d'implémentation qui voyage jusqu'au
        #  client, change au moindre refactoring, et ne dit rien d'utile à qui
        #  lit. Le code reste stable, la note reste en français, le détail
        #  reste côté serveur.
        return jsonify({'error': 'portfolio_analysis_unavailable',
                        'read_only': True,
                        'motif': 'le moteur de portefeuille a échoué sur ce '
                                 'scan — ce n’est pas une absence de données'})


__all__ = ['bp']
