# -*- coding: utf-8 -*-
"""tools/qa/modules_non_atteints.py — quels modules ne sont atteints par AUCUN
chemin de production ?

Mesuré le 2026-09-06 : `vertex/scanner/stages.py` porte un pipeline de notation
en huit étages, un commentaire « ordre OBLIGATOIRE des étages (§22) — testé » et
une suite de tests verte. Il n'est importé par aucun module de production. Le
scanner réel ne note pas les candidats de cette façon, et rien à la lecture ne
le disait — un test vert achève même de donner l'impression du contraire.

C'est la forme la plus coûteuse d'absence : celle qu'on ne cherche pas, parce
qu'on croit la voir tourner. Une capacité sans exécuteur réel s'appelle
NON_IMPLÉMENTÉ (invariant 8) ; encore faut-il savoir laquelle.

Méthode : on part des points d'entrée RÉELS du produit (`terminal.py`,
`vertex/runtime.py`, `vertex/__main__.py`, `vertex/app/factory.py`) et on suit
les imports de proche en proche. Ce que la fermeture transitive n'atteint pas
n'est exécuté par aucune requête, aucun worker et aucun job.

Trois nuances honnêtes, sans quoi l'outil accuserait à tort :

- un module chargé depuis un littéral de chaîne (le registre de blueprints de
  `app/factory.py`) compte comme importé ;

- un module atteint par un import PARESSEUX (dans une fonction) compte comme
  atteint : c'est le style dominant du dépôt pour éviter les cycles ;
- un module atteint uniquement par les TESTS est signalé à part. Il n'est pas
  mort — il est SPÉCIFIÉ mais pas branché, ce qui appelle une étiquette, pas
  une suppression.

Lecture seule ; aucune suppression n'est proposée, la doctrine l'interdit sans
preuve d'absence de consommateur, de migration et de rollback.

    python tools/qa/modules_non_atteints.py [--json rapport.json]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXCLUS = {'.venv', '.git', '__pycache__', 'node_modules', '.pytest_cache',
          '.claude', '.interface-design', 'build', 'dist'}
#: Ce que le produit exécute vraiment quand on le lance.
ENTREES = ('terminal.py', 'vertex/runtime.py', 'vertex/__main__.py',
           'vertex/app/factory.py')


def _modules_du_paquet() -> dict[str, str]:
    """{nom pointé: chemin} pour chaque module de `vertex`, plus la racine."""
    out: dict[str, str] = {}
    base = os.path.join(RACINE, 'vertex')
    for dossier, sous, noms in os.walk(base):
        sous[:] = [d for d in sous if d not in EXCLUS]
        for n in noms:
            if not n.endswith('.py'):
                continue
            chemin = os.path.join(dossier, n)
            rel = os.path.relpath(chemin, RACINE).replace(os.sep, '/')
            pointe = rel[:-3].replace('/', '.')
            if pointe.endswith('.__init__'):
                pointe = pointe[:-len('.__init__')]
            out[pointe] = rel
    for n in ('terminal.py',):
        c = os.path.join(RACINE, n)
        if os.path.isfile(c):
            out[n[:-3]] = n
    return out


def _paquet_de(chemin: str) -> str:
    """Nom pointé du PAQUET contenant ce fichier, pour résoudre le relatif."""
    pointe = chemin[:-3].replace('/', '.')
    if pointe.endswith('.__init__'):
        return pointe[:-len('.__init__')]
    return pointe.rsplit('.', 1)[0] if '.' in pointe else ''


def _imports(chemin: str) -> set[str]:
    """Modules `vertex.*` (ou `terminal`) importés, imports paresseux compris.

    Les imports RELATIFS (`from .response_validator import …`) sont résolus
    contre le paquet du fichier : sans cela, tout `vertex/ai/` paraissait mort
    alors que `investment_agent` en importe la moitié de cette façon."""
    try:
        with open(os.path.join(RACINE, chemin), encoding='utf-8') as f:
            arbre = ast.parse(f.read())
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        return set()
    out: set[str] = set()
    for n in ast.walk(arbre):
        #  IMPORT PAR CHAÎNE. `vertex/app/factory.py` enregistre ses blueprints
        #  depuis une liste de littéraux (`('vertex.app.routes.scan_api', 'bp')`)
        #  puis les charge dynamiquement. Ne suivre que les `import` de l'AST
        #  faisait passer VINGT-DEUX modules de routes pour non branchés —
        #  c'est-à-dire accuser la moitié de la surface HTTP du produit.
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            v = n.value
            if v.startswith(('vertex.', 'terminal.')) or v in ('terminal',):
                out.add(v)
            continue
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith(('vertex', 'terminal')):
                    out.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ''
            niveau = getattr(n, 'level', 0) or 0
            if niveau:
                base = _paquet_de(chemin)
                for _ in range(niveau - 1):
                    base = base.rsplit('.', 1)[0] if '.' in base else ''
                mod = '%s.%s' % (base, mod) if mod else base
            if not mod.startswith(('vertex', 'terminal')):
                continue
            out.add(mod)
            #  `from vertex.scanner import daily` : `daily` est un module.
            for a in n.names:
                out.add('%s.%s' % (mod, a.name))
    return out


def fermeture(depart: list[str], modules: dict[str, str]) -> set[str]:
    """Modules atteints depuis `depart`, en suivant les imports."""
    vus: set[str] = set()
    pile = list(depart)
    while pile:
        m = pile.pop()
        if m in vus or m not in modules:
            continue
        vus.add(m)
        for suivant in _imports(modules[m]):
            if suivant in modules and suivant not in vus:
                pile.append(suivant)
            #  `vertex.a.b` importé alors que seul `vertex.a` existe : le
            #  paquet parent est atteint, et son `__init__` peut réexporter.
            parent = suivant.rsplit('.', 1)[0]
            if parent in modules and parent not in vus:
                pile.append(parent)
    return vus


def _depuis_les_tests(modules: dict[str, str]) -> set[str]:
    dossier = os.path.join(RACINE, 'tests')
    vus: set[str] = set()
    if not os.path.isdir(dossier):
        return vus
    for n in sorted(os.listdir(dossier)):
        if n.endswith('.py'):
            vus |= {m for m in _imports('tests/' + n) if m in modules}
    return vus


def analyser() -> dict:
    modules = _modules_du_paquet()
    depart = []
    for e in ENTREES:
        pointe = e[:-3].replace('/', '.')
        if pointe.endswith('.__init__'):
            pointe = pointe[:-len('.__init__')]
        if pointe in modules:
            depart.append(pointe)
    atteints = fermeture(depart, modules)
    #  Une page ou une route peut n'être atteinte qu'à travers son paquet :
    #  la fermeture le couvre déjà (le parent est empilé).
    par_les_tests = _depuis_les_tests(modules)
    non_atteints = sorted(set(modules) - atteints)
    return {
        'entrees': depart,
        'modules': len(modules),
        'atteints': len(atteints),
        'specifies_non_branches': [m for m in non_atteints if m in par_les_tests],
        'jamais_atteints': [m for m in non_atteints if m not in par_les_tests],
        'chemins': {m: modules[m] for m in non_atteints},
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:                                  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    r = analyser()
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    print('modules %d · atteints depuis les entrées %d · spécifiés non branchés %d · '
          'jamais atteints %d'
          % (r['modules'], r['atteints'], len(r['specifies_non_branches']),
             len(r['jamais_atteints'])))
    for m in r['specifies_non_branches']:
        print('  SPÉCIFIÉ   %-46s (des tests l’exercent, aucun chemin de production)'
              % r['chemins'][m])
    for m in r['jamais_atteints']:
        print('  ORPHELIN   %s' % r['chemins'][m])
    return 0


if __name__ == '__main__':
    sys.exit(main())
