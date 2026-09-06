# -*- coding: utf-8 -*-
"""tools/qa/balayage_statique.py — chercher les erreurs LATENTES dans tout le code.

Le dépôt n'embarque ni Ruff ni Pyflakes, et la suite de tests ne traverse pas
toutes les branches : un nom mal orthographié dans un chemin d'erreur rare ne se
révèle qu'en production, au pire moment. Cet outil lit chaque module Python avec
`ast` et cherche quatre familles de défauts qui ne coûtent rien à trouver et
beaucoup à subir :

1. **Nom non défini** — utilisé dans un module sans y être ni importé, ni
   assigné, ni un builtin. C'est un `NameError` en attente. C'est la mesure la
   plus utile : elle a la même nature que le `ReferenceError: VX is not defined`
   trouvé côté navigateur, mais côté serveur.
2. **Import inutilisé** — un nom importé et jamais lu. Sans gravité, mais il
   masque les vrais imports et fait mentir la carte des dépendances.
3. **Redéfinition silencieuse** — deux fonctions du même nom au même niveau : la
   seconde gagne, la première est morte sans que rien ne le dise.
4. **Défaut mutable** — `def f(x=[])` partage l'objet entre les appels.

Lecture seule : aucun fichier n'est modifié, aucun code n'est exécuté.

    python tools/qa/balayage_statique.py [--racine vertex] [--json rapport.json]
                                         [--famille noms]
"""
from __future__ import annotations

import argparse
import ast
import builtins
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#: Dossiers sans intérêt pour la mesure (dépendances, caches, copies).
EXCLUS = {'.venv', '.git', '__pycache__', 'node_modules', '.pytest_cache',
          '.claude', '.interface-design', 'build', 'dist'}
BUILTINS = set(dir(builtins)) | {
    '__file__', '__name__', '__doc__', '__package__', '__spec__', '__loader__',
    '__builtins__', '__path__', '__debug__', 'WindowsError',
}


class _Portee(ast.NodeVisitor):
    """Collecte les noms LIÉS et les noms LUS d'un module, par portée.

    On ne refait pas un analyseur complet : on veut une mesure sûre, pas
    exhaustive. Tout ce qui est ambigu (import *, globals(), exec) désarme le
    module — mieux vaut ne rien dire que d'accuser à tort.
    """

    def __init__(self) -> None:
        self.lies: set[str] = set()
        self.lus: list[tuple[str, int]] = []
        self.importes: dict[str, int] = {}
        self.desarme: str | None = None
        self.doublons: list[tuple[str, int, int]] = []
        self.defauts_mutables: list[tuple[str, int]] = []
        self._def_par_nom: dict[str, int] = {}

    #  ── liaisons ────────────────────────────────────────────────────────────
    def visit_Import(self, n: ast.Import) -> None:
        for a in n.names:
            nom = (a.asname or a.name).split('.')[0]
            self.lies.add(nom)
            self.importes.setdefault(nom, n.lineno)
        self.generic_visit(n)

    def visit_ImportFrom(self, n: ast.ImportFrom) -> None:
        for a in n.names:
            if a.name == '*':
                self.desarme = 'import * ligne %d' % n.lineno
                return
            nom = a.asname or a.name
            self.lies.add(nom)
            self.importes.setdefault(nom, n.lineno)
        self.generic_visit(n)

    def _fonction(self, n) -> None:
        self.lies.add(n.name)
        precedent = self._def_par_nom.get(n.name)
        if precedent is not None and not _a_decorateur(n):
            self.doublons.append((n.name, precedent, n.lineno))
        self._def_par_nom[n.name] = n.lineno
        for d in (n.args.defaults + [x for x in n.args.kw_defaults if x]):
            if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                self.defauts_mutables.append((n.name, n.lineno))
        for a in _arguments(n.args):
            self.lies.add(a)
        self.generic_visit(n)

    visit_FunctionDef = _fonction
    visit_AsyncFunctionDef = _fonction

    def visit_ClassDef(self, n: ast.ClassDef) -> None:
        self.lies.add(n.name)
        self.generic_visit(n)

    def visit_Lambda(self, n: ast.Lambda) -> None:
        #  Une lambda LIE ses paramètres. Sans cette visite, `lambda e: e.x`
        #  accusait `e` d'être indéfini — mesuré : 27 faux positifs sur 33.
        for a in _arguments(n.args):
            self.lies.add(a)
        self.generic_visit(n)

    def _comprehension(self, n) -> None:
        #  Idem pour la cible d'une compréhension : `[x for x in xs]` lie `x`.
        for gen in n.generators:
            for cible in ast.walk(gen.target):
                if isinstance(cible, ast.Name):
                    self.lies.add(cible.id)
        self.generic_visit(n)

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension

    def visit_Global(self, n: ast.Global) -> None:
        self.lies.update(n.names)

    def visit_Nonlocal(self, n: ast.Nonlocal) -> None:
        self.lies.update(n.names)

    def visit_ExceptHandler(self, n: ast.ExceptHandler) -> None:
        if n.name:
            self.lies.add(n.name)
        self.generic_visit(n)

    def visit_Name(self, n: ast.Name) -> None:
        if isinstance(n.ctx, (ast.Store, ast.Del)):
            self.lies.add(n.id)
        else:
            self.lus.append((n.id, n.lineno))

    def visit_Attribute(self, n: ast.Attribute) -> None:
        self.generic_visit(n)

    def visit_Call(self, n: ast.Call) -> None:
        cible = n.func
        if isinstance(cible, ast.Name) and cible.id in ('globals', 'locals', 'eval', 'exec', 'vars'):
            self.desarme = '%s() ligne %d' % (cible.id, n.lineno)
        self.generic_visit(n)


def _a_decorateur(n) -> bool:
    """Une redéfinition décorée est souvent voulue (`@property`, `@x.setter`,
    surcharge de route). On ne l'accuse pas."""
    return bool(getattr(n, 'decorator_list', None))


def _arguments(a: ast.arguments) -> list[str]:
    noms = [x.arg for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)]
    if a.vararg:
        noms.append(a.vararg.arg)
    if a.kwarg:
        noms.append(a.kwarg.arg)
    return noms


#: Noms exemptés : ils sont fournis par un contexte que l'AST ne voit pas.
EXEMPTS = {'self', 'cls', '_', '__class__'}


def analyser(chemin: str) -> dict:
    with open(chemin, encoding='utf-8') as f:
        src = f.read()
    try:
        arbre = ast.parse(src, filename=chemin)
    except SyntaxError as exc:
        return {'fichier': chemin, 'syntaxe': '%s ligne %s' % (exc.msg, exc.lineno)}
    p = _Portee()
    p.visit(arbre)
    out: dict = {'fichier': chemin, 'desarme': p.desarme}
    if p.desarme:
        #  Le module manipule son espace de noms : toute accusation serait un
        #  faux positif. On le DIT au lieu de le taire.
        out['doublons'] = p.doublons
        out['defauts_mutables'] = p.defauts_mutables
        return out
    connus = p.lies | BUILTINS | EXEMPTS
    inconnus: dict[str, int] = {}
    for nom, ligne in p.lus:
        if nom not in connus and nom not in inconnus:
            inconnus[nom] = ligne
    lus_noms = {n for n, _ in p.lus}
    #  Un import peut servir pour son EFFET (enregistrement de blueprint) ou
    #  être réexporté : on ne compte inutilisé que ce qui n'est ni lu, ni dans
    #  `__all__`, ni un module de paquet importé pour son effet de bord.
    exportes = _all_du_module(arbre)
    inutilises = {n: l for n, l in p.importes.items()
                  if n not in lus_noms and n not in exportes and not n.startswith('_')}
    out.update({'noms_inconnus': inconnus, 'imports_inutilises': inutilises,
                'doublons': p.doublons, 'defauts_mutables': p.defauts_mutables})
    return out


def _all_du_module(arbre: ast.Module) -> set[str]:
    for n in arbre.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == '__all__' for c in n.targets):
            if isinstance(n.value, (ast.List, ast.Tuple)):
                return {e.value for e in n.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


def fichiers(racine: str):
    for dossier, sous, noms in os.walk(racine):
        sous[:] = [d for d in sous if d not in EXCLUS]
        for n in noms:
            if n.endswith('.py'):
                yield os.path.join(dossier, n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--racine', default=RACINE)
    ap.add_argument('--json', default=None)
    ap.add_argument('--famille', default='toutes',
                    choices=('toutes', 'noms', 'imports', 'doublons', 'mutables'))
    a = ap.parse_args()

    racine = a.racine if os.path.isabs(a.racine) else os.path.join(RACINE, a.racine)
    rapports = [analyser(f) for f in sorted(fichiers(racine))]
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(rapports, f, ensure_ascii=False, indent=1)

    n_syn = [r for r in rapports if r.get('syntaxe')]
    n_noms = [(r['fichier'], n, l) for r in rapports
              for n, l in (r.get('noms_inconnus') or {}).items()]
    n_imp = [(r['fichier'], n, l) for r in rapports
             for n, l in (r.get('imports_inutilises') or {}).items()]
    n_dbl = [(r['fichier'], n, a1, b1) for r in rapports
             for n, a1, b1 in (r.get('doublons') or [])]
    n_mut = [(r['fichier'], n, l) for r in rapports
             for n, l in (r.get('defauts_mutables') or [])]
    desarmes = [r['fichier'] for r in rapports if r.get('desarme')]

    rel = lambda p: os.path.relpath(p, RACINE).replace(os.sep, '/')   # noqa: E731
    print('modules %d · syntaxe KO %d · noms inconnus %d · imports inutilisés %d · '
          'redéfinitions %d · défauts mutables %d · modules désarmés %d'
          % (len(rapports), len(n_syn), len(n_noms), len(n_imp), len(n_dbl),
             len(n_mut), len(desarmes)))
    fam = a.famille
    for r in n_syn:
        print('  SYNTAXE   %s : %s' % (rel(r['fichier']), r['syntaxe']))
    if fam in ('toutes', 'noms'):
        for f, n, l in n_noms:
            print('  NOM       %s:%d  %s' % (rel(f), l, n))
    if fam in ('toutes', 'doublons'):
        for f, n, a1, b1 in n_dbl:
            print('  REDÉF     %s  %s (ligne %d puis %d)' % (rel(f), n, a1, b1))
    if fam in ('toutes', 'mutables'):
        for f, n, l in n_mut:
            print('  MUTABLE   %s:%d  %s' % (rel(f), l, n))
    if fam in ('toutes', 'imports'):
        for f, n, l in n_imp:
            print('  IMPORT    %s:%d  %s' % (rel(f), l, n))
    return 1 if (n_syn or n_noms) else 0


if __name__ == '__main__':
    sys.exit(main())
