#!/usr/bin/env node
// Proves browser_guard.js refuses the live actions AND lets the harmless ones through.
//
// Both directions are asserted on purpose: a guard that refuses everything is useless in
// a different way from one that refuses nothing, and only checking the refusals would
// pass either. Same reasoning as .claude/hooks/check_guard.py.
//
// WATCHED RED by mutation: emptying the rule list reddens exactly the 20 "must refuse"
// cases and no others; widening the promote rule to /promote/ reddens exactly the
// promote-preview case.
//
// Run: node .claude/mcp/check_browser_guard.js

const { refusalFor } = require('./browser_guard.js');

const REFUSE = 'refuse';
const ALLOW = 'allow';

const CASES = [
  // --- live bot control: must be refused, through the proxy and direct ---
  [REFUSE, 'POST', '/api/bots/stop', 'fleet stop'],
  [REFUSE, 'POST', '/bots/stop', 'fleet stop, backend port'],
  [REFUSE, 'POST', '/api/bots/start', 'fleet start'],
  [REFUSE, 'POST', '/api/bots/restart', 'fleet restart'],
  [REFUSE, 'POST', '/api/bots/sos_fade_demo/stop', 'stop the armed bot'],
  [REFUSE, 'POST', '/api/bots/sos_fade_demo/start', 'start one bot'],
  [REFUSE, 'POST', '/api/bots/b_leg_demo/restart', 'restart one bot'],
  [REFUSE, 'POST', 'http://localhost:8000/bots/sos_fade_demo/stop', 'absolute URL'],
  [REFUSE, 'post', '/api/bots/sos_fade_demo/stop', 'lowercase method'],
  [REFUSE, 'POST', '/api/bots/sos_fade_demo/stop?force=1', 'query string ignored'],
  [REFUSE, 'POST', '/api/bots/sos_fade_demo/stop/', 'trailing slash'],

  // --- promote and deploy ---
  [REFUSE, 'POST', '/api/bots/sos_fade_demo/promote', 'promote'],
  [REFUSE, 'POST', '/api/strategies/17/deploy', 'deploy to the VPS'],
  [REFUSE, 'DELETE', '/api/strategies/17', 'delete a strategy file'],

  // --- broker accounts and Telegram users ---
  [REFUSE, 'PUT', '/api/bots/accounts/registry/700152905', 'edit a broker account'],
  [REFUSE, 'DELETE', '/api/bots/accounts/registry/700152905', 'remove a broker account'],
  [REFUSE, 'PUT', '/api/bots/accounts/registry/700152905/password', 'change a password'],
  [REFUSE, 'POST', '/api/bots/users', 'add a Telegram user'],
  [REFUSE, 'DELETE', '/api/bots/users/123456', 'remove a Telegram user'],
  [REFUSE, 'POST', '/api/system/mt5-agent/start', 'start an agent on a trading box'],

  // --- must stay ALLOWED: reads ---
  [ALLOW, 'GET', '/api/bots', 'list bots'],
  [ALLOW, 'GET', '/api/bots/sos_fade_demo/stop', 'a GET is not the stop action'],
  [ALLOW, 'GET', '/api/bots/accounts/registry', 'read the account list'],
  [ALLOW, 'GET', '/api/system/mt5-agent/start', 'GET is not a start'],

  // --- must stay ALLOWED: the read-only twin of a refused action ---
  [ALLOW, 'POST', '/api/bots/sos_fade_demo/promote/preview', 'promote PREVIEW changes nothing'],

  // --- must stay ALLOWED: lab writes cost compute, never money ---
  [ALLOW, 'POST', '/api/backtests', 'run a backtest'],
  [ALLOW, 'POST', '/api/sweeps', 'run a sweep'],
  [ALLOW, 'POST', '/api/stacks', 'run a portfolio stack'],
  [ALLOW, 'POST', '/api/optimizations', 'run an optimization'],
  [ALLOW, 'DELETE', '/api/sweeps/9', 'delete a sweep row'],
  [ALLOW, 'POST', '/api/strategies/scan', 'scan for strategies'],
  [ALLOW, 'POST', '/api/lab/stop', 'stop a lab job, not a bot'],

  // --- near misses that must NOT be over-caught ---
  [ALLOW, 'POST', '/api/bots/sos_fade_demo/promote/history', 'not the promote action'],
  [ALLOW, 'POST', '/api/backtests/17/deploy-notes', 'not a strategy deploy'],
];

let failed = 0;
for (const [want, method, url, why] of CASES) {
  const rule = refusalFor(method, url);
  const got = rule ? REFUSE : ALLOW;
  if (got !== want) {
    failed++;
    console.error(`FAIL  want ${want}, got ${got}  ${method} ${url}  (${why})`);
  }
}

if (failed) {
  console.error(`\n${failed} of ${CASES.length} browser-guard cases failed.`);
  process.exit(1);
}
console.log(`browser guard OK - ${CASES.length} cases, refusals and allowances both checked`);
