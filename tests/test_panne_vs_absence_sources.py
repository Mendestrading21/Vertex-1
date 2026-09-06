# -*- coding: utf-8 -*-
"""tests/test_panne_vs_absence_sources.py — UNE PANNE N'EST PAS UNE ABSENCE.

## La mesure qui a fait naître ce banc (ROUGE avant le correctif)

`SourceRouter`, deux fournisseurs — l'un lève `TimeoutError`, l'autre rend
tranquillement `None` faute de donnée :

```text
avant : warnings = ['aucune source disponible',
                    'IBKR/LIVE: indisponible',          <- la source est TOMBÉE
                    'SECONDARY/DELAYED: indisponible']  <- elle a répondu « rien »
        pv.error   = None
        health()   = failures:1 des deux côtés, rien ne les sépare

après : warnings = ['aucune source disponible',
                    'IBKR/LIVE: panne (TimeoutError)',
                    'SECONDARY/DELAYED: aucune donnée']
        pv.error   = 'IBKR/LIVE: panne (TimeoutError) ; SECONDARY/DELAYED: aucune donnée'
        health()   = pannes:1/absences:0 et pannes:0/absences:1
```

Le mot unique « indisponible » couvrait donc aussi bien un courtier injoignable
qu'un titre sans cotation du jour — deux causes, deux gestes différents, et la
cause réellement mesurée (le type de l'exception) était jetée en route.

## Ce que ce banc garde

1. les deux situations ne produisent plus le même texte ;
2. la cause servie est celle qui a été MESURÉE (le type de l'exception), pas
   une supposition ;
3. le message de l'exception ne fuit jamais — un fournisseur peut y mettre une
   URL signée ou un jeton (garde historique de
   `tests/test_source_router_resilience.py`, conservée ici sur les deux
   nouveaux porteurs : `error` et `derniere_cause`) ;
4. `health()` compte les deux séparément.
"""
from __future__ import annotations

from vertex.data_sources import models as M
from vertex.data_sources.source_router import SourceRouter


def _routeur_deux_causes():
    """Un routeur dont la tête TOMBE et dont le repli n'a RIEN."""
    def tombe():
        raise TimeoutError('jeton-prive-a-ne-jamais-servir')

    def rien():
        return None

    r = SourceRouter()
    r.register(M.SOURCE_IBKR, M.MODE_LIVE, tombe)
    r.register(M.SOURCE_SECONDARY, M.MODE_DELAYED, rien)
    return r


def test_la_panne_et_l_absence_ne_portent_plus_le_meme_mot():
    """LE CŒUR. Avant : deux fois « indisponible ». Après : deux verdicts."""
    pv = _routeur_deux_causes().fetch()
    tete = next(w for w in pv.warnings if w.startswith('IBKR/LIVE'))
    repli = next(w for w in pv.warnings if w.startswith('SECONDARY/DELAYED'))
    assert tete != repli, (
        'la source tombée et la source sans donnée portent le même verdict : %r' % tete)
    assert 'panne' in tete, tete
    assert 'aucune donnée' in repli, repli


def test_la_cause_servie_est_le_type_mesure_de_l_exception():
    """« Mesurée, jamais supposée » : c'est `TimeoutError` qui a été levée."""
    r = _routeur_deux_causes()
    pv = r.fetch()
    assert 'TimeoutError' in (pv.error or ''), pv.error
    tete = r.health()['providers'][0]
    assert tete['derniere_cause'] == 'TimeoutError', tete
    repli = r.health()['providers'][1]
    assert repli['derniere_cause'] == 'aucune_donnee', repli


def test_l_enveloppe_porte_la_panne_au_lieu_de_la_taire():
    """`ProvenancedValue.error` existe pour ça — il restait vide (None)."""
    pv = _routeur_deux_causes().fetch()
    assert pv.value is None and pv.quality == M.QUALITY_MISSING
    assert pv.error, 'la panne doit être une donnée portée par l\'enveloppe'
    assert 'panne' in pv.error and 'aucune donnée' in pv.error


def test_le_message_du_fournisseur_ne_fuit_nulle_part():
    """Le TYPE nomme la cause ; le MESSAGE peut contenir un jeton ou une URL."""
    r = _routeur_deux_causes()
    pv = r.fetch()
    surfaces = [str(pv.warnings), str(pv.error), str(r.health())]
    for surface in surfaces:
        assert 'jeton-prive-a-ne-jamais-servir' not in surface, surface


def test_health_compte_separement_les_pannes_et_les_absences():
    """Un fournisseur tombé et un fournisseur vide n'ont pas la même santé."""
    r = _routeur_deux_causes()
    r.fetch()
    tete, repli = r.health()['providers'][0], r.health()['providers'][1]
    assert (tete['pannes'], tete['absences']) == (1, 0), tete
    assert (repli['pannes'], repli['absences']) == (0, 1), repli


def test_un_succes_efface_la_cause_precedente():
    """Une cause qui survit à la guérison deviendrait un mensonge d'archive."""
    etats = {'ok': False}

    def parfois():
        if not etats['ok']:
            raise ConnectionError('socket fermée')
        from vertex.data_sources.models import ProvenancedValue
        return ProvenancedValue(value=42)

    r = SourceRouter()
    r.register(M.SOURCE_IBKR, M.MODE_LIVE, parfois)
    r.fetch()
    assert r.health()['providers'][0]['derniere_cause'] == 'ConnectionError'
    etats['ok'] = True
    assert r.fetch().value == 42
    assert r.health()['providers'][0]['derniere_cause'] is None
