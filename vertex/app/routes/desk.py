"""
vertex/app/routes/desk.py — DESK PERSO (Blueprint, Ch. II).

Les routes du poste de travail personnel : synchronisation du desk entre
appareils (/api/desk), export TradingView de l'univers (/api/watchlist-tv)
et cotation en direct des trades perso (/api/pos-quotes).

(/api/ticker/<sym> vit dans terminal.py : sa version enrichie — profil
d'entreprise + comparaison aux pairs — a remplacé la version simple.)

Les dépendances lourdes du monolithe (pack options réseau, file de jobs IBKR)
sont INJECTÉES à la construction — le Blueprint reste testable sans réseau.

⛔ Lecture seule : ces routes lisent et cotent, ne passent JAMAIS d'ordre.
"""

import glob
import json
import os
import shutil
import threading
import time
from datetime import datetime

from flask import Blueprint, jsonify, request

from vertex.data.universe import UNIVERSE
from vertex.scheduler import registry as _sched
from vertex.services import persist

BACKUP_KEEP = 7   # rotations quotidiennes conservées

#: Instantanés « avant perte » conservés (voir `_snapshot_avant_perte`). Plus
#: nombreux que les quotidiens : ils sont rares par construction — un seul est
#: pris par épisode de perte — et chacun correspond à un incident réel.
AVANT_PERTE_KEEP = 20

#: Valeurs qui ne représentent AUCUN travail. Leur disparition ne fait rien
#: perdre, donc elle n'a pas à être protégée : une liste vide reste une liste
#: vide. Tout le reste compte, y compris un JSON qu'on ne sait pas relire —
#: c'est bien la raison de ne pas l'effacer.
_VIDES = ('', '[]', '{}', 'null', '""', "''")


def _porte_du_travail(valeur) -> bool:
    """La valeur, si elle disparaissait, ferait-elle perdre quelque chose ?"""
    if valeur is None:
        return False
    if not isinstance(valeur, str):
        try:
            valeur = json.dumps(valeur, ensure_ascii=False)
        except Exception:
            return True          # illisible ≠ vide : dans le doute, on protège
    return valeur.strip() not in _VIDES


def _snapshot_avant_perte(blob) -> str | None:
    """Instantané SUPPLÉMENTAIRE, pris au moment précis d'une perte annoncée.

    Le filet quotidien (`_backup_desk`) prend son image **avant la première
    écriture du jour** : restaurer depuis lui rend l'état d'hier et perd tout le
    travail de la journée (mesuré au lot 362). Celui-ci comble exactement ce
    trou — il capture l'état *juste avant* que des clés ne soient menacées, donc
    à la seconde près plutôt qu'à la journée près."""
    try:
        horodatage = datetime.now().strftime('%Y%m%d-%H%M%S')
        nom = 'desk_avantperte_%s.json' % horodatage
        persist.save_json(nom, blob)
        vieux = sorted(glob.glob(persist.cache_path('desk_avantperte_*.json')))
        for p in vieux[:-AVANT_PERTE_KEEP]:
            os.remove(p)
        return nom
    except OSError:
        #  Un instantané impossible (disque plein, droits) ne doit pas faire
        #  échouer la sync : les clés menacées sont de toute façon CONSERVÉES
        #  par la fusion ci-dessous — l'instantané est une seconde ceinture.
        return None


def _backup_desk():
    """Snapshot QUOTIDIEN de desk_data.json avant écrasement (1er write du jour).
    Filet de sécurité contre le last-writer-wins : positions/journal/alertes
    restaurables sur 7 jours. Silencieux — ne bloque jamais la sync."""
    try:
        src = persist.cache_path('desk_data.json')
        if not os.path.exists(src) or os.path.getsize(src) < 20:
            return
        day = datetime.now().strftime('%Y%m%d')
        dst = persist.cache_path('desk_backup_%s.json' % day)
        if os.path.exists(dst):
            return                                   # déjà sauvegardé aujourd'hui
        shutil.copyfile(src, dst)
        #  L'import est remonté en tête du module : un `beat` n'écrit que dans un
        #  dict sous verrou et ne lève pas. Le `try/except: pass` qui l'entourait
        #  ne protégeait donc que de l'import — mieux vaut qu'un import cassé
        #  éclate au démarrage qu'il ne se taise à chaque sauvegarde.
        _sched.beat('DATA_BACKUP', ok=True)
        olds = sorted(glob.glob(persist.cache_path('desk_backup_*.json')))
        for p in olds[:-BACKUP_KEEP]:
            os.remove(p)
    except Exception as e:
        #  L'ECHEC ETAIT MUET. Le battement ne vivait que sur le chemin de
        #  succes : une copie qui echoue — disque plein, permission, fichier
        #  verrouille — ne disait RIEN. Le job tombait « SILENCIEUX » au bout
        #  de deux jours, sans raison, et la sauvegarde du desk s'arretait sans
        #  que personne l'apprenne. C'est le genre de panne qu'on decouvre au
        #  moment ou l'on a besoin du backup.
        try:
            _sched.beat('DATA_BACKUP', ok=False,
                        error='%s: %s' % (type(e).__name__, e))
        except Exception:
            pass

POSQ_TTL_S = 45          # fraîcheur d'une cotation de trade perso
#  Attente MAXIMALE d'une requête pour une clé jamais cotée : le worker IBKR
#  répond d'ordinaire en moins d'une seconde ; au-delà, la requête rend le
#  repli étiqueté et nomme les clés encore en cours (`en_attente`).
POSQ_ATTENTE_S = float(os.environ.get('VERTEX_POSQ_ATTENTE_S', '1.5'))
POSQ_MAX_POSITIONS = 24  # borne dure par requête


def completer_par_repli(todo, out, repli):
    """Comble les positions ACTION encore sans cotation, depuis une source déjà
    en mémoire. Fonction PURE — c'est par elle que les témoins passent.

    Le défaut qu'elle corrige, reproduit localement : sans IBKR (ou si le worker
    ne rend rien), `/api/pos-quotes` renvoyait `results: {}`. Le client en
    déduisait `ok = false` et n'affichait AUCUN P&L — alors que le produit avait
    le prix en mémoire (scan yfinance). Une valeur connue restait invisible
    parce qu'un seul fournisseur était consulté.

    Les OPTIONS ne sont pas comblées : le scan ne cote pas de contrats, et
    fabriquer un prix d'option à partir du sous-jacent serait exactement la
    donnée inventée que le produit interdit. Elles restent absentes, donc
    honnêtement `—`.

    Chaque valeur de repli porte `source` : sans étiquette, un cours de scan se
    ferait passer pour une cotation broker.
    """
    if not repli:
        return 0
    combles = 0
    for p in todo:
        if not isinstance(p, dict):
            continue
        cle = p.get('key')
        if not cle or cle in out:
            continue
        if (p.get('right') or '').upper() in ('C', 'P'):
            continue                                   # option : jamais comblée
        sym = (p.get('sym') or '').upper()
        try:
            v = repli(sym)
        except Exception:                              # noqa: BLE001
            v = None
        #  LA PRIORITE N'EST PAS DECIDEE ICI. Elle vient de
        #  `source_router.PRIORITY`, seule table de priorite du produit, via
        #  `cotation_unifiee`. Un `if broker sinon scan` ecrit ici serait la
        #  troisieme regle de priorite du depot — et les deux precedentes
        #  (ordres de ports, escalades de type de donnees) ont diverge.
        from vertex.data_sources.cotation_unifiee import (
            en_charge_client, resoudre_cotation,
        )
        charge = en_charge_client(resoudre_cotation(broker=None, secondaire=v))
        if charge is None:
            continue
        out[cle] = charge
        combles += 1
    return combles


def _scan_fallback_quote(p):
    """Marque DIFFÉRÉE d'une position quand IBKR ne cote pas (TWS fermé).

    Actions : prix du scan (yfinance différé). Options : mid du contrat
    correspondant du board (sym + droit + strike, échéance par préfixe —
    le desk stocke 'YYYY-MM', le board 'YYYY-MM-DD'). Étiquetée delayed:True
    pour que l'UI l'affiche « différé » — un titre absent du scan reste sans
    marque (aucun chiffre inventé).
    """
    from vertex.app.state import scan_state
    sym = (p.get('sym') or '').upper()
    if not sym:
        return None
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    spot = detail.get('price')
    right = (p.get('right') or '').upper()
    is_opt = bool(right or p.get('strike') is not None)
    q = {}
    if isinstance(spot, (int, float)) and spot > 0:
        q['spot'] = spot
    if is_opt:
        want_type = 'PUT' if right.startswith('P') else 'CALL'
        want_exp = str(p.get('exp') or '')
        try:
            want_strike = float(p.get('strike'))
        except (TypeError, ValueError):
            want_strike = None
        for c in (scan_state.get('options_board') or []):
            if (str(c.get('sym', '')).upper() == sym
                    and c.get('type') == want_type
                    and c.get('mid') is not None
                    and want_strike is not None
                    and abs(float(c.get('strike') or 0) - want_strike) < 0.01
                    and (not want_exp or str(c.get('exp', '')).startswith(want_exp))):
                q['mark'] = c.get('mid')
                break
        if 'mark' not in q and want_strike is not None:
            # Le board n'a que les « meilleurs » strikes — marque du contrat
            # EXACT détenu depuis le CACHE de chaîne (on_demand) ; une lecture
            # manquante part en fond, jamais dans la requête utilisateur.
            try:
                from vertex.options import on_demand as _od
                mk = _od.contract_mark(sym, want_exp, want_strike,
                                       'P' if right.startswith('P') else 'C',
                                       reseau=False)
                if mk is not None:
                    q['mark'] = mk
            except Exception:
                pass
    if not q:
        return None
    q['delayed'] = True
    q['src'] = 'scan'
    return q


def make_blueprint(*, opt_job, ibkr_enabled, cotation_repli=None):
    """Construit le Blueprint du desk.

    opt_job(kind, args, timeout): job IBKR sérialisé (None si indisponible).
    ibkr_enabled                : cotations live possibles (sinon cache seul).
    cotation_repli(symbole)     : dernier recours pour une ACTION, rendant
                                  {'spot':…, 'spot_chg':…} ou None. Injecté —
                                  le blueprint ne doit pas savoir d'où vient
                                  cette valeur, et l'injection le rend
                                  éprouvable sans serveur.
    """
    bp = Blueprint('desk', __name__)
    desk_lock = threading.Lock()
    posq_cache = {}      # cotations des trades perso : {key: (ts, data)} — TTL 45 s
    #  Lot 6 — les crochets vivent SUR le blueprint (bp._vx_hooks), pas dans
    #  un global de module : chaque application construite porte les siens, et
    #  un banc les atteint par app.blueprints['desk']._vx_hooks sans polluer
    #  les autres. Un global s'etait fait ecraser par le premier banc venu.
    hooks = {'posq_cache': posq_cache, 'opt_job': opt_job,
             'ibkr_enabled': ibkr_enabled}
    bp._vx_hooks = hooks

    def _demo_exposee_sans_code():
        """Vrai seulement pour l'instance publique de demonstration."""
        from vertex.app.config import AUTH_ON as _auth, DEMO_MODE as _demo
        from vertex.app.exposition import exposition as _expo
        return bool(_demo and _expo(_auth)['ouvert_au_reseau'] and not _auth)

    @bp.route('/api/desk', methods=['GET', 'POST'])
    def api_desk():
        """Synchronisation du desk perso (trades, journal, favoris, capital, simulateur) entre appareils.
        Stockage local dans desk_data.json — dernier écrivain gagne (blob complet + timestamp)."""
        if request.method == 'POST':
            #  Lot 4 — demo EXPOSEE non persistante : un desk public en
            #  ecriture est un tableau blanc mondial. La LECTURE reste servie
            #  (la demo se visite), la demo LOCALE (loopback) continue
            #  d'ecrire — c'est le mode de travail quotidien. Le refus est
            #  honnete : ok:false nomme, jamais un faux succes ni une 500.
            if _demo_exposee_sans_code():
                return jsonify({'ok': False, 'demo_exposee': True,
                                'err': 'Demo publique : rien n\'est '
                                       'enregistre sur ce serveur.'}), 200
            body = request.get_json(force=True, silent=True) or {}
            if not isinstance(body.get('data'), dict) or not body.get('ts'):
                return jsonify({'ok': False, 'err': 'payload invalide'}), 400
            with desk_lock:
                #  ── UN PUSH NE PEUT PLUS EFFACER CE QU'IL N'ENVOIE PAS ──────
                #  Mesuré au lot 362 : le last-writer-wins était TOTAL, donc un
                #  push partiel — ou `data: {}` — remplaçait le blob entier et
                #  les clés absentes disparaissaient. Le scénario n'est pas
                #  théorique : le client omet toute clé absente de localStorage
                #  (`if (v != null)` dans vx-entities.js), et un navigateur dont
                #  l'écriture localStorage échoue en silence (navigation privée,
                #  quota) hydrate sans rien persister, puis pousse `{}`.
                #
                #  UNE CLÉ ABSENTE NE VEUT JAMAIS DIRE « SUPPRIMÉE » : aucun
                #  chemin du produit n'appelle `removeItem` sur une clé de desk
                #  (vérifié) — vider une liste écrit `'[]'`, qui est bien envoyé.
                #  Une absence est donc toujours un défaut de lecture, jamais une
                #  intention. On la traite comme telle : on conserve.
                ancien = persist.load_json('desk_data.json', {}) or {}
                ancien_data = ancien.get('data')
                if not isinstance(ancien_data, dict):
                    ancien_data = {}
                fusion = dict(body['data'])
                conservees = sorted(k for k, v in ancien_data.items()
                                    if k not in fusion and _porte_du_travail(v))
                instantane = None
                if conservees:
                    #  Instantané À LA SECONDE, en plus du filet quotidien qui,
                    #  lui, remonte à avant la première sync du jour.
                    instantane = _snapshot_avant_perte(ancien)
                    for k in conservees:
                        fusion[k] = ancien_data[k]
                _backup_desk()                       # snapshot quotidien AVANT écrasement
                persist.save_json('desk_data.json', {'ts': body['ts'], 'data': fusion})
            #  La conservation est DITE, pas silencieuse : un client qui perd
            #  son localStorage doit pouvoir s'en apercevoir.
            return jsonify({'ok': True, 'ts': body['ts'],
                            'conservees': conservees,
                            'instantane': instantane})
        with desk_lock:
            d = persist.load_json('desk_data.json', {}) or {}
        return jsonify(d)

    @bp.route('/api/desk/backups')
    def api_desk_backups():
        """Liste les instantanés du desk (restaurables), les deux familles.

        `quotidien` remonte à avant la première sync du jour ; `avant-perte` est
        pris à la seconde, au moment où un push allait faire disparaître des
        clés. Les lister ensemble n'est pas cosmétique : un instantané qu'aucune
        sortie ne nomme n'est pas un filet, c'est un fichier."""
        out = []
        for p in sorted(glob.glob(persist.cache_path('desk_backup_*.json')), reverse=True):
            nom = os.path.basename(p)
            out.append({'name': nom, 'date': nom[12:20], 'type': 'quotidien',
                        'size': os.path.getsize(p)})
        for p in sorted(glob.glob(persist.cache_path('desk_avantperte_*.json')),
                        reverse=True):
            nom = os.path.basename(p)
            out.append({'name': nom, 'date': nom[16:24], 'heure': nom[25:31],
                        'type': 'avant-perte', 'size': os.path.getsize(p)})
        return jsonify({'backups': out, 'keep': BACKUP_KEEP,
                        'keep_avant_perte': AVANT_PERTE_KEEP})

    @bp.route('/api/desk/restore', methods=['POST'])
    def api_desk_restore():
        """Restaure un snapshot quotidien → desk_data.json (ts=maintenant, donc
        tous les appareils re-tireront cette version). Nom STRICTEMENT validé."""
        #  Lot 4 — meme garde que l'ecriture : restaurer EST ecrire.
        if _demo_exposee_sans_code():
            return jsonify({'ok': False, 'demo_exposee': True,
                            'err': 'Demo publique : rien n\'est enregistre '
                                   'sur ce serveur.'}), 200
        name = str((request.get_json(force=True, silent=True) or {}).get('name') or '')
        import re
        #  Deux familles, une seule grammaire de chaque — le nom reste
        #  STRICTEMENT validé (aucun séparateur de chemin possible).
        if not (re.fullmatch(r'desk_backup_\d{8}\.json', name)
                or re.fullmatch(r'desk_avantperte_\d{8}-\d{6}\.json', name)):
            return jsonify({'ok': False, 'err': 'nom invalide'}), 400
        src = persist.cache_path(name)
        if not os.path.exists(src):
            return jsonify({'ok': False, 'err': 'backup introuvable'}), 404
        with desk_lock:
            snap = persist.load_json(name, None)
            if not snap or not isinstance(snap.get('data'), dict):
                return jsonify({'ok': False, 'err': 'backup illisible'}), 500
            persist.save_json('desk_data.json', {'ts': int(time.time() * 1000), 'data': snap['data']})
        return jsonify({'ok': True, 'restored': name})

    @bp.route('/api/journal/postmortem')
    def api_journal_postmortem():
        """POST-MORTEM du journal : stats réelles + drapeaux de discipline depuis les
        trades clôturés du desk (myTradesClosed + vxJournal). Descriptif, pas un
        conseil. Lecture seule — aucun ordre."""
        import json as _json
        from vertex.engines import postmortem as _pm
        blob = persist.load_json('desk_data.json', {}) or {}
        data = blob.get('data') or {}

        def _parse(key):
            raw = data.get(key)
            try:
                v = _json.loads(raw) if isinstance(raw, str) else (raw or [])
                return v if isinstance(v, list) else []
            except Exception:
                return []
        return jsonify(_pm.build(_parse('myTradesClosed'), _parse('vxJournal')))

    @bp.route('/api/watchlist-tv')
    def api_watchlist_tv():
        """Univers du desk au format TradingView (à coller dans une watchlist TV pour rester synchronisé)."""
        syms = list(UNIVERSE)
        return jsonify({'count': len(syms), 'symbols': syms, 'tv': ','.join(syms)})

    #  Lot 2 — la route d'import des positions du COMPTE est RETIRÉE.
    #  « Lecture seule » protegait de l'ordre, pas de la confidentialite : lire
    #  le portefeuille du courtier reste lire le compte. Le portefeuille de
    #  Vertex est celui que l'utilisateur declare ; les positions historiques
    #  deja importees restent lisibles dans le desk — on retire la capacite,
    #  pas les donnees acceptees.

    @bp.route('/api/pos-quotes', methods=['POST'])
    def api_pos_quotes():
        """Cote en direct les TRADES PERSO saisis sur la page Ma Stratégie (actions + options).
        Body : {positions:[{sym, exp?, strike?, right?}]} — exp 'YYYY-MM' acceptée (résolue au vrai jour).
        ⛔ Lecture seule : cote les contrats, ne passe JAMAIS d'ordre."""
        body = request.get_json(force=True, silent=True) or {}
        poss = (body.get('positions') or [])[:POSQ_MAX_POSITIONS]
        now = time.time()
        # purge des cotations périmées : le cache reste borné (pas de fuite mémoire
        # au fil des contrats cotés sur des semaines d'usage)
        for k in [k for k, (ts, _) in posq_cache.items() if now - ts > 20 * POSQ_TTL_S]:
            posq_cache.pop(k, None)
        #  L'etat broker se lit de l'instance : un banc doit pouvoir simuler
        #  « IBKR actif » sans ouvrir de socket.
        broker_actif = bool(hooks['ibkr_enabled'])
        todo, out, perimees = [], {}, []
        for p in poss:
            if not isinstance(p, dict):
                continue
            key = '%s|%s|%s|%s' % ((p.get('sym') or '').upper(), p.get('exp') or '',
                                   p.get('strike') if p.get('strike') is not None else '',
                                   (p.get('right') or '').upper())
            p['key'] = key
            c = posq_cache.get(key)
            if c and now - c[0] < POSQ_TTL_S:
                out[key] = c[1]
            elif c:
                #  Lot 6 — servir le PERIME immediatement, etiquete, plutot que
                #  payer jusqu'a 45 s de file worker (20/33/56 s mesurees) pour
                #  une cle deja en memoire. Le rafraichissement part derriere.
                out[key] = c[1]
                perimees.append((key, p))
            else:
                todo.append(p)
        if perimees and broker_actif:
            def _rafraichir(lots=list(perimees)):
                res = hooks['opt_job']('posq', ([p for _, p in lots],),
                                           timeout=45) or {}
                t2 = time.time()
                for k, v in res.items():
                    if v is not None:
                        posq_cache[k] = (t2, v)
            threading.Thread(target=_rafraichir, daemon=True).start()
        en_attente = []
        if todo and broker_actif:
            #  Une cle JAMAIS cotee part au worker EN FOND ; la requete n'attend
            #  que POSQ_ATTENTE_S (mesure : 20/33/56 s de file au pire, avant).
            #  Au-dela, le repli etiquete ci-dessous prend la main, `en_attente`
            #  nomme les cles encore en cours et le prochain passage lit le
            #  cache que le worker aura rempli. Aucun reseau lent dans la
            #  requete utilisateur (contrat CLAUDE.md).
            boite = {}

            def _coter(lots=list(todo)):
                res = hooks['opt_job']('posq', (lots,), timeout=45) or {}
                t2 = time.time()
                for k, v in res.items():
                    if v is not None:
                        posq_cache[k] = (t2, v)
                boite.update(res)
            th = threading.Thread(target=_coter, daemon=True)
            th.start()
            th.join(POSQ_ATTENTE_S)
            for k, v in list(boite.items()):
                if v is not None:
                    out[k] = v
            en_attente = [p.get('key') for p in todo if p.get('key') not in out]
        #  INTEGRATION main + vertex-live. Les deux branches avaient ecrit un
        #  repli pour TWS ferme, et chacune tenait une moitie du probleme :
        #
        #   * live couvrait ACTIONS *et* OPTIONS — l'option par le mid REEL du
        #     contrat du board, pas un prix derive du sous-jacent ; le refus de
        #     main visait la derivation, pas la lecture d'une cotation existante ;
        #   * main refusait de METTRE LE REPLI EN CACHE — un cours de scan range
        #     dans le cache des cotations courtier serait servi a la place d'une
        #     vraie cotation pendant tout le TTL, meme apres le retour de TWS.
        #
        #  On garde la couverture de live et la regle de main.
        #  1. Repli ACTIONS de `main` — fonction PURE, etiquetee SECONDARY, et
        #     tenue par des temoins : sans etiquette, un cours de scan se fait
        #     passer pour une cotation broker.
        combles = completer_par_repli(todo, out, cotation_repli)
        #  2. Repli OPTIONS de `vertex-live` — le mid REEL du contrat du board.
        #     `completer_par_repli` refuse deliberement les options : il ne sait
        #     que deriver du sous-jacent, ce qui serait un prix invente. Lire le
        #     mid d'un contrat COTE est autre chose, et c'est ce que live fait.
        for p in todo:
            k = p.get('key')
            if k and k not in out:
                fb = _scan_fallback_quote(p)
                if fb:
                    out[k] = fb          # servi, JAMAIS mis en cache
        #  #779/G1 — POSITION_REFRESH etait declare au registre des jobs mais
        #  n'avait AUCUN emetteur : la page Systeme l'affichait « jamais
        #  execute » alors qu'il tourne a chaque cotation du portefeuille.
        _sched.beat('POSITION_REFRESH', ok=True,
                    duration_ms=(time.time() - now) * 1000.0)
        #  La PROVENANCE de chaque marque, calculee par la fonction PARTAGEE avec
        #  le serveur. Perdue lors de l'integration de `vertex-live` — cette
        #  branche n'a jamais eu le lot de la marque visible — et rendue ici.
        #
        #  Mesure du 24 aout 2026 : sur URA 20270115 C 50, marche 3,50/4,30, la
        #  marque valait 3,70 — le dernier echange — sans que rien ne le dise, ce
        #  qui rendait inexplicable un ecart de 272 USD avec le courtier.
        from vertex.positions.calculator import source_de_marque
        for _k, _q in out.items():
            if not isinstance(_q, dict):
                continue
            _b, _a = _q.get('bid'), _q.get('ask')
            _mid = round((_b + _a) / 2, 4) if (_b and _a) else None
            #  Une cotation d'ACTION servie par le repli ne porte qu'un `px` :
            #  aucune convention de marque ne s'y applique. Lui coller une
            #  provenance « ABSENTE » serait doublement faux — le prix EXISTE, et
            #  l'origine n'est pas manquante, elle est hors sujet.
            if _q.get('mark') is None and _mid is None:
                continue
            if _mid is not None and _q.get('mid') is None:
                _q['mid'] = _mid
            _q['mark_source'] = source_de_marque(
                _q.get('mark'), last=_q.get('last'), close=_q.get('close'),
                mid=_mid)
            #  Un marche large rend TOUTE convention de marque incertaine.
            _q['spread_pct'] = (round((_a - _b) / _mid * 100, 2)
                                if (_mid and _b and _a) else None)
        #  `live` disait « IBKR configuré » : un P&L sur clôture de la veille
        #  passait pour du temps réel. Il dit désormais « des cotations IBKR
        #  récentes ont été servies » (preuve `ibkr_live` posée par ibkr_state).
        from vertex.app.state import scan_state as _etat_scan
        return jsonify({'results': out,
                        'en_attente': en_attente,
                        'live': bool(ibkr_enabled and _etat_scan.get('ibkr_live')),
                        'ibkr_configure': bool(ibkr_enabled),
                        'fallback_used': bool(combles), 'ts': int(now),
                        #  Lot 6 — les cles servies depuis un cache au-dela du
                        #  TTL : l'UI peut etiqueter « cote conservee » au lieu
                        #  de laisser un age faux passer pour frais.
                        'stale': [k for k, _ in perimees]})

    return bp


__all__ = ['make_blueprint', 'completer_par_repli', 'POSQ_TTL_S',
           'POSQ_MAX_POSITIONS']
