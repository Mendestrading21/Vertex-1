"""
LOT 154 — Caractérisation de la classification d'actualités
(`vertex/market/news_impact.py`) et du pipeline d'ingestion
(`vertex/market/news_pipeline.py`) — deux modules à ZÉRO test direct,
servis par daily_brief (§15).

Ces tests figent le classement par mots-clés, l'arithmétique
d'importance, les seuils de direction potentielle, la validation/
déduplication du pipeline et les comportements limites observés — les
changer devient une décision explicite. Titres synthétiques
déterministes (aucun texte externe réel).
"""

import pytest

from vertex.market import news_impact as ni
from vertex.market import news_pipeline as npl


# ── classify : priorité des catégories et défaut ─────────────────────────────

@pytest.mark.parametrize('title,cat', [
    ('Fed signals rate cut after earnings', 'MACRO'),   # MACRO prioritaire sur RESULTATS
    ('Congress passes new tariff bill', 'POLITIQUE'),
    ('Q3 earnings beats estimates', 'RESULTATS'),
    ('Company raises guidance', 'GUIDANCE'),
    ('Semiconductor demand surges', 'SECTEUR'),
    ('Apple announces new product', 'ENTREPRISE'),      # défaut sans mot-clé
])
def test_classify_priorite_et_defaut(title, cat):
    assert ni.classify(title) == cat


def test_classify_titre_absent_entreprise():
    assert ni.classify(None) == 'ENTREPRISE'
    assert ni.classify('') == 'ENTREPRISE'


def test_classify_limite_sous_chaine_documentee():
    # Comportement limite DOCUMENTÉ : le matching est par SOUS-CHAÎNE,
    # pas par mot entier — le mot-clé 'ai' matche À L'INTÉRIEUR de
    # « mountain » ou « rain » → SECTEUR. Passer à des frontières de
    # mots = décision explicite (changerait des classements existants).
    assert ni.classify('Mountain hiking gear sales') == 'SECTEUR'
    assert ni.classify('Rain delays harvest') == 'SECTEUR'


# ── score_importance : arithmétique exacte 0-100 ─────────────────────────────

def test_importance_base_et_corroborations_plafonnees():
    assert ni.score_importance({}, []) == 30                       # base (corrob 1 → +0)
    assert ni.score_importance({'corroborations': 4}, []) == 60    # +30
    assert ni.score_importance({'corroborations': 10}, []) == 60   # cap +30


def test_importance_bonus_et_plafond_100():
    assert ni.score_importance({'category': 'MACRO'}, []) == 40
    assert ni.score_importance({'sentiment': 0.5}, []) == 35       # |senti| ≥ 0.5 → +5
    assert ni.score_importance({'sentiment': 0.49}, []) == 30
    # Tout cumulé : 30 + 30 + 25 (portefeuille) + 15 (RESULTATS) + 5 = 105 → 100.
    ev = {'entities': ['ACN'], 'category': 'RESULTATS',
          'sentiment': 0.6, 'corroborations': 4}
    assert ni.score_importance(ev, ['ACN']) == 100


# ── potential_impact : seuils EXACTS ±0.15, confiance plafonnée 0.7 ──────────

@pytest.mark.parametrize('senti,direction,conf', [
    (0.15, 'NEUTRE', 0.3), (0.16, 'POSITIF_POTENTIEL', 0.16),
    (-0.15, 'NEUTRE', 0.3), (-0.16, 'NEGATIF_POTENTIEL', 0.16),
    (0.9, 'POSITIF_POTENTIEL', 0.7),                    # jamais > 0.7 (humble)
])
def test_direction_potentielle_seuils_exacts(senti, direction, conf):
    assert ni.potential_impact({'sentiment': senti}) == \
        {'direction': direction, 'confidence': conf}


def test_direction_sentiment_illisible_inconnue():
    assert ni.potential_impact({}) == {'direction': 'INCONNUE', 'confidence': 0.0}
    assert ni.potential_impact({'sentiment': 'x'}) == \
        {'direction': 'INCONNUE', 'confidence': 0.0}


# ── pipeline.collect : validation, dédup, tri — rejets comptés ───────────────

STATE = {'items': [
    {'title': 'Fed rate cut', 'publisher': 'Reuters',
     'time': '2026-08-07T10:00', 'senti': 0.6, 'sym': 'acn'},
    {'title': 'Fed rate cut', 'source': 'AP', 'date': '2026-08-07T11:00'},  # doublon
    {'title': '', 'publisher': 'X', 'time': 't'},       # titre vide → rejeté
    {'title': 'No source'},                              # sans source/heure → rejeté
    'brut',                                              # non-dict → rejeté
    {'title': 'Small item', 'source': 'S', 'date': 'd', 'fr': ''},
], 'updated': 'U'}


def test_pipeline_rejets_comptes_jamais_masques():
    out = npl.collect(STATE, ['ACN'])
    assert out['rejected'] == 3
    assert out['raw_count'] == 6
    assert out['updated'] == 'U'
    assert len(out['events']) == 2      # 4 valides → dédup → 2


def test_pipeline_doublon_fusionne_en_corroborations_et_importance():
    """MESURE DU 2026-09-06 — le +25 « portefeuille » était pris sur une
    attribution fausse. L'item source est `{'title': 'Fed rate cut',
    'sym': 'acn'}` : `sym` est le FIL INTERROGE par la boucle de collecte, pas
    le sujet de la dépêche — sur les 45 items réels servis, 22 titres sur 45
    ne nomment ni le ticker ni la société. Une baisse de taux de la Fed était
    donc rattachée à la position ACN (`positions_concerned == ['ACN']`) et
    gagnait +25 d'importance à ce titre : 80 au lieu de 55.

    Le banc épinglait cette valeur ; il épingle maintenant la valeur JUSTE.
    L'événement n'est pas perdu : il reste servi, avec sa provenance dite
    (`provenance_sym`) et son rôle (`fil`), simplement sans entité affirmée.
    """
    ev = npl.collect(STATE, ['ACN'])['events'][0]
    # Les deux « Fed rate cut » fusionnent : corroborations 2 →
    # importance 30 +10 (corrob) +10 (MACRO) +5 (senti 0.6) = 55.
    # Le +25 portefeuille N'EST PAS pris : le titre ne parle pas d'ACN.
    assert ev['title'] == 'Fed rate cut'
    assert ev['corroborations'] == 2
    assert ev['category'] == 'MACRO'
    assert ev['importance'] == 55
    assert ev['entities'] == [], 'aucune entité affirmée sans sujet établi'
    assert ev['positions_concerned'] == []
    assert ev['provenance_sym'] == 'ACN' and ev['sym_role'] == 'fil'


def test_pipeline_l_entite_est_affirmee_quand_le_titre_nomme_le_titre():
    """Le symétrique du précédent : quand le sujet EST établi, rien n'est
    perdu — l'entité, la position concernée et le +25 reviennent."""
    etat = {'items': [{'title': 'ACN beats estimates', 'publisher': 'Reuters',
                       'time': '2026-08-07T10:00', 'senti': 0.6, 'sym': 'acn'}],
            'updated': 'U'}
    ev = npl.collect(etat, ['ACN'])['events'][0]
    assert ev['entities'] == ['ACN'] and ev['sym_role'] == 'sujet'
    assert ev['positions_concerned'] == ['ACN']
    assert ev['importance'] == 30 + 25 + 15 + 5, 'base + portefeuille + RESULTATS + senti'
    #  Un rôle posé par un PRODUCTEUR est respecté tel quel, jamais recalculé.
    etat['items'][0].update({'title': 'Fed rate cut', 'sym_role': 'sujet'})
    assert npl.collect(etat, ['ACN'])['events'][0]['entities'] == ['ACN']


def test_pipeline_compte_les_entites_non_etablies():
    """Le compte est DIT, comme les rejets : 2 items valides portent un ticker
    de provenance dont le sujet n'est pas établi (les deux « Fed rate cut »
    n'en portent qu'un — le doublon n'a pas de `sym`)."""
    out = npl.collect(STATE, ['ACN'])
    assert out['entites_non_etablies'] == 1
    assert npl.collect({'items': []})['entites_non_etablies'] == 0


def test_pipeline_normalisation_fr_vide_none_et_tri():
    out = npl.collect(STATE, ['ACN'])
    small = out['events'][1]
    assert small['title'] == 'Small item'
    assert small['title_fr'] is None            # fr vide → None honnête
    assert small['importance'] == 30
    imps = [e['importance'] for e in out['events']]
    assert imps == sorted(imps, reverse=True)   # tri par importance desc


def test_pipeline_etat_vide_contrat_honnete():
    """Intention inchangee : sur un etat vide, rien n'est invente.

    L'assertion portait sur l'egalite stricte du dict rendu, ce qui est plus
    fort que son intention. Depuis D-125, `collect` AJOUTE `rejets_par_cause`
    et `rejets_note` — le rejet disait combien, jamais pourquoi. Aucun champ
    d'origine ne change, et c'est ce que ce banc verifie desormais, en exigeant
    que les compteurs neufs soient eux aussi honnetement a zero.
    """
    out = npl.collect({}, None)
    for cle, attendu in (('events', []), ('rejected', 0),
                         ('raw_count', 0), ('updated', None)):
        assert out[cle] == attendu, cle
    assert set(out['rejets_par_cause'].values()) == {0}
    assert set(out) - {'events', 'rejected', 'raw_count', 'updated'} \
        == {'rejets_par_cause', 'rejets_note', 'entites_non_etablies'}
    assert out['entites_non_etablies'] == 0


def test_les_entites_non_etablies_comptent_des_EVENEMENTS_pas_des_items():
    """MESURE DU 2026-09-06 (contrôle adverse) — le compteur était incrémenté
    dans la boucle d'ITEMS, donc AVANT `deduplicate`. Deux dépêches identiques
    portant le même fil interrogé et aucun sujet établi rendaient 1 événement
    servi et `entites_non_etablies == 2` : un compte qu'aucune lecture de la
    réponse ne peut retrouver, sous une clé dont la note dit « événements »
    — alors que `rejected`, lui, compte les ITEMS et l'écrit.

    Le compteur est désormais calculé sur les événements servis, et sur ce
    qu'ils AFFIRMENT (`entities` vide malgré un `provenance_sym`).
    """
    etat = {'items': [
        {'title': 'Fed rate cut', 'publisher': 'Reuters',
         'time': '2026-08-07T10:00', 'sym': 'ACN'},
        {'title': 'Fed rate cut', 'publisher': 'AP',
         'time': '2026-08-07T11:00', 'sym': 'ACN'},
    ]}
    out = npl.collect(etat, [])
    assert len(out['events']) == 1, 'les deux dépêches fusionnent'
    assert out['events'][0]['corroborations'] == 2
    assert out['entites_non_etablies'] == 1, (
        'le compteur suit les ÉVÉNEMENTS servis, pas les items reçus')
