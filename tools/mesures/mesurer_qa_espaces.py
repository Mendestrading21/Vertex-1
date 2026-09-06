#!/usr/bin/env python3
"""Vertex Test 1.0 · G4 — LES HUIT ESPACES, MESURÉS DANS UN VRAI NAVIGATEUR.

La mission demande que « les huit espaces soient validés desktop / mobile /
clavier / contraste ». Les quatre mots désignent quatre défauts très
différents, et **aucun des quatre ne se voit dans une réponse HTTP** :

| mot | ce qui casse | pourquoi `curl` ne le voit pas |
| --- | --- | --- |
| desktop / mobile | débordement horizontal | la largeur naît de la mise en page, pas du HTML |
| clavier | élément inatteignable ou sans anneau de focus | `:focus-visible` est un état, pas un attribut |
| contraste | texte gris sur fond gris | il faut le **fond effectif**, hérité d'un ancêtre |
| — | erreur JS | elle se produit après le rendu du document |

D'où un navigateur réel. Trois largeurs : **390** (iPhone), **768** (tablette,
la charnière où les grilles retombent), **1440** (bureau).

## Ce que chaque mesure établit, et sa limite

**Débordement.** Deux niveaux : le document défile-t-il latéralement, et un
conteneur **coupe-t-il** son contenu (`overflow-x:hidden|clip` avec un contenu
plus large) ? Les conteneurs qui défilent **exprès** (`auto|scroll`) sont exclus
— c'est le remède, pas le défaut.

*La première version comparait chaque élément à `window.innerWidth`, et
signalait 136 « débordements » sur un produit qui n'en avait aucun* : les
panneaux hors-écran garés par `transform: translateX(…)` — sidebar mobile,
drawer fermé, `aria-hidden` et `inert` — sont précisément le bon motif. Un
élément situé hors du cadre n'est un défaut que si l'on peut défiler jusqu'à
lui ou si son contenu est coupé ; sinon il est *rangé*, pas *débordant*.

**Clavier.** Pour chaque élément interactif visible : peut-il recevoir le focus,
et **cela se voit-il** ? Le second point est celui qu'on oublie : `el.focus()`
réussit toujours sur un `<button>`, y compris sous un `outline:none` qui rend le
parcours clavier invisible. On compare donc le style calculé avant / après focus
et on exige qu'*au moins une* propriété visible change (outline, box-shadow,
bordure, fond).

**Contraste.** Le fond effectif est cherché en **remontant les ancêtres** jusqu'au
premier fond opaque — couleur unie **ou dégradé**. Seuils WCAG AA : 4,5:1, ou
3:1 pour le grand texte (≥ 24 px, ou ≥ 18,66 px en gras).

*Ici aussi la première version accusait à tort* : elle ne lisait que
`backgroundColor`, à zéro sur un bouton peint par `linear-gradient`. La remontée
sautait donc le fond réellement peint pour atterrir sur la page sombre, et
l'encre du bouton primaire — à ~7:1 sur son dégradé — ressortait à 1,04:1. 34
faux positifs, tous sur le bouton le plus visible du produit.

**Ce que la mesure ne dit pas.** Elle voit l'état **au chargement** : un défaut
qui n'apparaît qu'après une interaction (menu ouvert, drawer déployé) lui
échappe. Elle ne compose pas les voiles translucides (le « verre » à 4 % de
blanc) : elle continue de remonter, ce qui la rend très légèrement optimiste
sur ces surfaces. Elle ne juge pas l'esthétique — elle mesure des seuils.

## Les témoins

Un détecteur qui ne trouve rien ne prouve rien. Chaque famille de mesure est
éprouvée sur des pages **fabriquées**, et — leçon de la campagne de mutation —
**via `_sonder`**, la fonction qu'emploie le balayage lui-même : tant que les
témoins posaient leur propre écouteur d'erreurs, on pouvait supprimer celui du
balayage sans qu'un seul témoin bronche.

Ce que chaque témoin épingle :

| témoin | épingle |
| --- | --- |
| enfant de 3 000 px | le document qui défile |
| 3 000 px dans un `overflow-x:hidden` | le contenu **coupé** |
| conteneur `overflow-x:auto` (négatif) | qu'on ne confond pas le remède avec le défaut |
| `<button>` sous `outline:none` | l'anneau de focus absent |
| `#888` sur `#777` (1,3:1) | la remontée du fond hérité |
| `#636363` sur `#000` (**3,50:1**) | le **seuil** de 4,5 — un défaut discret, pas criant |
| le même gris en 26 px (négatif) | le seuil distinct du grand texte (3,0) |
| dégradé clair→sombre | qu'on retient le **pire** point de la rampe |
| dégradé du bouton primaire (négatif) | qu'on ne saute pas le fond peint |
| document sans aucun fond | le repli de la remontée (blanc, pas noir) |
| un `throw` au chargement | le compteur d'erreurs |

Les témoins négatifs comptent autant que les positifs : un détecteur qui crie
sur tout passerait pour vigilant, et c'est exactement ce que les deux premières
versions faisaient.

Usage :
    python tools/mesures/mesurer_qa_espaces.py [--json] [--base URL]
                                                  [--largeurs 390,1440]
Sorties : 0 = mesuré, 2 = témoin muet, 3 = NON MESURÉ (navigateur indisponible).
"""
from __future__ import annotations

import functools
import glob
import os
import json
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

#  `VERTEX_MESURE_BASE` : cibler une autre instance (par ex. l'instance QA
#  sans code d'accès, 127.0.0.1:5003) sans toucher l'instance de travail.
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
LARGEURS = (390, 768, 1440)

#: Registre lu depuis le produit — recopier la liste ici la ferait diverger le
#: jour où un espace est renommé, et la mesure porterait alors sur des URL que
#: le produit ne sert plus.
def espaces():
    from vertex.ui.shell import PRIMARY_NAV
    return [(e['id'], e['href']) for e in PRIMARY_NAV]


#: Emplacements ou Playwright pose ses navigateurs, par plateforme. Le premier
#: motif est la convention de CONTENEUR ; les suivants sont le cache standard.
_MOTIFS_CHROMIUM = (
    '/opt/pw-browsers/chromium-*/chrome-linux/chrome',
    '/opt/pw-browsers/chromium/chrome-linux/chrome',
    '~/.cache/ms-playwright/chromium-*/chrome-linux/chrome',                 # Linux
    '~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/'
    'Chromium.app/Contents/MacOS/Chromium',                                  # macOS
    #  Windows : le SHELL headless d'abord — mesure du 2026-09-06 sur cette
    #  machine : `chrome.exe` complet refuse de s'engendrer (« spawn UNKNOWN »)
    #  alors que `chrome-headless-shell.exe` demarre ; c'est aussi ce que
    #  Playwright choisit seul en headless.
    '~/AppData/Local/ms-playwright/chromium_headless_shell-*/'
    'chrome-headless-shell-win*/chrome-headless-shell.exe',                  # Windows (shell)
    '~/AppData/Local/ms-playwright/chromium-*/chrome-win*/chrome.exe',       # Windows
)


def _chromium():
    """Le chemin du Chromium de Playwright — sur CETTE machine, pas sur une seule.

    Elle ne connaissait que `/opt/pw-browsers/...`, une convention de conteneur.
    Partout ailleurs — Windows, macOS, ou un Linux utilisant le cache standard —
    elle rendait None, et comme les gardiens G4 s'abstiennent sur
    `bool(_chromium())`, la mesure navigateur des huit espaces ne s'executait
    NULLE PART : ni en local, ni en CI (ci.yml n'installe pas playwright). Les
    « 0 defaut » de ces lots ont donc ete etablis a la main, jamais par la suite.

    `PLAYWRIGHT_BROWSERS_PATH` est honore en premier : c'est la variable par
    laquelle Playwright lui-meme se laisse deplacer, et l'ignorer ferait mentir
    la sonde sur une machine correctement configuree.

    Rendre None reste licite : `launch(executable_path=None)` laisse Playwright
    resoudre seul. Le None sert alors d'aveu au gardien — « je n'ai pas pu
    mesurer » — et non de verdict sur le produit.
    """
    racine = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    motifs = list(_MOTIFS_CHROMIUM)
    if racine:
        motifs[:0] = [os.path.join(racine, m) for m in
                      ('chromium-*/chrome-linux/chrome',
                       'chromium-*/chrome-win*/chrome.exe',
                       'chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium')]
    for motif in motifs:
        trouve = sorted(glob.glob(os.path.expanduser(motif)))
        if trouve:
            return trouve[-1]
    return None


#: Code de sortie « je n'ai PAS mesure ». Distinct de 0 (mesure propre), de 2
#: (temoin muet) et de 1 (plantage). La meme convention que
#: `mesurer_g5_live` pour TWS injoignable : ne pas avoir mesure n'est pas un
#: resultat, et surtout pas un resultat PROPRE.
SORTIE_SANS_NAVIGATEUR = 3

#: Les trois raisons, parce qu'elles n'appellent pas la meme action.
MODULE_ABSENT = 'MODULE_ABSENT'
BINAIRE_ABSENT = 'BINAIRE_ABSENT'
LANCEMENT_REFUSE = 'LANCEMENT_REFUSE'

REMEDES = {
    MODULE_ABSENT: 'pip install playwright',
    BINAIRE_ABSENT: 'python -m playwright install chromium',
    LANCEMENT_REFUSE: ("environnement : session sans interface, bac a sable ou "
                       "droits — la mesure navigateur ne peut pas s'executer ici"),
}


@functools.lru_cache(maxsize=1)
def diagnostic_navigateur() -> dict:
    """Le navigateur peut-il etre lance ici, et SINON pourquoi ? (une tentative)

    `navigateur_pret()` rendait un booleen. C'etait deja mieux que de tester la
    presence d'un fichier, mais le booleen avale le MOTIF — et les trois motifs
    n'appellent pas du tout la meme action :

    | motif | ce qu'il faut faire |
    |---|---|
    | `MODULE_ABSENT` | installer playwright |
    | `BINAIRE_ABSENT` | telecharger le navigateur |
    | `LANCEMENT_REFUSE` | changer d'environnement — rien a installer |

    Repondre « non » aux trois envoie l'operateur reinstaller un binaire qui
    est deja la. C'est la meme faute que celle de la sonde HTTP (D-053) :
    l'instrument sait pourquoi il a echoue, et ne le dit pas.

    Rend `{'pret', 'raison', 'detail', 'chemin', 'remede'}`.
    """
    chemin = _chromium()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        return {'pret': False, 'raison': MODULE_ABSENT, 'detail': str(e)[:160],
                'chemin': chemin, 'remede': REMEDES[MODULE_ABSENT]}
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch(executable_path=chemin,
                                    args=['--no-sandbox'])
            nav.close()
        return {'pret': True, 'raison': None, 'detail': None,
                'chemin': chemin, 'remede': None}
    except Exception as e:  # noqa: BLE001
        #  Un binaire introuvable et un binaire qui refuse de demarrer sont
        #  deux mondes : le premier s'installe, le second ne s'installe pas.
        raison = BINAIRE_ABSENT if chemin is None else LANCEMENT_REFUSE
        return {'pret': False, 'raison': raison,
                'detail': str(e).strip().splitlines()[0][:200] if str(e) else '',
                'chemin': chemin, 'remede': REMEDES[raison]}


def navigateur_pret() -> bool:
    """Le navigateur peut-il VRAIMENT etre lance ici ? (une seule tentative)

    Les gardiens G4 s'abstenaient sur `bool(_chromium())`, c'est-a-dire sur la
    PRESENCE d'un fichier. Deux machines echouent alors de deux facons opposees :

    - la ou le chemin n'etait pas connu, la mesure s'abstenait en silence — et
      les huit espaces n'ont jamais ete balayes par la suite ;
    - la ou le binaire existe mais ne peut pas etre engendre (session sans
      interface, bac a sable, droits), la mesure PLANTAIT au milieu du test, ce
      qui se lit « le produit est casse » alors que cela veut dire « je n'ai
      pas pu mesurer ».

    On tente donc un lancement, une fois, et on repond sur ce qui s'est passe.
    C'est la seule reponse qui distingue « pas mesure » de « mesure fausse ».

    Le contrat BOOLEEN est conserve : trois bancs de test s'abstiennent
    dessus. Le motif se lit avec `diagnostic_navigateur()`.
    """
    return bool(diagnostic_navigateur()['pret'])


def abandonner_sans_navigateur(flux=None) -> int:
    """L'aveu qu'un outil doit rendre quand il n'a PAS pu mesurer.

    Mesure du 24 aout 2026 : les trois outils navigateur sortaient en code 1
    avec 26 lignes de trace Playwright et ZERO ligne utile. Une trace brute se
    lit « le produit a plante » — c'est-a-dire l'inverse de la verite, qui est
    « l'instrument n'a pas pu demarrer ». Et le code 1 se confond avec un vrai
    plantage, alors que leur contrat annonce « 0 = mesure, 2 = temoin muet ».
    """
    import sys as _sys
    d = diagnostic_navigateur()
    flux = flux if flux is not None else _sys.stderr
    print('NON MESURE — navigateur indisponible (%s). %s'
          % (d['raison'], d['remede']), file=flux)
    if d['detail']:
        print('   motif : %s' % d['detail'], file=flux)
    print("   Ce code (%d) ne dit RIEN du produit : aucune mesure n'a eu "
          "lieu." % SORTIE_SANS_NAVIGATEUR, file=flux)
    return SORTIE_SANS_NAVIGATEUR


#  ---------------------------------------------------------------- sondes JS
#  Chaque sonde est un fragment autonome : elle est aussi appliquée aux pages
#  temoins, donc elle ne peut rien supposer du produit.

SONDE_DEBORDEMENT = r"""
() => {
  const doc = document.documentElement;
  const out = {document: null, elements: []};
  //  (1) Le document defile-t-il lateralement ? C'est LE defaut visible.
  if (doc.scrollWidth > doc.clientWidth + 1) {
    out.document = {scroll: doc.scrollWidth, client: doc.clientWidth};
  }
  //  (2) Un conteneur COUPE-t-il son contenu ? `overflow-x:hidden|clip` avec
  //  un contenu plus large = du texte inatteignable, sans barre pour y aller.
  //  `auto|scroll` est le REMEDE (l'utilisateur peut defiler), pas le defaut.
  const vus = new Set();
  for (const el of document.querySelectorAll('*')) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    const ox = st.overflowX;
    if (ox !== 'hidden' && ox !== 'clip') continue;
    if (el.scrollWidth <= el.clientWidth + 1) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    //  Le motif « visuellement cache » (`.vx-sr-only` : 1x1 px, clip) est du
    //  texte DESTINE aux lecteurs d'ecran, pas du texte derobe a l'oeil. Aucun
    //  contenu reel ne vit dans une boite d'un pixel : l'exclure ne peut donc
    //  pas masquer un defaut.
    if (r.width <= 1 || r.height <= 1) continue;
    //  Une troncature ASSUMEE (`text-overflow:ellipsis`) n'est pas une coupe
    //  accidentelle : les trois points disent au lecteur qu'il manque du texte.
    if (st.textOverflow === 'ellipsis') continue;
    //  Un conteneur SANS AUCUN CONTENU ne peut rien tronquer : son debordement
    //  vient d'un ornement (pseudo-element, animation) que le `overflow:hidden`
    //  est justement la pour rogner. Mesure : le squelette de chargement
    //  (`.vx-skeleton`, vide) porte un reflet `::after` en
    //  `transform:translateX(100%)` — a la fin du balayage son bord droit est a
    //  deux fois la largeur de la boite, d'ou un scrollWidth de 655 pour 366.
    //  L'instrument criait au defaut sur une decoration qui fonctionne comme
    //  prevu ; il ne se declenchait qu'en mode reel sans TWS, ou le squelette
    //  reste a l'ecran. Le critere reste HONNETE parce qu'une troncature
    //  suppose du contenu a tronquer : sans texte ni enfant, il n'y a rien a
    //  cacher.
    if (!(el.textContent || '').trim() && el.children.length === 0) continue;
    const cle = el.tagName + '.' + (el.className || '').toString().slice(0, 40);
    if (vus.has(cle)) continue;
    vus.add(cle);
    out.elements.push({
      tag: el.tagName.toLowerCase(),
      classe: (el.className || '').toString().slice(0, 60),
      contenu: el.scrollWidth, boite: el.clientWidth,
      coupe: el.scrollWidth - el.clientWidth,
    });
  }
  out.elements = out.elements.slice(0, 12);
  return out;
}
"""

SONDE_CLAVIER = r"""
() => {
  const SEL = 'a[href], button, input, select, textarea, [tabindex]';
  const sans_anneau = [], non_focusables = [];
  let total = 0;
  const empreinte = (el) => {
    const s = getComputedStyle(el);
    return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow,
            s.borderColor, s.borderWidth, s.backgroundColor].join('|');
  };
  for (const el of document.querySelectorAll(SEL)) {
    if (el.disabled) continue;
    if (el.getAttribute('tabindex') === '-1') continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    total++;
    const avant = empreinte(el);
    el.focus();
    if (document.activeElement !== el) {
      non_focusables.push({tag: el.tagName.toLowerCase(),
                           texte: (el.textContent || '').trim().slice(0, 40)});
      continue;
    }
    const apres = empreinte(el);
    if (avant === apres) {
      sans_anneau.push({tag: el.tagName.toLowerCase(),
                        classe: (el.className || '').toString().slice(0, 50),
                        texte: (el.textContent || '').trim().slice(0, 40)});
    }
    el.blur();
  }
  return {interactifs: total,
          sans_anneau: sans_anneau.slice(0, 12), sans_anneau_total: sans_anneau.length,
          non_focusables: non_focusables.slice(0, 8),
          non_focusables_total: non_focusables.length};
}
"""

SONDE_CONTRASTE = r"""
() => {
  const lum = (c) => {
    const f = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92
                                        : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
  };
  const lire = (s) => {
    const m = (s || '').match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return {rgb: [p[0], p[1], p[2]], a: p.length > 3 ? p[3] : 1};
  };
  const ratio = (a, b) => {
    const la = lum(a), lb = lum(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };
  //  LE POINT DELICAT, ET LA DEUXIEME FOIS OU L'INSTRUMENT ETAIT FAUX.
  //
  //  (a) Un texte sur `transparent` herite du fond d'un ancetre : le lire sur
  //      l'element lui-meme donnerait « transparent vs texte », un ratio
  //      invente. D'ou la remontee.
  //  (b) Mais un bouton peint par un `linear-gradient` a un `backgroundColor`
  //      A ZERO. Remonter SANS REGARDER LE DEGRADE saute le fond reellement
  //      peint et atterrit sur la page sombre : l'encre sombre du bouton
  //      primaire ressortait alors a 1,04:1 alors qu'elle est a ~9:1.
  //
  //  On s'arrete donc au premier fond OPAQUE, couleur unie ou degrade. Pour un
  //  degrade on retient la teinte la MOINS favorable : le texte est quelque
  //  part sur la rampe, et la borne honnete est le pire point.
  const stops_opaques = (img) => {
    if (!img || img === 'none') return [];
    const out = [];
    for (const m of img.matchAll(/rgba?\(([^)]+)\)/g)) {
      const p = m[1].split(',').map(x => parseFloat(x));
      const a = p.length > 3 ? p[3] : 1;
      //  Un voile translucide (`rgba(255,255,255,0.04)`, le verre) ne PEINT
      //  pas : il teinte. On continue de remonter — cf. limite documentee.
      if (a > 0.5) out.push([p[0], p[1], p[2]]);
    }
    return out;
  };
  const pire_fond = (el, fg) => {
    let p = el;
    while (p) {
      const s = getComputedStyle(p);
      const stops = stops_opaques(s.backgroundImage);
      if (stops.length) {
        let pire = stops[0], min = Infinity;
        for (const st of stops) {
          const r = ratio(fg, st);
          if (r < min) { min = r; pire = st; }
        }
        return pire;
      }
      const c = lire(s.backgroundColor);
      if (c && c.a > 0.5) return c.rgb;
      p = p.parentElement;
    }
    //  Aucun ancetre ne peint : le navigateur peint alors sa toile, qui est
    //  BLANCHE. Supposer du noir ici — le reflexe sur un produit sombre —
    //  rendrait le pire cas possible (texte blanc sur rien, donc invisible)
    //  parfaitement conforme.
    return [255, 255, 255];
  };
  //  LA TROISIEME FOIS OU L'INSTRUMENT ETAIT FAUX.
  //
  //  Un titre peint par `background-clip:text` + `-webkit-text-fill-color:
  //  transparent` a son ENCRE dans son propre `background-image`. Lire
  //  `color` y donne une couleur qui n'est jamais peinte, et `pire_fond`
  //  demarrant sur l'element prend le degrade de l'encre POUR LE FOND :
  //  encre claire comparee a elle-meme, 1,09:1. Les trois h1 du produit
  //  ressortaient ainsi en defaut alors qu'ils sont du blanc sur obsidienne.
  //
  //  Quand ce motif est reconnu : l'encre est la rampe de l'element, le fond
  //  est le premier ancetre qui peint, et le ratio retenu est le PIRE couple.
  const encre_clippee = (el, s) => {
    const clip = s.webkitBackgroundClip || s.backgroundClip;
    if (clip !== 'text') return null;
    //  Un `text-fill-color` OPAQUE gagne sur le degrade : l'encre est lui,
    //  et le cas ordinaire s'applique. Ne pas le verifier ferait lire un
    //  degrade decoratif comme encre sur un texte parfaitement peint.
    const fill = lire(s.webkitTextFillColor);
    if (fill && fill.a > 0.1) return null;
    const stops = stops_opaques(s.backgroundImage);
    return stops.length ? stops : null;
  };
  const faibles = [];
  let mesures = 0;
  for (const el of document.querySelectorAll('*')) {
    //  Seuls les elements qui portent EUX-MEMES du texte : sinon un <div>
    //  racine serait compte une fois par mot de la page.
    let propre = '';
    for (const n of el.childNodes) if (n.nodeType === 3) propre += n.textContent;
    propre = propre.trim();
    if (propre.length < 2) continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    if (parseFloat(st.opacity) < 0.1) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const encre = encre_clippee(el, st);
    const fg = lire(st.color);
    if (!encre && (!fg || fg.a < 0.1)) continue;
    const taille = parseFloat(st.fontSize);
    const gras = parseInt(st.fontWeight, 10) >= 700;
    const grand = taille >= 24 || (gras && taille >= 18.66);
    const seuil = grand ? 3.0 : 4.5;
    let rr;
    if (encre) {
      rr = Infinity;
      for (const teinte of encre) {
        //  Le fond part du PARENT : l'element porte l'encre, pas le fond.
        const r = ratio(teinte, pire_fond(el.parentElement, teinte));
        if (r < rr) rr = r;
      }
    } else {
      rr = ratio(fg.rgb, pire_fond(el, fg.rgb));
    }
    mesures++;
    if (rr < seuil) {
      faibles.push({texte: propre.slice(0, 40), ratio: Math.round(rr * 100) / 100,
                    seuil: seuil, taille: taille,
                    classe: (el.className || '').toString().slice(0, 50)});
    }
  }
  faibles.sort((a, b) => a.ratio - b.ratio);
  return {mesures: mesures, faibles: faibles.slice(0, 12),
          faibles_total: faibles.length};
}
"""


def _sonder(page, url, largeur, *, attendre=1800, contenu=None):
    """Charge et applique les quatre sondes. Retourne le relevé brut.

    `contenu` remplace le chargement d'URL par un document fabriqué. C'est ce
    qui permet aux témoins de passer par **cette fonction-ci** au lieu d'en
    réimplémenter une copie — la distinction n'est pas cosmétique : tant que
    les témoins posaient leur propre écouteur `pageerror`, supprimer celui du
    balayage laissait les témoins verts et la mesure aveugle. La mutation l'a
    montré, et c'est le trou le plus grave des cinq qu'elle a trouvés."""
    erreurs = []
    page.on('pageerror', lambda e: erreurs.append('pageerror: %s' % str(e)[:200]))
    page.on('console', lambda m: erreurs.append('console.%s: %s' % (m.type, m.text[:200]))
            if m.type == 'error' else None)
    page.set_viewport_size({'width': largeur, 'height': 900})
    statut = None
    if contenu is not None:
        page.set_content(contenu, wait_until='domcontentloaded')
        page.wait_for_timeout(150)
    else:
        #  `networkidle` ne se stabilise jamais : les pages interrogent
        #  /api/live en boucle. On attend le document, puis un delai fixe
        #  d'hydratation.
        rep = page.goto(url, wait_until='domcontentloaded', timeout=25000)
        statut = rep.status if rep else None
        page.wait_for_timeout(attendre)
    return {
        'url': url, 'largeur': largeur, 'statut': statut,
        'debordement': page.evaluate(SONDE_DEBORDEMENT),
        'clavier': page.evaluate(SONDE_CLAVIER),
        'contraste': page.evaluate(SONDE_CONTRASTE),
        'erreurs': erreurs[:10],
        'erreurs_total': len(erreurs),
    }


#: Le degrade EXACT du bouton primaire servi, releve dans le navigateur. Le
#: garder litteral est deliberé : c'est le cas qui a pris l'instrument en
#: defaut, et le temoin negatif ne prouve quelque chose que s'il le rejoue.
DEGRADE_PRIMAIRE = 'linear-gradient(rgb(225,160,110) 0%, rgb(210,138,84) 100%)'

#: #636363 sur #000 vaut EXACTEMENT 3,50:1 — sous le seuil normal (4,5) et
#: au-dessus du seuil grand texte (3,0). C'est ce couple qui épingle les DEUX
#: seuils : les défauts criants (1,3:1) laissaient passer un abaissement du
#: seuil à 1,5:1, mutation qui aurait rendu muet tout un domaine de défauts
#: réels. Un témoin doit vivre au bord, pas au fond.
GRIS_3_50 = '#636363'

PAGE_TEMOIN_DEFAUTS = """
<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;background:#777}
  .cadre{width:300px}
  .large{width:3000px;height:40px;background:#333}
  .coupe{width:300px;overflow-x:hidden}
  .gris{color:#888;background:#777;font-size:14px}
  /* Un stop CLAIR et un stop SOMBRE : seule la lecture du PIRE point de la
     rampe voit le defaut. Prendre le meilleur stop rendrait ce texte conforme. */
  .degrade-mixte{color:#000;background:linear-gradient(rgb(255,255,255),rgb(20,20,20))}
  /* Encre peinte par `background-clip:text` : une rampe GRISE sur le fond gris
     #777 de la page. Le texte est reellement illisible, et `color:#fff` ment —
     il n'est jamais peint. Lire `color` rendrait ce defaut invisible. */
  .encre-clippee{color:#fff;font-size:26px;-webkit-text-fill-color:transparent;
    -webkit-background-clip:text;background-clip:text;
    background-image:linear-gradient(rgb(130,130,130),rgb(122,122,122))}
  .bord{color:%s;background:#000;font-size:14px}
  button{outline:none!important;border:0;background:#777;color:#888}
  button:focus{outline:none!important}
</style></head><body>
  <div class="cadre"><div class="large">deborde le document</div></div>
  <div class="coupe"><div class="large">contenu coupe sans barre</div></div>
  <p class="gris">texte gris sur gris</p>
  <p class="degrade-mixte">texte sur degrade mixte</p>
  <p class="encre-clippee">encre clippee illisible</p>
  <p class="bord">texte au bord du seuil</p>
  <button class="gris">bouton sans anneau</button>
  <script>throw new Error('temoin erreur console');</script>
</body></html>
""" % GRIS_3_50

#: Page SANS aucun fond peint : le texte blanc y est invisible. Elle éprouve le
#: repli de la remontée — la couleur employée quand AUCUN ancêtre ne peint.
#: Ce repli doit être le BLANC : c'est ce que le navigateur peint réellement
#: derrière un document qui ne demande rien. Le supposer noir rendait le pire
#: cas (blanc sur blanc) invisible, et cette page ne l'aurait jamais montré.
PAGE_TEMOIN_NU = """
<!doctype html><html><head><meta charset="utf-8"></head><body>
  <p style="color:#fff">texte blanc sur un fond que personne ne peint</p>
</body></html>
"""

PAGE_TEMOIN_PROPRE = """
<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;background:#000;color:#fff}
  .cadre{width:300px}
  .defile{width:300px;overflow-x:auto}
  .large{width:3000px;height:20px}
  .primaire{color:#130b07;background:%s}
  /* Le MEME gris qu'au-dessus, en GRAND : 3,50:1 passe le seuil du grand
     texte (3,0). Si quelqu'un aligne tout sur 4,5, ce temoin le dit. */
  .grand{color:%s;background:#000;font-size:26px}
  button{background:#000;color:#fff;border:1px solid #fff}
  button:focus{outline:3px solid #fff}
  /* Le squelette de chargement du produit, reproduit a l'identique : boite
     VIDE, `overflow:hidden`, et un reflet `::after` qui balaie en
     `translateX(100%%)`. A la fin du balayage son bord droit est a deux fois la
     largeur de la boite. C'est une decoration que le rognage est justement la
     pour contenir — aucun contenu n'est cache, puisqu'il n'y en a pas. */
  .squelette{width:300px;height:40px;overflow:hidden;position:relative;background:#222}
  .squelette::after{content:"";position:absolute;inset:0;transform:translateX(100%%);
    background:linear-gradient(90deg,transparent,rgba(255,255,255,.05),transparent)}
  /* Le h1 du produit, reproduit a l'identique : rampe blanc -> #D4D8DF peinte
     dans le texte, sur obsidienne. Parfaitement lisible. Si l'instrument le
     signale, c'est LUI qui est faux — et c'est exactement ce qui arrivait. */
  .titre-clippe{font-size:24px;color:#f3f5f8;-webkit-text-fill-color:transparent;
    -webkit-background-clip:text;background-clip:text;
    background-image:linear-gradient(174deg,rgb(255,255,255) 0%%,rgb(212,216,223) 116%%)}
</style></head><body>
  <div class="squelette"></div>
  <div class="cadre"><p>texte blanc sur noir</p></div>
  <div class="defile"><div class="large">large mais DEFILABLE — c'est le remede</div></div>
  <p class="primaire">encre sombre sur le degrade du bouton primaire</p>
  <p class="grand">grand texte au-dessus du seuil</p>
  <p class="titre-clippe">titre argente au degrade</p>
  <button>bouton avec anneau</button>
</body></html>
""" % (DEGRADE_PRIMAIRE, GRIS_3_50)


def _temoins(navigateur) -> list:
    """Éprouve les quatre détecteurs sur trois pages fabriquées.

    Le témoin POSITIF vérifie qu'un défaut planté est vu ; le NÉGATIF qu'une
    page saine ne produit rien. Sans le second, un détecteur qui crie sur tout
    passerait pour vigilant.

    **Les témoins passent par `_sonder`**, la fonction qu'emploie le balayage.
    Une copie locale des écouteurs les rendrait verts pendant que la mesure
    devient aveugle : c'est ce que la mutation « ne plus écouter pageerror » a
    démontré."""
    echecs = []
    ctx = navigateur.new_context(viewport={'width': 390, 'height': 900},
                                 service_workers='block')
    page = ctx.new_page()
    releve = _sonder(page, None, 390, contenu=PAGE_TEMOIN_DEFAUTS)
    d, k, c = releve['debordement'], releve['clavier'], releve['contraste']
    vus = releve['erreurs']
    if not d['document']:
        echecs.append('TEMOIN DEBORDEMENT MUET (document) : un enfant de 3000 px '
                      'ne fait pas defiler le document — la sonde ne mesure rien')
    if not d['elements']:
        echecs.append('TEMOIN DEBORDEMENT MUET (coupe) : un contenu de 3000 px '
                      'dans un `overflow-x:hidden` de 300 n\'est pas vu — la '
                      'sonde ne detecte pas le texte inatteignable')
    if not k['sans_anneau']:
        echecs.append('TEMOIN CLAVIER MUET : un bouton sous `outline:none` sans '
                      'aucun autre changement au focus passe pour visible')
    if not any('gris sur gris' in f['texte'] for f in c['faibles']):
        echecs.append('TEMOIN CONTRASTE MUET (uni) : #888 sur #777 (~1,3:1) passe '
                      'le seuil de 4,5:1 — le fond effectif n\'est pas remonte')
    if not any('degrade mixte' in f['texte'] for f in c['faibles']):
        echecs.append('TEMOIN CONTRASTE MUET (degrade) : du noir sur un degrade '
                      'dont le PIRE stop est rgb(20,20,20) passe le seuil — soit '
                      'le fond peint par `background-image` n\'est pas evalue, '
                      'soit c\'est le MEILLEUR stop qui est retenu')
    #  Le temoin de SEUIL : 3,50:1 est un defaut discret. Les defauts criants
    #  (1,3:1) laissaient passer un abaissement du seuil a 1,5:1.
    if not any('au bord du seuil' in f['texte'] for f in c['faibles']):
        echecs.append('TEMOIN CONTRASTE MUET (seuil) : %s sur #000, soit '
                      '3,50:1, passe le seuil normal de 4,5:1 — le seuil AA '
                      'n\'est plus celui qui est applique' % GRIS_3_50)
    if not any('encre clippee' in f['texte'] for f in c['faibles']):
        echecs.append('TEMOIN CONTRASTE MUET (encre clippee) : une rampe grise '
                      'peinte par `background-clip:text` sur un fond gris '
                      'ressort conforme — la sonde lit `color`, qui n\'est '
                      'jamais peint, au lieu de l\'encre reelle')
    if not vus:
        echecs.append('TEMOIN ERREUR MUET : un `throw` au chargement n\'est pas '
                      'capte — le compteur d\'erreurs console ne compte rien')

    #  Page sans aucun fond peint : eprouve le REPLI de la remontee.
    nu = _sonder(page, None, 390, contenu=PAGE_TEMOIN_NU)
    if not nu['contraste']['faibles']:
        echecs.append('TEMOIN CONTRASTE MUET (repli) : du texte blanc sur un '
                      'document dont PERSONNE ne peint le fond ressort conforme '
                      '— le repli de la remontee suppose un fond sombre, alors '
                      'que le navigateur peint du blanc')

    releve2 = _sonder(page, None, 390, contenu=PAGE_TEMOIN_PROPRE)
    d2, k2, c2 = releve2['debordement'], releve2['clavier'], releve2['contraste']
    if d2['elements'] or d2['document']:
        echecs.append('TEMOIN NEGATIF ROMPU (debordement) : une page saine '
                      'ressort en debordement. Deux motifs sont eprouves ici et '
                      'aucun n\'est un defaut — un conteneur `overflow-x:auto` '
                      '(le remede) et un squelette VIDE dont le reflet anime '
                      'deborde sa boite rognee (une decoration, pas du contenu '
                      'cache). Trouve : %s'
                      % (d2['elements'][:1] or d2['document']))
    if k2['sans_anneau']:
        echecs.append('TEMOIN NEGATIF ROMPU (clavier) : un bouton avec '
                      '`outline:3px` au focus ressort sans anneau')
    #  CE TEMOIN-CI EST LE PLUS INSTRUCTIF : c'est exactement le cas que
    #  l'instrument classait a tort. L'encre sombre du bouton primaire est a
    #  ~7:1 sur son degrade, et a ~1:1 sur le fond de page. Un detecteur qui
    #  remonte au-dela du degrade condamne le bouton le plus visible du produit.
    if any('degrade du bouton primaire' in f['texte'] for f in c2['faibles']):
        echecs.append('TEMOIN NEGATIF ROMPU (degrade) : l\'encre sombre du '
                      'bouton primaire ressort en contraste faible — la remontee '
                      'saute le fond REELLEMENT peint et atterrit sur la page')
    #  Le seuil du GRAND texte est distinct (3,0) : le meme gris a 3,50:1, en
    #  26 px, est conforme. L'aligner sur 4,5 condamnerait des titres corrects.
    if any('grand texte' in f['texte'] for f in c2['faibles']):
        echecs.append('TEMOIN NEGATIF ROMPU (grand texte) : 3,50:1 en 26 px '
                      'ressort en anomalie — le seuil du grand texte (3,0) '
                      'n\'est plus distingue de celui du texte courant')
    #  Le pendant du precedent, et le defaut que ce lot corrige : le h1 du
    #  produit, blanc sur obsidienne, etait declare a 1,09:1 parce que son
    #  PROPRE degrade d'encre etait pris pour son fond.
    if any('titre argente' in f['texte'] for f in c2['faibles']):
        echecs.append('TEMOIN NEGATIF ROMPU (encre clippee) : un titre blanc '
                      'peint par `background-clip:text` sur obsidienne ressort '
                      'en contraste faible — le degrade de l\'ENCRE est pris '
                      'pour le FOND, et l\'encre est comparee a elle-meme')
    if c2['faibles']:
        echecs.append('TEMOIN NEGATIF ROMPU (contraste) : une page saine ressort '
                      'en contraste faible (%s)' % c2['faibles'][:1])
    ctx.close()
    return echecs


def mesurer(base: str = BASE_DEFAUT, largeurs=LARGEURS, *, temoins: bool = True) -> dict:
    from playwright.sync_api import sync_playwright
    chemin = _chromium()
    releves, echecs_temoins = [], []
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=chemin, args=['--no-sandbox'])
        if temoins:
            echecs_temoins = _temoins(nav)
        for ident, href in espaces():
            for largeur in largeurs:
                #  Un contexte NEUF par relevé : les écouteurs d'erreurs et le
                #  localStorage d'une page ne doivent pas colorer la suivante.
                ctx = nav.new_context(viewport={'width': largeur, 'height': 900},
                                      service_workers='block')
                page = ctx.new_page()
                try:
                    r = _sonder(page, base.rstrip('/') + href, largeur)
                except Exception as exc:  # noqa: BLE001
                    r = {'url': base + href, 'largeur': largeur, 'statut': None,
                         'echec': str(exc)[:200], 'erreurs': [], 'erreurs_total': 0,
                         'debordement': {'document': None, 'elements': []},
                         'clavier': {'interactifs': 0, 'sans_anneau': [],
                                     'sans_anneau_total': 0, 'non_focusables': [],
                                     'non_focusables_total': 0},
                         'contraste': {'mesures': 0, 'faibles': [], 'faibles_total': 0}}
                r['espace'] = ident
                releves.append(r)
                ctx.close()
        nav.close()
    return {
        'base': base, 'largeurs': list(largeurs),
        'espaces': [i for i, _ in espaces()],
        'echecs_temoins': echecs_temoins,
        'releves': releves,
        'total_debordements': sum(len(r['debordement']['elements']) for r in releves),
        'total_sans_anneau': sum(r['clavier']['sans_anneau_total'] for r in releves),
        'total_contraste': sum(r['contraste']['faibles_total'] for r in releves),
        'total_erreurs': sum(r['erreurs_total'] for r in releves),
        'statuts_non_200': [r['url'] for r in releves if r['statut'] != 200],
    }


def rendre_texte(r: dict) -> str:
    out = ['LES HUIT ESPACES — DESKTOP / MOBILE / CLAVIER / CONTRASTE',
           '=' * 66,
           'base     : %s' % r['base'],
           'largeurs : %s' % ', '.join(str(x) for x in r['largeurs']),
           '']
    entete = '%-14s %6s %6s %8s %8s %9s %7s' % (
        'espace', 'larg.', 'HTTP', 'debord.', 'sans-ann', 'contraste', 'err.')
    out.append(entete)
    out.append('-' * len(entete))
    for x in r['releves']:
        out.append('%-14s %6d %6s %8d %8d %9d %7d' % (
            x['espace'], x['largeur'], x['statut'],
            len(x['debordement']['elements']) + (1 if x['debordement']['document'] else 0),
            x['clavier']['sans_anneau_total'],
            x['contraste']['faibles_total'], x['erreurs_total']))
    out.append('')
    out.append('TOTAUX  debordements %d · sans anneau %d · contraste %d · erreurs %d'
               % (r['total_debordements'], r['total_sans_anneau'],
                  r['total_contraste'], r['total_erreurs']))
    detail = [x for x in r['releves']
              if x['debordement']['elements'] or x['clavier']['sans_anneau']
              or x['contraste']['faibles'] or x['erreurs']]
    for x in detail[:14]:
        out.append('')
        out.append('  %s @ %d px' % (x['espace'], x['largeur']))
        if x['debordement']['document']:
            d = x['debordement']['document']
            out.append('     DEBORD   le DOCUMENT defile : %d px de contenu pour '
                       '%d px de fenetre' % (d['scroll'], d['client']))
        for e in x['debordement']['elements'][:4]:
            out.append('     COUPE    <%s class="%s"> %d px de contenu dans %d px, '
                       'sans barre de defilement'
                       % (e['tag'], e['classe'], e['contenu'], e['boite']))
        for e in x['clavier']['sans_anneau'][:4]:
            out.append('     CLAVIER  <%s> « %s » sans changement visible au focus'
                       % (e['tag'], e['texte']))
        for e in x['contraste']['faibles'][:4]:
            out.append('     CONTRAST %.2f:1 (seuil %.1f) « %s »'
                       % (e['ratio'], e['seuil'], e['texte']))
        for e in x['erreurs'][:3]:
            out.append('     ERREUR   %s' % e)
    return '\n'.join(out)


def main() -> int:
    #  L'AVEU avant la mesure. Sans lui, l'outil sortait en code 1 avec
    #  26 lignes de trace Playwright et zero ligne utile — ce qui se lit
    #  « le produit a plante », l'inverse exact de la verite.
    if not navigateur_pret():
        return abandonner_sans_navigateur()
    base = BASE_DEFAUT
    if '--base' in sys.argv:
        base = sys.argv[sys.argv.index('--base') + 1]
    largeurs = LARGEURS
    if '--largeurs' in sys.argv:
        largeurs = tuple(int(x) for x in sys.argv[sys.argv.index('--largeurs') + 1].split(','))
    r = mesurer(base, largeurs)
    if r['echecs_temoins']:
        for e in r['echecs_temoins']:
            print('TEMOIN MUET : %s' % e, file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2, ensure_ascii=False) if '--json' in sys.argv
          else rendre_texte(r))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
