#!/usr/bin/env python3
"""Vertex Test 1.0 · G2 — QUELLES SURFACES SE VIDENT, ET LE PRODUIT SAIT-IL RÉPONDRE ?

Trois défauts de suite ont eu la même forme : **une donnée existait et l'écran
restait vide**.

| chantier | ce qui était su | ce qui était montré |
| --- | --- | --- |
| hors séance | `last` sans `close` | rien (prix jeté) |
| échelle IBKR | le différé aurait répondu | rien (jamais demandé) |
| cotations | ACN à 198,0 dans le scan | `results: {}` |

Les trois ont été trouvés **un par un, après signalement**. Cet outil arrête
cette boucle : il interroge toutes les surfaces servies et classe ce qu'elles
rendent, pour que le quatrième cas se voie avant d'être vécu.

## Ce que « vide » veut dire ici

Pas « HTTP 500 » — ça se voit. **HTTP 200 avec une charge sans aucune donnée
exploitable** : `{}`, `{'results': {}}`, `{'items': []}`. C'est la panne
silencieuse, celle qui affiche une carte propre et creuse.

## Ce que l'outil NE dit PAS

Il ne dit pas « défaut ». Beaucoup de surfaces sont **légitimement** vides :
aucune alerte déclenchée, aucun trade au journal, aucune position déclarée. Un
vide honnête est un vide. L'outil sépare donc :

- **VIDE ATTENDU** — la surface dépend du bureau de l'utilisateur, qui peut
  légitimement être vide ;
- **VIDE À EXAMINER** — la surface décrit le marché ou les moteurs, que le
  produit connaît par ailleurs. C'est là qu'ont vécu les trois défauts.

Le tri final reste humain, comme pour la preuve de non-usage du CSS.

Usage :
    python tools/mesures/mesurer_surfaces_vides.py [--json] [--base URL]
Sorties : 0 = mesuré, 2 = témoin muet.
"""
from __future__ import annotations

import os

import json
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures._sonde_http import (  # noqa: E402
    BUDGET_INTERACTIF, appeler, sonder_pret)

#  PORT DE MESURE PAR DÉFAUT : 5003, l'instance de VÉRIFICATION.
#
#  Mesuré le 2026-09-06 : ces outils visaient 5002 par défaut, c'est-à-dire, sur
#  le poste de l'auteur, l'instance RÉELLE branchée sur le courtier et protégée
#  par un code d'accès. Un outil de mesure qui frappe l'instance de travail lui
#  vole des requêtes, la ralentit, et sur une machine tierce sonde un port dont
#  il ne sait rien. L'instance de vérification (5003) existe précisément pour
#  ça : sans IBKR, sans code, sans desk. `VERTEX_MESURE_BASE` reste le moyen de
#  viser autre chose, explicitement.
BASE_DEFAUT = os.environ.get('VERTEX_MESURE_BASE', 'http://127.0.0.1:5003')

#: Échantillons pour les routes paramétrées — un symbole que le scan connaît,
#: sinon la mesure porterait sur « symbole inconnu » et non sur la surface.
ECHANTILLONS = {'sym': 'AAPL', 'symbol': 'AAPL', 'ticker': 'AAPL',
                'decision_id': 'inexistant', 'group': 'inexistant',
                'key': 'inexistant', 'name': 'inexistant'}

#: Surfaces dont le vide vient du BUREAU de l'utilisateur : pas de trade
#: déclaré, pas d'alerte armée, pas de note. Leur vide est une vérité sur
#: l'utilisateur, pas une panne du produit.
DEPEND_DU_BUREAU = (
    '/api/desk', '/api/alerts/status', '/api/positions/alerts',
    '/api/positions/state', '/api/journal', '/api/portefeuille',
    '/api/strategie', '/api/planning/ticket', '/api/pretrade/check',
    '/api/skyler/memory', '/api/portfolio/team', '/api/portfolio/stress',
    '/api/portfolio/context',  # /api/ibkr/positions retiree au lot 2 (market-data-only)
)

#: Mots qui ne sont PAS une donnée : un statut n'est pas un contenu. Sans cette
#: liste, `{'status': 'ok'}` passerait pour une surface pleine — et l'outil ne
#: verrait plus jamais un écran creux.
MOTS_VIDES = frozenset({
    'ok', 'error', 'none', 'null', 'n/d', '—', '-', 'unknown', 'inconnu',
    'demo', 'false', 'true', 'aucune', 'aucun', 'empty', 'vide', 'not_found',
})


def compter_donnees(charge, _profondeur=0) -> int:
    """Combien de valeurs EXPLOITABLES cette charge porte-t-elle ?

    Fonction pure — c'est par elle que les témoins passent.

    Ne comptent pas : les conteneurs vides, les booléens, les mots de statut,
    et les nombres à zéro **isolés dans un compteur**… non : un `0` compte,
    parce que « zéro opportunité » est une réponse, pas un silence. Ce qui ne
    compte pas, c'est l'ABSENCE.
    """
    if _profondeur > 8:
        return 0
    if charge is None or isinstance(charge, bool):
        return 0
    if isinstance(charge, (int, float)):
        return 1
    if isinstance(charge, str):
        t = charge.strip()
        return 0 if (not t or t.lower() in MOTS_VIDES) else 1
    if isinstance(charge, dict):
        return sum(compter_donnees(v, _profondeur + 1) for v in charge.values())
    if isinstance(charge, (list, tuple)):
        return sum(compter_donnees(v, _profondeur + 1) for v in charge)
    return 0


#: Surfaces alimentees par un CACHE que le reseau remplit (noms d'entreprises,
#: fiches analystes). Leur vide dit « le cache n'est pas encore rempli », pas
#: « le produit est casse » — et dans un environnement sans reseau il ne peut
#: pas l'etre. Les confondre ferait accuser le produit d'une contrainte
#: d'environnement.
DEPEND_DU_RESEAU = ('/api/names', '/api/analyst/', '/api/weekly',
                    '/api/live/report', '/api/search')


def classer(chemin: str, statut: int, charge, *, expiree: bool = False,
            scan_fait: bool = True) -> str:
    """PLEINE / VIDE_* / PAS_ENCORE_PRET / ATTENDU_404 / EXPIREE / ERREUR.

    `ATTENDU_404` n'est pas une indulgence : les routes parametrees sont
    interrogees avec des echantillons DELIBEREMENT inexistants
    (`decision_id=inexistant`). Un 404 y est la BONNE reponse, et le compter
    comme une panne noierait les vraies sous du bruit que l'instrument
    fabrique lui-meme.

    `EXPIREE` est SEPAREE d'`ERREUR`. Mesure du 24 aout 2026 : sur un produit
    inchange, cet outil a annonce 4, puis 1, puis 0, puis 5 « surfaces en
    erreur » selon la chauffe du serveur — et jamais les memes. Interrogees
    une a une avec un delai genereux, toutes repondaient 200 avec leurs
    donnees. Ce n'etaient pas des pannes : c'etait l'impatience de l'outil,
    presentee comme une mesure du produit.

    `PAS_ENCORE_PRET` couvre le second fantome. Tant que `last_scan` vaut
    `null`, les surfaces alimentees par le scan sont vides par construction :
    `/api/cockpit` et `/api/comite` sortaient « vides A EXAMINER » sur un
    serveur fraichement redemarre, et se remplissaient des le scan termine.
    On ne tient PAS de liste de ces surfaces — une liste ecrite a la main
    excuserait un jour un vide reel. La regle porte sur l'etat du produit :
    **un produit qui n'a pas scanne ne permet aucune conclusion** sur ses
    surfaces de marche et de moteurs.
    """
    if expiree:
        return 'EXPIREE'
    if statut == 404 and any(v in chemin for v in ECHANTILLONS.values()
                             if v.startswith('inexistant')):
        return 'ATTENDU_404'
    if statut != 200:
        return 'ERREUR'
    if compter_donnees(charge) > 0:
        return 'PLEINE'
    if any(chemin.startswith(p) for p in DEPEND_DU_BUREAU):
        return 'VIDE_ATTENDU'
    if any(chemin.startswith(p) for p in DEPEND_DU_RESEAU):
        return 'VIDE_CACHE_RESEAU'
    if not scan_fait:
        return 'PAS_ENCORE_PRET'
    return 'VIDE_A_EXAMINER'


FLUX_PERMANENTS = ('/api/live/events',)

ROUTES_A_EFFET = (
    '/api/rescan', '/api/live/refresh', '/api/skyler/sweep',
    '/api/ai/refresh', '/api/options/scanner', '/api/options/simulate',
    '/api/weekly-regen', '/api/copilot/ask',
)


def surfaces_servies() -> list:
    """Corpus dérivé de la TABLE DE ROUTAGE, jamais d'une liste écrite à la
    main : une liste recopiée diverge au premier ajout de route, et la mesure
    porte alors sur un produit qui n'existe plus."""
    import terminal                                          # noqa: F401
    vues = []
    for regle in terminal.app.url_map.iter_rules():
        if 'GET' not in (regle.methods or set()):
            continue
        chemin = str(regle)
        if not chemin.startswith('/api/'):
            continue
        for cle, val in ECHANTILLONS.items():
            chemin = chemin.replace('<%s>' % cle, val)
            chemin = chemin.replace('<string:%s>' % cle, val)
            chemin = chemin.replace('<path:%s>' % cle, val)
        if '<' in chemin:                                    # paramètre inconnu
            continue
        if any(chemin.startswith(x) for x in ROUTES_A_EFFET):
            continue
        if chemin in FLUX_PERMANENTS:
            continue
        vues.append(chemin)
    return sorted(set(vues))


def temoins() -> list:
    """Un classeur qui range tout dans « pleine » ne verrait plus jamais un
    écran creux ; un classeur qui range tout dans « vide » crierait partout."""
    e = []
    if compter_donnees({'results': {}}) != 0:
        e.append('TEMOIN ROMPU : un conteneur vide passe pour une donnee')
    if compter_donnees({'items': [], 'meta': {'ok': True}}) != 0:
        e.append('TEMOIN ROMPU : un statut passe pour un contenu — c\'est '
                 'exactement ce qui rend une carte creuse invisible')
    if compter_donnees({'quotes': {'ACN': {'last': 198.0}}}) != 1:
        e.append('TEMOIN MUET : une vraie valeur n\'est pas comptee')
    if compter_donnees({'n': 0}) != 1:
        e.append('TEMOIN ROMPU : un zero MESURE est traite comme une absence — '
                 '« zero opportunite » est une reponse, pas un silence')
    if compter_donnees({'etat': 'n/d', 'source': 'demo'}) != 0:
        e.append('TEMOIN ROMPU : un aveu d\'absence compte comme une donnee')
    if classer('/api/desk', 200, {}) != 'VIDE_ATTENDU':
        e.append('TEMOIN ROMPU : un vide qui vient du bureau est signale comme '
                 'suspect — l\'outil crierait sur un utilisateur sans trades')
    corpus = surfaces_servies()
    if any(x in FLUX_PERMANENTS for x in corpus):
        e.append('TEMOIN ROMPU : un FLUX permanent est dans le corpus — '
                 'l\'instrument attendrait une fin qui ne vient jamais et '
                 'accuserait un endpoint qui fonctionne')
    if any(x.startswith('/api/rescan') for x in corpus):
        e.append('TEMOIN ROMPU : une route A EFFET est dans le corpus — '
                 'l\'instrument declencherait un rescan au lieu de mesurer')
    if classer('/api/market/summary', 200, {}) != 'VIDE_A_EXAMINER':
        e.append('TEMOIN MUET : une surface MARCHE vide n\'est pas signalee — '
                 'c\'est precisement la ou les trois defauts ont vecu')
    if classer('/api/skyler/memory/inexistant', 404, None) != 'ATTENDU_404':
        e.append('TEMOIN ROMPU : un 404 sur un echantillon DELIBEREMENT '
                 'inexistant est compte comme une panne — l\'instrument noie '
                 'les vraies sous son propre bruit')
    if classer('/api/decision/reelle', 404, None) != 'ERREUR':
        e.append('TEMOIN ROMPU : un VRAI 404 est excuse — l\'indulgence du 404 '
                 'd\'echantillon s\'est etendue a tout')
    if classer('/api/names', 200, {}) != 'VIDE_CACHE_RESEAU':
        e.append('TEMOIN ROMPU : un cache reseau vide est confondu avec un '
                 'defaut produit')
    #  ─── les deux fantomes mesures le 24 aout 2026 ───────────────────────
    if classer('/api/market/summary', 0, None, expiree=True) != 'EXPIREE':
        e.append('TEMOIN ROMPU : une EXPIRATION est comptee comme une panne — '
                 'l\'outil annoncerait 4, 1, 0 puis 5 « surfaces en erreur » '
                 'sur un produit inchange, selon sa seule patience')
    if classer('/api/market/summary', 200, {}, scan_fait=False) != 'PAS_ENCORE_PRET':
        e.append('TEMOIN ROMPU : une surface vide AVANT le premier scan est '
                 'declaree suspecte — l\'auditeur cherche un defaut qui '
                 'n\'existe pas (mesure : /api/cockpit et /api/comite)')
    #  Contre-epreuves. Un gardien qui excuse TOUT ne garde plus rien.
    if classer('/api/market/summary', 200, {}, scan_fait=True) != 'VIDE_A_EXAMINER':
        e.append('TEMOIN MUET : l\'indulgence « pas encore pret » s\'est '
                 'etendue au produit CHAUD — un vrai ecran creux passerait')
    if classer('/api/decision/reelle', 500, None) != 'ERREUR':
        e.append('TEMOIN MUET : un VRAI 500 est excuse — la separation '
                 'expiration/erreur a desarme la detection des pannes')
    return e


def mesurer(base: str = BASE_DEFAUT) -> dict:
    echecs = temoins()
    #  L'etat de CHAUFFE se demande AVANT de conclure quoi que ce soit. Un
    #  produit qui n'a pas encore scanne rend des surfaces vides par
    #  construction : les declarer suspectes envoie l'auditeur chercher un
    #  defaut qui n'existe pas.
    pret = sonder_pret(base)
    scan_fait = bool(pret.get('scan_fait'))
    releves = []
    for chemin in surfaces_servies():
        rep = appeler(base, chemin)
        releves.append({
            'chemin': chemin, 'statut': rep.statut,
            'duree_s': round(rep.duree_s, 3),
            'donnees': compter_donnees(rep.charge),
            'lente': rep.duree_s > BUDGET_INTERACTIF,
            'classe': classer(chemin, rep.statut, rep.charge,
                              expiree=rep.expiree, scan_fait=scan_fait),
        })
    par_classe = {}
    for r in releves:
        par_classe.setdefault(r['classe'], []).append(r['chemin'])
    return {'base': base, 'pret': pret, 'echecs_temoins': echecs,
            'releves': releves, 'par_classe': par_classe,
            'total': len(releves)}


def rendre_texte(r: dict) -> str:
    pret = r.get('pret') or {}
    o = ['QUELLES SURFACES SE VIDENT ?', '=' * 60,
         'base : %s   surfaces servies : %d' % (r['base'], r['total'])]
    #  L'etat de chauffe est en TETE du rapport : sans lui, le lecteur ne peut
    #  pas savoir ce que ce releve vaut.
    if not pret.get('joignable'):
        o.append('CHAUFFE : produit INJOIGNABLE sur /healthz — le releve '
                 'ci-dessous ne mesure rien du produit.')
    elif pret.get('scan_fait'):
        o.append('CHAUFFE : scan a %s (%s titres, %s s) — releve concluant.'
                 % (pret.get('last_scan'), pret.get('scannes'),
                    pret.get('scan_age')))
    else:
        o.append('CHAUFFE : AUCUN SCAN ENCORE (last_scan null) — les surfaces '
                 'de marche et de moteurs sont vides PAR CONSTRUCTION. Elles '
                 'sont classees PAS_ENCORE_PRET, pas suspectes. Relancer une '
                 'fois le scan termine.')
    o.append('')
    for classe in ('ERREUR', 'EXPIREE', 'VIDE_A_EXAMINER', 'PAS_ENCORE_PRET',
                   'VIDE_CACHE_RESEAU', 'VIDE_ATTENDU', 'ATTENDU_404',
                   'PLEINE'):
        liste = r['par_classe'].get(classe) or []
        o.append('%-18s %3d' % (classe, len(liste)))
    o.append('')
    for classe, titre in (('ERREUR', 'EN ERREUR'),
                          ('EXPIREE', "EXPIREES — l'outil n'a pas attendu assez"),
                          ('VIDE_A_EXAMINER', 'VIDES — A EXAMINER')):
        liste = r['par_classe'].get(classe) or []
        if liste:
            o.append('%s :' % titre)
            for c in liste:
                o.append('   %s' % c)
            o.append('')
    #  Les durees, enfin mesurees. Sans elles, aucun avant/apres n'etait
    #  possible — et le programme en exige un a chaque lot.
    lentes = sorted((x for x in r['releves'] if x.get('lente')),
                    key=lambda x: -x['duree_s'])
    o.append('PLUS LENTES QUE %.0f s (seuil de confort DECLARE, pas mesure : '
             'aucun' % BUDGET_INTERACTIF)
    o.append("AbortController n'existe dans l'UI, donc rien n'abandonne une")
    o.append('requete cote navigateur) : %d' % len(lentes))
    for x in lentes[:8]:
        o.append('   %6.1f s  %s' % (x['duree_s'], x['chemin']))
    if not lentes:
        toutes = sorted(r['releves'], key=lambda x: -x['duree_s'])[:5]
        o.append('   aucune. Les cinq plus longues :')
        for x in toutes:
            o.append('   %6.1f s  %s' % (x['duree_s'], x['chemin']))
    o.append('')
    o.append("LECTURE : un vide n'est pas un defaut, et une LENTEUR n'est pas")
    o.append('une panne. Une surface qui depend du RESEAU (caches de noms,')
    o.append("fiches analystes) est vide tant que le cache n'est pas rempli —")
    o.append("dans un environnement sans reseau, elle NE PEUT PAS l'etre.")
    o.append('Lancer cet outil SUR LA MACHINE DE PRODUCTION, SCAN TERMINE, est')
    o.append('donc la seule mesure qui discrimine vraiment.')
    o.append('BUREAU peut etre vide en verite. Celles qui decrivent le MARCHE ou')
    o.append('les MOTEURS, non : le produit connait ces donnees par ailleurs.')
    o.append('Cet outil ne corrige rien — il montre ou regarder.')
    return '\n'.join(o)


def main() -> int:
    base = BASE_DEFAUT
    if '--base' in sys.argv:
        base = sys.argv[sys.argv.index('--base') + 1]
    r = mesurer(base)
    if r['echecs_temoins']:
        for x in r['echecs_temoins']:
            print(x, file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2, ensure_ascii=False) if '--json' in sys.argv
          else rendre_texte(r))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
