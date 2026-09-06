"""vertex.data_sources.ibkr_replay — REJOUER LE COURTIER SANS LE COURTIER.

G5 exige qu'une session TWS réelle soit prouvée. Mais une preuve qu'on ne peut
pas rejouer ne protège plus rien le lendemain : personne ne relance TWS pour
vérifier une régression, et c'est très exactement pour cela que les quatre
adaptateurs IBKR sont restés à **0 % de couverture** pendant que la connexion,
elle, était démontrée.

Ce module fait deux choses, et rien de plus :

1. **anonymiser** un relevé G5, pour que le dépôt puisse le conserver ;
2. **rejouer** les callbacks enregistrés, pour piloter le *vrai* code des
   adaptateurs hors TWS.

## Pourquoi un double « canardé » et non un mock

Un mock vérifie qu'on a appelé une méthode. On veut l'inverse : que le code des
adaptateurs — `qualify_stock`, `fetch_snapshot`, `fetch_positions`,
`fetch_expirations`, `fetch_contract_details` — s'exécute réellement, avec ses
conversions, ses gardes de `NaN` et sa provenance, sur des valeurs **venues d'un
vrai broker**. Le double lit une fixture ; il n'invente aucune valeur.

## Ce que ce module ne fait pas

Il ne remplace pas la session live. Un rejeu ne prouve ni le rythme, ni la
reconnexion, ni les droits du compte : ces cases restent `HUMAN_REQUIRED` et le
disent. Il n'ouvre pas non plus le contrat générique de providers prévu en
phase 2 (`data_sources/replay.py`) : il est volontairement borné à IBKR, pour
que la phase 1 se termine sans commencer la phase 2.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from vertex.data_sources import ibkr_gateway

#: Version du format de fixture. Une fixture sans version, ou d'une version que
#: ce lecteur ne connaît pas, est REFUSÉE : rejouer un format qu'on ne comprend
#: pas produirait une preuve fausse, ce qui est pire qu'une erreur.
VERSION_FIXTURE = 1

#: Identifiant de compte IBKR : `U` ou `DU` suivi de chiffres. Cherché partout,
#: y compris dans les messages d'erreur du broker — c'est là qu'il apparaît le
#: plus souvent, et c'est le dernier endroit où on pense à le masquer.
_COMPTE = re.compile(r"\b(?:DU|U)\d{6,}\b")

#: Remplaçant stable : deux relevés du même compte restent comparables entre
#: eux sans que le compte soit lisible.
MASQUE_COMPTE = "U<masque>"


def masquer_comptes(x):
    """Remplace tout identifiant de compte, à n'importe quelle profondeur."""
    if isinstance(x, str):
        return _COMPTE.sub(MASQUE_COMPTE, x)
    if isinstance(x, dict):
        return {k: masquer_comptes(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [masquer_comptes(v) for v in x]
    return x


def anonymiser(releve: dict) -> dict:
    """Un relevé G5 débarrassé de ce qui identifie le compte ou le portefeuille.

    Ce qui **part** : identifiants de compte, symboles détenus, quantités. Un
    portefeuille est une donnée personnelle, et la simple *liste des titres
    détenus* en est une même sans les quantités — elle se relie à une personne.

    Ce qui **reste** : cotations et Greeks (donnée de marché publique, et sans
    elles le rejeu ne pilote plus rien), modes de données, codes d'erreur,
    durées, et les **cardinalités** des écarts de position. Compter les écarts
    suffit à prouver que la réconciliation tourne ; les nommer ne prouverait
    rien de plus et publierait le portefeuille.
    """
    out = masquer_comptes(dict(releve or {}))
    pos = out.get("positions")
    if isinstance(pos, dict):
        out["positions"] = {
            "n_detenues_non_declarees": len(pos.get("detenues_non_declarees") or []),
            "n_declarees_non_detenues": len(pos.get("declarees_non_detenues") or []),
            "n_quantites_divergentes": len(pos.get("quantites_divergentes") or []),
            "concordant": bool(pos.get("concordant")),
            "anonymise": True,
        }
    out["anonymise"] = True
    return out


def contient_donnee_sensible(x) -> list:
    """Les traces personnelles encore présentes. Liste vide = publiable.

    Sert de **témoin** : un anonymiseur qui ne trouve rien parce qu'il regarde
    au mauvais endroit rend exactement la même réponse qu'un anonymiseur qui a
    travaillé. Ce contrôle est donc écrit séparément de `anonymiser`, et il
    cherche les deux formes de fuite : l'identifiant, et la liste des titres.
    """
    trouve = []

    def _voir(v, chemin):
        if isinstance(v, str) and _COMPTE.search(v):
            trouve.append("%s : identifiant de compte" % chemin)
        elif isinstance(v, dict):
            for k, sv in v.items():
                _voir(sv, "%s.%s" % (chemin, k))
        elif isinstance(v, (list, tuple)):
            for i, sv in enumerate(v):
                _voir(sv, "%s[%d]" % (chemin, i))

    _voir(x, "$")
    pos = x.get("positions") if isinstance(x, dict) else None
    if isinstance(pos, dict):
        for cle in ("detenues_non_declarees", "declarees_non_detenues",
                    "quantites_divergentes"):
            if pos.get(cle):
                trouve.append("$.positions.%s : titres détenus" % cle)
    trouve.extend(_lignes_de_detention(x, "$"))
    return trouve


#: Ce qui fait d'un dictionnaire une LIGNE DE DÉTENTION : un titre, et une
#: grandeur qui n'a de sens que si on le possède.
_CLE_TITRE = ("symbol", "sym", "ticker", "localSymbol", "conId")
_CLE_DETENTION = ("position", "quantity", "qty", "avgcost", "avg_cost",
                  "averagecost", "cost_basis", "capital_committed",
                  "marketvalue", "market_value", "unrealizedpnl",
                  "realizedpnl", "unrealized_pnl")


def _lignes_de_detention(x, chemin) -> list:
    """Toute ligne « titre + détention », À N'IMPORTE QUELLE PROFONDEUR.

    ## Pourquoi chercher une FORME et non une clé

    Mesuré le 2026-09-06 : ce témoin ne regardait qu'une clé `positions` de
    PREMIER NIVEAU, de type dict, avec trois sous-clés attendues. Or une
    capture réelle produit `fixture.positions_brutes`, une LISTE de
    `{symbol, position, avgCost}`. Sur un relevé de cette forme, `anonymiser()`
    rendait les tickers, les quantités et les prix de revient INTACTS, le
    témoin rendait `[]` — donc « publiable » — et `enregistrer()` écrivait le
    fichier sans refuser.

    La docstring d'`enregistrer` promet pourtant : « REFUSE d'écrire si une
    trace subsiste », parce qu'un artefact publié « en espérant » finit dans un
    dépôt public. La promesse était plus large que le contrôle, et c'est
    exactement la forme de défaut que ce dépôt vient de payer ailleurs.

    On cherche donc la PROPRIÉTÉ : un identifiant de titre accompagné d'une
    grandeur qui suppose qu'on le possède. Une cotation (`symbol`, `bid`,
    `ask`, `iv`) reste de la donnée de MARCHÉ et n'est pas signalée — sans
    quoi le rejeu perdrait ce qui le fait fonctionner.
    """
    out = []
    if isinstance(x, dict):
        bas = {str(k).lower() for k in x}
        titre = bas & {c.lower() for c in _CLE_TITRE}
        detention = bas & set(_CLE_DETENTION)
        if titre and detention and any(
                x.get(k) not in (None, "", [], {}) for k in x
                if str(k).lower() in detention):
            out.append("%s : ligne de détention (%s + %s)"
                       % (chemin, sorted(titre)[0], sorted(detention)[0]))
        for k, v in x.items():
            out.extend(_lignes_de_detention(v, "%s.%s" % (chemin, k)))
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            out.extend(_lignes_de_detention(v, "%s[%d]" % (chemin, i)))
    return out


def enregistrer(releve: dict, chemin) -> Path:
    """Écrit une fixture anonymisée. REFUSE d'écrire si une trace subsiste.

    Le refus est le point : un artefact qu'on publie « en espérant » qu'il soit
    propre finit dans un dépôt public avec un numéro de compte dedans.
    """
    anon = anonymiser(releve)
    restes = contient_donnee_sensible(anon)
    if restes:
        raise ValueError("anonymisation incomplète : %s" % " ; ".join(restes))
    paquet = {"version_fixture": VERSION_FIXTURE, "releve": anon}
    p = Path(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(paquet, indent=2, ensure_ascii=False, default=str),
                 encoding="utf-8")
    return p


def charger(chemin) -> dict:
    """Lit une fixture. Un format inconnu est une erreur, pas un défaut."""
    paquet = json.loads(Path(chemin).read_text(encoding="utf-8"))
    v = paquet.get("version_fixture")
    if v != VERSION_FIXTURE:
        raise ValueError(
            "fixture en version %r, lecteur en version %r — rejouer un format "
            "non compris produirait une preuve fausse" % (v, VERSION_FIXTURE))
    return paquet["releve"]


# ─────────────────────────────  les doubles de rejeu  ─────────────────────────
#
#  Ils imitent la surface d'`ib_async` que les adaptateurs utilisent VRAIMENT,
#  et rien d'autre. Ajouter des méthodes « au cas où » donnerait l'illusion
#  d'une couverture plus large que le code réellement exercé.

_NAN = float("nan")


class ContratRejoue:
    """Un contrat façon `ib_async` : attributs nus, pas de comportement."""

    def __init__(self, symbol="", secType="STK", exchange="SMART",
                 currency="USD", conId=0, strike=0.0, right="",
                 lastTradeDateOrContractMonth="", multiplier="100"):
        self.symbol = symbol
        self.secType = secType
        self.exchange = exchange
        self.currency = currency
        self.conId = conId
        self.strike = strike
        self.right = right
        self.lastTradeDateOrContractMonth = lastTradeDateOrContractMonth
        self.multiplier = multiplier


class _Greeks:
    def __init__(self, d):
        self.impliedVol = d.get("iv")
        self.delta = d.get("delta")
        self.gamma = d.get("gamma")
        self.theta = d.get("theta")
        self.vega = d.get("vega")


class _Horodatage:
    """Un instant qui sait se rendre en ISO — la seule chose qu'on lui demande."""

    def __init__(self, iso):
        self._iso = iso

    def isoformat(self):
        return self._iso


class TickerRejoue:
    """Une cotation rejouée.

    `NaN` est reproduit **fidèlement** : IBKR ne rend pas `None` pour un champ
    absent, il rend `NaN`, et c'est précisément ce que les adaptateurs testent
    (`t.last == t.last`). Un double qui rendrait `None` ferait passer ces gardes
    pour inutiles et laisserait le vrai défaut sous un test vert.
    """

    def __init__(self, d, contract=None):
        self.contract = contract
        self.last = d.get("last", _NAN)
        self.bid = d.get("bid", _NAN)
        self.ask = d.get("ask", _NAN)
        self.close = d.get("close", _NAN)
        self.volume = d.get("volume", _NAN)
        self.marketPrice = d.get("marketPrice", _NAN)
        self.delayedLast = d.get("delayedLast", _NAN)
        self.delayedBid = d.get("delayedBid", _NAN)
        self.delayedAsk = d.get("delayedAsk", _NAN)
        #  L'open interest n'arrive QUE si l'appelant a demande le tick
        #  generique 101. Le double reproduit donc les deux champs separes
        #  d'IBKR — un CALL ne porte pas l'OI des puts — et leur ABSENCE par
        #  `NaN`, comme le vrai. Rendre 0 ferait passer « pas de donnee » pour
        #  « aucun contrat ouvert », deux choses tres differentes pour juger
        #  la liquidite d'une option.
        self.callOpenInterest = d.get("callOpenInterest", _NAN)
        self.putOpenInterest = d.get("putOpenInterest", _NAN)
        g = d.get("greeks")
        self.modelGreeks = _Greeks(g) if g else None
        self.time = _Horodatage(d["time"]) if d.get("time") else None


class _Client:
    def __init__(self, market_data_type, readonly):
        self.marketDataType = market_data_type
        self.readonly = readonly


class _Evenement:
    """`errorEvent` : on ne garde que ce dont `sonder()` se sert — `+=`."""

    def __init__(self):
        self.abonnes = []

    def __iadd__(self, fn):
        self.abonnes.append(fn)
        return self

    def emettre(self, reqId, code, msg=""):
        for fn in list(self.abonnes):
            fn(reqId, code, msg)


class IBRejoue:
    """Un broker rejoué depuis une fixture.

    Il ne porte **aucune** méthode d'écriture — ni transmission, ni annulation,
    ni réservation d'identifiant d'ordre. Ce n'est pas un oubli : c'est la
    moitié de la preuve. Un double qui exposerait ces méthodes permettrait à un
    futur appel d'ordre de passer les tests sans jamais toucher TWS. La liste
    exacte des noms interdits vit dans le banc
    `le banc de rejeu`, pas ici — les écrire dans un
    module de production ferait échouer le gardien anti-ordres, à raison.
    """

    def __init__(self, fixture: dict):
        self.fixture = dict(fixture or {})
        self.client = _Client(self.fixture.get("mode_donnees", 3),
                              self.fixture.get("session_lecture_seule", True))
        self.errorEvent = _Evenement()
        self.appels = []                      # journal, pour les témoins
        self._connecte = True

    # ── cycle de vie ────────────────────────────────────────────────
    def isConnected(self):
        return self._connecte

    def disconnect(self):
        self._connecte = False

    def reqCurrentTime(self):
        self.appels.append("reqCurrentTime")
        return self.fixture.get("heure_broker", "")

    # ── contrats ────────────────────────────────────────────────────
    def qualifyContracts(self, *contrats):
        """Attribue un `conId` à ce que la fixture connaît, et RIEN aux autres.

        Un symbole inconnu ressort sans `conId` : c'est ce qui permet aux tests
        de prouver que les adaptateurs traitent l'absence, au lieu de supposer
        que tout se qualifie toujours.
        """
        self.appels.append("qualifyContracts")
        connus = self.fixture.get("contrats") or {}
        options = self.fixture.get("contrats_options") or {}
        sortis = []
        for c in contrats:
            #  Une option ne se qualifie JAMAIS par son sous-jacent, et le
            #  repli est explicitement interdit : deux strikes de la même
            #  échéance partagent le symbole. Laisser une option inconnue
            #  retomber sur la ligne « AAPL » lui donnerait le conId de
            #  l'action — le produit coterait alors l'action en croyant coter
            #  l'option. Ce défaut a existé dans ce double ; c'est le témoin
            #  `test_une_option_ne_recoit_jamais_le_conId_de_son_sous_jacent`
            #  qui l'a trouvé.
            if _est_option(c):
                d = options.get(_cle_contrat(c))
            else:
                d = connus.get(getattr(c, "symbol", ""))
            if not d:
                continue
            c.conId = d.get("conId", 0)
            c.currency = d.get("currency", getattr(c, "currency", "USD"))
            c.exchange = d.get("exchange", getattr(c, "exchange", "SMART"))
            if not c.conId:
                continue
            sortis.append(c)
        return sortis

    def reqMktData(self, contrat, genericTickList="", snapshot=False,  # noqa: ARG002
                   regulatorySnapshot=False, mktDataOptions=None):     # noqa: ARG002
        """Abonnement rejoue. Le `genericTickList` est CONSERVE, pas ignore.

        L'open interest n'arrive que si `101` a ete demande : un double qui
        servirait l'OI quoi qu'il arrive ferait passer un adaptateur qui ne le
        demande pas pour un adaptateur qui le recoit — exactement le defaut
        que `fetch_contract_details` portait (`open_interest=None` en dur).
        """
        self.appels.append("reqMktData")
        self.ticks_demandes = getattr(self, "ticks_demandes", [])
        self.ticks_demandes.append(str(genericTickList or ""))
        cotations = self.fixture.get("cotations_brutes") or {}
        cle = _cle_contrat(contrat)
        d = dict(cotations.get(cle) or cotations.get(getattr(contrat, "symbol", "")) or {})
        if "101" not in str(genericTickList or ""):
            d.pop("callOpenInterest", None)
            d.pop("putOpenInterest", None)
        return TickerRejoue(d, contract=contrat)

    def cancelMktData(self, contrat):  # noqa: ARG002
        """Fermer ce qu'on a ouvert. Un abonnement laisse ouvert consomme une
        ligne de marche du compte — ressource bornee et partagee."""
        self.appels.append("cancelMktData")

    def sleep(self, secondes):  # noqa: ARG002
        """Le rejeu n'attend pas : les callbacks sont deja la."""
        self.appels.append("sleep")

    def reqTickers(self, *contrats):
        self.appels.append("reqTickers")
        cotations = self.fixture.get("cotations_brutes") or {}
        out = []
        for c in contrats:
            cle = _cle_contrat(c)
            d = cotations.get(cle) or cotations.get(getattr(c, "symbol", ""))
            if d is None:
                continue
            out.append(TickerRejoue(d, contract=c))
        return out

    # ── portefeuille ────────────────────────────────────────────────
    def positions(self):
        self.appels.append("positions")
        return [_PositionRejouee(p) for p in (self.fixture.get("positions_brutes") or [])]

    # ── options ─────────────────────────────────────────────────────
    def reqSecDefOptParams(self, symbol, exchange, secType, conId):  # noqa: ARG002
        self.appels.append("reqSecDefOptParams")
        params = self.fixture.get("expirations_par_symbole") or {}
        lots = params.get(symbol)
        if lots is None:
            return []
        return [_ParamsRejoues(x) for x in lots]


class _PositionRejouee:
    def __init__(self, d):
        self.contract = ContratRejoue(
            symbol=d.get("symbol", ""), secType=d.get("secType", "STK"),
            currency=d.get("currency", "USD"))
        self.position = d.get("position")
        self.avgCost = d.get("avgCost")


class _ParamsRejoues:
    def __init__(self, d):
        self.expirations = list(d.get("expirations") or [])
        self.strikes = list(d.get("strikes") or [])


class PasserelleRejouee:
    """Une passerelle rejouée : `connect()` rend le broker, et c'est tout.

    Même invariant que la vraie façade — `READONLY` est vrai et n'est pas
    paramétrable. Un double « lecture seule optionnelle » permettrait d'écrire
    un test qui prouve l'invariant… en le désactivant.
    """

    READONLY = True

    def __init__(self, fixture: dict):
        self.ib = IBRejoue(fixture)
        self.host = "127.0.0.1"
        self.port = 0
        self._ib = self.ib

    def connect(self):
        return self.ib

    def disconnect(self):
        self.ib.disconnect()


def _est_option(c) -> bool:
    """Un contrat d'option se reconnaît à son `right`, ou à son `secType`."""
    return bool(getattr(c, "right", "")) or getattr(c, "secType", "") == "OPT"


def _cle_contrat(c) -> str:
    """Clé d'une cotation : le symbole pour une action, la ligne complète pour
    une option — sinon deux strikes de la même échéance se recouvriraient."""
    if getattr(c, "secType", "STK") == "OPT" or getattr(c, "right", ""):
        return "%s|%s|%s|%s" % (
            getattr(c, "symbol", ""),
            getattr(c, "lastTradeDateOrContractMonth", ""),
            getattr(c, "strike", ""),
            getattr(c, "right", ""))
    return getattr(c, "symbol", "")


def est_nan(x) -> bool:
    """`NaN` d'IBKR, reconnu sans se faire piéger par un non-flottant."""
    try:
        return math.isnan(float(x))
    except (TypeError, ValueError):
        return False


__all__ = [
    "VERSION_FIXTURE", "MASQUE_COMPTE",
    "masquer_comptes", "anonymiser", "contient_donnee_sensible",
    "enregistrer", "charger",
    "ContratRejoue", "TickerRejoue", "IBRejoue", "PasserelleRejouee",
    "est_nan",
]


# ──────────────────────────────  la capture réelle  ───────────────────────────

def _f(x):
    """Un flottant exploitable, ou `None`. Ne convertit JAMAIS `NaN` en 0."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def capturer(gateway, symboles=("AAPL", "MSFT"), *, avec_options=True) -> dict:
    """Enregistre, depuis un broker RÉEL, de quoi rejouer les adaptateurs.

    On capture le strict nécessaire aux chemins de code des quatre adaptateurs :
    la qualification des contrats, les cotations avec leurs Greeks, les
    positions, et les échéances d'options. Rien d'autre — une fixture qui
    enregistrerait « tout » serait invérifiable et vieillirait mal.

    Les positions sont capturées **brutes** parce que `fetch_positions` doit
    pouvoir s'exécuter dessus ; `anonymiser_fixture` les réduit ensuite à des
    formes non identifiantes. La capture et l'anonymisation restent deux gestes
    séparés : mélangés, on ne saurait plus lequel des deux a échoué.
    """
    Stock = ibkr_gateway.classe('Stock')

    ib = gateway.connect()
    #  readonly=True : la façade a ouvert la session avec ce verrou codé en dur.
    #  Il est réécrit ICI parce que le garde-fou anti-ordres lit la fenêtre qui
    #  SUIT chaque `.connect(` — un verrou qu'il ne voit pas est un verrou qu'il
    #  ne tient pas (même raison que dans `ibkr_link`).
    fixture: dict = {
        "session_lecture_seule": getattr(getattr(ib, "client", None),
                                         "readonly", None),
        "heure_broker": str(ib.reqCurrentTime()),
        "contrats": {},
        "cotations_brutes": {},
        "positions_brutes": [],
        "expirations_par_symbole": {},
    }

    contrats = [Stock(s, "SMART", "USD") for s in symboles]
    qualifies = ib.qualifyContracts(*contrats)
    for c in qualifies:
        fixture["contrats"][c.symbol] = {
            "conId": c.conId, "currency": c.currency, "exchange": c.exchange}

    for t in (ib.reqTickers(*qualifies) if qualifies else []):
        sym = getattr(getattr(t, "contract", None), "symbol", "")
        mg = getattr(t, "modelGreeks", None)
        fixture["cotations_brutes"][sym] = {
            "last": _f(getattr(t, "last", None)),
            "bid": _f(getattr(t, "bid", None)),
            "ask": _f(getattr(t, "ask", None)),
            "close": _f(getattr(t, "close", None)),
            "volume": _f(getattr(t, "volume", None)),
            "time": t.time.isoformat() if getattr(t, "time", None) else "",
            "greeks": ({"iv": _f(getattr(mg, "impliedVol", None)),
                        "delta": _f(getattr(mg, "delta", None)),
                        "gamma": _f(getattr(mg, "gamma", None)),
                        "theta": _f(getattr(mg, "theta", None)),
                        "vega": _f(getattr(mg, "vega", None))} if mg else None),
        }

    #  Lot 2 — les fixtures de rejeu ne capturent plus les positions du
    #  compte : `positions_brutes` reste une liste vide, et les rejeux qui la
    #  lisaient traitent l'absence comme « courtier non lu ».

    if avec_options:
        Option = ibkr_gateway.classe('Option')

        fixture["contrats_options"] = {}
        for c in qualifies:
            try:
                params = ib.reqSecDefOptParams(c.symbol, "", c.secType, c.conId)
            except Exception:  # noqa: BLE001
                continue
            fixture["expirations_par_symbole"][c.symbol] = [
                {"expirations": sorted(p.expirations)[:6],
                 "strikes": sorted(p.strikes)[:12]} for p in params[:1]]

            #  Une poignée de finalistes seulement — l'entonnoir §14. Capturer
            #  une chaîne entière produirait une fixture énorme, lente et
            #  invérifiable, pour prouver exactement la même ligne de code.
            spot = fixture["cotations_brutes"].get(c.symbol, {}).get("last")
            lot = params[0] if params else None
            if not (spot and lot and lot.expirations and lot.strikes):
                continue
            echeance = sorted(lot.expirations)[0]
            proches = sorted(lot.strikes, key=lambda k: abs(float(k) - spot))[:3]
            demandes = [Option(c.symbol, echeance, k, "C", "SMART",
                               currency="USD") for k in proches]
            try:
                qual_opt = [o for o in ib.qualifyContracts(*demandes) if o.conId]
                tick_opt = ib.reqTickers(*qual_opt) if qual_opt else []
            except Exception:  # noqa: BLE001
                continue
            for o, t in zip(qual_opt, tick_opt):
                cle = _cle_contrat(o)
                fixture["contrats_options"][cle] = {
                    "conId": o.conId, "currency": o.currency,
                    "exchange": o.exchange, "multiplier": o.multiplier}
                mg = getattr(t, "modelGreeks", None)
                fixture["cotations_brutes"][cle] = {
                    "last": _f(getattr(t, "last", None)),
                    "bid": _f(getattr(t, "bid", None)),
                    "ask": _f(getattr(t, "ask", None)),
                    "close": _f(getattr(t, "close", None)),
                    "volume": _f(getattr(t, "volume", None)),
                    "time": t.time.isoformat() if getattr(t, "time", None) else "",
                    "greeks": ({"iv": _f(getattr(mg, "impliedVol", None)),
                                "delta": _f(getattr(mg, "delta", None)),
                                "gamma": _f(getattr(mg, "gamma", None)),
                                "theta": _f(getattr(mg, "theta", None)),
                                "vega": _f(getattr(mg, "vega", None))}
                               if mg else None),
                }

    return fixture


def anonymiser_fixture(fixture: dict) -> dict:
    """Une fixture publiable : positions réduites, identifiants masqués.

    Les positions gardent leur FORME (un dictionnaire par ligne, avec les mêmes
    clés) mais perdent leur contenu identifiant : le symbole devient un jeton
    stable `TITRE_1`, la quantité est normalisée. `fetch_positions` s'exécute
    donc entièrement — filtrage des quantités nulles compris — sans que le
    portefeuille soit lisible.
    """
    out = masquer_comptes(dict(fixture or {}))
    lignes = []
    for i, p in enumerate(out.get("positions_brutes") or [], 1):
        try:
            q = float(p.get("position") or 0)
        except (TypeError, ValueError):
            q = 0.0
        lignes.append({"symbol": "TITRE_%d" % i,
                       "position": 0.0 if q == 0 else (1.0 if q > 0 else -1.0),
                       "avgCost": None,
                       "secType": p.get("secType") or "STK",
                       "currency": p.get("currency") or "USD"})
    out["positions_brutes"] = lignes
    out["anonymise"] = True
    return out
