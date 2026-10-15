import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><body></body>');
globalThis.document = dom.window.document;
globalThis.window = dom.window;
const { eventTime } = await import('swarm-lens/ui.js');
const { renderProfile } = await import('../../src/swarm_lens/web/plugins/data_profile/static/index.js');
const { dataWarningItems } = await import('../../src/swarm_lens/web/plugins/mast/static/details.js');

const dimension = (status, note, evidence = {}) => ({ status, note, evidence });
const profile = {
  cursor: 12, events: 12, declared: { time_grade: 'ordinal', attribution: 'unattributed', missing: ['timestamps'], notes: 'Order only.' },
  dimensions: {
    actors: dimension('absent', '0 of 10 agent actions name the agent.', { agents: 1, attributed_share: 0 }),
    time: dimension('absent', 'Timestamps are stand-ins.', { ordinal: 10, tied_share: 0.25 }),
    conversation: dimension('absent', 'The history holds no messages.', { messages: 0 }),
    actions: dimension('present', '8 of 10 tool calls have a recorded result.', { tool_calls: 10 }),
  },
  supports: [{ analysis: 'timing', verdict: 'unsupported', reason: 'Rates need real timestamps.' },
             { analysis: 'actions', verdict: 'supported', reason: 'Action analyses need tool calls.' }],
};

test('event times follow the declared time grade', () => {
  const at = '2026-06-16T09:27:10Z';
  assert.equal(eventTime({ at, position: 3 }), '09:27:10');
  assert.equal(eventTime({ at, time_grade: 'exact' }), '09:27:10');
  assert.equal(eventTime({ at, time_grade: 'approximate' }), '≈09:27:10');
  assert.equal(eventTime({ at, time_grade: 'ordinal' }), 'order only');
});

test('the profile view shows each dimension, the verdicts and the importer declaration', () => {
  const root = renderProfile(profile);
  const cards = [...root.querySelectorAll('.dp-card')];
  assert.deepEqual(cards.map(card => card.querySelector('h3').textContent), ['Actors', 'Time', 'Conversation', 'Actions']);
  assert.deepEqual(cards.map(card => card.querySelector('.dp-pill').dataset.tone), ['absent', 'absent', 'absent', 'present']);
  assert.match(cards[1].textContent, /tied share25%/);
  assert.match(cards[0].textContent, /attributed share0%/);
  const verdicts = [...root.querySelectorAll('li')].map(item => item.textContent);
  assert.match(verdicts[0], /^Timing analysisNot supported/);
  assert.match(verdicts[1], /^Action analysisSupported/);
  assert.match(root.querySelector('.dp-declared').textContent, /time is ordinal, agents are unattributed\. Missing: timestamps\. Order only\./);
  assert.equal(renderProfile({ ...profile, declared: null }).querySelector('.dp-declared'), null);
});

test('MAST lists data warnings only when the profile has some', () => {
  assert.deepEqual(dataWarningItems({}), []);
  const items = dataWarningItems({ data_warnings: ['Conversation: The history holds no messages.'] });
  assert.deepEqual(items.map(item => item.textContent),
                   ['This history may not suit MAST:', 'Conversation: The history holds no messages.']);
});
