# -*- coding: utf-8 -*-
"""tests/test_frontiere_ibkr_client.py — LE VERROU IBKR COUVRE AUSSI `ib.client`.

## La mesure qui a fait naître ce banc (ROUGE avant le correctif)

`vertex/data_sources/ibkr_session.py` promet, mot pour mot, de « VERROUILLER
l'instance : toute méthode de compte, de portefeuille, de P&L, d'ordre ou
d'exécution lève `FrontiereIbkrError` ». Mesuré sur `ib_async 2.1.0`, une
instance `IB()` passée à `verrouiller()` :

```text
façade IB      : 0 méthode sensible encore appelable   (le verrou tenait)
client bas niveau `ib.client` :
    95 méthodes publiques, 0 verrouillée
    27 d'entre elles portent la surface interdite, dont
    reqPositions · reqAccountSummary · reqAccountUpdates · reqExecutions
    reqPnL · reqPnLSingle · getAccounts · reqManagedAccts · reqUserInfo
    replaceFA · exerciseOptions · et la surface d'ordre
```

`ib.client` n'est ni privé ni théorique : c'est l'objet par lequel
`ibkr_session._poignee_de_main` ouvre la socket, et `Client.reqPositions()` se
résume à `self.send(61, 1)` — un vrai message sur une vraie session. La moitié
verrouillée était la moitié qui se voit.

Après correctif, sur la même instance : **40 méthodes du client verrouillées,
55 libres**, toutes de marché ou de transport.

## Ce que ce banc garde, et comment

Il ne fige AUCUNE liste de noms comme vérité : il mesure une propriété sur la
classe réellement installée. Un `ib_async` qui ajouterait demain
`reqPortfolioSummary` échouerait ici sans qu'une ligne soit à réécrire — c'est
tout l'objet du refus PAR DÉFAUT.

Les deux sens sont gardés : le verrou doit fermer la surface sensible **et**
laisser passer le marché. Un verrou qui bloque tout satisferait la première
moitié et casserait le produit ; la seconde moitié l'interdit.
"""
from __future__ import annotations

import pytest

from vertex.data_sources import ibkr_gateway, ibkr_session


def _ib_verrouillee():
    """Une vraie instance `IB`, obtenue par la porte unique, puis verrouillée.

    Aucune connexion : `verrouiller` n'émet rien et ne touche pas la socket.
    """
    IB = ibkr_gateway.classe('IB')       # porte unique (contrôle 018)
    return ibkr_session.verrouiller(IB())


def _publics(classe) -> set[str]:
    return {nom for nom in dir(classe)
            if not nom.startswith('_') and callable(getattr(classe, nom, None))}


def _est_verrouillee(objet, nom: str) -> bool:
    """Verrouillée = l'appel lève `FrontiereIbkrError` AVANT toute émission."""
    try:
        getattr(objet, nom)()
    except ibkr_session.FrontiereIbkrError:
        return True
    except Exception:                    # noqa: BLE001 — elle a été appelée : libre
        return False
    return False


def test_aucune_methode_publique_du_client_hors_surface_autorisee_ne_repond():
    """LE CŒUR. Refus PAR DÉFAUT sur `ib.client`, mesuré méthode par méthode.

    Avant correctif : 95 méthodes publiques du client, 0 verrouillée — donc 45
    hors de la surface de marché répondaient, dont les 27 sensibles.
    Après : chacune de ces 45 lève `FrontiereIbkrError`.
    """
    ib = _ib_verrouillee()
    autorisees = ibkr_session.surface_client_autorisee(type(ib.client))
    fuites = [nom for nom in sorted(_publics(type(ib.client)) - autorisees)
              if not _est_verrouillee(ib.client, nom)]
    assert not fuites, (
        'méthodes du client bas niveau encore appelables sur une session '
        '« verrouillée » : %s' % fuites)


def test_la_surface_sensible_du_client_est_nommee_et_bloquee():
    """Le même refus, nommé — pour qu'une régression se lise sans décoder l'AST.

    Ces noms sont ceux d'`ib_async.Client`. Les méthodes d'ORDRE ne sont pas
    citées dans le code produit (gardien `tests/test_no_orders.py`) : elles
    tombent sous le refus par défaut, mesuré par le test précédent.
    """
    ib = _ib_verrouillee()
    sensibles = ('reqPositions', 'reqPositionsMulti', 'reqAccountSummary',
                 'reqAccountUpdates', 'reqAccountUpdatesMulti', 'reqExecutions',
                 'reqPnL', 'reqPnLSingle', 'getAccounts', 'reqManagedAccts',
                 'reqUserInfo', 'reqFamilyCodes', 'replaceFA', 'requestFA',
                 'exerciseOptions')
    presentes = [n for n in sensibles if hasattr(type(ib.client), n)]
    assert presentes, 'aucune méthode sensible trouvée : la mesure ne mesure plus rien'
    ouvertes = [n for n in presentes if not _est_verrouillee(ib.client, n)]
    assert not ouvertes, 'surface compte/P&L/exécution ouverte sur ib.client : %s' % ouvertes


def test_le_verrou_ne_ferme_pas_le_marche_ni_le_transport():
    """L'AUTRE SENS. Un verrou qui bloque tout passerait le test précédent.

    Les requêtes de marché et la plomberie de transport doivent rester
    appelables : sans elles, plus une cotation, plus une connexion.
    """
    ib = _ib_verrouillee()
    marche = ('reqMktData', 'reqHistoricalData', 'reqContractDetails',
              'reqSecDefOptParams', 'reqTickers' if hasattr(type(ib.client), 'reqTickers')
              else 'reqRealTimeBars', 'reqScannerSubscription', 'reqNewsProviders')
    transport = ('connectAsync', 'disconnect', 'isConnected', 'isReady', 'send',
                 'serverVersion', 'getReqId', 'startApi')
    fermees = [n for n in marche + transport
               if hasattr(type(ib.client), n) and _est_verrouillee(ib.client, n)]
    assert not fermees, ('le verrou a fermé une capacité de marché ou de '
                         'transport : %s' % fermees)


def test_l_annulation_d_une_requete_autorisee_reste_possible():
    """`IB.calculateImpliedVolatilityAsync`, `IB.reqHeadTimeStampAsync` et
    `IB.getWshMetaData` — toutes blanchies — appellent `client.cancelX` dans
    leur `finally` (mesuré dans `ib_async/ib.py`, lignes 1943, 1971, 2438, 2518,
    2539). Verrouiller ces annulations casserait une capacité autorisée.

    Propriété, pas liste : pour CHAQUE `cancelX` du client, l'annulation est
    ouverte si et seulement si sa requête d'origine l'est.
    """
    ib = _ib_verrouillee()
    autorisees = ibkr_session.surface_client_autorisee(type(ib.client))
    for nom in sorted(_publics(type(ib.client))):
        if not nom.startswith('cancel') or len(nom) <= len('cancel'):
            continue
        base = nom[len('cancel'):]
        origine_ouverte = (('req' + base) in autorisees
                           or (base[0].lower() + base[1:]) in autorisees)
        bloquee = _est_verrouillee(ib.client, nom)
        assert bloquee is not origine_ouverte, (
            '%s : annulation %s alors que sa requête d\'origine est %s'
            % (nom, 'bloquée' if bloquee else 'ouverte',
               'autorisée' if origine_ouverte else 'interdite'))


def test_une_doublure_de_client_est_verrouillee_comme_la_vraie():
    """Le verrou ne doit pas dépendre de la classe `Client` d'`ib_async` : une
    doublure qui porte une méthode de compte est verrouillée pareillement.
    C'est ce qui rend le gardien utile aux bancs qui n'ouvrent aucune socket.
    """
    journal = []

    class _ClientDouble:
        def connectAsync(self, *a, **k):
            journal.append('connectAsync')

        def isReady(self):
            return True

        def disconnect(self):
            journal.append('disconnect')

        def reqPositions(self):
            journal.append('reqPositions')

        def reqMktData(self, *a, **k):
            journal.append('reqMktData')
            return []

    class _IBDouble:
        def __init__(self):
            self.client = _ClientDouble()

    ib = ibkr_session.verrouiller(_IBDouble())
    with pytest.raises(ibkr_session.FrontiereIbkrError):
        ib.client.reqPositions()
    assert 'reqPositions' not in journal, 'la méthode interdite a tout de même émis'
    ib.client.reqMktData('contrat')
    assert journal == ['reqMktData'], (
        'le marché doit rester ouvert sur la doublure : %r' % journal)
