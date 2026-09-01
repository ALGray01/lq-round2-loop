// Minimal JSON-file-backed data store for clients, documents, and access links.
// Deliberately not a database: the whole point of this exercise is the access-control
// model, not persistence engineering. Single-process, synchronous writes — fine for a
// demo/assessment scale, not for concurrent-writer production use.
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_PATH = path.join(__dirname, '..', 'data', 'db.json');

function emptyDb() {
  return { clients: [], documents: [], links: [] };
}

function load() {
  if (!fs.existsSync(DB_PATH)) {
    save(emptyDb());
  }
  const raw = fs.readFileSync(DB_PATH, 'utf8');
  return JSON.parse(raw);
}

function save(db) {
  fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
  fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2), 'utf8');
}

function newId(prefix) {
  return `${prefix}_${crypto.randomBytes(8).toString('hex')}`;
}

function newToken() {
  // 256 bits of entropy, URL-safe. Not sequential, not derived from any
  // client/document identifier, so a leaked token for one client reveals
  // nothing about anyone else's token.
  return crypto.randomBytes(32).toString('base64url');
}

// --- Clients ---------------------------------------------------------------

function createClient({ name, email }) {
  const db = load();
  const client = { id: newId('client'), name, email, createdAt: new Date().toISOString() };
  db.clients.push(client);
  save(db);
  return client;
}

function getClient(id) {
  return load().clients.find((c) => c.id === id) || null;
}

// --- Documents ---------------------------------------------------------------

function registerDocument({ id, title, file }) {
  const db = load();
  const existing = db.documents.find((d) => d.id === id);
  const doc = { id, title, file, createdAt: new Date().toISOString() };
  if (existing) {
    Object.assign(existing, doc);
  } else {
    db.documents.push(doc);
  }
  save(db);
  return doc;
}

function getDocument(id) {
  return load().documents.find((d) => d.id === id) || null;
}

function listDocuments() {
  return load().documents;
}

// --- Links (the actual access-control unit) --------------------------------

function issueLink({ clientId, documentId, ttlHours, maxViews, note }) {
  const db = load();
  if (!db.clients.find((c) => c.id === clientId)) throw new Error('unknown client');
  if (!db.documents.find((d) => d.id === documentId)) throw new Error('unknown document');

  const now = Date.now();
  const link = {
    token: newToken(),
    clientId,
    documentId,
    note: note || null,
    createdAt: new Date(now).toISOString(),
    expiresAt: ttlHours ? new Date(now + ttlHours * 3600 * 1000).toISOString() : null,
    maxViews: maxViews || null,
    viewCount: 0,
    revoked: false,
    revokedAt: null,
    accessLog: [],
  };
  db.links.push(link);
  save(db);
  return link;
}

function getLink(token) {
  return load().links.find((l) => l.token === token) || null;
}

function listLinks() {
  return load().links;
}

function revokeLink(token) {
  const db = load();
  const link = db.links.find((l) => l.token === token);
  if (!link) return null;
  link.revoked = true;
  link.revokedAt = new Date().toISOString();
  save(db);
  return link;
}

// Validate a token against every reason a link can be dead. Returns
// { ok: true, link } or { ok: false, status, reason, link? }.
function validateLink(token) {
  const link = getLink(token);
  if (!link) return { ok: false, status: 404, reason: 'not_found' };
  if (link.revoked) return { ok: false, status: 410, reason: 'revoked', link };
  if (link.expiresAt && Date.now() > Date.parse(link.expiresAt)) {
    return { ok: false, status: 410, reason: 'expired', link };
  }
  if (link.maxViews && link.viewCount >= link.maxViews) {
    return { ok: false, status: 410, reason: 'view_limit_reached', link };
  }
  return { ok: true, link };
}

function recordAccess(token, { ip, userAgent, device }) {
  const db = load();
  const link = db.links.find((l) => l.token === token);
  if (!link) return;
  link.viewCount += 1;
  link.accessLog.push({ at: new Date().toISOString(), ip, userAgent, device });
  save(db);
}

module.exports = {
  createClient,
  getClient,
  registerDocument,
  getDocument,
  listDocuments,
  issueLink,
  getLink,
  listLinks,
  revokeLink,
  validateLink,
  recordAccess,
};
