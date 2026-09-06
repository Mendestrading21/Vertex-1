"""vertex/app/caches.py — CACHES D'EXÉCUTION : UN PROPRIÉTAIRE, UNE POLITIQUE.

`QUALITY_STANDARD.md` §8 : *« Les caches ont un propriétaire et une politique de
fraîcheur. »* Avant ce module, les huit caches d'exécution vivaient au niveau
module de `terminal.py`, sans propriétaire déclaré ni politique écrite : rien
n'empêchait un second écrivain d'apparaître, et rien ne disait au lecteur
combien de temps une valeur restait valable.

Le propriétaire de chacun a été **mesuré** à l'AST (qui écrit dans l'objet),
jamais supposé — c'est la colonne `proprietaire` de `POLITIQUE`.

## Pourquoi ces objets peuvent déménager sans rien changer

Les huit sont **définis une fois et mutés en place** (mesuré : une seule
affectation, aucun `global`). Les importer ici et les relier par leur nom dans
`terminal.py` préserve donc l'**identité** de l'objet : `terminal._live_quotes`
et `caches._live_quotes` désignent le même dictionnaire, et tout écrivain
existant continue d'écrire là où les lecteurs lisent.

## L'invariant qui rend ce partage fragile, et qu'il faut connaître

C'est le même que celui de `scan_state` dans `CLAUDE.md` : **muter en place,
jamais réassigner.** Une réaffectation (`terminal._IDX_IBKR = {...}`) ne
déplace que l'étiquette : le module qui a importé l'objet garde l'ancien, et
les deux vues divergent en silence. `tests/test_pass_terminal.py`
pratique justement un `monkeypatch.setattr` de ce genre — il reste correct
aujourd'hui parce que les fonctions de `terminal.py` résolvent leurs globals à
l'appel, mais il cesserait de l'être le jour où un blueprint lirait le cache
depuis ce module. `tests/test_caches_parity.py` garde l'identité.

## Ce que ce module n'est pas

Ce n'est ni un cache HTTP, ni une couche de persistance : rien ici ne survit au
processus. Les caches disque et l'état utilisateur ont d'autres propriétaires
(`vertex/app/state.py`, `desk_data.json`).
"""

# ── Source de secours STOOQ ────────────────────────────────────────────────
# Yahoo (yfinance) rate-limite les serveurs de datacenter : `yf.download` revient
# vide sur Render. Stooq sert de filet — clôtures quotidiennes, donc une seule
# mise à jour utile par jour ; le TTL de 6 h évite de marteler un endpoint
# gratuit sans rien gagner. Lecture seule.
_STOOQ_CACHE = {'ts': 0.0, 'frames': {}}
_STOOQ_TTL = 6 * 3600

# Santé des sources de données. Un écrivain PAR CLÉ : chaque source déclare son
# propre état, ce qui est la seule forme de multi-écriture acceptable ici.
#
# Valeurs RÉELLEMENT écrites, relevées chez les deux seuls écrivains :
#   'UNKNOWN'       — valeur initiale, aucune tentative depuis le démarrage ;
#   'AVAILABLE'     — la source a servi des données (terminal.py, stooq.py) ;
#   'CACHED'        — servi depuis le cache après échec réseau (stooq.py) ;
#   'NOT_COLLECTED' — pas de tentative sur ce cycle (terminal.py) ;
#   'UNAVAILABLE'   — tentative faite, rien servi (terminal.py, stooq.py).
#
# Le commentaire précédent annonçait « 'UNKNOWN' | 'OK' | 'UNAVAILABLE' ». `OK`
# n'a JAMAIS été écrit par personne : c'était un vocabulaire d'état inventé par
# la documentation, et la page Système avait fini par bâtir sa liste blanche de
# sources saines dessus — cinq sources à `AVAILABLE` étaient donc affichées
# « dégradé » en permanence (constat 4). Le vocabulaire public servi est borné
# par `_PUBLIC_SOURCE_STATES` (vertex/app/routes/analysis_api.py), que Stooq
# complète de `CACHED` ; ce commentaire s'aligne sur les ÉMETTEURS, et
# `tests/test_pannes_sources.py` le vérifie en dérivant la liste du code.
_SOURCE_BUDGET_STATE = {'yfinance': 'UNKNOWN', 'stooq': 'UNKNOWN'}

# ── Instantanés des routes interactives ────────────────────────────────────
# `AUDIT-TOTAL-2026-08-25` P0.1 : une route de page ne lance pas de collecte.
# Mesuré sur `73de92f5` — `/api/ticker/<sym>` montait à 28–48 s sous charge, et
# cinq demandes SIMULTANÉES du même titre faisaient cinq collectes, dont une à
# 136,9 s. Ce magasin sert l'instantané daté et coalesce les reconstructions.
#
# Il vit ICI parce que `test_caches_parity` exige que tout ce que
# `POLITIQUE` déclare soit un objet réel de ce module — un registre qui décrit
# des caches inexistants ne décrit plus rien.
from vertex.app.snapshot import Magasin as _Magasin           # noqa: E402

_TICKER_SNAPSHOTS = _Magasin('ticker')

# ── Corrélations macro ─────────────────────────────────────────────────────
# Trames de référence (SOXX, QQQ, S&P, BTC, or, dollar, taux, VIX) partagées par
# tous les calculs de corrélation d'un même cycle.
_CORR_BENCH = {'ts': 0, 'df': None}

# ── IBKR, LECTURE SEULE ────────────────────────────────────────────────────
# Aucun de ces caches ne peut porter un ordre : ils ne contiennent que des
# instantanés de marché et de portefeuille obtenus en lecture.
_ibkr_cache = {'ts': 0.0, 'data': None}

# Indices en direct via IBKR. `_IDX_IBKR` est indexé par NOM D'AFFICHAGE, qui
# doit rester aligné sur `scan_state['indices']` — c'est ce qui permet l'overlay.
_IDX_IBKR = {}
_IDX_META = {'connected': False, 'ts': 0.0, 'n': 0}

# Cours en direct (flux IBKR permanent). `_live_quotes` est écrit par le
# stockage de ticker, `_live_meta` par le worker : deux objets, deux
# propriétaires, parce qu'ils répondent à deux questions différentes — « quel
# est le prix ? » et « la connexion tient-elle ? ».
_live_quotes = {}
_live_meta = {'connected': False, 'ts': 0.0, 'rt': False, 'n': 0}

#: Chaînes d'options déjà collectées, par symbole — PERSISTÉ sur disque
#: (`optall_cache.json`). Rempli par le chargement au démarrage du monolithe et
#: muté en place par `_opt_loop` (rotation de l'univers) et par
#: `vertex.options.pack.options_pack` (fiche ouverte). Ce partage entre une
#: boucle de fond et une route est exactement ce que ce module existe pour
#: rendre visible : l'objet doit rester LE MÊME des deux côtés.
_OPTALL_CACHE = {}


#  REGISTRE LISIBLE PAR MACHINE — c'est lui qui rend la politique VÉRIFIABLE.
#  Un commentaire se périme sans bruit ; ce dictionnaire est testé.
POLITIQUE = {
    '_STOOQ_CACHE': {
        'proprietaire': '_stooq_download',
        'fraicheur': 'TTL 21600 s (6 h) — données EOD, une maj utile par jour',
        'nature': 'cache',
    },
    '_SOURCE_BUDGET_STATE': {
        'proprietaire': '_download_universe + _stooq_download (un par clé)',
        'fraicheur': 'état courant, sans TTL — remis à jour à chaque tentative',
        'nature': 'sante-source',
    },
    '_CORR_BENCH': {
        'proprietaire': '_corr_benchmarks',
        'fraicheur': 'horodaté par `ts`, invalidé par l\'appelant',
        'nature': 'cache',
    },
    '_ibkr_cache': {
        'proprietaire': '_ibkr_snapshot',
        'fraicheur': 'horodaté par `ts`',
        'nature': 'cache',
    },
    '_IDX_IBKR': {
        'proprietaire': '_indices_loop',
        'fraicheur': 'live, chaque entrée porte son propre `ts`',
        'nature': 'live',
    },
    '_IDX_META': {
        'proprietaire': '_indices_loop',
        'fraicheur': 'live, `ts` global de la boucle',
        'nature': 'live-meta',
    },
    '_live_quotes': {
        'proprietaire': '_store_ticker',
        'fraicheur': 'live, poussé par le flux',
        'nature': 'live',
    },
    '_live_meta': {
        'proprietaire': '_quotes_worker',
        'fraicheur': 'live, `ts` de dernière réception',
        'nature': 'live-meta',
    },
    '_OPTALL_CACHE': {
        'proprietaire': '_opt_loop (rotation) + options_pack (fiche ouverte)',
        'fraicheur': 'TTL 86400 s cote boucle ; la fiche rafraichit a la demande',
        'nature': 'cache-persiste',   # optall_cache.json
    },
    #  Le magasin d'instantanes des routes interactives. Il ne vit pas ICI
    #  (c'est un objet, pas un dict partage avec `terminal.py`), mais sa
    #  politique est declaree ici : QUALITY_STANDARD §8 exige un proprietaire
    #  et une politique, pas un emplacement particulier.
    '_TICKER_SNAPSHOTS': {
        'proprietaire': 'vertex/app/routes/ticker_api.py (unique lecteur/ecrivain)',
        'fraicheur': 'fenetre 60 s alignee sur le ttl client ; au-dela, servi '
                     'RASSIS et reconstruit en fond, une seule fois par cle',
        'nature': 'cache',   # memoire : perdu au redemarrage, reconstruit
    },
}

__all__ = [
    '_STOOQ_CACHE', '_STOOQ_TTL', '_SOURCE_BUDGET_STATE', '_CORR_BENCH',
    '_ibkr_cache', '_IDX_IBKR', '_IDX_META', '_live_quotes', '_live_meta',
    '_OPTALL_CACHE', '_TICKER_SNAPSHOTS',
    'POLITIQUE',
]
