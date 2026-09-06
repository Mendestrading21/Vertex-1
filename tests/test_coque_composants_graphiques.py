"""LOT I — LA COQUE ET SES PRIMITIVES : CE QU'ELLES PROMETTENT, ELLES LE TIENNENT.

Quatre défauts mesurés le 06/09/2026 dans Chromium, sur les octets réellement
servis. Ils vivent tous dans des PRIMITIVES PARTAGÉES : chacun se multiplie par
le nombre de pages qui les appellent.


## (a) Cinq primitives sur huit avalaient le contrat des graphiques

`C.card` porte question, unité, source, horodatage, période et limites ; le lot
qui a écrit `tetePrimitive`/`piedPrimitive` les a donnés à `treemap` et
`waterfall`. Les cinq autres primitives SVG les acceptaient sans jamais les
rendre. Mesure : appel de chaque primitive avec
`{question, unit, source, timestamp, limits, period}`, puis recherche des
valeurs dans le HTML produit.

| primitive | question | source | horodatage | limites | période |
|---|---|---|---|---|---|
| `treemap`   | oui | oui | oui | oui | oui |
| `waterfall` | oui | oui | oui | oui | oui |
| `radar`     | **non** | **non** | **non** | **non** | **non** |
| `rings`     | **non** | **non** | **non** | **non** | **non** |
| `funnel`    | **non** | **non** | **non** | **non** | **non** |
| `flow`      | **non** | **non** | **non** | **non** | **non** |
| `gauge`     | **non** | **non** | **non** | **non** | **non** |

Ces cinq primitives servent la jauge de régime d'Aujourd'hui, le radar de
scorecard d'Analyse, les anneaux de participation, les entonnoirs de sélection
de Marchés et d'Opportunités, la chaîne d'impact de Vertex IA : une valeur
critique y était affichée sans source ni fraîcheur (invariant 5).


## (b) `C.radar` imputait un ZÉRO à un axe sans valeur

`clamp(v) = (v || 0) / max` transformait `null`, `undefined` et `''` en 0.
Mesure sur `C.radar(h, {axes:[{label:'Alpha'}, {label:'Beta', value:null},
{label:'Gamma', value:50}]})` :

    aria-label  → « radar : Alpha 0, Beta 0, Gamma 50 »
    polygone    → « 130.0,120.0 130.0,120.0 89.3,143.5 »

Deux sommets EXACTEMENT au centre (130,120) du cadre 260×240 : la lecture est
« note nulle » là où la mesure dit « pas de note ». Absence et zéro doivent
rester distincts (invariant 4).


## (c) L'alias `.vx-span-*` ne suivait aucun palier responsive

`layout.css` déclare `.vx-span-*` « même sémantique que `.vx-col-*` », et
`tests/test_grille_portees.py` l'accepte comme portée licite. Mais les paliers
de `responsive.css` ne nommaient que `.vx-col-*`. Mesure sur une `.vx-grid`
servie :

| largeur | `.vx-col-4` | `.vx-span-4` | `.vx-col-6` | `.vx-span-6` |
|---|---|---|---|---|
| 1600 px | 523 | 523 | 792 | 792 |
| 1024 px | 1024 | **331** | 504 | 504 |
| 390 px | 390 | **122** | 390 | **189** |

`.vx-span-10` et `.vx-span-11` n'existaient pas du tout. Le défaut était
LATENT — aucune page servie n'emploie l'alias aujourd'hui — mais c'est
exactement le piège du lot 610 : une carte de 122 px sur un téléphone, contenu
coupé, sans erreur ni débordement de page pour le signaler.


## (d) `.vx-badge` sortait du cadre au lieu de se replier

`white-space:nowrap` sans plafond de largeur. Mesure sur 9 pages × 3 largeurs,
1 597 badges rendus : à 390 px sur Aujourd'hui, le badge « Calls : Volatilité
implicite basse : environnement porteur… » mesurait 587 px dans une colonne de
390 — 234 px de texte hors écran, effacés par le `overflow-x:clip` de la coque,
sans barre de défilement ni signal. Tous les autres badges : 0 coupé.


## Ce que ces bancs ne prouvent pas

Ils exécutent le JavaScript et la feuille RÉELLEMENT servis (fichiers lus sur
disque, `CSS_ORDER` importé depuis la coque et non recopié), dans un vrai
Chromium, aux trois largeurs du contrat. Ils ne disent rien des pages qui
APPELLENT ces primitives : une page qui passe `value: a || 0` impute son zéro
elle-même, en amont, et aucun garde de primitive ne peut le voir.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
JS_DIR = RACINE / "vertex" / "static" / "vertex" / "js"
CSS_DIR = RACINE / "vertex" / "static" / "vertex" / "css"
CORE = JS_DIR / "vx-core.js"
CHARTS = JS_DIR / "charts" / "chart-core.js"

#: Les cinq primitives qui rendaient un SVG NU. `treemap` et `waterfall`
#: portent déjà le contrat : ils servent de témoins positifs.
NUES = ("radar", "rings", "funnel", "flow", "gauge")

#: Argument minimal viable de chaque primitive — assez pour qu'elle rende
#: autre chose que son état vide.
CORPS = {
    "radar": "axes:[{label:'A',value:10},{label:'B',value:20},{label:'C',value:30}]",
    "rings": "items:[{label:'A',value:10},{label:'B',value:20}]",
    "funnel": "stages:[{label:'A',value:10},{label:'B',value:5}]",
    "flow": "nodes:[{label:'A',count:1},{label:'B',count:2}]",
    "gauge": "value:42,label:'test'",
    "treemap": "items:[{label:'A',value:10},{label:'B',value:5}]",
    "waterfall": "items:[{label:'A',value:10},{label:'B',value:-5}]",
}

#: L'unité de `gauge` et de `rings` est DÉJÀ peinte sur le cadran / dans la
#: légende : la répéter au pied ferait le doublon que `piedPrimitive` évite
#: déjà pour la source.
UNITE_DEJA_INTERNE = ("gauge", "rings")


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
    reason="navigateur absent : ces bancs mesurent le rendu RÉELLEMENT servi",
)


def _bundle_css() -> str:
    """La cascade EXACTE de la coque, dans son ordre contractuel.

    `CSS_ORDER` est importé, jamais recopié : une feuille ajoutée ou déplacée
    par la coque déplace aussi ce banc.
    """
    from vertex.ui.shell import CSS_ORDER
    return "\n".join((CSS_DIR / nom).read_text(encoding="utf-8")
                     for nom in CSS_ORDER)


@pytest.fixture(scope="module")
def navigateur():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch()
        yield nav
        nav.close()


@pytest.fixture(scope="module")
def page_js(navigateur):
    """Une page nue qui porte le vrai `vx-core.js` puis le vrai `chart-core.js`."""
    pg = navigateur.new_page()
    pg.set_content("<!doctype html><html><body></body></html>")
    pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
    pg.add_script_tag(content=CHARTS.read_text(encoding="utf-8"))
    yield pg
    pg.close()


def _rendre(pg, nom: str, options: str) -> str:
    """Appelle une primitive dans un hôte neuf et rend son HTML."""
    return pg.evaluate(
        """(a) => {
          const h = document.createElement('div');
          document.body.appendChild(h);
          window.VXCharts[a.nom](h, a.opts);
          const html = h.innerHTML; h.remove(); return html;
        }""",
        {"nom": nom, "opts": pg.evaluate("(s) => eval('({' + s + '})')",
                                         options)},
    )


# ── (a) Le contrat des graphiques ─────────────────────────────────────
@pytest.mark.parametrize("nom", NUES + ("treemap", "waterfall"))
def test_chaque_primitive_porte_source_horodatage_et_limites(page_js, nom):
    """AVANT : les cinq primitives nues rendaient 0 des 5 mentions ; treemap et
    waterfall les rendaient déjà toutes les 5. APRÈS : 5 sur 5 partout."""
    html = _rendre(page_js, nom, CORPS[nom] + (
        ",question:'QUESTION_TEST',source:'SOURCE_TEST',limits:'LIMITES_TEST'"
        ",period:'PERIODE_TEST',timestamp:1757160300000"))
    manquant = [quoi for quoi, jeton in (
        ("question", "QUESTION_TEST"),
        ("source", "SOURCE_TEST"),
        ("limites", "LIMITES_TEST"),
        ("période", "PERIODE_TEST"),
        ("horodatage", "vx-update"),
    ) if jeton not in html]
    assert not manquant, (
        "C.%s avale %s : la valeur est affichée sans sa traçabilité "
        "(invariant 5). HTML rendu : %s" % (nom, ", ".join(manquant), html[:300]))


@pytest.mark.parametrize("nom", NUES)
def test_l_unite_est_annoncee_sans_etre_repetee_au_pied(page_js, nom):
    """Toute primitive doit dire l'unité de ses chiffres (invariant 5). `gauge`
    et `rings` la peignent DÉJÀ dans le graphique — sur le cadran, collée à
    chaque valeur de la légende ; la repasser au pied donnerait « % · confiance »
    puis « unité : % » à deux centimètres d'écart, le doublon que
    `piedPrimitive` évite déjà pour la source.

    On mesure OÙ vit l'unité, pas combien de fois la chaîne apparaît : elle est
    aussi dans l'`aria-label`, et l'y compter figerait la forme du nom
    accessible."""
    html = _rendre(page_js, nom, CORPS[nom] + ",unit:'UNITE_TEST',source:'S'")
    assert "UNITE_TEST" in html, (
        "C.%s n'annonce nulle part l'unité de ses chiffres : %s" % (nom, html[:300]))
    au_pied = "unité : UNITE_TEST" in html
    if nom in UNITE_DEJA_INTERNE:
        assert not au_pied, (
            "C.%s répète au pied une unité déjà peinte dans le graphique" % nom)
    else:
        assert au_pied, (
            "C.%s reçoit l'unité et ne l'écrit pas : %s" % (nom, html[:300]))


@pytest.mark.parametrize("nom", NUES)
def test_une_primitive_sans_legende_reste_exactement_ce_qu_elle_etait(page_js, nom):
    """Le pied ne s'affiche QUE si on lui donne quelque chose : les appels du
    produit (qui ne passent aujourd'hui ni source, ni horodatage, ni limites)
    ne changent pas de boîte."""
    html = _rendre(page_js, nom, CORPS[nom])
    assert "vx-primitive-foot" not in html and "vx-primitive-question" not in html, (
        "C.%s ajoute un pied ou une tête vides : %s" % (nom, html[:200]))


def test_le_pied_ne_saigne_pas_hors_d_un_hote_a_hauteur_figee(page_js):
    """Le pied posé dans un hôte dimensionné pour le SVG SEUL déborde : c'est la
    mesure du lot 33 sur le treemap (294 px de contenu dans 260 px). Les cinq
    primitives qui reçoivent un pied ici doivent libérer la hauteur AUSSI —
    sinon on déplace le défaut au lieu de le corriger."""
    for nom in NUES:
        etat = page_js.evaluate(
            """(a) => {
              const h = document.createElement('div');
              h.style.height = '150px';
              document.body.appendChild(h);
              window.VXCharts[a.nom](h, a.opts);
              const r = {inline: h.style.height, scroll: h.scrollHeight,
                         client: h.clientHeight,
                         pied: !!h.querySelector('.vx-primitive-foot')};
              h.remove(); return r;
            }""",
            {"nom": nom, "opts": page_js.evaluate(
                "(s) => eval('({' + s + '})')",
                CORPS[nom] + ",source:'S',timestamp:1757160300000")},
        )
        assert etat["pied"], "C.%s ne rend pas le pied attendu" % nom
        assert etat["scroll"] <= etat["client"] + 1, (
            "C.%s : %d px de contenu dans un hôte de %d px — le pied saigne sur "
            "le bloc suivant" % (nom, etat["scroll"], etat["client"]))


# ── (b) Absence et zéro restent distincts ─────────────────────────────
def test_un_axe_sans_valeur_n_est_pas_un_axe_a_zero(page_js):
    """AVANT : aria-label « radar : Alpha 0, Beta 0, Gamma 50 » et deux sommets
    du polygone confondus au centre (130.0,120.0). APRÈS : les axes sans valeur
    quittent le tracé et sont NOMMÉS."""
    r = page_js.evaluate(
        """() => {
          const h = document.createElement('div');
          document.body.appendChild(h);
          window.VXCharts.radar(h, {axes:[
            {label:'Alpha'}, {label:'Beta', value:null}, {label:'Vide', value:''},
            {label:'Gamma', value:50}, {label:'Delta', value:30},
            {label:'Epsilon', value:0}]});
          const svg = h.querySelector('svg');
          const poly = h.querySelector('polygon[fill-opacity]');
          const out = {aria: svg.getAttribute('aria-label'),
                       points: poly.getAttribute('points').trim().split(/\\s+/),
                       texte: h.textContent};
          h.remove(); return out;
        }""")
    for absent in ("Alpha", "Beta", "Vide"):
        assert "%s 0" % absent not in r["aria"], (
            "un axe sans valeur est annoncé à zéro : %s" % r["aria"])
        assert absent in r["texte"], (
            "un axe retiré du tracé disparaît en silence — le lecteur croit que "
            "la dimension n'a jamais existé : %r" % r["texte"])
    assert len(r["points"]) == 3, (
        "le polygone porte %d sommets pour 3 axes mesurés : %s"
        % (len(r["points"]), r["points"]))
    assert len(set(r["points"])) == 3, (
        "des sommets confondus au centre : %s" % r["points"])
    #  Le zéro MESURÉ, lui, reste un chiffre du graphique.
    assert "Epsilon 0" in r["aria"], r["aria"]


def test_aucun_libelle_d_axe_n_est_coupe_par_le_cadre(page_js):
    """AVANT, sur /system/design-system (`viewBox 0 0 260 240`, cinq axes), les
    boîtes `getBBox()` des libellés dépassaient le cadre : « Tendance » jusqu'à
    x=274.2 pour 260 de large, « Volatilité » à partir de x=-10.5 — soit
    « Tendar » et « latilité » à l'écran. Le libellé est la seule chose qui
    nomme la dimension notée."""
    r = page_js.evaluate(
        """() => {
          const h = document.createElement('div');
          document.body.appendChild(h);
          window.VXCharts.radar(h, {axes:[
            {label:'Momentum',value:80},{label:'Tendance',value:65},
            {label:'Qualité',value:72},{label:'Valorisation',value:48},
            {label:'Volatilité',value:55}]});
          const svg = h.querySelector('svg');
          const vb = svg.getAttribute('viewBox').split(' ').map(Number);
          const out = [...svg.querySelectorAll('text')].map(t => {
            const b = t.getBBox();
            return {txt: t.textContent, x0: +b.x.toFixed(1),
                    x1: +(b.x + b.width).toFixed(1),
                    y0: +b.y.toFixed(1), y1: +(b.y + b.height).toFixed(1)};
          });
          h.remove(); return {vb, out};
        }""")
    largeur, hauteur = r["vb"][2], r["vb"][3]
    coupes = [t for t in r["out"]
              if t["x0"] < 0 or t["x1"] > largeur or t["y0"] < 0 or t["y1"] > hauteur]
    assert not coupes, (
        "libellé(s) d'axe hors du cadre %dx%d : %s — le nom de la dimension est "
        "tronqué, la note ne veut plus rien dire" % (largeur, hauteur, coupes))


def test_un_zero_mesure_reste_trace(page_js):
    """Le garde ne doit pas filtrer les vrais zéros : trois notes à 0 forment un
    radar légitime, entièrement replié sur le centre, et sans mention d'absence."""
    r = page_js.evaluate(
        """() => {
          const h = document.createElement('div');
          document.body.appendChild(h);
          window.VXCharts.radar(h, {axes:[{label:'A',value:0},{label:'B',value:0},
                                          {label:'C',value:0}]});
          const out = {aria: h.querySelector('svg').getAttribute('aria-label'),
                       absence: !!h.querySelector('.vx-primitive-absents')};
          h.remove(); return out;
        }""")
    assert r["aria"].endswith("A 0, B 0, C 0"), r["aria"]
    assert not r["absence"], "un zéro mesuré est présenté comme une absence"


# ── (c) et (d) La grille et le badge, aux trois largeurs ──────────────
GABARIT = """<!doctype html><html><body>
<div class="vx-app"><main class="vx-main"><div class="vx-content" id="vx-content">
  <div class="vx-grid" id="g">%s</div>
  <div class="vx-flex vx-wrap" id="fb" style="width:100%%"><span class="vx-badge"
    id="b">Calls : Volatilite implicite basse : environnement porteur pour l'achat
    de calls, la convexite est accessible sur les echeances longues</span></div>
</div></main></div></body></html>"""

PORTEES = tuple(range(2, 13))


@pytest.fixture(scope="module")
def css():
    return _bundle_css()


@pytest.mark.parametrize("largeur", (1600, 1024, 390))
def test_l_alias_span_vaut_exactement_col_a_toutes_les_largeurs(navigateur, css, largeur):
    """AVANT, à 390 px : col-4 = 390 et span-4 = 122 ; col-6 = 390 et
    span-6 = 189 ; span-10 et span-11 n'existaient pas. L'alias promettait la
    même sémantique et servait le quart de la largeur."""
    cellules = "".join(
        '<div class="vx-col-%d" id="c%d">c</div>'
        '<div class="vx-span-%d" id="s%d">s</div>' % (n, n, n, n)
        for n in PORTEES)
    pg = navigateur.new_page(viewport={"width": largeur, "height": 900})
    pg.set_content(GABARIT % cellules)
    pg.add_style_tag(content=css)
    mesures = pg.evaluate(
        """(ns) => Object.fromEntries(ns.map(n => [n, [
             Math.round(document.getElementById('c'+n).getBoundingClientRect().width),
             Math.round(document.getElementById('s'+n).getBoundingClientRect().width)]]))""",
        list(PORTEES))
    pg.close()
    ecarts = {n: v for n, v in mesures.items() if v[0] != v[1]}
    assert not ecarts, (
        "à %d px, l'alias .vx-span-* diverge de .vx-col-* — {portée: [col, span]} "
        "= %s" % (largeur, ecarts))


@pytest.mark.parametrize("largeur", (1600, 1024, 390))
def test_un_badge_trop_long_se_replie_au_lieu_de_sortir_du_cadre(navigateur, css, largeur):
    """AVANT, à 390 px : badge de 587 px dans une colonne de 390 — 234 px de
    texte hors écran, effacés sans barre de défilement ni signal."""
    pg = navigateur.new_page(viewport={"width": largeur, "height": 900})
    pg.set_content(GABARIT % '<div class="vx-col-12">.</div>')
    pg.add_style_tag(content=css)
    m = pg.evaluate(
        """() => {
          const b = document.getElementById('b').getBoundingClientRect();
          const c = document.getElementById('vx-content').getBoundingClientRect();
          return {depasse: Math.round(b.right - c.right), h: Math.round(b.height),
                  w: Math.round(b.width), dispo: Math.round(c.width)};
        }""")
    pg.close()
    assert m["depasse"] <= 1, (
        "à %d px, le badge déborde de %d px de sa colonne (%d px de badge pour "
        "%d px disponibles) : le texte est effacé sans signal"
        % (largeur, m["depasse"], m["w"], m["dispo"]))
    if largeur == 390:
        assert m["h"] > 26, (
            "le badge tient sur une ligne à 390 px : il a été tronqué, pas replié")
# ── Contre-mesures du contrôleur adverse ──────────────────────────────
#: Les jeux d'axes RÉELLEMENT servis par le produit, plus leur variante tout
#: en majuscules — le cas que le lot déclarait ne pas couvrir.
JEUX_AXES = {
    "scorecard Analyse": [("Momentum", 70), ("Tendance", 50), ("Qualité", 60),
                          ("Valorisation", 40), ("Volatilité", 30)],
    "dossier Vertex IA": [("Conviction", 70), ("Risque", 50), ("Persistance", 60),
                          ("Ordre", 40), ("Efficience", 30), ("Momentum", 20)],
    "greeks Options": [("Delta", 70), ("Gamma", 50), ("Vega", 60), ("Theta", 40)],
    "majuscules": [("MOMENTUM", 70), ("TENDANCE", 50), ("QUALITÉ", 60),
                   ("VALORISATION", 40), ("VOLATILITÉ", 30)],
}


@pytest.mark.parametrize("jeu", sorted(JEUX_AXES))
def test_elargir_le_cadre_du_radar_ne_doit_pas_rapetisser_ses_libelles(page_js, jeu):
    """Un cadre élargi n'est PAS gratuit : le SVG est servi en `width:100%`,
    donc dans une carte plus étroite que le `viewBox` c'est tout le dessin qui
    rapetisse, libellés compris. Décoller le libellé du bord en surprovisionnant
    la marge remplace « coupé » par « illisible » — le défaut est déplacé, pas
    corrigé.

    Mesuré le 06/09/2026 sur les octets servis, cinq axes de la scorecard,
    fonte de conception 9,5 px :

        hôte de 390 px | marge par plus-long-libellé (`viewBox` 430) → 8,62 px
                       | marge par débordement mesuré (`viewBox` 352) → 9,50 px
        hôte de 300 px | `viewBox` 430 → 6,63 px | `viewBox` 352 → 8,10 px

    et sur /system/design-system à 390 px, où la carte rend 298 px, la fonte
    tombait à 6,58 px contre 9,50 px avant le lot.

    Le banc mesure les DEUX propriétés ensemble — aucun libellé coupé ET fonte
    rendue lisible — parce qu'elles se paient l'une l'autre : figer une seule
    des deux laisserait passer le correctif qui sacrifie l'autre.
    """
    axes = "[" + ",".join("{label:'%s',value:%d}" % (l, v)
                          for l, v in JEUX_AXES[jeu]) + "]"
    for hote, plancher in ((390, 9.4), (300, 7.8)):
        m = page_js.evaluate(
            """(a) => {
              const h = document.createElement('div');
              h.style.width = a.hote + 'px';
              document.body.appendChild(h);
              window.VXCharts.radar(h, {axes: eval(a.axes)});
              const svg = h.querySelector('svg');
              const vb = svg.getAttribute('viewBox').split(' ').map(Number);
              const rendu = svg.getBoundingClientRect().width;
              const coupes = [...svg.querySelectorAll('text')].map(t => {
                const b = t.getBBox();
                return {t: t.textContent, x0: +b.x.toFixed(1),
                        x1: +(b.x + b.width).toFixed(1)};
              }).filter(t => t.x0 < -0.2 || t.x1 > vb[2] + 0.2);
              const out = {vb: vb[2], rendu: +rendu.toFixed(1),
                           fonte: +(rendu / vb[2] * 9.5).toFixed(2), coupes};
              h.remove(); return out;
            }""", {"hote": hote, "axes": axes})
        assert not m["coupes"], (
            "%s, hôte de %d px : libellé(s) hors du cadre de %d — %s"
            % (jeu, hote, m["vb"], m["coupes"]))
        assert m["fonte"] >= plancher, (
            "%s, hôte de %d px : le cadre de %d rapetisse les libellés à "
            "%.2f px (plancher %.1f). Le libellé n'est plus coupé, il est "
            "illisible : la marge est provisionnée bien au-delà du "
            "débordement mesuré."
            % (jeu, hote, m["vb"], m["fonte"], plancher))


def test_moins_de_trois_axes_mesures_nomme_l_absence_au_lieu_du_vide(page_js):
    """Filtrer les axes sans valeur fait tomber sous les trois sommets qu'un
    polygone exige. Rendre le vide à ce moment-là fait DEUX pertes que le filtre
    était censé empêcher : les valeurs réellement mesurées sont jetées, et les
    absences ne sont nommées nulle part.

    Mesuré le 06/09/2026, cinq axes dont deux mesurés (Del 30, Eps 10) :

        avant le filtre → radar complet, aria « Alpha 0, Beta 0, Gam 0,
                          Del 30, Eps 10 » — trois zéros imputés, faux
        avec le filtre  → `innerHTML` de 0 caractère : carte blanche

    Une carte blanche ne nomme rien (invariants 4 et 6). Aucune page n'atteint
    ce chemin tant que `analysis_page` et `intelligence_page` imputent leurs
    zéros en amont (`a[1]||0`, `s.conviction??0`) ; il devient le cas courant
    d'une scorecard partielle dès que ces imputations tombent.
    """
    r = page_js.evaluate(
        """() => {
          const h = document.createElement('div');
          document.body.appendChild(h);
          window.VXCharts.radar(h, {axes:[
            {label:'Alpha'}, {label:'Beta'}, {label:'Gam'},
            {label:'Del', value:30}, {label:'Eps', value:10}]});
          const out = {texte: h.textContent.trim(),
                       absents: !!h.querySelector('.vx-primitive-absents'),
                       svg: !!h.querySelector('svg')};
          h.remove(); return out;
        }""")
    assert not r["svg"], "deux axes mesurés ne font pas un polygone"
    assert r["absents"], (
        "trois dimensions absentes ne sont nommées nulle part : la carte est "
        "muette, le lecteur ne sait pas qu'elles ont existé — %r" % r["texte"])
    for absent in ("Alpha", "Beta", "Gam"):
        assert absent in r["texte"], (
            "l'absence de %s n'est pas nommée : %r" % (absent, r["texte"]))
    for mesure in ("30", "10"):
        assert mesure in r["texte"], (
            "la valeur mesurée %s est jetée avec le graphique : %r"
            % (mesure, r["texte"]))
