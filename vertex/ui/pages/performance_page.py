"""vertex.ui.pages.performance_page — l'espace Journal (§27, refonte PR n°7).

Question unique : « Suis-je en train de devenir un meilleur investisseur ? »

Le Journal ne mesure PLUS la performance du portefeuille (courbe, drawdown,
contribution) : elle vit définitivement dans Portefeuille → Performance (§6, un
seul domicile, migration PR n°5). Le Journal est exclusivement le lieu de la
DISCIPLINE : qualité des décisions, respect de la méthode, erreurs, apprentissage,
revue des hypothèses, statistiques comportementales.

Sous-vues (?view=) : overview (Discipline) · journal (Chronologie) · learnings
(Apprentissage) · progression · track-record (Historique).

Le module Python ne fait AUCUN calcul financier : il assemble le squelette + le
script client. Les agrégations côté client portent uniquement sur les décisions
DÉCLARÉES par l'utilisateur (localStorage via VXEntities) — jamais des indicateurs
de marché. Donnée absente → état honnête (jamais un pourcentage inventé).
"""
from __future__ import annotations

import html
import re

from vertex.ui import vx2
from vertex.ui.shell import render_shell

# Ordre canonique de `navigation-and-pages.md` §10. « Historique » portait
# DEUX populations dans une seule vue — le moteur et le journal declare — avec
# une phrase pour prevenir de ne pas les confondre. Le contrat demande de les
# separer, et c'est plus sur qu'une phrase : deux vues ne se melangent pas.
#
# « Tracking hypothetique » n'est PAS ajoute ici : il appartient a Suivi, qui
# le sert depuis `/api/tracking`. Le panneau « Populations mesurees » y renvoie.
# En faire un onglet dupliquerait une verite qui doit n'avoir qu'un domicile.
_VIEWS = (
    ('overview', 'Synthèse'),
    ('journal', 'Journal'),
    ('real', 'Trades réels'),
    ('track-record', 'Signaux théoriques'),
    ('progression', 'Progression'),
    ('learnings', 'Apprentissages'),
)

# L'ancienne URL « Historique » menait aux deux ; elle mene aux signaux, et la
# vue le dit avec un renvoi vers l'autre population.
_ALIAS = {'history': 'track-record'}


def _tabs(view: str) -> str:
    return vx2.tabs([{'label': label, 'href': f'?view={vid}', 'actif': vid == view}
                     for vid, label in _VIEWS],
                    libelle='Sous-vues de la Performance')


# ── Les CINQ populations du contrat ───────────────────────────────────────
# « Ne jamais fusionner dans un même KPI » : trades réels déclarés, positions
# IBKR, signaux théoriques moteurs, idées suivies hypothétiquement, simulations
# options. Chacune a sa source, son propriétaire et sa nature de rendement —
# et la page doit le DIRE, pas l'espérer.
_POPULATIONS = (
    {'ident': 'reels', 'titre': 'Trades réels déclarés',
     'nature': 'Réalisé — encaissé', 'source': 'journal du desk',
     'ici': True, 'ou': None,
     'note': 'La seule population mesurée par les indicateurs de cette page.'},
    {'ident': 'ibkr', 'titre': 'Positions IBKR',
     'nature': 'Latent — non encaissé', 'source': 'IBKR en lecture seule',
     'ici': False, 'ou': '/portfolio?view=positions',
     'note': 'Valorisation en cours, jamais additionnée à un résultat clos.'},
    {'ident': 'signaux', 'titre': 'Signaux théoriques moteurs',
     'nature': 'Théorique — aucun capital engagé', 'source': '/api/track-record',
     'ici': True, 'ou': '/performance?view=track-record',
     'note': 'Rendements sur clôtures quotidiennes ; ni frais ni exécution.'},
    {'ident': 'suivis', 'titre': 'Idées suivies',
     'nature': 'Hypothétique — jamais encaissé', 'source': '/api/tracking',
     'ici': False, 'ou': '/follow-up',
     'note': 'Comparées à SPY depuis la date de marquage.'},
    {'ident': 'simulations', 'titre': 'Simulations options',
     'nature': 'Scénario — hypothèses explicites', 'source': None,
     'ici': False, 'ou': '/simulator',
     'note': 'Aucune persistance canonique : rien à mesurer dans la durée.'},
)


def _populations() -> str:
    lignes = []
    for pop in _POPULATIONS:
        if pop['ici']:
            etat = vx2.badge_etat('live', texte='Mesurée ici')
        elif pop['source'] is None:
            etat = vx2.badge_etat('missing', texte='Non conservée')
        else:
            etat = vx2.badge_etat('missing', texte='Mesurée ailleurs')
        lien = (vx2.bouton('Ouvrir', href=pop['ou'], variante='ghost')
                if pop['ou'] else '')
        lignes.append(
            '<article class="vx2-population">'
            f'<div class="vx2-population-head"><strong>{pop["titre"]}</strong>{etat}</div>'
            f'<p class="vx2-population-nature">{pop["nature"]}</p>'
            f'<p class="vx2-population-note">{pop["note"]}</p>'
            '<p class="vx2-population-source">Source&nbsp;: '
            + (f'<code>{pop["source"]}</code>' if pop['source']
               else '<span class="vx2-absent">aucune</span>')
            + f'</p>{lien}</article>')
    return vx2.section(
        titre='Populations mesurées',
        note='un indicateur ne mélange jamais deux de ces lignes',
        corps='<div class="vx2-populations">' + ''.join(lignes) + '</div>')


_HEADER = """
%%ENTETE%%
%%TABS%%
"""

_VIEW_CONTENT = {
    'overview': """
<section class="vx2-surface vx-mt3" id="vx-pf-hero" aria-label="Verdict de discipline">
  <div class="vx2-card-head"><div><h2 class="vx2-card-title">Verdict de discipline</h2>
    <p class="vx2-card-question">La m&eacute;thode est-elle appliqu&eacute;e&nbsp;?</p></div></div>
  <div class="vx2-state" data-kind="missing" role="status">
    <span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
    <p class="vx2-state-title">Verdict de discipline &mdash; calcul non disponible dans Vertex</p>
    <p class="vx2-state-cause">Aucun moteur ne produit ce verdict. Le chargeur qui devait
      remplir ce bloc appelait une fonction qui n&rsquo;existait pas&nbsp;; il a &eacute;t&eacute; retir&eacute;.
      Le bloc affichait depuis un squelette perp&eacute;tuel &mdash; une donn&eacute;e promise qui
      n&rsquo;arrivait jamais. Rien n&rsquo;est invent&eacute; pour le remplir&nbsp;: les mesures r&eacute;elles
      de discipline sont ci-dessous.</p></div></section>
<div class="vx-kpi-strip vx-mt3" id="vx-pf-kpis" data-max-kpis="4" aria-label="R&eacute;sultats des trades d&eacute;clar&eacute;s"><div class="vx-skeleton vx-skeleton-kpi"></div></div>
<div class="vx-mt4" id="vx-pf-discipline" aria-label="Mesures de discipline"><div class="vx-skeleton" style="height:80px"></div></div>
%%POPULATIONS%%
<div class="vx-grid vx-mt4">
  <div class="vx-col-8" id="vx-pf-equity"></div>
  <aside class="vx-col-4" id="vx-pf-drawdown"></aside>
</div>
<div class="vx-grid vx-mt3"><div class="vx-col-12">%%MENSUEL%%</div></div>
<div class="vx-hero-grid vx-mt4">
  <section class="vx-card" aria-label="Revue des hypothèses">
    <div class="vx-card-header"><span class="vx-card-title">Revue des hypothèses</span>
      <span class="vx-chart-question">Mes thèses se vérifient-elles ?</span></div>
    <div id="vx-pf-hypo"><div class="vx-skeleton" style="height:80px"></div></div>
  </section>
  <aside class="vx-insight-rail" aria-label="Prochain axe de travail">
    <div class="vx-insight" id="vx-pf-next-axis" data-tone="neutral">
      <div class="vx2-state" data-kind="missing" role="status">
        <p class="vx2-state-title">Prochain axe de travail &mdash; non produit</p>
        <p class="vx2-state-cause">Aucun moteur de Vertex ne d&eacute;signe d&rsquo;axe de travail.
          Le besoin est consign&eacute;&nbsp;; il n&rsquo;est pas simul&eacute;.</p></div></div>
  </aside>
</div>
<div class="vx-section-stack vx-mt4">
  <details class="vx-disclosure" id="vx-pf-results-disclosure">
    <summary>R&eacute;sultats d&eacute;clar&eacute;s &middot; P&amp;L, r&eacute;ussite et profit factor</summary>
    <div class="vx-disclosure__body">
      <div class="vx-page-lead vx-mb3"><b>Mesure descriptive du journal.</b>
        <span class="vx-meta">La performance de portefeuille reste dans <a href="/portfolio?view=performance">Portefeuille &rarr; Performance</a>.</span></div>
      <div class="vx-hero-grid">
        <section class="vx-card" aria-label="Post-mortem des trades clôturés">
          <div class="vx-card-header"><span class="vx-card-title">Post-mortem &mdash; que disent mes sorties&nbsp;?</span>
            <span class="vx-chart-question">Stats r&eacute;elles et drapeaux de discipline. Descriptif, pas un conseil.</span></div>
          <div id="vx-pf-postmortem">%%LOADING%%</div>
        </section>
        <div id="vx-pf-dist"></div>
      </div>
    </div>
  </details>
  <details class="vx-disclosure" id="vx-pf-history-disclosure">
    <summary>Avanc&eacute; &middot; calibration et m&eacute;moire du moteur</summary>
    <div class="vx-disclosure__body vx-section-stack">
      <div class="vx-toolbar">
        <span class="vx-meta">Historique technique, calibration et ledger immuable.</span>
        <a class="vx-btn vx-btn-sm vx-btn-ghost" href="?view=track-record">Ouvrir Historique &rarr;</a>
      </div>
      <section class="vx-card" aria-label="Calibration Skyler">
        <div class="vx-card-header"><span class="vx-card-title">Calibration Skyler</span>
          <span class="vx-chart-question">D&eacute;cisions canoniques et rendements r&eacute;els ; Brier indisponible tant qu&rsquo;il ne peut pas &ecirc;tre mesur&eacute;.</span></div>
        <div id="vx-pf-calibration">%%LOADING%%</div>
      </section>
      <section class="vx-card" aria-label="Mémoire décisionnelle">
        <div class="vx-card-header"><span class="vx-card-title">M&eacute;moire d&eacute;cisionnelle</span>
          <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/api/skyler/memory/export" download>Exporter &rarr;</a>
            <label class="vx-btn vx-btn-sm vx-btn-ghost" for="vx-mem-import-file" style="cursor:pointer">Importer &larr;</label>
            <input type="file" id="vx-mem-import-file" accept="application/json,.json" style="display:none"></span></div>
        <div id="vx-mem-import-result"></div>
        <div id="vx-pf-memory">%%LOADING%%</div>
      </section>
    </div>
  </details>
</div>
""",
    'journal': """
<div class="vx-page-lead vx-mt3">
  <div><h2>Chronologie des d&eacute;cisions</h2><div class="vx-sub">Retrouver une d&eacute;cision, sa raison et la le&ccedil;on d&eacute;clar&eacute;e.</div></div>
</div>
<div class="vx-toolbar vx-mt3" role="search" aria-label="Outils de la chronologie">
  <input class="vx-input" id="vx-pf-filter" data-filter-key="sym" placeholder="Filtrer par ticker"
    value="%%SYM%%" autocomplete="off" style="max-width:190px;text-transform:uppercase" aria-label="Filtrer par ticker" />
  <button class="vx-btn vx-btn-sm vx-btn-primary" id="vx-pf-add">Ajouter une entrée</button>
</div>
<div class="vx-hero-grid vx-mt3">
  <section class="vx-card" aria-label="Chronologie des décisions">
    <div class="vx-card-header"><span class="vx-card-title">D&eacute;cisions d&eacute;clar&eacute;es</span></div>
    <div id="vx-pf-journal">%%LOADING%%</div>
  </section>
  <aside class="vx-insight-rail" aria-label="Statistiques d'erreurs">
    <section class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Erreurs déclarées</span></div>
      <div id="vx-pf-mistakes">%%LOADING%%</div></section>
  </aside>
</div>
""",
    'learnings': """
<div class="vx-grid vx-mt3">
  <section class="vx-card vx-col-6" aria-label="Leçons du journal">
    <div class="vx-card-header"><span class="vx-card-title">Leçons apprises</span></div>
    <div id="vx-pf-lessons">%%LOADING%%</div>
  </section>
  <section class="vx-card vx-col-6" aria-label="Erreurs récurrentes">
    <div class="vx-card-header"><span class="vx-card-title">Erreurs récurrentes</span></div>
    <div id="vx-pf-recurrent">%%LOADING%%</div>
    <div class="vx-card-footer">
      <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/intelligence?view=memory">Règles proposées (Intelligence / Mémoire) →</a>
    </div>
  </section>
</div>
<div class="vx-grid vx-mt4">
  <section class="vx-card vx-col-12" aria-label="Biais comportementaux">
    <div class="vx-card-header"><span class="vx-card-title">Biais comportementaux</span>
      <span class="vx-chart-question">Quel état émotionnel accompagne mes décisions ?</span></div>
    <div id="vx-pf-biais">%%LOADING%%</div>
  </section>
</div>
""",
    'progression': """
<div class="vx-grid vx-mt3">
  <section class="vx-card vx-col-12" aria-label="Progression de la discipline">
    <div class="vx-card-header"><span class="vx-card-title">Ma progression</span>
      <span class="vx-chart-question">Est-ce que je m'améliore, décision après décision ?</span></div>
    <div id="vx-pf-prog">%%LOADING%%</div>
  </section>
</div>
""",
    'track-record': """
<div class="vx2-section vx-mt3"><div class="vx2-section-head">
  <h2 class="vx2-section-title">Signaux th&eacute;oriques</h2>
  <span class="vx2-section-note">rendements des verdicts moteur &mdash; aucun capital engag&eacute;</span></div></div>
<div class="vx2-banner" data-kind="prudence" role="status"><span>Population&nbsp;:
  <b>verdicts rendus par les moteurs</b>, mesur&eacute;s sur cl&ocirc;tures quotidiennes.
  Ni frais, ni ex&eacute;cution, ni glissement. Ces chiffres ne se m&eacute;langent
  <b>jamais</b> avec vos trades d&eacute;clar&eacute;s, qui vivent dans
  <a href="?view=real">Trades r&eacute;els</a>.</span></div>
<div class="vx-section-stack vx-mt4">
  <section class="vx-card" aria-label="Historique théorique du moteur" data-source-kind="engine">
    <div class="vx-card-header"><span class="vx-card-title">Moteur &middot; verdicts th&eacute;oriques</span>
      <span class="vx-badge">Source API moteur</span></div>
    <div id="vx-pf-track">%%LOADING%%</div>
  </section>
</div>
""",

    'real': """
<div class="vx2-section vx-mt3"><div class="vx2-section-head">
  <h2 class="vx2-section-title">Trades r&eacute;els</h2>
  <span class="vx2-section-note">vos cl&ocirc;tures d&eacute;clar&eacute;es &mdash; r&eacute;alis&eacute;, encaiss&eacute;</span></div></div>
<div class="vx2-banner" data-kind="prudence" role="status"><span>Population&nbsp;:
  <b>trades que vous avez d&eacute;clar&eacute;s</b> au journal, avec un r&eacute;sultat et un
  P&amp;L. Agr&eacute;gations arithm&eacute;tiques, hors frais et dividendes. Ces chiffres ne
  se m&eacute;langent <b>jamais</b> avec les verdicts moteur, qui vivent dans
  <a href="?view=track-record">Signaux th&eacute;oriques</a>.</span></div>
<div class="vx-section-stack vx-mt4">
  <section class="vx-card" aria-label="Historique déclaré du journal" data-source-kind="declared">
    <div class="vx-card-header"><span class="vx-card-title">Journal &middot; trades d&eacute;clar&eacute;s</span>
      <span class="vx-badge">Vos d&eacute;clarations</span>
      <span class="vx-actions"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="?view=journal">Ouvrir la chronologie &rarr;</a></span></div>
    <div id="vx-pf-real">%%LOADING%%</div>
  </section>
</div>
""",
}

_JS = r"""
<script src="/static/vertex/js/charts/bar-chart.js" defer></script>
<script src="/static/vertex/js/charts/heatmap.js" defer></script>
<script src="/static/vertex/js/charts/equity-chart.js" defer></script>
<script src="/static/vertex/js/charts/drawdown-chart.js" defer></script>
<script>
(function(){
'use strict';
const VIEW='%%VIEW%%';
const $=(id)=>document.getElementById(id);
const E=()=>window.VXEntities;
function esc(s){return String(s??'').replace(/[<>&"']/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));}
function trades(){/* entrées avec un résultat déclaré et un P&L numérique */
  return (E()?E().journal():[]).filter(e=>(e.result==='WIN'||e.result==='LOSS')&&isFinite(Number(e.pnl)));
}
function stats(list){
  const pnls=list.map(e=>Number(e.pnl));
  const wins=pnls.filter(p=>p>0),losses=pnls.filter(p=>p<0);
  const gains=wins.reduce((a,b)=>a+b,0),pertes=Math.abs(losses.reduce((a,b)=>a+b,0));
  const avgWin=wins.length?gains/wins.length:null,avgLoss=losses.length?-(pertes/losses.length):null;
  /* Drawdown max chiffré : plus grand repli du cumul de P&L (ordre chronologique). */
  let maxDD=0;{let cum=0,peak=0;list.slice().sort((a,b)=>String(a.date||'').localeCompare(String(b.date||'')))
    .forEach(e=>{cum+=Number(e.pnl)||0;peak=Math.max(peak,cum);maxDD=Math.min(maxDD,cum-peak);});}
  return {n:list.length,
    total:pnls.reduce((a,b)=>a+b,0),
    winRate:list.length?100*list.filter(e=>e.result==='WIN').length/list.length:null,
    profitFactor:pertes>0?gains/pertes:(gains>0?Infinity:null),
    expectancy:pnls.length?pnls.reduce((a,b)=>a+b,0)/pnls.length:null,
    avgWin:avgWin,avgLoss:avgLoss,
    ratio:(avgWin!=null&&avgLoss)?avgWin/Math.abs(avgLoss):null,
    best:pnls.length?Math.max.apply(null,pnls):null,
    worst:pnls.length?Math.min.apply(null,pnls):null,
    maxDD:maxDD};
}
const JOURNAL_ACTION='<a class="vx-btn vx-btn-sm" href="/journal?view=journal">Ouvrir la chronologie</a>';
function emptyCard(host,reason,action){const el=$(host);if(el)el.innerHTML='<div class="vx-card">'+VX.states.empty(reason,action||'')+'</div>';}

/* Statistiques COMPORTEMENTALES — agrégations honnêtes sur les décisions déclarées
   (jamais un indicateur de marché, jamais un pourcentage inventé). */
function behavioral(){
  const j=(E()?E().journal():[])||[];
  const closed=j.filter(e=>e.result==='WIN'||e.result==='LOSS');
  const num=(x)=>{const n=Number(x);return isFinite(n)?n:null;};
  const withPlan=j.filter(e=>e.reason&&num(e.stop)!=null);      /* raison + invalidation = plan */
  const withReason=j.filter(e=>e.reason);
  const closedWithLesson=closed.filter(e=>e.lesson);
  const lossWithStop=closed.filter(e=>e.result==='LOSS'&&num(e.stop)!=null&&num(e.exit)!=null);
  const respected=lossWithStop.filter(e=>num(e.exit)>=num(e.stop)*0.97); /* sortie ≈ stop, pas au-delà */
  return {n:j.length,closed:closed.length,
    wins:closed.filter(e=>e.result==='WIN').length,
    losses:closed.filter(e=>e.result==='LOSS').length,
    open:j.filter(e=>!e.result).length,
    respectMethod:j.length?Math.round(withPlan.length/j.length*100):null,
    entryQuality:j.length?Math.round(withReason.length/j.length*100):null,
    exitQuality:closed.length?Math.round(closedWithLesson.length/closed.length*100):null,
    invalRespect:lossWithStop.length?Math.round(respected.length/lossWithStop.length*100):null,
    mistakes:j.filter(e=>String(e.mistake||'').trim()).length,
    lessons:new Set(j.map(e=>String(e.lesson||'').trim()).filter(Boolean)).size};
}

/* Anneau de progression (§39) — n/max trades clôturés. SVG pur, sur tokens. */
function progressRing(n,max){
  var frac=Math.max(0,Math.min(1,max?n/max:0)),R=46,C=2*Math.PI*R;
  var col=frac>=1?'var(--vx-positive)':'var(--vx-brand)';
  return '<svg viewBox="0 0 120 120" style="width:132px;height:132px" role="img" aria-label="'+n+' sur '+max+' trades clôturés">'
    +'<circle cx="60" cy="60" r="'+R+'" fill="none" stroke="var(--vx-surface-3)" stroke-width="10"/>'
    +'<circle cx="60" cy="60" r="'+R+'" fill="none" stroke="'+col+'" stroke-width="10" stroke-linecap="round" stroke-dasharray="'+(frac*C).toFixed(1)+' '+C.toFixed(1)+'" transform="rotate(-90 60 60)"/>'
    +'<text x="60" y="57" text-anchor="middle" font-size="32" font-weight="700" fill="var(--vx-text-primary)" style="font-variant-numeric:tabular-nums">'+n+'</text>'
    +'<text x="60" y="78" text-anchor="middle" font-size="12" fill="var(--vx-text-muted)">/ '+max+' trades</text></svg>';
}
/* Aperçu FANTÔME de la courbe d'équité (§39) — forme déterministe, AUCUN chiffre :
   fait sentir le produit à venir sans jamais afficher de fausse performance. */
function ghostEquity(){
  var pts='M0 95 L60 88 L120 92 L180 70 L240 74 L300 52 L360 58 L420 34';
  return '<div style="position:relative;margin-bottom:6px"><svg viewBox="0 0 420 120" preserveAspectRatio="none" style="width:100%;height:118px;opacity:.55" aria-hidden="true">'
    +'<defs><linearGradient id="pfghost" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--vx-brand)" stop-opacity=".22"/><stop offset="1" stop-color="var(--vx-brand)" stop-opacity="0"/></linearGradient></defs>'
    +'<path d="'+pts+' L420 120 L0 120 Z" fill="url(#pfghost)"/><path d="'+pts+'" fill="none" stroke="var(--vx-brand)" stroke-width="2" stroke-dasharray="4 5" stroke-linejoin="round"/></svg>'
    +'<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center"><span class="vx-meta" style="background:var(--vx-surface-1);padding:4px 11px;border-radius:999px;border:1px solid var(--vx-border-soft)">Ta courbe d&#8217;équité apparaîtra ici</span></div></div>';
}

/* ═══ OVERVIEW ═══ */
/* Taille d'echantillon dans la barre de contexte : un taux de reussite sans
   son `n` ne dit pas s'il vaut quelque chose. */
function echantillon(){
  const el=$('vx-pf-echantillon');if(!el)return;
  const n=trades().length;
  const etat=n>=30?'live':n>=5?'delayed':'missing';
  const mot=n===0?'Aucun trade clôturé déclaré'
    :(n+' trade'+(n>1?'s':'')+' clôturé'+(n>1?'s':'')
      +(n<5?' · sous le minimum de 5':n<30?' · échantillon réduit':''));
  el.innerHTML='<span class="vx2-badge" data-state="'+etat+'">'+mot+'</span>';
}
/* Attendre un script `defer` qui n'est peut-etre pas servi.
   L'ancienne garde faisait `window.addEventListener('load', fn, {once:true})` :
   apres que `load` a deja tire — ce qui est le cas de tout rendu differe — le
   rappel n'est jamais rejoue, et le conteneur reste vide pour toujours. On
   sonde brievement, puis on ECRIT pourquoi rien ne vient. */
function quandPret(test,fn,hote,quoi){
  if(test())return fn();
  var essais=0;
  var t=setInterval(function(){
    if(test()){clearInterval(t);return fn();}
    if(++essais>20){
      clearInterval(t);
      var el=hote&&$(hote);
      if(el)el.innerHTML='<div class="vx2-state" data-kind="missing" role="status">'
        +'<p class="vx2-state-title">'+quoi+' — rendu indisponible</p>'
        +'<p class="vx2-state-cause">La bibliothèque de graphiques ne s’est pas '
        +'chargée sur cette page. Aucune donnée n’est perdue&nbsp;: elle n’est pas '
        +'dessinée.</p></div>';
    }
  },150);
}
function loadKpis(){
  const list=trades();
  if(list.length<5){
    const n=list.length;
    const milestones=[[5,'P&L, taux de réussite, profit factor, espérance'],
      [10,'Distribution gains/pertes, meilleurs & pires trades'],
      [20,'Courbe d’équité vs SPY, drawdown, MAE / MFE'],
      [30,'Rolling win rate & expectancy, perf par setup / régime']];
    const pct=Math.min(100,Math.round(n/5*100));
    const rows=milestones.map(function(m){const done=n>=m[0];
      return `<div class="vx-kv"><span class="k">${done?'✅':'🔒'} ${m[0]} trades</span>`
        +`<span class="v vx-dim" style="font-size:12px;text-align:right">${esc(m[1])}</span></div>`;}).join('');
    ($('vx-pf-kpis')||{}).innerHTML=`<div class="vx-card vx-col-12">
      <div class="vx-card-header"><span class="vx-card-title">Construis ton track record</span>
        <span class="vx-meta vx-right">${n} / 5 trades pour débloquer les premières statistiques</span></div>
      <div class="vx-grid">
        <div class="vx-col-4" style="display:flex;align-items:center;justify-content:center;padding:6px 0">${progressRing(n,5)}</div>
        <div class="vx-col-8">${ghostEquity()}<div class="vx-mt1">${rows}</div></div>
      </div>
      <div class="vx-help vx-mt3">Chaque trade clôturé (WIN/LOSS + P&amp;L) débloque des analyses. Aucune fausse performance n’est affichée avant d’avoir des données réelles — la méthode se juge sur des faits, pas des estimations.</div>
      <div class="vx-flex vx-mt3" style="gap:.5rem;flex-wrap:wrap">
        <a class="vx-btn vx-btn-sm vx-btn-primary" href="/performance?view=journal">Ajouter une entrée au journal</a>
        <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/portfolio?view=positions">Voir mes positions</a></div>
    </div>`;
    return list;
  }
  const s=stats(list);
  const pf=s.profitFactor===Infinity?'∞':(s.profitFactor===null?'—':VX.fmt.num(s.profitFactor,2));
  const cells=[
    ['P&L total (déclaré)',(s.total>=0?'+':'')+VX.fmt.num(s.total,0)+' $',s.total>=0?'vx-pos':'vx-neg'],
    ['Taux de réussite',VX.fmt.num(s.winRate,0)+' %',s.winRate>=50?'vx-pos':'vx-neg'],
    ['Profit factor',pf,(s.profitFactor||0)>=1?'vx-pos':'vx-neg'],
    ['Espérance / trade',(s.expectancy>=0?'+':'')+VX.fmt.num(s.expectancy,0)+' $',s.expectancy>=0?'vx-pos':'vx-neg'],
    ['Gain moyen',s.avgWin!=null?'+'+VX.fmt.num(s.avgWin,0)+' $':'—','vx-pos'],
    ['Perte moyenne',s.avgLoss!=null?VX.fmt.num(s.avgLoss,0)+' $':'—','vx-neg'],
    ['Ratio gain/perte',s.ratio!=null?VX.fmt.num(s.ratio,2):'—',(s.ratio||0)>=1?'vx-pos':'vx-neg'],
    ['Drawdown max',s.maxDD<0?VX.fmt.num(s.maxDD,0)+' $':'—','vx-neg'],
    ['Meilleur / pire',(s.best!=null?((s.best>=0?'+':'')+VX.fmt.num(s.best,0)):'—')+' / '+(s.worst!=null?VX.fmt.num(s.worst,0):'—')+' $','vx-muted'],
    ['Trades déclarés',String(s.n),'vx-muted'],
  ];
  ($('vx-pf-kpis')||{}).innerHTML=cells.map(([label,val,cls])=>{
    const tone=cls==='vx-pos'?'pos':cls==='vx-neg'?'neg':'';
    return `<div class="vx-stat" style="grid-column:span 2" data-tone="${tone}" aria-label="${esc(label)}">
      <div class="vx-stat-k">${label}</div>
      <div class="vx-stat-v">${val}</div>
      <div class="vx-stat-sub">journal local · vos déclarations</div></div>`;}).join('')
    +`<div class="vx-stat" style="grid-column:span 2">
      <div class="vx-stat-k">Source</div>
      <div class="vx-meta" style="font-size:11.5px;margin-top:5px;line-height:1.4">Calculs arithmétiques sur VOS trades déclarés — aucun indicateur de marché.</div></div>`;
  return list;
}
/* Équité DÉRIVÉE du cumul des P&L de clôture déclarés (le stock myTradesEquity
   n'est jamais alimenté par recordExit — s'y fier laissait la courbe vide). Base
   = capital déclaré si présent, sinon 0 (courbe de P&L cumulé). Réel, arithmétique. */
function derivedEquity(){
  const cl=trades().slice().filter(e=>e.date).sort((a,b)=>String(a.date).localeCompare(String(b.date)));
  if(cl.length<2)return [];
  const base=(E()&&E().capital&&E().capital())||0;
  let cum=base;const eq=[];
  cl.forEach(e=>{cum+=Number(e.pnl)||0;eq.push({d:e.date,v:Math.round(cum*100)/100});});
  return eq;
}
function loadEquity(){
  const eq=derivedEquity();
  if(eq.length>=2){
    /* equity-chart.js / drawdown-chart.js sont des scripts `defer` : garde-fou
       si loadEquity court avant leur enregistrement (évite « equityCard is not a
       function ») — on retente une fois tous les scripts chargés. */
    if(!(window.VXCharts&&VXCharts.equityCard&&VXCharts.drawdownCard)){
      return quandPret(function(){return window.VXCharts&&VXCharts.equityCard&&VXCharts.drawdownCard;},
        loadEquity,'vx-pf-equity','Courbe d’équité');}
    const labels=eq.map(p=>p.d),values=eq.map(p=>Number(p.v));
    VXCharts.equityCard('vx-pf-equity',{
      title:'Courbe d’équité (déclarée)',unit:'$',timeframe:eq.length+' points',
      question:'Le capital déclaré progresse-t-il régulièrement ?',
      conclusion:values[values.length-1]>=values[0]?'Équité en progression sur la période.':'Équité en retrait sur la période.',
      labels,values,height:240,
      source:'journal local (cumul des clôtures)',timestamp:null,mode:'delayed',
      explain:{shows:'La série d’équité issue de vos clôtures de positions déclarées.',
        why:'Une méthode saine produit une pente régulière, pas des à-coups.',
        confirm:'Nouveaux plus hauts d’équité avec drawdowns contenus.',
        invalidate:'Série de plus bas d’équité — réduire la taille et revoir le process.'}});
    VXCharts.drawdownCard('vx-pf-drawdown',{
      title:'Drawdown depuis les pics',unit:'%',
      question:'Les pertes restent-elles contrôlées ?',
      conclusion:'Dérivé arithmétiquement de la courbe d’équité déclarée.',
      labels,values,height:240,
      source:'journal local (cumul des clôtures)',timestamp:null,mode:'delayed',
      limits:'dérivé de la série déclarée — pas un indicateur de marché',
      explain:{shows:'L’écart en % entre l’équité et son dernier pic.',
        why:'La profondeur des drawdowns mesure la discipline de risque réelle.',
        confirm:'Drawdowns courts et peu profonds.',invalidate:'Drawdown qui s’aggrave pendant que vous continuez à trader.'}});
  }else{
    emptyCard('vx-pf-equity','Courbe d’équité indisponible — elle se construit au fil des clôtures de positions déclarées.',JOURNAL_ACTION);
    emptyCard('vx-pf-drawdown','Drawdown indisponible sans courbe d’équité.');
  }
}
/* Heatmap mensuelle + distribution — agrégations arithmétiques sur VOS
   clôtures déclarées (jamais un indicateur de marché). */
/* ═══ DISCIPLINE ════════════════════════════════════════════════════════
   Ce bloc etait le corps de `loadDiscipline()`. Quand cette fonction a ete
   retiree de l'orchestration, son CORPS est reste — colle a l'interieur de
   `loadMonthlyAndDist`, apres le retour anticipe. Trois consequences :

   1. la heatmap mensuelle n'etait plus dessinee nulle part : la fonction
      censee la produire ne la produisait plus ;
   2. avec trois cloture ou plus, elle levait `b is not defined` — `b`, `hero`
      et `next` n'etaient declares dans aucune portee ;
   3. rien de tout cela ne se voyait, parce que la fonction n'etait appelee
      par personne.

   Les deux responsabilites sont separees. Celle-ci ne compte que des faits
   declares : aucun pourcentage n'est estime. */
function loadDiscipline(){
  const b=behavioral();
  const hote=$('vx-pf-discipline'),next=$('vx-pf-next-axis');
  if(!b.n){
    if(hote)hote.innerHTML='<div class="vx2-state" data-kind="empty" role="status">'
      +'<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
      +'<p class="vx2-state-title">Discipline non mesurable</p>'
      +'<p class="vx2-state-cause">Aucune décision journalisée. Ces quatre mesures comptent '
      +'des déclarations ; sans déclaration, elles n’ont rien à compter.</p></div>';
    return;
  }
  const pct=(v)=>v==null?'n/d':v+' %';
  const ton=(v)=>v==null?'':(v>=80?'positive':v<50?'negative':'caution');
  const cell=(label,v,sub)=>'<div class="vx2-metric">'
    +'<span class="vx2-metric-label">'+label+'</span>'
    +'<span class="vx2-metric-value" data-tone="'+(v==null?'missing':ton(v))+'">'+pct(v)+'</span>'
    +'<span class="vx2-metric-meta">'+sub+'</span></div>';
  if(hote)hote.innerHTML='<div class="vx2-strip">'
    +cell('Respect de la méthode',b.respectMethod,'décisions avec plan documenté')
    +cell('Qualité des entrées',b.entryQuality,'avec raison d’entrée')
    +cell('Qualité des sorties',b.exitQuality,'clôtures avec leçon')
    +cell('Respect des invalidations',b.invalRespect,'pertes sorties près du stop')
    +'</div><p class="vx2-stamp vx-mt2">'+b.n+' décision(s) journalisée(s) · '
    +b.wins+' validée(s), '+b.losses+' invalidée(s), '+b.open+' en cours · '
    +'décomptes sur vos déclarations, aucun pourcentage estimé.</p>';
  if(next){
    const axes=[
      {value:b.respectMethod,title:'Formaliser le plan',body:'Ajouter une raison et une invalidation avant de juger la décision.'},
      {value:b.entryQuality,title:'Expliquer l’entrée',body:'Rendre la raison d’entrée explicite et vérifiable.'},
      {value:b.exitQuality,title:'Consigner la leçon',body:'Compléter la leçon après chaque clôture.'},
      {value:b.invalRespect,title:'Respecter l’invalidation',body:'Comparer la sortie au niveau d’invalidation déclaré.'}
    ];
    const connus=axes.filter(a=>a.value!=null).sort((x,y)=>x.value-y.value);
    const axe=connus[0]||axes.find(a=>a.value==null)||axes[0];
    next.dataset.tone=axe.value!=null&&axe.value<50?'risk':'neutral';
    /* « Prochain axe » n'est pas un verdict de moteur : c'est la plus basse des
       quatre mesures comptees. Le libelle le dit. */
    next.innerHTML='<span class="vx-eyebrow">Prochain axe · mesure la plus basse</span><h3>'+esc(axe.title)+'</h3>'
      +'<p class="vx-dim">'+esc(axe.body)+'</p>'
      +(axe.value==null?'<span class="vx2-badge" data-state="missing">mesure n/d</span>'
        :'<span class="vx2-badge" data-state="'+(axe.value<50?'stale':'delayed')+'">'+axe.value+' % aujourd’hui</span>')
      +'<div class="vx-mt3"><a class="vx2-btn vx2-btn--ghost" href="/performance?view=journal">Voir le journal &rarr;</a></div>';
  }
}

/* Revue des hypothèses — validées / invalidées / en cours (déclarations). */
function loadHypotheses(){
  const host=$('vx-pf-hypo');if(!host)return;
  const j=(E()?E().journal():[])||[];
  if(!j.length){host.innerHTML=VX.states.emptyDesk('Aucune hypothèse journalisée — chaque décision est une thèse à vérifier.',JOURNAL_ACTION);return;}
  const wins=j.filter(e=>e.result==='WIN'),losses=j.filter(e=>e.result==='LOSS'),open=j.filter(e=>!e.result);
  const chip=(label,n,cls)=>`<div class="vx-kpi vx-card vx-card--compact" style="grid-column:span 4">
    <span class="vx-kpi-label">${label}</span><span class="vx-kpi-value ${cls}" style="font-size:24px">${n}</span></div>`;
  const line=(e)=>`<div class="vx-flex" style="padding:7px 0;border-bottom:1px dashed var(--vx-border-soft);gap:10px;align-items:center">
    <button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(e.ticker||'')}">${esc(e.ticker||'—')}</button>
    <span class="vx-badge ${e.result==='WIN'?'vx-pos':e.result==='LOSS'?'vx-neg':'vx-muted'}">${e.result||'en cours'}</span>
    <span class="vx-grow vx-truncate vx-dim" style="font-size:12.5px" title="${esc(e.reason||e.lesson||'—')}">${esc(e.reason||e.lesson||'—')}</span></div>`;
  host.innerHTML=`<div class="vx-grid vx-mb3">
      ${chip('Validées',wins.length,'vx-pos')}${chip('Invalidées',losses.length,'vx-neg')}${chip('En cours',open.length,'vx-muted')}</div>`
    +j.slice().sort((a,b2)=>String(b2.date||'').localeCompare(String(a.date||''))).slice(0,6).map(line).join('')
    +`<div class="vx-card-footer">${j.length} hypothèse(s) · une hypothèse invalidée n’est pas un échec si l’invalidation a été respectée</div>`;
}

/* Distribution des rendements par trade — mesure de DISCIPLINE (asymétrie). */
function loadDist(){
  const closed=(E()?E().closedPositions():[])||[];
  const withPl=closed.filter(t=>t.pnl_pct!==undefined&&t.pnl_pct!==null&&t.closed);
  if(withPl.length<3){emptyCard('vx-pf-dist','Distribution disponible à partir de 3 clôtures datées.',JOURNAL_ACTION);return;}
  const buckets=[[-1e9,-20],[-20,-10],[-10,-5],[-5,0],[0,5],[5,10],[10,20],[20,50],[50,1e9]];
  const labels=['<-20','-20/-10','-10/-5','-5/0','0/+5','+5/+10','+10/+20','+20/+50','>+50'];
  const counts=buckets.map(([a,b])=>withPl.filter(t=>t.pnl_pct>=a&&t.pnl_pct<b).length);
  VXCharts.card('vx-pf-dist',{title:'Distribution des rendements par trade',unit:'trades',
    question:'Le profil est-il asymétrique (petites pertes, gains amples) ?',
    conclusion:withPl.length+' clôtures · l’asymétrie droite valide la gestion.',
    height:220,source:'journal local (clôtures)',timestamp:null,mode:'delayed',
    explain:{shows:'Le décompte de tes trades clôturés par tranche de rendement (%).',
      why:'La méthode vise des pertes tronquées (stops) et des gains étendus (TP échelonnés).',
      confirm:'Masse des pertes concentrée entre 0 et −10 %, queue droite étendue.',
      invalidate:'Queue gauche épaisse — les stops ne sont pas respectés.'},
    render:(cv)=>VXCharts.bars(cv,labels,counts,
      {colors:buckets.map(([a])=>a<0?VXCharts.colors.negative:VXCharts.colors.positive)})});
}

/* ═══ CHRONOLOGIE (journal) ═══ */
function currentFilter(){return ($('vx-pf-filter')?$('vx-pf-filter').value:'').trim().toUpperCase();}
function loadJournal(){
  const all=(E()?E().journal():[]).slice().sort((a,b)=>String(b.date||'').localeCompare(String(a.date||'')));
  const f=currentFilter();
  const list=f?all.filter(e=>String(e.ticker||'').toUpperCase().includes(f)):all;
  if(!list.length){
    ($('vx-pf-journal')||{}).innerHTML=VX.states.emptyDesk(
      f?('Aucune entrée pour « '+esc(f)+' ».'):'Chronologie vide — déclare tes décisions pour mesurer ton exécution.',
      '<button class="vx-btn vx-btn-sm" id="vx-pf-add-empty">Ajouter une entrée</button>');
    $('vx-pf-add-empty')?.addEventListener('click',openEntryModal);
    return;
  }
  ($('vx-pf-journal')||{}).innerHTML=
    `<table class="vx-table"><thead><tr><th>Date</th><th>Ticker</th><th>Direction</th>
     <th>Résultat</th><th class="vx-num">P&amp;L</th><th>Leçon</th><th></th></tr></thead><tbody>`
    +list.map(e=>{
      const pnl=Number(e.pnl);
      return `<tr>
        <td class="vx-mono vx-meta">${esc(e.date||'—')}</td>
        <td><button class="vx-btn vx-btn-sm vx-btn-ghost vx-ticker" data-open-analysis="${esc(e.ticker||'')}">${esc(e.ticker||'—')}</button></td>
        <td>${esc(e.dir||'—')}${e.auto?' <span class="vx-badge">auto</span>':''}</td>
        <td>${e.result==='WIN'?'<span class="vx-badge vx-pos">WIN</span>':e.result==='LOSS'?'<span class="vx-badge vx-neg">LOSS</span>':'—'}</td>
        <td class="vx-num vx-mono ${pnl>0?'vx-pos':pnl<0?'vx-neg':'vx-muted'}">${isFinite(pnl)?(pnl>0?'+':'')+VX.fmt.num(pnl,0)+' $':'—'}</td>
        <td class="vx-dim" style="font-size:12px;max-width:260px">${esc(e.lesson||'')}</td>
        <td><button class="vx-btn vx-btn-icon vx-btn-ghost" data-entity-menu="${esc(e.ticker||'')}" aria-label="Actions ${esc(e.ticker||'')}">⋯</button></td>
      </tr>`;}).join('')+'</tbody></table>'
    +`<div class="vx-card-footer">${list.length} entrée(s)${f?' (filtre : '+esc(f)+')':''} · journal local synchronisé desk</div>`;
}
function loadMistakes(){
  const all=E()?E().journal():[];
  const counts={};
  all.forEach(e=>{const m=String(e.mistake||'').trim();if(m)counts[m]=(counts[m]||0)+1;});
  const top=Object.entries(counts).sort((a,b)=>b[1]-a[1]);
  ($('vx-pf-mistakes')||{}).innerHTML=top.length?top.map(([m,n])=>
    `<div class="vx-kv"><span class="k">${esc(m)}</span><span class="v vx-mono">× ${n}</span></div>`).join('')
    :VX.states.emptyDesk('Aucune erreur déclarée — renseigne le champ « erreur » à chaque sortie perdante.');
}
function openEntryModal(){
  const field=(id,label,type,ph)=>`<div class="vx-field"><label for="${id}">${label}</label>
    <input class="vx-input" id="${id}" type="${type||'text'}" ${type==='number'?'step="any"':''} placeholder="${ph||''}" autocomplete="off" /></div>`;
  const body=`
    <div class="vx-form-row">${field('j-ticker','Ticker','text','ex. NVDA')}
      <div class="vx-field"><label for="j-dir">Direction</label>
        <select class="vx-select" id="j-dir"><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select></div></div>
    <div class="vx-field"><label for="j-reason">Raison d’entrée</label>
      <input class="vx-input" id="j-reason" placeholder="setup, catalyseur…" autocomplete="off" /></div>
    <div class="vx-form-row">${field('j-entry','Entrée','number')}${field('j-stop','Stop','number')}</div>
    <div class="vx-form-row">${field('j-tp','Objectif (TP)','number')}
      <div class="vx-field"><label for="j-result">Résultat</label>
        <select class="vx-select" id="j-result"><option value="">— en cours —</option>
        <option value="WIN">WIN</option><option value="LOSS">LOSS</option></select></div></div>
    <div class="vx-form-row">${field('j-exit','Sortie','number')}${field('j-pnl','P&amp;L ($)','number')}</div>
    <div class="vx-field"><label for="j-lesson">Leçon</label>
      <input class="vx-input" id="j-lesson" placeholder="ce que ce trade enseigne" autocomplete="off" /></div>
    <div class="vx-form-row">${field('j-mistake','Erreur commise (si perte)','text','ex. entrée sans confirmation')}
      ${field('j-emo','État émotionnel','text','calme, FOMO…')}</div>
    <div class="vx-help">Registre déclaratif — Vertex n’envoie JAMAIS un ordre.</div>`;
  VX.shell.openModal('Ajouter une entrée de journal',body,
    '<button class="vx-btn vx-btn-primary" id="j-confirm">Enregistrer</button>');
  $('j-confirm')?.addEventListener('click',()=>{
    const v=(id)=>$(id)?.value?.trim()||'';
    const n=(id)=>{const x=v(id);return x===''?null:Number(x);};
    const ticker=v('j-ticker').toUpperCase();
    if(!/^[A-Z.\-]{1,7}$/.test(ticker)){VX.toast('Ticker invalide','error');return;}
    const result=v('j-result');
    if(result&&n('j-pnl')===null){VX.toast('P&L requis quand un résultat est déclaré','error');return;}
    E().addJournalEntry({ticker,dir:v('j-dir'),reason:v('j-reason'),
      entry:n('j-entry'),stop:n('j-stop'),tp:n('j-tp'),
      result:result||'',exit:n('j-exit'),pnl:n('j-pnl'),
      lesson:v('j-lesson'),mistake:v('j-mistake'),emo:v('j-emo')});
    VX.shell.closeModal();
    loadJournal();loadMistakes();
  });
  $('j-ticker')?.focus();
}

/* ═══ APPRENTISSAGE (learnings) ═══ */
function loadLearnings(){
  const all=E()?E().journal():[];
  const lessons=[...new Set(all.map(e=>String(e.lesson||'').trim()).filter(Boolean))];
  ($('vx-pf-lessons')||{}).innerHTML=lessons.length?
    '<ul style="margin:0;padding-left:18px;line-height:1.9">'+lessons.map(l=>`<li>${esc(l)}</li>`).join('')+'</ul>'
    :VX.states.emptyDesk('Aucune leçon consignée — renseigne le champ « leçon » à chaque sortie de trade.',JOURNAL_ACTION);
  const counts={};
  all.forEach(e=>{const m=String(e.mistake||'').trim();if(m)counts[m]=(counts[m]||0)+1;});
  const top=Object.entries(counts).sort((a,b)=>b[1]-a[1]);
  ($('vx-pf-recurrent')||{}).innerHTML=top.length?top.map(([m,n])=>
    `<div class="vx-kv"><span class="k">${esc(m)}</span><span class="v vx-mono">× ${n}</span></div>`).join('')
    :VX.states.emptyDesk('Aucune erreur récurrente déclarée pour l’instant.');
  /* Biais comportementaux — décompte des états émotionnels déclarés. */
  const emo={};
  all.forEach(e=>{const m=String(e.emo||'').trim().toLowerCase();if(m)emo[m]=(emo[m]||0)+1;});
  const rows=Object.entries(emo).sort((a,b)=>b[1]-a[1]);
  const bh=$('vx-pf-biais');
  if(bh){
    if(!rows.length){bh.innerHTML=VX.states.emptyDesk('Aucun état émotionnel déclaré — renseigne « état émotionnel » (calme, FOMO, peur…) pour révéler tes biais.');}
    else{
      const max=rows[0][1];
      bh.innerHTML='<div style="display:flex;flex-direction:column;gap:6px">'+rows.map(([m,n])=>
        `<div style="display:flex;align-items:center;gap:8px"><span style="width:140px;font-size:12.5px;text-transform:capitalize" class="vx-dim">${esc(m)}</span>
         <span style="flex:1;height:13px;background:var(--vx-surface-3,#121214);border-radius:4px;overflow:hidden"><span style="display:block;height:100%;width:${Math.round(n/max*100)}%;background:var(--vx-brand,#D28A54);border-radius:4px"></span></span>
         <span class="vx-mono" style="width:34px;text-align:right">× ${n}</span></div>`).join('')+'</div>'
        +'<div class="vx-card-footer"><span class="vx-meta">Décompte déclaratif — un biais nommé est un biais qu’on peut corriger.</span></div>';
    }
  }
}

/* ═══ PROGRESSION ═══ */
function loadProgression(){
  const host=$('vx-pf-prog');if(!host)return;
  const b=behavioral();
  const milestones=[[5,'P&L, taux de réussite, profit factor, espérance'],
    [10,'Distribution gains/pertes, meilleurs & pires trades'],
    [20,'Respect des invalidations, MAE/MFE, meilleurs setups'],
    [30,'Rolling win rate & discipline par régime']];
  const rows=milestones.map(m=>{const done=b.n>=m[0];
    return `<div class="vx-kv"><span class="k">${done?'✅':'🔒'} ${m[0]} décisions</span>
      <span class="v vx-dim" style="font-size:12px;text-align:right">${esc(m[1])}</span></div>`;}).join('');
  /* Erreurs par mois (déclarées) — la fréquence baisse-t-elle ? */
  const all=(E()?E().journal():[])||[];
  const byMonth={};
  all.forEach(e=>{const d=String(e.date||'').slice(0,7);if(!d)return;if(String(e.mistake||'').trim())byMonth[d]=(byMonth[d]||0)+1;});
  const months=Object.keys(byMonth).sort();
  let trend='';
  if(months.length>=2&&window.VXCharts&&VXCharts.card){
    host.innerHTML=`<div class="vx-grid"><div class="vx-col-5">${rows}</div>
      <div class="vx-col-7" id="vx-pf-prog-chart"></div></div>`;
    VXCharts.card('vx-pf-prog-chart',{title:'Erreurs déclarées par mois',unit:'erreurs',
      question:'Mes erreurs récurrentes diminuent-elles ?',
      conclusion:byMonth[months[months.length-1]]<=byMonth[months[0]]?'Tendance à la baisse — la discipline progresse.':'Vigilance : les erreurs ne diminuent pas encore.',
      height:200,source:'journal local',timestamp:null,mode:'delayed',
      render:(cv)=>VXCharts.bars(cv,months,months.map(m=>byMonth[m]),
        {colors:months.map(()=>VXCharts.colors.warning),yFmt:(v)=>v})});
  }else{
    host.innerHTML=`<div class="vx-mb3">${rows}</div>`
      +`<div class="vx-meta">La courbe de progression (erreurs par période) apparaîtra avec au moins deux mois de décisions datées. `
      +`${b.n?('Actuellement '+b.n+' décision(s) journalisée(s).'):''} Aucune progression fabriquée avant d’avoir des faits.</div>`;
  }
}

/* ═══ HISTORIQUE DU MOTEUR ═══ */
async function loadTrack(){
  try{
    const tr=await VX.fetch('/api/track-record',{ttl:120000});
    const by=tr.by_verdict||{};
    const rows=Object.entries(by);
    if(!rows.length){
      /* #783/G3 — L'ANCIEN MESSAGE DISAIT « le registre se remplit à chaque
         scan », c'est-à-dire « patience ». Il l'a dit pendant que la jointure
         de dates était cassée : la condition ne pouvait JAMAIS se résoudre, et
         l'écran invitait à attendre un résultat impossible. Le serveur détaille
         desormais POURQUOI chaque entrée n'est pas notée ; on le sert. */
      const ig=tr.ignores||{};
      const causes=[];
      if(ig.horizon_non_echu) causes.push(ig.horizon_non_echu+' trop récent(s) (horizon pas encore écoulé)');
      if(ig.sans_serie) causes.push(ig.sans_serie+' sur des titres qui ne sont plus suivis par le scan');
      if(ig.date_absente) causes.push(ig.date_absente+' dont la séance est introuvable dans la série');
      ($('vx-pf-track')||{}).innerHTML=VX.states.empty(
        (tr.entries||0)+' verdict(s) enregistré(s), '+(tr.resolved||0)+' résolu(s)'
        +' — il en faut 5 par verdict pour publier une fiabilité.'
        +(causes.length?' Non notés : '+esc(causes.join(' · '))+'.':''),
        '<a class="vx-btn vx-btn-sm" href="/system?view=data">Système / Données</a>');
      return;
    }
    ($('vx-pf-track')||{}).innerHTML=
      `<div id="vx-pf-track-bar" class="vx-mb3"></div>`
      +`<table class="vx-table"><thead><tr><th>Verdict moteur</th><th class="vx-num">N</th>
       <th class="vx-num">Rdt +5 séances</th><th class="vx-num">Rdt +20 séances</th>
       <th class="vx-num">% gagnants +5 s</th><th class="vx-num">TP1 avant stop</th></tr></thead><tbody>`
      +rows.map(([verdict,s])=>`<tr>
        <td><b>${esc(verdict)}</b></td>
        <td class="vx-num vx-mono">${VX.fmt.nd(s.n)}</td>
        <td class="vx-num vx-mono ${s.avg_5j>0?'vx-pos':s.avg_5j<0?'vx-neg':'vx-muted'}">${s.avg_5j===null||s.avg_5j===undefined?'—':VX.fmt.pct(s.avg_5j)}</td>
        <td class="vx-num vx-mono ${s.avg_20j>0?'vx-pos':s.avg_20j<0?'vx-neg':'vx-muted'}">${s.avg_20j===null||s.avg_20j===undefined?'—':VX.fmt.pct(s.avg_20j)}</td>
        <td class="vx-num vx-mono ${s.win_5j==null?'':s.win_5j>=50?'vx-pos':'vx-neg'}">${s.win_5j===null||s.win_5j===undefined?'—':VX.fmt.num(s.win_5j,0)+' %'}</td>
        <td class="vx-num vx-mono">${s.tp1_rate===null||s.tp1_rate===undefined?'—':VX.fmt.num(s.tp1_rate,0)+' % ('+s.tp1_resolved+')'}</td>
      </tr>`).join('')+'</tbody></table>'
      +`<div class="vx-card-footer">${VX.updateIndicator(Date.now(),'historique moteur','delayed')}
        <span class="vx-meta">${esc(tr.note||'')}${tr.as_of?' · au '+esc(tr.as_of):''}</span></div>`;
    try{
      const _tl=rows.map(([v])=>v),_tv=rows.map(([,s])=>(s.avg_20j==null?null:s.avg_20j));
      if(window.VXCharts&&VXCharts.card&&VXCharts.bars&&_tv.some(x=>x!=null)){
        VXCharts.card('vx-pf-track-bar',{title:'Rendement moyen +20 séances par verdict',unit:'%',
          question:'Quels verdicts moteur ont le mieux tenu ?',height:200,
          source:'historique moteur',timestamp:null,mode:'delayed',
          limits:'moyenne réelle des verdicts résolus (n≥5) — mesure, pas une promesse',
          render:(cv)=>VXCharts.bars(cv,_tl,_tv,{colors:_tv.map(v=>v==null?VXCharts.colors.muted:(v>=0?VXCharts.colors.positive:VXCharts.colors.negative)),yFmt:(x)=>x+' %'})});
      }
    }catch(e){}
  }catch(e){($('vx-pf-track')||{}).innerHTML=VX.states.error('Historique moteur indisponible ('+esc(e.message)+')');}
}
function loadReal(){
  const list=trades();
  if(!list.length){
    ($('vx-pf-real')||{}).innerHTML=VX.states.emptyDesk('Aucun trade réel déclaré avec résultat — le journal est la seule source de cette section.',JOURNAL_ACTION);
    return;
  }
  const s=stats(list);
  const pf=s.profitFactor===Infinity?'∞':(s.profitFactor===null?'—':VX.fmt.num(s.profitFactor,2));
  ($('vx-pf-real')||{}).innerHTML=
    `<table class="vx-table"><thead><tr><th class="vx-num">Trades</th><th class="vx-num">Taux de réussite</th>
     <th class="vx-num">P&amp;L total</th><th class="vx-num">Profit factor</th><th class="vx-num">Espérance / trade</th></tr></thead>
     <tbody><tr>
       <td class="vx-num vx-mono">${s.n}</td>
       <td class="vx-num vx-mono ${s.winRate==null?'':s.winRate>=50?'vx-pos':'vx-neg'}">${VX.fmt.num(s.winRate,0)} %</td>
       <td class="vx-num vx-mono ${s.total>=0?'vx-pos':'vx-neg'}">${(s.total>=0?'+':'')+VX.fmt.num(s.total,0)} $</td>
       <td class="vx-num vx-mono">${pf}</td>
       <td class="vx-num vx-mono ${s.expectancy>=0?'vx-pos':'vx-neg'}">${(s.expectancy>=0?'+':'')+VX.fmt.num(s.expectancy,0)} $</td>
     </tr></tbody></table>
     <div class="vx-card-footer">${VX.updateIndicator(Date.now(),'journal local (tes déclarations)','delayed')}
       <span class="vx-meta">agrégations arithmétiques sur tes trades déclarés — indépendant des signaux moteur</span></div>`;
}

/* ═══ Orchestration ═══ */
/* Calibration Skyler (LOT 8e) : journal des décisions + rendements ex post réels.
   Brier honnêtement indisponible tant que rien de calibré. */
async function loadCalibration(){
  const host=$('vx-pf-calibration');if(!host)return;
  try{
    const d=await VX.fetch('/api/skyler/calibration',{ttl:120000});
    if(!d||!d.n_decisions){
      host.innerHTML='<div class="vx-empty">Aucune décision enregistrée pour le moment — le journal se remplit à chaque fiche Analyse consultée.</div>';
      return;
    }
    const byDec=Object.entries(d.by_decision||{}).map(([k,v])=>'<span class="vx-badge" data-tone="neutral" style="margin-right:.25rem">'+esc(k)+' × '+v+'</span>').join('');
    const oc=d.outcomes||{};
    let rows='';
    if(oc.available&&(oc.rows||[]).length){
      rows='<div class="vx-table-wrap vx-mt1"><table class="vx-table"><thead><tr><th>Titre</th><th>Décision</th><th>Prix décision</th><th>Prix actuel</th><th>Rendement</th></tr></thead><tbody>'
        +oc.rows.slice(-12).map(r=>{
          const cls=r.return_pct>0?'vx-pos':r.return_pct<0?'vx-neg':'';
          return '<tr><td data-label="Titre"><b>'+esc(r.symbol)+'</b></td><td data-label="Décision">'+esc(r.decision)+'</td>'
            +'<td data-label="Prix décision" class="vx-num">'+VX.fmt.num(r.entry_price,2)+'</td>'
            +'<td data-label="Prix actuel" class="vx-num">'+VX.fmt.num(r.current_price,2)+'</td>'
            +'<td data-label="Rendement" class="vx-num '+cls+'">'+(r.return_pct>0?'+':'')+r.return_pct+' %</td></tr>';
        }).join('')+'</tbody></table></div>';
    }
    host.innerHTML='<div class="vx-flex vx-mb1" style="gap:.4rem;align-items:center;flex-wrap:wrap">'
      +'<b>'+d.n_decisions+'</b><span class="vx-meta">décision(s) journalisée(s)</span>'+byDec
      +(d.demo?'<span class="vx-badge" data-tone="neutral">DÉMO</span>':'')+'</div>'
      +rows
      +'<div class="vx-meta" style="margin-top:.35rem">'
      +(oc.available?oc.measured+' mesurée(s), '+(oc.unmeasured||0)+' non mesurée(s) (sans cote — jamais inventé) · ':'')
      +'Brier : '+esc((d.brier&&d.brier.reason)||'indisponible')+'</div>';
  }catch(e){host.innerHTML='<div class="vx-error-banner">Calibration injoignable : '+esc(e.message)+'</div>';}
}
/* Mémoire décisionnelle (LOT 16) : ledger immuable + biais + erreurs par version.
   Lecture seule de /api/skyler/memory — états vides honnêtes, rien inventé. */
async function loadMemory(){
  const host=$('vx-pf-memory');if(!host)return;
  try{
    const d=await VX.fetch('/api/skyler/memory',{ttl:120000});
    if(!d||!d.n_decisions){
      host.innerHTML='<div class="vx-empty">Aucune décision figée pour le moment — la mémoire se remplit à chaque fiche Analyse consultée.</div>';
      return;
    }
    const agg=(d.aggregates&&d.aggregates.by_engine_version)||{};
    const vRows=Object.entries(agg).map(([v,a])=>{
      const errs=Object.entries(a.error_classes||{}).map(([k,n])=>esc(k)+' × '+n).join(' · ')||'aucune erreur classée (résultats en attente)';
      const decs=Object.entries(a.by_decision||{}).map(([k,n])=>esc(k)+' × '+n).join(' · ');
      return '<tr><td data-label="Moteur" class="vx-mono">'+esc(v)+'</td>'
        +'<td data-label="Décisions" class="vx-num">'+a.n_decisions+'</td>'
        +'<td data-label="Répartition">'+decs+'</td>'
        +'<td data-label="Mesurées" class="vx-num">'+(a.measured||0)+'</td>'
        +'<td data-label="Erreurs classées">'+errs+'</td></tr>';
    }).join('');
    const tone={DETECTE:'risk',ABSENT:'positive',INSUFFISANT:'neutral'};
    const pats=(d.patterns||[]).map(p=>'<span class="vx-badge" data-tone="'+(tone[p.status]||'neutral')
      +'" title="'+esc(p.basis||'')+'" style="margin:.12rem .25rem .12rem 0">'
      +esc(String(p.pattern||'').replace(/_/g,' '))+' : '+esc(p.status)+'</span>').join('');
    const recs=(d.recommendations||[]).map(r=>'<div class="vx-insight" data-tone="warning">'
      +esc(r.proposal)+' <span class="vx-meta">(en attente de validation humaine)</span></div>').join('');
    host.innerHTML='<div class="vx-flex vx-mb1" style="gap:.4rem;align-items:center;flex-wrap:wrap">'
      +'<b>'+d.n_decisions+'</b><span class="vx-meta">décision(s) figée(s) · '+(d.n_outcomes||0)+' résultat(s) mesuré(s)</span>'
      +(d.demo?'<span class="vx-badge" data-tone="neutral">DÉMO</span>':'')
      +((d.ledger_health&&d.ledger_health.status==='ANOMALIES')
        ?'<span class="vx-badge" data-tone="negative" title="'+esc(d.ledger_health.basis||'')
          +'">LEDGER : ANOMALIES</span>':'')
      +(function(){
        const ds=d.decisions||[];
        if(!ds.length)return '<span class="vx-meta">· aucune décision figée</span>';
        const sd=(ds[ds.length-1]||{}).session_date||null;
        if(!sd)return '<span class="vx-meta">· dernière décision figée : n/d</span>';
        const now=new Date();
        const todayUTC=Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate());
        const days=Math.round((todayUTC-new Date(sd+'T00:00:00Z').getTime())/86400000);
        const age=(isFinite(days)&&days>=0)?' (J-'+days+')':'';
        return '<span class="vx-meta">· dernière décision figée : '+esc(sd)+age+'</span>';
      })()+'</div>'
      +'<div class="vx-table-wrap"><table class="vx-table"><thead><tr><th>Moteur</th><th>Décisions</th><th>Répartition</th><th>Mesurées</th><th>Erreurs classées</th></tr></thead><tbody>'
      +vRows+'</tbody></table></div>'
      +(function(){
        const cc=d.calibration_by_context||{};
        const cells=[];
        [['by_level','niveau'],['by_regime','régime'],['by_decision','décision'],
         ['by_catalyst','catalyseur'],['by_catalyst_type','type']].forEach(([k,lbl])=>{
          Object.entries(cc[k]||{}).forEach(([name,c])=>{
            cells.push('<a class="vx-badge" data-tone="'+(c.status==='MESURE'?'positive':'neutral')
              +'" href="/memory/cell/'+encodeURIComponent(k)+'/'+encodeURIComponent(name)
              +'" title="'+esc(c.basis||'')+' — clic : décisions mesurées de la cellule" style="margin:.12rem .25rem .12rem 0">'
              +esc(lbl)+'='+esc(name)+' : '+(c.status==='MESURE'?(c.value+' ('+c.n_measured+' mesures)'):'insuffisant ('+c.n_measured+')')+'</a>');
          });
        });
        return cells.length?('<div class="vx-kpi-label vx-mt2">Calibration par contexte (niveau → régime → global · catalyseur/type = observation, jamais consommés)</div><div>'+cells.join('')+'</div>'):'';
      })()
      +'<div class="vx-kpi-label vx-mt2">Biais surveillés</div><div>'+pats+'</div>'
      +(recs?'<div class="vx-kpi-label vx-mt2">Propositions</div>'+recs:'')
      +(function(){
        const last=(d.decisions||[]).slice(-5).reverse();
        if(!last.length)return '';
        return '<div class="vx-kpi-label vx-mt2">Dernières décisions figées</div>'
          +'<div class="vx-table-wrap"><table class="vx-table"><thead><tr><th>Titre</th><th>Décision</th><th>Moteur</th><th>Séance</th><th>Post-mortem</th></tr></thead><tbody>'
          +last.map(r=>'<tr><td data-label="Titre"><b>'+esc(r.symbol)+'</b></td>'
            +'<td data-label="Décision">'+esc(r.decision)+'</td>'
            +'<td data-label="Moteur" class="vx-mono">'+esc(r.engine_version||'n/d')+'</td>'
            +'<td data-label="Séance">'+esc(r.session_date||'n/d')+'</td>'
            +'<td data-label="Post-mortem"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/memory/'+encodeURIComponent(r.decision_id)+'">détail →</a></td></tr>').join('')
          +'</tbody></table></div>';
      })()
      +'<div class="vx-meta" style="margin-top:.35rem">Ledger immuable — les décisions historiques ne sont jamais réécrites ; résultats séparés par version de moteur ; biais inobservables sans trades réels dits INSUFFISANT.</div>';
  }catch(e){host.innerHTML='<div class="vx-error-banner">Mémoire injoignable : '+esc(e.message)+'</div>';}
}
async function loadPostmortem(){
  const host=$('vx-pf-postmortem');if(!host)return;
  let d=null;
  try{d=await VX.fetch('/api/journal/postmortem',{ttl:60000});}catch(e){
    host.innerHTML=VX.states.error('Post-mortem indisponible : '+e.message);return;}
  if(!d||d.empty){
    host.innerHTML=VX.states.empty(esc((d&&d.reason)||'Aucun trade clôturé pour l\'instant.'),
      '<span class="vx-meta">Le post-mortem se construit avec tes clôtures (Portefeuille → Gérer → Clôturer).</span>');
    return;}
  const kpi=(l,v,cls)=>'<div class="vx-stat"><span class="vx-stat-label">'+l+'</span><span class="vx-stat-value '+(cls||'')+'">'+v+'</span></div>';
  const money=(x)=>x==null?'n/d':((x>=0?'+':'')+VX.fmt.num(x,0));
  host.innerHTML=
    '<div class="vx-stats-row">'
    +kpi('Trades',d.trades_n)
    +kpi('Réussite',d.win_rate!=null?d.win_rate+' %':'n/d')
    +kpi('P&L cumulé',money(d.total_pnl),d.total_pnl>0?'vx-pos':d.total_pnl<0?'vx-neg':'')
    +kpi('Profit factor',d.profit_factor!=null?VX.fmt.num(d.profit_factor,2):'n/d',d.profit_factor>=1?'vx-pos':'vx-neg')
    +kpi('Espérance/trade',money(d.expectancy),d.expectancy>0?'vx-pos':'vx-neg')
    +kpi('Durée moy.',d.hold_days_avg!=null?d.hold_days_avg+' j':'n/d')
    +'</div>'
    +'<p class="vx-lead" style="font-size:14px">'+esc(d.narrative||'')+'</p>'
    +((d.flags||[]).length?'<div class="vx-insight" data-tone="risk"><b>Drapeaux de discipline.</b><ul style="margin:.3rem 0 0;padding-left:1.1rem">'
      +d.flags.map(f=>'<li>'+esc(f)+'</li>').join('')+'</ul></div>':'')
    +((d.mistakes||[]).length?'<div class="vx-mt2 vx-muted">Erreurs notées : '
      +d.mistakes.map(m=>esc((m.ticker||'')+' — '+m.mistake)).join(' · ')+'</div>':'')
    +'<div class="vx-card-footer">Post-mortem descriptif (moteur déterministe, trades réels du desk) — pas un conseil.</div>';
}
function wireMemoryImport(){
  const inp=$('vx-mem-import-file');const host=$('vx-mem-import-result');
  if(!inp||!host||inp.dataset.wired)return;
  inp.dataset.wired='1';
  inp.addEventListener('change',()=>{
    const f=inp.files&&inp.files[0];if(!f)return;
    host.innerHTML='<div class="vx-insight" data-tone="neutral">Restauration en cours…</div>';
    const rd=new FileReader();
    rd.onload=async()=>{
      let bundle=null;
      try{bundle=JSON.parse(rd.result);}catch(e){
        host.innerHTML='<div class="vx-insight" data-tone="negative">Fichier illisible : pas un JSON valide.</div>';
        inp.value='';return;
      }
      try{
        const r=await fetch('/api/skyler/memory/import',{method:'POST',
          headers:{'Content-Type':'application/json'},body:JSON.stringify(bundle)});
        const d=await r.json();
        if(!r.ok||!d.ok){
          // erreur serveur affichée TELLE QUELLE (empreinte invalide, etc.)
          host.innerHTML='<div class="vx-insight" data-tone="negative">Import refus&eacute; — '
            +esc(d.error||('HTTP '+r.status))+(d.note?' : '+esc(d.note):'')+'</div>';
        }else{
          const s=d.stats||{};const ses=s.sessions||{};const j=s.journal||{};
          host.innerHTML='<div class="vx-insight" data-tone="positive">Restauration termin&eacute;e — '
            +'d&eacute;cisions : '+(s.added_decisions||0)+' ajout&eacute;e(s), '+(s.skipped_decisions||0)+' d&eacute;j&agrave; pr&eacute;sente(s) (la donn&eacute;e locale gagne) · '
            +'s&eacute;ances : '+(ses.added_sessions||0)+' ajout&eacute;e(s) · '
            +'journal : '+(j.added_entries||0)+' ajout&eacute;e(s)'
            +(((s.corrupted_entries||0)+(ses.corrupted_entries||0)+(j.corrupted_entries||0))>0
              ?' · entr&eacute;es corrompues ignor&eacute;es : '+((s.corrupted_entries||0)+(ses.corrupted_entries||0)+(j.corrupted_entries||0)):'')
            +' — ledger : '+esc((d.ledger_health||{}).status||'n/d')+'</div>';
          loadMemory();
        }
      }catch(e){
        host.innerHTML='<div class="vx-insight" data-tone="negative">Import impossible : '+esc(String(e))+'</div>';
      }
      inp.value='';
    };
    rd.readAsText(f);
  });
}
function bindDisclosures(){
  document.querySelectorAll('details.vx-disclosure').forEach(d=>{
    if(d.dataset.vxBound)return;
    d.dataset.vxBound='1';
    d.addEventListener('toggle',()=>{if(d.open)window.dispatchEvent(new Event('resize'));});
  });
}
function boot(){
  bindDisclosures();
  if(VIEW==='overview'){
    /*  `loadDiscipline()` etait appelee ICI et definie NULLE PART. Comme elle
        ouvrait la chaine, la vue « overview » du Journal levait des le premier
        appel : AUCUN des cinq blocs suivants ne se chargeait. Retiree — les
        cinq qui existent se chargent maintenant.  */
    /*  Trois chargeurs etaient definis et appeles NULLE PART depuis le retrait
        de `loadDiscipline()` : `loadKpis` (la bande d'indicateurs et la carte
        « Construis ton track record »), `loadEquity` (courbe + drawdown) et
        `loadMonthlyAndDist` (heatmap mensuelle). La bande gardait donc son
        squelette indefiniment — une donnee promise qui n'arrivait jamais —
        et les deux autres n'avaient meme plus de conteneur ou ecrire.  */
    loadKpis();echantillon();
    loadHypotheses();loadDist();loadPostmortem();loadCalibration();loadMemory();wireMemoryImport();
    loadEquity();loadDiscipline();}
  else if(VIEW==='journal'){
    loadJournal();loadMistakes();
    $('vx-pf-add')?.addEventListener('click',openEntryModal);
    $('vx-pf-filter')?.addEventListener('input',loadJournal);
  }
  else if(VIEW==='learnings'){loadLearnings();}
  else if(VIEW==='progression'){loadProgression();}
  else if(VIEW==='track-record'){loadTrack();}
  else if(VIEW==='real'){loadReal();echantillon();}
}
function whenReady(fn){
  if(window.VXEntities&&(VIEW!=='overview'&&VIEW!=='progression'||(window.VXCharts&&window.Chart)))return fn();
  window.addEventListener('load',fn,{once:true});
}
whenReady(boot);
VX.bus.on('vx:data-refreshed',()=>whenReady(boot));
})();
</script>
"""


# La heatmap mensuelle figure au contrat, et son code de rendu n'existe plus :
# il avait été remplacé, dans la fonction censée le porter, par le corps d'un
# `loadDiscipline()` retiré. Le réécrire supposerait d'agréger des rendements
# par mois DANS L'UI — ce que `performance-center.md` interdit explicitement
# (« ne jamais recalculer … dans la couche UI »). On l'avoue.
_MENSUEL = vx2.capacite_absente(
    quoi='Heatmap mensuelle',
    pourquoi='Aucun moteur n’agrège les rendements par mois, et l’agrégation '
             'ne doit pas être faite dans l’interface. La distribution par '
             'tranche, elle, ne fait que compter des clôtures : elle reste '
             'affichée ci-dessous.')

def _entete() -> str:
    """En-tête + contexte. La barre de contexte nomme la POPULATION mesurée :
    sans elle, un « taux de réussite » se lit comme celui du portefeuille, alors
    qu'il ne porte que sur les trades déclarés au journal (contrôle 101)."""
    return (
        vx2.page_header(
            surtitre='Gérer', titre='Performance',
            question='La méthode fonctionne-t-elle, et est-elle bien appliquée ?',
            actions=vx2.bouton('Ouvrir le Portefeuille', href='/portfolio',
                               variante='ghost'))
        + vx2.context_bar([
            {'label': 'Population mesurée', 'contenu':
                '<span class="vx2-stamp"><b>Trades réels déclarés</b> au journal '
                'du desk</span>'},
            {'label': 'Nature du résultat', 'contenu':
                '<span class="vx2-stamp">Réalisé — encaissé, hors frais '
                'et dividendes</span>'},
            {'label': 'Échantillon', 'contenu':
                '<span id="vx-pf-echantillon">'
                + vx2.badge_etat('missing', texte='Lecture…') + '</span>'},
            {'label': 'Calcul', 'contenu':
                '<span class="vx2-stamp">Arithmétique sur vos déclarations — '
                '<b>aucun moteur</b></span>'},
        ]))


def render(view: str = 'overview', params: dict | None = None) -> str:
    """Assemble la Performance pour la sous-vue demandée (URL = état)."""
    view = _ALIAS.get(view, view)
    if view not in dict(_VIEWS):
        view = 'overview'
    label = dict(_VIEWS)[view]
    sym = ''
    if params:
        raw = str(params.get('sym') or '').strip().upper()
        if re.fullmatch(r'[A-Z.\-]{1,7}', raw):
            sym = raw
    content = (_HEADER.replace('%%ENTETE%%', _entete())
               .replace('%%TABS%%', _tabs(view))
               + _VIEW_CONTENT[view]
               .replace('%%POPULATIONS%%', _populations())
               .replace('%%MENSUEL%%', _MENSUEL))
    content = content.replace('%%SYM%%', html.escape(sym)).replace(
        '%%LOADING%%', '<div class="vx-skeleton" style="height:60px"></div>')
    page_js = _JS.replace('%%VIEW%%', view)
    # Vertex 2.0 : l'espace s'appelle Performance ; le Journal en est une
    # sous-vue. `page_label` reste « Journal » — plusieurs bancs et le routeur
    # client s'y adossent, et l'étiquette décrit toujours ce que la vue montre.
    return render_shell(title='Performance', active='performance',
                        space_label='Performance', sub_label=label,
                        content=content, page_js=page_js,
                        page_label='Journal')
