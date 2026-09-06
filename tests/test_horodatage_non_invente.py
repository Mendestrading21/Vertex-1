"""Vertex Test 1.0 — UN HORODATAGE ABSENT NE DEVIENT PAS LE 1er JANVIER 1970.

Deux régressions mesurées le 06/09/2026 sur le code SERVI, toutes deux dans le
même geste : un pied de carte qui affirme ce qu'il n'a pas mesuré.

## (a) `VX.fmt.isoFull(null)` peignait l'époque Unix

`new Date(null)` coerce à 0 en JavaScript. Mesure exécutée dans Chromium sur le
`vx-core.js` servi, AVANT correctif :

| appel | rendu |
|---|---|
| `isoFull(null)` | **`01/01/1970 01:00:00`** |
| `isoFull(undefined)` | `''` |
| `isoFull('')` | `''` |

Seul `null` passait — et `null` est précisément ce que produit l'idiome du
dépôt `updateIndicator(x || null, …)`, présent sur 25 sites de `vertex/` (dont
14 dans portfolio_page.py, briefing.py et markets_page.py). `updateIndicator`
émettait `title="${VX.fmt.isoFull(ts)}"` SANS condition, alors que la ligne
voisine savait déjà que l'âge était inconnu (`ms == null` → pas de `data-ts`,
texte « Âge inconnu »). Le 1er janvier 1970 était donc peint, en info-bulle,
exactement dans le cas où RIEN n'avait été reçu.

## (b) `newsPied` codait le mode 'delayed' en dur

Mesure AVANT correctif : `newsPied(null, 0, 0, 0)` — c'est-à-dire le fetch de
`/news-feed` en échec — rendait

    <span class="vx-update" data-mode="delayed" title="01/01/1970 01:00:00">
      <span class="vx-update-age">Âge inconnu</span> · fil source inconnue Différé</span>

« Différé » est l'étiquette de mode d'une donnée SERVIE. Ici aucune charge n'a
été servie : l'erreur reçoit l'habillage de la donnée. Le contrat produit exige
que l'erreur, l'absence et le zéro restent distincts, et la page appliquait déjà
cette règle trente lignes plus loin (`pfModeMarques` rend `''` quand rien n'est
mesuré) — mais pas à son propre pied.

## Ce que ce banc ne prouve pas

Il exécute le VRAI code servi (vx-core.js chargé tel quel, `newsPied` extrait de
briefing.py par équilibrage d'accolades), pas une copie. Il ne dit rien du rendu
CSS : avec `mode === ''`, `updateIndicator` retombe sur `data-mode="fallback"`,
donc la pastille reste grise (`--vx-text-muted`, la couleur la moins
affirmative disponible). Aucun MOT de mode n'est écrit — c'est ce que ce banc
vérifie ; la valeur de l'attribut relève de components.css.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
CORE = RACINE / "vertex" / "static" / "vertex" / "js" / "vx-core.js"
BRIEFING = RACINE / "vertex" / "ui" / "pages" / "briefing.py"


def _navigateur_pret() -> bool:
    #  Même témoin que les autres bancs navigateur du dépôt : il distingue
    #  MODULE_ABSENT / BINAIRE_ABSENT / LANCEMENT_REFUSE d'un vrai échec.
    try:
        from tools.mesures.mesurer_qa_espaces import navigateur_pret
    except Exception:
        return False
    return bool(navigateur_pret())


pytestmark = pytest.mark.skipif(
    not _navigateur_pret(),
    reason="navigateur absent : ce banc exécute le JavaScript RÉELLEMENT servi",
)


def _extraire(nom: str, src: str) -> str:
    """Le source d'une fonction, accolades équilibrées (idem test_marque_visible)."""
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


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page()
        pg.set_content("<!doctype html><html><body></body></html>")
        pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
        #  Le pied du fil et ses trois constantes de libellé, extraits de la
        #  page servie — pas recopiés.
        brief = BRIEFING.read_text(encoding="utf-8")
        pg.add_script_tag(content=(
            "let NEWS_FILTER='all';const NEWS_MAX=8;"
            "const NEWS_LIB={all:'Tout',pos:'Positives',neg:'Négatives'};"
            + _extraire("newsPied", brief)
            + "window.newsPied=newsPied;"
        ))
        yield pg
        nav.close()


# ── (a) le formateur ──────────────────────────────────────────────────
def test_isoFull_refuse_de_dater_une_absence(page):
    """`isoFull(null)` rendait '01/01/1970 01:00:00' — mesure du 06/09/2026."""
    rendus = page.evaluate(
        "() => [VX.fmt.isoFull(null), VX.fmt.isoFull(undefined), VX.fmt.isoFull('')]"
    )
    assert rendus == ["", "", ""], (
        "un horodatage absent est daté : %r (l'époque Unix est une valeur inventée)"
        % (rendus,)
    )


def test_isoFull_date_toujours_un_horodatage_reel(page):
    """Le garde ne doit pas rendre le formateur muet sur une vraie valeur."""
    rendu = page.evaluate("() => VX.fmt.isoFull(1757160300000)")
    assert rendu and "1970" not in rendu, rendu


def test_updateIndicator_n_emet_aucune_info_bulle_sans_horodatage(page):
    html = page.evaluate("() => VX.updateIndicator(null, 'fil source inconnue', 'delayed')")
    assert "1970" not in html, "époque Unix peinte en info-bulle : %s" % html
    assert "title=" not in html, (
        "info-bulle émise sans horodatage servi (rien à dater) : %s" % html
    )
    assert "Âge inconnu" in html and "data-ts" not in html


def test_updateIndicator_garde_l_info_bulle_quand_l_horodatage_existe(page):
    html = page.evaluate("() => VX.updateIndicator(1757160300000, 'scan', 'delayed')")
    assert "title=" in html and "1970" not in html, html
    assert "data-ts=\"1757160300000\"" in html, html


# ── (b) le pied du fil d'actualités ───────────────────────────────────
def test_le_pied_du_fil_ne_qualifie_pas_de_differee_une_requete_en_echec(page):
    """`d===null` = /news-feed injoignable : aucune charge, donc aucun mode."""
    html = page.evaluate("() => newsPied(null, 0, 0, 0)")
    assert "1970" not in html, "époque Unix peinte dans le pied dégradé : %s" % html
    assert "Différé" not in html, (
        "le mot de mode d'une donnée servie est collé sur une absence : %s" % html
    )
    assert 'data-mode="delayed"' not in html, html
    #  L'absence reste DITE, elle ne disparaît pas.
    assert "Âge inconnu" in html and "source inconnue" in html, html
    assert "0 titre(s) affiché(s)" in html, html


def test_le_pied_du_fil_reste_differe_sur_une_charge_servie(page):
    """Charge servie → 'delayed' est mesuré : le fil ne transporte aucun tick."""
    charge = {"ts": 1757160300, "source": "yfinance", "source_detail": {"ibkr": 0, "web": 45}}
    html = page.evaluate("(d) => newsPied(d, 8, 45, 45)", charge)
    assert 'data-mode="delayed"' in html and "Différé" in html, html
    assert "yfinance" in html and "web 45" in html, html
    assert "1970" not in html, html


# ── Le garde de source : la forme fautive ne doit pas revenir ─────────
def test_aucune_info_bulle_inconditionnelle_dans_le_coeur():
    src = CORE.read_text(encoding="utf-8")
    assert 'title="${VX.fmt.isoFull(ts)}"' not in src, (
        "forme inconditionnelle restaurée dans vx-core.js : isoFull(null) peint 1970"
    )


def test_aucun_mode_code_en_dur_dans_le_pied_du_fil():
    src = BRIEFING.read_text(encoding="utf-8")
    pied = _extraire("newsPied", src)
    #  Le mode est DÉRIVÉ de la présence d'une charge...
    assert re.search(r"const mode\s*=\s*d\s*\?\s*'delayed'\s*:\s*''", pied), pied
    #  ...et c'est cette variable, jamais un littéral, que reçoit l'indicateur.
    code = re.sub(r"/\*.*?\*/", "", pied, flags=re.S)
    assert re.search(r"\n\s*mode\)\}", code), code
    assert "'delayed')" not in code, (
        "mode codé en dur dans l'appel à updateIndicator : %s" % code
    )
