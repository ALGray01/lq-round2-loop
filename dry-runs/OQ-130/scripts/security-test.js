// Adversarial checks against the access-control layer. Each check sends a
// genuinely hostile input (not a friendly one written to pass) and asserts
// the specific defensive behavior, printing the real HTTP status/response
// observed. Exits non-zero if anything behaves unsafely.
'use strict';

const fs = require('fs');
const path = require('path');
const { createApp } = require('../src/server');

const PORT = 3904;
const BASE = `http://localhost:${PORT}`;
const ADMIN_TOKEN = 'sec-test-admin-' + Date.now();

let failures = 0;
function expect(cond, msg) {
  console.log(`  ${cond ? 'OK  ' : 'FAIL'} ${msg}`);
  if (!cond) failures += 1;
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

async function raw(pathname, opts = {}) {
  const res = await fetch(BASE + pathname, opts);
  const text = await res.text();
  return { status: res.status, text };
}

async function main() {
  process.env.ADMIN_TOKEN = ADMIN_TOKEN;
  const dbPath = path.join(__dirname, '..', 'data', 'db.json');
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  fs.writeFileSync(dbPath, JSON.stringify({ clients: [], documents: [], links: [] }, null, 2));

  const app = createApp();
  const server = app.listen(PORT);
  await new Promise((resolve) => server.once('listening', resolve));
  console.log(`Security-test server on ${BASE}\n`);

  const clientA = (await admin('/admin/clients', { method: 'POST', body: JSON.stringify({ name: 'Client A' }) })).body;
  const clientB = (await admin('/admin/clients', { method: 'POST', body: JSON.stringify({ name: 'Client B' }) })).body;
  const linkA = (await admin('/admin/links', { method: 'POST', body: JSON.stringify({ clientId: clientA.id, documentId: 'penalty-calculator' }) })).body;
  const linkB = (await admin('/admin/links', { method: 'POST', body: JSON.stringify({ clientId: clientB.id, documentId: 'service-agreement-memo' }) })).body;

  try {
    console.log('--- Path traversal variants against /d/:token ---');
    const traversalPayloads = [
      '../../../../etc/passwd',
      '..%2f..%2f..%2fetc%2fpasswd',
      '..%252f..%252f..%252fetc%252fpasswd', // double-encoded
      '....//....//etc/passwd',
      String.fromCharCode(0) + '../../etc/passwd', // embedded null byte
      'penalty-calculator.html', // guessing the real filename as if it were a token
      '..\\..\\..\\windows\\win32.ini',
    ];
    for (const payload of traversalPayloads) {
      const r = await raw('/d/' + encodeURIComponent(payload));
      // Every payload above contains a character outside the token grammar
      // (. / \ or a null byte) or exceeds its length bound, so it must be
      // rejected by TOKEN_RE specifically, before any store lookup — hence
      // exactly 400, never 404. Asserting 400-or-404 here would also pass if
      // the grammar check were deleted and the request instead fell through
      // to a "no such token" 404, which would obscure whether the guard is
      // actually the thing stopping traversal. Requiring exactly 400 closes
      // that gap.
      expect(r.status === 400, `payload ${JSON.stringify(payload)} -> ${r.status} (rejected by token grammar before any lookup)`);
      expect(!r.text.includes('root:') && !r.text.includes('[extensions]'), `payload ${JSON.stringify(payload)} response body contains no OS file contents`);
    }
    console.log('');

    console.log('--- XSS / injection payloads as tokens ---');
    const injectionPayloads = [
      '<script>alert(1)</script>',
      "' OR '1'='1",
      '${7*7}',
      '{{7*7}}',
      'a'.repeat(5000), // oversized token, DoS-shaped input
    ];
    for (const payload of injectionPayloads) {
      const r = await raw('/d/' + encodeURIComponent(payload));
      // Same reasoning as the traversal block: every payload here violates
      // the token grammar (disallowed characters, or the 80-char length cap
      // for the repeated-'a' payload), so it must be exactly 400.
      expect(r.status === 400, `injection payload -> ${r.status} (rejected by token grammar, not 200/500/404)`);
      expect(!r.text.includes('<script>alert(1)</script>'), 'payload is never reflected unescaped in the response body');
    }
    console.log('');

    console.log('--- Cross-client access: does client A\'s token do anything for client B\'s document? ---');
    const crossFetch = await raw('/d/' + linkA.token);
    expect(crossFetch.status === 200, 'link A opens its own (penalty-calculator) document');
    expect(!crossFetch.text.includes('Clause-by-Clause'), "link A's response does not contain client B's memo content");
    console.log('');

    console.log('--- Admin auth bypass attempts ---');
    const noHeader = await raw('/admin/links');
    expect(noHeader.status === 401, `admin route with no auth header at all -> ${noHeader.status}`);
    const emptyHeader = await raw('/admin/links', { headers: { 'x-admin-token': '' } });
    expect(emptyHeader.status === 401, `admin route with empty auth header -> ${emptyHeader.status}`);
    const prefixHeader = await raw('/admin/links', { headers: { 'x-admin-token': ADMIN_TOKEN + 'x' } });
    expect(prefixHeader.status === 401, `admin route with correct-token-plus-suffix -> ${prefixHeader.status}`);
    const truncHeader = await raw('/admin/links', { headers: { 'x-admin-token': ADMIN_TOKEN.slice(0, -1) } });
    expect(truncHeader.status === 401, `admin route with correct-token-minus-last-char -> ${truncHeader.status}`);
    console.log('');

    console.log('--- Revoked/expired links stay dead under repeated hammering ---');
    const burn = (await admin('/admin/links', { method: 'POST', body: JSON.stringify({ clientId: clientA.id, documentId: 'penalty-calculator', maxViews: 1 }) })).body;
    await raw('/d/' + burn.token); // consume the single view
    let deadHits = 0;
    for (let i = 0; i < 5; i++) {
      const r = await raw('/d/' + burn.token);
      if (r.status === 410) deadHits += 1;
    }
    expect(deadHits === 5, `link with exhausted view budget stays dead across 5 repeated requests (${deadHits}/5 returned 410)`);
    console.log('');

    console.log('--- Race condition: concurrent requests against a fresh maxViews=1 link ---');
    const race = (await admin('/admin/links', { method: 'POST', body: JSON.stringify({ clientId: clientA.id, documentId: 'penalty-calculator', maxViews: 1 }) })).body;
    const concurrent = await Promise.all(Array.from({ length: 15 }, () => raw('/d/' + race.token)));
    const successes = concurrent.filter((r) => r.status === 200).length;
    expect(successes === 1, `exactly 1 of 15 concurrent requests against a maxViews=1 link succeeded (got ${successes})`);
    console.log('');

    console.log('--- Per-IP rate limiting on /d/:token actually engages ---');
    // Placed last among /d/:token checks deliberately: this test's whole
    // point is to exhaust this IP's rate-limit budget, which would make any
    // check placed after it unreliable.
    const rateLimited = (await admin('/admin/links', { method: 'POST', body: JSON.stringify({ clientId: clientA.id, documentId: 'penalty-calculator' }) })).body;
    const burst = await Promise.all(Array.from({ length: 70 }, () => raw('/d/' + rateLimited.token)));
    const tooMany = burst.filter((r) => r.status === 429).length;
    expect(tooMany > 0, `sending 70 requests for one link in quick succession triggers 429 on at least some of them (got ${tooMany})`);
    console.log('');

    console.log('--- Malformed admin payloads do not crash the server ---');
    const malformed = await raw('/admin/links', {
      method: 'POST',
      headers: { 'x-admin-token': ADMIN_TOKEN, 'Content-Type': 'application/json' },
      body: '{not valid json',
    });
    expect(malformed.status === 400 || malformed.status === 500, `malformed JSON body -> ${malformed.status} (handled, not a hang)`);
    const stillAlive = await raw('/admin/documents', { headers: { 'x-admin-token': ADMIN_TOKEN } });
    expect(stillAlive.status === 200, 'server still responds normally after the malformed request');
  } finally {
    server.close();
  }

  console.log(`\n${failures === 0 ? 'ALL SECURITY CHECKS PASSED' : failures + ' SECURITY CHECK(S) FAILED'}`);
  if (failures > 0) process.exitCode = 1;
}

main().catch((err) => {
  console.error('Security test crashed:', err);
  process.exitCode = 1;
});
