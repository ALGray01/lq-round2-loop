// Exercises public/admin.html itself in a real browser — clicking buttons
// and reading the rendered table — rather than only hitting the JSON API
// directly the way demo.js and security-test.js do. This is the check that
// the operator dashboard a real lawyer would actually click through isn't
// just markup that was never wired up correctly.
'use strict';
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { createApp, getAdminToken } = require('../src/server');

const PORT = 3905;

let failures = 0;
function expect(cond, msg) {
  console.log(`  ${cond ? 'OK  ' : 'FAIL'} ${msg}`);
  if (!cond) failures += 1;
}

async function main() {
  const dbPath = path.join(__dirname, '..', 'data', 'db.json');
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  fs.writeFileSync(dbPath, JSON.stringify({ clients: [], documents: [], links: [] }, null, 2));
  const tokenFile = path.join(__dirname, '..', 'data', 'admin.token');
  if (fs.existsSync(tokenFile)) fs.unlinkSync(tokenFile);
  delete process.env.ADMIN_TOKEN;

  const app = createApp();
  const server = app.listen(PORT);
  await new Promise((r) => server.once('listening', r));
  const adminToken = getAdminToken();

  const browser = await chromium.launch();
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  try {
    await page.goto(`http://localhost:${PORT}/admin`);
    await page.fill('#token', adminToken);
    await page.click('#saveToken');
    await page.reload(); // admin.html auto-loads documents/links if a token is in localStorage
    await page.waitForTimeout(300);

    await page.fill('#clientName', 'Acme Corp (UI test)');
    await page.fill('#clientEmail', 'counsel@acme-corp.example');
    await page.click('#createClient');
    await page.waitForTimeout(200);

    await page.selectOption('#linkDoc', 'penalty-calculator');
    await page.fill('#ttl', '72');
    await page.click('#issueLink');
    await page.waitForTimeout(300);

    const rowCount = await page.locator('#linksBody tr').count();
    expect(rowCount === 1, `links table shows 1 row after issuing one link via the UI (saw ${rowCount})`);
    const rowText = await page.locator('#linksBody tr').first().innerText();
    expect(rowText.includes('Acme Corp (UI test)') && rowText.includes('active'), `issued row shows the right client and "active" status: ${rowText.replace(/\n/g, ' | ')}`);

    const revokeBtn = page.locator('#linksBody button[data-token]').first();
    expect((await revokeBtn.count()) === 1, 'an active row has exactly one Revoke button');
    await revokeBtn.click();
    await page.waitForTimeout(300);
    const afterRevoke = await page.locator('#linksBody tr').first().innerText();
    expect(afterRevoke.includes('revoked'), `row shows "revoked" after clicking Revoke in the UI: ${afterRevoke.replace(/\n/g, ' | ')}`);
    expect((await page.locator('#linksBody button[data-token]').count()) === 0, 'revoked row no longer has a Revoke button');

    expect(consoleErrors.length === 0, `no browser console/page errors during the whole flow (saw ${consoleErrors.length}): ${JSON.stringify(consoleErrors)}`);
  } finally {
    await browser.close();
    server.close();
  }

  console.log(`\n${failures === 0 ? 'ALL ADMIN-UI CHECKS PASSED' : failures + ' ADMIN-UI CHECK(S) FAILED'}`);
  if (failures > 0) process.exitCode = 1;
}
main().catch((e) => { console.error(e); process.exitCode = 1; });
