# -*- coding: utf-8 -*-
"""tools/qa/audit_graphiques.py — les graphiques DESSINENT-ILS, les widgets AFFICHENT-ILS ?

`audit_cartes.py` mesure la page (statut, erreurs, squelettes, débordements) et
`audit_interactions.py` mesure les commandes. Aucun des deux ne répond à la
question qui compte pour l'utilisateur : **est-ce que le graphique trace une
courbe, et est-ce que le widget montre un chiffre ?** Une carte peut être
présente, sans erreur, sans squelette — et vide.

Cet outil ouvre chaque page et chaque sous-vue dans Chromium et mesure, pour
chacune :

- les CANEVAS (Chart.js et primitives) : dimensions, et surtout le nombre de
  pixels réellement peints (lecture de `getImageData`) — un canevas monté mais
  jamais dessiné est le défaut invisible par excellence ;
- les SVG de graphique : nombre d'éléments de tracé (path, rect, circle, line,
  polyline, polygon) et de libellés ;
- les WIDGETS de valeur (tuiles, indicateurs, lignes clé-valeur) : combien
  portent un chiffre, combien portent un tiret ou « n/d » ;
- l'état déclaré de chaque carte-graphique : dessine-t-elle, ou affiche-t-elle
  un état vide EXPLIQUÉ ? Une carte vide SANS explication est un défaut ; une
  carte vide qui dit pourquoi est un comportement honnête.

Lecture seule : aucun clic, aucune écriture, aucune modification du dépôt.

    python tools/qa/audit_graphiques.py [--base URL] [--largeur 1600] [--attente 7]
                                        [--json rapport.json] [--seul /markets]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from tools.qa.audit_cartes import pages  # noqa: E402

JS_MESURE = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const txt = (el) => (el.innerText || '').replace(/\s+/g, ' ').trim();

  //  Un canevas MONTÉ mais jamais dessiné est indiscernable à l'œil d'une carte
  //  qui charge encore : on compte les pixels réellement peints.
  function pixelsPeints(c) {
    try {
      const ctx = c.getContext('2d');
      if (!ctx || !c.width || !c.height) return 0;
      const d = ctx.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 3; i < d.length; i += 4 * 7) { if (d[i] > 8) n++; }
      return n;
    } catch (e) { return -1; }          // canevas non lisible (taint) : dit, jamais supposé
  }

  const conteneur = (el) => el.closest('section, .vx-card, .vx2-surface, [id]') || el.parentElement;
  const nom = (el) => {
    const c = conteneur(el);
    if (!c) return '?';
    const t = c.querySelector('.vx-card-title, .vx-chart-title, .vx2-card-title');
    return (t && txt(t)) || c.id || c.getAttribute('aria-label') || '?';
  };

  const canevas = [...document.querySelectorAll('canvas')].filter(vis).map((c) => ({
    nom: nom(c), w: Math.round(c.getBoundingClientRect().width),
    h: Math.round(c.getBoundingClientRect().height), pixels: pixelsPeints(c),
  }));

  //  Mesure du 2026-09-06 : la règle « moins de 3 tracés = svg vide » accusait
  //  124 widgets SAINS. Une jauge de score (anneau 78x78) porte exactement DEUX
  //  cercles — piste + arc — et c'est sa forme normale ; un treemap de deux
  //  contrats porte deux rectangles, et le tracé « fantôme » de la page
  //  Performance est un gabarit assumé, annoncé par sa carte. On classe donc le
  //  SVG par FAMILLE avant de juger, au lieu d'appliquer un seuil unique.
  const famille = (s, r) => {
    const carre = Math.abs(r.width - r.height) < 0.25 * Math.max(r.width, r.height);
    if (carre && r.width <= 160) return 'jauge';
    if (s.querySelector('rect') && !s.querySelector('polyline, path[d*=\"L\"]')) return 'aires';
    return 'graphique';
  };
  const svgs = [...document.querySelectorAll('svg')].filter(vis).filter((s) => {
    const r = s.getBoundingClientRect();
    return r.width > 40 && r.height > 30;                 // exclut les icônes
  }).map((s) => {
    const r = s.getBoundingClientRect();
    const hote = s.closest('section, .vx-card, .vx2-surface');
    return {
      nom: nom(s), famille: famille(s, r),
      explique: !!(hote && /aucune (fausse|donnée)|gabarit|exemple|à venir|pas encore|débloqu/i.test(txt(hote))),
      traces: s.querySelectorAll('path, rect, circle, line, polyline, polygon').length,
      libelles: s.querySelectorAll('text').length,
      w: Math.round(r.width), h: Math.round(r.height),
    };
  });

  //  Widgets de valeur : ce que l'utilisateur lit comme un chiffre.
  const CREUX = /^(—|-|–|n\/d|nd|\?|\.\.\.|…|\s*)$/i;
  //  Sélecteurs CALIBRÉS sur le DOM réel (mesure du 2026-09-06 : les valeurs
  //  vivent surtout dans `.v` des lignes clé-valeur, plus les tuiles et les
  //  cellules numériques des tables).
  //  Un tiret EST la représentation honnête d'une absence : le défaut n'est pas
  //  le tiret, c'est le tiret MUET. On mesure donc, pour chaque valeur creuse,
  //  si sa carte hôte porte une explication (état vide, note de bas de carte,
  //  légende « n/d », mention de source ou de fraîcheur).
  const EXPLIQUE = /aucune donnée|indisponible|non calcul|pas encore|insuffisant|non mesur|injoignable|non scanné|à actualiser|n\/d|non déclar|aucune position|source ?:|hors séance|non renseign|à venir|jamais exécut/i;
  const explique = (el) => {
    //  Une explication n'est pas forcément du TEXTE de carte. Mesuré le
    //  2026-09-06 : les tuiles SMI, USD/CHF et ETH d'« Aujourd'hui » portent
    //  `data-absent="1"` et un `title` complet — « SMI n'est pas servi par le
    //  dernier scan (source : yfinance) — aucune valeur n'est estimée à la
    //  place. » — et l'audit les comptait muettes parce qu'il ne lisait que le
    //  texte. Un marqueur explicite et une infobulle SONT des explications ;
    //  ne pas les voir accuse le correctif qui vient d'être fait.
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (n.getAttribute && (n.getAttribute('data-absent')
          || (n.getAttribute('title') || '').length > 12)) return true;
    }
    const c = el.closest('section, .vx-card, .vx2-surface') || el.parentElement;
    if (!c) return false;
    if (EXPLIQUE.test(txt(c))) return true;
    //  Un BADGE d'en-tête est une explication au même titre qu'un pied de
    //  carte : mesuré, la carte des fondamentaux dit « collecte en cours » là,
    //  et l'audit la comptait muette parce qu'il ne regardait que le pied.
    const f = c.querySelector('.vx-card-foot, .vx-card-footer, .vx-help, .vx-meta, .vx-badge');
    return !!(f && txt(f).length > 3);
  };
  //  Mesure du 2026-09-06 : `innerText` est calculé sur le RENDU. Dans un
  //  `<details>` replié, il rend '' alors que `textContent` porte « 513 » — et
  //  Chromium donne quand même une boîte non nulle à ces éléments. L'audit
  //  comptait donc CHAQUE valeur repliée comme creuse : 19 sur 19 pour
  //  « Système › données », dont pas une seule ne l'était. On écarte ce qui
  //  n'est pas affiché, au lieu de le déclarer vide.
  const replie = (el) => {
    const d = el.closest('details');
    return !!(d && !d.open);
  };
  const valeurs = [...document.querySelectorAll(
    '.vx-kv .v, .v, .vx-kpi-value, .vx-metric-v, .vx-tile-v, .vx-stat-v, .vx2-num, ' +
    '.vx-metric-value, .vx-kpi-delta, td.vx-num, .vx-mono')]
    .filter(vis).filter((el) => el.children.length === 0).filter((el) => !replie(el))
    .filter((el) => (el.textContent || '').trim() !== '' || txt(el) !== '')
    .map((el) => ({ nom: nom(el), v: txt(el).slice(0, 24), explique: CREUX.test(txt(el)) ? explique(el) : true }));
  const creux = valeurs.filter((x) => CREUX.test(x.v));

  //  Cartes-graphiques : celles qui contiennent un canevas ou un SVG de taille,
  //  ou qui portent un état vide là où un graphique est attendu.
  const ETAT_VIDE = /aucune donnée|indisponible|non calcul|pas encore|aucun |insuffisant|non mesur|injoignable|non scanné|à actualiser/i;
  const cartes = [...document.querySelectorAll('section.vx-card, .vx2-surface, .vx-card')].filter(vis)
    .map((c) => {
      const cvs = [...c.querySelectorAll('canvas')].filter(vis);
      const sv = [...c.querySelectorAll('svg')].filter((s) => {
        const r = s.getBoundingClientRect(); return r.width > 40 && r.height > 30;
      });
      const t = c.querySelector('.vx-card-title, .vx-chart-title, .vx2-card-title');
      const contenu = txt(c);
      return {
        nom: (t && txt(t)) || c.id || c.getAttribute('aria-label') || '?',
        canevas: cvs.length, svg: sv.length,
        peint: cvs.reduce((n, x) => n + Math.max(0, pixelsPeints(x)), 0)
             + sv.reduce((n, s) => n + s.querySelectorAll('path, rect, circle, line, polyline, polygon').length, 0),
        etat_vide: ETAT_VIDE.test(contenu),
        extrait: contenu.slice(0, 90),
      };
    }).filter((c) => c.canevas || c.svg || c.etat_vide);

  return {
    canevas, svgs, cartes,
    valeurs_total: valeurs.length, valeurs_creuses: creux.length,
    creux_muets: creux.filter((x) => !x.explique).length,
    creux: creux.filter((x) => !x.explique).slice(0, 12),
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

def auditer(base: str, largeur: int, attente: float, seul: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    liste = pages()
    if seul:
        motif = _normaliser_seul(seul)
        liste = [(n, c) for n, c in liste if c.startswith(motif) or motif in c]
    rapport = {'base': base, 'largeur': largeur, 'debut': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'pages': []}
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        ctx = nav.new_context(viewport={'width': largeur, 'height': 1200}, locale='fr-CH',
                              timezone_id='Europe/Zurich')
        page = ctx.new_page()
        for libelle, chemin in liste:
            try:
                page.goto(base + chemin, wait_until='domcontentloaded', timeout=45000)
                try:
                    page.wait_for_load_state('networkidle', timeout=15000)
                except Exception:  # noqa: BLE001 — SSE : jamais « idle »
                    pass
                #  Les graphiques se montent après les données : on descend la page
                #  (les cartes en `content-visibility` ne dessinent pas hors écran).
                page.evaluate("() => new Promise(r => { let y = 0; const t = setInterval(() => { window.scrollTo(0, y); y += 700; if (y > document.body.scrollHeight) { clearInterval(t); window.scrollTo(0, 0); r(); } }, 120); })")
                page.wait_for_timeout(int(attente * 1000))
                m = page.evaluate(JS_MESURE)
            except Exception as exc:  # noqa: BLE001
                m = {'exception_audit': str(exc)[:200]}
            m['page'] = libelle
            m['chemin'] = chemin
            rapport['pages'].append(m)
        ctx.close()
        nav.close()
    rapport['fin'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    return rapport


#: Un canevas peint moins que ce nombre de pixels échantillonnés est considéré
#: comme VIDE. Mesuré : un canevas Chart.js avec une courbe en peint des
#: milliers ; un canevas monté et jamais dessiné en peint 0.
SEUIL_PIXELS = 40
#: Nombre minimal de tracés PAR FAMILLE de SVG. Mesuré le 2026-09-06 sur les
#: 59 vues : une jauge d'anneau en porte 2 (piste + arc) et c'est complet ; un
#: graphique de série qui n'en porte qu'un seul n'a dessiné que son cadre.
SEUIL_TRACES = {'jauge': 1, 'aires': 1, 'graphique': 2}


def defauts(r: dict) -> list[dict]:
    out = []
    for pg in r['pages']:
        if pg.get('exception_audit'):
            out.append({'page': pg['page'], 'quoi': 'audit', 'detail': pg['exception_audit']})
            continue
        for c in pg.get('canevas', []):
            if c['pixels'] == 0:
                out.append({'page': pg['page'], 'quoi': 'canevas vide', 'detail': '%s (%dx%d)' % (c['nom'], c['w'], c['h'])})
            elif 0 < c['pixels'] < SEUIL_PIXELS:
                out.append({'page': pg['page'], 'quoi': 'canevas quasi vide', 'detail': '%s (%d px peints)' % (c['nom'], c['pixels'])})
        for s in pg.get('svgs', []):
            fam = s.get('famille') or 'graphique'
            if s['traces'] <= SEUIL_TRACES.get(fam, 2) and not s.get('explique'):
                out.append({'page': pg['page'], 'quoi': 'svg sans tracé',
                            'detail': '%s — %s, %d élément(s)' % (s['nom'], fam, s['traces'])})
        for c in pg.get('creux', []) or []:
            out.append({'page': pg['page'], 'quoi': 'valeur creuse muette',
                        'detail': '%s — « %s » sans explication sur la carte' % (c['nom'], c['v'])})
        for c in pg.get('cartes', []):
            if (c['canevas'] or c['svg']) and c['peint'] == 0 and not c['etat_vide']:
                out.append({'page': pg['page'], 'quoi': 'carte-graphique muette',
                            'detail': '%s — rien de dessiné, aucune explication : « %s »' % (c['nom'], c['extrait'])})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--base', default=os.environ.get('VERTEX_MESURE_BASE', 'http://127.0.0.1:5003'))
    ap.add_argument('--largeur', type=int, default=1600)
    ap.add_argument('--attente', type=float, default=7.0)
    ap.add_argument('--json', default=None)
    ap.add_argument('--seul', default=None)
    a = ap.parse_args()
    r = auditer(a.base, a.largeur, a.attente, a.seul)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    d = defauts(r)
    n_cv = sum(len(p.get('canevas') or []) for p in r['pages'])
    n_sv = sum(len(p.get('svgs') or []) for p in r['pages'])
    n_val = sum(p.get('valeurs_total') or 0 for p in r['pages'])
    n_creux = sum(p.get('valeurs_creuses') or 0 for p in r['pages'])
    n_muets = sum(p.get('creux_muets') or 0 for p in r['pages'])
    print('pages %d · canevas %d · svg %d · widgets %d (dont %d sans valeur, %d SANS EXPLICATION) · défauts %d'
          % (len(r['pages']), n_cv, n_sv, n_val, n_creux, n_muets, len(d)))
    for x in d:
        print('- %s : %s — %s' % (x['page'], x['quoi'], x['detail'][:170]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
