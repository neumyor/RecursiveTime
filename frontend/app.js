const state = {
  bootstrap: null,
  busy: false,
  selectedNodeType: null,
  pendingParts: [],
  loadingMessage: null,
  transcriptScope: 'all',
};

const els = {
  refreshBtn: document.querySelector('#refreshBtn'),
  statusText: document.querySelector('#statusText'),
  modeText: document.querySelector('#modeText'),
  modelText: document.querySelector('#modelText'),
  runtimeUvText: document.querySelector('#runtimeUvText'),
  nodeList: document.querySelector('#nodeList'),
  nodeDetail: document.querySelector('#nodeDetail'),
  chatStream: document.querySelector('#chatStream'),
  transcriptScope: document.querySelector('#transcriptScope'),
  sendForm: document.querySelector('#sendForm'),
  messageInput: document.querySelector('#messageInput'),
  sendBtn: document.querySelector('#sendBtn'),
  interruptBtn: document.querySelector('#interruptBtn'),
  timeline: document.querySelector('#timeline'),
  workspacePath: document.querySelector('#workspacePath'),
  fileTree: document.querySelector('#fileTree'),
  uploadForm: document.querySelector('#uploadForm'),
  referenceFiles: document.querySelector('#referenceFiles'),
  uploadBtn: document.querySelector('#uploadBtn'),
  stateBtn: document.querySelector('#stateBtn'),
  llmBtn: document.querySelector('#llmBtn'),
  clearAllLogsBtn: document.querySelector('#clearAllLogsBtn'),
  dialog: document.querySelector('#detailDialog'),
  dialogTitle: document.querySelector('#dialogTitle'),
  dialogBody: document.querySelector('#dialogBody'),
};

els.refreshBtn.addEventListener('click', () => refresh());
els.transcriptScope.addEventListener('change', () => {
  state.transcriptScope = els.transcriptScope.value;
  render();
});
els.stateBtn.addEventListener('click', () => showDetail('Workspace State', state.bootstrap?.state));
els.llmBtn.addEventListener('click', () => showDetail('LLM Config', state.bootstrap?.llmConfig));
els.interruptBtn.addEventListener('click', async () => {
  const reason = els.messageInput.value.trim();
  await interruptCurrent(reason || 'User interrupted from web UI.');
});
els.clearAllLogsBtn.addEventListener('click', async () => {
  if (!confirm('清空主聊天、timeline 和 node logs？该操作仅用于调试。')) return;
  await runAction(async () => {
    const result = await postJson('/api/debug/clear-logs', { scope: 'all' });
    state.bootstrap = result.bootstrap;
    render();
  });
});

els.sendForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = els.messageInput.value.trim();
  if (!text) return;
  els.messageInput.value = '';
  const pendingId = `pending-${Date.now()}`;
  state.pendingParts.push({
    id: pendingId,
    timestamp: new Date().toISOString(),
    role: 'user',
    type: 'text',
    text,
    sourceLabel: 'main',
    pending: true,
  });
  state.loadingMessage = {
    id: `loading-${Date.now()}`,
    timestamp: new Date().toISOString(),
    role: 'assistant',
    type: 'loading',
    text: '运行中',
    sourceLabel: 'harness',
  };
  render();
  await nextPaint();
  await runStreamingAction(async () => {
    const result = await postJson('/api/send', { text });
    state.bootstrap = result.bootstrap;
    state.pendingParts = state.pendingParts.filter((part) => part.id !== pendingId);
    render();
  });
});

els.uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const files = [...els.referenceFiles.files];
  if (!files.length) return;
  await runAction(async () => {
    const form = new FormData();
    for (const file of files) form.append('files', file);
    const result = await postForm('/api/references/upload', form);
    els.referenceFiles.value = '';
    state.bootstrap = result.bootstrap;
    render();
  });
});

async function refresh() {
  const data = await fetchJson('/api/bootstrap');
  state.bootstrap = data;
  state.busy = Boolean(data.runtime?.running);
  if (!data.runtime?.running) {
    state.loadingMessage = null;
    state.pendingParts = [];
  } else if (!state.loadingMessage) {
    state.loadingMessage = {
      id: `loading-${Date.now()}`,
      timestamp: new Date().toISOString(),
      role: 'assistant',
      type: 'loading',
      text: '后端运行中，点击刷新获取最新消息',
      sourceLabel: 'harness',
    };
  }
  render();
}

function render() {
  const data = state.bootstrap;
  if (!data) {
    renderChat(emptyBootstrap());
    return;
  }

  const ws = data.state;
  els.statusText.textContent = ws.activeNode ? `Active: ${ws.activeNode}` : 'Ready';
  els.modeText.textContent = data.dryRun ? `${ws.mode} / dry-run` : ws.mode;
  els.modelText.textContent = data.llmConfig?.config?.model || 'sdk-default';
  els.runtimeUvText.textContent = formatRuntimeUv(data.runtime?.workspaceUv);

  if (!state.selectedNodeType && data.nodeSpecs.length) {
    state.selectedNodeType = ws.activeNode || data.nodeSpecs[0].type;
  }
  renderNodes(data.nodeSpecs, ws, data.nodes);
  renderNodeDetail(data.nodeSpecs, data.nodes);
  renderTranscriptScope(data.nodes);
  renderChat(data);
  renderTimeline(data.timeline);
  renderFileTree(data.fileTree);
  renderDebugActions(data.debugEnabled);
  updateControls(data);
}

function renderTranscriptScope(nodes) {
  const options = [
    { value: 'all', label: 'All sessions' },
    { value: 'main', label: 'Main only' },
    ...(nodes || []).slice().reverse().map((node) => ({
      value: `node:${node.id}`,
      label: `${node.nodeType} · ${node.status} · ${formatTime(node.startedAt)}`,
    })),
  ];
  if (!options.some((option) => option.value === state.transcriptScope)) {
    state.transcriptScope = 'all';
  }
  const current = els.transcriptScope.value;
  const nextHtml = options.map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`).join('');
  if (els.transcriptScope.innerHTML !== nextHtml) {
    els.transcriptScope.innerHTML = nextHtml;
  }
  els.transcriptScope.value = state.transcriptScope || current || 'all';
}

function renderDebugActions(enabled) {
  for (const element of document.querySelectorAll('.debug-only')) {
    element.hidden = !enabled;
  }
}

function renderNodes(specs, ws, sessions) {
  const latestByType = new Map();
  for (const session of sessions) latestByType.set(session.nodeType, session);

  els.nodeList.innerHTML = specs.map((spec) => {
    const session = latestByType.get(spec.type);
    const active = ws.activeNode === spec.type;
    const done = ws.completedNodes.includes(spec.type);
    const failed = !done && session?.status === 'failed';
    const status = active ? 'active' : done ? 'done' : failed ? 'failed' : 'pending';
    return `
      <button class="node-item ${state.selectedNodeType === spec.type ? 'selected' : ''}" data-node="${escapeHtml(spec.type)}">
        <div>
          <div class="node-name">${escapeHtml(spec.type)}</div>
          <div class="meta">${escapeHtml(spec.phase)} · ${escapeHtml(spec.purpose)}</div>
        </div>
        <span class="badge ${status}">${status}</span>
      </button>
    `;
  }).join('');

  for (const item of els.nodeList.querySelectorAll('.node-item')) {
    item.addEventListener('click', () => {
      state.selectedNodeType = item.dataset.node;
      render();
    });
  }
}

function renderNodeDetail(specs, nodes) {
  const type = state.selectedNodeType;
  const spec = specs.find((candidate) => candidate.type === type);
  if (!spec) {
    els.nodeDetail.innerHTML = `<div class="empty">请选择一个 node。</div>`;
    return;
  }
  const sessions = nodes.filter((node) => node.nodeType === type).slice().reverse();
  const produced = unique([
    ...spec.produces,
    ...sessions.flatMap((node) => node.outputPaths || []),
  ]);
  els.nodeDetail.innerHTML = `
    <div class="node-detail-title">${escapeHtml(spec.type)}</div>
    <div class="meta">${escapeHtml(spec.purpose)}</div>
    <div class="detail-section-title">Artifacts</div>
    ${produced.length ? `<div class="artifact-list">${produced.map((path) => `
      <button class="artifact-item" data-path="${escapeHtml(path)}">${escapeHtml(path)}</button>
    `).join('')}</div>` : `<div class="empty">暂无节点产物。</div>`}
    <div class="detail-section-title">Sessions</div>
    ${sessions.length ? `<div class="session-list">${sessions.map((node) => `
      <button class="session-item" data-session="${escapeHtml(node.id)}">
        <div class="session-title">${escapeHtml(node.status)} · ${formatTime(node.startedAt)}</div>
        <div class="meta">${escapeHtml(node.summary || node.rationale || '')}</div>
      </button>
    `).join('')}</div>` : `<div class="empty">暂无 node session。</div>`}
  `;

  for (const item of els.nodeDetail.querySelectorAll('.session-item')) {
    item.addEventListener('click', async () => {
      const log = await fetchJson(`/api/nodes/${item.dataset.session}/log`);
      showDetail(`Node Log ${item.dataset.session}`, log);
    });
  }
  for (const item of els.nodeDetail.querySelectorAll('.artifact-item')) {
    item.addEventListener('click', async () => showWorkspaceFile(item.dataset.path));
  }
}

function renderChat(data) {
  const parts = collectTranscriptParts(data);
  const visibleParts = normalizeChatParts(parts);
  if (!visibleParts.length) {
    els.chatStream.innerHTML = `<div class="empty">暂无主会话消息。发送消息后，orchestrator 会决定是否进入 node。</div>`;
    return;
  }
  els.chatStream.innerHTML = visibleParts.slice(-80).map((part) => {
    const role = part.role || 'system';
    const roleClass = ['user', 'assistant', 'system', 'tool'].includes(role) ? role : 'system';
    const text = part.displayText || part.text || summarizeRaw(part.raw) || '';
    const source = part.sourceLabel ? `${part.sourceLabel} · ` : '';
    if (part.type === 'loading') {
      return `
        <article class="message assistant loading">
          <div class="message-role">${escapeHtml(source)}assistant · running · ${formatTime(part.timestamp)}</div>
          <div class="message-text loading-line"><span class="spinner"></span><span>${escapeHtml(part.text)}</span></div>
        </article>
      `;
    }
    if (part.type === 'tool_use' || part.type === 'tool_result') {
      const summary = toolSummary(part);
      const detail = part.displayText || part.text || summarizeRaw(part.raw) || '';
      return `
        <article class="message ${escapeHtml(roleClass)} tool-collapsed">
          <div class="message-role">${escapeHtml(source)}${escapeHtml(role)} · ${escapeHtml(part.type || 'text')} · ${formatTime(part.timestamp)}</div>
          <details>
            <summary>${escapeHtml(summary)}</summary>
            <pre class="tool-detail">${escapeHtml(detail)}</pre>
          </details>
        </article>
      `;
    }
    return `
      <article class="message ${escapeHtml(roleClass)}">
        <div class="message-role">${escapeHtml(source)}${escapeHtml(role)} · ${escapeHtml(part.type || 'text')} · ${formatTime(part.timestamp)}</div>
        <div class="message-text">${escapeHtml(text)}</div>
      </article>
    `;
  }).join('');
  els.chatStream.scrollTop = els.chatStream.scrollHeight;
}

function toolSummary(part) {
  if (part.type === 'tool_use') {
    const name = part.name || part.raw?.message?.content?.find?.((block) => block.type === 'tool_use')?.name || 'tool';
    const input = part.input || part.raw?.message?.content?.find?.((block) => block.type === 'tool_use')?.input;
    const hint = input && typeof input === 'object' ? Object.keys(input).slice(0, 3).join(', ') : '';
    return hint ? `调用工具：${name} (${hint})` : `调用工具：${name}`;
  }
  const text = part.displayText || part.text || '';
  const firstLine = text.split('\n').find((line) => line.trim()) || '工具结果';
  return firstLine.length > 120 ? `${firstLine.slice(0, 117)}...` : firstLine;
}

function collectTranscriptParts(data) {
  const scope = state.transcriptScope || 'all';
  const mainParts = (data.mainParts || []).map((part) => ({
    ...part,
    sourceLabel: 'main',
    sortKey: `${part.timestamp || ''}:main:${part.id || ''}`,
  }));
  const loggedUserTexts = new Set(mainParts.filter((part) => part.role === 'user' && part.text).map((part) => part.text));
  const nodeParts = [];
  const sessionsById = new Map((data.nodes || []).map((node) => [node.id, node]));
  for (const [nodeId, parts] of Object.entries(data.nodePartsById || {})) {
    const node = sessionsById.get(nodeId);
    const label = node ? `node:${node.nodeType}` : `node:${nodeId.slice(0, 8)}`;
    for (const part of parts || []) {
      nodeParts.push({
        ...part,
        nodeSessionId: nodeId,
        sourceLabel: label,
        sortKey: `${part.timestamp || ''}:node:${nodeId}:${part.id || ''}`,
      });
    }
  }
  const pendingParts = state.pendingParts
    .filter((part) => !(part.role === 'user' && loggedUserTexts.has(part.text)))
    .map((part) => ({
      ...part,
      sortKey: `${part.timestamp || ''}:pending:${part.id || ''}`,
    }));
  const loadingParts = state.loadingMessage ? [{
    ...state.loadingMessage,
    sortKey: `${new Date().toISOString()}:loading:${state.loadingMessage.id}`,
  }] : [];
  if (scope === 'main') {
    return [...mainParts, ...pendingParts, ...loadingParts].sort((a, b) => a.sortKey.localeCompare(b.sortKey));
  }
  if (scope.startsWith('node:')) {
    const nodeId = scope.slice('node:'.length);
    return nodeParts.filter((part) => part.nodeSessionId === nodeId || part.sortKey.includes(`:node:${nodeId}:`)).sort((a, b) => a.sortKey.localeCompare(b.sortKey));
  }
  return [...mainParts, ...nodeParts, ...pendingParts, ...loadingParts].sort((a, b) => a.sortKey.localeCompare(b.sortKey));
}

function normalizeChatParts(parts) {
  return parts
    .map((part) => ({ ...part, displayText: displayTextForPart(part) }))
    .filter((part) => {
      if (part.type === 'loading') return true;
      if (!part.displayText.trim()) return false;
      if (part.role === 'system' && part.type === 'raw' && ['init'].includes(part.displayText.trim())) return false;
      if (part.role === 'system' && part.type === 'result' && part.raw?.is_error !== true) return false;
      return true;
    });
}

function displayTextForPart(part) {
  if (part.type === 'loading') return part.text || '运行中';
  if (part.type === 'tool_use') {
    const name = part.name || part.raw?.message?.content?.find?.((block) => block.type === 'tool_use')?.name || 'tool';
    const input = part.input || part.raw?.message?.content?.find?.((block) => block.type === 'tool_use')?.input;
    return input ? `调用工具：${name}\n${JSON.stringify(input, null, 2)}` : `调用工具：${name}`;
  }
  if (part.type === 'tool_result') {
    const result = part.raw?.tool_use_result;
    if (result?.filenames) {
      const files = result.filenames.slice(0, 20).join('\n');
      const more = result.truncated ? `\n... (${result.numFiles} files total)` : '';
      return result.filenames.length ? `工具结果：\n${files}${more}` : '工具结果：No files found';
    }
    return part.text || '';
  }
  if (part.role === 'system' && part.type === 'raw') {
    const subtype = part.raw?.subtype || part.text || '';
    if (subtype === 'api_retry') return `API retry: attempt ${part.raw?.attempt ?? '?'}/${part.raw?.max_retries ?? '?'}`;
    return subtype;
  }
  if (part.role === 'system' && part.type === 'result') {
    if (part.raw?.is_error) return part.raw?.result || part.text || 'Error';
    return '';
  }
  return stripHarnessControl(part.text || '');
}

function stripHarnessControl(text) {
  return text
    .replace(/```(?:json)?\s*\{[\s\S]*?"harnessControl"[\s\S]*?\}\s*```/gi, '')
    .replace(/\{[\s\S]*?"harnessControl"[\s\S]*?\}\s*$/i, '')
    .trim();
}

function renderTimeline(events) {
  if (!events.length) {
    els.timeline.innerHTML = `<div class="empty">暂无流程记录。</div>`;
    return;
  }
  els.timeline.innerHTML = events.slice(-80).reverse().map((event) => `
    <div class="timeline-item">
      <div class="timeline-type">${escapeHtml(event.type)} ${event.nodeType ? `· ${escapeHtml(event.nodeType)}` : ''}</div>
      <div class="meta">${formatTime(event.timestamp)}</div>
      <div>${escapeHtml(event.message || '')}</div>
    </div>
  `).join('');
}

function renderFileTree(fileTree) {
  if (!fileTree?.tree) {
    els.workspacePath.textContent = '';
    els.fileTree.innerHTML = `<div class="empty">暂无 workspace 文件。</div>`;
    return;
  }
  els.workspacePath.textContent = fileTree.root || '';
  els.fileTree.innerHTML = renderTreeNode(fileTree.tree, true);
  if (fileTree.truncated) {
    els.fileTree.insertAdjacentHTML('beforeend', `<div class="empty">文件数量过多，已截断显示。</div>`);
  }
  for (const item of els.fileTree.querySelectorAll('.file-node.file')) {
    item.addEventListener('click', async () => showWorkspaceFile(item.dataset.path));
  }
}

function renderTreeNode(node, root = false) {
  if (!node) return '';
  if (node.kind === 'dir') {
    const open = root || ['user', 'artifacts', 'data', 'tools', 'runs', 'reports'].includes(node.path);
    return `
      <details class="file-dir" ${open ? 'open' : ''}>
        <summary>${root ? '▾' : '▸'} ${escapeHtml(node.name || 'workspace')}</summary>
        <div class="file-children">
          ${(node.children || []).map((child) => renderTreeNode(child)).join('')}
        </div>
      </details>
    `;
  }
  return `
    <button class="file-node file" data-path="${escapeHtml(node.path)}">
      <span>${escapeHtml(node.name)}</span>
      <span class="file-size">${formatBytes(node.size || 0)}</span>
    </button>
  `;
}

async function showWorkspaceFile(path) {
  if (!path) return;
  try {
    const file = await fetchJson(`/api/files/content?path=${encodeURIComponent(path)}`);
    if (file.binary) {
      showDetail(path, { message: 'Binary file preview is not supported.', size: file.size });
      return;
    }
    if (file.truncated) {
      showDetail(path, { message: 'File is too large to preview.', size: file.size });
      return;
    }
    showTextDetail(path, file.text || '');
  } catch (error) {
    showDetail(path, { message: error.message || String(error) });
  }
}

function updateControls(data) {
  const ws = data.state || {};
  const activeSession = getActiveNodeSession(data);
  const activePaused = Boolean(ws.activeNode && activeSession?.status === 'paused');
  const activeRunning = Boolean(ws.activeNode && activeSession?.status === 'running');
  els.sendBtn.disabled = state.busy || (Boolean(ws.activeNode) && !activePaused);
  els.sendBtn.textContent = activePaused ? 'Resume Node' : 'Send';
  els.messageInput.disabled = state.busy || (Boolean(ws.activeNode) && !activePaused);
  els.messageInput.placeholder = activePaused
    ? '补充说明后点击 Resume Node，当前 node 会继续执行'
    : '向 main orchestrator 发送消息，例如：请基于 ECG5000 设计异常样本分类的工具使用流程';
  els.interruptBtn.disabled = !state.busy && !activeRunning;
  els.uploadBtn.disabled = state.busy;
}

function getActiveNodeSession(data) {
  const ws = data.state || {};
  if (!ws.activeNodeSessionId) return null;
  return (data.nodes || []).find((node) => node.id === ws.activeNodeSessionId) || null;
}

async function runAction(fn) {
  state.busy = true;
  render();
  try {
    await fn();
  } catch (error) {
    showDetail('Error', { message: error.message || String(error) });
  } finally {
    state.busy = false;
    render();
  }
}

async function runStreamingAction(fn) {
  state.busy = true;
  render();
  await nextPaint();
  try {
    await fn();
  } catch (error) {
    showDetail('Error', { message: error.message || String(error) });
  } finally {
    try {
      const data = await fetchJson('/api/bootstrap');
      state.bootstrap = data;
      state.busy = Boolean(data.runtime?.running);
      if (!data.runtime?.running) {
        state.loadingMessage = null;
        state.pendingParts = [];
      }
    } catch {
      state.busy = false;
    }
    render();
  }
}

function emptyBootstrap() {
  return {
    state: {
      activeNode: null,
      completedNodes: [],
    },
    mainParts: [],
    nodePartsById: {},
    nodes: [],
    nodeSpecs: [],
    timeline: [],
    fileTree: null,
    runtime: { running: false, workspaceUv: null },
  };
}

function formatRuntimeUv(runtimeUv) {
  if (!runtimeUv) return '-';
  const runtimeState = runtimeUv.state || 'unknown';
  if (runtimeState === 'ready') return `ready · ${runtimeUv.pythonVersion || 'python'}`;
  if (runtimeState === 'skipped') return 'skipped';
  if (runtimeState === 'failed') return 'failed';
  return runtimeState;
}

function nextPaint() {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

async function interruptCurrent(reason) {
  els.interruptBtn.disabled = true;
  try {
    const result = await postJson('/api/interrupt', { reason });
    state.bootstrap = result.bootstrap;
    state.busy = false;
    state.loadingMessage = null;
    render();
  } catch (error) {
    showDetail('Interrupt Error', { message: error.message || String(error) });
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

async function postForm(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    body,
  });
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

function errorMessage(payload, response) {
  if (payload?.error) return payload.error;
  if (payload?.detail) return typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
  if (payload?.message) return payload.message;
  return response.statusText || `HTTP ${response.status}`;
}

function showDetail(title, value) {
  els.dialogTitle.textContent = title;
  els.dialogBody.textContent = JSON.stringify(value ?? null, null, 2);
  els.dialog.showModal();
}

function showTextDetail(title, text) {
  els.dialogTitle.textContent = title;
  els.dialogBody.textContent = text;
  els.dialog.showModal();
}

function summarizeRaw(raw) {
  if (!raw) return '';
  if (raw.subtype) return raw.subtype;
  if (raw.type) return raw.type;
  return JSON.stringify(raw);
}

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatBytes(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

refresh().catch((error) => showDetail('Startup Error', { message: error.message || String(error) }));
