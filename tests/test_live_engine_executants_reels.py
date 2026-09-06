# -*- coding: utf-8 -*-
"""tests/test_live_engine_executants_reels.py — LE RAPPORT DE SYNC NE PROMET
QUE CE QU'UN EXÉCUTANT PEUT TENIR.

## La mesure qui a fait naître ce banc (ROUGE avant le correctif)

`live_engine.refresh()` sur un processus SANS boucle câblée
(`configure(rescan_event=None)`, aucune boucle n'ayant appelé `wait_force`) :

```text
kicked = False                      <- RIEN n'a été déclenché
prices   → « relancé — recalcul complet en cours (≈10-30 s) »
weekly   → « relancé — recalcul complet en cours (≈10-30 s) »
ai       → « relancé — recalcul complet en cours (≈10-30 s) »
news     → « cycle forcé — nouvelles fraîches sous ≈60 s »
calendar → « cycle forcé — la boucle earnings se réveille immédiatement »
```

Cinq actions annoncées, zéro exécutant. Poser un `threading.Event` réussit
toujours — y compris quand personne ne l'attend : « forcé » décrivait le geste
du Sync Center, pas le sort de la demande. C'est l'invariant 6 : une capacité
sans exécuteur réel se NOMME, elle ne se déguise pas en automatisation en
attente.

## La preuve est une mesure, pas une supposition

Un exécutant se manifeste par `wait_force(domaine, timeout)` — le seul endroit
du produit où une boucle dit « j'attends ce forçage ». `boucle_a_l_ecoute` lit
ce signal et le fait périmer à l'échéance annoncée : une boucle morte cesse
d'être comptée, un domaine sans boucle ne l'a jamais été.
"""
from __future__ import annotations

import threading
import time

import pytest

from vertex.services import live_engine as LE


@pytest.fixture(autouse=True)
def _isole():
    """Chaque test repart d'un moteur vierge : le signal d'écoute est global."""
    ecoutes = dict(LE._ECOUTES)
    cfg = dict(LE._CFG)
    LE._ECOUTES.clear()
    for ev in LE._FORCE.values():
        ev.clear()
    yield
    LE._ECOUTES.clear()
    LE._ECOUTES.update(ecoutes)
    LE._CFG.update(cfg)


def _cabler(rescan_event=None, demo=False):
    LE.configure(scan_state={'scan_ts': time.time(), 'rows': []},
                 news_state={}, cal_state={}, weekly_state={},
                 rescan_event=rescan_event, demo=demo, ibkr_enabled=False)


def _actions(sortie):
    return {l['domain']: l for l in sortie['report']['lines']}


def test_sans_boucle_de_scan_le_rapport_ne_promet_aucun_recalcul():
    """LE CŒUR (prix/ia/hebdo). Avant : « recalcul complet en cours » pour un
    processus où `rescan_event` est None et où `kicked` reste False."""
    _cabler(rescan_event=None)
    sortie = LE.refresh(['prices', 'ai', 'weekly'])
    assert sortie['kicked'] is False, 'la mesure de départ n\'est plus la bonne'
    for domaine, ligne in _actions(sortie).items():
        assert ligne['executant'] == 'aucun_executant_observe', (domaine, ligne)
        assert 'NON_IMPLÉMENTÉ' in ligne['action'], (domaine, ligne['action'])
        assert 'en cours' not in ligne['action'], (
            '%s promet un recalcul que rien n\'exécute : %r' % (domaine, ligne['action']))


def test_avec_la_boucle_de_scan_cablee_le_rapport_annonce_le_recalcul():
    """L'AUTRE SENS : un gardien qui interdirait toujours la promesse serait
    aussi faux, dans l'autre direction."""
    _cabler(rescan_event=threading.Event())
    sortie = LE.refresh(['prices'])
    ligne = _actions(sortie)['prices']
    assert sortie['kicked'] is True
    assert ligne['executant'] == 'evenement_de_scan'
    assert 'relancé' in ligne['action'] and 'NON_IMPLÉMENTÉ' not in ligne['action']


def test_sans_boucle_news_le_forcage_est_pose_mais_n_est_pas_annonce_comme_tenu():
    """Poser l'événement est un fait ; qu'il soit consommé n'en est pas un."""
    _cabler(rescan_event=None)
    sortie = LE.refresh(['news', 'calendar'])
    lignes = _actions(sortie)
    for domaine in ('news', 'calendar'):
        ligne = lignes[domaine]
        assert ligne['executant'] == 'aucun_executant_observe', (domaine, ligne)
        assert 'aucune boucle' in ligne['action'], (domaine, ligne['action'])
        #  Le signal EST posé : le rapport ne doit pas non plus nier ce fait.
        assert LE.force_event(domaine).is_set(), domaine


def test_une_boucle_qui_attend_vraiment_retablit_la_promesse():
    """`wait_force` est la seule preuve d'exécutant. Une boucle qui l'appelle
    fait repasser la ligne à « cycle forcé »."""
    _cabler(rescan_event=None)
    fil = threading.Thread(target=lambda: LE.wait_force('news', 30), daemon=True)
    fil.start()
    for _ in range(200):                     # laisse le fil atteindre l'attente
        if LE.boucle_a_l_ecoute('news'):
            break
        time.sleep(0.01)
    assert LE.boucle_a_l_ecoute('news'), 'le signal d\'écoute n\'a pas été noté'
    ligne = _actions(LE.refresh(['news']))['news']
    assert ligne['executant'] == 'boucle_a_l_ecoute'
    assert 'cycle forcé' in ligne['action']
    fil.join(timeout=5)


def test_le_signal_d_ecoute_perime_quand_la_boucle_meurt():
    """Un signal éternel referait le défaut : une boucle morte redeviendrait
    « à l'écoute » pour toujours. Le signal vaut l'échéance annoncée + marge."""
    LE._ECOUTES['news'] = (time.time() - (5 + LE._ECOUTE_MARGE_S + 1), 5)
    assert LE.boucle_a_l_ecoute('news') is False
    LE._ECOUTES['news'] = (time.time(), 5)
    assert LE.boucle_a_l_ecoute('news') is True


def test_le_mode_demo_reste_nomme_pour_ce_qu_il_est():
    """En démo, aucun réseau : la ligne ne doit ni promettre ni accuser une
    boucle absente — elle nomme la démo."""
    _cabler(rescan_event=threading.Event(), demo=True)
    ligne = _actions(LE.refresh(['news']))['news']
    assert ligne['executant'] == 'demo'
    assert 'démo' in ligne['action']
