"""vertex.services.live_stream — diffuseur d'événements temps réel (§26).

Pub/sub en mémoire pour Server-Sent Events : chaque client SSE reçoit les
événements publiés par les boucles de fond (marché, positions, alertes,
jobs, connexions). Tampon circulaire pour rejouer après reconnexion
(Last-Event-ID). Lecture seule : les événements DÉCRIVENT, jamais
n'exécutent.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque

CHANNELS = ('market', 'positions', 'options', 'portfolio', 'decisions',
            'alerts', 'connections', 'jobs', 'system', 'news')


class _Broker:
    def __init__(self, ring: int = 200):
        self._lock = threading.Lock()
        self._clients: list[queue.Queue] = []
        self._ring: deque = deque(maxlen=ring)
        self._next_id = 1

    def publish(self, channel: str, data: dict) -> int:
        """Publie un événement — jamais bloquant (clients lents ignorés)."""
        if channel not in CHANNELS:
            channel = 'system'
        with self._lock:
            ev = {'id': self._next_id, 'channel': channel,
                  'ts': round(time.time(), 3), 'data': data}
            self._next_id += 1
            self._ring.append(ev)
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(ev)
            except queue.Full:
                pass
        return ev['id']

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=500)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    def replay_since(self, last_id: int) -> list[dict]:
        with self._lock:
            return [e for e in self._ring if e['id'] > last_id]

    def stats(self) -> dict:
        with self._lock:
            return {'clients': len(self._clients), 'buffered': len(self._ring),
                    'last_id': self._next_id - 1}


BROKER = _Broker()


def sse_format(ev: dict) -> str:
    return (f"id: {ev['id']}\n"
            f"event: {ev['channel']}\n"
            f"data: {json.dumps(ev, ensure_ascii=False)}\n\n")


__all__ = ['BROKER', 'CHANNELS', 'sse_format']
