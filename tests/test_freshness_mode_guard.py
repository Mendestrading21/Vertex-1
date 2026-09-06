"""SKYLER LOT 298 — gardien TRANSVERSAL du mode de fraîcheur « live ».

Leçon des lots 296/297 : deux étiquettes de fraîcheur mentaient parce
que le mode « live » était codé EN DUR pour des données de MARCHÉ qui
ont un repli (cotes desk) ou une variante démo (board). Règle
codifiée : un mode « live » codé en dur n'est permis QUE pour l'état
interne du serveur (system_page — registre des jobs, rapport de
démarrage : ces données n'ont ni repli ni variante démo). Partout
ailleurs, le mode doit suivre un drapeau réel (__pfLive, d.demo…).
"""
import glob
import re

# Exceptions documentées :
# - system_page : cartes d'état INTERNE du serveur (registre des jobs,
#   rapport de démarrage) — pas de repli ni de variante démo possible ;
# - widget_lab : bibliothèque de design FIGÉE — ses pastilles « live »
#   sont des spécimens d'exposition, pas des affirmations sur des données.
ALLOWED = {'vertex/ui/pages/system_page.py', 'vertex/ui/pages/widget_lab.py'}

SCAN = (['terminal.py']
        + glob.glob('vertex/ui/**/*.py', recursive=True)
        + glob.glob('vertex/static/vertex/js/**/*.js', recursive=True))


#: Une ligne entièrement commentée (`#` en Python, `//` en JavaScript).
_LIGNE_COMMENTEE = re.compile(r'^\s*(#|//)')


def _offenders(pattern, chemins=None):
    """Lignes de CODE qui portent le motif — jamais les commentaires.

    Mesure du 2026-09-06 : ce garde accusait `analysis_page.py:447`, la
    troisième ligne d'un commentaire de bloc qui CITE `mode:'live'` pour
    expliquer d'où vient le mode réel. Un garde lexical qui compte sa propre
    documentation a deux effets, tous deux mauvais : il crie au loup, et la
    seule façon de le faire taire est d'effacer l'explication qui empêchait
    le défaut de revenir.

    Les blocs `/* … */` sont suivis d'une ligne à l'autre : la ligne fautive
    ne commençait par aucun marqueur. Une garde qui ne regarde que le premier
    caractère ne sait pas lire du JavaScript.
    """
    out = []
    for path in (chemins if chemins is not None else SCAN):
        norm = path.replace('\\', '/')
        if norm in ALLOWED:
            continue
        with open(path, encoding='utf-8') as fh:
            dans_bloc = False
            for i, line in enumerate(fh, 1):
                nue = line
                if dans_bloc:
                    if '*/' in nue:
                        nue = nue.split('*/', 1)[1]
                        dans_bloc = False
                    else:
                        continue
                while '/*' in nue:
                    avant, apres = nue.split('/*', 1)
                    if '*/' in apres:
                        nue = avant + apres.split('*/', 1)[1]
                    else:
                        nue = avant
                        dans_bloc = True
                        break
                if _LIGNE_COMMENTEE.match(nue):
                    continue
                if re.search(pattern, nue):
                    out.append(f'{norm}:{i}: {line.strip()[:90]}')
    return out


def test_no_hardcoded_live_update_indicator():
    bad = _offenders(r",\s*'live'\)")
    assert not bad, ('mode « live » codé en dur (updateIndicator) — le mode '
                     'doit suivre un drapeau réel (__pfLive, d.demo…) : '
                     + ' | '.join(bad))


def test_no_hardcoded_live_chart_mode():
    bad = _offenders(r"mode:\s*'live'")
    assert not bad, ('mode:\'live\' codé en dur (VXCharts) — le mode doit '
                     'suivre un drapeau réel : ' + ' | '.join(bad))


LIGNE_FAUTIVE = "VXCharts.card('x', {mode:'live'});\n"

TEMOIN_JS = "VXCharts.card('x', {mode:'live'});\n// commentaire citant mode:'live' pour expliquer\n/* bloc\n   qui cite mode:'live' au milieu\n   et se ferme ici */\nvar ok = 1;\n"


def test_le_garde_attrape_toujours_un_VRAI_defaut(tmp_path):
    """Contre-épreuve — sans elle, ignorer les commentaires reviendrait à
    éteindre la garde sans que personne ne s'en aperçoive.

    Trois formes dans un même fichier : une ligne de CODE fautive (doit être
    vue), une ligne commentée et un bloc de trois lignes dont la fautive est
    au MILIEU — exactement la forme qui a fait crier la garde à tort.
    """
    f = tmp_path / 'temoin.js'
    f.write_text(TEMOIN_JS, encoding='utf-8')
    trouves = _offenders(r"mode:\s*'live'", chemins=[str(f)])
    assert len(trouves) == 1, trouves
    assert ':1:' in trouves[0], trouves


def test_le_garde_voit_un_defaut_APRES_la_fermeture_d_un_bloc(tmp_path):
    """Un bloc refermé ne doit pas rendre aveugle le reste de la ligne."""
    f = tmp_path / 'temoin2.js'
    f.write_text('/* note */ ' + LIGNE_FAUTIVE, encoding='utf-8')
    assert len(_offenders(r"mode:\s*'live'", chemins=[str(f)])) == 1
