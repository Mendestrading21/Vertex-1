"""vertex.market.news_pipeline — ingestion & validation des actualités (§15).

Source : le fil réel déjà collecté et assaini (news_state, boucle
d'actualités multi-sources). Ce module NORMALISE et VALIDE — il n'invente
jamais un événement : titre + source + heure requis, sinon rejeté
(le rejet est compté, pas masqué).
"""
from __future__ import annotations

from vertex.market.news_dedup import deduplicate, instant as _instant
from vertex.market.news_impact import classify, score_importance
from vertex.services.news_plus import nom_publieur, role_sujet


def _valid(item: dict) -> bool:
    """Titre + publieur + heure. Sans quoi l'événement n'est ni datable ni
    attribuable, et le rejet est COMPTÉ, pas masqué.

    `nom_publieur` remplace `publisher or source` : ces deux clés seules
    rejetaient **toutes les dépêches IBKR et tout le fil yfinance** — qui
    émettent `pub` — en les comptant comme MALFORMÉS. Mesure du 26 août 2026 :
    deux articles sur trois perdus.
    """
    return not raisons_rejet(item)


#: Les causes de rejet, nommées. `rejected` disait COMBIEN, jamais POURQUOI —
#: et un compte sans cause est une forme de masquage. C'est précisément ce qui
#: a envoyé chercher le défaut de D-122 du mauvais côté : deux dépêches IBKR
#: sur trois étaient comptées comme MALFORMÉES alors que le consommateur lisait
#: la mauvaise clé.
CAUSES_REJET = ('non_dict', 'titre_absent', 'publieur_absent', 'date_absente')


def raisons_rejet(item) -> list:
    """Toutes les raisons pour lesquelles cet item ne peut pas devenir un
    événement. Liste vide = item valide.

    Un item peut échouer sur **plusieurs** conditions ; elles sont toutes
    rendues. Ne garder que la première ferait apparaître la seconde seulement
    une fois la première corrigée, et le diagnostic se ferait en deux passes
    au lieu d'une.

    `_valid` en dérive : deux implantations de la même règle divergeraient, et
    c'est exactement le défaut que ce programme paie depuis D-117.
    """
    if not isinstance(item, dict):
        return ['non_dict']
    manque = []
    if not str(item.get('title') or '').strip():
        manque.append('titre_absent')
    if not nom_publieur(item):
        manque.append('publieur_absent')
    if not (item.get('time') or item.get('date')):
        manque.append('date_absente')
    return manque


def collect(news_state: dict, portfolio_syms: list[str] | None = None) -> dict:
    """items bruts → événements validés/dédupliqués/classés + stats de rejet.

    ## `entities` AFFIRMAIT un sujet — mesure du 2026-09-06

    Ce module lit `news_state` DIRECTEMENT (appelé par `daily_brief`), donc
    les items qu'il voit ne portent aucun marquage posé par la route : il
    écrivait `entities = [sym]` dès qu'un `sym` existait. Or `sym` est le FIL
    INTERROGÉ par la boucle de collecte, pas le sujet de la dépêche : sur les
    45 items réels servis, **22 titres sur 45** ne nomment ni le ticker ni la
    société. Conséquence en cascade, mesurée sur la fixture du banc : l'item
    `{'title': 'Fed rate cut', 'sym': 'acn'}` produisait
    `positions_concerned = ['ACN']` et le `+25 portefeuille` de
    `score_importance` (importance 80) — une baisse de taux de la Fed comptée
    comme une actualité DE la position ACN, et remontée à ce titre dans le
    brief quotidien.

    Le sujet est jugé ici par le MÊME juge que la route
    (`news_plus.role_sujet`), et un `sym_role` déjà posé par un producteur est
    réutilisé tel quel : une seule règle, un seul propriétaire.

    ## Ce que la règle coûte — chiffré, plutôt que « rien n'est perdu »

    Aucun ÉVÉNEMENT n'est perdu : le fil interrogé reste servi sous
    `provenance_sym`, qui n'affirme rien, et `entites_non_etablies` compte ce
    qui n'a pas pu être établi. Ce qui est perdu, c'est de l'ATTRIBUTION, et
    seulement quand la table des noms de société ne couvre pas le ticker.
    Mesure du contrôle adverse du 2026-09-06, sur les 45 items réels : 45
    événements avant comme après, 0 rejet supplémentaire, entités affirmées
    45 → 19, rattachements portefeuille 16 → 8 dont les 8 supprimés sont tous
    FAUX. Sur un portefeuille des 5 tickers servis mais ABSENTS de la table,
    en revanche, 3 attributions VRAIES tombaient (2 Lululemon, 1 Sandisk) —
    précision 75 % → 100 %, rappel 100 % → 67 % sur cette tranche. Ces cinq
    raisons sociales ont été ajoutées à `NOMS_SOCIETE` le même jour ; le trou
    est structurel et se comble par des NOMS RÉELS, jamais en relâchant la
    preuve.
    """
    raw = list(news_state.get('items') or [])
    rejected = 0
    par_cause = {c: 0 for c in CAUSES_REJET}
    events = []
    for it in raw:
        manque = raisons_rejet(it)
        if manque:
            rejected += 1
            for cause in manque:
                par_cause[cause] += 1
            continue
        title = str(it.get('title') or '').strip()
        sym = str(it.get('sym') or '').upper().strip()
        role = (it.get('sym_role') or role_sujet(it, sym)) if sym else None
        ev = {
            'title': title,
            'title_fr': str(it.get('fr') or '').strip() or None,
            'source': nom_publieur(it),
            'time': str(it.get('time') or it.get('date') or ''),
            'link': it.get('link') or None,
            'sentiment': it.get('senti'),
            #  N'affirme le titre que quand le sujet est ÉTABLI.
            'entities': [sym] if (sym and role == 'sujet') else [],
            #  Le fil interrogé, conservé sous un nom qui n'affirme rien.
            'provenance_sym': sym or None,
            'sym_role': role,
        }
        ev['category'] = classify(title)
        events.append(ev)
    events = deduplicate(events)
    #  COMPTÉ APRÈS DÉDUPLICATION, sur ce qui est SERVI. Il était incrémenté
    #  dans la boucle d'items : deux dépêches identiques sans sujet établi
    #  donnaient 1 événement et un compteur à 2, alors que la clé s'appelle
    #  `entites_non_etablies` et que sa note dit « événements » (`rejected`,
    #  lui, compte les ITEMS et le dit). Le critère est ce qui est AFFIRMÉ —
    #  `entities` vide sur un événement qui porte pourtant un ticker de
    #  provenance — plutôt que le rôle, parce que la fusion d'un doublon plus
    #  récent peut réécrire `sym_role` sans réécrire `entities` (vide =
    #  falsy, non recopié).
    non_etablies = sum(1 for ev in events
                       if ev.get('provenance_sym') and not ev.get('entities'))
    for ev in events:
        ev['importance'] = score_importance(ev, portfolio_syms or [])
        ev['positions_concerned'] = [s for s in ev.get('entities', [])
                                     if s in (portfolio_syms or [])]
    #  Même clé de récence que la déduplication : trier sur `time` brut
    #  classait par FORME d'horodatage avant de classer par date (voir
    #  `news_dedup.instant`).
    events.sort(key=lambda e: (e['importance'], _instant(e)), reverse=True)
    return {'events': events, 'rejected': rejected,
            #  `rejected` compte les ITEMS ; `rejets_par_cause` compte les
            #  CONDITIONS, et un item peut en manquer plusieurs. Leur somme
            #  n'a donc pas a etre egale — `rejets_note` le dit, plutot que de
            #  laisser un lecteur conclure a une incoherence.
            'rejets_par_cause': par_cause,
            'rejets_note': ('un item peut manquer plusieurs conditions : la somme '
                            'par cause peut depasser le nombre d items rejetes'),
            #  Combien d'événements valides portent un ticker de PROVENANCE
            #  dont le sujet n'est pas établi : ils existent, ils sont servis,
            #  ils ne sont simplement rattachés à aucune position.
            'entites_non_etablies': non_etablies,
            'raw_count': len(raw), 'updated': news_state.get('updated')}


__all__ = ['collect', 'raisons_rejet', 'CAUSES_REJET']
