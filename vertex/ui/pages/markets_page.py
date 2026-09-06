"""vertex.ui.pages.markets_page — l'espace Marchés (§23).

Question : « Dans quel environnement la stratégie opère-t-elle ? »
Sous-vues (param ?view=) : overview · macro · sectors · breadth · volatility.

Le module Python ne fait AUCUN calcul financier : il assemble le squelette
HTML + le script client ; toutes les données viennent des moteurs via
VX.fetch (/scan, /api/market/regime, /cal-feed, /api/market/summary).
Donnée absente → VX.states.empty honnête, jamais un chiffre inventé.
"""
from __future__ import annotations

from vertex.ui import vx2
from vertex.ui.shell import render_shell

# Sous-vues canoniques (ordre = ordre des onglets).
# `Breadth` etait le seul libelle anglais de la barre, alors que le corps de
# la page ecrit deja « Participation → » pour designer la MEME sous-vue.
# `indices` est la sous-vue « Indices & cross-asset » du contrat : ses trois
# blocs existaient, replies dans un `<details>` de la Synthese.
_VIEWS = (
    ('overview', 'Synthèse'),
    ('macro', 'Macro'),
    ('indices', 'Indices & cross-asset'),
    ('sectors', 'Secteurs'),
    ('breadth', 'Participation'),
    ('volatility', 'Volatilité'),
)


def _tabs(view: str) -> str:
    """Barre d'onglets — navigation par URL (?view=…), pas d'état JS."""
    return vx2.tabs([{'label': label, 'href': f'?view={vid}', 'actif': vid == view}
                     for vid, label in _VIEWS],
                    libelle='Sous-vues des Marchés')


_HEADER = """
%%ENTETE%%
%%TABS%%
<div id="vx-demo-banner"></div>
"""

# ── Squelettes par sous-vue ──────────────────────────────────────────────
_VIEW_CONTENT = {
    'overview': """
<!-- Réponse immédiate : régime et risque, sans seconde visualisation. -->
<div class="vx-hero-grid vx-mt3 vx-markets-lead">
  <section class="vx-card vx-card--hero" id="vx-mk-regime" aria-label="Régime de marché">
    <div class="vx-card-header"><span class="vx-card-title">Régime de marché</span>
      <span class="vx-chart-question">Le vent est-il dans le dos ou de face ?</span></div>
    <div id="vx-mk-regime-body">%%LOADING%%</div>
  </section>
  <aside class="vx-insight-rail" style="grid-template-columns:minmax(0,1fr)" id="vx-mk-risk" aria-label="Risque du jour">
    <section class="vx-card">
      <div class="vx-card-header"><span class="vx-card-title">Risque du jour</span></div>
      <div id="vx-mk-risk-body">%%LOADING%%</div>
    </section>
  </aside>
</div>

<!-- Quatre KPI maximum, puis UN graphe principal avec le leadership à droite. -->
<div class="vx-hero-grid vx-mt4">
  <div id="vx-mk-spy"></div>
  <aside class="vx-insight-rail" style="grid-template-columns:minmax(0,1fr)" id="vx-mk-leader" aria-label="Leadership sectoriel">
    <section class="vx-card">
      <div class="vx-card-header"><span class="vx-card-title">Leadership sectoriel</span>
        <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="?view=sectors">Secteurs →</a></span></div>
      <div id="vx-mk-leader-body">%%LOADING%%</div>
    </section>
  </aside>
</div>

<p class="vx2-stamp vx-mt4">La comparaison des indices et les mouvements du scan
  vivent désormais dans <a href="?view=indices">Indices &amp; cross-asset</a> —
  ils ne concurrencent plus le graphique de référence au premier écran.</p>
""",
    'indices': """
<!-- Sous-vue canonique « Indices & cross-asset ». Ces trois blocs existaient,
     repliés dans un `<details>` de la Synthèse : leur contenu ne change pas,
     leur adresse devient partageable. -->
<div class="vx-kpi-strip vx-mt3" id="vx-mk-strip" data-max-kpis="4" aria-label="Indices clés"></div>
<div class="vx-mt4" id="vx-mk-multi"></div>
<div class="vx-hero-grid vx-mt4">
  <section class="vx-card" aria-label="Top 10 hausses">
    <div class="vx-card-header"><span class="vx-card-title">Top 10 — plus fortes hausses</span>
      <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities?view=stocks">Univers →</a></span></div>
    <div id="vx-mk-top"></div>
  </section>
  <section class="vx-card" aria-label="Flop 10 baisses">
    <div class="vx-card-header"><span class="vx-card-title">Flop 10 — plus fortes baisses</span></div>
    <div id="vx-mk-flop"></div>
  </section>
</div>
""",
    'macro': """
<div class="vx-kpi-strip vx-mt3" id="vx-mk-macro-kpis" data-max-kpis="4" aria-label="Quatre indicateurs macro clés"></div>
<section class="vx-card vx-mt4" id="vx-mk-macro-officiel" aria-label="Références macro officielles">
  <div class="vx-card-header"><span class="vx-card-title">Références officielles — taux, inflation, change</span>
    <span class="vx-chart-question">Que publient la Fed, la BCE et la BNS, et à quelle date ?</span></div>
  <div id="vx-mk-macro-officiel-body"><div class="vx-skeleton" style="height:180px"></div></div>
</section>
<section class="vx-card vx-mt3 vx-mk-macro" id="vx-mk-communiques" aria-label="Communiqués officiels">
  <div class="vx-card-header"><span class="vx-card-title">Communiqués officiels — BCE, BNS</span>
    <span class="vx-chart-question">Qu'ont publié les banques centrales de la zone euro et de la Suisse ?</span></div>
  <div id="vx-mk-communiques-body"><div class="vx-skeleton" style="height:120px"></div></div>
</section>
<div class="vx-hero-grid vx-mt4">
  <div id="vx-mk-yield"></div>
  <aside class="vx-insight-rail" style="grid-template-columns:minmax(0,1fr)">
    <div class="vx-grid" id="vx-mk-macro-regime" aria-label="Appétit pour le risque &amp; régime"></div>
  </aside>
</div>
<div class="vx-section-stack vx-mt4">
  <div id="vx-mk-macro-cal"></div>
  <details class="vx-disclosure vx-markets-macro-details">
    <summary>Données complémentaires et limites</summary>
    <div class="vx-disclosure__body">
      <div class="vx-hero-grid">
        <div id="vx-mk-macro-extra"></div>
        <section class="vx-card" aria-label="Limites des données macro">
          <div class="vx-card-header"><span class="vx-card-title">Limites des données</span></div>
          <div class="vx-insight">Courbe tracée sur les <b>4 maturités réelles</b> du scan
          (3M · 5A · 10A · 30A). Les maturités intermédiaires (2A/7A/20A) ne sont pas fournies
          par les moteurs — non affichées plutôt qu’inventées.</div>
        </section>
      </div>
    </div>
  </details>
</div>
""",
    'sectors': """
<!-- Deux vues secteurs MAXIMUM (PR n°3) : RRG décisionnel + heatmap de détail.
     Le bar chart et le treemap redondants (mêmes scan.sectors) ont été retirés. -->
<div class="vx-grid vx-mt3">
  <div class="vx-col-8" id="vx-mk-rotation"></div>
  <section class="vx-card vx-col-4" aria-label="Leaders par secteur">
    <div class="vx-card-header"><span class="vx-card-title">Leaders par secteur</span></div>
    <div id="vx-mk-sectors-leaders">%%LOADING%%</div>
  </section>
</div>
<div class="vx-grid vx-mt4">
  <div class="vx-col-12" id="vx-mk-sectors-heat"></div>
</div>
""",
    'breadth': """
<!-- La tendance répond à la question principale ; le KPI et son rail donnent
     le niveau actuel sans ajouter une seconde jauge. -->
<div class="vx-hero-grid vx-mt3">
  <div id="vx-mk-breadth-trend"></div>
  <aside class="vx-insight-rail" style="grid-template-columns:minmax(0,1fr)" aria-label="Participation du marché">
    <section class="vx-card">
      <div class="vx-card-header"><span class="vx-card-title">Participation actuelle</span></div>
      <div id="vx-mk-breadth-gauge">%%LOADING%%</div>
      <div class="vx-card-header"><span class="vx-card-title">Détail — au-dessus des moyennes</span></div>
      <div id="vx-mk-breadth-detail">%%LOADING%%</div>
    </section>
  </aside>
</div>

<details class="vx-disclosure vx-mt4 vx-markets-breadth-details">
  <summary>Sélection et métriques avancées</summary>
  <div class="vx-disclosure__body">
    <div class="vx-section-stack">
      <div class="vx-hero-grid">
        <section class="vx-card" aria-label="Entonnoir de sélection">
          <div class="vx-card-header"><span class="vx-card-title">Entonnoir de sélection</span>
            <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities?view=stocks">Dossiers →</a></span></div>
          <div id="vx-mk-funnel">%%LOADING%%</div>
        </section>
        <div id="vx-mk-verdicts"></div>
      </div>
      <div class="vx-hero-grid">
        <section class="vx-card" id="vx-mk-internals-card" aria-label="Internals du marché" hidden>
          <div class="vx-card-header"><span class="vx-card-title">Internals — participation mesurée</span></div>
          <div id="vx-mk-internals"></div>
        </section>
        <section class="vx-card" id="vx-mk-dist-card" aria-label="Distribution des scores" hidden>
          <div class="vx-chart-head"><span class="vx-chart-title">Distribution des scores de l’univers</span>
            <span class="vx-chart-question">Le marché est-il globalement fort ou faible ?</span></div>
          <div id="vx-mk-dist"></div>
          <div class="vx-card-foot"><span class="vx-meta">Nombre de titres par tranche de score Vertex (0-100). Décalage à droite = univers globalement fort.</span></div>
        </section>
      </div>
      <section class="vx-card" id="vx-mk-health-card" aria-label="Composition de la santé du marché" hidden>
        <div class="vx-chart-head"><span class="vx-chart-title">Composition de la santé du marché</span>
          <span class="vx-chart-question">D’où vient le score de santé ?</span></div>
        <div id="vx-mk-health-wf" style="height:240px"></div>
        <div class="vx-card-foot"><span class="vx-meta">Santé = 30&nbsp;% (&gt;MM50) + 25&nbsp;% (&gt;MM200) + 25&nbsp;% (breadth) + 20&nbsp;% (avancées/déclins). Contributions pondérées du moteur d’internals — aucune pondération inventée.</span></div>
      </section>
      <section class="vx-card" aria-label="Limites des données de breadth">
        <div class="vx-insight">Breadth, participation (&gt;MM50/MM200), avancées/déclins,
        nouveaux hauts/bas et distribution des scores sont calculés sur l’<b>univers des leaders
        scannés</b> (univers partiel, pas l’ensemble du NYSE). Advance/decline cumulés
        multi-séances ne sont pas fournis — non affichés plutôt qu’inventés.</div>
      </section>
    </div>
  </div>
</details>
""",
    'volatility': """
<!-- Une seule lecture visuelle du VIX. Le contexte de régime reste textuel et replié. -->
<div class="vx-section-stack vx-mt3">
  <section class="vx-card vx-card--hero" id="vx-mk-vix" aria-label="VIX">
    <div class="vx-card-header"><span class="vx-card-title">VIX — volatilité implicite du marché</span></div>
    <div id="vx-mk-vix-body">%%LOADING%%</div>
  </section>
  <details class="vx-disclosure vx-markets-volatility-details">
    <summary>Contexte de régime et volatilité par titre</summary>
    <div class="vx-disclosure__body">
      <div class="vx-hero-grid">
        <aside class="vx-insight-rail" style="grid-template-columns:minmax(0,1fr)">
          <section class="vx-card" aria-label="Contexte de volatilité">
            <div class="vx-card-header"><span class="vx-card-title">Contexte — régime</span></div>
            <div id="vx-mk-vol-rail">%%LOADING%%</div>
          </section>
        </aside>
        <section class="vx-card" aria-label="Volatilité implicite par symbole">
          <div class="vx-card-header"><span class="vx-card-title">IV par symbole</span></div>
          <div class="vx-insight">La term structure de volatilité implicite par symbole est
          disponible dans la fiche analyse de chaque titre (onglet Options). Cette vue
          couvre la volatilité de marché (VIX) et le contexte de régime fournis par le moteur.</div>
          <div class="vx-mt3"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/analysis">Ouvrir une fiche analyse →</a></div>
        </section>
      </div>
    </div>
  </details>
</div>
""",
}

_JS = r"""
<script src="/static/vertex/js/charts/line-area-chart.js" defer></script>
<script src="/static/vertex/js/charts/bar-chart.js" defer></script>
<script src="/static/vertex/js/charts/heatmap.js" defer></script>
<script src="/static/vertex/js/charts/donut-chart.js" defer></script>
<script src="/static/vertex/js/charts/timeline-chart.js" defer></script>
<script>
(function(){
'use strict';
const VIEW='%%VIEW%%';
const $=(id)=>document.getElementById(id);
//  ECRIRE DANS UN HOTE QUI N'EST PLUS LA. Cette page a des vues
//  (?view=regime, sectors, macro...) : changer de vue REMPLACE le DOM, et
//  une requete encore en vol reprend la main ensuite sur un element
//  supprime — d'ou « unhandledrejection: Cannot set properties of null
//  (setting 'innerHTML') » sur /markets, intermittent et donc longtemps mis
//  sur le compte du hasard. Le fichier gardait DEJA trois ecritures
//  (`if(el)`, `if(t)`, `if(f)`) et laissait les autres nues : c'est
//  l'incoherence qui laissait passer la course, pas l'absence d'idee.
//  `(...||{}).innerHTML=` ecrit dans un objet jetable quand l'hote a
//  disparu : il n'y a plus rien a peindre, et la promesse ne se rompt pas.

function esc(s){return String(s??'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));}
function modeOf(scan){return scan&&scan.data_source==='demo'?'fallback':(scan&&scan.source==='ibkr'?'live':'delayed');}
// Contexte de marché = market_ctx (régime/vix/breadth/verdict) FUSIONNÉ avec
// market (statut horaire). Avant, `market` (et/open/session) masquait tout le
// contexte via `||` — d'où « verdict non calculé » et VIX/breadth vides à tort.
function mkt(scan){if(!scan)return {};return Object.assign({},scan.market||{},scan.market_ctx||{});}
async function getScan(){try{return await VX.fetch('/scan',{ttl:120000});}catch(e){return null;}}
function demoBanner(scan){
  if(scan&&scan.data_source==='demo'&&$('vx-demo-banner'))
    ($('vx-demo-banner')||{}).innerHTML='<div class="vx-demo-banner"><span class="vx-badge-demo">Démo</span> Données synthétiques clairement identifiées — jamais présentées comme réelles.</div>';
}
function emptyCard(host,reason,action,titre){
  const el=$(host);if(!el)return;
  el.innerHTML='<div class="vx-card">'
    +(titre?'<div class="vx-card-header"><span class="vx-card-title">'+titre+'</span></div>':'')
    +VX.states.empty(reason,action||'')+'</div>';
}
const SCAN_ACTION='<a class="vx-btn vx-btn-sm" href="/system?view=data">Système / Données</a>';

/* ═══ OVERVIEW ═══ */
/* Étiquettes FR + tonalité sémantique des régimes du moteur (jamais un code brut
   « UNKNOWN » affiché en grand : tonalité go=porteur, risk=défensif, ''=neutre). */
/* Vocabulaire humain des régimes : source unique VX.regime (vx-core.js) —
   conservé ici sous forme de triplets [label, tone, hint] pour le rendu. */
const REGIME_LABEL=Object.fromEntries(Object.entries(VX.regime.MAP)
  .map(([k,m])=>[k,[m.label,m.tone,m.hint]]));
/* Signaux SECONDAIRES du moteur de régimes : libellés français (mesuré au
   navigateur en mode peuplé : « YIELD_CURVE_INVERTED » sortait brut). Un
   jeton inconnu retombe sur le libellé du régime principal s'il en est un,
   sinon reste affiché tel quel — honnête, jamais masqué. */
const SECONDARY_LABEL={YIELD_CURVE_INVERTED:'Courbe des taux inversée',
  YIELD_CURVE_STEEP:'Courbe des taux pentue',BREADTH_DIVERGENCE:'Divergence de participation',
  DOLLAR_STRENGTHENING:'Dollar en renforcement',DOLLAR_WEAKENING:'Dollar en affaiblissement'};
const secFr=(t)=>SECONDARY_LABEL[t]||(REGIME_LABEL[t]?REGIME_LABEL[t][0]:t);
const SETUP_LABEL={BALANCED:'Équilibrée',BREAKOUT_PULLBACK:'Cassure / pullback',DEFENSIVE:'Défensive',
  MEAN_REVERSION:'Retour moyenne',MOMENTUM:'Momentum',QUALITY_DEFENSIVE:'Qualité défensive',
  CAPITAL_PRESERVATION:'Préservation capital',TAKE_PROFITS:'Prises de bénéfices',
  BREAKOUT_WATCH:'Veille de cassure',ATTENDRE:'Attendre'};
/* Mini-signal à rail (VIX / participation) pour l'état compact du hero régime. */
function sigRail(k,vtxt,pct,col){
  const w=(pct==null)?0:Math.max(0,Math.min(100,pct));
  return `<div class="vx-mk-sig"><span class="k">${k}</span><span class="v">${vtxt}</span>`
    +(pct==null?'':`<span class="vx-mk-sig-rail"><i style="width:${w.toFixed(0)}%;background:${col}"></i></span>`)+`</div>`;
}
function sigText(k,vtxt){return `<div class="vx-mk-sig"><span class="k">${k}</span><span class="v" style="font-size:15px">${vtxt}</span></div>`;}
async function loadRegime(scan){
  try{
    const r=await VX.fetch('/api/market/regime',{ttl:120000});
    const adj=r.adjustments||{};
    const conf=Math.round((r.confidence||0)*100);
    const dims=(r.dimensions_used||[]).length;
    const rStamp=r.as_of||r.timestamp||r.updated||null;
    /* État honnête MAIS compact & éditorial : moins de 3 dimensions → régime
       réellement INCONNU. On n'affiche PAS un « UNKNOWN » géant à 0 % NI 40 % de
       vide : on explique, puis on montre les signaux de marché RÉELLEMENT
       disponibles (VIX, participation, régime S&P, risk-on/off) issus du scan. */
    if(r.regime==='UNKNOWN'||!REGIME_LABEL[r.regime]){
      const m=mkt(scan);const CO=(window.VXCharts&&VXCharts.colors)||{};
      const sigs=[];
      if(m.vix!=null&&!isNaN(m.vix)){const v=Number(m.vix);
        sigs.push(sigRail('VIX',v.toFixed(1),(v-10)/30*100,v<15?CO.positive:v<25?CO.warning:CO.negative));}
      if(m.breadth!=null&&!isNaN(m.breadth)){const b=Number(m.breadth);
        sigs.push(sigRail('Participation &gt;MM50',Math.round(b)+' <small>%</small>',b,b>=55?CO.positive:b>=45?CO.warning:CO.negative));}
      if(m.spy_regime)sigs.push(sigText('Régime S&amp;P 500',
        esc({TREND:'Tendance',CHOP:'Sans direction',UP:'Haussier',DOWN:'Baissier'}[m.spy_regime]||m.spy_regime)));
      if(m.roro)sigs.push(sigText('Risk-on / risk-off',esc(m.roro)));
      ($('vx-mk-regime-body')||{}).innerHTML=
        `<div class="vx-mk-regime-compact">
          <div class="vx-mk-regime-lead">
            <span class="tag">Régime non qualifié</span>
            <span class="txt">Lecture du marché en cours — moins de 3 dimensions qualifiées (${dims} évaluée${dims>1?'s':''}) ; le moteur reste honnête et <b>bloque le nouveau risque</b>. Voici les signaux déjà disponibles :</span>
          </div>
          ${sigs.length?`<div class="vx-mk-sigrow">${sigs.join('')}</div>`:'<div class="vx-help">Aucun signal de marché fourni par le dernier scan.</div>'}
          <div class="vx-flex" style="gap:8px;margin-top:2px">${SCAN_ACTION}
            <span class="vx-meta" style="margin-left:auto">${VX.updateIndicator(rStamp,'Moteur de régimes','delayed')}</span></div>
        </div>`;
      return;
    }
    const meta=REGIME_LABEL[r.regime];
    const allowed=adj.new_risk_allowed;
    const chip=(k,v,st)=>`<div class="vx-mk-chip"${st?` data-state="${st}"`:''}><span class="k">${k}</span><span class="v">${v}</span></div>`;
    ($('vx-mk-regime-body')||{}).innerHTML=
      `<div class="vx-mk-regime-lead">
        <div class="vx-mk-regime-name" data-tone="${meta[1]}" data-regime="${esc(r.regime)}">${meta[0]}</div>
        <div class="vx-mk-regime-sub">${meta[2]} · ${dims} dimensions évaluées${(r.secondary&&r.secondary.length)?' · aussi '+esc(secFr(r.secondary[0])):''}</div>
        <div class="vx-mk-chips">
          ${chip('Nouveau risque',allowed?'Autorisé':'BLOQUÉ',allowed?'on':'off')}
          ${chip('Confiance',conf+' %')}
          ${chip('Priorité setups',VX.fmt.nd(SETUP_LABEL[adj.setup_priority]||adj.setup_priority))}
          ${chip('Confirmations',VX.fmt.nd(adj.confirmation_required))}
        </div>
      </div>
      <div class="vx-card-footer">${VX.updateIndicator(rStamp,'Moteur de régimes','delayed')}</div>`;
  }catch(e){($('vx-mk-regime-body')||{}).innerHTML=VX.states.error('Régime indisponible');}
}
function moversRows(rows,dir){
  const sorted=(rows||[]).filter(r=>r.change!==null&&r.change!==undefined).slice()
    .sort((a,b)=>dir==='top'?(b.change-a.change):(a.change-b.change)).slice(0,10);
  if(!sorted.length)return VX.states.empty('Aucune variation exploitable dans le dernier scan.');
  /* LOT 140 : l'ampleur de chaque variation gagne sa mini-barre de VERRE
     signee (echelle relative au max de la liste, patron 132-139) — la
     hierarchie des mouvements se voit sans lire les pourcentages. */
  const maxAbs=Math.max(0.1,...sorted.map(r=>Math.abs(r.change)));
  const chgBar=(chg)=>{const neg=chg<0;
    const tok=neg?'var(--vx-negative,#E9555F)':'var(--vx-positive,#2BBE90)';
    const w=Math.max(5,Math.abs(chg)/maxAbs*100);
    return '<span style="width:44px;height:7px;background:var(--vx-surface-3,#121214);border-radius:3px;overflow:hidden;display:inline-block;flex:none">'
      +'<span style="display:block;height:100%;width:'+w.toFixed(0)+'%;background:linear-gradient('+(neg?'270deg':'90deg')+',color-mix(in srgb,'+tok+' 35%,transparent),'+tok+');border-radius:3px'+(neg?';margin-left:auto':'')+'"></span></span>';};
  return sorted.map(function(r){const chg=r.change;
    return `<div class="vx-flex" style="padding:6px 0;border-bottom:1px dashed var(--vx-border-soft)">
      <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(r.symbol)}">${esc(r.symbol)}</button>
      ${chgBar(chg)}
      <span class="vx-num vx-mono ${chg>0?'vx-pos':chg<0?'vx-neg':'vx-muted'}" style="width:62px;text-align:right;font-weight:700">${VX.fmt.pct(chg,1)}</span>
      <span class="vx-grow vx-truncate vx-dim" style="font-size:11.5px" title="${esc(r.sector||'')}">${esc(r.sector||'')}</span>
      <span class="vx-num vx-mono vx-meta" style="width:64px;text-align:right">${r.price!==null&&r.price!==undefined?VX.fmt.price(r.price):''}</span>
      ${r.score!==null&&r.score!==undefined?`<span class="vx-badge" title="Score Vertex">${VX.fmt.num(r.score,0)}</span>`:''}
      <button class="vx-btn vx-btn-icon vx-btn-ghost" data-entity-menu="${esc(r.symbol)}" aria-label="Actions ${esc(r.symbol)}">⋯</button></div>`;}).join('');
}
function loadMovers(scan){
  const rows=(scan&&scan.rows)||[];
  const t=$('vx-mk-top'),f=$('vx-mk-flop');
  const foot=`<div class="vx-card-footer">${VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))} · ${rows.length} titres scannés</div>`;
  if(t)t.innerHTML=moversRows(rows,'top')+foot;
  if(f)f.innerHTML=moversRows(rows,'flop')+foot;
}
function loadLeader(scan){
  const sectors=(scan&&scan.sectors)||[];
  if(!sectors.length||typeof sectors[0]!=='object'){
    ($('vx-mk-leader-body')||{}).innerHTML=VX.states.empty('Secteurs non calculés par le dernier scan.',SCAN_ACTION);return;
  }
  const top=sectors[0];
  const topLeader=top.leader&&(top.leader.symbol||((typeof top.leader==='string')?top.leader:null));
  /* Classement visuel des secteurs meneurs : score en barre (hiérarchie par
     intensité, pas arc-en-ciel) — remplit la carte et se lit d'un coup d'œil. */
  const withScore=sectors.filter(s=>s.avg_score!=null);
  const maxSc=Math.max(1,...withScore.map(s=>s.avg_score));
  /* LOT 139 : barres en VERRE — degrade de leur propre couleur (doux -> dense,
     patron 130-138) et le MENEUR garde l'ember avec un halo doux. */
  const rank=withScore.slice(0,5).map((s,i)=>{
    const L=s.leader&&(s.leader.symbol||((typeof s.leader==='string')?s.leader:null));
    const w=Math.max(6,Math.round((s.avg_score/maxSc)*100));
    const tok=i===0?'var(--vx-ember-500)':'var(--vx-warm-grey)';
    const fill='background:linear-gradient(90deg,color-mix(in srgb,'+tok+' 40%,transparent),'+tok+')'
      +(i===0?';box-shadow:0 0 6px color-mix(in srgb,var(--vx-ember-500) 45%,transparent)':'');
    return `<div class="vx-mk-lead-row">
      <span class="vx-mk-lead-name" title="${esc(s.sector||'')}">${esc(s.sector||'n/d')}</span>
      <span class="vx-mk-lead-bar"><i style="width:${w}%;${fill}"></i></span>
      <span class="vx-mk-lead-sc">${VX.fmt.nd(s.avg_score)}</span>
      ${L?`<button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(L)}" title="Leader ${esc(L)}">${esc(L)}</button>`:'<span class="vx-meta">—</span>'}
    </div>`;}).join('');
  ($('vx-mk-leader-body')||{}).innerHTML=
    `<div class="vx-mk-lead-hero">
       <span class="vx-mk-lead-top">${esc(top.sector||'n/d')}</span>
       <span class="vx-meta">secteur meneur · score moyen ${VX.fmt.nd(top.avg_score)}${topLeader?' · leader '+esc(topLeader):''}</span>
     </div>
     <div class="vx-mk-lead-list">${rank}</div>
     <div class="vx-card-footer">${VX.updateIndicator(scan.scan_ts||scan.updated,scan.source||'scan',modeOf(scan))}</div>`;
}
function loadRisk(scan){
  const m=mkt(scan);
  if(!m.verdict&&!m.roro){
    ($('vx-mk-risk-body')||{}).innerHTML=VX.states.empty('Verdict marché non calculé — lancer un scan.',SCAN_ACTION);return;
  }
  ($('vx-mk-risk-body')||{}).innerHTML=
    (m.verdict?`<div style="font-size:14px;line-height:1.7">${esc(m.verdict)}</div>`:'')
    +(m.roro?`<div class="vx-kv vx-mt2"><span class="k">Risk-on / risk-off</span><span class="v">${esc(m.roro)}</span></div>`:'')
    +(m.spy_regime?`<div class="vx-kv"><span class="k">Régime S&amp;P 500</span><span class="v">${esc(m.spy_regime)}</span></div>`:'')
    +`<div class="vx-card-footer">${VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))}</div>`;
}
function idxByName(scan){
  const list=(scan&&Array.isArray(scan.indices))?scan.indices:[];
  const by={};list.forEach(i=>{if(i&&i.name)by[i.name]=i;});return by;
}
/* Source cross-asset UNIFIÉE : indices actions (scan.indices : .price/.change %),
   taux & dollar (scan.macro : .value + .chg en POINTS absolus, pas %), matières &
   crypto (scan.commodities : .price/.change %). Normalise les noms (WTI→Pétrole,
   Dollar (DXY)→DXY). Aucun point inventé — un actif absent du scan est simplement omis. */
function crossAsset(scan){
  const m={};
  ((scan&&scan.indices)||[]).forEach(i=>{if(i&&i.name)m[i.name]={last:i.price,change:i.change,series:i.spark};});
  ((scan&&scan.commodities)||[]).forEach(c=>{if(c&&c.name){const nm=(c.name==='WTI')?'Pétrole':c.name;
    m[nm]={last:c.price,change:c.change,series:c.spark};}});
  /* `x.date` = date de la DERNIÈRE BARRE de l'indicateur, produite par le
     collecteur. Elle était supprimée ici : le KPI « Taux 10 ans 4,78 % »
     s'affichait nu pendant que la courbe des taux juste dessous, bâtie sur le
     MÊME tableau scan.macro, portait « Il y a 16 min · yfinance Différé ».
     Un dimanche, le lecteur ne pouvait pas savoir que 4,78 % est la clôture
     de vendredi (invariant 6 : la valeur porte son timestamp). Indices et
     matières n'ont pas ce champ : `obs` reste absent — rien n'est fabriqué. */
  ((scan&&scan.macro)||[]).forEach(x=>{if(x&&x.name){const nm=(x.name==='Dollar (DXY)')?'DXY':x.name;
    m[nm]={last:x.value,change:x.chg,unit:x.unit,deltaUnit:'pts',deltaNeutral:true,obs:x.date||null};}});
  return m;
}
/* Lissage MONOTONE (Fritsch-Carlson) — même principe que le 'monotone' des
   graphiques Chart.js (lot 51) : la courbe ne dépasse JAMAIS les données
   réelles, les points restent exacts, calcul déterministe. */
function monotonePath(xs,ys){
  const n=xs.length;
  if(n<3)return 'M'+xs.map((x,i)=>x.toFixed(1)+','+ys[i].toFixed(1)).join(' L');
  const dx=[],m=[],t=new Array(n);
  for(let i=0;i<n-1;i++){dx.push(xs[i+1]-xs[i]);m.push((ys[i+1]-ys[i])/(dx[i]||1));}
  t[0]=m[0];t[n-1]=m[n-2];
  for(let i=1;i<n-1;i++)t[i]=(m[i-1]*m[i]<=0)?0:(m[i-1]+m[i])/2;
  for(let i=0;i<n-1;i++){
    if(m[i]===0){t[i]=0;t[i+1]=0;continue;}
    const a=t[i]/m[i],b=t[i+1]/m[i],s=a*a+b*b;
    if(s>9){const k=3/Math.sqrt(s);t[i]=k*a*m[i];t[i+1]=k*b*m[i];}
  }
  let d='M'+xs[0].toFixed(1)+','+ys[0].toFixed(1);
  for(let i=0;i<n-1;i++){const g=dx[i]/3;
    d+=' C'+(xs[i]+g).toFixed(1)+','+(ys[i]+g*t[i]).toFixed(1)
      +' '+(xs[i+1]-g).toFixed(1)+','+(ys[i+1]-g*t[i+1]).toFixed(1)
      +' '+xs[i+1].toFixed(1)+','+ys[i+1].toFixed(1);}
  return d;
}
/* Mini-area premium : chemin lissé monotone + remplissage dégradé + point
   actif final (signature 2026, lot 63 — même langage que C.area). `tone`
   ∈ up|down|flat|tech pilote la couleur (sémantique). */
let _AREA=0;
function sparkArea(vals,tone,h){
  if(!Array.isArray(vals)||vals.length<2)return '<svg aria-hidden="true"></svg>';
  h=h||40;const w=140,pad=2,mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rng=(mx-mn)||1;
  const uid='ar'+(++_AREA);
  const xs=vals.map((_,i)=>i/(vals.length-1)*w);
  const ys=vals.map(v=>h-pad-((v-mn)/rng)*(h-2*pad));
  const line=monotonePath(xs,ys);
  const area=line+' L'+w+','+h+' L0,'+h+' Z';
  const col=tone==='up'?'var(--vx-positive)':tone==='down'?'var(--vx-negative)':tone==='tech'?'var(--vx-technical)':'var(--vx-warm-grey)';
  const lx=xs[xs.length-1].toFixed(1),ly=ys[ys.length-1].toFixed(1);
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" width="100%" height="${h}" aria-hidden="true">
    <defs><linearGradient id="${uid}" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="${col}" stop-opacity=".28"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <path d="${area}" fill="url(#${uid})"/>
    <path d="${line}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
    <circle cx="${lx}" cy="${ly}" r="2.4" fill="${col}"/></svg>`;
}
const MONO={'S&P 500':'S&P','Nasdaq':'NDQ','Dow Jones':'DJIA','Russell 2000':'RUT',
  'Taux 10 ans':'10Y','DXY':'DXY','Pétrole':'WTI','Or':'AU','Bitcoin':'BTC'};
/* Position relative de la dernière valeur dans la plage de la série fournie
   (transformation d'affichage — aucun point inventé). */
function relInRange(vals){
  if(!Array.isArray(vals)||vals.length<3)return null;
  const mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rng=(mx-mn)||1;
  const p=(vals[vals.length-1]-mn)/rng;return {pct:p,mn,mx};}
/* Carte indice premium : monogramme · valeur · variation · mini-area · plage · état relatif. */
function indexCard(label,d,scan){
  const val=d&&(d.last??d.price??d.close);const chg=(d&&d.change!=null)?d.change:null;
  const dir=chg>0?'up':chg<0?'down':'flat';
  const chgTxt=chg==null?'n/d':(d&&d.deltaUnit?((chg>0?'+':'')+VX.fmt.num(chg,2)+' '+d.deltaUnit):VX.fmt.pct(chg));
  const vtxt=(val==null)?'—':(VX.fmt.price(val)+((d&&d.unit)?' '+d.unit:''));
  const ser=(d&&d.series&&d.series.length>2)?d.series:null;
  const rel=ser?relInRange(ser):null;
  const relTxt=rel?(rel.pct>=.66?'près du haut':rel.pct<=.33?'près du bas':'milieu de plage'):'';
  const rangeTxt=rel?('plage '+VX.fmt.price(rel.mn)+'–'+VX.fmt.price(rel.mx)):'';
  const tone=(d&&d.deltaNeutral)?'flat':dir;
  return `<div class="vx-mk-idx" data-dir="${tone}" aria-label="${esc(label)}">
    <div class="vx-mk-idx-top">
      <span class="vx-mk-mono">${MONO[label]||esc(label).slice(0,3).toUpperCase()}</span>
      <span class="vx-mk-idx-name">${esc(label)}</span>
      ${relTxt?`<span class="vx-mk-idx-rel">${relTxt}</span>`:''}
    </div>
    <div class="vx-mk-idx-valrow">
      <span class="vx-mk-idx-val">${vtxt}</span>
      <span class="vx-mk-idx-chg ${tone}">${chgTxt}</span>
    </div>
    <div class="vx-mk-area">${ser?sparkArea(ser,tone,40):''}</div>
    <div class="vx-mk-idx-foot"><b>${rangeTxt||'&nbsp;'}</b><span>${VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))}</span></div>
  </div>`;
}
/* Carte macro premium : aire à droite (plus de demi-carte vide) + relation clé. */
function macroCard(label,d,scan,note){
  const val=d&&(d.last??d.price??d.close);const chg=(d&&d.change!=null)?d.change:null;
  const dir=chg>0?'up':chg<0?'down':'flat';const tone=(d&&d.deltaNeutral)?'flat':dir;
  const chgTxt=chg==null?'n/d':(d&&d.deltaUnit?((chg>0?'+':'')+VX.fmt.num(chg,2)+' '+d.deltaUnit):VX.fmt.pct(chg));
  const vtxt=(val==null)?'—':(VX.fmt.price(val)+((d&&d.unit)?' '+d.unit:''));
  const ser=(d&&d.series&&d.series.length>2)?d.series:null;
  const chgHtml=`<span class="m-chg ${tone}">${chgTxt}${(d&&d.deltaNeutral)?' <span style="color:var(--vx-text-muted);font-weight:600">· niveau</span>':''}</span>`;
  /* Le strip macro était la SEULE exception à la convention maison : 4 cartes,
     0 élément de provenance, quand indexCard, la courbe des taux et les
     références officielles portent toutes la leur. La date d'observation est
     celle de la source quand elle existe (obs), l'indicateur de scan dit
     l'âge de l'instantané. Sans obs (Pétrole, Or), seul l'indicateur : aucune
     date fabriquée. */
  const foot=`<div class="m-foot">${(d&&d.obs)?'observé le '+esc(dateFrOff(d.obs))+' · ':''}`
    +`${VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))}</div>`;
  /* Sans série : layout compact plein-largeur (JAMAIS de demi-carte vide). */
  if(!ser){
    return `<div class="vx-mk-macro vx-mk-macro--flat" aria-label="${esc(label)}">
      <div class="m-head"><span class="m-mono">${MONO[label]||esc(label).slice(0,3).toUpperCase()}</span><span class="m-name">${esc(label)}</span></div>
      <div class="mf-row"><span class="m-val">${vtxt}</span>${chgHtml}</div>
      ${note?`<div class="m-note">${note}</div>`:''}
      ${foot}
    </div>`;
  }
  return `<div class="vx-mk-macro" aria-label="${esc(label)}">
    <div class="m-head"><span class="m-mono">${MONO[label]||esc(label).slice(0,3).toUpperCase()}</span><span class="m-name">${esc(label)}</span></div>
    <div class="m-val">${vtxt}</div>
    ${chgHtml}
    <div class="m-area">${sparkArea(ser,tone==='flat'?'tech':tone,56)}</div>
    ${note?`<div class="m-note">${note}</div>`:''}
    ${foot}
  </div>`;
}
const IDX_MAIN=['S&P 500','Nasdaq','Dow Jones','Russell 2000'];
function loadStrip(scan){
  const by=crossAsset(scan);
  const known=IDX_MAIN.filter(n=>by[n]&&(by[n].last!==null&&by[n].last!==undefined)).slice(0,4);
  if(!known.length){
    ($('vx-mk-strip')||{}).innerHTML='<div class="vx-col-12">'+VX.states.empty('Indices indisponibles — lancer un scan depuis Système.',SCAN_ACTION)+'</div>';return;
  }
  ($('vx-mk-strip')||{}).innerHTML=known.map(label=>
    '<div class="vx-kpi vx-markets-index-kpi">'+indexCard(label,by[label],scan)+'</div>').join('');
}
/* Comparaison multi-indices : chaque série rebasée à 0 % (transformation
   d'affichage des séries fournies — aucun point inventé). */
function loadMultiIndex(scan){
  const by=idxByName(scan);
  const wanted=['S&P 500','Nasdaq','Dow Jones','Russell 2000'];
  const sets=wanted.map(n=>({n,spark:(by[n]&&by[n].spark)||[]})).filter(x=>x.spark.length>5);
  if(!sets.length){emptyCard('vx-mk-multi','Séries indices indisponibles dans le dernier scan.',SCAN_ACTION,
    'Comparaison des indices');return;}
  const len=Math.min(...sets.map(x=>x.spark.length));
  const labels=Array.from({length:len},(_,i)=>i-len);
  window.VXCharts.card('vx-mk-multi',{
    title:'Indices — performance comparée',unit:'%',timeframe:len+' points',
    question:'Qui mène : large caps, tech ou small caps ?',
    conclusion:'Chaque indice rebasé à 0 % en début de fenêtre.',
    height:240,source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
    legend:wanted.map((n,i)=>({label:n,color:VXCharts.colors.series[i%6]})),
    explain:{shows:'Les mêmes séries d’indices que le bandeau, rebasées à 0 % pour comparer la force relative.',
      why:'Le leadership (tech vs small caps) qualifie l’appétit pour le risque.',
      confirm:'Small caps et tech au-dessus des large caps — appétit confirmé.',
      invalidate:'Défensives seules en tête — régime prudent.'},
    render:(cv)=>VXCharts.multiLine(cv,labels,
      sets.map(x=>({label:x.n,data:x.spark.slice(-len).map(v=>x.spark[x.spark.length-len]?(v/x.spark[x.spark.length-len]-1)*100:0)})),
      {yFmt:(v)=>v.toFixed(1)+' %'})});
}
function loadSpyChart(scan){
  const det=(scan&&scan.detail)||{};
  const okSeries=(k)=>det[k]&&det[k].series&&Array.isArray(det[k].series.close)&&det[k].series.close.length>10;
  // Comme le Briefing (briefing.py, loadMainChart) : SPY → INDICE « S&P 500 »
  // du scan (120 clôtures servies par le serveur) → dernier recours, 1er titre
  // porteur d'une série RÉELLE, étiqueté proxy.
  // Mesure du 06/09/2026 : l'étage INDICE manquait ici alors qu'il existe dans
  // le Briefing. L'univers scanné (513 constituants, aucun ETF indiciel) rend
  // `hasSpy` toujours faux, et Object.keys() étant ordonné, la carte traçait
  // DÉTERMINISTEMENT 'MMM' (3M, 139–183 USD) sous le titre « série de référence
  // marché », l'unité « points d'indice » et le verdict de régime du marché —
  // pendant que la page Aujourd'hui traçait, du MÊME payload, le vrai S&P 500
  // (6344–7799). Deux autorités pour une métrique : celle-ci était amputée.
  const hasSpy=okSeries('SPY');
  const spx=((scan&&scan.indices)||[]).find(i=>i&&i.name==='S&P 500');
  const hasIdx=!hasSpy&&!!(spx&&Array.isArray(spx.series)&&spx.series.length>10);
  const key=hasSpy?'SPY':(hasIdx?'S&P 500':Object.keys(det).find(okSeries));
  const closes=hasIdx?spx.series:((key&&det[key]&&det[key].series&&det[key].series.close)||[]);
  const m=mkt(scan);
  if(closes.length>10){
    const title=hasSpy?'S&P 500 (SPY) — série de référence'
                      :(hasIdx?'S&P 500 — série de référence'
                              :('Marché — série de référence · '+key+' (ni SPY ni indice S&P 500 dans le scan)'));
    VXCharts.areaCard('vx-mk-spy',{
      /* Unité : « points d'indice » n'est vrai QUE sur une série d'indice. Sur
         le proxy (un titre), la même étiquette annonçait une unité fausse
         au-dessus d'un cours en dollars (invariant 6). */
      title:title,unit:(hasSpy||hasIdx)?'points d’indice':'USD',timeframe:closes.length+' séances',
      question:'La tendance de fond reste-t-elle exploitable ?',
      conclusion:(m.spy_regime==='TREND'?'Tendance intacte':'Régime '+(m.spy_regime||'n/d'))+(m.verdict?' — '+m.verdict:''),
      labels:closes.map((_,i)=>i-closes.length),values:closes,height:260,
      /* GRAMMAIRE TV (lot 200) : chips Max/Min = les bornes RÉELLES de la série */
      extremes:true,
      source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
      explain:{shows:(hasSpy?'Les clôtures de SPY':hasIdx?'Les clôtures de l’indice S&P 500'
                      :'Les clôtures de '+key+' (proxy : ni SPY ni indice S&P 500 dans ce scan — la conclusion ci-dessus porte sur le RÉGIME DE MARCHÉ, pas sur cette série)')
                     +' telles que fournies par le scan (aucun indicateur recalculé côté UI).',
        why:'La Stratégie Vertex n’attaque qu’en environnement porteur : le régime module seuils et tailles.',
        confirm:'Clôtures au-dessus des dernières résistances avec breadth > 55 %.',
        invalidate:'Cassure des supports avec expansion de volatilité.'}});
  }else{
    emptyCard('vx-mk-spy','Série de référence indisponible — lancer un scan depuis Système.',SCAN_ACTION,
      'Graphique de référence — S&amp;P 500');
  }
}

/* ═══ MACRO ═══ */
const MACRO_NAMES=['Taux 10 ans','DXY','Pétrole','Or','Bitcoin'];
/* Relation clé de chaque actif macro (contexte de lecture — texte, jamais un chiffre inventé). */
const MACRO_NOTE={
  'Taux 10 ans':'Coût de l’argent long — hausse = pression sur les valorisations.',
  'DXY':'Dollar fort = vent de face pour actifs risqués et matières.',
  'Pétrole':'Baromètre d’inflation et de demande cyclique.',
  'Or':'Refuge — monte souvent quand l’aversion au risque grandit.',
  'Bitcoin':'Actif risque à bêta élevé — proxy d’appétit spéculatif.'};
function loadMacroKpis(scan){
  const by=crossAsset(scan);
  const known=MACRO_NAMES.filter(n=>by[n]&&by[n].last!==null&&by[n].last!==undefined);
  if(!known.length){
    ($('vx-mk-macro-kpis')||{}).innerHTML='<div class="vx-col-12">'+VX.states.empty('Données macro non fournies par le scan — rien d’inventé.',SCAN_ACTION)+'</div>';return;
  }
  /* Premier écran = quatre KPI maximum. Les actifs supplémentaires restent
     disponibles sous disclosure, sans suppression de donnée ni de source. */
  const primary=known.slice(0,4),extra=known.slice(4);
  ($('vx-mk-macro-kpis')||{}).innerHTML=primary.map(n=>
    '<div class="vx-kpi vx-markets-macro-kpi">'+macroCard(n,by[n],scan,MACRO_NOTE[n])+'</div>').join('');
  const x=$('vx-mk-macro-extra');
  if(x){
    x.innerHTML=extra.length
      ?'<section class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Cross-asset complémentaire</span></div>'
        +extra.map(n=>macroCard(n,by[n],scan,MACRO_NOTE[n])).join('')
        +'<div class="vx-card-footer">'+VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))+'</div></section>'
      :'<section class="vx-card"><div class="vx-insight">Aucun actif macro supplémentaire fourni par le scan.</div></section>';
  }
}
/* Courbe des taux US — 4 maturités RÉELLES du scan (jamais interpolées) */
function loadYield(scan){
  const el=document.getElementById('vx-mk-yield');if(!el||!window.VXCharts)return;
  const macro=(scan&&scan.macro)||[];const byId={};macro.forEach(m=>{byId[m.id]=m;});
  const mats=[['^IRX','3M'],['^FVX','5A'],['^TNX','10A'],['^TYX','30A']];
  const pts=mats.filter(m=>byId[m[0]]&&byId[m[0]].value!=null);
  if(pts.length<2){emptyCard('vx-mk-yield','Courbe des taux indisponible — maturités non fournies par le scan.',SCAN_ACTION);return;}
  const labels=pts.map(m=>m[1]);
  const cur=pts.map(m=>byId[m[0]].value);
  const prev=pts.map(m=>byId[m[0]].prev!=null?byId[m[0]].prev:byId[m[0]].value);
  const t10=byId['^TNX'],t3=byId['^IRX'];
  const spread=(t10&&t3&&t10.value!=null&&t3.value!=null)?(t10.value-t3.value):null;
  const cc=VXCharts.colors;
  VXCharts.card('vx-mk-yield',{
    title:'Courbe des taux US',unit:'%',timeframe:'clôture',
    question:'La courbe est-elle normale ou inversée ?',
    conclusion:spread!=null?('Spread 10a-3m '+(spread>=0?'+':'')+spread.toFixed(2)+' pt — '+(spread<0?'INVERSÉE (signal de récession)':'pentue / normale')):'—',
    height:250,source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
    limits:'4 maturités réelles (3M/5A/10A/30A)',
    legend:[{label:'Actuelle',color:cc.info},{label:'Séance préc.',color:cc.neutral}],
    explain:{shows:'Le rendement du Trésor US par maturité (points réels du scan, non interpolés).',
      why:'Une courbe inversée (court > long) précède souvent les récessions et module l’appétit pour le risque.',
      confirm:'Repentification : le spread 10a-3m remonte durablement.',invalidate:'Inversion qui s’aggrave.'},
    render:(cv)=>VXCharts.multiLine(cv,labels,[
      {label:'Actuelle',data:cur,borderColor:cc.info,borderWidth:2.2,pointRadius:3,pointBackgroundColor:cc.info,fill:false},
      {label:'Séance préc.',data:prev,borderColor:cc.neutral,borderWidth:1.4,borderDash:[4,3],pointRadius:0,fill:false}
    ],{yFmt:(v)=>v+' %'})});
}
async function loadMacroRegime(){
  /* LOT 603 (dossier 531-A, suite) : un echec ne laisse plus la zone vide et
     muette. Invariant produit : donnee absente -> mention honnete. */
  var s=null,err=null;
  try{ s=await VX.fetch('/api/market/summary',{ttl:30000}); }catch(e){ err=e; }
  var el=$('vx-mk-macro-regime'); if(!el)return;
  if(err||!s){ el.innerHTML=VX.states.error('Appétit pour le risque indisponible'); return; }
  var gap=(typeof s.roro_gap==='number')?s.roro_gap:null,roro=s.roro||'—',br=s.breadth||{};
  var pos=gap!=null&&gap>=0,mag=gap==null?0:Math.min(100,Math.abs(gap)/25*100);
  var bar='<div style="position:relative;height:16px;background:var(--vx-surface-3);border-radius:6px;overflow:hidden;margin:6px 0">'
    +'<div style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--vx-border-strong)"></div>'
    +(gap==null?'':'<div style="position:absolute;top:2px;bottom:2px;'+(pos?'left:50%':'right:50%')+';width:'+(mag/2).toFixed(0)+'%;background:'+(pos?'var(--vx-positive)':'var(--vx-negative)')+';border-radius:3px"></div>')+'</div>';
  var brCls=function(x){return x==null?'':(x>=55?'vx-pos':x<=45?'vx-neg':'vx-warn');};
  var kv=function(l,v,vc){return '<div class="vx-kv"><span class="k">'+l+'</span><span class="v vx-mono '+(vc||'')+'">'+v+'</span></div>';};
  el.innerHTML='<section class="vx-card vx-col-12" aria-label="Appétit pour le risque">'
    +'<div class="vx-card-header"><span class="vx-card-title">Appétit pour le risque</span><span class="vx-chart-question">Risk-on ou risk-off ?</span></div>'
    +'<div style="font-size:22px;font-weight:800;color:'+(pos?'var(--vx-positive)':'var(--vx-negative)')+'">'+esc(roro)+'</div>'+bar
    +'<div class="vx-flex" style="justify-content:space-between"><span class="vx-meta">RISK-OFF</span><span class="vx-meta">écart '+(gap==null?'n/d':(gap>0?'+':'')+gap)+'</span><span class="vx-meta">RISK-ON</span></div>'
    +'<div class="vx-mt3">'
    +kv('Régime',esc(s.regime||'—'))
    +kv('VIX',s.vix!=null?esc(s.vix)+(s.vix_band?' · '+esc(s.vix_band):''):'—')
    +kv('&gt; MM50',br.above50!=null?br.above50+' %':'—',brCls(br.above50))
    +kv('&gt; MM200',br.above200!=null?br.above200+' %':'—',brCls(br.above200))
    +'</div><div class="vx-card-footer"><span class="vx-meta">Écart risk-on/risk-off du moteur (positif = appétit, négatif = aversion). Aucune valeur inventée.</span></div></section>';
}
/* Références macro OFFICIELLES (FRED, BCE, BNS) — instantané du collecteur de
   fond (/api/macro/officiel). Chaque tuile porte la valeur, l'unité, la DATE
   D'OBSERVATION chez la source (pas l'heure du clic), la fréquence et la source.
   Une série en échec dit son erreur ; jamais un zéro. */
const FREQ_FR={quotidien:'quotidien',mensuel:'mensuel',annuel:'annuel'};
function dateFrOff(s){
  const m=/^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(s||''));
  if(!m)return s||'—';
  return m[3]?(m[3]+'/'+m[2]+'/'+m[1]):(m[2]+'/'+m[1]);
}
function ageObs(iso){
  if(!iso)return null;
  const d=new Date(iso.length===7?iso+'-01T00:00:00Z':iso.length===10?iso+'T00:00:00Z':iso);
  return isNaN(d)?null:Math.round((Date.now()-d.getTime())/86400000);
}
/* Communiqués officiels (BCE, BNS) : même instantané que les références —
   titre, lien, date de la source (jamais le texte du communiqué). */
function paintCommuniques(d){
  const host=$('vx-mk-communiques-body');if(!host)return;
  const liste=(d&&d.communiques)||[];const err=(d&&d.communiques_erreurs)||{};
  if(!liste.length){
    host.innerHTML=VX.states.empty(Object.keys(err).length?'Flux injoignables : '+Object.keys(err).map(k=>esc(k)+' ('+esc(err[k])+')').join(' · ')
      :'Aucun communiqué encore collecté : le collecteur de fond passe toutes les '+(d&&d.cadence_min||360)+' min.');
    return;
  }
  host.innerHTML='<ul class="vx-mt1" style="margin:0;padding-left:0;list-style:none">'+liste.slice(0,16).map(c=>
    '<li class="vx-kv" style="align-items:flex-start;gap:10px"><span class="k" style="flex:0 0 auto"><span class="vx-badge">'+esc(c.source)+'</span> '
    /* `.slice(0,16)` DÉCAPITAIT le `Z` que le serveur pose exprès (vérifié par
       tests/test_communiques_officiels.py : published_at se termine par 'Z') :
       « 2026-09-04T09:10Z » s'affichait « 2026-09-04 09:10 », heure UTC nue au
       milieu de tampons en heure locale (« Il y a 25 min »). VX.fmt.instantSource
       convertit dans le fuseau du lecteur quand la source déclare le sien, et
       marque « fuseau n/d » sinon — jamais de fuseau inventé. */
    +'<span class="vx-mono" title="'+esc(VX.fmt.instantSourceNote(c.published_at))+'">'+esc(VX.fmt.instantSource(c.published_at)||'date n/d')+'</span></span>'
    +'<span class="v" style="text-align:left;white-space:normal"><a href="'+esc(c.link)+'" target="_blank" rel="noopener noreferrer">'+c.title+' ↗</a></span></li>').join('')+'</ul>'
    +'<div class="vx-table-stamp"><span>'+liste.length+' communiqués · '+(d.communiques_sources||[]).map(x=>'<b>'+esc(x.source)+'</b>').join(' · ')+'</span>'
    +'<span>'+VX.updateIndicator(d.as_of,'collecteur officiel','delayed')+'</span>'
    +(Object.keys(err).length?'<span class="vx-warn">'+Object.keys(err).map(k=>esc(k)+' : '+esc(err[k])).join(' · ')+'</span>':'')+'</div>'
    +'<div class="vx-meta vx-mt2">Dates et titres de la source, réutilisation avec attribution ; le texte des communiqués n’est pas repris.</div>';
}
async function loadMacroOfficiel(){
  const host=$('vx-mk-macro-officiel-body');if(!host)return;
  let d=null;
  try{ d=await VX.fetch('/api/macro/officiel',{ttl:60000}); }
  catch(e){ host.innerHTML=VX.states.error('Références officielles injoignables ('+esc(e.message)+')'); return; }
  paintCommuniques(d);
  const series=(d&&d.series)||[];
  if(!series.length){
    host.innerHTML=VX.states.empty('Aucune collecte encore effectuée : le collecteur de fond passe toutes les '+(d&&d.cadence_min||360)+' min.',null,{title:'Pas encore collecté'});
    return;
  }
  const zones=['US','Zone euro','Suisse'];
  const tuile=(s)=>{
    const absent=s.value==null;
    const dec=(s.unite==='USD'||s.unite==='CHF')?4:2;   /* change : 4 décimales, taux : 2 */
    const delta=(!absent&&s.previous!=null)?(s.value-s.previous):null;
    const dtone=delta==null?'':(delta>0?'pos':delta<0?'neg':'');
    const meta=absent
      ? ('indisponible · '+esc(s.error||'aucune observation'))
      : ('observé le '+dateFrOff(s.observed_at)+' · '+(FREQ_FR[s.frequence]||s.frequence)
         +(delta!=null?' · '+(delta>0?'+':'')+VX.fmt.num(delta,dec)+' '+esc(s.unite)+' vs '+dateFrOff(s.previous_at):''));
    return VX.tile.metric({k:s.libelle,v:absent?null:VX.fmt.num(s.value,dec),unit:absent?'':s.unite,tone:absent?'':dtone,meta:meta,kTitle:s.note||''});
  };
  let html='';
  zones.forEach(z=>{
    const rows=series.filter(s=>s.zone===z);if(!rows.length)return;
    html+='<div class="vx-meta" style="margin:8px 0 4px;text-transform:uppercase;letter-spacing:.06em">'+esc(z)+'</div>'
      +'<div class="vx-metricgrid vx-opt-kpis">'+rows.map(tuile).join('')+'</div>';
  });
  const src=d.sources||{};
  const foot='<div class="vx-table-stamp"><span>Sources : '+Object.keys(src).map(k=>'<b>'+esc(k)+'</b>').join(' · ')
    +'</span><span>'+d.disponibles+'/'+d.total+' séries publiées</span>'
    +'<span>'+VX.updateIndicator(d.as_of,'collecteur officiel','delayed')+'</span>'
    +(d.etat&&d.etat.derniere_erreur?'<span class="vx-warn">'+esc(d.etat.derniere_erreur)+'</span>':'')+'</div>'
    +'<div class="vx-meta vx-mt2">Publications officielles, jamais des cotations : la date affichée est celle de la source. Droits : affichage personnel avec attribution (FRED, BCE, BNS).</div>';
  host.innerHTML=html+foot;
}
if(window.VX&&VX.bus){VX.bus.on('vx:live:market',function(ev){ const d=(ev&&ev.detail)||{}; if(d.macro_officiel&&VIEW==='macro'){ VX.fetch.invalidate&&VX.fetch.invalidate('/api/macro/officiel'); loadMacroOfficiel(); } });}
async function loadMacroCal(){
  try{
    const cal=await VX.fetch('/cal-feed',{ttl:300000});
    const items=(cal.macro||[]).map(m=>({when:m.date,kind:m.kind||'Macro',
      label:esc(m.label||'')+(m.note?' — '+esc(m.note):'')+(m.dte!==undefined&&m.dte!==null?` (J-${m.dte})`:'')}));
    VXCharts.timelineCard('vx-mk-macro-cal',{title:'Calendrier macro',unit:'événements',
      question:'Quels événements macro peuvent changer le régime ?',
      items,source:'calendrier moteur',timestamp:cal.ts?cal.ts*1000:null,mode:'delayed',
      emptyText:'Aucun événement macro fourni par le calendrier moteur.'});
  }catch(e){emptyCard('vx-mk-macro-cal','Calendrier macro indisponible ('+esc(e.message)+').');}
}

/* ═══ SECTORS ═══ */
function loadSectors(scan){
  const sectors=(scan&&scan.sectors)||[];
  if(!sectors.length){
    /*  DEUX DÉFAUTS ICI, mesurés sur un scan sans secteurs — l'état d'un
        démarrage à froid ou d'un réseau qui ne répond pas.

        1. `emptyCard('vx-mk-sectors-chart', …)` visait un identifiant qui
           N'EXISTE PAS dans le balisage (seuls `-heat` et `-leaders` y sont).
           `emptyCard` sort silencieusement sur un hôte introuvable : le
           message « Secteurs non calculés » n'était jamais affiché.
        2. À la place, un `heatmapCard` recopié dans cette branche dessinait
           la carte AVEC `rows: sectors.map(...)` sur un `sectors` VIDE —
           mesuré : une carte de 196 px, titrée « PERFORMANCE ET MOMENTUM PAR
           SECTEUR », posant sa question et n'y répondant par aucune ligne.
           Sa signature d'accident : `unit:'%'` y était écrit TROIS FOIS.

        La branche dit maintenant ce qu'elle a à dire, sur l'hôte qui existe,
        et ne dessine plus une carte creuse. */
    emptyCard('vx-mk-sectors-heat','Secteurs non calculés par le dernier scan.',
              SCAN_ACTION,'Performance et momentum par secteur');
    ($('vx-mk-sectors-leaders')||{}).innerHTML=
      VX.states.empty('Secteurs non calculés par le dernier scan.');
    return;
  }
  VXCharts.heatmapCard('vx-mk-sectors-heat',{
    title:'Performance et momentum par secteur',unit:'%',
    question:'Quels secteurs attirent le capital aujourd’hui ?',
    conclusion:'Vert = flux entrant, rouge = flux sortant (variation moyenne du jour).',
    columns:['Var. moyenne %','Score','RVOL','Titres'],
    rows:sectors.map(sec=>({label:esc(sec.sector||'n/d'),cells:[
      {value:sec.avg_change??null,onclick:'/opportunities?view=stocks&sector='+encodeURIComponent(sec.sector||'')},
      {value:sec.avg_score??null,label:VX.fmt.nd(sec.avg_score)},
      {value:null,label:VX.fmt.nd(sec.avg_rvol)},
      {value:null,label:String(sec.n??'—')}]})),
    min:-3,max:3,fmt:(v)=>v===null?'—':VX.fmt.pct(v),
    source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
    limits:'univers = leaders scannés'});
  ($('vx-mk-sectors-leaders')||{}).innerHTML=
    `<table class="vx-table"><thead><tr><th>Secteur</th><th class="vx-num">Score</th><th>Leader</th><th></th></tr></thead><tbody>`
    +sectors.map(s=>{
      const L=s.leader&&(s.leader.symbol||((typeof s.leader==='string')?s.leader:null));
      return `<tr>
      <td><a href="/opportunities?view=stocks&sector=${encodeURIComponent(s.sector||'')}" onclick="VX.context.save()">${esc(s.sector||'n/d')}</a></td>
      <td class="vx-num vx-mono">${VX.fmt.nd(s.avg_score)}</td>
      <td>${L?`<button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(L)}">${esc(L)}</button>`:'—'}</td>
      <td>${L?`<button class="vx-btn vx-btn-icon vx-btn-ghost" data-entity-menu="${esc(L)}" aria-label="Actions ${esc(L)}">⋯</button>`:''}</td>
    </tr>`;}).join('')+'</tbody></table>'
    +`<div class="vx-card-footer">${VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))}</div>`;
  /* Rotation sectorielle en quadrant (RRG-like) : force relative × momentum */
  if(window.VXCharts&&sectors.length>=2){
    const cc2=VXCharts.colors;
    const pts=sectors.map(s=>({x:(s.avg_score!=null?s.avg_score:(s.score||50)),y:(s.avg_change!=null?s.avg_change:0),label:s.sector||''}));
    const quadCol=(x,y)=>x>=50?(y>=0?cc2.positive:cc2.warning):(y>=0?cc2.neutral:cc2.negative);
    VXCharts.card('vx-mk-rotation',{
      title:'Rotation sectorielle — force relative × momentum',
      question:'Quels secteurs mènent, lesquels s’essoufflent ?',
      conclusion:'Haut-droit = Leaders (force + momentum) · bas-gauche = Retardataires — cliquer un secteur',
      height:360,source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
      limits:'force = score moyen · momentum = variation moyenne du jour (univers scanné)',
      explain:{shows:'Chaque secteur placé par sa force relative (score moyen) et son momentum (variation moyenne du jour).',
        why:'La stratégie surpondère la zone « Leading » (haut-droit) et se méfie du « Lagging » (bas-gauche).',
        confirm:'Un secteur qui migre vers le haut-droit sur plusieurs séances.',invalidate:'Bascule vers le bas-gauche.'},
      render:(cv)=>VXCharts.mount(cv,{type:'scatter',
        data:{datasets:[{data:pts,pointRadius:7,pointHoverRadius:11,
          pointBackgroundColor:(ctx)=>ctx.raw?quadCol(ctx.raw.x,ctx.raw.y):cc2.neutral,
          pointBorderColor:'rgba(255,255,255,.22)',pointBorderWidth:1}]},
        options:{scales:{
          x:{title:{display:true,text:'Force relative (score moyen) →'},min:0,max:100,grid:{color:'rgba(255,255,255,.06)'}},
          y:{title:{display:true,text:'Momentum (var. moy. %) ↑'},grid:{color:'rgba(255,255,255,.06)'}}},
          plugins:{tooltip:{callbacks:{label:(ctx)=>ctx.raw.label+' · force '+VX.fmt.num(ctx.raw.x,0)+' · momentum '+VX.fmt.pct(ctx.raw.y,1)}}},
          onClick:(evt,els,chart)=>{const p=chart.getElementsAtEventForMode(evt,'nearest',{intersect:true},true);
            if(p.length){const d=chart.data.datasets[0].data[p[0].index];VX.context.save();location.href='/opportunities?view=stocks&sector='+encodeURIComponent(d.label);}}},
        plugins:[{id:'vxQuad',afterDatasetsDraw(chart){const a=chart.chartArea,sx=chart.scales.x,sy=chart.scales.y;const xc=sx.getPixelForValue(50),y0=sy.getPixelForValue(0);const g=chart.ctx;
          g.save();g.strokeStyle='rgba(255,255,255,.12)';g.setLineDash([4,4]);g.beginPath();
          if(xc>a.left&&xc<a.right){g.moveTo(xc,a.top);g.lineTo(xc,a.bottom);}
          if(y0>a.top&&y0<a.bottom){g.moveTo(a.left,y0);g.lineTo(a.right,y0);}g.stroke();g.setLineDash([]);
          g.font='10px sans-serif';g.fillStyle='rgba(255,255,255,.32)';
          g.fillText('LEADING',a.right-58,a.top+14);g.fillText('IMPROVING',a.left+6,a.top+14);
          g.fillText('WEAKENING',a.right-66,a.bottom-8);g.fillText('LAGGING',a.left+6,a.bottom-8);
          g.fillStyle=(window.VXCharts&&VXCharts.colors&&VXCharts.colors.muted)||'#989092';g.font='9px sans-serif';
          chart.data.datasets[0].data.forEach((d,i)=>{const m=chart.getDatasetMeta(0).data[i];if(m)g.fillText(String(d.label).slice(0,11),m.x+9,m.y+3);});
          g.restore();}}]})});
  }
}

/* ═══ BREADTH ═══ */
async function loadBreadth(scan){
  const CO=(window.VXCharts&&VXCharts.colors)||{};
  /* breadth réelle = /api/market/summary.breadth (objet), pas scan.market. */
  let sum={};try{sum=await VX.fetch('/api/market/summary',{ttl:60000})||{};}catch(e){}
  const sb=sum.breadth;let brNum=null,bo=null;
  if(sb!=null&&typeof sb==='object'){
    bo=sb;const raw=(sb.above50!=null)?sb.above50:sb.above200;
    brNum=(raw!=null&&!isNaN(raw))?Number(raw):null;
  }
  else if(sb!=null&&!isNaN(sb))brNum=Number(sb);
  /* Le host historique `vx-mk-breadth-gauge` est conservé pour le contrat DOM,
     mais le doublon en jauge devient un KPI + rail simple. La tendance reste la
     seule visualisation principale de la vue. */
  const bHost=$('vx-mk-breadth-gauge');
  if(bHost&&brNum!=null){
    const pct=Math.max(0,Math.min(100,brNum));
    const reading=brNum>=55?'Participation saine — hausse partagée':brNum>=45?'Participation moyenne':'Participation étroite — sélectivité';
    bHost.innerHTML=
      '<div class="vx-stat-xl"><span class="vx-stat-xl-value vx-mono">'+VX.fmt.num(brNum,0)+' %</span><span class="vx-stat-xl-label">Titres &gt; MM50</span></div>'
      +'<div class="vx-rail vx-mt2" style="--vx-rail-pos:'+pct.toFixed(0)+'%"><span class="vx-rail-mark"></span></div>'
      +'<div class="vx-rail-scale"><span>0 %</span><span>50 %</span><span>100 %</span></div>'
      +'<div class="vx-insight vx-mt2">'+reading+'</div>'
      +'<div class="vx-card-footer">'+VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))+'</div>';
  }else if(bHost)bHost.innerHTML=VX.states.empty('Participation non calculée par le dernier scan.',SCAN_ACTION);
  /* Détail : au-dessus des moyennes, avancées/déclins, nouveaux hauts/bas */
  const dEl=$('vx-mk-breadth-detail');
  if(dEl){
    if(bo){
      const kv=(k,v,cls)=>`<div class="vx-kv"><span class="k">${k}</span><span class="v vx-mono ${cls||''}">${v}</span></div>`;
      const pc=(v)=>v>=55?'vx-pos':v<=45?'vx-neg':'';
      dEl.innerHTML=
        (bo.above50!=null?kv('Titres > MM50',Math.round(bo.above50)+' %',pc(bo.above50)):'')
        +(bo.above200!=null?kv('Titres > MM200',Math.round(bo.above200)+' %',pc(bo.above200)):'')
        +((bo.adv!=null&&bo.dec!=null)?kv('Avancées / Déclins',bo.adv+' / '+bo.dec,bo.adv>=bo.dec?'vx-pos':'vx-neg'):'')
        +((bo.nh!=null&&bo.nl!=null)?kv('Nouveaux hauts / bas',bo.nh+' / '+bo.nl,bo.nh>=bo.nl?'vx-pos':'vx-neg'):'')
        +(bo.buy!=null?kv('Signaux d’achat (univers)',bo.buy):'')
        +`<div class="vx-help vx-mt2">Calculé sur l’univers des leaders scannés (partiel, pas tout le NYSE). Advance/decline cumulés multi-séances non fournis — non affichés plutôt qu’inventés.</div>`;
    }else dEl.innerHTML=VX.states.empty('Détail de participation non fourni par le dernier scan.');
  }
  /* Tendance de participation : historique breadth RÉEL (internals.history : d/a50/a200/
     health) déjà servi mais jamais tracé — montre si la participation s'améliore ou se dégrade. */
  const H=(scan&&scan.internals&&scan.internals.history)||[];
  const tEl=$('vx-mk-breadth-trend');
  if(tEl){
    if(H.length>2&&window.VXCharts&&VXCharts.card&&VXCharts.multiLine){
      const tl=H.map(p=>p.d);
      const series=[{label:'> MM50 %',data:H.map(p=>p.a50)},{label:'> MM200 %',data:H.map(p=>p.a200)},
        {label:'Santé',data:H.map(p=>p.health)}];
      VXCharts.card('vx-mk-breadth-trend',{title:'Tendance de participation',unit:'% de titres',
        question:'La participation s’améliore-t-elle ou se dégrade-t-elle ?',height:210,
        source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
        limits:'historique breadth de l’univers scanné (partiel, pas tout le NYSE)',
        render:(cv)=>VXCharts.multiLine(cv,tl,series,{yFmt:(v)=>Math.round(v)+' %'})});
    }else emptyCard('vx-mk-breadth-trend','Historique de participation insuffisant (se remplit à chaque scan).',SCAN_ACTION);
  }
  const rows=(scan&&scan.rows)||[];
  const counts={};
  rows.forEach(r=>{const v=r.verdict||r.decision;if(v)counts[v]=(counts[v]||0)+1;});
  const top=Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,5);
  if(top.length){
    VXCharts.donutCard('vx-mk-verdicts',{
      title:'Répartition des verdicts du scan',unit:'titres',question:'Le moteur trouve-t-il des dossiers ?',
      conclusion:top[0][0]+' domine ('+top[0][1]+' titre(s) sur '+rows.length+')',
      labels:top.map(x=>x[0]),values:top.map(x=>x[1]),height:200,
      source:(scan&&scan.source)||'scan',timestamp:scan&&(scan.scan_ts||scan.updated),mode:modeOf(scan),
      explain:{shows:'Le décompte des verdicts moteur sur l’univers scanné (max 5 catégories).',
        why:'Beaucoup d’ÉVITER = environnement hostile même si les indices tiennent.',
        confirm:'Verdicts d’achat en hausse sur plusieurs scans.',invalidate:'Bascule massive vers ÉVITER.'}});
  }else emptyCard('vx-mk-verdicts','Aucun verdict dans le dernier scan.',SCAN_ACTION);
  /* Entonnoir de sélection : univers → notés → dossiers → achats (données du scan) */
  if(window.VXCharts&&VXCharts.funnel){
    const scanned=rows.length;
    const noted=rows.filter(r=>r.score!==null&&r.score!==undefined).length;
    /* Le scan parle anglais (BUY/WATCH/WAIT/AVOID), le comité français : les
       deux vocabulaires sont acceptés, sinon « Achats » vaut 0 à tort
       (même règle que l'entonnoir d'Aujourd'hui, briefing.py). */
    const isBuy=v=>['ACHETER','RENFORCER','BUY','STRONG_BUY'].includes((v||'').toUpperCase());
    const isAct=v=>{const u=(v||'').toUpperCase();return !!u&&!['ÉVITER','EVITER','AVOID','SELL','STRONG_SELL'].includes(u);};
    const dossiers=rows.filter(r=>isAct(r.verdict||r.decision)).length;
    const buys=rows.filter(r=>isBuy(r.verdict||r.decision)).length;
    if(scanned>0){
      VXCharts.funnel('vx-mk-funnel',{ariaLabel:'Entonnoir de sélection',fmt:v=>v,
        stages:[{label:'Univers scanné',value:scanned,color:CO.neutral},
          {label:'Notés',value:noted,color:CO.info},
          {label:'Dossiers actionnables',value:dossiers,color:CO.warning},
          {label:'Achats',value:buys,color:CO.positive}]});
      const el=$('vx-mk-funnel');if(el)el.insertAdjacentHTML('beforeend',
        '<div class="vx-help vx-mt2">Chaque étape resserre l’univers scanné jusqu’aux verdicts d’achat du comité. Aucune idée n’est forcée : un entonnoir plat = marché hostile.</div>');
    }else emptyCard('vx-mk-funnel','Univers non scanné.',SCAN_ACTION);
  }
  /* Waterfall : composition de la santé du marché (contributions pondérées de l'internals) */
  const inter=(scan&&scan.internals)||{};
  const card=$('vx-mk-health-card');
  if(card&&window.VXCharts&&VXCharts.waterfall&&inter.health!=null&&inter.pct_a50!=null){
    card.hidden=false;
    VXCharts.waterfall('vx-mk-health-wf',{ariaLabel:'Composition de la santé du marché',unit:'points de santé (0-100)',
      question:'Qu’est-ce qui compose la santé du marché aujourd’hui ?',
      source:'SCAN',timestamp:(scan&&(scan.scan_ts||scan.updated))||null,mode:'delayed',
      limits:'contributions pondérées des internes du marché',
      items:[
        {label:'>MM50',value:0.30*(inter.pct_a50||0)},
        {label:'>MM200',value:0.25*(inter.pct_a200||0)},
        {label:'Breadth',value:0.25*(inter.breadth!=null?inter.breadth:(brNum||0))},
        {label:'Adv/Déc',value:0.20*(inter.advpct||0)},
        {label:'Santé',value:inter.health,isTotal:true}],
      fmt:(v)=>Math.round(v)});
  }else if(card){card.hidden=true;}
  loadBreadthInternals(scan);
}
function loadBreadthInternals(scan){
  const inter=(scan&&scan.internals)||{};
  const iCard=$('vx-mk-internals-card'),dCard=$('vx-mk-dist-card');
  if(!inter||inter.pct_a50===null||inter.pct_a50===undefined){if(iCard)iCard.hidden=true;if(dCard)dCard.hidden=true;return;}
  if(iCard)iCard.hidden=false;
  const kvr=(k,v,cls)=>`<div class="vx-kv"><span class="k">${k}</span><span class="v vx-mono ${cls||''}">${v}</span></div>`;
  const pos=(v)=>v>=55?'vx-pos':v<=45?'vx-neg':'';
  ($('vx-mk-internals')||{}).innerHTML=
    kvr('% au-dessus MM50',inter.pct_a50+' %',pos(inter.pct_a50))
    +kvr('% au-dessus MM200',inter.pct_a200+' %',pos(inter.pct_a200))
    +kvr('Avancées / déclins',inter.advpct+' % en hausse',pos(inter.advpct))
    +kvr('Nouveaux plus-hauts (52s)',VX.fmt.nd(inter.nh),inter.nh>inter.nl?'vx-pos':'')
    +kvr('Nouveaux plus-bas (52s)',VX.fmt.nd(inter.nl),inter.nl>inter.nh?'vx-neg':'')
    +(inter.avg_rsi!==null&&inter.avg_rsi!==undefined?kvr('RSI moyen univers',inter.avg_rsi):'')
    +`<div class="vx-card-footer">${VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))} · univers scanné</div>`;
  const dist=inter.dist||[];
  if(dCard&&dist.length&&window.VXCharts){dCard.hidden=false;
    const maxN=Math.max(1,...dist);const cc=VXCharts.colors;
    const bar=(n,i)=>{const h=Math.round(n/maxN*100);
      const col=i>=7?cc.positive:i<=2?cc.negative:cc.warning;
      return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:3px" role="img" aria-label="score ${i*10} à ${i*10+10} : ${n} titres">
        <span style="width:100%;height:120px;display:flex;align-items:flex-end"><span style="width:100%;height:${h}%;background:${col};border-radius:3px 3px 0 0;min-height:2px"></span></span>
        <span style="font-size:9px;color:var(--vx-text-muted,#989092);font-variant-numeric:tabular-nums">${i*10}</span></div>`;};
    ($('vx-mk-dist')||{}).innerHTML='<div style="display:flex;gap:3px;align-items:flex-end;padding:6px 2px">'+dist.map(bar).join('')+'</div>';
  }else if(dCard){dCard.hidden=true;}
}

/* ═══ VOLATILITY ═══ (cockpit : un seul hero VIX + contexte régime textuel)
   Source RÉELLE = /api/market/summary (scan.market ne porte que la session). */
async function loadVix(scan){
  let sum={};try{sum=await VX.fetch('/api/market/summary',{ttl:60000})||{};}catch(e){}
  let vix=(sum.vix!=null&&!isNaN(sum.vix))?Number(sum.vix):null;
  if(vix==null){const vi=((scan&&scan.indices)||[]).find(i=>i&&i.name==='VIX');if(vi&&vi.price!=null)vix=Number(vi.price);}
  const chg=(sum.vix_chg!==undefined)?sum.vix_chg:null;
  const band=sum.vix_band||mkt(scan).vix_band;
  if(vix==null){
    ($('vx-mk-vix-body')||{}).innerHTML=VX.states.empty('VIX non fourni par le dernier scan.',SCAN_ACTION);
  }else{
    const stress=Math.max(0,Math.min(100,(vix-10)/30*100));
    const reading=vix<15?'Volatilité comprimée — primes d’options bon marché':vix<25?'Volatilité élevée — prudence sur les entrées':'Stress — expansion de volatilité';
    /* `vx-mk-vix-gauge` reste l'hôte contractuel, mais ne monte plus une jauge
       redondante : il porte désormais la valeur hero. Le rail est l'unique
       visualisation bornée calme ↔ stress. */
    ($('vx-mk-vix-body')||{}).innerHTML=
      `<div id="vx-mk-vix-gauge" class="vx-markets-vix-stat"><div class="vx-stat-xl"><span class="vx-stat-xl-value vx-mono">${VX.fmt.nd(vix)}</span><span class="vx-stat-xl-label">Indice VIX</span></div></div>`
      +(chg!==null&&chg!==undefined?`<div class="vx-kv"><span class="k">Variation</span><span class="v ${chg>0?'vx-neg':chg<0?'vx-pos':'vx-muted'}">${VX.fmt.pct(chg)} vs hier</span></div>`:'')
      +(band?`<div class="vx-kv"><span class="k">Bande</span><span class="v">${esc(band)}</span></div>`:'')
      +`<div class="vx-stat-xl-label vx-mt3">Calme ↔ Stress</div>`
      +`<div class="vx-rail vx-rail--stress vx-mt2" style="--vx-rail-pos:${stress.toFixed(0)}%"><span class="vx-rail-mark"></span></div>`
      +`<div class="vx-rail-chipline" style="--vx-rail-pos:${stress.toFixed(0)}%"><span class="vx-rail-chip">${VX.fmt.nd(vix)}</span></div>`
      +`<div class="vx-rail-scale"><span>10</span><span>25</span><span>40+</span></div>`
      +`<div class="vx-insight vx-mt2">${reading}. Un VIX en expansion invalide les entrées agressives.</div>`
      +`<div class="vx-card-footer">${VX.updateIndicator(scan&&(scan.scan_ts||scan.updated),(scan&&scan.source)||'scan',modeOf(scan))}</div>`;
  }
  /* Contexte régime — uniquement en texte, sous disclosure. */
  try{
    const r=await VX.fetch('/api/market/regime',{ttl:120000});
    const conf=Math.round((r.confidence||0)*100);
    const allowed=r.adjustments&&r.adjustments.new_risk_allowed;
    /* Étiquette honnête : UNKNOWN garde son état dédié (jamais « confiance 0 % »
       présentée comme une mesure), jamais un code brut. */
    const known=r.regime!=='UNKNOWN'&&REGIME_LABEL[r.regime];
    const regTxt=known?('<b>'+esc(known[0])+'</b> · confiance '+conf+' %')
      :'<b>Régime non qualifié</b> — moins de 3 dimensions de marché';
    if($('vx-mk-vol-rail'))($('vx-mk-vol-rail')||{}).innerHTML=
      '<div class="vx-insight">Régime '+regTxt+'</div>'
      +'<div class="vx-kv vx-mt2"><span class="k">Confiance</span><span class="v vx-mono">'+(known?conf+' %':'n/d')+'</span></div>'
      +'<div class="vx-kv"><span class="k">Nouveau risque</span><span class="v '+(allowed?'vx-pos':'vx-neg')+'">'+(allowed?'autorisé':'BLOQUÉ')+'</span></div>'
      +'<div class="vx-card-footer">'+VX.updateIndicator(r.as_of||r.timestamp||r.updated||null,'Moteur de régimes','delayed')
      +'<a class="vx-btn vx-btn-sm vx-btn-ghost vx-right" href="?view=breadth">Participation →</a></div>';
  }catch(e){if($('vx-mk-vol-rail'))($('vx-mk-vol-rail')||{}).innerHTML=VX.states.error('Régime indisponible');}
}

/* ═══ Orchestration ═══ */
function bindDisclosureResize(){
  document.querySelectorAll('details.vx-disclosure').forEach(d=>{
    if(d.dataset.vxResizeBound)return;
    d.dataset.vxResizeBound='1';
    d.addEventListener('toggle',()=>{
      if(d.open)requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
    });
  });
}
/* Diffusion (P1) : `boot` est rejoué sur `vx:data-refreshed` (émis par
   live-updates.js APRÈS invalidation du cache, regroupé) — voir la fin du
   script. La sous-vue vient de l'URL, aucun filtre local n'est perdu. */
async function boot(){
  bindDisclosureResize();
  const render=(scan)=>{
    demoBanner(scan);
    /* Badge de fraîcheur du snapshot (§8) : Live / Analyse / À actualiser. */
    try{
      if($('vx-mk-fresh')){
        /* Âge HONNÊTE = ancienneté réelle du scan (scan_age serveur), pas l'âge de
           l'entrée de cache : un snapshot resservi doit refléter l'âge de la DONNÉE.
           Et quand cet âge MANQUE, on écrit pourquoi plutôt qu'un tiret nu. */
        const ageMs=(scan&&typeof scan.scan_age==='number')?scan.scan_age*1000:null;
        const live=!!scan&&scan.data_source!=='demo';
        if(!scan)
          ($('vx-mk-fresh')||{}).innerHTML='<span class="vx2-badge" data-state="offline">Aucun scan disponible</span>';
        else if(ageMs==null)
          ($('vx-mk-fresh')||{}).innerHTML='<span class="vx2-badge" data-state="missing">Scan non horodaté — âge inconnu</span>';
        else if(window.VX&&VX.freshness)
          ($('vx-mk-fresh')||{}).innerHTML=VX.freshness.chip(VX.freshness.assess({ageMs:ageMs,live:live}));
      }
    }catch(e){}
    if(VIEW==='overview'){loadRegime(scan);loadLeader(scan||{});loadRisk(scan);loadSpyChart(scan);}
    else if(VIEW==='indices'){loadStrip(scan);loadMultiIndex(scan);loadMovers(scan);}
    else if(VIEW==='macro'){loadMacroKpis(scan);loadMacroRegime();loadYield(scan);loadMacroCal();loadMacroOfficiel();}
    else if(VIEW==='sectors'){loadSectors(scan);}
    else if(VIEW==='breadth'){loadBreadth(scan);}
    else if(VIEW==='volatility'){loadVix(scan);}
  };
  /* Stale-while-revalidate : peinture IMMÉDIATE depuis le cache (revisite instantanée)
     puis revalidation en fond — jamais d'écran vide. */
  const pk=VX.fetch.peek('/scan');
  if(pk&&pk.data) render(pk.data);
  render(await getScan());
}
function whenChartsReady(fn){
  if(window.VXCharts&&window.Chart)return fn();
  window.addEventListener('load',fn,{once:true});
}
whenChartsReady(boot);
VX.bus.on('vx:data-refreshed',boot);
})();
</script>
"""


def _entete() -> str:
    """En-tête + contexte. L'emplacement de fraîcheur rendait un tiret nu :
    `VX.freshness.assess({ageMs:null})` renvoie l'état `unknown`, dont le
    libellé EST « — ». Un signe qui ne nomme pas sa grandeur n'informe de rien."""
    return (
        vx2.page_header(
            surtitre='Explorer', titre='Marchés',
            question='Dans quel environnement la stratégie opère-t-elle ?',
            actions=vx2.bouton('Ouvrir les Opportunités', href='/opportunities',
                               variante='ghost'))
        + vx2.context_bar([
            {'label': 'Univers', 'contenu':
                '<span class="vx2-stamp">Indices, secteurs et volatilité du '
                '<b>dernier scan</b></span>'},
            {'label': 'Nature', 'contenu':
                '<span class="vx2-stamp">Contexte — <b>aucune recommandation</b> '
                'n’est émise ici</span>'},
            {'label': 'Fraîcheur du scan', 'contenu':
                '<span id="vx-mk-fresh">'
                + vx2.badge_etat('missing', texte='Lecture…') + '</span>'},
        ]))


def render(view: str = 'overview') -> str:
    """Assemble la page Marchés pour la sous-vue demandée (URL = état)."""
    if view not in dict(_VIEWS):
        view = 'overview'
    label = dict(_VIEWS)[view]
    content = (_HEADER.replace('%%ENTETE%%', _entete())
               .replace('%%TABS%%', _tabs(view))
               + _VIEW_CONTENT[view]).replace(
        '%%LOADING%%', '<div class="vx-skeleton" style="height:60px"></div>')
    page_js = _JS.replace('%%VIEW%%', view)
    return render_shell(title='Marchés', active='markets', space_label='Marchés',
                        sub_label=label, content=content, page_js=page_js,
                        page_label='Marchés')
