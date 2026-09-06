# -*- coding: utf-8 -*-
"""RACINE du constat 9 : l'horodatage des dépêches produit par
`vertex/options/legacy_engine.news_for`.

Ce module est le PRODUCTEUR du champ `time` de chaque dépêche du fil (branche
de repli web, `terminal.py:1769`). Toute la chaîne en aval est correcte et
l'était déjà :

  · `news_plus.horodatage_source` sait lire `Z` et les décalages `±HH:MM` et
    les convertit en UTC (bancs : tests/test_actualites_horodatees.py) ;
  · `VX.fmt.instantSource` (vx-core.js) convertit dans le fuseau du LECTEUR
    quand la source déclare le sien, et marque « fuseau n/d » sinon.

Le producteur, lui, tronquait : `str(t)[:16].replace('T', ' ')`. Mesure du
2026-09-06 sur le fil servi — **45 items sur 45 arrivaient sans fuseau alors
que la source en portait un**, et l'écran devait écrire
« 04/09/2026 23:42 (fuseau n/d) » là où il pouvait dire « Il y a 12 min ».

Trois lots successifs ont documenté ce défaut en le déclarant hors périmètre
(« la racine reste à faire par le lot propriétaire ») ; ce banc épingle la
racine, pas la conséquence.
"""
from vertex.options import legacy_engine as le
from vertex.services import news_plus as np_


class _Ticker(object):
    """Le seul contrat que `news_for` lit sur un ticker yfinance."""

    def __init__(self, items):
        self.news = items


def _nouveau(pub_date, **extra):
    """Format IMBRIQUÉ actuel de yfinance (`content.pubDate`, ISO + `Z`)."""
    c = {'title': 'Titre', 'provider': {'displayName': 'Reuters'},
         'pubDate': pub_date, 'canonicalUrl': {'url': 'https://exemple/1'}}
    c.update(extra)
    return {'content': c}


def _plat(epoque):
    """Ancien format PLAT (`providerPublishTime`, entier d'époque UNIX)."""
    return {'title': 'Titre plat', 'publisher': 'AP',
            'providerPublishTime': epoque, 'link': 'https://exemple/2'}


def test_le_fuseau_declare_par_la_source_survit_a_la_production():
    """`str(t)[:16]` coupait le 20e caractère : le `Z` de yfinance mourait ICI.

    Mesure comparée sur la MÊME entrée `'2026-09-04T23:42:00Z'` :
      AVANT  time '2026-09-04 23:42'  → published_at '2026-09-04T23:42'  (nu)
      APRÈS  time '2026-09-04T23:42:00Z' → published_at '2026-09-04T23:42Z'
    """
    it = le.news_for(_Ticker([_nouveau('2026-09-04T23:42:00Z')]))[0]
    assert it['time'] == '2026-09-04T23:42:00Z'
    assert np_.horodatage_source(it['time']) == '2026-09-04T23:42Z'
    #  Contre-épreuve de la troncature : elle détruisait bien le fuseau.
    tronque = str('2026-09-04T23:42:00Z')[:16].replace('T', ' ')
    assert np_.horodatage_source(tronque) == '2026-09-04T23:42'


def test_un_decalage_declare_est_converti_au_lieu_d_etre_servi_comme_heure_locale():
    """Le cas le PLUS faux de la troncature : une source déclarant `+02:00`
    voyait son heure locale servie NUE, donc lue comme si aucun fuseau n'avait
    été déclaré — un décalage de deux heures, silencieux.

    AVANT '2026-09-04T23:42' (nu, faux de 2 h) · APRÈS '2026-09-04T21:42Z'."""
    it = le.news_for(_Ticker([_nouveau('2026-09-04T23:42:00+02:00')]))[0]
    assert np_.horodatage_source(it['time']) == '2026-09-04T21:42Z'


def test_l_epoque_unix_de_l_ancien_format_n_est_plus_reduite_en_chaine_illisible():
    """`providerPublishTime` est un ENTIER de secondes UNIX ; `str(...)[:16]`
    en faisait `'1788000000'`, illisible pour toute la chaîne aval — donc
    `published_at: None`, une ABSENCE là où la source avait donné une date.

    La conversion est une lecture d'UNITÉ, pas une estimation : l'époque UNIX
    est définie en UTC, le `Z` est porté par la conversion, pas supposé."""
    assert np_.horodatage_source(str(1788000000)[:16]) is None      # le défaut
    it = le.news_for(_Ticker([_plat(1788000000)]))[0]
    assert it['time'].endswith('Z')
    assert np_.horodatage_source(it['time']) == '2026-08-29T10:40Z'


def test_l_absence_d_horodatage_reste_une_absence_et_non_une_epoque_zero():
    """Rien n'est fabriqué : sans date, `time` reste vide et `published_at`
    None. Un booléen n'est pas une époque, et une époque hors domaine reste
    une absence — sinon `datetime.fromtimestamp` peindrait le 1er janvier 1970
    ou lèverait dans la boucle de collecte."""
    sans = le.news_for(_Ticker([_nouveau(None)]))[0]
    assert sans['time'] == ''
    assert np_.horodatage_source(sans['time']) is None
    assert le._horodatage_depeche(True) == ''       # un booléen n'est pas une date
    assert le._horodatage_depeche(1e30) == ''       # hors domaine : absence, pas 1970
    assert le._horodatage_depeche(None) == ''


def test_le_producteur_ne_tronque_plus_du_tout():
    """Garde de forme : la troncature est la CAUSE, elle ne doit pas revenir
    par un autre chemin (un `[:19]`, un `[:16]` déplacé). On lit le corps de
    `news_for`, pas le fichier entier — les commentaires citent le défaut."""
    import inspect
    corps = inspect.getsource(le.news_for)
    assert '[:16]' not in corps
    assert '_horodatage_depeche(t)' in corps
