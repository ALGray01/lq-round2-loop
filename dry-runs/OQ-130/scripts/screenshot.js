// Visual proof that the two explainers actually render, and are actually
// interactive, on a real desktop viewport and a real phone viewport — using
// a genuine Chromium browser (Playwright), not a hand-rolled HTTP client.
// This is the independent-counterpart check for the "renders right on
// mobile" claim: an HTTP 200 with the right bytes proves delivery, but only
// a real browser proves it lays out and responds to touch/click correctly.
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium, devices } = require('playwright');
const { createApp } = require('../src/server');

const PORT = 3902;
const BASE = `http://localhost:${PORT}`;
const ADMIN_TOKEN = 'screenshot-admin-token-' + Date.now();
const PROOF_DIR = path.join(__dirname, '..', 'proof');

async function admin(pathname, opts = {}) {
  const res = await fetch(BASE + pathname, {
    ...opts,
    headers: { 'x-admin-token': ADMIN_TOKEN, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  return res.json();
}

async function main() {
  process.env.ADMIN_TOKEN = ADMIN_TOKEN;
  const dbPath = path.join(__dirname, '..', 'data', 'db.json');
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  fs.writeFileSync(dbPath, JSON.stringify({ clients: [], documents: [], links: [] }, null, 2));
  fs.mkdirSync(PROOF_DIR, { recursive: true });

  const app = createApp();
  const server = app.listen(PORT);
  await new Promise((resolve) => server.once('listening', resolve));

  const client = await admin('/admin/clients', {
    method: 'POST',
    body: JSON.stringify({ name: 'Acme Corp (simulated client)', email: 'counsel@acme-corp.example' }),
  });
  const linkCalc = await admin('/admin/links', {
    method: 'POST',
    body: JSON.stringify({ clientId: client.id, documentId: 'penalty-calculator', ttlHours: 72 }),
  });
  const linkMemo = await admin('/admin/links', {
    method: 'POST',
    body: JSON.stringify({ clientId: client.id, documentId: 'service-agreement-memo', ttlHours: 72 }),
  });

  const browser = await chromium.launch();

  try {
    // --- Desktop: 1440x900, standard mouse/keyboard context ---
    const desktopCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const desktopPage = await desktopCtx.newPage();

    await desktopPage.goto(linkCalc.url);
    await desktopPage.screenshot({ path: path.join(PROOF_DIR, '01-calculator-desktop.png'), fullPage: true });
    // Prove interactivity: flip to fixed-fee mode and move the days-late slider.
    await desktopPage.click('#tab-fixed');
    await desktopPage.fill('#daysLate', '25');
    await desktopPage.dispatchEvent('#daysLate', 'input');
    await desktopPage.screenshot({ path: path.join(PROOF_DIR, '02-calculator-desktop-interacted.png'), fullPage: true });
    const desktopAmount = await desktopPage.textContent('#resultAmount');
    console.log(`Desktop calculator after interaction shows: ${desktopAmount}`);

    // Note: viewport-only (not fullPage) for the memo — Chromium's fullPage
    // capture re-renders `position: sticky` elements at both their natural
    // and stuck offsets, producing a duplicate-nav artifact in the PNG that
    // doesn't reflect what a real user scrolling the page ever sees.
    await desktopPage.goto(linkMemo.url);
    await desktopPage.screenshot({ path: path.join(PROOF_DIR, '03-memo-desktop.png') });
    await desktopPage.click('#c-liability .head');
    await desktopPage.check('#showClauses');
    await desktopPage.screenshot({ path: path.join(PROOF_DIR, '04-memo-desktop-expanded.png') });

    await desktopCtx.close();

    // --- Phone: real iPhone 13 device profile (viewport, UA, touch, DPR) ---
    const iphone = devices['iPhone 13'];
    const mobileCtx = await browser.newContext({ ...iphone });
    const mobilePage = await mobileCtx.newPage();

    await mobilePage.goto(linkCalc.url);
    await mobilePage.screenshot({ path: path.join(PROOF_DIR, '05-calculator-mobile.png'), fullPage: true });
    await mobilePage.tap('#tab-fixed');
    await mobilePage.fill('#daysLate', '25');
    await mobilePage.dispatchEvent('#daysLate', 'input');
    await mobilePage.screenshot({ path: path.join(PROOF_DIR, '06-calculator-mobile-interacted.png'), fullPage: true });
    const mobileAmount = await mobilePage.textContent('#resultAmount');
    console.log(`Mobile calculator after interaction shows: ${mobileAmount}`);

    await mobilePage.goto(linkMemo.url);
    await mobilePage.screenshot({ path: path.join(PROOF_DIR, '07-memo-mobile.png') });
    await mobilePage.tap('#c-ip .head');
    await mobilePage.screenshot({ path: path.join(PROOF_DIR, '08-memo-mobile-expanded.png') });
    await mobilePage.evaluate(() => window.scrollTo(0, 900));
    await mobilePage.screenshot({ path: path.join(PROOF_DIR, '09-memo-mobile-scrolled.png') });

    // Check for horizontal overflow (the classic "broke on a phone" symptom).
    const hasHorizontalScroll = await mobilePage.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    console.log(`Mobile memo page has horizontal overflow: ${hasHorizontalScroll}`);
    if (hasHorizontalScroll) throw new Error('Mobile layout overflows horizontally — this is exactly the failure mode the brief calls out.');

    await mobileCtx.close();

    if (desktopAmount === mobileAmount) {
      console.log('Desktop and mobile calculators agree after the same interaction — same page, same logic, both surfaces.');
    } else {
      throw new Error(`Desktop (${desktopAmount}) and mobile (${mobileAmount}) calculator results disagree.`);
    }
  } finally {
    await browser.close();
    server.close();
  }

  console.log(`\nScreenshots written to ${PROOF_DIR}`);
}

main().catch((err) => {
  console.error('Screenshot run failed:', err);
  process.exitCode = 1;
});
