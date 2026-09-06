"""vertex.ui.pages.system_page — l'espace Système (§29).

Question : « Le système est-il en bonne santé et branché sur du réel ? ».
Quatre sous-vues : connections (IBKR / TradingView / Claude / sync / stockage),
data (qualité + fraîcheur par domaine), settings (préférences locales +
export/import desk), archive (coffre vxVault).

Invariant produit affirmé partout : READONLY — aucun ordre possible
(disabled-by-design). Donnée absente → état vide honnête avec action.
"""
from __future__ import annotations

from vertex.app.config import AUTH_ON
from vertex.ui import vx2
from vertex.ui.shell import json_for_script, render_shell

# Les huit sous-vues de `navigation-and-pages.md` §12. Trois portaient deja
# leur contenu sous un autre nom — `automations` EST la vue des jobs,
# `settings` EST celle des preferences — et deux manquaient vraiment.
# Les cles d'URL historiques restent valables (voir `_ALIAS`).
VIEWS = (
    ('connections', 'Connexions'),
    ('data', 'Données'),
    ('jobs', 'Jobs'),
    ('alerts', 'Alertes techniques'),
    ('preferences', 'Préférences'),
    ('security', 'Sécurité'),
    ('archives', 'Archives'),
)
# Le Design System est une PAGE a lui, deja routee. Le contrat le range parmi
# les sous-vues de Systeme : il y figure comme onglet, et pointe vers elle —
# la dupliquer serait pire que l'y renvoyer.
_ONGLET_EXTERNE = ('/design-system', 'Design System')

# Une adresse partagee hier ne doit pas tomber ailleurs sans un mot.
_ALIAS = {'automations': 'jobs', 'settings': 'preferences', 'archive': 'archives'}
_DEFAULT_VIEW = 'connections'


# Ce que le contrat range dans « Alertes techniques » et que Vertex ne produit
# pas. On l'avoue ici plutôt que d'inventer un moteur dans un template.
_ABSENCES_ALERTES = (
    '<div class="vx2-strip">'
    + vx2.capacite_absente(
        quoi='Historique des alertes',
        pourquoi='Le serveur expose des compteurs cumulés depuis le démarrage, '
                 'pas un journal daté : Vertex ne conserve pas la suite des '
                 'alertes passées.')
    + vx2.capacite_absente(
        quoi='Seuils et règles d’escalade',
        pourquoi='Aucun moteur ne définit de seuil technique ni de politique '
                 'd’escalade ; les compteurs sont descriptifs.')
    + '</div>')

# L'engagement produit, écrit noir sur blanc là où on vient le vérifier.
_JAMAIS = (
    '<ul class="vx2-jamais">'
    '<li>Vertex ne transmet <b>aucun ordre</b>, ni en réel ni en simulé.</li>'
    '<li>Le lien courtier est ouvert en <b>lecture seule</b> ; aucun chemin '
    'd’exécution n’existe dans le code servi.</li>'
    '<li>Aucune valeur de clé ni de secret ne transite par l’interface — '
    'seul leur <b>statut</b> est affiché.</li>'
    '<li>Aucune donnée financière n’est inventée : une donnée absente reste '
    'absente.</li>'
    '<li>Les préférences d’affichage restent <b>locales à ce navigateur</b> ; '
    'elles ne touchent ni les moteurs ni le desk.</li>'
    '</ul>')


def _lock_card(auth_on: bool) -> str:
    """Carte « Verrou d'accès » (vue Connexions) — l'état RÉEL du verrou.

    Seul bouton de verrouillage atteignable de l'UI : l'ancien vivait dans
    la page Paramètres héritée, jamais routée.

    ## Le défaut corrigé le 25 août 2026

    Sans code, cette carte affirmait : « par sécurité, le serveur n'écoute que
    **127.0.0.1** (pas d'accès WiFi/LAN) ». C'était **faux** dès que
    `VERTEX_LAN=1` ou `PORT` était posé — deux cas où il n'y a ni code ni
    restriction. **L'écran de sécurité affirmait une protection absente**, à
    propos du portefeuille réel de l'utilisateur.

    La phrase n'était dérivée de rien : elle décrivait une intention. Elle vient
    désormais de `vertex/app/exposition.py`, le même calcul que celui qui décide
    réellement de l'écoute.
    """
    from vertex.app.exposition import exposition as _exposition

    etat = _exposition(auth_on)
    if auth_on:
        body = ('<div class="vx-help vx-mb2">Code d&#8217;entr&eacute;e exig&eacute; sur tous les appareils '
                '&mdash; session sign&eacute;e 30 jours, anti-force-brute, comparaison &agrave; temps constant.</div>'
                '<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/logout" id="vx-lock-btn">'
                '&#128275; Se d&eacute;connecter &amp; verrouiller cet appareil</a>')
        badge = '<span class="vx-badge" id="vx-lock-badge">actif</span>'
    elif etat['expose_sans_code']:
        #  LE cas que la carte niait. Il est dit en toutes lettres, avec la
        #  raison exacte de l'ouverture — sans quoi l'utilisateur cherche une
        #  variable qui n'est pas la sienne.
        cause = ('la variable <b>VERTEX_LAN=1</b>' if etat['motif'] == 'VERTEX_LAN'
                 else 'la variable <b>PORT</b> (h&eacute;bergeur)')
        body = ('<div class="vx-insight" data-tone="risk"><b>Aucun code, et le desk est '
                'joignable depuis le r&eacute;seau.</b> Le serveur &eacute;coute sur '
                '<b>0.0.0.0</b> &mdash; toutes les interfaces &mdash; &agrave; cause de '
                + cause + '. Toute personne sur ce r&eacute;seau peut lire le portefeuille, '
                'les positions et le journal.</div>'
                '<div class="vx-help vx-mt2">Pour prot&eacute;ger l&#8217;acc&egrave;s : d&eacute;finir '
                '<b>VERTEX_CODE</b> dans <b>.env</b> &mdash; voir SECURITE.md. '
                'Pour refermer compl&egrave;tement : retirer '
                + ('<b>VERTEX_LAN</b>' if etat['motif'] == 'VERTEX_LAN' else '<b>PORT</b>')
                + ' et red&eacute;marrer.</div>')
        badge = '<span class="vx-badge" data-tone="warn" id="vx-lock-badge">expos&eacute; sans code</span>'
    else:
        body = ('<div class="vx-help">Aucun code d&#8217;entr&eacute;e d&eacute;fini &mdash; le serveur '
                '&eacute;coute uniquement <b>127.0.0.1</b>, donc le desk n&#8217;est joignable que '
                'depuis cette machine. Pour prot&eacute;ger et ouvrir l&#8217;acc&egrave;s '
                '(iPhone, tablette) : d&eacute;finir <b>VERTEX_CODE</b> dans <b>.env</b> '
                '&mdash; voir SECURITE.md.</div>')
        badge = '<span class="vx-badge" id="vx-lock-badge">inactif</span>'
    return ('<div class="vx-grid vx-mt4"><section class="vx-card vx-col-12" aria-label="Verrou d&#8217;acc&egrave;s">'
            '<div class="vx-card-header"><span class="vx-card-title">Verrou d&#8217;acc&egrave;s</span>'
            + badge + '</div>' + body + '</section></div>')


def _tabs(active: str) -> str:
    """Les sept sous-vues, plus le Design System qui pointe vers sa page.

    L'onglet Design System portait `color:var(--vx-copper-light)` en style
    en ligne — un jeton de la palette Obsidian Copper abandonnée, qui ne se
    résout plus. Il prend l'apparence commune : rien ne justifie qu'un onglet
    se distingue par une couleur que la palette ne connaît pas.
    """
    items = [{'label': label, 'href': f'?view={vid}', 'actif': vid == active}
             for vid, label in VIEWS]
    href, label = _ONGLET_EXTERNE
    items.append({'label': label, 'href': href, 'actif': False,
                  'attrs': ' title="Référence visuelle — page dédiée"'})
    return vx2.tabs(items, libelle='Sous-vues du Système')


def _header(active: str) -> str:
    return (
        vx2.page_header(
            surtitre='Utilitaire', titre='Système',
            question='Vertex est-il sain, alimenté et correctement configuré ?')
        + vx2.context_bar([
            {'label': 'Invariant', 'contenu':
                '<span class="vx-readonly-shield" id="vx-readonly-invariant">'
                '<b>READONLY</b> · analyse uniquement '
                '<span id="vx-readonly-confirm" class="vx-meta"></span></span>'},
            {'label': 'Portée', 'contenu':
                '<span class="vx2-stamp">Santé, sources, tâches et préférences '
                '— <b>aucune donnée de marché</b></span>'},
            {'label': 'Santé globale', 'contenu':
                '<span id="vx-sys-ctx-sante">'
                + vx2.badge_etat('missing', texte='Lecture…') + '</span>'},
        ])
        + _tabs(active))


_VIEW_CONTENT = {
    'connections': '''
<section class="vx-card vx-card--hero vx-page-lead vx-mt4" id="vx-sys-hero" aria-label="Verdict technique">
  <div class="vx-skeleton" style="height:64px"></div>
</section>
<section class="vx-card vx-mt4" id="vx-conn-summary" aria-label="Matrice consolidée des connexions">
  <div class="vx-card-header"><span class="vx-card-title">Matrice consolid&eacute;e des connexions</span>
    <span class="vx-dim" style="font-size:12px">configur&eacute; &ne; connect&eacute; &middot; jamais LIVE sans preuve</span></div>
  <div id="vx-conn-summary-body">%%LOADING%%</div>
</section>
<div class="vx-hero-grid vx-mt4">
  <div class="vx-kpi-strip" id="vx-sys-kpis" data-max-kpis="4" aria-label="Quatre indicateurs de confiance"><div class="vx-skeleton" style="height:70px"></div></div>
  <aside class="vx-insight-rail" aria-label="Santé du système">
    <section class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Santé — moteurs</span>
        <span class="vx-chart-question">Les moteurs tournent-ils ?</span></div>
      <div id="vx-sys-gauge"><div class="vx-skeleton" style="height:118px"></div></div>
      <div class="vx-card-footer"><span class="vx-meta">% de moteurs au statut « ok » — donnée réelle, aucun score inventé.</span></div></section>
  </aside>
</div>
<details class="vx-disclosure vx-mt4" id="vx-conn-details">
  <summary>D&eacute;tails des int&eacute;grations, du stockage et des moteurs</summary>
  <div class="vx-disclosure__body vx-section-stack">
    <div class="vx-grid" id="vx-conn-grid">
      <section class="vx-card vx-col-4" aria-label="IBKR">
        <div class="vx-card-header"><span class="vx-card-title">IBKR</span><span id="vx-conn-ibkr-badge"></span></div>
        <div id="vx-conn-ibkr">%%LOADING%%</div>
      </section>
      <section class="vx-card vx-col-4" aria-label="Requ&ecirc;tes options">
        <div class="vx-card-header"><span class="vx-card-title">Requ&ecirc;tes options</span><span id="vx-strikes-badge"></span></div>
        <div id="vx-strikes">%%LOADING%%</div>
      </section>
      <section class="vx-card vx-col-4" aria-label="TradingView">
        <div class="vx-card-header"><span class="vx-card-title">TradingView</span><span id="vx-conn-tv-badge"></span></div>
        <div id="vx-conn-tv">%%LOADING%%</div>
      </section>
      <section class="vx-card vx-col-4" aria-label="Claude (IA)">
        <div class="vx-card-header"><span class="vx-card-title">Claude (IA)</span><span id="vx-conn-ai-badge"></span></div>
        <div id="vx-conn-ai">%%LOADING%%</div>
      </section>
    </div>
    <section class="vx-card" aria-label="Cerveau Claude — enrichissement web">
      <div class="vx-card-header"><span class="vx-card-title">Cerveau Claude &middot; donn&eacute;es web sourc&eacute;es</span>
        <span class="vx-actions"><span id="vx-brain-badge"></span>
          <button class="vx-btn vx-btn-sm vx-btn-primary" id="vx-brain-refresh">Mettre &agrave; jour avec Claude</button></span></div>
      <div class="vx-help vx-mb2">Cotations diff&eacute;r&eacute;es et actualit&eacute;s restent sourc&eacute;es, &eacute;tiquet&eacute;es et ne sont jamais pr&eacute;sent&eacute;es comme une donn&eacute;e broker live.</div>
      <div id="vx-brain-body">%%LOADING%%</div>
    </section>
    <div class="vx-hero-grid">
      <section class="vx-card" aria-label="Synchronisation">
        <div class="vx-card-header"><span class="vx-card-title">Synchronisation</span><span id="vx-conn-sync-badge"></span></div>
        <div id="vx-conn-sync">%%LOADING%%</div>
      </section>
      <section class="vx-card" aria-label="Stockage">
        <div class="vx-card-header"><span class="vx-card-title">Stockage &amp; sant&eacute;</span><span id="vx-conn-store-badge"></span></div>
        <div id="vx-conn-store">%%LOADING%%</div>
      </section>
    </div>
    %%LOCKCARD%%
    <section class="vx-card" aria-label="Moteurs">
      <div class="vx-card-header"><span class="vx-card-title">Moteurs</span><span class="vx-actions" id="vx-conn-meta"></span></div>
      <div id="vx-conn-engines">%%LOADING%%</div>
    </section>
  </div>
</details>''',

    'data': '''
<div class="vx-page-lead vx-mt4">
  <div><h2>Donn&eacute;es exploitables</h2><div class="vx-sub">Qualit&eacute;, fra&icirc;cheur et exceptions qui peuvent limiter une d&eacute;cision.</div></div>
  <div class="vx-toolbar"><button class="vx-btn vx-btn-sm vx-btn-primary" id="vx-data-refresh">Actualiser</button></div>
</div>
<div class="vx-hero-grid vx-mt4">
  <div id="vx-data-quality-chart"></div>
  <section class="vx-card" aria-label="Fra&icirc;cheur par domaine">
    <div class="vx-card-header"><span class="vx-card-title">Fra&icirc;cheur par domaine</span>
      <span class="vx-actions" id="vx-data-fresh-meta"></span></div>
    <div id="vx-data-fresh">%%LOADING%%</div>
  </section>
</div>
<div class="vx-section-stack vx-mt4">
  <section class="vx-card" aria-label="Titres d&eacute;grad&eacute;s">
    <div class="vx-card-header"><span class="vx-card-title">Titres en qualit&eacute; d&eacute;grad&eacute;e</span></div>
    <div id="vx-data-degraded">%%LOADING%%</div>
  </section>
  <details class="vx-disclosure" id="vx-data-diagnostics">
    <summary>Diagnostics avanc&eacute;s &middot; scan et continuit&eacute;</summary>
    <div class="vx-disclosure__body vx-section-stack">
      <section class="vx-card" aria-label="Dernier scan">
        <div class="vx-card-header"><span class="vx-card-title">Dernier scan &amp; m&eacute;triques</span></div>
        <div id="vx-data-scan">%%LOADING%%</div>
      </section>
      <section class="vx-card" aria-label="Continuit&eacute;">
        <div class="vx-card-header"><span class="vx-card-title">Continuit&eacute; &middot; navigation et donn&eacute;es</span>
          <span class="vx-actions vx-meta">Session applicative continue (client)</span></div>
        <div id="vx-continuity">%%LOADING%%</div>
      </section>
    </div>
  </details>
</div>''',

    'jobs': '''
<div class="vx-page-lead vx-mt4"><div><h2>Automatisations</h2><div class="vx-sub">Ce qui tourne, ce qui d&eacute;marre et ce qui reste &agrave; configurer.</div></div></div>
<div class="vx-hero-grid vx-mt4">
  <section class="vx-card vx-col-7" aria-label="Jobs de fond">
    <div class="vx-card-header"><span class="vx-card-title">T&acirc;ches en arri&egrave;re-plan</span>
      <span class="vx-meta vx-right">priorit&eacute; : positions &gt; stops &gt; options &gt; risques &gt; d&eacute;cisions &gt; univers</span></div>
    <div id="vx-auto-jobs">%%LOADING%%</div>
  </section>
  <section class="vx-card vx-col-5" aria-label="Rapport de d&eacute;marrage">
    <div class="vx-card-header"><span class="vx-card-title">D&eacute;marrage</span></div>
    <div id="vx-auto-startup">%%LOADING%%</div>
  </section>
</div>
<details class="vx-disclosure vx-mt4" id="vx-auto-configuration">
  <summary>Configuration &middot; statuts uniquement</summary>
  <div class="vx-disclosure__body"><div id="vx-auto-config">%%LOADING%%</div></div>
</details>
''',
    'preferences': '''
<div class="vx-page-lead vx-mt4"><div><h2>R&eacute;glages essentiels</h2><div class="vx-sub">Pr&eacute;f&eacute;rences locales de cet appareil.</div></div></div>
<div class="vx-section-stack vx-mt4">
  <section class="vx-card" aria-label="Affichage">
    <div class="vx-card-header"><span class="vx-card-title">Affichage</span></div>
    <div class="vx-kv"><span class="k">Densit&eacute;</span><span class="v">
      <span class="vx-segmented" role="group" aria-label="Densit&eacute;">
        <button data-density-btn="compact" aria-pressed="false">Compact</button>
        <button data-density-btn="confort" aria-pressed="true">Confort</button>
        <button data-density-btn="dense" aria-pressed="false">Dense</button>
      </span></span></div>
    <div class="vx-kv"><span class="k">Navigation lat&eacute;rale</span><span class="v">
      <span class="vx-segmented" role="group" aria-label="Sidebar">
        <button data-sidebar-btn="expanded" aria-pressed="false">D&eacute;ploy&eacute;e</button>
        <button data-sidebar-btn="collapsed" aria-pressed="false">R&eacute;duite</button>
      </span></span></div>
    <div class="vx-kv"><span class="k">Notifications push</span><span class="v">
      <span class="vx-segmented" role="group" aria-label="Notifications">
        <button data-notif-btn="1" aria-pressed="false">Activ&eacute;es</button>
        <button data-notif-btn="0" aria-pressed="false">Coup&eacute;es</button>
      </span></span></div>
    <div class="vx-kv"><span class="k">Langue</span>
      <span class="v">Fran&ccedil;ais <span class="vx-meta">(interface FR uniquement pour l&#8217;instant)</span></span></div>
    <div class="vx-help vx-mt2">Pr&eacute;f&eacute;rences purement locales (localStorage de ce navigateur) —
      elles ne touchent ni les moteurs ni les donn&eacute;es desk.</div>
  </section>
  <details class="vx-disclosure" id="vx-settings-advanced">
    <summary>Avanc&eacute; &middot; sauvegarde, application et r&eacute;f&eacute;rence visuelle</summary>
    <div class="vx-disclosure__body vx-section-stack">
      <section class="vx-card" aria-label="Donn&eacute;es desk">
        <div class="vx-card-header"><span class="vx-card-title">Sauvegarde desk</span></div>
        <div id="vx-settings-desk">%%LOADING%%</div>
        <div class="vx-toolbar vx-mt3">
          <button class="vx-btn vx-btn-primary" id="vx-desk-export">Exporter (JSON)</button>
          <label class="vx-btn" for="vx-desk-import-file" style="cursor:pointer">Importer un JSON&hellip;</label>
          <input type="file" id="vx-desk-import-file" accept="application/json,.json" hidden />
        </div>
        <div class="vx-help vx-mt2">L&#8217;import demande confirmation ; aucune cl&eacute; n&#8217;est renomm&eacute;e et le protocole de synchronisation reste intact.</div>
      </section>
      <section class="vx-card" aria-label="Application">
        <div class="vx-card-header"><span class="vx-card-title">Application</span><span class="vx-badge" id="vx-app-shell-badge"></span></div>
        <div id="vx-app-info">%%LOADING%%</div>
        <div class="vx-toolbar vx-mt3"><button class="vx-btn vx-btn-primary" id="vx-app-update">Forcer la mise &agrave; jour de l&#8217;app</button></div>
        <div class="vx-help vx-mt2">Recharge le shell hors ligne. <b>Aucune donn&eacute;e desk n&#8217;est touch&eacute;e</b>.</div>
      </section>
      <section class="vx-card" aria-label="Référence visuelle">
        <div class="vx-card-header"><span class="vx-card-title">R&eacute;f&eacute;rence visuelle</span></div>
        <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/design-system">Ouvrir le Design System &rarr;</a>
      </section>
    </div>
  </details>
</div>''',

    'alerts': '''
<div class="vx2-section"><div class="vx2-section-head">
  <h2 class="vx2-section-title">Alertes techniques</h2>
  <span class="vx2-section-note">ce qui a &eacute;chou&eacute;, ce qui a &eacute;t&eacute; &eacute;touff&eacute;, et pourquoi</span></div></div>
<div class="vx-grid vx-mt3">
  <div class="vx-col-12" id="vx-alerts-kpis"><div class="vx-skeleton" style="height:80px"></div></div>
</div>
<div class="vx-hero-grid vx-mt4">
  <section class="vx-card" aria-label="Pannes en cours">
    <div class="vx-card-header"><span class="vx-card-title">Pannes en cours</span>
      <span class="vx-chart-question">Qu&#8217;est-ce qui emp&ecirc;che Vertex de d&eacute;cider&nbsp;?</span></div>
    <div id="vx-alerts-pannes">%%LOADING%%</div>
  </section>
  <aside class="vx-insight-rail" style="grid-template-columns:minmax(0,1fr)">
    <section class="vx-card" aria-label="Alertes de march&eacute;">
      <div class="vx-card-header"><span class="vx-card-title">Alertes de march&eacute;</span></div>
      <div id="vx-alerts-marche">%%LOADING%%</div>
    </section>
  </aside>
</div>
<div class="vx-mt4" id="vx-alerts-absences"></div>''',

    'security': '''
<div class="vx2-section"><div class="vx2-section-head">
  <h2 class="vx2-section-title">S&eacute;curit&eacute;</h2>
  <span class="vx2-section-note">l&#8217;invariant, l&#8217;exposition r&eacute;seau et les secrets &mdash; jamais leur valeur</span></div></div>
<div class="vx-grid vx-mt3">
  <div class="vx-col-12" id="vx-sec-invariant"><div class="vx-skeleton" style="height:90px"></div></div>
</div>
<div class="vx-mt4">%%LOCKCARD%%</div>
<section class="vx-card vx-mt4" aria-label="Secrets et cl&eacute;s">
  <div class="vx-card-header"><span class="vx-card-title">Secrets et cl&eacute;s</span>
    <span class="vx-chart-question">Lesquels sont pos&eacute;s, et que se passe-t-il sans eux&nbsp;?</span></div>
  <div class="vx2-banner" data-kind="prudence" role="status"><span>Seul le <b>statut</b> est
    affich&eacute;. Aucune valeur, aucun fragment de cl&eacute; ne transite jamais par cette page.</span></div>
  <div id="vx-sec-config" class="vx-mt3">%%LOADING%%</div>
</section>
<section class="vx-card vx-mt4" aria-label="Ce que Vertex ne fait pas">
  <div class="vx-card-header"><span class="vx-card-title">Ce que Vertex ne fait pas</span></div>
  <div id="vx-sec-jamais"></div>
</section>''',

    'archives': '''
<div class="vx-grid vx-mt4">
  <section class="vx-card vx-col-12" aria-label="Coffre — archive">
    <div class="vx-card-header"><span class="vx-card-title">Coffre (archive interne)</span>
      <span class="vx-actions">
        <button class="vx-btn vx-btn-sm" id="vx-vault-new">Nouvelle entr&eacute;e</button>
        <button class="vx-btn vx-btn-sm vx-btn-ghost" id="vx-vault-export">Exporter (JSON)</button></span></div>
    <div class="vx-flex vx-wrap vx-gap2 vx-mb3">
      <input class="vx-input" id="vx-vault-search" type="search"
        placeholder="Recherche plein texte (titre, contenu, tags)"
        aria-label="Rechercher dans le coffre" style="max-width:340px"
        data-filter-key="q" />
      <span id="vx-vault-chips" role="group" aria-label="Filtrer par type"
        class="vx-flex vx-wrap vx-gap2"></span>
    </div>
    <div id="vx-vault-list">%%LOADING%%</div>
  </section>
</div>''',
}


_JS = r"""
<script src="/static/vertex/js/charts/donut-chart.js" defer></script>
<script src="/static/vertex/js/charts/bar-chart.js" defer></script>
<script>
(function(){
'use strict';
const $=(id)=>document.getElementById(id);
const E=()=>window.VXEntities;
const ROOT=document.getElementById('vx-system');
const VIEW=(ROOT&&ROOT.dataset.view)||'connections';
function esc(s){return String(s??'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));}
function whenChartsReady(fn){
  if(window.VXCharts&&window.Chart)return fn();
  window.addEventListener('load',fn,{once:true});
}
function statusBadge(status,label){
  return `<span class="vx-badge vx-badge-status" data-status="${esc(status)}">${esc(label||status)}</span>`;
}
function kv(k,v){return `<div class="vx-kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;}

/* Bandeau consolidé des canaux — /api/system/connections (statuts canoniques). */
async function loadConnSummary(){
  const el=document.getElementById('vx-conn-summary-body');if(!el)return;
  let d;try{d=await VX.fetch('/api/system/connections',{ttl:20000});}catch(e){el.innerHTML=VX.states.error('Connexions indisponibles');return;}
  const tone={LIVE:'pos',READY:'pos',DELAYED:'warn',DEGRADED:'warn',FALLBACK:'warn',STALE:'warn',
    OFFLINE:'neg',ERROR:'neg',BLOCKED:'neg',CONFIGURATION_MISSING:'neutral',NOT_IMPLEMENTED:'neutral',DEMO:'neutral',LOADING:'neutral'};
  const statusLabel={LIVE:'Direct',READY:'Prêt',DELAYED:'Différé',DEGRADED:'Dégradé',
    FALLBACK:'Secours',STALE:'Périmé',OFFLINE:'Hors ligne',ERROR:'Erreur',BLOCKED:'Bloqué',
    CONFIGURATION_MISSING:'À configurer',NOT_IMPLEMENTED:'Non disponible',DEMO:'Démo',LOADING:'Chargement'};
  const col={pos:'var(--vx-positive,#2BBE90)',warn:'var(--vx-warning,#D9BE3C)',neg:'var(--vx-negative,#E9555F)',neutral:'var(--vx-text-muted,#989092)'};
  const rows=(d.connections||[]).map(function(c){
    const t=tone[c.status]||'neutral';
    /* LOT 126 : la colonne du badge s'adapte au statut (max-content) — fini
       CONFIGURATION_MISSING qui debordait sur le texte voisin. */
    return '<div class="vx-connection-row">'
      +'<b class="vx-connection-name">'+esc(c.name)+'</b>'
      +'<span class="vx-badge vx-connection-status" title="Statut technique : '+esc(c.status)+'" style="color:'+col[t]+';border-color:'+col[t]+'">'+esc(statusLabel[c.status]||c.status)+'</span>'
      +'<span class="vx-dim vx-connection-detail">'+esc(c.detail||'')+(c.action?' <span class="vx-connection-action">→ '+esc(c.action)+'</span>':'')+'</span></div>';
  }).join('');
  el.innerHTML=rows||'<div class="vx-empty">Aucun canal.</div>';
}

/* Cerveau Claude+web — /api/ai/status + /api/ai/enrichment (provenance honnête). */
const BRAIN_TONE={OK:['live','à jour'],DEGRADED:['delayed','partiel'],
  MISSING:['frozen','indisponible'],EMPTY:['frozen','jamais lancé']};
function brainCitations(cits){
  if(!cits||!cits.length)return '';
  return '<div class="vx-flex vx-wrap vx-gap2" style="margin-top:.2rem">'
    +cits.slice(0,4).map(c=>`<a class="vx-badge vx-badge-ghost" href="${esc(c.url)}" target="_blank" rel="noopener noreferrer"
       style="font-size:11px" title="${esc(c.url)}">↗ ${esc((c.title||c.url).slice(0,42))}</a>`).join('')+'</div>';
}
async function loadBrain(){
  const body=$('vx-brain-body');if(!body)return;
  let st,snap;
  try{
    [st,snap]=await Promise.all([
      VX.fetch('/api/ai/status',{ttl:8000}),
      VX.fetch('/api/ai/enrichment',{ttl:8000})]);
  }catch(e){body.innerHTML=VX.states.error('Cerveau Claude injoignable');return;}
  const status=(st&&st.status)||'EMPTY';
  const tn=BRAIN_TONE[status]||['frozen','—'];
  ($('vx-brain-badge')||{}).innerHTML=statusBadge(tn[0],tn[1]);
  const quotes=(snap&&snap.surfaces&&snap.surfaces.quotes)||{};
  const news=(snap&&snap.surfaces&&snap.surfaces.news)||{};
  const found=st&&st.quotes_found!=null?st.quotes_found:0;
  let head=kv('&Eacute;tat',statusBadge(tn[0],status)+' <span class="vx-dim" style="font-size:12px">'+esc((st&&st.note)||'')+'</span>')
    +kv('Mod&egrave;le',esc((st&&st.model)||'—'))
    +kv('Derni&egrave;re analyse',(snap&&snap.as_of)?VX.fmt.ago(Date.parse(snap.as_of)):'&mdash;')
    +kv('Cotations trouv&eacute;es (recherche web)',VX.fmt.nd(found)+' / '+VX.fmt.nd((st&&st.symbols)||0)+' <span class="vx-dim" style="font-size:12px">(non canoniques &mdash; le prix du scan fait foi, &eacute;cart servi)</span>');
  const syms=Object.keys(quotes).filter(s=>quotes[s]&&quotes[s].value!=null).slice(0,12);
  /* Plus forts mouvements du jour (change_pct réel déjà servi) en barres signées — au-dessus
     du tableau texte. Émeraude/corail par signe (hex, Chart.js ne résout pas var(--x)). */
  const movers=Object.keys(quotes).filter(s=>quotes[s]&&quotes[s].change_pct!=null)
    .sort((a,b)=>Math.abs(quotes[b].change_pct)-Math.abs(quotes[a].change_pct)).slice(0,8);
  let table='';
  if(syms.length){
    table='<div class="vx-divider"></div><div style="overflow-x:auto"><table class="vx-table">'
      +'<thead><tr><th>Titre</th><th class="vx-num">Prix web (Claude)</th><th class="vx-num">Prix du scan (canonique)</th><th class="vx-num">&Eacute;cart</th><th>Provenance</th><th>Actualit&eacute;</th></tr></thead><tbody>'
      +syms.map(s=>{
        const q=quotes[s];const n=news[s]&&news[s].value&&news[s].value[0];
        const chg=q.change_pct!=null?(' <span class="'+(q.change_pct>=0?'vx-pos':'vx-neg')+'">'+(q.change_pct>=0?'+':'')+VX.fmt.num(q.change_pct,2)+'%</span>'):'';
        const impactCls=n?({HAUSSIER:'vx-pos',BAISSIER:'vx-neg',NEUTRE:'vx-dim'}[n.impact]||'vx-dim'):'';
        return '<tr><td><b>'+esc(s)+'</b></td>'
          +'<td class="vx-num vx-mono">'+VX.fmt.num(q.value,2)+' '+esc(q.currency||'')+chg+'</td>'
          +'<td class="vx-num vx-mono">'+(q.scan_price!=null?VX.fmt.num(q.scan_price,2):'<span class="vx-dim">hors scan</span>')+'</td>'
          +'<td class="vx-num vx-mono '+(q.ecart_pct==null?'vx-dim':Math.abs(q.ecart_pct)>1?'vx-neg':'vx-pos')+'">'+(q.ecart_pct!=null?((q.ecart_pct>=0?'+':'')+VX.fmt.num(q.ecart_pct,2)+' %'):'n/d')+'</td>'
          +'<td><span class="vx-badge" style="color:var(--vx-warning,#D9BE3C);border:1px solid var(--vx-warning,#D9BE3C);font-size:11px">'+esc(q.source_label||'via Claude · web')+'</span>'+brainCitations(q.citations)+'</td>'
          +'<td class="'+impactCls+'" style="font-size:12px">'+(n?esc(n.impact)+' — '+esc((n.headline||'').slice(0,64)):'<span class="vx-dim">—</span>')+'</td></tr>';
      }).join('')+'</tbody></table></div>';
  }else if(status==='MISSING'){
    table='<div class="vx-insight vx-mt2" data-tone="neutral">Analyse Claude+web <b>indisponible</b> — ajoute '
      +'<span class="vx-mono">ANTHROPIC_API_KEY</span> dans <span class="vx-mono">.env</span> pour activer le cerveau. '
      +'En attendant, l&#8217;app sert les donn&eacute;es r&eacute;elles/moteur uniquement (aucun chiffre invent&eacute;).</div>';
  }else{
    table='<div class="vx-empty vx-mt2">Aucune cotation web pour l&#8217;instant. « Mettre &agrave; jour avec Claude » pour lancer une recherche.</div>';
  }
  body.innerHTML=head+(movers.length?'<div id="vx-brain-movers" class="vx-mt3"></div>':'')+table
    +'<div class="vx-card-footer">'+VX.updateIndicator((snap&&snap.as_of)?Date.parse(snap.as_of):null,'/api/ai/enrichment',status==='OK'?'delayed':'fallback')
    +' · rendements/prix 100% diff&eacute;r&eacute;s &mdash; jamais un ordre</div>';
  if(window.VXCharts&&VXCharts.barCard&&movers.length){
    VXCharts.barCard('vx-brain-movers',{title:'Plus forts mouvements du jour',unit:'%',
      question:'Quels titres bougent le plus aujourd&rsquo;hui&nbsp;?',source:'SCAN',
      labels:movers,values:movers.map(s=>quotes[s].change_pct),
      colors:movers.map(s=>quotes[s].change_pct>=0?VXCharts.colors.positive:VXCharts.colors.negative),
      horizontal:true,yFmt:(v)=>v+'%',source:'via Claude · web',
      timestamp:(snap&&snap.as_of)?Date.parse(snap.as_of):null,mode:'delayed'});
  }
}
async function refreshBrain(){
  const btn=$('vx-brain-refresh');
  if(btn){btn.disabled=true;btn.textContent='Recherche Claude…';}
  try{
    const r=await fetch('/api/ai/refresh',{method:'POST'});
    const d=await r.json().catch(()=>({}));
    VX.toast(d.note||'Enrichissement Claude lancé', r.ok?'success':'error');
  }catch(e){VX.toast('Mise à jour impossible : '+e.message,'error');}
  /* Laisse le temps à la tâche de fond, puis rafraîchit l'affichage. */
  setTimeout(()=>{ if(btn){btn.disabled=false;btn.textContent='Mettre à jour avec Claude';} loadBrain(); }, 3500);
}

/* TradingView — liste globale des signaux récents (tous titres) + aide setup. */
const TV_BULL2=['SUPPORT_RECLAIM','BREAKOUT_CONFIRMED','BREAKOUT_RETEST','MOMENTUM_ACCELERATION','VOLUME_EXPANSION','TREND_ALIGNMENT'];
const TV_BEAR2=['FAILED_BREAKOUT','THESIS_INVALIDATION'];
function tvDirBadge(sig){
  const up=TV_BULL2.indexOf(sig)>=0,dn=TV_BEAR2.indexOf(sig)>=0;
  const c=up?'vx-pos':(dn?'vx-neg':'vx-dim'),t=up?'haussier':(dn?'baissier':'contextuel');
  return '<span class="vx-badge '+c+'" style="font-size:11px">'+t+'</span>';
}
async function loadTvSignals(){
  const host=$('vx-tv-signals');if(!host)return;
  let d;try{d=await VX.fetch('/api/tradingview/signals',{ttl:15000});}catch(e){host.innerHTML='';return;}
  const sigs=(d.signals||[]).slice().reverse();   // plus récent d'abord
  if(!sigs.length){host.innerHTML='<div class="vx-empty" style="margin-top:.6rem">Aucun signal reçu pour l\'instant — la liste se remplira à la première alerte TradingView.</div>';return;}
  host.innerHTML='<div class="vx-divider"></div><div class="vx-meta vx-mb1">Signaux récents — tous titres (plus récent d\'abord)</div>'
    +'<div style="overflow-x:auto"><table class="vx-table"><thead><tr><th>Titre</th><th>Signal</th><th>Sens</th><th>Reçu</th><th></th></tr></thead><tbody>'
    +sigs.slice(0,20).map(function(s){
      return '<tr><td><b>'+esc(s.symbol)+'</b></td><td class="vx-mono" style="font-size:12px">'+esc(s.signal)+'</td>'
        +'<td>'+tvDirBadge(s.signal)+'</td>'
        +'<td class="vx-meta">'+VX.fmt.ago((s.received_ts||0)*1000)+(s.fresh===false?' <span class="vx-badge">rassis</span>':'')+'</td>'
        +'<td><a class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" href="/analysis/'+esc(s.symbol)+'">Analyser →</a></td></tr>';
    }).join('')+'</tbody></table></div>';
}
function openTvSetup(){
  const origin=location.origin;
  const url=origin+'/api/tradingview/webhook';
  const codes=['SUPPORT_RECLAIM','BREAKOUT_CONFIRMED','BREAKOUT_RETEST','MOMENTUM_ACCELERATION',
    'VOLUME_EXPANSION','VOLATILITY_COMPRESSION','VOLATILITY_EXPANSION','TREND_ALIGNMENT',
    'CORRECTION_DEEP','FAILED_BREAKOUT','THESIS_INVALIDATION'];
  const payload='{\n  "secret": "TON_SECRET",\n  "symbol": "{{ticker}}",\n  "signal": "BREAKOUT_CONFIRMED",\n  "timestamp": {{timenow}},\n  "price": {{close}}\n}';
  VX.shell.openDrawer('Configurer ton alerte TradingView',
    '<div class="vx-help">Une alerte TradingView pointée ici déclenche une <b>réévaluation</b> Vertex — <b>jamais un ordre</b>. Suis ces 4 étapes.</div>'
    +'<ol style="padding-left:1.1rem;line-height:1.9;font-size:13px">'
    +'<li>Dans <span class="vx-mono">.env</span>, définis <span class="vx-mono">TRADINGVIEW_WEBHOOK_SECRET</span> (un mot de passe à toi) puis relance Vertex.</li>'
    +'<li>Sur TradingView : <b>Créer une alerte</b> → onglet <b>Notifications</b> → coche <b>Webhook URL</b> et colle :</li></ol>'
    +'<div class="vx-kv"><span class="k">URL webhook</span><span class="v"><code class="vx-mono" style="font-size:12px">'+esc(url)+'</code> '
    +'<button class="vx-btn vx-btn-sm" id="vx-tv-copy-url">Copier</button></span></div>'
    +'<ol start="3" style="padding-left:1.1rem;line-height:1.9;font-size:13px">'
    +'<li>Dans le <b>message</b> de l\'alerte, colle ce corps JSON (remplace <span class="vx-mono">TON_SECRET</span> par ton secret) :</li></ol>'
    +'<pre class="vx-mono" style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:12px;overflow-x:auto;font-size:12px">'+esc(payload)+'</pre>'
    +'<button class="vx-btn vx-btn-sm vx-mb2" id="vx-tv-copy-payload">Copier le corps JSON</button>'
    +'<ol start="4" style="padding-left:1.1rem;line-height:1.9;font-size:13px">'
    +'<li>Change <span class="vx-mono">"signal"</span> selon ton alerte. Codes acceptés :</li></ol>'
    +'<div class="vx-flex vx-wrap vx-gap2">'+codes.map(function(c){return '<span class="vx-badge vx-mono" style="font-size:11px">'+c+'</span>';}).join('')+'</div>'
    +'<div class="vx-help vx-mt3">Astuce : le script Pine prêt à l\'emploi est dans <span class="vx-mono">tradingview/vertex_signals.pine</span> — il émet déjà ce JSON avec les bons codes.</div>');
  document.getElementById('vx-tv-copy-url')?.addEventListener('click',function(){navigator.clipboard&&navigator.clipboard.writeText(url);VX.toast('URL webhook copiée','success');});
  document.getElementById('vx-tv-copy-payload')?.addEventListener('click',function(){navigator.clipboard&&navigator.clipboard.writeText(payload);VX.toast('Corps JSON copié','success');});
}

/* ══ Vue CONNEXIONS ═════════════════════════════════════════════════ */
async function loadConnections(){
  loadConnSummary();
  loadBrain();
  const [stR,liveR,diagR,hzR]=await Promise.allSettled([
    VX.fetch('/api/system-status',{ttl:30000}),
    VX.fetch('/api/live/status',{ttl:30000}),
    VX.fetch('/api/system/diagnostics',{ttl:30000}),
    VX.fetch('/healthz',{ttl:30000})]);
  const st=stR.status==='fulfilled'?stR.value:null;
  const live=liveR.status==='fulfilled'?liveR.value:null;
  const diag=diagR.status==='fulfilled'?diagR.value:null;
  const hz=hzR.status==='fulfilled'?hzR.value:null;

  /* Hero santé (jauge % moteurs ok) + bande KPI command center — §41.
     Agrégations RÉELLES des payloads (statuts moteurs, fraîcheur, warnings,
     scan, IA) ; aucun chiffre inventé, jamais 0 pour une valeur absente. */
  try{
    var _eng=(st&&st.engines)||[];
    var _ok=_eng.filter(function(e){return e&&e.status==='ok';}).length;
    var _fr=(st&&st.freshness)||{}, _frK=Object.keys(_fr);
    var _frOk=_frK.filter(function(k){return _fr[k]&&_fr[k].state==='fresh';}).length;
    var _warn=((st&&st.warnings)||[]).length;
    var _sym=(st&&st.scan&&st.scan.symbols); if(_sym==null&&diag&&diag.scan)_sym=diag.scan.rows;
    var _ai=(diag&&diag.ai)||{};
    var _pct=_eng.length?Math.round(_ok/_eng.length*100):null;
    /* Hero technique (§ « Puis-je faire confiance à Vertex aujourd'hui ? ») —
       synthèse honnête depuis les payloads réels ; aucun chiffre inventé. */
    try{
      var _delayed=_frK.length-_frOk;
      var _ib=String((st&&(st.data_sources||{}).ibkr)||'inconnu');
      var _ibTxt={'connected-live':['IBKR connecté · temps réel','pos'],
        'connected-delayed':['IBKR connecté · différé','warn'],
        'enabled-idle':['IBKR activé · aucune session confirmée','warn'],
        'disabled':['IBKR désactivé','muted'],'inconnu':['IBKR état inconnu','muted']}[_ib]||['IBKR état inconnu','muted'];
      var _demo=st&&st.mode&&String(st.mode).toLowerCase().indexOf('demo')>=0;
      var _headline,_tone;
      if(!_eng.length){_headline='État système en cours de lecture';_tone='muted';}
      else if(_warn>0||_ok<_eng.length){_headline='Système partiellement dégradé';_tone='warn';}
      else{_headline='Système opérationnel';_tone='pos';}
      var _ro=(st&&st.readonly&&st.analysis_only);
      var _line=[
        _ibTxt[0],
        (_delayed>0?(_delayed+' domaine(s) de données en différé/rassis'):(_frK.length?'toutes les données fraîches':'fraîcheur inconnue')),
        (_warn===0?'aucune erreur critique':(_warn+' avertissement(s) à revoir')),
        (_ro?'lecture seule confirmée (aucun ordre)':'lecture seule NON confirmée')
      ];
      var _hero=$('vx-sys-hero');
      if(_hero)_hero.innerHTML='<div class="vx-flex vx-wrap" style="justify-content:space-between;align-items:flex-start;gap:10px">'
        +'<div style="max-width:640px"><div class="vx-flex" style="gap:8px;align-items:center;margin-bottom:4px">'
        +'<span class="vx-eyebrow">Confiance données</span>'
        /*  La pastille rendait le MEME texte que le titre juste en dessous :
            « Systeme partiellement degrade » se lisait deux fois, l'un sous
            l'autre. Elle porte desormais l'ETAT — ce que le titre ne dit pas —
            et le titre garde le verdict. Chacun apporte quelque chose.  */
        +'<span class="vx-freshness" data-state="'+(_tone==='pos'?'live':_tone==='warn'?'delayed':'stale')+'">'
        +({pos:'toutes vertes',warn:'à revoir',muted:'lecture en cours'}[_tone]||'état inconnu')+'</span>'
        +(_demo?'<span class="vx-badge-demo">DÉMO</span>':'')+(_ro?'<span class="vx-badge vx-pos">READONLY</span>':'')+'</div>'
        +'<h2 style="margin:0 0 6px;font-size:21px" class="'+({pos:'vx-pos',warn:'vx-warn',muted:'vx-muted'}[_tone])+'">'+esc(_headline)+'</h2>'
        +'<p class="vx-dim" style="margin:0;font-size:13.5px;line-height:1.6">'+_line.map(esc).join(' · ')+'.</p></div>'
        +'<div class="vx-flex" style="gap:8px;flex-wrap:wrap">'
        +'<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/system?view=data">Fraîcheur par domaine →</a>'
        +'<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/system?view=automations">Diagnostics</a></div></div>';
    }catch(e){}
    whenChartsReady(function(){ if(window.VXCharts&&VXCharts.gauge) VXCharts.gauge('vx-sys-gauge',{
      value:_pct,min:0,max:100,unit:'%',label:'Moteurs OK',
      reading:_eng.length?(_ok+'/'+_eng.length+' moteurs opérationnels'):'moteurs inconnus',
      bands:[{to:60,color:VXCharts.colors.negative},{to:85,color:VXCharts.colors.warning},{to:100,color:VXCharts.colors.positive}]}); });
    var _kp=function(l,v,d,cls){return '<div class="vx-card vx-card--compact vx-kpi-card vx-kpi"><span class="vx-kpi-label">'+l+'</span><span class="vx-kpi-value '+(cls||'')+'" style="font-size:22px">'+v+'</span>'+(d?'<span class="vx-kpi-delta '+(cls||'vx-muted')+'">'+d+'</span>':'')+'</div>';};
    var _kh=$('vx-sys-kpis');
    if(_kh)_kh.innerHTML=
      _kp('Moteurs',_eng.length?(_ok+'/'+_eng.length):'—','opérationnels',(_eng.length&&_ok===_eng.length)?'vx-pos':'')
      +_kp('Données fraîches',_frK.length?(_frOk+'/'+_frK.length):'—','domaines')
      +_kp('Erreurs',_warn,_warn===0?'aucune':'à voir',_warn===0?'vx-pos':'vx-neg')
      +_kp('Lecture seule',(st&&st.readonly)?'✓':'⚠',(st&&st.readonly)?'aucun ordre':'à vérifier',(st&&st.readonly)?'vx-pos':'vx-neg');
  }catch(e){}

  /* Invariant READONLY confirmé par le serveur */
  if(st)($('vx-readonly-confirm')||{}).textContent=st.readonly&&st.analysis_only
    ?' · serveur confirmé · '+(st.order_execution||'disabled-by-design')
    :' · confirmation serveur absente';

  /* IBKR — honnête : connecté-live / connecté-différé / activé-inactif / désactivé */
  if(st){
    const ib=String((st.data_sources||{}).ibkr||'inconnu');
    const map={'connected-live':['live','connecté · temps réel (lecture seule)'],
      'connected-delayed':['delayed','connecté · différé (lecture seule)'],
      'enabled-idle':['frozen','activé · aucune session TWS confirmée'],
      'disabled':['offline','désactivé']};
    const m=map[ib]||['offline','inconnu'];
    const proven=ib==='connected-live'||ib==='connected-delayed';
    ($('vx-conn-ibkr-badge')||{}).innerHTML=statusBadge(m[0],m[1]);
    ($('vx-conn-ibkr')||{}).innerHTML=
      kv('&Eacute;tat',esc(m[1]))
      +(ib==='enabled-idle'?'<div class="vx-help vx-mt1 vx-mb1">Config présente mais <b>aucune preuve de session</b> — jamais affiché « connecté » sans tick réel. Ouvre TWS/Gateway (lecture seule).</div>':'')
      +kv('Donn&eacute;es march&eacute;',esc((st.data_sources||{}).market_data||'—'))
      +kv('Mode global',esc(st.mode||'—'))
      +kv('Ex&eacute;cution d&#8217;ordres','<b class="vx-neg">'+esc(st.order_execution||'disabled-by-design')+'</b>')
      +`<div class="vx-card-footer">${VX.updateIndicator(st.ts||null,'/api/system-status',proven?(ib==='connected-live'?'live':'delayed'):'fallback')}</div>`;
  }else{
    ($('vx-conn-ibkr')||{}).innerHTML=VX.states.error('&Eacute;tat syst&egrave;me indisponible');
    ($('vx-conn-ibkr-badge')||{}).innerHTML=statusBadge('offline','inconnu');
  }

  /* Requêtes options — le correctif est INVISIBLE par construction : il se voit
     dans ce qui N'ARRIVE PLUS. Mesuré le 25 août 2026 : le produit demandait au
     courtier des contrats inexistants (214 refus sur 250 lignes de journal,
     « tout sauf les multiples de 5 »). Sans ce compteur, l'observer exigerait de
     comparer deux journaux à la main — donc personne ne le ferait. */
  const sk=diag&&diag.option_strikes;
  if(sk){
    const pct=sk.part_evitee_pct;
    /* `null` = rien n'a encore été proposé. Afficher « 0 % » ferait passer
       « je n'ai pas mesuré » pour « je n'évite rien ». */
    const badge=pct==null?['frozen','aucune mesure encore']
      :(pct>0?['live',pct+' % évité']:['frozen','rien à éviter']);
    ($('vx-strikes-badge')||{}).innerHTML=statusBadge(badge[0],badge[1]);
    ($('vx-strikes')||{}).innerHTML=
      kv('Strikes demand&eacute;s',VX.fmt.nd(sk.strikes_proposes))
      +kv('&Eacute;vit&eacute;s (d&eacute;j&agrave; refus&eacute;s)',VX.fmt.nd(sk.strikes_evites)
          +(pct!=null?' <span class="vx-dim">('+pct+' %)</span>':''))
      +kv('Refus m&eacute;moris&eacute;s',VX.fmt.nd(sk.refus_retenus)
          +' <span class="vx-dim">sur '+VX.fmt.nd(sk.couples)+' couple(s) titre/&eacute;ch&eacute;ance</span>')
      +(sk.redemandes_faute_de_mieux
        ?kv('Redemand&eacute;s quand m&ecirc;me',VX.fmt.nd(sk.redemandes_faute_de_mieux)
            +' <span class="vx-dim">tout &eacute;tait connu refus&eacute; &mdash; on ne vide jamais la cha&icirc;ne en silence</span>')
        :'')
      +'<div class="vx-help vx-mt2">IBKR rend les strikes <b>toutes &eacute;ch&eacute;ances confondues</b>, mais son pas change avec l&#8217;&eacute;ch&eacute;ance. Ce qui a d&eacute;j&agrave; &eacute;t&eacute; refus&eacute; n&#8217;est plus redemand&eacute; &mdash; jamais un strike <b>invent&eacute;</b>.</div>'
      +`<div class="vx-card-footer">${VX.updateIndicator(Date.now(),'/api/system/diagnostics','delayed')}</div>`;
  }else{
    ($('vx-strikes')||{}).innerHTML=VX.states.empty('Aucune mesure de requ&ecirc;tes options &mdash; la rotation n&#8217;a pas encore interrog&eacute; le courtier.');
    ($('vx-strikes-badge')||{}).innerHTML=statusBadge('offline','n/d');
  }

  /* TradingView — état honnête : désactivé ≠ configuré-en-attente ≠ actif */
  const tv=diag&&diag.tradingview;
  if(tv){
    const stored=tv.stored??tv.count??0;
    const fresh=tv.fresh??0;
    /* state serveur : DISABLED (pas de secret) / WAITING (configuré, 0 signal frais) / ACTIVE */
    const state=tv.state||(tv.configured?(fresh>0?'ACTIVE':'WAITING'):'DISABLED');
    const badge={ACTIVE:['live','actif · '+fresh+' frais'],
      WAITING:['frozen','configuré · en attente'],
      DISABLED:['offline','webhook désactivé']}[state]||['offline','n/d'];
    ($('vx-conn-tv-badge')||{}).innerHTML=statusBadge(badge[0],badge[1]);
    ($('vx-conn-tv')||{}).innerHTML=
      kv('&Eacute;tat',state==='DISABLED'
        ?'<span class="vx-dim">secret webhook absent — 503 honn&ecirc;te, aucun signal invent&eacute;</span>'
        :(state==='ACTIVE'?'<span class="vx-pos">signaux re&ccedil;us</span>':'<span class="vx-dim">webhook pr&ecirc;t, aucun signal r&eacute;cent</span>'))
      +kv('Signaux stock&eacute;s',VX.fmt.nd(stored)+(fresh?' <span class="vx-dim">('+fresh+' frais)</span>':''))
      +(tv.newest_age_s!=null?kv('Dernier signal',VX.fmt.ago(Date.now()-tv.newest_age_s*1000)):'')
      +kv('R&ocirc;le','webhooks d&#8217;alertes TradingView — <b>r&eacute;&eacute;valuation</b>, jamais un ordre')
      +(state==='DISABLED'?'<div class="vx-help vx-mt2">Active-le : d&eacute;finis <span class="vx-mono">TRADINGVIEW_WEBHOOK_SECRET</span> dans <span class="vx-mono">.env</span>.</div>':'')
      +'<div class="vx-flex vx-wrap vx-gap2 vx-mt2"><button class="vx-btn vx-btn-sm vx-btn-primary" id="vx-tv-setup">Configurer mon alerte TradingView</button></div>'
      +'<div id="vx-tv-signals"></div>'
      +`<div class="vx-card-footer">${VX.updateIndicator(Date.now(),'/api/system/diagnostics',state==='ACTIVE'?'live':'delayed')}
        <a class="vx-btn vx-btn-sm vx-btn-ghost vx-right" href="/opportunities?view=radar">Voir le radar des signaux →</a></div>`;
    document.getElementById('vx-tv-setup')?.addEventListener('click',openTvSetup);
    loadTvSignals();
  }else{
    ($('vx-conn-tv')||{}).innerHTML=VX.states.empty('Aucun diagnostic TradingView disponible — le magasin de signaux n&#8217;a rien re&ccedil;u.',
      '<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities?view=radar">Voir le radar</a>');
    ($('vx-conn-tv-badge')||{}).innerHTML=statusBadge('offline','n/d');
  }

  /* Claude / IA */
  const ai=diag&&diag.ai;
  const aiSrc=st&&(st.data_sources||{}).ai;
  if(ai||aiSrc!==undefined){
    const ok=ai?(ai.ok??0):null,total=ai?(ai.total??0):null,fb=ai?(ai.fallbacks??0):null;
    const aiOn=String(aiSrc||'').indexOf('on')===0||String(aiSrc||'')==='enabled'||(ok!==null&&ok>0);
    ($('vx-conn-ai-badge')||{}).innerHTML=statusBadge(aiOn?'live':(fb?'fallback':'offline'),
      aiOn?'disponible':(fb?'mode secours':'indisponible'));
    ($('vx-conn-ai')||{}).innerHTML=
      kv('Source IA',esc(aiSrc??'—'))
      +(ai?kv('Appels r&eacute;ussis',VX.fmt.nd(ok)+' / '+VX.fmt.nd(total))
          +kv('Replis d&eacute;terministes',VX.fmt.nd(fb)):'')
      +kv('R&ocirc;le','<span class="vx-dim">explique et reformule — ne d&eacute;cide jamais</span>')
      +`<div class="vx-card-footer">${VX.updateIndicator(Date.now(),'/api/system/diagnostics',aiOn?'live':'fallback')}</div>`;
  }else{
    ($('vx-conn-ai')||{}).innerHTML=VX.states.empty('Audit IA indisponible — la synth&egrave;se d&eacute;terministe des moteurs reste servie.');
    ($('vx-conn-ai-badge')||{}).innerHTML=statusBadge('fallback','n/d');
  }

  /* Synchronisation (Live Engine) */
  if(live){
    const doms=live.domains||{};
    const names=Object.keys(doms);
    const freshCount=names.filter(k=>doms[k].fresh||['fresh','live','ok'].includes(doms[k].state)).length;
    const errs=(live.errors||[]);
    ($('vx-conn-sync-badge')||{}).innerHTML=statusBadge(
      errs.length?'delayed':(freshCount===names.length&&names.length?'live':'delayed'),
      freshCount+' / '+names.length+' domaines frais');
    const liveOn=live.mode==='live';
    const diagItem=(ok,title,detail)=>{
      const c=ok===true?'var(--vx-positive)':ok===false?'var(--vx-negative)':'var(--vx-warning)';
      const mark=ok===true?'✓':ok===false?'✕':'○';
      return `<div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:7px">`
        +`<span style="color:${c};font-weight:700;flex:0 0 auto">${mark}</span>`
        +`<div style="min-width:0"><div style="font-weight:600;color:var(--vx-text-secondary)">${title}</div>`
        +`<div class="vx-meta">${detail}</div></div></div>`;};
    ($('vx-conn-sync')||{}).innerHTML=
      kv('Mode',esc(live.mode||'—'))
      +kv('Derni&egrave;re synchro',VX.fmt.ago(live.last_refresh))
      +kv('Domaines',names.map(esc).join(', ')||'—')
      +(errs.length?`<div class="vx-error-banner vx-mt2">⚠ ${errs.map(e=>esc(e.domain+' : '+e.error)).join('<br>')}</div>`:'')
      +`<div class="vx-mt3" style="border-top:1px solid var(--vx-border-faint);padding-top:10px">`
      +`<div class="vx-meta" style="text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Passer en pleinement live — à vérifier côté ton compte IBKR</div>`
      +diagItem(liveOn,'TWS / IB Gateway ouvert + API activée','Édition → Paramètres → API : « Enable ActiveX and Socket Clients », ports 7496/7497 (live) ou 7497/4002 (paper).')
      +diagItem(null,'Abonnement Reuters (fondamentaux)','Coche « Reuters Worldwide Fundamentals » dans IBKR Market Data → lève l’erreur 10358 et remplace le repli yfinance par des fondamentaux temps réel.')
      +diagItem(null,'Abonnement Nasdaq-100 (NDX)','Sans cet abonnement, le Nasdaq reste en différé (affiché honnêtement, jamais mélangé). Abonne-toi pour le temps réel homogène.')
      +`<div class="vx-meta vx-mt2">Hors séance, les cotations IBKR passent en différé/frozen — c’est normal, pas une panne.</div></div>`
      +`<div class="vx-card-footer">${VX.updateIndicator(live.generated?live.generated*1000:null,'/api/live/status',liveOn?'live':'delayed')}
        <a class="vx-btn vx-btn-sm vx-btn-ghost vx-right" href="/system?view=data">D&eacute;tail par domaine →</a></div>`;
  }else{
    ($('vx-conn-sync')||{}).innerHTML=VX.states.error('Live Engine injoignable');
    ($('vx-conn-sync-badge')||{}).innerHTML=statusBadge('offline','hors ligne');
  }

  /* Stockage & santé */
  if(hz){
    const ok=hz.ok!==false&&(hz.status==='ok'||hz.ok===true||hz.status===undefined);
    ($('vx-conn-store-badge')||{}).innerHTML=statusBadge(ok?'live':'offline',ok?'sain':'dégradé');
    ($('vx-conn-store')||{}).innerHTML=
      kv('Sant&eacute; serveur',ok?'<span class="vx-pos">OK</span>':'<span class="vx-neg">d&eacute;grad&eacute;</span>')
      +(st?kv('Build',esc(st.build||'—')):'')
      +kv('Donn&eacute;es perso','localStorage navigateur &harr; blob desk_data.json (last-writer-wins)')
      +kv('Sauvegardes','backup quotidien desk_backup_* c&ocirc;t&eacute; serveur')
      +`<div class="vx-card-footer">${VX.updateIndicator(Date.now(),'/healthz',ok?'live':'error')}</div>`;
  }else{
    ($('vx-conn-store')||{}).innerHTML=VX.states.error('/healthz injoignable');
    ($('vx-conn-store-badge')||{}).innerHTML=statusBadge('offline','hors ligne');
  }

  /* Moteurs */
  if(st&&Array.isArray(st.engines)&&st.engines.length){
    /* Moteurs en stat-tiles à halo (au lieu de badges plats) : nom + état
       color-codé. Jamais « prêt » si le moteur n'a aucune donnée exploitable. */
    ($('vx-conn-engines')||{}).innerHTML='<div class="vx-statrow">'
      +st.engines.map(en=>{
        const loaded=en.status==='ok'||en.ok===true;
        const hasData=!!(en.last_success||en.last_run||en.fresh);
        const state=!loaded?['neg','KO','hors service']:(hasData?['pos','Prêt','opérationnel']:['','Chargé','sans données']);
        const dotc=state[0]==='pos'?'var(--vx-positive)':state[0]==='neg'?'var(--vx-negative)':'var(--vx-warning)';
        return `<div class="vx-stat" data-tone="${state[0]}" title="${esc(en.last_error||en.last_success||'')}">
          <div class="vx-stat-k">${esc(en.name||'moteur')}</div>
          <div class="vx-stat-v" style="font-size:15px;display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:99px;background:${dotc};flex:0 0 auto"></span>${state[1]}</div>
          <div class="vx-stat-sub">${state[2]}</div></div>`;
      }).join('')+'</div>'
      +((st.warnings||[]).length?`<div class="vx-stale-banner vx-mt3">⏳ ${st.warnings.map(esc).join(' · ')}</div>`:'')
      +`<div class="vx-mt3"><button class="vx-btn vx-btn-sm vx-btn-ghost" id="vx-tech-endpoints">Détails techniques (endpoints) →</button></div>`;
    ($('vx-conn-meta')||{}).innerHTML=VX.updateIndicator(st.ts||null,'/api/system-status','delayed');
    $('vx-tech-endpoints')?.addEventListener('click',()=>{
      VX.shell.openDrawer('Endpoints techniques',
        [['GET /healthz','santé serveur'],['GET /api/system-status','état institutionnel complet'],
         ['GET /api/live/status','mode + fraîcheur par domaine'],['GET /api/system/diagnostics','diagnostics moteurs'],
         ['GET /api/data-quality','rapport qualité données'],['GET /api/client-log','erreurs JS remontées'],
         ['GET /scan','dump du dernier scan'],['GET/POST /api/desk','sync données perso (17 clés)'],
         ['POST /api/live/refresh','déclencher une mise à jour'],['GET /api/desk/backups + POST /api/desk/restore','sauvegardes quotidiennes']]
        .map(([ep,d])=>`<div class="vx-kv"><span class="k vx-mono" style="font-size:11px">${ep}</span><span class="v vx-meta">${d}</span></div>`).join('')
        +'<div class="vx-help vx-mt3">Lecture seule — aucun de ces endpoints ne peut passer un ordre.</div>');});
  }else{
    ($('vx-conn-engines')||{}).innerHTML=VX.states.empty('Liste des moteurs indisponible.');
  }
}

/* ══ Continuité — observabilité navigation & données (§18) ══════════ */
async function loadContinuity(){
  const host=$('vx-continuity'); if(!host)return;
  const s=(VX.fetch.stats&&VX.fetch.stats())||{};
  const st=(VX.store&&VX.store.snapshot&&VX.store.snapshot())||{};
  let man=null; try{ man=await VX.fetch('/api/session/manifest',{ttl:30000}); }catch(e){}
  const net=document.documentElement.getAttribute('data-net')||'online';
  const nPrices=(VX.prices&&VX.prices._m)?Object.keys(VX.prices._m).length:0;
  /* LOT 606 (dossier 582, ouvert au 582, ferme ici) : ce site portait
     `(man.age_s||0)*1000` — un REPLI sur un age, la seule des cinq puces de
     fraicheur a ne pas garder l ignorance. Le serveur met DELIBEREMENT
     `age_s: null` quand il ne peut pas garantir l anciennete (session_snapshot,
     et `restored['age_s']=None` avec son commentaire d honnetete) ; `null||0`
     vaut 0, donc « age nul », donc la puce « Analyse » — l inverse exact du
     tiret honnete. Une GARDE DE TYPE, comme les quatre autres sites : un age
     inconnu redevient `null`, et `assess` rend `—`. */
  const fr=(VX.freshness&&man)?VX.freshness.chip(VX.freshness.assess({
      ageMs:(typeof man.age_s==='number')?man.age_s*1000:null,
      offline:net==='offline', error:man.error, refreshing:man.status==='analyzing'})):'';
  const row=(k,v)=>'<div class="vx-kv"><span class="k">'+k+'</span><span class="v">'+v+'</span></div>';
  const nd=(v,suf)=>(v==null?'&mdash;':(''+v+(suf||'')));
  host.innerHTML='<div class="vx-grid">'
   +'<div class="vx-col-4"><div class="vx-subhead">Navigation</div>'
     +row('Shell persistant','oui (SPA)')
     +row('Historique',(st.nav_history?st.nav_history.length:0)+' pages')
     +row('Ticker actif',nd(st.active_ticker))+'</div>'
   +'<div class="vx-col-4"><div class="vx-subhead">Cache client</div>'
     +row('Entrées',nd(s.entries))
     +row('Taux de hits',nd(s.hit_rate,'&nbsp;%'))
     +row('Dédup / requêtes en vol',nd(s.dedup)+' / '+nd(s.inflight))+'</div>'
   +'<div class="vx-col-4"><div class="vx-subhead">Session d\'analyse '+fr+'</div>'
     +row('Session',nd(man&&man.session_id))
     +row('Couverture',nd(man&&man.coverage_pct,'&nbsp;%'))
     +row('Qualité données',nd(man&&man.quality_pct,'&nbsp;%'))+'</div>'
   +'<div class="vx-col-4"><div class="vx-subhead">Connexion</div>'
     +row('Réseau',net==='offline'?'<span class="vx-neg">hors ligne</span>':'en ligne')
     +row('Source',nd(man&&man.source))+'</div>'
   +'<div class="vx-col-4"><div class="vx-subhead">Prix centraux</div>'
     +row('Tickers suivis',nd(nPrices))+'</div>'
   +'</div>';
}

/* ══ Vue DONNÉES ════════════════════════════════════════════════════ */
async function loadData(){
  const [dqR,diagR,liveR]=await Promise.allSettled([
    VX.fetch('/api/data-quality',{ttl:30000}),
    VX.fetch('/api/system/diagnostics',{ttl:30000}),
    VX.fetch('/api/live/status',{ttl:30000})]);
  const dq=dqR.status==='fulfilled'?dqR.value:null;
  const diag=diagR.status==='fulfilled'?diagR.value:null;
  const live=liveR.status==='fulfilled'?liveR.value:null;
  const scan=diag&&diag.scan;

  /* Qualité (donut) */
  if(dq&&dq.total>0){
    const byQ=dq.by_quality||{};
    const labels=Object.keys(byQ);
    const values=labels.map(k=>byQ[k]);
    const dominant=labels.slice().sort((a,b)=>byQ[b]-byQ[a])[0];
    whenChartsReady(()=>{
      const colors=VXCharts.colors;
      const colByQ={FRESH:colors.positive,RECENT:colors.cyan,
        STALE:colors.warning,EXPIRED:colors.negative,MISSING:colors.muted,
        DEMO:colors.violet};
      VXCharts.donutCard('vx-data-quality-chart',{
        title:'Qualit&eacute; des donn&eacute;es ('+dq.total+' titres)',unit:'titres',
        question:'Les donn&eacute;es sont-elles utilisables pour d&eacute;cider ?',
        conclusion:'Dominante : '+dominant+' ('+byQ[dominant]+' / '+dq.total+') · source '+(dq.scan_source||'n/d'),
        labels,values,colors:labels.map(k=>colByQ[k]||colors.muted),height:200,
        source:'scan '+(dq.scan_source||'n/d'),timestamp:(scan&&scan.last_scan_ts)||null,
        mode:dq.scan_source==='demo'?'fallback':'delayed',
        limits:dq.note||'',
        explain:{shows:'La r&eacute;partition des titres scann&eacute;s par niveau de qualit&eacute; de donn&eacute;es.',
          why:'Une d&eacute;cision ACTIONABLE exige des donn&eacute;es fra&icirc;ches — la qualit&eacute; plafonne la d&eacute;cision.',
          confirm:'Une majorit&eacute; FRESH/RECENT issue d&#8217;une source r&eacute;elle.',
          invalidate:'Des paquets STALE/EXPIRED/MISSING ou une source d&eacute;mo.'}});
    });
  }else{
    ($('vx-data-quality-chart')||{}).innerHTML='<div class="vx-card">'
      +VX.states.empty('Aucun titre scann&eacute; — la qualit&eacute; ne peut pas &ecirc;tre mesur&eacute;e.',
        '<button class="vx-btn vx-btn-sm" id="vx-data-refresh-empty">Actualiser maintenant</button>')+'</div>';
    document.getElementById('vx-data-refresh-empty')?.addEventListener('click',doRefresh);
  }

  /* Scan + métriques */
  if(scan){
    const metrics=diag.metrics||{};
    const mkeys=Object.keys(metrics).slice(0,8);
    ($('vx-data-scan')||{}).innerHTML=
      kv('Lignes scann&eacute;es',VX.fmt.nd(scan.rows))
      +kv('Source scan',esc(scan.source||'aucune'))
      +kv('Source options',esc(scan.options_source||'—'))
      +kv('Dernier scan',VX.fmt.ago(scan.last_scan_ts))
      +(mkeys.length?'<div class="vx-divider"></div><div class="vx-meta vx-mb1">M&eacute;triques internes</div>'
        +mkeys.map(k=>kv(esc(k),'<span class="vx-mono">'+esc(JSON.stringify(metrics[k]))+'</span>')).join(''):'')
      +`<div class="vx-card-footer">${VX.updateIndicator(scan.last_scan_ts,'/api/system/diagnostics',
        scan.source&&scan.source!=='demo'?'delayed':'fallback')}</div>`;
  }else{
    ($('vx-data-scan')||{}).innerHTML=VX.states.error('Diagnostics indisponibles');
  }

  /* Fraîcheur par domaine */
  if(live&&live.domains&&Object.keys(live.domains).length){
    const doms=live.domains;
    /* Heatmap de fraîcheur (§37) : une tuile/domaine, couleur = état, chiffre = âge. */
    /* GRAMMAIRE TV (lot 196) : le domaine le PLUS RASSIS (âge max connu,
       si ≥ 2 âges connus) est la DOMINANTE — tuile au liseré appuyé + âge
       en CHIP pleine couleur dans la table (grammaire tvEdgeChip), les
       autres restent adoucis. Comptes réels uniquement. */
    const knownAges=Object.keys(doms).filter(k=>{const a=(doms[k]||{}).age_s;return a!==null&&a!==undefined&&isFinite(Number(a));});
    let worstKey=null;
    if(knownAges.length>=2)worstKey=knownAges.reduce((a,b)=>Number(doms[a].age_s)>=Number(doms[b].age_s)?a:b);
    const tile=(k)=>{const d=doms[k]||{};
      const fresh=d.fresh===true||['fresh','live','ok'].includes(d.state);
      const off=d.state==='offline';
      const col=fresh?'--vx-positive':(off?'--vx-negative':'--vx-warning');
      const soft=fresh?'rgba(57,184,120,.13)':(off?'rgba(220,98,85,.13)':'rgba(204,137,44,.13)');
      const age=d.age_s===null||d.age_s===undefined?'—':(d.age_s<120?Math.round(d.age_s)+' s':Math.round(d.age_s/60)+' min');
      const lbl=fresh?'frais':(off?'hors ligne':'différé');
      return `<div role="img" aria-label="${esc(k)} ${lbl} ${age}" style="padding:10px 12px;border-radius:9px;display:flex;flex-direction:column;gap:1px;background:${soft};border:1px solid var(${col},#8f8a83)">
        <span style="font-size:11px;color:var(--vx-text-secondary,#b7b2aa);text-transform:capitalize;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(k)}</span>
        <span style="font-size:16px;font-weight:700;font-variant-numeric:tabular-nums;color:var(${col},#8f8a83)">${age}</span>
        <span style="font-size:9px;letter-spacing:.05em;text-transform:uppercase;color:var(--vx-text-muted,#817d77)">${lbl}</span></div>`;};
    const heat=`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:8px;margin-bottom:14px" aria-label="Heatmap de fraîcheur des données">${Object.keys(doms).map(tile).join('')}</div>`;
    /* LOT 142 : l'age n'est plus un chiffre nu — mini-barre de VERRE de
       STALENESS relative (echelle = age max connu ; frais -> positive
       courte, differe -> warning, hors ligne -> negative) : le domaine le
       plus rassis saute aux yeux. Sans age connu : pas de barre (honnete). */
    const maxAge=Math.max(1,...Object.keys(doms).map(k=>Number((doms[k]||{}).age_s)||0));
    const ageBar=(d,ageTxt,isWorst)=>{
      if(d.age_s===null||d.age_s===undefined)return ageTxt;   /* pas d'age -> pas de barre */
      const a=Number(d.age_s);
      if(!isFinite(a))return ageTxt;
      const fresh=d.fresh===true||d.state==='fresh'||d.state==='live';
      const tok=fresh?'var(--vx-positive,#2BBE90)':(d.state==='offline'?'var(--vx-negative,#E9555F)':'var(--vx-warning,#D9BE3C)');
      const w=Math.max(4,Math.min(100,a/maxAge*100));
      /* le PLUS RASSIS porte son age en CHIP pleine couleur (texte sombre) */
      const ageHtml=isWorst
        ?'<span style="background:'+tok+';color:var(--vx-graphite-850,#121214);font-weight:800;padding:1px 7px;border-radius:6px;font-size:11px">'+ageTxt+'</span>'
        :'<span>'+ageTxt+'</span>';
      return '<span style="display:inline-flex;align-items:center;gap:6px;justify-content:flex-end">'
        +'<span style="width:56px;height:7px;background:var(--vx-surface-3,#121214);border-radius:3px;overflow:hidden;display:inline-block">'
        +'<span style="display:block;height:100%;width:'+w.toFixed(0)+'%;background:linear-gradient(90deg,color-mix(in srgb,'+tok+' 35%,transparent),'+tok+');border-radius:3px"></span></span>'
        +ageHtml+'</span>';};
    ($('vx-data-fresh')||{}).innerHTML=heat+`<div style="overflow-x:auto"><table class="vx-table">
      <thead><tr><th>Domaine</th><th>&Eacute;tat</th><th class="vx-num">&Acirc;ge</th><th>D&eacute;tail</th></tr></thead><tbody>`
      +Object.keys(doms).map(k=>{
        const d=doms[k]||{};
        const fresh=d.fresh===true||['fresh','live','ok'].includes(d.state);
        const status=fresh?'live':(d.state==='offline'?'offline':'delayed');
        const age=d.age_s===null||d.age_s===undefined?'—'
          :(d.age_s<120?Math.round(d.age_s)+' s':Math.round(d.age_s/60)+' min');
        return `<tr><td><b>${esc(k)}</b></td>
          <td>${statusBadge(status,fresh?'frais':(d.state||'rassis'))}</td>
          <td class="vx-num vx-mono">${ageBar(d,age,k===worstKey)}</td>
          <td class="vx-dim" style="font-size:12px">${esc(d.detail||'—')}</td></tr>`;
      }).join('')+'</tbody></table></div>';
    ($('vx-data-fresh-meta')||{}).innerHTML=VX.updateIndicator(
      live.generated?live.generated*1000:null,'Live Engine · mode '+(live.mode||'n/d'),'delayed');
  }else{
    ($('vx-data-fresh')||{}).innerHTML=VX.states.empty('Aucun domaine suivi par le Live Engine pour l&#8217;instant.');
  }

  /* Titres dégradés */
  if(dq){
    const worst=dq.degraded||[];
    ($('vx-data-degraded')||{}).innerHTML=worst.length
      ?'<div class="vx-flex vx-wrap vx-gap2">'+worst.map(w=>{
        const q=String(w.quality||'').toUpperCase();
        const st=/EXPIR|MISSING|ABSEN|INVALID/.test(q)?'offline':/STALE|DELAY|RETARD|DEGRAD/.test(q)?'delayed':'delayed';
        return `<button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(w.symbol)}"
          title="${esc((w.warnings||[]).join(' · '))}">${esc(w.symbol)}
          <span class="vx-badge vx-badge-status" data-status="${st}">${esc(w.quality)}</span></button>`;}).join('')+'</div>'
      :VX.states.empty('Aucun titre en qualit&eacute; d&eacute;grad&eacute;e — rien &agrave; signaler.');
  }else{
    ($('vx-data-degraded')||{}).innerHTML=VX.states.error('Rapport de qualit&eacute; indisponible');
  }
}
async function doRefresh(){
  const btn=$('vx-data-refresh');
  if(btn){btn.disabled=true;btn.textContent='Actualisation…';}
  try{
    const r=await fetch('/api/live/refresh',{method:'POST'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    VX.toast('Actualisation demandée au Live Engine','success');
    await VX.refresh.runAll();
  }catch(e){VX.toast('Actualisation impossible : '+e.message,'error');}
  if(btn){btn.disabled=false;btn.textContent='Actualiser';}
  loadData();
}

/* ══ Vue RÉGLAGES ═══════════════════════════════════════════════════ */
/* Carte Application (lot 284) : version du shell RÉELLE lue des caches du
   navigateur (jamais un numéro codé en dur) + mise à jour forcée — vide le
   cache SW puis recharge. Ne touche JAMAIS localStorage (données desk). */
async function renderAppInfo(){
  /* Deux versions RÉELLES : locale (caches de cet appareil) et publiée
     (lue de /sw.js servi à l'instant) → verdict à jour / mise à jour. */
  let local=null,server=null;
  try{
    const ks=await caches.keys();
    const m=ks.map(k=>/^td-shell-v(\d+)$/.exec(k)).filter(Boolean);
    if(m.length)local=Math.max.apply(null,m.map(x=>Number(x[1])));
  }catch(e){}
  try{
    const t=await (await fetch('/sw.js',{cache:'no-store'})).text();
    const m=/td-shell-v(\d+)/.exec(t);
    if(m)server=Number(m[1]);
  }catch(e){}
  const fmt=v=>v==null?'n/d':'td-shell-v'+v;
  const sw=('serviceWorker' in navigator)
    ?(navigator.serviceWorker.controller?'actif (hors-ligne prêt)':'installé, pas encore aux commandes')
    :'indisponible';
  const el=$('vx-app-info');
  if(el)el.innerHTML=kv('Version locale (cache de cet appareil)',fmt(local))
    +kv('Version publiée (serveur)',fmt(server))
    +kv('Service worker',sw);
  const badge=$('vx-app-shell-badge');
  if(badge)badge.textContent=(local!=null&&server!=null)
    ?(server>local?'mise à jour disponible':'à jour')
    :fmt(local);
}
async function forceAppUpdate(){
  const btn=$('vx-app-update');
  if(btn){btn.disabled=true;btn.textContent='Mise à jour…';}
  try{
    if('serviceWorker' in navigator){
      const regs=await navigator.serviceWorker.getRegistrations();
      for(const r of regs){try{await r.unregister();}catch(e){}}
    }
    if(window.caches){
      const ks=await caches.keys();
      for(const k of ks){try{await caches.delete(k);}catch(e){}}
    }
  }catch(e){}
  location.reload();
}
function initSettings(){
  /* Densité (vxDashboardLayout.density) */
  let layout={};try{layout=JSON.parse(localStorage.getItem('vxDashboardLayout')||'{}')}catch(e){}
  const density=layout.density||'confort';
  document.querySelectorAll('[data-density-btn]').forEach(b=>{
    b.setAttribute('aria-pressed',String(b.dataset.densityBtn===density));
    b.addEventListener('click',()=>{
      layout.density=b.dataset.densityBtn;
      try{localStorage.setItem('vxDashboardLayout',JSON.stringify(layout))}catch(e){}
      document.body.dataset.density=layout.density==='compact'?'compact':(layout.density==='dense'?'dense':'');
      document.querySelectorAll('[data-density-btn]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      VX.toast('Densité enregistrée','success');
    });
  });
  /* Sidebar (vxSidebarState) */
  const sb=localStorage.getItem('vxSidebarState')||'expanded';
  document.querySelectorAll('[data-sidebar-btn]').forEach(b=>{
    b.setAttribute('aria-pressed',String(b.dataset.sidebarBtn===sb));
    b.addEventListener('click',()=>{
      try{localStorage.setItem('vxSidebarState',b.dataset.sidebarBtn)}catch(e){}
      const app=document.getElementById('vx-app');
      if(app)app.dataset.sidebar=b.dataset.sidebarBtn;
      document.querySelectorAll('[data-sidebar-btn]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
    });
  });
  /* Notifications (vxNotificationPrefs {push:bool}) */
  let notif={push:false};try{notif=Object.assign(notif,JSON.parse(localStorage.getItem('vxNotificationPrefs')||'{}'))}catch(e){}
  document.querySelectorAll('[data-notif-btn]').forEach(b=>{
    b.setAttribute('aria-pressed',String((b.dataset.notifBtn==='1')===!!notif.push));
    b.addEventListener('click',()=>{
      notif.push=b.dataset.notifBtn==='1';
      try{localStorage.setItem('vxNotificationPrefs',JSON.stringify(notif))}catch(e){}
      document.querySelectorAll('[data-notif-btn]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      VX.toast(notif.push?'Notifications push activées':'Notifications push coupées','success');
    });
  });
  renderDeskSummary();
  $('vx-desk-export').addEventListener('click',exportDesk);
  $('vx-desk-import-file').addEventListener('change',importDesk);
  if($('vx-app-update')){
    $('vx-app-update').addEventListener('click',forceAppUpdate);
    renderAppInfo();
    /* Au premier chargement le SW installe encore son cache : re-lire quand il est prêt. */
    if('serviceWorker' in navigator&&navigator.serviceWorker.ready)
      navigator.serviceWorker.ready.then(()=>setTimeout(renderAppInfo,600)).catch(()=>{});
  }
  VX.bus.on('vx:data-refreshed',renderDeskSummary);
}
function deskKeys(){
  return (E()&&E().DESK_KEYS)||['myTrades','myTradesClosed','myTradesEquity','myRecos',
    'myRecosClosed','myCapital','simCash','simStart','simTrades','simClosed',
    'myFavs','myNotes','vxJournal','myTradeLog','vxVault','vxAlerts','vxWatchlist'];
}
function renderDeskSummary(){
  const keys=deskKeys();
  let present=0,bytes=0;
  keys.forEach(k=>{const v=localStorage.getItem(k);if(v!=null){present++;bytes+=v.length;}});
  ($('vx-settings-desk')||{}).innerHTML=
    kv('Cl&eacute;s synchronis&eacute;es',keys.length+' (contrat DESK_KEYS — aucune cl&eacute; renomm&eacute;e)')
    +kv('Cl&eacute;s pr&eacute;sentes localement',String(present))
    +kv('Taille locale',VX.fmt.num(bytes/1024,1)+' Ko')
    +kv('Derni&egrave;re &eacute;criture locale',VX.fmt.ago(Number(localStorage.getItem('deskTs')||0)||null));
}
function exportDesk(){
  const keys=deskKeys();const data={};
  keys.forEach(k=>{const v=localStorage.getItem(k);if(v!=null)data[k]=v;});
  const payload={exported:new Date().toISOString(),ts:Number(localStorage.getItem('deskTs')||Date.now()),data};
  const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='vertex-desk-'+new Date().toISOString().slice(0,10)+'.json';
  a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),3000);
  VX.toast('Export desk téléchargé','success');
}
function importDesk(ev){
  const file=ev.target.files&&ev.target.files[0];
  ev.target.value='';
  if(!file)return;
  const reader=new FileReader();
  reader.onload=()=>{
    let payload=null;
    try{payload=JSON.parse(String(reader.result));}catch(e){VX.toast('Fichier JSON invalide','error');return;}
    const data=payload&&payload.data?payload.data:payload;
    if(!data||typeof data!=='object'){VX.toast('Structure inattendue — export desk attendu','error');return;}
    const keys=deskKeys();
    const importable=Object.keys(data).filter(k=>keys.includes(k)&&typeof data[k]==='string');
    if(!importable.length){VX.toast('Aucune clé desk reconnue dans ce fichier','error');return;}
    VX.shell.openModal('Confirmer l’import',
      `<p>Ce fichier va <b>remplacer</b> ${importable.length} cl&eacute;(s) locale(s) :</p>
       <div class="vx-flex vx-wrap vx-gap2 vx-mt2">${importable.map(k=>`<span class="vx-badge">${esc(k)}</span>`).join('')}</div>
       <div class="vx-insight vx-mt3" data-tone="risk">L&#8217;&eacute;criture est suivie d&#8217;une synchronisation
       serveur (last-writer-wins). Les backups quotidiens desk_backup_* restent disponibles en cas d&#8217;erreur.</div>`,
      '<button class="vx-btn vx-btn-primary" id="vx-desk-import-confirm">Importer et synchroniser</button>');
    document.getElementById('vx-desk-import-confirm').addEventListener('click',()=>{
      importable.forEach(k=>{try{localStorage.setItem(k,data[k]);}catch(e){}});
      try{localStorage.setItem('deskTs',String(Date.now()));}catch(e){}
      const out={};keys.forEach(k=>{const v=localStorage.getItem(k);if(v!=null)out[k]=v;});
      fetch('/api/desk',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ts:Number(localStorage.getItem('deskTs')||Date.now()),data:out})}).then(r=>{if(!r.ok)VX.toast('Synchronisation du bureau refusée par le serveur (HTTP '+r.status+') — tes données restent sur cet appareil.','warn',5200);}).catch(()=>{VX.toast('Synchronisation du bureau impossible (serveur injoignable) — tes données restent sur cet appareil.','warn',5200);});
      VX.shell.closeModal();
      VX.bus.emit('vx:data-refreshed',{reason:'desk-import'});
      VX.toast(importable.length+' clé(s) importée(s) et synchronisée(s)','success');
      renderDeskSummary();
    });
  };
  reader.readAsText(file);
}

/* ══ Vue ARCHIVE (vxVault) ══════════════════════════════════════════ */
let vaultTypeFilter='';
function vaultGet(){try{const v=JSON.parse(localStorage.getItem('vxVault')||'[]');return Array.isArray(v)?v:[];}catch(e){return[];}}
function vaultSet(list){
  try{
    localStorage.setItem('vxVault',JSON.stringify(list));
    localStorage.setItem('deskTs',String(Date.now()));
  }catch(e){VX.toast('Écriture locale impossible (quota ?)','error');return;}
  /* Push desk — même protocole que vx-entities.js (last-writer-wins). */
  try{
    const keys=deskKeys();const data={};
    keys.forEach(k=>{const v=localStorage.getItem(k);if(v!=null)data[k]=v;});
    fetch('/api/desk',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ts:Number(localStorage.getItem('deskTs')||Date.now()),data})}).then(r=>{if(!r.ok)VX.toast('Synchronisation du bureau refusée par le serveur (HTTP '+r.status+') — tes données restent sur cet appareil.','warn',5200);}).catch(()=>{VX.toast('Synchronisation du bureau impossible (serveur injoignable) — tes données restent sur cet appareil.','warn',5200);});
  }catch(e){}
}
function initArchive(){
  renderVault();
  $('vx-vault-search').addEventListener('input',renderVault);
  $('vx-vault-new').addEventListener('click',()=>openVaultModal(null));
  $('vx-vault-export').addEventListener('click',()=>{
    const blob=new Blob([JSON.stringify(vaultGet(),null,2)],{type:'application/json'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download='vertex-vault-'+new Date().toISOString().slice(0,10)+'.json';
    a.click();
    setTimeout(()=>URL.revokeObjectURL(a.href),3000);
    VX.toast('Export du coffre téléchargé','success');
  });
  VX.bus.on('vx:data-refreshed',renderVault);
}
function renderVault(){
  const all=vaultGet();
  const types=[...new Set(all.map(e=>e.type).filter(Boolean))].sort();
  ($('vx-vault-chips')||{}).innerHTML=[['','Tous ('+all.length+')']]
    .concat(types.map(t=>[t,t+' ('+all.filter(e=>e.type===t).length+')']))
    .map(([val,label])=>`<button class="vx-chip" data-filter-key="type" data-filter-value="${esc(val)}"
      aria-pressed="${String(val===vaultTypeFilter)}">${esc(label)}</button>`).join('');
  document.querySelectorAll('#vx-vault-chips .vx-chip').forEach(ch=>
    ch.addEventListener('click',()=>{vaultTypeFilter=ch.dataset.filterValue;renderVault();}));
  const q=($('vx-vault-search').value||'').trim().toLowerCase();
  const rows=all.filter(e=>{
    if(vaultTypeFilter&&e.type!==vaultTypeFilter)return false;
    if(!q)return true;
    return [e.title,e.content,(e.tags||[]).join(' '),e.type]
      .map(x=>String(x||'').toLowerCase()).some(x=>x.includes(q));
  }).sort((a,b)=>String(b.updatedAt||b.createdAt||'').localeCompare(String(a.updatedAt||a.createdAt||'')));
  if(!rows.length){
    ($('vx-vault-list')||{}).innerHTML=VX.states.emptyDesk(
      all.length?'Aucune entr&eacute;e ne correspond &agrave; la recherche ou au filtre.'
      :'Le coffre est vide — archivez ici vos analyses, mod&egrave;les et documents de r&eacute;f&eacute;rence.',
      all.length?'':'<button class="vx-btn vx-btn-sm" id="vx-vault-new-empty">Cr&eacute;er la premi&egrave;re entr&eacute;e</button>');
    document.getElementById('vx-vault-new-empty')?.addEventListener('click',()=>openVaultModal(null));
    return;
  }
  ($('vx-vault-list')||{}).innerHTML=`<div style="overflow-x:auto"><table class="vx-table">
    <thead><tr><th>Titre</th><th>Type</th><th>Tags</th><th class="vx-num">Mis &agrave; jour</th><th></th></tr></thead><tbody>`
    +rows.map(e=>`<tr>
      <td><button class="vx-btn vx-btn-sm vx-btn-ghost" data-vault-open="${esc(String(e.id))}"
        style="font-weight:600">${esc(e.title||'(sans titre)')}</button>
        <div class="vx-meta vx-truncate" style="max-width:420px" title="${esc(String(e.content||'').slice(0,120))}">${esc(String(e.content||'').slice(0,120))}</div></td>
      <td><span class="vx-badge">${esc(e.type||'note')}</span>
        ${e.status?`<span class="vx-badge vx-muted">${esc(e.status)}</span>`:''}</td>
      <td class="vx-dim" style="font-size:12px">${(e.tags||[]).map(t=>'#'+esc(t)).join(' ')||'—'}</td>
      <td class="vx-num vx-meta">${VX.fmt.ago(e.updatedAt||e.createdAt)}</td>
      <td><button class="vx-btn vx-btn-sm" data-vault-edit="${esc(String(e.id))}">Modifier</button></td>
    </tr>`).join('')+'</tbody></table></div>'
    +`<div class="vx-card-footer">${rows.length} entr&eacute;e(s) affich&eacute;e(s) · coffre local synchronis&eacute; via /api/desk</div>`;
  document.querySelectorAll('[data-vault-open]').forEach(b=>
    b.addEventListener('click',()=>openVaultDrawer(b.dataset.vaultOpen)));
  document.querySelectorAll('[data-vault-edit]').forEach(b=>
    b.addEventListener('click',()=>openVaultModal(b.dataset.vaultEdit)));
}
function openVaultDrawer(id){
  const e=vaultGet().find(x=>String(x.id)===String(id));
  if(!e)return;
  VX.shell.openDrawer(e.title||'(sans titre)',
    `<div class="vx-flex vx-wrap vx-gap2 vx-mb3">
      <span class="vx-badge">${esc(e.type||'note')}</span>
      ${e.priority?`<span class="vx-badge">priorit&eacute; ${esc(e.priority)}</span>`:''}
      ${e.status?`<span class="vx-badge">${esc(e.status)}</span>`:''}</div>
    <div style="white-space:pre-wrap;font-size:13px;line-height:1.7">${esc(e.content||'')}</div>
    ${(e.tags||[]).length?`<div class="vx-mt3 vx-dim">${e.tags.map(t=>'#'+esc(t)).join(' ')}</div>`:''}
    <div class="vx-divider"></div>
    <div class="vx-meta">Cr&eacute;&eacute;e ${VX.fmt.ago(e.createdAt)} · mise &agrave; jour ${VX.fmt.ago(e.updatedAt||e.createdAt)}</div>
    <div class="vx-mt3"><button class="vx-btn vx-btn-sm" onclick="document.querySelector('[data-vault-edit=&quot;${esc(String(e.id))}&quot;]')?.click();VX.shell.closeDrawer()">Modifier</button></div>`);
}
function openVaultModal(id){
  const existing=id?vaultGet().find(x=>String(x.id)===String(id)):null;
  const e=existing||{title:'',type:'note',content:'',tags:[],priority:'normal',status:'active'};
  VX.shell.openModal(existing?'Modifier l’entrée':'Nouvelle entrée',
    `<div class="vx-field"><label for="vv-title">Titre</label>
      <input class="vx-input" id="vv-title" value="${esc(e.title)}" /></div>
    <div class="vx-form-row">
      <div class="vx-field"><label for="vv-type">Type</label>
        <select class="vx-select" id="vv-type">
          ${['note','analyse','modele','document','lien','regle'].map(t=>
            `<option value="${t}" ${e.type===t?'selected':''}>${t}</option>`).join('')}
        </select></div>
      <div class="vx-field"><label for="vv-priority">Priorit&eacute;</label>
        <select class="vx-select" id="vv-priority">
          ${['haute','normal','basse'].map(p=>
            `<option value="${p}" ${e.priority===p?'selected':''}>${p}</option>`).join('')}
        </select></div>
    </div>
    <div class="vx-field"><label for="vv-content">Contenu</label>
      <textarea class="vx-textarea" id="vv-content" rows="8">${esc(e.content)}</textarea></div>
    <div class="vx-field"><label for="vv-tags">Tags (s&eacute;par&eacute;s par des virgules)</label>
      <input class="vx-input" id="vv-tags" value="${esc((e.tags||[]).join(', '))}" /></div>`,
    `${existing?'<button class="vx-btn vx-btn-ghost" id="vv-delete">Supprimer</button>':''}
     <button class="vx-btn vx-btn-primary" id="vv-save">${existing?'Enregistrer':'Cr&eacute;er'}</button>`);
  document.getElementById('vv-save').addEventListener('click',()=>{
    const title=(document.getElementById('vv-title').value||'').trim();
    if(!title){VX.toast('Titre requis','error');return;}
    const now=new Date().toISOString();
    const entry={
      id:existing?existing.id:Date.now(),
      title,
      type:document.getElementById('vv-type').value,
      content:document.getElementById('vv-content').value,
      tags:(document.getElementById('vv-tags').value||'').split(',').map(s=>s.trim()).filter(Boolean),
      createdAt:existing?(existing.createdAt||now):now,
      updatedAt:now,
      status:existing?(existing.status||'active'):'active',
      priority:document.getElementById('vv-priority').value,
    };
    const list=vaultGet().filter(x=>String(x.id)!==String(entry.id));
    list.push(entry);
    vaultSet(list);
    VX.shell.closeModal();
    VX.toast(existing?'Entrée mise à jour':'Entrée créée','success');
    renderVault();
  });
  document.getElementById('vv-delete')?.addEventListener('click',()=>{
    vaultSet(vaultGet().filter(x=>String(x.id)!==String(id)));
    VX.shell.closeModal();
    VX.toast('Entrée supprimée');
    renderVault();
  });
}

/* ══ Vue AUTOMATISATIONS (§24) ══════════════════════════════════════ */
async function loadAutomations(){
  try{
    const d=await VX.fetch('/api/system/automations',{ttl:15000});
    const jobs=d.jobs||[];
    ($('vx-auto-jobs')||{}).innerHTML=jobs.length?`<div class="vx-table-wrap"><table class="vx-table"><thead><tr>
      <th>Tâche</th><th>Statut</th><th class="vx-num">Exécutions</th><th>Dernière</th><th>Prochaine (est.)</th><th class="vx-num">Durée</th></tr></thead><tbody>
      ${jobs.map(j=>{
        /* #779/G1 — AVANT, une seule branche : `last_run===null` -> « jamais
           exécuté ». Le même mot pour un job EN PANNE et pour un job qu'AUCUN
           code n'exécute. La mesure (tools/mesures/mesurer_registre_jobs.py)
           a trouvé 18 des 27 jobs déclarés sans le moindre émetteur `beat` :
           ils ne pouvaient pas tourner, et l'écran les accusait d'un échec.
           Le serveur tranche désormais lui-même via `etat`. */
        /* SILENCIEUX (lot 7) : cadencé, déjà battu, muet depuis > 2× sa
           cadence — la boucle est morte ou coincée. Avant, un job mort
           restait « OK » pour toujours. Ambre : prudence, pas erreur —
           le dernier passage avait réussi. */
        const ETATS={NON_IMPLEMENTE:['frozen','non implémenté'],EN_ATTENTE:['frozen','en attente'],
                     ACTIF:['live','OK'],ERREUR:['offline','erreur'],
                     SILENCIEUX:['stale','silencieux']};
        const st=ETATS[j.etat]||(j.last_run===null?['frozen','en attente']:(j.last_ok?['live','OK']:['offline','erreur']));
        return `<tr><td><b>${esc(j.name)}</b><br><span class="vx-meta">${esc(j.description||'')}</span></td>
        <td><span class="vx-badge vx-badge-status" data-status="${st[0]}" title="${esc(j.last_error||'')}">${st[1]}</span></td>
        <td class="vx-num">${j.runs||0}</td>
        <td class="vx-mono vx-meta">${j.age_s!==null&&j.age_s!==undefined?VX.fmt.ago(Date.now()-j.age_s*1000):'—'}</td>
        <td class="vx-mono vx-meta">${j.etat==='NON_IMPLEMENTE'?'—':
          /* « sur événement » PROMET un déclenchement. Pour un job sans exécutant,
             aucun événement ne le déclenchera jamais : la même invention que le
             statut, une colonne plus loin. Trouvée à la capture, pas à l'API. */
          (j.next_run_eta_s!==null&&j.next_run_eta_s!==undefined?('dans ~'+Math.round(j.next_run_eta_s/60)+' min'):(j.interval_s?'—':'sur événement'))}</td>
        <td class="vx-num">${j.last_duration_ms!==null&&j.last_duration_ms!==undefined?j.last_duration_ms+' ms':'—'}</td></tr>`;}).join('')}
      </tbody></table></div>
      <div class="vx-card-footer">${VX.updateIndicator(Date.now(),'/api/system/automations','live')}
      · « non implémenté » = déclaré au registre, aucun exécutant dans le code — ce n'est pas une panne.
      « en attente » = implémenté, pas encore passé depuis le démarrage.</div>`
      :VX.states.empty('Registre de jobs vide.');
  }catch(e){($('vx-auto-jobs')||{}).innerHTML=VX.states.error('Registre indisponible : '+esc(e.message));}
  try{
    const r=await VX.fetch('/api/system/startup-report',{ttl:60000});
    ($('vx-auto-startup')||{}).innerHTML=(r.steps||[]).length?
      (r.steps.map(st2=>{
        const tone={CONNECTED:'live',READY:'live',CONFIGURED:'live',DEGRADED:'delayed',
          MISSING:'frozen',OFFLINE:'offline',ERROR:'offline'}[st2.status]||'frozen';
        return `<div class="vx-kv"><span class="k">${esc(st2.step)}</span>
          <span class="v"><span class="vx-badge vx-badge-status" data-status="${tone}">${esc(st2.status)}</span></span></div>
          <div class="vx-meta" style="margin:-4px 0 6px">${esc(st2.detail||'')}</div>`;}).join('')
       +`<div class="vx-kv"><span class="k">Exécution d'ordres</span><span class="v vx-pos">${esc(r.order_execution||'')}</span></div>`
       +`<div class="vx-card-footer">${VX.updateIndicator((r.ts||0)*1000,'séquence de démarrage','live')}</div>`)
      :VX.states.empty('Rapport non généré (serveur fraîchement démarré ?).');
  }catch(e){($('vx-auto-startup')||{}).innerHTML=VX.states.error('Rapport indisponible');}
  try{
    const c=await VX.fetch('/api/system/config',{ttl:60000});
    const rows=Object.entries(c).filter(([k])=>!k.startsWith('_'));
    ($('vx-auto-config')||{}).innerHTML=`<div class="vx-flex vx-wrap vx-gap2">${rows.map(([k,v])=>{
      const tone={CONFIGURED:'live',MISSING:'frozen',INVALID:'offline'}[v.status]||'frozen';
      return `<span class="vx-badge vx-badge-status" data-status="${tone}"
        title="${esc(v.consequence||'')}">${esc(k)} · ${esc(v.status)}</span>`;}).join('')}</div>
      <div class="vx-help vx-mt2">Survoler un badge : conséquence exacte d'une variable absente. Aucune valeur n'est jamais affichée ni journalisée.</div>`;
  }catch(e){($('vx-auto-config')||{}).innerHTML=VX.states.error('Validation indisponible');}
}


/* ══ ALERTES TECHNIQUES ══════════════════════════════════════════════
   Rien n'est calcule ici. Tout vient de `/api/system/diagnostics`, de
   `/healthz` et de `/api/system/jobs` — trois endpoints deja servis.
   Une alerte qu'aucun moteur ne produit est DECLAREE absente, pas simulee. */
async function loadAlerts(){
  const k=(l,v,sub,ton)=>'<div class="vx2-metric"><span class="vx2-metric-label">'+l+'</span>'
    +'<span class="vx2-metric-value" data-tone="'+(ton||'')+'">'+v+'</span>'
    +(sub?'<span class="vx2-metric-meta">'+sub+'</span>':'')+'</div>';
  let dg=null,hz=null,jb=null;
  try{dg=await VX.fetch('/api/system/diagnostics',{ttl:30000});}catch(e){}
  try{hz=await VX.fetch('/healthz',{ttl:30000});}catch(e){}
  try{jb=await VX.fetch('/api/system/jobs',{ttl:30000});}catch(e){}
  const al=(dg&&dg.alerts)||{},me=al.metrics||{};
  const jobs=(jb&&jb.jobs)||[];
  const enEchec=jobs.filter(j=>j.last_error);
  const nonImpl=jobs.filter(j=>j.implemente===false);
  ($('vx-alerts-kpis')||{}).innerHTML='<div class="vx2-strip">'
    +k('Alertes actives',al.active!=null?String(al.active):'—',
       'alertes de marché armées',al.active>0?'caution':'')
    +k('Emises',me.emitted!=null?String(me.emitted):'—','depuis le démarrage')
    +k('Tâches en échec',String(enEchec.length),
       enEchec.length?'dernière erreur consignée':'aucune erreur de tâche',
       enEchec.length?'negative':'positive')
    /*  Un job marque `implemente:false` n'a AUCUN executant : dire qu'il n'a
        « jamais ete execute » l'accuse d'un silence qui n'est pas le sien. Le
        registre distingue trois situations — non implemente, en attente, en
        panne — et l'ecran doit les distinguer aussi.  */
    +k('Tâches sans exécutant',String(nonImpl.length),
       'déclarées au registre, aucun code derrière',nonImpl.length?'missing':'')
    +'</div>';

  /* Pannes : une panne est un FAIT rapporte par le serveur, pas une deduction. */
  const pannes=[];
  if(hz&&hz.scan_error)pannes.push(['Scan',String(hz.scan_error),'negative']);
  const lk=(dg&&dg.ibkr_link)||{};
  if(lk.raison)pannes.push(['Lien IBKR',String(lk.raison),lk.mode?'caution':'missing']);
  const sh=(hz&&hz.source_health)||{};
  Object.keys(sh).forEach(function(nom){
    const v=String(sh[nom]||'');
    /*  `UNKNOWN`, `STALE`… sont des codes moteur : ils ne s'affichent jamais
        bruts. Un etat inconnu n'est pas non plus une panne — il empeche de
        decider, ce que la carte dit, mais le mot doit etre juste.  */
    const LIB={UNKNOWN:'état non rapporté par le serveur',
               STALE:'données périmées',DEGRADED:'source dégradée',
               PARTIAL:'couverture partielle',OFFLINE:'source hors ligne'};
    if(v&&v!=='OK'&&v!=='LIVE')pannes.push(['Source '+nom,LIB[v]||v,v==='UNKNOWN'?'missing':'caution']);
  });
  enEchec.forEach(j=>pannes.push(['Tache '+j.name,String(j.last_error),'negative']));
  ($('vx-alerts-pannes')||{}).innerHTML=pannes.length
    ? '<div class="vx2-theses">'+pannes.map(function(p){
        return '<article class="vx2-these" data-etat="'+(p[2]==='negative'?'cassee':p[2]==='caution'?'fragilisee':'')+'">'
          +'<div class="vx2-these-head"><strong>'+esc(p[0])+'</strong>'
          +'<span class="vx2-badge" data-state="'+(p[2]==='negative'?'error':p[2]==='caution'?'delayed':'missing')+'">'
          +(p[2]==='negative'?'en échec':p[2]==='caution'?'dégradé':'inconnu')+'</span></div>'
          +'<p class="vx2-these-texte">'+esc(p[1])+'</p></article>';}).join('')+'</div>'
    : '<div class="vx2-state" data-kind="empty" role="status">'
      +'<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
      +'<p class="vx2-state-title">Aucune panne rapportée</p>'
      +'<p class="vx2-state-cause">Ni le scan, ni le lien courtier, ni les taches de fond '
      +'ne signalent d\'erreur. L\'absence de panne n\'est pas une garantie de fraîcheur : '
      +'la voir sur <a href="/system?view=data">Donnees</a>.</p></div>';

  /* Alertes de marche : elles vivent dans le desk, pas dans un moteur. */
  const E=window.VXEntities;
  const ual=(E&&E.alerts&&E.alerts())||[];
  ($('vx-alerts-marche')||{}).innerHTML=ual.length
    ? '<div class="vx-kv"><span class="k">Alertes déclarées</span><span class="v vx-mono">'+ual.length+'</span></div>'
      +'<div class="vx2-stamp vx-mt2">Elles vivent dans le bureau local. '
      +'Les compteurs ci-dessus decrivent le moteur d\'alertes du serveur.</div>'
    : '<div class="vx2-state" data-kind="empty" role="status">'
      +'<p class="vx2-state-title">Aucune alerte de marché déclarée</p>'
      +'<p class="vx2-state-cause">Elles se posent depuis une analyse ou une position.</p></div>';

  ($('vx-alerts-absences')||{}).innerHTML=%%ABSENCES_ALERTES%%;
}

/* ══ SECURITE ════════════════════════════════════════════════════════
   L'invariant est confirme PAR LE SERVEUR, jamais par un drapeau de page. */
/* La barre de contexte porte la sante globale. Elle etait declaree et remplie
   par personne : « Lecture… » pour toujours. */
async function peindreSante(){
  const el=$('vx-sys-ctx-sante');if(!el)return;
  const dire=(t,e)=>{el.innerHTML='<span class="vx2-badge" data-state="'+e+'">'+t+'</span>';};
  /* /healthz est une sonde de VIE : status='ok' = le process repond, rien de
     plus. Le badge la traduisait en « Operationnel · 8 moteurs » pendant que
     la jauge de la meme page disait 0/8 (mesure au navigateur). L'etat global
     vient desormais de /readyz — les verifications REELLES — et le compte
     affiche est celui des verifications passees, pas des moteurs declares. */
  let rz=null;try{rz=await VX.fetch('/readyz',{ttl:30000});}catch(e){}
  if(!rz||!Array.isArray(rz.checks)){dire('Santé non lue','missing');return;}
  const ok=rz.checks.filter(c=>c.ok).length,n=rz.checks.length;
  if(rz.ready===true&&ok===n){dire('Prêt · '+ok+'/'+n+' vérifications','live');return;}
  if(rz.ready===true){dire('Prêt · '+ok+'/'+n+' vérifications','delayed');return;}
  dire('Non prêt · '+ok+'/'+n+' vérifications','error');
}

async function loadSecurity(){
  let hz=null,cf=null;
  try{hz=await VX.fetch('/healthz',{ttl:30000});}catch(e){}
  try{cf=await VX.fetch('/api/system/config',{ttl:60000});}catch(e){}
  const ro=hz&&hz.constitution&&hz.constitution.read_only===true;
  ($('vx-sec-invariant')||{}).innerHTML='<div class="vx2-strip">'
    +'<div class="vx2-metric"><span class="vx2-metric-label">Lecture seule</span>'
    +'<span class="vx2-metric-value" data-tone="'+(ro?'positive':'negative')+'">'
    +(ro?'CONFIRMÉE':'NON CONFIRMÉE')+'</span>'
    +'<span class="vx2-metric-meta">'+(ro?'par le serveur, pas par la page'
      :'le serveur ne l\'a pas confirmee — ne pas s\'y fier')+'</span></div>'
    +'<div class="vx2-metric"><span class="vx2-metric-label">Profil stratégique</span>'
    +'<span class="vx2-metric-value">'+esc(((hz&&hz.constitution)||{}).strategy_id||'—')+'</span>'
    +'<span class="vx2-metric-meta">version '+esc(String(((hz&&hz.constitution)||{}).version||'—'))+'</span></div>'
    +'<div class="vx2-metric"><span class="vx2-metric-label">Courtier</span>'
    +'<span class="vx2-metric-value" data-tone="'+(hz&&hz.ibkr_live?'positive':'missing')+'">'
    +(hz&&hz.ibkr_live?'connecté':(hz&&hz.ibkr_enabled?'activé, hors ligne':'désactivé'))+'</span>'
    +'<span class="vx2-metric-meta">toujours en lecture seule</span></div>'
    +'</div>';

  /* Secrets : le STATUT seul. Jamais une valeur, jamais un fragment. */
  const el=$('vx-sec-config');
  if(el){
    const clefs=cf?Object.keys(cf).filter(c=>c.charAt(0)!=='_').sort():[];
    el.innerHTML=clefs.length
      ? '<div class="vx-table-wrap"><table class="vx2-table"><thead><tr>'
        +'<th scope="col">Clé</th><th scope="col">Statut</th><th scope="col">Requise</th>'
        +'<th scope="col">Conséquence si absente</th></tr></thead><tbody>'
        +clefs.map(function(c){const v=cf[c]||{};
          const pose=String(v.status||'').toUpperCase()!=='MISSING';
          return '<tr><td><code>'+esc(c)+'</code></td>'
            +'<td><span class="vx2-badge" data-state="'+(pose?'live':'missing')+'">'
            +(pose?'posée':'absente')+'</span></td>'
            +'<td>'+(v.required?'oui':'non')+'</td>'
            +'<td>'+esc(v.consequence||'—')+'</td></tr>';}).join('')
        +'</tbody></table></div>'
      : '<div class="vx2-state" data-kind="missing" role="status">'
        +'<p class="vx2-state-title">Inventaire des clés indisponible</p>'
        +'<p class="vx2-state-cause">`/api/system/config` n\'a pas répondu.</p></div>';
  }
  ($('vx-sec-jamais')||{}).innerHTML=%%JAMAIS%%;
}

/* ══ Orchestration ══════════════════════════════════════════════════ */
document.querySelectorAll('details.vx-disclosure').forEach(d=>{
  d.addEventListener('toggle',()=>{if(d.open)window.dispatchEvent(new Event('resize'));});
});
peindreSante();
if(VIEW==='connections'){
  loadConnections();
  document.getElementById('vx-brain-refresh')?.addEventListener('click',refreshBrain);
  VX.refresh.register(loadConnections,60000,'connections');
}else if(VIEW==='data'){
  loadData();
  loadContinuity();
  $('vx-data-refresh').addEventListener('click',doRefresh);
  VX.refresh.register(loadData,60000,'data');
  VX.refresh.register(loadContinuity,15000,'continuity');
}else if(VIEW==='jobs'){
  loadAutomations();
  VX.refresh.register(loadAutomations,60000,'jobs');
}else if(VIEW==='alerts'){
  loadAlerts();
  VX.refresh.register(loadAlerts,60000,'alertes');
}else if(VIEW==='preferences'){
  initSettings();
}else if(VIEW==='security'){
  loadSecurity();
}else if(VIEW==='archives'){
  initArchive();
}
VX.context.restoreIfReturning();
})();
</script>
"""


def render(view: str = 'connections') -> str:
    view = _ALIAS.get(view, view)
    view = view if view in dict(VIEWS) else _DEFAULT_VIEW
    body = _VIEW_CONTENT[view].replace(
        '%%LOADING%%', '<div class="vx-skeleton" style="height:60px"></div>').replace(
        '%%LOCKCARD%%', _lock_card(AUTH_ON))
    content = (_header(view)
               + f'<div id="vx-system" data-view="{view}">' + body + '</div>')
    page_js = (_JS.replace('%%ABSENCES_ALERTES%%', json_for_script(_ABSENCES_ALERTES))
               .replace('%%JAMAIS%%', json_for_script(_JAMAIS)))
    sub = dict(VIEWS)[view]
    return render_shell(title='Système', active='system',
                        space_label='Système', sub_label=sub,
                        content=content, page_js=page_js,
                        page_label='Système — ' + sub)
