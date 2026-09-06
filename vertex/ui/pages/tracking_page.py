"""vertex.ui.pages.tracking_page — l'espace SUIVI (Vertex 2.0).

« Quelles thèses, idées et décisions exigent une attention ? »

Vue transversale : elle **ne possède aucun store**. Elle compose ce qui existe
déjà — `/api/tracking` (suivis actifs, clôturés et en attente de donnée) — et
renvoie vers les propriétaires canoniques pour le reste : la watchlist, les
positions et les options vivent dans le Portefeuille, et n'ont pas à être
dupliquées ici.

Tout gain affiché est **hypothétique** et étiqueté comme tel — jamais un gain
encaissé. Un suivi est une idée marquée, pas une position.

`/tracking` reste servi à l'identique : l'URL est en favori et dans plusieurs
bancs. `/follow-up` est la destination canonique.
"""
from __future__ import annotations

from vertex.ui import vx2
from vertex.ui.shell import render_shell

#: Sous-vues réellement distinctes dans la donnée servie. `/api/tracking` rend
#: trois statuts — ACTIVE, DATA_REQUIRED, STOPPED — et rien d'autre : on n'en
#: invente pas un quatrième pour remplir une barre d'onglets.
#:
#: MESURE DU 06/09/2026 — `attention` et `active` rendaient un écran
#: RIGOUREUSEMENT identique (mêmes sections visibles, même titre, même
#: question, mêmes lignes) : deux onglets pour un seul écran. La distinction
#: est désormais portée par `tracking.js` sur le statut SERVI (DATA_REQUIRED /
#: référence absente), jamais sur un seuil inventé. Le titre et la question de
#: la section active sont donc nommés (`vx-trk-active-title` /
#: `vx-trk-active-question`) pour que la sous-vue dise ce qu'elle filtre.
_VIEWS = (
    ('attention', 'À revoir'),
    ('active', 'Suivis actifs'),
    ('archives', 'Archives'),
)

#: Capacités que le contrat place dans Suivi mais dont le propriétaire est
#: ailleurs. On y renvoie ; on ne les recrée pas.
_AILLEURS = (
    ('Watchlist', '/portfolio?view=watchlist',
     'Les éléments surveillés vivent dans le Portefeuille.'),
    ('Positions', '/portfolio?view=positions',
     'Les positions déclarées et leur réconciliation.'),
    ('Options', '/portfolio?view=options',
     'Les positions options, séparées des actions.'),
    ('Journal des décisions', '/performance?view=journal',
     'Les décisions et leurs revues appartiennent à Performance.'),
)

_STYLE = """
<style>
#vx-content .vx-hypo{display:inline-flex;align-items:center;gap:6px;font-size:11px;
  font-weight:600;letter-spacing:.03em;color:var(--vx-caution);
  border:1px solid rgba(221,162,59,.32);background:var(--vx-warning-soft);
  border-radius:var(--vx2-r-pill);padding:.14rem .7rem}
#vx-content .vx-trk-note{color:var(--vx-smoke);font-size:12.5px;margin:.6rem 0 0;line-height:1.55}
#vx-content .vx-pos{color:var(--vx-positive)}
#vx-content .vx-neg{color:var(--vx-negative)}
#vx-content .vx-muted{color:var(--vx-smoke)}
#vx-content .vx-stat{display:flex;flex-direction:column;min-width:88px}
#vx-content .vx-stat-label{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--vx-smoke)}
#vx-content .vx-stat-value{font-family:var(--vx-font-mono);font-size:20px;font-weight:600;
  color:var(--vx-ink);margin-top:.15rem;font-variant-numeric:tabular-nums}
#vx-content .vx-trk-ailleurs{display:grid;gap:10px;
  grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
</style>
"""


def _tabs(view: str) -> str:
    return vx2.tabs(
        [{'label': lbl, 'href': f'/follow-up?view={vid}', 'actif': vid == view}
         for vid, lbl in _VIEWS],
        libelle='Sous-vues du Suivi')


def _contexte() -> str:
    return vx2.context_bar([
        {'label': 'Population', 'contenu':
            '<span class="vx2-badge" data-state="missing">Idées suivies</span>'},
        {'label': 'Nature du rendement', 'contenu':
            '<span class="vx-hypo">Hypothétique — jamais encaissé</span>'},
        {'label': 'Référence', 'contenu':
            '<span class="vx2-stamp">Comparé à <b>SPY</b></span>'},
        {'label': 'Fraîcheur', 'contenu':
            '<span id="vx-trk-fresh">'
            + vx2.badge_etat('missing', texte='Lecture…') + '</span>'},
    ])


def _ailleurs() -> str:
    """Ce que le contrat range dans Suivi mais dont le propriétaire est ailleurs.

    Les lister en renvoyant vers eux évite deux fautes symétriques : les
    dupliquer, ou laisser croire qu'ils n'existent pas.
    """
    cartes = ''.join(
        f'<a class="vx2-surface vx2-surface--compact" href="{href}" '
        f'style="text-decoration:none;display:block">'
        f'<span class="vx2-card-title">{titre} →</span>'
        f'<p class="vx2-metric-meta" style="margin:6px 0 0">{note}</p></a>'
        for titre, href, note in _AILLEURS)
    return (f'<div class="vx-trk-ailleurs">{cartes}</div>'
            + '<p class="vx-trk-note">Ces surfaces ne sont pas recopiées ici : '
              'elles ont un propriétaire, et une même vérité ne doit avoir '
              'qu\'un seul endroit où elle se lit.</p>')


_CONTENT = """
<section class="vx2-surface vx-mt3" id="vx-trk-summary" aria-label="Résumé des suivis">
  <div class="vx2-card-head"><div><h2 class="vx2-card-title">Résumé</h2>
    <p class="vx2-card-question">Combien d'idées sont suivies, et dans quel état&nbsp;?</p></div></div>
  <div id="vx-trk-summary-body"><div class="vx2-skeleton" style="height:60px"></div></div>
</section>
<div class="vx-mt3" id="vx-trk-chart"></div>
<section class="vx2-surface vx-mt3" id="vx-trk-active" aria-label="Suivis actifs">
  <div class="vx2-card-head"><div><h2 class="vx2-card-title" id="vx-trk-active-title">Suivis actifs</h2>
    <p class="vx2-card-question" id="vx-trk-active-question">Que valent ces idées depuis qu'elles sont marquées&nbsp;?</p></div></div>
  <div id="vx-trk-active-body"><div class="vx2-skeleton" style="height:160px"></div></div>
  <p class="vx-trk-note">Un suivi est une <b>idée marquée</b> : Vertex mesure sa
    performance <b>hypothétique</b> depuis l'horodatage du suivi, contre SPY.
    Ce n'est jamais une position réelle, ni un gain encaissé.</p>
</section>
<section class="vx2-surface vx-mt3" id="vx-trk-stopped" aria-label="Suivis clôturés">
  <div class="vx2-card-head"><div><h2 class="vx2-card-title">Archives</h2>
    <p class="vx2-card-question">Qu'ont donné les suivis arrêtés&nbsp;?</p></div></div>
  <div id="vx-trk-stopped-body"></div>
</section>
%%AILLEURS%%
"""

_PAGE_JS = '<script src="/static/vertex/js/pages/tracking.js" defer></script>'


def render(view: str = 'attention') -> str:
    if view not in dict(_VIEWS):
        view = 'attention'
    label = dict(_VIEWS)[view]
    content = (
        _STYLE
        + '<div class="vx2-page" data-trk-view="' + view + '">'
        + vx2.page_header(
            surtitre='Gérer',
            titre='Suivi',
            question='Quelles thèses, idées et décisions exigent une attention ?',
            actions=vx2.bouton('Ouvrir le Portefeuille', href='/portfolio',
                               variante='ghost'))
        + _contexte()
        + _tabs(view)
        + _CONTENT.replace('%%AILLEURS%%',
                           vx2.section(titre='Ailleurs dans Vertex',
                                       note='propriétaires canoniques',
                                       corps=_ailleurs()))
        + '</div>')
    return render_shell(
        title='Suivi', active='follow-up', space_label='Suivi',
        sub_label=label, page_label='tracking',
        content=content, page_js=_PAGE_JS)


__all__ = ['render']
