# -*- coding: utf-8 -*-
"""Aucun nom indéfini, aucune erreur de syntaxe dans le code servi.

Le dépôt n'embarque ni Ruff ni Pyflakes, et la suite de tests ne traverse pas
toutes les branches. Mesure du 2026-09-06 : un balayage AST des 322 modules du
paquet a trouvé un `NameError` en attente — `_POS_TTL_S`, lu dans le memo des
cotations de `positions_api.py`, défini nulle part depuis que le lot « frontière
IBKR market-data-only » avait retiré le memo voisin qui le portait.

Ce défaut est INVISIBLE en test : la fonction rend `{}` d'emblée quand IBKR est
absent, ce qui est le cas de toute la suite et de l'instance QA. Il faut IBKR
actif, un desk non vide et un SECOND appel sur le même panier pour l'atteindre —
c'est-à-dire l'usage normal de l'instance de travail, où il rendait un 500.

Ce banc rejoue le balayage à chaque exécution : un nom indéfini ne peut plus
être commis.
"""
import os
import sys

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RACINE)

from tools.qa import balayage_statique as bs  # noqa: E402


def _rapports(sous_dossier: str):
    racine = os.path.join(_RACINE, sous_dossier)
    return [bs.analyser(f) for f in sorted(bs.fichiers(racine))]


def _rel(p: str) -> str:
    return os.path.relpath(p, _RACINE).replace(os.sep, '/')


def test_le_balayage_inspecte_bien_le_code_servi():
    """Une garde qui n'inspecte rien est une garde qui ment."""
    rapports = _rapports('vertex')
    assert len(rapports) > 250, (
        'seulement %d modules inspectés : le balayage ne couvre plus le paquet'
        % len(rapports))


def test_aucune_erreur_de_syntaxe():
    fautifs = [(_rel(r['fichier']), r['syntaxe'])
               for r in _rapports('vertex') + _rapports('tools')
               if r.get('syntaxe')]
    assert not fautifs, fautifs


def test_aucun_nom_indefini_dans_le_paquet():
    fautifs = []
    for r in _rapports('vertex'):
        for nom, ligne in (r.get('noms_inconnus') or {}).items():
            fautifs.append('%s:%d  %s' % (_rel(r['fichier']), ligne, nom))
    assert not fautifs, (
        'noms utilisés sans être définis, importés ni builtins — chacun est un '
        'NameError en attente sur la branche qui l’atteint :\n  %s'
        % '\n  '.join(fautifs))


def test_aucun_nom_indefini_dans_l_outillage():
    """L'outillage de preuve doit être au moins aussi fiable que le produit."""
    fautifs = []
    for r in _rapports('tools') + _rapports('scripts'):
        for nom, ligne in (r.get('noms_inconnus') or {}).items():
            fautifs.append('%s:%d  %s' % (_rel(r['fichier']), ligne, nom))
    assert not fautifs, fautifs


def test_aucun_defaut_mutable_partage_entre_appels():
    """`def f(x=[])` partage l'objet entre tous les appels."""
    fautifs = []
    for r in _rapports('vertex'):
        for nom, ligne in (r.get('defauts_mutables') or []):
            fautifs.append('%s:%d  %s' % (_rel(r['fichier']), ligne, nom))
    assert not fautifs, fautifs


def test_le_balayage_avoue_ce_qu_il_ne_peut_pas_mesurer():
    """Un module qui manipule son espace de noms est DÉSARMÉ, pas jugé.

    Sans cet aveu, un `import *` ou un `globals()` ferait passer le balayage
    pour exhaustif alors qu'il ne l'est pas sur ce module.
    """
    desarmes = [_rel(r['fichier']) for r in _rapports('vertex') if r.get('desarme')]
    #  On n'exige pas zéro : on exige que la liste soit CONNUE et courte.
    assert len(desarmes) <= 5, desarmes
