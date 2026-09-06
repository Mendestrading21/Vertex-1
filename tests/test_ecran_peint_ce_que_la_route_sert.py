"""Vertex Test 1.0 — QUAND LA ROUTE SERT LA DONNÉE, L'ÉCRAN LA PEINT.

Un « — » peut être honnête (la source est absente, et la carte le dit) ou être
un DÉFAUT (la route sert le fait, l'écran le jette). Ce banc épingle quatre
défauts de la seconde espèce, chacun mesuré sur la charge RÉELLEMENT servie par
`app.test_client()`.

## 1. Corrélations : une promesse fausse sur les deux chemins (constat 28 A)

`corrHeatmap` écrivait en dur « Corrélations indisponibles — nécessitent un
historique de prix (≥ 30 séances par titre, **disponible avec le flux live**) »
et n'ouvrait jamais `corr.reason`. Mesure du 06/09/2026 sur les deux appelants :

| route | `reason` servi |
|---|---|
| `/api/portfolio/team` | « NON_IMPLÉMENTÉ … cette route ne fournit aucune série de rendements au moteur … » |
| `/api/portfolio/context` | « séries datées insuffisantes pour au moins deux positions » |

Aucune des deux causes n'est levée par « le flux live » : la première est une
capacité non branchée sur la route, la seconde un manque d'historique daté. La
phrase envoyait donc ouvrir TWS pour débloquer une carte que TWS ne débloque
pas — invariant 8.

## 2. HHI : deux autorités, deux barèmes, un seul mot (constats 24 / 26)

Mesure du 06/09/2026, même produit, deux vues :

| vue | route | `hhi_basis` servi | barème |
|---|---|---|---|
| Risque | `/api/portfolio/team` | compartiment actions, poids renormalisés à 100 % — cash exclu | 33 / 66 sur HHI×100 |
| Allocation | `/api/portfolio/context` | toutes les lignes valorisées ; le cash n'est pas une ligne | 0,18 / 0,25 |

Conséquence arithmétique : **le nombre 0,30 se lit « bien dispersé » d'un côté
et « concentré » de l'autre**, sous le même libellé « HHI ». Et sur KO 88,07 $
+ 25 000 $ de cash, `hhi` vaut 1,0 — « très concentré » en rouge — pendant que
`invested_pct` vaut 0,35 : le rouge décrit un compartiment quasi vide. Les deux
champs sont servis ; ni l'un ni l'autre n'était peint.

Ce banc n'exige AUCUN changement de seuil ni de nombre : il exige que chaque
écran nomme la base de son indice.

## 3. Périmètre du stress : servi, jeté (constat 26, moitié écran)

`/api/portfolio/team` rend `stress.coverage` et `stress.warnings`. Mesuré :
`coverage.note` = « base de stress = positions valorisées + cash ; les options
déclarées exigent marque et greeks IBKR et restent hors base » et
`options_in_equity` = false. Un impact de -0,05 % sur une base qui exclut les
options n'est pas le même chiffre selon qu'on le sait ou non.

## 4. Ponctualité macro : « 11/11 séries publiées » (constat C-4)

Mesuré sur le cache réel (11 séries) : `en_retard` vaut **2** — IPCH zone euro
arrêté au 2025-12 (RETARD_FORT, 249 j) et Confédération 10 ans au 2025-07
(RETARD_FORT, 402 j) — pendant que le pied annonçait « 11/11 séries publiées »
et que la page ne lisait ni `fraicheur`, ni `age_jours`, ni `en_retard`.
`SANS_OBJET` (les deux taux directeurs BCE, 81 j) n'est PAS un retard : un taux
en vigueur court jusqu'au changement suivant.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
PORTEFEUILLE = RACINE / "vertex" / "ui" / "pages" / "portfolio_page.py"
MARCHES = RACINE / "vertex" / "ui" / "pages" / "markets_page.py"
INTELLIGENCE = RACINE / "vertex" / "ui" / "pages" / "intelligence_page.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _sans_commentaires(src: str) -> str:
    """Le CODE seul : un commentaire qui cite le défaut ne doit pas le sauver."""
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _extraire(nom: str, src: str) -> str:
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


# ══ 1. Corrélations : la cause SERVIE, pas une promesse ═══════════════
def test_les_deux_routes_servent_une_cause_de_correlation():
    """La cause existe côté serveur — l'écran n'a rien à inventer."""
    os.environ.setdefault("VERTEX_CODE", "")
    from vertex.runtime import app
    c = app.test_client()
    corps = {"positions": [{"symbol": "KO", "quantity": 1, "avg_cost": 88.07,
                            "last_price": 88.07, "sector": "Consumer"}],
             "option_positions": [], "cash": 25000, "simulated": False}
    team = c.post("/api/portfolio/team", json=corps).get_json()
    corr = (team.get("risk") or {}).get("correlations") or {}
    assert corr.get("reason"), "la route team doit nommer sa cause"
    assert "NON_IMPLÉMENTÉ" in corr["reason"]
    ctx = c.get("/api/portfolio/context").get_json()
    cc = ctx.get("correlations") or {}
    assert cc.get("reason"), "la route context doit nommer sa cause"


def test_la_heatmap_ouvre_la_cause_au_lieu_de_promettre_le_flux_live():
    code = _sans_commentaires(_src(PORTEFEUILLE))
    assert "disponible avec le flux live" not in code, (
        "promesse jamais vraie sur aucun chemin de code : ni /team (capacité non "
        "branchée) ni /context (historique daté manquant) ne dépendent de TWS"
    )
    corps = _extraire("corrHeatmap", _sans_commentaires(_src(PORTEFEUILLE)))
    assert "corr.reason" in corps, "la cause servie doit être lue"
    assert "cause non servie par la route" in corps, (
        "sans `reason`, on dit l'absence de cause au lieu d'en fabriquer une"
    )


def test_la_heatmap_n_emprunte_plus_l_horloge_des_cotations():
    """`__pfTs` date /api/pos-quotes ; aucune des deux routes ne date sa matrice."""
    corps = _extraire("corrHeatmap", _sans_commentaires(_src(PORTEFEUILLE)))
    assert "window.__pfTs" not in corps, corps
    assert "timestamp:(corr&&corr.as_of)||null" in corps


# ══ 2. HHI : chaque écran nomme la base de son indice ════════════════
def test_les_deux_routes_servent_des_bases_de_hhi_differentes():
    """La contradiction est réelle et mesurée, pas supposée."""
    os.environ.setdefault("VERTEX_CODE", "")
    from vertex.runtime import app
    c = app.test_client()
    corps = {"positions": [{"symbol": "KO", "quantity": 1, "avg_cost": 88.07,
                            "last_price": 88.07, "sector": "Consumer"}],
             "option_positions": [], "cash": 25000, "simulated": False}
    risk = (c.post("/api/portfolio/team", json=corps).get_json() or {}).get("risk") or {}
    ctx = c.get("/api/portfolio/context").get_json() or {}
    assert risk.get("hhi_basis") and ctx.get("hhi_basis")
    assert risk["hhi_basis"] != ctx["hhi_basis"], (
        "deux bases identiques rendraient ce banc sans objet"
    )
    assert isinstance(risk.get("invested_pct"), (int, float))
    #  Le barème de chaque écran, rejoué sur le MÊME nombre.
    h = 0.30
    risque = "très concentré" if h * 100 >= 66 else (
        "concentration modérée" if h * 100 >= 33 else "bien dispersé")
    alloc = "concentré" if h >= 0.25 else ("modérément concentré" if h >= 0.18 else "dispersé")
    assert (risque, alloc) == ("bien dispersé", "concentré"), (risque, alloc)


def test_l_ecran_risque_nomme_la_base_du_hhi_et_la_part_investie():
    code = _sans_commentaires(_src(PORTEFEUILLE))
    assert "risk.hhi_basis" in code, "la base servie doit être peinte"
    assert "risk.invested_pct" in code, (
        "« très concentré » sur 0,35 % du capital investi doit dire les 0,35 %"
    )
    assert "hhiPied" in code
    #  Les seuils du moteur ne bougent pas : on nomme, on ne recalcule pas.
    assert "_hhi>=66?'très concentré'" in code and "_hhi>=33?'concentration modérée'" in code


def test_l_ecran_allocation_nomme_la_base_de_son_hhi():
    code = _sans_commentaires(_src(PORTEFEUILLE))
    assert "d.hhi_basis" in code, "la vue Allocation doit nommer sa propre base"
    assert "d.hhi>=0.25?'concentré'" in code, "barème inchangé"


# ══ 3. Périmètre du stress ═══════════════════════════════════════════
def test_la_route_sert_le_perimetre_du_stress():
    os.environ.setdefault("VERTEX_CODE", "")
    from vertex.runtime import app
    c = app.test_client()
    corps = {"positions": [{"symbol": "KO", "quantity": 1, "avg_cost": 88.07,
                            "last_price": 88.07, "sector": "Consumer"}],
             "option_positions": [], "cash": 25000, "simulated": False}
    st = (c.post("/api/portfolio/team", json=corps).get_json() or {}).get("stress") or {}
    cov = st.get("coverage") or {}
    assert cov.get("note") and "equity_basis" in cov
    assert cov.get("options_in_equity") is False
    assert isinstance(st.get("warnings"), list)


def test_l_ecran_peint_la_couverture_et_les_avertissements_du_stress():
    code = _sans_commentaires(_src(PORTEFEUILLE))
    assert "function stressPerimetre(" in code
    assert "${stressPerimetre(stressBloc)}" in code, "la carte Stress doit l'appeler"
    corps = _extraire("stressPerimetre", code)
    for cle in ("coverage", "warnings", "equity_basis", "options_open",
                "options_in_equity", "options_vega_known"):
        assert cle in corps, cle
    #  Les avertissements ne sont plus réduits à leur NOMBRE.
    assert "risk.warnings.map(esc).join" in code, (
        "« 2 avertissement(s) » cachait le texte que le moteur a écrit"
    )


# ══ 4. Ponctualité macro ═════════════════════════════════════════════
def test_le_collecteur_sert_bien_un_verdict_de_ponctualite():
    """Mesure sur le cache réel : 2 séries en retard sur 11 disponibles."""
    from vertex.services import macro_officiel as svc
    svc.charger_cache()
    snap = svc.snapshot()
    if not snap.get("series"):
        pytest.skip("aucun cache macro sur ce poste — rien à mesurer")
    assert isinstance(snap.get("en_retard"), int)
    verdicts = {s.get("fraicheur") for s in snap["series"]}
    assert verdicts <= {"A_JOUR", "RETARD", "RETARD_FORT", "SANS_OBJET", "INCONNU"}
    assert all("age_jours" in s for s in snap["series"])
    #  `SANS_OBJET` n'entre pas dans le compte des retards.
    sans_objet = [s for s in snap["series"] if s.get("fraicheur") == "SANS_OBJET"]
    assert snap["en_retard"] == sum(
        1 for s in snap["series"] if s.get("fraicheur") in ("RETARD", "RETARD_FORT"))
    for s in sans_objet:
        assert s.get("frequence") == "en vigueur", s


def test_la_bande_macro_peint_la_ponctualite_servie():
    code = _sans_commentaires(_src(MARCHES))
    assert "function ponctualite(" in code
    assert "s.fraicheur" in code and "s.age_jours" in code
    assert "const pon=ponctualite(s);" in code and "+(pon?' · '+pon:'')" in code
    #  Le pied dit les DEUX faits : disponibilité et ponctualité.
    assert "d.en_retard" in code
    assert "en retard chez la source" in code and "aucune en retard" in code
    assert "retards non mesurés" in code, (
        "champ absent ≠ aucun retard : l'absence de mesure se dit"
    )


def test_la_table_des_frequences_couvre_les_quatre_valeurs_servies():
    """`en vigueur` manquait à FREQ_FR — sans effet visible, mais la table ment."""
    from vertex.data_sources import macro_officiel as src
    servies = {s.frequence for s in src.CATALOGUE}
    code = _src(MARCHES)
    table = code.split("const FREQ_FR=")[1].split("};")[0]
    for f in servies:
        assert f in table, "fréquence servie absente de la table : %r" % f


def test_le_helper_d_age_client_a_disparu():
    """Le serveur sert `age_jours` : un second calcul dans la page divergerait."""
    code = _src(MARCHES)
    assert "function ageObs(" not in code, (
        "helper mort ET seconde autorité d'âge : le serveur calcule, la page peint"
    )


# ══ 5. Prisme marché : la clé lue doit exister chez le producteur ════
def test_le_prisme_lit_des_cles_que_le_moteur_rend_vraiment():
    """`lens.summary` n'existe pas : la ligne ne s'affichait jamais."""
    from vertex.engines import market_lens
    rendu = market_lens.build(market={}, sectors=[], sector_name=None, stock_pct=None)
    assert "summary" not in rendu, "si la clé apparaît, ce banc doit être revu"
    code = _sans_commentaires(_src(INTELLIGENCE))
    assert "lens.summary" not in code, "clé morte : la carte ne s'affiche jamais"
    for cle in ("alignment", "headline"):
        assert cle in rendu, cle
        assert "lens." + cle in code, "la page doit lire une clé réellement rendue"


# ══ 6. Bande de commandement : deux causes, deux phrases ═════════════
def test_la_bande_ne_crie_pas_a_la_panne_de_cotation_sur_un_cout_nul():
    """`invested === 0` avec TOUTES les marques présentes n'est pas une panne."""
    code = _sans_commentaires(_src(PORTEFEUILLE))
    corps = _extraire("pfCommandStrip", code)
    assert "'marques indispo.'" not in corps, (
        "une panne de cotation affirmée sur un portefeuille intégralement marqué"
    )
    assert "coût déclaré nul — aucun pourcentage calculable" in corps
    assert "pfCauseMarques(sansMarque)" in corps


# ══ 7. Éprouvé À L'EXÉCUTION dans un navigateur réel ═════════════════
#  Node est absent de ce poste (12 bancs de test_marque_visible.py sont
#  skippés pour cette raison) : on exécute le VRAI code servi dans Chromium.
CORE = RACINE / "vertex" / "static" / "vertex" / "js" / "vx-core.js"


def _navigateur_pret() -> bool:
    try:
        from tools.mesures.mesurer_qa_espaces import navigateur_pret
    except Exception:
        return False
    return bool(navigateur_pret())


@pytest.fixture(scope="module")
def page():
    if not _navigateur_pret():
        pytest.skip("navigateur absent : ces trois bancs exécutent le JS servi")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page()
        pg.set_content("<!doctype html><html><body></body></html>")
        pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
        #  La table de libellés est EXTRAITE de la page, jamais recopiée : une
        #  copie divergerait au premier libellé changé et le banc deviendrait
        #  une caractérisation de lui-même.
        marches = _src(MARCHES)
        table = "const FRAICHEUR_FR=" + marches.split("const FRAICHEUR_FR=")[1].split("};")[0] + "};"
        pg.add_script_tag(content=(
            "function esc(s){return String(s??'').replace(/[<>&\"]/g,"
            "c=>({'<':'&lt;','>':'&gt;','&':'&amp;','\"':'&quot;'}[c]));}"
            + _extraire("stressPerimetre", _src(PORTEFEUILLE))
            + table
            + _extraire("ponctualite", marches)
            + "window.stressPerimetre=stressPerimetre;window.ponctualite=ponctualite;"
        ))
        yield pg
        nav.close()


def test_le_rejeu_cible_ne_relance_que_la_tache_du_canal(page):
    """Constat 23 : un battement `jobs` relançait TOUTES les tâches de la page."""
    vus = page.evaluate("""() => {
      const vus = [];
      VX.refresh._tasks = [];
      ['jobs','marches','portefeuille'].forEach(l =>
        VX.refresh.register(() => { vus.push(l); }, 1e9, l));
      return VX.refresh.runTasks(['jobs']).then(() => vus);
    }""")
    assert vus == ["jobs"], vus
    tous = page.evaluate("""() => {
      const vus = [];
      VX.refresh._tasks = [];
      ['jobs','marches','portefeuille'].forEach(l =>
        VX.refresh.register(() => { vus.push(l); }, 1e9, l));
      return VX.refresh.runTasks().then(() => vus.sort());
    }""")
    assert tous == ["jobs", "marches", "portefeuille"], (
        "sans filtre, le rejeu doit rester complet (aucun autre canal changé)"
    )


def test_le_perimetre_du_stress_se_lit_en_francais(page):
    """La charge MESURÉE du 06/09/2026, peinte telle que le moteur l'écrit."""
    cov = {"equity_basis": "positions valorisées du snapshot + cash",
           "note": "base de stress = positions valorisées + cash ; les options "
                   "déclarées exigent marque et greeks IBKR et restent hors base",
           "options_in_equity": False, "options_open": 0,
           "options_vega_known": True, "read_only": True}
    html = page.evaluate("(b) => stressPerimetre(b)",
                         {"coverage": cov, "warnings": ["2 option(s) hors base de stress"]})
    assert "positions valorisées du snapshot + cash" in html
    assert "hors base de stress" in html
    assert "2 option(s) hors base de stress" in html
    #  Aucun périmètre servi → rien de peint, jamais une phrase inventée.
    assert page.evaluate("() => stressPerimetre({})") == ""
    assert page.evaluate("() => stressPerimetre(null)") == ""


def test_la_ponctualite_distingue_retard_absence_et_valeur_en_vigueur(page):
    """`SANS_OBJET` (taux directeur, 81 j) n'est pas un retard ; l'absence non plus."""
    lu = lambda s: page.evaluate("(s) => ponctualite(s)", s)  # noqa: E731
    assert "en retard" in lu({"fraicheur": "RETARD_FORT", "age_jours": 402})
    assert "402" in lu({"fraicheur": "RETARD_FORT", "age_jours": 402})
    envigueur = lu({"fraicheur": "SANS_OBJET", "age_jours": 81})
    assert "retard" not in envigueur and "en vigueur" in envigueur, envigueur
    assert "81" not in envigueur, "un âge affiché à côté d'un taux courant se lit comme un retard"
    assert lu({"fraicheur": "A_JOUR", "age_jours": 3}) == "à jour (3 j)"
    assert lu({}) == "", "champ non servi : aucun verdict inventé"
    assert "non jugée" in lu({"fraicheur": "INCONNU", "age_jours": None})
