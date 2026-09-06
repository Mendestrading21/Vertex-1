"""vertex/app/routes/redesign.py — routes du Vertex Master Redesign (§10-11).

Huit espaces + fiche canonique + redirections des anciennes routes (avec
conservation du ticker, de la vue et des filtres). Strangler pattern : le
monolithe garde ses APIs, ses pages HTML legacy sont remplacées ici.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, send_from_directory

from vertex.ui.pages import (analysis_page, briefing, design_system_page,
                             intelligence_page, markets_page, opportunities_page,
                             options_intel_page, performance_page, portfolio_page,
                             system_page, tracking_page)

# Anciennes routes → nouvelles destinations (§11). Jamais de suppression sèche.
LEGACY_REDIRECTS = {
    '/daily': '/',
    '/analyse': '/analysis',
    '/news': '/',
    '/semaine': '/',
    '/brief': '/',
    '/stocks': '/analysis',
    '/compare': '/analysis?view=compare',
    '/comparateur': '/analysis?view=compare',
    '/entreprises': '/analysis',
    '/analyse-entreprise': '/analysis',
    '/strategie': '/portfolio',
    '/strategy': '/portfolio',
    '/ma-page': '/portfolio?view=watchlist',
    '/moi': '/portfolio?view=watchlist',
    '/watchlist': '/portfolio?view=watchlist',
    '/suivi': '/portfolio?view=watchlist',
    '/suivis': '/portfolio?view=watchlist',
    '/options-lab': '/opportunities?view=options',
    '/options-desk': '/opportunities?view=options',
    '/sectors': '/#sectors',
    '/heatmap': '/#sectors',
    '/catalysts': '/opportunities?view=calendar',
    '/catalyseurs': '/opportunities?view=calendar',
    '/anomalies': '/opportunities?view=anomalies',
    '/decisions': '/journal?view=journal',
    '/review': '/intelligence?view=committee',
    '/research': '/intelligence?view=research',
    '/equipe': '/intelligence?view=strategy',
    '/equipe-du-mois': '/intelligence?view=strategy',
    '/bordel': '/intelligence',
    '/strategy-os': '/intelligence?view=strategy',
    '/vertex-intelligence': '/intelligence?view=analyst',
    '/health': '/system?view=data',
    '/settings': '/system?view=settings',
    '/parametres': '/system?view=settings',
    '/vault': '/system?view=archive',
    '/archive': '/system?view=archive',
}


VX_STATIC_DIR = Path(__file__).resolve().parents[2] / 'static' / 'vertex'


def make_blueprint(scan_state: dict) -> Blueprint:
    bp = Blueprint('redesign', __name__)

    # Les assets du redesign vivent dans vertex/static/vertex/** (architecture
    # cible §9) ; le dossier statique Flask historique reste static/ à la
    # racine. Cette règle, plus spécifique que /static/<path>, sert le
    # sous-arbre vertex/.
    @bp.route('/static/vertex/<path:filename>')
    def vx_static(filename):
        resp = send_from_directory(VX_STATIC_DIR, filename)
        resp.cache_control.max_age = 3600
        return resp

    # ── Espaces principaux ────────────────────────────────────────────
    @bp.route('/')
    def briefing_route():
        return briefing.render(scan_state=scan_state)

    # ── Marchés (Vertex 2.0) — page de PREMIÈRE CLASSE, à nouveau.
    # Elle avait été fusionnée dans le Dashboard par redirection d'ancre. La
    # conséquence : « une visualisation dominante par sous-vue » devenait
    # impossible, puisque Synthèse, Macro, Secteurs, Participation et Volatilité
    # partageaient un même écran avec le brief et le portefeuille. Le module
    # `markets_page` existait déjà et rendait ces cinq sous-vues : la refonte le
    # remet en service, elle ne le crée pas.
    @bp.route('/markets')
    def markets_route():
        return markets_page.render(view=request.args.get('view', 'overview'))

    @bp.route('/opportunities')
    def opportunities_route():
        return opportunities_page.render(view=request.args.get('view', 'radar'),
                                         params=request.args)

    @bp.route('/portfolio')
    def portfolio_route():
        return portfolio_page.render(view=request.args.get('view', 'team'))

    @bp.route('/analysis')
    def analysis_index_route():
        return analysis_page.render_index(view=request.args.get('view', ''))

    @bp.route('/analysis/<sym>')
    def analysis_route(sym):
        return analysis_page.render(sym.upper())

    # ── Journal (espace canonique n°7) — décisions, hypothèses, revues,
    # erreurs, statistiques et apprentissage. Rendu par performance_page (mission
    # « mesurer la méthode ») ; la performance de PORTEFEUILLE migrera vers
    # Portefeuille lors de la refonte de contenu. /performance redirige ici.
    # ── Performance (Vertex 2.0) — « la méthode fonctionne-t-elle, et est-elle
    # bien appliquée ? ». Le Journal en devient une SOUS-VUE : il mesure la même
    # chose, à l'échelle de la décision individuelle.
    #
    # `/journal` continue de répondre 200 sur exactement le même rendu. Rediriger
    # aurait été plus propre en apparence, mais l'URL est en favori, en lien dans
    # le produit et dans une trentaine de bancs : une fonction existante ne doit
    # pas devenir introuvable pour la commodité d'un plan de nommage.
    @bp.route('/performance')
    @bp.route('/journal')
    def performance_route():
        return performance_page.render(view=request.args.get('view', 'overview'),
                                       params=request.args)

    # ── Intelligence — N'EST PLUS un espace principal (PR n°2). Son raisonnement
    # de comité sera intégré à Analyse (refonte Analyse). Page conservée joignable
    # hors nav le temps de la migration (aucune fonctionnalité perdue).
    @bp.route('/intelligence')
    def intelligence_route():
        return intelligence_page.render(view=request.args.get('view', 'analyst'))

    @bp.route('/system')
    def system_route():
        return system_page.render(view=request.args.get('view', 'connections'))

    @bp.route('/system/design-system')
    def design_system_route():
        from vertex.ui.pages import design_system_demo
        return design_system_demo.render()

    # ── Options Intelligence (§18) — espace de première classe (5e des 8
    # entrées PRIMARY_NAV, actif « Options »). Aussi rejoignable depuis
    # Opportunités (vue Options), la fiche Analyse et la palette.
    @bp.route('/options')
    def options_intel_route():
        return options_intel_page.render(view=request.args.get('view', 'structure'))

    # ── Dossier Options d'un titre — la « machine d'analyse » d'un sous-jacent
    # (chaîne, probabilités, IV, scénarios, stratégies). Bascule Action|Options
    # depuis la fiche /analysis/<sym>.
    # ── Dossier Options d'un titre — chaîne CALL/strike/PUT, probabilités,
    # IV, scénarios, stratégies.
    #
    # COLLISION DE ROUTE, connue et documentée dans CLAUDE.md : `/options/<sym>`
    # est déclaré DEUX fois — ici, et dans `ticker_api.opt_ep` qui rend du JSON.
    # C'est le JSON qui gagne. Conséquence mesurée : cette page n'a jamais été
    # servie, et les NEUF liens internes qui pointaient vers elle déversaient du
    # JSON brut à l'utilisateur.
    #
    # Supprimer l'endpoint JSON serait une modification de backend, hors du
    # périmètre de cette refonte visuelle. La page reçoit donc une URL qui lui
    # appartient, et les liens la suivent. `/options/<sym>` reste servi à
    # l'identique pour ses éventuels consommateurs.
    #
    # Besoin hors périmètre consigné : déduplquer la route côté backend, et
    # rendre `/options/<sym>` à la page — le JSON est déjà servi sous
    # `/api/options/chain/<sym>` et `/api/options/chain-grid/<sym>`.
    @bp.route('/options/dossier/<sym>')
    def options_symbol_route(sym):
        from vertex.ui.pages import options_symbol_page
        return options_symbol_page.render(sym)

    # ── Calendrier (Vertex 2.0) — surface transversale composée de la SEULE
    # source d'événements agrégés du produit, `/cal-feed` (résultats + macro +
    # couverture du calendrier officiel). La vue `/opportunities?view=calendar`
    # reste servie : cette page ne la remplace pas.
    # Dividendes, expirations, catalyseurs hors résultats et revues planifiées
    # n'ont AUCUNE source dans Vertex : la page les déclare absents plutôt que
    # d'afficher une grille vide qui laisserait croire qu'il n'y a rien.
    @bp.route('/calendar')
    def calendar_route():
        from vertex.ui.pages import calendar_page
        return calendar_page.render(view=request.args.get('view', 'today'))

    # ── Simulateur (Vertex 2.0) — composition VISUELLE de capacités de
    # simulation qui existaient déjà et n'étaient réunies nulle part :
    # `/api/options/simulate` (scénarios cours × temps), `/api/options/analyze`
    # (payoff multi-jambes, qui accepte aussi une jambe `stock` — capacité
    # présente et jusqu'ici inexploitée par l'interface) et
    # `/api/pretrade/check` (concentration résultante).
    # Aucun moteur, aucun store, aucun ordre n'est créé ici.
    @bp.route('/simulator')
    def simulator_route():
        from vertex.ui.pages import simulator_page
        return simulator_page.render(view=request.args.get('view', 'simple'))

    # ── Suivi (Vertex 2.0) — « quelles thèses, idées et décisions exigent une
    # attention ? ». Vue transversale : elle ne possède aucun store, elle compose
    # watchlist, suivis et revues dont les propriétaires restent inchangés.
    # `/tracking` reste servi pour la même raison que `/journal`.
    @bp.route('/follow-up')
    @bp.route('/tracking')
    def follow_up_route():
        return tracking_page.render(view=request.args.get('view', 'attention'))

    # ── Design System (§50) — page de référence visuelle « vivante »
    # (OBSIDIAN COPPER). Purement cosmétique : aucune donnée, aucun moteur.
    # Accessible depuis Système via le lien /design-system. À distinguer de la
    # vitrine Command Surface (§34/§35) servie sur /system/design-system.
    @bp.route('/design-system')
    def design_system_page_route():
        return design_system_page.render()

    # ── Widget Lab — LABORATOIRE du Design System (bibliothèque de widgets).
    # Route AUTONOME hors produit : aucune donnée réelle, aucun moteur, pas dans
    # la nav. Sert à voir/comparer/tester/choisir les widgets (V1…Vn + états).
    # Source de vérité : la bibliotheque de widgets (archive, retiree du depot).
    @bp.route('/widget-lab')
    def widget_lab_route():
        from vertex.ui.pages import widget_lab
        return widget_lab.render()

    # ── Brief éditorial (§21) : paquet structuré → 10 lignes ─────────
    @bp.route('/api/briefing/editorial')
    def briefing_editorial():
        base = briefing.build_editorial(scan_state)
        # Brief quotidien §15 (PRE_MARKET/INTRADAY/CLOSE/WEEKLY) : sections
        # sourcées + actualités RÉELLES validées (news_state) — fusionné sans
        # casser le schéma historique (lines/word_count/...).
        try:
            from vertex.app.state import news_state
            from vertex.market.daily_brief import build_daily_brief
            from vertex.services import persist as _persist
            desk = _persist.load_json('desk_data.json', {}) or {}
            import json as _json
            raw = (desk.get('data') or {}).get('myTrades')
            trades = _json.loads(raw) if isinstance(raw, str) else (raw or [])
            syms = sorted({str(t.get('sym', '')).upper() for t in trades
                           if isinstance(t, dict) and t.get('sym')})
            daily = build_daily_brief(scan_state, news_state, syms)
            base.update({'daily': daily, 'kind': daily['kind'],
                         'sources': daily['sources'],
                         'what_changed_today': daily['what_changed'],
                         'main_risk': daily['main_risk'],
                         'main_opportunity': daily['main_opportunity']})
        except Exception:
            #  CODE STABLE, pas le texte de l'exception. `str(e)[:120]` partait
            #  dans `jsonify(base)` : un message de bibliotheque, en anglais,
            #  servi comme etat (meme faute que `IndexError: single positional
            #  indexer is out-of-bounds` sur `/options/<sym>`, deja corrigee).
            #  Le motif reste NOMME cote francais ; le detail interne, lui, ne
            #  traverse plus la frontiere HTTP.
            base['daily_error'] = 'daily_brief_unavailable'
            base['daily_error_note'] = ('brief quotidien indisponible — '
                                        'sections sourcées non calculées, '
                                        'aucune ligne n’est inventée')
        # Brief éditorial narratif (§10) — texte fluide de séance, sourcé, jamais
        # de fait d'actualité inventé. Fusionné sans casser le schéma historique.
        try:
            from vertex.app.state import news_state
            from vertex.market.editorial import build_narrative
            base['editorial'] = build_narrative(scan_state, news_state)
        except Exception:
            base['editorial_error'] = 'editorial_unavailable'
            base['editorial_error_note'] = ('éditorial narratif indisponible — '
                                            'le texte de séance n’est pas '
                                            'reconstitué à partir d’une '
                                            'supposition')
        return jsonify(base)

    # ── Simulation d'un contrat (moteur scenario_pricer — §35) ───────
    @bp.route('/api/options/simulate')
    def options_simulate():
        from vertex.options import scenario_pricer
        from vertex.options.models import UnderlyingSetup
        a = request.args
        sym = (a.get('sym') or '').upper()
        detail = (scan_state.get('detail') or {}).get(sym) or {}
        plan = detail.get('plan') or {}
        try:
            spot = float(a.get('spot') or detail.get('price') or 0)
            contract = {
                'symbol': sym, 'right': (a.get('right') or 'C')[:1].upper(),
                'strike': float(a.get('strike')), 'dte': int(a.get('dte') or 0),
                'mid': float(a.get('mid')) if a.get('mid') else None,
                'iv': float(a.get('iv')) if a.get('iv') else None,
                'expiry': a.get('exp') or '',
            }
        except (TypeError, ValueError):
            return jsonify({'error': 'paramètres invalides (sym, strike, dte, mid requis)'}), 400
        if spot <= 0:
            return jsonify({'error': f'{sym}: spot indisponible — simulation refusée '
                                     '(aucune donnée inventée)'}), 422
        notes = []
        # Normalisations documentées : le board historique exprime l'IV en %
        # et le coût en dollars PAR CONTRAT (prime × 100).
        if contract['iv'] and contract['iv'] > 3:
            contract['iv'] = round(contract['iv'] / 100.0, 4)
            notes.append('IV convertie de % en décimal')
        if contract['mid'] and spot and contract['mid'] > spot:
            contract['mid'] = round(contract['mid'] / 100.0, 4)
            notes.append('prime par contrat convertie en prime par action (÷100)')
        #  Entrees MESUREES, pas des constantes : meme proprietaire que
        #  `options_intel_api`, pour que les deux routes disent le meme prix.
        from vertex.options import entrees_mesurees as _entrees
        setup = UnderlyingSetup(
            symbol=sym, spot=spot,
            invalidation=plan.get('stop'), tp1=plan.get('tp1'),
            tp2=plan.get('tp2'), tp3=plan.get('tp3'),
            dividend_yield=(_entrees.rendement_dividende(scan_state, sym) or 0.0))
        try:
            sim = scenario_pricer.simulate(contract, setup,
                                           rate_curve=_entrees.courbe(scan_state))
            sim['entrees'] = _entrees.provenance(scan_state, sym)
            analysis = scenario_pricer.capital_free_analysis(sim, contract)
        except Exception:
            #  MESURE du 2026-09-06, instance de test (`app.test_client()`) :
            #  `GET /api/options/simulate?sym=AAPL&spot=100&strike=0&dte=30&mid=5`
            #  rendait 422 avec `"simulation impossible: float division by
            #  zero"`, et `...&iv=99999` rendait `"math domain error"`. Deux
            #  messages de la bibliotheque standard, en anglais, servis comme
            #  etat : le lecteur n'apprend ni ce qui manque ni quoi corriger.
            #  Code stable + note francaise ; le detail reste au serveur.
            return jsonify({
                'error': 'simulation_impossible',
                'note': 'le moteur de scénarios n’a pas pu évaluer ce contrat '
                        'avec ces paramètres (strike, échéance, IV ou prime '
                        'hors domaine) — aucune valeur n’est inventée',
            }), 422
        sim['limitations'] = list(sim.get('limitations') or []) + notes
        return jsonify({'symbol': sym, 'contract': contract, 'sim': sim,
                        'capital_free': analysis})

    # ── Redirections legacy (conservation ticker/vue/filtres) ────────
    def _legacy(target):
        def _view(**kwargs):
            dest = target
            extra = request.query_string.decode()
            if extra:
                # Une cible avec fragment (/#sectors) : la query s'insère AVANT
                # le '#', sinon l'URL est malformée (/#sectors?x=1).
                if '#' in dest:
                    base, frag = dest.split('#', 1)
                    dest = base + ('&' if '?' in base else '?') + extra + '#' + frag
                else:
                    dest += ('&' if '?' in dest else '?') + extra
            return redirect(dest, code=301)
        return _view

    for old, new in LEGACY_REDIRECTS.items():
        bp.add_url_rule(old, endpoint=f'legacy_{old.strip("/").replace("-", "_").replace("/", "_")}',
                        view_func=_legacy(new))

    @bp.route('/titre/<sym>')
    @bp.route('/company/<sym>')
    def legacy_titre(sym):
        return redirect(f'/analysis/{sym.upper()}', code=301)

    return bp
