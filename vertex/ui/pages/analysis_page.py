"""vertex.ui.pages.analysis_page — la fiche canonique (§26).

Question : « Cette entreprise et cette opportunité méritent-elles du capital
maintenant ? ». Ordre strict : résumé décisionnel → thèse → graphique →
fondamental → catalyseurs → technique → sentiment → anomalies → scénarios →
plan → options → compatibilité portefeuille → historique.
Tout ticker, partout dans l'app, ouvre CETTE fiche.
"""
from __future__ import annotations


from vertex.ui.shell import json_for_script, render_shell


def render_index(view: str = '') -> str:
    dims = ''.join(
        f'<div class="an-dim"><span class="an-dim-n">{n}</span>'
        f'<span class="an-dim-l">{lab}</span></div>'
        for n, lab in [
            ('1', 'Décision — verdict, confiance et prochaine action'),
            ('2', 'Prix — tendance, invalidation et objectifs'),
            ('3', 'Scénarios — perte, cas central et potentiel'),
            ('4', 'Preuves — fondamentaux, catalyseurs et risques'),
        ])
    content = """
<div class="vx-page-header"><div><p class="vx2-eyebrow">Explorer</p><h1>Analyse</h1>
<div class="vx-sub">Ce dossier mérite-t-il du capital potentiel, et sous quelles
conditions&nbsp;?</div></div></div>
<style id="an-index-css">
.an-dim{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px dashed var(--vx-border-soft)}
.an-dim:last-child{border-bottom:none}
.an-dim-n{flex:0 0 26px;height:26px;display:grid;place-items:center;border-radius:8px;
 background:var(--vx-brand-soft);color:var(--vx-copper-light);font:700 12px/1 var(--vx-font-mono,monospace);
 border:1px solid var(--vx-border-accent)}
.an-dim-l{font-size:13px;color:var(--vx-text-secondary)}
.an-shortcut{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;
 border-bottom:1px dashed var(--vx-border-soft);font-size:13px;color:var(--vx-text-secondary)}
.an-shortcut:last-child{border-bottom:none}
.an-kbd{font:600 11px/1 var(--vx-font-mono,monospace);color:var(--vx-text-primary);
 background:var(--vx-graphite-800);border:1px solid var(--vx-border-default);border-radius:6px;padding:4px 7px}
</style>
<div class="vx-grid">
  <div class="vx-col-7">
    <div class="vx-card">
      <div class="vx-field"><label for="an-search">Ticker ou entreprise</label>
      <input class="vx-input" id="an-search" placeholder="ex. NVDA, Microsoft…" autocomplete="off"
        style="font-size:16px;padding:12px" /></div>
      <div id="an-results" class="vx-flex-col"></div>
      <div class="vx-help vx-mt2">Astuce : ⌘K / Ctrl+K depuis n’importe quelle page.</div>
    </div>
    <section class="vx-card vx-mt4" aria-label="Titres récents">
      <div class="vx-card-header"><span class="vx-card-title">Titres récents</span></div>
      <div class="vx-card-body vx-flex vx-wrap" id="an-recent"><span class="vx-skeleton" style="width:120px;height:26px"></span></div>
    </section>
    <section class="vx-card vx-mt4" aria-label="Favoris">
      <div class="vx-card-header"><span class="vx-card-title">Favoris</span>
        <span class="vx-dim" style="font-size:12px">titres marqués ★</span></div>
      <div class="vx-card-body vx-flex vx-wrap" id="an-favs"></div>
    </section>
  </div>
  <aside class="vx-col-5">
    <details class="vx-card an-disclosure" aria-label="Contenu d'une fiche">
      <summary><span>Comment lire une fiche</span><span class="vx-meta">4 repères</span></summary>
      <div class="vx-card-body" style="padding:var(--vx-s3)">""" + dims + """</div>
    </details>
    <section class="vx-card vx-mt4" aria-label="Raccourcis">
      <div class="vx-card-header"><span class="vx-card-title">Raccourcis</span></div>
      <div class="vx-card-body">
        <div class="an-shortcut"><span>Recherche globale</span><span class="an-kbd">⌘K</span></div>
        <div class="an-shortcut"><span>Scanner d’opportunités</span><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities">Ouvrir →</a></div>
        <div class="an-shortcut"><span>Portefeuille & positions</span><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/portfolio">Ouvrir →</a></div>
      </div>
    </section>
  </aside>
</div>
"""
    js = r"""
<script>
(function(){
const $=(id)=>document.getElementById(id);
($('an-recent')||{}).innerHTML=VX.recentTickers.get().map(s=>
  `<button class="vx-btn vx-ticker" data-open-analysis="${s}">${s}</button>`).join('')
  ||'<span class="vx-muted">Aucun titre consulté récemment.</span>';
let favs=[];try{favs=JSON.parse(localStorage.getItem('myFavs')||'[]');}catch(e){favs=[];}
($('an-favs')||{}).innerHTML=(Array.isArray(favs)&&favs.length?favs:[]).map(s=>
  `<button class="vx-btn vx-ticker" data-open-analysis="${s}">${s}</button>`).join('')
  ||'<span class="vx-muted">Aucun favori — marque un titre avec ★ depuis sa fiche.</span>';
let names=null;
/* Échappement local (ce bloc est une IIFE distincte du esc() principal) : les libellés
   de /api/names sont rendus en innerHTML → on neutralise tout HTML/attribut. */
const escN=s=>String(s??'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));
$('an-search').addEventListener('input',async function(){
  const q=this.value.trim().toUpperCase();
  if(!q){($('an-results')||{}).innerHTML='';return}
  try{ if(!names){const d=await VX.fetch('/api/names',{ttl:600000});names=d.names||d;} }catch(e){names={};}
  const hits=Object.entries(names).filter(([s,n])=>s.startsWith(q)||String(n).toUpperCase().includes(q)).slice(0,8);
  ($('an-results')||{}).innerHTML=(hits.length?hits:( /^[A-Z.]{1,6}$/.test(q)?[[q,'ouvrir la fiche']]:[]))
    .map(([s,n])=>`<button class="vx-btn" style="justify-content:flex-start" data-open-analysis="${escN(s)}">
      <span class="vx-ticker" style="min-width:64px">${escN(s)}</span><span class="vx-dim">${escN(n)}</span></button>`).join('')
    ||VX.states.empty('Aucun titre trouvé dans l’univers.');
});
$('an-search').focus();
})();
</script>
"""
    return render_shell(title='Analyse', active='analysis', space_label='Analyse',
                        content=content, page_js=js, page_label='Analyse')


_SECTIONS = """
<style>
#an-scores-card .an-scorecard-grid{display:grid;grid-template-columns:minmax(206px,248px) 1fr;
  gap:32px;align-items:center;width:100%}
@media(max-width:760px){#an-scores-card .an-scorecard-grid{grid-template-columns:1fr;gap:14px}}
/* Cartes sœurs à leur HAUTEUR NATURELLE : quand l'une est plus courte, elle ne s'étire plus
   pour matcher sa voisine → fini les grands vides (riskmap, fundamental, anomalies…). */
#an-workspace .vx-grid{align-items:start}
</style>
<div id="an-stale"></div>
<div id="an-annexes"></div>
<!-- Identité compacte : le verdict canonique reste dans an-verdict, juste dessous. -->
<section class="vx-card vx-accent an-identity" id="an-hero" aria-labelledby="an-identity-title">
  <h2 class="vx-sr-only" id="an-identity-title">Identité et cours de %%SYM%%</h2>
  <div class="an-identity-main">
    <span class="vx-ticker" id="an-sym">%%SYM%%</span>
    <span class="vx-dim" id="an-name">—</span>
    <span class="vx-kpi-value" id="an-price">—</span>
    <span class="vx-mono" id="an-change">—</span>
    <span id="an-fresh"></span>
    <span id="an-badges"></span>
    <span class="vx-right vx-flex">
      <span class="vx-flex" style="gap:2px;margin-right:6px" role="group" aria-label="Mode d'analyse">
        <span class="vx-btn vx-btn-sm vx-btn-primary" aria-current="true" title="Mode actuel : analyse de l'action">Action</span>
        <a class="vx-btn vx-btn-sm" href="/options/dossier/%%SYM%%" title="Dossier options : chaîne, probabilités, IV, scénarios, stratégies">Options</a>
      </span>
      <button class="vx-btn vx-btn-icon vx-btn-ghost" id="an-fav" aria-label="Favori" title="Favori">★</button>
      <button class="vx-btn vx-btn-sm vx-btn-soft" id="an-follow"
        onclick="VXEntities.followStock('%%SYM%%',{decision:(document.getElementById('an-decision')||{}).dataset&&document.getElementById('an-decision').dataset.decision});location.href='/tracking';"
        title="Suivre : mesure la performance hypothétique depuis maintenant">Suivre →</button>
      <button class="vx-btn vx-btn-sm" data-entity-menu="%%SYM%%">Actions ▾</button>
    </span>
  </div>
</section><!-- an-hero : c'était un </div>, donc une fermante ORPHELINE que le
     navigateur ignore. La <section> restait ouverte et tout le dossier —
     scores, physique, workspace, rail — s'imbriquait dans cette carte collante :
     cartes empilées les unes sur les autres, colonnes réduites à un mot par
     ligne. Le défaut préexistait à la refonte ; il a été vu sur la capture. -->
<!-- ── VERDICT CANONIQUE ──────────────────────────────────────────────────
     Ce conteneur MANQUAIT. `paintDecision()` faisait bien `$('an-verdict')`,
     mais l'élément n'existait dans aucune section : la garde `if(V)` avalait
     silencieusement le rendu. Résultat mesuré au navigateur — `#an-verdict`
     absent, `.vx-verdict-card` absente : le verdict canonique était calculé,
     récupéré, puis JETÉ. Le dossier passait de l'identité aux scénarios sans
     jamais dire ce que Vertex conclut.
     Le renderer n'a pas été touché : on lui rend son domicile. -->
<div id="an-trace" class="vx-mt3">%%TRACE%%</div>
<div id="an-verdict" class="vx-mt3"></div>
<!-- Raisonnement du comité : le renderer de loadDecisionStack écrivait dans
     `#an-committee`, qui n'existait dans aucune section (garde `if(CO)`
     silencieuse). L'hôte lui est rendu. -->
<div id="an-committee" class="vx-mt3"></div>

<!-- Scores + radar : SORTIS du hero collant → la barre d'identité (titre/prix/décision)
     reste seule en haut au défilement, le reste de l'analyse défile librement. -->
<!-- Scores et These vivent DANS le workspace §22, plus bas. Les deux cartes
     qui se trouvaient ici en etaient des doublons a l'identique : memes `id`,
     deux fois dans le meme document. `getElementById` ne rend que le PREMIER,
     donc le script remplissait ces cartes-ci et laissait celles du workspace —
     celles que la page met en avant — sur leur tiret. Retirees. -->

<!-- 2-bis. PROFIL DU TITRE — synthèse visuelle au coup d'œil -->
<section class="vx-card vx-mt4 vx-card--premium" id="an-profile">
  <div class="vx-card-header"><span class="vx-card-title">Profil du titre — coup d'œil</span>
    <span class="vx-chart-question">Que disent les moteurs en un regard ?</span></div>
  <div data-body>%%LOADING%%</div>
</section>

<!-- Physique & probabilités (moteurs quant : Monte-Carlo, Kelly, structure statistique, MTF) -->
<div class="vx-grid vx-mt4" id="an-physblock" style="align-items:start">
  <div class="vx-col-7" id="an-mc"></div>
  <div class="vx-col-5" id="an-physics"></div>
</div>
<div class="vx-grid vx-mt3" id="an-physblock2" style="align-items:start">
  <div class="vx-col-5" id="an-kelly"></div>
  <div class="vx-col-7" id="an-mtf"></div>
</div>

<!-- Workspace (§22) : colonne principale + rail sticky décisionnel -->
<div class="vx-grid vx-mt4" id="an-workspace">
<div class="vx-col-8 an-main-column">
  <section class="vx-card" id="an-thesis-card" aria-labelledby="an-thesis-title">
    <div class="vx-card-header"><h2 class="vx-card-title" id="an-thesis-title">Thèse</h2>
      <span class="vx-actions"><button class="vx-btn vx-btn-sm vx-btn-ghost"
        onclick="VXEntities.openAddModal('%%SYM%%','note')">Éditer</button></span></div>
    <div id="an-thesis" class="vx-dim">—</div>
  </section>

<!-- 3. Graphique principal + sous-graphe RSII -->
<!-- Bandeau catalyseur (résultats estimés) : rempli par loadChart, caché
     sans échéance connue. L'hôte manquait ; le bandeau n'apparaissait jamais. -->
<div id="an-catalyst-strip" class="vx-mb2" hidden></div>
<div id="an-chart"></div>
<div id="an-rsi" class="vx-mt2"></div>
<div id="an-volume" class="vx-mt2"></div>

<!-- 3-bis. Valorisation vs secteur (radar) + Financials — fondamentaux réels -->
<div class="vx-grid vx-mt4">
  <div class="vx-col-5" id="an-valuation"></div>
  <section class="vx-card vx-col-7 vx-card--premium" id="an-financials">
    <div class="vx-card-header"><span class="vx-card-title">Financials — fondamentaux</span>
      <span class="vx-actions"><span class="vx-badge" id="an-fin-src">—</span></span></div>
    <div data-body>%%LOADING%%</div>
  </section>
</div>

<!-- 3-ter. Croissance trimestrielle (CA · résultat net · marge) -->
<div class="vx-mt4" id="an-quarters"></div>

<!-- 3-quater. Positionnement (croissance × rentabilité vs pairs) + carte des risques -->
<div class="vx-grid vx-mt4">
  <div class="vx-col-7" id="an-quadrant"></div>
  <section class="vx-card vx-col-5 vx-card--premium" id="an-riskmap">
    <div class="vx-card-header"><span class="vx-card-title">Carte des risques</span>
      <span class="vx-chart-question">Où se concentre la vigilance ?</span></div>
    <div data-body>%%LOADING%%</div>
  </section>
</div>

  <!-- Dimensions dans l'ordre constitutionnel. -->
  <div class="vx-grid vx-mt4">
  <section class="vx-card vx-col-6" id="an-fundamental"><div class="vx-card-header">
    <h3 class="vx-card-title">1 · Fondamental</h3></div><div data-body>%%LOADING%%</div></section>
  <section class="vx-card vx-col-6" id="an-catalysts"><div class="vx-card-header">
    <h3 class="vx-card-title">2 · Catalyseurs</h3></div><div data-body>%%LOADING%%</div></section>
  <section class="vx-card vx-col-6" id="an-technical"><div class="vx-card-header">
    <h3 class="vx-card-title">3 · Timing technique</h3></div><div data-body>%%LOADING%%</div></section>
  <section class="vx-card vx-col-6" id="an-sentiment"><div class="vx-card-header">
    <h3 class="vx-card-title">4 · Sentiment & positionnement</h3></div><div data-body>%%LOADING%%</div></section>
  </div>

  <!-- Expertise à la demande : les moteurs continuent tous de charger, mais
       leurs sorties secondaires ne concurrencent plus le verdict canonique. -->
  <details class="vx-card an-disclosure vx-mt4" id="an-deep-analysis">
    <summary><span>Analyse approfondie</span><span class="vx-meta">scores, anomalies, évidence et signaux</span></summary>
    <div class="an-proof-grid">
      <section aria-labelledby="an-engine-title">
        <h3 id="an-engine-title">Diagnostic moteurs</h3>
        <p class="vx-meta">Score /40, règles bloquantes et audit. Ces diagnostics expliquent la décision sans la remplacer.</p>
        <div id="an-skyler">%%LOADING%%</div>
        <section id="an-rail-decision" aria-label="Sortie ExecutiveEngine">
          <h3 class="vx-sr-only">Sortie ExecutiveEngine</h3><div data-body>%%LOADING%%</div></section>
        <div class="vx-flex vx-wrap vx-mt3" id="an-scores" aria-label="Scores du moteur"></div>
        <p class="vx-meta an-scorecard-note">Marge risque : 100 = aucun garde-fou bloquant ; ce score ne mesure pas la volatilité.</p>
      </section>
      <section aria-labelledby="an-anomaly-title">
        <h3 id="an-anomaly-title">Scanner d’anomalies</h3>
        <p class="vx-meta">Spikes |z|≥2, régime de volatilité, séquences et extrêmes. Constat descriptif, pas une prévision.</p>
        <div id="an-anomaly">%%LOADING%%</div>
        <section id="an-anomalies" aria-label="Liste des anomalies"><div data-body>%%LOADING%%</div></section>
        <details class="an-disclosure an-disclosure--nested">
          <summary>Évidence historique</summary>
          <p class="vx-meta">Résultats observés après les spikes passés de la série disponible. In-sample, descriptif — pas un backtest.</p>
          <div id="an-evidence">%%LOADING%%</div>
        </details>
      </section>
      <section id="an-tv" aria-labelledby="an-tv-title">
        <h3 id="an-tv-title">Signaux TradingView</h3><div data-body>%%LOADING%%</div>
      </section>
    </div>
  </details>
</div>
<aside class="vx-col-4" id="an-rail">
<div class="an-rail-stack">
  <section class="vx-card" id="an-plan"><div class="vx-card-header">
    <h2 class="vx-card-title">Plan & niveaux clés</h2></div><div data-body>%%LOADING%%</div></section>
  <section class="vx-card vx-card--compact" id="an-rail-risks"><div class="vx-card-header">
    <h2 class="vx-card-title">Risques identifiés</h2></div><div data-body>—</div></section>
</div>
</aside>
</div>

<!-- Outils séparés du rail et repliés : disponibles sans écraser la lecture. -->
<details class="vx-card an-disclosure vx-mt4" id="an-tools">
<summary><span>Outils d’analyse</span><span class="vx-meta">copilote et contrôles avant décision</span></summary>
<div class="an-tools-grid">
  <section class="vx-card" id="an-copilot" aria-labelledby="an-copilot-title">
    <div class="vx-card-header"><h2 class="vx-card-title" id="an-copilot-title">Copilote</h2></div>
    <p class="vx-chart-question">Question sur ce titre — réponse ancrée dans les chiffres disponibles.</p>
    <div data-body>
      <input id="an-cp-q" class="vx-input" aria-label="Question sur ce titre" placeholder="ex. Quel est le risque principal ici ?" maxlength="500" autocomplete="off" style="margin-bottom:.4rem" />
      <label class="vx-meta" style="display:flex;align-items:center;gap:6px;margin-bottom:.4rem;cursor:pointer">
        <input type="checkbox" id="an-cp-pos" /> Inclure mes positions déclarées dans la question (vie privée : exclues par défaut)
      </label>
      <button class="vx-btn vx-btn-sm vx-btn-primary" id="an-cp-go">Demander</button>
      <div id="an-cp-out" class="vx-mt2" aria-live="polite"></div>
      <div class="vx-meta vx-mt1">Lecture seule — aucune exécution.</div>
    </div></section>
  <section class="vx-card" id="an-pretrade" aria-labelledby="an-pretrade-title">
    <div class="vx-card-header"><h2 class="vx-card-title" id="an-pretrade-title">Contrôles avant décision</h2></div>
    <p class="vx-chart-question">Sept contrôles descriptifs avant d’envisager ce titre — aucune exécution.</p>
    <div data-body>
      <input id="an-pt-amt" class="vx-input" type="number" min="1" step="any" aria-label="Montant envisag&eacute; en dollars" placeholder="Montant envisagé (ex. 2000)" style="margin-bottom:.4rem" />
      <button class="vx-btn vx-btn-sm vx-btn-primary" id="an-pt-go">Vérifier les garde-fous</button>
      <div id="an-pt-out" class="vx-mt2" aria-live="polite"></div>
    </div></section>
</div>
</details>

<!-- 9. Scénarios -->
<section class="vx-card vx-mt4" id="an-scenarios"><div class="vx-card-header">
  <span class="vx-card-title">Scénarios Bull / Base / Bear</span></div><div data-body>%%LOADING%%</div></section>

<!-- 11. Options : chaîne enrichie (greeks réels + BE/risque max/rendement) + bulle d'équilibre -->
<div class="vx-grid vx-mt4">
  <div class="vx-col-12" id="an-options-chain"></div>
  <div class="vx-col-12" id="an-options-bubble"></div>
</div>
<section class="vx-card vx-mt4" id="an-options" hidden>
  <div class="vx-card-header"><span class="vx-card-title">Options — Vertex Dynamic Options</span>
    <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost"
      href="/options/dossier/%%SYM%%">Dossier options complet →</a></span></div>
  <div data-body>%%LOADING%%</div>
</section>
<div class="vx-grid vx-mt4">
  <section class="vx-card vx-col-6" id="an-portfolio-fit"><div class="vx-card-header">
    <h2 class="vx-card-title">Compatibilité portefeuille</h2></div><div data-body>%%LOADING%%</div></section>
  <section class="vx-card vx-col-6" id="an-history"><div class="vx-card-header">
    <h2 class="vx-card-title">Historique et suivis</h2></div><div data-body>%%LOADING%%</div></section>
</div>
"""

_JS = r"""
<!-- Moteur de chandeliers : ÉCHELLE DE REPLI, pas un chargement concurrent.
     Un SEUL moteur rend le graphique (cf. drawChart plus bas) :
       1. VXCharts.lwCandlestickCard  → CANONIQUE (TradingView Lightweight Charts,
          qualité pro : chandeliers nets, overlays MM + plan, zoom/pan natif).
       2. VXCharts.candlestickCard    → repli Canvas si la lib LWC échoue.
       3. VXCharts.priceCard          → repli ligne si les bougies sont invalides.
     Vérifié navigateur : #an-chart contient un unique .vx-lwc (LWC actif).
     Ne pas retirer les paliers 2-3 : ce sont les replis honnêtes, pas des doublons. -->
<script src="/static/vertex/js/charts/price-chart.js" defer></script>
<script src="/static/vertex/js/charts/option-chain.js" defer></script>
<script src="/static/vertex/js/charts/candlestick-chart.js" defer></script>
<script src="/static/vertex/js/vendor/lightweight-charts.standalone.production.js" defer></script>
<script src="/static/vertex/js/charts/candlestick-lwc.js" defer></script>
<script src="/static/vertex/js/charts/annotations.js" defer></script>
<script src="/static/vertex/js/charts/anomaly-scan.js" defer></script>
<script>
(function(){
'use strict';
const SYM=%%SYM_JSON%%;
const $=(id)=>document.getElementById(id);
const E=()=>window.VXEntities;
function esc(s){return String(s??'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));}
function body(id,html){const el=document.querySelector('#'+id+' [data-body]');if(el)el.innerHTML=html;}
function kv(k,v,cls){return `<div class="vx-kv"><span class="k">${k}</span><span class="v ${cls||''}">${VX.fmt.nd(v)}</span></div>`;}

/* Cellule de métrique premium color-codée. m:{k,val,unit,cmp,tone,bar} — tone∈
   pos/neg/warn/opt/'' ; bar∈[0..100] (position vs médiane, repère à 50). Une
   valeur nulle rend « — » (aucun chiffre inventé). */
function metric(m){
  // Builder partagé (CMP-02) — markup .vx-metric canonique (cmp/mid/kTitle). Repli inline si VX.tile absent.
  if(window.VX&&VX.tile)return VX.tile.metric({k:m.k,kTitle:m.k,v:m.val,unit:m.unit,tone:m.tone,cmp:m.cmp,bar:m.bar,mid:50});
  const v=(m.val===null||m.val===undefined||m.val==='')?'—':m.val;
  const tone=v==='—'?'':(m.tone||'');
  const bar=(m.bar!=null&&v!=='—')?
    `<div class="vx-metric-bar"><i style="width:${Math.max(3,Math.min(100,m.bar))}%"></i><b style="left:50%"></b></div>`:'';
  const cmp=(m.cmp&&v!=='—')?`<div class="vx-metric-cmp">${m.cmp}</div>`:'';
  return `<div class="vx-metric" data-tone="${tone}">`
    +`<span class="vx-metric-k" title="${esc(m.k)}">${esc(m.k)}</span>`
    +`<span class="vx-metric-v">${v}${m.unit?`<span class="vx-metric-u">${m.unit}</span>`:''}</span>`
    +cmp+bar+`</div>`;
}
function metricGrid(cells){return `<div class="vx-metricgrid">${cells.join('')}</div>`;}
/* score radial 0..100 (50=médiane) pour la mini-barre, aligné sur le radar. */
function vsMed(value,median,better){
  if(value==null||median==null||!median)return null;
  const r=better==='low'?(median/value):(value/median);
  return Math.max(6,Math.min(100,r*50));
}

/* Barre de fourchette des objectifs analystes (bas · médian · haut · prix courant).
   Données réelles company.analysts — jamais inventées ; le prix courant n'est
   superposé que s'il existe (souvent absent hors flux live). */
function analystRangeBar(an,price){
  const lo=an.target_low,hi=an.target_high,mid=an.target_median??an.target_mean;
  if(lo==null||hi==null||hi<=lo)return '';
  const pts=[lo,hi];if(mid!=null)pts.push(mid);if(price!=null)pts.push(price);
  const dmin=Math.min.apply(null,pts),dmax=Math.max.apply(null,pts),span=(dmax-dmin)||1;
  const pad=span*0.06,a=dmin-pad,b=dmax+pad,rng=(b-a)||1;
  const pos=(x)=>((x-a)/rng*100).toFixed(1);
  const fillL=pos(lo),fillR=pos(hi);
  const P=(v)=>'$'+VX.fmt.price(v);
  let ticks=`<i class="rb-tick" style="left:${pos(lo)}%"></i><i class="rb-tick" style="left:${pos(hi)}%"></i>`
    +`<span class="rb-lab" style="left:${pos(lo)}%">${P(lo)}<span class="rb-lab-sub">bas</span></span>`
    +`<span class="rb-lab" style="left:${pos(hi)}%">${P(hi)}<span class="rb-lab-sub">haut</span></span>`;
  if(mid!=null)ticks+=`<i class="rb-tick" data-kind="mean" style="left:${pos(mid)}%"></i>`
    +`<span class="rb-lab" data-kind="mean" style="left:${pos(mid)}%">${P(mid)}<span class="rb-lab-sub">objectif</span></span>`;
  if(price!=null)ticks+=`<i class="rb-tick" data-kind="price" style="left:${pos(price)}%"></i>`
    +`<span class="rb-lab" data-kind="price" style="left:${pos(price)}%">${P(price)}<span class="rb-lab-sub">cours</span></span>`;
  return `<div class="vx-rangebar" role="img" aria-label="Fourchette d'objectifs ${P(lo)} à ${P(hi)}">`
    +`<span class="rb-fill" style="left:${fillL}%;right:${(100-fillR)}%"></span>${ticks}</div>`;
}

/* Barres comparatives titre vs pairs sur une métrique (P/E par défaut).
   rows réels (company.fundamentals + peers_data) ; médiane sectorielle en repère. */
function peersCompareBars(cf,peers,sm,opt){
  opt=opt||{};const key=opt.key||'pe';const med=opt.median;
  const self={sym:SYM,val:cf[key],self:1};
  const others=(peers||[]).filter(p=>p&&p.symbol!==SYM&&p[key]!=null&&isFinite(p[key]))
    .map(p=>({sym:p.symbol,val:+p[key]}));
  const all=[self].concat(others).filter(r=>r.val!=null&&isFinite(r.val));
  if(all.length<2)return '';
  const mx=Math.max.apply(null,all.map(r=>Math.abs(r.val)),med?[Math.abs(med)]:[])||1;
  const fmtV=opt.fmt||(v=>(+v).toFixed(1));
  const bars=all.sort((x,y)=>y.val-x.val).map(r=>
    `<div class="vx-cmpbar" data-self="${r.self?1:0}">
       <span class="cb-name">${esc(r.sym)}</span>
       <span class="cb-track"><i style="width:${Math.max(4,Math.min(100,Math.abs(r.val)/mx*100)).toFixed(0)}%"></i></span>
       <span class="cb-val">${fmtV(r.val)}</span></div>`).join('');
  return `<div class="vx-cmpbars">${bars}</div>`
    +(med!=null?`<div class="vx-meta vx-mt1">Médiane secteur : <b class="vx-mono">${fmtV(med)}</b></div>`:'');
}

/* Valorisation vs secteur (radar) + Financials premium — données company réelles
   (cache serveur), jamais inventées. Le prix live peut manquer ; les
   fondamentaux/médianes sectorielles sont servis même sans flux temps réel. */
function paintValuation(t,cf){
  cf=cf||{};
  const sm=(t&&t.sector_median)||{};
  const demo=!!(window.__vxStatus&&window.__vxStatus.demo);
  /* pourcentages : cf.* en fraction (0.27) · sm.median_* déjà en % (18.03) */
  const revG=cf.rev_growth!=null?cf.rev_growth*100:null;
  const marg=cf.margin!=null?cf.margin*100:null;
  const roe=cf.roe!=null?cf.roe*100:null;
  /* ── Radar (via kit premium) ── */
  if(window.VXCharts&&VXCharts.valuationRadar){
    VXCharts.valuationRadar('an-valuation',{
      title:'Valorisation vs secteur',sym:SYM,sectorLabel:'Médiane secteur',
      question:'Le titre se paie-t-il cher ou bon marché face à ses pairs ?',
      axes:[
        {label:'Valorisation',value:cf.pe,median:sm.median_pe,better:'low',fmt:v=>'×'+(+v).toFixed(1)},
        {label:'Valo. fwd',value:cf.forward_pe,median:sm.median_fwd_pe,better:'low',fmt:v=>'×'+(+v).toFixed(1)},
        {label:'Croissance',value:revG,median:sm.median_growth,better:'high',fmt:v=>(+v).toFixed(1)+'%'},
        {label:'Marge',value:marg,median:sm.median_margin,better:'high',fmt:v=>(+v).toFixed(1)+'%'},
        {label:'Rentab.',value:roe,median:sm.median_roe,better:'high',fmt:v=>(+v).toFixed(0)+'%'},
      ],
      source:demo?'company (DÉMO)':'company (cache)',timestamp:null,mode:demo?'fallback':'delayed',
    });
  }
  /* ── Grille Financials premium ── */
  const B=(x)=>{if(x==null||!isFinite(x))return '—';const a=Math.abs(x),s=x<0?'-':'';
    if(a>=1e12)return s+(a/1e12).toFixed(2)+' T$';if(a>=1e9)return s+(a/1e9).toFixed(1)+' Md$';
    if(a>=1e6)return s+(a/1e6).toFixed(0)+' M$';return s+a.toFixed(0)+' $';};
  const cells=[
    metric({k:'P/E',val:cf.pe!=null?'×'+(+cf.pe).toFixed(1):null,
      tone:cf.pe!=null&&sm.median_pe?(cf.pe<sm.median_pe?'pos':'neg'):'',
      cmp:sm.median_pe?`méd ×${(+sm.median_pe).toFixed(1)}`:'',bar:vsMed(cf.pe,sm.median_pe,'low')}),
    metric({k:'P/E anticipé',val:cf.forward_pe!=null?'×'+(+cf.forward_pe).toFixed(1):null,
      tone:cf.forward_pe!=null&&sm.median_fwd_pe?(cf.forward_pe<sm.median_fwd_pe?'pos':'neg'):'',
      cmp:sm.median_fwd_pe?`méd ×${(+sm.median_fwd_pe).toFixed(1)}`:'',bar:vsMed(cf.forward_pe,sm.median_fwd_pe,'low')}),
    metric({k:'PEG',val:cf.peg!=null?(+cf.peg).toFixed(2):null,
      tone:cf.peg!=null?(cf.peg<1?'pos':cf.peg>2?'warn':''):''}),
    metric({k:'Croissance CA',val:revG!=null?(revG>=0?'+':'')+revG.toFixed(1):null,unit:'%',
      tone:revG!=null&&sm.median_growth?(revG>sm.median_growth?'pos':'neg'):'',
      cmp:sm.median_growth?`méd ${(+sm.median_growth).toFixed(1)}%`:'',bar:vsMed(revG,sm.median_growth,'high')}),
    metric({k:'Croissance BPA',val:cf.eps_growth!=null?((cf.eps_growth*100>=0?'+':'')+(cf.eps_growth*100).toFixed(1)):null,unit:'%',
      tone:cf.eps_growth!=null?(cf.eps_growth>0?'pos':'neg'):''}),
    metric({k:'Marge nette',val:marg!=null?marg.toFixed(1):null,unit:'%',
      tone:marg!=null&&sm.median_margin?(marg>sm.median_margin?'pos':'neg'):'',
      cmp:sm.median_margin?`méd ${(+sm.median_margin).toFixed(1)}%`:'',bar:vsMed(marg,sm.median_margin,'high')}),
    metric({k:'ROE',val:roe!=null?roe.toFixed(0):null,unit:'%',
      tone:roe!=null&&sm.median_roe?(roe>sm.median_roe?'pos':'neg'):'',
      cmp:sm.median_roe?`méd ${(+sm.median_roe).toFixed(0)}%`:'',bar:vsMed(roe,sm.median_roe,'high')}),
    metric({k:'Free cash flow',val:B(cf.fcf),tone:cf.fcf>0?'pos':cf.fcf<0?'neg':''}),
    metric({k:'Capitalisation',val:B(cf.mcap)}),
    metric({k:'Trésorerie',val:B(cf.cash),tone:'pos'}),
    metric({k:'Dette',val:B(cf.debt),tone:cf.debt>cf.cash?'warn':''}),
    /* cf.dividend = dividendYield (un RENDEMENT, pas un montant $). yfinance le
       renvoie tantôt en fraction (0.0044) tantôt en pourcent (0.44) selon la
       version → normaliser en % : ×100 si < 1 (fraction), sinon tel quel. */
    metric({k:'Rendement du dividende',val:cf.dividend!=null?((cf.dividend<1?cf.dividend*100:cf.dividend)).toFixed(2):null,unit:cf.dividend!=null?'%':''}),
  ];
  /* Comparaison P/E vs pairs (réel : company.fundamentals + peers_data) */
  const peers=(t&&t.peers_data)||[];
  const cmp=peersCompareBars(cf,peers,sm,{key:'pe',median:sm.median_pe,fmt:v=>'×'+(+v).toFixed(1)});
  const cmpBlock=cmp?`<div class="vx-mt3"><div class="vx-metric-k" style="margin-bottom:6px">P/E — ${SYM} vs pairs</div>${cmp}</div>`:'';
  body('an-financials',metricGrid(cells)+cmpBlock);
  /* Le badge affirmait « cache » dans TOUS les états non-démo. MESURE du
     2026-09-06 sur un titre jamais demandé (instance neuve, cache froid) :
     les douze mesures affichaient « — » sous un badge « cache » — une
     provenance annoncée alors que rien n'était en cache et que la collecte
     était en vol. Absence, collecte en cours, instantané précédent et cache
     sont quatre états DISTINCTS (invariant 5) ; la page connaît déjà le bon
     dans `t.meta`, elle ne le lisait simplement pas ici. */
  const srcEl=$('an-fin-src');
  if(srcEl){
    const fm=(t&&t.meta)||{};
    srcEl.textContent=demo?'DÉMO'
      :(fm.rafraichissement_en_cours||fm.etat==='MISSING')?'collecte en cours'
      :fm.etat==='OFFLINE'?'source injoignable'
      :fm.etat==='STALE'?'scan précédent'
      :fm.qualite==='PARTIELLE'?'cache partiel'
      :'cache';
    srcEl.setAttribute('data-tone',
      demo?'warn'
      :(fm.rafraichissement_en_cours||fm.etat==='MISSING')?''
      :(fm.etat==='OFFLINE')?'risk'
      :(fm.etat==='STALE'||fm.qualite==='PARTIELLE')?'warn':'');
    srcEl.title=demo?'chiffres de démonstration — aucune valeur réelle'
      :(fm.rafraichissement_en_cours||fm.etat==='MISSING')
        ?'les fondamentaux sont en cours de collecte : un tiret signifie « pas encore reçu », pas « zéro »'
      :fm.etat==='OFFLINE'?'la source des fondamentaux est injoignable'
      :fm.etat==='STALE'?'valeurs du scan précédent'
      :'valeurs du dernier instantané collecté';
  }
  paintQuarters(cf,demo);
  paintQuadrant(cf,sm,peers,demo);
  paintRiskMap(t&&t.risk_map);
}

/* Quadrant croissance × rentabilité : le titre (vert) vs ses pairs (acier) vs la
   médiane secteur (repère). Haut-droit = croissance ET rentabilité fortes. Réel. */
/* Etat vide SANS perdre la colonne : remplacer host.className effacait le
   span vx-col-* de la grille 12 colonnes — carte mesuree a 95 px. */
function _gardeSpan(host,base){
  const col=(host.className.match(/vx-col-\d+/)||[''])[0];
  host.className=(base?base+' ':'')+col;
}
function paintQuadrant(cf,sm,peers,demo){
  const host=$('an-quadrant');if(!host)return;
  const P=[];const ok=(x)=>x!=null&&isFinite(x);
  if(ok(cf.rev_growth)&&ok(cf.roe))P.push({x:cf.rev_growth*100,y:cf.roe*100,sym:SYM,self:1});
  (peers||[]).forEach(function(p){if(p&&p.symbol!==SYM&&ok(p.rev_growth)&&ok(p.roe))P.push({x:+p.rev_growth*100,y:+p.roe*100,sym:p.symbol,self:0});});
  if(!P.length||!(window.VXCharts&&window.Chart)){
    _gardeSpan(host,'');host.innerHTML='<div class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Croissance × rentabilité</span></div>'
      +VX.states.empty('Comparables insuffisants pour positionner le titre.')+'</div>';return;
  }
  const cc=VXCharts.colors;
  const med=(ok(sm&&sm.median_growth)&&ok(sm&&sm.median_roe))?[{x:+sm.median_growth,y:+sm.median_roe,sym:'Médiane secteur',self:2}]:[];
  const cfg={type:'scatter',
    data:{datasets:[
      {data:P,pointRadius:function(x){return x.raw&&x.raw.self?8:5;},pointHoverRadius:10,
       pointBackgroundColor:function(x){return x.raw&&x.raw.self?cc.brand:cc.neutral;},
       pointBorderColor:'rgba(0,0,0,.4)',pointBorderWidth:1},
      {data:med,pointStyle:'triangle',pointRadius:9,pointBackgroundColor:cc.warning,
       pointBorderColor:'rgba(0,0,0,.4)',pointBorderWidth:1}]},
    options:{scales:{
      x:{title:{display:true,text:'Croissance CA (%)'},grid:{color:'rgba(255,255,255,.06)'}},
      y:{title:{display:true,text:'ROE (%)'},grid:{color:'rgba(255,255,255,.06)'}}},
      plugins:{tooltip:{callbacks:{label:function(it){var p=it.raw;return p.sym+' — croissance '+p.x.toFixed(1)+'% · ROE '+p.y.toFixed(0)+'%';}}}}}};
  VXCharts.card('an-quadrant',{title:'Croissance × rentabilité vs pairs',unit:'%',
    question:'Le titre allie-t-il croissance ET rentabilité ?',
    conclusion:(ok(cf.rev_growth)&&ok(cf.roe)&&sm)?((cf.rev_growth*100>=(sm.median_growth||0)&&cf.roe*100>=(sm.median_roe||0))?'Cadran qualité — croissance et rentabilité au-dessus du secteur':'Au moins un axe sous la médiane sectorielle'):'',
    height:320,legend:[{label:SYM,color:cc.brand},{label:'Pairs',color:cc.neutral},{label:'Médiane',color:cc.warning}],
    source:demo?'company (DÉMO)':'company (cache)',timestamp:null,mode:'delayed',
    limits:'X = croissance du CA · Y = ROE (rentabilité des fonds propres)',
    render:function(cv){return VXCharts.mount(cv,cfg);}});
}

/* Carte des risques visuelle : les catégories de risk_map (réel, heuristique) en
   barres color-codées par niveau (FAIBLE=vert · MODÉRÉ=ambre · ÉLEVÉ=corail). */
function paintRiskMap(rm){
  const el=document.querySelector('#an-riskmap [data-body]');if(!el)return;
  const risks=(rm&&rm.risks)||[];
  if(!risks.length){el.innerHTML=VX.states.empty('Carte des risques indisponible pour ce titre.');return;}
  const T={'FAIBLE':['var(--vx-positive)',30],'MODÉRÉ':['var(--vx-warning)',62],'MODERE':['var(--vx-warning)',62],
    'ÉLEVÉ':['var(--vx-negative)',95],'ELEVE':['var(--vx-negative)',95],'INCONNU':['var(--vx-steel-3)',10]};
  el.innerHTML='<div class="vx-wbars" style="margin-top:2px">'+risks.map(r=>{
    const t=T[r.level]||['var(--vx-steel-3)',10];
    return `<div class="vx-wbar" title="${esc(r.note||'')}"><span class="wb-name">${esc(r.category||'—')}</span>`
      +`<span class="wb-track"><i style="width:${t[1]}%;background:${t[0]}"></i></span>`
      +`<span class="wb-val" style="color:${t[0]}">${esc(r.level||'—')}</span></div>`;}).join('')+'</div>'
    +`<div class="vx-meta vx-mt2">${esc((rm.limitations&&rm.limitations[0])||'Indicateur de vigilance heuristique — pas une prévision.')}</div>`;
}

/* Croissance trimestrielle : CA + résultat net (barres) + marge nette (ligne, axe
   droit) sur les 8 derniers trimestres. Vraie donnée company.fundamentals.quarters
   (peuplée via yfinance sur le poste utilisateur). Vide honnête si absente. */
function paintQuarters(cf,demo){
  const host=$('an-quarters');if(!host)return;
  const qs=((cf&&cf.quarters)||[]).filter(q=>q&&(q.rev!=null||q.ni!=null));
  if(qs.length<2){
    _gardeSpan(host,'');
    host.innerHTML='<div class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Croissance trimestrielle</span></div>'
      +VX.states.empty('Historique trimestriel indisponible pour ce titre (CA/résultat par trimestre servis via le flux de données du poste).')+'</div>';
    return;
  }
  if(!(window.VXCharts&&window.Chart))return;
  const cc=VXCharts.colors;
  const labels=qs.map(q=>String(q.q).slice(0,7));
  const B=(x)=>x==null?'—':(Math.abs(x)>=1e9?(x/1e9).toFixed(1)+' Md':(Math.abs(x)>=1e6?(x/1e6).toFixed(0)+' M':(''+x)));
  const _qtip=function(it){var q=qs[it.dataIndex];
    return it.dataset.label==='Marge nette'?('Marge '+(q.rev?(q.ni/q.rev*100).toFixed(1):'—')+' %')
      :(it.dataset.label+' : '+B(it.parsed.y));};
  const _qcfg={type:'bar',
    data:{labels:labels,datasets:[
      {type:'bar',label:'CA',data:qs.map(q=>q.rev),backgroundColor:'rgba(143,138,131,.55)',
       borderColor:cc.neutral,borderWidth:1,yAxisID:'y',order:2},
      {type:'bar',label:'Résultat net',data:qs.map(q=>q.ni),
       backgroundColor:qs.map(q=>q.ni>=0?'rgba(54,200,137,.75)':'rgba(237,101,92,.75)'),yAxisID:'y',order:2},
      {type:'line',label:'Marge nette',data:qs.map(q=>(q.rev?q.ni/q.rev*100:null)),
       borderColor:cc.brand,backgroundColor:cc.brand,borderWidth:2,tension:.3,pointRadius:3,yAxisID:'y1',order:1}]},
    options:{scales:{
      y:{position:'left',grid:{color:'rgba(255,255,255,.05)'},ticks:{callback:function(v){return B(v);}}},
      y1:{position:'right',grid:{display:false},ticks:{callback:function(v){return v+' %';}}},
      x:{grid:{display:false}}},
      plugins:{tooltip:{callbacks:{label:_qtip}}}}};
  VXCharts.card('an-quarters',{
    title:'Croissance trimestrielle',unit:'%',question:'Le chiffre d’affaires et le résultat progressent-ils ?',
    conclusion:(function(){const r0=qs[0].rev,r1=qs[qs.length-1].rev;
      return (r0&&r1)?('CA '+(r1>=r0?'en hausse':'en baisse')+' sur '+qs.length+' trimestres'):(qs.length+' trimestres');})(),
    height:300,legend:[{label:'Chiffre d’affaires',color:cc.neutral},{label:'Résultat net',color:cc.positive},{label:'Marge nette',color:cc.brand}],
    source:demo?'company (DÉMO)':'company (cache)',timestamp:null,mode:demo?'fallback':'delayed',
    limits:'CA & résultat net par trimestre · marge = résultat/CA',
    explain:{shows:'Le chiffre d’affaires et le résultat net des 8 derniers trimestres, plus la marge nette.',
      why:'La trajectoire trimestrielle révèle l’accélération ou l’essoufflement, invisibles sur un seul point annuel.',
      confirm:'CA et marge qui montent ensemble, trimestre après trimestre.',
      invalidate:'Marge qui s’érode malgré un CA en hausse — croissance non rentable.'},
    render:function(cv){return VXCharts.mount(cv,_qcfg);}});
}

/* PROFIL DU TITRE — scorecard de synthèse instantanée. 5 mini-jauges radiales
   (dimensions du scoring), probabilité de gain, R:R, performance multi-horizon,
   alignement multi-timeframe, position 52 sem. Données réelles /scan + detail ;
   « — » honnête si le titre est hors du scan courant. */
async function paintProfile(d){
  const el=document.querySelector('#an-profile [data-body]');if(!el)return;
  d=d||{};
  /* Lot 4b : les sous-scores du profil sont DÉJÀ dans le detail /api/ticker → inutile de
     tirer le /scan complet (~8 Mo) pour lire une seule ligne. */
  const _psub=d.sub||{}, _pvx=d.vertex||{};
  const row={st_conf:_psub.confidence,st_mom:_psub.momentum,st_tech:_psub.technical,
             st_fund:_psub.fundamental,st_risk:_psub.risk,score:d.score,
             vx_pwin:_pvx.p_win,vx_rr:_pvx.rr};
  const G=(window.VXCharts&&VXCharts.scoreGaugeSVG)?VXCharts.scoreGaugeSVG:null;
  const dims=[['Conviction',row.st_conf,0],['Momentum',row.st_mom,0],['Technique',row.st_tech,0],
              ['Fondamental',row.st_fund,0],['Risque',row.st_risk,1]];
  const hasDim=dims.some(x=>x[1]!=null);
  if(!hasDim&&d.perf_m==null&&!d.mtf){
    el.innerHTML=VX.states.empty('Profil indisponible — titre hors du scan courant.',
      '<a class="vx-btn vx-btn-sm" href="/system?view=data">Vérifier les données</a>');
    return;
  }
  const gauges=(G&&hasDim)?dims.map(x=>G(x[1],{label:x[0],invert:!!x[2]})).join(''):'';
  const score=row.score;
  const pwin=row.vx_pwin!=null?Math.round(row.vx_pwin*100):null;
  const rr=row.vx_rr;
  const pos52=d.pos52;
  const perf=[['1 sem',d.perf_w],['1 mois',d.perf_m],['1 trim',d.perf_q],['1 an',d.perf_y]];
  const perfMax=Math.max.apply(null,[1].concat(perf.map(p=>Math.abs(p[1]||0))));
  const perfHtml=perf.map(p=>{const v=p[1];const has=v!=null&&!isNaN(v);
    const w=has?Math.max(6,Math.min(100,Math.abs(v)/perfMax*100)):0;
    const col=v>0?'var(--vx-positive)':v<0?'var(--vx-negative)':'var(--vx-steel-3)';
    return `<div class="vx-perfbar"><span class="pb-k">${p[0]}</span>`
      +`<span class="pb-v ${v>0?'vx-pos':v<0?'vx-neg':'vx-muted'}">${has?VX.fmt.pct(v,1):'—'}</span>`
      +`<div class="pb-bar"><i style="width:${w.toFixed(0)}%;background:${col}"></i></div></div>`;}).join('');
  const mtf=d.mtf||{};
  const mtfTone=/HAUSS/i.test(mtf.state||'')?'ai':/BAISS/i.test(mtf.state||'')?'risk':'';
  const side=(score!=null?`<div class="vx-flex" style="align-items:baseline;gap:8px"><span style="font:700 32px/1 var(--vx-font-mono);color:var(--vx-brand-strong)">${score}</span><span class="vx-meta">score composite Vertex</span></div>`:'')
    +(pwin!=null?`<div><div class="vx-meter-row"><span>Probabilité de gain</span><b class="vx-mono">${pwin}%${rr!=null?' · R:R '+VX.fmt.num(rr,1):''}</b></div><div class="vx-meter"><i style="width:${Math.max(2,Math.min(100,pwin))}%"></i></div></div>`:'')
    +(pos52!=null&&!isNaN(pos52)?`<div><div class="vx-meter-row"><span>Position 52 sem.</span><b class="vx-mono">${Math.round(pos52)}%</b></div><div class="vx-meter"><i style="width:${Math.max(2,Math.min(100,pos52))}%;background:var(--vx-steel-3)"></i><b style="left:${Math.max(0,Math.min(100,pos52))}%"></b></div></div>`:'')
    +(mtf.state?`<div class="vx-insight" data-tone="${mtfTone}" style="font-size:12px"><b>MTF ${esc(mtf.state)}</b>${mtf.note?' — '+esc(mtf.note):''}</div>`:'');
  el.innerHTML=`<div class="vx-scorecard">`
    +(gauges?`<div class="vx-gaugecluster">${gauges}</div>`:'')
    +`<div class="vx-scorecard-side">${side||'<span class="vx-meta">Métriques de décision indisponibles.</span>'}</div>`
    +(perfHtml?`<div class="vx-scorecard-side" style="grid-column:1/-1"><span class="vx-metric-k" style="display:block;margin-bottom:2px">Performance</span><div class="vx-perfbars">${perfHtml}</div></div>`:'')
    +`</div>`
    +`<div class="vx-card-footer">${VX.updateIndicator((TICKER&&TICKER.detail&&TICKER.detail.updated)||null,(window.__vxStatus&&window.__vxStatus.source)||'scan',(window.__vxStatus&&window.__vxStatus.demo)?'fallback':'delayed')}</div>`;
}

VX.recentTickers.push(SYM);

/* Header : badges entités + favori */
function paintBadges(){
  ($('an-badges')||{}).innerHTML=E()?E().badges(SYM):'';
  const fav=!!(E()&&E().isFavorite(SYM));
  $('an-fav').style.color=fav?'var(--vx-warning)':'var(--vx-text-muted)';
  $('an-fav').setAttribute('aria-pressed',String(fav));
  $('an-fav').setAttribute('aria-label',fav?'Retirer des favoris':'Ajouter aux favoris');
}
$('an-fav').addEventListener('click',()=>{E().toggleFavorite(SYM);paintBadges();});
['vx:favorites-changed','vx:watchlist-changed','vx:follow-changed','vx:position-changed','vx:alert-changed']
  .forEach(ev=>VX.bus.on(ev,paintBadges));

/* Thèse : note utilisateur si elle existe, sinon THÈSE MOTEUR (auto) — texte réel
   des moteurs sur les données du scan, clairement étiqueté, éditable à tout moment. */
let ENGINE_THESIS=null;
function paintThesis(){
  const note=E()&&E().note(SYM);
  ($('an-thesis')||{}).innerHTML=note?esc(note).replace(/\n/g,'<br>'):
    (ENGINE_THESIS
      ?`<div class="vx-insight" data-tone="ai"><b>Thèse moteur (auto)</b> — ${esc(ENGINE_THESIS)}</div>
        <div class="vx-meta vx-mt2">Générée par les moteurs sur les données du scan — écris ta propre thèse pour la remplacer.
        <button class="vx-btn vx-btn-sm vx-btn-ghost" onclick="VXEntities.openAddModal('${SYM}','note')">Écrire ma thèse</button></div>`
      :VX.states.empty('Aucune thèse enregistrée sur ce titre.',
        `<button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal('${SYM}','note')">Écrire la thèse</button>`));
}
VX.bus.on('vx:thesis-changed',paintThesis);

/* Physique & probabilités — trace la SORTIE des moteurs quant (aucun recalcul client).
   Les couleurs viennent de C.colors mappées sur l'ÉTAT (jamais l'hex du moteur). */
function stCol(state){
  var cc=VXCharts.colors, s=String(state||'').toUpperCase();
  if(/HAUSS|ALIGN|FRACTAL|PERSIST|TENDANCE/.test(s))return cc.positive;
  if(/BAISS|CHAOS|STRESS|DEGRAD|DÉGRAD|CONTRARI|RISQUE/.test(s))return cc.negative;
  if(/MOYENNE|RETOUR|RANGE|NEUTRE|MIXTE|PRUDEN|DIVERG/.test(s))return cc.warning;
  return cc.neutral;
}
function physFoot(src,ts){return '<div class="vx-chart-foot">'+VX.updateIndicator(ts||null,src,'delayed')+'<span class="vx-meta">estimation moteur — lecture seule</span></div>';}
function paintPhysics(d){
  if(!window.VXCharts||!d)return;
  var cc=VXCharts.colors,v=d.vertex||{},mc=v.mc||{},bs=v.bootstrap||{},kelly=v.kelly||{},ph=d.physics||{},mtf=d.mtf||{};
  /* 1) Monte-Carlo / bootstrap : dispersion des rendements */
  var mcEl=$('an-mc');
  if(mcEl){
    var p05=bs.p05,p50=(bs.p50!=null?bs.p50:(mc.edge_mean_bps!=null?+(mc.edge_mean_bps/100).toFixed(2):null)),p95=bs.p95;
    if(p05==null&&p95==null){mcEl.innerHTML='';}
    else{
      var tp1f=mc.p_tp1_first,stopf=mc.p_stop_before_tp1;
      VXCharts.card('an-mc',{
        title:'Dispersion des rendements — Monte-Carlo & bootstrap',
        question:'Quelle fourchette de rendement l’horizon peut-il produire ?',
        conclusion:(p50!=null?'médian '+VX.fmt.pct(p50):'')+(bs.p_positive!=null?' · '+Math.round(bs.p_positive*100)+'% proba positive':''),
        unit:'% horizon',height:232,source:'Monte-Carlo 1200 chemins (GBM) · bootstrap blocs',timestamp:d.updated||null,mode:'delayed',
        limits:'MODEL_ESTIMATE · '+(bs.horizon||mc.days||'?')+' j'+(tp1f!=null?' · TP1 avant stop '+Math.round(tp1f*100)+'% vs stop '+Math.round((stopf||0)*100)+'%':''),
        render:function(cv){return VXCharts.mount(cv,{type:'bar',
          data:{labels:['Pessimiste P05','Médian P50','Optimiste P95'],datasets:[{data:[p05,p50,p95],backgroundColor:[cc.negative,cc.neutral,cc.positive],borderRadius:5,maxBarThickness:46}]},
          options:{indexAxis:'y',scales:{x:{ticks:{callback:function(x){return x+'%';},color:cc.muted,font:{size:10}},grid:{color:cc.grid}},y:{grid:{display:false},ticks:{color:cc.text,font:{size:11}}}},plugins:{legend:{display:false}}}});}
      });
    }
  }
  /* 2) Physique du prix : radar structure statistique + demi-vie */
  var phEl=$('an-physics');
  if(phEl){
    if(ph.hurst==null&&ph.efficiency==null){phEl.innerHTML='';}
    else{
      var col=stCol(ph.state);
      phEl.classList.add('vx-card');
      // Décomposition des mesures RÉELLES (remplit la carte + plus lisible qu'un simple radar).
      var phRow=function(lab,val,hint){return val==null?'':
        '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid var(--vx-border-faint,rgba(255,255,255,.05))">'
        +'<span style="font-size:12px;color:var(--vx-text-secondary)">'+lab+'</span>'
        +'<span style="text-align:right"><b class="vx-mono" style="font-size:13px">'+val+'</b>'
        +(hint?' <span class="vx-meta" style="font-size:10.5px">'+esc(hint)+'</span>':'')+'</span></div>';};
      var hu=ph.hurst, ef=ph.efficiency, en=ph.entropy, hl=ph.half_life;
      var phRows='<div class="vx-mt2">'
        +phRow('Hurst (fractale)', hu!=null?VX.fmt.num(hu,2):null, hu==null?'':(hu<0.45?'anti-persistant · retour moyenne':(hu>0.55?'persistant · tendance':'aléatoire')))
        +phRow('Efficience (Kaufman)', ef!=null?Math.round(ef*100)+' %':null, ef==null?'':(ef>0.55?'mouvement propre':'bruité'))
        +phRow('Entropie (désordre)', en!=null?VX.fmt.num(en,2):null, en==null?'':(en>0.6?'chaotique':'ordonné'))
        +phRow('Demi-vie (retour moy.)', hl!=null?VX.fmt.num(hl,1)+' j':null, hl==null?'':(hl<10?'rapide':'lente'))
        +'</div>';
      phEl.innerHTML='<div class="vx-card-header"><span class="vx-card-title">Physique du prix — structure statistique</span>'
        +'<span class="vx-chart-question">Tendance fractale, retour à la moyenne, ou chaos ?</span></div>'
        +'<div class="vx-flex" style="gap:.4rem;flex-wrap:wrap;margin:2px 0 4px">'
        +'<span class="vx-badge" style="color:'+col+';border-color:'+col+'55">'+esc(ph.state||'—')+'</span>'
        +(ph.half_life!=null?'<span class="vx-badge" title="demi-vie de retour à la moyenne (Ornstein-Uhlenbeck)">demi-vie '+VX.fmt.num(ph.half_life,1)+' j</span>':'')
        +(ph.hurst!=null?'<span class="vx-badge" title="exposant de Hurst">Hurst '+VX.fmt.num(ph.hurst,2)+'</span>':'')+'</div>'
        +'<div id="an-physics-radar"></div>'
        +phRows
        +(ph.note?'<div class="vx-meta" style="margin-top:6px;line-height:1.5">'+esc(ph.note)+'</div>':'')
        +physFoot('regime_features (Hurst · entropie · Kaufman · OU)',d.updated);
      if(VXCharts.radar){VXCharts.radar('an-physics-radar',{axes:[
        {label:'Persistance',value:Math.max(0,Math.min(100,(ph.hurst||0)*100))},
        {label:'Efficience',value:Math.max(0,Math.min(100,(ph.efficiency||0)*100))},
        {label:'Ordre',value:Math.max(0,Math.min(100,(1-(ph.entropy||0))*100))}],
        max:100,ariaLabel:'Physique '+SYM,color:col,width:250,height:186});}
    }
  }
  /* 3) Kelly — jauge de taille suggérée (demi-Kelly capé) */
  var kEl=$('an-kelly');
  if(kEl){
    if(kelly.pct==null){kEl.innerHTML='';}
    else{
      kEl.classList.add('vx-card');
      kEl.innerHTML='<div class="vx-card-header"><span class="vx-card-title">Taille suggérée — critère de Kelly</span>'
        +'<span class="vx-chart-question">Quelle fraction du capital, au maximum ?</span></div><div id="an-kelly-g"></div>'
        +'<div class="vx-meta" style="text-align:center;margin-top:2px">'+esc(kelly.note||'demi-Kelly capé · jamais automatique')+'</div>'
        +physFoot('quant_engine · Kelly',d.updated);
      if(VXCharts.gauge){VXCharts.gauge('an-kelly-g',{value:kelly.pct,min:0,max:15,unit:'%',label:'du capital',
        reading:'plafond prudent 12 %',bands:[{to:6,color:cc.neutral},{to:12,color:cc.brand},{to:15,color:cc.warning}]});}
    }
  }
  /* 4) MTF — alignement multi-horizons */
  var mEl=$('an-mtf');
  if(mEl){
    if(!mtf.state&&mtf.weekly_above30==null){mEl.innerHTML='';}
    else{
      var col2=stCol(mtf.state),dailyUp=(d.ma50_rising===true)||(d.mom>0),wUp=mtf.weekly_above30&&mtf.weekly_rising;
      mEl.classList.add('vx-card');
      mEl.innerHTML='<div class="vx-card-header"><span class="vx-card-title">Alignement multi-horizons (MTF)</span>'
        +'<span class="vx-chart-question">Les horizons tirent-ils dans le même sens ?</span>'
        +'<span class="vx-badge" style="color:'+col2+';border-color:'+col2+'55">'+esc(mtf.state||'—')+'</span></div>'
        +'<div id="an-mtf-flow"></div>'
        +(mtf.note?'<div class="vx-meta" style="margin-top:4px">'+esc(mtf.note)+'</div>':'')
        +physFoot('timeframes (journalier × hebdo)',d.updated);
      if(VXCharts.flow){VXCharts.flow('an-mtf-flow',{nodes:[
        {label:'Journalier',sub:(dailyUp?'haussier':'prudent'),tone:dailyUp?'active':'idle'},
        {label:'Hebdo',sub:(wUp?'haussier':'prudent'),tone:wUp?'active':'idle',count:(mtf.weekly_rsi!=null?Math.round(mtf.weekly_rsi):null)},
        {label:'Conviction',sub:(mtf.adj!=null?(mtf.adj>0?'+'+mtf.adj:''+mtf.adj):''),tone:(col2===cc.positive?'active':(col2===cc.negative?'err':'idle'))}
      ],ariaLabel:'MTF '+SYM});}
    }
  }
}

/* Dossier principal — /api/ticker + décision exécutive */
let TF='6m'; let TICKER=null;
/*  `_g` et `DEC` etaient EMPLOYES et jamais declares.

    `_g` fige la generation de page au moment ou le chargement commence :
    `if(VX.page._gen!==_g)return;` sert a ne rien peindre sur une page que
    l'utilisateur a deja quittee. Sans declaration, cette garde levait
    `ReferenceError` — et emportait tout le chargement du dossier avec elle.
    Elle protegeait donc contre une course, en provoquant une panne certaine.

    `DEC` porte la decision du moteur, relue par le brouillon de these.
    `DEC=dec` sur un nom non declare leve en mode strict, et la page est en
    `'use strict'`.  */
let _g=(window.VX&&VX.page&&VX.page._gen)||0;
let DEC=null;
async function loadDossier(){
  /* Lot 4 : préchauffe EN PARALLÈLE toutes les requêtes indépendantes du dossier —
     les await plus bas récupèrent le résultat déjà en vol (coalescing VX.fetch par URL) :
     une cascade de 5 allers-retours en série devient une seule vague concurrente. */
  ['/api/ticker/'+SYM,'/api/strategy/decision/'+SYM,'/api/anomalies/'+SYM,
   '/api/tradingview/signals?symbol='+SYM,'/api/options/chain/'+SYM]
    .forEach(function(u){try{VX.fetch(u).catch(function(){});}catch(e){}});
  let t=null,exec=null,status=null,stale=false;
  try{t=await VX.fetch('/api/ticker/'+SYM,{ttl:60000});}catch(e){}
  try{exec=await VX.fetch('/api/strategy/decision/'+SYM,{ttl:60000});}catch(e){}
  try{status=status||await VX.fetch('/api/live/status',{ttl:60000});}catch(e){}
  if(window.VX&&VX.page&&VX.page._gen!==_g)return;   // page supplantée → ne rien peindre
  TICKER=t;
  const d=(t&&t.detail)||{};
  const demo=!!(window.__vxStatus&&window.__vxStatus.demo);
  /* Thèse moteur (auto) — affichée tant que l'utilisateur n'a pas écrit la sienne. */
  ENGINE_THESIS=(typeof d.thesis==='string'&&d.thesis)?d.thesis:null;
  paintThesis();
  if(!t||!t.in_universe&&!d.price){
    ($('an-stale')||{}).innerHTML='<div class="vx-error-banner">Titre hors du scan courant — dossier partiel. '
      +'<a class="vx-btn vx-btn-sm" href="/system?view=data">Vérifier les données</a></div>';
  }
  /* État des ANNEXES (entreprise, pairs, options, risques). Depuis que la
     collecte est sortie du chemin synchrone — la fiche montait à 28–48 s sous
     charge, et cinq demandes simultanées du même titre faisaient cinq
     collectes dont une à 136,9 s — elles peuvent ne pas être encore là.
     Le dire est OBLIGATOIRE : servir une fiche amputée en silence serait pire
     que l'attente qu'on vient de retirer. */
  try{
    const m=(t&&t.meta)||null;
    const hote=$('an-annexes');
    if(hote&&m){
      if(m.etat==='MISSING'||m.etat==='OFFLINE'){
        hote.innerHTML='<div class="vx-insight" data-tone="risk">'
          +'<b>Dossier en cours de constitution</b> — entreprise, pairs, options et risques '
          +'n&#8217;ont pas encore été collectés'+(m.rafraichissement_en_cours?' (collecte en cours)':'')
          +(m.erreur?' · '+esc(m.erreur):'')+'. Le prix et le détail du scan ci-dessus sont, eux, à jour.</div>';
      }else{
        const bits=[];
        if(m.etat==='STALE')bits.push('<span class="vx-badge" data-tone="warn">SCAN PRÉCÉDENT</span>');
        if(m.qualite==='PARTIELLE')bits.push('<span class="vx-badge" data-tone="warn">PARTIEL</span>'
          +(m.erreur?' <span class="vx-meta">'+esc(m.erreur)+'</span>':''));
        if(m.rafraichissement_en_cours)bits.push('<span class="vx-meta">actualisation en cours</span>');
        hote.innerHTML=bits.length?('<div class="vx-meta">'+bits.join(' · ')+'</div>'):'';
      }
      /* Relance BORNEE. Sans borne, un titre dont la collecte echoue en
         boucle ferait battre la page indefiniment ; avec zero relance, la
         premiere visite resterait vide jusqu'au prochain rechargement. */
      const enCours=m.rafraichissement_en_cours||m.etat==='MISSING';
      window.__anAttentes=enCours?((window.__anAttentes||0)+1):0;
      /* La borne doit couvrir la collecte REELLE, pas une intuition : mesuree
         entre 17 et 46 s sur un titre neuf (compte reel, TWS ouvert). Une
         premiere version bornait a 6 x 5 s = 30 s et perdait la course — la
         fiche restait « en cours » alors que l'API etait complete. Recul
         progressif : ~4+6+8+10+12+14+16+18+20+22 s, soit environ 130 s. */
      if(enCours&&window.__anAttentes<=10){
        const _d=Math.min(4000+window.__anAttentes*2000,22000);
        setTimeout(()=>{ if(window.VX&&VX.page&&VX.page._gen!==_g)return; loadDossier(); },_d);
      }else if(enCours){
        hote.innerHTML+='<div class="vx-meta">La collecte n&#8217;a pas abouti apr&egrave;s plusieurs tentatives — '
          +'<a href="/system?view=data">v&eacute;rifier les sources</a>.</div>';
      }
    }
  }catch(e){}
  /*  `scanTs`, `scanMode` et `scanSource` étaient EMPLOYÉS à trois endroits
      — la puce de fraîcheur du prix, le pied de la carte ExecutiveEngine et
      le graphique de scénarios — et déclarés NULLE PART. La fiche levait donc
      `ReferenceError` avant même de peindre son en-tête.

      Ils sont dérivés de ce que le serveur a réellement rendu :
        · l'horodatage vient de la décision (`exec.as_of`), qui porte l'heure
          du scan dont le verdict dérive — pas l'heure du navigateur ;
        · le mode vient de `/api/live/status`, jamais d'un drapeau de config ;
        · la source nomme le courtier seulement s'il est vraiment branché.

      `null` quand l'information manque : `VX.updateIndicator` sait rendre
      « n/d », alors qu'une date inventée se lirait comme une mesure.  */
  const scanTs=(exec&&exec.as_of)||null;
  const scanMode=demo?'demo':((status&&status.mode)||'delayed');
  const scanSource=(status&&status.ibkr)?'IBKR · scan':'scan';
  /* Domaine « prix » de /api/live/status : porte l'âge réel (age_s) de la
     dernière cotation servie. `null` quand la route ne l'a pas fourni. */
  const priceDomain=(status&&status.domains&&status.domains.prices)||null;

  /* Hero */
  ($('an-name')||{}).textContent=(t&&t.company&&(t.company.name||t.company.shortName))||'';
  ($('an-price')||{}).textContent=VX.fmt.nd(d.price!==undefined?VX.fmt.price(d.price):null);
  const verdictPrice=$('an-verdict-price');
  if(verdictPrice)verdictPrice.textContent=d.price!=null?VX.fmt.price(d.price):'n/d';
  const chg=d.change;
  ($('an-change')||{}).textContent=chg!==undefined?VX.fmt.pct(chg):'n/d';
  $('an-change').className='vx-mono '+(chg>0?'vx-pos':chg<0?'vx-neg':'vx-muted');
  /* Badge de fraîcheur du prix (§8) : Live / Analyse / À actualiser, honnête. */
  try{
    if($('an-fresh')&&window.VX&&VX.freshness){
      if(d.price==null){($('an-fresh')||{}).innerHTML='';}
      else{
        const ageMs=priceDomain&&typeof priceDomain.age_s==='number'?priceDomain.age_s*1000:null;
        if(demo){($('an-fresh')||{}).innerHTML='<span class="vx-fresh-chip" data-state="demo">DÉMO</span>';}
        else{($('an-fresh')||{}).innerHTML=VX.freshness.chip(VX.freshness.assess({ageMs:ageMs,live:scanMode==='live'}));}
      }
    }
  }catch(e){}
  /*  Hors scan (`available:false`) ou verdict absent, RIEN n'est fabriqué :
      `decision` reste null et le rail dit « NON ÉVALUÉ » avec la raison du
      serveur. Un « ATTENDRE » par défaut se lisait comme un verdict calculé. */
  const horsScan=!exec||exec.available===false||!exec.final_decision;
  const decision=horsScan?null:String(exec.final_decision);
  const decisionAff=decision||'NON ÉVALUÉ';
  /*  Une écriture NUE de `textContent` sur `an-decision` vivait ici, et le
      nœud `#an-decision` n'existe plus : il appartenait à l'agencement
      précédent. (Le motif exact n'est pas recopié ci-dessus : le recensement
      du lot « DOM sûr » lit aussi les commentaires, et le citer ferait
      échouer la garde sur sa propre documentation.)
      L'écriture levait donc « Cannot set properties of null » à CHAQUE
      chargement de fiche, et emportait tout ce qui suit — le rail décisionnel,
      les scénarios, l'audit.

      Le verdict lui-même n'était pas perdu : il est rendu plus bas dans un
      badge `vx-badge-decision` porteur du même `data-decision`. C'est
      l'écriture morte qu'on retire, pas l'information.  */
  /* Rail décisionnel sticky */
  const railD=$('an-rail-decision')&&$('an-rail-decision').querySelector('[data-body]');
  if(railD){
    const audit=(exec&&exec.audit_trail)||[];
    /* Conseil DIRECT : chiffres-clés du plan (setup, R:R, stop) + phrase d'accroche
       de la thèse moteur — tout est déjà calculé, aucune invention. */
    const pl=d.plan||{};
    const advice=[];
    if(pl.setup_quality!=null)advice.push('setup '+VX.fmt.num(pl.setup_quality,0)+'/100');
    if(pl.rr!=null||pl.rr_res!=null)advice.push('R:R '+VX.fmt.num(pl.rr!=null?pl.rr:pl.rr_res,1)+'×');
    if(pl.stop!=null)advice.push('stop '+(pl.stop_type?esc(pl.stop_type)+' ':'')+VX.fmt.nd(pl.stop));
    railD.innerHTML=`<div class="vx-kpi vx-mb2">
        <span class="vx-kpi-value" style="font-size:24px"><span class="vx-badge vx-badge-decision" data-decision="${decisionAff.replace(/É/g,'E').replace(' ','_')}" style="font-size:14px;padding:5px 14px">${esc(decisionAff)}</span></span>
        <span class="vx-kpi-delta vx-muted">${horsScan
          ?esc((exec&&(exec.reason||exec.error))||'titre hors scan courant — aucun verdict calculé')
          :(exec&&exec.reason?esc(exec.reason):'moteur exécutif unique')}</span></div>`
      +(advice.length?`<div class="vx-flex vx-wrap vx-mb2" style="gap:.3rem">${advice.map(a=>`<span class="vx-badge">${a}</span>`).join('')}</div>`:'')
      +(d.thesis?`<div class="vx-insight vx-mb2" data-tone="ai" style="font-size:12px;line-height:1.5">${esc(String(d.thesis).split(/[.·]/)[0])}.</div>`:'')
      +(audit.length?`<details class="vx-mt1"><summary class="vx-meta" style="cursor:pointer">Audit trail (${audit.length})</summary>
        <ul style="margin:6px 0 0;padding-left:16px;font-size:11.5px" class="vx-dim">${audit.slice(0,8).map(a=>`<li>${esc(typeof a==='string'?a:JSON.stringify(a))}</li>`).join('')}</ul></details>`:'')
      +`<div class="vx-card-footer">${scanTs
        ?VX.updateIndicator(scanTs,'ExecutiveEngine',demo?'fallback':scanMode)
        :'<span class="vx-update" data-mode="fallback"><span class="vx-dot"></span>ExecutiveEngine · fraîcheur n/d</span>'}</div>`;
  }
  const railR=$('an-rail-risks')&&$('an-rail-risks').querySelector('[data-body]');
  if(railR){
    const blocking=(exec&&exec.blocking_anomalies)||(exec&&exec.blocking)||[];
    const warns=(exec&&exec.warnings)||[];
    const all=[...blocking.map(b=>({t:'bloquant',v:b})),...warns.map(w=>({t:'attention',v:w}))];
    let html=all.length?all.slice(0,6).map(r=>
      `<div class="vx-insight" data-tone="risk" style="font-size:12px"><b>${r.t}</b> — ${esc(typeof r.v==='string'?r.v:JSON.stringify(r.v))}</div>`).join('')
      :'<span class="vx-meta">Aucun risque bloquant remonté par les moteurs.</span>';
    /* Carte des risques d'entreprise (§24) — fondamentaux réels. */
    const rm=t&&t.risk_map;
    if(rm&&rm.risks){
      const col={'ÉLEVÉ':'var(--vx-negative,#E9555F)','MODÉRÉ':'var(--vx-warning,#D9BE3C)',
        'FAIBLE':'var(--vx-positive,#2BBE90)','INCONNU':'var(--vx-text-muted,#989092)'};
      html+='<div class="vx-mt3" style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--vx-text-muted,#989092)">Carte des risques ('
        +esc(rm.known_count)+'/'+esc(rm.total_count)+' mesurés)</div>'
        +rm.risks.map(r=>`<div style="display:flex;justify-content:space-between;gap:.5rem;padding:.3rem 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:12px">`
          +`<span>${esc(r.category)}</span><span style="color:${col[r.level]||'#888'};font-weight:600">${esc(r.level)}</span></div>`
          +`<div class="vx-meta" style="font-size:11px;margin-bottom:.2rem">${esc(r.note||'')}</div>`).join('');
    }
    railR.innerHTML=html;
  }
  const sc=(exec&&exec.scores)||{};
  const scAxes=[['Conviction',sc.conviction],['Risque',sc.risk],['Timing',sc.timing],
    ['Asymétrie',sc.asymmetry],['Qualité',sc.data_quality]];
  /* Scorecard PRO : radar à gauche + barres étiquetées à droite (équilibré, remplit la
     largeur). Barres en argent neutre — la sémantique varie (risque haut = mauvais,
     conviction haute = bon), on ne colore donc pas en vert/rouge pour ne pas induire. */
  const scBar=(k,v)=>`<div style="display:flex;align-items:center;gap:12px;padding:7px 0;border-bottom:1px solid var(--vx-border-faint,rgba(255,255,255,.05))">
      <span style="flex:0 0 92px;font-size:12.5px;color:var(--vx-text-secondary)">${k}</span>
      <span style="flex:1;min-width:60px;height:7px;border-radius:99px;background:var(--vx-surface-0);overflow:hidden">
        <i style="display:block;height:100%;width:${v==null?0:Math.max(3,Math.min(100,v))}%;background:var(--vx-brand);border-radius:99px;transition:width .4s ease"></i></span>
      <b class="vx-mono" style="flex:0 0 30px;text-align:right;font-size:14px">${VX.fmt.nd(v)}</b></div>`;
  ($('an-scores')||{}).innerHTML=`<div class="an-scorecard-grid">
      <div id="an-scorecard-radar" style="min-height:196px;display:flex;align-items:center;justify-content:center"></div>
      <div style="min-width:0">${scAxes.map(([k,v])=>scBar(k,v)).join('')}${demo?'<div class="vx-badge vx-mt2" style="color:var(--vx-warning)">DONNÉES DÉMO</div>':''}</div>
    </div>`;
  if(scAxes.some(a=>a[1]!==null&&a[1]!==undefined)){
    // Robuste : si exec vient du cache, les scores se peignent AVANT que VXCharts (script
    // deferred) soit prêt → on réessaie jusqu'à ce qu'il le soit (sinon radar vide).
    (function drawScRadar(n){
      if(window.VXCharts&&VXCharts.radar){
        VXCharts.radar('an-scorecard-radar',{axes:scAxes.map(a=>({label:a[0],value:a[1]||0})),
          max:100,ariaLabel:'Scorecard '+SYM,color:VXCharts.colors.brand,width:236,height:200});
      }else if(n<60){setTimeout(function(){drawScRadar(n+1);},80);}
    })(0);
  }
  paintPhysics(d);

  /* 3. Graphique principal — Trading Workspace (chandeliers réels + overlays MM) */
  const S=d.series||{};
  const closes=S.close||[];
  const plan=d.plan||{};
  const tfN={'1m':21,'3m':63,'6m':126,'1y':252,'2y':504}[TF]||126;
  const cut=closes.slice(-tfN);
  const tail=(arr)=>Array.isArray(arr)?arr.slice(-tfN):null;
  /* Bougies RÉELLES seulement si OHLC complet fourni par le moteur (jamais inventé). */
  const O=tail(S.open),H=tail(S.high),L=tail(S.low);
  const bars=(O&&H&&L&&O.length===cut.length)?cut.map((c,i)=>({o:O[i],h:H[i],l:L[i],c:c})):[];
  const VC=window.VXCharts||{cols:{}};
  const cc=(n,f)=>(VC.colors&&VC.colors[n])||f;
  /* Overlays = moyennes mobiles RÉELLES calculées côté serveur (ema20/sma50/sma200). */
  const overlays=[
    {label:'MM20',color:cc('amber','#ce8a29'),data:tail(S.ema20),dash:[]},
    {label:'MM50',color:cc('beige','#c8ad8d'),data:tail(S.sma50),dash:[5,3]},
    {label:'MM200',color:cc('neutral','#9d978e'),data:tail(S.sma200),dash:[2,3]},
  ].filter(o=>o.data&&o.data.some(x=>x!=null));
  const earningsDte=(d.earnings_dte!==null&&d.earnings_dte!==undefined&&d.earnings_dte!==''
    &&Number.isFinite(Number(d.earnings_dte))&&Number(d.earnings_dte)>=0)?Math.round(Number(d.earnings_dte)):null;
  const catalyst=$('an-catalyst-strip');
  if(catalyst){
    catalyst.hidden=earningsDte===null;
    catalyst.innerHTML=earningsDte===null?'':`<span class="vx-badge vx-warn">Résultats estimés · dans ${earningsDte} j</span>
      <span class="vx-meta">Événement futur, hors série historique.</span>`;
  }
  if(cut.length>10){
    /* Chandeliers PRO (TradingView LWC) si OHLC daté dispo ; repli auto sur le
       candlestick Chart.js sinon. Même contrat de carte (contrôles TF, explain…). */
    /* Attendre VXCharts (chart-core.js deferred) : un dossier servi du cache peut tourner
       avant son chargement — meme garde retry que le radar plus haut (sinon ReferenceError). */
    (function drawWorkspace(_n){
    if(!(window.VXCharts&&VXCharts.mount)){ if(_n<60)setTimeout(function(){drawWorkspace(_n+1);},80); return; }
    /*  `candlestick-lwc.js` et `candlestick-chart.js` sont chargés en `defer` :
        ce bloc peut courir AVANT leur enregistrement, et `drawChart` valait
        alors `undefined` — « drawChart is not a function », le graphique
        principal du titre absent, et tout ce qui suit dans la fonction
        emporté avec lui.

        Le même garde-fou existe déjà dans `performance_page` pour
        `equity-chart.js`. On réessaie UNE fois, quand tous les scripts sont
        enregistrés ; si le moteur manque encore, c'est qu'il ne viendra pas,
        et l'on rend un état vide honnête plutôt qu'une exception.  */
    const _moteur=()=>(window.VXCharts&&(VXCharts.lwCandlestickCard||VXCharts.candlestickCard))||null;
    const drawChart=_moteur();
    if(!drawChart){
      window.addEventListener('load',()=>{
        const m=_moteur();
        if(m){loadDossier();}
        else{($('an-chart')||{}).innerHTML=
          (window.VX&&VX.states?VX.states.error('Moteur graphique indisponible')
                                :'<div class="vx-meta">Moteur graphique indisponible</div>');}
      },{once:true});
      return;
    }
    drawChart('an-chart',{
      title:SYM+' — graphique principal',timeframe:TF,
      question:'Le timing est-il exploitable maintenant ?',
      conclusion:(d.verdict?('Verdict technique moteur : '+d.verdict):'—')
        +(plan.rr?` · R:R structurel ${plan.rr}`:''),
      controlsHtml:['1m','3m','6m','1y','2y'].map(tf=>
        `<button class="vx-chip" data-tf="${tf}" aria-pressed="${tf===TF}">${tf}</button>`).join(''),
      labels:cut.map((_,i)=>i-cut.length),bars:bars,closes:cut,overlays:overlays,plan:plan,events:[],
      dates:tail(S.dates),volume:tail(S.volume),
      height:Math.round(Math.min(460,Math.max(340,(window.innerWidth||1200)*0.30))),
      source:scanSource,timestamp:scanTs||null,mode:demo?'demo':scanMode,
      limits:(bars.length?'bougies OHLC quotidiennes':'clôtures quotidiennes')+' du scan · MM = moyennes serveur · niveaux = plan moteur',
      explain:{shows:'Chandeliers (ou clôtures) du titre, moyennes mobiles 20/50/200 et niveaux du plan moteur : entrée, stop (invalidation), objectifs.',
        why:'Le plan chiffré discipline l’exécution : l’invalidation est définie AVANT d’engager du capital ; les MM situent la tendance.',
        confirm:'Cours au-dessus des MM, cassure de la résistance avec volume, breadth favorable.',
        invalidate:`Clôture sous le stop ${VX.fmt.nd(plan.stop)} — la thèse est invalidée, pas « en retard ».`}});
    document.querySelectorAll('[data-tf]').forEach(b=>b.addEventListener('click',()=>{TF=b.dataset.tf;loadDossier();}));
    const chartEl=document.querySelector('#an-chart .vx-lwc')||document.querySelector('#an-chart canvas');
    if(chartEl)chartEl.addEventListener('dblclick',()=>VXCharts.alertFromLevel(SYM,plan.entry||d.price));
    /* Sous-graphe RSI (14) — momentum ; bandes 70 (suracheté) / 30 (survendu) / 50.
       Donnée RÉELLE déjà calculée par le moteur (series.rsi), jamais trace vide. */
    const rsi=tail(S.rsi);
    if(rsi&&rsi.some(x=>x!=null)){
      const rsiBands={id:'vxRsiBands',beforeDatasetsDraw:function(chart){
        const a=chart.chartArea,sy=chart.scales.y,c=chart.ctx;if(!sy)return;c.save();
        [[70,'rgba(237,101,92,.45)'],[30,'rgba(54,200,137,.45)'],[50,'rgba(255,255,255,.12)']].forEach(function(b){
          const y=sy.getPixelForValue(b[0]);if(y<a.top||y>a.bottom)return;
          c.strokeStyle=b[1];c.setLineDash(b[0]===50?[2,3]:[4,3]);c.lineWidth=1;
          c.beginPath();c.moveTo(a.left,y);c.lineTo(a.right,y);c.stroke();});
        c.setLineDash([]);c.restore();}};
      VXCharts.card('an-rsi',{title:SYM+' — RSI (14)',height:118,unit:'RSI',
        question:'Momentum : suracheté (>70) ou survendu (<30) ?',
        conclusion:(d.rsi!=null?('RSI actuel '+VX.fmt.num(d.rsi,0)+(d.rsi>=70?' · suracheté':d.rsi<=30?' · survendu':' · neutre')):''),
        source:'scan',timestamp:(TICKER&&TICKER.detail&&TICKER.detail.updated)||null,mode:demo?'fallback':'delayed',
        render:function(cv){return VXCharts.mount(cv,{type:'line',
          data:{labels:cut.map((_,i)=>i-cut.length),datasets:[{data:rsi,borderColor:VXCharts.colors.brand,borderWidth:1.5,pointRadius:0,tension:.25,fill:false}]},
          options:{scales:{x:{display:false},y:{min:0,max:100,position:'right',grid:{display:false},border:{display:false},ticks:{stepSize:20,font:{size:10},color:VXCharts.colors.muted,padding:6}}},
            plugins:{tooltip:{callbacks:{label:function(ctx){return 'RSI '+VX.fmt.num(ctx.parsed.y,0);}}}}},
          plugins:[rsiBands]});}});
    }else{($('an-rsi')||{}).innerHTML='';}
    /* Sous-graphe Volume — barres colorées selon le sens du jour (hausse/baisse).
       Donnée RÉELLE (series.volume) ; « le mouvement est-il soutenu ? » */
    const vol=tail(S.volume);
    if(vol&&vol.some(x=>x!=null)){
      const volCols=cut.map(function(c,i){return (i>0&&c<cut[i-1])?VXCharts.colors.negative:VXCharts.colors.positive;});
      VXCharts.card('an-volume',{title:SYM+' — Volume',height:96,unit:'titres',
        question:'Le mouvement est-il soutenu par le volume ?',
        source:'scan',timestamp:(TICKER&&TICKER.detail&&TICKER.detail.updated)||null,mode:demo?'fallback':'delayed',
        render:function(cv){return VXCharts.mount(cv,{type:'bar',
          data:{labels:cut.map((_,i)=>i-cut.length),datasets:[{data:vol,
            backgroundColor:volCols.map(function(c){return (VXCharts.rgba&&VXCharts.rgba(c,.5))||c;}),
            borderRadius:1,maxBarThickness:6}]},
          options:{scales:{x:{display:false},y:{position:'right',grid:{display:false},border:{display:false},
            ticks:{maxTicksLimit:3,font:{size:9},color:VXCharts.colors.muted,padding:6,
              callback:function(v){return v>=1e6?(v/1e6).toFixed(0)+'M':v>=1e3?(v/1e3).toFixed(0)+'k':v;}}}},
            plugins:{tooltip:{callbacks:{label:function(ctx){return 'Volume '+VX.fmt.num(ctx.parsed.y,0);}}}}}});}});
    }else{($('an-volume')||{}).innerHTML='';}
    })(0);
  }else{
    ($('an-chart')||{}).innerHTML='<div class="vx-card">'+VX.states.empty('Série de prix indisponible pour ce titre.')+'</div>';
    ($('an-rsi')||{}).innerHTML='';($('an-volume')||{}).innerHTML='';
  }

  /* 4. Fondamental */
  const f=(exec&&exec.fundamental)||{};
  const peers=(t&&t.peers_data)||[];
  /* Le titre analysé n'est JAMAIS dans sa propre liste de pairs → on part de ses
     fondamentaux propres (company.fundamentals) puis on superpose l'entrée pairs
     si elle existe. Sans ce socle, P/E / marge / croissance / ROE restaient vides. */
  const cf=(t&&t.company&&t.company.fundamentals)||{};
  const me=Object.assign({pe:cf.pe,margin:cf.margin,rev_growth:cf.rev_growth,roe:cf.roe},
                         peers.find(p=>p.symbol===SYM)||{});
  /* Formateur « gros montant » (capitalisation, cash-flow) : T$ / Md$ / M$. */
  const fmtBig=(v)=>{if(v==null||isNaN(v))return null;const a=Math.abs(v);
    return a>=1e12?(v/1e12).toFixed(2)+' T$':a>=1e9?(v/1e9).toFixed(1)+' Md$':a>=1e6?(v/1e6).toFixed(0)+' M$':VX.fmt.nd(v);};
  const _kvif=(lab,val)=>val==null||val===''?'':kv(lab,val);
  body('an-fundamental',
    kv('Score fondamental moteur',d.st_fund??f.score)
    +_kvif('Capitalisation',fmtBig(cf.mcap))
    +kv('Croissance CA',me.rev_growth!==undefined?VX.fmt.pct(me.rev_growth*100,0):null)
    +_kvif('Croissance BPA',cf.eps_growth!=null?VX.fmt.pct(cf.eps_growth*100,0):null)
    +kv('Marge',me.margin!==undefined?VX.fmt.pct(me.margin*100,0):null)
    +kv('P/E',me.pe!=null?(+me.pe).toFixed(1):null)
    +_kvif('P/E anticipé',cf.forward_pe!=null?(+cf.forward_pe).toFixed(1):null)
    +_kvif('PEG',cf.peg!=null?(+cf.peg).toFixed(2):null)
    +kv('ROE',me.roe!==undefined&&me.roe!==null?VX.fmt.pct(me.roe*100,0):null)
    +_kvif('Dette / EBITDA',cf.debt_to_ebitda!=null?(+cf.debt_to_ebitda).toFixed(2)+'×':null)
    +_kvif('Cash-flow libre',fmtBig(cf.fcf))
    /* mediane : SEULEMENT la valeur numerique — le repli sur l'objet entier
       rendait « [object Object] » quand sector_median etait un dict vide
       (mesure au navigateur, dossier sans fondamentaux). */
    +kv('Médiane sectorielle P/E',(t&&t.sector_median&&t.sector_median.median_pe!=null)?(+t.sector_median.median_pe).toFixed(1):null)
    +_kvif('Prochains résultats',cf.earnings_date)
    +(peers.length>1?`<div class="vx-meta vx-mt2">Pairs : ${peers.filter(p=>p.symbol!==SYM).slice(0,4).map(p=>
      `<button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${p.symbol}">${p.symbol}</button>`).join('')}</div>`:''));

  /* 4-bis. Valorisation vs secteur (radar) + Financials premium — vraie donnée cachée */
  paintValuation(t,cf);
  /* 2-bis. Profil du titre — scorecard au coup d'œil (dimensions + pwin + perf + MTF) */
  paintProfile(d);

  /* 5. Catalyseurs */
  body('an-catalysts',
    kv('Prochains résultats',earningsDte!==null?('dans '+earningsDte+' j'):null,
       earningsDte!==null&&earningsDte<=10?'vx-warn':'')
    +kv('Politique par défaut','sortie avant annonce (hold-through = dossier complet exigé)')
    +`<div class="vx-meta vx-mt2"><a href="/opportunities?view=calendar">Calendrier complet →</a></div>`);

  /* 6. Technique */
  const ttm=(d.ttm_fired?'🚀 sortie de compression':(d.ttm_squeeze?'🔒 en compression (BB dans Keltner)':null));
  const ttmDir=d.ttm_dir==='up'?' · momentum haussier':d.ttm_dir==='down'?' · momentum baissier':'';
  function perfBars(d){
    const rows=[['1 sem.',d.perf_w],['1 mois',d.perf_m],['1 trim.',d.perf_q],['1 an',d.perf_y]].filter(r=>r[1]!=null&&!isNaN(r[1]));
    if(!rows.length)return '';
    const maxAbs=Math.max(5,...rows.map(r=>Math.abs(r[1])));
    return '<div class="vx-mt2" style="border-top:1px solid var(--vx-border,#30292B);padding-top:8px">'
      +'<div class="vx-meta vx-mb1" style="text-transform:uppercase;letter-spacing:.04em">Performance multi-horizons</div>'
      /* LOT 130 : matiere verre — la barre est un degrade de sa propre couleur,
         doux au centre (zero) et DENSE a l'extremite de la valeur (meme
         grammaire que C.bars), via color-mix sur les tokens (aucun litteral). */
      +rows.map(function(r){const v=r[1];const neg=v<0;const w=Math.min(50,Math.abs(v)/maxAbs*50);
        const tok=neg?'var(--vx-negative,#E9555F)':'var(--vx-positive,#2BBE90)';
        const grad='linear-gradient('+(neg?'270deg':'90deg')+',color-mix(in srgb,'+tok+' 35%,transparent),'+tok+')';
        return '<div style="display:flex;align-items:center;gap:6px;margin:2px 0" role="img" aria-label="'+r[0]+' '+(v>=0?'+':'')+v+' %">'
          +'<span style="width:52px;font-size:10.5px;color:var(--vx-text-muted,#989092)">'+r[0]+'</span>'
          +'<span style="flex:1;height:10px;position:relative;background:var(--vx-surface-3,#121214);border-radius:3px;overflow:hidden">'
            +'<span style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:rgba(255,255,255,.16)"></span>'
            +'<span style="position:absolute;top:0;bottom:0;'+(neg?('right:50%;width:'+w.toFixed(1)+'%'):('left:50%;width:'+w.toFixed(1)+'%'))+';background:'+grad+';border-radius:2px"></span></span>'
          +'<span style="width:54px;text-align:right;font-size:10.5px;font-variant-numeric:tabular-nums" class="'+(neg?'vx-neg':'vx-pos')+'">'+(v>=0?'+':'')+VX.fmt.num(v,1)+'%</span></div>';
      }).join('')+'</div>';
  }
  /* Checklist de signaux techniques (booléens RÉELS du moteur — jamais inventés). */
  const SIGLABEL={above20:'Cours > MM20',above50:'Cours > MM50',above200:'Cours > MM200',
    stacked:'MM empilées (20>50>200)',golden:'Golden cross',momCross:'Croisement momentum',
    rsiBull:'RSI haussier',volUp:'Volume en hausse'};
  function signalsGrid(d){
    const s=d.signals; if(!s||typeof s!=='object')return '';
    const items=Object.keys(SIGLABEL).filter(k=>k in s);
    if(!items.length)return '';
    const n=(d.sigcount!=null)?d.sigcount:items.filter(k=>s[k]).length;
    return '<div class="vx-mt2" style="border-top:1px solid var(--vx-border);padding-top:8px">'
      +'<div class="vx-meta vx-mb1" style="text-transform:uppercase;letter-spacing:.04em">Checklist de signaux ('+n+'/'+items.length+')</div>'
      +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 12px">'
      +items.map(function(k){var on=!!s[k];return '<div style="display:flex;gap:6px;align-items:center;font-size:11.5px">'
        +'<span style="flex:0 0 auto;font-weight:700;color:'+(on?'var(--vx-positive)':'var(--vx-text-faint)')+'">'+(on?'✓':'○')+'</span>'
        +'<span style="color:var(--vx-text-'+(on?'secondary':'faint')+')">'+SIGLABEL[k]+'</span></div>';}).join('')
      +'</div></div>';
  }
  /* Décomposition honnête du score : base → ajustements moteur → score final. */
  function scoreDecomp(d){
    if(d.base_score==null)return '';
    const parts=[['Physique',d.phys_adj],['Multi-horizons',d.mtf_adj],['Structure',d.struct_adj]]
      .filter(function(p){return p[1]!=null&&p[1]!==0;});
    const fmt=function(v){return (v>0?'+':'')+VX.fmt.num(v,0);};
    return '<div class="vx-mt2" style="border-top:1px solid var(--vx-border);padding-top:8px">'
      +'<div class="vx-meta vx-mb1" style="text-transform:uppercase;letter-spacing:.04em">Décomposition du score</div>'
      +'<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:11.5px;font-variant-numeric:tabular-nums">'
      +'<span class="vx-mono">base '+VX.fmt.num(d.base_score,0)+'</span>'
      +parts.map(function(p){return '<span class="vx-badge '+(p[1]>0?'vx-pos':'vx-neg')+'">'+p[0]+' '+fmt(p[1])+'</span>';}).join('')
      +'<span class="vx-mono" style="font-weight:700">= '+VX.fmt.num(d.score,0)+'</span></div></div>';
  }
  body('an-technical',
    kv('Score',d.score)+kv('Verdict technique (métadonnée)',d.verdict)
    +kv('Force relative',d.rs)+kv('RSI',d.rsi)
    +kv('Position 52 semaines',d.pos52!==undefined?d.pos52+' %':null)
    +kv('Extension vs ATR',d.ext_atr,(d.ext_atr>=2.5?'vx-warn':''))
    +(ttm?kv('TTM Squeeze',ttm+ttmDir,(d.ttm_fired&&d.ttm_dir==='up'?'vx-pos':d.ttm_fired&&d.ttm_dir==='down'?'vx-neg':'')):'')
    +perfBars(d)
    +signalsGrid(d)
    +scoreDecomp(d)
    +`<div class="vx-meta vx-mt2">La décision finale unique reste ${decision} — les verdicts techniques sont des entrées du moteur exécutif.</div>`);

  /* 7. Sentiment + consensus analystes (données company déjà chargées → objectif de cours + potentiel) */
  const an=(t&&t.company&&t.company.analysts)||{};
  const _px=d.price, _tgt=an.target_mean;
  const _up=(_tgt&&_px)?((_tgt/_px-1)*100):null;
  const _rl={strong_buy:'Achat fort',buy:'Achat',outperform:'Surperformance',hold:'Conserver',underperform:'Sous-performance',sell:'Vente'}[an.rating]||an.rating;
  const consensus=(an.rating||_tgt)?(
    `<div class="vx-mt2" style="border-top:1px solid var(--vx-border,#30292B);padding-top:8px">`
    +(an.rating?`<div class="vx-kv"><span class="k">Consensus analystes</span><span class="v">${esc(_rl||'—')}${an.rating_mean!=null?` (${(+an.rating_mean).toFixed(1)}/5)`:''}${an.n_analysts?` · ${an.n_analysts} analystes`:''}</span></div>`:'')
    +(_tgt?`<div class="vx-kv"><span class="k">Objectif moyen</span><span class="v">${VX.fmt.price(_tgt)}${_up!=null?` <span class="${_up>=0?'vx-pos':'vx-neg'}">(${_up>=0?'+':''}${_up.toFixed(1)}%)</span>`:''}</span></div>`:'')
    +analystRangeBar(an,_px)
    +`</div>`):'';
  body('an-sentiment',
    kv('Force relative vs univers',d.rs)
    +kv('Régime marché',(exec&&exec.technical&&exec.technical.regime)||null)
    +consensus
    +`<div class="vx-meta vx-mt2">Positionnement institutionnel : proxies uniquement — jamais présentés comme des flux certains. Consensus analystes = données publiques (peut dater).</div>`);

  /* 8. Anomalies */
  try{
    const a=await VX.fetch('/api/anomalies/'+SYM,{ttl:120000});
    const anoms=(a.anomalies||[]).slice().sort((x,y)=>(y.blocking?1:0)-(x.blocking?1:0)||(y.severity||0)-(x.severity||0));
    const sevCol=(s,blk)=>blk?'var(--vx-negative)':(s>=3?'var(--vx-negative)':s>=2?'var(--vx-warning)':'var(--vx-text-muted)');
    body('an-anomalies',anoms.length?
      anoms.map(x=>`<div class="vx-flex" style="gap:8px;align-items:flex-start;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.05)">
        <span class="vx-badge" style="color:${sevCol(x.severity,x.blocking)};flex:0 0 auto">${x.blocking?'⛔ ':''}${esc(x.code||'')}${x.severity?' · sev '+x.severity:''}</span>
        <span class="vx-meta" style="flex:1;white-space:normal;line-height:1.4">${esc(x.impact||'')}${x.confidence!=null?` <span class="vx-dim">(${Math.round(x.confidence*100)} % conf.)</span>`:''}</span></div>`).join('')
      +`<div class="vx-meta vx-mt2">${esc(a.note||'')}</div>`
      :VX.states.empty('Aucune anomalie détectée sur la série disponible.'));
  }catch(e){body('an-anomalies',VX.states.error('Moteur d’anomalies injoignable'));}

  /* TradingView (§30) + confluence vs verdict moteur (miroir de tv_confluence.py) */
  try{
    const TV_BULL=['SUPPORT_RECLAIM','BREAKOUT_CONFIRMED','BREAKOUT_RETEST','MOMENTUM_ACCELERATION','VOLUME_EXPANSION','TREND_ALIGNMENT'];
    const TV_BEAR=['FAILED_BREAKOUT','THESIS_INVALIDATION'];
    const vDn=/AVOID|ÉVITER|EVITER|ALL[ÉE]GER|SORTIR|R[ÉE]DUIRE|NO_NEW_RISK|VENDRE|REFUS|REJET/i.test(d.verdict||'');
    const vUp=/ACHETER|BUY|RENFORCER|ACCUMULER/i.test(d.verdict||'');
    /* baissier d'abord (miroir de tv_confluence.verdict_stance) — jamais un faux CONFIRME */
    const vStance=vDn?'BEARISH':(vUp?'BULLISH':'NEUTRAL');
    function confl(sig){
      const sd=TV_BULL.indexOf(sig)>=0?'BULLISH':(TV_BEAR.indexOf(sig)>=0?'BEARISH':'NEUTRAL');
      if(sd==='NEUTRAL'||vStance==='NEUTRAL')return ['NEUTRE','vx-dim','·'];
      if(sd===vStance)return ['CONFIRME','vx-pos','✓'];
      return ['CONTREDIT','vx-neg','✗'];
    }
    const tv=await VX.fetch('/api/tradingview/signals?symbol='+SYM,{ttl:60000});
    const sigs=(tv.signals||[]).slice(-4).reverse();
    let confirms=0,contradicts=0;
    sigs.forEach(s=>{const c=confl(s.signal);if(c[0]==='CONFIRME')confirms++;else if(c[0]==='CONTREDIT')contradicts++;});
    const overall=contradicts&&!confirms?['CONTREDIT le verdict','vx-neg']
      :confirms&&!contradicts?['CONFIRME le verdict','vx-pos']
      :(confirms||contradicts)?['signaux MIXTES','vx-dim']:['—','vx-dim'];
    body('an-tv',(sigs.length?
      (d.verdict?`<div class="vx-kv"><span class="k">Confluence</span><span class="v ${overall[1]}"><b>${overall[0]}</b> <span class="vx-meta">(vs ${esc(d.verdict)})</span></span></div>`:'')
      +sigs.map(s=>{
      const fresh=(s.fresh!==undefined)?s.fresh:((Date.now()/1000-(s.received_ts||0))<=6*3600);
      const c=confl(s.signal);
      return `<div class="vx-kv"><span class="k">${s.signal}</span>
        <span class="v"><span class="vx-badge ${c[1]}" title="confluence">${c[2]} ${c[0]}</span>
        ${fresh?'':'<span class="vx-badge">rassis</span>'}
        <span class="vx-meta">${VX.fmt.ago((s.received_ts||0)*1000)}</span></span></div>`;}).join('')
      +'<div class="vx-meta vx-mt2">Un signal TradingView déclenche une réévaluation — jamais un ACHETER direct. La confluence est une lecture de cohérence, pas une décision.</div>'
      :((tv.status&&(tv.status.state==='DISABLED'||tv.status.configured===false))
        ?VX.states.empty('Webhook TradingView non configuré — signaux désactivés.',
          '<span class="vx-meta">Définis <span class="vx-mono">TRADINGVIEW_WEBHOOK_SECRET</span> dans <span class="vx-mono">.env</span>, puis configure ton alerte — guide dans <a href="/system?view=connections">Système → Connexions</a>.</span>')
        :VX.states.empty('Aucun signal TradingView reçu pour ce titre.',
          '<span class="vx-meta">Webhook actif : /api/tradingview/webhook (voir tradingview/README.md)</span>')))
      +`<div class="vx-flex vx-mt2">
        <a class="vx-btn vx-btn-sm" target="_blank" rel="noopener" href="https://www.tradingview.com/chart/?symbol=${SYM}">Ouvrir dans TradingView ↗</a>
        <button class="vx-btn vx-btn-sm vx-btn-ghost" onclick="VXEntities.openAddModal('${SYM}','alert')">Créer une alerte</button></div>`);
  }catch(e){body('an-tv',VX.states.empty('Intégration TradingView non configurée — aucune donnée inventée.'));}

  /* 9. Scénarios : domicile unique = Carte-Scénario en tête (loadDecisionStack). */

  /* 10. Plan — échelle Risk/Reward (§24.5) : niveaux du plan proportionnels au prix */
  function rrLadder(px,plan){
    const VC=window.VXCharts||{colors:{}};const col=(n,f)=>(VC.colors&&VC.colors[n])||f;
    const lv=[];
    if(plan.stop!=null)lv.push({k:'Stop',v:plan.stop,c:col('negative','#E9555F')});
    const e=plan.entry;
    if(e!=null)lv.push({k:'Entrée',v:e,c:col('info','#45D6E8')});
    else if(px!=null)lv.push({k:'Cours',v:px,c:col('neutral','#8A8284')});
    [plan.tp1,plan.tp2,plan.tp3].forEach(function(t,i){if(t!=null)lv.push({k:'TP'+(i+1),v:t,c:col('positive','#2BBE90')});});
    if(lv.length<2)return '';
    const vals=lv.map(function(l){return l.v;});
    const min=Math.min.apply(null,vals),max=Math.max.apply(null,vals),rng=(max-min)||1;
    const W=280,H=16+lv.length*26,padT=12,padB=12,plotH=H-padT-padB,axX=70;
    const y=function(v){return padT+(max-v)/rng*plotH;};
    let bands='';
    if(plan.stop!=null&&e!=null)bands+='<rect x="'+(axX-4)+'" y="'+Math.min(y(e),y(plan.stop)).toFixed(1)+'" width="8" height="'+Math.abs(y(plan.stop)-y(e)).toFixed(1)+'" fill="'+col('negative','#dc5f52')+'" fill-opacity=".18"/>';
    const tps=[plan.tp1,plan.tp2,plan.tp3].filter(function(t){return t!=null;});
    const topTp=tps.length?Math.max.apply(null,tps):null;
    if(topTp!=null&&e!=null)bands+='<rect x="'+(axX-4)+'" y="'+Math.min(y(e),y(topTp)).toFixed(1)+'" width="8" height="'+Math.abs(y(topTp)-y(e)).toFixed(1)+'" fill="'+col('positive','#38b879')+'" fill-opacity=".16"/>';
    const rows=lv.map(function(l){const yy=y(l.v);const pct=(px&&l.v)?((l.v/px-1)*100):null;
      return '<line x1="'+axX+'" y1="'+yy.toFixed(1)+'" x2="'+(axX+8)+'" y2="'+yy.toFixed(1)+'" stroke="'+l.c+'" stroke-width="2"/>'
        +'<circle cx="'+axX+'" cy="'+yy.toFixed(1)+'" r="3" fill="'+l.c+'"/>'
        +'<text x="'+(axX-8)+'" y="'+(yy+3).toFixed(1)+'" text-anchor="end" font-size="10" fill="var(--vx-text-secondary,#BABABA)">'+l.k+'</text>'
        +'<text x="'+(axX+14)+'" y="'+(yy+3).toFixed(1)+'" font-size="10.5" fill="'+l.c+'" style="font-variant-numeric:tabular-nums">'+VX.fmt.nd(l.v)+(pct!=null?' ('+(pct>=0?'+':'')+pct.toFixed(1)+'%)':'')+'</text>';}).join('');
    const aria='Échelle risque/récompense : '+lv.map(function(l){return l.k+' '+VX.fmt.nd(l.v);}).join(', ')+(plan.rr?', R:R '+plan.rr:'');
    return '<svg viewBox="0 0 '+W+' '+H+'" width="100%" style="max-width:'+W+'px;display:block;margin:0 auto 10px" role="img" aria-label="'+aria.replace(/"/g,'&quot;')+'">'
      +'<line x1="'+axX+'" y1="'+padT+'" x2="'+axX+'" y2="'+(H-padB)+'" stroke="rgba(255,255,255,.12)"/>'+bands+rows+'</svg>';
  }
  body('an-plan',
    rrLadder(d.price,plan)
    +`<details class="an-disclosure an-disclosure--nested vx-mt3">
      <summary>Voir tous les niveaux</summary>
      <div class="vx-mt2">`
    +kv('Entrée',plan.entry)+kv('Stop (invalidation sous-jacent)',plan.stop,'vx-neg')
    +kv('TP1',plan.tp1,'vx-pos')+kv('TP2',plan.tp2,'vx-pos')+kv('TP3',plan.tp3,'vx-pos')
    +kv('R:R structurel',plan.rr)
    +`</div></details>
    <div class="vx-flex vx-mt3" style="flex-wrap:wrap;gap:.4rem">
      <button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal('${SYM}','follow')">Créer un suivi</button>
      <button class="vx-btn vx-btn-sm vx-btn-ghost" onclick="VXCharts.alertFromLevel('${SYM}',${JSON.stringify(plan.entry??null)})">Alerte sur l’entrée</button>
      <button class="vx-btn vx-btn-sm vx-btn-soft" onclick="window.__prepOrder&&window.__prepOrder('${SYM}')">Calculer le dimensionnement</button>
    </div>
    <div id="an-order-ticket" class="vx-mt2"></div>`);
  window.__prepOrder=function(sym){
    const host=document.getElementById('an-order-ticket');if(!host)return;
    const av=Number(localStorage.getItem('vxAccountValue')||'')||null;
    host.innerHTML=`<div class="vx-card">
      <div class="vx-card-header"><span class="vx-card-title">Dimensionnement indicatif — aucune exécution</span></div>
      <div class="vx-card-body vx-flex" style="gap:.5rem;flex-wrap:wrap;align-items:end">
        <label class="vx-field" style="max-width:170px"><span>Valeur du compte ($)</span>
          <input id="ot-av" class="vx-input" type="number" step="any" value="${av||''}" placeholder="ex. 100000"></label>
        <label class="vx-field" style="max-width:130px"><span>Risque par trade (%)</span>
          <input id="ot-rp" class="vx-input" type="number" step="any" value="1"></label>
        <button class="vx-btn vx-btn-sm" id="ot-go">Calculer</button>
      </div>
      <div id="ot-out"></div></div>`;
    document.getElementById('ot-go').addEventListener('click',function(){
      const avv=Number(document.getElementById('ot-av').value)||null;
      const rp=Number(document.getElementById('ot-rp').value)||null;
      if(avv)localStorage.setItem('vxAccountValue',String(avv));
      fetch('/api/planning/ticket',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({symbol:sym,account_value:avv,risk_pct:rp})})
        .then(r=>r.json()).then(function(t){
          const out=document.getElementById('ot-out');if(!out)return;
          const s=t.sizing||{};
          const warn=(t.blockers||[]).concat(t.warnings||[]);
          out.innerHTML='<div class="vx-mt2">'
            +'<div class="vx-stats-row" style="display:flex;gap:1.2rem;flex-wrap:wrap">'
            +'<div><div class="vx-meta">Quantité</div><b style="font-size:18px">'+(t.qty!=null?t.qty:'—')+'</b></div>'
            +'<div><div class="vx-meta">Capital à risque</div><b>'+(s.capital_at_risk!=null?'$'+s.capital_at_risk:'—')+'</b></div>'
            +'<div><div class="vx-meta">Capital engagé</div><b>'+(s.capital_deployed!=null?'$'+s.capital_deployed:'—')+'</b></div>'
            +'<div><div class="vx-meta">Poids projeté</div><b>'+(s.weight_pct!=null?s.weight_pct+' %':'—')+'</b></div>'
            +'<div><div class="vx-meta">R:R</div><b>'+(t.reward_risk!=null?t.reward_risk:'—')+'</b></div></div>'
            +(t.blocked?'<div class="vx-stale-banner vx-mt2">⛔ Préparation bloquée par la stratégie : '+warn.map(esc).join(' · ')+'</div>'
              :(warn.length?'<div class="vx-meta vx-mt2" style="color:var(--vx-warning)">'+warn.map(esc).join(' · ')+'</div>':''))
            +'<pre id="ot-pre" style="white-space:pre-wrap;background:var(--vx-surface-2,#121214);padding:.7rem;border-radius:8px;margin-top:.7rem;font-size:12px">'+esc(t.copy_text||'')+'</pre>'
            +'<button class="vx-btn vx-btn-sm vx-btn-ghost" id="ot-copy">Copier l’analyse</button>'
            +'<div class="vx-meta vx-mt1">'+esc(t.disclaimer||'')+'</div></div>';
          const cp=document.getElementById('ot-copy');
          if(cp)cp.addEventListener('click',function(){
            const pre=document.getElementById('ot-pre');
            if(pre&&navigator.clipboard)navigator.clipboard.writeText(pre.textContent);
            VX.toast('Ticket d’analyse copié — aucune transmission','success');});
        }).catch(function(e){(document.getElementById('ot-out')||{}).innerHTML='<div class="vx-error-banner">'+esc(e.message)+'</div>';});
    });
  };

  /* 11. Options — chaîne ENRICHIE via /api/options/chain (board réel : greeks
     delta/gamma/theta/vega, IV, OI, volume, prime, break-even, PoP, qualité) +
     colonnes calculées risque max & rendement. Composant partagé C.optionChainTable
     + bulle d'équilibre prime×DTE. Shortlist honnête, greeks = modèle. */
  try{
    const ch=await VX.fetch('/api/options/chain/'+SYM,{ttl:180000});
    const arr=(ch&&ch.contracts)||[];
    if(arr.length&&window.VXCharts&&VXCharts.optionChainTable){
      VXCharts.optionChainTable('an-options-chain',{contracts:arr,spot:ch.spot,sym:SYM,
        source:ch.source||'board options',timestamp:ch.as_of,mode:ch.on_demand?'delayed':'delayed'});
      if(VXCharts.bestContractBubble)VXCharts.bestContractBubble('an-options-bubble',{contracts:arr,spot:ch.spot,
        source:ch.source||'board options',timestamp:ch.as_of,mode:'delayed'});
    }else{
      const host=document.getElementById('an-options-chain');
      if(host){_gardeSpan(host,'vx-card');host.innerHTML='<div class="vx-card-header"><span class="vx-card-title">Chaîne — meilleurs contrats</span></div>'
        +VX.states.empty('Aucun contrat exploitable pour '+esc(SYM)+' (IBKR hors ligne ou titre sans options liquides).',
          '<a class="vx-btn vx-btn-sm" href="/options/dossier/'+SYM+'">Ouvrir le dossier options</a>');}
      const bb=document.getElementById('an-options-bubble');if(bb)bb.innerHTML='';
    }
  }catch(e){
    const host=document.getElementById('an-options-chain');
    if(host){_gardeSpan(host,'vx-card');host.innerHTML='<div class="vx-card-header"><span class="vx-card-title">Chaîne — meilleurs contrats</span></div>'
      +VX.states.empty('Chaîne d’options indisponible ('+esc(e.message)+').');}
  }

  /* 12. Compatibilité portefeuille */
  const positions=E()?E().positions():[];
  const held=positions.filter(p=>p.sym===SYM);
  const count=positions.length;
  body('an-portfolio-fit',
    kv('Positions déclarées',count+' / 10 max')
    +kv('Ce titre',held.length?('détenu ('+held.map(h=>h.type).join(', ')+')'):'non détenu')
    +kv('Règle',count>=10?'portefeuille plein — remplacement obligatoire':'place disponible',
        count>=10?'vx-warn':'vx-pos')
    +`<div class="vx-meta vx-mt2"><a href="/portfolio?view=risk">Risque complet (positions réelles) →</a></div>`);

  /* 13. Historique */
  const jr=(E()?E().journal():[]).filter(j=>j.ticker===SYM).slice(-5).reverse();
  const follows=(E()?E().follows():[]).filter(r=>r.sym===SYM);
  body('an-history',
    (follows.length?`<div class="vx-insight">Suivi actif depuis ${follows[0].followed}
      — stop ${VX.fmt.nd(follows[0].stop)}, objectif ${VX.fmt.nd(follows[0].tgt)}</div>`:'')
    +(jr.length?jr.map(j=>`<div class="vx-kv"><span class="k">${j.date} · ${esc(j.dir||'')}</span>
      <span class="v ${j.pnl>0?'vx-pos':j.pnl<0?'vx-neg':''}">${j.result||''} ${j.pnl!==undefined&&j.pnl!==''?VX.fmt.num(j.pnl):''}</span></div>`).join('')
      :VX.states.emptyDesk('Aucune entrée de journal sur ce titre.'))
    +`<div class="vx-meta vx-mt2"><a href="/journal?view=journal&sym=${SYM}">Journal complet →</a></div>`);
  paintBadges();paintThesis();
  try{loadAnalyst();}catch(e){}
}

/* Analystes PROFONDS (à la demande) : révisions BPA, surprises, notes, détention, initiés.
   Enrichit Catalyseurs + Sentiment sans bloquer le dossier principal. */
async function loadAnalyst(essai){
  essai=essai||0;
  let a=null;
  /* Le serveur ne fait plus de réseau dans la requête : EN_COURS = collecte
     lancée en fond → réessai borné (3) après `retry_s`, hors cache client.
     La page supplantée (VX.page._gen) ne repeint pas. */
  try{a=await VX.fetch('/api/analyst/'+SYM,{ttl:essai?0:600000});}catch(e){}
  if(a&&a.etat==='EN_COURS'){
    if(essai<3)setTimeout(function(){
      if(window.VX&&VX.page&&VX.page._gen!==_g)return;
      loadAnalyst(essai+1);
    },((a.retry_s||6)*1000));
    return;
  }
  if(!a||a.demo||a.error||a.available===false)return;
  const $b=id=>document.querySelector('#'+id+' [data-body]');
  const price=(TICKER&&TICKER.detail&&TICKER.detail.price)||null;
  /* Catalyseurs : révisions BPA + surprises + notes datées */
  const er=a.eps_revisions, su=a.surprises, sm=su&&su.summary, ra=a.ratings_actions, et=a.eps_trend;
  let cat='';
  if(su&&su.next)cat+=kv('Prochains résultats (est.)',su.next);
  if(sm)cat+=kv('Surprises BPA',`battu ${sm.beats}/${sm.total} trim.`+(sm.avg!=null?` · moy. ${sm.avg>=0?'+':''}${sm.avg}%`:''),(sm.beats>=sm.total*0.7?'vx-pos':sm.beats<=sm.total*0.4?'vx-neg':''));
  if(er&&er.net30!=null)cat+=kv('Révisions BPA (30j)',`${er.up30||0} ↑ / ${er.down30||0} ↓`+(et&&et.revision_pct_90d!=null?` · estim. ${et.revision_pct_90d>=0?'+':''}${et.revision_pct_90d}% /90j`:''),(er.trend==='up'?'vx-pos':er.trend==='down'?'vx-neg':''));
  if(a.growth_fwd!=null)cat+=kv('Croissance BPA attendue',`${a.growth_fwd>=0?'+':''}${a.growth_fwd}%`);
  if(ra&&ra.length){
    cat+=`<div class="vx-meta vx-mt2" style="text-transform:uppercase;letter-spacing:.04em">Notes récentes</div>`;
    cat+=ra.slice(0,4).map(function(r){
      const s=(r.pt_action||'')+' '+(r.to||'');
      const dir=/rais|upgrade|overweight|\bbuy\b|outperform/i.test(s)?'vx-pos':/low|cut|downgrade|underweight|\bsell\b|reduce/i.test(s)?'vx-neg':'';
      const tgt=r.target?` → ${VX.fmt.price(r.target)}`+(r.prior&&r.prior!==r.target?` (av. ${VX.fmt.price(r.prior)})`:''):'';
      return `<div class="vx-kv"><span class="k">${esc(r.date)} · ${esc(r.firm)}</span><span class="v ${dir}">${esc(r.to||r.pt_action||r.action)}${tgt}</span></div>`;
    }).join('');
  }
  if(cat&&a.stale)cat+=`<div class="vx-meta vx-mt1">Données analystes périmées (&gt; 12 h), rafraîchissement en cours.</div>`;
  if(cat)analystAjout('an-catalysts',cat);
  /* Sentiment : détention institutionnelle (13F) + initiés */
  let sen='';
  if(a.holders&&a.holders.length){
    sen+=`<div class="vx-meta vx-mt2" style="text-transform:uppercase;letter-spacing:.04em">Top détenteurs (13F)</div>`;
    sen+=a.holders.slice(0,5).map(function(h){
      return `<div class="vx-kv"><span class="k">${esc(h.holder)}</span><span class="v">${h.pct!=null?(h.pct*100).toFixed(1)+' %':'—'}${h.change?` <span class="${h.change>0?'vx-pos':'vx-neg'}">(${h.change>0?'+':''}${(h.change*100).toFixed(0)}%)</span>`:''}</span></div>`;
    }).join('');
  }
  if(a.insider){const ib=a.insider;
    sen+=kv('Initiés (récent)',`${ib.buys} achat(s) / ${ib.sells} vente(s)`,(ib.bias==='buy'?'vx-pos':ib.bias==='sell'?'vx-neg':''));
  }
  if(sen)analystAjout('an-sentiment',sen);
}
/* Ajout IDEMPOTENT : le corps de la carte est réécrit par loadDossier (rafraîchissement
   180 s, deuxième passage du routeur) ; l'ancien `innerHTML+=` s'empilait ou
   disparaissait selon l'ordre. Mesuré : bloc peint à 1 s, effacé à 2 s. */
function analystAjout(id,html){
  const el=document.querySelector('#'+id+' [data-body]');if(!el)return;
  el.querySelectorAll('[data-analyst]').forEach(n=>n.remove());
  el.insertAdjacentHTML('beforeend',`<div class="vx-mt2" data-analyst style="border-top:1px solid var(--vx-border,#30292B);padding-top:8px">${html}</div>`);
}
/* ── Carte-Verdict + Carte-Scénario + Raisonnement du comité (decision stack) ── */
/* DecisionTrace du dossier : Donnée → Moteur → Décision → Portefeuille.
   N'ÉCRIT QUE du texte et un ton dans des nœuds déjà rendus par vx2 ; aucun
   balisage n'est fabriqué ici, et aucune valeur n'est dérivée : chaque nœud
   lit ce que le moteur a rendu. Un nœud sans donnée reste à « — » en gris. */
function paintTrace(dec){
  const set=(id,val,meta,tone)=>{
    const n=$(id); if(!n)return;
    n.setAttribute('data-tone',tone||'neutral');
    const v=n.querySelector('.vx2-trace-value'), m=n.querySelector('.vx2-trace-meta');
    if(v)v.textContent=(val===null||val===undefined||val==='')?'\u2014':String(val);
    if(m)m.textContent=meta||'';
  };
  const TONE={green:'positive',red:'negative',amber:'caution',orange:'caution',gray:'neutral'};

  /* Donnée : prix réel + qualité du dossier, telle que le moteur la note. */
  const px=(TICKER&&TICKER.detail&&TICKER.detail.price!=null)?VX.fmt.price(TICKER.detail.price):null;
  const dq=dec&&dec.data_quality&&dec.data_quality.grade?('qualit\u00e9 '+dec.data_quality.grade):null;
  const mode=(typeof demoState==='function'&&demoState())?'d\u00e9mo':'diff\u00e9r\u00e9e';
  set('an-trace-donnee',px,dq?(dq+' \u00b7 '+mode):mode,px?'neutral':'missing');

  /* Moteur : confiance, telle qu'il la rend. Aucun seuil décidé ici. */
  const conf=(dec&&dec.confidence!=null)?dec.confidence:null;
  set('an-trace-moteur',conf!=null?(conf+'/100'):null,
      dec&&dec.grade?('note '+dec.grade):'confiance moteur',
      conf!=null?'neutral':'missing');

  /* Décision : le verdict canonique, avec le ton que le moteur lui donne. */
  if(dec&&dec.final_decision==='DATA_INSUFFICIENT'){
    set('an-trace-decision','Vertex ne tranche pas','donn\u00e9es insuffisantes','caution');
  }else{
    set('an-trace-decision',(dec&&(dec.decision_label||dec.final_decision))||null,
        dec&&dec.vehicle?('v\u00e9hicule '+dec.vehicle):'verdict canonique',
        TONE[(dec&&dec.decision_tone)||'gray']||'neutral');
  }

  /* Portefeuille : le titre est-il déjà détenu ? Compte de positions réelles. */
  let pos=[];try{pos=(window.VXEntities?window.VXEntities.positions():[])||[];}catch(e){}
  const detenu=pos.filter(t=>String(t.sym||'').toUpperCase()===SYM);
  if(!pos.length){set('an-trace-portefeuille','Aucune position','rien \u00e0 confronter','missing');}
  else if(detenu.length){set('an-trace-portefeuille','D\u00e9j\u00e0 d\u00e9tenu',
      detenu.length+(detenu.length>1?' lignes':' ligne'),'caution');}
  else{set('an-trace-portefeuille','Non d\u00e9tenu',pos.length+' positions ailleurs','neutral');}
}

function pctRet(entry,tgt){if(entry==null||tgt==null||!entry)return null;return (tgt-entry)/entry*100;}
async function loadDecisionStack(){
  let dec=null;
  try{dec=await VX.fetch('/api/decision/'+SYM,{ttl:60000});}catch(e){}
  paintTrace(dec);
  const V=$('an-verdict'),SC=$('an-scenarios'),CO=$('an-committee');
  if(!dec){if(V)V.innerHTML='<div class="vx-card">'+VX.states.error('Décision indisponible')+'</div>';return;}
  /* DATA_INSUFFICIENT → état honnête, aucune conviction. */
  if(dec.final_decision==='DATA_INSUFFICIENT'){
    const miss=(dec.data_quality&&(dec.data_quality.missing_fields||[]).join(', '))||'données du titre absentes';
    if(V)V.innerHTML='<section class="vx-card vx-verdict-card" data-tone="gray">'
      +'<div class="vx-verdict-head"><span class="vx-verdict-label">Données insuffisantes</span>'
      +'<span class="vx-verdict-score">confiance 0</span></div>'
      +'<div class="vx-insufficient"><div class="vx-insufficient-icon">&mdash;</div>'
      +'<div><b>Vertex ne tranche pas '+esc(SYM)+'.</b>'
      +'<div class="vx-insufficient-why">Données insuffisantes ('+esc(miss)+'). Aucune conviction affichée tant que le dossier n\'est pas complet.</div></div></div>'
      +'<div class="vx-mt3"><a class="vx-btn vx-btn-soft" href="/system?view=data">Prochaine action : vérifier les données →</a></div></section>';
    if(SC)SC.innerHTML='';if(CO)CO.innerHTML='';
    return;
  }
  DEC=dec;paintThesis();   // le brouillon de thèse se nourrit du dossier réel
  const tone=dec.decision_tone||'gray';
  const conf=(dec.confidence!=null)?dec.confidence:null;
  const entry=dec.entry,inval=dec.invalidation!=null?dec.invalidation:dec.stop;
  const tgts=dec.targets||{};
  const dq=(dec.data_quality&&dec.data_quality.grade)?('données '+dec.data_quality.grade):'';
  const cell=(k,v,id)=>'<div class="vx-verdict-cell"><span class="k">'+k+'</span><span class="v"'
    +(id?' id="'+id+'"':'')+'>'+v+'</span></div>';
  if(V)V.innerHTML='<section class="vx-card vx-verdict-card" data-tone="'+esc(tone)+'">'
    +'<div class="vx-verdict-head"><span class="vx-verdict-label">'+esc(dec.decision_label||dec.final_decision)+'</span>'
    +(dec.grade?'<span class="vx-badge">'+esc(dec.grade)+'</span>':'')
    +(conf!=null?'<span class="vx-verdict-score">confiance '+conf+'/100</span>':'')
    +'<span class="vx-actions">'+('<span class="vx-freshness" data-live="'+(demoState()?'fallback':'delayed')+'"><span class="vx-live-dot"></span>'+(demoState()?'Démo':'Différé')+'</span>')+'</span></div>'
    +'<div class="vx-verdict-grid">'
    +cell('Prix',(TICKER&&TICKER.detail&&TICKER.detail.price!=null)?VX.fmt.price(TICKER.detail.price):'n/d','an-verdict-price')
    +cell('Entrée',entry!=null?VX.fmt.price(entry):'—')
    +cell('Invalidation',inval!=null?VX.fmt.price(inval):'—')
    +cell('Conviction',dec.conviction!=null?dec.conviction:'—')
    +cell('Véhicule',esc(dec.vehicle||'—'))
    +(dq?cell('Qualité',esc(dq)):'')
    +'</div>'
    +'<div class="vx-mt3 vx-flex vx-wrap vx-gap2">'
    +'<a class="vx-btn vx-btn-primary" href="#an-scenarios">Voir les scénarios ↓</a>'
    +'<button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal(\''+SYM+'\',\'alert\')">Alerte sur l\'invalidation</button>'
    +'<button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal(\''+SYM+'\',\'note\')">Journaliser l\'hypothèse</button></div>'
    +'</section>';
  /* Carte-Scénario : pessimiste / probable / exceptionnel dérivés du plan réel
     (entrée → invalidation / cibles). Aucune probabilité inventée. */
  if(SC){
    const rDown=pctRet(entry,inval),rBase=pctRet(entry,tgts.tp1!=null?tgts.tp1:tgts.tp2),rUp=pctRet(entry,tgts.tp3!=null?tgts.tp3:tgts.tp2);
    const asym=(rDown!=null&&rUp!=null&&rDown!==0)?Math.abs(rUp/rDown):null;
    const scen=(kind,k,tgt,ret,note)=>'<div class="vx-scenario" data-kind="'+kind+'"><span class="vx-scenario-k">'+k+'</span>'
      +'<span class="vx-scenario-v">'+(ret!=null?(ret>0?'+':'')+ret.toFixed(1)+' %':'—')+'</span>'
      +'<span class="vx-scenario-note">'+(tgt!=null?'cible '+VX.fmt.price(tgt):'cible n/d')+(note?' · '+note:'')+'</span></div>';
    if(entry!=null&&(inval!=null||tgts.tp1!=null)){
      SC.innerHTML='<section class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Scénarios</span>'
        +'<span class="vx-chart-question">Combien puis-je perdre, gagner probablement, gagner exceptionnellement ?</span></div>'
        +'<div class="vx-scenario-grid">'
        +scen('down','Pessimiste',inval,rDown,'invalidation')
        +scen('base','Probable',tgts.tp1!=null?tgts.tp1:tgts.tp2,rBase,'cible 1')
        +scen('up','Exceptionnel',tgts.tp3!=null?tgts.tp3:tgts.tp2,rUp,'cible étendue')
        +'</div>'
        +(asym!=null?'<div class="vx-kv vx-mt2"><span class="k">Asymétrie (gain exceptionnel / perte max)</span><span class="v vx-mono '+(asym>=2?'vx-pos':asym>=1?'':'vx-neg')+'">'+asym.toFixed(1)+'×</span></div>':'')
        +'<div class="vx-card-foot"><span class="vx-meta">Scénarios dérivés du plan de niveaux moteur (entrée/invalidation/cibles) — aucune probabilité inventée.</span></div></section>';
    }else{SC.innerHTML='<div class="vx-card">'+VX.states.empty('Plan de niveaux insuffisant pour construire les scénarios.')+'</div>';}
  }
  /* Raisonnement du comité (intégré depuis Intelligence). L'accord chiffré
     seul (« accord 6/100 ») était cryptique : il est traduit en langage
     humain (faible / moyen / fort) et expliqué quand les moteurs divergent. */
  if(CO){
    const com=dec.committee||{};
    const pros=(dec.pros||[]).slice(0,4),cons=(dec.cons||[]).slice(0,4),unk=(dec.unknowns||[]).slice(0,3);
    const ag=com.agreement;
    const agBadge=ag==null?'':('<span class="vx-actions"><span class="vx-badge '
      +(ag>=70?'vx-pos':ag>=40?'':'vx-neg')+'" title="Convergence des moteurs entre eux (0–100)">accord des moteurs : '
      +(ag>=70?'fort':ag>=40?'moyen':'faible')+' <span class="vx-mono">('+ag+'/100)</span></span></span>');
    const agNote=(ag!=null&&ag<40)
      ?' Accord faible : les moteurs se contredisent — la prudence du verdict vient de là.':'';
    CO.innerHTML='<section class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Raisonnement du comité</span>'
      +agBadge+'</div>'
      +(com.view?'<div class="vx-dim vx-mb2">Consensus : <b>'+esc(com.view)+'</b>'+(com.has_contradiction?' · <span class="vx-neg">contradictions internes exposées</span>':'')+'</div>':'')
      +'<div class="vx-grid">'
      +'<div class="vx-col-6"><div class="vx-meta vx-mb1">Facteurs positifs</div>'+(pros.length?pros.map(p=>'<div class="vx-pos" style="font-size:12px">+ '+esc(p)+'</div>').join(''):'<span class="vx-muted">—</span>')+'</div>'
      +'<div class="vx-col-6"><div class="vx-meta vx-mb1">Facteurs négatifs</div>'+(cons.length?cons.map(c=>'<div class="vx-neg" style="font-size:12px">− '+esc(c)+'</div>').join(''):'<span class="vx-muted">—</span>')+'</div>'
      +'</div>'
      +(com.devils_advocate?'<div class="vx-insight vx-mt2" data-tone="risk"><b>Avocat du diable</b><div class="vx-mt1">'+esc(com.devils_advocate)+'</div></div>':'')
      +(unk.length?'<div class="vx-kv vx-mt2"><span class="k">Ce que nous ne savons pas</span><span class="v vx-muted">'+unk.map(esc).join(' · ')+'</span></div>':'')
      +'<div class="vx-card-foot"><span class="vx-meta">Comité déterministe (decision stack) — l\'IA explique, ne décide jamais.'+agNote+'</span></div></section>';
  }
}
function demoState(){return !!(window.__vxStatus&&window.__vxStatus.demo);}
/* Copilote du titre : question libre → /api/copilot/ask ancré sur SYM (chiffres réels). */
(function(){
  const go=$('an-cp-go'),q=$('an-cp-q'),out=$('an-cp-out');
  if(!go||!q||!out)return;
  function ask(){
    const question=(q.value||'').trim();
    if(!question){VX.toast&&VX.toast('Écris une question','warn');return;}
    out.innerHTML='<div class="vx-empty">Le copilote analyse '+SYM+'…</div>';
    fetch('/api/copilot/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:question,symbol:SYM,
        avec_positions:!!($('an-cp-pos')&&$('an-cp-pos').checked)})})
      .then(r=>r.json()).then(d=>{
        if(!d.ok){out.innerHTML='<div class="vx-error-banner">'+esc(d.error||'réponse indisponible')+'</div>';return;}
        out.innerHTML='<div class="vx-insight" data-tone="action" style="white-space:pre-wrap;font-size:12.5px">'+esc(d.answer)+'</div>'
          +'<div class="vx-meta" style="margin-top:.3rem">'+esc(d.label||'')+'</div>';
      }).catch(e=>{out.innerHTML='<div class="vx-error-banner">Copilote injoignable : '+esc(e.message)+'</div>';});
  }
  go.addEventListener('click',ask);
  q.addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
})();
/* Ticket pré-trade : montant envisagé → 7 contrôles réels via /api/pretrade/check. */
(function(){
  const go=$('an-pt-go'),amt=$('an-pt-amt'),out=$('an-pt-out');
  if(!go||!amt||!out)return;
  const ICON={ok:'✓',attention:'⚠',defavorable:'✕',inconnu:'·'};
  const CLS={ok:'vx-pos',attention:'vx-warn',defavorable:'vx-neg',inconnu:'vx-muted'};
  function run(){
    const a=Number(amt.value);
    if(!(a>0)){VX.toast&&VX.toast('Montant envisagé requis','warn');return;}
    out.innerHTML='<div class="vx-empty">Vérification de '+SYM+'…</div>';
    fetch('/api/pretrade/check',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol:SYM,amount:a})})
      .then(r=>r.json()).then(d=>{
        const tone=d.tone==='ok'?'pos':d.tone==='ko'?'neg':'neutral';
        out.innerHTML='<div class="vx-flex vx-mb1" style="gap:.4rem;align-items:center">'
          +'<span class="vx-badge" data-tone="'+tone+'">'+esc(d.overall||'—')+'</span>'
          +'<span class="vx-meta">'+esc(d.symbol)+' · '+VX.fmt.num(d.amount,0)+'</span></div>'
          +'<ul style="margin:.2rem 0;padding-left:0;list-style:none;font-size:12.5px">'
          +(d.checks||[]).map(c=>'<li style="margin:.25rem 0"><span class="'+(CLS[c.status]||'vx-muted')+'" style="display:inline-block;width:16px">'+(ICON[c.status]||'·')+'</span><b>'+esc(c.label)+'</b> — '+esc(c.detail)+'</li>').join('')
          +'</ul><div class="vx-meta">'+esc(d.narrative||'')+'</div>';
      }).catch(e=>{out.innerHTML='<div class="vx-error-banner">Vérification impossible : '+esc(e.message)+'</div>';});
  }
  go.addEventListener('click',run);
  amt.addEventListener('keydown',e=>{if(e.key==='Enter')run();});
})();
async function loadAnomalies(){
  const host=$('an-anomaly');if(!host)return;
  try{
    const d=await VX.fetch('/api/anomalies/'+SYM,{ttl:120000});
    if(window.VXCharts&&VXCharts.anomalyScan)VXCharts.anomalyScan('an-anomaly',d);
    else host.innerHTML='<div class="vx-empty">Builder indisponible.</div>';
  }catch(e){host.innerHTML='<div class="vx-error-banner">Scanner injoignable : '+esc(e.message)+'</div>';}
}
/* Skyler — décision canonique : score /40 par blocs, hard gates, scénarios. */
async function loadSkyler(){
  const host=$('an-skyler');if(!host)return;
  try{
    const r=await VX.fetch('/api/skyler/'+SYM,{ttl:120000});
    const d=r&&r.decision;if(!d){host.innerHTML='<div class="vx-empty">Décision indisponible.</div>';return;}
    const tone=d.decision==='ACHETER'||d.decision==='RENFORCER'?'pos'
      :d.decision==='REFUSER'||d.decision==='REDUIRE'?'neg':'neutral';
    const sc=d.score||{},blocks=sc.blocks||{};
    const LBL={fundamentals_quality:'Fondamentaux',catalysts:'Catalyseurs',
      technical_timing:'Technique',institutions_flow_anomalies:'Flux/anomalies',
      market_regime_sector:'Régime',asymmetry_scenarios:'Asymétrie',
      options_quality:'Option',data_quality:'Données'};
    const chips=Object.keys(LBL).filter(k=>blocks[k]).map(k=>{
      const b=blocks[k];const cls=b.status==='INSUFFICIENT'?'vx-muted':(b.points>=b.max*0.66?'vx-pos':'vx-warn');
      return '<span class="vx-badge" data-tone="neutral" title="'+esc(b.basis||'')+'" style="margin:.12rem .2rem .12rem 0"><span class="'+cls+'">'+esc(LBL[k])+' '+b.points+'/'+b.max+'</span></span>';
    }).join('');
    const gates=(d.gates||[]).filter(g=>g.triggered===true);
    const unknown=(d.gates||[]).filter(g=>g.triggered===null).length;
    const sn=d.scenarios||{};
    const row=(s,lab)=>s?'<li style="margin:.2rem 0"><b>'+lab+'</b> — cible '+VX.fmt.num(s.target,2)
      +' ('+(s.return_pct>0?'+':'')+s.return_pct+' %) · probabilité : non calibrée</li>':'';
    host.innerHTML='<div class="vx-flex vx-mb1" style="gap:.45rem;align-items:center;flex-wrap:wrap">'
      +'<span class="vx-badge" data-tone="'+tone+'">'+esc(d.decision||'—')+'</span>'
      +'<b>'+(sc.total??'—')+'/40</b><span class="vx-meta">niveau '+esc(d.level||'—')
      +(d.capped_by_gate?' · plafonnée par '+esc(d.capped_by_gate):'')+'</span></div>'
      +'<div class="vx-mb1">'+chips+'</div>'
      +(gates.length?'<div class="vx-mb1">'+gates.map(g=>'<div class="vx-neg" style="font-size:12.5px">✕ '+esc(g.id)+' — '+esc(g.reason)+'</div>').join('')+'</div>':'')
      +(sn.available?'<ul style="margin:.2rem 0;padding-left:0;list-style:none;font-size:12.5px">'
        +row(sn.bear,'Pessimiste')+row(sn.base,'Probable')+row(sn.bull,'Exceptionnel')+'</ul>':'')
      +'<div class="vx-meta" style="margin-top:.3rem">'
      +(d.catalyst?'Catalyseur : '+esc(d.catalyst)+' · ':'')
      +(d.invalidation!=null?'Invalidation : '+VX.fmt.num(d.invalidation,2)+' · ':'')
      +(d.max_risk_pct!=null?'Risque max : '+d.max_risk_pct+' % · ':'')
      +(unknown?unknown+' porte(s) non évaluable(s) · ':'')
      +'Objection : '+esc(d.strongest_objection||'—')+'</div>';
  }catch(e){host.innerHTML='<div class="vx-error-banner">Skyler injoignable : '+esc(e.message)+'</div>';}
}
/* Laboratoire d'évidence (X2) : stats ex post réelles après les spikes passés. */
async function loadEvidence(){
  const host=$('an-evidence');if(!host)return;
  try{
    const d=await VX.fetch('/api/evidence/'+SYM,{ttl:300000});
    if(!d||d.available===false){
      host.innerHTML='<div class="vx-empty">'+esc((d&&d.reason)||'évidence indisponible')+'.</div>';return;
    }
    if(!d.n_events){
      host.innerHTML='<div class="vx-empty">Aucun spike historique sur la fenêtre ('+d.points+' clôtures) — rien à mesurer, rien d\'inventé.</div>';return;
    }
    const fm=(v)=>v==null?'—':((v>0?'+':'')+v+' %');
    const cls=(v)=>v==null?'':v>0?'vx-pos':v<0?'vx-neg':'';
    const row=(lab,b)=>b.n_measured?'<tr><td data-label="Direction"><b>'+lab+'</b> <span class="vx-meta">×'+b.n_measured+'</span></td>'
      +'<td data-label="+1 barre" class="vx-num '+cls(b.median_fwd_1_pct)+'">'+fm(b.median_fwd_1_pct)+'</td>'
      +'<td data-label="+5 barres" class="vx-num '+cls(b.median_fwd_5_pct)+'">'+fm(b.median_fwd_5_pct)+'</td>'
      +'<td data-label="+10 barres" class="vx-num '+cls(b.median_fwd_10_pct)+'">'+fm(b.median_fwd_10_pct)+'</td>'
      +'<td data-label="MFE" class="vx-num vx-pos">'+fm(b.median_mfe_pct)+'</td>'
      +'<td data-label="MAE" class="vx-num vx-neg">'+fm(b.median_mae_pct)+'</td></tr>':'';
    host.innerHTML='<div class="vx-table-wrap"><table class="vx-table"><thead><tr>'
      +'<th>Après un spike…</th><th>+1 barre</th><th>+5 barres</th><th>+10 barres</th><th>MFE</th><th>MAE</th>'
      +'</tr></thead><tbody>'+row('haussier',d.up)+row('baissier',d.down)+'</tbody></table></div>'
      +'<div class="vx-meta" style="margin-top:.3rem">'+d.n_events+' spike(s) historique(s)'
      +(d.n_unmeasurable?' · '+d.n_unmeasurable+' trop récent(s) non mesurable(s)':'')
      +' · médianes exactes · '+esc(d.note||'')+'</div>';
  }catch(e){host.innerHTML='<div class="vx-error-banner">Évidence injoignable : '+esc(e.message)+'</div>';}
}
loadDossier();
loadDecisionStack();
loadAnomalies();
loadEvidence();
VX.refresh.register(loadEvidence,300000,'analysis-evidence');
loadSkyler();
VX.refresh.register(loadSkyler,300000,'analysis-skyler');
VX.refresh.register(loadAnomalies,300000,'analysis-anomaly');
VX.refresh.register(loadDossier,180000,'analysis');
VX.refresh.register(loadDecisionStack,180000,'analysis-decision');
})();
</script>
"""

_MOBILE_BAR = """
<div class="vx-mobile-bar"><nav aria-label="Actions rapides">
  <button onclick="VXEntities.toggleFavorite('%%SYM%%')">★<span>Favori</span></button>
  <button onclick="VXEntities.openAddModal('%%SYM%%','follow')">◎<span>Suivre</span></button>
  <button onclick="VXEntities.openAddModal('%%SYM%%','alert')">!<span>Alerte</span></button>
  <button onclick="location.href='/opportunities?view=options&sym=%%SYM%%'">◇<span>Options</span></button>
  <button data-entity-menu="%%SYM%%">⋯<span>Plus</span></button>
</nav></div>
"""


def _trace_dossier() -> str:
    """Squelette de la DecisionTrace du dossier — `analyse-hero`, deuxième des
    cinq emplacements canoniques.

    Le serveur ne connaît ici que le symbole : tout le dossier est chargé par
    le client. Il rend donc les quatre nœuds à `—` avec le ton « missing », et
    `paintTrace()` les complète depuis la décision réellement reçue. Aucun nœud
    ne part sur une valeur optimiste.

    Le balisage vient de `vx2` : une classe `.vx2-*` ne s'écrit que là.
    """
    from vertex.ui import vx2
    return vx2.decision_trace([
        {'label': 'Donnée', 'valeur': '—', 'meta': 'lecture du dossier…',
         'tone': 'missing', 'ident': 'an-trace-donnee'},
        {'label': 'Moteur', 'valeur': '—', 'meta': 'confiance —',
         'tone': 'missing', 'ident': 'an-trace-moteur'},
        {'label': 'Décision', 'valeur': '—', 'meta': 'verdict —',
         'tone': 'missing', 'ident': 'an-trace-decision'},
        {'label': 'Portefeuille', 'valeur': '—', 'meta': 'positions —',
         'tone': 'missing', 'ident': 'an-trace-portefeuille'},
    ], emplacement='analyse-hero')


def render(sym: str) -> str:
    sym = sym.upper()[:8]
    safe = ''.join(ch for ch in sym if ch.isalnum() or ch in '.-')
    content = ('<div class="vx-page-header"><div><p class="vx2-eyebrow">Explorer</p>'
               '<h1>' + safe + '</h1>'
               '<div class="vx-sub">Cette entreprise et cette opportunité '
               'méritent-elles du capital maintenant ?</div></div></div>'
               + _SECTIONS.replace('%%SYM%%', safe)
               .replace('%%TRACE%%', _trace_dossier())
               .replace('%%LOADING%%', '<div class="vx-skeleton" style="height:48px"></div>'))
    js = _JS.replace('%%SYM_JSON%%', json_for_script(safe))
    return render_shell(title=f'{safe} · Analyse', active='analysis',
                        space_label='Analyse', sub_label=safe, content=content,
                        page_js=js, page_label=f'Analyse {safe}',
                        mobile_actions=_MOBILE_BAR.replace('%%SYM%%', safe))
