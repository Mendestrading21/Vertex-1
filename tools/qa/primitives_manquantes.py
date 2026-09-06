# -*- coding: utf-8 -*-
"""tools/qa/primitives_manquantes.py — une page appelle-t-elle une primitive
de graphique qu'elle ne charge pas ?

Mesuré le 2026-09-06 par l'audit navigateur : `/system?view=data` levait
`TypeError: VXCharts.donutCard is not a function`. La page charge pourtant
`donut-chart.js`. La cause est plus subtile et se reproduit ailleurs : la
garde `whenChartsReady` ne teste que l'existence de l'ESPACE DE NOMS
(`window.VXCharts && window.Chart`), pas celle de la FONCTION appelée. Or les
modules de graphique sont chargés en `defer` et enrichissent `VXCharts` un par
un : l'espace de noms existe dès le premier module, bien avant le dernier.

Un tel défaut ne se voit ni à la lecture, ni dans la suite de tests : il faut
une page réelle, la bonne sous-vue, et le bon ordre d'arrivée des scripts.
Cet outil le trouve statiquement, sur les douze pages à la fois, en croisant
trois faits :

1. quelles primitives chaque module de `js/charts/` DÉFINIT (`C.nom = …`) ;
2. quelles primitives chaque page APPELLE (`VXCharts.nom(`) ;
3. quels modules chaque page CHARGE (`<script src=".../charts/x.js">`).

Une primitive appelée sans que son module soit chargé est une erreur certaine.
Une primitive appelée derrière une garde qui ne la nomme pas est une erreur
probable, dépendante de l'ordre d'arrivée : elle est signalée à part.

Lecture seule.

    python tools/qa/primitives_manquantes.py [--json rapport.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CHARTS = os.path.join(RACINE, 'vertex', 'static', 'vertex', 'js', 'charts')
_PAGES = os.path.join(RACINE, 'vertex', 'ui', 'pages')
_JS_PAGES = os.path.join(RACINE, 'vertex', 'static', 'vertex', 'js', 'pages')

#: `C.nom=function`, `C.nom = (`, `VXCharts.nom = ` — les trois formes vues.
_DEFINIT = re.compile(r'\b(?:C|VXCharts|W\.VXCharts)\.([A-Za-z_]\w*)\s*=')
_APPELLE = re.compile(r'\bVXCharts\.([A-Za-z_]\w*)\s*\(')
_TESTE = re.compile(r'\bVXCharts\.([A-Za-z_]\w*)\b')
_CHARGE = re.compile(r'js/charts/([\w-]+)\.js')
#: Membres de l'espace de noms qui ne sont pas des primitives de dessin.
_NON_PRIMITIVES = {'colors', 'theme', 'fmt', 'ready', 'defaults', 'palette'}
#: Modules chargés par la COQUE, donc présents sur toutes les pages. Lus chez
#: la coque plutôt que recopiés : une liste figée mentirait au premier ajout.
_SHELL = os.path.join(RACINE, 'vertex', 'ui', 'shell')


def modules_de_la_coque() -> set[str]:
    out: set[str] = set()
    if not os.path.isdir(_SHELL):
        return out
    for nom in os.listdir(_SHELL):
        if nom.endswith('.py'):
            out.update(_CHARGE.findall(_lire(os.path.join(_SHELL, nom))))
    return out


def _lire(p: str) -> str:
    with open(p, encoding='utf-8') as f:
        return f.read()


def definitions() -> dict[str, str]:
    """{nom de primitive: module qui la définit}."""
    out: dict[str, str] = {}
    if not os.path.isdir(_CHARTS):
        return out
    for nom in sorted(os.listdir(_CHARTS)):
        if not nom.endswith('.js'):
            continue
        src = _lire(os.path.join(_CHARTS, nom))
        for m in _DEFINIT.finditer(src):
            out.setdefault(m.group(1), nom[:-3])
    return out


def _sources() -> list[tuple[str, str, set]]:
    """(étiquette, source, modules disponibles) pour chaque page et module.

    Un fichier de `js/pages/` ne porte aucune balise `<script>` : ses modules
    de graphique sont chargés par la ou les PAGES qui l'incluent. Les compter
    absents accusait à tort trois primitives d'options. On additionne donc les
    chargements de toutes les pages qui référencent le module.
    """
    coque = modules_de_la_coque()
    pages = []
    if os.path.isdir(_PAGES):
        for nom in sorted(os.listdir(_PAGES)):
            if nom.endswith('.py') and not nom.startswith('__'):
                pages.append((nom, _lire(os.path.join(_PAGES, nom))))
    out = [('pages/%s' % nom, src, set(_CHARGE.findall(src)) | coque)
           for nom, src in pages]
    if os.path.isdir(_JS_PAGES):
        for nom in sorted(os.listdir(_JS_PAGES)):
            if not nom.endswith('.js'):
                continue
            src = _lire(os.path.join(_JS_PAGES, nom))
            hotes = [p for _, p in pages if 'js/pages/' + nom in p]
            dispo = set(coque)
            for p in hotes:
                dispo |= set(_CHARGE.findall(p))
            out.append(('js/pages/%s' % nom, src, dispo))
    return out


def _garde_nomme(src: str, primitive: str) -> bool:
    """La page teste-t-elle explicitement CETTE primitive avant de l'appeler ?

    `if (window.VXCharts && VXCharts.donutCard)` est une garde correcte ;
    `if (window.VXCharts && window.Chart)` ne l'est pas — elle ne dit rien du
    module qui définit la primitive.
    """
    for m in _TESTE.finditer(src):
        if m.group(1) != primitive:
            continue
        suite = src[m.end():m.end() + 2].lstrip()
        if not suite.startswith('('):          # cité sans être appelé = testé
            return True
    return False


def analyser() -> dict:
    defs = definitions()
    certaines, probables = [], []
    for etiquette, src, charges in _sources():
        appels = {m.group(1) for m in _APPELLE.finditer(src)} - _NON_PRIMITIVES
        for prim in sorted(appels):
            module = defs.get(prim)
            if module is None:
                certaines.append({'page': etiquette, 'primitive': prim,
                                  'quoi': 'primitive DÉFINIE NULLE PART'})
            elif module not in charges:
                #  Une page servie peut hériter des scripts de la coque : on le
                #  dit comme probable, pas comme certain, plutôt que d'accuser.
                probables.append({'page': etiquette, 'primitive': prim,
                                  'module': module,
                                  'quoi': 'module non chargé par cette page'})
            elif not _garde_nomme(src, prim):
                probables.append({'page': etiquette, 'primitive': prim,
                                  'module': module,
                                  'quoi': 'appelée sans garde nommant la primitive'})
    return {'primitives': defs, 'certaines': certaines, 'probables': probables}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    r = analyser()
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    print('primitives définies %d · erreurs certaines %d · à risque d’ordre %d'
          % (len(r['primitives']), len(r['certaines']), len(r['probables'])))
    for x in r['certaines']:
        print('  CERTAIN  %-34s %s — %s' % (x['page'], x['primitive'], x['quoi']))
    for x in r['probables']:
        print('  RISQUE   %-34s %-18s %s (%s)'
              % (x['page'], x['primitive'], x['quoi'], x.get('module', '?')))
    return 1 if r['certaines'] else 0


if __name__ == '__main__':
    sys.exit(main())
