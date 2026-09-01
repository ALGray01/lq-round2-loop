// Tiny in-memory sliding-window rate limiter. Token space is 256 bits, so
// brute-forcing a valid token is not a realistic threat on its own — this is
// defense in depth against scripted probing of /d/:token, not the primary
// access control (that's the token itself).
'use strict';

function makeLimiter({ windowMs, max }) {
  const hits = new Map(); // ip -> [timestamps]

  return function rateLimit(req, res, next) {
    const ip = req.ip;
    const now = Date.now();
    const arr = (hits.get(ip) || []).filter((t) => now - t < windowMs);
    arr.push(now);
    hits.set(ip, arr);
    if (arr.length > max) {
      res.status(429).send('Too many requests. Try again shortly.');
      return;
    }
    next();
  };
}

module.exports = { makeLimiter };
