# -*- coding: utf-8 -*-
"""P1 — diffusion réelle (docs/VERTEX_PLAN_SUITE.md).

Le diffuseur SSE avait des émetteurs (scan, board d'options, alertes, système)
mais AUCUNE page n'en faisait rien hors deux cas : les cartes sondaient. Ici :
- deux émetteurs de plus (actualités, battements de jobs) ;
- le client invalide le cache et rejoue les tâches de la page sur événement,
  différé de 1,5 s, jamais en onglet masqué (rattrapage), jamais un reload ;
- Marchés, Opportunités (hors screener) et Portefeuille enregistrent leurs
  chargeurs comme tâches rejouables.
Tests contractuels et de source ; le comportement navigateur est vérifié sur
l'instance QA (journal de nuit).
"""
import os
import queue

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(_ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def test_le_canal_news_existe_et_le_client_l_ecoute():
    from vertex.services import live_stream as ls
    assert 'news' in ls.CHANNELS
    js = _src('vertex', 'static', 'vertex', 'js', 'live-updates.js')
    assert "'jobs', 'system', 'news'" in js


def test_le_battement_d_un_job_est_diffuse():
    from vertex.services.live_stream import BROKER
    from vertex.scheduler import registry
    q = BROKER.subscribe()
    try:
        registry.beat('TEST_DIFFUSION_JOB', ok=True)
        ev = q.get(timeout=2)
        assert ev['channel'] == 'jobs' and ev['data'] == {'job': 'TEST_DIFFUSION_JOB', 'ok': True}
    finally:
        BROKER.unsubscribe(q)


def test_la_boucle_actualites_diffuse():
    src = _src('terminal.py')
    assert "_broker.publish('news', {'n': len(news_state.get('items') or [])" in src


def test_le_client_reagit_sans_rechargement():
    """Le client réagit sans recharger — et sans rejouer ce qui n'a pas bougé.

    MESURE (constat 23) : `appliquer()` appelait `VX.refresh.runTasks()` sans
    argument pour TOUS les canaux, canal `jobs` compris. Or `jobs` annonce
    qu'une boucle de fond a battu et sa seule cible de cache est `/api/system` :
    chaque battement faisait donc rejouer l'INTÉGRALITÉ des tâches de la page
    ouverte — Marchés, Portefeuille, Aujourd'hui relançaient tous leurs fetch
    pour un événement qui ne touche aucun de leurs chiffres, et certains de ces
    fetch font battre des jobs à leur tour. Amplification inter-pages, bornée
    (≈1 événement / 10 s / job) mais entière.

    Ce gardien épinglait la forme fautive au caractère près
    (`VX.refresh.runTasks()` et `async runTasks()`). Il exige désormais le
    rejeu CIBLÉ : `runTasks(labels)` filtre par label de tâche. Les autres
    canaux, qui annoncent des données réellement peintes, gardent le rejeu
    complet (`REJEU_CIBLE[channel]` vaut `undefined` → aucun filtre).

    La LISTE elle-même n'est plus épinglée ici. Mesure du 2026-09-06 : figer
    `{ jobs: ['jobs'] }` au caractère près a masqué un défaut réel — la vue
    Alertes enregistre `loadAlerts` sous le label `alertes` et lit pourtant
    `/api/system/jobs`, donc elle était exclue du rejeu et n'était repeinte
    que par son intervalle de 60 s. Un gardien qui fige une liste empêche de
    la corriger. Ce qui doit rester vrai, c'est le FILTRAGE ; la composition
    de la liste est vérifiée par sa propre mesure, dans
    tests/test_rejeu_canal_jobs.py, qui la confronte aux tâches réellement
    enregistrées par la page.
    """
    js = _src('vertex', 'static', 'vertex', 'js', 'live-updates.js')
    assert 'function reagir(channel)' in js and 'function appliquer(channel)' in js
    assert 'setTimeout(() => appliquer(channel), 1500)' in js, 'les événements doivent être regroupés'
    assert 'if (document.hidden) { pending[channel] = true; return; }' in js
    assert 'function rattraper()' in js and "connect(); rattraper();" in js
    assert 'location.reload' not in js
    assert 'VX.refresh.runTasks(REJEU_CIBLE[channel])' in js
    assert 'VX.refresh.runTasks()' not in js, (
        'rejeu complet restauré : un battement `jobs` relance toutes les tâches'
    )
    assert 'const REJEU_CIBLE = {' in js and "jobs: [" in js, (
        'le canal `jobs` n’a plus de liste de rejeu ciblé')
    # vx:data-refreshed part APRÈS l'invalidation (regroupé), plus par événement brut
    assert "VX.bus.emit('vx:data-refreshed', { channel, live: true });" in js
    assert "VX.bus.emit('vx:data-refreshed', { channel: ev.channel, live: true });" not in js
    core = _src('vertex', 'static', 'vertex', 'js', 'vx-core.js')
    assert 'async runTasks(labels)' in core and 'if (document.hidden) return false;' in core
    # Le filtre est facultatif : sans argument, le rejeu reste complet.
    assert 'const filtre = Array.isArray(labels) ? labels : null;' in core
    assert 'this._tasks.filter((t) => filtre.indexOf(t.label) >= 0)' in core


def test_les_pages_rejouent_leurs_chargeurs_en_preservant_les_filtres():
    m = _src('vertex', 'ui', 'pages', 'markets_page.py')
    assert "VX.bus.on('vx:data-refreshed',boot);" in m      # rejeu après invalidation
    assert "const d=(ev&&ev.detail)||{}; if(d.macro_officiel" in m, 'l’écouteur macro doit lire ev.detail (CustomEvent)'
    o = _src('vertex', 'ui', 'pages', 'opportunities_page.py')
    assert "if(VIEW==='screener')return Promise.resolve();" in o, 'le screener (filtres saisis) ne doit pas être rejoué'
    p = _src('vertex', 'ui', 'pages', 'portfolio_page.py')
    assert "'portefeuille-live'" in p
