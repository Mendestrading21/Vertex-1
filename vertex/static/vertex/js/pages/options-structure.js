/* options-structure.js — Options : Carte-Verdict + Scénarios + payoff canonique +
   Greeks interprétés + comparaison (vue « structure »), lecture LEAPS (« leaps ») et
   positions options canoniques (« positions »). PR n°6.

   Moteur canonique de payoff : multileg_lab via /api/options/strategies/<sym> et
   /api/options/analyze — un seul moteur (Constitution §6, LOT D). Aucune exécution
   d'ordre : chaque action est analytique. Donnée absente => état honnête (jamais un
   chiffre inventé, jamais une PoP fabriquée). */
(function () {
  'use strict';
  var VX = window.VX, VC = window.VXCharts;
  var Vf = (VX && VX.fmt) || {};
  function view() { try { return new URLSearchParams(location.search).get('view') || 'structure'; } catch (e) { return 'structure'; } }
  function esc(s) { return String(s == null ? '' : s).replace(/[<>&"]/g, function (c) { return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]; }); }
  function $(id) { return document.getElementById(id); }
  function price(v) { return (Vf.price ? Vf.price(v) : ('$' + Number(v).toFixed(2))); }
  function num(v, d) { return (Vf.num ? Vf.num(v, d) : Number(v).toFixed(d == null ? 2 : d)); }
  function nd(v) { return (Vf.nd ? Vf.nd(v) : (v == null ? '—' : v)); }
  var toneCls = function (t) { return ({ pos: 'vx-pos', neg: 'vx-neg', warn: 'vx-warn', muted: 'vx-muted' })[t] || 'vx-muted'; };

  var _board = null;
  function board() {
    if (_board) return Promise.resolve(_board);
    return VX.fetch('/api/options', { ttl: 120000 }).then(function (d) { _board = (d && d.board) || []; return _board; }).catch(function () { return []; });
  }

  /* ── Liquidité, mouvement attendu, asymétrie, verdict, scénarios ──
     Calculés par le SERVEUR (vertex/options/structure_verdict.py) et servis
     dans `strategie.analyse` par /api/options/strategies/<sym>. Les fonctions
     qui vivaient ici (liqState, strategyLiquidity, pnlAt, expectedMove,
     computeVerdict) étaient un calcul financier dans l'interface : retirées,
     la page PEINT. Scénarios et P&L à l'échéance (payoff) viennent du serveur.
     Liquidité absente = « Insuffisante — non évaluable », jamais un zéro
     (règle conservée côté serveur). ── */
  function analyseDe(s) { return (s && s.analyse) || null; }

  /* ════════════════ VUE STRUCTURE ════════════════ */

  /* La vue porte QUATRE hôtes de contenu. Mesure du 2026-09-06 : les branches
     dégradées n'en remplissaient que deux — `vx-os-scenarios` et
     `vx-os-compare` étaient vidés au chargement (l. 44) et jamais remplis,
     donc littéralement vides et sans motif dans TOUS les états dégradés, y
     compris la panne réseau où seul l'hôte du verdict était servi. Un hôte
     vide ne distingue pas « rien à montrer » de « la lecture a échoué ».
     Un seul endroit nomme donc l'absence, pour que le prochain état dégradé
     ne puisse pas en oublier un. */
  var HOTES_STRUCTURE = [
    ['vx-os-scenarios', 'Pas de scénarios'],
    ['vx-os-compare', 'Pas de comparaison de structures'],
    ['vx-os-payoff', 'Pas de courbe de P&amp;L'],
    ['vx-os-greeks', 'Pas de greeks de position'],
  ];
  function nommerAbsenceStructure(motif, enPanne) {
    HOTES_STRUCTURE.forEach(function (h) {
      var el = $(h[0]); if (!el) return;
      el.innerHTML = (enPanne ? VX.states.error(h[1] + ' : ' + motif)
                              : '<div class="vx-empty">' + h[1] + ' : ' + motif + '.</div>');
    });
  }

  var _structRetry = {};
  function loadStructure(sym) {
    try { if (window.VX && VX.store) VX.store.set('active_ticker', sym); } catch (e0) {}
    var vHost = $('vx-os-verdict'); if (!vHost) return;
    vHost.innerHTML = '<div class="vx-skeleton" style="height:150px"></div>';
    /* Chargement : les quatre hôtes disent qu'ils travaillent. Deux d'entre
       eux restaient à '' — indiscernable d'une carte qui n'a rien à dire. */
    ($('vx-os-scenarios')||{}).innerHTML = '<div class="vx-empty">Calcul…</div>';
    ($('vx-os-compare')||{}).innerHTML = '<div class="vx-empty">Calcul…</div>';
    ($('vx-os-payoff')||{}).innerHTML = '<div class="vx-empty">Calcul…</div>';
    ($('vx-os-greeks')||{}).innerHTML = '<div class="vx-empty">Calcul…</div>';
    Promise.all([VX.fetch('/api/options/strategies/' + encodeURIComponent(sym), { ttl: 60000 }), board()])
      .then(function (r) {
        var d = r[0], bd = r[1];
        /* Chaîne chargée en fond (serveur : en_cours) → réessai borné hors cache. */
        if (d && d.en_cours && (_structRetry[sym] || 0) < 2) {
          _structRetry[sym] = (_structRetry[sym] || 0) + 1;
          setTimeout(function () {
            try { VX.fetch.invalidate('/api/options/strategies/' + encodeURIComponent(sym)); } catch (e1) {}
            loadStructure(sym);
          }, ((d.retry_s || 8) * 1000));
        }
        if (!d || !d.available || !(d.strategies || []).length) {
          /* MESURE du 2026-09-06 : `vx-os-greeks` restait à '' (vidé l. 44 et
             jamais rempli) et `vx-os-payoff` affichait un TIRET NU — deux
             hôtes muets sur un écran dont la carte verdict, elle, nomme la
             cause. Un tiret sans motif ne distingue pas l'absence de la
             panne. On répète ICI le motif que la carte verdict possède,
             plutôt que d'inventer un second vocabulaire. */
          var motif = (d && d.reason) || 'aucune structure constructible depuis le board';
          vHost.innerHTML = insufficientCard(sym, motif);
          nommerAbsenceStructure(esc(motif), false);
          return;
        }
        var s = d.strategies.filter(function (x) { return x.recommended; })[0] || d.strategies[0];
        var a = analyseDe(s);
        if (!a || !a.verdict) {
          /* Second site du même défaut : ici la structure EXISTE mais son
             analyse serveur manque — un état différent du précédent, et les
             deux hôtes doivent le dire au lieu de rendre un tiret nu. */
          var motifA = 'analyse serveur absente (structure_verdict)';
          vHost.innerHTML = insufficientCard(sym, motifA);
          nommerAbsenceStructure(esc(motifA), false);
          return;
        }
        vHost.innerHTML = verdictCard(d, s, {
          spot: a.spot, dte: a.dte, capital: a.capital, gainProb: a.gain_prob, gainExc: a.gain_exc,
          asym: a.asym, liq: a.liquidite, verdict: a.verdict, ivDec: a.iv_dec, em: a.em
        });
        renderScenarios(d, s, a);
        renderPayoff(d, s, { spot: a.spot, capital: a.capital });
        renderGreeks(s, a.iv_dec);
        renderCompare(d, bd);
      })
      .catch(function (e) {
        /* Une lecture EN ÉCHEC n'est pas une absence : les quatre hôtes le
           disent avec l'état d'erreur, pas avec un vide. */
        var motifE = esc(e.message || 'lecture en échec');
        vHost.innerHTML = VX.states.error('Analyse indisponible : ' + motifE);
        nommerAbsenceStructure('la lecture a échoué (' + motifE + ')', true);
      });
  }

  function insufficientCard(sym, reason) {
    return '<section class="vx-card vx-insufficient" role="note">'
      + '<div class="vx-card-header"><span class="vx-card-title">Données insuffisantes</span></div>'
      + '<p>Structure non évaluable pour <b>' + esc(sym) + '</b> : ' + esc(reason) + '.</p>'
      + '<p class="vx-meta">Aucun verdict positif, aucune PoP ni Greek affichés comme fiables tant que primes/IV/OI manquent. '
      + 'Prochaine action : choisir un sous-jacent présent dans le tableau d\'options, ou réessayer après un scan.</p></section>';
  }

  function verdictCard(d, s, m) {
    var netLbl = s.is_credit ? ('Crédit ' + price(Math.abs(s.net_premium))) : ('Débit ' + price(Math.abs(s.net_premium)));
    var gmax = s.max_profit_unbounded ? 'illimité (théorique)' : (s.max_profit != null ? price(s.max_profit) : '—');
    var be = (s.breakevens && s.breakevens.length) ? s.breakevens.map(function (b) { return nd(b); }).join(' · ') : '—';
    var g = s.greeks || null;
    var cell = function (l, v, cls) { return '<div class="vx-kv"><span class="k">' + l + '</span><span class="v ' + (cls || '') + '">' + v + '</span></div>'; };
    var fresh = '<span class="vx-freshness" data-state="' + (d.demo ? 'demo' : 'delayed') + '">' + (d.demo ? 'Démo' : 'Différé') + '</span>';
    return '<section class="vx-verdict-card vx-card" aria-label="Verdict de la structure">'
      + '<div class="vx-flex vx-wrap" style="justify-content:space-between;align-items:flex-start;gap:10px">'
      + '<div><div class="vx-flex" style="gap:8px;align-items:center"><span class="vx-eyebrow">Verdict</span>' + fresh
      + (m.liq ? '<span class="vx-badge ' + toneCls(m.liq.tone) + '">Liquidité : ' + m.liq.label + '</span>' : '') + '</div>'
      + '<h2 class="' + toneCls(m.verdict.tone) + '" style="margin:4px 0 2px;font-size:22px">' + esc(m.verdict.label) + '</h2>'
      + '<div class="vx-dim" style="font-size:13px">' + esc(d.sym) + ' · <b>' + esc(s.label) + '</b> · biais ' + esc(d.bias) + ' — ' + esc(m.verdict.why) + '</div></div>'
      + '<div class="vx-flex" style="flex-direction:column;align-items:flex-end;gap:2px">'
      + '<div class="vx-kpi-label">Ratio d\'asymétrie</div>'
      + '<div class="' + (m.asym >= 3 ? 'vx-pos' : m.asym != null && m.asym < 1.2 ? 'vx-neg' : 'vx-warn') + '" style="font-size:26px;font-weight:700">' + (m.asym != null ? num(m.asym, 1) + '×' : 'n/d') + '</div>'
      + '<div class="vx-meta">gain exceptionnel / perte max</div></div></div>'
      + '<div class="vx-grid vx-mt3" style="grid-template-columns:repeat(4,1fr);gap:8px">'
      + cell('Sous-jacent', esc(d.sym) + ' @ ' + price(m.spot))
      + cell('Échéance', esc(d.exp ? String(d.exp).slice(0, 10) : '—') + ' · ' + (m.dte != null ? m.dte + ' j' : '—'))
      + cell('Strikes', esc((s.legs || []).map(function (l) { return (l.type[0].toUpperCase()) + nd(l.strike); }).join(' / ')))
      + cell('Prime nette', netLbl, s.is_credit ? 'vx-pos' : '')
      + cell('Capital à risque', price(m.capital), 'vx-neg')
      + cell('Perte maximale', price(-m.capital), 'vx-neg')
      + cell('Gain probable (+1σ, échéance)', m.gainProb != null ? ((m.gainProb >= 0 ? '+' : '') + price(m.gainProb)) : 'n/d', m.gainProb >= 0 ? 'vx-pos' : 'vx-neg')
      + cell('Gain exceptionnel', typeof m.gainExc === 'number' ? ('+' + price(m.gainExc)) : gmax, 'vx-pos')
      + cell('Breakeven(s)', be)
      + cell('Delta global', g ? num(g.delta, 1) : 'Insuffisant', g ? 'vx-violet' : 'vx-muted')
      + cell('Theta global', g ? num(g.theta, 2) + ' $/j' : 'Insuffisant', g ? 'vx-neg' : 'vx-muted')
      + cell('IV', m.ivDec != null ? num(m.ivDec * 100, 1) + ' %' : 'n/d', m.ivDec != null ? 'vx-violet' : '')
      + '</div>'
      + '<div class="vx-card-foot vx-mt2"><span class="vx-meta">' + esc(s.model_note || '')
      + ' · PoP ' + (s.probability_of_profit != null ? num(s.probability_of_profit, 0) + ' %' : 'n/d') + ' (modèle lognormal — estimation).'
      + ' Payoff & greeks : moteur multileg_lab (board ' + (d.demo ? 'démo' : 'réel') + '). Lecture seule — aucun ordre.</span></div>'
      + '<div class="vx-flex vx-mt2" style="gap:8px;flex-wrap:wrap">'
      + '<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/analysis/' + encodeURIComponent(d.sym) + '">Voir l\'analyse du sous-jacent →</a>'
      + '<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/options?view=volatility">La volatilité est-elle chère ?</a>'
      + '<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/options?view=events">Un événement menace-t-il l\'échéance ?</a></div>'
      + '</section>';
  }

  /* Carte-Scénario (LOT C) — valeurs À L'ÉCHÉANCE (distinctes de la valeur avant échéance). */
  function renderScenarios(d, s, a) {
    var host = $('vx-os-scenarios'); if (!host) return;
    var sc = (a && a.scenarios) || [];
    if (!a || !a.em || !sc.length) { host.innerHTML = '<section class="vx-card"><div class="vx-meta">Scénarios indisponibles : IV absente, mouvement attendu non calculable (aucune valeur inventée).</div></section>'; return; }
    /* Scénarios SERVIS (structure_verdict) : prix, P&L et % viennent du serveur. */
    var cards = sc.map(function (x) {
      var pnl = x.pnl, pct = x.pct;
      return '<div class="vx-scenario" data-kind="' + esc(x.kind || 'base') + '">'
        + '<div class="vx-scenario-head"><b>' + esc(x.cle) + '</b><span class="vx-meta">' + esc(x.cond) + '</span></div>'
        + '<div class="vx-kv"><span class="k">Sous-jacent</span><span class="v vx-mono">' + price(x.px) + '</span></div>'
        + '<div class="vx-kv"><span class="k">P&L (échéance)</span><span class="v vx-mono ' + (pnl >= 0 ? 'vx-pos' : 'vx-neg') + '">' + (pnl != null ? ((pnl >= 0 ? '+' : '') + price(pnl)) : 'n/d') + '</span></div>'
        + '<div class="vx-kv"><span class="k">P&L %</span><span class="v vx-mono ' + (pct >= 0 ? 'vx-pos' : 'vx-neg') + '">' + (pct != null ? (pct >= 0 ? '+' : '') + num(pct, 0) + ' %' : 'n/d') + '</span></div>'
        + '<div class="vx-kv"><span class="k">Horizon</span><span class="v">' + (x.horizon_j != null ? x.horizon_j + ' j' : '—') + '</span></div>'
        + '</div>';
    }).join('');
    host.innerHTML = '<section class="vx-card" aria-label="Scénarios de la structure">'
      + '<div class="vx-card-header"><span class="vx-card-title">Scénarios — valeurs à l\'échéance</span>'
      + '<span class="vx-chart-question">Perte probable · gain probable · gain exceptionnel (jamais confondus)</span></div>'
      + '<div class="vx-scenario-grid">' + cards + '</div>'
      + '<div class="vx-card-foot"><span class="vx-meta">Valeurs à l\'échéance (payoff). Avant l\'échéance, la valeur inclut la valeur-temps '
      + '(theta) et l\'IV — non modélisée ici pour ne pas inventer un prix. Aucune probabilité affichée n\'est garantie.</span></div></section>';
  }

  /* Payoff canonique (LOT D) — moteur multileg_lab, Chart Shell, spot + breakevens. */
  function renderPayoff(d, s, m) {
    var host = $('vx-os-payoff'); if (!host) return;
    var pts = s.payoff || [];
    if (!VC || !window.Chart || pts.length < 2) { host.innerHTML = '<div class="vx-empty">Payoff indisponible (données insuffisantes).</div>'; return; }
    var favorable = pts.filter(function (p) { return p.pnl >= 0; }).length;
    var concl = (s.breakevens && s.breakevens.length)
      ? ('Zone favorable au-delà de ' + s.breakevens.map(function (b) { return nd(b); }).join(' / ') + '. Perte plafonnée à ' + price(m.capital) + '.')
      : ('Perte plafonnée à ' + price(m.capital) + '.');
    host.innerHTML = '';
    VC.card('vx-os-payoff', {
      title: 'Payoff à l\'échéance — ' + esc(s.label), question: 'Où gagne / perd la structure ?',
      conclusion: concl, unit: 'P&L $ (1 structure)', timeframe: (d.dte != null ? d.dte + ' j' : ''),
      source: d.demo ? 'multileg_lab (board démo)' : 'multileg_lab (board réel)', timestamp: (d && d.as_of) || null, mode: d.demo ? 'demo' : 'delayed',
      summary: 'Courbe de P&L à l\'échéance selon le cours du sous-jacent ; spot ' + price(m.spot)
        + ', breakeven(s) ' + ((s.breakevens || []).map(function (b) { return nd(b); }).join(', ') || '—')
        + ', perte max ' + price(m.capital) + ', ' + favorable + ' points sur ' + pts.length + ' en zone favorable.',
      height: 260,
      render: function (cv) {
        var spot = m.spot, bes = s.breakevens || [];
        /* LOT 133 : l'axe X est en CATEGORIES (labels = prix) — un repere doit
           etre place par INDEX, pas par prix ; l'ancien getPixelForValue(prix)
           tombait hors de l'axe et spot/BE n'etaient JAMAIS traces. */
        function idxOf(px) {
          var best = 0, bd = Infinity;
          for (var i = 0; i < pts.length; i++) { var dd = Math.abs(pts[i].price - px); if (dd < bd) { bd = dd; best = i; } }
          return best;
        }
        var refPlugin = {
          id: 'osRefs', afterDraw: function (ch) {
            var xa = ch.scales.x, ya = ch.scales.y, ctx = ch.ctx; if (!xa || !ya) return;
            function vline(px, color, label) {
              var xp = xa.getPixelForValue(idxOf(px)); if (isNaN(xp)) return;
              ctx.save(); ctx.strokeStyle = color; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
              ctx.beginPath(); ctx.moveTo(xp, ya.top); ctx.lineTo(xp, ya.bottom); ctx.stroke();
              ctx.setLineDash([]); ctx.fillStyle = color; ctx.font = '10px system-ui'; ctx.fillText(label, xp + 3, ya.top + 10); ctx.restore();
            }
            var y0 = ya.getPixelForValue(0);
            if (!isNaN(y0)) { ctx.save(); ctx.strokeStyle = 'rgba(255,255,255,.25)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(xa.left, y0); ctx.lineTo(xa.right, y0); ctx.stroke(); ctx.restore(); }
            /* LOT 133 : reperes sur TOKENS (grammaire du payoff lot 124) —
               spot en info, breakeven en warning ; plus aucun rgba orphelin. */
            vline(spot, VC.colors.info, 'spot');
            bes.forEach(function (b) { vline(b, VC.colors.warning, 'BE'); });
          }
        };
        VC.mount(cv, {
          type: 'line',
          data: { labels: pts.map(function (p) { return p.price; }), datasets: [{ data: pts.map(function (p) { return p.pnl; }), borderWidth: 1.6, pointRadius: 0, tension: 0, borderColor: VC.colors.neutral, segment: { borderColor: function (c) { return c.p1.parsed.y >= 0 ? VC.colors.positive : VC.colors.negative; } },
            /* zones gain/perte teintees — on VOIT ou la structure gagne */
            fill: { target: { value: 0 }, above: VC.colors.positive + '24', below: VC.colors.negative + '20' } }] },
          options: {
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (c) { return 'P&L ' + price(c.parsed.y) + ' @ ' + nd(c.label); } } } },
            scales: { x: { ticks: { maxTicksLimit: 7, callback: function (v) { return nd(this.getLabelForValue(v)); } }, grid: { display: false } }, y: { grid: { color: 'rgba(255,255,255,.06)' }, ticks: { callback: function (v) { return price(v); } } } }
          },
          /* LOT 133 : C.mount ne prend que (canvas, config) — l'ancien 3e
             argument etait ignore et spot/BE n'apparaissaient JAMAIS. Les
             plugins inline vivent au niveau racine de la config Chart.js. */
          plugins: [refPlugin, VC.softGlowPlugin ? VC.softGlowPlugin() : { id: 'noop' }]
        });
      }
    });
  }

  /* Greeks interprétés (LOT E) — jamais un Greek sans interprétation. */
  function greekRow(label, val, unit, interp, tone) {
    return '<div class="vx-greek"><div class="vx-flex" style="justify-content:space-between"><b>' + label + '</b>'
      + '<span class="vx-mono ' + (tone || '') + '">' + (val == null ? 'Insuffisant' : num(val, 3) + (unit ? ' ' + unit : '')) + '</span></div>'
      + '<div class="vx-meta">' + esc(interp) + '</div></div>';
  }
  function renderGreeks(s, ivDec) {
    var host = $('vx-os-greeks'); if (!host) return;
    var g = s.greeks;
    if (!g) {
      host.innerHTML = '<div class="vx-insufficient" role="note"><b>Greeks indisponibles.</b> '
        + 'IV absente sur le board — aucun delta/theta/vega affiché comme fiable (pas d\'estimation inventée).</div>';
      return;
    }
    var lvl1 = greekRow('Delta', g.delta, '$/pt', '≈ ' + num(g.delta, 1) + ' $ de P&L par +1 $ du sous-jacent. Risque principal : direction.', g.delta >= 0 ? 'vx-pos' : 'vx-neg')
      + greekRow('Theta', g.theta, '$/jour', '≈ ' + num(g.theta, 2) + ' $/jour d\'érosion (toutes choses égales). Risque : le temps.', 'vx-neg')
      + greekRow('Vega', g.vega, '$/pt IV', '≈ ' + num(g.vega, 2) + ' $ par +1 pt d\'IV. Risque : effondrement de volatilité post-événement.', 'vx-violet')
      + greekRow('Gamma', g.gamma, '', 'Accélération du delta quand le cours bouge — plus élevé près du strike / de l\'échéance.', 'vx-violet');
    var lvl2 = greekRow('Vanna', g.vanna, '', 'Sensibilité du delta à l\'IV (couplage direction × volatilité).', 'vx-violet')
      + greekRow('Vomma', g.vomma, '', 'Sensibilité du vega à l\'IV (convexité de volatilité).', 'vx-violet');
    host.innerHTML = '<div class="vx-greeks">' + lvl1 + '</div>'
      + '<details class="vx-mt2"><summary class="vx-btn vx-btn-sm vx-btn-ghost">Greeks avancés</summary>'
      + '<div class="vx-greeks vx-mt2">' + lvl2 + '</div></details>'
      + '<div class="vx-card-foot"><span class="vx-meta">Greeks de position (moteur). Agrégés seulement si IV fiable — sinon « Insuffisant ».</span></div>';
  }

  /* Comparaison de structures (LOT I) — matrice claire, pas un radar. */
  function renderCompare(d, bd) {
    var host = $('vx-os-compare'); if (!host) return;
    var rows = d.strategies || []; if (rows.length < 2) { host.innerHTML = ''; return; }
    var head = ['Structure', 'Coût/risque max', 'Gain max', 'Breakeven', 'Delta', 'Theta', 'Vega', 'PoP', 'DTE', 'Liquidité', 'Asymétrie', 'Adéquation'];
    var body = rows.map(function (s) {
      var an = analyseDe(s) || {};
      var cap = an.capital != null ? an.capital : Math.abs(s.max_loss || 0);
      var gmax = s.max_profit_unbounded ? '∞' : (s.max_profit != null ? price(s.max_profit) : '—');
      var asym = an.asym_compare != null ? an.asym_compare : null;   // servi (max_profit / capital)
      var g = s.greeks || {};
      var liq = an.liquidite || { key: 'insuffisante', label: 'Insuffisante', tone: 'neg' };
      return '<tr' + (s.recommended ? ' class="vx-row-hl"' : '') + '>'
        + '<td data-label="Structure">' + (s.recommended ? '★ ' : '') + esc(s.label) + '</td>'
        + '<td data-label="Risque max" class="vx-num vx-neg">' + price(cap) + '</td>'
        + '<td data-label="Gain max" class="vx-num vx-pos">' + gmax + '</td>'
        + '<td data-label="Breakeven" class="vx-num">' + ((s.breakevens || []).map(function (b) { return nd(b); }).join(' · ') || '—') + '</td>'
        + '<td data-label="Delta" class="vx-num">' + (g.delta != null ? num(g.delta, 1) : '—') + '</td>'
        + '<td data-label="Theta" class="vx-num vx-neg">' + (g.theta != null ? num(g.theta, 2) : '—') + '</td>'
        + '<td data-label="Vega" class="vx-num">' + (g.vega != null ? num(g.vega, 2) : '—') + '</td>'
        + '<td data-label="PoP" class="vx-num">' + (s.probability_of_profit != null ? num(s.probability_of_profit, 0) + ' %' : '—') + '</td>'
        + '<td data-label="DTE" class="vx-num">' + (s.days_to_exp != null ? s.days_to_exp + ' j' : '—') + '</td>'
        + '<td data-label="Liquidité"><span class="' + toneCls(liq.tone) + '">' + liq.label + '</span></td>'
        + '<td data-label="Asymétrie" class="vx-num">' + (asym != null ? num(asym, 1) + '×' : '—') + '</td>'
        + '<td data-label="Adéquation" class="vx-num">' + (s.fit_score != null ? num(s.fit_score, 0) : '—') + '</td></tr>';
    }).join('');
    host.innerHTML = '<section class="vx-card" aria-label="Comparaison des structures">'
      + '<div class="vx-card-header"><span class="vx-card-title">Comparer les structures</span>'
      + '<span class="vx-chart-question">Quelle structure exprime le mieux la thèse avec le moins de risque inutile ?</span></div>'
      + '<div class="vx-table-wrap vx-table-cards"><table class="vx-table"><thead><tr>'
      + head.map(function (h) { return '<th>' + h + '</th>'; }).join('') + '</tr></thead><tbody>' + body + '</tbody></table></div>'
      + '<div class="vx-card-foot"><span class="vx-meta">★ = mieux adaptée au biais (adéquation = 45 % alignement + 30 % PoP + 25 % R:R — heuristique transparente, pas une promesse).</span></div></section>';
  }

  /* ════════════════ VUE LEAPS (LOT B) ════════════════ */
  function leapsScore(c) {
    /* Score de compatibilité EXPLICABLE (0-100) — uniquement sur données réelles.
       Le temps seul n'est jamais une thèse : delta + liquidité pèsent le plus. */
    var parts = [];
    var delta = Math.abs(c.delta == null ? 0 : c.delta);
    var dDelta = (delta >= 0.70 && delta <= 0.90) ? 30 : (delta >= 0.60 && delta < 0.95) ? 18 : 6;
    parts.push({ k: 'Delta ' + (c.delta != null ? num(delta, 2) : 'n/d'), v: dDelta, max: 30, ok: dDelta >= 24 });
    var mo = c.dte != null ? c.dte / 30 : null;
    var dDte = (mo != null && mo >= 6 && mo <= 18) ? 25 : (mo != null && mo >= 4 && mo <= 22) ? 14 : 4;
    parts.push({ k: 'Échéance ' + (mo != null ? num(mo, 0) + ' mois' : 'n/d'), v: dDte, max: 25, ok: dDte >= 20 });
    var dOi = c.oi == null ? 0 : (c.oi >= 8000 ? 20 : c.oi >= 3000 ? 13 : c.oi >= 800 ? 6 : 2);
    parts.push({ k: 'OI ' + nd(c.oi), v: dOi, max: 20, ok: dOi >= 13 });
    /* Le board RÉEL publie `spread` (%) ; `spread_pct` est la clé du board de
       DÉMO. Mesuré le 2026-09-06 : 30/30 cartes LEAPS affichaient « Spread n/d
       · 0/15 » alors que /api/options servait la valeur (NVDA CALL 230
       2027-03-19 : spread 1,0) — le pied de carte promet pourtant « Score
       explicable = somme des composantes réelles ci-dessus ». Une composante
       sur cinq valait zéro à cause d'un nom de champ : NVDA 61/100 (ambre) au
       lieu de 76/100 (vert). Les deux clés absentes restent « n/d ». */
    var sp = (c.spread_pct != null) ? c.spread_pct : c.spread;
    var dSp = sp == null ? 0 : (sp <= 3 ? 15 : sp <= 6 ? 9 : sp <= 10 ? 4 : 0);
    parts.push({ k: 'Spread ' + (sp != null ? num(sp, 1) + ' %' : 'n/d'), v: dSp, max: 15, ok: dSp >= 9 });
    var dIv = c.iv == null ? 0 : (c.iv <= 45 ? 10 : c.iv <= 70 ? 6 : 2);
    parts.push({ k: 'IV ' + (c.iv != null ? num(c.iv, 0) + ' %' : 'n/d'), v: dIv, max: 10, ok: dIv >= 6 });
    var total = parts.reduce(function (a, p) { return a + p.v; }, 0);
    return { total: total, parts: parts };
  }
  function loadLeaps(sym) {
    try { if (window.VX && VX.store) VX.store.set('active_ticker', sym); } catch (e0) {}
    var host = $('vx-lp-out'); if (!host) return;
    host.innerHTML = '<div class="vx-skeleton" style="height:120px"></div>';
    board().then(function (bd) {
      var leaps = bd.filter(function (c) { return c.sym === sym && c.type === 'CALL' && c.dte != null && c.dte >= 150 && c.dte <= 560; })
        .sort(function (a, b) { return leapsScore(b).total - leapsScore(a).total; });
      if (!leaps.length) {
        host.innerHTML = '<section class="vx-card vx-insufficient" role="note"><div class="vx-card-header"><span class="vx-card-title">Aucun LEAPS exploitable</span></div>'
          + '<p>Pas de call longue échéance (6-18 mois) pour <b>' + esc(sym) + '</b> dans le tableau. '
          + 'Un LEAPS exige delta 0,70-0,90, OI élevé et spread faible — non évaluable sans ces données.</p></section>';
        return;
      }
      host.innerHTML = leaps.slice(0, 4).map(function (c) {
        var sc = leapsScore(c), tone = sc.total >= 70 ? 'pos' : sc.total >= 50 ? 'warn' : 'neg';
        var kind = (Math.abs(c.delta || 0) >= 0.7 ? 'Achat de tendance (delta directionnel)' : 'Achat de temps — le temps seul n\'est pas une thèse');
        var bars = sc.parts.map(function (p) {
          return '<div class="vx-opt-dim"><span class="vx-opt-dim-l">' + esc(p.k) + '</span>'
            + '<span class="vx-opt-dim-bar"><i style="width:' + Math.round(p.v / p.max * 100) + '%;background:' + (p.ok ? 'var(--vx-positive,#2BBE90)' : 'var(--vx-warning,#D9BE3C)') + '"></i></span>'
            + '<span class="vx-opt-dim-v">' + p.v + '/' + p.max + '</span></div>';
        }).join('');
        return '<section class="vx-card vx-mb3" aria-label="LEAPS ' + esc(c.sym) + '">'
          + '<div class="vx-flex" style="justify-content:space-between;align-items:flex-start">'
          + '<div><span class="vx-ticker">' + esc(c.sym) + '</span> <span class="vx-badge" style="color:var(--vx-option,#9B7BFF)">CALL ' + nd(c.strike) + ' · ' + esc(String(c.exp).slice(0, 10)) + '</span>'
          + '<div class="vx-meta vx-mt1">' + esc(kind) + '</div></div>'
          + '<div style="text-align:right"><div class="vx-kpi-label">Compatibilité LEAPS</div>'
          + '<div class="' + toneCls(tone) + '" style="font-size:28px;font-weight:700">' + sc.total + '<small style="font-size:14px">/100</small></div></div></div>'
          + '<div class="vx-opt-dims vx-mt2">' + bars + '</div>'
          + '<div class="vx-card-foot"><span class="vx-meta">Score explicable = somme des composantes réelles ci-dessus (aucun score opaque). '
          + 'Un LEAPS ne se justifie que combiné à une tendance et un catalyseur — la durée ne remplace pas la thèse.</span></div></section>';
      }).join('');
    });
  }

  /* ════════════════ VUE POSITIONS (LOT J/K) — domicile canonique ════════════════ */
  function hasConfirm(t) { var s = t.entrySnap || {}; return !!(s.validated || s.breakout || s.confirmed || s.revalidated); }
  function optNextAction(t) {
    /* GARDE-FOU (Constitution §18) : jamais « renforcer » une option perdante sans
       confirmation positive explicite — et jamais parce que la prime a baissé. */
    if (t.pl != null && t.pl < 0) {
      if (!hasConfirm(t)) return { label: 'Renforcement interdit : aucune confirmation positive détectée', tone: 'neg' };
      return { label: 'Confirmation détectée — renforcement possible seulement après revue (theta/thèse/liquidité)', tone: 'muted' };
    }
    if (t.pl == null) return { label: 'Marque indisponible — conserver, réévaluer avec IBKR', tone: 'muted' };
    if (t.pl >= 100) return { label: 'Gain ≥ +100 % : sécuriser 25-50 % et laisser courir le reste (indicatif)', tone: 'pos' };
    if (t.pl >= 75) return { label: 'Gain ≥ +75 % : réévaluation complète (thèse, catalyseur, theta)', tone: 'pos' };
    if (t.pl >= 50) return { label: 'Gain ≥ +50 % : conserver tant que thèse et catalyseur tiennent', tone: 'pos' };
    if (t.pl >= 30) return { label: 'Gain ≥ +30 % : réévaluer invalidation et risque de temps', tone: 'pos' };
    if (t.pl >= 20) return { label: 'Gain ≥ +20 % : aucune action automatique', tone: 'muted' };
    return { label: 'Conserver — thèse intacte, surveiller le theta', tone: 'muted' };
  }
  var _optQuotes = {};
  var _optQuoteMeta = { ts: null, live: false, fallback: false };   /* cache marques par id — survit aux re-rendus (§ marques n/d honnêtes) */
  function loadPositions() {
    var host = $('vx-op-body'); if (!host) return;
    var E = window.VXEntities;
    var opts = E ? E.positions().filter(function (t) { return t.type !== 'STK'; }) : [];
    if (!opts.length) {
      host.innerHTML = VX.states.empty('Aucune position option déclarée — le sélecteur privilégie les CALLS (max 3, dont 1 PUT tactique).',
        '<a class="vx-btn vx-btn-sm vx-btn-primary" href="/opportunities?view=options">Chercher un contrat</a>');
      return;
    }
    var models = [];
    var body = opts.map(function (t, index) {
      var q = _optQuotes[t.id] || {}; var mark = q.mark != null ? q.mark : null;
      var value = mark != null ? mark * 100 * t.qty : null;
      var pl = (value != null && t.cost) ? (value - t.cost) / t.cost * 100 : null;
      var tt = Object.assign({}, t, { pl: pl });
      var dte = t.exp ? Math.round((new Date(t.exp) - Date.now()) / 86400000) : null;
      var na = optNextAction(tt), s = t.entrySnap || {};
      models.push({ t: t, mark: mark, value: value, pl: pl, dte: dte, action: na, snap: s });
      return '<tr data-option-position="' + index + '" data-clickable tabindex="0">'
        + '<td data-label="Contrat"><span class="vx-table-primary"><strong class="vx-ticker">' + esc(t.sym) + '</strong>'
        + '<span>' + esc(t.type) + ' ' + nd(t.strike) + ' · ' + esc(t.exp || 'échéance n/d') + '</span></span></td>'
        + '<td data-label="Qté" class="vx-num">' + t.qty + '</td>'
        + '<td data-label="Marque" class="vx-num">' + (mark != null ? price(mark) : 'n/d') + '</td>'
        + '<td data-label="P&L %" class="vx-num ' + (pl > 0 ? 'vx-pos' : pl < 0 ? 'vx-neg' : '') + '">' + (pl != null ? num(pl, 1) + ' %' : 'n/d') + '</td>'
        + '<td data-label="DTE" class="vx-num ' + (dte != null && dte <= 7 ? 'vx-warn' : '') + '">' + (dte != null ? dte + ' j' : '—') + '</td>'
        + '<td data-label="Prochaine action" class="' + toneCls(na.tone) + '" style="max-width:230px;font-size:12px">' + esc(na.label) + '</td>'
        + '<td data-label="Détail"><span class="vx-row-open">Ouvrir</span></td></tr>';
    }).join('');
    host.innerHTML = '<div class="vx-insight vx-mb3" data-tone="risk"><b>Règle de sécurité.</b> '
      + 'Une option en perte n’affiche jamais « renforcer » sans confirmation positive du marché.</div>'
      + '<section class="vx-card"><div class="vx-card-header"><span class="vx-card-title">Positions options</span>'
      + '<span class="vx-meta vx-right">' + opts.length + ' · lecture seule — aucun ordre</span></div>'
      + '<div class="vx-table-wrap vx-table-cards"><table class="vx-table"><thead><tr>'
      + '<th>Contrat</th><th class="vx-num">Qté</th><th class="vx-num">Marque</th><th class="vx-num">P&L %</th>'
      + '<th class="vx-num">DTE</th><th>Prochaine action</th><th></th></tr></thead><tbody>' + body + '</tbody></table></div>'
      + '<div class="vx-card-footer"><span class="vx-meta">Marques/Greeks live via IBKR (lecture seule) ; sans IBKR, « n/d » honnête — jamais estimés.</span></div></section>';

  
  /* ── PROVENANCE DU CONTRAT (controle 079) ─────────────────────────────
     « Le drawer contrat expose mark, source, qualite, spread, heure et
     limites. » Les cinq champs etaient DEJA RECUPERES par `/api/pos-quotes`
     — `mark_source`, `spread_pct`, `bid`, `ask`, `ts` — et seul `mark` etait
     lu. Un prix sans son origine ni son heure est un chiffre sans autorite :
     l'ecart avec le releve du courtier reste alors inexplicable.

     Rien n'est calcule ici : chaque valeur vient du serveur telle quelle. */
  var MARQUE_LIB = {
    DERNIER_ECHANGE: 'dernier \u00e9change', MILIEU_FOURCHETTE: 'milieu de fourchette',
    CLOTURE_VEILLE: 'cl\u00f4ture de la veille', ABSENTE: null
  };
  var SPREAD_INCERTAIN = 10;   /* au-dela, toute convention de marque diverge */

  function provenanceContrat(t) {
    var q = _optQuotes[t.id] || {};
    var abs = function (txt) { return '<span class="vx2-absent">' + (txt || 'n/d') + '</span>'; };
    var lignes = [];
    var kv = function (cle, val) {
      lignes.push('<div class="vx-kv"><span>' + cle + '</span><b>' + val + '</b></div>');
    };
    kv('Marque', q.mark != null ? price(q.mark) : abs('aucune cotation'));
    var lib = MARQUE_LIB[q.mark_source];
    kv('Source de la marque', lib ? esc(lib) : abs('convention non renseign\u00e9e'));
    kv('Fourchette', (q.bid != null && q.ask != null)
      ? (price(q.bid) + ' / ' + price(q.ask)) : abs());
    /*  QUALITE : un spread large rend TOUTE marque incertaine. On le dit avec
        un mot, pas seulement avec une couleur.  */
    var sp = q.spread_pct;
    kv('\u00c9cart de fourchette', sp == null ? abs()
      : '<span class="' + (sp >= SPREAD_INCERTAIN ? 'vx-neg' : sp >= 5 ? 'vx-warn' : '') + '">'
        + num(sp, 2) + ' %' + (sp >= SPREAD_INCERTAIN ? ' \u00b7 marque incertaine' : '') + '</span>');
    var heure = _optQuoteMeta.ts;
    kv('Heure de la cotation', heure != null && window.VX && VX.fmt
      ? esc(VX.fmt.ago(heure * 1000)) : abs('non horodat\u00e9e'));
    kv('Mode', _optQuoteMeta.live
      ? '<span class="vx-pos">IBKR temps r\u00e9el</span>'
      : '<span class="vx-warn">Diff\u00e9r\u00e9' + (_optQuoteMeta.fallback ? ' \u00b7 repli' : '') + '</span>');
    return '<div class="vx-card vx-card--compact">'
      + '<div class="vx-card-header"><span class="vx-card-title">Provenance et qualit\u00e9</span></div>'
      + lignes.join('')
      + '<div class="vx-card-footer"><span class="vx-meta">Trois conventions de marque '
      + 'coexistent chez le courtier lui-m\u00eame et ne donnent pas le m\u00eame chiffre. '
      + 'Le libell\u00e9 dit laquelle a servi. Aucune Greek n\u2019est estim\u00e9e : sans grecques '
      + 'de position IBKR, elles restent absentes.</span></div></div>';
  }

  function openPosition(index) {
      var m = models[index]; if (!m || !VX.shell) return;
      var t = m.t, body = '<div class="vx-section-stack">'
        + '<div class="vx-data-ledger"><span>' + esc(t.type || 'Option') + '</span><span>' + esc(t.exp || 'échéance n/d') + '</span><span>Lecture seule</span></div>'
        + '<div class="vx-stats-row">'
        + '<div class="vx-stat"><span class="vx-stat-label">Coût</span><span class="vx-stat-value">' + price(t.cost) + '</span></div>'
        + '<div class="vx-stat"><span class="vx-stat-label">Marque</span><span class="vx-stat-value">' + (m.mark != null ? price(m.mark) : 'n/d') + '</span></div>'
        + '<div class="vx-stat"><span class="vx-stat-label">P&L</span><span class="vx-stat-value ' + (m.pl > 0 ? 'vx-pos' : m.pl < 0 ? 'vx-neg' : '') + '">' + (m.pl != null ? num(m.pl, 1) + ' %' : 'n/d') + '</span></div>'
        + '<div class="vx-stat"><span class="vx-stat-label">DTE</span><span class="vx-stat-value">' + (m.dte != null ? m.dte + ' j' : 'n/d') + '</span></div></div>'
        + '<div class="vx-card vx-card--compact"><div class="vx-card-header"><span class="vx-card-title">Plan de suivi</span></div>'
        + '<div class="vx-kv"><span>Strike</span><b>' + nd(t.strike) + '</b></div>'
        + '<div class="vx-kv"><span>Invalidation</span><b class="vx-neg">' + nd(m.snap.stop) + '</b></div>'
        + '<div class="vx-kv"><span>Action suivante</span><b class="' + toneCls(m.action.tone) + '">' + esc(m.action.label) + '</b></div></div>'
        + provenanceContrat(t)
        + '<p class="vx-meta">La marque reste n/d sans cotation IBKR. Aucun prix n’est estimé.</p></div>';
      var footer = '<a class="vx-btn vx-btn-sm vx-btn-primary" href="/options?view=structure&sym=' + encodeURIComponent(t.sym) + '">Analyser la structure</a>';
      VX.shell.openDrawer(esc(t.sym) + ' · position option', body, { variant: 'summary', footerHtml: footer });
    }
    host.querySelectorAll('[data-option-position]').forEach(function (row) {
      var open = function () { openPosition(Number(row.getAttribute('data-option-position'))); };
      row.addEventListener('click', open);
      row.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
      });
    });
    // marques serveur (best-effort, comme le desk)
    fetch('/api/pos-quotes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ positions: opts.map(function (t) { return { sym: t.sym, exp: t.exp, strike: t.strike, right: t.right }; }) }) })
      .then(function (r) { return r.json(); }).then(function (d) {
        var res = d.results || {}, changed = false;
        /*  La reponse porte l'heure et le mode ; seule la marque etait lue.
            Le controle 079 exige mark, SOURCE, HEURE, QUALITE et LIMITES.  */
        _optQuoteMeta = { ts: d.ts != null ? d.ts : null, live: !!d.live, fallback: !!d.fallback_used };
        /*  BOUCLE INFINIE, corrigee ici. `changed` passait a vrai des que le
            serveur renvoyait UNE cotation, sans regarder si elle differait de
            celle deja en cache. Le re-rendu relance ce meme fetch, qui renvoie
            la meme cotation, qui repasse `changed` a vrai : la page appelait
            `/api/pos-quotes` en boucle, indefiniment.

            Invisible en demo, ou l'endpoint ne renvoie jamais rien — et donc
            jamais declenchee ici. Avec IBKR connecte et une position option,
            elle l'aurait ete a chaque visite. Mesuree en pilotant la page :
            la navigation n'atteignait jamais l'inactivite reseau.

            On ne re-rend que si la cotation a REELLEMENT change.  */
        opts.forEach(function (t) {
          var k = [String(t.sym).toUpperCase(), t.exp || '', (t.strike != null ? t.strike : ''), (t.right || '').toUpperCase()].join('|');
          if (!res[k]) return;
          var avant = _optQuotes[t.id];
          if (avant && JSON.stringify(avant) === JSON.stringify(res[k])) return;
          _optQuotes[t.id] = res[k];
          changed = true;
        });
        if (changed) loadPositions();
      }).catch(function () {});
  }

  /* ── Auto-symbole depuis le board (chips) ── */
  function chips(hostId, inputId, load) {
    var host = $(hostId), input = $(inputId); if (!host || !input) return;
    board().then(function (bd) {
      var syms = Array.from(new Set(bd.map(function (c) { return c.sym; }))).slice(0, 8);
      if (!syms.length) {
        /* Sans tableau d'options, « Depuis le tableau : » suivi de rien est une
           promesse non tenue. On dit la cause, et on laisse la saisie libre. */
        host.innerHTML = '<span class="vx-muted" style="font-size:11px">'
          + 'Aucun sous-jacent dans le tableau d\u2019options : la cha\u00eene n\u2019a pas '
          + '\u00e9t\u00e9 aliment\u00e9e par le dernier scan. Saisis un symbole ci-dessus.</span>';
        return;
      }
      host.innerHTML = '<span class="vx-muted" style="font-size:11px">Depuis le tableau :</span> '
        + syms.map(function (x) { return '<button type="button" class="vx-btn vx-btn-sm vx-btn-ghost" data-osym="' + esc(x) + '">' + esc(x) + '</button>'; }).join('');
      host.addEventListener('click', function (e) { var b = e.target.closest ? e.target.closest('[data-osym]') : null; if (!b) return; input.value = b.getAttribute('data-osym'); try { if (VX.store) VX.store.set('active_ticker', input.value); } catch (x) {} load(input.value); });
      var pre = null; try { pre = new URLSearchParams(location.search).get('sym'); } catch (e2) {}
      if (!input.value && (pre || syms.length)) { input.value = (pre || syms[0]).toUpperCase(); load(input.value); }
    });
  }

  function init() {
    var v = view();
    if (v === 'structure') {
      var go = $('vx-os-go'), inp = $('vx-os-sym');
      if (!go || !inp) return;
      var run = function () { var s = (inp.value || '').trim().toUpperCase(); if (s) loadStructure(s); };
      go.addEventListener('click', run);
      inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') run(); });
      chips('vx-os-chips', 'vx-os-sym', function (s) { loadStructure(s); });
    } else if (v === 'leaps') {
      var g2 = $('vx-lp-go'), i2 = $('vx-lp-sym');
      if (!g2 || !i2) return;
      var run2 = function () { var s = (i2.value || '').trim().toUpperCase(); if (s) loadLeaps(s); };
      g2.addEventListener('click', run2);
      i2.addEventListener('keydown', function (e) { if (e.key === 'Enter') run2(); });
      chips('vx-lp-chips', 'vx-lp-sym', function (s) { loadLeaps(s); });
    } else if (v === 'positions') {
      if (window.VXEntities) loadPositions(); else window.addEventListener('load', loadPositions, { once: true });
      if (VX && VX.bus) VX.bus.on('vx:position-changed', loadPositions);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
