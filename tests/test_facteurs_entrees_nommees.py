# -*- coding: utf-8 -*-
"""Chaque facteur d'exposition DIT quelle entrée lui manque.

Mesure du 2026-09-06 : l'unique appelant de production du modèle de facteurs
(`vertex/engines/portfolio_context.py`) construit son entrée comme
`{symbole: {'returns': [...]}}` — aucune donnée fondamentale n'est transmise.
Sur les dix facteurs, seuls MARKET, BETA, MOMENTUM et LOW_VOL peuvent donc
porter une valeur ; les six autres sont None en permanence.

L'appelant traduisait cela par une raison UNIQUE et vague : « preuve facteur
indisponible pour les positions couvertes ». Ce n'est pas faux, c'est
inexploitable — le lecteur ne peut pas distinguer une donnée absente à la
source, une donnée non demandée, et un calcul en échec.

Le modèle est le seul à savoir ce que chaque facteur exige. Il le publie donc.
"""
from vertex.research.institutional import factor_model as fm


def _rendements(n=300):
    """Série déterministe, assez longue pour MOMENTUM 12-1 et LOW_VOL."""
    return [0.004 if i % 3 else -0.003 for i in range(n)]


def test_le_recensement_des_exigences_couvre_tous_les_facteurs():
    """Une garde qui n'inspecte qu'une partie ment sur le reste."""
    rendus = set(factor for factor in fm.factor_exposures({'returns': _rendements()}))
    assert rendus == set(fm.REQUIS), (rendus ^ set(fm.REQUIS))


def test_un_facteur_sans_valeur_nomme_son_entree_manquante():
    r = fm.factor_exposures({'returns': _rendements()})
    for facteur in ('SIZE', 'VALUE', 'QUALITY', 'GROWTH', 'PROFITABILITY'):
        item = r[facteur]
        assert item['value'] is None, facteur
        assert item.get('manquant'), (facteur, item)
        assert 'entrée(s) absente(s)' in item['note'], (facteur, item['note'])
        for cle in item['manquant']:
            assert cle in item['note'], (facteur, cle)


def test_un_facteur_CALCULE_ne_porte_aucune_plainte():
    """Contre-épreuve : la garde ne doit pas bavarder quand tout va bien."""
    r = fm.factor_exposures({'returns': _rendements(), 'market_cap': 1.2e12,
                             'pe': 30.0, 'roe': 0.5, 'margin': 0.25,
                             'revenue_growth': 0.12, 'capex_to_revenue': 0.08})
    for facteur in ('SIZE', 'VALUE', 'QUALITY', 'GROWTH', 'PROFITABILITY', 'INVESTMENT'):
        item = r[facteur]
        assert item['value'] is not None, (facteur, item)
        assert 'manquant' not in item, (facteur, item)
        assert 'absente' not in item['note'], (facteur, item['note'])


def test_chaque_facteur_publie_ce_qu_il_exige():
    r = fm.factor_exposures({'returns': _rendements()})
    for facteur, item in r.items():
        assert 'requiert' in item, facteur
        assert item['requiert'] == list(fm.REQUIS[facteur]), facteur


def test_la_couverture_des_entrees_est_mesurable_sans_calculer():
    """Un appelant doit pouvoir DIRE pourquoi, sans deviner ni recalculer."""
    c = fm.couverture_entrees({'returns': _rendements()})
    assert c['entrees']['returns'] is True
    assert c['entrees']['market_cap'] is False
    assert c['facteurs_totaux'] == len(fm.REQUIS)
    #  Le cas RÉEL du produit : seules les séries sont transmises.
    assert set(c['facteurs_calculables']) == {'MARKET', 'BETA', 'MOMENTUM', 'LOW_VOL'}, (
        c['facteurs_calculables'])


def test_avec_toutes_les_entrees_tous_les_facteurs_sont_calculables():
    c = fm.couverture_entrees({'returns': _rendements(), 'market_cap': 1.0,
                               'pe': 1.0, 'pb': 1.0, 'roe': 1.0, 'margin': 1.0,
                               'revenue_growth': 1.0, 'capex_to_revenue': 1.0})
    assert len(c['facteurs_calculables']) == c['facteurs_totaux']
