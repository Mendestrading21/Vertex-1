#!/usr/bin/env python3
"""Vertex Test 1.0 · #781 — QUELLE COUCHE VISUELLE EST RÉELLEMENT SERVIE ?

`#781` s'ouvre sur un constat : *« le dépôt empile plusieurs directions
visuelles et de nombreuses feuilles CSS/implémentations de graphiques »*. C'est
une **hypothèse**, et l'acceptation demandée — « une seule couche visuelle
canonique servie sur les huit espaces » — ne peut se prononcer que sur une
mesure. Ce que `ls` montre n'est pas ce que le navigateur reçoit.

Un précédent rend la prudence obligatoire : le guide du projet décrivait
`vx_kit.py` comme un « kit global présent sur toutes les pages ». Mesuré, son
JS (21 727 o) n'atteignait **aucune** des huit.

## Les cinq mesures

1. **Couches servies** — quelle feuille atteint quelle page, et pour quels
   octets. Répond directement à la prémisse de l'issue.
2. **Règles jamais appariées** — pour chaque règle de chaque feuille chargée,
   existe-t-il un élément qui la satisfasse sur *au moins une* des huit pages ?
   Voir la limite plus bas : ce sont des **candidates**, pas un permis de
   supprimer.
3. **Cibles tactiles** — contre les **deux** seuils que le produit s'est donnés,
   lus dans `responsive.css` et jamais recopiés.
4. **Mouvement réduit** — sous `prefers-reduced-motion: reduce`, reste-t-il des
   animations ou des transitions longues ? Une demande, pas une préférence.
5. **Hexadécimaux bruts** — `#781` demande « aucun hex dispersé hors tokens ».
   Mesuré sur les **octets servis**, et reporté sans jugement.

## Deux distinctions que l'instrument a dû apprendre

**Deux seuils tactiles, pas un.** Le lot 612 a mesuré en vrai Chromium à 390 px :
40 px pour les actions primaires, **32 px pour les secondaires**, appliqués
uniformément à 40 boutons. `tests/test_cibles_tactiles.py` garde les
deux. Mesurer contre le seul 40 px rend **113 « défauts »** dont la quasi-
totalité *sont* la règle secondaire — c'est accuser le produit d'une décision
qu'il a prise exprès, et noyer le seul défaut réel.

**Hauteur et largeur ne se réparent pas pareil.** La hauteur ne dépend que du
CSS : trop courte = défaut franc. La largeur dépend du **texte** et de la place
que la mise en page laisse — un lien étroit peut n'être que le *symptôme* d'un
conteneur trop petit, et l'élargir sans regarder le conteneur soigne le
thermomètre. Mesure à l'appui : les liens étroits du fil d'Ariane l'étaient
parce que le fil recevait 84 px pour 122-185 px de contenu.

## La limite qui gouverne la mesure n° 2

« Jamais appariée **au chargement**, sur ces huit pages » n'est pas « morte ».
Une règle d'état (`.vx-drawer.open`, une classe posée par JS après une
interaction) ne peut pas s'apparier à l'instant du relevé, et le lui reprocher
serait absurde. Les sélecteurs à pseudo-classes sont réduits à leur partie
structurelle avant l'essai, et le résultat reste une **liste de candidates**,
conforme à `CLEANUP_POLICY.md`.

Cet outil **ne supprime rien**.

Usage :
    python tools/mesures/mesurer_couche_visuelle.py [--json] [--base URL]
                                                       [--largeur 390]
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
    _chromium, abandonner_sans_navigateur, espaces, navigateur_pret)

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
LARGEUR_DEFAUT = 390

_CSS_RESPONSIVE = RACINE / 'vertex' / 'static' / 'vertex' / 'css' / 'responsive.css'


def seuils_tactiles() -> dict:
    """Les deux seuils, LUS dans le CSS servi.

    Les recopier ici les ferait diverger du produit au premier ajustement, et
    l'instrument se mettrait à l'accuser."""
    src = _CSS_RESPONSIVE.read_text(encoding='utf-8')
    primaire = re.search(r"\.vx-btn,\.vx-tab,\.vx-chip\{min-height:(\d+)px\}", src)
    secondaire = re.search(r"\.vx-btn-sm\{min-height:(\d+)px\}", src)
    if not primaire or not secondaire:
        raise SystemExit('seuils tactiles introuvables dans responsive.css — '
                         'corriger la lecture, ne pas recopier les valeurs')
    return {'primaire': int(primaire.group(1)),
            'secondaire': int(secondaire.group(1))}


SONDE_COUCHES = r"""
() => {
  const out = {feuilles: [], inline_octets: 0, scripts: []};
  for (const f of document.styleSheets) {
    let n = 0;
    try { n = f.cssRules.length; } catch (e) { n = -1; }   // feuille opaque
    out.feuilles.push({href: f.href ? f.href.replace(location.origin, '') : null,
                       regles: n});
  }
  for (const s of document.querySelectorAll('style')) {
    out.inline_octets += (s.textContent || '').length;
  }
  for (const s of document.querySelectorAll('script[src]')) out.scripts.push(s.getAttribute('src'));
  return out;
}
"""

SONDE_REGLES = r"""
() => {
  //  Les selecteurs sont reduits a leur partie STRUCTURELLE : `:hover`,
  //  `::after`, `:focus-visible` ne peuvent pas s'apparier a l'instant du
  //  releve, et le leur reprocher produirait une liste entierement fausse.
  const structurel = (sel) => sel
    .replace(/::?[a-zA-Z-]+(\([^)]*\))?/g, '')
    .replace(/\s+/g, ' ').trim();
  const apparie = new Set(), total = new Set();
  const parcourir = (regles, origine) => {
    for (const r of regles) {
      if (r.cssRules && r.selectorText === undefined) { parcourir(r.cssRules, origine); continue; }
      if (!r.selectorText) continue;
      for (const brut of r.selectorText.split(',')) {
        const cle = origine + '||' + brut.trim();
        total.add(cle);
        const s = structurel(brut);
        if (!s) { apparie.add(cle); continue; }    // purement etat : non jugeable
        try { if (document.querySelector(s)) apparie.add(cle); } catch (e) { apparie.add(cle); }
      }
    }
  };
  for (const f of document.styleSheets) {
    const origine = f.href ? f.href.replace(location.origin, '') : '(inline)';
    try { parcourir(f.cssRules, origine); } catch (e) { /* opaque */ }
  }
  return {apparies: [...apparie], total: [...total]};
}
"""

SONDE_TACTILE = r"""
(seuils) => {
  const SEL = 'a[href], button, input, select, textarea, [role="button"], [onclick]';
  const trop_bas = [], trop_etroits = [], bande_secondaire = [];
  let total = 0;
  for (const el of document.querySelectorAll(SEL)) {
    if (el.disabled) continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    //  (a) Un element GARE hors du cadre n'est pas une cible tactile : le lien
    //  d'evitement clavier vit a `translateY(-160%)` jusqu'au focus. Le compter
    //  serait la meme erreur que compter un drawer ferme comme un debordement.
    if (r.bottom <= 0 || r.top >= window.innerHeight ||
        r.right <= 0 || r.left >= window.innerWidth) continue;
    //  (b) Un lien DANS une phrase n'est pas une cible a dimensionner :
    //  l'exiger imposerait des paragraphes a 40 px de hauteur de ligne.
    if (el.tagName === 'A' && el.closest('p, li, .vx-prose')) continue;
    total++;
    const fiche = {tag: el.tagName.toLowerCase(),
                   classe: (el.className || '').toString().slice(0, 50),
                   texte: (el.textContent || '').trim().slice(0, 30),
                   h: Math.round(r.height * 10) / 10,
                   w: Math.round(r.width * 10) / 10,
                   tronque: el.scrollWidth > el.clientWidth + 1};
    if (r.height < seuils.secondaire) { fiche.cause = 'hauteur'; trop_bas.push(fiche); }
    else if (r.width < seuils.secondaire) { fiche.cause = 'largeur'; trop_etroits.push(fiche); }
    else if (r.height < seuils.primaire || r.width < seuils.primaire) bande_secondaire.push(fiche);
  }
  return {total: total,
          trop_bas: trop_bas.slice(0, 15), trop_bas_total: trop_bas.length,
          trop_etroits: trop_etroits.slice(0, 15), trop_etroits_total: trop_etroits.length,
          bande_secondaire_total: bande_secondaire.length};
}
"""

SONDE_FIL = r"""
() => {
  //  Le fil d'Ariane est le SEUL repere de lieu persistant en mobile : la
  //  sidebar y est hors-ecran. S'il tronque, la page ne dit plus ou l'on est.
  const bc = document.querySelector('.vx-breadcrumb');
  if (!bc) return null;
  const visibles = [...bc.children].filter(c => getComputedStyle(c).display !== 'none');
  const h1 = document.querySelector('.vx-content h1, main h1, h1');
  return {
    boite: Math.round(bc.getBoundingClientRect().width),
    naturel: visibles.reduce((a, c) => a + c.scrollWidth, 0),
    segments: visibles.map(c => ({texte: (c.textContent || '').trim(),
                                  w: Math.round(c.getBoundingClientRect().width),
                                  naturel: c.scrollWidth,
                                  tronque: c.scrollWidth > c.clientWidth + 1})),
    h1: h1 ? (h1.textContent || '').trim() : null,
  };
}
"""

SONDE_MOUVEMENT = r"""
() => {
  const anime = [];
  for (const el of document.querySelectorAll('*')) {
    const s = getComputedStyle(el);
    const dureeA = parseFloat(s.animationDuration) || 0;
    const dureeT = parseFloat(s.transitionDuration) || 0;
    if (s.animationName !== 'none' && dureeA > 0.01) {
      anime.push({type: 'animation', nom: s.animationName, duree: dureeA,
                  classe: (el.className || '').toString().slice(0, 40)});
    } else if (dureeT > 0.15) {
      //  Une transition tres courte (<=150 ms) est un accuse de reception, pas
      //  du mouvement : la compter noierait le signal.
      anime.push({type: 'transition', duree: dureeT,
                  propriete: String(s.transitionProperty).slice(0, 40),
                  classe: (el.className || '').toString().slice(0, 40)});
    }
  }
  const vus = new Set(), uniques = [];
  for (const a of anime) {
    const k = a.type + a.classe + (a.nom || a.propriete || '');
    if (vus.has(k)) continue;
    vus.add(k); uniques.push(a);
  }
  return {uniques: uniques.slice(0, 15), uniques_total: uniques.length};
}
"""

_HEX = re.compile(r'#[0-9a-fA-F]{6}\b')


def _hex_servis(base, chemins):
    """Les couleurs REELLEMENT servies par chaque page.

    Une page qui n'a pas repondu etait auparavant `continue` : elle
    DISPARAISSAIT du releve, et la conclusion « cette couleur n'est servie
    nulle part » portait alors sur un corpus ampute EN SILENCE. C'est un faux
    NEGATIF, plus dangereux qu'un faux positif parce qu'il ne se voit pas — et
    le delai plat de 20 s suffisait a le declencher sur une page lente.

    Les pages muettes sont desormais conservees sous `None` : le lecteur
    distingue « aucune couleur trouvee » de « page jamais lue ».
    """
    trouves = {}
    for c in chemins:
        rep = appeler(base, c)
        trouves[c] = (None if not rep.a_repondu
                      else sorted({m.group(0).lower()
                                   for m in _HEX.finditer(rep.texte)}))
    return trouves


PAGE_TEMOIN = """
<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0}
  .existe{color:#abcdef}
  .n-existe-pas-du-tout-xyz{color:#123456}
  .bas{display:inline-block;width:80px;height:12px}
  .etroit{display:inline-block;width:12px;height:80px}
  .gare{position:fixed;left:0;top:0;transform:translateY(-500%);width:10px;height:10px}
  .bouge{animation:tourne 2s linear infinite;width:10px;height:10px}
  @keyframes tourne{from{transform:rotate(0)}to{transform:rotate(360deg)}}
</style></head><body>
  <p class="existe">apparie</p>
  <button class="bas">bas</button>
  <button class="etroit">etroit</button>
  <button class="gare">gare hors cadre</button>
  <div class="bouge">anime</div>
  <!--  Fil d'Ariane temoin : un segment qui TRONQUE (84 px de boite pour un
        libelle bien plus long, sous `overflow:hidden`) et un qui TIENT. Sans
        ce couple, un recensement de troncatures VIDE ne prouverait rien : il
        serait identique a celui d'une sonde devenue aveugle — un selecteur
        renomme suffit a faire rendre `null` a SONDE_FIL, et le gardien
        passerait au vert pour toujours.  -->
  <nav class="vx-breadcrumb" style="display:flex;width:200px">
    <span style="width:84px;overflow:hidden;white-space:nowrap"
          >segment beaucoup trop long pour sa boite</span>
    <span style="width:84px;overflow:hidden;white-space:nowrap">court</span>
  </nav>
</body></html>
"""


def _temoins(nav) -> list:
    """Chaque sonde est présentée à une page fabriquée dont on connaît la
    réponse. Les témoins négatifs comptent autant que les positifs : un
    détecteur qui crie sur tout est aussi inutilisable qu'un aveugle."""
    e = []
    seuils = seuils_tactiles()
    ctx = nav.new_context(viewport={'width': LARGEUR_DEFAUT, 'height': 900},
                          service_workers='block')
    page = ctx.new_page()
    page.set_content(PAGE_TEMOIN, wait_until='domcontentloaded')
    page.wait_for_timeout(150)

    if not page.evaluate(SONDE_COUCHES)['inline_octets']:
        e.append('TEMOIN COUCHES MUET : un bloc <style> present n\'est pas compte')

    regles = page.evaluate(SONDE_REGLES)
    jamais = set(regles['total']) - set(regles['apparies'])
    if not any('n-existe-pas-du-tout-xyz' in x for x in jamais):
        e.append('TEMOIN REGLES MUET : une regle dont le selecteur n\'existe sur '
                 'AUCUN element ressort appariee')
    if any('.existe' in x for x in jamais):
        e.append('TEMOIN NEGATIF ROMPU (regles) : une regle dont le selecteur '
                 'EXISTE ressort non appariee — tout le CSS vivant serait '
                 'signale comme mort')

    t = page.evaluate(SONDE_TACTILE, seuils)
    if not any(x['classe'] == 'bas' for x in t['trop_bas']):
        e.append('TEMOIN TACTILE MUET (hauteur) : un bouton de 12 px de haut '
                 'passe sous le plancher de %d px sans etre vu' % seuils['secondaire'])
    if not any(x['classe'] == 'etroit' for x in t['trop_etroits']):
        e.append('TEMOIN TACTILE MUET (largeur) : un bouton de 12 px de large '
                 'n\'est pas vu')
    if any(x['classe'] == 'bas' for x in t['trop_etroits']) or \
            any(x['classe'] == 'etroit' for x in t['trop_bas']):
        e.append('TEMOIN CROISE ROMPU : hauteur et largeur sont confondues — '
                 'or elles ne se reparent pas pareil')
    #  Le temoin le plus instructif : l'element GARE hors du cadre ne doit
    #  compter NI comme cible, ni comme anomalie.
    if any(x['classe'] == 'gare' for x in t['trop_bas'] + t['trop_etroits']):
        e.append('TEMOIN NEGATIF ROMPU (gare) : un element hors du cadre est '
                 'compte comme cible tactile — le lien d\'evitement clavier, '
                 'garé a translateY(-500%), serait signale sur les 8 espaces')

    if not page.evaluate(SONDE_MOUVEMENT)['uniques']:
        e.append('TEMOIN MOUVEMENT MUET : une animation infinie de 2 s n\'est pas vue')

    fil = page.evaluate(SONDE_FIL)
    if not fil:
        e.append('TEMOIN FIL MUET (absent) : un `.vx-breadcrumb` present rend '
                 '`null` — la sonde ne trouve plus le fil, et un recensement '
                 'de troncatures vide ne voudrait plus rien dire')
    else:
        tronques = [x for x in fil['segments'] if x['tronque']]
        tiennent = [x for x in fil['segments'] if not x['tronque']]
        if not any('trop long' in x['texte'] for x in tronques):
            e.append('TEMOIN FIL MUET : un segment de 84 px sous '
                     '`overflow:hidden`, dont le contenu est deux fois plus '
                     'large, ne ressort pas tronque')
        if not any(x['texte'] == 'court' for x in tiennent):
            e.append('TEMOIN NEGATIF ROMPU (fil) : un segment qui TIENT dans sa '
                     'boite ressort tronque — tous les espaces seraient '
                     'signales, et le recensement deviendrait du bruit')
    ctx.close()
    return e


def mesurer(base: str = BASE_DEFAUT, largeur: int = LARGEUR_DEFAUT, *,
            temoins: bool = True) -> dict:
    from playwright.sync_api import sync_playwright
    seuils = seuils_tactiles()
    releves, echecs = [], []
    appariees, totales = set(), set()
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=_chromium(), args=['--no-sandbox'])
        if temoins:
            echecs = _temoins(nav)
        for ident, href in espaces():
            #  `has_touch` EST NECESSAIRE. La regle de cible tactile du produit
            #  vit sous `@media (pointer:coarse)` : sans contexte tactile, elle
            #  ne s'applique PAS, et cette sonde relevait alors chaque puce a
            #  28 px comme « trop basse ». Douze faux defauts sur /calendar,
            #  mesures sur un produit correct — la regle existait, c'est
            #  l'instrument qui regardait au mauvais endroit. Verifie : avec
            #  `has_touch`, les memes puces font 44 px.
            ctx = nav.new_context(viewport={'width': largeur, 'height': 900},
                                  service_workers='block',
                                  has_touch=(largeur <= 480),
                                  is_mobile=(largeur <= 480))
            page = ctx.new_page()
            page.goto(base.rstrip('/') + href, wait_until='domcontentloaded', timeout=25000)
            page.wait_for_timeout(1800)
            couches = page.evaluate(SONDE_COUCHES)
            regles = page.evaluate(SONDE_REGLES)
            tactile = page.evaluate(SONDE_TACTILE, seuils)
            fil = page.evaluate(SONDE_FIL)
            appariees |= set(regles['apparies'])
            totales |= set(regles['total'])
            ctx.close()

            #  Mouvement reduit : un contexte SEPARE — la preference ne
            #  s'applique pas a un document deja charge.
            ctx2 = nav.new_context(viewport={'width': largeur, 'height': 900},
                                   service_workers='block', reduced_motion='reduce')
            page2 = ctx2.new_page()
            page2.goto(base.rstrip('/') + href, wait_until='domcontentloaded', timeout=25000)
            page2.wait_for_timeout(1200)
            mouvement = page2.evaluate(SONDE_MOUVEMENT)
            ctx2.close()

            releves.append({
                'espace': ident, 'href': href,
                'feuilles': [f['href'] for f in couches['feuilles'] if f['href']],
                'inline_octets': couches['inline_octets'],
                'scripts': couches['scripts'],
                'tactile': tactile, 'fil': fil, 'mouvement_reduit': mouvement,
            })
        nav.close()

    jamais = sorted(totales - appariees)
    par_feuille = {}
    for x in jamais:
        par_feuille.setdefault(x.split('||')[0], []).append(x.split('||', 1)[1])
    toutes = sorted({f for r in releves for f in r['feuilles']})
    presence = {f: sorted(r['espace'] for r in releves if f in r['feuilles'])
                for f in toutes}
    fils_tronques = [r['espace'] for r in releves
                     if r['fil'] and any(s['tronque'] for s in r['fil']['segments'])]

    return {
        'base': base, 'largeur': largeur, 'seuils_tactiles': seuils,
        'echecs_temoins': echecs, 'releves': releves,
        'feuilles': toutes, 'presence': presence,
        'feuilles_partout': sorted(f for f, p in presence.items() if len(p) == len(releves)),
        'feuilles_partielles': {f: p for f, p in presence.items() if len(p) < len(releves)},
        'regles_distinctes': len(totales),
        'regles_jamais_appariees': len(jamais),
        'jamais_par_feuille': {k: len(v) for k, v in sorted(par_feuille.items())},
        'exemples_jamais_appariees': {k: v[:8] for k, v in sorted(par_feuille.items())},
        #  La liste ENTIERE : `exemples_*` est tronquee pour l'affichage, et
        #  `mesurer_regles_mortes.py` a besoin de toutes les candidates pour
        #  produire une preuve — une preuve sur un echantillon n'en est pas une.
        'toutes_jamais_appariees': {k: v for k, v in sorted(par_feuille.items())},
        'tactile_trop_bas': sum(r['tactile']['trop_bas_total'] for r in releves),
        'tactile_trop_etroits': sum(r['tactile']['trop_etroits_total'] for r in releves),
        'tactile_bande_secondaire': sum(r['tactile']['bande_secondaire_total'] for r in releves),
        'fils_tronques': fils_tronques,
        'mouvement_total': sum(r['mouvement_reduit']['uniques_total'] for r in releves),
        'hex_servis': _hex_servis(base, [r['href'] for r in releves]),
    }


def rendre_texte(r: dict) -> str:
    s = r['seuils_tactiles']
    o = ['LA COUCHE VISUELLE REELLEMENT SERVIE',
         '=' * 68,
         'base : %s   largeur : %d px' % (r['base'], r['largeur']), '']
    o.append('FEUILLES CHARGEES : %d — dont %d sur les %d espaces'
             % (len(r['feuilles']), len(r['feuilles_partout']), len(r['releves'])))
    if r['feuilles_partielles']:
        o.append('   PARTIELLES (une couche diverge selon la page) :')
        for f, p in sorted(r['feuilles_partielles'].items()):
            o.append('      %-50s %s' % (f, ', '.join(p)))
    else:
        o.append('   aucune feuille partielle : la pile est la MEME partout')
    o.append('')
    o.append('REGLES CSS distinctes           : %d' % r['regles_distinctes'])
    o.append('   jamais appariees au chargement : %d  (CANDIDATES, pas une preuve)'
             % r['regles_jamais_appariees'])
    for f, n in sorted(r['jamais_par_feuille'].items(), key=lambda x: -x[1])[:8]:
        o.append('      %-50s %4d' % (f, n))
    o.append('')
    o.append('CIBLES TACTILES — les DEUX seuils du produit (%d primaire / %d secondaire)'
             % (s['primaire'], s['secondaire']))
    o.append('   HAUTEUR sous %d px : %d   <- defaut franc (le CSS seul decide)'
             % (s['secondaire'], r['tactile_trop_bas']))
    o.append('   LARGEUR sous %d px : %d   <- symptome possible d\'un conteneur '
             'trop etroit' % (s['secondaire'], r['tactile_trop_etroits']))
    o.append('   bande %d-%d px     : %d   (actions secondaires, lot 612 — info)'
             % (s['secondaire'], s['primaire'], r['tactile_bande_secondaire']))
    for x in r['releves']:
        for p in (x['tactile']['trop_bas'] + x['tactile']['trop_etroits'])[:2]:
            o.append('      %-14s %s <%s class="%s"> %sx%s%s — « %s »'
                     % (x['espace'], p['cause'].upper(), p['tag'], p['classe'],
                        p['w'], p['h'], ' TRONQUE' if p['tronque'] else '', p['texte']))
    o.append('')
    o.append('FIL D\'ARIANE (seul repere de lieu quand la sidebar est hors-ecran)')
    o.append('   tronque sur %d espace(s) : %s'
             % (len(r['fils_tronques']), ', '.join(r['fils_tronques']) or 'aucun'))
    for x in r['releves']:
        f = x['fil']
        if not f:
            continue
        marque = '  <-- TRONQUE' if x['espace'] in r['fils_tronques'] else ''
        o.append('   %-14s %3d px pour %3d px   %s%s'
                 % (x['espace'], f['boite'], f['naturel'],
                    ' / '.join(s2['texte'] for s2 in f['segments']), marque))
    o.append('')
    o.append('MOUVEMENT malgre `prefers-reduced-motion: reduce` : %d' % r['mouvement_total'])
    #  `None` = page JAMAIS LUE, distincte d'une page sans couleur. La
    #  compter comme vide gonflerait la conclusion « cette couleur n'est
    #  servie nulle part » d'un corpus ampute en silence.
    muettes = sorted(c for c, v in r['hex_servis'].items() if v is None)
    tous = sorted({h for v in r['hex_servis'].values() if v for h in v})
    o.append('HEXADECIMAUX distincts dans les octets servis     : %d' % len(tous))
    o.append('PAGES NON LUES (corpus ampute, conclusion partielle) : %d'
             % len(muettes))
    for c in muettes[:8]:
        o.append('   %s' % c)
    o.append('')
    o.append('RAPPEL : « jamais appariee au chargement » n\'est PAS « morte ».')
    o.append('Cet outil ne supprime rien (CLEANUP_POLICY.md).')
    return '\n'.join(o)


def main() -> int:
    #  L'AVEU avant la mesure. Sans lui, l'outil sortait en code 1 avec
    #  26 lignes de trace Playwright et zero ligne utile — ce qui se lit
    #  « le produit a plante », l'inverse exact de la verite.
    if not navigateur_pret():
        return abandonner_sans_navigateur()
    base, largeur = BASE_DEFAUT, LARGEUR_DEFAUT
    if '--base' in sys.argv:
        base = sys.argv[sys.argv.index('--base') + 1]
    if '--largeur' in sys.argv:
        largeur = int(sys.argv[sys.argv.index('--largeur') + 1])
    r = mesurer(base, largeur)
    if r['echecs_temoins']:
        for e in r['echecs_temoins']:
            print('TEMOIN MUET : %s' % e, file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2, ensure_ascii=False) if '--json' in sys.argv
          else rendre_texte(r))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
