# -*- coding: utf-8 -*-
"""Le doublon RETENU est le plus récent, quelle que soit la FORME de sa date.

Mesure du 2026-09-06 (contrôle adverse) : la déduplication départageait deux
dépêches racontant le même événement en comparant `ev['time']` en CHAÎNE BRUTE.
Or ce champ arrive sous au moins trois formes selon la branche productrice :

- courtier : ``2026-09-05 08:00:00+00:00`` (espace)
- ISO      : ``2026-09-05T07:00:00Z``      (``T``)
- RSS      : ``Sat, 06 Sep 2026 07:00:00 GMT`` (RFC 2822, commence par une lettre)

Une comparaison lexicographique classe donc par forme avant de classer par
date : le ``T`` (0x54) bat l'espace (0x20) dès le 11ᵉ caractère, et une lettre
bat tout. L'événement fusionné héritait de la source, de la date, du lien et du
sentiment du plus ANCIEN.

Aucun réseau : dépêches synthétiques, comparaison des deux ordres d'arrivée.
"""
from vertex.market import news_dedup


def _depeche(source, time, titre='Nvidia beats estimates', **extra):
    d = {'title': titre, 'source': source, 'time': time,
         'link': 'https://exemple.test/%s' % source.lower()}
    d.update(extra)
    return d


def _retenu(a, b):
    """Source retenue, mesurée dans les DEUX ordres d'arrivée.

    Un départage correct ne doit pas dépendre de l'ordre : si les deux ordres
    ne donnent pas la même réponse, c'est le premier arrivé qui gagne, pas le
    plus récent.
    """
    un = news_dedup.deduplicate([dict(a), dict(b)])
    deux = news_dedup.deduplicate([dict(b), dict(a)])
    assert len(un) == 1 and len(deux) == 1, 'les deux titres devaient fusionner'
    assert un[0]['source'] == deux[0]['source'], (
        'le départage dépend de l’ordre d’arrivée : %r puis %r'
        % (un[0]['source'], deux[0]['source']))
    return un[0]


def test_le_courtier_plus_recent_bat_l_ISO_plus_ancien():
    """Le cas EXACT que le correctif d'horodatage du tour 3 avait retourné."""
    ev = _retenu(_depeche('IBKR', '2026-09-05 08:00:00+00:00'),
                 _depeche('Reuters', '2026-09-05T07:00:00Z'))
    assert ev['source'] == 'IBKR', (
        'à date égale, la forme ISO gagnait sur la forme du courtier : '
        'un tri par apparence, pas par heure')
    assert news_dedup.instant(ev) == '2026-09-05T08:00Z'


def test_l_ISO_plus_recent_bat_le_courtier_plus_ancien():
    """Contre-épreuve : le correctif ne doit pas simplement inverser le biais."""
    ev = _retenu(_depeche('IBKR', '2026-09-05 06:00:00+00:00'),
                 _depeche('Reuters', '2026-09-05T07:00:00Z'))
    assert ev['source'] == 'Reuters'


def test_le_RFC_2822_ne_domine_plus_toute_date():
    """Défaut PRÉEXISTANT : un `pubDate` RSS commence par une lettre."""
    ev = _retenu(_depeche('RSS', 'Sat, 06 Sep 2026 07:00:00 GMT'),
                 _depeche('IBKR', '2026-09-06 09:00:00+00:00'))
    assert ev['source'] == 'IBKR', (
        'une date RFC 2822 gagnait contre toute date ISO, quelle qu’elle soit')


def test_published_at_deja_normalise_fait_autorite():
    """Le producteur pose déjà l'instant normalisé : on ne le recalcule pas."""
    ev = _depeche('IBKR', 'illisible', published_at='2026-09-05T08:00Z')
    assert news_dedup.instant(ev) == '2026-09-05T08:00Z'


def test_une_date_illisible_ne_gagne_jamais_contre_une_date_lisible():
    ev = _retenu(_depeche('IBKR', ''), _depeche('Reuters', '2026-09-05T07:00:00Z'))
    assert ev['source'] == 'Reuters'
    assert news_dedup.instant({'time': 'pas une date'}) == ''
    assert news_dedup.instant({}) == ''


def test_la_corroboration_et_les_sources_restent_comptees():
    """Anti-régression : le départage ne doit rien casser de la fusion."""
    ev = _retenu(_depeche('IBKR', '2026-09-05 08:00:00+00:00'),
                 _depeche('Reuters', '2026-09-05T07:00:00Z'))
    assert ev['corroborations'] == 2
    assert ev['also_from'], 'la seconde source doit rester nommée'


def test_le_tri_final_du_fil_utilise_la_meme_cle():
    """Deux clés de récence différentes seraient deux autorités."""
    import inspect

    from vertex.market import news_pipeline
    src = inspect.getsource(news_pipeline)
    assert "e.get('time') or ''" not in src, (
        'le tri final compare de nouveau `time` brut : il classerait par forme '
        'de date, comme la déduplication le faisait')
    assert '_instant(e)' in src
