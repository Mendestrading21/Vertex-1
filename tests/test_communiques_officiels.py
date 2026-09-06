# -*- coding: utf-8 -*-
"""P5 — communiqués officiels BCE et BNS (fixtures RSS RÉELLES capturées le
2026-09-06 : `bce_press.xml`, `bns_adhoc.xml`). Aucun réseau ici ; la collecte
réelle est couverte par `VERTEX_TEST_RESEAU=1` dans test_macro_officiel.
"""
import os
from pathlib import Path

from vertex.data_sources import macro_officiel as src

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests' / 'fixtures' / 'macro_officiel'


def test_parser_bce_rend_des_communiques_dates_et_assainis():
    out = src.parser_communiques((FIX / 'bce_press.xml').read_text(encoding='utf-8'), 'BCE')
    assert 5 <= len(out) <= src.COMMUNIQUES_PAR_SOURCE
    c = out[0]
    assert c['source'] == 'BCE' and c['link'].startswith('https://') and c['title']
    assert c['published_at'] and c['published_at'].endswith('Z')      # RFC 2822 +0200 → UTC
    assert '<' not in c['title'] and c['received_at'].endswith('Z')


def test_parser_bns_rend_des_communiques_dates_par_dc_date():
    """MESURE (2026-09-06) : le flux ad hoc de la BNS n'émet AUCUN `pubDate`
    (0 occurrence sur 15 379 octets) mais 36 `<dc:date>`. Le parseur ne lisant
    que `pubDate`, `published_at` valait None sur **12 communiqués sur 12** —
    100 % d'un fournisseur officiel — alors que `_items_surs` avait déjà la
    valeur en mémoire sous la clé `date` (namespace retiré) et que
    `horodatage_source` la lisait sans rien inventer.

    Ce test épingle l'assertion qui manquait ici : le jumeau BCE exigeait déjà
    `c['published_at']`, ce cas-ci n'exigeait que source et lien — le trou
    d'assertion était exactement à l'endroit du défaut.
    """
    brut = (FIX / 'bns_adhoc.xml').read_text(encoding='utf-8')
    assert '<pubDate' not in brut and '<dc:date' in brut, 'fixture = capture fidèle du flux réel'
    out = src.parser_communiques(brut, 'BNS')
    assert out and all(c['source'] == 'BNS' and c['link'].startswith('https://') for c in out)
    assert all(c['published_at'] for c in out), 'dc:date lu : plus de fausse absence de date'
    #  Le premier item du flux est daté 2026-09-02T10:15:00Z par la source.
    assert out[0]['published_at'] == '2026-09-02T10:15Z'


def test_la_date_bns_vient_du_flux_jamais_du_titre():
    """Le titre BNS commence par une date en clair (« 2026-09-02 - Federal
    Council… ») : on ne l'extrait PAS. Une chaîne d'affichage n'est pas un
    horodatage déclaré. Sans `dc:date`, l'absence reste une absence."""
    sans_date = ('<?xml version="1.0"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/">'
                 '<channel><item><title>2026-09-02 - Federal Council appoints X</title>'
                 '<link>https://www.snb.ch/x</link></item></channel></rss>')
    out = src.parser_communiques(sans_date, 'BNS')
    assert out and out[0]['published_at'] is None
    assert out[0]['title'].startswith('2026-09-02 -'), 'le titre est servi tel quel'


def test_le_tri_replace_le_communique_bns_a_son_rang_reel():
    """MESURE : avec `published_at` perdu, la clé de tri `published_at or ''`
    reléguait les 12 BNS derrière les 12 BCE. Le communiqué suisse du
    2026-09-02 — 2e plus récent des 24 — tombait en **13e position**, sous
    10 communiqués BCE plus anciens, et 8 communiqués sortaient des 16 rendus
    par la carte. Date lue : il remonte au rang 2."""
    def fetch(url, accept):
        return (FIX / ('bns_adhoc.xml' if 'snb.ch' in url else 'bce_press.xml')).read_text(encoding='utf-8')
    liste, erreurs = src.collecter_communiques(fetch)
    assert erreurs == {} and len(liste) == 24
    assert sum(1 for c in liste if not c['published_at']) == 0
    rang = next(i for i, c in enumerate(liste) if c['source'] == 'BNS')
    assert rang == 1, 'le BNS du 2026-09-02 est le 2e plus récent des 24'
    dates = [c['published_at'] for c in liste]
    assert dates == sorted(dates, reverse=True)


def test_collecte_deduplique_trie_et_isole_les_pannes():
    def fetch(url, accept):
        if 'snb.ch' in url:
            raise OSError('flux BNS injoignable')
        return (FIX / 'bce_press.xml').read_text(encoding='utf-8')
    liste, erreurs = src.collecter_communiques(fetch)
    assert liste and all(c['source'] == 'BCE' for c in liste)
    assert 'BNS' in erreurs and 'OSError' in erreurs['BNS']
    dates = [c['published_at'] or '' for c in liste]
    assert dates == sorted(dates, reverse=True)
    assert len({c['link'] for c in liste}) == len(liste)


def test_un_flux_hostile_est_refuse_et_devient_une_erreur_de_source():
    """DOCTYPE/entités refusés par le parseur durci : le parseur lève, la
    collecte enregistre l'erreur pour la source et n'invente rien."""
    import pytest
    hostile = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
    with pytest.raises(Exception):
        src.parser_communiques(hostile, 'BCE')
    liste, erreurs = src.collecter_communiques(lambda url, accept: hostile)
    assert liste == [] and set(erreurs) == {'BCE', 'BNS'}


def test_l_instantane_du_service_porte_les_communiques(monkeypatch, tmp_path):
    from vertex.services import macro_officiel as svc
    monkeypatch.setattr(svc, '_racine', lambda: str(tmp_path))
    monkeypatch.setattr(svc, '_battre', lambda *a, **k: None)
    monkeypatch.setattr(svc, '_publier', lambda: None)
    from tests.test_macro_officiel import _fetch_fixtures
    snap = svc.collecter_une_fois(_fetch_fixtures)
    assert snap['communiques'] and {c['source'] for c in snap['communiques']} == {'BCE', 'BNS'}
    assert snap['communiques_erreurs'] == {}
    assert [x['source'] for x in snap['communiques_sources']] == ['BCE', 'BNS']
    # persisté et réhydraté
    svc._ETAT['communiques'] = []
    svc.charger_cache()
    assert svc.snapshot()['communiques']


def test_les_hotes_des_flux_sont_en_liste_blanche():
    from vertex.services import macro_officiel as svc
    for _s, _l, url in src.COMMUNIQUES:
        from urllib.parse import urlparse
        assert urlparse(url).hostname in svc.HOTES_AUTORISES


def test_la_carte_marches_affiche_les_communiques():
    page = (ROOT / 'vertex' / 'ui' / 'pages' / 'markets_page.py').read_text(encoding='utf-8')
    assert 'id="vx-mk-communiques"' in page and 'function paintCommuniques(' in page
    assert 'paintCommuniques(d);' in page
    assert 'le texte des communiqués n’est pas repris' in page
