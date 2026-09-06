/**
 * tools/rc_short_audit.js — RC COURTE périodique (SKYLER LOT 32).
 *
 * Audit léger navigateur des 8 espaces canoniques :
 *   - 0 erreur console au repos (erreurs réseau in-flight d'une navigation
 *     abandonnée et polices externes injoignables en sandbox exclues,
 *     comme documenté au lot 27) ;
 *   - 0 pageerror (exception JS non rattrapée) ;
 *   - HTTP 200 par page ; /healthz ok ; /api/client-log à 0 ;
 *   - service worker courant servi (td-shell-vNNN affiché pour preuve) ;
 *   - PARCOURS MÉMOIRE (LOT 41) : une décision démo est déclenchée
 *     (/api/skyler/AAPL), puis la vue post-mortem /memory/<id> du record
 *     figé est vérifiée en vrai navigateur (200, contenu, 0 erreur
 *     console) et la vue cellule /memory/cell/… d'une cellule existante
 *     si le magasin en publie une — sinon le 404 LISIBLE est vérifié et
 *     DIT (jamais un état inventé) ;
 *   - CYCLE SOUVERAIN (LOT 48) : le bundle d'export est téléchargé, une
 *     copie ALTÉRÉE doit être REFUSÉE (empreinte_invalide dit), puis le
 *     bundle INTACT est restauré via le VRAI bouton « Importer » de la
 *     carte Mémoire (setInputFiles) — le message doit dire la
 *     restauration et un ledger SAIN. Sauvegarde ET restauration sont
 *     ainsi prouvées en navigateur à chaque RC.
 *
 * Usage : serveur démo lancé (DEMO=1 NO_IBKR=1 START_ON_IMPORT=1), puis
 *   NODE_PATH=/opt/node22/lib/node_modules node tools/rc_short_audit.js
 * Sortie : rapport texte + code retour 0 (GO) / 1 (défauts à investiguer).
 */
const { chromium } = require('playwright');

const BASE = process.env.VERTEX_MESURE_BASE || process.env.VERTEX_BASE
  || 'http://127.0.0.1:5003';   //  jamais l'instance réelle par défaut
const PAGES = ['/', '/markets', '/opportunities', '/analysis',
               '/portfolio', '/options', '/journal', '/system'];
// Bruit d'environnement documenté (lot 27) — jamais des défauts produit :
const NOISE = [/net::ERR_ABORTED/, /fonts\.googleapis\.com/, /fonts\.gstatic\.com/,
               /Failed to load resource/];

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium',
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const defects = [];

  for (const path of PAGES) {
    const consoleErrors = [];
    const pageErrors = [];
    const onConsole = (m) => {
      if (m.type() === 'error' && !NOISE.some((r) => r.test(m.text()))) {
        consoleErrors.push(m.text());
      }
    };
    const onPageError = (e) => pageErrors.push(String(e));
    page.on('console', onConsole);
    page.on('pageerror', onPageError);

    const resp = await page.goto(BASE + path, {
      waitUntil: 'domcontentloaded', timeout: 20000,
    });
    await page.waitForTimeout(2500);            // hydratation + premier poll

    const status = resp ? resp.status() : 0;
    if (status !== 200) defects.push(`${path} → HTTP ${status}`);
    for (const e of consoleErrors) defects.push(`${path} → console: ${e}`);
    for (const e of pageErrors) defects.push(`${path} → pageerror: ${e}`);
    console.log(`${path.padEnd(15)} HTTP ${status}  console_err=${consoleErrors.length}  pageerror=${pageErrors.length}`);

    page.off('console', onConsole);
    page.off('pageerror', onPageError);
  }

  const health = await page.evaluate(async (base) => {
    const r = await fetch(base + '/healthz');
    return { status: r.status, body: await r.text() };
  }, BASE);
  console.log(`/healthz        HTTP ${health.status}  ${health.body.slice(0, 60)}`);
  if (health.status !== 200) defects.push(`/healthz → HTTP ${health.status}`);

  const clientLog = await page.evaluate(async (base) => {
    const r = await fetch(base + '/api/client-log');
    return await r.json();
  }, BASE);
  const n = Array.isArray(clientLog) ? clientLog.length
    : (clientLog.count ?? (clientLog.errors || []).length);
  console.log(`/api/client-log n=${n}`);
  if (n !== 0) defects.push(`/api/client-log → ${n} erreur(s) client`);

  const sw = await page.evaluate(async (base) => {
    const r = await fetch(base + '/sw.js');
    const t = await r.text();
    const m = t.match(/td-shell-v(\d+)/);
    return m ? m[0] : null;
  }, BASE);
  console.log(`sw.js           ${sw}`);
  if (!sw) defects.push('/sw.js → aucun td-shell-vNNN trouvé');

  // ─── Parcours mémoire (LOT 41) : décision → record figé → cellule ───
  const memInfo = await page.evaluate(async (base) => {
    await fetch(base + '/api/skyler/AAPL');       // fige une décision démo
    const r = await fetch(base + '/api/skyler/memory');
    const d = await r.json();
    const ds = d.decisions || [];
    const last = ds.length ? ds[ds.length - 1] : null;
    const cc = d.calibration_by_context || {};
    let cell = null;
    for (const g of ['by_level', 'by_decision', 'by_regime',
                     'by_catalyst', 'by_catalyst_type']) {
      const keys = Object.keys(cc[g] || {});
      if (keys.length) { cell = g + '/' + encodeURIComponent(keys[0]); break; }
    }
    return { id: last ? last.decision_id : null, cell };
  }, BASE);

  async function visit(path, expect, mustContain) {
    const errs = [];
    const onC = (m) => {
      if (m.type() === 'error' && !NOISE.some((r) => r.test(m.text()))) errs.push(m.text());
    };
    page.on('console', onC);
    const resp = await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.waitForTimeout(1200);
    const status = resp ? resp.status() : 0;
    const body = await page.evaluate(() => document.body.innerText);
    page.off('console', onC);
    console.log(`${path.slice(0, 40).padEnd(40)} HTTP ${status}  console_err=${errs.length}`);
    if (status !== expect) defects.push(`${path} → HTTP ${status} (attendu ${expect})`);
    // innerText reflète la casse AFFICHÉE (text-transform CSS) → comparaison
    // insensible à la casse
    if (mustContain && !body.toLowerCase().includes(mustContain.toLowerCase())) {
      defects.push(`${path} → « ${mustContain} » absent`);
    }
    for (const e of errs) defects.push(`${path} → console: ${e}`);
  }

  if (memInfo.id) {
    await visit('/memory/' + encodeURIComponent(memInfo.id), 200, 'Décision figée');
  } else {
    defects.push('/api/skyler/memory → aucun record figé après /api/skyler/AAPL');
  }
  if (memInfo.cell) {
    await visit('/memory/cell/' + memInfo.cell, 200, 'Cellule');
  } else {
    // aucune cellule mesurée (honnête en démo) → le 404 LISIBLE est vérifié
    await visit('/memory/cell/by_level/AUCUNE_CELLULE', 404, 'Cellule inconnue');
    console.log('(aucune cellule mesurée publiée — 404 lisible vérifié à la place)');
  }

  // ─── Cycle souverain (LOT 48) : export → altération refusée → import ───
  const fs = require('fs');
  const os = require('os');
  const path = require('path');
  const bundle = await page.evaluate(async (base) => {
    const r = await fetch(base + '/api/skyler/memory/export');
    return await r.json();
  }, BASE);
  if (!bundle || !bundle.content_sha256) {
    defects.push('/api/skyler/memory/export → bundle sans content_sha256');
  } else {
    // 1. une copie ALTÉRÉE doit être refusée — empreinte dite
    const refusal = await page.evaluate(async (args) => {
      const tampered = JSON.parse(JSON.stringify(args.bundle));
      tampered.note = (tampered.note || '') + ' ALTERATION';
      const r = await fetch(args.base + '/api/skyler/memory/import', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(tampered),
      });
      const d = await r.json();
      return { status: r.status, error: d.error || null };
    }, { base: BASE, bundle });
    console.log(`import bundle altéré                     HTTP ${refusal.status}  (${refusal.error})`);
    if (refusal.status !== 400 || refusal.error !== 'empreinte_invalide') {
      defects.push('import altéré → attendu 400 empreinte_invalide, obtenu '
        + refusal.status + '/' + refusal.error);
    }
    // 2. le bundle INTACT est restauré via le VRAI bouton Importer
    const tmpFile = path.join(os.tmpdir(), 'rc_sovereign_bundle.json');
    fs.writeFileSync(tmpFile, JSON.stringify(bundle), 'utf-8');
    await page.goto(BASE + '/journal', { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.waitForTimeout(2000);
    // L'import vit désormais dans le niveau Expert replié : l'audit suit le
    // vrai parcours utilisateur avant d'utiliser le vrai champ fichier.
    await page.locator('#vx-pf-history-disclosure > summary').click();
    await page.waitForTimeout(200);
    await page.setInputFiles('#vx-mem-import-file', tmpFile);
    await page.waitForTimeout(2500);
    const result = await page.evaluate(() => {
      const el = document.getElementById('vx-mem-import-result');
      return el ? el.innerText : 'ABSENT';
    });
    fs.unlinkSync(tmpFile);
    const low = result.toLowerCase();
    console.log(`import via bouton                        « ${result.slice(0, 70)}… »`);
    if (!low.includes('restauration') || !low.includes('sain')) {
      defects.push('import via bouton → message inattendu : ' + result.slice(0, 120));
    }
  }

  await browser.close();
  if (defects.length) {
    console.log('\nDÉFAUTS :');
    for (const d of defects) console.log('  - ' + d);
    process.exit(1);
  }
  console.log('\nRC COURTE : GO — 0 défaut.');
  process.exit(0);
})().catch((e) => { console.error('AUDIT ÉCHOUÉ :', e); process.exit(1); });
