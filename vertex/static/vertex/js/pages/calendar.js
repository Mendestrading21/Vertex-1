/* Vertex 2.0 — Calendrier.
 *
 * Consomme `GET /cal-feed`, l'unique source d'événements agrégés du produit,
 * et n'en dérive aucune donnée nouvelle.
 *
 * UNE HONNÊTETÉ EXPLICITE
 *   `/cal-feed` ne porte pas de champ `ts`. Trois pages du produit écrivent
 *   `cal.ts || Date.now()` : elles affichent donc l'heure du NAVIGATEUR comme
 *   fraîcheur de la donnée — une fraîcheur toujours verte, et fausse. Ce
 *   fichier ne reproduit pas ce raccourci. Il affiche `updated` quand il
 *   existe, et déclare l'horodatage absent sinon.
 */
(function () {
  'use strict';

  var ABSENT = '—';
  var etatFiltres = { horizon: 7, cat: '', mesPositions: false };
  var dernierLot = null;

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function etat(titre, cause, kind) {
    return '<div class="vx2-state" data-kind="' + esc(kind || 'empty') + '" role="status">'
      + '<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
      + '<p class="vx2-state-title">' + esc(titre) + '</p>'
      + '<p class="vx2-state-cause">' + esc(cause) + '</p></div>';
  }

  function badge(state, texte, titre) {
    return '<span class="vx2-badge" data-state="' + esc(state) + '"'
      + (titre ? ' title="' + esc(titre) + '"' : '') + '>' + esc(texte) + '</span>';
  }

  /* Niveau de confirmation d'une date : dérivé de ce que le serveur a dit
   * (`confirmation`, `demo`, `approx`). Sans information, on l'écrit
   * (« n/d ») au lieu d'affirmer « Confirmé ». */
  function badgeConfirmation(e, court) {
    if (e.demo) return badge('stale', court ? 'Démo' : 'Synthétique (démo)', e.confirmation || '');
    if (e.approx) return badge('stale', court ? 'Approx.' : 'Approximative', e.confirmation || '');
    var c = String(e.confirmation || '');
    if (!c) return badge('stale', court ? 'Confirmation n/d' : 'Confirmation inconnue');
    if (/^confirm/i.test(c)) return badge('live', court ? 'Confirmée' : 'Confirmée par l’émetteur', c);
    return badge('stale', court ? 'Non confirmée' : 'Non confirmée par l’émetteur', c);
  }

  function positionsDetenues() {
    try {
      if (window.VXEntities && typeof window.VXEntities.positions === 'function') {
        return window.VXEntities.positions().map(function (p) {
          return String(p.sym || '').toUpperCase();
        }).filter(Boolean);
      }
    } catch (e) { /* le centre d'entités peut ne pas être prêt : liste vide. */ }
    return [];
  }

  /* Normalisation en un modèle d'affichage UNIQUE. Aucun champ n'est inventé :
   * ce qui n'est pas fourni reste absent. */
  function normaliser(cal, mesPositions) {
    var out = [];
    (cal.macro || []).forEach(function (m) {
      out.push({
        when: m.date, dte: m.dte, cat: 'macro',
        kind: m.kind || 'Économie',
        titre: m.label || ABSENT,
        note: m.note || '',
        approx: !!m.approx,
        importance: m.importance || '',
        source: m.source || '',
        confirmation: m.confirmation || '',
        demo: !!m.demo,
        sym: null, expose: false
      });
    });
    (cal.items || []).forEach(function (it) {
      var sym = String(it.sym || '').toUpperCase();
      out.push({
        when: it.date, dte: it.dte, cat: 'earnings', kind: 'Résultats',
        titre: sym + ' — publication des résultats',
        note: '', approx: !!it.approx,
        importance: '',
        /* Source et niveau de confirmation SERVIS par /cal-feed ; rien n'est
         * affirmé ici (« Confirmé » n'est jamais décidé par l'écran). */
        source: it.source || (cal.source ? String(cal.source) : ''),
        confirmation: it.confirmation || '',
        demo: !!(it.demo || cal.demo),
        sym: sym,
        verdict: it.verdict || null,
        grade: it.grade || null,
        expose: mesPositions.indexOf(sym) !== -1
      });
    });
    return out.filter(function (e) { return e.when; })
      .sort(function (a, b) { return String(a.when).localeCompare(String(b.when)); });
  }

  function filtrer(items) {
    return items.filter(function (e) {
      if (etatFiltres.cat && e.cat !== etatFiltres.cat) return false;
      if (etatFiltres.mesPositions && !e.expose) return false;
      if (typeof e.dte === 'number' && e.dte > etatFiltres.horizon) return false;
      return true;
    });
  }

  /* Le vocabulaire des verdicts appartient au MOTEUR, pas à cette page.
     La coque l'injecte déjà dans `window.__VXVOCAB` depuis
     `vertex.engines.recommendation.vocab_js()`. Le recopier ici en ferait une
     seconde vérité, libre de dériver le jour où un verdict est renommé — et
     Vertex n'a qu'une source par vérité. Sans vocabulaire disponible, le
     verdict brut est affiché tel quel : jamais traduit à l'aveugle. */
  function libelleVerdict(v) {
    if (!v) return null;
    try {
      var voc = window.__VXVOCAB;
      if (typeof voc === 'string') voc = JSON.parse(voc);
      var e = voc && (voc[v] || voc[String(v).toUpperCase()]);
      if (e && e.label) return e.label;
    } catch (e) { /* vocabulaire absent : on rend le verdict brut */ }
    return String(v);
  }

  function ligneEvenement(e) {
    var metas = [];
    metas.push(e.kind);
    if (e.approx) metas.push('date approximative');
    if (e.confirmation) metas.push(e.confirmation);
    if (e.importance) metas.push('importance ' + e.importance);
    if (e.verdict) metas.push('verdict du moteur : ' + libelleVerdict(e.verdict));
    if (e.note) metas.push(e.note);
    return '<li class="vx-cal-ev" data-expose="' + (e.expose ? '1' : '0') + '">'
      + badgeConfirmation(e, true)
      + '<span class="vx-cal-ev-corps">'
      + '<span class="vx-cal-ev-titre">' + esc(e.titre) + '</span>'
      + '<span class="vx-cal-ev-meta">' + esc(metas.join(' · ')) + '</span>'
      + '</span>'
      + (e.expose ? badge('stale', 'Position exposée') : '')
      + '</li>';
  }

  function grouperParJour(items) {
    var jours = [];
    var index = {};
    items.forEach(function (e) {
      if (!index[e.when]) { index[e.when] = { when: e.when, dte: e.dte, events: [] }; jours.push(index[e.when]); }
      index[e.when].events.push(e);
    });
    return jours;
  }

  function rendreTimeline(items) {
    var hote = $('#vx-cal-timeline');
    if (!hote) return;
    if (!items.length) {
      hote.innerHTML = etat('Aucun événement dans cet horizon',
        'Les sources répondent, mais aucun événement ne tombe dans la période et '
        + 'les filtres retenus. Élargis l’horizon pour voir plus loin.', 'empty');
      return;
    }
    hote.innerHTML = '<div>' + grouperParJour(items).map(function (j) {
      var dte = typeof j.dte === 'number'
        ? (j.dte === 0 ? "aujourd'hui" : (j.dte > 0 ? 'dans ' + j.dte + ' j' : 'il y a ' + Math.abs(j.dte) + ' j'))
        : ABSENT;
      return '<section class="vx-cal-jour">'
        + '<div class="vx-cal-jour-tete">'
        + '<span class="vx-cal-jour-date">' + esc(j.when) + '</span>'
        + '<span class="vx-cal-jour-dte">' + esc(dte) + '</span></div>'
        + '<ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px">'
        + j.events.map(ligneEvenement).join('') + '</ul></section>';
    }).join('') + '</div>';
  }

  function rendrePositions(items) {
    var hote = $('#vx-cal-positions');
    if (!hote) return;
    var exposes = items.filter(function (e) { return e.expose; });
    if (!positionsDetenues().length) {
      hote.innerHTML = etat('Aucune position déclarée',
        'Vertex ne connaît aucune position à croiser avec le calendrier. '
        + 'Déclare des positions dans le Portefeuille pour voir ce qui les touche.', 'empty');
      return;
    }
    if (!exposes.length) {
      hote.innerHTML = etat('Aucun événement sur tes positions',
        'Aucun événement de cet horizon ne concerne un titre que tu détiens. '
        + 'Ce n’est pas une absence de données : le calendrier a répondu.', 'empty');
      return;
    }
    hote.innerHTML = '<ul style="list-style:none;margin:0;padding:0;display:flex;'
      + 'flex-direction:column;gap:8px">'
      + exposes.map(function (e) {
        return '<li class="vx-cal-ev" data-expose="1">'
          + '<span class="vx-cal-ev-corps">'
          + '<span class="vx-cal-ev-titre">' + esc(e.sym || e.titre) + '</span>'
          + '<span class="vx-cal-ev-meta">' + esc(e.when)
          + (typeof e.dte === 'number' ? ' · dans ' + e.dte + ' j' : '') + '</span></span>'
          + '<a class="vx2-btn vx2-btn--ghost" href="/analysis/' + encodeURIComponent(e.sym || '')
          + '" style="margin-left:auto">Ouvrir le dossier</a></li>';
      }).join('') + '</ul>';
  }

  /* Table équivalente — la chronologie est la visualisation principale de cette
   * page ; elle doit avoir sa lecture tabulaire. */
  function rendreTable(items) {
    var hote = $('#vx-cal-table');
    if (!hote) return;
    if (!items.length) { hote.innerHTML = ''; return; }
    var rows = items.map(function (e) {
      return '<tr><td class="vx2-sticky-col vx2-num">' + esc(e.when) + '</td>'
        + '<td class="vx2-num">' + (typeof e.dte === 'number' ? esc(e.dte) : ABSENT) + '</td>'
        + '<td>' + esc(e.kind) + '</td>'
        + '<td>' + esc(e.titre) + '</td>'
        + '<td>' + (e.sym ? '<a href="/analysis/' + encodeURIComponent(e.sym) + '">'
          + esc(e.sym) + '</a>' : '<span class="vx2-absent">' + ABSENT + '</span>') + '</td>'
        + '<td>' + badgeConfirmation(e, false) + '</td>'
        + '<td>' + (e.source ? esc(e.source) : '<span class="vx2-absent">' + ABSENT + '</span>') + '</td>'
        + '</tr>';
    }).join('');
    hote.innerHTML = '<div class="vx2-surface">'
      + '<div class="vx2-card-head"><div><h2 class="vx2-card-title">Agenda</h2>'
      + '<p class="vx2-card-question">La même chronologie, en tableau filtrable.</p></div></div>'
      + '<div class="vx2-table-wrap" tabindex="0" role="region" aria-label="Agenda des événements">'
      + '<table class="vx2-table"><thead><tr>'
      + '<th class="vx2-sticky-col vx2-num" scope="col">Date</th>'
      + '<th class="vx2-num" scope="col">Échéance <span class="vx2-th-unit">(j)</span></th>'
      + '<th scope="col">Type</th><th scope="col">Événement</th>'
      + '<th scope="col">Instrument</th><th scope="col">Date</th>'
      + '<th scope="col">Source</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div></div>';
  }

  function rendreFraicheur(cal) {
    var hote = $('#vx-cal-fraicheur');
    if (!hote) return;
    // Lot 46 : le flux porte désormais `ts` (époque serveur) — un âge VIVANT
    // remplace le libellé figé ; sans ts on garde `updated`, sans rien on le dit.
    if (cal && cal.ts && window.VX && VX.updateIndicator) {
      hote.innerHTML = VX.updateIndicator(cal.ts, 'lot construit à ' + (cal.updated || '—'), 'delayed');
    } else if (cal && cal.updated) {
      hote.innerHTML = badge('delayed', 'Lot construit à ' + cal.updated);
    } else {
      hote.innerHTML = badge('missing', 'Horodatage indisponible');
    }
  }

  function rendreCouverture(cal) {
    var hote = $('#vx-cal-couverture');
    if (!hote) return;
    var c = cal && cal.macro_couverture;
    if (!c) { hote.innerHTML = ''; return; }
    if (c.fomc_horizon_depasse) {
      hote.innerHTML = '<div class="vx2-banner" data-kind="caution" role="status"><span>'
        + '<b>Calendrier officiel épuisé — </b>'
        + 'les dates de politique monétaire ne sont publiées que jusqu’au '
        + esc(c.fomc_publie_jusqu_a || ABSENT) + '. Au-delà ('
        + esc(c.fomc_jours_non_couverts == null ? ABSENT : c.fomc_jours_non_couverts)
        + ' jours demandés), Vertex n’affiche que des dates de règle, marquées '
        + '« approximative ». Aucune date n’est supposée.</span></div>';
    } else {
      hote.innerHTML = '<div class="vx2-banner" role="status"><span>'
        + 'Calendrier officiel publié jusqu’au <b>'
        + esc(c.fomc_publie_jusqu_a || ABSENT) + '</b>. '
        + 'Les dates d’emploi et d’inflation suivent une règle de publication et '
        + 'sont marquées « approximative ».</span></div>';
    }
  }

  function rendreCompte(total, affiches) {
    var hote = $('#vx-cal-compte');
    if (!hote) return;
    hote.innerHTML = '<span class="vx2-stamp"><b>' + affiches + '</b> sur ' + total
      + ' événement' + (total > 1 ? 's' : '') + '</span>';
  }

  function rafraichir() {
    if (!dernierLot) return;
    var mes = positionsDetenues();
    var tous = normaliser(dernierLot, mes);
    var vus = filtrer(tous);
    rendreCompte(tous.length, vus.length);
    rendreTimeline(vus);
    rendrePositions(vus);
    rendreTable(vus);
  }

  async function charger() {
    try {
      var cal;
      if (window.VX && typeof window.VX.fetch === 'function') {
        cal = await window.VX.fetch('/cal-feed', { ttl: 300000 });
      } else {
        var r = await fetch('/cal-feed', { credentials: 'same-origin' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        cal = await r.json();
      }
      dernierLot = cal || {};
      rendreFraicheur(dernierLot);
      rendreCouverture(dernierLot);
      rafraichir();
    } catch (e) {
      var hote = $('#vx-cal-timeline');
      if (hote) {
        hote.innerHTML = etat('Calendrier indisponible',
          'La source d’événements n’a pas répondu : '
          + (e && e.message ? e.message : 'erreur réseau')
          + '. Aucun événement n’est affiché — l’absence de réponse n’est pas '
          + 'une absence d’événements.', 'error');
      }
      var f = $('#vx-cal-fraicheur');
      if (f) f.innerHTML = badge('error', 'Source injoignable');
      var p = $('#vx-cal-positions');
      if (p) p.innerHTML = '';
      var c = $('#vx-cal-couverture');
      if (c) c.innerHTML = '';
    }
  }

  function groupePresse(sel, onPick) {
    $$(sel).forEach(function (btn) {
      btn.addEventListener('click', function () {
        $$(sel).forEach(function (b) {
          b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
        });
        onPick(btn);
        rafraichir();
      });
    });
  }


  /* ── SOUS-VUE OPTIONS ─────────────────────────────────────────────────
     Le contrat range « Options » parmi les vues du calendrier. Vertex ne
     produit AUCUN agregat d'expirations de marche et ne detecte aucune date
     d'OPEX — c'est ecrit dans la fiche de couverture, et ca le reste.

     Mais une chose EXISTE et etait datee nulle part : les echeances des
     contrats que l'utilisateur a lui-meme declares. Elles sont reelles,
     datees, et n'exigent aucun moteur. La vue les montre, et dit
     explicitement ce qu'elle ne montre pas. */
  function estOption(t) {
    return t && (t.type === 'CALL' || t.type === 'PUT' || t.right === 'C' || t.right === 'P');
  }
  function rendreEcheances() {
    var hote = document.getElementById('vx-cal-timeline');
    if (!hote) return;
    var E = window.VXEntities;
    var opts = ((E && E.positions && E.positions()) || []).filter(estOption)
      .filter(function (t) { return t.exp; })
      .sort(function (a, b) { return String(a.exp).localeCompare(String(b.exp)); });
    if (!opts.length) {
      hote.innerHTML = '<div class="vx2-state" data-kind="empty" role="status">'
        + '<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
        + '<p class="vx2-state-title">Aucune échéance d’option déclarée</p>'
        + '<p class="vx2-state-cause">Cette vue date les contrats que <b>vous</b> avez '
        + 'déclarés. Vertex ne connaît aucun calendrier d’expirations de marché '
        + 'et ne détecte aucune date d’OPEX.</p>'
        + '<div class="vx2-state-actions">'
        + '<a class="vx2-btn" href="/portfolio?view=options">Ouvrir mes options</a></div></div>';
      return;
    }
    var auj = new Date(); auj.setHours(0, 0, 0, 0);
    var jours = {};
    opts.forEach(function (t) {
      (jours[t.exp] = jours[t.exp] || []).push(t);
    });
    var html = Object.keys(jours).sort().map(function (d) {
      var dte = Math.round((new Date(d) - auj) / 86400000);
      var ton = dte < 0 ? 'stale' : dte <= 7 ? 'delayed' : 'missing';
      var mot = dte < 0 ? 'expirée' : dte === 0 ? 'aujourd’hui'
        : ('dans ' + dte + ' jour' + (dte > 1 ? 's' : ''));
      return '<div class="vx-cal-jour"><div class="vx-cal-jour-tete">'
        + '<span class="vx-cal-jour-date">' + esc(d) + '</span>'
        + '<span class="vx2-badge" data-state="' + ton + '">' + mot + '</span></div>'
        + jours[d].map(function (t) {
            return '<div class="vx-cal-ev" data-expose="1"><div class="vx-cal-ev-corps">'
              + '<span class="vx-cal-ev-titre">' + esc(t.sym) + ' ' + esc(t.type || '')
              + ' ' + esc(String(t.strike == null ? '' : t.strike)) + '</span>'
              + '<span class="vx-cal-ev-meta">' + esc(String(t.qty || '')) + ' contrat(s) '
              + '· position déclarée au desk</span></div></div>';
          }).join('')
        + '</div>';
    }).join('');
    hote.innerHTML = html
      + '<p class="vx2-stamp vx-mt3">Seules vos positions déclarées sont datées ici. '
      + 'Aucun calendrier d’expirations de marché, aucune date d’OPEX : '
      + 'Vertex n’en produit pas.</p>';
    var cpt = document.getElementById('vx-cal-compte');
    if (cpt) cpt.innerHTML = '<span class="vx2-badge" data-state="option">'
      + opts.length + ' contrat(s) · ' + Object.keys(jours).length + ' échéance(s)</span>';
  }

  function boot() {
    // La vue choisie fixe l'horizon de départ : « Aujourd'hui » n'affiche pas
    // trente jours, et « Mois » n'en affiche pas sept.
    var page = $('[data-cal-view]');
    var vue = page ? page.getAttribute('data-cal-view') : 'today';
    var HORIZON_PAR_VUE = { today: 0, week: 7, month: 30, agenda: 120, portfolio: 30,
                            macro: 120, options: 365 };
    /*  La vue Options ne lit pas `/cal-feed` : sa donnee est le desk local.
        Sortir tot laissait TROIS blocs en suspens — le panneau lateral en
        rectangle gris, la fraicheur sur « Chargement… » pour toujours, et un
        bandeau de couverture qui parlait d'une lecture qui n'aurait pas lieu.
        On les remplit AVEC CE QUI EST VRAI ICI plutot que de les abandonner.  */
    if (vue === 'options') {
      rendreEcheances();
      var fr = $('#vx-cal-fraicheur');
      if (fr) fr.innerHTML = '<span class="vx2-badge" data-state="missing">'
        + 'Positions déclarées — horodatage local, non fourni</span>';
      var cv = $('#vx-cal-couverture');
      if (cv) cv.innerHTML = '<div class="vx2-banner" data-kind="prudence" role="status">'
        + '<span>Cette vue ne lit pas le calendrier officiel : elle date '
        + '<b>vos contrats déclarés</b>. Aucun agrégat d’expirations de marché, '
        + 'aucune date d’OPEX — Vertex n’en produit pas.</span></div>';
      var pos = $('#vx-cal-positions');
      if (pos) pos.innerHTML = '<div class="vx2-state" data-kind="missing" role="status">'
        + '<p class="vx2-state-title">Sans objet sur cette vue</p>'
        + '<p class="vx2-state-cause">Chaque échéance listée à gauche EST une position '
        + 'déclarée : les séparer n’apporterait rien. Les événements de marché qui '
        + 'touchent le portefeuille vivent dans '
        + '<a href="/calendar?view=portfolio">Portefeuille</a>.</p></div>';
      return;
    }
    if (HORIZON_PAR_VUE[vue] != null) etatFiltres.horizon = HORIZON_PAR_VUE[vue];
    if (vue === 'macro') etatFiltres.cat = 'macro';
    if (vue === 'portfolio') etatFiltres.mesPositions = true;

    $$('[data-cal-horizon]').forEach(function (b) {
      b.setAttribute('aria-pressed',
        Number(b.getAttribute('data-cal-horizon')) === etatFiltres.horizon ? 'true' : 'false');
    });
    $$('[data-cal-cat]').forEach(function (b) {
      b.setAttribute('aria-pressed',
        b.getAttribute('data-cal-cat') === etatFiltres.cat ? 'true' : 'false');
    });
    var mine = document.querySelector('[data-cal-mine]');
    if (mine) mine.setAttribute('aria-pressed', etatFiltres.mesPositions ? 'true' : 'false');

    groupePresse('[data-cal-horizon]', function (b) {
      etatFiltres.horizon = Number(b.getAttribute('data-cal-horizon'));
    });
    groupePresse('[data-cal-cat]', function (b) {
      etatFiltres.cat = b.getAttribute('data-cal-cat');
    });
    if (mine) {
      mine.addEventListener('click', function () {
        etatFiltres.mesPositions = !etatFiltres.mesPositions;
        mine.setAttribute('aria-pressed', etatFiltres.mesPositions ? 'true' : 'false');
        rafraichir();
      });
    }
    charger();
    if (window.VX && window.VX.bus && typeof window.VX.bus.on === 'function') {
      window.VX.bus.on('vx:data-refreshed', charger);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
