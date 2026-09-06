/* Vertex Charts — chart-core.js
   Moteur unique : Chart.js (déjà embarqué) + contrat visuel §34.
   Chaque graphique = ChartCard { titre, question, conclusion, corps, pied
   (source/date/mode/limites), bouton « Comprendre ce graphique » }.
   L'UI ne calcule AUCUN indicateur : elle trace ce que les moteurs donnent. */
(function () {
  'use strict';
  const VX = window.VX;
  const C = window.VXCharts = window.VXCharts || {};

  /* Thème V3 unique (chart-theme.js) — repli sur les mêmes valeurs si absent */
  const THEME = window.VXChartTheme || { colors: {}, tooltip: {} };
  C.colors = Object.assign({
    brand: '#c9cdd4', blue: '#c9cdd4', cyan: '#c0b79f', violet: '#9c79d0',
    option: '#9c79d0', teal: '#53b9ad', plum: '#8f698c', sand: '#c0b79f',
    steel: '#909b94', stone: '#6d746e',
    positive: '#36c889', negative: '#ed655c', warning: '#dda23b',
    info: '#c9cdd4', neutral: '#8f8a83',
    text: '#b7b3ad', muted: '#817d77', grid: 'rgba(255,255,255,.05)',
    series: ['#c9cdd4', '#8f8a83', '#9aa1a9', '#9c79d0', '#dda23b', '#6d746e'],
    /* Palette macro/cross-asset : teal en tête (jamais confondu avec la marque) */
    macroSeries: ['#53b9ad', '#c0b79f', '#8f698c', '#909b94', '#dda23b', '#6d746e'],
  }, THEME.colors);

  /* Police des labels dessinés au canvas (SVG hérite du body ; le canvas non).
     Dérivée de --vx-font pour suivre la typo globale, mise en cache. */
  let _labelFam = '';
  C.labelFont = function (px) {
    if (!_labelFam) _labelFam = (getComputedStyle(document.documentElement).getPropertyValue('--vx-font') || '').trim() || 'sans-serif';
    return (px || 9) + 'px ' + _labelFam;
  };

  /* ── Rendu MODERNE (global) : dégradés, glow, barres arrondies, crosshair ──
     Un seul endroit → tous les graphiques Chart.js de l'app en profitent. */
  function _rgba(col, a) {
    if (typeof col !== 'string') return null;
    if (col[0] === '#' && col.length >= 7) {
      const r = parseInt(col.slice(1, 3), 16), g = parseInt(col.slice(3, 5), 16), b = parseInt(col.slice(5, 7), 16);
      if ([r, g, b].some(isNaN)) return null;
      return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
    }
    const m = col.match(/rgba?\(([^)]+)\)/);
    if (m) { const p = m[1].split(',').slice(0, 3).map(s => s.trim()); return 'rgba(' + p.join(',') + ',' + a + ')'; }
    return null;
  }
  /* Exposé : dériver une couleur du thème avec alpha (ex. heatmap → C.colors.positive).
     Source unique → plus aucune divergence de teinte hors-thème. */
  C.rgba = _rgba;
  /* Arrondi de barre UNIQUE (cohérence de tous les graphes à barres). */
  C.barRadius = 4;
  /* Carte à état vide honnête (évite le canvas blanc) — tête + pied conservés. */
  C.emptyCard = function (host, opts, reason) {
    return C.card(host, Object.assign({}, opts, {
      state: 'empty', emptyReason: reason || (opts && opts.emptyReason) || 'Aucune donnée disponible pour l’instant.',
    }));
  };
  /* Longueur de données valides (>0 point non-nul) pour décider READY vs EMPTY. */
  C.hasData = function (arr) { return Array.isArray(arr) && arr.some(v => v !== null && v !== undefined && !(typeof v === 'number' && isNaN(v))); };
  /* Lueur douce sous chaque ligne (couleur de la série) — désactivée si l'OS
     demande moins d'animations (économie de peinture). */
  const _glowPlugin = {
    id: 'vxglow',
    beforeDatasetDraw(chart, args) {
      if (args.meta.type !== 'line') return;
      const ds = chart.data.datasets[args.index] || {};
      const col = typeof ds.borderColor === 'string' ? _rgba(ds.borderColor, .40) : null;
      const c = chart.ctx; c.save();
      c.shadowColor = col || 'rgba(201,205,212,.28)';
      c.shadowBlur = 8; c.shadowOffsetY = 1;
    },
    afterDatasetDraw(chart, args) { if (args.meta.type === 'line') chart.ctx.restore(); },
  };
  /* Point de tête lumineux au bout de chaque ligne (réf. visuelle : bille blanche
     glow). Ignoré sur les micro-sparklines (zone trop courte) et sur les lignes qui
     affichent déjà leurs points, pour éviter l'encombrement. */
  const _leadDotPlugin = {
    id: 'vxleaddot',
    afterDatasetsDraw(chart) {
      const a = chart.chartArea;
      if (!a || (a.bottom - a.top) < 46) return;
      chart.data.datasets.forEach(function (ds, i) {
        if (ds.pointRadius) return;
        const meta = chart.getDatasetMeta(i);
        if (!meta || meta.type !== 'line' || meta.hidden) return;
        const pts = meta.data || [];
        let p = null;
        for (let k = pts.length - 1; k >= 0; k--) { const q = pts[k]; if (q && !q.skip && isFinite(q.x) && isFinite(q.y)) { p = q; break; } }
        if (!p) return;
        const col = typeof ds.borderColor === 'string' ? ds.borderColor : C.colors.brand;
        const c = chart.ctx; c.save();
        c.shadowColor = col; c.shadowBlur = 8;
        c.beginPath(); c.arc(p.x, p.y, 3, 0, Math.PI * 2); c.fillStyle = col; c.fill();
        c.shadowBlur = 0;
        c.beginPath(); c.arc(p.x, p.y, 1.4, 0, Math.PI * 2); c.fillStyle = '#fff'; c.fill();
        c.restore();
      });
    },
  };
  /* Crosshair pointillé vertical au survol (axes cartésiens uniquement).

     UN SEUL tracé, deux façons de le demander : l'objet `_crossPlugin` pour
     les graphiques qui prennent la couleur par défaut, et la fabrique
     `C.crosshairPlugin(couleur)` pour ceux qui la choisissent.

     La fabrique était APPELÉE par `candlestick-chart.js`
     (`C.crosshairPlugin(C.colors.brand)`) et n'existait PAS : la carte
     chandeliers de la fiche Analyse levait « C.crosshairPlugin is not a
     function » à chaque rendu, et le graphique principal du titre ne
     s'affichait jamais.

     Écrire une seconde implémentation aurait fait diverger les deux tracés au
     premier ajustement ; la fabrique délègue donc au même dessin. */
  function _dessinerCroix(chart, couleur) {
    if (!chart.scales || !chart.scales.x || !chart.chartArea) return;
    const act = chart.tooltip && chart.tooltip.getActiveElements ? chart.tooltip.getActiveElements() : [];
    if (!act.length) return;
    const el0 = act[0].element, x = el0.x, y = el0.y, a = chart.chartArea, c = chart.ctx;
    c.save(); c.strokeStyle = couleur || 'rgba(255,255,255,.14)'; c.lineWidth = 1; c.setLineDash([3, 3]);
    c.beginPath(); c.moveTo(x, a.top); c.lineTo(x, a.bottom); c.stroke();
    if (typeof y === 'number' && y >= a.top && y <= a.bottom) {
      c.beginPath(); c.moveTo(a.left, y); c.lineTo(a.right, y); c.stroke();
    }
    c.restore();
  }
  const _crossPlugin = {
    id: 'vxcrosshair',
    afterDraw(chart) { _dessinerCroix(chart, null); },
  };
  /* La couleur de marque est ARGENT dans Black Glass : on l'attenue pour que
     la croix reste un repère et ne concurrence pas la donnée. */
  C.crosshairPlugin = function (couleur) {
    return { id: 'vxcrosshair-teinte',
             afterDraw: function (chart) { _dessinerCroix(chart, couleur || null); } };
  };
  function chartDefaults() {
    if (!window.Chart) return;
    const d = Chart.defaults;
    d.font.family = getComputedStyle(document.documentElement).getPropertyValue('--vx-font') || 'Inter,sans-serif';
    d.font.size = 11;
    /* Couleurs sémantiques dérivées des tokens CSS (source unique → aucune divergence
       canvas/CSS si un token change ; repli sur les hex du thème). */
    try {
      const cs = getComputedStyle(document.documentElement);
      const tk = (n, f) => { const v = (cs.getPropertyValue(n) || '').trim(); return v || f; };
      C.colors.positive = tk('--vx-positive', C.colors.positive);
      C.colors.negative = tk('--vx-negative', C.colors.negative);
      C.colors.warning = tk('--vx-warning', C.colors.warning);
      C.colors.option = C.colors.violet = tk('--vx-option', C.colors.option);
      C.colors.brand = tk('--vx-brand', C.colors.brand);
    } catch (e) { /* garde les hex de repli */ }
    d.color = C.colors.text;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) d.animation = false;
    else if (d.animation && typeof d.animation === 'object') { d.animation.duration = 260; d.animation.easing = 'easeOutQuart'; }
    d.plugins.legend.display = false;
    d.interaction = { mode: 'nearest', axis: 'xy', intersect: false };
    const tt = (window.VXChartTheme && window.VXChartTheme.tooltip) || {};
    d.plugins.tooltip.backgroundColor = tt.backgroundColor || '#151719';
    d.plugins.tooltip.borderColor = tt.borderColor || 'rgba(255,255,255,.15)';
    d.plugins.tooltip.borderWidth = 1;
    d.plugins.tooltip.padding = 10;
    d.plugins.tooltip.cornerRadius = 8;
    d.plugins.tooltip.titleColor = tt.titleColor || '#f3f1ed';
    d.plugins.tooltip.bodyColor = tt.bodyColor || '#b7b3ad';
    /* Tooltip enrichi (global) : pastilles rondes, espacement, typo explicite. */
    d.plugins.tooltip.usePointStyle = true;
    d.plugins.tooltip.boxWidth = 8; d.plugins.tooltip.boxHeight = 8; d.plugins.tooltip.boxPadding = 4;
    d.plugins.tooltip.caretSize = 5; d.plugins.tooltip.bodySpacing = 4;
    d.plugins.tooltip.titleFont = { weight: '600', size: 11.5 };
    d.plugins.tooltip.bodyFont = { size: 11.5 };
    d.maintainAspectRatio = false;
    /* Points (nuages/bulles) : liseré sombre discret pour détacher les points qui
       se chevauchent + zone de survol confortable. Sans effet sur les lignes
       (pointRadius:0 → non dessinés). */
    try {
      d.elements.point.borderWidth = 1;
      d.elements.point.borderColor = 'rgba(8,9,11,.6)';
      d.elements.point.hoverRadius = 6;
      d.elements.point.hitRadius = 6;
    } catch (e) { /* defaults absents */ }
    try { if (!reduced) { Chart.register(_glowPlugin); Chart.register(_leadDotPlugin); } Chart.register(_crossPlugin); } catch (e) { /* déjà enregistrés */ }
  }
  if (window.Chart) chartDefaults(); else document.addEventListener('DOMContentLoaded', chartDefaults);

  /* Modernise une config avant montage : remplissage des lignes en DÉGRADÉ
     vertical (couleur de série → transparent) et barres ARRONDIES. Opt-out
     naturel : une série qui fournit déjà un backgroundColor scriptable ou un
     borderRadius garde son réglage. */
  function _modernize(config) {
    const sets = (config && config.data && config.data.datasets) || [];
    sets.forEach(function (ds) {
      const t = ds.type || config.type;
      if (t === 'line' && ds.fill && typeof (ds.backgroundColor || '') === 'string') {
        const base = (typeof ds.borderColor === 'string' && _rgba(ds.borderColor, 1)) ? ds.borderColor : ds.backgroundColor;
        const top = _rgba(base, .30), mid = _rgba(base, .12), bottom = _rgba(base, .02);
        if (top && bottom) ds.backgroundColor = function (c2) {
          const ch = c2.chart, area = ch.chartArea;
          if (!area) return bottom;
          const g = ch.ctx.createLinearGradient(0, area.top, 0, area.bottom);
          g.addColorStop(0, top); if (mid) g.addColorStop(.55, mid); g.addColorStop(1, bottom); return g;
        };
      }
      if (t === 'bar') {
        if (ds.borderRadius == null) ds.borderRadius = C.barRadius;
        if (ds.maxBarThickness == null) ds.maxBarThickness = 38;
      }
    });
    return config;
  }

  const registry = new Map(); // canvasId -> Chart (évite les canvas orphelins)
  C.mount = function (canvas, config) {
    if (!window.Chart || !canvas) return null;
    const prev = registry.get(canvas);
    if (prev) prev.destroy();
    const chart = new Chart(canvas.getContext('2d'), _modernize(config));
    registry.set(canvas, chart);
    return chart;
  };
  C.axes = function ({ y = true, x = true, yFmt } = {}) {
    /* Grille aérée : aucune bordure d'axe, aucune graduation, ticks discrets,
       ligne du zéro plus marquée (repère de lecture P&L/variation). */
    const gridZero = (ctx) => (ctx.tick && ctx.tick.value === 0) ? 'rgba(255,255,255,.16)' : C.colors.grid;
    const tickBase = { padding: 6, color: C.colors.muted, font: { size: 10 } };
    return {
      x: { display: x, border: { display: false },
           grid: { color: C.colors.grid, drawTicks: false, tickLength: 0 },
           ticks: Object.assign({}, tickBase, { maxTicksLimit: 8, maxRotation: 0 }) },
      y: { display: y, position: 'right', border: { display: false },
           grid: { color: gridZero, drawTicks: false, tickLength: 0 },
           ticks: Object.assign({}, tickBase, { maxTicksLimit: 6, callback: yFmt || undefined }) },
    };
  };

  /* ── Gabarits de hauteur (lot 44) : une échelle NOMMÉE au lieu de pixels
     inventés page par page. `size` prime ; `height` numérique reste accepté
     (compat — le pixel desktop des cartes existantes ne bouge pas). Le corps
     émet `--vx-chart-h` : la feuille peut borner en mobile sans toucher au
     choix de la page. ── */
  C.TAILLES = { xs: 120, s: 160, m: 200, l: 240, xl: 300, hero: 360 };
  C.hauteur = function (size, height) {
    if (size && C.TAILLES[size]) return C.TAILLES[size];
    const h = Number(height);
    return (isFinite(h) && h > 0) ? Math.round(h) : C.TAILLES.m;
  };

  /* ── ChartCard : contrat visuel §34 ─────────────────────────────── */
  let uid = 0;
  C.card = function (host, opts) {
    /* opts: {title, question, conclusion, timeframe|period, unit, controlsHtml, height,
              source, timestamp, mode, limits, explain:{shows,why,confirm,invalidate},
              legend:[{label,color}], render(canvas)->Chart}
       period = alias de timeframe (badge). unit = unité de l'axe (%, $, pts…),
       affichée en pied et dans le tiroir « Comprendre » (contrat graphique §34). */
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    /* Re-rendu d'une carte (filtres, périodes) : détruire l'ancien Chart AVANT
       d'écraser le canvas — sinon les instances s'accumulent à chaque repaint. */
    el.querySelectorAll('canvas').forEach(function (oldCv) {
      const prev = registry.get(oldCv) || (window.Chart && Chart.getChart && Chart.getChart(oldCv));
      if (prev) { try { prev.destroy(); } catch (e) { /* déjà détruit */ } }
      registry.delete(oldCv);
    });
    const id = 'vxch-' + (++uid);
    const legend = (opts.legend || []).map(l =>
      `<span><span class="vx-swatch" style="background:${l.color}"></span>${l.label}</span>`).join('');
    el.classList.add('vx-card', 'vx-chart-card');
    /* État de la carte : 'ready' (canvas) sinon loading/empty/error → on peint
       VX.states DANS le corps (tête + pied conservés). Supprime les graphes blancs. */
    const st = opts.state || (opts.render ? 'ready' : 'empty');
    const bodyInner = (st === 'ready')
      ? `<canvas id="${id}" role="img" aria-label="${opts.title || 'graphique'}"></canvas>`
      : (st === 'loading' ? VX.states.loading(3)
        : st === 'error' ? VX.states.error(opts.errorCause, opts.retry)
        : VX.states.empty(opts.emptyReason, opts.emptyAction, opts.emptyOpts || {}));
    el.innerHTML = `
      <div class="vx-chart-head">
        <span class="vx-chart-title">${opts.title || ''}</span>
        ${(opts.timeframe || opts.period) ? `<span class="vx-badge">${opts.timeframe || opts.period}</span>` : ''}
        ${opts.unit ? `<span class="vx-badge vx-badge-unit" title="Unité de l'axe">${opts.unit}</span>` : ''}
        <span class="vx-chart-controls">${opts.controlsHtml || ''}</span>
        ${opts.question ? `<span class="vx-chart-question">${opts.question}</span>` : ''}
        ${opts.conclusion ? `<span class="vx-chart-conclusion">${opts.conclusion}</span>` : ''}
      </div>
      <div class="vx-chart-body" style="--vx-chart-h:${C.hauteur(opts.size, opts.height)}px;height:var(--vx-chart-h)">${bodyInner}</div>
      ${legend ? `<div class="vx-chart-legend">${legend}</div>` : ''}
      <div class="vx-chart-foot">
        ${VX.updateIndicator(opts.timestamp, opts.source, opts.mode)}
        ${opts.limits ? `<span class="vx-meta">${opts.limits}</span>` : ''}
        <span class="vx-chart-tools">
          <button class="vx-btn vx-btn-sm vx-btn-ghost vx-chart-tbl" title="Voir les données en tableau" aria-label="Voir les données">Données</button>
          <button class="vx-btn vx-btn-sm vx-btn-ghost vx-chart-fs" title="Agrandir en plein écran" aria-label="Agrandir en plein écran">⤢ Agrandir</button>
          <button class="vx-btn vx-btn-sm vx-btn-ghost vx-explain-btn" data-explain="${id}">Comprendre</button>
        </span>
      </div>`;
    const canvas = el.querySelector('canvas');
    const chart = (st === 'ready' && opts.render && canvas) ? opts.render(canvas) : null;
    el.querySelector('[data-explain]')?.addEventListener('click', () => {
      const ex = opts.explain || {};
      VX.shell.openDrawer(opts.title || 'Graphique', `
        <h3 class="vx-mb2">Ce que montre le graphique</h3><p class="vx-dim">${ex.shows || opts.question || '—'}</p>
        <h3 class="vx-mt4 vx-mb2">Pourquoi cela compte</h3><p class="vx-dim">${ex.why || '—'}</p>
        <h3 class="vx-mt4 vx-mb2">Ce qui confirmerait</h3><p class="vx-dim">${ex.confirm || '—'}</p>
        <h3 class="vx-mt4 vx-mb2">Ce qui invaliderait</h3><p class="vx-dim">${ex.invalidate || '—'}</p>
        <div class="vx-divider"></div>
        <div class="vx-meta">Source : ${opts.source || 'n/d'} · ${VX.fmt.ago(opts.timestamp)}${opts.unit ? ' · unité ' + opts.unit : ''}${(opts.period || opts.timeframe) ? ' · ' + (opts.period || opts.timeframe) : ''}${opts.limits ? ' · ' + opts.limits : ''}</div>`);
    });
    /* Plein écran / mode focus (§35) : la carte occupe le viewport, le graphique
       se redimensionne (Chart.js maintainAspectRatio:false). Échap ou clic ferme. */
    el.querySelector('.vx-chart-fs')?.addEventListener('click', () => C.toggleFullscreen(el, chart));
    /* Vue tableau (§8) : les données RÉELLES du graphique en table, depuis
       chart.data — aucune valeur inventée, exactement ce qui est tracé. */
    el.querySelector('.vx-chart-tbl')?.addEventListener('click', () => C.showDataTable(opts.title, chart));
    return chart;
  };

  /* Bascule plein écran d'une carte graphique. */
  C.toggleFullscreen = function (el, chart) {
    const on = el.classList.toggle('vx-chart-fs');
    document.body.classList.toggle('vx-fs-open', on);
    let bd = document.getElementById('vx-chart-fs-backdrop');
    if (on && !bd) {
      bd = document.createElement('div'); bd.id = 'vx-chart-fs-backdrop';
      bd.addEventListener('click', () => C.toggleFullscreen(el, chart));
      document.body.appendChild(bd);
    }
    if (bd) bd.style.display = on ? 'block' : 'none';
    const esc = (e) => { if (e.key === 'Escape') { C.toggleFullscreen(el, chart); document.removeEventListener('keydown', esc); } };
    if (on) document.addEventListener('keydown', esc);
    if (chart && chart.resize) setTimeout(() => { try { chart.resize(); } catch (e) {} }, 60);
  };

  /* Construit une table HTML à partir des données réellement tracées. */
  C.showDataTable = function (title, chart) {
    if (!chart || !chart.data) { VX.toast && VX.toast('Aucune donnée tabulable', 'warning'); return; }
    const labels = chart.data.labels || [];
    const ds = chart.data.datasets || [];
    const fmt = (v) => (v == null || v === '') ? '—'
      : (typeof v === 'object' ? (v.y != null ? VX.fmt.num(v.y, 2) : (v.x != null ? VX.fmt.num(v.x, 2) : '—')) : (isNaN(v) ? String(v) : VX.fmt.num(+v, 2)));
    const n = Math.max(labels.length, ...ds.map(d => (d.data || []).length));
    let head = '<th>#</th>' + ds.map(d => `<th class="vx-num">${(d.label || 'série')}</th>`).join('');
    let body = '';
    for (let i = 0; i < n; i++) {
      body += `<tr><td class="vx-mono">${labels[i] != null ? labels[i] : (i + 1)}</td>`
        + ds.map(d => `<td class="vx-num vx-mono">${fmt((d.data || [])[i])}</td>`).join('') + '</tr>';
    }
    VX.shell.openDrawer((title || 'Graphique') + ' — données',
      `<div class="vx-table-wrap" style="max-height:70vh"><table class="vx-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>
       <div class="vx-meta vx-mt2">${n} point(s) — valeurs réellement tracées, aucune estimation.</div>`);
  };

  /* ── Primitives réutilisées par tous les modules ─────────────────── */
  C.sparkline = function (canvas, values, { color, positiveIsGood = true } = {}) {
    if (!canvas || !values || values.length < 2) return null;
    const up = values[values.length - 1] >= values[0];
    const col = color || (up === positiveIsGood ? C.colors.positive : C.colors.negative);
    return C.mount(canvas, {
      type: 'line',
      data: { labels: values.map((_, i) => i), datasets: [{ data: values, borderColor: col, borderWidth: 1.4, pointRadius: 0, fill: false, tension: .3 }] },
      options: { scales: { x: { display: false }, y: { display: false } }, plugins: { tooltip: { enabled: false } }, events: [] },
    });
  };
  C.area = function (canvas, labels, values, { color = C.colors.blue, yFmt, fill = true, extraDatasets = [] } = {}) {
    return C.mount(canvas, {
      type: 'line',
      data: { labels, datasets: [{ data: values, borderColor: color, borderWidth: 2.1, pointRadius: 0, tension: .25, fill,
        backgroundColor: (ctx) => {
          const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height || 200);
          g.addColorStop(0, color + '52'); g.addColorStop(.5, color + '1F'); g.addColorStop(1, color + '00'); return g;
        } }, ...extraDatasets] },
      options: { scales: C.axes({ yFmt }), interaction: { mode: 'index', intersect: false } },
    });
  };
  C.bars = function (canvas, labels, values, { colors, horizontal = false, yFmt } = {}) {
    const cols = colors || values.map(v => v >= 0 ? C.colors.positive : C.colors.negative);
    /* Horizontal : les CATÉGORIES vivent sur l'axe y — yFmt ne s'applique qu'aux
       VALEURS (axe x), sinon les noms disparaissent au profit de ticks formatés. */
    const scales = horizontal
      ? { x: { grid: { color: C.colors.grid }, ticks: { maxTicksLimit: 6, callback: yFmt || undefined } },
          y: { grid: { display: false }, ticks: { autoSkip: false } } }
      : C.axes({ yFmt });
    return C.mount(canvas, {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: cols, borderRadius: C.barRadius, maxBarThickness: 26 }] },
      options: { indexAxis: horizontal ? 'y' : 'x', scales },
    });
  };
  C.donut = function (canvas, labels, values, { colors } = {}) {
    /* §33 : un donut ≤ ~5 catégories */
    const l = labels.slice(0, 5), v = values.slice(0, 5);
    return C.mount(canvas, {
      type: 'doughnut',
      /* Donut « verre » : segments détachés (spacing) + bouts arrondis (borderRadius)
         + léger décalage au survol → rendu glossy, réf. visuelle. */
      data: { labels: l, datasets: [{ data: v, backgroundColor: colors || C.colors.series, borderWidth: 0, borderRadius: 5, spacing: 2, hoverOffset: 6 }] },
      options: { cutout: '70%', plugins: { legend: { display: true, position: 'right', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, font: { size: 10 } } } } },
    });
  };
  C.multiLine = function (canvas, labels, datasets, { yFmt } = {}) {
    return C.mount(canvas, {
      type: 'line',
      data: { labels, datasets: datasets.map((d, i) => Object.assign({ borderColor: C.colors.series[i % 6], borderWidth: 1.5, pointRadius: 0, tension: .25, fill: false }, d)) },
      options: { scales: C.axes({ yFmt }), interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } } },
    });
  };
  /* Annotations de niveaux (entrée/stop/TP…) — plugin ligne horizontale. */
  C.levelLines = function (levels) {
    /* levels: [{value,label,kind:'entry'|'stop'|'tp'|'support'|'resistance'}] */
    const colByKind = { entry: C.colors.info, stop: C.colors.negative, tp: C.colors.positive,
      // Un support n'est ni positif ni analytique : c'est un NIVEAU.
      // Il se lit en argent ; la prudence reste réservée à la résistance.
      support: C.colors.brand, resistance: C.colors.warning };
    return {
      id: 'vxLevels',
      afterDatasetsDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        if (!scales.y) return;
        (levels || []).forEach(lv => {
          if (lv.value === null || lv.value === undefined) return;
          const y = scales.y.getPixelForValue(lv.value);
          if (y < chartArea.top || y > chartArea.bottom) return;
          ctx.save();
          ctx.strokeStyle = colByKind[lv.kind] || C.colors.muted;
          ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(chartArea.left, y); ctx.lineTo(chartArea.right, y); ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = colByKind[lv.kind] || C.colors.muted;
          ctx.font = '10px ' + (Chart.defaults.font.family || 'monospace');
          ctx.fillText(`${lv.label || lv.kind} ${VX.fmt.price(lv.value)}`, chartArea.left + 4, y - 3);
          ctx.restore();
        });
      },
    };
  };
  /* ── Jauge radiale (SVG, sans Chart.js) — régime, risk score, VIX, options env ──
     opts: {value, min=0, max=100, unit, label, reading,
            bands:[{to, color}], // zones colorées de gauche→droite (ordre croissant)
            positiveIsLow=false} // n/u : la couleur vient des bandes
     Accessible : role=img + aria-label chiffré. Aucune animation permanente. */
  C.gauge = function (host, opts) {
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    const o = opts || {};
    const min = o.min != null ? o.min : 0, max = o.max != null ? o.max : 100;
    const v = (o.value == null || isNaN(o.value)) ? null : Math.max(min, Math.min(max, o.value));
    const W = 200, H = 118, cx = 100, cy = 104, r = 84;
    const ang = (t) => Math.PI * (1 - (Math.max(min, Math.min(max, t)) - min) / (max - min)); // 180°→0°
    const pt = (a, rr = r) => [cx + rr * Math.cos(a), cy - rr * Math.sin(a)];
    const arc = (a0, a1, rr = r) => {
      const [x0, y0] = pt(a0, rr), [x1, y1] = pt(a1, rr);
      const large = Math.abs(a0 - a1) > Math.PI ? 1 : 0;
      return `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${rr} ${rr} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
    };
    const bands = o.bands && o.bands.length ? o.bands : [{ to: max, color: C.colors.neutral }];
    // pistes de fond colorées par bande (contexte), puis arc de valeur par-dessus
    let track = '', prev = min;
    bands.forEach(b => {
      track += `<path d="${arc(ang(prev), ang(b.to))}" stroke="${b.color}" stroke-opacity=".22" stroke-width="9" fill="none" stroke-linecap="round"/>`;
      prev = b.to;
    });
    let valArc = '', needle = '', valColor = C.colors.neutral;
    if (v != null) {
      for (const b of bands) { if (v <= b.to) { valColor = b.color; break; } valColor = b.color; }
      /* Aucun halo permanent (design system) : l'arc porte sa couleur, pas une lueur. */
      valArc = `<path d="${arc(ang(min), ang(v))}" stroke="${valColor}" stroke-width="9" fill="none" stroke-linecap="round"/>`;
      const [nx, ny] = pt(ang(v), r);
      // Bille lumineuse blanche (réf. visuelle) : halo teinté → bille blanche → cœur teinté
      needle = `<circle cx="${nx.toFixed(1)}" cy="${ny.toFixed(1)}" r="9" fill="${valColor}" opacity=".16"/>`
        + `<circle cx="${nx.toFixed(1)}" cy="${ny.toFixed(1)}" r="5.2" fill="var(--vx-ink,#f5f7fa)"/>`
        + `<circle cx="${nx.toFixed(1)}" cy="${ny.toFixed(1)}" r="2.3" fill="${valColor}"/>`;
    }
    const disp = v == null ? '—' : (Number.isInteger(v) ? v : (+v).toFixed(1));
    const aria = `${o.label || 'jauge'} : ${v == null ? 'donnée indisponible' : disp + (o.unit || '')}${o.reading ? ' — ' + o.reading : ''}`;
    /*  L'unite est DEJA peinte sous le cadran : la repasser au pied donnerait
        « % · confiance » puis « unité : % » a deux centimetres d'ecart, le
        doublon que `piedPrimitive` evite deja pour la source.  */
    const tete = tetePrimitive(o), pied = piedPrimitive(Object.assign({}, o, { unit: null }));
    _libereHauteur(el, tete, pied);
    el.innerHTML = tete + `
      <div class="vx-gauge" role="img" aria-label="${aria.replace(/"/g, '&quot;')}">
        <svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:230px;display:block;margin:0 auto">
          ${track}${valArc}${needle}
          <text x="${cx}" y="${cy - 20}" text-anchor="middle" fill="${valColor}" font-size="30" font-weight="700" style="font-variant-numeric:tabular-nums">${disp}</text>
          <text x="${cx}" y="${cy - 3}" text-anchor="middle" fill="var(--vx-text-muted,#828892)" font-size="10" letter-spacing=".5">${(o.unit || '') + (o.label ? ' · ' + o.label : '')}</text>
        </svg>
        ${o.reading ? `<div class="vx-meta" style="text-align:center;margin-top:4px">${o.reading}</div>` : ''}
      </div>` + pied;
    return el;
  };


  /* ── PIED DE PRIMITIVE ────────────────────────────────────────────────
     `treemap` et `waterfall` rendent un SVG NU : contrairement a `C.card`,
     ils n'ont jamais porte ni unite, ni source, ni horodatage. Le contrat
     des graphiques (« question, conclusion, source, unite, periode ») ne
     pouvait donc pas etre tenu la ou ils servent — et les options qu'on leur
     passait etaient silencieusement ignorees.

     Ce pied les rend effectives. Il ne s'affiche que si on lui donne quelque
     chose : une primitive sans legende reste exactement ce qu'elle etait. */
  /* La QUESTION se lit AVANT le graphique — c'est elle qui dit pourquoi on le
     regarde. Les primitives nues n'en portaient aucune. */
  function tetePrimitive(o) {
    return o.question
      ? '<p class="vx-chart-question vx-primitive-question">' + o.question + '</p>' : '';
  }

  function piedPrimitive(o) {
    const age = (o.timestamp != null && window.VX && VX.updateIndicator)
      ? VX.updateIndicator(o.timestamp, o.source || '', o.mode) : '';
    const bouts = [];
    if (o.unit) bouts.push('unité : ' + o.unit);
    /*  `updateIndicator` NOMME deja la source. La repeter donnait
        « · portfolio_context Différé · source : portfolio_context » — deux
        fois la meme origine a trois centimetres d'ecart.  */
    if (o.source && !age) bouts.push('source : ' + o.source);
    if (o.period || o.timeframe) bouts.push(o.period || o.timeframe);
    if (o.limits) bouts.push(o.limits);
    if (!bouts.length && !age) return '';
    return '<div class="vx-chart-foot vx-primitive-foot">'
      + age + (bouts.length ? '<span class="vx-meta">' + bouts.join(' · ') + '</span>' : '')
      + '</div>';
  }

  /*  Le meme pied pose dans un hote FIGE (`style="height:260px"`, dimensionne
      pour le SVG seul) saigne sur le bloc suivant : c'est la mesure du lot 33
      sur le treemap (294 px de contenu dans 260 px). `treemap` et `waterfall`
      liberent donc la hauteur ; les cinq primitives qui recoivent tete et pied
      ici doivent la liberer AUSSI, sinon on deplace le defaut au lieu de le
      corriger. On ne libere QUE si on ajoute quelque chose : une primitive
      appelee sans legende garde exactement la boite qu'elle avait.  */
  function _libereHauteur(el, tete, pied) {
    if ((tete || pied) && el.style.height) el.style.height = '';
  }

  /* ── Treemap (SVG squarifié) — poids relatif : portefeuille, segments, secteurs ──
     opts: {items:[{label, value>0, color?, sub?}], width, height, fmt?, emptyHtml?}
     Aspect ratios équilibrés (algorithme squarify). Accessible : chaque tuile role=img. */
  C.treemap = function (host, opts) {
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    const o = opts || {};
    let items = (o.items || []).filter(d => d && d.value > 0).sort((a, b) => b.value - a.value);
    if (!items.length) { el.innerHTML = o.emptyHtml || ''; return null; }
    /* L'hote est souvent dimensionne pour le SVG seul (height:260px inline) ;
       la tete et le pied vivent DEDANS — un height fige ferait saigner le
       pied sur le bloc suivant (mesure : Composition du capital sous la
       legende du treemap). On libere la hauteur : le conteneur suit son
       contenu, le SVG garde sa hauteur de conception en pixels. */
    if (el.style.height) { el.style.height = ''; }
    const W = o.width || 640, H = o.height || 300;
    const total = items.reduce((s, d) => s + d.value, 0);
    const nodes = items.map(d => ({ d, area: d.value / total * W * H }));
    const rects = [];
    let fx = 0, fy = 0, fw = W, fh = H;
    const worst = (row, len) => {
      let sum = 0, mx = 0, mn = Infinity;
      row.forEach(r => { sum += r.area; if (r.area > mx) mx = r.area; if (r.area < mn) mn = r.area; });
      const s2 = sum * sum, l2 = len * len;
      return Math.max(l2 * mx / s2, s2 / (l2 * mn));
    };
    const layout = (row) => {
      const sum = row.reduce((a, r) => a + r.area, 0);
      if (fw >= fh) {                       // bande verticale à gauche (largeur rw)
        const rw = sum / fh; let oy = fy;
        row.forEach(r => { const rh = r.area / rw; rects.push({ d: r.d, x: fx, y: oy, w: rw, h: rh }); oy += rh; });
        fx += rw; fw -= rw;
      } else {                              // bande horizontale en haut (hauteur rh)
        const rh = sum / fw; let ox = fx;
        row.forEach(r => { const rw = r.area / rh; rects.push({ d: r.d, x: ox, y: fy, w: rw, h: rh }); ox += rw; });
        fy += rh; fh -= rh;
      }
    };
    let rest = nodes.slice(), row = [];
    while (rest.length) {
      const len = Math.min(fw, fh), next = rest[0];
      if (row.length === 0 || worst(row.concat(next), len) <= worst(row, len)) row.push(rest.shift());
      else { layout(row); row = []; }
    }
    if (row.length) layout(row);
    const fmt = o.fmt || ((v) => v);
    const svg = rects.map(r => {
      const col = r.d.color || C.colors.neutral;
      const small = r.w < 54 || r.h < 30;
      const lbl = String(r.d.label || '');
      const aria = `${lbl} : ${fmt(r.d.value)}${r.d.sub ? ' ' + r.d.sub : ''}`;
      return `<g role="img" aria-label="${aria.replace(/"/g, '&quot;')}">
        <rect x="${r.x.toFixed(1)}" y="${r.y.toFixed(1)}" width="${Math.max(0, r.w - 1.5).toFixed(1)}" height="${Math.max(0, r.h - 1.5).toFixed(1)}"
          rx="3" fill="${col}" fill-opacity=".82" stroke="var(--vx-bg-app,#050505)" stroke-width="1.5"/>
        ${small ? '' : `<text x="${(r.x + 6).toFixed(1)}" y="${(r.y + 16).toFixed(1)}" fill="#f3f1ed" font-size="11" font-weight="700">${lbl.slice(0, Math.floor(r.w / 7))}</text>
        <text x="${(r.x + 6).toFixed(1)}" y="${(r.y + 30).toFixed(1)}" fill="rgba(255,255,255,.82)" font-size="10" style="font-variant-numeric:tabular-nums">${fmt(r.d.value)}${r.d.sub ? ' · ' + r.d.sub : ''}</text>`}
      </g>`;
    }).join('');
    el.innerHTML = tetePrimitive(o)
      + `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none" style="display:block">${svg}</svg>`
      + piedPrimitive(o);
    return el;
  };

  /* ── Waterfall (SVG) — décomposition/contribution : P&L, risque, santé, décision ──
     opts: {items:[{label, value, isTotal?}], fmt?, ariaLabel, width, height, emptyHtml}
     Contributions cumulatives (vert +, rouge −) ; isTotal = barre depuis 0 (brand).
     Accessible : role=img + résumé. */
  C.waterfall = function (host, opts) {
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    const o = opts || {};
    const items = (o.items || []).filter(it => it && it.value != null && !isNaN(it.value));
    if (!items.length) { el.innerHTML = o.emptyHtml || ''; return null; }
    if (el.style.height) { el.style.height = ''; }   /* meme regle que treemap */
    const W = o.width || 620, H = o.height || 240, PAD_B = 30, PAD_T = 16;
    let cum = 0; const bars = [];
    items.forEach(it => {
      if (it.isTotal) { bars.push({ label: it.label, from: 0, to: it.value, val: it.value, total: true }); }
      else { const from = cum; cum += it.value; bars.push({ label: it.label, from, to: cum, val: it.value }); }
    });
    const vals = bars.reduce((a, b) => a.concat([b.from, b.to]), [0]);
    const maxV = Math.max.apply(null, vals), minV = Math.min.apply(null, vals);
    const range = (maxV - minV) || 1, plotH = H - PAD_B - PAD_T;
    const y = (v) => PAD_T + (maxV - v) / range * plotH;
    const n = bars.length, gap = 10, bw = Math.max(6, (W - gap * (n + 1)) / n);
    const fmt = o.fmt || ((v) => Math.round(v));
    let svg = '';
    bars.forEach((b, i) => {
      const x = gap + i * (bw + gap);
      const yTop = y(Math.max(b.from, b.to)), yBot = y(Math.min(b.from, b.to));
      const h = Math.max(2, yBot - yTop);
      const col = b.total ? C.colors.brand : (b.val >= 0 ? C.colors.positive : C.colors.negative);
      svg += `<rect x="${x.toFixed(1)}" y="${yTop.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${col}" fill-opacity=".85" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))"/>`;
      if (i < bars.length - 1 && !bars[i + 1].total) {
        const yc = y(b.to), xn = gap + (i + 1) * (bw + gap);
        svg += `<line x1="${(x + bw).toFixed(1)}" y1="${yc.toFixed(1)}" x2="${xn.toFixed(1)}" y2="${yc.toFixed(1)}" stroke="rgba(255,255,255,.18)" stroke-dasharray="2,2"/>`;
      }
      svg += `<text x="${(x + bw / 2).toFixed(1)}" y="${(yTop - 4).toFixed(1)}" text-anchor="middle" font-size="10" fill="var(--vx-text-secondary,#b7b2aa)" style="font-variant-numeric:tabular-nums">${(b.val >= 0 && !b.total ? '+' : '') + fmt(b.val)}</text>`;
      svg += `<text x="${(x + bw / 2).toFixed(1)}" y="${(H - 9).toFixed(1)}" text-anchor="middle" font-size="9" fill="var(--vx-text-muted,#817d77)">${String(b.label).slice(0, Math.floor(bw / 6) + 2)}</text>`;
    });
    const aria = (o.ariaLabel || 'décomposition') + ' : ' + bars.map(b => b.label + ' ' + fmt(b.val)).join(', ');
    el.innerHTML = tetePrimitive(o)
      + `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${aria.replace(/"/g, '&quot;')}">${svg}</svg>`
      + piedPrimitive(o);
    return el;
  };

  /* ── Radar (SVG polygonal) — scorecard, greeks, risques d'entreprise ──
     opts: {axes:[{label, value}], max=100, color, ariaLabel, width, height, emptyHtml}
     ≥3 axes requis. Accessible : role=img + résumé chiffré. */
  C.radar = function (host, opts) {
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    const o = opts || {};
    /*  Un axe SANS valeur n'est pas un axe A ZERO.
        Mesure du 06/09/2026, fichier servi par 127.0.0.1:5003, appel
        `C.radar(h,{axes:[{label:'Alpha'},{label:'Beta',value:null},
        {label:'Gamma',value:50}]})` :
          aria-label rendu   → « radar : Alpha 0, Beta 0, Gamma 50 »
          sommets du polygone → « 130.0,120.0 130.0,120.0 89.3,143.5 »
        soit deux sommets confondus EXACTEMENT au centre (130,120) du cadre
        260x240 — la lecture « note nulle », alors que la mesure dit « pas de
        note ». Le coupable est `clamp(v) = (v || 0) / max`, qui imputait un
        zero a `null`, `undefined` et `''` (invariant 4 : absence et zero
        restent des etats distincts).
        Les axes sans valeur finie sortent donc du trace — la meme regle que
        `rings`, `funnel`, `waterfall` et `treemap`, qui filtrent deja — et
        ils sont NOMMES sous le graphique : un axe retire en silence ferait
        croire que la scorecard n'a jamais eu cette dimension.  */
    const _fini = (v) => v !== null && v !== undefined && v !== ''
      && isFinite(Number(v));
    const tous = (o.axes || []).filter(a => a && a.label != null);
    const axes = tous.filter(a => _fini(a.value));
    const absents = tous.filter(a => !_fini(a.value)).map(a => String(a.label));
    /*  Moins de trois axes mesures : un polygone n'a pas de forme, on ne le
        trace pas. Mais rendre le vide ferait DEUX pertes que le filtre
        ci-dessus etait cense empecher.
        Mesure du 06/09/2026, `C.radar(h,{axes:[{label:'Alpha'},{label:'Beta'},
        {label:'Gam'},{label:'Del',value:30},{label:'Eps',value:10}]})` :
          avant le filtre → radar complet, aria « Alpha 0, Beta 0, Gam 0,
                            Del 30, Eps 10 » (trois zeros imputes : faux)
          apres le filtre → `innerHTML` de 0 caractere
        soit une carte BLANCHE : les deux valeurs REELLEMENT mesurees (30 et
        10) sont jetees, et les trois absences ne sont nommees nulle part —
        exactement le « retire en silence » que ce lot dit corriger, pousse
        de l'axe a la carte entiere (invariants 4 et 6).
        Aucune page n'atteint ce chemin aujourd'hui, parce que `analysis_page`
        et `intelligence_page` imputent leurs zeros EN AMONT (`a[1]||0`,
        `s.conviction??0`). Le jour ou ces imputations tombent — c'est le
        correctif que ce lot recommande — ce chemin devient le cas courant
        d'une scorecard partielle. */
    if (axes.length < 3) {
      const secours =
        (axes.length ? '<p class="vx-meta">' + axes.map(a =>
            a.label + ' : ' + Math.round(Number(a.value))).join(' · ') + '</p>' : '')
        + (absents.length ? '<p class="vx-meta vx-primitive-absents">Sans donnée : '
            + absents.join(', ') + '</p>' : '');
      _libereHauteur(el, '', secours);
      el.innerHTML = (o.emptyHtml || '') + secours;
      return null;
    }
    const max = o.max || 100, N = axes.length, W = o.width || 260, H = o.height || 240;
    /*  Le cadre ne reservait aucune place aux LIBELLES d'axes : ancres posees
        a `R + 13` du centre, texte etale vers l'exterieur, `viewBox` arrete a
        `W`. Mesure du 06/09/2026 sur /system/design-system (viewBox 0 0 260
        240, cinq axes) via `getBBox()` :
          « Tendance »  → x va jusqu'a 274.2 pour un cadre de 260 (14.2 coupes)
          « Volatilite » → x commence a -10.5 (10.5 coupes)
        A l'ecran : « Tendar » et « latilite ». Le libelle est la SEULE chose
        qui nomme la dimension notee — coupe, la note ne veut plus rien dire,
        et le defaut touche la scorecard d'Analyse, les Scores du dossier de
        Vertex IA et les Greeks d'Options.
        On elargit donc le cadre horizontalement, sans toucher au rayon.

        La marge est le DEBORDEMENT REELLEMENT MESURE, axe par axe, dans la
        geometrie du rendu — pas la longueur du plus long libelle. La nuance
        n'est pas cosmetique : le `viewBox` s'etire, mais le SVG est servi en
        `width:100%`, donc dans une carte plus etroite que `VW` c'est TOUT le
        dessin qui rapetisse, libelles compris.
        Mesure du 06/09/2026, cinq axes « Momentum / Tendance / Qualite /
        Valorisation / Volatilite », cadre 260x240 :
          debordement reel      → 43,8 px (« Volatilite », ancre a gauche)
          marge par plus-long-libelle → 85 px, soit 2,2x le besoin
          `viewBox` qui en resulte    → 430 au lieu de 352
        et sur /system/design-system a 390 px, ou la carte rend 298 px de
        large, la fonte des libelles tombait a 6,58 px (9,5 px avant le lot).
        Le libelle cessait d'etre coupe pour devenir illisible : on deplacait
        le defaut. Avec la marge geometrique, la meme carte rend 8,04 px.

        La largeur d'un libelle reste une ESTIMATION — on ne peut pas mesurer
        un texte qui n'est pas encore dans le DOM. La constante est le pire
        cas MESURE sur les libellés du produit et leurs variantes majuscules
        (« MOMENTUM » : 57,63 px de boite pour 8 signes a 9,5 px de fonte,
        soit 7,2 px/signe ; « Volatilite » n'en fait que 3,47). L'ancienne
        constante de 6,4 passait donc SOUS le pire cas majuscule qu'elle
        pretendait couvrir. Bornee a 90 px : un libelle aberrant ne doit pas
        faire exploser la carte — il sera coupe, et c'est dit ici. */
    const PXSIGNE = 7.2;
    const _angPad = (i) => -Math.PI / 2 + i * 2 * Math.PI / axes.length;
    let _deb = 0;
    axes.forEach((a, i) => {
      const lx = W / 2 + (Math.min(W, H) / 2 - 26 + 13) * Math.cos(_angPad(i));
      const lw = PXSIGNE * String(a.label).length;
      //  Meme regle d'ancrage que la boucle des libelles, plus bas : le
      //  decalage du centre par PADX est commun aux deux, donc invariant.
      const x0 = Math.abs(lx - W / 2) < 6 ? lx - lw / 2 : (lx > W / 2 ? lx : lx - lw);
      _deb = Math.max(_deb, -x0, x0 + lw - W);
    });
    const PADX = Math.max(0, Math.min(90, Math.ceil(_deb) + 2));
    const VW = W + 2 * PADX;
    const cx = VW / 2, cy = H / 2, R = Math.min(W, H) / 2 - 26;
    const ang = (i) => -Math.PI / 2 + i * 2 * Math.PI / N;
    const pt = (i, r) => [cx + r * Math.cos(ang(i)), cy + r * Math.sin(ang(i))];
    let grid = '';
    [0.25, 0.5, 0.75, 1].forEach(f => {
      grid += `<polygon points="${axes.map((_, i) => pt(i, R * f).map(n => n.toFixed(1)).join(',')).join(' ')}" fill="none" stroke="rgba(255,255,255,.06)" stroke-width="1"/>`;
    });
    let spokes = '', labels = '';
    axes.forEach((a, i) => {
      const [ex, ey] = pt(i, R);
      spokes += `<line x1="${cx}" y1="${cy}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" stroke="rgba(255,255,255,.06)"/>`;
      const [lx, ly] = pt(i, R + 13);
      const anchor = Math.abs(lx - cx) < 6 ? 'middle' : (lx > cx ? 'start' : 'end');
      labels += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="middle" font-size="9.5" fill="var(--vx-text-muted,#817d77)">${a.label}</text>`;
    });
    const clamp = (v) => Math.max(0, Math.min(1, Number(v) / max));
    const vpts = axes.map((a, i) => pt(i, R * clamp(a.value)).map(n => n.toFixed(1)).join(',')).join(' ');
    const col = o.color || C.colors.brand;
    const dots = axes.map((a, i) => { const [px, py] = pt(i, R * clamp(a.value)); return `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="2.6" fill="${col}"/>`; }).join('');
    const aria = (o.ariaLabel || 'radar') + ' : ' + axes.map(a => a.label + ' ' + Math.round(Number(a.value))).join(', ')
      + (absents.length ? ' — sans donnée : ' + absents.join(', ') : '');
    /*  L'absence est ecrite A L'ECRAN, pas seulement dans l'aria-label : un
        lecteur voyant qui compte cinq dimensions attendues et quatre branches
        tracees doit lire POURQUOI, sans ouvrir l'inspecteur.  */
    const note = absents.length
      ? '<p class="vx-meta vx-primitive-absents">Sans donnée : ' + absents.join(', ') + '</p>' : '';
    const tete = tetePrimitive(o), pied = piedPrimitive(o);
    _libereHauteur(el, tete, pied || note);
    el.innerHTML = tete + `<svg viewBox="0 0 ${VW} ${H}" width="100%" style="max-width:${VW}px;display:block;margin:0 auto" role="img" aria-label="${aria.replace(/"/g, '&quot;')}">
      ${grid}${spokes}<polygon points="${vpts}" fill="${col}" fill-opacity=".20" stroke="${col}" stroke-width="1.8" style="filter:drop-shadow(0 0 4px ${col})"/>${dots}${labels}</svg>` + note + pied;
    return el;
  };

  /* ── Flow diagram (chaîne de nœuds connectés) — impacts, pipeline système ──
     opts: {nodes:[{label, count?, sub?, tone?('active'|'idle'|'warn'|'err'), color?}], ariaLabel, emptyHtml}
     Horizontal, scrollable, responsive. Accessible : role=img + résumé. */
  C.flow = function (host, opts) {
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    const o = opts || {};
    const nodes = o.nodes || [];
    if (!nodes.length) { el.innerHTML = o.emptyHtml || ''; return null; }
    const toneCol = { active: C.colors.positive, idle: C.colors.neutral, warn: C.colors.warning, err: C.colors.negative };
    const aria = (o.ariaLabel || 'diagramme de flux') + ' : ' + nodes.map(n => n.label + (n.count != null ? ' ' + n.count : '')).join(' → ');
    const tete = tetePrimitive(o), pied = piedPrimitive(o);
    _libereHauteur(el, tete, pied);
    el.innerHTML = tete + '<div role="img" aria-label="' + aria.replace(/"/g, '&quot;') + '" style="display:flex;align-items:stretch;overflow-x:auto;padding:4px 0">'
      + nodes.map((n, i) => {
        const col = n.color || toneCol[n.tone] || C.colors.neutral;
        const active = n.tone === 'active' || (n.count > 0);
        const bg = active ? 'rgba(57,184,120,.09)' : 'var(--vx-surface-2,#111315)';
        const arrow = i < nodes.length - 1 ? '<span aria-hidden="true" style="align-self:center;color:var(--vx-text-muted,#817d77);padding:0 5px;font-size:13px">→</span>' : '';
        return '<div style="flex:0 0 auto;min-width:76px;text-align:center;padding:8px 10px;border-radius:9px;background:' + bg + ';border:1px solid ' + col + '55">'
          + '<div style="font-size:10.5px;color:var(--vx-text-secondary,#b7b2aa);text-transform:capitalize;white-space:nowrap">' + String(n.label) + '</div>'
          + (n.count != null ? '<div style="font-size:15px;font-weight:700;color:' + col + ';font-variant-numeric:tabular-nums">' + n.count + '</div>' : '')
          + (n.sub ? '<div style="font-size:9px;letter-spacing:.04em;text-transform:uppercase;color:var(--vx-text-muted,#817d77)">' + n.sub + '</div>' : '')
          + '</div>' + arrow;
      }).join('') + '</div>' + pied;
    return el;
  };

  /* ── Anneaux concentriques (multi-métriques en %) — composite, scorecard ──
     opts: {items:[{label, value, max?(=100), color?}], size?, centerLabel?, centerValue?, ariaLabel, emptyHtml}
     Jusqu'à 5 anneaux, extérieur → intérieur. SVG pur, accessible. */
  C.rings = function (host, opts) {
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    const o = opts || {};
    const items = (o.items || []).filter(d => d && d.value != null && !isNaN(d.value)).slice(0, 5);
    if (!items.length) { el.innerHTML = o.emptyHtml || ''; return null; }
    const S = o.size || 200, cx = S / 2, cy = S / 2;
    const gap = 4, sw = Math.max(6, (S / 2 - 24) / items.length - gap);
    const TAU = Math.PI * 2;
    let rings = '', legend = '';
    items.forEach((d, i) => {
      const r = (S / 2 - 10) - i * (sw + gap);
      const frac = Math.max(0, Math.min(1, (d.value || 0) / (d.max || 100)));
      const col = d.color || C.colors.series[i % C.colors.series.length];
      const circ = TAU * r;
      // piste + arc de valeur (départ à 12h, sens horaire)
      rings += `<circle cx="${cx}" cy="${cy}" r="${r.toFixed(1)}" fill="none" stroke="${col}" stroke-opacity=".16" stroke-width="${sw.toFixed(1)}"/>`;
      rings += `<circle cx="${cx}" cy="${cy}" r="${r.toFixed(1)}" fill="none" stroke="${col}" stroke-width="${sw.toFixed(1)}" stroke-linecap="round"
        stroke-dasharray="${(circ * frac).toFixed(1)} ${(circ * (1 - frac) + circ).toFixed(1)}"
        transform="rotate(-90 ${cx} ${cy})" style="filter:drop-shadow(0 0 3px ${col})"/>`;
      legend += `<div class="vx-flex" style="gap:6px;align-items:center;font-size:11px">
        <span style="width:9px;height:9px;border-radius:2px;background:${col};flex:0 0 auto"></span>
        <span class="vx-grow vx-truncate" style="color:var(--vx-text-secondary,#b7b2aa)">${String(d.label)}</span>
        <b class="vx-mono" style="color:${col}">${Number.isInteger(d.value) ? d.value : (+d.value).toFixed(1)}${o.unit || ' %'}</b></div>`;
    });
    const center = (o.centerValue != null)
      ? `<text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="26" font-weight="700" fill="var(--vx-text-primary,#f3f1ed)" style="font-variant-numeric:tabular-nums">${o.centerValue}</text>
         ${o.centerLabel ? `<text x="${cx}" y="${cy + 16}" text-anchor="middle" font-size="9.5" fill="var(--vx-text-muted,#817d77)">${o.centerLabel}</text>` : ''}`
      : '';
    const aria = (o.ariaLabel || 'anneaux') + ' : ' + items.map(d => d.label + ' ' + Math.round(d.value)).join(', ');
    /*  Comme la jauge : l'unite est deja collee a chaque valeur de la legende,
        elle ne repasse pas au pied.  */
    const tete = tetePrimitive(o), pied = piedPrimitive(Object.assign({}, o, { unit: null }));
    _libereHauteur(el, tete, pied);
    el.innerHTML = tete + `<div class="vx-flex vx-wrap" style="gap:14px;align-items:center;justify-content:center">
      <svg viewBox="0 0 ${S} ${S}" width="${S}" style="max-width:${S}px;flex:0 0 auto" role="img" aria-label="${aria.replace(/"/g, '&quot;')}">${rings}${center}</svg>
      <div style="flex:1;min-width:140px;display:flex;flex-direction:column;gap:6px">${legend}</div></div>` + pied;
    return el;
  };

  /* ── Entonnoir de conversion (étapes qui se resserrent) — pipeline de sélection ──
     opts: {stages:[{label, value, color?}], ariaLabel, fmt?, emptyHtml}
     Trapèzes centrés, largeur ∝ valeur, % de l'étape initiale affiché. */
  C.funnel = function (host, opts) {
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    const o = opts || {};
    const stages = (o.stages || []).filter(s => s && s.value != null && !isNaN(s.value));
    if (stages.length < 2) { el.innerHTML = o.emptyHtml || ''; return null; }
    const fmt = o.fmt || ((v) => v);
    const top = Math.max(...stages.map(s => s.value), 1);
    const W = o.width || 320, rowH = 34, gap = 6, H = stages.length * (rowH + gap);
    const cx = W / 2, minW = 26;
    let rows = '';
    stages.forEach((s, i) => {
      const w0 = minW + (W - minW) * (Math.max(0, s.value) / top);
      const next = stages[i + 1];
      const w1 = next ? minW + (W - minW) * (Math.max(0, next.value) / top) : w0 * 0.86;
      const y = i * (rowH + gap);
      const col = s.color || C.colors.series[i % C.colors.series.length];
      const pct = Math.round(s.value / top * 100);
      rows += `<polygon points="${(cx - w0 / 2).toFixed(1)},${y} ${(cx + w0 / 2).toFixed(1)},${y} ${(cx + w1 / 2).toFixed(1)},${y + rowH} ${(cx - w1 / 2).toFixed(1)},${y + rowH}"
        fill="${col}" fill-opacity=".86" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))"/>
        <line x1="${(cx - w0 / 2).toFixed(1)}" y1="${y + 0.5}" x2="${(cx + w0 / 2).toFixed(1)}" y2="${y + 0.5}" stroke="rgba(255,255,255,.20)" stroke-width="1"/>
        <text x="${cx}" y="${y + rowH / 2 - 1}" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="700" fill="#0b0b0c" style="font-variant-numeric:tabular-nums">${fmt(s.value)}</text>`;
      rows += `<text x="8" y="${y + rowH / 2}" dominant-baseline="middle" font-size="10.5" fill="var(--vx-text-secondary,#b7b2aa)">${String(s.label)}</text>
        <text x="${W - 6}" y="${y + rowH / 2}" text-anchor="end" dominant-baseline="middle" font-size="10" fill="var(--vx-text-muted,#817d77)" style="font-variant-numeric:tabular-nums">${pct}%</text>`;
    });
    const aria = (o.ariaLabel || 'entonnoir') + ' : ' + stages.map(s => s.label + ' ' + fmt(s.value)).join(' → ');
    /* max-width : évite que l'entonnoir ne s'étire grotesquement sur une carte
       large (le viewBox 320px scalé à 100% gonflait tout ×4). Centré. */
    const tete = tetePrimitive(o), pied = piedPrimitive(o);
    _libereHauteur(el, tete, pied);
    el.innerHTML = tete + `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;max-width:${o.maxWidth || 460}px;margin:0 auto" role="img" aria-label="${aria.replace(/"/g, '&quot;')}">${rows}</svg>` + pied;
    return el;
  };

  /* ── Barres-étincelles (mini bar chart pour tuiles KPI) ──
     C.sparkbars(hostOrEl, values[], {color?, height?, posNeg?}) */
  C.sparkbars = function (host, values, opts) {
    const el = typeof host === 'string' ? document.getElementById(host) : host;
    if (!el) return null;
    const o = opts || {}, v = (values || []).filter(x => x != null && !isNaN(x));
    if (v.length < 2) { el.innerHTML = ''; return null; }
    const H = o.height || 30, W = Math.max(40, v.length * 5), max = Math.max(...v.map(Math.abs), 1e-9);
    const bw = W / v.length * 0.7, gap = W / v.length * 0.3;
    const bars = v.map((x, i) => {
      const h = Math.max(1, Math.abs(x) / max * (H - 2));
      const col = o.posNeg ? (x >= 0 ? C.colors.positive : C.colors.negative) : (o.color || C.colors.brand);
      return `<rect x="${(i * (bw + gap)).toFixed(1)}" y="${(H - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="1" fill="${col}" opacity=".9"/>`;
    }).join('');
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none" style="display:block" aria-hidden="true">${bars}</svg>`;
    return el;
  };

  /* Marqueurs verticaux (earnings, événements). */
  C.eventMarkers = function (markers) {
    return {
      id: 'vxEvents',
      afterDatasetsDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        (markers || []).forEach(m => {
          const x = scales.x.getPixelForValue(m.index);
          if (!isFinite(x) || x < chartArea.left || x > chartArea.right) return;
          ctx.save();
          ctx.strokeStyle = C.colors.warning; ctx.setLineDash([2, 3]);
          ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
          ctx.fillStyle = C.colors.warning; ctx.font = C.labelFont(9);
          ctx.fillText(m.label || 'E', x + 2, chartArea.top + 9);
          ctx.restore();
        });
      },
    };
  };
})();
