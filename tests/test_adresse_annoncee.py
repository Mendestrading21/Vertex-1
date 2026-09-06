# -*- coding: utf-8 -*-
"""L'adresse annoncée au démarrage doit être joignable — mesure du 2026-09-06.

Ouvert dans un navigateur, `http://localhost:5002` ne répondait pas : le serveur
écoute en IPv4 (`0.0.0.0` ou `127.0.0.1`, règle de `vertex/app/exposition.py`),
et le client résolvait `localhost` en IPv6 (`::1`). Pire, un service worker
déjà installé sur cette origine servait alors la coque PÉRIMÉE de son cache
hors-ligne : la page s'affichait sans feuille de style et sans données —
l'application paraissait cassée alors qu'elle tournait normalement (vérifié en
parallèle : `http://127.0.0.1:5002/healthz` répondait `status: ok`,
`ibkr_live: true`).

Le correctif n'est PAS de changer l'écoute (l'exposition réseau est une règle de
sécurité avec ses propres gardiens) : c'est d'annoncer et d'ouvrir l'adresse qui
répond à coup sûr.
"""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lire(nom):
    with open(os.path.join(_ROOT, nom), encoding='utf-8', errors='replace') as f:
        return f.read()


def test_le_demarrage_annonce_une_adresse_ipv4():
    src = _lire('terminal.py')
    m = re.search(r"print\(f'VERTEX -> (http://[^{]*)\{port\}", src)
    assert m, 'la ligne de démarrage qui annonce l’adresse a disparu'
    assert m.group(1) == 'http://127.0.0.1:', (
        'le démarrage annonce %r : `localhost` peut résoudre en ::1, que le '
        'serveur (IPv4) n’écoute pas.' % m.group(1))


def test_les_lanceurs_ouvrent_l_adresse_ipv4():
    for nom in ('Lancer_VERTEX.bat', 'Lancer_VERTEX_DEMO.bat'):
        src = _lire(nom)
        assert 'start http://127.0.0.1:5002' in src, nom
        assert 'start http://localhost:5002' not in src, nom


def test_la_raison_est_ecrite_a_cote_du_correctif():
    """Sans la raison, quelqu'un « simplifiera » l'adresse en `localhost`."""
    src = _lire('terminal.py')
    i = src.index("print(f'VERTEX -> http://127.0.0.1:")
    contexte = src[max(0, i - 700):i]
    assert '::1' in contexte and 'IPv4' in contexte, (
        'la raison de l’adresse IPv4 n’est plus écrite à côté d’elle')


def test_l_ecoute_elle_meme_n_a_pas_bouge():
    """Le correctif touche l'ANNONCE, jamais la règle d'exposition."""
    from vertex.app.exposition import exposition
    assert exposition(True, env={})['hote'] == '0.0.0.0'      # verrou actif : LAN autorisé
    assert exposition(False, env={})['hote'] == '127.0.0.1'   # sans verrou : boucle locale
