"""Lot 6 — une cotation en mémoire se sert immédiatement, jamais après 45 s.

Mesuré avant ce lot : `/api/pos-quotes` tient un cache de 45 s ; au-delà, la
requête UI attendait le worker IBKR — jusqu'à 45 s, derrière la rotation des
chaînes dans la MÊME file (20/33/56 s relevés dans le code). Une cotation
vieille de 46 s existait pourtant en mémoire.

Le contrat du skill : aucune requête d'interface n'attend le fournisseur.
La tranche tenue ici : si le cache porte la clé — fraîche OU périmée — la
route répond immédiatement ; le périmé est ÉTIQUETÉ (`stale` + âge) et un
rafraîchissement part en arrière-plan. Seule une clé jamais cotée garde une
attente bornée, resserrée à 12 s, puis le repli honnête existant.
"""
from __future__ import annotations

import threading
import time


def _hooks():
    """Les crochets du blueprint desk de l'application REELLE — pas d'un
    blueprint reconstruit par un autre banc."""
    import terminal
    return terminal.app.blueprints['desk']._vx_hooks


def test_une_cotation_perimee_se_sert_immediatement(monkeypatch):
    """Cache au-delà du TTL + worker LENT → réponse immédiate, étiquetée."""
    import terminal

    cle = 'NVDA|||'
    vieux = time.time() - 120           # bien au-delà des 45 s de TTL
    _hooks()['posq_cache'][cle] = (vieux, {'mark': 500.0,
                                                     'source': 'IBKR'})

    def worker_lent(kind, args, timeout):
        time.sleep(5)                    # un vrai blocage se verrait au chrono
        return {}

    monkeypatch.setitem(_hooks(), 'opt_job', worker_lent)
    monkeypatch.setitem(_hooks(), 'ibkr_enabled', True)

    debut = time.monotonic()
    r = terminal.app.test_client().post('/api/pos-quotes',
                                        json={'positions': [{'sym': 'NVDA'}]})
    duree = time.monotonic() - debut
    corps = r.get_json()

    assert r.status_code == 200
    assert duree < 3.0, (
        'la route a attendu le worker (%.1f s) alors que le cache portait la '
        'clé : le périmé doit se servir immédiatement.' % duree)
    assert corps['results'][cle]['mark'] == 500.0
    assert cle in corps.get('stale', []), (
        'une cotation périmée servie sans étiquette est un mensonge de '
        'fraîcheur : la réponse doit porter `stale`.')
    _hooks()['posq_cache'].pop(cle, None)


def test_une_cle_jamais_cotee_garde_une_attente_bornee_courte(monkeypatch):
    """Mission alimentation (2026-09-06) : la clé jamais cotée part au worker
    EN FOND ; la REQUÊTE n'attend plus que `POSQ_ATTENTE_S` (1,5 s par défaut,
    0,2 s ici), puis rend le repli et nomme la clé dans `en_attente`. Le
    worker garde son propre délai (45 s), hors requête."""
    import terminal
    from vertex.app.routes import desk

    monkeypatch.setattr(desk, 'POSQ_ATTENTE_S', 0.2)
    appels = []

    def worker_lent(kind, args, timeout):
        appels.append((kind, threading.current_thread() is threading.main_thread()))
        if kind == 'posq':
            time.sleep(0.8)
        return {}

    monkeypatch.setitem(_hooks(), 'opt_job', worker_lent)
    monkeypatch.setitem(_hooks(), 'ibkr_enabled', True)
    _hooks()['posq_cache'].pop('ZZZZ|||', None)
    debut = time.monotonic()
    corps = terminal.app.test_client().post(
        '/api/pos-quotes', json={'positions': [{'sym': 'ZZZZ'}]}).get_json()
    duree = time.monotonic() - debut
    assert duree < 0.7, (
        'la requête a attendu le worker (%.2f s) : la clé jamais cotée doit '
        'partir en fond, la requête ne garde qu’une attente courte.' % duree)
    assert 'ZZZZ|||' in corps.get('en_attente', []), (
        'la clé encore en cours de cotation doit être nommée (`en_attente`).')
    assert any(k == 'posq' and not principal for k, principal in appels), (
        'le worker doit avoir été appelé hors du fil de la requête.')
