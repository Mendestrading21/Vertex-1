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


def test_parser_bns_rend_des_communiques():
    out = src.parser_communiques((FIX / 'bns_adhoc.xml').read_text(encoding='utf-8'), 'BNS')
    assert out and all(c['source'] == 'BNS' and c['link'].startswith('https://') for c in out)


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
