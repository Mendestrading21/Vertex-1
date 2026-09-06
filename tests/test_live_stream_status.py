"""tests/test_live_stream_status.py — SKYLER LOT 99 : services temps réel figés.

Trous réels de couverture : vertex/services/live_stream.py (le broker SSE
pub/sub — AUCUN test direct, seule mention = son nom dans une liste de
workers) et les transitions d'état de status_service (ok/warming/degraded,
avertissements de rassissement, fraîcheur unknown/stale, résolution du mode)
que test_ibkr_honesty/test_foundation ne figent pas.
Caractérisations nées vertes (dites) — moteurs INTACTS.
Brokers NEUFS à chaque test : le BROKER global partagé n'est jamais touché.
"""
import json
import time

from vertex.services import status_service
from vertex.services.live_stream import CHANNELS, _Broker, sse_format


# ---------------------------------------------------------------- live_stream

def test_unknown_channel_routed_to_system_and_ids_monotonic():
    b = _Broker()
    assert b.publish('market', {'a': 1}) == 1
    assert b.publish('canal-inexistant', {'b': 2}) == 2
    evs = b.replay_since(0)
    assert [e['id'] for e in evs] == [1, 2]
    assert evs[1]['channel'] == 'system', (
        'un canal inconnu est reclassé system — jamais perdu, jamais inventé')
    assert all(c in CHANNELS for c in ('market', 'system'))


def test_replay_since_serves_only_newer_events():
    b = _Broker()
    for i in range(5):
        b.publish('alerts', {'i': i})
    assert [e['id'] for e in b.replay_since(3)] == [4, 5]
    assert b.replay_since(5) == []          # client à jour → rien à rejouer


def test_ring_buffer_drops_oldest_beyond_capacity():
    b = _Broker(ring=3)
    for i in range(5):
        b.publish('jobs', {'i': i})
    evs = b.replay_since(0)
    assert [e['id'] for e in evs] == [3, 4, 5], (
        'tampon circulaire : les plus anciens sortent, les ids restent vrais')
    assert b.stats() == {'clients': 0, 'buffered': 3, 'last_id': 5}


def test_un_canal_bavard_n_evince_pas_le_rejeu_des_autres():
    """MESURE (6 sept. 2026, instance de contrôle) : composition du tampon de
    rejeu au moment du rejeu à la connexion → 200/200 événements `jobs`, dont
    187 `POSITION_REFRESH`. Aucun `market`, `positions`, `portfolio`, `alerts`
    ni `connections` ne survivait : le client qui se reconnectait avec
    `Last-Event-ID` rejouait 93 % de bruit et avait perdu EN SILENCE tous les
    vrais changements d'état, alors que ce module annonce « rejouer après
    reconnexion ». Le tampon est désormais par canal : un canal bavard ne peut
    plus affamer les autres.
    """
    b = _Broker(ring=3)
    vrai = b.publish('market', {'scan_ts': 1})
    for i in range(50):                     # le canal bavard, comme mesuré
        b.publish('jobs', {'i': i})
    rejeu = b.replay_since(0)
    assert [e['id'] for e in rejeu] == sorted(e['id'] for e in rejeu), (
        'le rejeu doit rester chronologique après refusion des canaux')
    marches = [e for e in rejeu if e['channel'] == 'market']
    assert [e['id'] for e in marches] == [vrai], (
        'le vrai changement d’état a été évincé par 50 battements de jobs')
    assert len(b.replay_since(0)) == 4      # 3 `jobs` gardés + 1 `market`


def test_slow_client_never_blocks_publisher():
    b = _Broker()
    q = b.subscribe()
    for i in range(501):                    # dépasse maxsize=500 de la file
        b.publish('positions', {'i': i})
    assert q.qsize() == 500                 # le surplus est ignoré, pas bloqué
    assert b.stats()['last_id'] == 501      # le diffuseur n'a jamais attendu


def test_subscribe_unsubscribe_is_idempotent():
    b = _Broker()
    q = b.subscribe()
    b.publish('connections', {'x': 1})
    assert q.get_nowait()['data'] == {'x': 1}
    b.unsubscribe(q)
    b.unsubscribe(q)                        # double départ : silencieux
    b.publish('connections', {'x': 2})
    assert q.qsize() == 0                   # plus rien ne lui est livré
    assert b.stats()['clients'] == 0


def test_sse_format_exact_named_event_framing():
    # Le client utilise addEventListener(canal) — le framing NOMMÉ est le
    # contrat (leçon lot 85 : onmessage reste muet sur un event: nommé).
    ev = {'id': 7, 'channel': 'system', 'ts': 1.0, 'data': {'msg': 'déjà vu'}}
    out = sse_format(ev)
    assert out.startswith('id: 7\nevent: system\ndata: ')
    assert out.endswith('\n\n')             # double saut = fin d'événement SSE
    payload = json.loads(out.split('data: ', 1)[1])
    assert payload['data']['msg'] == 'déjà vu'   # accents intacts (pas d'\\u)


# -------------------------------------------------------------- status_service

def _status(scan_state, **kw):
    base = dict(build='test', readonly=True, ibkr_enabled=False,
                demo_mode=False, ai_on=False)
    base.update(kw)
    return status_service.build_system_status(scan_state, **base)


def test_app_status_transitions_warming_degraded_ok():
    warming = _status({})
    assert warming['app'] == 'warming'
    assert any('aucun titre' in w for w in warming['warnings'])
    degraded = _status({'rows': [1], 'error': 'boom'})
    assert degraded['app'] == 'degraded'    # l'erreur prime sur tout
    ok = _status({'rows': [1], 'scan_ts': time.time()})
    assert ok['app'] == 'ok' and ok['warnings'] == []


def test_freshness_unknown_stale_and_stale_warning():
    st = _status({'rows': [1], 'scan_ts': time.time() - 5000})
    assert st['freshness']['scan']['state'] == 'stale'
    assert any('rassis' in w for w in st['warnings'])
    assert st['app'] == 'warming'           # rassis = avertissement, pas panne
    no_ts = _status({'rows': [1]})
    assert no_ts['freshness']['scan']['state'] == 'unknown', (
        'pas de timestamp → unknown honnête, jamais fresh par défaut')
    assert status_service._age_seconds('pas-un-nombre') is None


def test_mode_resolution_demo_primes_then_ibkr_then_cloud():
    assert _status({}, demo_mode=True, ibkr_enabled=True)['mode'] == 'demo'
    assert _status({}, ibkr_enabled=True)['mode'] == 'ibkr'
    assert _status({})['mode'] == 'cloud'
