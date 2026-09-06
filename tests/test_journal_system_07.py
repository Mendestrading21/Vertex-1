"""tests/test_journal_system_07.py — PR n°7 (gardiens Journal + Système).

Journal (« Suis-je en train de devenir un meilleur investisseur ? ») : discipline
UNIQUEMENT — Hero éditorial honnête, stats comportementales, hypothèses,
progression. Aucune performance de portefeuille (elle vit dans Portefeuille).
Système (« Puis-je faire confiance à Vertex aujourd'hui ? ») : Hero technique
cockpit. READONLY absolu.
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module')
def client():
    import terminal
    terminal.app.config['TESTING'] = True
    return terminal.app.test_client()


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


JR = 'vertex/ui/pages/performance_page.py'
SY = 'vertex/ui/pages/system_page.py'


# ── Journal = discipline uniquement ──────────────────────────────────────
def test_journal_is_discipline_not_portfolio_performance():
    src = _read(JR)
    # aucune courbe de performance de portefeuille au Journal
    assert 'equityCard' not in src and 'drawdownCard' not in src and 'heatmapCard' not in src
    # discipline / comportement
    assert 'Discipline' in src and 'function behavioral' in src
    assert 'respectMethod' in src and 'invalRespect' in src
    # renvoi vers le domicile de la performance
    assert '/portfolio?view=performance' in src


def test_journal_hero_is_honest_no_fabricated_percent():
    src = _read(JR)
    assert 'vx-pf-hero' in src and 'function loadDiscipline' in src
    # honnêteté explicite : rien n'est inventé
    assert 'inventé' in src
    # pas de pourcentage codé en dur type « 92 % » dans le Hero
    assert '92 %' not in src and '92%' not in src


def test_journal_new_views_present():
    src = _read(JR)
    for v in ('overview', 'journal', 'learnings', 'progression', 'track-record'):
        assert f"('{v}'," in src
    assert 'function loadHypotheses' in src and 'function loadProgression' in src
    # biais comportementaux
    assert 'vx-pf-biais' in src


def test_journal_routes_200(client):
    for v in ('overview', 'journal', 'learnings', 'progression', 'track-record'):
        r = client.get('/journal?view=' + v)
        assert r.status_code == 200, v
    r = client.get('/journal')
    #  VERTEX 2.0 : l'espace s'appelle Performance — « la méthode fonctionne-t-elle,
    #  et est-elle bien appliquée ? ». Le Journal en est une SOUS-VUE : il mesure la
    #  même chose, à l'échelle de la décision individuelle.
    #  L'URL /journal continue de servir la page à l'identique, et c'est le point :
    #  elle est en favori, liée dans le produit et présente dans une trentaine de
    #  bancs. Ce qui a changé est le titre affiché, pas la disponibilité.
    html = r.get_data(as_text=True)
    #  VERTEX 2.0 : le titre passe par `vx2.page_header`, qui pose la classe
    #  canonique. L'intention du banc — la page porte bien son titre — est
    #  conservee ; seul le balisage a change.
    assert r.status_code == 200 and '<h1 class="vx2-title">Performance</h1>' in html
    assert 'Journal' in html, 'le Journal reste nommé quelque part dans la page'


# ── Système = Hero technique cockpit ─────────────────────────────────────
def test_system_hero_technique_present():
    src = _read(SY)
    assert 'vx-sys-hero' in src
    assert 'Confiance données' in src
    assert 'Système opérationnel' in src and 'Système partiellement dégradé' in src
    # confiance = IBKR + fraîcheur + erreurs + readonly
    assert 'IBKR' in src and 'lecture seule confirmée' in src


def test_system_route_200_and_readonly(client):
    r = client.get('/system')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    #  `in html` avait glissé DANS le commentaire : l'assertion portait sur une
    #  chaîne littérale non vide, donc toujours vraie. Mesure par mutation
    #  (page_header privé de son <h1>) : /system rendait 103 987 caractères SANS
    #  le titre et ce banc restait vert, pendant que la garde jumelle de la
    #  ligne 77 (forme correcte) échouait. Garde morte, remise en vie.
    assert '<h1 class="vx2-title">Système</h1>' in html  # VERTEX 2.0 : titre via vx2.page_header
    assert 'READONLY' in html  # invariant affiché
