import {mkdir, readFile, rename, unlink, writeFile} from 'node:fs/promises';
import path from 'node:path';

import {FileOutbox, MediaStore, WebhookClient, mediaObjectKey, normalizeMessage} from './core.mjs';

const required = [
  'ZALO_INBOX_BACKEND_URL',
  'ZALO_INBOX_BOOTSTRAP_SECRET',
  'ZALO_INBOX_WEBHOOK_SECRET',
  'ZALO_INBOX_STORAGE_ROOT',
  'ZALO_CONNECTOR_RETENTION_HOURS',
  'ZALO_CONNECTOR_QUOTA_BYTES',
];

export function readSettings(env = process.env) {
  const missing = required.filter((name) => !String(env[name] || '').trim());
  if (missing.length) throw new Error(`required connector settings missing: ${missing.join(', ')}`);
  const retentionHours = Number(env.ZALO_CONNECTOR_RETENTION_HOURS);
  const quotaBytes = Number(env.ZALO_CONNECTOR_QUOTA_BYTES);
  if (!Number.isFinite(retentionHours) || retentionHours <= 0 || !Number.isSafeInteger(quotaBytes) || quotaBytes <= 0) {
    throw new Error('retention hours and quota bytes must be positive numbers');
  }
  return {
    backendUrl: env.ZALO_INBOX_BACKEND_URL,
    bootstrapSecret: env.ZALO_INBOX_BOOTSTRAP_SECRET,
    webhookSecret: env.ZALO_INBOX_WEBHOOK_SECRET,
    storageRoot: path.resolve(env.ZALO_INBOX_STORAGE_ROOT),
    stateRoot: path.resolve(env.ZALO_CONNECTOR_STATE_ROOT || 'runtime/zalo_connector'),
    retentionHours,
    quotaBytes,
    heartbeatMs: 15000,
    configPollMs: 15000,
    sourceReconcileMs: 3600000,
  };
}

const observedAt = () => new Date().toISOString();
const MY_DOCUMENTS_REALTIME_VERIFIED = false;

export function createZaloClient(Zalo) {
  return new Zalo({logging: false, selfListen: true});
}

function normalizeActivity(value) {
  if (value === undefined || value === null || value === '') return null;
  const number = Number(value);
  const date = Number.isFinite(number)
    ? new Date(number < 1e12 ? number * 1000 : number)
    : new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error('last activity is invalid');
  return date.toISOString();
}

export function sourceDescriptor({conversationId, sourceType, displayName, lastActivityAt}) {
  const conversationIdValue = String(conversationId || '').trim();
  const displayNameValue = String(displayName || '').trim();
  if (!conversationIdValue) throw new Error('conversation id is required');
  if (!['friend', 'group', 'stranger', 'my_documents'].includes(sourceType)) throw new Error('source type is invalid');
  if (!displayNameValue) throw new Error('display name is required');
  return {
    conversation_id: conversationIdValue,
    conversation_type: sourceType === 'group' ? 'group' : 'user',
    source_display_name: displayNameValue,
    source_type: sourceType,
    last_activity_at: normalizeActivity(lastActivityAt),
  };
}

export async function resolveUnknownSource(api, message, send2meId) {
  const conversationId = String(message?.threadId || '').trim();
  if (!conversationId) return {status: 'retryable_failure', error_code: 'source_response_invalid'};
  if (conversationId === String(send2meId || '')) {
    return {status: 'resolved', source: sourceDescriptor({
      conversationId,
      sourceType: 'my_documents',
      displayName: 'My Documents',
    })};
  }
  if (![0, 1].includes(message?.type)) {
    return {status: 'retryable_failure', error_code: 'source_response_invalid'};
  }
  try {
    if (message?.type === 1) {
      const response = await api.getGroupInfo([conversationId]);
      const profile = response?.gridInfoMap?.[conversationId];
      const profileId = String(profile?.groupId || profile?.grid || conversationId);
      if (!profile || profileId !== conversationId || !String(profile.name || '').trim()) {
        return {status: 'retryable_failure', error_code: 'source_response_invalid'};
      }
      return {status: 'resolved', source: sourceDescriptor({
        conversationId,
        sourceType: 'group',
        displayName: profile.name,
      })};
    }
    const response = await api.getUserInfo(conversationId);
    const profile = response?.changed_profiles?.[conversationId] ?? response?.[conversationId];
    const profileId = String(profile?.userId || profile?.user_id || '');
    const displayName = String(profile?.displayName || profile?.zaloName || '').trim();
    if (!profile || profileId !== conversationId || !displayName || ![0, 1].includes(profile.isFr)) {
      return {status: 'retryable_failure', error_code: 'source_response_invalid'};
    }
    const source = sourceDescriptor({
      conversationId,
      sourceType: profile.isFr === 0 ? 'stranger' : 'friend',
      displayName,
      lastActivityAt: profile.lastActionTime,
    });
    return {status: profile.isFr === 0 ? 'confirmed_stranger' : 'resolved', source};
  } catch {
    return {status: 'retryable_failure', error_code: 'source_lookup_failed'};
  }
}

export async function processUnknownSourceQueue({
  api,
  accountId,
  send2meId,
  unknownQueue,
  client,
  refresh,
  enabledIds,
  sourceNames,
  handleKnownMessage,
  reportError = () => {},
  now = Date.now,
}) {
  for (const {name, event} of await unknownQueue.entries()) {
    const current = now();
    if (event.next_attempt_at && Date.parse(event.next_attempt_at) > current) continue;
    const result = await resolveUnknownSource(api, event.message, send2meId);
    if (result.status === 'retryable_failure') {
      const attempts = Number(event.attempts || 0) + 1;
      if (attempts >= 3) {
        await unknownQueue.remove(name);
        await reportError(result.error_code);
      } else {
        const nextAttemptAt = new Date(current + 1000 * 2 ** (attempts - 1)).toISOString();
        await unknownQueue.replace(name, {...event, attempts, next_attempt_at: nextAttemptAt});
      }
      continue;
    }
    await client.sendEvent({
      schema_version: 1,
      event_type: 'discovery',
      connector_account_id: accountId,
      ...result.source,
      last_activity_at: normalizeActivity(event.message?.data?.ts) || observedAt(),
    });
    sourceNames.set(result.source.conversation_id, result.source);
    if (result.status === 'resolved') {
      await refresh();
      if (enabledIds.has(result.source.conversation_id)) await handleKnownMessage(event.message, false);
    }
    await unknownQueue.remove(name);
  }
}

export async function syncSources({api, accountId, client, send2meId}) {
  const sources = new Map();
  const publish = async (descriptor) => {
    sources.set(descriptor.conversation_id, descriptor);
    await client.sendEvent({
      schema_version: 1,
      event_type: 'discovery',
      connector_account_id: accountId,
      ...descriptor,
    });
  };
  const friends = await api.getAllFriends();
  for (const friend of friends) {
    const id = String(friend.userId || '');
    await publish(sourceDescriptor({
      conversationId: id,
      sourceType: 'friend',
      displayName: friend.displayName || friend.zaloName || id,
      lastActivityAt: friend.lastActionTime,
    }));
  }
  const groups = await api.getAllGroups();
  const groupIds = Object.keys(groups.gridVerMap || {});
  if (groupIds.length) {
    const details = await api.getGroupInfo(groupIds);
    for (const id of groupIds) {
      await publish(sourceDescriptor({
        conversationId: id,
        sourceType: 'group',
        displayName: details.gridInfoMap?.[id]?.name || id,
      }));
    }
  }
  const contextSend2meId = send2meId ?? api.getContext?.()?.loginInfo?.send2me_id;
  if (contextSend2meId) {
    await publish(sourceDescriptor({
      conversationId: contextSend2meId,
      sourceType: 'my_documents',
      displayName: 'My Documents',
    }));
  }
  return sources;
}

export async function processDownloadQueue({downloadQueue, store, outbox, client}) {
  const entries = await downloadQueue.entries();
  const assemblies = new Map(entries
    .filter(({event}) => event.record_type === 'message')
    .map((entry) => [entry.event.message_key, entry]));
  for (const {name, event} of entries.filter(({event}) => event.record_type === 'attachment')) {
    const assembly = assemblies.get(event.message_key);
    if (!assembly) continue;
    const objectKey = mediaObjectKey(
      assembly.event.envelope.connector_account_id,
      assembly.event.envelope.msg_id,
      event.attachment.attachment_index,
      event.attachment.mime_type,
      assembly.event.envelope.sent_at,
    );
    const stored = await store.download(objectKey, event.attachment.download_url);
    assembly.event.completed[event.attachment.attachment_index] = {
      attachment_index: event.attachment.attachment_index,
      mime_type: event.attachment.mime_type,
      media_object_key: objectKey,
      size_bytes: stored.sizeBytes,
    };
    await downloadQueue.enqueue(event.message_key, assembly.event);
    await downloadQueue.remove(name);
  }
  for (const {name, event} of assemblies.values()) {
    if (event.completed.filter(Boolean).length !== event.envelope.attachments.length) continue;
    const published = {...event.envelope, attachments: event.completed};
    await outbox.enqueue(event.message_key, published);
    await downloadQueue.remove(name);
  }
  await outbox.flush(client);
}

export async function handleMessage({message, accountId, enabledIds, sourceNames, send2meId, store, outbox, downloadQueue, client, storageFull = false}, reportActivity = true) {
  const conversationId = String(message?.threadId || '');
  const source = sourceNames.get(conversationId);
  if (!source?.source_display_name) return;
  const messageId = String(message?.data?.msgId || message?.data?.cliMsgId || '').trim();
  const senderId = String(message?.data?.uidFrom || message?.data?.senderId || '').trim();
  if (!messageId || !senderId) return;
  if (!enabledIds.has(conversationId)) {
    if (reportActivity) {
      const timestamp = Number(message?.data?.ts);
      await client.sendEvent({schema_version: 1, event_type: 'discovery', connector_account_id: accountId, ...source,
        last_activity_at: Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : observedAt()});
    }
    return;
  }
  if (source.source_type === 'my_documents' && !MY_DOCUMENTS_REALTIME_VERIFIED) return;
  let envelope = normalizeMessage(message, accountId, source, send2meId);
  if (!envelope) {
    if (reportActivity) {
      const timestamp = Number(message?.data?.ts);
      await client.sendEvent({schema_version: 1, event_type: 'discovery', connector_account_id: accountId, ...source,
        last_activity_at: Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : observedAt()});
    }
    return;
  }
  if (storageFull) envelope = {...envelope, attachments: []};
  const messageKey = `${accountId}:${envelope.conversation_id}:${envelope.msg_id}`;
  const existing = (await downloadQueue.entries()).find(({event}) => event.record_type === 'message' && event.message_key === messageKey)?.event;
  const assembly = existing || {record_type: 'message', message_key: messageKey, envelope, completed: Array(envelope.attachments.length).fill(null)};
  if (!existing) await downloadQueue.enqueue(messageKey, assembly);
  const timestamp = Number(message?.data?.ts);
  if (reportActivity) {
    await client.sendEvent({
      schema_version: 1,
      event_type: 'discovery',
      connector_account_id: accountId,
      ...source,
      last_activity_at: Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : observedAt(),
    });
  }
  for (const attachment of envelope.attachments) {
    if (assembly.completed[attachment.attachment_index]) continue;
    await downloadQueue.enqueue(`${messageKey}:${attachment.attachment_index}`, {
      record_type: 'attachment',
      message_key: messageKey,
      attachment,
    });
  }
  await processDownloadQueue({downloadQueue, store, outbox, client});
}

function replaceSet(target, values) {
  target.clear();
  for (const value of values) target.add(value);
  return target;
}

export async function refreshRuntimeState({
  accountId,
  client,
  store,
  api,
  activeEnabledIds = new Set(),
  policyVersion = 0,
  sourceSyncAckVersion = 0,
  send2meId,
}) {
  let config;
  try {
    config = await client.getConfig(accountId);
  } catch {
    return {
      enabledIds: activeEnabledIds,
      policyVersion,
      sourceSyncAckVersion,
      sources: null,
      storageFull: null,
    };
  }
  let sources;
  let sourceMap;
  let ackedPolicyVersion;
  let desiredPolicyVersion;
  let requestedSyncVersion;
  let configuredSourceSyncAckVersion;
  let protectedKeys;
  try {
    if (!config || !Array.isArray(config.sources) || !Array.isArray(config.protected_media_object_keys)) throw new Error('config is invalid');
    sources = config.sources;
    ackedPolicyVersion = Number(config.policy_acked_version || 0);
    desiredPolicyVersion = Number(config.policy_version || 0);
    requestedSyncVersion = Number(config.source_sync_request_version || 0);
    configuredSourceSyncAckVersion = Number(config.source_sync_acked_version || 0);
    if (![ackedPolicyVersion, desiredPolicyVersion, requestedSyncVersion, configuredSourceSyncAckVersion].every(Number.isSafeInteger)) throw new Error('config version is invalid');
    protectedKeys = new Set(config.protected_media_object_keys.map((key) => String(key)));
    sourceMap = new Map(sources.map((source) => [String(source.conversation_id), sourceDescriptor({
        conversationId: source.conversation_id,
        sourceType: source.source_type || (source.conversation_type === 'group' ? 'group' : 'friend'),
        displayName: source.display_name,
        lastActivityAt: source.last_activity_at,
      })]));
  } catch {
    return {enabledIds: activeEnabledIds, policyVersion, sourceSyncAckVersion, sources: null, sourceMap: null, storageFull: null};
  }
  const ackActiveIds = sources
    .filter((source) => source.acked_enabled === true)
    .map((source) => String(source.conversation_id));
  replaceSet(activeEnabledIds, ackActiveIds);
  policyVersion = ackedPolicyVersion;

  if (desiredPolicyVersion > ackedPolicyVersion) {
    const pendingChangedIds = new Set(sources
      .filter((source) => Boolean(source.desired_enabled) !== Boolean(source.acked_enabled))
      .map((source) => String(source.conversation_id)));
    replaceSet(activeEnabledIds, [...activeEnabledIds].filter((id) => !pendingChangedIds.has(id)));
    const stagedEnabledIds = new Set(sources
      .filter((source) => Boolean(source.desired_enabled))
      .map((source) => String(source.conversation_id)));
    try {
      await client.ackPolicy(accountId, desiredPolicyVersion);
      replaceSet(activeEnabledIds, stagedEnabledIds);
      policyVersion = desiredPolicyVersion;
    } catch {
      // Changed sources stay fail-closed until a later exact ACK succeeds.
    }
  }

  sourceSyncAckVersion = configuredSourceSyncAckVersion;
  let discoveryComplete = false;
  if (api && requestedSyncVersion > sourceSyncAckVersion) {
    try {
      sourceMap = await syncSources({api, accountId, client, send2meId});
      discoveryComplete = true;
    } catch {
      // A later config poll retries the same unacknowledged request.
    }
    if (discoveryComplete) {
      try {
        await client.ackSourceSync(accountId, requestedSyncVersion);
        sourceSyncAckVersion = requestedSyncVersion;
      } catch {
        // Keep discovered metadata; only ACK advancement waits for HTTP success.
      }
    }
  }
  const storage = await store.prune({protectedKeys});
  return {
    enabledIds: activeEnabledIds,
    policyVersion,
    sourceSyncAckVersion,
    sources,
    sourceMap,
    storageFull: Boolean(storage.storageFull),
  };
}

export async function installSourceSyncTriggers({listener, reconcile, sourceReconcileMs, runInitial = true, setTimer = setInterval}) {
  const trigger = () => { void reconcile().catch(() => {}); };
  listener.on('connected', trigger);
  listener.on('friend_event', trigger);
  listener.on('group_event', trigger);
  const timer = setTimer(trigger, sourceReconcileMs);
  if (runInitial) await reconcile().catch(() => {});
  return timer;
}

export async function handleQrLoginEvent({event, eventTypes, stateEvent, rememberSession}) {
  if (event.type === eventTypes.QRCodeGenerated) {
    try {
      await event.actions.saveToFile();
      const image = String(event.data.image || '').replace(/^data:image\/png;base64,/, '');
      await stateEvent('login_required', {qr_image: `data:image/png;base64,${image}`});
    } catch (error) {
      event.actions.abort();
      throw error;
    }
  } else if (event.type === eventTypes.QRCodeExpired) {
    event.actions.retry();
    await stateEvent('login_required', {qr_image: ''});
  } else if (event.type === eventTypes.QRCodeDeclined) {
    event.actions.retry();
    await stateEvent('login_required', {qr_image: ''});
  } else if (event.type === eventTypes.GotLoginInfo) {
    rememberSession(event.data);
  }
}

export async function publishConnectedState({api, stateEvent, qrLoginSuccess}) {
  const ownId = String(api.getOwnId() || '');
  if (!ownId) throw new Error('Zalo account id is unavailable');
  await stateEvent('disconnected', {qr_login_success: qrLoginSuccess, bound_zalo_id: ownId});
}

export async function finalizeQrLogin({api, stateEvent, session, saveSession}) {
  await publishConnectedState({api, stateEvent, qrLoginSuccess: true});
  await saveSession(session);
}

export async function verifyRestoredSession({api, stateEvent, deleteSession}) {
  try {
    await publishConnectedState({api, stateEvent, qrLoginSuccess: false});
  } catch (error) {
    await deleteSession();
    await stateEvent('login_required');
    throw error;
  }
}

export function isParentAlive(parentPid, kill = process.kill) {
  if (!parentPid) return true;
  try {
    kill(Number(parentPid), 0);
    return true;
  } catch (error) {
    return error.code !== 'ESRCH';
  }
}

export function startParentWatch(parentPid, {
  isAlive = (pid) => isParentAlive(pid),
  onDead = () => process.exit(0),
  setTimer = setInterval,
} = {}) {
  if (!parentPid) return null;
  return setTimer(() => { if (!isAlive(parentPid)) onDead(); }, 2000);
}

export function listenerHeartbeatState(listenerConnected) {
  return listenerConnected ? 'connected' : 'disconnected';
}

export function shouldRestoreSession(session, env) {
  return Boolean(session) && env.ZALO_CONNECTOR_FORCE_QR !== '1';
}

async function readJson(filename) {
  try {
    return JSON.parse(await readFile(filename, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

async function writeJson(filename, value) {
  await mkdir(path.dirname(filename), {recursive: true});
  const temporary = `${filename}.${process.pid}.tmp`;
  await writeFile(temporary, JSON.stringify(value), {encoding: 'utf8', mode: 0o600});
  await rename(temporary, filename);
}

async function nextGeneration(filename) {
  const current = Number((await readJson(filename))?.generation || 0);
  const generation = current + 1;
  await writeJson(filename, {generation});
  return generation;
}

export async function startConnector({Zalo, LoginQRCallbackEventType, env = process.env, fetchImpl = fetch}) {
  const parentWatch = startParentWatch(env.ZALO_CONNECTOR_PARENT_PID);
  const settings = readSettings(env);
  await mkdir(settings.stateRoot, {recursive: true});
  const accountFile = path.join(settings.stateRoot, 'account.json');
  const sessionFile = path.join(settings.stateRoot, 'session.json');
  const generationFile = path.join(settings.stateRoot, 'generation.json');
  const client = new WebhookClient({
    baseUrl: settings.backendUrl,
    secret: settings.webhookSecret,
    bootstrapSecret: settings.bootstrapSecret,
    fetchImpl,
  });
  let account = await readJson(accountFile);
  if (!account?.connector_account_id) {
    account = await client.onboard();
    await writeJson(accountFile, account);
  }
  const accountId = String(account.connector_account_id);
  const generation = await nextGeneration(generationFile);
  let storageFull = false;
  const stateEvent = (state, extra = {}) => client.sendEvent({
    schema_version: 1,
    event_type: 'state',
    connector_account_id: accountId,
    state,
    listener_generation: generation,
    observed_at: observedAt(),
    storage_full: storageFull,
    ...extra,
  });

  const zalo = createZaloClient(Zalo);
  let api = null;
  const savedSession = await readJson(sessionFile);
  if (savedSession && !shouldRestoreSession(savedSession, env)) {
    await unlink(sessionFile).catch(() => {});
  }
  if (shouldRestoreSession(savedSession, env)) {
    try {
      api = await zalo.login(savedSession);
    } catch {
      await unlink(sessionFile).catch(() => {});
    }
  }
  if (!api) {
    await stateEvent('login_required');
    let pendingSession = null;
    api = await zalo.loginQR({qrPath: path.join(settings.stateRoot, 'login-qr.png')}, (event) => {
      void handleQrLoginEvent({
        event,
        eventTypes: LoginQRCallbackEventType,
        stateEvent,
        rememberSession: (session) => { pendingSession = session; },
      }).catch(() => {});
    });
    if (!api) throw new Error('Zalo QR login did not complete');
    if (!pendingSession) throw new Error('Zalo QR session is unavailable');
    await finalizeQrLogin({
      api,
      stateEvent,
      session: pendingSession,
      saveSession: (session) => writeJson(sessionFile, session),
    });
  } else {
    await verifyRestoredSession({
      api,
      stateEvent,
      deleteSession: () => unlink(sessionFile).catch(() => {}),
    });
  }

  const store = new MediaStore({root: settings.storageRoot, quotaBytes: settings.quotaBytes, retentionHours: settings.retentionHours});
  const outbox = new FileOutbox(path.join(settings.stateRoot, 'webhook-outbox'));
  const downloadQueue = new FileOutbox(path.join(settings.stateRoot, 'download-queue'));
  const unknownQueue = new FileOutbox(path.join(settings.stateRoot, 'unknown-source-queue'));
  const send2meId = api.getContext?.()?.loginInfo?.send2me_id;
  let sourceNames = new Map();
  let enabledIds = new Set();
  let policyVersion = 0;
  let sourceSyncAckVersion = 0;
  let listenerConnected = false;
  let closed = false;
  // ponytail: global connector queue; use per-account queues only if throughput matters.
  let serial = Promise.resolve();
  const enqueueOperation = (fn) => {
    if (closed) return Promise.reject(new Error('connector is closed'));
    const operation = serial.then(() => {
      if (!closed) return fn();
    });
    serial = operation.catch(() => {});
    return operation;
  };

  const reconcileSources = async () => {
    const discovered = await syncSources({api, accountId, client, send2meId});
    sourceNames = discovered;
  };

  const handleKnownMessage = (message, reportActivity) => handleMessage({
    message,
    accountId,
    enabledIds,
    sourceNames,
    send2meId,
    store,
    outbox,
    downloadQueue,
    client,
    storageFull,
  }, reportActivity);
  const retryUnknownSources = () => processUnknownSourceQueue({
    api,
    accountId,
    send2meId,
    unknownQueue,
    client,
    refresh: () => refresh(false),
    enabledIds,
    sourceNames,
    handleKnownMessage,
    reportError: (errorCode) => stateEvent(listenerHeartbeatState(listenerConnected), {error_code: errorCode}),
  });
  const refresh = async (retryUnknown = true) => {
    const previousStorageFull = storageFull;
    const runtime = await refreshRuntimeState({
      accountId,
      client,
      store,
      api,
      activeEnabledIds: enabledIds,
      policyVersion,
      sourceSyncAckVersion,
      send2meId,
    });
    enabledIds = runtime.enabledIds;
    policyVersion = runtime.policyVersion;
    sourceSyncAckVersion = runtime.sourceSyncAckVersion;
    if (runtime.sourceMap) sourceNames = runtime.sourceMap;
    if (runtime.storageFull !== null) storageFull = runtime.storageFull;
    if (!storageFull) {
      try {
        await processDownloadQueue({downloadQueue, store, outbox, client});
      } catch (error) {
        if (!/quota/i.test(String(error?.message || ''))) throw error;
        storageFull = true;
      }
    }
    if (previousStorageFull !== storageFull) await stateEvent(listenerHeartbeatState(listenerConnected));
    await outbox.flush(client);
    if (retryUnknown) await retryUnknownSources();
    return runtime;
  };
  const sourceReconcile = await installSourceSyncTriggers({
    listener: api.listener,
    reconcile: () => enqueueOperation(reconcileSources),
    sourceReconcileMs: settings.sourceReconcileMs,
    runInitial: false,
  });

  api.listener.on('message', (message) => {
    void enqueueOperation(async () => {
      const conversationId = String(message?.threadId || '').trim();
      const messageId = String(message?.data?.msgId || message?.data?.cliMsgId || '').trim();
      const senderId = String(message?.data?.uidFrom || message?.data?.senderId || '').trim();
      if (!conversationId || !messageId || !senderId) return;
      if (sourceNames.has(conversationId)) {
        await handleKnownMessage(message);
      } else {
        await unknownQueue.enqueue(`${accountId}:${conversationId}:${messageId}`, {
          record_type: 'unknown_source',
          message,
          attempts: 0,
        });
      }
      await retryUnknownSources();
    })
      .catch((error) => {
        if (/quota/i.test(String(error?.message || ''))) {
          storageFull = true;
          void stateEvent(listenerHeartbeatState(listenerConnected)).catch(() => {});
        }
      });
  });
  api.listener.on('connected', () => {
    listenerConnected = true;
    void stateEvent('connected').catch(() => {});
  });
  api.listener.on('disconnected', () => {
    listenerConnected = false;
    void stateEvent('disconnected').catch(() => {});
  });
  api.listener.on('error', () => {
    listenerConnected = false;
    void stateEvent('disconnected').catch(() => {});
  });
  const initialRuntime = await refresh();
  if (initialRuntime.sourceMap === undefined) await reconcileSources().catch(() => {});
  api.listener.start({retryOnClose: true});

  const heartbeat = setInterval(() => {
    void stateEvent(listenerHeartbeatState(listenerConnected)).catch(() => {});
  }, settings.heartbeatMs);
  const poll = setInterval(() => { void enqueueOperation(refresh).catch(() => {}); }, settings.configPollMs);
  const close = () => {
    closed = true;
    clearInterval(heartbeat);
    clearInterval(poll);
    clearInterval(sourceReconcile);
    if (parentWatch) clearInterval(parentWatch);
    api.listener.stop();
  };
  return {accountId, close};
}
