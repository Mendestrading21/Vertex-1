# -*- coding: utf-8 -*-
"""Gardiens « honnêteté » (mission alimentation, tranche 2).

Quatre défauts consignés dans docs/VERTEX_DATA_COVERAGE.md §13 :

1. la route `/api/strategy/decision/<sym>` FABRIQUAIT un verdict « ATTENDRE »
   pour un titre hors scan — il se lisait comme une conclusion du moteur ;
2. le calendrier écrivait « Confirmé » de lui-même sur chaque publication de
   résultats, alors que le serveur (/cal-feed) dit « date fournisseur, non
   confirmée par l’émetteur » ;
3. l'entonnoir de Marchés ne comptait que le vocabulaire français des
   verdicts ; le scan parle anglais (BUY/…) → « Achats = 0 » structurel ;
4. la fiche Analyse référençait `priceDomain` et `status` sans les déclarer et
   écrivait dans deux hôtes DOM absents (`#an-committee`, `#an-catalyst-strip`).

Tests contractuels sur le code servi + une route sans réseau. Aucune
connexion réelle.
"""
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(_ROOT, *parts), encoding='utf-8') as f:
        return f.read()


# ── 1. Verdict hors scan ────────────────────────────────────────────────────

@pytest.fixture
def client():
    from vertex.runtime import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_hors_scan_aucun_verdict_fabrique(client):
    j = client.get('/api/strategy/decision/ZZZZ').get_json()
    assert j['available'] is False
    assert j['final_decision'] is None, 'un verdict a été fabriqué hors scan'
    assert j['etat'] == 'NON_EVALUE'
    assert 'aucun verdict' in j['reason']


def test_la_route_ne_porte_plus_le_defaut_attendre():
    src = _src('vertex', 'app', 'routes', 'strategy_os_api.py')
    assert "'final_decision': 'ATTENDRE'" not in src


def test_les_pages_ne_fabriquent_plus_attendre_par_defaut():
    for page in ('analysis_page.py', 'intelligence_page.py'):
        src = _src('vertex', 'ui', 'pages', page)
        assert "||'ATTENDRE'" not in src, page
        assert 'NON ÉVALUÉ' in src, page


def test_le_rail_de_la_fiche_dit_pourquoi_il_n_evalue_pas():
    src = _src('vertex', 'ui', 'pages', 'analysis_page.py')
    assert 'const horsScan=!exec||exec.available===false||!exec.final_decision;' in src
    assert 'aucun verdict calculé' in src


# ── 2. Calendrier : confirmation servie ─────────────────────────────────────

def test_le_calendrier_ne_decide_plus_confirme():
    src = _src('vertex', 'static', 'vertex', 'js', 'pages', 'calendar.js')
    assert "badge('live', 'Confirmé')" not in src
    assert "badge('live', 'Confirmée')" not in src
    # Le niveau vient du serveur : champs de /cal-feed lus, jamais inventés.
    assert 'confirmation: it.confirmation ||' in src
    assert 'demo: !!(it.demo || cal.demo)' in src
    assert 'source: it.source ||' in src
    assert 'function badgeConfirmation(' in src
    # « Confirmée » n'apparaît que si le serveur commence par « confirm… ».
    assert '/^confirm/i.test(c)' in src
    # Sans information : on le dit.
    assert 'Confirmation n/d' in src


def test_le_serveur_etiquette_chaque_item_du_calendrier():
    src = _src('vertex', 'app', 'routes', 'content.py')
    assert "it['confirmation'] =" in src
    assert 'non confirmée par l’émetteur' in src


def test_les_evenements_macro_servent_leur_niveau_de_confirmation():
    """Dérivé de la source comme `approx` : une date de règle n'est jamais
    servie « confirmée », une date publiée par la Fed l'est."""
    from vertex.data import macro_calendar as mc
    from datetime import date
    evts = mc.events(120, today=date(2026, 9, 6))
    assert evts, 'aucun événement macro sur 120 jours'
    for e in evts:
        assert 'confirmation' in e, e
        if e['source'] == mc.SOURCE_FED:
            assert e['confirmation'].startswith('confirmée') and e['approx'] is False
        else:
            assert e['confirmation'].startswith('non confirmée') and e['approx'] is True


# ── 3. Entonnoir Marchés : vocabulaire du scan ─────────────────────────────

def test_l_entonnoir_marches_compte_les_achats_du_scan():
    src = _src('vertex', 'ui', 'pages', 'markets_page.py')
    m = re.search(r"const isBuy=v=>\[([^\]]*)\]", src)
    assert m, 'isBuy introuvable dans markets_page.py'
    voc = m.group(1)
    for tok in ("'ACHETER'", "'RENFORCER'", "'BUY'", "'STRONG_BUY'"):
        assert tok in voc, tok
    m2 = re.search(r"const isAct=v=>\{[^\n]*\[([^\]]*)\]", src)
    assert m2 and "'AVOID'" in m2.group(1)


def test_les_deux_entonnoirs_partagent_le_meme_vocabulaire():
    """Aujourd'hui (briefing.py) et Marchés comptent les mêmes verdicts : une
    divergence ferait afficher deux chiffres différents pour le même scan."""
    a = _src('vertex', 'ui', 'pages', 'briefing.py')
    b = _src('vertex', 'ui', 'pages', 'markets_page.py')
    ra = re.search(r"const isBuy=v=>\[([^\]]*)\]", a).group(1)
    rb = re.search(r"const isBuy=v=>\[([^\]]*)\]", b).group(1)
    assert set(re.findall(r"'([A-Z_ÉE]+)'", ra)) == set(re.findall(r"'([A-Z_ÉE]+)'", rb))


# ── 4. Fiche Analyse : références déclarées, hôtes présents ────────────────

def test_status_et_pricedomain_sont_declares():
    src = _src('vertex', 'ui', 'pages', 'analysis_page.py')
    assert 'let t=null,exec=null,status=null,stale=false;' in src
    assert 'const priceDomain=(status&&status.domains&&status.domains.prices)||null;' in src


def test_les_hotes_ecrits_par_la_fiche_existent():
    src = _src('vertex', 'ui', 'pages', 'analysis_page.py')
    for hote in ('an-committee', 'an-catalyst-strip'):
        assert "$('%s')" % hote in src, hote
        assert 'id="%s"' % hote in src, 'hôte %s écrit mais absent du DOM' % hote


def test_la_fiche_analyse_rend_les_hotes(client):
    r = client.get('/analysis/AAPL')
    if r.status_code != 200:
        pytest.skip('page Analyse non servie dans cet environnement (%s)' % r.status_code)
    body = r.get_data(as_text=True)
    assert 'id="an-committee"' in body
    assert 'id="an-catalyst-strip"' in body
