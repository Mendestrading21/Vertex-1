"""vertex.ui.pages.opportunities_page — le SCREENER complet (§24+).

Question : « Quelles opportunités méritent réellement une analyse ? »
La page passe de 515 titres scannés à UNE décision : filtres globaux
(verdict, secteur, score, proba de gain, gain/risque, volume relatif,
véhicule), graphiques qui montrent le POURQUOI (scatter avantage × proba,
distribution live, secteurs des résultats), top cartes, table triable.
Sous-vues : screener · options · portefeuille · anomalies · calendrier.
Données réelles uniquement — « — » honnête si absent.
"""
from __future__ import annotations


from vertex.ui import vx2
from vertex.ui.shell import json_for_script, render_shell

# Le contrat réclame des sous-vues Actions et ETF. Vertex sait classer un
# instrument — `vertex.market.instrument_profile.build()` — mais ce verdict
# n'est PAS servi sur les lignes du scan : seul `/api/analysis` le porte, et
# pour un symbole à la fois.
#
# On ne recrée donc pas la règle dans l'interface. On lit son RÉFÉRENTIEL
# curé — deux listes statiques du produit — et l'écran DIT ce que cette
# couverture vaut. Un titre hors des deux listes n'est pas classé de force :
# il est compté à part, et nommé.
def _referentiel_classes() -> dict:
    from vertex.market import instrument_profile as _ip
    from vertex.market import sectors as _sec
    return {
        'etf': sorted(set(_ip.BROAD_ETFS) | set(_ip.ETF_SECTOR_PROXY)),
        'actions': sorted(_sec.SECTOR_MAP),
    }


_VIEWS = (('screener', 'Radar'), ('stocks', 'Actions'), ('etf', 'ETF'),
          ('options', 'Options'), ('anomalies', 'Anomalies'),
          ('calendar', 'Catalyseurs'), ('portfolio', 'Positions × moteur'))

# `stocks` menait au Radar ; il a désormais sa propre vue, et c'est la même
# table filtrée — un lien historique arrive donc au bon endroit, en mieux.
_VIEW_ALIASES = {'radar': 'screener'}


def _tabs(view: str) -> str:
    return vx2.tabs([{'label': label, 'href': f'/opportunities?view={v}',
                      'actif': v == view} for v, label in _VIEWS],
                    libelle='Sous-vues des Opportunités')


_CONTENT = """
<div class="vx-page-header vx-page-lead"><div><p class="vx2-eyebrow">Explorer</p><h1>Opportunités</h1>
<div class="vx-sub">Quels dossiers méritent une analyse maintenant&nbsp;?</div></div>
<div class="vx-actions vx-toolbar"><button class="vx-btn vx-btn-sm"
  onclick="VXEntities.openAddModal()">+ Ajouter</button></div></div>
<div class="vx2-contextbar" id="op-context" role="group" aria-label="Contexte du scan"><span class="vx2-stamp">Lecture du scan…</span></div>
%%TABS%%
<style>
  /* Barre de filtres du screener : collante, lisible, réactive */
  .vx-screenbar{position:sticky;top:calc(var(--vx-topbar-h) + 2px);z-index:14;
    display:flex;flex-wrap:wrap;gap:.45rem;align-items:center;padding:10px 12px;
    margin-top:12px;border:1px solid var(--vx-border,#26221e);border-radius:12px;
    background:color-mix(in srgb,var(--vx-surface-1,#141513) 92%,transparent);
    backdrop-filter:blur(6px)}
  .vx-screenbar .vx-chip[aria-pressed="true"]{border-color:var(--vx-brand);color:var(--vx-brand-strong,#a3ca42)}
  .vx-screenbar label.rng{display:flex;align-items:center;gap:6px;font-size:11px;
    color:var(--vx-text-dim,#817d77)}
  .vx-screenbar label.rng input[type=range]{width:86px;accent-color:var(--vx-brand,#c9cdd4)}
  .vx-screenbar label.rng b{font-variant-numeric:tabular-nums;min-width:30px;color:var(--vx-text-secondary)}
  /* KPI du screener */
  .vx-scr-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:12px}
  .vx-scr-kpis .k{padding:11px 13px;border-radius:11px;background:var(--vx-surface-0,#0d100e);
    border:1px solid var(--vx-border,#26221e)}
  .vx-scr-kpis .k b{display:block;font:700 21px/1.15 var(--vx-font-mono,monospace);color:var(--vx-text-primary,#f2f5f1)}
  .vx-scr-kpis .k span{font-size:10.5px;color:var(--vx-text-dim,#817d77);text-transform:uppercase;letter-spacing:.05em}
  /* Table triable */
  th[data-sort]{cursor:pointer;user-select:none;white-space:nowrap}
  th[data-sort]:hover{color:var(--vx-brand,#c9cdd4)}
  th[data-sort][data-dir="desc"]::after{content:" ↓";color:var(--vx-brand)}
  th[data-sort][data-dir="asc"]::after{content:" ↑";color:var(--vx-brand)}
  /* Rail 52 semaines dans la table */
  .vx-rail52{display:inline-block;width:56px;height:5px;border-radius:99px;
    background:var(--vx-surface-0);position:relative;vertical-align:middle}
  .vx-rail52 i{position:absolute;top:-2px;width:8px;height:8px;margin-left:-4px;
    border-radius:99px;background:var(--vx-beige,#c0b79f)}
  /* Mobile : la barre de filtres (haute une fois empilée) ne reste pas collante */
  @media (max-width:760px){.vx-screenbar{position:static}}
  /* Grille de cartes opportunités : responsive PROPRE (fini le span 4 inline) */
  .vx-opp-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
  @media (max-width:1100px){.vx-opp-grid{grid-template-columns:repeat(2,1fr)}}
  @media (max-width:680px){.vx-opp-grid{grid-template-columns:1fr}}
  .vx-opp-card{min-width:0}
  .vx-opp-notrade{border-left:3px solid var(--vx-negative)!important;opacity:.92}
  /* KPI : liseré sémantique comme les tuiles météo du Dashboard */
  .vx-scr-kpis .k{border-left:3px solid transparent}
  .vx-scr-kpis .k[data-tone="pos"]{border-left-color:var(--vx-positive)}
  .vx-scr-kpis .k[data-tone="neg"]{border-left-color:var(--vx-negative)}
  .vx-scr-kpis .k[data-tone="brand"]{border-left-color:var(--vx-brand)}

  /* ═══════════ ARGENT LUMINEUX — harmonisation avec le Dashboard ═══════════ */
  #vx-content .vx-card{position:relative;overflow:hidden;border-radius:16px;
    border:1px solid rgba(255,255,255,.07);
    background:linear-gradient(180deg,#14151a 0%,#0c0d11 100%);
    box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 26px 56px -40px #000;
    transition:border-color .18s ease,box-shadow .18s ease}
  #vx-content .vx-card::after{content:"";position:absolute;left:16px;right:16px;top:0;height:1px;
    background:linear-gradient(90deg,transparent,rgba(255,255,255,.18),transparent);opacity:.5;pointer-events:none}
  #vx-content .vx-card:hover{border-color:rgba(255,255,255,.16)}
  #vx-content .vx-card--premium,#vx-content .vx-card--accent{background:linear-gradient(180deg,#16171d 0%,#0d0e12 100%)}
  #vx-content .vx-card-title{font-size:12.5px !important;font-weight:640;letter-spacing:.09em;
    text-transform:uppercase;color:var(--vx-text-secondary,#c2c7cf)}
  #vx-content .vx-card-header{padding-bottom:9px;margin-bottom:12px;border-bottom:1px solid rgba(255,255,255,.05)}
  /* opacité RETIRÉE (lot 30) : elle abaissait le jeton AA à ~3,8:1 — mesuré
     Lighthouse. La hiérarchie vient du jeton, de la taille et de l'italique. */
  #vx-content .vx-chart-question{font-size:11px;font-style:italic}
  #vx-content .vx-meta{font-size:10.5px;color:var(--vx-text-muted,#7c828c)}
  #vx-content .vx-card-footer,#vx-content .vx-card-foot{opacity:.72}
  #vx-content .vx-num,#vx-content .vx-kpi-value,#vx-content .vx-mono{font-variant-numeric:tabular-nums}
  /* Tables : lignes fines, en-têtes discrets, survol argent */
  #vx-content .vx-table th{font-size:10px;letter-spacing:.07em;text-transform:uppercase;
    color:var(--vx-text-muted,#7c828c);font-weight:600}
  #vx-content .vx-table td,#vx-content .vx-table th{border-color:rgba(255,255,255,.05) !important}
  #vx-content .vx-table tbody tr{transition:background .12s}
  #vx-content .vx-table tbody tr:hover{background:rgba(255,255,255,.025)}
  /* Badges de contexte discrets (les colorés gardent leur force) */
  #vx-content .vx-badge:not([style*="color"]){background:rgba(255,255,255,.03);
    border-color:rgba(255,255,255,.07);color:var(--vx-text-muted,#7c828c)}
  /* Chips : style argent net */
  #vx-content .vx-chip{border-radius:9px;border:1px solid rgba(255,255,255,.09);
    background:rgba(255,255,255,.025);color:var(--vx-text-secondary,#c2c7cf)}
  #vx-content .vx-chip[aria-pressed="true"]{border-color:rgba(255,255,255,.34);color:#fff;background:rgba(255,255,255,.07)}
  /* Cartes résultats : coins + survol */
  #vx-content .vx-opp-card{border-radius:14px;transition:border-color .15s ease,transform .15s ease}
  #vx-content .vx-opp-card:hover{border-color:rgba(255,255,255,.16);transform:translateY(-1px)}
</style>
<div id="op-body" class="vx-mt3">%%LOADING%%</div>
"""

_JS = r"""
<script src="/static/vertex/js/charts/timeline-chart.js" defer></script>
<script src="/static/vertex/js/charts/heatmap.js" defer></script>
<script src="/static/vertex/js/charts/option-payoff.js" defer></script>
<script src="/static/vertex/js/charts/option-scenarios.js" defer></script>
<script src="/static/vertex/js/charts/option-theta.js" defer></script>
<script src="/static/vertex/js/charts/option-iv-sensitivity.js" defer></script>
<script src="/static/vertex/js/charts/bar-chart.js" defer></script>
<script src="/static/vertex/js/charts/donut-chart.js" defer></script>
<script src="/static/vertex/js/charts/sector-chart.js" defer></script>
<script>
(function(){
'use strict';
const VIEW=%%VIEW%%;const PARAMS=%%PARAMS%%;const CLASSES=%%CLASSES%%;
const $=(id)=>document.getElementById(id);
function esc(s){return String(s??'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));}
const OUT=['Rejetée','Radar','À surveiller','Proche','Actionnable','Invalidée'];
function bucketOf(r){
  if(r.verdict==='AVOID'||r.verdict==='ÉVITER')return'Rejetée';
  if((r.rr_ok&&r.score>=72&&(r.verdict==='BUY'||r.verdict==='ACHETER')))return'Actionnable';
  if(r.score>=66)return'Proche';
  if(r.score>=56)return'À surveiller';
  return'Radar';
}
/* verdict → classe sémantique (buy/achat=vert, attente/surveille=jaune, évite/refus=rouge) */
function vCls(v){var s=String(v||'').toLowerCase();
  if(!s)return'';
  if(/(buy|achet|renforc|accumul|acheter|long\b|s\+)/.test(s))return'vx-pos';
  if(/(avoid|évit|evit|refus|réduir|reduir|sell|vendre|rejet|short)/.test(s))return'vx-neg';
  if(/(hold|attend|neutre|patience|surveil|proche|watch|radar)/.test(s))return'vx-warn';
  return'';}
/* bucket de statut → classe sémantique (actionnable=vert, proche/surveille=jaune, rejetée=rouge) */
function bucketCls(b){var s=String(b||'').toLowerCase();
  if(/actionnable/.test(s))return'vx-pos';
  if(/(rejet|invalid)/.test(s))return'vx-neg';
  if(/(proche|surveil|attente)/.test(s))return'vx-warn';
  return'';}
/* playbook peut être une chaîne OU un objet moteur → toujours une chaîne sûre */
function pbStr(pb){return (pb&&typeof pb==='object')?(pb.name||pb.label||pb.key||pb.type||''):(pb||'');}
/* ── SIX AIDES APPELEES ET DEFINIES NULLE PART ─────────────────────────
   `VERD_FR`, `verdictDir`, `verdictWord`, `pbText`, `pbIcon` et `heatCell`
   etaient appelees par la carte d'opportunite, le filtre de setup, le donut
   des verdicts, la revue de position et la table des anomalies — et
   introuvables dans TOUT le depot. Chacun de ces chemins levait un
   `ReferenceError` qui remplacait le corps entier de la page.

   Invisible en demo : le scan y rend zero ligne, donc aucun ne s'execute.
   Trouve en injectant un scan fictif dans le navigateur.

   Elles vivent ICI, au niveau du module — un premier placement les avait
   enfermees dans la portee du Radar, et les vues Anomalies et Positions
   levaient encore. Le balayage peuple l'a montre.

   Aucune ne calcule ni n'invente : elles LISENT ce que le serveur attache
   deja. Un champ absent reste absent. */
const VERD_FR=(function(){
  /* Le libelle vient du vocabulaire CANONIQUE (`recommendation.vocab_js()`).
     Une table ecrite a la main divergerait du moteur au premier verdict
     ajoute, en silence. */
  const v=window.__VXVOCAB||{},out={};
  Object.keys(v).forEach(function(k){const e=v[k];out[k]=(e&&(e.label||e[0]))||k;});
  return out;
})();
/* Direction de la jauge : le TON est canonique, on ne redecide pas ici si un
   verdict est haussier. */
function verdictDir(dec){
  const e=(window.__VXVOCAB||{})[dec];const t=String((e&&e.tone)||'');
  if(t.indexOf('green')>=0)return 'up';
  if(t.indexOf('red')>=0)return 'down';
  return '';
}
function verdictWord(dec){return VERD_FR[dec]||dec||'';}
/* Playbook : `strategy_fit._playbook_of` l'attache cote serveur. `pbStr`
   existait deja pour en extraire le nom — on le REUTILISE plutot que d'en
   ecrire un second qui divergerait. */
function pbText(r){return pbStr(r&&r.playbook);}
function pbIcon(r){const p=r&&r.playbook;return (p&&p.ic)||'';}
/* Cellule chauffee par seuils. Les seuils viennent de l'APPELANT, deja ecrits
   dans chaque table. Une valeur absente ne recoit AUCUNE couleur : un tiret
   gris, jamais un vert par defaut. */
function heatCell(v,opt){
  opt=opt||{};const n=Number(v);
  if(v==null||!isFinite(n))
    return '<td data-label="'+esc(opt.label||'')+'" class="vx-num">'
      +'<span class="vx2-absent">—</span></td>';
  const ton=n>=(opt.good!=null?opt.good:70)?'vx-pos'
    :n>=(opt.mid!=null?opt.mid:40)?'vx-warn':'vx-neg';
  return '<td data-label="'+esc(opt.label||'')+'" class="vx-num">'
    +'<span class="vx-mono '+ton+'">'+VX.fmt.num(n,0)+'</span></td>';
}
function metaMode(scan){return scan&&scan.data_source==='demo'?'fallback':'delayed';}

/* ContextBar — univers, dernier scan, source et mode. Rendue MEME quand le
   scan est vide : « aucun titre » sans dire d'ou vient ce vide oblige a
   deviner si la cause est la source, le moteur ou le rendu. */
function paintContext(scan){
  const el=$('op-context'); if(!el)return;
  const nd='<span class="vx2-absent">\u2014</span>';
  const rows=(scan&&scan.rows)||[];
  const src=(scan&&scan.source)||null;
  const ts=(scan&&(scan.scan_ts_h||scan.scan_ts||scan.updated))||null;
  const demo=scan&&scan.data_source==='demo';
  const badge=demo?'<span class="vx2-badge" data-state="demo">D\u00e9mo</span>'
    :(src?'<span class="vx2-badge" data-state="delayed">Diff\u00e9r\u00e9e</span>'
         :'<span class="vx2-badge" data-state="missing">Indisponible</span>');
  const grp=(label,contenu)=>'<div class="vx2-context-group">'
    +'<span class="vx2-context-label">'+label+'</span>'+contenu+'</div>';
  const sep='<span class="vx2-context-sep" aria-hidden="true"></span>';
  el.innerHTML=[
    grp('Univers','<span class="vx2-mono">'+(rows.length?VX.fmt.nd(rows.length)+' titres':nd)+'</span>'),
    grp('Dernier scan','<span class="vx2-mono">'+(ts?esc(String(ts)):nd)+'</span>'),
    grp('Source','<span class="vx2-stamp"><b>'+(src?esc(String(src)):'\u2014')+'</b></span>'),
    grp('Fra\u00eecheur',badge)
  ].join(sep);
}
/* Debounce : les curseurs tirent input en rafale — on repeint au calme (120 ms). */
function debounce(fn,ms){let t=null;return function(){const a=arguments,c=this;
  clearTimeout(t);t=setTimeout(()=>fn.apply(c,a),ms||120);};}
function demoBanner(scan){return scan&&scan.data_source==='demo'?
  '<div class="vx-stale-banner">Mode DÉMO — données synthétiques, clairement identifiées.</div>':'';}
function rowActions(sym){return `<div class="vx-row-actions">
  <button class="vx-btn vx-btn-sm vx-btn-ghost" data-inspect="${sym}" title="Aperçu rapide" aria-label="Aperçu ${sym}">Aperçu</button>
  <button class="vx-btn vx-btn-sm vx-btn-ghost" data-open-analysis="${sym}">Analyse</button>
  <button class="vx-btn vx-btn-icon vx-btn-ghost" data-entity-menu="${sym}" aria-label="Actions ${sym}">⋯</button></div>`;}
function sparkMini(closes){
  const v=(closes||[]).filter(x=>x!=null&&isFinite(x)).slice(-60);
  if(v.length<8)return '';
  const w=120,h=26,mn=Math.min.apply(null,v),mx=Math.max.apply(null,v),rng=(mx-mn)||1;
  const pts=v.map((x,i)=>(i/(v.length-1)*w).toFixed(1)+','+(h-1-((x-mn)/rng)*(h-2)).toFixed(1)).join(' ');
  const up=v[v.length-1]>=v[0];
  const col=up?'var(--vx-positive)':'var(--vx-negative)';
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" width="100%" height="26" style="display:block;margin-top:6px" aria-hidden="true">
    <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" opacity=".9"/></svg>`;
}
function dimStrip(r){
  const dims=[['C','Conviction',r.st_conf,0],['M','Momentum',r.st_mom,0],['T','Technique',r.st_tech,0],
              ['F','Fondamental',r.st_fund,0],['R','Risque',r.st_risk,1]];
  if(!dims.some(d=>d[2]!=null))return '';
  return `<div style="display:flex;gap:5px;align-items:flex-end;margin-top:8px" role="img" aria-label="dimensions du score">`
    +dims.map(d=>{const v=d[2];
      const lvl=v==null?null:(d[3]?100-v:v);
      const col=lvl==null?'var(--vx-surface-4)':lvl>=67?'var(--vx-positive)':lvl>=40?'var(--vx-warning)':'var(--vx-negative)';
      const hh=v==null?4:Math.max(4,Math.round(v/100*24));
      return `<span title="${d[1]} : ${v==null?'n/d':Math.round(v)}" style="flex:1;display:flex;flex-direction:column;align-items:center;gap:3px">
        <span style="display:flex;align-items:flex-end;height:24px;width:100%"><i style="display:block;width:100%;height:${hh}px;border-radius:3px 3px 1px 1px;background:${col};opacity:${v==null?.35:.95}"></i></span>
        <b style="font:600 8.5px/1 var(--vx-font);color:var(--vx-text-faint)">${d[0]}</b></span>`;}).join('')+'</div>';
}
/* Drapeaux moteur → français lisible (vx_flags : raisons du no-trade / contexte) */
const FLAG_FR={regime_chop:'Marché sans direction',regime_panic:'Marché en panique',
  regime_risk_off:'Contexte risk-off',edge_incertain_et_risque_eleve:'Avantage incertain + risque élevé',
  edge_faible:'Avantage faible',liquidite_faible:'Liquidité faible',correlation_elevee:'Trop corrélé au panier',
  extension_excessive:'Titre trop étendu',fondamentaux_solides:'Fondamentaux solides',
  fondamentaux_faibles:'Fondamentaux faibles',earnings_proche:'Résultats imminents',
  volatilite_elevee:'Volatilité élevée',stop_trop_large:'Stop trop large'};
function flagFr(k){return FLAG_FR[k]||String(k||'').replace(/_/g,' ');}
/* Barre de niveaux : stop · cours · entrée · TP — situe le prix dans le plan moteur */
function levelsBar(plan,price){
  if(!plan||plan.entry==null||plan.stop==null)return '';
  const tp=plan.tp3||plan.tp2||plan.tp1;if(tp==null)return '';
  const lo=Math.min(plan.stop,plan.entry,price||plan.entry);
  const hi=Math.max(tp,plan.entry,price||plan.entry);const rng=(hi-lo)||1;
  const pc=(v)=>Math.max(0,Math.min(100,(v-lo)/rng*100));
  const mk=(v,col,lbl,tt)=>v==null?'':`<i style="position:absolute;left:${pc(v)}%;top:-3px;width:2px;height:12px;background:${col}" title="${lbl} ${VX.fmt.price(v)}"></i>`;
  const zEntry=pc(plan.entry),zStop=pc(plan.stop);
  return `<div style="margin-top:8px" title="stop ${VX.fmt.price(plan.stop)} · entrée ${VX.fmt.price(plan.entry)} · objectif ${VX.fmt.price(tp)}">
    <div class="vx-flex" style="justify-content:space-between;font-size:9px;color:var(--vx-text-dim)">
      <span style="color:var(--vx-negative)">stop ${VX.fmt.price(plan.stop)}</span>
      <span>entrée ${VX.fmt.price(plan.entry)}</span>
      <span style="color:var(--vx-positive)">objectif ${VX.fmt.price(tp)}</span></div>
    <div style="position:relative;height:6px;border-radius:99px;margin-top:3px;overflow:hidden;
      background:linear-gradient(90deg,rgba(237,101,92,.35) 0%,rgba(237,101,92,.15) ${zStop}%,var(--vx-surface-0) ${zStop}%,var(--vx-surface-0) ${zEntry}%,rgba(54,200,137,.15) ${zEntry}%,rgba(54,200,137,.4) 100%)">
      ${price!=null?`<i style="position:absolute;left:${pc(price)}%;top:-3px;width:9px;height:9px;margin-left:-4px;border-radius:99px;background:var(--vx-text-primary,#f2f5f1);box-shadow:0 0 0 2px var(--vx-surface-0)" title="cours ${VX.fmt.price(price)}"></i>`:''}
    </div></div>`;
}
/* Ruban de momentum : perf 1S · 1M · 3M · 1A en mini-barres divergentes.
   Montre d'un coup si le titre accélère ou s'essouffle selon l'horizon. */
function perfRibbon(r){
  const H=[['1S',r.perf_w],['1M',r.perf_m],['3M',r.perf_q],['1A',r.perf_y]].filter(x=>x[1]!=null&&isFinite(x[1]));
  if(!H.length)return '';
  const mx=Math.max(6,...H.map(x=>Math.abs(x[1])));
  return `<div class="vx-flex" style="gap:5px;margin-top:7px" role="img" aria-label="momentum multi-horizons">`
    +H.map(([lbl,v])=>{const h=Math.max(3,Math.round(Math.abs(v)/mx*22));const up=v>=0;
      return `<span title="${lbl} : ${v>=0?'+':''}${VX.fmt.num(v,1)} %" style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px">
        <span style="display:flex;align-items:${up?'flex-end':'flex-start'};height:24px;width:100%">
          <i style="display:block;width:100%;height:${h}px;border-radius:2px;background:${up?'var(--vx-positive)':'var(--vx-negative)'};opacity:.9"></i></span>
        <b style="font:600 8px/1 var(--vx-font);color:var(--vx-text-faint)">${lbl}</b></span>`;}).join('')+'</div>';
}
function gradeBadge(g){if(!g)return '';
  const col={S:'#36c889',A:'#c9cdd4',B:'#dda23b',C:'#ed655c',D:'#ed655c'}[String(g).toUpperCase()]||'var(--vx-text-dim)';
  return `<span class="vx-badge" style="color:${col};border-color:${col}" title="note globale du moteur (S = élite)">${esc(g)}</span>`;}
function mtfBadge(r){const st=(r&&r.mtf&&r.mtf.state)||'';const u=st.toUpperCase();
  if(!u)return '';
  const col=u.includes('ALIGNÉ')?'var(--vx-positive)':u.includes('REPLI')?'var(--vx-warning)':'var(--vx-text-dim)';
  const short=u.includes('ALIGNÉ')?'MTF alignés':u.includes('REPLI')?'MTF repli':'MTF neutre';
  return `<span class="vx-badge" style="color:${col}" title="${esc((r.mtf&&r.mtf.note)||st)}">${short}</span>`;}
function noTradeBadge(r){return r&&r.vx_notrade?`<span class="vx-badge" style="color:var(--vx-negative)" title="dossier interdit par le moteur — voir les raisons">🚫 NO-TRADE</span>`:'';}
function rail52(v){
  if(v==null||isNaN(v))return '—';
  const p=Math.max(0,Math.min(100,v));
  return `<span class="vx-rail52" title="position dans la fourchette 52 semaines : ${Math.round(p)} %"><i style="left:${p}%"></i></span>`;
}

/* ═════════ SCREENER (vue par défaut) — de 515 titres à UNE décision ═════════ */
/* CLASSE D'INSTRUMENT — sous-vues Actions et ETF.
   Vertex sait classer un instrument, mais ce verdict n'est PAS servi sur les
   lignes du scan. On ne recree donc pas la regle ici : on lit son REFERENTIEL
   cure, injecte par la page, et l'ecran DIT ce que cette couverture vaut.
   Un titre hors des deux listes n'est jamais classe de force. */
const _ETF=new Set(CLASSES.etf||[]), _ACT=new Set(CLASSES.actions||[]);
function classeDe(sym){
  const s=String(sym||'').toUpperCase();
  return _ETF.has(s)?'ETF':(_ACT.has(s)?'ACTION':'NON_CLASSE');
}
async function renderScreener(classe){
  const scan=await VX.fetch('/scan',{ttl:120000});
  paintContext(scan);
  let rows=(scan.rows||[]).filter(r=>r.score!==undefined);
  let bandeau='';
  if(classe){
    const total=rows.length;
    const nonClasses=rows.filter(r=>classeDe(r.symbol)==='NON_CLASSE').length;
    rows=rows.filter(r=>classeDe(r.symbol)===classe);
    const nom=classe==='ETF'?'ETF':'actions';
    bandeau='<div class="vx2-banner" data-kind="prudence" role="status"><span>'
      +'<b>'+rows.length+'</b> '+nom+' sur '+total+' ligne(s) scorée(s). '
      +'Le classement vient du <b>référentiel curé</b> de Vertex '
      +'('+(_ETF.size)+' ETF, '+(_ACT.size)+' actions au référentiel sectoriel), '
      +'pas d’un champ servi par le scan : '
      +(nonClasses?('<b>'+nonClasses+'</b> ligne(s) restent non classées et n’apparaissent '
                    +'dans aucune des deux vues — elles sont visibles au '
                    +'<a href="/opportunities?view=screener">Radar</a>.')
                 :'aucune ligne non classée.')
      +'</span></div>';
  }
  if(!rows.length){
    ($('op-body')||{}).innerHTML='<div class="vx2-state" data-kind="empty" role="status">'
      +'<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
      +'<p class="vx2-state-title">'+(classe
          ?('Aucun '+(classe==='ETF'?'ETF':'titre action')+' scoré dans le scan courant')
          :'Aucun titre scoré dans le scan courant')+'</p>'
      +'<p class="vx2-state-cause">L’entonnoir n’a rien à classer : le dernier scan '
      +'n’a produit aucune ligne portant un score. La barre de contexte '
      +'ci-dessus dit de quelle source et de quand il date.</p>'
      +'<div class="vx2-state-actions">'
      +'<a class="vx2-btn" href="/system?view=data">Ouvrir Système → Données</a></div>'
      +'</div>';
    return;}
  const detail=scan.detail||{};
  const byId={};rows.forEach(r=>{if(r&&r.symbol)byId[r.symbol]=r;});   // index partagé (dossier express, revue…)
  const sectors=[...new Set(rows.map(r=>r.sector).filter(Boolean))].sort();

  /* État des filtres : URL (liens entrants) > localStorage > défauts. */
  let saved={};try{saved=JSON.parse(localStorage.getItem('vxScreenFilters')||'{}')}catch(e){}
  const state=Object.assign({bucket:'',sector:'',vehicle:'',setup:'',mtf:'',grade:'',
      minScore:0,minPwin:0,minRR:0,minRvol:0,maxPrice:0,
      setBreakout:false,setPullback:false,setSqueeze:false,setAccum:false,
      exclNoTrade:false,exclHeld:false,exclProxy:false},
    saved,{bucket:PARAMS.decision||saved.bucket||'',sector:PARAMS.sector||saved.sector||'',
           setup:(PARAMS.setup||saved.setup||'').toUpperCase()});
  /* URL entrante > sauvegarde : un lien partagé impose ses filtres */
  (function(){const u=new URLSearchParams(location.search);
    ['bucket','sector','vehicle','mtf','grade','setup'].forEach(k=>{if(u.get(k))state[k]=u.get(k);});
    ['minScore','minPwin','minRR','minRvol','maxPrice'].forEach(k=>{if(u.get(k))state[k]=+u.get(k)||0;});
    ['setBreakout','setPullback','setSqueeze','setAccum','exclNoTrade','exclHeld','exclProxy'].forEach(k=>{if(u.get(k)==='1')state[k]=true;});})();
  function persist(){
    try{localStorage.setItem('vxScreenFilters',JSON.stringify(state))}catch(e){}
    /* reflète les filtres non vides dans l'URL — lien partageable, retour fidèle */
    try{const u=new URLSearchParams();
      Object.keys(state).forEach(k=>{const v=state[k];
        if(v===true)u.set(k,'1');else if(v&&v!==0&&v!=='')u.set(k,v);});
      const qs=u.toString();
      history.replaceState(null,'',location.pathname+(qs?'?'+qs:'')+location.hash);}catch(e){}
  }
  const heldSyms=new Set(((window.VXEntities?VXEntities.positions():[])||[]).map(p=>String(p.sym).toUpperCase()));
  function vehicleOf(r){const v=r&&r.vehicle;return String((v&&v.reco)||v||'').toUpperCase();}
  function mtfState(r){const m=r&&r.mtf;return String((m&&m.state)||'').toUpperCase();}
  function filtered(){
    let f=rows;
    if(state.bucket)f=f.filter(r=>bucketOf(r)===state.bucket);
    if(state.sector)f=f.filter(r=>r.sector===state.sector);
    if(state.vehicle)f=f.filter(r=>vehicleOf(r).includes(state.vehicle));
    if(state.mtf)f=f.filter(r=>mtfState(r).includes(state.mtf));
    if(state.grade){const ord={S:4,A:3,B:2,C:1,D:0};const min=ord[state.grade];
      f=f.filter(r=>(ord[String(r.grade||'').toUpperCase()]??-1)>=min);}
    if(state.setup)f=f.filter(r=>(pbText(r)||'').toUpperCase().includes(state.setup));
    if(state.setBreakout)f=f.filter(r=>r.breakout===true);
    if(state.setPullback)f=f.filter(r=>r.pullback===true);
    if(state.setSqueeze)f=f.filter(r=>r.squeeze===true);
    if(state.setAccum)f=f.filter(r=>r.accumulation===true);
    if(state.exclNoTrade)f=f.filter(r=>!r.vx_notrade);
    if(state.exclHeld)f=f.filter(r=>!heldSyms.has(r.symbol));
    if(state.exclProxy)f=f.filter(r=>r.st_fproxy!==true);
    if(state.minScore)f=f.filter(r=>(r.score||0)>=state.minScore);
    if(state.minPwin)f=f.filter(r=>((r.vx_pwin||0)*100)>=state.minPwin);
    if(state.minRR)f=f.filter(r=>(r.rr||0)>=state.minRR);
    if(state.minRvol)f=f.filter(r=>(r.rvol||0)>=state.minRvol);
    if(state.maxPrice)f=f.filter(r=>(r.price||0)<=state.maxPrice);
    return f;
  }
  /* ── Squelette de la vue ── */
  ($('op-body')||{}).innerHTML=demoBanner(scan)+bandeau+`
    <div class="vx-screenbar" role="group" aria-label="Filtres du screener">
      <span class="vx-meta" style="flex-basis:100%;display:flex;flex-wrap:wrap;gap:.4rem;align-items:center">
        <button class="vx-btn vx-btn-sm vx-btn-ghost" id="op-reset">Réinitialiser les filtres</button>
        <span class="vx-meta vx-right" id="op-count"></span></span>
      ${OUT.map(b=>`<button class="vx-chip" data-fk="bucket" data-fv="${b}" aria-pressed="${state.bucket===b}">${b}</button>`).join('')}
      <select class="vx-select" data-fk="sector" style="width:auto" aria-label="Secteur">
        <option value="">Tous secteurs</option>${sectors.map(s=>`<option ${state.sector===s?'selected':''}>${s}</option>`).join('')}</select>
      <select class="vx-select" data-fk="vehicle" style="width:auto" aria-label="Véhicule">
        <option value="">Action & option</option>
        <option value="ACTION" ${state.vehicle==='ACTION'?'selected':''}>Plutôt action</option>
        <option value="OPTION" ${state.vehicle==='OPTION'?'selected':''}>Plutôt option</option></select>
      <select class="vx-select" data-fk="mtf" style="width:auto" aria-label="Multi-horizons">
        <option value="">Tous horizons</option>
        <option value="ALIGNÉ" ${state.mtf==='ALIGNÉ'?'selected':''}>Journalier + hebdo alignés</option>
        <option value="REPLI" ${state.mtf==='REPLI'?'selected':''}>Repli dans tendance</option>
        <option value="NEUTRE" ${state.mtf==='NEUTRE'?'selected':''}>Neutre</option></select>
      <select class="vx-select" data-fk="grade" style="width:auto" aria-label="Note minimale">
        <option value="">Toute note</option>
        <option value="S" ${state.grade==='S'?'selected':''}>Note S seulement</option>
        <option value="A" ${state.grade==='A'?'selected':''}>Note A et mieux</option>
        <option value="B" ${state.grade==='B'?'selected':''}>Note B et mieux</option></select>
      <span class="vx-meta" style="flex-basis:100%;display:flex;flex-wrap:wrap;gap:.4rem;align-items:center">SETUPS
        <button class="vx-chip" data-ft="setBreakout" aria-pressed="${state.setBreakout}">🚀 Cassure</button>
        <button class="vx-chip" data-ft="setPullback" aria-pressed="${state.setPullback}">🎯 Repli</button>
        <button class="vx-chip" data-ft="setSqueeze" aria-pressed="${state.setSqueeze}">🔒 Compression</button>
        <button class="vx-chip" data-ft="setAccum" aria-pressed="${state.setAccum}">📥 Accumulation</button>
        <span style="width:10px"></span>EXCLURE
        <button class="vx-chip" data-ft="exclNoTrade" aria-pressed="${state.exclNoTrade}">🚫 no-trade moteur</button>
        <button class="vx-chip" data-ft="exclHeld" aria-pressed="${state.exclHeld}">💼 mes positions</button>
        <button class="vx-chip" data-ft="exclProxy" aria-pressed="${state.exclProxy}">≈ fondamental estimé</button></span>
      <label class="rng">score ≥ <input type="range" data-fk="minScore" min="0" max="90" step="5" value="${state.minScore}"><b>${state.minScore||'0'}</b></label>
      <label class="rng">proba gain ≥ <input type="range" data-fk="minPwin" min="0" max="90" step="5" value="${state.minPwin}"><b>${state.minPwin||'0'}%</b></label>
      <label class="rng">gain/risque ≥ <input type="range" data-fk="minRR" min="0" max="4" step="0.5" value="${state.minRR}"><b>${state.minRR||'0'}×</b></label>
      <label class="rng">volume ≥ <input type="range" data-fk="minRvol" min="0" max="3" step="0.5" value="${state.minRvol}"><b>×${state.minRvol||'0'}</b></label>
      <label class="rng">prix ≤ <input type="range" data-fk="maxPrice" min="0" max="1000" step="25" value="${state.maxPrice}"><b>${state.maxPrice?('$'+state.maxPrice):'∞'}</b></label>
      <input class="vx-input" data-fk="setup" style="width:130px" placeholder="setup (BREAKOUT…)" value="${esc(state.setup)}" aria-label="Setup">
    </div>
    <div class="vx-scr-kpis" id="op-kpis" aria-label="Résumé des résultats"></div>
    <div class="vx-grid vx-mt4">
      <div class="vx-col-8" id="op-scatter"></div>
      <div class="vx-col-4">
        <div class="vx-card" id="op-sel-card"><div class="vx-card-header"><span class="vx-card-title">Sélection</span></div>
          <div id="op-radar-sel">${'<div class="vx-meta">Clique un point du nuage pour ouvrir son dossier express.</div>'}</div></div>
        <div id="op-funnel" class="vx-mt3"></div>
      </div>
    </div>
    <div class="vx-grid vx-mt4">
      <section class="vx-card vx-col-6" id="op-dist-card"><div class="vx-card-header">
        <span class="vx-card-title">Scores des résultats</span>
        <span class="vx-chart-question">Le filtre isole-t-il vraiment le haut du panier ?</span></div>
        <div id="op-dist"></div>
        <div class="vx-card-foot"><span class="vx-meta" id="op-dist-meta"></span></div></section>
      <div class="vx-col-6" id="op-sectors"></div>
    </div>
    <div class="vx-grid vx-mt4">
      <div class="vx-col-8" id="op-heat"></div>
      <div class="vx-col-4" id="op-verdicts"></div>
    </div>
    <div id="op-topcards" class="vx-mt4"></div>
    <div class="vx-card vx-mt4"><div class="vx-card-header"><span class="vx-card-title">Tous les résultats</span>
      <span class="vx-chart-question">Chaque opportunité en carte — score, objectifs/stop, « pourquoi » ; un clic ouvre la fiche.</span>
      <span class="vx-right vx-flex" style="gap:6px;align-items:center"><span class="vx-meta">Trier</span><select class="vx-select" id="op-sort" style="width:auto" aria-label="Trier les résultats"></select></span></div>
      <div id="op-table"></div>
      <div class="vx-card-footer">${VX.updateIndicator(scan.scan_ts||scan.updated,scan.source,metaMode(scan))}
        · <span id="op-table-count"></span> · tri : <span id="op-sort-label">score</span></div></div>`;

  /* ── KPI live ── */
  function paintKpis(f){
    const buys=f.filter(r=>r.verdict==='BUY'||r.verdict==='ACHETER').length;
    const avg=(arr)=>arr.length?arr.reduce((a,b)=>a+b,0)/arr.length:null;
    const avgScore=avg(f.map(r=>r.score).filter(x=>x!=null));
    const pwins=f.map(r=>r.vx_pwin).filter(x=>x!=null).map(x=>x*100);
    const avgPwin=avg(pwins);
    const bySec={};f.forEach(r=>{if(r.sector){(bySec[r.sector]=bySec[r.sector]||[]).push(r.score||0);}});
    const bestSec=Object.entries(bySec).map(([s,v])=>[s,avg(v)]).sort((a,b)=>b[1]-a[1])[0];
    ($('op-kpis')||{}).innerHTML=
      `<div class="k"><b>${f.length}</b><span>titres retenus</span></div>`
      +`<div class="k" data-tone="${buys>0?'pos':''}"><b style="color:var(--vx-positive)">${buys}</b><span>signaux d’achat</span></div>`
      +`<div class="k" data-tone="${avgScore>=60?'pos':avgScore<45?'neg':''}"><b>${avgScore!=null?Math.round(avgScore):'—'}</b><span>score moyen</span></div>`
      +`<div class="k" data-tone="${avgPwin>=55?'pos':avgPwin<45?'neg':''}"><b>${avgPwin!=null?Math.round(avgPwin)+' %':'—'}</b><span>proba gain moyenne</span></div>`
      +`<div class="k" data-tone="brand"><b style="font-size:15px;line-height:1.4">${bestSec?esc(bestSec[0]):'—'}</b><span>secteur le mieux noté</span></div>`
      +(function(){const al=f.filter(r=>mtfState(r).includes('ALIGNÉ')).length;
        return `<div class="k"><b>${f.length?Math.round(al/f.length*100)+' %':'—'}</b><span>journalier+hebdo alignés</span></div>`;})()
      +(function(){const el=f.filter(r=>['S','A'].includes(String(r.grade||'').toUpperCase())).length;
        return `<div class="k" data-tone="${el>0?'pos':''}"><b>${el}</b><span>notes S ou A (élite)</span></div>`;})();
    ($('op-count')||{}).textContent=f.length+' / '+rows.length+' titres';
  }

  /* ── Nuage POURQUOI : avantage statistique × proba de gain ── */
  let scatterChart=null;
  function paintScatter(f){
    const cc=VXCharts.colors;
    const pts=f.filter(r=>r.vx_edge!=null&&r.vx_pwin!=null).map(r=>({
      x:r.vx_edge,y:r.vx_pwin*100,sym:r.symbol,v:r.verdict,sector:r.sector||'',
      price:r.price,rr:r.rr,score:r.score,conv:r.st_conf,setup:pbText(r),noTrade:!!r.vx_notrade,
      ev:r.vx_ev,asym:r.vx_asym,kelly:r.vx_kelly,flags:r.vx_flags||[],
      /* rayon = Kelly (déjà en %, 0-25) que le moteur oserait — repli conviction */
      r:r.vx_kelly!=null?4+Math.min(11,Math.max(0,r.vx_kelly*0.7)):4+Math.min(9,Math.max(0,(r.st_conf||50)-40)/6)}));
    const host=$('op-scatter');
    if(!pts.length){host.innerHTML='<div class="vx-card">'+VX.states.empty('Aucun titre du filtre ne porte à la fois un avantage (edge) et une proba de gain — élargis les filtres.')+'</div>';scatterChart=null;return;}
    const elite=pts.filter(p=>p.x>=60&&p.y>=60).length;
    VXCharts.card('op-scatter',{
      title:'Le POURQUOI en un regard — avantage × proba de gain',
      question:'Quels titres combinent un vrai avantage statistique ET une bonne proba de réussite ?',
      conclusion:elite+' titre(s) en zone ÉLITE (avantage ≥ 60 et proba ≥ 60 %)',
      height:320,source:scan.source,timestamp:scan.scan_ts||scan.updated,mode:metaMode(scan),
      limits:'avantage & proba : moteur Vertex Monte-Carlo · taille = Kelly (taille de position suggérée) · croix corail = NO-TRADE moteur',
      explain:{shows:'Chaque point est un titre filtré, placé par son avantage statistique (edge) et sa probabilité de gain simulée.',
        why:'Un bon dossier combine un avantage réel ET une proba favorable — l’un sans l’autre ne suffit pas.',
        confirm:'Un point qui migre vers le haut-droit en gardant sa conviction.',
        invalidate:'Proba qui retombe sous 50 % — le dossier perd son espérance.'},
      render:(cv)=>{scatterChart=VXCharts.mount(cv,{type:'scatter',
        data:{datasets:[{data:pts,
          pointRadius:(ctx)=>ctx.raw?ctx.raw.r:4,pointHoverRadius:(ctx)=>ctx.raw?ctx.raw.r+3:8,
          /* croix = NO-TRADE moteur (dossier interdit malgré ses chiffres) */
          pointStyle:(ctx)=>ctx.raw&&ctx.raw.noTrade?'crossRot':'circle',
          pointBackgroundColor:(ctx)=>{const v=ctx.raw&&ctx.raw.v;
            return v==='BUY'||v==='ACHETER'?cc.positive:(v==='AVOID'||v==='ÉVITER'?cc.negative:cc.neutral);},
          pointBorderColor:(ctx)=>ctx.raw&&ctx.raw.noTrade?cc.negative:'rgba(255,255,255,.22)',pointBorderWidth:(ctx)=>ctx.raw&&ctx.raw.noTrade?2:1}]},
        options:{scales:{
          x:{title:{display:true,text:'Avantage statistique (edge) →'},min:0,max:100,grid:{color:'rgba(255,255,255,.05)'}},
          y:{title:{display:true,text:'Proba de gain % ↑'},min:0,max:100,grid:{color:'rgba(255,255,255,.05)'}}},
          plugins:{tooltip:{callbacks:{label:(ctx)=>{const d2=ctx.raw;
            return `${d2.sym} · avantage ${Math.round(d2.x)} · proba ${Math.round(d2.y)} %`+(d2.ev!=null?' · espérance '+(d2.ev>=0?'+':'')+VX.fmt.num(d2.ev,1)+' %':'')+(d2.noTrade&&d2.flags[0]?' · 🚫 '+flagFr(d2.flags[0]):'');}}}},
          onClick:(evt,els,chart)=>{const p=chart.getElementsAtEventForMode(evt,'nearest',{intersect:true},true);
            if(p.length)selectSym(chart.data.datasets[0].data[p[0].index]);}},
        plugins:[{id:'opZones',beforeDatasetsDraw(chart){
          const a=chart.chartArea,sx=chart.scales.x,sy=chart.scales.y,g=chart.ctx;
          const x60=sx.getPixelForValue(60),y60=sy.getPixelForValue(60),y50=sy.getPixelForValue(50);
          g.save();
          g.fillStyle='rgba(54,200,137,.055)';g.fillRect(x60,a.top,a.right-x60,y60-a.top);
          g.fillStyle='rgba(237,101,92,.045)';g.fillRect(a.left,y50,a.right-a.left,a.bottom-y50);
          g.strokeStyle='rgba(255,255,255,.10)';g.setLineDash([4,4]);g.beginPath();
          g.moveTo(x60,a.top);g.lineTo(x60,a.bottom);g.moveTo(a.left,y60);g.lineTo(a.right,y60);g.stroke();g.setLineDash([]);
          g.font='10px sans-serif';g.fillStyle='rgba(54,200,137,.55)';g.fillText('ZONE ÉLITE',a.right-70,a.top+14);
          g.fillStyle='rgba(237,101,92,.5)';g.fillText('proba défavorable',a.left+6,a.bottom-8);
          g.restore();}}]});return scatterChart;}});
  }
  function selectSym(d){
    const plan=(detail[d.sym]&&detail[d.sym].plan)||null;
    const flags=(d.flags||[]);
    ($('op-radar-sel')||{}).innerHTML=
      `<div class="vx-flex"><span class="vx-ticker" style="font-size:16px">${esc(d.sym)}</span>${window.VXEntities?VXEntities.badges(d.sym):''}
         <span class="vx-badge vx-badge-decision vx-right" data-decision="${esc(d.v||'')}">${esc(VERD_FR[d.v]||d.v||'n/d')}</span></div>
       ${d.noTrade?`<div class="vx-insight vx-mt2" data-tone="risk"><b>🚫 NO-TRADE moteur</b>${flags.length?'<div class="vx-mt1" style="font-size:12px">'+flags.map(flagFr).map(esc).join(' · ')+'</div>':''}</div>`:(flags.length?`<div class="vx-flex vx-wrap vx-mt2" style="gap:.3rem">${flags.slice(0,3).map(fl=>`<span class="vx-badge">${esc(flagFr(fl))}</span>`).join('')}</div>`:'')}
       <div class="vx-kv vx-mt2"><span class="k">Avantage (edge)</span><span class="v vx-mono">${VX.fmt.nd(Math.round(d.x))} / 100</span></div>
       <div class="vx-kv"><span class="k">Proba de gain</span><span class="v vx-mono">${VX.fmt.nd(Math.round(d.y))} %</span></div>
       ${d.ev!=null?`<div class="vx-kv"><span class="k">Espérance / trade</span><span class="v vx-mono ${d.ev>0?'vx-pos':d.ev<0?'vx-neg':''}">${(d.ev>=0?'+':'')+VX.fmt.num(d.ev,1)} %</span></div>`:''}
       ${d.asym!=null?`<div class="vx-kv"><span class="k">Asymétrie gain/perte</span><span class="v vx-mono">${VX.fmt.nd(d.asym)}</span></div>`:''}
       ${d.kelly!=null?`<div class="vx-kv"><span class="k">Taille suggérée (Kelly)</span><span class="v vx-mono">${VX.fmt.num(d.kelly,1)} %</span></div><div id="op-sel-kelly" style="margin:-4px 0 2px"></div>`:''}
       <div class="vx-kv"><span class="k">Score</span><span class="v vx-mono">${VX.fmt.nd(d.score)}</span></div>
       <div class="vx-kv"><span class="k">Cours</span><span class="v vx-mono">${d.price!=null?VX.fmt.price(d.price):'n/d'}</span></div>
       <div class="vx-kv"><span class="k">Gain/risque</span><span class="v vx-mono">${d.rr!=null?VX.fmt.num(d.rr,1)+'×':'n/d'}</span></div>
       ${levelsBar(plan,d.price)}
       <div id="op-sel-mc" class="vx-mt2"></div>
       ${(function(){const r0=byId[d.sym];return r0?perfRibbon(r0):'';})()}
       ${(function(){const cr=detail[d.sym]&&detail[d.sym].chart_read;return cr?`<div class="vx-meta vx-mt2" style="white-space:normal;line-height:1.45"><b>Lecture technique :</b> ${esc(cr)}</div>`:'';})()}
       ${d.setup?`<div class="vx-kv vx-mt2"><span class="k">Setup</span><span class="v">${esc(d.setup)}</span></div>`:''}
       ${d.sector?`<div class="vx-kv"><span class="k">Secteur</span><span class="v">${esc(d.sector)}</span></div>`:''}
       <div class="vx-flex vx-wrap vx-mt2" style="gap:.3rem">
         <button class="vx-btn vx-btn-sm vx-btn-primary" data-open-analysis="${esc(d.sym)}">Analyse</button>
         <button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal('${esc(d.sym)}','follow')">Suivre</button>
         <button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal('${esc(d.sym)}','alert')">Alerte</button>
         <a class="vx-btn vx-btn-sm" href="/options/dossier/${esc(d.sym)}">Options</a></div>`;
    /* Visuels quant du tiroir (mêmes moteurs que la fiche Analyse — data déjà dans le scan) */
    (function(){
      if(!window.VXCharts)return;
      const cc=VXCharts.colors,dd=detail[d.sym]||{},v=dd.vertex||{};
      const kp=(v.kelly&&v.kelly.pct!=null)?v.kelly.pct:d.kelly;
      if(kp!=null&&document.getElementById('op-sel-kelly')&&VXCharts.gauge){
        VXCharts.gauge('op-sel-kelly',{value:kp,min:0,max:15,unit:'%',
          bands:[{to:6,color:cc.neutral},{to:12,color:cc.brand},{to:15,color:cc.warning}]});
      }
      const mc=v.mc||{},bs=v.bootstrap||{},mcEl=document.getElementById('op-sel-mc');
      if(mcEl&&bs.p05!=null&&bs.p95!=null&&VXCharts.card){
        const tp1=mc.p_tp1_first,stopf=mc.p_stop_before_tp1;
        VXCharts.card('op-sel-mc',{title:'Dispersion Monte-Carlo',unit:'%',
          question:'Fourchette réaliste du rendement sur l’horizon ?',
          conclusion:(tp1!=null?'TP1 avant stop '+Math.round(tp1*100)+'% · stop '+Math.round((stopf||0)*100)+'%':''),
          height:150,source:'Monte-Carlo · bootstrap',timestamp:null,mode:'delayed',limits:'MODEL_ESTIMATE',
          render:function(cv){return VXCharts.mount(cv,{type:'bar',
            data:{labels:['P05','P50','P95'],datasets:[{data:[bs.p05,bs.p50,bs.p95],backgroundColor:[cc.negative,cc.neutral,cc.positive],borderRadius:4,maxBarThickness:26}]},
            options:{indexAxis:'y',scales:{x:{ticks:{callback:function(x){return x+'%';},color:cc.muted,font:{size:9}},grid:{color:cc.grid}},y:{grid:{display:false},ticks:{color:cc.text,font:{size:10}}}},plugins:{legend:{display:false}}}});}});
      }
    })();
  }

  /* ── Distribution des scores (résultats filtrés) ── */
  function paintDist(f){
    const el=$('op-dist');if(!el)return;
    const dist=Array.from({length:10},()=>0);
    f.forEach(r=>{const sIdx=Math.max(0,Math.min(9,Math.floor((r.score||0)/10)));dist[sIdx]++;});
    const tot=f.length;
    if(!tot){el.innerHTML=VX.states.empty('Aucun résultat avec ces filtres.');($('op-dist-meta')||{}).textContent='';return;}
    const maxN=Math.max(1,...dist);
    el.innerHTML='<div style="display:flex;gap:4px;align-items:flex-end;padding:8px 2px">'+dist.map((n,i)=>{
      const hh=Math.round(n/maxN*100);
      const col=i>=7?'var(--vx-positive)':i<=2?'var(--vx-negative)':'var(--vx-warning)';
      return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:3px" role="img" aria-label="score ${i*10}-${i*10+10} : ${n} titres" title="${n} titre(s) entre ${i*10} et ${i*10+10}">
        <span style="font-size:9.5px;color:var(--vx-text-dim)">${n||''}</span>
        <span style="width:100%;height:110px;display:flex;align-items:flex-end"><span style="width:100%;height:${hh}%;background:${col};border-radius:3px 3px 0 0;min-height:2px;opacity:.85"></span></span>
        <span style="font-size:9px;color:var(--vx-text-muted);font-variant-numeric:tabular-nums">${i*10}</span></div>`;}).join('')+'</div>';
    const avg=Math.round(f.reduce((a,r)=>a+(r.score||0),0)/tot);
    ($('op-dist-meta')||{}).textContent='score moyen des résultats : '+avg+' / 100 · '+tot+' titres';
  }

  /* ── Secteurs des résultats (score moyen par secteur, filtré) ── */
  function paintSectors(f){
    const host=$('op-sectors');if(!host)return;
    const by={};f.forEach(r=>{if(r.sector){(by[r.sector]=by[r.sector]||[]).push(r.score||0);}});
    const entries=Object.entries(by).map(([s,v])=>[s,Math.round(v.reduce((a,b)=>a+b,0)/v.length),v.length])
      .sort((a,b)=>b[1]-a[1]).slice(0,9);
    if(!entries.length){host.innerHTML='<div class="vx-card">'+VX.states.empty('Aucun secteur dans les résultats filtrés.')+'</div>';return;}
    VXCharts.sectorCard('op-sectors',{
      title:'Secteurs des résultats',unit:'titres',question:'Où se concentrent les titres retenus par TES filtres ?',
      conclusion:entries[0][0]+' en tête ('+entries[0][1]+' de score moyen · '+entries[0][2]+' titres)',
      labels:entries.map(e=>e[0]+' ('+e[2]+')'),values:entries.map(e=>e[1]),height:240,
      source:scan.source,timestamp:scan.scan_ts||scan.updated,mode:metaMode(scan),
      onSector:(name)=>{state.sector=name.replace(/ \(\d+\)$/,'');persist();syncBar();applyAll();},
      explain:{shows:'Le score moyen par secteur, calculé UNIQUEMENT sur les titres qui passent tes filtres.',
        why:'Concentrer l’attention là où les résultats filtrés sont les plus forts.',
        confirm:'Un secteur qui reste en tête quand tu durcis les filtres.',invalidate:'Un leadership qui dépend d’un seul titre.'}});
  }

  /* ── Carte d'opportunité RICHE (helper réutilisé : top + grille complète) ── */
  function oppCard(r){
    const dec=r.verdict||'';
    const gauge=(window.VXCharts&&VXCharts.confidenceGaugeSVG&&r.score!=null)
      ?VXCharts.confidenceGaugeSVG(r.score,verdictDir(dec),{size:78,stroke:7,dirLabel:verdictWord(dec)}):'';
    const pb=pbText(r);const ic=pbIcon(r);
    const ser=detail[r.symbol]&&detail[r.symbol].series;
    const spark=sparkMini(ser&&ser.close);
    const chips=[];
    if(r.vx_pwin!=null)chips.push(`<span class="vx-badge" style="color:var(--vx-positive)">proba. gain ${Math.round(r.vx_pwin*100)} %</span>`);
    if(r.vx_ev!=null)chips.push(`<span class="vx-badge" style="color:${r.vx_ev>0?'var(--vx-positive)':'var(--vx-negative)'}" title="espérance mathématique par trade">espérance ${(r.vx_ev>=0?'+':'')+VX.fmt.num(r.vx_ev,1)} %</span>`);
    if(r.vx_edge!=null)chips.push(`<span class="vx-badge">avantage ${Math.round(r.vx_edge)}</span>`);
    if(r.rr!=null)chips.push(`<span class="vx-badge">gain/risque ${VX.fmt.num(r.rr,1)}×</span>`);
    if(r.vx_kelly!=null&&r.vx_kelly>0)chips.push(`<span class="vx-badge" title="taille de position suggérée">Kelly ${VX.fmt.num(r.vx_kelly,0)} %</span>`);
    if(mtfBadge(r))chips.push(mtfBadge(r));
    if(r.rvol!=null&&r.rvol>=1.5)chips.push(`<span class="vx-badge" style="color:var(--vx-warning)">volume ×${VX.fmt.num(r.rvol,1)}</span>`);
    if(r.vx_notrade)chips.push(noTradeBadge(r));
    const planR=detail[r.symbol]&&detail[r.symbol].plan;
    return `<div class="vx-card vx-opp-card vx-card--premium ${r.vx_notrade?'vx-opp-notrade':''}" aria-label="${r.symbol}">
      <div class="vx-flex" style="align-items:flex-start;gap:.6rem">
        <div style="min-width:0;flex:1">
          <div class="vx-flex" style="gap:.4rem;flex-wrap:wrap"><button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" style="font-size:16px;padding-left:0" data-open-analysis="${r.symbol}">${r.symbol}</button>
            <span class="vx-badge">${bucketOf(r)}</span>${gradeBadge(r.grade)}</div>
          <div class="vx-mono vx-mt1" style="font-size:18px;font-weight:700;color:var(--vx-text-primary,#f4f1ec)">${r.price!=null?'$'+VX.fmt.price(r.price):'—'}</div>
          ${spark}${perfRibbon(r)}
        </div>
        <div style="flex:0 0 auto">${gauge}</div>
      </div>
      ${dimStrip(r)}
      <div class="vx-flex vx-wrap vx-mt1" style="gap:.3rem">${chips.join('')}</div>
      ${levelsBar(planR,r.price)}
      ${pb?`<div class="vx-meta vx-mt1" style="white-space:normal;line-height:1.45">${ic?esc(ic)+' ':''}<b>Pourquoi :</b> ${esc(pb)}</div>`:''}
      <div class="vx-flex vx-wrap vx-mt2" style="gap:.3rem">
        <button class="vx-btn vx-btn-sm vx-btn-primary" data-open-analysis="${r.symbol}">Analyser</button>
        <button class="vx-btn vx-btn-sm" data-inspect="${r.symbol}" title="Aperçu rapide">Aperçu</button>
        <button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal('${r.symbol}','follow')">Suivre</button>
        <button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal('${r.symbol}','alert')">Alerte</button>
        <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/options/dossier/${r.symbol}">Options</a>
      </div></div>`;
  }
  /* ── Top cartes des résultats (highlight 6) ── */
  function paintTopCards(f){
    const el=$('op-topcards');if(!el)return;
    const prio=(r)=>bucketOf(r)==='Actionnable'?0:bucketOf(r)==='Proche'?1:bucketOf(r)==='À surveiller'?2:3;
    const ranked=f.filter(r=>r.verdict!=='AVOID'&&r.verdict!=='ÉVITER')
      .slice().sort((a,b)=>prio(a)-prio(b)||(b.score||0)-(a.score||0)).slice(0,6);
    if(!ranked.length){el.innerHTML='';return;}
    el.innerHTML='<div class="vx-card-header" style="padding:0 0 8px"><span class="vx-card-title">Top des résultats — pourquoi eux</span>'
      +'<span class="vx-chart-question">Les 6 meilleurs candidats de TON filtre, avec leurs raisons.</span></div>'
      +'<div class="vx-opp-grid vx-mb2">'+ranked.map(oppCard).join('')+'</div>';
  }

  /* ── Table triable ── */
  const SORTS={score:{k:r=>r.score||0,label:'score'},pwin:{k:r=>(r.vx_pwin||0),label:'proba de gain'},
    ev:{k:r=>(r.vx_ev==null?-999:r.vx_ev),label:'espérance'},
    edge:{k:r=>(r.vx_edge||0),label:'avantage'},rr:{k:r=>(r.rr||0),label:'gain/risque'},
    rvol:{k:r=>(r.rvol||0),label:'volume relatif'},chg:{k:r=>(r.change||0),label:'variation'},
    perfw:{k:r=>(r.perf_w||0),label:'perf. semaine'},perfm:{k:r=>(r.perf_m||0),label:'perf. mois'},
    pos52:{k:r=>(r.pos52||0),label:'position 52 sem.'},
    grade:{k:r=>({S:4,A:3,B:2,C:1,D:0}[String(r.grade||'').toUpperCase()]||-1),label:'note'}};
  let sortKey='score',sortDir=-1,shownLimit=48;
  function populateSortSelect(){
    const sel=document.getElementById('op-sort');if(!sel||sel.dataset.ready)return;
    sel.innerHTML=Object.entries(SORTS).map(([k,s])=>`<option value="${k}"${k===sortKey?' selected':''}>${s.label}</option>`).join('');
    sel.dataset.ready='1';
    sel.addEventListener('change',()=>{sortKey=sel.value;sortDir=-1;shownLimit=48;paintTable(filtered());});
  }
  /* « Tous les résultats » = GRILLE DE CARTES riches (plus de table) : chaque
     opportunité en carte (score, objectifs/stop, pourquoi). Tri par sélecteur,
     pagination « voir plus ». Un clic sur la carte ouvre la fiche. */
  function paintTable(f){
    populateSortSelect();
    const s=SORTS[sortKey]||SORTS.score;
    const sorted=f.slice().sort((a,b)=>(s.k(b)-s.k(a))*(-sortDir));
    ($('op-sort-label')||{}).textContent=s.label;
    const shown=sorted.slice(0,shownLimit);
    ($('op-table-count')||{}).textContent=shown.length+' affichées sur '+f.length;
    ($('op-table')||{}).innerHTML=sorted.length
      ?'<div class="vx-opp-grid">'+shown.map(oppCard).join('')+'</div>'
        +(sorted.length>shown.length?`<div class="vx-mt3" style="text-align:center"><button class="vx-btn vx-btn-sm" id="op-more">Voir plus (${sorted.length-shown.length} restantes)</button></div>`:'')
      :VX.states.empty('Aucun titre ne correspond aux filtres.','<button class="vx-btn vx-btn-sm" id="op-clear2">Effacer les filtres</button>');
    document.getElementById('op-clear2')?.addEventListener('click',()=>resetFilters());
    document.getElementById('op-more')?.addEventListener('click',()=>{shownLimit+=48;paintTable(filtered());});
  }

  /* ── Entonnoir CLIQUABLE : chaque étage applique le filtre correspondant ── */
  async function paintFunnel(){
    const el=$('op-funnel');if(!el)return;
    let fn;try{fn=await VX.fetch('/api/opportunities/funnel',{ttl:60000});}catch(e){return;}
    if(!fn||!fn.stages||!fn.stages.length)return;
    el.innerHTML='<div class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Entonnoir</span>'
      +'<span class="vx-chart-question">Cliquer un étage filtre le screener.</span></div>'
      +'<div id="op-funnel-viz"></div>'
      +(fn.actionable_symbols&&fn.actionable_symbols.length?'<div class="vx-dim vx-mt2" style="font-size:12px">Actionnables : '
        +fn.actionable_symbols.map(s=>'<button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="'+esc(s)+'" style="padding:0 4px;color:var(--vx-positive)">'+esc(s)+'</button>').join(' ')+'</div>':'')
      /* Delta depuis le scan precedent (lot 12/16) : trois etats honnetes —
         premier scan (pas de base), rien de note, listes bornees serveur. */
      +(function(){const d=fn.delta||{};
        if(d.disponible===false)return '';
        if(d.premier_scan)return '<div class="vx-dim vx-mt1" style="font-size:12px">Premier scan — pas encore de comparaison.</div>';
        const en=(d.entrants||[]).map(esc).join(', '),so=(d.sortants||[]).map(esc).join(', ');
        if(!en&&!so)return '<div class="vx-dim vx-mt1" style="font-size:12px">Aucun changement d\'actionnables depuis le scan précédent.</div>';
        return '<div class="vx-dim vx-mt1" style="font-size:12px">'
          +(en?'Entrés : '+en:'')+(en&&so?' · ':'')+(so?'Sortis : '+so:'')+'</div>';})()
      +'</div>';
    if(window.VXCharts&&VXCharts.funnel){
      VXCharts.funnel('op-funnel-viz',{stages:fn.stages.map(s=>({label:s.label,value:s.count})),
        fmt:v=>VX.fmt.nd(v),ariaLabel:'Entonnoir de sélection'});
      /* étages cliquables → mappe l'étage vers un filtre bucket approché */
      const map={'Actionnable':'Actionnable','Proche':'Proche','À surveiller':'À surveiller'};
      el.querySelectorAll('#op-funnel-viz [role="img"], #op-funnel-viz svg, #op-funnel-viz div').forEach(()=>{});
      el.querySelector('#op-funnel-viz').addEventListener('click',(ev)=>{
        const t=(ev.target.textContent||'').trim();
        const k=Object.keys(map).find(x=>t.includes(x));
        if(k){state.bucket=state.bucket===map[k]?'':map[k];persist();syncBar();applyAll();}});
    }
  }

  /* ── Heat secteur × statut : où vivent les résultats (clic = filtre combiné) ── */
  function paintHeat(f){
    const host=$('op-heat');if(!host||!window.VXCharts||!VXCharts.heatmapCard)return;
    const secs=[...new Set(f.map(r=>r.sector).filter(Boolean))];
    if(!secs.length){host.innerHTML='<div class="vx-card">'+VX.states.empty('Aucun secteur dans les résultats.')+'</div>';return;}
    const cnt={};f.forEach(r=>{const k=(r.sector||'')+'|'+bucketOf(r);cnt[k]=(cnt[k]||0)+1;});
    /* on garde le secteur BRUT (raw) séparé du libellé échappé — le filtre matche
       r.sector===raw, jamais la version HTML-échappée (bug « 0 titre » sur A&B). */
    const rows2=secs.map(sec=>({raw:sec,label:esc(sec),cells:OUT.map(b=>{
      const v=cnt[sec+'|'+b]||0;
      return {value:v||null,label:v?String(v):'—',title:sec+' · '+b+' : '+v+' titre(s)'};})}))
      .sort((a,b)=>{const t=(x)=>OUT.reduce((acc,bb,i)=>acc+(cnt[x.raw+'|'+bb]||0)*(OUT.length-i),0);return t(b)-t(a);});
    VXCharts.heatmapCard('op-heat',{
      title:'Carte secteur × statut',unit:'titres',question:'Dans quels secteurs vivent les dossiers les plus avancés ?',
      conclusion:'Colonne Actionnable = prêt · cliquer une cellule applique les deux filtres.',
      columns:OUT,rows:rows2,min:0,max:Math.max(4,...Object.values(cnt)),
      fmt:(v)=>v==null?'—':String(v),
      source:scan.source,timestamp:scan.scan_ts||scan.updated,mode:metaMode(scan),
      limits:'compte de titres par secteur et statut, sur TES filtres'});
    /* clic cellule → filtre secteur+statut */
    host.querySelectorAll('tbody tr').forEach((tr,ri)=>{
      [...tr.querySelectorAll('td')].slice(1).forEach((td,ci)=>{
        td.style.cursor='pointer';
        td.addEventListener('click',()=>{
          const raw=rows2[ri]&&rows2[ri].raw;
          state.sector=state.sector===raw?'':raw;
          state.bucket=state.bucket===OUT[ci]?'':OUT[ci];
          persist();syncBar();applyAll();});
      });});
  }
/* ── Donut verdicts des résultats ── */
  function paintVerdicts(f){
    const host=$('op-verdicts');if(!host)return;
    const cnt={};f.forEach(r=>{const v=VERD_FR[r.verdict]||r.verdict||'n/d';cnt[v]=(cnt[v]||0)+1;});
    const ks=Object.keys(cnt);
    if(!ks.length){host.innerHTML='<div class="vx-card">'+VX.states.empty('Aucun verdict.')+'</div>';return;}
    const tone={'ACHAT':'#36c889','SURVEILLER':'#c0b79f','ATTENDRE':'#dda23b','ÉVITER':'#ed655c'};
    VXCharts.donutCard('op-verdicts',{title:'Verdicts des résultats',unit:'titres',
      question:'Que pense le moteur de TA sélection ?',
      labels:ks,values:ks.map(k=>cnt[k]),colors:ks.map(k=>tone[k]||'#8f8a83'),height:200,
      source:scan.source,timestamp:scan.scan_ts||scan.updated,mode:metaMode(scan)});
  }
  /* ── Application globale des filtres ── */
  function applyAll(){
    const f=filtered();
    paintKpis(f);paintScatter(f);paintDist(f);paintSectors(f);paintHeat(f);paintVerdicts(f);paintTopCards(f);paintTable(f);
  }
  function syncBar(){
    document.querySelectorAll('[data-fk="bucket"]').forEach(c=>
      c.setAttribute('aria-pressed',String(c.dataset.fv===state.bucket)));
    const sec=document.querySelector('select[data-fk="sector"]');if(sec)sec.value=state.sector;
  }
  function resetFilters(silent){
    Object.assign(state,{bucket:'',sector:'',vehicle:'',setup:'',mtf:'',grade:'',
      minScore:0,minPwin:0,minRR:0,minRvol:0,maxPrice:0,
      setBreakout:false,setPullback:false,setSqueeze:false,setAccum:false,
      exclNoTrade:false,exclHeld:false,exclProxy:false});
    const gs=document.querySelector('select[data-fk="grade"]');if(gs)gs.value='';
    persist();
    document.querySelectorAll('.vx-screenbar input[type=range]').forEach(r=>{r.value=0;
      const b=r.closest('label').querySelector('b');
      b.textContent=r.dataset.fk==='maxPrice'?'∞':'0'+(r.dataset.fk==='minPwin'?'%':r.dataset.fk==='minRR'?'×':'');});
    document.querySelectorAll('.vx-screenbar [data-ft]').forEach(x=>x.setAttribute('aria-pressed','false'));
    const inp=document.querySelector('input[data-fk="setup"]');if(inp)inp.value='';
    const veh=document.querySelector('select[data-fk="vehicle"]');if(veh)veh.value='';
    const mtfSel=document.querySelector('select[data-fk="mtf"]');if(mtfSel)mtfSel.value='';
    if(!silent){syncBar();applyAll();}
  }
  /* Écouteurs de la barre */
  document.querySelectorAll('[data-fk="bucket"]').forEach(c=>c.addEventListener('click',()=>{
    state.bucket=state.bucket===c.dataset.fv?'':c.dataset.fv;persist();syncBar();applyAll();}));
  document.querySelector('select[data-fk="sector"]').addEventListener('change',function(){state.sector=this.value;persist();applyAll();});
  document.querySelector('select[data-fk="vehicle"]').addEventListener('change',function(){state.vehicle=this.value;persist();applyAll();});
  document.querySelector('select[data-fk="mtf"]').addEventListener('change',function(){state.mtf=this.value;persist();applyAll();});
  document.querySelector('select[data-fk="grade"]').addEventListener('change',function(){state.grade=this.value;persist();applyAll();});
  const applyDebounced=debounce(applyAll,120);
  document.querySelectorAll('.vx-screenbar input[type=range]').forEach(r=>r.addEventListener('input',function(){
    state[this.dataset.fk]=+this.value;
    const b=this.closest('label').querySelector('b');
    if(this.dataset.fk==='maxPrice')b.textContent=this.value>0?('$'+this.value):'∞';
    else b.textContent=this.value+(this.dataset.fk==='minPwin'?'%':this.dataset.fk==='minRR'?'×':'');
    persist();applyDebounced();}));
  document.querySelectorAll('.vx-screenbar [data-ft]').forEach(c=>c.addEventListener('click',()=>{
    state[c.dataset.ft]=!state[c.dataset.ft];
    c.setAttribute('aria-pressed',String(state[c.dataset.ft]));
    persist();applyAll();}));
  document.querySelector('input[data-fk="setup"]').addEventListener('input',function(){state.setup=this.value.toUpperCase();persist();applyDebounced();});
  document.getElementById('op-reset').addEventListener('click',()=>resetFilters());

  paintFunnel();
  applyAll();
  VX.context.restoreIfReturning();
}

/* ═════════ OPTIONS : screener du board réel ═════════ */
async function renderOptions(){
  const scan=await VX.fetch('/scan',{ttl:120000});
  paintContext(scan);
  const board=(scan.options_board||[]);
  window.__opCompare=function(symWanted){
    /* Plages NON chevauchantes : ≥0.45 défensif · 0.30-0.45 principal · 0.18-0.30 convexe */
    const catOf2=(c)=>{const d=Math.abs(c.delta||0);
      if(d>=0.45&&d<=0.65)return'BALANCED';if(d>=0.30&&d<0.45)return'DYNAMIC';
      if(d>=0.18&&d<0.30)return'ULTRA_CONVEX';return'AUTRE';};
    let pool=board;
    if(symWanted)pool=pool.filter(c=>c.sym===symWanted);
    const pick=(cat)=>pool.filter(c=>catOf2(c)===cat)
      .sort((a,b)=>(b.quality||0)-(a.quality||0))[0]||null;
    const trio=[['Défensif (Balanced)',pick('BALANCED')],
                ['PRINCIPAL (Dynamic)',pick('DYNAMIC')],
                ['Explosif (Ultra convex)',pick('ULTRA_CONVEX')]];
    const avail=trio.filter(([,c])=>c);
    if(!avail.length){VX.toast('Aucun contrat comparable sur ce filtre','warning');return;}
    const row=(label,c)=>c?`<tr>
      <td><b>${label}</b><br><span class="vx-mono vx-meta">${c.sym} ${VX.fmt.nd(c.strike)} ${c.exp||''}</span></td>
      <td class="vx-num">${VX.fmt.nd(c.delta)}</td><td class="vx-num">${VX.fmt.nd(c.dte)}</td>
      <td class="vx-num">${c.iv!=null?(c.iv).toFixed(0)+'%':'—'}</td>
      <td class="vx-num">${VX.fmt.nd(c.cost)}</td>
      <td class="vx-num">${c.spread!=null?c.spread+'%':'—'}</td>
      <td class="vx-num">${VX.fmt.nd(c.oi)}</td>
      <td class="vx-num"><b>${VX.fmt.nd(c.quality)}</b></td></tr>`:'';
    const main=avail.find(([l])=>l.startsWith('PRINCIPAL'))||avail[0];
    const others=avail.filter(x=>x!==main);
    const why=others.map(([l,c])=>{
      const m=main[1];const wins=[];
      if((c.delta||0)>(m.delta||0))wins.push('delta plus élevé (plus défensif)');
      if((c.cost||1e9)<(m.cost||1e9))wins.push('prime plus faible (plus convexe)');
      if((c.oi||0)>(m.oi||0))wins.push('OI supérieur');
      return `<li><b>${l}</b> : ${wins.length?('gagne sur '+wins.join(', ')):'ne domine sur aucune dimension clé'} — qualité globale ${VX.fmt.nd(c.quality)} vs ${VX.fmt.nd(m?m.quality:null)}.</li>`;
    }).join('');
    VX.shell.openDrawer('Comparateur de contrats'+(symWanted?' — '+symWanted:''),
      `<div class="vx-table-wrap"><table class="vx-table"><thead><tr>
        <th>Contrat</th><th class="vx-num">Δ</th><th class="vx-num">DTE</th><th class="vx-num">IV</th>
        <th class="vx-num">Prime</th><th class="vx-num">Spread</th><th class="vx-num">OI</th>
        <th class="vx-num">Qualité</th></tr></thead>
        <tbody>${avail.map(([l,c])=>row(l,c)).join('')}</tbody></table></div>
       <div class="vx-insight vx-mt3"><b>Pourquoi ${main[0]} domine</b>
         <div class="vx-mt1" style="font-size:12.5px">Le contrat principal offre le meilleur score composite
         (R:R simulé × liquidité × coût du temps). Les alternatives gagnent chacune sur UNE dimension :</div>
         <ul class="vx-mt1" style="margin:0;padding-left:18px;font-size:12.5px">${why||'<li>aucune alternative disponible</li>'}</ul></div>
       <div class="vx-help vx-mt2">Analyse uniquement — copier le contrat pour le consulter chez le broker.</div>`);
  };
  const symFilter=(PARAMS.sym||'').toUpperCase();
  const state={type:'',bucket:'',danger:'',minQ:0,minPop:0,maxDte:0,maxCost:0,exclStale:false,sym:symFilter};
  function filtered(){
    let f=board;
    if(state.sym)f=f.filter(c=>c.sym===state.sym);
    if(state.type)f=f.filter(c=>c.type===state.type);
    if(state.bucket)f=f.filter(c=>c.bucket===state.bucket);
    if(state.danger)f=f.filter(c=>c.danger===state.danger);
    if(state.minQ)f=f.filter(c=>(c.quality||0)>=state.minQ);
    if(state.minPop)f=f.filter(c=>(c.pop||0)>=state.minPop);
    if(state.maxDte)f=f.filter(c=>(c.dte||0)<=state.maxDte);
    if(state.maxCost)f=f.filter(c=>(c.cost||0)<=state.maxCost);
    if(state.exclStale)f=f.filter(c=>!c.stale);
    return f;
  }
  const dangers=[...new Set(board.map(c=>c.danger).filter(Boolean))];
  ($('op-body')||{}).innerHTML=demoBanner(scan)+`
    <div class="vx-screenbar" role="group" aria-label="Filtres options">
      ${['CALL','PUT'].map(t=>`<button class="vx-chip" data-fk="type" data-fv="${t}" aria-pressed="false"
        style="${t==='PUT'?'color:var(--vx-violet)':''}">${t}</button>`).join('')}
      ${['court','moyen','long'].map(b=>`<button class="vx-chip" data-fk="bucket" data-fv="${b}" aria-pressed="false">${b} terme</button>`).join('')}
      <select class="vx-select" data-fk="danger" style="width:auto" aria-label="Danger">
        <option value="">Tout danger</option>${dangers.map(d=>`<option>${esc(d)}</option>`).join('')}</select>
      <label class="rng">qualité ≥ <input type="range" data-fk="minQ" min="0" max="80" step="5" value="0"><b>0</b></label>
      <label class="rng">proba profit ≥ <input type="range" data-fk="minPop" min="0" max="70" step="5" value="0"><b>0%</b></label>
      <label class="rng">échéance ≤ <input type="range" data-fk="maxDte" min="0" max="400" step="20" value="0"><b>∞</b></label>
      <label class="rng">prime ≤ <input type="range" data-fk="maxCost" min="0" max="6000" step="250" value="0"><b>∞</b></label>
      <button class="vx-chip" data-ft="exclStale" aria-pressed="false">⏸ exclure hors séance</button>
      <input class="vx-input" data-fk="sym" style="width:110px;text-transform:uppercase" placeholder="Ticker" value="${esc(state.sym)}" aria-label="Filtrer par ticker">
      <button class="vx-btn vx-btn-sm vx-btn-soft" onclick="window.__opCompare&&window.__opCompare(document.querySelector('[data-fk=sym]').value.toUpperCase())">Comparer 3 contrats</button>
      <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/options">Desk options →</a>
      <span class="vx-meta vx-right" id="op-opt-count"></span>
    </div>
    <div class="vx-scr-kpis" id="op-opt-kpis"></div>
    <div class="vx-grid vx-mt4">
      <div class="vx-col-8" id="op-opt-scatter"></div>
      <div class="vx-col-4"><div class="vx-card" id="op-opt-sel-card">
        <div class="vx-card-header"><span class="vx-card-title">Contrat sélectionné</span></div>
        <div id="op-opt-sel"><div class="vx-meta">Clique un point du nuage ou une ligne de la table pour simuler le contrat.</div></div></div></div>
    </div>
    <div class="vx-grid vx-mt4">
      <div class="vx-col-6" id="op-ivdte"></div>
      <section class="vx-card vx-col-6" id="op-mix-card"><div class="vx-card-header">
        <span class="vx-card-title">Répartition du board</span>
        <span class="vx-chart-question">Terme × sens — où vit l’offre de contrats ?</span></div>
        <div id="op-mix"></div></section>
    </div>
    <div class="vx-card vx-mt4"><div class="vx-card-header"><span class="vx-card-title">Contrats du board</span>
      <span class="vx-chart-question">Cliquer une ligne simule le contrat (payoff, scénarios, décote temps).</span></div>
      <div id="op-opt-table"></div>
      <div class="vx-card-footer">${VX.updateIndicator(scan.scan_ts||scan.updated,scan.options_source||scan.source,metaMode(scan))}</div></div>
    <div class="vx-grid vx-mt4" id="op-contract" hidden>
      <div class="vx-col-6" id="op-payoff"></div>
      <div class="vx-col-6" id="op-scenarios"></div>
      <div class="vx-col-6" id="op-theta"></div>
      <div class="vx-col-6" id="op-iv"></div>
    </div>`;
  function paintKpis(f){
    const calls=f.filter(c=>c.type==='CALL').length;
    const qmax=f.length?Math.max(...f.map(c=>c.quality||0)):null;
    const pmax=f.length?Math.max(...f.map(c=>c.pop||0)):null;
    const ivs=f.map(c=>c.iv).filter(x=>x!=null).sort((a,b)=>a-b);
    const ivMed=ivs.length?ivs[Math.floor(ivs.length/2)]:null;
    const stale=f.filter(c=>c.stale).length;
    ($('op-opt-kpis')||{}).innerHTML=
      `<div class="k"><b>${f.length}</b><span>contrats</span></div>`
      +`<div class="k"><b>${calls} / ${f.length-calls}</b><span>calls / puts</span></div>`
      +`<div class="k"><b>${qmax!=null?Math.round(qmax):'—'}</b><span>meilleure qualité</span></div>`
      +`<div class="k"><b>${pmax!=null?Math.round(pmax)+' %':'—'}</b><span>meilleure proba profit</span></div>`
      +`<div class="k"><b>${ivMed!=null?Math.round(ivMed)+' %':'—'}</b><span>IV médiane</span></div>`
      +(function(){const ems=f.map(c=>c.em_pct).filter(x=>x!=null).sort((a,b)=>a-b);
        const emMed=ems.length?ems[Math.floor(ems.length/2)]:null;
        return `<div class="k"><b>${emMed!=null?'±'+VX.fmt.num(emMed,1)+' %':'—'}</b><span>mouvement attendu médian</span></div>`;})()
      +`<div class="k"><b>${stale}</b><span>hors séance (indicatif)</span></div>`;
    ($('op-opt-count')||{}).textContent=f.length+' / '+board.length+' contrats';
  }
  function paintScatter(f){
    const host=$('op-opt-scatter');if(!host)return;
    const cc=VXCharts.colors;
    const pts=f.filter(c=>c.quality!=null&&c.pop!=null).map(c=>({
      x:c.quality,y:c.pop,sym:c.sym,type:c.type,strike:c.strike,exp:c.exp,dte:c.dte,
      cost:c.cost,danger:c.danger,idx:board.indexOf(c),
      r:4+Math.min(8,Math.sqrt((c.cost||100)/220))}));
    if(!pts.length){host.innerHTML='<div class="vx-card">'+VX.states.empty('Aucun contrat avec qualité et proba dans ce filtre.')+'</div>';return;}
    const dangerCol={'Faible':cc.positive,'Modéré':cc.warning,'Élevé':cc.negative,'Extrême':'#b13a33'};
    VXCharts.card('op-opt-scatter',{
      title:'Qualité × proba de profit — où sont les bons contrats ?',
      question:'Quels contrats combinent qualité (liquidité, spread, théta) et proba de finir gagnants ?',
      conclusion:pts.filter(p=>p.x>=55&&p.y>=45).length+' contrat(s) en zone favorable (qualité ≥ 55 · proba ≥ 45 %)',
      height:320,source:scan.options_source||scan.source,timestamp:scan.scan_ts||scan.updated,mode:metaMode(scan),
      limits:'taille de point = prime engagée · couleur = danger (théta, proba, échéance)',
      explain:{shows:'Chaque point est un contrat du board, placé par sa qualité composite et sa probabilité de profit à l’échéance.',
        why:'Une prime pas chère ne vaut rien si le contrat est illiquide ou brûle trop vite — la qualité le mesure.',
        confirm:'Contrat en haut-droit avec danger Faible/Modéré.',
        invalidate:'Danger Élevé/Extrême : le théta ou l’échéance jouent contre toi.'},
      render:(cv)=>VXCharts.mount(cv,{type:'scatter',
        data:{datasets:[{data:pts,
          pointRadius:(ctx)=>ctx.raw?ctx.raw.r:4,pointHoverRadius:(ctx)=>ctx.raw?ctx.raw.r+3:8,
          pointBackgroundColor:(ctx)=>dangerCol[ctx.raw&&ctx.raw.danger]||cc.neutral,
          pointBorderColor:'rgba(255,255,255,.2)',pointBorderWidth:1}]},
        options:{scales:{
          x:{title:{display:true,text:'Qualité du contrat →'},min:0,max:100,grid:{color:'rgba(255,255,255,.05)'}},
          y:{title:{display:true,text:'Proba de profit % ↑'},min:0,max:100,grid:{color:'rgba(255,255,255,.05)'}}},
          plugins:{tooltip:{callbacks:{label:(ctx)=>`${ctx.raw.sym} ${ctx.raw.type} ${ctx.raw.strike} (${ctx.raw.dte} j) · qualité ${Math.round(ctx.raw.x)} · proba ${Math.round(ctx.raw.y)} % · danger ${ctx.raw.danger||'n/d'}`}}},
          onClick:(evt,els,chart)=>{const p=chart.getElementsAtEventForMode(evt,'nearest',{intersect:true},true);
            if(p.length){const d=chart.data.datasets[0].data[p[0].index];openContract(board[d.idx]);}}}})});
  }
  /* Carte CONTRAT (options en cartes, pas en liste) — strike/échéance/DTE en avant,
     grecs & probas en chips ; clic → openContract (prix, évolution, payoff, scénarios). */
  function optCard(c){
    const idx=board.indexOf(c);
    const typeCol=c.type==='PUT'?'var(--vx-violet)':'var(--vx-positive)';
    const dgcol={'Faible':'var(--vx-positive)','Modéré':'var(--vx-warning)','Élevé':'var(--vx-negative)','Extrême':'var(--vx-negative)'}[c.danger]||'var(--vx-text-dim)';
    return `<div class="vx-card vx-opp-card" data-ct="${idx}" tabindex="0" role="button" aria-label="Simuler ${esc(c.sym)} ${VX.fmt.nd(c.strike)}">
      <div class="vx-flex" style="justify-content:space-between;gap:6px;align-items:flex-start">
        <div class="vx-flex vx-wrap" style="gap:.35rem;align-items:center"><span class="vx-ticker" style="font-size:15px">${c.sym}</span>
          <span class="vx-badge" style="color:${typeCol}">${c.type}</span><span class="vx-badge">${esc(c.bucket||'')}</span></div>
        <span class="vx-badge" style="color:${dgcol}" title="risque">${esc(c.danger||'—')}</span></div>
      <div class="vx-mono vx-mt1" style="font-size:16px;font-weight:700">Strike ${VX.fmt.nd(c.strike)}<span class="vx-meta" style="font-weight:400"> · éch. ${esc(String(c.exp||'').slice(0,10))}${c.dte!=null?' ('+c.dte+' j)':''}</span></div>
      <div class="vx-flex vx-wrap vx-mt1" style="gap:.3rem">
        ${c.cost!=null?`<span class="vx-badge">prime ${VX.fmt.nd(c.cost)} $</span>`:''}
        ${c.delta!=null?`<span class="vx-badge">Δ ${VX.fmt.nd(c.delta)}</span>`:''}
        ${c.iv!=null?`<span class="vx-badge">IV ${Math.round(c.iv)}%</span>`:''}
        ${c.pop!=null?`<span class="vx-badge" style="color:var(--vx-positive)">PoP ${Math.round(c.pop)}%</span>`:''}
        ${c.p_tgt!=null?`<span class="vx-badge">P(obj) ${Math.round(c.p_tgt)}%</span>`:''}
        ${c.swing_ret!=null?`<span class="vx-badge" style="color:${c.swing_ret>0?'var(--vx-positive)':'var(--vx-text-dim)'}" title="rendement si objectif atteint">rend. ${c.swing_ret>=0?'+':''}${VX.fmt.num(c.swing_ret,0)}%${c.swing_ok?' ✓':''}</span>`:''}
        ${c.quality!=null?`<span class="vx-badge">qualité ${Math.round(c.quality)}</span>`:''}
      </div>
      <div class="vx-meta vx-mt2">Clic → prix actuel du sous-jacent, évolution, payoff & scénarios</div></div>`;
  }
  function paintTable(f){
    const sorted=f.slice().sort((a,b)=>(b.quality||0)-(a.quality||0));
    ($('op-opt-table')||{}).innerHTML=sorted.length
      ?'<div class="vx-opp-grid">'+sorted.slice(0,48).map(optCard).join('')+'</div>'
      :VX.states.empty(state.sym?'Aucun contrat pour '+state.sym+' dans ce filtre.':'Board options vide — le sélecteur ne force jamais une idée.',
        '<a class="vx-btn vx-btn-sm" href="/system?view=data">Vérifier les données</a>');
    document.querySelectorAll('#op-opt-table [data-ct]').forEach(cd=>{
      const open=(e)=>{if(e.target.closest('[data-open-analysis],[data-entity-menu]'))return;openContract(board[+cd.dataset.ct]);};
      cd.addEventListener('click',open);
      cd.addEventListener('keydown',(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(e);}});});
  }
  /* IV selon l'échéance : structure de vol du board filtré */
  function paintIvDte(f){
    const host=$('op-ivdte');if(!host)return;
    const cc=VXCharts.colors;
    const pts=f.filter(c=>c.iv!=null&&c.dte!=null).map(c=>({x:c.dte,y:c.iv,sym:c.sym,type:c.type,strike:c.strike,idx:board.indexOf(c)}));
    if(!pts.length){host.innerHTML='<div class="vx-card">'+VX.states.empty('Aucun contrat avec IV dans ce filtre.')+'</div>';return;}
    VXCharts.card('op-ivdte',{
      title:'IV selon l’échéance',question:'Payes-tu la volatilité plus cher sur le court ou le long terme ?',
      conclusion:(function(){const sh=pts.filter(p2=>p2.x<=60),lg=pts.filter(p2=>p2.x>150);
        const med=(a)=>{if(!a.length)return null;const v=a.map(x=>x.y).sort((m,n)=>m-n);return v[Math.floor(v.length/2)];};
        const ms=med(sh),ml=med(lg);
        return (ms!=null&&ml!=null)?('IV médiane : '+Math.round(ms)+' % court terme vs '+Math.round(ml)+' % long terme'):'structure partielle';})(),
      height:240,source:scan.options_source||scan.source,timestamp:scan.scan_ts||scan.updated,mode:metaMode(scan),
      explain:{shows:'Chaque contrat filtré placé par son échéance (jours) et son IV.',
        why:'Une IV courte gonflée signale un événement price — acheter du temps peut coûter moins cher en annualisé.',
        confirm:'IV courte < IV longue (structure normale).',invalidate:'Inversion : le court terme se paie plus cher.'},
      render:(cv)=>VXCharts.mount(cv,{type:'scatter',
        data:{datasets:[{data:pts,pointRadius:4,pointHoverRadius:7,
          pointBackgroundColor:(ctx)=>ctx.raw&&ctx.raw.type==='PUT'?cc.violet:cc.positive,
          pointBorderColor:'rgba(255,255,255,.18)',pointBorderWidth:1}]},
        options:{scales:{x:{title:{display:true,text:'Échéance (jours) →'},grid:{color:'rgba(255,255,255,.05)'}},
          y:{title:{display:true,text:'IV % ↑'},grid:{color:'rgba(255,255,255,.05)'}}},
          plugins:{tooltip:{callbacks:{label:(ctx)=>`${ctx.raw.sym} ${ctx.raw.type} ${ctx.raw.strike} · ${ctx.raw.x} j · IV ${Math.round(ctx.raw.y)} %`}}},
          onClick:(evt,els,chart)=>{const p2=chart.getElementsAtEventForMode(evt,'nearest',{intersect:true},true);
            if(p2.length){openContract(board[chart.data.datasets[0].data[p2[0].index].idx]);}}}})});
  }
  /* Répartition terme × type : barres empilées HTML */
  function paintMix(f){
    const el=$('op-mix');if(!el)return;
    const B=['court','moyen','long'];
    const cnt={};f.forEach(c=>{const k=(c.bucket||'?')+'|'+c.type;cnt[k]=(cnt[k]||0)+1;});
    const tot=f.length||1;
    if(!f.length){el.innerHTML=VX.states.empty('Aucun contrat.');return;}
    el.innerHTML=B.map(b=>{
      const ca=cnt[b+'|CALL']||0,pu=cnt[b+'|PUT']||0,t=ca+pu;
      if(!t)return '';
      return `<div class="vx-mt2"><div class="vx-flex" style="justify-content:space-between;font-size:11.5px">
          <b>${b} terme</b><span class="vx-meta">${t} contrat(s) · ${Math.round(t/tot*100)} %</span></div>
        <div style="display:flex;height:14px;border-radius:7px;overflow:hidden;background:var(--vx-surface-0);margin-top:4px"
          role="img" aria-label="${b} : ${ca} calls, ${pu} puts">
          ${ca?`<i style="width:${ca/t*100}%;background:var(--vx-positive)" title="${ca} CALL"></i>`:''}
          ${pu?`<i style="width:${pu/t*100}%;background:var(--vx-violet)" title="${pu} PUT"></i>`:''}</div></div>`;
    }).join('')
    +'<div class="vx-stackbar-legend vx-mt2"><span><i style="background:var(--vx-positive)"></i>CALL</span><span><i style="background:var(--vx-violet)"></i>PUT</span></div>';
  }
  function applyAll(){const f=filtered();paintKpis(f);paintScatter(f);paintIvDte(f);paintMix(f);paintTable(f);}
  document.querySelectorAll('.vx-screenbar [data-fk="type"],.vx-screenbar [data-fk="bucket"]').forEach(c=>c.addEventListener('click',()=>{
    const k=c.dataset.fk;state[k]=state[k]===c.dataset.fv?'':c.dataset.fv;
    document.querySelectorAll(`.vx-screenbar [data-fk="${k}"]`).forEach(x=>
      x.setAttribute('aria-pressed',String(x.dataset.fv===state[k])));applyAll();}));
  document.querySelector('select[data-fk="danger"]').addEventListener('change',function(){state.danger=this.value;applyAll();});
  const applyDebounced2=debounce(applyAll,120);
  document.querySelectorAll('.vx-screenbar input[type=range]').forEach(r=>r.addEventListener('input',function(){
    state[this.dataset.fk]=+this.value;
    const b=this.closest('label').querySelector('b');
    if(this.dataset.fk==='maxDte')b.textContent=this.value>0?(this.value+' j'):'∞';
    else if(this.dataset.fk==='maxCost')b.textContent=this.value>0?('$'+this.value):'∞';
    else b.textContent=this.value+(this.dataset.fk==='minPop'?'%':'');
    applyDebounced2();}));
  document.querySelectorAll('.vx-screenbar [data-ft]').forEach(c=>c.addEventListener('click',()=>{
    state[c.dataset.ft]=!state[c.dataset.ft];
    c.setAttribute('aria-pressed',String(state[c.dataset.ft]));applyAll();}));
  document.querySelector('input[data-fk="sym"]').addEventListener('input',function(){state.sym=this.value.toUpperCase();applyDebounced2();});
  async function openContract(c){
    if(!c)return;
    /* Les contrats du board ne portent pas toujours le spot : on le prend du
       scan (prix réel du sous-jacent) — sans spot, payoff vide honnête. */
    const spot=(c.spot!=null&&isFinite(c.spot))?c.spot:(((scan.detail||{})[c.sym]||{}).price);
    ($('op-opt-sel')||{}).innerHTML=
      `<div class="vx-flex"><span class="vx-ticker" style="font-size:15px">${esc(c.sym)}</span>
        <span class="vx-badge" style="color:${c.type==='PUT'?'var(--vx-violet)':'var(--vx-positive)'}">${c.type}</span>
        <span class="vx-badge vx-right">${esc(c.bucket||'')}</span></div>
       <div class="vx-kv vx-mt2"><span class="k">Strike · échéance</span><span class="v vx-mono">${VX.fmt.nd(c.strike)} · ${esc(String(c.exp||'').slice(0,10))}</span></div>
       <div class="vx-kv"><span class="k">Prime</span><span class="v vx-mono">${VX.fmt.nd(c.cost)} $</span></div>
       <div class="vx-kv"><span class="k">Proba profit</span><span class="v vx-mono">${c.pop!=null?Math.round(c.pop)+' %':'n/d'}</span></div>
       ${c.p_itm!=null?`<div class="vx-kv"><span class="k">Proba dans la monnaie</span><span class="v vx-mono">${Math.round(c.p_itm)} %</span></div>`:''}
       ${c.p_tgt!=null?`<div class="vx-kv"><span class="k">Proba d’atteindre l’objectif</span><span class="v vx-mono">${Math.round(c.p_tgt)} %</span></div>`:''}
       ${c.em_pct!=null?`<div class="vx-kv"><span class="k">Mouvement attendu</span><span class="v vx-mono">± ${VX.fmt.num(c.em_pct,1)} %</span></div>`:''}
       ${c.swing_ret!=null?`<div class="vx-kv"><span class="k">Rendement si objectif</span><span class="v vx-mono ${c.swing_ret>0?'vx-pos':''}">+${VX.fmt.num(c.swing_ret,0)} %${c.swing_ok?' · aligné plan':''}</span></div>`:''}
       <div class="vx-kv"><span class="k">Qualité</span><span class="v vx-mono">${VX.fmt.nd(c.quality)}</span></div>
       <div class="vx-kv"><span class="k">Danger</span><span class="v">${esc(c.danger||'n/d')}</span></div>
       <div class="vx-kv"><span class="k">Décote temps</span><span class="v vx-mono">${c.theta_burn!=null?VX.fmt.num(c.theta_burn,2)+' % / jour':'n/d'}</span></div>
       ${c.quality_parts?`<div class="vx-metric-k vx-mt2" style="display:block">D’où vient la qualité ${VX.fmt.nd(c.quality)}</div>
         ${Object.entries(c.quality_parts).map(([k2,v2])=>{
           const got=Array.isArray(v2)?v2[0]:v2;const max2=Array.isArray(v2)?v2[1]:100;
           const pc=max2?Math.round(got/max2*100):0;
           return `<div class="vx-flex" style="gap:7px;align-items:center;padding:1.5px 0">
             <span class="vx-meta" style="flex:0 0 76px">${esc(k2)}</span>
             <span style="flex:1;height:5px;border-radius:99px;background:var(--vx-surface-0);overflow:hidden">
               <i style="display:block;height:100%;width:${Math.max(3,Math.min(100,pc))}%;background:${pc>=70?'var(--vx-positive)':pc>=40?'var(--vx-warning)':'var(--vx-negative)'};border-radius:99px"></i></span>
             <b class="vx-mono" style="font-size:10px;flex:0 0 40px;text-align:right">${got}/${max2}</b></div>`;}).join('')}`:''}
       <div class="vx-flex vx-wrap vx-mt2" style="gap:.3rem">
         <a class="vx-btn vx-btn-sm vx-btn-primary" href="/options/dossier/${esc(c.sym)}">Dossier options</a>
         <button class="vx-btn vx-btn-sm" data-open-analysis="${esc(c.sym)}">Fiche action</button></div>`;
    $('op-contract').hidden=false;
    $('op-contract').open=true;
    $('op-contract').scrollIntoView({behavior:'smooth',block:'nearest'});
    VXCharts.payoffCard('op-payoff',{title:`${c.sym} ${c.strike} ${c.type} ${c.exp}`,unit:'$ par contrat',
      question:'Que rapporte/coûte ce contrat à l’échéance ?',
      conclusion:`Breakeven ${VX.fmt.nd(c.be)} · prime ${VX.fmt.nd(c.cost)}`,
      spot:spot,strike:c.strike,premium:c.cost,right:c.type==='PUT'?'P':'C',breakeven:c.be,height:210,
      expectedMovePct:c.em_pct,target:c.tgt,
      source:'board options',timestamp:null,mode:'delayed',
      conclusion:(c.be!=null&&spot&&c.em_pct?('Breakeven '+VX.fmt.nd(c.be)+' · '+(Math.abs(c.be-spot)/spot*100<=c.em_pct?'DANS':'HORS')+' le mouvement attendu (±'+VX.fmt.num(c.em_pct,1)+' %)'):('Breakeven '+VX.fmt.nd(c.be))),
      explain:{shows:'Le P&L du contrat à l’échéance selon le prix du sous-jacent (arithmétique du contrat).',
        why:'Visualiser breakeven et asymétrie avant d’engager la prime.',
        confirm:'Sous-jacent au-delà du breakeven avant l’échéance.',
        invalidate:'Stop sous-jacent touché — on ne « garde pas en espérant ».'}});
    try{
      const q=new URLSearchParams({sym:c.sym,strike:c.strike,dte:c.dte,mid:c.cost,
        iv:c.iv||'',right:c.type==='PUT'?'P':'C',exp:c.exp,spot:spot||''});
      const s=await VX.fetch('/api/options/simulate?'+q.toString(),{ttl:120000});
      VXCharts.scenarioMatrix('op-scenarios',s.sim,{title:'Scénarios (moteur)',
        question:'Que vaut le contrat selon le spot et le temps ?',
        conclusion:`R:R simulé ${VX.fmt.nd(s.sim.reward_risk)} · perte planifiée ${VX.fmt.nd(s.sim.worst_planned_loss_pct)} %`,
        source:'scenario_pricer',timestamp:(s&&s.ts)||null,mode:'delayed'});
      VXCharts.thetaCard('op-theta',s.sim,{title:'Décomposition temps',unit:'$ par jour',
        question:'Combien coûte chaque jour d’attente ?',
        conclusion:'Réévaluer après 5-8 séances sans mouvement',
        height:190,source:'scenario_pricer',timestamp:(s&&s.ts)||null,mode:'delayed'});
      VXCharts.ivSensitivityCard('op-iv',s.sim,{title:'Sensibilité IV',unit:'$',
        question:'Que se passe-t-il si la volatilité implicite bouge ?',
        conclusion:'IV -20 % à +20 % au scénario BASE',height:190,
        source:'scenario_pricer',timestamp:(s&&s.ts)||null,mode:'delayed'});
    }catch(e){
      ($('op-scenarios')||{}).innerHTML='<div class="vx-card">'+VX.states.error('Simulation moteur indisponible : '+e.message)+'</div>';
      ($('op-theta')||{}).innerHTML='';($('op-iv')||{}).innerHTML='';
    }
  }
  applyAll();
}

/* ═════════ PORTEFEUILLE : mes positions × le moteur + candidats ═════════ */
async function renderPortfolio(){
  const scan=await VX.fetch('/scan',{ttl:120000});
  paintContext(scan);
  const rows=(scan.rows||[]);
  const byId={};rows.forEach(r=>{byId[r.symbol]=r;});
  const pos=(window.VXEntities?VXEntities.positions():[])||[];
  if(!pos.length){
    ($('op-body')||{}).innerHTML=VX.states.empty('Aucune position déclarée — le comparateur portefeuille × moteur s’active dès ta première position.',
      '<button class="vx-btn vx-btn-sm vx-btn-primary" onclick="VXEntities.openAddModal(\'\',\'position\')">Déclarer une position</button>');
    return;
  }
  const held=pos.map(p=>{
    const r=byId[String(p.sym).toUpperCase()]||null;
    const status=!r?'hors scan':(r.verdict==='AVOID'||r.verdict==='ÉVITER')?'à revoir'
      :(r.verdict==='BUY'||r.verdict==='ACHETER')?'confirmée':'neutre';
    return {p,r,status};
  });
  const toReview=held.filter(h=>h.status==='à revoir');
  const secOfHeld=[...new Set(held.map(h=>h.r&&h.r.sector).filter(Boolean))];
  /* Candidats de remplacement : meilleurs titres NON détenus, priorité aux secteurs du portefeuille */
  const heldSyms=new Set(pos.map(p=>String(p.sym).toUpperCase()));
  const candidates=rows.filter(r=>!heldSyms.has(r.symbol)&&(r.verdict==='BUY'||r.verdict==='ACHETER'))
    .slice().sort((a,b)=>(secOfHeld.includes(b.sector)?1:0)-(secOfHeld.includes(a.sector)?1:0)||(b.score||0)-(a.score||0))
    .slice(0,6);
  const statusBadge={confirmée:'<span class="vx-badge" style="color:var(--vx-positive)">CONFIRMÉE par le moteur</span>',
    'à revoir':'<span class="vx-badge" style="color:var(--vx-negative)">À REVOIR — verdict ÉVITER</span>',
    neutre:'<span class="vx-badge" style="color:var(--vx-warning)">NEUTRE — surveiller</span>',
    'hors scan':'<span class="vx-badge">hors de l’univers scanné</span>'};
  ($('op-body')||{}).innerHTML=demoBanner(scan)+`
    <div class="vx-scr-kpis">
      <div class="k"><b>${pos.length}</b><span>positions déclarées</span></div>
      <div class="k"><b style="color:var(--vx-positive)">${held.filter(h=>h.status==='confirmée').length}</b><span>confirmées par le moteur</span></div>
      <div class="k"><b style="color:var(--vx-negative)">${toReview.length}</b><span>à revoir (verdict ÉVITER)</span></div>
      <div class="k"><b>${candidates.length}</b><span>candidats d’achat non détenus</span></div>
    </div>
    ${toReview.length?`<div class="vx-insight vx-mt3" data-tone="risk"><b>⚠ ${toReview.length} position(s) contredite(s) par le moteur :</b>
      ${toReview.map(h=>`<button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(h.p.sym)}">${esc(h.p.sym)}</button>`).join(' ')}
      — vérifier le dossier avant de décider (jamais de vente automatique).</div>`:''}
    <div class="vx-grid vx-mt3">
      <section class="vx-card vx-col-6" id="op-pf-risk-card"><div class="vx-card-header">
        <span class="vx-card-title">Risque du panier</span>
        <span class="vx-chart-question">Mon portefeuille est-il réellement diversifié ?</span></div>
        <div id="op-pf-risk"><div class="vx-skeleton" style="height:60px"></div></div></section>
      <section class="vx-card vx-col-6" id="op-pf-sect-card"><div class="vx-card-header">
        <span class="vx-card-title">Secteurs du portefeuille</span></div>
        <div id="op-pf-sect"></div></section>
    </div>
    <div class="vx-card vx-mt4"><div class="vx-card-header"><span class="vx-card-title">Mes positions × le moteur</span>
      <span class="vx-chart-question">Le moteur confirme-t-il encore chacune de mes lignes ?</span></div>
      <div id="op-pf-cards"></div>
      <div class="vx-card-footer">${VX.updateIndicator(scan.scan_ts||scan.updated,scan.source,metaMode(scan))}
        · verdicts du moteur — analyse uniquement, aucune vente automatique</div></div>
    <div id="op-pf-cands" class="vx-mt4"></div>`;
  /* Positions en CARTES design (liseré au statut, jauge de score, mini-courbe) */
  const statusCol={confirmée:'var(--vx-positive)','à revoir':'var(--vx-negative)',
    neutre:'var(--vx-warning)','hors scan':'var(--vx-text-dim)'};
  ($('op-pf-cards')||{}).innerHTML='<div class="vx-movergrid" style="grid-template-columns:repeat(auto-fill,minmax(250px,1fr))">'
    +held.map(h=>{const r=h.r||{};
      const ser=(scan.detail||{})[h.p.sym]&&scan.detail[h.p.sym].series;
      const gauge=(window.VXCharts&&VXCharts.scoreGaugeSVG&&r.score!=null)
        ?VXCharts.scoreGaugeSVG(r.score,{size:64,stroke:6,label:'score'}):'';
      return `<div class="vx-mover" role="group" style="cursor:default;border-left:3px solid ${statusCol[h.status]||'var(--vx-border)'}">
      <div class="vx-flex" style="justify-content:space-between;gap:6px;align-items:flex-start">
        <div style="min-width:0">
          <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" style="font-size:16px;padding-left:0" data-open-analysis="${esc(h.p.sym)}">${esc(h.p.sym)}</button>
          <span class="vx-badge" ${h.p.type!=='STK'?'style="color:var(--vx-violet)"':''}>${esc(h.p.type||'STK')}${h.p.strike?' '+esc(h.p.strike):''}</span>
        </div>
        <div style="flex:0 0 auto">${gauge}</div></div>
      <div class="vx-mt1">${statusBadge[h.status]||''}</div>
      <div class="vx-flex vx-wrap vx-mt1" style="gap:.3rem">
        ${r.vx_pwin!=null?`<span class="vx-badge" style="color:var(--vx-positive)">proba ${Math.round(r.vx_pwin*100)} %</span>`:''}
        ${r.change!=null?`<span class="vx-badge ${r.change>0?'vx-pos':'vx-neg'}">${VX.fmt.pct(r.change,1)} auj.</span>`:''}
        ${r.pos52!=null?`<span class="vx-badge" title="position dans la fourchette 52 semaines">52 sem. ${Math.round(r.pos52)} %</span>`:''}</div>
      ${sparkMini(ser&&ser.close)}
      ${pbText(r)?`<div class="vx-meta vx-mt1" style="white-space:normal;line-height:1.4">${esc(pbText(r))}</div>`:''}
      <div class="vx-flex vx-mt2" style="gap:.3rem">
        <button class="vx-btn vx-btn-sm vx-btn-primary" data-open-analysis="${esc(h.p.sym)}">Analyser</button>
        <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/options/dossier/${esc(h.p.sym)}">Options</a>
        <button class="vx-btn vx-btn-icon vx-btn-ghost" data-entity-menu="${esc(h.p.sym)}" aria-label="Actions">⋯</button></div>
    </div>`;}).join('')+'</div>';
  /* Risque du panier — chiffres RÉELS du moteur de risque (/api/command.risk) */
  try{
    const cmd=await VX.fetch('/api/command',{ttl:60000});
    const rk=(cmd&&cmd.risk)||null;
    const el=$('op-pf-risk');
    if(rk&&el){
      const kv2=(k,v,cls)=>`<div class="vx-kv"><span class="k">${k}</span><span class="v vx-mono ${cls||''}">${v}</span></div>`;
      el.innerHTML=
        `<div id="op-pf-divgauge" class="vx-mb2"></div>`
        +kv2('Corrélation moyenne',rk.avg_corr!=null?VX.fmt.num(rk.avg_corr,2):'n/d',rk.avg_corr>0.65?'vx-neg':'')
        +kv2('Pire corrélation',rk.max_corr!=null?VX.fmt.num(rk.max_corr,2):'n/d')
        +kv2('Secteur le plus lourd',(rk.max_sector_name?esc(rk.max_sector_name)+' · ':'')+(rk.max_sector!=null?Math.round(rk.max_sector)+' %':'n/d'),
          rk.max_sector>((rk.limits&&rk.limits.max_sector)||40)?'vx-neg':'')
        +kv2('Nouveau risque',rk.no_new_risk?'BLOQUÉ':'autorisé',rk.no_new_risk?'vx-neg':'vx-pos')
        +((rk.flags&&rk.flags.length)?`<div class="vx-insight vx-mt2" data-tone="risk">${rk.flags.map(f2=>esc(f2)).join('<br>')}</div>`:'')
        +`<div class="vx-card-footer"><span class="vx-meta">moteur de risque du panier — limites : ${(rk.limits&&rk.limits.max_pos)||'—'} positions max · ${(rk.limits&&rk.limits.max_sector)||'—'} % max par secteur</span></div>`;
      if(window.VXCharts&&VXCharts.gauge&&rk.diversification!=null){
        VXCharts.gauge('op-pf-divgauge',{value:rk.diversification,min:0,max:100,unit:' %',label:'Diversification',
          reading:rk.diversification>=70?'Panier réellement diversifié':'Concentration à surveiller',
          bands:[{to:40,color:VXCharts.colors.negative},{to:70,color:VXCharts.colors.warning},{to:100,color:VXCharts.colors.positive}]});
      }
    }else if(el){el.innerHTML=VX.states.empty('Moteur de risque indisponible pour ce panier.');}
  }catch(e){const el=$('op-pf-risk');if(el)el.innerHTML=VX.states.empty('Moteur de risque indisponible.');}
  /* Donut secteurs du portefeuille (positions réelles × secteur du scan) */
  (function(){
    const cnt={};held.forEach(h=>{const sec2=(h.r&&h.r.sector)||'Hors scan';cnt[sec2]=(cnt[sec2]||0)+1;});
    const ks=Object.keys(cnt);
    if(ks.length&&window.VXCharts&&VXCharts.donutCard){
      VXCharts.donutCard('op-pf-sect-card',{title:'Secteurs du portefeuille',unit:'% du portefeuille',
        question:'Suis-je concentré sur un seul thème ?',
        labels:ks,values:ks.map(k=>cnt[k]),height:200,
        source:'positions déclarées × scan',timestamp:null,mode:'delayed'});
    }else{($('op-pf-sect')||{}).innerHTML=VX.states.empty('Aucun secteur identifiable.');}
  })();
  const cd=$('op-pf-cands');
  cd.innerHTML='<div class="vx-card-header" style="padding:0 0 8px"><span class="vx-card-title">Candidats non détenus — signaux d’achat du moteur</span>'
    +'<span class="vx-chart-question">Qui mériterait une place, priorité aux secteurs déjà en portefeuille ?</span></div>'
    +(candidates.length?'<div class="vx-opp-grid">'+candidates.map(r=>`
      <div class="vx-card" style="border-left:3px solid var(--vx-positive);min-width:0">
        <div class="vx-flex"><button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" style="font-size:15px;padding-left:0" data-open-analysis="${r.symbol}">${r.symbol}</button>
          <span class="vx-badge vx-badge-decision vx-right" data-decision="${esc(r.verdict)}">${esc(VERD_FR[r.verdict]||r.verdict)}</span></div>
        <div class="vx-flex vx-wrap vx-mt1" style="gap:.3rem">
          <span class="vx-badge">score ${VX.fmt.nd(r.score)}</span>
          ${r.vx_pwin!=null?`<span class="vx-badge" style="color:var(--vx-positive)">proba ${Math.round(r.vx_pwin*100)} %</span>`:''}
          ${r.sector?`<span class="vx-badge">${esc(r.sector)}${secOfHeld.includes(r.sector)?' · déjà en portefeuille':''}</span>`:''}</div>
        ${pbText(r)?`<div class="vx-meta vx-mt1" style="white-space:normal">${esc(pbText(r))}</div>`:''}
        <div class="vx-flex vx-mt2" style="gap:.3rem">
          <button class="vx-btn vx-btn-sm vx-btn-primary" data-open-analysis="${r.symbol}">Analyser</button>
          <button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal('${r.symbol}','follow')">Suivre</button></div>
      </div>`).join('')+'</div>'
    :VX.states.empty('Aucun candidat d’achat non détenu dans le scan courant.'));
}

/* ═════════ ANOMALIES ═════════ */
async function renderAnomalies(){
  const scan=await VX.fetch('/scan',{ttl:120000});
  paintContext(scan);
  const all=(scan.rows||[]).filter(r=>(r.anomalies||[]).length);
  let lvl='';let q='';
  ($('op-body')||{}).innerHTML=demoBanner(scan)+`
    <div class="vx-screenbar">
      ${['ALERTE','ACTIF','CALME'].map(l=>`<button class="vx-chip" data-lvl="${l}" aria-pressed="false"
        style="${l==='ALERTE'?'color:var(--vx-negative)':l==='ACTIF'?'color:var(--vx-warning)':''}">${l==='ALERTE'?'🔴':l==='ACTIF'?'🟠':'⚪'} ${l}</button>`).join('')}
      <input class="vx-input" id="op-anom-q" style="width:110px;text-transform:uppercase" placeholder="Ticker" aria-label="Filtrer les anomalies par ticker">
      <button class="vx-chip" data-ag="Données">Qualité des données</button>
      <span class="vx-meta vx-right" id="op-anom-count"></span>
    </div>
    <div class="vx-scr-kpis" id="op-anom-kpis"></div>
    <div class="vx-mt4" id="op-anom-types"></div>
    <div id="op-anom" class="vx-mt4"></div>`;
  function filtered(){
    let f=all;
    if(lvl)f=f.filter(r=>String(r.anomaly_lvl||'').toUpperCase()===lvl);
    if(q)f=f.filter(r=>r.symbol.includes(q));
    return f.slice().sort((a,b)=>(b.anomaly_score||0)-(a.anomaly_score||0));
  }
  function paint(){
    const f=filtered();
    /* KPI par niveau (sur TOUT le scan, pas seulement le filtre) */
    const c={ALERTE:0,ACTIF:0,CALME:0};all.forEach(r=>{const l=String(r.anomaly_lvl||'').toUpperCase();if(c[l]!=null)c[l]++;});
    ($('op-anom-kpis')||{}).innerHTML=
      `<div class="k"><b>${all.length}</b><span>titres avec anomalies</span></div>`
      +`<div class="k"><b style="color:var(--vx-negative)">${c.ALERTE}</b><span>en alerte</span></div>`
      +`<div class="k"><b style="color:var(--vx-warning)">${c.ACTIF}</b><span>actifs</span></div>`
      +`<div class="k"><b>${c.CALME}</b><span>calmes</span></div>`;
    ($('op-anom-count')||{}).textContent=f.length+' / '+all.length;
    /* Top types d'anomalies (compte par libellé réel) */
    const types={};f.forEach(r=>(r.anomalies||[]).forEach(a=>{
      const l=(typeof a==='string')?a:(a.lbl||a.k||'');if(l)types[l]=(types[l]||0)+1;}));
    const topT=Object.entries(types).sort((a,b)=>b[1]-a[1]).slice(0,8);
    ($('op-anom-types')||{}).innerHTML=topT.length?
      '<div class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Anomalies les plus fréquentes</span>'
      +'<span class="vx-chart-question">Quel comportement inhabituel domine la séance ?</span></div>'
      +topT.map(([l,n])=>{const w=Math.round(n/topT[0][1]*100);
        return `<div class="vx-flex" style="gap:8px;align-items:center;padding:3px 0">
          <span class="vx-meta" style="flex:0 0 46%;white-space:normal">${esc(l)}</span>
          <span style="flex:1;height:7px;border-radius:99px;background:var(--vx-surface-0);overflow:hidden">
            <i style="display:block;height:100%;width:${Math.max(4,w)}%;background:var(--vx-brand);border-radius:99px"></i></span>
          <b class="vx-mono" style="flex:0 0 26px;text-align:right">${n}</b></div>`;}).join('')+'</div>':'';
    ($('op-anom')||{}).innerHTML=f.length?`<div class="vx-table-wrap vx-table-cards"><table class="vx-table"><thead><tr>
      <th>Titre</th><th>Niveau</th><th>Anomalies</th><th class="vx-num">Intensité</th><th class="vx-num">Score</th><th></th></tr></thead><tbody>
      ${f.slice(0,60).map(r=>`<tr data-clickable data-open-analysis="${r.symbol}">
        <td data-label="Titre"><span class="vx-ticker">${r.symbol}</span></td>
        <td data-label="Niveau"><span class="vx-badge" style="color:${r.anomaly_lvl==='ALERTE'?'var(--vx-negative)':r.anomaly_lvl==='ACTIF'?'var(--vx-warning)':'var(--vx-text-dim)'}">${esc(r.anomaly_lvl||'—')}</span></td>
        <td data-label="Anomalies">${(r.anomalies||[]).slice(0,3).map(a=>`<span class="vx-badge" title="${esc(typeof a==='object'?(a.k||''):'')}">${esc(typeof a==='string'?a:(a.lbl||a.k||''))}</span>`).join(' ')}</td>
        ${heatCell(r.anomaly_score,{label:'Intensité',good:55,mid:25})}
        ${heatCell(r.score,{label:'Score',good:72,mid:56})}
        <td>${rowActions(r.symbol)}</td></tr>`).join('')}</tbody></table></div>`
      :VX.states.empty('Aucune anomalie ne correspond à ce filtre.');
  }
  document.querySelectorAll('[data-lvl]').forEach(b=>b.addEventListener('click',()=>{
    lvl=lvl===b.dataset.lvl?'':b.dataset.lvl;
    document.querySelectorAll('[data-lvl]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.lvl===lvl)));
    paint();}));
  document.getElementById('op-anom-q').addEventListener('input',function(){q=this.value.toUpperCase();paint();});
  document.querySelector('[data-ag="Données"]').addEventListener('click',()=>{
    VX.fetch('/api/data-quality',{ttl:60000}).then(dq=>{
      VX.shell.openDrawer('Qualité des données',`${Object.entries(dq.by_quality||{}).map(([k,v])=>
        `<div class="vx-kv"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('')}
        <div class="vx-meta vx-mt2">${esc(dq.note||'')}</div>`);
    }).catch(()=>VX.toast('Qualité de données indisponible','error'));});
  paint();
}

/* ═════════ CALENDRIER ═════════ */
async function renderCalendar(){
  try{
    /* Cette vue lit /cal-feed ; le scan n'est demande que pour la barre de
       contexte, afin qu'elle ne soit pas la seule sous-vue sans provenance. */
    VX.fetch('/scan',{ttl:120000}).then(paintContext).catch(()=>{});
    const cal=await VX.fetch('/cal-feed',{ttl:300000});
    const positions=(window.VXEntities?window.VXEntities.positions():[]).map(p=>String(p.sym).toUpperCase());
    let cat='',mine=false,horizon=0;
    ($('op-body')||{}).innerHTML=`
      <div class="vx-screenbar">
        ${[['','Tout'],['macro','Économie'],['earnings','Résultats']].map(([v,l])=>
          `<button class="vx-chip" data-cat="${v}" aria-pressed="${v===''}">${l}</button>`).join('')}
        ${[[0,'Tout l’horizon'],[7,'7 jours'],[14,'14 jours'],[30,'30 jours']].map(([v,l])=>
          `<button class="vx-chip" data-hz="${v}" aria-pressed="${v===0}">${l}</button>`).join('')}
        <button class="vx-chip" id="op-cal-mine" aria-pressed="false">💼 mes positions seulement</button>
        <span class="vx-meta vx-right" id="op-cal-count"></span>
      </div>
      <div id="op-cal" class="vx-mt3"></div>`;
    function paint(){
      const items=[...(cal.macro||[]).map(m=>({when:m.date,dte:m.dte,cat:'macro',kind:m.kind||'Économie',
          label:esc(m.label)+(m.note?' — '+esc(m.note):'')+(m.approx?' (approx.)':'')})),
        ...(cal.items||[]).map(it=>({when:it.date,dte:it.dte,cat:'earnings',kind:'Résultats',sym:it.sym,
          label:`résultats dans ${it.dte} j · verdict moteur ${esc(VERD_FR[it.verdict]||it.verdict||'n/d')}`
            +(positions.includes(it.sym)?' · <b class="vx-warn">position exposée</b>':'')}))]
        .filter(i=>!cat||i.cat===cat)
        .filter(i=>!horizon||(i.dte!=null&&i.dte<=horizon))
        .filter(i=>!mine||(i.sym&&positions.includes(i.sym))||(i.cat==='macro'&&positions.length))
        .sort((a,b)=>String(a.when).localeCompare(String(b.when)));
      (document.getElementById('op-cal-count')||{}).textContent=items.length+' événement(s)';
      VXCharts.timelineCard('op-cal',{title:'Calendrier des catalyseurs',unit:'événements',
        question:'Quels événements peuvent faire bouger les dossiers ?',
        items:items.slice(0,40),source:'calendrier moteur',timestamp:cal.ts?cal.ts*1000:null,mode:'delayed',
        emptyText:'Aucun événement sur ce filtre.'});
    }
    document.querySelectorAll('[data-cat]').forEach(b=>b.addEventListener('click',()=>{
      cat=b.dataset.cat;
      document.querySelectorAll('[data-cat]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));paint();}));
    document.querySelectorAll('[data-hz]').forEach(b=>b.addEventListener('click',()=>{
      horizon=+b.dataset.hz;
      document.querySelectorAll('[data-hz]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));paint();}));
    document.getElementById('op-cal-mine').addEventListener('click',function(){
      mine=!mine;this.setAttribute('aria-pressed',String(mine));paint();});
    paint();
  }catch(e){($('op-body')||{}).innerHTML=VX.states.error('Calendrier indisponible');}
}

const RENDER={screener:()=>renderScreener(null),
  stocks:()=>renderScreener('ACTION'),
  etf:()=>renderScreener('ETF'),
  options:renderOptions,portfolio:renderPortfolio,
  anomalies:renderAnomalies,calendar:renderCalendar};
function boot(){(RENDER[VIEW]||renderScreener)().catch(e=>{
  ($('op-body')||{}).innerHTML=VX.states.error('Chargement impossible : '+e.message);});}
if(window.VXCharts&&window.Chart)boot();else window.addEventListener('load',boot,{once:true});
})();
</script>
"""


def render(view: str = 'screener', params=None) -> str:
    view = _VIEW_ALIASES.get(view, view)
    view = view if view in dict(_VIEWS) else 'screener'
    p = {k: v for k, v in (params or {}).items() if k in
         ('sym', 'sector', 'setup', 'decision')}
    content = (_CONTENT.replace('%%TABS%%', _tabs(view))
               .replace('%%LOADING%%', '<div class="vx-skeleton" style="height:120px"></div>'))
    #  `json_for_script`, JAMAIS `json.dumps` nu : ce dernier echappe `"` et
    #  `\` mais NI `<` NI `/`. Une valeur contenant `</script>` fermerait la
    #  balise cote analyseur HTML et tout ce qui suit deviendrait du HTML ACTIF —
    #  c'etait le cas de `/opportunities?sym=...` avant le lot 372.
    #
    #  L'integration de `vertex-live` avait rapporte ici les appels nus de cette
    #  branche, qui n'a jamais eu le durcissement du 372. Y ajouter `import json`
    #  aurait fait disparaitre l'erreur ET rouvert la faille.
    js = (_JS.replace('%%CLASSES%%', json_for_script(_referentiel_classes()))
          .replace('%%VIEW%%', json_for_script(view))
          .replace('%%PARAMS%%', json_for_script(p)))
    label = dict(_VIEWS)[view]
    return render_shell(title=f'Opportunités · {label}', active='opportunities',
                        space_label='Opportunités', sub_label=label,
                        content=content, page_js=js,
                        page_label=f'Opportunités {label}')
