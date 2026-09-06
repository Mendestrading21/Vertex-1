"""vertex.scheduler.registry — registre des jobs de fond (§24).

Les boucles historiques de terminal.py restent les exécutants (aucun
re-threading risqué) : elles se DÉCLARENT ici et émettent un battement
(`beat`) à chaque exécution. Le registre expose statut, dernière exécution,
prochaine exécution estimée, durée et dernier résultat — pour la vue
Système/Automatisations et le rapport de démarrage. Priorité produit :
positions ouvertes > stops > options > risques > décisions > opportunités >
univers (l'ordre d'affichage reflète cette priorité).
"""
from __future__ import annotations

import contextlib
import time
import threading

_LOCK = threading.Lock()

#: Naissance du processus : une attente a une durée maximale. Sans ce repère,
#: `EN_ATTENTE` (« implémenté, pas encore passé depuis le démarrage ») n'expire
#: jamais — mesuré sur l'instance sans TWS : `MARKET_RADAR_REFRESH`, cadence
#: 240 s, affichait « en attente / 0 exécution » après 16 min d'uptime (4× sa
#: cadence) parce que son thread n'est créé que sous `if IBKR_ENABLED:`.
#: `SILENCIEUX` ne pouvait pas prendre le relais : il exige un `last_run`.
_DEMARRAGE = time.time()

# Jobs canoniques (nom → métadonnées). interval_s = cadence NOMINALE de la
# boucle historique ; les jobs « événement » ont interval_s None.
_JOBS: dict[str, dict] = {}

#  Cadence du scan, DÉRIVÉE de son unique propriétaire au lieu d'être
#  recopiée. Elle valait 360 s ici pour une boucle à 1800 : deux nombres
#  pour une seule vérité, et c'est toujours le duplicata qui dérive.
#  `vertex.data.constants` n'importe que `vertex.version`, qui n'importe
#  rien : aucun cycle possible.
from vertex.data.constants import REFRESH_SEC as _REFRESH_SEC  # noqa: E402

#  ── LA QUATRIÈME COLONNE : `implemente` (Vertex Test 1.0, #779/G1) ──────────────
#  Elle a été ajoutée parce que la mesure a contredit le registre. Le registre
#  ne reçoit d'information que par `beat('NOM')` ; or
#  `tools/mesures/mesurer_registre_jobs.py` a énuméré à l'AST TOUS les appels
#  `beat` du dépôt et trouvé **7 émetteurs pour 27 jobs déclarés**. Les 20 autres
#  ne pouvaient pas tourner : aucun code ne porte leur nom.
#
#  L'interface, elle, affichait « jamais exécuté » pour les 27 — le même mot
#  pour un job en panne et pour un job qui n'existe pas — et le pied de page
#  affirmait qu'ils « dépendent d'intégrations absentes dans cet
#  environnement ». C'était faux : ils ne dépendent de rien, ils n'ont pas
#  d'exécutant. Une affirmation invérifiable présentée comme un diagnostic.
#
#  `implemente=False` n'est donc pas un aveu de dette : c'est la seule
#  description honnête d'une intention non encore réalisée. Le drapeau n'est pas
#  déclaratif au sens faible — `tests/test_registre_jobs.py` le
#  confronte à la mesure dans les DEUX sens : marquer un job implémenté sans
#  émetteur échoue, et poser un émetteur sans lever le drapeau échoue aussi.
_CANONICAL_4 = (
    ('STARTUP_HEALTH_CHECK', 'Vérification des connexions au démarrage', None, True),
    ('POSITION_REFRESH', 'Cotation des positions déclarées (pos-quotes)', None, True),
    ('OPTION_POSITION_REFRESH', 'Chaînes options IBKR (lecture seule)', 300, False),
    #  360 -> REFRESH_SEC (1800). MESURÉ SUR LE REGISTRE : l'état SILENCIEUX
    #  tombe dès 2 x la cadence annoncée, soit 720 s, alors que le scan ne
    #  repasse qu'à 1800 s. Le job CENTRAL du produit était donc déclaré
    #  « la boucle est morte ou coincée » pendant 1080 s de chaque cycle —
    #  60 % du temps — en tournant parfaitement.
    ('MARKET_DATA_REFRESH', 'Scan univers + indices + contexte marché',
     _REFRESH_SEC, True),
    ('PORTFOLIO_RECALCULATION', 'Risque portefeuille sur positions réelles', None, False),
    ('DECISION_RECALCULATION', 'Décisions exécutives (par requête/à la demande)', None, False),
    #  3600 -> 10800 : la cadence annoncee etait le TIERS de la boucle reelle
    #  (`time.sleep(3 * 3600)` en reel, `wait_force('calendar', 3 * 3600)` en
    #  demo). Deux consequences, toutes deux fausses a l'ecran : un ETA
    #  « prochaine dans ~1 h » pour un job qui repasse dans trois, et surtout
    #  l'etat SILENCIEUX des que 2 x 3600 s etaient passees — soit a chaque
    #  cycle, une alarme permanente sur un job sain. Meme famille que
    #  NEWS_REFRESH et POSITION_REFRESH ; il en restait un.
    ('CATALYST_REFRESH', 'Calendrier earnings + macro', 3 * 3600, True),
    ('NEWS_REFRESH', 'Fil de nouvelles assaini', 60, True),
    #  AJOUT : la boucle des fondamentaux tournait sans AUCUNE ligne a
    #  l'ecran — elle empruntait le battement de `TRACK_RECORD_UPDATE`,
    #  le job d'une autre boucle. Elle a desormais le sien. Cadence : la
    #  boucle dort 45 s tant qu'il manque des titres, puis 6 h ; on
    #  annonce la cadence de CROISIERE, celle qui vaut une fois le cache
    #  rempli — annoncer 45 s ferait crier SILENCIEUX pendant six heures.
    ('FUNDAMENTALS_REFRESH', 'Fondamentaux P/E + médianes secteur', 6 * 3600, True),
    #  AJOUT : `_opt_loop` rafraîchit le board d'options toutes les 120 s
    #  — rotation de l'univers puis focus — et AUCUNE ligne de la page
    #  Système ne la représentait. `OPTION_POSITION_REFRESH` existe
    #  au-dessus, mais décrit la cotation des POSITIONS options :
    #  l'emprunter aurait refait la faute corrigée sur
    #  `TRACK_RECORD_UPDATE` — parler au nom d'un autre travail.
    ('OPTIONS_BOARD_REFRESH', 'Board options — rotation univers + focus', 120, True),
    #  AJOUT : `_radar_loop` interroge les scanners du marché ENTIER
    #  (gainers, losers, most active) et le fil Dow Jones / Briefing
    #  toutes les 240 s — la dernière boucle cadencée du produit qui
    #  n'avait aucune ligne à l'écran.
    ('MARKET_RADAR_REFRESH', 'Radar marché entier + fil courtier', 240, True),
    #  AJOUT (mission alimentation 2026-09-06) : références macro OFFICIELLES
    #  (FRED, BCE, BNS) collectées par `vertex/services/macro_officiel.py`,
    #  cadence de croisière 6 h (séries quotidiennes ou mensuelles).
    #  CE LITTÉRAL NE FAIT PLUS AUTORITÉ : la cadence réelle est une fonction
    #  (`macro_officiel.cadence_min()`, pilotée par VERTEX_MACRO_OFFICIEL_MIN),
    #  résolue à la lecture par `_interval_effectif`. Il ne sert plus que de
    #  repli si le module est indisponible.
    ('MACRO_OFFICIEL_REFRESH', 'Références macro officielles (FRED, BCE, BNS)', 6 * 3600, True),
    ('PREMARKET_BRIEF', 'Brief pré-marché', None, False),
    ('INTRADAY_BRIEF', 'Brief intraday', None, False),
    ('CLOSE_BRIEF', 'Brief de clôture', None, False),
    ('EOD_SNAPSHOT', 'Instantané de fin de journée (track record)', 86400, False),
    #  604800 -> 300. `interval_s` est la cadence de la BOUCLE, pas la
    #  période du roster : le roster est figé pour la semaine ISO, mais
    #  `_weekly_loop` repasse toutes les 5 min pour rafraîchir les chiffres
    #  vivants, et bat à chaque tour. Annoncer 7 jours donnait un seuil de
    #  silence de 14 JOURS : une boucle réellement morte aurait mis deux
    #  semaines à se voir.
    ('WEEKLY_REVIEW', 'Sélection & revue hebdomadaire', 300, True),
    ('SYSTEM_AUDIT', 'Diagnostics système', None, False),
    #  86400 -> None. MESURE SUR LE REGISTRE : `DATA_BACKUP` annonçait une
    #  cadence quotidienne alors qu'AUCUNE horloge ne l'appelle — son unique
    #  émetteur est `_backup_desk` (vertex/app/routes/desk.py:97/109), appelé
    #  depuis le POST de synchronisation du desk, sans boucle ni thread ni
    #  minuteur (balayage AST : c'est le SEUL job implémenté qui déclarait une
    #  cadence sans boucle). Deux faussetés en découlaient : la colonne
    #  « Prochaine (est.) » promettait « dans ~1440 min » — un compte à rebours
    #  que rien ne tient — et, 48 h après un battement (un week-end sans
    #  toucher au desk), l'état passait SILENCIEUX, dont la légende dit « la
    #  boucle est morte ou coincée » : un diagnostic impossible ici, la vraie
    #  cause étant « le desk n'a pas été synchronisé ». `interval_s = None`
    #  rend l'étiquette déjà existante et honnête « sur événement ».
    ('DATA_BACKUP', 'Backup du desk avant la première écriture du jour (rotation 7)', None, True),
    #  86400 -> 6 h. Le battement a rejoint `_edge_loop`, la boucle qui
    #  appelle vraiment `_track.record` et qui dort 6 h. L'écart faisait
    #  attendre 2 jours avant qu'une boucle morte ne se voie.
    ('TRACK_RECORD_UPDATE', 'Mise à jour de la fiabilité mesurée', 6 * 3600, True),
    ('ALERTS_EVALUATION', 'Évaluation serveur des alertes utilisateur', 60, True),
    # Position Intelligence (§39) — cycle de vie analytique des positions.
    ('STARTUP_POSITION_SYNC', 'Détection & réconciliation des positions au démarrage', None, False),
    ('OPEN_POSITION_REFRESH', 'Cotation des positions actions ouvertes', 45, False),
    ('OPEN_OPTION_REFRESH', 'Cotation des positions options ouvertes', 60, False),
    ('MATERIAL_POSITION_RECALCULATION', 'Recalcul après changement matériel', None, False),
    ('THESIS_HEALTH_REVIEW', 'Réévaluation de la santé des thèses', None, False),
    ('EOD_POSITION_SNAPSHOT', 'Instantané de fin de journée des positions', 86400, False),
    ('POSITION_INTEGRITY_AUDIT', 'Audit d’intégrité des positions', None, False),
    # Tracking Engine (§14-18) — suivi analytique hypothétique.
    ('TRACKING_REFRESH', 'Rafraîchissement des suivis actifs', 60, False),
    ('TRACKING_SNAPSHOT', 'Instantané horodaté des suivis', 300, False),
    ('EOD_TRACKING_SNAPSHOT', 'Instantané de fin de journée des suivis', 86400, False),
)

#: Conservé pour les appelants historiques qui itèrent sur trois colonnes.
_CANONICAL = tuple((n, d, i) for n, d, i, _ in _CANONICAL_4)

#: Les jobs qu'aucun code n'exécute aujourd'hui. Servi pour que l'interface
#: puisse dire « non implémenté » au lieu de « jamais exécuté ».
NON_IMPLEMENTES = frozenset(n for n, _, _, ok in _CANONICAL_4 if not ok)

for name, desc, interval, _implemente in _CANONICAL_4:
    _JOBS[name] = {'name': name, 'description': desc, 'interval_s': interval,
                   'implemente': _implemente,
                   'last_run': None, 'last_ok': None, 'last_error': None,
                   'runs': 0, 'last_duration_ms': None,
                   'echecs_consecutifs': 0}


#  ── BORNAGE DE LA DIFFUSION (canal `jobs`) ─────────────────────────────────
#  MESURE (6 sept. 2026, instance de contrôle) : `POSITION_REFRESH` est battu
#  DANS le handler de POST /api/pos-quotes ; le battement était diffusé à TOUS
#  les clients SSE, et le client rejoue ses tâches sur n'importe quel canal —
#  donc reposte /api/pos-quotes. Un seul onglet au repos entretenait la boucle
#  à 0,65 évt/s (un appel toutes les 1,53 s = le debounce du client), soit
#  ~590× la cadence de 15 min que la page déclare elle-même. Conséquence
#  mesurée sur le tampon de rejeu (maxlen 200) : 200/200 événements `jobs`,
#  dont 187 POSITION_REFRESH — plus aucun `market`, `positions`, `alerts` ni
#  `connections` ne survivait, et un client qui se reconnecte rejouait 93 % de
#  bruit en ayant perdu en silence tous les vrais changements d'état.
#
#  On ne supprime PAS le battement (le registre continuerait alors de mentir
#  sur `last_run`/`runs`) : on borne sa DIFFUSION à un événement par job et par
#  `_DIFFUSION_MIN_S`. Un CHANGEMENT d'état (succès -> échec ou l'inverse) passe
#  toujours : ce qui est étouffé n'est qu'une répétition sans information.
#  Ceci ne referme pas la boucle à lui seul — il faut aussi que le battement
#  déclenché par une requête cesse d'être diffusé (desk.py) et que le client
#  cesse de rejouer TOUTES ses tâches pour le canal `jobs` (live-updates.js).
_DIFFUSION_MIN_S = 10.0
_DERNIERE_DIFFUSION: dict[str, tuple[float, bool]] = {}


def beat(name: str, ok: bool = True, error: str | None = None,
         duration_ms: float | None = None, diffuser: bool = True) -> None:
    """Battement émis par une boucle historique après une exécution.

    `diffuser=False` — pour un battement déclenché par la requête d'un client
    (et non par une boucle de fond) : le registre l'enregistre, mais l'annoncer
    à TOUS les clients SSE n'apprend rien à personne et referme la boucle
    mesurée ci-dessus. C'est ce qu'attend l'émetteur de `POSITION_REFRESH`,
    dans le handler de POST /api/pos-quotes (vertex/app/routes/desk.py).
    """
    with _LOCK:
        j = _JOBS.setdefault(name, {'name': name, 'description': '', 'interval_s': None,
                                    'implemente': True,
                                    'last_run': None, 'last_ok': None, 'last_error': None,
                                    'runs': 0, 'last_duration_ms': None,
                                    'echecs_consecutifs': 0})
        j['last_run'] = time.time()
        j['last_ok'] = bool(ok)
        j['last_error'] = (str(error)[:200] if error else None)
        j['runs'] += 1
        #  Lot 7 — le compteur de tempete : des echecs EN SERIE se comptent,
        #  un succes remet a zero. Le registre le porte pour que l'ecran et
        #  un futur circuit breaker lisent le meme chiffre.
        j['echecs_consecutifs'] = 0 if ok else j.get('echecs_consecutifs', 0) + 1
        if duration_ms is not None:
            j['last_duration_ms'] = round(duration_ms)
        #  cf. `_DIFFUSION_MIN_S` : une RÉPÉTITION du même verdict, à moins de
        #  10 s de la précédente, n'apprend rien à personne et remplit le
        #  tampon de rejeu. Un changement de verdict passe toujours.
        precedent = _DERNIERE_DIFFUSION.get(name)
        diffuser = diffuser and not (precedent is not None
                                     and precedent[1] == bool(ok)
                                     and (j['last_run'] - precedent[0]) < _DIFFUSION_MIN_S)
        if diffuser:
            _DERNIERE_DIFFUSION[name] = (j['last_run'], bool(ok))
    #  Diffusion (canal `jobs`) : la page Système suit les battements sans
    #  sonder. Hors verrou, jamais bloquant, jamais une exception ici.
    if diffuser:
        with contextlib.suppress(Exception):
            from vertex.services.live_stream import BROKER as _broker
            _broker.publish('jobs', {'job': name, 'ok': bool(ok)})


def _interval_effectif(nom: str, declare: int | None) -> int | None:
    """Cadence RÉELLEMENT en vigueur dans ce processus, pas le littéral déclaré.

    `MACRO_OFFICIEL_REFRESH` est le SEUL job dont la cadence est une fonction
    (`VERTEX_MACRO_OFFICIEL_MIN`, plancher 15 min) et non une constante.
    MESURE (processus isolé, comparaison sommeil réel / `interval_s` servi) :

    ```text
    env=None → boucle 21600 s | registre 21600 s | seuil SILENCIEUX 43200 s | OK
    env=1440 → boucle 86400 s | registre 21600 s | seuil        43200 s | DÉRIVE
    env=15   → boucle   900 s | registre 21600 s | seuil        43200 s | DÉRIVE
    ```

    Poser la variable documentée (docs/VERTEX_DATA_COVERAGE.md) à 15 min
    laissait donc une boucle MORTE affichée « ACTIF » pendant 12 h au lieu de
    30 min, et `next_run_eta_s` faux dans les deux sens. Même traitement que
    `REFRESH_SEC` plus haut : dériver du propriétaire canonique au lieu de le
    recopier. Import paresseux — aucun cycle au niveau module.
    """
    if nom == 'MACRO_OFFICIEL_REFRESH':
        try:
            from vertex.services.macro_officiel import cadence_min
            return int(cadence_min()) * 60
        except Exception:              # module absent/cassé : le littéral reste
            return declare
    return declare


def jobs() -> list[dict]:
    """Snapshot trié par priorité produit (ordre canonique).

    `etat` distingue trois situations que `last_run: null` confondait toutes :

    - `NON_IMPLEMENTE` — aucun code du dépôt n'émet ce battement. Le job ne peut
      pas tourner ; dire « jamais exécuté » laisserait croire à une panne.
    - `EN_ATTENTE`     — implémenté, mais pas encore passé depuis le démarrage.
    - `ACTIF` / `ERREUR` — il a tourné, et son dernier passage a réussi ou non.
    - `SILENCIEUX` (lot 7) — cadencé, déjà battu avec succès, et MUET depuis
      plus de deux fois sa cadence : la boucle est morte ou coincée. Avant ce
      lot, un job mort restait « ACTIF » pour toujours — un vert de façade sur
      des alertes que personne n'évalue plus. ERREUR prime sur le silence :
      un échec suivi de mutisme reste un échec.
    - `JAMAIS_DEMARRE` — cadencé, implémenté, et JAMAIS battu alors que 2× sa
      cadence s'est écoulée depuis la naissance du processus : la boucle n'a
      pas démarré dans cette configuration (ex. `MARKET_RADAR_REFRESH`, dont le
      thread n'est créé que sous `if IBKR_ENABLED:`) ou est morte avant son
      premier battement. Mesuré : « en attente / 0 » après 16 min d'uptime sur
      un job à 240 s — une attente qui ne finit jamais se lisait comme une
      imminence, et `SILENCIEUX` ne pouvait pas la relever faute de `last_run`.
    """
    now = time.time()
    #  Le verrou ne couvre que la COPIE de l'état : `_interval_effectif` fait un
    #  import paresseux, et importer sous un verrou non réentrant qu'un `beat`
    #  peut vouloir prendre s'appelle un interblocage.
    with _LOCK:
        instantane = [dict(_JOBS[name]) for name, _, _ in _CANONICAL]
    out = []
    for j in instantane:
        j['interval_s'] = _interval_effectif(j['name'], j['interval_s'])
        if j['last_run'] and j['interval_s']:
            j['next_run_eta_s'] = max(0, round(j['last_run'] + j['interval_s'] - now))
        else:
            j['next_run_eta_s'] = None
        j['age_s'] = round(now - j['last_run']) if j['last_run'] else None
        if not j.get('implemente', True):
            j['etat'] = 'NON_IMPLEMENTE'
        elif j['last_run'] is None:
            #  Une attente qui dure plus de 2× la cadence n'est plus une
            #  attente : la boucle n'a pas démarré (configuration) ou est morte
            #  avant son premier battement. Même seuil que SILENCIEUX, donc
            #  aucune constante de plus ; les jobs « sur événement »
            #  (`interval_s is None`) restent EN_ATTENTE — rien ne les cadence.
            j['etat'] = ('JAMAIS_DEMARRE'
                         if (j['interval_s']
                             and (now - _DEMARRAGE) > 2 * j['interval_s'])
                         else 'EN_ATTENTE')
        elif not j['last_ok']:
            j['etat'] = 'ERREUR'
        elif (j['interval_s']
                and (now - j['last_run']) > 2 * j['interval_s']):
            j['etat'] = 'SILENCIEUX'
        else:
            j['etat'] = 'ACTIF'
        out.append(j)
    return out


class _Registry:
    beat = staticmethod(beat)
    jobs = staticmethod(jobs)


registry = _Registry()

__all__ = ['registry', 'jobs', 'beat', 'NON_IMPLEMENTES']
