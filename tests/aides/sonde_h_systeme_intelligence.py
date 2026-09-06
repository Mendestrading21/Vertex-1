"""Relevé navigateur des pages Système et Vertex IA. Sortie : une ligne JSON.

DANS UN SOUS-PROCESSUS, et c'est nécessaire : `ib_async` applique
`nest_asyncio`, ce qui fait croire à Playwright qu'une boucle asyncio tourne —
son API synchrone refuse alors de démarrer dans le processus de test (même
raison, même remède que `sonde_boutons_morts.py`).

La sonde ne juge rien : elle rapporte des grandeurs et des textes. Les seuils
et les comparaisons vivent dans `tests/test_h_systeme_intelligence.py`.

`VERTEX_MESURE_BASE` désigne l'instance de MESURE (copie QA, sans code
d'accès). Le défaut vise 5003 délibérément : 5002 est l'instance réelle,
branchée sur le courtier, et une sonde n'a rien à y faire.
"""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from playwright.sync_api import sync_playwright  # noqa: E402

from tools.mesures.mesurer_qa_espaces import _chromium  # noqa: E402

BASE = os.environ.get('VERTEX_MESURE_BASE', 'http://127.0.0.1:5003')

#: Largeurs imposées par la doctrine d'interface, plus 1440 — la plus dégradée
#: au relevé du 6 sept. 2026 (16 éléments en débordement dans la bande KPI).
LARGEURS = (1600, 1440, 1024, 390)

VUES_IA = ('analyst', 'brief', 'committee', 'decisions',
           'research', 'memory', 'strategy', 'impacts')

#: Ce que rend `/healthz` dans chaque cas éprouvé. Le premier est le seul qui
#: AFFIRME quelque chose ; les autres se taisent, se contredisent ou se
#: déclarent en panne.
#:
#: Les deux derniers sont les BORDS du partage : une clé de verdict PRÉSENTE
#: mais vide de sens. `{"status":""}` n'affirme pas plus que `{}` — et
#: `{"ok":0}` porte bien la clé `ok`, ce qu'une explication du silence ne peut
#: pas nier.
CAS_HEALTHZ = {
    'affirme_sain': '{"status":"ok"}',
    'muet_vide': '{}',
    'muet_sans_verdict': '{"build":"X"}',
    'affirme_degrade': '{"status":"degraded"}',
    'affirme_ko': '{"ok":false}',
    'status_vide': '{"status":""}',
    'ok_non_booleen': '{"ok":0}',
}

#: Mesure de la bande d'indicateurs de confiance : largeur des tuiles, nombre
#: de rangées et débordements horizontaux RÉELS de ses descendants.
_JS_BANDE = r"""()=>{
 const k=document.getElementById('vx-sys-kpis');
 if(!k)return null;
 const r=[...k.children].map(e=>e.getBoundingClientRect());
 const deb=[...k.querySelectorAll('*')]
   .filter(e=>e.scrollWidth>e.clientWidth+2)
   .map(e=>({q:(typeof e.className==='string'?e.className:e.tagName).slice(0,60),
             sw:e.scrollWidth,cw:e.clientWidth}));
 return {tuiles:r.map(x=>Math.round(x.width)),
         rangees:new Set(r.map(x=>Math.round(x.top))).size,
         debordements:deb,
         page_deborde:document.documentElement.scrollWidth
                      >document.documentElement.clientWidth+1};
}"""

_JS_FRAICHEUR = ("()=>{const f=document.getElementById('vx-ia-fresh');"
                 "return f?f.innerText.replace(/\\s+/g,' ').trim():null;}")

_JS_STOCKAGE = r"""()=>{
 const b=document.getElementById('vx-conn-store-badge');
 const c=document.getElementById('vx-conn-store');
 return {badge:b?b.innerText.replace(/\s+/g,' ').trim():null,
         corps:c?c.innerText.replace(/\s+/g,' ').trim():null};
}"""


def _texte_servi(chemin, ident):
    """Le contenu que le SERVEUR met dans cet élément, avant tout script.

    Sert de témoin : un badge qui affiche encore, une fois la page chargée,
    exactement ce que le serveur y avait posé n'a été peint par personne. On
    le LIT plutôt que de le figer dans le banc — le jour où le libellé de
    départ change, la mesure suit.
    """
    with urllib.request.urlopen(BASE + chemin, timeout=15) as r:
        html = r.read().decode('utf-8', 'replace')
    m = re.search(r'<span id="%s"[^>]*>(.*?)</span>\s*</div>' % ident, html, re.S)
    brut = m.group(1) if m else ''
    brut = re.sub(r'<[^>]+>', ' ', brut)
    brut = (brut.replace('&hellip;', '…').replace('&nbsp;', ' ')
                .replace('&amp;', '&'))
    return re.sub(r'\s+', ' ', brut).strip()


def _attendre(page):
    page.wait_for_timeout(2800)


def relever():
    out = {'base': BASE, 'bande': {}, 'fraicheur': {}, 'stockage': {},
           'console': {}, 'temoin_fraicheur_servi': {}}
    chemin = _chromium()
    kw = {'executable_path': chemin} if chemin else {}
    for vue in VUES_IA:
        out['temoin_fraicheur_servi'][vue] = _texte_servi(
            '/intelligence?view=' + vue, 'vx-ia-fresh')
    with sync_playwright() as pw:
        nav = pw.chromium.launch(args=['--no-sandbox'], **kw)

        #  Le service worker sert une coque MISE EN CACHE : mesurer avec lui,
        #  c'est mesurer une feuille de style d'hier. Il est neutralisé pour
        #  que le relevé porte sur ce que le serveur sert AUJOURD'HUI.
        for largeur in LARGEURS:
            ctx = nav.new_context(viewport={'width': largeur, 'height': 900},
                                  service_workers='block')
            page = ctx.new_page()
            erreurs = []
            page.on('console', lambda m, E=erreurs:
                    E.append(m.type + ': ' + m.text[:160]) if m.type == 'error' else None)
            page.on('pageerror', lambda e, E=erreurs: E.append('pageerror: ' + str(e)[:160]))
            page.goto(BASE + '/system?view=connections', wait_until='load', timeout=30000)
            _attendre(page)
            out['bande'][str(largeur)] = page.evaluate(_JS_BANDE)
            out['console']['systeme@%d' % largeur] = erreurs
            ctx.close()

        ctx = nav.new_context(viewport={'width': 1600, 'height': 900},
                              service_workers='block')
        for vue in VUES_IA:
            page = ctx.new_page()
            erreurs = []
            page.on('console', lambda m, E=erreurs:
                    E.append(m.type + ': ' + m.text[:160]) if m.type == 'error' else None)
            page.on('pageerror', lambda e, E=erreurs: E.append('pageerror: ' + str(e)[:160]))
            page.goto(BASE + '/intelligence?view=' + vue, wait_until='load', timeout=30000)
            _attendre(page)
            out['fraicheur'][vue] = page.evaluate(_JS_FRAICHEUR)
            out['console']['ia@' + vue] = erreurs
            page.close()

        for nom, corps in CAS_HEALTHZ.items():
            page = ctx.new_page()
            page.route('**/healthz',
                       lambda r, _req=None, c=corps: r.fulfill(
                           status=200, content_type='application/json', body=c))
            page.goto(BASE + '/system?view=connections', wait_until='load', timeout=30000)
            _attendre(page)
            page.evaluate("()=>document.querySelectorAll('details').forEach(d=>{d.open=true})")
            page.wait_for_timeout(500)
            out['stockage'][nom] = page.evaluate(_JS_STOCKAGE)
            page.close()
        ctx.close()
        nav.close()
    return out


if __name__ == '__main__':
    #  `ensure_ascii=True` : la sortie standard de Windows est en cp1252 et
    #  refusait « ↔ » (mesuré : la sonde plantait sur le corps de la carte
    #  Stockage). Le banc relit du JSON, il retrouve les caractères intacts.
    print(json.dumps(relever(), ensure_ascii=True))
