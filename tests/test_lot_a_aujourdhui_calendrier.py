"""LOT A — AUJOURD'HUI ET CALENDRIER : CE QUE LA PAGE PROMET LE MATIN.

Les deux premières vues de la journée promettent « en cinq secondes, je sais
quoi regarder ». Six défauts mesurés le 06/09/2026 dans Chromium sur
l'instance de vérification (5003, `NO_IBKR=1`, `DEMO=0`), pas lus dans un
document.


## (a) La carte centrale d'Aujourd'hui ne savait pas se dater

`build_editorial` servait `as_of = scan_state['updated']`. Mesure sur 5003 :
ce champ vaut `'19:49:23'` — une heure murale nue, sans date ni fuseau, quand
le MÊME instant existe à côté sous forme d'instant
(`scan_ts_h = '2026-09-06T17:49:23Z'`, `scan_ts = 1788716963.687`).
`VX.freshness._ms('19:49:23')` ne peut rien parser et rend `null`, donc
`VX.updateIndicator` rendait :

    Brief du marché — Vertex   →  « Âge inconnu · Investing.com, … Différé »
                                  data-ts absent · title absent

pendant que ses huit voisines de la même page affichaient « Il y a 24 min »
avec `title="06/09/2026 19:49:23"`. Un mode servi (« Différé ») affirmé sur une
charge dont l'âge n'est pas mesurable est exactement ce que l'invariant 5
interdit. `_trace_aujourdhui`, dans le MÊME fichier, pratiquait déjà le bon
ordre de préférence.


## (b) « Posture du comité » affirmait un mode sans âge

Mesure de `/api/command` le 06/09/2026 : ses clés sont exactement
`{alerts, controls_availability, counts, decision, exposure, portfolio_score,
regime, risk, top_options, top_stocks, validation}` — ni `ts`, ni `as_of`, ni
`updated`. `cTs` valait donc toujours `null` et la carte rendait
« Âge inconnu · comité Différé ».

Cet âge est pourtant mesurable sans un seul appel réseau : `command.py` ne lit
QUE `scan_state`, donc la charge du comité a l'âge du scan qui l'a produite.
Le serveur pose cet instant dans `[data-scan-ts]` et le pied nomme cette
provenance au lieu de la faire passer pour l'heure de l'endpoint.


## (c) « Radar d'alertes » ne portait aucune fraîcheur

Mesure sur 5003 : la carte rendait deux alertes de risque et **zéro**
`.vx-update`, quand douze autres cartes de la même page en portaient un. Un
radar sans heure ne dit pas si le balayage date de la minute ou de la veille.
`/api/alerts/status` sert pourtant `ts` (horloge du dernier balayage, évalué
toutes les 60 s), et chaque déclenchement persisté par `terminal.py` porte son
propre `ts` et son `price` : un franchissement d'il y a trois jours rendait le
même badge « déclenchée » qu'un franchissement d'il y a une minute.


## (d) Trois tuiles portaient un tiret MUET

`loadStrip` filtre les instruments absents ; `loadMarketGrid` rend les douze de
sa table quoi qu'il arrive. Mesure : SMI, USD/CHF et ETH sortaient en
« — / n/d » avec `title` ABSENT — rien ne distinguait l'absence d'un zéro, d'une
panne ou d'un oubli. La cause est mesurable sans rien supposer : l'instrument
n'est pas dans la charge du scan, et le scan dit qui l'a servie.


## (e) — hors périmètre, déjà corrigé ailleurs pendant ce lot

Une phrase de 104 caractères (`ed.calls_impact`) servie dans `.vx-badge`
sortait de l'écran de 234 px à 390 px. Mesure du 06/09/2026, 20:03 :
`span.vx-badge`, largeur 587 px dans un parent de 316 px, bord droit 624 px
pour un viewport de 390 px, `white-space` calculé à `nowrap`. Le défaut ne
vivait pas dans cette page mais dans la primitive partagée : à 20:20, un autre
lot avait plafonné et replié `.vx-badge` dans `components.css`, avec la MÊME
mesure. Re-mesuré ici après ce correctif : largeur 316 px, aucun débordement.
Ce lot ne le corrige donc pas une seconde fois dans la page.

## (f) Le tableau du Calendrier nommait « Date » une colonne de confirmation

Mesure sur `/calendar?view=week` : en-têtes servis
`['Date','Échéance (j)','Type','Événement','Instrument','Date','Source']` —
DEUX colonnes « Date » — et la cellule sous la seconde valait « Non confirmée
par l'émetteur ». Un en-tête qui nomme autre chose que sa colonne est une
valeur fausse : le lecteur lit un niveau de confirmation en croyant lire une
date.


## Comment ces bancs mesurent

Les bancs (b) à (f) exécutent le JavaScript RÉELLEMENT servi — extrait de
`briefing._JS` et de `calendar.js` par appariement d'accolades, jamais recopié
— dans un vrai Chromium, avec le vrai `vx-core.js` et la vraie cascade CSS de
la coque. Aucun banc ne fige une chaîne d'affichage : ils mesurent une
propriété (un `data-ts` exploitable, un `title` non vide, une largeur rendue,
l'appariement en-tête ↔ cellule).

## Ce qu'ils ne prouvent pas

Ils ne disent rien de la justesse des chiffres servis par les moteurs, ni de
l'âge réel des sources en amont : ils prouvent que la page dit ce qu'elle
mesure et ne prétend rien de plus.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from vertex.ui.pages import briefing

RACINE = Path(__file__).resolve().parents[1]
JS_DIR = RACINE / "vertex" / "static" / "vertex" / "js"
CSS_DIR = RACINE / "vertex" / "static" / "vertex" / "css"
CORE = JS_DIR / "vx-core.js"
CALENDRIER_JS = JS_DIR / "pages" / "calendar.js"

#: L'instant de scan tel que 5003 le sert, sous ses deux formes.
SCAN_TS_H = "2026-09-06T17:49:23Z"
SCAN_UPDATED = "19:49:23"

# ── Instrument partagé : exécuter le JS RÉELLEMENT servi ─────────────
def _extraire_fonction(source: str, nom: str) -> str:
    """Isole une fonction nommée par appariement d'accolades.

    On EXTRAIT au lieu de recopier : une fonction renommée ou déplacée fait
    tomber le banc au lieu de le laisser garder un fantôme.
    """
    m = re.search(r"(?:async\s+)?function\s+" + re.escape(nom) + r"\s*\(", source)
    assert m, f"fonction {nom!r} introuvable dans la source servie"
    debut = source.index("{", m.end() - 1)
    profondeur = 0
    for i in range(debut, len(source)):
        if source[i] == "{":
            profondeur += 1
        elif source[i] == "}":
            profondeur -= 1
            if profondeur == 0:
                return source[m.start():i + 1]
    raise AssertionError(f"accolades non appariées pour {nom!r}")


def _navigateur_pret() -> bool:
    #  Même témoin que les autres bancs navigateur du dépôt.
    try:
        from tools.mesures.mesurer_qa_espaces import navigateur_pret
    except Exception:
        return False
    return bool(navigateur_pret())


navigateur_requis = pytest.mark.skipif(
    not _navigateur_pret(),
    reason="navigateur absent : ces bancs mesurent le rendu RÉELLEMENT servi",
)


@pytest.fixture(scope="module")
def navigateur():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch()
        yield nav
        nav.close()


@pytest.fixture(scope="module")
def page_briefing(navigateur):
    """Page nue portant le vrai `vx-core.js` et les fonctions d'Aujourd'hui.

    `$`, `esc` et `E` vivent dans l'IIFE de la page : on les redonne à
    l'identique, rien de plus, pour que les fonctions extraites s'exécutent
    dans les mêmes conditions qu'en production.
    """
    pg = navigateur.new_page(viewport={"width": 390, "height": 900})
    pg.set_content("<!doctype html><html><body>"
                   "<main id='vx-content'><div id='vx-alerts'></div>"
                   "<div id='vx-opp-posture'></div></main></body></html>")
    pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
    prelude = (
        "const $=(id)=>document.getElementById(id);"
        "function esc(s){return String(s??'').replace(/[<>&\"]/g,"
        "c=>({'<':'&lt;','>':'&gt;','&':'&amp;','\"':'&quot;'}[c]));}"
        "let __alerts=[];const E=()=>({alerts:()=>__alerts});"
    )
    js = briefing._JS
    pg.add_script_tag(content=(
        prelude
        + _extraire_fonction(js, "kpiCell")
        + "\n" + _extraire_fonction(js, "loadAlerts")
        + "\nwindow.kpiCell=kpiCell;window.loadAlerts=loadAlerts;"
        + "window.__setAlerts=(a)=>{__alerts=a;};"))
    yield pg
    pg.close()


# ── (a) La carte centrale sait se dater ──────────────────────────────
def test_le_brief_est_date_par_un_instant_et_non_par_une_heure_nue():
    """AVANT : as_of = '19:49:23' (heure murale nue) → `VX.freshness._ms` rend
    `null` → « Âge inconnu », sans info-bulle. APRÈS : as_of = scan_ts_h."""
    scan = {"updated": SCAN_UPDATED, "scan_ts_h": SCAN_TS_H, "source": "yfinance"}
    as_of = briefing.build_editorial(scan)["as_of"]
    assert as_of == SCAN_TS_H, (
        "le brief se date de %r alors que le scan sert l'instant %r : la carte "
        "centrale d'Aujourd'hui affiche « Âge inconnu » quand ses voisines "
        "affichent un âge." % (as_of, SCAN_TS_H))


@pytest.mark.parametrize("dispo", [{"scan_ts_h": SCAN_TS_H},
                                   {"scan_ts": 1788716963.687278}])
def test_l_instant_servi_par_le_scan_l_emporte_sur_l_heure_murale(dispo):
    """La propriété, pas la chaîne : DÈS QU'un instant est servi, `as_of` doit
    être cet instant. `HH:MM:SS` seul n'en est pas un — aucun consommateur ne
    peut en déduire un âge, et c'est exactement ce que la carte a affiché."""
    scan = dict(dispo, updated=SCAN_UPDATED)
    as_of = str(briefing.build_editorial(scan)["as_of"])
    assert not re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", as_of), (
        "as_of = %r alors que le scan sert %r : une heure murale nue préférée "
        "à un instant." % (as_of, sorted(dispo)))


def test_le_brief_prefere_l_instant_mais_ne_perd_jamais_la_datation():
    """Repli mesuré : un scan qui ne sert que `updated` garde son ancienne
    valeur plutôt que de perdre toute datation (aucune régression imposée aux
    déploiements qui n'ont pas `scan_ts_h`)."""
    assert briefing.build_editorial({"updated": SCAN_UPDATED})["as_of"] == SCAN_UPDATED


# ── (b) L'instant du scan est posé dans la page ──────────────────────
def test_la_page_pose_l_instant_du_scan_quand_le_scan_se_date():
    """AVANT : rien dans le DOM ne portait l'instant du scan, donc la carte
    « Posture du comité » n'avait aucun repli et rendait « Âge inconnu ».
    APRÈS : `[data-scan-ts]` porte l'instant servi."""
    html = briefing.render({"scan_ts_h": SCAN_TS_H, "updated": SCAN_UPDATED})
    m = re.search(r'class="vx-page-header"[^>]*data-scan-ts="([^"]+)"', html)
    assert m, "aucun [data-scan-ts] dans l'en-tête de page"
    assert m.group(1) == SCAN_TS_H


def test_l_attribut_disparait_quand_le_scan_ne_date_rien():
    """Un attribut VIDE se lit comme une date illisible. Absence d'instant =
    absence d'attribut, jamais `data-scan-ts=""`."""
    html = briefing.render({"updated": SCAN_UPDATED})
    m = re.search(r'class="vx-page-header"([^>]*)>', html)
    assert m, "en-tête de page introuvable"
    assert "data-scan-ts" not in m.group(1), (
        "le scan ne sert aucun instant : la page ne doit pas prétendre en "
        "porter un — attributs rendus : %r" % m.group(1))
    assert "%%SCANTS%%" not in html, "gabarit non substitué servi au navigateur"


@navigateur_requis
def test_la_posture_du_comite_se_date_du_scan_et_nomme_cette_provenance(navigateur):
    """AVANT : « Âge inconnu · comité Différé » — un mode affirmé sans âge.
    APRÈS : un `data-ts` exploitable, et le pied DIT que la date vient du scan.

    On exécute la construction réellement servie : la page rendue par
    `briefing.render`, dont on ne stimule que la lecture de `[data-scan-ts]`.
    """
    pg = navigateur.new_page()
    pg.set_content(briefing.render({"scan_ts_h": SCAN_TS_H}))
    lu = pg.evaluate("() => {const h=document.querySelector('[data-scan-ts]');"
                     "return h?h.getAttribute('data-scan-ts'):null;}")
    pg.close()
    assert lu == SCAN_TS_H, (
        "le client ne retrouve pas l'instant du scan dans le DOM : la carte "
        "« Posture du comité » retombe sur « Âge inconnu ».")
    #  La source du pied doit NOMMER le repli : dater du scan sans le dire
    #  ferait passer l'heure du scan pour celle de `/api/command`.
    fonction = _extraire_fonction(briefing._JS, "loadOpportunities")
    assert "data-scan-ts" in fonction and "daté du scan" in fonction, (
        "le pied doit lire l'instant du scan ET dire d'où il vient.")


# ── (c) Le radar d'alertes porte une fraîcheur MESURÉE ───────────────
@navigateur_requis
def test_le_radar_d_alertes_porte_un_age_exploitable(page_briefing):
    """AVANT : zéro `.vx-update` dans `#vx-alerts` — la carte ne se datait pas.
    APRÈS : un `.vx-update[data-ts]` bâti sur le `ts` que sert réellement
    `/api/alerts/status`."""
    ts = 1788718928
    page_briefing.evaluate(
        """async (ts) => {
             window.__setAlerts([]);
             VX.fetch = (u) => Promise.resolve(
               u.indexOf('/api/alerts/status') === 0 ? {fired:{}, ts:ts}
               : {alerts:[['\\u{1F7E0}','CONCENTRATION','Secteur trop concentré.']]});
             await loadAlerts();
           }""", ts)
    lu = page_briefing.evaluate(
        """() => {const u=document.querySelector('#vx-alerts .vx-update');
             return u?{ts:u.getAttribute('data-ts'), mode:u.getAttribute('data-mode'),
                       txt:u.textContent}:null;}""")
    assert lu, "aucune fraîcheur rendue par la carte Alertes"
    assert lu["ts"] == str(ts * 1000), (
        "l'âge n'est pas celui que la source a mesuré : %r" % lu)
    assert lu["mode"] == "delayed"


@navigateur_requis
def test_sans_horodatage_servi_le_radar_n_affirme_aucun_mode(page_briefing):
    """Règle déjà tenue par `newsPied` dans le même fichier : un mode servi
    (« Différé ») ne se pose pas d'office sur une charge dont rien n'est daté.
    L'erreur, l'absence et le zéro restent distincts (invariant 4)."""
    page_briefing.evaluate(
        """async () => {
             window.__setAlerts([]);
             VX.fetch = () => Promise.resolve({});
             await loadAlerts();
           }""")
    mode = page_briefing.evaluate(
        """() => {const u=document.querySelector('#vx-alerts .vx-update');
                  return u?u.getAttribute('data-mode'):'ABSENT';}""")
    assert mode != "delayed", (
        "« Différé » affirmé sur une charge sans horodatage : c'est l'étiquette "
        "d'une donnée servie posée sur une absence de mesure.")


@navigateur_requis
def test_une_alerte_declenchee_dit_quand_et_a_quel_prix(page_briefing):
    """AVANT : « déclenchée » nu — un franchissement d'il y a trois jours se
    lisait comme un franchissement de la minute. `terminal.py` persiste
    pourtant `ts` et `price` à l'instant du franchissement."""
    page_briefing.evaluate(
        """async () => {
             window.__setAlerts([{id:'a1', sym:'KO', cond:'above', level:70,
                                  active:true, note:''}]);
             VX.fetch = (u) => Promise.resolve(
               u.indexOf('/api/alerts/status') === 0
                 ? {fired:{a1:{id:'a1', sym:'KO', cond:'above', level:70,
                               price:71.5, ts: Math.floor(Date.now()/1000) - 7200}},
                    ts: Math.floor(Date.now()/1000)}
                 : {});
             await loadAlerts();
           }""")
    txt = page_briefing.evaluate(
        """() => {const b=[...document.querySelectorAll('#vx-alerts .vx-badge')]
                    .find(x=>/déclenchée/.test(x.textContent));
                  return b?b.textContent:null;}""")
    assert txt, "aucun badge « déclenchée » rendu"
    assert re.search(r"\d", txt), (
        "le badge « déclenchée » ne porte ni heure ni prix : %r — il ne "
        "distingue pas un franchissement d'il y a deux heures d'un "
        "franchissement de la minute." % txt)


# ── (d) Un tiret EXPLIQUÉ, jamais muet ───────────────────────────────
@navigateur_requis
def test_une_tuile_sans_valeur_nomme_la_cause(page_briefing):
    """AVANT : SMI, USD/CHF et ETH rendaient « — / n/d » avec `title` ABSENT.
    APRÈS : la tuile porte la cause mesurée — l'instrument n'est pas dans la
    charge du scan, et le scan dit qui l'a servie."""
    html = page_briefing.evaluate(
        "() => kpiCell('SMI', null, {source:'yfinance'}, 2)")
    page_briefing.evaluate("(h) => {document.body.insertAdjacentHTML('beforeend',h);}",
                           html)
    lu = page_briefing.evaluate(
        """() => {const t=[...document.querySelectorAll('.vx-idx-tile')]
                    .find(x=>/SMI/.test(x.textContent));
                  return {title:t.getAttribute('title')||'',
                          absent:t.getAttribute('data-absent'),
                          valeur:(t.querySelector('.vx-kpi-value')||{}).textContent,
                          delta:(t.querySelector('.vx-kpi-delta')||{}).textContent};}""")
    assert lu["valeur"].strip() == "—", "la valeur absente doit rester un tiret"
    assert lu["absent"] == "1"
    assert "SMI" in lu["title"] and "yfinance" in lu["title"], (
        "tiret MUET : la tuile ne dit ni quel instrument manque ni qui a servi "
        "le scan — title=%r" % lu["title"])
    assert lu["delta"].strip() != "n/d", (
        "« n/d » ne nomme rien : ni l'absence, ni sa cause.")


@navigateur_requis
def test_une_tuile_qui_porte_une_valeur_ne_porte_aucune_excuse(page_briefing):
    """Témoin négatif : l'explication n'apparaît QUE là où il manque quelque
    chose. Une tuile alimentée ne doit ni `title`, ni `data-absent`."""
    html = page_briefing.evaluate(
        "() => kpiCell('S&P 500', {last:7719, change:-0.38}, {source:'yfinance'}, 2)")
    assert "data-absent" not in html and "title=" not in html, html[:200]


# ── (f) Chaque colonne du Calendrier porte son propre nom ────────────
@pytest.fixture(scope="module")
def agenda_calendrier(navigateur):
    """Fait BOOTER `calendar.js` sur un `/cal-feed` de laboratoire, puis rend
    le tableau Agenda. C'est le script servi qui construit le tableau : le banc
    mesure l'appariement en-tête ↔ cellule, jamais une chaîne figée."""
    pg = navigateur.new_page(viewport={"width": 1600, "height": 1000})
    pg.set_content(
        "<!doctype html><html><body><main id='vx-content'>"
        "<div data-cal-view='agenda'></div>"
        "<div id='vx-cal-fraicheur'></div><div id='vx-cal-couverture'></div>"
        "<div id='vx-cal-compte'></div><div id='vx-cal-timeline'></div>"
        "<div id='vx-cal-positions'></div><div id='vx-cal-table'></div>"
        "</main></body></html>")
    pg.evaluate("""() => {
        window.__LOT = {demo:false, ts: 1788717119.44, updated:'19:51 06/09',
          source:'yfinance', macro:[],
          items:[{sym:'GME', date:'2026-09-08', dte:2, source:'yfinance',
                  confirmation:'date fournisseur, non confirmée par l’émetteur'}]};
        window.fetch = () => Promise.resolve({ok:true, json:()=>Promise.resolve(window.__LOT)});
      }""")
    pg.add_script_tag(content=CALENDRIER_JS.read_text(encoding="utf-8"))
    pg.wait_for_selector("#vx-cal-table table", timeout=10000)
    donnees = pg.evaluate("""() => {
        const t=document.querySelector('#vx-cal-table table');
        return {th:[...t.querySelectorAll('thead th')].map(x=>x.textContent.trim()),
                td:[...t.querySelectorAll('tbody tr:first-child td')]
                     .map(x=>x.textContent.trim())};}""")
    pg.close()
    return donnees


@navigateur_requis
def test_aucune_colonne_de_l_agenda_ne_porte_le_nom_d_une_autre(agenda_calendrier):
    """AVANT : ['Date','Échéance (j)','Type','Événement','Instrument','Date',
    'Source'] — DEUX colonnes « Date ». Un en-tête dupliqué rend l'une des deux
    colonnes illisible par construction."""
    th = agenda_calendrier["th"]
    doublons = sorted({t for t in th if th.count(t) > 1})
    assert not doublons, (
        "en-têtes dupliqués %r dans %r : le lecteur ne peut pas savoir ce que "
        "porte chaque colonne." % (doublons, th))


@navigateur_requis
def test_la_colonne_de_confirmation_est_nommee_par_ce_qu_elle_contient(agenda_calendrier):
    """La propriété, pas la chaîne : la cellule qui porte le niveau de
    confirmation servi par `/cal-feed` doit se trouver sous un en-tête qui parle
    de confirmation — et pas sous « Date »."""
    th, td = agenda_calendrier["th"], agenda_calendrier["td"]
    assert len(th) == len(td), (
        "%d en-têtes pour %d cellules : le tableau ne s'aligne pas."
        % (len(th), len(td)))
    idx = [i for i, c in enumerate(td) if "confirm" in c.lower()]
    assert idx, ("aucune cellule ne porte le niveau de confirmation servi : "
                 "cellules=%r" % (td,))
    for i in idx:
        assert "confirmation" in th[i].lower(), (
            "la cellule %r vit sous l'en-tête %r : le lecteur lit un niveau de "
            "confirmation en croyant lire une %s." % (td[i], th[i], th[i].lower()))


# ── (g) Le repli de datation doit être LISIBLE par le client ─────────
#
#  Contrôle adverse du 06/09/2026. Le lot pose `[data-scan-ts]` pour que la
#  carte « Posture du comité » ait un âge. Mesuré dans Chromium sur le
#  `vx-core.js` servi, le repli `scan_ts` (époque) ne l'avait pas :
#
#      render({'scan_ts': 1788719544.6501086})
#        -> data-scan-ts="1788719544.6501086"
#        -> VX.freshness._ms(...) = null      (new Date -> « Invalid Date »)
#        -> pied : « Âge inconnu · comité — daté du scan qui l'a produit
#                    Différé », data-mode="delayed", data-ts ABSENT
#
#  soit le défaut (b) reproduit, aggravé d'une provenance affirmée sans date.
#  La chaîne restait *truthy*, donc `cTs` valait vrai et le mode était affirmé.
#  `build_editorial` convertissait déjà l'époque en ISO dans le MÊME fichier ;
#  `render()` ne le faisait pas. La conversion est désormais partagée.
@navigateur_requis
@pytest.mark.parametrize("scan,attendu_present", [
    ({"scan_ts_h": SCAN_TS_H}, True),
    ({"scan_ts": 1788719544.6501086}, True),
    ({"updated": SCAN_UPDATED}, False),
])
def test_l_instant_pose_dans_la_page_est_lisible_par_l_analyseur_du_client(
        page_briefing, scan, attendu_present):
    """La propriété mesurée est « le client sait dater cet attribut », pas la
    forme de la chaîne : on la passe à `VX.freshness._ms`, l'unique analyseur
    d'horodatage du client, dans un vrai Chromium."""
    html = briefing.render(scan)
    m = re.search(r'class="vx-page-header"[^>]*data-scan-ts="([^"]*)"', html)
    if not attendu_present:
        assert m is None, (
            "le scan ne date rien : la page ne doit poser aucun instant "
            "(attribut trouvé : %r)" % (m.group(1) if m else None))
        return
    assert m, "aucun [data-scan-ts] alors que le scan sert un instant : %r" % scan
    lu = page_briefing.evaluate("(t) => VX.freshness._ms(t)", m.group(1))
    assert lu is not None, (
        "data-scan-ts=%r : l'analyseur du client rend `null`, donc le pied de "
        "« Posture du comité » affiche « Âge inconnu » tout en affirmant "
        "« Différé » et « daté du scan qui l'a produit » — le défaut que ce "
        "repli devait supprimer." % m.group(1))


# ── (h) Le pied du radar parle français, pas HTTP ────────────────────
@navigateur_requis
def test_le_radar_d_alertes_ne_montre_aucun_chemin_d_api(page_briefing):
    """Contrôle adverse : le pied ajouté par ce lot rendait « 2 alerte(s) de
    risque (issues de /api/command, non datées par la source) » — mesuré dans
    Chromium sur la fonction servie. C'était le seul texte visible du produit
    à nommer une route interne. Le banc mesure la PROPRIÉTÉ (aucun chemin
    d'API dans le texte lu par l'utilisateur), pas une formulation."""
    page_briefing.evaluate(
        """async () => {
             window.__setAlerts([{id:'a1', sym:'KO', cond:'above', level:70,
                                  active:true, note:''}]);
             VX.fetch = (u) => Promise.resolve(
               u.indexOf('/api/alerts/status') === 0
                 ? {fired:{}, ts: Math.floor(Date.now()/1000)}
                 : {alerts:[['A','CONCENTRATION','Secteur trop concentre.']]});
             await loadAlerts();
           }""")
    txt = page_briefing.evaluate(
        """() => {const h=document.getElementById('vx-alerts');
                  return h ? h.innerText : '';}""")
    assert txt.strip(), "la carte Alertes n'a rien rendu"
    routes = re.findall(r"/api/[a-z0-9/_-]+", txt)
    assert not routes, (
        "chemin(s) d'API dans le texte lu par l'utilisateur : %r — le contrat "
        "demande du français clair, et la provenance a un nom en français."
        % routes)
