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
`error`, jamais 0. Les fréquences (quotidien / mensuel / annuel / en vigueur)
sont déclarées par série : un chiffre mensuel de juillet n'est pas « en
retard », il est mensuel — et un taux directeur du 17 juin est EN VIGUEUR, pas
vieux de 81 jours. La PONCTUALITÉ est jugée ici (`juger_fraicheur` /
`juger_series`, champs `fraicheur` et `age_jours`) : elle est distincte de la
disponibilité, le retard d'un fournisseur est dit et jamais deviné à l'écran,
et le verdict est recalculé À CHAQUE LECTURE — jamais figé dans l'observation
ni persisté dans le cache, sinon il vieillit en silence.

Ce module ne parle pas au réseau tout seul : `collecter()` reçoit une fonction
`fetch(url, accept) -> str` injectable (tests avec fixtures réelles capturées
dans tests/fixtures/macro_officiel/). Le réseau vit dans
`vertex.services.macro_officiel` (boucle de fond, cache, battement).
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import time
from dataclasses import dataclass, asdict
from typing import Callable

FRED_CSV = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}'
BCE_SDMX = ('https://data-api.ecb.europa.eu/service/data/{flux}'
            '?lastNObservations=3&format=jsondata')
BNS_CUBE = 'https://data.snb.ch/api/cube/{cube}/data/json/en'


#: Une série de TAUX DIRECTEUR n'est pas périodique : elle ne bouge qu'au
#: changement de taux, et la dernière valeur reste EN VIGUEUR jusqu'au suivant.
#: Mesure du 2026-09-06 sur `FM/B.U2.EUR.4F.KR.MRR_FR.LEV` (3 dernières
#: observations) : 2025-04-23 → 2,40 ; 2025-06-11 → 2,15 ; 2026-06-17 → 2,40.
#: C'est un escalier de décisions, pas une série quotidienne : étiqueter ces
#: deux séries « quotidien » faisait passer une valeur JUSTE et COURANTE pour
#: une donnée vieille de 81 jours. La chaîne est écrite en clair (avec un
#: espace) parce qu'elle est affichée telle quelle quand la table de libellés
#: de la carte ne la connaît pas.
FREQ_EN_VIGUEUR = 'en vigueur'


@dataclass(frozen=True)
class SerieOfficielle:
    """Une série du catalogue : identité, fournisseur, unité, fréquence."""
    id: str                  # identifiant Vertex (stable, affiché)
    fournisseur: str         # FRED | BCE | BNS
    reference: str           # identifiant chez le fournisseur (série, flux, cube)
    libelle: str             # français, court
    unite: str               # % · pt · CHF/USD…
    frequence: str           # quotidien | mensuel | annuel | en vigueur
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
                    FREQ_EN_VIGUEUR, 'Zone euro',
                    note='Taux des opérations principales de refinancement, en vigueur jusqu’au prochain changement.'),
    SerieOfficielle('ze_depot', 'BCE', 'FM/B.U2.EUR.4F.KR.DFR.LEV', 'BCE — facilité de dépôt', '%',
                    FREQ_EN_VIGUEUR, 'Zone euro',
                    note='Taux de la facilité de dépôt, en vigueur jusqu’au prochain changement.'),
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
    #  PAS de verdict de fraîcheur ici : une observation enregistre ce que la
    #  SOURCE a publié, pas ce qu'on en pensait à l'instant de la collecte.
    #  Le verdict est une fonction de l'heure de LECTURE — il est calculé à la
    #  sortie par `juger_series`, jamais figé ni persisté (voir sa docstring).

    def to_dict(self) -> dict:
        return asdict(self)


#: Tolérance avant de parler de RETARD, par fréquence, en jours.
#: `quotidien` : 5 j couvrent un week-end prolongé (FRED ne publie pas les
#: jours fériés) ; `mensuel` : 45 j couvrent le délai de publication d'un mois
#: clos ; `annuel` : 400 j. Au-delà de trois fois la tolérance, c'est un
#: RETARD_FORT — ce n'est plus un décalage de publication.
TOLERANCE_J: dict[str, int] = {'quotidien': 5, 'mensuel': 45, 'annuel': 400}


def _fin_de_periode(observed_at: str) -> _dt.date | None:
    """Dernier jour COUVERT par l'observation ('2025-12' → 2025-12-31).

    Un chiffre mensuel de décembre n'a pas 279 jours de retard le 6 septembre
    parce qu'il porte le 1er décembre : il couvre le mois entier. Compter
    depuis la fin de la période évite de fabriquer un mois de retard qui
    n'existe pas."""
    import calendar as _cal
    s = str(observed_at or '').strip()
    try:
        if len(s) == 7:
            an, mois = int(s[:4]), int(s[5:7])
            return _dt.date(an, mois, _cal.monthrange(an, mois)[1])
        if len(s) == 4:
            return _dt.date(int(s), 12, 31)
        return _dt.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def juger_fraicheur(frequence: str, observed_at: str,
                    aujourdhui: _dt.date | None = None) -> tuple[str, int | None]:
    """(verdict, ÂGE en jours) — la PONCTUALITÉ d'une observation, calculée.

    Le second membre est un ÂGE, pas un retard. Le nom `retard_jours` qu'il
    portait était un piège de lecture mesuré : il valait 81 sur `ze_refi`, dont
    le verdict est `SANS_OBJET` parce que ce taux directeur est EN VIGUEUR — le
    premier écran qui aurait lu le champ sans lire `fraicheur` aurait affiché
    « 81 jours de retard » sur une valeur courante, exactement le mensonge que
    ce module existe pour empêcher. Le champ servi s'appelle `age_jours`.

    ## Le manque, mesuré le 2026-09-06

    `/api/macro/officiel` servait 16 clés par série, dont aucune ne portait de
    verdict de fraîcheur (`grep` retard/stale/fraicheur/qualite : 0), et le
    pied de carte affichait « 11/11 séries publiées » — `disponibles` compte
    `value is not None`, donc la DISPONIBILITÉ, jamais la ponctualité. Le
    même gabarit de tuile rendait alors le SARON du mois dernier (à jour) et
    le rendement Confédération 10 ans arrêté à 2025-07 chez la source, soit
    **14 publications mensuelles manquantes** ; l'IPCH zone euro s'arrêtait à
    2025-12, soit 9 publications manquantes. Le contrat exige que « retard »
    reste un état DISTINCT de absence/zéro/estimation : il n'existait nulle
    part dans la chaîne.

    ## Ce que la fonction refuse de faire

    Marquer en retard un taux directeur. Mesuré : le taux de refinancement
    BCE date du 2026-06-17 (81 jours) et c'est le taux EN VIGUEUR aujourd'hui
    — un badge « 81 jours de retard » y serait un mensonge. D'où
    `SANS_OBJET` pour la fréquence `en vigueur`.

    Le retard constaté est celui de la SOURCE : Vertex ne se trompe pas de
    ligne (cube BNS `rendoblim` rejoué : 451 points, le dernier est bien
    2025-07). Le verdict décrit la donnée, il n'accuse pas la collecte.
    """
    freq = str(frequence or '').strip()
    if freq == FREQ_EN_VIGUEUR:
        #  Une valeur en vigueur ne vieillit pas : elle court jusqu'au
        #  changement suivant. L'âge reste servi, pour l'écran.
        fin = _fin_de_periode(observed_at)
        jours = ((aujourdhui or _dt.date.today()) - fin).days if fin else None
        return 'SANS_OBJET', jours
    fin = _fin_de_periode(observed_at)
    if fin is None:
        return 'INCONNU', None
    jours = ((aujourdhui or _dt.date.today()) - fin).days
    tol = TOLERANCE_J.get(freq)
    if tol is None:
        #  Fréquence inconnue : on rend l'âge, jamais un verdict fabriqué.
        return 'INCONNU', jours
    if jours <= tol:
        return 'A_JOUR', jours
    return ('RETARD_FORT' if jours > 3 * tol else 'RETARD'), jours


def juger_series(series, aujourdhui: _dt.date | None = None) -> list[dict]:
    """Les séries, chacune AVEC son verdict de ponctualité recalculé MAINTENANT.

    ## Le verdict qui rassissait en silence — mesure du 2026-09-06

    `fraicheur` et `retard_jours` étaient calculés UNE fois dans `observer()`,
    écrits dans le dict de la série, persistés par `_sauver()` dans
    `macro_officiel_cache.json`, puis réhydratés tels quels par
    `charger_cache()`. Mesure sur le cache réellement écrit ce jour-là :
    `ch_saron` y est figé à `A_JOUR` / 6 j et `us_10a` à `A_JOUR` / 3 j.
    Rejugées au 2026-11-15 à partir du MÊME `observed_at`, ces deux séries
    valent `RETARD` 76 j et `RETARD_FORT` 73 j. Tant que la boucle de 6 h
    tourne, l'écart est négligeable ; sur le chemin de reprise depuis cache
    (sources injoignables au démarrage), l'API affirmait « à jour » sur une
    donnée qui ne l'était plus — une fraîcheur qui rassit est le défaut du
    verdict de fraîcheur au second degré.

    D'où la règle : le verdict n'est ni stocké ni persisté, il est une
    FONCTION de l'heure de lecture, appliquée au moment de servir. Un
    `retard_jours` laissé par un cache antérieur est retiré, pas conservé à
    côté de `age_jours` : deux champs pour une même grandeur, dont l'un ment
    sur son sens, valent moins qu'un seul.
    """
    out = []
    for s in series or []:
        if not isinstance(s, dict):
            continue
        d = dict(s)
        d.pop('retard_jours', None)      # cache écrit avant le renommage
        d['fraicheur'], d['age_jours'] = juger_fraicheur(
            d.get('frequence') or '', d.get('observed_at') or '', aujourdhui)
        out.append(d)
    return out


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
    jamais une exception qui casserait les autres séries, jamais un zéro.

    Aucun verdict de ponctualité n'est écrit ici : il dépend de l'heure de
    LECTURE, pas de celle de la collecte, et le figer ici le faisait persister
    dans le cache puis réapparaître périmé (voir `juger_series`)."""
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


# ── Communiqués officiels (circuit PUBLICATIONS, flux RSS publics) ──────────
#: (source, libellé, URL). Droits : réutilisation avec attribution (BCE, BNS) ;
#: seuls titre, lien et date sont conservés — jamais le texte des communiqués.
COMMUNIQUES: tuple[tuple[str, str, str], ...] = (
    ('BCE', 'Banque centrale européenne — communiqués de presse',
     'https://www.ecb.europa.eu/rss/press.html'),
    ('BNS', 'Banque nationale suisse — communiqués ad hoc',
     'https://www.snb.ch/public/rss/en/adhoc'),
)
COMMUNIQUES_PAR_SOURCE = 12


def parser_communiques(xml_text: str, source: str, n: int = COMMUNIQUES_PAR_SOURCE) -> list[dict]:
    """Flux RSS → [{source, title, link, published_at, received_at}].

    Lecture par le parseur DURCI de `news_plus` (DTD et entités refusés, taille
    bornée), titres et liens assainis au même point que le fil d'actualités ;
    `published_at` = date FOURNIE par la source — `pubDate` (RSS) sinon
    `dc:date` (Dublin Core) —, normalisée ; None si absente ou illisible,
    jamais inventée ni déduite du titre.

    ## Pourquoi `dc:date` en repli, mesure du 2026-09-06

    Le flux ad hoc de la BNS n'émet AUCUN `pubDate` : sur les 15 379 octets
    servis par `https://www.snb.ch/public/rss/en/adhoc`, `pubDate` apparaît
    **0 fois** et `dc:date` **72 fois** (36 items × ouverture/fermeture) —
    même compte sur la fixture `bns_adhoc.xml`. Ne lire que `pubDate` rendait
    donc `published_at = None` sur **12 communiqués sur 12**, soit 100 % d'un
    fournisseur officiel, alors que la donnée était DÉJÀ en mémoire :
    `_items_surs` rend `<dc:date>2026-09-02T10:15:00Z</dc:date>` sous son nom
    QUALIFIÉ `dc:date` (en plus du nom local), et `horodatage_source` la lit
    sans rien inventer. Le repli cite ce vocabulaire précis : lire le nom
    dénamespacé aurait accepté n'importe quel `<foo:date>` — date de révision,
    date d'événement — comme une date de publication.

    Conséquence mesurée de cette perte : le tri de `collecter_communiques`
    (clé `published_at or ''`) reléguait les 12 BNS derrière les 12 BCE — le
    communiqué du 2026-09-02, 2e plus récent des 24, tombait en 13e position
    et 8 communiqués sortaient des 16 rendus par la carte. Le titre porte
    bien une date en clair (« 2026-09-02 - Federal Council… »), mais on ne
    l'extrait PAS : une chaîne d'affichage n'est pas un horodatage déclaré.

    `pubDate` reste prioritaire : la fixture `bce_press.xml` porte un
    `pubDate` par item et aucun `dc:date` d'item — le chemin BCE est
    inchangé."""
    from vertex.services import news_plus as _np
    out = []
    recu = utc_now_iso()
    for champs in _np._items_surs(xml_text, n):
        titre = _np._clean_text(str(champs.get('title') or '').strip())
        lien = _np._lien_sur(champs.get('link') or '')
        if not titre or not lien:
            continue
        #  `pubDate` d'abord (RSS), `dc:date` ensuite : la BNS ne publie que le
        #  second. Le repli nomme le vocabulaire DUBLIN CORE, pas un `*:date`
        #  quelconque — `_items_surs` conserve le nom qualifié à côté du nom
        #  local, si bien qu'un futur `<foo:date>` (date de révision, date
        #  d'événement) ne peut plus se faire passer pour une date de
        #  publication. Mesure du 2026-09-06 : BCE 15 `pubDate` / 0 `dc:date`
        #  d'item, BNS 0 `pubDate` / 36 `dc:date` — les deux chemins sont
        #  couverts, aucun flux actuel ne porte un autre `*:date`.
        out.append({'source': source, 'title': titre, 'link': lien,
                    'published_at': (_np.horodatage_source(champs.get('pubDate'))
                                     or _np.horodatage_source(champs.get('dc:date'))),
                    'received_at': recu})
    return out


def collecter_communiques(fetch: Callable[[str, str], str]) -> tuple[list[dict], dict]:
    """Tous les flux → (communiqués dédupliqués par lien, triés par date
    décroissante, erreurs par source). Un flux en panne n'emporte pas l'autre."""
    vus, out, erreurs = set(), [], {}
    for source, _lib, url in COMMUNIQUES:
        try:
            for c in parser_communiques(fetch(url, 'application/rss+xml'), source):
                if c['link'] in vus:
                    continue
                vus.add(c['link'])
                out.append(c)
        except Exception as exc:  # noqa: BLE001 — la panne est une donnée
            erreurs[source] = '%s: %s' % (type(exc).__name__, str(exc)[:160])
    out.sort(key=lambda c: c.get('published_at') or '', reverse=True)
    return out, erreurs



__all__ = ['SerieOfficielle', 'Observation', 'CATALOGUE', 'SOURCES', 'url_de',
           'parser_fred', 'parser_bce', 'parser_bns', 'observer', 'collecter',
           'utc_now_iso', 'COMMUNIQUES', 'parser_communiques', 'collecter_communiques',
           'juger_fraicheur', 'juger_series', 'TOLERANCE_J', 'FREQ_EN_VIGUEUR']
