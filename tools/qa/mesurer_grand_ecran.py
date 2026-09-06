# -*- coding: utf-8 -*-
"""tools/qa/mesurer_grand_ecran.py — combien de l'écran Vertex utilise-t-il ?

Le poste de travail porte deux écrans 5120 × 1440 (32:9). La coque plafonne le
contenu à `--vx-content-max` et pose une barre latérale fixe : sur un écran
ordinaire cela protège la longueur de ligne, sur un ultra-large cela laisse une
bande vide plus large que le contenu lui-même.

Cet outil ne juge pas : il MESURE, page par page et largeur par largeur —

- la largeur réellement occupée par le contenu, et celle laissée vide ;
- le nombre de COLONNES que chaque grille forme réellement (deux cartes sur la
  même ligne comptent pour deux colonnes) ;
- la longueur de ligne du texte courant, en caractères — au-delà d'environ 90,
  l'œil perd la ligne suivante, et « utiliser l'écran » cesse d'être un gain ;
- les cartes qui s'étirent sans se remplir : hauteur faible pour une largeur
  énorme, symptôme d'une grille qui n'a pas su répartir.

Lecture seule.

    python tools/qa/mesurer_grand_ecran.py [--base URL] [--largeurs 5120,2560,1920]
                                           [--json rapport.json] [--seul /markets]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RACINE)
from tools.qa.audit_cartes import pages, _normaliser_seul  # noqa: E402

JS_MESURE = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const doc = document.documentElement;
  const contenu = document.querySelector('.vx-content, #vx-content, main') || document.body;
  const rc = contenu.getBoundingClientRect();

  //  Une GRILLE forme des colonnes : on compte les cartes qui partagent la
  //  même bande horizontale, ce qui est ce que l'œil appelle « une ligne ».
  const cartes = [...document.querySelectorAll('section.vx-card, .vx-card, .vx2-surface')]
    .filter(vis).filter((c) => !c.parentElement.closest('.vx-card'));
  const lignes = {};
  cartes.forEach((c) => {
    const r = c.getBoundingClientRect();
    const bande = Math.round((r.top + window.scrollY) / 24);
    (lignes[bande] = lignes[bande] || []).push(Math.round(r.width));
  });
  const parLigne = Object.values(lignes).map((l) => l.length);
  const colonnes = parLigne.length ? Math.max(...parLigne) : 0;
  const seules = parLigne.filter((n) => n === 1).length;

  //  Longueur de ligne du texte courant, en caractères approximatifs.
  //  On MESURE la largeur d'un caractère dans la police de l'élément, au lieu
  //  de la supposer. Le facteur 0,5 em surestimait d'environ 30 % : une carte
  //  bridée à 92ch était rapportée à 122 caractères, ce qui faisait chercher un
  //  défaut là où la règle fonctionnait.
  const largeurCar = (el) => {
    const sonde = document.createElement('span');
    sonde.textContent = '0';
    const cs = getComputedStyle(el);
    sonde.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;'
      + 'font:' + cs.font + ';letter-spacing:' + cs.letterSpacing;
    el.appendChild(sonde);
    const w = sonde.getBoundingClientRect().width || 7;
    sonde.remove();
    return w;
  };
  const mesureTexte = (el) => {
    const t = (el.innerText || '').trim();
    if (t.length < 80) return null;
    const r = el.getBoundingClientRect();
    return Math.round(r.width / largeurCar(el));
  };
  const longueurs = [...document.querySelectorAll('p, .vx-help, .vx-meta, .vx-sub, li')]
    .filter(vis).map(mesureTexte).filter((x) => x !== null);

  //  Cartes ÉTIRÉES : très larges et très plates.
  const etirees = cartes.filter((c) => {
    const r = c.getBoundingClientRect();
    return r.width > 900 && r.height < 160;
  }).length;

  return {
    fenetre: window.innerWidth,
    contenu_largeur: Math.round(rc.width),
    contenu_gauche: Math.round(rc.left),
    vide_droite: Math.round(doc.clientWidth - rc.right),
    cartes: cartes.length,
    colonnes_max: colonnes,
    lignes_a_une_carte: seules,
    lignes_total: parLigne.length,
    texte_max_caracteres: longueurs.length ? Math.max(...longueurs) : null,
    texte_median_caracteres: longueurs.length
      ? longueurs.sort((a, b) => a - b)[Math.floor(longueurs.length / 2)] : null,
    cartes_etirees: etirees,
    debordement: doc.scrollWidth > doc.clientWidth,
  };
}
"""


def mesurer(base: str, largeurs: list[int], seul: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    liste = pages()
    if seul:
        motif = _normaliser_seul(seul)
        liste = [(n, c) for n, c in liste if c.startswith(motif) or motif in c]
    out = {'base': base, 'largeurs': largeurs, 'pages': []}
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        for largeur in largeurs:
            ctx = nav.new_context(viewport={'width': largeur, 'height': 1440},
                                  locale='fr-CH', timezone_id='Europe/Zurich')
            page = ctx.new_page()
            for libelle, chemin in liste:
                try:
                    page.goto(base + chemin, wait_until='domcontentloaded', timeout=45000)
                    page.wait_for_timeout(3500)
                    m = page.evaluate(JS_MESURE)
                except Exception as exc:                # noqa: BLE001
                    m = {'exception': str(exc)[:160], 'fenetre': largeur}
                m['page'] = libelle
                m['chemin'] = chemin
                out['pages'].append(m)
            ctx.close()
        nav.close()
    return out


def resume(r: dict) -> list[str]:
    lignes = []
    for largeur in r['largeurs']:
        vues = [p for p in r['pages'] if p.get('fenetre') == largeur and not p.get('exception')]
        if not vues:
            continue
        util = [100.0 * p['contenu_largeur'] / largeur for p in vues]
        col = [p['colonnes_max'] for p in vues]
        seules = sum(p['lignes_a_une_carte'] for p in vues)
        total = sum(p['lignes_total'] for p in vues) or 1
        txt = [p['texte_max_caracteres'] for p in vues if p.get('texte_max_caracteres')]
        etir = sum(p['cartes_etirees'] for p in vues)
        deb = sum(1 for p in vues if p.get('debordement'))
        lignes.append(
            '%5d px · écran utilisé %4.1f %% · colonnes max %d (médiane %d) · '
            'lignes à UNE carte %d/%d (%.0f %%) · ligne de texte max %s car. · '
            'cartes étirées %d · débordements %d'
            % (largeur, sum(util) / len(util), max(col), sorted(col)[len(col) // 2],
               seules, total, 100.0 * seules / total,
               max(txt) if txt else '?', etir, deb))
    return lignes


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:                                   # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--base', default=os.environ.get('VERTEX_MESURE_BASE',
                                                     'http://127.0.0.1:5003'))
    ap.add_argument('--largeurs', default='5120,2560,1920')
    ap.add_argument('--json', default=None)
    ap.add_argument('--seul', default=None)
    a = ap.parse_args()
    largeurs = [int(x) for x in a.largeurs.split(',') if x.strip()]
    r = mesurer(a.base, largeurs, a.seul)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    for ligne in resume(r):
        print(ligne)
    return 0


if __name__ == '__main__':
    sys.exit(main())
