#!/usr/bin/env python3
"""Vertex Test 1.0 · #781 — QUELLES RÈGLES CSS SONT *PROUVÉES* INATTEIGNABLES ?

`mesurer_couche_visuelle.py` rend 476 règles « jamais appariées au chargement ».
C'est une **liste de candidates**, et `CLEANUP_POLICY.md` demande davantage :
une **preuve de non-usage**. Cet outil produit cette preuve — ou constate qu'elle
n'existe pas.

## Pourquoi le non-appariement ne prouve rien

Une règle d'état ne peut pas s'apparier à l'instant du relevé. `.vx-drawer.open`
n'existe que drawer ouvert ; `.vx-row.is-selected` que ligne sélectionnée. Les
compter comme mortes serait supprimer précisément le CSS des états — celui qu'on
voit le moins et dont on a le plus besoin.

## Le critère de preuve

Une règle est **prouvée inatteignable** quand **aucune** des classes de son
sélecteur n'apparaît, comme littéral, dans **aucun octet servi** : ni dans le
HTML des huit espaces, ni dans le JavaScript qu'ils chargent.

Le raisonnement : si `vx-machin` n'est écrit nulle part dans ce que le
navigateur reçoit, aucun chemin — rendu serveur, `classList.add`, template — ne
peut le poser. La règle ne peut pas s'allumer.

Une règle dont **au moins une** classe apparaît quelque part est classée
`ATTEIGNABLE` — même si elle ne s'apparie pas au chargement. C'est le cas des
états, et c'est voulu : le doute profite à la règle.

## La faille du critère, et sa mesure

Un nom de classe **construit** (`'vx-' + genre`) n'apparaît jamais en entier
dans les octets. Une règle visant `vx-haut` serait alors déclarée morte alors
que du JS peut la poser. L'outil **cherche donc ces constructions** et refuse de
conclure s'il en trouve dans un préfixe concerné — mieux vaut ne rien supprimer
que supprimer sur une preuve trouée.

Cet outil **ne supprime rien**.

Usage :
    python tools/mesures/mesurer_regles_mortes.py [--json] [--base URL]
Sorties : 0 = mesuré, 2 = témoin muet, 3 = NON MESURÉ (navigateur indisponible).
"""
from __future__ import annotations

import json
import pathlib
import re
import os
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures._sonde_http import appeler  # noqa: E402
from tools.mesures.mesurer_qa_espaces import (  # noqa: E402
    abandonner_sans_navigateur, navigateur_pret)

#  `VERTEX_MESURE_BASE` : cibler une autre instance (par ex. l'instance QA
#  sans code d'accès, 127.0.0.1:5003) sans toucher l'instance de travail.
BASE_DEFAUT = os.environ.get('VERTEX_MESURE_BASE', 'http://127.0.0.1:5002')

#: Les classes d'un sélecteur CSS. `.a.b .c:hover` -> {a, b, c}
_CLASSES = re.compile(r'\.(-?[_a-zA-Z][\w-]*)')

#: Une classe CONSTRUITE : un nom assemblé plutôt qu'écrit en entier.
#:
#: Le motif doit rester ÉTROIT. Une première version cherchait toute
#: interpolation `${…}` : elle aurait trouvé chaque gabarit de texte, d'URL ou
#: de nombre du produit, déclaré la preuve « non fiable » partout, et rendu
#: l'outil inutilisable — un détecteur qui crie sur tout ne guide rien.
#:
#: Deux formes seulement, celles qui produisent réellement un nom partiel :
#:   `'vx-quelquechose' +`      concaténation depuis un préfixe
#:   `` `…vx-truc${…}` ``       interpolation DANS un gabarit qui porte `vx-`
_CONSTRUITE = re.compile(
    r"""['"]([\w-]*vx-[\w-]*)['"]\s*\+|`[^`]*vx-[\w-]*\$\{""")


def _lire(url):
    """La `Reponse` de la sonde partagee — statut, corps et duree.

    L'ancienne version rendait `''` sur toute exception. C'etait le plus
    couteux des defauts de cette classe : une page qui n'avait pas repondu
    dans les 25 s entrait dans le corpus comme une page VIDE, et chaque classe
    CSS qu'elle seule utilise devenait « jamais apparaissante » — donc
    candidate a la suppression. Un instrument qui propose de supprimer du code
    a cause de sa propre impatience est pire qu'aucun instrument.

    Le STATUT est rendu, pas seulement le corps : un 404 sur un echantillon
    deliberement inexistant n'est pas une page qu'on n'a pas su lire.
    """
    return appeler('', url)


def _attendu_absent(chemin: str) -> bool:
    """Ce 404 etait-il DEMANDE ?

    Les routes parametrees sont instanciees avec des echantillons
    deliberement inexistants (`/memory/inexistant`). Les compter comme
    « pages non lues » declarerait le corpus ampute a CHAQUE passage, et
    retomberait toutes les preuves a INDECIDABLE — un outil qui ne conclut
    jamais ne sert a rien. Defaut trouve en executant l'outil, pas en le
    relisant.
    """
    return any(v in chemin for v in _ECHANTILLONS.values()
               if str(v).startswith('inexistant'))


#: Routes GET qui DÉCLENCHENT quelque chose plutôt que de rendre une page.
#: Les visiter pour bâtir un corpus reviendrait à lancer du travail pour
#: mesurer — et la mesure ne doit rien provoquer.
_ROUTES_ACTIONS = {'/weekly-regen', '/scan', '/logout', '/sw.js', '/readyz',
                   '/healthz', '/quotes', '/weekly-feed'}


#: Valeurs concrètes pour exercer les routes PARAMÉTRÉES. Sans elles, tout le
#: balisage des fiches — `/analysis/<sym>`, `/company/<sym>`, `/options/<sym>` —
#: reste hors du corpus, et une classe qui n'y vit que là serait « prouvée »
#: morte. C'était le TROISIÈME trou de cette preuve.
_ECHANTILLONS = {'sym': 'AAPL', 'decision_id': 'inexistant',
                 'group': 'inexistant', 'key': 'inexistant'}


def _instancier(rule):
    """`/analysis/<sym>` -> `/analysis/AAPL`. None si un paramètre est inconnu."""
    out = rule
    for m in re.finditer(r'<([^>]+)>', rule):
        nom = m.group(1).split(':')[-1]
        if nom not in _ECHANTILLONS:
            return None
        out = out.replace(m.group(0), _ECHANTILLONS[nom])
    return out


def routes_html():
    """TOUTES les routes HTML du produit, lues dans la table de routage.

    **C'est ici que la première version se trompait.** Elle bâtissait le corpus
    à partir des huit espaces de `PRIMARY_NAV`, et le produit en sert bien
    davantage : `/design-system`, `/widget-lab`, `/intelligence`, `/tracking`…

    Conséquence mesurée : `.ds-note` — écrit deux fois dans la page
    `/design-system` servie — ressortait **« prouvée inatteignable »**. Une
    fausse preuve, c'est-à-dire exactement ce qui aurait autorisé une
    suppression injustifiée. Le corpus vient donc de la table de routage, pas
    d'une liste choisie à la main.
    """
    import os
    os.environ.setdefault('DEMO', '1')
    os.environ.setdefault('NO_IBKR', '1')
    os.environ.setdefault('START_ON_IMPORT', '0')
    import terminal
    rules = []
    for r in terminal.app.url_map.iter_rules():
        rule = str(r.rule)
        if 'GET' not in r.methods:
            continue
        if rule.startswith(('/api/', '/static')) or rule in _ROUTES_ACTIONS:
            continue
        if '<' in rule:
            #  Les fiches rendent un balisage que les pages d'index n'ont pas.
            concret = _instancier(rule)
            if concret:
                rules.append(concret)
            continue
        rules.append(rule)
    return sorted(set(rules))


#: Pages et scripts que la mesure n'a PAS pu lire. Une conclusion
#: « regle morte » tiree d'un corpus ampute proposerait de supprimer du
#: code a cause de l'impatience de l'instrument.
NON_LUES: list = []


def octets_servis(base, routes=None):
    """Tout ce que le navigateur reçoit : chaque page HTML et son JavaScript.

    Le CSS est volontairement EXCLU : y chercher une classe la trouverait
    toujours — c'est de là qu'on part."""
    base = base.rstrip('/')
    corpus, sources_js = {}, set()
    #  Ce que l'on n'a PAS pu lire. Auparavant `continue` muet : le corpus
    #  retrecissait sans que rien ne le dise, et chaque classe vivant sur la
    #  page manquante devenait « jamais appariee », donc candidate a la
    #  suppression. `NON_LUES` rend cette amputation VISIBLE.
    NON_LUES.clear()
    for route in (routes if routes is not None else routes_html()):
        rep = _lire(base + route)
        if not rep.a_repondu:
            if not (rep.statut == 404 and _attendu_absent(route)):
                NON_LUES.append('page:%s (%s)'
                                % (route, rep.erreur or rep.statut))
            continue
        html = rep.texte
        corpus['page:' + route] = html
        for m in re.finditer(r'<script[^>]+src="([^"]+)"', html):
            src = m.group(1)
            if src.startswith('/'):
                sources_js.add(src)
    for src in sorted(sources_js):
        rep = _lire(base + src)
        if not rep.a_repondu:
            NON_LUES.append('js:%s (%s)' % (src, rep.erreur or rep.statut))
            continue
        corpus['js:' + src] = rep.texte
    return corpus


def classes_construites(corpus):
    """Les endroits où un nom de classe est ASSEMBLÉ plutôt qu'écrit.

    C'est la faille du critère de preuve : ce qui est assemblé n'apparaît pas
    en entier dans les octets."""
    trouves = []
    for nom, contenu in corpus.items():
        if not nom.startswith('js:'):
            continue
        for m in _CONSTRUITE.finditer(contenu):
            frag = m.group(0)[:60]
            if 'vx-' in frag:
                trouves.append({'source': nom, 'fragment': frag})
    #  Dedoublonne sur le fragment : le meme idiome revient souvent.
    vus, uniques = set(), []
    for t in trouves:
        if t['fragment'] in vus:
            continue
        vus.add(t['fragment'])
        uniques.append(t)
    return uniques


def prefixes_construits(construites):
    """Les préfixes depuis lesquels du JS assemble un nom de classe.

    Mesuré : `'vx-chart-size-' +` en construit un. Une règle visant
    `.vx-chart-size-lg` ne peut donc PAS être prouvée morte — le nom complet
    n'existe nulle part dans les octets, et c'est justement parce qu'il est
    fabriqué à l'exécution."""
    pref = set()
    for c in construites:
        m = re.search(r"""['"]([\w-]*vx-[\w-]*)['"]\s*\+""", c['fragment'])
        if m:
            pref.add(m.group(1))
    return sorted(pref)


def classer(selecteurs, corpus, prefixes=()):
    """`PROUVEE_INATTEIGNABLE` si AUCUNE de ses classes n'est écrite nulle part
    **et** qu'aucune ne dérive d'un préfixe assemblé à l'exécution.

    Le doute profite à la règle : une seule classe présente — ou une seule
    classe dérivable — suffit à la retirer des preuves."""
    texte = '\n'.join(v for k, v in corpus.items())
    presentes = {}
    out = []
    for sel in selecteurs:
        classes = set(_CLASSES.findall(sel))
        if not classes:
            #  Selecteur sans classe (`button`, `[data-x]`, `h1 > span`) : on ne
            #  sait pas prouver, donc on ne prouve pas.
            out.append({'selecteur': sel, 'classe': 'INDECIDABLE',
                        'raison': 'aucune classe dans le selecteur'})
            continue
        vues = []
        for c in sorted(classes):
            if c not in presentes:
                presentes[c] = c in texte
            if presentes[c]:
                vues.append(c)
        if vues:
            out.append({'selecteur': sel, 'classe': 'ATTEIGNABLE',
                        'classes': sorted(classes), 'classes_vues': vues})
            continue
        #  Aucune classe ecrite — mais l'une derive-t-elle d'un prefixe que du
        #  JS assemble ? Si oui, l'absence ne prouve rien.
        derivables = [c for c in sorted(classes)
                      if any(c.startswith(p) and c != p for p in prefixes)]
        if derivables:
            out.append({'selecteur': sel, 'classe': 'INDECIDABLE',
                        'classes': sorted(classes), 'classes_vues': [],
                        'raison': 'derive d\'un prefixe assemble : %s'
                                  % ', '.join(derivables)})
            continue
        out.append({'selecteur': sel, 'classe': 'PROUVEE_INATTEIGNABLE',
                    'classes': sorted(classes), 'classes_vues': []})
    return out


def mesurer(base: str = BASE_DEFAUT, candidates=None) -> dict:
    from tools.mesures import mesurer_couche_visuelle as _couche
    if candidates is None:
        r = _couche.mesurer(base, temoins=False)
        #  TOUTES les candidates, pas l'echantillon d'affichage : une preuve
        #  etablie sur un echantillon n'est pas une preuve.
        candidates = r['toutes_jamais_appariees']
        total_annonce = r['regles_jamais_appariees']
    else:
        total_annonce = sum(len(v) for v in candidates.values())

    corpus = octets_servis(base)
    construites = classes_construites(corpus)
    prefixes = prefixes_construits(construites)
    par_feuille, tous = {}, []
    for feuille, sels in sorted(candidates.items()):
        lignes = classer(sels, corpus, prefixes)
        par_feuille[feuille] = lignes
        tous.extend(lignes)
    #  Un corpus AMPUTE ne prouve rien. Si une seule page n'a pas ete lue, la
    #  classe qui n'y vit que la parait « jamais apparaissante » — et l'outil
    #  proposerait de supprimer du code a cause de sa propre impatience. Toutes
    #  les preuves retombent donc a INDECIDABLE, avec le motif.
    non_lues = list(NON_LUES)
    if non_lues:
        for x in tous:
            if x['classe'] == 'PROUVEE_INATTEIGNABLE':
                x['classe'] = 'INDECIDABLE'
                x['motif'] = ('corpus ampute : %d page(s) non lue(s) — aucune '
                              'preuve possible' % len(non_lues))
    prouvees = [x for x in tous if x['classe'] == 'PROUVEE_INATTEIGNABLE']
    return {
        'base': base,
        'non_lues': non_lues,
        'corpus_complet': not non_lues,
        'octets_servis': {k: len(v) for k, v in corpus.items()},
        'candidates_examinees': len(tous),
        'candidates_annoncees': total_annonce,
        'prouvees_inatteignables': len(prouvees),
        'atteignables': sum(1 for x in tous if x['classe'] == 'ATTEIGNABLE'),
        'indecidables': sum(1 for x in tous if x['classe'] == 'INDECIDABLE'),
        'classes_construites': construites,
        'prefixes_construits': prefixes,
        #  La preuve reste FIABLE meme en presence de prefixes assembles : les
        #  regles concernees sont ecartees vers INDECIDABLE, elles ne polluent
        #  pas les preuves. Ce qui la rendrait non fiable serait de les compter.
        'preuve_fiable': True,
        'detail': par_feuille,
        'exemples_prouvees': [x['selecteur'] for x in prouvees[:25]],
    }


CORPUS_TEMOIN = {
    'page:t': '<div class="vx-existe">x</div>',
    'js:/t.js': "el.classList.add('vx-pose-par-js');",
}


def _temoins() -> list:
    """Le contrôle est présenté à un corpus fabriqué dont on connaît la
    réponse. Sans cela, « 0 prouvée » ne distingue pas un produit sain d'un
    détecteur aveugle."""
    e = []
    r = {x['selecteur']: x['classe'] for x in classer(
        ['.vx-existe', '.vx-pose-par-js', '.vx-nulle-part-xyz',
         '.vx-existe.vx-nulle-part-xyz', 'button'], CORPUS_TEMOIN)}
    if r.get('.vx-nulle-part-xyz') != 'PROUVEE_INATTEIGNABLE':
        e.append('TEMOIN MUET : une classe ecrite NULLE PART n\'est pas '
                 'prouvee inatteignable — l\'outil ne prouvera jamais rien')
    if r.get('.vx-existe') != 'ATTEIGNABLE':
        e.append('TEMOIN NEGATIF ROMPU : une classe presente dans le HTML '
                 'ressort inatteignable — l\'outil autoriserait a supprimer du '
                 'CSS vivant')
    if r.get('.vx-pose-par-js') != 'ATTEIGNABLE':
        e.append('TEMOIN NEGATIF ROMPU (JS) : une classe posee par '
                 '`classList.add` ressort inatteignable — tout le CSS des '
                 'ETATS serait declare mort')
    #  LE temoin qui compte le plus : le doute doit profiter a la regle.
    if r.get('.vx-existe.vx-nulle-part-xyz') != 'ATTEIGNABLE':
        e.append('TEMOIN NEGATIF ROMPU (doute) : un selecteur dont UNE SEULE '
                 'classe existe ressort inatteignable — une regle d\'etat '
                 '(`.vx-carte.est-ouverte`) serait supprimee')
    if r.get('button') != 'INDECIDABLE':
        e.append('TEMOIN MUET : un selecteur sans classe est tranche alors '
                 'qu\'on ne sait pas le prouver')
    if not classes_construites({'js:/t.js': "c='vx-'+genre"}):
        e.append('TEMOIN MUET (construites) : un nom de classe ASSEMBLE n\'est '
                 'pas detecte — la preuve serait donnee comme fiable a tort')
    #  Une classe derivee d'un prefixe assemble ne doit JAMAIS etre prouvee.
    d = {x['selecteur']: x['classe'] for x in classer(
        ['.vx-taille-lg'], {'page:t': ''}, prefixes=['vx-taille-'])}
    if d.get('.vx-taille-lg') != 'INDECIDABLE':
        e.append('TEMOIN MUET (prefixe) : une classe derivee d\'un prefixe '
                 'assemble a l\'execution est prouvee morte — or son nom '
                 'complet n\'existe nulle part PARCE QU\'il est fabrique')

    #  LE TEMOIN QUI MANQUAIT, ET QUI A LAISSE PASSER UNE FAUSSE PREUVE.
    #  Le corpus doit couvrir TOUTES les pages servies, pas les huit espaces.
    #  `.ds-note` vit sur /design-system : avec un corpus reduit a PRIMARY_NAV,
    #  elle ressortait « prouvee inatteignable » — un permis de supprimer du
    #  CSS vivant.
    routes = routes_html()
    hors_espaces = [r for r in routes
                    if r not in ('/', '/markets', '/opportunities', '/analysis',
                                 '/portfolio', '/options', '/journal', '/system')]
    if len(hors_espaces) < 5:
        e.append('TEMOIN MUET (corpus) : la table de routage ne rend que %d '
                 'page(s) hors des huit espaces — le corpus est probablement '
                 'retombe sur PRIMARY_NAV, et une classe servie ailleurs sera '
                 'declaree morte a tort' % len(hors_espaces))
    if '/design-system' not in routes and '/system/design-system' not in routes:
        e.append('TEMOIN MUET (corpus) : /design-system est absent du corpus, '
                 'alors que c\'est la page qui a revele la fausse preuve')
    #  Les FICHES doivent etre dans le corpus : elles rendent un balisage que
    #  les pages d'index n'ont pas, et c'etait le troisieme trou de la preuve.
    if not any(r.startswith('/analysis/') for r in routes):
        e.append('TEMOIN MUET (corpus) : aucune route PARAMETREE instanciee — '
                 'tout le balisage des fiches est hors du corpus, et une '
                 'classe qui n\'y vit que la sera declaree morte a tort')
    return e


def rendre_texte(r: dict) -> str:
    o = ['REGLES CSS — CE QUI EST *PROUVE* INATTEIGNABLE',
         '=' * 66, 'base : %s' % r['base'], '']
    o.append('octets servis examines : %d pages+scripts, %d o'
             % (len(r['octets_servis']), sum(r['octets_servis'].values())))
    non_lues = r.get('non_lues') or []
    if non_lues:
        o.append("CORPUS AMPUTE : %d page(s)/script(s) NON LU(S) — aucune "
                 "preuve n'est possible" % len(non_lues))
        for x in non_lues[:8]:
            o.append('   %s' % x)
        o.append('Toutes les preuves sont retombees a INDECIDABLE. Relancer '
                 'quand le produit repond.')
    o.append('')
    o.append('candidates examinees        : %d (sur %d annoncees)'
             % (r['candidates_examinees'], r['candidates_annoncees']))
    o.append('   PROUVEES inatteignables  : %d' % r['prouvees_inatteignables'])
    o.append('   atteignables             : %d   (une classe existe quelque part)'
             % r['atteignables'])
    o.append('   indecidables             : %d   (selecteur sans classe)'
             % r['indecidables'])
    o.append('')
    if r['prefixes_construits']:
        o.append('PREFIXES ASSEMBLES a l\'execution : %s'
                 % ', '.join(r['prefixes_construits']))
        o.append('   Un nom construit n\'apparait pas en entier dans les octets.')
        o.append('   Les regles qui en derivent sont ecartees vers INDECIDABLE :')
        o.append('   on ne les supprime pas, et elles ne polluent pas les preuves.')
    else:
        o.append('Aucun prefixe de classe assemble dans le JS servi.')
    o.append('')
    if r['exemples_prouvees']:
        o.append('EXEMPLES DE REGLES PROUVEES INATTEIGNABLES :')
        for s in r['exemples_prouvees']:
            o.append('   %s' % s)
    o.append('')
    o.append('RAPPEL : cet outil NE SUPPRIME RIEN. La suppression releve de')
    o.append('CLEANUP_POLICY.md et d\'une decision humaine.')
    return '\n'.join(o)


def main() -> int:
    #  Cet outil derive ses candidates de `mesurer_couche_visuelle`, qui exige
    #  un navigateur. Sans cet aveu, il plantait au milieu d'une trace
    #  Playwright — en ayant deja construit un corpus de 4,4 Mo pour rien.
    if not navigateur_pret():
        return abandonner_sans_navigateur()
    base = BASE_DEFAUT
    if '--base' in sys.argv:
        base = sys.argv[sys.argv.index('--base') + 1]
    echecs = _temoins()
    if echecs:
        for x in echecs:
            print('TEMOIN MUET : %s' % x, file=sys.stderr)
        return 2
    r = mesurer(base)
    print(json.dumps(r, indent=2, ensure_ascii=False) if '--json' in sys.argv
          else rendre_texte(r))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
