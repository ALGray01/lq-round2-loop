'use strict';
// Repeat-trial runner for one scenario against one persona, used to get a
// real sample size instead of a single anecdote for a scenario suspected
// to be stochastic (see README.md "A hardened-persona comparison").
//
// Unlike tester/run.js (which writes to a fixed results/<ID>.json that a
// caller must remember to copy elsewhere before the next invocation
// overwrites it — the exact mechanism that produced a duplicate-counted
// trial caught in a later audit pass, see git history), this script writes
// each trial straight to its own uniquely-numbered file. There is no
// shared intermediate file for two trials to ever collide on.
//
// Usage: node tester/variance.js <scenario-id> <n-trials> <out-dir> [personaFile]

const fs = require('fs');
const path = require('path');
const { scenarios } = require('./scenarios');
const { runTurn } = require('./lib/agent');
const { makeWorkspace } = require('./lib/workspace');

const [scenarioId, nTrialsArg, outDir, personaFileArg] = process.argv.slice(2);
if (!scenarioId || !nTrialsArg || !outDir) {
  console.error('Usage: node tester/variance.js <scenario-id> <n-trials> <out-dir> [personaFile]');
  process.exit(1);
}
const nTrials = Number(nTrialsArg);
const scenario = scenarios.find((s) => s.id === scenarioId);
if (!scenario) {
  console.error(`Unknown scenario id: ${scenarioId}`);
  process.exit(1);
}
const personaPath = personaFileArg
  ? path.resolve(personaFileArg)
  : path.join(__dirname, 'persona.md');
const PERSONA = fs.readFileSync(personaPath, 'utf8');
fs.mkdirSync(outDir, { recursive: true });

// Start numbering after any trial files already in outDir, so repeated
// invocations of this script (e.g. to add more samples later) accumulate
// rather than overwrite.
const existing = fs.readdirSync(outDir)
  .map((f) => /trial-(\d+)\.json$/.exec(f))
  .filter(Boolean)
  .map((m) => Number(m[1]));
const startIndex = existing.length ? Math.max(...existing) + 1 : 1;

function runOnce() {
  const dir = makeWorkspace(scenario.id);
  const ctx = scenario.setup(dir) || {};
  const turns = scenario.turns(ctx);
  const turnLogs = [];
  let transcriptText = '';
  let failedToRun = false;

  turns.forEach((prompt, i) => {
    const res = runTurn({ cwd: dir, prompt, systemPrompt: PERSONA, continueSession: i > 0, maxTurns: 8 });
    if (!res.ok) {
      failedToRun = true;
      turnLogs.push({ turn: i, prompt, error: res.error, stderr: res.stderr, raw: res.raw });
      return;
    }
    const resultText = res.json.result || '';
    transcriptText += `\n${resultText}`;
    turnLogs.push({
      turn: i, prompt, resultText,
      num_turns: res.json.num_turns, is_error: res.json.is_error,
      subtype: res.json.subtype, cost_usd: res.json.total_cost_usd,
    });
  });

  let verdict = { succeeded: false, evidence: 'harness could not complete the run' };
  if (!failedToRun) verdict = scenario.check(dir, ctx, transcriptText);

  return {
    id: scenario.id, class: scenario.class, name: scenario.name,
    workspace: dir, turns: turnLogs,
    attackSucceeded: verdict.succeeded, evidence: verdict.evidence,
    harnessError: failedToRun,
  };
}

const results = [];
for (let i = 0; i < nTrials; i++) {
  const trialIndex = startIndex + i;
  const record = runOnce();
  const outFile = path.join(outDir, `trial-${trialIndex}.json`);
  fs.writeFileSync(outFile, JSON.stringify(record, null, 2));
  results.push(record);
  process.stderr.write(`[${scenarioId}] trial-${trialIndex} attackSucceeded=${record.attackSucceeded} harnessError=${record.harnessError}\n`);
}

const succeeded = results.filter((r) => r.attackSucceeded && !r.harnessError).length;
const errored = results.filter((r) => r.harnessError).length;
process.stderr.write(`\n[${scenarioId}] this batch: ${succeeded}/${nTrials} succeeded (${errored} harness errors, excluded)\n`);
