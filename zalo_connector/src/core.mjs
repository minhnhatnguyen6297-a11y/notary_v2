import {createHash, createHmac} from 'node:crypto';
import {mkdir, open, readdir, readFile, rename, stat, unlink, writeFile} from 'node:fs/promises';
import path from 'node:path';

export function signBody(body, timestamp, secret) {
  if (!secret) throw new Error('webhook secret is required');
  return createHmac('sha256', secret).update(`${timestamp}.${body}`).digest('hex');
}

function exactAck(event, response) {
  if (response?.ack !== true) return false;
  if (event.event_type === 'policy_ack') return response.policy_version === event.policy_version;
  if (event.event_type === 'source_sync_ack') return response.source_sync_request_version === event.source_sync_request_version;
  if (event.event_type !== 'message') return true;
  const components = response.components;
  const textStatuses = event.raw_text == null ? new Set(['absent']) : new Set(['imported', 'duplicate', 'ignored']);
  const mediaStatuses = new Set(['imported', 'duplicate', 'ignored']);
  if (!components || !textStatuses.has(components.text) || !Array.isArray(components.media)) return false;
  const expected = (event.attachments || []).map(({attachment_index}) => attachment_index);
  return components.media.length === expected.length && components.media.every((item, index) => (
    item?.attachment_index === expected[index] && mediaStatuses.has(item.status)
  ));
}

function requireExactAck(event, response) {
  if (!exactAck(event, response)) throw new Error('backend acknowledgement did not match event');
  return response;
}

export class WebhookClient {
  constructor({baseUrl, secret, bootstrapSecret, fetchImpl = fetch, now = Date.now}) {
    this.baseUrl = String(baseUrl || '').replace(/\/$/, '');
    this.secret = secret;
    this.bootstrapSecret = bootstrapSecret;
    this.fetch = fetchImpl;
    this.now = now;
  }

  async onboard() {
    const response = await this.fetch(`${this.baseUrl}/zalo-inbox/api/connectors/onboard`, {
      method: 'POST',
      headers: {'x-zalo-bootstrap': this.bootstrapSecret},
    });
    return this.#json(response);
  }

  async sendEvent(event, signal) {
    const body = JSON.stringify(event);
    const timestamp = String(Math.floor(this.now() / 1000));
    const response = await this.fetch(`${this.baseUrl}/zalo-inbox/api/webhook`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-zalo-timestamp': timestamp,
        'x-zalo-signature': signBody(body, timestamp, this.secret),
      },
      body,
      ...(signal ? {signal} : {}),
    });
    return requireExactAck(event, await this.#json(response));
  }

  ackPolicy(accountId, policyVersion) {
    return this.sendEvent({
      schema_version: 1,
      event_type: 'policy_ack',
      connector_account_id: accountId,
      policy_version: policyVersion,
    });
  }

  ackSourceSync(accountId, sourceSyncRequestVersion) {
    return this.sendEvent({
      schema_version: 1,
      event_type: 'source_sync_ack',
      connector_account_id: accountId,
      source_sync_request_version: sourceSyncRequestVersion,
    });
  }

  async getConfig(accountId) {
    const timestamp = String(Math.floor(this.now() / 1000));
    const response = await this.fetch(`${this.baseUrl}/zalo-inbox/api/connectors/${encodeURIComponent(accountId)}/config`, {
      headers: {
        'x-zalo-timestamp': timestamp,
        'x-zalo-signature': signBody('', timestamp, this.secret),
      },
    });
    return this.#json(response);
  }

  async getNextCommand(accountId) {
    const timestamp = String(Math.floor(this.now() / 1000));
    const accountKeyHex = createHmac('sha256', this.secret).update(String(accountId)).digest('hex');
    const response = await this.fetch(`${this.baseUrl}/zalo-inbox/api/connectors/${encodeURIComponent(accountId)}/commands/next`, {
      headers: {
        'x-zalo-timestamp': timestamp,
        'x-zalo-signature': signBody('', timestamp, accountKeyHex),
      },
    });
    if (response.status === 204) return null;
    const command = await this.#json(response);
    if (
      command?.command_type !== 'data_sync'
      || !String(command.run_id || '').trim()
      || typeof command.cutoff_at !== 'string' || Number.isNaN(Date.parse(command.cutoff_at))
      || typeof command.deadline_at !== 'string' || Number.isNaN(Date.parse(command.deadline_at))
      || !Array.isArray(command.source_ids)
    ) throw new Error('backend command is invalid');
    return command;
  }

  async #json(response) {
    if (!response.ok) throw new Error(`backend returned HTTP ${response.status}`);
    return response.json();
  }
}

function attachmentCandidates(content) {
  if (!content || typeof content !== 'object') return [];
  const candidates = [content];
  if (typeof content.params === 'string') {
    try {
      const parsed = JSON.parse(content.params);
      if (parsed && typeof parsed === 'object') candidates.push(parsed);
    } catch {
      // zca-js payloads are not consistent across attachment types.
    }
  }
  return candidates;
}

function supportedAttachment(content) {
  for (const candidate of attachmentCandidates(content)) {
    const url = candidate.hdUrl || candidate.href || candidate.downloadUrl || candidate.fileUrl || candidate.url;
    if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) continue;
    const title = String(candidate.title || content.title || 'attachment');
    const declared = String(candidate.mime_type || candidate.mimeType || candidate.type || content.type || '').toLowerCase();
    const pathname = new URL(url).pathname.toLowerCase();
    let mimeType = declared;
    if (!['image/jpeg', 'image/png', 'application/pdf'].includes(mimeType)) {
      if (/\.pdf$/i.test(title) || pathname.endsWith('.pdf')) mimeType = 'application/pdf';
      else if (/\.png$/i.test(title) || pathname.endsWith('.png')) mimeType = 'image/png';
      else if (/\.(jpe?g)$/i.test(title) || /\.(jpe?g)$/i.test(pathname) || declared.startsWith('image') || candidate.hdUrl) mimeType = 'image/jpeg';
    }
    if (['image/jpeg', 'image/png', 'application/pdf'].includes(mimeType)) return {url, mimeType, title};
  }
  return null;
}

export function normalizeMessage(message, accountId, source, send2meId) {
  const threadId = String(message?.threadId || '');
  if (!message || (message.isSelf && threadId !== String(send2meId || ''))) return null;
  const content = message.data?.content;
  const candidates = Array.isArray(message.data?.attachments)
    ? message.data.attachments
    : (content && typeof content === 'object' ? [content] : []);
  const attachments = candidates
    .map(supportedAttachment)
    .filter(Boolean)
    .map((attachment, attachmentIndex) => ({
      attachment_index: attachmentIndex,
      mime_type: attachment.mimeType,
      download_url: attachment.url,
      original_filename: attachment.title,
    }));
  const rawText = typeof content === 'string' && content.trim() ? content : null;
  const messageId = String(message.data?.msgId || message.data?.cliMsgId || '').trim();
  const senderId = String(message.data?.uidFrom || message.data?.senderId || '').trim();
  if (!messageId || !senderId || (rawText === null && attachments.length === 0)) return null;
  const timestamp = Number(message.data?.ts);
  const sentAt = Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : new Date().toISOString();
  return {
    schema_version: 1,
    event_type: 'message',
    connector_account_id: accountId,
    conversation_id: threadId,
    conversation_type: source.source_type === 'group' ? 'group' : 'user',
    source_type: source.source_type,
    source_display_name: source.source_display_name,
    msg_id: messageId,
    sender_id: senderId,
    sent_at: sentAt,
    raw_text: rawText,
    attachments,
  };
}

function safeKey(key) {
  const normalized = String(key).replaceAll('\\', '/');
  const parts = normalized.split('/');
  if (!normalized || normalized.startsWith('/') || parts.some((part) => !part || part === '.' || part === '..')) {
    throw new Error('invalid storage key');
  }
  return {normalized, parts};
}

async function walkFiles(root, directory = root) {
  let entries;
  try {
    entries = await readdir(directory, {withFileTypes: true});
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
  const files = [];
  for (const entry of entries) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walkFiles(root, target));
    else if (entry.isFile() && !entry.name.endsWith('.tmp')) files.push(target);
  }
  return files;
}

export class FileOutbox {
  constructor(root) {
    this.root = path.resolve(root);
  }

  async enqueue(eventId, event) {
    await mkdir(this.root, {recursive: true});
    const name = `${createHash('sha256').update(String(eventId)).digest('hex')}.json`;
    const target = path.join(this.root, name);
    const temporary = `${target}.${process.pid}.tmp`;
    await writeFile(temporary, JSON.stringify(event), {encoding: 'utf8', mode: 0o600});
    await rename(temporary, target);
    return name;
  }

  async pending() {
    await mkdir(this.root, {recursive: true});
    return (await readdir(this.root)).filter((name) => name.endsWith('.json')).sort();
  }

  async entries() {
    return Promise.all((await this.pending()).map(async (name) => ({
      name,
      event: JSON.parse(await readFile(path.join(this.root, name), 'utf8')),
    })));
  }

  async remove(name) {
    if (path.basename(name) !== name || !name.endsWith('.json')) throw new Error('invalid outbox entry');
    await unlink(path.join(this.root, name));
  }

  async replace(name, event) {
    if (path.basename(name) !== name || !name.endsWith('.json')) throw new Error('invalid outbox entry');
    const target = path.join(this.root, name);
    const temporary = `${target}.${process.pid}.tmp`;
    await writeFile(temporary, JSON.stringify(event), {encoding: 'utf8', mode: 0o600});
    await rename(temporary, target);
  }

  async flush(client) {
    for (const {name, event} of await this.entries()) {
      requireExactAck(event, await client.sendEvent(event));
      await this.remove(name);
    }
  }
}

export function mediaObjectKey(accountId, messageId, attachmentIndex, mimeType, sentAt = new Date()) {
  if (!/^[A-Za-z0-9_-]+$/.test(accountId)) throw new Error('invalid connector account id');
  const extension = {'image/jpeg': 'jpg', 'image/png': 'png', 'application/pdf': 'pdf'}[mimeType];
  if (!extension) throw new Error('unsupported media type');
  const date = new Date(sentAt);
  const day = Number.isNaN(date.getTime()) ? 'unknown-date' : date.toISOString().slice(0, 10);
  const digest = createHash('sha256').update(`${messageId}:${attachmentIndex}`).digest('hex');
  return `${accountId}/${day}/${digest}.${extension}`;
}

export class MediaStore {
  constructor({root, quotaBytes, retentionHours}) {
    this.root = path.resolve(root);
    this.quotaBytes = Number(quotaBytes);
    this.retentionMs = Number(retentionHours) * 60 * 60 * 1000;
    if (!Number.isSafeInteger(this.quotaBytes) || this.quotaBytes <= 0 || !Number.isFinite(this.retentionMs) || this.retentionMs <= 0) {
      throw new Error('positive storage quota and retention are required');
    }
  }

  #target(key) {
    const {normalized, parts} = safeKey(key);
    const target = path.resolve(this.root, ...parts);
    if (target !== this.root && !target.startsWith(`${this.root}${path.sep}`)) throw new Error('storage path escapes root');
    return {normalized, target};
  }

  async #usage(excluding = null) {
    let total = 0;
    for (const file of await walkFiles(this.root)) {
      if (file !== excluding) total += (await stat(file)).size;
    }
    return total;
  }

  async put(key, data) {
    const buffer = Buffer.from(data);
    const {target} = this.#target(key);
    if (await this.#usage(target) + buffer.length > this.quotaBytes) throw new Error('connector storage quota exceeded');
    await mkdir(path.dirname(target), {recursive: true});
    const temporary = `${target}.${process.pid}.tmp`;
    await writeFile(temporary, buffer, {mode: 0o600});
    await rename(temporary, target);
    return target;
  }

  async download(key, url, signal, fetchImpl = fetch) {
    const {target} = this.#target(key);
    const response = await fetchImpl(url, signal ? {signal} : undefined);
    signal?.throwIfAborted();
    if (!response.ok || !response.body) throw new Error(`attachment download returned HTTP ${response.status}`);
    const baseUsage = await this.#usage(target);
    const announced = Number(response.headers.get('content-length'));
    if (Number.isFinite(announced) && baseUsage + announced > this.quotaBytes) throw new Error('connector storage quota exceeded');
    await mkdir(path.dirname(target), {recursive: true});
    const temporary = `${target}.${process.pid}.tmp`;
    const handle = await open(temporary, 'w', 0o600);
    let written = 0;
    try {
      for await (const chunk of response.body) {
        signal?.throwIfAborted();
        written += chunk.length;
        if (baseUsage + written > this.quotaBytes) throw new Error('connector storage quota exceeded');
        await handle.write(chunk);
      }
      signal?.throwIfAborted();
      await handle.close();
      await rename(temporary, target);
      return {path: target, sizeBytes: written};
    } catch (error) {
      await handle.close().catch(() => {});
      await unlink(temporary).catch(() => {});
      throw error;
    }
  }

  async prune({protectedKeys, now = new Date()}) {
    const protectedSet = new Set([...protectedKeys].map((key) => safeKey(key).normalized));
    const candidates = [];
    for (const file of await walkFiles(this.root)) {
      const info = await stat(file);
      const key = path.relative(this.root, file).split(path.sep).join('/');
      if (!protectedSet.has(key)) candidates.push({file, key, info});
    }
    const cutoff = now.getTime() - this.retentionMs;
    for (const candidate of candidates.filter(({info}) => info.mtimeMs < cutoff)) await unlink(candidate.file).catch(() => {});

    let usage = await this.#usage();
    if (usage <= this.quotaBytes) return {usageBytes: usage, storageFull: false};
    for (const candidate of candidates.sort((a, b) => a.info.mtimeMs - b.info.mtimeMs)) {
      try {
        await unlink(candidate.file);
        usage -= candidate.info.size;
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
      if (usage <= this.quotaBytes) return {usageBytes: usage, storageFull: false};
    }
    return {usageBytes: usage, storageFull: true};
  }
}
