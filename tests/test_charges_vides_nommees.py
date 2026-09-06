# -*- coding: utf-8 -*-
"""Une charge vide dit POURQUOI elle est vide.

Mesure du 2026-09-06, en exerçant les 184 règles du runtime : cinq routes
rendaient `{}` ou `[]` sans une seule clé disant pourquoi — `/api/comite`,
`/api/portefeuille`, `/api/search`, `/api/strategie`, `/api/weekly`. Un
appelant ne pouvait pas distinguer « rien à signaler » de « le calcul n'a pas
tourné », alors que l'invariant 5 sépare précisément ces deux états.

Aucune de ces routes n'a de consommateur dans le dépôt (relevé .py/.js) : elles
servent un humain ou un script externe, c'est-à-dire exactement le lecteur qui
n'a aucun moyen de deviner. La forme NON vide est inchangée ; seul le cas vide
gagne un motif.

Aucun réseau : client de test, état de scan vide.
"""
import pytest


@pytest.fixture(scope='module')
def client():
    import os
    os.environ['VERTEX_CODE'] = ''
    os.environ.setdefault('NO_IBKR', '1')
    os.environ.setdefault('DEMO', '0')
    from vertex.runtime import app
    app.config['TESTING'] = True
    return app.test_client()


_ROUTES = ('/api/comite', '/api/portefeuille', '/api/strategie', '/api/weekly')
#: Les clés qui NOMMENT un état, quelle que soit la route.
_NOMMANTES = ('motif', 'disponible', 'error', 'usage', 'read_only')


@pytest.mark.parametrize('chemin', _ROUTES + ('/api/search',))
def test_la_charge_repond_et_nomme_son_etat(client, chemin):
    r = client.get(chemin)
    assert r.status_code == 200, chemin
    charge = r.get_json()
    assert isinstance(charge, (dict, list)), (chemin, type(charge))
    if isinstance(charge, list):
        #  Une liste NON vide est la forme historique et reste admise.
        assert charge, (
            '%s rend une liste vide sans pouvoir dire pourquoi : une liste ne '
            'peut pas porter de motif, la route doit rendre un objet' % chemin)
        return
    if charge and not any(k in charge for k in _NOMMANTES):
        return          # charge pleine : elle se suffit
    assert any(k in charge for k in _NOMMANTES), (
        '%s rend une charge vide sans clé qui nomme l’absence : le lecteur ne '
        'peut pas distinguer « rien à signaler » de « le calcul n’a pas '
        'tourné » — %r' % (chemin, charge))


@pytest.mark.parametrize('chemin', _ROUTES)
def test_le_motif_est_une_phrase_utile_pas_un_code(client, chemin):
    charge = client.get(chemin).get_json()
    if not isinstance(charge, dict) or charge.get('disponible') is not False:
        pytest.skip('%s sert une charge pleine sur cette instance' % chemin)
    motif = charge.get('motif') or ''
    assert len(motif) > 30, (chemin, motif)
    assert ' ' in motif and motif.lower() != motif.upper(), (
        '%s rend un code plutôt qu’une phrase : %r' % (chemin, motif))


def test_la_recherche_sans_terme_explique_son_usage(client):
    """Le cas le plus fréquent d'appel à la main : sans paramètre."""
    charge = client.get('/api/search').get_json()
    assert isinstance(charge, dict)
    assert 'q=' in (charge.get('usage') or ''), charge
    assert charge.get('resultats') == []


def test_la_recherche_sans_resultat_dit_sur_quoi_elle_a_cherche(client):
    charge = client.get('/api/search?q=ZZZZQQ').get_json()
    assert isinstance(charge, dict), charge
    assert charge.get('resultats') == []
    assert 'ZZZZQQ' in (charge.get('motif') or ''), charge
    assert isinstance(charge.get('univers'), int), charge


def test_une_PANNE_du_portefeuille_ne_se_lit_pas_comme_une_absence(client):
    """Les deux états emploient des clés DIFFÉRENTES, exprès."""
    import inspect

    from vertex.app.routes import command
    src = inspect.getsource(command.api_portefeuille)
    assert "'error': 'portfolio_analysis_unavailable'" in src
    assert "'disponible': False" in src
    #  La branche de panne ne doit pas emprunter le vocabulaire de l'absence.
    #  On part du DERNIER `except` : le premier protège la lecture du capital,
    #  et la tranche partirait d'avant la branche d'absence.
    panne = src[src.rindex('except Exception'):]
    assert "'disponible'" not in panne, (
        'la panne se déclare disponible=False comme une absence : les deux '
        'états redeviennent indiscernables')
