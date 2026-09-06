"""
vertex/data/macro_calendar.py — CALENDRIER MACRO : LA SOURCE DE CHAQUE DATE.

`VERTEX-INTELLIGENCE-2.0`, Phase 3, critère d'acceptation :

> `macro_calendar.py` ne crée plus de date exacte depuis une règle approximative.

## Les trois défauts, mesurés le 26 août 2026

**1. La liste FOMC expirait en silence.** `FOMC_2026` s'arrête au 9 décembre
2026. Mesuré :

```text
depuis 2026-08-26, horizon 365 j : FOMC 3   NFP 12   CPI 12
depuis 2026-12-20, horizon 365 j : FOMC 0   NFP 12   CPI 12
depuis 2027-06-01, horizon 365 j : FOMC 0   NFP 12   CPI 12
```

Zéro réunion de la Fed sur un an, servi **sans un mot**, à côté de vingt-quatre
autres événements qui, eux, continuaient d'arriver. Un lecteur en conclut qu'il
n'y a pas de FOMC, pas que le calendrier s'est tu. Et l'échéance était proche :
trois mois et demi.

**2. Le NFP se disait CERTAIN alors qu'il vient d'une règle.** `approx: False`
sur une date calculée par `_first_friday` — pas lue dans le calendrier officiel
du BLS, que Vertex ne consulte pas. Une règle peut coïncider avec la
publication ; elle ne peut pas en porter la certitude. Le cas limite est
visible dans l'année en cours : le 1er mai 2026 **est** un vendredi, et c'est
précisément la configuration où une convention de calendrier se discute.

**3. Le CPI fabriquait le 13.** Marqué `approx: True` — honnête — mais le champ
`date` reste une date ISO précise, et un consommateur qui ignore `approx`
affiche une fausse précision.

## Ce que ce module garantit désormais

Chaque événement porte sa **source** (`FED_PUBLIE` ou `REGLE_BLS`), et `approx`
en **découle** : une date issue d'une règle ne peut structurellement pas être
marquée certaine. Et `couverture()` dit jusqu'où le calendrier publié va, et
combien de jours de l'horizon demandé ne sont couverts par rien.

## Ce que ce module ne fait toujours PAS

Il n'appelle **aucun réseau** — c'était vrai avant, ça le reste. Les dates
officielles du BLS et de la Fed viendraient d'un flux à contractualiser
(licence, replay, point-in-time) : c'est la suite de la Phase 3, pas ce lot.
Ici, on cesse de **prétendre** ; on ne prétend pas non plus avoir la source.
"""

from datetime import date, timedelta

#: Dates de DÉCISION du FOMC 2026, publiées par la Réserve fédérale (2e jour de
#: réunion). Recopiées, donc datées : voir `PUBLIE_LE`.
FOMC_PUBLIE = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
]

#: Nom historique, conservé pour les consommateurs existants.
FOMC_2026 = FOMC_PUBLIE

#: Jusqu'où le calendrier PUBLIÉ va. Au-delà, ce module ne sait rien — et le
#: dit, au lieu de rendre une liste vide qui se lit « aucune réunion ».
DERNIERE_DATE_PUBLIEE = max(FOMC_PUBLIE)

#: Sources possibles d'une date. `approx` en découle : voir `_APPROX_PAR_SOURCE`.
SOURCE_FED = 'FED_PUBLIE'
SOURCE_REGLE = 'REGLE_BLS'

#: **Une règle ne rend jamais une date certaine.** C'est la table qui l'impose,
#: et non chaque appelant : un `approx` recopié à la main finit par diverger de
#: la source qu'il décrit — c'est le défaut de D-084, payé trois fois.
_APPROX_PAR_SOURCE = {
    SOURCE_FED: False,
    SOURCE_REGLE: True,
}

#: Niveau de confirmation SERVI avec chaque événement, dérivé de la source
#: comme `approx` : l'écran ne décide jamais « Confirmé » de lui-même. Le
#: texte commence par « confirmée » ou « non confirmée » : c'est le contrat
#: que lit le calendrier (calendar.js, `badgeConfirmation`).
_CONFIRMATION_PAR_SOURCE = {
    SOURCE_FED: 'confirmée — calendrier officiel publié par la Fed',
    SOURCE_REGLE: 'non confirmée — règle de calendrier, date non publiée',
}


def _premier_vendredi(annee, mois):
    d = date(annee, mois, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _mi_mois(annee, mois):
    """CPI : publication BLS vers la mi-mois. Le 13 est un REPÈRE, pas une date."""
    return date(annee, mois, 13)


def couverture(horizon_days=120, today=None) -> dict:
    """Jusqu'où ce calendrier sait, et à partir d'où il ne sait plus.

    Sans ce bloc, un horizon qui dépasse la dernière date publiée rend
    simplement **moins d'événements** — indiscernable d'une période calme.
    """
    today = today or date.today()
    limite = today + timedelta(days=horizon_days)
    depasse = limite > DERNIERE_DATE_PUBLIEE
    return {
        'fomc_publie_jusqu_a': DERNIERE_DATE_PUBLIEE.isoformat(),
        'horizon_demande_jusqu_a': limite.isoformat(),
        'fomc_horizon_depasse': depasse,
        'fomc_jours_non_couverts': max(0, (limite - DERNIERE_DATE_PUBLIEE).days),
        'fomc_epuise': today > DERNIERE_DATE_PUBLIEE,
        'sources': {SOURCE_FED: 'calendrier publié par la Réserve fédérale',
                    SOURCE_REGLE: 'règle de calendrier, pas une date publiée'},
        'reseau': False,
        'note': ("les dates BLS ne sont pas lues d'un calendrier officiel : "
                 "elles viennent d'une règle et sont marquées approximatives"),
        'read_only': True,
    }


def events(horizon_days=120, today=None):
    """Les événements macro à venir, triés par date.

    `[{date, dte, kind, label, importance, approx, source, note}]`

    `approx` **découle** de `source` : une date issue d'une règle ne peut pas
    être marquée certaine. Quand l'horizon dépasse le calendrier FOMC publié,
    un événement `COUVERTURE` le dit, à sa date de fin — parce qu'une absence
    silencieuse se lit comme une absence de réunion.
    """
    today = today or date.today()
    limite = today + timedelta(days=horizon_days)
    out = []

    for d in FOMC_PUBLIE:
        if today <= d <= limite:
            out.append(_evenement(
                d, 'FOMC', 'Décision Fed (FOMC)', 'haute', SOURCE_FED,
                'taux + conférence Powell 14h30 ET — volatilité indices/taux'))

    annee, mois = today.year, today.month
    for _ in range(max(1, horizon_days // 28) + 1):
        for calcul, kind, label, note in (
            (_premier_vendredi, 'NFP', 'Emploi US (NFP)',
             'premier vendredi 8h30 ET (règle, pas le calendrier BLS officiel) '
             '— chocs sur taux et dollar'),
            (_mi_mois, 'CPI', 'Inflation US (CPI)',
             'publication BLS vers la mi-mois (repère, pas une date publiée) '
             '— pivot du récit Fed'),
        ):
            d = calcul(annee, mois)
            if today <= d <= limite:
                out.append(_evenement(d, kind, label, 'haute', SOURCE_REGLE, note))
        mois += 1
        if mois > 12:
            mois, annee = 1, annee + 1

    cov = couverture(horizon_days, today)
    if cov['fomc_horizon_depasse']:
        #  Une absence qui ne se dit pas se lit comme « aucune reunion ».
        out.append(_evenement(
            min(limite, max(today, DERNIERE_DATE_PUBLIEE)), 'COUVERTURE',
            'Calendrier FOMC non publié au-delà du %s'
            % DERNIERE_DATE_PUBLIEE.isoformat(),
            'information', SOURCE_FED,
            'aucune réunion n’est inférée sur les %d jours suivants — absence de '
            'donnée, pas absence d’événement' % cov['fomc_jours_non_couverts']))

    for e in out:
        e['dte'] = (date.fromisoformat(e['date']) - today).days
    out.sort(key=lambda e: (e['date'], e['kind']))
    return out


def _evenement(d, kind, label, importance, source, note):
    return {
        'kind': kind,
        'date': d.isoformat(),
        'label': label,
        'importance': importance,
        'source': source,
        #  Derive, jamais recopie : voir `_APPROX_PAR_SOURCE`.
        'approx': _APPROX_PAR_SOURCE[source],
        'confirmation': _CONFIRMATION_PAR_SOURCE[source],
        'note': note,
    }
