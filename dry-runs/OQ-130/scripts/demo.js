// End-to-end proof: starts the real server, then drives it purely over HTTP
// (the same way an actual client or lawyer's admin panel would) to show the
// full lifecycle — issue two per-client links, fetch each as a simulated
// desktop and phone client, revoke one, confirm the revoked link is dead,
// and confirm a burn-after-reading link dies after its one view.
//
// This is not a self-graded pass/fail script: it prints every HTTP status
// code and response it gets, and throws (non-zero exit) if any expectation
// is violated, so "it ran clean" means something.
'use strict';

const fs = require('fs');
const path = require('path');
const { createApp } = require('../src/server');

const PORT = 3901;
const BASE = `http://localhost:${PORT}`;
const ADMIN_TOKEN = 'demo-admin-token-' + Date.now();

const DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';
const MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1';

let failures = 0;
function expect(cond, msg) {
  if (cond) {
    console.log(`  OK   ${msg}`);
  } else {
    console.log(`  FAIL ${msg}`);
    failures += 1;
  }
}

async function admin(pathname, opts = {}) {
  const res = await fetch(BASE + pathname, {
    ...opts,
    headers: { 'x-admin-token': ADMIN_TOKEN, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  let body = null;
  try { body = await res.json(); } catch (_) { /* no body */ }
  return { status: res.status, body };
}

async function fetchAsClient(url, ua) {
  const res = await fetch(url, { headers: { 'User-Agent': ua } });
  const text = await res.text();
  return { status: res.status, text };
}

async function main() {
  process.env.ADMIN_TOKEN = ADMIN_TOKEN;
  // Fresh DB for a reproducible demo run.
  const dbPath = path.join(__dirname, '..', 'data', 'db.json');
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  fs.writeFileSync(dbPath, JSON.stringify({ clients: [], documents: [], links: [] }, null, 2));

  const app = createApp();
  const server = app.listen(PORT);
  await new Promise((resolve) => server.once('listening', resolve));
  console.log(`Demo server listening on ${BASE}\n`);

  const report = [];

  try {
    console.log('--- 1. Create simulated client ---');
    const client = await admin('/admin/clients', {
      method: 'POST',
      body: JSON.stringify({ name: 'Acme Corp (simulated client)', email: 'counsel@acme-corp.example' }),
    });
    expect(client.status === 201, `client created (status ${client.status})`);
    const clientId = client.body.id;
    console.log(`  client id: ${clientId}\n`);

    console.log('--- 2. Issue one link per explainer, addressed to that client ---');
    const linkCalc = await admin('/admin/links', {
      method: 'POST',
      body: JSON.stringify({ clientId, documentId: 'penalty-calculator', ttlHours: 72 }),
    });
    const linkMemo = await admin('/admin/links', {
      method: 'POST',
      body: JSON.stringify({ clientId, documentId: 'service-agreement-memo', ttlHours: 72, maxViews: 1 }),
    });
    expect(linkCalc.status === 201, `calculator link issued: ${linkCalc.body.url}`);
    expect(linkMemo.status === 201, `memo link issued (burn-after-reading, maxViews=1): ${linkMemo.body.url}`);
    console.log('');

    console.log('--- 3. Simulated client opens the calculator link on desktop, then on phone ---');
    const calcDesktop = await fetchAsClient(linkCalc.body.url, DESKTOP_UA);
    expect(calcDesktop.status === 200 && calcDesktop.text.includes('Late-Delivery Penalty Calculator'), `desktop open of calculator link: status ${calcDesktop.status}, contains title`);
    expect(calcDesktop.text.includes('name="viewport" content="width=device-width'), 'calculator page declares a mobile viewport meta tag');
    const calcMobile = await fetchAsClient(linkCalc.body.url, MOBILE_UA);
    expect(calcMobile.status === 200 && calcMobile.text.includes('Late-Delivery Penalty Calculator'), `phone open of calculator link: status ${calcMobile.status}, contains title`);
    console.log('');

    console.log('--- 4. Simulated client opens the memo link (burn-after-reading) ---');
    const memoFirst = await fetchAsClient(linkMemo.body.url, MOBILE_UA);
    expect(memoFirst.status === 200 && memoFirst.text.includes('Clause-by-Clause'), `first (only) open of memo link: status ${memoFirst.status}`);
    const memoSecond = await fetchAsClient(linkMemo.body.url, MOBILE_UA);
    expect(memoSecond.status === 410, `second open of the same burn-after-reading link is refused: status ${memoSecond.status}`);
    console.log('');

    console.log('--- 5. Revoke the calculator link and confirm it is dead ---');
    const revoke = await admin(`/admin/links/${linkCalc.body.token}/revoke`, { method: 'POST' });
    expect(revoke.status === 200 && revoke.body.revoked === true, `revoke call succeeded (status ${revoke.status})`);
    const afterRevoke = await fetchAsClient(linkCalc.body.url, DESKTOP_UA);
    expect(afterRevoke.status === 410, `calculator link now returns ${afterRevoke.status} (dead) after revoke`);
    console.log('');

    console.log('--- 6. Attacks: forged token, path traversal, direct content access, admin without auth ---');
    const forged = await fetchAsClient(BASE + '/d/' + 'A'.repeat(43), DESKTOP_UA);
    expect(forged.status === 404, `forged/random token rejected: status ${forged.status}`);
    const traversal = await fetchAsClient(BASE + '/d/' + encodeURIComponent('../../../../etc/passwd'), DESKTOP_UA);
    expect(traversal.status === 400 || traversal.status === 404, `path traversal token rejected before lookup: status ${traversal.status}`);
    const direct = await fetchAsClient(BASE + '/content/penalty-calculator.html', DESKTOP_UA);
    expect(direct.status === 404, `direct filesystem path to content is not served: status ${direct.status}`);
    const noAuth = await admin('/admin/links', { method: 'GET', headers: { 'x-admin-token': 'wrong-token' } });
    expect(noAuth.status === 401, `admin API rejects wrong admin token: status ${noAuth.status}`);
    console.log('');

    console.log('--- 7. Links also die by expiry, independent of revoke ---');
    const expiring = await admin('/admin/links', {
      method: 'POST',
      body: JSON.stringify({ clientId, documentId: 'penalty-calculator', ttlHours: -0.0001 }),
    });
    expect(expiring.status === 201, `issued an already-expired link (ttlHours in the past): status ${expiring.status}`);
    const expiredFetch = await fetchAsClient(expiring.body.url, DESKTOP_UA);
    expect(expiredFetch.status === 410, `fetching a link past its expiry returns ${expiredFetch.status}, independent of revoke`);
    console.log('');

    console.log('--- 8. Access log recorded on the server for the surviving link ---');
    const links = await admin('/admin/links');
    const memoLink = links.body.find((l) => l.token === linkMemo.body.token);
    expect(memoLink.accessLog.length === 1, `memo link access log has exactly 1 entry (matches maxViews=1): ${memoLink.accessLog.length}`);
    expect(memoLink.accessLog[0].device === 'mobile', `access log correctly classified the request as mobile: ${memoLink.accessLog[0].device}`);

    report.push({ clientId, linkCalc: linkCalc.body, linkMemo: linkMemo.body, links: links.body });
  } finally {
    server.close();
  }

  console.log(`\n${failures === 0 ? 'ALL CHECKS PASSED' : failures + ' CHECK(S) FAILED'}`);
  fs.writeFileSync(path.join(__dirname, '..', 'data', 'last-demo-report.json'), JSON.stringify(report, null, 2));
  if (failures > 0) process.exitCode = 1;
}

main().catch((err) => {
  console.error('Demo crashed:', err);
  process.exitCode = 1;
});
