# -*- coding: utf-8 -*-
"""tools/qa/cles_sans_producteur.py — quelles clés le code LIT-il que personne
n'écrit jamais ?

C'est le défaut le plus coûteux du produit parce qu'il est SILENCIEUX :
`detail.get('st_fund')` rend `None` sans lever, la note fondamentale part dans
les inconnues du dossier, le verdict change, et rien ne signale que la clé lue
n'existe nulle part. Trois sites jumeaux lisaient ainsi `st_fund` et
`fund_score` — deux clés sans aucun producteur dans le dépôt — pendant que la
note vivait dans `detail['sub']['fundamental']`. `st_timing` était du même
tonneau : zéro assignation, deux lectures, une note de timing promise et jamais
servie.

Cet outil croise, sur tout le dépôt — `terminal.py` COMPRIS, car c'est le plus
gros producteur de clés du produit et l'oublier revient à calomnier ses
consommateurs :

- les clés LUES : `d.get('x')`, `d['x']`, `d.get('x', défaut)`, `'x' in d` ;
- les clés ÉCRITES : `d['x'] = …`, `{'x': …}`, `dict(x=…)`, `d.setdefault('x',…)`,
  `**{'x': …}`, et les chaînes littérales des fixtures et des JSON du dépôt.

Une clé lue et jamais écrite est SUSPECTE. Elle n'est pas toujours fautive :
les charges des sources externes (yfinance, IBKR, FRED, SEC) sont écrites
ailleurs qu'ici. L'outil sépare donc ce qu'il sait de ce qu'il suppose, et
n'accuse que les clés lues dans PLUSIEURS modules — une lecture isolée d'une
charge externe est trop banale pour être un signal.

Lecture seule.

    python tools/qa/cles_sans_producteur.py [--racine vertex] [--min-lecteurs 2]
                                            [--json rapport.json]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXCLUS = {'.venv', '.git', '__pycache__', 'node_modules', '.pytest_cache',
          '.claude', '.interface-design', 'build', 'dist'}
#: Une clé plausible : identifiant en minuscules, assez longue pour ne pas être
#: un mot de passage (`id`, `k`, `v`) et sans espace.
_CLE = re.compile(r'^[a-z][a-z0-9_]{3,40}$')


class _Lecture(ast.NodeVisitor):
    def __init__(self) -> None:
        self.lues: dict[str, int] = {}
        self.ecrites: set[str] = set()

    def _lit(self, cle: str, ligne: int) -> None:
        if _CLE.match(cle):
            self.lues.setdefault(cle, ligne)

    def _ecrit(self, cle: str) -> None:
        if isinstance(cle, str):
            self.ecrites.add(cle)

    def visit_Call(self, n: ast.Call) -> None:
        f = n.func
        if isinstance(f, ast.Attribute) and n.args:
            a0 = n.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                if f.attr == 'get':
                    self._lit(a0.value, n.lineno)
                elif f.attr in ('setdefault', 'pop'):
                    #  `setdefault` écrit ET lit ; `pop` lit. On les compte
                    #  comme des écritures : elles prouvent que la clé vit ici.
                    self._ecrit(a0.value)
            if f.attr == 'update':
                for a in n.args:
                    if isinstance(a, ast.Dict):
                        self._cles_du_dict(a, ecrit=True)
        for kw in n.keywords:
            if kw.arg:
                self._ecrit(kw.arg)
        self.generic_visit(n)

    def visit_Subscript(self, n: ast.Subscript) -> None:
        s = n.slice
        if isinstance(s, ast.Constant) and isinstance(s.value, str):
            if isinstance(n.ctx, ast.Store):
                self._ecrit(s.value)
            else:
                self._lit(s.value, n.lineno)
        self.generic_visit(n)

    def visit_Compare(self, n: ast.Compare) -> None:
        #  `'x' in d` est une lecture de la clé `x`.
        for op, cmp in zip(n.ops, n.comparators):
            if isinstance(op, (ast.In, ast.NotIn)) and isinstance(n.left, ast.Constant) \
                    and isinstance(n.left.value, str):
                self._lit(n.left.value, n.lineno)
        self.generic_visit(n)

    def _cles_du_dict(self, n: ast.Dict, ecrit: bool) -> None:
        for k in n.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                if ecrit:
                    self._ecrit(k.value)

    def visit_Dict(self, n: ast.Dict) -> None:
        self._cles_du_dict(n, ecrit=True)
        self.generic_visit(n)


def fichiers(racine: str, ext=('.py',)):
    for dossier, sous, noms in os.walk(racine):
        sous[:] = [d for d in sous if d not in EXCLUS]
        for n in noms:
            if n.endswith(ext):
                yield os.path.join(dossier, n)


#: Modules de la RACINE du dépôt. `terminal.py` est le plus gros producteur de
#: clés du produit (il construit les lignes de tableau du scan) : l'oublier
#: faisait accuser à tort cinq clés de `opportunities/funnel.py` — mesuré, elles
#: sont bien posées à terminal.py:669-675. Un détecteur qui ignore le principal
#: producteur ne détecte pas, il calomnie.
MODULES_RACINE = ('terminal.py',)


def analyser(racines: list[str]) -> dict:
    lues: dict[str, list[tuple[str, int]]] = {}
    ecrites: set[str] = set()
    a_lire = []
    for racine in racines:
        a_lire.extend(fichiers(racine))
    for nom in MODULES_RACINE:
        chemin = os.path.join(RACINE, nom)
        if os.path.isfile(chemin):
            a_lire.append(chemin)
    for f in a_lire:
        try:
            with open(f, encoding='utf-8') as h:
                arbre = ast.parse(h.read(), filename=f)
        except (SyntaxError, UnicodeDecodeError):
            continue
        v = _Lecture()
        v.visit(arbre)
        ecrites |= v.ecrites
        rel = os.path.relpath(f, RACINE).replace(os.sep, '/')
        for cle, ligne in v.lues.items():
            lues.setdefault(cle, []).append((rel, ligne))
    return {'lues': lues, 'ecrites': ecrites}


def cles_json_du_depot(dossiers: list[str]) -> set[str]:
    """Les clés présentes dans les JSON du dépôt (fixtures, caches, profils).

    Une clé peut n'être écrite par aucun code Python et exister quand même :
    elle vient d'un fichier de données. L'ignorer produirait des accusations
    fausses par dizaines.
    """
    out: set[str] = set()
    for d in dossiers:
        if not os.path.isdir(d):
            continue
        for f in fichiers(d, ext=('.json',)):
            try:
                with open(f, encoding='utf-8') as h:
                    charge = json.load(h)
            except Exception:                          # noqa: BLE001
                continue
            pile = [charge]
            while pile:
                x = pile.pop()
                if isinstance(x, dict):
                    out |= {k for k in x if isinstance(k, str)}
                    pile.extend(x.values())
                elif isinstance(x, list):
                    pile.extend(x[:200])
    return out


def suspectes(r: dict, connues: set[str], min_lecteurs: int) -> list[dict]:
    out = []
    for cle, sites in sorted(r['lues'].items()):
        if cle in r['ecrites'] or cle in connues:
            continue
        modules = sorted({m for m, _ in sites})
        if len(modules) < min_lecteurs:
            continue
        out.append({'cle': cle, 'lecteurs': len(sites), 'modules': modules[:6],
                    'sites': ['%s:%d' % (m, l) for m, l in sites[:6]]})
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:                                  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--racine', action='append', default=None)
    ap.add_argument('--min-lecteurs', type=int, default=2)
    ap.add_argument('--json', default=None)
    a = ap.parse_args()

    racines = [os.path.join(RACINE, x) for x in (a.racine or ['vertex', 'tests', 'tools'])]
    r = analyser(racines)
    connues = cles_json_du_depot([RACINE])
    s = suspectes(r, connues, a.min_lecteurs)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'suspectes': s, 'ecrites': len(r['ecrites']),
                       'lues': len(r['lues'])}, f, ensure_ascii=False, indent=1)
    print('clés lues %d · clés écrites %d · clés connues des JSON %d · SUSPECTES %d'
          % (len(r['lues']), len(r['ecrites']), len(connues), len(s)))
    for x in s:
        print('  %-34s %d lecture(s) dans %d module(s) : %s'
              % (x['cle'], x['lecteurs'], len(x['modules']), ', '.join(x['sites'][:3])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
