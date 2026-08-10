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
  normalizeMessage,
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
      const event = events.at(-1);
      return jsonResponse(event.event_type === 'policy_ack'
        ? {ack: true, policy_version: event.policy_version}
        : {ack: true, source_sync_request_version: event.source_sync_request_version});
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

test('WebhookClient rejects malformed 2xx and non-matching version ACKs', async () => {
  for (const body of [{}, {ack: false}, {ack: true, policy_version: 6}]) {
    const client = new WebhookClient({
      baseUrl: 'http://backend', secret: 'secret', fetchImpl: async () => jsonResponse(body),
    });
    await assert.rejects(() => client.ackPolicy('account-1', 7), /ack/i);
  }
});

test('normalizeMessage keeps text and all supported attachments in one descriptor', () => {
  const base = {
    type: 1,
    threadId: 'g-1',
    isSelf: false,
    data: {
      msgId: 'm-1',
      uidFrom: 'sender-1',
      ts: '1785812400000',
      dName: 'Người gửi',
      content: 'Nội dung',
      attachments: [
        {href: 'https://cdn.example/document.pdf', title: 'hop-dong.pdf', type: 'application/pdf'},
        {hdUrl: 'https://cdn.example/image-hd', title: 'anh.png', type: 'image/png'},
        {href: 'https://cdn.example/video.mp4', title: 'video.mp4', type: 'video/mp4'},
      ],
    },
  };
  const event = normalizeMessage(base, 'account-1', {
    source_type: 'group', source_display_name: 'Nhóm A',
  }, 'send2me');
  assert.equal(event.raw_text, 'Nội dung');
  assert.equal(event.conversation_id, 'g-1');
  assert.equal(event.conversation_type, 'group');
  assert.equal(event.msg_id, 'm-1');
  assert.deepEqual(event.attachments, [
    {attachment_index: 0, mime_type: 'application/pdf', download_url: 'https://cdn.example/document.pdf', original_filename: 'hop-dong.pdf'},
    {attachment_index: 1, mime_type: 'image/png', download_url: 'https://cdn.example/image-hd', original_filename: 'anh.png'},
  ]);
  assert.match(event.sent_at, /^2026-08-04T/);
});

test('normalizeMessage accepts exact My Documents self thread and rejects other self messages', () => {
  const image = {
    type: 0,
    threadId: 'u-1',
    isSelf: false,
    data: {msgId: 'm-img', uidFrom: 'sender-1', ts: '1785812400000', content: {href: 'https://cdn.example/image', hdUrl: 'https://cdn.example/image-hd'}},
  };
  const event = normalizeMessage(image, 'account-1', {source_type: 'friend', source_display_name: 'Bạn A'}, 'my-docs');
  assert.equal(event.conversation_type, 'user');
  assert.equal(event.attachments[0].mime_type, 'image/jpeg');
  assert.equal(normalizeMessage({...image, isSelf: true}, 'account-1', {source_type: 'friend', source_display_name: 'Bạn A'}, 'my-docs'), null);
  const mine = {...image, isSelf: true, threadId: 'my-docs'};
  assert.equal(normalizeMessage(mine, 'account-1', {source_type: 'my_documents', source_display_name: 'My Documents'}, 'my-docs').source_type, 'my_documents');
});

test('normalizeMessage rejects empty message and sender identifiers without inventing fallbacks', () => {
  const source = {source_type: 'friend', source_display_name: 'Bạn A'};
  const base = {type: 0, threadId: 'u-1', data: {msgId: 'm-1', uidFrom: 'sender-1', content: 'private'}};
  assert.equal(normalizeMessage({...base, data: {...base.data, msgId: '', cliMsgId: ''}}, 'account-1', source, ''), null);
  assert.equal(normalizeMessage({...base, data: {...base.data, uidFrom: '', senderId: ''}}, 'account-1', source, ''), null);
  assert.equal(normalizeMessage({...base, data: {...base.data, uidFrom: '', senderId: 'sender-2'}}, 'account-1', source, '').sender_id, 'sender-2');
});

test('FileOutbox keeps failed events and removes only acknowledged events', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-outbox-'));
  const outbox = new FileOutbox(root);
  const event = {schema_version: 1, event_type: 'heartbeat', connector_account_id: 'a'};
  await outbox.enqueue('event-1', event);
  await assert.rejects(() => outbox.flush({sendEvent: async () => { throw new Error('offline'); }}), /offline/);
  assert.equal((await outbox.pending()).length, 1);
  await outbox.flush({sendEvent: async (payload) => { assert.deepEqual(payload, event); return {ack: true}; }});
  assert.deepEqual(await outbox.pending(), []);
});

test('FileOutbox retains message until exact component ACK', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-outbox-message-'));
  const outbox = new FileOutbox(root);
  const event = {
    schema_version: 1, event_type: 'message', connector_account_id: 'a', raw_text: 'private',
    attachments: [{attachment_index: 0}, {attachment_index: 1}],
  };
  await outbox.enqueue('message-1', event);
  for (const response of [
    {ack: true},
    {ack: true, components: {text: 'imported', media: [{attachment_index: 0, status: 'imported'}]}},
    {ack: true, components: {text: 'imported', media: [
      {attachment_index: 0, status: 'imported'}, {attachment_index: 1, status: 'wrong'},
    ]}},
  ]) {
    await assert.rejects(() => outbox.flush({sendEvent: async () => response}), /ack/i);
    assert.equal((await outbox.pending()).length, 1);
  }
  await outbox.flush({sendEvent: async () => ({ack: true, components: {text: 'imported', media: [
    {attachment_index: 0, status: 'duplicate'}, {attachment_index: 1, status: 'ignored'},
  ]}})});
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
