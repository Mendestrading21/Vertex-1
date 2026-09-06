# -*- coding: utf-8 -*-
"""Mesure la page Opportunites dans un vrai navigateur. Sortie : JSON.

DANS UN SOUS-PROCESSUS, pour la meme raison que `sonde_boutons_morts` :
`ib_async` applique `nest_asyncio`, et l'API synchrone de Playwright refuse
alors de demarrer dans le processus de test.

Usage :  python tests/aides/sonde_opportunites.py http://127.0.0.1:5003
Sortie :  {"ok": true, "screener": {...}, "anomalies": {...}, "etf": {...}}
          {"ok": false, "motif": "..."} si rien n'a pu etre mesure.
"""
import json
import os
import sys

_JS_SCREENER = r"""
async () => {
  const out = {};
  const scan = await fetch('/scan').then(r => r.json()).catch(() => null);
  const lignes = ((scan && scan.rows) || []).filter(r => r.score !== undefined);
  out.scoreesServies = lignes.length;
  out.sansSecteur = lignes.filter(r => !r.sector).length;

  /* --- Cartes : chacune porte-t-elle un age ? --------------------------- */
  out.cartesSansAge = [];
  document.querySelectorAll('#op-body .vx-card, #op-body section.vx-card').forEach(el => {
    const t = (el.querySelector('.vx-card-title, .vx-chart-title') || {}).textContent;
    if (!t) return;
    if (!el.querySelector('.vx-update-age')) out.cartesSansAge.push(t.trim());
  });

  /* --- Donut des verdicts : couleurs reellement posees ------------------ */
  const cv = document.querySelector('#op-verdicts canvas');
  out.donut = null;
  if (cv && window.Chart && Chart.getChart) {
    const ch = Chart.getChart(cv);
    if (ch) {
      const cols = ch.data.datasets[0].backgroundColor || [];
      out.donut = {labels: ch.data.labels, couleurs: cols,
                   distinctes: [...new Set(cols.map(String))].length};
    }
  }

  /* --- Matrice secteur x statut ---------------------------------------- */
  const lignesData = [...document.querySelectorAll('#op-heat table tr')]
      .filter(tr => tr.querySelector('td'));
  out.matrice = {lignes: lignesData.length, sommeCellules: 0,
                 cellulesNonCliquables: 0, cellules: 0, fonds: []};
  lignesData.forEach(tr => {
    [...tr.querySelectorAll('td')].forEach(td => {
      out.matrice.cellules++;
      out.matrice.sommeCellules += (parseInt(td.textContent, 10) || 0);
      if (getComputedStyle(td).cursor !== 'pointer') out.matrice.cellulesNonCliquables++;
      out.matrice.fonds.push({v: parseInt(td.textContent, 10),
                              fond: getComputedStyle(td).backgroundColor});
    });
  });
  /* Reperes de teinte : les deux couleurs SIGNEES de la charte, resolues
     dans le theme courant plutot qu'ecrites en dur. */
  const teinte = (jeton) => {
    const s = document.createElement('span');
    s.style.color = 'var(' + jeton + ')';
    document.body.appendChild(s);
    const c = getComputedStyle(s).color;
    s.remove();
    return c;
  };
  out.teintes = {positive: teinte('--vx-positive'), negative: teinte('--vx-negative')};
  out.matriceBornes = ((document.querySelector('#op-heat .vx-chart-foot .vx-meta') || {})
      .textContent || '').trim();

  /* --- Barre de contexte : la fraicheur est-elle MESUREE ? -------------- */
  const grp = (nom) => [...document.querySelectorAll('#op-context .vx2-context-group')]
      .find(g => ((g.querySelector('.vx2-context-label') || {}).textContent || '')
                 .trim().toLowerCase().startsWith(nom));
  const gScan = grp('dernier'), gFra = grp('fra');
  out.contexte = {
    scanTexte: gScan ? (gScan.innerText || '').replace(/\s+/g, ' ').trim() : null,
    fraicheurTexte: gFra ? (gFra.innerText || '').replace(/\s+/g, ' ').trim() : null,
    fraicheurEtat: gFra && gFra.querySelector('.vx2-badge')
        ? gFra.querySelector('.vx2-badge').getAttribute('data-state') : null,
    scanTsH: (scan && scan.scan_ts_h) || null,
    ageSecondes: (scan && scan.scan_age) != null ? scan.scan_age : null,
    seuilStaleMs: (window.VX && VX.freshness && VX.freshness.THRESH)
        ? VX.freshness.THRESH.stale : null,
    etatA40min: (window.VX && VX.freshness)
        ? VX.freshness.assess({ageMs: 40 * 60 * 1000}).state : null,
    /* L'age que la PAGE calcule (depuis `scan_ts`), et l'etat que la table du
       produit lui donne. On releve la BORNE REELLEMENT APPLIQUEE au lieu de
       nommer une constante : `assess` ne bascule qu'a `THRESH.snapshot`
       (30 min) — `THRESH.stale` (35 min) n'y sert nulle part. Un banc calibre
       sur `THRESH.stale` accuse la page a tort entre 30 et 35 min (mesure du
       06/09/2026 : scan age de 32 min, page « stale », banc attendait
       « delayed »). */
    ageMsMesure: (function () {
      if (!(window.VX && VX.freshness)) return null;
      var t = (scan && (scan.scan_ts || scan.scan_ts_h)) || null;
      var ms = VX.freshness._ms(t);
      return (ms == null) ? null : Math.max(0, Date.now() - ms);
    })(),
    etatProduit: (function () {
      if (!(window.VX && VX.freshness)) return null;
      var t = (scan && (scan.scan_ts || scan.scan_ts_h)) || null;
      var ms = VX.freshness._ms(t);
      if (ms == null) return null;
      return VX.freshness.assess({ageMs: Math.max(0, Date.now() - ms)}).state;
    })(),
  };

  /* --- Le clic d'une cellule applique-t-il CE que la cellule promet ? --- */
  out.clic = null;
  if (lignesData.length) {
    const tds = [...lignesData[0].querySelectorAll('td')];
    /* colonne >= 1 : un decalage d'une colonne doit se voir */
    const cible = tds.find((td, i) => i >= 1 && (parseInt(td.textContent, 10) || 0) > 0);
    if (cible) {
      const titre = cible.title || '';
      const gauche = titre.split(' : ')[0];
      const promis = {secteur: gauche.split(' · ')[0],
                      statut: gauche.split(' · ')[1],
                      compte: parseInt(cible.textContent, 10) || 0};
      cible.click();
      await new Promise(r => setTimeout(r, 700));
      let f = {};
      try { f = JSON.parse(localStorage.getItem('vxScreenFilters') || '{}'); } catch (e) {}
      const cpt = (document.getElementById('op-count') || {}).textContent || '';
      out.clic = {promis: promis,
                  obtenu: {secteur: f.sector || '', statut: f.bucket || ''},
                  compteAffiche: parseInt(cpt, 10)};
    }
  }
  return out;
}
"""

_JS_ANOMALIES = r"""
() => {
  const out = {};
  const sonde = document.createElement('span');
  sonde.style.color = 'var(--vx-positive)';
  document.body.appendChild(sonde);
  out.vert = getComputedStyle(sonde).color;
  sonde.remove();
  out.entetes = [...document.querySelectorAll('#op-anom thead th')].map(t => t.textContent.trim());
  out.intensites = [...document.querySelectorAll('#op-anom tbody tr')].slice(0, 20).map(tr => {
    const tds = [...tr.querySelectorAll('td')];
    const sp = tds[3] && tds[3].querySelector('span');
    return {sym: (tds[0] || {}).textContent, niveau: (tds[1] || {}).textContent,
            valeur: parseInt((tds[3] || {}).textContent, 10),
            couleur: sp ? getComputedStyle(sp).color : null};
  });
  out.cartesSansAge = [];
  document.querySelectorAll('#op-body .vx-card, #op-body section.vx-card').forEach(el => {
    const t = (el.querySelector('.vx-card-title, .vx-chart-title') || {}).textContent;
    if (t && !el.querySelector('.vx-update-age')) out.cartesSansAge.push(t.trim());
  });
  out.tableAvecAge = !!document.querySelector('#op-anom .vx-update-age');
  return out;
}
"""

_JS_ETF = r"""
async () => {
  const scan = await fetch('/scan').then(r => r.json()).catch(() => null);
  const lignes = ((scan && scan.rows) || []).filter(r => r.score !== undefined);
  return {scoreesServies: lignes.length,
          titre: ((document.querySelector('#op-body .vx2-state-title') || {}).textContent || '').trim(),
          cause: ((document.querySelector('#op-body .vx2-state-cause') || {}).textContent || '').trim(),
          corps: (document.getElementById('op-body').innerText || '').trim()};
}
"""


def _chromium():
    """Chemin du Chromium de Playwright sur CETTE machine, ou None.

    None reste licite : `launch(executable_path=None)` laisse Playwright
    resoudre seul. Meme regle que `tools.mesures.mesurer_qa_espaces._chromium`.
    """
    pistes = []
    depuis_env = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    if depuis_env:
        pistes.append(depuis_env)
    pistes += ['/opt/pw-browsers',
               os.path.expanduser('~/AppData/Local/ms-playwright'),
               os.path.expanduser('~/.cache/ms-playwright'),
               os.path.expanduser('~/Library/Caches/ms-playwright')]
    for base in pistes:
        if not os.path.isdir(base):
            continue
        for nom in sorted(os.listdir(base), reverse=True):
            if not nom.startswith('chromium'):
                continue
            for bout in ('chrome-win/chrome.exe', 'chrome-linux/chrome',
                         'chrome-mac/Chromium.app/Contents/MacOS/Chromium'):
                chemin = os.path.join(base, nom, bout)
                if os.path.exists(chemin):
                    return chemin
    return None


#: Toutes les sous-vues servies par la page. Une seule d'entre elles qui
#: tombe en « Chargement impossible » est un ecran mort : le corps garde son
#: bandeau d'erreur, et la console reste MUETTE (boot attrape l'exception).
#: C'est exactement ce qui est arrive le 06/09/2026 sur la vue Options —
#: « update is not defined » — sans une ligne de console.
_VUES = ('screener', 'stocks', 'etf', 'options', 'anomalies', 'calendar',
         'portfolio')

_JS_VIVANTE = r"""
() => {
  const b = document.getElementById('op-body');
  if (!b) return {corps: 0, erreur: 'pas de #op-body'};
  const err = b.querySelector('.vx-error-banner, [data-state="error"]');
  return {corps: (b.innerText || '').trim().length,
          erreur: err ? (err.innerText || '').trim().slice(0, 160) : null,
          squelette: !!b.querySelector(':scope > .vx-skeleton')};
}
"""


def main() -> None:
    base = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5003').rstrip('/')
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({'ok': False, 'motif': 'playwright absent : %s' % exc}))
        return
    exe = _chromium()
    kw = {'executable_path': exe} if exe else {}
    detail = {'screener': _JS_SCREENER, 'anomalies': _JS_ANOMALIES, 'etf': _JS_ETF}
    out = {'ok': True, 'base': base, 'console': {}, 'vivantes': {}}
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(**kw)
            for vue in _VUES:
                ctx = nav.new_context(viewport={'width': 1600, 'height': 1000})
                page = ctx.new_page()
                erreurs = []
                page.on('pageerror', lambda e: erreurs.append(str(e)[:200]))
                page.on('console',
                        lambda m: erreurs.append(m.type + ': ' + m.text[:200])
                        if m.type == 'error' else None)
                page.goto('%s/opportunities?view=%s' % (base, vue),
                          wait_until='networkidle', timeout=60000)
                page.wait_for_timeout(2500)
                out['vivantes'][vue] = page.evaluate(_JS_VIVANTE)
                if vue in detail:
                    out[vue] = page.evaluate(detail[vue])
                out['console'][vue] = erreurs
                ctx.close()
            nav.close()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({'ok': False, 'motif': '%s: %s' % (type(exc).__name__, exc)}))
        return
    #  `ensure_ascii=True` : la sortie standard de Windows est en cp1252 et
    #  la page rend des caracteres hors table (fleche « → » de « Systeme
    #  → Donnees », tirets cadratins, guillemets francais). MESURE DU
    #  06/09/2026 : avec `ensure_ascii=False`, la sonde mourait ici sur
    #  UnicodeEncodeError, n'ecrivait RIEN sur stdout, et les 28 bancs du
    #  lot s'abstenaient en bloc (« sonde muette ») au lieu de mesurer.
    #  Meme convention que `sonde_h_systeme_intelligence`.
    print(json.dumps(out, ensure_ascii=True))


if __name__ == '__main__':
    main()
