# -*- coding: utf-8 -*-
"""Lot C-opportunites — la page Opportunites dit-elle ce qu'elle montre ?

Tout ce qui suit a ete MESURE dans Chromium sur l'instance QA (copie du depot,
`NO_IBKR=1`, `DEMO=0`, sans verrou), charge reelle : 513 lignes scorees,
11 secteurs servis, 96 contrats au board, 82 titres porteurs d'anomalies.
Zero erreur console avant comme apres.

## 1. La matrice secteur x statut filtrait sur la MAUVAISE cellule (grave)

`heatmapCard` (charts/heatmap.js) ecrit sa ligne d'en-tete directement dans
le `<table>`, sans `<thead>` : le navigateur l'enferme dans le `<tbody>` avec
les donnees, et le libelle de chaque ligne est un `<th>`. Le cablage du clic
comptait donc l'en-tete comme une ligne de donnees, et sautait la premiere
cellule de donnees avec un `.slice(1)` prevu pour un libelle en `<td>`.

Mesure du 06/09/2026, clic sur la cellule titree
« Technology · Radar : 3 titre(s) » :

| | secteur applique | statut applique | compteur |
|---|---|---|---|
| avant | `Industrials` | `Rejetee` | 20 / 513 |
| apres | `Technology` | `Radar` | 3 / 513 |

Et la colonne « Rejetee » n'etait cablee sur AUCUNE ligne : `style.cursor`
valait `default` sur ses 11 cellules (0 sur 66 aujourd'hui).

## 2. Une intensite d'anomalie maximale peinte en VERT (grave)

`heatCell` ne connaissait qu'un sens de lecture, « haut = bon ». La colonne
« Intensite » des Anomalies l'employait. Mesure du 06/09/2026 : LULU, niveau
ALERTE, intensite 100/100, couleur calculee `rgb(54, 200, 137)` — le vert que
la charte reserve au positif ; FICO, ALERTE, 100 : idem. Apres, sens
`risque` : `rgb(237, 101, 92)`.

## 3. Le donut des verdicts avait perdu TOUTES ses couleurs

Table de tons indexee en majuscules ('ACHAT') face a des libelles canoniques
('Achat'). Releve Chart.js du 06/09/2026 :
`backgroundColor = ["#8f8a83","#8f8a83","#8f8a83","#8f8a83"]` pour
Achat / Surveiller / Eviter / Attendre. Apres, la couleur vient du ton
canonique (`window.__VXVOCAB`) : quatre couleurs distinctes.

## 4. Deux cartes du Radar sans aucune provenance

Releve DOM du 06/09/2026 : « Entonnoir » et « Scores des resultats » ne
portaient aucun `.vx-update-age`, la vue Anomalies non plus (ni la carte des
types, ni la table). Seule « Selection » — un encart d'invite, sans chiffre —
peut legitimement ne pas dater.

## 5. La matrice totalisait 355 titres sous un KPI qui en annonce 513

158 lignes sur 513 n'ont AUCUN secteur servi par le scan. Elles ne peuvent
figurer dans aucune ligne de la matrice, et rien ne le disait.

## 6. La rampe de couleur de la matrice jugeait un simple effectif

Rampe DIVERGENTE (emeraude/corail) sur un COMPTE, et maximum pris sur
`Object.values(cnt)` — qui inclut les seaux des titres SANS secteur, jamais
affiches. Mesure du 06/09/2026 : maximum 64 contre 36 reellement peint ; fond
de « Technology · Rejetee : 28 » = `rgba(237,101,92,0.15)`. Desormais teinte
unique (`scale:'sequential'`) calibree sur les cellules visibles.

## 7. Une fraicheur qui ne mesurait pas l'age

« DERNIER SCAN 2026-09-06T17:49:23Z » — la chaine brute de la source — pendant
que tous les pieds de carte disaient « Il y a 18 min » ; et le badge
« Differee » sortait des qu'une source existait, identique a 18 minutes et a
six heures. Le seuil vient maintenant de `VX.freshness.THRESH`, la table du
produit (30 min), pas d'un choix local.

## Portee du banc

Ces mesures exigent un navigateur, une instance ouverte ET un scan qui sert
des lignes : sans l'un des trois, les tests s'ABSTIENNENT (ils ne « passent »
pas). `VERTEX_MESURE_BASE` designe l'instance de mesure ; par defaut
`http://127.0.0.1:5003`.

Deux gardiens ne tombaient PAS sur la version d'avant, et c'est voulu : les
sept vues sans erreur console, et les sept vues qui peignent un corps plutot
qu'un bandeau « Chargement impossible ». Ce sont des filets de regression —
le second a d'ailleurs attrape, pendant ce lot meme, un accent grave glisse
dans un gabarit JS qui avait tue la vue Options en silence (console vide,
corps de 72 caracteres).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
SONDE = RACINE / "tests" / "aides" / "sonde_opportunites.py"
BASE = os.environ.get("VERTEX_MESURE_BASE", "http://127.0.0.1:5003").rstrip("/")

#: Seules cartes autorisees a ne porter aucun horodatage : celles qui
#: n'affichent AUCUNE valeur mesuree tant qu'on n'a rien selectionne.
CARTES_SANS_CHIFFRE = {"Sélection", "Contrat sélectionné"}

_CACHE: dict = {}


def _instance_ouverte() -> bool:
    """Une instance QA OUVERTE, pas un ecran de code d'accès.

    Une instance derrière `VERTEX_CODE` servirait sa page de connexion : le
    banc « mesurerait » alors la mauvaise page en silence.
    """
    try:
        with urllib.request.urlopen(BASE + "/opportunities", timeout=8) as r:
            corps = r.read().decode("utf-8", "replace")
        return (r.status == 200 and 'id="op-body"' in corps
                and 'name="code"' not in corps and 'type="password"' not in corps)
    except Exception:  # noqa: BLE001
        return False


def _mesure() -> dict:
    """Lance la sonde navigateur UNE fois par session et rend son JSON."""
    if "r" in _CACHE:
        return _CACHE["r"]
    if not _instance_ouverte():
        _CACHE["r"] = {"ok": False, "motif": "aucune instance ouverte sur " + BASE}
        return _CACHE["r"]
    #  Sous-processus : `ib_async` applique `nest_asyncio` et l'API synchrone
    #  de Playwright refuse alors de demarrer dans le processus de test.
    proc = subprocess.run([sys.executable, str(SONDE), BASE],
                          capture_output=True, text=True, timeout=300,
                          encoding="utf-8", errors="replace")
    sortie = (proc.stdout or "").strip().splitlines()
    try:
        _CACHE["r"] = json.loads(sortie[-1]) if sortie else {
            "ok": False, "motif": "sonde muette : " + (proc.stderr or "")[-300:]}
    except Exception as exc:  # noqa: BLE001
        _CACHE["r"] = {"ok": False, "motif": "sortie illisible (%s) : %s"
                                             % (exc, (proc.stdout or "")[-300:])}
    return _CACHE["r"]


def _mesure_ou_abstention() -> dict:
    m = _mesure()
    if not m.get("ok"):
        pytest.skip("non mesure : " + str(m.get("motif")))
    return m


def _avec_donnees() -> dict:
    """Mesure ET scan non vide.

    Un scan en cours (`scan_status` RUNNING) ou degrade sert zero ligne : la
    page peint alors son etat vide, il n'y a ni matrice ni donut a juger.
    Mesure du 06/09/2026 : lance pendant un rescan, ce banc « echouait » sur
    une matrice vide — il aurait accuse la page d'un defaut qui n'existait
    pas. « Pas mesure » et « mesure fausse » ne se confondent pas.
    """
    m = _mesure_ou_abstention()
    if not m["screener"].get("scoreesServies"):
        pytest.skip("le scan courant ne sert aucune ligne scoree "
                    "(scan en cours ou degrade) : rien a juger")
    return m


# ────────────────────────────────────────────────────────── 1. la matrice

def test_le_clic_d_une_cellule_applique_le_secteur_et_le_statut_de_CETTE_cellule():
    """Avant : « Technology · Radar : 3 » -> Industrials / Rejetee, 20 titres."""
    m = _avec_donnees()
    clic = m["screener"].get("clic")
    assert clic, "aucune cellule chiffree dans la matrice : rien n'a pu etre clique"
    promis, obtenu = clic["promis"], clic["obtenu"]
    assert obtenu["secteur"] == promis["secteur"], (
        "la cellule promet le secteur %r, le filtre applique %r"
        % (promis["secteur"], obtenu["secteur"]))
    assert obtenu["statut"] == promis["statut"], (
        "la cellule promet le statut %r, le filtre applique %r"
        % (promis["statut"], obtenu["statut"]))


def test_le_compteur_apres_clic_vaut_le_nombre_ecrit_dans_la_cellule():
    """La cellule dit « 3 titre(s) » : le screener doit en afficher 3."""
    m = _avec_donnees()
    clic = m["screener"].get("clic")
    assert clic, "aucune cellule chiffree dans la matrice"
    assert clic["compteAffiche"] == clic["promis"]["compte"], (
        "cellule %r : %d titre(s) annonces, %s affiche(s) apres le clic"
        % (clic["promis"], clic["promis"]["compte"], clic["compteAffiche"]))


def test_toutes_les_cellules_de_la_matrice_sont_cliquables():
    """Avant : les 11 cellules de la colonne « Rejetee » restaient inertes."""
    m = _avec_donnees()
    mat = m["screener"]["matrice"]
    assert mat["cellules"] > 0, "matrice vide : rien a mesurer"
    assert mat["cellulesNonCliquables"] == 0, (
        "%d cellule(s) sur %d ne repondent pas au clic"
        % (mat["cellulesNonCliquables"], mat["cellules"]))


def test_la_matrice_avoue_les_titres_qu_elle_ne_peut_pas_ranger():
    """158 titres sur 513 n'ont aucun secteur servi : la carte doit le dire."""
    m = _avec_donnees()
    sans = m["screener"]["sansSecteur"]
    if not sans:
        pytest.skip("le scan courant sert un secteur pour chaque titre")
    somme = m["screener"]["matrice"]["sommeCellules"]
    total = m["screener"]["scoreesServies"]
    assert somme == total - sans, (
        "somme de la matrice %d, attendu %d (= %d titres - %d sans secteur)"
        % (somme, total - sans, total, sans))
    bornes = m["screener"]["matriceBornes"]
    assert str(sans) in bornes and str(total) in bornes, (
        "le pied de la matrice ne nomme pas les %d titres non rangeables "
        "sur %d : %r" % (sans, total, bornes))


def test_un_compte_de_titres_n_est_pas_peint_sur_une_rampe_bon_mauvais():
    """Un effectif n'est ni bon ni mauvais.

    Avant : la matrice employait la rampe DIVERGENTE de `heatmap.js` (emeraude
    haut / corail bas) sur un simple compte — mesure du 06/09/2026, fond de la
    cellule « Technology · Rejetee : 28 » = `rgba(237,101,92,0.15)`, et
    « Financial Services · Proche : 36 » en vert. Deux effectifs, deux
    jugements que la donnee ne porte pas. `heatmap.js` prevoit le cas non
    signe : `scale:'sequential'`, une seule teinte.

    Second defaut, meme cellule : le maximum de la rampe se prenait sur
    `Object.values(cnt)`, qui compte AUSSI les seaux des titres sans secteur,
    jamais affiches — 64 mesure contre 36 reellement peint.
    """
    m = _avec_donnees()
    mat = m["screener"]["matrice"]
    if not mat["cellules"]:
        pytest.skip("matrice vide")

    def rgb(couleur):
        nombres = [int(x) for x in re.findall(r"\d+", couleur or "")[:3]]
        return tuple(nombres) if len(nombres) == 3 else None

    signees = {rgb(m["screener"]["teintes"]["positive"]),
               rgb(m["screener"]["teintes"]["negative"])}
    fautives = [c for c in mat["fonds"] if rgb(c["fond"]) in signees]
    assert not fautives, (
        "%d cellule(s) de comptes peintes dans une couleur de jugement : %s"
        % (len(fautives), fautives[:4]))


# ─────────────────────────────────────────────── 2. le sens des couleurs

def test_une_intensite_d_anomalie_elevee_n_est_jamais_peinte_en_vert():
    """Avant : LULU / FICO, niveau ALERTE, intensite 100, rgb(54,200,137)."""
    m = _avec_donnees()
    an = m["anomalies"]
    vert = an["vert"]
    fautives = [x for x in an["intensites"]
                if x["valeur"] is not None and x["valeur"] >= 55
                and x["couleur"] == vert]
    assert not fautives, (
        "le maximum du desordre peint dans la couleur du positif (%s) : %s"
        % (vert, [(x["sym"], x["niveau"], x["valeur"]) for x in fautives]))


def test_les_colonnes_chiffrees_des_anomalies_portent_leur_unite():
    """« 100 » et « 27 » sont des echelles sur 100 ; le titre doit le dire."""
    m = _avec_donnees()
    entetes = m["anomalies"]["entetes"]
    if not entetes:
        pytest.skip("aucune anomalie dans le scan courant")
    for attendu in ("Intensité", "Score"):
        col = [h for h in entetes if h.startswith(attendu)]
        assert col, "colonne %r absente : %r" % (attendu, entetes)
        assert "/ 100" in col[0], (
            "la colonne %r ne porte pas son unite : %r" % (attendu, col[0]))


def test_le_donut_des_verdicts_distingue_les_verdicts_par_la_couleur():
    """Avant : quatre parts, une seule couleur (#8f8a83) — releve Chart.js."""
    m = _avec_donnees()
    donut = m["screener"].get("donut")
    if not donut or len(donut["labels"]) < 2:
        pytest.skip("moins de deux verdicts dans le scan courant")
    assert donut["distinctes"] >= 2, (
        "%d verdicts, une seule couleur %r : le donut ne dit plus rien"
        % (len(donut["labels"]), donut["couleurs"][:1]))


# ──────────────────────────────────────── 3. provenance de chaque carte

@pytest.mark.parametrize("vue", ["screener", "anomalies"])
def test_chaque_carte_chiffree_porte_son_horodatage(vue):
    """Avant : « Entonnoir », « Scores des resultats », et les deux cartes
    de la vue Anomalies, sans le moindre `.vx-update-age`."""
    m = _avec_donnees()
    nues = [t for t in m[vue]["cartesSansAge"] if t not in CARTES_SANS_CHIFFRE]
    assert not nues, (
        "vue %s : carte(s) chiffree(s) sans source ni horodatage : %s" % (vue, nues))


def test_la_table_des_anomalies_porte_sa_provenance():
    m = _avec_donnees()
    if not m["anomalies"]["entetes"]:
        pytest.skip("aucune anomalie dans le scan courant")
    assert m["anomalies"]["tableAvecAge"], (
        "la table des anomalies liste des intensites sans dire de quel scan "
        "elles viennent")


# ──────────────────────────── 3 bis. une fraicheur qui MESURE l'age

def test_le_dernier_scan_n_est_pas_affiche_en_horodatage_brut():
    """Avant : « 2026-09-06T17:49:23Z » dans la barre de contexte, pendant que
    TOUS les pieds de carte de la meme page disaient « Il y a 18 min »."""
    m = _avec_donnees()
    ctx = m["screener"]["contexte"]
    if not ctx["scanTexte"] or not ctx["scanTsH"]:
        pytest.skip("aucun horodatage de scan servi")
    assert ctx["scanTsH"] not in ctx["scanTexte"], (
        "la barre de contexte sert la chaine brute de la source : %r"
        % ctx["scanTexte"])


def test_le_badge_de_fraicheur_depend_de_l_age_reellement_mesure():
    """Avant : `data-state="delayed"` des qu'une source existait — la MEME
    chaine a 18 minutes et a six heures.

    CORRECTION DU CONTROLE ADVERSE (06/09/2026). La premiere redaction de ce
    banc comparait l'age a `VX.freshness.THRESH.stale` (2 100 000 ms, 35 min).
    Or `assess` n'emploie JAMAIS cette borne : elle bascule a
    `THRESH.snapshot` (1 800 000 ms, 30 min). Mesure d'un scan injecte a
    32 min sur l'instance QA : la page affichait `data-state="stale"` /
    « A actualiser » — ce qui est JUSTE — et le banc attendait « delayed ».
    Le gardien accusait donc la page a tort sur toute la fenetre 30-35 min ;
    il n'avait jamais tombe parce que tous les scans mesures avaient 1 a
    5 min. On ne fige plus une constante : on releve l'etat que la table du
    produit donne a l'age REELLEMENT mesure, et le badge doit le suivre.
    """
    m = _avec_donnees()
    ctx = m["screener"]["contexte"]
    if ctx["ageMsMesure"] is None or ctx["etatProduit"] is None:
        pytest.skip("aucun horodatage de scan servi : age non mesurable")
    assert ctx["etatA40min"] == "stale", (
        "la table de fraicheur du produit ne classe plus 40 min en « stale » "
        "(%r) : le badge de la page suivrait un seuil fantome" % ctx["etatA40min"])
    attendu = "stale" if ctx["etatProduit"] == "stale" else "delayed"
    assert ctx["fraicheurEtat"] == attendu, (
        "scan age de %d s : la table du produit dit %r, badge %r attendu, "
        "%r affiche" % (ctx["ageMsMesure"] / 1000, ctx["etatProduit"],
                        attendu, ctx["fraicheurEtat"]))


# ─────────────────────────────── 4. un vide qui nomme sa cause REELLE

def test_la_vue_ETF_vide_ne_pretend_pas_que_le_scan_n_a_rien_produit():
    """Avant : 513 lignes scorees servies, et l'ecran repondait « le dernier
    scan n'a produit aucune ligne portant un score »."""
    m = _avec_donnees()
    etf = m["etf"]
    if not etf["titre"]:
        pytest.skip("la vue ETF n'est pas vide sur ce scan")
    if not etf["scoreesServies"]:
        #  Le scan a pu basculer entre les deux onglets de la sonde : sans
        #  ligne scoree, la phrase generique est la VRAIE cause.
        pytest.skip("scan vide au moment de la vue ETF : rien a contredire")
    assert "aucune ligne portant un score" not in etf["cause"], (
        "%d ligne(s) scorees servies, et la cause affichee dit le contraire : %r"
        % (etf["scoreesServies"], etf["cause"]))
    assert str(etf["scoreesServies"]) in etf["cause"], (
        "la cause ne rend pas compte des %d lignes reellement scorees : %r"
        % (etf["scoreesServies"], etf["cause"]))


# ─────────────────────────────────────────────────── 5. rien ne casse

VUES = ["screener", "stocks", "etf", "options", "anomalies", "calendar", "portfolio"]


@pytest.mark.parametrize("vue", VUES)
def test_aucune_erreur_console_sur_les_vues_mesurees(vue):
    m = _mesure_ou_abstention()
    assert m["console"][vue] == [], m["console"][vue]


@pytest.mark.parametrize("vue", VUES)
def test_chaque_sous_vue_peint_un_corps_et_non_un_bandeau_d_erreur(vue):
    """`boot()` attrape l'exception d'une sous-vue et pose « Chargement
    impossible » : l'ecran meurt EN SILENCE, console vide. Mesure du
    06/09/2026 pendant ce lot : un accent grave place dans un commentaire
    HTML, a l'interieur d'un gabarit JS, a coupe la chaine et la vue Options
    a servi « Chargement impossible : update is not defined » — 72 caracteres
    de corps, zero ligne de console. Aucun autre banc ne l'aurait vu."""
    m = _mesure_ou_abstention()
    v = m["vivantes"][vue]
    assert v["erreur"] is None, "vue %s en erreur : %s" % (vue, v["erreur"])
    assert not v.get("squelette"), (
        "vue %s : le squelette de chargement n'a jamais ete remplace" % vue)
    assert v["corps"] > 80, (
        "vue %s : corps de %d caractere(s), la vue n'a rien peint"
        % (vue, v["corps"]))
