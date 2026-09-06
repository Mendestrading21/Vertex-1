# -*- coding: utf-8 -*-
"""tools/qa/exercer_routes.py — TOUTES les routes répondent-elles, et quoi ?

L'audit navigateur ouvre les pages ; il ne dit rien des routes qu'aucune page
n'appelle, ni de celles qu'une page appelle avec un paramètre inhabituel. Cet
outil recense les règles Flask du runtime et exerce chaque route lisible
(GET/HEAD) avec le client de test, sans réseau et sans code d'accès.

Pour chaque route il relève :

- le STATUT et le temps de réponse (une route lente dans la requête utilisateur
  est un défaut de contrat : une page sert des instantanés bornés) ;
- si la charge est du JSON, sa FORME : vide, objet sans clé, liste vide, ou
  contenu — et si une absence est NOMMÉE (une clé `error`, `reason`, `etat`,
  `note`, `available`) plutôt que silencieuse ;
- les COLLISIONS : deux règles pour un même chemin, c'est-à-dire deux
  propriétaires pour une même capacité.

Lecture seule : aucune méthode d'écriture n'est exercée, aucun fichier n'est
modifié. `READONLY` et `ANALYSIS_ONLY` restent vrais.

    python tools/qa/exercer_routes.py [--json rapport.json] [--lent 1.5]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Valeurs d'exemple pour les routes paramétrées. Un symbole réel du scan et
#: des identifiants inoffensifs : on exerce la LECTURE, jamais une écriture.
_EXEMPLES = {
    'sym': 'NVDA', 'symbol': 'NVDA', 'ticker': 'NVDA',
    'sid': 'NVDA', 'id': '1', 'pid': '1', 'position_id': '1',
    'name': 'default', 'key': 'default', 'slug': 'default',
    'path': 'index', 'filename': 'index',
}
#: Routes à ne PAS exercer : elles ferment la session ou déclenchent un travail
#: lourd que ce balayage n'a pas à provoquer.
_INTERDITES = ('/logout', '/login', '/sw.js', '/api/client-log')
#: Clés qui NOMMENT une absence. Une charge vide qui en porte une est honnête.
_NOMME = ('error', 'erreur', 'reason', 'motif', 'etat', 'state', 'note',
          'available', 'disponible', 'status', 'statut', 'message', 'usage',
          'en_cours', 'warning', 'limites')


def _client():
    os.environ.setdefault('NO_IBKR', '1')
    os.environ.setdefault('DEMO', '0')
    os.environ['VERTEX_CODE'] = ''
    sys.path.insert(0, RACINE)
    from vertex.runtime import app
    app.config['TESTING'] = True
    return app, app.test_client()


def _remplir(regle: str) -> str | None:
    """Chemin concret pour une règle paramétrée, ou None si on ne sait pas."""
    out = regle
    while '<' in out:
        d = out.index('<')
        f = out.index('>', d)
        jeton = out[d + 1:f]
        nom = jeton.split(':')[-1]
        val = _EXEMPLES.get(nom)
        if val is None:
            return None
        out = out[:d] + val + out[f + 1:]
    return out


def _forme(charge) -> str:
    if charge is None:
        return 'non-JSON'
    if isinstance(charge, dict):
        if not charge:
            return 'objet VIDE'
        return 'objet %d clés' % len(charge)
    if isinstance(charge, list):
        return 'liste vide' if not charge else 'liste %d' % len(charge)
    return type(charge).__name__


def _nomme_l_absence(charge) -> bool:
    if isinstance(charge, dict):
        return any(k in charge for k in _NOMME)
    return False


def collisions_seules() -> dict:
    """Les collisions SANS exercer une seule route.

    L'exercice complet fait de vraies requêtes (donc du réseau côté sources) :
    il a sa place dans un rapport, pas dans un banc de test. La collision, elle,
    se lit dans la table des règles — c'est une propriété de structure.
    """
    app, _ = _client()
    vues: dict[tuple, list] = {}
    for r in app.url_map.iter_rules():
        for m in sorted((r.methods or set()) - {'HEAD', 'OPTIONS'}):
            vues.setdefault((str(r.rule), m), []).append(r.endpoint)
    return {'%s [%s]' % (chemin, m): sorted(set(eps))
            for (chemin, m), eps in vues.items() if len(set(eps)) > 1}


def exercer(lent: float = 1.5) -> dict:
    app, cli = _client()
    #  Une COLLISION est deux propriétaires pour la MÊME capacité, c'est-à-dire
    #  le même chemin ET la même méthode. Grouper par chemin seul accusait trois
    #  routes REST parfaitement normales — `/api/tracking` en GET et en POST,
    #  `/api/tracking/<id>` en GET et en PATCH, `/api/client-log` en GET et en
    #  POST : deux verbes, deux fonctions, un seul chemin. Une garde qui crie au
    #  loup sur la forme normale du produit finit par être ignorée.
    vues: dict[tuple, list] = {}
    for r in app.url_map.iter_rules():
        for m in sorted((r.methods or set()) - {'HEAD', 'OPTIONS'}):
            vues.setdefault((str(r.rule), m), []).append(r.endpoint)
    collisions = {'%s [%s]' % (chemin, m): sorted(set(eps))
                  for (chemin, m), eps in vues.items() if len(set(eps)) > 1}

    releves = []
    for r in sorted(app.url_map.iter_rules(), key=lambda x: str(x.rule)):
        methodes = r.methods or set()
        if 'GET' not in methodes:
            continue
        if str(r.rule).startswith(_INTERDITES) or 'static' in r.endpoint:
            continue
        chemin = _remplir(str(r.rule))
        if chemin is None:
            releves.append({'regle': str(r.rule), 'endpoint': r.endpoint,
                            'statut': None, 'note': 'paramètre inconnu — non exercée'})
            continue
        t0 = time.time()
        try:
            rep = cli.get(chemin)
            ms = round((time.time() - t0) * 1000)
            charge = rep.get_json(silent=True)
            releves.append({
                'regle': str(r.rule), 'chemin': chemin, 'endpoint': r.endpoint,
                'statut': rep.status_code, 'ms': ms,
                'forme': _forme(charge),
                'absence_nommee': _nomme_l_absence(charge),
                'lent': ms > lent * 1000,
            })
        except Exception as exc:                      # noqa: BLE001
            releves.append({'regle': str(r.rule), 'chemin': chemin,
                            'endpoint': r.endpoint, 'statut': 'EXCEPTION',
                            'note': '%s: %s' % (type(exc).__name__, exc)})
    return {'collisions': collisions, 'releves': releves}


def defauts(r: dict) -> list[str]:
    out = []
    for chemin, eps in (r['collisions'] or {}).items():
        out.append('COLLISION  %s → %s' % (chemin, ', '.join(eps)))
    for x in r['releves']:
        s = x.get('statut')
        if s == 'EXCEPTION':
            out.append('EXCEPTION  %s : %s' % (x['regle'], x.get('note')))
        elif isinstance(s, int) and s >= 500:
            out.append('HTTP %d    %s' % (s, x['chemin']))
        elif x.get('lent'):
            out.append('LENTE      %s : %d ms' % (x['chemin'], x['ms']))
        elif (x.get('forme') in ('objet VIDE', 'liste vide')
              and not x.get('absence_nommee') and isinstance(s, int) and s < 400):
            out.append('MUETTE     %s : %s sans clé qui nomme l’absence'
                       % (x['chemin'], x['forme']))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', default=None)
    ap.add_argument('--lent', type=float, default=1.5)
    a = ap.parse_args()
    r = exercer(a.lent)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    d = defauts(r)
    exercees = [x for x in r['releves'] if isinstance(x.get('statut'), int)]
    print('routes GET %d · exercées %d · non exercées %d · collisions %d · défauts %d'
          % (len(r['releves']), len(exercees),
             len(r['releves']) - len(exercees), len(r['collisions']), len(d)))
    for ligne in d:
        print('  ' + ligne)
    return 1 if any(x.startswith(('HTTP 5', 'EXCEPTION', 'COLLISION')) for x in d) else 0


if __name__ == '__main__':
    sys.exit(main())
