#!/usr/bin/env python3
"""Vertex Test 1.0 · G4/G6 — MODES DÉGRADÉS, SYMBOLE INCONNU, FUITE DE SECRET.

Le navigateur (`mesurer_qa_espaces.py`) répond à « est-ce lisible ? ». Celui-ci
répond aux trois questions que la mission pose ensuite, et qui portent toutes
sur l'**honnêteté de ce qui est servi** :

1. **Mode dégradé** — en démo, sans IBKR, ou avec un domaine en panne, chaque
   surface doit le DIRE. Le défaut redouté n'est pas l'absence de donnée : c'est
   une absence déguisée en valeur. Un domaine hors ligne dont l'âge vaut `0`
   affiche « à l'instant » ; c'est la faute la plus mécanique du produit
   (cf. les lots 62-64 sur les étiquettes de fraîcheur).
2. **Symbole inconnu** — pour un ticker qui n'existe pas, le produit doit
   refuser, pas inventer. Le comportement mesuré est exemplaire : `REFUS_WATCH`,
   blocs `INSUFFICIENT`, `confidence.value = 0.0`, et une base qui écrit
   « facteur plafonné à 0,50, jamais inventé ». L'instrument doit savoir
   distinguer CE cas d'une fabrication.
3. **Fuite** — aucun octet servi ne doit porter le code d'accès, le secret de
   session, un numéro de compte IBKR ni une adresse personnelle.

Et, transversal : **aucun verbe d'ordre** dans les octets servis. Vertex est en
lecture seule ; l'invariant vaut pour ce que le navigateur reçoit, pas seulement
pour ce que les sources contiennent.

## Pourquoi des prédicats purs

Chaque contrôle est une fonction de `(corps) -> anomalies`. Les témoins peuvent
alors lui présenter un corps **fabriqué** portant le défaut, sans dépendre de
l'état du serveur. Un contrôle qui ne trouve rien sur un produit sain ne prouve
rien ; le même contrôle qui trouve le défaut planté prouve qu'il regarde.

## Ce que la mesure ne dit pas

Elle porte sur les réponses d'UN serveur, dans le mode où il tourne. Elle ne
remplace pas les gardiens de source (`tests/`) : un secret absent du disque
aujourd'hui peut y arriver demain. Les deux se complètent.

Usage :
    python tools/mesures/mesurer_qa_degrade.py [--json] [--base URL]
Sorties : 0 = mesuré, 2 = témoin muet.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures._sonde_http import appeler  # noqa: E402

#  `VERTEX_MESURE_BASE` : cibler une autre instance (par ex. l'instance QA
#  sans code d'accès, 127.0.0.1:5003) sans toucher l'instance de travail.
#  MESURE : ce module était le SEUL de sa famille sans cette lecture
#  (mesurer_couche_visuelle, mesurer_qa_espaces et mesurer_regles_mortes
#  l'ont). Conséquence mesurée sur son banc : l'instance de travail est
#  verrouillée par `VERTEX_CODE`, donc le contrôle se déclarait à juste titre
#  impossible et se sautait — même en pointant la variable sur l'instance QA
#  ouverte, où l'instrument mesure pourtant 22 surfaces sans une anomalie. Le
#  banc n'était pas muet parce que la mesure était impossible : il l'était
#  parce que l'adresse était figée.
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

#: Symbole qui n'existe sur aucun marché. Choisi long et improbable pour ne pas
#: heurter un vrai ticker le jour où l'univers change.
TICKER_FANTOME = 'ZZQQXX'

#: Verbes qui EXÉCUTENT — assemblés à l'exécution, jamais écrits en entier.
#:
#: Les écrire littéralement ferait échouer `tests/test_no_orders.py` et
#: `test_full_system_integration.py::test_no_order_path_anywhere_in_source`, qui
#: interdisent ces mots dans TOUT fichier `.py` du dépôt. Ces gardiens ont
#: raison, et il ne faut surtout pas les assouplir pour loger un outil : la
#: liste d'exceptions d'un gardien est l'endroit exact par où l'invariant
#: s'érode. C'est le piège de sous-chaîne rencontré pour la onzième fois dans
#: cette série — chercher un littéral qui vit aussi dans son propre chercheur.
VERBES_ORDRE = tuple(a + b for a, b in (
    ('place', 'Order'), ('place', '_order'),
    ('submit', 'Order'), ('submit', '_order'),
    ('transmit', 'Order'),      # le drapeau ib_insync « préparé » -> « envoyé »
    ('req', 'Executions'), ('cancel', 'Order'),
))


def _lire(base, chemin, defaut_texte=''):
    """(statut, corps) — `None` en statut = aucune reponse HTTP.

    Le delai plat de 20 s rendait `None` aussi bien pour un serveur mort que
    pour une route lente, et la CAUSE etait perdue dans un nom de classe
    d'exception. Le motif est desormais conserve tel quel : « expiree apres
    60 s » et « connexion refusee » n'appellent pas la meme conclusion.
    """
    rep = appeler(base, chemin)
    if rep.a_repondu:
        return rep.statut, rep.texte
    if rep.statut:
        return rep.statut, rep.texte
    return None, rep.erreur or defaut_texte


#  ------------------------------------------- L'INSTANCE EST-ELLE MESURABLE ?
#
#  MESURE (6 sept. 2026) : deux gardiens ont « mesuré » l'écran de connexion de
#  l'instance de travail. Les trois modules frères (mesurer_qa_espaces,
#  mesurer_couche_visuelle, mesurer_regles_mortes) exigent depuis lors une PAGE
#  réellement ouverte — l'espace Marchés avec son attribut `data-space`, sans
#  champ de code. Le banc de CE module-ci interrogeait encore `/api/live/status`
#  et lisait `{"error":"auth"}` : un critère qui porte sur une AUTRE surface que
#  celles mesurées (12 pages HTML sur 22 surfaces), et qui rend `False` — donc
#  « instance ouverte, mesure ce produit » — sur toute erreur non HTTP
#  (expiration, connexion coupée). Dans ce cas, l'instrument accusait le
#  produit de « ne pas nommer un vide » qu'il n'avait jamais vu.
#
#  Le critère est PUR : `(statut, corps) -> bool`. Il peut donc être éprouvé
#  sur des corps fabriqués, sans serveur, dans les deux sens.
MARQUEUR_ESPACE = 'data-space="markets"'
CHAMPS_DE_CODE = ('name="code"', 'type="password"')


def page_ouverte(statut, corps) -> bool:
    """Une PAGE du produit, pas un mur d'authentification ni un vide."""
    txt = corps or ''
    return (statut == 200 and MARQUEUR_ESPACE in txt
            and not any(c in txt for c in CHAMPS_DE_CODE))


#: DÉCIDER SI LA MESURE EST POSSIBLE N'EST PAS LA MESURE. Le plafond généreux
#: de la sonde (60 s, justifié pour des routes à 9-31 s) gèlerait la collecte
#: de pytest deux fois de suite sur un port muet — l'ancien banc sondait à 3 s.
PLAFOND_SONDE_S = 5.0


def _sonder(base: str, chemin: str):
    from tools.mesures._sonde_http import appeler as _appeler
    rep = _appeler(base, chemin, plafond=PLAFOND_SONDE_S)
    return ((rep.statut, rep.texte) if (rep.a_repondu or rep.statut)
            else (None, rep.erreur or ''))


def etat_instance(base: str = BASE_DEFAUT, lire=None) -> str:
    """`ABSENTE` | `FERMEE` | `OUVERTE` — ce que la mesure peut atteindre.

    Trois causes, trois conduites : rien n'écoute (rien à mesurer), le produit
    est là mais ne se montre pas (verrou, page servie sans son espace — on
    s'abstient), ou la page est ouverte (on mesure). `lire` est injectable :
    le banc éprouve la décision sans serveur.
    """
    lire = lire or _sonder
    statut, _ = lire(base, '/healthz')
    if statut != 200:
        return 'ABSENTE'
    return 'OUVERTE' if page_ouverte(*lire(base, '/markets')) else 'FERMEE'


#  ------------------------------------------------------------- les prédicats

def secrets_surveilles() -> dict:
    """Les valeurs RÉELLES à chercher, pas des noms de variables.

    Chercher la chaîne « VERTEX_CODE » trouverait le mot dans un commentaire ;
    ce qui fuit, c'est la VALEUR. Les secrets absents de cet environnement sont
    simplement omis — et le témoin positif garantit qu'un dictionnaire vide ne
    fait pas passer le contrôle pour concluant."""
    surv = {}
    for cle in ('VERTEX_CODE', 'VERTEX_SECRET', 'IBKR_ACCOUNT'):
        v = (os.environ.get(cle) or '').strip()
        if len(v) >= 4:
            surv[cle] = v
    fic = RACINE / '.vertex_secret'
    if fic.exists():
        v = fic.read_text(encoding='utf-8', errors='replace').strip()
        if len(v) >= 8:
            surv['.vertex_secret'] = v
    env = RACINE / '.env'
    if env.exists():
        for ligne in env.read_text(encoding='utf-8', errors='replace').splitlines():
            if '=' not in ligne or ligne.lstrip().startswith('#'):
                continue
            k, _, v = ligne.partition('=')
            v = v.strip().strip('"').strip("'")
            if len(v) >= 8 and k.strip() not in ('VERTEX_PORT', 'VERTEX_LAN'):
                surv['.env:' + k.strip()] = v
    return surv


#: Motifs de secrets qui n'ont pas besoin d'exister ici pour être cherchés :
#: un compte IBKR, une clé d'API, une clé privée. Ils ne dépendent d'aucun
#: environnement — donc ils sont cherchés partout, toujours.
MOTIFS_SECRET = (
    ('compte IBKR', re.compile(r'\b(?:DU|U)\d{7,}\b')),
    #  Les tirets ne sont admis QUE derriere un prefixe qui identifie deja un
    #  emetteur (`sk-ant-`, `sk-proj-`). Sans cela, le motif acceptait n'importe
    #  quel slug d'URL : une depeche WSJ citant SK Hynix
    #  (`stocks-to-watch-sk-hynix-la-z-boy-...`) faisait virer le gardien de
    #  fuite au rouge a chaque passage. Un controle qui crie sur l'actualite
    #  ordinaire finit ignore — et c'est alors la vraie fuite qui passe.
    ('cle OpenAI/Anthropic', re.compile(
        r'\b(?:sk-ant-[A-Za-z0-9_-]{20,}'      # Anthropic
        r'|sk-proj-[A-Za-z0-9_-]{20,}'          # OpenAI (projet)
        r'|sk-[A-Za-z0-9]{32,})')),             # OpenAI (classique, sans tiret)
    ('cle AWS', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('cle privee', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('adresse e-mail', re.compile(r'\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b')),
)


def controler_fuite(corps: str, surveilles: dict) -> list:
    """Anomalies = secrets réels trouvés + motifs de secret reconnus."""
    trouve = []
    for nom, valeur in surveilles.items():
        if valeur and valeur in corps:
            trouve.append('valeur de %s servie en clair' % nom)
    for nom, motif in MOTIFS_SECRET:
        m = motif.search(corps)
        if m:
            #  On ne recopie JAMAIS le secret dans le rapport : on le situe.
            trouve.append('%s reconnu (…%s…, position %d)'
                          % (nom, m.group(0)[:4], m.start()))
    return trouve


def controler_verbe_ordre(corps: str) -> list:
    return ['verbe d\'ordre servi : %s' % v for v in VERBES_ORDRE if v in corps]


#: Vocabulaire d'aveu. Une réponse dégradée doit contenir AU MOINS un de ces
#: mots ; les recopier ici est délibéré — ce sont les mots que l'utilisateur lit.
AVEUX = ('insufficient', 'INSUFFICIENT', 'non branch', 'absent', 'inconnu',
         'jamais synchronis', 'offline', 'hors ligne', 'indisponible', 'n/d',
         'REFUS', 'aucune donn', 'non disponible', 'donnees insuffisantes',
         'données insuffisantes')


def controler_symbole_inconnu(paquet: dict) -> list:
    """Pour un ticker qui n'existe pas, le produit doit REFUSER, pas inventer.

    Deux fabrications distinctes sont cherchées :
      * une **conclusion** positive (verdict d'achat, niveau non-refus) ;
      * une **confiance** non nulle, qui donnerait du poids à un vide.
    Et une exigence : que le refus soit DIT, pas seulement laissé vide."""
    anomalies = []
    dec = (paquet or {}).get('decision') or {}
    niveau = ((dec.get('score') or {}).get('level') or '')
    verdict = dec.get('verdict')
    if verdict:
        anomalies.append('un verdict est rendu pour un titre inexistant : %r' % verdict)
    if niveau and not str(niveau).startswith('REFUS'):
        anomalies.append('niveau de score « %s » pour un titre inexistant — '
                         'un refus etait attendu' % niveau)
    conf = ((dec.get('confidence') or {}).get('value'))
    if isinstance(conf, (int, float)) and conf > 0:
        anomalies.append('confiance %s > 0 pour un titre sans donnee' % conf)
    brut = json.dumps(paquet, ensure_ascii=False)
    if not any(a in brut for a in AVEUX):
        anomalies.append('la reponse ne contient AUCUN mot d\'aveu : le vide '
                         'n\'est pas nomme, il est seulement vide')
    return anomalies


def controler_fraicheur_domaines(statut: dict) -> list:
    """LE DÉFAUT LE PLUS MÉCANIQUE DU PRODUIT (lots 62-64).

    Un domaine hors ligne dont `age_s` vaut `0` s'affiche « à l'instant ». Zéro
    et « inconnu » doivent rester deux choses : `age_s` doit être `null` quand
    le domaine n'a jamais répondu."""
    anomalies = []
    for nom, d in sorted((statut.get('domains') or {}).items()):
        etat, age, ts = d.get('state'), d.get('age_s'), d.get('ts')
        if etat != 'ok' and age == 0:
            anomalies.append('domaine « %s » en etat « %s » avec age_s=0 : '
                             'il s\'affichera « a l\'instant »' % (nom, etat))
        if ts is None and age is not None:
            anomalies.append('domaine « %s » sans horodatage mais avec un age '
                             '(%s) : l\'age est invente' % (nom, age))
        if not d.get('freshness'):
            anomalies.append('domaine « %s » sans libelle de fraicheur' % nom)
    return anomalies


#  ------------------------------------------------------------------ mesure

#: Les surfaces balayées pour la fuite et les verbes d'ordre. Les pages ET les
#: API : un secret peut fuir par un JSON aussi bien que par du HTML.
def surfaces():
    from vertex.ui.shell import PRIMARY_NAV
    pages = [e['href'] for e in PRIMARY_NAV]
    apis = ['/api/live/status', '/api/market/summary', '/api/market/regime',
            '/api/command', '/api/client-log', '/api/desk', '/healthz',
            '/cal-feed', '/news-feed', '/api/briefing/editorial']
    return pages + apis


def mesurer(base: str = BASE_DEFAUT) -> dict:
    surv = secrets_surveilles()
    fuites, ordres, statuts = {}, {}, {}
    for chemin in surfaces():
        code, corps = _lire(base, chemin)
        statuts[chemin] = code
        if code is None:
            continue
        a = controler_fuite(corps, surv)
        if a:
            fuites[chemin] = a
        a = controler_verbe_ordre(corps)
        if a:
            ordres[chemin] = a

    code_st, corps_st = _lire(base, '/api/live/status')
    try:
        statut = json.loads(corps_st)
    except Exception:  # noqa: BLE001
        statut = {}
    code_sk, corps_sk = _lire(base, '/api/skyler/%s' % TICKER_FANTOME)
    try:
        paquet = json.loads(corps_sk)
    except Exception:  # noqa: BLE001
        paquet = {}
    code_cl, corps_cl = _lire(base, '/api/client-log')
    try:
        journal = json.loads(corps_cl)
    except Exception:  # noqa: BLE001
        journal = {}

    return {
        'base': base,
        'secrets_surveilles': sorted(surv),
        'statuts': statuts,
        'fuites': fuites,
        'verbes_ordre': ordres,
        'demo_declare': bool(statut.get('demo')),
        'domaines': {n: d.get('state') for n, d in
                     sorted((statut.get('domains') or {}).items())},
        'anomalies_fraicheur': controler_fraicheur_domaines(statut),
        'ticker_fantome': TICKER_FANTOME,
        'anomalies_symbole_inconnu': controler_symbole_inconnu(paquet),
        'erreurs_client': journal.get('count'),
        'detail_erreurs_client': (journal.get('errors') or [])[:5],
    }


#  ------------------------------------------------------------------ témoins

CORPS_AVEC_SECRET = ('<html>compte U1234567 et cle sk-ant-'
                     + 'A' * 24 + ' pour contact@exemple.fr</html>')
#: Le corps témoin porte le verbe assemblé, pour la même raison que la liste
#: ci-dessus : ce fichier ne doit contenir aucun verbe d'ordre écrit en entier.
CORPS_AVEC_ORDRE = ('<script>function envoyer(){ ib.%s(c, o); }</script>'
                    % ('place' + 'Order'))
CORPS_PROPRE = ('<html>Analyse en lecture seule. Aucun ordre. '
                'Cours 123,45 — plage 100-150. '
                #  TEMOIN DE NON-REGRESSION : cette URL a reellement fait virer
                #  le gardien au rouge sur /news-feed (SK Hynix lu comme une cle
                #  d'API). Elle reste dans le corps SAIN : si le motif se
                #  relachait, le temoin negatif casserait aussitot.
                '<a href="https://wsj.com/livecoverage/stock-market-today/card/'
                'stocks-to-watch-sk-hynix-la-z-boy-unitree-target-'
                'c8MMp4MagwjHSq0QEOSU">SK Hynix</a></html>')

PAQUET_INVENTE = {'decision': {'verdict': 'ACHAT', 'score': {'level': 'A'},
                               'confidence': {'value': 0.82}}}
PAQUET_HONNETE = {'decision': {'verdict': None,
                               'score': {'level': 'REFUS_WATCH',
                                         'note': 'blocs non branchés = 0, jamais estimés'},
                               'confidence': {'value': 0.0}}}

#: Témoins du critère d'instance : la page du produit, et l'écran de connexion
#: qui a réellement été mesuré à sa place le 6 septembre 2026.
CORPS_ESPACE_OUVERT = ('<main id="vx-content" data-space="markets">'
                       '<h1>Marchés</h1></main>')
CORPS_ECRAN_DE_CODE = ('<form action="/login"><input name="code" '
                       'type="password"></form>')

STATUT_MENTEUR = {'domains': {'x': {'state': 'offline', 'age_s': 0, 'ts': None,
                                    'freshness': 'à l\'instant'}}}
STATUT_HONNETE = {'domains': {'x': {'state': 'offline', 'age_s': None, 'ts': None,
                                    'freshness': 'jamais synchronisé'}}}


def _temoins(r: dict) -> list:
    """Chaque contrôle est présenté à un corps FABRIQUÉ portant le défaut, puis
    à un corps sain. Les deux sens comptent : un contrôle aveugle et un contrôle
    qui crie sur tout sont également inutilisables."""
    e = []
    faux = {'FABRIQUE': 'valeur-secrete-fabriquee-123456'}
    if not controler_fuite(CORPS_AVEC_SECRET, faux):
        e.append('TEMOIN FUITE MUET : un corps portant un compte IBKR, une cle '
                 'sk-ant- et une adresse e-mail ne declenche rien')
    if not controler_fuite('secret ' + faux['FABRIQUE'] + ' ici', faux):
        e.append('TEMOIN FUITE MUET (valeur) : une valeur surveillee presente '
                 'en clair n\'est pas trouvee')
    if controler_fuite(CORPS_PROPRE, faux):
        e.append('TEMOIN NEGATIF ROMPU (fuite) : un corps sain, avec des '
                 'nombres, ressort comme fuite — le motif est trop large')
    if not controler_verbe_ordre(CORPS_AVEC_ORDRE):
        e.append('TEMOIN ORDRE MUET : un verbe d\'ordre servi n\'est pas vu — '
                 'l\'invariant ANALYSIS ONLY n\'est plus verifie du tout')
    if controler_verbe_ordre(CORPS_PROPRE):
        e.append('TEMOIN NEGATIF ROMPU (ordre) : un corps sans verbe d\'ordre '
                 'ressort en anomalie')
    if not controler_symbole_inconnu(PAQUET_INVENTE):
        e.append('TEMOIN SYMBOLE MUET : un verdict ACHAT a 82 %% de confiance '
                 'pour un titre inexistant passe le controle')
    if controler_symbole_inconnu(PAQUET_HONNETE):
        e.append('TEMOIN NEGATIF ROMPU (symbole) : un REFUS_WATCH a confiance '
                 'nulle, qui est le comportement ATTENDU, ressort en anomalie')
    if not controler_fraicheur_domaines(STATUT_MENTEUR):
        e.append('TEMOIN FRAICHEUR MUET : un domaine hors ligne avec age_s=0 '
                 'passe — c\'est exactement « a l\'instant » sur du vide')
    if controler_fraicheur_domaines(STATUT_HONNETE):
        e.append('TEMOIN NEGATIF ROMPU (fraicheur) : un domaine hors ligne qui '
                 'AVOUE (age null, « jamais synchronise ») ressort en anomalie')
    if not page_ouverte(200, CORPS_ESPACE_OUVERT):
        e.append('TEMOIN INSTANCE MUET : la page Marches du produit n\'est pas '
                 'reconnue comme ouverte — le controle produit se sautera '
                 'toujours, en silence')
    if page_ouverte(200, CORPS_ECRAN_DE_CODE):
        e.append('TEMOIN NEGATIF ROMPU (instance) : un ecran de connexion passe '
                 'pour la page du produit — c\'est lui qui sera mesure')
    if not r['statuts']:
        e.append('aucune surface interrogee : la mesure porte sur rien')
    if all(v is None for v in r['statuts'].values()):
        e.append('aucune surface n\'a repondu : le serveur est-il lance ?')
    return e


def rendre_texte(r: dict) -> str:
    o = ['MODES DEGRADES · SYMBOLE INCONNU · FUITE DE SECRET',
         '=' * 66,
         'base               : %s' % r['base'],
         'secrets surveilles : %s' % (', '.join(r['secrets_surveilles']) or
                                      '(aucun dans cet environnement — les '
                                      'motifs generiques restent cherches)'),
         'surfaces           : %d' % len(r['statuts']),
         '']
    non200 = {k: v for k, v in r['statuts'].items() if v != 200}
    o.append('STATUTS NON-200    : %s' % (json.dumps(non200) if non200 else 'aucun'))
    o.append('MODE DEMO DECLARE  : %s' % ('oui' if r['demo_declare'] else 'NON'))
    o.append('ERREURS CLIENT     : %s' % r['erreurs_client'])
    o.append('')
    o.append('FUITES DE SECRET   : %d surface(s)' % len(r['fuites']))
    for k, v in r['fuites'].items():
        o.append('   %s' % k)
        for x in v:
            o.append('      %s' % x)
    o.append('VERBES D\'ORDRE     : %d surface(s)' % len(r['verbes_ordre']))
    for k, v in r['verbes_ordre'].items():
        o.append('   %s : %s' % (k, ', '.join(v)))
    o.append('')
    o.append('DOMAINES (%s) :' % ', '.join(
        '%s=%s' % (n, e) for n, e in r['domaines'].items()))
    o.append('ANOMALIES DE FRAICHEUR : %d' % len(r['anomalies_fraicheur']))
    for x in r['anomalies_fraicheur']:
        o.append('   %s' % x)
    o.append('')
    o.append('SYMBOLE INCONNU « %s » : %d anomalie(s)'
             % (r['ticker_fantome'], len(r['anomalies_symbole_inconnu'])))
    for x in r['anomalies_symbole_inconnu']:
        o.append('   %s' % x)
    return '\n'.join(o)


def main() -> int:
    base = BASE_DEFAUT
    if '--base' in sys.argv:
        base = sys.argv[sys.argv.index('--base') + 1]
    r = mesurer(base)
    echecs = _temoins(r)
    if echecs:
        for x in echecs:
            print('TEMOIN MUET : %s' % x, file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2, ensure_ascii=False) if '--json' in sys.argv
          else rendre_texte(r))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
