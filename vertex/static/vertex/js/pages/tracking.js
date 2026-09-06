/* tracking.js — espace Suivis (§17). Lit /api/tracking + performance par suivi.
   Tout gain est étiqueté HYPOTHÉTIQUE. Lecture seule. */
(function () {
  'use strict';
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var VXf = (window.VX && VX.fmt) || { nd: function (v) { return v == null ? '—' : v; }, num: function (v, d) { return v == null ? '—' : Number(v).toFixed(d || 2); } };

  function get(url) { return (window.VX && VX.fetch) ? VX.fetch(url, { ttl: 10000 }) : fetch(url).then(function (r) { return r.json(); }); }
  function pct(v) {
    if (v == null) return '<span class="vx-muted">—</span>';
    var cls = v >= 0 ? 'vx-pos' : 'vx-neg';
    return '<span class="' + cls + '">' + (v >= 0 ? '+' : '') + VXf.num(v, 2) + ' %</span>';
  }
  function absDate(iso) {
    if (!iso) return '—';
    try { var d = new Date(iso); return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }); }
    catch (e) { return esc(iso); }
  }

  function summaryHtml(s) {
    // Tuile canonique via le builder partagé (markup .vx-stat/.vx-stat-k/-v stylé
    // par premium.css/glass.css). Repli inline si VX.tile pas encore chargé.
    function stat(l, v) {
      return (window.VX && VX.tile) ? VX.tile.stat({ k: l, v: v })
        : '<div class="vx-stat"><div class="vx-stat-k">' + esc(l) + '</div><div class="vx-stat-v">' + v + '</div></div>';
    }
    return '<div class="vx-statrow">' +
      stat('Actifs', VXf.nd(s.active)) + stat('Actions', VXf.nd(s.stocks)) +
      stat('Options', VXf.nd(s.options)) + stat('Clôturés', VXf.nd(s.stopped)) +
      stat('Réf. manquante', VXf.nd(s.data_required)) + '</div>';
  }

  /* TROIS ABSENCES DIFFERENTES S'ECRIVAIENT DU MEME TIRET — mesure du
     06/09/2026. Sur une instance QA fraiche, `/api/tracking/<id>/performance`
     rend `benchmark_return_pct: null` et `alpha_pct: null` (SPY pas encore
     cote) alors que `return_pct` vaut 0,0 : les colonnes SPY et Alpha
     affichaient « — », soit exactement ce qu'affiche un suivi sans prix de
     reference, et exactement ce qu'affiche un suivi dont la performance n'a
     pas pu etre lue du tout. Trois causes, un seul signe.

     `pct()` reste pour les lignes cloturees, ou le chiffre final est fige.
     Ici chaque absence dit la SIENNE. */
  function pctCause(v, cause) {
    if (v == null) return '<span class="vx-muted">' + esc(cause) + '</span>';
    var cls = v >= 0 ? 'vx-pos' : 'vx-neg';
    return '<span class="' + cls + '">' + (v >= 0 ? '+' : '') + VXf.num(v, 2) + ' %</span>';
  }
  function activeRow(t, p) {
    var ref = t.reference_price;
    //  `p` absent = la route de performance n'a pas repondu pour CE suivi.
    //  Ce n'est pas « pas de reference » : la cause est en amont.
    var muet = p ? null : 'non lu';
    return '<tr>' +
      '<td><b>' + esc(t.symbol) + '</b>' + (t.entity_type === 'OPTION' ? ' <span class="vx-muted">OPT</span>' : '') + '</td>' +
      '<td>' + absDate(t.started_at) + '</td>' +
      '<td>' + (ref != null ? VXf.num(ref, 2) : '<span class="vx-muted">réf. requise</span>') +
      (t.reference_price_type ? ' <span class="vx-muted">(' + esc(t.reference_price_type) + ')</span>' : '') + '</td>' +
      '<td>' + (p && p.current_price != null ? VXf.num(p.current_price, 2) : '<span class="vx-muted">' + (muet || 'non coté') + '</span>') + '</td>' +
      '<td>' + pctCause(p && p.return_pct, muet || 'réf. requise') + '</td>' +
      '<td>' + pctCause(p && p.benchmark_return_pct, muet || 'réf. SPY n/d') + '</td>' +
      '<td>' + pctCause(p && p.alpha_pct, muet || 'sans réf. SPY') + '</td>' +
      '<td>' + pctCause(p && p.mfe_pct, muet || 'n/d') + ' / ' + pctCause(p && p.mae_pct, muet || 'n/d') + '</td>' +
      '<td>' + esc(t.strategy_decision_at_start || '—') + '</td>' +
      '</tr>';
  }

  function table(head, bodyRows) {
    return '<div class="vx-table-wrap"><table class="vx-table"><thead><tr>' +
      head.map(function (h) { return '<th>' + h + '</th>'; }).join('') +
      '</tr></thead><tbody>' + bodyRows + '</tbody></table></div>';
  }

  // Graphique interactif : rendement hypothétique vs SPY par suivi actif.
  function renderPerfChart(rows) {
    var host = document.getElementById('vx-trk-chart');
    var VC = window.VXCharts;
    if (!host || !VC || !window.Chart) return;
    var pts = rows.filter(function (r) { return r.p && r.p.return_pct != null; });
    if (!pts.length) { host.innerHTML = ''; return; }
    var positive = (VC.colors && VC.colors.positive) || '#2BBE90';
    var negative = (VC.colors && VC.colors.negative) || '#E9555F';
    var neutral = (VC.colors && VC.colors.neutral) || '#9d978e';
    var labels = pts.map(function (r) { return r.t.symbol; });
    var self = pts.map(function (r) { return +r.p.return_pct.toFixed(2); });
    var spy = pts.map(function (r) { return r.p.benchmark_return_pct != null ? +r.p.benchmark_return_pct.toFixed(2) : null; });
    VC.card('vx-trk-chart', {
      title: 'Performance hypothétique depuis le suivi',
      question: 'Chaque idée suivie bat-elle SPY depuis que je l\'ai marquée ?',
      conclusion: pts.length + ' suivi(s) actif(s) — rendements 100 % hypothétiques',
      height: 240, source: 'SCAN', timestamp: null, mode: 'delayed',
      limits: 'rendement prix hors frais/dividendes · aucune position réelle',
      legend: [{ label: 'Idée suivie — émeraude = gain / corail = perte', color: positive }, { label: 'SPY (référence)', color: neutral }],
      explain: {
        shows: 'Le rendement de chaque idée suivie et celui de SPY sur la même fenêtre.',
        why: 'Vertex vise à battre SPY : un alpha positif valide la sélection.',
        confirm: 'Barre de l\'idée au-dessus de sa barre SPY (grise) → alpha positif.',
        invalidate: 'Sous-performance persistante vs SPY.'
      },
      render: function (cv) {
        return VC.mount(cv, {
          type: 'bar',
          data: {
            labels: labels, datasets: [
              { label: 'Idée suivie', data: self, backgroundColor: self.map(function (v) { return v >= 0 ? positive : negative; }), borderRadius: 3, maxBarThickness: 26 },
              { label: 'SPY', data: spy, backgroundColor: neutral + 'cc', borderRadius: 3, maxBarThickness: 26 }
            ]
          },
          options: {
            interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ' : ' + (ctx.parsed.y == null ? '—' : (ctx.parsed.y >= 0 ? '+' : '') + ctx.parsed.y + ' %'); } } } },
            scales: { y: { suggestedMin: -1, suggestedMax: 1, ticks: { callback: function (v) { return v + ' %'; } } } }
          }
        });
      }
    });
  }

  /* « A REVOIR » ET « SUIVIS ACTIFS » RENDAIENT LE MEME ECRAN — mesure du
     06/09/2026 sur l'instance QA : memes sections visibles
     (summary/chart/active), meme titre, meme question, meme unique ligne
     NVDA. La table `montre` ci-dessous donnait deja `attention` et `active`
     a l'identique. Deux onglets, un seul ecran : le second ne repond a rien.

     Ce qui separe reellement les deux est SERVI, pas invente : `/api/tracking`
     rend un statut par suivi, et `DATA_REQUIRED` designe litteralement le
     suivi qu'on ne peut pas mesurer faute de prix de reference (la table
     ecrit deja « ref. requise » sur cette ligne). « A revoir » liste donc ce
     qui attend une donnee ; « Suivis actifs » liste tout l'actif.

     Aucun seuil de performance n'entre ici : « sous-performe SPY » serait un
     jugement invente par la page, pas un etat de la donnee. */
  function aReVoir(t) {
    return t.status === 'DATA_REQUIRED' || t.reference_price == null;
  }

  /* Sous-vue demandee. Les trois sections restent dans le DOM : un seul appel
     reseau les remplit toutes, et masquer coute moins qu'un second aller-retour. */
  function vueCourante() {
    var el = document.querySelector('[data-trk-view]');
    return (el && el.getAttribute('data-trk-view')) || 'attention';
  }
  function appliquerVue() {
    var v = vueCourante();
    /* Le graphique « performance vs SPY » repond a la question de l'onglet
       ACTIF. Dans « A revoir », les lignes retenues sont justement celles
       sans prix de reference : il n'aurait aucune serie a tracer. */
    var montre = {
      attention: ['vx-trk-summary', 'vx-trk-active'],
      active: ['vx-trk-summary', 'vx-trk-chart', 'vx-trk-active'],
      archives: ['vx-trk-summary', 'vx-trk-stopped']
    }[v] || ['vx-trk-summary', 'vx-trk-chart', 'vx-trk-active'];
    ['vx-trk-summary', 'vx-trk-chart', 'vx-trk-active', 'vx-trk-stopped']
      .forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.hidden = montre.indexOf(id) === -1;
      });
  }

  /* La fraicheur : `/api/tracking` ne porte pas d'horodatage. On l'AVOUE plutot
     que d'afficher l'heure du navigateur — c'est le raccourci que trois pages
     du produit prennent avec `cal.ts || Date.now()`, et il rend une fraicheur
     toujours verte, et fausse. */
  function peindreFraicheur(d) {
    var el = document.getElementById('vx-trk-fresh');
    if (!el) return;
    var n = (d && d.summary && d.summary.total) || 0;
    el.innerHTML = '<span class="vx2-badge" data-state="missing">'
      + (n ? n + ' suivi' + (n > 1 ? 's' : '') + ' \u00b7 horodatage non fourni'
          : 'Aucun suivi enregistr\u00e9') + '</span>';
  }

  function loadActive() {
    appliquerVue();
    var sEl = document.getElementById('vx-trk-summary-body');
    var aEl = document.getElementById('vx-trk-active-body');
    var xEl = document.getElementById('vx-trk-stopped-body');
    get('/api/tracking').then(function (d) {
      var items = (d && d.trackings) || [];
      peindreFraicheur(d);
      if (sEl) sEl.innerHTML = summaryHtml((d && d.summary) || {});
      var actifs = items.filter(function (t) { return t.status === 'ACTIVE' || t.status === 'DATA_REQUIRED'; });
      var stopped = items.filter(function (t) { return t.status === 'STOPPED'; });
      /* La sous-vue choisit sa POPULATION, et le titre dit laquelle : sans ce
         couple, « A revoir » affichait le tableau complet sous le titre
         « Suivis actifs » — l'onglet ne changeait rien et le titre mentait. */
      var vue = vueCourante();
      var attention = vue === 'attention';
      var active = attention ? actifs.filter(aReVoir) : actifs;
      var tEl = document.getElementById('vx-trk-active-title');
      var qEl = document.getElementById('vx-trk-active-question');
      if (tEl) tEl.textContent = attention ? 'À revoir' : 'Suivis actifs';
      if (qEl) qEl.textContent = attention
        ? 'Quels suivis attendent une donnée avant de pouvoir être mesurés ?'
        : 'Que valent ces idées depuis qu’elles sont marquées ?';
      if (!active.length) {
        /* Trois vides DISTINCTS : rien de suivi · rien a revoir alors que des
           suivis existent · rien d'actif. Un seul « Aucun suivi » melangeait
           « je n'ai rien a te signaler » et « tu n'as rien enregistre ». */
        var cause = attention
          ? (actifs.length
              ? 'Les ' + actifs.length + ' suivi(s) actif(s) ont tous un prix de référence : rien n’attend de donnée.'
              : 'Aucun suivi actif — donc rien à revoir.')
          : 'Aucun suivi actif. Marque une idée « Suivre » depuis Opportunités ou une analyse.';
        aEl.innerHTML = '<div class="vx2-state" data-kind="empty" role="status">'
          + '<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
          + '<p class="vx2-state-title">' + (attention ? 'Rien à revoir' : 'Aucun suivi actif') + '</p>'
          + '<p class="vx2-state-cause">' + esc(cause) + '</p></div>';
      } else {
        // charge la performance de chaque suivi (séquentiel léger)
        Promise.all(active.map(function (t) {
          return get('/api/tracking/' + encodeURIComponent(t.tracking_id) + '/performance')
            .then(function (p) { return { t: t, p: p }; }).catch(function () { return { t: t, p: null }; });
        })).then(function (rows) {
          aEl.innerHTML = table(['Titre', 'Depuis le', 'Référence', 'Actuel', 'Rdt hypo.', 'SPY', 'Alpha', 'MFE / MAE', 'Décision init.'],
            rows.map(function (r) { return activeRow(r.t, r.p); }).join(''));
          if (!attention) renderPerfChart(rows);
        });
      }
      if (stopped.length) {
        xEl.innerHTML = table(['Titre', 'Ouvert', 'Clôturé', 'Rdt final hypo.', 'MFE', 'MAE', 'Décision'],
          stopped.map(function (t) {
            var f = t.final || {};
            return '<tr><td><b>' + esc(t.symbol) + '</b></td><td>' + absDate(t.started_at) + '</td><td>' + absDate(t.stopped_at) +
              '</td><td>' + pct(f.return_pct) + '</td><td>' + pct(f.mfe_pct) + '</td><td>' + pct(f.mae_pct) +
              '</td><td>' + esc(f.final_decision || '—') + '</td></tr>';
          }).join(''));
      } else if (xEl) {
        xEl.innerHTML = '<div class="vx2-state" data-kind="empty" role="status">'
          + '<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
          + '<p class="vx2-state-title">Aucun suivi cl\u00f4tur\u00e9</p>'
          + '<p class="vx2-state-cause">Aucune id\u00e9e suivie n\u2019a encore \u00e9t\u00e9 arr\u00eat\u00e9e. '
          + 'Les archives se remplissent quand un suivi prend fin.</p></div>';
      }
    }).catch(function (e) {
      if (aEl) aEl.innerHTML = '<div class="vx-error-banner">⚠ ' + esc(e.message) + '</div>';
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadActive);
  else loadActive();
})();
