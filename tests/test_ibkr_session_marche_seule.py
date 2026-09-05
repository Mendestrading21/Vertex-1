# -*- coding: utf-8 -*-
"""tests/test_ibkr_session_marche_seule.py — la session IBKR n'émet QUE du marché.

Mesuré dans `ib_async 2.1.0` (`.venv/Lib/site-packages/ib_async/ib.py`,
`connectAsync`) : `IB.connect(readonly=True)` émet `reqPositions` sans
condition, puis `reqAccountUpdates` / `reqAccountUpdatesMulti` / `reqExecutions`
selon `fetchFields` (défaut ALL). Toutes les connexions de Vertex passaient par
`IB.connect` : l'invariant « IBKR = données de marché uniquement » était violé
au premier instant de chaque session, avant la première cotation, sans qu'aucun
écran ne l'affiche. Ces gardiens sont nés ROUGES sur `main` (ed363d67).

Trois niveaux de preuve :
1. doublure d'`IB` : la connexion n'émet que la poignée de main client ;
2. verrouillage : chaque méthode interdite lève avant toute requête ;
3. statique : plus aucun site du dépôt n'appelle `IB.connect` ; tous passent
   par `ibkr_session.connecter` avec `readonly=True` écrit.
Un quatrième niveau, sur la vraie socket TWS, ne tourne que sur demande
(`VERTEX_TEST_IBKR_LIVE=1`) et n'est jamais compté comme une preuve implicite.
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import pytest

from vertex.data_sources import ibkr_session

ROOT = Path(__file__).resolve().parents[1]


#  Les méthodes d'ordre ne sont pas nommées dans le code produit (gardien
#  test_no_orders) : elles tombent sous le refus par défaut. Le test les nomme.
_ORDRES = ('placeOrder', 'cancelOrder', 'whatIfOrder', 'reqGlobalCancel',
           'reqOpenOrders', 'reqAllOpenOrders', 'reqCompletedOrders',
           'whatIfOrderAsync', 'reqOpenOrdersAsync', 'reqAllOpenOrdersAsync',
           'reqCompletedOrdersAsync')


# ── Doublure d'IB : elle enregistre CHAQUE appel, réseau compris ────────────
class _ClientDouble:
    def __init__(self, journal):
        self._journal = journal
        self._accounts = ['DU000000']       # métadonnée de protocole simulée
        self._ready = False

    async def connectAsync(self, host, port, clientId, timeout=None):
        self._journal.append(('client.connectAsync', host, port, clientId))
        self._ready = True

    def isReady(self):
        return self._ready

    def disconnect(self):
        self._journal.append(('client.disconnect',))
        self._ready = False

    def getAccounts(self):
        self._journal.append(('client.getAccounts',))
        return list(self._accounts)


class _WrapperDouble:
    def __init__(self):
        self.clientId = None
        self.accounts = ['DU000000']
        self.positions = {}
        self.acctSummary = {}


class _IBDouble:
    """Expose les méthodes que `ib_async.IB` expose, toutes journalisées."""

    def __init__(self):
        self.journal = []
        self.wrapper = _WrapperDouble()
        self.client = _ClientDouble(self.journal)
        for nom in ibkr_session.METHODES_INTERDITES + (
                'reqMktData', 'reqHistoricalData', 'qualifyContracts', 'reqMarketDataType'):
            setattr(self, nom, self._journalise(nom))

    def _journalise(self, nom):
        def _f(*a, **k):
            self.journal.append((nom,) + a)
            return []
        _f.__name__ = nom
        return _f

    def _run(self, *awaitables):
        async def _tout():
            return await asyncio.gather(*awaitables)
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_tout())
        finally:
            loop.close()

    def isConnected(self):
        return self.client.isReady()


#  Comme sur `ib_async.IB`, les méthodes d'ordre sont des méthodes de CLASSE :
#  c'est là que le refus par défaut du verrouillage les attrape.
def _methode_de_classe(nom):
    def _f(self, *a, **k):
        self.journal.append((nom,) + a)
        return []
    _f.__name__ = nom
    return _f


for _nom in _ORDRES:
    setattr(_IBDouble, _nom, _methode_de_classe(_nom))


def test_la_connexion_n_emet_que_la_poignee_de_main():
    ib = _IBDouble()
    ibkr_session.connecter(ib, '127.0.0.1', 7496, 29, timeout=1, readonly=True)
    noms = [e[0] for e in ib.journal]
    assert noms == ['client.connectAsync'], (
        'la session a émis autre chose que la poignée de main : %r' % noms)
    assert ib.wrapper.clientId == 29
    assert ibkr_session.est_verrouillee(ib)


def test_aucune_requete_de_compte_pendant_la_connexion():
    ib = _IBDouble()
    ibkr_session.connecter(ib, '127.0.0.1', 7496, 29, timeout=1, readonly=True)
    emis = {e[0] for e in ib.journal}
    for nom in ('reqPositions', 'reqAccountUpdates', 'reqAccountUpdatesMulti',
                'reqExecutions', 'reqOpenOrders', 'reqCompletedOrders',
                'reqAccountSummary', 'reqPnL', 'client.getAccounts'):
        assert nom not in emis, nom


@pytest.mark.parametrize('nom', ibkr_session.METHODES_INTERDITES + _ORDRES)
def test_chaque_methode_interdite_leve_apres_verrouillage(nom):
    ib = _IBDouble()
    ibkr_session.connecter(ib, '127.0.0.1', 7496, 29, timeout=1, readonly=True)
    avant = len(ib.journal)
    with pytest.raises(ibkr_session.FrontiereIbkrError):
        getattr(ib, nom)()
    assert len(ib.journal) == avant, 'la méthode interdite a tout de même émis quelque chose'


def test_refus_par_defaut_sur_une_methode_inconnue_de_la_classe():
    class _IBAvecOrdre(_IBDouble):
        def methodeInconnue(self):
            self.journal.append(('methodeInconnue',))
    ib = _IBAvecOrdre()
    ibkr_session.connecter(ib, '127.0.0.1', 7496, 29, timeout=1, readonly=True)
    with pytest.raises(ibkr_session.FrontiereIbkrError):
        ib.methodeInconnue()
    assert ('methodeInconnue',) not in ib.journal


def test_les_methodes_de_marche_restent_disponibles():
    ib = _IBDouble()
    ibkr_session.connecter(ib, '127.0.0.1', 7496, 29, timeout=1, readonly=True)
    ib.reqMarketDataType(3)
    ib.reqMktData('contrat')
    assert [e[0] for e in ib.journal][-2:] == ['reqMarketDataType', 'reqMktData']


def test_les_identifiants_de_compte_sont_effaces_de_la_session():
    ib = _IBDouble()
    ibkr_session.connecter(ib, '127.0.0.1', 7496, 29, timeout=1, readonly=True)
    assert ib.wrapper.accounts == []
    assert ib.client._accounts == []


def test_client_id_zero_et_readonly_false_sont_refuses():
    with pytest.raises(ValueError):
        ibkr_session.connecter(_IBDouble(), '127.0.0.1', 7496, 0, timeout=1, readonly=True)
    with pytest.raises(ValueError):
        ibkr_session.connecter(_IBDouble(), '127.0.0.1', 7496, 29, timeout=1, readonly=False)


def test_connecter_role_parcourt_les_ports_et_note_le_succes(monkeypatch):
    from vertex.data_sources import ibkr_link
    notes = []
    monkeypatch.setattr(ibkr_link, 'noter_succes', lambda port, role: notes.append(('ok', port, role)))
    monkeypatch.setattr(ibkr_link, 'noter_echec', lambda role, detail='': notes.append(('ko', role)))

    class _ClientCapricieux(_ClientDouble):
        async def connectAsync(self, host, port, clientId, timeout=None):
            self._journal.append(('client.connectAsync', host, port, clientId))
            if port == 7496:
                raise ConnectionRefusedError('port fermé')
            self._ready = True

    ib = _IBDouble()
    ib.client = _ClientCapricieux(ib.journal)
    port = ibkr_session.connecter_role(ib, 'passerelle', timeout=1, ports=(7496, 7497))
    assert port == 7497
    assert notes == [('ok', 7497, 'passerelle')]
    assert [e[0] for e in ib.journal if e[0] != 'client.disconnect'] == \
        ['client.connectAsync', 'client.connectAsync']


# ── Gardien statique : plus aucun `IB.connect` dans le dépôt ────────────────
_SOURCES = ['terminal.py', 'ib_reader.py']


def _py_runtime():
    for p in (ROOT / 'vertex').rglob('*.py'):
        yield p
    for n in _SOURCES:
        yield ROOT / n


def test_aucun_site_n_appelle_plus_ib_connect():
    fautifs = []
    motif = re.compile(r'\.connect\s*\(|\.connectAsync\s*\(')
    for p in _py_runtime():
        if p.name == 'ibkr_session.py':
            continue
        src = p.read_text(encoding='utf-8', errors='ignore')
        for i, line in enumerate(src.splitlines(), 1):
            if motif.search(line) and ('clientId' in line or 'client_id' in line
                                       or 'readonly' in line or 'ibkr' in line.lower()):
                fautifs.append('%s:%d: %s' % (p.relative_to(ROOT), i, line.strip()[:90]))
    assert not fautifs, 'connexion IBKR hors de ibkr_session :\n' + '\n'.join(fautifs)


def test_chaque_site_passe_par_la_session_avec_readonly_ecrit():
    sites = []
    for p in _py_runtime():
        if p.name == 'ibkr_session.py':
            continue
        src = p.read_text(encoding='utf-8', errors='ignore')
        for i, line in enumerate(src.splitlines(), 1):
            if 'ibkr_session.connecter' in line or '_session.connecter' in line:
                fen = ' '.join(src.splitlines()[i - 1:i + 3])
                sites.append((p, i, fen))
    assert sites, 'aucun site ne passe par ibkr_session (gardien aveugle ?)'
    for p, i, fen in sites:
        assert 'readonly=True' in fen, '%s:%d : session sans readonly=True écrit' % (p.relative_to(ROOT), i)


def test_le_lecteur_racine_n_a_plus_de_methode_de_compte():
    src = (ROOT / 'ib_reader.py').read_text(encoding='utf-8')
    for nom in ('accountSummary', 'account_summary', '.positions()', 'def positions'):
        assert nom not in src, 'ib_reader.py porte encore une lecture de compte : %s' % nom


# ── Niveau 4 : vraie socket, uniquement sur demande explicite ───────────────
@pytest.mark.skipif(os.environ.get('VERTEX_TEST_IBKR_LIVE') != '1',
                    reason='preuve sur socket réelle : VERTEX_TEST_IBKR_LIVE=1 avec TWS ouvert')
def test_sur_la_vraie_socket_la_session_ne_detient_aucun_compte():
    from vertex.data_sources import ibkr_gateway
    IB = ibkr_gateway.classe('IB')
    ib = IB()
    port = ibkr_session.connecter_role(ib, 'verification', timeout=6)
    try:
        assert ib.isConnected() and port
        assert ib.wrapper.positions == {} or not ib.wrapper.positions
        assert not getattr(ib.wrapper, 'acctSummary', {})
        assert not getattr(ib.wrapper, 'accountValues', {})
        assert not ib.wrapper.accounts
        with pytest.raises(ibkr_session.FrontiereIbkrError):
            ib.positions()
        ib.reqMarketDataType(3)
        assert ib.reqCurrentTime() is not None
    finally:
        ib.disconnect()
