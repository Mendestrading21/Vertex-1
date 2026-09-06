"""Lot J-routes-api — UNE ABSENCE SERVIE DOIT ÊTRE UNE MESURE, PAS UNE HYPOTHÈSE.

## Le défaut, mesuré le 2026-09-06 (`app.test_client()`, NO_IBKR=1, DEMO=0)

Trois routes du dossier options servaient la MÊME phrase fixe, quelle que soit
la situation réelle :

```json
{"symbol": "AAPL", "available": false,
 "note": "Chaîne large indisponible (TWS fermé, hors séance, ou titre pas
          encore chargé)."}
```

Trois causes annoncées, **zéro mesurée**. Relevés du même jour, même processus :

  · `IBKR_ENABLED` valait `False` — la source de la chaîne large était coupée
    par la configuration. Aucun socket TWS n'a été ouvert, donc « TWS fermé »
    n'était pas un constat ; aucun calendrier de séance n'a été lu, donc
    « hors séance » non plus.
  · `chaine_a_la_demande.prechauffer('AAPL')` rendait
    `{'etat': 'MISSING', 'chargement_en_cours': True}` au premier appel puis
    `{'etat': 'LIVE', 'chargement_en_cours': False}` une seconde plus tard :
    DEUX états distincts, racontés par la même phrase. Sa docstring dit
    pourtant « rend l'état, pour que l'appelant puisse le joindre à sa réponse
    au lieu d'avaler l'échec » — les trois routes jetaient ce retour.
  · `scan_state['chaine_non_persistee']`, posé par `terminal.py` quand une
    chaîne reçue ne peut pas être enregistrée, n'était lu par personne.

La phrase n'était pas cosmétique : `options-symbol.js` rend `d.note` tel quel
sur `/options/dossier/<sym>`. L'utilisateur lisait donc une cause inventée.

## Ce que ce banc garde

Que les quatre situations restent DISCERNABLES dans la charge servie, et que
la réponse ne nomme jamais un état que le processus n'a pas observé. Il ne fige
aucune phrase : il pilote les quatre branches et vérifie qu'elles rendent
quatre motifs différents.

## `/api/options/event-risk/<sym>` — deux entrées sans écrivain

Mesuré sur une charge `/scan` réelle (513 titres, instance de contrôle) : une
entrée de `scan_state['detail']` porte 66 clés, et **aucune** des 513 ne porte
`earnings_in_days` ni `ex_dividend_days` (la seule clé contenant « div » est
`rsi_div`). Balayage du dépôt : aucun écrivain non plus. La route recevait donc
`None` à chaque appel et servait « Dates d'événement inconnues » — une phrase
qui se lit comme « le calendrier est vide » alors qu'aucun calendrier n'a été
lu. Entrée non câblée et absence mesurée sont deux états distincts.

## `/api/options/simulate` — le texte d'exception servi

Mesuré avant correctif : `?sym=AAPL&spot=100&strike=0&dte=30&mid=5` rendait
`422 {"error": "simulation impossible: float division by zero"}`, et
`&iv=99999` rendait `"math domain error"`. Deux messages de la bibliothèque
standard, en anglais, servis comme état.
"""
from __future__ import annotations

import json

import pytest
from flask import Flask

from vertex.app.routes import options_intel_api as oia
from vertex.app.state import scan_state


#: Vocabulaire de causes que ces routes ne mesurent JAMAIS. Elles n'ouvrent
#: aucun socket courtier et ne lisent aucun calendrier de séance : nommer l'un
#: de ces états serait une affirmation sans observation. La liste reste courte
#: et motivée — ce n'est pas un filtre de style, c'est la frontière de ce que
#: le code peut constater.
_CAUSES_NON_MESUREES = ('TWS', 'hors séance', 'hors seance')

_CLES_ETAT = ('options_chain_full', 'chaine_non_persistee', 'options_view_cache',
              'options_board', 'detail', 'options_as_of', 'scan_ts')


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(oia.bp)
    return app.test_client()


@pytest.fixture(autouse=True)
def etat_propre():
    """L'état partagé est un dict de processus : sans remise à zéro, l'ordre de
    collecte déciderait du résultat."""
    avant = {k: scan_state.get(k) for k in _CLES_ETAT}
    for k in _CLES_ETAT:
        scan_state.pop(k, None)
    yield
    for k, v in avant.items():
        if v is None:
            scan_state.pop(k, None)
        else:
            scan_state[k] = v


def _prechauffage(monkeypatch, **etat):
    """Fige l'état de collecte rendu par `prechauffer` — et, au passage, empêche
    le banc de déclencher une vraie collecte réseau."""
    base = {'symbole': 'AAPL', 'contrats': 0, 'etat': 'LIVE',
            'chargement_en_cours': False, 'erreur': None}
    base.update(etat)
    monkeypatch.setattr(oia._chaine, 'prechauffer', lambda sym: dict(base))


def _source(monkeypatch, *, ibkr=False, demo=False):
    monkeypatch.setattr(oia, 'IBKR_ENABLED', ibkr)
    monkeypatch.setattr(oia, 'DEMO_MODE', demo)


_VUES = ('/api/options/max-pain/AAPL', '/api/options/chain-grid/AAPL',
         '/api/options/surface/AAPL')


# ── 1. Aucune cause n'est affirmée sans mesure ──────────────────────────────

@pytest.mark.parametrize('route', _VUES)
def test_aucune_cause_non_mesuree_dans_la_charge_servie(client, monkeypatch, route):
    """SANS le correctif, les trois routes rendaient « TWS fermé, hors séance »
    alors qu'aucun socket TWS n'avait été ouvert et qu'aucune séance n'avait été
    lue. Ce banc échoue sur cette charge-là."""
    _source(monkeypatch, ibkr=False, demo=False)
    _prechauffage(monkeypatch)
    corps = client.get(route).get_data(as_text=True)
    presentes = [c for c in _CAUSES_NON_MESUREES if c in corps]
    assert presentes == [], (
        '%s affirme une cause que la route ne mesure pas (%s) — extrait : %s'
        % (route, presentes, corps[:220]))


@pytest.mark.parametrize('route', _VUES)
def test_la_source_annoncee_suit_la_configuration_REELLE(client, monkeypatch, route):
    """`source_activee` n'est pas un texte : c'est la conjonction mesurée de
    `IBKR_ENABLED` et `DEMO_MODE`, les deux seuls écrivains de
    `options_chain_full` dans le dépôt."""
    for ibkr, demo, attendu in ((False, False, False), (True, False, True),
                                (False, True, True)):
        _source(monkeypatch, ibkr=ibkr, demo=demo)
        _prechauffage(monkeypatch)
        j = client.get(route).get_json()
        assert j['available'] is False
        assert j['source_activee'] is attendu, (
            '%s : source_activee=%r avec IBKR_ENABLED=%r DEMO_MODE=%r'
            % (route, j['source_activee'], ibkr, demo))


# ── 2. Les quatre situations restent DISCERNABLES ───────────────────────────

def test_les_quatre_motifs_sont_distincts(client, monkeypatch):
    """Une seule phrase pour quatre états, c'est une phrase qui n'informe pas.
    Chaque branche est pilotée par une mesure différente et doit rendre un
    motif différent — et un motif seul, jamais deux à la fois."""
    motifs = {}

    _source(monkeypatch, ibkr=True, demo=False)
    _prechauffage(monkeypatch, chargement_en_cours=True, etat='MISSING')
    j = client.get('/api/options/max-pain/AAPL').get_json()
    motifs['collecte en cours'] = j['raison']
    assert j['chargement_en_cours'] is True and j['retry_s'] == 8, (
        'une collecte en cours doit inviter à réessayer, pas se taire : %r' % j)

    _source(monkeypatch, ibkr=True, demo=False)
    _prechauffage(monkeypatch)
    scan_state['chaine_non_persistee'] = {
        'AAPL': {'echeance': '20261218', 'cote': 'C', 'erreur': 'OSError: disque plein'}}
    j = client.get('/api/options/max-pain/AAPL').get_json()
    motifs['persistance échouée'] = j['raison']
    assert j['collecte_en_erreur'] is True
    scan_state.pop('chaine_non_persistee', None)

    _source(monkeypatch, ibkr=False, demo=False)
    _prechauffage(monkeypatch)
    motifs['source coupée'] = client.get('/api/options/max-pain/AAPL').get_json()['raison']

    _source(monkeypatch, ibkr=True, demo=False)
    _prechauffage(monkeypatch)
    motifs['collecte vide'] = client.get('/api/options/max-pain/AAPL').get_json()['raison']

    assert len(set(motifs.values())) == 4, (
        'quatre situations mesurées, %d motif(s) servi(s) : %r'
        % (len(set(motifs.values())), motifs))


def test_le_detail_de_l_exception_ne_franchit_pas_la_frontiere_HTTP(client, monkeypatch):
    """`Meta.erreur` (snapshot.py) et `chaine_non_persistee['erreur']` portent
    tous deux `'%s: %s' % (type(exc).__name__, exc)`. Servir le motif d'échec
    est juste ; servir sa formulation Python ne l'est pas."""
    _source(monkeypatch, ibkr=True, demo=False)
    _prechauffage(monkeypatch, erreur='TimeoutError: le courtier ne répond pas')
    scan_state['chaine_non_persistee'] = {
        'AAPL': {'echeance': '20261218', 'cote': 'C',
                 'erreur': 'PermissionError: [Errno 13] refuse'}}
    corps = client.get('/api/options/surface/AAPL').get_data(as_text=True)
    for signature in ('TimeoutError', 'PermissionError', 'Errno'):
        assert signature not in corps, (
            'texte d’exception servi (%s) : %s' % (signature, corps[:220]))
    assert json.loads(corps)['collecte_en_erreur'] is True, (
        'le FAIT de l’échec doit rester servi, seul son libellé Python part'
    )


def test_une_chaine_presente_reste_servie_normalement(client, monkeypatch):
    """Dénominateur : si ces routes ne servaient plus rien, l'honnêteté du vide
    serait vraie pour rien."""
    _source(monkeypatch, ibkr=True, demo=False)
    _prechauffage(monkeypatch)
    scan_state['options_chain_full'] = {'AAPL': {
        'spot': 200.0, 'ts': 1788700000.0,
        '20261218': {'C': {195.0: {'oi': 10, 'iv': 0.3}, 200.0: {'oi': 40, 'iv': 0.28},
                           205.0: {'oi': 15, 'iv': 0.31}},
                     'P': {195.0: {'oi': 20, 'iv': 0.33}, 200.0: {'oi': 30, 'iv': 0.29},
                           205.0: {'oi': 5, 'iv': 0.30}}}}}
    j = client.get('/api/options/max-pain/AAPL').get_json()
    assert j['available'] is True and j['expiries'], j
    assert j['expiries'][0]['max_pain'] is not None


# ── 3. event-risk : entrée non câblée ≠ absence mesurée ─────────────────────

def test_event_risk_distingue_non_cablee_absente_et_mesuree(client, monkeypatch):
    """Trois états, trois libellés. SANS le correctif, la route servait le même
    `status: INCONNU` sans jamais dire que deux de ses quatre entrées n'ont
    aucun écrivain dans le dépôt."""
    _prechauffage(monkeypatch)
    scan_state['options_board'] = []
    scan_state['detail'] = {}
    j = client.get('/api/options/event-risk/AAPL').get_json()
    assert j['entrees_statut']['earnings_in_days'] == 'NON_CABLEE'
    assert j['entrees_statut']['ex_dividend_days'] == 'NON_CABLEE'
    #  `right`/`dte` viennent du board, pas de `detail` : leur absence EST une
    #  mesure (aucun contrat noté), et les confondre serait le défaut inverse.
    assert j['entrees_statut']['dte'] == 'AUCUN_CONTRAT'
    assert 'earnings_in_days' in j['entrees_non_cablees']

    #  Un autre titre porte la clé → pour AAPL ce n'est plus « non câblée »
    #  mais « absente », et la différence doit se voir.
    scan_state['detail'] = {'MSFT': {'earnings_in_days': 4}}
    j = client.get('/api/options/event-risk/AAPL').get_json()
    assert j['entrees_statut']['earnings_in_days'] == 'ABSENTE'
    assert 'earnings_in_days' not in j['entrees_non_cablees']

    #  Entrées réellement mesurées → plus aucune réserve de câblage, et le
    #  moteur peut rendre autre chose qu'INCONNU.
    scan_state['detail'] = {'AAPL': {'earnings_in_days': 3, 'ex_dividend_days': 9}}
    scan_state['options_board'] = [{'sym': 'AAPL', 'type': 'CALL', 'dte': 21,
                                    'quality': 80}]
    j = client.get('/api/options/event-risk/AAPL').get_json()
    assert j['entrees_non_cablees'] == []
    assert j['interpretation']['status'] != 'INCONNU', j['interpretation']
    assert not [x for x in (j['interpretation'].get('limitations') or [])
                if 'non câblées' in x]


def test_event_risk_avoue_le_cablage_manquant_DANS_l_interpretation(client, monkeypatch):
    """L'écran ne lit que `d.interpretation` (`options-intel.js`) : un aveu qui
    ne vivrait qu'à côté ne serait jamais montré."""
    _prechauffage(monkeypatch)
    scan_state['detail'] = {}
    scan_state['options_board'] = []
    interp = client.get('/api/options/event-risk/AAPL').get_json()['interpretation']
    assert [x for x in (interp.get('limitations') or []) if 'non câblées' in x], (
        'la réserve de câblage n’atteint pas la carte servie : %r' % interp)
    #  Le contrat de `/api/charts/<id>/interpretation` passe par la même vue.
    autre = client.get(
        '/api/charts/options.event_risk/interpretation?sym=AAPL').get_json()
    assert autre['chart_id'] == 'options.event_risk'
    assert autre['limitations'] == interp['limitations']


# ── 4. Contrôle adverse : deux branches qui affirmaient sans mesurer ────────
#
#  Ajoutées au contrôle du lot J-routes-api. Le correctif du lot avait remplacé
#  une cause inventée par une autre, à cause de l'ORDRE des branches et d'un
#  état non discriminé.


def test_source_coupee_ne_promet_pas_un_rechargement(client, monkeypatch):
    """`chargement_en_cours` ne mesure PAS la chaîne large.

    Il vient du magasin d'instantanés du board ÉTROIT (`prechauffer` →
    `on_demand.fetch` → `legacy_engine.best_for_symbol`). Ce chargement ne
    remplit `options_chain_full` que par la passerelle IBKR substituée dans
    `legacy_engine.yf` (`terminal.py:1571`) : source coupée, il passe par
    yfinance et n'écrira jamais la chaîne large.

    MESURE du 2026-09-06 sur l'instance de contrôle (5003, `NO_IBKR=1`),
    PREMIER appel sur trois titres froids — ZTS, PAYX, CDW — les trois routes
    rendaient `raison: CHARGEMENT_EN_COURS`, `retry_s: 8`, « rechargez dans
    quelques secondes », avec `source_activee: false` dans LA MÊME charge.
    Charge contradictoire, et promesse qu'aucune configuration ne peut tenir.
    Après correctif : `SOURCE_DESACTIVEE`, `retry_s: None`.
    """
    for route in _VUES:
        _source(monkeypatch, ibkr=False, demo=False)
        _prechauffage(monkeypatch, chargement_en_cours=True, etat='MISSING')
        j = client.get(route).get_json()
        assert j['source_activee'] is False
        assert j['raison'] == 'SOURCE_DESACTIVEE', (
            '%s : source coupée mais motif %r — la charge se contredit'
            % (route, j['raison']))
        assert j['retry_s'] is None, (
            '%s promet un rechargement dans %r s alors que la source de la '
            'chaîne large est coupée : rien ne peut arriver'
            % (route, j['retry_s']))
        assert 'rechargez' not in j['note'].lower(), (
            '%s invite à réessayer sans qu’un réessai puisse aboutir : %s'
            % (route, j['note']))


def test_une_collecte_JAMAIS_enregistree_ne_se_dit_pas_ABOUTIE(client, monkeypatch):
    """« personne ne l'a » et « les autres l'ont, pas celui-ci » sont deux états.

    C'est la discrimination que la route event-risk applique déjà à ses entrées
    (`NON_CABLEE` vs `ABSENTE`) ; elle manquait ici. MESURE avant correctif,
    source ACTIVE et `scan_state['options_chain_full']` absent — l'état d'un
    processus qui démarre, avant la première rotation : la route servait « la
    collecte de la chaîne large de AAPL A ABOUTI sans aucun contrat », donc un
    résultat de collecte là où aucune collecte n'avait rien enregistré, pour
    aucun titre. Les deux situations rendaient la MÊME phrase.
    """
    _source(monkeypatch, ibkr=True, demo=False)
    _prechauffage(monkeypatch)
    scan_state.pop('options_chain_full', None)
    vierge = client.get('/api/options/max-pain/AAPL').get_json()
    assert vierge['raison'] == 'AUCUNE_COLLECTE_ENREGISTREE', vierge
    assert 'abouti' not in vierge['note'], (
        'rien n’a été enregistré, et la charge parle d’une collecte aboutie : %s'
        % vierge['note'])

    #  Un AUTRE titre a bien une chaîne large → pour AAPL, l'absence devient
    #  une mesure, et elle doit se dire autrement.
    scan_state['options_chain_full'] = {'MSFT': {'spot': 1.0, 'ts': 1.0}}
    mesuree = client.get('/api/options/max-pain/AAPL').get_json()
    assert mesuree['raison'] == 'AUCUN_CONTRAT_COLLECTE', mesuree
    assert mesuree['raison'] != vierge['raison'], (
        'deux états distincts, un seul motif servi : %r' % mesuree)
