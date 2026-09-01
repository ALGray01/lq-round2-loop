# Explainer link delivery layer

A small server that turns an interactive HTML legal explainer into a
per-client, access-controlled link: token-gated, mobile-rendering, and
revocable. Built for OQ-130.

The problem it solves: lawyers now ship interactive HTML one-pagers
(calculators, clause-by-clause commentary) instead of Word docs, but there's
no good way to *deliver* one to a specific client — email strips scripts and
styling, attachments don't render on a phone, and putting the file on public
hosting leaks it to anyone with the URL. This repo is the missing delivery
layer: an admin issues a link tied to one client and one document, the client
opens it in a normal browser (desktop or phone, no app, no download), and the
admin can kill that specific link at any time without touching anyone else's.

## What's actually here

- **`server.js` / `src/server.js`** — an Express server with two route groups:
  - `/admin/*` — protected by a static admin token (`x-admin-token` header),
    used to create clients, issue links, list links, and revoke links.
  - `/d/:token` — the client-facing route. No login, no account — the token
    *is* the access control.
- **`src/store.js`** — a JSON-file-backed store (`data/db.json`) for clients,
  documents, and links. Not a database; this is scoped to prove the access-
  control model, not to be a production persistence layer (see Limitations).
- **`content/`** — the two real explainers, each a single self-contained HTML
  file (inline CSS/JS, no external assets to leak):
  - `penalty-calculator.html` — an interactive liquidated-damages calculator
    (toggle between percentage-of-value and fixed-fee-per-day penalty
    structures, live total, cap visualization, clause text toggle).
  - `service-agreement-memo.html` — a six-clause, clause-by-clause memo with
    collapsible sections, risk badges (Low/Medium/High), a sticky
    jump-to-section nav, and a toggle to reveal the original clause text
    next to the plain-English commentary.
- **`public/admin.html`** — a minimal operator dashboard (create client, issue
  link, see status, revoke) that talks to the `/admin/*` API. Not linked from
  anywhere client-facing.
- **`scripts/demo.js`** — drives the whole lifecycle over real HTTP against a
  live instance of the server: issue two links, open them as a simulated
  desktop and phone client, revoke one, exhaust a burn-after-reading one,
  expire one by time, then attack it (forged token, path traversal, direct
  content access, wrong admin token). Prints every status code it got and
  fails loudly (non-zero exit) if any expectation is violated.
- **`scripts/security-test.js`** — a separate, more adversarial pass: path
  traversal variants (including double-encoding and embedded null bytes),
  injection-shaped tokens, cross-client isolation, admin-auth bypass attempts,
  a genuine 15-way concurrent-request race against a single-view link
  (checking the server doesn't over-count views under real concurrency, not
  just in theory), and a 70-request burst against one link confirming the
  per-IP rate limiter actually returns `429`s rather than just existing in
  code and never firing.
- **`scripts/admin-ui-check.js`** — drives `public/admin.html` itself in a
  real browser (fills fields, clicks buttons, reads the rendered table) to
  confirm the operator dashboard a lawyer would actually click through is
  correctly wired to the API, not just markup that looks right. Checks for
  zero browser console errors across the whole flow.
- **`scripts/screenshot.js`** — opens both links in a real headless Chromium
  browser (Playwright, not a hand-rolled HTTP client) at a real desktop
  viewport (1440×900) and a real iPhone 13 device profile (viewport, UA,
  touch, device pixel ratio), interacts with each (flips the calculator mode,
  expands a memo section), and saves the result to `proof/*.png`. Also checks
  for horizontal overflow on the mobile viewport — the concrete symptom of
  "broke on a phone."

## How to run it

```bash
npm install
node server.js
# → prints the URL and the admin token to use in the x-admin-token header
```

Then either drive it by hand (`curl` / the admin token) or open
`http://localhost:3000/admin`, paste the printed admin token, create a
client, and issue a link.

To see the automated proof:

```bash
node scripts/demo.js           # full lifecycle over real HTTP, prints every check
node scripts/security-test.js  # adversarial input / auth-bypass / race-condition checks
node scripts/screenshot.js     # real-browser desktop + phone screenshots -> proof/
node scripts/admin-ui-check.js # drives public/admin.html itself in a real browser
```

All four scripts start their own server instance on a private port and
reset `data/db.json` first, so they're safe to re-run and don't depend on
`node server.js` already running.

## Where the content lives

Both explainers live on the server's local disk under `content/`, as plain
files. That directory is **never mounted as a static route** — there is no
`express.static('content')` anywhere, and `app.use('/content', ...)` is
explicitly wired to return 404 unconditionally (`src/server.js`). The only
code path that ever reads a file from `content/` is the `/d/:token` handler,
and only after `store.validateLink()` has returned `ok: true`. There is no
URL, however constructed, that reaches a document's bytes without first
passing through that check. `security-test.js` attacks this directly (path
traversal, direct-path requests) rather than just asserting it by reading the
code.

## Who can reach it

Each link is one cryptographically random 256-bit token
(`crypto.randomBytes(32).toString('base64url')`), bound at issue time to
exactly one client and one document. There's no way to derive one client's
token from another's, and no enumeration surface — `/d/:token` validates the
token against a strict `^[A-Za-z0-9_-]{20,80}$` grammar *before* any lookup,
so malformed input never reaches the store, let alone a filesystem path. A
per-IP rate limiter (`src/rateLimit.js`) throttles `/d/:token` as defense in
depth, though the token space alone already makes brute-forcing infeasible.
Every response carries `Cache-Control: no-store`, `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, and `X-Robots-Tag: noindex` so a shared
device, a proxy cache, or a search crawler doesn't become a second copy of
the document. The admin API is gated separately by a static token compared
via SHA-256 digests fed through `crypto.timingSafeEqual` (hashing first, so
both operands are always 32 bytes — comparing the raw strings would require
a length check *before* the constant-time compare, and that branch itself
leaks whether a guess has the right length), generated fresh per install
(`data/admin.token`, gitignored — never in the repo) unless overridden via
`ADMIN_TOKEN`.

**Deploying behind a reverse proxy:** the rate limiter keys on `req.ip`,
which by default is the raw socket address. Behind a TLS-terminating reverse
proxy (the deployment this README's own Limitations section recommends),
Express would report every real client as the proxy's one IP unless told
otherwise — collapsing the per-client rate limit into one shared bucket for
*all* clients on *all* links, a real client-facing denial-of-service. Set
`TRUST_PROXY` (a hop count, per [Express's `trust proxy`
setting](https://expressjs.com/en/guide/behind-proxies.html)) to match your
topology. Left unset by default rather than defaulting to `true`, because
trusting `X-Forwarded-For` blindly would let a direct client spoof their own
IP and bypass the rate limiter entirely — the correct value is
deployment-specific and there's no safe one-size-fits-all default.

## How a link dies

Three independent mechanisms, all enforced in `store.validateLink()` and all
exercised by `demo.js` against a running server (not merely reasoned about):

1. **Explicit revoke** — `POST /admin/links/:token/revoke` flips `revoked:
   true` on that one link. Every other link for that client, or for anyone
   else, is untouched. Once revoked, the link returns `410 Gone` forever —
   confirmed live in `demo.js` step 5.
2. **Expiry** — an optional TTL set at issue time (`ttlHours`). Past
   `expiresAt`, the link returns `410` regardless of revoke status —
   confirmed in `demo.js` step 7 by issuing a link whose TTL is already in
   the past.
3. **Burn-after-reading** — an optional `maxViews` (e.g. `1`). Once the view
   count reaches the limit, the link returns `410` even though it was never
   explicitly revoked and hasn't expired — confirmed in `demo.js` step 4, and
   stress-tested under 15-way concurrency in `security-test.js` (exactly 1 of
   15 simultaneous requests against a fresh `maxViews: 1` link succeeds; the
   route handler runs synchronously start-to-finish per request in Node's
   event loop, so there's no `await` gap between the validity check and the
   view-count increment for two requests to race through).

In all three cases the response is a generic "link unavailable" page, not a
404-vs-410 tell that would help someone distinguish "wrong guess" from "right
guess, but dead" — except that dead links legitimately *do* return 410 with a
specific reason (revoked / expired / view limit) shown to the person holding
the link, since that's meaningfully better UX for a confused client and the
256-bit token space makes probing moot either way.

## Proving it on both surfaces

`proof/` contains real Chromium screenshots (via Playwright, not a
description of expected behavior) for both explainers on a 1440×900 desktop
viewport and an iPhone 13 profile (device pixel ratio, touch, mobile UA,
390×844 viewport):

| File | What it shows |
|---|---|
| `01-02` | Calculator, desktop, before/after switching modes and changing days-late |
| `03-04` | Memo, desktop, collapsed and with a clause expanded + original text shown |
| `05-06` | Calculator, phone, before/after the same interaction as desktop |
| `07-09` | Memo, phone, collapsed / expanded / scrolled |

`screenshot.js` also asserts, against the live page (not just visually):
desktop and mobile arrive at the identical calculated total after the same
interaction, and the mobile memo page has zero horizontal scroll overflow —
the precise "attachment breaks on a phone" failure this whole project exists
to avoid.

**A bug the screenshots themselves caught:** the calculator's "cap applied"
badge used `element.hidden = true/false` for visibility, but the badge's own
CSS class also sets `display: inline-block`. Author CSS always overrides the
browser's default `[hidden] { display: none }` rule regardless of
specificity, so the badge was showing on every load regardless of whether the
cap actually applied. The first screenshot run caught it (badge visible at
$11,250 against a $12,000 cap, which is *below* the cap); fixed by toggling
`style.display` directly instead of the `hidden` attribute, and re-verified
by re-running the screenshot script. This is the kind of thing "looks right
reading the code" would have missed and only actually rendering it caught.

## The test scripts were checked against a true negative

Before trusting `demo.js`/`security-test.js` as evidence, I deliberately
broke the thing they claim to verify: commented out the `revoked` check in
`store.validateLink()` (`src/store.js`) so a revoked link would keep serving
content, then re-ran `demo.js`. It failed correctly — `FAIL calculator link
now returns 200 (dead) after revoke`, exit code 1 — then the change was
reverted and the suite re-run clean (`git diff` after reverting shows
`store.js` byte-identical to the committed version). This is the check for
"a scorer that's wrong in its own favor": these scripts do fail when the
underlying behavior is actually broken, not just when nothing has been
tried.

## Independent three-persona audit

Once the above was built and passing, three fresh agents with no prior
context audited this repo independently and in parallel, each running real
attacks/checks against a live instance rather than reading and reasoning:
an **attacker** (crafted input against every access-control surface), a
**verification skeptic** (hunting for hollow/circular checks), and a
**baseline builder** (the JSON-vs-in-memory comparison above). What they
found and what happened as a result:

- **Fixed — rate-limiter trust-proxy gap.** The attacker found that
  `req.ip`, unconfigured, would collapse to one shared IP for every client
  behind the reverse proxy this README itself recommends, turning the
  per-client rate limit into an accidental shared-bucket DoS. Added the
  `TRUST_PROXY` env var (documented above under "Who can reach it") rather
  than a default, since the correct value is deployment-topology-specific
  and a wrong default (`true`) would let a direct client spoof
  `X-Forwarded-For` and defeat the limiter entirely.
- **Fixed — admin-token timing oracle.** The attacker measured a
  consistent ~40–70µs timing gap in `timingSafeEqualStr` between
  wrong-length and right-length guesses (it checked buffer length before
  calling `crypto.timingSafeEqual`, and that check itself isn't
  constant-time across the branch). Fixed by hashing both sides to a fixed
  32 bytes first, removing the length signal entirely, not just making each
  branch internally constant-time.
- **Fixed — a test that would pass even if its own guard were deleted.**
  The skeptic found that `security-test.js`'s traversal/injection
  assertions accepted `400 OR 404`, so disabling the token-grammar regex
  entirely (verified live: I did it, re-ran the suite, watched it still
  print `ALL SECURITY CHECKS PASSED`) went undetected — the deeper
  architectural defense (content is never looked up by raw URL) still held,
  but the test no longer isolated *why*. Tightened both blocks to require
  exactly `400`, re-broke the regex the same way, confirmed the suite now
  fails (`12 SECURITY CHECK(S) FAILED`), then reverted and confirmed it
  passes clean again.
- **Accepted, documented, not fixed — token lookup isn't constant-time.**
  `store.getLink` does a plain `Array.find`/`===` scan, unlike the
  hash-then-compare admin path. With 256 bits of entropy per token and real
  network jitter, this isn't a practically exploitable channel — the
  attacker's own report rates it low/informational — and closing it (e.g.
  hashing every stored token for comparison) would be complexity
  disproportionate to the actual risk. Noted here rather than silently
  left as a gap nobody flagged.
- **Nothing else exploitable found.** The attacker's other traversal/
  injection/case-sensitivity/oversized-token attempts and the skeptic's
  re-runs of `demo.js`/`security-test.js`/`admin-ui-check.js` against
  unmodified code, plus two more deliberate true-negative breaks (disabling
  the `maxViews` check and the rate limiter itself, both correctly caught
  by the existing scripts), found no further defects.

## Limitations, honestly

- **JSON-file store, not a database — and it gets measurably slower with
  scale, not just unsafe across processes.** `data/db.json` is
  `JSON.parse`d and re-`JSON.stringify`d **in full** on every single
  request, regardless of which one link is touched. A head-to-head
  benchmark against a naive in-memory `Map`-backed version of the exact
  same store interface (same API, zero disk I/O — built specifically to
  test this claim, not asserted) measured, at 200 ops per size:

  | links in `db.json` | file size | file store | in-memory | gap |
  |---|---|---|---|---|
  | 10 | 13.5 KB | 9.3 ms/op | 0.0035 ms/op | ~2700x |
  | 200 | 253 KB | 13.2 ms/op | 0.0100 ms/op | ~1300x |
  | 1,000 | 1.26 MB | 26.9 ms/op | 0.0288 ms/op | ~930x |
  | 5,000 | 6.31 MB | 99.3 ms/op | 0.184 ms/op | ~540x |
  | 20,000 | 25.3 MB | 443.8 ms/op | 1.144 ms/op | ~390x |

  At demo scale (tens of links) the cost is imperceptible, but it is not
  flat — it grows roughly with total accumulated link count (every past
  link's full `accessLog` gets re-parsed and re-written on every request),
  and 5,000–20,000 issued links is a plausible one-firm, one-year volume
  with zero multi-process deployment required. So "fine at this scale" was
  true but incomplete: a single, correctly-behaving process still degrades
  from ordinary link-issuing volume alone, well before anyone adds a load
  balancer. The naive in-memory alternative has no such growth curve and is
  380–2700x faster in this benchmark — at the cost of losing all data on
  every restart, which is a real tradeoff, not a free win. A real deployment
  wanting both durability and flat per-request cost needs an actual
  database (Postgres/SQLite with indexed lookups), not either of these two.
  The concurrency-safety claim (the race test passing) is separately still
  accurate and unaffected by this — it's specifically the *latency-at-scale*
  half of the store's story that this repo hadn't measured until now.
  Would not survive multiple server processes (e.g. behind a load balancer)
  writing concurrently regardless of the above — that claim was already
  accurate and stands unchanged.
- **No transport encryption in this repo.** The server speaks plain HTTP on
  localhost. A real deployment puts this behind TLS (nginx/Caddy reverse
  proxy or a platform that terminates TLS) — token-bearing URLs must never
  travel in the clear. Not implemented here because it's infrastructure, not
  application logic, and would just be a self-signed cert with no
  independent verification value in this environment.
- **Delivery of the link itself (email/SMS to the client) is out of scope.**
  This repo builds and proves the link's access control and rendering; it
  assumes the firm sends the URL to the client through whatever channel they
  already use for a one-line message (which is the whole point — a link,
  unlike an HTML attachment, survives any of those channels intact).
- **No audit UI beyond the raw access log.** `link.accessLog` records
  timestamp, IP, user-agent, and a mobile/desktop guess per view, and the
  admin API exposes it, but there's no dashboard rendering it as a timeline —
  `public/admin.html` only shows view counts, not the full log.
- **Admin auth is a single shared static token**, not per-operator accounts.
  Adequate for "one firm, one admin, prove the model"; a real multi-lawyer
  deployment needs per-user admin accounts and per-user audit trail on who
  issued/revoked which link.
- **The two explainers are original content written for this exercise**,
  modeled on real liquidated-damages and MSA clause patterns but not sourced
  from an actual client engagement — there was no real client document
  available to digitize in this environment. The delivery/access-control
  layer around them is what's being demonstrated and is exercised identically
  regardless of which HTML file it's asked to gate.
- **`bash` is broken in this sandbox** (a Cygwin shared-library load failure
  unrelated to this project), so all commands in this session ran through
  PowerShell instead of the `retry.sh`/`lib/retry.sh` helper referenced in
  the session's standing instructions. The one network-dependent step
  (`npx playwright install chromium`) succeeded on the first attempt; had it
  failed, the fallback would have been to skip Playwright screenshots and
  rely solely on `demo.js`'s real HTTP-level proof, noted here rather than
  silently.
