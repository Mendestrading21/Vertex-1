/* options-scanner.js — SCANNER PAR UNIVERS (SKYLER LOT 8c).
   TACTICAL / SWING / LEAPS strictement séparés (mandat V2), hors-mandat
   ÉTIQUETÉ (jamais caché), probabilité de doublement ESTIMÉE affichée telle
   quelle (modèle non calibré — dit à l'écran). Lecture seule, aucun ordre. */
(function () {
  'use strict';
  var out = document.getElementById('vx-sc-out');
  if (!out) return;                      // actif uniquement sur la vue LEAPS
  var tabs = document.getElementById('vx-sc-tabs');
  var symIn = document.getElementById('vx-sc-sym');
  var go = document.getElementById('vx-sc-go');
  var universe = 'LEAPS';
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[<>&"']/g, function (c) {
      return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  /* Format fr-FR partagé (VX.fmt.num) : « 230,5 » et non « 230.5 » dans une table française. */
  var num = function (v, d) {
    if (v == null || isNaN(v)) return '—';
    return (window.VX && VX.fmt) ? VX.fmt.num(v, d == null ? 2 : d) : Number(v).toFixed(d == null ? 2 : d);
  };

  function mandateCell(c) {
    if (c.mandate == null) return '<span class="vx2-absent">—</span>';
    if (!c.hors_mandat) return '<span class="vx-badge" data-tone="pos">Conforme</span>';
    /* Les raisons viennent du moteur (`mandate_reasons`) quand il les donne ;
       elles se LISENT sous le badge, pas seulement au survol. */
    var why = Array.isArray(c.mandate_reasons) ? c.mandate_reasons.slice() : [];
    if (!why.length) {
      if (c.mandate.delta_ok === false) why.push('delta hors 0,70-0,90');
      if (c.mandate.oi_ok === false) why.push('OI insuffisant');
      if (c.mandate.spread_ok === false) why.push('spread trop large');
    }
    return '<span class="vx-badge" data-tone="neg">Hors mandat</span>'
      + (why.length ? '<span class="vx-meta" style="display:block;font-size:11px;white-space:normal;max-width:220px">' + esc(why.join(' · ')) + '</span>' : '');
  }

  function render(d) {
    if (!d || d.available === false) {
      out.innerHTML = '<div class="vx-empty">' + esc((d && d.reason) || 'Scan indisponible.') + '</div>';
      return;
    }
    var candidates = d.candidates || [];
    var rows = candidates.map(function (c, index) {
      return '<tr data-candidate="' + index + '" data-clickable tabindex="0">'
        + '<td data-label="Contrat"><span class="vx-table-primary"><strong>' + esc(c.sym) + '</strong>'
        + '<span>' + esc(c.type) + (c.exp ? ' · ' + esc(c.exp) : '') + '</span></span></td>'
        + '<td data-label="Strike" class="vx-num">' + num(c.strike, 1) + '</td>'
        + '<td data-label="DTE" class="vx-num">' + esc(c.dte) + '</td>'
        + '<td data-label="Delta" class="vx-num">' + num(c.delta, 2) + '</td>'
        + '<td data-label="IV" class="vx-num">' + (c.iv != null ? num(c.iv * 100, 1) + ' %' : '—') + '</td>'
        + '<td data-label="Qualité" class="vx-num">' + (c.quality != null ? c.quality : '—') + '</td>'
        + '<td data-label="Mandat">' + mandateCell(c) + '</td>'
        + '<td data-label="Détail"><span class="vx-row-open">Ouvrir</span></td>'
        + '</tr>';
    }).join('');
    out.innerHTML = '<div class="vx-meta vx-mb1">' + esc(d.universe) + ' · fenêtre ' + esc((d.window || []).join('-'))
      + ' DTE · ' + d.n + ' contrat(s)' + (d.demo ? ' · <span class="vx-badge" data-tone="neutral">DÉMO</span>' : '') + '</div>'
      + '<div class="vx-table-wrap"><table class="vx-table"><thead><tr>'
      + '<th>Contrat</th><th class="vx-num">Strike</th><th class="vx-num">DTE</th><th class="vx-num">Delta</th>'
      + '<th class="vx-num">IV</th><th class="vx-num">Qualité</th><th>Mandat</th><th><span class="vx2-sr-only">Détail</span></th>'
      + '</tr></thead><tbody>' + rows + '</tbody></table></div>'
      + '<div class="vx-meta" style="margin-top:.3rem">P(doubler) = P(valeur terminale ≥ 2× coût), '
      + 'modèle lognormal non calibré — estimation, pas une promesse · hors-mandat affiché, jamais filtré en silence.</div>';

    /* Action primaire du blueprint : « Simuler le contrat ». Le lien porte les
       parametres REELS du candidat (prime mid = cost/100, le cout est par
       contrat) — rien n'est invente : sans cout, pas de mid transmis et le
       simulateur refusera honnetement. */
    function simLink(c) {
      var mid = (c.cost != null && isFinite(c.cost)) ? (Number(c.cost) / 100) : null;
      var q = new URLSearchParams({ classe: 'option', sym: c.sym || '',
        right: (String(c.type || '').toUpperCase() === 'PUT') ? 'P' : 'C',
        strike: c.strike != null ? c.strike : '', dte: c.dte != null ? c.dte : '' });
      if (mid) q.set('mid', String(Math.round(mid * 100) / 100));
      return '<a class="vx-btn vx-btn-sm" href="/simulator?' + q.toString()
        + '">Simuler ce contrat \u2192</a>';
    }

    function openCandidate(index) {
      var c = candidates[index]; if (!c || !window.VX || !VX.shell) return;
      var dp = c.double_prob;
      /* Lignage du cours : le board ne porte pas de `spot`, le serveur replie
         sur le cours du scan (même source que /scenarios, /gex-radar, /chain).
         Ce cours n'est PAS horodaté sur la cotation du contrat — le dire, sinon
         le repli passerait pour une cotation du contrat. */
      var spotSrc = (c.spot_source === 'scan.detail.price')
        ? ' · cours du scan, pas de la cotation du contrat' : '';
      var probability = (dp && dp.available) ? num(dp.probability * 100, 1) + ' % · estimation' + spotSrc
        : ('non disponible' + (dp && dp.reason ? ' · ' + dp.reason : ''));
      var mandate = c.mandate == null ? 'non disponible' : (c.hors_mandat ? 'Hors mandat' : 'Conforme');
      var body = '<div class="vx-section-stack">'
        + '<div class="vx-data-ledger"><span>' + esc(c.type || 'Contrat') + '</span><span>' + esc(c.dte) + ' jours</span>'
        + '<span>Lecture seule</span></div>'
        + '<div class="vx-stats-row">'
        + '<div class="vx-stat"><span class="vx-stat-label">Strike</span><span class="vx-stat-value">' + num(c.strike, 1) + '</span></div>'
        + '<div class="vx-stat"><span class="vx-stat-label">Delta</span><span class="vx-stat-value">' + num(c.delta, 2) + '</span></div>'
        + '<div class="vx-stat"><span class="vx-stat-label">IV</span><span class="vx-stat-value">' + (c.iv != null ? num(c.iv * 100, 1) + ' %' : 'n/d') + '</span></div>'
        + '<div class="vx-stat"><span class="vx-stat-label">Qualité</span><span class="vx-stat-value">' + (c.quality != null ? c.quality : 'n/d') + '</span></div></div>'
        + '<div class="vx-card vx-card--compact"><div class="vx-card-header"><span class="vx-card-title">Liquidité et mandat</span></div>'
        + '<div class="vx-kv"><span>Open interest</span><b>' + (c.oi != null ? c.oi : 'n/d') + '</b></div>'
        + '<div class="vx-kv"><span>Spread</span><b>' + (c.spread_pct != null ? num(c.spread_pct, 1) + ' %' : 'n/d') + '</b></div>'
        + '<div class="vx-kv"><span>Mandat</span><b>' + mandate + '</b></div>'
        + '<div class="vx-kv"><span>Probabilité de doubler</span><b>' + probability + '</b></div></div>'
        + simLink(c)
        + '<p class="vx-meta">Modèle lognormal non calibré. Cette lecture ne déclenche aucun ordre.</p></div>';
      VX.shell.openDrawer((c.sym || 'Contrat') + ' · détail LEAPS', body, { variant: 'summary' });
    }
    out.querySelectorAll('[data-candidate]').forEach(function (row) {
      var open = function () { openCandidate(Number(row.getAttribute('data-candidate'))); };
      row.addEventListener('click', open);
      row.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
      });
    });
  }

  function run() {
    var sym = (symIn && symIn.value || '').trim().toUpperCase();
    out.innerHTML = '<div class="vx-empty">Scan ' + esc(universe) + '…</div>';
    VX.fetch('/api/options/scanner/' + encodeURIComponent(universe) + (sym ? ('?sym=' + encodeURIComponent(sym)) : ''),
             { ttl: 120000 })
      .then(render)
      .catch(function (e) { out.innerHTML = '<div class="vx-error-banner">Scanner injoignable : ' + esc(e.message) + '</div>'; });
  }

  if (tabs) {
    tabs.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-universe]');
      if (!b) return;
      universe = b.getAttribute('data-universe');
      Array.prototype.forEach.call(tabs.querySelectorAll('[data-universe]'), function (x) {
        x.classList.toggle('vx-btn-ghost', x !== b);
        x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
      });
      run();
    });
  }
  if (go) go.addEventListener('click', run);
  if (symIn) symIn.addEventListener('keydown', function (e) { if (e.key === 'Enter') run(); });
  run();
})();
