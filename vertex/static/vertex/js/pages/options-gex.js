/* options-gex.js — vue « Positionnement dealer (GEX) » de l'espace Options.
   Récupère /api/options/gex/<sym> (profil GEX + flux notable + thèse, données
   réelles du board) et rend : thèse (analyste), tuiles de synthèse, barres GEX
   par strike (SVG inline), flux notable. Honnête : vue fenêtrée signalée, « n/d »
   si donnée absente, jamais de chiffre inventé. Lecture seule, aucun ordre. */
(function () {
  'use strict';
  if (!document.getElementById('vx-gx-thesis')) return;   // pas sur cette vue
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[<>&"']/g, function (c) {
    return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var f = function (x, d) { return (typeof x === 'number' && isFinite(x)) ? x.toLocaleString('fr-FR', { maximumFractionDigits: d == null ? 2 : d }) : 'n/d'; };
  var money = function (x) {
    if (typeof x !== 'number' || !isFinite(x)) return 'n/d';
    var a = Math.abs(x), s = x < 0 ? '−' : '';
    /* Un seul formateur fr-FR : « 5,65 M$ », pas « 5.65 M$ » à côté de « 230,36 ». */
    if (a >= 1e9) return s + f(a / 1e9, 2) + ' Md$';
    if (a >= 1e6) return s + f(a / 1e6, 2) + ' M$';
    if (a >= 1e3) return s + f(a / 1e3, 1) + ' k$';
    return s + f(a, 0) + ' $';
  };

  function toneBias(b) { return b === 'haussier' ? 'pos' : b === 'baissier' ? 'neg' : 'neutral'; }

  function renderThesis(d) {
    var s = d.synthesis || {}, host = $('vx-gx-thesis');
    if (!host) return;
    if (s.empty) {
      host.innerHTML = '<section class="vx-card"><div class="vx-empty"><b>Aucune donnée</b><br>'
        + esc((s.reason || 'positionnement indisponible') + '.') + '</div></section>';
      return;
    }
    var demo = d.demo ? '<span class="vx-demo-tag">DÉMO</span> ' : '';
    var chips = [];
    (s.evidence || []).forEach(function (e) { chips.push('<li>' + esc(e) + '</li>'); });
    host.innerHTML =
      '<section class="vx-card" aria-label="Thèse positionnement">'
      + '<div class="vx-verdict">' + demo
      + '<div class="vx-flex" style="gap:.5rem;align-items:center;flex-wrap:wrap">'
      + '<span class="vx-badge" data-tone="' + toneBias(s.bias) + '">' + esc(s.headline || '—') + '</span>'
      + (s.earnings_risk ? '<span class="vx-badge" data-tone="neg">Risque événementiel : ' + esc(s.earnings_risk) + '</span>' : '')
      + '</div>'
      + '<p class="vx-lead">' + esc(s.narrative || '') + '</p>'
      + (chips.length ? '<ul class="vx-muted" style="margin:.4rem 0 .2rem;padding-left:1.1rem">' + chips.join('') + '</ul>' : '')
      + '<div class="vx-muted">Vue ' + esc(d.coverage || '') + ' · thèse déterministe · lecture seule — aucun ordre.</div>'
      + '</div></section>';
  }

  function tile(label, value, sub) {
    return '<div class="vx-stat"><span class="vx-stat-label">' + esc(label) + '</span>'
      + '<span class="vx-stat-value">' + value + '</span>'
      + (sub ? '<span class="vx-muted">' + esc(sub) + '</span>' : '') + '</div>';
  }

  function renderTiles(d) {
    var g = d.gex || {}, host = $('vx-gx-tiles');
    if (!host) return;
    if (g.empty) { host.innerHTML = ''; return; }
    var reg = g.regime === 'stabilisant' ? 'Stabilisant (pinning)'
      : g.regime === 'accelerateur' ? 'Accélérateur' : 'Neutre';
    host.innerHTML = '<section class="vx-card"><div class="vx-stats-row">'
      + tile('Spot', f(g.spot), null)
      + tile('Net GEX', money(g.net_gex_total), g.net_gex_total > 0 ? 'dealers longs gamma' : g.net_gex_total < 0 ? 'dealers courts gamma' : '')
      + tile('Régime', '<span class="vx-badge" data-tone="' + (g.net_gex_total > 0 ? 'pos' : g.net_gex_total < 0 ? 'neg' : 'neutral') + '">' + reg + '</span>', null)
      + tile('Bascule 0-γ', f(g.zero_gamma), 'zero-gamma flip')
      + tile('Mur call', f(g.call_wall), 'aimant haussier')
      + tile('Mur put', f(g.put_wall), 'support')
      + tile('Vanna nette', money(g.net_vanna_total), 'Δ$ pour +1 pt d’IV')
      + tile('Charm net', money(g.net_charm_total), 'Δ$ qui dérive par jour')
      + tile('Max pain', f(g.max_pain), 'aimant d’expiration (OI)')
      + tile('Skew IV', (typeof g.iv_skew_pts === 'number' ? (g.iv_skew_pts > 0 ? '+' : '') + f(g.iv_skew_pts, 1) + ' pts' : 'n/d'), g.iv_skew_pts > 0 ? 'prime de peur (puts chers)' : g.iv_skew_pts < 0 ? 'calls plus chers' : '')
      + '</div></section>';
  }

  /* GEX quotidien — barres net GEX par jour (journal réel, comme le « Daily GEX »). */
  function renderDaily(d) {
    var host = $('vx-gx-daily');
    if (!host) return;
    var h = d.history || [];
    if (h.length < 1) {
      host.innerHTML = '<div class="vx-empty">L’historique se construit à chaque analyse — reviens demain pour la tendance.</div>';
      return;
    }
    var W = 520, H = 190, pad = 26, n = h.length;
    var maxAbs = 1;
    h.forEach(function (e) { maxAbs = Math.max(maxAbs, Math.abs(e.net_gex || 0)); });
    var bw = Math.max(3, Math.min(26, (W - 2 * pad) / n - 3));
    var midY = H / 2;
    var pos = 'var(--vx-positive,#2BBE90)', neg = 'var(--vx-negative,#E9555F)';
    var svg = ['<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="Net GEX quotidien">'];
    svg.push('<line x1="' + pad + '" y1="' + midY + '" x2="' + (W - pad) + '" y2="' + midY + '" stroke="var(--vx-border,#30292B)"/>');
    h.forEach(function (e, i) {
      var x = pad + i * ((W - 2 * pad) / n);
      var v = e.net_gex || 0;
      var bh = Math.abs(v) / maxAbs * (H / 2 - 18);
      var y = v >= 0 ? midY - bh : midY;
      svg.push('<rect x="' + x + '" y="' + y + '" width="' + bw + '" height="' + Math.max(1, bh) + '" fill="' + (v >= 0 ? pos : neg) + '" opacity=".85"><title>' + esc(e.date) + ' : ' + money(v) + '</title></rect>');
    });
    var first = h[0], last = h[n - 1];
    svg.push('<text x="' + pad + '" y="' + (H - 4) + '" font-size="9.5" fill="var(--vx-text-muted,#989092)">' + esc(first.date) + '</text>');
    svg.push('<text x="' + (W - pad) + '" y="' + (H - 4) + '" font-size="9.5" text-anchor="end" fill="var(--vx-text-muted,#989092)">' + esc(last.date) + '</text>');
    svg.push('</svg>');
    var trend = (n >= 2 && last.net_gex != null && first.net_gex != null)
      ? (last.net_gex > first.net_gex ? 'Le gamma s’empile à la hausse sur la période.'
        : last.net_gex < first.net_gex ? 'Le gamma net se dégrade sur la période.' : 'Gamma net stable.')
      : 'Un seul point pour l’instant — la tendance viendra avec les prochains jours.';
    host.innerHTML = svg.join('')
      + '<div class="vx-muted" style="margin-top:.3rem">' + esc(trend) + ' ' + n + ' jour(s) journalisé(s) — points réels uniquement.</div>';
  }

  /* Radar de positionnement : tous les titres du board, classés par |net GEX|. */
  function loadRadar() {
    var host = $('vx-gx-radar');
    if (!host) return;
    VX.fetch('/api/options/gex-radar', { ttl: 120000 }).then(function (d) {
      if (d.empty || !(d.rows || []).length) {
        host.innerHTML = '<div class="vx-empty">' + esc((d.reason || 'radar indisponible') + '.') + '</div>';
        return;
      }
      /* LOT 134 : le net GEX n'est plus un chiffre nu — mini-barre SIGNEE de
         verre depuis l'axe zero (positif -> droite en positive, negatif ->
         gauche en negative ; degrade doux au zero -> dense a la valeur via
         color-mix sur tokens ; echelle relative au max du radar). L'oeil voit
         qui stabilise et qui accelere sans lire chaque nombre. */
      var maxG = 1;
      d.rows.forEach(function (r) { maxG = Math.max(maxG, Math.abs(r.net_gex || 0)); });
      function gexBar(v) {
        if (v == null || !isFinite(v)) return money(v);
        var neg = v < 0, w = Math.max(3, Math.abs(v) / maxG * 50);
        var tok = neg ? 'var(--vx-negative,#E9555F)' : 'var(--vx-positive,#2BBE90)';
        return '<span style="display:inline-flex;align-items:center;gap:6px;justify-content:flex-end">'
          + '<span style="width:76px;height:8px;background:var(--vx-surface-3,#121214);border-radius:3px;overflow:hidden;display:inline-block;position:relative">'
          + '<span style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:rgba(255,255,255,.16)"></span>'
          + '<span style="position:absolute;top:0;bottom:0;' + (neg ? ('right:50%;width:' + w.toFixed(0) + '%') : ('left:50%;width:' + w.toFixed(0) + '%'))
          + ';background:linear-gradient(' + (neg ? '270deg' : '90deg') + ',color-mix(in srgb,' + tok + ' 35%,transparent),' + tok + ');border-radius:2px"></span></span>'
          + '<span>' + money(v) + '</span></span>';
      }
      var rows = d.rows.map(function (r) {
        var regTone = r.regime === 'stabilisant' ? 'pos' : r.regime === 'accelerateur' ? 'neg' : 'neutral';
        var biasTone = r.bias === 'haussier' ? 'pos' : r.bias === 'baissier' ? 'neg' : 'neutral';
        /* Ligne activable au clavier (Entrée/Espace) et nommée : une ligne
           « cliquable » au pointeur seul excluait le clavier et le lecteur d'écran. */
        return '<tr data-gx-sym="' + esc(r.symbol) + '" data-clickable tabindex="0" aria-label="Analyser le positionnement de ' + esc(r.symbol) + '">'
          + '<td data-label="Titre"><span class="vx-ticker">' + esc(r.symbol) + '</span></td>'
          + '<td data-label="Spot" class="vx-num">' + f(r.spot) + '</td>'
          + '<td data-label="Net GEX" class="vx-num ' + (r.net_gex > 0 ? 'vx-pos' : r.net_gex < 0 ? 'vx-neg' : '') + '">' + gexBar(r.net_gex) + '</td>'
          + '<td data-label="Régime"><span class="vx-badge" data-tone="' + regTone + '">' + esc(r.regime || '—') + '</span></td>'
          + '<td data-label="Biais"><span class="vx-badge" data-tone="' + biasTone + '">' + esc(r.bias || '—') + '</span></td>'
          + '<td data-label="Bascule 0-γ" class="vx-num">' + f(r.zero_gamma) + '</td>'
          + '<td data-label="Mur call" class="vx-num">' + f(r.call_wall) + '</td>'
          + '<td data-label="Mur put" class="vx-num">' + f(r.put_wall) + '</td>'
          + '<td data-label="Max pain" class="vx-num">' + f(r.max_pain) + '</td>'
          + '<td data-label="Détail"><span class="vx-row-open">Analyser</span></td></tr>';
      }).join('');
      host.innerHTML =
        (d.climate ? '<div class="vx-muted" style="margin-bottom:.4rem">Climat : ' + esc(d.climate)
          + ' · ' + d.symbols_usable + '/' + d.symbols_scanned + ' titres exploitables.</div>' : '')
        + '<div class="vx-table-wrap vx-table-cards"><table class="vx-table"><thead><tr>'
        + '<th scope="col">Titre</th><th scope="col" class="vx-num">Spot</th><th scope="col" class="vx-num">Net GEX <span class="vx2-th-unit">($)</span></th><th scope="col">Régime</th>'
        + '<th scope="col">Biais</th><th scope="col" class="vx-num">Bascule 0-γ</th><th scope="col" class="vx-num">Mur call</th><th scope="col" class="vx-num">Mur put</th><th scope="col" class="vx-num">Max pain</th>'
        + '<th scope="col"><span class="vx2-sr-only">Détail</span></th></tr></thead><tbody>' + rows + '</tbody></table></div>';
      host.querySelectorAll('[data-gx-sym]').forEach(function (tr) {
        var open = function () {
          var s = tr.getAttribute('data-gx-sym');
          if ($('vx-gx-sym')) $('vx-gx-sym').value = s;
          load(s);
          var th = $('vx-gx-thesis');
          var doux = !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
          if (th && th.scrollIntoView) th.scrollIntoView({ behavior: doux ? 'smooth' : 'auto', block: 'start' });
        };
        tr.addEventListener('click', open);
        tr.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); }
        });
      });
    }).catch(function (e) {
      host.innerHTML = '<div class="vx-error-banner">Radar injoignable : ' + esc(e.message) + '</div>';
    });
  }

  /* Copilote : question → /api/copilot/ask (ancré dans les chiffres réels). */
  function wireCopilot() {
    var go = $('vx-cp-go'), q = $('vx-cp-q'), out = $('vx-cp-out');
    if (!go || !q || !out) return;
    function ask() {
      var question = (q.value || '').trim();
      if (!question) { VX.toast && VX.toast('Écris une question', 'warn'); return; }
      var sym = ($('vx-gx-sym') && $('vx-gx-sym').value || '').trim().toUpperCase() || null;
      out.innerHTML = '<div class="vx-empty">Le copilote analyse' + (sym ? ' ' + esc(sym) : '') + '…</div>';
      fetch('/api/copilot/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question, symbol: sym,
          avec_positions: !!($('vx-cp-pos') && $('vx-cp-pos').checked) }) })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) { out.innerHTML = '<div class="vx-error-banner">' + esc(d.error || 'réponse indisponible') + '</div>'; return; }
          out.innerHTML = '<div class="vx-insight" data-tone="action" style="white-space:pre-wrap">' + esc(d.answer) + '</div>'
            + '<div class="vx-muted" style="margin-top:.3rem">' + esc(d.label || '') + ' · lecture seule — aucun ordre.</div>';
        })
        .catch(function (e) { out.innerHTML = '<div class="vx-error-banner">Copilote injoignable : ' + esc(e.message) + '</div>'; });
    }
    go.addEventListener('click', ask);
    q.addEventListener('keydown', function (e) { if (e.key === 'Enter') ask(); });
    /* Vie privée (lot 25) : les positions déclarées ne partent JAMAIS dans le
       prompt sans cette case — action explicite, décochée par défaut. */
    if (!$('vx-cp-pos')) {
      var priv = document.createElement('label');
      priv.className = 'vx-meta';
      priv.style.cssText = 'display:flex;align-items:center;gap:6px;margin-top:.35rem;cursor:pointer';
      priv.innerHTML = '<input type="checkbox" id="vx-cp-pos"> Inclure mes positions déclarées (exclues par défaut)';
      /* `q` vit dans un <label class="vx-field"> qui n'est PAS le parent de
         `out` : insertBefore levait NotFoundError (erreur console sur toute la
         vue Positionnement, mesurée en QA). Le parent de `out` est le bon. */
      out.parentNode.insertBefore(priv, out);
    }
    /* Questions suggérées (1 clic) — remplissent et envoient. */
    var sug = document.createElement('div');
    sug.className = 'vx-flex vx-wrap'; sug.style.cssText = 'gap:6px;margin-top:.4rem';
    ['Résume le positionnement dealer.', 'Quel est le risque principal ?',
     'Le flux confirme-t-il le biais ?'].forEach(function (t) {
      var b = document.createElement('button');
      b.className = 'vx-btn vx-btn-sm vx-btn-ghost'; b.textContent = t;
      b.addEventListener('click', function () { q.value = t; ask(); });
      sug.appendChild(b);
    });
    out.parentNode.insertBefore(sug, out);
  }

  /* Barres GEX par strike — SVG inline (call vert vers la droite, put rouge vers la gauche). */
  function renderBars(d) {
    var g = d.gex || {}, host = $('vx-gx-bars');
    if (!host) return;
    if (g.empty || !(g.strikes || []).length) {
      host.innerHTML = '<div class="vx-empty">Aucun strike exploitable (OI + gamma réels absents).</div>';
      return;
    }
    var rows = g.strikes.slice().sort(function (a, b) { return b.strike - a.strike; });   // strikes hauts en haut
    var maxAbs = 0;
    rows.forEach(function (r) { maxAbs = Math.max(maxAbs, Math.abs(r.call_gex || 0), Math.abs(r.put_gex || 0)); });
    maxAbs = maxAbs || 1;
    var W = 520, mid = W / 2, rowH = 20, H = rows.length * rowH + 28, scale = (W / 2 - 60) / maxAbs;
    var pos = 'var(--vx-positive,#2BBE90)', neg = 'var(--vx-negative,#E9555F)';
    /* GRAMMAIRE TV (lot 203) : les MURS (plus gros call GEX / plus gros put
       GEX — s'il y a ≥ 2 strikes) sont les dominantes — barre pleine
       intensité + valeur RÉELLE en chip pleine couleur (texte sombre) au
       bout de la barre ; les autres restent adoucies (.55). */
    var iCall = -1, iPut = -1;
    if (rows.length >= 2) rows.forEach(function (r, i) {
      if ((r.call_gex || 0) > 0 && (iCall < 0 || (r.call_gex || 0) > (rows[iCall].call_gex || 0))) iCall = i;
      if (Math.abs(r.put_gex || 0) > 0 && (iPut < 0 || Math.abs(r.put_gex || 0) > Math.abs(rows[iPut].put_gex || 0))) iPut = i;
    });
    function chip(x, y, txt, colr, alignLeft) {
      var w = txt.length * 5.4 + 8, h = 12;
      var ax = alignLeft ? x : x - w;
      ax = Math.max(2, Math.min(ax, W - w - 2));
      return '<rect x="' + ax.toFixed(1) + '" y="' + (y - 1) + '" width="' + w.toFixed(1) + '" height="' + h + '" rx="6" fill="' + colr + '"/>'
        + '<text x="' + (ax + w / 2).toFixed(1) + '" y="' + (y + 8) + '" text-anchor="middle" font-size="8.5" font-weight="800" fill="var(--vx-graphite-850,#121214)">' + txt + '</text>';
    }
    var spotY = null;
    var svg = ['<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="GEX par strike">'];
    svg.push('<line x1="' + mid + '" y1="6" x2="' + mid + '" y2="' + (H - 16) + '" stroke="var(--vx-border,#30292B)"/>');
    rows.forEach(function (r, i) {
      var y = 10 + i * rowH;
      if (spotY === null && g.spot != null && r.strike <= g.spot) spotY = y - 2;   // 1er strike ≤ spot
      var cw = Math.abs(r.call_gex || 0) * scale, pw = Math.abs(r.put_gex || 0) * scale;
      if (cw > 0.5) svg.push('<rect x="' + mid + '" y="' + y + '" width="' + cw + '" height="' + (rowH - 6) + '" fill="' + pos + '" opacity="' + (i === iCall ? '1' : '.55') + '"/>');
      if (pw > 0.5) svg.push('<rect x="' + (mid - pw) + '" y="' + y + '" width="' + pw + '" height="' + (rowH - 6) + '" fill="' + neg + '" opacity="' + (i === iPut ? '1' : '.55') + '"/>');
      if (i === iCall && cw > 0.5) svg.push(chip(mid + cw + 4, y, money(r.call_gex), pos, true));
      if (i === iPut && pw > 0.5) svg.push(chip(mid - pw - 4, y, money(r.put_gex), neg, false));
      svg.push('<text x="' + (mid + 4) + '" y="' + (y + rowH - 9) + '" font-size="9.5" fill="var(--vx-text-muted,#989092)">' + f(r.strike, 0) + '</text>');
    });
    if (spotY != null) svg.push('<line x1="10" y1="' + spotY + '" x2="' + (W - 10) + '" y2="' + spotY + '" stroke="var(--vx-analysis-light,#65d8e8)" stroke-dasharray="3 3"/>');
    svg.push('</svg>');
    host.innerHTML = svg.join('')
      + '<div class="vx-muted" style="margin-top:.3rem">Vert = call GEX (+) · rouge = put GEX (−) · pointillé cyan = spot ' + f(g.spot) + '. '
      + esc(d.coverage || '') + '.</div>';
  }

  function renderFlow(d) {
    var fl = d.flow || {}, host = $('vx-gx-flow');
    if (!host) return;
    if (fl.empty || !(fl.contracts || []).length) {
      host.innerHTML = '<div class="vx-empty">' + esc((fl.reason || 'aucun flux notable exploitable') + '.') + '</div>';
      return;
    }
    var rows = fl.contracts.map(function (c) {
      return '<tr><td><span class="vx-badge" data-tone="' + (c.type === 'CALL' ? 'pos' : 'neg') + '">' + esc(c.type) + '</span> ' + f(c.strike, 0)
        + (c.exp ? ' <span class="vx-muted">' + esc(c.exp) + '</span>' : '') + '</td>'
        + '<td class="vx-num">' + f(c.vol, 0) + '</td>'
        + '<td class="vx-num">' + (c.vol_oi != null ? f(c.vol_oi, 2) + (c.fresh ? ' ⚡' : '') : 'n/d') + '</td>'
        + '<td class="vx-num">' + money(c.premium) + '</td></tr>';
    }).join('');
    var skew = fl.skew ? '<div class="vx-muted" style="margin-bottom:.3rem">Skew premium : <b>' + esc(fl.skew) + '</b> (' + f(fl.call_pct, 0) + ' % calls)</div>' : '';
    host.innerHTML = skew
      + '<div class="vx-table-wrap"><table class="vx-table"><thead><tr><th>Contrat</th><th class="vx-num">Vol</th><th class="vx-num">Vol/OI</th><th class="vx-num">Premium</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div>'
      + '<div class="vx-muted" style="margin-top:.3rem">' + esc(fl.basis || '') + '. ⚡ = volume &gt; OI (positionnement frais).</div>';
  }

  function load(sym) {
    sym = (sym || '').trim().toUpperCase();
    if (!/^[A-Z.\-]{1,12}$/.test(sym)) { VX.toast && VX.toast('Ticker invalide', 'error'); return; }
    try { if (VX.store) VX.store.set('active_ticker', sym); } catch (e0) {}
    ($('vx-gx-thesis')||{}).innerHTML = '<section class="vx-card"><div class="vx-empty">Analyse du positionnement de ' + esc(sym) + '…</div></section>';
    VX.fetch('/api/options/gex/' + encodeURIComponent(sym), { ttl: 120000 }).then(function (d) {
      renderThesis(d); renderTiles(d); renderBars(d); renderFlow(d); renderDaily(d);
      try { VX.context && VX.context.save && VX.context.save({ selectedSymbol: sym }); } catch (e) {}
    }).catch(function (e) {
      ($('vx-gx-thesis')||{}).innerHTML = '<section class="vx-card"><div class="vx-error-banner">Chargement impossible : ' + esc(e.message) + '</div></section>';
    });
  }

  var go = $('vx-gx-go'), inp = $('vx-gx-sym');
  if (go && inp) {
    go.addEventListener('click', function () { load(inp.value); });
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') load(inp.value); });
  }
  wireCopilot();
  loadRadar();
  /* pré-remplissage : ticker actif du store, sinon un contrat du board via chips */
  var pre = '';
  try { pre = (VX.store && VX.store.get && VX.store.get('active_ticker')) || ''; } catch (e) {}
  if (pre && inp) { inp.value = pre; load(pre); }
})();
