"""
LOT 187 — Gardiens de la page DESIGN SYSTEM (/design-system, 254 l,
ZÉRO test dédié) + CORRECTIF d'honnêteté : la page de référence
affichait des hex PÉRIMÉS recopiés à la main (ex. --vx-black affiché
#020202, réel #060405 ; des tokens devenus alias var() montraient
l'ancienne valeur). Correctif : les hex sont désormais DÉRIVÉS de
tokens.css à l'import (alias résolus un niveau) — la double source a
disparu, la page LIT la vérité. SW v151 → v152 (changement visible).
"""
import re

import pytest

import terminal
from vertex.ui.pages import design_system_page as ds


def _html():
    return terminal.app.test_client().get('/design-system').get_data(as_text=True)


# ── Le correctif : la page de référence ne peut plus mentir ──────────────────

def test_chaque_hex_affiche_est_la_vraie_valeur_de_tokens_css():
    # Preuve rouge/vert du défaut corrigé : AVANT, 10+ étiquettes divergeaient
    # de tokens.css ; APRÈS, chaque hex affiché == la valeur réelle (alias
    # var() résolus). La page ne recopie plus rien — elle dérive.
    shown = re.findall(r'<code>(--vx-[a-z0-9-]+)</code>'
                       r'<span class="ds-hex">([^<]+)</span>', _html())
    assert len(shown) >= 30                         # anti-vide
    faux = [(v, h) for v, h in shown if ds._TOKENS.get(v, '').lower() != h.lower()]
    assert faux == []


def test_les_tokens_derives_couvrent_tous_les_groupes():
    # Chaque variable exposée par la page existe RÉELLEMENT dans tokens.css —
    # une variable renommée côté CSS fait échouer la référence, jamais un
    # silence.
    for group in (ds._BG, ds._COPPER, ds._SEM, ds._TEXT):
        for var in group:
            assert ds._TOKENS.get(var), var


def test_les_alias_var_sont_resolus_en_hex():
    # Un token alias (var(--x)) est montré avec la valeur FINALE, pas la
    # syntaxe var() — l'utilisateur lit une couleur, pas une indirection.
    affiches = dict(re.findall(r'<code>(--vx-[a-z0-9-]+)</code>'
                               r'<span class="ds-hex">([^<]+)</span>', _html()))
    assert not any(h.startswith('var(') for h in affiches.values())


# ── Invariants produit de la page (jamais gardés jusqu'ici) ──────────────────

def test_page_saine_ids_uniques_sans_litteraux_interdits():
    html = _html()
    ids = re.findall(r'id="([^"]+)"', html)
    assert [i for i in set(ids) if ids.count(i) > 1] == []   # aucun id dupliqué
    assert '#8f8a83' not in html.lower()             # littéral interdit (gardien)
    for verb in ('placeorder', 'submit_order', 'transmit('):
        assert verb not in html.lower()


def test_echantillons_copiables_et_etat_vide_honnete():
    html = _html()
    assert html.count('data-ds-copy') >= 20          # chaque échantillon copiable
    # L'état « données insuffisantes » de référence utilise le libellé produit.
    assert 'La source actuelle ne fournit pas les informations nécessaires' in html


def test_service_worker_bumpe_v152():
    body = terminal.app.test_client().get('/sw.js').get_data(as_text=True)
    assert 'td-shell-v300' in body                   # changement visible → bump
