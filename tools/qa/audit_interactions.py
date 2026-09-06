# -*- coding: utf-8 -*-
"""tools/qa/audit_interactions.py — audit des INTERACTIONS, page par page.

Complète `audit_cartes.py` (qui mesure l'affichage) : ici, sur chaque page et
sous-vue, on clique chaque bouton, onglet, puce et lien de filtre VISIBLE et on
relève ce que la page fait : erreurs console, exceptions, requêtes en échec,
apparition d'un état d'erreur, page qui ne répond plus. Chromium (Playwright)
contre l'instance QA (sans IBKR, sans code d'accès).

Garde-fous : aucun clic sur une commande qui modifie le desk ou lance une
collecte lourde (Clôturer, Supprimer, Effacer, Réinitialiser, Importer,
Exporter, Enregistrer, Déclarer, Ajouter, Lancer un scan, Mettre à jour avec
Claude), aucune soumission de formulaire, aucun lien externe ; les modales et
tiroirs ouverts sont refermés (Échap). Lecture seule.

    python tools/qa/audit_interactions.py [--base URL] [--largeur 1280] [--max 40]
                                          [--json rapport.json] [--seul /markets]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from tools.qa.audit_cartes import pages  # noqa: E402

INTERDITS = re.compile(r"cl[ôo]turer|supprimer|effacer|r[ée]initialiser|importer|exporter|enregistrer|"
                       r"d[ée]clarer|ajouter|lancer un scan|rescan|mettre [àa] jour avec claude|"
                       r"envoyer|valider|confirmer|purger|vider|archiver|se d[ée]connecter", re.I)

JS_CIBLES = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && el.offsetParent !== null; };
  const sel = 'button, [role="button"], a.vx2-tab, a.vx-btn, .vx-chip, [data-view-tab], [data-cal-horizon], [data-tf], summary';
  const out = [];
  document.querySelectorAll(sel).forEach((el, i) => {
    if (!vis(el)) return;
    if (el.closest('form') && el.getAttribute('type') === 'submit') return;
    if (el.tagName === 'A') {
      const h = el.getAttribute('href') || '';
      if (!h || h.startsWith('http') || h.startsWith('mailto') || el.getAttribute('target') === '_blank') return;
    }
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return;
    el.setAttribute('data-audit-idx', String(i));
    out.push({ idx: i, tag: el.tagName.toLowerCase(), texte: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().slice(0, 50), href: el.getAttribute('href') || '' });
  });
  return out;
}
"""

JS_ETAT = r"""
() => ({
  erreurs: [...document.querySelectorAll('.vx2-state[data-kind="error"], .vx-state-error')].filter(e => e.offsetParent !== null).length,
  url: location.pathname + location.search
})
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

def auditer(base: str, largeur: int, maxi: int, seul: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    liste = pages()
    if seul:
        motif = _normaliser_seul(seul)
        liste = [(n, c) for n, c in liste if c.startswith(motif) or motif in c]
    rapport = {'base': base, 'largeur': largeur, 'debut': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'pages': []}
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        ctx = nav.new_context(viewport={'width': largeur, 'height': 1000}, locale='fr-CH', timezone_id='Europe/Zurich')
        page = ctx.new_page()
        console: list = []
        exceptions: list = []
        reseau: list = []
        page.on('console', lambda m: console.append(m.text[:160]) if m.type == 'error' else None)
        page.on('pageerror', lambda e: exceptions.append(str(e)[:160]))
        page.on('response', lambda r: reseau.append('%s %s' % (r.status, r.url[-80:])) if r.status >= 400 else None)
        for libelle, chemin in liste:
            resultat = {'page': libelle, 'chemin': chemin, 'clics': 0, 'ignores': 0, 'problemes': []}
            try:
                page.goto(base + chemin, wait_until='domcontentloaded', timeout=45000)
                page.wait_for_timeout(4000)
                cibles = page.evaluate(JS_CIBLES)
            except Exception as exc:  # noqa: BLE001
                resultat['problemes'].append('ouverture : %s' % str(exc)[:120])
                rapport['pages'].append(resultat)
                continue
            for c in cibles[:maxi]:
                if INTERDITS.search(c['texte']):
                    resultat['ignores'] += 1
                    continue
                console.clear(); exceptions.clear(); reseau.clear()
                avant = page.evaluate(JS_ETAT)
                try:
                    loc = page.locator('[data-audit-idx="%d"]' % c['idx'])
                    if loc.count() == 0:
                        continue
                    loc.first.click(timeout=3000, no_wait_after=True)
                    page.wait_for_timeout(900)
                    page.keyboard.press('Escape')
                    page.wait_for_timeout(150)
                    apres = page.evaluate(JS_ETAT)
                    resultat['clics'] += 1
                    etiquette = '%s « %s »' % (c['tag'], c['texte'] or c['href'])
                    if exceptions:
                        resultat['problemes'].append('%s → exception : %s' % (etiquette, exceptions[0]))
                    if console:
                        resultat['problemes'].append('%s → console : %s' % (etiquette, console[0]))
                    if reseau:
                        resultat['problemes'].append('%s → réseau : %s' % (etiquette, ', '.join(sorted(set(reseau))[:3])))
                    if apres['erreurs'] > avant['erreurs']:
                        resultat['problemes'].append('%s → état d’erreur affiché' % etiquette)
                    if apres['url'] != avant['url']:
                        # navigation : on revient à la page auditée
                        page.goto(base + chemin, wait_until='domcontentloaded', timeout=45000)
                        page.wait_for_timeout(2500)
                        page.evaluate(JS_CIBLES)
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc).splitlines()[0][:120]
                    if 'Timeout' in msg or 'not visible' in msg or 'intercepts' in msg:
                        resultat['ignores'] += 1
                    else:
                        resultat['problemes'].append('%s → clic impossible : %s' % (c['texte'], msg))
                    try:
                        page.goto(base + chemin, wait_until='domcontentloaded', timeout=45000)
                        page.wait_for_timeout(2000)
                        page.evaluate(JS_CIBLES)
                    except Exception:  # noqa: BLE001
                        break
            rapport['pages'].append(resultat)
        ctx.close()
        nav.close()
    rapport['fin'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    return rapport


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--base', default=os.environ.get('VERTEX_MESURE_BASE', 'http://127.0.0.1:5003'))
    ap.add_argument('--largeur', type=int, default=1280)
    ap.add_argument('--max', type=int, default=40)
    ap.add_argument('--json', default=None)
    ap.add_argument('--seul', default=None)
    a = ap.parse_args()
    r = auditer(a.base, a.largeur, a.max, a.seul)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    total = sum(x['clics'] for x in r['pages'])
    probs = [x for x in r['pages'] if x['problemes']]
    print('pages : %d · clics : %d · pages avec problème : %d' % (len(r['pages']), total, len(probs)))
    for x in probs:
        for pb in x['problemes'][:6]:
            print('- %s : %s' % (x['page'], pb[:220]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
