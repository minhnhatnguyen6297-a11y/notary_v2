import assert from 'node:assert/strict';
import {mkdir, mkdtemp, rm, stat, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {FileOutbox} from '../src/core.mjs';
import {createZaloClient, finalizeQrLogin, handleMessage, handleQrLoginEvent, installSourceSyncTriggers, isParentAlive, listenerHeartbeatState, processUnknownSourceQueue, publishConnectedState, readSettings, refreshRuntimeState, resolveUnknownSource, shouldRestoreSession, sourceDescriptor, startConnector, startParentWatch, syncSources, verifyRestoredSession} from '../src/connector.mjs';

test('readSettings requires deployment quota and retention instead of inventing defaults', () => {
  assert.throws(() => readSettings({}), /required/i);
  const settings = readSettings({
    ZALO_INBOX_BACKEND_URL: 'http://127.0.0.1:8000',
    ZALO_INBOX_BOOTSTRAP_SECRET: 'bootstrap',
    ZALO_INBOX_WEBHOOK_SECRET: 'webhook',
    ZALO_INBOX_STORAGE_ROOT: 'runtime/zalo',
    ZALO_CONNECTOR_RETENTION_HOURS: '72',
    ZALO_CONNECTOR_QUOTA_BYTES: '1000',
  });
  assert.equal(settings.retentionHours, 72);
  assert.equal(settings.quotaBytes, 1000);
  assert.equal(settings.heartbeatMs, 15000);
  assert.equal(settings.configPollMs, 15000);
  assert.equal(settings.sourceReconcileMs, 3600000);
});

test('zca-js logging is disabled and exact My Documents self messages are enabled', () => {
  class FakeZalo {
    constructor(options) {
      this.options = options;
    }
  }
  assert.deepEqual(createZaloClient(FakeZalo).options, {logging: false, selfListen: true});
});

test('sourceDescriptor validates source types and normalizes last activity', () => {
  assert.deepEqual(sourceDescriptor({
    conversationId: ' user-1 ',
    sourceType: 'friend',
    displayName: ' Bạn A ',
    lastActivityAt: 1785812400,
  }), {
    conversation_id: 'user-1',
    conversation_type: 'user',
    source_display_name: 'Bạn A',
    source_type: 'friend',
    last_activity_at: new Date(1785812400 * 1000).toISOString(),
  });
  assert.equal(sourceDescriptor({conversationId: 'g-1', sourceType: 'group', displayName: 'Nhóm A'}).conversation_type, 'group');
  assert.equal(sourceDescriptor({conversationId: 'me', sourceType: 'my_documents', displayName: 'My Documents'}).conversation_type, 'user');
  assert.throws(() => sourceDescriptor({conversationId: '', sourceType: 'friend', displayName: 'A'}), /conversation/i);
  assert.throws(() => sourceDescriptor({conversationId: 'u', sourceType: 'unknown', displayName: 'A'}), /source type/i);
  assert.throws(() => sourceDescriptor({conversationId: 'u', sourceType: 'friend', displayName: 'A', lastActivityAt: 'not-a-date'}), /activity/i);
});

test('syncSources publishes complete friend, group, and exact My Documents metadata', async () => {
  const api = {
    getAllFriends: async () => [{userId: 'u-1', displayName: 'Bạn A', lastActionTime: 1785812400}],
    getAllGroups: async () => ({gridVerMap: {'g-1': 'v1'}}),
    getGroupInfo: async () => ({gridInfoMap: {'g-1': {name: 'Nhóm A', createdTime: 1}}}),
    getContext: () => ({loginInfo: {send2me_id: 'send-to-me-exact'}}),
  };
  const events = [];
  const sources = await syncSources(apiFixture(api, 'account-1', {sendEvent: async (event) => events.push(event)}));
  assert.deepEqual([...sources.keys()], ['u-1', 'g-1', 'send-to-me-exact']);
  assert.deepEqual(events.map(({conversation_id, conversation_type, source_type, source_display_name, last_activity_at}) => ({conversation_id, conversation_type, source_type, source_display_name, last_activity_at})), [
    {conversation_id: 'u-1', conversation_type: 'user', source_type: 'friend', source_display_name: 'Bạn A', last_activity_at: new Date(1785812400 * 1000).toISOString()},
    {conversation_id: 'g-1', conversation_type: 'group', source_type: 'group', source_display_name: 'Nhóm A', last_activity_at: null},
    {conversation_id: 'send-to-me-exact', conversation_type: 'user', source_type: 'my_documents', source_display_name: 'My Documents', last_activity_at: null},
  ]);
  assert.ok(events.every((event) => event.schema_version === 1 && event.event_type === 'discovery'));
});

function apiFixture(api, accountId, client, extra = {}) {
  return {api, accountId, client, ...extra};
}

test('resolveUnknownSource resolves exact My Documents without an upstream lookup', async () => {
  const api = {
    getUserInfo: async () => assert.fail('exact My Documents must not query user info'),
    getGroupInfo: async () => assert.fail('exact My Documents must not query group info'),
  };
  assert.deepEqual(await resolveUnknownSource(api, {type: 0, threadId: 'my-docs'}, 'my-docs'), {
    status: 'resolved',
    source: sourceDescriptor({conversationId: 'my-docs', sourceType: 'my_documents', displayName: 'My Documents'}),
  });
});

test('resolveUnknownSource distinguishes valid friends, explicit strangers, and valid groups', async () => {
  assert.deepEqual(await resolveUnknownSource({
    getUserInfo: async () => ({changed_profiles: {'u-1': {userId: 'u-1', displayName: 'Bạn A', isFr: 1}}}),
  }, {type: 0, threadId: 'u-1'}, 'my-docs'), {
    status: 'resolved',
    source: sourceDescriptor({conversationId: 'u-1', sourceType: 'friend', displayName: 'Bạn A'}),
  });
  assert.deepEqual(await resolveUnknownSource({
    getUserInfo: async () => ({changed_profiles: {'u-2': {userId: 'u-2', displayName: 'Người lạ', isFr: 0}}}),
  }, {type: 0, threadId: 'u-2'}, 'my-docs'), {
    status: 'confirmed_stranger',
    source: sourceDescriptor({conversationId: 'u-2', sourceType: 'stranger', displayName: 'Người lạ'}),
  });
  assert.deepEqual(await resolveUnknownSource({
    getGroupInfo: async (ids) => {
      assert.deepEqual(ids, ['g-1']);
      return {gridInfoMap: {'g-1': {groupId: 'g-1', name: 'Nhóm A'}}};
    },
  }, {type: 1, threadId: 'g-1'}, 'my-docs'), {
    status: 'resolved',
    source: sourceDescriptor({conversationId: 'g-1', sourceType: 'group', displayName: 'Nhóm A'}),
  });
});

test('resolveUnknownSource keeps malformed and upstream failures retryable with stable codes', async () => {
  assert.deepEqual(await resolveUnknownSource({getUserInfo: async () => ({changed_profiles: {}})}, {type: 0, threadId: 'u-1'}, ''), {
    status: 'retryable_failure', error_code: 'source_response_invalid',
  });
  assert.deepEqual(await resolveUnknownSource({
    getUserInfo: async () => assert.fail('inconclusive thread type must not query a user'),
  }, {type: 9, threadId: 'u-1'}, ''), {
    status: 'retryable_failure', error_code: 'source_response_invalid',
  });
  assert.deepEqual(await resolveUnknownSource({getGroupInfo: async () => { throw new Error('private URL and name'); }}, {type: 1, threadId: 'g-1'}, ''), {
    status: 'retryable_failure', error_code: 'source_lookup_failed',
  });
});

async function unknownQueueFixture(sourceId, message, extra = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-unknown-'));
  const unknownQueue = new FileOutbox(path.join(root, 'unknown-source-queue'));
  await unknownQueue.enqueue('pending-1', {record_type: 'unknown_source', message, attempts: 0});
  const discoveries = [];
  const handled = [];
  const errors = [];
  const fixture = {
    api: extra.api,
    accountId: 'account-1',
    send2meId: extra.send2meId || 'my-docs',
    unknownQueue,
    client: {sendEvent: async (event) => discoveries.push(event)},
    refresh: async () => {},
    enabledIds: extra.enabledIds || new Set([sourceId]),
    sourceNames: new Map(),
    handleKnownMessage: async (pending) => handled.push(pending),
    reportError: (errorCode) => errors.push(errorCode),
  };
  return {root, unknownQueue, discoveries, handled, errors, fixture};
}

test('processUnknownSourceQueue publishes friend metadata, refreshes policy, and continues only after ACK enablement', async () => {
  const message = {type: 0, threadId: 'u-1', data: {msgId: 'secret-id', content: 'private text'}};
  const testCase = await unknownQueueFixture('u-1', message, {
    api: {getUserInfo: async () => ({changed_profiles: {'u-1': {userId: 'u-1', displayName: 'Bạn A', isFr: 1}}})},
    enabledIds: new Set(),
  });
  let refreshed = 0;
  testCase.fixture.refresh = async () => { refreshed += 1; testCase.fixture.enabledIds.add('u-1'); };
  await processUnknownSourceQueue(testCase.fixture);
  assert.equal(refreshed, 1);
  assert.deepEqual(testCase.discoveries.map((event) => event.source_type), ['friend']);
  assert.deepEqual(testCase.handled, [message]);
  assert.equal(testCase.fixture.sourceNames.get('u-1').source_display_name, 'Bạn A');
  assert.deepEqual(await testCase.unknownQueue.pending(), []);
  await rm(testCase.root, {recursive: true, force: true});
});

test('processUnknownSourceQueue handles group and exact My Documents resolution through the same ACK gate', async () => {
  for (const scenario of [
    {
      id: 'g-1', message: {type: 1, threadId: 'g-1', data: {msgId: 'm-g', content: 'group'}},
      api: {getGroupInfo: async () => ({gridInfoMap: {'g-1': {groupId: 'g-1', name: 'Nhóm A'}}})}, type: 'group',
    },
    {
      id: 'my-docs', message: {type: 0, threadId: 'my-docs', isSelf: true, data: {msgId: 'm-me', content: 'mine'}},
      api: {}, type: 'my_documents',
    },
  ]) {
    const testCase = await unknownQueueFixture(scenario.id, scenario.message, {api: scenario.api});
    await processUnknownSourceQueue(testCase.fixture);
    assert.deepEqual(testCase.discoveries.map((event) => event.source_type), [scenario.type]);
    assert.deepEqual(testCase.handled, [scenario.message]);
    assert.deepEqual(await testCase.unknownQueue.pending(), []);
    await rm(testCase.root, {recursive: true, force: true});
  }
});

test('processUnknownSourceQueue publishes explicit stranger metadata and discards content without handling', async () => {
  const message = {type: 0, threadId: 'u-2', data: {msgId: 'secret-id', content: 'private text'}};
  const testCase = await unknownQueueFixture('u-2', message, {
    api: {getUserInfo: async () => ({changed_profiles: {'u-2': {userId: 'u-2', displayName: 'Người lạ', isFr: 0}}})},
  });
  await processUnknownSourceQueue(testCase.fixture);
  assert.deepEqual(testCase.discoveries.map((event) => event.source_type), ['stranger']);
  assert.deepEqual(testCase.handled, []);
  assert.deepEqual(await testCase.unknownQueue.pending(), []);
  await rm(testCase.root, {recursive: true, force: true});
});

test('processUnknownSourceQueue persists bounded backoff and skips retries until due', async () => {
  let attempts = 0;
  let now = Date.parse('2026-08-04T03:00:00Z');
  const message = {type: 0, threadId: 'u-3', data: {msgId: 'secret-id', content: 'private text'}};
  const testCase = await unknownQueueFixture('u-3', message, {
    api: {getUserInfo: async () => {
      attempts += 1;
      if (attempts < 3) throw new Error('private URL');
      return {changed_profiles: {'u-3': {userId: 'u-3', displayName: 'Bạn B', isFr: 1}}};
    }},
  });
  testCase.fixture.now = () => now;
  await processUnknownSourceQueue(testCase.fixture);
  const first = (await testCase.unknownQueue.entries())[0].event;
  assert.equal(first.attempts, 1);
  assert.equal(first.next_attempt_at, '2026-08-04T03:00:01.000Z');
  await processUnknownSourceQueue(testCase.fixture);
  assert.equal(attempts, 1);
  now += 1000;
  await processUnknownSourceQueue(testCase.fixture);
  const second = (await testCase.unknownQueue.entries())[0].event;
  assert.equal(second.attempts, 2);
  assert.equal(second.next_attempt_at, '2026-08-04T03:00:03.000Z');
  now += 1999;
  await processUnknownSourceQueue(testCase.fixture);
  assert.equal(attempts, 2);
  now += 1;
  await processUnknownSourceQueue(testCase.fixture);
  assert.deepEqual(testCase.handled, [message]);
  assert.deepEqual(await testCase.unknownQueue.pending(), []);
  await rm(testCase.root, {recursive: true, force: true});
});

test('unknown retry replacement survives restart under one stable durable key', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-unknown-replace-'));
  try {
    const unknownQueue = new FileOutbox(path.join(root, 'queue'));
    await unknownQueue.enqueue('stable-event', {record_type: 'unknown_source', message: {type: 0, threadId: 'u-1'}, attempts: 0});
    const replace = unknownQueue.replace.bind(unknownQueue);
    unknownQueue.replace = async (name, event) => { await replace(name, event); throw new Error('crash-after-replace'); };
    await assert.rejects(() => processUnknownSourceQueue({
      api: {getUserInfo: async () => { throw new Error('offline'); }}, accountId: 'account-1', send2meId: '', unknownQueue,
      client: {sendEvent: async () => {}}, refresh: async () => {}, enabledIds: new Set(), sourceNames: new Map(),
      handleKnownMessage: async () => {}, now: () => 0,
    }), /crash-after-replace/);
    const entries = await new FileOutbox(path.join(root, 'queue')).entries();
    assert.equal(entries.length, 1);
    assert.equal(entries[0].event.attempts, 1);
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});

test('processUnknownSourceQueue removes content on third failure and reports only a stable code', async () => {
  const message = {type: 0, threadId: 'u-secret', data: {msgId: 'secret-id', content: 'private text', href: 'https://secret'}};
  const testCase = await unknownQueueFixture('u-secret', message, {
    api: {getUserInfo: async () => { throw new Error('Người A https://secret secret-id'); }},
  });
  let now = 0;
  testCase.fixture.now = () => now;
  await processUnknownSourceQueue(testCase.fixture);
  now = 1000;
  await processUnknownSourceQueue(testCase.fixture);
  now = 3000;
  await processUnknownSourceQueue(testCase.fixture);
  assert.deepEqual(await testCase.unknownQueue.pending(), []);
  assert.deepEqual(testCase.errors, ['source_lookup_failed']);
  assert.equal(JSON.stringify(testCase.errors).includes('secret'), false);
  await rm(testCase.root, {recursive: true, force: true});
});

test('handleMessage durably retries sibling attachments and publishes one private message envelope', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-message-'));
  const outbox = new FileOutbox(path.join(root, 'outbox'));
  const downloadQueue = new FileOutbox(path.join(root, 'download-queue'));
  const published = [];
  let failSecond = true;
  let downloadCalls = 0;
  const store = {download: async (key, url) => {
    downloadCalls += 1;
    if (downloadCalls === 2 && failSecond) throw new Error('crash');
    return {path: `/data/${key}`, sizeBytes: url.endsWith('/a.png') ? 3 : 4};
  }};
  const message = {
    type: 1,
    threadId: 'g-1',
    isSelf: false,
    data: {
      msgId: 'm-1',
      uidFrom: 'sender-1',
      ts: '1785812400000',
      content: 'Nội dung',
      attachments: [
        {href: 'https://cdn.example/a.png', title: 'a.png', type: 'image/png'},
        {href: 'https://cdn.example/b.pdf', title: 'b.pdf', type: 'application/pdf'},
      ],
    },
  };
  const fixture = {
    message,
    accountId: 'account-1',
    enabledIds: new Set(['g-1']),
    sourceNames: new Map([['g-1', sourceDescriptor({conversationId: 'g-1', sourceType: 'group', displayName: 'Nhóm A'})]]),
    send2meId: 'my-docs',
    store,
    outbox,
    downloadQueue,
    client: {sendEvent: async (event) => {
      published.push(event);
      return event.event_type === 'message'
        ? {ack: true, components: {text: 'imported', media: event.attachments.map(({attachment_index}) => ({attachment_index, status: 'imported'}))}}
        : {ack: true};
    }},
  };
  await assert.rejects(() => handleMessage(fixture), /crash/);
  assert.equal((await downloadQueue.entries()).length, 2);

  failSecond = false;
  await handleMessage(fixture);
  const messageEvents = published.filter((event) => event.event_type === 'message');
  assert.equal(messageEvents.length, 1);
  assert.equal(messageEvents[0].raw_text, 'Nội dung');
  assert.deepEqual(messageEvents[0].attachments, [
    {attachment_index: 0, mime_type: 'image/png', media_object_key: messageEvents[0].attachments[0].media_object_key, size_bytes: 3},
    {attachment_index: 1, mime_type: 'application/pdf', media_object_key: messageEvents[0].attachments[1].media_object_key, size_bytes: 4},
  ]);
  assert.equal(JSON.stringify(messageEvents[0]).includes('download_url'), false);
  assert.equal(JSON.stringify(messageEvents[0]).includes('original_filename'), false);
  assert.deepEqual(await downloadQueue.pending(), []);
  assert.deepEqual(await outbox.pending(), []);
  await rm(root, {recursive: true, force: true});
});

test('handleMessage reports activity before gating disabled and unsupported-only content', async () => {
  const published = [];
  const activity = [];
  let downloads = 0;
  const fixture = {
    accountId: 'account-1',
    enabledIds: new Set(),
    sourceNames: new Map([['u-1', sourceDescriptor({conversationId: 'u-1', sourceType: 'friend', displayName: 'Bạn A'})]]),
    send2meId: 'my-docs',
    store: {download: async () => { downloads += 1; }},
    outbox: {enqueue: async (_id, event) => published.push(event), flush: async () => {}},
    downloadQueue: {entries: async () => [], enqueue: async () => assert.fail('disabled source must not persist'), remove: async () => {}},
    client: {sendEvent: async (event) => activity.push(event)},
  };
  const base = {type: 0, threadId: 'u-1', isSelf: false, data: {msgId: 'm-text', uidFrom: 'sender-1', ts: '1785812400000', content: 'Xin chào'}};
  await handleMessage({...fixture, message: base});
  assert.equal(downloads, 0);
  assert.deepEqual(published, []);
  assert.deepEqual(activity.map(({event_type, last_activity_at}) => ({event_type, last_activity_at})), [
    {event_type: 'discovery', last_activity_at: new Date(1785812400000).toISOString()},
  ]);

  await handleMessage({...fixture, message: {...base, data: {...base.data, msgId: '', uidFrom: ''}}});
  assert.equal(activity.length, 1);

  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-text-'));
  fixture.enabledIds.add('u-1');
  fixture.downloadQueue = new FileOutbox(path.join(root, 'download-queue'));
  await handleMessage({...fixture, message: base});
  assert.equal(downloads, 0);
  assert.equal(published.length, 1);
  assert.deepEqual(published[0].attachments, []);

  await handleMessage({...fixture, message: {...base, data: {...base.data, msgId: 'm-unsupported', content: {href: 'https://cdn.example/a.zip', title: 'a.zip'}}}});
  assert.equal(downloads, 0);
  assert.equal(published.length, 1);
  assert.equal(activity.length, 3);
  await rm(root, {recursive: true, force: true});
});

test('handleMessage persists text before the first backend activity call and retains it offline', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-durable-first-'));
  try {
    const downloadQueue = new FileOutbox(path.join(root, 'download-queue'));
    await assert.rejects(() => handleMessage({
      message: {type: 0, threadId: 'u-1', data: {msgId: 'm-1', uidFrom: 'sender-1', content: 'private'}},
      accountId: 'account-1', enabledIds: new Set(['u-1']),
      sourceNames: new Map([['u-1', sourceDescriptor({conversationId: 'u-1', sourceType: 'friend', displayName: 'Bạn A'})]]),
      send2meId: '', store: {download: async () => assert.fail('text must not download')},
      outbox: new FileOutbox(path.join(root, 'outbox')), downloadQueue,
      client: {sendEvent: async () => {
        assert.equal((await downloadQueue.entries()).filter(({event}) => event.record_type === 'message').length, 1);
        throw new Error('offline');
      }},
    }), /offline/);
    assert.equal((await downloadQueue.pending()).length, 1);
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});

test('handleMessage treats storage full as media-only and still publishes text', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-storage-full-text-'));
  const published = [];
  try {
    await handleMessage({
      message: {type: 0, threadId: 'u-1', data: {msgId: 'm-1', uidFrom: 'sender-1', content: 'private', attachments: [
        {href: 'https://cdn.example/a.png', title: 'a.png', type: 'image/png'},
      ]}},
      accountId: 'account-1', enabledIds: new Set(['u-1']),
      sourceNames: new Map([['u-1', sourceDescriptor({conversationId: 'u-1', sourceType: 'friend', displayName: 'Bạn A'})]]),
      send2meId: '', storageFull: true, store: {download: async () => assert.fail('full media store must not download')},
      outbox: new FileOutbox(path.join(root, 'outbox')), downloadQueue: new FileOutbox(path.join(root, 'download-queue')),
      client: {sendEvent: async (event) => {
        if (event.event_type === 'message') published.push(event);
        return event.event_type === 'message' ? {ack: true, components: {text: 'imported', media: []}} : {ack: true};
      }},
    });
    assert.equal(published.length, 1);
    assert.equal(published[0].raw_text, 'private');
    assert.deepEqual(published[0].attachments, []);
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});

test('handleMessage keeps enabled My Documents content behind live verification', async () => {
  let downloads = 0;
  let persisted = 0;
  await handleMessage({
    message: {type: 0, threadId: 'my-docs', isSelf: true, data: {
      msgId: 'private-id', ts: '1785812400000', content: 'private text',
      attachments: [{href: 'https://private.example/file.png', title: 'private.png', type: 'image/png'}],
    }},
    accountId: 'account-1',
    enabledIds: new Set(['my-docs']),
    sourceNames: new Map([['my-docs', sourceDescriptor({conversationId: 'my-docs', sourceType: 'my_documents', displayName: 'My Documents'})]]),
    send2meId: 'my-docs',
    store: {download: async () => { downloads += 1; }},
    outbox: {enqueue: async () => { persisted += 1; }, flush: async () => {}},
    downloadQueue: {entries: async () => [], enqueue: async () => { persisted += 1; }, remove: async () => {}},
    client: {sendEvent: async () => {}},
  });
  assert.equal(downloads, 0);
  assert.equal(persisted, 0);
});

test('connector success and failure paths never log private sentinels', async () => {
  const sentinels = [
    'RAW_TEXT_SENTINEL', 'SENDER_SENTINEL', 'CONVERSATION_SENTINEL', 'DISPLAY_SENTINEL',
    'ORIGINAL_FILENAME_SENTINEL', 'https://REMOTE_URL_SENTINEL', 'OBJECT_KEY_SENTINEL', 'UPSTREAM_ERROR_SENTINEL',
  ];
  const captured = [];
  const originals = Object.fromEntries(['log', 'info', 'warn', 'error', 'debug'].map((name) => [name, console[name]]));
  for (const name of Object.keys(originals)) console[name] = (...args) => captured.push(args.join(' '));
  const outboxRoot = await mkdtemp(path.join(os.tmpdir(), 'zalo-log-outbox-'));
  const downloadRoot = await mkdtemp(path.join(os.tmpdir(), 'zalo-log-download-'));
  try {
    await resolveUnknownSource({getUserInfo: async () => ({changed_profiles: {
      known: {userId: 'known', displayName: sentinels[3], isFr: 1},
    }})}, {type: 0, threadId: 'known'}, 'my-docs');
    await resolveUnknownSource({getUserInfo: async () => { throw new Error(sentinels[7]); }}, {
      type: 0, threadId: sentinels[2], data: {content: sentinels[0], uidFrom: sentinels[1]},
    }, 'my-docs');
    await assert.rejects(() => handleMessage({
      message: {type: 0, threadId: 'known', data: {msgId: 'm', uidFrom: 'sender-1', ts: '1785812400000', content: {
        href: sentinels[5], title: sentinels[4], type: 'image/png',
      }}},
      accountId: 'account-1', enabledIds: new Set(['known']),
      sourceNames: new Map([['known', sourceDescriptor({conversationId: 'known', sourceType: 'friend', displayName: sentinels[3]})]]),
      send2meId: 'my-docs',
      store: {download: async () => { throw new Error(sentinels[7]); }},
      outbox: new FileOutbox(path.join(outboxRoot, 'outbox')),
      downloadQueue: new FileOutbox(path.join(downloadRoot, 'download')),
      client: {sendEvent: async () => ({ack: true})},
    }), /UPSTREAM_ERROR_SENTINEL/);
    assert.throws(() => sourceDescriptor({conversationId: sentinels[2], sourceType: 'invalid', displayName: sentinels[3]}));
  } finally {
    Object.assign(console, originals);
    await rm(outboxRoot, {recursive: true, force: true});
    await rm(downloadRoot, {recursive: true, force: true});
  }
  await assert.rejects(() => stat(outboxRoot), /ENOENT/);
  await assert.rejects(() => stat(downloadRoot), /ENOENT/);
  const output = captured.join('\n');
  for (const sentinel of sentinels) assert.equal(output.includes(sentinel), false);
});

test('startConnector refreshes config and fallback source map before listener.start handles an immediate message', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-start-'));
  const stateRoot = path.join(root, 'state');
  await mkdir(stateRoot, {recursive: true});
  await writeFile(path.join(stateRoot, 'account.json'), JSON.stringify({connector_account_id: 'account-1'}));
  await writeFile(path.join(stateRoot, 'session.json'), JSON.stringify({cookie: []}));
  const order = [];
  const handlers = new Map();
  let messageEvents = 0;
  let resolveMessage;
  const messageReceived = new Promise((resolve) => { resolveMessage = resolve; });
  const listener = {
    on: (name, callback) => handlers.set(name, callback),
    start: () => {
      order.push('listener.start');
      handlers.get('message')({
        type: 1,
        threadId: 'g-1',
        isSelf: true,
        data: {msgId: 'm-1', uidFrom: 'sender-1', ts: '1785812400000', content: {href: 'https://cdn.example/a.png', title: 'a.png', type: 'image/png'}},
      });
    },
    stop: () => {},
  };
  const api = {
    listener,
    getOwnId: () => 'zalo-owner-1',
    getContext: () => ({loginInfo: {send2me_id: 'g-1'}}),
    getAllFriends: async () => { order.push('initial-scan'); throw new Error('scan unavailable'); },
    getAllGroups: async () => assert.fail('failed friend scan must stop the full scan'),
    requestOldMessages: async () => assert.fail('startup must not prefetch history'),
  };
  class FakeZalo {
    async login() { return api; }
  }
  const fetchImpl = async (url, options = {}) => {
    if (url.endsWith('/config')) {
      order.push('config');
      return new Response(JSON.stringify({
        policy_version: 1,
        policy_acked_version: 1,
        source_sync_request_version: 1,
        source_sync_acked_version: 0,
        sources: [{conversation_id: 'g-1', display_name: 'Config group', source_type: 'group', acked_enabled: true}],
        protected_media_object_keys: [],
      }), {status: 200});
    }
    const event = options.body ? JSON.parse(options.body) : {};
    if (event.event_type === 'message') {
      messageEvents += 1;
      resolveMessage();
    }
    const response = event.event_type === 'message'
      ? {ack: true, components: {text: event.raw_text == null ? 'absent' : 'imported', media: event.attachments.map(({attachment_index}) => ({attachment_index, status: 'imported'}))}}
      : {ack: true};
    return new Response(JSON.stringify(response), {status: 200});
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    order.push(`download:${url}`);
    return new Response(Buffer.from('image'), {status: 200, headers: {'content-length': '5'}});
  };
  let connector;
  try {
    connector = await startConnector({
      Zalo: FakeZalo,
      LoginQRCallbackEventType: {},
      fetchImpl,
      env: {
        ZALO_INBOX_BACKEND_URL: 'http://backend',
        ZALO_INBOX_BOOTSTRAP_SECRET: 'bootstrap',
        ZALO_INBOX_WEBHOOK_SECRET: 'webhook',
        ZALO_INBOX_STORAGE_ROOT: path.join(root, 'media'),
        ZALO_CONNECTOR_STATE_ROOT: stateRoot,
        ZALO_CONNECTOR_RETENTION_HOURS: '72',
        ZALO_CONNECTOR_QUOTA_BYTES: '1000',
      },
    });
    await Promise.race([
      messageReceived,
      new Promise((_, reject) => setTimeout(() => reject(new Error('immediate message was not handled')), 1000)),
    ]);
    assert.ok(order.indexOf('config') < order.indexOf('listener.start'));
    assert.ok(order.indexOf('initial-scan') < order.indexOf('listener.start'));
    assert.equal(messageEvents, 1);
  } finally {
    connector?.close();
    globalThis.fetch = originalFetch;
    await rm(root, {recursive: true, force: true});
  }
});

test('startConnector durably resolves an unknown friend before ACK-enabled content processing', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-start-unknown-'));
  const stateRoot = path.join(root, 'state');
  await mkdir(stateRoot, {recursive: true});
  await writeFile(path.join(stateRoot, 'account.json'), JSON.stringify({connector_account_id: 'account-1'}));
  await writeFile(path.join(stateRoot, 'session.json'), JSON.stringify({cookie: []}));
  const handlers = new Map();
  const events = [];
  let lookups = 0;
  let discovered = false;
  let resolveMessage;
  const messageReceived = new Promise((resolve) => { resolveMessage = resolve; });
  const listener = {
    on: (name, callback) => handlers.set(name, callback),
    start: () => {
      handlers.get('message')({type: 0, threadId: 'u-malformed', data: {msgId: '', uidFrom: '', content: 'must-not-persist'}});
      handlers.get('message')({type: 0, threadId: '   ', data: {msgId: 'm-space', uidFrom: 'sender-space', content: 'must-not-persist'}});
      handlers.get('message')({type: 0, threadId: 'u-new', data: {msgId: 'm-new', uidFrom: 'sender-1', ts: '1785812400000', content: 'private'}});
    },
    stop: () => {},
  };
  const api = {
    listener,
    getOwnId: () => 'zalo-owner-1',
    getContext: () => ({loginInfo: {send2me_id: 'my-docs'}}),
    getAllFriends: async () => { throw new Error('full scan unavailable'); },
    getUserInfo: async () => {
      lookups += 1;
      assert.equal((await new FileOutbox(path.join(stateRoot, 'unknown-source-queue')).pending()).length, 1);
      return {changed_profiles: {'u-new': {userId: 'u-new', displayName: 'Bạn mới', isFr: 1}}};
    },
  };
  class FakeZalo { async login() { return api; } }
  const fetchImpl = async (url, options = {}) => {
    if (url.endsWith('/config')) return new Response(JSON.stringify({
      policy_version: discovered ? 1 : 0,
      policy_acked_version: discovered ? 1 : 0,
      source_sync_request_version: 0,
      source_sync_acked_version: 0,
      sources: discovered ? [{conversation_id: 'u-new', display_name: 'Bạn mới', source_type: 'friend', acked_enabled: true}] : [],
      protected_media_object_keys: [],
    }), {status: 200});
    const event = JSON.parse(options.body || '{}');
    events.push(event);
    if (event.event_type === 'discovery') discovered = true;
    if (event.event_type === 'message') resolveMessage();
    const response = event.event_type === 'message'
      ? {ack: true, components: {text: event.raw_text == null ? 'absent' : 'imported', media: event.attachments.map(({attachment_index}) => ({attachment_index, status: 'imported'}))}}
      : {ack: true};
    return new Response(JSON.stringify(response), {status: 200});
  };
  const connector = await startConnector({
    Zalo: FakeZalo,
    LoginQRCallbackEventType: {},
    fetchImpl,
    env: {
      ZALO_INBOX_BACKEND_URL: 'http://backend',
      ZALO_INBOX_BOOTSTRAP_SECRET: 'bootstrap',
      ZALO_INBOX_WEBHOOK_SECRET: 'webhook',
      ZALO_INBOX_STORAGE_ROOT: path.join(root, 'media'),
      ZALO_CONNECTOR_STATE_ROOT: stateRoot,
      ZALO_CONNECTOR_RETENTION_HOURS: '72',
      ZALO_CONNECTOR_QUOTA_BYTES: '1000',
    },
  });
  try {
    await Promise.race([messageReceived, new Promise((_, reject) => setTimeout(() => reject(new Error('unknown message not continued')), 1000))]);
    assert.deepEqual(events.filter((event) => ['discovery', 'message'].includes(event.event_type)).map((event) => event.event_type), ['discovery', 'message']);
    const durableQueue = new FileOutbox(path.join(stateRoot, 'unknown-source-queue'));
    for (let remaining = 20; remaining > 0 && (await durableQueue.pending()).length; remaining -= 1) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    assert.deepEqual(await durableQueue.pending(), []);
    assert.equal(lookups, 1);
  } finally {
    connector.close();
    await rm(root, {recursive: true, force: true});
  }
});

async function startSourceSyncFixture(scans) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-source-sync-'));
  const stateRoot = path.join(root, 'state');
  await mkdir(stateRoot, {recursive: true});
  await writeFile(path.join(stateRoot, 'account.json'), JSON.stringify({connector_account_id: 'account-1'}));
  await writeFile(path.join(stateRoot, 'session.json'), JSON.stringify({cookie: []}));
  const handlers = new Map();
  const mediaEvents = [];
  let resolveMedia;
  const mediaReceived = new Promise((resolve) => { resolveMedia = resolve; });
  const listener = {
    on: (name, callback) => handlers.set(name, [...(handlers.get(name) || []), callback]),
    start: () => {},
    stop: () => {},
  };
  const api = {
    listener,
    getOwnId: () => 'zalo-owner-1',
    getAllFriends: () => scans.shift()(),
    getAllGroups: async () => ({gridVerMap: {}}),
    getContext: () => ({loginInfo: {send2me_id: ''}}),
  };
  class FakeZalo {
    async login() { return api; }
  }
  const fetchImpl = async (url, options = {}) => {
    if (url.endsWith('/config')) {
      return new Response(JSON.stringify({
        policy_version: 1,
        policy_acked_version: 1,
        source_sync_request_version: 0,
        source_sync_acked_version: 0,
        sources: [{conversation_id: 'u-b', display_name: 'Config name', source_type: 'friend', acked_enabled: true}],
        protected_media_object_keys: [],
      }), {status: 200});
    }
    const event = options.body ? JSON.parse(options.body) : {};
    if (event.event_type === 'message') {
      mediaEvents.push(event);
      resolveMedia();
    }
    return new Response(JSON.stringify({ack: true}), {status: 200});
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(Buffer.from('image'), {status: 200, headers: {'content-length': '5'}});
  const connector = await startConnector({
    Zalo: FakeZalo,
    LoginQRCallbackEventType: {},
    fetchImpl,
    env: {
      ZALO_INBOX_BACKEND_URL: 'http://backend',
      ZALO_INBOX_BOOTSTRAP_SECRET: 'bootstrap',
      ZALO_INBOX_WEBHOOK_SECRET: 'webhook',
      ZALO_INBOX_STORAGE_ROOT: path.join(root, 'media'),
      ZALO_CONNECTOR_STATE_ROOT: stateRoot,
      ZALO_CONNECTOR_RETENTION_HOURS: '72',
      ZALO_CONNECTOR_QUOTA_BYTES: '1000',
    },
  });
  return {
    trigger: (name) => handlers.get(name)[0](),
    sendMessage: () => handlers.get('message')[0]({
      type: 0,
      threadId: 'u-b',
      isSelf: false,
      data: {msgId: 'm-1', uidFrom: 'sender-1', ts: '1785812400000', content: {href: 'https://cdn.example/b.png', title: 'b.png', type: 'image/png'}},
    }),
    mediaEvents,
    mediaReceived,
    close: async () => {
      connector.close();
      globalThis.fetch = originalFetch;
      await rm(root, {recursive: true, force: true});
    },
  };
}

test('source triggers serialize blocked scans and keep the newer source inventory', async () => {
  let releaseA;
  let startedA;
  let startedB;
  const aStarted = new Promise((resolve) => { startedA = resolve; });
  const bStarted = new Promise((resolve) => { startedB = resolve; });
  const aReleased = new Promise((resolve) => { releaseA = resolve; });
  const fixture = await startSourceSyncFixture([
    async () => {
      startedA();
      await aReleased;
      return [{userId: 'u-a', displayName: 'Stale A'}];
    },
    async () => {
      startedB();
      return [{userId: 'u-b', displayName: 'Fresh B'}];
    },
  ]);
  try {
    fixture.trigger('connected');
    await aStarted;
    fixture.trigger('friend_event');
    await Promise.resolve();
    let bHasStarted = false;
    void bStarted.then(() => { bHasStarted = true; });
    await Promise.resolve();
    assert.equal(bHasStarted, false);

    releaseA();
    await bStarted;
    fixture.sendMessage();
    await fixture.mediaReceived;
    assert.equal(fixture.mediaEvents[0].source_display_name, 'Fresh B');
  } finally {
    await fixture.close();
  }
});

test('a failed queued source scan does not block the later source scan', async () => {
  let releaseA;
  let startedA;
  let startedB;
  const aStarted = new Promise((resolve) => { startedA = resolve; });
  const bStarted = new Promise((resolve) => { startedB = resolve; });
  const aReleased = new Promise((resolve) => { releaseA = resolve; });
  const fixture = await startSourceSyncFixture([
    async () => {
      startedA();
      await aReleased;
      throw new Error('scan A failed');
    },
    async () => {
      startedB();
      return [{userId: 'u-b', displayName: 'Recovered B'}];
    },
  ]);
  try {
    fixture.trigger('connected');
    await aStarted;
    fixture.trigger('group_event');
    releaseA();
    await bStarted;
    fixture.sendMessage();
    await fixture.mediaReceived;
    assert.equal(fixture.mediaEvents[0].source_display_name, 'Recovered B');
  } finally {
    await fixture.close();
  }
});

test('refreshRuntimeState stages policy fail-closed and applies it only after exact ACK success', async () => {
  const enabledIds = new Set(['unchanged-source', 'changed-source']);
  const acked = [];
  const config = {
    policy_version: 7,
    policy_acked_version: 6,
    source_sync_request_version: 0,
    source_sync_acked_version: 0,
    sources: [
      {conversation_id: 'unchanged-source', display_name: 'Unchanged', source_type: 'friend', desired_enabled: true, acked_enabled: true, policy_version: 6},
      {conversation_id: 'changed-source', display_name: 'Changed', source_type: 'friend', desired_enabled: false, acked_enabled: true, policy_version: 7},
      {conversation_id: 'new-source', display_name: 'New', source_type: 'friend', desired_enabled: true, acked_enabled: false, policy_version: 7},
    ],
    protected_media_object_keys: [],
  };
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: enabledIds,
    policyVersion: 6,
    sourceSyncAckVersion: 0,
    client: {
      getConfig: async () => config,
      ackPolicy: async (_accountId, version) => {
        assert.deepEqual([...enabledIds], ['unchanged-source']);
        acked.push(version);
      },
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });

  assert.deepEqual(acked, [7]);
  assert.equal(state.policyVersion, 7);
  assert.deepEqual([...state.enabledIds], ['unchanged-source', 'new-source']);
});

test('refreshRuntimeState keeps changed sources fail-closed on ACK failure and retries without partial activation', async () => {
  const enabledIds = new Set(['unchanged-source', 'changed-source']);
  const config = {
    policy_version: 7,
    policy_acked_version: 6,
    source_sync_request_version: 0,
    source_sync_acked_version: 0,
    sources: [
      {conversation_id: 'unchanged-source', display_name: 'Unchanged', source_type: 'friend', desired_enabled: true, acked_enabled: true, policy_version: 6},
      {conversation_id: 'changed-source', display_name: 'Changed', source_type: 'friend', desired_enabled: false, acked_enabled: true, policy_version: 7},
      {conversation_id: 'new-source', display_name: 'New', source_type: 'friend', desired_enabled: true, acked_enabled: false, policy_version: 7},
    ],
    protected_media_object_keys: [],
  };
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: enabledIds,
    policyVersion: 6,
    sourceSyncAckVersion: 0,
    client: {getConfig: async () => config, ackPolicy: async () => { throw new Error('offline'); }},
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });

  assert.equal(state.policyVersion, 6);
  assert.deepEqual([...state.enabledIds], ['unchanged-source']);
});

test('refreshRuntimeState keeps the prior effective policy on config failure', async () => {
  const enabledIds = new Set(['prior-source']);
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: enabledIds,
    policyVersion: 6,
    sourceSyncAckVersion: 1,
    client: {getConfig: async () => { throw new Error('offline'); }},
    store: {prune: async () => assert.fail('config failure must not prune')},
  });
  assert.equal(state.policyVersion, 6);
  assert.equal(state.sourceSyncAckVersion, 1);
  assert.deepEqual([...state.enabledIds], ['prior-source']);
});

test('refreshRuntimeState rejects a malformed source before mutating effective runtime state', async () => {
  const enabledIds = new Set(['prior-source']);
  const state = await refreshRuntimeState({
    accountId: 'account-1', activeEnabledIds: enabledIds, policyVersion: 6, sourceSyncAckVersion: 2,
    client: {getConfig: async () => ({
      policy_version: 7, policy_acked_version: 7,
      source_sync_request_version: 3, source_sync_acked_version: 3,
      sources: [{conversation_id: 'attacker', display_name: 'Bad', source_type: 'invalid', acked_enabled: true}],
      protected_media_object_keys: [],
    }), ackPolicy: async () => assert.fail('invalid config must not ACK')},
    store: {prune: async () => assert.fail('invalid config must not prune')},
  });
  assert.deepEqual([...enabledIds], ['prior-source']);
  assert.equal(state.policyVersion, 6);
  assert.equal(state.sourceSyncAckVersion, 2);
  assert.equal(state.sourceMap, null);
});

test('refreshRuntimeState rejects blank source metadata before mutating effective runtime state', async () => {
  const enabledIds = new Set(['prior-source']);
  const state = await refreshRuntimeState({
    accountId: 'account-1', activeEnabledIds: enabledIds, policyVersion: 6, sourceSyncAckVersion: 2,
    client: {getConfig: async () => ({
      policy_version: 7, policy_acked_version: 7,
      source_sync_request_version: 3, source_sync_acked_version: 3,
      sources: [{conversation_id: 'attacker', display_name: '', source_type: 'friend', acked_enabled: true}],
      protected_media_object_keys: [],
    })},
    store: {prune: async () => assert.fail('invalid config must not prune')},
  });
  assert.deepEqual([...enabledIds], ['prior-source']);
  assert.equal(state.policyVersion, 6);
  assert.equal(state.sourceSyncAckVersion, 2);
  assert.equal(state.sourceMap, null);
});

test('refreshRuntimeState does not ACK-loop an already applied policy replay', async () => {
  const enabledIds = new Set(['unchanged-source', 'new-source']);
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: enabledIds,
    policyVersion: 7,
    sourceSyncAckVersion: 0,
    client: {
      getConfig: async () => ({
        policy_version: 7,
        policy_acked_version: 7,
        source_sync_request_version: 0,
        source_sync_acked_version: 0,
        sources: [
          {conversation_id: 'unchanged-source', display_name: 'Unchanged', source_type: 'friend', desired_enabled: true, acked_enabled: true, policy_version: 7},
          {conversation_id: 'new-source', display_name: 'New', source_type: 'friend', desired_enabled: true, acked_enabled: true, policy_version: 7},
        ],
        protected_media_object_keys: [],
      }),
      ackPolicy: async () => assert.fail('same policy version must not ACK again'),
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });
  assert.deepEqual([...state.enabledIds], ['unchanged-source', 'new-source']);
});

test('restart reconstructs a fully ACKed production config without sending another ACK', async () => {
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    client: {
      getConfig: async () => ({
        policy_version: 7,
        policy_acked_version: 7,
        source_sync_request_version: 0,
        source_sync_acked_version: 0,
        sources: [
          {conversation_id: 'active-source', display_name: 'Active', source_type: 'friend', desired_enabled: true, acked_enabled: true, policy_version: 7},
          {conversation_id: 'disabled-source', display_name: 'Disabled', source_type: 'friend', desired_enabled: false, acked_enabled: false, policy_version: 7},
        ],
        protected_media_object_keys: [],
      }),
      ackPolicy: async () => assert.fail('already-ACKed policy must not ACK again'),
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });

  assert.equal(state.policyVersion, 7);
  assert.deepEqual([...state.enabledIds], ['active-source']);
});

test('restart keeps only unchanged ACK-active production sources when the desired policy ACK fails', async () => {
  const acked = [];
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    client: {
      getConfig: async () => ({
        policy_version: 8,
        policy_acked_version: 7,
        source_sync_request_version: 0,
        source_sync_acked_version: 0,
        sources: [
          {conversation_id: 'unchanged-source', display_name: 'Unchanged', source_type: 'friend', desired_enabled: true, acked_enabled: true, policy_version: 7},
          {conversation_id: 'changed-off', display_name: 'Changed Off', source_type: 'friend', desired_enabled: false, acked_enabled: true, policy_version: 8},
          {conversation_id: 'changed-on', display_name: 'Changed On', source_type: 'friend', desired_enabled: true, acked_enabled: false, policy_version: 8},
        ],
        protected_media_object_keys: [],
      }),
      ackPolicy: async (_accountId, version) => { acked.push(version); throw new Error('offline'); },
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });

  assert.deepEqual(acked, [8]);
  assert.equal(state.policyVersion, 7);
  assert.deepEqual([...state.enabledIds], ['unchanged-source']);
});

test('refreshRuntimeState reports hard quota and keeps the backend allowlist', async () => {
  const calls = [];
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    policyVersion: 0,
    sourceSyncAckVersion: 0,
    client: {
      getConfig: async () => ({
        policy_version: 1,
        policy_acked_version: 0,
        source_sync_request_version: 0,
        source_sync_acked_version: 0,
        sources: [{conversation_id: 'g-1', display_name: 'Group', source_type: 'group', desired_enabled: true, acked_enabled: false, policy_version: 1}],
        protected_media_object_keys: ['account-1/protected.png'],
      }),
      ackPolicy: async () => {},
    },
    store: {prune: async (options) => {
      calls.push(options);
      return {usageBytes: 100, storageFull: true};
    }},
  });
  assert.deepEqual([...state.enabledIds], ['g-1']);
  assert.equal(state.storageFull, true);
  assert.deepEqual(calls, [{protectedKeys: new Set(['account-1/protected.png'])}]);
});

test('source-sync request advances only after all discovery webhooks and exact ACK succeed', async () => {
  const order = [];
  const api = {
    getAllFriends: async () => [{userId: 'u-1', displayName: 'Bạn A'}],
    getAllGroups: async () => ({gridVerMap: {}}),
    getContext: () => ({loginInfo: {send2me_id: 'my-docs'}}),
  };
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    policyVersion: 4,
    sourceSyncAckVersion: 1,
    api,
    client: {
      getConfig: async () => ({policy_version: 4, policy_acked_version: 4, source_sync_request_version: 2, source_sync_acked_version: 1, sources: [], protected_media_object_keys: []}),
      sendEvent: async (event) => order.push(`discover:${event.source_type}`),
      ackSourceSync: async (_accountId, version) => order.push(`ack:${version}`),
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });
  assert.deepEqual(order, ['discover:friend', 'discover:my_documents', 'ack:2']);
  assert.equal(state.sourceSyncAckVersion, 2);
  assert.deepEqual([...state.sourceMap.keys()], ['u-1', 'my-docs']);
});

test('failed discovery does not ACK or advance source-sync request version; stale requests do not scan', async () => {
  let scans = 0;
  let acks = 0;
  const api = {
    getAllFriends: async () => { scans += 1; return [{userId: 'u-1', displayName: 'Bạn A'}]; },
    getAllGroups: async () => ({gridVerMap: {}}),
    getContext: () => ({loginInfo: {send2me_id: ''}}),
  };
  const base = {
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    policyVersion: 4,
    sourceSyncAckVersion: 2,
    api,
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  };
  const failed = await refreshRuntimeState({
    ...base,
    sourceSyncAckVersion: 1,
    client: {
      getConfig: async () => ({policy_version: 4, policy_acked_version: 4, source_sync_request_version: 2, source_sync_acked_version: 1, sources: [], protected_media_object_keys: []}),
      sendEvent: async () => { throw new Error('discovery failed'); },
      ackSourceSync: async () => { acks += 1; },
    },
  });
  assert.equal(failed.sourceSyncAckVersion, 1);
  assert.equal(acks, 0);

  scans = 0;
  const stale = await refreshRuntimeState({
    ...base,
    client: {
      getConfig: async () => ({policy_version: 4, policy_acked_version: 4, source_sync_request_version: 2, source_sync_acked_version: 2, sources: [], protected_media_object_keys: []}),
      sendEvent: async () => assert.fail('equal request version must not scan'),
      ackSourceSync: async () => assert.fail('equal request version must not ACK'),
    },
  });
  assert.equal(stale.sourceSyncAckVersion, 2);
  assert.equal(scans, 0);
});

test('config display_name remains the source map fallback when discovery fails', async () => {
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    api: {
      getAllFriends: async () => [{userId: 'u-1', displayName: 'stale scan name'}],
      getAllGroups: async () => ({gridVerMap: {}}),
    },
    client: {
      getConfig: async () => ({
        policy_version: 3,
        policy_acked_version: 3,
        source_sync_request_version: 2,
        source_sync_acked_version: 1,
        sources: [{conversation_id: 'u-1', display_name: 'Config name', acked_enabled: true}],
        protected_media_object_keys: [],
      }),
      sendEvent: async () => { throw new Error('discovery unavailable'); },
      ackSourceSync: async () => assert.fail('failed discovery must not ACK'),
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });

  assert.equal(state.sourceMap.get('u-1').source_display_name, 'Config name');
  assert.deepEqual([...state.enabledIds], ['u-1']);
  assert.equal(state.sourceSyncAckVersion, 1);
});

test('source-sync request version advances only after source_sync_ack HTTP success', async () => {
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    policyVersion: 4,
    sourceSyncAckVersion: 1,
    api: {
      getAllFriends: async () => [],
      getAllGroups: async () => ({gridVerMap: {}}),
      getContext: () => ({loginInfo: {send2me_id: ''}}),
    },
    client: {
      getConfig: async () => ({policy_version: 4, policy_acked_version: 4, source_sync_request_version: 2, source_sync_acked_version: 1, sources: [], protected_media_object_keys: []}),
      ackSourceSync: async () => { throw new Error('offline'); },
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });
  assert.equal(state.sourceSyncAckVersion, 1);
  assert.deepEqual([...state.sourceMap.keys()], []);
});

test('restart does not scan an already-ACKed source-sync request on config poll', async () => {
  let scans = 0;
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    api: {
      getAllFriends: async () => { scans += 1; return []; },
      getAllGroups: async () => ({gridVerMap: {}}),
    },
    client: {
      getConfig: async () => ({
        policy_version: 0,
        policy_acked_version: 0,
        source_sync_request_version: 3,
        source_sync_acked_version: 3,
        sources: [],
        protected_media_object_keys: [],
      }),
      ackSourceSync: async () => assert.fail('already-ACKed request must not ACK again'),
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  });

  assert.equal(scans, 0);
  assert.equal(state.sourceSyncAckVersion, 3);
});

test('an unACKed source-sync request retries on a later config poll', async () => {
  let scans = 0;
  let discoveryAttempts = 0;
  const acknowledgements = [];
  const fixture = {
    accountId: 'account-1',
    activeEnabledIds: new Set(),
    api: {
      getAllFriends: async () => { scans += 1; return [{userId: 'u-1', displayName: 'Bạn A'}]; },
      getAllGroups: async () => ({gridVerMap: {}}),
      getContext: () => ({loginInfo: {send2me_id: ''}}),
    },
    client: {
      getConfig: async () => ({
        policy_version: 0,
        policy_acked_version: 0,
        source_sync_request_version: 3,
        source_sync_acked_version: 2,
        sources: [],
        protected_media_object_keys: [],
      }),
      sendEvent: async () => {
        discoveryAttempts += 1;
        if (discoveryAttempts === 1) throw new Error('discovery failed');
      },
      ackSourceSync: async (_accountId, version) => acknowledgements.push(version),
    },
    store: {prune: async () => ({usageBytes: 0, storageFull: false})},
  };

  const failed = await refreshRuntimeState(fixture);
  const retried = await refreshRuntimeState({
    ...fixture,
    policyVersion: failed.policyVersion,
    sourceSyncAckVersion: failed.sourceSyncAckVersion,
  });

  assert.equal(scans, 2);
  assert.deepEqual(acknowledgements, [3]);
  assert.equal(failed.sourceSyncAckVersion, 2);
  assert.equal(retried.sourceSyncAckVersion, 3);
});

test('source sync runs after login and uses exact listener event names plus a 60-minute timer', async () => {
  const handlers = new Map();
  let timerCallback;
  let reconciliations = 0;
  const timer = await installSourceSyncTriggers({
    listener: {on: (name, callback) => handlers.set(name, callback)},
    reconcile: async () => { reconciliations += 1; },
    sourceReconcileMs: 3600000,
    setTimer: (callback, milliseconds) => {
      assert.equal(milliseconds, 3600000);
      timerCallback = callback;
      return 'source-timer';
    },
  });
  assert.equal(timer, 'source-timer');
  assert.equal(reconciliations, 1);
  assert.deepEqual([...handlers.keys()], ['connected', 'friend_event', 'group_event']);
  handlers.get('connected')();
  handlers.get('friend_event')();
  handlers.get('group_event')();
  timerCallback();
  await Promise.resolve();
  assert.equal(reconciliations, 5);
});

test('initial source discovery failure leaves listener triggers installed for retry', async () => {
  const handlers = new Map();
  let timerCallback;
  let reconciliations = 0;
  const timer = await installSourceSyncTriggers({
    listener: {on: (name, callback) => handlers.set(name, callback)},
    reconcile: async () => {
      reconciliations += 1;
      if (reconciliations === 1) throw new Error('initial discovery failed');
    },
    sourceReconcileMs: 3600000,
    setTimer: (callback) => { timerCallback = callback; return 'source-timer'; },
  });

  assert.equal(timer, 'source-timer');
  assert.deepEqual([...handlers.keys()], ['connected', 'friend_event', 'group_event']);
  handlers.get('connected')();
  timerCallback();
  await Promise.resolve();
  assert.equal(reconciliations, 3);
});

test('startup can install source triggers without a duplicate unconditional scan', async () => {
  let reconciliations = 0;
  await installSourceSyncTriggers({
    listener: {on: () => {}},
    reconcile: async () => { reconciliations += 1; },
    sourceReconcileMs: 3600000,
    runInitial: false,
    setTimer: () => 'source-timer',
  });
  assert.equal(reconciliations, 0);
});

test('QR callback publishes a browser-safe image, saves it, and retries expiry without leaking token', async () => {
  const states = [];
  const sessions = [];
  let saved = 0;
  let retried = 0;
  const eventTypes = {QRCodeGenerated: 0, QRCodeExpired: 1, GotLoginInfo: 4};

  await handleQrLoginEvent({
    event: {
      type: 0,
      data: {image: 'cG5n', token: 'must-not-leak'},
      actions: {saveToFile: async () => { saved += 1; }},
    },
    eventTypes,
    stateEvent: async (state, payload) => states.push({state, payload}),
    rememberSession: (session) => sessions.push(session),
  });
  await handleQrLoginEvent({
    event: {type: 1, data: null, actions: {retry: () => { retried += 1; }}},
    eventTypes,
    stateEvent: async (state, payload) => states.push({state, payload}),
    rememberSession: () => {},
  });
  await handleQrLoginEvent({
    event: {type: 4, data: {cookie: [], imei: 'i', userAgent: 'u'}, actions: null},
    eventTypes,
    stateEvent: async () => {},
    rememberSession: (session) => sessions.push(session),
  });

  assert.equal(saved, 1);
  assert.equal(retried, 1);
  assert.deepEqual(states, [
    {state: 'login_required', payload: {qr_image: 'data:image/png;base64,cG5n'}},
    {state: 'login_required', payload: {qr_image: ''}},
  ]);
  assert.equal(JSON.stringify(states).includes('must-not-leak'), false);
  assert.deepEqual(sessions, [{cookie: [], imei: 'i', userAgent: 'u'}]);
});

test('QR publication failure aborts login instead of leaving a pending connector', async () => {
  let aborted = 0;
  await assert.rejects(
    handleQrLoginEvent({
      event: {
        type: 0,
        data: {image: 'cG5n'},
        actions: {saveToFile: async () => {}, abort: () => { aborted += 1; }},
      },
      eventTypes: {QRCodeGenerated: 0, QRCodeExpired: 1, QRCodeDeclined: 3, GotLoginInfo: 4},
      stateEvent: async () => { throw new Error('backend unavailable'); },
      rememberSession: () => {},
    }),
    /backend unavailable/,
  );
  assert.equal(aborted, 1);
});

test('declined QR clears the stale image and immediately creates a replacement', async () => {
  const states = [];
  let retried = 0;
  await handleQrLoginEvent({
    event: {
      type: 3,
      data: {code: 'must-not-leak'},
      actions: {retry: () => { retried += 1; }},
    },
    eventTypes: {QRCodeGenerated: 0, QRCodeExpired: 1, QRCodeDeclined: 3, GotLoginInfo: 4},
    stateEvent: async (state, payload) => states.push({state, payload}),
    rememberSession: () => {},
  });

  assert.deepEqual(states, [{state: 'login_required', payload: {qr_image: ''}}]);
  assert.equal(retried, 1);
  assert.equal(JSON.stringify(states).includes('must-not-leak'), false);

  retried = 0;
  await assert.rejects(
    handleQrLoginEvent({
      event: {type: 3, data: {code: 'hidden'}, actions: {retry: () => { retried += 1; }}},
      eventTypes: {QRCodeGenerated: 0, QRCodeExpired: 1, QRCodeDeclined: 3, GotLoginInfo: 4},
      stateEvent: async () => { throw new Error('backend unavailable'); },
      rememberSession: () => {},
    }),
    /backend unavailable/,
  );
  assert.equal(retried, 1);
});

test('expired QR retries synchronously before waiting for backend cleanup', async () => {
  const order = [];
  let releaseCleanup;
  const cleanup = new Promise((resolve) => { releaseCleanup = resolve; });
  const handling = handleQrLoginEvent({
    event: {
      type: 1,
      data: null,
      actions: {retry: () => order.push('retry')},
    },
    eventTypes: {QRCodeGenerated: 0, QRCodeExpired: 1, QRCodeDeclined: 3, GotLoginInfo: 4},
    stateEvent: async () => {
      order.push('cleanup-start');
      await cleanup;
      order.push('cleanup-finish');
    },
    rememberSession: () => {},
  });

  await Promise.resolve();
  assert.deepEqual(order, ['retry', 'cleanup-start']);
  releaseCleanup();
  await handling;
});

test('authenticated session binds the account but waits for listener heartbeat before connected', async () => {
  const states = [];
  await publishConnectedState({
    api: {getOwnId: () => 'zalo-owner-1'},
    stateEvent: async (state, payload) => states.push({state, payload}),
    qrLoginSuccess: true,
  });
  assert.deepEqual(states, [{state: 'disconnected', payload: {qr_login_success: true, bound_zalo_id: 'zalo-owner-1'}}]);

  states.length = 0;
  await publishConnectedState({
    api: {getOwnId: () => 'zalo-owner-1'},
    stateEvent: async (state, payload) => states.push({state, payload}),
    qrLoginSuccess: false,
  });
  assert.deepEqual(states, [{state: 'disconnected', payload: {qr_login_success: false, bound_zalo_id: 'zalo-owner-1'}}]);
});

test('QR session is persisted only after backend accepts the bound account', async () => {
  let saved = 0;
  await assert.rejects(
    finalizeQrLogin({
      api: {getOwnId: () => 'wrong-owner'},
      stateEvent: async () => { throw new Error('backend returned HTTP 409'); },
      session: {cookie: []},
      saveSession: async () => { saved += 1; },
    }),
    /409/,
  );
  assert.equal(saved, 0);

  const order = [];
  await finalizeQrLogin({
    api: {getOwnId: () => 'zalo-owner-1'},
    stateEvent: async () => order.push('backend-ack'),
    session: {cookie: []},
    saveSession: async () => order.push('session-saved'),
  });
  assert.deepEqual(order, ['backend-ack', 'session-saved']);
});

test('restored session mismatch is removed and returns connector to login-required', async () => {
  const order = [];
  await assert.rejects(
    verifyRestoredSession({
      api: {getOwnId: () => 'wrong-owner'},
      stateEvent: async (state) => {
        order.push(state);
        if (state === 'disconnected') throw new Error('backend returned HTTP 409');
      },
      deleteSession: async () => order.push('session-deleted'),
    }),
    /409/,
  );
  assert.deepEqual(order, ['disconnected', 'session-deleted', 'login_required']);
});

test('parent liveness treats only missing process as dead', () => {
  assert.equal(isParentAlive('123', () => {}), true);
  assert.equal(isParentAlive('123', () => { const error = new Error('missing'); error.code = 'ESRCH'; throw error; }), false);
  assert.equal(isParentAlive('123', () => { const error = new Error('denied'); error.code = 'EPERM'; throw error; }), true);
});

test('parent watch exits only after the managed FastAPI parent disappears', () => {
  let callback = null;
  let exited = 0;
  const timer = startParentWatch('123', {
    isAlive: () => false,
    onDead: () => { exited += 1; },
    setTimer: (fn, ms) => { callback = fn; assert.equal(ms, 2000); return 'timer'; },
  });
  assert.equal(timer, 'timer');
  callback();
  assert.equal(exited, 1);
  assert.equal(startParentWatch('', {setTimer: () => assert.fail('timer must not start')}), null);
});

test('heartbeat never reports connected while the Zalo listener is down', () => {
  assert.equal(listenerHeartbeatState(true), 'connected');
  assert.equal(listenerHeartbeatState(false), 'disconnected');
});

test('login-required restart forces a new QR instead of restoring the stale session', () => {
  const session = {cookie: []};
  assert.equal(shouldRestoreSession(session, {}), true);
  assert.equal(shouldRestoreSession(session, {ZALO_CONNECTOR_FORCE_QR: '1'}), false);
  assert.equal(shouldRestoreSession(null, {}), false);
});
