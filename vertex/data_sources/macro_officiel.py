"""vertex.data_sources.macro_officiel — références macro OFFICIELLES, sourcées et datées.

Trois fournisseurs publics, sans clé, mesurés joignables depuis cette machine
le 2026-09-06 (voir docs/VERTEX_SOURCE_REGISTRY.md) :

- **FRED** (Federal Reserve Bank of St. Louis) — CSV public `fredgraph.csv`
  (l'API JSON exige une clé `FRED_API_KEY` ; le CSV public n'en exige pas) ;
- **BCE** (ECB Data Portal, SDMX-JSON) ;
- **BNS** (data.snb.ch, cubes JSON).

Chaque série rend une observation DATÉE PAR LA SOURCE (`observed_at` = date de
l'observation publiée), distincte de l'heure de réception (`received_at`).
Aucune valeur n'est inventée : une série qui échoue rend `value=None` avec
`error`, jamais 0. Les fréquences (quotidien / mensuel / annuel) sont
déclarées par série : un chiffre mensuel de juillet n'est pas « en retard »,
il est mensuel.

Ce module ne parle pas au réseau tout seul : `collecter()` reçoit une fonction
`fetch(url, accept) -> str` injectable (tests avec fixtures réelles capturées
dans tests/fixtures/macro_officiel/). Le réseau vit dans
`vertex.services.macro_officiel` (boucle de fond, cache, battement).
"""
from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, asdict
from typing import Callable

FRED_CSV = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}'
BCE_SDMX = ('https://data-api.ecb.europa.eu/service/data/{flux}'
            '?lastNObservations=3&format=jsondata')
BNS_CUBE = 'https://data.snb.ch/api/cube/{cube}/data/json/en'


@dataclass(frozen=True)
class SerieOfficielle:
    """Une série du catalogue : identité, fournisseur, unité, fréquence."""
    id: str                  # identifiant Vertex (stable, affiché)
    fournisseur: str         # FRED | BCE | BNS
    reference: str           # identifiant chez le fournisseur (série, flux, cube)
    libelle: str             # français, court
    unite: str               # % · pt · CHF/USD…
    frequence: str           # quotidien | mensuel | annuel
    zone: str                # US · Zone euro · Suisse
    selection: str = ''      # BNS : libellé exact de la série dans le cube
    note: str = ''           # définition en une phrase


#: Catalogue. Les identifiants sont stables ; les libellés sont ceux affichés.
CATALOGUE: tuple[SerieOfficielle, ...] = (
    SerieOfficielle('us_fed_funds', 'FRED', 'DFF', 'Fed funds effectif', '%', 'quotidien', 'US',
                    note='Taux effectif des fonds fédéraux (moyenne pondérée des transactions).'),
    SerieOfficielle('us_2a', 'FRED', 'DGS2', 'Trésor US 2 ans', '%', 'quotidien', 'US',
                    note='Rendement à échéance constante 2 ans.'),
    SerieOfficielle('us_10a', 'FRED', 'DGS10', 'Trésor US 10 ans', '%', 'quotidien', 'US',
                    note='Rendement à échéance constante 10 ans.'),
    SerieOfficielle('us_10a_2a', 'FRED', 'T10Y2Y', 'Pente 10 ans − 2 ans', 'pt', 'quotidien', 'US',
                    note='Écart 10 ans − 2 ans publié par FRED (négatif = inversion).'),
    SerieOfficielle('ze_refi', 'BCE', 'FM/B.U2.EUR.4F.KR.MRR_FR.LEV', 'BCE — refinancement', '%',
                    'quotidien', 'Zone euro', note='Taux des opérations principales de refinancement.'),
    SerieOfficielle('ze_depot', 'BCE', 'FM/B.U2.EUR.4F.KR.DFR.LEV', 'BCE — facilité de dépôt', '%',
                    'quotidien', 'Zone euro', note='Taux de la facilité de dépôt.'),
    SerieOfficielle('ze_inflation', 'BCE', 'ICP/M.U2.N.000000.4.ANR', 'Inflation zone euro (IPCH)', '%',
                    'mensuel', 'Zone euro', note='Variation annuelle de l’indice des prix harmonisé.'),
    SerieOfficielle('eur_usd', 'BCE', 'EXR/D.USD.EUR.SP00.A', 'EUR/USD (référence BCE)', 'USD',
                    'quotidien', 'Zone euro', note='Cours de référence de la BCE, 1 EUR en USD.'),
    SerieOfficielle('eur_chf', 'BCE', 'EXR/D.CHF.EUR.SP00.A', 'EUR/CHF (référence BCE)', 'CHF',
                    'quotidien', 'Suisse', note='Cours de référence de la BCE, 1 EUR en CHF.'),
    SerieOfficielle('ch_saron', 'BNS', 'zimoma', 'SARON (1 jour)', '%', 'mensuel', 'Suisse',
                    selection='Switzerland - CHF - SARON - 1 day',
                    note='Moyenne mensuelle du taux SARON au jour le jour.'),
    SerieOfficielle('ch_conf_10a', 'BNS', 'rendoblim', 'Confédération 10 ans', '%', 'mensuel', 'Suisse',
                    selection='CHF Swiss Confederation bond issues - 10 years',
                    note='Rendement des emprunts de la Confédération à 10 ans (moyenne mensuelle).'),
)

SOURCES = {
    'FRED': {'nom': 'FRED — Federal Reserve Bank of St. Louis',
             'droits': 'usage personnel et affichage avec attribution (FRED Terms of Use)',
             'cle': 'aucune (CSV public)'},
    'BCE': {'nom': 'BCE — ECB Data Portal',
            'droits': 'réutilisation libre avec attribution',
            'cle': 'aucune'},
    'BNS': {'nom': 'BNS — data.snb.ch',
            'droits': 'réutilisation avec mention de la source',
            'cle': 'aucune'},
}


@dataclass
class Observation:
    """Une observation datée par la source, ou une absence expliquée."""
    id: str
    libelle: str
    fournisseur: str
    reference: str
    unite: str
    frequence: str
    zone: str
    value: float | None = None
    observed_at: str = ''        # date de l'observation chez la source (YYYY-MM-DD ou YYYY-MM)
    previous: float | None = None
    previous_at: str = ''
    received_at: str = ''        # ISO 8601 UTC, heure de réception ici
    url: str = ''
    note: str = ''
    error: str | None = None
    mode: str = 'PERIODIQUE'     # jamais « live » : ce sont des publications

    def to_dict(self) -> dict:
        return asdict(self)


def utc_now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def url_de(serie: SerieOfficielle) -> str:
    if serie.fournisseur == 'FRED':
        return FRED_CSV.format(serie=serie.reference)
    if serie.fournisseur == 'BCE':
        return BCE_SDMX.format(flux=serie.reference)
    return BNS_CUBE.format(cube=serie.reference)


# ── Parseurs (purs, testés sur fixtures réelles) ────────────────────────────

def _nombre(x) -> float | None:
    """FRED note une valeur manquante « . » ; la BNS peut rendre null."""
    if x is None:
        return None
    s = str(x).strip()
    if s in ('', '.', 'NA', 'null'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parser_fred(texte: str) -> list[tuple[str, float | None]]:
    """CSV `observation_date,<SERIE>` → [(date, valeur|None)] dans l'ordre du fichier."""
    lignes = list(csv.reader(io.StringIO(texte)))
    if not lignes or len(lignes[0]) < 2:
        raise ValueError('CSV FRED sans en-tête reconnaissable')
    out = []
    for row in lignes[1:]:
        if len(row) < 2:
            continue
        out.append((row[0].strip(), _nombre(row[1])))
    return out


def parser_bce(texte: str) -> list[tuple[str, float | None]]:
    """SDMX-JSON de la BCE → [(période, valeur)] ordonnés par période."""
    d = json.loads(texte)
    series = d['dataSets'][0]['series']
    if not series:
        return []
    cle = next(iter(series))
    obs = series[cle].get('observations', {})
    periodes = d['structure']['dimensions']['observation'][0]['values']
    out = []
    for i, v in obs.items():
        periode = periodes[int(i)]['id']
        out.append((periode, _nombre(v[0] if v else None)))
    out.sort(key=lambda t: t[0])
    return out


def parser_bns(texte: str, selection: str) -> list[tuple[str, float | None]]:
    """Cube JSON de la BNS → [(période, valeur)] de la série dont l'en-tête
    concaténé vaut `selection` (ex. « Switzerland - CHF - SARON - 1 day »)."""
    d = json.loads(texte)
    for ts in d.get('timeseries', []):
        entete = ' - '.join(str(h.get('dimItem', '')) for h in ts.get('header', []))
        if entete == selection:
            return [(str(v.get('date', '')), _nombre(v.get('value'))) for v in ts.get('values', [])]
    raise KeyError('série BNS absente du cube : %s' % selection)


def _derniere_observee(points: list[tuple[str, float | None]]):
    """Dernière observation NON manquante et la précédente non manquante."""
    valides = [(d, v) for d, v in points if v is not None]
    if not valides:
        return None, '', None, ''
    d1, v1 = valides[-1]
    d0, v0 = valides[-2] if len(valides) > 1 else ('', None)
    return v1, d1, v0, d0


# ── Collecte (réseau injecté) ───────────────────────────────────────────────

def observer(serie: SerieOfficielle, fetch: Callable[[str, str], str]) -> Observation:
    """Une série → une Observation. Toute erreur devient une donnée (`error`),
    jamais une exception qui casserait les autres séries, jamais un zéro."""
    url = url_de(serie)
    obs = Observation(id=serie.id, libelle=serie.libelle, fournisseur=serie.fournisseur,
                      reference=serie.reference, unite=serie.unite, frequence=serie.frequence,
                      zone=serie.zone, url=url, note=serie.note, received_at=utc_now_iso())
    try:
        if serie.fournisseur == 'FRED':
            points = parser_fred(fetch(url, 'text/csv'))
        elif serie.fournisseur == 'BCE':
            points = parser_bce(fetch(url, 'application/json'))
        else:
            points = parser_bns(fetch(url, 'application/json'), serie.selection)
        v1, d1, v0, d0 = _derniere_observee(points)
        if v1 is None:
            obs.error = 'aucune observation publiée dans la réponse'
            return obs
        obs.value, obs.observed_at, obs.previous, obs.previous_at = v1, d1, v0, d0
    except Exception as exc:  # noqa: BLE001 — la panne est une donnée
        obs.error = '%s: %s' % (type(exc).__name__, str(exc)[:160])
    return obs


def collecter(fetch: Callable[[str, str], str],
              catalogue: tuple[SerieOfficielle, ...] = CATALOGUE) -> list[Observation]:
    return [observer(s, fetch) for s in catalogue]


__all__ = ['SerieOfficielle', 'Observation', 'CATALOGUE', 'SOURCES', 'url_de',
           'parser_fred', 'parser_bce', 'parser_bns', 'observer', 'collecter',
           'utc_now_iso']
