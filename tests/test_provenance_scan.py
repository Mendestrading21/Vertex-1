"""La provenance du scan n'a qu'UN propriétaire : le scan.

## La mesure qui a ouvert ce banc (6 sept. 2026)

`_download_universe` publie `scan_state['source']`, `source_detail` et
`abandon_debit`. Elle a DEUX appelants : `_scan_once` (533 symboles = 517
titres + 16 de contexte) et `edge_backtest`, lancé toutes les 6 h par
`_edge_loop` avec 141 symboles (140 titres + le benchmark). Les écritures
étaient inconditionnelles, donc le backtest réécrivait la provenance au nom du
scan :

```text
APRES SCAN   source='yfinance'  detail={'yfinance':533,'symboles_demandes':533} scanned_n=513
APRES EDGE   source='yfinance'  detail={'yfinance':141,'symboles_demandes':141} scanned_n=513
edge_backtest a rendu : None      (sous 50 observations — il n'a rien produit)
```

Et, Yahoo bridé pendant le BACKTEST seulement :

```text
APRES SCAN   source='yfinance'    budget_yf='AVAILABLE'  abandon=None
APRES EDGE   source='unavailable' budget_yf='UNAVAILABLE'
             abandon_debit publié AU NOM DU SCAN :
             {'restes_sans_donnee': 41,
              'exemples': ['CAT','BA','HON','GE','RTX','LMT','DE','MMM']}
```

## Pourquoi c'est un défaut d'honnêteté et pas de cosmétique

`scan_state['source']` n'alimente pas qu'un compteur de diagnostic : il est lu
par `/healthz`, `scan_api`, `positions/recalculator` (`data_quality.overall` et
`actionable_allowed`), `decision_packet`, `daily_brief` et le badge
« live / delayed » des pages. Le relevé ci-dessus montre donc une DÉGRADATION
FAUSSE affichée sur un scan de 513 lignes parfaitement saines, jusqu'à ~30 min
toutes les 6 h. Et `abandon_debit` nommait CAT, BA, HON, GE, RTX « restés sans
donnée » alors que le scan venait de les servir : une ABSENCE FABRIQUÉE, ce que
ce bloc avait précisément été écrit pour empêcher.

Le dépôt connaissait déjà la fuite sans la corriger :
`tests/test_strangler_stooq.py` la contourne par `monkeypatch.setitem` et
raconte qu'elle a réellement fait échouer `test_tracking_api` en suite.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import terminal  # noqa: E402

#: Tickers volontairement improbables : ce banc écrit dans le `scan_state` et
#: le cache partagés du processus de test ; il ne doit croiser aucun symbole
#: qu'un autre banc double ou attend.
_SCAN = ['ZZTESTA', 'ZZTESTB', 'ZZTESTC']


def _serie(n: int = 300) -> pd.DataFrame:
    idx = pd.bdate_range('2023-01-02', periods=n)
    return pd.DataFrame({'Close': np.linspace(100.0, 120.0, n)}, index=idx)


class _Vide:
    """Ce que rend yfinance quand Yahoo bride le débit : `len(dl) == 0`."""

    def __len__(self):
        return 0


@pytest.fixture
def etat_isole(monkeypatch):
    """Restaure la provenance partagée après le banc — cf. la fuite mesurée
    dans `tests/test_strangler_stooq.py` (verte en isolé, rouge en suite)."""
    for cle in ('source', 'source_detail', 'abandon_debit'):
        monkeypatch.setitem(terminal.scan_state, cle, terminal.scan_state.get(cle))
    monkeypatch.setitem(terminal._SOURCE_BUDGET_STATE, 'yfinance',
                        terminal._SOURCE_BUDGET_STATE.get('yfinance'))
    monkeypatch.setattr(terminal, 'IBKR_ENABLED', False)
    monkeypatch.setattr(terminal, '_stooq_download', lambda tickers: {})
    return monkeypatch


def test_le_backtest_ne_reecrit_pas_la_provenance_du_scan(etat_isole):
    """Le scan publie, le backtest se tait — même quand le backtest échoue.

    Reproduction fidèle de la mesure : un scan sain, puis un backtest pendant
    lequel Yahoo ne répond plus. Avant correction, la seconde phase laissait
    `source='unavailable'` et un `abandon_debit` derrière elle, au nom d'un
    scan qui n'avait rien perdu.
    """
    monkeypatch = etat_isole
    monkeypatch.setattr(terminal.yf, 'download',
                        lambda tickers, **kw: {t: _serie() for t in tickers})
    terminal._download_universe(list(_SCAN))
    apres_scan = (terminal.scan_state['source'],
                  dict(terminal.scan_state['source_detail']),
                  terminal.scan_state['abandon_debit'])
    assert apres_scan[0] == 'yfinance'
    #  'univers' -> 'symboles_demandes' : la clé compte les symboles DEMANDÉS
    #  à la file (533 en production), pas l'univers servi (`universe_n`, 517)
    #  ni le scanné (`scanned_n`, 513). Trois dénominateurs justes, un seul mot.
    assert apres_scan[1] == {'ibkr': 0, 'yfinance': 3, 'stooq': 0,
                             'symboles_demandes': 3}

    #  Le backtest, avec Yahoo muet : la population (3 symboles + le benchmark)
    #  et le verdict de source seraient publiés au nom du scan.
    appels: list[list] = []

    def _yahoo_muet(tickers, **kw):
        appels.append(list(tickers))
        return _Vide()

    monkeypatch.setattr(terminal.yf, 'download', _yahoo_muet)
    assert terminal.edge_backtest(syms=['ZZTESTA', 'ZZTESTB']) is None
    assert appels, (
        'DÉNOMINATEUR : le backtest n’a rien téléchargé (edge_backtest avale '
        'les exceptions de `telecharger` et rend None) — ce banc ne mesurerait '
        'plus rien')

    assert (terminal.scan_state['source'],
            dict(terminal.scan_state['source_detail']),
            terminal.scan_state['abandon_debit']) == apres_scan, (
        'le backtest a réécrit la provenance du scan : la source servie avec '
        'les 513 lignes du scan décrit alors une AUTRE population (141 '
        'symboles), et rien à l’écran ne dit qu’elle vient d’un autre lot')


def test_un_abandon_du_backtest_n_invente_pas_une_absence_dans_le_scan(etat_isole):
    """CAT, BA, HON, GE, RTX étaient nommés « restés sans donnée » par le
    backtest alors que le scan venait de les servir. Ici : le scan sert les
    trois titres, puis le backtest abandonne les siens après trois lots vides.
    `abandon_debit` doit rester celui du scan — c'est-à-dire `None`."""
    monkeypatch = etat_isole
    monkeypatch.setattr(terminal.yf, 'download',
                        lambda tickers, **kw: {t: _serie() for t in tickers})
    terminal._download_universe(list(_SCAN))
    assert terminal.scan_state['abandon_debit'] is None, 'scan sain : rien à avouer'

    monkeypatch.setattr(terminal.yf, 'download', lambda tickers, **kw: _Vide())
    monkeypatch.setattr(terminal.time, 'sleep', lambda _s: None)   # backoff : 6 s
    #  chunk=1 : trois lots vides d'affilée déclenchent l'abandon de la file.
    terminal._download_universe(['ZZEDGE1', 'ZZEDGE2', 'ZZEDGE3', 'ZZEDGE4'],
                                chunk=1, publier_provenance=False)
    assert terminal.scan_state['abandon_debit'] is None, (
        'un abandon survenu HORS du scan est publié sous l’étiquette du scan : '
        'Vertex nomme alors des titres « restés sans donnée » que le scan a '
        'servis — une absence fabriquée')
    assert terminal.scan_state['source'] == 'yfinance', (
        'la provenance du scan a été rétrogradée par un téléchargement qui '
        'n’est pas le sien')


def test_le_scan_publie_toujours_sa_provenance(etat_isole):
    """Contre-épreuve : un garde trop large rendrait la provenance muette, ce
    qui est le défaut inverse — plus aucun repli visible."""
    monkeypatch = etat_isole
    monkeypatch.setattr(terminal.yf, 'download', lambda tickers, **kw: _Vide())
    monkeypatch.setattr(terminal, '_stooq_download',
                        lambda tickers: {t: _serie() for t in tickers})
    terminal._download_universe(['ZZONLY1', 'ZZONLY2'])
    assert terminal.scan_state['source'] == 'stooq', (
        'le repli Stooq doit rester NOMMÉ : un repli invisible est un mensonge '
        'de source')
    assert terminal.scan_state['source_detail']['stooq'] == 2


def test_yahoo_jamais_interroge_n_est_pas_yahoo_en_panne(etat_isole):
    """Une SOURCE NON INTERROGÉE n'est pas une source indisponible.

    MESURE (doublures en mémoire, IBKR sert tout l'univers) :

    ```text
    avant : manquants=[]  boucle yfinance non exécutée  yahoo_n=0
            _SOURCE_BUDGET_STATE['yfinance'] = 'UNAVAILABLE'
            → source_health.yfinance_budget = 'UNAVAILABLE'
            → carte « Pannes en cours » : « Source yfinance_budget · source
              indisponible » — une panne INVENTÉE, sur la carte dont la
              fonction déclarée est de dire ce qui bloque la décision
    après : 'NOT_COLLECTED' — « non collectée lors de ce scan » (libellé déjà
            servi et déjà traduit par la page)
    ```

    Invariant 5 : absence, zéro et dégradation restent distincts. Une vraie
    panne de Yahoo se noierait parmi les fausses.
    """
    monkeypatch = etat_isole
    monkeypatch.setattr(terminal, 'IBKR_ENABLED', True)
    monkeypatch.setattr(terminal, 'DEMO_MODE', False)

    from vertex.data_sources import ibkr_historical as _hist
    monkeypatch.setattr(_hist, 'fetch_universe_bars',
                        lambda tickers, **kw: ({t: _serie() for t in tickers}, {}))

    def _yahoo_interdit(tickers, **kw):      # DÉNOMINATEUR : si Yahoo est
        raise AssertionError(               # appelé, le banc ne mesure pas
            'yfinance interrogé alors qu’IBKR a tout servi : %s' % (tickers,))

    monkeypatch.setattr(terminal.yf, 'download', _yahoo_interdit)
    terminal._download_universe(list(_SCAN))

    assert terminal.scan_state['source'] == 'ibkr'
    assert terminal._SOURCE_BUDGET_STATE['yfinance'] == 'NOT_COLLECTED', (
        'yfinance est déclaré « %s » sans avoir été interrogé une seule fois : '
        'la page Système affiche une panne que rien ne mesure'
        % terminal._SOURCE_BUDGET_STATE['yfinance'])
