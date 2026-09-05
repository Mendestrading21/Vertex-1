"""Vertex Test 1.0 · #779 — PARITÉ DU REGISTRE DE ROUTES (contribution à G1).

`RELEASE_GATES.md` G1 exige que **le registre de routes ait un propriétaire
modulaire, avec parité**. Avant `vertex/app/factory.py`, 22
`app.register_blueprint(...)` étaient dispersés dans `terminal.py` entre les
lignes 147 et 2456 : personne ne pouvait répondre à « quelles routes
l'application sert-elle ? » sans lire 2 300 lignes.

## La collision qui aurait cassé en silence — RÉSOLUE au lot 9

Deux blueprints déclaraient **le même chemin** — `/api/anomalies/<sym>`. Le
dispatch tranchait (analysis_api gagnait), et l'ordre d'enregistrement était
la seule chose qui empêchait un basculement silencieux de handler.

Au lot 9, la règle masquée de `strategy_os_api` a été **retirée** : son seul
consommateur (la page legacy `/strategy-os`) est une redirection 301. Le
propriétaire unique est `analysis_api.api_anomalies`, et un gardien générique
(`test_collisions_routes`) échoue désormais sur TOUTE route à deux
propriétaires — l'ordre d'enregistrement n'est plus une protection, c'est un
détail.

## `create_app()` : le piège du `root_path`

`terminal.py` faisait `Flask(__name__)` depuis la racine du dépôt, donc
`static_folder` valait `<racine>/static` — un dossier qui contient **deux
fichiers réellement servis** (`chart.umd.min.js`, `icon-180.png`).

Écrire `Flask(__name__)` dans `vertex/app/factory.py` ferait dériver `root_path`
vers `vertex/app/`, donc `static_folder` vers un chemin inexistant : les deux
fichiers partiraient en **404 sans la moindre erreur au démarrage**, et le
service worker mettrait ces 404 en cache. D'où le `root_path` explicite, et les
tests ci-dessous qui comparent les chemins **résolus** — pas la façon de les
obtenir.
"""
import pathlib

import pytest

from vertex.app import factory


@pytest.fixture(scope='module')
def application():
    from vertex.runtime import app
    return app


def test_le_dispatch_de_la_route_en_collision_est_inchange(application):
    """LE POINT LE PLUS FRAGILE DE L'EXTRACTION.

    Un test sur le NOMBRE de règles ne l'aurait pas vu : les deux règles
    existent dans les deux cas. Seul le handler effectivement choisi le dit."""
    adaptateur = application.url_map.bind('localhost')
    point, _ = adaptateur.match('/api/anomalies/ACN')
    assert point == 'analysis_api.api_anomalies', (
        '/api/anomalies/<sym> est desormais servi par « %s » : le regroupement '
        'des blueprints a change le gagnant de la collision. Verifier que '
        '`register_blueprints(app)` reste appele AVANT `strategy_os_api`.'
        % point)


def test_la_route_anomalies_a_un_seul_proprietaire(application):
    """Lot 9 : la règle masquée de strategy_os_api est retirée — ce banc
    gardait la coexistence pour figer le vainqueur du dispatch ; il garde
    désormais l'état cible : UN propriétaire, le canonique."""
    points = sorted(r.endpoint for r in application.url_map.iter_rules()
                    if r.rule == '/api/anomalies/<sym>')
    assert points == ['analysis_api.api_anomalies'], (
        'la route anomalies a change de proprietaire(s) : %s' % points)


def test_le_registre_declare_ce_qui_est_reellement_enregistre(application):
    """Une liste déclarative qui diverge du réel est pire qu'aucune liste : elle
    fait croire à un inventaire."""
    declares = {chemin.rsplit('.', 1)[-1] for chemin, _ in factory.BLUEPRINTS}
    servis = set(application.blueprints)
    manquants = sorted(d for d in declares if d not in servis and
                       d.replace('_api', '') not in servis)
    assert not manquants, (
        'ces blueprints sont declares dans le registre mais absents de '
        'l\'application : %s' % manquants)
    #  15 -> 16 : `track_record_api` (aucune injection — ses deux dependances
    #  vivaient deja dans le paquet).
    #  16 -> 17 : `scan_api`, une fois la porte anti-rafale partie avec lui.
    #  17 -> 19 : `correlations_api` (son trio de helpers l'a suivi) et
    #  `weekly_api` (chemin du snapshot + carte des resultats).
    #  19 -> 21 : `descriptions_api` (table FR + cache disque) et `ticker_api`
    #  (les deux dernieres routes LEGACY, avec `options_pack`).
    #  21 -> 22 : `macro_api` (références macro officielles FRED/BCE/BNS,
    #  mission alimentation 2026-09-06), né dans le paquet, sans injection.
    assert len(factory.BLUEPRINTS) == 22, (
        'le registre ne compte plus 22 entrees (%d) : si un blueprint a migre '
        'depuis le monolithe, mettre a jour A_INJECTION en meme temps'
        % len(factory.BLUEPRINTS))


def test_les_blueprints_a_injection_restent_documentes(application):
    """`A_INJECTION` n'est pas décoratif : il dit **pourquoi** sept blueprints
    n'ont pas pu déménager. Une entrée qui disparaît sans que le blueprint bouge
    ferait mentir la doc ; une entrée qui reste alors que le blueprint a migré
    laisserait croire à un couplage résolu."""
    assert set(factory.A_INJECTION) == {
        'desk', 'tv_webhooks', 'strategy_os_api', 'redesign',
        'positions_api', 'decision_api', 'live_state_api'}, (
        'la liste des blueprints a injection a change : verifier qu\'un '
        'couplage a bien ete resolu, et pas seulement efface de la doc')
    for nom, raison in factory.A_INJECTION.items():
        assert raison and len(raison) > 10, (
            '%s ne dit plus POURQUOI il ne peut pas deménager' % nom)


def test_le_monolithe_n_enregistre_plus_les_blueprints_sans_injection():
    """La preuve que le regroupement a RETIRÉ, et pas seulement ajouté.

    Un enregistrement resté en place ferait lever Flask (nom déjà pris) — mais
    surtout, le registre déclaratif cesserait d'être la source unique."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[1].joinpath(
        'terminal.py').read_text(encoding='utf-8')
    for bp in ('_feeds.bp', '_analysis_api.bp', '_command.bp', '_session_api.bp',
               '_options_lab_api.bp', '_options_intel_api.bp', '_tracking_api.bp',
               '_opportunities_api.bp', '_planning_api.bp', '_ai_api.bp',
               '_live_api.bp', '_system.bp', '_live_events.bp', '_content.bp',
               '_company_api.bp'):
        assert ('app.register_blueprint(%s)' % bp) not in src, (
            '`terminal.py` enregistre encore %s directement : le registre '
            'declaratif n\'est plus la source unique' % bp)
    assert '_factory.register_blueprints(app)' in src, (
        'le monolithe n\'appelle plus le registre canonique : les 15 '
        'blueprints ne sont plus servis du tout')


def test_le_registre_n_importe_rien_a_son_propre_import():
    """Un registre qui importerait 15 modules au chargement ferait payer son
    coût à tous les tests, y compris ceux qui ne servent aucune route."""
    import pathlib
    src = pathlib.Path(factory.__file__).read_text(encoding='utf-8')
    tete = src.split('def register_blueprints')[0]
    assert 'from vertex.app.routes' not in tete, (
        'le registre importe des blueprints au chargement du module')
    assert 'import_module' in src, (
        'l\'import differe a disparu : le registre redevient un cout fixe')


def test_la_fabrique_ne_deplace_pas_la_racine_ni_le_dossier_statique(application):
    """LE PIÈGE DE `create_app()`.

    Un test sur « l'application démarre » ne l'aurait pas vu : elle démarre très
    bien avec un `static_folder` qui n'existe pas. Ce sont les deux fichiers
    servis qui le disent."""
    import pathlib as _pl
    racine = _pl.Path(__file__).resolve().parents[1]
    assert _pl.Path(application.root_path) == racine, (
        'root_path a derive vers %s : la fabrique a repris `Flask(__name__)` '
        'au lieu du chemin explicite' % application.root_path)
    assert _pl.Path(application.static_folder) == racine / 'static', (
        'static_folder a derive vers %s' % application.static_folder)
    client = application.test_client()
    for fichier in ('chart.umd.min.js', 'icon-180.png'):
        r = client.get('/static/' + fichier)
        assert r.status_code == 200, (
            '/static/%s repond %d : le dossier statique de la racine n\'est '
            'plus servi (le service worker mettrait cette 404 en cache)'
            % (fichier, r.status_code))


def test_la_fabrique_installe_toute_la_plomberie(application):
    """Chaque morceau déplacé est vérifié par son EFFET, pas par sa présence
    dans le fichier — un `after_request` peut être défini et jamais enregistré."""
    client = application.test_client()
    r = client.get('/healthz')
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert r.headers.get('Permissions-Policy'), 'Permissions-Policy a disparu'

    #  JSON sûr : sans lui, Flask sort `NaN`, que `JSON.parse` REFUSE.
    assert application.json.dumps({'x': float('nan')}) == '{"x": null}', (
        'le fournisseur JSON sur n\'est plus installe : une reponse contenant '
        'NaN rendrait une page blanche cote navigateur')

    #  Session et charge utile.
    assert application.config['MAX_CONTENT_LENGTH'] == 2 * 1024 * 1024
    assert application.config['SESSION_COOKIE_HTTPONLY'] is True
    assert application.config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    assert application.secret_key, 'la cle de session a disparu'

    #  404 : JSON sur /api, page HTML ailleurs.
    assert client.get('/api/route-absente').get_json() == {
        'error': 'not_found', 'path': '/api/route-absente'}
    assert client.get('/page-absente').status_code == 404


def test_l_ordre_d_enregistrement_servi_est_celui_qui_est_declare(application):
    """Le verrou d'abord, puis les 15 sans injection, puis les 6 à injection.

    PREMIÈRE VERSION DE CE TEST : RETIRÉE. Elle affirmait garder la place du
    verrou *à l'intérieur* de `create_app()` — mais `create_app()` n'enregistre
    que lui, donc il est premier où qu'on le mette dans la fonction. La mutation
    correspondante (verrou déplacé en fin de fabrique) **passait**, et elle avait
    raison de passer : le comportement ne change pas. Un test qui ne peut pas
    échouer pour la raison qu'il annonce ment sur ce qu'il protège.

    Ce qui est réellement en jeu, et falsifiable : l'ordre COMPLET tel qu'il est
    servi. Avancer `register_blueprints(app)` dans la fabrique avant le verrou,
    ou perdre le verrou, le casse."""
    noms = list(application.blueprints)
    assert noms[0] == 'auth', (
        'le verrou n\'est plus le premier blueprint : %s' % noms[:3])

    declares = [c.rsplit('.', 1)[-1].replace('_api', '') for c, _ in factory.BLUEPRINTS]
    position = {n: i for i, n in enumerate(noms)}
    for nom in declares:
        candidats = [n for n in noms if n == nom or n.startswith(nom)]
        if not candidats:
            continue
        assert position[candidats[0]] > 0, (
            '%s est enregistre avant le verrou : sa garde ne le couvrirait '
            'plus' % nom)
    for injecte in factory.A_INJECTION:
        court = injecte.replace('_api', '')
        vus = [n for n in noms if n == court or n == injecte]
        if vus:
            assert position[vus[0]] > position[noms[0]], (
                '%s precede le verrou' % injecte)


def test_le_monolithe_ne_construit_plus_l_application():
    """La preuve que l'extraction a RETIRÉ, et pas seulement ajouté."""
    src = pathlib.Path(__file__).resolve().parents[1].joinpath(
        'terminal.py').read_text(encoding='utf-8')
    #  ON VISE L'AFFECTATION, PAS LE NOM. `Flask(__name__)` apparait aussi dans
    #  le commentaire qui EXPLIQUE pourquoi il a disparu — le chercher tel quel
    #  faisait echouer ce test sur un fichier parfaitement correct. Neuvieme
    #  occurrence de ce piege dans la serie, et la premiere que j'ai posee
    #  moi-meme dans le meme fichier que sa cause.
    import re
    assert not re.search(r'^\s*app\s*=\s*Flask\(', src, re.M), (
        '`terminal.py` reconstruit une application Flask : il y a de nouveau '
        'deux fabriques, et la racine y redevient implicite')
    assert '_factory.create_app()' in src, (
        'le monolithe ne passe plus par la fabrique canonique')
    for parti in ('def _security_headers', 'def _err_404', 'def _err_500',
                  'def _gzip_response', 'app.secret_key ='):
        assert parti not in src, (
            '`%s` est revenu dans terminal.py : la plomberie Flask a deux '
            'domiciles, et rien ne dit lequel gagne' % parti)
