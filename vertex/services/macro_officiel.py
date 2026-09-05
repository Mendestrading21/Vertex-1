"""vertex.services.macro_officiel — collecteur de fond des références macro officielles.

Circuit PUBLICATIONS (pas un flux de cotations) :
planification → API/CSV publics (FRED, BCE, BNS) → extraction → instantané
daté → cartes. Une collecte toutes les `VERTEX_MACRO_OFFICIEL_MIN` minutes
(défaut 360 : ces séries sont quotidiennes ou mensuelles, les interroger plus
souvent n'apporte rien et pèse sur les fournisseurs), reprise espacée après
échec (backoff borné), instantané persisté dans `macro_officiel_cache.json`
(racine, gitignoré comme les autres `*_cache.json`) pour survivre à un
redémarrage, battement `MACRO_OFFICIEL_REFRESH` dans le registre des jobs et
événement SSE `market` pour que les cartes ouvertes se rafraîchissent sans
rechargement.

Le réseau est concentré ici (`_fetch`) : timeouts bornés, User-Agent nommant
Vertex, réponse plafonnée en taille, aucune redirection vers un hôte interne
(les URLs sont celles du catalogue, jamais fournies par un contenu externe).
"""
from __future__ import annotations

import calendar
import json
import os
import random
import threading
import time
import urllib.request
from urllib.parse import urlparse

from vertex.data_sources import macro_officiel as _src

CACHE = 'macro_officiel_cache.json'
JOB = 'MACRO_OFFICIEL_REFRESH'
HOTES_AUTORISES = ('fred.stlouisfed.org', 'data-api.ecb.europa.eu', 'data.snb.ch')
TAILLE_MAX = 4_000_000     # octets : le cube BNS le plus lourd fait ~0,9 Mo
TIMEOUT_S = 25

_LOCK = threading.Lock()
_ETAT: dict = {'as_of': None, 'series': [], 'sources': _src.SOURCES,
               'derniere_erreur': None, 'echecs_consecutifs': 0, 'runs': 0,
               'cadence_min': None}


def _racine() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


CADENCE_DEFAUT_MIN = 360     # séries quotidiennes/mensuelles : 6 h de croisière


def cadence_min() -> int:
    brut = (os.environ.get('VERTEX_MACRO_OFFICIEL_MIN') or '').strip()
    return max(15, int(brut)) if brut.isdigit() else CADENCE_DEFAUT_MIN


def _fetch(url: str, accept: str) -> str:
    hote = urlparse(url).hostname or ''
    if hote not in HOTES_AUTORISES:
        raise PermissionError('hôte hors liste blanche : %s' % hote)
    req = urllib.request.Request(url, headers={
        'Accept': accept,
        'User-Agent': 'Vertex (analyse personnelle, lecture seule)'})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:       # noqa: S310 — hôte vérifié
        if (r.geturl() and (urlparse(r.geturl()).hostname or '') not in HOTES_AUTORISES):
            raise PermissionError('redirection hors liste blanche')
        brut = r.read(TAILLE_MAX + 1)
    if len(brut) > TAILLE_MAX:
        raise ValueError('réponse trop volumineuse (> %d octets)' % TAILLE_MAX)
    return brut.decode('utf-8', 'replace')


def charger_cache() -> None:
    """Réhydrate l'instantané persisté (les dates restent celles de la source)."""
    try:
        with open(os.path.join(_racine(), CACHE), encoding='utf-8') as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return
    with _LOCK:
        _ETAT['as_of'] = d.get('as_of')
        _ETAT['series'] = list(d.get('series') or [])
        _ETAT['restaure_depuis_cache'] = True


def _sauver() -> None:
    with _LOCK:
        d = {'as_of': _ETAT['as_of'], 'series': _ETAT['series']}
    chemin = os.path.join(_racine(), CACHE)
    tmp = chemin + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(d, fh, ensure_ascii=False)
    os.replace(tmp, chemin)


def collecter_une_fois(fetch=None) -> dict:
    """Une collecte complète ; idempotente (un instantané remplace le précédent).
    Une série en échec garde `value=None` et son `error` — les autres vivent."""
    debut = time.time()
    obs = _src.collecter(fetch or _fetch)
    series = [o.to_dict() for o in obs]
    erreurs = [o for o in obs if o.error]
    ok = len(erreurs) < len(obs)          # au moins une série a répondu
    with _LOCK:
        _ETAT['as_of'] = _src.utc_now_iso()
        _ETAT['series'] = series
        _ETAT['runs'] += 1
        _ETAT['restaure_depuis_cache'] = False
        _ETAT['derniere_erreur'] = ('%d/%d séries en échec : %s' % (
            len(erreurs), len(obs), '; '.join('%s (%s)' % (o.id, o.error) for o in erreurs[:3])
        )) if erreurs else None
        _ETAT['echecs_consecutifs'] = 0 if ok else _ETAT['echecs_consecutifs'] + 1
    try:
        _sauver()
    except OSError:
        pass
    _battre(ok, _ETAT['derniere_erreur'], (time.time() - debut) * 1000)
    _publier()
    return snapshot()


def _battre(ok: bool, erreur, duree_ms: float) -> None:
    try:
        from vertex.scheduler import registry as _sched
        #  Le nom est ECRIT : le registre mesure ses emetteurs a l'AST.
        _sched.beat('MACRO_OFFICIEL_REFRESH', ok=ok, error=erreur, duration_ms=duree_ms)
    except Exception:  # noqa: BLE001 — le registre est un témoin, pas une dépendance
        return


def _publier() -> None:
    try:
        from vertex.services.live_stream import BROKER
        BROKER.publish('market', {'macro_officiel': _ETAT['as_of']})
    except Exception:  # noqa: BLE001
        return


def snapshot() -> dict:
    """Instantané borné pour l'API : jamais de collecte réseau ici."""
    with _LOCK:
        series = list(_ETAT['series'])
        as_of = _ETAT['as_of']
        etat = {k: _ETAT.get(k) for k in ('derniere_erreur', 'echecs_consecutifs', 'runs',
                                          'restaure_depuis_cache')}
    age_s = None
    if as_of:
        try:
            age_s = max(0, int(time.time() - calendar.timegm(time.strptime(as_of, '%Y-%m-%dT%H:%M:%SZ'))))
        except ValueError:
            age_s = None
    return {'as_of': as_of, 'age_s': age_s, 'cadence_min': cadence_min(),
            'series': series, 'sources': _src.SOURCES,
            'disponibles': sum(1 for s in series if s.get('value') is not None),
            'total': len(_src.CATALOGUE), 'etat': etat, 'read_only': True}


def boucle() -> None:
    """Boucle de fond : collecte, dort `cadence_min`, recommence. Après un
    échec total, reprise espacée (5 min × 2^n, plafonnée à la cadence)."""
    charger_cache()
    while True:
        try:
            collecter_une_fois()
        except Exception as exc:  # noqa: BLE001 — la boucle ne meurt jamais en silence
            with _LOCK:
                _ETAT['derniere_erreur'] = 'collecte: %s' % exc
                _ETAT['echecs_consecutifs'] += 1
            _battre(False, str(exc), 0)
        with _LOCK:
            n = _ETAT['echecs_consecutifs']
        if n:
            attente = min(cadence_min() * 60, 300 * (2 ** min(n, 6)))
        else:
            attente = cadence_min() * 60
        time.sleep(attente + random.uniform(0, 30))


def demarrer() -> threading.Thread:
    t = threading.Thread(target=boucle, name='macro-officiel', daemon=True)
    t.start()
    return t


__all__ = ['JOB', 'CACHE', 'collecter_une_fois', 'snapshot', 'boucle', 'demarrer',
           'charger_cache', 'cadence_min']
