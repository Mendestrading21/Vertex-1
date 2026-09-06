# -*- coding: utf-8 -*-
"""tools/qa/run_qa_instance.py — instance de VÉRIFICATION visuelle de Vertex.

Pourquoi : l'instance de travail (port 5002) tourne avec IBKR en direct et un
code d'accès. Pour capturer les pages et contrôler la console sans saisir ce
code ni ouvrir une seconde connexion TWS (identifiants clients partagés), on
lance une COPIE du dépôt, sans IBKR, sans démo et sans verrou, en boucle
locale uniquement.

Ce que fait ce script :
1. miroir du dépôt dans ``<répertoire temporaire>/vertex-qa`` (sans .git, .venv,
   .env, .vertex_secret, __pycache__) — les caches JSON du dépôt sont copiés
   tels quels : ce sont des instantanés, jamais réécrits dans le dépôt source ;
2. le desk DÉCLARÉ n'est jamais copié : l'instance sert un portefeuille vide.
   C'est à la fois une protection (le dépôt est public, et une campagne d'audit
   recopie ce qu'elle mesure) et la bonne condition de mesure — une instance de
   vérification doit montrer les états d'absence, pas les positions de son
   auteur ;
3. environnement : ``NO_IBKR=1`` (aucune connexion courtier), ``DEMO=0`` (aucun
   chiffre fictif : données différées yfinance, affichées comme telles),
   ``VERTEX_CODE=`` (sans verrou, donc écoute 127.0.0.1 seulement) ;
4. démarrage des workers puis du serveur Flask sur ``127.0.0.1:5003``.

Invariants : ``READONLY``/``ANALYSIS_ONLY`` inchangés ; aucune donnée de compte ;
aucune écriture dans le dépôt source. Usage :

    .venv/Scripts/python.exe tools/qa/run_qa_instance.py [--port 5003]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXCLUS_DOSSIERS = {'.git', '.venv', '__pycache__', 'node_modules', '.claude',
                   '.interface-design', '.pytest_cache'}
#: DONNÉES PERSONNELLES — jamais copiées dans le miroir.
#:
#: Mesuré le 2026-09-06 : la copie n'excluait que les secrets, pas le
#: PATRIMOINE. `desk_data.json` était donc miroité, l'instance de vérification
#: servait le portefeuille RÉEL de l'utilisateur, et les campagnes d'audit ont
#: recopié ses montants dans des bancs et des documents d'un dépôt PUBLIC —
#: composition, capital engagé par ligne, liquidités, prix d'entrée suivis.
#:
#: Un secret se remplace ; un patrimoine publié ne se reprend pas. Le miroir
#: sert donc un desk VIDE, ce qui est aussi la bonne condition de mesure :
#: l'instance de vérification doit montrer les états d'absence, pas les
#: positions de son auteur.
EXCLUS_FICHIERS = {'.env', '.vertex_secret',
                   'desk_data.json', 'position_inventory.json',
                   'tracking.json', 'track_record.json', 'journal.json'}
#: Motifs de sauvegarde des mêmes fichiers (`desk_data_backup_2026….json`).
EXCLUS_MOTIFS = ('desk_data', 'position_inventory', 'track_record')


def _ignorer(dossier: str, noms: list[str]) -> set[str]:
    out = {n for n in noms
           if n in EXCLUS_DOSSIERS or n in EXCLUS_FICHIERS or n.endswith('.pyc')}
    #  Les sauvegardes datées portent le même patrimoine sous un autre nom.
    out |= {n for n in noms
            if n.endswith('.json') and any(m in n for m in EXCLUS_MOTIFS)}
    return out


def miroir(destination: str) -> None:
    """Copie du dépôt par-dessus la destination (les fichiers sont écrasés).

    Pas de suppression préalable : sous Windows, un dossier encore tenu par un
    processus (ou en lecture seule) fait échouer `rmtree` ; un fichier périmé
    laissé dans la copie est sans effet, le serveur ne sert que le code copié."""
    shutil.copytree(RACINE, destination, ignore=_ignorer, dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--port', type=int, default=5003)
    parser.add_argument('--dest', default=os.path.join(tempfile.gettempdir(), 'vertex-qa'))
    args = parser.parse_args()

    miroir(args.dest)
    os.chdir(args.dest)
    sys.path.insert(0, args.dest)
    os.environ['NO_IBKR'] = '1'
    os.environ['DEMO'] = '0'
    os.environ['VERTEX_CODE'] = ''
    os.environ['START_ON_IMPORT'] = '1'
    os.environ.pop('PORT', None)
    import terminal  # noqa: E402 — les workers démarrent à l'import (START_ON_IMPORT)
    print('QA -> http://127.0.0.1:%d  (NO_IBKR=1, DEMO=0, sans verrou, loopback) — copie : %s'
          % (args.port, args.dest))
    terminal.app.run(host='127.0.0.1', port=args.port, debug=False,
                     use_reloader=False, threaded=True)


if __name__ == '__main__':
    main()
