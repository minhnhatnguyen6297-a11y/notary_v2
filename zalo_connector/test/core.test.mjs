import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import {mkdtemp, readFile, stat, utimes, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  FileOutbox,
  MediaStore,
  WebhookClient,
  attachmentEvents,
  mediaObjectKey,
  signBody,
} from '../src/core.mjs';

const jsonResponse = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: {'content-type': 'application/json'},
});

test('signBody matches backend timestamp-dot-body HMAC contract', () => {
  const body = '{"event_type":"heartbeat"}';
  const expected = createHmac('sha256', 'secret').update(`123.${body}`).digest('hex');
  assert.equal(signBody(body, '123', 'secret'), expected);
});

test('WebhookClient signs events and reads connector-only allowlist config', async () => {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({url, options});
    return url.endsWith('/config')
      ? jsonResponse({sources: [{conversation_id: 'g-1', enabled: true}], protected_media_object_keys: []})
      : jsonResponse({ack: true});
  };
  const client = new WebhookClient({baseUrl: 'http://backend', secret: 'secret', fetchImpl, now: () => 123000});
  await client.sendEvent({schema_version: 1, event_type: 'heartbeat'});
  await client.getConfig('account-1');

  const sentBody = calls[0].options.body;
  assert.equal(calls[0].options.headers['x-zalo-timestamp'], '123');
  assert.equal(calls[0].options.headers['x-zalo-signature'], signBody(sentBody, '123', 'secret'));
  assert.equal(calls[1].options.headers['x-zalo-signature'], signBody('', '123', 'secret'));
  assert.equal(calls[1].url, 'http://backend/zalo-inbox/api/connectors/account-1/config');
});

test('WebhookClient sends exact versioned policy and source-sync ACK events', async () => {
  const events = [];
  const client = new WebhookClient({
    baseUrl: 'http://backend',
    secret: 'secret',
    fetchImpl: async (_url, options) => {
      events.push(JSON.parse(options.body));
      return jsonResponse({ack: true});
    },
  });

  await client.ackPolicy('account-1', 7);
  await client.ackSourceSync('account-1', 3);

  assert.deepEqual(events, [
    {
      schema_version: 1,
      event_type: 'policy_ack',
      connector_account_id: 'account-1',
      policy_version: 7,
    },
    {
      schema_version: 1,
      event_type: 'source_sync_ack',
      connector_account_id: 'account-1',
      source_sync_request_version: 3,
    },
  ]);
});

test('attachmentEvents ignores disabled/self messages and builds stable media events for enabled sources', () => {
  const base = {
    type: 1,
    threadId: 'g-1',
    isSelf: false,
    data: {
      msgId: 'm-1',
      ts: '1785812400000',
      dName: 'Người gửi',
      content: {href: 'https://cdn.example/document.pdf', title: 'hop-dong.pdf', type: 'application/pdf'},
    },
  };
  assert.deepEqual(attachmentEvents(base, new Set(), 'account-1', 'Nhóm A'), []);
  assert.deepEqual(attachmentEvents({...base, isSelf: true}, new Set(['g-1']), 'account-1', 'Nhóm A'), []);

  const [event] = attachmentEvents(base, new Set(['g-1']), 'account-1', 'Nhóm A');
  assert.equal(event.conversation_id, 'g-1');
  assert.equal(event.conversation_type, 'group');
  assert.equal(event.msg_id, 'm-1');
  assert.equal(event.attachment_index, 0);
  assert.equal(event.mime_type, 'application/pdf');
  assert.equal(event.download_url, 'https://cdn.example/document.pdf');
  assert.match(event.sent_at, /^2026-08-04T/);
});

test('attachmentEvents accepts zca image payload and rejects unsupported media', () => {
  const image = {
    type: 0,
    threadId: 'u-1',
    isSelf: false,
    data: {msgId: 'm-img', ts: '1785812400000', content: {href: 'https://cdn.example/image', hdUrl: 'https://cdn.example/image-hd'}},
  };
  const [event] = attachmentEvents(image, new Set(['u-1']), 'account-1', 'Bạn A');
  assert.equal(event.conversation_type, 'user');
  assert.equal(event.mime_type, 'image/jpeg');
  assert.equal(event.download_url, 'https://cdn.example/image-hd');
  assert.deepEqual(
    attachmentEvents({...image, data: {...image.data, content: {href: 'https://cdn.example/file.zip', title: 'file.zip'}}}, new Set(['u-1']), 'account-1', 'Bạn A'),
    [],
  );
});

test('FileOutbox keeps failed events and removes only acknowledged events', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-outbox-'));
  const outbox = new FileOutbox(root);
  const event = {schema_version: 1, event_type: 'heartbeat', connector_account_id: 'a'};
  await outbox.enqueue('event-1', event);
  await assert.rejects(() => outbox.flush({sendEvent: async () => { throw new Error('offline'); }}), /offline/);
  assert.equal((await outbox.pending()).length, 1);
  await outbox.flush({sendEvent: async (payload) => assert.deepEqual(payload, event)});
  assert.deepEqual(await outbox.pending(), []);
});

test('MediaStore enforces quota and retention without deleting protected media', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-media-'));
  const store = new MediaStore({root, quotaBytes: 8, retentionHours: 1});
  const firstKey = mediaObjectKey('account-1', 'm-1', 0, 'image/png', new Date('2026-08-04T00:00:00Z'));
  await store.put(firstKey, Buffer.from('1234'));
  await assert.rejects(() => store.put(mediaObjectKey('account-1', 'm-2', 0, 'image/png'), Buffer.from('56789')), /quota/i);

  const firstPath = path.join(root, ...firstKey.split('/'));
  const old = new Date('2026-08-03T00:00:00Z');
  await utimes(firstPath, old, old);
  const retained = await store.prune({protectedKeys: new Set([firstKey]), now: new Date('2026-08-04T02:00:00Z')});
  assert.equal((await stat(firstPath)).size, 4);
  assert.deepEqual(retained, {usageBytes: 4, storageFull: false});
  const emptied = await store.prune({protectedKeys: new Set(), now: new Date('2026-08-04T02:00:00Z')});
  await assert.rejects(() => readFile(firstPath), /ENOENT/);
  assert.deepEqual(emptied, {usageBytes: 0, storageFull: false});

  const protectedKey = mediaObjectKey('account-1', 'm-3', 0, 'image/png');
  await store.put(protectedKey, Buffer.alloc(8));
  const full = await store.prune({protectedKeys: new Set([protectedKey]), now: new Date()});
  assert.deepEqual(full, {usageBytes: 8, storageFull: false});
});
