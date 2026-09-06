# -*- coding: utf-8 -*-
"""Les actifs de première partie partent COMPRESSÉS sur le réseau.

Mesure du 2026-09-06 : rien ne l'était. Le filtre de `vertex/app/factory.py` ne
retenait que `application/json` et `text/html`, et sortait d'emblée sur
`resp.direct_passthrough` — qui est TOUJOURS vrai pour un fichier servi par
`send_file`, c'est-à-dire pour tout `/static/…`. Relevé sur l'instance :
`/asset/css/bundle.css` 155 ko, `vx-core.js` 49 ko, `chart-core.js` 57 ko,
aucun en-tête `Content-Encoding`.

Total première partie : **791 ko servis pour 265 ko compressés**. Les deux
tiers étaient payés à chaque chargement froid — sur un téléphone en 4G, la
différence entre une page qui s'ouvre et une page qu'on attend.

Ce banc vérifie les quatre propriétés qui rendent la compression SÛRE, parce
que la manière la plus facile de casser un site est de compresser mal : le
corps décompressé doit être identique à l'octet près, un client sans gzip doit
recevoir le clair, la réponse doit porter `Vary`, et l'étiquette d'entité ne
doit pas désigner deux corps différents.
"""
import gzip

import pytest


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    import os
    os.environ['VERTEX_CODE'] = ''
    os.environ.setdefault('NO_IBKR', '1')
    os.environ.setdefault('DEMO', '0')
    from vertex.runtime import app
    app.config['TESTING'] = True
    return app.test_client()


#: Un actif de chaque famille servie : feuille agrégée (route), script de la
#: coque et module de page (fichiers statiques en flux).
_ACTIFS = ('/asset/css/bundle.css',
           '/static/vertex/js/vx-core.js',
           '/static/vertex/js/pages/options-intel.js')


@pytest.mark.parametrize('chemin', _ACTIFS)
def test_l_actif_est_servi_compresse(client, chemin):
    r = client.get(chemin, headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200, chemin
    assert r.headers.get('Content-Encoding') == 'gzip', (
        '%s part encore en clair : les deux tiers du poids sont payés pour '
        'rien à chaque chargement froid' % chemin)


@pytest.mark.parametrize('chemin', _ACTIFS)
def test_le_corps_decompresse_est_identique_a_l_octet_pres(client, chemin):
    """La pire panne possible : un corps valide et pourtant illisible."""
    clair = client.get(chemin).get_data()
    compresse = client.get(chemin, headers={'Accept-Encoding': 'gzip'}).get_data()
    assert gzip.decompress(compresse) == clair, chemin
    assert len(compresse) < len(clair), chemin


@pytest.mark.parametrize('chemin', _ACTIFS)
def test_un_client_sans_gzip_recoit_le_clair(client, chemin):
    r = client.get(chemin)
    assert r.headers.get('Content-Encoding') is None, chemin
    assert r.get_data()[:2] != b'\x1f\x8b', chemin


@pytest.mark.parametrize('chemin', _ACTIFS)
def test_la_reponse_dit_qu_elle_varie_selon_l_encodage(client, chemin):
    """Sans `Vary`, un cache partagé sert le corps compressé à un client qui ne
    sait pas le lire."""
    r = client.get(chemin, headers={'Accept-Encoding': 'gzip'})
    assert 'Accept-Encoding' in (r.headers.get('Vary') or ''), chemin


def test_l_etiquette_d_entite_ne_designe_pas_deux_corps(client):
    """Deux corps différents sous une même étiquette, c'est un cache qui peut
    servir l'un pour l'autre. nginx suffixe depuis toujours ; on fait pareil."""
    chemin = '/static/vertex/js/vx-core.js'
    clair = client.get(chemin).headers.get('ETag')
    compresse = client.get(chemin, headers={'Accept-Encoding': 'gzip'}).headers.get('ETag')
    if not clair:
        pytest.skip('le serveur statique ne pose pas d’étiquette d’entité ici')
    assert compresse and compresse != clair, (clair, compresse)
    assert 'gzip' in compresse


def test_une_reponse_deja_compressee_n_est_pas_recompressee(client):
    """Un double gzip produit un corps que le client lit comme du binaire."""
    r = client.get('/api/system/diagnostics', headers={'Accept-Encoding': 'gzip'})
    if r.headers.get('Content-Encoding') != 'gzip':
        pytest.skip('charge trop petite pour être compressée')
    assert gzip.decompress(r.get_data())[:2] != b'\x1f\x8b'


def test_une_image_n_est_pas_recompressee_pour_rien(client):
    """Compresser du déjà-compressé coûte du processeur pour zéro octet."""
    from vertex.app import factory
    import inspect
    src = inspect.getsource(factory)
    assert 'image/svg+xml' in src, 'le SVG, lui, se compresse bien'
    assert "ct.startswith('image/png')" not in src
