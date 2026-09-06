# -*- coding: utf-8 -*-
"""Le code Vertex reste en LF : un diff doit rester lisible par un humain.

Mesure du 2026-09-06 : un outil d'édition a réécrit `terminal.py` entièrement
en CRLF. Le changement réel valait 73 lignes ; `git diff` en annonçait 2883.
Une revue devient impossible, `git blame` perd sa valeur, et un correctif
minime prend l'apparence d'une réécriture — exactement ce que le contrat de lot
interdit (« implémenter le changement minimal cohérent »).

Ce test ne juge pas la copie de travail (un éditeur local peut faire ce qu'il
veut) : il juge ce qui est COMMIS, c'est-à-dire ce qu'un relecteur verra. Les
formats exécutés par Windows et les compétences vendues dans
`.claude/design-skills/` sont commis en CRLF et restent hors périmètre.

Réparation : `python tools/qa/normaliser_fins_de_ligne.py`.
"""
import os
import subprocess

import pytest

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Le périmètre relu à la main : le code, les tests et l'outillage de Vertex.
_PERIMETRE = ('vertex/', 'tests/', 'tools/', 'scripts/')
_FICHIERS = ('terminal.py',)
#: Exécutés par un interpréteur Windows qui exige CRLF.
_EXTENSIONS_CRLF = {'.bat', '.cmd', '.ps1', '.reg'}
#: Les fixtures sont des OCTETS CAPTURÉS chez la source (mesuré : le communiqué
#: ad hoc de la BNS arrive en CRLF). Les réécrire falsifierait la preuve que le
#: parseur sait lire ce que la source envoie vraiment.
_HORS_PERIMETRE = ('tests/fixtures/',)


def _eol_index() -> list[tuple[str, str]]:
    """(chemin, fin de ligne indexée) pour chaque fichier suivi du périmètre."""
    out = subprocess.run(['git', 'ls-files', '--eol'], cwd=_RACINE,
                         capture_output=True, text=True, errors='replace')
    if out.returncode != 0:
        pytest.skip('dépôt Git indisponible : mesure impossible, jamais supposée')
    lignes = []
    for ligne in out.stdout.splitlines():
        marques, _, chemin = ligne.partition('\t')
        chemin = chemin.strip().replace(chr(92), '/')
        if not chemin:
            continue
        if not (chemin.startswith(_PERIMETRE) or chemin in _FICHIERS):
            continue
        if chemin.startswith(_HORS_PERIMETRE):
            continue
        if os.path.splitext(chemin)[1].lower() in _EXTENSIONS_CRLF:
            continue
        jetons = marques.split()
        index = next((j[2:] for j in jetons if j.startswith('i/')), '')
        lignes.append((chemin, index))
    return lignes


def test_le_perimetre_est_bien_mesure():
    """Une garde qui n'inspecte rien est une garde qui ment."""
    mesures = _eol_index()
    assert len(mesures) > 200, (
        'seulement %d fichiers inspectés : le périmètre ne décrit plus le dépôt'
        % len(mesures))
    assert any(c == 'terminal.py' for c, _ in mesures)


def test_aucun_fichier_source_nest_commis_en_crlf():
    fautifs = [c for c, eol in _eol_index() if eol == 'crlf']
    assert not fautifs, (
        '%d fichier(s) commis en CRLF — un diff de revue devient illisible :\n  %s\n'
        'réparer avec : python tools/qa/normaliser_fins_de_ligne.py'
        % (len(fautifs), '\n  '.join(sorted(fautifs)[:20])))


def test_l_outil_de_reparation_existe_et_est_documente():
    """La garde nomme un remède : il doit exister et dire pourquoi il agit."""
    outil = os.path.join(_RACINE, 'tools', 'qa', 'normaliser_fins_de_ligne.py')
    assert os.path.isfile(outil), 'le remède annoncé par l’échec n’existe pas'
    with open(outil, encoding='utf-8') as f:
        src = f.read()
    assert '--verifier' in src, 'l’outil doit offrir un mode de contrôle sans écriture'
    assert 'design-skills' in src, (
        'l’outil doit dire pourquoi il épargne les fichiers commis en CRLF')
