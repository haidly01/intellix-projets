#!/usr/bin/env node
/**
 * Tests d'intention extraits de conversation_sofia_process.js (source unique).
 * Échoue si detectIntent/normTranscript ne peuvent pas être lus depuis lib/.
 */
import fs from 'fs';
import vm from 'vm';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LIB = path.resolve(__dirname, '../lib/conversation_sofia_process.js');
const FIXTURES = path.resolve(__dirname, 'golden_transcripts.json');

function extractFunction(src, name) {
  const start = src.indexOf(`function ${name}`);
  if (start < 0) throw new Error(`function ${name} introuvable dans ${LIB}`);
  let i = src.indexOf('{', start);
  let depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error(`function ${name} non fermée`);
}

function loadIntentEngine() {
  const src = fs.readFileSync(LIB, 'utf8');
  const normSrc = extractFunction(src, 'normTranscript');
  const detectSrc = extractFunction(src, 'detectIntent');
  const sandbox = {};
  vm.createContext(sandbox);
  vm.runInContext(`${normSrc}\n${detectSrc}`, sandbox);
  return { normTranscript: sandbox.normTranscript, detectIntent: sandbox.detectIntent };
}

const { normTranscript, detectIntent } = loadIntentEngine();

const builtinTests = [
  { step: 'GREETING', raw: 'oui', expect: { intent: 'proprietaire' }, label: 'greeting oui' },
  { step: 'GREETING', raw: 'ouais', expect: { intent: 'proprietaire' }, label: 'greeting ouais' },
  { step: 'GREETING', raw: 'je veux vendre ma maison', expect: { intent: 'proprietaire', besoin: 'immo' }, label: 'vendre ma maison' },
  { step: 'GREETING', raw: 'cuisine', expect: { intent: 'proprietaire', besoin: 'reno' }, label: 'cuisine au greeting' },
  { step: 'GREETING', raw: 'sous-sol', expect: { intent: 'proprietaire', besoin: 'reno' }, label: 'sous-sol au greeting' },
  { step: 'QUESTION_PROJET', raw: 'Sous sol', expect: { intent: 'projet' }, label: 'sous-sol projet' },
  { step: 'QUESTION_PROJET', raw: 'cuisine et salle de bain', expect: { intent: 'projet' }, label: 'cuisine sdb' },
  { step: 'QUESTION_PROJET', raw: 'sou sol', expect: { intent: 'projet' }, label: 'sou sol' },
  { step: 'QUESTION_BESOIN', raw: 'vendre ma maison', expect: { intent: 'immo' }, label: 'besoin immo' },
  { step: 'GREETING', raw: '', expect: { intent: 'silence' }, label: 'silence greeting' },
];

let fixtureTests = [];
if (fs.existsSync(FIXTURES)) {
  fixtureTests = JSON.parse(fs.readFileSync(FIXTURES, 'utf8'));
}

const allTests = [...builtinTests, ...fixtureTests];
let passed = 0;
let failed = 0;

for (const t of allTests) {
  const text = normTranscript(t.raw);
  const got = detectIntent(t.step, text);
  const expect = t.expect || { intent: t.expect_intent };
  let ok = got.intent === expect.intent;
  if (ok && expect.besoin !== undefined) ok = got.besoin === expect.besoin;
  const label = t.label || `[${t.step}] "${t.raw}"`;
  if (ok) {
    passed++;
    console.log(`OK  ${label}`);
  } else {
    failed++;
    const extra = expect.besoin ? ` besoin=${expect.besoin}` : '';
    console.log(`FAIL ${label}: got intent=${got.intent}${got.besoin ? ' besoin=' + got.besoin : ''}, expected intent=${expect.intent}${extra}`);
  }
}

console.log(`\n${passed}/${allTests.length} tests intent passés`);
process.exit(failed > 0 ? 1 : 0);
