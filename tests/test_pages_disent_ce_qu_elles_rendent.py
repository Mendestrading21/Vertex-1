# -*- coding: utf-8 -*-
"""tests/test_pages_disent_ce_qu_elles_rendent.py — l'écran ne dit plus autre
chose que ce qu'il rend.

Sept défauts d'AFFICHAGE mesurés sur l'instance de contrôle le 06/09/2026, tous
reproduits avant correction ; ces gardiens naissent ROUGES sur le SHA de
baseline. Aucun calcul financier n'est déplacé dans la page : ces bancs gardent
des ÉNONCÉS (heure, unité, cause, provenance), pas des chiffres.

1. Fuseau détruit à l'affichage — `/news-feed` sert `published_at` en UTC
   ('2026-09-06T13:05:00Z') et `/api/macro/officiel` pose le `Z` exprès
   (verrouillé par tests/test_communiques_officiels.py). Le Briefing coupait la
   chaîne avec `match(/(\\d{2}:\\d{2})/)` et Marchés avec `.slice(0,16)` : une
   dépêche de 12 min s'affichait « 13:05 » face à une horloge lecteur à 15:17
   (lue vieille de 2 h 12), et la DATE était perdue (un item du 04/09 rendu
   « 23:42 »). Zéro occurrence de « UTC » sur ces lignes.
2. Fil d'actualités sans âge ni provenance — 0 `.vx-update` dans la carte quand
   19 vivaient sur la même page, 8 titres rendus sur 45 servis sans le dire, et
   `source_detail={'ibkr':0,'web':18}` calculé côté serveur, jamais affiché ;
   `loadNews` n'était réenregistré nulle part (4 s après `VX.liveReact('news')` :
   zéro requête supplémentaire).
3. Absence rendue comme un zéro — `const e=+r.entry_spot` avec `entry_spot=null`
   donne 0, `isFinite(0)` est vrai : la barre de plan affichait
   « 0,00 STOP · 361,19 ENTRÉE · 0,00 OBJECTIF », un R:R fabriqué, alors que le
   repli honnête (« — ») existait dix lignes plus bas.
4. Cause de panne fausse — la tuile « P&L latent » écrivait « IBKR hors ligne »
   en dur ; repro avec socket vivante (`live:true`, contrats absents du board) :
   l'écran envoyait vérifier TWS pour un contrat simplement non coté.
5. Fausse fraîcheur — le repli ACTION de `/api/pos-quotes` ne pose pas
   `delayed` (seulement source/mode/fallback_used) : un portefeuille valorisé au
   prix de scan s'annonçait « marques live/desk » / « IBKR temps réel/desk ».
6. Série de référence amputée — l'univers scanné (513 constituants, aucun ETF
   indiciel) rend `hasSpy` toujours faux ; sans l'étage « indice » (présent, lui,
   dans le Briefing), la carte marché de /markets traçait déterministement
   'MMM' (139–183 USD) sous l'unité « points d'indice » et le verdict de régime.
7. KPI macro nus — 4 cartes, 0 provenance, alors que la courbe des taux juste
   dessous, bâtie sur le MÊME `scan.macro`, porte « Il y a 16 min · yfinance
   Différé » et que `scan.macro[].date` est servi puis jeté par `crossAsset()`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / 'vertex' / 'ui' / 'pages'
STATIC = ROOT / 'vertex' / 'static' / 'vertex'


def _lire(*parts) -> str:
    return (ROOT / Path(*parts)).read_text(encoding='utf-8')


def _sans_commentaires(src: str) -> str:
    """Retire les blocs /* … */ et les lignes // — les gardiens portent sur le
    CODE servi, pas sur les commentaires qui citent le défaut corrigé."""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return '\n'.join('' if l.strip().startswith('//') else l for l in src.splitlines())


@pytest.fixture(scope='module')
def briefing() -> str:
    return _lire('vertex', 'ui', 'pages', 'briefing.py')


@pytest.fixture(scope='module')
def marches() -> str:
    return _lire('vertex', 'ui', 'pages', 'markets_page.py')


@pytest.fixture(scope='module')
def portefeuille() -> str:
    return _lire('vertex', 'ui', 'pages', 'portfolio_page.py')


@pytest.fixture(scope='module')
def core() -> str:
    return _lire('vertex', 'static', 'vertex', 'js', 'vx-core.js')


# ── 1. Le fuseau d'un horodatage est son unité (invariant 6) ────────────────

def test_le_detecteur_de_fuseau_reconnait_Z_et_les_decalages_et_rien_d_autre(core):
    """La règle vit dans UN helper partagé : les deux pages divergeaient
    justement parce que chacune coupait la chaîne à sa façon. On extrait la
    regex RÉELLEMENT servie et on l'exerce sur les formes mesurées du flux."""
    m = re.search(r'_hasTz\(s\)\s*\{\s*return\s*/(?P<re>.+?)/i\.test', core)
    assert m, 'VX.fmt._hasTz introuvable dans vx-core.js'
    rx = re.compile(m.group('re'), re.I)
    assert rx.search('2026-09-06T13:05:00Z'), 'le Z de yfinance doit être vu'
    assert rx.search('2026-09-04T09:10Z'), 'le Z posé par le collecteur officiel doit être vu'
    assert rx.search('2026-09-06T09:10+02:00') and rx.search('2026-09-06T09:10-0400')
    #  Les 45 items mesurés le 06/09 n'avaient AUCUN fuseau : ne pas en inventer un.
    assert not rx.search('2026-09-06T13:05'), 'une chaîne sans fuseau ne doit pas passer pour datée UTC'
    assert not rx.search('2026-09-04'), 'une date nue n’est pas un décalage horaire'


def test_le_helper_convertit_quand_le_fuseau_est_declare_et_le_dit_sinon(core):
    for marqueur in ('instantSource(iso, opts)', 'instantSourceNote(iso)',
                     "VX.fmt.ago(d)", "(fuseau n/d)"):
        assert marqueur in core, marqueur
    #  Sans fuseau, la DATE doit survivre : c'est la seconde moitié du défaut
    #  (un item du 04/09 rendu « 23:42 », indiscernable du jour même).
    assert "m[3] + '/' + m[2] + '/' + m[1]" in core, 'la date complète doit être rendue'


def test_le_fil_du_briefing_ne_decoupe_plus_l_heure_a_la_regex(briefing):
    code = _sans_commentaires(briefing)
    assert r"match(/(\d{2}:\d{2})/)" not in code, \
        'la regex jetait le fuseau ET la date de published_at'
    assert "VX.fmt.instantSource(iso,{style:'ago'})" in code
    assert "(n.published_at||n.time)" in code, 'la source du champ reste celle du contrat'
    assert 'VX.fmt.instantSourceNote(iso)' in code, 'l’info-bulle dit la chaîne brute de la source'


def test_les_communiques_ne_sont_plus_decapites_de_leur_Z(marches):
    code = _sans_commentaires(marches)
    #  `liste.slice(0,16)` (16 communiqués rendus) est légitime ; c'est la coupe
    #  appliquée à l'HORODATAGE qui décapitait le fuseau.
    assert not re.search(r'published_at[^\n]{0,40}\.slice\(', code), \
        'la coupe à 16 caractères effaçait le Z que le serveur pose exprès'
    assert 'VX.fmt.instantSource(c.published_at)' in code
    assert 'VX.fmt.instantSourceNote(c.published_at)' in code


# ── 2. Le fil d'actualités porte son âge, sa provenance et sa troncature ────

def test_la_carte_actualites_porte_un_tampon_et_dit_sa_troncature(briefing):
    code = _sans_commentaires(briefing)
    debut = code.index('async function loadNews()')
    fin = code.index('function buildAnchors()')
    carte = code[debut:fin]
    assert 'VX.updateIndicator(' in carte, 'aucun tampon dans la carte (mesuré : 0 .vx-update)'
    assert 'd.source_detail' in carte, 'la bascule courtier→web est servie et doit être dite'
    assert 'titre(s) affiché(s) sur' in carte, '8 rendus sur 45 servis, sans le dire'


def test_le_fil_est_rejoue_et_ne_fige_plus_a_l_heure_du_chargement(briefing):
    assert re.search(r'VX\.refresh\.register\(loadNews,\s*\d+', briefing), \
        'loadNews n’était ni dans VX.refresh.register ni sur un canal de bus'


# ── 3. Absence ≠ zéro sur le plan d'un setup (invariant 5) ──────────────────

def test_la_barre_de_plan_refuse_la_coercition_nue(portefeuille):
    code = _sans_commentaires(portefeuille)
    for nu in ('+r.entry_spot', '+r.stop', '+r.tgt',
               'Number(r.entry_spot)', 'Number(r.stop)', 'Number(r.tgt)'):
        assert nu not in code, f'{nu} : `+null` vaut 0 et isFinite(0) est vrai'
    assert "const fin=x=>(x===null||x===undefined||x===''||typeof x==='boolean')?NaN:+x;" in code, \
        'la coercition stricte est le correctif : elle rejette null, \'\' et les booléens'
    assert 'plan non défini' in code, 'un suivi sans niveau doit se nommer, pas se dessiner'


def test_le_modal_de_suivi_refuse_un_plan_a_moitie_saisi():
    ent = _lire('vertex', 'static', 'vertex', 'js', 'vx-entities.js')
    code = _sans_commentaires(ent)
    assert 'Plan incomplet' in code, \
        'deux niveaux sur trois se redessinent ensuite comme un plan complet'
    assert "if (saisis && saisis < 3)" in code


# ── 4. La cause affichée est mesurée, jamais devinée ────────────────────────

def test_aucune_panne_courtier_n_est_affirmee_sans_avoir_ete_mesuree(portefeuille):
    """Repro décisive : `/api/pos-quotes` répondait `live: true` pendant que la
    tuile affichait « IBKR hors ligne » — la page n'avait jamais lu l'état du
    courtier (une seule lecture de `d.live`, jamais consommée ici)."""
    code = _sans_commentaires(portefeuille)
    for i, ligne in enumerate(code.splitlines(), 1):
        if 'IBKR hors ligne' in ligne:
            assert 'window.__pfLive' in ligne, \
                f'ligne {i} : cause courtier affirmée sans tester window.__pfLive'
    assert 'function pfCauseMarques(' in code, 'une seule autorité pour cette phrase'
    assert "position(s) sans marque" in code, 'la cause réelle mesurée est nommée'
    assert 'coût déclaré nul' in code, 'invested===0 est une troisième cause, distincte'


# ── 5. « live » n'est écrit que sur preuve, côté page aussi ─────────────────

def test_le_portefeuille_lit_le_repli_servi_avant_d_annoncer_du_live(portefeuille):
    code = _sans_commentaires(portefeuille)
    assert 'window.__pfFallback=!!d.fallback_used;' in code, \
        'fallback_used est servi et n’était lu nulle part'
    assert "window.__pfLive===true?'marques live/desk'" in code, \
        '« live/desk » ne doit plus se déduire de la seule absence de q.delayed'
    assert 'window.__pfFallback===true' in code


def test_le_briefing_n_annonce_ibkr_temps_reel_que_sur_preuve(briefing):
    code = _sans_commentaires(briefing)
    assert "pfLive===true?'IBKR temps réel/desk'" in code
    assert 'pfRepli=!!j.fallback_used' in code, \
        'le repli ACTION ne pose pas delayed : sans fallback_used, le scan passe pour du live'


# ── 6. Une carte marché trace le marché (un seul propriétaire) ──────────────

def test_la_carte_marche_retrouve_l_etage_indice_du_briefing(marches, briefing):
    code = _sans_commentaires(marches)
    debut = code.index('function loadSpyChart(scan)')
    carte = code[debut:code.index('const MACRO_NAMES')]
    assert "i.name==='S&P 500'" in carte, \
        'l’étage INDICE manquait : la carte tombait sur le 1er titre du scan (MMM)'
    assert "hasIdx?'S&P 500':Object.keys(det).find(okSeries)" in carte, \
        'priorité SPY → indice S&P 500 → proxy, comme le Briefing'
    #  Le Briefing porte la même priorité : les deux pages ne doivent plus diverger.
    assert "i.name==='S&P 500'" in _sans_commentaires(briefing)


def test_l_unite_de_la_carte_marche_suit_la_serie_reellement_tracee(marches):
    code = _sans_commentaires(marches)
    assert "unit:(hasSpy||hasIdx)?'points d’indice':'USD'" in code, \
        '« points d’indice » au-dessus d’un cours de 3M en dollars est une unité fausse'
    assert 'SPY absente du scan' not in code, \
        'le titre du dernier recours doit dire qu’il manque AUSSI l’indice'


# ── 7. Un KPI macro porte son observation et sa source ──────────────────────

def test_le_strip_macro_conserve_la_date_d_observation_servie(marches):
    code = _sans_commentaires(marches)
    assert 'obs:x.date||null' in code, \
        'crossAsset() supprimait la date d’observation avant l’affichage'
    assert "'observé le '+esc(dateFrOff(d.obs))" in code
    assert 'class="m-foot"' in code and 'VX.updateIndicator(' in code.split('function macroCard(')[1][:900]


def test_le_pied_du_kpi_macro_a_une_regle_de_style():
    css = _lire('vertex', 'static', 'vertex', 'css', 'vertex-2-0.css')
    assert '.vx-mk-macro .m-foot{' in css, 'un pied sans règle se rend en bloc de texte nu'


# ── Preuve de service : les corrections sont bien DANS le HTML servi ────────

@pytest.fixture(scope='module')
def client():
    import terminal
    terminal.app.config['TESTING'] = True
    return terminal.app.test_client()


@pytest.mark.parametrize('route,attendu', [
    ('/', "VX.fmt.instantSource(iso,{style:'ago'})"),
    ('/markets', 'VX.fmt.instantSource(c.published_at)'),
    ('/portfolio', 'function pfCauseMarques('),
])
def test_le_html_servi_porte_bien_le_correctif(client, route, attendu):
    r = client.get(route)
    assert r.status_code == 200, (route, r.status_code, r.headers.get('Location'))
    assert attendu in r.get_data(as_text=True), route
