# -*- coding: utf-8 -*-
"""tests/test_news_attribution.py — le ticker d'un article est une PROVENANCE.

MESURE DU 2026-09-06, sur les 45 items servis par `/news-feed` (source `web`,
donc 100 % de repli Google News) : **22 titres sur 45** ne nommaient ni le
ticker ni la société du fil auquel ils étaient attribués. Cas non ambigus
relevés : `[AMZN] Costco silently kills member perk`,
`[NVDA] Where Will Shopify Stock Be in 5 Years?`,
`[META] 'AI Laggard' Apple Is Sitting Pretty…` — ce dernier nommant
explicitement un AUTRE ticker.

Conséquence chiffrée : la route servait `sentiment['NVDA'] = {'n': 4,
'score': 0.5}`, un sentiment haussier bâti sur Snowflake, le pétrole, GitLab
et Shopify — aucune actualité Nvidia dedans.

Ce que ce banc épingle, côté sortie servie : chaque item porte son `sym_role`,
la route dit sur quoi son agrégat de provenance est bâti, et l'agrégat par
SUJET CONFIRMÉ est servi sans jamais fabriquer d'entrée pour un ticker dont
aucun article n'est établi. Aucun réseau.
"""
from flask import Flask

from vertex.app import state
from vertex.app.routes import content


#: Les items réellement servis au moment de la mesure (titres exacts).
_ITEMS = [
    {'sym': 'NVDA', 'title': 'Where Will Shopify Stock Be in 5 Years?', 'senti': 1},
    {'sym': 'NVDA', 'title': 'Should You Buy Snowflake Stock After Its Recent Surge?', 'senti': 1},
    {'sym': 'NVDA', 'title': 'Oil Surged, Then Slumped, Year to Date in 2026.', 'senti': 1},
    {'sym': 'NVDA', 'title': 'GitLab Is Starting to Prove the Bears Wrong', 'senti': 0},
    {'sym': 'AMZN', 'title': 'Costco silently kills member perk', 'senti': 1},
    {'sym': 'AAPL', 'title': 'Apple lifts guidance', 'senti': 1},
]


def _client():
    app = Flask(__name__)
    app.register_blueprint(content.bp)
    return app.test_client()


def _feed(chemin='/news-feed'):
    sauve = dict(state.news_state)
    try:
        state.news_state['items'] = [dict(i) for i in _ITEMS]
        return _client().get(chemin).get_json()
    finally:
        state.news_state.clear()
        state.news_state.update(sauve)


def test_chaque_item_servi_porte_son_role_sujet_ou_fil():
    j = _feed()
    roles = [(i['sym'], i['sym_role']) for i in j['items']]
    assert roles == [('NVDA', 'fil'), ('NVDA', 'fil'), ('NVDA', 'fil'),
                     ('NVDA', 'fil'), ('AMZN', 'fil'), ('AAPL', 'sujet')]
    assert len(j['items']) == len(_ITEMS), 'aucune information réelle n’est retirée'


def test_l_agregat_par_sujet_ne_fabrique_aucun_score_de_ticker():
    """Le « NVDA +0,5 sur n=4 » mesuré n'a aucun article NVDA derrière lui :
    il disparaît de l'agrégat par sujet au lieu d'y valoir 0,0."""
    j = _feed()
    assert j['sentiment']['NVDA'] == {'score': 0.75, 'n': 4}, 'agrégat de provenance'
    assert j['sentiment_base'].startswith('fil interrogé'), 'sa base est DITE'
    assert j['sentiment_sujets'] == {'AAPL': {'score': 1.0, 'n': 1}}
    assert 'NVDA' not in j['sentiment_sujets'] and 'AMZN' not in j['sentiment_sujets']


def test_la_recherche_par_ticker_dit_combien_de_sujets_sont_etablis():
    """`?sym=NVDA` rendait 4 articles dont aucun sur Nvidia, sans rien en
    dire. Les items restent servis — ils sont de l'information réelle — mais
    la réponse compte désormais ce qui est établi et ce qui ne l'est pas."""
    j = _feed('/news-feed?sym=NVDA')
    assert j['filtered'] is True and len(j['items']) == 4
    assert j['filtre_sym'] == {'sym': 'NVDA', 'base': 'fil interrogé',
                               'sujets_confirmes': 0, 'sujet_non_etabli': 4}
    assert _feed()['filtre_sym'] is None, 'sans filtre, pas de bloc de filtre'


def test_un_ticker_mot_courant_n_entre_pas_dans_l_agregat_par_sujet():
    """MESURE DU 2026-09-06 — la chaîne complète fabriquait encore un score.

    Les tickers d'une ou deux lettres et les mots anglais courants sont dans
    l'univers scanné (17 sur 517 : A, ALL, ARE, CAT, COST, DD, FAST, HAS, IT,
    KEY, KO, LOW, NOW, ON, SO, T, WELL) et donc éligibles aux 6 titres chauds
    injectés dans la boucle. Le juge comparant après abaissement de casse,
    `/news-feed` servait `sentiment_sujets = {'T': {'score': 1.0, 'n': 1}}` sur
    « Bill Gates Says He Still Won't Invest in Crypto » — exactement le score de
    ticker fabriqué que ce lot supprime. La provenance, elle, reste servie : rien
    n'est retiré du fil.
    """
    sauve = dict(state.news_state)
    try:
        state.news_state['items'] = [
            {'sym': 'T', 'title': "Bill Gates Says He Still Won't Invest in Crypto",
             'senti': 1},
            {'sym': 'ON', 'title': 'Fed Holds Rates Steady on Inflation Concerns',
             'senti': 1},
        ]
        j = _client().get('/news-feed').get_json()
    finally:
        state.news_state.clear()
        state.news_state.update(sauve)
    assert [i['sym_role'] for i in j['items']] == ['fil', 'fil']
    assert j['sentiment_sujets'] == {}, 'aucun sujet établi → aucune ligne'
    assert set(j['sentiment']) == {'T', 'ON'}, 'la provenance reste servie et nommée'
    assert len(j['items']) == 2, 'aucune information réelle n’est retirée'


def test_la_reponse_declare_l_etat_des_canaux_de_preuve_de_sujet():
    """Une table par sujet peu peuplée a deux explications possibles : peu de
    titres nomment leur sujet, OU un canal de preuve est éteint. La réponse
    déclare donc l'état des trois canaux.

    MISE À JOUR DU 2026-09-06 — `attestation_vendeur` était déclarée
    `NON_IMPLÉMENTÉ`, et c'était VRAI : aucun producteur ne posait
    `sym_atteste`. Le seul producteur du fil — `terminal.py::_news_loop` — le
    pose désormais sur la branche COURTIER (`ibkr_news.depeches_lot`, qui
    interroge `reqHistoricalNews` sur le `conId` qualifié : c'est IBKR qui
    rattache la dépêche au contrat). Le canal est donc `ACTIF`, et le gardien
    de `news_plus` DÉRIVE cette valeur du balayage des producteurs — terminal.py
    inclus, alors qu'il vivait hors du glob `vertex/**` et que le canal pouvait
    devenir vivant sans que rien ne tombe.

    Ce que « ACTIF » ne dit PAS, et ne doit pas laisser croire : la fixture de
    ce banc est un fil 100 % repli web, sans une seule dépêche attestée — le
    canal existe, il ne s'allume que sur les dépêches du courtier. Les six
    items restent donc jugés au ticker et au nom, comme au-dessus.
    """
    j = _feed()
    assert j['sujet_preuves'] == {'attestation_vendeur': 'ACTIF',
                                  'ticker_ecrit_en_majuscules': 'ACTIF',
                                  'nom_de_societe': 'ACTIF'}
    #  Aucun item de cette fixture n'est attesté : la déclaration porte sur le
    #  CANAL, jamais sur un item.
    assert all('sym_atteste' not in i for i in j['items'])
    assert [i['sym_role'] for i in j['items']][-1] == 'sujet', (
        'le jugement au nom de société reste le seul en jeu ici')
