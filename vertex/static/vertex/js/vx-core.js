/* Vertex Core — event bus, contexte de navigation, refresh manager,
   fraîcheur, toasts. Aucune logique financière ici : l'UI consomme les
   moteurs, elle ne recalcule rien. */
(function () {
  'use strict';
  const VX = window.VX = window.VX || {};

  /* ── Télémétrie d'erreurs (objectif 0-erreur : /api/client-log) ──── */
  function reportError(msg, src, line) {
    try {
      fetch('/api/client-log', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page: location.pathname, msg: String(msg || '').slice(0, 300), src: String(src || '').slice(0, 160), line: line | 0 }),
      }).catch(() => {});
    } catch (e) {}
  }
  window.addEventListener('error', (e) => reportError(e.message, e.filename, e.lineno));
  window.addEventListener('unhandledrejection', (e) => {
    const r = e && e.reason;
    reportError('unhandledrejection: ' + ((r && r.message) ? r.message : String(r)).slice(0, 260), '', 0);
  });

  /* ── Event bus (§41) ─────────────────────────────────────────────── */
  const bus = new EventTarget();
  let _pageBus = [];                    // abonnements de PAGE (purgés à la navigation)
  VX.bus = {
    /* opts.persistent : abonnement de SHELL, survit aux navigations client.
       Défaut = abonnement de page → retiré au teardown (évite les doublons). */
    on(name, fn, opts) {
      bus.addEventListener(name, fn);
      if (!(opts && opts.persistent)) _pageBus.push({ name, fn });
      return () => bus.removeEventListener(name, fn);
    },
    emit(name, detail) { bus.dispatchEvent(new CustomEvent(name, { detail })); },
    _clearPage() { _pageBus.forEach((h) => bus.removeEventListener(h.name, h.fn)); _pageBus = []; },
  };
  VX.EVENTS = ['vx:favorites-changed', 'vx:watchlist-changed', 'vx:follow-changed',
    'vx:position-changed', 'vx:alert-changed', 'vx:thesis-changed',
    'vx:decision-updated', 'vx:data-refreshed', 'vx:connection-changed'];

  /* ── Formatage ───────────────────────────────────────────────────── */
  VX.fmt = {
    nd(v) { return (v === null || v === undefined || v === '' || (typeof v === 'number' && !isFinite(v))) ? '—' : v; },
    num(v, dec = 2) {
      if (v === null || v === undefined || !isFinite(v)) return '—';
      return Number(v).toLocaleString('fr-FR', { minimumFractionDigits: dec, maximumFractionDigits: dec });
    },
    pct(v, dec = 2, signed = true) {
      if (v === null || v === undefined || !isFinite(v)) return '—';
      const s = signed && v > 0 ? '+' : '';
      return s + Number(v).toLocaleString('fr-FR', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + ' %';
    },
    price(v) { return VX.fmt.num(v, Math.abs(v) >= 1000 ? 0 : 2); },
    /* §38 : « À l'instant », « Il y a 8 min », « Aujourd'hui à 15:42 »… */
    ago(ts) {
      if (!ts) return '—';
      const d = (ts instanceof Date) ? ts : new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
      if (isNaN(d)) return '—';
      const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
      if (s < 10) return 'À l’instant';
      if (s < 90) return `Il y a ${Math.round(s)} s`;
      if (s < 3600) return `Il y a ${Math.round(s / 60)} min`;
      const today = new Date(); const opts = { hour: '2-digit', minute: '2-digit' };
      if (d.toDateString() === today.toDateString()) return 'Aujourd’hui à ' + d.toLocaleTimeString('fr-FR', opts);
      const yest = new Date(Date.now() - 864e5);
      if (d.toDateString() === yest.toDateString()) return 'Hier à ' + d.toLocaleTimeString('fr-FR', opts);
      return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
    },
    isoFull(ts) {
      const d = (ts instanceof Date) ? ts : new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
      return isNaN(d) ? '' : d.toLocaleString('fr-FR');
    },
  };

  /* ── UpdateIndicator (§38) ───────────────────────────────────────────
     `data-ts` et `.vx-update-age` ne sont pas décoratifs : ils rendent l'âge
     RE-CALCULABLE après coup. Sans eux, l'âge est peint une fois et ne bouge
     plus — mesuré : une page sans tâche `VX.refresh` affichait « Il y a 21 min »
     indéfiniment, réseau vivant comme réseau coupé. Le calcul (`VX.fmt.ago`)
     était juste ; c'est le RENDU qui n'était jamais rejoué. Voir `VX.freshness
     ._retick` plus bas. */
  VX.updateIndicator = function (ts, source, mode) {
    const modeLabel = { live: 'Live', delayed: 'Différé', fallback: 'Secours', error: 'Erreur' }[mode] || '';
    const ms = VX.freshness._ms(ts);
    const suite = source ? ' · ' + source + (modeLabel ? ' ' + modeLabel : '') : '';
    return `<span class="vx-update" data-mode="${mode || 'fallback'}"` +
      (ms == null ? '' : ` data-ts="${ms}"`) +
      ` title="${VX.fmt.isoFull(ts)}">` +
      /*  `VX.fmt.ago(null)` rend « — ». Pose dans un pied de carte, ce tiret
          se lit comme un age, alors qu'il dit l'ABSENCE d'age : trois pages
          affichaient « ● — · Moteur … » sans qu'on puisse savoir si la donnee
          etait fraiche, vieille, ou jamais horodatee. Le mot le dit.  */
      `<span class="vx-dot"></span><span class="vx-update-age">` +
      (ms == null ? 'Âge inconnu' : VX.fmt.ago(ts)) + `</span>${suite}</span>`;
  };

  /* ── Régimes de marché : vocabulaire HUMAIN partagé ─────────────────
     Source unique des libellés : les codes moteur (TREND_UP, CHOP…) ne
     s'affichent JAMAIS bruts — chaque page consomme cette table.
     Forme : { label, tone ('go'|'risk'|''), hint }. */
  VX.regime = {
    MAP: {
      TREND_UP: { label: 'Bull Momentum', tone: 'go', hint: 'Tendance haussière — le marché bénéficie d’un momentum favorable.' },
      TREND_DOWN: { label: 'Bear Pressure', tone: 'risk', hint: 'Tendance baissière — la pression vendeuse reste dominante.' },
      CHOP: { label: 'Range Mode', tone: '', hint: 'Marché sans direction — privilégier patience et sélectivité.' },
      RISK_ON: { label: 'Risk-On', tone: 'go', hint: 'Appétit pour le risque — environnement favorable aux actifs dynamiques.' },
      RISK_OFF: { label: 'Defensive Mode', tone: 'risk', hint: 'Prudence dominante — priorité à la qualité et à la protection.' },
      PANIC: { label: 'Market Stress', tone: 'risk', hint: 'Stress extrême — priorité à la préservation du capital.' },
      EUPHORIA: { label: 'Euphoria Mode', tone: '', hint: 'Optimisme extrême — attention aux excès et aux retournements.' },
      VOLATILITY_EXPANSION: { label: 'Volatility Surge', tone: 'risk', hint: 'La volatilité augmente — mouvements rapides et risque renforcé.' },
      VOLATILITY_COMPRESSION: { label: 'Volatility Squeeze', tone: '', hint: 'Marché calme — une accélération pourrait se préparer.' },
      MEAN_REVERSION: { label: 'Mean Reversion', tone: '', hint: 'Les excès se corrigent — viser les retours à la moyenne.' },
      TRANSITION: { label: 'Regime Shift', tone: '', hint: 'Le régime bascule — attendre la confirmation.' },
      UNKNOWN: { label: 'Signal Pending', tone: '', hint: 'Lecture du marché en cours — données encore insuffisantes.' },
    },
    _get(code) { return this.MAP[String(code || '').trim().toUpperCase()] || null; },
    /* Libellé humain ; un code inconnu revient tel quel (honnête, jamais inventé). */
    label(code) { const m = this._get(code); return m ? m.label : (code || 'n/d'); },
    tone(code) { const m = this._get(code); return m ? m.tone : ''; },
    hint(code) { const m = this._get(code); return m ? m.hint : ''; },
    known(code) { return !!this._get(code); },
  };

  /* ── États de données (§39) ──────────────────────────────────────── */
  VX.states = {
    loading(rows = 3) {
      let h = '<div class="vx-flex-col" aria-busy="true" data-state="loading">';
      for (let i = 0; i < rows; i++) h += `<div class="vx-skeleton" style="height:${i ? 14 : 22}px;width:${90 - i * 15}%"></div>`;
      return h + '</div>';
    },
    // Mini-visualisation « fantôme » (§44) : silhouette de placeholder, JAMAIS
    // une donnée. Sert à ne plus laisser de rectangle vide (§10). type :
    // 'bars' (défaut) · 'line' · 'ring' · false (aucun).
    ghost(type) {
      if (type === false) return '';
      if (type === 'ring') {
        return '<svg class="vx-state-ghost" viewBox="0 0 44 44" aria-hidden="true">' +
          '<circle cx="22" cy="22" r="17" fill="none" stroke="currentColor" stroke-width="5" opacity=".18"/>' +
          '<circle cx="22" cy="22" r="17" fill="none" stroke="var(--vx-copper-light)" stroke-width="5" ' +
          'stroke-dasharray="60 107" stroke-linecap="round" opacity=".35" transform="rotate(-90 22 22)"/></svg>';
      }
      if (type === 'line') {
        return '<svg class="vx-state-ghost" viewBox="0 0 140 48" aria-hidden="true">' +
          '<line x1="6" y1="42" x2="134" y2="42" stroke="currentColor" stroke-width="1" stroke-dasharray="2 3" opacity=".3"/>' +
          '<path d="M6 34 L34 26 L58 30 L82 16 L106 22 L134 12" fill="none" stroke="var(--vx-copper-light)" ' +
          'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity=".4"/></svg>';
      }
      let bars = '';
      const hs = [16, 26, 12, 30, 20, 34, 22];
      hs.forEach((h, i) => {
        bars += `<rect x="${8 + i * 19}" y="${42 - h}" width="11" height="${h}" rx="2" ` +
          `fill="${i === 5 ? 'var(--vx-copper-light)' : 'currentColor'}" opacity="${i === 5 ? .38 : .16}"/>`;
      });
      return '<svg class="vx-state-ghost" viewBox="0 0 140 48" aria-hidden="true">' +
        '<line x1="6" y1="42" x2="140" y2="42" stroke="currentColor" stroke-width="1" opacity=".2"/>' + bars + '</svg>';
    },
    empty(reason, action, opts) {
      opts = opts || {};
      const title = opts.title || 'Aucune donnée';
      const g = VX.states.ghost(opts.ghost === undefined ? 'bars' : opts.ghost);
      return `<div class="vx-state" data-state="empty">${g}<b>${title}</b><span>${reason || ''}</span>${action || ''}</div>`;
    },
    /* LOT 608 — un vide qui vient du BUREAU (localStorage synchronisé), pas d'un
       moteur serveur. Depuis le 607, `VX.store.desk_sync` sait quand la lecture
       du bureau a échoué ; personne ne l'affichait, et « Aucune position
       déclarée » restait écrit tel quel alors que le serveur avait peut-être les
       positions. C'est 607-A dans la zone même où l'utilisateur forme sa
       conviction — le message global du 607 est transitoire, celui-ci est là.

       DÉLIBÉRÉMENT SÉPARÉ de `empty()` : sur les 59 états vides du produit, 39
       viennent d'un moteur serveur et n'ont RIEN à voir avec le bureau. Y coller
       cette mention serait un mensonge d'un autre genre — la faute corrigée
       depuis le 602, commise à l'envers. Cet état est réservé aux zones qui
       lisent réellement les clés du bureau. */
    emptyDesk(reason, action, opts) {
      let sync = null;
      try { sync = VX.store && VX.store.get('desk_sync'); } catch (e) {}
      const base = VX.states.empty(reason, action, opts);
      if (!sync || sync === 'ok') return base;
      const quoi = sync === 'read-error'
        ? 'tes données du serveur n’ont pas pu être chargées'
        : 'la dernière sauvegarde vers le serveur a échoué';
      return base + `<div class="vx-error-banner" data-state="desk-desync">` +
        `⚠ Bureau non synchronisé — ${quoi}. Cette liste peut être incomplète : ` +
        `n’en conclus pas qu’elle est vide.` +
        `<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/system?view=data">Ouvrir Système</a></div>`;
    },
    stale(ageText, source, impact) {
      return `<div class="vx-stale-banner" data-state="stale">⏳ Donnée rassise (${ageText}${source ? ' · ' + source : ''})` +
        `${impact ? ' — ' + impact : ' — décision ACTIONABLE bloquée'}</div>`;
    },
    error(cause, retryFn) {
      return `<div class="vx-error-banner" data-state="error">⚠ ${cause || 'Erreur de chargement'}` +
        `<button class="vx-btn vx-btn-sm" onclick="${retryFn || 'location.reload()'}">Réessayer</button>` +
        `<a class="vx-btn vx-btn-sm vx-btn-ghost" href="/system?view=data">Ouvrir Système</a></div>`;
    },
  };

  /* ── Toasts (§42 — jamais alert/confirm/prompt) ──────────────────── */
  VX.toast = function (message, tone = 'info', ms = 3200) {
    let host = document.querySelector('.vx-toasts');
    if (!host) { host = document.createElement('div'); host.className = 'vx-toasts'; host.setAttribute('role', 'status'); document.body.appendChild(host); }
    const t = document.createElement('div');
    t.className = 'vx-toast'; t.dataset.tone = tone; t.textContent = message;
    host.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 350); }, ms);
  };

  /* ── VXContext (§15) : conservation page/vue/filtres/scroll ─────── */
  const CTX_KEY = 'vxNavigationContext';
  VX.context = {
    _read() { try { return JSON.parse(sessionStorage.getItem(CTX_KEY) || 'null'); } catch (e) { return null; } },
    save(extra) {
      const url = new URL(location.href);
      const ctx = Object.assign({
        from: url.pathname, view: url.searchParams.get('view') || null,
        filters: VX.context._collectFilters(), scrollY: window.scrollY,
        label: document.querySelector('[data-page-label]')?.dataset.pageLabel || document.title,
        ts: Date.now(),
      }, extra || {});
      try { sessionStorage.setItem(CTX_KEY, JSON.stringify(ctx)); } catch (e) { /* quota */ }
      window.VXContext = ctx;
      return ctx;
    },
    get() { return window.VXContext || VX.context._read(); },
    clear() { try { sessionStorage.removeItem(CTX_KEY); } catch (e) {} window.VXContext = null; },
    _collectFilters() {
      const out = {};
      document.querySelectorAll('[data-filter-key]').forEach(el => {
        const k = el.dataset.filterKey;
        if (el.matches('.vx-chip')) { if (el.getAttribute('aria-pressed') === 'true') out[k] = el.dataset.filterValue || '1'; }
        else if (el.value) out[k] = el.value;
      });
      return out;
    },
    /* Restaure filtres + scroll si on revient sur la page d'origine. */
    restoreIfReturning() {
      const ctx = VX.context._read();
      if (!ctx || ctx.from !== location.pathname) return null;
      const view = new URL(location.href).searchParams.get('view') || null;
      if (ctx.view && view && ctx.view !== view) return null;
      Object.entries(ctx.filters || {}).forEach(([k, v]) => {
        document.querySelectorAll(`[data-filter-key="${k}"]`).forEach(el => {
          if (el.matches('.vx-chip')) { if ((el.dataset.filterValue || '1') === v) el.setAttribute('aria-pressed', 'true'); }
          else el.value = v;
        });
      });
      if (ctx.scrollY) requestAnimationFrame(() => window.scrollTo(0, ctx.scrollY));
      return ctx;
    },
  };
  /* Ouvre l'analyse en conservant le contexte — utilisé PARTOUT. */
  VX.openAnalysis = function (symbol, extra) {
    VX.context.save(Object.assign({ selectedSymbol: symbol }, extra || {}));
    VX.recentTickers.push(symbol);
    var href = '/analysis/' + encodeURIComponent(symbol.toUpperCase());
    if (VX.router && VX.router.go) VX.router.go(href);   // navigation ticker fluide (SPA)
    else location.href = href;                            // repli dur (routeur absent)
  };

  /* ── Tickers récents ─────────────────────────────────────────────── */
  VX.recentTickers = {
    get() { try { return JSON.parse(localStorage.getItem('vxRecentTickers') || '[]'); } catch (e) { return []; } },
    push(sym) {
      sym = String(sym || '').toUpperCase(); if (!sym) return;
      const list = VX.recentTickers.get().filter(s => s !== sym); list.unshift(sym);
      try { localStorage.setItem('vxRecentTickers', JSON.stringify(list.slice(0, 12))); } catch (e) {}
    },
  };

  /* ── Couche de données : cache persistant + SWR + dédup (§40, LOT 3) ──
     Le cache survit désormais au reload (sessionStorage) → revenir sur une page
     ne relance pas un chargement lourd. Déduplication in-flight, invalidation
     ciblée, stale-while-revalidate (VX.swr), annulation propre. Lecture seule. */
  const cache = new Map();     // url -> {ts, data}
  const inflight = new Map();  // url -> {p, ctl}
  const PERSIST_KEY = 'vxDataCache';
  const PERSIST_MAX_ENTRY = 200000;   // n'archive pas les gros payloads (ex. /scan ~8Mo)
  const PERSIST_MAX = 60;             // nb d'entrées persistées

  /* Hydrate le cache depuis la session au démarrage (revisite instantanée). */
  (function hydrate() {
    try {
      const raw = sessionStorage.getItem(PERSIST_KEY);
      if (!raw) return;
      const obj = JSON.parse(raw);
      Object.keys(obj).forEach((u) => { cache.set(u, obj[u]); });
    } catch (e) {}
  })();
  // Ne JAMAIS archiver de données personnelles/compte en clair dans sessionStorage
  // (positions réelles, IBKR, desk, compte) — confidentialité. Ces endpoints restent
  // en cache mémoire (perdu au reload), mais ne sont pas persistés.
  const PERSIST_DENY = ['/api/ibkr', '/api/positions', '/api/pos-quotes', '/api/desk',
    '/api/account', '/api/tracking'];
  function _persistable(url) {
    for (let i = 0; i < PERSIST_DENY.length; i++) { if (url.indexOf(PERSIST_DENY[i]) === 0) return false; }
    return true;
  }
  let _persistTimer = null;
  function schedulePersist() {
    if (_persistTimer) return;
    _persistTimer = setTimeout(() => {
      _persistTimer = null;
      try {
        const out = {}; let n = 0;
        // les plus récents d'abord, bornés en taille et en nombre
        const entries = Array.from(cache.entries()).sort((a, b) => b[1].ts - a[1].ts);
        for (const [u, v] of entries) {
          if (n >= PERSIST_MAX) break;
          if (!_persistable(u)) continue;               // données perso/compte → jamais persistées
          let s; try { s = JSON.stringify(v); } catch (e) { continue; }
          if (s.length > PERSIST_MAX_ENTRY) continue;   // trop gros → non persisté
          out[u] = v; n++;
        }
        sessionStorage.setItem(PERSIST_KEY, JSON.stringify(out));
      } catch (e) {}
    }, 400);
  }

  function _store(url, data) {
    cache.set(url, { ts: Date.now(), data });
    if (cache.size > 120) cache.delete(cache.keys().next().value);
    schedulePersist();
  }

  /* ── TTL effectif : « chargé une fois, figé 30 min » ─────────────────────
     Dans un cycle de session d'analyse (30 min), les données du scan ne changent
     PAS. On les tient donc en cache toute la session → changer de page est
     INSTANTANÉ, aucun rechargement, aucune ré-recherche. Sécurité :
     - un TTL explicite ≤ 0 (SWR, /api/session/manifest, bouton « Rafraîchir »)
       force toujours le réseau — jamais forcé long ;
     - les endpoints LIVE / personnels (statut, cotations, IBKR, desk, compte)
       gardent leur TTL court d'origine ;
     - watchSession invalide le cache dès qu'un NOUVEAU scan publie (session_id) →
       bascule atomique, donc jamais de donnée périmée servie au-delà de la session. */
  const SESSION_TTL = 1800000;   // 30 min = REFRESH_SEC serveur (cadence de session)
  const LIVE_TTL = ['/api/live/status', '/api/pos-quotes', '/api/ibkr', '/api/positions',
    '/api/account', '/api/tracking', '/api/desk'];
  function _effTtl(url, ttl) {
    if (ttl <= 0) return ttl;                                  // force-refresh explicite → réseau
    for (let i = 0; i < LIVE_TTL.length; i++) { if (url.indexOf(LIVE_TTL[i]) === 0) return ttl; }
    // On NE fige PAS tant que la session n'est pas « ready » : au démarrage à froid le
    // scan se remplit encore (régime UNKNOWN, VIX n/d…) — garder le TTL court laisse les
    // données arriver, au lieu de figer un écran vide 30 min. Une fois la session prête,
    // on tient les données du scan toute la session (navigation instantanée).
    try { if (!VX.store || VX.store.get('session_status') !== 'ready') return ttl; } catch (e) { return ttl; }
    return ttl > SESSION_TTL ? ttl : SESSION_TTL;
  }

  /* ── Echappement HTML (§securite) ───────────────────────────────────
     Le produit construit son HTML par chaines. Chaque page en avait sa PROPRE
     copie d'`esc`, et le JS servi sous /static n'en avait AUCUNE : les
     notifications interpolaient `n.title`, `n.message` et `n.category` bruts.
     Recensement du 25 aout 2026 : cinq interpolations de champs d'origine
     externe sans echappement dans tout le produit.

     Gravite dite honnetement : aucun chemin d'attaquant DISTANT n'est prouve.
     Le seul champ reellement externe est le `sector` de yfinance ; les autres
     viennent des tickers saisis par l'utilisateur. Ce qu'on ferme, c'est la
     CLASSE — pas un exploit vivant. */
  VX.esc = function (s) {
    return String(s == null ? '' : s).replace(/[<>&"']/g, function (c) {
      return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  const _stats = { hits: 0, misses: 0, dedup: 0 };   // observabilité (§18)
  VX.fetch = function (url, { ttl = 30000, priority = 'normal', signal } = {}) {
    ttl = _effTtl(url, ttl);                                   // « figé 30 min » : cf. _effTtl
    const hit = cache.get(url);
    if (hit && Date.now() - hit.ts < ttl) { _stats.hits++; return Promise.resolve(hit.data); }
    if (inflight.has(url)) { _stats.dedup++; return inflight.get(url).p; }
    _stats.misses++;
    const ctl = new AbortController();
    if (signal) signal.addEventListener('abort', () => ctl.abort());
    const p = (async () => {
      let lastErr;
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const r = await fetch(url, { signal: ctl.signal });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const data = await r.json();
          _store(url, data);
          return data;
        } catch (e) {
          lastErr = e;
          if (e.name === 'AbortError') throw e;
          await new Promise(res => setTimeout(res, 600 * (attempt + 1)));
        }
      }
      throw lastErr;
    })().finally(() => inflight.delete(url));
    inflight.set(url, { p, ctl });
    return p;
  };

  /* Lecture synchrone du cache (sans réseau) : donnée + fraîcheur, ou null. */
  VX.fetch.peek = function (url) {
    const hit = cache.get(url);
    return hit ? { data: hit.data, age: Date.now() - hit.ts, ts: hit.ts } : null;
  };
  /* Métriques de cache (observabilité §18) : hits / misses / dédup / entrées. */
  VX.fetch.stats = function () {
    const total = _stats.hits + _stats.misses;
    return {
      hits: _stats.hits, misses: _stats.misses, dedup: _stats.dedup,
      hit_rate: total ? Math.round(100 * _stats.hits / total) : null,
      entries: cache.size, inflight: inflight.size,
    };
  };
  /* Invalidation CIBLÉE (clé exacte, préfixe, ou prédicat) — plus de cache.clear() aveugle. */
  VX.fetch.invalidate = function (target) {
    let pred;
    if (typeof target === 'function') pred = target;
    else if (typeof target === 'string') pred = (u) => u === target || u.indexOf(target) === 0;
    else { cache.clear(); schedulePersist(); return; }
    Array.from(cache.keys()).forEach((u) => { if (pred(u)) cache.delete(u); });
    schedulePersist();
  };

  /* stale-while-revalidate : rend le cache TOUT DE SUITE (même périmé), puis
     revalide en fond et rappelle onData si la donnée a changé. Ne vide JAMAIS
     l'écran, ne remplace jamais du valide par du vide (erreur → garde l'ancien).
     Retourne un annulateur : à appeler au changement de page/ticker (anti-hors-ordre). */
  VX.swr = function (url, onData, opts) {
    opts = opts || {};
    const ttl = opts.ttl == null ? 30000 : opts.ttl;
    let alive = true;
    const hit = cache.get(url);
    let servedStr = null;
    if (hit) { servedStr = safeStr(hit.data); try { onData(hit.data, { stale: Date.now() - hit.ts >= ttl, cached: true }); } catch (e) {} }
    const fresh = hit && Date.now() - hit.ts < ttl;
    if (!fresh) {
      VX.fetch(url, { ttl: 0 }).then((data) => {
        if (!alive) return;                       // navigation/ticker changé → ignore (hors-ordre)
        const s = safeStr(data);
        if (s !== servedStr) { try { onData(data, { stale: false, cached: false }); } catch (e) {} }
      }).catch(() => { /* garde l'ancien contenu, jamais de vide */ });
    }
    return function cancel() { alive = false; };
  };
  function safeStr(o) { try { return JSON.stringify(o); } catch (e) { return null; } }
  VX.refresh = {
    _tasks: [], _suspended: false,
    /* opts.persistent : tâche de SHELL (statut global…), survit aux navigations.
       Défaut = tâche de page → intervalle arrêté au teardown (évite les doublons
       de loaders et les fetch fantômes après changement de page). */
    register(fn, intervalMs, label, opts) {
      const task = { fn, intervalMs, label, id: null, persistent: !!(opts && opts.persistent) };
      const run = () => { if (!document.hidden) { try { fn(); } catch (e) { console.error('[vx-refresh]', label, e); } } };
      task.id = setInterval(run, intervalMs);
      this._tasks.push(task);
      return task;
    },
    _clearPage() {
      const keep = [];
      this._tasks.forEach((t) => { if (t.persistent) { keep.push(t); } else { clearInterval(t.id); } });
      this._tasks = keep;
    },
    /* Rejoue les tâches de la page (sans toast, sans vider tout le cache) :
       appelé par live-updates.js quand le serveur annonce une donnée neuve. */
    async runTasks() {
      if (document.hidden) return false;
      await Promise.allSettled(this._tasks.map((t) => { try { return t.fn(); } catch (e) { return null; } }));
      return true;
    },
    async runAll(btn) {
      if (btn) { btn.dataset.state = 'refreshing'; btn.disabled = true; }
      VX.fetch.invalidate();      // vide cache mémoire + persistance (rafraîchissement explicite)
      try {
        await Promise.allSettled(this._tasks.map(t => t.fn()));
        VX.bus.emit('vx:data-refreshed', {});
        if (btn) { btn.dataset.state = 'success'; VX.toast('Données actualisées', 'success'); }
      } catch (e) { if (btn) btn.dataset.state = 'error'; }
      if (btn) setTimeout(() => { btn.dataset.state = 'ready'; btn.disabled = false; }, 900);
    },
  };

  /* ── Cycle de vie de PAGE (navigation client persistante, LOT 2) ──────
     Le routeur (vx-router.js) appelle VX.page._teardown() AVANT de remplacer
     #vx-content : on arrête les tâches/abonnements de la page sortante et on
     exécute ses nettoyages (onLeave). Le shell (statut, live-updates, entités)
     est marqué persistant et n'est jamais touché. */
  VX.page = {
    _gen: 0,
    _leave: [],
    onLeave(fn) { if (typeof fn === 'function') this._leave.push(fn); },
    _teardown() {
      this._leave.forEach((fn) => { try { fn(); } catch (e) {} });
      this._leave = [];
      try { VX.refresh._clearPage(); } catch (e) {}
      try { VX.bus._clearPage(); } catch (e) {}
      try { if (window.VXCharts && VXCharts.destroyAll) VXCharts.destroyAll(); } catch (e) {}
      this._gen++;
    },
  };

  /* ── Fraîcheur : identité visuelle unifiée des données (§8, LOT 5) ──────
     Une SEULE table de seuils (résout l'incohérence des seuils de l'audit) : un
     helper que chaque page adopte pour marquer live / snapshot / sauvegardé /
     stale / recalcul / erreur / offline, de façon discrète et cohérente. */
  VX.freshness = {
    THRESH: { live: 20000, snapshot: 1800000, stale: 2100000 },   // ms : 20 s / 30 min / 35 min — aligné sur la session d'analyse (cadence 30 min)
    LABEL: {
      live: 'Live', snapshot: 'Analyse', saved: 'Sauvegardé',
      stale: 'À actualiser', refreshing: 'Recalcul…', error: 'Erreur', offline: 'Hors ligne',
    },
    assess(o) {
      o = o || {};
      //  L'INSTANT DE RÉFÉRENCE est conservé (`at`) pour que l'évaluation
      //  puisse être REJOUÉE plus tard sans redemander la donnée : un âge
      //  n'est vrai qu'à la seconde où on le calcule.
      const at = (o.ageMs == null) ? null : Date.now() - o.ageMs;
      if (o.offline) return this._r('offline');
      if (o.error) return this._r('error');
      if (o.refreshing) return this._r('refreshing');
      if (o.saved) return this._r('saved');
      const a = o.ageMs;
      if (a == null) return { state: 'unknown', label: '—', tone: 'muted' };
      if (o.live && a < this.THRESH.live) return this._r('live', at, o.live);
      if (a < this.THRESH.snapshot) return this._r('snapshot', at, o.live);
      return this._r('stale', at, o.live);
    },
    _r(state, at, live) {
      const tone = { live: 'pos', snapshot: 'info', saved: 'muted', stale: 'warn',
        refreshing: 'info', error: 'neg', offline: 'neg' }[state] || 'muted';
      const r = { state: state, label: this.LABEL[state] || state, tone: tone };
      if (at != null) { r.at = at; r.live = !!live; }
      return r;
    },
    /* Puce discrète prête à insérer (innerHTML). */
    chip(a) {
      a = a || {};
      const dot = a.state === 'live' ? '<span class="vx-fresh-dot"></span>' : '';
      return '<span class="vx-fresh-chip" data-state="' + a.state + '" title="' + (a.label || '') + '"' +
        (a.at == null ? '' : ' data-at="' + a.at + '" data-was-live="' + (a.live ? '1' : '0') + '"') +
        '>' + dot + (a.label || '') + '</span>';
    },

    /* ── RE-DATAGE (aucune requête) ──────────────────────────────────────
       Un âge affiché est vrai à l'instant où il est peint, et faux ensuite.
       Les pages qui n'enregistrent aucune tâche `VX.refresh` ne repeignent
       jamais — mesuré : 11 lignes de provenance sur 11 figées sur Marchés
       après deux heures, réseau vivant. Et quand le réseau tombe, PLUS AUCUNE
       page ne repeint, y compris celles qui rafraîchissent d'habitude.

       On rejoue donc le seul calcul qui n'a besoin de rien : l'âge se déduit
       de l'horodatage DÉJÀ dans le DOM. Aucun `fetch`, aucune donnée nouvelle,
       aucun chiffre modifié — seule l'étiquette qui date le chiffre est
       remise à l'heure. Un chiffre périmé reste affiché ; il cesse seulement
       de se présenter comme frais. */
    _ms(ts) {
      if (ts == null || ts === '') return null;
      const d = (ts instanceof Date) ? ts
        : new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
      const v = d.getTime();
      return isNaN(v) ? null : v;
    },
    _retick(racine) {
      const doc = racine || document;
      let n = 0;
      doc.querySelectorAll('.vx-update[data-ts] > .vx-update-age').forEach((el) => {
        const ts = Number(el.parentElement.getAttribute('data-ts'));
        if (!isFinite(ts)) return;
        const t = VX.fmt.ago(ts);
        if (el.textContent !== t) { el.textContent = t; n++; }
      });
      doc.querySelectorAll('.vx-fresh-chip[data-at]').forEach((el) => {
        const at = Number(el.getAttribute('data-at'));
        if (!isFinite(at)) return;
        const a = this.assess({ ageMs: Date.now() - at,
          live: el.getAttribute('data-was-live') === '1' });
        if (el.getAttribute('data-state') === a.state) return;
        el.setAttribute('data-state', a.state);
        el.setAttribute('title', a.label || '');
        el.innerHTML = (a.state === 'live' ? '<span class="vx-fresh-dot"></span>' : '')
          + (a.label || '');
        n++;
      });
      return n;
    },
  };

  /* Tâche de SHELL : survit aux navigations, ne demande rien au réseau. 30 s
     est un compromis mesuré — le premier seuil du produit est à 20 s (live),
     donc une puce ne peut pas mentir plus d'une demi-période au-delà. */
  VX.refresh.register(() => VX.freshness._retick(), 30000, 'freshness-retick',
    { persistent: true });

  /* ── Store global minimal (LOT 2 — fondation ; SWR/dédup enrichis au LOT 3) ──
     Vérité partagée du contexte applicatif : session active, ticker courant,
     historique de navigation, prix live (source centrale à venir). Lecture seule
     côté métier — aucun ordre, aucune donnée inventée. */
  VX.store = {
    _s: {
      active_session_id: null, previous_session_id: null, session_status: null,
      active_ticker: null, selected_timeframe: null,
      nav_history: [], live_prices: {}, freshness_map: {},
    },
    get(k) { return this._s[k]; },
    set(k, v) { this._s[k] = v; VX.bus.emit('vx:store-changed', { key: k, value: v }); return v; },
    snapshot() { return Object.assign({}, this._s); },
    pushNav(href) {
      const h = this._s.nav_history;
      if (h[h.length - 1] !== href) h.push(href);
      if (h.length > 30) h.shift();
    },
  };

  /* ── Source de prix CENTRALE (§9, LOT 5) ──────────────────────────────
     Un ticker = un prix partout (shell, Analyse, Portefeuille, Options, listes).
     On distingue explicitement : prix LIVE, prix de RÉFÉRENCE du snapshot (session),
     prix moyen d'ACHAT. On ne remplace JAMAIS silencieusement un prix de scénario/
     référence par le live. Prix invalide → ignoré (jamais de chiffre inventé).
     Les widgets lisent get()/subscribe() → cohérence garantie entre les pages. */
  VX.prices = {
    _m: {},        // SYM -> {live, chg, liveTs, ref, refSession, avgCost}
    _subs: {},
    get(sym) { return sym ? (this._m[String(sym).toUpperCase()] || null) : null; },
    _ok(v) { return v != null && isFinite(v); },
    setLive(sym, price, chg, ts) {
      if (!sym || !this._ok(price)) return;              // jamais de prix inventé
      sym = String(sym).toUpperCase();
      const e = this._m[sym] || (this._m[sym] = {});
      e.live = +price; if (this._ok(chg)) e.chg = +chg; e.liveTs = ts || Date.now();
      try { VX.store._s.live_prices[sym] = e; } catch (x) {}
      this._emit(sym);
    },
    setRef(sym, price, sessionId) {                       // prix figé du snapshot d'analyse
      if (!sym) return;
      sym = String(sym).toUpperCase();
      const e = this._m[sym] || (this._m[sym] = {});
      if (this._ok(price)) { e.ref = +price; e.refSession = sessionId || null; }
      this._emit(sym);
    },
    setAvgCost(sym, price) {
      if (!sym || !this._ok(price)) return;
      sym = String(sym).toUpperCase();
      (this._m[sym] || (this._m[sym] = {})).avgCost = +price;
    },
    subscribe(sym, cb) {
      sym = String(sym).toUpperCase();
      (this._subs[sym] || (this._subs[sym] = [])).push(cb);
      if (this._m[sym]) { try { cb(this._m[sym]); } catch (e) {} }   // valeur courante tout de suite
      return () => { this._subs[sym] = (this._subs[sym] || []).filter((f) => f !== cb); };
    },
    _emit(sym) {
      (this._subs[sym] || []).forEach((cb) => { try { cb(this._m[sym]); } catch (e) {} });
      VX.bus.emit('vx:price:' + sym, this._m[sym]);
    },
  };

  /* Suspendre en arrière-plan, rafraîchir au retour. */
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) VX.bus.emit('vx:data-refreshed', { reason: 'visibility' });
  });

  /* ── PRÉCHAUFFAGE : au chargement du shell, on réchauffe les endpoints légers
     (digest de session + résumé marché) dès que le navigateur est au repos, pour
     que la première navigation vers Aujourd'hui / Marchés soit quasi instantanée.
     Uniquement des GET de lecture, cache client partagé (VX.fetch). Aucun ordre. */
  const _warm = () => {
    ['/api/session/digest', '/api/market/summary'].forEach(u => {
      try { VX.fetch(u, { ttl: 30000, priority: 'low' }).catch(() => {}); } catch (e) {}
    });
  };
  const _schedule = () => (window.requestIdleCallback
    ? requestIdleCallback(_warm, { timeout: 2500 }) : setTimeout(_warm, 900));
  if (document.readyState === 'complete') _schedule();
  else window.addEventListener('load', _schedule, { once: true });

  /*  _toneAttr / _toneCls — LE TON D'UNE TUILE, ET RIEN D'AUTRE.

      Les deux etaient APPELEES par `VX.tile.metric`, `.stat` et `.kpi`, et
      definies NULLE PART — ni ici, ni sur `main`, ni sur `vertex-live`.
      Chaque tuile construite par ces trois helpers levait donc
      `ReferenceError`, et la section qui l'attendait restait vide.

      Deux sorties distinctes parce que le CSS les consomme differemment :
      `data-tone="…"` porte le halo et la bordure de la tuile ; `.vx-…`
      colore un texte. Les melanger produisait des tuiles sans halo ou des
      chiffres sans couleur.

      Un ton INCONNU rend la chaine vide plutot qu'un ton par defaut : une
      tuile neutre se lit « pas de jugement », alors qu'un vert de repli
      affirmerait « positif » sans que rien ne le soutienne.  */
  var _TONS_ATTR = {
    pos: 'pos', positive: 'pos', go: 'go', success: 'success',
    neg: 'neg', negative: 'neg', error: 'error', risk: 'risk',
    warn: 'warn', warning: 'warning', wait: 'wait', over: 'over',
    opt: 'opt', option: 'opt', brand: 'brand', ai: 'ai', cash: 'cash',
    offline: 'offline'
  };
  var _TONS_CLS = {
    pos: 'vx-pos', positive: 'vx-pos', go: 'vx-pos', success: 'vx-pos',
    neg: 'vx-neg', negative: 'vx-neg', error: 'vx-neg', risk: 'vx-neg',
    warn: 'vx-warn', warning: 'vx-warn', wait: 'vx-warn', over: 'vx-warn',
    muted: 'vx-muted', active: 'vx-active'
  };

  function _toneAttr(t) {
    return _TONS_ATTR[String(t == null ? '' : t).toLowerCase()] || '';
  }

  function _toneCls(t) {
    return _TONS_CLS[String(t == null ? '' : t).toLowerCase()] || '';
  }

  /*  VX.tile — systeme de tuiles de la refonte Black Glass, apporte par
      l'integration de `vertex-live`. Les pages du kit l'appellent ; sans
      lui, chaque tuile de metrique et de statistique serait vide.

      La BASE de ce fichier vient de `main` : elle porte VX.swr, VX.store,
      VX.fetch (cache + invalidation), VX.freshness, VX.prices, VX.regime,
      VX.page — dix sous-systemes que `vertex-live` n'a pas. Prendre le
      fichier de live en entier, comme je l'avais fait d'abord, jetait toute
      cette couche de continuite ; `tests/test_continuity_data.py` l'a dit.  */
  VX.tile = {
    /* Micro-barre inline (Qualité, PoP…) : le CHIFFRE porte le sens, la barre
       n'est qu'un repère visuel (aria-hidden). Une définition partagée au lieu
       des deux blocs inline identiques d'options-intel.js et options-symbol.js.
       o = {v (0-100), unit, tone ('pos'|'warn'|'neg'|'opt'|''), dec} ; v absent → « — ». */
    microbar: function (o) {
      o = o || {};
      var v = (o.v == null || isNaN(o.v)) ? null : Number(o.v);
      if (v == null) return '<span class="vx2-absent">—</span>';
      var w = Math.max(3, Math.min(100, Math.abs(v)));
      var txt = VX.fmt.num(v, o.dec == null ? 0 : o.dec) + (o.unit ? VX.esc(o.unit) : '');
      return '<span class="vx-microbar" data-tone="' + _toneAttr(o.tone) + '">'
        + '<i aria-hidden="true"><b style="width:' + w + '%"></b></i>'
        + '<span>' + txt + '</span></span>';
    },
    /* Métrique riche : label (+ title) + valeur (+ unité) (+ chip de comparaison)
       (+ mini-barre 0-100 avec repère médian optionnel). Les options additives
       cmp / mid / kTitle sont OFF par défaut → rétrocompatible. */
    metric: function (o) {
      o = o || {};
      var v = VX.fmt.nd(o.v);
      var absent = (v === '—');
      var u = o.unit ? '<span class="vx-metric-u">' + VX.esc(o.unit) + '</span>' : '';
      var cmp = (o.cmp && !absent) ? '<div class="vx-metric-cmp">' + o.cmp + '</div>' : '';
      var mid = (o.mid != null) ? '<b style="left:' + (o.mid | 0) + '%"></b>' : '';
      var bar = (o.bar != null && !absent)
        ? '<div class="vx-metric-bar"><i style="width:' + Math.max(3, Math.min(100, o.bar)) + '%"></i>' + mid + '</div>' : '';
      var kt = o.kTitle ? ' title="' + VX.esc(o.kTitle) + '"' : '';
      /* `meta` (additif, OFF par défaut) : une ligne de contexte sous la valeur
         — population, dispersion, bande moteur — pour que le chiffre ne soit
         jamais nu. Texte échappé : jamais de HTML injecté par un appelant. */
      var meta = o.meta ? '<span class="vx-metric-meta">' + VX.esc(o.meta) + '</span>' : '';
      return '<div class="vx-metric" data-tone="' + (absent ? '' : _toneAttr(o.tone)) + '">'
        + '<span class="vx-metric-k"' + kt + '>' + VX.esc(o.k) + '</span>'
        + '<span class="vx-metric-v">' + v + u + '</span>' + cmp + bar + meta + '</div>';
    },
    /* Stat à halo : label + valeur (+ sous-légende) (+ extra, ex. sparkline SVG).
       Option additive `vfs` (taille de valeur, px) OFF par défaut → rétrocompatible. */
    stat: function (o) {
      o = o || {};
      var vstyle = o.vfs ? ' style="font-size:' + (o.vfs | 0) + 'px"' : '';
      var sub = (o.sub != null && o.sub !== '') ? '<div class="vx-stat-sub">' + VX.esc(o.sub) + '</div>' : '';
      return '<div class="vx-stat" data-tone="' + _toneAttr(o.tone) + '">'
        + '<div class="vx-stat-k">' + VX.esc(o.k) + '</div>'
        + '<div class="vx-stat-v"' + vstyle + '>' + VX.fmt.nd(o.v) + '</div>' + sub + (o.extra || '') + '</div>';
    },
    /* KPI dans une carte compacte : label + valeur + delta (ton par classe). */
    kpi: function (o) {
      o = o || {};
      var tc = _toneCls(o.tone);
      var span = o.span ? ' style="grid-column:span ' + (o.span | 0) + '"' : '';
      var delta = (o.delta != null && o.delta !== '')
        ? '<span class="vx-kpi-delta ' + (tc || 'vx-muted') + '">' + o.delta + '</span>' : '';
      return '<div class="vx-card vx-card--compact vx-kpi"' + span + '>'
        + '<span class="vx-kpi-label">' + VX.esc(o.label) + '</span>'
        + '<span class="vx-kpi-value' + (tc ? ' ' + tc : '') + '">' + VX.fmt.nd(o.value) + '</span>' + delta + '</div>';
    },
  };

})();
