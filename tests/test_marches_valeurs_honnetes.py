"""Vertex — MARCHÉS : ce que chaque carte AFFIRME doit être ce que la donnée DIT.

Six défauts mesurés le 06/09/2026 sur la page « Marchés », instance QA
(`tools/qa/run_qa_instance.py`, NO_IBKR=1, DEMO=0, scan yfinance peuplé :
513 lignes, 9 secteurs, spy_regime='NEUTRAL'). Chaque mesure « avant » a été
refaite en rejouant la MÊME charge sur deux instances — l'une servant la page
au SHA de base, l'autre la page corrigée — pour que la différence vienne du
code et non d'un scan qui bouge.

## 1. Une part servie, lue comme un compte (le plus grave)

`market_ctx.breadth.buy` est une PART : son producteur écrit
`round(100 * nb de verdicts BUY / N)` (vertex/market/context.py). La carte
« Détail — au-dessus des moyennes » l'affichait NU, entre deux lignes qui sont
des comptes (« Avancées / Déclins · 182 / 331 ») :

    Signaux d’achat (univers)      18        ← 18 signaux ?

Mesure du même scan : 94 verdicts BUY sur 513 titres, soit 18 %. L'entonnoir
de la MÊME vue affichait « 94 · Achats » deux cartes plus bas. Le lecteur avait
sous les yeux deux nombres pour une seule grandeur, dans un rapport de 1 à 5.

## 2. Codes moteur anglais rendus tels quels (invariant 8)

`spy_regime` ne prend que trois valeurs (TREND / CHOP / NEUTRAL,
vertex/market/context.py). Trois cartes les peignaient brutes — « Régime S&P
500 · NEUTRAL », « Régime NEUTRAL — … », « Régime · NEUTRAL » — alors que la
page Aujourd'hui traduit déjà le même champ. La table locale de Marchés portait
UP et DOWN, deux valeurs qu'aucun moteur ne produit, et pas NEUTRAL, la seule
servie. Même défaut sur les verdicts du scan : « AVOID domine (219 titre(s) sur
513) » et une légende BUY / WATCH / WAIT / AVOID, quand la table canonique de la
coque (`window.__VXVOCAB`) dit Éviter / Achat / Surveiller / Attendre.

## 3. « Appétit pour le risque » sans provenance (invariant 5)

Seule carte de la vue Macro sans source, sans horodatage et sans fraîcheur,
pendant que les cinq voisines affichaient « Il y a 23 min · yfinance Différé ».
Elle porte pourtant un régime, un VIX et une participation — des valeurs
critiques. Ce qu'elle peint n'est pas une seconde mesure : `/api/market/summary`
re-sert `scan.market_ctx` champ pour champ (vertex/app/routes/feeds.py).

## 4. Une couleur qui contredit le chiffre qu'elle recouvre

`heatmapCard` n'a qu'un couple (min,max) pour TOUT le tableau. La carte
« Performance et momentum par secteur » lui passe -3 / +3 — l'échelle d'une
variation quotidienne — et lui donnait la colonne Score, notée de 0 à 100.
Mesure des neuf cellules : `rgba(54,200,137,.5)` NEUF fois, le vert maximal,
Conso 27 peint comme Finance 80, sous une légende qui dit « Vert = flux
entrant ».

## 5. Deux coordonnées inventées dans le nuage de rotation

`s.score||50` visait un champ que `scan.sectors[]` ne porte pas : la valeur
était donc TOUJOURS 50, et la variation manquante devenait 0. Reproduit en
servant un /scan dont « Conso » perd ses deux mesures : le point apparaissait à
(50 ; 0), au centre exact des quadrants, indiscernable d'une mesure réelle.

## 6. Décimales anglaises sur une page française

Mesuré au navigateur : « 14.5 » (le plus gros chiffre de la vue Volatilité),
« Spread 10a-3m +1.02 pt », RVOL « 0.84 / 1.15 », axes « 3.5 % » et « -4.0 % » —
au-dessus de tableaux qui écrivent « -1,28 % ».

Les gardiens ci-dessous mesurent des PROPRIÉTÉS (l'AST du producteur, la forme
des cellules passées à la heatmap, la présence d'un traducteur sur les lignes
de rendu), jamais une phrase d'écran : une reformulation ne doit pas les casser,
un retour du défaut doit les casser.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
MARCHES = RACINE / 'vertex' / 'ui' / 'pages' / 'markets_page.py'
CONTEXTE = RACINE / 'vertex' / 'market' / 'context.py'


def _src() -> str:
    return MARCHES.read_text(encoding='utf-8')


def _sans_commentaires(src: str) -> str:
    """Le CODE seul : un commentaire qui cite le défaut ne doit pas le sauver."""
    return re.sub(r'/\*.*?\*/', '', src, flags=re.S)


def _fonction(nom: str, src: str) -> str:
    """Corps d'une fonction JS, accolades équilibrées (`async` accepté)."""
    i = src.index('function %s(' % nom)
    prof, j = 0, i
    while j < len(src):
        if src[j] == '{':
            prof += 1
        elif src[j] == '}':
            prof -= 1
            if prof == 0:
                return src[i:j + 1]
        j += 1
    raise AssertionError('fonction %s non refermée' % nom)


# ══ 1. La part d'achats est une PART — le producteur le dit, l'écran doit le dire
def test_le_producteur_sert_une_part_pas_un_compte():
    """AST du producteur : `breadth['buy']` = round(100 * BUY / N), donc un %."""
    arbre = ast.parse(CONTEXTE.read_text(encoding='utf-8'))
    expressions = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Dict):
            for cle, valeur in zip(noeud.keys, noeud.values):
                if isinstance(cle, ast.Constant) and cle.value == 'buy':
                    expressions.append(ast.unparse(valeur))
    assert expressions, "clé 'buy' introuvable dans vertex/market/context.py"
    formule = expressions[0]
    assert '100' in formule and '/' in formule, (
        "`buy` n'est plus une part (%s) : si le moteur sert désormais un COMPTE, "
        "c'est l'écran qui doit changer d'unité, pas ce gardien qui doit sauter"
        % formule)


def test_la_part_d_achats_affichee_porte_son_unite():
    """Sans « % », 18 se lit « 18 titres » là où le scan en compte 94."""
    corps = _sans_commentaires(_fonction('loadBreadth', _src()))
    lignes = [x for x in corps.splitlines() if 'bo.buy' in x and 'kv(' in x]
    assert lignes, 'la ligne qui rend `bo.buy` a disparu'
    for ligne in lignes:
        assert '%' in ligne, (
            'part servie rendue sans unité — le lecteur lit un compte : ' + ligne.strip())


# ══ 2. Aucun code moteur anglais n'atteint l'écran ═══════════════════
#  Une ligne qui CONSTRUIT du texte (esc, kv, sigText, conclusion) et qui parle
#  du régime doit passer par le traducteur. Reformuler la carte ne casse rien ;
#  réintroduire `esc(m.spy_regime)` casse.
_RENDU = ('esc(', 'kv(', 'sigText(', 'conclusion:')


def test_aucun_code_de_regime_du_sp_n_atteint_l_ecran_sans_traduction():
    code = _sans_commentaires(_src())
    fautives = [ligne.strip() for ligne in code.splitlines()
                if ('spy_regime' in ligne or 's.regime' in ligne)
                and any(marque in ligne for marque in _RENDU)
                and 'spyRegFr' not in ligne]
    assert not fautives, (
        'code moteur (TREND/CHOP/NEUTRAL) peint tel quel : %s' % fautives)


def test_le_traducteur_de_regime_couvre_les_valeurs_reellement_produites():
    """La table locale portait UP/DOWN (jamais produits) et pas NEUTRAL (servi)."""
    produites = set()
    arbre = ast.parse(CONTEXTE.read_text(encoding='utf-8'))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            if noeud.value in ('TREND', 'CHOP', 'NEUTRAL'):
                produites.add(noeud.value)
    assert produites == {'TREND', 'CHOP', 'NEUTRAL'}, produites
    table = re.search(r'const SPY_REGIME_FR=\{([^}]*)\}', _src())
    assert table, 'table de traduction du régime S&P introuvable'
    for code in produites:
        assert code + ':' in table.group(1), (
            '%s est servi par le moteur et n’a aucun libellé français' % code)


def test_les_verdicts_du_scan_passent_par_le_vocabulaire_canonique():
    corps = _sans_commentaires(_fonction('loadBreadth', _src()))
    lignes = [x for x in corps.splitlines()
              if ('top[0][0]' in x or 'labels:top.map' in x)]
    assert lignes, 'le donut des verdicts a disparu'
    for ligne in lignes:
        assert 'verdFr' in ligne, 'verdict moteur peint brut : ' + ligne.strip()
    defn = [x for x in _sans_commentaires(_src()).splitlines() if 'const verdFr=' in x]
    assert defn and '__VXVOCAB' in defn[0], (
        'le vocabulaire doit venir de la table canonique de la coque')
    assert 'AVOID' not in defn[0] and 'BUY' not in defn[0], (
        'une table locale divergerait du moteur au premier verdict ajouté')


# ══ 3. Provenance de la carte « Appétit pour le risque » ═════════════
def test_la_carte_appetit_pour_le_risque_est_datee_et_sourcee():
    src = _sans_commentaires(_src())
    corps = _fonction('loadMacroRegime', src)
    assert 'VX.updateIndicator' in corps, (
        'carte de régime/VIX/participation sans source ni horodatage (invariant 5)')
    signature = re.search(r'function loadMacroRegime\((\w*)\)', corps)
    assert signature and signature.group(1), (
        'sans l’instantané en paramètre, le pied ne peut pas dire l’âge de la donnée')
    argument = signature.group(1)
    assert re.search(r'loadMacroRegime\(%s\)' % argument, src), (
        'le répartiteur de vues doit passer l’instantané à la carte')


# ══ 4. Une seule colonne colorée : celle que la légende annonce ══════
def test_une_seule_colonne_de_la_heatmap_sectorielle_est_coloree():
    corps = _sans_commentaires(_fonction('loadSectors', _src()))
    bloc = corps[corps.index('rows:sectors.map('):corps.index('min:-3')]
    valeurs = [v.strip() for v in re.findall(r'value:([^,}]+)', bloc)]
    assert len(valeurs) == 4, valeurs
    colorees = [v for v in valeurs if v != 'null']
    assert len(colorees) == 1, (
        'l’échelle -3/+3 est celle d’une variation quotidienne : toute autre '
        'colonne qui la reçoit sature (mesuré : 9 scores sur 9 au vert maximal) '
        '— %s' % colorees)
    assert 'avg_change' in colorees[0], (
        'la seule colonne colorée doit être celle que la conclusion annonce')


# ══ 5. Le nuage de rotation ne fabrique aucune coordonnée ════════════
def test_le_nuage_de_rotation_ne_place_aucun_secteur_sans_coordonnees():
    corps = _sans_commentaires(_fonction('loadSectors', _src()))
    points = [x for x in corps.splitlines() if 'pts=' in x]
    assert points, 'le nuage de rotation a disparu'
    ligne = points[0]
    assert not re.search(r'\|\|\s*[\d.]', ligne), (
        'coordonnée de repli inventée (mesuré : tout secteur sans score '
        'atterrissait à x=50) : ' + ligne.strip())
    assert not re.search(r'!=\s*null\s*\?[^:]+:\s*[\d.]', ligne), (
        'variation manquante remplacée par un nombre : ' + ligne.strip())
    filtres = [x for x in corps.splitlines()
               if '.filter(' in x and 'avg_score' in x and 'avg_change' in x]
    assert filtres, 'les secteurs non cotés doivent être écartés du nuage'


def test_l_hote_du_nuage_ne_reste_jamais_vide_et_muet():
    """`vx-mk-rotation` doit être peint sur TOUTE sortie de `loadSectors`.

    Première rédaction de ce gardien : `assert "emptyCard('vx-mk-rotation'" in
    corps`. Une chaîne figée, pas une propriété — et elle passait au vert sur
    une page où l'hôte restait muet. Mesuré au navigateur le 06/09/2026 sur
    5003 (`/scan` sert `sectors: []`, démarrage à froid) : l'état vide existait
    bien dans le fichier, mais dans la branche « secteurs présents, aucun
    coté » ; la sortie anticipée « aucun secteur » rendait la main AVANT de
    l'atteindre, et `#vx-mk-rotation` mesurait 869 × 224 px pour
    `innerHTML.length === 0` — seul hôte muet des six vues de Marchés.

    On mesure donc la REACHABILITÉ : un `return;` nu quitte la fonction, et
    tout hôte non peint à cet instant reste vide. Chaque sortie doit avoir
    nommé les trois hôtes de la vue.
    """
    corps = _sans_commentaires(_fonction('loadSectors', _src()))
    hotes = ('vx-mk-rotation', 'vx-mk-sectors-heat', 'vx-mk-sectors-leaders')
    sorties = [m.start() for m in re.finditer(r'\breturn\s*;', corps)]
    assert sorties, 'plus aucune sortie anticipée : ce gardien doit être revu'
    for pos in sorties:
        amont = corps[:pos]
        muets = [h for h in hotes if h not in amont]
        assert not muets, (
            'sortie de loadSectors laissant %s vide(s) et muet(s) — mesuré : '
            '869 × 224 px sans un caractère' % ', '.join(muets))
    #  Et la branche « secteurs présents mais non cotés » garde son état propre.
    assert "emptyCard('vx-mk-rotation'" in corps.split('return;')[-1], (
        'aucun état honnête pour la carte de rotation dans le cas coté')


# ══ 6. Décimales françaises ══════════════════════════════════════════
#  `toFixed` est légitime pour une GÉOMÉTRIE (largeur CSS, coordonnée SVG) et
#  faux pour un nombre lu par un humain. La règle mesure le contexte de la ligne.
_GEOMETRIE = ('style=', '--vx-rail-pos', 'viewBox', ' L', ' C')


@pytest.mark.parametrize('nom', ['loadYield', 'loadVix', 'loadMultiIndex',
                                 'loadMacroRegime', 'loadSectors'])
def test_les_nombres_lus_par_un_humain_sortent_en_francais(nom):
    corps = _sans_commentaires(_fonction(nom, _src()))
    for ligne in corps.splitlines():
        if 'toFixed(' in ligne:
            assert any(g in ligne for g in _GEOMETRIE), (
                'nombre affiché en notation anglaise (mesuré : « +1.02 pt », '
                '« -4.0 % ») : ' + ligne.strip())


def test_les_grandeurs_a_decimales_ne_passent_pas_par_le_formateur_neutre():
    """`VX.fmt.nd` rend la valeur TELLE QUELLE : « 14.5 » sur une page française."""
    code = _sans_commentaires(_src())
    for champ in ('vix', 'sec.avg_rvol', 's.vix'):
        assert 'VX.fmt.nd(%s)' % champ not in code, (
            '%s porte des décimales : `nd` les rend en notation anglaise' % champ)


# ══ 7. Le grand chiffre et son libellé ne se touchent pas ═══════════
def test_le_grand_chiffre_et_son_libelle_ne_sont_pas_colles():
    """`.vx-stat-xl` EST le nombre (cockpit.css) ; le libellé est un bloc dessous.

    La page emboîtait les deux dans un `.vx-stat-xl` commun, le libellé en
    `<span>` derrière une classe `.vx-stat-xl-value` qu'aucune feuille servie
    ne définit. Mesuré au navigateur le 06/09/2026 sur les deux vues
    concernées : valeur x=1053 largeur=100, libellé x=1153, même ligne —
    « 48 %TITRES > MM50 » et « 14,5INDICE VIX », à 1600 comme à 390 px.
    """
    feuilles = sorted((RACINE / 'vertex' / 'static' / 'vertex' / 'css').glob('*.css'))
    assert len(feuilles) > 10, 'les feuilles servies sont introuvables'
    css = ''.join(f.read_text(encoding='utf-8') for f in feuilles)
    assert 'vx-stat-xl-value' not in css, (
        'la classe a désormais une règle : ce gardien doit être revu, pas contourné')
    code = _sans_commentaires(_src())
    assert 'vx-stat-xl-value' not in code, (
        'classe sans règle : elle ne sépare pas le libellé du nombre')
    for m in re.finditer(r'class="vx-stat-xl-label"', code):
        ouvrant = code.rfind('<', 0, m.start())
        assert code.startswith('<div', ouvrant), (
            'libellé en ligne : il se colle au grand chiffre — '
            + code[ouvrant:ouvrant + 60])


# ══ Mesure navigateur (facultative) ══════════════════════════════════
#  Le banc ci-dessus mesure le code ; celui-ci mesure l'ÉCRAN. Il s'abstient
#  sans instance ouverte plutôt que d'échouer sur une absence d'environnement.
#  Usage : VERTEX_MESURE_BASE=http://127.0.0.1:5203 pytest tests/test_marches_valeurs_honnetes.py
def _base():
    return os.environ.get('VERTEX_MESURE_BASE') or ''


@pytest.mark.skipif(not _base(), reason='aucune instance de mesure (VERTEX_MESURE_BASE)')
def test_navigateur_les_cartes_disent_la_verite():
    pytest.importorskip('playwright.sync_api')
    from playwright.sync_api import sync_playwright
    base = _base()
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        contexte = navigateur.new_context(viewport={'width': 1600, 'height': 1000},
                                          service_workers='block')
        page = contexte.new_page()
        erreurs = []
        page.on('pageerror', lambda e: erreurs.append(str(e)[:200]))
        page.goto(base + '/markets?view=sectors', wait_until='networkidle')
        page.wait_for_timeout(2500)
        cellules = page.evaluate(
            "() => {const t=document.querySelector('#vx-mk-sectors-heat table.vx-heat');"
            "return t?[...t.querySelectorAll('tr')].slice(1).map(tr=>"
            "getComputedStyle(tr.children[2]).backgroundColor):[];}")
        #  L'INSTRUMENT D'ABORD : sur une instance sans scan, la heatmap n'a
        #  aucune ligne et « aucune cellule fautive » serait un verdict VIDE —
        #  vert pour la mauvaise raison. Mesuré : l'instance de contrôle sans
        #  collecte rendait 0 ligne et ce gardien passait sur la page NON
        #  corrigée. On refuse de conclure au lieu de rassurer.
        if len(cellules) < 3:
            pytest.skip('instance non peuplée (%d ligne(s) de secteurs) : '
                        'la mesure ne conclut pas' % len(cellules))
        assert not [c for c in cellules if 'rgba' in c], (
            'la colonne Score reçoit encore l’échelle de la variation : %s' % cellules)
        page.goto(base + '/markets?view=overview', wait_until='networkidle')
        page.wait_for_timeout(2500)
        texte = page.evaluate("() => (document.getElementById('vx-content')||document.body).innerText")
        if 'Régime S&P 500' not in texte:
            pytest.skip('aucun régime servi par cette instance : la mesure ne conclut pas')
        for code in ('NEUTRAL', 'AVOID', 'WATCH'):
            assert not re.search(r'\b%s\b' % code, texte), (
                'code moteur anglais à l’écran : ' + code)
        assert not erreurs, erreurs
        navigateur.close()
