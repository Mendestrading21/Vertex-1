# -*- coding: utf-8 -*-
"""Le Brief quotidien ne DIAGNOSTIQUE pas ce qu'il n'a pas mesuré.

MESURE DU 2026-09-06 — `vertex/market/daily_brief.py:109` servait, dès qu'aucun
événement ne sortait du pipeline :

    « Flux d'actualités hors ligne dans cet environnement — aucun événement
      affiché plutôt qu'un événement inventé. »

La seconde moitié est juste ; la première est une CAUSE que ce module ne
mesure nulle part. `build_daily_brief` reçoit un `news_state` déjà collecté et
compte ce qui en sort : il ne connaît ni la connectivité, ni l'état des
sources, ni même si la boucle de collecte tourne. La phrase fondait donc trois
états que l'invariant 5 exige de garder distincts :

* le fil n'a pas été transmis (`news_state=None`) ;
* le fil est transmis et VIDE (0 dépêche reçue) ;
* des dépêches sont arrivées et le pipeline les a TOUTES écartées faute de
  titre, de publieur ou de date — un défaut de collecte, pas une absence
  d'actualité, et le seul des trois qui désigne quelque chose à réparer.

Ces bancs figent les trois textes et interdisent le retour de la cause
inventée. Aucun réseau : les états sont construits à la main.
"""
from vertex.market.daily_brief import build_daily_brief

_SCAN = {'source': 'demo'}


def _dominante(news_state):
    b = build_daily_brief(_SCAN, news_state, [])
    return next(s for s in b['sections'] if s['label'] == 'Actualité dominante')['text']


def test_le_fil_non_transmis_est_dit_comme_tel():
    txt = _dominante(None)
    assert 'non transmis' in txt
    assert 'aucun événement affiché plutôt qu’un événement inventé' in txt


def test_le_fil_vide_est_distinct_du_fil_non_transmis():
    txt = _dominante({'items': []})
    assert 'transmis mais vide' in txt and '0 dépêche reçue' in txt
    assert txt != _dominante(None), (
        '« pas de fil » et « fil vide » sont deux états différents')


def test_des_depeches_toutes_ecartees_nomment_la_cause_REELLE():
    """Trois dépêches reçues, trois rejetées : ce n'est pas une absence
    d'actualité, c'est un défaut de collecte — et `collect()` sait dire
    laquelle des trois conditions manque."""
    etat = {'items': [{'title': 'Sans publieur ni date'},
                      {'title': '', 'publisher': 'Reuters', 'time': 't'},
                      'pas-un-dict']}
    txt = _dominante(etat)
    assert '3 dépêches reçues' in txt
    assert 'toutes écartées faute de titre, de publieur ou de date' in txt
    #  Le détail par cause vient du pipeline, jamais d'une supposition — et un
    #  item peut manquer PLUSIEURS conditions (le premier n'a ni publieur ni
    #  date), d'où une somme par cause supérieure au nombre d'items.
    assert ('(date absente : 1, non dict : 1, publieur absent : 1, '
            'titre absent : 1)') in txt, txt


def test_aucune_cause_de_connexion_n_est_affirmee_nulle_part():
    """L'anti-régression, sur les TROIS états et sur le texte complet du brief
    (le brief concatène ses sections : la phrase repartait aussi dans `text`)."""
    for etat in (None, {'items': []}, {'items': [{'title': 'x'}]}):
        b = build_daily_brief(_SCAN, etat, [])
        entier = b['text'] + ' ' + ' '.join(b['compact'])
        assert 'hors ligne' not in entier, entier
        assert 'dans cet environnement' not in entier


def test_un_evenement_reel_reste_l_actualite_dominante():
    """Le correctif ne touche QUE la branche vide : une dépêche valide reste
    servie, avec sa source, comme avant."""
    etat = {'items': [{'title': 'Fed cuts rates', 'publisher': 'Reuters',
                       'time': '2026-09-05T10:00', 'senti': 1}]}
    txt = _dominante(etat)
    assert 'Fed cuts rates' in txt and 'Reuters' in txt
