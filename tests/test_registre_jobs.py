"""Vertex Test 1.0 · #779/G1 — LE REGISTRE DE JOBS NE DÉCLARE PLUS CE QU'IL N'A PAS.

`RELEASE_GATES.md` G1 demande un propriétaire modulaire pour le scheduler. Il en
avait déjà un — `vertex/scheduler/registry.py` — et c'est précisément ce qui
rendait le défaut invisible : la case était cochée.

## Ce que la mesure a trouvé

`tools/mesures/mesurer_registre_jobs.py` énumère à l'AST **tous** les appels
`registry.beat('NOM')` du dépôt. Le registre ne reçoit d'information que par
là : un nom déclaré qu'aucun `beat` ne porte ne peut pas tourner, jamais.

```text
avant : 27 jobs déclarés · 7 émetteurs · 20 jobs sans exécutant
après : 27 jobs déclarés · 9 émetteurs · 18 marqués `implemente: False`
```

## Pourquoi c'était un défaut d'honnêteté, pas de cosmétique

`/api/system/automations` servait les 27 lignes à l'identique, et la page
Système affichait **« jamais exécuté »** pour toutes celles sans `last_run` —
le même mot pour un job en panne et pour un job qui n'existe pas. Le pied de
page allait plus loin et *expliquait* le silence : « dépendent d'intégrations
absentes dans cet environnement ». Ce diagnostic était faux. `NEWS_REFRESH`,
par exemple, tournait toutes les 60 s depuis toujours : sa boucle n'émettait
simplement aucun battement. Deux mensonges de sens opposé sur la même ligne.

C'est la règle 4 de `CLAUDE.md` — donnée absente → aveu honnête, jamais une
valeur inventée — appliquée à un état plutôt qu'à un chiffre.

## Le drapeau est confronté à la mesure DANS LES DEUX SENS

`implemente` serait sans valeur s'il n'était qu'une annotation : il dériverait au
premier ajout. Le test central le compare à ce que l'AST trouve, dans les deux
directions — marquer un job implémenté sans émetteur échoue, et poser un
émetteur sans lever le drapeau échoue aussi.
"""
import importlib
import pathlib
import sys
import time

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures import mesurer_registre_jobs as _mes  # noqa: E402

_reg = importlib.import_module('vertex.scheduler.registry')


@pytest.fixture(scope='module')
def mesure():
    return _mes.mesurer()


def test_le_drapeau_implemente_colle_a_la_mesure_dans_les_deux_sens(mesure):
    """LE CŒUR DU GARDIEN.

    Un job marqué implémenté doit avoir un émetteur ; un job qui a un émetteur
    doit être marqué implémenté. Les deux écarts sont des mensonges — de sens
    opposé, mais servis par la même API."""
    etat_mesure = {l['nom']: l['etat'] for l in mesure['jobs']}
    declare = {nom: bool(ok) for nom, _, _, ok in _reg._CANONICAL_4}

    menteurs_optimistes = sorted(
        n for n, ok in declare.items() if ok and etat_mesure[n] == 'SANS_EMETTEUR')
    assert not menteurs_optimistes, (
        'ces jobs se declarent implementes mais aucun appel beat() ne porte '
        'leur nom : /api/system/automations les affichera « en attente » pour '
        'toujours, ce qui se lit comme une panne — %s' % menteurs_optimistes)

    menteurs_pessimistes = sorted(
        n for n, ok in declare.items() if not ok and etat_mesure[n] == 'ACTIF')
    assert not menteurs_pessimistes, (
        'ces jobs ont un emetteur mais restent marques « non implemente » : '
        'l\'ecran nie un travail qui a bien lieu — %s' % menteurs_pessimistes)


def test_la_mesure_nest_pas_aveugle(mesure):
    """Un détecteur qui ne trouve rien ne prouve rien. Les deux témoins de
    l'outil sont rejoués ici : sans eux, ce fichier vérifierait seulement que
    « rien ne trouve rien »."""
    echecs = _mes._temoins(mesure)
    assert not echecs, 'les temoins de l\'instrument sont muets : %s' % echecs
    assert _mes.TEMOIN_ABSENT not in {l['nom'] for l in mesure['jobs']}, (
        'le temoin negatif a ete declare au registre : il ne temoigne plus')
    assert mesure['actifs'] >= 9, (
        'seulement %d jobs actifs : des emetteurs ont disparu du depot'
        % mesure['actifs'])


def test_les_deux_emetteurs_poses_battent_reellement():
    """`NEWS_REFRESH` et `POSITION_REFRESH` ont été câblés dans ce lot. Vérifier
    la seule présence de la chaîne dans la source serait creux : c'est
    l'effet sur le registre qui compte."""
    src_terminal = RACINE.joinpath('terminal.py').read_text(encoding='utf-8')
    assert "_sched.beat('NEWS_REFRESH'" in src_terminal, (
        'la boucle de nouvelles n\'emet plus de battement : NEWS_REFRESH '
        'redevient invisible alors qu\'elle tourne toutes les 60 s')
    src_desk = RACINE.joinpath('vertex/app/routes/desk.py').read_text(encoding='utf-8')
    assert "_sched.beat('POSITION_REFRESH'" in src_desk, (
        '/api/pos-quotes n\'emet plus de battement : POSITION_REFRESH '
        'redevient invisible')

    #  L'EFFET, pas la chaine : on bat, et on regarde ce que sert `jobs()`.
    _reg.beat('NEWS_REFRESH', ok=True)
    ligne = next(j for j in _reg.jobs() if j['name'] == 'NEWS_REFRESH')
    assert ligne['etat'] == 'ACTIF' and ligne['last_run'], (
        'un battement ne fait plus passer le job a ACTIF : %s' % ligne)


def test_letat_distingue_les_trois_situations():
    """`last_run: null` confondait « non implémenté », « en attente » et
    « en panne ». Trois causes, trois conduites à tenir."""
    lignes = {j['name']: j for j in _reg.jobs()}
    #  Non implémenté : le registre le sait AVANT tout battement.
    assert lignes['THESIS_HEALTH_REVIEW']['etat'] == 'NON_IMPLEMENTE'
    #  En panne : un battement en échec ne doit pas se lire « OK ».
    _reg.beat('CATALYST_REFRESH', ok=False, error='reseau')
    assert next(j for j in _reg.jobs()
                if j['name'] == 'CATALYST_REFRESH')['etat'] == 'ERREUR'
    _reg.beat('CATALYST_REFRESH', ok=True)


def test_lecran_ne_dit_plus_jamais_execute_ni_ne_l_explique_a_tort():
    """La sortie compte autant que le registre : c'est elle que l'utilisateur
    lit. L'ancien pied de page *expliquait* le silence par des « intégrations
    absentes » — une affirmation invérifiable sur 20 lignes dont la plupart
    n'avaient aucun exécutant."""
    src = RACINE.joinpath('vertex/ui/pages/system_page.py').read_text(encoding='utf-8')
    assert 'jamais exécuté' not in src, (
        'la page Systeme accuse de nouveau un job de n\'avoir jamais tourne '
        'alors qu\'il n\'a peut-etre aucun executant')
    assert 'dépendent d\'intégrations absentes' not in src, (
        'le pied de page rediagnostique le silence des jobs : cette phrase '
        'etait fausse pour 18 des 27 lignes')
    assert 'NON_IMPLEMENTE:' in src and 'non implémenté' in src, (
        'l\'ecran ne distingue plus « non implemente » des autres etats')


def test_la_colonne_prochaine_ne_promet_rien_a_un_job_sans_executant():
    """TROUVÉ À LA CAPTURE, PAS À L'API.

    Le statut corrigé, la ligne continuait d'annoncer **« sur événement »** dans
    la colonne « Prochaine (est.) » pour sept jobs sans exécutant. C'est une
    promesse : aucun événement ne déclenchera jamais un job que rien n'exécute.
    La même invention que le statut, une colonne plus loin — invisible depuis
    `/api/system/automations`, qui sert un JSON sans cette colonne."""
    src = RACINE.joinpath('vertex/ui/pages/system_page.py').read_text(encoding='utf-8')
    assert "j.etat==='NON_IMPLEMENTE'?'—':" in src, (
        'la colonne « Prochaine » ne court-circuite plus les jobs sans '
        'executant : elle leur promet de nouveau un declenchement')


def test_le_bilan_du_scheduler_ne_compte_plus_les_jobs_sans_executant():
    """Deuxième récidive, dans le panneau Démarrage : « 27 jobs enregistrés »
    présenté comme un état de santé READY. Le total flattait en comptant 18
    lignes qu'aucun code n'exécute."""
    from vertex.services import connections as _cx
    src = pathlib.Path(_cx.__file__).read_text(encoding='utf-8')
    #  ON VISE LA CHAINE SERVIE, pas le mot : « jobs enregistrés » vivait aussi
    #  dans un commentaire deux lignes plus haut — le chercher tel quel faisait
    #  echouer le test sur une prose sans effet.
    assert "%d jobs enregistrés" not in src, (
        'le bilan du scheduler recompte tous les jobs declares, executables ou '
        'non : le total redevient flatteur')
    assert 'jobs exécutables' in src and 'déclarés sans exécutant' in src, (
        'le bilan ne distingue plus executable et declare')

    instantane = _cx.snapshot({}, ibkr_enabled=False, demo_mode=True)
    ligne = next(c for c in instantane['connections'] if c['name'] == 'Scheduler')
    #  9 -> 10 : `FUNDAMENTALS_REFRESH` est DÉCLARÉ. La boucle des
    #  fondamentaux tournait déjà — elle empruntait le battement de
    #  `TRACK_RECORD_UPDATE`, le job d'une autre boucle. Le total des
    #  10 -> 12 : `OPTIONS_BOARD_REFRESH` (board d'options, 120 s) et
    #  `MARKET_RADAR_REFRESH` (scanners du marché entier + fil courtier,
    #  240 s), qui tournaient sans aucune ligne. Le total des
    #  exécutables monte parce qu'une capacité réelle cesse d'être invisible,
    #  pas parce qu'on a ajouté une ligne décorative : « 18 déclarés sans
    #  exécutant » ne bouge pas, et `test_le_drapeau_implemente_suit_la_mesure`
    #  refuserait le drapeau sans émetteur.
    assert '13 jobs exécutables' in ligne['detail'], (
        'le detail servi ne reflete pas la mesure : %s' % ligne['detail'])
    assert '18 déclarés sans exécutant' in ligne['detail'], (
        'les jobs sans executant ne sont plus nommes : %s' % ligne['detail'])


def test_les_intervalles_annonces_ne_sont_pas_inventes():
    """Deux cadences déclarées ne correspondaient à aucune boucle réelle.

    `NEWS_REFRESH` annonçait 900 s pour une boucle à 60 s, et `POSITION_REFRESH`
    annonçait 45 s pour une route **à la demande**. `next_run_eta_s` en dérive :
    l'écran affichait « prochaine dans ~15 min » pour un job qui repasse dans la
    minute, et un compte à rebours pour un job qui ne repasse que si on le
    demande."""
    par_nom = {n: i for n, _, i, _ in _reg._CANONICAL_4}
    assert par_nom['NEWS_REFRESH'] == 60, (
        'la cadence de NEWS_REFRESH ne suit plus la boucle ; verifier '
        '`_live.wait_force(\'news\', N)` dans terminal.py')
    src = RACINE.joinpath('terminal.py').read_text(encoding='utf-8')
    assert "_live.wait_force('news', 60)" in src, (
        'la boucle de nouvelles a change de cadence : mettre a jour '
        'NEWS_REFRESH dans le registre, sinon l\'ETA servi est faux')
    assert par_nom['POSITION_REFRESH'] is None, (
        'POSITION_REFRESH annonce de nouveau une cadence : la cotation des '
        'positions est declenchee par /api/pos-quotes, pas par un minuteur')


def test_la_forme_a_trois_colonnes_reste_servie():
    """`_CANONICAL` est lu ailleurs dans le dépôt. Ajouter une quatrième colonne
    ne doit pas casser ces appelants."""
    assert all(len(t) == 3 for t in _reg._CANONICAL)
    #  27 -> 30 : `FUNDAMENTALS_REFRESH`, `OPTIONS_BOARD_REFRESH` et
    #  `MARKET_RADAR_REFRESH` (cf. ci-dessus). Trois boucles cadencées
    #  qui tournaient sans aucune ligne à l'écran, chacune empruntant le
    #  job d'une autre ou n'en ayant aucun. Toutes les boucles de fond
    #  du produit sont désormais déclarées.
    assert len(_reg._CANONICAL) == len(_reg._CANONICAL_4) == 31
    assert _reg.NON_IMPLEMENTES and 'NEWS_REFRESH' not in _reg.NON_IMPLEMENTES


# ── Cadence dynamique : le registre ne recopie plus, il dérive ──────────────

def test_la_cadence_macro_officielle_suit_son_proprietaire(monkeypatch):
    """MESURE (processus isolé, comparaison sommeil réel / `interval_s` servi) :

    ```text
    env=None → boucle 21600 s | registre 21600 s | seuil SILENCIEUX 43200 s | OK
    env=1440 → boucle 86400 s | registre 21600 s | seuil        43200 s | DÉRIVE
    env=15   → boucle   900 s | registre 21600 s | seuil        43200 s | DÉRIVE
    ```

    `MACRO_OFFICIEL_REFRESH` est le seul job dont la cadence est une fonction
    (`VERTEX_MACRO_OFFICIEL_MIN`, plancher 15 min, documentée dans
    docs/VERTEX_DATA_COVERAGE.md). Le registre en recopiait un littéral : poser
    la variable à 15 min laissait une boucle MORTE affichée « ACTIF » pendant
    12 h au lieu de 30 min — un faux vert sur un verdict de santé — et
    l'allonger à 24 h armait SILENCIEUX en permanence sur un job sain.
    """
    from vertex.services import macro_officiel as mo

    monkeypatch.setenv('VERTEX_MACRO_OFFICIEL_MIN', '1440')
    j = {x['name']: x for x in _reg.jobs()}['MACRO_OFFICIEL_REFRESH']
    assert j['interval_s'] == mo.cadence_min() * 60 == 86400, (
        'le registre recopie une cadence figee : le seuil SILENCIEUX (2x) '
        'devient faux des que VERTEX_MACRO_OFFICIEL_MIN est pose')
    monkeypatch.delenv('VERTEX_MACRO_OFFICIEL_MIN')
    j = {x['name']: x for x in _reg.jobs()}['MACRO_OFFICIEL_REFRESH']
    assert j['interval_s'] == 21600, 'le defaut doit rester concordant'


# ── Une attente ne dure pas éternellement ──────────────────────────────────

def _fige(job):
    """Remet un job à l'état « jamais battu » et rend son état restauré après."""
    memoire = dict(_reg._JOBS[job])
    _reg._JOBS[job].update({'last_run': None, 'last_ok': None, 'runs': 0,
                            'last_error': None, 'last_duration_ms': None})
    return memoire


def test_une_attente_qui_ne_finit_jamais_cesse_de_se_dire_en_attente():
    """MESURE (instance sans TWS, deux relevés de /api/system/automations à 15
    puis 16 min d'uptime) : `MARKET_RADAR_REFRESH`, cadence 240 s, affichait
    `etat=EN_ATTENTE runs=0 age_s=None` — plus de 4x sa cadence sans un seul
    battement, parce que son thread n'est créé que sous `if IBKR_ENABLED:`.

    « En attente » veut dire « implémenté, pas encore passé depuis le
    démarrage » : c'est vrai à chaque instant, et pourtant l'écran laisse
    croire à une imminence qui ne viendra jamais. `SILENCIEUX` ne pouvait pas
    prendre le relais — il exige un `last_run`. Une boucle morte au berceau
    était donc indiscernable d'un démarrage récent, sur la carte dont la
    fonction est précisément de dire ce qui tourne.
    """
    job = 'MARKET_RADAR_REFRESH'
    memoire = _fige(job)
    demarrage = _reg._DEMARRAGE
    try:
        interval = {x['name']: x for x in _reg.jobs()}[job]['interval_s']
        assert interval, 'ce banc suppose un job cadencé'
        #  Juste après le démarrage : l'attente est légitime.
        _reg._DEMARRAGE = time.time()
        assert {x['name']: x for x in _reg.jobs()}[job]['etat'] == 'EN_ATTENTE'
        #  Passé 2x la cadence sans le moindre battement, ce n'est plus une
        #  attente : la boucle n'a pas démarré, ou est morte avant son premier
        #  passage. Même seuil que SILENCIEUX.
        _reg._DEMARRAGE = time.time() - (2 * interval + 1)
        etat = {x['name']: x for x in _reg.jobs()}[job]['etat']
        assert etat == 'JAMAIS_DEMARRE', (
            '%s n\'a jamais battu apres %g s (2x sa cadence de %g s) et se dit '
            'encore « %s » : une boucle morte au berceau reste invisible'
            % (job, 2 * interval + 1, interval, etat))
    finally:
        _reg._DEMARRAGE = demarrage
        _reg._JOBS[job].update(memoire)


def test_une_boucle_vivante_qui_attend_son_entree_n_est_pas_dite_morte():
    """RÉGRESSION DU LOT PRÉCÉDENT — un état FAUX à la place d'un silence.

    MESURE (registre en processus isolé, 6 sept. 2026) : quatre boucles réelles
    sont gardées par la disponibilité du scan (`_opt_loop`, `_weekly_loop`,
    `_fund_loop`, `_edge_loop` : `if scan_state.get('rows')…` puis `sleep(8)`
    sans battre). Passé 2× leur cadence depuis la naissance du processus, elles
    étaient servies :

    ```text
    OPTIONS_BOARD_REFRESH  cadence 120 s  uptime   241 s → JAMAIS_DEMARRE
    WEEKLY_REVIEW          cadence 300 s  uptime   601 s → JAMAIS_DEMARRE
    FUNDAMENTALS_REFRESH   cadence   6 h  uptime 43201 s → JAMAIS_DEMARRE
    TRACK_RECORD_UPDATE    cadence   6 h  uptime 43201 s → JAMAIS_DEMARRE
    ```

    L'écran ajoute « boucle non démarrée dans cette configuration ou arrêtée
    avant son premier passage » : c'est faux, elles tournent et attendent leur
    entrée. La fenêtre s'ouvre dès que le premier scan traîne — le chemin
    `abandon_debit` et ses backoffs anti-429 de 6 s suffisent.

    Le signal de vie vient de la boucle, jamais d'une supposition du registre,
    et il PÉRIME : une boucle morte en attendant redevient « jamais démarrée ».
    """
    job = 'OPTIONS_BOARD_REFRESH'
    memoire = _fige(job)
    demarrage = _reg._DEMARRAGE
    _reg._ATTENTES.pop(job, None)
    try:
        interval = {x['name']: x for x in _reg.jobs()}[job]['interval_s']
        _reg._DEMARRAGE = time.time() - (2 * interval + 1)
        #  Sans signal : le diagnostic d'origine tient (boucle vraiment morte).
        assert {x['name']: x for x in _reg.jobs()}[job]['etat'] == 'JAMAIS_DEMARRE'
        #  La boucle dit qu'elle tourne et ce qu'elle attend.
        _reg.attente(job, 'MARKET_DATA_REFRESH')
        ligne = {x['name']: x for x in _reg.jobs()}[job]
        assert ligne['etat'] == 'EN_ATTENTE_ENTREE', (
            'une boucle vivante qui attend le premier scan est declaree « %s » '
            'apres %g s d\'uptime : un diagnostic faux, pire que le silence '
            'qu\'il remplace' % (ligne['etat'], 2 * interval + 1))
        assert ligne['attente_de'] == 'MARKET_DATA_REFRESH', (
            'l\'ecran ne peut pas renvoyer vers la vraie cause : %s' % ligne)
        assert ligne['runs'] == 0 and ligne['last_run'] is None, (
            'attendre a ete compte comme un passage : le registre se met a '
            'mentir dans l\'autre sens')
        #  Le signal périme : plus rien ne l'entretient → la boucle est morte.
        _reg._ATTENTES[job] = (time.time() - _reg._ATTENTE_TTL_S - 1,
                               'MARKET_DATA_REFRESH')
        assert {x['name']: x for x in _reg.jobs()}[job]['etat'] == 'JAMAIS_DEMARRE', (
            'un signal de vie perime tient toujours lieu de vie : une boucle '
            'morte en attendant resterait invisible pour toujours')
    finally:
        _reg._DEMARRAGE = demarrage
        _reg._ATTENTES.pop(job, None)
        _reg._JOBS[job].update(memoire)


def test_les_boucles_gardees_par_le_scan_signalent_TOUTES_leur_attente():
    """Le signal serait du code mort s'il n'était appelé nulle part.

    Dérivé de l'AST de terminal.py, dans les deux sens : toute boucle dont le
    corps est gardé par `scan_state.get('rows')` doit signaler, dans son
    `else`, l'attente du job qu'elle bat dans son `if`. Une cinquième boucle
    gardée ajoutée demain sans signal échouera ici.
    """
    import ast

    src = RACINE.joinpath('terminal.py').read_text(encoding='utf-8')
    arbre = ast.parse(src)

    def _noms(noeuds, fonction):
        out = set()
        for n in noeuds:
            for x in ast.walk(n):
                if (isinstance(x, ast.Call)
                        and isinstance(x.func, ast.Attribute)
                        and x.func.attr == fonction and x.args
                        and isinstance(x.args[0], ast.Constant)
                        and isinstance(x.args[0].value, str)):
                    out.add(x.args[0].value)
        return out

    def _garde_le_scan(test):
        for x in ast.walk(test):
            if (isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                    and x.func.attr == 'get' and isinstance(x.func.value, ast.Name)
                    and x.func.value.id == 'scan_state' and x.args
                    and getattr(x.args[0], 'value', None) == 'rows'):
                return True
        return False

    gardees = {}
    for fn in [n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)]:
        for boucle in [n for n in ast.walk(fn) if isinstance(n, ast.While)]:
            for si in [n for n in boucle.body if isinstance(n, ast.If)]:
                if _garde_le_scan(si.test) and si.orelse:
                    gardees[fn.name] = (_noms(si.body, 'beat'),
                                        _noms(si.orelse, 'attente'))
    assert len(gardees) >= 4, (
        'la mesure ne retrouve plus les boucles gardees par le scan : %s'
        % sorted(gardees))
    for nom, (bat, attend) in sorted(gardees.items()):
        assert bat and bat == attend, (
            '%s bat %s mais signale son attente pour %s : la boucle se taira '
            'pendant qu\'elle attend le premier scan, et le registre la '
            'declarera « jamais demarree » (mesure : des 241 s d\'uptime)'
            % (nom, sorted(bat), sorted(attend)))


def test_le_signal_d_attente_est_joignable_par_le_chemin_des_boucles():
    """`from vertex.scheduler import registry` rend l'OBJET, pas le module.

    Les boucles appellent `_sched.attente(...)` sous `except Exception: pass` :
    une fonction absente de `_Registry` y serait avalée en silence — un
    correctif qui ne corrige rien, invisible à l'exécution."""
    from vertex.scheduler import registry as _sched_comme_les_boucles

    assert hasattr(_sched_comme_les_boucles, 'attente'), (
        'le chemin d\'appel reel des boucles ne porte pas `attente` : le '
        'signal de vie est du code mort, avale par leur except')
    job = 'MARKET_RADAR_REFRESH'
    memoire = _fige(job)
    try:
        _sched_comme_les_boucles.attente(job, 'MARKET_DATA_REFRESH')
        assert _reg._ATTENTES[job][1] == 'MARKET_DATA_REFRESH'
        #  Un battement referme l'attente : elle appartient au passe.
        _sched_comme_les_boucles.beat(job, ok=True)
        assert job not in _reg._ATTENTES
    finally:
        _reg._ATTENTES.pop(job, None)
        _reg._JOBS[job].update(memoire)


def test_un_job_sur_evenement_reste_en_attente_meme_longtemps_apres():
    """Contre-épreuve : `JAMAIS_DEMARRE` accuserait à tort un job qu'aucune
    horloge ne cadence. `POSITION_REFRESH` (interval_s None) est déclenché par
    /api/pos-quotes : ne pas être passé n'y est jamais une anomalie."""
    job = 'POSITION_REFRESH'
    memoire = _fige(job)
    demarrage = _reg._DEMARRAGE
    try:
        _reg._DEMARRAGE = time.time() - 86400 * 30
        assert {x['name']: x for x in _reg.jobs()}[job]['etat'] == 'EN_ATTENTE'
    finally:
        _reg._DEMARRAGE = demarrage
        _reg._JOBS[job].update(memoire)


# ── La diffusion des battements est bornée ──────────────────────────────────

def test_un_battement_repete_ne_sature_pas_le_tampon_de_rejeu():
    """MESURE (instance de contrôle, un seul onglet ouvert au repos, zéro
    action utilisateur) : 23 battements POSITION_REFRESH en 35 s, soit un
    toutes les 1,53 s — le battement est émis DANS le handler de
    POST /api/pos-quotes, diffusé à tous les clients SSE, et le client rejoue
    ses tâches sur n'importe quel canal, donc repostait. Composition du tampon
    de rejeu (maxlen 200) au moment du rejeu : 200/200 événements `jobs`, dont
    187 POSITION_REFRESH — plus aucun `market`, `positions` ni `alerts` ne
    survivait, et un client qui se reconnecte rejouait 93 % de bruit.

    Le battement lui-même reste émis (`runs`/`last_run` continuent de dire la
    vérité) : c'est sa RÉPÉTITION à l'identique qui n'est plus diffusée.
    """
    from vertex.services.live_stream import BROKER

    nom = 'TEST_BATTEMENT_REPETE'
    q = BROKER.subscribe()
    try:
        for _ in range(20):
            _reg.beat(nom, ok=True)
        recus = []
        while True:
            try:
                recus.append(q.get_nowait())
            except Exception:  # noqa: BLE001 — file vide
                break
        assert len(recus) == 1, (
            '20 battements identiques en moins de %g s ont produit %d '
            'evenements : le tampon de rejeu se remplit de repetitions et les '
            'vrais changements d\'etat en sortent'
            % (_reg._DIFFUSION_MIN_S, len(recus)))
        assert _reg._JOBS[nom]['runs'] == 20, (
            'le registre doit continuer de compter TOUS les passages : borner '
            'la diffusion ne doit pas rendre le registre muet')
        #  Un CHANGEMENT de verdict passe toujours : c'est une information.
        _reg.beat(nom, ok=False, error='boom')
        assert q.get(timeout=2)['data'] == {'job': nom, 'ok': False}
        #  Un battement déclenché par la requête d'un client décrit une action
        #  DÉJÀ demandée : il s'enregistre, il ne s'annonce pas.
        _reg.beat(nom, ok=True, diffuser=False)
        assert q.empty(), 'diffuser=False publie quand même'
        assert _reg._JOBS[nom]['runs'] == 22 and _reg._JOBS[nom]['last_ok'] is True
    finally:
        BROKER.unsubscribe(q)
        _reg._JOBS.pop(nom, None)
        _reg._DERNIERE_DIFFUSION.pop(nom, None)
