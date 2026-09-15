import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../frontend/static/js/zalo_inbox.js', import.meta.url), 'utf8');

test('retryable output cards send the selected output type', () => {
  assert.match(source, /output\.status === 'error' && output\.retryable/);
  assert.match(source, /retry\('output', name\)/);
  assert.match(source, /output_type: outputType/);
});

test('creating a new batch warns when the latest batch is unfinished', () => {
  assert.match(source, /state\.latest_batch\?\.unfinished/);
  assert.match(source, /previous-batch-warning/);
  assert.match(source, /continue-create-batch/);
});

test('source settings starts QR login directly from the module', async () => {
  const template = await readFile(new URL('../frontend/templates/zalo_inbox.html', import.meta.url), 'utf8');
  assert.match(template, /id="start-zalo-login"/);
  assert.match(template, /id="connector-login-notice"/);
  assert.match(template, />Đăng nhập Zalo</);
  assert.match(source, /api\/connectors\/start/);
  assert.match(source, /start-zalo-login/);
  assert.match(source, /force_restart: state\.connector\.state !== 'connected'/);
  assert.match(source, /force_qr: state\.connector\.state === 'login_required'/);
  assert.match(source, /connector\.error/);
  assert.match(source, /connector-login-notice/);
  assert.match(source, /getInstance\(\$\('settings-modal'\)\)\?\.hide\(\)/);
});

test('module entry does not auto-open QR before explicit login', async () => {
  const template = await readFile(new URL('../frontend/templates/zalo_inbox.html', import.meta.url), 'utf8');
  assert.match(template, /id="start-zalo-login"/);
  assert.match(source, /start-zalo-login/);
  assert.doesNotMatch(source, /if \(connector\.state === 'login_required' && connector\.qr_image\) \{/);
});

test('background polling does not erase an actionable error notice', () => {
  const refreshBody = source.match(/async function refresh\(\) \{([\s\S]*?)\n  \}/)?.[1] || '';
  assert.doesNotMatch(refreshBody, /clearNotice\(\)/);
});
