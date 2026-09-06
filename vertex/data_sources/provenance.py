"""vertex.data_sources.provenance — horodatage et fraîcheur des valeurs."""
from __future__ import annotations

import datetime as _dt

from .models import (
    ProvenancedValue, QUALITY_FRESH, QUALITY_RECENT, QUALITY_STALE,
    QUALITY_EXPIRED, QUALITY_MISSING, MODE_LIVE, MODE_DELAYED, MODE_EOD,
    SOURCE_UNAVAILABLE, utc_now_iso,
)

# Seuils de fraîcheur (secondes) par mode de source.
FRESHNESS_THRESHOLDS = {
    MODE_LIVE: {'fresh': 30, 'recent': 300, 'stale': 3600},
    MODE_DELAYED: {'fresh': 1200, 'recent': 3600, 'stale': 4 * 3600},
    MODE_EOD: {'fresh': 24 * 3600, 'recent': 3 * 24 * 3600, 'stale': 7 * 24 * 3600},
}
_DEFAULT_THRESHOLDS = FRESHNESS_THRESHOLDS[MODE_DELAYED]


def parse_iso(ts: str) -> _dt.datetime | None:
    if not ts:
        return None
    try:
        return _dt.datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        return None


def age_seconds(timestamp: str, now: _dt.datetime | None = None) -> float | None:
    dt = parse_iso(timestamp)
    if dt is None:
        return None
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return max(0.0, (now - dt).total_seconds())


def grade_quality(age: float | None, source_mode: str) -> str:
    if age is None:
        return QUALITY_MISSING
    th = FRESHNESS_THRESHOLDS.get(source_mode, _DEFAULT_THRESHOLDS)
    if age <= th['fresh']:
        return QUALITY_FRESH
    if age <= th['recent']:
        return QUALITY_RECENT
    if age <= th['stale']:
        return QUALITY_STALE
    return QUALITY_EXPIRED


def _iso(moment: _dt.datetime | None) -> str:
    """ISO 8601 UTC d'un instant donné, ou de maintenant."""
    if moment is None:
        return utc_now_iso()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_dt.timezone.utc)
    return moment.astimezone(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def stamp(value, source: str, source_mode: str, timestamp: str = '',
          fallback_used: bool = False, now: _dt.datetime | None = None) -> ProvenancedValue:
    """Construit une ProvenancedValue complète (âge + qualité calculés).

    ## Heure d'OBSERVATION contre heure de RÉCEPTION (mesuré le 6 sept. 2026)

    `models.ProvenancedValue` porte `observed_at` et `received_at` depuis le
    lot 5, et sa propre note dit pourquoi : « confondre [la latence] avec l'âge
    rend une donnée lente *fraîche* à tort ». La fonction qui remplit TOUTES les
    enveloppes du produit ne les remplissait ni l'une ni l'autre :

    ```text
    stamp(100.0, SECONDARY, DELAYED)      # aucun horodatage de source
      timestamp    2026-09-06T18:11:21Z   <- l'instant de RÉCEPTION
      age_seconds  0.49
      quality      FRESH
      observed_at  ''      received_at  ''      warnings  []
    ```

    Le principal appelant du produit est ce cas-là :
    `cotation_unifiee._fournisseur` appelle `stamp(...)` **sans horodatage** —
    les cotations de positions étaient donc toutes datées de leur arrivée et
    notées FRESH, la seule trace de l'inconnue étant deux champs vides que rien
    n'expliquait.

    Ce qui change, sans rien inventer : `received_at` est MESURÉ et toujours
    servi ; `observed_at` ne l'est **que** si la source a donné son heure — il
    reste vide sinon, parce qu'on ne la connaît pas ; et l'enveloppe le DIT
    (`horodatage de la source absent…`) au lieu de laisser un champ muet.
    `timestamp`, `age_seconds` et `quality` ne changent pas de sens : les
    consommateurs existants lisent la même chose qu'avant.
    """
    if value is None:
        return ProvenancedValue(source=source or SOURCE_UNAVAILABLE,
                                warnings=['valeur absente'],
                                received_at=_iso(now))
    horodatage_source = bool(timestamp)
    #  MÊME horloge que `received_at`. Sans horodatage de source, `timestamp`
    #  EST l'instant de réception : les servir depuis deux horloges différentes
    #  (`utc_now_iso()` d'un côté, `_iso(now)` de l'autre) fabriquait une
    #  enveloppe qui se contredit — mesuré sous `now=18:30:00Z` :
    #  `received_at=18:30:00Z` mais `timestamp=18:35:33Z`, soit une valeur
    #  reçue 5 min AVANT d'être datée, et un `age_seconds` rabattu à 0.0 par le
    #  `max(0.0, …)` d'`age_seconds`. Les deux sortent désormais du même
    #  instant ; sans `now`, `_iso(None)` vaut exactement `utc_now_iso()`.
    timestamp = timestamp or _iso(now)
    age = age_seconds(timestamp, now=now)
    pv = ProvenancedValue(
        value=value, source=source, source_mode=source_mode,
        timestamp=timestamp, age_seconds=age,
        quality=grade_quality(age, source_mode), fallback_used=fallback_used,
        #  Mesuré : l'instant où Vertex a reçu la valeur.
        received_at=_iso(now),
        #  Connu seulement si la source l'a dit. Vide = inconnu, jamais deviné.
        observed_at=timestamp if horodatage_source else '',
    )
    if not horodatage_source:
        pv.warnings.append(
            'horodatage de la source absent : âge mesuré depuis la réception, '
            'pas depuis l\'observation')
    if fallback_used:
        pv.warnings.append(f'fallback utilisé ({source}/{source_mode})')
    if pv.quality in (QUALITY_STALE, QUALITY_EXPIRED):
        pv.warnings.append(f'donnée {pv.quality.lower()} (âge {int(age or 0)}s)')
    return pv


def refresh_quality(pv: ProvenancedValue, now: _dt.datetime | None = None) -> ProvenancedValue:
    """Recalcule âge/qualité d'une valeur existante (les données vieillissent)."""
    pv.age_seconds = age_seconds(pv.timestamp, now=now)
    pv.quality = grade_quality(pv.age_seconds, pv.source_mode) if pv.value is not None else QUALITY_MISSING
    return pv
