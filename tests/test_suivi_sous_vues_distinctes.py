"""LOT F — SUIVI : deux onglets pour un seul écran, et des tirets muets.

Mesures du 2026-09-06, Chromium sur instance QA (`tools/qa/run_qa_instance.py`,
NO_IBKR=1, DEMO=0), un suivi enregistré (NVDA, OPTION, ACTIVE).

## Défaut 1 — « À revoir » et « Suivis actifs » rendaient le même écran

MESURE AVANT — les deux sous-vues, relevées dans le DOM :

```text
attention : sections [summary, chart, active] · titre « Suivis actifs »
            question « Que valent ces idées… » · 1 ligne
active    : sections [summary, chart, active] · titre « Suivis actifs »
            question « Que valent ces idées… » · 1 ligne
```

Rigoureusement identiques. Cliquer « Suivis actifs » après « À revoir » ne
changeait rien — et « À revoir », qui est la sous-vue **par défaut**, portait
le titre de l'autre.

MESURE APRÈS :

```text
attention : sections [summary, active] · titre « À revoir »
            question « Quels suivis attendent une donnée… » · 0 ligne
            « Rien à revoir — Les suivis actifs ont tous un prix de
              référence : rien n'attend de donnée. »
active    : sections [summary, chart, active] · titre « Suivis actifs »
            question « Que valent ces idées… » · 1 ligne
```

Le critère de « à revoir » est **servi**, pas inventé : `/api/tracking` rend
`status` ∈ {ACTIVE, DATA_REQUIRED, STOPPED}, et `DATA_REQUIRED` désigne
littéralement le suivi qu'on ne peut pas mesurer faute de prix de référence.
Aucun seuil de performance n'entre ici : « sous-performe SPY » serait un
jugement de la page, pas un état de la donnée.

Le graphique disparaît de « À revoir » parce qu'il répond à la question de
l'autre onglet — et parce que les lignes retenues sont justement celles qui
n'ont pas de série à tracer.

## Défaut 2 — trois absences, un seul tiret

MESURE AVANT, sur une instance QA fraîche (SPY pas encore coté) :

```text
/api/tracking/<id>/performance
  → {return_pct: 0.0, benchmark_return_pct: null, alpha_pct: null}
tableau : Rdt hypo. « +0,00 % » · SPY « — » · Alpha « — »
```

Le même « — » servait à trois choses : *le suivi n'a pas de prix de
référence*, *la référence SPY n'est pas cotée*, et *la route de performance
n'a pas répondu pour cette ligne*. Ces trois causes n'appellent pas la même
action, et la première est la seule que l'utilisateur puisse corriger.

Ce banc n'impose aucune formulation : il exige que les causes **diffèrent**.
"""
from __future__ import annotations

import json
import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(RACINE, 'vertex', 'static', 'vertex', 'js', 'pages', 'tracking.js')
PAGE = os.path.join(RACINE, 'vertex', 'ui', 'pages', 'tracking_page.py')


def _js() -> str:
    with open(JS, encoding='utf-8') as fh:
        return fh.read()


def _sans_commentaires(source: str) -> str:
    """Le source privé de ses `/* … */` et de ses `//`.

    Les commentaires de ce fichier CITENT le défaut corrigé ; les relire
    reviendrait à accuser la page de le contenir encore.
    """
    source = re.sub(r'/\*.*?\*/', ' ', source, flags=re.S)
    return re.sub(r'^\s*//.*$', ' ', source, flags=re.M)


def _chromium():
    from tools.mesures.mesurer_qa_espaces import _chromium as resoudre
    return resoudre()


def _navigateur_dispo() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(executable_path=_chromium(),
                              args=['--no-sandbox']).close()
        return True
    except Exception:
        return False


_SANS_NAVIGATEUR = pytest.mark.skipif(
    not _navigateur_dispo(),
    reason='playwright/chromium absent — la propriété ne serait pas mesurée')


@pytest.fixture(scope='module')
def bac():
    """Le module entier, chargé dans Chromium.

    `tracking.js` est une IIFE : ses fonctions ne sortent pas. Le banc en
    exporte le strict nécessaire en réécrivant la dernière ligne — il exécute
    donc le VRAI source, pas une copie qui pourrait diverger.
    """
    from playwright.sync_api import sync_playwright
    src = _js()
    assert src.rstrip().endswith('})();'), (
        'tracking.js n’est plus une IIFE — le harnais doit être relu')
    #  `loadActive()` s'exécute au chargement : sans DOM ni route, il échoue en
    #  silence dans son propre .catch. On exporte avant de le laisser courir.
    expose = ('\n  window.__bac = {activeRow: activeRow, aReVoir: aReVoir,'
              ' pctCause: pctCause};\n})();')
    src = src.rstrip()[:-len('})();')] + expose
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=_chromium(), args=['--no-sandbox'])
        page = nav.new_page()
        page.goto('about:blank')
        page.add_script_tag(content=src)
        try:
            yield page
        finally:
            nav.close()


def _appel(page, expression):
    return page.evaluate('() => %s' % expression)


# ═══ Défaut 1 — les deux sous-vues ═══

def test_les_sous_vues_ne_montrent_plus_les_memes_sections():
    """La table `montre` donnait `attention` et `active` à l'identique.

    Mesure de PROPRIÉTÉ : les deux listes doivent différer. Aucun contenu de
    liste n'est imposé — seulement qu'elles ne soient plus la même.
    """
    src = _sans_commentaires(_js())
    bloc = re.search(r'var montre = \{(.*?)\}\[v\]', src, re.S)
    assert bloc, 'la table des sous-vues est introuvable'
    vues = dict(re.findall(r"(\w+):\s*\[([^\]]*)\]", bloc.group(1)))
    assert {'attention', 'active', 'archives'} <= set(vues), vues
    assert vues['attention'] != vues['active'], (
        'les deux sous-vues montrent les mêmes sections : l’onglet ne change '
        'rien (défaut mesuré le 06/09/2026)')


@_SANS_NAVIGATEUR
def test_a_revoir_retient_ce_qui_attend_une_donnee(bac):
    """`DATA_REQUIRED` et « pas de prix de référence » sont à revoir ; un suivi
    mesurable ne l'est pas. Sans ce tri, « À revoir » listait tout."""
    mesurable = {'status': 'ACTIVE', 'reference_price': 27.32}
    sans_ref = {'status': 'ACTIVE', 'reference_price': None}
    attend = {'status': 'DATA_REQUIRED', 'reference_price': 12.0}
    assert _appel(bac, 'window.__bac.aReVoir(%s)' % json.dumps(mesurable)) is False
    assert _appel(bac, 'window.__bac.aReVoir(%s)' % json.dumps(sans_ref)) is True
    assert _appel(bac, 'window.__bac.aReVoir(%s)' % json.dumps(attend)) is True


def test_le_titre_de_la_section_est_nommable():
    """Le titre disait « Suivis actifs » dans les DEUX sous-vues.

    Il ne peut être corrigé que s'il porte un identifiant : gardien de la
    jointure entre la page et son script, pas d'une phrase.
    """
    with open(PAGE, encoding='utf-8') as fh:
        page = fh.read()
    for ident in ('vx-trk-active-title', 'vx-trk-active-question'):
        assert ident in page, '%s absent : le script ne peut plus nommer la vue' % ident
    src = _sans_commentaires(_js())
    for ident in ('vx-trk-active-title', 'vx-trk-active-question'):
        assert ident in src, '%s jamais lu : le titre resterait celui de l’autre vue' % ident


# ═══ Défaut 2 — les trois absences ═══

@_SANS_NAVIGATEUR
def test_trois_absences_trois_causes(bac):
    """LA propriété violée par le tiret unique.

    Suivi sans référence · référence SPY non cotée · performance non lue :
    trois lignes, et les cellules concernées ne doivent pas se ressembler.
    """
    base = {'symbol': 'NVDA', 'entity_type': 'OPTION', 'started_at': None,
            'reference_price_type': 'MID', 'strategy_decision_at_start': 'SURVEILLER'}
    sans_ref = dict(base, reference_price=None)
    avec_ref = dict(base, reference_price=27.32)

    #  1. mesuré, mais SPY absent
    spy_absent = _appel(bac, 'window.__bac.activeRow(%s, %s)' % (
        json.dumps(avec_ref),
        json.dumps({'current_price': 27.32, 'return_pct': 0.0,
                    'benchmark_return_pct': None, 'alpha_pct': None,
                    'mfe_pct': 4.69, 'mae_pct': 0.0})))
    #  2. pas de prix de référence : rien n'est mesurable
    sans_reference = _appel(bac, 'window.__bac.activeRow(%s, %s)' % (
        json.dumps(sans_ref),
        json.dumps({'current_price': 27.32, 'return_pct': None,
                    'benchmark_return_pct': None, 'alpha_pct': None,
                    'mfe_pct': None, 'mae_pct': None})))
    #  3. la route de performance n'a pas répondu
    non_lu = _appel(bac, 'window.__bac.activeRow(%s, null)' % json.dumps(avec_ref))

    assert spy_absent != sans_reference != non_lu
    #  Le cas 1 garde son rendement mesuré : l'absence est LOCALE à SPY.
    assert '+0,00 %' in spy_absent or '+0.00 %' in spy_absent, spy_absent
    #  Aucune des trois n'écrit le tiret cadratin muet dans les colonnes
    #  chiffrées — le seul « — » licite reste la décision initiale absente.
    for ligne, nom in ((spy_absent, 'SPY absent'), (sans_reference, 'sans réf.'),
                       (non_lu, 'non lu')):
        cellules = re.findall(r'<td>(.*?)</td>', ligne, re.S)[3:8]
        assert not any(c.strip() == '<span class="vx-muted">—</span>'
                       for c in cellules), '%s : tiret muet dans %r' % (nom, cellules)


@_SANS_NAVIGATEUR
def test_une_valeur_connue_reste_chiffree(bac):
    """Le témoin négatif : nommer les absences ne doit pas manger les nombres."""
    ligne = _appel(bac, 'window.__bac.pctCause(-1.5, "jamais")')
    assert '1,50 %' in ligne or '1.50 %' in ligne, ligne
    assert 'jamais' not in ligne
    assert 'vx-neg' in ligne


@_SANS_NAVIGATEUR
def test_la_cause_est_echappee(bac):
    """La cause traverse `esc()` : elle vient du code, mais la règle du produit
    est qu'aucune chaîne n'entre dans le DOM sans échappement."""
    ligne = _appel(bac, 'window.__bac.pctCause(null, "<b>x</b>")')
    assert '<b>' not in ligne, ligne
    assert '&lt;b&gt;' in ligne, ligne
