import {mkdir, readFile, rename, unlink, writeFile} from 'node:fs/promises';
import path from 'node:path';

import {FileOutbox, MediaStore, WebhookClient, attachmentEvents, mediaObjectKey} from './core.mjs';

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
  };
}

const observedAt = () => new Date().toISOString();

export function createZaloClient(Zalo) {
  return new Zalo({logging: false});
}

export async function discoverSources(api, accountId, client) {
  const sourceNames = new Map();
  const friends = await api.getAllFriends();
  for (const friend of friends) {
    const id = String(friend.userId);
    const name = String(friend.displayName || friend.zaloName || id);
    sourceNames.set(id, name);
    await client.sendEvent({
      schema_version: 1,
      event_type: 'discovery',
      connector_account_id: accountId,
      conversation_id: id,
      conversation_type: 'user',
      source_display_name: name,
    });
  }
  const groups = await api.getAllGroups();
  const groupIds = Object.keys(groups.gridVerMap || {});
  if (groupIds.length) {
    const details = await api.getGroupInfo(groupIds);
    for (const id of groupIds) {
      const name = String(details.gridInfoMap?.[id]?.name || id);
      sourceNames.set(id, name);
      await client.sendEvent({
        schema_version: 1,
        event_type: 'discovery',
        connector_account_id: accountId,
        conversation_id: id,
        conversation_type: 'group',
        source_display_name: name,
      });
    }
  }
  return sourceNames;
}

export async function processDownloadQueue({downloadQueue, store, outbox, client}) {
  for (const {name, event} of await downloadQueue.entries()) {
    const objectKey = mediaObjectKey(
      event.connector_account_id,
      event.msg_id,
      event.attachment_index,
      event.mime_type,
      event.sent_at,
    );
    const stored = await store.download(objectKey, event.download_url);
    const published = {...event, media_object_key: objectKey, size_bytes: stored.sizeBytes};
    delete published.download_url;
    delete published.original_filename;
    await outbox.enqueue(`${event.connector_account_id}:${event.conversation_id}:${event.msg_id}:${event.attachment_index}`, published);
    await downloadQueue.remove(name);
  }
  await outbox.flush(client);
}

export async function handleMessage({message, accountId, enabledIds, sourceNames, store, outbox, downloadQueue, client}) {
  const sourceName = sourceNames.get(String(message.threadId));
  if (!sourceName) return;
  for (const event of attachmentEvents(message, enabledIds, accountId, sourceName)) {
    const eventId = `${accountId}:${event.conversation_id}:${event.msg_id}:${event.attachment_index}`;
    await downloadQueue.enqueue(eventId, event);
  }
  await processDownloadQueue({downloadQueue, store, outbox, client});
}

export async function refreshRuntimeState({accountId, client, store}) {
  const config = await client.getConfig(accountId);
  const storage = await store.prune({protectedKeys: new Set(config.protected_media_object_keys || [])});
  return {
    enabledIds: new Set((config.sources || []).filter((source) => source.enabled).map((source) => String(source.conversation_id))),
    sources: config.sources || [],
    storageFull: Boolean(storage.storageFull),
  };
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

  const sourceNames = await discoverSources(api, accountId, client);
  const store = new MediaStore({root: settings.storageRoot, quotaBytes: settings.quotaBytes, retentionHours: settings.retentionHours});
  const outbox = new FileOutbox(path.join(settings.stateRoot, 'webhook-outbox'));
  const downloadQueue = new FileOutbox(path.join(settings.stateRoot, 'download-queue'));
  let enabledIds = new Set();
  let listenerConnected = false;
  let serial = Promise.resolve();

  const refresh = async () => {
    const previousStorageFull = storageFull;
    const runtime = await refreshRuntimeState({accountId, client, store});
    enabledIds = runtime.enabledIds;
    for (const source of runtime.sources) sourceNames.set(String(source.conversation_id), String(source.display_name || sourceNames.get(String(source.conversation_id)) || ''));
    storageFull = runtime.storageFull;
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
  };
  await refresh();

  api.listener.on('message', (message) => {
    if (storageFull) return;
    serial = serial
      .then(() => handleMessage({message, accountId, enabledIds, sourceNames, store, outbox, downloadQueue, client}))
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
  api.listener.start({retryOnClose: true});

  const heartbeat = setInterval(() => {
    void stateEvent(listenerHeartbeatState(listenerConnected)).catch(() => {});
  }, settings.heartbeatMs);
  const poll = setInterval(() => { serial = serial.then(refresh).catch(() => {}); }, settings.configPollMs);
  const close = () => {
    clearInterval(heartbeat);
    clearInterval(poll);
    if (parentWatch) clearInterval(parentWatch);
    api.listener.stop();
  };
  return {accountId, close};
}
