"""vertex/app/factory.py — REGISTRE DE ROUTES CANONIQUE (#779, gate G1).

`RELEASE_GATES.md` G1 : *« PASS lorsque factory Flask, routes, lifecycle/workers
et scheduler ont un propriétaire modulaire, avec parité et sans double
démarrage. »*

Ce module prend la deuxième de ces quatre responsabilités : **le registre de
routes**. Avant lui, 22 `app.register_blueprint(...)` étaient dispersés dans
`terminal.py` entre les lignes 147 et 2456, mêlés aux définitions de vues et aux
fonctions utilitaires. Personne ne pouvait répondre à « quelles routes
l'application sert-elle ? » sans lire 2 300 lignes.

## Deux familles, et une seule peut déménager

Mesuré, pas supposé :

- **15 blueprints sans injection** — un objet `bp` de module, rien d'autre. Leur
  enregistrement est une donnée, pas du code : il devient la liste déclarative
  `BLUEPRINTS`.
- **7 blueprints à injection** — `make_blueprint(...)` nourri par l'état local du
  monolithe (`scan_state`, `_opt_job`, `_on_tv_signal`…). Ils restent dans
  `terminal.py` **tant que cet état y vit**. Les déplacer ici n'aurait rien
  découplé : le registre importerait alors le monolithe, ce qui inverse la
  dépendance sans la réduire.

`auth` faisait un septième cas à injection, et n'en était pas un : son unique
argument, `VERTEX_CODE`, vient de `vertex/app/config.py` — pas du monolithe. Il
est désormais enregistré par `create_app()`, **en premier**, parce que son
`before_request` doit pouvoir refuser une requête destinée à n'importe quel
blueprint.

## `create_app()` — et le piège qu'il fallait mesurer avant de l'écrire

`create_app()` construit l'application : configuration de session, fournisseur
JSON sûr, mesure de latence, en-têtes de sécurité, pages d'erreur, compression,
puis les blueprints. Aucune de ces responsabilités ne dépend de l'état du
monolithe — c'est ce qui rend le déplacement possible.

**Le piège, mesuré et non supposé.** `terminal.py` faisait `Flask(__name__)`
depuis la racine du dépôt, d'où :

```text
root_path     = <racine du dépôt>
static_folder = <racine>/static      ← contient 2 fichiers RÉELLEMENT SERVIS
                                       (chart.umd.min.js, icon-180.png)
```

Écrire `Flask(__name__)` **ici** ferait dériver `root_path` vers `vertex/app/`,
donc `static_folder` vers un dossier qui n'existe pas : les deux fichiers
seraient servis en 404, **sans erreur au démarrage**, et le service worker en
mettrait la 404 en cache. D'où le `root_path` **explicite**, et un gardien qui
compare les chemins résolus plutôt que la façon de les obtenir.

`import_name` reste `'terminal'` : Flask s'en sert pour `app.name` (et le
logger). Le monolithe le produisait déjà — `__name__` vaut `'terminal'` à
l'import et `'__main__'` en lancement direct, cas où Flask renvoie de toute
façon le nom du fichier.

## L'ordre d'enregistrement est-il neutre ?

Question qu'il fallait poser avant de regrouper. Flask résout les règles par leur
chemin, pas par leur ordre — sauf si deux blueprints déclarent la **même** règle,
auquel cas le premier gagne. Mesuré : le dépôt compte **4 règles en double**,
dont trois sont deux méthodes HTTP du même blueprint (inoffensives) et une seule
est une vraie collision — `/api/anomalies/<sym>`, entre `analysis_api` et
`strategy_os_api`. **Aucune route déclarée par `terminal.py` n'entre en
collision avec un blueprint**, ce qui rend l'avancement des enregistrements dans
`create_app()` neutre pour le dispatch. Le filet de parité compare l'ensemble
complet des règles, et un test interroge le gagnant de la collision connue.
"""
from __future__ import annotations

import pathlib
from typing import Any, List, Tuple

#: LE REGISTRE DÉCLARATIF. Chaque entrée est `(module, attribut)` : le module est
#: importé à l'enregistrement, jamais au chargement de ce fichier — un registre
#: qui importerait 15 modules à l'import ferait payer son coût même aux tests qui
#: ne servent aucune route.
#:
#: L'ordre reproduit celui qu'avait `terminal.py`, pour que la parité soit
#: comparable ligne à ligne si quelqu'un doute.
BLUEPRINTS: Tuple[Tuple[str, str], ...] = (
    ('vertex.app.routes.scan_api', 'bp'),
    ('vertex.app.routes.correlations_api', 'bp'),
    ('vertex.app.routes.weekly_api', 'bp'),
    ('vertex.app.routes.descriptions_api', 'bp'),
    ('vertex.app.routes.ticker_api', 'bp'),
    ('vertex.app.routes.feeds', 'bp'),
    ('vertex.app.routes.company_api', 'bp'),
    ('vertex.app.routes.analysis_api', 'bp'),
    ('vertex.app.routes.command', 'bp'),
    ('vertex.app.routes.session_api', 'bp'),
    ('vertex.app.routes.options_lab_api', 'bp'),
    ('vertex.app.routes.options_intel_api', 'bp'),
    ('vertex.app.routes.tracking_api', 'bp'),
    ('vertex.app.routes.track_record_api', 'bp'),
    ('vertex.app.routes.opportunities_api', 'bp'),
    ('vertex.app.routes.planning_api', 'bp'),
    ('vertex.app.routes.ai_api', 'bp'),
    ('vertex.app.routes.live_api', 'bp'),
    ('vertex.app.routes.system', 'bp'),
    ('vertex.app.routes.live_events', 'bp'),
    ('vertex.app.routes.content', 'bp'),
    ('vertex.app.routes.macro_api', 'bp'),
)

#: Les blueprints qui restent chez le monolithe, et POURQUOI. Cette liste n'est
#: pas décorative : `tests/test_factory_parity.py` vérifie qu'elle
#: correspond à ce que `terminal.py` enregistre encore. Une entrée qui disparaît
#: sans que le blueprint bouge ferait mentir la doc ; une entrée qui reste alors
#: que le blueprint a migré laisserait croire à un couplage résolu.
A_INJECTION = {
    'desk': 'job options `_opt_job` et drapeau IBKR, tous deux locaux au monolithe',
    'tv_webhooks': 'callback `_on_tv_signal` défini dans le monolithe',
    'strategy_os_api': '`scan_state` passé en argument à la fabrique',
    'redesign': '`scan_state` passé en argument à la fabrique',
    'positions_api': 'accès à l\'inventaire de positions tenu par le monolithe',
    'decision_api': '`scan_state` plus le mode démonstration résolu au démarrage',
    'live_state_api': 'instantané IBKR (worker `ib_async` du monolithe) et le '
                      'dictionnaire d\'alertes que la boucle mute en place',
}


def register_blueprints(app: Any) -> List[str]:
    """Enregistre les blueprints sans injection. Rend les noms enregistrés.

    Le retour n'est pas cosmétique : il permet à l'appelant — et au test de
    parité — de constater *ce qui a réellement été branché*, plutôt que de
    supposer que la liste et la réalité coïncident."""
    from importlib import import_module

    enregistres: List[str] = []
    for chemin, attribut in BLUEPRINTS:
        module = import_module(chemin)
        bp = getattr(module, attribut)
        app.register_blueprint(bp)
        enregistres.append(bp.name)
    return enregistres


#: Racine du dépôt — le dossier qui contient `terminal.py`, `static/` et
#: `templates/`. Calculée depuis CE fichier (`vertex/app/factory.py`), donc
#: stable quel que soit le répertoire courant du processus.
RACINE = pathlib.Path(__file__).resolve().parents[2]


def create_app(*, root_path: str | None = None) -> Any:
    """Construit l'application Vertex. **Analyse seule, aucun ordre possible.**

    `root_path` est explicite et non déduit de `__name__` : voir l'en-tête du
    module — le déduire ici ferait pointer `static_folder` vers un dossier
    inexistant et rendrait deux fichiers réellement servis introuvables, sans la
    moindre erreur au démarrage."""
    import math
    import os
    import time
    from datetime import timedelta

    from flask import Flask, g, jsonify, redirect, request
    from flask.json.provider import DefaultJSONProvider

    from vertex.app.config import SECRET_KEY, VERTEX_CODE
    from vertex.app.routes import auth as _auth
    from vertex.app import origine as _origine
    from vertex.services import request_metrics as _request_metrics

    app = Flask('terminal', root_path=str(root_path or RACINE))

    # ── Session et charge utile ──────────────────────────────────────────────
    app.secret_key = SECRET_KEY
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        # cookie jamais envoyé en clair quand l'app est servie en HTTPS
        SESSION_COOKIE_SECURE=bool(os.environ.get('RENDER')
                                   or os.environ.get('VERTEX_HTTPS')))
    #  2 Mo — la synchro du desk est un petit blob JSON.
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

    # ── JSON SÛR : NaN/Infinity → null ───────────────────────────────────────
    #  Sans lui, Flask sort littéralement `NaN`, toléré par Python mais REFUSÉ
    #  par `JSON.parse` des navigateurs → page blanche. Le cas arrive avec
    #  l'univers XXL : un titre récent n'a pas assez d'historique pour ma200.
    def _sans_nan(o):
        if isinstance(o, float):
            return None if (math.isnan(o) or math.isinf(o)) else o
        if isinstance(o, dict):
            return {k: _sans_nan(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_sans_nan(v) for v in o]
        return o

    class _FournisseurJSONSur(DefaultJSONProvider):
        def dumps(self, obj, **kw):
            return super().dumps(_sans_nan(obj), **kw)

    app.json = _FournisseurJSONSur(app)

    # ── Mesure de latence des API ────────────────────────────────────────────
    @app.before_request
    def _latence_debut():
        if request.path.startswith('/api/'):
            g._vertex_request_started = time.perf_counter()

    @app.after_request
    def _latence_fin(resp):
        debut = getattr(g, '_vertex_request_started', None)
        if debut is not None:
            _request_metrics.record(
                request.endpoint, resp.status_code,
                (time.perf_counter() - debut) * 1000)
        return resp

    # ── Écritures : même origine seulement ───────────────────────────────────
    #  Démontré le 25 août 2026 sur le vrai produit : un POST `text/plain`
    #  portant `Origin: https://site-malveillant.example` était accepté (200) et
    #  écrivait dans `/api/desk`. Quatorze routes POST existent ; aucune ne
    #  vérifiait l'origine.
    #
    #  Posé ICI, avant les blueprints : une protection d'écriture qui n'en
    #  couvrirait que certaines ne protège rien — c'est celle qu'on oublie qui
    #  sert de porte.
    @app.before_request
    def _refuser_ecriture_etrangere():
        if _origine.origine_etrangere(methode=request.method,
                                      origine=request.headers.get('Origin', ''),
                                      hote_servi=request.host):
            #  403 et non 404 : l'utilisateur légitime qui tomberait dessus doit
            #  comprendre ce qui se passe, et le journal doit pouvoir le compter.
            return jsonify({
                'ok': False,
                'err': 'ecriture refusee : origine differente de celle servie',
                'origine': request.headers.get('Origin', '')[:120],
            }), 403
        return None

    # ── Verrou d'accès : posé TÔT, avant toute route ─────────────────────────
    #  Son `before_request` doit pouvoir refuser une requête destinée à
    #  n'importe quel blueprint — d'où sa place ici, en premier.
    app.register_blueprint(_auth.make_blueprint(code=VERTEX_CODE))

    # ── En-têtes de sécurité ─────────────────────────────────────────────────
    @app.after_request
    def _entetes_securite(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        #  SAMEORIGIN et non DENY : l'accueil embarque ses propres pages en
        #  iframe (?embed=1) — DENY les bloquait en silence. Le clickjacking
        #  externe reste interdit.
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        resp.headers.setdefault('Permissions-Policy',
                                'camera=(), microphone=(), geolocation=()')
        #  Données personnelles (trades, positions, portefeuille, suivi,
        #  journal) : jamais stockées par un cache intermédiaire ou partagé.
        #  Contrôle 025 de l'audit-150 : seul /api/desk était couvert — les
        #  autres surfaces de patrimoine partaient sans directive.
        _PERSONNEL = ('/api/desk', '/api/positions', '/api/portfolio',
                      '/api/tracking', '/api/journal', '/api/track-record')
        if request.path.startswith(_PERSONNEL):
            resp.headers['Cache-Control'] = 'no-store'
        if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
            resp.headers.setdefault('Strict-Transport-Security',
                                    'max-age=31536000; includeSubDomains')
        return resp

    # ── Pages d'erreur ───────────────────────────────────────────────────────
    @app.errorhandler(404)
    def _err_404(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'not_found', 'path': request.path}), 404
        return (_PAGE_404, 404)

    @app.errorhandler(500)
    def _err_500(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'internal'}), 500
        return redirect('/')

    # ── Compression ──────────────────────────────────────────────────────────
    #  Les types dont la compression change quelque chose. Une image ou une
    #  police sont déjà compressées : les repasser au gzip coûte du temps
    #  processeur pour zéro octet gagné.
    _TYPES_JS = ('text/javascript', 'application/javascript',
                 'application/x-javascript')
    #  Un fichier servi en flux n'est matérialisé que sous cette borne : au-delà
    #  (un média, une archive), on le laisse passer plutôt que de le charger en
    #  mémoire pour rien.
    _PLAFOND_FLUX = 4 * 1024 * 1024
    @app.after_request
    def _gzip_response(resp):
        """Compresse les grosses réponses (`/scan` pèse ~8 Mo → ~10× moins) —
        décisif sur un iPhone en Wi-Fi."""
        try:
            if resp.status_code != 200:
                return resp
            if resp.headers.get('Content-Encoding'):
                #  DEJA compressee par la route. Recompresser produit un
                #  DOUBLE gzip : le client decompresse une fois, obtient des
                #  octets qui commencent encore par 1f 8b, et lit du binaire la
                #  ou il attend du JSON. Le corps est valide a l'octet pres et
                #  pourtant illisible — la pire forme de panne, parce que rien
                #  ne signale d'erreur.
                return resp
            #  LES ACTIFS N'ÉTAIENT PAS COMPRESSÉS — mesuré le 2026-09-06.
            #
            #  Le filtre ne retenait que JSON et HTML, et sortait d'emblée sur
            #  `direct_passthrough`, qui est TOUJOURS vrai pour un fichier servi
            #  par `send_file`. Résultat mesuré sur l'instance : ni
            #  `/asset/css/bundle.css` (155 ko), ni `vx-core.js` (49 ko), ni
            #  `chart-core.js` (57 ko) ne portaient `Content-Encoding`.
            #
            #  Total première partie : 791 ko servis, 265 ko une fois
            #  compressés. **526 ko, les deux tiers, payés à chaque chargement
            #  froid** — sur un téléphone en 4G, c'est la différence entre une
            #  page qui s'ouvre et une page qu'on attend.
            #
            #  Le corps d'un fichier en flux doit être matérialisé avant d'être
            #  compressé ; on ne le fait que sous une borne, pour ne pas charger
            #  en mémoire un gros média.
            ct = (resp.content_type or '').split(';')[0].strip()
            compressible = (ct.startswith('application/json') or ct == 'text/html'
                            or ct == 'text/css' or ct in _TYPES_JS
                            or ct == 'image/svg+xml' or ct == 'text/plain')
            if not compressible:
                return resp
            #  `Vary` VA SUR LES DEUX VARIANTES, pas seulement sur la compressée.
            #  Un cache partagé qui range la réponse EN CLAIR sans `Vary` peut
            #  la resservir à un client qui aurait accepté du gzip — sans
            #  dommage — mais surtout il peut ranger la MÊME entrée pour les
            #  deux, et l'ordre des visiteurs déciderait alors du corps servi.
            #  On l'annonce dès qu'on sait que la ressource se négocie.
            resp.headers['Vary'] = 'Accept-Encoding'
            if 'gzip' not in (request.headers.get('Accept-Encoding') or ''):
                return resp
            if resp.direct_passthrough:
                if (resp.content_length or 0) > _PLAFOND_FLUX:
                    return resp
                resp.direct_passthrough = False
            data = resp.get_data()
            if len(data) < 8192:
                return resp
            import gzip as _gz
            gz = _gz.compress(data, 5)
            if len(gz) >= len(data):
                return resp
            resp.set_data(gz)
            resp.headers['Content-Encoding'] = 'gzip'
            resp.headers['Content-Length'] = str(len(gz))
            resp.headers['Vary'] = 'Accept-Encoding'
            #  L'étiquette d'entité désignait le corps NON compressé. Deux
            #  corps différents sous une même étiquette, c'est un cache qui peut
            #  servir l'un pour l'autre ; nginx règle cela depuis toujours par
            #  un suffixe. On fait pareil.
            #
            #  MAIS LE SUFFIXE SEUL CASSE LA REVALIDATION, et c'est pire que le
            #  défaut qu'il corrige. Mesuré le 2026-09-06 : Flask compare le
            #  `If-None-Match` du client à SON étiquette, non suffixée, AVANT
            #  que cette fonction ne s'exécute. Le client renvoyant
            #  « …-gzip », la comparaison échouait toujours : `vx-core.js`
            #  rendait 200 et 18 ko à CHAQUE revalidation, là où il rendait 304
            #  et zéro octet avant la compression. Un visiteur qui revient y
            #  perdait ce qu'un visiteur neuf y gagnait.
            #
            #  La comparaison est donc refaite ICI, contre l'étiquette
            #  réellement servie. `If-None-Match` peut porter plusieurs valeurs
            #  et le préfixe faible `W/` ; on compare sur la liste nettoyée.
            etag = resp.headers.get('ETag')
            if etag and 'gzip' not in etag:
                etag = (etag[:-1] + '-gzip"') if etag.endswith('"') else (etag + '-gzip')
                resp.headers['ETag'] = etag
            if etag:
                connues = [t.strip().removeprefix('W/')
                           for t in (request.headers.get('If-None-Match') or '').split(',')]
                if etag in connues or '*' in connues:
                    #  304 : ni corps, ni longueur, mais les validateurs et la
                    #  politique de cache restent — sans eux le client
                    #  redemanderait tout au prochain tour.
                    resp.status_code = 304
                    resp.set_data(b'')
                    for entete in ('Content-Length', 'Content-Encoding', 'Content-Type'):
                        resp.headers.pop(entete, None)
        except Exception:
            #  Une compression ratée ne doit jamais coûter la réponse : on rend
            #  le corps tel quel, qui est toujours valide. `return` explicite
            #  plutôt que `pass` — le comportement est le même, mais l'intention
            #  se lit, et le gardien des avaleurs silencieux n'a rien à juger.
            return resp
        return resp

    return app


#: Page 404 autonome — aucune dépendance au shell, pour rester servable même si
#: le rendu de page est en cause.
#:
#: NOTE (#779) : ses couleurs sont l'ancienne identité orange (`#FF7A18`), pas le
#: violet `#9B7BFF` de `CLAUDE.md`. Constat relevé au déplacement, **non
#: corrigé** : repeindre une page au passage d'une extraction mêlerait deux
#: changements dans un même diff.
_PAGE_404 = (
    '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<title>404 · Vertex</title><style>body{background:#0b0e14;color:#eef2f8;'
    'font-family:Inter,system-ui,sans-serif;display:grid;place-items:center;'
    'height:100vh;margin:0}'
    '.c{text-align:center}.n{font-size:64px;font-weight:900;color:#FF7A18}'
    '.t{color:#8794ab;margin:10px 0 22px}'
    'a{color:#FF9A3D;text-decoration:none;font-weight:700;'
    'border:1px solid rgba(255,122,24,.4);padding:10px 20px;border-radius:12px}'
    '</style></head>'
    '<body><div class="c"><div class="n">404</div>'
    '<div class="t">Cette page n\'existe pas (ou plus).</div>'
    '<a href="/">← Retour au Market Overview</a></div></body></html>')


__all__ = ['BLUEPRINTS', 'A_INJECTION', 'RACINE', 'create_app',
           'register_blueprints']
