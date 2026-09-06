"""vertex/app/routes/company_api.py — API ENTREPRISE (profil, analystes, noms).

Extrait de `terminal.py` au titre de #779. Ces trois routes y étaient décorées
directement sur `app`, ce qui en faisait la seule surface du produit dont le
propriétaire était le monolithe et non un blueprint.

## Pourquoi ces trois-là en premier

Les dépendances des quatorze routes LEGACY ont été mesurées à l'AST. Celles-ci
sont les seules — avec `/api/track-record` — à ne dépendre de **rien d'autre que
`app`** : pas d'état local, pas de verrou, pas de fonction privée du monolithe.
Elles se déplacent donc **sans injection**, ce qui est la plus petite
convergence prouvable au sens du prompt maître.

`/api/track-record` reste pour l'instant dans `terminal.py` : elle appelle
l'auto-évaluation du moteur, qui relève de la mémoire et de la calibration
(#783). La ranger ici, ou dans `tracking_api` qui gère des suivis
*hypothétiques*, serait un mensonge de nommage.

## Contrat conservé à l'identique

Les trois vues gardent leur corps, leurs messages d'erreur et leur forme de
réponse. L'extraction déplace la propriété, **pas le comportement** — c'est ce
que `tests/test_routes_company_parity.py` garde.

⛔ Lecture seule : aucune de ces routes ne prépare ni ne transmet d'ordre.
"""
from __future__ import annotations

import contextlib
import threading
import time

from flask import Blueprint, jsonify

from vertex.app.config import DEMO_MODE
from vertex.data import company as _company
from vertex.app import snapshot as _instantane
from vertex.data_sources import analyst_deep
from vertex.data_sources import sec_fondamentaux as _sec_f

bp = Blueprint('company_api', __name__)


_COMPANY_EN_COURS: dict[str, float] = {}
_COMPANY_VERROU = threading.Lock()


def _collecter_profil_en_fond(sym):
    """`company.get(allow_fetch=True, brief=True)` dans un thread démon : le
    profil yfinance ET sa traduction (réseau) ne se font jamais dans la requête."""
    now = time.time()
    with _COMPANY_VERROU:
        if now - _COMPANY_EN_COURS.get(sym, 0) < ANALYST_RELANCE_S:
            return False
        _COMPANY_EN_COURS[sym] = now

    def _run():
        try:
            with contextlib.suppress(Exception):
                _company.get(sym, demo=DEMO_MODE, allow_fetch=True, brief=True)
        finally:
            with _COMPANY_VERROU:
                _COMPANY_EN_COURS.pop(sym, None)
    threading.Thread(target=_run, daemon=True, name='profil-' + sym).start()
    return True


@bp.route('/api/company/<sym>')
def api_company(sym):
    """Profil d'entreprise seul (cache hebdomadaire — activité, CEO, segments, pairs).

    Aucun réseau dans la requête : le cache (ou la couche curée) est servi tel
    quel avec `etat` CACHE / PERIME / EN_COURS ; une entrée absente ou périmée
    déclenche la collecte EN FOND (`retry_s`)."""
    sym = sym.upper()
    try:
        present, frais = (False, False)
        with contextlib.suppress(Exception):
            present, frais = _company.fraicheur(sym)
        out = _company.get(sym, demo=DEMO_MODE, allow_fetch=False, brief=False)
        if not isinstance(out, dict):
            out = {'symbol': sym}
        if frais or DEMO_MODE:
            out['etat'] = 'CACHE' if present else 'CURE'
        else:
            _collecter_profil_en_fond(sym)
            out['etat'] = 'PERIME' if present else 'EN_COURS'
            out['stale'] = present
            out['retry_s'] = ANALYST_RETRY_S
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': 'company_unavailable',
                        'note': 'fiche société indisponible — '
                                'source injoignable ou titre inconnu'})


#  Collectes analystes EN COURS (dédoublonnage par symbole) : une fiche ouverte
#  trois fois ne lance qu'une collecte. Entrée oubliée à la fin du thread, ou
#  après ANALYST_RELANCE_S si le thread n'a jamais rendu la main.
_ANALYST_EN_COURS: dict[str, float] = {}
_ANALYST_VERROU = threading.Lock()
ANALYST_RELANCE_S = 120
ANALYST_RETRY_S = 6


def _collecter_analystes_en_fond(sym):
    """Lance `analyst_deep.get(sym)` dans un thread démon. Rend True si une
    collecte a été lancée, False si une collecte est déjà en cours."""
    now = time.time()
    with _ANALYST_VERROU:
        if now - _ANALYST_EN_COURS.get(sym, 0) < ANALYST_RELANCE_S:
            return False
        _ANALYST_EN_COURS[sym] = now

    def _run():
        try:
            with contextlib.suppress(Exception):   # la panne reste dans le cache/journal, pas ici
                analyst_deep.get(sym)
        finally:
            with _ANALYST_VERROU:
                _ANALYST_EN_COURS.pop(sym, None)
    threading.Thread(target=_run, daemon=True, name='analystes-' + sym).start()
    return True


@bp.route('/api/analyst/<sym>')
def api_analyst(sym):
    """Données analystes PROFONDES (révisions BPA, surprises, notes, détention,
    initiés) — cache disque 12 h. En démo : rien (pas de réseau).

    Aucun réseau dans la requête : le cache est servi tel quel (`etat`
    CACHE ou PERIME + `stale`), et une entrée absente ou périmée déclenche une
    collecte EN FOND ; la page réessaie après `retry_s` (`etat` EN_COURS)."""
    if DEMO_MODE:
        return jsonify({'demo': True})
    sym = sym.upper()
    ent, frais = None, False
    with contextlib.suppress(Exception):           # cache illisible = absent
        ent, frais = analyst_deep.depuis_cache(sym)
    if frais:
        out = dict(ent)
        out['etat'] = 'CACHE'
        return jsonify(out)
    _collecter_analystes_en_fond(sym)
    if ent:
        out = dict(ent)
        out.update({'etat': 'PERIME', 'stale': True,
                    'note': 'données analystes périmées (> 12 h) servies telles quelles — '
                            'rafraîchissement en cours'})
        return jsonify(out)
    return jsonify({'available': False, 'etat': 'EN_COURS', 'sym': sym,
                    'retry_s': ANALYST_RETRY_S,
                    'note': 'collecte analystes en cours — la fiche réessaie d’elle-même'})


@bp.route('/api/names')
def api_names():
    """{ticker: nom d'entreprise} depuis le cache — pour afficher les noms dans Stock info
    (lecture seule, instantané, aucun fetch réseau)."""
    try:
        cache = _company._load()
        return jsonify({k: v.get('name') for k, v in cache.items()
                        if isinstance(v, dict) and v.get('name')})
    except Exception:
        return jsonify({})


#  ── SEC EDGAR : la seule source fondamentale DATEE du produit ───────────────
#
#  Elle etait ecrite, testee, et branchee NULLE PART. Les fondamentaux Reuters
#  sont refuses par le compte IBKR (10358) et `yfinance` n'expose aucune date
#  de publication : sans cette route, aucun fait fondamental du produit ne
#  peut dire ce qui etait connaissable a une date donnee.
#
#  Servie par le magasin d'instantanes, jamais en synchrone : un
#  `companyfacts` fait plusieurs mega-octets et se paie en secondes. La route
#  rend tout de suite ce qu'elle a et charge le reste EN FOND — c'est le
#  defaut P0.1, et on ne le rouvre pas pour une source de plus.
FRAICHEUR_SEC_S = 6 * 3600.0
PLAFOND_SEC_S = 48 * 3600.0
_MAGASIN_SEC = _instantane.Magasin('sec-fondamentaux')


@bp.route('/api/sec/fondamentaux/<sym>')
def api_sec_fondamentaux(sym):
    """Faits deposes a la SEC pour ce titre, chacun date de sa publication.

    Chaque fait porte DEUX dates : `observed_at` (la periode decrite) et
    `available_at` (le depot). Les confondre est exactement ce que la doctrine
    interdit — un retrotest qui daterait un resultat de sa periode emploierait
    un chiffre publie des semaines plus tard.
    """
    symbole = str(sym or '').upper()[:12]

    def _charger():
        r = _sec_f.fondamentaux(symbole)
        return r, {'source': 'SEC_EDGAR',
                   'qualite': 'MEASURED' if r.get('faits') else 'ABSENTE'}

    valeur, meta = _MAGASIN_SEC.servir(
        symbole, _charger, fraicheur_s=FRAICHEUR_SEC_S,
        plafond_s=PLAFOND_SEC_S, attendre=False)
    corps = dict(valeur or {'symbole': symbole, 'faits': []})
    corps['etat_fraicheur'] = {
        'etat': meta.etat,
        'age_s': meta.age_s,
        'chargement_en_cours': bool(getattr(meta, 'rafraichissement_en_cours', False)),
        'erreur': meta.erreur,
        'note': ('un premier appel sur un titre froid rend MISSING et charge en '
                 'fond : « aucun fait » signifie ici « pas encore », pas '
                 '« cette entreprise n a rien depose »'),
    }
    corps['read_only'] = True
    return jsonify(corps)


@bp.route('/api/sec/etat')
def api_sec_etat():
    """L'etat de la source — dont le drapeau et le contact, separement.

    `VERTEX_ENABLE_SEC` a longtemps figure dans un `.env` sans que RIEN ne le
    lise. Cette route rend la question verifiable depuis la page Systeme.
    """
    return jsonify(_sec_f.etat())


__all__ = ['bp']
