# -*- coding: utf-8 -*-
"""Aucun chemin n'a deux propriétaires pour une même méthode.

Deux règles Flask pour le même couple (chemin, méthode) est le défaut de
propriété le plus coûteux du produit : la seconde gagne en silence, la première
devient morte, et une correction appliquée à la mauvaise ne change rien à
l'écran — on cherche alors le défaut ailleurs pendant des heures. La doctrine
en signalait deux au SHA de baseline.

Mesure du 2026-09-06 sur 184 règles : **zéro**. Les trois cas que grouper par
chemin seul faisait remonter sont des routes REST normales — `/api/tracking` en
GET et en POST, `/api/tracking/<id>` en GET et en PATCH, `/api/client-log` en
GET et en POST : deux verbes, deux fonctions, un seul chemin. Une garde qui
crie au loup sur la forme normale du produit finit par être ignorée, donc elle
groupe par (chemin, méthode).

Ce banc n'exerce AUCUNE route : la collision est une propriété de la table des
règles. L'exercice complet, qui fait de vraies requêtes, vit dans
`tools/qa/exercer_routes.py`.
"""
import os
import sys

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RACINE)

from tools.qa import exercer_routes as er  # noqa: E402


def test_la_table_des_regles_est_bien_lue():
    """Une garde qui n'inspecte rien est une garde qui ment."""
    app, _ = er._client()
    regles = list(app.url_map.iter_rules())
    assert len(regles) > 150, 'seulement %d règles : le runtime n’est pas monté' % len(regles)


def test_aucun_chemin_n_a_deux_proprietaires():
    collisions = er.collisions_seules()
    assert not collisions, (
        'deux fonctions se disputent le même couple (chemin, méthode) — la '
        'seconde gagne en silence :\n  %s'
        % '\n  '.join('%s → %s' % (k, ', '.join(v)) for k, v in collisions.items()))


def test_la_mesure_distingue_bien_les_verbes():
    """Contre-épreuve : sans la méthode, trois routes normales seraient accusées."""
    app, _ = er._client()
    par_chemin: dict[str, set] = {}
    for r in app.url_map.iter_rules():
        par_chemin.setdefault(str(r.rule), set()).add(r.endpoint)
    partages = {c: sorted(e) for c, e in par_chemin.items() if len(e) > 1}
    assert partages, (
        'aucun chemin ne porte plus deux verbes : la contre-épreuve de cette '
        'garde ne prouve plus rien, il faut la réécrire')
    #  Et aucun de ces chemins partagés ne doit être une vraie collision.
    for chemin in partages:
        assert not any(k.startswith(chemin + ' [') for k in er.collisions_seules())
