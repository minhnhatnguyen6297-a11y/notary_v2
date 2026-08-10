import assert from 'node:assert/strict';
import {mkdir, mkdtemp, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {createZaloClient, finalizeQrLogin, handleMessage, handleQrLoginEvent, installSourceSyncTriggers, isParentAlive, listenerHeartbeatState, publishConnectedState, readSettings, refreshRuntimeState, shouldRestoreSession, sourceDescriptor, startConnector, startParentWatch, syncSources, verifyRestoredSession} from '../src/connector.mjs';

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

test('zca-js logging is disabled before login can expose Zalo identifiers', () => {
  class FakeZalo {
    constructor(options) {
      this.options = options;
    }
  }
  assert.deepEqual(createZaloClient(FakeZalo).options, {logging: false});
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

test('handleMessage publishes only after durable media download and strips remote URL', async () => {
  const order = [];
  const queued = [];
  const pendingDownloads = [];
  const store = {
    download: async (key, url) => {
      order.push(`download:${url}`);
      return {path: `/data/${key}`, sizeBytes: 123};
    },
  };
  const outbox = {
    enqueue: async (id, event) => { order.push('enqueue'); queued.push({id, event}); },
    flush: async () => order.push('flush'),
  };
  const downloadQueue = {
    enqueue: async (id, event) => { order.push('queue-download'); pendingDownloads.push({name: id, event}); },
    entries: async () => pendingDownloads,
    remove: async () => order.push('remove-download'),
  };
  const message = {
    type: 1,
    threadId: 'g-1',
    isSelf: false,
    data: {
      msgId: 'm-1',
      ts: '1785812400000',
      content: {href: 'https://cdn.example/a.png', title: 'a.png', type: 'image/png'},
    },
  };
  await handleMessage({
    message,
    accountId: 'account-1',
    enabledIds: new Set(['g-1']),
    sourceNames: new Map([['g-1', 'Nhóm A']]),
    store,
    outbox,
    downloadQueue,
    client: {},
  });

  assert.deepEqual(order, ['queue-download', 'download:https://cdn.example/a.png', 'enqueue', 'remove-download', 'flush']);
  assert.equal(queued.length, 1);
  assert.equal(queued[0].event.size_bytes, 123);
  assert.match(queued[0].event.media_object_key, /^account-1\//);
  assert.equal('download_url' in queued[0].event, false);
});

test('startConnector refreshes config and fallback source map before listener.start handles an immediate message', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'zalo-start-'));
  const stateRoot = path.join(root, 'state');
  await mkdir(stateRoot, {recursive: true});
  await writeFile(path.join(stateRoot, 'account.json'), JSON.stringify({connector_account_id: 'account-1'}));
  await writeFile(path.join(stateRoot, 'session.json'), JSON.stringify({cookie: []}));
  const order = [];
  const handlers = new Map();
  let mediaEvents = 0;
  let resolveMedia;
  const mediaReceived = new Promise((resolve) => { resolveMedia = resolve; });
  const listener = {
    on: (name, callback) => handlers.set(name, callback),
    start: () => {
      order.push('listener.start');
      handlers.get('message')({
        type: 1,
        threadId: 'g-1',
        isSelf: false,
        data: {msgId: 'm-1', ts: '1785812400000', content: {href: 'https://cdn.example/a.png', title: 'a.png', type: 'image/png'}},
      });
    },
    stop: () => {},
  };
  const api = {
    listener,
    getOwnId: () => 'zalo-owner-1',
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
        sources: [{conversation_id: 'g-1', display_name: 'Config group', acked_enabled: true}],
        protected_media_object_keys: [],
      }), {status: 200});
    }
    const event = options.body ? JSON.parse(options.body) : {};
    if (event.event_type === 'media') {
      mediaEvents += 1;
      resolveMedia();
    }
    return new Response(JSON.stringify({ack: true}), {status: 200});
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
      mediaReceived,
      new Promise((_, reject) => setTimeout(() => reject(new Error('immediate message was not handled')), 1000)),
    ]);
    assert.ok(order.indexOf('config') < order.indexOf('listener.start'));
    assert.ok(order.indexOf('initial-scan') < order.indexOf('listener.start'));
    assert.equal(mediaEvents, 1);
  } finally {
    connector?.close();
    globalThis.fetch = originalFetch;
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
        sources: [{conversation_id: 'u-b', display_name: 'Config name', acked_enabled: true}],
        protected_media_object_keys: [],
      }), {status: 200});
    }
    const event = options.body ? JSON.parse(options.body) : {};
    if (event.event_type === 'media') {
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
      data: {msgId: 'm-1', ts: '1785812400000', content: {href: 'https://cdn.example/b.png', title: 'b.png', type: 'image/png'}},
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
      {conversation_id: 'unchanged-source', desired_enabled: true, acked_enabled: true, policy_version: 6},
      {conversation_id: 'changed-source', desired_enabled: false, acked_enabled: true, policy_version: 7},
      {conversation_id: 'new-source', desired_enabled: true, acked_enabled: false, policy_version: 7},
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
      {conversation_id: 'unchanged-source', desired_enabled: true, acked_enabled: true, policy_version: 6},
      {conversation_id: 'changed-source', desired_enabled: false, acked_enabled: true, policy_version: 7},
      {conversation_id: 'new-source', desired_enabled: true, acked_enabled: false, policy_version: 7},
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
          {conversation_id: 'unchanged-source', desired_enabled: true, acked_enabled: true, policy_version: 7},
          {conversation_id: 'new-source', desired_enabled: true, acked_enabled: true, policy_version: 7},
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
          {conversation_id: 'active-source', desired_enabled: true, acked_enabled: true, policy_version: 7},
          {conversation_id: 'disabled-source', desired_enabled: false, acked_enabled: false, policy_version: 7},
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
          {conversation_id: 'unchanged-source', desired_enabled: true, acked_enabled: true, policy_version: 7},
          {conversation_id: 'changed-off', desired_enabled: false, acked_enabled: true, policy_version: 8},
          {conversation_id: 'changed-on', desired_enabled: true, acked_enabled: false, policy_version: 8},
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
        sources: [{conversation_id: 'g-1', desired_enabled: true, acked_enabled: false, policy_version: 1}],
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

  assert.equal(state.sourceMap.get('u-1'), 'Config name');
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
