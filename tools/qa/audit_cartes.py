# -*- coding: utf-8 -*-
"""tools/qa/audit_cartes.py — audit COMPLET du logiciel, page par page, carte par carte.

Ouvre chaque page et chaque sous-vue de Vertex dans un vrai Chromium
(Playwright), à deux largeurs (1600 et 390 px), contre l'instance QA
(`VERTEX_MESURE_BASE`, défaut http://127.0.0.1:5003 — sans IBKR, sans code
d'accès), et relève pour chacune :

- statut HTTP de la page et requêtes réseau en échec (>= 400) ;
- erreurs console et exceptions de page ;
- squelettes encore affichés après stabilisation (`.vx-skeleton`) : une carte
  jamais remplie ;
- états d'erreur rendus (`.vx2-state[data-kind="error"]`, `.vx-state-error`) ;
- cartes (`section.vx-card`, `.vx2-surface`) au corps vide ;
- débordement horizontal du document (largeur du contenu > viewport) ;
- entrées `/api/client-log` accumulées pendant l'audit.

Rien n'est corrigé ici : le script MESURE et écrit un rapport JSON + Markdown.
Lecture seule, aucun ordre, aucune donnée de compte.

    python tools/qa/audit_cartes.py [--base URL] [--largeurs 1600,390] [--attente 6]
                                    [--json rapport.json] [--md rapport.md] [--seul /markets]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

#: Symboles servis dans les caches du dépôt (scan et board) : le dossier d'un
#: titre absent serait un test de l'état « hors scan », pas de la fiche.
SYM = os.environ.get('VERTEX_AUDIT_SYM', 'NVDA')


def pages() -> list[tuple[str, str]]:
    """(libellé, chemin) pour chaque page et sous-vue réellement servie —
    énumérées depuis les modules de page, jamais recopiées à la main."""
    out: list[tuple[str, str]] = [('Aujourd’hui', '/')]
    from vertex.ui.pages import (calendar_page, markets_page, opportunities_page, options_intel_page,
                                 performance_page, portfolio_page, simulator_page, tracking_page,
                                 system_page)
    for nom, chemin, mod in (('Calendrier', '/calendar', calendar_page), ('Marchés', '/markets', markets_page),
                             ('Opportunités', '/opportunities', opportunities_page),
                             ('Options', '/options', options_intel_page),
                             ('Simulateur', '/simulator', simulator_page),
                             ('Portefeuille', '/portfolio', portfolio_page),
                             ('Suivi', '/tracking', tracking_page),
                             ('Performance', '/performance', performance_page),
                             ('Système', '/system', system_page)):
        vues = getattr(mod, '_VIEWS', None) or getattr(mod, 'VIEWS', None) or ()
        if vues:
            for vid, _label in vues:
                out.append(('%s › %s' % (nom, vid), '%s?view=%s' % (chemin, vid)))
        else:
            out.append((nom, chemin))
    out += [('Analyse %s' % SYM, '/analysis/%s' % SYM),
            ('Options › dossier %s' % SYM, '/options/dossier/%s' % SYM),
            ('Vertex IA', '/intelligence')]
    return out


JS_RELEVE = r"""
() => {
  const W = document.documentElement.clientWidth;
  const vis = (el) => !!(el.offsetParent !== null || el.getClientRects().length);
  const squelettes = [...document.querySelectorAll('.vx-skeleton')].filter(vis);
  const erreurs = [...document.querySelectorAll('.vx2-state[data-kind="error"], .vx-state-error, .vx-state[data-kind="error"]')].filter(vis)
    .map(e => (e.innerText || '').trim().slice(0, 140));
  const cartes = [...document.querySelectorAll('section.vx-card, .vx2-surface, .vx-card')].filter(vis);
  /* textContent, pas innerText : les cartes hors écran en `content-visibility:auto`
     ne sont pas rendues et leur innerText est vide (faux positif mesuré). */
  const vides = cartes.filter(c => (c.textContent || '').trim().length === 0 && !c.querySelector('svg,canvas,img,input,table'))
    .map(c => (c.id || c.getAttribute('aria-label') || c.className.toString().slice(0, 40)));
  const squelettesHotes = squelettes.map(s => {
    const c = s.closest('section, .vx-card, .vx2-surface, [id]');
    return c ? (c.id || c.getAttribute('aria-label') || c.className.toString().slice(0, 40)) : '?';
  });
  const deb = [...document.querySelectorAll('body *')].filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.right > W + 1 && vis(el) && getComputedStyle(el).position !== 'fixed'
      && !el.closest('.vx-drawer, .vx-drawer-panel, [aria-hidden="true"], .vx2-tabs, .vx2-tabbar, nav');
  }).slice(0, 6).map(el => (el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + el.className.toString().split(' ')[0]));
  return {
    viewport: W, scrollW: document.documentElement.scrollWidth, bodyScrollW: document.body.scrollWidth,
    cartes: cartes.length, vides, squelettes: squelettesHotes, erreurs, deb,
    titre: document.title, absents: (document.body.innerText.match(/Aucune donnée/g) || []).length,
    nd: (document.body.innerText.match(/\bn\/d\b/g) || []).length
  };
}
"""



def _normaliser_seul(seul: str) -> str:
    """Rend un filtre de chemin utilisable depuis n'importe quel shell.

    Mesuré le 2026-09-06 : lancé depuis Git Bash, `--seul /markets` arrive au
    programme sous la forme `C:/Program Files/Git/markets` (conversion de
    chemin MSYS), et le filtre ne retenait AUCUNE page — sans rien dire. Un
    outil de mesure qui rend « 0 page » au lieu d'un refus est pire qu'inutile.
    """
    s = (seul or '').replace(chr(92), '/')
    for jeton in ('/Git/', '/git/'):
        if jeton in s:
            s = '/' + s.split(jeton, 1)[1]
    if not s.startswith('/'):
        s = '/' + s
    return s

def auditer(base: str, largeurs: list[int], attente: float, seul: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    liste = pages()
    if seul:
        motif = _normaliser_seul(seul)
        liste = [(n, c) for n, c in liste if c.startswith(motif) or motif in c]
    rapport = {'base': base, 'debut': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'largeurs': largeurs, 'pages': []}
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        for largeur in largeurs:
            ctx = nav.new_context(viewport={'width': largeur, 'height': 1000}, locale='fr-CH',
                                  timezone_id='Europe/Zurich')
            page = ctx.new_page()
            #  Un seul jeu d'écouteurs par page Playwright ; les listes sont
            #  vidées entre deux relevés (les écouteurs ne s'accumulent pas).
            console: list = []
            exceptions: list = []
            reseau: list = []
            page.on('console', lambda m: console.append(m.text[:200]) if m.type == 'error' else None)
            page.on('pageerror', lambda e: exceptions.append(str(e)[:200]))
            page.on('response', lambda r: reseau.append('%s %s' % (r.status, r.url[-90:])) if r.status >= 400 else None)
            for libelle, chemin in liste:
                console.clear(); exceptions.clear(); reseau.clear()
                t0 = time.time()
                try:
                    rep = page.goto(base + chemin, wait_until='domcontentloaded', timeout=45000)
                    statut = rep.status if rep else None
                    try:
                        page.wait_for_load_state('networkidle', timeout=15000)
                    except Exception:  # noqa: BLE001 — SSE ou sondage : jamais « idle », on attend le délai
                        pass
                    page.wait_for_timeout(int(attente * 1000))
                    releve = page.evaluate(JS_RELEVE)
                except Exception as exc:  # noqa: BLE001
                    statut, releve = None, {'exception_audit': str(exc)[:200]}
                rapport['pages'].append({
                    'page': libelle, 'chemin': chemin, 'largeur': largeur, 'statut': statut,
                    'duree_s': round(time.time() - t0, 1), 'console': console[:8], 'exceptions': exceptions[:5],
                    'reseau_echecs': sorted(set(reseau))[:10], **releve})
            ctx.close()
        nav.close()
    try:
        with urllib.request.urlopen(base + '/api/client-log', timeout=8) as r:
            rapport['client_log'] = json.loads(r.read().decode('utf-8'))
    except Exception as exc:  # noqa: BLE001
        rapport['client_log'] = {'erreur': str(exc)[:120]}
    rapport['fin'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    return rapport


def defauts(r: dict) -> list[dict]:
    out = []
    for pg in r['pages']:
        probs = []
        if pg.get('statut') not in (200,):
            probs.append('statut %s' % pg.get('statut'))
        if pg.get('exception_audit'):
            probs.append('audit : ' + pg['exception_audit'])
        if pg.get('console'):
            probs.append('console : ' + ' | '.join(pg['console'][:3]))
        if pg.get('exceptions'):
            probs.append('exception : ' + ' | '.join(pg['exceptions'][:2]))
        if pg.get('reseau_echecs'):
            probs.append('réseau : ' + ' | '.join(pg['reseau_echecs'][:4]))
        if pg.get('squelettes'):
            probs.append('squelettes : ' + ', '.join(sorted(set(pg['squelettes']))[:6]))
        if pg.get('erreurs'):
            probs.append('états d’erreur : ' + ' | '.join(pg['erreurs'][:3]))
        if pg.get('vides'):
            probs.append('cartes vides : ' + ', '.join(pg['vides'][:6]))
        if pg.get('bodyScrollW', 0) > (pg.get('viewport') or 0) + 1:
            probs.append('débordement %s > %s (%s)' % (pg.get('bodyScrollW'), pg.get('viewport'), ', '.join(pg.get('deb') or [])))
        if probs:
            out.append({'page': pg['page'], 'chemin': pg['chemin'], 'largeur': pg['largeur'], 'problemes': probs})
    return out


def markdown(r: dict) -> str:
    d = defauts(r)
    lignes = ['# VERTEX_AUDIT_CARTES — audit navigateur complet',
              '', 'Base : `%s` · %s → %s · largeurs %s · %d relevés (%d pages × %d largeurs).' % (
                  r['base'], r['debut'], r['fin'], r['largeurs'], len(r['pages']),
                  len(r['pages']) // max(1, len(r['largeurs'])), len(r['largeurs'])),
              '', '## Relevés avec un problème (%d)' % len(d), '',
              '| Page | Largeur | Problèmes |', '|---|---|---|']
    for x in d:
        lignes.append('| %s (`%s`) | %d | %s |' % (x['page'], x['chemin'], x['largeur'], ' ; '.join(x['problemes']).replace('|', '/')))
    lignes += ['', '## Tous les relevés', '', '| Page | Largeur | Statut | Cartes | Squelettes | Erreurs | Vides | « Aucune donnée » | n/d | Durée |', '|---|---|---|---|---|---|---|---|---|---|']
    for pg in r['pages']:
        lignes.append('| %s | %d | %s | %s | %d | %d | %d | %s | %s | %s s |' % (
            pg['page'], pg['largeur'], pg.get('statut'), pg.get('cartes', '?'), len(pg.get('squelettes') or []),
            len(pg.get('erreurs') or []), len(pg.get('vides') or []), pg.get('absents', '?'), pg.get('nd', '?'), pg.get('duree_s')))
    cl = r.get('client_log')
    if isinstance(cl, dict):
        #  MESURE (6 sept. 2026) : cette ligne lisait `items`/`entries`/`logs`,
        #  trois clés que le serveur n'a JAMAIS servies (`git log -S` : un seul
        #  commit, forme {count, errors} depuis toujours). Elle rendait donc
        #  « 0 entrée(s) » quoi qu'il arrive — y compris sur 5 erreurs JS
        #  réelles, et y compris quand le relevé lui-même avait échoué
        #  ({'erreur': 'HTTP Error 502'}, posé plus haut). Un zéro constant qui
        #  avale l'échec de mesure et le présente comme un résultat propre :
        #  l'invariant 5 (zéro, absent et erreur restent distincts) enfreint
        #  dans la couche de PREUVE. La lecture s'aligne sur `rc_short_audit.js`
        #  (`clientLog.count ?? (clientLog.errors || []).length`), déjà correct.
        if cl.get('erreur'):
            lignes += ['', '`/api/client-log` : NON MESURÉ — %s.' % cl['erreur']]
        else:
            n = (cl['count'] if isinstance(cl.get('count'), int)
                 else len(cl.get('errors') or []))
            lignes += ['', '`/api/client-log` : %d entrée(s) pendant l’audit.' % n]
            if n:
                #  Une preuve à zéro doit pouvoir devenir une preuve à N lisible.
                lignes += ['', '```',
                           json.dumps(cl.get('errors') or [], ensure_ascii=False, indent=1),
                           '```']
    return '\n'.join(lignes) + '\n'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--base', default=os.environ.get('VERTEX_MESURE_BASE', 'http://127.0.0.1:5003'))
    ap.add_argument('--largeurs', default='1600,390')
    ap.add_argument('--attente', type=float, default=6.0)
    ap.add_argument('--json', default=None)
    ap.add_argument('--md', default=None)
    ap.add_argument('--seul', default=None)
    a = ap.parse_args()
    r = auditer(a.base, [int(x) for x in a.largeurs.split(',')], a.attente, a.seul)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    md = markdown(r)
    if a.md:
        with open(a.md, 'w', encoding='utf-8') as f:
            f.write(md)
    d = defauts(r)
    print('relevés : %d · avec problème : %d' % (len(r['pages']), len(d)))
    for x in d:
        print('- %s @%d : %s' % (x['page'], x['largeur'], ' ; '.join(x['problemes'])[:300]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
