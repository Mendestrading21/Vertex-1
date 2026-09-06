/* Vertex Live Updates — client SSE (§26).
   EventSource → VX.bus (vx:live:<canal>) avec : reconnexion automatique
   (Last-Event-ID géré par le navigateur), déduplication par id, repli
   polling adaptatif si SSE échoue, ralentissement onglet masqué,
   statut publié sur VX.bus ('vx:live-status'). Aucune exécution :
   les événements ne font que DÉCRIRE l'état serveur. */
(function () {
  'use strict';
  const VX = window.VX; if (!VX) return;
  let es = null, lastId = 0, failures = 0, pollTimer = null;
  let status = 'OFFLINE';

  function setStatus(s) {
    if (s === status) return;
    status = s;
    VX.bus.emit('vx:live-status', { status: s });
  }
  VX.liveStatus = () => status;

  /* ── Réaction aux événements (P1 diffusion) ──────────────────────
     Le serveur annonce QU'UNE donnée a changé (scan, board d'options,
     actualités, alertes, jobs) ; le client invalide les URL concernées de
     son cache et rejoue les tâches de la page. Regroupé (1,5 s), jamais en
     onglet masqué (rattrapé à la ré-apparition), jamais un rechargement
     complet : filtres, symbole, onglet et position restent en place. */
  const CIBLES = {
    market: null,                                       /* tout le cache */
    options: ['/api/options', '/scan', '/api/opportunities'],
    news: ['/api/news', '/news', '/api/session'],
    alerts: ['/api/alerts', '/api/command'],
    jobs: ['/api/system'],
    positions: ['/api/pos-quotes', '/api/portfolio'],
    portfolio: ['/api/portfolio', '/api/risk'],
    decisions: ['/api/decision', '/api/strategy', '/api/command'],
    connections: ['/api/live', '/api/ibkr', '/api/system'],
    system: []
  };
  /* ── CANAUX TÉLÉMÉTRIQUES : pas de rejeu complet de la page ────────────
     `jobs` annonce qu'une BOUCLE DE FOND a battu, pas qu'une donnée affichée a
     changé : sa seule cible de cache est `/api/system`. Le rejeu de TOUTES les
     tâches de la page était donc payé par toutes les pages ouvertes — Marchés,
     Portefeuille, Aujourd'hui rejouaient l'intégralité de leurs fetch pour un
     battement qui ne touche aucun de leurs chiffres. C'est l'amplification
     inter-pages du constat 23, et elle s'auto-entretient : certains de ces
     fetch font battre des jobs à leur tour.
     Le rejeu reste INSTANTANÉ là où il a un sens. Système enregistre ses tâches
     PAR VUE : `jobs` peint « Automatisations » (system_page.py:1584) et
     `alertes` peint « Tâches en échec » / « dernière erreur consignée »
     (l.1587) — et `loadAlerts` lit BIEN `/api/system/jobs` (l.1414). Le premier
     filtre ne nommait que `jobs` : mesuré, la carte Alertes gardait un cache
     invalidé mais n'était repeinte que par son intervalle de 60 s, contre
     ~1,5 s avant. Les deux labels sont donc rejoués.
     Ailleurs, rien à rejouer — le cache est invalidé et `vx:live:jobs` /
     `vx:data-refreshed` partent comme avant, donc aucun abonné n'est privé de
     l'information.
     Les autres canaux gardent le rejeu complet : ils annoncent des données
     réellement peintes (cotations, scan, actualités, alertes, décisions). */
  const REJEU_CIBLE = { jobs: ['jobs', 'alertes'] };
  const timers = {}, pending = {};
  function appliquer(channel) {
    const c = CIBLES[channel];
    if (c === null) VX.fetch.invalidate();
    else if (c && c.length) c.forEach((p) => { try { VX.fetch.invalidate(p); } catch (e) {} });
    if (VX.refresh && VX.refresh.runTasks) VX.refresh.runTasks(REJEU_CIBLE[channel]);
    /* Les pages qui écoutent `vx:data-refreshed` (Marchés, Performance,
       Calendrier, Aujourd'hui…) rejouent APRÈS l'invalidation : avant, il
       partait par événement brut, cache intact → rejeu à vide. */
    VX.bus.emit('vx:data-refreshed', { channel, live: true });
    VX.bus.emit('vx:live-applied', { channel });
  }
  function reagir(channel) {
    if (!(channel in CIBLES)) return;
    if (document.hidden) { pending[channel] = true; return; }
    clearTimeout(timers[channel]);
    timers[channel] = setTimeout(() => appliquer(channel), 1500);
  }
  function rattraper() {
    Object.keys(pending).forEach((ch) => { delete pending[ch]; reagir(ch); });
  }
  VX.liveReact = reagir;   /* exposé pour les tests d'intégration navigateur */

  function dispatch(ev) {
    if (!ev || typeof ev.id !== 'number' || ev.id <= lastId) return; /* dédup */
    lastId = ev.id;
    VX.bus.emit('vx:live:' + ev.channel, ev.data);
    reagir(ev.channel);
  }

  function connect() {
    if (es || document.hidden) return;
    try {
      es = new EventSource('/api/live/events' + (lastId ? '?lastEventId=' + lastId : ''));
    } catch (e) { fallbackPolling(); return; }
    es.onopen = () => { failures = 0; setStatus('LIVE'); stopPolling(); };
    es.onerror = () => {
      es && es.close(); es = null;
      failures += 1;
      setStatus(failures > 3 ? 'FALLBACK' : 'DELAYED');
      if (failures > 3) fallbackPolling();
      else setTimeout(connect, Math.min(30000, 2000 * failures));
    };
    ['market', 'positions', 'options', 'portfolio', 'decisions',
     'alerts', 'connections', 'jobs', 'system', 'news'].forEach(ch => {
      es.addEventListener(ch, (m) => {
        try { dispatch(JSON.parse(m.data)); } catch (e) {}
      });
    });
  }

  /* Repli : polling adaptatif du statut live (le refresh manager par page
     continue de rafraîchir les données elles-mêmes). */
  function fallbackPolling() {
    if (pollTimer) return;
    const tick = async () => {
      try {
        await VX.fetch('/api/live/status', { ttl: 0 });
        setStatus('FALLBACK');
      } catch (e) { setStatus('OFFLINE'); }
    };
    tick();
    pollTimer = setInterval(() => { if (!document.hidden) tick(); }, 60000);
  }
  function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { es && es.close(); es = null; setStatus('DELAYED'); }
    else { connect(); rattraper(); }
  });
  window.addEventListener('pagehide', () => { es && es.close(); es = null; });

  connect();
})();
