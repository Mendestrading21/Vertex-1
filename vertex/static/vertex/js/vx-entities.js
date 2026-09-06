/* Vertex Entity Actions (§17-19) — LA couche unique favoris / watchlist /
   suivis / positions / alertes / notes / thèses.
   Schémas localStorage historiques PRÉSERVÉS À L'IDENTIQUE (audit §3) :
   - myFavs   = ["NVDA", ...]
   - myNotes  = {"NVDA": "note"}
   - myRecos  = suivis ⭐ [{id,kind:'STK',sym,entry_spot,stop,tgt,followed}]
   - myTrades = positions [{id,type,sym,exp,strike,right,qty,cost,added,entrySnap,note}]
   - myTradesClosed = [{sym,type,strike,exp,qty,cost,exit,added,closed,note}]
   - vxAlerts = [{id,sym,cond:'above'|'below'|'target',level,note,created,active}]
   - vxJournal = entrées de journal (schéma journal.py)
   - vxWatchlist (NOUVEAU, ajouté aux 4 listes de sync) =
       [{sym,priority,thesis,zone,catalyst,added,review,status}]
   Sync desk : POST /api/desk {ts, data} — last-writer-wins, INCHANGÉ. */
(function () {
  'use strict';
  const VX = window.VX;

  /* Clés synchronisées — SOURCE UNIQUE servie du contrat desk (lot 37) ;
     le repli inline de system_page doit rester identique (gardien lot 381). */
  const DESK_KEYS = ['myTrades', 'myTradesClosed', 'myTradesEquity', 'myRecos',
    'myRecosClosed', 'myCapital', 'simCash', 'simStart', 'simTrades', 'simClosed',
    'myFavs', 'myNotes', 'vxJournal', 'myTradeLog', 'vxVault', 'vxAlerts',
    'vxWatchlist'];

  const today = () => new Date().toISOString().slice(0, 10);
  function get(key, fallback) {
    try { const v = JSON.parse(localStorage.getItem(key)); return v === null || v === undefined ? fallback : v; }
    catch (e) { return fallback; }
  }
  function set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); localStorage.setItem('deskTs', String(Date.now())); } catch (e) {}
    schedulePush();
  }

  /* ── Anti-doublon : le store ne contient JAMAIS de doublon ──────────
     uniqBy garde la 1re occurrence par clé sémantique. */
  function uniqBy(arr, keyFn) {
    const seen = new Set(); const out = [];
    (Array.isArray(arr) ? arr : []).forEach(x => {
      let k; try { k = keyFn(x); } catch (e) { k = x; }
      if (!seen.has(k)) { seen.add(k); out.push(x); }
    });
    return out;
  }
  const _posKey = t => [String(t.sym || '').toUpperCase(), t.type, t.strike, t.exp, t.right, t.qty, t.cost].join('|');
  const _alertKey = a => [String(a.sym || '').toUpperCase(), a.cond, a.level, a.active].join('|');
  const _followKey = r => (r.kind || 'STK') + ':' + String(r.sym || '').toUpperCase();
  /* Nettoyage rétroactif SÛR (aucune perte) : dédup par clé sémantique des listes
     où un doublon n'a aucun sens. Les POSITIONS ne sont PAS purgées (deux lots
     identiques peuvent être légitimes) ; seul l'ajout d'un doublon EXACT est bloqué.
     Écriture directe (pas de bump deskTs) → ne perturbe pas la sync last-writer-wins. */
  function dedupeStore() {
    try {
      const put = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
      const favs0 = get('myFavs', []) || [];
      const favs1 = uniqBy(favs0.map(s => String(s).toUpperCase()), s => s);
      if (JSON.stringify(favs0) !== JSON.stringify(favs1)) put('myFavs', favs1);
      const wl0 = get('vxWatchlist', []) || []; const wseen = {};
      wl0.forEach(w => { if (w && w.sym) { w.sym = String(w.sym).toUpperCase(); wseen[w.sym] = w; } });
      const wl1 = Object.keys(wseen).map(k => wseen[k]);
      if (wl0.length !== wl1.length) put('vxWatchlist', wl1);
      const rec0 = get('myRecos', []) || []; const rec1 = uniqBy(rec0, _followKey);
      if (rec0.length !== rec1.length) put('myRecos', rec1);
      const al0 = get('vxAlerts', []) || []; const al1 = uniqBy(al0, _alertKey);
      if (al0.length !== al1.length) put('vxAlerts', al1);
    } catch (e) {}
  }

  /* ── Sync /api/desk (protocole historique inchangé) ─────────────── */
  let pushTimer = null;
  function schedulePush() { clearTimeout(pushTimer); pushTimer = setTimeout(() => { pushTimer = null; pushNow(); }, 1200); }

  /* LOT 604 — la synchro du bureau échouait EN SILENCE, deux fois dans une
     ligne : `fetch(...).catch(() => {})` avalait l'échec réseau, ET un 4xx/5xx
     ne déclenchait même pas ce `catch` (fetch ne rejette que sur échec réseau ;
     une réponse d'erreur RÉSOUT la promesse, et `r.ok` n'était jamais lu). Un
     refus du serveur était donc totalement invisible. Ces données sont les
     données PERSONNELLES de l'utilisateur — invariant produit : ce qui échoue
     se dit. Rien n'est perdu (localStorage garde tout, le push suivant
     rattrape) ; c'est ce que le message annonce, sans dramatiser. */
  const SYNC_ALERTE_MS = 600000;          // au plus une alerte visible / 10 min
  let derniereAlerteSync = 0;
  function syncAlerte(message) {
    const t = Date.now();
    if (t - derniereAlerteSync < SYNC_ALERTE_MS) return;
    derniereAlerteSync = t;
    try { VX.toast(message, 'warn', 5200); } catch (e) {}
  }
  function syncEtat(etat, detail) {
    try { VX.store.set('desk_sync', etat); } catch (e) {}
    if (etat === 'ok') return;
    syncAlerte('Synchronisation du bureau impossible (' + detail + ') — tes données '
      + 'restent sur cet appareil et repartiront à la prochaine réussite.');
  }

  function pushNow() {
    try {
      const data = {};
      DESK_KEYS.forEach(k => { const v = localStorage.getItem(k); if (v != null) data[k] = v; });
      const ts = Number(localStorage.getItem('deskTs') || Date.now());
      fetch('/api/desk', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ts, data }) })
        .then(r => { syncEtat(r.ok ? 'ok' : 'error', 'refus du serveur, HTTP ' + r.status); })
        .catch(() => { syncEtat('error', 'serveur injoignable'); });
    } catch (e) { syncEtat('error', 'écriture locale impossible'); }
  }
  /* LOT 607 — la LECTURE échouait en silence, comme l'écriture avant le 604 :
     `r.ok` n'était pas lu (604-A, sur l'autre chemin) et le `catch` était vide.
     Le coût est plus grand qu'il n'y paraît : sur un navigateur neuf dont le GET
     échoue, le bureau s'affiche VIDE — et « aucun trade déclaré » devient
     indiscernable de « bureau non synchronisé », alors que le serveur, lui, a
     les données. C'est l'invariant produit pris à l'envers : ce n'est pas une
     donnée absente présentée comme réelle, c'est une donnée RÉELLE présentée
     comme absente. Rien n'est perdu ni écrasé — la lecture reste en lecture. */
  async function pull() {
    try {
      const r = await fetch('/api/desk');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      const localTs = Number(localStorage.getItem('deskTs') || 0);
      if (d && d.ts && d.data) {
        if (d.ts > localTs) { /* serveur plus récent : ne jamais écraser du plus récent par du plus ancien */
          Object.entries(d.data).forEach(([k, v]) => { if (DESK_KEYS.includes(k)) try { localStorage.setItem(k, v); } catch (e) {} });
          try { localStorage.setItem('deskTs', String(d.ts)); } catch (e) {}
          dedupeStore(); /* la sync peut ramener des doublons → on nettoie */
          VX.bus.emit('vx:data-refreshed', { reason: 'desk-pull' });
          ['vx:favorites-changed', 'vx:watchlist-changed', 'vx:follow-changed', 'vx:position-changed', 'vx:alert-changed'].forEach(ev => VX.bus.emit(ev, { source: 'sync' }));
        } else if (localTs > d.ts) pushNow();
      } else if (!d || !d.ts) {
        if (localTs) pushNow();
      }
      try { VX.store.set('desk_sync', 'ok'); } catch (e2) {}
    } catch (e) {
      try { VX.store.set('desk_sync', 'read-error'); } catch (e2) {}
      syncAlerte('Bureau non synchronisé : tes données du serveur n’ont pas pu être '
        + 'chargées (' + ((e && e.message) || 'erreur réseau') + '). Ce qui s’affiche '
        + 'vient de cet appareil — n’en conclus pas que c’est vide.');
    }
  }
  dedupeStore(); pull(); setInterval(() => { if (!document.hidden) pull(); }, 120000);
  /* Flush du push au déchargement : une écriture suivie d'une navigation
     immédiate ne doit jamais se perdre (le débounce n'attend pas la page
     suivante — sendBeacon survit à l'unload). */
  window.addEventListener('pagehide', () => {
    if (pushTimer === null) return;
    clearTimeout(pushTimer); pushTimer = null;
    try {
      const data = {};
      DESK_KEYS.forEach(k => { const v = localStorage.getItem(k); if (v != null) data[k] = v; });
      const ts = Number(localStorage.getItem('deskTs') || Date.now());
      const blob = new Blob([JSON.stringify({ ts, data })], { type: 'application/json' });
      if (!navigator.sendBeacon || !navigator.sendBeacon('/api/desk', blob)) pushNow();
    } catch (e) {}
  });

  /* ── Store ───────────────────────────────────────────────────────── */
  const E = window.VXEntities = {
    DESK_KEYS,
    /* Favoris (étoile, accès rapide) */
    favorites() { return uniqBy((get('myFavs', []) || []).map(s => String(s).toUpperCase()), s => s); },
    isFavorite(sym) { return this.favorites().includes(String(sym).toUpperCase()); },
    toggleFavorite(sym) {
      sym = String(sym).toUpperCase();
      const favs = this.favorites();
      const i = favs.indexOf(sym);
      if (i >= 0) { favs.splice(i, 1); VX.toast(`${sym} retiré des favoris`); }
      else { favs.push(sym); VX.toast(`${sym} ajouté aux favoris`, 'success'); }
      set('myFavs', favs);
      VX.bus.emit('vx:favorites-changed', { sym, active: i < 0 });
      return i < 0;
    },
    /* Watchlist (surveillance active, riche) */
    watchlist() { return uniqBy(get('vxWatchlist', []) || [], w => String(w && w.sym || '').toUpperCase()); },
    inWatchlist(sym) { return this.watchlist().some(w => w.sym === String(sym).toUpperCase()); },
    addToWatchlist(sym, fields) {
      sym = String(sym).toUpperCase();
      const list = this.watchlist().filter(w => w.sym !== sym);
      list.push(Object.assign({ sym, priority: 'normal', thesis: '', zone: '', catalyst: '',
        added: today(), review: '', status: 'a_etudier' }, fields || {}));
      set('vxWatchlist', list);
      VX.bus.emit('vx:watchlist-changed', { sym, active: true });
      VX.toast(`${sym} ajouté à la watchlist`, 'success');
    },
    removeFromWatchlist(sym) {
      sym = String(sym).toUpperCase();
      set('vxWatchlist', this.watchlist().filter(w => w.sym !== sym));
      VX.bus.emit('vx:watchlist-changed', { sym, active: false });
      VX.toast(`${sym} retiré de la watchlist`);
    },
    /* Suivis ⭐ (setup suivi — schéma myRecos historique) */
    follows() { return uniqBy(get('myRecos', []) || [], _followKey); },
    isFollowed(sym) { return this.follows().some(r => r.sym === String(sym).toUpperCase() && r.kind === 'STK'); },
    followStock(sym, { entry_spot = null, stop = null, tgt = null, decision = '', score = null } = {}) {
      sym = String(sym).toUpperCase();
      const list = this.follows();
      if (this.isFollowed(sym)) return;
      list.push({ id: Date.now(), kind: 'STK', sym, entry_spot, stop, tgt, followed: today() });
      set('myRecos', list);
      /* Moteur de SUIVI serveur (§14) : capture le prix de référence + SPY à
         l'instant du clic → performance hypothétique horodatée. Best-effort ;
         le bookmark local reste même si l'API est indisponible. */
      try {
        fetch('/api/tracking', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entity_type: 'STOCK', symbol: sym, decision: decision || '', score: score })
        }).catch(function () { });
      } catch (e) { /* jamais bloquant */ }
      VX.bus.emit('vx:follow-changed', { sym, active: true });
      VX.toast(`Suivi créé sur ${sym} — performance hypothétique depuis maintenant`, 'success');
    },
    unfollow(sym) {
      sym = String(sym).toUpperCase();
      set('myRecos', this.follows().filter(r => !(r.sym === sym && r.kind === 'STK')));
      VX.bus.emit('vx:follow-changed', { sym, active: false });
      VX.toast(`Suivi retiré sur ${sym}`);
    },
    /* Positions (schéma myTrades historique — AUCUN ordre : registre déclaratif) */
    positions() { return get('myTrades', []); },
    closedPositions() { return get('myTradesClosed', []); },
    hasPosition(sym) { return this.positions().some(t => t.sym === String(sym).toUpperCase()); },
    addPosition(fields) {
      const t = Object.assign({ id: Date.now(), type: 'STK', sym: '', exp: null,
        strike: null, right: null, qty: 1, cost: 0, added: today(),
        entrySnap: {}, note: '' }, fields || {});
      t.sym = String(t.sym).toUpperCase();
      if (!t.sym || !(t.qty > 0)) { VX.toast('Position invalide (ticker/quantité)', 'error'); return null; }
      const list = this.positions();
      /* Anti-doublon EXACT : bloque un ré-enregistrement identique (double-clic) ;
         deux lots réellement distincts (qté/coût différents) restent permis. */
      if (list.some(x => _posKey(x) === _posKey(t))) {
        VX.toast(`Position ${t.sym} identique déjà enregistrée`, 'error'); return null;
      }
      list.push(t); set('myTrades', list);
      this._log(t.sym, 'OPEN', `${t.type} ${t.qty} @ ${t.cost}`, t.id);
      VX.bus.emit('vx:position-changed', { sym: t.sym, action: 'open' });
      VX.toast(`Position ${t.sym} enregistrée`, 'success');
      return t;
    },
    updatePosition(id, fields) {
      const list = this.positions();
      const t = list.find(x => String(x.id) === String(id)); if (!t) return;
      Object.assign(t, fields || {}); set('myTrades', list);
      VX.bus.emit('vx:position-changed', { sym: t.sym, action: 'update' });
      VX.toast(`Position ${t.sym} modifiée`, 'success');
    },
    /* recordExit : clôture DÉCLARATIVE d'une position dans le desk local
       (localStorage → journal). AUCUN ordre n'est envoyé — analyse seule. */
    recordExit(id, exitAmount, note) {
      const list = this.positions();
      const i = list.findIndex(x => String(x.id) === String(id)); if (i < 0) return;
      const t = list.splice(i, 1)[0];
      const closed = this.closedPositions();
      closed.push({ sym: t.sym, type: t.type, strike: t.strike, exp: t.exp,
        qty: t.qty, cost: t.cost, exit: Number(exitAmount) || 0,
        added: t.added, closed: today(), note: note || t.note || '' });
      set('myTrades', list); set('myTradesClosed', closed);
      /* entrée de journal automatique (comportement historique conservé) */
      const jr = get('vxJournal', []);
      const invested = t.cost || 0; /* schéma desk : cost = TOTAL investi */
      const recovered = Number(exitAmount) || 0;
      jr.push({ id: Date.now() + 1, ticker: t.sym, tf: 'swing',
        dir: 'LONG', reason: '', entry: t.cost, stop: t.entrySnap?.stop ?? '',
        tp: t.entrySnap?.tgt ?? '', risk: '', emo: '', conf: '', disc: '',
        trigger: '', result: recovered >= invested ? 'WIN' : 'LOSS',
        exit: recovered, pnl: Math.round((recovered - invested) * 100) / 100,
        lesson: '', mistake: '', date: today(), auto: true, kind: t.type,
        strike: t.strike, invested, recovered });
      set('vxJournal', jr);
      this._log(t.sym, 'CLOSE', `sortie ${recovered}`, t.id);
      VX.bus.emit('vx:position-changed', { sym: t.sym, action: 'close' });
      VX.toast(`Position ${t.sym} clôturée (journal mis à jour)`, 'success');
    },
    /* deletePosition : suppression PURE d'une saisie du registre (ticker/quantité
       erronés) — retirée de myTrades, AUCUN passage au journal, AUCUN ordre.
       Différent de recordExit qui journalise une sortie réelle. */
    deletePosition(id) {
      const list = this.positions();
      const t = list.find(x => String(x.id) === String(id)); if (!t) return false;
      set('myTrades', list.filter(x => x.id !== id));
      this._log(t.sym, 'DELETE', 'position retirée du registre', id);
      VX.bus.emit('vx:position-changed', { sym: t.sym, action: 'delete' });
      VX.toast(`Position ${t.sym} supprimée du registre`, 'success');
      return true;
    },
    /* Alertes (schéma vxAlerts historique — évaluées côté serveur) */
    alerts() { return uniqBy(get('vxAlerts', []) || [], _alertKey); },
    hasAlert(sym) { return this.alerts().some(a => a.sym === String(sym).toUpperCase() && a.active); },
    addAlert(sym, cond, level, note) {
      sym = String(sym).toUpperCase();
      const list = this.alerts();
      /* Anti-doublon : une alerte active identique (sym·condition·niveau) ne se crée pas deux fois. */
      const _c = cond || 'above', _l = Number(level);
      if (list.some(a => a.active && a.sym === sym && a.cond === _c && a.level === _l)) {
        VX.toast(`Alerte identique déjà active sur ${sym}`, 'error'); return;
      }
      list.push({ id: Date.now(), sym, cond: cond || 'above', level: Number(level),
        note: note || '', created: new Date().toISOString(), active: true });
      set('vxAlerts', list);
      VX.bus.emit('vx:alert-changed', { sym, active: true });
      VX.toast(`Alerte créée sur ${sym} (${cond} ${level})`, 'success');
    },
    removeAlert(id) {
      const list = this.alerts(); const a = list.find(x => String(x.id) === String(id));
      set('vxAlerts', list.filter(x => x.id !== id));
      VX.bus.emit('vx:alert-changed', { sym: a?.sym, active: false });
    },
    /* Notes & thèses */
    notes() { return get('myNotes', {}); },
    note(sym) { return this.notes()[String(sym).toUpperCase()] || ''; },
    setNote(sym, text) {
      sym = String(sym).toUpperCase();
      const n = this.notes();
      if (text) n[sym] = text; else delete n[sym];
      set('myNotes', n);
      VX.bus.emit('vx:thesis-changed', { sym });
      VX.toast('Note enregistrée', 'success');
    },
    journal() { return get('vxJournal', []); },
    addJournalEntry(entry) {
      const jr = this.journal();
      jr.push(Object.assign({ id: Date.now(), date: today() }, entry));
      set('vxJournal', jr);
      VX.toast('Entrée de journal enregistrée', 'success');
    },
    capital() { const c = get('myCapital', null); return c === null ? null : Number(c); },
    equity() { return get('myTradesEquity', []); },
    _log(sym, ev, txt, tid) {
      const log = get('myTradeLog', []);
      const d = new Date();
      log.push({ ts: Date.now(), d: d.toISOString().slice(0, 16).replace('T', ' '), sym, ev, txt, tid });
      set('myTradeLog', log.slice(-400));
    },
    /* Badges d'état d'un ticker (§18) */
    badges(sym) {
      sym = String(sym).toUpperCase();
      const out = [];
      if (this.isFavorite(sym)) out.push('<span class="vx-badge vx-badge-entity" data-kind="fav">★ Favori</span>');
      if (this.inWatchlist(sym)) out.push('<span class="vx-badge vx-badge-entity" data-kind="watch">Watchlist</span>');
      if (this.isFollowed(sym)) out.push('<span class="vx-badge vx-badge-entity" data-kind="follow">Suivi actif</span>');
      if (this.hasPosition(sym)) out.push('<span class="vx-badge vx-badge-entity" data-kind="position">Position</span>');
      if (this.hasAlert(sym)) out.push('<span class="vx-badge vx-badge-entity" data-kind="alert">Alerte active</span>');
      return out.join(' ');
    },
  };

  /* ── Menu d'actions universel (§17) ─────────────────────────────── */
  E.actionsFor = function (sym, contract) {
    sym = String(sym).toUpperCase();
    const acts = [
      { label: 'Ouvrir l’analyse', run: () => VX.openAnalysis(sym) },
      { label: E.isFavorite(sym) ? 'Retirer des favoris' : 'Ajouter aux favoris', run: () => E.toggleFavorite(sym) },
      { label: E.inWatchlist(sym) ? 'Retirer de la watchlist' : 'Ajouter à la watchlist', run: () => E.inWatchlist(sym) ? E.removeFromWatchlist(sym) : E.openAddModal(sym, 'watchlist') },
      { label: E.isFollowed(sym) ? 'Modifier le suivi' : 'Créer un suivi', run: () => E.openAddModal(sym, 'follow') },
      { label: 'Créer une alerte', run: () => E.openAddModal(sym, 'alert') },
      { label: 'Ajouter une position', run: () => E.openAddModal(sym, 'position', contract) },
      { sep: true },
      { label: 'Ouvrir les options', run: () => { VX.context.save({ selectedSymbol: sym }); location.href = '/opportunities?view=options&sym=' + sym; } },
      { label: 'Ajouter une note / thèse', run: () => E.openAddModal(sym, 'note') },
      { label: 'Ouvrir le journal', run: () => { VX.context.save(); location.href = '/journal?view=journal&sym=' + sym; } },
      { label: 'Copier le ticker', run: () => { navigator.clipboard?.writeText(sym); VX.toast(sym + ' copié'); } },
      { label: 'Ouvrir TradingView ↗', run: () => window.open('https://www.tradingview.com/chart/?symbol=' + encodeURIComponent(sym), '_blank', 'noopener') },
    ];
    return acts;
  };
  /* Menu contextuel positionné (clavier: ↑↓ Entrée Échap) */
  E.openMenu = function (sym, anchorEl, contract) {
    E._renderMenu(E.actionsFor(sym, contract), anchorEl);
  };
  /* Rendu générique d'un menu d'actions [{label,run}|{sep}] ancré sur un élément. */
  E._renderMenu = function (acts, anchorEl) {
    const menu = document.getElementById('vx-context-menu');
    menu.innerHTML = acts.map((a, i) => a.sep ? '<div class="vx-sep"></div>' :
      `<button role="menuitem" data-i="${i}">${a.label}</button>`).join('');
    const r = anchorEl.getBoundingClientRect();
    menu.style.left = Math.min(r.left, window.innerWidth - 250) + 'px';
    menu.style.top = Math.min(r.bottom + 4, window.innerHeight - 320) + 'px';
    menu.dataset.open = '1';
    const btns = [...menu.querySelectorAll('button')];
    let sel = 0; btns[0]?.focus();
    function highlight() { btns.forEach((b, i) => b.dataset.active = i === sel ? '1' : '0'); btns[sel]?.focus(); }
    menu.onkeydown = (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(btns.length - 1, sel + 1); highlight(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(0, sel - 1); highlight(); }
      else if (e.key === 'Enter') { e.preventDefault(); btns[sel]?.click(); }
    };
    btns.forEach(b => b.addEventListener('click', () => {
      menu.dataset.open = '0';
      acts[+b.dataset.i].run();
    }));
    const close = (ev) => { if (!menu.contains(ev.target)) { menu.dataset.open = '0'; document.removeEventListener('mousedown', close); } };
    setTimeout(() => document.addEventListener('mousedown', close), 0);
  };
  /* Délégation globale : tout élément [data-entity-menu="SYM"] ouvre le menu. */
  document.addEventListener('click', (e) => {
    const closeTrigger = e.target.closest('[data-close-pos]');
    if (closeTrigger) { e.preventDefault(); e.stopPropagation(); E.openClosePosition(Number(closeTrigger.dataset.closePos)); return; }
    const posTrigger = e.target.closest('[data-position-menu]');
    if (posTrigger) { e.preventDefault(); e.stopPropagation(); E.openPositionMenu(Number(posTrigger.dataset.positionMenu), posTrigger); return; }
    const trigger = e.target.closest('[data-entity-menu]');
    if (trigger) { e.preventDefault(); e.stopPropagation(); E.openMenu(trigger.dataset.entityMenu, trigger); return; }
    /* Un bouton Aperçu ([data-inspect]) DANS une ligne cliquable : c'est
       l'inspecteur qui gère, pas la navigation vers la fiche complète. */
    if (e.target.closest('[data-inspect]')) return;
    const open = e.target.closest('[data-open-analysis]');
    if (open) { e.preventDefault(); VX.openAnalysis(open.dataset.openAnalysis); }
  });
  /* Clavier : Enter/Espace activent les contrôles délégués non natifs
     (tickers role="button", menus d'entité) — même chemin que le clic. */
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const el = e.target.closest && e.target.closest('[data-open-analysis],[data-entity-menu],[data-position-menu]');
    if (!el) return;
    if (['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) return;
    e.preventDefault(); el.click();
  });

  /* ── + Ajouter : formulaire progressif (§19) ─────────────────────── */
  E.openAddModal = function (presetSym, presetDest, contract) {
    const destinations = [
      ['favorite', 'Favori'], ['watchlist', 'Watchlist'], ['follow', 'Suivi'],
      ['position', 'Position'], ['alert', 'Alerte'], ['note', 'Thèse / note'],
    ];
    let step = presetSym ? (presetDest ? 3 : 2) : 1;
    let sym = presetSym || '', dest = presetDest || '';
    function stepsBar() {
      return `<div class="vx-steps">${[1, 2, 3].map(i => `<span data-done="${step >= i ? 1 : 0}"></span>`).join('')}</div>`;
    }
    function render() {
      let body = stepsBar(); let footer = '';
      if (step === 1) {
        body += `<div class="vx-field"><label for="vx-add-sym">Ticker</label>
          <input class="vx-input" id="vx-add-sym" placeholder="ex. NVDA" value="${sym}"
            autocomplete="off" style="text-transform:uppercase" /></div>
          <div class="vx-help">Recherchez l’actif puis choisissez la destination.</div>`;
        footer = '<button class="vx-btn vx-btn-primary" id="vx-add-next">Continuer</button>';
      } else if (step === 2) {
        body += `<div class="vx-flex vx-mb3"><span class="vx-ticker" style="font-size:18px">${sym}</span>${E.badges(sym)}</div>
          <div class="vx-flex vx-wrap vx-gap3">` +
          destinations.map(([id, label]) =>
            `<button class="vx-btn" data-dest="${id}">${label}</button>`).join('') + '</div>';
      } else {
        body += `<div class="vx-flex vx-mb3"><span class="vx-ticker" style="font-size:18px">${sym}</span>
          <span class="vx-badge">${destinations.find(d => d[0] === dest)?.[1] || dest}</span></div>` + detailForm();
        footer = '<button class="vx-btn vx-btn-primary" id="vx-add-confirm">Confirmer</button>';
      }
      VX.shell.openModal('Ajouter', body, footer);
      wire();
    }
    function detailForm() {
      if (dest === 'favorite') return '<div class="vx-help">Aucun détail requis — l’étoile donne un accès rapide permanent.</div>';
      if (dest === 'watchlist') return `
        <div class="vx-form-row">
          <div class="vx-field"><label>Priorité</label><select class="vx-select" id="f-priority">
            <option value="haute">Haute</option><option value="normal" selected>Normale</option><option value="basse">Basse</option></select></div>
          <div class="vx-field"><label>Zone souhaitée</label><input class="vx-input" id="f-zone" placeholder="ex. 480-495" /></div>
        </div>
        <div class="vx-field"><label>Thèse courte</label><input class="vx-input" id="f-thesis" placeholder="pourquoi surveiller ?" /></div>
        <div class="vx-field"><label>Catalyseur</label><input class="vx-input" id="f-catalyst" placeholder="earnings, produit…" /></div>`;
      if (dest === 'follow') return `
        <div class="vx-form-row">
          <div class="vx-field"><label>Entrée visée</label><input class="vx-input" id="f-entry" type="number" step="any" /></div>
          <div class="vx-field"><label>Stop (invalidation)</label><input class="vx-input" id="f-stop" type="number" step="any" /></div>
        </div>
        <div class="vx-field"><label>Objectif</label><input class="vx-input" id="f-tgt" type="number" step="any" /></div>`;
      if (dest === 'alert') return `
        <div class="vx-form-row">
          <div class="vx-field"><label>Condition</label><select class="vx-select" id="f-cond">
            <option value="above">Franchit à la hausse</option>
            <option value="below">Casse à la baisse</option>
            <option value="target">Atteint la cible</option></select></div>
          <div class="vx-field"><label>Niveau</label><input class="vx-input" id="f-level" type="number" step="any" required /></div>
        </div>
        <div class="vx-field"><label>Note</label><input class="vx-input" id="f-note" placeholder="contexte de l’alerte" /></div>
        <div class="vx-help">Évaluée côté serveur toutes les 60 s sur données réelles.</div>`;
      if (dest === 'position') {
        const c = contract || {};
        return `
        <div class="vx-form-row">
          <div class="vx-field"><label>Type</label><select class="vx-select" id="f-type">
            <option value="STK" ${!c.right ? 'selected' : ''}>Action</option>
            <option value="CALL" ${c.right === 'C' ? 'selected' : ''}>CALL</option>
            <option value="PUT" ${c.right === 'P' ? 'selected' : ''}>PUT</option></select></div>
          <div class="vx-field"><label>Quantité</label><input class="vx-input" id="f-qty" type="number" min="1" value="1" /></div>
        </div>
        <div class="vx-form-row">
          <div class="vx-field"><label>Prix unitaire (prime PAR ACTION si option — le coût total est calculé)</label>
            <input class="vx-input" id="f-cost" type="number" step="any" value="${c.mid ?? ''}" /></div>
          <div class="vx-field"><label>Stop sous-jacent</label><input class="vx-input" id="f-stop" type="number" step="any" value="${c.stop ?? ''}" /></div>
        </div>
        <div class="vx-form-row">
          <div class="vx-field"><label>Strike (option)</label><input class="vx-input" id="f-strike" type="number" step="any" value="${c.strike ?? ''}" /></div>
          <div class="vx-field"><label>Expiration (option)</label><input class="vx-input" id="f-exp" placeholder="YYYY-MM-DD" value="${c.expiry ?? ''}" /></div>
        </div>
        <div class="vx-form-row">
          <div class="vx-field"><label>Objectif (sous-jacent)</label><input class="vx-input" id="f-tgt" type="number" step="any" value="${c.tgt ?? ''}" /></div>
          <div class="vx-field"><label>Devise</label><select class="vx-select" id="f-ccy">
            <option value="USD" selected>USD</option><option value="CHF">CHF</option>
            <option value="EUR">EUR</option><option value="CAD">CAD</option></select></div>
        </div>
        <div class="vx-form-row">
          <div class="vx-field"><label>Stratégie (libre)</label><input class="vx-input" id="f-strategy" placeholder="ex. swing 6 sem., LEAPS…" /></div>
          <div class="vx-field"><label>Frais (totaux)</label><input class="vx-input" id="f-fees" type="number" step="any" /></div>
        </div>
        <div class="vx-help">Registre déclaratif — Vertex n’envoie JAMAIS un ordre.</div>`;
      }
      if (dest === 'note') return `
        <div class="vx-field"><label>Thèse / note</label>
        <textarea class="vx-textarea" id="f-text">${E.note(sym)}</textarea></div>`;
      return '';
    }
    function confirmAdd() {
      const v = (id) => document.getElementById(id)?.value?.trim();
      const n = (id) => { const x = v(id); return x === '' || x === undefined ? null : Number(x); };
      if (dest === 'favorite') { if (!E.isFavorite(sym)) E.toggleFavorite(sym); }
      else if (dest === 'watchlist') E.addToWatchlist(sym, { priority: v('f-priority'), zone: v('f-zone'), thesis: v('f-thesis'), catalyst: v('f-catalyst') });
      else if (dest === 'follow') {
        /* Même discipline que le chemin « alerte » deux lignes plus bas : un
           plan PARTIEL (deux niveaux sur trois) est ensuite dessiné comme un
           plan complet par la barre stop/entrée/objectif du Portefeuille, le
           niveau manquant se lisant 0,00. Soit les trois, soit aucun. */
        const niv = [n('f-entry'), n('f-stop'), n('f-tgt')];
        const saisis = niv.filter((x) => x !== null).length;
        if (saisis && saisis < 3) { VX.toast('Plan incomplet : entrée, stop ET objectif — ou aucun des trois', 'error'); return; }
        E.followStock(sym, { entry_spot: niv[0], stop: niv[1], tgt: niv[2] });
      }
      else if (dest === 'alert') {
        if (n('f-level') === null) { VX.toast('Niveau requis', 'error'); return; }
        E.addAlert(sym, v('f-cond'), n('f-level'), v('f-note'));
      } else if (dest === 'position') {
        const qty = n('f-qty') || 1, unit = n('f-cost') || 0, typ = v('f-type');
        /* schéma desk historique : cost = TOTAL investi (option = prime×100×qté) */
        const total = typ === 'STK' ? qty * unit : qty * unit * 100;
        /* Parité avec le schéma historique du desk (lot 3) : sans ces champs,
           une position déclarée ICI n'avait jamais d'objectif (tp1=None dans
           tout le pipeline), pas de devise, pas de stratégie — alors que la
           même déclaration depuis le legacy les porte. models.py lit
           snap.stop/snap.tgt d'abord, puis myStop/myTgt : on écrit les DEUX,
           comme le legacy. */
        E.addPosition({ type: typ, sym, qty, cost: Math.round(total * 100) / 100,
          entryPrice: unit,
          strike: n('f-strike'), exp: v('f-exp') || null,
          right: typ === 'CALL' ? 'C' : (typ === 'PUT' ? 'P' : null),
          myStop: n('f-stop'), myTgt: n('f-tgt'), target1: n('f-tgt'),
          fees: n('f-fees'), currency: v('f-ccy') || 'USD',
          strategy: v('f-strategy') || null,
          entrySnap: { stop: n('f-stop'), tgt: n('f-tgt'),
                       date: new Date().toISOString().slice(0, 10) } });
      } else if (dest === 'note') E.setNote(sym, v('f-text'));
      VX.shell.closeModal();
    }
    function wire() {
      document.getElementById('vx-add-next')?.addEventListener('click', () => {
        const val = document.getElementById('vx-add-sym')?.value?.trim().toUpperCase();
        if (!/^[A-Z.\-]{1,7}$/.test(val || '')) { VX.toast('Ticker invalide', 'error'); return; }
        sym = val; step = dest ? 3 : 2; render();
      });
      document.getElementById('vx-add-sym')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') document.getElementById('vx-add-next')?.click();
      });
      document.querySelectorAll('#vx-modal [data-dest]').forEach(b =>
        b.addEventListener('click', () => { dest = b.dataset.dest; step = 3; render(); }));
      document.getElementById('vx-add-confirm')?.addEventListener('click', confirmAdd);
      document.getElementById('vx-add-sym')?.focus();
    }
    render();
  };

  /* ── Gestion d'une POSITION précise (par id) : modifier / clôturer / supprimer ──
     Registre déclaratif : toutes ces actions restent LOCALES, Vertex n'envoie
     JAMAIS d'ordre. « Clôturer » journalise une sortie réelle (P&L) ; « Supprimer »
     retire une saisie erronée sans rien journaliser. ── */
  E.openEditPosition = function (id) {
    const t = E.positions().find(x => String(x.id) === String(id));
    if (!t) { VX.toast('Position introuvable', 'error'); return; }
    const isOpt = t.type !== 'STK';
    const per = t.qty ? (isOpt ? t.cost / (t.qty * 100) : t.cost / t.qty) : 0;   // prix unitaire reconstruit
    const stop0 = (t.entrySnap && t.entrySnap.stop != null) ? t.entrySnap.stop : '';
    const body = `
      <div class="vx-flex vx-mb3"><span class="vx-ticker" style="font-size:18px">${t.sym}</span>
        <span class="vx-badge">${t.type}${t.strike ? ' ' + t.strike : ''}${t.exp ? ' ' + t.exp : ''}</span></div>
      <div class="vx-form-row">
        <div class="vx-field"><label>Quantité</label><input class="vx-input" id="fe-qty" type="number" min="1" value="${t.qty}" /></div>
        <div class="vx-field"><label>Prix unitaire${isOpt ? ' (prime par action)' : ''}</label>
          <input class="vx-input" id="fe-cost" type="number" step="any" value="${per || ''}" /></div>
      </div>
      <div class="vx-field"><label>Stop / invalidation</label>
        <input class="vx-input" id="fe-stop" type="number" step="any" value="${stop0}" /></div>
      <div class="vx-help">Modification LOCALE du registre — aucun ordre envoyé.</div>`;
    VX.shell.openModal('Modifier la position — ' + t.sym, body,
      '<button class="vx-btn" id="fe-cancel">Annuler</button><button class="vx-btn vx-btn-primary" id="fe-ok">Enregistrer</button>');
    document.getElementById('fe-cancel')?.addEventListener('click', () => VX.shell.closeModal());
    document.getElementById('fe-ok')?.addEventListener('click', () => {
      const qty = Number(document.getElementById('fe-qty').value) || 0;
      const unit = Number(document.getElementById('fe-cost').value) || 0;
      if (!(qty > 0)) { VX.toast('Quantité invalide', 'error'); return; }
      const total = isOpt ? qty * unit * 100 : qty * unit;   // schéma desk : cost = TOTAL investi
      const snap = Object.assign({}, t.entrySnap || {});
      const sv = document.getElementById('fe-stop').value;
      snap.stop = sv === '' ? null : Number(sv);
      E.updatePosition(id, { qty, cost: Math.round(total * 100) / 100, entryPrice: unit, entrySnap: snap });
      VX.shell.closeModal();
    });
  };
  E.openClosePosition = function (id) {
    const t = E.positions().find(x => String(x.id) === String(id));
    if (!t) { VX.toast('Position introuvable', 'error'); return; }
    const invested = (VX.fmt && VX.fmt.price) ? VX.fmt.price(t.cost) : t.cost;
    const body = `
      <div class="vx-flex vx-mb3"><span class="vx-ticker" style="font-size:18px">${t.sym}</span>
        <span class="vx-badge">${t.type}${t.strike ? ' ' + t.strike : ''}</span>
        <span class="vx-meta">investi ${invested}</span></div>
      <div class="vx-field"><label>Montant TOTAL récupéré à la sortie</label>
        <input class="vx-input" id="fc-exit" type="number" step="any" placeholder="valeur de sortie totale" /></div>
      <div class="vx-field"><label>Note (optionnel)</label>
        <input class="vx-input" id="fc-note" placeholder="raison de la sortie" /></div>
      <div class="vx-help">Clôture DÉCLARATIVE : la position passe au journal (P&amp;L calculé). Aucun ordre n'est envoyé.</div>`;
    VX.shell.openModal('Clôturer la position — ' + t.sym, body,
      '<button class="vx-btn" id="fc-cancel">Annuler</button><button class="vx-btn vx-btn-primary" id="fc-ok">Clôturer</button>');
    document.getElementById('fc-cancel')?.addEventListener('click', () => VX.shell.closeModal());
    document.getElementById('fc-ok')?.addEventListener('click', () => {
      const exit = document.getElementById('fc-exit').value;
      if (exit === '' || isNaN(Number(exit))) { VX.toast('Montant de sortie requis', 'error'); return; }
      E.recordExit(id, Number(exit), document.getElementById('fc-note').value);
      VX.shell.closeModal();
    });
  };
  E.confirmDeletePosition = function (id) {
    const t = E.positions().find(x => String(x.id) === String(id));
    if (!t) { VX.toast('Position introuvable', 'error'); return; }
    const desc = `${t.type}${t.strike ? ' ' + t.strike : ''}${t.exp ? ' ' + t.exp : ''}, qté ${t.qty}`;
    VX.shell.openModal('Supprimer la position — ' + t.sym,
      `<p>Retirer <b>${t.sym}</b> (${desc}) du registre ?</p>
       <div class="vx-help">Suppression d'une saisie — <b>sans</b> passage au journal. Pour journaliser une sortie réelle, utilise « Clôturer ».</div>`,
      '<button class="vx-btn" id="fd-cancel">Annuler</button><button class="vx-btn vx-btn-danger" id="fd-ok">Supprimer</button>');
    document.getElementById('fd-cancel')?.addEventListener('click', () => VX.shell.closeModal());
    document.getElementById('fd-ok')?.addEventListener('click', () => { E.deletePosition(id); VX.shell.closeModal(); });
  };
  /* Menu d'actions d'une POSITION précise (id) — surface modifier/clôturer/supprimer,
     puis les actions utiles du titre. Ouvert par [data-position-menu="<id>"]. */
  E.openPositionMenu = function (id, anchorEl) {
    const t = E.positions().find(x => String(x.id) === String(id));
    if (!t) { VX.toast('Position introuvable', 'error'); return; }
    E._renderMenu([
      { label: 'Modifier la position', run: () => E.openEditPosition(id) },
      { label: 'Clôturer la position (→ journal)', run: () => E.openClosePosition(id) },
      { label: 'Supprimer la position', run: () => E.confirmDeletePosition(id) },
      { sep: true },
      { label: 'Ouvrir l’analyse', run: () => VX.openAnalysis(t.sym) },
      { label: 'Ajouter une note / thèse', run: () => E.openAddModal(t.sym, 'note') },
      { label: 'Ouvrir le journal', run: () => { VX.context.save(); location.href = '/journal?view=journal&sym=' + t.sym; } },
      { label: 'Copier le ticker', run: () => { navigator.clipboard?.writeText(t.sym); VX.toast(t.sym + ' copié'); } },
    ], anchorEl);
  };
})();
