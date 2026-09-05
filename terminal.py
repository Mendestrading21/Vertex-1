"""
terminal.py — TRACK TERMINAL (cockpit web unifié, local, live).

Un seul terminal : watchlist scannée + classée  →  clic sur un titre  →  fiche
détaillée (signaux techniques, score Track, IV / IV-rank, earnings, plan de
trade entrée/stop/cibles, mini-chart)  +  GEX (positionnement dealers) à la
demande. Esthétique sombre pro. Auto-rafraîchi.

Lancer :  py terminal.py   →   http://localhost:5002
Données :  yfinance (différé ~15 min — OK swing). Greeks/GEX = Black-Scholes maison.
⛔ ANALYSE ONLY — aucun ordre, aucune exécution. NOT FINANCIAL ADVICE.
"""
import os
import copy
import hashlib
import json
import time
import threading
from datetime import datetime, timedelta

#  `numpy` n'est plus importé ici : son dernier usage dans ce fichier était
#  `edge_backtest`, partie dans `vertex/engines/edge_validation.py`.
#  `test_terminal_imports` l'a relevé — un import orphelin donne à croire
#  que le monolithe calcule encore ce qu'il ne calcule plus.
import pandas as pd
import yfinance as yf

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))   # charge la clé API si présente (jamais commitée)
except Exception:
    pass

# Moteurs migrés depuis l'ancien package personnel (audit : 5 modules importés
# mais jamais utilisés ici — scoring, pivots, régime physique, timeframes,
# noyau quant — ne sont volontairement plus importés par le monolithe ;
# `strategy.config` les a rejoints au lot 324, il n'était plus consommé).
from vertex.options import legacy_engine as options
from vertex.options import strike_memory as _strike_memory
from vertex.ai import briefs as ai
from vertex.scanner import daily, weekly
from vertex.anomalies import stock_anomalies as anomalies
from vertex.market import sectors
from vertex.market import context as market
from vertex.services.refus_fournisseur import MemoireRefus as _MemoireRefus
from vertex.research import chart_read as research
from vertex.data_sources import fundamentals
from vertex.data_sources import scan_evidence as _scan_evidence
#  Point UNIQUE de decouverte de TWS : ordre des ports et identifiants de
#  session. Voir vertex/data_sources/ibkr_link.py pour ce qu'il corrige.
from vertex.data_sources import ibkr_link as _ibkr_link
from vertex.data_sources import ibkr_session as _ibkr_session  # noqa: E402
from vertex.engines import decide as engine
from vertex.engines import scorecard as ibkr
from vertex.strategy import legacy_adapter as strategy
from vertex.engines import committee

DAILY_PREV_PATH = os.path.join(os.path.dirname(__file__), 'daily_prev.json')  # baseline diff jour/jour
#  Le chemin du snapshot hebdo vit dans `vertex/app/weekly_selection.py`.
#  ATTENTION : y recopier `os.path.dirname(__file__)` le ferait pointer vers
#  vertex/app/ — l'ancien snapshot ne serait plus jamais relu, SANS erreur.
from vertex.app.weekly_selection import CHEMIN as WEEKLY_PATH  # noqa: E402

# ─── Univers, constantes & config : extraits en modules dédiés (refonte institutionnelle) ───
#     Responsabilité unique par module ; terminal.py ne fait plus que consommer la donnée.
from vertex.data.universe import *  # noqa: F401,F403  (tickers, indices, secteurs, industries)
from vertex.data.constants import BENCH, R, BUILD, REFRESH_SEC, DEMO_UNIVERSE_N  # noqa: F401
from vertex.app.config import IBKR_ENABLED, DEMO_MODE  # noqa: F401
from vertex.services import persist as _persist
from vertex.observability.metrics import METRICS  # télémétrie perf (timers scan) — §37
from vertex.services import live_engine as _live
from vertex.services import news_plus as _news_plus
from vertex.engines import track_record as _track
from vertex.engines import analysis as _analysis
from vertex.engines import backtest as _backtest
from vertex.engines import swing as _swing
from vertex.engines import strategy_fit as _strategy_fit
from vertex.engines import stats as _stats
from vertex.app.state import scan_state, weekly_state, news_state, cal_state
#  #779 — CACHES D'EXECUTION : proprietaire et politique de fraicheur declares
#  dans `vertex/app/caches.py` (QUALITY_STANDARD §8). Les objets sont les MEMES :
#  mutes en place, jamais reassignes, donc l'identite est preservee.
from vertex.app import lifecycle as _lifecycle
from vertex.app.caches import (          # noqa: F401  (relies par leur nom)
    _STOOQ_CACHE, _STOOQ_TTL, _SOURCE_BUDGET_STATE, _CORR_BENCH,
    _ibkr_cache, _IDX_IBKR, _IDX_META, _live_quotes, _live_meta,
)
from vertex.app.routes import desk as _desk
from vertex.app.routes import decision_api as _decision_api
from vertex.data import demo as _demo
from vertex.data import company as _company
from vertex.services import market_clock as _market_clock

#  ── FABRIQUE FLASK CANONIQUE (#779, gate G1) ─────────────────────────────
#  `Flask(__name__)`, la configuration de session, le fournisseur JSON sur
#  (NaN -> null), la mesure de latence, le verrou d'acces, les en-tetes de
#  securite, les pages d'erreur et la compression vivaient ICI, disperses entre
#  les lignes 88 et 1865. Aucun de ces blocs ne dependait de l'etat du
#  monolithe : ils sont desormais tenus par `vertex/app/factory.py`.
#
#  LE PIEGE, MESURE : `Flask(__name__)` ecrit dans `vertex/app/` ferait deriver
#  `root_path` vers ce dossier, donc `static_folder` vers un chemin inexistant
#  — les deux fichiers reellement servis depuis `static/` (chart.umd.min.js,
#  icon-180.png) partiraient en 404 SANS erreur au demarrage. La fabrique fixe
#  donc `root_path` explicitement.
from vertex.app import factory as _factory  # noqa: E402
from vertex.app import ibkr_state as _ibkr_state  # noqa: E402
from vertex.app import rescan_gate as _rescan_gate  # noqa: E402
from vertex.app import weekly_selection as _weekly_selection  # noqa: E402
from vertex.app.caches import _OPTALL_CACHE  # noqa: E402
app = _factory.create_app()

# ─────────────────────────────────────────────────────────────────────────────
# 🔒 CODE D'ENTRÉE (verrou d'accès) — OPTIONNEL, activé par variable d'env.
#   • Mets  VERTEX_CODE=tonCode  → toute l'app est protégée par un code d'entrée.
#   • Sans VERTEX_CODE défini    → aucun verrou (comportement d'origine, démo ouverte).
#   • Session signée (cookie) valable 30 jours ; anti-force-brute par IP.
#   • Recommandé aussi : VERTEX_SECRET=une_longue_chaine_aléatoire (sinon dérivée du code).
# ─────────────────────────────────────────────────────────────────────────────
# Source unique de la config d'accès : vertex/app/config.py.
# Le Blueprint auth (login/logout + garde globale + anti-force-brute) et la
# configuration de session sont posés par `_factory.create_app()`, EN PREMIER :
# le `before_request` du verrou doit pouvoir refuser une requête destinée à
# n'importe quel blueprint. AUTH_ON reste lu ici — plusieurs vues s'en servent.
from vertex.app.config import VERTEX_CODE, AUTH_ON, SECRET_KEY  # noqa: E402,F401


# scan_state : état partagé du scan — domicile unique dans vertex/app/state.py.
# Importé en tête ; rempli ci-dessous (caches disque) puis muté EN PLACE par la boucle.

# ─── CACHES PERSISTANTS SUR DISQUE (survivent aux redémarrages → anti-throttle) ───
# yfinance throttle les .info/option_chain en masse → après chaque restart tout retombait
# à 0. On persiste fondamentaux + options + macro sur disque : rechargés instantanément
# au démarrage, remplis GRADUELLEMENT en fond (petits lots) → jamais 0.
# Source unique de la persistance JSON : vertex/services/persist.py (Ch. II).
_load_json = _persist.load_json
_save_json = _persist.save_json


# Médianes de valorisation par secteur : source unique dans vertex/engines/stats.py.
_recompute_sectors = _stats.sector_medians


_FUND_CACHE = _load_json('fund_cache.json', {})     # {sym: {...fondamentaux...}} — accumulé


def _seed_fund_from_company():
    """Complète les TROUS du cache fondamentaux avec le profil entreprise RÉEL
    (company_cache : pe/forward_pe/marge/croissance/ROE, couverture ~518 titres).
    Le job IBKR (tick 258) et yfinance restent prioritaires : on ne remplit QUE
    les champs None — jamais d'écrasement d'une valeur fraîche. Sans ce seeding,
    le cache restait creux (titres présents mais tout-null, donc jamais re-tentés)
    → valorisation/médianes/P&L sectoriels privés de données réelles."""
    try:
        prof = _company._load()
    except Exception:
        return 0
    n = 0
    for sym, cp in (prof or {}).items():
        if not isinstance(cp, dict):
            continue
        cur = _FUND_CACHE.get(sym) or {'sector': _GICS_SECTOR.get(sym),
                                       'industry': None, 'name': cp.get('name')}
        div = cp.get('dividend')
        m = {'pe': cp.get('pe'), 'fwd_pe': cp.get('forward_pe'), 'peg': cp.get('peg'),
             'margin': cp.get('margin'), 'growth': cp.get('rev_growth'),
             'mcap': cp.get('mcap'), 'roe': cp.get('roe'),
             'div': (div / 100.0) if isinstance(div, (int, float)) else None}
        changed = False
        for k, v in m.items():
            if v is not None and cur.get(k) is None:
                cur[k] = v
                changed = True
        if changed:
            cur.setdefault('sector', _GICS_SECTOR.get(sym))
            _FUND_CACHE[sym] = cur
            n += 1
    if n:
        _save_json('fund_cache.json', _FUND_CACHE)
    return n


_seed_fund_from_company()                            # données réelles dès le boot
_OPT_CACHE = _load_json('options_cache.json', {})   # {'board':[...], 'ts':...}
if _FUND_CACHE:                                      # publie le cache dès le démarrage → zéro attente
    scan_state['fundamentals'] = {'by_sym': _FUND_CACHE, 'by_sector': _recompute_sectors(_FUND_CACHE)}
if _OPT_CACHE.get('board'):
    scan_state['options_board'] = _OPT_CACHE['board']
    scan_state['options_as_of'] = _OPT_CACHE.get('ts')
scan_state['macro'] = _load_json('macro_cache.json', [])
scan_state['radar'] = _load_json('radar_cache.json', None)   # radar marché IBKR (persistant)


#  Les deux coerceurs numeriques `_i`/`_f` sont partis avec leur unique
#  appelant, dans `vertex/options/pack.py`.


# Black-Scholes : source unique dans vertex/options/legacy_engine.py (dé-duplication — cf. audit).


# Horloge de marché US : source unique dans vertex/services/market_clock.py.
market_status = _market_clock.market_status


# ─── analyse par titre (sur OHLCV daily) ─────────────────────────────────
# Cœur analytique (OHLCV → fiche technique) : source unique dans vertex/engines/analysis.py.
analyse = _analysis.analyse


# Forward-test papier : source unique dans vertex/engines/backtest.py.
backtest = _backtest.backtest


# ─── SOURCE DE SECOURS : STOOQ (EOD gratuit, NON bloqué sur les IP cloud/Render) ──
#  DÉPLACÉ (strangler) vers `vertex/data_sources/stooq.py` : une source de
#  données n'a pas sa place dans l'adaptateur historique. Les trois noms sont
#  réexportés ici parce que deux bancs remplacent `terminal._stooq_download`
#  par une doublure, et que `_download_universe` le résout dans CES globales.
from vertex.data_sources.stooq import (       # noqa: E402,F401
    STOOQ_REQUEST_TIMEOUT_SECONDS, _STOOQ_IDX,
    _stooq_symbol, _stooq_one, _stooq_download,
)

YFINANCE_BATCH_TIMEOUT_SECONDS = 10
# symboles matières premières / crypto (bande sous les indices) — yfinance
_COMMO = [('GC=F', 'Or', '🥇'), ('SI=F', 'Argent', '🥈'), ('BTC-USD', 'Bitcoin', '₿'),
          ('CL=F', 'WTI', '🛢️'), ('BZ=F', 'Brent', '🛢️')]
# MACRO / TAUX : rendements du Trésor US + dollar (yfinance, fiable). kind 'y'=rendement %, 'p'=indice.
_MACRO_TK = [('^IRX', 'Taux 3 mois', '%', 'y'), ('^FVX', 'Taux 5 ans', '%', 'y'),
             ('^TNX', 'Taux 10 ans', '%', 'y'), ('^TYX', 'Taux 30 ans', '%', 'y'),
             ('DX-Y.NYB', 'Dollar (DXY)', '', 'p')]



# ── LOT 2 : cache mémoire du téléchargement quotidien (TTL selon la séance) ────
# La barre EOD ne change pas hors séance → re-télécharger 1 an × ~517 titres toutes
# les 120 s est pur gaspillage (et déclenche les 429 de Yahoo). Cache par ticker :
# séance ouverte = TTL court (barre intraday partielle fraîche) ; fermée = TTL long.
# VERTEX_YF_TTL=0 désactive (comportement historique) ; N force un TTL fixe.
_YF_CACHE = {}          # {ticker: (DataFrame, ts)}
_YF_TTL_OPEN = 90       # < REFRESH_SEC=120 : garde la barre du jour fraîche en séance
_YF_TTL_CLOSED = 900    # 15 min hors séance : barre figée, tue la tempête + les 429


#: Reglages refuses, pour ne les signaler qu'une fois par valeur.
_TTL_INVALIDE: dict = {}


def _analyse_fp(df, bench_ret, fund):
    """Empreinte des ENTRÉES d'`analyse()` — la fonction qui manquait.

    `vertex-live` a écrit le bloc de mémoïsation de `_analyse_one` en appelant
    `_analyse_fp(df, bench_ret, _fund)`. **Cette fonction n'a jamais été
    écrite** — ni sur `main`, ni sur `vertex-live`, ni ailleurs dans l'arbre.

    Conséquence mesurée le 26 août 2026, mode démo, douze titres :

    ```text
    rows 0   scan_error None   titres_en_echec 12/12
    NameError: name '_analyse_fp' is not defined
    ```

    Chaque symbole levait `NameError` à sa première ligne utile, `_safe_one`
    l'avalait, et le scan rendait **zéro ligne en se déclarant sain**. C'est la
    signature exacte du desk : `n/d` partout, `/healthz` « ok ».

    ## Ce que l'empreinte doit couvrir

    Exactement les trois entrées d'`analyse(df, bench_ret, fund=…)`, et rien de
    plus. Une empreinte trop large fait manquer tous les caches ; une empreinte
    trop étroite **rend un résultat périmé pour une entrée qui a changé** — et
    ce second défaut est silencieux, donc bien pire.

    * `df` : la dernière valeur de chaque colonne, plus sa longueur et la
      dernière date. Une barre neuve change la longueur **et** la dernière
      clôture ; une révision de la dernière barre change la clôture. Hacher les
      milliers de barres coûterait plus cher que le calcul qu'on évite.
    * `bench_ret` : sa longueur et sa dernière valeur — le régime bouge avec.
    * `fund` : le dictionnaire entier, trié, car chaque champ entre dans le
      score fondamental.

    En cas de doute — une structure qu'on ne sait pas lire — on rend `None`, et
    l'appelant recalcule. **Un cache qui échoue doit coûter du temps, jamais de
    la justesse.**
    """
    try:
        h = hashlib.blake2b(digest_size=16)
        h.update(b'v1')
        n = len(df)
        h.update(str(n).encode())
        if n:
            derniere = df.index[-1]
            h.update(str(derniere).encode())
            for col in sorted(map(str, df.columns)):
                v = df[col].iloc[-1]
                h.update(('%s=%r' % (col, v)).encode('utf-8', 'replace'))
        if bench_ret is not None:
            h.update(('b%d' % len(bench_ret)).encode())
            if len(bench_ret):
                h.update(repr(bench_ret.iloc[-1]).encode('utf-8', 'replace'))
        if fund:
            for k in sorted(map(str, fund)):
                h.update(('%s=%r' % (k, fund[k])).encode('utf-8', 'replace'))
        return h.hexdigest()
    except Exception:
        #  Pas d'empreinte -> pas de memo. `None != None` est FAUX en Python,
        #  donc on rend une valeur unique plutot que `None` : sans quoi deux
        #  echecs successifs se prendraient pour un hit et l'on servirait le
        #  resultat d'un AUTRE titre.
        return object()


#: Memo du scan : {SYM: (empreinte_des_entrees, sortie_PURE_de_analyse)}.
#:
#:  CE NOM ETAIT EMPLOYE ET JAMAIS DEFINI. `_one(sym)` — le worker qui analyse
#:  UN titre — lisait `_ANALYSE_MEMO.get(sym)` a sa premiere ligne utile. Chaque
#:  symbole levait donc `NameError`, le worker rendait `None`, et le scan
#:  rendait **zero ligne en se declarant sain** :
#:
#:      rows 0   scanned None   scan_error None
#:
#:  Mesure faite le 26 aout 2026 sur douze titres en mode demo. C'est la
#:  signature exacte de ce que montre le desk : des tuiles `n/d` partout et un
#:  `/healthz` qui repond « ok ».
#:
#:  Le memo evite de recalculer `analyse()` quand les entrees n'ont pas bouge
#:  (meme empreinte). Un dict de module suffit : il ne survit pas au processus,
#:  et un scan froid le remplit en un passage.
_ANALYSE_MEMO: dict = {}


def _yf_ttl():
    env = os.environ.get('VERTEX_YF_TTL')
    if env is not None:
        try:
            return max(0, int(env))     # 0 = cache off ; N = TTL fixe manuel
        except ValueError:
            #  Un reglage qui ne prend pas SANS LE DIRE est pire qu'un reglage
            #  absent : l'utilisateur croit avoir agi. On le nomme une fois.
            if not _TTL_INVALIDE.get(env):
                _TTL_INVALIDE[env] = True
                log.warning('VERTEX_YF_TTL=%r ignore (entier attendu) : '
                            'le TTL automatique reste actif', env)
    try:
        return _YF_TTL_OPEN if market_status().get('open') else _YF_TTL_CLOSED
    except Exception:
        return _YF_TTL_CLOSED


def _download_universe(tickers, period='1y', chunk=50):
    """Télécharge l'univers PAR LOTS (plus robuste/rapide qu'un seul gros appel
    sur le plan gratuit). Renvoie un dict {ticker: DataFrame} ; un lot ou un
    ticker en échec est simplement ignoré (jamais de plantage global).
    Si yfinance échoue (ex: Yahoo bloque l'IP du serveur cloud), bascule
    automatiquement sur Stooq pour les tickers manquants.
    Cache mémoire par ticker (Lot 2) : sert depuis le cache les tickers encore
    frais selon la séance, ne télécharge que les périmés/manquants."""
    ttl = _yf_ttl()
    now = time.time()
    frames = {}
    #  ── TETE DE CHAINE : IBKR ────────────────────────────────────────────
    #  Le courtier d'abord, le web ensuite. Les barres IBKR sont celles du
    #  compte qui detient les positions : les memes que les cotations, les
    #  chaines d'options et le P&L. Faire cohabiter deux origines pour un
    #  meme titre, c'est accepter que le scan et l'ecran ne parlent pas du
    #  meme cours.
    #
    #  Ce qu'IBKR ne sert pas reste au repli, et c'est voulu : un symbole
    #  qu'il ne connait pas (mesure : AVB) ou un compte sans abonnement
    #  doivent produire une ABSENCE ici, pas un trou dans le scan. yfinance
    #  puis stooq ramassent exactement ce qui manque.
    ibkr_n = 0
    if IBKR_ENABLED and not DEMO_MODE:
        try:
            import asyncio as _aio
            from vertex.data_sources.ibkr_historical import fetch_universe_bars
            try:                       # le scan tourne dans un thread de fond
                _aio.get_event_loop()
            except RuntimeError:
                _aio.set_event_loop(_aio.new_event_loop())
            duree = {'1y': '1 Y', '6mo': '6 M', '2y': '2 Y'}.get(period, '1 Y')
            recus, rapport = fetch_universe_bars(tickers, duration=duree)
            frames.update(recus)
            ibkr_n = len(recus)
            if rapport.get('inconnus') or rapport.get('vides'):
                _live_meta['hist_repli'] = len(rapport['inconnus']) + len(rapport['vides'])
        except Exception as _e:        # TWS absent, refus, coupure : on continue
            _live_meta['hist_err'] = '%s: %s' % (type(_e).__name__, _e)

    manquants = [t for t in tickers if t not in frames]
    bad_batches = 0
    _abandonnes: list = []
    for i in range(0, len(manquants), chunk):
        part = manquants[i:i + chunk]
        try:
            dl = yf.download(part, period=period, interval='1d', progress=False,
                             auto_adjust=True, group_by='ticker', threads=True,
                             timeout=YFINANCE_BATCH_TIMEOUT_SECONDS)
        except Exception:
            dl = None
        if dl is None or len(dl) == 0:
            # BACKOFF anti-throttle (429) : après 3 lots vides d'affilée, Yahoo bloque
            # l'IP → inutile d'insister, on passe direct au filet Stooq (caché 6 h)
            bad_batches += 1
            if bad_batches >= 3:
                #  L'abandon CESSE D'ETRE MUET. Il emportait jusqu'ici tout le
                #  reste de la file sans que rien ne le dise : le Dashboard
                #  affichait « n/d » et le scan annoncait « aucune erreur ».
                #  Un abandon qui ne se nomme pas se lit comme une absence de
                #  donnee chez la source.
                _abandonnes.extend(manquants[i:])
                break
            time.sleep(2 * bad_batches)
            continue
        bad_batches = 0
        for t in part:
            try:
                df = dl if len(part) == 1 else dl[t]
                if df is not None and not df.dropna().empty:
                    frames[t] = df
                    if ttl > 0:
                        _YF_CACHE[t] = (df, now)   # met en cache le frais
            except Exception:
                continue
    # FILET DE SECOURS : tout ce que Yahoo n'a pas donné → Stooq (cloud-friendly)
    yahoo_n = len(frames)
    missing = [t for t in tickers if t not in frames]
    if missing:
        try:
            frames.update(_stooq_download(missing))
        except Exception:
            pass
    stooq_n = len(frames) - yahoo_n
    #  RETRANCHER AVANT de juger yfinance : `yahoo_n` comptait le cumul, part
    #  IBKR comprise. Juge sur le cumul, le budget se declarait « disponible »
    #  alors que Yahoo n'avait rien servi — un diagnostic faux, et faux dans le
    #  sens rassurant.
    yahoo_n -= ibkr_n
    _SOURCE_BUDGET_STATE['yfinance'] = 'AVAILABLE' if yahoo_n else 'UNAVAILABLE'
    #  La provenance NOMME chaque contributeur. « ibkr+yfinance » n'est pas
    #  « ibkr » : l'ecran doit pouvoir dire qu'une partie de l'univers n'a pas
    #  ete servie par le courtier, sinon le repli devient invisible — et un
    #  repli invisible est un mensonge de source (QUALITY_STANDARD §1).
    contributeurs = [n for n, c in (('ibkr', ibkr_n), ('yfinance', yahoo_n),
                                    ('stooq', stooq_n)) if c > 0]
    scan_state['source'] = '+'.join(contributeurs) if contributeurs else 'unavailable'
    scan_state['source_detail'] = {'ibkr': ibkr_n, 'yfinance': yahoo_n,
                                   'stooq': stooq_n, 'univers': len(tickers)}
    #  CE QUI A ETE ABANDONNE, et pourquoi. Le backoff anti-429 coupait la file
    #  en silence : le Dashboard affichait « n/d » pendant que le scan annoncait
    #  « aucune erreur ». Un abandon qui ne se nomme pas se lit comme une
    #  absence de donnee chez la source — et on cherche alors du mauvais cote.
    #
    #  `restants` compte ce qui n'a ete servi NI par Yahoo, NI par Stooq : les
    #  abandonnes que le filet de secours a rattrapes ne manquent plus.
    restants = [t for t in _abandonnes if t not in frames]
    scan_state['abandon_debit'] = {
        'apres_lots_vides': bool(_abandonnes),
        'symboles_abandonnes': len(_abandonnes),
        'restes_sans_donnee': len(restants),
        'exemples': restants[:8],
        'motif': ('trois lots vides d affilee : Yahoo limite le debit, la file '
                  'est coupee et le filet Stooq prend le relais'),
        'read_only': True,
    } if _abandonnes else None
    return frames


_demo_universe = _demo.demo_universe
_demo_options_board = _demo.demo_options_board


_annotate_swing = _swing.annotate


def _generation(etat):
    """Génération du prochain scan — monotone, portée par chaque publication.
    Sans try/except ni repli chiffré (invariant lot 385) : un `scan_gen`
    corrompu repart de zéro par typage, pas par un chiffre posé en except."""
    prec = etat.get('scan_gen')
    return (prec if isinstance(prec, int) and not isinstance(prec, bool) else 0) + 1


def _publier(etat, phase, gen, bloc):
    """Publication ATOMIQUE du scan (lot 42). UN seul dict.update C-level par
    phase — aucun entrelacement de bytecode entre les clés d'un même bloc —
    estampillé `scan_gen` + `scan_phase` ('partiel' → 'complet' ; 'erreur').
    Les lecteurs (routes Flask, autres threads) savent CE qu'ils lisent :
    avant, les dérivés (analytics, réconciliation, tilt…) étaient posés à
    l'unité entre deux générations — un état déchiré, indétectable."""
    b = dict(bloc)
    b['scan_gen'] = gen
    b['scan_phase'] = phase
    etat.update(b)


def _scan_once():
    try:
        _gen = _generation(scan_state)
        # En DÉMO : on ne scanne que 20 titres → rapide sur le CPU bridé du cloud,
        # suffisant pour visualiser toutes les données. Hors démo : univers complet.
        syms_scan = UNIVERSE[:DEMO_UNIVERSE_N] if DEMO_MODE else UNIVERSE
        #  LE CONTEXTE DE MARCHE PASSE EN TETE, et ce n'est pas cosmetique.
        #
        #  Mesure du 26 aout 2026, sur le desk de l'utilisateur : Dow, S&P,
        #  Nasdaq, Russell, VIX, or, petrole, argent, BTC, ETH — TOUTES les
        #  tuiles d'en-tete du Dashboard a « n/d », pendant que le scan
        #  annoncait 513 titres et aucune erreur.
        #
        #  La cause : ces ~16 symboles etaient les DERNIERS de la file, apres
        #  les 513 actions. Or `_download_universe` abandonne tout le reste
        #  apres trois lots vides d'affilee (backoff anti-429) — donc quand
        #  Yahoo limite le debit en fin de scan, ce sont exactement eux qui
        #  sont sacrifies. Verifie le meme jour : yfinance rendait pourtant
        #  ^GSPC 7680,36, ^IXIC 26113,75, ^DJI 53547,62, ^VIX 15,44.
        #
        #  Seize symboles portent la lecture d'ensemble de la page d'accueil ;
        #  513 en portent une ligne chacun. Les servir en premier ne coute rien
        #  et garantit l'en-tete meme quand la queue tombe.
        _contexte = ([BENCH, '^VIX', '^GSPC', '^IXIC', '^DJI', '^RUT']
                     + [c[0] for c in _COMMO] + [m[0] for m in _MACRO_TK])
        _syms = _contexte + [t for t in syms_scan if t not in _contexte]
        with METRICS.timer('scan.download'):
            if DEMO_MODE:
                data = _demo_universe(_syms)
            else:
                data = _download_universe(_syms)
        if BENCH not in data:
            _publier(scan_state, 'erreur', _gen, {
                'error': 'market_data_unavailable',
                **({'source': 'demo'} if DEMO_MODE else {}),
                'source_health': {
                    'scan': 'DEGRADED', 'market': 'UNAVAILABLE',
                    'options': 'NOT_COLLECTED', 'fundamentals': 'NOT_COLLECTED',
                }})
            return
        bc = data[BENCH]['Close'].dropna()
        bench_ret = (float(bc.iloc[-1]) / float(bc.iloc[-63]) - 1) if len(bc) > 63 else 0.0
        rows, detail = [], {}
        _funds = scan_state.get('fundamentals') or {}   # LOT 3 : snapshot unique (cohérent + thread-safe sous //)

        def _analyse_one(sym):
            """Calcul complet d'UN titre — PUR (lit data/bench_ret/_funds en lecture seule,
            écrit un objet local). Renvoie (row, sym, detail) ou None. Base du scan //."""
            df = data[sym].dropna()
            if len(df) < 60:
                return None
            _fsy = (_funds.get('by_sym') or {}).get(sym) or {}
            _fsec = (_funds.get('by_sector') or {}).get(_fsy.get('sector')) or {}
            _fund = ({**_fsy, 'sector_median_pe': _fsec.get('median_pe'),
                      'sector_median_margin': _fsec.get('median_margin'),
                      'sector_median_growth': _fsec.get('median_growth')} if _fsy else {})
            # secteur GICS statique TOUJOURS injecté → profil offensif/défensif fiable même sans fondamentaux live
            _fund.setdefault('sector', _GICS_SECTOR.get(sym) or _INDUSTRY_MAP.get(sym))
            _fp = _analyse_fp(df, bench_ret, _fund or None)
            _memo = _ANALYSE_MEMO.get(sym)
            if _memo is not None and _memo[0] == _fp:
                d = copy.deepcopy(_memo[1])   # hit : copie privée d'un calcul déjà identique (byte-identique)
                METRICS.inc('scan.memo_hits')
            else:
                with METRICS.timer('scan.symbol'):
                    d = analyse(df, bench_ret, fund=(_fund or None))   # vrais fondamentaux → score fondamental réel (sinon proxy)
                _ANALYSE_MEMO[sym] = (_fp, copy.deepcopy(d))   # stocke la sortie PURE (avant enrichissements ci-dessous)
                METRICS.inc('scan.memo_miss')
            d['chart_read'] = research.chart_read(d)   # analyse graphique FR (cartes Screener + modale)
            d['thesis'] = research.thesis(d)            # synthèse Vertex décisive (fusion signaux + comment jouer)
            d['sector'] = _GICS_SECTOR.get(sym)         # secteur GICS → contexte transversal / pairs (DecisionStack)
            _clf = df['Close'].dropna()                # perf multi-horizons (Équipe semaine/mois/trim./année)

            def _pf(nn, _c=_clf):
                return round((float(_c.iloc[-1]) / float(_c.iloc[-1 - nn]) - 1) * 100, 1) if len(_c) > nn else None
            d['perf_w'], d['perf_m'], d['perf_q'], d['perf_y'] = _pf(5), _pf(21), _pf(63), _pf(252)
            d['hot'] = sym in TREND_SET   # badge 🔥 UI — NE PAS écraser d['trend'] (score 0-100 lu par engine/weekly)
            _vx = d.get('vertex') or {}
            _sub = d.get('sub') or {}
            _kel = _vx.get('kelly') or {}
            _mc = _vx.get('mc') or {}
            _evb = _vx.get('ev') or {}
            row = {'symbol': sym, 'price': d['price'], 'change': d['change'],
                             'score': d['score'], 'grade': d['grade'], 'verdict': d['verdict'],
                             'perf_w': d.get('perf_w'), 'perf_m': d.get('perf_m'),
                             'perf_q': d.get('perf_q'), 'perf_y': d.get('perf_y'),
                             'sigcount': d['sigcount'], 'trend': sym in TREND_SET,
                             'sector': _GICS_SECTOR.get(sym),   # secteur GICS statique (page Secteurs)
                             'industry': _INDUSTRY_MAP.get(sym),   # industrie fine statique (~55 groupes)
                             # contexte titre (déjà calculé, jamais surfacé en watchlist/cockpit)
                             'regime': d.get('regime'), 'rsi': d.get('rsi'), 'rs': d.get('rs'),
                             'rvol': d.get('volx'), 'setup_quality': d.get('setup_quality'),
                             'ext_atr': d.get('ext_atr'), 'rsi_div': d.get('rsi_div'), 'pos52': d.get('pos52'),
                             'profile': d.get('profile'), 'profile_hint': d.get('profile_hint'),
                             'squeeze': d.get('squeeze'), 'breakout': d.get('breakout'),
                             'accumulation': d.get('accumulation'), 'distribution': d.get('distribution'), 'pullback': d.get('pullback'),
                             'anomalies': d.get('anomalies'), 'anomaly_score': d.get('anomaly_score'),
                             'anomaly_lvl': d.get('anomaly_lvl'), 'gap_pct': d.get('gap_pct'), 'zscore': d.get('zscore'),
                             'physics': d.get('physics'), 'mtf': d.get('mtf'),
                             # VERTEX — noyau quant complet (edge, sous-scores, Kelly, Monte-Carlo, EV, drapeaux)
                             'vx_edge': _vx.get('edge'), 'vx_verdict': _vx.get('verdict'),
                             'vx_pwin': _vx.get('p_win'), 'vx_kelly': _kel.get('pct'),
                             'vx_tq': _vx.get('trend_quality'), 'vx_eq': _vx.get('entry_quality'),
                             'vx_rr': _vx.get('rr'), 'vx_em': _vx.get('expected_move'),
                             'vx_inst': _vx.get('institutionality'), 'vx_ext': _vx.get('extension_penalty'),
                             'vx_asym': _vx.get('asymmetry'),
                             'vx_tp1': _mc.get('p_hit_tp1'), 'vx_tp1first': _mc.get('p_tp1_first'),
                             'vx_stopfirst': _mc.get('p_stop_before_tp1'), 'vx_ev': _evb.get('ev_pct'),
                             'vx_notrade': _vx.get('no_trade'), 'vx_flags': _vx.get('risk_flags') or [],
                             # sous-scores SCORING (décompose pourquoi le score global = X)
                             'st_tech': _sub.get('technical'), 'st_mom': _sub.get('momentum'),
                             'st_fund': _sub.get('fundamental'), 'st_risk': _sub.get('risk'),
                             'st_conf': _sub.get('confidence'), 'st_fproxy': _sub.get('fundamental_is_proxy')}
            return (row, sym, d)

        _echecs_titres: dict = {}

        def _safe_one(sym):
            try:
                return _analyse_one(sym)
            except Exception as _e:
                #  « un titre en echec est simplement ignore » : vrai pour UN
                #  titre, faux quand la cause est commune. Un defaut partage —
                #  un nom absent, une colonne renommee — fait tomber les 513 d'un
                #  coup, et le scan rendait alors ZERO ligne en se declarant
                #  sain : `rows 0, scanned None, scan_error None`. C'est
                #  exactement ce que le desk affichait, `n/d` partout, pendant
                #  que /healthz repondait « ok ».
                #
                #  Le titre reste ignore ; ce qui change, c'est qu'on sait
                #  desormais combien, lesquels, et pourquoi.
                _echecs_titres[str(sym)] = '%s: %s' % (
                    type(_e).__name__, str(_e)[:120])
                return None

        _t_compute = time.monotonic()   # LOT 0 : durée totale du calcul par symbole (télémétrie perf)
        _workers = int(os.environ.get('VERTEX_SCAN_WORKERS',
                                       str(min(8, max(1, (os.cpu_count() or 2) - 1)))))  # laisse 1 cœur au serveur web
        if _workers > 1 and len(syms_scan) > 1:
            # LOT 3 : calcul par titre EN PARALLÈLE (map-and-collect → zéro mutation partagée).
            # analyse()/research.* pures + RNG Monte-Carlo/bootstrap LOCAL ⇒ byte-identique au mode
            # série (repli VERTEX_SCAN_WORKERS=1). numpy/pandas relâchent le GIL ⇒ vrai parallélisme.
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=_workers) as _ex:
                _results = list(_ex.map(_safe_one, syms_scan))
        else:
            _results = [_safe_one(s) for s in syms_scan]
        #  Un scan qui perd TOUS ses titres n'est pas un scan sain.
        _te = ({'n': len(_echecs_titres), 'total': len(syms_scan),
                'exemples': dict(list(_echecs_titres.items())[:5])}
               if _echecs_titres else None)
        for _r in _results:   # assemblage sur le thread principal (ordre préservé par map ; rows re-trié après)
            if _r is None:
                continue
            _row, _sym, _d = _r
            rows.append(_row)
            detail[_sym] = _d
        METRICS.timing('scan.compute_all', (time.monotonic() - _t_compute) * 1000)  # LOT 0
        rows.sort(key=lambda x: x['score'], reverse=True)
        breadth = round(sum(1 for r in rows if r['verdict'] == 'BUY') / len(rows) * 100) if rows else 0
        spy = ({'price': round(float(bc.iloc[-1]), 2),
                'change': round((float(bc.iloc[-1]) / float(bc.iloc[-2]) - 1) * 100, 2)} if len(bc) > 1 else None)
        # INDICES PRINCIPAUX (bande du haut). Le S&P 500 porte en plus une série
        # de 120 séances + MM20/50/200 calculées ICI (serveur) : c'est le graphique
        # héros du Dashboard quand SPY n'est pas dans l'univers scanné — vraie
        # série d'indice, jamais un titre proxy.
        indices = []
        for _tk, _nm in [('^GSPC', 'S&P 500'), ('^IXIC', 'Nasdaq'), ('^DJI', 'Dow Jones'), ('^RUT', 'Russell 2000'), ('^VIX', 'VIX')]:
            try:
                _cc = data[_tk]['Close'].dropna()
                _e = {'name': _nm, 'price': round(float(_cc.iloc[-1]), 2),
                      'change': round((float(_cc.iloc[-1]) / float(_cc.iloc[-2]) - 1) * 100, 2),
                      'spark': [round(float(x), 2) for x in _cc.tail(24).values],
                      'vix': _tk == '^VIX'}
                if _tk == '^GSPC':
                    def _ser(s):
                        return [None if x != x else round(float(x), 2)
                                for x in s.tail(120).values]
                    _e['series'] = _ser(_cc)
                    _e['dates'] = [str(d.date()) for d in _cc.tail(120).index]
                    _e['ema20'] = _ser(_cc.ewm(span=20, adjust=False).mean())
                    _e['sma50'] = _ser(_cc.rolling(50).mean())
                    _e['sma200'] = _ser(_cc.rolling(200).mean())
                indices.append(_e)
            except Exception:
                pass
        # MATIÈRES PREMIÈRES / CRYPTO (bande sous les indices)
        commodities = []
        for _tk, _nm, _ic in _COMMO:
            try:
                _cc = data[_tk]['Close'].dropna()
                commodities.append({'name': _nm, 'icon': _ic, 'price': round(float(_cc.iloc[-1]), 2),
                                    'change': round((float(_cc.iloc[-1]) / float(_cc.iloc[-2]) - 1) * 100, 2),
                                    'spark': [round(float(x), 2) for x in _cc.tail(24).values]})
            except Exception:
                pass
        # MACRO / TAUX (rendements du Trésor + dollar → contexte : coût de l'argent, courbe)
        def _mv(_tk):
            try:
                _cc = data[_tk]['Close'].dropna()
                _v = float(_cc.iloc[-1]); _p = float(_cc.iloc[-2]) if len(_cc) > 1 else _v
                return _v, _p
            except Exception:
                return None, None
        macro = []
        for _tk, _nm, _un, _kind in _MACRO_TK:
            _v, _p = _mv(_tk)
            if _v is None:
                continue
            if _kind == 'y' and _v > 20:          # ^TNX & co parfois cotés ×10 → normalise en %
                _v /= 10.0; _p = _p / 10.0 if _p else _p
            try:
                _dt = str(data[_tk]['Close'].dropna().index[-1].date())
            except Exception:
                _dt = ''
            macro.append({'id': _tk, 'name': _nm, 'unit': _un, 'value': round(_v, 2),
                          'prev': round(_p, 2), 'chg': round(_v - _p, 3), 'date': _dt})
        _t10 = next((m for m in macro if m['id'] == '^TNX'), None)
        _t3 = next((m for m in macro if m['id'] == '^IRX'), None)
        if _t10 and _t3:                          # courbe 10a-3m : négative = inversion (signal récession)
            _cur = round(_t10['value'] - _t3['value'], 2); _curp = round(_t10['prev'] - _t3['prev'], 2)
            macro.insert(3, {'id': 'CURVE', 'name': 'Courbe 10a-3m', 'unit': '%', 'value': _cur,
                             'prev': _curp, 'chg': round(_cur - _curp, 3), 'date': _t10.get('date', '')})
        if macro:
            _save_json('macro_cache.json', macro)
        # BAROMÈTRE / INTERNALS + historique de breadth persistant (1 point/jour, maj intraday)
        internals = _market_internals(rows, detail, breadth)
        _attach_vehicle(rows, scan_state.get('options_board') or [])   # verdict ACTION vs OPTION par titre
        _attach_strategy(rows, detail)                                  # score strat + playbook + R:R par titre
        try:
            _bh = _load_json('breadth_history.json', [])
            _today = datetime.now().strftime('%Y-%m-%d')
            _snap = {'d': _today, 'a50': internals['pct_a50'], 'a200': internals['pct_a200'],
                     'net': internals['up'] - internals['dn'], 'health': internals['health']}
            if _bh and _bh[-1].get('d') == _today:
                _bh[-1] = _snap
            else:
                _bh.append(_snap)
            _bh = _bh[-180:]
            _save_json('breadth_history.json', _bh)
            internals['history'] = _bh
        except Exception:
            internals['history'] = []
        # PUBLICATION ANTICIPÉE : sur le CPU bridé du cloud gratuit, le backtest + les
        # recommandations sont lents. On allume tout de suite cockpit/scores/indices
        # (déjà calculés), les blocs lourds suivent dans le même scan ci-dessous.
        _publier(scan_state, 'partiel', _gen,
                 {'rows': rows, 'detail': detail, 'indices': indices, 'commodities': commodities, 'macro': macro, 'internals': internals,
                  'breadth': breadth, 'spy': spy, 'market': market_status(),
                  'universe_n': len(syms_scan), 'scanned_n': len(rows),
                  'titres_en_echec': _te,
                  **({'source': 'demo'} if DEMO_MODE else {}),
                  'scan_ts': time.time(),
                  #  `scan_ts_h` : lu par 23 consommateurs (as_of des routes,
                  #  DecisionTrace…) et jamais ecrit jusqu'a la mission
                  #  alimentation — la fraicheur se lisait « HH:MM:SS » sans date.
                  'scan_ts_h': _horodatage_iso_utc(),
                  'updated': datetime.now().strftime('%H:%M:%S'), 'error': None})
        if DEMO_MODE:                                  # VITRINE : board d'options synthétique
            try:
                _db = _demo_options_board(rows, detail)
                _annotate_swing(_db, detail)
                #  IMMUABILITÉ (lot 45) : rows est DÉJÀ publié quelques lignes
                #  plus haut — copie avant verdict, republication de la copie.
                rows = [dict(r) for r in rows]
                _attach_vehicle(rows, _db)
                _publier(scan_state, 'partiel', _gen,
                         {'rows': rows,
                          'options_board': _db, 'options_as_of': time.time(),
                          # chaîne large synthétique (grille/surface/skew)
                          'options_chain_full': _demo.demo_chain_full(rows, detail)})
            except Exception:
                pass
        # PREUVES PAR TITRE : qualité, provenance et réconciliation sont produites
        # à partir du cycle actuel avant tout chemin décisionnel Skyler/Strategy OS.
        # Une chaîne sans timestamp reste explicitement non actionnable.
        try:
            _packets, _reconciliations = _scan_evidence.build_scan(
                detail, data, scan_state.get('source'), scan_state.get('options_board') or [],
                scan_state.get('options_as_of'))
        except Exception:
            _packets, _reconciliations = [], {}
        # (_packets/_reconciliations rejoignent la publication 'complet' — lot 42)
        try:
            pf = backtest(data)
        except Exception:
            pf = scan_state.get('portfolio')
        # BRIEF QUOTIDIEN + ANOMALIES + SECTEURS (tout depuis rows/detail, zéro réseau)
        prev = {}
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            prev = daily.load_baseline(DAILY_PREV_PATH, today)
            daily_brief = daily.build_daily(rows, detail, prev=prev)
            daily.save_state(DAILY_PREV_PATH, today, daily.snapshot(rows, detail))
        except Exception:
            daily_brief = scan_state.get('daily')
        try:
            anoms = anomalies.detect_anomalies(rows, detail)
        except Exception:
            anoms = scan_state.get('anomalies') or []
        try:
            secs = sectors.build_sectors(rows, detail, prev=prev)
        except Exception:
            secs = scan_state.get('sectors') or []
        try:
            vix_close = data['^VIX']['Close']
        except Exception:
            vix_close = None
        try:
            mctx = market.context(data[BENCH].dropna(), vix_close, rows, detail, secs)
        except Exception:
            mctx = scan_state.get('market_ctx')
        try:
            _tilt = _strat_tilt(mctx)                  # tilt stratégie selon le climat
        except Exception:
            _tilt = scan_state.get('strat_tilt')       # publié avec le bloc 'complet'
        # RECOMMANDATIONS : moteur de décision IBKR (/40 + niveau + timing) sur tout l'univers
        recs = []
        fstate = scan_state.get('fundamentals') or {}
        fsym = fstate.get('by_sym') or {}
        fsec = fstate.get('by_sector') or {}
        # meilleur contrat CALL par titre (depuis l'options_board) pour les composantes option
        board_best = {}
        for c in (scan_state.get('options_board') or []):
            if c.get('type') != 'CALL':
                continue
            s = c.get('sym')
            cur = board_best.get(s)
            rank = {'long': 3, 'moyen': 2, 'court': 1}.get(c.get('bucket'), 0) * 100 + (c.get('pop') or 0)
            if not cur or rank > cur[0]:
                board_best[s] = (rank, c)
        for r in rows:
            sym = r['symbol']
            d = detail.get(sym)
            if not d:
                continue
            fu = fsym.get(sym) or {}
            sec = fu.get('sector') or sectors.SECTOR_MAP.get(sym)
            med = (fsec.get(sec) or {}).get('median_pe')
            opt = {'valuation': fundamentals.valuation(fu.get('pe'), med)} if fu.get('pe') else {}
            if sym in board_best:
                opt['best_pick'] = board_best[sym][1]
            v = ibkr.verdict(d, opt, fu)
            dec = engine.decide(d)
            if v:
                recs.append({'symbol': sym, 'price': r['price'], 'change': r['change'],
                             'grade': r['grade'], 'sector': sectors.SECTOR_MAP.get(sym),
                             'decision': v['decision'], 'tone': v['tone'], 'niveau': v['niveau'],
                             'score40': v['score40'], 'alloc': v['alloc'], 'timing': v['timing']['state'],
                             'raison': v['raison'], 'action': v['action'],
                             'pros': (dec or {}).get('pros', [])[:2]})
        recs.sort(key=lambda x: -x['score40'])
        # STRATÉGIE OPTIONS PERSONNALISÉE (1/2/3/6/9/12 mois) — Black-Scholes, zéro réseau
        try:
            strat = strategy.build(rows, detail, market=mctx, top_n=6,
                                   board=scan_state.get('options_board') or [])
        except Exception:
            strat = scan_state.get('strategy')
        # COMITÉ D'INVESTISSEMENT (4 portes + thèse/plan/invalidation/conviction)
        try:
            comite = committee.evaluate(rows, detail, market=mctx, top_n=12)
        except Exception:
            comite = scan_state.get('committee')
        _publier(scan_state, 'complet', _gen,
                 {'rows': rows, 'detail': detail, 'portfolio': pf, 'daily': daily_brief,
                  'anomalies': anoms, 'sectors': secs, 'market_ctx': mctx, 'indices': indices,
                  'commodities': commodities, 'macro': macro, 'internals': internals,
                  'recommendations': recs, 'strategy': strat, 'committee': comite,
                  'analytics_packets': _packets, 'reconciliation_by_symbol': _reconciliations,
                  'strat_tilt': _tilt, 'titres_en_echec': _te,
                  'breadth': breadth, 'spy': spy, 'market': market_status(),
                  'source_health': {
                      'scan': 'AVAILABLE',
                      'market': 'AVAILABLE' if data is not None else 'UNAVAILABLE',
                      'options': 'AVAILABLE' if scan_state.get('options_board') else 'NOT_COLLECTED',
                      'fundamentals': 'AVAILABLE' if fsym else 'NOT_COLLECTED',
                      'yfinance_budget': _SOURCE_BUDGET_STATE['yfinance'],
                      'stooq_budget': _SOURCE_BUDGET_STATE['stooq'],
                  },
                  'universe_n': len(syms_scan), 'scanned_n': len(rows),
                  'scan_ts': time.time(),
                  'scan_ts_h': _horodatage_iso_utc(),
                  'updated': datetime.now().strftime('%H:%M:%S'), 'error': None})
        try:
            _apply_ibkr_indices()   # overlay indices/VIX TEMPS RÉEL IBKR par-dessus le différé yfinance
        except Exception:
            pass
    except Exception:
        _publier(scan_state, 'erreur', _generation(scan_state), {
            'error': 'scan_failed',
            'source_health': {
                'scan': 'DEGRADED', 'market': 'UNKNOWN',
                'options': 'UNKNOWN', 'fundamentals': 'UNKNOWN',
            }})


_SCAN_LOCK = threading.Lock()


def scan():
    """Exécute un seul scan à la fois sans écraser le dernier état publié."""
    if not _SCAN_LOCK.acquire(blocking=False):
        scan_state['scan_status'] = 'RUNNING'
        scan_state['scan_skip_count'] = int(scan_state.get('scan_skip_count') or 0) + 1
        return False
    scan_state['scan_status'] = 'RUNNING'
    try:
        _scan_once()
        return True
    finally:
        scan_state['scan_status'] = 'DEGRADED' if scan_state.get('error') else 'IDLE'
        _SCAN_LOCK.release()


#  ── PORTE ANTI-RAFALE DU RE-SCAN (#779/G1) ────────────────────────────────
#  Le groupe complet — evenement, verrou, fenetre, delai restant — vit desormais
#  dans `vertex/app/rescan_gate.py`. Il n'avait aucune dependance au monolithe :
#  seulement threading, os, time et math.
#
#  L'EVENEMENT EST PARTAGE, PAS RECOPIE : `_live.configure` le transmet a la
#  boucle de scan, qui attend CET objet. Le reassigner laisserait la boucle
#  attendre un objet que plus personne ne reveille — sans aucune erreur levee.
_rescan_evt = _rescan_gate.EVENEMENT
RESCAN_COOLDOWN_SEC = _rescan_gate.COOLDOWN_S
_rescan_cooldown_remaining = _rescan_gate.restant


# ── VERTEX LIVE ENGINE : câblage du moteur central (états + déclencheur) ──
_live.configure(scan_state=scan_state, news_state=news_state, cal_state=cal_state,
                weekly_state=weekly_state, rescan_event=_rescan_evt,
                ibkr_enabled=IBKR_ENABLED, demo=DEMO_MODE)


def _loop():
    from vertex.scheduler import registry as _sched
    from vertex.services.live_stream import BROKER as _broker
    while True:
        _t0 = time.time()
        try:
            scan()
            _sched.beat('MARKET_DATA_REFRESH', ok=True,
                        duration_ms=(time.time() - _t0) * 1000)
            _broker.publish('market', {'scan_ts': scan_state.get('scan_ts'),
                                       'source': scan_state.get('source'),
                                       'scanned': scan_state.get('scanned_n')})
        except Exception as _e:
            _sched.beat('MARKET_DATA_REFRESH', ok=False, error=str(_e))
        _rescan_evt.wait(REFRESH_SEC)   # dort jusqu'à REFRESH_SEC, OU se réveille tout de suite si rescan manuel
        _rescan_evt.clear()


# ─── PONT OPTIONS IBKR : chaînes d'options via TWS (abonnement OPRA actif) ────
# L'utilisateur est ABONNÉ aux données IBKR → tout le DIRECT (cours + chaînes
# d'options + greeks) passe par IBKR, plus par Yahoo (endpoint options bloqué 401).
# Le moteur vertex/options/legacy_engine.py reste INTACT : on lui présente un adaptateur qui imite
# l'interface yfinance qu'il consomme (.options + .option_chain(exp).calls/.puts).
# ⚠️ ib_async n'est PAS thread-safe → toutes les requêtes passent par UN worker
# dédié (file de jobs, clientId 41) qui possède la connexion. ⛔ LECTURE SEULE.
# Lot 40 — la FIFO nue est remplacée par la file à priorités/coalescence/
# péremption/breaker (vertex/services/file_ibkr.py). Le worker reste UNIQUE.
from vertex.services.file_ibkr import FileIBKR as _FileIBKR

_optf = _FileIBKR()

# ── Connexion IBKR configurable (honnêteté : les variables documentées dans
#    .env.example sont désormais RÉELLEMENT respectées). IBKR_HOST/PORT/CLIENT_ID
#    priment ; à défaut, sonde par défaut (REAL d'abord, cohérente entre workers). ──
_IBKR_HOST = (os.environ.get('IBKR_HOST') or '127.0.0.1').strip() or '127.0.0.1'
_IBKR_CID_BASE = (os.environ.get('IBKR_CLIENT_ID') or '').strip()


#  `_ibkr_ports` et `_ibkr_cid` ont vecu ici jusqu'a l'integration de
#  `vertex-live`. Ils sont retires : `main` a centralise l'ordre de sonde
#  et l'identifiant de session dans `vertex/data_sources/ibkr_link.py`,
#  parce que CINQ sites ouvraient leur propre connexion avec chacun ses
#  idees — dont un qui cherchait le compte PAPIER en premier quand les
#  quatre autres cherchaient le REEL. Deux ordres differents, c'est
#  l'ecran qui affiche un compte et le scan qui en lit un autre.
#  Gardien : `tests/test_ibkr_link.py`.


def _ibkr_opt_worker():
    # Setup GARDÉ : si ib_async manque ou si l'init échoue, le worker répond None
    # à tous les jobs (dégradation rapide) au lieu de mourir → file jamais bloquée.
    try:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        from vertex.data_sources import ibkr_gateway as _gw_ib
        IB, Stock, Option, ScannerSubscription = (_gw_ib.classe(n) for n in ('IB', 'Stock', 'Option', 'ScannerSubscription'))
        ib = IB()
        # ⛑️ ANTI-BLOCAGE : borne TOUTES les requêtes synchrones ib_async
        # (qualifyContracts/reqTickers/reqSecDefOptParams/…). Sans elle, un TWS
        # en socket semi-ouvert fige le worker unique POUR TOUJOURS et tout le
        # canal options/scan/posq meurt en silence. Timeout → exception rattrapée
        # par le try du job → None → on continue.
        ib.RequestTimeout = 45
    except Exception:
        while True:                                  # drain : réponses immédiates None
            _optf.terminer(_optf.prochain(), None)

    def conn():
        if ib.isConnected():
            return True
        #  Ordre des ports et identifiant de session viennent de `ibkr_link`.
        #  Cinq sites ouvraient leur propre connexion avec chacun ses idees,
        #  dont DEUX partageaient le clientId 17 (IBKR refuse alors la seconde
        #  session) et un cherchait le papier quand les autres cherchaient le
        #  reel.
        for port in _ibkr_link.ordre_des_ports():
            try:
                #  Session marché seulement (aucune lecture de compte au connect).
                _ibkr_session.connecter(ib, _ibkr_link.hote(), port, client_id=_ibkr_link.client_id('options'),
                                        timeout=6, readonly=True)
                ib.reqMarketDataType(1)              # temps réel (abonnement actif)
                _ibkr_link.noter_succes(port, 'options')
                _optf.noter_connexion(True)
                return True
            except Exception:
                continue
        _ibkr_link.noter_echec('options')
        _optf.noter_connexion(False)                 # breaker : None immédiat pendant la fenêtre
        return False

    def meta(sym):
        stk = Stock(sym, 'SMART', 'USD')
        ib.qualifyContracts(stk)
        if not getattr(stk, 'conId', 0):
            return None
        params = ib.reqSecDefOptParams(stk.symbol, '', stk.secType, stk.conId)
        p = ([x for x in params if x.exchange == 'SMART'] or params)
        if not p:
            return None
        # Préférer la classe d'options STANDARD (tradingClass == symbole). Certains
        # sous-jacents exposent AUSSI une classe AJUSTÉE (« 2MSFT », « 1GOOG »…, née d'un
        # split ou dividende spécial) : ses strikes near-the-money n'existent pas → IBKR
        # répond « Unknown contract » en masse et la chaîne ressort VIDE (bug MSFT & co).
        std = [x for x in p if x.tradingClass == stk.symbol]
        p = std or p
        _exps, _ks = set(), set()
        for x in p:                                   # union : un paramset SMART peut ne porter qu'une partie des échéances
            _exps |= set(x.expirations)
            _ks |= set(x.strikes)
        tk = ib.reqTickers(stk)[0]
        spot = tk.marketPrice()
        if not spot or spot != spot:
            spot = tk.close
        exps = sorted('%s-%s-%s' % (e[:4], e[4:6], e[6:8]) for e in _exps)
        return {'exps': exps, 'spot': float(spot or 0), 'tc': p[0].tradingClass,
                'strikes': sorted(float(k) for k in _ks)}

    def chain(sym, m, exp, right):
        spot = m['spot']
        if spot <= 0:
            return []
        lo, hi = (0.96, 1.22) if right == 'C' else (0.78, 1.04)
        ks = [k for k in m['strikes'] if spot * lo <= k <= spot * hi]
        ks = sorted(ks, key=lambda k: abs(k - spot))[:14]       # 14 strikes max → vitesse
        e8 = exp.replace('-', '')
        #  `m['strikes']` est l'UNION des strikes de toutes les échéances : le pas
        #  d'IBKR change pourtant avec l'échéance (1 $ sur les hebdomadaires, 5 $
        #  ou 10 $ au-delà). Mesuré le 25 août 2026 : 214 refus « aucune
        #  définition de titre » sur 250 lignes de journal, TOUT sauf les
        #  multiples de 5, et les MÊMES strikes redemandés à chaque cycle.
        #  La mémoire retire ce que le courtier a déjà refusé ; elle n'invente
        #  jamais un strike, et redemande tout si elle croit tout refusé.
        ks_demandes = _strike_memory.filtrer(sym, e8, ks)
        opts = [Option(sym, e8, k, right, 'SMART', tradingClass=m['tc'])
                for k in sorted(ks_demandes)]
        opts = [o for o in ib.qualifyContracts(*opts) if getattr(o, 'conId', 0)]
        _valides = {float(o.strike) for o in opts}
        _strike_memory.noter_acceptes(sym, e8, _valides)
        _strike_memory.noter_refus(sym, e8,
                                   [k for k in ks_demandes if k not in _valides])
        rows = []
        for i in range(0, len(opts), 40):
            batch = opts[i:i + 40]
            tks = [ib.reqMktData(c, genericTickList='100,101,106', snapshot=False) for c in batch]
            ib.sleep(2.6)                                       # greeks + OI arrivent en ~2 s
            for c, t in zip(batch, tks):
                mg = t.modelGreeks

                def _g(v):                                      # greek IBKR propre (NaN → None)
                    return float(v) if (v is not None and v == v) else None
                iv = float(mg.impliedVol) if (mg and mg.impliedVol and mg.impliedVol == mg.impliedVol) else 0.0
                oi = t.callOpenInterest if right == 'C' else t.putOpenInterest
                last = t.last if (t.last and t.last == t.last) else (t.close if (t.close and t.close == t.close) else 0.0)
                rows.append({'strike': float(c.strike), 'impliedVolatility': iv,
                             # DAT-01 : distinguer ABSENT (NaN → None) d'un vrai 0 reporté.
                             # (x == x) est faux uniquement pour NaN ; un vrai 0 est donc conservé.
                             'openInterest': (int(oi) if (oi is not None and oi == oi) else None),
                             'volume': (int(t.volume) if (t.volume is not None and t.volume == t.volume) else None),
                             'bid': float(t.bid) if (t.bid and t.bid == t.bid and t.bid > 0) else 0.0,
                             'ask': float(t.ask) if (t.ask and t.ask == t.ask and t.ask > 0) else 0.0,
                             'lastPrice': float(last),
                             # Greeks RÉELS du broker (modelGreeks IBKR) — jamais estimés.
                             'delta': _g(mg.delta) if mg else None,
                             'gamma': _g(mg.gamma) if mg else None,
                             'theta': _g(mg.theta) if mg else None,
                             'vega': _g(mg.vega) if mg else None})
            for c in batch:
                try:
                    ib.cancelMktData(c)
                except Exception:
                    pass
        return rows

    def fund(syms):
        """Ratios fondamentaux Reuters via tick générique 258 (gratuit à activer côté IBKR).
        Renvoie {sym: {attr: val}} — vide si l'abonnement Reuters n'est pas coché (erreur 10358)."""
        stks = [Stock(s, 'SMART', 'USD') for s in syms]
        stks = [c for c in ib.qualifyContracts(*stks) if getattr(c, 'conId', 0)]
        out = {}
        for i in range(0, len(stks), 30):
            batch = stks[i:i + 30]
            tks = [ib.reqMktData(c, genericTickList='258', snapshot=False) for c in batch]
            ib.sleep(3.5)
            for c, t in zip(batch, tks):
                fr = getattr(t, 'fundamentalRatios', None)
                if fr:
                    d = {}
                    for k in dir(fr):
                        if k.startswith('_'):
                            continue
                        v = getattr(fr, k, None)
                        if isinstance(v, (int, float)) and v == v:
                            d[k] = float(v)
                    if d:
                        out[c.symbol] = d
            for c in batch:
                try:
                    ib.cancelMktData(c)
                except Exception:
                    pass
        return out

    def news():
        """Fil de titres marché (Dow Jones + Briefing) via l'API news IBKR. Lecture seule."""
        stk = Stock('SPY', 'SMART', 'USD')
        ib.qualifyContracts(stk)
        if not getattr(stk, 'conId', 0):
            return []
        try:
            provs = '+'.join(p.code for p in ib.reqNewsProviders())
        except Exception:
            provs = 'BRFG+BRFUPDN+DJNL'
        arts = ib.reqHistoricalNews(stk.conId, provs, '', '', 40) or []
        out = []
        for a in arts:
            h = (a.headline or '').strip()
            while h[:1] in ('!', '{'):                     # nettoie les tags {K:N}! des fils DJ
                h = h[h.find('}') + 1:].strip() if h[:1] == '{' and '}' in h else h[1:].strip()
            if not h:
                continue
            out.append({'time': str(a.time)[:16], 'prov': a.providerCode, 'title': h[:180],
                        'analyst': a.providerCode == 'BRFUPDN'})
        return out

    def scan(code):
        """Scanner IBKR sur TOUT le marché US (pas seulement notre univers). Top 12 + cours."""
        sub = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR',
                                  scanCode=code, abovePrice=5, numberOfRows=15)
        rows = ib.reqScannerData(sub, []) or []
        cons = [r.contractDetails.contract for r in rows][:12]
        res = []
        if cons:
            try:
                tks = ib.reqTickers(*cons)
            except Exception:
                tks = []
            px = {}
            for t in tks:
                last = t.last if (t.last and t.last == t.last) else t.close
                cl = t.close if (t.close and t.close == t.close) else None
                px[t.contract.symbol] = (round(float(last), 2) if (last and last == last) else None,
                                         round((float(last) / cl - 1) * 100, 2) if (last and last == last and cl) else None)
            for i, c in enumerate(cons):
                p = px.get(c.symbol, (None, None))
                res.append({'sym': c.symbol, 'rank': i + 1, 'price': p[0], 'change': p[1]})
        return res

    def posq(positions):
        """Cotation LIVE des positions perso de l'utilisateur (actions + contrats d'options précis).
        exp acceptée en 'YYYY-MM' (résout la vraie échéance du mois) ou 'YYYYMMDD'. Lecture seule."""
        out = {}
        stks = {}
        for p in positions:
            s = (p.get('sym') or '').upper()
            if s and s not in stks:
                stks[s] = Stock(s, 'SMART', 'USD')
        cons = [c for c in ib.qualifyContracts(*stks.values()) if getattr(c, 'conId', 0)] if stks else []
        stks = {c.symbol: c for c in cons}
        spots = {}
        if cons:
            try:
                for t in ib.reqTickers(*cons):
                    last = t.last if (t.last and t.last == t.last) else t.close
                    cl = t.close if (t.close and t.close == t.close) else None
                    spots[t.contract.symbol] = {
                        'spot': round(float(last), 2) if (last and last == last) else None,
                        'spot_chg': round((float(last) / cl - 1) * 100, 2) if (last and last == last and cl) else None}
            except Exception:
                pass
        expcache, opts = {}, []
        for p in positions:
            s = (p.get('sym') or '').upper()
            right = (p.get('right') or '').upper()[:1]
            key = p.get('key') or s
            if right not in ('C', 'P'):                      # position ACTION : spot suffit
                out[key] = {'type': 'STK', **(spots.get(s) or {})} if s in stks else {'err': 'ticker introuvable'}
                continue
            if s not in stks:
                out[key] = {'err': 'ticker introuvable'}
                continue
            exp = (p.get('exp') or '').replace('-', '')
            if len(exp) == 6:                                # 'YYYYMM' → première échéance du mois
                if s not in expcache:
                    try:
                        pr = ib.reqSecDefOptParams(s, '', 'STK', stks[s].conId)
                        sm = [x for x in pr if x.exchange == 'SMART'] or pr
                        es = set()
                        for x in sm:                          # ⚠️ union : chaque paramset SMART ne porte qu'une partie des échéances
                            es |= set(x.expirations)
                        expcache[s] = sorted(es)
                    except Exception:
                        expcache[s] = []
                cand = [e for e in expcache[s] if e.startswith(exp)]
                if not cand:
                    out[key] = {'err': 'échéance %s-%s introuvable' % (exp[:4], exp[4:6])}
                    continue
                exp = cand[0]
            try:
                strike = float(p.get('strike') or 0)
            except Exception:
                strike = 0.0
            opts.append((key, s, exp, Option(s, exp, strike, right, 'SMART')))
        if opts:
            ib.qualifyContracts(*[o for _, _, _, o in opts])
        good = [(k, s, e, o) for (k, s, e, o) in opts if getattr(o, 'conId', 0)]
        for (k, s, e, o) in opts:
            if not getattr(o, 'conId', 0):
                out[k] = {'err': 'contrat introuvable (%s %s $%s%s)' % (s, e, o.strike, o.right)}
        def read_tk(t):
            mg = t.modelGreeks
            last = float(t.last) if (t.last and t.last == t.last and t.last > 0) else None
            close = float(t.close) if (t.close and t.close == t.close and t.close > 0) else None
            bid = float(t.bid) if (t.bid and t.bid == t.bid and t.bid > 0) else None
            ask = float(t.ask) if (t.ask and t.ask == t.ask and t.ask > 0) else None
            mark = last if last is not None else (((bid + ask) / 2) if (bid and ask) else close)
            return {'last': round(last, 2) if last is not None else None,
                    'close': round(close, 2) if close is not None else None,
                    'bid': round(bid, 2) if bid is not None else None,
                    'ask': round(ask, 2) if ask is not None else None,
                    'mark': round(float(mark), 2) if mark is not None else None,
                    'iv': round(float(mg.impliedVol) * 100, 1) if (mg and mg.impliedVol and mg.impliedVol == mg.impliedVol) else None,
                    'delta': round(float(mg.delta), 2) if (mg and mg.delta is not None and mg.delta == mg.delta) else None}

        def quote_pass(items):
            for i in range(0, len(items), 30):
                batch = items[i:i + 30]
                tks = [ib.reqMktData(o, genericTickList='106', snapshot=False) for _, _, _, o in batch]
                ib.sleep(2.8)
                for (key, s, e, o), t in zip(batch, tks):
                    q = read_tk(t)
                    base = out.get(key) or {'type': 'OPT', 'exp': '%s-%s-%s' % (e[:4], e[4:6], e[6:8]),
                                            'strike': float(o.strike), 'right': o.right, **(spots.get(s) or {})}
                    for kk, vv in q.items():
                        if vv is not None or kk not in base:
                            base[kk] = vv if vv is not None else base.get(kk)
                    out[key] = base
                for _, _, _, o in batch:
                    try:
                        ib.cancelMktData(o)
                    except Exception:
                        pass

        quote_pass(good)
        #  Rattrapage des cotations manquantes sur l'ECHELLE COMPLETE. La
        #  version d'origine ne tentait que le type 2 (cloture figee), qui
        #  exige TOUJOURS un abonnement : sans abonnement, la chaine d'options
        #  restait vide malgre le rattrapage.
        for _t in _ibkr_link.ECHELLE_DONNEES[1:]:
            missing = [x for x in good if (out.get(x[0]) or {}).get('mark') is None]
            if not missing:
                break
            try:
                ib.reqMarketDataType(_t)
                quote_pass(missing)
            except Exception:
                continue
        try:
            ib.reqMarketDataType(1)              # on rend la ligne au temps reel
        except Exception:
            pass
        return out

    while True:
        job = _optf.prochain()                       # priorités + péremption (lot 40)
        kind, args, res = job.kind, job.args, None
        try:
            if not _optf.connexion_permise():
                res = None                           # breaker ouvert : pas de re-sonde
            elif not conn():
                res = None
            elif kind == 'meta':
                res = meta(*args)
            elif kind == 'chain':
                res = chain(*args)
            elif kind == 'fund':
                res = fund(*args)
            elif kind == 'news':
                res = news()
            elif kind == 'scan':
                res = scan(*args)
            elif kind == 'posq':
                res = posq(*args)
            #  Lot 2 — le job `positions` est RETIRÉ : il lisait le portefeuille
            #  du COMPTE via ib.positions(). readonly protegeait de l'ordre,
            #  pas de la confidentialite. Le worker ne sert plus que du marche.
        except Exception:
            res = None
            # Échec de job (timeout/déconnexion) : on repart d'une connexion PROPRE.
            # Un socket semi-ouvert renverrait isConnected()=True et referait échouer
            # tous les jobs suivants — le disconnect force conn() à se reconnecter.
            try:
                ib.disconnect()
            except Exception:
                pass
        _optf.terminer(job, res)


def _opt_job(kind, args, timeout):
    #  Contrat historique conservé (None au timeout) — la file coalesce les
    #  demandes identiques et n'exécute jamais un job que plus personne n'attend.
    return _optf.soumettre(kind, args, timeout)


def _persist_chain_full(sym, exp, right, rows, spot):
    """Persiste la chaîne LARGE (14 strikes/côté, AVANT le filtrage « finalistes » du
    board) → débloque max pain / murs d'OI / strikes demandés / PCR RÉELS.
    scan_state['options_chain_full'][SYM] = {exp: {'C'|'P': {strike: {oi,vol,iv}}}, 'spot':…, 'ts':…}.
    Borné à ~200 symboles (purge LRU grossière). ⛔ lecture seule, best-effort, silencieux."""
    sym = (sym or '').upper()
    right = (right or 'C').upper()[:1]
    if not sym or not rows:
        return
    by_strike = {}
    for r in rows:
        try:
            k = round(float(r['strike']), 2)
        except (TypeError, ValueError, KeyError):
            continue
        if k <= 0:
            continue
        oi = r.get('openInterest')                        # DAT-01 : None honnête si absent, 0 si vrai 0
        vol = r.get('volume')
        iv = r.get('impliedVolatility')

        def _rg(name, nd=4):                              # greek broker persisté (None honnête)
            v = r.get(name)
            return round(float(v), nd) if isinstance(v, (int, float)) else None

        def _q(name, nd=2):                               # cotation bid/ask/last (None honnête, >0)
            v = r.get(name)
            return round(float(v), nd) if isinstance(v, (int, float)) and float(v) > 0 else None
        by_strike[k] = {'oi': (int(oi) if oi is not None else None),
                        'vol': (int(vol) if vol is not None else None),
                        'iv': (round(float(iv), 4) if iv else None),
                        'delta': _rg('delta'), 'gamma': _rg('gamma'),
                        'theta': _rg('theta'), 'vega': _rg('vega'),
                        'bid': _q('bid'), 'ask': _q('ask'), 'last': _q('lastPrice')}
    if not by_strike:
        return
    full = scan_state.setdefault('options_chain_full', {})
    ent = full.get(sym)
    if ent is None:
        if len(full) >= 200:                              # borne mémoire : purge le plus ancien
            oldest = min(full, key=lambda kk: (full[kk] or {}).get('ts') or 0)
            full.pop(oldest, None)
        ent = full[sym] = {}
    ent.setdefault(exp, {})[right] = by_strike
    ent['ts'] = time.time()
    try:
        if spot is not None and float(spot) > 0:
            ent['spot'] = round(float(spot), 2)
    except (TypeError, ValueError):
        pass


class _IbkrChainSide:
    """Résultat de option_chain(exp) : .calls/.puts PARESSEUX → on ne fetch que le côté demandé."""
    def __init__(self, sym, m, exp):
        self._a = (sym, m, exp)

    def _df(self, right):
        sym, m, exp = self._a
        rows = _opt_job('chain', (sym, m, exp, right), timeout=75) or []
        if rows:                                          # capte la chaîne large pour max pain / OI / PCR
            try:
                _persist_chain_full(sym, exp, right, rows, (m or {}).get('spot'))
            except Exception as _e:
                #  Sans ce nom, max-pain et surface restent vides et se lisent
                #  comme « ce titre n'a pas d'options ».
                scan_state.setdefault('chaine_non_persistee', {})[str(sym).upper()] = {
                    'echeance': exp, 'cote': right, 'erreur': str(_e)[:160]}
        return pd.DataFrame(rows, columns=['strike', 'impliedVolatility', 'openInterest',
                                           'volume', 'bid', 'ask', 'lastPrice'])

    @property
    def calls(self):
        return self._df('C')

    @property
    def puts(self):
        return self._df('P')


class _IbkrTicker:
    """Imite l’interface yf.Ticker consommée par vertex/options/legacy_engine.py (moteur intact)."""
    def __init__(self, sym):
        self._sym = str(sym).upper()
        self._m = _opt_job('meta', (self._sym,), timeout=25)

    @property
    def options(self):
        return list(self._m['exps']) if self._m else []

    def option_chain(self, exp):
        return _IbkrChainSide(self._sym, self._m, exp)


class _IbkrYF:
    Ticker = _IbkrTicker


_YF_FOR_OPTIONS = options.yf          # yfinance d'origine → repli automatique si TWS fermé
# ROTATION UNIVERS COMPLET : cache accumulé {sym: {'ts':…, 'contracts':[…]}} — persistant.
# Chaque cycle analyse les ~15 titres les plus ANCIENS → tout l'univers optionable (~700
# titres US) est couvert en quelques heures, puis rafraîchi en continu (fraîcheur < 24 h).
#  Le cache des chaines d'options vit dans `vertex/app/caches.py` — il est
#  partage entre `_opt_loop` (rotation) et `options_pack` (fiche ouverte).
#  L'objet doit rester LE MEME des deux cotes : on le REMPLIT, on ne le
#  reassigne pas.
_OPTALL_CACHE.update(_load_json('optall_cache.json', {}) or {})


_LAST_FOCUS = list((_OPT_CACHE or {}).get('board') or [])   # dernier board focus connu (graine)


_attach_vehicle = _strategy_fit.attach_vehicle
_attach_strategy = _strategy_fit.attach_strategy
_strat_tilt = _strategy_fit.strat_tilt


def _publish_board(focus):
    """Publie FOCUS ∪ ROTATION fraîche (<24 h), dédupliqué — le focus (plus frais) gagne."""
    now = time.time()
    fresh = [(s, v) for s, v in _OPTALL_CACHE.items() if now - (v.get('ts') or 0) < 24 * 3600]
    rot = [c for _, v in fresh for c in (v.get('contracts') or [])]
    merged = {}
    for c in rot + (focus or []):
        merged[(c.get('sym'), c.get('exp'), c.get('strike'), c.get('type'))] = c
    ob = list(merged.values())
    if ob:
        _annotate_swing(ob, scan_state.get('detail') or {})
        bloc = {'options_board': ob, 'options_as_of': now}
        # Suivis HYPOTHÉTIQUES uniquement : chaque refresh du board fige une
        # quote de contrat réellement publiée pour alimenter le track record.
        try:
            from vertex.tracking import repository as _tracking_repo
            bloc['option_tracking_snapshot'] = _tracking_repo.record_option_board(
                ob, at=now, source=scan_state.get('options_source') or 'options_board')
        except Exception:
            # Le suivi ne doit jamais interrompre la publication analytique.
            bloc['option_tracking_snapshot'] = {'error': 'snapshot indisponible'}
        #  IMMUABILITÉ (lot 45, dette du lot 42) : la liste publiée reste
        #  figée — le verdict véhicule est attaché sur une COPIE ligne à
        #  ligne, republiée dans le MÊME cycle (génération et phase
        #  conservées) en un seul bloc atomique avec le board.
        rows_nouveaux = [dict(r) for r in (scan_state.get('rows') or [])]
        _attach_vehicle(rows_nouveaux, ob)
        bloc['rows'] = rows_nouveaux
        _gen_cour = scan_state.get('scan_gen')
        _publier(scan_state,
                 scan_state.get('scan_phase') or 'partiel',
                 _gen_cour if isinstance(_gen_cour, int)
                 and not isinstance(_gen_cour, bool) else 0,
                 bloc)
        _save_json('options_cache.json', {'board': ob, 'ts': time.time()})
        # Push SSE (canal 'options') : le board a changé → les pages options se rafraîchissent.
        try:
            from vertex.services.live_stream import BROKER as _broker
            _broker.publish('options', {'board_n': len(ob),
                                        'coverage': scan_state.get('options_coverage'),
                                        'source': scan_state.get('options_source')})
        except Exception:
            pass


def _opt_loop():
    """Board options — chaînes via IBKR TEMPS RÉEL (abonnement) ; repli yfinance si TWS fermé.
    ROTATION d'abord (couverture univers visible vite), puis FOCUS (top setups ultra-frais)."""
    global _LAST_FOCUS
    while True:
        if scan_state.get('rows') and scan_state.get('detail'):
            echec_opt = None
            try:
                probe = _opt_job('meta', ('SPY',), timeout=15) if IBKR_ENABLED else None
                options.yf = _IbkrYF if probe else _YF_FOR_OPTIONS
                scan_state['options_source'] = 'ibkr' if probe else 'yfinance'
                # 1) ROTATION UNIVERS COMPLET (IBKR uniquement) — 15 titres les plus anciens,
                #    publication après CHAQUE lot de 5 → la couverture grimpe en continu.
                if probe:
                    det = scan_state['detail']
                    cands = [r['symbol'] for r in scan_state['rows'] if '.' not in r['symbol']]
                    stale = sorted(cands, key=lambda s: (_OPTALL_CACHE.get(s) or {}).get('ts', 0))[:15]
                    for j, sym in enumerate(stale):
                        d = det.get(sym) or {}
                        spot = d.get('price')
                        entry = {'ts': time.time(), 'contracts': []}
                        if spot:
                            plan = d.get('plan') or {}
                            tgt = plan.get('tp2') or round(spot * 1.12, 2)
                            try:
                                entry['contracts'] = options.best_for_symbol(
                                    sym, spot, tgt, 'call', max_n=1, buckets=('court', 'moyen', 'long'))
                            except Exception:
                                pass
                        _OPTALL_CACHE[sym] = entry
                        if (j + 1) % 5 == 0 or j == len(stale) - 1:
                            now = time.time()
                            fresh = [(s, v) for s, v in _OPTALL_CACHE.items()
                                     if now - (v.get('ts') or 0) < 24 * 3600]
                            scan_state['options_coverage'] = {
                                'done': len(fresh), 'total': len(cands),
                                'with_options': sum(1 for _, v in fresh if v.get('contracts'))}
                            _publish_board(_LAST_FOCUS)
                    _save_json('optall_cache.json', _OPTALL_CACHE)
                # 2) FOCUS : meilleurs setups du jour, données les plus fraîches (~8 s/titre IBKR)
                ob = options.build_board(scan_state['detail'], scan_state['rows'],
                                         max_calls=(25 if probe else 40), max_puts=8)
                if ob:
                    _LAST_FOCUS = ob
                    if probe:
                        _publish_board(ob)
                    else:                              # repli yfinance : board focus seul
                        _annotate_swing(ob, scan_state.get('detail') or {})
                        scan_state['options_board'] = ob
                        scan_state['options_as_of'] = time.time()
                        _save_json('options_cache.json', {'board': ob, 'ts': time.time()})
            except Exception as e:
                echec_opt = '%s: %s' % (type(e).__name__, e)
            try:
                #  CETTE BOUCLE NE BATTAIT RIEN. Elle rafraichit le board
                #  d'options toutes les 120 s — rotation de l'univers puis
                #  focus — et aucune ligne de la page Systeme ne la
                #  representait. `OPTION_POSITION_REFRESH` existe au registre
                #  mais decrit la cotation des POSITIONS options : l'emprunter
                #  aurait refait la faute que ce lot vient de corriger sur
                #  `TRACK_RECORD_UPDATE`, parler au nom d'un autre travail.
                from vertex.scheduler import registry as _sched
                _sched.beat('OPTIONS_BOARD_REFRESH', ok=(echec_opt is None),
                            error=echec_opt)
            except Exception:
                pass
            time.sleep(120)
        else:
            time.sleep(8)


def _radar_loop():
    """RADAR marché entier : scanners IBKR (tout le marché US, pas seulement l'univers)
    + fil de nouvelles Dow Jones / Briefing. Rafraîchi ~4 min. ⛔ LECTURE SEULE."""
    time.sleep(30)
    while True:
        out = {}
        #  LES MOTIFS SONT RETENUS, PAS AVALES. Quatre flux, quatre
        #  `except: pass` : quand ils echouaient tous — c'est le cas nominal
        #  sans TWS — `out` restait vide, le `if out` sautait l'ecriture, et le
        #  radar gardait sa valeur precedente PAR OMISSION, sans que la raison
        #  existe nulle part. Une absence silencieuse ressemble a une absence
        #  de marche ; ce n'en est pas une.
        #  DEUX DESTINATAIRES, DEUX NIVEAUX DE DETAIL. `absents` ne porte que
        #  des NOMS DE FLUX : il part au client via `/scan`, et le vocabulaire
        #  d'erreur servi est fait de codes stables, jamais d'un type Python
        #  (cf. `tests/test_aucune_exception_servie.py`). Le motif complet va
        #  au registre, surface d'exploitation, ou nommer la cause est le
        #  contrat — comme `_weekly_loop` le fait deja.
        absents, motifs = [], []
        for code, key in (('TOP_PERC_GAIN', 'gainers'), ('TOP_PERC_LOSE', 'losers'),
                          ('MOST_ACTIVE', 'active')):
            try:
                r = _opt_job('scan', (code,), timeout=45)
                if r:
                    out[key] = r
            except Exception as e:
                absents.append(key)
                motifs.append('%s: %s: %s' % (key, type(e).__name__, e))
        try:
            nw = _opt_job('news', (), timeout=40)
            if nw:
                out['news'] = _news_plus.sanitize_news(nw[:35])   # XSS : titres IBKR externes
        except Exception as e:
            absents.append('news')
            motifs.append('news: %s: %s' % (type(e).__name__, e))
        if out:
            out['updated'] = datetime.now().strftime('%H:%M %d/%m')
            out['ts'] = time.time()          # epoque serveur — la page affiche un age VRAI
            scan_state['radar'] = out
            _save_json('radar_cache.json', out)
        #  L'ecart se DIT, qu'il soit total ou partiel : quatre flux attendus,
        #  ceux qui ont manque sont nommes. La valeur precedente reste servie —
        #  elle est reelle — mais elle ne passe plus pour fraiche en silence.
        scan_state['radar_ecart'] = ({'flux_absents': absents,
                                      'attendus': 4,
                                      'ts': time.time()} if absents else None)
        try:
            #  CETTE BOUCLE NE BATTAIT RIEN. Elle interroge les scanners du
            #  marche entier et le fil Dow Jones toutes les 240 s, et aucune
            #  ligne de la page Systeme ne la representait.
            from vertex.scheduler import registry as _sched
            _sched.beat('MARKET_RADAR_REFRESH', ok=bool(out),
                        error='; '.join(motifs)[:200] or None)
        except Exception:
            pass
        time.sleep(240)


def _map_ibkr_fund(sym, d):
    """Convertit les ratios Reuters (tick 258) au schéma fondamentaux de l'app."""
    def g(*keys, scale=1.0):
        for k in keys:
            v = d.get(k)
            if isinstance(v, (int, float)) and v == v:
                return v * scale
        return None
    mc = g('MKTCAP')
    return {'pe': g('PEEXCLXOR', 'APENORM'), 'fwd_pe': g('ProjPE'), 'pb': g('PRICE2BK'),
            'peg': None, 'margin': g('TTMNPMGN', scale=0.01), 'growth': g('TTMREVCHG', scale=0.01),
            'beta': g('BETA'), 'mcap': mc * 1e6 if mc else None, 'div': g('YIELD', scale=0.01),
            'roe': g('TTMROEPCT', scale=0.01), 'debt_eq': g('QTOTD2EQ'),
            'sector': _GICS_SECTOR.get(sym), 'industry': _INDUSTRY_MAP.get(sym), 'name': None}


# ─── NEWS LIVE : flux marché rafraîchi chaque minute ─────────────────────
# news_state : état partagé (state.py) — rempli par la boucle d'actualités.
NEWS_SYMS = ['SPY', 'QQQ', 'NVDA', 'AAPL', 'MSFT', 'META', 'AMZN', 'TSLA', 'AMD', 'GOOGL', 'AVGO', 'PLTR']


def _news_loop():
    while True:
        try:
            feed = []
            # couverture dynamique : le socle + les titres CHAUDS du scan (mouvement/volume)
            hot = []
            try:
                rows_n = sorted((scan_state.get('rows') or []),
                                key=lambda r: abs(r.get('change') or 0) + (r.get('rvol') or 0), reverse=True)
                hot = [r['symbol'] for r in rows_n[:6] if r.get('symbol') not in NEWS_SYMS]
            except Exception:
                pass
            #  ── TETE DE CHAINE : LE COURTIER ────────────────────────────
            #  Le compte est abonne a des fournisseurs professionnels (Dow
            #  Jones, Briefing) : prendre les depeches sur le web pendant ce
            #  temps, c'est lire une autre actualite que celle du courtier qui
            #  detient les positions.
            #
            #  Un LOT, pas 18 appels : la boucle couvre 12 symboles fixes plus
            #  6 titres chauds, et l'identifiant client est unique — ouvrir une
            #  session par symbole couterait plus cher que les depeches.
            #  Mesure : 12 symboles servis en 8,9 s sur une seule session.
            depeches = {}
            if IBKR_ENABLED and not DEMO_MODE:
                try:
                    import asyncio as _aio_n
                    from vertex.data_sources.ibkr_news import depeches_lot
                    try:
                        _aio_n.get_event_loop()
                    except RuntimeError:
                        _aio_n.set_event_loop(_aio_n.new_event_loop())
                    depeches = depeches_lot(NEWS_SYMS + hot, n=4)
                except Exception as _en:      # TWS absent, refus : on continue
                    _live_meta['news_err'] = '%s: %s' % (type(_en).__name__, _en)
            n_ibkr = n_web = 0
            for sym in NEWS_SYMS + hot:
                try:
                    its = depeches.get(sym) or []
                    if its:
                        n_ibkr += 1
                    else:
                        #  Ce que le courtier ne sert pas descend la chaine.
                        #  Une absence ici n'est pas un vide a l'ecran : c'est
                        #  le repli qui prend la main, et la provenance le dit.
                        its = options.news_for(yf.Ticker(sym), n=4)
                        if not its:                               # repli multi-sources (throttle yfinance)
                            its = _news_plus.rss_news(sym, n=4)
                        if its:
                            n_web += 1
                    its, _ = ai.fr_news(sym, its)
                    for it in its:
                        it['senti'] = _news_plus.sentiment((it.get('title') or '') + ' ' + (it.get('fr') or ''))
                        feed.append({**it, 'sym': sym})
                except Exception:
                    continue
            # LOT 605 : la deduplication se faisait sur `titre[:60]` — deux
            # depeches DIFFERENTES partageant leur ouverture etaient confondues
            # (information REELLE perdue), et le meme article en casse ou
            # ponctuation differente passait deux fois. `dedupe_news` existe
            # dans le depot depuis le lot 4, est teste, et cle sur le titre
            # NORMALISE COMPLET + le lien : le fil ne l'appelait simplement pas.
            # Dedupe AVANT le tri : on garde le premier arrive, comme avant.
            feed = _news_plus.dedupe_news(feed)
            feed.sort(key=lambda x: x.get('time') or '', reverse=True)
            #  Regle produit n°5 : tout texte externe passe par
            #  `sanitize_news` AVANT d'etre servi. Cette branche-ci —
            #  RSS, yfinance, traduction — ne le faisait pas ; seule
            #  celle d'IBKR etait couverte. Le fil est rendu en
            #  innerHTML : un titre porteur de balise passait tel quel.
            news_state['items'] = _news_plus.sanitize_news(feed[:45])
            news_state['updated'] = datetime.now().strftime('%H:%M:%S')
            #  La provenance NOMME ses contributeurs, comme le scan : « ibkr »
            #  n'est pas « ibkr+web ». Sans ce compte, un fil bascule
            #  entierement sur le web sans que rien ne change a l'ecran.
            news_state['source_detail'] = {'ibkr': n_ibkr, 'web': n_web}
            news_state['source'] = '+'.join(
                [n for n, c in (('ibkr', n_ibkr), ('web', n_web)) if c]) or 'aucune'
            #  #779/G1 — NEWS_REFRESH était déclaré au registre des jobs sans
            #  aucun émetteur : la boucle tournait, la page Système affichait
            #  « jamais exécuté ». La cadence déclarée au registre (900 s) était
            #  fausse elle aussi ; la vraie est celle d'en dessous, 60 s.
            from vertex.scheduler import registry as _sched
            _sched.beat('NEWS_REFRESH', ok=True)
        except Exception as e:
            #  Ce battement ne pouvait JAMAIS dire ERREUR : place en fin de
            #  `try`, il n'etait atteint qu'en cas de succes, et l'echec
            #  partait dans un `pass` sans motif. Le fil tombait donc en
            #  SILENCIEUX — « la boucle est morte ou coincee » — alors qu'elle
            #  tournait et echouait toutes les 60 s pour une raison nommable.
            #  Le registre a un champ pour cette raison ; il restait vide.
            try:
                from vertex.scheduler import registry as _sched
                _sched.beat('NEWS_REFRESH', ok=False,
                            error='%s: %s' % (type(e).__name__, e))
            except Exception:
                pass
        _live.wait_force('news', 60)


# ─── CALENDRIER EARNINGS : prochaines dates pour les 45 (rafraîchi /3h) ───
cal_state['items'] = _load_json('cal_cache.json', [])   # réhydrate l'état partagé (persistant, anti-restart)


def _cal_loop():
    # « CHOPE TOUT » : couverture élargie à ~280 titres (cœur + big caps + trend + S&P)
    # au lieu de la seule watchlist. Doux avec l'endpoint (pause entre appels) + persistant.
    targets = list(dict.fromkeys(WATCHLIST + _BIG_EXTRA + _TREND_EXTRA + _SP500_EXTRA))[:280]
    def _publish(items):
        items = sorted(items, key=lambda x: x['dte'] if x['dte'] is not None else 9999)
        good = [x for x in items if x['dte'] is not None and x['dte'] >= -2]
        if good and len(good) >= len(cal_state.get('items') or []) * 0.5:
            cal_state['items'] = good
            cal_state['updated'] = datetime.now().strftime('%H:%M %d/%m')
            cal_state['ts'] = time.time()   # époque serveur — la page affiche un âge VRAI
            _save_json('cal_cache.json', good)
    time.sleep(5 if DEMO_MODE else 90)                 # laisse le scan de démarrage finir (anti-throttle)
    if DEMO_MODE:                                      # VITRINE : calendrier earnings synthétique
        import zlib
        while True:
            rows = scan_state.get('rows') or []
            if rows:
                items = []
                for r in rows:
                    sym = r['symbol']
                    seed = zlib.crc32(('cal' + sym).encode()) & 0xffffffff
                    dte = 2 + (seed % 46)              # résultats étalés sur ~6 semaines
                    es = (datetime.now() + timedelta(days=dte)).strftime('%Y-%m-%d')
                    det = (scan_state.get('detail') or {}).get(sym, {})
                    items.append({'sym': sym, 'date': es, 'dte': dte,
                                  'score': det.get('score'), 'grade': det.get('grade'),
                                  'verdict': det.get('verdict')})
                items.sort(key=lambda x: x['dte'])
                cal_state['items'] = items
                cal_state['updated'] = datetime.now().strftime('%H:%M %d/%m')
                cal_state['ts'] = time.time()
                try:
                    from vertex.scheduler import registry as _sched
                    _sched.beat('CATALYST_REFRESH', ok=True)
                except Exception:
                    pass
                _live.wait_force('calendar', 3 * 3600)   # interruptible : Sync Center peut forcer
            else:
                time.sleep(10)
    while True:
        # try/except ENGLOBANT : seule boucle qui n'en avait pas — une ligne malformée
        # dans rows/items tuait le thread → calendrier figé à vie, sans bruit.
        try:
            if scan_state.get('rows'):
                items, fails = [], 0
                echec = None
                for i, sym in enumerate(targets):
                    try:
                        cal = yf.Ticker(sym).calendar
                        ed = cal.get('Earnings Date') if isinstance(cal, dict) else None
                        ed = ed[0] if isinstance(ed, (list, tuple)) and ed else ed
                        fails = 0
                        if ed is not None:
                            es = str(ed)[:10]
                            d = (datetime.strptime(es, '%Y-%m-%d') - datetime.now()).days
                            det = scan_state['detail'].get(sym, {})
                            items.append({'sym': sym, 'date': es, 'dte': d,
                                          'score': det.get('score'), 'grade': det.get('grade'),
                                          'verdict': det.get('verdict')})
                    except Exception:
                        fails += 1
                        if fails % 12 == 0:            # rafale d'échecs = throttle → on respire
                            time.sleep(45)
                    time.sleep(0.12)
                    if i and i % 40 == 0:             # publication INCRÉMENTALE (pas d'attente 5 min)
                        _publish(items)
                _publish(items)
            else:
                time.sleep(10)
                continue
        except Exception as e:
            #  L'echec est NOMME, pas avale — meme regle que `_weekly_loop`.
            echec = '%s: %s' % (type(e).__name__, e)
        try:
            #  LE BATTEMENT MANQUAIT SUR CE CHEMIN. Il n'existait que dans la
            #  branche `DEMO_MODE` ci-dessus : `CATALYST_REFRESH` etait donc le
            #  SEUL job du depot dont l'unique emetteur vivait sous DEMO. En
            #  reel, `last_run` restait None a jamais et la page Systeme
            #  affichait « EN_ATTENTE » — « pas encore passe depuis le
            #  demarrage » — pour un calendrier rafraichi toutes les trois
            #  heures. C'est exactement la confusion que le registre existe
            #  pour empecher, appliquee cette fois a un job QUI MARCHE.
            from vertex.scheduler import registry as _sched
            _sched.beat('CATALYST_REFRESH', ok=(echec is None), error=echec)
        except Exception:
            pass
        time.sleep(30 if echec else 3 * 3600)


# ─── FONDAMENTAUX : P/E par titre + médianes secteur (lent, rafraîchi /6h) ───
#  Lot 43 — mémoire DATÉE des refus : les titres morts (rachetés, radiés) que
#  ni IBKR ni yfinance ne servent ne sont plus redemandés à chaque cycle.
#  Avant : mêmes symboles refusés toutes les 45 s À VIE (« Aucune définition
#  de titre », 404), et le rythme ne se calmait jamais. TTL 24 h — un refus
#  est daté, jamais définitif.
_REFUS_FUND = _MemoireRefus()


def _fund_loop():
    # yfinance .info = 1 appel/titre = LENT et throttlé en masse. STRATÉGIE ANTI-THROTTLE :
    # on remplit le cache PAR PETITS LOTS (40 titres manquants / 45 s) → doux pour l'IP,
    # accumulé sur disque (fund_cache.json) → survit aux redémarrages, ne repart jamais de 0.
    FUND_N = 400
    targets = UNIVERSE[:FUND_N]
    while True:
        if scan_state.get('rows'):
            echec_fund = None
            try:
                candidats = [s for s in targets if s not in _FUND_CACHE]
                missing, _morts = _REFUS_FUND.filtrer(candidats)
                batch = missing[:40]
                if batch:
                    new = {}
                    # 1) IBKR d'abord (ratios Reuters tick 258 — abonnement GRATUIT à cocher
                    #    dans le compte IBKR ; tant qu'il ne l'est pas → vide, repli yfinance)
                    ibf = _opt_job('fund', (batch,), timeout=90) if IBKR_ENABLED else None
                    if ibf:
                        new = {s: _map_ibkr_fund(s, d) for s, d in ibf.items()}
                        scan_state['fund_source'] = 'ibkr'
                    else:
                        fb = fundamentals.build(batch)
                        new = (fb or {}).get('by_sym') or {}
                        if new:
                            scan_state['fund_source'] = 'yfinance'
                    if new:
                        _FUND_CACHE.update(new)               # fusion (couverture cumulée)
                        _save_json('fund_cache.json', _FUND_CACHE)
                    #  Refus DATÉS : un symbole tenté que ni IBKR ni yfinance
                    #  n'a servi ne sera pas redemandé avant le TTL — et
                    #  l'écart se DIT (fund_refus), il ne se tait pas.
                    for s in batch:
                        if s not in _FUND_CACHE:
                            _REFUS_FUND.noter(s)
                    scan_state['fund_refus'] = _REFUS_FUND.etat()
                if _FUND_CACHE:
                    scan_state['fundamentals'] = {'by_sym': _FUND_CACHE,
                                                  'by_sector': _recompute_sectors(_FUND_CACHE)}
            except Exception as e:
                echec_fund = '%s: %s' % (type(e).__name__, e)
            still_missing = any(s not in _FUND_CACHE and not _REFUS_FUND.refuse_recemment(s)
                                for s in targets)
            try:
                #  Cette boucle emettait `TRACK_RECORD_UPDATE`, le job d'une
                #  AUTRE boucle, et a `ok=True` fige apres un `except: pass`.
                #  Deux fautes en une : elle parlait au nom d'un travail
                #  qu'elle ne fait pas, et elle le declarait sain quoi qu'il
                #  arrive. Elle declare desormais SON job — les fondamentaux
                #  tournaient sans aucune ligne a l'ecran — et dit la verite.
                from vertex.scheduler import registry as _sched
                _sched.beat('FUNDAMENTALS_REFRESH', ok=(echec_fund is None),
                            error=echec_fund)
            except Exception:
                pass
            time.sleep(45 if still_missing else 6 * 3600)     # rapide tant que ça remplit, puis lent
        else:
            time.sleep(12)


# ─── VALIDATION DE L'EDGE : le score Vertex prédit-il les rendements ? (backtest walk-forward) ──
# Pour des dates PASSÉES, on recalcule le score « tel qu'il était » (analyse sur l'historique
# tronqué) puis on mesure le rendement RÉALISÉ ensuite (5/21/63 j). Regroupé par tranche de
# score → prouve (ou non) que score élevé = rendement supérieur. Zéro look-ahead. LECTURE SEULE.
# Corrélation de rangs (Spearman) : source unique dans vertex/engines/stats.py.
_spearman = _stats.spearman
from vertex.engines import edge_validation as _edge_validation  # noqa: E402


#  DÉPLACÉ (strangler) vers `vertex/engines/edge_validation.py`, qui reçoit
#  la collecte et l'analyse en PARAMÈTRE. Le backtest y devient éprouvable sans
#  réseau — il ne l'était pas ici, et n'avait donc aucun test.
#  Cette porte garde la signature d'origine : `_edge_loop` est inchangée, et
#  `_download_universe` reste résolu dans CES globales au moment de l'appel,
#  donc les doublures de test continuent de mordre.
def edge_backtest(syms=None, horizons=(5, 21, 63), step=8, lookback=460):
    return _edge_validation.edge_backtest(
        telecharger=_download_universe, analyser=analyse,
        univers=list(dict.fromkeys(WATCHLIST + _BIG_EXTRA + _TREND_EXTRA))[:140],
        bench=BENCH, syms=syms, horizons=horizons, step=step, lookback=lookback)

_EDGE_CACHE = _load_json('edge_cache.json', None)
if _EDGE_CACHE:
    scan_state['edge'] = _EDGE_CACHE


def _edge_loop():
    while True:
        if scan_state.get('rows'):
            try:
                eb = edge_backtest()
                if eb:
                    scan_state['edge'] = eb
                    _save_json('edge_cache.json', eb)
            except Exception:
                pass
            #  LE BATTEMENT ETAIT DANS LA MAUVAISE BOUCLE. `TRACK_RECORD_UPDATE`
            #  — « Mise a jour de la fiabilite mesuree » — etait emis par
            #  `_fund_loop`, la boucle des FONDAMENTAUX, qui n'y touche pas.
            #  La vraie mise a jour est ici, `_track.record`, et elle ne
            #  battait rien. La page Systeme declarait donc la fiabilite
            #  mesuree « ACTIF » sur la foi d'un cycle de fondamentaux, et un
            #  `_track.record` en echec a chaque tour n'aurait rien dit.
            echec_track = None
            try:
                _track.record(scan_state)             # 📓 snapshot quotidien des verdicts (idempotent)
            except Exception as e:
                echec_track = '%s: %s' % (type(e).__name__, e)
            try:
                from vertex.scheduler import registry as _sched
                _sched.beat('TRACK_RECORD_UPDATE', ok=(echec_track is None),
                            error=echec_track)
            except Exception:
                pass
            time.sleep(6 * 3600)
        else:
            time.sleep(20)


# ─── BAROMÈTRE DU MARCHÉ : internals / breadth agrégés depuis le scan (vue top-down) ──
#  DÉPLACÉ (strangler) vers `vertex/market/internals.py`. La fonction ne
#  collecte rien : tout entre par ses arguments, tout sort par sa valeur de
#  retour — elle n'avait aucune raison de vivre dans le monolithe. Le nom est
#  réexporté ici parce que `_scan_once` le résout dans CES globales.
from vertex.market.internals import market_internals as _market_internals  # noqa: E402,F401


# ─── WATCHLIST DE LA SEMAINE : sélection FIGÉE le lundi (état partagé → state.py) ──


_earnings_map = _weekly_selection.carte_resultats


def _weekly_loop():
    """Construit/charge la sélection hebdo. Le ROSTER est figé pour la semaine ISO
    (snapshot persisté) ; on rafraîchit seulement les chiffres vivants à chaque tour."""
    while True:
        if scan_state.get('rows') and scan_state.get('detail'):
            #  L'echec est NOMME, pas avale. Avant, un `except: pass` laissait le
            #  domaine « hebdo » a l'etat « jamais synchronise » sans jamais dire
            #  pourquoi : la surface montrait une absence, et la raison de cette
            #  absence n'existait nulle part (QUALITY_STANDARD §1).
            echec = None
            try:
                snap, regen = weekly.get_or_build(
                    WEEKLY_PATH, scan_state['rows'], scan_state['detail'],
                    earnings=_earnings_map(), n=6, with_options=True)
                weekly_state.update({'data': snap, 'regenerated': regen,
                                     'error': None,
                                     'updated': datetime.now().strftime('%H:%M:%S')})
            except Exception as e:
                echec = '%s: %s' % (type(e).__name__, e)
                weekly_state['error'] = echec
            try:
                #  Le battement dit la VERITE. Emis inconditionnellement a `ok=True`,
                #  il declarait le job WEEKLY_REVIEW sain alors que la construction
                #  venait d'echouer — la page Systeme affichait donc un vert faux.
                from vertex.scheduler import registry as _sched
                _sched.beat('WEEKLY_REVIEW', ok=(echec is None), error=echec)
            except Exception:
                pass
            time.sleep(300)        # options réelles = lent → toutes les 5 min
        else:
            time.sleep(8)


# ─── options / GEX / earnings à la demande ───────────────────────────────
#  `options_pack` vit dans `vertex/options/pack.py`. Mesure : sur 18 symboles
#  utilises, TROIS seulement etaient locaux — le cache `_OPTALL_CACHE` (parti
#  dans vertex/app/caches.py) et les deux coerceurs `_i`/`_f`, dont il etait
#  l'unique appelant. Le nom local reste : `_opt_loop` s'en sert.
from vertex.options.pack import options_pack  # noqa: E402


#  `/scan` et `/api/rescan` sont partis dans
#  `vertex/app/routes/scan_api.py` — aucune injection : leur seule
#  dependance locale etait la porte anti-rafale, partie avec elles.


#  Les en-tetes de securite, les pages d'erreur 404/500 et la compression gzip
#  vivaient ici. Aucun ne dependait de l'etat du monolithe : ils sont tenus par
#  `vertex/app/factory.py::create_app`, avec le reste de la plomberie Flask.


#  `_scan_age` existait a l'identique ici ET dans decision_api. Une seule
#  maison desormais : `vertex.app.state.scan_age`.


# ─── FLUX DE DONNÉES (Blueprint) — market/summary · cockpit · watchlist · options · search · weekly · strategie · comite ───
#  ── REGISTRE DE ROUTES CANONIQUE (#779, contribution a G1) ─────────────
#  Les 15 blueprints SANS injection sont declares dans
#  `vertex/app/factory.py` et enregistres ici, en un point unique. Avant, ils
#  etaient disperses entre les lignes 1866 et 2456, meles aux vues et aux
#  utilitaires : personne ne pouvait dire quelles routes l'application sert
#  sans lire 2 300 lignes.
#
#  LA POSITION DE CET APPEL N'EST PAS ARBITRAIRE. `/api/anomalies/<sym>` est
#  declare par DEUX blueprints — `analysis_api` (sans injection, ici) et
#  `strategy_os_api` (a injection, enregistre plus bas). Flask donne la regle
#  au PREMIER enregistre. Placer ce groupe apres `strategy_os_api` changerait
#  donc le gagnant en silence. Il reste avant.
from vertex.app import factory as _factory
_factory.register_blueprints(app)


#  `/api/ticker/<sym>` et `/options/<sym>` sont partis dans
#  `vertex/app/routes/ticker_api.py`.


# ─── DESK PERSO (Blueprint) — /api/desk · /api/watchlist-tv · /api/pos-quotes ───
#  RETABLI : la suppression de `/api/ticker` avait emporte cet enregistrement,
#  qui vivait DANS le meme intervalle. Sept routes du desk perso — synchro,
#  sauvegardes, restauration, cotations de positions — avaient disparu du
#  service. Aucune erreur n'etait levee : Flask ne se plaint pas d'un blueprint
#  qu'on n'enregistre pas. Le diff des regles avant/apres l'a montre.
def _cotation_repli(symbole):
    """Dernier recours pour coter une ACTION : le prix que le SCAN a deja etabli.

    Aucune requete reseau nouvelle — la valeur est deja en memoire, produite par
    le cycle de scan (yfinance/Stooq). C'est ce qui evite un P&L vide quand TWS
    est ferme, sans abonnement, ou hors seance.
    """
    d = (scan_state.get('detail') or {}).get(symbole) or {}
    px = d.get('price')
    if px is None:
        return None
    return {'spot': px, 'spot_chg': d.get('change')}


app.register_blueprint(_desk.make_blueprint(
    opt_job=_opt_job, ibkr_enabled=IBKR_ENABLED,
    cotation_repli=_cotation_repli))


# ─── SANTÉ SYSTÈME & PWA (Blueprint) — healthz · system-status · favicon · manifest · sw.js ───


# ─── TRADINGVIEW (Blueprint) — /api/tradingview/webhook · /api/tradingview/signals ───
# Signaux d'information uniquement : le webhook déclenche une RÉÉVALUATION,
# jamais un achat (secret TRADINGVIEW_WEBHOOK_SECRET requis, anti-replay, dédup).
from vertex.data_sources import tradingview_webhooks as _tv_webhooks


def _on_tv_signal(entry):
    """Réacteur : un signal TradingView accepté réveille la boucle de scan.

    Tient la promesse REEVALUATE — le prochain passage réévalue le titre. Reste
    strictement lecture seule : aucun ordre, aucune écriture de position."""
    try:
        _rescan_evt.set()
    except Exception:
        pass


app.register_blueprint(_tv_webhooks.make_blueprint(on_signal=_on_tv_signal))


# ─── VERTEX STRATEGY OS (Blueprint + page) — constitution · décision unique ·
#     régime · anomalies · équipe · diagnostics · qualité de données ───
from vertex.app.routes import strategy_os_api as _strategy_os_api
app.register_blueprint(_strategy_os_api.make_blueprint(scan_state=scan_state))


# ─── VERTEX MASTER REDESIGN (Blueprint) — 8 espaces + fiche canonique +
#     redirections des anciennes pages (strangler pattern, APIs intactes) ───
from vertex.app.routes import redesign as _redesign
app.register_blueprint(_redesign.make_blueprint(scan_state=scan_state))

# ─── FLUX TEMPS RÉEL (SSE) : /api/live/events — lecture seule, §26 ───

# ─── POSITION INTELLIGENCE : /api/positions/* — lecture seule, cycle de vie ───
from vertex.app.routes import positions_api as _positions_api
app.register_blueprint(_positions_api.make_blueprint(
    scan_state=scan_state, opt_job=_opt_job, ibkr_enabled=IBKR_ENABLED))


# ─── API DÉCISION (Blueprint) — /api/decision · /api/brief · /api/committee-review ───
# Sortie du monolithe : logique dans vertex/app/routes/decision_api.py, état injecté.
app.register_blueprint(_decision_api.make_blueprint(scan_state=scan_state, demo_mode=DEMO_MODE))


# ─── IBKR LECTURE SEULE (ib_reader, readonly) — jamais d'ordre ──────────────
_IBKR_MODE = {7496: 'RÉEL (TWS)', 7497: 'PAPER (TWS)', 4001: 'RÉEL (Gateway)', 4002: 'PAPER (Gateway)'}


def _ibkr_worker(res):
    import asyncio
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())   # boucle dédiée à ce thread
    except Exception:
        pass
    try:
        from ib_reader import IBKRReader
    except Exception as e:
        res['error'] = f'ib_async non disponible ({type(e).__name__})'
        return
    r = IBKRReader()
    #  Ce site cherchait le PAPIER en premier alors que les trois autres
    #  cherchaient le REEL : quand les deux TWS repondent, l'ecran affichait le
    #  cash d'un compte et les cotations d'un autre, sans que rien ne le dise.
    for port in _ibkr_link.ordre_des_ports():
        try:
            #  Preuve de socket seulement : session marché, jamais de compte.
            _ibkr_session.connecter(r.ib, _ibkr_link.hote(), port, client_id=_ibkr_link.client_id('compte'),
                                    timeout=2, readonly=True)
            r.port = port
            _ibkr_link.noter_succes(port, 'compte')
            break
        except Exception:
            continue
    if not r.ib.isConnected():
        res['error'] = "TWS/Gateway non lancé ou API désactivée (ports 7497/7496). Lance TWS en lecture seule + active l'API."
        return
    #  Lot 2 — frontiere market-data-only. Ce worker lisait accountSummary,
    #  managedAccounts et les positions pour la carte « COMPTE IBKR » du
    #  legacy. Tout cela est du COMPTE, pas du marche : retire. Il ne reste
    #  que la preuve de socket — connecte, sur quel port, en quel mode — qui
    #  est l'etat de connexion autorise.
    try:
        res['connected'] = True
        res['mode'] = _IBKR_MODE.get(r.port, '?')
    except Exception as e:
        res['error'] = f'lecture IBKR : {type(e).__name__}'
    finally:
        try:
            r.disconnect()
        except Exception:
            pass


def _ibkr_snapshot():
    #  Lot 2 — le snapshot ne porte plus AUCUN champ de compte : ni account,
    #  ni net_liq/cash/buying_power/upnl, ni positions. `/ibkr` repond
    #  desormais { connected, mode, error } — la preuve de socket, rien d'autre.
    if not IBKR_ENABLED:
        return {'connected': False, 'error': 'IBKR désactivé (cloud — pas de TWS)', 'mode': None}
    now = time.time()
    if _ibkr_cache['data'] and now - _ibkr_cache['ts'] < 15:
        return _ibkr_cache['data']
    res = {'connected': False, 'error': None, 'mode': None}
    t = threading.Thread(target=_ibkr_worker, args=(res,), daemon=True)
    t.start()
    t.join(timeout=14)
    if t.is_alive() and not res['error']:
        res['error'] = 'connexion IBKR trop longue (timeout)'
    _ibkr_cache['data'] = res
    _ibkr_cache['ts'] = now
    return res


# ─── COURS EN DIRECT (flux IBKR permanent, lecture seule) ───────────────────


#  La passerelle socket -> scan_state vit desormais dans
#  `vertex/app/ibkr_state.py` : ses deux entrees (`_live_meta`, `scan_state`)
#  avaient deja un domicile dans le paquet, elle restait ici par habitude. Le
#  nom local est CONSERVE — une quinzaine d'appelants s'en servent dans ce
#  fichier, et les renommer d'un coup melerait deux changements.
_sync_ibkr_state = _ibkr_state.sync


def _px_valide(v):
    """Prix exploitable, ou None. `nan` et `None` sont la MEME chose : « IBKR
    n\'a rien donne »."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if (f == f and f > 0) else None


def _store_ticker(t):
    """Range un ticker IBKR dans _live_quotes. Rend (stocke, temps_reel).

    LE PRIX EST CONSERVE DES QU\'IL EXISTE. L\'ancienne version exigeait `last`
    ET `close` (`if last and close:`) : hors seance, IBKR ne livre pas toujours
    la cloture, et un prix REEL etait alors JETE parce qu\'un champ DERIVE — la
    variation — n\'etait pas calculable. Jeter une verite pour proteger un
    calcul, c\'est l\'inverse de la regle du produit : une donnee absente devient
    un `—` honnete, elle ne vide pas l\'ecran de ce qu\'on sait.

    `stocke` est rendu pour que l\'appelant sache si un passage a produit QUOI
    QUE CE SOIT — c\'est ce qui declenche le repli vers la cloture figee.
    """
    s = t.contract.symbol.replace(' ', '-')   # IBKR 'BRK B' -> forme interne yfinance 'BRK-B'
    last = _px_valide(getattr(t, 'last', None))
    close = _px_valide(getattr(t, 'close', None))
    if last is None:
        try:
            last = _px_valide(t.marketPrice())
        except Exception:
            last = None
    if last is None:
        last = close
    if last is None:
        return (False, False)
    _live_quotes[s] = {
        'last': round(last, 2),
        #  Variation INCONNUE plutot qu\'absente de la ligne : sans cloture on
        #  ne peut pas la calculer, et l\'inventer serait pire que l\'avouer.
        'change': round((last - close) / close * 100, 2) if close else None,
        'bid': (lambda v: round(v, 2) if v else None)(_px_valide(getattr(t, 'bid', None))),
        'ask': (lambda v: round(v, 2) if v else None)(_px_valide(getattr(t, 'ask', None))),
    }
    return (True, getattr(t, 'marketDataType', None) == 1)


def _quotes_worker():
    """Maintient une connexion IBKR readonly et stream les cours en direct de la
    watchlist dans _live_quotes. ⛔ LECTURE SEULE — reqMktData uniquement, jamais d'ordre."""
    import asyncio
    while True:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            from vertex.data_sources import ibkr_gateway as _gw_ib
            IB, Stock = _gw_ib.classe('IB'), _gw_ib.classe('Stock')
            ib = IB()
            ok = False
            for port in _ibkr_link.ordre_des_ports():
                try:
                    _ibkr_session.connecter(ib, _ibkr_link.hote(), port, client_id=_ibkr_link.client_id('cotations'),
                                            timeout=4, readonly=True)
                    _ibkr_link.noter_succes(port, 'cotations')
                    ok = True
                    break
                except Exception:
                    continue
            if not ok:
                _ibkr_link.noter_echec('cotations')
            if not ok:
                _live_meta['connected'] = False
                _sync_ibkr_state()
                time.sleep(20)
                continue
            #  1 = temps reel. IBKR NE BASCULE PAS TOUT SEUL : le commentaire
            #  d'origine (« bascule auto en differe si pas d'abonnement ») etait
            #  FAUX. Avec le type 1, un marche ferme ou un abonnement manquant
            #  rend des ticks vides — et l'ecran se retrouve sans aucun cours,
            #  « comme si IBKR n'avait rien trouve ». Le chemin options le
            #  savait deja (il retente en type 2) ; ce worker-ci et celui des
            #  indices ne le savaient pas.
            mdt = 1
            ib.reqMarketDataType(mdt)
            _live_meta['mdt'] = mdt
            _live_meta['mdt_libelle'] = _ibkr_link.libelle_donnees(mdt)
            passages_a_vide = 0
            cs = [Stock(s.replace('-', ' '), 'SMART', 'USD') for s in LIVE_SYMBOLS]   # classe B : BRK-B -> 'BRK B' pour IBKR
            ib.qualifyContracts(*cs)
            valid = [c for c in cs if getattr(c, 'conId', 0)]
            _live_meta.update({'connected': True, 'n': len(valid)})
            debut_degrade = 0
            while ib.isConnected():
                rt = False
                recus = 0
                for i in range(0, len(valid), 20):   # lots de 20 = cycle rapide sur tout l'univers, snapshot (lignes libérées entre lots)
                    try:                              # timeout : un symbole sans données ne bloque pas le lot
                        # 14 s : avec l'abonnement TEMPS RÉEL, la fin de snapshot des titres
                        # calmes (hors séance) prend ~11 s — 7 s annulait des lots entiers.
                        tickers = ib.run(asyncio.wait_for(ib.reqTickersAsync(*valid[i:i + 20]), 14))
                    except Exception as _e:
                        _live_meta['err'] = f'reqTickers: {type(_e).__name__}: {_e}'
                        continue
                    for t in tickers:
                        stocke, temps_reel = _store_ticker(t)
                        if stocke:
                            recus += 1
                        if temps_reel:
                            rt = True
                    _live_meta.update({'ts': time.time(), 'rt': rt})   # frais dès le 1er lot
                    _sync_ibkr_state()
                    ib.sleep(0.2)
                #  Un cycle ENTIER sans un seul cours : le marche est ferme, ou
                #  l'abonnement ne couvre pas ces titres. On demande alors la
                #  CLOTURE FIGEE (type 2) — une donnee vraie, simplement datee
                #  d'hier — plutot que de laisser huit ecrans vides. Deux cycles
                #  d'attente : un lot qui expire n'est pas un marche ferme.
                #  Escalade 1 -> 2 -> 3 -> 4, regle UNIQUE partagee par les
                #  flux (`ibkr_link.type_suivant`). Le type 2 exige encore un
                #  abonnement : sans abonnement, seul le 3 (differe) parle. Deux
                #  cycles d'attente avant de descendre — un lot qui expire n'est
                #  pas un marche ferme.
                if recus == 0:
                    passages_a_vide += 1
                    if passages_a_vide >= 2:
                        suivant = _ibkr_link.type_suivant(mdt, False)
                        if suivant != mdt:
                            mdt = suivant
                            ib.reqMarketDataType(mdt)
                            _live_meta['mdt'] = mdt
                            _live_meta['mdt_libelle'] = _ibkr_link.libelle_donnees(mdt)
                            debut_degrade = time.time() if mdt != 1 else 0
                        passages_a_vide = 0
                else:
                    passages_a_vide = 0
                #  Retour au temps reel toutes les 15 min : rester en mode
                #  degrade ferait mentir l'ecran a l'ouverture de la seance.
                #  `debut_degrade` est pose AU MOMENT DE LA BASCULE — le
                #  remettre a l'heure a chaque cycle rendait ce retour
                #  structurellement inatteignable.
                if mdt != 1 and debut_degrade and time.time() - debut_degrade > 900:
                    mdt = 1
                    ib.reqMarketDataType(mdt)
                    _live_meta['mdt'] = mdt
                    _live_meta['mdt_libelle'] = _ibkr_link.libelle_donnees(mdt)
                    debut_degrade = 0
                ib.sleep(4)
        except Exception as _e:
            _live_meta['connected'] = False
            _live_meta['err'] = f'loop: {type(_e).__name__}: {_e}'
            _sync_ibkr_state()
        time.sleep(15)


# ─── INDICES EN DIRECT (IBKR temps réel) ───────────────────────────────────
# yfinance ne cote les indices qu'en différé ~15 min. IBKR les donne en temps réel :
# S&P 500 et VIX via les indices CBOE (abonnement actif), Dow Jones via le CFD gratuit
# IBUS30. On overlaie scan_state['indices'] + le VIX du contexte. On N'OVERLAIE PAS
# le Nasdaq (yfinance = ^IXIC Composite ; IBKR gratuit = NDX 100 → indices DIFFÉRENTS,
# mélanger serait malhonnête §4) ni le Russell. ⛔ LECTURE SEULE (reqMktData only).
# nom d'affichage (DOIT matcher scan_state['indices']) -> (secType, symbol, exchange)
_IDX_SPECS = [
    ('S&P 500', 'IND', 'SPX', 'CBOE'),
    ('VIX', 'IND', 'VIX', 'CBOE'),
    ('Dow Jones', 'CFD', 'IBUS30', 'SMART'),
]


def _apply_ibkr_indices():
    """Overlaie les valeurs indices IBKR fraîches (< 75 s) sur scan_state.
    Ne mute QUE des clés/éléments existants — scan_state jamais réassigné."""
    now = time.time()
    fresh = {n: v for n, v in _IDX_IBKR.items()
             if v.get('price') is not None and (now - v.get('ts', 0)) < 75}
    if not fresh:
        return
    idx = scan_state.get('indices')
    if isinstance(idx, list):
        for e in idx:
            v = fresh.get(e.get('name'))
            if v:
                e['price'] = v['price']
                if v.get('change') is not None:
                    e['change'] = v['change']
                e['src'] = 'ibkr'          # provenance temps réel (honnêteté §4)
    vx = fresh.get('VIX')
    if vx:
        mc = scan_state.get('market_ctx')
        if isinstance(mc, dict):
            mc['vix'] = round(vx['price'], 2)
            if vx.get('change') is not None:
                mc['vix_chg'] = round(vx['change'], 2)
    scan_state['indices_live'] = {'source': 'ibkr', 'ts': now,
                                  'names': sorted(fresh.keys())}


def _indices_loop():
    """Worker indices TEMPS RÉEL IBKR (SPX/VIX CBOE + CFD Dow). Lecture seule —
    reqMktData uniquement, jamais d'ordre. 3 lignes de marché : cadence négligeable."""
    import asyncio
    while True:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            from vertex.data_sources import ibkr_gateway as _gw_ib
            IB, Index, CFD = _gw_ib.classe('IB'), _gw_ib.classe('Index'), _gw_ib.classe('CFD')
            ib = IB()
            ok = False
            for port in _ibkr_link.ordre_des_ports():
                try:
                    _ibkr_session.connecter(ib, _ibkr_link.hote(), port, client_id=_ibkr_link.client_id('indices'),
                                            timeout=4, readonly=True)
                    _ibkr_link.noter_succes(port, 'indices')
                    ok = True
                    break
                except Exception:
                    continue
            if not ok:
                _ibkr_link.noter_echec('indices')
            if not ok:
                _IDX_META['connected'] = False
                time.sleep(20)
                continue
            #  Meme correctif : IBKR ne bascule pas seul, et le commentaire
            #  d'origine (« repli auto differe si besoin ») decrivait un
            #  comportement qui n'existe pas.
            ib.reqMarketDataType(1)
            _IDX_META['mdt'] = 1
            streams = []
            for name, sec, sym, exch in _IDX_SPECS:
                try:
                    c = Index(sym, exch, 'USD') if sec == 'IND' else CFD(sym)
                    ib.qualifyContracts(c)
                    if getattr(c, 'conId', 0):
                        streams.append((name, ib.reqMktData(c, '', False)))
                except Exception:
                    continue
            _IDX_META.update({'connected': bool(streams), 'n': len(streams)})
            while ib.isConnected():
                ib.sleep(12)
                recus = 0
                for name, t in streams:
                    px = None
                    for v in (getattr(t, 'last', None), t.marketPrice(), getattr(t, 'close', None)):
                        try:
                            if v is not None and v == v and v > 0:
                                px = float(v)
                                break
                        except Exception:
                            continue
                    prev = getattr(t, 'close', None)
                    chg = None
                    try:
                        if px and prev and prev == prev and prev > 0:
                            chg = round((px / float(prev) - 1) * 100, 2)
                    except Exception:
                        chg = None
                    if px is not None:
                        _IDX_IBKR[name] = {'price': round(px, 2), 'change': chg, 'ts': time.time()}
                        recus += 1
                _IDX_META['ts'] = time.time()
                #  Aucun indice cote : cloture figee plutot qu'un bandeau vide.
                #  L'echec de la bascule est ECRIT, jamais avale : un
                #  `except: pass` de plus aurait rendu muette la seule
                #  explication d'un bandeau vide — precisement le defaut traite
                #  ici. Les gardiens des lots 385/386 l'ont refuse, a raison.
                cible = _ibkr_link.type_suivant(_IDX_META.get('mdt', 1),
                                                bool(recus))
                if _IDX_META.get('mdt') != cible:
                    try:
                        ib.reqMarketDataType(cible)
                        _IDX_META['mdt'] = cible
                        _IDX_META['mdt_libelle'] = _ibkr_link.libelle_donnees(cible)
                        _IDX_META.pop('err_mdt', None)
                    except Exception as _mdte:
                        _IDX_META['err_mdt'] = (
                            'bascule type %d refusee: %s: %s'
                            % (cible, type(_mdte).__name__, _mdte))
                _apply_ibkr_indices()
        except Exception as _e:
            _IDX_META['connected'] = False
            _IDX_META['err'] = f'{type(_e).__name__}: {_e}'
        time.sleep(15)


#  `/quotes` et `/ibkr` sont partis dans
#  `vertex/app/routes/live_state_api.py` avec `/api/alerts/status`.


# ─── FILS DE CONTENU (Blueprint) — news-feed · cal-feed · weekly-feed ───


#  `/weekly-regen` est parti dans `vertex/app/routes/weekly_api.py`.


# ─── COUCHE PAGES RETIRÉE (strangler, lot 36) ───────────────────────────────
#  Ici vécurent ~4650 lignes de gabarits HTML morts : PAGE_DAILY,
#  PAGE_WATCHLIST, PAGE_OPTIONS_DESK, PAGE_ME, PAGE_ENTREPRISES, les sept
#  pages `_vpage` (/settings /review /research /health /heatmap /equipe
#  /bordel) et leur machinerie (_extract, _inject_*, _hub_tabs, blocs nav/kit).
#  Preuve du retrait : aucune route ne les renvoyait (toutes appartiennent à
#  vertex.app.routes.redesign — pages 2.0 ou 301) et AUCUN nom de la couche
#  n'était référencé hors d'elle (AST, 0 référence). Les doubles écrivains
#  myRecos/myFavs/myNotes qu'elle portait étaient donc inatteignables : le
#  seul écrivain servi est vx-entities.js. Gardien :
#  tests/test_strangler_couche_pages.py. Rollback : git revert du lot.




# ─── 🔔 ALERTES ACTIVES : évaluation SERVEUR des alertes utilisateur (60 s) ───
# Les vxAlerts étaient stockées mais jamais évaluées. Ici : prix live IBKR
# (repli scan) vs niveau → déclenchement persisté (alerts_fired.json), consommé
# par le kit client (toast + journal + désactivation). Lecture seule, zéro ordre.
_ALERTS_FIRED = _load_json('alerts_fired.json', {})


#  ── SONDES D'ETAT (#779/G1) ────────────────────────────────────────────────
#  Enregistre ICI et pas avec les six autres blueprints a injection : ses deux
#  dependances (`_ibkr_snapshot`, `_ALERTS_FIRED`) sont definies plus bas dans
#  ce fichier, et l'enregistrer plus haut leverait un NameError a l'import.
#  L'ordre est neutre pour le dispatch — aucune des trois routes n'entre en
#  collision (mesure : 4 regles en double dans le depot, aucune de celles-ci).
#
#  `_ALERTS_FIRED` est passe PAR REFERENCE : la boucle d'alertes le mute en
#  place, et c'est ce partage qui fait que /api/alerts/status sert l'etat
#  courant plutot qu'une copie figee au demarrage.
from vertex.app.routes import live_state_api as _live_state_api  # noqa: E402
app.register_blueprint(_live_state_api.make_blueprint(
    ibkr_snapshot=_ibkr_snapshot, alerts_fired=_ALERTS_FIRED))


def _alert_price(sym):
    q = _live_quotes.get(sym)
    if q and _live_meta.get('connected') and q.get('last') is not None:
        return q['last']
    d = (scan_state.get('detail') or {}).get(sym) or {}
    return d.get('price')


def _alerts_loop():
    while True:
        echec = None
        try:
            blob = _load_json('desk_data.json', {}) or {}
            raw = (blob.get('data') or {}).get('vxAlerts')
            alerts = json.loads(raw) if isinstance(raw, str) else (raw or [])
            changed = False
            for a in alerts:
                if not isinstance(a, dict):
                    continue
                aid = str(a.get('id') or '')
                if not aid or aid in _ALERTS_FIRED or a.get('active') is False:
                    continue
                sym = (a.get('sym') or '').upper()
                lvl, px = a.get('level'), _alert_price((a.get('sym') or '').upper())
                if px is None or lvl is None:
                    continue
                cond = a.get('cond') or 'above'
                hit = (px >= lvl) if cond in ('above', 'target') else (px <= lvl)
                if hit:
                    _ALERTS_FIRED[aid] = {'id': a.get('id'), 'sym': sym, 'cond': cond,
                                          'level': lvl, 'price': round(float(px), 4),
                                          'ts': int(time.time()), 'note': a.get('note') or ''}
                    changed = True
            if changed:
                if len(_ALERTS_FIRED) > 200:          # borne dure
                    for k in sorted(_ALERTS_FIRED, key=lambda k: _ALERTS_FIRED[k].get('ts', 0))[:-200]:
                        _ALERTS_FIRED.pop(k, None)
                _save_json('alerts_fired.json', _ALERTS_FIRED)
                # Push SSE (canal 'alerts') : une alerte vient de se déclencher.
                try:
                    from vertex.services.live_stream import BROKER as _broker
                    _broker.publish('alerts', {'fired': len(_ALERTS_FIRED)})
                except Exception:
                    pass
        except Exception as e:
            #  L'echec est NOMME, pas avale.
            echec = '%s: %s' % (type(e).__name__, e)
        try:
            #  LE VERT ETAIT INCONDITIONNEL. Ce battement vivait APRES le
            #  `except ...: pass` englobant, a `ok=True` fige : un cycle
            #  entierement en echec — fichier du desk illisible, JSON
            #  malforme — declarait quand meme le job SAIN. La page Systeme
            #  affichait « Evaluation serveur des alertes utilisateur : ACTIF »
            #  pendant que plus aucune alerte n'etait evaluee. C'est le filet
            #  de l'utilisateur : le mensonge y coute le plus cher.
            from vertex.scheduler import registry as _sched
            _sched.beat('ALERTS_EVALUATION', ok=(echec is None), error=echec)
        except Exception:
            pass
        time.sleep(60)


#  `/api/alerts/status` a rejoint `live_state_api`, et
#  `/api/track-record` `track_record_api` (aucune injection : ses deux
#  dependances vivaient deja dans le paquet).


def _horodatage_iso_utc() -> str:
    """Horodatage ISO 8601 UTC (`2026-09-06T00:12:03Z`) : parseable par
    `VX.freshness._ms`, contrairement a `updated` (heure locale sans date)."""
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _demarrer_les_boucles():
    """Démarre les threads de fond. En mode DÉMO (vitrine cloud) on ne lance QUE le
    scan synthétique : les autres boucles (options/news/calendrier/hebdo/fondamentaux)
    dépendent de yfinance — inutiles et coûteuses (mémoire/CPU) quand le réseau est
    bloqué sur le serveur. Hors démo, tout démarre normalement."""
    #  AVANT TOUT THREAD : `ib_async` ecrit deux lignes par tentative et par
    #  port, sur quatre ports et quatre workers. Mesure d'un premier lancement
    #  sans TWS : 168 lignes en une minute, en anglais, pour un etat
    #  parfaitement normal. Le filtre en garde UNE, traduite, et compte le
    #  reste ; l'etat reel reste sur Systeme > Connexions.
    _ibkr_link.calmer_le_journal_du_courtier()
    threading.Thread(target=_loop, daemon=True).start()
    threading.Thread(target=_alerts_loop, daemon=True).start()   # 🔔 alertes utilisateur actives
    if DEMO_MODE:                                     # VITRINE : calendrier earnings synthétique
        threading.Thread(target=_cal_loop, daemon=True).start()
    if not DEMO_MODE:
        threading.Thread(target=_opt_loop, daemon=True).start()
        threading.Thread(target=_news_loop, daemon=True).start()
        threading.Thread(target=_cal_loop, daemon=True).start()
        threading.Thread(target=_weekly_loop, daemon=True).start()
        threading.Thread(target=_fund_loop, daemon=True).start()
        threading.Thread(target=_edge_loop, daemon=True).start()
        #  Références macro officielles (FRED, BCE, BNS) : collecteur de fond
        #  propre au paquet (`vertex/services/macro_officiel.py`), rien de
        #  nouveau dans le monolithe hormis ce démarrage.
        from vertex.services import macro_officiel as _macro_officiel
        _macro_officiel.demarrer()
    if IBKR_ENABLED:                                  # pas de TWS sur le cloud → on n'essaie pas
        threading.Thread(target=_quotes_worker, daemon=True).start()
        threading.Thread(target=_indices_loop, daemon=True).start()      # indices/VIX TEMPS RÉEL IBKR (lecture seule)
        threading.Thread(target=_ibkr_opt_worker, daemon=True).start()   # chaînes options IBKR (lecture seule)
        threading.Thread(target=_radar_loop, daemon=True).start()        # scanners + news IBKR (lecture seule)


def _start_workers():
    """Point d'entrée du démarrage des boucles — GARDÉ CONTRE LE DOUBLE APPEL.

    #779/G1. `_start_workers()` est appelé à DEUX endroits : à l'import quand
    `START_ON_IMPORT=1`, et par `_start_app()`. Sans garde, les deux appels
    partaient, et `_loop`, `_alerts_loop` et `_cal_loop` tournaient EN DOUBLE —
    mesuré : 4 fils après import, 7 après le second appel. Deux boucles de scan
    mutant `scan_state` en même temps ne plantent pas : elles s'écrasent
    l'une l'autre au hasard de l'ordonnancement.

    La production n'était pas touchée (gunicorn n'appelle jamais `_start_app`),
    mais le lancement local documenté l'était — donc toute mesure prise en
    `START_ON_IMPORT=1` l'a été avec deux boucles concurrentes.

    Le second appel est ignoré ET COMPTÉ : `_lifecycle.statut()['ignores']`
    permet de constater qu'une seconde tentative a eu lieu."""
    return _lifecycle.demarrer_une_seule_fois(_demarrer_les_boucles, nom='boucles')


def _start_app():
    _start_workers()
    # Séquence de démarrage ordonnée (§10) — jamais bloquante, rapport exposé
    def _startup():
        try:
            from vertex.services.startup import run_startup_sequence
            from vertex.scheduler import registry as _sched
            from vertex.services.live_stream import BROKER as _broker
            rep = run_startup_sequence(scan_state)
            #  Le motif MANQUAIT : `ok=False` sans raison laisse la page
            #  Systeme dire « en echec » sans dire de quoi. Le rapport porte
            #  deja la reponse — chaque etape a son `status` et son `detail` —
            #  elle n'etait simplement pas transmise. On NOMME les etapes en
            #  ERROR, celles-la memes qui font basculer `ok` a faux.
            _casses = [e for e in (rep.get('steps') or [])
                       if e.get('status') == 'ERROR']
            _sched.beat('STARTUP_HEALTH_CHECK', ok=rep.get('ok', False),
                        error='; '.join('%s: %s' % (e.get('step'), e.get('detail'))
                                        for e in _casses) or None)
            _broker.publish('system', {'startup': True, 'ok': rep.get('ok')})
        except Exception as _e:
            #  ET SURTOUT : quand la sequence elle-meme casse, il n'y avait
            #  AUCUN battement — le job restait « EN_ATTENTE » a jamais et la
            #  raison partait dans un `print` que personne ne lit. Un rapport
            #  de demarrage indisponible est une information de premier ordre.
            print('[startup] rapport indisponible:', _e)
            try:
                from vertex.scheduler import registry as _sched2
                _sched2.beat('STARTUP_HEALTH_CHECK', ok=False,
                             error='%s: %s' % (type(_e).__name__, _e))
            except Exception:
                pass

    def _brain_boot():
        """« Lancer avec Claude » : enrichit toutes les surfaces au démarrage.

        Attend que le premier scan peuple les titres, puis lance Claude+web une
        fois. Sans clé, on écrit malgré tout un instantané MISSING honnête (l'UI
        affiche « analyse Claude indisponible » au lieu d'inventer). Jamais
        bloquant."""
        try:
            from vertex.ai import enrichment as _enrich
            from vertex.app.routes.ai_api import enrich_symbols, start_background_enrichment
            from vertex.ai.web_provider import ClaudeWebProvider
            for _ in range(30):                      # ~30 s max d'attente du 1er scan
                if scan_state.get('rows'):
                    break
                time.sleep(1)
            if ClaudeWebProvider().available():
                start_background_enrichment()        # tâche de fond, non bloquante
            else:
                _enrich.run(enrich_symbols())        # écrit un instantané MISSING honnête
        except Exception as _e:
            print('[brain] enrichissement Claude indisponible:', _e)

    threading.Thread(target=_startup, daemon=True).start()
    threading.Thread(target=_brain_boot, daemon=True).start()
    port = int(os.environ.get('PORT', 5002))          # le cloud (Render…) impose le port via $PORT
    # 🔒 EXPOSITION RÉSEAU INTELLIGENTE :
    #   • verrou actif (VERTEX_CODE) ou VERTEX_LAN=1 ou cloud ($PORT) → 0.0.0.0 (iPhone/LAN ok)
    #   • sinon → 127.0.0.1 SEULEMENT : sans code d'accès, le desk ne doit pas être
    #     lisible par n'importe qui sur le Wi-Fi. (Pour l'iPhone sans code : VERTEX_LAN=1.)
    #  La regle d'ecoute et la PHRASE qui l'explique ont desormais un seul
    #  proprietaire (`vertex/app/exposition.py`). Elle etait decrite ICI et sur
    #  la page Systeme a partir d'une supposition : avec `PORT` defini et sans
    #  code, ce message annoncait « VERTEX_LAN=1 — SANS code ! » en nommant une
    #  variable non definie. Le comportement d'ecoute est INCHANGE.
    from vertex.app.exposition import exposition as _exposition, phrase as _phrase
    _etat = _exposition(AUTH_ON)
    #  Lot 4 — un desk PRIVE joignable du reseau sans code ne demarre pas.
    #  L'avertissement d'hier devient un refus : la phrase nomme les trois
    #  issues (VERTEX_CODE, DEMO=1, loopback) et le processus sort en erreur.
    if _etat.get('demarrage_refuse'):
        print(_etat['raison'])
        raise SystemExit(2)
    host = _etat['hote']
    print(f'VERTEX -> http://localhost:{port}  ·  IBKR live: {IBKR_ENABLED}  (Ctrl+C pour arreter)')
    print('   ' + _phrase(_etat))
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


# démarre les threads dès l'import (pour gunicorn/cloud) si demandé, sinon en __main__
if os.environ.get('START_ON_IMPORT') == '1':
    _start_workers()

if __name__ == '__main__':
    _start_app()
