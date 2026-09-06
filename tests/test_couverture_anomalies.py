# -*- coding: utf-8 -*-
"""Le détecteur d'anomalies dit COMBIEN de ses familles il a pu évaluer.

Mesure du 2026-09-06 : le seul appelant de production
(`vertex.engines.anomaly_context.build`) construit son contexte avec
`context = {}` puis n'y ajoute au plus que `benchmark_closes`. Les blocs
`fundamentals` et `events` ne lui sont JAMAIS transmis.

Recensement des 42 appels à `add()` du détecteur : **15 ne peuvent pas se
déclencher** — sept fondamentales (dont `VALUATION_DISLOCATION`,
`EARNINGS_REVISION_SHOCK`, `QUALITY_DETERIORATION`) et huit événementielles
(dont `GUIDANCE_SHOCK`, `POST_EARNINGS_DRIFT`).

Deux des clés lues n'ont AUCUN producteur dans le dépôt — `quality_flags` et
`eps_revision_pct` — donc `QUALITY_DETERIORATION` et la pénalité de score de
`vertex.scanner.stages` sont mortes par construction. Une troisième,
`sector_median_pe`, en a bien un (`vertex.options.pack`), mais il n'atteint
jamais ce détecteur : la donnée existe, c'est le câble qui manque. Confondre
les deux maladies mènerait à la mauvaise réparation.

Rien n'est FAUX là-dedans — aucune anomalie inventée. Mais l'appelant publiait
`provenance: OHLCV_ENRICHED` avec `limitations: []` dès qu'un benchmark était
présent : une couverture complète annoncée pour 27 détecteurs sur 42. Une
absence silencieuse se lit « rien à signaler », c'est-à-dire l'inverse d'une
mesure.

Ce banc vérifie deux choses : que la couverture est rendue, et que les comptes
déclarés correspondent au CODE — un recensement figé qui dérive est pire
qu'aucun recensement.
"""
import ast
import inspect
import os
import re

from vertex.anomalies import stock_anomalies as sa


def _familles_du_code() -> dict[str, int]:
    """Compte les `add()` par bloc de contexte, en LISANT le module.

    On suit `context.get('x')` : chaque `add()` qui vient après appartient à la
    famille ainsi ouverte. C'est exactement la structure du fichier, et si elle
    change, ce banc le dit au lieu de faire confiance à une constante.
    """
    src = inspect.getsource(sa)
    famille, comptes = 'prix_volume', {}
    correspondance = {'benchmark_closes': 'relatif', 'fundamentals': 'fondamental',
                      'events': 'evenement'}
    for ligne in src.split('\n'):
        m = re.search(r"context\.get\('(\w+)'\)", ligne)
        if m and m.group(1) in correspondance:
            famille = correspondance[m.group(1)]
        if re.search(r"\badd\('[A-Z_]+'", ligne):
            comptes[famille] = comptes.get(famille, 0) + 1
    return comptes


def test_le_recensement_declare_correspond_au_code():
    reels = _familles_du_code()
    declares = {nom: spec['detections'] for nom, spec in sa.FAMILLES.items()}
    assert reels == declares, (
        'le recensement des familles a dérivé du code — mesuré %s, déclaré %s'
        % (reels, declares))


def test_le_contexte_reellement_fourni_ne_couvre_pas_tout():
    """Le cas du produit : bars + benchmark, rien d'autre."""
    c = sa.couverture_detecteurs({'benchmark_closes': [1.0, 2.0, 3.0]})
    assert c['complet'] is False
    assert set(c['familles_absentes']) == {'fondamental', 'evenement'}, c
    assert c['detections_executees'] == 27
    assert c['detections_totales'] == 42
    assert len(c['limitations']) == 2
    for ligne in c['limitations']:
        assert 'non exécutée' in ligne and 'absent du contexte' in ligne, ligne


def test_un_contexte_complet_est_declare_complet():
    """Contre-épreuve : la garde ne doit pas crier au loup en permanence."""
    c = sa.couverture_detecteurs({'benchmark_closes': [1.0], 'fundamentals': {'pe': 20},
                                  'events': {'earnings_in_days': 3}})
    assert c['complet'] is True
    assert c['limitations'] == []
    assert c['detections_executees'] == c['detections_totales']


def test_sans_contexte_seules_les_familles_de_prix_sont_evaluees():
    c = sa.couverture_detecteurs(None)
    assert c['familles_evaluees'] == ['prix_volume']
    assert c['detections_executees'] == 23


def test_les_trois_cles_sans_producteur_sont_nommees_dans_la_raison():
    """La mesure qui a fait trouver le défaut doit rester écrite."""
    doc = sa.couverture_detecteurs.__doc__ or ''
    for cle in ('quality_flags', 'sector_median_pe', 'eps_revision_pct'):
        #  Les trois restent nommées, mais pour deux raisons DIFFÉRENTES : la
        #  documentation doit garder la distinction.
        assert cle in doc, (
            '%s n’est plus nommée : la prochaine lecture d’une clé sans '
            'producteur repartira de zéro' % cle)


def test_aucune_de_ces_trois_cles_n_a_acquis_un_producteur_en_silence():
    """Si l'une est enfin produite, ce banc le dit — et la doc doit suivre."""
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ecrites = set()
    #  Le détecteur RÉÉMET dans son événement la clé qu'il vient de lire
    #  (`{'sector_median_pe': sector_pe}`) : le compter comme producteur ferait
    #  croire que la donnée entre quelque part, alors qu'elle ne fait que
    #  ressortir. On cherche un producteur AMONT, donc ailleurs que chez le
    #  consommateur.
    consommateurs = {'stock_anomalies.py', 'stages.py'}
    for dossier, sous, noms in os.walk(os.path.join(racine, 'vertex')):
        sous[:] = [d for d in sous if d != '__pycache__']
        for nom in noms:
            if not nom.endswith('.py') or nom in consommateurs:
                continue
            with open(os.path.join(dossier, nom), encoding='utf-8') as f:
                try:
                    arbre = ast.parse(f.read())
                except SyntaxError:
                    continue
            for n in ast.walk(arbre):
                if isinstance(n, ast.Dict):
                    ecrites |= {k.value for k in n.keys
                                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                elif isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store) \
                        and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                    ecrites.add(n.slice.value)
    #  `sector_median_pe` est volontairement hors de cette liste : il A un
    #  producteur (`vertex/options/pack.py`), ce qui est justement la nuance
    #  que la documentation porte. Ne restent que les deux clés orphelines.
    nouvelles = {'quality_flags', 'eps_revision_pct'} & ecrites
    assert not nouvelles, (
        '%s a désormais un producteur : la détection correspondante peut être '
        'branchée, et la documentation de couverture doit être corrigée'
        % sorted(nouvelles))
