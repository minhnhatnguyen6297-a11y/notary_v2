(() => {
  const root = document.getElementById('zalo-inbox');
  if (!root) return;

  const initialBatchId = root.dataset.batchId || null;
  let batchId = initialBatchId;
  let state = null;
  let batch = null;
  let loginRequested = false;
  const selectedMedia = new Set();

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[char]));
  const label = (name) => ({pdf: 'PDF', json: 'JSON', excel: 'Excel'}[name] || name);

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    });
    const payload = response.headers.get('content-type')?.includes('json') ? await response.json() : null;
    if (!response.ok) throw new Error(payload?.detail || `Lỗi HTTP ${response.status}`);
    return payload;
  }

  function notice(message, kind = 'danger') {
    const box = $('notice');
    box.className = `alert alert-${kind}`;
    box.textContent = message;
    box.classList.remove('d-none');
  }

  function clearNotice() {
    $('notice').classList.add('d-none');
  }

  function renderConnector() {
    const connector = state.connector;
    const status = $('connector-status');
    const labels = {connected: 'Đã kết nối', disconnected: 'Mất kết nối', login_required: 'Cần đăng nhập lại'};
    const colors = {connected: 'success', disconnected: 'warning', login_required: 'danger'};
    status.className = `badge text-bg-${colors[connector.state] || 'secondary'}`;
    status.textContent = labels[connector.state] || connector.state;
    if (connector.storage_full) status.textContent += ' · Hết dung lượng';
    const loginButton = $('start-zalo-login');
    loginButton.classList.toggle('d-none', connector.state === 'connected');
    loginButton.textContent = connector.state === 'disconnected' ? 'Kết nối lại' : 'Đăng nhập Zalo';
    const loginNotice = $('connector-login-notice');
    if (connector.error) {
      loginNotice.className = 'alert alert-danger';
      loginNotice.textContent = connector.error;
    } else if (connector.state === 'connected') {
      loginNotice.classList.add('d-none');
      loginNotice.textContent = '';
    }

    const qrModal = bootstrap.Modal.getOrCreateInstance($('qr-modal'));
    if (loginRequested && connector.state === 'login_required' && connector.qr_image && connector.qr_expires_at) {
      $('qr-image').src = connector.qr_image;
      $('qr-expires').textContent = `Có hiệu lực đến ${new Date(connector.qr_expires_at).toLocaleTimeString('vi-VN')}`;
      bootstrap.Modal.getInstance($('settings-modal'))?.hide();
      qrModal.show();
    } else if (loginRequested && connector.state === 'login_required' && !connector.qr_image && !connector.error) {
      $('qr-expires').textContent = 'Đang tạo mã QR mới…';
      qrModal.show();
    } else {
      qrModal.hide();
    }
  }

  function renderSources() {
    const list = $('source-list');
    if (!state.sources.length) {
      list.innerHTML = '<p class="text-muted mb-0">Connector chưa phát hiện cuộc trò chuyện nào.</p>';
      return;
    }
    list.innerHTML = state.sources.map((source) => `
      <label class="d-flex justify-content-between align-items-center border rounded p-3 mb-2">
        <span><strong>${esc(source.display_name)}</strong><br><small class="text-muted">${source.conversation_type === 'group' ? 'Nhóm' : 'Cá nhân'}</small></span>
        <input class="form-check-input source-toggle" type="checkbox" data-id="${esc(source.id)}" ${source.enabled ? 'checked' : ''}>
      </label>
    `).join('');
    list.querySelectorAll('.source-toggle').forEach((input) => input.addEventListener('change', async () => {
      try {
        await api(`/zalo-inbox/api/sources/${encodeURIComponent(input.dataset.id)}`, {
          method: 'PATCH', body: JSON.stringify({enabled: input.checked}),
        });
        await refreshState();
      } catch (error) {
        input.checked = !input.checked;
        notice(error.message);
      }
    }));
  }

  function renderMedia() {
    const container = $('media-groups');
    const sourceById = Object.fromEntries(state.sources.map((source) => [source.id, source]));
    const grouped = new Map();
    state.media.forEach((media) => {
      if (!grouped.has(media.source_id)) grouped.set(media.source_id, []);
      grouped.get(media.source_id).push(media);
    });
    if (!state.media.length) {
      container.innerHTML = '<p class="text-muted mb-0">Chưa có tài liệu từ nguồn đã bật.</p>';
      selectedMedia.clear();
      renderSelection();
      return;
    }
    const currentIds = new Set(state.media.map((media) => media.id));
    [...selectedMedia].forEach((id) => { if (!currentIds.has(id)) selectedMedia.delete(id); });
    container.innerHTML = [...grouped.entries()].map(([sourceId, mediaRows]) => `
      <div class="col-12"><h3 class="source-heading">${esc(sourceById[sourceId]?.display_name || 'Nguồn')}</h3></div>
      ${mediaRows.map((media) => `
        <div class="col-6 col-md-4 col-xl-3">
          <label class="media-card d-block">
            ${media.mime_type === 'application/pdf'
              ? '<div class="d-flex align-items-center justify-content-center bg-light" style="height:150px"><i class="bi bi-file-earmark-pdf fs-1 text-danger"></i></div>'
              : `<img src="${esc(media.content_url)}" loading="lazy" alt="Tài liệu nhận qua Zalo">`}
            <span class="body d-block">
              <input class="form-check-input media-choice me-1" type="checkbox" value="${esc(media.id)}" ${selectedMedia.has(media.id) ? 'checked' : ''}>
              <small>${new Date(media.sent_at).toLocaleString('vi-VN')}</small>
            </span>
          </label>
        </div>
      `).join('')}
    `).join('');
    container.querySelectorAll('.media-choice').forEach((input) => input.addEventListener('change', () => {
      input.checked ? selectedMedia.add(input.value) : selectedMedia.delete(input.value);
      renderSelection();
    }));
    renderSelection();
  }

  function renderSelection() {
    const count = selectedMedia.size;
    $('selection-summary').textContent = count ? `Đã chọn ${count} tài liệu` : 'Chưa chọn tài liệu';
    $('create-batch').disabled = count === 0;
    $('select-all').checked = Boolean(state?.media.length) && count === state.media.length;
  }

  async function refreshState() {
    state = await api('/zalo-inbox/api/state');
    renderConnector();
    renderSources();
    if (!batchId) renderMedia();
  }

  async function createBatch() {
    const result = await api('/zalo-inbox/api/batches', {method: 'POST', body: JSON.stringify({media_ids: [...selectedMedia]})});
    window.location.assign(result.url);
  }

  function previewPayload() {
    return [...$('preview-items').querySelectorAll('[data-item-id]')].map((element) => ({
      input_item_id: element.dataset.itemId,
      use_crop: element.querySelector('.crop-choice')?.checked || false,
    }));
  }

  async function savePreview() {
    batch = await api(`/zalo-inbox/api/batches/${encodeURIComponent(batchId)}/preview`, {
      method: 'PATCH', body: JSON.stringify({items: previewPayload()}),
    });
    renderBatch();
  }

  function bindPreview() {
    const container = $('preview-items');
    let dragging = null;
    container.querySelectorAll('[data-item-id]').forEach((card) => {
      card.addEventListener('dragstart', () => { dragging = card; card.classList.add('dragging'); });
      card.addEventListener('dragend', async () => {
        card.classList.remove('dragging'); dragging = null;
        try { await savePreview(); } catch (error) { notice(error.message); }
      });
      card.addEventListener('dragover', (event) => {
        event.preventDefault();
        if (!dragging || dragging === card) return;
        const rect = card.getBoundingClientRect();
        container.insertBefore(dragging, event.clientY < rect.top + rect.height / 2 ? card : card.nextSibling);
      });
      card.querySelector('.remove-item')?.addEventListener('click', async () => {
        card.remove();
        try { await savePreview(); } catch (error) { notice(error.message); }
      });
      card.querySelector('.crop-choice')?.addEventListener('change', async () => {
        try { await savePreview(); } catch (error) { notice(error.message); }
      });
    });
  }

  function renderPreview() {
    $('preview-items').innerHTML = batch.items.map((item) => `
      <div class="col-6 col-lg-3" data-item-id="${esc(item.input_item_id)}" draggable="true">
        <div class="preview-card ${item.status === 'error' ? 'border-danger' : ''}">
          ${item.status === 'ready' ? `<img src="${esc(item.preview_url)}" alt="Preview tài liệu">` : '<div class="p-4 text-danger">Chuẩn bị lỗi</div>'}
          <div class="body">
            <strong class="small">${esc(item.source_display_name)}</strong>
            <div class="small text-muted">${item.page_count > 1 ? `Trang ${item.page_number}/${item.page_count}` : '1 trang'}</div>
            ${item.error ? `<div class="small text-danger mt-1">${esc(item.error)}</div>` : ''}
            <div class="d-flex justify-content-between mt-2">
              <label class="small"><input class="form-check-input crop-choice" type="checkbox" ${item.use_crop ? 'checked' : ''} ${item.crop_available ? '' : 'disabled'}> Crop</label>
              <button class="btn btn-link btn-sm text-danger p-0 remove-item" type="button">Bỏ</button>
            </div>
          </div>
        </div>
      </div>
    `).join('');
    bindPreview();
  }

  function renderResults() {
    const states = {creating: 'Đang tạo', awaiting_confirmation: 'Chờ xác nhận', ready: 'Sẵn sàng', error: 'Lỗi', expired: 'Hết hạn'};
    $('output-results').innerHTML = Object.entries(batch.outputs).map(([name, output]) => `
      <div class="col-md-4"><div class="output-state">
        <strong>${label(name)}</strong><div class="small text-muted my-2">${states[output.status] || output.status}</div>
        ${output.error ? `<div class="small text-danger mb-2">${esc(output.error)}</div>` : ''}
        ${output.download_url ? `<a class="btn btn-outline-primary btn-sm" href="${esc(output.download_url)}">Tải xuống</a>` : ''}
        ${output.status === 'error' && output.retryable ? `<button id="retry-output-${esc(name)}" class="btn btn-outline-danger btn-sm" type="button">Thử lại</button>` : ''}
      </div></div>
    `).join('');
    Object.entries(batch.outputs).forEach(([name, output]) => {
      if (output.status === 'error' && output.retryable) {
        $(`retry-output-${name}`).addEventListener('click', () => retry('output', name));
      }
    });
    const canReview = batch.ocr_status === 'awaiting_confirmation' || batch.ocr_status === 'confirmed';
    $('open-review').classList.toggle('d-none', !canReview);
    if (batch.ocr_status === 'error') {
      $('output-results').insertAdjacentHTML('beforeend', '<div class="col-12"><button id="retry-ocr" class="btn btn-outline-danger btn-sm">Thử lại OCR</button></div>');
      $('retry-ocr').addEventListener('click', () => retry('ocr'));
    }
  }

  function renderBatch() {
    $('inbox-view').classList.add('d-none');
    $('batch-view').classList.remove('d-none');
    ['preparing-panel', 'preview-panel', 'result-panel'].forEach((id) => $(id).classList.add('d-none'));
    $('batch-expiry').textContent = batch.expires_at ? `Hết hạn: ${new Date(batch.expires_at).toLocaleString('vi-VN')}` : '';
    if (batch.status === 'preparing') {
      $('preparing-panel').classList.remove('d-none');
    } else if (!batch.selection.length && (batch.status === 'review' || batch.status === 'error')) {
      $('preview-panel').classList.remove('d-none');
      renderPreview();
      if (batch.status === 'error') {
        $('preview-items').insertAdjacentHTML('afterend', '<button id="retry-preparation" class="btn btn-outline-danger btn-sm mt-3">Thử lại item lỗi</button>');
        $('retry-preparation').addEventListener('click', () => retry('preparation'));
      }
    } else {
      $('result-panel').classList.remove('d-none');
      renderResults();
    }
  }

  async function refreshBatch() {
    if (!batchId) return;
    batch = await api(`/zalo-inbox/api/batches/${encodeURIComponent(batchId)}`);
    renderBatch();
  }

  async function retry(step, outputType = null) {
    try {
      clearNotice();
      await api(`/zalo-inbox/api/batches/${encodeURIComponent(batchId)}/retry`, {
        method: 'POST', body: JSON.stringify({step, output_type: outputType}),
      });
      await refreshBatch();
    } catch (error) { notice(error.message); }
  }

  $('open-settings').addEventListener('click', () => bootstrap.Modal.getOrCreateInstance($('settings-modal')).show());
  $('start-zalo-login').addEventListener('click', async () => {
    const button = $('start-zalo-login');
    const loginNotice = $('connector-login-notice');
    button.disabled = true;
    loginRequested = true;
    loginNotice.classList.add('d-none');
    try {
      clearNotice();
      await api('/zalo-inbox/api/connectors/start', {
        method: 'POST',
        body: JSON.stringify({
          force_restart: state.connector.state !== 'connected',
          force_qr: state.connector.state === 'login_required',
        }),
      });
      loginNotice.className = 'alert alert-info';
      loginNotice.textContent = 'Đang tạo mã QR đăng nhập Zalo…';
      await refreshState();
    } catch (error) {
      loginNotice.className = 'alert alert-danger';
      loginNotice.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  $('select-all').addEventListener('change', (event) => {
    selectedMedia.clear();
    if (event.target.checked) state.media.forEach((media) => selectedMedia.add(media.id));
    renderMedia();
  });
  $('create-batch').addEventListener('click', async () => {
    try {
      clearNotice();
      if (state.latest_batch?.unfinished) {
        $('previous-batch-link').href = state.latest_batch.url;
        bootstrap.Modal.getOrCreateInstance($('previous-batch-warning')).show();
        return;
      }
      await createBatch();
    } catch (error) { notice(error.message); }
  });
  $('continue-create-batch').addEventListener('click', async () => {
    try {
      bootstrap.Modal.getOrCreateInstance($('previous-batch-warning')).hide();
      await createBatch();
    } catch (error) { notice(error.message); }
  });
  document.querySelectorAll('.output-choice').forEach((input) => input.addEventListener('change', () => {
    $('start-output').disabled = !document.querySelector('.output-choice:checked');
  }));
  $('start-output').addEventListener('click', async () => {
    try {
      clearNotice();
      const outputs = [...document.querySelectorAll('.output-choice:checked')].map((input) => input.value);
      await api(`/zalo-inbox/api/batches/${encodeURIComponent(batchId)}/outputs`, {method: 'POST', body: JSON.stringify({outputs})});
      await refreshBatch();
    } catch (error) { notice(error.message); }
  });
  $('open-review').addEventListener('click', () => {
    const result = batch.ocr_result || {};
    $('persons-json').value = JSON.stringify(result.persons || [], null, 2);
    $('properties-json').value = JSON.stringify(result.properties || [], null, 2);
    $('raw-ocr').textContent = JSON.stringify(result.raw_results || [], null, 2);
    const readOnly = batch.ocr_read_only;
    $('persons-json').readOnly = readOnly;
    $('properties-json').readOnly = readOnly;
    $('confirm-ocr').classList.toggle('d-none', readOnly);
    bootstrap.Modal.getOrCreateInstance($('review-modal')).show();
  });
  $('confirm-ocr').addEventListener('click', async () => {
    try {
      clearNotice();
      const persons = JSON.parse($('persons-json').value);
      const properties = JSON.parse($('properties-json').value);
      batch = await api(`/zalo-inbox/api/batches/${encodeURIComponent(batchId)}/confirm`, {
        method: 'POST', body: JSON.stringify({persons, properties}),
      });
      bootstrap.Modal.getOrCreateInstance($('review-modal')).hide();
      renderBatch();
    } catch (error) { notice(error.message); }
  });

  async function refresh() {
    if (document.hidden) return;
    try {
      await refreshState();
      await refreshBatch();
    } catch (error) { notice(error.message); }
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('focus', refresh);
  refresh();
  window.setInterval(refresh, 2000);
})();
