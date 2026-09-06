"""vertex.ui.pages.portfolio_page — l'espace Portefeuille (§25, refonte PR n°5).

Mission unique : « Où mon capital est-il réellement exposé, et quelle position
exige une décision ? » — pas un inventaire, un instrument de décision.

Sous-vues (?view=) :
  team        → Synthèse (premier écran : Hero + 4 KPI + risque dominant + action)
  positions   → Tableau canonique (état de thèse, invalidation, catalyseur, action)
  performance → Performance de portefeuille (MIGRÉE depuis Journal — un seul domicile)
  risk        → Risque priorisé (moteur risk_engine — positions réelles)
  options     → Options command center (inchangé — refonte dédiée PR n°7)
  watchlist   → Surveillance active (watchlist + suivis + favoris)

INVARIANTS ABSOLUS (Constitution §17-22) :
  · IBKR strictement READONLY — AUCUN chemin d'exécution d'ordre, aucun bouton
    Acheter/Vendre/Renforcer. Toute « action » est ANALYTIQUE.
  · Jamais déduire « thèse cassée » d'une simple baisse de prix : seul le
    franchissement de l'invalidation (niveau pré-défini) casse une thèse (§18).
  · JAMAIS suggérer de renforcer une position perdante sans confirmation
    positive explicite du marché (§18) — garde-fou testé.
  · Les gagnants sont réévalués selon la thèse, jamais vendus par réflexe (§19).
  · Donnée absente → « n/d » honnête, jamais un zéro inventé. Source/unité/
    fraîcheur/état (live/delayed/stale/demo/offline) toujours affichés.
"""
from __future__ import annotations


from vertex.ui import vx2
from vertex.ui.shell import json_for_script, render_shell

# Ordre canonique de `navigation-and-pages.md` §8 : Synthèse, Positions,
# Allocation, Options, Risque, Thèses. `performance` reste en queue — sa
# migration vers /performance suppose de fusionner DEUX implémentations
# d'équité vivantes, ce qui déborde d'une refonte visuelle (consigné).
_VIEWS = (('team', 'Synthèse'), ('positions', 'Positions'),
          ('allocation', 'Allocation'), ('options', 'Options'),
          ('risk', 'Risque'), ('theses', 'Thèses'),
          ('performance', 'Performance'))

# `watchlist` était le nom de la sous-vue Thèses. L'URL reste valable : une
# adresse partagée hier ne doit pas tomber sur la Synthèse sans un mot.
_ALIAS = {'watchlist': 'theses'}


def _tabs(view: str) -> str:
    return vx2.tabs([{'label': label, 'href': f'/portfolio?view={v}',
                      'actif': v == view} for v, label in _VIEWS],
                    libelle='Sous-vues du portefeuille')


_CONTENT = """
%%HEADER%%
%%TABS%%
<div class="vx-grid vx-mt4" id="pf-summary" aria-label="Synthèse portefeuille"></div>
<div id="pf-body" class="vx-mt4">%%LOADING%%</div>
<style>
#vx-content .vx-cmd-strip{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}
@media (max-width:1100px){#vx-content .vx-cmd-strip{grid-template-columns:repeat(3,1fr)}}
@media (max-width:640px){#vx-content .vx-cmd-strip{grid-template-columns:repeat(2,1fr)}}
#vx-content .vx-cmd-k{padding:12px 14px;border-radius:12px;background:var(--vx-surface-0,#090c0a);
  border:1px solid var(--vx-border,#26221e);border-left:3px solid transparent}
#vx-content .vx-cmd-k[data-tone="pos"]{border-left-color:var(--vx-positive)}
#vx-content .vx-cmd-k[data-tone="neg"]{border-left-color:var(--vx-negative)}
#vx-content .vx-cmd-k-v{font:700 22px/1.15 var(--vx-font-mono,monospace);color:var(--vx-text-primary,#f1f5f1);font-variant-numeric:tabular-nums}
#vx-content .vx-cmd-k-l{font-size:11px;color:var(--vx-text-muted,#848d85);text-transform:uppercase;letter-spacing:.05em;margin-top:3px}
#vx-content .vx-cmd-k-s{font-size:11px;color:var(--vx-text-faint,#5d675f);margin-top:1px}
#vx-content .vx-poscard{background:var(--vx-surface-0,#090c0a);border:1px solid var(--vx-border,#26221e);
  border-radius:12px;padding:11px 13px;min-width:0;transition:border-color .15s,transform .15s}
#vx-content .vx-poscard:hover{border-color:var(--vx-brand);transform:translateY(-1px)}
</style>
"""

_JS = r"""
<script src="/static/vertex/js/charts/donut-chart.js" defer></script>
<script src="/static/vertex/js/charts/sparkline.js" defer></script>
<script src="/static/vertex/js/charts/equity-chart.js" defer></script>
<script src="/static/vertex/js/charts/drawdown-chart.js" defer></script>
<script src="/static/vertex/js/charts/heatmap.js" defer></script>
<script src="/static/vertex/js/charts/bar-chart.js" defer></script>
<script src="/static/vertex/js/charts/option-payoff.js" defer></script>
<script src="/static/vertex/js/charts/line-area-chart.js" defer></script>
<script src="/static/vertex/js/charts/heatmap.js" defer></script>
<script>
(function(){
'use strict';
const VIEW=%%VIEW%%;
const VX2_ALLOC_ABSENCES=%%ABSENCES%%;
const $=(id)=>document.getElementById(id);
const E=()=>window.VXEntities;
function esc(s){return String(s??'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));}
function kv(k,v,cls){return `<div class="vx-kv"><span class="k">${k}</span><span class="v ${cls||''}">${VX.fmt.nd(v)}</span></div>`;}
const toneCls=(t)=>({pos:'vx-pos',neg:'vx-neg',warn:'vx-warn',muted:'vx-muted'}[t]||'vx-muted');

async function quotesFor(pos){
  if(!pos.length)return{};
  try{
    /* Contrat serveur /api/pos-quotes : {positions:[{sym,exp,strike,right}]}
       → résultats indexés par clé composite 'SYM|exp|strike|RIGHT'. */
    const body=pos.map(t=>({sym:t.sym,exp:t.exp,strike:t.strike,right:t.right}));
    const r=await fetch('/api/pos-quotes',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({positions:body})});
    const d=await r.json();window.__pfLive=!!d.live;
    /* `fallback_used` est servi par /api/pos-quotes et n'était lu NULLE PART
       (constat 27) : le repli ACTION ne pose pas `delayed` sur la cote, si
       bien qu'un portefeuille valorisé au prix de scan s'annonçait
       « marques live/desk ». Un témoin de plus, aucun calcul de plus. */
    window.__pfFallback=!!d.fallback_used;
    //  L'instant ou la donnee EST ARRIVEE, pas celui ou on la dessine.
    //  Les pieds de carte affichaient `Date.now()` : ils promettaient
    //  « mis a jour maintenant » a chaque re-rendu, y compris dix minutes
    //  plus tard sur une charge qui n'avait pas bouge. Un age faux est
    //  pire qu'un age absent — il empeche de se mefier.
    window.__pfTs=(d.ts!=null?d.ts:null);
    const res=d.results||{};const byId={};
    pos.forEach(t=>{const key=[String(t.sym).toUpperCase(),t.exp||'',
      (t.strike!==null&&t.strike!==undefined)?t.strike:'',
      (t.right||'').toUpperCase()].join('|');
      if(res[key])byId[t.id]=res[key];});
    return byId;
  }catch(e){
    /* Rien mesuré : on efface les témoins au lieu de laisser ceux de l'appel
       précédent parler pour celui-ci (un état « live » périmé est un état faux).
       `__pfTs` faisait exception et le commentaire mentait donc sur lui-même :
       mesure du 06/09/2026 — après un /api/pos-quotes en échec, les neuf pieds
       du Portefeuille affichaient « Il y a N min », l'âge de la charge
       PRÉCÉDENTE, juste au-dessus de « provenance des marques non mesurée ».
       Un âge périmé est un âge faux : il éteint la méfiance au moment précis
       où elle est justifiée. Les trois témoins tombent ensemble. */
    window.__pfLive=null;window.__pfFallback=null;window.__pfTs=null;return{};}
}
/* Cause de l'ABSENCE de marque — mesurée, jamais devinée.
   Constat 25 du 06/09/2026 : la tuile P&L écrivait « IBKR hors ligne » en dur
   dans la branche `pl===null`, sans jamais tester l'état du courtier. Repro
   avec socket vivante (`live:true`, `ibkr_configure:true`, contrats absents du
   board) : l'écran envoyait vérifier TWS alors que la vraie cause était
   « contrat non coté ». `window.__pfLive` est posé par quotesFor() AVANT tout
   rendu ; `null` = non mesuré, et on se tait alors sur le courtier. */
function pfCauseMarques(sansMarque){
  /* `sansMarque===0` n'affirme plus « marques indisponibles » : les quatre
     appelants ne passent 0 que dans des cas où la cause est AUTRE (aucune
     position déclarée, module graphique absent), et la phrase désignait alors
     une panne de cotation qui n'existait pas. Branche gardée — elle ne ment
     plus, elle avoue. */
  const base=sansMarque>0?(sansMarque+' position(s) sans marque'):'cause non mesurée';
  return base+(window.__pfLive===false?' · IBKR hors ligne':'');
}
/* ── PROVENANCE ET MODE DES MARQUES : une seule autorité pour la page ──────
   Correctif du constat 27, second tour. `fallback_used` était bien LU (posé par
   quotesFor) mais consommé à DEUX endroits sur dix-sept ; les quinze autres
   pieds de carte lisaient encore le seul témoin `live` pour choisir à la fois
   leur étiquette de source et leur mode. Or /api/pos-quotes peut répondre
   `live:true` ET `fallback_used:true` en même temps (routes/desk.py :
   `fallback_used = bool(combles)`, combles = les ACTIONS comblées au prix de
   scan) : ces quinze pieds annonçaient « IBKR/desk · Live » au-dessus de prix
   de scan. `__pfLive===null` = jamais mesuré (fetch en échec) : on ne nomme
   alors ni source ni mode — updateIndicator n'écrit aucun mot pour ''. */
function pfSourceMarques(){
  if(window.__pfLive===null||window.__pfLive===undefined)return 'provenance des marques non mesurée';
  if(window.__pfFallback===true)return window.__pfLive===true?'IBKR/desk · repli scan utilisé':'desk (repli)';
  return window.__pfLive===true?'IBKR/desk':'desk (repli)';
}
function pfModeMarques(){
  if(window.__pfLive===null||window.__pfLive===undefined)return '';
  if(window.__pfFallback===true)return 'fallback';
  return window.__pfLive===true?'live':'fallback';
}
function enrich(pos,quotes){
  /* Schéma desk : t.cost = TOTAL investi. Cotes serveur : spot (actions,
     par action) · mark (options, PAR ACTION → ×100 par contrat). */
  return pos.map(t=>{
    const q=quotes[t.id]||{};
    const isOpt=t.type!=='STK';
    const mark=isOpt?(q.mark??q.last??null):(q.spot??q.mark??q.last??null);
    /* La PROVENANCE vient du serveur (fonction partagee) : la recalculer ici
       la ferait diverger au premier ajustement, et l'ecran annoncerait une
       origine que le calcul ne pratique plus. */
    const markSource=q.mark_source??null;
    const spreadPct=(typeof q.spread_pct==='number')?q.spread_pct:null;
    const underSpot=isOpt?(q.spot??null):null;
    const value=mark!==null?(isOpt?mark*100*t.qty:mark*t.qty):null;
    const invested=t.cost||0;
    const pl=value!==null&&invested?((value-invested)/invested*100):null;
    /* P&L latent ABSOLU : la carte « Contribution » l'attendait (t.plAbs) et
       personne ne le produisait — elle restait vide même avec des marques. */
    const plAbs=value!==null?(value-invested):null;
    /* `q.delayed` seul ratait le repli ACTION : celui-ci ne pose pas ce drapeau,
       il pose `mode:'DELAYED'` et `fallback_used:true` (cotation_unifiee
       .en_charge_client). Le différé redevient donc lisible POSITION PAR
       POSITION — le témoin de carte `__pfFallback` ne disait, lui, que « au
       moins une ». Règle partagée avec le Briefing : VX.quotes.differee. */
    return Object.assign({},t,{mark,underSpot,value,invested,pl,plAbs,delayed:VX.quotes.differee(q)});
  });
}
/* Trois conventions coexistent chez le courtier lui-meme et ne donnent pas le
   meme chiffre. Le libelle dit LAQUELLE a servi — sans lui, un prix affiche est
   un chiffre sans origine, et un ecart avec le releve du courtier reste
   inexplicable. Mesure du 24 aout 2026 sur URA : marche 3,50/4,30, marque 3,70
   (dernier echange), milieu 3,90, marque IBKR 3,8546. */
const MARQUE_LIB={DERNIER_ECHANGE:'dernier echange',MILIEU_FOURCHETTE:'milieu',
                  CLOTURE_VEILLE:'cloture veille',ABSENTE:''};
/* Au-dela, dernier echange, milieu et marque du courtier s'ecartent de
   plusieurs pour cent : un prix au centime promet alors une precision que la
   donnee n'a pas. */
const SPREAD_INCERTAIN=10;
function marqueNote(t){
  if(t.mark==null)return'';
  const lib=MARQUE_LIB[t.markSource]||'';
  const large=(t.spreadPct!=null&&t.spreadPct>=SPREAD_INCERTAIN);
  if(!lib&&!large)return'';
  const bits=[];
  if(lib)bits.push(lib);
  if(large)bits.push('marche large '+VX.fmt.pct(t.spreadPct,0,false));
  return '<div class="vx-meta'+(large?' vx-warn':'')+'">'+bits.join(' · ')+'</div>';
}
/* ═══ ÉTAT DE THÈSE — PORTÉ DEPUIS `main`, IL MANQUAIT ═══════════════════
   `thesisState(t)` était APPELÉE ici (bloc « positions à décision ») et
   définie NULLE PART : ni dans cette page, ni dans un fichier statique. Le
   bloc levait donc `ReferenceError` à chaque rendu — troisième nom fantôme
   de la refonte, après `_analyse_fp` et `_ANALYSE_MEMO`.

   Ce n'est pas qu'un plantage : c'est une RÈGLE DE GESTION qui ne
   s'appliquait plus. Six états honnêtes — dont « Données insuffisantes »,
   qui refuse de rendre un verdict sans marque — et surtout le garde-fou
   des perdants : une position en perte ne reçoit JAMAIS « renforcer » sans
   confirmation positive explicite. Aucune de ces actions n'exécute d'ordre.
   ═══════════════════════════════════════════════════════════════════════ */
/* Validation positive du marché : SEULE justification d'un renforcement (§18).
   Elle doit venir d'un fait explicite du snapshot d'entrée (breakout, résultats
   confirmés, revalidation) — JAMAIS d'une baisse de prix ni d'un P&L négatif. */
function hasPositiveConfirmation(t){
  const s=t.entrySnap||{};
  return !!(s.validated||s.breakout||s.confirmed||s.revalidated||s.thesis_improved);
}

/* État de thèse — six états honnêtes. La franchise de l'invalidation (niveau
   pré-défini AVANT l'entrée) casse la thèse ; une simple baisse ne la casse
   jamais (§18). Sans marque → « données insuffisantes » (jamais un verdict). */
function thesisState(t){
  const s=t.entrySnap||{};
  const stop=Number(s.stop);
  const hasStop=isFinite(stop)&&stop>0;
  const mark=(t.type!=='STK')?t.underSpot:t.mark;   /* option : niveau du sous-jacent */
  if(mark==null||mark===undefined)
    return {key:'insuffisant',label:'Données insuffisantes',tone:'muted'};
  if(hasStop&&mark<=stop)
    return {key:'cassee',label:'Cassée — invalidation atteinte',tone:'neg'};
  if(hasStop&&mark<=stop*1.04)
    return {key:'fragilisee',label:'Fragilisée — proche invalidation',tone:'warn'};
  if(hasPositiveConfirmation(t)&&t.pl!=null&&t.pl>0)
    return {key:'renforcee',label:'Renforcée par les faits',tone:'pos'};
  if(t.pl!=null&&t.pl>=0)
    return {key:'intacte',label:'Intacte',tone:'pos'};
  return {key:'surveiller',label:'À surveiller',tone:'muted'};
}

/* Gestion des gagnants — RÈGLES INDICATIVES uniquement (§19). Jamais une sortie
   automatique : « laisser courir » est la règle par défaut d'une thèse qui tient. */
function winnerRule(pl){
  if(pl==null||pl<20)return null;
  if(pl>=100)return 'Gain ≥ +100 % : sécuriser 25-50 % et laisser courir le reste (règle indicative).';
  if(pl>=75) return 'Gain ≥ +75 % : envisager de sécuriser une fraction, laisser courir le reste.';
  if(pl>=50) return 'Gain ≥ +50 % : relever le stop sous le prix, réévaluer la thèse (jamais vendre par réflexe).';
  if(pl>=30) return 'Gain ≥ +30 % : verrouiller le risque (stop au-dessus du prix moyen).';
  return 'Gain ≥ +20 % : trade validé — laisser courir tant que la thèse tient.';
}

/* Prochaine action ANALYTIQUE (§17-19). GARDE-FOU PERDANTS : une position en
   perte ne reçoit JAMAIS « renforcer » sans confirmation positive explicite —
   sinon message d'interdiction. Aucune de ces actions n'exécute d'ordre. */
function nextAction(t){
  const st=thesisState(t);
  if(st.key==='cassee')
    return {label:'Réévaluer la sortie — invalidation atteinte',tone:'neg'};
  if(st.key==='fragilisee')
    return {label:'Surveiller de près — thèse proche de l’invalidation',tone:'warn'};
  if(t.pl!=null&&t.pl<0){
    /* Perte SANS confirmation → renforcement formellement interdit (§18). */
    if(!hasPositiveConfirmation(t))
      return {label:'Renforcement interdit : aucune confirmation positive détectée',tone:'neg'};
    return {label:'Confirmation détectée — renforcement possible seulement après revue',tone:'muted'};
  }
  const wr=winnerRule(t.pl);
  if(wr)return {label:wr,tone:'pos'};
  return {label:'Conserver — thèse intacte, laisser courir',tone:'muted'};
}


/* Tiroir de detail d'une position option.
   APPELEE ET JAMAIS DEFINIE : chaque clic sur « analyser » d'une ligne option
   levait `ReferenceError`. L'API reelle du shell est `VX.shell.openDrawer`,
   deja employee par `options-structure.js` et `chart-core.js` ; c'est elle
   qu'on appelle, plutot que d'inventer un second tiroir.
   Lecture seule : ce tiroir DECRIT une position, il n'en prepare aucune. */
function openOptionDrawer(t){
  if(!t){return;}
  if(!(window.VX&&VX.shell&&VX.shell.openDrawer)){return;}
  const li=(k,v)=>'<div class="vx-kv"><span class="k">'+esc(k)+'</span>'
    +'<span class="v vx-mono">'+v+'</span></div>';
  const px=(v)=>(v==null?'n/d':VX.fmt.price(v));
  const dte=(t.exp?Math.round((new Date(t.exp)-Date.now())/86400000):null);
  const corps='<div class="vx-grid" style="grid-template-columns:1fr 1fr;gap:6px">'
    +li('Type',esc(t.type||'—'))
    +li('Strike',px(t.strike))
    +li('Echeance',esc(t.exp||'—')+(dte!=null?' ('+dte+' j)':''))
    +li('Quantite',(t.qty==null?'n/d':t.qty))
    +li('Cout',px(t.cost))
    +li('Marque',px(t.mark))
    +li('Valeur',px(t.value))
    +li('P&L',(t.pl==null?'n/d':VX.fmt.pct(t.pl,1)))
    +'</div>'+marqueNote(t)
    +'<div class="vx-card-footer">'
    +VX.updateIndicator(window.__pfTs||null,
        pfSourceMarques(),
        pfModeMarques())
    /*  Apostrophe française dans une chaîne JS : le piège du dépôt. On écrit
        « aucun ordre préparé » plutôt que « aucune préparation d'ordre » —
        contourner vaut mieux qu'échapper, un échappement se reperd. */
    +' · lecture seule — aucun ordre préparé</div>';
  VX.shell.openDrawer(esc(t.sym||'Position')+' · detail option',corps,
                      {variant:'summary'});
}

function roleOf(t){
  const snap=t.entrySnap||{};
  if(t.type!=='STK')return'Options tactiques';
  if((snap.score||0)>=78||(snap.verdict||'').includes('FORT'))return'Offensive';
  if(['XLU','XLP','BIL','SGOV','SHV','GLD'].includes(t.sym))return'Défense / gardien';
  return'Noyau';
}
/* Barres divergentes autour de 0 : attribution P&L par position (gagnants à droite,
   perdants à gauche). items:[{name,val}] où val = P&L en %. Données réelles. */
function divBars(items,opt){
  opt=opt||{};const fmt=opt.fmt||((v)=>VX.fmt.pct(v,1));
  const arr=(items||[]).filter(x=>x&&x.val!=null&&isFinite(x.val)).sort((a,b)=>b.val-a.val);
  if(!arr.length)return '';
  const mx=Math.max.apply(null,[1e-9].concat(arr.map(x=>Math.abs(x.val))));
  return '<div class="vx-divbars">'+arr.map(x=>{const pos=x.val>=0;const w=Math.max(2,Math.min(50,Math.abs(x.val)/mx*50));
    return `<div class="vx-divbar"><span class="db-name">${esc(x.name)}</span>`
      +`<span class="db-track"><i class="${pos?'pos':'neg'}" style="width:${w.toFixed(1)}%"></i></span>`
      +`<span class="db-val ${pos?'vx-pos':'vx-neg'}">${fmt(x.val)}</span></div>`;}).join('')+'</div>';
}
/* Greeks agrégés du portefeuille options : delta directionnel (émeraude/corail),
   theta = décroissance (corail si négatif). Note honnête si non estimés (IBKR requis). */
function greeksBlock(g){
  g=g||{};
  const has=g.delta!=null||g.gamma!=null||g.theta!=null||g.vega!=null;
  if(!has)return '<div class="vx-meta vx-mt2">Greeks broker requis — sans IBKR ni options ouvertes, non estimés (aucune invention).</div>';
  const row=(k,v,dec,tone)=>`<div class="vx-kv"><span class="k">${k} global</span><span class="v vx-mono ${tone||''}">${v==null?'—':VX.fmt.num(v,dec)}</span></div>`;
  return row('Delta',g.delta,3,g.delta>0?'vx-pos':g.delta<0?'vx-neg':'')
    +row('Gamma',g.gamma,4)
    +row('Theta',g.theta,3,g.theta<0?'vx-neg':'')
    +row('Vega',g.vega,3)
    +(g.open_options?`<div class="vx-meta vx-mt2">${g.open_options} option(s) ouverte(s)${g.greeks_partial?' · agrégat partiel (certaines jambes sans greeks)':''}</div>`:'');
}
/* Heatmap de corrélations du portefeuille (risk.correlations : pairs réels +
   symbols_covered). Couleur INVERSÉE vs défaut : haute corrélation = risque =
   corail ; décorrélé = émeraude. Vide honnête sans historique. */
function corrHeatmap(hostId,corr){
  const el=$(hostId);if(!el)return;
  const syms=(corr&&corr.symbols_covered)||[];const pairs=(corr&&corr.pairs)||{};
  if(syms.length<2||!Object.keys(pairs).length){
    /* PROMESSE MENSONGÈRE, mesurée le 06/09/2026 (constat 28 A). La carte
       écrivait en dur « … nécessitent un historique de prix (≥ 30 séances par
       titre, disponible avec le flux live) » et n'ouvrait JAMAIS `corr.reason`,
       que les deux routes servent pourtant :
         · /api/portfolio/team → « NON_IMPLÉMENTÉ sur /api/portfolio/team —
           cette route ne fournit aucune série de rendements au moteur ; les
           corrélations mesurées sont servies par /api/portfolio/context (vue
           Allocation) » ;
         · /api/portfolio/context → « séries datées insuffisantes pour au moins
           deux positions ».
       Aucune des deux causes n'est réparée par « le flux live » : la première
       est une capacité non branchée sur la route, la seconde un manque
       d'historique daté. La phrase envoyait donc le lecteur ouvrir TWS pour
       débloquer une carte que TWS ne débloque pas (invariant 8). La cause
       affichée est désormais celle que le moteur MESURE ; sans `reason` servi,
       on dit qu'aucune cause n'a été servie plutôt que d'en fabriquer une. */
    const cause=(corr&&corr.reason)?String(corr.reason)
      :'cause non servie par la route — corrélations indisponibles';
    el.className='vx-col-12';
    el.innerHTML='<div class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Corrélations du portefeuille</span></div>'
      +VX.states.empty('Corrélations indisponibles — '+esc(cause))+'</div>';
    return;
  }
  const raw=(a,b)=>a===b?1:((pairs[a+'/'+b]!=null)?pairs[a+'/'+b]:(pairs[b+'/'+a]!=null?pairs[b+'/'+a]:null));
  const rows=syms.map(a=>({label:a,cells:syms.map(b=>{const v=raw(a,b);
    return {value:(a===b||v==null)?null:-v,   // négation : haute corrélation → corail
            label:(v==null?'—':(+v).toFixed(2)),title:a+' / '+b+' : '+(v==null?'n/d':(+v).toFixed(2))};})}));
  VXCharts.heatmapCard(hostId,{title:'Corrélations du portefeuille',unit:'coefficient',
    question:'La diversification est-elle réelle ou illusoire ?',
    conclusion:(corr.average!=null?('corrélation moyenne '+(+corr.average).toFixed(2)):'')+(corr.warning?' — '+corr.warning:''),
    /* La matrice ne vient PAS des cotations de position : risk_engine la calcule
       sur l'historique de clôtures du scan (/api/risk → portfolio_risk.build sur
       scan_state['detail']). Le libellé « rendements réels / de repli » et le
       mode se déduisaient pourtant de `window.__pfLive`, un témoin de socket
       courtier qui ne dit rien de cet historique : une corrélation sur clôtures
       ne devient pas « Live » parce que TWS est ouvert. */
    /* HORODATAGE : `__pfTs` date la charge /api/pos-quotes, pas cette matrice.
       Mesuré le 06/09/2026 sur les deux appelants : /api/portfolio/team rend
       `risk.as_of` VIDE (le snapshot construit par la route n'en porte pas) et
       /api/portfolio/context rend `as_of: null` — aucune des deux ne date ses
       corrélations. Emprunter l'horloge des cotations donnait à une matrice
       calculée sur des clôtures la fraîcheur d'un appel de cotation. Sans
       horodatage servi, on l'avoue au lieu de l'emprunter. */
    columns:syms,rows:rows,min:-1,max:1,
    source:'risk_engine · corrélations sur l’historique du scan'
      +((corr&&corr.as_of)?'':' · horodatage non servi'),
    timestamp:(corr&&corr.as_of)||null,mode:(corr&&corr.as_of)?'delayed':'',
    limits:'corail = fortement corrélé (risque de concentration) · émeraude = décorrélé (diversification réelle)'});
}
/* Composition du capital : Actions / Options / Cash en barre empilée + légende.
   Valeur au marché si dispo, sinon au coût ; cash = capital déclaré. Réel. */
function compositionBar(rich){
  const stk=rich.filter(t=>t.type==='STK').reduce((s,t)=>s+(t.value??t.invested),0);
  const opt=rich.filter(t=>t.type!=='STK').reduce((s,t)=>s+(t.value??t.invested),0);
  const cash=E().capital()||0;const tot=stk+opt+cash;
  if(!tot)return '';
  const seg=(v,col)=>{const p=v/tot*100;return p>0?`<i style="width:${p.toFixed(1)}%;background:${col}"></i>`:'';};
  const leg=(l,v,col)=>`<span><i style="background:${col}"></i>${l} <b>${(v/tot*100).toFixed(0)}%</b> · ${VX.fmt.price(v)} $</span>`;
  const A='var(--vx-brand)',O='var(--vx-violet)',C='var(--vx-steel-3)';
  return `<div class="vx-mt3"><span class="vx-metric-k" style="display:block;margin-bottom:2px">Composition du capital</span>`
    +`<div class="vx-stackbar" role="img" aria-label="Actions ${(stk/tot*100).toFixed(0)}% Options ${(opt/tot*100).toFixed(0)}% Cash ${(cash/tot*100).toFixed(0)}%">`
    +seg(stk,A)+seg(opt,O)+seg(cash,C)+`</div>`
    +`<div class="vx-stackbar-legend">`+leg('Actions',stk,A)+leg('Options',opt,O)+leg('Cash',cash,C)+`</div></div>`;
}
/* Barres de poids par position (allocation réelle du moteur risk.weights) : cash
   inclus, surpondérations (risk.overweight) en ambre, repère au poids max. */
function weightBars(weights,overweight,maxW){
  maxW=maxW||15;
  const es=Object.keys(weights||{}).map(k=>({k:k==='_CASH'?'Cash':k,raw:k,v:+weights[k],
      cash:k==='_CASH',over:!!(overweight&&overweight[k]!=null)}))
    .filter(e=>isFinite(e.v)&&e.v>0).sort((a,b)=>b.v-a.v);
  if(!es.length)return '';
  const mx=Math.max.apply(null,[maxW*1.15].concat(es.map(e=>e.v)));
  return '<div class="vx-wbars">'+es.map(e=>`<div class="vx-wbar" data-tone="${e.cash?'cash':e.over?'over':''}">`
    +`<span class="wb-name">${esc(e.k)}${e.over?'<span class="wb-tag">surpondéré</span>':''}</span>`
    +`<span class="wb-track"><i style="width:${Math.max(2,Math.min(100,e.v/mx*100)).toFixed(0)}%"></i>`
    +`${e.cash?'':`<b style="left:${Math.min(100,maxW/mx*100).toFixed(0)}%"></b>`}</span>`
    +`<span class="wb-val">${e.v.toFixed(1)}%</span></div>`).join('')
    +`<div class="vx-meta vx-mt2">Repère corail = poids max ${maxW}% par position · Cash = liquidités.</div></div>`;
}
/* COCKPIT de synthèse : jauge « positions gagnantes » + gagnants/perdants +
   valeur/P&L/équipe/options en tuiles. Valeur au coût toujours calculable ;
   marques live si disponibles — jamais un chiffre inventé, l'étiquette dit
   ce qui est affiché ; jauge absente sans marques (honnête). */
function renderSummary(rich){
  const host=$('pf-summary');if(!host)return;
  if(!rich.length){host.innerHTML='';return;}
  const stocks=rich.filter(t=>t.type==='STK'),opts=rich.filter(t=>t.type!=='STK');
  const invested=rich.reduce((s,t)=>s+t.invested,0);
  const marked=rich.filter(t=>t.value!==null);
  const value=marked.length===rich.length?rich.reduce((s,t)=>s+t.value,0):null;
  const pl=value!==null&&invested?(value-invested):null;
  const winners=marked.filter(t=>t.pl>0).length,losers=marked.filter(t=>t.pl<0).length;
  const winPct=marked.length?Math.round(winners/marked.length*100):null;
  const gauge=(winPct!=null&&window.VXCharts&&VXCharts.scoreGaugeSVG)
    ?VXCharts.scoreGaugeSVG(winPct,{label:'positions gagnantes',size:92,stroke:8}):'';
  const wl=marked.length?`<div style="display:flex;height:9px;border-radius:99px;overflow:hidden;background:var(--vx-surface-0);margin-top:8px" role="img" aria-label="${winners} gagnantes contre ${losers} perdantes">
      <i style="width:${(winners/(marked.length||1)*100).toFixed(0)}%;background:var(--vx-positive)"></i>
      <i style="flex:1;background:var(--vx-negative)"></i></div>
    <div class="vx-meter-row" style="margin-top:5px"><span style="color:var(--vx-positive)">${winners} gagnante(s)</span><span style="color:var(--vx-negative)">${losers} perdante(s)</span></div>`:'';
  const tile=(label,val,sub,tone)=>`<div class="vx-stat" data-tone="${tone||''}">
    <div class="vx-stat-k">${label}</div><div class="vx-stat-v" style="font-size:19px">${val}</div>
    ${sub?`<div class="vx-stat-sub">${sub}</div>`:''}</div>`;
  /* Trois causes DISTINCTES d'un P&L absent (invariant 5) : marque manquante,
     coût déclaré nul, panne courtier. La ligne 382 les fusionnait toutes dans
     « IBKR hors ligne » — un fait sur le courtier que la page n'avait jamais
     mesuré. Vocabulaire déjà employé par pfCommandStrip (« marques indispo. »). */
  const sansMarque=rich.length-marked.length;
  /* `plSub` n'est LU que lorsque `pl===null` (tuile P&L latent). Or
     `pl = value!==null && invested ? … : null` : avec sansMarque===0, `value`
     n'est jamais nul, donc `pl===null` implique `!invested`. La troisième
     branche (`pfCauseMarques(0)` → « marques indisponibles ») était donc
     inatteignable, et elle aurait nommé une panne de cotation pour un
     portefeuille au coût déclaré nul. Deux causes réelles, deux branches. */
  const plSub=sansMarque>0?pfCauseMarques(sansMarque)
             :'coût déclaré nul — aucun pourcentage calculable';
  /* `delayed` seul ne suffit pas : le repli ACTION ne le porte pas (constat 27).
     `window.__pfFallback` vient du `fallback_used` servi par la route. */
  const differe=rich.some(t=>t.delayed)||window.__pfFallback===true;
  const marqueLib=differe?'marques différées (scan)'
                 :(window.__pfLive===true?'marques live/desk'
                   :window.__pfLive===false?'marques desk — IBKR hors ligne':'marques de provenance non mesurée');
  host.innerHTML=`<div class="vx-card vx-col-12 vx-card--premium">
    <div class="vx-scorecard" style="grid-template-columns:${gauge?'auto minmax(0,1fr)':'minmax(0,1fr)'}">
      ${gauge?`<div class="vx-gaugecluster" style="flex-direction:column">${gauge}</div>`:''}
      <div class="vx-scorecard-side">
        <div class="vx-statrow">
          ${tile('Valeur',value!==null?VX.fmt.price(value):VX.fmt.price(invested),value!==null?marqueLib:'au coût ('+pfCauseMarques(sansMarque)+')')}
          ${tile('P&L latent',pl!==null?((pl>=0?'+':'')+VX.fmt.price(pl)):'n/d',pl!==null?VX.fmt.pct(pl/invested*100,1)+(differe?' · différé':''):plSub,pl>0?'pos':pl<0?'neg':'')}
          ${tile('Équipe actions',stocks.length+' / 10',stocks.length>=10?'complet — remplacement obligatoire':'places disponibles')}
          ${tile('Options tactiques',opts.length+' / 3','CALLS '+opts.filter(t=>t.type==='CALL').length+' · PUTS '+opts.filter(t=>t.type==='PUT').length+' / 1 max')}
        </div>
        ${wl}
      </div>
    </div></div>`;
}

/* ── ÉQUIPE ── */
/* Bandeau COMMAND CENTER (§23) : valeur, P&L, gagnants/perdants, capital engagé,
   diversification RÉELLE du moteur de risque. Aucune valeur inventée. */
async function pfCommandStrip(rich){
  const host=$('pf-cmd-strip');if(!host)return;
  const invested=rich.reduce((s,t)=>s+(t.invested||0),0);
  const marked=rich.filter(t=>t.value!=null);
  const value=marked.length===rich.length&&rich.length?rich.reduce((s,t)=>s+t.value,0):null;
  const pl=value!=null&&invested?value-invested:null;
  const plPct=pl!=null&&invested?pl/invested*100:null;
  const winners=marked.filter(t=>t.pl>0).length,losers=marked.filter(t=>t.pl<0).length;
  const tone=(v)=>v>0?'pos':v<0?'neg':'';
  /* SECOND SITE DU CONSTAT 25, sur la même page. La sous-ligne du P&L écrivait
     « marques indispo. » dès que `plPct` était nul. Or
     `plPct = pl!=null && invested ? … : null` et `pl = value!=null && invested
     ? … : null` : avec `invested === 0` et TOUTES les positions marquées, la
     bande annonçait une panne de cotation alors qu'aucune marque ne manquait.
     C'est exactement le cas que `renderSummary` nomme « coût déclaré nul —
     aucun pourcentage calculable » (l. 448) ; les deux causes se disent
     désormais avec le même vocabulaire, ici comme là-bas. */
  const sansMarque=rich.length-marked.length;
  const plSub=plPct!=null?((plPct>0?'+':'')+VX.fmt.num(plPct,1)+' %')
             :(sansMarque>0?pfCauseMarques(sansMarque)
                           :'coût déclaré nul — aucun pourcentage calculable');
  let risk=null;try{const cmd=await VX.fetch('/api/command',{ttl:60000});risk=cmd&&cmd.risk;}catch(e){}
  const k=(label,val,sub,t)=>`<div class="vx-cmd-k" data-tone="${t||''}">
    <div class="vx-cmd-k-v">${val}</div><div class="vx-cmd-k-l">${label}</div>${sub?`<div class="vx-cmd-k-s">${sub}</div>`:''}</div>`;
  host.innerHTML=`<div class="vx-cmd-strip">
    ${k('Valeur',value!=null?VX.fmt.price(value)+' $':VX.fmt.price(invested)+' $',value!=null?'au marché':'au coût')}
    ${k('P&L latent',pl!=null?((pl>0?'+':'')+VX.fmt.price(pl)+' $'):'n/d',esc(plSub),tone(pl))}
    ${k('Gagnantes / perdantes',winners+' / '+losers,marked.length+' marquées',winners>=losers?'pos':'neg')}
    ${k('Capital engagé',VX.fmt.price(invested)+' $',rich.length+' position(s)')}
    ${k('Diversification',risk&&risk.diversification!=null?Math.round(risk.diversification)+' %':'—',risk&&risk.max_corr!=null?'corr. max '+VX.fmt.num(risk.max_corr,2):'',risk&&risk.diversification>=70?'pos':risk&&risk.diversification<45?'neg':'')}
    ${k('Nouveau risque',risk?(risk.no_new_risk?'BLOQUÉ':'autorisé'):'—',risk&&risk.max_sector_name?risk.max_sector_name+' '+Math.round(risk.max_sector||0)+' %':'',risk?(risk.no_new_risk?'neg':'pos'):'')}
  </div>`;
}
async function renderTeam(){
  const pos=E().positions();
  ($('pf-summary')||{}).innerHTML='';
  if(!pos.length){
    ($('pf-body')||{}).innerHTML=VX.states.emptyDesk(
      'Aucune position déclarée — le portefeuille répond « où suis-je exposé ? » '
      +'dès la première position. Les positions se déclarent dans Vertex — le compte courtier n\'est jamais lu.',
      '<button class="vx-btn vx-btn-sm vx-btn-primary" onclick="VXEntities.openAddModal(\'\',\'position\')">Déclarer une position</button>'
      +' <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/opportunities">Chercher des candidats →</a>');
    return;
  }
  const rich=enrich(pos,await quotesFor(pos));
  renderSummary(rich);
  const roles={'Offensive':[],'Noyau':[],'Défense / gardien':[],'Options tactiques':[]};
  rich.forEach(t=>roles[roleOf(t)].push(t));
  const totalValue=rich.reduce((s,t)=>s+(t.value??t.invested),0);
  const sub={'Offensive':'Attaquants','Noyau':'Milieux','Défense / gardien':'Défenseurs & gardien',
    'Options tactiques':'HORS équipe — jamais gardien (max 3)'};
  ($('pf-body')||{}).innerHTML=`<div id="pf-cmd-strip" class="vx-mb3"></div>
    <section class="vx-card vx-mb3" aria-label="Allocation du portefeuille">
      <div class="vx-chart-head"><span class="vx-chart-title">Allocation du portefeuille</span>
        <span class="vx-chart-question">Où est concentré le capital, et qui gagne/perd ?</span></div>
      <div id="pf-alloc-tree" style="height:260px"></div>
      ${compositionBar(rich)}
      <div class="vx-card-foot"><span class="vx-meta">Taille = poids (valeur au marché ou au coût) · couleur = P&amp;L latent quand il est connu (vert gagnant / rouge perdant), sinon concentration (rouge &gt; 25 % · ambre ≥ 15 % · vert en dessous). Positions déclarées, aucune valeur inventée.</span></div>
    </section>
    <div class="vx-grid">
    <div class="vx-col-8" id="pf-team-cols"></div>
    <div class="vx-col-4"><div id="pf-roles-donut"></div>
      <div class="vx-card vx-mt3"><div class="vx-card-header"><span class="vx-card-title">Places</span></div>
      ${kv('Composantes',rich.filter(t=>t.type==='STK').length+' / 10 max')}
      ${kv('Options ouvertes',rich.filter(t=>t.type!=='STK').length+' / 3 max',
        rich.filter(t=>t.type!=='STK').length>=3?'vx-warn':'')}
      ${kv('Règle','11e position = remplacement obligatoire')}
      <div id="pf-team-issues" class="vx-mt2"></div>
      <div class="vx-meta vx-mt2"><a href="/opportunities">Chercher des candidats →</a></div></div>
      <div class="vx-card vx-mt3" id="pf-contrib"><div class="vx-card-header"><span class="vx-card-title">Contributeurs</span></div>
      <div id="pf-contrib-body"></div></div></div></div>`;
  /* Attribution P&L par position en barres divergentes, en DOLLARS de contribution
     (value − investi) — « qui a bougé l'aiguille », pas le % qui exagère les petites
     lignes. Gagnants à droite, perdants à gauche. Repli honnête sans marque. */
  const withVal=rich.filter(t=>t.value!=null&&t.invested);
  const _pfx=(v)=>(v>=0?'+':'')+VX.fmt.price(v)+' $';
  pfCommandStrip(rich);
  /* Conformité de l’équipe : rôles & problèmes calculés par le moteur (team_view),
     surfacés honnêtement (chaînes du moteur, aucun chiffre inventé). */
  (async function(){
    try{
      let scanT=null;try{scanT=await VX.fetch('/scan',{ttl:300000});}catch(e){}
      const secOf=(s)=>{const d=scanT&&scanT.detail&&scanT.detail[s];return(d&&d.sector)||'';};
      const payload={positions:rich.filter(t=>t.type==='STK').map(t=>{const per=t.qty?t.cost/t.qty:t.cost;
        return {symbol:t.sym,quantity:t.qty,avg_cost:per,last_price:(t.mark!=null?t.mark:per),sector:secOf(t.sym)};}),
        option_positions:rich.filter(t=>t.type!=='STK').map(t=>({sym:t.sym,exp:t.exp,strike:t.strike,right:t.type,qty:t.qty})),
        cash:E().capital()||0,simulated:false};
      const r=await fetch('/api/portfolio/team',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const team=((await r.json())||{}).team||{};
      const issues=team.issues||[];
      const el=document.getElementById('pf-team-issues');if(!el)return;
      el.innerHTML=issues.length
        ?'<span class="vx-metric-k" style="display:block;margin-bottom:4px">Conformité de l’équipe</span>'
          +issues.map(x=>`<div class="vx-insight" data-tone="risk" style="margin-bottom:4px">${esc(typeof x==='string'?x:(x.message||x.label||x.issue||''))}</div>`).join('')
        :'<div class="vx-meta" style="color:var(--vx-positive)">✓ Composition d’équipe conforme.</div>';
    }catch(e){}
  })();
  ($('pf-contrib-body')||{}).innerHTML=withVal.length
    ?divBars(withVal.map(t=>({name:(t.sym+(t.type!=='STK'?' '+t.type:'')),val:(t.value-t.invested)})),{fmt:_pfx})
    :'<div class="vx-meta">'+pfCauseMarques(rich.filter(t=>t.value==null).length)+' — aucun P&L affiché plutôt qu’un chiffre inventé.</div>';
  ($('pf-team-cols')||{}).innerHTML=Object.entries(roles).map(([role,list])=>`
    <section class="vx-card vx-mb3" aria-label="${role}">
      <div class="vx-card-header"><span class="vx-card-title">${role}</span>
        <span class="vx-meta">${sub[role]}</span>
        <span class="vx-meta vx-right">${list.length} position(s)</span></div>
      ${list.length?'<div class="vx-grid-auto" style="margin-top:8px">'+list.map(t=>{
        const plCol=t.pl>0?'var(--vx-positive)':t.pl<0?'var(--vx-negative)':'var(--vx-stone)';
        const wgt=totalValue?(t.value??t.invested)/totalValue*100:null;
        const stop=t.entrySnap&&t.entrySnap.stop;
        return `<div class="vx-poscard" style="border-left:3px solid ${plCol}">
          <div class="vx-flex" style="justify-content:space-between;gap:6px;align-items:flex-start">
            <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" style="font-size:15px;padding-left:0;font-weight:700" data-open-analysis="${t.sym}">${t.sym}</button>
            <span class="vx-badge" ${t.type!=='STK'?'style="color:var(--vx-option)"':''}>${t.type}${t.strike?' '+t.strike:''}</span></div>
          <div class="vx-mono" style="font-size:21px;font-weight:700;color:${plCol};line-height:1.1;margin-top:3px">${t.pl!==null?((t.pl>0?'+':'')+VX.fmt.num(t.pl,1)+' %'):'n/d'}</div>
          <div class="vx-meta" style="margin-top:2px">${wgt!=null?'poids '+VX.fmt.num(wgt,1)+' %':'poids —'}${t.value!=null?' · '+VX.fmt.price(t.value)+' $':''}</div>
          ${stop!=null?`<div class="vx-meta">stop ${VX.fmt.nd(stop)}</div>`:''}
          ${(t.entrySnap&&t.entrySnap.thesis)||t.note?`<div class="vx-meta vx-truncate" style="margin-top:3px">${esc((t.entrySnap&&t.entrySnap.thesis)||t.note)}</div>`:''}
          <div class="vx-flex" style="justify-content:flex-end;gap:.3rem;margin-top:6px">
            <button class="vx-btn vx-btn-sm vx-btn-ghost" data-inspect="${t.sym}" title="Aperçu rapide">Aperçu</button>
            <button class="vx-btn vx-btn-sm vx-btn-ghost" data-open-analysis="${t.sym}">Analyser</button>
            <button class="vx-btn vx-btn-icon vx-btn-ghost" data-position-menu="${t.id}" aria-label="Actions position ${t.sym}">⋯</button></div>
        </div>`;}).join('')+'</div>':'<div class="vx-meta" style="padding:6px 0">— aucune position dans ce rôle —</div>'}
    </section>`).join('');
  /* Treemap d'allocation (§20 — remplace le donut seul) : taille = poids, couleur = P&L */
  /*  `plConnu` et `totalTree` étaient EMPLOYÉS quatre fois dans le bloc
      ci-dessous et déclarés NULLE PART. Trouvés en remettant le desk à zéro :
      c'est le chemin d'un utilisateur NEUF, celui qu'aucune session avec des
      positions n'exerce.

      `plConnu` : le P&L est-il connu pour au moins une ligne ? La treemap
      colore par P&L quand il l'est, et **par concentration** sinon — colorer
      par un P&L absent peindrait tout en neutre et ferait passer une donnée
      manquante pour un portefeuille à l'équilibre.

      `totalTree` : le total qui sert de dénominateur aux poids. Sans lui, le
      repli de concentration divisait par `undefined`.  */
  const plConnu=rich.some(t=>t.pl!=null);
  const totalTree=rich.reduce((a,t)=>a+Math.max(0,t.value??t.invested??0),0);
  if(window.VXCharts&&VXCharts.treemap){
    const cc=VXCharts.colors;const el=$('pf-alloc-tree');const w=(el&&el.clientWidth)||900;
    VXCharts.treemap(el,{width:w,height:260,unit:'$ investi',
      /* La carte hôte pose déjà la question (« Où est concentré le capital,
         et qui gagne/perd ? ») : la redire ici la doublerait. */
      source:pfSourceMarques(),timestamp:window.__pfTs||null,
      mode:pfModeMarques(),
      limits:'aire = capital engagé · couleur = P&L quand il est connu, sinon concentration (rouge > 25 %)',
      items:rich.map(t=>({label:t.sym,value:Math.max(1,t.value??t.invested??0),
        sub:(t.pl!=null?((t.pl>=0?'+':'')+VX.fmt.num(t.pl,1)+'%')
             :(plConnu?(t.type!=='STK'?t.type:'')
               :(totalTree>0?VX.fmt.num(Math.max(0,t.value??t.invested??0)/totalTree*100,0)+' %':''))),
        color:(plConnu
               ?(t.pl>0?cc.positive:t.pl<0?cc.negative:cc.neutral)
               :(function(){ /* repli concentration — repere ~15 % de ce fichier */
                   if(!(totalTree>0))return cc.neutral;
                   const w=Math.max(0,t.value??t.invested??0)/totalTree*100;
                   return w>25?cc.negative:(w>=15?cc.warning:cc.positive);})())})),
      fmt:(v)=>VX.fmt.price(v)});
  }

  /* Aperçu « positions à décision » — les plus urgentes (cassée/fragilisée/gagnants). */
  const urgent=rich.map(t=>({t,st:thesisState(t)}))
    .filter(x=>['cassee','fragilisee'].includes(x.st.key)||(x.t.pl!=null&&x.t.pl>=50))
    .slice(0,5);
  const dl=$('pf-decision-list');
  if(dl){
    if(!urgent.length){dl.innerHTML=VX.states.emptyDesk('Aucune position urgente — toutes les thèses sont intactes ou en surveillance normale.');}
    else{dl.innerHTML=urgent.map(x=>{const t=x.t,na=nextAction(t);
      return `<div class="vx-flex" style="padding:9px 0;border-bottom:1px dashed var(--vx-border-soft);gap:10px;align-items:center">
        <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${t.sym}">${t.sym}</button>
        <span class="vx-badge ${toneCls(x.st.tone)}">${esc(x.st.label)}</span>
        <span class="vx-num vx-mono ${t.pl>0?'vx-pos':t.pl<0?'vx-neg':'vx-muted'}">${t.pl!=null?VX.fmt.pct(t.pl,1):'n/d'}</span>
        <span class="vx-grow vx-truncate ${toneCls(na.tone)}" style="font-size:12.5px" title="${esc(na.label)}">${esc(na.label)}</span>
      </div>`;}).join('');}
  }
}

/* Diff « depuis ta dernière visite » (LOT H) — honnête, jamais fabriqué. */
function renderDiff(m,rich){
  const host=$('pf-diff');if(!host)return;
  let base=null;try{base=JSON.parse(localStorage.getItem('vxPortfolioBaseline')||'null');}catch(e){}
  const now=Date.now();
  const snapshot={ts:now,netValue:m.netValue,plAbs:m.plAbs,
    byPl:Object.fromEntries(rich.filter(t=>t.pl!=null).map(t=>[t.sym,t.pl]))};
  /* (Re)poser la référence : première fois, ou si > 12 h (une « visite » distincte),
     et uniquement avec des marques réelles pour éviter un delta trivial. */
  if(m.allMarked&&(!base||(now-(base.ts||0))>43200000)){
    try{localStorage.setItem('vxPortfolioBaseline',JSON.stringify(snapshot));}catch(e){}
  }
  if(!base||base.netValue==null){
    host.innerHTML=`<section class="vx-card vx-card--compact"><div class="vx-card-header">
      <span class="vx-card-title">Depuis ta dernière visite</span></div>
      <div class="vx-meta">Aucun historique de comparaison disponible — la référence se pose à cette visite.</div></section>`;
    return;
  }
  const dNet=(m.netValue!=null&&base.netValue!=null)?(m.netValue-base.netValue):null;
  const dPl=(m.plAbs!=null&&base.plAbs!=null)?(m.plAbs-base.plAbs):null;
  const movers=Object.keys(snapshot.byPl).filter(s=>base.byPl&&base.byPl[s]!=null)
    .map(s=>({s,d:snapshot.byPl[s]-base.byPl[s]})).filter(x=>Math.abs(x.d)>=0.5)
    .sort((a,b)=>Math.abs(b.d)-Math.abs(a.d)).slice(0,3);
  host.innerHTML=`<section class="vx-card vx-card--compact"><div class="vx-card-header">
    <span class="vx-card-title">Depuis ta dernière visite</span>
    <span class="vx-meta vx-right">réf. ${VX.fmt.ago(base.ts)}</span></div>
    <div class="vx-flex vx-wrap" style="gap:18px">
      <span>Valeur nette : <b class="${dNet>0?'vx-pos':dNet<0?'vx-neg':'vx-muted'}">${dNet!=null?((dNet>=0?'+':'')+VX.fmt.price(dNet)):'n/d'}</b></span>
      <span>P&L latent : <b class="${dPl>0?'vx-pos':dPl<0?'vx-neg':'vx-muted'}">${dPl!=null?((dPl>=0?'+':'')+VX.fmt.price(dPl)):'n/d'}</b></span>
      ${movers.length?'<span class="vx-meta">Bougé : '+movers.map(x=>esc(x.s)+' '+(x.d>=0?'+':'')+VX.fmt.num(x.d,1)+' pt').join(' · ')+'</span>':'<span class="vx-meta">Aucun mouvement notable</span>'}
    </div></section>`;
}

/* ═══ POSITIONS — TABLEAU CANONIQUE (LOT B/C/D) ═══ */
function actionListHtml(state){
  const pf=(state&&state.portfolio)||{};
  const rows=pf.positions_needing_action||[];
  if(!rows.length)return '';
  const pill=(pr)=>{const c={P0_CRITICAL:'var(--vx-negative)',P1_HIGH:'var(--vx-warning)'}[pr]||'var(--vx-text-muted)';
    return `<span class="vx-badge" style="color:${c}">${(pr||'').replace('_',' ')}</span>`;}
  return `<details class="vx-disclosure vx-mb3"><summary>Priorités avancées du moteur · ${rows.length}</summary>
    <section class="vx-card vx-mt2"><div class="vx-card-header">
    <span class="vx-card-title">Priorités du moteur (Position Intelligence)</span>
    <span class="vx-meta vx-right">P0 puis P1</span></div>
    <div class="vx-table-wrap vx-table-cards"><table class="vx-table"><thead><tr>
    <th>Priorité</th><th>Titre</th><th>Statut</th><th>Action analytique</th>
    <th>Verdict moteur</th><th class="vx-num">P&L</th></tr></thead><tbody>
    ${rows.map(r=>`<tr>
      <td data-label="Priorité">${pill(r.priority)}</td>
      <td data-label="Titre"><button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${r.symbol}">${r.symbol}</button></td>
      <td data-label="Statut">${esc((r.status||'').replace(/_/g,' '))}</td>
      <td data-label="Action"><b>${esc((r.action||'').replace(/_/g,' '))}</b></td>
      <td data-label="Verdict">${r.decision?`<span class="vx-badge vx-badge-decision" data-decision="${(r.decision||'').replace('É','E')}">${r.decision}</span>`:'—'}</td>
      <td data-label="P&L" class="vx-num ${r.pl_pct>0?'vx-pos':r.pl_pct<0?'vx-neg':''}">${r.pl_pct!=null?VX.fmt.pct(r.pl_pct,1):'n/d'}</td>
    </tr>`).join('')}</tbody></table></div>
    <div class="vx-card-footer">${VX.updateIndicator(state.updated_at,'Position Intelligence',state.live?'live':'fallback')}
    · verdicts moteur — aucune action n’exécute d’ordre</div></section></details>`;
}

async function renderPositions(){
  const pos=E().positions();
  const rich=enrich(pos,await quotesFor(pos));
  renderSummary(rich);
  if(!pos.length){
    ($('pf-body')||{}).innerHTML=VX.states.emptyDesk('Aucune position déclarée.',
      '<button class="vx-btn vx-btn-sm vx-btn-primary" onclick="VXEntities.openAddModal(\'\',\'position\')">Déclarer une position</button>');
    return;
  }
  /* Lot 2 — frontiere IBKR market-data-only : Vertex ne lit plus les
     positions du COMPTE courtier. Le portefeuille est celui que l'utilisateur
     declare ; IBKR ne sert plus qu'a coter. */
  let posState=null,alerts=null;
  try{posState=await VX.fetch('/api/positions/state',{ttl:30000});}catch(e){}
  const posById={};((posState&&posState.positions)||[]).forEach(p=>{posById[String(p.position_id)]=p;});
  const srcLabel=(s)=>({IBKR:'IBKR',MANUAL:'Manuelle',PAPER:'Paper',SIMULATED:'Simulation',IMPORTED:'Importée'}[s]||'Manuelle');
  const groups={Actions:rich.filter(t=>t.type==='STK'),Options:rich.filter(t=>t.type!=='STK')};
  ($('pf-body')||{}).innerHTML=
    (posState?actionListHtml(posState):'')
    +Object.entries(groups).map(([g,list])=>`
    <section class="vx-card vx-mb3"><div class="vx-card-header"><span class="vx-card-title">${g}</span>
      <span class="vx-meta vx-right">${list.length}</span></div>
    ${list.length?`<div class="vx-table-wrap vx-table-cards"><table class="vx-table"><thead><tr>
      <th>Titre</th><th>Source</th><th>Contrat</th><th class="vx-num">Qté</th><th class="vx-num">Coût</th>
      <th class="vx-num">Marque</th><th class="vx-num">P&L</th><th>Statut</th><th></th></tr></thead><tbody>
      ${list.map(t=>{const pi=posById[String(t.id)]||{};return `<tr>
        <td data-label="Titre"><span class="vx-ticker">${t.sym}</span> ${E().badges(t.sym)}</td>
        <td data-label="Source"><span class="vx-badge">${srcLabel(pi.source)}</span></td>
        <td data-label="Contrat">${t.type}${t.strike?' '+t.strike+' '+(t.exp||''):''}</td>
        <td data-label="Qté" class="vx-num">${t.qty}</td>
        <td data-label="Coût (total)" class="vx-num">${VX.fmt.price(t.cost)}</td>
        <td data-label="Marque" class="vx-num">${t.mark!==null?VX.fmt.price(t.mark):'n/d'}${marqueNote(t)}</td>
        <td data-label="P&L" class="vx-num">${t.pl!==null?`<span style="display:inline-flex;align-items:center;gap:7px;justify-content:flex-end"><span style="flex:0 0 38px;height:6px;border-radius:99px;background:var(--vx-surface-0);position:relative;overflow:hidden"><i style="position:absolute;left:0;top:0;bottom:0;width:${Math.max(4,Math.min(100,Math.abs(t.pl)*6)).toFixed(0)}%;background:${t.pl>0?'var(--vx-positive)':t.pl<0?'var(--vx-negative)':'var(--vx-steel-3)'};border-radius:99px"></i></span><b class="vx-mono ${t.pl>0?'vx-pos':t.pl<0?'vx-neg':''}" style="min-width:44px">${VX.fmt.pct(t.pl,1)}</b></span>`:'<span class="vx-muted">n/d</span>'}</td>
        <td data-label="Statut" class="vx-meta">${pi.lifecycle_status?esc(pi.lifecycle_status.replace(/_/g,' ')):'—'}</td>
        <td><div class="vx-row-actions">
          <button class="vx-btn vx-btn-sm vx-btn-ghost" data-open-analysis="${t.sym}">Analyse</button>
          <button class="vx-btn vx-btn-sm" data-close-pos="${t.id}">Clôturer</button>
          <button class="vx-btn vx-btn-icon vx-btn-ghost" data-position-menu="${t.id}" aria-label="Actions position ${t.sym}">⋯</button>
        </div></td></tr>`;}).join('')}</tbody></table></div>`
      :VX.states.empty('Aucune position '+g.toLowerCase()+'.')}
    </section>`).join('')
    +`<div class="vx-card-footer">${VX.updateIndicator(window.__pfTs||null,pfSourceMarques(),pfModeMarques())}
      · portefeuille déclaré dans Vertex — IBKR ne sert qu'à coter · lecture seule — aucun ordre</div>`;
}

/* ═══ PERFORMANCE (LOT G — migrée depuis Journal, domicile unique) ═══ */
function pfEquiteDerivee(closed){
  const cl=(closed||[]).filter(t=>t&&t.closed&&isFinite(Number(t.cost))&&isFinite(Number(t.exit)))
    .slice().sort((a,b)=>String(a.closed).localeCompare(String(b.closed)));
  if(cl.length<2)return [];
  const base=(E()&&E().capital&&E().capital())||0;
  let cum=base;const eq=[];
  cl.forEach(t=>{cum+=Number(t.exit)-Number(t.cost);eq.push({d:t.closed,v:Math.round(cum*100)/100});});
  return eq;
}
function pfTrades(){return (E()?E().journal():[]).filter(e=>(e.result==='WIN'||e.result==='LOSS')&&isFinite(Number(e.pnl)));}
async function renderPerformance(){
  const pos=E().positions();
  renderSummary(enrich(pos,await quotesFor(pos)));
  const closed=(E()?E().closedPositions():[])||[];
  /* Équité DÉRIVÉE des clôtures déclarées (exit − coût, cumulé, base = capital
     déclaré) : le stock `myTradesEquity` n'est alimenté par personne, la courbe
     restait vide à vie. Même règle que la page Performance. Arithmétique, réel. */
  const eq=pfEquiteDerivee(closed);
  ($('pf-body')||{}).innerHTML=`
    <div class="vx-insight vx-page-lead vx-mb3" role="note"><b>Performance de portefeuille — domicile unique.</b>
      Courbe cumulée, drawdown, contribution et saisonnalité vivent ici (migrées depuis Journal).
      Le Journal ne conserve que la méthode, la discipline, les erreurs et l’apprentissage.</div>
    <div class="vx-grid vx-hero-grid vx-mb3">
      <div class="vx-col-8" id="pf-perf-equity"></div>
      <aside class="vx-col-4 vx-insight-rail" id="pf-perf-drawdown"></aside>
    </div>
    <div class="vx-grid">
      <div class="vx-col-7" id="pf-perf-monthly"></div>
      <div class="vx-col-5" id="pf-perf-contrib"></div>
    </div>`;
  /* LOT 608 : `desk` a vrai quand le vide vient du BUREAU (journal, equite,
     clotures declarees) et non d un moteur — seul ce cas merite la mention
     « bureau non synchronise ». */
  const emptyCard=(host,reason,action,desk)=>{const el=$(host);if(el)el.innerHTML='<div class="vx-card">'+(desk?VX.states.emptyDesk(reason,action||''):VX.states.empty(reason,action||''))+'</div>';};
  const JOURNAL_ACTION='<a class="vx-btn vx-btn-sm" href="/journal?view=journal">Ouvrir le journal</a>';

  /* Courbe d'équité cumulée + drawdown (série des clôtures déclarées). */
  if(eq.length>=2&&window.VXCharts&&VXCharts.equityCard){
    const labels=eq.map(p=>p.d),values=eq.map(p=>Number(p.v));
    const up=values[values.length-1]>=values[0];
    VXCharts.equityCard('pf-perf-equity',{title:'Courbe d’équité (cumulée)',unit:'$',timeframe:eq.length+' points',
      question:'Le capital progresse-t-il régulièrement ?',
      conclusion:up?'Équité en progression sur la période.':'Équité en retrait sur la période.',
      labels,values,height:240,source:'clôtures déclarées (cumul exit − coût)',timestamp:window.__pfTs||null,mode:'delayed',
      explain:{shows:'La série d’équité issue de tes clôtures de positions.',
        why:'Une méthode saine produit une pente régulière, pas des à-coups.',
        confirm:'Nouveaux plus hauts avec drawdowns contenus.',invalidate:'Série de plus bas d’équité.'}});
    VXCharts.drawdownCard('pf-perf-drawdown',{title:'Drawdown depuis les pics',unit:'%',
      question:'Les pertes de portefeuille restent-elles contrôlées ?',
      conclusion:'Dérivé arithmétiquement de la courbe d’équité.',
      labels,values,height:240,source:'clôtures déclarées (cumul exit − coût)',timestamp:window.__pfTs||null,mode:'delayed',
      limits:'dérivé de la série déclarée — pas un indicateur de marché',
      explain:{shows:'L’écart en % entre l’équité et son dernier pic.',
        why:'La profondeur des drawdowns mesure la discipline de risque réelle.',
        confirm:'Drawdowns courts et peu profonds.',invalidate:'Drawdown qui s’aggrave.'}});
  }else{
    emptyCard('pf-perf-equity','Courbe d’équité indisponible — elle se construit au fil des clôtures de positions déclarées.',JOURNAL_ACTION,true);
    emptyCard('pf-perf-drawdown','Drawdown indisponible sans courbe d’équité.',null,true);
  }

  /* Saisonnalité mensuelle (période) — moyenne simple des % de clôture par mois. */
  const withPl=closed.filter(t=>t.pnl_pct!==undefined&&t.pnl_pct!==null&&t.closed);
  if(withPl.length>=3&&window.VXCharts&&VXCharts.heatmapCard){
    const byMonth={};
    withPl.forEach(t=>{const m2=String(t.closed).slice(0,7);(byMonth[m2]=byMonth[m2]||[]).push(Number(t.pnl_pct));});
    const months=Object.keys(byMonth).sort();
    const years=[...new Set(months.map(m2=>m2.slice(0,4)))];
    const MN=['01','02','03','04','05','06','07','08','09','10','11','12'];
    const ML=['J','F','M','A','M','J','J','A','S','O','N','D'];
    VXCharts.heatmapCard('pf-perf-monthly',{title:'P&L moyen par mois (clôtures)',unit:'%',
      question:'Y a-t-il des périodes de sur- ou sous-performance ?',
      conclusion:months.length+' mois avec clôtures · moyenne simple des % par trade.',columns:ML,
      rows:years.map(y=>({label:y,cells:MN.map(mm=>{const arr=byMonth[y+'-'+mm];
        return arr?{value:arr.reduce((a,b)=>a+b,0)/arr.length,title:arr.length+' clôture(s)'}:{value:null,label:'·'};})})),
      min:-8,max:8,fmt:(v)=>v===null?'·':VX.fmt.pct(v,1),
      source:'clôtures déclarées',timestamp:window.__pfTs||null,mode:'delayed',
      limits:'moyenne des % par trade — pas une performance composée'});
  }else{emptyCard('pf-perf-monthly','Saisonnalité disponible à partir de 3 clôtures datées.',JOURNAL_ACTION,true);}

  /* Contribution par position (positions ouvertes, P&L latent absolu). */
  const rich=enrich(pos,await quotesFor(pos));
  const withAbs=rich.filter(t=>t.plAbs!=null).sort((a,b)=>b.plAbs-a.plAbs);
  if(withAbs.length&&window.VXCharts&&VXCharts.card&&VXCharts.bars){
    VXCharts.card('pf-perf-contrib',{title:'Contribution au P&L (positions ouvertes)',unit:'$',
      question:'Qui porte le résultat latent ?',
      conclusion:withAbs[0].sym+' domine ('+((withAbs[0].plAbs>=0?'+':'')+VX.fmt.price(withAbs[0].plAbs))+').',
      height:Math.max(160,Math.min(300,withAbs.length*30)),source:pfSourceMarques(),
      timestamp:window.__pfTs||null,mode:pfModeMarques(),limits:'P&L latent absolu (valeur − coût)',
      render:(cv)=>VXCharts.bars(cv,withAbs.map(t=>t.sym),withAbs.map(t=>Math.round(t.plAbs)),
        {horizontal:true,colors:withAbs.map(t=>t.plAbs>=0?VXCharts.colors.positive:VXCharts.colors.negative),
         yFmt:(v)=>VX.fmt.price(v)})});
  }else{
    /* Le seul appelant qui pouvait vraiment passer 0 à `pfCauseMarques` :
       sans position déclarée (rich vide) ou sans module graphique chargé, le
       compte de positions sans marque vaut 0 et la carte annonçait pourtant
       « marques indisponibles » — une panne de cotation inventée pour un cas
       qui n'en est pas une. Trois causes, trois phrases. */
    const sansAbs=rich.filter(t=>t.plAbs==null).length;
    emptyCard('pf-perf-contrib',!rich.length
      ?'Contribution indisponible — aucune position ouverte déclarée.'
      :(sansAbs?('Contribution indisponible — '+pfCauseMarques(sansAbs)+'.')
              :'Contribution indisponible — module de graphiques non chargé.'));}
}

/* ═══ OPTIONS COMMAND CENTER (§19 — inchangé, refonte dédiée PR n°7) ═══ */
async function renderOptions(){
  /* LOT J — Portefeuille ne garde qu'un RÉSUMÉ d'exposition options ; le détail
     canonique (Greeks, échéances, payoff, scénarios, catalyseurs, invalidations,
     liquidité) vit dans l'espace Options → Mes positions. Un seul domicile (§6). */
  const pos=E().positions();
  const opts=pos.filter(t=>t.type!=='STK');
  const rich=enrich(opts,await quotesFor(opts));
  renderSummary(enrich(pos,await quotesFor(pos)));
  if(!opts.length){
    ($('pf-body')||{}).innerHTML=VX.states.emptyDesk(
      'Aucune position option — le sélecteur privilégie les CALLS (max 3, dont 1 PUT tactique).',
      '<a class="vx-btn vx-btn-sm vx-btn-primary" href="/opportunities?view=options">Chercher un contrat</a>'
      +' <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/options?view=structure">Analyser une structure →</a>');
    return;
  }
  const calls=rich.filter(t=>t.type==='CALL'),puts=rich.filter(t=>t.type==='PUT');
  const engaged=rich.reduce((s2,t)=>s2+t.invested,0);
  const marked=rich.filter(t=>t.value!==null);
  const plTot=marked.length===rich.length&&rich.length?rich.reduce((s2,t)=>s2+(t.value-t.invested),0):null;
  const dtes=rich.map(t=>t.exp?Math.round((new Date(t.exp)-Date.now())/86400000):null).filter(v=>v!==null);
  const dteAvg=dtes.length?Math.round(dtes.reduce((a,b)=>a+b,0)/dtes.length):null;
  const shortDte=rich.filter(t=>t.exp&&((new Date(t.exp)-Date.now())/86400000)<=7).length;
  const H=(l,v,d,cls)=>`<div class="vx-card vx-card--compact vx-kpi vx-col-3">
    <span class="vx-kpi-label">${l}</span><span class="vx-kpi-value" style="font-size:20px">${v}</span>
    ${d?`<span class="vx-kpi-delta ${cls||'vx-muted'}">${d}</span>`:''}</div>`;
  /* Greeks RÉELS du broker (modelGreeks IBKR persistés) — jamais estimés. Jambe non cotée → n/d honnête. */
  let og=null;try{og=await (await fetch('/api/portfolio/greeks',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({option_positions:rich.map(t=>({sym:t.sym,exp:t.exp,strike:t.strike,right:t.type,qty:t.qty}))})})).json();}catch(e){}
  const gCov=og?`${og.priced}/${og.open_options} jambe(s) cotée(s)${og.greeks_partial?' · partiel':''}`:'greeks broker requis (IBKR)';
  const gDelta=(og&&og.delta!=null)?((og.delta>0?'+':'')+VX.fmt.num(og.delta,0)):'n/d';
  const gTheta=(og&&og.theta!=null)?(VX.fmt.num(og.theta,0)+' $/j'):'n/d';
  const gVega=(og&&og.vega!=null)?('vega '+VX.fmt.num(og.vega,0)+' $/pt'):(og?'chaîne à charger':'IBKR requis');
  /* CONTAMINATION CROISÉE, mesurée : renderOptions appelle quotesFor(opts) PUIS
     quotesFor(pos) — les deux écrivent les MÊMES globales, si bien que
     `window.__pfFallback` reflétait ici le repli de TOUT le portefeuille. Une
     action valorisée au prix de scan collait donc « · différé » au P&L des
     OPTIONS, qui n'était pas concerné : le repli ACTION ne comble jamais un
     contrat (routes/desk.py refuse d'en dériver le prix). Le témoin par
     POSITION suffit — le repli OPTION, lui, pose `delayed` sur sa propre cote. */
  const plOptSub=plTot!==null
    ?VX.fmt.pct(plTot/engaged*100,1)+(rich.some(t=>t.delayed)?' · différé':'')
    :pfCauseMarques(rich.length-marked.length);
  ($('pf-body')||{}).innerHTML=
    `<div class="vx-grid vx-mb3">
      ${H('CALLS ouverts',calls.length,'direction principale (~90 %)')}
      ${H('PUTS tactiques',puts.length+' / 1',puts.length>1?'PLAFOND DÉPASSÉ':'rares, jamais « parce que ça baisse »',puts.length>1?'vx-neg':'')}
      ${H('Capital engagé',VX.fmt.price(engaged),'coût total déclaré')}
      ${H('P&L options',plTot!==null?VX.fmt.price(plTot):'n/d',plOptSub,plTot>0?'vx-pos':plTot<0?'vx-neg':'vx-muted')}
    </div>
    <div class="vx-grid vx-mb3">
      ${H('DTE moyen',dteAvg!==null?dteAvg+' j':'n/d','constitution : 60-270, préf. 90-210')}
      ${H('Delta total',gDelta,gCov,(og&&og.delta>0)?'vx-pos':(og&&og.delta<0)?'vx-neg':'')}
      ${H('Theta quotidien',gTheta,gVega,(og&&og.theta<0)?'vx-neg':'')}
      ${H('Risque événementiel',rich.some(t=>t.entrySnap&&t.entrySnap.earnings_dte!=null)?'à vérifier':'—','earnings par position ci-dessous')}
    </div>
    <section class="vx-card vx-mb3" aria-label="Allocation du capital options">
      <div class="vx-chart-head"><span class="vx-chart-title">Capital engagé par contrat</span>
        <span class="vx-chart-question">Où est concentré le capital options ?</span></div>
      <div id="pf-opt-tree" style="height:220px"></div>
      <div class="vx-card-foot"><span class="vx-meta">Taille = capital engagé (coût déclaré) · couleur = sens (CALL acier / PUT violet). Aucune valeur inventée.</span></div>
    </section>
    <div id="pf-opt-mix" class="vx-grid vx-mb3"></div>
    <div id="pf-opt-combined" class="vx-grid vx-mb3"></div>
    <section class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Positions options</span>
      <span class="vx-meta vx-right">analyse complète par position — aucune exécution</span></div>
    <div class="vx-table-wrap vx-table-cards"><table class="vx-table"><thead><tr>
      <th>Contrat</th><th class="vx-num">Qté</th><th class="vx-num">Coût</th><th class="vx-num">Marque</th>
      <th class="vx-num">P&L</th><th class="vx-num">DTE</th><th>Stop sous-jacent</th><th></th></tr></thead><tbody>
    ${rich.map(t=>{
      const dte=t.exp?Math.round((new Date(t.exp)-Date.now())/86400000):null;
      return `<tr>
      <td data-label="Contrat"><span class="vx-ticker">${t.sym}</span>
        <span class="vx-badge" style="color:var(--vx-option)">${t.type} ${t.strike??''} ${t.exp||''}</span></td>
      <td data-label="Qté" class="vx-num">${t.qty}</td>
      <td data-label="Coût" class="vx-num">${VX.fmt.price(t.cost)}</td>
      <td data-label="Marque" class="vx-num">${t.mark!==null?VX.fmt.price(t.mark):'n/d'}${marqueNote(t)}</td>
      <td data-label="P&L" class="vx-num ${t.pl>0?'vx-pos':t.pl<0?'vx-neg':''}">${t.pl!==null?VX.fmt.pct(t.pl,1):'n/d'}</td>
      <td data-label="DTE" class="vx-num ${dte!==null&&dte<=7?'vx-warn':''}">${dte!==null?dte+' j':'—'}</td>
      <td data-label="Stop">${VX.fmt.nd(t.entrySnap&&t.entrySnap.stop)}</td>
      <td><div class="vx-row-actions">
        <button class="vx-btn vx-btn-sm vx-btn-primary" data-opt-analyze="${t.id}">Analyser</button>
        <button class="vx-btn vx-btn-icon vx-btn-ghost" data-position-menu="${t.id}" aria-label="Actions position ${t.sym}">⋯</button>
      </div></td></tr>`;}).join('')}</tbody></table></div>
    <div class="vx-card-footer">${VX.updateIndicator(window.__pfTs||null,pfSourceMarques(),pfModeMarques())}
      · Greeks agrégés affichés uniquement avec IBKR (jamais estimés en agrégat)</div></section>`;
  if(window.VXCharts&&VXCharts.treemap){
    const cc=VXCharts.colors;const el=document.getElementById('pf-opt-tree');const w=(el&&el.clientWidth)||900;
    VXCharts.treemap(el,{width:w,height:220,unit:'$ investi',
      /* Question déjà posée par la carte hôte : « Où est concentré le capital
         options ? » */
      source:pfSourceMarques(),timestamp:window.__pfTs||null,
      mode:pfModeMarques(),limits:'aire = prime engagée par contrat',
      items:rich.map(t=>({label:t.sym+' '+(t.strike||''),value:Math.max(1,t.invested||0),
        sub:(t.type==='PUT'?'PUT':'CALL')+(t.exp?' '+t.exp:''),
        color:(t.type==='PUT'?(cc.violet||'#9c79d0'):(cc.neutral||'#8f8a83'))})),
      fmt:(v)=>VX.fmt.price(v)});
  }
  document.querySelectorAll('[data-opt-analyze]').forEach(b=>
    b.addEventListener('click',()=>openOptionDrawer(rich.find(t=>String(t.id)===b.dataset.optAnalyze))));
  renderCombinedOptions(rich);
  renderOptMix(rich);
}
/* §19 : répartition CALL/PUT (donut) + distribution des échéances (DTE) — données
   DÉCLARÉES uniquement (type, exp→dte) ; aucun greek estimé. */
function renderOptMix(rich){
  const host=document.getElementById('pf-opt-mix');if(!host)return;
  const calls=rich.filter(t=>t.type==='CALL').length,puts=rich.filter(t=>t.type==='PUT').length;
  host.innerHTML='<div class="vx-col-5" id="pf-opt-ring"></div>'
    +'<section class="vx-card vx-col-7"><div class="vx-card-header">'
    +'<span class="vx-card-title">Échéances de tes contrats</span>'
    +'<span class="vx-chart-question">Suis-je exposé à une expiration proche ?</span></div>'
    +'<div id="pf-opt-dte"></div>'
    +'<div class="vx-card-foot"><span class="vx-meta">Jours avant échéance (DTE) par position déclarée · une barre courte = expiration proche.</span></div></section>';
  if(window.VXCharts&&VXCharts.donutCard&&(calls||puts)){
    VXCharts.donutCard('pf-opt-ring',{title:'CALL vs PUT',unit:'contrats',
      question:'Le portefeuille options est-il directionnel ?',
      conclusion:calls+' call(s) · '+puts+' put(s)',
      labels:['CALL','PUT'],values:[calls,puts],colors:['var(--vx-neutral)','var(--vx-option)'],height:200,
      source:'positions déclarées',timestamp:window.__pfTs||null,mode:pfModeMarques()});
  }
  const dtes=rich.map(t=>({sym:t.sym,strike:t.strike,type:t.type,
      dte:t.exp?Math.round((new Date(t.exp)-Date.now())/86400000):null})).filter(x=>x.dte!=null)
    .sort((a,b)=>a.dte-b.dte);
  const de=document.getElementById('pf-opt-dte');
  if(de){
    if(dtes.length){
      const mx=Math.max.apply(null,dtes.map(d=>d.dte))||1;
      de.innerHTML='<div style="padding:6px 2px">'+dtes.map(d=>{
        const w=Math.max(3,Math.round(d.dte/mx*100));
        const soon=d.dte<=14,near=d.dte<=45;
        const col=soon?'var(--vx-negative)':near?'var(--vx-warning)':'var(--vx-neutral)';
        return `<div class="vx-flex" style="gap:8px;align-items:center;padding:3px 0">
          <span class="vx-mono" style="flex:0 0 96px;font-size:11.5px">${esc(d.sym)} ${d.type==='PUT'?'P':'C'}${d.strike?' '+VX.fmt.nd(d.strike):''}</span>
          <span style="flex:1;height:7px;border-radius:99px;background:var(--vx-surface-0);overflow:hidden">
            <i style="display:block;height:100%;width:${w}%;background:${col};border-radius:99px"></i></span>
          <b class="vx-mono" style="flex:0 0 44px;text-align:right;font-size:11.5px;color:${col}">${d.dte} j</b></div>`;
      }).join('')+'</div>';
    }else de.innerHTML=VX.states.empty('Aucune échéance datée sur tes positions.');
  }
}

/* Structure combinée par sous-jacent : analyse TES positions options réelles comme une
   stratégie multi-jambes (payoff net, breakevens, gain/perte max) via le moteur
   multileg_lab. Greeks/PoP nécessitent l'IV (n/d sans IBKR) — jamais estimés. */
async function renderCombinedOptions(rich){
  const host=document.getElementById('pf-opt-combined'); if(!host)return;
  const by={};
  rich.forEach(t=>{ if(t.type==='CALL'||t.type==='PUT'){(by[t.sym]=by[t.sym]||[]).push(t);} });
  const syms=Object.keys(by);
  if(!syms.length){host.innerHTML='';return;}
  const results=await Promise.all(syms.map(async sym=>{
    const group=by[sym];
    const spot=group.map(t=>t.underSpot).find(s=>s!=null);
    if(spot==null)return null;   // pas de cote sous-jacent → pas de payoff honnête
    const legs=group.map(t=>({type:(t.type||'').toLowerCase(),strike:t.strike,
      premium:(t.qty&&t.cost)?t.cost/(t.qty*100):null,qty:t.qty}));
    if(legs.some(l=>l.premium==null||l.strike==null))return null;
    const dtes=group.map(t=>t.exp?Math.round((new Date(t.exp)-Date.now())/86400000):null).filter(v=>v!=null);
    const days=dtes.length?Math.min.apply(null,dtes):null;
    try{
      const r=await fetch('/api/options/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({legs:legs,spot:spot,iv:null,days:days,name:sym})});
      const d=await r.json(); if(!d||!d.available)return null; return {sym:sym,spot:spot,group:group,d:d};
    }catch(e){return null;}
  }));
  const ok=results.filter(Boolean);
  if(!ok.length){host.innerHTML='';return;}
  host.innerHTML=ok.map((x,i)=>{
    const d=x.d;
    const mp=d.max_profit_unbounded?'illimité':(d.max_profit!=null?VX.fmt.price(d.max_profit):'—');
    const be=(d.breakevens&&d.breakevens.length)?d.breakevens.map(b=>VX.fmt.nd(b)).join(' · '):'—';
    return `<section class="vx-card vx-col-6">
      <div class="vx-card-header"><span class="vx-card-title">${esc(x.sym)} — structure combinée (${x.group.length} jambe${x.group.length>1?'s':''})</span>
        <span class="vx-badge" style="color:var(--vx-${d.is_credit?'positive':'option'})">${d.is_credit?'crédit ':'débit '}${VX.fmt.price(Math.abs(d.net_premium))}</span></div>
      <div id="pf-comb-pf-${i}" style="height:150px"></div>
      <div class="vx-grid vx-mt2" style="grid-template-columns:repeat(3,1fr);gap:6px">
        <div class="vx-kv"><span class="k">Gain max</span><span class="v vx-mono">${mp}</span></div>
        <div class="vx-kv"><span class="k">Perte max</span><span class="v vx-mono vx-neg">${d.max_loss!=null?VX.fmt.price(d.max_loss):'—'}</span></div>
        <div class="vx-kv"><span class="k">Breakevens</span><span class="v vx-mono">${be}</span></div>
      </div>
      <div class="vx-card-footer">${VX.updateIndicator(window.__pfTs||null,pfSourceMarques(),pfModeMarques())}
        · résumé d'exposition — le détail par contrat est dans Options</div>
    </section>`;
  }).join('');
}

/* Lot 2 — le rapprochement du P&L contre le courtier est RETIRÉ, avec sa
   route. Il lisait accountSummary, reqPnL et le portefeuille du compte —
   exactement ce que la frontière market-data-only interdit, readonly ou pas.
   Constat au passage : son hôte `pf-pnl-recon` n'existait dans AUCUNE vue ;
   la carte ne se peignait jamais. On retire donc une capacité déjà morte à
   l'écran, pas un affichage vivant. Le P&L affiché reste celui que Vertex
   calcule sur les positions déclarées, cotées par symbole. */

/* PÉRIMÈTRE DU STRESS — servi, jamais peint jusqu'ici.
   /api/portfolio/team rend `stress.coverage` {equity_basis, note, options_open,
   options_in_equity, options_vega_known} et `stress.warnings` (liste). Mesure
   du 06/09/2026 sur KO 88,07 $ + 25 000 $ de cash : coverage.note dit « base de
   stress = positions valorisées + cash ; les options déclarées exigent marque
   et greeks IBKR et restent hors base » et options_in_equity vaut false — deux
   faits qui changent la lecture de CHAQUE pourcentage du tableau, et que
   l'écran jetait. Un impact de -0,05 % calculé sur une base qui exclut les
   options n'est pas le même chiffre selon qu'on le sait ou non.
   Rien n'est recalculé ici : on peint les phrases du moteur. */
function stressPerimetre(bloc){
  const cov=(bloc&&bloc.coverage)||null;
  const warns=(bloc&&bloc.warnings)||[];
  if(!cov&&!warns.length)return '';
  let txt='';
  if(cov){
    const bits=[];
    if(cov.equity_basis)bits.push('base : '+cov.equity_basis);
    if(typeof cov.options_open==='number')
      bits.push(cov.options_open+' option(s) déclarée(s), '
        +(cov.options_in_equity?'incluse(s) dans la base':'hors base de stress'));
    if(cov.options_vega_known===false)bits.push('vega des options non mesuré');
    txt=bits.join(' · ')+(cov.note?' — '+cov.note:'');
  }
  return (txt?`<div class="vx-meta vx-mt2">${esc(txt)}</div>`:'')
    +(warns.length?`<div class="vx-meta vx-warn vx-mt1">${warns.map(esc).join(' · ')}</div>`:'');
}

/* ═══ RISQUE PRIORISÉ (LOT F — moteur risk_engine, positions réelles §26) ═══ */
async function renderRisk(){
  const pos=E().positions();
  if(!pos.length){($('pf-body')||{}).innerHTML=VX.states.emptyDesk('Aucune position déclarée — le risque se calcule sur les positions réelles, jamais sur les candidats du scanner.');return;}
  const rich=enrich(pos,await quotesFor(pos));
  renderSummary(rich);
  let scan=null;try{scan=await VX.fetch('/scan',{ttl:300000});}catch(e){}
  const sectorOf=(sym)=>{const d=scan&&scan.detail&&scan.detail[sym];return(d&&d.sector)||'';};
  const payload={positions:rich.filter(t=>t.type==='STK').map(t=>{const per=t.qty?t.cost/t.qty:t.cost;
      return {symbol:t.sym,quantity:t.qty,avg_cost:per,last_price:(t.mark!=null?t.mark:per),sector:sectorOf(t.sym)};}),
    option_positions:rich.filter(t=>t.type!=='STK').map(t=>({sym:t.sym,exp:t.exp,strike:t.strike,right:t.type,qty:t.qty})),
    cash:E().capital()||0,simulated:false};
  try{
    const r=await fetch('/api/portfolio/team',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d=await r.json();
    const risk=d.risk||{},guard=d.guard||{},stressBloc=d.stress||{},stress=stressBloc.scenarios||{};
    const optGreeks={delta:risk.options_exposure&&risk.options_exposure.delta};
    /* ── HHI : DEUX AUTORITÉS À L'ÉCRAN, mesurées le 06/09/2026 ─────────────
       Le même mot « HHI » désigne deux grandeurs différentes sur deux vues du
       MÊME portefeuille, avec deux barèmes opposés :
         · ici (/api/portfolio/team → risk_engine) : base « compartiment
           actions, poids renormalisés à 100 % — cash exclu », barème 33/66 sur
           HHI×100 ;
         · vue Allocation (/api/portfolio/context) : base « toutes les lignes
           valorisées (actions, ETF et options au capital engagé) », barème
           0,18 / 0,25.
       Mesure de la contradiction : le nombre 0,30 se lit « bien dispersé » ici
       et « concentré » là-bas. Et sur KO 88,07 $ + 25 000 $ de cash, `hhi`
       vaut 1,0 — « très concentré » en rouge — alors que 0,35 % du capital est
       investi : le rouge décrit un compartiment quasi vide.
       Le serveur sert déjà la base (`hhi_basis`) et la part investie
       (`invested_pct`) ; ni l'une ni l'autre n'était peinte. On ne touche NI
       les seuils NI les nombres — la page peint ce que le moteur dit, elle
       nomme seulement ce que son chiffre mesure. */
    const hhiBase=risk.hhi_basis?String(risk.hhi_basis):'';
    const hhiPart=(typeof risk.invested_pct==='number')
      ?(VX.fmt.num(risk.invested_pct,2)+' % du capital investi')
      :'part investie non servie';
    const hhiPied=[hhiBase,hhiPart].filter(Boolean).join(' · ');
    ($('pf-body')||{}).innerHTML=`<div class="vx-grid vx-mb3">
      <section class="vx-card vx-col-4" aria-label="Concentration du risque">
        <div class="vx-card-header"><span class="vx-card-title">Concentration du risque</span>
          <span class="vx-chart-question">Le capital est-il trop concentré ?</span></div>
        <div id="pf-risk-gauge"><div class="vx-skeleton" style="height:118px"></div></div>
        <div class="vx-card-footer"><span class="vx-meta">Indice HHI (0 = dispersé · 100 = tout sur un titre) — donnée réelle du moteur.
          Base : ${esc(hhiPied)}. La vue Allocation publie un HHI d&#8217;une AUTRE base (toutes les lignes valoris&eacute;es) : les deux nombres ne se comparent pas.</span></div>
      </section>
      <section class="vx-card vx-col-8" aria-label="Synthèse du risque">
        <div class="vx-card-header"><span class="vx-card-title">Synthèse du risque</span></div>
        <div class="vx-grid" id="pf-risk-kpis"></div>
        <div class="vx-mt3"><span class="vx-metric-k" style="display:block;margin-bottom:2px">Poids par position</span>
          <div id="pf-weight-bars"><span class="vx-meta">Allocation…</span></div></div>
      </section>
    </div>
    <div class="vx-grid">
      <div class="vx-card vx-col-4"><div class="vx-card-header"><span class="vx-card-title">Garde-fous</span></div>
        ${kv('Nouveau titre',guard.new_stock_allowed?'autorisé':'BLOQUÉ',guard.new_stock_allowed?'vx-pos':'vx-neg')}
        ${kv('Nouvelle option',guard.new_option_allowed?'autorisée':'BLOQUÉE',guard.new_option_allowed?'vx-pos':'vx-neg')}
        ${(guard.blocking_rules||[]).map(r=>`<div class="vx-insight" data-tone="risk">${r}</div>`).join('')}
        ${(guard.mandatory_reviews||[]).map(r=>`<div class="vx-meta">⚠ ${esc(r)}</div>`).join('')}</div>
      <div class="vx-card vx-col-4"><div class="vx-card-header"><span class="vx-card-title">Concentration</span></div>
        ${kv('Drawdown portefeuille',risk.drawdown_pct!==null&&risk.drawdown_pct!==undefined?risk.drawdown_pct+' %':'n/d (pic non renseigné)')}
        ${kv('HHI',risk.hhi)}${hhiPied?`<div class="vx-meta" style="margin:-2px 0 6px">${esc(hhiPied)}</div>`:''}
        ${kv('Bêta pondéré',risk.beta)}
        ${(function(){const ps=risk.per_stock_pl_pct||{};const ent=Object.keys(ps).map(k=>[k,ps[k]]).sort((a,b)=>a[1]-b[1]);
          if(!ent.length)return '';
          return '<div class="vx-mt2"><span class="vx-metric-k" style="display:block;margin-bottom:3px">P&amp;L par position (pire en tête)</span>'
            +ent.map(function(e){var s=e[0],v=e[1];var col=v>0?'var(--vx-positive)':v<-20?'var(--vx-negative)':v<0?'var(--vx-warning)':'var(--vx-text-secondary)';
              return '<div class="vx-flex" style="justify-content:space-between;font-size:11.5px;padding:2px 0"><span class="vx-mono">'+esc(s)+'</span><span class="vx-mono" style="color:'+col+'">'+(v>=0?'+':'')+VX.fmt.num(v,1)+' %'+(v<-20?' ⚠ drawdown':'')+'</span></div>';}).join('')
            +'</div>';})()}
        <div id="pf-sector-donut" class="vx-mt2"><span class="vx-meta">Exposition sectorielle…</span></div></div>
      <div class="vx-card vx-col-4"><div class="vx-card-header"><span class="vx-card-title">Greeks agrégés</span></div>
        ${greeksBlock(risk.options_exposure)}</div>
      <section class="vx-card vx-col-12"><div class="vx-card-header"><span class="vx-card-title">Stress tests (§26)</span>
        <span class="vx-chart-question">Combien perd le portefeuille dans chaque scénario ?</span></div>
        ${(function(){const arr=Object.entries(stress).filter(([,v])=>v.impact_pct!=null);
          if(!arr.length)return '';
          const maxAbs=Math.max.apply(null,[1].concat(arr.map(([,v])=>Math.abs(v.impact_pct))));
          /* LOT 131 : matiere verre — chaque barre est un degrade de sa propre
             couleur (doux au zero -> dense a l'extremite), via color-mix sur les
             tokens (aucun litteral) ; le PIRE scenario est mis en avant (halo +
             libelle en negatif) : LE chiffre educatif d'un stress test. */
          const worst=arr.reduce((a,[k,v])=>v.impact_pct<a.v?{k:k,v:v.impact_pct}:a,{k:null,v:0});
          return '<div class="vx-mb3">'+arr.map(([k,v])=>{const neg=v.impact_pct<0;
            const w=Math.min(100,Math.abs(v.impact_pct)/maxAbs*100);
            const tok=neg?'var(--vx-negative,#E9555F)':'var(--vx-positive,#2BBE90)';
            const isWorst=neg&&k===worst.k;
            return '<div style="display:flex;align-items:center;gap:8px;margin:3px 0" role="img" aria-label="'+esc(k)+' '+VX.fmt.pct(v.impact_pct,1)+(isWorst?' — pire scenario':'')+'">'
              +'<span title="'+esc(k)+'" style="width:150px;font-size:11px;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'+(isWorst?'color:var(--vx-negative,#E9555F);font-weight:700':'color:var(--vx-text-secondary,#BABABA)')+'">'+esc(k)+'</span>'
              +'<span style="flex:1;height:13px;background:var(--vx-surface-3,#121214);border-radius:4px;overflow:hidden"><span style="display:block;height:100%;width:'+w.toFixed(0)+'%;background:linear-gradient(90deg,color-mix(in srgb,'+tok+' 35%,transparent),'+tok+');border-radius:4px'+(isWorst?';box-shadow:0 0 6px color-mix(in srgb,var(--vx-negative,#E9555F) 45%,transparent)':'')+'"></span></span>'
              +'<span style="width:58px;text-align:right;font-size:11px;font-variant-numeric:tabular-nums;'+(isWorst?'font-weight:700':'')+'" class="'+(neg?'vx-neg':'vx-pos')+'">'+VX.fmt.pct(v.impact_pct,1)+'</span></div>';
          }).join('')+'</div>';})()}
        <div class="vx-table-wrap"><table class="vx-table"><thead><tr><th>Scénario</th>
        <th class="vx-num">Impact estimé</th><th>Note</th></tr></thead><tbody>
        ${Object.entries(stress).map(([k,v])=>`<tr><td>${k}</td>
          <td class="vx-num ${v.impact_pct<0?'vx-neg':''}">${v.impact_pct!==null&&v.impact_pct!==undefined?VX.fmt.pct(v.impact_pct,1):'non estimé'}</td>
          <td class="vx-meta">${esc(v.note||'')}</td></tr>`).join('')}</tbody></table></div>
        ${stressPerimetre(stressBloc)}
        <div class="vx-card-footer">${VX.updateIndicator(window.__pfTs||null,'risk_engine · horodatage des marques d’entrée',pfModeMarques())}
        ${(risk.warnings||[]).length?'· '+risk.warnings.map(esc).join(' · '):''}</div></section>
      <div class="vx-col-12" id="pf-corr-heatmap"></div></div>`;
    /* Heatmap de corrélations RÉELLES entre les positions (risk_engine · rendements) :
       rouge = fortement corrélé (diversification illusoire), vert = décorrélé. Vide
       honnête sans historique de prix (flux live requis). */
    corrHeatmap('pf-corr-heatmap',risk.correlations);
    /* Hero §31-32 : jauge de concentration (HHI×100) + bande KPI risque. Données
       réelles du moteur (risk.hhi/beta/drawdown, pire scénario stress). */
    try{
      var _hhi=(risk.hhi!=null)?Math.round(risk.hhi*100):null;
      if(window.VXCharts&&VXCharts.gauge)VXCharts.gauge('pf-risk-gauge',{
        value:_hhi,min:0,max:100,unit:'',label:'Concentration',
        /*  La lecture NOMME sa base : « très concentré » sur un compartiment
            actions renormalisé à 100 % ne dit pas la même chose selon qu'il
            pèse 0,35 % ou 95 % du capital. Le mot du barème est inchangé ; ce
            qui s'y ajoute est SERVI (hhi_basis / invested_pct), pas déduit.  */
        /*  `reading` est inséré tel quel dans le DOM ET dans un aria-label par
            chart-core.js : la phrase vient du serveur, elle passe par esc().  */
        reading:(_hhi==null?'donnée indisponible':(_hhi>=66?'très concentré':_hhi>=33?'concentration modérée':'bien dispersé'))
          +(hhiPied?' — '+esc(hhiPied):''),
        bands:[{to:33,color:VXCharts.colors.positive},{to:66,color:VXCharts.colors.warning},{to:100,color:VXCharts.colors.negative}]});
      var _ws=Object.values(stress).map(function(v){return v&&v.impact_pct;}).filter(function(x){return typeof x==='number';});
      var _worst=_ws.length?Math.min.apply(null,_ws):null;
      var _rk=function(l,v,d,cls){return '<div class="vx-card vx-card--compact vx-kpi vx-col-3"><span class="vx-kpi-label">'+l+'</span><span class="vx-kpi-value" style="font-size:22px">'+(v==null?'—':v)+'</span>'+(d?'<span class="vx-kpi-delta '+(cls||'vx-muted')+'">'+d+'</span>':'')+'</div>';};
      var _rh=$('pf-risk-kpis');
      if(_rh)_rh.innerHTML=
        _rk('HHI',risk.hhi!=null?risk.hhi:'—',
            esc(risk.hhi_basis?'indice · '+risk.hhi_basis:'indice · base non servie'),
            (_hhi!=null&&_hhi>=66)?'vx-neg':'')
        +_rk('Bêta',risk.beta!=null?risk.beta:'—','pondéré')
        +_rk('Drawdown',(risk.drawdown_pct!=null)?(risk.drawdown_pct+' %'):'n/d','pic')
        +_rk('Pire scénario',_worst!=null?VX.fmt.pct(_worst,1):'—','stress',(_worst!=null&&_worst<0)?'vx-neg':'');
      /* Barres de poids par position (risk.weights réel + cash + surpondérations) —
         remplit la synthèse et rend la concentration lisible d'un coup d'œil. */
      var _wb=$('pf-weight-bars');
      if(_wb)_wb.innerHTML=weightBars(risk.weights,risk.overweight,15)||'<span class="vx-meta">Poids par position indisponibles.</span>';
      /* Exposition sectorielle : donut au lieu d'une liste tronquée à 5 ; le surplus
         est regroupé en « Autres » (aucune troncature silencieuse). '—' honnête si vide. */
      var _sw=risk.sector_weights||{};
      var _sh=document.getElementById('pf-sector-donut');
      if(_sh){
        var _se=Object.keys(_sw).map(function(k){return [k,+_sw[k]];}).filter(function(e){return isFinite(e[1])&&e[1]>0;}).sort(function(a,b){return b[1]-a[1];});
        if(!_se.length){_sh.innerHTML='<span class="vx-meta">Exposition sectorielle indisponible (aucune position action).</span>';}
        else if(window.VXCharts&&VXCharts.donut){
          var _lab,_val;
          if(_se.length<=5){_lab=_se.map(function(e){return e[0];});_val=_se.map(function(e){return e[1];});}
          else{var _t=_se.slice(0,4);_lab=_t.map(function(e){return e[0];});_val=_t.map(function(e){return e[1];});
            var _rest=_se.slice(4).reduce(function(s,e){return s+e[1];},0);_lab.push('Autres');_val.push(+_rest.toFixed(2));}
          _sh.innerHTML='<div class="vx-kpi-label vx-mb1">Exposition sectorielle</div><div style="height:150px"><canvas></canvas></div>';
          VXCharts.donut(_sh.querySelector('canvas'),_lab,_val,{});
        } else {_sh.innerHTML=_se.map(function(e){return kv(e[0],e[1]+' %');}).join('');}
      }
    }catch(e){}

  }catch(e){($('pf-body')||{}).innerHTML=VX.states.error('Moteur de risque injoignable : '+e.message);}
}

/* ── WATCHLIST (+ suivis + favoris §18) ── */
/* Sparkline compacte pour les tuiles de watchlist (série réelle du scan). */
function sparkWl(closes,up){
  const v=(closes||[]).filter(x=>x!=null&&isFinite(x)).slice(-40);
  if(v.length<8)return '';
  const w=100,h=20,mn=Math.min.apply(null,v),mx=Math.max.apply(null,v),rng=(mx-mn)||1;
  const pts=v.map((x,i)=>(i/(v.length-1)*w).toFixed(1)+','+(h-1-((x-mn)/rng)*(h-2)).toFixed(1)).join(' ');
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" width="100%" height="20" style="display:block;margin:7px 0 2px;opacity:.9" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${up?'var(--vx-positive)':'var(--vx-negative)'}" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}
async function renderWatchlist(){
  const wl=E().watchlist(),follows=E().follows(),favs=E().favorites();
  const statuses=['idee','a_etudier','en_attente','proche','declenchee','invalidee','archivee'];
  const labels={idee:'Idée',a_etudier:'À étudier',en_attente:'En attente',proche:'Proche',
    declenchee:'Déclenchée',invalidee:'Invalidée',archivee:'Archivée'};
  /* Jointure watchlist ↔ scan : score, variation, MTF et sparkline RÉELS quand le
     titre est scanné ; tuile sobre (sans enrichissement inventé) sinon. */
  let scan=null;try{scan=await VX.fetch('/scan',{ttl:120000});}catch(e){}
  const rowOf={};((scan&&scan.rows)||[]).forEach(r=>{if(r&&r.symbol)rowOf[r.symbol]=r;});
  const detOf=(scan&&scan.detail)||{};
  const wlTiles=wl.map(w=>{
    const r=rowOf[w.sym]||{};const det=detOf[w.sym]||{};
    const chg=r.change;const mtf=det.mtf||{};
    const mtfTone=/HAUSS/i.test(mtf.state||'')?'var(--vx-positive)':/BAISS/i.test(mtf.state||'')?'var(--vx-negative)':'var(--vx-warning)';
    const prio=(w.priority||'normale');
    return `<div class="vx-mover" style="cursor:default">
      <div class="vx-flex" style="justify-content:space-between;gap:6px">
        <span class="mv-sym">${esc(w.sym)}</span>
        <span class="vx-flex" style="gap:4px">
          ${prio!=='normale'?`<span class="vx-badge" style="color:var(--vx-warning)">${esc(prio)}</span>`:''}
          ${r.score!=null?`<span class="vx-badge" title="Score Vertex">${VX.fmt.num(r.score,0)}</span>`:''}</span></div>
      <div class="mv-chg ${chg>0?'vx-pos':chg<0?'vx-neg':''}" style="font-size:15px">
        ${chg!=null?VX.fmt.pct(chg,1):'<span class="vx-muted" style="font-size:12px">hors scan</span>'}
        ${r.price!=null?`<span class="vx-meta" style="font-weight:500"> · ${VX.fmt.price(r.price)}</span>`:''}</div>
      ${mtf.state?`<div class="mv-sub" style="color:${mtfTone};margin-top:4px">MTF ${esc(mtf.state)}</div>`:''}
      ${sparkWl(det.series&&det.series.close,chg==null?true:chg>=0)}
      ${w.thesis?`<div class="mv-sub" style="white-space:normal;line-height:1.4;max-height:2.9em;overflow:hidden" title="${esc(w.thesis)}">${esc(w.thesis)}</div>`:''}
      <div class="mv-sub" style="margin-top:5px">${w.zone?`zone <b>${esc(w.zone)}</b>`:''}${w.zone&&w.catalyst?' · ':''}${w.catalyst?esc(w.catalyst):''}</div>
      <div class="vx-flex vx-mt2" style="gap:.3rem;align-items:center">
        <select class="vx-select" data-wl-status="${w.sym}" style="width:auto;padding:3px 22px 3px 8px;font-size:11px">
          ${statuses.map(s=>`<option value="${s}" ${w.status===s?'selected':''}>${labels[s]}</option>`).join('')}</select>
        <span class="vx-grow"></span>
        <button class="vx-btn vx-btn-sm vx-btn-primary" data-open-analysis="${w.sym}">Analyser</button>
        <button class="vx-btn vx-btn-sm vx-btn-danger" data-wl-del="${w.sym}">✕</button>
      </div>
    </div>`;}).join('');
  ($('pf-body')||{}).innerHTML=`
    <section class="vx-card vx-mb3 vx-card--premium"><div class="vx-card-header"><span class="vx-card-title">Watchlist (surveillance active)</span>
      <span class="vx-chart-question">Score, tendance et alignement en direct du scan</span>
      <span class="vx-actions"><button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal('','watchlist')">+ Ajouter</button></span></div>
      ${wl.length?`<div class="vx-movergrid" style="grid-template-columns:repeat(auto-fill,minmax(240px,1fr))">${wlTiles}</div>`
        :VX.states.empty('Watchlist vide — ajoutez les titres à surveiller activement avec thèse et zone.',
          '<button class="vx-btn vx-btn-sm" onclick="VXEntities.openAddModal(\'\',\'watchlist\')">+ Ajouter</button>')}
    </section>
    <section class="vx-card vx-mb3"><div class="vx-card-header"><span class="vx-card-title">Suivis actifs (setups)</span>
      <span class="vx-chart-question">Stop · entrée · objectif — le plan de chaque setup, visuel</span></div>
      ${follows.length?follows.map(r=>{
        /* `+null`, `+''` et `+false` valent 0, et `isFinite(0)` vaut true : la
           garde laissait passer une ABSENCE et la barre dessinait un plan
           « 0,00 STOP · 361,19 ENTRÉE · 0,00 OBJECTIF » — une perte de 100 %
           présentée comme le plan de risque du setup. Mesuré le 06/09/2026 :
           le bouton « Suivre → » d'Analyse crée un suivi sans aucun niveau
           (vx-entities.js : entry_spot/stop/tgt = null par défaut), donc ce
           rendu est le cas NOMINAL, pas un cas de bord. Coercition stricte :
           une absence devient NaN, la garde tombe, et le repli honnête déjà
           écrit plus bas (VX.fmt.nd → « — ») s'affiche. Un vrai 0 reste
           affiché — absence et zéro redeviennent distincts (invariant 5). */
        const fin=x=>(x===null||x===undefined||x===''||typeof x==='boolean')?NaN:+x;
        const e=fin(r.entry_spot),s=fin(r.stop),t=fin(r.tgt);
        let range='';
        if([e,s,t].every(x=>isFinite(x))){
          const lo=Math.min(e,s,t),hi=Math.max(e,s,t),span=(hi-lo)||1,pad=span*.08,a=lo-pad,rng=(hi+pad*2)-a;
          const P=x=>((x-a)/rng*100).toFixed(1);
          range=`<div class="vx-rangebar" style="margin:24px 10px 32px;flex:1;min-width:170px">
            <span class="rb-fill" style="left:${P(Math.min(s,t))}%;right:${(100-+P(Math.max(s,t))).toFixed(1)}%"></span>
            <i class="rb-tick" style="left:${P(s)}%;background:var(--vx-negative)"></i><span class="rb-lab" style="left:${P(s)}%;color:var(--vx-negative)">${VX.fmt.price(s)}<span class="rb-lab-sub">stop</span></span>
            <i class="rb-tick" data-kind="price" style="left:${P(e)}%"></i><span class="rb-lab" data-kind="price" style="left:${P(e)}%">${VX.fmt.price(e)}<span class="rb-lab-sub">entrée</span></span>
            <i class="rb-tick" data-kind="mean" style="left:${P(t)}%;background:var(--vx-positive)"></i><span class="rb-lab" data-kind="mean" style="left:${P(t)}%;color:var(--vx-positive)">${VX.fmt.price(t)}<span class="rb-lab-sub">objectif</span></span>
          </div>`;
        }
        /* Le libellé de repli affirmait une CAUSE que la branche ne mesure pas :
           elle se déclenche sur `[e,s,t].every(x=>!isFinite(x))`, ce qui couvre
           aussi une valeur stockée non numérique (une chaîne non parsable donne
           NaN sans passer par la garde null/''/booléen). « Aucun niveau saisi à
           la création du suivi » était donc une hypothèse : vraie du cas nominal
           (le bouton « Suivre → » crée entry_spot/stop/tgt à null), fausse d'un
           suivi corrompu. La page dit ce qu'elle constate. */
        return `<div class="vx-flex" style="padding:9px 0;border-bottom:1px dashed var(--vx-border-soft);gap:12px;align-items:center">
        <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${r.sym}">${r.sym}</button>
        <span class="vx-badge vx-badge-entity" data-kind="follow">${r.kind}</span>
        ${range||`<span class="vx-grow vx-mono vx-meta">${[e,s,t].every(x=>!isFinite(x))?'plan non défini — aucun niveau exploitable':`entrée ${VX.fmt.nd(r.entry_spot)} · stop ${VX.fmt.nd(r.stop)} · objectif ${VX.fmt.nd(r.tgt)}`}</span>`}
        <span class="vx-meta">depuis ${r.followed||'—'}</span>
        <button class="vx-btn vx-btn-sm vx-btn-danger" data-unfollow="${r.sym}">Retirer</button></div>`;}).join('')
        :VX.states.empty('Aucun suivi actif — créez un suivi depuis une analyse (entrée/stop/objectif).')}
    </section>
    <section class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Favoris (accès rapide)</span></div>
      <div class="vx-meta vx-mb2">Simple raccourci. Un favori n’implique ni thèse, ni alerte, ni position.</div>
      <div class="vx-flex vx-wrap">${favs.length?favs.map(s=>
        `<button class="vx-btn vx-ticker" data-open-analysis="${s}">★ ${s}</button>`).join('')
        :'<span class="vx-muted">Aucun favori — l’étoile est disponible sur chaque titre.</span>'}</div>
    </section></div>`;
  document.querySelectorAll('[data-wl-del]').forEach(b=>b.addEventListener('click',()=>{E().removeFromWatchlist(b.dataset.wlDel);renderWatchlist();}));
  document.querySelectorAll('[data-unfollow]').forEach(b=>b.addEventListener('click',()=>{E().unfollow(b.dataset.unfollow);renderWatchlist();}));
  document.querySelectorAll('[data-wl-status]').forEach(sel=>sel.addEventListener('change',()=>{
    E().addToWatchlist(sel.dataset.wlStatus,Object.assign({},E().watchlist().find(w=>w.sym===sel.dataset.wlStatus),{status:sel.value}));}));
}

/* Discipline V2 (SKYLER LOT 8d) : bornes 8-15, concentration (top/HHI), plafond
   par titre — PortfolioContext canonique, jamais un chiffre inventé. */
/* ═══ STRESS ET DEPENDANCES CACHEES — LES DEUX ANALYSES MANQUANTES ═══════

   Les deux etaient APPELEES par la vue « risque » et definies NULLE PART :
   `risk:async function(){await renderRisk();await renderStress();
    await renderDiscipline();await renderHiddenDeps();}`

   La vue levait donc `ReferenceError` sur la deuxieme ligne et ne rendait
   RIEN — pas meme `renderRisk`, qui existe pourtant.

   Les moteurs, eux, existaient : `/api/portfolio/stress` et `/api/risk` sont
   servis depuis `engines/portfolio_stress.py` et le contexte de correlation.
   Seul l'affichage manquait.

   Lecture seule : ces deux blocs DECRIVENT une exposition, ils n'en preparent
   aucune. Aucun chiffre n'est calcule ici — tout vient du serveur.
   ═══════════════════════════════════════════════════════════════════════ */

/* Stress : ce que le portefeuille encaisse sur un choc de marche. */
async function renderStress(){
  let d=null,err=null;
  try{d=await VX.fetch('/api/portfolio/stress',{ttl:120000});}catch(e){err=e;}
  document.querySelectorAll('[aria-label="Stress"]').forEach(n=>n.remove());
  const host=document.createElement('section');
  host.className='vx-card vx-mt3';host.setAttribute('aria-label','Stress');

  if(err||!d){
    host.innerHTML='<div class="vx-card-header"><span class="vx-card-title">Stress de marche</span></div>'
      +VX.states.error('Stress indisponible');
    ($('pf-body')||{}).appendChild&&$('pf-body').appendChild(host);return;}

  const tete='<div class="vx-card-header"><span class="vx-card-title">Stress de marche</span>'
    +'<span class="vx-chart-question">Que perd le portefeuille si le marche recule ?</span></div>';

  if(d.empty){
    /*  Un stress sans position chiffrable n'est pas un stress a zero : c'est
        une ABSENCE. L'afficher comme « perte 0 » serait la lecture la plus
        dangereuse possible de cette carte.  */
    const exclus=(d.excluded||[]).length;
    host.innerHTML=tete+VX.states.empty(esc(d.reason||'aucune position chiffrable'))
      +(exclus?`<div class="vx-meta vx-mt2">${exclus} position(s) exclue(s) faute de prix reel`
        +(d.excluded_cost!=null?` · cout declare ${VX.fmt.price(d.excluded_cost)}`:'')+'</div>':'')
      +`<div class="vx-card-footer">${VX.updateIndicator(null,
          'portfolio_stress · horodatage non servi par la route','')}</div>`;
    ($('pf-body')||{}).appendChild&&$('pf-body').appendChild(host);return;}

  const lignes=(d.positions||[]).map(x=>{
    const pv=(x.loss_pct!=null)?VX.fmt.pct(x.loss_pct,1):'n/d';
    return `<tr><td data-label="Titre">${esc(x.sym||'')}</td>`
      +`<td data-label="Valeur" class="vx-num">${x.value!=null?VX.fmt.price(x.value):'n/d'}</td>`
      +`<td data-label="Choc" class="vx-num vx-neg">${x.loss!=null?VX.fmt.price(x.loss):'n/d'}</td>`
      +`<td data-label="Impact" class="vx-num vx-neg">${pv}</td></tr>`;}).join('');

  host.innerHTML=tete
    +`<div class="vx-meta">${esc(d.assumption||'')}</div>`
    +(d.narrative?`<p class="vx-mt2">${esc(d.narrative)}</p>`:'')
    +`<div class="vx-table-wrap vx-mt2"><table class="vx-table"><thead><tr>
        <th>Titre</th><th class="vx-num">Valeur</th><th class="vx-num">Choc</th>
        <th class="vx-num">Impact</th></tr></thead><tbody>${lignes}</tbody></table></div>`
    +`<div class="vx-meta vx-mt2">Couverture ${d.coverage_pct!=null?VX.fmt.pct(d.coverage_pct,0):'n/d'}`
    +((d.excluded||[]).length?` · ${(d.excluded||[]).length} position(s) hors calcul faute de prix reel`:'')
    +'</div>'
    /* HORODATAGE : `window.__pfTs` est l'heure de la charge /api/pos-quotes.
       Or cette carte lit /api/portfolio/stress, un GET SANS CORPS que la route
       sert depuis le scan — elle ne consomme aucune des marques de pos-quotes.
       Mesure du 06/09/2026 sur la charge servie : ses clés sont assumption,
       coverage_pct, empty, excluded, excluded_cost, generator, narrative,
       positions, reason, scenarios, stressed_value — aucun `as_of`, aucun `ts`.
       Dater cette carte avec l'horloge d'une AUTRE route lui prêtait une
       fraîcheur jamais mesurée (famille du constat 51). Sans horodatage servi,
       `updateIndicator(null, …)` écrit « Âge inconnu » et n'affirme aucun mode :
       une absence dite vaut mieux qu'un âge emprunté. */
    +`<div class="vx-card-footer">${VX.updateIndicator(null,
        'portfolio_stress · '+esc(d.generator||'moteur')+' · horodatage non servi par la route',
        '')} · lecture seule</div>`;
  ($('pf-body')||{}).appendChild&&$('pf-body').appendChild(host);
}

/* Dependances cachees : ce que l'etiquette de secteur ne montre pas. */
/* Panier = positions DÉCLARÉES (actions/ETF), envoyées explicitement au
   moteur. Le GET de /api/risk mesure le panier du comité, pas le portefeuille :
   c'était l'ancien défaut (§13 #7). Aucun chiffre n'est calculé ici. */
function pfSymbolesDeclares(){
  const pos=(window.VXEntities?VXEntities.positions():[])||[];
  return [...new Set(pos.filter(p=>!p.type||p.type==='STK')
    .map(p=>String(p.sym||'').toUpperCase()).filter(Boolean))];
}
async function pfRisqueDeclare(){
  const r=await fetch('/api/risk',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({symbols:pfSymbolesDeclares()})});
  if(!r.ok)throw new Error('HTTP '+r.status);
  return r.json();
}
async function renderHiddenDeps(){
  let d=null,err=null;
  try{d=await pfRisqueDeclare();}catch(e){err=e;}
  document.querySelectorAll('[aria-label="Dependances cachees"]').forEach(n=>n.remove());
  const host=document.createElement('section');
  host.className='vx-card vx-mt3';host.setAttribute('aria-label','Dependances cachees');

  const tete='<div class="vx-card-header"><span class="vx-card-title">Dependances cachees</span>'
    +'<span class="vx-chart-question">Mes positions bougent-elles ensemble sans que le secteur le dise ?</span></div>';

  if(err||!d){
    host.innerHTML=tete+VX.states.error('Analyse de dependances indisponible');
    ($('pf-body')||{}).appendChild&&$('pf-body').appendChild(host);return;}

  const flags=d.flags||[];
  if(!flags.length){
    /*  « Aucun drapeau » et « panier trop petit » sont deux choses
        differentes : la premiere est un resultat, la seconde une absence de
        mesure. Le serveur les distingue par `note` — on la sert telle quelle
        plutot que d'annoncer une diversification qu'on n'a pas mesuree.  */
    /*  « Aucun drapeau » sur un panier mesure est un RESULTAT (etat positif),
        pas une absence de donnee : seule la `note` du serveur (panier trop
        petit, aucune position) est un etat vide.  */
    host.innerHTML=tete
      +(d.note?VX.states.empty(esc(d.note))
             :'<div class="vx-insight vx-mt2">Aucune dependance cachee detectee sur '+(d.n||0)+' titre(s) declare(s).</div>')
      +pfNonMesures(d)
      +`<div class="vx-card-footer">${VX.updateIndicator(d.as_of||window.__pfTs||null,'risk_engine · positions declarees',
          pfModeMarques())}</div>`;
    ($('pf-body')||{}).appendChild&&$('pf-body').appendChild(host);return;}

  const items=flags.map(f=>{
    const t=(f.severity==='high'||f.level==='high')?'neg':'warn';
    const paire=(f.pair||f.symbols||[]).join(' + ');
    return `<div class="vx-kv"><span class="k">${esc(paire||f.kind||'')}</span>`
      +`<span class="v"><span class="vx-badge" data-tone="${t}">${esc(f.label||f.kind||'')}</span></span></div>`;
  }).join('');

  host.innerHTML=tete
    +`<div class="vx-mt2">${items}</div>`
    +`<div class="vx-meta vx-mt2">${flags.length} signal(aux) sur ${d.n||0} titre(s) declare(s)`
    +(d.no_new_risk?' · <span class="vx-neg">nouveau risque deconseille</span>':'')+'</div>'
    +pfNonMesures(d)
    +`<div class="vx-card-footer">${VX.updateIndicator(d.as_of||window.__pfTs||null,'risk_engine · positions declarees',
        pfModeMarques())} · lecture seule</div>`;
  ($('pf-body')||{}).appendChild&&$('pf-body').appendChild(host);
}
/* Titres declares que le moteur n'a PAS pu mesurer (hors scan ou historique
   < 40 clotures) : dits, jamais comptes comme « diversifies ». */
function pfNonMesures(d){
  const nm=(d&&d.non_mesures)||[];
  return nm.length?`<div class="vx-meta vx-mt1">${nm.length} titre(s) non mesurable(s) (hors scan ou historique trop court) : ${nm.map(esc).join(', ')}</div>`:'';
}

async function renderDiscipline(){
  /* LOT 603 (dossier 531-A, suite) : un echec ne fait plus disparaitre la
     section. Invariant produit : donnee absente -> mention honnete. */
  let d=null,err=null;
  try{d=await VX.fetch('/api/portfolio/context',{ttl:120000});}catch(e){err=e;}
  document.querySelectorAll('[aria-label="Discipline V2"]').forEach(n=>n.remove());   // idempotent
  const host=document.createElement('details');
  host.className='vx-disclosure vx-mt3';host.setAttribute('aria-label','Discipline V2');
  if(err||!d){
    host.innerHTML='<summary>Expertise · discipline Constitution V2</summary><div class="vx-card vx-mt2">'
      +VX.states.error('Discipline du portefeuille indisponible')+'</div>';
    $('pf-body').appendChild(host);return;}
  if(d.available===false){
    host.innerHTML=`<summary>Expertise · discipline Constitution V2</summary><div class="vx-card vx-mt2">
      ${VX.states.empty(esc((d.reason||'contexte indisponible')+'.'))}</div>`;
  }else{
    const b=d.bounds||{};
    const inb=d.in_bounds?'<span class="vx-badge" data-tone="pos">dans les bornes</span>'
      :`<span class="vx-badge" data-tone="neutral">${d.n_positions<b.min?'sous la cible':'au-dessus de la cible'}</span>`;
    const topOver=(d.top_weight_pct||0)>15;
    host.innerHTML=`<summary>Expertise · discipline Constitution V2</summary><div class="vx-card vx-mt2">
      <div class="vx-card-header"><span class="vx-card-title">Discipline du portefeuille (Constitution V2)</span>
      <span class="vx-chart-question">${b.min}-${b.max} lignes cibles · plafond 15&nbsp;% par titre. Le HHI canonique reste dans les 4 KPI Risque.</span></div>
      <div class="vx-grid">
        <div class="vx-stat vx-col-4"><span class="vx-stat-label">Lignes</span><span class="vx-stat-value">${d.n_positions}</span><span class="vx-meta">${inb}</span></div>
        <div class="vx-stat vx-col-4"><span class="vx-stat-label">Plus gros titre</span><span class="vx-stat-value">${esc(d.top_symbol||'—')}</span><span class="vx-meta ${topOver?'vx-neg':''}">${VX.fmt.num(d.top_weight_pct,1)}&nbsp;% ${topOver?'· > plafond 15 %':''}</span></div>
        <div class="vx-stat vx-col-4"><span class="vx-stat-label">Valeur suivie</span><span class="vx-stat-value">${VX.fmt.num(d.total_value,0)}</span><span class="vx-meta">${esc((d.provenance||[]).join(' + '))}</span></div>
      </div>
      <div class="vx-meta" style="margin-top:.35rem">${d.valuation_note?esc(d.valuation_note)+' · ':''}Bornes et plafonds = Constitution V2 — analyse, jamais un ordre.</div></div>`;
  }
  $('pf-body').appendChild(host);
}
/* ═══ ALLOCATION ET EXPOSITIONS ══════════════════════════════════════════
   Sous-vue canonique manquante (`portfolio-center.md` § Allocation) : la page
   savait dessiner des poids, mais nulle part elle ne repondait « ou suis-je
   concentre, et sur quoi ne sais-je PAS repondre ».

   Tout vient de `/api/portfolio/context` (moteur `portfolio_context`) : poids,
   HHI, mix par actif, mix sectoriel, couverture du referentiel, budget de
   risque, expositions factorielles. Aucun chiffre n'est calcule ici — pas meme
   un total : le moteur les porte deja, et un second calcul divergerait.
   Devise, pays, theme et look-through ETF sont DECLARES absents, pas simules. */
/* `unite` est OBLIGATOIRE a l'appel : la premiere version suffixait « % » en
   dur, et le budget de risque — qui est en dollars — s'affichait « 3280,0 % ».
   Une echelle qui ment sur son unite est pire qu'une echelle absente. */
function allocBars(entries,unite,opt){
  opt=opt||{};
  const es=(entries||[]).filter(e=>e&&isFinite(e.v)&&e.v>0).sort((a,b)=>b.v-a.v);
  if(!es.length)return '';
  const mx=Math.max.apply(null,es.map(e=>e.v));
  const dire=(v)=>(unite==='%')
    ? ((v<0.05?'&lt; 0,1':VX.fmt.num(v,1))+'&nbsp;%')
    : (VX.fmt.num(v,0)+'&nbsp;'+unite);
  return '<div class="vx-wbars">'+es.map(e=>`<div class="vx-wbar">`
    +`<span class="wb-name">${esc(e.k)}</span>`
    +`<span class="wb-track"><i style="width:${Math.max(2,e.v/mx*100).toFixed(0)}%`
    +`${e.color?';background:'+e.color:''}"></i></span>`
    +`<span class="wb-val">${dire(e.v)}</span></div>`).join('')
    +(opt.note?`<div class="vx-meta vx-mt2">${esc(opt.note)}</div>`:'')+'</div>';
}
/* Une couleur par TYPE d'actif, jamais par titre : le violet est reserve aux
   options (regle de palette), le reste reste structurel argent/gris. */
function allocColor(assetType){
  return {OPTION:'var(--vx-options)',ETF:'var(--vx-steel-3, #7f8794)'}[assetType]
    ||'var(--vx-silver, #c9ced8)';
}
async function renderAllocation(){
  const body=$('pf-body');if(!body)return;
  /* Pas de cockpit `renderSummary` ici : il valorise AU COUT quand les marques
     manquent, le moteur valorise A LA MARQUE. Les deux tuiles s'appelaient
     « Valeur » et affichaient deux nombres differents a trois centimetres
     d'ecart. Cette sous-vue ne montre que la valorisation du moteur. */
  const pos=E().positions();
  ($('pf-summary')||{}).innerHTML='';
  let d=null,err=null;
  try{d=await VX.fetch('/api/portfolio/context',{ttl:60000});}catch(e){err=e;}
  if(err){body.innerHTML=VX.states.error('Contexte portefeuille indisponible : '+err.message);return;}
  if(!d||!d.available){
    body.innerHTML='<div class="vx2-state" data-kind="empty" role="status">'
      +'<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
      +'<p class="vx2-state-title">Allocation incalculable</p>'
      +'<p class="vx2-state-cause">'+esc((d&&d.reason)||'contexte portefeuille indisponible')+'</p>'
      +'<p class="vx2-state-cause">Les poids, la concentration et le mix sectoriel '
      +'exigent au moins une position déclarée et valorisée.</p>'
      +'<div class="vx2-state-actions">'
      +'<button type="button" class="vx2-btn" data-variante="primaire" '
      +'onclick="VXEntities.openAddModal(\'\',\'position\')">Déclarer une position</button></div></div>';
    return;
  }
  /* Type d'actif par titre : le moteur donne le mix, la position donne le type.
     La jointure sert UNIQUEMENT a colorer — aucun poids n'est recalcule. */
  const typeOf={};pos.forEach(t=>{typeOf[String(t.sym).toUpperCase()]=(t.type==='STK')?'STOCK':(t.type==='ETF'?'ETF':'OPTION');});
  const b=d.bounds||{},maxW=(d.sizing&&d.sizing.max_stock_weight_pct)||15;
  const hhiTone=d.hhi==null?'':(d.hhi>=0.25?'neg':d.hhi>=0.18?'warn':'pos');
  const topOver=(d.top_weight_pct||0)>maxW;
  const cov=d.sector_coverage||{};
  const rb=d.risk_budget||{};
  /* Tons canoniques : la CSS 2.0 lit `positive|negative|caution|missing` sur la
     VALEUR, pas sur la carte. Les abreviations `pos/neg/warn` employees ailleurs
     dans ce fichier ne peignent rien ici — d'ou la traduction. */
  const TON={pos:'positive',neg:'negative',warn:'caution','':'',undefined:''};
  const k=(label,val,sub,tone)=>`<div class="vx2-metric">`
    +`<span class="vx2-metric-label">${label}</span>`
    +`<span class="vx2-metric-value" data-tone="${TON[tone]||''}">${val}</span>`
    +(sub?`<span class="vx2-metric-meta">${sub}</span>`:'')+`</div>`;

  body.innerHTML=`
    <div class="vx2-strip vx-mb3">
      ${k('Valeur suivie',VX.fmt.num(d.total_value,0)+' $',esc((d.provenance||[]).join(' + '))||'—')}
      ${k('Lignes',d.n_positions+' / '+(b.min??'?')+'–'+(b.max??'?'),
          d.in_bounds?'dans les bornes':(d.n_positions<(b.min||0)?'sous la cible · '+d.free_slots+' place(s)':'au-dessus de la cible'),
          d.in_bounds?'pos':'warn')}
      ${k('Poids du plus gros titre',VX.fmt.num(d.top_weight_pct,1)+' %',
          esc(d.top_symbol||'—')+(topOver?' · au-dessus du plafond '+maxW+' %':' · plafond '+maxW+' %'),
          topOver?'neg':'')}
      ${k('HHI',d.hhi!=null?VX.fmt.num(d.hhi,3):'—',
          /*  Le même mot « HHI » vit sur la vue Risque avec une AUTRE base
              (compartiment actions renormalisé à 100 %) et un AUTRE barème
              (33/66 sur HHI×100) : mesuré, 0,30 s'y lit « bien dispersé » et
              ici « concentré ». `hhi_basis` est servi par les deux routes ;
              le peindre est la seule façon de ne pas laisser le lecteur croire
              qu'il regarde deux fois le même indice. */
          esc(d.hhi==null?'non calculable':(d.hhi>=0.25?'concentré':d.hhi>=0.18?'modérément concentré':'dispersé')
              +(d.hhi_basis?' · '+d.hhi_basis:' · base non servie')),hhiTone)}
    </div>
    ${d.valuation_note?`<div class="vx2-banner" data-kind="prudence" role="status"><span>${esc(d.valuation_note)}</span></div>`:''}
    ${d.asset_mix_note?`<div class="vx2-banner" data-kind="prudence" role="status"><span>${esc(d.asset_mix_note)}</span></div>`:''}
    <div class="vx-grid vx-mb3">
      <div class="vx-col-7"><div class="vx2-surface">
        <div class="vx2-card-head"><span class="vx2-card-title">Poids par position</span>
        <span class="vx2-card-question">Où le capital est-il réellement concentré ?</span></div>
        <div id="pf-alloc-treemap" style="height:280px"></div>
        <div class="vx2-stamp vx-mt2">Aire = poids au portefeuille · argent = action · violet = option.</div>
        <div id="pf-alloc-note" class="vx-mt2"></div>
      </div></div>
      <div class="vx-col-5"><div class="vx2-surface">
        <div class="vx2-card-head"><span class="vx2-card-title">Mix par type d’actif</span></div>
        ${allocBars(Object.keys(d.asset_mix||{}).map(a=>({k:a,v:d.asset_mix[a].weight_pct,color:allocColor(a)})),'%',
          {note:'Un type d’actif absent du référentiel n’est jamais classé par défaut.'})}
      </div></div>
    </div>
    <div class="vx-grid vx-mb3">
      <div class="vx-col-6"><div class="vx2-surface">
        <div class="vx2-card-head"><span class="vx2-card-title">Exposition sectorielle</span>
        <span class="vx2-card-question">Quel secteur porte le risque commun ?</span></div>
        ${cov.available
          ? allocBars(Object.keys(d.sector_mix||{}).map(sc=>({k:sc,v:d.sector_mix[sc].weight_pct})),'%')
            +(cov.unclassified_value_pct>0
              ? `<div class="vx2-banner" data-kind="prudence" role="status"><span>`
                +`${VX.fmt.num(cov.unclassified_value_pct,1)} % de la valeur hors référentiel sectoriel`
                +` (${esc((cov.unclassified_symbols||[]).join(', ')||'—')}) — non répartie, jamais attribuée d’office.</span></div>`
              : '')
          : `<div class="vx2-state" data-kind="missing" role="status">`
            +`<p class="vx2-state-title">Secteurs non couverts</p>`
            +`<p class="vx2-state-cause">Aucun titre du portefeuille n’est présent dans le référentiel sectoriel.</p></div>`}
      </div></div>
      <div class="vx-col-6"><div class="vx2-surface">
        <div class="vx2-card-head"><span class="vx2-card-title">Budget de risque au stop</span>
        <span class="vx2-card-question">Combien le plan de sortie met-il en jeu ?</span></div>
        ${rb.available
          ? `<div class="vx2-strip vx-mb2">
               ${k('Risque connu',VX.fmt.num(rb.known_risk_to_stop,0)+' $','stop × quantité')}
               ${k('Couverture',VX.fmt.num(rb.coverage_pct,0)+' %',rb.covered_positions+' / '+rb.total_positions+' position(s)',
                   rb.coverage_pct>=80?'pos':'warn')}
             </div>`
            +allocBars((rb.by_position||[]).map(x=>({k:x.symbol,v:x.risk_to_stop})),'$',
               {note:'Échelle en dollars de risque au stop, pas en pourcentage de poids.'})
            +((rb.unmeasured||[]).length?`<div class="vx2-banner" data-kind="prudence" role="status"><span>`
               +`${(rb.unmeasured||[]).length} position(s) sans risque mesurable : `
               +`${esc((rb.unmeasured||[]).map(u=>u.symbol+' — '+u.reason).join(' · '))}</span></div>`:'')
          : `<div class="vx2-state" data-kind="missing" role="status">`
            +`<p class="vx2-state-title">Budget de risque non mesurable</p>`
            +`<p class="vx2-state-cause">Aucune position ne porte à la fois une cote, un stop et une quantité.</p></div>`}
      </div></div>
    </div>
    <div class="vx-grid vx-mb3"><div class="vx-col-12" id="pf-alloc-corr"></div></div>
    <div class="vx-grid vx-mb3"><div class="vx-col-12"><div class="vx2-surface">
      <div class="vx2-card-head"><span class="vx2-card-title">Expositions factorielles</span></div>
      ${(d.factor_exposure&&d.factor_exposure.available)
        ? allocBars(Object.keys(d.factor_exposure.factors||{})
            .filter(f=>d.factor_exposure.factors[f].value!=null)
            .map(f=>({k:f,v:d.factor_exposure.factors[f].value})),'')
        : `<div class="vx2-state" data-kind="missing" role="status">`
          +`<p class="vx2-state-title">Facteurs non couverts</p>`
          +`<p class="vx2-state-cause">Le moteur factoriel existe mais ne couvre `
          +`${VX.fmt.num((d.factor_exposure||{}).coverage_pct_max||0,0)} % de la valeur : `
          +`marché, bêta, taille, valeur, qualité et croissance restent non mesurés ici.</p></div>`}
    </div></div></div>
    <div class="vx-grid"><div class="vx-col-12">${VX2_ALLOC_ABSENCES}</div></div>`;

  /* Treemap des poids — le moteur donne `weights`, la carte ne fait que
     l'ordonner et l'aerer. Aucun poids n'est recompose. */
  if(window.VXCharts&&VXCharts.treemap){
    const items=Object.keys(d.weights||{}).map(sym=>({label:sym,value:+d.weights[sym],
      color:allocColor(typeOf[sym]||'STOCK'),sub:''}));
    VXCharts.treemap('pf-alloc-treemap',{items:items,unit:'% du portefeuille',
      /* Question déjà posée par la surface hôte, juste au-dessus. */
      source:'portfolio_context',timestamp:d.as_of||null,mode:'delayed',
      limits:'aire = poids au portefeuille · argent = action · violet = option',
      width:640,height:280,fmt:(v)=>VX.fmt.num(v,1)+' %',
      emptyHtml:'<div class="vx2-state" data-kind="empty"><p class="vx2-state-title">Aucun poids calculable</p></div>'});
    /* Une tuile sous ~0,3 % du cadre ne recoit aucun libelle lisible : elle
       disparait dans le trait de separation. La taire ferait lire « tout le
       portefeuille est ici » — on la NOMME sous le graphique. */
    const invisibles=items.filter(i=>i.value>0&&i.value<0.3).map(i=>i.label);
    const note=$('pf-alloc-note');
    if(note&&invisibles.length)note.innerHTML='<span class="vx2-badge" data-state="missing">'
      +invisibles.length+' position(s) trop petite(s) pour être dessinée(s)&nbsp;: '
      +esc(invisibles.join(', '))+'</span>';
  }
  corrHeatmap('pf-alloc-corr',d.correlations||{});
}

/* ═══ THESES ════════════════════════════════════════════════════════════
   `portfolio-center.md` range watchlist ET theses dans une meme sous-vue :
   « chaque element conserve pourquoi maintenant, catalyseur, invalidation,
   horizon, priorite, prochaine revue ». La watchlist portait deja ce contrat ;
   les theses des positions OUVERTES, elles, n'etaient lisibles nulle part —
   `thesisState()` les calculait pour une pastille de tableau, et le texte de
   la these ne s'affichait qu'au survol d'un attribut `title`.

   Rien n'est calcule ici : `thesisState` et `nextAction` sont les fonctions
   deja employees par la vue Positions, appelees telles quelles.

   La carte n'utilise PAS `.vx2-rowcard` : cette classe vit dans
   `.vx2-rowcards`, qui est `display:none` au-dessus de 760 px — c'est le
   repli mobile des tables, pas une carte de contenu. */
const THESE_ETAT={neg:'stale',warn:'delayed',pos:'live',muted:'missing'};
/* Le reste du fichier ecrit `type!=='STK'` ; le desk ne produit que STK, CALL
   et PUT, donc les deux formes coincident aujourd'hui. Celle-ci dit ce qu'elle
   teste, et ne rangerait pas un ETF parmi les options. */
const estOption=(t)=>t.type==='CALL'||t.type==='PUT'||t.right==='C'||t.right==='P';
async function thesesPositions(){
  const pos=E().positions();
  if(!pos.length)return '';
  const rich=enrich(pos,await quotesFor(pos));
  const cell=(label,html)=>`<div class="vx2-these-cell"><dt>${label}</dt><dd>${html}</dd></div>`;
  const abs=(txt)=>`<span class="vx2-absent">${txt}</span>`;
  const cartes=rich.map(t=>{
    const st=thesisState(t),act=nextAction(t),snap=t.entrySnap||{};
    const stop=Number(snap.stop);
    const hasStop=isFinite(stop)&&stop>0;
    const mark=estOption(t)?t.underSpot:t.mark;
    const dist=(hasStop&&mark!=null)?((mark-stop)/stop*100):null;
    return `<article class="vx2-these" data-etat="${st.key}">
      <div class="vx2-these-head">
        <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(t.sym)}">${esc(t.sym)}</button>
        <span class="vx2-badge" data-state="${THESE_ETAT[st.tone]||'missing'}">${esc(st.label)}</span>
        ${estOption(t)?'<span class="vx2-badge" data-state="option">Option</span>':''}
      </div>
      <p class="vx2-these-texte">${snap.thesis?esc(snap.thesis)
        :abs('Thèse non écrite — sans thèse écrite, aucun fait ne peut l’invalider.')}</p>
      <dl class="vx2-these-grid">
        ${cell('Invalidation',hasStop?'<span class="vx2-mono">'+VX.fmt.price(stop)+'</span>':abs('non définie'))}
        ${cell('Distance',dist!=null?'<span class="vx2-mono">'+(dist>=0?'+':'')+VX.fmt.num(dist,1)+'&nbsp;%</span>':abs('n.d.'))}
        ${cell('Objectif',snap.tgt!=null?'<span class="vx2-mono">'+VX.fmt.price(snap.tgt)+'</span>':abs('non défini'))}
        ${cell('Catalyseur',snap.catalyst?esc(snap.catalyst):abs('n.d.'))}
        ${cell('Depuis le',t.added?esc(t.added):abs('n.d.'))}
      </dl>
      <p class="vx2-these-action"><b>Prochaine action analytique&nbsp;:</b>
        <span class="${toneCls(act.tone)}">${esc(act.label)}</span></p>
    </article>`;}).join('');
  return `<section class="vx2-section" aria-label="Thèses des positions ouvertes">
    <div class="vx2-section-head"><h2 class="vx2-section-title">Thèses des positions ouvertes</h2>
      <span class="vx2-section-note">${rich.length} position(s) — l’état de thèse ne se déduit jamais du seul prix</span></div>
    <div class="vx2-theses">${cartes}</div>
    <p class="vx2-stamp vx-mt2">Seul le franchissement de l’invalidation prédéfinie casse une thèse.
      Une baisse de prix, à elle seule, ne la casse jamais.</p></section>`;
}
async function renderTheses(){
  await renderWatchlist();
  const body=$('pf-body');if(!body)return;
  const html=await thesesPositions();
  if(!html)return;
  /* `data-open-analysis` porte deja un delegue global (vx-entities.js) :
     ne rien recabler ici, sinon chaque clic ouvrirait deux fois. */
  const holder=document.createElement('div');
  holder.innerHTML=html;
  const sec=holder.firstElementChild;
  if(sec)body.insertBefore(sec,body.firstChild);
}

const RENDER={team:renderTeam,positions:renderPositions,
  allocation:renderAllocation,options:renderOptions,
  risk:async function(){await renderRisk();await renderStress();await renderDiscipline();await renderHiddenDeps();},
  theses:renderTheses,performance:renderPerformance};
async function pfFresh(){
  const el=$('pf-fresh');if(!el)return;
  /* `VX.freshness.assess({ageMs:null})` rend l'etat `unknown`, dont le libelle
     est le tiret « — ». Pose seul a cote d'un bouton, ce tiret ne nommait ni
     sa grandeur ni son absence : l'ecran affichait un signe, pas une
     information. Quand l'age manque, on ecrit POURQUOI. */
  const dire=(txt,etat)=>{el.innerHTML='<span class="vx2-badge" data-state="'+etat+'">'+txt+'</span>';};
  if(!window.VX||!VX.freshness){dire('Fraîcheur non évaluée','missing');return;}
  let pk=VX.fetch.peek('/api/session/manifest');
  if(!pk){try{await VX.fetch('/api/session/manifest',{ttl:30000});pk=VX.fetch.peek('/api/session/manifest');}catch(e){}}
  const live=!(window.__vxStatus&&window.__vxStatus.demo);
  /* Age HONNETE = anciennete reelle de la session (manifest.age_s), pas l'age de
     l'entree de cache : un manifest resservi doit refleter l'age de la DONNEE. */
  const a=(pk&&pk.data&&typeof pk.data.age_s==='number')?pk.data.age_s*1000:null;
  if(a==null){dire('Session non horodatée — âge inconnu','missing');return;}
  el.innerHTML=VX.freshness.chip(VX.freshness.assess({ageMs:a,live:live}));
}
/* Diffusion (P1) : rejeu sur événement serveur (cotations, scan) — le
   portefeuille est déclaré localement, la sous-vue vient de l'URL. */
if(window.VX&&VX.refresh&&VX.refresh.register)VX.refresh.register(function(){pfFresh();return (RENDER[VIEW]||renderTeam)();},15*60*1000,'portefeuille-live');
function boot(){pfFresh();(RENDER[VIEW]||renderTeam)().catch(e=>{($('pf-body')||{}).innerHTML=VX.states.error(e.message);});}
if(window.VXCharts&&window.Chart)boot();else window.addEventListener('load',boot,{once:true});
['vx:position-changed','vx:watchlist-changed','vx:follow-changed','vx:favorites-changed']
  .forEach(ev=>VX.bus.on(ev,(e)=>{if((e.detail||{}).source!=='sync')return boot();boot();}));
})();
</script>
"""


# `portfolio-center.md` réclame six axes d'exposition. Vertex en calcule deux.
# Les quatre autres sont DÉCLARÉS absents : la refonte 2.0 est visuelle et ne
# développe aucun moteur — fabriquer un pays ou une devise dans un template
# produirait un chiffre sans source, ce que la règle n°4 interdit.
_ABSENCES = (
    '<div class="vx2-strip">'
    + vx2.capacite_absente(
        quoi='Exposition par devise',
        pourquoi='Les positions déclarées ne portent pas de devise exploitable '
                 'et aucun moteur de change n’alimente le portefeuille.')
    + vx2.capacite_absente(
        quoi='Exposition par pays',
        pourquoi='Aucun référentiel pays n’est branché ; le référentiel '
                 'sectoriel existant ne porte pas de domiciliation.')
    + vx2.capacite_absente(
        quoi='Exposition par thème',
        pourquoi='Vertex ne tient pas de taxonomie thématique canonique.')
    + vx2.capacite_absente(
        quoi='Transparence ETF (look-through)',
        pourquoi='Elle exige les composants datés de chaque ETF ; sans holdings '
                 'à date, un ETF est compté comme une ligne, jamais éclaté.')
    + '</div>')


def _entete(view: str) -> str:
    """En-tête + barre de contexte. La fraîcheur porte un LIBELLÉ : l'ancien
    emplacement rendait un tiret nu, à côté d'un bouton, sans dire de quoi il
    parlait — un `—` qui ne nomme pas sa grandeur n'informe de rien."""
    return (
        vx2.page_header(
            surtitre='Gérer', titre='Portefeuille',
            question='Que possède le portefeuille, pourquoi, et avec quels risques ?',
            actions=(
                vx2.bouton('Déclarer une position', variante='primary',
                           attrs=' onclick="VXEntities.openAddModal(\'\',\'position\')"')
                + vx2.bouton('Ajouter à la watchlist',
                             attrs=' onclick="VXEntities.openAddModal(\'\',\'watchlist\')"')
                + vx2.bouton('Ouvrir le Suivi', href='/follow-up', variante='ghost')))
        + vx2.context_bar([
            {'label': 'Périmètre', 'contenu':
                '<span class="vx2-stamp">Positions déclarées au desk '
                '<b>+ IBKR en lecture seule</b></span>'},
            {'label': 'Valorisation', 'contenu':
                '<span class="vx2-stamp">Marque du scan, sinon '
                '<b>au coût</b> — jamais un prix inventé</span>'},
            {'label': 'Fraîcheur', 'contenu':
                '<span id="pf-fresh">'
                + vx2.badge_etat('missing', texte='Lecture…') + '</span>'},
        ]))


def render(view: str = 'team') -> str:
    view = _ALIAS.get(view, view)
    view = view if view in dict(_VIEWS) else 'team'
    content = (_CONTENT.replace('%%HEADER%%', _entete(view))
               .replace('%%TABS%%', _tabs(view))
               .replace('%%LOADING%%', '<div class="vx-skeleton" style="height:120px"></div>'))
    label = dict(_VIEWS)[view]
    return render_shell(title=f'Portefeuille · {label}', active='portfolio',
                        space_label='Portefeuille', sub_label=label,
                        content=content,
                        page_js=(_JS.replace('%%VIEW%%', json_for_script(view))
                                 .replace('%%ABSENCES%%', json_for_script(_ABSENCES))),
                        page_label=f'Portefeuille {label}')
