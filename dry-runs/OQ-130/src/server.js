'use strict';

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const express = require('express');
const store = require('./store');
const { makeLimiter } = require('./rateLimit');

const CONTENT_DIR = path.join(__dirname, '..', 'content');
const PUBLIC_DIR = path.join(__dirname, '..', 'public');

// Admin token: read from env if set, otherwise from a locally-generated file
// under data/ (created on first boot, gitignored). Never checked into the repo.
const ADMIN_TOKEN_FILE = path.join(__dirname, '..', 'data', 'admin.token');
function getAdminToken() {
  if (process.env.ADMIN_TOKEN) return process.env.ADMIN_TOKEN;
  fs.mkdirSync(path.dirname(ADMIN_TOKEN_FILE), { recursive: true });
  if (!fs.existsSync(ADMIN_TOKEN_FILE)) {
    fs.writeFileSync(ADMIN_TOKEN_FILE, crypto.randomBytes(24).toString('base64url'), 'utf8');
  }
  return fs.readFileSync(ADMIN_TOKEN_FILE, 'utf8').trim();
}

// Token grammar for /d/:token — base64url only. Anything else (path
// separators, dots, encoded traversal sequences) is rejected before it ever
// reaches a lookup, let alone a filesystem path.
const TOKEN_RE = /^[A-Za-z0-9_-]{20,80}$/;

// Compare via fixed-length digests, not the raw strings: crypto.timingSafeEqual
// itself throws on mismatched lengths, so comparing raw strings of different
// lengths requires a length check first — and that check leaks, in constant
// time per branch but not across branches, whether a guess has the right
// length. Hashing first makes both inputs always 32 bytes, removing that
// signal entirely rather than just making each branch internally constant-time.
function timingSafeEqualStr(a, b) {
  const bufA = crypto.createHash('sha256').update(String(a)).digest();
  const bufB = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(bufA, bufB);
}

function isMobileUA(ua) {
  return /Mobile|Android|iPhone|iPad|iPod/i.test(ua || '');
}

function seedContent() {
  store.registerDocument({
    id: 'penalty-calculator',
    title: 'Late-Delivery Penalty Calculator',
    file: 'penalty-calculator.html',
  });
  store.registerDocument({
    id: 'service-agreement-memo',
    title: 'Service Agreement — Clause-by-Clause Memo',
    file: 'service-agreement-memo.html',
  });
}

function createApp() {
  seedContent();
  const app = express();
  app.disable('x-powered-by');

  // The per-IP rate limiter (below) keys on req.ip, which is the raw socket
  // address unless Express is told to trust a reverse proxy's X-Forwarded-For.
  // Left unset (the secure default), *every* real client behind a
  // TLS-terminating proxy — the exact deployment this README's Limitations
  // section recommends — would report as the proxy's one IP, collapsing the
  // rate limiter into a single shared bucket for all clients on all links: a
  // client-facing denial-of-service, not a security bypass. Set TRUST_PROXY
  // to the number of proxy hops in front of this app (per Express's
  // `trust proxy` setting) to fix that in a real deployment; never set it to
  // `true` unless every hop between the internet and this process is a proxy
  // you control, since that would let a client set its own X-Forwarded-For
  // and bypass the rate limiter entirely.
  if (process.env.TRUST_PROXY) {
    const n = Number(process.env.TRUST_PROXY);
    app.set('trust proxy', Number.isFinite(n) ? n : process.env.TRUST_PROXY);
  }

  app.use(express.json());

  // Baseline hardening headers on every response.
  app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('X-Robots-Tag', 'noindex, nofollow');
    next();
  });

  const adminToken = getAdminToken();

  function requireAdmin(req, res, next) {
    const supplied = req.get('x-admin-token') || '';
    if (!supplied || !timingSafeEqualStr(supplied, adminToken)) {
      return res.status(401).json({ error: 'unauthorized' });
    }
    next();
  }

  // ---- Admin API (issuing + revoking links) --------------------------------

  app.post('/admin/clients', requireAdmin, (req, res) => {
    const { name, email } = req.body || {};
    if (!name) return res.status(400).json({ error: 'name required' });
    const client = store.createClient({ name, email });
    res.status(201).json(client);
  });

  app.get('/admin/documents', requireAdmin, (req, res) => {
    res.json(store.listDocuments());
  });

  app.post('/admin/links', requireAdmin, (req, res) => {
    const { clientId, documentId, ttlHours, maxViews, note } = req.body || {};
    if (!clientId || !documentId) {
      return res.status(400).json({ error: 'clientId and documentId required' });
    }
    try {
      const link = store.issueLink({ clientId, documentId, ttlHours, maxViews, note });
      const base = `${req.protocol}://${req.get('host')}`;
      res.status(201).json({ ...link, url: `${base}/d/${link.token}` });
    } catch (err) {
      res.status(400).json({ error: err.message });
    }
  });

  app.get('/admin/links', requireAdmin, (req, res) => {
    const base = `${req.protocol}://${req.get('host')}`;
    const links = store.listLinks().map((l) => ({ ...l, url: `${base}/d/${l.token}` }));
    res.json(links);
  });

  app.post('/admin/links/:token/revoke', requireAdmin, (req, res) => {
    const link = store.revokeLink(req.params.token);
    if (!link) return res.status(404).json({ error: 'not_found' });
    res.json(link);
  });

  // Minimal admin dashboard (static, calls the API above with a token the
  // operator pastes in). Not linked from anywhere client-facing.
  app.get('/admin', (req, res) => {
    res.sendFile(path.join(PUBLIC_DIR, 'admin.html'));
  });

  // ---- Client-facing delivery route ----------------------------------------

  const dLimiter = makeLimiter({ windowMs: 60_000, max: 60 });

  app.get('/d/:token', dLimiter, (req, res) => {
    const { token } = req.params;
    if (!TOKEN_RE.test(token)) {
      return res.status(400).send(renderStatusPage('This link is malformed.'));
    }

    const result = store.validateLink(token);
    if (!result.ok) {
      const messages = {
        not_found: 'This link is not valid. Double-check the URL your firm sent you.',
        revoked: 'This link has been revoked by the sender and can no longer be used.',
        expired: 'This link has expired. Ask your firm to send a new one.',
        view_limit_reached: 'This link has already been used and cannot be opened again.',
      };
      return res.status(result.status).send(renderStatusPage(messages[result.reason]));
    }

    const { link } = result;
    const doc = store.getDocument(link.documentId);
    if (!doc) return res.status(404).send(renderStatusPage('The requested document no longer exists.'));

    const filePath = path.join(CONTENT_DIR, doc.file);
    if (!fs.existsSync(filePath)) {
      return res.status(500).send(renderStatusPage('The document could not be loaded.'));
    }

    store.recordAccess(token, {
      ip: req.ip,
      userAgent: req.get('user-agent') || '',
      device: isMobileUA(req.get('user-agent')) ? 'mobile' : 'desktop',
    });

    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, private');
    res.setHeader('Pragma', 'no-cache');
    res.type('html').send(fs.readFileSync(filePath, 'utf8'));
  });

  function renderStatusPage(message) {
    return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Link unavailable</title>
<style>
  body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f172a;color:#e2e8f0;
       display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:24px;}
  .card{max-width:420px;background:#1e293b;border-radius:12px;padding:32px;text-align:center;
        box-shadow:0 10px 30px rgba(0,0,0,.3);}
  h1{font-size:1.1rem;margin:0 0 8px;color:#f87171;}
  p{margin:0;line-height:1.5;color:#cbd5e1;}
</style></head><body><div class="card"><h1>Link unavailable</h1><p>${message}</p></div></body></html>`;
  }

  // Explicitly refuse to serve /content directly under any circumstance —
  // this is the "content never has a public path" guarantee, made testable.
  app.use('/content', (req, res) => res.status(404).send('Not found'));

  // Catch malformed bodies (e.g. broken JSON from express.json()) and any
  // other thrown error with a clean 400/500 instead of Express's default
  // HTML stack-trace page.
  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    const status = err.status || err.statusCode || 500;
    res.status(status).json({ error: status < 500 ? 'bad_request' : 'server_error' });
  });

  return app;
}

module.exports = { createApp, getAdminToken };
