"""vertex.data_sources.ibkr_news — DEPECHES DU COURTIER (lecture seule).

Les news venaient du web (yfinance, puis un repli RSS), alors que le compte
est abonne a des fournisseurs professionnels. Meme raison que pour les
barres du scan : deux origines pour un meme titre, c'est accepter que
l'ecran et le fil ne parlent pas de la meme actualite.

## Les fournisseurs sont MESURES, pas listes

`reqNewsProviders()` rend huit codes, mais trois ne sont pas abonnes. Et
c'est un piege concret : passer la liste ENTIERE a `reqHistoricalNews`
fait rejeter la requete COMPLETE (erreur 321, « Not subscribed »), donc
zero depeche alors que quatre fournisseurs repondaient. Mesure du jour sur
U<masque>, AAPL, 3 jours :

    BRFG 5 · DJ-N 5 · DJ-RT 5 · BRFUPDN 5 · DJNL 0
    DJ-RTA / DJ-RTE / DJ-RTG : erreur 321

On interroge donc fournisseur par fournisseur : un refus en isole un seul.

## Ce que ce module ne fait pas

Il ne fabrique pas de lien. IBKR ne sert pas d'URL publique — un article se
lit par `reqNewsArticle(providerCode, articleId)`. Rendre un lien vide est
l'aveu exact ; en inventer un donnerait un clic mort.
"""
from __future__ import annotations

import datetime as _dt
import re
import threading
from vertex.data_sources import ibkr_gateway

#: Fournisseurs MESURES comme servant des depeches sur ce compte. DJNL rend
#: systematiquement zero et les trois DJ-RT* ne sont pas abonnes : les
#: garder ne couterait pas une erreur, cela couterait un aller-retour par
#: symbole et par tour de boucle, pour rien.
FOURNISSEURS = ('BRFG', 'DJ-N', 'DJ-RT', 'BRFUPDN')

#: `reqHistoricalNews` prefixe ses titres de metadonnees de langue et
#: d article — « {A:800015:L:en}Apple Bites Into Record Q3 ». Affiche tel
#: quel, le fil commencerait par une accolade technique.
_PREFIXE = re.compile(r'^[{][^}]*[}]')

_VERROU = threading.Lock()


def _titre(brut: str) -> str:
    return _PREFIXE.sub('', str(brut or '')).strip()


def depeches_pour(symbole: str, n: int = 4, *, gateway=None, jours: int = 3):
    """Les `n` dernieres depeches du courtier pour ce titre.

    Rend la forme deja attendue par la boucle news — {title, pub, time,
    link} — pour que la traduction FR et le sentiment continuent de
    s'appliquer sans etre reecrits.

    Une absence reste une absence : un symbole sans depeche rend une liste
    VIDE, et l'appelant ira au repli. Rendre un article vide le ferait
    passer pour servi.
    """
    Stock = ibkr_gateway.classe('Stock')
    notre = gateway is None
    if notre:
        from .ibkr_gateway import IbkrGateway
        from . import ibkr_link
        gateway = IbkrGateway(client_id=ibkr_link.client_id('news'))
    out = []
    verrou = _VERROU if notre else None
    if verrou:
        verrou.acquire()
    try:
        ib = gateway.connect()
        c = Stock(str(symbole).replace('-', ' ').upper(), 'SMART', 'USD')
        ib.qualifyContracts(c)
        if not getattr(c, 'conId', 0):
            return []
        fin = _dt.datetime.now(_dt.timezone.utc)
        deb = fin - _dt.timedelta(days=jours)
        vus = set()
        for code in FOURNISSEURS:
            try:
                lot = ib.reqHistoricalNews(
                    c.conId, code,
                    deb.strftime('%Y-%m-%d %H:%M:%S'),
                    fin.strftime('%Y-%m-%d %H:%M:%S'), n)
            except Exception:  # noqa: BLE001
                continue                     # un refus en isole UN, pas tous
            for a in (lot or []):
                t = _titre(getattr(a, 'headline', ''))
                if not t or t in vus:
                    continue
                vus.add(t)
                out.append({'title': t,
                            'pub': getattr(a, 'providerCode', '') or 'IBKR',
                            #  L'HORODATAGE N'EST PLUS TRONQUE. `[:16]` gardait
                            #  « 2026-09-05 13:22 » et jetait la QUEUE, qui
                            #  porte le fuseau declare par le courtier :
                            #  `ib_insync` rend un datetime UTC, dont le
                            #  `str()` est « 2026-09-05 13:22:11+00:00 ».
                            #  Consequence mesuree : `horodatage_source` ne
                            #  voyait plus aucun fuseau et rendait
                            #  « 2026-09-05T13:22 » — l'ecran affichait
                            #  « fuseau n/d » sur une source qui, elle, le
                            #  declare. On garde donc la chaine ENTIERE ; c'est
                            #  `horodatage_source` qui normalise, et lui
                            #  n'invente pas de fuseau quand la source se tait.
                            'time': str(getattr(a, 'time', '') or '').strip(),
                            'link': ''})   # IBKR n'expose pas d'URL publique
    finally:
        if notre:
            try:
                if gateway._ib:
                    gateway._ib.disconnect()
            except Exception as exc:  # noqa: BLE001
                out.append({'title': '', 'pub': '', 'time': '',
                            'link': '', 'fermeture': str(exc)[:80]})
                out = [x for x in out if x.get('title')]
        if verrou:
            verrou.release()
    out.sort(key=lambda x: x['time'], reverse=True)
    return out[:n]


__all__ = ['depeches_pour', 'depeches_lot', 'FOURNISSEURS']


def depeches_lot(symboles, n: int = 4, *, jours: int = 3):
    """Les depeches de PLUSIEURS titres sur UNE seule session.

    La boucle news couvre 18 symboles (12 fixes + 6 chauds) a chaque tour.
    Appeler `depeches_pour` symbole par symbole ouvrirait 18 sessions par
    tour, sur un identifiant client unique : la connexion couterait plus cher
    que les depeches. On ouvre donc une fois, on interroge tout, on ferme.

    Rend `{symbole: [articles]}`. Un titre sans depeche est ABSENT du
    dictionnaire — jamais present avec une liste vide, ce qui le ferait
    passer pour servi et empecherait le repli d'aller le chercher.
    """
    symboles = [str(x) for x in (symboles or [])]
    if not symboles:
        return {}
    from .ibkr_gateway import IbkrGateway
    from . import ibkr_link
    passerelle = IbkrGateway(client_id=ibkr_link.client_id('news'))
    out = {}
    with _VERROU:
        try:
            passerelle.connect()
            for sym in symboles:
                try:
                    art = depeches_pour(sym, n, gateway=passerelle, jours=jours)
                except Exception:  # noqa: BLE001
                    continue
                if art:
                    out[sym] = art
        except Exception:  # noqa: BLE001
            return out                 # TWS absent : le repli prendra la suite
        finally:
            try:
                if passerelle._ib:
                    passerelle._ib.disconnect()
            except Exception as exc:  # noqa: BLE001
                out.setdefault('_fermeture', str(exc)[:80])
    out.pop('_fermeture', None)
    return out
