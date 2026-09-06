/* options-intel.js — client de l'espace Options Intelligence (§18).
 * Lit /api/options/* (moteurs purs) et rend chaque interprétation canonique
 * avec son verdict, ses preuves et un tiroir « Comprendre ce graphique ».
 * Aucun chiffre inventé : donnée absente → état honnête. Lecture seule.
 */
(function () {
  'use strict';
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var VXf = (window.VX && VX.fmt) || { nd: function (v) { return v == null ? '—' : v; }, num: function (v) { return v == null ? '—' : v; } };

  // Couleur/label du statut canonique (jamais de bleu — thème Obsidian Copper).
  var ST = {
    FAVORABLE: { cls: 'pos', label: 'Favorable' },
    NEUTRE: { cls: 'neutral', label: 'Neutre' },
    DEFAVORABLE: { cls: 'neg', label: 'Défavorable' },
    BLOQUANT: { cls: 'neg', label: 'Bloquant' },
    INCONNU: { cls: 'neutral', label: 'Inconnu' }
  };
  // dernière interprétation par graphique — pour le tiroir « Comprendre »
  var LAST = {};

  function badge(status) {
    var s = ST[status] || ST.INCONNU;
    return '<span class="vx-badge" data-tone="' + s.cls + '">' + esc(s.label) + '</span>';
  }

  function confHtml(c) {
    if (c == null) return '<span class="vx-muted">confiance n/d</span>';
    return '<span class="vx-muted">confiance ' + Math.round(c * 100) + ' %</span>';
  }

  // Carte de verdict compacte + mémorisation pour le tiroir.
  function verdictCard(interp) {
    if (!interp) return '<div class="vx-empty">Interprétation indisponible.</div>';
    LAST[interp.chart_id] = interp;
    var reading = interp.dominant_reading || 'Donnée insuffisante pour un verdict.';
    return '<div class="vx-verdict" data-status="' + esc(interp.status) + '">' +
      '<div class="vx-flex" style="gap:.6rem;align-items:center;margin-bottom:.5rem">' +
      badge(interp.status) + confHtml(interp.confidence) +
      (interp.source ? '<span class="vx-muted">· ' + esc(interp.source) + '</span>' : '') +
      '</div>' +
      '<p class="vx-lead">' + esc(reading) + '</p>' +
      '<p class="vx-sub">' + esc(interp.strategy_impact || '') + '</p>' +
      evidenceHtml(interp) +
      (interp.as_of ? '<div class="vx-table-stamp"><span>Source <b>' + esc(interp.source || 'scan') + '</b> · ' + esc(interp.as_of) + '</span></div>' : '') +
      '</div>';
  }
  // Preuves pour / contre, en clair sous la lecture (le tiroir garde le détail).
  function evidenceHtml(interp) {
    var pos = interp.positive_evidence || [], neg = interp.negative_evidence || [];
    if (!pos.length && !neg.length) return '';
    var li = function (arr, tone) { return arr.map(function (x) { return '<li data-tone="' + tone + '">' + esc(x) + '</li>'; }).join(''); };
    return '<ul class="vx-verdict-evidence">' + li(pos, 'pos') + li(neg, 'neg') + '</ul>';
  }

  // Tiroir « Comprendre ce graphique » — question, preuves, incertitudes, limites.
  function explainDrawer(interp) {
    if (!interp) { if (window.VX && VX.toast) VX.toast('Rien à expliquer pour l’instant', 'info'); return; }
    var li = function (arr) {
      if (!arr || !arr.length) return '<li class="vx-muted">—</li>';
      return arr.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('');
    };
    var html = '<div class="vx-explain">' +
      '<h3>' + esc(interp.question) + '</h3>' +
      '<p class="vx-lead">' + badge(interp.status) + ' ' + esc(interp.dominant_reading || '—') + '</p>' +
      '<div class="vx-grid2">' +
      '<div><h4>Ce qui soutient</h4><ul>' + li(interp.positive_evidence) + '</ul></div>' +
      '<div><h4>Ce qui pèse contre</h4><ul>' + li(interp.negative_evidence) + '</ul></div>' +
      '</div>' +
      '<h4>Incertitudes</h4><ul>' + li(interp.uncertainties) + '</ul>' +
      '<h4>Impact stratégique</h4><p>' + esc(interp.strategy_impact || '—') + '</p>' +
      '<h4>Limites méthodologiques</h4><ul>' + li(interp.limitations) + '</ul>' +
      '<p class="vx-muted">Source : ' + esc(interp.source || 'n/d') +
      ' · Donnée : ' + esc(interp.as_of || 'n/d') + '</p>' +
      '</div>';
    if (window.VX && VX.drawer && VX.drawer.open) { VX.drawer.open('Comprendre ce graphique', html); }
    else if (window.VX && VX.shell && VX.shell.openDrawer) { VX.shell.openDrawer('Comprendre', html); }
    else { showFallbackModal(html); }
  }

  function showFallbackModal(html) {
    var host = document.getElementById('vx-opt-modal');
    if (!host) {
      host = document.createElement('div'); host.id = 'vx-opt-modal';
      host.style.cssText = 'position:fixed;inset:0;background:rgba(8,8,8,.72);z-index:70;display:flex;align-items:center;justify-content:center;padding:1rem';
      host.addEventListener('click', function (e) { if (e.target === host) host.remove(); });
      document.body.appendChild(host);
    }
    host.innerHTML = '<div class="vx-card" style="max-width:640px;max-height:82vh;overflow:auto;padding:1.2rem">' +
      html + '<div style="margin-top:1rem;text-align:right"><button class="vx-btn vx-btn-sm" id="vx-opt-modal-x">Fermer</button></div></div>';
    var x = document.getElementById('vx-opt-modal-x');
    if (x) x.addEventListener('click', function () { host.remove(); });
  }

  // Squelette à la hauteur RÉSERVÉE de la zone (CLS) : le contenu remplace un
  // bloc de même taille au lieu de faire sauter la page.
  function loading(el, h) {
    if (!el) return;
    var inner = (window.VX && VX.states) ? VX.states.loading(3) : 'Chargement…';
    el.innerHTML = h ? '<div aria-busy="true" style="min-height:' + h + 'px">' + inner + '</div>' : inner;
  }
  function fail(el, cause) {
    if (el) el.innerHTML = (window.VX && VX.states)
      ? VX.states.error(cause) : '<div class="vx-error-banner">' + esc(cause) + '</div>';
  }

  function get(url) {
    return (window.VX && VX.fetch) ? VX.fetch(url, { ttl: 15000 })
      : fetch(url).then(function (r) { return r.json(); });
  }

  // ── Vue d'ensemble — carte d'environnement ─────────────────────────
  // Libellé MOTEUR de l'environnement (PORTEUR / MITIGE / HOSTILE) : le mot
  // affiché est celui du moteur, jamais une relecture par seuils côté client.
  var ENV = {
    PORTEUR: { tone: 'pos', label: 'Porteur' },
    MITIGE: { tone: 'warn', label: 'Mitigé' },
    HOSTILE: { tone: 'neg', label: 'Hostile' }
  };
  function envBadge(label) {
    var e = ENV[label];
    if (!e) return '<span class="vx-badge" data-tone="neutral">' + esc(label || 'Inconnu') + '</span>';
    return '<span class="vx-badge" data-tone="' + e.tone + '">' + e.label + '</span>';
  }
  function envTone(label) { var e = ENV[label]; return e ? e.tone : 'neutral'; }

  // Jauge d'environnement + dimensions (OPTIONS HERO §14). Chaque dimension
  // rend libellé | barre | valeur | note. Une dimension NON MESURÉE n'a pas de
  // barre remplie (absence ≠ zéro) et dit pourquoi avec la note du moteur.
  function heroHtml(env, demo) {
    if (!env || env.score == null) {
      LAST['options.environment'] = env && env.interpretation;
      return (window.VX && VX.states)
        ? VX.states.empty('Aucune dimension mesurable dans ce scan.', '', { title: 'Environnement non calculable' })
        : '<div class="vx-empty">Environnement non calculable : aucune dimension mesurable.</div>';
    }
    LAST['options.environment'] = env.interpretation;
    var it = env.interpretation || {};
    var cov = env.data_coverage || {};
    var known = env.dimensions_known != null ? env.dimensions_known : cov.known_dimensions;
    var total = env.dimensions_total != null ? env.dimensions_total : cov.total_dimensions;
    var dims = (env.dimensions || []).map(function (d) {
      var w = (d.known && d.score != null) ? Math.round(d.score) : null;
      var note = d.note ? esc(d.note) : '';
      return '<div class="vx-opt-dim" data-state="' + (w == null ? 'missing' : 'known') + '">' +
        '<span class="vx-opt-dim-l">' + esc(d.label) + '</span>' +
        '<span class="vx-opt-dim-bar" aria-hidden="true">' + (w == null ? '' : '<i style="width:' + w + '%"></i>') + '</span>' +
        '<span class="vx-opt-dim-v">' + (w == null ? '—' : w) + '</span>' +
        '<span class="vx-opt-dim-n">' + (w == null ? 'non mesuré' + (note ? ' · ' + note : '') : note) + '</span></div>';
    }).join('');
    var coverage = '';
    if (known != null && total != null) {
      var partial = known < total;
      coverage = '<span class="vx2-badge" data-state="' + (partial ? 'partial' : 'live') + '">' +
        (partial ? 'Partielle' : 'Complète') + ' · ' + known + '/' + total + ' dimensions mesurées</span>';
    }
    return (demo ? '<div class="vx-demo-tag">Données de démonstration</div>' : '') +
      '<div class="vx-opt-hero-grid">' +
      '<div class="vx-opt-gauge">' +
      '<div id="vx-opt-gauge-radial" data-score="' + Math.round(env.score) + '"></div>' +
      '<div class="vx-opt-coverage">' + envBadge(env.label) + coverage + confHtml(it.confidence) + '</div></div>' +
      '<div class="vx-opt-dims">' + dims + '</div></div>' +
      (cov.note ? '<p class="vx-meta vx-mt2">' + esc(cov.note) + '</p>' : '');
  }
  function mountEnvGauge(env) {
    if (!env || !window.VXCharts || !VXCharts.gauge) return;
    var el = document.getElementById('vx-opt-gauge-radial'); if (!el) return;
    var s = Math.round(env.score || 0);
    var it = env.interpretation || {};
    var cc = VXCharts.colors || {};
    var tone = envTone(env.label);
    var color = tone === 'pos' ? cc.positive : tone === 'neg' ? cc.negative : cc.warning;
    // Une seule bande, colorée par le libellé MOTEUR : aucun seuil recodé ici.
    VXCharts.gauge(el, { value: s, min: 0, max: 100, unit: ' /100', label: 'environnement',
      reading: it.dominant_reading || '', bands: [{ to: 100, color: color || cc.neutral }] });
  }

  // ── Vue d'ensemble ────────────────────────────────────────────────
  function loadOverview() {
    var hEl = document.getElementById('vx-opt-hero-body');
    var cEl = document.getElementById('vx-opt-counters-body');
    var vEl = document.getElementById('vx-opt-verdict-body');
    var rEl = document.getElementById('vx-opt-radar-lite-body');
    loading(hEl, 220); loading(cEl, 110); loading(vEl, 220); loading(rEl, 300);
    get('/api/options/overview').then(function (d) {
      if (!d || d.empty) {
        var msg = (window.VX && VX.states) ? VX.states.empty('Aucun contrat dans le tableau (scan vide ou hors séance).') : 'Aucune donnée.';
        if (hEl) { hEl.innerHTML = heroHtml(d && d.environment, d && d.demo); mountEnvGauge(d && d.environment); }
        if (cEl) cEl.innerHTML = msg;
        if (vEl) vEl.innerHTML = verdictCard(d && d.interpretation);
        // Vider en silence laissait une carte titree « Meilleurs contrats
        // (radar) » sans une ligne dessous : un titre qui promet et ne rend
        // rien. L'absence est nommee, avec sa cause.
        if (rEl) rEl.innerHTML = (window.VX && VX.states)
          ? VX.states.empty('Aucun contrat à classer : le radar lit le même '
            + 'tableau d’options, vide lui aussi.')
          : 'Aucun contrat à classer.';
        return;
      }
      var c = d.counters || {};
      if (hEl) { hEl.innerHTML = heroHtml(d.environment, d.demo); mountEnvGauge(d.environment); }
      if (cEl) cEl.innerHTML = countersHtml(c, d.demo, d.as_of, d.option_pulse, d.volatility_pulse);
      if (vEl) vEl.innerHTML = verdictCard(d.interpretation);
      if (rEl) rEl.innerHTML = radarTable((d.radar || []).slice(0, 6), { asOf: d.as_of, total: c.total, shown: Math.min(6, (d.radar || []).length) });
    }).catch(function (e) {
      var cause = 'Chargement de la vue d’ensemble : ' + e.message;
      [hEl, cEl, vEl, rEl].forEach(function (el) { fail(el, cause); });
    });
  }

  // Tuile de métrique canonique (kit .vx-metric via VX.tile.metric) avec une
  // ligne de contexte (`meta`). Repli « — » honnête si la valeur manque.
  function kpi(k, v, unit, tone, meta, bar) {
    if (window.VX && VX.tile) return VX.tile.metric({ k: k, v: v, unit: unit, tone: tone, meta: meta, bar: bar });
    return '<div class="vx-metric" data-tone="' + (v == null ? '' : (tone || '')) + '"><span class="vx-metric-k">' + esc(k) + '</span>' +
      '<span class="vx-metric-v">' + (v == null ? '—' : v) + (unit ? '<span class="vx-metric-u">' + unit + '</span>' : '') + '</span>' +
      (meta ? '<span class="vx-metric-meta">' + esc(meta) + '</span>' : '') + '</div>';
  }

  // Répartition CALL vs PUT en barre empilée. CALL = argent, PUT = violet :
  // un type de contrat n'est ni un gain ni une perte (le vert/rouge reste aux
  // valeurs signées). Aucune consigne de stratégie dans une légende de donnée.
  function callPutBar(calls, puts, ratio) {
    var t = (calls || 0) + (puts || 0); if (!t) return '';
    var cp = Math.round((calls || 0) / t * 100), pp = 100 - cp;
    return '<div class="vx-mt3" role="img" aria-label="CALLS ' + (calls || 0) + ' contre PUTS ' + (puts || 0) + ', ' + cp + ' % de calls">' +
      '<div class="vx-stackbar-legend" style="justify-content:space-between;margin-bottom:6px">' +
      '<span><i class="vx-swatch--call"></i>CALLS ' + VXf.nd(calls) + ' <b>' + cp + ' %</b></span>' +
      '<span class="vx-muted">Dominante : ' + ((calls || 0) >= (puts || 0) ? 'CALLS' : 'PUTS') +
      (ratio != null ? ' · ratio C/P ' + VXf.num(ratio, 1) : '') + '</span>' +
      '<span><i class="vx-swatch--put"></i>PUTS ' + VXf.nd(puts) + ' <b>' + pp + ' %</b></span></div>' +
      '<div class="vx-stackbar vx-stackbar--options"><i data-side="call" style="width:' + cp + '%"></i><i data-side="put" style="width:' + pp + '%"></i></div></div>';
  }

  var VOL_STATE = { EXPANSION: 'en expansion', COMPRESSION: 'en compression', STABLE: 'stable', NEUTRE: 'neutre' };
  var BAND = { FAIBLE: ['faible', 'neg'], MOYEN: ['moyenne', 'warn'], BON: ['bonne', 'pos'], BONNE: ['bonne', 'pos'], ELEVE: ['élevée', 'pos'], HAUT: ['haute', 'pos'] };

  // Bande de six indicateurs : chaque chiffre porte son contexte (population,
  // dispersion, bande moteur) au lieu de le répéter dans d'autres cartes.
  function countersHtml(c, demo, asOf, op, vp) {
    op = op || {}; vp = vp || {};
    var band = BAND[String(c.quality_band || '').toUpperCase()];
    var ivMeta = [];
    if (vp.median_iv != null) ivMeta.push('médiane ' + VXf.num(vp.median_iv, 1) + ' %');
    if (vp.min_iv != null && vp.max_iv != null) ivMeta.push(VXf.num(vp.min_iv, 1) + '–' + VXf.num(vp.max_iv, 1) + ' %');
    if (vp.state) ivMeta.push(VOL_STATE[String(vp.state).toUpperCase()] || String(vp.state).toLowerCase());
    var dteMeta = op.avg_theta_burn != null ? 'theta moy. ' + VXf.num(op.avg_theta_burn, 2) + ' %/j de prime' : '';
    return (demo ? '<div class="vx-demo-tag">Données de démonstration</div>' : '') +
      '<div class="vx-metricgrid vx-opt-kpis">' +
      kpi('Contrats', VXf.nd(c.total), '', '',
        (c.symbols != null ? c.symbols + ' titres' : '') + (c.avg_oi != null ? ' · OI moy. ' + VXf.num(c.avg_oi, 0) : '')) +
      kpi('CALLS / PUTS', (c.calls != null && c.puts != null) ? VXf.nd(c.calls) + ' / ' + VXf.nd(c.puts) : null, '', '',
        op.call_put_ratio != null ? 'ratio C/P ' + VXf.num(op.call_put_ratio, 1) : '') +
      kpi('IV moyenne', c.avg_iv != null ? VXf.num(c.avg_iv, 1) : null, '%', '', ivMeta.join(' · ')) +
      kpi('Qualité moy.', c.avg_quality != null ? VXf.num(c.avg_quality, 0) : null, '/100', band ? band[1] : '',
        band ? 'bande moteur : ' + band[0] : (c.quality_band ? 'bande : ' + String(c.quality_band).toLowerCase() : ''), c.avg_quality) +
      kpi('Spread moy.', c.avg_spread_pct != null ? VXf.num(c.avg_spread_pct, 1) : null, '%', '',
        c.avg_spread_pct != null ? 'moyenne des spreads cotés' : 'non disponible sur ce scan') +
      kpi('DTE moy.', op.avg_dte != null ? Math.round(op.avg_dte) : null, ' j', '', dteMeta) +
      '</div>' +
      callPutBar(c.calls, c.puts, op.call_put_ratio) +
      (asOf ? '<div class="vx-table-stamp"><span>Source <b>scan</b> · ' + esc(asOf) + '</span></div>' : '');
  }

  // Suivi hypothétique d'un contrat : référence = prime par action (cost/100).
  window.__optFollow = function (btn) {
    var d = btn.dataset;
    var mark = d.cost ? Number(d.cost) / 100 : null;
    if (mark == null || !isFinite(mark)) { if (window.VX && VX.toast) VX.toast('Prime indisponible — suivi impossible', 'error'); return; }
    btn.setAttribute('data-state', 'loading'); btn.disabled = true;
    fetch('/api/tracking', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entity_type: 'OPTION', symbol: d.sym, contract_id: d.cid, mark: mark, decision: 'SURVEILLER' })
    }).then(function () { if (window.VX && VX.toast) VX.toast('Contrat ' + d.sym + ' suivi (hypothétique)', 'success'); setTimeout(function () { location.href = '/tracking'; }, 700); })
      .catch(function () { btn.removeAttribute('data-state'); btn.disabled = false; if (window.VX && VX.toast) VX.toast('Suivi impossible', 'error'); });
  };

  // Cellule micro-barre (qualité, PoP…) : builder partagé VX.tile.microbar —
  // le chiffre porte le sens, la barre est un repère. Seuils inchangés (66/45).
  function microBar(val, unit, tone, label) {
    var td = '<td class="vx-num"' + (label ? ' data-label="' + esc(label) + '"' : '') + '>';
    if (val == null || isNaN(val)) return td + '<span class="vx2-absent">—</span></td>';
    var html = (window.VX && VX.tile && VX.tile.microbar)
      ? VX.tile.microbar({ v: val, unit: unit, tone: tone })
      : '<b class="vx-mono">' + Math.round(val) + (unit || '') + '</b>';
    return td + html + '</td>';
  }
  function qualityTone(q) { return q == null ? '' : q >= 66 ? 'pos' : q >= 45 ? 'warn' : 'neg'; }
  function dateFr(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
    return m ? m[3] + '/' + m[2] + '/' + m[1] : (iso || '—');
  }
  var BUCKET = { long: 'longue', moyen: 'moyenne', court: 'courte', tactique: 'tactique' };

  // Table des meilleurs contrats. Colonnes numériques alignées à droite en
  // mono, échéance en date, action nommée (« Suivre NVDA CALL 230 · 19/03/2027 »),
  // population et source sous la table — jamais une liste tronquée en silence.
  function radarTable(rows, opts) {
    opts = opts || {};
    if (!rows || !rows.length) return '<div class="vx-empty">Aucun contrat de qualité mesurable.</div>';
    var body = rows.map(function (r) {
      var cid = [r.sym, r.exp || '', r.strike != null ? r.strike : '', r.type === 'PUT' ? 'P' : 'C'].join('|');
      var name = esc(r.sym) + ' ' + esc(r.type || '') + ' ' + VXf.nd(r.strike) + (r.exp ? ' · ' + dateFr(r.exp) : '');
      var follow = r.cost != null ? '<button class="vx-btn vx-btn-sm vx-btn-ghost" data-sym="' + esc(r.sym) +
        '" data-cid="' + esc(cid) + '" data-cost="' + esc(r.cost) + '" aria-label="Suivre ' + name + '" onclick="window.__optFollow(this)">Suivre</button>'
        : '<span class="vx-muted" title="Prime indisponible">—</span>';
      return '<tr><td data-label="Titre"><span class="vx-ticker">' + esc(r.sym) + '</span></td>' +
        '<td data-label="Type">' + esc(r.type || '') + '</td>' +
        '<td data-label="Échéance"><span class="vx-table-primary"><strong>' + esc(dateFr(r.exp)) + '</strong>' +
        (r.bucket ? '<span>' + esc(BUCKET[r.bucket] || r.bucket) + '</span>' : '') + '</span></td>' +
        '<td data-label="DTE" class="vx-num">' + (r.dte != null ? r.dte + ' j' : '—') + '</td>' +
        '<td data-label="Strike" class="vx-num">' + (r.strike != null ? VXf.num(r.strike, r.strike % 1 ? 2 : 0) : '—') + '</td>' +
        '<td data-label="IV" class="vx-num">' + (r.iv != null ? VXf.num(r.iv, 1) + ' %' : '—') + '</td>' +
        '<td data-label="Coût" class="vx-num">' + (r.cost != null ? VXf.num(r.cost, 0) + ' $' : '—') + '</td>' +
        microBar(r.quality, '', qualityTone(r.quality), 'Qualité') +
        microBar(r.pop, ' %', 'opt', 'PoP') +
        '<td data-label="Suivi">' + follow + '</td></tr>';
    }).join('');
    var stamp = '';
    if (opts.asOf || opts.total != null) {
      stamp = '<div class="vx-table-stamp">' +
        (opts.shown != null && opts.total != null ? '<span><b>' + opts.shown + '</b> contrats affichés sur ' + opts.total + ', classés par qualité décroissante</span>' : '') +
        (opts.asOf ? '<span>Source <b>scan</b> · ' + esc(opts.asOf) + '</span>' : '') +
        '<span>PoP : probabilité de profit estimée par le moteur</span></div>';
    }
    return '<div class="vx-table-wrap vx-table-cards"><table class="vx-table"><caption class="vx2-sr-only">Meilleurs contrats du tableau d’options</caption><thead><tr>' +
      '<th scope="col">Titre</th><th scope="col">Type</th><th scope="col">Échéance</th><th scope="col" class="vx-num">DTE</th>' +
      '<th scope="col" class="vx-num">Strike</th><th scope="col" class="vx-num">IV</th><th scope="col" class="vx-num">Coût</th>' +
      '<th scope="col" class="vx-num" title="Qualité moteur 0–100">Qualité</th><th scope="col" class="vx-num" title="Probabilité de profit estimée">PoP (est.)</th>' +
      '<th scope="col"><span class="vx2-sr-only">Suivi</span></th></tr></thead><tbody>' + body + '</tbody></table></div>' + stamp;
  }

  // Nuage qualité × probabilité de profit : chaque contrat placé par sa qualité (X)
  // et sa PoP (Y) ; taille = IV (convexité), violet = PUT / acier = CALL. Le coin
  // haut-droit = contrats de qualité ET à forte probabilité. Données réelles /api.
  function radarScatter(hostId, rows) {
    var host = document.getElementById(hostId);
    if (!host || !window.VXCharts || !window.Chart) { if (host) host.innerHTML = ''; return; }
    var cc = VXCharts.colors;
    var pts = (rows || []).filter(function (r) { return r.quality != null && r.pop != null; }).map(function (r) {
      return { x: +r.quality, y: +r.pop, sym: r.sym, type: r.type, iv: r.iv, r: 4 + Math.min(9, (r.iv || 30) / 12) };
    });
    if (pts.length < 2) { host.innerHTML = ''; return; }
    var cfg = {
      type: 'scatter', data: { datasets: [{ data: pts,
        pointRadius: function (ctx) { return ctx.raw ? ctx.raw.r : 5; }, pointHoverRadius: 11,
        pointBackgroundColor: function (ctx) { var p = ctx.raw; return p && p.type === 'PUT' ? cc.violet : cc.neutral; },
        pointBorderColor: 'rgba(0,0,0,.4)', pointBorderWidth: 1 }] },
      options: { scales: {
        x: { title: { display: true, text: 'Qualité du contrat' }, grid: { color: 'rgba(255,255,255,.06)' } },
        y: { title: { display: true, text: 'Probabilité de profit (%)' }, grid: { color: 'rgba(255,255,255,.06)' } } },
        plugins: { tooltip: { callbacks: { label: function (it) { var p = it.raw;
          return p.sym + ' ' + (p.type || '') + ' — qualité ' + Math.round(p.x) + ' · PoP ' + Math.round(p.y) + '% · IV ' + (p.iv != null ? Math.round(p.iv) + '%' : 'n/d'); } } } } }
    };
    host.innerHTML = '<div class="vx-chart-body" style="--vx-chart-h:320px;height:var(--vx-chart-h)"><canvas id="' + hostId + '-cv"></canvas></div>' +
      '<div class="vx-chart-legend"><span><span class="vx-swatch" style="background:' + cc.neutral + '"></span>CALL</span>' +
      '<span><span class="vx-swatch" style="background:' + cc.violet + '"></span>PUT</span>' +
      '<span class="vx-meta">taille = IV (convexité) · haut-droit = qualité ET probabilité</span></div>';
    VXCharts.mount(document.getElementById(hostId + '-cv'), cfg);
  }

  function loadRadar() {
    var el = document.getElementById('vx-opt-radar-body');
    loading(el);
    get('/api/options/overview').then(function (d) {
      if (!d || d.empty) { el.innerHTML = (window.VX && VX.states) ? VX.states.empty('Tableau d’options vide.') : 'Aucune donnée.'; return; }
      el.innerHTML = '<div id="vx-opt-radar-scatter" class="vx-mb3"></div>' + radarTable(d.radar || []);
      radarScatter('vx-opt-radar-scatter', d.radar || []);
    }).catch(function (e) { fail(el, e.message); });
  }

  // ── Volatilité par titre ──────────────────────────────────────────
  function loadVolatility(sym) {
    var el = document.getElementById('vx-opt-vol-out-body');
    if (!sym) { el.innerHTML = '<div class="vx-empty">Saisis un symbole.</div>'; return; }
    try { if (VX.store) VX.store.set('active_ticker', sym); } catch (e0) {}
    loading(el);
    get('/api/options/volatility/' + encodeURIComponent(sym)).then(function (d) {
      var interp = d && d.interpretation;
      el.innerHTML = verdictCard(interp) +
        '<div class="vx-muted" style="margin-top:.6rem">Contrats analysés : ' + VXf.nd(d && d.contracts) +
        (d && d.current_iv != null ? ' · IV médiane ' + VXf.num(d.current_iv * 100, 1) + ' %' : '') + '</div>' +
        /* `iv_rank_note` est servi par la route et n’était lu par AUCUNE page :
           l’absence d’IV rank restait expliquée dans le JSON seulement. */
        (d && d.iv_rank_note ? '<div class="vx-muted" style="margin-top:.35rem">' + esc(d.iv_rank_note) + '</div>' : '');
    }).catch(function (e) { fail(el, e.message); });
    renderVolCharts(sym);
  }

  // ── Graphiques interactifs de volatilité (§15) ────────────────────
  function clearChart(id) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = '';
    return el;
  }

  /* ── TABLE EQUIVALENTE (controle 080) ──────────────────────────────────
     Le contrat exige que TermStructure et SmileSkew portent « des lignes
     precises AVEC table equivalente ». Un graphique seul exclut la lecture
     au lecteur d'ecran, le zoom fort, l'impression et la copie d'un chiffre.

     L'unite vit dans l'EN-TETE, jamais repetee dans chaque cellule, et la
     table ne recalcule RIEN : elle rend les memes nombres que la courbe. */
  function tableEquivalente(hostId, opts) {
    var hote = document.getElementById(hostId);
    if (!hote || !opts || !opts.lignes || !opts.lignes.length) return;
    var ths = opts.colonnes.map(function (c) {
      return '<th' + (c.num ? ' class="vx2-num"' : '') + ' scope="col">' + esc(c.titre)
        + (c.unite ? ' <span class="vx2-th-unit">' + esc(c.unite) + '</span>' : '') + '</th>';
    }).join('');
    var trs = opts.lignes.map(function (l) {
      return '<tr>' + l.map(function (cel, i) {
        var c = opts.colonnes[i] || {};
        return '<td' + (c.num ? ' class="vx2-num"' : '') + '>' + cel + '</td>';
      }).join('') + '</tr>';
    }).join('');
    var det = document.createElement('details');
    det.className = 'vx2-table-equivalente';
    det.innerHTML = '<summary>' + esc(opts.titre) + ' — les mêmes chiffres en table</summary>'
      + '<div class="vx2-table-wrap"><table class="vx2-table"><caption class="vx2-sr-only">'
      + esc(opts.legende || opts.titre) + '</caption><thead><tr>' + ths + '</tr></thead>'
      + '<tbody>' + trs + '</tbody></table></div>'
      + (opts.note ? '<p class="vx2-stamp">' + esc(opts.note) + '</p>' : '');
    hote.appendChild(det);
  }

  /* L'horodatage REEL vit dans `interpretation.as_of` ; `vol_charts.build` ne
     le remonte pas a la racine. Les quatre cartes passaient donc `d.as_of`,
     c'est-a-dire `undefined`, a leur pied de page — un age promis, jamais
     rendu. On lit la ou il est. */
  function volTs(d) {
    return (d && d.interpretation && d.interpretation.as_of) || (d && d.as_of) || null;
  }

  var _charts = [];
  function destroyCharts() { _charts.forEach(function (c) { try { c && c.destroy && c.destroy(); } catch (e) { } }); _charts = []; }

  function renderVolCharts(sym) {
    var VC = window.VXCharts;
    var ids = ['vx-opt-term', 'vx-opt-cone', 'vx-opt-oi', 'vx-opt-smile'];
    ids.forEach(function (id) { var e = clearChart(id); if (e) e.innerHTML = '<div class="vx-skeleton" style="height:240px"></div>'; });
    if (!VC || !window.Chart) { ids.forEach(function (id) { var e = document.getElementById(id); if (e) e.innerHTML = '<div class="vx-empty">Moteur graphique indisponible.</div>'; }); return; }
    destroyCharts();
    get('/api/options/vol-charts/' + encodeURIComponent(sym)).then(function (d) {
      if (!d || d.empty) {
        ids.forEach(function (id) { var e = document.getElementById(id); if (e) e.innerHTML = (window.VX && VX.states) ? VX.states.empty('Aucun contrat pour ' + esc(sym) + ' dans le tableau.') : 'Aucune donnée.'; });
        return;
      }
      /*  La barre de contexte doit dater la donnee REELLEMENT affichee, pas le
          scan global : sur cette vue, ce sont les graphiques de volatilite.  */
      if (window.VX && VX.bus) VX.bus.emit('vx:options-fresh', { ts: volTs(d), contracts: d.contracts });
      chartTerm(VC, d);
      chartCone(VC, d);
      chartOI(VC, d);
      chartSmile(VC, d);
    }).catch(function (e) {
      ids.forEach(function (id) { var el = document.getElementById(id); if (el) el.innerHTML = '<div class="vx-error-banner">⚠ ' + esc(e.message) + '</div>'; });
    });
  }

  function col(VC, name, fallback) { return (VC.colors && VC.colors[name]) || fallback; }

  function spotLinePlugin(spot, label) {
    return {
      id: 'vxSpotLine' + String(spot).replace(/[^0-9]/g, ''),
      afterDatasetsDraw: function (chart) {
        if (spot == null || !chart.scales || !chart.scales.x) return;
        var labels = chart.data.labels || [], nearest = -1, distance = Infinity;
        labels.forEach(function (value, index) {
          var delta = Math.abs(Number(value) - Number(spot));
          if (isFinite(delta) && delta < distance) { distance = delta; nearest = index; }
        });
        if (nearest < 0) return;
        var x = chart.scales.x.getPixelForValue(nearest), area = chart.chartArea;
        if (!isFinite(x) || !area) return;
        var ctx = chart.ctx; ctx.save();
        ctx.strokeStyle = col(window.VXCharts || {}, 'brand', 'rgb(210,138,84)');
        ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(x, area.top); ctx.lineTo(x, area.bottom); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle = col(window.VXCharts || {}, 'muted', 'rgb(152,144,146)');
        ctx.font = '11px JetBrains Mono'; ctx.textAlign = 'center';
        ctx.fillText(label || ('Spot ' + spot), x, area.top + 12); ctx.restore();
      },
    };
  }

  // Structure par terme de l'IV — line, une série (marque).
  function chartTerm(VC, d) {
    var pts = (d.term_structure && d.term_structure.points) || [];
    if (pts.length < 2) { (document.getElementById('vx-opt-term')||{}).innerHTML = '<div class="vx-card"><div class="vx-empty">Structure par terme : pas assez d’échéances.</div></div>'; return; }
    var brand = col(VC, 'brand', '#c9cdd4');
    var slope = d.term_structure.slope;
    var concl = slope == null ? '' : slope > 0.02 ? 'Contango — court terme meilleur marché' : slope < -0.02 ? 'Inversée — stress court terme' : 'Structure plate';
    var c = VC.card('vx-opt-term', {
      title: 'Structure par terme de l’IV', question: 'L’IV monte-t-elle ou baisse-t-elle avec l’échéance ?',
      conclusion: concl, variant: 'hero', height: 360, source: 'SCAN', timestamp: volTs(d), mode: 'delayed',
      limits: 'IV ATM approximée par le contrat le plus proche du spot',
      explain: { shows: 'IV ATM par échéance (DTE).', why: 'Une structure inversée signale un stress/événement de court terme (crush probable).', confirm: 'Pente positive et régulière.', invalidate: 'Pente fortement négative.' },
      render: function (canvas) {
        return VC.mount(canvas, {
          type: 'line',
          data: { labels: pts.map(function (p) { return p.dte + ' j'; }),
            datasets: [{ label: 'IV ATM', data: pts.map(function (p) { return +(p.iv * 100).toFixed(1); }),
              borderColor: brand, backgroundColor: brand + '18', borderWidth: 2, pointRadius: 2, pointHoverRadius: 6, tension: 0, fill: true }] },
          options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: { callbacks: { label: function (ctx) { return 'IV ' + ctx.parsed.y + ' %'; } } } },
            scales: {
              x: { title: { display: true, text: 'Échéance (DTE)' } },
              y: { title: { display: true, text: 'Volatilité implicite (%)' }, ticks: { callback: function (v) { return v + ' %'; } } },
            } } });
      } });
    _charts.push(c);
    tableEquivalente('vx-opt-term', {
      titre: 'Structure par terme de l\u2019IV',
      legende: 'Volatilit\u00e9 implicite ATM par \u00e9ch\u00e9ance, et le strike retenu pour chacune.',
      colonnes: [{ titre: '\u00c9ch\u00e9ance', unite: '(jours)', num: true },
                 { titre: 'IV ATM', unite: '(%)', num: true },
                 { titre: 'Strike retenu', unite: '', num: true }],
      lignes: pts.map(function (p) {
        return [String(p.dte), VXf.num(p.iv * 100, 1), VXf.nd(p.strike)];
      }),
      note: 'IV ATM approxim\u00e9e par le contrat le plus proche du spot \u00b7 '
        + (slope == null ? 'pente non calculable' : 'pente ' + VXf.num(slope, 4))
        + ' \u00b7 source SCAN.'
    });
  }

  // Cône de mouvement attendu — bandes 1σ/2σ (fill entre datasets).
  function chartCone(VC, d) {
    var pts = (d.expected_move_cone && d.expected_move_cone.points) || [];
    if (pts.length < 2) { (document.getElementById('vx-opt-cone')||{}).innerHTML = '<div class="vx-card"><div class="vx-empty">Cône : pas assez d’échéances.</div></div>'; return; }
    var brand = col(VC, 'brand', '#c9cdd4'), copper = col(VC, 'copper', '#6d746e');
    var labels = pts.map(function (p) { return p.dte + ' j'; });
    /* GRAMMAIRE TV (lot 203) : les bandes 1σ/2σ sont une ESTIMATION
       lognormale → remplissage HACHURÉ (C.hatchPattern, lot 197) comme le
       cône de projection et le payoff. Repli translucide si absent. */
    var h1 = VC.hatchPattern ? VC.hatchPattern(brand) : brand + '20';
    var h2 = VC.hatchPattern ? VC.hatchPattern(copper) : copper + '18';
    var ds = function (key, w, fill, bg) {
      return { data: pts.map(function (p) { return p[key]; }), borderColor: w ? copper : 'transparent', borderWidth: w, pointRadius: 0, fill: fill, backgroundColor: bg, tension: .25 };
    };
    var c = VC.card('vx-opt-cone', {
      title: 'Cône de mouvement attendu', question: 'Jusqu’où le sous-jacent peut-il bouger, à 1σ et 2σ ?',
      conclusion: 'Estimation lognormale · spot ' + VXf.nd(d.spot), height: 240, source: 'SCAN', timestamp: volTs(d), mode: 'delayed',
      limits: 'σ = spot · IV_ATM · √(DTE/365) — estimation lognormale',
      legend: [{ label: '1σ', color: brand }, { label: '2σ', color: copper }],
      explain: { shows: 'Fourchette probable du spot par échéance (±1σ, ±2σ).', why: 'Situe stop et objectifs par rapport au mouvement réellement price.', confirm: 'Cible à l’intérieur de 1σ.', invalidate: 'Cible au-delà de 2σ.' },
      render: function (canvas) {
        return VC.mount(canvas, {
          type: 'line',
          data: { labels: labels, datasets: [
            ds('hi2', 0, false, 'transparent'),
            Object.assign(ds('hi1', 1, '-1', h2), {}),
            Object.assign(ds('mid', 2, '-1', h1), { borderColor: brand }),
            Object.assign(ds('lo1', 1, '-1', h1), {}),
            Object.assign(ds('lo2', 1, '-1', h2), {}) ] },
          options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: { callbacks: { label: function (ctx) { return ['2σ+', '1σ+', 'médian', '1σ−', '2σ−'][ctx.datasetIndex] + ' : ' + VXf.num(ctx.parsed.y, 2); } } } },
            scales: {
              x: { title: { display: true, text: 'Échéance (DTE)' } },
              y: { title: { display: true, text: 'Cours estimé' }, ticks: { callback: function (v) { return VXf.num(v, 0); } } },
            } } });
      } });
    _charts.push(c);
  }

  // Open interest par strike — bar divergente CALL / PUT.
  function chartOI(VC, d) {
    var rows = (d.oi_by_strike && d.oi_by_strike.rows) || [];
    if (!rows.length) { (document.getElementById('vx-opt-oi')||{}).innerHTML = '<div class="vx-card"><div class="vx-empty">Open interest indisponible.</div></div>'; return; }
    var brand = col(VC, 'brand', '#c9cdd4'), violet = col(VC, 'violet', '#9c79d0');
    var c = VC.card('vx-opt-oi', {
      title: 'Open interest par strike', question: 'Où se concentrent les positions ouvertes ?',
      /*  Le contrat exige que l'OI montre LE ZERO et la PROVENANCE des niveaux
          (controle 081). Un strike sans contrat et un strike a zero contrat
          ouvert se ressemblent sur une barre : le compte des strikes vides le
          separe, et la limite dit d'ou viennent les niveaux — jamais d'un
          moteur de « murs » que Vertex ne possede pas.  */
      conclusion: 'CALL vs PUT sur ' + rows.length + ' strike(s) · '
        + rows.filter(function (r) { return !r.call && !r.put; }).length + ' à zéro contrat ouvert',
      height: 240, source: 'SCAN', timestamp: volTs(d), mode: 'delayed',
      limits: 'Niveaux agrégés depuis les contrats du scan, strike par strike — '
        + 'aucun « mur » n’est déduit : Vertex ne possède pas de moteur de niveaux. '
        + 'Le zéro est la ligne médiane ; CALL au-dessus, PUT en dessous.',
      legend: [{ label: 'CALL OI', color: brand }, { label: 'PUT OI', color: violet }],
      explain: { shows: 'Open interest CALL (haut) et PUT (bas) par strike.', why: 'Les gros strikes agissent souvent comme aimants/paliers.', confirm: 'OI CALL massif au-dessus du spot.', invalidate: 'OI PUT dominant sous le spot.' },
      render: function (canvas) {
        return VC.mount(canvas, {
          type: 'bar',
          data: { labels: rows.map(function (r) { return r.strike; }),
            datasets: [
              { label: 'CALL OI', data: rows.map(function (r) { return r.call; }), backgroundColor: brand + 'cc', borderRadius: 2, maxBarThickness: 22 },
              { label: 'PUT OI', data: rows.map(function (r) { return -r.put; }), backgroundColor: violet + 'cc', borderRadius: 2, maxBarThickness: 22 } ] },
          plugins: [spotLinePlugin(d.spot, 'Spot ' + VXf.nd(d.spot))],
          options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ' : ' + VXf.num(Math.abs(ctx.parsed.y), 0); } } } },
            scales: {
              x: { stacked: true, title: { display: true, text: 'Strike' } },
              y: { stacked: true, title: { display: true, text: 'Open interest (contrats)' },
                grid: { color: function (ctx) { return Number(ctx.tick.value) === 0 ? 'rgba(255,255,255,.18)' : 'rgba(255,255,255,.05)'; } },
                ticks: { callback: function (v) { return VXf.num(Math.abs(v), 0); } } },
            } } });
      } });
    _charts.push(c);
    tableEquivalente('vx-opt-oi', {
      titre: 'Open interest par strike',
      legende: 'Contrats ouverts en call et en put, strike par strike, et leur solde.',
      colonnes: [{ titre: 'Strike', unite: '', num: true },
                 { titre: 'OI call', unite: '(contrats)', num: true },
                 { titre: 'OI put', unite: '(contrats)', num: true },
                 { titre: 'Solde call \u2212 put', unite: '(contrats)', num: true }],
      lignes: rows.map(function (r) {
        var solde = (r.call || 0) - (r.put || 0);
        /*  ZERO EXPLICITE : un 0 reel s'ecrit « 0 », il ne se tait pas et ne
            devient pas un tiret. Le tiret est reserve a l'absence.  */
        return [VXf.nd(r.strike), VXf.num(r.call || 0, 0), VXf.num(r.put || 0, 0),
                (solde >= 0 ? '+' : '') + VXf.num(solde, 0)];
      }),
      note: 'Spot ' + VXf.nd(d.spot) + ' \u00b7 « 0 » est un z\u00e9ro mesur\u00e9, pas une absence \u00b7 '
        + 'niveaux agr\u00e9g\u00e9s depuis les contrats du scan, aucun mur d\u00e9duit.'
    });
  }

  // Smile d'IV — IV par strike (calls + puts) pour une échéance.
  function chartSmile(VC, d) {
    var sm = d.iv_smile || {};
    var calls = sm.calls || [], puts = sm.puts || [];
    if (!calls.length && !puts.length) { (document.getElementById('vx-opt-smile')||{}).innerHTML = '<div class="vx-card"><div class="vx-empty">Smile indisponible.</div></div>'; return; }
    var brand = col(VC, 'brand', '#c9cdd4'), beige = col(VC, 'beige', '#c0b79f');
    var strikes = {};
    calls.concat(puts).forEach(function (r) { strikes[r.strike] = 1; });
    var xs = Object.keys(strikes).map(Number).sort(function (a, b) { return a - b; });
    var mapiv = function (arr) { var m = {}; arr.forEach(function (r) { m[r.strike] = +(r.iv * 100).toFixed(1); }); return xs.map(function (x) { return m[x] != null ? m[x] : null; }); };
    var c = VC.card('vx-opt-smile', {
      title: 'Smile d’IV' + (sm.dte != null ? ' · ' + sm.dte + ' j' : ''), question: 'L’IV est-elle plus chère sur les puts (skew) ?',
      conclusion: 'Spot ' + VXf.nd(sm.spot), height: 240, source: 'SCAN', timestamp: volTs(d), mode: 'delayed',
      legend: [{ label: 'CALL IV', color: brand }, { label: 'PUT IV', color: beige }],
      explain: { shows: 'IV par strike pour une échéance (calls et puts).', why: 'Un skew put marqué révèle une demande de protection (peur).', confirm: 'Smile symétrique et bas.', invalidate: 'Skew put très pentu.' },
      render: function (canvas) {
        return VC.mount(canvas, {
          type: 'line', data: { labels: xs, datasets: [
            { label: 'CALL IV', data: mapiv(calls), borderColor: brand, backgroundColor: brand, borderWidth: 2, pointRadius: 2, pointHoverRadius: 6, spanGaps: true, tension: 0, fill: false },
            { label: 'PUT IV', data: mapiv(puts), borderColor: beige, backgroundColor: beige, borderWidth: 1.5, pointRadius: 2, pointHoverRadius: 6, spanGaps: true, tension: 0, fill: false } ] },
          plugins: [spotLinePlugin(sm.spot, 'Spot ' + VXf.nd(sm.spot))],
          options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ' : ' + (ctx.parsed.y == null ? '—' : ctx.parsed.y + ' %'); } } } },
            scales: {
              x: { title: { display: true, text: 'Strike' } },
              y: { title: { display: true, text: 'Volatilité implicite (%)' }, ticks: { callback: function (v) { return v + ' %'; } } },
            } } });
      } });
    _charts.push(c);
    var ivDe = function (arr, x) {
      for (var i = 0; i < arr.length; i++) if (arr[i].strike === x) return VXf.num(arr[i].iv * 100, 1);
      return '<span class="vx2-absent">\u2014</span>';
    };
    tableEquivalente('vx-opt-smile', {
      titre: 'Smile d\u2019IV',
      legende: 'Volatilit\u00e9 implicite des calls et des puts, strike par strike, pour une \u00e9ch\u00e9ance.',
      colonnes: [{ titre: 'Strike', unite: '', num: true },
                 { titre: 'IV call', unite: '(%)', num: true },
                 { titre: 'IV put', unite: '(%)', num: true },
                 { titre: '\u00c9cart put \u2212 call', unite: '(pts)', num: true }],
      lignes: xs.map(function (x) {
        var vc = null, vp = null;
        calls.forEach(function (r) { if (r.strike === x) vc = r.iv * 100; });
        puts.forEach(function (r) { if (r.strike === x) vp = r.iv * 100; });
        var ecart = (vc != null && vp != null)
          ? ((vp - vc >= 0 ? '+' : '') + VXf.num(vp - vc, 1))
          : '<span class="vx2-absent">\u2014</span>';
        return [VXf.nd(x), ivDe(calls, x), ivDe(puts, x), ecart];
      }),
      note: '\u00c9ch\u00e9ance ' + (sm.dte != null ? sm.dte + ' jours' : 'non pr\u00e9cis\u00e9e')
        + ' \u00b7 spot ' + VXf.nd(sm.spot)
        + ' \u00b7 un \u00e9cart positif signale un skew put \u00b7 source SCAN.'
    });
  }

  // ── Scénarios du meilleur contrat (§19) ───────────────────────────
  function loadScenarios(sym) {
    var el = document.getElementById('vx-opt-sc-out-body');
    if (!sym) { el.innerHTML = '<div class="vx-empty">Saisis un symbole.</div>'; return; }
    try { if (VX.store) VX.store.set('active_ticker', sym); } catch (e0) {}
    loading(el);
    loadStrategies(sym);   // stratégies multi-jambes en parallèle (même sélecteur)
    get('/api/options/scenarios/' + encodeURIComponent(sym)).then(function (d) {
      if (!d || d.empty) { el.innerHTML = (window.VX && VX.states) ? VX.states.empty(esc((d && d.reason) || 'Indisponible.')) : 'Indisponible.'; return; }
      var c = d.contract || {}, sim = d.sim || {};
      var sc = sim.scenarios || {};
      var order = ['STOP', 'BEAR', 'FLAT', 'BASE', 'TP1', 'TP2', 'TP3'];
      var SCN = { STOP: 'Stop', BEAR: 'Baissier', FLAT: 'Stable', BASE: 'Base', TP1: 'Objectif 1', TP2: 'Objectif 2', TP3: 'Objectif 3' };
      var horizon = null;
      // Chaque scénario porte {spot, by_time_days:{'0':{value,pnl_pct},...}} :
      // on affiche l'immédiat (J+0) et un horizon (J+10) pour montrer le theta.
      var rows = order.filter(function (k) { return sc[k]; }).map(function (k) {
        var s = sc[k]; var bt = s.by_time_days || {};
        var hk = bt['10'] ? '10' : (bt['15'] ? '15' : null);
        if (hk && horizon == null) horizon = hk;
        var d0 = bt['0'] || {}, d10 = hk ? bt[hk] : {};
        var g = d0.pnl_pct, g10 = d10.pnl_pct;
        var cls = g == null ? '' : (g >= 0 ? 'vx-pos' : 'vx-neg');
        var cls10 = g10 == null ? '' : (g10 >= 0 ? 'vx-pos' : 'vx-neg');
        return '<tr><td><b>' + esc(SCN[k] || k) + '</b></td>' +
          '<td>' + (s.spot != null ? VXf.num(s.spot, 2) : '—') + '</td>' +
          '<td>' + (d0.value != null ? VXf.num(d0.value, 2) : '—') + '</td>' +
          '<td class="' + cls + '">' + (g != null ? (g >= 0 ? '+' : '') + VXf.num(g, 0) + ' %' : '—') + '</td>' +
          '<td class="' + cls10 + '">' + (g10 != null ? (g10 >= 0 ? '+' : '') + VXf.num(g10, 0) + ' %' : '—') + '</td></tr>';
      }).join('');
      var lims = (sim.limitations || []).map(function (l) { return '<li>' + esc(l) + '</li>'; }).join('');
      // Table plate = repli honnête si les composants graphiques ne sont pas chargés.
      var tableHTML = rows ? '<div class="vx-table-wrap"><table class="vx-table"><thead><tr><th scope="col">Scénario</th><th scope="col" class="vx-num">Spot</th><th scope="col" class="vx-num">Prime (J+0)</th><th scope="col" class="vx-num">Gain J+0</th><th scope="col" class="vx-num">Gain J+' + (horizon || '10') + '</th></tr></thead><tbody>' + rows + '</tbody></table></div>' : '<div class="vx-empty">Grille de scénarios indisponible.</div>';
      el.innerHTML =
        '<div class="vx-muted" style="margin-bottom:.6rem">Contrat : ' + esc(c.type || '') + ' ' + VXf.nd(c.strike) +
        ' · ' + (c.dte != null ? c.dte + ' j' : '—') + ' · IV ' + (c.iv != null ? VXf.num(c.iv, 1) + ' %' : '—') +
        ' · spot ' + VXf.nd(c.spot) + '</div>' +
        '<div id="vx-opt-sc-matrix">' + tableHTML + '</div>' +
        (sim.reward_risk != null ? '<div class="vx-muted" style="margin-top:.5rem">R:R du plan : <b>' + VXf.num(sim.reward_risk, 2) + '</b> · pire perte planifiée : ' + (sim.worst_planned_loss_pct != null ? VXf.num(sim.worst_planned_loss_pct, 0) + ' %' : '—') + '</div>' : '') +
        '<div class="vx-grid vx-mt3"><div class="vx-col-6" id="vx-opt-sc-theta"></div><div class="vx-col-6" id="vx-opt-sc-iv"></div></div>' +
        '<div class="vx-explain" style="margin-top:.8rem"><h4>Limites (estimation)</h4><ul>' + (lims || '<li class="vx-muted">—</li>') + '</ul>' +
        (sim.model_source ? '<p class="vx-muted">Modèle : ' + esc(sim.model_source) + '</p>' : '') + '</div>';
      // Heatmap scénario×temps + décote temps (theta) + sensibilité IV — mêmes données
      // moteur (sim.scenarios / sim.time_decay / sim.iv_sensitivity), rien de calculé ici.
      if (window.VXCharts) {
        var VC = window.VXCharts, ts = (d && d.ts) || null;   /* époque serveur, jamais l'heure du clic */
        if (VC.scenarioMatrix && VC.heatmapCard) VC.scenarioMatrix('vx-opt-sc-matrix', sim, { title: 'Valeur du contrat — scénario × horizon', question: 'Que vaut le contrat selon le mouvement du spot et le temps ?', source: 'scenario_pricer', timestamp: ts, mode: 'delayed' });
        if (VC.thetaCard) VC.thetaCard('vx-opt-sc-theta', sim, { title: 'Décote temps (theta)',unit:'$ par jour', question: 'Combien le temps grignote-t-il la prime, à spot figé ?', source: 'scenario_pricer', timestamp: ts, mode: 'delayed' });
        if (VC.ivSensitivityCard && VC.barCard) VC.ivSensitivityCard('vx-opt-sc-iv', sim, { title: 'Sensibilité à l\'IV', unit: '$ de prime', question: 'Quel impact d\'une variation d\'implicite sur la prime ?', source: 'scenario_pricer', timestamp: ts, mode: 'delayed' });
      }
    }).catch(function (e) { fail(el, e.message); });
  }

  // ── Stratégies options MULTI-JAMBES (§19) — moteur multileg_lab, lecture seule ──
  function fmtUsd(v) { var n = Math.round(v); return (n < 0 ? '-$' : '$') + VXf.num(Math.abs(n), 0); }
  function stratKpi(l, v) {
    return '<div class="vx-card--compact" style="padding:5px 7px;background:var(--vx-surface-2,#121214);border-radius:7px">' +
      '<div style="font-size:10px;letter-spacing:.03em;color:var(--vx-text-muted,#989092)">' + l + '</div>' +
      '<div class="vx-mono" style="font-size:13px;font-weight:700">' + v + '</div></div>';
  }
  function loadStrategies(sym) {
    var el = document.getElementById('vx-opt-strategies');
    if (!el) return;
    if (!sym) { el.innerHTML = '<div class="vx-empty">Saisis un symbole.</div>'; return; }
    loading(el);
    get('/api/options/strategies/' + encodeURIComponent(sym)).then(function (d) {
      /* Chaîne chargée en fond (serveur : en_cours) → réessai borné hors cache. */
      if (d && d.en_cours && (loadStrategies._retry || 0) < 2) {
        loadStrategies._retry = (loadStrategies._retry || 0) + 1;
        setTimeout(function () {
          try { VX.fetch.invalidate('/api/options/strategies/' + encodeURIComponent(sym)); } catch (e1) {}
          loadStrategies(sym);
        }, ((d.retry_s || 8) * 1000));
      }
      if (!d || !d.available || !d.strategies || !d.strategies.length) {
        el.innerHTML = (window.VX && VX.states) ? VX.states.empty(esc((d && d.reason) || 'Stratégies indisponibles pour ce titre.')) : 'Indisponible.';
        return;
      }
      var biasFr = { bullish: 'haussier', bearish: 'baissier', neutral: 'neutre' }[d.bias] || '—';
      var head = '<div class="vx-muted" style="margin-bottom:.6rem">' + esc(sym) + ' · spot ' + VXf.nd(d.spot) +
        ' · échéance ' + esc(d.exp || '—') + ' (' + VXf.nd(d.dte) + ' j) · IV ' + (d.iv != null ? d.iv.toFixed(1) + ' %' : '—') +
        ' · biais ' + biasFr + ' → stratégies classées par adéquation</div>';
      el.innerHTML = head + '<div class="vx-grid">' + d.strategies.map(function (s, i) {
        var credit = s.is_credit;
        var mp = s.max_profit_unbounded ? 'illimité' : (s.max_profit != null ? fmtUsd(s.max_profit) : '—');
        var ml = s.max_loss != null ? fmtUsd(s.max_loss) : '—';
        var pop = s.probability_of_profit != null ? s.probability_of_profit + ' %' : '—';
        var be = (s.breakevens && s.breakevens.length) ? s.breakevens.map(function (b) { return VXf.nd(b); }).join(' · ') : '—';
        var g = s.greeks;
        var recoStyle = s.recommended ? ' style="border-color:var(--vx-signal-500,#c9cdd4);box-shadow:0 0 0 1px var(--vx-signal-500,#c9cdd4)"' : '';
        return '<section class="vx-card vx-col-6"' + recoStyle + '>' +
          '<div class="vx-card-header"><span class="vx-card-title">' + esc(s.label) + '</span>' +
          (s.recommended ? '<span class="vx-badge" style="background:var(--vx-signal-500,#c9cdd4);color:#0b0d0a;font-weight:700">★ Recommandée</span>' : '') +
          '<span class="vx-badge" style="color:var(--vx-' + (credit ? 'positive' : 'option') + ')">' + (credit ? 'crédit ' : 'débit ') + fmtUsd(Math.abs(s.net_premium)) + '</span></div>' +
          (s.fit_reason ? '<div class="vx-meta" style="margin:-2px 0 6px">' + esc(s.fit_reason) + '</div>' : '') +
          '<div id="strat-pf-' + i + '" style="height:150px"></div>' +
          '<div class="vx-grid vx-mt2" style="grid-template-columns:repeat(4,1fr);gap:6px">' +
          stratKpi('PoP', pop) + stratKpi('Gain max', mp) + stratKpi('Perte max', ml) + stratKpi('Breakevens', be) +
          '</div>' +
          (g ? '<div class="vx-meta vx-mt2">Δ ' + g.delta + ' · Θ ' + g.theta + '/j · Vega ' + g.vega + '/1%IV' +
            (g.vanna != null ? ' · Vanna ' + g.vanna + ' · Vomma ' + g.vomma : '') + '</div>' : '') +
          '</section>';
      }).join('') + '</div>' +
        '<div class="vx-explain" style="margin-top:.6rem"><p class="vx-muted">' + esc(d.strategies[0].model_note || '') + '</p></div>';
      // Courbe payoff par stratégie (ligne P&L verte au-dessus de 0, corail en dessous).
      d.strategies.forEach(function (s, i) {
        var host = document.getElementById('strat-pf-' + i);
        var pts = s.payoff || [];
        if (!host || !window.VXCharts || pts.length < 2) return;
        host.innerHTML = '<canvas></canvas>';
        VXCharts.mount(host.querySelector('canvas'), {
          type: 'line',
          data: {
            labels: pts.map(function (p) { return p.price; }),
            datasets: [{
              data: pts.map(function (p) { return p.pnl; }),
              borderColor: VXCharts.colors.neutral, borderWidth: 1.6, pointRadius: 0, fill: false, tension: 0,
              segment: { borderColor: function (ctx) { return ctx.p1.parsed.y >= 0 ? VXCharts.colors.positive : VXCharts.colors.negative; } },
            }],
          },
          options: {
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (ctx) { return 'P&L ' + fmtUsd(ctx.parsed.y) + ' @ ' + VXf.nd(ctx.label); } } } },
            scales: { x: { ticks: { maxTicksLimit: 6 }, grid: { display: false } }, y: { grid: { color: 'rgba(255,255,255,.06)' }, ticks: { callback: function (v) { return fmtUsd(v); } } } },
          },
        });
      });
    }).catch(function (e) { fail(el, e.message); });
  }

  // ── Événements par titre ──────────────────────────────────────────
  function loadEvents(sym) {
    var el = document.getElementById('vx-opt-ev-out-body');
    if (!sym) { el.innerHTML = '<div class="vx-empty">Saisis un symbole.</div>'; return; }
    try { if (VX.store) VX.store.set('active_ticker', sym); } catch (e0) {}
    loading(el);
    get('/api/options/event-risk/' + encodeURIComponent(sym)).then(function (d) {
      el.innerHTML = verdictCard(d && d.interpretation);
    }).catch(function (e) { fail(el, e.message); });
  }

  // ── Câblage ───────────────────────────────────────────────────────
  function view() {
    var lbl = document.querySelector('[data-page-label]');
    var v = lbl ? (lbl.dataset.pageLabel || '') : '';
    var m = v.split(':')[1] || 'overview';
    return m;
  }

  function bindExplain() {
    document.body.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('[data-explain]') : null;
      if (!b) return;
      var map = { overview: 'options.overview_mix', volatility: 'options.volatility', event_risk: 'options.event_risk', environment: 'options.environment' };
      explainDrawer(LAST[map[b.dataset.explain]]);
    });
  }

  // ── Symboles réellement présents dans le tableau d'options (démo/scan) ──
  /* Le second argument est l'ERREUR de lecture, pas une liste vide : un tableau
     réellement vide et un tableau qu'on n'a PAS PU LIRE sont deux états que
     l'invariant 5 exige de garder distincts, et `catch(cb([]))` les fondait. */
  function boardSyms(cb) {
    get('/api/options/overview').then(function (d) {
      var rows = (d && d.radar) || [];
      var seen = {}, syms = [];
      rows.forEach(function (r) { var s = (r && r.sym || '').toUpperCase(); if (s && !seen[s]) { seen[s] = 1; syms.push(s); } });
      cb(syms, null);
    }).catch(function (e) { cb([], e || new Error('lecture impossible')); });
  }

  /* ABSENCE NOMMÉE quand le tableau d'options ne fournit aucun titre.
     MESURE du 2026-09-06 (instance de contrôle, sans IBKR) :
     `/options?view=volatility` rendait 16 valeurs vides sur 16. Cause :
     `autoSym` faisait `if (!syms.length) return;` — un retour SILENCIEUX —
     et les quatre hôtes de graphiques (`vx-opt-term`, `vx-opt-cone`,
     `vx-opt-oi`, `vx-opt-smile`) restaient littéralement vides sous un rail
     qui conseillait « Choisis un symbole présent dans le tableau d'options »,
     consigne inapplicable puisqu'il n'y en avait aucun. Une absence se dit ;
     et une PANNE de lecture se dit autrement qu'une absence. */
  function nommerAbsenceDeTableau(railId, chartIds, erreur) {
    var msg = erreur
      ? ('Le tableau d’options n’a pas pu être lu (' + (erreur.message || 'erreur inconnue') + ') : '
         + 'ce n’est pas une absence de données, c’est une lecture en échec. Saisis un symbole pour interroger directement.')
      : ('Aucun titre dans le tableau d’options pour l’instant : rien à pré-sélectionner. '
         + 'Le tableau se remplit au passage du scan ; tu peux saisir un symbole à la main.');
    var rail = document.getElementById(railId);
    if (rail) {
      rail.innerHTML = erreur
        ? ((window.VX && VX.states) ? VX.states.error(esc(msg)) : '<div class="vx-error-banner">' + esc(msg) + '</div>')
        : ((window.VX && VX.states) ? VX.states.empty(esc(msg)) : '<div class="vx-empty">' + esc(msg) + '</div>');
    }
    (chartIds || []).forEach(function (id) {
      var e = document.getElementById(id);
      if (e) e.innerHTML = '<div class="vx-card"><div class="vx-' + (erreur ? 'error-banner' : 'empty') + '">' + esc(msg) + '</div></div>';
    });
  }

  // Pré-sélectionne un symbole du tableau + puces d'accès rapide, pour que les
  // graphiques s'affichent d'emblée (§36) au lieu d'un formulaire vide (§10).
  function autoSym(goEl, inputEl, loadFn, vide) {
    if (!inputEl) return;
    boardSyms(function (syms, erreur) {
      if (!syms.length) { if (vide) vide(erreur); return; }
      if (goEl && goEl.parentNode && !goEl.parentNode.querySelector('.opt-chips')) {
        var chips = document.createElement('div');
        chips.className = 'opt-chips vx-flex vx-wrap';
        chips.style.cssText = 'gap:6px;margin-top:10px;align-items:center';
        chips.innerHTML = '<span class="vx-muted" style="font-size:11px">Depuis le tableau :</span>' +
          syms.slice(0, 8).map(function (x) { return '<button type="button" class="vx-btn vx-btn-sm vx-btn-ghost opt-chip" data-optsym="' + esc(x) + '">' + esc(x) + '</button>'; }).join('');
        goEl.parentNode.appendChild(chips);
        chips.addEventListener('click', function (e) {
          var b = e.target.closest ? e.target.closest('[data-optsym]') : null;
          if (!b) return;
          var sym = b.getAttribute('data-optsym');
          inputEl.value = sym; loadFn(sym);
          chips.querySelectorAll('.opt-chip').forEach(function (c) { c.classList.toggle('vx-active', c === b); });
        });
      }
      if (!inputEl.value) {
        inputEl.value = syms[0]; loadFn(syms[0]);
        var first = goEl && goEl.parentNode && goEl.parentNode.querySelector('.opt-chip');
        if (first) first.classList.add('vx-active');
      }
    });
  }

  function init() {
    bindExplain();
    var v = view();
    if (v === 'overview') loadOverview();
    else if (v === 'radar') loadRadar();
    else if (v === 'volatility') {
      var g = document.getElementById('vx-opt-vol-go');
      var s = document.getElementById('vx-opt-vol-sym');
      if (g) g.addEventListener('click', function () { loadVolatility((s.value || '').trim().toUpperCase()); });
      if (s) s.addEventListener('keydown', function (e) { if (e.key === 'Enter') loadVolatility((s.value || '').trim().toUpperCase()); });
      autoSym(g, s, loadVolatility, function (err) {
        nommerAbsenceDeTableau('vx-opt-vol-out-body',
          ['vx-opt-term', 'vx-opt-cone', 'vx-opt-oi', 'vx-opt-smile'], err);
      });
    } else if (v === 'events') {
      var g2 = document.getElementById('vx-opt-ev-go');
      var s2 = document.getElementById('vx-opt-ev-sym');
      if (g2) g2.addEventListener('click', function () { loadEvents((s2.value || '').trim().toUpperCase()); });
      if (s2) s2.addEventListener('keydown', function (e) { if (e.key === 'Enter') loadEvents((s2.value || '').trim().toUpperCase()); });
      autoSym(g2, s2, loadEvents, function (err) {
        nommerAbsenceDeTableau('vx-opt-ev-out-body', [], err);
      });
    } else if (v === 'scenarios') {
      var g3 = document.getElementById('vx-opt-sc-go');
      var s3 = document.getElementById('vx-opt-sc-sym');
      if (g3) g3.addEventListener('click', function () { loadScenarios((s3.value || '').trim().toUpperCase()); });
      if (s3) s3.addEventListener('keydown', function (e) { if (e.key === 'Enter') loadScenarios((s3.value || '').trim().toUpperCase()); });
      autoSym(g3, s3, loadScenarios, function (err) {
        /* MESURE du 2026-09-06 : cette vue porte un SECOND hôte,
           `vx-opt-strategies` (options_intel_page.py:289). Il n'était pas
           passé ici, donc il gardait son texte de départ — « Choisis un
           symbole pour construire les stratégies depuis le board » — à
           l'identique dans les DEUX états : consigne inapplicable quand le
           board est vide, et panne muette quand la lecture échoue. C'est la
           même confusion absence/panne que le rail voisin vient de fermer. */
        nommerAbsenceDeTableau('vx-opt-sc-out-body', ['vx-opt-strategies'], err);
      });
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
