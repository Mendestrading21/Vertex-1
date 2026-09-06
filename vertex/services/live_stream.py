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
    #  ── LE TAMPON DE REJEU EST PAR CANAL, PAS GLOBAL ────────────────────────
    #  MESURE (6 sept. 2026, instance de contrôle, un seul onglet au repos) :
    #  le tampon unique de 200 événements contenait 200/200 événements `jobs`,
    #  dont 187 `POSITION_REFRESH` — un battement émis dans le handler d'une
    #  requête et rediffusé à tous. Aucun événement `market`, `positions`,
    #  `portfolio`, `alerts` ni `connections` ne survivait : à 0,65 évt/s, la
    #  totalité du tampon tournait en ~5 minutes, et un client qui se
    #  reconnectait avec `Last-Event-ID` rejouait 93 % de bruit en ayant perdu
    #  EN SILENCE tous les vrais changements d'état. La capacité de rejeu
    #  annoncée dans l'en-tête de ce module était donc une promesse non tenue.
    #
    #  Un canal bavard ne peut plus évincer les autres : chacun garde ses
    #  événements récents, le rejeu les refusionne par id croissant. Le
    #  comportement d'un canal isolé est inchangé (les plus anciens sortent,
    #  les ids restent vrais) ; seule la famine inter-canaux disparaît.
    #
    #  ── `ring` RESTE LA CAPACITÉ TOTALE ────────────────────────────────────
    #  Premier correctif : un anneau de `ring` PAR CANAL. Conséquence mesurée,
    #  et c'est une régression : `_Broker(ring=200)` bornait le tampon à 200
    #  événements ; avec 10 canaux il en gardait jusqu'à 2 000 (10 × 200), donc
    #  autant rejoués d'un coup à un client qui se reconnecte avec un
    #  `Last-Event-ID` très ancien — 10× la mémoire et 10× la rafale annoncées.
    #  `stats()['buffered']` (somme des anneaux) changeait de borne sans le
    #  dire. `ring` redevient donc la capacité TOTALE :
    #
    #  - chaque canal a un QUOTA garanti (`ring // len(CHANNELS)`, 20 par
    #    défaut) : un bavard ne peut plus l'affamer ;
    #  - la capacité inutilisée reste disponible — un canal seul occupe encore
    #    les 200 places, comme avant les deux correctifs ;
    #  - quand le total dépasse `ring`, l'éviction retire le plus ANCIEN
    #    événement du canal qui dépasse LE PLUS son quota. C'est le bavard qui
    #    paie, jamais le canal silencieux qui garde le vrai changement d'état.
    def __init__(self, ring: int = 200):
        self._lock = threading.Lock()
        self._clients: list[queue.Queue] = []
        self._ring_max = ring
        #: Plancher garanti par canal. `max(1, …)` : sur un tampon minuscule
        #: (bancs à `ring=3`) le quota entier vaudrait 0 et aucun canal ne
        #: serait protégé.
        self._quota = max(1, ring // len(CHANNELS))
        self._rings: dict[str, deque] = {}
        self._next_id = 1

    def _borner(self) -> None:
        """Ramène le total sous `_ring_max` — appelée sous verrou uniquement."""
        total = sum(len(a) for a in self._rings.values())
        while total > self._ring_max:
            #  Le canal qui dépasse le plus son quota (à égalité, le plus
            #  long). Chaque tour retire un événement : la boucle se termine.
            canal = max(self._rings, key=lambda c: (len(self._rings[c]) - self._quota,
                                                    len(self._rings[c])))
            self._rings[canal].popleft()
            if not self._rings[canal]:
                del self._rings[canal]
            total -= 1

    def publish(self, channel: str, data: dict) -> int:
        """Publie un événement — jamais bloquant (clients lents ignorés)."""
        if channel not in CHANNELS:
            channel = 'system'
        with self._lock:
            ev = {'id': self._next_id, 'channel': channel,
                  'ts': round(time.time(), 3), 'data': data}
            self._next_id += 1
            anneau = self._rings.get(channel)
            if anneau is None:
                anneau = self._rings[channel] = deque(maxlen=self._ring_max)
            anneau.append(ev)
            self._borner()
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
        #  Refusion par id croissant : le client reçoit l'ordre chronologique
        #  réel, quel que soit le canal qui a le plus parlé.
        with self._lock:
            evs = [e for anneau in self._rings.values() for e in anneau
                   if e['id'] > last_id]
        evs.sort(key=lambda e: e['id'])
        return evs

    def stats(self) -> dict:
        #  `buffered` garde son sens ET sa borne : le nombre d'événements
        #  rejouables, tous canaux confondus, jamais plus que `ring`.
        with self._lock:
            return {'clients': len(self._clients),
                    'buffered': sum(len(a) for a in self._rings.values()),
                    'last_id': self._next_id - 1}


BROKER = _Broker()


def sse_format(ev: dict) -> str:
    return (f"id: {ev['id']}\n"
            f"event: {ev['channel']}\n"
            f"data: {json.dumps(ev, ensure_ascii=False)}\n\n")


__all__ = ['BROKER', 'CHANNELS', 'sse_format']
