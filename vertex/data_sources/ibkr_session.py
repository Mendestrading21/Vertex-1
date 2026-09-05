"""vertex.data_sources.ibkr_session — connexion IBKR « données de marché SEULEMENT ».

Pourquoi ce module existe (mesuré dans `ib_async 2.1.0`, `ib.py::connectAsync`) :

- `IB.connect(...)` émet **`reqPositions` sans condition**, puis selon
  `fetchFields` (défaut `StartupFetchALL`) `reqAccountUpdates(account)`,
  `reqAccountUpdatesMulti` pour chaque sous-compte et `reqExecutions`.
- `readonly=True` n'empêche AUCUNE de ces lectures : il ne coupe que les
  requêtes d'ordres ouverts/terminés.
- `fetchFields=StartupFetchNONE` laisse encore passer `reqPositions`.

Or l'invariant Vertex est sans nuance : IBKR fournit des données de marché,
jamais compte, cash, NAV, positions, P&L, ordres ni exécutions. Une session
ouverte par `IB.connect` viole donc l'invariant AVANT la première cotation,
même si l'application n'affiche jamais ces données.

Ce module ouvre la session au niveau de la couche client (poignée de main
API : version, `nextValidId`, identifiants de comptes gérés — métadonnées du
protocole, inévitables, ni journalisées ni exposées), sans aucune requête de
synchronisation, puis VERROUILLE l'instance : toute méthode de compte, de
portefeuille, de P&L, d'ordre ou d'exécution lève `FrontiereIbkrError`.

Ce que prouvent les tests (`tests/test_ibkr_session_marche_seule.py`) :
1. sur une doublure d'`IB`, la connexion n'émet que la poignée de main ;
2. après verrouillage, chaque méthode interdite lève ;
3. aucun site du dépôt n'appelle plus `IB.connect` / `connectAsync` ;
4. (optionnel, `VERTEX_TEST_IBKR_LIVE=1` avec TWS ouvert) sur la vraie socket,
   la session ne détient ni position, ni valeur de compte, ni ordre.

Aucun import direct de `ib_async` ici : la porte unique reste
`vertex.data_sources.ibkr_gateway.classe` (contrôle 018). Ce module ne reçoit
qu'une instance `IB` déjà construite.
"""
from __future__ import annotations

import time
from typing import Iterable

from vertex.data_sources import ibkr_link

#: Méthodes d'`ib_async.IB` qui lisent le COMPTE, le PORTEFEUILLE ou le P&L.
#: Nommées ici parce que le verrouillage doit pouvoir les citer dans les tests ;
#: les méthodes d'ORDRE et d'EXÉCUTION ne sont pas nommées dans le code produit
#: (le gardien `tests/test_no_orders.py` l'interdit) : elles tombent sous le
#: refus PAR DÉFAUT — tout ce qui n'est pas dans `METHODES_MARCHE` est verrouillé.
METHODES_INTERDITES: tuple[str, ...] = (
    'managedAccounts', 'accountValues', 'accountSummary', 'portfolio', 'positions',
    'pnl', 'pnlSingle', 'reqAccountUpdates', 'reqAccountUpdatesMulti',
    'reqAccountSummary', 'reqPositions', 'reqPositionsMulti', 'reqPnL',
    'reqPnLSingle', 'reqUserInfo', 'reqFamilyCodes', 'trades', 'openTrades',
    'orders', 'openOrders', 'fills', 'executions', 'reqExecutions',
    'reqAccountUpdatesAsync', 'reqAccountUpdatesMultiAsync', 'accountSummaryAsync',
    'reqAccountSummaryAsync', 'reqPositionsAsync', 'reqPositionsMultiAsync',
    'reqPnLAsync', 'reqPnLSingleAsync', 'reqUserInfoAsync', 'reqFamilyCodesAsync',
    'reqExecutionsAsync', 'reqAutoOpenOrders',
)

#: LISTE BLANCHE : les seules méthodes publiques d'`IB` qu'une session Vertex
#: peut appeler. Tout autre attribut appelable de la classe est verrouillé.
METHODES_MARCHE: frozenset[str] = frozenset((
    # contrats et cotations
    'qualifyContracts', 'qualifyContractsAsync', 'reqContractDetails',
    'reqContractDetailsAsync', 'reqMatchingSymbols', 'reqMatchingSymbolsAsync',
    'reqMktData', 'cancelMktData', 'reqTickers', 'reqTickersAsync',
    'reqMarketDataType', 'reqSmartComponents', 'reqSmartComponentsAsync',
    'reqMarketRule', 'reqMarketRuleAsync', 'reqMktDepthExchanges',
    'reqMktDepthExchangesAsync', 'reqMktDepth', 'cancelMktDepth',
    'reqRealTimeBars', 'cancelRealTimeBars', 'reqTickByTickData',
    'cancelTickByTickData', 'ticker', 'tickers', 'pendingTickers', 'contracts',
    # historique
    'reqHistoricalData', 'reqHistoricalDataAsync', 'cancelHistoricalData',
    'reqHeadTimeStamp', 'reqHeadTimeStampAsync', 'reqHistogramData',
    'reqHistogramDataAsync', 'reqHistoricalTicks', 'reqHistoricalTicksAsync',
    'reqHistoricalSchedule', 'reqHistoricalScheduleAsync',
    # options
    'reqSecDefOptParams', 'reqSecDefOptParamsAsync', 'calculateImpliedVolatility',
    'calculateImpliedVolatilityAsync', 'calculateOptionPrice',
    'calculateOptionPriceAsync',
    # actualités et scanners
    'reqNewsBulletins', 'cancelNewsBulletins', 'newsBulletins', 'newsTicks',
    'reqNewsProviders', 'reqNewsProvidersAsync', 'reqNewsArticle',
    'reqNewsArticleAsync', 'reqHistoricalNews', 'reqHistoricalNewsAsync',
    'reqScannerData', 'reqScannerDataAsync', 'reqScannerSubscription',
    'cancelScannerSubscription', 'reqScannerParameters', 'reqScannerParametersAsync',
    # session et boucle
    'isConnected', 'disconnect', 'sleep', 'run', 'waitOnUpdate', 'loopUntil',
    'setTimeout', 'timeRange', 'timeRangeAsync', 'schedule', 'reqCurrentTime',
    'reqCurrentTimeAsync', 'reqTimeAsync', 'reqWshMetaData', 'reqWshEventData',
    'getWshMetaData', 'getWshEventData',
))

_MARQUE = '_vertex_marche_seulement'


class FrontiereIbkrError(PermissionError):
    """Appel d'une méthode de compte, de portefeuille, d'ordre ou d'exécution
    sur une session IBKR de Vertex. Levée AVANT toute requête réseau."""


def _interdit(nom: str):
    def _refus(*_args, **_kwargs):
        raise FrontiereIbkrError(
            'IBKR est une source de données de marché uniquement : `%s` est '
            'interdit par la frontière Vertex (aucune requête émise).' % nom)
    _refus.__name__ = nom
    _refus.__doc__ = 'Verrouillé par vertex.data_sources.ibkr_session.'
    return _refus


def verrouiller(ib):
    """Verrouille une instance `IB` : les méthodes interdites lèvent.

    Les identifiants de comptes gérés reçus pendant la poignée de main sont
    des métadonnées de protocole ; ils sont effacés de l'instance pour
    qu'aucun chemin ultérieur ne puisse les lire ni les journaliser.
    """
    #  Refus PAR DÉFAUT : chaque méthode publique de la classe qui n'est pas
    #  dans la liste blanche de marché est remplacée sur l'instance. Les
    #  méthodes de compte nommées ci-dessus le sont aussi, même si la classe
    #  ne les définit pas (doublures de test).
    for nom in dir(type(ib)):
        if nom.startswith('_') or nom in METHODES_MARCHE:
            continue
        if callable(getattr(type(ib), nom, None)):
            setattr(ib, nom, _interdit(nom))
    for nom in METHODES_INTERDITES:
        setattr(ib, nom, _interdit(nom))
    wrapper = getattr(ib, 'wrapper', None)
    if wrapper is not None:
        for attr in ('accounts',):
            if hasattr(wrapper, attr):
                try:
                    setattr(wrapper, attr, [])
                except Exception:  # noqa: BLE001 — attribut figé : on n'insiste pas
                    pass
    client = getattr(ib, 'client', None)
    if client is not None and hasattr(client, '_accounts'):
        try:
            client._accounts = []
        except Exception:  # noqa: BLE001
            pass
    setattr(ib, _MARQUE, True)
    return ib


def est_verrouillee(ib) -> bool:
    return bool(getattr(ib, _MARQUE, False))


async def _poignee_de_main(ib, host: str, port: int, client_id: int, timeout: float | None):
    """Connexion de la couche client seulement : version API, `nextValidId`,
    comptes gérés. AUCUNE requête de positions, de compte, d'ordres ou
    d'exécutions n'est émise (contrairement à `IB.connectAsync`)."""
    ib.wrapper.clientId = int(client_id)
    await ib.client.connectAsync(host, int(port), int(client_id), timeout or None)
    if not ib.client.isReady():
        raise ConnectionError('socket IBKR rompue pendant la connexion')


def connecter(ib, host: str, port: int, client_id: int, timeout: float = 4.0,
              *, readonly: bool = True):
    """Ouvre une session « marché seulement » et la verrouille.

    `readonly` n'accepte que `True` : le mot reste écrit sur chaque site
    d'appel, là où les gardiens (`tests/test_no_orders.py`) le cherchent, et
    la valeur `False` est refusée avant toute connexion. `client_id` 0 est
    refusé : ib_async l'associe à l'auto-liaison des ordres manuels de TWS
    (`reqAutoOpenOrders`), ce qui n'a aucune place ici.
    """
    if readonly is not True:
        raise ValueError('une session IBKR de Vertex est toujours readonly=True')
    client_id = int(client_id)
    if client_id == 0:
        raise ValueError('clientId 0 interdit : il lie la session aux ordres manuels de TWS')
    ib._run(_poignee_de_main(ib, host, port, client_id, timeout))
    return verrouiller(ib)


def connecter_role(ib, role: str, timeout: float = 4.0,
                   ports: Iterable[int] | None = None) -> int:
    """Parcourt les ports partagés (`ibkr_link.ordre_des_ports`) avec
    l'identifiant du rôle, note le succès ou l'échec pour les autres sites, et
    rend le port qui a répondu. Lève `ConnectionError` si aucun ne répond."""
    host = ibkr_link.hote()
    client_id = ibkr_link.client_id(role)
    derniere: Exception | None = None
    essais = list(ports) if ports is not None else list(ibkr_link.ordre_des_ports())
    for port in essais:
        debut = time.time()
        try:
            connecter(ib, host, port, client_id, timeout, readonly=True)
        except Exception as exc:  # noqa: BLE001 — chaque port est un essai borné
            derniere = exc
            try:
                ib.client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            continue
        ibkr_link.noter_succes(port, role)
        return port
    ibkr_link.noter_echec(role, str(derniere or ''))
    raise ConnectionError(
        'TWS / IB Gateway injoignable sur %s (ports essayés : %s)%s'
        % (host, ', '.join(str(p) for p in essais),
           ' — %s' % derniere if derniere else ''))


__all__ = ['METHODES_INTERDITES', 'METHODES_MARCHE', 'FrontiereIbkrError',
           'verrouiller', 'est_verrouillee', 'connecter', 'connecter_role']
