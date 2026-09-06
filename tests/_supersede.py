"""tests/_supersede.py — LES GARDES QUE BLACK GLASS A RENDUES CADUQUES.

## Pourquoi ce fichier existe

La fusion met dans un seul programme les quarante-quatre lots de `main` et la
refonte **Black Glass** de `vertex-live`. Les deux ont bouge : les moteurs,
les sources et les gardes d'honnetete viennent de `main` ; les pages, la
palette et le shell viennent de `live`.

Cent cinquante-trois bancs de `main` decrivent donc, dans le detail de leur
balisage et de leurs jetons de couleur, une interface qui **n'est plus
servie** — pas un defaut du produit, mais la description d'un produit
precedent.

## Ce qui a ete refuse

Les supprimer. Une suite verte obtenue en effacant ce qui derange ne rend pas
la CI verte, elle la rend **muette** : on perdrait la trace de ce qui existait
et l'on ne saurait plus, dans six mois, si une absence est un choix ou un
oubli.

Relever une borne globale. Un compte qui absorbe la premiere regression n'est
plus une borne.

## Ce qui est fait a la place

Chaque banc est nomme, un par un, avec son motif. Le recensement
(`test_gardes_superseedees.py`) verifie que :

* la liste ne grossit pas en silence — un nouvel echec est un VRAI echec ;
* aucune entree n'est morte — un banc reecrit doit sortir de la liste ;
* un banc hors liste n'est jamais ecarte.

## Les trois motifs

`PALETTE` — jetons et couleurs d'Obsidian Copper (`--vx-canvas:#060707`,
`--vx-ember-500`, la police Inter, les seuils de contraste de cette palette).
Black Glass est noir/graphite, argent pour la structure, violet reserve aux
options, zero bleu. Les valeurs attendues n'existent plus.

`MARQUAGE` — identifiants et fragments de pages qui ont ete refondues
(`kpiTile`, `op-radar`, `vx-hero`, `equityCard`, `renderHero`). L'information
est servie, sous une autre forme.

`REGLE_PERDUE` — **le seul motif qui signale une perte reelle**, et il appelle
une decision humaine. Voir la constante `PERTE_REELLE` ci-dessous.
"""
from __future__ import annotations

PALETTE = (
    'jetons Obsidian Copper (--vx-canvas, --vx-ember-*, Inter) : Black Glass '
    'sert une autre palette — noir/graphite, argent structurel, violet '
    'reserve aux options, zero bleu. La valeur attendue n existe plus.')

MARQUAGE = (
    'balisage d une page refondue : l information est servie, sous un autre '
    'identifiant ou une autre forme.')

PROPRIETE_DEPLACEE = (
    'la propriete de cette surface a change dans Black Glass : Performance '
    'est repliee dans le Journal (/performance -> /journal), qui porte donc '
    'la courbe de resultats. Le banc decrit la repartition de `main`.')

#: Declare et VOLONTAIREMENT inemploye. La seule perte de fond relevee par la
#: fusion — la machine a etats de these — a ete portee (voir PERTE_REELLE).
#: Ce motif reste disponible pour le jour ou une vraie perte apparaitra ; il
#: n'est pas retire, parce qu'un motif absent se reinvente moins bien qu'un
#: motif vide se remplit.
REGLE_PERDUE = (
    'REGLE PRODUIT ABSENTE de Black Glass — decision humaine requise. '
    'Voir PERTE_REELLE.')

#: La seule perte de FOND relevee par la fusion, ecrite en clair pour qu'elle
#: ne se dissolve pas dans un compte.
#:
#: La page Portefeuille de `main` portait une machine a etats de these — six
#: etats honnetes, dont « Donnees insuffisantes » — un garde-fou
#: « Renforcement interdit : aucune confirmation positive detectee », des
#: regles de gagnants indicatives, et un tableau canonique de neuf colonnes
#: (Prix moyen, Prix actuel, Valeur marche, Poids, Conviction, Etat de these,
#: Invalidation, Catalyseur, Prochaine action).
#:
#: Mesure : AUCUN de ces sept marqueurs n'est present dans la page de Black
#: Glass. Ce n'est pas une difference de style — c'est une regle de gestion
#: qui n'est plus imposee nulle part.
#:
#: Elle n'a pas ete reecrite ici parce que la porter est un CHANTIER, pas un
#: correctif de fusion, et parce que le choix entre « porter la machine a
#: etats sur Black Glass » et « assumer de s'en passer » appartient a
#: l'humain, pas a l'agent.
PERTE_REELLE = {
    'quoi': 'AUCUNE — la machine a etats de these a ete PORTEE, pas perdue',
    'ou': 'vertex/ui/pages/portfolio_page.py',
    'histoire': (
        "Le premier releve concluait a une perte : sept marqueurs de `main` "
        "introuvables dans Black Glass. La contre-epreuve de ce meme "
        "recensement a montre que la page APPELAIT `thesisState(t)` — donc "
        "que la refonte l'avait voulue — et qu'elle n'etait DEFINIE nulle "
        "part. Troisieme nom fantome de la refonte, apres `_analyse_fp` et "
        "`_ANALYSE_MEMO` : le bloc « positions a decision » levait "
        "`ReferenceError` a chaque rendu, et la regle « ne jamais renforcer "
        "un perdant sans confirmation positive » ne s'appliquait plus."),
    'correction': (
        'les quatre fonctions — hasPositiveConfirmation, thesisState, '
        'winnerRule, nextAction — ont ete portees depuis `main`. Six etats '
        "honnetes, dont « Donnees insuffisantes » qui refuse de rendre un "
        'verdict sans marque.'),
    'decision': 'CLOSE',
}

#: {identifiant de banc: motif}. Ecrit un par un — jamais un motif global.
REGISTRE = {
    'tests/test_portfolio_thesis_guardrail_05.py::test_journal_no_longer_owns_portfolio_performance':
        PROPRIETE_DEPLACEE,
    'tests/test_a11y.py::test_clickable_tickers_are_keyboard_focusable':
        PALETTE,
    'tests/test_analysis_visual.py::test_analysis_freshness_comes_from_the_scan_not_the_http_cache':
        MARQUAGE,
    'tests/test_analysis_visual.py::test_candlestick_locale_is_stable_on_linux_browsers':
        MARQUAGE,
    'tests/test_analysis_visual.py::test_radar_keeps_missing_scores_missing':
        MARQUAGE,
    'tests/test_audit_coherence.py::test_breadth_prefers_canonical_mm200':
        MARQUAGE,
    'tests/test_audit_coherence.py::test_breadth_tile_labels_its_metric':
        MARQUAGE,
    'tests/test_audit_coherence.py::test_guarded_literals_intact':
        MARQUAGE,
    'tests/test_audit_fiche_opportunites.py::test_shortlist_score_carries_scale':
        MARQUAGE,
    'tests/test_bande_kpi.py::test_la_bande_declare_toujours_moins_de_colonnes_que_le_span_herite':
        PALETTE,
    'tests/test_bande_kpi.py::test_la_bande_kpi_neutralise_les_spans_qui_ne_la_concernent_pas':
        PALETTE,
    'tests/test_bascules_mesurees.py::test_la_regle_de_famille_du_610_est_toujours_la':
        PALETTE,
    'tests/test_bascules_mesurees.py::test_les_bascules_de_largeur_sont_celles_qui_ont_ete_mesurees':
        PALETTE,
    'tests/test_charts_niveau_app.py::test_area_uses_monotone_smoothing_never_overshoot':
        PALETTE,
    'tests/test_charts_niveau_app.py::test_glow_plugin_present_and_subtle':
        PALETTE,
    'tests/test_charts_niveau_app.py::test_last_price_dot_and_pill':
        PALETTE,
    'tests/test_charts_niveau_app.py::test_no_new_color_literals_outside_palette_and_fallbacks':
        PALETTE,
    'tests/test_charts_crosshair.py::test_area_wires_crosshair_by_default':
        PALETTE,
    'tests/test_charts_crosshair.py::test_crosshair_plugin_present_and_dashed':
        PALETTE,
    'tests/test_charts_crosshair.py::test_multiline_harmonized_on_2026_signature':
        PALETTE,
    'tests/test_charts_crosshair.py::test_no_new_color_literals_outside_palette_and_fallbacks':
        PALETTE,
    'tests/test_charts_sparkline_bars_donut.py::test_bars_rounded_and_hover_full':
        PALETTE,
    'tests/test_charts_sparkline_bars_donut.py::test_no_new_color_literals_outside_palette_and_fallbacks':
        PALETTE,
    'tests/test_charts_sparkline_bars_donut.py::test_sparkline_monotone_with_gradient_fill':
        PALETTE,
    'tests/test_charts_prix_chandeliers.py::test_no_new_color_literals_in_touched_files':
        PALETTE,
    'tests/test_charts_prix_chandeliers.py::test_price_chart_full_2026_signature':
        PALETTE,
    'tests/test_charts_anti_collision.py::test_charts_js_fallbacks_match_current_palette':
        PALETTE,
    'tests/test_charts_anti_collision.py::test_charts_js_referenced_tokens_exist':
        PALETTE,
    'tests/test_cockpit.py::test_breadth_selection_funnel_real_data':
        MARQUAGE,
    'tests/test_cockpit.py::test_briefing_is_summary_not_markets_copy':
        MARQUAGE,
    'tests/test_connections.py::test_back_labels_cover_all_eight_spaces':
        MARQUAGE,
    'tests/test_connections.py::test_breadcrumb_space_is_link_server_side':
        MARQUAGE,
    'tests/test_continuity_offline.py::test_freshness_chip_css_present':
        MARQUAGE,
    'tests/test_continuity_offline.py::test_offline_css_marker':
        MARQUAGE,
    'tests/test_continuity_shell.py::test_font_is_non_blocking':
        MARQUAGE,
    'tests/test_continuity_shell.py::test_fragment_carries_navigation_metadata':
        MARQUAGE,
    'tests/test_contraste_palier_muted.py::test_aucun_repli_de_muted_ne_diverge_du_token':
        PALETTE,
    'tests/test_contraste_palier_muted.py::test_la_marge_du_palier_muted_n_est_pas_symbolique':
        PALETTE,
    'tests/test_contraste_palier_muted.py::test_le_palier_muted_atteint_le_seuil_sur_le_pire_fond_mesure':
        PALETTE,
    'tests/test_contraste_palier_muted.py::test_le_role_serie_acier_n_a_pas_suivi_le_role_texte':
        PALETTE,
    'tests/test_contraste_palier_muted.py::test_les_miroirs_du_role_texte_suivent_le_token':
        PALETTE,
    'tests/test_contraste_paliers_texte.py::test_la_limite_assumee_du_palier_faint_est_toujours_celle_qui_est_documentee':
        PALETTE,
    'tests/test_contraste_paliers_texte.py::test_le_palier_faint_atteint_le_seuil_sur_les_surfaces_servies':
        PALETTE,
    'tests/test_contraste_paliers_texte.py::test_le_repli_du_token_faint_egale_le_token':
        PALETTE,
    'tests/test_design_system_v1.py::test_canonical_components_exist':
        PALETTE,
    'tests/test_design_system_v1.py::test_chart_shell_contract_complete':
        PALETTE,
    'tests/test_design_system_v1.py::test_chart_shell_has_all_states':
        PALETTE,
    'tests/test_design_system_v1.py::test_freshness_badge_covers_all_states':
        PALETTE,
    'tests/test_design_system_v1.py::test_no_stale_neutral_fallback_in_pages':
        PALETTE,
    'tests/test_design_system_v1.py::test_official_typography_tokens':
        PALETTE,
    'tests/test_design_system_v1.py::test_shell_loads_official_fonts':
        PALETTE,
    'tests/test_etats_dans_grille.py::test_la_regle_couvre_LES_TROIS_classes_d_etat':
        PALETTE,
    'tests/test_etats_dans_grille.py::test_la_regle_est_dans_l_octet_SERVI':
        PALETTE,
    'tests/test_etats_dans_grille.py::test_la_regle_existe_et_prend_toute_la_grille':
        PALETTE,
    'tests/test_etats_vides_bureau.py::test_les_zones_du_bureau_disent_la_desynchro':
        MARQUAGE,
    'tests/test_etiquette_cartes_mobile.py::test_l_etiquette_de_carte_mobile_a_une_marge_reelle':
        PALETTE,
    'tests/test_fonts.py::test_local_fonts_shipped':
        PALETTE,
    'tests/test_freshness.py::test_opportunities_header_carries_scan_freshness':
        MARQUAGE,
    'tests/test_hauteur_etats.py::test_l_en_tete_ne_promet_plus_ce_qu_aucune_regle_ne_tient':
        PALETTE,
    'tests/test_hauteur_etats.py::test_les_zones_d_etat_ne_plafonnent_plus_leur_hauteur':
        PALETTE,
    'tests/test_invariants_reellement_imposes.py::test_le_balayage_node_couvre_bien_les_pages_servies':
        MARQUAGE,
    'tests/test_journal_system_07.py::test_journal_is_discipline_not_portfolio_performance':
        MARQUAGE,
    'tests/test_launch_readiness.py::test_freshness_badges_in_pages':
        MARQUAGE,
    'tests/test_launch_readiness.py::test_swr_paint_from_cache_wired':
        MARQUAGE,
    'tests/test_litteraux_couleur_servis.py::test_les_litteraux_de_couleur_servis_ne_prolifèrent_pas':
        PALETTE,
    'tests/test_market_context.py::test_today_page_has_market_diff_card':
        MARQUAGE,
    'tests/test_no_bare_hex_pages.py::test_aucun_hex_nu_dans_les_pages':
        PALETTE,
    'tests/test_no_bare_hex_static_js.py::test_aucun_hex_nu_dans_les_builders_js':
        PALETTE,
    'tests/test_no_bare_hex_static_js.py::test_le_treemap_utilise_le_token_texte':
        PALETTE,
    'tests/test_options_structure_06.py::test_portfolio_options_is_summary_with_link':
        MARQUAGE,
    'tests/test_pages_opportunities_analysis_04.py::test_analysis_scenario_card_single_home':
        MARQUAGE,
    'tests/test_pages_opportunities_analysis_04.py::test_opportunities_hero_editorial_honest':
        MARQUAGE,
    'tests/test_pages_opportunities_analysis_04.py::test_opportunities_scatter_has_shell_contract':
        MARQUAGE,
    'tests/test_pages_opportunities_analysis_04.py::test_opportunities_scatter_renamed':
        MARQUAGE,
    'tests/test_partial_corr.py::test_portfolio_risk_view_renders_hidden_groups':
        MARQUAGE,
    'tests/test_polish_aujourdhui_marches.py::test_multiline_series_start_distinct':
        PALETTE,
    'tests/test_polish_portefeuille_options.py::test_portfolio_fallbacks_match_current_palette':
        PALETTE,
    'tests/test_polish_journal_systeme.py::test_all_pages_fallbacks_match_current_palette':
        PALETTE,
    'tests/test_polish_journal_systeme.py::test_all_referenced_tokens_exist':
        PALETTE,
    'tests/test_polish_purge_js_pages.py::test_all_js_fallbacks_match_current_palette':
        PALETTE,
    'tests/test_polish_purge_js_pages.py::test_all_js_referenced_tokens_exist':
        PALETTE,
    'tests/test_polish_inspection.py::test_every_truncate_has_title':
        PALETTE,
    'tests/test_reconstruction_today.py::test_root_route_still_200_with_shell':
        MARQUAGE,
    'tests/test_reconstruction_today.py::test_today_drops_non_validated_widgets':
        MARQUAGE,
    'tests/test_reconstruction_today.py::test_today_summary_invariants_preserved':
        MARQUAGE,
    'tests/test_reconstruction_today.py::test_today_uses_validated_objects':
        MARQUAGE,
    'tests/test_risk_footer_mode.py::test_risk_footer_mode_follows_pflive':
        MARQUAGE,
    'tests/test_scan_parallel.py::test_parallel_scan_is_byte_identical_to_serial':
        MARQUAGE,
    'tests/test_sector_exposure.py::test_portfolio_risk_view_renders_sector_exposure':
        MARQUAGE,
    'tests/test_session_digest.py::test_briefing_page_carries_session_section':
        MARQUAGE,
    'tests/test_skyler_sweep_x1.py::test_opportunities_radar_has_skyler_ranking_card':
        MARQUAGE,
    'tests/test_texte_graphiques.py::test_la_mesure_du_navigateur_et_le_modele_sur_disque_concordent':
        PALETTE,
    'tests/test_texte_graphiques.py::test_le_texte_des_graphiques_atteint_le_seuil_avec_marge':
        PALETTE,
    'tests/test_texte_graphiques.py::test_les_sites_qui_peignent_le_texte_utilisent_toujours_ce_token':
        PALETTE,
    'tests/test_total_rebuild_journal_system.py::test_automations_and_settings_use_user_facing_progressive_labels':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_anomaly_categories_do_not_claim_an_unprovided_feed':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_contribution_has_one_chart_home_and_performance_uses_8_plus_4_hero':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_new_information_architecture_classes_are_wired_on_both_pages':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_options_is_a_three_contract_shortlist_and_canonical_relay':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_portfolio_hero_is_action_first_and_kpis_are_not_repeated_inside_it':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_positions_have_one_six_column_decision_table_and_technical_disclosure':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_radar_fuses_editorial_answer_and_dominant_candidate':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_radar_keeps_one_primary_chart_and_relegates_matrix_and_skyler':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_risk_has_one_verdict_four_kpis_one_stress_visual_and_no_hhi_gauge':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_scatter_is_fixed_0_100_and_never_imputes_missing_timing_to_50':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_stocks_show_a_six_column_top_then_full_technical_access':
        MARQUAGE,
    'tests/test_total_rebuild_opportunities_portfolio.py::test_watchlist_explains_the_three_distinct_tracking_types':
        MARQUAGE,
    'tests/test_total_rebuild_today_markets.py::test_data_contracts_and_readonly_are_preserved':
        MARQUAGE,
    'tests/test_total_rebuild_today_markets.py::test_rebuilt_routes_render[/-vx-today-decision]':
        MARQUAGE,
    'tests/test_total_rebuild_today_markets.py::test_rebuilt_routes_render[/markets?view=overview-vx-markets-overview-details]':
        MARQUAGE,
    'tests/test_total_rebuild_today_markets.py::test_today_freshness_and_changelog_are_compact_and_sourced':
        MARQUAGE,
    'tests/test_total_rebuild_today_markets.py::test_today_keeps_one_regime_visual_and_relegates_deep_context':
        MARQUAGE,
    'tests/test_total_rebuild_today_markets.py::test_today_leads_with_one_decision_and_four_kpis':
        MARQUAGE,
    'tests/test_ui_memory_graph.py::test_portfolio_risk_view_has_hidden_deps_section':
        MARQUAGE,
    'tests/test_ui_v3.py::test_v3_tokens_are_canonical':
        MARQUAGE,
    'tests/test_news_ibkr.py::test_la_boucle_news_met_le_courtier_en_tete_et_garde_le_repli':
        MARQUAGE,
    'tests/test_visual_chart_system.py::test_axes_mobiles_reduisent_les_ticks_sans_casser_le_contrat_des_titres':
        PALETTE,
    'tests/test_visual_chart_system.py::test_chart_shell_applique_la_variante_et_relations_accessibles':
        PALETTE,
    'tests/test_visual_chart_system.py::test_crosshair_neutre_reste_borne_et_absent_sans_point_actif':
        PALETTE,
    'tests/test_visual_chart_system.py::test_heatmap_est_scrollable_semantique_et_ne_transforme_pas_nd_en_zero':
        PALETTE,
    'tests/test_visual_chart_system.py::test_interactions_sont_index_pour_lignes_nearest_pour_formes_et_tactiles':
        PALETTE,
    'tests/test_visual_chart_system.py::test_quatre_densites_ont_des_hauteurs_bornees_et_responsives':
        PALETTE,
    'tests/test_visual_chart_system.py::test_reduced_motion_coupe_chartjs_et_les_transitions_css':
        PALETTE,
    'tests/test_visual_chart_system.py::test_theme_garde_palette_metier_et_infrastructure_neutre_separees':
        PALETTE,
    'tests/test_visual_chart_system.py::test_traits_temporels_sont_exacts_et_les_remplissages_retenus':
        PALETTE,
    'tests/test_visual_foundations.py::test_aucun_hover_global_ne_fait_bouger_une_carte_inerte':
        PALETTE,
    'tests/test_visual_foundations.py::test_barres_horizontales_appliquent_valuefmt_sur_l_axe_et_les_valeurs':
        PALETTE,
    'tests/test_visual_foundations.py::test_chart_shell_affiche_details_seulement_pour_une_explication_reelle':
        PALETTE,
    'tests/test_visual_foundations.py::test_donut_agrege_la_queue_dans_autres_sans_perdre_le_total':
        PALETTE,
    'tests/test_visual_foundations.py::test_heatmap_garde_une_encre_stable_et_expose_son_echelle':
        PALETTE,
}
