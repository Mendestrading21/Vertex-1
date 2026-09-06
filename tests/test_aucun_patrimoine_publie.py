# -*- coding: utf-8 -*-
"""Aucun chiffre du desk RÉEL de la machine n'apparaît dans un fichier suivi.

Mesure du 2026-09-06, avant fusion vers la branche par défaut d'un dépôt
PUBLIC : quatorze fichiers suivis portaient des montants issus du desk déclaré
de l'utilisateur — composition ligne par ligne, capital engagé, liquidités,
prix d'entrée d'un suivi. La chaîne était complète et banale :

1. `tools/qa/run_qa_instance.py` miroitait le dépôt en n'excluant que les
   SECRETS (`.env`, `.vertex_secret`), pas le PATRIMOINE. `desk_data.json`
   était donc copié et l'instance de vérification servait le portefeuille réel ;
2. les campagnes d'audit mesuraient sur cette instance et, faisant bien leur
   travail, recopiaient les valeurs observées dans les docstrings, les
   assertions et les documents — jusqu'à figer `assert r['equity'] == …`.

Un secret se remplace ; un patrimoine publié ne se reprend pas. Ce banc ferme
la boucle : il lit le desk local et refuse que ses chiffres se retrouvent dans
un fichier suivi par Git.

Il ne PUBLIE évidemment rien lui-même : il ne montre jamais une valeur du desk,
seulement le fichier et la ligne où elle a fuité.
"""
import json
import os
import re
import subprocess

import pytest

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: Les fichiers de données personnelles, tels que le produit les nomme.
_SOURCES = ('desk_data.json', 'position_inventory.json', 'tracking.json',
            'track_record.json')
#: Un montant assez « signant » pour valoir accusation. En dessous, un nombre
#: rond se retrouve partout par hasard (un profil, un seuil, une quantité).
_PLANCHER = 1000
#: Nombres ronds qui appartiennent au vocabulaire du produit, pas au desk.
_BANALS = {1000, 2000, 5000, 10000, 20000, 25000, 50000, 100000, 200000,
           500000, 1000000}


def _valeurs_du_desk() -> set[str]:
    """Les montants du desk local, sous les formes qu'un code pourrait écrire."""
    out: set[str] = set()
    for nom in _SOURCES:
        chemin = os.path.join(_RACINE, nom)
        if not os.path.isfile(chemin):
            continue
        try:
            with open(chemin, encoding='utf-8') as f:
                brut = json.load(f)
        except Exception:                              # noqa: BLE001
            continue
        pile = [brut]
        while pile:
            x = pile.pop()
            if isinstance(x, dict):
                pile.extend(x.values())
            elif isinstance(x, list):
                pile.extend(x)
            elif isinstance(x, str):
                #  Les caches du produit sérialisent parfois en chaîne.
                try:
                    pile.append(json.loads(x))
                except Exception:                      # noqa: BLE001
                    pass
            elif isinstance(x, (int, float)) and not isinstance(x, bool):
                v = float(x)
                if abs(v) < _PLANCHER or v in _BANALS:
                    continue
                out.add(('%d' % v) if float(v).is_integer() else ('%.2f' % v))
    return out


def _fichiers_suivis() -> list[str]:
    out = subprocess.run(['git', 'ls-files'], cwd=_RACINE,
                         capture_output=True, text=True, errors='replace')
    if out.returncode != 0:
        pytest.skip('dépôt Git indisponible : mesure impossible, jamais supposée')
    return [l for l in out.stdout.splitlines()
            if l.endswith(('.py', '.js', '.md', '.css', '.html', '.yml', '.txt'))]


def test_le_banc_a_de_quoi_mesurer():
    """Sans desk local, ce banc ne prouve rien : il doit le DIRE, pas passer."""
    if not any(os.path.isfile(os.path.join(_RACINE, n)) for n in _SOURCES):
        pytest.skip('aucun fichier de desk sur cette machine — rien à protéger ici')
    assert _fichiers_suivis(), 'aucun fichier suivi inspecté'


def test_aucun_montant_du_desk_local_n_est_dans_un_fichier_suivi():
    valeurs = _valeurs_du_desk()
    if not valeurs:
        pytest.skip('desk local vide ou sans montant significatif')
    #  Frontières de mot : « 7777 » ne doit pas s'accrocher à « 17777 ».
    #  L'exemple est neutre à dessein — un gardien qui cite un montant
    #  réel pour s'expliquer commet la faute qu'il surveille.
    motifs = {v: re.compile(r'(?<![\d.])' + re.escape(v) + r'(?![\d])') for v in valeurs}
    fuites = []
    for rel in _fichiers_suivis():
        chemin = os.path.join(_RACINE, rel)
        try:
            with open(chemin, encoding='utf-8', errors='replace') as f:
                lignes = f.readlines()
        except OSError:
            continue
        for i, ligne in enumerate(lignes, 1):
            for v, motif in motifs.items():
                if motif.search(ligne):
                    #  On ne répète PAS la valeur : ce message est lu dans des
                    #  journaux publics d'intégration continue.
                    fuites.append('%s:%d (montant du desk local, %d chiffres)'
                                  % (rel, i, len(v.replace('.', ''))))
    assert not fuites, (
        '%d montant(s) du desk RÉEL de cette machine apparaissent dans des '
        'fichiers suivis par Git. Le dépôt est public : un patrimoine publié '
        'ne se reprend pas. Remplacer par des valeurs synthétiques et rondes, '
        'et dire dans le docstring qu’elles le sont.\n  %s'
        % (len(fuites), '\n  '.join(fuites[:25])))


def test_le_miroir_de_verification_n_emporte_aucune_donnee_personnelle():
    """La source de la fuite : la copie n'excluait que les secrets."""
    import sys
    sys.path.insert(0, _RACINE)
    from tools.qa import run_qa_instance as qa

    for nom in _SOURCES:
        assert nom in qa.EXCLUS_FICHIERS, (
            '%s serait copié dans le miroir : l’instance de vérification '
            'servirait le portefeuille réel, et la prochaine campagne d’audit '
            'recopierait ses montants' % nom)
    #  Les sauvegardes datées portent le même patrimoine sous un autre nom.
    ignores = qa._ignorer('.', ['desk_data.json', 'desk_data_backup_2026-09-06.json',
                                'terminal.py', 'position_inventory_backup.json'])
    assert 'desk_data_backup_2026-09-06.json' in ignores, ignores
    assert 'position_inventory_backup.json' in ignores, ignores
    assert 'terminal.py' not in ignores, 'le miroir doit toujours copier le code'


# ── Le garde-fou de PUBLICATION d'une capture courtier ──────────────────────

def test_le_temoin_voit_une_ligne_de_detention_a_n_importe_quelle_profondeur():
    """`enregistrer()` promet de REFUSER d'écrire si une trace subsiste.

    Mesuré le 2026-09-06 : le témoin ne regardait qu'une clé `positions` de
    PREMIER NIVEAU, de type dict, avec trois sous-clés attendues. Une capture
    réelle produit `fixture.positions_brutes`, une LISTE de
    `{symbol, position, avgCost}` : sur cette forme, l'anonymiseur rendait les
    tickers, quantités et prix de revient intacts, le témoin rendait « rien à
    signaler », et le fichier était écrit.

    La promesse était plus large que le contrôle — la forme exacte du défaut
    que ce dépôt a payé ailleurs cette nuit.
    """
    from vertex.data_sources.ibkr_replay import contient_donnee_sensible

    capture = {'version_fixture': 1,
               'fixture': {'positions_brutes': [
                   {'symbol': 'NVDA', 'position': 250, 'avgCost': 118.42}]}}
    restes = contient_donnee_sensible(capture)
    assert restes, 'une liste de titres détenus passe encore pour publiable'
    assert 'positions_brutes' in restes[0]


def test_le_temoin_ne_confond_pas_une_COTATION_avec_une_DETENTION():
    """Contre-épreuve : sans elle, on refuserait toute donnée de marché.

    Une cotation porte un titre et des prix ; elle est publique et le rejeu ne
    fonctionne pas sans elle. Ce qui trahit une détention, c'est la grandeur
    qui n'a de sens que si on possède le titre — quantité, prix de revient,
    valeur de marché, plus-value.
    """
    from vertex.data_sources.ibkr_replay import contient_donnee_sensible

    assert contient_donnee_sensible(
        {'quotes': [{'symbol': 'NVDA', 'bid': 1.2, 'ask': 1.3, 'iv': 0.4}]}) == []
    assert contient_donnee_sensible({'fixture': {'positions_brutes': []}}) == []


def test_ecrire_une_capture_non_anonyme_est_REFUSE(tmp_path):
    """Le refus est le point : un artefact publié « en espérant » finit dans un
    dépôt public avec un portefeuille dedans."""
    import pytest as _pytest

    from vertex.data_sources import ibkr_replay

    releve = {'positions_brutes': [{'symbol': 'NVDA', 'position': 250,
                                    'avgCost': 118.42}]}
    cible = tmp_path / 'capture.json'
    with _pytest.raises(Exception):
        ibkr_replay.enregistrer(releve, cible)
    assert not cible.exists(), 'le fichier a été écrit malgré la trace'
