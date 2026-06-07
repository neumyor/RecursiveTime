import './styles.css';
import DOMPurify from 'dompurify';
import {
  Activity,
  AlertTriangle,
  ArrowUp,
  Archive,
  Bot,
  Boxes,
  ChevronLeft,
  Check,
  ChevronRight,
  Circle,
  Clock3,
  File,
  FolderTree,
  Gauge,
  GitBranch,
  HardDriveUpload,
  Info,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  TerminalSquare,
  Trash2,
  Upload,
  X,
  XCircle,
  type IconNode,
} from 'lucide';
import { marked } from 'marked';

type JsonMap = Record<string, any>;

type FileTreeNode = {
  kind: 'dir' | 'file';
  name: string;
  path: string;
  size?: number;
  children?: FileTreeNode[];
};

type Bootstrap = {
  state: JsonMap;
  timeline: JsonMap[];
  mainParts: JsonMap[];
  nodes: JsonMap[];
  nodePartsById: Record<string, JsonMap[]>;
  nodeSpecs: JsonMap[];
  fileTree: { root?: string; tree?: FileTreeNode; truncated?: boolean } | null;
  llmConfig?: JsonMap;
  dryRun?: boolean;
  debugEnabled?: boolean;
  runtime?: {
    running?: boolean;
    workspaceUv?: JsonMap | null;
  };
};

const state = {
  bootstrap: null as Bootstrap | null,
  busy: false,
  selectedNodeType: null as string | null,
  pendingParts: [] as JsonMap[],
  loadingMessage: null as JsonMap | null,
  transcriptScope: 'all',
  lastRefreshAt: null as Date | null,
  leftCollapsed: window.innerWidth <= 820,
  rightCollapsed: window.innerWidth <= 1180,
};

marked.setOptions({
  breaks: true,
  gfm: true,
});

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) throw new Error('Missing #app root');

app.innerHTML = `
  <button id="leftRailToggle" class="rail-toggle left-toggle" type="button" title="折叠左栏"><span data-icon="ChevronLeft"></span></button>
  <button id="rightRailToggle" class="rail-toggle right-toggle" type="button" title="折叠右栏"><span data-icon="ChevronRight"></span></button>

  <aside class="left-rail">
    <section class="brand-block">
      <div class="brand-mark" data-icon="Sparkles"></div>
      <div>
        <h1>HarnessingTS</h1>
        <p>Time-Series Tool-Use Harness</p>
      </div>
    </section>

    <section class="panel status-panel">
      <div class="panel-heading">
        <span data-icon="Gauge"></span>
        <span>Workspace</span>
      </div>
      <dl class="kv">
        <dt>Status</dt>
        <dd id="statusText">Loading</dd>
        <dt>Mode</dt>
        <dd id="modeText">-</dd>
        <dt>Model</dt>
        <dd id="modelText">-</dd>
        <dt>Runtime</dt>
        <dd id="runtimeUvText">-</dd>
      </dl>
      <div class="workspace-actions">
        <button id="stateBtn" type="button" class="ghost"><span data-icon="Archive"></span><span>State</span></button>
        <button id="llmBtn" type="button" class="ghost"><span data-icon="Settings2"></span><span>LLM</span></button>
      </div>
    </section>

    <section id="pendingControlPanel" class="panel control-panel" hidden>
      <div class="panel-heading">
        <span data-icon="ShieldCheck"></span>
        <span>Pending Control</span>
      </div>
      <div id="pendingControlBody" class="control-body"></div>
      <div class="split-actions">
        <button id="approveControlBtn" type="button" class="success-btn"><span data-icon="Check"></span><span>Approve</span></button>
        <button id="rejectControlBtn" type="button" class="danger ghost"><span data-icon="X"></span><span>Reject</span></button>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <span data-icon="GitBranch"></span>
        <span>Node Chain</span>
      </div>
      <div id="nodeList" class="node-list"></div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <span data-icon="Boxes"></span>
        <span>Selected Node</span>
      </div>
      <div id="nodeDetail" class="node-detail"></div>
    </section>

    <details class="panel timeline-panel">
      <summary class="panel-heading">
        <span data-icon="Clock3"></span>
        <span>Timeline</span>
      </summary>
      <div id="timeline" class="timeline"></div>
    </details>
  </aside>

  <main class="main-pane">
    <header class="toolbar">
      <div class="toolbar-main">
        <div class="title-group">
          <div class="eyebrow"><span data-icon="Bot"></span><span>Main Session</span></div>
          <h2 id="mainTitle">Orchestrator</h2>
        </div>
        <label class="transcript-filter">
          <span>Transcript</span>
          <select id="transcriptScope"></select>
        </label>
      </div>
      <div class="toolbar-actions">
        <button id="interruptBtn" type="button" class="danger ghost"><span data-icon="Pause"></span><span>Pause</span></button>
        <button id="clearAllLogsBtn" type="button" class="danger ghost debug-only"><span data-icon="Trash2"></span><span>Clear Logs</span></button>
      </div>
    </header>

    <section id="chatStream" class="chat-stream"></section>

    <form id="sendForm" class="composer">
      <div class="composer-shell">
        <textarea id="messageInput" rows="1" placeholder="向 orchestrator 发送消息"></textarea>
        <button id="sendBtn" type="submit" class="send-round" title="发送" disabled><span data-icon="ArrowUp"></span></button>
      </div>
    </form>
  </main>

  <aside class="right-rail">
    <section class="panel files-panel">
      <div class="panel-heading">
        <span data-icon="FolderTree"></span>
        <span>Workspace Files</span>
      </div>
      <div id="workspacePath" class="workspace-path"></div>
      <form id="uploadForm" class="upload-form">
        <label>
          <span>Reference Files</span>
          <input id="referenceFiles" type="file" multiple />
        </label>
        <button id="uploadBtn" type="submit" class="secondary"><span data-icon="Upload"></span><span>Upload references</span></button>
      </form>
      <form id="rawZipUploadForm" class="upload-form">
        <label>
          <span>Raw Data Zip</span>
          <input id="rawZipFile" type="file" accept=".zip" />
        </label>
        <div class="upload-hint">Upload a .zip archive; it will be extracted into data/raw/.</div>
        <button id="rawZipUploadBtn" type="submit" class="secondary"><span data-icon="HardDriveUpload"></span><span>Extract raw data</span></button>
      </form>
      <div id="fileTree" class="file-tree"></div>
    </section>
  </aside>

  <dialog id="detailDialog">
    <form method="dialog">
      <header>
        <h3 id="dialogTitle">Detail</h3>
        <button value="close" class="icon-btn ghost" type="submit" title="关闭"><span data-icon="X"></span></button>
      </header>
      <pre id="dialogBody"></pre>
    </form>
  </dialog>
`;

const iconMap: Record<string, IconNode> = {
  Activity,
  AlertTriangle,
  ArrowUp,
  Archive,
  Bot,
  Boxes,
  ChevronLeft,
  Check,
  ChevronRight,
  Circle,
  Clock3,
  File,
  FolderTree,
  Gauge,
  GitBranch,
  HardDriveUpload,
  Info,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  TerminalSquare,
  Trash2,
  Upload,
  X,
  XCircle,
};

const els = {
  leftRailToggle: query<HTMLButtonElement>('#leftRailToggle'),
  rightRailToggle: query<HTMLButtonElement>('#rightRailToggle'),
  statusText: query('#statusText'),
  modeText: query('#modeText'),
  modelText: query('#modelText'),
  runtimeUvText: query('#runtimeUvText'),
  pendingControlPanel: query<HTMLElement>('#pendingControlPanel'),
  pendingControlBody: query('#pendingControlBody'),
  approveControlBtn: query<HTMLButtonElement>('#approveControlBtn'),
  rejectControlBtn: query<HTMLButtonElement>('#rejectControlBtn'),
  nodeList: query('#nodeList'),
  nodeDetail: query('#nodeDetail'),
  chatStream: query<HTMLElement>('#chatStream'),
  transcriptScope: query<HTMLSelectElement>('#transcriptScope'),
  sendForm: query<HTMLFormElement>('#sendForm'),
  messageInput: query<HTMLTextAreaElement>('#messageInput'),
  sendBtn: query<HTMLButtonElement>('#sendBtn'),
  interruptBtn: query<HTMLButtonElement>('#interruptBtn'),
  timeline: query('#timeline'),
  workspacePath: query('#workspacePath'),
  fileTree: query('#fileTree'),
  uploadForm: query<HTMLFormElement>('#uploadForm'),
  referenceFiles: query<HTMLInputElement>('#referenceFiles'),
  uploadBtn: query<HTMLButtonElement>('#uploadBtn'),
  rawZipUploadForm: query<HTMLFormElement>('#rawZipUploadForm'),
  rawZipFile: query<HTMLInputElement>('#rawZipFile'),
  rawZipUploadBtn: query<HTMLButtonElement>('#rawZipUploadBtn'),
  stateBtn: query<HTMLButtonElement>('#stateBtn'),
  llmBtn: query<HTMLButtonElement>('#llmBtn'),
  clearAllLogsBtn: query<HTMLButtonElement>('#clearAllLogsBtn'),
  dialog: query<HTMLDialogElement>('#detailDialog'),
  dialogTitle: query('#dialogTitle'),
  dialogBody: query('#dialogBody'),
};

hydrateIcons();

els.leftRailToggle.addEventListener('click', () => {
  state.leftCollapsed = !state.leftCollapsed;
  renderShellState();
});
els.rightRailToggle.addEventListener('click', () => {
  state.rightCollapsed = !state.rightCollapsed;
  renderShellState();
});
els.messageInput.addEventListener('input', () => {
  autosizeComposer();
  updateSendButton();
});
els.messageInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!els.sendBtn.disabled) els.sendForm.requestSubmit();
  }
});
els.approveControlBtn.addEventListener('click', async () => {
  await runAction(async () => {
    const result = await postJson('/api/control/approve', {});
    state.bootstrap = result.bootstrap;
    render();
  });
});
els.rejectControlBtn.addEventListener('click', async () => {
  const reason = els.messageInput.value.trim();
  await runAction(async () => {
    const result = await postJson('/api/control/reject', { reason: reason || 'Rejected from web UI.' });
    state.bootstrap = result.bootstrap;
    render();
  });
});
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
  autosizeComposer();
  updateSendButton();
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
  state.loadingMessage = loadingPart('运行中');
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
  const files = [...(els.referenceFiles.files || [])];
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

els.rawZipUploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = els.rawZipFile.files?.[0];
  if (!file) return;
  await runAction(async () => {
    const form = new FormData();
    form.append('file', file);
    const result = await postForm('/api/data/raw/upload-zip', form);
    els.rawZipFile.value = '';
    state.bootstrap = result.bootstrap;
    showDetail('Raw Data Zip Uploaded', {
      archive: result.uploaded?.archive,
      targetDir: result.uploaded?.targetDir,
      extractedCount: result.uploaded?.extracted?.length || 0,
      extracted: result.uploaded?.extracted || [],
    });
    render();
  });
});

async function refresh() {
  const data = await fetchJson<Bootstrap>('/api/bootstrap');
  state.bootstrap = data;
  state.busy = Boolean(data.runtime?.running);
  state.lastRefreshAt = new Date();
  if (!data.runtime?.running) {
    state.loadingMessage = null;
    state.pendingParts = [];
  } else if (!state.loadingMessage) {
    state.loadingMessage = loadingPart('后端运行中，正在自动同步最新消息');
  }
  render();
}

function render() {
  const data = state.bootstrap;
  if (!data) {
    renderChat(emptyBootstrap());
    return;
  }

  const ws = data.state || {};
  const activeNode = ws.activeNode;
  els.statusText.innerHTML = statusPill(activeNode ? `Active: ${activeNode}` : 'Ready', activeNode ? 'active' : 'ready');
  els.modeText.textContent = data.dryRun ? `${ws.controlMode || ws.mode} / dry-run` : (ws.controlMode || ws.mode || '-');
  els.modelText.textContent = data.llmConfig?.config?.model || 'sdk-default';
  els.runtimeUvText.innerHTML = runtimePill(data.runtime?.workspaceUv);

  if (!state.selectedNodeType && data.nodeSpecs.length) {
    state.selectedNodeType = activeNode || data.nodeSpecs[0].type;
  }
  renderNodes(data.nodeSpecs, ws, data.nodes);
  renderNodeDetail(data.nodeSpecs, data.nodes);
  renderPendingControl(ws.pendingControl);
  renderTranscriptScope(data.nodes);
  renderChat(data);
  renderTimeline(data.timeline);
  renderFileTree(data.fileTree);
  renderDebugActions(Boolean(data.debugEnabled));
  updateControls(data);
  renderShellState();
  hydrateIcons();
}

function renderPendingControl(pending: JsonMap | null | undefined) {
  if (!pending) {
    els.pendingControlPanel.hidden = true;
    els.pendingControlBody.innerHTML = '';
    return;
  }
  els.pendingControlPanel.hidden = false;
  const args = pending.args || {};
  els.pendingControlBody.innerHTML = `
    <div class="control-kind">${escapeHtml(pending.kind || 'control')}</div>
    <div class="meta">${escapeHtml(pending.nodeType || '')} · ${formatTime(pending.createdAt)}</div>
    <div class="control-message">${escapeHtml(pending.message || '')}</div>
    <details>
      <summary>Arguments</summary>
      <pre>${escapeHtml(JSON.stringify(args, null, 2))}</pre>
    </details>
  `;
}

function renderTranscriptScope(nodes: JsonMap[]) {
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
  if (els.transcriptScope.innerHTML !== nextHtml) els.transcriptScope.innerHTML = nextHtml;
  els.transcriptScope.value = state.transcriptScope || current || 'all';
}

function renderDebugActions(enabled: boolean) {
  for (const element of document.querySelectorAll<HTMLElement>('.debug-only')) {
    element.hidden = !enabled;
  }
}

function renderNodes(specs: JsonMap[], ws: JsonMap, sessions: JsonMap[]) {
  const latestByType = new Map<string, JsonMap>();
  for (const session of sessions) latestByType.set(session.nodeType, session);
  const completedNodes = ws.completedNodes || [];

  els.nodeList.innerHTML = specs.map((spec, index) => {
    const session = latestByType.get(spec.type);
    const active = ws.activeNode === spec.type;
    const done = completedNodes.includes(spec.type);
    const failed = !done && session?.status === 'failed';
    const status = active ? 'active' : done ? 'done' : failed ? 'failed' : 'pending';
    return `
      <button class="node-item ${state.selectedNodeType === spec.type ? 'selected' : ''}" data-node="${escapeHtml(spec.type)}">
        <span class="node-index">${index + 1}</span>
        <span class="node-copy">
          <span class="node-name">${escapeHtml(spec.type)}</span>
          <span class="meta">${escapeHtml(spec.phase)} · ${escapeHtml(spec.purpose)}</span>
        </span>
        <span class="badge ${status}">${statusIcon(status)}${status}</span>
      </button>
    `;
  }).join('');

  for (const item of els.nodeList.querySelectorAll<HTMLElement>('.node-item')) {
    item.addEventListener('click', () => {
      state.selectedNodeType = item.dataset.node || null;
      render();
    });
  }
}

function renderNodeDetail(specs: JsonMap[], nodes: JsonMap[]) {
  const type = state.selectedNodeType;
  const spec = specs.find((candidate) => candidate.type === type);
  if (!spec) {
    els.nodeDetail.innerHTML = emptyState('请选择一个 node。', 'Info');
    return;
  }
  const sessions = nodes.filter((node) => node.nodeType === type).slice().reverse();
  const produced = unique([
    ...(spec.produces || []),
    ...sessions.flatMap((node) => node.outputPaths || []),
  ]);
  els.nodeDetail.innerHTML = `
    <div class="node-detail-title">${escapeHtml(spec.type)}</div>
    <div class="meta">${escapeHtml(spec.purpose)}</div>
    <div class="detail-section-title">Artifacts</div>
    ${produced.length ? `<div class="artifact-list">${produced.map((path) => `
      <button class="artifact-item" data-path="${escapeHtml(path)}"><span data-icon="File"></span><span>${escapeHtml(path)}</span></button>
    `).join('')}</div>` : emptyState('暂无节点产物。', 'File')}
    <div class="detail-section-title">Sessions</div>
    ${sessions.length ? `<div class="session-list">${sessions.map((node) => `
      <button class="session-item" data-session="${escapeHtml(node.id)}">
        <span class="session-title">${escapeHtml(node.status)} · ${formatTime(node.startedAt)}</span>
        <span class="meta">${escapeHtml(node.summary || node.rationale || '')}</span>
      </button>
    `).join('')}</div>` : emptyState('暂无 node session。', 'Activity')}
  `;

  for (const item of els.nodeDetail.querySelectorAll<HTMLElement>('.session-item')) {
    item.addEventListener('click', async () => {
      const log = await fetchJson(`/api/nodes/${item.dataset.session}/log`);
      showDetail(`Node Log ${item.dataset.session}`, log);
    });
  }
  for (const item of els.nodeDetail.querySelectorAll<HTMLElement>('.artifact-item')) {
    item.addEventListener('click', async () => showWorkspaceFile(item.dataset.path || ''));
  }
}

function renderChat(data: Bootstrap) {
  const wasNearBottom = els.chatStream.scrollHeight - els.chatStream.scrollTop - els.chatStream.clientHeight < 160;
  const parts = collectTranscriptParts(data);
  const visibleParts = normalizeChatParts(parts);
  if (!visibleParts.length) {
    els.chatStream.innerHTML = `
      <div class="welcome-state">
        <div class="welcome-orbit"><span data-icon="Sparkles"></span></div>
        <h3>Ready for a time-series workflow</h3>
        <p>发送任务后，orchestrator 会读取 workspace、规划节点并把执行过程同步到这里。</p>
      </div>
    `;
    return;
  }
  els.chatStream.innerHTML = visibleParts.map((part) => messageHtml(part)).join('');
  bindToolCards();
  if (wasNearBottom || state.loadingMessage) {
    els.chatStream.scrollTop = els.chatStream.scrollHeight;
  }
}

function messageHtml(part: JsonMap) {
  const role = part.role || 'system';
  const roleClass = ['user', 'assistant', 'system', 'tool'].includes(role) ? role : 'system';
  const text = part.displayText || part.text || summarizeRaw(part.raw) || '';
  const source = part.sourceLabel ? `${part.sourceLabel} · ` : '';
  if (part.type === 'loading') {
    return `
      <article class="message assistant loading">
        <div class="message-role"><span data-icon="Loader2"></span>${escapeHtml(source)}assistant · running · ${formatTime(part.timestamp)}</div>
        <div class="message-text loading-line"><span>${escapeHtml(part.text)}</span></div>
      </article>
    `;
  }
  if (part.type === 'tool_use' || part.type === 'tool_result') {
    const summary = toolSummary(part);
    const detail = part.displayText || part.text || summarizeRaw(part.raw) || '';
    const toolName = toolNameForPart(part);
    const done = part.type === 'tool_result';
    return `
      <article class="message ${escapeHtml(roleClass)} tool-collapsed">
        <button class="tool-card" type="button" data-tool-toggle>
          <span class="tool-status ${done ? 'done' : 'running'}"><span data-icon="${done ? 'Check' : 'TerminalSquare'}"></span></span>
          <span class="tool-copy">
            <span class="tool-title">${escapeHtml(summary)}</span>
            <span class="tool-meta">${escapeHtml(source)}${escapeHtml(toolName)} · ${escapeHtml(part.type || 'tool')} · ${formatTime(part.timestamp)}</span>
          </span>
          <span class="tool-chevron" data-icon="ChevronRight"></span>
        </button>
        <pre class="tool-detail" hidden>${escapeHtml(detail)}</pre>
      </article>
    `;
  }
  return `
    <article class="message ${escapeHtml(roleClass)}">
      <div class="message-role"><span data-icon="${role === 'user' ? 'Send' : role === 'assistant' ? 'Bot' : 'Info'}"></span>${escapeHtml(source)}${escapeHtml(role)} · ${escapeHtml(part.type || 'text')} · ${formatTime(part.timestamp)}</div>
      <div class="message-text markdown-body">${renderMarkdown(text)}</div>
    </article>
  `;
}

function toolSummary(part: JsonMap) {
  if (part.type === 'tool_use') {
    const name = part.name || part.raw?.message?.content?.find?.((block: JsonMap) => block.type === 'tool_use')?.name || 'tool';
    const input = part.input || part.raw?.message?.content?.find?.((block: JsonMap) => block.type === 'tool_use')?.input;
    const hint = input && typeof input === 'object' ? Object.keys(input).slice(0, 3).join(', ') : '';
    return hint ? `调用工具：${name} (${hint})` : `调用工具：${name}`;
  }
  const text = part.displayText || part.text || '';
  const firstLine = text.split('\n').find((line: string) => line.trim()) || '工具结果';
  return firstLine.length > 120 ? `${firstLine.slice(0, 117)}...` : firstLine;
}

function toolNameForPart(part: JsonMap) {
  if (part.name) return part.name;
  const toolBlock = part.raw?.message?.content?.find?.((block: JsonMap) => block.type === 'tool_use');
  return toolBlock?.name || part.raw?.tool_name || 'tool';
}

function collectTranscriptParts(data: Bootstrap): JsonMap[] {
  const scope = state.transcriptScope || 'all';
  const mainParts: JsonMap[] = (data.mainParts || []).map((part: JsonMap) => ({
    ...part,
    sourceLabel: 'main',
    sortKey: `${part.timestamp || ''}:main:${part.id || ''}`,
  }));
  const loggedUserTexts = new Set(mainParts.filter((part) => part.role === 'user' && part.text).map((part) => part.text));
  const nodeParts: JsonMap[] = [];
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
    .map((part) => ({ ...part, sortKey: `${part.timestamp || ''}:pending:${part.id || ''}` }));
  const loadingParts = state.loadingMessage ? [{
    ...state.loadingMessage,
    sortKey: `${new Date().toISOString()}:loading:${state.loadingMessage.id}`,
  }] : [];
  if (scope === 'main') return [...mainParts, ...pendingParts, ...loadingParts].sort(sortByKey);
  if (scope.startsWith('node:')) {
    const nodeId = scope.slice('node:'.length);
    return nodeParts.filter((part) => part.nodeSessionId === nodeId || part.sortKey.includes(`:node:${nodeId}:`)).sort(sortByKey);
  }
  return [...mainParts, ...nodeParts, ...pendingParts, ...loadingParts].sort(sortByKey);
}

function normalizeChatParts(parts: JsonMap[]): JsonMap[] {
  return parts
    .map((part: JsonMap) => ({ ...part, displayText: displayTextForPart(part) }))
    .filter((part: JsonMap) => {
      if (part.type === 'loading') return true;
      if (!part.displayText.trim()) return false;
      if (part.role === 'system' && part.type === 'raw' && ['init'].includes(part.displayText.trim())) return false;
      if (part.role === 'system' && part.type === 'result' && part.raw?.is_error !== true) return false;
      return true;
    });
}

function displayTextForPart(part: JsonMap) {
  if (part.type === 'loading') return part.text || '运行中';
  if (part.type === 'tool_use') {
    const name = part.name || part.raw?.message?.content?.find?.((block: JsonMap) => block.type === 'tool_use')?.name || 'tool';
    const input = part.input || part.raw?.message?.content?.find?.((block: JsonMap) => block.type === 'tool_use')?.input;
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
  return part.text || '';
}

function renderTimeline(events: JsonMap[]) {
  if (!events.length) {
    els.timeline.innerHTML = emptyState('暂无流程记录。', 'Clock3');
    return;
  }
  els.timeline.innerHTML = events.slice(-80).reverse().map((event) => `
    <button class="timeline-item" type="button">
      <span class="timeline-dot"></span>
      <span class="timeline-copy">
        <span class="timeline-type">${escapeHtml(event.type)} ${event.nodeType ? `· ${escapeHtml(event.nodeType)}` : ''}</span>
        <span class="meta">${formatTime(event.timestamp)}</span>
        <span>${escapeHtml(event.message || '')}</span>
      </span>
    </button>
  `).join('');
}

function renderFileTree(fileTree: Bootstrap['fileTree']) {
  if (!fileTree?.tree) {
    els.workspacePath.textContent = '';
    els.fileTree.innerHTML = emptyState('暂无 workspace 文件。', 'FolderTree');
    return;
  }
  els.workspacePath.textContent = fileTree.root || '';
  els.fileTree.innerHTML = renderTreeNode(fileTree.tree, true);
  if (fileTree.truncated) els.fileTree.insertAdjacentHTML('beforeend', emptyState('文件数量过多，已截断显示。', 'AlertTriangle'));
  for (const item of els.fileTree.querySelectorAll<HTMLElement>('.file-node.file')) {
    item.addEventListener('click', async () => showWorkspaceFile(item.dataset.path || ''));
  }
}

function renderTreeNode(node: FileTreeNode | undefined, root = false): string {
  if (!node) return '';
  if (node.kind === 'dir') {
    const open = root || ['user', 'artifacts', 'data', 'tools', 'runs', 'reports'].includes(node.path);
    return `
      <details class="file-dir" ${open ? 'open' : ''}>
        <summary><span data-icon="ChevronRight"></span><span>${escapeHtml(node.name || 'workspace')}</span></summary>
        <div class="file-children">
          ${(node.children || []).map((child) => renderTreeNode(child)).join('')}
        </div>
      </details>
    `;
  }
  return `
    <button class="file-node file" data-path="${escapeHtml(node.path)}">
      <span class="file-label"><span data-icon="File"></span><span>${escapeHtml(node.name)}</span></span>
      <span class="file-size">${formatBytes(node.size || 0)}</span>
    </button>
  `;
}

async function showWorkspaceFile(path: string) {
  if (!path) return;
  try {
    const file = await fetchJson<JsonMap>(`/api/files/content?path=${encodeURIComponent(path)}`);
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
    showDetail(path, { message: error instanceof Error ? error.message : String(error) });
  }
}

function updateControls(data: Bootstrap) {
  const ws = data.state || {};
  const activeSession = getActiveNodeSession(data);
  const activePaused = Boolean(ws.activeNode && activeSession?.status === 'paused');
  const activeRunning = Boolean(ws.activeNode && activeSession?.status === 'running');
  const pendingControl = Boolean(ws.pendingControl);
  els.sendBtn.disabled = state.busy || (Boolean(ws.activeNode) && !activePaused);
  els.messageInput.disabled = state.busy || (Boolean(ws.activeNode) && !activePaused);
  els.messageInput.placeholder = activePaused
    ? '补充说明后点击 Resume，当前 node 会继续执行'
    : '向 orchestrator 发送消息';
  els.interruptBtn.disabled = !state.busy && !activeRunning;
  els.uploadBtn.disabled = state.busy;
  els.rawZipUploadBtn.disabled = state.busy;
  els.approveControlBtn.disabled = state.busy || !pendingControl;
  els.rejectControlBtn.disabled = state.busy || !pendingControl;
  updateSendButton(activePaused);
  autosizeComposer();
}

function getActiveNodeSession(data: Bootstrap) {
  const ws = data.state || {};
  if (!ws.activeNodeSessionId) return null;
  return (data.nodes || []).find((node) => node.id === ws.activeNodeSessionId) || null;
}

async function runAction(fn: () => Promise<void>) {
  state.busy = true;
  render();
  try {
    await fn();
  } catch (error) {
    showDetail('Error', { message: error instanceof Error ? error.message : String(error) });
  } finally {
    state.busy = false;
    render();
  }
}

async function runStreamingAction(fn: () => Promise<void>) {
  state.busy = true;
  render();
  await nextPaint();
  try {
    await fn();
  } catch (error) {
    showDetail('Error', { message: error instanceof Error ? error.message : String(error) });
  } finally {
    try {
      const data = await fetchJson<Bootstrap>('/api/bootstrap');
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

function emptyBootstrap(): Bootstrap {
  return {
    state: { activeNode: null, completedNodes: [] },
    mainParts: [],
    nodePartsById: {},
    nodes: [],
    nodeSpecs: [],
    timeline: [],
    fileTree: null,
    runtime: { running: false, workspaceUv: null },
  };
}

function formatRuntimeUv(runtimeUv: JsonMap | null | undefined) {
  if (!runtimeUv) return '-';
  const runtimeState = runtimeUv.state || 'unknown';
  if (runtimeState === 'ready') return `ready · ${runtimeUv.pythonVersion || 'python'}`;
  if (runtimeState === 'skipped') return 'skipped';
  if (runtimeState === 'failed') return 'failed';
  return runtimeState;
}

function runtimePill(runtimeUv: JsonMap | null | undefined) {
  const text = formatRuntimeUv(runtimeUv);
  const tone = text.startsWith('ready') ? 'ready' : text === 'failed' ? 'failed' : 'pending';
  return `<span class="mini-pill ${tone}">${escapeHtml(text)}</span>`;
}

function statusPill(text: string, tone: string) {
  return `<span class="mini-pill ${tone}">${escapeHtml(text)}</span>`;
}

function statusIcon(status: string) {
  const icon = status === 'done' ? 'Check' : status === 'active' ? 'Loader2' : status === 'failed' ? 'XCircle' : 'Circle';
  return `<span data-icon="${icon}"></span>`;
}

function emptyState(text: string, icon = 'Info') {
  return `<div class="empty"><span data-icon="${icon}"></span><span>${escapeHtml(text)}</span></div>`;
}

function renderMarkdown(text: string) {
  const html = marked.parse(text || '', { async: false }) as string;
  return DOMPurify.sanitize(html);
}

function bindToolCards() {
  for (const button of els.chatStream.querySelectorAll<HTMLButtonElement>('[data-tool-toggle]')) {
    button.addEventListener('click', () => {
      const detail = button.nextElementSibling as HTMLElement | null;
      if (!detail) return;
      const expanded = detail.hidden === true;
      detail.hidden = !expanded;
      button.classList.toggle('expanded', expanded);
    });
  }
}

function renderShellState() {
  document.body.classList.toggle('left-collapsed', state.leftCollapsed);
  document.body.classList.toggle('right-collapsed', state.rightCollapsed);
  els.leftRailToggle.title = state.leftCollapsed ? '展开左栏' : '折叠左栏';
  els.rightRailToggle.title = state.rightCollapsed ? '展开右栏' : '折叠右栏';
  els.leftRailToggle.innerHTML = `<span data-icon="${state.leftCollapsed ? 'ChevronRight' : 'ChevronLeft'}"></span>`;
  els.rightRailToggle.innerHTML = `<span data-icon="${state.rightCollapsed ? 'ChevronLeft' : 'ChevronRight'}"></span>`;
  hydrateIcons(els.leftRailToggle);
  hydrateIcons(els.rightRailToggle);
}

function autosizeComposer() {
  els.messageInput.style.height = 'auto';
  const maxHeight = Math.round(window.innerHeight * 0.3);
  els.messageInput.style.height = `${Math.min(els.messageInput.scrollHeight, maxHeight)}px`;
}

function updateSendButton(activePaused = false) {
  const hasText = Boolean(els.messageInput.value.trim());
  const canSend = hasText && !els.messageInput.disabled && !state.busy;
  els.sendBtn.disabled = !canSend;
  const icon = state.busy ? 'Square' : activePaused ? 'Play' : 'ArrowUp';
  els.sendBtn.innerHTML = `<span data-icon="${icon}"></span>`;
  els.sendBtn.title = activePaused ? '继续当前 node' : '发送';
  els.sendBtn.classList.toggle('ready', canSend);
  hydrateIcons(els.sendBtn);
}

function loadingPart(text: string) {
  return {
    id: `loading-${Date.now()}`,
    timestamp: new Date().toISOString(),
    role: 'assistant',
    type: 'loading',
    text,
    sourceLabel: 'harness',
  };
}

function nextPaint() {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

async function interruptCurrent(reason: string) {
  els.interruptBtn.disabled = true;
  try {
    const result = await postJson('/api/interrupt', { reason });
    state.bootstrap = result.bootstrap;
    state.busy = false;
    state.loadingMessage = null;
    render();
  } catch (error) {
    showDetail('Interrupt Error', { message: error instanceof Error ? error.message : String(error) });
  }
}

async function fetchJson<T = any>(url: string): Promise<T> {
  const response = await fetch(url);
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

async function postJson<T = any>(url: string, body: JsonMap): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

async function postForm<T = any>(url: string, body: FormData): Promise<T> {
  const response = await fetch(url, { method: 'POST', body });
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

async function readJsonResponse(response: Response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

function errorMessage(payload: any, response: Response) {
  if (payload?.error) return payload.error;
  if (payload?.detail) return typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
  if (payload?.message) return payload.message;
  return response.statusText || `HTTP ${response.status}`;
}

function showDetail(title: string, value: any) {
  els.dialogTitle.textContent = title;
  els.dialogBody.textContent = JSON.stringify(value ?? null, null, 2);
  els.dialog.showModal();
}

function showTextDetail(title: string, text: string) {
  els.dialogTitle.textContent = title;
  els.dialogBody.textContent = text;
  els.dialog.showModal();
}

function summarizeRaw(raw: any) {
  if (!raw) return '';
  if (raw.subtype) return raw.subtype;
  if (raw.type) return raw.type;
  return JSON.stringify(raw);
}

function formatTime(value: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function unique(values: any[]) {
  return [...new Set(values.filter(Boolean))];
}

function sortByKey(a: JsonMap, b: JsonMap) {
  return String(a.sortKey || '').localeCompare(String(b.sortKey || ''));
}

function escapeHtml(value: any) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function query<T extends Element = HTMLElement>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing element: ${selector}`);
  return element;
}

function hydrateIcons(root: ParentNode = document) {
  for (const holder of root.querySelectorAll<HTMLElement>('[data-icon]')) {
    if (holder.dataset.iconHydrated === 'true') continue;
    const name = holder.dataset.icon || '';
    const iconNode = iconMap[name];
    if (!iconNode) continue;
    const svg = createIcon(iconNode);
    holder.replaceChildren(svg);
    holder.dataset.iconHydrated = 'true';
  }
}

function createIcon(iconNode: IconNode) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  for (const [tag, attrs] of iconNode) {
    const child = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs)) child.setAttribute(key, String(value));
    svg.appendChild(child);
  }
  return svg;
}

setInterval(() => {
  if (state.bootstrap?.runtime?.running || state.busy) {
    refresh().catch(() => undefined);
  }
}, 2500);

refresh().catch((error) => showDetail('Startup Error', { message: error instanceof Error ? error.message : String(error) }));
