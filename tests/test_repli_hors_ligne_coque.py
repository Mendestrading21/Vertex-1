# -*- coding: utf-8 -*-
"""Le repli hors-ligne doit rendre une page LISIBLE, pas du HTML nu.

Mesure du 2026-09-06, navigateur réel : réseau injoignable sur l'origine, le
service worker sert bien la coque de son cache — mais la feuille de style est
demandée avec sa version (`/asset/css/bundle.css?v=vx-shell-10`) alors que le
pré-cache la stocke SANS requête. `cache.match` compare la query par défaut :
aucune correspondance, la page s'affichait sans style ET sans JavaScript, donc
sans même le voyant « hors ligne » qui aurait expliqué l'état. L'application
paraissait cassée alors qu'elle tournait (`/healthz` : `status: ok`).

Le repli tente donc une seconde correspondance en ignorant la query.
"""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SYSTEM = os.path.join(_ROOT, 'vertex', 'app', 'routes', 'system.py')


def _sw():
    with open(_SYSTEM, encoding='utf-8') as f:
        src = f.read()
    m = re.search(r'_SW_JS = r"""(.*?)"""', src, re.S)
    assert m, 'le service worker n’est plus dans system.py'
    return m.group(1)


def _code():
    """Le service worker SANS ses commentaires : les positions relatives ne
    doivent pas dépendre d'une phrase d'explication."""
    lignes = [l for l in _sw().splitlines() if not l.strip().startswith('//')]
    return chr(10).join(lignes)


def test_le_repli_ignore_la_version_de_la_feuille_de_style():
    sw = _sw()
    assert 'ignoreSearch:true' in sw.replace(' ', ''), (
        'sans `ignoreSearch`, la coque hors-ligne est servie SANS style : '
        'le pré-cache stocke /asset/css/bundle.css, la page demande ?v=…')
    # l'ordre compte : le frais d'abord, puis l'exact, puis la version voisine
    code = _code()
    i_exact = code.index('cache.match(req)')
    i_ignore = code.index('ignoreSearch')
    assert i_exact < i_ignore, 'la correspondance EXACTE doit rester prioritaire'


def test_le_prechargement_contient_bien_la_feuille_sans_version():
    sw = _sw()
    assert "'/asset/css/bundle.css'" in sw, (
        'le pré-cache ne contient plus la feuille : le repli n’aurait rien à servir')


def test_le_reseau_reste_prioritaire():
    """Network-first : le repli ne doit jamais devenir la voie normale."""
    code = _code()
    assert 'Promise.race([fetch(req)' in code
    assert code.index('Promise.race([fetch(req)') < code.index('}catch(')


def test_la_raison_est_ecrite_dans_le_service_worker():
    sw = _sw()
    assert 'coque' in sw and 'nue' in sw, (
        'la raison du repli élargi n’est plus écrite à côté de lui')
