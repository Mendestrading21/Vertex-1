"""tests/test_simulateur_comparaison_et_provenance.py — LOT G : le Simulateur
annonçait une réussite sans effet, prescrivait une boucle impossible, et
servait des jetons de moteur bruts à la place d'un texte d'interface.

MESURES DU 06/09/2026 (Chromium sur l'instance QA 5003, NO_IBKR=1, DEMO=0,
scan à 513 lignes) — AVANT les correctifs :

1. COMPARAISON SANS EFFET, PUIS BOUCLE IMPOSSIBLE
   Depuis `/simulator` (Simple), classe Actions, VEEV quantité 10 :
     · la simulation rend un résultat réel (engagement net 2 750,90 USD) ;
     · clic « Ajouter à la comparaison » → message « Ajouté à la comparaison
       (1/3). », c'est-à-dire une RÉUSSITE annoncée ;
     · `#vx-sim-compare-zone` mesuré : ABSENT de la vue Simple. Le clic
       n'avait donc AUCUN effet visible là où il était déclenché ;
     · onglet « Comparer » → « Aucune simulation à comparer · Lance une
       simulation depuis Simple ou Avancé, puis Ajouter à la comparaison ».
       La page réclamait exactement ce qui venait d'être fait, et qui ne
       pouvait pas survivre à la navigation : `comparaisons` vit dans la
       portée du module, et la page n'a aucun store.
   APRÈS : la zone est servie sur Simple et Avancé (le clic affiche la carte
   « A — VEEV »), et « Comparer » nomme la vraie cause de son vide.
   Aucune persistance n'est créée : le contrat de la page l'interdit.

2. JETONS DE MOTEUR BRUTS DANS L'ESTAMPILLE
   Sur VEEV C 280, 180 j, mid 15, l'estampille servie était :
     « Modèle FALLBACK_ESTIMATE · Contrat VEEV C 280 · Échéance — · Taux
       0,0380 », et AUCUN de ses éléments ne portait d'attribut `title`.
   `FALLBACK_ESTIMATE` signifie qu'aucune IV n'était cotée et qu'elle a été
   réinversée depuis le prix : toute la matrice repose sur une entrée
   reconstruite. C'était illisible (anglais, jeton machine), sans état de
   qualité, et le tiret d'échéance était muet.
   APRÈS : « Modèle [Black-Scholes, IV reconstruite] » (pastille `stale`,
   `title` explicatif) et « Échéance — » porte « Donnée indisponible — non
   servie par le moteur ».

Ces bancs mesurent des PROPRIÉTÉS (présence de l'hôte de sortie du bouton,
absence d'écrasement de l'état servi, couverture des jetons que le moteur peut
réellement émettre) plutôt que des libellés. Nés ROUGES.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from vertex.ui.pages import simulator_page as sp

_JS = Path('vertex/static/vertex/js/pages/simulator.js').read_text(encoding='utf-8')


def _bloc(nom: str, source: str = None) -> str:
    """Corps d'une fonction JS, par comptage d'accolades."""
    js = source if source is not None else _JS
    debut = js.index(nom)
    i = js.index('{', debut)
    prof = 0
    for fin in range(i, len(js)):
        if js[fin] == '{':
            prof += 1
        elif js[fin] == '}':
            prof -= 1
            if prof == 0:
                return js[i:fin + 1]
    raise AssertionError(f'bloc non refermé : {nom}')


def test_le_bouton_de_comparaison_a_son_hote_de_sortie():
    """Un bouton dont la sortie n'a nulle part où s'écrire est un bouton mort.

    Mesuré : Simple et Avancé portaient `data-sim-comparer` mais AUCUN
    `#vx-sim-compare-zone`. Le clic ne produisait qu'un message de réussite."""
    for vue, _ in sp._VIEWS:
        page = sp.render(view=vue)
        porte_bouton = 'data-sim-comparer' in page
        porte_zone = 'id="vx-sim-compare-zone"' in page
        if porte_bouton:
            assert porte_zone, (
                f'la vue {vue!r} propose « Ajouter à la comparaison » sans '
                'servir la zone qui en affiche le résultat : le clic reste '
                'sans effet visible')


def test_la_vue_comparer_nomme_la_cause_de_son_vide():
    """Elle prescrivait la boucle que l'utilisateur venait de faire.

    On mesure la DISCRIMINATION entre les deux vides possibles : celui d'un
    hôte qui peut être rempli sur place, et celui d'un hôte qui ne peut hériter
    de rien. Deux situations différentes ne peuvent pas partager un message."""
    comparer = sp.render(view='comparer')
    simple = sp.render(view='simple')
    #  `vx2.etat` échappe la cause avant de la servir : on compare ce qui est
    #  réellement dans la page, pas la constante brute.
    cause = html.escape(sp._COMPARAISON_CAUSE)
    assert cause in comparer, (
        'la vue « Comparer » doit dire pourquoi elle est structurellement '
        'vide (aucune persistance), pas réclamer une action déjà faite')
    assert cause not in simple, (
        'la cause de non-héritage ne vaut pas pour une vue qui remplit sa '
        'propre zone : deux vides distincts, deux explications distinctes')
    assert 'data-sim-heritable="0"' in comparer
    assert 'data-sim-heritable="1"' in simple


def test_le_script_n_ecrase_pas_l_etat_vide_servi():
    """`rendreComparaison()` réécrivait l'état vide au chargement, remplaçant
    l'explication servie par un message générique — y compris sur la vue
    « Comparer », où cette explication est la seule chose honnête à dire."""
    corps = _bloc('function rendreComparaison()')
    #  Le corps de la branche « rien à comparer », borné par ses accolades :
    #  découper au premier `innerHTML` rencontré ferait passer le banc sur la
    #  version fautive, où cet `innerHTML` EST la faute.
    branche_vide = _bloc('!comparaisons.length', corps)
    assert 'innerHTML' not in branche_vide, (
        'quand il n\'y a rien à comparer, le script doit laisser en place '
        'l\'état SERVI, qui porte la cause propre à cet hôte ; le réécrire '
        'efface l\'explication de la vue « Comparer »')


def test_tout_jeton_de_modele_emis_par_le_moteur_est_nomme_en_francais():
    """Le jeton machine n'est pas un texte d'interface (invariant : tout le
    texte visible est en français clair), et la distinction entre IV cotée et
    IV reconstruite change la confiance qu'on accorde au résultat.

    Les jetons ne sont pas recopiés ici : ils sont LUS dans le moteur, si bien
    qu'un nouveau `model_source` fera tomber ce banc au lieu de fuir à l'écran.
    """
    pricer = Path('vertex/options/scenario_pricer.py').read_text(encoding='utf-8')
    from vertex.options.models import GREEKS_MODEL

    jetons = {GREEKS_MODEL}
    jetons |= set(re.findall(r"result\['model_source'\]\s*=\s*'([A-Z_]+)'", pricer))

    table = _bloc('var MODELES =')
    for jeton in jetons:
        assert re.search(r'\b' + re.escape(jeton) + r'\s*:', table), (
            f'le moteur peut émettre model_source={jeton!r} ; la page le '
            'servirait tel quel, en anglais, sans état de qualité')

    #  Les deux états ne peuvent pas se ressembler : une IV reconstruite est
    #  une donnée dégradée, elle ne se lit pas comme une IV cotée.
    etats = dict(re.findall(r"(\w+):\s*\{[^}]*?etat:\s*'(\w+)'", table))
    assert etats.get('MODEL_ESTIMATE') != etats.get('FALLBACK_ESTIMATE'), (
        'IV cotée et IV réinversée depuis le prix doivent porter des états de '
        'qualité distincts — sinon la dégradation est invisible')


def test_l_estampille_ne_pose_aucun_tiret_muet():
    """Un tiret expliqué est honnête ; un tiret nu ne dit ni ce qui manque, ni
    pourquoi. Mesuré : zéro `title` sur l'estampille servie, « Échéance — »
    compris."""
    for fonction in ('function rendreOption(', 'function rendreStructure('):
        corps = _bloc(fonction)
        debut = corps.index("var provenance")
        stamp = corps[debut:corps.index('</div>', debut)]
        assert '|| ABSENT' not in stamp and '? ABSENT' not in stamp, (
            f'{fonction} pose encore un tiret nu dans son estampille : une '
            'absence doit passer par `texteOuAbsent`/`num`, qui la nomment')
    aide = _bloc('function texteOuAbsent(')
    assert 'title=' in aide, 'l\'absence doit porter son explication'


def test_un_dividende_inconnu_ne_s_affiche_pas_comme_un_zero_mesure():
    """CONTRÔLE ADVERSE du 06/09/2026 — l'estampille de la structure servait
    « Dividende 0,0000 » pour un rendement que le moteur déclare INCONNU.

    MESURE AVANT (Chromium sur une instance QA, /simulator classe Actions,
    VEEV × 10, réponse réelle de `POST /api/options/analyze`) :
      estampille → « Modèle Lognormal risque-neutre · Taux 0,0300 ·
                     Dividende 0,0000 · Base des primes déclarée »
      même réponse → `entrees.dividende = {rendement: null, applique: false,
        motif: "rendement du dividende inconnu pour ce titre — non applique"}`
    Le moteur refuse explicitement de rendre `0.0` pour un rendement inconnu ;
    `model.q` retombe à 0.0 pour CALCULER, et la page publiait ce 0.0 comme une
    mesure à quatre décimales. Zéro et absence sont deux états distincts.

    Le fait moteur est MESURÉ ici (appel réel de `provenance`), pas recopié :
    si un jour le rendement inconnu devenait 0.0 côté moteur, ce banc tombe et
    on relit la question au lieu de la perdre de vue."""
    from vertex.options import entrees_mesurees as em

    prov = em.provenance({}, 'VEEV')['dividende']
    assert prov['rendement'] is None and prov['applique'] is False, (
        'le moteur ne distingue plus « inconnu » de « nul » : ce banc mesurait '
        f'cette distinction — reçu {prov!r}')
    assert prov['motif'], 'une absence sans motif ne peut pas être affichée'

    corps = _bloc('function rendreStructure(')
    debut = corps.index('var provenance')
    stamp = corps[debut:corps.index('</div>', debut)]
    i = stamp.index('Dividende')
    champ = stamp[i:stamp.index('</span>', i)]
    assert 'm.q' not in champ, (
        'le dividende est lu dans `model.q`, qui vaut 0.0 quand le rendement '
        'est inconnu : un zéro affiché à la place d\'une absence')
    assert 'entrees' in champ, (
        'seul le bloc de provenance distingue « rendement nul » de « rendement '
        'inconnu » : le champ doit y puiser')
