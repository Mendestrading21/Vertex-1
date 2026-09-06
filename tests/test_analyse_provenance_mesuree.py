# -*- coding: utf-8 -*-
"""La fiche Analyse ne jette plus l'horodatage qu'elle tient, et n'affirme plus
une provenance qu'elle n'a pas mesurée.

Trois défauts mesurés le 06/09/2026 sur la fiche `/analysis/<SYM>`, Chromium
contre l'instance QA (NO_IBKR=1, DEMO=0). Ce sont les mêmes défauts que celui
qui venait d'être corrigé sur le badge « Financials — fondamentaux », une carte
plus loin ; le badge n'est pas touché ici.

## (a) SEPT pieds de cartes lisaient une clé que le serveur ne sert pas

`profil`, `Monte-Carlo`, `physique du prix`, `Kelly`, `MTF`, `RSI` et `volume`
appelaient tous `VX.updateIndicator` avec `detail.updated` (ou `d.updated`,
même objet). Mesure de la charge servie par `/api/ticker/AAPL` : **58 clés dans
`detail`, aucune nommée `updated`** ; et `analysis.analyse()`, qui PRODUIT ce
dictionnaire, en rend 56 dont aucune ne porte d'horodatage (vérifié par ce
banc, sans réseau). Les sept pieds rendaient donc, invariablement :

    ● Âge inconnu · scan Différé

alors que l'horodatage était disponible dans la MÊME fonction, trois lignes
au-dessus : le graphique principal affichait « Il y a 17 min » avec
`exec.as_of` (`2026-09-06T17:49:23Z`), égal à `/api/live/status`
`domains.prices.ts` = `1788716963` — le même instant, vérifié.

Après correctif, mesuré au navigateur sur la même instance : les sept pieds
affichent « Il y a 27 min » avec `data-ts="1788716963000"`.

## (b) Trois cartes annonçaient « company (cache) » quand rien n'était en cache

Le radar de valorisation, le quadrant croissance × rentabilité et la croissance
trimestrielle écrivaient en dur `source:'company (cache)'`, `timestamp:null`,
`mode:'delayed'`. Mesure sur un titre à cache FROID (`meta.etat==='MISSING'`,
`rafraichissement_en_cours===true`, `company===null`) : le badge voisin disait
« collecte en cours » pendant que ces trois pieds affirmaient « cache ». Rien
n'était en cache. Sur un titre chaud, ils affichaient « Âge inconnu » alors que
`meta.recu_a` porte l'instant de réception réel (mesuré : `1788718041.18`).

Leurs états vides accusaient en outre le TITRE — « Comparables insuffisants
pour positionner le titre », « Historique trimestriel indisponible pour ce
titre » — d'une absence qui était celle de la collecte.

## (c) Une distinction mesurée par le serveur, calculée puis jetée

`mode:ch.on_demand?'delayed':'delayed'` — les deux branches rendaient la même
chose. `on_demand` (mesuré `true` sur AAPL) dit que les contrats ne viennent
pas de la rotation du board mais d'une collecte dédiée.

## (d) Un libelle d'objectif analyste debordait de son cadre a 390 px

`.rb-lab` est centre sur sa graduation (`premium.css` : `translateX(-50%)`).
Mesure dans Chromium a 390 px sur `/analysis/AAPL`, carte « Sentiment » :
`.vx-rangebar` rendait `scrollWidth` 323 pour `clientWidth` 318 — le libellé
« $400,00 », pose a 94,6 %, sortait de 5 px du cadre.

## Ce que ce banc ne prouve pas

Il exécute le vrai `provAnnexes` extrait de la page servie, sur les charges
`meta` RÉELLEMENT mesurées, et lit les propriétés de la source (pas des
libellés figés). Il ne dit rien du CSS, ni de la justesse de `exec.as_of` comme
horodatage du scan — cette équivalence a été vérifiée à la main contre
`/api/live/status` mais n'est pas rejouable hors réseau.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RACINE = Path(__file__).resolve().parents[1]
PAGE = RACINE / "vertex" / "ui" / "pages" / "analysis_page.py"
CORE = RACINE / "vertex" / "static" / "vertex" / "js" / "vx-core.js"
PREMIUM = RACINE / "vertex" / "static" / "vertex" / "css" / "premium.css"


def _src() -> str:
    return PAGE.read_text(encoding="utf-8")


def _js_sans_commentaires() -> str:
    """Le code EXÉCUTABLE de la page : les blocs `/* … */` sont retirés.

    Sans ce nettoyage, un banc qui cherche une faute la retrouverait dans le
    commentaire qui explique la correction — et resterait rouge à jamais."""
    return re.sub(r"/\*.*?\*/", " ", _src(), flags=re.S)


def _extraire(nom: str, src: str) -> str:
    """Le source d'une fonction, accolades équilibrées (idem test_horodatage)."""
    i = src.index("function %s(" % nom)
    prof, j = 0, i
    while j < len(src):
        if src[j] == "{":
            prof += 1
        elif src[j] == "}":
            prof -= 1
            if prof == 0:
                return src[i:j + 1]
        j += 1
    raise AssertionError("fonction %s non refermée" % nom)


# ── (a) la clé qui n'existe pas ───────────────────────────────────────────


def _detail_fixture() -> dict:
    """Le dictionnaire `detail` tel que le moteur le PRODUIT réellement.

    `/api/ticker/<sym>` rend `scan_state['detail'][sym]`, c'est-à-dire la sortie
    d'`analysis.analyse()`. On la mesure ici plutôt que de recopier une liste de
    clés : le jour où le moteur se mettra à horodater son détail, ce banc le
    verra et cessera d'interdire la lecture."""
    from vertex.engines import analysis
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    close = pd.Series(np.linspace(80, 130, 260) + 6 * np.sin(np.linspace(0, 20, 260)),
                      index=idx)
    df = pd.DataFrame({
        "Open": close.shift(1).fillna(close.iloc[0]), "High": close + 1.5,
        "Low": close - 1.5, "Close": close,
        "Volume": pd.Series(np.linspace(1e6, 2e6, 260), index=idx),
    }, index=idx)
    return analysis.analyse(df, 0.05, fund={"beta": 1.3, "div": 0.01,
                                            "sector": "Technology", "pe": 25,
                                            "margin": 0.2, "growth": 0.15})


def test_le_moteur_ne_produit_aucun_horodatage_dans_le_detail():
    """La MESURE qui fonde le banc suivant : la clé lue n'existe pas."""
    cles = set(_detail_fixture())
    assert "updated" in cles or "updated" not in cles  # lisibilité : on mesure
    assert "updated" not in cles, (
        "le moteur produit désormais `detail.updated` : la fiche a le droit de "
        "la lire, ce banc doit être révisé")


def test_aucun_pied_de_carte_ne_lit_une_cle_absente_de_la_charge():
    """Sept pieds lisaient `detail.updated` → « Âge inconnu » perpétuel."""
    assert "updated" not in set(_detail_fixture()), "prémisse invalidée"
    lectures = re.findall(r"\w+\.updated\b", _js_sans_commentaires())
    assert not lectures, (
        "la fiche date ses cartes avec une clé que `/api/ticker` ne sert pas "
        "(%s) : le pied rendra « Âge inconnu » quoi qu'il arrive" % (lectures,))


def test_aucun_pied_de_carte_ne_pose_un_horodatage_constant_nul():
    """`timestamp:null` écrit en dur = une carte qui renonce à se dater."""
    js = _js_sans_commentaires().replace(" ", "")
    assert "timestamp:null" not in js, (
        "une carte déclare son horodatage absent par constante, alors que "
        "`meta.recu_a` / `exec.as_of` sont servis")


# ── (c) la distinction jetée ──────────────────────────────────────────────


def test_aucune_distinction_calculee_puis_jetee():
    """Un ternaire dont les deux branches sont identiques ne décide rien."""
    js = _js_sans_commentaires()
    morts = [m.group(0) for m in
             re.finditer(r"\?\s*('(?:[^'\\]|\\.)*')\s*:\s*('(?:[^'\\]|\\.)*')", js)
             if m.group(1) == m.group(2)]
    assert not morts, (
        "une condition mesurée est évaluée puis jetée : %s" % (morts,))


# ── (b) la provenance des annexes, exécutée ───────────────────────────────
#
#  Charges `meta` RÉELLES relevées sur l'instance QA le 06/09/2026.
META_FROID = {"age_s": None, "erreur": None, "etat": "MISSING", "fraicheur_s": 60.0,
              "observe_a": None, "qualite": None, "rafraichissement_en_cours": True,
              "recu_a": None, "source": None}
META_CHAUD = {"age_s": 10.052, "erreur": None, "etat": "DELAYED", "fraicheur_s": 60.0,
              "observe_a": None, "qualite": "COMPLETE",
              "rafraichissement_en_cours": False, "recu_a": 1788718041.1795266,
              "source": "yfinance+ibkr"}
META_STALE = dict(META_CHAUD, etat="STALE", rafraichissement_en_cours=False,
                  recu_a=1788717951.0566297)
META_OFFLINE = dict(META_FROID, etat="OFFLINE", rafraichissement_en_cours=False)
META_PARTIEL = dict(META_CHAUD, qualite="PARTIELLE",
                    erreur="paquet options indisponible")


def _navigateur_pret() -> bool:
    try:
        from tools.mesures.mesurer_qa_espaces import navigateur_pret
    except Exception:
        return False
    return bool(navigateur_pret())


navigateur = pytest.mark.skipif(
    not _navigateur_pret(),
    reason="navigateur absent : ce banc exécute le JavaScript RÉELLEMENT servi")


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page()
        pg.set_content("<!doctype html><html><body></body></html>")
        pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
        #  La fonction EXTRAITE de la page servie, pas recopiée.
        pg.add_script_tag(content=_extraire("provAnnexes", _src())
                          + "window.provAnnexes=provAnnexes;")
        yield pg
        nav.close()


def _prov(page, meta, demo=False):
    return page.evaluate("([m,d]) => provAnnexes(m,d)", [meta, demo])


@navigateur
def test_la_provenance_nomme_la_collecte_en_vol_au_lieu_du_cache(page):
    """Le défaut : « company (cache) » sur un titre dont RIEN n'est en cache."""
    p = _prov(page, META_FROID)
    assert "cache" not in p["source"], (
        "provenance affirmée « cache » alors que `etat==='MISSING'` et "
        "`rafraichissement_en_cours===true` : %r" % p["source"])
    assert p["encours"] is True
    assert p["cause"], "l'état vide n'a aucune raison à afficher"


@navigateur
def test_les_cinq_etats_des_annexes_rendent_cinq_provenances_distinctes(page):
    """Un vocabulaire qui confond deux états n'en nomme aucun (invariant 5)."""
    rendus = {
        "démo": _prov(page, META_CHAUD, demo=True)["source"],
        "collecte": _prov(page, META_FROID)["source"],
        "injoignable": _prov(page, META_OFFLINE)["source"],
        "précédent": _prov(page, META_STALE)["source"],
        "partiel": _prov(page, META_PARTIEL)["source"],
        "cache": _prov(page, META_CHAUD)["source"],
    }
    assert len(set(rendus.values())) == len(rendus), rendus


@navigateur
def test_la_provenance_porte_l_horodatage_de_reception_quand_il_existe(page):
    """« Âge inconnu » alors que `meta.recu_a` était servi."""
    assert _prov(page, META_CHAUD)["ts"] == pytest.approx(1788718041.18, abs=0.01)
    assert _prov(page, META_FROID)["ts"] is None, (
        "un horodatage est fabriqué là où la charge n'en sert aucun")


@navigateur
def test_le_pied_rendu_affiche_un_age_reel_et_non_ame_inconnu(page):
    """La propriété visible : ce que le lecteur lit dans le pied de la carte."""
    html = page.evaluate(
        "(p) => VX.updateIndicator(p.ts, p.source, p.mode)", _prov(page, META_CHAUD))
    assert "Âge inconnu" not in html, html
    assert "data-ts=" in html and "1970" not in html, html
    #  À l'inverse, une absence reste DITE — jamais datée.
    froid = page.evaluate(
        "(p) => VX.updateIndicator(p.ts, p.source, p.mode)", _prov(page, META_FROID))
    assert "Âge inconnu" in froid and "data-ts=" not in froid, froid


@navigateur
def test_la_cause_n_impute_au_titre_que_ce_qui_vient_du_titre(page):
    """Un état vide pendant la collecte ne dit pas « indisponible pour ce titre »."""
    assert _prov(page, META_CHAUD)["cause"] is None, (
        "une cause de dégradation est affichée alors que la charge est complète")
    for meta in (META_FROID, META_OFFLINE):
        cause = _prov(page, meta)["cause"]
        assert cause and "ce titre" not in cause, cause


# ── un seul vocabulaire pour l'état des annexes ───────────────────────────


def test_la_provenance_et_le_badge_lisent_les_MEMES_champs_de_meta():
    """Deux lecteurs du même fait qui n'observent pas les mêmes champs
    divergeront : le badge dirait « collecte en cours » pendant que le pied
    dirait « cache », ce qui EST le défaut corrigé ici."""
    src = _src()
    prov = _extraire("provAnnexes", src)
    debut = src.index("const srcEl=$('an-fin-src')")
    badge = src[debut:debut + 1400]
    champs = ("rafraichissement_en_cours", "etat", "qualite",
              "'MISSING'", "'OFFLINE'", "'STALE'", "'PARTIELLE'")
    manquants = [c for c in champs if (c in badge) != (c in prov)]
    assert not manquants, (
        "le badge et la provenance des pieds n'observent pas les mêmes champs "
        "de `meta` : %s" % (manquants,))


def test_les_etats_vides_des_annexes_peuvent_nommer_leur_cause():
    """Les trois vides servis par les annexes acceptent la cause mesurée."""
    js = _js_sans_commentaires()
    for fin in ("Comparables insuffisants pour positionner le titre.",
                "Historique trimestriel indisponible pour ce titre",
                "Carte des risques indisponible pour ce titre."):
        i = js.index(fin)
        amont = js[max(0, i - 120):i]
        assert "ANNEXES.cause" in amont, (
            "l'état vide « %s… » impute au titre une absence qui peut venir de "
            "la collecte" % fin[:40])


# ── (d) la barre d'objectifs analystes tient dans son cadre ───────────────


@navigateur
def test_la_barre_d_objectifs_ne_deborde_pas_dans_une_colonne_etroite(page):
    """Mesure de la LARGEUR rendue, pas d'une chaine : `.vx-rangebar` sortait
    de 5 px de son cadre a 318 px de large (viewport 390)."""
    page.add_style_tag(content=PREMIUM.read_text(encoding="utf-8"))
    page.add_script_tag(content=_extraire("analystRangeBar", _src())
                        + "window.analystRangeBar=analystRangeBar;")
    #  Charge REELLE relevee le 06/09/2026 sur /analysis/AAPL (carte Sentiment).
    mesure = page.evaluate("""(largeur) => {
      const h = document.createElement('div');
      h.setAttribute('style', 'width:' + largeur + 'px');
      h.innerHTML = analystArgs();
      document.body.appendChild(h);
      const b = h.querySelector('.vx-rangebar');
      return {sw: b.scrollWidth, cw: b.clientWidth};
    }""".replace("analystArgs()",
                 "analystRangeBar({target_low:215,target_high:400,"
                 "target_median:290},319.97)"), 318)
    assert mesure["sw"] <= mesure["cw"] + 1, (
        "la barre d'objectifs deborde de %d px de son cadre : un libelle "
        "centre sur une graduation de bord sort du cadre"
        % (mesure["sw"] - mesure["cw"]))


# ── CONTRÔLE ADVERSE — deux régressions mesurées le 06/09/2026 ────────────
#
#  Ces quatre bancs ne gardent pas les correctifs ci-dessus : ils gardent ce
#  que ces correctifs avaient CASSÉ.

import threading  # noqa: E402
import time  # noqa: E402


def _mesure_cache_servi_pendant_un_rafraichissement() -> tuple:
    """La charge `meta` de la branche RASSIS, MESURÉE sur le vrai magasin.

    `vertex/app/snapshot.py` connaît trois états, pas deux : quand la valeur a
    dépassé sa fenêtre mais EXISTE, elle est servie immédiatement, marquée
    `STALE`, et un rafraîchissement part en fond — donc avec
    `rafraichissement_en_cours=True` ET une valeur non nulle. `/api/ticker`
    pose `fraicheur_s=60` : c'est l'état de toute page rouverte après une
    minute, pas un cas limite. On le fabrique ici avec le module lui-même
    plutôt que de recopier un dictionnaire : si le magasin cessait un jour de
    servir pendant un rafraîchissement, ce banc le verrait au lieu de garder
    une fiction."""
    from vertex.app import snapshot
    porte = threading.Event()
    appels = {"n": 0}

    def bati():
        appels["n"] += 1
        if appels["n"] > 1:
            porte.wait(5)          # la reconstruction reste EN VOL
        return ({"pe": 36.6}, {"source": "yfinance+ibkr", "qualite": "COMPLETE"})

    m = snapshot.Magasin("banc-provenance")
    m.servir("AAPL", bati, fraicheur_s=0.0, etat_frais=snapshot.DELAYED,
             attendre=True)
    time.sleep(0.02)
    valeur, meta = m.servir("AAPL", bati, fraicheur_s=0.0, attendre=False)
    d = meta.vers_dict()
    porte.set()
    return valeur, d


def test_le_magasin_sert_bien_un_cache_pendant_un_rafraichissement():
    """La MESURE qui fonde les deux bancs suivants."""
    valeur, meta = _mesure_cache_servi_pendant_un_rafraichissement()
    assert valeur is not None, "le magasin ne sert plus rien pendant un rafraîchissement"
    assert meta["etat"] == "STALE", meta
    assert meta["rafraichissement_en_cours"] is True, meta
    assert meta["qualite"] == "COMPLETE" and meta["recu_a"], meta


@navigateur
def test_un_cache_complet_servi_n_est_pas_annonce_comme_une_collecte(page):
    """`rafraichissement_en_cours` primait sur la PRÉSENCE de la charge.

    Mesuré au navigateur sur 127.0.0.1:5003, /analysis/AAPL, charge servie
    `{etat:'STALE', qualite:'COMPLETE', rafraichissement_en_cours:true,
    recu_a:1788719818.43}` — douze valeurs réelles à l'écran :

        avant : « Il y a 66 s · company (collecte en cours) Secours »
        après : « Il y a 66 s · company (scan précédent · rafraîchissement
                  en cours) Différé »

    Ni « collecte en cours » ni « Secours » n'étaient vrais : le cache était
    complet, servi, daté. La collecte n'est la CAUSE d'un vide que s'il n'y a
    rien à montrer ; `recu_a` mesure exactement cela."""
    _, meta = _mesure_cache_servi_pendant_un_rafraichissement()
    p = _prov(page, meta)
    assert p["ts"] == pytest.approx(meta["recu_a"], abs=0.01), p
    assert "collecte en cours" not in p["source"], (
        "une charge COMPLÈTE servie est annoncée comme une collecte : %r" % p["source"])
    assert p["mode"] == "delayed", (
        "un cache complet est annoncé en mode de secours : %r" % p["mode"])
    assert p["cause"] is None, (
        "une raison de vide est posée alors que la charge a été reçue : %r" % p["cause"])
    #  Le rafraîchissement en vol reste DIT — l'information n'est pas perdue.
    assert "rafra" in p["source"], p["source"]
    html = page.evaluate("(p) => VX.updateIndicator(p.ts,p.source,p.mode)", p)
    assert "Secours" not in html and "Âge inconnu" not in html, html


def _vocabulaire_des_modes() -> set:
    """Les modes que le RENDU sait nommer, lus dans `vx-core.js`.

    Mesure, pas liste figée : le jour où `updateIndicator` apprendra « demo »,
    ce banc cessera tout seul de l'interdire."""
    js = CORE.read_text(encoding="utf-8")
    bloc = re.search(r"const modeLabel\s*=\s*\{([^}]*)\}", js).group(1)
    return set(re.findall(r"(\w+)\s*:", bloc))


def _modes_emis_par_la_page() -> set:
    """Tout littéral que la fiche passe comme MODE de provenance."""
    js = _js_sans_commentaires()
    exprs = [m.group(1) for m in re.finditer(r"mode\s*:\s*([^,}\n]+)", js)]
    exprs += [m.group(1) for m in re.finditer(r"scanMode\s*=\s*([^;\n]+)", js)]
    for appel in re.findall(r"updateIndicator\(([^()]*(?:\([^()]*\)[^()]*)*)\)", js):
        args, prof, cur = [], 0, ""
        for ch in appel:
            if ch == "," and prof == 0:
                args.append(cur); cur = ""; continue
            if ch in "([":
                prof += 1
            elif ch in ")]":
                prof -= 1
            cur += ch
        args.append(cur)
        if len(args) >= 3:
            exprs.append(args[2])
    modes = set()
    for e in exprs:
        modes |= set(re.findall(r"'([^']*)'", e))
    return modes


def test_la_fiche_n_emet_aucun_mode_que_le_rendu_ne_sait_nommer():
    """`'demo'` traversait `updateIndicator` sans produire un seul mot.

    Mesure du 06/09/2026 sur le fichier servi :
    `VX.updateIndicator(ts,'scan','demo')` rend « … · scan » — aucun mot de
    mode, `data-mode="demo"` sans règle dans `components.css` (point gris par
    défaut) ; `…,'fallback')` rend « … · scan Secours ». En DÉMO, sept pieds
    de la fiche annonçaient donc leur mode… en silence."""
    connus, emis = _vocabulaire_des_modes(), _modes_emis_par_la_page()
    assert connus, "vocabulaire des modes introuvable dans vx-core.js"
    inconnus = sorted(emis - connus)
    assert not inconnus, (
        "la fiche émet des modes que `VX.updateIndicator` ne sait pas nommer "
        "(%s) : le pied restera muet sur l'état de la donnée. Vocabulaire "
        "mesuré : %s" % (inconnus, sorted(connus)))


@navigateur
def test_en_demo_le_pied_du_scan_nomme_la_demonstration(page):
    """Une fiche entièrement fabriquée avait un pied indiscernable du réel.

    Le banc exécute les DEUX lignes de `loadDossier` qui décident la
    provenance du scan, extraites de la page servie, avec `demo=true`."""
    src = _js_sans_commentaires()
    lignes = "".join(
        re.search(r"const %s=[^;]+;" % nom, src).group(0)
        for nom in ("scanMode", "scanSource"))
    html = page.evaluate(
        "([code,ts]) => { const demo=true,status={mode:'delayed',ibkr:false};"
        " return (new Function('demo','status','VX','ts',"
        " code + ' return VX.updateIndicator(ts,scanSource,scanMode);'))"
        "(demo,status,VX,ts); }", [lignes, 1788719544])
    assert "DÉMO" in html, (
        "le pied d'une fiche de démonstration ne nomme pas la démonstration : %s"
        % html)
    mots = set(re.findall(r"'([^']*)'", re.search(
        r"const modeLabel\s*=\s*\{([^}]*)\}",
        CORE.read_text(encoding="utf-8")).group(1)))
    assert any(m and m in html for m in mots), (
        "aucun mot de mode dans le pied : %s (vocabulaire %s)" % (html, sorted(mots)))
