// LOT 80 — 5 parcours bout-en-bout « du réveil à la décision ».
const { chromium } = require('playwright');
/*  Instance de VÉRIFICATION par défaut (5003), jamais l'instance réelle
    branchée sur le courtier. */
const BASE = process.env.VERTEX_MESURE_BASE || 'http://127.0.0.1:5003';
(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await (await browser.newContext()).newPage();
  const errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)); });
  page.on('pageerror', e => errs.push('PAGEERROR ' + String(e).slice(0, 120)));
  const results = [];
  const step = (name, ok, detail) => { results.push({ name, ok, detail }); console.log(`${ok ? 'OK  ' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`); };
  const settle = (ms = 2200) => page.waitForTimeout(ms);

  // ── Parcours 1 : / → meilleure opp → fiche → retour
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' }); await settle(2600);
  const brief = await page.evaluate(() => document.body.innerText.slice(0, 2000));
  step('P1a brief lisible', /Régime|Brief|Discipline/i.test(brief));
  const bestLink = await page.$('[data-open-analysis], a[href^="/analysis/"]');
  step('P1b meilleure opp cliquable', !!bestLink);
  if (bestLink) {
    await bestLink.click(); await settle(2600);
    const url1 = page.url();
    const fiche = await page.evaluate(() => document.body.innerText.slice(0, 3000));
    step('P1c fiche chargée avec verdict', /\/analysis\//.test(url1) && /REFUSER|EXÉCUTER|ACHETER|WATCH|verdict|décision/i.test(fiche), url1.replace(BASE, ''));
    await page.goBack({ waitUntil: 'domcontentloaded' }); await settle();
    step('P1d retour arrière sur /', new URL(page.url()).pathname === '/');
  }

  // ── Parcours 2 : sidebar → Marchés → vue breadth → graphe rendu
  const mk = await page.$('.vx-sidebar [data-nav-id="markets"], .vx-sidebar a[href="/markets"]');
  step('P2a lien Marchés sidebar', !!mk);
  if (mk) { await mk.click(); await settle(2600); }
  else { await page.goto(BASE + '/markets', { waitUntil: 'domcontentloaded' }); await settle(2600); }
  step('P2b sur /markets', page.url().includes('/markets'));
  await page.goto(BASE + '/markets?view=breadth', { waitUntil: 'domcontentloaded' }); await settle(2600);
  const hasChart = await page.evaluate(() => !!document.querySelector('canvas, svg.vx-chart, .vx-chart-card svg, .vx-chart-card canvas'));
  step('P2c vue breadth avec graphe rendu', hasChart);

  // ── Parcours 3 : Opportunités → ticker shortlist → fiche
  await page.goto(BASE + '/opportunities', { waitUntil: 'domcontentloaded' }); await settle(2800);
  const tk = await page.$('.vx-op-tk [data-open-analysis]');
  step('P3a ticker shortlist présent', !!tk);
  if (tk) {
    const sym = await tk.getAttribute('data-open-analysis');
    await tk.click(); await settle(2600);
    step('P3b fiche du ticker ouverte', page.url().includes('/analysis/'), `${sym} → ${page.url().replace(BASE, '')}`);
  }

  // ── Parcours 4 : fiche → menu entité ouvert puis fermé
  const ent = await page.$('[data-entity-menu]');
  step('P4a déclencheur menu entité', !!ent);
  if (ent) {
    await ent.click(); await settle(900);
    const menuOpen = await page.evaluate(() => { const m = document.querySelector('.vx-entity-menu, [data-open="1"]'); return !!m; });
    step('P4b menu ouvert', menuOpen);
    await page.mouse.click(4, 4); await settle(700);
    const menuClosed = await page.evaluate(() => { const m = document.querySelector('.vx-entity-menu[data-open="1"], .vx-menu[data-open="1"]'); return !m; });
    step('P4c menu refermé proprement', menuClosed);
  }

  // ── Parcours 5 : Journal → décision mémoire → page mémoire lisible
  await page.goto(BASE + '/journal', { waitUntil: 'domcontentloaded' }); await settle(2600);
  const mem = await page.$('a[href^="/memory/"]');
  step('P5a lien décision mémoire présent', !!mem);
  if (mem) {
    await mem.click(); await settle(2200);
    const memText = await page.evaluate(() => document.body.innerText.slice(0, 1500));
    step('P5b page mémoire lisible', page.url().includes('/memory/') && /décision|Décision|verdict|empreinte|hash/i.test(memText), page.url().replace(BASE, ''));
  }

  await browser.close();
  const fails = results.filter(r => !r.ok).length;
  console.log(`\nPARCOURS : ${results.length} étapes, ${fails} échec(s) · erreurs console/page = ${errs.length}`);
  if (errs.length) console.log('ERRS:', [...new Set(errs)].slice(0, 5));
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
