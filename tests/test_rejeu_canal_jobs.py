# -*- coding: utf-8 -*-
"""Le filtre de rejeu du canal `jobs` nomme TOUTES les tâches qui en dépendent.

Mesure du 2026-09-06 (contrôle adverse) : pour arrêter l'amplification
inter-pages, `live-updates.js` a restreint le rejeu du canal `jobs` à la seule
tâche portant le label `jobs`. Or la page Système enregistre ses tâches PAR
VUE : la vue « alertes » enregistre `loadAlerts` sous le label `alertes`, et
`loadAlerts` lit `/api/system/jobs` pour peindre « Tâches en échec » et
« dernière erreur consignée ». Le filtre l'excluait : le cache était bien
invalidé, mais la carte n'était repeinte que par son intervalle de 60 s, contre
environ 1,5 s auparavant.

Le défaut est invisible à la lecture — il faut rapprocher trois endroits — donc
ce banc le rapproche : toute tâche de la page Système qui LIT l'endpoint des
jobs doit être rejouée par le canal des jobs.

Aucun réseau, aucun navigateur : lecture des deux sources.
"""
import os
import re

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PAGE = os.path.join(_RACINE, 'vertex', 'ui', 'pages', 'system_page.py')
_LIVE = os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'js', 'live-updates.js')
#: L'endpoint que le battement `jobs` rend périmé.
_ENDPOINT = '/api/system/jobs'


def _lire(chemin):
    with open(chemin, encoding='utf-8') as f:
        return f.read()


def _taches_enregistrees() -> dict[str, str]:
    """{nom de fonction: label} pour chaque `VX.refresh.register(fn, ms, 'label')`."""
    motif = re.compile(r"VX\.refresh\.register\(\s*(\w+)\s*,\s*\d+\s*,\s*'([^']+)'")
    return {m.group(1): m.group(2) for m in motif.finditer(_lire(_PAGE))}


def _corps(source: str, nom: str) -> str:
    """Corps approximatif d'une fonction JS, du `function nom` au suivant."""
    debut = source.find('function %s(' % nom)
    if debut < 0:
        debut = source.find('async function %s(' % nom)
    assert debut >= 0, 'fonction %s introuvable' % nom
    suivant = source.find('\nfunction ', debut + 1)
    autre = source.find('\nasync function ', debut + 1)
    fins = [i for i in (suivant, autre) if i > 0]
    return source[debut:min(fins)] if fins else source[debut:]


def _rejeu_du_canal_jobs() -> list[str]:
    m = re.search(r"REJEU_CIBLE\s*=\s*\{([^}]*)\}", _lire(_LIVE))
    assert m, 'REJEU_CIBLE introuvable dans live-updates.js'
    bloc = re.search(r"jobs\s*:\s*\[([^\]]*)\]", m.group(1))
    assert bloc, 'le canal `jobs` n’a plus de liste de rejeu'
    return re.findall(r"'([^']+)'", bloc.group(1))


def test_le_banc_mesure_bien_quelque_chose():
    """Une garde qui n'inspecte rien est une garde qui ment."""
    taches = _taches_enregistrees()
    assert len(taches) >= 4, taches
    assert 'loadAlerts' in taches and 'loadAutomations' in taches, taches


def test_toute_tache_qui_lit_les_jobs_est_rejouee_par_le_canal_jobs():
    page = _lire(_PAGE)
    rejeu = set(_rejeu_du_canal_jobs())
    manquantes = []
    for fonction, label in _taches_enregistrees().items():
        if _ENDPOINT in _corps(page, fonction) and label not in rejeu:
            manquantes.append('%s (label %r)' % (fonction, label))
    assert not manquantes, (
        'ces tâches lisent %s mais ne sont pas rejouées par le canal `jobs` — '
        'leur carte reste périmée jusqu’à leur propre intervalle : %s'
        % (_ENDPOINT, ', '.join(manquantes)))


def test_le_filtre_ne_rejoue_pas_toute_la_page():
    """Contre-épreuve : le correctif ne doit pas rouvrir l'amplification."""
    rejeu = _rejeu_du_canal_jobs()
    labels = set(_taches_enregistrees().values())
    assert set(rejeu) < labels, (
        'le canal `jobs` rejoue TOUTES les tâches de la page : c’est '
        'l’amplification inter-pages que le filtre existe pour arrêter')
