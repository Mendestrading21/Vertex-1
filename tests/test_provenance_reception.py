# -*- coding: utf-8 -*-
"""tests/test_provenance_reception.py — OBSERVÉ QUAND, REÇU QUAND : DEUX CHAMPS,
DEUX FAITS.

## La mesure qui a fait naître ce banc (ROUGE avant le correctif)

`models.ProvenancedValue` porte `observed_at` et `received_at` depuis le lot 5,
et sa propre note dit pourquoi : « l'écart entre les deux est la latence, et la
confondre avec l'âge rend une donnée lente *fraîche* à tort ». La fonction qui
remplit TOUTES les enveloppes du produit ne remplissait ni l'un ni l'autre :

```text
stamp(100.0, SECONDARY, DELAYED)      # le cas réel : aucun horodatage de source
  timestamp    2026-09-06T18:11:21Z   <- l'instant de RÉCEPTION, servi comme date
  age_seconds  0.49
  quality      FRESH
  observed_at  ''      received_at  ''      warnings  []
```

Ce n'est pas un cas de laboratoire : `cotation_unifiee._fournisseur` — le
chemin des cotations de positions — appelle `stamp(...)` **sans horodatage**.
Chaque cotation était donc datée de son arrivée, notée FRESH, et la seule trace
de l'inconnue était deux champs vides que rien n'expliquait.

## Ce que ce banc garde

1. `received_at` est servi et MESURÉ (il l'est toujours : c'est notre horloge) ;
2. `observed_at` n'est servi QUE si la source a donné son heure — vide sinon,
   jamais recopié depuis la réception, ce qui ferait croire à une observation
   qu'on n'a pas ;
3. l'enveloppe DIT que l'âge est compté depuis la réception quand la source
   s'est tue ;
4. `timestamp`, `age_seconds` et `quality` gardent exactement leur sens
   d'avant : le correctif ajoute, il ne réécrit pas.
"""
from __future__ import annotations

import datetime as _dt

from vertex.data_sources import models as M
from vertex.data_sources import provenance as P

NOW = _dt.datetime(2026, 9, 6, 18, 30, 0, tzinfo=_dt.timezone.utc)


def test_sans_horodatage_de_source_l_observation_reste_inconnue():
    """LE CŒUR. `observed_at` vide = on ne sait pas. Le remplir avec l'heure de
    réception serait l'invention exacte que le modèle interdit."""
    pv = P.stamp(100.0, M.SOURCE_SECONDARY, M.MODE_DELAYED, now=NOW)
    assert pv.observed_at == '', (
        'l\'heure d\'observation a été inventée : %r' % pv.observed_at)
    assert pv.received_at == '2026-09-06T18:30:00Z', pv.received_at


def test_sans_horodatage_de_source_l_enveloppe_le_dit():
    """Un champ vide ne se lit pas. L'aveu, lui, se lit."""
    pv = P.stamp(100.0, M.SOURCE_SECONDARY, M.MODE_DELAYED, now=NOW)
    assert any('horodatage de la source absent' in w for w in pv.warnings), pv.warnings
    assert any('réception' in w for w in pv.warnings), pv.warnings


def test_avec_horodatage_de_source_les_deux_instants_sont_distincts():
    """Le cas où la source parle : l'observation est la sienne, la réception la
    nôtre, et l'écart entre les deux est lisible — c'est la latence."""
    pv = P.stamp(100.0, M.SOURCE_IBKR, M.MODE_LIVE,
                 timestamp='2026-09-06T18:29:00Z', now=NOW)
    assert pv.observed_at == '2026-09-06T18:29:00Z'
    assert pv.received_at == '2026-09-06T18:30:00Z'
    assert pv.observed_at != pv.received_at
    #  Aucun aveu d'horodatage manquant : la source a parlé.
    assert not any('horodatage de la source absent' in w for w in pv.warnings), pv.warnings


def test_l_age_et_la_qualite_gardent_leur_sens():
    """L'AUTRE SENS : le correctif ajoute des faits, il n'en change aucun.
    Une cotation IBKR live de 60 s reste RECENT, pas FRESH ni MISSING."""
    pv = P.stamp(100.0, M.SOURCE_IBKR, M.MODE_LIVE,
                 timestamp='2026-09-06T18:29:00Z', now=NOW)
    assert pv.age_seconds == 60.0
    assert pv.quality == M.QUALITY_RECENT
    assert pv.timestamp == '2026-09-06T18:29:00Z'
    assert pv.value == 100.0 and pv.source == M.SOURCE_IBKR


def test_une_valeur_absente_porte_quand_meme_son_heure_de_reception():
    """Une absence est datée : « on n'a rien reçu » est un fait, à un instant."""
    pv = P.stamp(None, M.SOURCE_IBKR, M.MODE_LIVE, now=NOW)
    assert pv.value is None and pv.quality == M.QUALITY_MISSING
    assert pv.received_at == '2026-09-06T18:30:00Z'
    assert pv.observed_at == ''


def test_le_chemin_reel_des_cotations_porte_desormais_la_reception():
    """Le vrai appelant : `cotation_unifiee` stampe SANS horodatage de source.
    C'est ce chemin — les cotations de positions — que la mesure a trouvé muet.
    """
    from vertex.data_sources import cotation_unifiee as CU
    pv = CU.resoudre_cotation(broker={'spot': 101.5}, secondaire=None,
                              symbole='nvda', devise='USD')
    assert pv.value is not None
    assert pv.received_at, 'la cotation servie ne dit pas quand elle a été reçue'
    assert pv.observed_at == '', (
        'IBKR n\'a pas donné d\'heure ici : l\'observation ne doit pas être inventée')
    assert any('horodatage de la source absent' in w for w in pv.warnings), pv.warnings
def test_l_heure_de_reception_et_l_horodatage_servi_sortent_de_la_meme_horloge():
    """CONTRÔLE ADVERSE. Sans horodatage de source, `timestamp` EST l'heure de
    réception — les deux champs décrivent alors le MÊME instant et ne peuvent
    pas se contredire.

    Mesuré avant ce contrôle (`timestamp = timestamp or utc_now_iso()` pendant
    que `received_at = _iso(now)`), sous `now = 18:30:00Z` :

    ```text
    received_at  2026-09-06T18:30:00Z
    timestamp    2026-09-06T18:35:33Z    <- horloge réelle, 5 min PLUS TARD
    age_seconds  0.0                     <- rabattu par max(0.0, …)
    ```

    L'enveloppe affirmait donc avoir été reçue cinq minutes avant d'être datée,
    et son âge n'était plus mesuré mais rabattu. Après : les deux champs valent
    `18:30:00Z` et `age_seconds` vaut 0.0 parce qu'il est nul, pas parce qu'il
    a été borné.
    """
    pv = P.stamp(100.0, M.SOURCE_SECONDARY, M.MODE_DELAYED, now=NOW)
    assert pv.timestamp == pv.received_at, (
        "sans horodatage de source, la date servie et l'heure de réception "
        'sont le même instant : %r vs %r' % (pv.timestamp, pv.received_at))
    assert pv.timestamp == '2026-09-06T18:30:00Z', pv.timestamp
    assert pv.age_seconds == 0.0, pv.age_seconds
    #  L'AUTRE SENS : quand la source donne son heure, les deux DIVERGENT —
    #  cet écart est la latence, et l'aplatir reperdrait l'information.
    avec = P.stamp(100.0, M.SOURCE_SECONDARY, M.MODE_DELAYED,
                   timestamp='2026-09-06T18:29:00Z', now=NOW)
    assert avec.timestamp != avec.received_at and avec.age_seconds == 60.0
