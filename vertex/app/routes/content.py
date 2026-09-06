"""
vertex/app/routes/content.py — FILS DE CONTENU (Blueprint, Ch. II).

Actualités, calendrier de catalyseurs, watchlist hebdo — lectures des états
partagés (`vertex.app.state`). Le flag `ai_on` signale si la couche IA
(résumés/traductions) est disponible. Lecture seule, analyse uniquement.
"""

from flask import Blueprint, jsonify, request

from vertex.ai import briefs as ai
from vertex.data import macro_calendar
from vertex.services import news_plus
from vertex.app.state import news_state, cal_state, weekly_state

bp = Blueprint('content', __name__)


@bp.route('/news-feed')
def news_feed_ep():
    """Fil de news. Recherche serveur : ?sym=NVDA (fil) · ?q=fed (mot-clé).

    ## `sym` est une PROVENANCE, pas un sujet — mesure du 2026-09-06

    La boucle de collecte écrit `sym` = le fil interrogé, pas le titre dont
    parle la dépêche. Mesure sur les 45 items servis : **22 titres sur 45** ne
    nomment ni le ticker ni la société ; `GET /news-feed?sym=NVDA` rendait
    4 articles — Snowflake, GitLab, Shopify, le pétrole — dont AUCUN sur
    Nvidia, et `sentiment['NVDA']` valait `{'n': 4, 'score': 0.5}`.

    Ce qui est corrigé ici : chaque item servi porte `sym_role`
    (`sujet` = le sujet est établi, `fil` = simple provenance), la réponse dit
    combien d'items filtrés sont dans chaque cas, et l'agrégat par sujet
    confirmé est servi à côté de l'agrégat de provenance, qui nomme désormais
    sa base. Aucun item n'est retiré : une dépêche hors sujet reste de
    l'information réelle, elle cesse seulement d'affirmer un sujet.

    ## Pourquoi la table par sujet est peu peuplée, DIT au lieu d'être subi

    `sujet_preuves` sert l'état RÉEL des trois canaux de preuve, DÉRIVÉ d'un
    balayage du dépôt — jamais écrit en dur ici. Sans cette déclaration, un
    lecteur de l'API ne peut pas distinguer « peu de sujets établis » de « un
    canal de preuve est éteint », et la seconde explication resterait invisible.

    Cette prose affirmait encore que l'attestation du vendeur valait
    `NON_IMPLÉMENTÉ` faute de producteur. Mesuré le 2026-09-06 par appel
    direct : la MÊME fonction sert `attestation_vendeur: 'ACTIF'` depuis que
    `terminal.py::_news_loop` pose `sym_atteste` sur la seule branche courtier.
    Aucune valeur servie n'était fausse — c'est la documentation de la route
    qui contredisait sa propre sortie, ce qui est la façon la plus discrète de
    rendre une garde inutile : un lecteur qui croit le commentaire ne va pas
    vérifier la réponse. La valeur reste dérivée du balayage, donc elle
    retombera d'elle-même si le producteur disparaît.
    """
    items = news_state.get('items') or []
    sym = (request.args.get('sym') or '').upper().strip()
    q = (request.args.get('q') or '').lower().strip()
    if sym:
        items = [n for n in items if (n.get('sym') or '').upper() == sym]
    if q:
        items = [n for n in items
                 if q in (str(n.get('title') or '') + ' ' + str(n.get('fr') or '')
                          + ' ' + str(n.get('publisher') or '')).lower()]
    # XSS : titres/liens externes assainis AU POINT DE SORTIE (rendus en innerHTML côté client)
    items = news_plus.sanitize_news(items)
    #  Le rôle est posé APRÈS l'assainissement : il se lit sur le texte
    #  réellement servi, pas sur une version que le client ne verra pas.
    items = news_plus.marquer_sujets(items)
    n_sujets = sum(1 for n in items if n.get('sym_role') == 'sujet')
    filtre = ({'sym': sym, 'base': 'fil interrogé',
               'sujets_confirmes': n_sujets, 'sujet_non_etabli': len(items) - n_sujets}
              if sym else None)
    return jsonify({**news_state, 'items': items, 'filtered': bool(sym or q),
                    'filtre_sym': filtre,
                    #  Agrégat de PROVENANCE : conservé pour ses appelants, mais
                    #  il dit maintenant sur quoi il est bâti (invariant 6).
                    'sentiment': news_plus.aggregate(items),
                    'sentiment_base': 'fil interrogé (provenance) — pas le sujet de la dépêche',
                    #  Agrégat par sujet ÉTABLI : un ticker sans article confirmé
                    #  en est absent, il n'y reçoit pas un score fabriqué.
                    'sentiment_sujets': news_plus.aggregate(items, sujets_seulement=True),
                    #  Quels canaux de preuve de sujet sont RÉELLEMENT actifs.
                    'sujet_preuves': news_plus.PREUVES_SUJET,
                    'ai_on': ai.available()})


@bp.route('/cal-feed')
def cal_feed_ep():
    """Earnings + macro : FOMC (dates Fed PUBLIÉES), NFP et CPI (RÈGLES de
    calendrier, donc approximatifs — le calendrier officiel BLS n'est pas lu).

    `macro_couverture` dit jusqu'où le calendrier FOMC publié va : au-delà, une
    absence de réunion est une absence de DONNÉE, pas une absence d'événement.
    """
    #  La couverture accompagne les evenements : un horizon qui depasse le
    #  calendrier FOMC publie doit se voir, pas se deviner.
    return jsonify({**cal_state, **_items_dates(cal_state),
                    'macro': macro_calendar.events(horizon_days=120),
                    'macro_couverture': macro_calendar.couverture(horizon_days=120)})


def _items_dates(etat: dict) -> dict:
    """Les items du calendrier, DATÉS à la lecture.

    Mesuré : `cal_cache.json` réhydraté au démarrage gardait un `dte` figé au
    moment de la collecte (un cache de trois jours annonçait J-10 pour un
    résultat à J-7) et aucun `ts` avant la première publication ; en démo, les
    dates synthétiques ne portaient aucun drapeau. Ici : `dte` recalculé depuis
    `date`, `ts` = époque de publication sinon mtime du cache, `source` et
    `confirmation` par item — l'écran ne peut plus dire « Confirmé » de lui-même.
    """
    import os as _os
    from datetime import date as _date
    from vertex.app.config import DEMO_MODE as _demo
    items = []
    aujourd_hui = _date.today()
    for it in (etat.get('items') or []):
        it = dict(it)
        try:
            d = _date.fromisoformat(str(it.get('date') or '')[:10])
            it['dte'] = (d - aujourd_hui).days
        except ValueError:
            it['dte'] = None
        it['source'] = 'demo' if _demo else 'yfinance'
        it['confirmation'] = ('synthétique (démonstration)' if _demo
                              else 'date fournisseur, non confirmée par l’émetteur')
        items.append(it)
    ts = etat.get('ts')
    if not ts:
        try:
            racine = _os.path.dirname(_os.path.dirname(_os.path.dirname(
                _os.path.dirname(_os.path.abspath(__file__)))))
            ts = _os.path.getmtime(_os.path.join(racine, 'cal_cache.json'))
        except OSError:
            ts = None
    return {'items': items, 'ts': ts, 'source': 'demo' if _demo else 'yfinance',
            'demo': bool(_demo)}


@bp.route('/weekly-feed')
def weekly_feed_ep():
    return jsonify({**weekly_state, 'ai_on': ai.available()})


__all__ = ['bp']
