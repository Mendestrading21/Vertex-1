// LOT 83 — tri/filtres/contrôles interactifs : cliquer et vérifier l'effet.
const { chromium } = require('playwright');
/*  Instance de VÉRIFICATION par défaut (5003), jamais l'instance réelle
    branchée sur le courtier : un outil de mesure ne doit pas lui voler
    ses requêtes ni sonder un port dont il ne sait rien. */
const BASE = process.env.VERTEX_MESURE_BASE || 'http://127.0.0.1:5003';
const PAGES = ['/markets', '/opportunities?view=stocks', '/opportunities?view=options',
               '/opportunities?view=anomalies', '/opportunities?view=calendar',
               '/portfolio', '/options', '/journal'];
(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await (await browser.newContext()).newPage();
  const errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 100)); });
  page.on('pageerror', e => errs.push('PAGEERROR ' + String(e).slice(0, 100)));
  let defects = 0, tested = 0;
  for (const path of PAGES) {
    await page.goto(BASE + path, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(2600);
    // 1) th cliquables (tri) : cliquer le 1er th trié/cliquable de chaque table
    const tables = await page.$$('table');
    for (let t = 0; t < Math.min(tables.length, 3); t++) {
      const ths = await tables[t].$$('th[data-sort], th.sortable, th[onclick], th[role="button"], th[tabindex]');
      if (!ths.length) continue;
      tested++;
      const before = await tables[t].$$eval('tbody tr', rs => rs.slice(0, 5).map(r => r.innerText.slice(0, 40)));
      await ths[0].click(); await page.waitForTimeout(900);
      const after = await tables[t].$$eval('tbody tr', rs => rs.slice(0, 5).map(r => r.innerText.slice(0, 40)));
      const changed = JSON.stringify(before) !== JSON.stringify(after);
      // re-cliquer peut inverser : accepter si 2e clic change aussi
      if (!changed) {
        await ths[0].click(); await page.waitForTimeout(900);
        const after2 = await tables[t].$$eval('tbody tr', rs => rs.slice(0, 5).map(r => r.innerText.slice(0, 40)));
        if (JSON.stringify(after) === JSON.stringify(after2)) {
          defects++; console.log(`INERTE tri ${path} table[${t}] th[0]`);
        }
      }
    }
    // 2) segmented controls / onglets de vue — re-localisés à chaque tour (SPA)
    const SEG_SEL = '.vx-seg [data-view], .vx-tabs a[href], .vx-view-tabs a, [data-vx-seg] button';
    const nSegs = Math.min((await page.$$(SEG_SEL)).length, 4);
    for (let s = 0; s < nSegs; s++) {
      try {
        const segs2 = await page.$$(SEG_SEL);
        if (s >= segs2.length) break;
        const el = segs2[s];
        const wasActive = await el.evaluate(e => e.getAttribute('aria-selected') === 'true' || e.classList.contains('active') || e.getAttribute('data-active') === '1');
        if (wasActive) continue;
        tested++;
        const url0 = page.url();
        await el.click({ timeout: 3000 }).catch(() => {});
        await page.waitForTimeout(1600);
        const urlChanged = page.url() !== url0;
        let domActive = true;
        try {
          const segs3 = await page.$$(SEG_SEL);
          domActive = s < segs3.length ? await segs3[s].evaluate(e => e.getAttribute('aria-selected') === 'true' || e.classList.contains('active') || e.getAttribute('data-active') === '1') : true;
        } catch (e2) { domActive = true; }
        if (!urlChanged && !domActive) { defects++; console.log(`INERTE seg ${path} [${s}]`); }
        if (urlChanged) { await page.goto(BASE + path, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800); }
      } catch (e1) { /* navigation SPA en cours — re-baser */
        await page.goto(BASE + path, { waitUntil: 'domcontentloaded' }).catch(() => {});
        await page.waitForTimeout(1800);
      }
    }
    // 3) selects visibles
    const sels = await page.$$('select');
    for (let s = 0; s < Math.min(sels.length, 2); s++) {
      const vis = await sels[s].isVisible().catch(() => false);
      if (!vis) continue;
      tested++;
      const opts = await sels[s].$$eval('option', os => os.map(o => o.value));
      if (opts.length > 1) {
        const body0 = await page.evaluate(() => document.body.innerText.length);
        await sels[s].selectOption(opts[1]).catch(() => {}); await page.waitForTimeout(1200);
        const body1 = await page.evaluate(() => document.body.innerText.length);
        if (body0 === body1) console.log(`(select sans effet mesuré ${path} [${s}] — à vérifier manuellement)`);
      }
    }
    console.log(`${path.padEnd(32)} audité`);
  }
  await browser.close();
  console.log(`\nCONTRÔLES testés=${tested} · INERTES/défauts=${defects} · erreurs console=${errs.length}`);
  if (errs.length) console.log('ERRS:', [...new Set(errs)].slice(0, 5));
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
