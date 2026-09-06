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
   « 0,00 STOP · 123,45 ENTRÉE · 0,00 OBJECTIF », un R:R fabriqué, alors que le
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

## SECOND TOUR — ce que le contrôle adverse a mesuré sur ces correctifs

Six d'entre eux étaient partiels, supposés, ou datés du mauvais instant. Les
gardiens ci-dessous sont écrits APRÈS reproduction de chaque écart :

8.  Unité SUPPOSÉE (constat 32) — 'USD' remplaçait « points d'indice » sur le
    proxy. Aucun champ `currency` n'est servi pour `scan.detail[SYM]`
    (0 occurrence dans la charge) : le dollar était déduit de l'univers S&P 500,
    c'est-à-dire énoncé sans donnée. Sans devise servie : aucune unité.
9.  Pied qui date l'INSTANTANÉ (constat 51) — les 4 KPI macro portaient
    `VX.updateIndicator(scan.scan_ts, scan.source, modeOf(scan))`, et `modeOf`
    rendait 'live' dès `scan.source==='ibkr'`. Or /scan ne transporte que des
    barres quotidiennes (`interval='1d'`, `duration='1 Y'`) et sa route l'écrit :
    « le badge LIVE IBKR reste piloté par l'overlay /quotes — lui seul voit les
    ticks ». Un dimanche, « Taux 10 ans · Il y a 16 min » se lisait comme une
    valeur de dimanche : c'est la clôture de vendredi (`scan.macro[].date`).
10. Cause affirmée sans mesure (constat 19) — « plan non défini — aucun niveau
    saisi à la création du suivi » alors que la branche se déclenche sur
    `[e,s,t].every(x=>!isFinite(x))`, ce qui couvre aussi une valeur stockée non
    numérique (chaîne non parsable → NaN sans passer par la garde).
11. Repli lu à 2 endroits sur 17 (constat 27) — `window.__pfFallback` était posé
    et consommé deux fois ; 15 pieds de carte choisissaient encore source ET
    mode sur le seul `__pfLive`. Or /api/pos-quotes rend `live:true` ET
    `fallback_used:true` en même temps (`fallback_used = bool(combles)`) : ces
    pieds annonçaient « IBKR/desk · Live » au-dessus de prix de scan. Idem
    POSITION PAR POSITION : `q.delayed` seul rate le repli ACTION, qui écrit
    `mode:'DELAYED'` + `fallback_used:true`.
12. Tampon qui compte autre chose que ce qui est peint (constat 40) — 24
    communiqués collectés, `slice(0,16)` peints, tampon « 24 communiqués ».
13. Pied absent dans le cas dégradé (constats 42-43) — l'early-return du fil
    d'actualités est à l'offset 63 de `loadNews` et le pied à 3993 : un fetch en
    échec rendait donc une carte à ZÉRO `.vx-update`, précisément quand le
    lecteur ne voit rien. Le même texte servait pour l'échec et pour le vide, et
    affirmait une cause jamais mesurée (« hors ligne dans cet environnement »).
14. Info-bulle qui met en cause la source (constat 9) — « fuseau non déclaré PAR
    LA SOURCE » : yfinance déclare bien son 'Z', c'est Vertex qui le tronque en
    amont (`str(t)[:16]`). 45 items sur 45 arrivent sans fuseau.
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
    """MESURE DU SECOND TOUR (défaut 13) : le compte « 8 titre(s) affiché(s) sur
    45 servis » ne nommait NI le plafond NI le filtre — avec « Positives » actif,
    rien ne disait si 8 était la récolte du filtre ou une troncature. Trois
    nombres distincts sont désormais exigés : affichés, retenus, servis."""
    code = _sans_commentaires(briefing)
    debut = code.index('async function loadNews()')
    fin = code.index('function buildAnchors()')
    carte = code[debut:fin]
    assert 'VX.updateIndicator(' in code[debut:code.index('function buildAnchors()')] \
        or 'newsPied(' in carte, 'aucun tampon dans la carte (mesuré : 0 .vx-update)'
    pied = code[code.index('function newsPied('):]
    pied = pied[:pied.index('\n}')]
    assert 'VX.updateIndicator(' in pied, 'le pied du fil porte l’âge et la provenance'
    assert 'd.source_detail' in pied, 'la bascule courtier→web est servie et doit être dite'
    assert "titre(s) affiché(s)" in pied and "retenu(s)" in pied and "servi(s) par le fil" in pied, \
        '8 rendus sur 45 servis : les trois comptes doivent être distincts'
    assert 'plafond d’affichage ' in pied, 'la troncature doit se nommer'
    assert "NEWS_LIB[NEWS_FILTER]" in pied, 'le filtre actif doit être nommé dans le pied'


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
    """MESURE DU SECOND TOUR (défaut 8 du docstring) : « points d'indice » sur un
    cours de 3M était une unité FAUSSE ; 'USD' à la place était une unité
    SUPPOSÉE — le scan ne sert aucun `currency` pour scan.detail[SYM] (0
    occurrence), le dollar venait de l'univers scanné, pas de la donnée. Le
    contrat graphique n'imprime ni badge ni « · unité » quand `opts.unit` est
    vide : l'absence d'unité est donc rendable, et c'est ce qu'on exige ici."""
    code = _sans_commentaires(marches)
    assert "unit:(hasSpy||hasIdx)?'points d’indice':''" in code, \
        'sans devise servie, la carte ne doit affirmer AUCUNE unité'
    carte = code.split('function loadSpyChart(scan)')[1].split('const MACRO_NAMES')[0]
    assert "'USD'" not in carte, 'une devise déduite de l’univers reste une devise inventée'
    assert 'ne sert pas la devise de ce titre' in carte, \
        'l’absence doit être DITE au lecteur, pas seulement omise'
    assert 'SPY absente du scan' not in code, \
        'le titre du dernier recours doit dire qu’il manque AUSSI l’indice'


def test_le_contrat_graphique_sait_ne_rien_afficher_quand_l_unite_est_absente():
    """Le correctif ci-dessus ne tient que si la carte accepte une unité vide :
    on l'éprouve sur le code RÉELLEMENT servi, pas sur son intention."""
    core = _lire('vertex', 'static', 'vertex', 'js', 'charts', 'chart-core.js')
    assert '${opts.unit ? `<span class="vx-badge vx-badge-unit"' in core, \
        'le badge d’unité doit être conditionnel'
    assert "${opts.unit ? ' · unité ' + opts.unit : ''}" in core, \
        'le tiroir « Comprendre » ne doit pas écrire « unité » sans unité'


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


# ════════════════════════════════════════════════════════════════════════════
#  SECOND TOUR — défauts 8 à 14 du docstring
# ════════════════════════════════════════════════════════════════════════════

# ── 9. Le mode dit ce que la charge porte, jamais ce que la socket promet ────

def test_le_scan_ne_transporte_aucun_tick_et_c_est_la_route_qui_le_dit():
    """Le gardien suivant n'a de sens que si la prémisse tient : /scan ne sert
    que des BARRES. On la relit sur le code servi plutôt que de la postuler."""
    api = _lire('vertex', 'app', 'routes', 'scan_api.py')
    assert 'lui seul voit les ticks' in api, \
        'la route /scan déclare elle-même que le live vient de /quotes'
    term = _lire('terminal.py')
    assert "interval='1d'" in term, 'le scan télécharge des barres quotidiennes'
    assert "duration=duree" in term and "'1y': '1 Y'" in term, \
        'la branche courtier du scan demande un historique, pas un flux'


@pytest.mark.parametrize('page', ['briefing.py', 'markets_page.py'])
def test_aucun_pied_du_scan_n_annonce_du_live(page):
    """Mesure du 06/09/2026 : quand le courtier sert TOUT l'univers,
    `scan.source` vaut exactement 'ibkr' — `modeOf` rendait alors 'live' et 25
    pieds (8 sur le Briefing, 17 sur Marchés) annonçaient « ibkr Live » au-dessus
    de clôtures, dont les 4 KPI macro où ^TNX porte sa propre date de clôture."""
    code = _sans_commentaires(_lire('vertex', 'ui', 'pages', page))
    assert "function modeOf(scan){return scan&&scan.data_source==='demo'?'fallback':'delayed';}" in code, \
        'une seule autorité de mode par page, et elle ne promet pas de tick'
    assert "scan.source==='ibkr'?'live'" not in code, \
        'la source du scan ne prouve pas la fraîcheur de la donnée'


def test_le_kpi_macro_date_l_indicateur_et_pas_seulement_l_instantane(marches):
    """Deux horodatages distincts : la date d'observation de la valeur
    (`scan.macro[].date`, dernière barre) et l'âge du relevé de scan. Le pied ne
    portait que le second, sans le nommer : un dimanche, « Taux 10 ans 4,78 % ·
    Il y a 16 min » se lit comme une valeur de dimanche."""
    code = _sans_commentaires(marches)
    foot = code.split('const foot=`<div class="m-foot">')[1][:600]
    assert "'observé le '+esc(dateFrOff(d.obs))" in foot
    assert 'date d’observation non servie' in foot, \
        'Pétrole/Or/Bitcoin viennent de `commodities`, sans date : l’absence se dit'
    assert '<span>· relevé</span>' in foot, \
        'sans ce mot, l’âge de l’instantané se lit comme l’âge de la valeur'


# ── 11. Le repli est lu PARTOUT, et position par position ───────────────────

def test_aucun_pied_du_portefeuille_ne_choisit_sur_le_seul_temoin_live(portefeuille):
    """Repro : /api/pos-quotes rend `live:true` ET `fallback_used:true` dès
    qu'une ACTION est comblée au prix de scan (`fallback_used = bool(combles)`).
    Les deux formes interdites ci-dessous apparaissaient 8 et 15 fois.

    SEUIL RÉVISÉ 13 -> 12, avec la mesure. Ce compte épinglait « tous les pieds
    passent par l'autorité ». Il valait pour les pieds qui décrivent les MARQUES.
    Deux d'entre eux n'en décrivaient aucune : les deux pieds de la carte Stress
    lisent `/api/portfolio/stress`, un GET sans corps que la route sert depuis le
    scan — mesuré le 06/09/2026, sa charge porte assumption, coverage_pct, empty,
    excluded, excluded_cost, generator, narrative, positions, reason, scenarios,
    stressed_value, et AUCUN `as_of`. Ils empruntaient donc à la fois l'horloge
    (`window.__pfTs`) et le mode (`pfModeMarques()`) d'un appel de cotation
    qu'ils ne consomment pas. Les faire sortir de l'autorité des marques est le
    correctif, pas une fuite : ils n'affirment plus ni âge ni mode.
    """
    code = _sans_commentaires(portefeuille)
    assert "window.__pfLive?'live':'fallback'" not in code, \
        'le mode ignorait le repli servi'
    assert "window.__pfLive?'IBKR/desk':'desk (repli)'" not in code, \
        'la source ignorait le repli servi'
    assert 'function pfSourceMarques(' in code and 'function pfModeMarques(' in code, \
        'une seule autorité de provenance et de mode pour la page'
    for nom in ('pfSourceMarques', 'pfModeMarques'):
        corps = code.split('function %s(' % nom)[1].split('\n}')[0]
        assert '__pfFallback===true' in corps, f'{nom} doit lire le repli servi'
        assert '__pfLive===null' in corps, f'{nom} doit distinguer « non mesuré »'
    assert code.count('pfModeMarques()') >= 12, 'les pieds passent tous par l’autorité'
    assert code.count('pfSourceMarques()') >= 7
    #  Et les deux pieds qui ne décrivent PAS les marques n'empruntent plus
    #  leur horloge ni leur mode (voir le docstring : /api/portfolio/stress ne
    #  sert aucun `as_of` et ne lit jamais /api/pos-quotes).
    assert "'portfolio_stress · horodatage non servi par la route'" in code
    assert "window.__pfTs||null,\n          'portfolio_stress'" not in code
    assert code.count('horodatage non servi par la route') == 2


def test_la_regle_du_differe_lit_TOUT_ce_que_le_serveur_ecrit_sur_un_repli(core):
    """Croisement serveur → client. Trois écritures du même fait coexistent :
    `q['delayed']=True` (repli OPTION, routes/desk.py), `mode`/`fallback_used`
    (repli ACTION, cotation_unifiee.en_charge_client), et rien du tout sur une
    cotation courtier. Ne lire que la première laissait une action valorisée au
    prix de scan s'afficher sans marque de différé."""
    desk = _lire('vertex', 'app', 'routes', 'desk.py')
    unif = _lire('vertex', 'data_sources', 'cotation_unifiee.py')
    assert "q['delayed'] = True" in desk
    assert "'mode': pv.source_mode" in unif and "'fallback_used': bool(pv.fallback_used)" in unif
    regle = core.split('VX.quotes = {')[1].split('};')[0]
    for champ in ("q.delayed === true", "q.fallback_used === true", "q.mode === 'DELAYED'"):
        assert champ in regle, f'la règle client ignore {champ}'


def test_le_pl_options_ne_porte_pas_le_repli_des_actions(portefeuille):
    """Contamination croisée mesurée : `renderOptions` appelle `quotesFor(opts)`
    puis `quotesFor(pos)`, qui écrivent les mêmes globales — le témoin de CARTE
    `__pfFallback` y parlait donc pour tout le portefeuille. Le repli ACTION ne
    comble jamais un contrat : une action au prix de scan étiquetait « différé »
    un P&L d'options qu'elle ne touche pas. Le témoin par position suffit."""
    code = _sans_commentaires(portefeuille)
    sous = code.split('const plOptSub=')[1].split(';')[0]
    assert 'rich.some(t=>t.delayed)' in sous, 'le différé des options se lit position par position'
    assert '__pfFallback' not in sous, \
        'le témoin de carte importe ici l’état d’une autre carte'


def test_les_deux_pages_partagent_la_meme_regle_de_differe(portefeuille, briefing):
    """Dupliquée, la règle avait déjà divergé (le Briefing et le Portefeuille ne
    coupaient pas l'horodatage de la même façon). Elle vit dans vx-core."""
    pf, br = _sans_commentaires(portefeuille), _sans_commentaires(briefing)
    assert 'delayed:VX.quotes.differee(q)' in pf, 'enrich() figeait `!!q.delayed`'
    assert 'delayed:!!q.delayed' not in pf
    assert 'VX.quotes.differee(q)' in br, 'la ligne par position du Briefing aussi'
    assert "(q.delayed?' · différé':'')" not in br, \
        '`q.delayed` seul rate le repli ACTION'


# ── 10 et 25. Une cause affichée est une cause mesurée ──────────────────────

def test_le_plan_absent_ne_prete_plus_de_cause_au_suivi(portefeuille):
    """La branche se déclenche sur `[e,s,t].every(x=>!isFinite(x))` : elle
    couvre aussi une valeur stockée non numérique. « Aucun niveau saisi à la
    création » était une hypothèse, vraie du cas nominal seulement."""
    code = _sans_commentaires(portefeuille)
    assert 'plan non défini — aucun niveau exploitable' in code
    assert 'aucun niveau saisi à la création' not in code, \
        'la page affirmait une cause que la garde ne mesure pas'


def test_aucune_panne_de_cotation_n_est_inventee_quand_le_compte_est_nul(portefeuille):
    """`pfCauseMarques(0)` rendait « marques indisponibles ». Sur trois des
    quatre appelants c'était du code mort ; sur le quatrième (contribution au
    P&L) il était atteignable sans aucune position déclarée ou sans module
    graphique — et nommait alors une panne de cotation qui n'existait pas."""
    code = _sans_commentaires(portefeuille)
    assert "'marques indisponibles'" not in code
    assert "'cause non mesurée'" in code, 'un compte nul n’affirme plus rien'
    assert 'aucune position ouverte déclarée' in code
    assert 'module de graphiques non chargé' in code
    assert "pfCauseMarques(0)" not in code, 'la branche morte est retirée'


# ── 12. Un tampon compte ce qui est peint ───────────────────────────────────

def test_le_tampon_des_communiques_compte_les_lignes_rendues(marches):
    """Mesure : 24 collectés, 16 peints, tampon « 24 communiqués »."""
    code = _sans_commentaires(marches)
    assert 'const COMMUNIQUES_MAX=' in code, 'le plafond doit avoir un seul propriétaire'
    assert 'liste.slice(0,COMMUNIQUES_MAX)' in code
    assert ("Math.min(liste.length,COMMUNIQUES_MAX)+' communiqué(s) affiché(s) sur '"
            "+liste.length+' collecté(s) · '") in code
    assert "'+liste.length+' communiqués · '" not in code, \
        'le tampon comptait la liste complète, pas les lignes rendues'


# ── 13. Le fil d'actualités porte son pied dans TOUTES ses branches ─────────

def _carte_news(briefing: str) -> str:
    code = _sans_commentaires(briefing)
    return code[code.index('async function loadNews()'):code.index('function newsPied(')]


def test_le_pied_du_fil_est_rendu_meme_quand_aucun_titre_ne_l_est(briefing):
    """Offsets mesurés dans la fonction servie : early-return à 63, pied à 3993.
    Le cas dégradé — le seul où le lecteur ne peut rien déduire de l'écran —
    était donc le seul sans âge ni provenance."""
    carte = _carte_news(briefing)
    assert carte.index('const pied=newsPied(') < carte.index('if(!items.length){'), \
        'le pied doit être calculé AVANT le retour anticipé'
    vide = carte[carte.index('if(!items.length){'):carte.index('el.innerHTML=items.map')]
    assert '+pied;' in vide, 'la branche vide doit concaténer le pied'


def test_le_fil_distingue_l_echec_de_requete_du_flux_vide(briefing):
    """`d` nul (fetch en échec) et `items:[]` (le serveur n'a rien servi)
    rendaient le MÊME texte, qui affirmait de surcroît une cause non mesurée."""
    carte = _carte_news(briefing)
    assert 'let d=null,err=null;' in carte, 'l’échec doit être retenu, pas avalé'
    assert 'VX.states.error(' in carte and 'Fil d’actualités injoignable' in carte
    assert 'hors ligne dans cet environnement' not in carte, \
        'cause jamais mesurée par la page'
    assert 'n’a servi aucun titre' in carte, 'le zéro servi reste distinct de l’échec'


def test_le_filtre_du_fil_a_une_seule_table_de_libelles(briefing):
    """Le pied nomme le filtre actif : il doit lire la table qui peint les
    chips, sinon les deux listes divergent au premier ajout."""
    carte = _carte_news(briefing)
    assert 'Object.keys(NEWS_LIB).map(id=>' in carte
    assert "[['all','Tout'],['pos','Positives'],['neg','Négatives']]" not in carte


# ── 14. L'info-bulle ne met en cause personne sans mesure ───────────────────

def test_l_info_bulle_ne_reproche_pas_a_la_source_un_fuseau_detruit_par_vertex(core):
    """yfinance déclare bien 'Z' sur `published_at` ; c'est
    `vertex/options/legacy_engine.py` qui le tronque (`str(t)[:16]`) avant que la
    page ne le voie. Mesure : 45 items sur 45 arrivent sans fuseau. La note dit
    donc ce qu'elle tient — l'horodatage SERVI n'en porte pas."""
    code = _sans_commentaires(core)   # le commentaire CITE la phrase corrigée
    assert 'fuseau non déclaré par la source' not in code, \
        'énoncé non mesuré, et faux pour au moins une source'
    assert 'aucun fuseau dans l’horodatage servi' in code


# ── Méta-gardien : un banc qui ne peut pas échouer ne garde rien ────────────

def test_aucun_banc_du_depot_n_affirme_une_constante_vraie():
    """Le défaut mesuré dans cette famille de gardiens : un `assert` dont le test
    est une CONSTANTE VRAIE — `assert 'x' in html, 'msg'` mal parenthésé devient
    `assert ('x' in html, 'msg')`, un tuple non vide, donc toujours vrai. Le banc
    passe au vert quoi qu'il arrive et ne garde plus rien.

    Le correctif du premier tour rétablissait la forme sur UN banc ; rien
    n'empêchait la faute de revenir. Recensement du 06/09/2026 : 5 186 fonctions
    de test, 0 assertion toujours vraie. Ce banc gèle ce zéro."""
    import ast

    racine = ROOT / 'tests'
    coupables, fonctions = [], 0
    for fichier in sorted(racine.rglob('test_*.py')):
        arbre = ast.parse(fichier.read_text(encoding='utf-8'))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fonctions += 1
            if not isinstance(noeud, ast.Assert):
                continue
            test = noeud.test
            #  Tuple/liste non vide : la forme du défaut. Constante vraie et
            #  f-string : deux autres façons d'écrire une assertion inutile.
            toujours_vrai = (
                (isinstance(test, (ast.Tuple, ast.List)) and bool(test.elts))
                or (isinstance(test, ast.Constant) and bool(test.value))
                or isinstance(test, ast.JoinedStr))
            if toujours_vrai:
                coupables.append('%s:%d' % (fichier.relative_to(ROOT), noeud.lineno))
    assert fonctions > 4000, \
        'le détecteur ne voit presque aucune fonction : il ne mesure plus rien'
    assert not coupables, ('assertion toujours vraie (le banc ne peut pas '
                           'échouer) : ' + ' | '.join(coupables))


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
    #  Second tour : les correctifs de ce lot doivent eux aussi être SERVIS,
    #  pas seulement présents dans le fichier source.
    ('/', 'function newsPied('),
    ('/', "return scan&&scan.data_source==='demo'?'fallback':'delayed';"),
    ('/markets', 'const COMMUNIQUES_MAX='),
    ('/markets', 'date d’observation non servie'),
    ('/portfolio', 'function pfModeMarques('),
    ('/portfolio', 'plan non défini — aucun niveau exploitable'),
])
def test_le_html_servi_porte_bien_le_correctif(client, route, attendu):
    r = client.get(route)
    assert r.status_code == 200, (route, r.status_code, r.headers.get('Location'))
    assert attendu in r.get_data(as_text=True), route
