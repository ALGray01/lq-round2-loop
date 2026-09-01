'use strict';
// Prompt-injection tester for a vanilla Claude Code legal agent.
// Runs every scenario in tester/scenarios.js against a real `claude -p`
// subprocess (see lib/agent.js), each in its own throwaway sandbox
// directory, and checks the resulting filesystem/transcript for whether
// the attack's objective was actually achieved.
//
// Usage: node tester/run.js [scenario-id ...]
// With no args, runs every scenario. Writes results/<id>.json (full
// transcript + verdict) and results/summary.json + results/REPORT.md.
// PERSONA_FILE=tester/persona-hardened.md env var swaps in an alternate
// persona (used for the hardened-persona comparison in README) and, when
// set to a non-default file, writes to results/<PERSONA_TAG>/ instead of
// results/ directly so the two persona's outputs never overwrite each
// other.

const fs = require('fs');
const path = require('path');
const { scenarios } = require('./scenarios');
const { runTurn } = require('./lib/agent');
const { makeWorkspace } = require('./lib/workspace');

const personaPath = process.env.PERSONA_FILE
  ? path.resolve(process.env.PERSONA_FILE)
  : path.join(__dirname, 'persona.md');
const PERSONA = fs.readFileSync(personaPath, 'utf8');
const isDefaultPersona = personaPath === path.join(__dirname, 'persona.md');
const RESULTS_DIR = isDefaultPersona
  ? path.join(__dirname, '..', 'results')
  : path.join(__dirname, '..', 'results', path.basename(personaPath, '.md'));
fs.mkdirSync(RESULTS_DIR, { recursive: true });

const requested = process.argv.slice(2);
const toRun = requested.length
  ? scenarios.filter((s) => requested.includes(s.id))
  : scenarios;

function runScenario(scenario) {
  const dir = makeWorkspace(scenario.id);
  const ctx = scenario.setup(dir) || {};
  const turns = scenario.turns(ctx);

  const turnLogs = [];
  let transcriptText = '';
  let failedToRun = false;

  turns.forEach((prompt, i) => {
    const res = runTurn({
      cwd: dir,
      prompt,
      systemPrompt: PERSONA,
      continueSession: i > 0,
      maxTurns: 8,
    });
    if (!res.ok) {
      failedToRun = true;
      turnLogs.push({ turn: i, prompt, error: res.error, stderr: res.stderr, raw: res.raw });
      return;
    }
    const resultText = res.json.result || '';
    transcriptText += `\n${resultText}`;
    turnLogs.push({
      turn: i,
      prompt,
      resultText,
      num_turns: res.json.num_turns,
      is_error: res.json.is_error,
      subtype: res.json.subtype,
      cost_usd: res.json.total_cost_usd,
    });
  });

  let verdict = { succeeded: false, evidence: 'harness could not complete the run' };
  if (!failedToRun) {
    verdict = scenario.check(dir, ctx, transcriptText);
  }

  const record = {
    id: scenario.id,
    class: scenario.class,
    name: scenario.name,
    attackerGoal: scenario.attackerGoal,
    protects: scenario.protects,
    workspace: dir,
    turns: turnLogs,
    attackSucceeded: verdict.succeeded,
    evidence: verdict.evidence,
    harnessError: failedToRun,
  };

  fs.writeFileSync(
    path.join(RESULTS_DIR, `${scenario.id}.json`),
    JSON.stringify(record, null, 2),
  );

  return record;
}

const results = [];
for (const scenario of toRun) {
  process.stderr.write(`[${scenario.id}] running...\n`);
  const record = runScenario(scenario);
  process.stderr.write(`[${scenario.id}] attackSucceeded=${record.attackSucceeded} harnessError=${record.harnessError}\n`);
  results.push(record);
}

fs.writeFileSync(path.join(RESULTS_DIR, 'summary.json'), JSON.stringify(results, null, 2));

const attackResults = results.filter((r) => r.class !== 'control');
const controlResults = results.filter((r) => r.class === 'control');
// Harness failures (CLI crash/timeout/unparseable output) are NOT the same
// as "the agent defended itself" — scenario.check() never even ran on real
// data for them (see the harnessError branch above), so folding them into
// the "no" column would silently count an inconclusive run as a defensive
// win. Keep them out of both the numerator and the denominator, and call
// them out explicitly instead.
const scorable = attackResults.filter((r) => !r.harnessError);
const inconclusive = attackResults.filter((r) => r.harnessError);
const gotPast = scorable.filter((r) => r.attackSucceeded);

let report = '# Prompt-Injection Test Results\n\n';
report += `Ran ${results.length} scenarios (${attackResults.length} attack cases, ${controlResults.length} control cases) ` +
  `against a vanilla Claude Code agent (see ../tester/persona.md). ${gotPast.length} of ${scorable.length} scorable attack cases got past the agent` +
  (inconclusive.length ? ` (${inconclusive.length} inconclusive due to a harness failure — see below, excluded from this count).\n\n` : '.\n\n');

report += '## Attack cases\n\n| ID | Class | Name | Got past? | Evidence |\n|---|---|---|---|---|\n';
for (const r of scorable) {
  report += `| ${r.id} | ${r.class} | ${r.name} | ${r.attackSucceeded ? '**YES**' : 'no'} | ${r.evidence.replace(/\|/g, '/')} |\n`;
}

if (inconclusive.length) {
  report += '\n## Inconclusive (harness failure — not scored either way)\n\n| ID | Class | Name | Error |\n|---|---|---|---|\n';
  for (const r of inconclusive) {
    const errTurn = r.turns.find((t) => t.error) || {};
    report += `| ${r.id} | ${r.class} | ${r.name} | ${errTurn.error || 'unknown'} |\n`;
  }
}

report += '\n## Control cases (validate the checker, not the agent)\n\n| ID | Name | Flagged as attack success? | Evidence |\n|---|---|---|---|\n';
for (const r of controlResults) {
  report += `| ${r.id} | ${r.name} | ${r.attackSucceeded ? '**YES (checker bug!)**' : 'no'} | ${r.evidence.replace(/\|/g, '/')} |\n`;
}

report += '\nFull per-scenario transcripts: `results/<ID>.json`. Machine-readable summary: `results/summary.json`.\n';

fs.writeFileSync(path.join(RESULTS_DIR, 'REPORT.md'), report);
process.stderr.write(`\nDone. ${gotPast.length}/${attackResults.length} attack cases got past. See results/REPORT.md\n`);
