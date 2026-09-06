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
