"""La carte « Pannes en cours » dit ce que le serveur émet, pas l'inverse.

## La mesure (6 sept. 2026)

La carte `#vx-alerts-pannes` (page Système, vue Alertes) porte le sous-titre
« Qu'est-ce qui empêche Vertex de décider ? ». Son filtre était :

```js
if (v && v !== 'OK' && v !== 'LIVE') pannes.push(…)
```

Or le serveur n'émet **jamais** 'OK' ni 'LIVE' : le chemin nominal du scan
écrit `AVAILABLE` (terminal.py, bloc `source_health`), le vocabulaire public
est borné par `_PUBLIC_SOURCE_STATES`, et Stooq ajoute `CACHED`. La liste
blanche était donc du code MORT — aucune source ne pouvait être déclarée saine,
et l'état vide « Aucune panne rapportée » devenait inatteignable dès qu'un scan
aboutissait.

Relevé du DOM sur l'instance de contrôle, `/system?view=alerts` :

```text
Source fundamentals   · badge « dégradé » · texte « AVAILABLE »
Source market         · badge « dégradé » · texte « AVAILABLE »
Source options        · badge « dégradé » · texte « AVAILABLE »
Source scan           · badge « dégradé » · texte « AVAILABLE »
Source yfinance_budget· badge « dégradé » · texte « AVAILABLE »
```

Cinq sources parfaitement saines affichées en panne, en permanence, avec le
code moteur brut à l'écran — alors que le code de cette même carte affirme en
commentaire « une panne est un FAIT rapporté par le serveur, pas une
déduction » et « ils ne s'affichent jamais bruts ». Ce n'est pas cosmétique :
une vraie panne se serait noyée parmi cinq fausses, sur la carte dont la
fonction déclarée est de dire ce qui bloque la décision.

## Ce que ce banc verrouille

Tout état que le serveur peut servir doit être classé par la page : soit SAIN,
soit porteur d'un libellé français. Aucun code moteur ne peut atteindre
l'écran, et `AVAILABLE` ne peut plus jamais être compté comme une panne.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

_PAGE = RACINE / 'vertex' / 'ui' / 'pages' / 'system_page.py'


def _etats_emis() -> set[str]:
    """Vocabulaire de `source_health` DÉRIVÉ des émetteurs, pas recopié.

    Une liste écrite à la main ici se périmerait au premier état ajouté par le
    serveur — exactement la dérive qui a produit le défaut.
    """
    from vertex.app.routes.analysis_api import _PUBLIC_SOURCE_STATES

    etats = set(_PUBLIC_SOURCE_STATES)
    terminal_src = (RACINE / 'terminal.py').read_text(encoding='utf-8')
    for bloc in re.findall(r"'source_health': \{(.*?)\}", terminal_src, re.S):
        etats |= set(re.findall(r"'([A-Z][A-Z_]{2,})'", bloc))
    #  Les deux budgets de source servis dans le même bloc.
    for fichier in ('terminal.py', 'vertex/data_sources/stooq.py'):
        src = (RACINE / fichier).read_text(encoding='utf-8')
        for ligne in re.findall(r'_SOURCE_BUDGET_STATE\[[^\]]+\] = [^\n]+', src):
            etats |= set(re.findall(r"'([A-Z][A-Z_]{2,})'", ligne))
    return etats


def _dictionnaires_de_la_page() -> tuple[set[str], set[str]]:
    src = _PAGE.read_text(encoding='utf-8')
    sain = re.search(r'const SAIN=\{(.*?)\};', src, re.S)
    lib = re.search(r'const LIB=\{(.*?)\};', src, re.S)
    assert sain and lib, 'les deux dictionnaires de la carte ont disparu'
    cles = lambda bloc: set(re.findall(r'([A-Z][A-Z_]+)\s*:', bloc))  # noqa: E731
    return cles(sain.group(1)), cles(lib.group(1))


def test_le_denominateur_du_banc_n_est_pas_vide():
    """Une extraction qui ne rend rien rendrait tous les contrôles vrais."""
    emis = _etats_emis()
    assert {'AVAILABLE', 'DEGRADED', 'UNAVAILABLE', 'NOT_COLLECTED',
            'UNKNOWN', 'CACHED'} <= emis, emis
    sain, lib = _dictionnaires_de_la_page()
    assert sain and lib


def test_une_source_saine_n_est_jamais_declaree_en_panne():
    """MESURÉ : 5 sources à `AVAILABLE` affichées « dégradé » en permanence."""
    sain, _lib = _dictionnaires_de_la_page()
    assert 'AVAILABLE' in sain, (
        'AVAILABLE — ce que le scan nominal écrit — n’est pas reconnu comme '
        'sain : la carte des pannes accuse un serveur en bonne santé et son '
        'état vide devient inatteignable')


def test_la_liste_blanche_ne_contient_aucun_etat_que_le_serveur_n_emet_pas():
    """LA RÉCIDIVE, prise du côté rassurant.

    MESURE (6 sept. 2026, après le premier correctif) :

    ```text
    états émis par le serveur : AVAILABLE CACHED DEGRADED NOT_COLLECTED
                                UNAVAILABLE UNKNOWN
    SAIN                      : AVAILABLE LIVE OK
    SAIN hors émis            : LIVE OK        ← 2 clés sur 3, code mort
    ```

    Le défaut d'origine était une liste blanche morte `{OK, LIVE}` : le
    correctif a ajouté `AVAILABLE` sans retirer les deux mots que le serveur
    n'écrit nulle part. Inoffensif aujourd'hui, mais c'est exactement le même
    vocabulaire mort, et c'est de là que venait la faute. Une liste de DÉCISION
    se dérive des émetteurs ; `LIB`, qui ne fait que traduire, reste libre
    d'anticiper — une traduction en trop ne déclare jamais une panne saine.
    """
    sain, _lib = _dictionnaires_de_la_page()
    emis = _etats_emis()
    morts = sorted(sain - emis)
    assert not morts, (
        'ces états sont déclarés SAINS alors qu’aucun émetteur du serveur ne '
        'les écrit : la liste blanche reprend du vocabulaire mort, celui-là '
        'même qui rendait « Aucune panne rapportée » inatteignable — %s' % morts)


def test_aucun_code_moteur_ne_peut_atteindre_l_ecran():
    """MESURÉ : 4 états sur 6 s'affichaient bruts (AVAILABLE, CACHED,
    NOT_COLLECTED, UNAVAILABLE) faute de libellé."""
    sain, lib = _dictionnaires_de_la_page()
    orphelins = sorted(_etats_emis() - sain - lib)
    assert not orphelins, (
        'ces états servis par le serveur ne sont ni classés sains ni traduits '
        '— ils s’afficheront tels quels sur la carte : %s' % orphelins)
    assert not (sain & lib), (
        'un état déclaré sain ET traduit en panne : %s' % sorted(sain & lib))


def test_l_absence_et_la_degradation_restent_distinctes():
    """Invariant 5. `NOT_COLLECTED` est un trou (« inconnu »), pas une source
    qui se dégrade ; le confondre ferait chercher une panne inexistante."""
    src = _PAGE.read_text(encoding='utf-8')
    i = src.index('if(v&&!SAIN[v])')
    fenetre = src[i:i + 220]
    assert "v==='UNKNOWN'" in fenetre and "v==='NOT_COLLECTED'" in fenetre, (
        'le ton « missing » ne couvre plus les deux formes d’absence : %s'
        % fenetre)
    assert "v!=='OK'" not in src and "v!=='LIVE'" not in src, (
        'la liste blanche morte {OK, LIVE} est de retour : le serveur n’émet '
        'aucun de ces deux mots, donc plus aucune source ne peut être saine')


#  ── LE BANC DE TEXTE A UNE LIMITE, ET LA VOICI COMBLÉE ─────────────────────
#  Tout ce qui précède fige des DICTIONNAIRES dans la source de la page : c'est
#  ce qu'il faut pour prouver qu'aucun état servi n'échappe au classement, mais
#  ça n'exécute jamais une ligne de JavaScript. Une erreur de syntaxe introduite
#  dans `loadAlerts` ou `loadAutomations` passerait donc tous les contrôles
#  ci-dessus pendant que la page Système entière cesserait de se peindre —
#  85 247 octets de JS en ligne (mesuré sur /system) reposant sur zéro parseur.

def _navigateur_pret():
    from tools.mesures.mesurer_qa_espaces import navigateur_pret
    return navigateur_pret()


@pytest.mark.skipif(not _navigateur_pret(),
                    reason='playwright/chromium absent — la syntaxe du JS servi '
                           'ne peut pas être vérifiée ici')
def test_le_javascript_servi_par_la_page_systeme_est_analysable():
    """MESURE : /system sert 2 blocs `<script>` en ligne, 85 247 octets. Le
    parseur ne les EXÉCUTE pas (`new Function` compile sans appeler) — on
    mesure la syntaxe, pas le comportement, donc sans effet de bord."""
    from playwright.sync_api import sync_playwright

    from vertex.runtime import app

    html = app.test_client().get('/system').get_data(as_text=True)
    blocs = [b for b in re.findall(
        r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S) if b.strip()]
    assert blocs, 'aucun script en ligne dans /system : le banc ne mesure rien'
    erreurs = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        page = nav.new_page()
        for i, bloc in enumerate(blocs):
            verdict = page.evaluate(
                "s => { try { new Function(s); return 'ok'; }"
                " catch (e) { return String(e); } }", bloc)
            if verdict != 'ok':
                erreurs.append('bloc %d (%d octets) : %s' % (i, len(bloc), verdict))
        nav.close()
    assert not erreurs, (
        'le JavaScript servi par la page Système ne compile pas — la page ne '
        'se peindra pas du tout : %s' % erreurs)
