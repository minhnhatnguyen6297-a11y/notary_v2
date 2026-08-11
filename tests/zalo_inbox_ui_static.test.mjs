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

test('source policy settings expose consent, search, refresh, and separate source sections', async () => {
  const template = await readFile(new URL('../frontend/templates/zalo_inbox.html', import.meta.url), 'utf8');
  for (const id of [
    'consent-panel', 'confirm-intake-consent', 'source-search', 'refresh-sources',
    'source-refresh-status', 'policy-status', 'source-list', 'stranger-source-list',
  ]) assert.match(template, new RegExp(`id="${id}"`));
  assert.match(template, /Friends, groups và My Documents mặc định BẬT/);
  assert.match(template, /Strangers mặc định TẮT/);
  assert.match(template, /Làm mới nguồn/);
  assert.match(template, /aria-label="Tìm nguồn theo tên"/);
});

test('source policy actions use account-scoped APIs and refresh public state', () => {
  assert.match(source, /api\/connectors\/\$\{encodeURIComponent\(state\.connector\.id\)\}\/consent/);
  assert.match(source, /api\/connectors\/\$\{encodeURIComponent\(state\.connector\.id\)\}\/sources\/refresh/);
  assert.match(source, /method: 'POST'/);
  assert.match(source, /await refreshState\(\)/);
});

test('source rendering preserves backend partitions and order while filtering only by display name', () => {
  const renderBody = source.match(/function renderSources\(\) \{([\s\S]*?)\n  \}/)?.[1] || '';
  assert.match(renderBody, /state\.sources/);
  assert.match(renderBody, /state\.stranger_sources/);
  assert.match(renderBody, /display_name\.toLocaleLowerCase\('vi-VN'\)/);
  assert.doesNotMatch(renderBody, /\.sort\(/);
  assert.doesNotMatch(renderBody, /conversation_id/);
});

test('source rows show type, activity, and fail closed while policy is pending', () => {
  assert.match(source, /friend: 'Bạn bè'/);
  assert.match(source, /group: 'Nhóm'/);
  assert.match(source, /my_documents: 'My Documents'/);
  assert.match(source, /stranger: 'Người lạ'/);
  assert.match(source, /source\.last_activity_at/);
  assert.match(source, /source\.pending \? 'disabled' : ''/);
  assert.match(source, /source\.pending \? '[^']*Đang áp dụng/);
  assert.match(source, /desired_enabled/);
});

test('consent and refresh progress use public state without optimistic readiness', () => {
  assert.match(source, /state\.consent_required/);
  assert.match(source, /Cần xác nhận lại/);
  assert.match(source, /state\.policy_pending/);
  assert.match(source, /Đang áp dụng/);
  assert.match(source, /sourceRefreshPending/);
  assert.match(source, /state\.source_sync/);
  assert.match(source, /sourceSync\.status === 'pending'/);
  assert.match(source, /sourceSync\.status === 'error'/);
  assert.doesNotMatch(source, /source\.pending = false/);
});

test('re-consent explains legacy inventory reset and risky actions start disabled', async () => {
  const template = await readFile(new URL('../frontend/templates/zalo_inbox.html', import.meta.url), 'utf8');
  assert.match(template, /toàn bộ nguồn hiện có chưa lưu lựa chọn rõ ràng/);
  assert.match(template, /id="start-data-sync"[^>]*disabled/);
  assert.match(template, /id="confirm-intake-consent"[^>]*disabled/);
  assert.match(template, /id="refresh-sources"[^>]*disabled/);
  const consentHandler = source.match(/\$\('confirm-intake-consent'\)\.addEventListener\('click',[\s\S]*?\n  \}\);/)?.[0] || '';
  assert.match(consentHandler, /await refreshState\(\)/);
  assert.doesNotMatch(consentHandler, /button\.disabled = false/);
});

test('data sync panel has one accessible action and permanent trust warnings', async () => {
  const template = await readFile(new URL('../frontend/templates/zalo_inbox.html', import.meta.url), 'utf8');
  assert.equal((template.match(/id="start-data-sync"/g) || []).length, 1);
  for (const id of ['data-sync-status', 'data-sync-counters', 'data-sync-window', 'data-sync-error', 'gap-warning']) {
    assert.match(template, new RegExp(`id="${id}"`));
  }
  assert.match(template, />Đồng bộ dữ liệu</);
  assert.match(template, /best-effort/);
  assert.match(template, /có thể thiếu/);
});

test('data sync action uses account-scoped POST and refreshes existing state', () => {
  assert.match(source, /api\/connectors\/\$\{encodeURIComponent\(state\.connector\.id\)\}\/data-sync/);
  assert.match(source, /method: 'POST'/);
  assert.match(source, /await refreshState\(\)/);
  assert.equal((source.match(/setInterval\(/g) || []).length, 1);
  assert.doesNotMatch(source, /EventSource|WebSocket/);
});

test('data sync is disabled by every public-state gate', () => {
  assert.match(source, /state\.consent_required/);
  assert.match(source, /state\.connector\.state !== 'connected'/);
  assert.match(source, /state\.policy_pending/);
  assert.match(source, /state\.data_sync\?\.status === 'running'/);
});

test('data sync renders only three statuses, five counters, window, and sanitized error code', () => {
  assert.match(source, /running: 'Đang đồng bộ'/);
  assert.match(source, /completed_best_effort: 'Hoàn tất best-effort'/);
  assert.match(source, /error: 'Lỗi'/);
  for (const key of ['received', 'duplicates', 'imported_text', 'imported_media', 'media_download_failures']) {
    assert.match(source, new RegExp(`${key}:`));
  }
  assert.match(source, /sync\.cutoff_at/);
  assert.match(source, /sync\.deadline_at/);
  assert.match(source, /sync\.error_code/);
  assert.doesNotMatch(source, /sync\.error_message|sync\.run_id|source_ids/);
});

test('gap warning is rendered from public state and never cleared as a sync side effect', () => {
  assert.match(source, /state\.gap_started_at/);
  assert.match(source, /Có thể thiếu event từ/);
  const clickBody = source.match(/\$\('start-data-sync'\)\.addEventListener\('click',[\s\S]*?\n  \}\);/)?.[0] || '';
  assert.doesNotMatch(clickBody, /gap-warning|gap_started_at/);
});

test('source rendering cannot mutate media selection and media remains in backend order', () => {
  const renderSourcesBody = source.match(/function renderSources\(\) \{([\s\S]*?)\n  \}/)?.[1] || '';
  const renderMediaBody = source.match(/function renderMedia\(\) \{([\s\S]*?)\n  \}/)?.[1] || '';
  assert.doesNotMatch(renderSourcesBody, /selectedMedia|renderMedia/);
  assert.match(renderMediaBody, /state\.media\.forEach/);
  assert.doesNotMatch(renderMediaBody, /\.sort\(|\.reverse\(/);
});
