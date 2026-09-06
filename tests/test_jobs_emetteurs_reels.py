"""UN JOB DÉCLARÉ IMPLÉMENTÉ DOIT BATTRE EN MODE RÉEL.

## Le défaut mesuré

`vertex/scheduler/registry.py` porte un drapeau `implemente`, et son propre
commentaire dit pourquoi il existe : distinguer « en panne » de « n'existe
pas », parce que l'interface disait « jamais exécuté » pour les deux.
`tools/mesures/mesurer_registre_jobs.py` confronte le drapeau à la réalité en
énumérant à l'AST tous les appels `beat('NOM')` du dépôt.

**Cette mesure ne regarde pas OÙ vit l'appel.** `CATALYST_REFRESH` — « Calendrier
earnings + macro » — avait son unique émetteur à l'intérieur de la branche
`if DEMO_MODE:` de `_cal_loop`. Le drapeau disait « implémenté », la mesure le
confirmait, et pourtant :

    en DÉMO   → le job bat toutes les 3 h, la page Système l'affiche ACTIF
    en RÉEL   → `last_run` reste `None` À JAMAIS, état `EN_ATTENTE`

« EN_ATTENTE » veut dire « implémenté, mais pas encore passé depuis le
démarrage ». La page Système l'affichait donc indéfiniment pour un calendrier
réellement rafraîchi toutes les trois heures, et dont les données étaient
servies. Exactement la confusion que le registre existe pour empêcher —
appliquée cette fois à un job QUI MARCHE.

C'était le seul des dix émetteurs du dépôt dans ce cas. Un seul suffit : la
page Système est l'endroit où l'on va pour savoir si la machine tourne.

## Ce que ce banc garde

Tout job `implemente=True` a au moins un émetteur ATTEIGNABLE HORS
`DEMO_MODE`. Un émetteur supplémentaire sous démo reste licite — la vitrine a
le droit de battre aussi ; ce qui ne l'est pas, c'est qu'il soit le seul.

## Ce qu'il n'exige PAS

Que chaque job ait un émetteur : `implemente=False` décrit honnêtement une
intention non réalisée, et `test_registre_jobs` garde déjà ce sens-là dans les
deux directions.
"""
from __future__ import annotations

import ast
import importlib
import os

import pytest

#  `from vertex.scheduler import registry` rend l'INSTANCE `_Registry`, pas
#  le module : elle n'expose que `beat` et `jobs`. On importe le module,
#  comme `test_registre_jobs`.
_reg = importlib.import_module('vertex.scheduler.registry')

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Dossiers hors périmètre : les bancs eux-mêmes battent pour éprouver le
#: registre, et ne sont pas des exécutants du produit.
_IGNORES = {'__pycache__', '.git', 'node_modules', 'tests', '.venv', 'venv'}


def _fichiers():
    for racine, dirs, noms in os.walk(_RACINE):
        dirs[:] = [d for d in dirs if d not in _IGNORES]
        for nom in sorted(noms):
            if nom.endswith('.py'):
                yield os.path.join(racine, nom)


def _sous_demo(arbre) -> set[int]:
    """Identités des nœuds situés dans la branche VRAIE d'un `if DEMO_MODE`."""
    dedans = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.If) and 'DEMO_MODE' in ast.dump(n.test):
            for b in n.body:
                for x in ast.walk(b):
                    dedans.add(id(x))
    return dedans


def _emetteurs() -> dict[str, dict[str, list]]:
    """{job: {'reel': [(fichier, ligne)…], 'demo': […]}}"""
    out: dict[str, dict[str, list]] = {}
    for chemin in _fichiers():
        try:
            src = open(chemin, encoding='utf-8').read()
            arbre = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError):
            continue
        demo = _sous_demo(arbre)
        for n in ast.walk(arbre):
            if (isinstance(n, ast.Call)
                    and getattr(n.func, 'attr', None) == 'beat'
                    and n.args and isinstance(n.args[0], ast.Constant)
                    and isinstance(n.args[0].value, str)):
                place = 'demo' if id(n) in demo else 'reel'
                rel = os.path.relpath(chemin, _RACINE)
                out.setdefault(n.args[0].value, {'reel': [], 'demo': []})
                out[n.args[0].value][place].append((rel, n.lineno))
    return out


# ── 1. Anti-vide : le détecteur trouve bien des émetteurs ───────────────────

def test_le_detecteur_trouve_des_emetteurs():
    """Un détecteur qui ne voit aucun `beat` déclarerait toute la suite
    conforme en ne mesurant rien."""
    e = _emetteurs()
    assert len(e) >= 8, 'seulement %d jobs émetteurs trouvés : %s' % (len(e), sorted(e))
    total = sum(len(v['reel']) + len(v['demo']) for v in e.values())
    assert total >= 10, '%d appels `beat` trouvés' % total


def test_le_detecteur_distingue_VRAIMENT_demo_et_reel():
    """Contre-épreuve du critère : sur un fragment fabriqué, l'appel sous
    `DEMO_MODE` doit être classé démo et l'autre non. Sans elle, tout pourrait
    être classé « réel » et le banc principal serait vide de sens."""
    arbre = ast.parse(
        'if DEMO_MODE:\n'
        "    _s.beat('SOUS_DEMO')\n"
        "_s.beat('HORS_DEMO')\n")
    demo = _sous_demo(arbre)
    vus = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and getattr(n.func, 'attr', None) == 'beat':
            vus[n.args[0].value] = 'demo' if id(n) in demo else 'reel'
    assert vus == {'SOUS_DEMO': 'demo', 'HORS_DEMO': 'reel'}, vus


# ── 2. Le contrat ───────────────────────────────────────────────────────────

def test_aucun_job_implemente_ne_bat_UNIQUEMENT_en_demo():
    e = _emetteurs()
    fautes = []
    for nom, _desc, _iv, implemente in _reg._CANONICAL_4:
        if not implemente:
            continue
        places = e.get(nom)
        if places and not places['reel'] and places['demo']:
            fautes.append('%s (démo seule : %s)'
                          % (nom, ', '.join('%s:%d' % p for p in places['demo'])))
    assert fautes == [], (
        'ces jobs sont déclarés implémentés mais ne battent QUE sous '
        '`DEMO_MODE` : en mode réel ils restent « EN_ATTENTE » pour toujours, '
        'et la page Système annonce qu\'ils n\'ont jamais démarré alors qu\'ils '
        'tournent — %s' % ' ; '.join(fautes))


def test_le_calendrier_bat_bien_sur_LES_DEUX_chemins():
    """Le cas qui a motivé ce banc, nommé. La branche démo garde son
    battement : ce n'est pas lui le défaut, c'est d'être le seul."""
    places = _emetteurs().get('CATALYST_REFRESH')
    assert places, 'plus aucun émetteur pour CATALYST_REFRESH'
    assert places['reel'], (
        'le chemin RÉEL de `_cal_loop` ne bat plus : la page Système '
        'réafficherait « EN_ATTENTE » sur un calendrier qui se rafraîchit')
    assert places['demo'], (
        'la branche démo a perdu son battement — la vitrine afficherait un job '
        'silencieux alors qu\'elle publie un calendrier synthétique')


# ── 3. La cadence annoncée suit la boucle réelle ────────────────────────────

def test_la_cadence_du_calendrier_suit_la_boucle():
    """Même famille que `test_registre_jobs::test_les_intervalles_annonces_ne_
    sont_pas_inventes`, qui couvrait NEWS_REFRESH et POSITION_REFRESH. Il en
    restait un : 3600 s annoncées pour une boucle à 3 × 3600.

    Conséquence à l'écran, une fois le battement réparé : l'état SILENCIEUX
    tombe dès que 2 × l'intervalle est dépassé — donc à CHAQUE cycle, une
    alarme permanente sur un job sain."""
    par_nom = {n: i for n, _, i, _ in _reg._CANONICAL_4}
    assert par_nom['CATALYST_REFRESH'] == 3 * 3600, (
        'la cadence annoncée (%s s) ne suit plus la boucle du calendrier'
        % par_nom['CATALYST_REFRESH'])
    src = open(os.path.join(_RACINE, 'terminal.py'), encoding='utf-8').read()
    assert 'time.sleep(30 if echec else 3 * 3600)' in src, (
        'la boucle du calendrier a changé de cadence : mettre à jour '
        'CATALYST_REFRESH, sinon l’ETA servi et l’état SILENCIEUX sont faux')
    assert "_live.wait_force('calendar', 3 * 3600)" in src, (
        'la branche démo a changé de cadence : les deux chemins doivent '
        'annoncer la même, sinon l’écran ment dans l’un des deux modes')


def test_un_job_sain_ne_tombe_pas_SILENCIEUX_entre_deux_passages():
    """La propriété que la cadence sert vraiment. Éprouvée sur le registre
    lui-même, pas déduite du code."""
    import time

    nom = 'CATALYST_REFRESH'
    iv = {n: i for n, _, i, _ in _reg._CANONICAL_4}[nom]
    memoire = dict(_reg._JOBS[nom])
    try:
        _reg.beat(nom, ok=True)
        #  Juste avant le passage suivant : le job doit rester ACTIF.
        _reg._JOBS[nom]['last_run'] = time.time() - (iv - 60)
        etat = next(j for j in _reg.jobs() if j['name'] == nom)['etat']
        assert etat == 'ACTIF', (
            'un job qui vient de passer et repasse dans une minute est déjà '
            '« %s » — la cadence annoncée est trop courte' % etat)
        #  Bien au-delà de deux cadences : là, le silence est un vrai signal.
        _reg._JOBS[nom]['last_run'] = time.time() - (2 * iv + 60)
        etat = next(j for j in _reg.jobs() if j['name'] == nom)['etat']
        assert etat == 'SILENCIEUX', (
            'un job muet depuis plus de deux cadences ressort « %s » — la '
            'détection de boucle morte ne fonctionne plus' % etat)
    finally:
        _reg._JOBS[nom].update(memoire)


# ── 4. Preuve fonctionnelle : la boucle bat VRAIMENT ────────────────────────

class _Sortie(BaseException):
    """Sert à quitter une boucle `while True` après un tour complet.

    Elle hérite de `BaseException`, PAS de `Exception` : `_cal_loop` porte un
    `except Exception` englobant, qui l'avalerait et l'enregistrerait comme un
    échec du calendrier. Le banc mesurerait alors sa propre sortie au lieu du
    tour qu'il voulait éprouver — première version, corrigée.
    """


def test_un_tour_du_chemin_REEL_emet_bien_le_battement(monkeypatch):
    """L'AST dit qu'un appel existe ; il ne dit pas qu'il est atteint. Ce banc
    fait tourner `_cal_loop` UN tour sur le chemin réel et lit le registre.

    C'est la différence entre « le code contient un `beat` » et « le job bat » —
    précisément la distinction que le défaut corrigé ici exploitait.
    """
    import terminal

    monkeypatch.setattr(terminal, 'DEMO_MODE', False)
    monkeypatch.setitem(terminal.scan_state, 'rows', [{'symbol': 'AAA'}])
    monkeypatch.setitem(terminal.scan_state, 'detail', {})

    from datetime import datetime, timedelta
    proche = (datetime.now() + timedelta(days=9)).strftime('%Y-%m-%d')

    class _TickerSain:
        def __init__(self, sym):
            self.sym = sym

        @property
        def calendar(self):
            return {'Earnings Date': [proche]}

    monkeypatch.setattr(terminal.yf, 'Ticker', _TickerSain)
    #  `_publish` écrit dans `cal_state` : on le rend au banc suivant.
    memoire_cal = dict(terminal.cal_state)

    dodos = []

    def _dodo(secondes):
        #  La PREMIÈRE pause est celle d'amorçage (90 s, « laisse le scan de
        #  démarrage finir ») : elle précède la boucle. La faire lever ici
        #  sortirait avant tout tour — et le banc conclurait « aucun battement »
        #  sans avoir rien exercé.
        dodos.append(secondes)
        if len(dodos) > 1 and secondes >= 30:
            raise _Sortie
    monkeypatch.setattr(terminal.time, 'sleep', _dodo)

    memoire = dict(_reg._JOBS['CATALYST_REFRESH'])
    _reg._JOBS['CATALYST_REFRESH'].update(
        {'last_run': None, 'last_ok': None, 'last_error': None, 'runs': 0})
    try:
        with pytest.raises(_Sortie):
            terminal._cal_loop()
        j = _reg._JOBS['CATALYST_REFRESH']
        assert j['last_run'] is not None, (
            'un tour complet du chemin réel n’a émis AUCUN battement — la page '
            'Système afficherait « EN_ATTENTE » sur un calendrier qui tourne')
        assert j['last_ok'] is True, (
            'le tour a réussi (aucune exception englobante) mais le battement '
            'annonce un échec : %r' % j['last_error'])
        etat = next(x for x in _reg.jobs()
                    if x['name'] == 'CATALYST_REFRESH')['etat']
        assert etat == 'ACTIF', 'état servi après un tour sain : %s' % etat
    finally:
        _reg._JOBS['CATALYST_REFRESH'].update(memoire)
        terminal.cal_state.clear()
        terminal.cal_state.update(memoire_cal)
    assert dodos[-1] == 3 * 3600, (
        'la boucle ne dort pas la cadence annoncée après un tour sain : %r'
        % dodos[-1])


def test_un_tour_EN_ECHEC_ne_declare_pas_le_job_sain(monkeypatch):
    """Contre-épreuve : un battement émis inconditionnellement à `ok=True`
    serait un vert de façade — le défaut que `_weekly_loop` a déjà corrigé."""
    import terminal

    monkeypatch.setattr(terminal, 'DEMO_MODE', False)

    class _EtatQuiCasse(dict):
        def get(self, cle, defaut=None):
            if cle == 'rows':
                raise RuntimeError('état du scan illisible')
            return super().get(cle, defaut)

    monkeypatch.setattr(terminal, 'scan_state', _EtatQuiCasse())

    dodos = []

    def _dodo(secondes):
        dodos.append(secondes)
        if len(dodos) > 1:            # cf. la pause d'amorçage ci-dessus
            raise _Sortie
    monkeypatch.setattr(terminal.time, 'sleep', _dodo)

    memoire = dict(_reg._JOBS['CATALYST_REFRESH'])
    _reg._JOBS['CATALYST_REFRESH'].update(
        {'last_run': None, 'last_ok': None, 'last_error': None, 'runs': 0})
    try:
        with pytest.raises(_Sortie):
            terminal._cal_loop()
        j = _reg._JOBS['CATALYST_REFRESH']
        assert j['last_ok'] is False, (
            'le tour a échoué et le job se déclare sain — vert de façade')
        assert j['last_error'], 'l’échec est enregistré sans motif'
        etat = next(x for x in _reg.jobs()
                    if x['name'] == 'CATALYST_REFRESH')['etat']
        assert etat == 'ERREUR', 'état servi après un tour en échec : %s' % etat
    finally:
        _reg._JOBS['CATALYST_REFRESH'].update(memoire)


# ── 5. Un battement doit pouvoir dire ERREUR ────────────────────────────────
#
#  `_weekly_loop` porte déjà la leçon, écrite dans son propre commentaire :
#  « Émis inconditionnellement à `ok=True`, il déclarait le job WEEKLY_REVIEW
#  sain alors que la construction venait d'échouer — la page Système affichait
#  donc un vert faux. »
#
#  Trois boucles répétaient exactement ce motif, mesurées à l'AST :
#
#    ALERTS_EVALUATION   battement APRÈS le `except ...: pass` englobant, à
#                        `ok=True` figé. Un cycle entièrement en échec — desk
#                        illisible, JSON malformé — déclarait le job sain. La
#                        page annonçait « Évaluation serveur des alertes
#                        utilisateur : ACTIF » pendant que plus aucune alerte
#                        n'était évaluée. C'est le filet de l'utilisateur.
#
#    TRACK_RECORD_UPDATE même motif, ET dans la MAUVAISE BOUCLE : il était émis
#                        par `_fund_loop`, qui ne touche pas au track record.
#                        `_track.record`, la vraie mise à jour, vivait dans
#                        `_edge_loop` et ne battait rien.
#
#    NEWS_REFRESH        en fin de `try` : jamais atteint en cas d'échec, dont
#                        le motif partait dans un `pass`. Le fil tombait en
#                        SILENCIEUX — « la boucle est morte ou coincée » —
#                        alors qu'elle tournait et échouait toutes les 60 s
#                        pour une raison nommable.
#
#  `MARKET_DATA_REFRESH` faisait déjà les choses correctement : `ok=True` sur
#  le chemin de succès, `ok=False, error=str(e)` dans son `except`. Il sert de
#  témoin négatif — le banc ne doit pas crier sur lui.

#  LA LISTE EST DÉRIVÉE DU REGISTRE, PAS ÉCRITE À LA MAIN. Une liste
#  manuelle se périme en silence : le job suivant serait ajouté sans jamais
#  entrer dans ce banc, et « aucun vert de façade » resterait vrai en ne
#  couvrant plus rien.
#
#  Le critère est la CADENCE. Un job cadencé qui échoue en boucle doit pouvoir
#  le dire : sans cela, il reste au dernier battement réussi, bascule
#  SILENCIEUX — « la boucle est morte ou coincée » — et la vraie raison
#  n'existe nulle part. Les jobs à `interval_s is None` sont déclenchés par un
#  événement ou une requête : leur échec remonte à l'appelant, il n'y a pas de
#  boucle à surveiller. Ils sont donc HORS du critère, et c'est dit ici plutôt
#  que sous-entendu par une absence.
def _jobs_cadences_avec_emetteur() -> list[str]:
    emis = set(_emetteurs())
    return [nom for nom, _d, interval, implemente in _reg._CANONICAL_4
            if implemente and interval is not None and nom in emis]


#: Plancher ANTI-VIDE : ces jobs-là doivent rester couverts. Si la dérivation
#: ci-dessus se mettait à ne rien rendre, le banc paramétré deviendrait vide et
#: passerait — la panne exacte que ce dépôt appelle « un détecteur muet ».
#:
#: `DATA_BACKUP` en est SORTI (6 sept. 2026) parce que sa cadence est passée à
#: `None`, et non parce que son émetteur aurait disparu. MESURE À L'ORIGINE :
#: le registre lui déclarait 86400 s alors qu'aucune horloge ne l'appelle — son
#: seul émetteur est `_backup_desk` (routes/desk.py:97/109), invoqué par le POST
#: de synchronisation du desk. L'écran promettait donc « prochaine dans
#: ~1440 min », et 48 h après un battement il basculait SILENCIEUX (« la boucle
#: est morte ou coincée ») alors qu'il n'y a pas de boucle. Le critère de ce
#: banc étant la CADENCE, un job sur événement n'y a plus sa place — mais sa
#: couverture ne doit pas disparaître pour autant : elle est reprise nommément
#: par `test_le_backup_du_desk_peut_declarer_son_echec` ci-dessous.
_PLANCHER = frozenset({
    'ALERTS_EVALUATION', 'TRACK_RECORD_UPDATE', 'NEWS_REFRESH',
    'CATALYST_REFRESH', 'WEEKLY_REVIEW', 'MARKET_DATA_REFRESH',
    'FUNDAMENTALS_REFRESH', 'OPTIONS_BOARD_REFRESH', 'MARKET_RADAR_REFRESH',
})


def test_la_derivation_couvre_au_moins_les_jobs_connus():
    couverts = set(_jobs_cadences_avec_emetteur())
    manquants = sorted(_PLANCHER - couverts)
    assert not manquants, (
        'ces jobs cadencés ne sont plus couverts par le banc — soit leur '
        'émetteur a disparu, soit leur cadence est passée à None : %s'
        % manquants)


def test_les_jobs_SANS_cadence_sont_bien_ecartes():
    """Contre-épreuve du critère. `POSITION_REFRESH` et `STARTUP_HEALTH_CHECK`
    n'ont pas de cadence : ils sont déclenchés par une requête ou par le
    démarrage. Les inclure exigerait une cérémonie sans objet ; les exclure par
    hasard rendrait le critère creux. Ils sont écartés POUR CETTE RAISON."""
    sans_cadence = {nom for nom, _d, iv, impl in _reg._CANONICAL_4
                    if impl and iv is None}
    assert {'POSITION_REFRESH', 'STARTUP_HEALTH_CHECK'} <= sans_cadence
    assert not (sans_cadence & set(_jobs_cadences_avec_emetteur()))


def _formes_de_battement() -> dict[str, list[dict]]:
    """{job: [{'ok_fige_vrai': bool, 'motif': bool, 'fichier', 'ligne'}…]}"""
    out: dict[str, list[dict]] = {}
    for chemin in _fichiers():
        try:
            arbre = ast.parse(open(chemin, encoding='utf-8').read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(arbre):
            if not (isinstance(n, ast.Call)
                    and getattr(n.func, 'attr', None) == 'beat'
                    and n.args and isinstance(n.args[0], ast.Constant)):
                continue
            mots = {k.arg: k.value for k in n.keywords}
            ok = mots.get('ok')
            #  `ok` absent vaut True par défaut : c'est la même promesse figée.
            fige = ok is None or (isinstance(ok, ast.Constant) and ok.value is True)
            out.setdefault(n.args[0].value, []).append(
                {'ok_fige_vrai': fige, 'motif': 'error' in mots,
                 'fichier': os.path.relpath(chemin, _RACINE), 'ligne': n.lineno})
    return out


def test_le_detecteur_de_forme_distingue_les_trois_ecritures():
    """Contre-épreuve du critère, sur des fragments dont on connaît la
    réponse. Sans elle, « aucun vert de façade » pourrait signifier « je ne
    sais pas reconnaître un `ok=True` »."""
    cas = ast.parse(
        "_s.beat('A', ok=True)\n"
        "_s.beat('B')\n"
        "_s.beat('C', ok=(e is None), error=e)\n")
    vus = {}
    for n in ast.walk(cas):
        if isinstance(n, ast.Call) and getattr(n.func, 'attr', None) == 'beat':
            mots = {k.arg: k.value for k in n.keywords}
            ok = mots.get('ok')
            vus[n.args[0].value] = (
                ok is None or (isinstance(ok, ast.Constant) and ok.value is True),
                'error' in mots)
    assert vus == {'A': (True, False), 'B': (True, False), 'C': (False, True)}, vus


@pytest.mark.parametrize('job', _jobs_cadences_avec_emetteur())
def test_chaque_boucle_peut_declarer_son_echec(job):
    """Au moins un émetteur du job transmet un `ok` CALCULÉ et son motif.
    Un émetteur supplémentaire figé à `ok=True` reste licite — la branche
    démo du calendrier en est une, et son cycle synthétique ne peut pas
    échouer ; ce qui ne l'est pas, c'est qu'aucun émetteur ne puisse dire non.
    """
    formes = _formes_de_battement().get(job)
    assert formes, 'aucun émetteur pour %s' % job
    honnetes = [f for f in formes if not f['ok_fige_vrai'] and f['motif']]
    assert honnetes, (
        '%s ne peut JAMAIS se déclarer en échec : %d émetteur(s), tous figés à '
        '`ok=True` sans motif (%s). Un cycle en échec laisserait la page '
        'Système annoncer un job sain — le « vert faux » que `_weekly_loop` '
        'nomme dans son propre commentaire.'
        % (job, len(formes),
           ', '.join('%s:%d' % (f['fichier'], f['ligne']) for f in formes)))


def test_le_backup_du_desk_peut_declarer_son_echec():
    """`DATA_BACKUP` est sorti du banc paramétré avec sa cadence : on le garde
    couvert nommément, sinon la sortie serait une perte de couverture muette.

    Il reste implémenté (deux émetteurs mesurés dans `routes/desk.py`) et doit
    conserver les DEUX formes : un succès et un échec motivé. Sa cadence, elle,
    vaut désormais `None` — mesuré au registre avant correction, elle valait
    86400 s pour un déclencheur de requête, ce qui produisait « prochaine dans
    ~1440 min » puis SILENCIEUX après 48 h sans synchronisation du desk.
    """
    formes = _formes_de_battement().get('DATA_BACKUP')
    assert formes, 'DATA_BACKUP n’a plus d’émetteur : il n’est plus implémenté'
    honnetes = [f for f in formes if not f['ok_fige_vrai'] and f['motif']]
    assert honnetes, (
        'DATA_BACKUP ne peut plus se déclarer en échec : %s'
        % ', '.join('%s:%d' % (f['fichier'], f['ligne']) for f in formes))
    par_nom = {n: i for n, _d, i, _impl in _reg._CANONICAL_4}
    assert par_nom['DATA_BACKUP'] is None, (
        'DATA_BACKUP annonce de nouveau une cadence : aucune horloge ne '
        'l’appelle, son seul déclencheur est le POST de synchronisation du '
        'desk — une cadence y refabrique un compte à rebours et arme '
        'SILENCIEUX sur une boucle qui n’existe pas')


def test_le_battement_du_track_record_vit_avec_le_travail_qu_il_decrit():
    """Un battement émis par une boucle qui ne fait pas le travail décrit est
    une mesure sans objet : `TRACK_RECORD_UPDATE` était émis par la boucle des
    FONDAMENTAUX, pendant que `_track.record` tournait ailleurs sans rien
    dire."""
    #  PAR AST, pas par sous-chaîne : le commentaire qui explique le
    #  déplacement contient le nom du job dans les DEUX fonctions. Un
    #  `'TRACK_RECORD_UPDATE' not in source` échouait donc sur de la prose
    #  sans effet — la leçon que `test_la_fenetre_de_fraicheur_ne_s_elargit_pas`
    #  a déjà payée une fois.
    src = open(os.path.join(_RACINE, 'terminal.py'), encoding='utf-8').read()
    arbre = ast.parse(src)
    fonctions = {n.name: n for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef)}

    def _bat(fn):
        return {n.args[0].value for n in ast.walk(fonctions[fn])
                if isinstance(n, ast.Call)
                and getattr(n.func, 'attr', None) == 'beat'
                and n.args and isinstance(n.args[0], ast.Constant)}

    def _appelle_track(fn):
        return any(isinstance(n, ast.Call)
                   and getattr(n.func, 'attr', None) == 'record'
                   and getattr(getattr(n.func, 'value', None), 'id', '') == '_track'
                   for n in ast.walk(fonctions[fn]))

    assert _appelle_track('_edge_loop'), (
        '`_track.record` a quitté `_edge_loop` : le battement doit suivre le '
        'travail, pas rester où il était')
    assert 'TRACK_RECORD_UPDATE' in _bat('_edge_loop'), (
        'la boucle qui appelle `_track.record` ne bat plus pour lui')
    assert 'TRACK_RECORD_UPDATE' not in _bat('_fund_loop'), (
        'la boucle des fondamentaux ré-emprunte le job du track record : elle '
        'parlerait de nouveau au nom d’un travail qu’elle ne fait pas')
    assert 'FUNDAMENTALS_REFRESH' in _bat('_fund_loop'), (
        'la boucle des fondamentaux ne déclare plus son propre job : elle '
        'redeviendrait invisible sur la page Système')
