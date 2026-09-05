"""vertex.data_sources.ibkr_link — OÙ EST TWS, ET QUI A LE DROIT DE S'Y BRANCHER.

Objectif : **lancer TWS suffit**. Aucune variable à définir, aucun port à
choisir, aucun redémarrage de Vertex.

## Ce que ce module corrige, mesuré dans le code

Avant lui, cinq endroits ouvraient leur propre connexion, chacun avec ses idées :

| site | ports essayés | clientId |
| --- | --- | --- |
| worker options (`terminal.py`) | 7496, 7497, 4001, 4002 | 41 |
| lecture du compte (`terminal.py`) | **7497, 7496, 4002, 4001** | **17** |
| cotations live (`terminal.py`) | 7496, 7497, 4001, 4002 | 18 |
| indices (`terminal.py`) | 7496, 7497, 4001, 4002 | 22 |
| passerelle (`ibkr_gateway.py`) | **7497 seul** | **17** |

Trois défauts, et aucun n'est cosmétique :

1. **La lecture du compte cherchait le PAPIER en premier**, les trois autres le
   RÉEL. Quand les deux TWS sont joignables — ce qui arrive à qui teste une
   stratégie à côté de son compte réel — l'écran affiche le **cash d'un compte
   et les cotations d'un autre**, sans que rien ne le dise. C'est un mensonge
   de composition : chaque chiffre est vrai, l'écran est faux.
2. **Deux sites partageaient le clientId 17.** IBKR refuse une seconde session
   portant un identifiant déjà pris : selon l'ordre de démarrage, l'un des deux
   échouait, avec un message qui ne parle pas de collision.
3. **La passerelle n'essayait qu'un port.** Sur un TWS réel seul (7496), elle
   ne se connectait **jamais**, en silence.

## Le port qui a marché est PARTAGÉ

Chaque site redécouvrait le port pour son compte. TWS éteint, le worker options
payait 4 essais × 6 s = **24 s par job**. Une fois qu'un site a trouvé, les
autres essaient ce port **d'abord** : la connexion suivante est immédiate, et
l'échec reste borné.

Le port mémorisé est **oublié dès qu'il cesse de répondre** — un souvenir qu'on
ne remet jamais en question deviendrait un mensonge le jour où l'utilisateur
passe du papier au réel.

## Lecture seule

Ce module ne se connecte à rien lui-même : il dit **où essayer** et **avec quel
identifiant**. Le `readonly=True` reste écrit sur chaque site d'appel, là où les
garde-fous le cherchent (`tests/test_no_orders.py`) — le déplacer ici le
rendrait invisible à l'endroit qui compte.
"""
from __future__ import annotations

import os
import socket
import logging
import threading
import time

#: Ports standards d'IBKR, **réel d'abord**. Cet ordre n'est pas arbitraire :
#: c'est celui que trois des quatre sites appliquaient déjà, et le compte visé
#: par ce terminal est un compte réel. L'ordre ne compte que si PLUSIEURS TWS
#: répondent — et dans ce cas, mieux vaut que tout l'écran parle du même.
PORTS = (
    (7496, 'TWS réel'),
    (7497, 'TWS papier'),
    (4001, 'IB Gateway réel'),
    (4002, 'IB Gateway papier'),
)

#: Un identifiant par consommateur, tous distincts. IBKR refuse deux sessions
#: portant le même : la collision se manifeste par un échec de connexion dont le
#: message ne mentionne jamais la cause.
CLIENT_IDS = {
    'options': 41,      # worker options (chaînes, Greeks)
    'compte': 17,       # lecture du compte (cash, positions)
    'cotations': 18,    # flux de cotations
    'indices': 22,      # flux d'indices
    'passerelle': 19,   # vertex.data_sources.ibkr_gateway — 17 auparavant,
                        # donc en collision directe avec « compte ».
    'pnl': 25,          # souscription reqPnL. Role PROPRE : `compte` est
                        # deja tenu par le lecteur de resume, et reqPnL est
                        # une SOUSCRIPTION qui vit plus longtemps qu'une
                        # lecture — les faire cohabiter les evincerait.
    'news': 24,         # depeches du courtier. Role PROPRE : la boucle news
                        # tourne toutes les minutes, celle du scan par salves
                        # de plusieurs minutes — partager un identifiant les
                        # ferait s'evincer mutuellement.
    'historique': 23,   # barres quotidiennes de l'univers de scan. Un rôle
                        # PROPRE, et non un emprunt à « cotations » : le scan
                        # tourne par salves longues, la collision se lirait
                        # comme une panne de cotations sans rapport.
    'verification': 29, # preuve sur socket réelle (tests/test_ibkr_session_
                        # marche_seule.py, sur demande) : une session brève,
                        # jamais partagée avec un consommateur du produit.
}

MODES = dict(PORTS)

#: Échelle des types de données IBKR, du plus riche au plus tolérant.
#:
#: 1 temps réel · 2 clôture figée · 3 différé (~15 min) · 4 clôture différée.
#:
#: **Le type 2 exige toujours un abonnement.** C'est le piège : replier de 1
#: vers 2 ne règle QUE le cas « marché fermé alors qu'on est abonné ». Sans
#: abonnement, ni 1 ni 2 ne rendent quoi que ce soit — seul le **3** parle.
#: L'échelle couvre donc les quatre situations réelles :
#:
#: | abonné | marché | type qui répond |
#: | --- | --- | --- |
#: | oui | ouvert | 1 |
#: | oui | fermé  | 2 |
#: | non | ouvert | 3 |
#: | non | fermé  | 4 |
#:
#: Aucun de ces modes n'invente : `ibkr_market_data._MODE_BY_TYPE` les traduit
#: déjà en LIVE / FROZEN / DELAYED, et une puce de fraîcheur ne peut afficher
#: « Live » que pour le type 1.
ECHELLE_DONNEES = (1, 2, 3, 4)

LIBELLE_DONNEES = {
    1: 'temps réel',
    2: 'clôture figée',
    3: 'différé (~15 min)',
    4: 'clôture différée',
}


def type_suivant(actuel: int, recu: bool, *, echelle=ECHELLE_DONNEES) -> int:
    """Quel type demander ensuite, sachant si le passage a rapporté quelque chose.

    Une seule règle, partagée par les trois flux — écrire trois fois la même
    escalade produit trois escalades différentes, et c'est déjà arrivé deux
    fois dans ce produit (ordres de ports, repli hors séance).

    - quelque chose est arrivé → on ne bouge pas ;
    - rien n'est arrivé → on descend d'un cran ;
    - arrivé en bas sans rien → on **remonte au temps réel** plutôt que de
      rester coincé : si la séance a rouvert entre-temps, rester en différé
      afficherait un cours vieux de quinze minutes sans raison.
    """
    if recu:
        return actuel
    if actuel not in echelle:
        return echelle[0]
    i = echelle.index(actuel) + 1
    return echelle[i] if i < len(echelle) else echelle[0]


def libelle_donnees(t) -> str:
    """Mot lisible pour un type. Un type inconnu est avoué, jamais deviné."""
    return LIBELLE_DONNEES.get(t, 'inconnu')


_VERROU = threading.Lock()
_MEMOIRE: dict = {'port': None, 'depuis': None, 'decouvert_par': None}
_DERNIERS_ESSAIS: dict = {}


def hote() -> str:
    """`IBKR_HOST` reste respecté pour les montages inhabituels (TWS sur une
    autre machine), mais n'est JAMAIS nécessaire au cas normal."""
    return os.environ.get('IBKR_HOST', '127.0.0.1').strip() or '127.0.0.1'


def client_id(role: str) -> int:
    """Identifiant du rôle. Un rôle inconnu est une erreur franche : rendre un
    identifiant par défaut recréerait exactement la collision qu'on corrige."""
    if role not in CLIENT_IDS:
        raise KeyError('role IBKR inconnu : %r (connus : %s)'
                       % (role, ', '.join(sorted(CLIENT_IDS))))
    return CLIENT_IDS[role]


def ports_declares() -> tuple:
    """Ordre d'essai. `IBKR_PORT`, s'il est défini, passe DEVANT sans supprimer
    les autres : forcer un port ne doit pas empêcher de trouver TWS ailleurs —
    une variable oubliée dans un `.env` couperait sinon la connexion sans rien
    dire."""
    ordre = [p for p, _ in PORTS]
    force = (os.environ.get('IBKR_PORT') or '').strip()
    if force.isdigit() and int(force) in ordre:
        ordre.remove(int(force))
        ordre.insert(0, int(force))
    elif force.isdigit():
        ordre.insert(0, int(force))
    return tuple(ordre)


def ordre_des_ports() -> tuple:
    """Ce que les sites d'appel doivent parcourir : le port qui a MARCHÉ en
    tête, puis les autres. C'est ce qui rend la deuxième connexion immédiate."""
    ordre = list(ports_declares())
    connu = _MEMOIRE.get('port')
    if connu in ordre:
        ordre.remove(connu)
        ordre.insert(0, connu)
    return tuple(ordre)


def _ouvrable(port: int, hote_: str, delai: float) -> bool:
    """Le socket répond-il ? Sonde de niveau TCP : elle ne parle pas le
    protocole IBKR et n'ouvre AUCUNE session — donc rien à fermer, aucun
    clientId consommé, et aucun risque d'interférer avec une session vivante."""
    try:
        with socket.create_connection((hote_, port), timeout=delai):
            return True
    except OSError:
        return False


def sonder(ports=None, *, hote_=None, delai: float = 0.35, essai=None) -> dict:
    """Quels ports répondent, ici et maintenant.

    `essai` est injectable — c'est ce qui rend ce module éprouvable sans TWS.
    Un banc qui ne pourrait être testé qu'avec un broker réel ne serait testé
    qu'une fois, le jour où il est trop tard.
    """
    essai = essai or (lambda p: _ouvrable(p, hote_ or hote(), delai))
    ouverts = []
    for p in (ports if ports is not None else ports_declares()):
        if essai(p):
            ouverts.append(p)
    return {
        'ouverts': ouverts,
        'retenu': ouverts[0] if ouverts else None,
        'mode': MODES.get(ouverts[0]) if ouverts else None,
        'ambigu': len(ouverts) > 1,
        'hote': hote_ or hote(),
        'ordre': list(ports if ports is not None else ports_declares()),
    }


def noter_succes(port: int, role: str) -> None:
    """Un site vient de se connecter : les suivants iront droit au but."""
    with _VERROU:
        if _MEMOIRE.get('port') != port:
            _MEMOIRE.update({'port': port, 'depuis': time.time(),
                             'decouvert_par': role})
        _DERNIERS_ESSAIS[role] = {'port': port, 'ok': True, 'quand': time.time()}


def noter_echec(role: str, detail: str = '') -> None:
    """Un site n'a rien trouvé. Si personne n'y arrive plus, le souvenir du port
    est effacé : le garder ferait dire « connecté sur 7496 » à un écran qui ne
    l'est plus."""
    with _VERROU:
        _DERNIERS_ESSAIS[role] = {'port': None, 'ok': False,
                                  'quand': time.time(), 'detail': detail[:200]}
        if _DERNIERS_ESSAIS and not any(v.get('ok') for v in _DERNIERS_ESSAIS.values()):
            _MEMOIRE.update({'port': None, 'depuis': None, 'decouvert_par': None})


def etat() -> dict:
    """État lisible, sans rien affirmer que la mesure ne montre.

    `raison` n'est pas décorative : c'est elle qui transforme « ça ne marche
    pas » en geste à faire.
    """
    with _VERROU:
        port = _MEMOIRE.get('port')
        essais = dict(_DERNIERS_ESSAIS)
        depuis = _MEMOIRE.get('depuis')
    roles_ok = sorted(r for r, v in essais.items() if v.get('ok'))
    if port:
        raison = ''
    elif not essais:
        raison = ('Aucune tentative de connexion n\'a encore eu lieu — les flux '
                  'démarrent quelques secondes après le lancement.')
    else:
        raison = ('TWS / IB Gateway ne répond sur aucun des ports standards '
                  '(%s). Vérifier que TWS est lancé et que l\'API est activée '
                  '(Configuration → API → Enable ActiveX and Socket Clients), '
                  'avec 127.0.0.1 dans les adresses autorisées.'
                  % ', '.join(str(p) for p in ports_declares()))
    return {
        'port': port,
        'mode': MODES.get(port) if port else None,
        'hote': hote(),
        'depuis': depuis,
        'age_s': round(time.time() - depuis, 1) if depuis else None,
        'decouvert_par': _MEMOIRE.get('decouvert_par'),
        'roles_connectes': roles_ok,
        'roles_en_echec': sorted(r for r, v in essais.items() if not v.get('ok')),
        'ports_essayes': list(ports_declares()),
        'raison': raison,
    }


def oublier() -> None:
    """Remet le module à zéro (bancs d'essai, et bascule papier ↔ réel)."""
    with _VERROU:
        _MEMOIRE.update({'port': None, 'depuis': None, 'decouvert_par': None})
        _DERNIERS_ESSAIS.clear()


#  ── LE JOURNAL DU COURTIER : DIRE UNE FOIS, PAS CINQUANTE ──────────────────
#
#  Sans TWS ouvert, `ib_async` écrit DEUX lignes par tentative et par port, sur
#  quatre ports, pour quatre workers, en boucle. Mesuré à un premier lancement
#  sans TWS : **168 lignes** « API connection failed: ConnectionRefusedError »
#  en une minute. Le message est en anglais, il est vrai, et il est illisible :
#  quelqu'un qui lance Vertex pour la première fois y voit une application
#  cassée alors que l'état est parfaitement normal.
#
#  Ce filtre NE TAIT RIEN QUI NE SOIT DÉJÀ DIT AILLEURS. La première occurrence
#  passe, traduite et complète ; les répétitions sont comptées et le compte est
#  lisible (`repetitions_tues()`). L'état lui-même vit dans `etat()` et sur la
#  page Système → Connexions, qui dit « IBKR non activé (aucune session
#  TWS/Gateway détectée) ». Ce qui disparaît, c'est la répétition, pas
#  l'information.
#
#  Tout message du courtier qui n'est PAS cette répétition passe intact : un
#  refus de permission, une collision de clientId ou une erreur de marché doit
#  rester visible mot pour mot.
_REPETITIONS = ('API connection failed', 'Make sure API port')

_PREMIERE = ("TWS / IB Gateway injoignable sur %s — c'est l'etat NORMAL sans "
             "session courtier ouverte. Vertex sert les donnees differees "
             "(yfinance) et le dit sur chaque valeur. Statut detaille : "
             "page Systeme > Connexions.")


class _FiltreRepetitions(logging.Filter):
    """Laisse passer la première, compte les suivantes."""

    def __init__(self) -> None:
        super().__init__()
        self.tues = 0
        self._dit = False
        self._v = threading.Lock()

    def filter(self, record) -> bool:        # noqa: A003  (API de logging)
        try:
            message = record.getMessage()
        except Exception:                    # noqa: BLE001  un record exotique passe
            return True
        if not any(m in message for m in _REPETITIONS):
            return True                      # tout le reste : INTACT
        with self._v:
            if self._dit:
                self.tues += 1
                return False
            self._dit = True
        record.msg = _PREMIERE % ', '.join(str(p) for p in ordre_des_ports())
        record.args = ()
        record.levelno = logging.WARNING
        record.levelname = 'WARNING'
        return True


_FILTRE = _FiltreRepetitions()
_POSE = False


def calmer_le_journal_du_courtier() -> bool:
    """Installe le filtre sur les journaux du courtier. Idempotent.

    Rend `True` s'il vient d'être posé, `False` s'il l'était déjà — un appelant
    ne peut donc pas croire l'avoir posé deux fois."""
    global _POSE
    with _VERROU:
        if _POSE:
            return False
        for nom in ('ib_async', 'ib_async.client', 'ib_insync', 'ib_insync.client'):
            logging.getLogger(nom).addFilter(_FILTRE)
        _POSE = True
        return True


def repetitions_tues() -> int:
    """Combien de répétitions ont été retenues. Jamais perdu, seulement compté."""
    return _FILTRE.tues


__all__ = ['PORTS', 'CLIENT_IDS', 'MODES', 'ECHELLE_DONNEES',
           'calmer_le_journal_du_courtier', 'repetitions_tues',
           'LIBELLE_DONNEES', 'type_suivant', 'libelle_donnees', 'hote', 'client_id', 'ports_declares',
           'ordre_des_ports', 'sonder', 'noter_succes', 'noter_echec', 'etat',
           'oublier']
