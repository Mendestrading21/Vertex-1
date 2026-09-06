"""vertex.data_sources.source_router — priorité des sources, sans mélange silencieux.

Priorité (§12) :
  1. IBKR live
  2. IBKR delayed / frozen — clairement indiqué
  3. fournisseur secondaire validé
  4. fallback EOD
  5. indisponible (honnête : None, jamais un chiffre inventé)

## Une PANNE n'est pas une ABSENCE (mesuré le 6 sept. 2026)

Le routeur écrivait le MÊME mot dans les deux cas. Deux fournisseurs, l'un qui
lève `TimeoutError('lecture IBKR expirée après 4s')`, l'autre qui rend
tranquillement `None` faute de donnée :

```text
avant : ['aucune source disponible',
         'IBKR/LIVE: indisponible',            <- la source est TOMBÉE
         'SECONDARY/DELAYED: indisponible']    <- la source a RÉPONDU « rien »
        pv.error = None
        health() : failures=1 pour les deux, rien ne les distingue
```

« Indisponible » décrivait donc aussi bien un serveur injoignable qu'un titre
sans cotation ce jour-là — et la cause mesurée (le type de l'exception) était
jetée. Le geste à faire n'est pourtant pas le même : relancer TWS, ou accepter
qu'il n'y ait rien à afficher.

Ce que le routeur sert désormais : `panne (TypeErreur)` contre `aucune donnée`,
le compte séparé des deux dans `health()`, et la cause portée par l'enveloppe
(`ProvenancedValue.error`, le champ prévu pour ça — « la panne est une donnée »).

**Le TYPE de l'exception, jamais son message** : un message de fournisseur peut
contenir une URL signée ou un jeton (`tests/test_source_router_resilience.py`
le garde depuis toujours). `TimeoutError` suffit à nommer la cause sans rien
divulguer.
"""
from __future__ import annotations

import time
from typing import Callable

from .models import (
    ProvenancedValue, SOURCE_IBKR, SOURCE_SECONDARY, SOURCE_FALLBACK_EOD,
    MODE_LIVE, MODE_DELAYED, MODE_FROZEN, MODE_EOD, missing,
)
from . import provenance

# (source, mode) ordonnés par préférence décroissante.
PRIORITY: tuple[tuple[str, str], ...] = (
    (SOURCE_IBKR, MODE_LIVE),
    (SOURCE_IBKR, MODE_DELAYED),
    (SOURCE_IBKR, MODE_FROZEN),
    (SOURCE_SECONDARY, MODE_DELAYED),
    (SOURCE_SECONDARY, MODE_EOD),
    (SOURCE_FALLBACK_EOD, MODE_EOD),
)


def rank(source: str, mode: str) -> int:
    try:
        return PRIORITY.index((source, mode))
    except ValueError:
        return len(PRIORITY)


class SourceRouter:
    """Route une demande vers la meilleure source disponible.

    Les providers sont des callables ``() -> ProvenancedValue | None`` déclarés
    avec leur (source, mode). Le routeur essaie dans l'ordre de priorité et
    marque ``fallback_used`` dès qu'on n'est plus sur la source de tête.
    """

    def __init__(self, failure_threshold: int = 2, cooldown_seconds: float = 30.0,
                 slow_provider_ms: float = 2500.0, clock: Callable[[], float] | None = None) -> None:
        self._providers: list[tuple[int, str, str, Callable[[], ProvenancedValue | None]]] = []
        self._failure_threshold = max(1, int(failure_threshold))
        self._cooldown_seconds = max(1.0, float(cooldown_seconds))
        self._slow_provider_ms = max(1.0, float(slow_provider_ms))
        self._clock = clock or time.monotonic
        self._state: dict[tuple[str, str], dict] = {}

    def register(self, source: str, mode: str,
                 provider: Callable[[], ProvenancedValue | None]) -> None:
        self._providers.append((rank(source, mode), source, mode, provider))
        self._providers.sort(key=lambda item: item[0])
        self._state.setdefault((source, mode), {
            'failures': 0, 'open_until': 0.0, 'last_latency_ms': None,
            'slow_calls': 0, 'calls': 0,
            #  `failures` compte les deux ; ces deux-là les SÉPARENT. Sans eux,
            #  un fournisseur tombé et un fournisseur sans donnée présentent le
            #  même bilan de santé.
            'pannes': 0, 'absences': 0, 'derniere_cause': None,
        })

    def health(self) -> dict:
        """État agrégé des fournisseurs, sans URL, message d'erreur ni donnée de marché.

        `derniere_cause` porte le TYPE de la dernière défaillance
        (`'TimeoutError'`, ou `'aucune_donnee'` quand la source a répondu sans
        rien avoir) — jamais le message de l'exception, qui peut contenir une
        URL signée ou un jeton.
        """
        now = self._clock()
        providers = []
        for _, source, mode, _ in self._providers:
            state = self._state[(source, mode)]
            open_for = max(0.0, state['open_until'] - now)
            providers.append({
                'source': source, 'mode': mode,
                'status': 'OPEN' if open_for else 'CLOSED',
                'failures': state['failures'],
                'open_for_seconds': round(open_for, 3),
                'calls': state['calls'],
                'last_latency_ms': state['last_latency_ms'],
                'slow_calls': state['slow_calls'],
                'pannes': state['pannes'],
                'absences': state['absences'],
                'derniere_cause': state['derniere_cause'],
            })
        return {'read_only': True, 'failure_threshold': self._failure_threshold,
                'cooldown_seconds': self._cooldown_seconds, 'providers': providers}

    def _defaillance(self, state: dict, cause: str) -> None:
        """Compte une défaillance et arme le disjoncteur. `cause` est un TYPE."""
        state['failures'] += 1
        state['derniere_cause'] = cause
        if state['failures'] >= self._failure_threshold:
            state['open_until'] = self._clock() + self._cooldown_seconds

    def fetch(self) -> ProvenancedValue:
        errors: list[str] = []
        for idx, (_, source, mode, provider) in enumerate(self._providers):
            state = self._state[(source, mode)]
            now = self._clock()
            if state['open_until'] > now:
                errors.append(f'{source}/{mode}: circuit_ouvert')
                continue
            started = self._clock()
            try:
                pv = provider()
            except Exception as exc:  # une source qui casse ne casse pas l'app
                #  PANNE : la source n'a pas répondu. La cause SERVIE est le
                #  type mesuré de l'exception — jamais son message (jeton, URL
                #  signée), jamais une supposition.
                state['calls'] += 1
                self._defaillance(state, type(exc).__name__)
                state['pannes'] += 1
                errors.append(f'{source}/{mode}: panne ({type(exc).__name__})')
                continue
            elapsed_ms = (self._clock() - started) * 1000
            state['calls'] += 1
            state['last_latency_ms'] = round(max(0.0, elapsed_ms), 3)
            if pv is None or pv.value is None:
                #  ABSENCE : la source a répondu, elle n'avait rien. Un titre
                #  sans cotation du jour n'est pas un fournisseur en panne, et
                #  le geste à faire n'est pas le même.
                self._defaillance(state, 'aucune_donnee')
                state['absences'] += 1
                errors.append(f'{source}/{mode}: aucune donnée')
                continue
            state['failures'] = 0
            state['open_until'] = 0.0
            state['derniere_cause'] = None
            pv.source, pv.source_mode = source, mode
            pv.fallback_used = idx > 0
            if elapsed_ms > self._slow_provider_ms:
                state['slow_calls'] += 1
                pv.warnings.append(f'latence_source_elevee {source}/{mode}')
            if idx > 0:
                pv.warnings.append(
                    f'source de repli {source}/{mode} (sources devant indisponibles)')
            provenance.refresh_quality(pv)
            return pv
        pv = missing('aucune source disponible')
        pv.warnings.extend(errors)
        #  `ProvenancedValue.error` existe pour ça — « la panne est une donnée,
        #  portée par la valeur et non levée » (models.py). Il restait vide,
        #  donc l'appelant ne pouvait pas distinguer « rien à afficher » de
        #  « les sources sont tombées » sans relire des chaînes.
        pv.error = ' ; '.join(errors) or 'aucun fournisseur enregistré'
        return pv
