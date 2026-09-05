/* Vertex 2.0 — Simulateur.
 *
 * CE FICHIER NE CALCULE AUCUNE VALEUR FINANCIÈRE.
 * Il lit les champs saisis, appelle les endpoints EXISTANTS et affiche les
 * valeurs telles qu'elles reviennent. Aucun prix, aucune prime, aucun P&L,
 * aucun point mort, aucune probabilité n'est dérivé ici : tout vient du moteur.
 * Une valeur absente reste absente — jamais complétée, jamais mise à zéro.
 *
 * Endpoints consommés (tous préexistants) :
 *   GET  /api/options/simulate   → vertex.options.scenario_pricer
 *   POST /api/options/analyze    → vertex.engines.multileg_lab
 *   POST /api/pretrade/check     → vertex.engines.pretrade
 */
(function () {
  'use strict';

  var ABSENT = '—';
  var MAX_COMPARAISONS = 3;
  var comparaisons = [];

  /* Retour visible apres un clic. Le code appelait un helper global qui
     n'existe NULLE PART dans le produit ; celui qui est servi s'appelle
     `VX.toast`. Les trois appels etaient gardes par un `if` sur ce mauvais
     nom, donc silencieux — le bouton « Ajouter a la comparaison » ne disait
     rien, ni en cas de succes, ni quand il n'y avait pas encore de simulation
     a ajouter.
     Releve en CLIQUANT le bouton (tools/audit/boutons_morts.py) : aucun
     effet mesurable. Une garde sur un mauvais nom ne leve pas d'erreur ; elle
     rend la panne invisible. */
  function dire(message, ton) {
    if (window.VX && typeof VX.toast === 'function') {
      VX.toast(message, ton || 'info');
      return true;
    }
    return false;
  }
  var classeActive = 'option';

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* Mise en forme SEULEMENT. Aucune règle métier : le ton vient du signe de la
   * valeur déjà calculée par le moteur, pas d'un seuil décidé ici. */
  function num(v, opts) {
    opts = opts || {};
    if (v === null || v === undefined || v === '' || (typeof v === 'number' && !isFinite(v))) {
      return '<span class="vx2-mono vx2-absent" title="Donnée indisponible">' + ABSENT + '</span>';
    }
    var n = Number(v);
    var txt = isNaN(n) ? String(v) : n.toLocaleString('fr-FR', {
      minimumFractionDigits: opts.dec == null ? 2 : opts.dec,
      maximumFractionDigits: opts.dec == null ? 2 : opts.dec
    });
    if (opts.signe && !isNaN(n) && n > 0) txt = '+' + txt;
    var cls = '';
    if (opts.directionnel && !isNaN(n)) cls = n > 0 ? ' vx2-pos' : (n < 0 ? ' vx2-neg' : '');
    var unite = opts.unite ? '<span class="vx2-unit"> ' + esc(opts.unite) + '</span>' : '';
    return '<span class="vx2-mono' + cls + '">' + esc(txt) + unite + '</span>';
  }

  function etat(titre, cause, kind) {
    return '<div class="vx2-state" data-kind="' + esc(kind || 'empty') + '" role="status">'
      + '<span class="vx2-state-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
      + '<p class="vx2-state-title">' + esc(titre) + '</p>'
      + '<p class="vx2-state-cause">' + esc(cause) + '</p></div>';
  }

  function metric(label, valeurHtml, meta) {
    return '<div class="vx2-metric"><span class="vx2-metric-label">' + esc(label) + '</span>'
      + '<span class="vx2-metric-value">' + valeurHtml + '</span>'
      + (meta ? '<span class="vx2-metric-meta">' + esc(meta) + '</span>' : '') + '</div>';
  }

  /* Les limitations du moteur ne sont PAS une note de bas de page : elles disent
   * ce que le chiffre affiché ne couvre pas. Elles sont rendues avec lui. */
  function limitations(liste) {
    if (!liste || !liste.length) return '';
    return '<div class="vx2-banner" data-kind="caution" role="status"><span><b>Limites du modèle — </b>'
      + liste.map(esc).join(' · ') + '</span></div>';
  }

  function lireParams() {
    var f = $('#vx-sim-form');
    if (!f) return {};
    var get = function (id) { var el = $('#' + id); return el ? String(el.value || '').trim() : ''; };
    return {
      sym: get('sim-sym').toUpperCase(),
      montant: get('sim-montant'),
      quantite: get('sim-quantite'),
      right: get('sim-right') || 'C',
      strike: get('sim-strike'),
      dte: get('sim-dte'),
      mid: get('sim-mid')
    };
  }

  // ── Rendu : simulation d'OPTION ────────────────────────────────────────
  function rendreOption(data) {
    var sim = (data && data.sim) || {};
    var cf = (data && data.capital_free) || {};
    var c = (data && data.contract) || {};

    var bande = '<div class="vx2-strip">'
      + metric('Gain attendu', num(sim.base_expected_gain_pct, { unite: '%', signe: true, dec: 1, directionnel: true }), 'scénario BASE')
      + metric('Perte planifiée', num(sim.worst_planned_loss_pct, { unite: '%', signe: true, dec: 1, directionnel: true }), 'au niveau d’invalidation')
      + metric('Gain / risque', num(sim.reward_risk, { dec: 2 }), 'rapport')
      + metric('Coût par contrat', num(cf.cost_per_contract, { unite: 'USD' }), 'prime × multiplicateur')
      + '</div>';

    var scen = sim.scenarios || {};
    var ordre = ['STOP', 'BEAR', 'FLAT', 'BASE', 'TP1', 'TP2', 'TP3'];
    var libelle = {
      STOP: 'Invalidation', BEAR: 'Adverse', FLAT: 'Inchangé', BASE: 'Central',
      TP1: 'Objectif 1', TP2: 'Objectif 2', TP3: 'Objectif 3'
    };
    // Colonnes de temps : celles que le moteur a RÉELLEMENT renvoyées.
    var jours = [];
    ordre.forEach(function (k) {
      var n = scen[k];
      if (n && n.by_time_days) {
        Object.keys(n.by_time_days).forEach(function (d) {
          if (jours.indexOf(d) === -1) jours.push(d);
        });
      }
    });
    jours.sort(function (a, b) { return Number(a) - Number(b); });

    var matrice;
    if (!jours.length) {
      matrice = etat('Matrice cours × temps indisponible',
        'Le moteur n’a renvoyé aucun horizon : l’échéance est trop courte ou les données du contrat sont insuffisantes.',
        'missing');
    } else {
      var th = '<th scope="col" class="vx2-sticky-col">Scénario</th>'
        + '<th scope="col" class="vx2-num">Cours</th>'
        + jours.map(function (d) { return '<th scope="col" class="vx2-num">J+' + esc(d) + '</th>'; }).join('');
      var trs = ordre.map(function (k) {
        var n = scen[k];
        if (!n) {
          // Un objectif absent du plan reste ABSENT — pas une case à zéro.
          return '<tr><td class="vx2-sticky-col">' + esc(libelle[k]) + '</td>'
            + '<td class="vx2-num">' + num(null) + '</td>'
            + jours.map(function () { return '<td class="vx2-num">' + num(null) + '</td>'; }).join('')
            + '</tr>';
        }
        return '<tr><td class="vx2-sticky-col">' + esc(libelle[k]) + '</td>'
          + '<td class="vx2-num">' + num(n.spot) + '</td>'
          + jours.map(function (d) {
            var cell = n.by_time_days && n.by_time_days[d];
            return '<td class="vx2-num">'
              + (cell ? num(cell.pnl_pct, { unite: '%', signe: true, dec: 1, directionnel: true }) : num(null))
              + '</td>';
          }).join('') + '</tr>';
      }).join('');
      matrice = '<div class="vx2-table-wrap" tabindex="0" role="region" '
        + 'aria-label="Résultat théorique par scénario de cours et horizon">'
        + '<table class="vx2-table"><caption class="vx2-sr-only">'
        + 'Résultat théorique en pourcentage de la prime, par scénario de cours et horizon en jours'
        + '</caption><thead><tr>' + th + '</tr></thead><tbody>' + trs + '</tbody></table></div>';
    }

    var decay = (sim.time_decay || []).map(function (r) {
      return '<tr><td class="vx2-num">J+' + esc(r.days) + '</td>'
        + '<td class="vx2-num">' + num(r.value, { dec: 3 }) + '</td>'
        + '<td class="vx2-num">' + num(r.pnl_pct, { unite: '%', signe: true, dec: 1, directionnel: true }) + '</td></tr>';
    }).join('');
    var iv = (sim.iv_sensitivity || []).map(function (r) {
      return '<tr><td class="vx2-num">' + num(r.iv_shift_pct, { unite: '%', signe: true, dec: 0 }) + '</td>'
        + '<td class="vx2-num">' + num(r.value, { dec: 3 }) + '</td>'
        + '<td class="vx2-num">' + num(r.pnl_pct, { unite: '%', signe: true, dec: 1, directionnel: true }) + '</td></tr>';
    }).join('');

    var avance = '';
    if (decay || iv) {
      avance = '<div class="vx2-grid">'
        + '<div class="vx2-col-6"><div class="vx2-surface">'
        + '<div class="vx2-card-head"><div><h3 class="vx2-card-title">Décroissance temporelle</h3>'
        + '<p class="vx2-card-question">Que coûte l’attente, à cours inchangé ?</p></div></div>'
        + (decay ? '<div class="vx2-table-wrap" tabindex="0"><table class="vx2-table"><thead><tr>'
          + '<th class="vx2-num">Horizon</th><th class="vx2-num">Valeur</th>'
          + '<th class="vx2-num">Résultat (%)</th></tr></thead><tbody>' + decay + '</tbody></table></div>'
          : etat('Aucune décroissance renvoyée', 'Le moteur n’a pas fourni cette décomposition pour ce contrat.', 'missing'))
        + '</div></div>'
        + '<div class="vx2-col-6"><div class="vx2-surface">'
        + '<div class="vx2-card-head"><div><h3 class="vx2-card-title">Sensibilité à la volatilité</h3>'
        + '<p class="vx2-card-question">Que se passe-t-il si la volatilité implicite bouge ?</p></div></div>'
        + (iv ? '<div class="vx2-table-wrap" tabindex="0"><table class="vx2-table"><thead><tr>'
          + '<th class="vx2-num">Variation d’IV</th><th class="vx2-num">Valeur</th>'
          + '<th class="vx2-num">Résultat (%)</th></tr></thead><tbody>' + iv + '</tbody></table></div>'
          : etat('Aucune sensibilité renvoyée', 'Le moteur n’a pas fourni cette décomposition pour ce contrat.', 'missing'))
        + '</div></div></div>';
    }

    var provenance = '<div class="vx2-stamp">'
      + '<span>Modèle <b>' + esc(sim.model_source || ABSENT) + '</b></span>'
      + '<span aria-hidden="true">·</span>'
      + '<span>Contrat <b>' + esc(c.symbol || ABSENT) + ' ' + esc(c.right || '') + ' '
      + esc(c.strike == null ? ABSENT : c.strike) + '</b></span>'
      + '<span aria-hidden="true">·</span>'
      + '<span>Échéance ' + esc(c.expiry || ABSENT) + '</span>'
      + '<span aria-hidden="true">·</span>'
      + '<span>Taux ' + (sim.rate && sim.rate.rate != null ? num(sim.rate.rate, { dec: 4 }) : ABSENT) + '</span>'
      + '</div>';

    return { bande: bande, corps: matrice, avance: avance, provenance: provenance,
             limites: limitations(sim.limitations) };
  }

  // ── Rendu : simulation d'ACTION / ETF (moteur multi-jambes) ────────────
  function rendreStructure(d) {
    if (!d || d.available === false) {
      var refus = (d && d.refusals || []).map(function (r) {
        return r.field + ' : ' + r.why;
      }).join(' · ');
      return { bande: '', corps: etat('Simulation refusée par le moteur',
        (d && d.reason ? d.reason : 'Le moteur a refusé de produire un résultat.')
        + (refus ? ' — ' + refus : ''), 'missing'), avance: '', provenance: '', limites: '' };
    }
    var bande = '<div class="vx2-strip">'
      + metric('Engagement net', num(d.net_premium, { unite: 'USD', directionnel: false }),
               d.is_credit ? 'crédit reçu' : 'débit versé')
      + metric('Gain maximum', d.max_profit_unbounded
          ? '<span class="vx2-mono vx2-pos">Non borné</span>'
          : num(d.max_profit, { unite: 'USD', signe: true, directionnel: true }), 'théorique')
      + metric('Perte maximum', d.max_loss_unbounded
          ? '<span class="vx2-mono vx2-neg">Non bornée</span>'
          : num(d.max_loss, { unite: 'USD', signe: true, directionnel: true }), 'théorique')
      + metric('Probabilité de gain', num(d.probability_of_profit, { unite: '%', dec: 1 }),
               d.probability_of_profit == null
                 ? 'non calculable sans volatilité implicite cotée'
                 : 'risque-neutre, pas une fréquence observée')
      + '</div>';

    var be = (d.breakevens || []);
    var bes = be.length
      ? be.map(function (b) { return num(b); }).join(' <span aria-hidden="true">·</span> ')
      : num(null);

    // Table du payoff — la visualisation critique a TOUJOURS son équivalent
    // tabulaire. On échantillonne l'affichage, pas la donnée.
    var pts = d.payoff || [];
    var pas = Math.max(1, Math.round(pts.length / 13));
    var rows = pts.filter(function (_, i) { return i % pas === 0; }).map(function (p) {
      return '<tr><td class="vx2-num">' + num(p.price) + '</td>'
        + '<td class="vx2-num">' + num(p.pnl, { signe: true, directionnel: true }) + '</td></tr>';
    }).join('');

    var corps = '<div class="vx2-banner"><span><b>Points morts — </b>' + bes
      + ' &nbsp;<span class="vx2-unit">cours auquel le résultat théorique est nul</span></span></div>'
      + '<div class="vx2-table-wrap" tabindex="0" role="region" '
      + 'aria-label="Résultat théorique à l’échéance selon le cours">'
      + '<table class="vx2-table"><caption class="vx2-sr-only">'
      + 'Résultat théorique en devise du compte, selon le cours du sous-jacent'
      + '</caption><thead><tr><th class="vx2-num">Cours</th>'
      + '<th class="vx2-num">Résultat théorique</th></tr></thead><tbody>'
      + rows + '</tbody></table></div>';

    var g = d.greeks;
    var avance = g ? '<div class="vx2-surface"><div class="vx2-card-head"><div>'
      + '<h3 class="vx2-card-title">Sensibilités</h3>'
      + '<p class="vx2-card-question">À quoi la structure réagit-elle ?</p></div></div>'
      + '<div class="vx2-strip">'
      + metric('Delta', num(g.delta, { dec: 3 }), 'cours')
      + metric('Gamma', num(g.gamma, { dec: 4 }), 'convexité')
      + metric('Theta', num(g.theta, { dec: 3 }), 'temps')
      + metric('Vega', num(g.vega, { dec: 3 }), 'volatilité')
      + '</div></div>' : '';

    var m = d.model || {};
    var provenance = '<div class="vx2-stamp">'
      + '<span>Modèle <b>' + esc(m.type || ABSENT) + '</b></span>'
      + '<span aria-hidden="true">·</span>'
      + '<span>Taux ' + num(m.r, { dec: 4 }) + '</span>'
      + '<span aria-hidden="true">·</span>'
      + '<span>Dividende ' + num(m.q, { dec: 4 }) + '</span>'
      + '<span aria-hidden="true">·</span>'
      + '<span>Base des primes ' + esc(m.premium_basis || ABSENT) + '</span></div>';

    var lim = [];
    if (m.note) lim.push(m.note);
    if (d.model_note) lim.push(d.model_note);
    if (d.execution && d.execution.note) lim.push(d.execution.note);
    return { bande: bande, corps: corps, avance: avance, provenance: provenance,
             limites: limitations(lim) };
  }

  // ── Impact portefeuille ────────────────────────────────────────────────
  function rendreImpact(d) {
    if (!d || !d.checks) return '';
    var TON = { OK: 'positive', WARN: 'caution', KO: 'negative', UNKNOWN: 'missing' };
    var MOT = { OK: 'Conforme', WARN: 'Prudence', KO: 'Bloquant', UNKNOWN: 'Inconnu' };
    var rows = d.checks.map(function (c) {
      var st = String(c.status || 'UNKNOWN').toUpperCase();
      return '<tr><td class="vx2-sticky-col"><b>' + esc(c.label || c.id) + '</b></td>'
        + '<td><span class="vx2-badge" data-state="'
        + (st === 'OK' ? 'live' : st === 'KO' ? 'error' : st === 'WARN' ? 'stale' : 'missing')
        + '">' + esc(MOT[st] || st) + '</span></td>'
        + '<td>' + esc(c.message || '') + '</td></tr>';
    }).join('');
    return '<div class="vx2-surface"><div class="vx2-card-head"><div>'
      + '<h3 class="vx2-card-title">Impact sur le portefeuille</h3>'
      + '<p class="vx2-card-question">Ce montant est-il compatible avec ce que je détiens déjà ?</p></div></div>'
      + '<div class="vx2-banner" data-kind="caution"><span>Cet impact décrit la '
      + '<b>concentration résultante</b>. Il ne calcule ni résultat, ni bêta, ni repli '
      + 'maximal du portefeuille avec la position ajoutée : aucun moteur de Vertex ne les produit. '
      + 'Ce n’est pas un dimensionnement, et Vertex ne transmet aucun ordre.</span></div>'
      + '<div class="vx2-table-wrap" tabindex="0" role="region" aria-label="Contrôles d’impact portefeuille">'
      + '<table class="vx2-table"><thead><tr><th class="vx2-sticky-col">Contrôle</th>'
      + '<th>État</th><th>Lecture</th></tr></thead><tbody>' + rows + '</tbody></table></div></div>';
  }

  function afficher(res, sym, note) {
    var zone = $('#vx-sim-resultats');
    if (!zone) return;
    /* h2 (pas h3) : meme regle que vx2.surface — le titre suit le h1 de page
       (heading-order, lot 28). `note` : la provenance du prix, DITE. */
    zone.innerHTML = '<div class="vx2-surface">'
      + '<div class="vx2-card-head"><div><h2 class="vx2-card-title">Résultats théoriques — ' + esc(sym) + '</h2>'
      + '<p class="vx2-card-question">Scénarios, pas prévisions.'
      + (note ? ' ' + esc(note) : '') + '</p></div></div>'
      + res.bande + res.corps + res.limites + res.provenance + '</div>';
    var av = $('#vx-sim-avance');
    if (av) av.innerHTML = res.avance || '';
  }

  function erreur(msg) {
    var zone = $('#vx-sim-resultats');
    if (zone) zone.innerHTML = etat('Simulation impossible', msg, 'error');
    var av = $('#vx-sim-avance'); if (av) av.innerHTML = '';
    var im = $('#vx-sim-impact'); if (im) im.innerHTML = '';
  }

  async function lancer() {
    var p = lireParams();
    if (!p.sym) { erreur('Renseigne un instrument présent dans le scan courant.'); return; }
    var btn = $('#vx-sim-run');
    if (btn) { btn.disabled = true; btn.textContent = 'Calcul…'; }
    var zone = $('#vx-sim-resultats');
    if (zone) zone.innerHTML = '<div class="vx2-skeleton" style="height:220px"></div>';

    try {
      var res;
      if (classeActive === 'option') {
        var qs = new URLSearchParams({ sym: p.sym, right: p.right });
        if (p.strike) qs.set('strike', p.strike);
        if (p.dte) qs.set('dte', p.dte);
        if (p.mid) qs.set('mid', p.mid);
        var r = await fetch('/api/options/simulate?' + qs.toString(), { credentials: 'same-origin' });
        var d = await r.json();
        if (!r.ok) {
          /* le message brut de l'API (« parametres invalides (sym, strike,
             dte, mid requis) ») parlait les champs du serveur — le refus
             nomme ceux de l'INTERFACE. */
          erreur((d && d.error && /invalides/.test(d.error))
            ? 'Une simulation d’option demande Strike, Horizon (jours) et la prime au mid. '
              + 'Reprends-les depuis le scanner ou la chaîne (« Simuler ce contrat »).'
            : (d && d.error ? d.error : 'Le moteur a refusé la simulation.'));
          return;
        }
        res = rendreOption(d);
      } else {
        // Action / ETF : une jambe `stock`. La quantité est saisie ; le prix
        // de référence suit la promesse des Hypothèses de la page : le prix
        // RÉEL du scan courant. La saisie manuelle PRIME (déclaration
        // utilisateur) ; sans scan NI saisie, refus — jamais un prix supposé.
        var qte = Number(String(p.quantite).replace(',', '.'));
        var ref = Number(String(p.mid || '').replace(',', '.'));
        var refSource = ref ? 'saisi' : null;
        if (!ref) {
          var prixDuScan = null;
          try {
            var scan = await VX.fetch('/scan', { ttl: 120000 });
            var ligne = ((scan && scan.rows) || []).find(function (r) {
              return String(r.symbol || '').toUpperCase() === p.sym; });
            if (ligne && ligne.price != null && isFinite(ligne.price)) prixDuScan = Number(ligne.price);
          } catch (e) { /* scan indisponible → refus honnête ci-dessous */ }
          if (prixDuScan) { ref = prixDuScan; refSource = 'scan'; }
        }
        if (!qte || !ref) {
          erreur(!qte
            ? 'Une simulation d’action demande une quantité de titres.'
            : 'Prix de référence absent du scan courant pour ' + p.sym
              + ' — saisis-le, Vertex ne suppose aucun prix.');
          return;
        }
        var r2 = await fetch('/api/options/analyze', {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            legs: [{ type: 'stock', strike: 0, premium: ref, qty: qte }],
            //  Aucune IV inventée : sans volatilité cotée, le moteur rend
            //  probabilité de gain et sensibilités ABSENTES (jamais un chiffre
            //  fabriqué sur une constante). Le payoff, lui, n'en a pas besoin.
            spot: ref, days: Number(p.dte) || 90, iv: null,
            sym: p.sym, name: p.sym + ' — position en actions ('
              + (refSource === 'scan' ? 'prix du scan courant' : 'prix saisi')
              + ' : ' + ref + ' $)'
          })
        });
        var d2 = await r2.json();
        if (!r2.ok) { erreur(d2 && d2.error ? d2.error : 'Le moteur a refusé la simulation.'); return; }
        res = rendreStructure(d2);
      }
      afficher(res, p.sym, (classeActive !== 'option' && typeof refSource !== 'undefined' && refSource)
        ? (refSource === 'scan' ? 'Prix de référence : prix du scan courant (' + ref + ' $).'
                                : 'Prix de référence saisi (' + ref + ' $).')
        : '');
      window.__vxSimDernier = { sym: p.sym, classe: classeActive, res: res };

      // Impact portefeuille — seulement si un MONTANT est saisi. Sans montant,
      // il n'y a pas de question à poser au moteur.
      var im = $('#vx-sim-impact');
      if (im) {
        var montant = Number(String(p.montant).replace(/\s/g, '').replace(',', '.'));
        if (montant > 0) {
          try {
            var ri = await fetch('/api/pretrade/check', {
              method: 'POST', credentials: 'same-origin',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ symbol: p.sym, amount: montant })
            });
            var di = await ri.json();
            im.innerHTML = ri.ok ? rendreImpact(di)
              : etat('Impact portefeuille indisponible',
                     (di && di.error) || 'Le moteur n’a pas répondu.', 'missing');
          } catch (e) {
            im.innerHTML = etat('Impact portefeuille indisponible',
              'La requête n’a pas abouti.', 'error');
          }
        } else {
          im.innerHTML = etat('Impact portefeuille non calculé',
            'Renseigne un montant envisagé pour voir la concentration résultante.', 'empty');
        }
      }
    } catch (e) {
      erreur('La requête n’a pas abouti : ' + (e && e.message ? e.message : 'erreur réseau') + '.');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Calculer les scénarios'; }
    }
  }

  // ── Comparaison — trois au maximum ─────────────────────────────────────
  function rendreComparaison() {
    var zone = $('#vx-sim-compare-zone');
    if (!zone) return;
    if (!comparaisons.length) {
      zone.innerHTML = etat('Aucune simulation à comparer',
        'Lance une simulation depuis Simple ou Avancé, puis « Ajouter à la comparaison ».', 'empty');
      return;
    }
    zone.innerHTML = '<div class="vx2-grid">' + comparaisons.map(function (c, i) {
      return '<div class="vx2-col-4"><div class="vx2-surface">'
        + '<div class="vx2-card-head"><div><h3 class="vx2-card-title">'
        + esc(String.fromCharCode(65 + i)) + ' — ' + esc(c.sym) + '</h3>'
        + '<p class="vx2-card-question">' + esc(c.classe === 'option' ? 'Option' : 'Action / ETF') + '</p></div></div>'
        + c.res.bande + '</div></div>';
    }).join('') + '</div>'
      + '<div class="vx2-banner" data-kind="caution"><span>Les trois colonnes partagent la '
      + 'même base de date et la même devise. Ce sont des <b>scénarios théoriques</b>, '
      + 'jamais des prévisions.</span></div>';
  }

  /* Parcours du blueprint : « Options -> Simuler le contrat ». Le contexte
     (classe, sym, right, strike, dte, mid) arrive par l'URL depuis un CLIC
     explicite — on préremplit et on lance. Aucun paramètre n'est inventé :
     ce qui manque reste vide et le refus honnête s'applique. */
  function prefillDepuisContexte() {
    var q = new URLSearchParams(location.search);
    if (!q.get('sym')) return;
    var pose = function (id, val) { var el = $('#' + id); if (el && val != null && val !== '') el.value = val; };
    if (q.get('classe') === 'action') {
      var ba = document.querySelector('[data-sim-classe="action"]');
      if (ba) ba.click();
    }
    pose('sim-sym', String(q.get('sym') || '').toUpperCase());
    pose('sim-right', q.get('right'));
    pose('sim-strike', q.get('strike'));
    pose('sim-dte', q.get('dte'));
    pose('sim-mid', q.get('mid'));
    pose('sim-quantite', q.get('quantite'));
    lancer();
  }

  function boot() {
    var f = $('#vx-sim-form');
    if (f) {
      f.addEventListener('submit', function (e) { e.preventDefault(); lancer(); });
    }
    $$('[data-sim-classe]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (btn.hasAttribute('disabled')) return;
        classeActive = btn.getAttribute('data-sim-classe');
        $$('[data-sim-classe]').forEach(function (b) {
          b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
        });
        // Les champs propres aux options n'apparaissent que pour les options.
        $$('[data-sim-bloc="option"]').forEach(function (bloc) {
          bloc.classList.toggle('is-on', classeActive === 'option');
        });
        // Le champ existe pour toutes les classes ; seul son nom change, parce
        // que « prime » et « cours de référence » ne désignent pas la même chose.
        var mid = document.getElementById('sim-mid');
        var champ = mid && mid.closest('.vx2-field');
        var lbl = champ && champ.querySelector('label');
        if (lbl) lbl.textContent = classeActive === 'option' ? 'Prime (mid)' : 'Prix de référence';
        if (mid) mid.placeholder = classeActive === 'option' ? 'par action' : 'cours';
      });
    });
    // État initial : la classe Options est active, ses champs sont visibles.
    $$('[data-sim-bloc="option"]').forEach(function (b) { b.classList.add('is-on'); });

    prefillDepuisContexte();

    var cmp = document.querySelector('[data-sim-comparer]');
    if (cmp) {
      cmp.addEventListener('click', function () {
        var d = window.__vxSimDernier;
        if (!d) {
          dire('Lance d’abord une simulation.', 'warn');
          return;
        }
        if (comparaisons.length >= MAX_COMPARAISONS) comparaisons.shift();
        comparaisons.push(d);
        rendreComparaison();
        dire('Ajouté à la comparaison (' + comparaisons.length
          + '/' + MAX_COMPARAISONS + ').', 'success');
      });
    }
    rendreComparaison();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
