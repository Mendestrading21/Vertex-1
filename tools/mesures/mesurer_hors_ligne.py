#!/usr/bin/env python3
"""Vertex Test 1.0 · G4 — QUAND LE RÉSEAU TOMBE, LE PRODUIT LE DIT-IL ?

Le balayage QA a couvert le mode démo, l'absence d'IBKR et la panne partielle.
Il restait le cas le plus banal et le moins testé : **le réseau tombe pendant
qu'on regarde l'écran**. C'est le mode dégradé du quotidien — métro, ascenseur,
wifi qui décroche — et c'est celui où un terminal d'analyse est le plus
dangereux, parce que les chiffres restent affichés alors qu'ils ne valent plus
rien.

## Ce qui a amené cette mesure

La preuve de non-usage du CSS (#781) a classé `.vx-offline-banner` « prouvée
inatteignable » : la classe est **stylée dans `states.css` et rendue par
personne**. Plutôt que d'en conclure « CSS mort, à supprimer », la question
utile était l'inverse : *le produit a-t-il seulement une façon de dire qu'il est
hors ligne ?*

`vx-core.js` porte bien le vocabulaire (`offline: 'Hors ligne'`) dans ses puces
de fraîcheur. Reste à savoir si l'écran l'emploie quand le réseau tombe.

## Le protocole

On charge la page **en ligne** — c'est le cas réaliste, personne n'ouvre un
terminal déjà déconnecté — puis on coupe le réseau et on laisse les
rafraîchissements échouer. On relève ensuite :

1. **le produit le DIT-il ?** un texte d'aveu (« Hors ligne », « À actualiser »,
   « Erreur »…) apparaît-il quelque part ;
2. **les chiffres MENTENT-ils ?** les valeurs affichées avant la coupure
   sont-elles toujours là, sans marque de péremption ;
3. **la console crie-t-elle ?** des erreurs réseau non rattrapées.

Le point 2 est le plus important, et le moins évident : un chiffre qui reste à
l'écran sans dire qu'il est périmé est **pire** qu'un écran vide. C'est
exactement l'invariant « aucune surface ne masque une donnée périmée ».

## Les témoins

Un détecteur de « le produit avoue » doit être éprouvé dans les deux sens :
une page qui n'avoue rien doit ressortir muette, une page qui avoue doit
ressortir parlante. Sans quoi « 0 anomalie » ne distingue pas un produit
honnête d'un détecteur aveugle.

Usage :
    python tools/mesures/mesurer_hors_ligne.py [--json] [--base URL]
Sorties : 0 = mesuré, 2 = témoin muet, 3 = NON MESURÉ (navigateur indisponible).
"""
from __future__ import annotations

import os

import json
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures.mesurer_qa_espaces import (  # noqa: E402
    _chromium, abandonner_sans_navigateur, espaces, navigateur_pret)

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
LARGEUR = 1440

#: Les mots par lesquels le produit peut avouer une coupure. Recopiés depuis
#: `vx-core.js` et les états servis — ce sont les mots que l'utilisateur lit.
AVEUX = ('Hors ligne', 'hors ligne', 'À actualiser', 'A actualiser',
         'Erreur', 'erreur', 'indisponible', 'Reconnexion', 'Périmé',
         'Perime', 'non disponible', 'Impossible')

SONDE_AVEU = r"""
(aveux) => {
  const texte = document.body ? (document.body.innerText || '') : '';
  const trouves = aveux.filter(a => texte.includes(a));
  //  Une puce de fraicheur qui a bascule est l'aveu le plus fin du produit.
  const puces = [...document.querySelectorAll('.vx-fresh-chip,[data-state],.vx-freshness')]
    .map(e => ({classe: (e.className || '').toString().slice(0, 40),
                etat: e.getAttribute('data-state') || e.getAttribute('data-live') || '',
                texte: (e.textContent || '').trim().slice(0, 30)}))
    .filter(p => p.texte);
  return {aveux_trouves: trouves, puces: puces.slice(0, 12), puces_total: puces.length};
}
"""

SONDE_CHIFFRES = r"""
() => {
  //  Les VALEURS mises en avant : ce sont elles qui trompent si elles restent
  //  a l'ecran sans dire qu'elles sont perimees.
  const sel = '.vx-kpi-value, .vx-mk-idx-val, .vx-metric-value, [data-value]';
  return [...document.querySelectorAll(sel)]
    .map(e => (e.textContent || '').trim())
    .filter(t => t && t !== '—' && t !== 'n/d')
    .slice(0, 20);
}
"""

#: Etats qu'une marque de fraicheur peut porter SANS mentir quand la donnee est
#: perimee. Repris du vocabulaire servi (`vx-core.js` : LABEL/_r) et de la
#: seconde grammaire `.vx-freshness[data-live]` ou `frozen` = perime.
#:
#: `fallback` et `delayed` n'y sont PAS, et c'est le correctif d'une premiere
#: version trop indulgente : ce sont des modes de PROVENANCE (« Secours »,
#: « Différé »), pas des enonces d'age. Les compter comme des aveux faisait
#: passer pour « date » un chiffre sous une simple banniere Demo — 12 chiffres
#: credités a tort sur 15. Une marque ne date un chiffre que si elle porte un
#: age (`.vx-update[data-ts]`, traite a part) ou un etat degrade.
ETATS_HONNETES = ('offline', 'error', 'stale', 'frozen', 'unknown', 'empty',
                  'saved', 'refreshing')

#: Etats par lesquels une marque AFFIRME la fraicheur. Apres deux heures sans
#: reseau, une telle affirmation est fausse — c'est le cas dangereux.
#:
#: Ne s'applique qu'aux marques d'ETAT (les puces). `.vx-update[data-mode]`
#: porte une PROVENANCE (« Live », « Différé », « Secours ») : `mode=live` dit
#: d'ou vient la donnee, pas qu'elle est fraiche — son age est ecrit a cote et
#: se recalcule. Les confondre faisait ressortir « date faux » les 4 chiffres de
#: Systeme, dont la portee contient une ligne `/healthz Live`.
REVENDIQUE_FRAIS = ('live', 'snapshot', 'ready')

#: Sonde PAR CHIFFRE : un verdict par page masque un defaut par chiffre, comme
#: mesure au lot 63 sur les badges. Pour chaque valeur affichee, on remonte
#: jusqu'au premier ancetre qui porte une marque de fraicheur — c'est la portee
#: dans laquelle ce chiffre est cense etre date — et on releve cette marque.
SONDE_PAR_CHIFFRE = r"""
(etats_honnetes) => {
  const SEL_VAL = '.vx-kpi-value, .vx-mk-idx-val, .vx-metric-value, [data-value]';
  const SEL_MARQUE = '.vx-fresh-chip[data-state], .vx-freshness[data-live],' +
                     '.vx-update[data-mode], .vx-stale-banner[data-state]';
  const etat = (m) => (m.getAttribute('data-state') || m.getAttribute('data-live')
                       || m.getAttribute('data-mode') || '').toLowerCase();
  const out = [];
  for (const v of document.querySelectorAll(SEL_VAL)) {
    const texte = (v.textContent || '').trim();
    if (!texte || texte === '—' || texte === 'n/d') continue;
    //  Remontee : la PREMIERE portee qui date ce chiffre. On ne remonte pas
    //  jusqu'a <body> par principe — une puce a l'autre bout de la page ne
    //  date pas ce chiffre-ci ; mais si aucune portee intermediaire ne date,
    //  le chiffre est bien « sans marque », et c'est le constat utile.
    let n = v.parentElement, marques = null, profondeur = 0;
    while (n && n !== document.body && profondeur < 12) {
      const m = n.querySelectorAll(SEL_MARQUE);
      if (m.length) { marques = [...m].map(x => ({
        etat: etat(x), texte: (x.textContent || '').trim().slice(0, 40),
        //  `age` = la marque situe la donnee dans le TEMPS (ligne de
        //  provenance) ; `etat` = elle qualifie sa fraicheur (puce). Seules
        //  les secondes peuvent AFFIRMER la fraicheur, donc mentir.
        genre: x.classList.contains('vx-update') ? 'age' : 'etat',
        //  « datable » = la marque porte l'horodatage qui permet de RECALCULER
        //  l'age. Sans lui, l'age affiche est fige a la peinture.
        datable: x.hasAttribute('data-ts') || x.hasAttribute('data-at') })); break; }
      n = n.parentElement; profondeur++;
    }
    out.push({
      valeur: texte.slice(0, 24),
      portee: n && n !== document.body
        ? (n.className || n.tagName || '').toString().slice(0, 40) : null,
      marques: marques || [],
    });
  }
  return out;
}
"""


def classer_chiffres(par_chiffre: list) -> dict:
    """Repartit les chiffres releves en trois familles. Fonction PURE — c'est
    par elle que les temoins passent, sinon ils eprouveraient une copie.

    - ``date_faux`` : une marque de la portee AFFIRME encore la fraicheur. Le
      chiffre n'est pas seulement vieux, il se presente comme frais — c'est le
      seul cas franchement dangereux, et il prime sur tout le reste ;
    - ``date``      : une marque porte un age (`.vx-update[data-ts]`, dont le
      texte est recalcule) ou un etat degrade — le chiffre est situe dans le
      temps ;
    - ``nu``        : rien dans la portee ne dit quand ce chiffre a ete etabli.
      Une banniere « Demo » qualifie la NATURE de la donnee, pas son age : elle
      ne suffit pas.
    """
    faux, date, nu = [], [], []
    for c in par_chiffre:
        etats = [m['etat'] for m in c['marques'] if m['genre'] == 'etat']
        if any(e in REVENDIQUE_FRAIS for e in etats):
            faux.append(c)
        elif (any(e in ETATS_HONNETES for e in etats)
                or any(m['datable'] for m in c['marques'])):
            date.append(c)
        else:
            nu.append(c)
    return {'date_faux': faux, 'date': date, 'nu': nu}


#: Vieillissement : 12 s hors ligne ne PERIME rien — au sens des seuils du
#: produit (20 s live / 30 min analyse), une donnee de 12 s est fraiche, et une
#: puce qui dit « Analyse » dit vrai. Le mensonge n'apparait qu'au-dela du
#: seuil. On ne peut pas attendre 35 minutes par page : on avance l'horloge de
#: la page, exactement comme les lots 62-64 vieillissaient les reponses en vol.
#: Ce que cela met a l'epreuve n'est pas le calcul de `assess` (teste ailleurs)
#: mais une propriete du RENDU : la puce est-elle re-evaluee sans donnee
#: nouvelle, ou figee a la peinture ?
DECALAGE_HORLOGE = r"""
(ms) => {
  const vrai = Date.now;
  const D = window.Date;
  const F = function (...a) {
    return a.length ? new D(...a) : new D(vrai.call(D) + ms);
  };
  F.now = () => vrai.call(D) + ms;
  F.parse = D.parse; F.UTC = D.UTC; F.prototype = D.prototype;
  window.Date = F;
  return F.now() - vrai.call(D);
}
"""

#: Les pages temoins doivent porter un element que la sonde SAIT lire —
#: sinon le temoin echoue pour la mauvaise raison. C'est ce qui s'est produit
#: au premier essai : la sonde cherche `.vx-kpi-value`, la page n'avait que des
#: `<p>`, et l'outil a refuse de mesurer. Il a eu raison : mieux vaut un
#: instrument qui s'arrete qu'un instrument qui mesure du vide.
PAGE_MUETTE = ('<!doctype html><html><body>'
               '<span class="vx-kpi-value">123,45</span>'
               '<p>Tout va bien</p></body></html>')
PAGE_PARLANTE = ('<!doctype html><html><body>'
                 '<span class="vx-kpi-value">123,45</span>'
                 '<p>Hors ligne — donnees non rafraichies</p></body></html>')

#: Temoin de la classification par chiffre : les TROIS familles a la fois, sur
#: une meme page. Un temoin qui n'en porterait qu'une laisserait passer un
#: classeur qui range tout dans cette famille-la.
PAGE_TROIS_CAS = (
    '<!doctype html><html><body>'
    '<div class="carte"><span class="vx-kpi-value">9,99</span>'
    '<span class="vx-fresh-chip" data-state="stale">À actualiser</span></div>'
    '<div class="carte"><span class="vx-kpi-value">1,11</span>'
    '<span class="vx-fresh-chip" data-state="live">Live</span></div>'
    #  Le quatrieme cas est celui qui a fait tomber la premiere version : une
    #  banniere qui qualifie la NATURE de la donnee, sans aucun age. Elle doit
    #  ressortir NUE, pas datee.
    '<div class="carte"><span class="vx-kpi-value">3,33</span>'
    '<span class="vx-freshness" data-live="fallback">Démo</span></div>'
    '<div class="carte"><span class="vx-kpi-value">2,22</span></div>'
    '</body></html>')


def _temoins(nav) -> list:
    e = []
    ctx = nav.new_context(viewport={'width': LARGEUR, 'height': 900},
                          service_workers='block')
    page = ctx.new_page()

    page.set_content(PAGE_MUETTE, wait_until='domcontentloaded')
    if page.evaluate(SONDE_AVEU, list(AVEUX))['aveux_trouves']:
        e.append('TEMOIN NEGATIF ROMPU : une page qui n\'avoue RIEN ressort '
                 'comme avouant — le detecteur trouverait un aveu partout')

    page.set_content(PAGE_PARLANTE, wait_until='domcontentloaded')
    if not page.evaluate(SONDE_AVEU, list(AVEUX))['aveux_trouves']:
        e.append('TEMOIN MUET : une page qui dit « Hors ligne » n\'est pas vue '
                 'comme avouant — la mesure ne mesure rien')

    if not page.evaluate(SONDE_CHIFFRES):
        e.append('TEMOIN MUET (chiffres) : aucune valeur relevee sur une page '
                 'qui en porte une — on ne saura pas si les chiffres restent')

    #  Temoins de la classification PAR CHIFFRE. Ils passent par la sonde ET
    #  par `classer_chiffres` — eprouver une copie ne prouverait rien.
    page.set_content(PAGE_TROIS_CAS, wait_until='domcontentloaded')
    cl = classer_chiffres(page.evaluate(SONDE_PAR_CHIFFRE, list(ETATS_HONNETES)))
    for famille, attendu in (('date', ['9,99']), ('date_faux', ['1,11']),
                             ('nu', ['3,33', '2,22'])):
        vus = [c['valeur'] for c in cl[famille]]
        if vus != attendu:
            e.append('TEMOIN ROMPU (%s) : attendu %s, obtenu %s — la '
                     'classification par chiffre ne discrimine pas'
                     % (famille, attendu, vus))

    #  Temoin de l'horloge : sans lui, un vieillissement sans effet serait lu
    #  comme « le produit tient », alors que c'est l'instrument qui n'a rien
    #  vieilli.
    decale = page.evaluate(DECALAGE_HORLOGE, 7200000)
    if decale < 7100000:
        e.append('TEMOIN ROMPU (horloge) : le decalage demande de 2 h n\'a pas '
                 'pris (%d ms) — tout vieillissement mesure serait faux' % decale)
    ctx.close()
    return e


#: Periode du re-datage servi (`vx-core.js`, tache « freshness-retick »). La
#: fenetre d'observation apres vieillissement doit la DEPASSER : mesurer 26 s
#: apres avoir vieilli de 2 h reprochait au produit un mensonge qu'il n'avait
#: pas encore eu l'occasion de corriger. Lue dans la source, jamais recopiee.
def periode_retick_s() -> int:
    src = (RACINE / 'vertex/static/vertex/js/vx-core.js').read_text(encoding='utf-8')
    import re as _re
    m = _re.search(r"_retick\(\),\s*(\d+),\s*'freshness-retick'", src)
    if not m:
        raise SystemExit('periode de re-datage introuvable dans vx-core.js — '
                         'l\'instrument ne peut pas choisir sa fenetre')
    return int(m.group(1)) // 1000


def mesurer(base: str = BASE_DEFAUT, *, temoins: bool = True,
            attente_s: int = 12) -> dict:
    from playwright.sync_api import sync_playwright
    releves, echecs = [], []
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=_chromium(), args=['--no-sandbox'])
        if temoins:
            echecs = _temoins(nav)
        for ident, href in espaces():
            ctx = nav.new_context(viewport={'width': LARGEUR, 'height': 900},
                                  service_workers='block')
            page = ctx.new_page()
            erreurs = []
            page.on('pageerror', lambda x: erreurs.append(str(x)[:150]))
            page.on('console', lambda m: erreurs.append(m.text[:150])
                    if m.type == 'error' else None)
            page.goto(base.rstrip('/') + href, wait_until='domcontentloaded',
                      timeout=25000)
            page.wait_for_timeout(2000)
            avant_aveu = page.evaluate(SONDE_AVEU, list(AVEUX))
            avant_chiffres = page.evaluate(SONDE_CHIFFRES)

            #  LE RESEAU TOMBE. On laisse les rafraichissements echouer.
            ctx.set_offline(True)
            page.wait_for_timeout(attente_s * 1000)
            apres_aveu = page.evaluate(SONDE_AVEU, list(AVEUX))
            apres_chiffres = page.evaluate(SONDE_CHIFFRES)
            cl_court = classer_chiffres(
                page.evaluate(SONDE_PAR_CHIFFRE, list(ETATS_HONNETES)))

            #  SECONDE PHASE — le reseau est toujours coupe, mais la donnee a
            #  desormais 2 h : elle est perimee au sens des seuils du produit
            #  lui-meme (30 min). Ce que dit l'ecran maintenant n'a plus
            #  d'excuse.
            page.evaluate(DECALAGE_HORLOGE, 7200000)
            page.wait_for_timeout(max(attente_s, periode_retick_s() + 8) * 1000)
            vieilli_aveu = page.evaluate(SONDE_AVEU, list(AVEUX))
            cl_vieilli = classer_chiffres(
                page.evaluate(SONDE_PAR_CHIFFRE, list(ETATS_HONNETES)))
            ctx.close()

            restes = [c for c in apres_chiffres if c in avant_chiffres]
            releves.append({
                'espace': ident,
                'avoue_avant': avant_aveu['aveux_trouves'],
                'avoue_apres': apres_aveu['aveux_trouves'],
                'nouvel_aveu': sorted(set(apres_aveu['aveux_trouves'])
                                      - set(avant_aveu['aveux_trouves'])),
                'chiffres_avant': len(avant_chiffres),
                'chiffres_apres': len(apres_chiffres),
                'chiffres_restes': len(restes),
                'puces': apres_aveu['puces'][:6],
                'erreurs': erreurs[:6],
                'erreurs_total': len(erreurs),
                #  Par chiffre, aux deux ages.
                'court_date': len(cl_court['date']),
                'court_date_faux': len(cl_court['date_faux']),
                'court_nu': len(cl_court['nu']),
                'vieilli_date': len(cl_vieilli['date']),
                'vieilli_date_faux': len(cl_vieilli['date_faux']),
                'vieilli_nu': len(cl_vieilli['nu']),
                'vieilli_aveux': vieilli_aveu['aveux_trouves'],
                'exemples_faux': [{'valeur': c['valeur'],
                                   'marques': [m['etat'] for m in c['marques']]}
                                  for c in cl_vieilli['date_faux'][:4]],
                'exemples_nus': [c['valeur'] for c in cl_vieilli['nu'][:4]],
            })
        nav.close()

    muets = [r['espace'] for r in releves if not r['avoue_apres']]
    return {
        'base': base, 'attente_s': attente_s,
        'echecs_temoins': echecs, 'releves': releves,
        'espaces_muets': muets,
        'espaces_avec_nouvel_aveu': [r['espace'] for r in releves if r['nouvel_aveu']],
        'chiffres_restes_total': sum(r['chiffres_restes'] for r in releves),
        'erreurs_total': sum(r['erreurs_total'] for r in releves),
        #  Le chiffre qui compte : combien de valeurs restent affichees sous une
        #  marque qui affirme encore la fraicheur, alors que la donnee a 2 h.
        'faux_vieillis': sum(r['vieilli_date_faux'] for r in releves),
        'nus_vieillis': sum(r['vieilli_nu'] for r in releves),
        'dates_vieillis': sum(r['vieilli_date'] for r in releves),
    }


def rendre_texte(r: dict) -> str:
    o = ['QUAND LE RESEAU TOMBE, LE PRODUIT LE DIT-IL ?',
         '=' * 68,
         'base : %s   coupure maintenue %d s' % (r['base'], r['attente_s']), '']
    entete = '%-14s %-10s %-10s %-9s %s' % ('espace', 'chiffres', 'restes',
                                            'erreurs', 'aveu apres coupure')
    o.append(entete)
    o.append('-' * len(entete))
    for x in r['releves']:
        o.append('%-14s %-10d %-10d %-9d %s'
                 % (x['espace'], x['chiffres_apres'], x['chiffres_restes'],
                    x['erreurs_total'],
                    ', '.join(x['avoue_apres'][:3]) or '— AUCUN —'))
    o.append('')
    o.append('ESPACES MUETS (aucun aveu apres coupure) : %d/%d  %s'
             % (len(r['espaces_muets']), len(r['releves']),
                ', '.join(r['espaces_muets']) or ''))
    o.append('ESPACES AVEC UN NOUVEL AVEU               : %d/%d  %s'
             % (len(r['espaces_avec_nouvel_aveu']), len(r['releves']),
                ', '.join(r['espaces_avec_nouvel_aveu']) or ''))
    o.append('CHIFFRES ENCORE AFFICHES apres coupure    : %d'
             % r['chiffres_restes_total'])
    o.append('')
    o.append('LECTURE : un chiffre qui reste sans dire qu\'il est perime est PIRE')
    o.append('qu\'un ecran vide. Ce que la mesure verifie, c\'est que l\'ecran')
    o.append('l\'AVOUE — pas qu\'il se vide.')
    o.append('')
    o.append('PAR CHIFFRE, RESEAU COUPE ET DONNEE VIEILLIE DE 2 H')
    o.append('(a 12 s une donnee est FRAICHE au sens des seuils du produit :')
    o.append(' 20 s live / 30 min analyse. Le mensonge ne peut apparaitre')
    o.append(' qu\'au-dela du seuil — c\'est pourquoi on vieillit.)')
    o.append('')
    e2 = '%-14s %-24s %s' % ('espace', 'a 12 s (date/faux/nu)',
                             'a 2 h (date/faux/nu)')
    o.append(e2)
    o.append('-' * len(e2))
    for x in r['releves']:
        o.append('%-14s %-24s %s'
                 % (x['espace'],
                    '%d / %d / %d' % (x['court_date'], x['court_date_faux'],
                                      x['court_nu']),
                    '%d / %d / %d' % (x['vieilli_date'], x['vieilli_date_faux'],
                                      x['vieilli_nu'])))
    o.append('')
    o.append('A 2 H, RESEAU COUPE : %d chiffres sont DATES · %d sont DATES FAUX '
             '(marque affirmant encore la fraicheur) · %d sont NUS (rien ne dit '
             'quand ils ont ete etablis)'
             % (r['dates_vieillis'], r['faux_vieillis'], r['nus_vieillis']))
    for x in r['releves']:
        if x['exemples_faux'] or x['exemples_nus']:
            o.append('')
            o.append('   %s :' % x['espace'])
            for c in x['exemples_faux']:
                o.append('      DATE FAUX  %-16s marques=%s'
                         % (c['valeur'], ','.join(c['marques']) or '—'))
            for v in x['exemples_nus']:
                o.append('      NU         %s' % v)
    for x in r['releves']:
        if x['puces']:
            o.append('')
            o.append('   %s — puces de fraicheur apres coupure :' % x['espace'])
            for p in x['puces'][:4]:
                o.append('      [%s] %s' % (p['etat'] or '—', p['texte']))
            break
    return '\n'.join(o)


def main() -> int:
    #  L'AVEU avant la mesure. Sans lui, l'outil sortait en code 1 avec
    #  26 lignes de trace Playwright et zero ligne utile — ce qui se lit
    #  « le produit a plante », l'inverse exact de la verite.
    if not navigateur_pret():
        return abandonner_sans_navigateur()
    base = BASE_DEFAUT
    if '--base' in sys.argv:
        base = sys.argv[sys.argv.index('--base') + 1]
    r = mesurer(base)
    if r['echecs_temoins']:
        for x in r['echecs_temoins']:
            print('TEMOIN MUET : %s' % x, file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2, ensure_ascii=False) if '--json' in sys.argv
          else rendre_texte(r))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
