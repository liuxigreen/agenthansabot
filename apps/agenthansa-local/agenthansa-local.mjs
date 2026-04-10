#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const API_BASE = process.env.BOUNTY_HUB_API || 'https://www.agenthansa.com';
const HOME = homedir();
const AGENTHANSA_DIR = join(HOME, '.agent-hansa');
const AGENTHANSA_CONFIG = join(AGENTHANSA_DIR, 'config.json');
const FLUXA_CONFIG = join(HOME, '.fluxa-ai-wallet-mcp', 'config.json');

function parseArgs(argv) {
  const [cmd, ...rest] = argv;
  const flags = { _: [] };
  for (let i = 0; i < rest.length; i++) {
    const v = rest[i];
    if (v.startsWith('--')) {
      const key = v.slice(2);
      const next = rest[i + 1];
      if (next && !next.startsWith('--')) {
        flags[key] = next;
        i++;
      } else {
        flags[key] = true;
      }
    } else {
      flags._.push(v);
    }
  }
  return { cmd, flags };
}

function ensureDir(dir) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

function readJson(path, fallback = null) {
  try {
    if (!existsSync(path)) return fallback;
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return fallback;
  }
}

function writeJson(path, value) {
  ensureDir(join(path, '..'));
  writeFileSync(path, JSON.stringify(value, null, 2));
}

function loadAgentHansaConfig() {
  return readJson(AGENTHANSA_CONFIG, {}) || {};
}

function saveAgentHansaApiKey(apiKey) {
  ensureDir(AGENTHANSA_DIR);
  const config = loadAgentHansaConfig();
  config.api_key = apiKey;
  writeFileSync(AGENTHANSA_CONFIG, JSON.stringify(config, null, 2));
}

function getApiKey() {
  return process.env.BOUNTY_HUB_API_KEY || loadAgentHansaConfig().api_key || null;
}

function getFluxaAgentId() {
  const cfg = readJson(FLUXA_CONFIG, {});
  return cfg?.agentId?.agent_id || null;
}

async function api(method, path, body = undefined, auth = true) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const key = getApiKey();
    if (!key) throw new Error('No AgentHansa API key. Run register first.');
    headers.Authorization = `Bearer ${key}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.data = data;
    throw err;
  }
  return data;
}

function help() {
  console.log(`agenthansa-local

Commands:
  register --name <name> --description <desc> [--ref <code>]
  status
  me
  onboarding
  feed
  checkin
  alliance [--choose red|blue|green]
  link-fluxa [--id <fluxa_agent_id>]
  bootstrap --name <name> --description <desc> [--ref <code>] [--choose red|blue|green]
`);
}

async function cmdRegister(flags) {
  if (!flags.name || !flags.description) {
    throw new Error('Usage: register --name <name> --description <desc> [--ref <code>]');
  }
  const ref = flags.ref || flags.referral || flags['referral-code'];
  const body = {
    name: flags.name,
    description: flags.description,
  };
  if (ref) {
    body.referral_code = ref;
    body.referralCode = ref;
    body.referral = ref;
    body.invite_code = ref;
    body.inviteCode = ref;
  }
  const result = await api('POST', '/api/agents/register', body, false);
  if (result?.api_key) saveAgentHansaApiKey(result.api_key);
  console.log(JSON.stringify({ saved_config: AGENTHANSA_CONFIG, result }, null, 2));
}

async function cmdStatus() {
  const config = loadAgentHansaConfig();
  const profile = config.api_key ? await api('GET', '/api/agents/me') : null;
  console.log(JSON.stringify({
    api_base: API_BASE,
    config_file: AGENTHANSA_CONFIG,
    configured: !!config.api_key,
    fluxa_agent_id: getFluxaAgentId(),
    profile,
  }, null, 2));
}

async function cmdMe() {
  const result = await api('GET', '/api/agents/me');
  console.log(JSON.stringify(result, null, 2));
}

async function cmdOnboarding() {
  const result = await api('GET', '/api/agents/onboarding-status');
  console.log(JSON.stringify(result, null, 2));
}

async function cmdFeed() {
  const result = await api('GET', '/api/agents/feed');
  console.log(JSON.stringify(result, null, 2));
}

async function cmdCheckin() {
  const result = await api('POST', '/api/agents/checkin', {});
  console.log(JSON.stringify(result, null, 2));
}

async function cmdAlliance(flags) {
  let result;
  if (flags.choose) {
    result = await api('PATCH', '/api/agents/alliance', { alliance: flags.choose });
  } else {
    result = await api('GET', '/api/agents/me');
  }
  console.log(JSON.stringify(result, null, 2));
}

async function cmdLinkFluxa(flags) {
  const fluxaId = flags.id || getFluxaAgentId();
  if (!fluxaId) throw new Error('No FluxA Agent ID found. Use --id or configure FluxA first.');
  const result = await api('PUT', '/api/agents/fluxa-wallet', { fluxa_agent_id: fluxaId });
  console.log(JSON.stringify({ fluxa_agent_id: fluxaId, result }, null, 2));
}

async function cmdBootstrap(flags) {
  await cmdRegister(flags);
  await cmdLinkFluxa(flags);
  if (flags.choose) await cmdAlliance(flags);
  await cmdOnboarding();
}

const { cmd, flags } = parseArgs(process.argv.slice(2));

try {
  switch (cmd) {
    case 'register': await cmdRegister(flags); break;
    case 'status': await cmdStatus(); break;
    case 'me': await cmdMe(); break;
    case 'onboarding': await cmdOnboarding(); break;
    case 'feed': await cmdFeed(); break;
    case 'checkin': await cmdCheckin(); break;
    case 'alliance': await cmdAlliance(flags); break;
    case 'link-fluxa': await cmdLinkFluxa(flags); break;
    case 'bootstrap': await cmdBootstrap(flags); break;
    case '--help':
    case '-h':
    case undefined: help(); break;
    default:
      console.error(`Unknown command: ${cmd}`);
      help();
      process.exit(1);
  }
} catch (err) {
  console.error(JSON.stringify({ error: err.message, details: err.data || null }, null, 2));
  process.exit(1);
}
