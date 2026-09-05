"""vertex.data_sources.ibkr_gateway — connexion IBKR STRICTEMENT lecture seule.

Invariant produit : `readonly=True` est codé en dur et non paramétrable.
Aucune méthode d'ordre n'existe dans cette façade ; les tests de sécurité
(tests/test_no_orders.py, tests/test_ibkr_honesty.py,
tests/test_order_ticket.py) inspectent ce module.
"""
from __future__ import annotations

import os
import threading

from vertex.data_sources import ibkr_link, ibkr_session


def classe(nom: str):
    """L'UNIQUE porte d'import de ib_async (contrôle 018 de l'audit-150).

    Toute classe ib_async (Stock, Option, Index, CFD, IB,
    ScannerSubscription…) s'obtient ICI, jamais par un import direct —
    gardien : tests/test_import_ibkr_unique.py. Import paresseux :
    l'application démarre et fonctionne sans la dépendance (mode dégradé).
    """
    import ib_async
    return getattr(ib_async, nom)

# Timeout anti-blocage : ne pas retirer (un worker IBKR bloqué gèle l'app).
REQUEST_TIMEOUT_S = 45

_DEFAULT_HOST = ibkr_link.hote()
#: Le port n'est plus figé : cette façade n'essayait QUE le 7497 (TWS papier) et
#: ne se connectait donc JAMAIS, en silence, sur un TWS réel seul. `None`
#: signifie « cherche », et `connect()` parcourt l'ordre partagé.
_DEFAULT_PORT = None
#: 17 auparavant — soit exactement l'identifiant de la lecture de compte. IBKR
#: refuse une seconde session portant un identifiant déjà pris : selon l'ordre
#: de démarrage, l'un des deux échouait, avec un message qui ne parle jamais de
#: collision.
_DEFAULT_CLIENT_ID = int(os.environ.get('IBKR_CLIENT_ID', '0')) \
    or ibkr_link.client_id('passerelle')


class IbkrGateway:
    """Façade de connexion. Un seul worker à la fois (lock), lecture seule à vie."""

    READONLY = True  # non négociable — inspecté par les tests de sécurité

    def __init__(self, host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT,
                 client_id: int = _DEFAULT_CLIENT_ID) -> None:
        self.host, self.port, self.client_id = host, port, client_id
        self._ib = None
        self._lock = threading.Lock()

    # ── cycle de vie ─────────────────────────────────────────────────
    def connect(self):
        """Connexion lecture seule. Import paresseux : l'app doit démarrer sans TWS.

        Le port est CHERCHÉ quand il n'est pas imposé : lancer TWS doit suffire,
        sans variable d'environnement ni redémarrage.
        """
        IB = classe('IB')     # porte unique, paresseuse (mode dégradé sans dépendance)
        with self._lock:
            if self._ib is not None and self._ib.isConnected():
                return self._ib
            ports = (self.port,) if self.port else ibkr_link.ordre_des_ports()
            derniere = None
            for port in ports:
                ib = IB()
                ib.RequestTimeout = REQUEST_TIMEOUT_S
                try:
                    #  Session « marché seulement » (ibkr_session) : poignée
                    #  de main client, AUCUNE synchronisation de compte,
                    #  positions, ordres ni exécutions — `IB.connect` en
                    #  émettait au premier instant, readonly=True ou non —
                    #  puis verrouillage des méthodes de compte. readonly=True
                    #  reste écrit ici, où les gardiens le cherchent.
                    ibkr_session.connecter(ib, self.host, port, client_id=self.client_id,
                                           timeout=REQUEST_TIMEOUT_S, readonly=True)
                except Exception as exc:                       # noqa: BLE001
                    derniere = exc
                    continue
                #  Affectation SIMPLE, et ce n'est pas du style : la mesure de
                #  surface IBKR derive les porteurs d'objet `IB` en suivant les
                #  ALIAS (`self._ib = ib`). Ecrit en tuple
                #  (`self._ib, self.port = ib, port`), l'alias n'est plus derive
                #  et TOUS les appels passant par `self._ib` deviennent
                #  invisibles a la liste blanche lecture seule. Le gardien l'a
                #  trouve ; c'est le code qui a ete corrige, pas lui.
                self._ib = ib
                self.port = port
                ibkr_link.noter_succes(port, 'passerelle')
                return ib
            ibkr_link.noter_echec('passerelle', str(derniere or ''))
            #  On releve l'echec plutot que de rendre None : un appelant qui
            #  recevrait None irait chercher des cotations sur un objet absent,
            #  et le message parlerait d'attribut manquant au lieu de TWS.
            raise ConnectionError(
                'TWS / IB Gateway injoignable sur %s (ports essayés : %s)%s'
                % (self.host, ', '.join(str(p) for p in ports),
                   ' — %s' % derniere if derniere else ''))

    def disconnect(self) -> None:
        with self._lock:
            if self._ib is not None:
                try:
                    self._ib.disconnect()
                finally:
                    self._ib = None

    @property
    def connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    def status(self) -> dict:
        """`port` vaut None tant qu'aucune session n'a abouti — l'aveu honnête
        « on ne sait pas encore », et non un port supposé. `ports_essayes` rend
        la panne diagnosticable sans lire le code."""
        return {'connected': self.connected, 'host': self.host, 'port': self.port,
                'mode': ibkr_link.MODES.get(self.port),
                'ports_essayes': list(ibkr_link.ordre_des_ports()),
                'client_id': self.client_id, 'readonly': True,
                'order_execution': 'disabled-by-design'}
