"""
LOT 361 — Ce que le SERVICE WORKER met réellement en cache, et le contrat
que la règle critique n°3 sous-entend sans le dire.

La règle écrite dit : « tout changement de shell visible utilisateur → bump
`td-shell-vN` ». Or le service worker (`vertex/app/routes/system.py`) met en
cache **tout `/static`** — CSS, JS, polices, images — en plus des navigations,
et `activate` supprime tous les caches dont la clé diffère de `CACHE`. Le bump
n'est donc pas « pour que l'utilisateur voie la nouvelle interface » (le
service worker est *network-first* : en ligne, le frais gagne toujours) : c'est
ce qui **purge la copie de repli hors-ligne**.

Mesure de l'historique au lot 361 : **27 commits sur 144** touchant
`vertex/static` n'ont pas bumpé — conformes à la règle écrite, hors du périmètre
réel du cache. Fenêtre d'exposition : visiteur déjà venu, hors-ligne ou réseau
> 4,5 s, servi depuis un cache assemblé à des visites différentes (HTML et CSS
peuvent dater de deux passages distincts).

Ce fichier fige deux choses :
  1. la sémantique du service worker (périmètre du cache, network-first, purge
     à l'activation) — pour qu'un changement de politique soit délibéré ;
  2. le CONTRAT : les assets servis et la version du shell sont enregistrés
     ensemble ci-dessous. Un asset change → il faut bumper `td-shell-vN` puis
     rafraîchir ces deux constantes dans le même commit.
"""
import hashlib
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SW = os.path.join(_ROOT, 'vertex', 'app', 'routes', 'system.py')
_STATIC = os.path.join(_ROOT, 'vertex', 'static')

# ── Contrat enregistré : ces assets vont avec cette version de shell ─────────
_EMPREINTE = '91f0c0a288755d67721fe9b9a1da57d7648650d143490850bd9a1c17af49f665'
_SW_VERSION = 292

_AIDE = (
    "Un fichier servi sous /static a changé.\n"
    "Le service worker met TOUT /static en cache (repli hors-ligne) : sans "
    "bump, un visiteur hors-ligne garde l'ancienne copie.\n"
    "À faire dans le MÊME commit :\n"
    "  1. bumper `const CACHE='td-shell-vN'` dans vertex/app/routes/system.py "
    "(+ les 5 gardiens de version) ;\n"
    "  2. remettre à jour _EMPREINTE et _SW_VERSION dans ce fichier.\n"
    "Empreinte mesurée : %s"
)


def _sw_source():
    return open(_SW, encoding='utf-8').read()


def _version():
    m = re.search(r"const CACHE='td-shell-v(\d+)'", _sw_source())
    assert m, 'version du shell introuvable dans le service worker'
    return int(m.group(1))


def _empreinte():
    r"""Empreinte agrégée, stable, de tous les fichiers servis sous /static.

    CANONIQUE, et c'est le point : l'empreinte doit désigner l'ÉTAT DES SOURCES,
    pas la façon dont la machine les a matérialisées. Deux détails de plateforme
    la faisaient diverger alors qu'aucun asset n'avait bougé —

    - le séparateur de `os.path.relpath` (`\` sous Windows, `/` ailleurs) ;
    - les fins de ligne, `core.autocrlf=true` livrant des assets en CRLF.

    Sans normalisation, le gardien était rouge par construction sur Windows —
    donc la machine où G5 se valide (celle qui a TWS) ne pouvait pas reproduire
    la preuve. Un gardien qu'on ne peut pas exécuter là où l'on décide ne
    garde rien.
    """
    chemins = []
    for racine, _, noms in os.walk(_STATIC):
        chemins.extend(os.path.join(racine, n) for n in noms)
    chemins.sort()
    h = hashlib.sha256()
    for p in chemins:
        h.update(os.path.relpath(p, _ROOT).replace(os.sep, '/').encode())
        with open(p, 'rb') as f:
            brut = f.read().replace(b'\r\n', b'\n')   # CRLF -> LF : canonique
            h.update(hashlib.sha256(brut).digest())
    return h.hexdigest(), len(chemins)


# ── 1. Sémantique du service worker ──────────────────────────────────────────

def test_le_cache_couvre_navigations_static_et_manifeste():
    src = _sw_source()
    assert "url.pathname.startsWith('/static')" in src, \
        'le périmètre du cache a changé — la règle n°3 doit être relue'
    assert "req.mode==='navigate'" in src
    assert "url.pathname==='/manifest.webmanifest'" in src


def test_le_service_worker_est_network_first_avec_repli():
    src = _sw_source()
    # Le frais gagne toujours en ligne ; le cache ne sert qu'en repli.
    assert 'Promise.race([fetch(req)' in src
    assert 'await cache.match(req)' in src


def test_l_activation_purge_toutes_les_autres_versions():
    src = _sw_source()
    assert 'caches.keys()' in src and 'k!==CACHE' in src and 'caches.delete(k)' in src


# ── 2. Le contrat assets ↔ version de shell ──────────────────────────────────

def test_les_assets_servis_correspondent_a_la_version_enregistree():
    empreinte, n = _empreinte()
    assert n >= 40, 'trop peu de fichiers analysés — le gardien tournerait à vide'
    assert empreinte == _EMPREINTE, _AIDE % empreinte


def test_la_version_enregistree_n_est_jamais_en_avance_sur_le_service_worker():
    # Un bump sans changement d'asset est légitime (refonte HTML) : on exige
    # seulement que la version enregistrée ne dépasse pas celle qui est servie.
    assert _SW_VERSION <= _version()
