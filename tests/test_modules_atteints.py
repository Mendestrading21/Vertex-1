# -*- coding: utf-8 -*-
"""Tout module du paquet est atteint par un chemin de production, ou étiqueté.

Mesure du 2026-09-06, fermeture transitive des imports depuis les points
d'entrée réels : 319 modules sur 323 sont atteints. Les quatre autres ne le
sont que par leurs propres bancs — ils sont SPÉCIFIÉS, pas branchés :

- `vertex/scanner/stages.py` : un pipeline de notation en huit étages que le
  scanner réel n'exécute pas ;
- `vertex/ai/tool_registry.py` : la liste blanche des outils Claude, alors
  qu'aucun outil local n'est exposé au modèle ;
- `vertex/product.py` : des constantes de contrat, consultées par les bancs et
  la documentation — c'est leur rôle ;
- `vertex/data_sources/ibkr_replay.py` : un banc de rejeu.

Les deux premiers portent désormais `ETAT = NON_IMPLÉMENTÉ` et `MANQUE`. C'est
la forme la plus coûteuse d'absence : celle qu'on ne cherche pas, parce qu'un
test vert donne l'impression qu'elle tourne.

Ce banc tient la liste à jour dans les DEUX sens : un module qui sort de la
production sans étiquette le fait tomber, et un module étiqueté qui devient
atteint aussi.
"""
import os
import sys

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RACINE)

from tools.qa import modules_non_atteints as mna  # noqa: E402

#: Les modules dont on SAIT qu'ils ne sont pas branchés, et pourquoi.
_ADMIS = {
    'vertex/scanner/stages.py': 'étiqueté NON_IMPLÉMENTÉ',
    'vertex/ai/tool_registry.py': 'étiqueté NON_IMPLÉMENTÉ',
    'vertex/product.py': 'constantes de contrat, consultées par bancs et docs',
    'vertex/data_sources/ibkr_replay.py': 'banc de rejeu',
}
#: Ceux qui doivent, en plus, porter l'étiquette lisible par un programme.
_ETIQUETES = ('vertex.scanner.stages', 'vertex.ai.tool_registry')


def _rapport():
    return mna.analyser()


def test_la_fermeture_atteint_bien_l_essentiel_du_paquet():
    """Une garde qui n'atteint rien accuserait tout : on vérifie l'inverse."""
    r = _rapport()
    assert r['modules'] > 300, r['modules']
    assert r['atteints'] / r['modules'] > 0.95, (r['atteints'], r['modules'])


def test_aucun_module_orphelin():
    """Ni production, ni tests : personne ne l'exécute jamais."""
    r = _rapport()
    orphelins = [r['chemins'][m] for m in r['jamais_atteints']]
    assert not orphelins, orphelins


def test_les_modules_non_branches_sont_exactement_ceux_qu_on_connait():
    r = _rapport()
    trouves = {r['chemins'][m] for m in r['specifies_non_branches']}
    inattendus = sorted(trouves - set(_ADMIS))
    assert not inattendus, (
        '%s ne sont plus atteints par la production : soit un import a disparu, '
        'soit une capacité vient d’être débranchée en silence' % inattendus)
    disparus = sorted(set(_ADMIS) - trouves)
    assert not disparus, (
        '%s sont désormais atteints par la production : retirer leur étiquette '
        'NON_IMPLÉMENTÉ et vérifier que leurs entrées sont bien produites'
        % disparus)


def test_les_capacites_non_branchees_portent_une_etiquette_lisible():
    import importlib
    for nom in _ETIQUETES:
        mod = importlib.import_module(nom)
        assert getattr(mod, 'ETAT', None) == 'NON_IMPLÉMENTÉ', nom
        manque = getattr(mod, 'MANQUE', ())
        assert manque and all(isinstance(x, str) and len(x) > 20 for x in manque), (nom, manque)


def test_l_outil_resout_les_imports_indirects():
    """Contre-épreuve : sans cela, la moitié du produit paraîtrait morte.

    Deux formes ont fait accuser à tort, et doivent rester couvertes : le
    registre de blueprints par littéraux de chaîne (22 modules de routes) et
    les imports relatifs (`from .response_validator import …`, tout `vertex/ai`).
    """
    r = _rapport()
    chemins_non_atteints = set(r['chemins'].values())
    for temoin in ('vertex/app/routes/system.py', 'vertex/ai/response_validator.py',
                   'vertex/ai/investment_agent.py'):
        assert temoin not in chemins_non_atteints, (
            '%s est compté non atteint : la résolution des imports indirects '
            'a régressé' % temoin)
