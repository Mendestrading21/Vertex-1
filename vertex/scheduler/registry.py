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
    ('DATA_BACKUP', 'Backup quotidien du desk (rotation 7)', 86400, True),
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


def beat(name: str, ok: bool = True, error: str | None = None,
         duration_ms: float | None = None) -> None:
    """Battement émis par une boucle historique après une exécution."""
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
    #  Diffusion (canal `jobs`) : la page Système suit les battements sans
    #  sonder. Hors verrou, jamais bloquant, jamais une exception ici.
    with contextlib.suppress(Exception):
        from vertex.services.live_stream import BROKER as _broker
        _broker.publish('jobs', {'job': name, 'ok': bool(ok)})


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
    """
    now = time.time()
    out = []
    with _LOCK:
        for name, _, _ in _CANONICAL:
            j = dict(_JOBS[name])
            if j['last_run'] and j['interval_s']:
                j['next_run_eta_s'] = max(0, round(j['last_run'] + j['interval_s'] - now))
            else:
                j['next_run_eta_s'] = None
            j['age_s'] = round(now - j['last_run']) if j['last_run'] else None
            if not j.get('implemente', True):
                j['etat'] = 'NON_IMPLEMENTE'
            elif j['last_run'] is None:
                j['etat'] = 'EN_ATTENTE'
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
