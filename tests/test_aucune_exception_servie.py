"""AUCUNE EXCEPTION PYTHON NE SORT DANS UNE CHARGE SERVIE.

## Le défaut, mesuré

`/options/AAPL` rendait **HTTP 200** avec :

```json
"error": "IndexError: single positional indexer is out-of-bounds"
```

Un type et un message internes, en anglais, livrés au client. Deux fautes en
une : une divulgation de détail d'implémentation, et un « état » qui ne dit
rien de ce qui manque réellement.

`tests/test_instantane.py` l'avait relevé — « une exception Python brute servie
comme état » — et `ticker_api` portait un commentaire affirmant que l'aveu était
désormais structuré. Il l'était à moitié : la FORME du pack avait été corrigée,
le MESSAGE était resté brut. Trois routes faisaient la même chose :
`ticker_api`, `weekly_api`, `correlations_api`, toutes avec le motif
`except Exception as e` puis `'%s: %s' % (type(e).__name__, e)`.

## Ce que ce banc garde

Le vocabulaire d'erreur du dépôt est fait de **codes stables** —
`options_lab_unavailable`, `empreinte_absente`, `symbole_invalide`. Ce banc
interdit qu'un texte d'exception les remplace, à deux endroits :

1. **dans le code** — aucune source de `vertex/` ne compose une charge servie à
   partir de `type(e).__name__` ou de `str(exc)` sur une exception large ;
2. **dans les octets réellement servis** — les routes concernées sont
   exercées et leur charge est inspectée.

## Ce qu'il n'interdit PAS

`str(exc)` sur une exception **applicative volontaire** reste correct :
`PayloadError` porte des codes stables (`payload_json_objet_requis`,
`symbole_invalide`), qui SONT le message destiné à l'appelant. Trois routes en
usent légitimement et ne sont pas visées — les confondre avec une fuite aurait
supprimé une bonne pratique.
"""
from __future__ import annotations

import ast
import json
import os
import re

import pytest

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Signatures d'exception Python qui n'ont rien à faire dans une charge servie.
_SIGNATURES = (
    'IndexError', 'KeyError', 'TypeError', 'ValueError', 'AttributeError',
    'ZeroDivisionError', 'IndexingError', 'Traceback (most recent call last)',
    'object has no attribute', 'not subscriptable', 'out-of-bounds',
)

#: Routes qui rendaient une exception brute, plus leur voisine restée saine.
#  Élargi : toutes les routes qui répondent 200 en moins de 20 ms, mesurées une
#  par une. Celles qui déclenchent une collecte réseau (yfinance sur un titre
#  neuf) sont volontairement absentes — elles feraient dépendre ce banc d'une
#  sortie HTTPS, et un gardien lent finit désactivé.
_ROUTES = (
    #  Les cinq d'origine : celles qui fuyaient, plus leurs voisines.
    '/options/AAPL',
    '/api/correlations/AAPL',
    '/api/ticker/AAPL',
    '/api/company/AAPL',
    '/healthz',
    #  Élargissement — état, décision, mémoire, marché, anomalies, graphe.
    '/readyz',
    '/api/system-status',
    '/api/data-quality',
    '/api/tracking',
    '/api/decision/AAPL',
    '/api/session/digest',
    '/api/market/summary',
    '/api/anomalies/AAPL',
    '/api/skyler/graph',
    '/api/weekly',
    #  Ajoutées au lot J-routes-api. MESURE du 2026-09-06, avant correctif,
    #  sur `app.test_client()` : la première rendait
    #  `{"error":"simulation impossible: float division by zero"}` et la
    #  seconde `{"error":"simulation impossible: math domain error"}` — deux
    #  messages de la bibliothèque standard servis comme état. Le balayage
    #  statique ne les voyait pas : le texte passait par une f-string, pas par
    #  `str(exc)`. D'où le critère de FLUX ajouté plus bas.
    '/api/options/simulate?sym=AAPL&spot=100&strike=0&dte=30&mid=5&iv=0.3',
    '/api/options/simulate?sym=AAPL&spot=100&strike=100&dte=30&mid=5&iv=99999',
)

#: Sous-ensemble pour le DÉNOMINATEUR. `/api/weekly` en est absent : il rend
#: `{}` tant qu'aucun scan n'a construit la sélection hebdomadaire, et c'est un
#: état légitime — pas une page vide. Exiger d'elle un corps non trivial
#: ferait échouer ce banc sur un démarrage à froid, donc pour une raison qui ne
#: concerne pas les fuites d'exception qu'il garde.
_ROUTES_NON_VIDES = tuple(r for r in _ROUTES if r != '/api/weekly')


@pytest.fixture(scope='module')
def client():
    import terminal
    terminal.app.config['TESTING'] = True
    return terminal.app.test_client()


#: Modules qui COMPOSENT une réponse HTTP. Le balayage statique se limite à
#: eux, et c'est la leçon la plus chère de ce lot : appliqué à tout `vertex/`,
#: il criait sur des champs `erreur` INTERNES dont le contrat est justement de
#: NOMMER LA CAUSE — `test_echeances_doctrine`, `test_fondamentaux_dates` et
#: `test_legacy_basket_risk` l'exigent noir sur blanc (« un profil illisible est
#: nommé et non avalé », « une collecte en échec porte son motif »).
#: Les avoir « corrigés » aurait troqué une fuite contre une perte de
#: diagnostic. Un échec interne doit dire pourquoi ; une charge SERVIE ne doit
#: pas dire avec quelle exception Python. Ce sont deux contrats distincts.
def _sources():
    routes = os.path.join(_RACINE, 'vertex', 'app', 'routes')
    for racine, dirs, noms in os.walk(routes):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for nom in noms:
            if nom.endswith('.py'):
                yield os.path.join(racine, nom)


# ── 1. Anti-vide : le détecteur mord-il ? ───────────────────────────────────

def test_le_detecteur_reconnait_une_charge_fautive():
    """Un banc qui ne trouve rien sur une charge FABRIQUÉE fautive ne prouve
    rien sur les charges réelles."""
    fautif = json.dumps({'sym': 'X', 'error': 'IndexError: single positional '
                                              'indexer is out-of-bounds'})
    trouve = [s for s in _SIGNATURES if s in fautif]
    assert trouve, 'le détecteur ne voit pas une exception servie évidente'

    sain = json.dumps({'sym': 'X', 'error': 'options_pack_unavailable',
                       'note': 'chaîne d’options indisponible pour ce titre'})
    assert [s for s in _SIGNATURES if s in sain] == [], (
        'le détecteur crie sur une charge saine — il serait inutilisable')


# ── 2. Dans le CODE : aucune charge composée depuis une exception large ─────

def test_le_TYPE_de_l_exception_n_entre_pas_dans_un_champ_d_erreur_SERVI():
    """`type(e).__name__` livre le détail interne — mais SEULEMENT s'il finit
    dans une charge.

    Ce banc a d'abord visé toute occurrence dans `vertex/`. Il criait alors sur
    `snapshot.py` et `persist.py`, qui gardent le type pour leurs MÉTRIQUES
    internes : jamais servi, et précieux pour diagnostiquer. Interdire ça aurait
    supprimé une bonne pratique au nom d'une règle trop large — le défaut même
    que ce dépôt reproche aux outils d'analyse.

    Le critère retenu est donc : le type entre-t-il dans la VALEUR d'un champ
    `error` / `erreur` d'un dictionnaire ? C'est là, et là seulement, qu'il
    part vers le client.
    """
    motif = re.compile(
        r"""['"]err(?:or|eur)['"]\s*:\s*[^,}\n]*type\(\s*\w+\s*\)\.__name__"""
        r"""|\[\s*['"]err(?:or|eur)['"]\s*\]\s*=\s*[^\n]*type\(\s*\w+\s*\)\.__name__""")
    fautes = []
    for chemin in sorted(_sources()):
        with open(chemin, encoding='utf-8', errors='ignore') as f:
            for num, ligne in enumerate(f, 1):
                if motif.search(ligne):
                    fautes.append('%s:%d' % (os.path.relpath(chemin, _RACINE), num))
    assert fautes == [], (
        'le type de l’exception entre dans un champ d’erreur servi — employer '
        'un code stable (`options_pack_unavailable`, `empreinte_absente`) : %s'
        % '; '.join(fautes))


def test_le_critere_distingue_bien_le_SERVI_de_l_INTERNE():
    """Contre-épreuve du critère ci-dessus : il doit mordre sur la forme
    fautive et se taire sur la forme interne, sinon il ne discrimine rien."""
    motif = re.compile(
        r"""['"]err(?:or|eur)['"]\s*:\s*[^,}\n]*type\(\s*\w+\s*\)\.__name__"""
        r"""|\[\s*['"]err(?:or|eur)['"]\s*\]\s*=\s*[^\n]*type\(\s*\w+\s*\)\.__name__""")
    fautif = ["out['error'] = f'{type(e).__name__}: {e}'",
              "return jsonify({'error': '%s: %s' % (type(e).__name__, e)})"]
    interne = ["_STATS['last_error'] = type(exc).__name__",
               "e.erreur = ('%s: %s' % (type(exc).__name__, exc))[:200]"]
    for ligne in fautif:
        assert motif.search(ligne), 'critère aveugle sur : %s' % ligne
    for ligne in interne:
        assert not motif.search(ligne), 'critère trop large sur : %s' % ligne


def test_str_d_exception_LARGE_ne_devient_pas_une_charge():
    """`str(exc)` reste licite sur une exception APPLICATIVE (`PayloadError`,
    dont le message EST un code stable). Il ne l'est pas sur `except Exception`,
    où le texte vient de la bibliothèque et non du produit."""
    fautes = []
    for chemin in sorted(_sources()):
        with open(chemin, encoding='utf-8', errors='ignore') as f:
            src = f.read()
        try:
            arbre = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, ast.ExceptHandler) or n.name is None:
                continue
            large = (n.type is None
                     or (isinstance(n.type, ast.Name) and n.type.id == 'Exception'))
            if not large:
                continue
            seg = ast.get_source_segment(src, n) or ''
            motif = r'str\(\s*%s\s*\)' % re.escape(n.name)
            if re.search(motif, seg) and ('jsonify' in seg or "'error'" in seg
                                          or '"error"' in seg):
                fautes.append('%s:%d' % (os.path.relpath(chemin, _RACINE), n.lineno))
    assert fautes == [], (
        'texte d’une exception LARGE servi au client : %s' % '; '.join(fautes))


# ── 2 bis. Le critère de FLUX : où le nom de l'exception ATTERRIT-il ? ──────
#
#  Les deux critères ci-dessus regardent la FORME (`str(e)`, `type(e).__name__`)
#  dans le TEXTE de la clause. Mesuré le 2026-09-06 : trois fuites réelles leur
#  échappaient, toutes dans `vertex/app/routes/redesign.py`, pour deux raisons
#  de forme et non de fond —
#
#    · `return jsonify({'error': f'simulation impossible: {exc}'}), 422`
#      — f-string : pas de `str(exc)`, donc invisible ;
#    · `base['daily_error'] = str(e)[:120]` (idem `editorial_error`), puis
#      `return jsonify(base)` DEUX lignes plus bas, hors de la clause : le
#      segment de la clause ne contient ni `jsonify` ni `'error'`, donc le
#      garde-fou se taisait alors même que le texte partait au client.
#
#  Un gardien qui interdit une ÉCRITURE plutôt qu'un EFFET se contourne sans le
#  vouloir : il suffit de changer de syntaxe. Celui-ci mesure la propriété qui
#  compte — le nom de l'exception rejoint-il la charge servie ? — et il
#  n'interdit pas la bonne pratique inverse, garder le détail pour un usage
#  INTERNE (`_sched.beat(error=…)`, `_IV_NON_RECALCULEE.append({'erreur': …})`).


def _racine_cible(cible):
    """`base['daily_error']` → `base`. None si la cible n'a pas de racine nommée."""
    while isinstance(cible, (ast.Subscript, ast.Attribute)):
        cible = cible.value
    return cible.id if isinstance(cible, ast.Name) else None


def _noms_servis(fn):
    """Les variables passées telles quelles à `jsonify(...)` dans cette fonction."""
    noms = set()
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == 'jsonify'):
            noms |= {a.id for a in n.args if isinstance(a, ast.Name)}
    return noms


def _emploie(noeud, nom):
    return any(isinstance(x, ast.Name) and x.id == nom for x in ast.walk(noeud))


def fuites_de_flux(src):
    """Positions où le nom d'une exception LARGE atteint une charge servie."""
    fautes = set()
    for fn in ast.walk(ast.parse(src)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        servis = _noms_servis(fn)
        for h in ast.walk(fn):
            if not isinstance(h, ast.ExceptHandler) or h.name is None:
                continue
            large = (h.type is None
                     or (isinstance(h.type, ast.Name) and h.type.id == 'Exception'))
            if not large:
                continue
            for st in ast.walk(h):
                #  a) le nom part dans un `return` (jsonify direct ou dict) ;
                if isinstance(st, ast.Return) and _emploie(st, h.name):
                    fautes.add((st.lineno, 'return'))
                #  b) le nom entre dans un appel à `jsonify(...)` ;
                elif (isinstance(st, ast.Call) and isinstance(st.func, ast.Name)
                        and st.func.id == 'jsonify' and _emploie(st, h.name)):
                    fautes.add((st.lineno, 'jsonify'))
                #  c) le nom est rangé dans une variable que la fonction sert
                #     ensuite — la fuite différée, la plus discrète des trois.
                elif isinstance(st, ast.Assign) and _emploie(st.value, h.name):
                    if any(_racine_cible(c) in servis for c in st.targets):
                        fautes.add((st.lineno, 'variable servie'))
    return sorted(fautes)


def test_le_nom_de_l_exception_LARGE_n_atteint_pas_une_charge_SERVIE():
    fautes = []
    for chemin in sorted(_sources()):
        with open(chemin, encoding='utf-8', errors='ignore') as f:
            src = f.read()
        try:
            trouvees = fuites_de_flux(src)
        except SyntaxError:
            continue
        rel = os.path.relpath(chemin, _RACINE)
        fautes += ['%s:%d (%s)' % (rel, ligne, voie) for ligne, voie in trouvees]
    assert fautes == [], (
        'le nom d’une exception LARGE rejoint une charge servie — employer un '
        'code stable et une note française, et garder le détail côté serveur : '
        '%s' % '; '.join(fautes))


def test_le_critere_de_FLUX_mord_sur_les_trois_fuites_MESUREES():
    """Anti-vide : les trois formes réellement trouvées le 2026-09-06 doivent
    être détectées, sinon ce banc ne prouve rien de ce qu'il prétend garder."""
    for source in (
        # f-string dans un return — /api/options/simulate
        "def r():\n"
        "    try:\n        x = 1\n"
        "    except Exception as exc:\n"
        "        return jsonify({'error': f'simulation impossible: {exc}'}), 422\n",
        # variable servie plus loin — /api/briefing/editorial
        "def r():\n"
        "    base = {}\n    try:\n        x = 1\n"
        "    except Exception as e:\n        base['daily_error'] = str(e)[:120]\n"
        "    return jsonify(base)\n",
        # concaténation via %, forme historique
        "def r():\n"
        "    try:\n        x = 1\n"
        "    except Exception as e:\n"
        "        return jsonify({'erreur': '%s: %s' % (type(e).__name__, e)})\n",
    ):
        assert fuites_de_flux(source), 'critère aveugle sur :\n%s' % source


def test_le_critere_de_FLUX_laisse_vivre_le_diagnostic_INTERNE():
    """Contre-épreuve : garder le détail d'une exception pour un usage interne
    est une BONNE pratique, et le dépôt en use à deux endroits mesurés
    (`desk.py` → battement du scheduler, `options_intel_api.py` → compteur d'IV
    non recalculée). Un gardien qui les condamnerait ferait perdre du
    diagnostic pour rien."""
    for source in (
        "def r():\n"
        "    try:\n        x = 1\n"
        "    except Exception as e:\n"
        "        _sched.beat('DATA_BACKUP', ok=False,\n"
        "                    error='%s: %s' % (type(e).__name__, e))\n",
        "def r():\n"
        "    try:\n        x = 1\n"
        "    except Exception as _e:\n"
        "        _IV_NON_RECALCULEE.append({'erreur': str(_e)[:120]})\n",
        #  Une variable NON servie garde le droit de porter le détail.
        "def r():\n"
        "    journal = {}\n    try:\n        x = 1\n"
        "    except Exception as e:\n        journal['erreur'] = str(e)\n"
        "    return jsonify({'ok': False})\n",
    ):
        assert fuites_de_flux(source) == [], 'critère trop large sur :\n%s' % source


# ── 3. Sur les OCTETS SERVIS ────────────────────────────────────────────────

@pytest.mark.parametrize('route', _ROUTES)
def test_la_charge_servie_ne_porte_aucune_signature_d_exception(client, route):
    reponse = client.get(route)
    assert reponse.status_code < 500, '%s : %d' % (route, reponse.status_code)
    corps = reponse.get_data(as_text=True)
    trouvees = sorted({s for s in _SIGNATURES if s in corps})
    assert trouvees == [], (
        '%s sert une signature d’exception %s — extrait : %s'
        % (route, trouvees, corps[:300]))


def test_les_routes_exercees_rendent_bien_quelque_chose(client):
    """Dénominateur : si ces routes rendaient du vide, l'absence de signature
    ci-dessus serait vraie pour rien."""
    for route in _ROUTES_NON_VIDES:
        corps = client.get(route).get_data(as_text=True)
        assert len(corps) > 20, '%s rend %d octets' % (route, len(corps))


# ── 4. Le bon motif reste employé ───────────────────────────────────────────

def test_le_vocabulaire_de_codes_stables_est_bien_VIVANT():
    """Si plus aucune route ne servait de code stable, c'est que la convention
    aurait été abandonnée — et ce banc garderait une règle morte."""
    codes = set()
    for chemin in sorted(_sources()):
        with open(chemin, encoding='utf-8', errors='ignore') as f:
            src = f.read()
        codes |= set(re.findall(r"['\"]error['\"]\s*:\s*'([a-z_]{6,})'", src))
        codes |= set(re.findall(r"['\"]reason['\"]\s*:\s*'([a-z_]{6,})'", src))
    assert len(codes) >= 10, (
        'seulement %d codes d’erreur stables trouvés : la convention semble '
        'abandonnée (%s)' % (len(codes), sorted(codes)))
    for attendu in ('options_pack_unavailable', 'correlations_unavailable',
                    'weekly_rebuild_unavailable'):
        assert attendu in codes, 'code de remplacement absent : %s' % attendu
