"""vertex.ui.shell — app shell unique du Vertex Master Redesign (§9-13).

Rend le squelette commun (sidebar 8 espaces, topbar, drawers, palette,
toasts, mobile action bar) autour du contenu d'une page. Migration strangler :
les nouvelles pages utilisent ce shell, le monolithe historique reste intact
le temps de la bascule des routes.
"""
from __future__ import annotations

#  vx-shell-3 : refonte dashboards — le bundle CSS (immuable, 1 an) change de
#  contenu ; sans ce bump un visiteur garderait l'ancienne feuille en cache.
SHELL_VERSION = 'vx-shell-10'

#: L'ORDRE DE LA CASCADE — un contrat, pas une liste (lot 30). Le bundle
#: /asset/css/bundle.css concatène ces feuilles dans CET ordre exact :
#: le déplacer change le rendu (la couche finale vertex-2-0.css gagne).
#: Lighthouse (lot 28) : 19 requêtes CSS en chaîne critique = LCP 6-7 s
#: simulés — une seule requête les remplace ; les feuilles individuelles
#: restent servies (développement, bancs, rollback).
CSS_ORDER = ('fonts.css', 'tokens.css', 'base.css', 'layout.css',
             'components.css', 'buttons.css', 'states.css', 'animations.css',
             'forms.css', 'tables.css', 'charts.css', 'utilities.css',
             'responsive.css', 'polish.css', 'control-surface.css',
             'cockpit.css', 'premium.css', 'glass.css', 'vertex-2-0.css')

# ── Navigation Vertex 2.0 — groupée par TRAVAIL, pas par architecture ────────
#
# La forme précédente alignait sept entrées à plat : l'utilisateur ne distinguait
# pas ce qu'il consulte tous les matins de ce qu'il explore ponctuellement. Les
# quatre groupes disent ce à quoi chaque page sert :
#
#   Piloter       ce que je regarde maintenant
#   Explorer      ce que j'étudie
#   Gérer         ce que je possède et surveille
#   Intelligence  ce qui explique
#
# Système reste épinglé en bas : c'est un utilitaire, pas une étape de travail.
#
# Aucune page n'a disparu dans la bascule. Marchés retrouve sa page propre,
# Journal devient une sous-vue de Performance, Suivis devient Suivi — et les
# anciennes URL continuent de répondre (voir LEGACY_REDIRECTS dans redesign.py).
NAV_GROUPS = (
    {'id': 'piloter', 'label': 'Piloter', 'items': (
        {'id': 'briefing', 'label': "Aujourd'hui", 'href': '/', 'icon': 'home'},
        {'id': 'calendar', 'label': 'Calendrier', 'href': '/calendar', 'icon': 'calendar'},
    )},
    {'id': 'explorer', 'label': 'Explorer', 'items': (
        {'id': 'markets', 'label': 'Marchés', 'href': '/markets', 'icon': 'globe'},
        {'id': 'opportunities', 'label': 'Opportunités', 'href': '/opportunities', 'icon': 'radar'},
        {'id': 'analysis', 'label': 'Analyse', 'href': '/analysis', 'icon': 'chart'},
        {'id': 'options', 'label': 'Options', 'href': '/options', 'icon': 'bolt'},
        {'id': 'simulator', 'label': 'Simulateur', 'href': '/simulator', 'icon': 'sliders'},
    )},
    {'id': 'gerer', 'label': 'Gérer', 'items': (
        {'id': 'portfolio', 'label': 'Portefeuille', 'href': '/portfolio', 'icon': 'briefcase'},
        {'id': 'follow-up', 'label': 'Suivi', 'href': '/follow-up', 'icon': 'eye'},
        {'id': 'performance', 'label': 'Performance', 'href': '/performance', 'icon': 'trend'},
    )},
    {'id': 'intelligence', 'label': 'Intelligence', 'items': (
        {'id': 'intelligence', 'label': 'Vertex IA', 'href': '/intelligence', 'icon': 'brain'},
    )},
)

#: Utilitaire épinglé — hors groupes de travail.
PINNED_NAV = (
    {'id': 'system', 'label': 'Système', 'href': '/system', 'icon': 'settings'},
)

#: Registre PLAT des espaces servis. Reste la source unique pour tout ce qui
#: itère sur la navigation (tests, mesures QA, palette de commandes) : la
#: bascule vers des groupes ne devait pas casser ces consommateurs.
PRIMARY_NAV = tuple(
    it for g in NAV_GROUPS for it in g['items']) + PINNED_NAV

# Icônes : SVG inline sobres (pas d'emojis comme langage principal).
_ICONS = {
    'home': '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
    'globe': '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.7 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.7-3.8-9S9.5 5.6 12 3z"/>',
    'radar': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12 18 6"/>',
    'briefcase': '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
    'chart': '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 16v-5m4 5V8m4 8v-3"/>',
    'trend': '<path d="M3 17 9 11l4 4 8-8"/><path d="M21 12V7h-5"/>',
    'brain': '<path d="M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0-1 5.8V15a3 3 0 0 0 4 2.8"/><path d="M15 4a3 3 0 0 1 3 3v1a3 3 0 0 1 1 5.8V15a3 3 0 0 1-4 2.8"/><path d="M12 3v18"/>',
    'settings': '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.4 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.4-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z"/>',
    'search': '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    'bell': '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    'plug': '<path d="M9 7V3m6 4V3M7 7h10v4a5 5 0 0 1-10 0V7z"/><path d="M12 16v5"/>',
    'refresh': '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'chevrons': '<path d="m11 17-5-5 5-5m7 10-5-5 5-5"/>',
    'back': '<path d="m15 18-6-6 6-6"/>',
    'star': '<path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6-5.4-3-5.4 3 1.1-6L3.2 9.4l6.1-.8L12 3z"/>',
    'bolt': '<path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z"/>',
    'book': '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19a2 2 0 0 0 2 2h13"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4m8-4v4"/>',
    'sliders': '<path d="M4 7h10M18 7h2M4 12h4M12 12h8M4 17h12M20 17h0"/>'
               '<circle cx="16" cy="7" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="17" r="2"/>',
    'eye': '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
}


def json_for_script(value) -> str:
    """Sérialise `value` pour un bloc `<script>` inline — JAMAIS `json.dumps` nu.

    `json.dumps` échappe `"` et `\\` mais NI `<` NI `/` : une valeur contenant
    `</script>` ferme la balise côté analyseur HTML et tout ce qui suit devient
    du HTML ACTIF. C'était le cas de `/opportunities?sym=…`, dont les valeurs de
    paramètres d'URL n'étaient pas filtrées (constat du lot 372 — seules les
    CLÉS étaient sur liste blanche).

    On neutralise `<`, `>` et `&` en échappements `\\uXXXX`. Un moteur JS les
    relit à l'identique dans un littéral de chaîne : le comportement client est
    inchangé, seul l'analyseur HTML ne peut plus voir de balise fermante.

    Gardien : `tests/test_json_script.py`.
    """
    import json as _json
    return (_json.dumps(value)
            .replace('<', '\\u003c').replace('>', '\\u003e')
            .replace('&', '\\u0026'))


def icon(name: str, size: int = 18) -> str:
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
            f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{_ICONS.get(name, "")}</svg>')


def _nav_link(it: dict, active: str) -> str:
    current = ' aria-current="page"' if it['id'] == active else ''
    return (f'<a class="vx-nav-item" href="{it["href"]}" data-nav-id="{it["id"]}"{current}>'
            f'{icon(it["icon"])}<span class="vx-nav-label">{it["label"]}</span></a>')


def _sidebar(active: str) -> str:
    """Sidebar groupée par travail. Le titre de groupe est un vrai en-tête de
    liste : il porte le regroupement pour l'œil ET pour un lecteur d'écran."""
    groups = []
    for g in NAV_GROUPS:
        links = ''.join(_nav_link(it, active) for it in g['items'])
        groups.append(
            f'<div class="vx-nav-group" role="group" '
            f'aria-labelledby="vx-navg-{g["id"]}">'
            f'<p class="vx-nav-group-label" id="vx-navg-{g["id"]}">{g["label"]}</p>'
            f'{links}</div>')
    nav = ''.join(groups)
    system_item = ''.join(_nav_link(it, active) for it in PINNED_NAV)
    return f'''<aside class="vx-sidebar" aria-label="Navigation principale">
  <div class="vx-sidebar-logo"><span class="vx-logo-mark">V</span>
    <span class="vx-logo-name">Vertex</span></div>
  <nav class="vx-sidebar-nav">{nav}</nav>
  <div class="vx-sidebar-foot">
    <div class="vx-sidebar-status" id="vx-global-status">
      <span class="vx-dot" style="width:7px;height:7px;border-radius:99px;background:var(--vx-text-faint)"></span>
      <span class="vx-status-label">État…</span></div>
    {system_item}
    <button class="vx-nav-item vx-collapse-btn" id="vx-collapse-btn"
      aria-label="Réduire la navigation">{icon('chevrons')}<span class="vx-nav-label">Réduire</span></button>
  </div>
</aside>'''


def _space_href(active: str) -> str:
    """Racine de l'espace actif — depuis PRIMARY_NAV (source unique)."""
    for it in PRIMARY_NAV:
        if it['id'] == active:
            return it['href']
    return '/'


def _topbar(space_label: str, sub_label: str = '', space_href: str = '/') -> str:
    # Fil d'Ariane CLIQUABLE (lot 55) : « Vertex » ramène au briefing, le
    # segment d'espace ramène à la racine de l'espace (utile depuis une fiche).
    crumb = (f'<a class="vx-crumb-root" href="/">Vertex</a>'
             f'<span aria-hidden="true">/</span>'
             f'<a class="vx-crumb-space" href="{space_href}"><b>{space_label}</b></a>')
    if sub_label:
        crumb += f'<span aria-hidden="true">/</span><span>{sub_label}</span>'
    return f'''<header class="vx-topbar">
  <button class="vx-btn vx-btn-icon vx-btn-ghost vx-hide-mobile" id="vx-mobile-nav-btn"
    aria-label="Ouvrir la navigation" style="display:none">{icon('chevrons')}</button>
  <button class="vx-back-btn" id="vx-back-btn" data-visible="0">{icon('back')}<span>Retour</span></button>
  <nav class="vx-breadcrumb" aria-label="Fil d’Ariane">{crumb}</nav>
  <div class="vx-topbar-search">{icon('search', 16)}
    <input id="vx-global-search" type="search" placeholder="Rechercher une action, une option ou une page"
      autocomplete="off" aria-label="Recherche globale" />
    <span class="vx-kbd">⌘K</span></div>
  <div class="vx-topbar-right">
    <button class="vx-btn vx-btn-sm vx-btn-primary" id="vx-add-btn" aria-label="Ajouter une position ou une idée">{icon('plus', 14)}<span class="vx-hide-mobile">Ajouter</span></button>
    <div class="vx-session vx-hide-mobile" id="vx-session">—<br><span class="vx-muted">New York —:—</span></div>
    <button class="vx-btn vx-btn-icon vx-btn-ghost" id="vx-connections-btn"
      aria-label="Connexions" title="Connexions (IBKR, TradingView, Claude, sync)">{icon('plug')}</button>
    <button class="vx-btn vx-btn-icon vx-btn-ghost" id="vx-notifs-btn" style="position:relative"
      aria-label="Notifications">{icon('bell')}<span class="vx-notif-badge" id="vx-notif-badge" hidden>0</span></button>
    <button class="vx-btn vx-btn-icon vx-btn-ghost" id="vx-refresh-btn" data-state="ready"
      aria-label="Actualiser les données">{icon('refresh')}</button>
  </div>
</header>'''


def _mobile_bar(active: str) -> str:
    """Cinq destinations maximum, et celles du travail quotidien : Aujourd'hui,
    Opportunités, Portefeuille, Suivi, Performance. Le reste passe par « Plus »."""
    order = ('briefing', 'opportunities', 'portfolio', 'follow-up', 'performance')
    by_id = {it['id']: it for it in PRIMARY_NAV}
    links = []
    for nav_id in order:
        it = by_id.get(nav_id)
        if it is None:
            continue
        current = ' aria-current="page"' if it['id'] == active else ''
        links.append(f'<a href="{it["href"]}"{current}>{icon(it["icon"], 20)}'
                     f'<span>{it["label"]}</span></a>')
    return (f'<div class="vx-mobile-bar"><nav aria-label="Navigation mobile">{"".join(links)}'
            f'<button id="vx-mobile-more" aria-label="Plus">{icon("chevrons", 20)}<span>Plus</span></button>'
            f'</nav></div>')


_OVERLAYS = '''
<div class="vx-overlay" id="vx-overlay" data-open="0"></div>
<aside class="vx-drawer" id="vx-drawer" data-open="0" role="dialog" aria-modal="true" aria-label="Panneau contextuel" aria-hidden="true" inert>
  <div class="vx-drawer-header"><h2 id="vx-drawer-title">—</h2>
    <button class="vx-btn vx-btn-icon vx-btn-ghost vx-right" data-close-drawer aria-label="Fermer">✕</button></div>
  <div class="vx-drawer-tabs" id="vx-drawer-tabs" hidden></div>
  <div class="vx-drawer-body" id="vx-drawer-body"></div>
  <div class="vx-drawer-footer" id="vx-drawer-footer"></div>
</aside>
<div class="vx-modal" id="vx-modal" data-open="0" role="dialog" aria-modal="true" aria-hidden="true" inert>
  <div class="vx-modal-box">
    <div class="vx-modal-header"><h2 id="vx-modal-title">—</h2>
      <button class="vx-btn vx-btn-icon vx-btn-ghost vx-right" data-close-modal aria-label="Fermer">✕</button></div>
    <div class="vx-modal-body" id="vx-modal-body"></div>
    <div class="vx-modal-footer" id="vx-modal-footer"></div>
  </div>
</div>
<div class="vx-palette" id="vx-palette" data-open="0" role="dialog" aria-modal="true" aria-label="Palette de commandes">
  <div class="vx-palette-box">
    <input id="vx-palette-input" placeholder="Ticker, page ou action… (↑↓ pour naviguer, Entrée pour ouvrir)"
      autocomplete="off" aria-label="Palette de commandes" />
    <div class="vx-palette-list" id="vx-palette-list" role="listbox"></div>
  </div>
</div>
<div class="vx-context-menu" id="vx-context-menu" data-open="0" role="menu"></div>
<div class="vx-toasts" role="status" aria-live="polite"></div>
'''


def _wants_fragment() -> bool:
    """Vrai si la requête courante demande un FRAGMENT (navigation client persistante).

    Progressive-enhancement : sans JS (ou en accès direct / deep link / refresh /
    nouvel onglet) la requête est normale → document complet. Le routeur client
    (vx-router.js) ajoute l'en-tête `X-Vertex-Fragment: 1` pour ne recevoir que le
    contenu + les métadonnées, et ne remplacer que #vx-content sans reconstruire le
    shell. Lecture seule ; jamais d'effet de bord."""
    try:
        from flask import request
        return (request.headers.get('X-Vertex-Fragment') == '1'
                or request.args.get('__frag') == '1')
    except Exception:
        return False


def _render_fragment(*, title: str, active: str, space_label: str, sub_label: str,
                     content: str, page_js: str, page_label: str, mobile_bar: str) -> str:
    """Enveloppe de fragment : métadonnées + contenu + barre mobile + scripts de page.

    Le contenu et la barre mobile sont dans des <template> (aucune ressource chargée,
    aucun script exécuté à l'analyse) ; le routeur lit les data-* pour remettre à jour
    le fil d'Ariane / la nav active / le titre, injecte le contenu, puis ré-exécute
    `page_js` (src dédupliqués, inline en portée isolée). Voir vx-router.js."""
    from html import escape
    return (f'<div class="vx-fragment" data-title="{escape(title, quote=True)}" '
            f'data-active="{escape(active, quote=True)}" '
            f'data-space-label="{escape(space_label, quote=True)}" '
            f'data-sub-label="{escape(sub_label, quote=True)}" '
            f'data-page-label="{escape(page_label or space_label, quote=True)}"></div>\n'
            f'<template class="vx-frag-content">{content}</template>\n'
            f'<template class="vx-frag-mobile">{mobile_bar}</template>\n'
            f'{page_js}')


def render_shell(*, title: str, active: str, space_label: str, sub_label: str = '',
                 content: str, page_js: str = '', page_label: str = '',
                 mobile_actions: str = '') -> str:
    """Assemble la page complète autour du contenu fourni.

    Si la requête demande un fragment (navigation client persistante), ne renvoie
    QUE le contenu + métadonnées + scripts de page (shell conservé côté client)."""
    from vertex.engines.recommendation import vocab_js as _vjs
    vocab = _vjs()   # vocabulaire des verdicts — source unique (__VXVOCAB)
    mobile_bar = mobile_actions or _mobile_bar(active)
    if _wants_fragment():
        return _render_fragment(title=title, active=active, space_label=space_label,
                                sub_label=sub_label, content=content, page_js=page_js,
                                page_label=page_label, mobile_bar=mobile_bar)
    return f'''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#080808">
<title>{title} · Vertex</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/static/icon-180.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="preload" as="font" type="font/woff2" crossorigin href="/static/vertex/fonts/geist-variable.woff2">
<link rel="preload" as="font" type="font/woff2" crossorigin href="/static/vertex/fonts/geist-mono-variable.woff2">
<link rel="stylesheet" href="/asset/css/bundle.css?v={SHELL_VERSION}">
<noscript><style>
  /* Sans JavaScript, aucun de ces squelettes ne sera jamais rempli : ils
     promettent une donnee qui n'arrivera pas. Mesure au navigateur, moteur JS
     coupe : 53 squelettes sur dix pages, dont 22 sur la page d'accueil. Un
     ecran qui fait semblant de charger ment plus qu'un ecran qui dit non. */
  .vx-skeleton,.vx2-skeleton{{display:none !important}}
</style></noscript>
</head>
<body data-shell="{SHELL_VERSION}">
<a class="vx-skip-link" href="#vx-content">Aller au contenu principal</a>
<div class="vx-app" id="vx-app" data-sidebar="expanded">
{_sidebar(active)}
<div class="vx-main">
{_topbar(space_label, sub_label, _space_href(active))}
<main class="vx-content" id="vx-content" data-space="{active}" data-page-label="{page_label or space_label}">
<noscript>
  <div class="vx2-noscript" role="alert">
    <b>JavaScript est désactivé.</b> La coque, la navigation et les liens
    fonctionnent, mais <b>aucune donnée ne se charge</b> : chiffres, graphiques,
    verdicts et fraîcheur viennent tous du navigateur. Rien de ce qui est
    affiché ci-dessous n’est à jour. Active JavaScript pour lire Vertex.
  </div>
</noscript>
{content}
</main>
</div>
</div>
{mobile_bar}
{_OVERLAYS}
<script src="/static/chart.umd.min.js" defer></script>
<script id="vx-vocab">window.__VXVOCAB={vocab};</script>
<script src="/static/vertex/js/vx-core.js"></script>
<script src="/static/vertex/js/vx-entities.js"></script>
<script src="/static/vertex/js/vx-shell.js"></script>
<script src="/static/vertex/js/vx-router.js" defer></script>
<script src="/static/vertex/js/ui/inspector-drawer.js" defer></script>
<script src="/static/vertex/js/live-updates.js" defer></script>
<script src="/static/vertex/js/charts/chart-theme-black-glass.js" defer></script>
<script src="/static/vertex/js/charts/chart-core.js" defer></script>
<script src="/static/vertex/js/charts/radar-chart.js" defer></script>
{page_js}
</body></html>'''
