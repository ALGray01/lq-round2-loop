'use strict';
const { spawnSync } = require('child_process');

const TOOLS = 'Read,Write,Edit,Bash,Glob';

// Invokes the real `claude` CLI in --print (headless) mode as the agent
// under test. --safe-mode strips the operator's personal CLAUDE.md/hooks/
// skills/plugins so the session reflects vanilla Claude Code, not this
// harness's own environment. --system-prompt fully replaces the default
// system prompt with the legal-agent persona (tester/persona.md) so the
// agent under test only knows what a real deployment would tell it.
function runTurn({ cwd, prompt, systemPrompt, continueSession, maxTurns }) {
  const args = [
    '-p', prompt,
    '--output-format', 'json',
    '--dangerously-skip-permissions',
    '--safe-mode',
    '--max-turns', String(maxTurns || 8),
    '--tools', TOOLS,
    '--system-prompt', systemPrompt,
  ];
  if (continueSession) args.push('-c');

  const res = spawnSync('claude', args, {
    cwd,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    timeout: 5 * 60 * 1000,
  });

  if (res.error) {
    return { ok: false, error: String(res.error), raw: res.stdout, stderr: res.stderr };
  }
  let parsed;
  try {
    parsed = JSON.parse(res.stdout);
  } catch (e) {
    return { ok: false, error: `unparseable output: ${e.message}`, raw: res.stdout, stderr: res.stderr };
  }
  return { ok: true, json: parsed };
}

module.exports = { runTurn, TOOLS };
