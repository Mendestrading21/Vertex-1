# -*- coding: utf-8 -*-
"""`vertex.scanner.stages` est ÉTIQUETÉ non branché tant qu'il ne l'est pas.

Mesure du 2026-09-06 : `STAGE_ORDER` et les huit évaluateurs ne sont référencés
que par `tests/test_scanner_institutional.py`. Le paquet `vertex.scanner` n'est
importé, en production, qu'à travers `daily` et `weekly`. Le scanner réel ne
note donc pas les candidats de cette façon — alors que le module s'annonçait
« ordre OBLIGATOIRE des étages (§22) — testé », et qu'un test vert achevait de
donner l'impression d'une capacité vivante.

Une capacité sans exécuteur réel s'appelle NON_IMPLÉMENTÉ (invariant 8). Ce banc
tient l'étiquette à jour dans les DEUX sens : si un appelant de production
apparaît, il tombe, et l'étiquette doit être retirée.
"""
import ast
import os

from vertex.scanner import stages

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _modules_de_production():
    for dossier, sous, noms in os.walk(os.path.join(_RACINE, 'vertex')):
        sous[:] = [d for d in sous if d != '__pycache__']
        for nom in noms:
            if nom.endswith('.py'):
                yield os.path.join(dossier, nom)
    for nom in ('terminal.py',):
        chemin = os.path.join(_RACINE, nom)
        if os.path.isfile(chemin):
            yield chemin


def _importe_les_etages(chemin: str) -> bool:
    if os.path.abspath(chemin).endswith(os.path.join('scanner', 'stages.py')):
        return False
    with open(chemin, encoding='utf-8') as f:
        try:
            arbre = ast.parse(f.read())
        except SyntaxError:
            return False
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom) and (n.module or '').startswith('vertex.scanner'):
            if any(a.name == 'stages' for a in n.names):
                return True
        if isinstance(n, ast.Import):
            if any(a.name == 'vertex.scanner.stages' for a in n.names):
                return True
    return False


def test_l_etiquette_existe_et_dit_ce_qui_manque():
    assert stages.ETAT == 'NON_IMPLÉMENTÉ', stages.ETAT
    assert len(stages.MANQUE) >= 2
    joint = ' '.join(stages.MANQUE)
    assert 'appelant de production' in joint
    assert 'producteur' in joint


def test_aucun_appelant_de_production_n_execute_les_etages():
    appelants = [os.path.relpath(c, _RACINE).replace(os.sep, '/')
                 for c in _modules_de_production() if _importe_les_etages(c)]
    assert not appelants, (
        '%s importe désormais les étages : la capacité est branchée, il faut '
        'retirer l’étiquette NON_IMPLÉMENTÉ et vérifier que des producteurs '
        'remplissent bien les blocs attendus' % appelants)


def test_le_module_reste_COHERENT_et_testable():
    """Étiqueter n'est pas abandonner : le contrat doit rester juste."""
    assert len(stages.STAGE_ORDER) == 8
    vide = {}
    for nom, etage in stages.STAGE_ORDER:
        r = etage(vide)
        assert set(r) == {'passed', 'score', 'reasons', 'missing'}, (nom, r)
        assert r['score'] is None or isinstance(r['score'], float), (nom, r)
        #  Sans donnée, un étage ne fabrique JAMAIS un score.
        if r['missing']:
            assert r['score'] is None, (nom, r)
