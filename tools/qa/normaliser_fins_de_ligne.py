# -*- coding: utf-8 -*-
"""tools/qa/normaliser_fins_de_ligne.py — remettre les fichiers texte en LF.

Pourquoi : mesuré le 2026-09-06, un outil d'édition a réécrit `terminal.py`
entièrement en CRLF. Le contenu n'avait changé que de 73 lignes, mais
`git diff` en annonçait 2883 — une revue humaine devient impossible et un
`git blame` perd sa valeur. Le dépôt est en LF (vérifié : `git show HEAD:` ne
contient aucun CRLF).

Ce script ne touche QUE les fins de ligne : il lit en binaire, remplace
`\r\n` par `\n`, et n'écrit que si le contenu change. Aucun contenu, aucun
encodage, aucun espace n'est modifié.

Il ne « corrige » pas ce qui a toujours été en CRLF : un fichier n'est retenu
que si la version INDEXÉE est en LF et la copie de travail en CRLF — donc
seulement une conversion ACCIDENTELLE. Les compétences vendues dans
`.claude/design-skills/` et les fixtures capturées chez la source sont commises
en CRLF et restent intactes, comme les formats exécutés par Windows. Les fichiers volontairement CRLF
(`.bat`, `.cmd`, `.ps1`) sont exclus.

    python tools/qa/normaliser_fins_de_ligne.py [--verifier] [chemins...]

`--verifier` ne réécrit rien et rend 1 s'il reste un fichier en CRLF : c'est la
forme utilisable en garde-fou.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#: Sous Windows, ces formats sont exécutés par un interpréteur qui exige CRLF.
EXTENSIONS_CRLF = {'.bat', '.cmd', '.ps1', '.reg'}
#: Fichiers texte du dépôt dont la fin de ligne est un contrat de revue.
EXTENSIONS_TEXTE = {'.py', '.js', '.css', '.md', '.json', '.yml', '.yaml',
                    '.txt', '.html', '.cfg', '.ini', '.toml'}


def _suivis() -> list[str]:
    out = subprocess.run(['git', 'ls-files'], cwd=RACINE, capture_output=True, text=True)
    return [l for l in out.stdout.splitlines() if l.strip()]


def index_en_lf() -> set[str]:
    """Chemins dont la version INDEXÉE est en LF, en un seul appel à Git.

    `git ls-files --eol` rend, par fichier, `i/<eol index>` et `w/<eol copie de
    travail>`. Un `i/lf` + `w/crlf` est exactement la conversion accidentelle
    qu'on veut défaire ; un `i/crlf` est un choix du dépôt, qu'on laisse.
    """
    out = subprocess.run(['git', 'ls-files', '--eol'], cwd=RACINE,
                         capture_output=True, text=True, errors='replace')
    lf = set()
    for ligne in out.stdout.splitlines():
        if not ligne.strip():
            continue
        marques, _, chemin = ligne.partition('	')
        if not chemin:
            continue
        if ' i/lf' in ' ' + marques:
            lf.add(chemin.strip())
    return lf


def candidats(chemins: list[str] | None) -> list[str]:
    liste = chemins or _suivis()
    gardes = []
    for c in liste:
        ext = os.path.splitext(c)[1].lower()
        if ext in EXTENSIONS_CRLF or ext not in EXTENSIONS_TEXTE:
            continue
        gardes.append(c)
    return gardes


def normaliser(chemins: list[str] | None, ecrire: bool) -> list[tuple[str, int]]:
    touches = []
    en_lf = index_en_lf()
    for rel in candidats(chemins):
        plein = os.path.join(RACINE, rel)
        if not os.path.isfile(plein):
            continue
        with open(plein, 'rb') as f:
            brut = f.read()
        n = brut.count(b'\r\n')
        if not n:
            continue
        if rel.replace(chr(92), '/') not in en_lf:
            continue                     # CRLF d'origine : ce n'est pas un dégât
        touches.append((rel, n))
        if ecrire:
            with open(plein, 'wb') as f:
                f.write(brut.replace(b'\r\n', b'\n'))
    return touches


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--verifier', action='store_true',
                    help='ne rien réécrire ; rendre 1 s’il reste un fichier CRLF')
    ap.add_argument('chemins', nargs='*')
    a = ap.parse_args()
    touches = normaliser(a.chemins or None, ecrire=not a.verifier)
    if not touches:
        print('fins de ligne : tout est en LF')
        return 0
    verbe = 'restent en CRLF' if a.verifier else 'remis en LF'
    print('%d fichier(s) %s :' % (len(touches), verbe))
    for rel, n in sorted(touches, key=lambda x: -x[1])[:40]:
        print('  %6d  %s' % (n, rel))
    return 1 if a.verifier else 0


if __name__ == '__main__':
    sys.exit(main())
