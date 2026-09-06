# -*- coding: utf-8 -*-
"""tests/test_macro_officiel.py — références macro officielles (FRED, BCE, BNS).

Contrat : chaque série rend une observation DATÉE PAR LA SOURCE, ou une
absence expliquée ; jamais un zéro fabriqué, jamais l'heure du clic comme date
de donnée ; aucune collecte réseau dans une requête HTTP ; la boucle de fond
émet son battement dans le registre des jobs.

Trois niveaux :
1. parseurs et collecte sur FIXTURES RÉELLES capturées le 2026-09-06
   (`tests/fixtures/macro_officiel/`) — aucun réseau ;
2. contrat de la route `/api/macro/officiel` avec le client Flask ;
3. (sur demande, `VERTEX_TEST_RESEAU=1`) une vraie collecte contre les trois
   fournisseurs — jamais comptée comme preuve implicite.
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

import pytest

from vertex.data_sources import macro_officiel as src

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests' / 'fixtures' / 'macro_officiel'

_BCE = {'FM/B.U2.EUR.4F.KR.MRR_FR.LEV': 'MRR', 'FM/B.U2.EUR.4F.KR.DFR.LEV': 'DFR',
        'EXR/D.USD.EUR.SP00.A': 'EURUSD', 'EXR/D.CHF.EUR.SP00.A': 'EURCHF',
        'ICP/M.U2.N.000000.4.ANR': 'HICP'}


_RSS = {'https://www.ecb.europa.eu/rss/press.html': 'bce_press.xml',
        'https://www.snb.ch/public/rss/en/adhoc': 'bns_adhoc.xml'}


def _fetch_fixtures(url, accept):
    if url in _RSS:
        return (FIX / _RSS[url]).read_text(encoding='utf-8')
    for s in src.CATALOGUE:
        if src.url_de(s) != url:
            continue
        if s.fournisseur == 'FRED':
            return (FIX / ('fred_%s.csv' % s.reference)).read_text(encoding='utf-8')
        if s.fournisseur == 'BCE':
            return (FIX / ('bce_%s.json' % _BCE[s.reference])).read_text(encoding='utf-8')
        return (FIX / ('bns_%s.json' % s.reference)).read_text(encoding='utf-8')
    raise KeyError(url)


# ── 1. Parseurs et collecte sur fixtures réelles ────────────────────────────
def test_parser_fred_ignore_les_valeurs_manquantes_et_garde_les_dates():
    pts = src.parser_fred('observation_date,DGS10\n2026-09-01,.\n2026-09-02,4.79\n2026-09-03,4.77\n')
    assert pts == [('2026-09-01', None), ('2026-09-02', 4.79), ('2026-09-03', 4.77)]
    v, d, pv, pd_ = src._derniere_observee(pts)
    assert (v, d, pv, pd_) == (4.77, '2026-09-03', 4.79, '2026-09-02')


def test_parser_bce_rend_les_periodes_dans_l_ordre():
    pts = src.parser_bce((FIX / 'bce_MRR.json').read_text(encoding='utf-8'))
    assert pts and all(re.match(r'^\d{4}-\d{2}', p) for p, _ in pts)
    assert pts == sorted(pts)


def test_parser_bns_selectionne_la_serie_par_son_entete():
    pts = src.parser_bns((FIX / 'bns_zimoma.json').read_text(encoding='utf-8'),
                         'Switzerland - CHF - SARON - 1 day')
    assert pts and re.match(r'^\d{4}-\d{2}$', pts[-1][0])
    with pytest.raises(KeyError):
        src.parser_bns((FIX / 'bns_zimoma.json').read_text(encoding='utf-8'), 'série inexistante')


def test_chaque_serie_du_catalogue_rend_une_observation_datee_par_la_source():
    obs = src.collecter(_fetch_fixtures)
    assert len(obs) == len(src.CATALOGUE)
    for o in obs:
        assert o.error is None, (o.id, o.error)
        assert o.value is not None and o.observed_at, o.id
        assert re.match(r'^\d{4}-\d{2}(-\d{2})?$', o.observed_at), (o.id, o.observed_at)
        assert o.received_at.endswith('Z'), 'heure de réception ISO UTC'
        assert o.observed_at != o.received_at[:10] or o.frequence == 'quotidien'
        assert o.unite and o.frequence in ('quotidien', 'mensuel', 'annuel')
        assert o.mode == 'PERIODIQUE', 'une publication n’est jamais « live »'


def test_une_serie_en_panne_devient_une_absence_expliquee_jamais_un_zero():
    def fetch(url, accept):
        if 'DGS10' in url:
            raise TimeoutError('délai dépassé')
        if 'DFF' in url:
            return 'observation_date,DFF\n2026-09-03,.\n'      # publiée sans valeur
        return _fetch_fixtures(url, accept)
    obs = {o.id: o for o in src.collecter(fetch)}
    assert obs['us_10a'].value is None and 'TimeoutError' in obs['us_10a'].error
    assert obs['us_fed_funds'].value is None and 'aucune observation' in obs['us_fed_funds'].error
    assert obs['us_2a'].value is not None, 'les autres séries vivent'
    for o in obs.values():
        assert o.value != 0 or o.observed_at, 'un zéro ne remplace jamais une absence'


def test_le_catalogue_est_coherent():
    ids = [s.id for s in src.CATALOGUE]
    assert len(ids) == len(set(ids))
    for s in src.CATALOGUE:
        assert s.fournisseur in src.SOURCES
        assert (s.fournisseur != 'BNS') or s.selection, 'une série BNS nomme sa ligne du cube'
        assert src.url_de(s).startswith('https://')


# ── 2. Collecteur et route ──────────────────────────────────────────────────
def test_le_collecteur_expose_un_instantane_date_et_bat_dans_le_registre(monkeypatch, tmp_path):
    from vertex.services import macro_officiel as svc
    from vertex.scheduler import registry as reg
    monkeypatch.setattr(svc, '_racine', lambda: str(tmp_path))
    svc._ETAT.update({'as_of': None, 'series': [], 'runs': 0, 'echecs_consecutifs': 0})
    snap = svc.collecter_une_fois(fetch=_fetch_fixtures)
    assert snap['as_of'] and snap['age_s'] is not None and snap['age_s'] < 120
    assert snap['disponibles'] == snap['total'] == len(src.CATALOGUE)
    assert snap['read_only'] is True and snap['etat']['derniere_erreur'] is None
    assert (tmp_path / svc.CACHE).exists(), 'instantané persisté pour survivre à un redémarrage'
    job = next(j for j in reg.jobs() if j['name'] == svc.JOB)
    assert job['runs'] >= 1 and job['last_ok'] is True and job['etat'] == 'ACTIF'


def test_la_route_sert_l_instantane_sans_collecte_reseau(monkeypatch):
    from vertex.services import macro_officiel as svc
    import terminal
    appels = []
    monkeypatch.setattr(svc, '_fetch', lambda url, accept: appels.append(url) or (_ for _ in ()).throw(RuntimeError('réseau interdit dans une requête')))
    client = terminal.app.test_client()
    r = client.get('/api/macro/officiel')
    assert r.status_code == 200
    d = r.get_json()
    assert set(d) >= {'as_of', 'series', 'sources', 'disponibles', 'total', 'cadence_min', 'read_only'}
    assert appels == [], 'GET ne déclenche aucune collecte'
    assert 'private' in (r.headers.get('Cache-Control') or '')


def test_le_reseau_du_collecteur_refuse_tout_hote_hors_liste_blanche():
    from vertex.services import macro_officiel as svc
    with pytest.raises(PermissionError):
        svc._fetch('https://example.com/x', 'text/csv')
    with pytest.raises(PermissionError):
        svc._fetch('http://169.254.169.254/latest/meta-data', 'text/plain')


def test_le_job_est_declare_implemente_et_le_thread_demarre_hors_demo():
    from vertex.scheduler.registry import NON_IMPLEMENTES
    assert 'MACRO_OFFICIEL_REFRESH' not in NON_IMPLEMENTES
    src_terminal = (ROOT / 'terminal.py').read_text(encoding='utf-8')
    assert '_macro_officiel.demarrer()' in src_terminal
    src_page = (ROOT / 'vertex' / 'ui' / 'pages' / 'markets_page.py').read_text(encoding='utf-8')
    assert 'id="vx-mk-macro-officiel"' in src_page and '/api/macro/officiel' in src_page
    assert 'observé le' in src_page, 'la carte affiche la date de la source, pas l’heure du clic'


# ── 3. Vraie collecte, sur demande seulement ────────────────────────────────
@pytest.mark.skipif(os.environ.get('VERTEX_TEST_RESEAU') != '1',
                    reason='collecte réelle FRED/BCE/BNS : VERTEX_TEST_RESEAU=1')
def test_collecte_reelle_contre_les_trois_fournisseurs():
    from vertex.services import macro_officiel as svc
    obs = src.collecter(svc._fetch)
    ok = [o for o in obs if o.value is not None]
    assert len(ok) >= 8, [(o.id, o.error) for o in obs if o.error]
    assert {o.fournisseur for o in ok} == {'FRED', 'BCE', 'BNS'}
