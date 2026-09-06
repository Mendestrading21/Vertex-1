"""Tests — honnêteté des calculs Greeks (audit système, §21).

Vérifie qu'aucune valeur absente n'est transformée en 0 fabriqué et qu'aucun
label de provenance (BROKER_GREEKS) n'est apposé sans valeurs réelles.
"""
from vertex.positions import calculator
from vertex.portfolio import risk_engine


def _opt(qty=1):
    return {
        'asset_type': 'OPTION', 'symbol': 'AAPL', 'right': 'CALL',
        'strike': 200, 'expiration': '2026-09-18', 'quantity': qty,
        'multiplier': 100, 'cost_total': 500, 'capital_committed': 500,
        'avg_cost': 5.0, 'data_quality': {},
    }


def test_positional_greek_none_when_quantity_unknown():
    """qty=None → Greek positionnel None, jamais 0 fabriqué (mais valeur unitaire gardée)."""
    p = _opt(qty=None)
    calculator.enrich_option(p, {'mark': 6.0, 'iv': 0.3}, None,
                             {'source': 'BROKER_GREEKS', 'delta': 0.5}, {})
    assert p['delta'] is None
    assert p.get('delta_per_option') == 0.5


def test_positional_greek_computed_once_with_quantity():
    p = _opt(qty=2)
    calculator.enrich_option(p, {'mark': 6.0, 'iv': 0.3}, None,
                             {'source': 'BROKER_GREEKS', 'delta': 0.5}, {})
    # 0.5 × 100 × 2 = 100 (multiplicateur appliqué une seule fois)
    assert p['delta'] == 100.0
    assert p['greeks_source'] == 'BROKER_GREEKS'


def test_no_broker_greeks_label_without_values():
    """Sans valeurs de Greeks, la provenance ne doit pas être BROKER_GREEKS."""
    p = _opt(qty=1)
    calculator.enrich_option(p, {'mark': 6.0, 'iv': 0.3}, None, None, {})
    assert p['greeks_source'] == 'UNAVAILABLE'
    assert p['delta'] is None


def test_une_marque_sans_aucune_reference_ne_pretend_pas_venir_d_un_echange():
    """MESURE : `POST /api/pos-quotes` rendait
    `{"mark":6.2,"mark_source":"DERNIER_ECHANGE","spot":230.36,"spread_pct":null}`
    pour NVDA 2026-10-23 245 C, alors que 6,20 est le MILIEU du board
    ((6,00 + 6,40) / 2 ; idem GEN 1,18 et MPC 23,95). Le dict de repli ne porte
    ni bid, ni ask, ni mid, ni last : la branche finale de `source_de_marque`
    affirmait une convention qu'elle n'avait aucun moyen de connaître, et le
    tiroir « Provenance et qualité » imprimait « Source de la marque : dernier
    échange ». Sans référence, la convention est INDÉTERMINÉE — le client sait
    déjà rendre cela par « convention non renseignée »."""
    assert calculator.source_de_marque(6.2) == calculator.MARQUE_INDETERMINEE
    p = _opt(qty=1)
    calculator.enrich_option(p, {'mark': 6.2}, None, None, {})
    assert p['mark'] == 6.2                       # la marque reste servie
    assert p['mark_source'] == calculator.MARQUE_INDETERMINEE


def test_les_trois_conventions_connues_restent_nommees():
    """Non-régression : dès qu'une référence est fournie, la provenance est
    affirmée comme avant — c'est l'affirmation SANS preuve qui est retirée."""
    assert calculator.source_de_marque(6.2, last=6.2) == calculator.MARQUE_DERNIER_ECHANGE
    assert calculator.source_de_marque(6.2, close=6.2) == calculator.MARQUE_CLOTURE
    assert calculator.source_de_marque(6.2, mid=6.2) == calculator.MARQUE_MILIEU
    #  Une marque qui ne colle à aucune des références FOURNIES vient bien d'un
    #  prix échangé : ce cas-là garde son étiquette.
    assert calculator.source_de_marque(6.35, mid=6.2) == calculator.MARQUE_DERNIER_ECHANGE
    assert calculator.source_de_marque(None) == calculator.MARQUE_ABSENTE


# ── Constat 29 : une échéance illisible n'est pas une échéance absente ──────

def test_lecheance_declaree_se_relit_quel_que_soit_le_separateur():
    """MESURE : le desk réel stocke `exp='2027.01.15'` (saisie libre) alors que
    le board d'options ne sert que du 'YYYY-MM-DD'. `_dte('2027.01.15')`
    rendait None là où `_dte('2027-01-15')` rend 131 jours — donc EXPIRED,
    DTE_WARNING et THETA_WARNING ne pouvaient jamais s'armer sur 2 des 3
    positions déclarées. La normalisation est une lecture, pas une réécriture :
    `desk_data.json` n'est pas touché."""
    from vertex.positions.models import _dte, echeance_normalisee
    for forme in ('2027-01-15', '2027.01.15', '2027/01/15', '20270115',
                  '2027-01-15T00:00:00'):
        assert echeance_normalisee(forme) == '2027-01-15', forme
        assert _dte(forme) == _dte('2027-01-15'), forme
    assert echeance_normalisee('2026.10') == '2026-10'        # mois seul reconnu
    assert _dte('2026-10') is None                            # jour inconnu, jamais deviné


def test_une_date_non_reconnue_ne_devient_jamais_une_date_plausible():
    """Rien n'est deviné : une date impossible ou incomplète rend None."""
    from vertex.positions.models import echeance_normalisee
    for forme in ('demain', '2027-1-5', '2027-02-31', '15/01/2027', '', None):
        assert echeance_normalisee(forme) is None, forme


def test_une_echeance_illisible_est_nommee_et_non_confondue_avec_une_absence():
    """MESURE : `/api/positions/state` rendait `expiration:'2027.01.15',
    dte:None, data_quality:{'overall':'MISSING_MARK','issues':[]}` — une date
    illisible strictement indistinguable d'une date absente, sans aucun
    `issue`. Le défaut est désormais NOMMÉ (et le reste après normalisation,
    pour une date réellement invalide)."""
    from vertex.positions import audit
    p = _opt(qty=1)
    p['expiration'] = 'demain'
    calculator.enrich_option(p, {'mark': 6.0}, None, None, {})
    assert 'EXPIRATION_ILLISIBLE' in p['data_quality']['issues']
    # L'audit d'intégrité le nomme aussi, à côté de EXPIRATION_MISSING.
    errs = audit._check({'symbol': 'AAPL', 'quantity': 1, 'capital_committed': 500,
                         'currency': 'USD', 'source': 'MANUAL', 'asset_type': 'OPTION',
                         'strike': 200, 'expiration': 'demain', 'thesis_text': 'x'})
    assert errs == ['EXPIRATION_ILLISIBLE']


def test_une_echeance_illisible_nest_nommee_quune_fois():
    """MESURE : deux enrichissements du même dict empilaient
    `issues: ['EXPIRATION_ILLISIBLE', 'EXPIRATION_ILLISIBLE']`, et cette liste
    est publiée telle quelle. Un défaut listé deux fois n'est pas deux
    défauts."""
    p = _opt(qty=1)
    p['expiration'] = 'demain'
    calculator.enrich_option(p, {'mark': 6.0}, None, None, {})
    calculator.enrich_option(p, {'mark': 6.1}, None, None, {})
    assert p['data_quality']['issues'].count('EXPIRATION_ILLISIBLE') == 1


def test_une_echeance_lisible_ne_leve_aucun_probleme():
    """Non-régression : les formes reconnues ne déclenchent rien."""
    from vertex.positions import audit
    p = _opt(qty=1)
    p['expiration'] = '2027.01.15'
    calculator.enrich_option(p, {'mark': 6.0}, None, None, {})
    assert 'EXPIRATION_ILLISIBLE' not in p['data_quality']['issues']
    assert audit._check({'symbol': 'AAPL', 'quantity': 1, 'capital_committed': 500,
                         'currency': 'USD', 'source': 'MANUAL', 'asset_type': 'OPTION',
                         'strike': 200, 'expiration': '2027.01.15', 'thesis_text': 'x'}) == []


def _opt_declaree(exp='2027-01-15', right='CALL', pid='p1'):
    """Ligne d'option COMPLÈTE (aucune autre erreur d'audit possible)."""
    return {'position_id': pid, 'symbol': 'MSFT', 'asset_type': 'OPTION',
            'quantity': 7, 'capital_committed': 9800.0, 'currency': 'USD',
            'source': 'MANUAL', 'strike': 500.0, 'expiration': exp,
            'multiplier': 100, 'right': right, 'thesis_text': 'thèse déclarée'}


def test_le_meme_contrat_declare_dans_deux_formats_reste_un_doublon():
    """MESURE : MSFT 2027-01-15 500 C saisi une fois '2027-01-15' et une fois
    '2027.01.15' — le format réellement présent sur le desk — sortait
    `status: HEALTHY`, `critical: 0`, `findings: []`, alors que les DEUX mêmes
    formats sortent `CRITICAL` / DUPLICATE_IDENTITY. La clé d'identité
    comparait la chaîne brute : 9 800 $ de capital engagé comptés deux fois
    échappaient à l'audit d'intégrité."""
    from vertex.positions import audit
    r = audit.audit_positions([_opt_declaree('2027-01-15', pid='p1'),
                               _opt_declaree('2027.01.15', pid='p2')])
    assert r['status'] == 'CRITICAL'                     # valait HEALTHY
    assert any('DUPLICATE_IDENTITY' in f['errors'] for f in r['findings'])


def test_un_straddle_nest_pas_un_doublon():
    """MESURE, dans l'autre sens : un CALL et un PUT MSFT 2027-01-15 500 —
    deux contrats DIFFÉRENTS — sortaient `CRITICAL` avec DUPLICATE_IDENTITY,
    parce que le sens de l'option ne faisait pas partie de l'identité. Un
    défaut inventé est aussi faux qu'un défaut caché."""
    from vertex.positions import audit
    r = audit.audit_positions([_opt_declaree(right='CALL', pid='p1'),
                               _opt_declaree(right='PUT', pid='p2')])
    assert r['status'] == 'HEALTHY'                      # valait CRITICAL
    assert r['findings'] == []


def test_deux_saisies_identiques_restent_un_doublon():
    """Non-régression : le doublon franc reste détecté."""
    from vertex.positions import audit
    r = audit.audit_positions([_opt_declaree(pid='p1'), _opt_declaree(pid='p2')])
    assert r['status'] == 'CRITICAL'


# ── Constat 41, SECOND SITE : le catalyseur noté 60 dans le recalculateur ──

def _desk_une_action():
    import json
    return {'data': {'myTrades': json.dumps([
        {'id': 1, 'sym': 'AAPL', 'type': 'STK', 'qty': 10, 'cost': 2000,
         'entrySnap': {'stop': 190.0, 'tgt': 300.0, 'thesis': 'thèse déclarée'}}])}}


def _scan_sans_garde_fou():
    """Scan à la FORME RÉELLE du produit — c'est le cœur du constat 5/7.

    Cette fixture posait `market: {'spy_trend','breadth','vix'}` et
    `detail['AAPL']['st_fund']`. Les deux formes sont MORTES en production :
    `scan_state['market']` est l'horloge de séance (clés réelles
    ['et','open','session'], terminal.py), les dimensions du régime vivent dans
    `market_ctx`, et la note fondamentale vit dans `detail['sub']['fundamental']`
    (`analysis.analyse` → 'sub': sc) — `st_fund` n'est posée que sur la LIGNE de
    tableau, `fund_score` n'a aucune assignation dans le dépôt. Une fixture qui
    parle un vocabulaire que personne n'émet ne peut pas voir le défaut : elle
    servait 72 au recalculateur là où le scan réel lui servait None.
    """
    return {'source': 'ibkr',
            'market': {'et': '10:31', 'open': True, 'session': 'REGULAR'},
            'market_ctx': {'spy_regime': 'TREND', 'vix': 15.0,
                           'breadth': {'above200': 68}, 'roro': 'RISK-ON'},
            'detail': {'AAPL': {'price': 210.0, 'score': 72, 'rs': 72,
                                'rr': 4.5, 'earnings_dte': 20, 'sector': 'Technology',
                                'sub': {'fundamental': 72,
                                        'fundamental_is_proxy': False},
                                #  LES DEUX PREUVES CRITIQUES QUE PORTE UN SCAN
                                #  RÉEL. `scan_evidence.build_scan` pose
                                #  `detail['data_quality']` et
                                #  `detail['reconciliation']` sur CHAQUE titre
                                #  scanné (vérifié chez le producteur). La
                                #  fixture ne les portait pas : le
                                #  recalculateur ne s'en apercevait pas, parce
                                #  qu'il fabriquait à la main un
                                #  `reconciliation: {'actionable_allowed':
                                #  True}` — une autorisation affirmée sans
                                #  mesure. Depuis qu'il passe par
                                #  `decision_packet.build`, une preuve absente
                                #  bloque, et c'est le comportement voulu. La
                                #  prémisse de cette fixture étant « aucun
                                #  garde-fou bloquant », les deux preuves sont
                                #  déclarées explicitement PASSANTES ; le
                                #  témoin négatif du cas contraire vit dans
                                #  tests/test_desk_positions_une_seule_autorite.py.
                                'data_quality': {'overall': 'RECENT',
                                                 'actionable_allowed': True},
                                'reconciliation': {'available': True,
                                                   'actionable_allowed': True},}}}


def test_le_verdict_dune_position_ne_repose_plus_sur_un_catalyseur_note_60():
    """CONSTAT 41 — le premier site (decision_packet) était corrigé, celui-ci non.

    MESURE par `recalculate_all` (AAPL 10 titres à 200 $, stop 190, cible 300,
    cote 210 ; scan sub.fundamental 72, score 72, rs 72, rr 4.5, earnings_dte 20,
    régime TREND, AUCUN garde-fou bloquant) : la constante
    `60 if earnings_dte is not None else None` donnait une conviction de
    (72 + 72 + 72 + 60) / 4 = 69,0 → `decision: ATTENDRE`. Sans elle, la
    conviction est celle des trois notes RÉELLEMENT mesurées, 72,0 →
    `decision: RENFORCER`. Un chiffre qui ne mesurait rien — J-400, J+20 et
    J+9999 rendaient le même 60 — retournait donc un verdict de position, et
    retirait 'catalysts' des inconnues du dossier.

    Troisième tour : la fixture parle désormais la forme RÉELLE du scan (voir
    `_scan_sans_garde_fou`). Sur cette forme, le recalculateur au SHA de
    baseline rendait `decision: ATTENDRE` et
    `decision_blocking: ['REGIME_BLOCKS_NEW_RISK']` — le catalyseur n'était plus
    le seul défaut, le fondamental et le régime l'étaient aussi.
    """
    from vertex.positions import recalculator
    from vertex.strategy import decision_packet
    out = recalculator.recalculate_all(_scan_sans_garde_fou(), _desk_une_action())
    p = out['positions'][0]
    assert p['decision_blocking'] == []            # le verdict n'est pas plafonné
    assert p['decision'] == 'RENFORCER'            # valait ATTENDRE avec le 60
    #  Un seul propriétaire de la notion « catalyseur » : le bloc canonique,
    #  lu par son nom PUBLIC (`read_catalysts`), jamais par son symbole privé.
    bloc = decision_packet.read_catalysts({'earnings_dte': 20})
    assert bloc['score'] is None and bloc['earnings_dte'] == 20


def test_le_recalculateur_ne_reintroduit_pas_la_constante_de_catalyseur():
    """Garde-fou source : la constante magique ne doit pas revenir par copie.

    Troisième tour — deux cibles ajoutées, chacune adossée à une mesure :
    `_dp._catalysts` (symbole PRIVÉ d'un autre paquet, importé dans un
    `try/except Exception` : un renommage chez son propriétaire ne casserait
    rien à l'import, il éteindrait silencieusement TOUTES les décisions du
    portefeuille) et `st_fund`/`fund_score`, les deux clés sans producteur.
    """
    import ast
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'vertex/positions/recalculator.py'), encoding='utf-8').read()
    assert "'score': 60" not in src
    #  Troisième tour : le desk ne compose plus le paquet du tout — il appelle
    #  `decision_packet.build`, qui lit catalyseurs, fondamental, régime et les
    #  TROIS preuves critiques chez leur unique propriétaire. Épingler
    #  `_dp.read_catalysts(d)` figerait une étape intermédiaire déjà dépassée ;
    #  ce qui doit rester vrai, c'est qu'aucun second constructeur ne renaisse.
    assert '_dp.build(' in src                     # un seul constructeur de paquet
    #  Mesuré sur l'ARBRE, pas sur le texte : le module EXPLIQUE en commentaire
    #  le paquet qu'il ne compose plus, en citant ses clés. Un gardien qui lit
    #  la prose accuserait sa propre documentation.
    arbre = ast.parse(src)
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Dict):
            continue
        cles = {c.value for c in noeud.keys
                if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        interdites = cles & {'reconciliation', 'data_quality', 'catalysts', 'fundamental'}
        assert not interdites, (
            'recalculator compose de nouveau %s : ces sections appartiennent à '
            'decision_packet.build, sinon deux autorités de décision'
            % sorted(interdites))
    #  `read_fundamental` n'est plus appelé ici non plus : `build` le fait, chez
    #  le propriétaire. Ce qui doit rester vrai est vérifié plus bas — aucune
    #  clé morte lue, aucun symbole privé importé.
    #  Le CODE seul : les commentaires de ce module CITENT les formes fautives
    #  pour en garder la mesure. Un garde lexical qui les compte se déclencherait
    #  sur sa propre documentation, et la seule façon de le faire taire serait
    #  d'effacer la mesure. `ast.unparse` rend le code SANS commentaires — les
    #  littéraux de chaîne, eux, sont conservés : c'est justement dans un
    #  `d.get('st_fund')` que le défaut se cache.
    code = ast.unparse(ast.parse(src))
    assert '_dp._catalysts' not in code            # par son nom PUBLIC, pas le privé
    for morte in ('st_fund', 'fund_score', 'st_timing'):
        assert "'%s'" % morte not in code, (
            '%s est une clé SANS producteur sur le detail du scan : la lire '
            'fabrique une inconnue à partir d’une mesure existante' % morte)


def test_risk_engine_does_not_coerce_missing_greeks_to_zero():
    """Garde-fou source : l'agrégat Greeks du risk_engine ne doit plus utiliser
    `g.get('delta') or 0` (qui transformait un Greek absent en 0)."""
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'vertex/portfolio/risk_engine.py'), encoding='utf-8').read()
    assert "g.get('delta') or 0" not in src
    assert 'greeks_partial' in src  # l'agrégat signale désormais l'incomplétude
