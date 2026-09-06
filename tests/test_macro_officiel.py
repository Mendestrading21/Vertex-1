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
        #  `en vigueur` ajouté après mesure : voir
        #  `test_un_taux_directeur_n_est_jamais_marque_en_retard`.
        assert o.unite and o.frequence in ('quotidien', 'mensuel', 'annuel',
                                           src.FREQ_EN_VIGUEUR)
        assert o.mode == 'PERIODIQUE', 'une publication n’est jamais « live »'
        #  L'observation ne PORTE plus de verdict : il dépend de l'heure de
        #  LECTURE, pas de celle de la collecte (voir
        #  `test_le_verdict_de_fraicheur_est_rejuge_a_la_lecture_et_jamais_persiste`).
        assert not hasattr(o, 'fraicheur') and not hasattr(o, 'retard_jours')
    for s in src.juger_series([o.to_dict() for o in obs]):
        assert s['fraicheur'] in ('SANS_OBJET', 'A_JOUR', 'RETARD', 'RETARD_FORT'), s['id']


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


# ── 1 bis. Verdict de fraîcheur (calculé au serveur, jamais déduit à l'écran) ─
def test_juger_fraicheur_distingue_a_jour_retard_et_retard_fort():
    """MESURE (2026-09-06) : `/api/macro/officiel` servait 16 clés par série,
    aucune ne portant de verdict de fraîcheur — `retard` n'existait nulle part
    dans la chaîne, alors que le contrat exige qu'il reste un état DISTINCT de
    l'absence. Le même gabarit de tuile rendait le SARON de 2026-08 (à jour)
    et le rendement Confédération 10 ans arrêté à 2025-07 chez la BNS, soit
    14 publications mensuelles manquantes ; l'IPCH zone euro s'arrêtait à
    2025-12, soit 9 manquantes. Le pied affichait « 11/11 séries publiées ».

    Le mensuel se compte depuis la FIN du mois observé : un chiffre de
    décembre n'a pas 279 jours de retard parce qu'il porte le 1er décembre."""
    import datetime as _dt
    j = _dt.date(2026, 9, 6)
    assert src.juger_fraicheur('quotidien', '2026-09-03', j) == ('A_JOUR', 3)
    assert src.juger_fraicheur('mensuel', '2026-08', j) == ('A_JOUR', 6)      # ch_saron
    assert src.juger_fraicheur('mensuel', '2025-12', j) == ('RETARD_FORT', 249)  # ze_inflation
    assert src.juger_fraicheur('mensuel', '2025-07', j) == ('RETARD_FORT', 402)  # ch_conf_10a
    assert src.juger_fraicheur('quotidien', '2026-08-25', j) == ('RETARD', 12)
    #  Rien d'inventé quand on ne sait pas : ni verdict, ni âge.
    assert src.juger_fraicheur('quotidien', '', j) == ('INCONNU', None)
    assert src.juger_fraicheur('trimestriel', '2026-06', j) == ('INCONNU', 68)


def test_un_taux_directeur_n_est_jamais_marque_en_retard():
    """MESURE : `FM/B.U2.EUR.4F.KR.MRR_FR.LEV` rend [('2025-04-23', 2.4),
    ('2025-06-11', 2.15), ('2026-06-17', 2.4)] — un escalier de DÉCISIONS, pas
    une série quotidienne. Les 2,40 % du 2026-06-17 sont le taux EN VIGUEUR
    aujourd'hui : un badge « 81 jours de retard » y serait un mensonge. C'est
    l'étiquette `frequence='quotidien'` qui était fausse, pas la valeur."""
    import datetime as _dt
    verdict, jours = src.juger_fraicheur(src.FREQ_EN_VIGUEUR, '2026-06-17', _dt.date(2026, 9, 6))
    assert (verdict, jours) == ('SANS_OBJET', 81), 'âge servi, retard non affirmé'
    cat = {s.id: s for s in src.CATALOGUE}
    assert cat['ze_refi'].frequence == cat['ze_depot'].frequence == src.FREQ_EN_VIGUEUR
    #  Date figée : sinon le verdict des séries quotidiennes de la fixture
    #  changerait tout seul en dormant cinq jours.
    obs = {s['id']: s for s in src.juger_series(
        [o.to_dict() for o in src.collecter(_fetch_fixtures)], _dt.date(2026, 9, 6))}
    assert obs['ze_refi']['fraicheur'] == 'SANS_OBJET' and obs['ze_refi']['value'] is not None
    #  Le champ s'appelle `age_jours` et NON `retard_jours` : il vaut 81 sur une
    #  série dont le verdict est SANS_OBJET (taux directeur EN VIGUEUR). Un écran
    #  qui lirait « retard_jours » sans lire « fraicheur » afficherait
    #  « 81 jours de retard » sur le taux courant — le mensonge exact que ce
    #  module existe pour empêcher.
    assert obs['ze_refi']['age_jours'] == 81
    assert 'retard_jours' not in obs['ze_refi'], 'le nom qui mentait est retiré'
    assert obs['ch_conf_10a']['fraicheur'] == 'RETARD_FORT', 'retard de la SOURCE, dit'
    assert [s['id'] for s in obs.values() if s['fraicheur'] in ('RETARD', 'RETARD_FORT')] == \
        ['ze_inflation', 'ch_conf_10a']


def test_l_instantane_compte_les_series_en_retard_a_cote_des_disponibles(monkeypatch, tmp_path):
    """« 11/11 séries publiées » ne parlait que de DISPONIBILITÉ (`value is not
    None`) : deux séries en retard fort s'y comptaient comme les autres. Le
    compte des retards est servi à côté, sans changer le premier."""
    from vertex.services import macro_officiel as svc
    monkeypatch.setattr(svc, '_racine', lambda: str(tmp_path))
    monkeypatch.setattr(svc, '_battre', lambda *a, **k: None)
    monkeypatch.setattr(svc, '_publier', lambda: None)
    snap = svc.collecter_une_fois(_fetch_fixtures)
    assert snap['disponibles'] == snap['total'] == len(src.CATALOGUE)
    en_retard = [s['id'] for s in snap['series'] if s['fraicheur'] in ('RETARD', 'RETARD_FORT')]
    assert snap['en_retard'] == len(en_retard) >= 2, 'le compte du pied suit les séries'
    #  Les deux retards sont ceux de la SOURCE, figés dans la fixture ; les
    #  séries quotidiennes, elles, vieillissent avec l'horloge de la machine.
    assert {'ze_inflation', 'ch_conf_10a'} <= set(en_retard)
    assert all('fraicheur' in s and 'age_jours' in s for s in snap['series'])
    assert next(s for s in snap['series'] if s['id'] == 'ze_refi')['fraicheur'] == 'SANS_OBJET'


def test_le_verdict_de_fraicheur_est_rejuge_a_la_lecture_et_jamais_persiste(monkeypatch, tmp_path):
    """MESURE DU 2026-09-06 — la fraîcheur rassissait en silence.

    `fraicheur`/`retard_jours` étaient calculés UNE fois dans `observer()`,
    écrits dans la série, persistés par `_sauver()` puis réhydratés tels quels
    par `charger_cache()`. Relevé dans le `macro_officiel_cache.json` réel de
    ce jour-là : `ch_saron` figé à `A_JOUR` / 6 j et `us_10a` à `A_JOUR` / 3 j.
    Rejugées au 2026-11-15 sur le MÊME `observed_at` : `RETARD` 76 j et
    `RETARD_FORT` 73 j. Sur le chemin de reprise depuis cache (sources
    injoignables au démarrage), l'API affirmait donc « à jour » sur une donnée
    qui ne l'était plus.

    Ce banc rejoue ce chemin : un cache PORTEUR d'un verdict périmé est
    réhydraté, et l'instantané servi doit contredire le cache. Sans le recalcul
    dans `snapshot()`, il rendrait `A_JOUR`.
    """
    import json as _json
    from vertex.services import macro_officiel as svc
    monkeypatch.setattr(svc, '_racine', lambda: str(tmp_path))
    (tmp_path / svc.CACHE).write_text(_json.dumps({
        'as_of': '2026-01-08T06:00:00Z',
        'series': [{'id': 'us_10a', 'libelle': 'Trésor US 10 ans', 'frequence': 'quotidien',
                    'value': 4.77, 'observed_at': '2026-01-05', 'error': None,
                    'fraicheur': 'A_JOUR', 'retard_jours': 3},
                   {'id': 'ze_refi', 'libelle': 'BCE — refinancement',
                    'frequence': src.FREQ_EN_VIGUEUR, 'value': 2.4,
                    'observed_at': '2026-06-17', 'error': None,
                    'fraicheur': 'RETARD_FORT', 'retard_jours': 81}],
        'communiques': []}, ensure_ascii=False), encoding='utf-8')
    etat_avant = dict(svc._ETAT)
    svc.charger_cache()
    try:
        snap = svc.snapshot()
        series = {s['id']: s for s in snap['series']}
        assert snap['etat']['restaure_depuis_cache'] is True
        #  Le cache DIT « A_JOUR » ; l'observation date du 2026-01-05, soit bien
        #  au-delà des 5 jours de tolérance quotidienne — et le test ne peut que
        #  vieillir, donc son verdict ne changera pas avec l'horloge.
        assert series['us_10a']['fraicheur'] == 'RETARD_FORT'
        assert series['us_10a']['age_jours'] >= 244
        #  Symétrique : le cache DIT « RETARD_FORT » sur un taux EN VIGUEUR ; le
        #  verdict rejugé rétablit SANS_OBJET.
        assert series['ze_refi']['fraicheur'] == 'SANS_OBJET'
        assert all('retard_jours' not in s for s in series.values())
        assert snap['en_retard'] == 1, 'le compte du pied suit le verdict rejugé'
    finally:
        svc._ETAT.clear()
        svc._ETAT.update(etat_avant)


def test_le_cache_persiste_ne_contient_aucun_verdict_de_fraicheur(monkeypatch, tmp_path):
    """Un verdict écrit sur disque redevient périmé sans que personne ne le voie :
    ce qui est persisté, c'est UNIQUEMENT ce que la source a publié."""
    import json as _json
    from vertex.services import macro_officiel as svc
    monkeypatch.setattr(svc, '_racine', lambda: str(tmp_path))
    monkeypatch.setattr(svc, '_battre', lambda *a, **k: None)
    monkeypatch.setattr(svc, '_publier', lambda: None)
    svc.collecter_une_fois(_fetch_fixtures)
    ecrit = _json.loads((tmp_path / svc.CACHE).read_text(encoding='utf-8'))
    for s in ecrit['series']:
        assert 'fraicheur' not in s and 'retard_jours' not in s and 'age_jours' not in s, s['id']
        assert s['observed_at'], 'la date de la SOURCE, elle, est persistée' 


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
