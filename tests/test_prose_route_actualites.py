# -*- coding: utf-8 -*-
"""La documentation de `/news-feed` ne contredit pas ce que la route SERT.

Mesure du 2026-09-06 (contrôle adverse) : la docstring de la route affirmait
« l'attestation du vendeur est déclarée NON_IMPLÉMENTÉ : aucun producteur du
dépôt ne pose `sym_atteste` », alors que la MÊME fonction servait
`sujet_preuves['attestation_vendeur'] = 'ACTIF'` depuis qu'un producteur avait
été branché. Aucune valeur servie n'était fausse — c'est la prose qui l'était.

C'est la façon la plus discrète de rendre une garde inutile : un lecteur qui
croit le commentaire ne va pas vérifier la réponse. Ce banc lit les deux et les
confronte, pour chaque canal de preuve, sans réseau ni courtier.
"""
import inspect
import os
import re

import pytest


@pytest.fixture()
def preuves_servies(monkeypatch):
    """L'état RÉEL des canaux, lu sur la réponse de la route."""
    monkeypatch.setenv('VERTEX_CODE', '')
    monkeypatch.setenv('DEMO', '1')
    monkeypatch.setenv('NO_IBKR', '1')
    from vertex.runtime import app
    corps = app.test_client().get('/news-feed').get_json() or {}
    etat = corps.get('sujet_preuves')
    assert isinstance(etat, dict) and etat, (
        'la route ne sert plus l’état des canaux de preuve : %r' % (etat,))
    return etat


def _docstring_de_la_route() -> str:
    """La docstring lue sur la FONCTION, pas cherchée par son nom dans le texte.

    Un motif nommant `news_feed` aurait raté `news_feed_ep`, et une garde qui
    ne trouve rien se contente de passer.
    """
    import ast

    from vertex.app.routes import content
    arbre = ast.parse(inspect.getsource(content))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.FunctionDef) and noeud.name.startswith('news_feed'):
            doc = ast.get_docstring(noeud)
            if doc:
                return doc
    raise AssertionError('la route /news-feed n’a plus de documentation')


def test_aucun_canal_ACTIF_n_est_declare_non_implemente_par_la_prose(preuves_servies):
    doc = _docstring_de_la_route()
    actifs = [c for c, etat in preuves_servies.items() if etat == 'ACTIF']
    assert actifs, preuves_servies
    fautifs = []
    for canal in actifs:
        #  Le canal nommé dans la même phrase qu'une déclaration d'absence.
        for phrase in re.split(r'(?<=[.!?])\s+', doc):
            mots = canal.replace('_', ' ')
            if mots in phrase.lower() and 'NON_IMPLÉMENT' in phrase:
                fautifs.append((canal, phrase.strip()[:110]))
    assert not fautifs, (
        'la documentation déclare absent un canal que la route sert comme '
        'ACTIF : %s' % fautifs)


def test_la_prose_dit_que_l_etat_est_DERIVE_et_non_ecrit_en_dur():
    """Une valeur dérivée retombe d'elle-même ; une constante ment en silence."""
    doc = _docstring_de_la_route()
    assert 'dérivé' in doc.lower() or 'balayage' in doc.lower(), (
        'la documentation doit dire que l’état des canaux est MESURÉ, sinon '
        'rien ne distingue une constante d’une mesure')


def test_l_etat_servi_ne_contient_que_des_valeurs_du_vocabulaire(preuves_servies):
    """Absence, activité et non-implémentation restent DISTINCTES."""
    admis = {'ACTIF', 'NON_IMPLÉMENTÉ', 'NON_IMPLEMENTE', 'INACTIF', 'ABSENT'}
    inconnus = {c: v for c, v in preuves_servies.items() if v not in admis}
    assert not inconnus, inconnus
