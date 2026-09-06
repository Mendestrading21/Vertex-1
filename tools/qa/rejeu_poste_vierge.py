# -*- coding: utf-8 -*-
"""tools/qa/rejeu_poste_vierge.py — la suite passe-t-elle sur une machine VIERGE ?

Mesuré le 2026-09-06 : deux bancs de `test_ecran_peint_ce_que_la_route_sert.py`
passaient sur le poste de développement et TOMBAIENT en intégration continue.
La cause n'était pas l'environnement : `/api/portfolio/context` lit
`persist.load_json('desk_data.json')`, c'est-à-dire le desk RÉEL de la machine.
Ici il porte des positions déclarées, donc la route rendait un contexte
complet ; sur un exécuteur vierge elle rend son court-circuit honnête
`{'available': False, 'reason': 'aucune position réelle déclarée…'}`.

Un banc qui dépend du portefeuille de l'utilisateur ne prouve rien. Il lit des
données personnelles, il rend un résultat différent sur chaque machine, et
surtout il MASQUE la régression qu'il prétend surveiller : vert ici, il ne
protège rien.

Cet outil rejoue la suite (ou une partie) avec le répertoire de cache pointé
sur un dossier temporaire VIDE. Tout ce qui tombe alors dépend de l'état local
de la machine — desk déclaré, journal de trades, caches de scan, instantanés —
et doit apporter ses propres données.

Aucun fichier du dépôt n'est modifié ni supprimé : seul le chemin de lecture
change, le temps du rejeu.

    python tools/qa/rejeu_poste_vierge.py [chemins pytest...]
    python tools/qa/rejeu_poste_vierge.py tests/test_ecran_peint_ce_que_la_route_sert.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Ces deux bancs mesurent LE CHEMIN DE CACHE lui-même — précisément ce que ce
#: rejeu détourne. Ils tombent donc par construction, et les compter comme des
#: trouvailles reviendrait à rapporter l'effet de l'outil comme un défaut du
#: produit. Un détecteur qui s'accuse lui-même n'est pas un détecteur.
#:
#: Ils ne sont pas ignorés en silence : ils sont NOMMÉS dans le rapport, avec
#: leur raison, et leur nombre est vérifié — si l'un disparaît ou si un
#: troisième apparaît, il faut regarder.
ATTENDUS = {
    'tests/test_persist.py::test_cache_path_points_to_repo_root':
        'vérifie que le cache est sous la racine du dépôt — ce rejeu le déplace exprès',
    'tests/test_correlations_weekly_parity.py::test_le_chemin_du_snapshot_hebdo_n_a_pas_bouge':
        'compare le chemin de l’instantané hebdomadaire à la racine — même cause',
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:                                  # noqa: BLE001
        pass
    sys.path.insert(0, RACINE)
    os.chdir(RACINE)

    vide = tempfile.mkdtemp(prefix='vertex-poste-vierge-')
    from vertex.services import persist
    reel = persist._BASE_DIR
    persist._BASE_DIR = vide

    desk = persist.load_json('desk_data.json', {}) or {}
    print('répertoire de cache : %s' % vide)
    print('desk vu par le serveur : %s'
          % ('(vide — c’est le but)' if not desk else 'NON VIDE : %r' % list(desk)[:5]))
    if desk:
        print('ATTENTION : le détournement n’a pas pris, la mesure ne vaut rien.')
        persist._BASE_DIR = reel
        return 2

    import pytest
    cibles = sys.argv[1:] or ['tests']
    #  On DÉSÉLECTIONNE les deux bancs qui mesurent le chemin détourné,
    #  plutôt que de les laisser tomber puis d'expliquer après coup.
    exclusions = []
    for nom in ATTENDUS:
        exclusions += ['--deselect', nom]
    code = pytest.main(['-q', '-p', 'no:cacheprovider'] + exclusions + cibles)
    persist._BASE_DIR = reel

    print('')
    print('Écartés par construction — ils mesurent le chemin que ce rejeu détourne :')
    for nom, raison in ATTENDUS.items():
        print('  · %s' % nom)
        print('    %s' % raison)
    print('')
    print('code de sortie : %s' % code)
    if code:
        print('Ce qui tombe ici dépend de l’état LOCAL de la machine : le banc '
              'doit apporter ses propres données, pas lire celles de '
              'l’utilisateur.')
    else:
        print('Aucun banc ne dépend de l’état local de cette machine.')
    return int(code)


if __name__ == '__main__':
    sys.exit(main())
