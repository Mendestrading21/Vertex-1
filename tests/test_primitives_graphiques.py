# -*- coding: utf-8 -*-
"""Aucune page n'appelle une primitive de graphique qui n'existe pas.

Mesure du 2026-09-06, audit navigateur : `/system?view=data` levait
`TypeError: VXCharts.donutCard is not a function` — une carte entière perdue,
sans que rien à l'écran ne dise pourquoi. La page charge pourtant
`donut-chart.js` ; la cause est la garde `whenChartsReady`, qui ne teste que
l'existence de l'ESPACE DE NOMS (`window.VXCharts && window.Chart`) et non
celle de la fonction appelée. Les modules de graphique enrichissent `VXCharts`
un par un : l'espace de noms existe dès le premier, bien avant le dernier.

Deux niveaux de garde ici :

- **certaines** : une primitive appelée alors qu'aucun module ne la définit, ou
  que son module n'est chargé ni par la page ni par la coque. C'est une erreur
  à coup sûr — tolérance zéro.
- **à risque d'ordre** : une primitive appelée sans garde qui la NOMME. C'est
  une erreur dépendante de l'ordre d'arrivée des scripts. On ne peut pas les
  fermer toutes d'un coup sans réécrire huit pages ; on fige donc le compte
  MESURÉ pour qu'il ne puisse que baisser.
"""
import os
import sys

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RACINE)

from tools.qa import primitives_manquantes as pm  # noqa: E402

#: Compte mesuré le 2026-09-06. Il descend quand une page apprend à nommer la
#: primitive qu'elle attend ; il ne remonte jamais.
_RISQUES_RECENSES = 28


def test_le_balayage_voit_bien_les_primitives_et_les_pages():
    """Une garde qui n'inspecte rien est une garde qui ment."""
    defs = pm.definitions()
    assert len(defs) > 40, 'seulement %d primitives trouvées' % len(defs)
    assert 'donutCard' in defs and 'heatmapCard' in defs, sorted(defs)[:20]
    assert len(pm._sources()) > 15


def test_la_coque_est_bien_prise_en_compte():
    """`chart-core` est chargé par la coque : l'ignorer accuserait 38 pages."""
    coque = pm.modules_de_la_coque()
    assert 'chart-core' in coque, coque


def test_aucune_primitive_appelee_sans_exister():
    r = pm.analyser()
    assert not r['certaines'], (
        'ces appels échouent à coup sûr — la carte disparaît sans explication :'
        '\n  %s' % '\n  '.join(
            '%s : %s (%s)' % (x['page'], x['primitive'], x['quoi'])
            for x in r['certaines']))


def test_le_nombre_d_appels_a_risque_d_ordre_ne_remonte_pas():
    r = pm.analyser()
    n = len(r['probables'])
    assert n <= _RISQUES_RECENSES, (
        '%d appels sans garde nommant leur primitive, %d recensés le '
        '2026-09-06 : une page a cessé de vérifier ce qu’elle attend.\n  %s'
        % (n, _RISQUES_RECENSES, '\n  '.join(
            '%s : %s (%s)' % (x['page'], x['primitive'], x.get('module'))
            for x in r['probables'][:12])))


def test_une_garde_qui_nomme_la_primitive_est_reconnue():
    """Contre-épreuve : la mesure doit distinguer les deux formes de garde."""
    bonne = "if(window.VXCharts&&VXCharts.donutCard){VXCharts.donutCard('x',{});}"
    mauvaise = "if(window.VXCharts&&window.Chart){VXCharts.donutCard('x',{});}"
    assert pm._garde_nomme(bonne, 'donutCard') is True
    assert pm._garde_nomme(mauvaise, 'donutCard') is False
