import assert from 'node:assert/strict';
import test from 'node:test';

import {createZaloClient, discoverSources, finalizeQrLogin, handleMessage, handleQrLoginEvent, isParentAlive, listenerHeartbeatState, publishConnectedState, readSettings, refreshRuntimeState, shouldRestoreSession, startParentWatch, verifyRestoredSession} from '../src/connector.mjs';

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
});

test('zca-js logging is disabled before login can expose Zalo identifiers', () => {
  class FakeZalo {
    constructor(options) {
      this.options = options;
    }
  }
  assert.deepEqual(createZaloClient(FakeZalo).options, {logging: false});
});

test('discoverSources publishes one source event per friend and group', async () => {
  const api = {
    getAllFriends: async () => [{userId: 'u-1', displayName: 'Bạn A'}],
    getAllGroups: async () => ({gridVerMap: {'g-1': 'v1'}}),
    getGroupInfo: async () => ({gridInfoMap: {'g-1': {name: 'Nhóm A'}}}),
  };
  const events = [];
  await discoverSources(api, 'account-1', {sendEvent: async (event) => events.push(event)});
  assert.deepEqual(events.map(({conversation_id, conversation_type, source_display_name}) => ({conversation_id, conversation_type, source_display_name})), [
    {conversation_id: 'u-1', conversation_type: 'user', source_display_name: 'Bạn A'},
    {conversation_id: 'g-1', conversation_type: 'group', source_display_name: 'Nhóm A'},
  ]);
  assert.ok(events.every((event) => event.schema_version === 1 && event.event_type === 'discovery'));
});

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

test('refreshRuntimeState reports hard quota and keeps the backend allowlist', async () => {
  const calls = [];
  const state = await refreshRuntimeState({
    accountId: 'account-1',
    client: {getConfig: async () => ({
      sources: [{conversation_id: 'g-1', enabled: true}],
      protected_media_object_keys: ['account-1/protected.png'],
    })},
    store: {prune: async (options) => {
      calls.push(options);
      return {usageBytes: 100, storageFull: true};
    }},
  });
  assert.deepEqual([...state.enabledIds], ['g-1']);
  assert.equal(state.storageFull, true);
  assert.deepEqual(calls, [{protectedKeys: new Set(['account-1/protected.png'])}]);
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
