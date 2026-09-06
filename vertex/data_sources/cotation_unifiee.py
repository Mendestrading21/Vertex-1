"""vertex.data_sources.cotation_unifiee — UN SEUL endroit décide de la source.

## Ce que ce module réunit

Le produit portait **deux piles IBKR** et plusieurs replis, chacun avec sa
propre idée de la priorité :

| pile | ce qu'elle fait | provenance |
| --- | --- | --- |
| workers de `terminal.py` | tout le travail réel (options, cotations, indices) | aucune |
| `vertex/data_sources/ibkr_*` | passerelle, snapshots, historique | complète (`ProvenancedValue`) |

…et, à côté, `source_router.py` — qui **implémente exactement la fusion
demandée** (IBKR live → différé → figé → secondaire → EOD → absence honnête,
avec disjoncteur et mesure de latence) — avec **zéro appelant**. Comme
`fallback_market_data.py`. La fusion était écrite ; elle n'était pas branchée.

Ce module la branche, sur le premier chemin qui en avait besoin : la cotation
des positions.

## Pourquoi passer par le routeur plutôt que par un `if`

Un `if broker sinon scan` marche, et c'est ce que faisait le correctif
précédent. Ce qu'il ne donne pas :

- **l'ordre écrit une seule fois** — trois `if` dans trois fichiers, c'est trois
  priorités qui divergeront (déjà vu deux fois : cinq ordres de ports, trois
  escalades de type de données) ;
- **l'étiquette de provenance** — `SOURCE_IBKR/MODE_LIVE` n'est pas
  `SOURCE_SECONDARY/MODE_DELAYED`, et l'écran doit pouvoir le dire ;
- **`fallback_used`** — posé par le routeur dès qu'on n'est plus sur la source
  de tête, sans que l'appelant ait à y penser ;
- **le disjoncteur** — une source qui échoue deux fois est mise au repos 30 s
  au lieu d'être retentée à chaque requête.

## Ce qu'il ne fait pas

Il ne **fabrique** rien. Quand aucune source ne répond, il rend le `missing()`
du routeur — une absence tracée, qui devient un `—` à l'écran. C'est la seule
réponse honnête, et elle vaut mieux qu'un zéro plausible.
"""
from __future__ import annotations

from .models import (
    MODE_DELAYED, MODE_LIVE, SOURCE_IBKR, SOURCE_SECONDARY, ProvenancedValue,
)
from .provenance import stamp
from .source_router import SourceRouter


def _fournisseur(valeur, source: str, mode: str):
    """Enveloppe une valeur DÉJÀ obtenue en fournisseur pour le routeur.

    Les cotations broker arrivent par lots (un job pour toutes les positions) :
    rejouer un appel par symbole serait absurde et violerait le pacing IBKR. On
    présente donc au routeur ce qu'on a déjà, et c'est LUI qui tranche et
    étiquette — le bénéfice recherché n'est pas de rappeler la source, c'est
    d'avoir **une seule règle de priorité**.
    """
    def _f():
        if valeur is None:
            return None
        prix = valeur.get('spot') if isinstance(valeur, dict) else None
        if prix is None:
            return None
        return stamp(value=dict(valeur), source=source, source_mode=mode)
    return _f


def resoudre_cotation(broker=None, secondaire=None, *, symbole: str = '',
                      devise: str = '',
                      routeur: SourceRouter | None = None) -> ProvenancedValue:
    """Meilleure cotation disponible, étiquetée.

    `broker` : ce qu'IBKR a rendu (ou None). `secondaire` : le repli déjà en
    mémoire (scan). Les deux ont la forme `{'spot':…, 'spot_chg':…}`.

    L'ordre n'est pas décidé ici : il vient de `source_router.PRIORITY`, seule
    table de priorité du produit.

    Lot 5 — l'enveloppe rendue porte le contrat canonique quand l'appelant
    sait le remplir : `instrument_id` (le symbole qualifié), `currency` (la
    devise s'il la CONNAÎT — jamais un USD supposé), `unit` (un spot est un
    prix), et le `lineage` de production. Les champs restent None/''
    lorsqu'ils ne sont pas connus : l'absence est une donnée, pas un défaut.
    """
    r = routeur or SourceRouter()
    r.register(SOURCE_IBKR, MODE_LIVE, _fournisseur(broker, SOURCE_IBKR, MODE_LIVE))
    r.register(SOURCE_SECONDARY, MODE_DELAYED,
               _fournisseur(secondaire, SOURCE_SECONDARY, MODE_DELAYED))
    pv = r.fetch()
    if pv is not None:
        pv.instrument_id = symbole.upper() or None
        pv.currency = devise or None
        pv.unit = 'prix' if pv.value is not None else None
        pv.lineage.append('cotation_unifiee.resoudre_cotation')
    return pv


def en_charge_client(pv: ProvenancedValue) -> dict | None:
    """Traduit une valeur tracée en charge JSON pour l'écran.

    `source` et `mode` sont TOUJOURS portés : sans eux, un cours de scan se fait
    passer pour une cotation broker — le mensonge de provenance le plus facile
    à commettre, et le plus difficile à détecter après coup.
    """
    if pv is None or pv.value is None:
        return None
    v = dict(pv.value)
    v.update({'type': 'STK', 'source': pv.source, 'mode': pv.source_mode,
              'fallback_used': bool(pv.fallback_used)})
    #  CONSTAT 27, RACINE. Le repli OPTION (`routes/desk.py
    #  _scan_fallback_quote`) étiquette sa cote `delayed: True` ; ce repli-ci,
    #  celui des ACTIONS, ne le posait pas — il ne servait que `mode:'DELAYED'`
    #  et `fallback_used: true`. Deux écritures du MÊME fait dans la même
    #  charge `/api/pos-quotes`, et une page qui n'en lit qu'une annonce du
    #  temps réel sur un prix de scan (mesuré : le seul test `q.delayed`
    #  laissait une action valorisée au cours du scan s'afficher sans aucune
    #  marque de différé). La règle client (`VX.quotes.differee`) est un OU
    #  logique des trois champs : poser le troisième ne double aucun compte et
    #  ferme la divergence de vocabulaire à sa source. Rien n'est affirmé —
    #  `delayed` n'est écrit que si le routeur a réellement classé la cote en
    #  mode différé.
    if pv.source_mode == MODE_DELAYED:
        v['delayed'] = True
    return v


__all__ = ['resoudre_cotation', 'en_charge_client']
