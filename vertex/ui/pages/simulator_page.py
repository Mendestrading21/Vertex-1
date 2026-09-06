"""vertex.ui.pages.simulator_page — le SIMULATEUR (Vertex 2.0).

« Que pourrait devenir une position sous plusieurs scénarios explicites, et quel
serait son impact sur le portefeuille ? »

CE QUE CETTE PAGE EST
    Une composition VISUELLE de capacités de simulation qui existaient déjà et
    n'étaient réunies nulle part :

      · `/api/options/simulate`  → scénarios cours × temps, décroissance
        temporelle, sensibilité IV, gain attendu, perte planifiée, rendement
        théorique. Propriétaire : `vertex.options.scenario_pricer`.
      · `POST /api/options/analyze` → payoff, points morts, gain et perte
        maximum, probabilité de gain et Greeks d'une structure de 1 à 16
        jambes. Propriétaire : `vertex.engines.multileg_lab`.
        Ce moteur accepte une jambe `stock` (multiplicateur 1) : il calcule
        donc AUSSI le résultat théorique d'une position en actions ou en ETF.
        Cette capacité existait et n'était exploitée par aucune interface.
      · `POST /api/pretrade/check` → impact d'un montant envisagé sur le
        portefeuille : concentration résultante, plafond par titre, verdict du
        comité, régime, résultats imminents. Propriétaire :
        `vertex.engines.pretrade`.
      · `/api/portfolio/stress` → choc uniforme ±X % sur les positions actions
        réelles, au prix réel du scan. Propriétaire :
        `vertex.engines.portfolio_stress`.

CE QUE CETTE PAGE N'EST PAS
    Elle ne crée aucun moteur, aucune formule, aucun store, aucune persistance.
    Elle ne complète jamais une Greek, une IV, un mark ou un multiplicateur
    absent. Le JavaScript de cette page n'effectue AUCUN calcul financier : il
    envoie les paramètres saisis et affiche les valeurs rendues telles quelles.

CE QUI MANQUE, ET QUI EST DIT
    · Forex : aucun moteur et aucune donnée de change dans Vertex. La classe
      est présentée comme non prise en charge — pas simulée avec des hypothèses
      fabriquées.
    · ETF : le look-through des composants n'est pas simulé, faute de
      positions point-in-time. Le payoff du véhicule lui-même l'est.
    · La matrice cours × temps reste propre aux options : une action n'a pas de
      valeur temps, son résultat ne dépend que du cours. Ce n'est pas une
      absence, c'est la nature de l'instrument — et la page le dit plutôt que
      d'afficher une matrice vide.
    · L'impact portefeuille se limite à la CONCENTRATION résultante. Aucun
      moteur ne produit le P&L, le bêta ou le repli maximal du portefeuille
      avec la position ajoutée.

AUCUN ORDRE. Les sorties sont des `scénarios`, des `hypothèses` et des
`résultats théoriques` — jamais une prévision certaine ni une recommandation.
"""
from __future__ import annotations

from vertex.ui import vx2
from vertex.ui.shell import render_shell

#: Sous-vues réellement servies. « Historique » est absent volontairement :
#: aucun store canonique ne persiste une simulation, et la refonte visuelle
#: n'a pas le droit d'en créer un.
_VIEWS = (
    ('simple', 'Simple'),
    ('avance', 'Avancé'),
    ('comparer', 'Comparer'),
)

#: La comparaison vit dans la MÉMOIRE DE LA PAGE OUVERTE, et nulle part
#: ailleurs. C'est une conséquence directe du contrat ci-dessus (« aucune
#: persistance »), et l'utilisateur doit le lire avant de perdre son travail,
#: pas après.
#:
#: MESURE DU 06/09/2026 (Chromium sur 5003) : depuis « Simple », lancer une
#: simulation puis cliquer « Ajouter à la comparaison » affichait le message
#: « Ajouté à la comparaison (1/3). » — une réussite annoncée — SANS aucun
#: effet visible, la vue Simple ne portant aucune zone de comparaison. En
#: ouvrant ensuite l'onglet « Comparer », la page répondait « Aucune simulation
#: à comparer · Lance une simulation depuis Simple ou Avancé, puis Ajouter à la
#: comparaison » : elle demandait exactement ce qui venait d'être fait.
#: Deux corrections, aucune persistance créée :
#:   1. la zone de comparaison est servie SUR les vues qui portent le bouton —
#:      l'ajout a désormais un effet visible là où on le déclenche ;
#:   2. la vue « Comparer » dit la vraie cause de son vide au lieu de prescrire
#:      une boucle que la page ne peut pas tenir.
_COMPARAISON_CAUSE = (
    'Une comparaison vit dans la mémoire de la page ouverte : Vertex ne '
    'possède pas de store de simulations et cette refonte n\'en crée pas. '
    'Changer de sous-vue recharge la page et la vide donc entièrement. '
    'Construis et lis la comparaison sans quitter Simple ou Avancé : la zone '
    'y est servie sous les résultats.'
)


def _zone_comparaison(*, servie: bool) -> str:
    """Zone de comparaison. `servie` distingue les vues qui portent le bouton
    (Simple, Avancé) de la vue « Comparer », qui ne peut hériter de rien."""
    vide = (vx2.etat(
        titre='Aucune simulation à comparer',
        cause='Lance une simulation ci-dessus, puis « Ajouter à la '
              'comparaison ». Trois au maximum : au-delà, la comparaison '
              'cesse d\'être lisible.',
        kind='empty')
        if servie else
        vx2.etat(titre='Aucune simulation à comparer',
                 cause=_COMPARAISON_CAUSE, kind='missing'))
    return ('<div id="vx-sim-compare-zone" data-sim-heritable="'
            + ('1' if servie else '0') + '">' + vide + '</div>')

#: Classes d'actifs, et l'état RÉEL de leur prise en charge.
_CLASSES = (
    ('option', 'Options', 'complete'),
    ('action', 'Actions', 'complete'),
    ('etf', 'ETF', 'partielle'),
    ('forex', 'Forex', 'absente'),
)


def _tabs(view: str) -> str:
    return vx2.tabs(
        [{'label': lbl, 'href': f'/simulator?view={vid}', 'actif': vid == view}
         for vid, lbl in _VIEWS],
        libelle='Sous-vues du Simulateur')


def _selecteur_classe() -> str:
    """Le sélecteur annonce la prise en charge AVANT la saisie.

    Laisser l'utilisateur remplir un formulaire Forex pour lui répondre ensuite
    « non pris en charge » serait un piège. L'état est visible d'emblée.
    """
    chips = []
    for cid, label, etat in _CLASSES:
        suffixe = {'complete': '', 'partielle': ' · partiel',
                   'absente': ' · non pris en charge'}[etat]
        actif = ' aria-pressed="true"' if cid == 'option' else ' aria-pressed="false"'
        dis = ' disabled aria-disabled="true"' if etat == 'absente' else ''
        chips.append(
            f'<button type="button" class="vx2-chip" data-sim-classe="{cid}" '
            f'data-etat="{etat}"{actif}{dis}>{label}{suffixe}</button>')
    return ('<div class="vx2-context-group" role="group" '
            'aria-label="Classe d\'actif simulée">'
            + ''.join(chips) + '</div>')


def _formulaire() -> str:
    """Paramètres. `Montant` et `Quantité` sont deux champs DISTINCTS et
    mutuellement exclusifs (contrôle 085) : confondre « j'investis 10 000 » et
    « j'achète 10 000 titres » change le résultat d'un facteur arbitraire."""
    return (
        '<form id="vx-sim-form" class="vx2-section" autocomplete="off">'
        + vx2.champ(
            ident='sim-sym', label='Instrument',
            controle='<input class="vx2-input" id="sim-sym" name="sym" '
                     'placeholder="Ticker — ex. AAPL" maxlength="12" '
                     'spellcheck="false">',
            aide='Le titre doit être présent dans le scan courant : le '
                 'simulateur lit son prix réel, il n\'en invente aucun.')
        + '<div class="vx2-grid" style="gap:12px">'
        + '<div class="vx2-col-6">' + vx2.champ(
            ident='sim-montant', label='Montant envisagé',
            controle='<input class="vx2-input" id="sim-montant" name="montant" '
                     'inputmode="decimal" placeholder="10 000">',
            aide='En devise du compte. Distinct d\'une quantité.') + '</div>'
        + '<div class="vx2-col-6">' + vx2.champ(
            ident='sim-quantite', label='Quantité',
            controle='<input class="vx2-input" id="sim-quantite" name="quantite" '
                     'inputmode="decimal" placeholder="Nombre de titres ou de contrats">',
            aide='Titres pour une action, contrats pour une option.') + '</div>'
        + '</div>'
        #  Prix de référence et horizon valent pour TOUTES les classes : ils
        #  restent visibles quel que soit le choix. Seuls le type et le strike
        #  sont propres aux options. La première version enfermait le prix de
        #  référence dans le bloc « options » — une simulation d'action devenait
        #  alors impossible à renseigner. Vu en pilotant la page, pas en la
        #  relisant.
        + '<div class="vx2-grid" style="gap:12px">'
        + '<div class="vx2-col-6">' + vx2.champ(
            ident='sim-mid', label='Prix de référence',
            controle='<input class="vx2-input" id="sim-mid" name="mid" '
                     'inputmode="decimal" placeholder="par action">',
            aide='Pour une option : la prime au mid, par action et non par '
                 'contrat. Pour une action ou un ETF : le cours de référence.')
        + '</div>'
        + '<div class="vx2-col-6">' + vx2.champ(
            ident='sim-dte', label='Horizon',
            controle='<input class="vx2-input" id="sim-dte" name="dte" '
                     'inputmode="numeric" placeholder="180">',
            aide='En jours. Pour une option, jours jusqu\'à l\'échéance.')
        + '</div></div>'
        + '<div class="vx2-grid" data-sim-bloc="option" style="gap:12px">'
        + '<div class="vx2-col-6">' + vx2.champ(
            ident='sim-right', label='Type de contrat',
            controle='<select class="vx2-select" id="sim-right" name="right">'
                     '<option value="C">CALL</option><option value="P">PUT</option>'
                     '</select>') + '</div>'
        + '<div class="vx2-col-6">' + vx2.champ(
            ident='sim-strike', label='Strike',
            controle='<input class="vx2-input" id="sim-strike" name="strike" '
                     'inputmode="decimal" placeholder="180">') + '</div>'
        + '</div>'
        + '<div class="vx2-header-actions">'
        + '<button type="submit" class="vx2-btn vx2-btn--primary" id="vx-sim-run">'
          'Calculer les scénarios</button>'
        + '<button type="button" class="vx2-btn" id="vx-sim-compare" '
          'data-sim-comparer="1">Ajouter à la comparaison</button>'
        + '</div>'
        + '<p class="vx2-help">Vertex ne transmet aucun ordre. Ces résultats sont '
          'des scénarios théoriques calculés par ses moteurs, jamais une '
          'prévision certaine ni une recommandation.</p>'
        '</form>')


_HYPOTHESES = (
    '<ul class="vx2-hyp">'
    '<li>Le prix de référence est le <b>prix réel du scan courant</b>. '
    'Sans prix réel, la simulation est refusée — aucune valeur n\'est supposée.</li>'
    '<li>Les scénarios de cours viennent du <b>mouvement attendu</b> et du plan '
    '(invalidation, objectifs) du dossier, pas d\'un choix de l\'interface.</li>'
    '<li>Les valeurs d\'option sont calculées par le moteur de Vertex, avec la '
    'courbe de taux et le rendement du dividende mesurés. La source du modèle '
    'et ses limites sont affichées avec le résultat.</li>'
    '<li>L\'impact portefeuille compare la <b>concentration résultante</b> aux '
    'bornes du profil. Il ne calcule ni P&amp;L, ni bêta, ni repli maximal du '
    'portefeuille avec la position ajoutée : aucun moteur ne les produit. Ce '
    'n\'est pas un dimensionnement canonique.</li>'
    '<li>Aucune simulation n\'est enregistrée : Vertex ne possède pas de store '
    'de simulations, et cette refonte n\'en crée pas.</li>'
    '</ul>')


_VIEW_CONTENT = {
    'simple': (
        '<div class="vx2-grid">'
        '<div class="vx2-col-5">'
        + vx2.surface(_formulaire(), titre='Paramètres',
                      question='Que simule-t-on, et avec quelles hypothèses ?')
        + '</div>'
        '<div class="vx2-col-7">'
        '<div id="vx-sim-resultats">'
        + vx2.etat(titre='Aucune simulation lancée',
                   cause='Renseigne un instrument présent dans le scan courant, '
                         'puis lance le calcul des scénarios.',
                   kind='empty')
        + '</div></div>'
        '<div class="vx2-col-12" id="vx-sim-impact"></div>'
        '<div class="vx2-col-12">'
        + vx2.surface(_zone_comparaison(servie=True), titre='Comparaison',
                      question='Trois simulations au maximum, sur la même base '
                               'de date et de devise.')
        + '</div>'
        '<div class="vx2-col-12">'
        + vx2.surface(_HYPOTHESES, titre='Hypothèses',
                      question='Sur quoi ces scénarios reposent-ils ?')
        + '</div></div>'),
    'avance': (
        '<div class="vx2-grid">'
        '<div class="vx2-col-4">'
        + vx2.surface(_formulaire(), titre='Paramètres',
                      question='Que simule-t-on, et avec quelles hypothèses ?')
        + '</div>'
        '<div class="vx2-col-8"><div id="vx-sim-resultats">'
        + vx2.etat(titre='Aucune simulation lancée',
                   cause='Les vues avancées — matrice cours × temps, '
                         'décroissance temporelle, sensibilité à la volatilité — '
                         'apparaissent une fois les scénarios calculés.',
                   kind='empty')
        + '</div></div>'
        '<div class="vx2-col-12" id="vx-sim-avance"></div>'
        '<div class="vx2-col-12" id="vx-sim-impact"></div>'
        '<div class="vx2-col-12">'
        + vx2.surface(_zone_comparaison(servie=True), titre='Comparaison',
                      question='Trois simulations au maximum, sur la même base '
                               'de date et de devise.')
        + '</div>'
        '<div class="vx2-col-12">'
        + vx2.surface(_HYPOTHESES, titre='Hypothèses',
                      question='Sur quoi ces scénarios reposent-ils ?')
        + '</div></div>'),
    'comparer': (
        '<div class="vx2-grid">'
        '<div class="vx2-col-12">'
        + vx2.surface(
            _zone_comparaison(servie=False)
            + '<div class="vx2-header-actions">'
            + vx2.bouton('Ouvrir Simple', href='/simulator?view=simple')
            + vx2.bouton('Ouvrir Avancé', href='/simulator?view=avance',
                         variante='ghost')
            + '</div>',
            titre='Comparaison',
            question='Trois simulations au maximum, sur la même base de date et de devise.')
        + '</div>'
        '<div class="vx2-col-12">'
        + vx2.surface(_HYPOTHESES, titre='Hypothèses',
                      question='Sur quoi ces scénarios reposent-ils ?')
        + '</div></div>'),
}


def _capacites() -> str:
    """Registre de prise en charge — visible, pas enfoui dans une note de bas de page."""
    lignes = [
        ['<b>Options</b>',
         vx2.badge_etat('live', texte='Complète'),
         'Scénarios de cours, matrice cours × temps, décroissance temporelle, '
         'sensibilité à la volatilité, payoff, points morts, probabilité de '
         'gain, Greeks, gain attendu et perte planifiée.',
         '<code>/api/options/simulate</code> · <code>/api/options/analyze</code>'],
        ['<b>Actions</b>',
         vx2.badge_etat('live', texte='Complète'),
         'Payoff, point mort, perte maximale et résultat théorique par cours. '
         'Le moteur multi-jambes accepte une jambe <code>stock</code> — la '
         'capacité existait, aucune interface ne l\'exploitait. Pas de matrice '
         'temps : une action n\'a pas de valeur temps.',
         '<code>/api/options/analyze</code> · <code>/api/pretrade/check</code>'],
        ['<b>ETF</b>',
         vx2.badge_etat('partial', texte='Partielle'),
         'Même traitement qu\'une action pour le véhicule lui-même. Le '
         '<b>look-through</b> des composants n\'est pas simulé : aucune '
         'position point-in-time n\'alimente ce calcul.',
         '<code>/api/options/analyze</code>'],
        ['<b>Forex</b>',
         vx2.badge_etat('missing', texte='Non prise en charge'),
         'Aucun moteur et aucune donnée de change dans Vertex. La classe est '
         'déclarée absente plutôt que simulée avec des hypothèses fabriquées.',
         vx2.valeur(None)],
    ]
    return vx2.table(
        colonnes=[{'titre': 'Classe', 'sticky': True},
                  {'titre': 'Prise en charge'},
                  {'titre': 'Ce qui est réellement calculé'},
                  {'titre': 'Moteur'}],
        lignes=lignes,
        libelle='Prise en charge du Simulateur par classe d\'actif')


_STYLE = """
<style>
#vx-content .vx2-hyp{margin:0;padding-left:1.1rem;display:flex;flex-direction:column;
  gap:.5rem;color:var(--vx-mist);font-size:13px;line-height:1.55}
#vx-content .vx2-hyp b{color:var(--vx-ink);font-weight:600}
#vx-content .vx2-hyp code,#vx-content .vx2-table code{font-family:var(--vx-font-mono);
  font-size:11.5px;color:var(--vx-smoke)}
#vx-content [data-sim-bloc]{display:none}
#vx-content [data-sim-bloc].is-on{display:grid}
#vx-content .vx2-chip[disabled]{opacity:.4;cursor:not-allowed}
</style>
"""

_PAGE_JS = '<script src="/static/vertex/js/pages/simulator.js" defer></script>'


def render(view: str = 'simple') -> str:
    if view not in dict(_VIEWS):
        view = 'simple'
    label = dict(_VIEWS)[view]
    content = (
        _STYLE
        + '<div class="vx2-page">'
        + vx2.page_header(
            surtitre='Explorer',
            titre='Simulateur',
            question='Que pourrait devenir une position sous plusieurs scénarios '
                     'explicites, et quel serait son impact sur le portefeuille ?',
            actions=vx2.bouton('Ouvrir le Portefeuille', href='/portfolio',
                               variante='ghost'))
        + vx2.context_bar([
            {'label': 'Classe', 'contenu': _selecteur_classe()},
            {'label': 'Nature', 'contenu':
                '<span class="vx2-badge" data-state="missing">Résultats théoriques</span>'},
            {'label': 'Enregistrement', 'contenu':
                '<span class="vx2-stamp">Aucun — pas de store de simulations</span>'},
        ])
        + _tabs(view)
        + _VIEW_CONTENT[view]
        + vx2.section(
            titre='Prise en charge par classe d\'actif',
            note='ce qui est calculé, et ce qui ne l\'est pas',
            corps=_capacites())
        + '</div>')
    return render_shell(
        title='Simulateur', active='simulator', space_label='Simulateur',
        sub_label=label, page_label='Simulateur',
        content=content, page_js=_PAGE_JS)


__all__ = ['render']
