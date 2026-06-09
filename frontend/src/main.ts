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
  Network,
  Pause,
  Play,
  RefreshCw,
  Send,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
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
  runtimeSettings?: JsonMap;
  knowledgeGraph?: JsonMap;
  knowledgeBaseSummary?: JsonMap;
  knowledgeGraphParts?: JsonMap[];
  dryRun?: boolean;
  debugEnabled?: boolean;
  runtime?: {
    running?: boolean;
    knowledgeGraphRunning?: boolean;
    workspaceUv?: JsonMap | null;
  };
  knowledgeGraphBuild?: JsonMap;
  knowledgeGraphLlmConfig?: JsonMap;
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
  view: (window.location.pathname === '/knowledge-graph' ? 'knowledgeGraph' : 'chat') as 'chat' | 'knowledgeGraph',
  selectedGraphNodeId: null as string | null,
  selectedKnowledgeBaseKind: null as string | null,
  knowledgeBaseCards: null as JsonMap | null,
  knowledgeBaseCardsBusy: false,
  expandedToolPartIds: new Set<string>(),
  candidateSaveTimer: 0,
  knowledgeQuestion: '',
  knowledgeAnswer: null as JsonMap | null,
  knowledgeQueryBusy: false,
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

    <div class="main-left-content">
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
    </div>

    <div class="graph-left-content">
      <section class="panel">
        <div class="panel-heading">
          <span data-icon="Settings2"></span>
          <span>Builder Settings</span>
        </div>
        <div id="graphBuildStatus" class="graph-build-status"></div>
        <div class="graph-left-actions">
          <button id="buildGraphBtn" type="button"><span data-icon="RefreshCw"></span><span>Build</span></button>
          <button id="continueGraphBtn" type="button" class="secondary"><span data-icon="Play"></span><span>Continue</span></button>
          <button id="pauseGraphBtn" type="button" class="danger ghost"><span data-icon="Pause"></span><span>Pause</span></button>
          <button id="backToChatBtn" type="button" class="ghost"><span data-icon="ChevronLeft"></span><span>Main</span></button>
        </div>
        <label>
          <span>Extraction Depth</span>
          <input id="graphExtractionDepthInput" type="number" min="1" max="4" step="1" />
        </label>
        <label>
          <span>Auth</span>
          <select id="graphAuthMode">
            <option value="manual">manual</option>
            <option value="sdk-default">sdk-default</option>
          </select>
        </label>
        <label>
          <span>Protocol</span>
          <select id="graphProtocol">
            <option value="">auto</option>
            <option value="anthropic">anthropic</option>
            <option value="openai-compat">openai-compat</option>
          </select>
        </label>
        <label>
          <span>Model</span>
          <input id="graphModelInput" type="text" placeholder="inherits main model" />
        </label>
        <label>
          <span>Base URL</span>
          <input id="graphBaseUrlInput" type="text" placeholder="inherits main endpoint" />
        </label>
        <label>
          <span>API Key</span>
          <input id="graphApiKeyInput" type="password" placeholder="leave blank to keep current" />
        </label>
        <button id="saveGraphLlmBtn" type="button" class="secondary full-width"><span data-icon="Check"></span><span>Save builder LLM</span></button>
      </section>

      <section class="panel">
        <div class="panel-heading">
          <span data-icon="Gauge"></span>
          <span>Knowledge Base</span>
        </div>
        <div class="knowledge-summary" id="knowledgeSummary"></div>
        <div class="knowledge-card-list" id="knowledgeCards"></div>
      </section>
    </div>
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
        <button id="clearAllLogsBtn" type="button" class="danger ghost debug-only"><span data-icon="Trash2"></span><span>Reset Workspace</span></button>
      </div>
    </header>

    <section id="chatStream" class="chat-stream"></section>
    <section id="knowledgeGraphView" class="knowledge-graph-view" hidden>
      <div class="graph-header">
        <div class="graph-title-block">
          <div class="eyebrow"><span data-icon="Network"></span><span>Knowledge Graph</span></div>
          <h2 id="graphTitle">Reference Knowledge</h2>
        </div>
      </div>
      <section class="builder-trace-panel">
        <div class="panel-heading">
          <span data-icon="TerminalSquare"></span>
          <span>Builder Agent Trace</span>
        </div>
        <div id="builderTrace" class="builder-trace"></div>
      </section>
      <div class="graph-layout">
        <div id="graphCanvas" class="graph-canvas"></div>
        <section id="graphInspector" class="graph-inspector"></section>
      </div>
    </section>

    <form id="sendForm" class="composer">
      <div class="composer-shell">
        <textarea id="messageInput" rows="1" placeholder="向 orchestrator 发送消息"></textarea>
        <button id="sendBtn" type="submit" class="send-round" title="发送" disabled><span data-icon="ArrowUp"></span></button>
      </div>
    </form>
  </main>

  <aside class="right-rail">
    <section class="panel">
      <div class="panel-heading">
        <span data-icon="SlidersHorizontal"></span>
        <span>Runtime Controls</span>
      </div>
      <label>
        <span>Iterative candidates (k)</span>
        <input id="candidateCountInput" type="number" min="1" max="8" step="1" />
      </label>
      <button id="knowledgeGraphBtn" type="button" class="secondary full-width"><span data-icon="Network"></span><span>Knowledge Graph</span></button>
    </section>
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
  Network,
  Pause,
  Play,
  RefreshCw,
  Send,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
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
  knowledgeGraphView: query<HTMLElement>('#knowledgeGraphView'),
  graphTitle: query('#graphTitle'),
  graphCanvas: query('#graphCanvas'),
  graphInspector: query('#graphInspector'),
  graphBuildStatus: query('#graphBuildStatus'),
  graphAuthMode: query<HTMLSelectElement>('#graphAuthMode'),
  graphProtocol: query<HTMLSelectElement>('#graphProtocol'),
  graphModelInput: query<HTMLInputElement>('#graphModelInput'),
  graphApiKeyInput: query<HTMLInputElement>('#graphApiKeyInput'),
  graphBaseUrlInput: query<HTMLInputElement>('#graphBaseUrlInput'),
  graphExtractionDepthInput: query<HTMLInputElement>('#graphExtractionDepthInput'),
  saveGraphLlmBtn: query<HTMLButtonElement>('#saveGraphLlmBtn'),
  buildGraphBtn: query<HTMLButtonElement>('#buildGraphBtn'),
  continueGraphBtn: query<HTMLButtonElement>('#continueGraphBtn'),
  pauseGraphBtn: query<HTMLButtonElement>('#pauseGraphBtn'),
  knowledgeSummary: query('#knowledgeSummary'),
  knowledgeCards: query('#knowledgeCards'),
  builderTrace: query('#builderTrace'),
  backToChatBtn: query<HTMLButtonElement>('#backToChatBtn'),
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
  candidateCountInput: query<HTMLInputElement>('#candidateCountInput'),
  knowledgeGraphBtn: query<HTMLButtonElement>('#knowledgeGraphBtn'),
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
els.backToChatBtn.addEventListener('click', () => {
  state.view = 'chat';
  history.pushState({}, '', '/');
  render();
});
els.buildGraphBtn.addEventListener('click', async () => {
  await postJson('/api/knowledge-graph/build', { trigger: 'manual' });
  await refresh();
});
els.continueGraphBtn.addEventListener('click', async () => {
  await postJson('/api/knowledge-graph/continue', {});
  await refresh();
});
els.pauseGraphBtn.addEventListener('click', async () => {
  const result = await postJson('/api/knowledge-graph/pause', { reason: 'Paused from knowledge graph UI.' });
  state.bootstrap = result.bootstrap;
  render();
});
els.saveGraphLlmBtn.addEventListener('click', async () => {
  await saveKnowledgeGraphLlmConfig();
});
els.knowledgeGraphBtn.addEventListener('click', async () => {
  state.view = 'knowledgeGraph';
  history.pushState({}, '', '/knowledge-graph');
  const graph = await fetchJson<JsonMap>('/api/knowledge-graph');
  if (state.bootstrap) state.bootstrap.knowledgeGraph = graph;
  render();
});
window.addEventListener('popstate', () => {
  state.view = window.location.pathname === '/knowledge-graph' ? 'knowledgeGraph' : 'chat';
  render();
});
els.candidateCountInput.addEventListener('input', () => {
  window.clearTimeout(state.candidateSaveTimer);
  state.candidateSaveTimer = window.setTimeout(() => {
    saveCandidateCount().catch((error) => showDetail('Runtime Settings Error', { message: error instanceof Error ? error.message : String(error) }));
  }, 350);
});
els.candidateCountInput.addEventListener('change', async () => {
  window.clearTimeout(state.candidateSaveTimer);
  await saveCandidateCount();
});
els.graphExtractionDepthInput.addEventListener('change', async () => {
  await saveGraphExtractionDepth();
});
async function saveCandidateCount() {
  const value = Number.parseInt(els.candidateCountInput.value, 10);
  if (!Number.isFinite(value)) return;
  const result = await postJson('/api/runtime-settings', { iterativeCandidateCount: value });
  state.bootstrap = result.bootstrap;
  state.busy = Boolean(result.bootstrap?.runtime?.running);
  render();
}
async function saveGraphExtractionDepth() {
  const value = Number.parseInt(els.graphExtractionDepthInput.value, 10);
  if (!Number.isFinite(value)) return;
  const result = await postJson('/api/runtime-settings', { knowledgeGraphExtractionDepth: value });
  state.bootstrap = result.bootstrap;
  state.busy = Boolean(result.bootstrap?.runtime?.running);
  render();
}
async function saveKnowledgeGraphLlmConfig() {
  const result = await postJson('/api/knowledge-graph/llm-config', {
    authMode: els.graphAuthMode.value,
    protocol: els.graphProtocol.value || undefined,
    model: els.graphModelInput.value.trim(),
    apiKey: els.graphApiKeyInput.value.trim() || undefined,
    baseUrl: els.graphBaseUrlInput.value.trim(),
  });
  state.bootstrap = result.bootstrap;
  els.graphApiKeyInput.value = '';
  render();
}
els.interruptBtn.addEventListener('click', async () => {
  const reason = els.messageInput.value.trim();
  await interruptCurrent(reason || 'User interrupted from web UI.');
});
els.clearAllLogsBtn.addEventListener('click', async () => {
  if (!confirm('这将重置整个工作区，删除 references、knowledge graph、日志、运行产物、报告和临时工具。设置中的 API key、endpoint、model 与 k 会保留。是否继续？')) return;
  const typed = prompt('二次确认：请输入 RESET 来确认重置工作区。');
  if (typed !== 'RESET') return;
  await runAction(async () => {
    const result = await postJson('/api/debug/clear-logs', { scope: 'all', confirmReset: true });
    state.bootstrap = result.bootstrap;
    state.transcriptScope = 'main';
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
    const result = await postSend(text);
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

async function livePoll() {
  const data = await fetchJson<Bootstrap>('/api/live');
  state.bootstrap = data;
  state.busy = Boolean(data.runtime?.running);
  state.lastRefreshAt = new Date();
  if (!data.runtime?.running) {
    state.loadingMessage = null;
    state.pendingParts = [];
  } else if (!state.loadingMessage) {
    state.loadingMessage = loadingPart('后端运行中，正在自动同步最新消息');
  }
  liveRender(data);
}

function liveRender(data: Bootstrap) {
  const ws = data.state || {};
  const activeNode = ws.activeNode;

  // Lightweight status updates (text-only, no DOM rebuild)
  els.statusText.innerHTML = statusPill(activeNode ? `Active: ${activeNode}` : 'Ready', activeNode ? 'active' : 'ready');
  els.modeText.textContent = data.dryRun ? `${ws.controlMode || ws.mode} / dry-run` : (ws.controlMode || ws.mode || '-');
  els.modelText.textContent = data.llmConfig?.config?.model || 'sdk-default';
  els.runtimeUvText.innerHTML = runtimePill(data.runtime?.workspaceUv);

  if (!state.selectedNodeType && data.nodeSpecs.length) {
    state.selectedNodeType = activeNode || data.nodeSpecs[0].type;
  }

  // Live-updating panels — full render with scroll preservation
  renderPendingControl(ws.pendingControl);
  renderTranscriptScope(data.nodes);
  renderChat(data);
  renderTimeline(data.timeline);
  renderRuntimeSettings(data.runtimeSettings || ws.runtimeSettings);
  updateControls(data);

  // Knowledge graph view extras (builder status + trace)
  if (state.view === 'knowledgeGraph') {
    renderKnowledgeGraphBuilder(data);
    renderBuilderTrace(data.knowledgeGraphParts || []);
  }

  renderShellState();
  renderViewState();
  hydrateIcons();
}

function render() {
  const data = state.bootstrap;
  if (!data) {
    renderChat(emptyBootstrap());
    renderViewState();
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
  renderKnowledgeGraph(data.knowledgeGraph);
  renderKnowledgeGraphBuilder(data);
  renderKnowledgeWorkbench(data);
  renderBuilderTrace(data.knowledgeGraphParts || []);
  renderViewState();
  renderTimeline(data.timeline);
  renderFileTree(data.fileTree);
  renderRuntimeSettings(data.runtimeSettings || ws.runtimeSettings);
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
  const savedScroll = els.chatStream.scrollTop;
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
  // Preserve scroll: auto-scroll only when user was already near bottom
  if (wasNearBottom) {
    els.chatStream.scrollTop = els.chatStream.scrollHeight;
  } else if (savedScroll < els.chatStream.scrollHeight) {
    els.chatStream.scrollTop = Math.min(savedScroll, els.chatStream.scrollHeight - els.chatStream.clientHeight);
  }
}

function renderRuntimeSettings(settings: JsonMap | null | undefined) {
  const value = settings?.iterativeCandidateCount ?? 3;
  if (els.candidateCountInput.value !== String(value)) els.candidateCountInput.value = String(value);
  const graphDepth = settings?.knowledgeGraphExtractionDepth ?? 2;
  if (els.graphExtractionDepthInput.value !== String(graphDepth)) els.graphExtractionDepthInput.value = String(graphDepth);
}

function renderViewState() {
  const graphMode = state.view === 'knowledgeGraph';
  els.chatStream.hidden = graphMode;
  els.knowledgeGraphView.hidden = !graphMode;
  els.sendForm.hidden = graphMode;
  els.transcriptScope.disabled = graphMode;
  query('#mainTitle').textContent = graphMode ? 'Knowledge Graph' : 'Orchestrator';
  document.body.classList.toggle('knowledge-page', graphMode);
}

function renderKnowledgeGraphBuilder(data: Bootstrap) {
  const build = data.knowledgeGraphBuild || {};
  const config = data.knowledgeGraphLlmConfig?.config || {};
  const running = Boolean(data.runtime?.knowledgeGraphRunning || build.running);
  const canContinue = !running && ['paused', 'failed'].includes(String(build.status || ''));
  els.graphBuildStatus.innerHTML = `
    <span class="mini-pill ${build.status === 'failed' ? 'failed' : running ? 'active' : build.status === 'completed' ? 'ready' : 'pending'}">
      ${running ? '<span data-icon="Loader2"></span>' : ''}
      ${escapeHtml(running ? 'running' : build.status || 'idle')}
    </span>
    <span class="meta">${escapeHtml(build.message || '')}</span>
  `;
  if (els.graphAuthMode.value !== (config.authMode || 'manual')) els.graphAuthMode.value = config.authMode || 'manual';
  if (els.graphProtocol.value !== (config.protocol || '')) els.graphProtocol.value = config.protocol || '';
  if (els.graphModelInput.value !== (config.model || '')) els.graphModelInput.value = config.model || '';
  if (els.graphBaseUrlInput.value !== (config.baseUrl || '')) els.graphBaseUrlInput.value = config.baseUrl || '';
  els.buildGraphBtn.disabled = running;
  els.continueGraphBtn.disabled = !canContinue;
  els.pauseGraphBtn.disabled = !running;
  els.graphExtractionDepthInput.disabled = running;
  els.saveGraphLlmBtn.disabled = false;
}

function renderKnowledgeWorkbench(data: Bootstrap) {
  const summary = data.knowledgeBaseSummary || data.knowledgeGraph?.summary || {};
  els.knowledgeSummary.innerHTML = `
    <div class="knowledge-depth">Depth ${escapeHtml(summary.extractionDepth ?? data.runtimeSettings?.knowledgeGraphExtractionDepth ?? 2)}</div>
    ${knowledgeStatHtml('knowledge', summary.knowledgeCount ?? 0, 'Knowledge')}
    ${knowledgeStatHtml('evidence', summary.evidenceCount ?? 0, 'Evidence')}
    ${knowledgeStatHtml('classes', summary.classCount ?? 0, 'Classes')}
    ${knowledgeStatHtml('relations', summary.relationCount ?? 0, 'Relations')}
  `;
  for (const item of els.knowledgeSummary.querySelectorAll<HTMLButtonElement>('[data-kb-kind]')) {
    item.addEventListener('click', async () => {
      await openKnowledgeBaseCards(item.dataset.kbKind || '');
    });
  }
  renderKnowledgeBaseCards();
}

function knowledgeStatHtml(kind: string, count: any, label: string) {
  const selected = state.selectedKnowledgeBaseKind === kind ? ' selected' : '';
  return `
    <button class="knowledge-stat${selected}" type="button" data-kb-kind="${escapeHtml(kind)}">
      <span>${escapeHtml(count)}</span>
      <span>${escapeHtml(label)}</span>
    </button>
  `;
}

async function openKnowledgeBaseCards(kind: string) {
  if (!kind) return;
  state.selectedKnowledgeBaseKind = kind;
  state.knowledgeBaseCardsBusy = true;
  renderKnowledgeBaseCards();
  try {
    state.knowledgeBaseCards = await fetchJson<JsonMap>(`/api/knowledge-base/cards?kind=${encodeURIComponent(kind)}&limit=200`);
  } catch (error) {
    state.knowledgeBaseCards = {
      label: kind,
      cards: [],
      error: error instanceof Error ? error.message : String(error),
    };
  } finally {
    state.knowledgeBaseCardsBusy = false;
    renderKnowledgeBaseCards();
    hydrateIcons(els.knowledgeCards);
  }
}

function closeKnowledgeBaseCards() {
  state.selectedKnowledgeBaseKind = null;
  state.knowledgeBaseCards = null;
  state.knowledgeBaseCardsBusy = false;
  renderKnowledgeBaseCards();
}

function renderKnowledgeBaseCards() {
  if (!state.selectedKnowledgeBaseKind) {
    els.knowledgeCards.innerHTML = '';
    return;
  }
  if (state.knowledgeBaseCardsBusy) {
    els.knowledgeCards.innerHTML = `
      <div class="kb-list-head">
        <div class="node-detail-title">${escapeHtml(state.selectedKnowledgeBaseKind)}</div>
        <button class="icon-btn ghost" type="button" data-kb-close title="Close"><span data-icon="X"></span></button>
      </div>
      ${emptyState('Loading cards...', 'Loader2')}
    `;
    bindKnowledgeCardControls();
    return;
  }
  const payload = state.knowledgeBaseCards || {};
  const cards: JsonMap[] = payload.cards || [];
  els.knowledgeCards.innerHTML = `
    <div class="kb-list-head">
      <div>
        <div class="node-detail-title">${escapeHtml(payload.label || state.selectedKnowledgeBaseKind)}</div>
        <div class="meta">${escapeHtml(cards.length)} shown${payload.count ? ` · ${escapeHtml(payload.count)} total` : ''}</div>
      </div>
      <button class="icon-btn ghost" type="button" data-kb-close title="Close"><span data-icon="X"></span></button>
    </div>
    ${payload.error ? `<div class="empty"><span data-icon="AlertTriangle"></span><span>${escapeHtml(payload.error)}</span></div>` : ''}
    ${cards.length ? `<div class="kb-cards">${cards.map(knowledgeBaseCardHtml).join('')}</div>` : emptyState('No cards yet.', 'Info')}
  `;
  bindKnowledgeCardControls();
}

function bindKnowledgeCardControls() {
  const close = els.knowledgeCards.querySelector<HTMLButtonElement>('[data-kb-close]');
  close?.addEventListener('click', closeKnowledgeBaseCards);
  for (const item of els.knowledgeCards.querySelectorAll<HTMLElement>('[data-preview-url]')) {
    item.addEventListener('click', () => {
      const previewUrl = item.dataset.previewUrl || '';
      if (previewUrl) window.open(previewUrl, '_blank', 'noopener');
    });
  }
}

function knowledgeBaseCardHtml(card: JsonMap) {
  const previewUrl = card.previewUrl || '';
  const meta = card.meta || {};
  const metaItems = Object.entries(meta)
    .filter(([, value]) => Array.isArray(value) ? value.length : value)
    .slice(0, 4);
  return `
    <article class="kb-card ${previewUrl ? 'clickable' : ''}" ${previewUrl ? `data-preview-url="${escapeHtml(previewUrl)}"` : ''}>
      <div class="kb-card-title">
        <span>${escapeHtml(card.title || card.id || 'card')}</span>
        <span class="meta">${escapeHtml(card.id || '')}</span>
      </div>
      ${card.subtitle ? `<div class="meta">${escapeHtml(card.subtitle)}</div>` : ''}
      ${card.body ? `<p>${escapeHtml(card.body)}</p>` : ''}
      ${metaItems.length ? `<div class="graph-mini-list">${metaItems.map(([key, value]) => `<span>${escapeHtml(key)}: ${escapeHtml(Array.isArray(value) ? value.join(', ') : value)}</span>`).join('')}</div>` : ''}
    </article>
  `;
}

function renderBuilderTrace(parts: JsonMap[]) {
  const wasNearBottom = els.builderTrace.scrollHeight - els.builderTrace.scrollTop - els.builderTrace.clientHeight < 120;
  const savedScroll = els.builderTrace.scrollTop;
  const visible = normalizeChatParts((parts || []).map((part) => ({ ...part, sourceLabel: 'builder' }))).slice(-80);
  if (!visible.length) {
    els.builderTrace.innerHTML = emptyState('No builder agent trace yet. Click Build in the left settings bar.', 'TerminalSquare');
    return;
  }
  els.builderTrace.innerHTML = visible.map((part) => messageHtml(part)).join('');
  bindToolCards(els.builderTrace);
  if (wasNearBottom) {
    els.builderTrace.scrollTop = els.builderTrace.scrollHeight;
  } else if (savedScroll < els.builderTrace.scrollHeight) {
    els.builderTrace.scrollTop = Math.min(savedScroll, els.builderTrace.scrollHeight - els.builderTrace.clientHeight);
  }
}

function renderKnowledgeGraph(graph: JsonMap | null | undefined) {
  const nodes: JsonMap[] = graph?.nodes || [];
  const edges: JsonMap[] = graph?.edges || [];
  els.graphTitle.textContent = graph?.taskGoal || 'Reference Knowledge';
  if (!nodes.length) {
    els.graphCanvas.innerHTML = emptyState(graph?.notes || '暂无知识图谱。完成 problem-contract 后会在这里显示。', 'Network');
    els.graphInspector.innerHTML = graphMetadataHtml(graph, nodes, edges);
    return;
  }

  const selected = nodes.find((node) => node.id === state.selectedGraphNodeId) || nodes[0];
  state.selectedGraphNodeId = selected?.id || null;
  const width = 920;
  const height = 620;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.36;
  const positions = new Map<string, { x: number; y: number }>();
  nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
    const typeOffset = graphNodeTypes.indexOf(node.type || '') % 5;
    positions.set(String(node.id), {
      x: centerX + Math.cos(angle) * (radius - typeOffset * 18),
      y: centerY + Math.sin(angle) * (radius - typeOffset * 18),
    });
  });

  els.graphCanvas.innerHTML = `
    <svg class="graph-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Knowledge graph">
      <g class="graph-edges">
        ${edges.map((edge) => {
          const source = positions.get(String(edge.source));
          const target = positions.get(String(edge.target));
          if (!source || !target) return '';
          return `<line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" />`;
        }).join('')}
      </g>
      <g class="graph-nodes">
        ${nodes.map((node) => {
          const position = positions.get(String(node.id));
          if (!position) return '';
          const selectedClass = node.id === state.selectedGraphNodeId ? ' selected' : '';
          return `
            <g class="graph-node${selectedClass}" data-node-id="${escapeHtml(node.id)}" transform="translate(${position.x} ${position.y})">
              <circle r="22"></circle>
              <text y="42">${escapeHtml(shortGraphLabel(node.label || node.id))}</text>
            </g>
          `;
        }).join('')}
      </g>
    </svg>
  `;
  for (const item of els.graphCanvas.querySelectorAll<SVGGElement>('.graph-node')) {
    item.addEventListener('click', () => {
      state.selectedGraphNodeId = item.dataset.nodeId || null;
      renderKnowledgeGraph(state.bootstrap?.knowledgeGraph);
      hydrateIcons();
    });
  }
  els.graphInspector.innerHTML = graphInspectorHtml(graph, selected, nodes, edges);
  for (const item of els.graphInspector.querySelectorAll<HTMLElement>('.artifact-item')) {
    item.addEventListener('click', async () => {
      const previewUrl = item.dataset.previewUrl || '';
      if (previewUrl) {
        window.open(previewUrl, '_blank', 'noopener');
        return;
      }
      await showWorkspaceFile(item.dataset.path || '');
    });
  }
}

const graphNodeTypes = ['task', 'concept', 'observable', 'method', 'metric', 'risk', 'assumption', 'data_field', 'case_pattern', 'reference'];

function graphMetadataHtml(graph: JsonMap | null | undefined, nodes: JsonMap[], edges: JsonMap[]) {
  return `
    <div class="node-detail-title">Graph Metadata</div>
    <dl class="kv graph-kv">
      <dt>Classes</dt><dd>${nodes.length}</dd>
      <dt>Relations</dt><dd>${edges.length}</dd>
      <dt>Updated</dt><dd>${escapeHtml(graph?.updatedAt || '-')}</dd>
    </dl>
  `;
}

function graphInspectorHtml(graph: JsonMap | null | undefined, selected: JsonMap | undefined, nodes: JsonMap[], edges: JsonMap[]) {
  if (!selected) return graphMetadataHtml(graph, nodes, edges);
  const related = edges.filter((edge) => edge.source === selected.id || edge.target === selected.id);
  return `
    ${graphMetadataHtml(graph, nodes, edges)}
    <div class="detail-section-title">Selected</div>
    <div class="graph-selected">
      <div class="node-detail-title">${escapeHtml(selected.label || selected.id)}</div>
      <div class="meta">${escapeHtml(selected.type || 'class')} · ${escapeHtml(selected.id || '')}</div>
      ${classDescriptionHtml(selected.summary || '')}
    </div>
    <div class="detail-section-title">Source Knowledge</div>
    ${idListHtml(selected.knowledgeIds || [], 'Knowledge')}
    <div class="detail-section-title">Evidence</div>
    ${graphEvidenceHtml(selected.evidence || [])}
    <div class="detail-section-title">Relations</div>
    ${related.length ? `<div class="graph-relations">${related.map((edge) => `
      <div class="graph-relation">
        <div class="timeline-type">${escapeHtml(edge.relation || 'related')}</div>
        <div class="meta">${escapeHtml(edge.sourceLabel || edge.source)} -> ${escapeHtml(edge.targetLabel || edge.target)}</div>
        <div>${escapeHtml(edge.summary || '')}</div>
        ${edge.knowledgeIds?.length ? idListHtml(edge.knowledgeIds, 'Knowledge') : ''}
      </div>
    `).join('')}</div>` : emptyState('暂无关联边。', 'GitBranch')}
  `;
}

function idListHtml(items: string[], label: string) {
  if (!items.length) return emptyState(`No supporting ${label.toLowerCase()} yet.`, 'Info');
  return `<div class="graph-mini-list">${items.map((item) => `<span>${escapeHtml(item)}</span>`).join('')}</div>`;
}

function classDescriptionHtml(summary: string) {
  if (!summary) return emptyState('暂无描述。', 'Info');
  return `
    <details class="class-description">
      <summary>Description</summary>
      <p>${escapeHtml(summary)}</p>
    </details>
  `;
}

function graphEvidenceHtml(items: JsonMap[]) {
  if (!items.length) return emptyState('暂无证据。', 'File');
  return `<div class="graph-evidence">${items.slice(0, 6).map((item) => `
    <button class="artifact-item evidence-item" type="button" data-path="${escapeHtml(item.sourcePath || '')}" data-preview-url="${escapeHtml(item.previewUrl || '')}">
      <span data-icon="File"></span>
      <span>${escapeHtml(item.sourcePath || 'source')}: ${escapeHtml(item.quote || item.summary || '')}</span>
    </button>
  `).join('')}</div>`;
}

function shortGraphLabel(value: string) {
  return value.length > 18 ? `${value.slice(0, 17)}...` : value;
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
    const partId = String(part.id || `${part.timestamp || ''}:${toolName}:${part.type || ''}`);
    const expanded = state.expandedToolPartIds.has(partId);
    return `
      <article class="message ${escapeHtml(roleClass)} tool-collapsed${expanded ? ' expanded' : ''}" data-part-id="${escapeHtml(partId)}">
        <button class="tool-card${expanded ? ' expanded' : ''}" type="button" data-tool-toggle>
          <span class="tool-status ${done ? 'done' : 'running'}"><span data-icon="${done ? 'Check' : 'TerminalSquare'}"></span></span>
          <span class="tool-copy">
            <span class="tool-title">${escapeHtml(summary)}</span>
            <span class="tool-meta">${escapeHtml(source)}${escapeHtml(toolName)} · ${escapeHtml(part.type || 'tool')} · ${formatTime(part.timestamp)}</span>
          </span>
          <span class="tool-chevron" data-icon="ChevronRight"></span>
        </button>
        <pre class="tool-detail" ${expanded ? '' : 'hidden'}>${escapeHtml(detail)}</pre>
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
  const SUPPRESS_SYSTEM_SUBTYPES = new Set([
    'init',
    'task_started',
    'task_progress',
    'task_updated',
    'task_notification',
    'task_completed',
    'task_failed',
    'task_stopped',
    'task_output',
    'system',
  ]);
  return parts
    .map((part: JsonMap) => ({ ...part, displayText: displayTextForPart(part) }))
    .filter((part: JsonMap) => {
      if (part.type === 'loading') return true;
      if (!part.displayText.trim()) return false;
      if (part.role === 'system' && part.type === 'raw') {
        const subtype = part.raw?.subtype || part.text || part.displayText || '';
        if (SUPPRESS_SYSTEM_SUBTYPES.has(subtype.trim())) return false;
      }
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
    const rawText = toolResultTextFromRaw(part.raw);
    if (rawText) return rawText;
    return part.text === 'Tool result' ? '' : part.text || '';
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
  const savedScroll = els.timeline.scrollTop;
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
  els.timeline.scrollTop = Math.min(savedScroll, els.timeline.scrollHeight - els.timeline.clientHeight);
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
      state.busy = false;
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

function bindToolCards(root: HTMLElement = els.chatStream) {
  for (const button of root.querySelectorAll<HTMLButtonElement>('[data-tool-toggle]')) {
    button.addEventListener('click', () => {
      const detail = button.nextElementSibling as HTMLElement | null;
      if (!detail) return;
      const expanded = detail.hidden === true;
      detail.hidden = !expanded;
      const article = button.closest<HTMLElement>('.tool-collapsed');
      const partId = article?.dataset.partId;
      if (partId) {
        if (expanded) state.expandedToolPartIds.add(partId);
        else state.expandedToolPartIds.delete(partId);
      }
      article?.classList.toggle('expanded', expanded);
      button.classList.toggle('expanded', expanded);
      if (expanded) requestAnimationFrame(() => article?.scrollIntoView({ block: 'nearest' }));
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
    state.busy = Boolean(result.bootstrap?.runtime?.running);
    if (state.busy) {
      state.loadingMessage = loadingPart('暂停中，等待当前请求收尾');
      render();
      await waitForBackendIdle(5000);
    } else {
      state.loadingMessage = null;
      render();
    }
  } catch (error) {
    showDetail('Interrupt Error', { message: error instanceof Error ? error.message : String(error) });
  }
}

async function postSend(text: string): Promise<any> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      return await postJson('/api/send', { text });
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      if (!isPausedResumeSettling(message)) break;
      state.loadingMessage = loadingPart('暂停恢复中，正在重试发送');
      await sleep(700);
      try {
        state.bootstrap = await fetchJson<Bootstrap>('/api/bootstrap');
        state.busy = Boolean(state.bootstrap.runtime?.running);
      } catch {
        // Keep retrying with the original send request if the refresh races the server.
      }
    }
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

function isPausedResumeSettling(message: string): boolean {
  if (!isActiveNodePaused(state.bootstrap)) return false;
  return message.includes('still settling') || message.includes('already active');
}

async function waitForBackendIdle(timeoutMs: number) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    await sleep(300);
    const data = await fetchJson<Bootstrap>('/api/bootstrap');
    state.bootstrap = data;
    state.busy = Boolean(data.runtime?.running);
    if (!state.busy) {
      state.loadingMessage = null;
      render();
      return;
    }
    render();
  }
}

function isActiveNodePaused(data: Bootstrap | null): boolean {
  if (!data?.state?.activeNodeSessionId) return false;
  const node = (data.nodes || []).find((item) => item.id === data.state.activeNodeSessionId);
  return node?.status === 'paused';
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
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

function toolResultTextFromRaw(raw: any): string {
  const content = raw?.message?.content ?? raw?.content;
  return extractToolResultText(content);
}

function extractToolResultText(value: any): string {
  if (typeof value === 'string') return value.trim();
  if (!Array.isArray(value)) return '';
  const parts: string[] = [];
  for (const item of value) {
    if (typeof item === 'string') {
      if (item.trim()) parts.push(item.trim());
      continue;
    }
    if (!item || typeof item !== 'object') continue;
    if (typeof item.text === 'string' && item.text.trim()) {
      parts.push(item.text.trim());
      continue;
    }
    const nested = extractToolResultText(item.content);
    if (nested) parts.push(nested);
  }
  return parts.join('\n');
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
  if (state.bootstrap?.runtime?.running || state.bootstrap?.runtime?.knowledgeGraphRunning || state.busy) {
    livePoll().catch(() => undefined);
  }
}, 10000);

refresh().catch((error) => showDetail('Startup Error', { message: error instanceof Error ? error.message : String(error) }));
