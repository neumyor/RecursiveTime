import './styles.css';
import { fetchJson, postForm, postJson } from './api';
import DOMPurify from 'dompurify';
import {
  Activity,
  AlertTriangle,
  ArrowDown,
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
import type { Bootstrap, FileTreeNode, JsonMap } from './types';

const state = {
  bootstrap: null as Bootstrap | null,
  busy: false,
  selectedNodeType: null as string | null,
  pendingParts: [] as JsonMap[],
  loadingMessage: null as JsonMap | null,
  transcriptScope: 'all',
  leftCollapsed: window.innerWidth <= 820,
  rightCollapsed: window.innerWidth <= 1180,
  view: ((window.location.pathname === '/knowledge-graph'
    ? 'knowledgeGraph'
    : window.location.pathname === '/chain-summary'
    ? 'chainSummary'
    : window.location.pathname === '/image-viewer'
    ? 'imageViewer'
    : window.location.pathname === '/settings'
    ? 'settings'
    : 'chat') as 'chat' | 'knowledgeGraph' | 'chainSummary' | 'imageViewer' | 'settings'),
  selectedImagePath: new URLSearchParams(window.location.search).get('path') || '',
  selectedGraphNodeId: null as string | null,
  selectedKnowledgeBaseKind: null as string | null,
  knowledgeBaseCards: null as JsonMap | null,
  knowledgeBaseCardsBusy: false,
  expandedToolPartIds: new Set<string>(),
  settings: {
    iterativeK: 3,
    graphDepth: 2,
    graphAuthMode: 'manual',
    graphProtocol: '',
    graphContext: '',
    graphModel: '',
    graphBaseUrl: '',
    graphApiKey: '',
    mainAuthMode: 'manual',
    mainProtocol: '',
    mainContext: '',
    mainModel: '',
    mainBaseUrl: '',
    mainApiKey: '',
  } as {
    iterativeK: number;
    graphDepth: number;
    graphAuthMode: string;
    graphProtocol: string;
    graphContext: string;
    graphModel: string;
    graphBaseUrl: string;
    graphApiKey: string;
    mainAuthMode: string;
    mainProtocol: string;
    mainContext: string;
    mainModel: string;
    mainBaseUrl: string;
    mainApiKey: string;
  },
  settingsSaveTimer: 0,
  knowledgeQuestion: '',
  knowledgeAnswer: null as JsonMap | null,
  knowledgeQueryBusy: false,
  chainStatusSignature: '',
  chainChartSignature: '',
  chainContentSignature: '',
  renderSignatures: new Map<string, string>(),
  realtimeWaiters: [] as Array<{
    predicate: (data: Bootstrap) => boolean;
    resolve: (data: Bootstrap) => void;
    reject: (error: Error) => void;
    timer: number;
  }>,
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
        <dt>Variant</dt>
        <dd id="variantText">-</dd>
        <dt>Model</dt>
        <dd id="modelText">-</dd>
        <dt>Runtime</dt>
        <dd id="runtimeUvText">-</dd>
      </dl>
      <div class="workspace-actions">
        <button id="stateBtn" type="button" class="ghost"><span data-icon="Archive"></span><span>State</span></button>
        <button id="llmBtn" type="button" class="ghost"><span data-icon="Settings2"></span><span>LLM</span></button>
      </div>
      <button id="settingsBtn" type="button" class="workspace-settings-btn"><span data-icon="SlidersHorizontal"></span><span>Settings</span></button>
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
        <button id="resetChatBtn" type="button" class="ghost debug-only"><span data-icon="RefreshCw"></span><span>Reset Chat</span></button>
        <button id="clearAllLogsBtn" type="button" class="danger ghost debug-only"><span data-icon="Trash2"></span><span>Reset Workspace</span></button>
      </div>
    </header>

    <section id="chatStream" class="chat-stream"></section>

    <section id="settingsView" class="settings-view" hidden>
      <header class="settings-header">
        <div class="settings-header-inner">
          <div class="settings-header-text">
            <div class="settings-eyebrow"><span data-icon="SlidersHorizontal"></span><span>Workspace</span></div>
            <h1 class="settings-title">Settings</h1>
            <p class="settings-subtitle">All configurable parameters for this workspace. Changes apply immediately or on the next message.</p>
          </div>
          <div class="settings-header-actions">
            <button id="settingsDoneBtn" type="button" class="settings-done-btn"><span data-icon="ChevronLeft"></span><span>Back to Chat</span></button>
          </div>
        </div>
      </header>
      <div id="settingsContent" class="settings-content"></div>
    </section>
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

    <section id="chainSummaryView" class="chain-summary-view" hidden>
      <header class="chain-header">
        <div class="chain-title-block">
          <div class="eyebrow"><span data-icon="Activity"></span><span>Chain Summary</span></div>
          <h2>思维链总结</h2>
          <p>把当前 workspace 的日志、iteration 报告、运行结果和样本证据组织成一条可审计的决策链。</p>
        </div>
        <div class="chain-header-actions">
          <button id="backToChatFromChainBtn" type="button" class="chain-back-btn"><span data-icon="ChevronLeft"></span><span>返回主会话</span></button>
          <button id="buildChainSummaryBtn" type="button" class="chain-generate-btn"><span data-icon="RefreshCw"></span><span>生成思维链总结</span></button>
        </div>
      </header>
      <section id="chainBuildStatus" class="chain-build-status"></section>
      <section id="chainMetricChart" class="chain-chart-panel"></section>
      <section id="chainSummaryContent" class="chain-content-panel"></section>
    </section>

    <section id="imageViewerView" class="image-viewer-view" hidden>
      <header class="image-viewer-header">
        <div>
          <div class="eyebrow"><span data-icon="Activity"></span><span>Chain Summary Image</span></div>
          <h2 id="imageViewerTitle">样本可视化</h2>
        </div>
        <button id="backToChainFromImageBtn" type="button" class="chain-back-btn"><span data-icon="ChevronLeft"></span><span>返回思维链总结</span></button>
      </header>
      <section class="image-viewer-stage">
        <img id="imageViewerImage" alt="Chain summary visualization" />
      </section>
      <div id="imageViewerPath" class="image-viewer-path"></div>
    </section>

    <form id="sendForm" class="composer">
      <div class="composer-shell">
        <textarea id="messageInput" rows="1" placeholder="向 orchestrator 发送消息"></textarea>
        <button id="sendBtn" type="submit" class="send-round" title="发送" disabled><span data-icon="ArrowUp"></span></button>
      </div>
    </form>
  </main>

  <aside class="right-rail">
    <button id="kgCta" class="kg-cta" type="button" data-state="idle" aria-label="Open Knowledge Graph">
      <div class="kg-cta-icon"><span data-icon="Network"></span></div>
      <div class="kg-cta-body">
        <div class="kg-cta-eyebrow">Reference Knowledge</div>
        <div class="kg-cta-title">Knowledge Graph</div>
        <div class="kg-cta-meta">
          <span class="kg-cta-pill" id="kgCtaPill">Idle</span>
          <span class="kg-cta-stats" id="kgCtaStats">not built</span>
        </div>
      </div>
      <div class="kg-cta-arrow"><span data-icon="ChevronRight"></span></div>
    </button>
    <button id="chainCta" class="kg-cta chain-cta" type="button" data-state="idle" aria-label="Open Chain Summary">
      <div class="kg-cta-icon"><span data-icon="Activity"></span></div>
      <div class="kg-cta-body">
        <div class="kg-cta-eyebrow">Agent Trajectory</div>
        <div class="kg-cta-title">思维链总结</div>
        <div class="kg-cta-meta">
          <span class="kg-cta-pill" id="chainCtaPill">Idle</span>
          <span class="kg-cta-stats" id="chainCtaStats">not generated</span>
        </div>
      </div>
      <div class="kg-cta-arrow"><span data-icon="ChevronRight"></span></div>
    </button>
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
  ArrowDown,
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
  variantText: query('#variantText'),
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
  chainSummaryView: query<HTMLElement>('#chainSummaryView'),
  imageViewerView: query<HTMLElement>('#imageViewerView'),
  imageViewerTitle: query<HTMLElement>('#imageViewerTitle'),
  imageViewerImage: query<HTMLImageElement>('#imageViewerImage'),
  imageViewerPath: query<HTMLElement>('#imageViewerPath'),
  backToChainFromImageBtn: query<HTMLButtonElement>('#backToChainFromImageBtn'),
  backToChatFromChainBtn: query<HTMLButtonElement>('#backToChatFromChainBtn'),
  buildChainSummaryBtn: query<HTMLButtonElement>('#buildChainSummaryBtn'),
  chainBuildStatus: query<HTMLElement>('#chainBuildStatus'),
  chainMetricChart: query<HTMLElement>('#chainMetricChart'),
  chainSummaryContent: query<HTMLElement>('#chainSummaryContent'),
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
  kgCta: query<HTMLButtonElement>('#kgCta'),
  kgCtaPill: query<HTMLElement>('#kgCtaPill'),
  kgCtaStats: query<HTMLElement>('#kgCtaStats'),
  chainCta: query<HTMLButtonElement>('#chainCta'),
  chainCtaPill: query<HTMLElement>('#chainCtaPill'),
  chainCtaStats: query<HTMLElement>('#chainCtaStats'),
  stateBtn: query<HTMLButtonElement>('#stateBtn'),
  llmBtn: query<HTMLButtonElement>('#llmBtn'),
  settingsBtn: query<HTMLButtonElement>('#settingsBtn'),
  settingsView: query<HTMLElement>('#settingsView'),
  settingsContent: query<HTMLElement>('#settingsContent'),
  settingsDoneBtn: query<HTMLButtonElement>('#settingsDoneBtn'),
  resetChatBtn: query<HTMLButtonElement>('#resetChatBtn'),
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

// Track IME composition state locally. We need this because some mobile
// IMEs (e.g. iOS Chinese) commit the candidate and *then* fire the final
// Enter keydown with isComposing already false — by the time the keydown
// arrives the composition has ended, so a flag tracked via
// compositionstart / compositionend is the only reliable signal.
let imeActive = false;
els.messageInput.addEventListener('compositionstart', () => {
  imeActive = true;
});
els.messageInput.addEventListener('compositionend', () => {
  imeActive = false;
});
els.messageInput.addEventListener('keydown', (event) => {
  // An IME-processing Enter must never send. Four independent signals cover
  // the matrix of browsers and IMEs:
  //   1. event.isComposing  — modern Chromium / WebKit / Firefox (Chrome 66+,
  //      Firefox 68+, Safari 13+). True while a composition is active.
  //   2. event.keyCode === 229 — the legacy "IME processed" indicator that
  //      every browser still emits as a fallback (deprecated but universal).
  //   3. event.key === 'Process' — what older WebKit and some mobile IMEs
  //      set on the keydown of a key the IME consumed.
  //   4. imeActive — the composition-state flag tracked above, for the
  //      post-composition-end race on iOS Chinese / Korean keyboards.
  if (event.isComposing || event.keyCode === 229 || event.key === 'Process' || imeActive) return;
  if (event.key !== 'Enter' || event.shiftKey) return;
  event.preventDefault();
  if (!els.sendBtn.disabled) els.sendForm.requestSubmit();
});
els.approveControlBtn.addEventListener('click', async () => {
  await runStreamingAction(async () => {
    await postJson('/api/control/approve', {});
  });
});
els.rejectControlBtn.addEventListener('click', async () => {
  const reason = els.messageInput.value.trim();
  await runAction(async () => {
    const result = await postJson('/api/control/reject', { reason: reason || 'Rejected from web UI.' });
    applyBootstrapSnapshot(result.bootstrap);
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
els.settingsBtn.addEventListener('click', () => {
  state.view = 'settings';
  history.pushState({}, '', '/settings');
  render();
});
els.settingsDoneBtn.addEventListener('click', () => {
  state.view = 'chat';
  history.pushState({}, '', '/');
  render();
});
els.buildGraphBtn.addEventListener('click', async () => {
  await postJson('/api/knowledge-graph/build', { trigger: 'manual' });
});
els.continueGraphBtn.addEventListener('click', async () => {
  await postJson('/api/knowledge-graph/continue', {});
});
els.pauseGraphBtn.addEventListener('click', async () => {
  await postJson('/api/knowledge-graph/pause', { reason: 'Paused from knowledge graph UI.' });
});
els.saveGraphLlmBtn.addEventListener('click', async () => {
  await saveKnowledgeGraphLlmConfig();
});
els.kgCta.addEventListener('click', async () => {
  state.view = 'knowledgeGraph';
  history.pushState({}, '', '/knowledge-graph');
  render();
});
els.chainCta.addEventListener('click', async () => {
  state.view = 'chainSummary';
  history.pushState({}, '', '/chain-summary');
  resetChainRenderSignatures();
  render();
});
els.backToChatFromChainBtn.addEventListener('click', () => {
  state.view = 'chat';
  history.pushState({}, '', '/');
  render();
});
els.backToChainFromImageBtn.addEventListener('click', () => {
  state.view = 'chainSummary';
  history.pushState({}, '', '/chain-summary');
  render();
});
els.buildChainSummaryBtn.addEventListener('click', async () => {
  resetChainRenderSignatures();
  await postJson('/api/chain-summary/build', {});
});
window.addEventListener('popstate', () => {
  const path = window.location.pathname;
  state.view = path === '/knowledge-graph'
    ? 'knowledgeGraph'
    : path === '/chain-summary'
    ? 'chainSummary'
    : path === '/image-viewer'
    ? 'imageViewer'
    : path === '/settings'
    ? 'settings'
    : 'chat';
  state.selectedImagePath = path === '/image-viewer'
    ? new URLSearchParams(window.location.search).get('path') || ''
    : state.selectedImagePath;
  render();
});
els.graphExtractionDepthInput.addEventListener('change', async () => {
  await saveGraphExtractionDepth();
});
async function saveGraphExtractionDepth() {
  const value = Number.parseInt(els.graphExtractionDepthInput.value, 10);
  if (!Number.isFinite(value)) return;
  const result = await postJson('/api/runtime-settings', { knowledgeGraphExtractionDepth: value });
  applyBootstrapSnapshot(result.bootstrap);
}
async function saveKnowledgeGraphLlmConfig() {
  const result = await postJson('/api/knowledge-graph/llm-config', {
    authMode: els.graphAuthMode.value,
    protocol: els.graphProtocol.value || undefined,
    model: els.graphModelInput.value.trim(),
    apiKey: els.graphApiKeyInput.value.trim() || undefined,
    baseUrl: els.graphBaseUrlInput.value.trim(),
  });
  applyBootstrapSnapshot(result.bootstrap);
  els.graphApiKeyInput.value = '';
}
els.interruptBtn.addEventListener('click', async () => {
  const reason = els.messageInput.value.trim();
  await interruptCurrent(reason || 'User interrupted from web UI.');
});
els.resetChatBtn.addEventListener('click', async () => {
  if (!confirm('这将重置聊天记录和 agent 工作流记忆，但保留 data/raw、references 和已构建的知识图谱。是否继续？')) return;
  await runAction(async () => {
    const result = await postJson('/api/debug/clear-logs', { scope: 'chat', confirmReset: true });
    state.pendingParts = [];
    state.loadingMessage = null;
    state.transcriptScope = 'main';
    state.renderSignatures.clear();
    applyBootstrapSnapshot(result.bootstrap);
  });
});
els.clearAllLogsBtn.addEventListener('click', async () => {
  if (!confirm('这将重置整个工作区，删除 references、knowledge graph、日志、运行产物、报告和临时工具。设置中的 API key、endpoint、model 与 k 会保留。是否继续？')) return;
  const typed = prompt('二次确认：请输入 RESET 来确认重置工作区。');
  if (typed !== 'RESET') return;
  await runAction(async () => {
    const result = await postJson('/api/debug/clear-logs', { scope: 'all', confirmReset: true });
    state.pendingParts = [];
    state.loadingMessage = null;
    state.transcriptScope = 'main';
    state.renderSignatures.clear();
    applyBootstrapSnapshot(result.bootstrap);
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
    await postSend(text);
  });
});

els.uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const files = [...(els.referenceFiles.files || [])];
  if (!files.length) return;
  await runAction(async () => {
    const form = new FormData();
    for (const file of files) form.append('files', file);
    await postForm('/api/references/upload', form);
    els.referenceFiles.value = '';
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
    showDetail('Raw Data Zip Uploaded', {
      archive: result.uploaded?.archive,
      targetDir: result.uploaded?.targetDir,
      extractedCount: result.uploaded?.extracted?.length || 0,
      extracted: result.uploaded?.extracted || [],
    });
  });
});

function connectRealtimeEvents() {
  const source = new EventSource('/api/events');
  source.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data || '{}');
      applyRealtimeEvent(message.type, message.payload || {});
    } catch {
      // EventSource reconnects automatically; malformed events are ignored.
    }
  };
  window.addEventListener('beforeunload', () => source.close(), { once: true });
}

function applyRealtimeEvent(eventType: string, payload: JsonMap) {
  if (eventType === 'bootstrap_snapshot' && payload.bootstrap) {
    applyBootstrapSnapshot(payload.bootstrap as Bootstrap);
    return;
  }
  if (!state.bootstrap) return;
  if (eventType === 'main_parts') {
    state.bootstrap.mainParts = payload.mainParts || [];
    state.pendingParts = reconcilePendingParts(state.bootstrap);
    render();
    return;
  }
  if (eventType === 'knowledge_graph_parts') {
    state.bootstrap.knowledgeGraphParts = payload.knowledgeGraphParts || [];
    render();
    return;
  }
  if (eventType === 'chain_summary_parts') {
    state.bootstrap.chainSummaryParts = payload.chainSummaryParts || [];
    render();
    return;
  }
  if (eventType === 'node_parts') {
    state.bootstrap.nodePartsById = {
      ...(state.bootstrap.nodePartsById || {}),
      ...(payload.nodePartsById || {}),
    };
    if (payload.nodes) state.bootstrap.nodes = payload.nodes;
    if (payload.state) state.bootstrap.state = payload.state;
    if (payload.timeline) state.bootstrap.timeline = payload.timeline;
    render();
    return;
  }
  if (eventType === 'workspace_files' && payload.fileTree) {
    state.bootstrap.fileTree = payload.fileTree;
    render();
    return;
  }
  if (eventType === 'live_snapshot' && payload.snapshot) {
    const merged = { ...state.bootstrap, ...payload.snapshot } as Bootstrap;
    applyBootstrapSnapshot(merged);
  }
}

function applyBootstrapSnapshot(data: Bootstrap) {
  state.bootstrap = data;
  state.busy = Boolean(data.runtime?.running);
  state.pendingParts = reconcilePendingParts(data);
  state.loadingMessage = state.busy
    ? state.loadingMessage || loadingPart('后端运行中，正在实时接收最新消息')
    : null;
  render();
  resolveRealtimeWaiters(data);
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
  setHtmlIfChanged(els.statusText, statusPill(activeNode ? `Active: ${activeNode}` : 'Ready', activeNode ? 'active' : 'ready'));
  els.modeText.textContent = data.dryRun ? `${ws.controlMode || ws.mode} / dry-run` : (ws.controlMode || ws.mode || '-');
  setHtmlIfChanged(els.variantText, variantPill(data.variant));
  els.modelText.textContent = data.llmConfig?.config?.model || 'sdk-default';
  setHtmlIfChanged(els.runtimeUvText, runtimePill(data.runtime?.workspaceUv));

  if (!state.selectedNodeType && data.nodeSpecs.length) {
    state.selectedNodeType = activeNode || data.nodeSpecs[0].type;
  }
  renderStable('nodes', [data.nodeSpecs, ws, data.nodes, state.selectedNodeType], () => renderNodes(data.nodeSpecs, ws, data.nodes));
  renderStable('node-detail', [data.nodeSpecs, data.nodes, state.selectedNodeType], () => renderNodeDetail(data.nodeSpecs, data.nodes));
  renderStable('pending-control', ws.pendingControl, () => renderPendingControl(ws.pendingControl));
  renderStable('transcript-scope', [data.nodes, state.transcriptScope], () => renderTranscriptScope(data.nodes));
  renderChat(data);
  renderStable('knowledge-graph', [data.knowledgeGraph, state.selectedGraphNodeId], () => renderKnowledgeGraph(data.knowledgeGraph));
  renderStable('knowledge-builder', [data.knowledgeGraphBuild, data.runtime, data.knowledgeGraphLlmConfig], () => renderKnowledgeGraphBuilder(data));
  renderStable('knowledge-workbench', [data.knowledgeBaseSummary, state.selectedKnowledgeBaseKind, state.knowledgeBaseCards, state.knowledgeBaseCardsBusy, state.knowledgeQuestion, state.knowledgeAnswer, state.knowledgeQueryBusy], () => renderKnowledgeWorkbench(data));
  renderStable('builder-trace', data.knowledgeGraphParts || [], () => renderBuilderTrace(data.knowledgeGraphParts || []));
  renderChainSummary(data);
  renderImageViewer();
  renderStable('settings', [data.llmConfig, data.knowledgeGraphLlmConfig, data.runtimeSettings], () => renderSettings(data));
  renderViewState();
  renderStable('timeline', data.timeline, () => renderTimeline(data.timeline));
  renderStable('file-tree', data.fileTree, () => renderFileTree(data.fileTree));
  renderStable('runtime-settings', data.runtimeSettings || ws.runtimeSettings, () => renderRuntimeSettings(data.runtimeSettings || ws.runtimeSettings));
  renderKgCta(data);
  renderChainCta(data);
  renderDebugActions(Boolean(data.debugEnabled));
  updateControls(data);
  renderShellState();
  hydrateIcons();
}

function renderStable(key: string, value: any, renderFn: () => void) {
  const signature = stableSignature(value);
  if (state.renderSignatures.get(key) === signature) return;
  state.renderSignatures.set(key, signature);
  renderFn();
}

function stableSignature(value: any) {
  const json = JSON.stringify(value ?? null);
  let hash = 2166136261;
  for (let index = 0; index < json.length; index += 1) {
    hash ^= json.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `${json.length}:${hash >>> 0}`;
}

function setHtmlIfChanged(element: HTMLElement, html: string) {
  if (element.innerHTML !== html) element.innerHTML = html;
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
    const isOpen = state.selectedNodeType === spec.type;
    return `
      <details class="node-item" data-node="${escapeHtml(spec.type)}" ${isOpen ? 'open' : ''}>
        <summary class="node-header">
          <span class="node-index">${index + 1}</span>
          <span class="node-name">${escapeHtml(spec.type)}</span>
          <span class="badge ${status}">${statusIcon(status)}${status}</span>
          <span class="node-chevron" data-icon="ChevronRight"></span>
        </summary>
        <div class="node-body">
          <div class="node-purpose">${escapeHtml(spec.phase)} · ${escapeHtml(spec.purpose)}</div>
        </div>
      </details>
    `;
  }).join('');

  for (const details of els.nodeList.querySelectorAll<HTMLDetailsElement>('details.node-item')) {
    details.addEventListener('toggle', () => {
      if (!details.open) return;
      // Close any other open details (exclusive accordion)
      for (const other of els.nodeList.querySelectorAll<HTMLDetailsElement>('details.node-item')) {
        if (other !== details && other.open) other.open = false;
      }
      state.selectedNodeType = details.dataset.node || null;
      renderNodeDetail(specs, sessions);
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
  const loadingParts = collectLoadingParts();
  const renderedParts = [...visibleParts, ...loadingParts];
  if (!renderedParts.length) {
    if (!els.chatStream.querySelector('.welcome-state') || els.chatStream.childElementCount !== 1) {
      els.chatStream.innerHTML = `
        <div class="welcome-state">
          <div class="welcome-orbit"><span data-icon="Sparkles"></span></div>
          <h3>Ready for a time-series workflow</h3>
          <p>发送任务后，orchestrator 会读取 workspace、规划节点并把执行过程同步到这里。</p>
        </div>
      `;
      hydrateIcons(els.chatStream);
    }
    return;
  }

  els.chatStream.querySelector('.welcome-state')?.remove();
  const existing = new Map<string, HTMLElement>();
  for (const element of els.chatStream.querySelectorAll<HTMLElement>('[data-message-key]')) {
    const key = element.dataset.messageKey;
    if (key) existing.set(key, element);
  }

  const desired: HTMLElement[] = [];
  const desiredKeys = new Set<string>();
  let changed = false;
  renderedParts.forEach((part, index) => {
    const key = messageKey(part, index);
    const fingerprint = stableSignature(part);
    desiredKeys.add(key);
    let element = existing.get(key);
    if (!element || element.dataset.messageFingerprint !== fingerprint) {
      const replacement = createMessageElement(part, key, fingerprint);
      if (element) element.remove();
      element = replacement;
      changed = true;
    }
    desired.push(element);
  });

  for (const [key, element] of existing) {
    if (!desiredKeys.has(key)) {
      element.remove();
      changed = true;
    }
  }

  let cursor = els.chatStream.firstElementChild;
  for (const element of desired) {
    if (element !== cursor) {
      els.chatStream.insertBefore(element, cursor);
      changed = true;
    }
    cursor = element.nextElementSibling;
  }

  if (changed && wasNearBottom) {
    els.chatStream.scrollTop = els.chatStream.scrollHeight;
  } else if (changed && savedScroll < els.chatStream.scrollHeight) {
    els.chatStream.scrollTop = Math.min(savedScroll, els.chatStream.scrollHeight - els.chatStream.clientHeight);
  }
}

function messageKey(part: JsonMap, index: number) {
  return String(part.id || part.sortKey || `${part.role || 'system'}:${part.type || 'text'}:${part.timestamp || index}`);
}

function createMessageElement(part: JsonMap, key: string, fingerprint: string) {
  const template = document.createElement('template');
  template.innerHTML = messageHtml(part).trim();
  const element = template.content.firstElementChild as HTMLElement | null;
  if (!element) throw new Error(`Unable to render message ${key}`);
  element.dataset.messageKey = key;
  element.dataset.messageFingerprint = fingerprint;
  bindToolCards(element);
  hydrateIcons(element);
  return element;
}

function renderRuntimeSettings(settings: JsonMap | null | undefined) {
  const graphDepth = settings?.knowledgeGraphExtractionDepth ?? 2;
  if (els.graphExtractionDepthInput.value !== String(graphDepth)) els.graphExtractionDepthInput.value = String(graphDepth);
}

function renderKgCta(data: Bootstrap) {
  if (!data) return;
  const build = data.knowledgeGraphBuild || {};
  const graph = data.knowledgeGraph || {};
  const running = Boolean(data.runtime?.knowledgeGraphRunning || build.running);
  const classes = (graph.nodes || []).length;
  const relations = (graph.edges || []).length;
  let state: 'idle' | 'building' | 'built' | 'failed' = 'idle';
  let label = 'Idle';
  if (build.status === 'failed') {
    state = 'failed';
    label = 'Failed';
  } else if (running) {
    state = 'building';
    label = 'Building';
  } else if (build.status === 'completed' && classes > 0) {
    state = 'built';
    label = 'Built';
  }
  els.kgCta.dataset.state = state;
  els.kgCtaPill.textContent = label;
  els.kgCtaPill.className = `kg-cta-pill ${state}`;
  els.kgCtaStats.textContent = classes > 0 || relations > 0
    ? `${classes} classes · ${relations} relations`
    : 'not built';
}

function renderChainCta(data: Bootstrap) {
  if (!data) return;
  const build = data.chainSummaryBuild || {};
  const summary = data.chainSummary || {};
  const running = Boolean(data.runtime?.chainSummaryRunning || build.running);
  const iterations = Array.isArray(summary.iterations) ? summary.iterations.length : 0;
  const metrics = Array.isArray(summary.metricSeries) ? summary.metricSeries.length : 0;
  let ctaState: 'idle' | 'building' | 'built' | 'failed' = 'idle';
  let label = 'Idle';
  if (build.status === 'failed') {
    ctaState = 'failed';
    label = 'Failed';
  } else if (running) {
    ctaState = 'building';
    label = 'Building';
  } else if (build.status === 'completed' || iterations > 0 || metrics > 0) {
    ctaState = 'built';
    label = 'Ready';
  }
  els.chainCta.dataset.state = ctaState;
  els.chainCtaPill.textContent = label;
  els.chainCtaPill.className = `kg-cta-pill ${ctaState}`;
  els.chainCtaStats.textContent = iterations || metrics ? `${iterations} iterations · ${metrics} metrics` : 'not generated';
}

function syncSettingsFromBootstrap(data: Bootstrap) {
  const settings = data.runtimeSettings || data.state?.runtimeSettings || {};
  state.settings.iterativeK = settings.iterativeCandidateCount ?? 3;
  state.settings.graphDepth = settings.knowledgeGraphExtractionDepth ?? 2;

  const main = data.llmConfig?.config || {};
  state.settings.mainAuthMode = main.authMode || 'manual';
  state.settings.mainProtocol = main.protocol || '';
  state.settings.mainContext = main.contextWindow || '';
  state.settings.mainModel = main.model || '';
  state.settings.mainBaseUrl = main.baseUrl || '';
  // apiKey is masked (e.g. "****1234"); never seed the editor with a real value

  const graph = data.knowledgeGraphLlmConfig?.config || {};
  state.settings.graphAuthMode = graph.authMode || 'manual';
  state.settings.graphProtocol = graph.protocol || '';
  state.settings.graphContext = graph.contextWindow || '';
  state.settings.graphModel = graph.model || '';
  state.settings.graphBaseUrl = graph.baseUrl || '';
}

function renderSettings(data: Bootstrap) {
  if (state.view !== 'settings') return;
  if (!data) return;
  syncSettingsFromBootstrap(data);
  const ws = data.state || {};

  const workspaceRows = [
    { label: 'Variant', value: variantPill(data.variant) },
    { label: 'Active node', value: ws.activeNode
      ? `<span class="settings-readout-pill active">${escapeHtml(ws.activeNode)}</span>`
      : `<span class="settings-readout-pill">—</span>` },
    { label: 'Control mode', value: `<span class="settings-readout-pill ${ws.controlMode === 'auto' ? 'active' : ''}">${escapeHtml(ws.controlMode || ws.mode || 'manual')}</span>` },
    { label: 'Dry run', value: data.dryRun
      ? `<span class="settings-readout-pill active">on</span>`
      : `<span class="settings-readout-pill">off</span>` },
    { label: 'Debug actions', value: data.debugEnabled
      ? `<span class="settings-readout-pill active">enabled</span>`
      : `<span class="settings-readout-pill">disabled</span>` },
    { label: 'Workspace UV', value: runtimePill(data.runtime?.workspaceUv) },
    { label: 'Workspace path', value: `<span class="settings-readout-mono">${escapeHtml(data.runtime?.workspaceUv?.workspace || '')}</span>`, copyable: data.runtime?.workspaceUv?.workspace || '' },
  ];

  const kOptions = [1, 2, 3, 4, 5, 6, 7, 8];
  const depthOptions = [1, 2, 3, 4];

  els.settingsContent.innerHTML = `
    <div class="settings-section">
      <div class="settings-section-header">Workspace</div>
      <div class="settings-card">
        ${workspaceRows.map((row) => `
          <div class="settings-row">
            <div class="settings-row-label">${escapeHtml(row.label)}</div>
            <div class="settings-row-control">${row.value}${row.copyable ? `<button class="settings-icon-btn" type="button" data-copy="${escapeHtml(row.copyable)}" title="Copy"><span data-icon="Archive"></span></button>` : ''}</div>
          </div>
        `).join('')}
      </div>
      <p class="settings-section-foot">Read-only at runtime. Variant, control mode, dry run, and debug actions are server launch env vars (<code>TS_HARNESS_VARIANT</code> / <code>TS_HARNESS_CONTROL_MODE</code> / <code>TS_HARNESS_DRY_RUN</code> / <code>TS_HARNESS_DEBUG</code>); restart the server to change them.</p>
    </div>

    <div class="settings-section">
      <div class="settings-section-header">Runtime</div>
      <div class="settings-card">
        <div class="settings-row">
          <div class="settings-row-label">
            <div>Iterative candidates (k)</div>
            <div class="settings-row-help">How many parallel methods the iterative-solving node generates per loop.</div>
          </div>
          <div class="settings-row-control">
            ${segmentedHtml('iterativeK', kOptions.map(String), String(state.settings.iterativeK), (v) => v)}
          </div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">
            <div>Knowledge graph extraction depth</div>
            <div class="settings-row-help">How many hops the reference knowledge builder follows per source.</div>
          </div>
          <div class="settings-row-control">
            ${segmentedHtml('graphDepth', depthOptions.map(String), String(state.settings.graphDepth), (v) => v)}
          </div>
        </div>
      </div>
    </div>

    ${renderLlmSection('graph', 'Knowledge Graph Builder LLM', 'Used by the reference knowledge graph builder agent. Leave fields blank to inherit from Main LLM.')}
    ${renderLlmSection('main', 'Main LLM', 'Used by the orchestrator and all node agents. Saved to <code>&lt;workspace&gt;/config.llm.json</code>; takes effect on the next message.', true)}
  `;

  bindSettingsHandlers();
  hydrateIcons(els.settingsContent);
}

function renderLlmSection(prefix: 'graph' | 'main', title: string, description: string, isMain = false): string {
  const s = state.settings;
  const authValue = (isMain ? s.mainAuthMode : s.graphAuthMode) || 'manual';
  const protocolValue = isMain ? s.mainProtocol : s.graphProtocol;
  const contextValue = isMain ? s.mainContext : s.graphContext;
  const modelValue = isMain ? s.mainModel : s.graphModel;
  const baseUrlValue = isMain ? s.mainBaseUrl : s.graphBaseUrl;
  const authOptions = [
    { value: 'manual', label: 'manual' },
    { value: 'sdk-default', label: 'sdk-default' },
  ];
  const protocolOptions = [
    { value: '', label: 'auto' },
    { value: 'anthropic', label: 'anthropic' },
    { value: 'openai-compat', label: 'openai-compat' },
  ];
  const contextOptions = [
    { value: '', label: 'default' },
    { value: '200k', label: '200k' },
    { value: '1m', label: '1m' },
  ];
  const modelPlaceholder = isMain ? 'e.g. deepseek-v4-pro' : 'inherits main model';
  const baseUrlPlaceholder = isMain ? 'https://api.example.com/anthropic' : 'inherits main endpoint';
  const apiKeyPlaceholder = 'leave blank to keep current';
  const saveBtnId = isMain ? 'saveMainLlmBtn' : 'saveGraphLlmBtn2';
  const resetBtnId = isMain ? 'resetMainLlmBtn' : '';
  const modelId = `${prefix}Model`;
  const baseUrlId = `${prefix}BaseUrl`;
  const apiKeyId = `${prefix}ApiKey`;
  return `
    <div class="settings-section">
      <div class="settings-section-header">${escapeHtml(title)}</div>
      <div class="settings-card">
        <div class="settings-row">
          <div class="settings-row-label">Auth</div>
          <div class="settings-row-control">${segmentedHtml(`${prefix}AuthMode`, authOptions.map((o) => o.value), authValue, (v) => v, authOptions.map((o) => o.label))}</div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">Protocol</div>
          <div class="settings-row-control">${segmentedHtml(`${prefix}Protocol`, protocolOptions.map((o) => o.value), protocolValue, (v) => v, protocolOptions.map((o) => o.label))}</div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">Context window</div>
          <div class="settings-row-control">${segmentedHtml(`${prefix}Context`, contextOptions.map((o) => o.value), contextValue, (v) => v, contextOptions.map((o) => o.label))}</div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">Model</div>
          <div class="settings-row-control"><input class="settings-input" type="text" id="${modelId}" value="${escapeHtml(modelValue)}" placeholder="${escapeHtml(modelPlaceholder)}" /></div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">Endpoint</div>
          <div class="settings-row-control"><input class="settings-input" type="text" id="${baseUrlId}" value="${escapeHtml(baseUrlValue)}" placeholder="${escapeHtml(baseUrlPlaceholder)}" /></div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">API key</div>
          <div class="settings-row-control"><input class="settings-input" type="password" id="${apiKeyId}" value="" placeholder="${escapeHtml(apiKeyPlaceholder)}" autocomplete="off" /></div>
        </div>
        <div class="settings-card-footer">
          <button id="${saveBtnId}" type="button" class="settings-primary-btn"><span data-icon="Check"></span><span>${escapeHtml(isMain ? 'Save main LLM' : 'Save builder LLM')}</span></button>
          ${isMain ? `<button id="${resetBtnId}" type="button" class="settings-secondary-btn"><span data-icon="RefreshCw"></span><span>Reset to file default</span></button>` : ''}
          <span class="settings-save-status" id="${prefix}SaveStatus"></span>
        </div>
      </div>
      <p class="settings-section-foot">${description}</p>
    </div>
  `;
}

function segmentedHtml(group: string, values: string[], current: string, format: (v: string) => string = (v) => v, labels: string[] | null = null): string {
  return `
    <div class="settings-segmented" data-segmented-group="${escapeHtml(group)}" role="group">
      ${values.map((v, i) => {
        const label = labels ? labels[i] : format(v);
        const selected = (current || '') === v ? 'selected' : '';
        return `<button type="button" class="settings-segmented-item ${selected}" data-value="${escapeHtml(v)}">${escapeHtml(label)}</button>`;
      }).join('')}
    </div>
  `;
}

function bindSettingsHandlers() {
  for (const group of els.settingsContent.querySelectorAll<HTMLElement>('[data-segmented-group]')) {
    const name = group.dataset.segmentedGroup || '';
    for (const item of group.querySelectorAll<HTMLButtonElement>('.settings-segmented-item')) {
      item.addEventListener('click', () => {
        const value = item.dataset.value || '';
        for (const sibling of group.querySelectorAll<HTMLButtonElement>('.settings-segmented-item')) {
          sibling.classList.toggle('selected', sibling === item);
        }
        if (name === 'iterativeK') {
          state.settings.iterativeK = Number(value) || 3;
          saveRuntimeSettings();
        } else if (name === 'graphDepth') {
          state.settings.graphDepth = Number(value) || 2;
          saveRuntimeSettings();
        } else if (name === 'graphAuthMode') state.settings.graphAuthMode = value;
        else if (name === 'graphProtocol') state.settings.graphProtocol = value;
        else if (name === 'graphContext') state.settings.graphContext = value;
        else if (name === 'mainAuthMode') state.settings.mainAuthMode = value;
        else if (name === 'mainProtocol') state.settings.mainProtocol = value;
        else if (name === 'mainContext') state.settings.mainContext = value;
      });
    }
  }
  for (const input of els.settingsContent.querySelectorAll<HTMLInputElement>('.settings-input')) {
    input.addEventListener('input', () => {
      const id = input.id;
      if (id === 'graphModel') state.settings.graphModel = input.value;
      else if (id === 'graphBaseUrl') state.settings.graphBaseUrl = input.value;
      else if (id === 'graphApiKey') state.settings.graphApiKey = input.value;
      else if (id === 'mainModel') state.settings.mainModel = input.value;
      else if (id === 'mainBaseUrl') state.settings.mainBaseUrl = input.value;
      else if (id === 'mainApiKey') state.settings.mainApiKey = input.value;
    });
  }
  const graphSave = els.settingsContent.querySelector<HTMLButtonElement>('#saveGraphLlmBtn2');
  graphSave?.addEventListener('click', () => saveLlmConfig(false));
  const mainSave = els.settingsContent.querySelector<HTMLButtonElement>('#saveMainLlmBtn');
  mainSave?.addEventListener('click', () => saveLlmConfig(true));
  const mainReset = els.settingsContent.querySelector<HTMLButtonElement>('#resetMainLlmBtn');
  mainReset?.addEventListener('click', () => resetMainLlmConfig());
  for (const copyBtn of els.settingsContent.querySelectorAll<HTMLButtonElement>('[data-copy]')) {
    copyBtn.addEventListener('click', async () => {
      const text = copyBtn.dataset.copy || '';
      try {
        await navigator.clipboard.writeText(text);
        const original = copyBtn.innerHTML;
        copyBtn.innerHTML = '<span data-icon="Check"></span>';
        copyBtn.classList.add('copied');
        hydrateIcons(copyBtn);
        window.setTimeout(() => {
          copyBtn.innerHTML = original;
          copyBtn.classList.remove('copied');
          hydrateIcons(copyBtn);
        }, 1100);
      } catch (error) {
        showDetail('Copy failed', { message: error instanceof Error ? error.message : String(error) });
      }
    });
  }
}

async function saveRuntimeSettings() {
  const result = await postJson('/api/runtime-settings', {
    iterativeCandidateCount: state.settings.iterativeK,
    knowledgeGraphExtractionDepth: state.settings.graphDepth,
  });
  applyBootstrapSnapshot(result.bootstrap);
}

async function saveLlmConfig(isMain: boolean) {
  const s = state.settings;
  const statusSelector = isMain ? '#mainSaveStatus' : '#graphSaveStatus';
  const body: JsonMap = isMain
    ? {
        authMode: s.mainAuthMode,
        protocol: s.mainProtocol,
        model: s.mainModel,
        apiKey: s.mainApiKey || undefined,
        baseUrl: s.mainBaseUrl,
        contextWindow: s.mainContext,
      }
    : {
        authMode: s.graphAuthMode,
        protocol: s.graphProtocol,
        model: s.graphModel,
        apiKey: s.graphApiKey || undefined,
        baseUrl: s.graphBaseUrl,
        contextWindow: s.graphContext,
      };
  try {
    const url = isMain ? '/api/llm-config' : '/api/knowledge-graph/llm-config';
    const result = await postJson(url, body);
    applyBootstrapSnapshot(result.bootstrap);
    // Clear the password field after a successful save.
    if (isMain) {
      state.settings.mainApiKey = '';
      const input = document.getElementById('mainApiKey') as HTMLInputElement | null;
      if (input) input.value = '';
    } else {
      state.settings.graphApiKey = '';
      const input = document.getElementById('graphApiKey') as HTMLInputElement | null;
      if (input) input.value = '';
    }
    const status = els.settingsContent.querySelector<HTMLElement>(statusSelector);
    if (status) {
      status.textContent = 'Saved';
      status.classList.add('saved');
      window.setTimeout(() => {
        status.textContent = '';
        status.classList.remove('saved');
      }, 1800);
    }
  } catch (error) {
    showDetail(isMain ? 'Save main LLM failed' : 'Save builder LLM failed', { message: error instanceof Error ? error.message : String(error) });
  }
}

async function resetMainLlmConfig() {
  if (!confirm('Reset main LLM to file default? This clears model, endpoint, protocol, and context window saved in <workspace>/config.llm.json. API key is kept.')) return;
  try {
    const result = await postJson('/api/llm-config', {
      authMode: 'sdk-default',
      protocol: '',
      model: '',
      baseUrl: '',
      contextWindow: '',
    });
    syncSettingsFromBootstrap(result.bootstrap);
    applyBootstrapSnapshot(result.bootstrap);
  } catch (error) {
    showDetail('Reset main LLM failed', { message: error instanceof Error ? error.message : String(error) });
  }
}

function renderViewState() {
  const graphMode = state.view === 'knowledgeGraph';
  const chainMode = state.view === 'chainSummary';
  const imageMode = state.view === 'imageViewer';
  const settingsMode = state.view === 'settings';
  els.chatStream.hidden = graphMode || chainMode || imageMode || settingsMode;
  els.knowledgeGraphView.hidden = !graphMode;
  els.chainSummaryView.hidden = !chainMode;
  els.imageViewerView.hidden = !imageMode;
  els.settingsView.hidden = !settingsMode;
  els.sendForm.hidden = graphMode || chainMode || imageMode || settingsMode;
  els.transcriptScope.disabled = graphMode || chainMode || imageMode;
  query('#mainTitle').textContent = graphMode ? 'Knowledge Graph' : chainMode ? '思维链总结' : imageMode ? '图片查看' : settingsMode ? 'Settings' : 'Orchestrator';
  document.body.classList.toggle('knowledge-page', graphMode);
  document.body.classList.toggle('chain-page', chainMode);
  document.body.classList.toggle('image-page', imageMode);
  document.body.classList.toggle('settings-page', settingsMode);
}

function renderChainSummary(data: Bootstrap) {
  if (state.view !== 'chainSummary') return;
  const build = data.chainSummaryBuild || {};
  const summary = data.chainSummary || {};
  const running = Boolean(data.runtime?.chainSummaryRunning || build.running);
  const iterations = Array.isArray(summary.iterations) ? summary.iterations.length : 0;
  const metrics = Array.isArray(summary.metricSeries) ? summary.metricSeries.length : 0;
  const samples = Array.isArray(summary.iterations)
    ? summary.iterations.reduce((count: number, iteration: JsonMap) => count + (Array.isArray(iteration.sampleInspirations) ? iteration.sampleInspirations.length : 0), 0)
    : 0;
  els.buildChainSummaryBtn.disabled = running;
  const statusSignature = stableStringify({
    status: build.status || 'idle',
    running,
    message: build.message || '',
    iterations,
    metrics,
    samples,
  });
  if (statusSignature !== state.chainStatusSignature) {
    state.chainStatusSignature = statusSignature;
    els.chainBuildStatus.innerHTML = `
    <div class="chain-status-main">
      <span class="mini-pill ${build.status === 'failed' ? 'failed' : running ? 'active' : build.status === 'completed' ? 'ready' : 'pending'}">
        ${running ? '<span data-icon="Loader2"></span>' : ''}
        ${escapeHtml(running ? 'running' : build.status || 'idle')}
      </span>
      <span class="meta">${escapeHtml(build.message || 'Chain builder uses the current workspace logs and artifacts.')}</span>
    </div>
    <div class="chain-status-stats">
      <span><strong>${escapeHtml(iterations)}</strong><small>Iterations</small></span>
      <span><strong>${escapeHtml(metrics)}</strong><small>Metrics</small></span>
      <span><strong>${escapeHtml(samples)}</strong><small>Samples</small></span>
    </div>
  `;
  }
  const chartSignature = stableStringify(summary.metricSeries || []);
  if (chartSignature !== state.chainChartSignature) {
    state.chainChartSignature = chartSignature;
    renderChainMetricChart(summary.metricSeries || []);
  }
  const contentSignature = stableStringify({
    status: build.status || '',
    message: build.status === 'failed' ? build.message || '' : '',
    title: summary.title || '',
    generatedAt: summary.generatedAt || '',
    overview: summary.overview || '',
    uncertainty: summary.uncertainty || [],
    iterations: summary.iterations || [],
  });
  if (contentSignature !== state.chainContentSignature) {
    state.chainContentSignature = contentSignature;
    renderChainContent(summary, build);
  }
}

function renderChainMetricChart(series: JsonMap[]) {
  const cleaned = (series || []).filter((item) =>
    Array.isArray(item.values) && item.values.some((value: JsonMap) => Number.isFinite(Number(value.value)))
  );
  if (!cleaned.length) {
    els.chainMetricChart.innerHTML = emptyState('生成后将在这里展示多个关键指标随 iteration 的变化。', 'Activity');
    return;
  }
  els.chainMetricChart.innerHTML = `
    <div class="panel-heading"><span data-icon="Activity"></span><span>指标 x Iterations</span></div>
    <div class="metric-chart-grid">
      ${cleaned.map(metricChartHtml).join('')}
    </div>
  `;
}

function metricChartHtml(series: JsonMap) {
  const values = bestMetricValuesByIteration(series);
  const numeric = values.map((item) => Number(item.value)).filter((value) => Number.isFinite(value));
  const min = Math.min(...numeric);
  const max = Math.max(...numeric);
  const spread = max - min || 1;
  const width = Math.max(520, (values.length - 1) * 82 + 96);
  const height = 180;
  const padX = 48;
  const padY = 38;
  const points = values.map((item, index) => {
    const value = Number(item.value);
    const x = values.length === 1 ? width / 2 : padX + (index * (width - padX * 2)) / (values.length - 1);
    const rawY = height - padY - ((value - min) / spread) * (height - padY * 2);
    const y = Math.max(32, Math.min(height - 32, rawY));
    return {
      x,
      y,
      value,
      label: iterationAxisLabel(item.iteration, index),
      note: item.label && item.label !== item.iteration ? String(item.label) : '',
    };
  });
  const polyline = points.map((point) => `${point.x},${point.y}`).join(' ');
  return `
    <article class="metric-chart-card">
      <div class="metric-chart-title">
        <span>${escapeHtml(series.name || 'metric')}</span>
        <span class="meta">${escapeHtml(series.unit || series.direction || '')}</span>
      </div>
      <div class="metric-chart-scroll">
        <div class="metric-chart-stage" style="min-width:${width}px">
          <svg class="metric-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(series.name || 'metric')}">
            <line class="metric-axis" x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}"></line>
            <polyline class="metric-line" points="${polyline}"></polyline>
            ${points.map((point) => `
              <g class="metric-point" transform="translate(${point.x} ${point.y})">
                <circle r="5"></circle>
                <text y="-11">${escapeHtml(formatMetricValue(point.value))}</text>
              </g>
            `).join('')}
          </svg>
          <div class="metric-labels">
            ${points.map((point) => `<span style="left:${(point.x / width) * 100}%" title="${escapeHtml(point.note || point.label)}">${escapeHtml(point.label)}</span>`).join('')}
          </div>
        </div>
      </div>
    </article>
  `;
}

function bestMetricValuesByIteration(series: JsonMap): JsonMap[] {
  const direction = String(series.direction || 'neutral');
  const values: JsonMap[] = (series.values || []).filter((item: JsonMap) => Number.isFinite(Number(item.value)));
  const grouped = new Map<string, JsonMap>();
  for (const item of values) {
    const key = String(item.iteration || item.label || grouped.size + 1);
    const current = grouped.get(key);
    if (!current || isBetterMetricValue(Number(item.value), Number(current.value), direction)) {
      grouped.set(key, { ...item, iteration: key });
    }
  }
  return [...grouped.values()].sort((a, b) => iterationSortKey(a.iteration) - iterationSortKey(b.iteration));
}

function isBetterMetricValue(next: number, current: number, direction: string) {
  if (direction === 'lower') return next < current;
  if (direction === 'neutral') return Math.abs(next) > Math.abs(current);
  return next > current;
}

function iterationAxisLabel(value: any, index: number) {
  const text = String(value || '').trim();
  const match = text.match(/(?:iteration|iter|it)[^\d]*(\d+)/i) || text.match(/(\d+)/);
  if (match) return String(Number(match[1]));
  return String(index + 1);
}

function iterationSortKey(value: any) {
  const match = String(value || '').match(/(\d+)/);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

function renderChainContent(summary: JsonMap, build: JsonMap = {}) {
  const iterations: JsonMap[] = summary.iterations || [];
  const generated = build.status === 'completed';
  if (!generated) {
    els.chainSummaryContent.innerHTML = `
      <div class="chain-placeholder">
        <span data-icon="Activity"></span>
        <h3>等待生成思维链总结</h3>
        <p>${escapeHtml(build.status === 'failed' ? build.message || '生成失败，请检查 chain builder 日志。' : '点击上方按钮后，chain builder 会读取当前 workspace 的 logs、reports、runs 和样本可视化，生成完整决策链。')}</p>
      </div>
    `;
    return;
  }
  if (!iterations.length && !summary.overview) {
    els.chainSummaryContent.innerHTML = emptyState('chain builder 已完成，但没有可展示的总结内容。', 'Info');
    return;
  }
  els.chainSummaryContent.innerHTML = `
    <article class="chain-overview">
      <div class="panel-heading"><span data-icon="Sparkles"></span><span>${escapeHtml(summary.title || '思维链总结')}</span></div>
      ${summary.generatedAt ? `<div class="meta">Generated ${escapeHtml(formatTime(summary.generatedAt))}</div>` : ''}
      <div class="markdown-body">${renderMarkdown(summary.overview || '')}</div>
      ${Array.isArray(summary.uncertainty) && summary.uncertainty.length ? `
        <details class="chain-uncertainty">
          <summary><span data-icon="AlertTriangle"></span><span>Warnings / 信息缺口</span><span class="chain-warning-count">${summary.uncertainty.length}</span></summary>
          <div class="chain-uncertainty-list">
            ${summary.uncertainty.map((item: any) => `<span><span data-icon="AlertTriangle"></span>${escapeHtml(item)}</span>`).join('')}
          </div>
        </details>
      ` : ''}
    </article>
    <div class="chain-iterations">
      ${iterations.map((iteration, index) => chainIterationHtml(iteration, index, iterations.length)).join('')}
    </div>
  `;
  for (const item of els.chainSummaryContent.querySelectorAll<HTMLElement>('[data-chain-path]')) {
    item.addEventListener('click', async () => showWorkspaceFile(item.dataset.chainPath || ''));
  }
  for (const item of els.chainSummaryContent.querySelectorAll<HTMLElement>('[data-chain-image]')) {
    item.addEventListener('click', () => openChainImage(item.dataset.chainImage || ''));
  }
}

function chainIterationHtml(iteration: JsonMap, index: number, total: number) {
  const methods: JsonMap[] = iteration.methods || [];
  const results: JsonMap[] = Array.isArray(iteration.methodResults) && iteration.methodResults.length ? iteration.methodResults : iteration.testResults || [];
  const samples: JsonMap[] = iteration.sampleInspirations || [];
  const methodRows = pairMethodResults(methods, results);
  return `
    <article class="chain-iteration-card">
      <header class="chain-iteration-head">
        <div class="chain-iteration-id"><span>Iteration</span>${escapeHtml(iteration.iterationId || 'iteration')}</div>
      </header>
      <section class="chain-card-section">
      <div class="detail-section-title"><span class="chain-section-index">1</span><span>提出方法</span></div>
      ${methodRows.length ? `<div class="chain-method-result-list">${methodRows.map(methodResultRowHtml).join('')}</div>` : emptyState('没有可审计的方法与测试结果记录。', 'Info')}
      </section>
      <section class="chain-card-section">
      <div class="detail-section-title"><span class="chain-section-index">2</span><span>样本启发</span></div>
      ${samples.length ? `<div class="chain-samples">${samples.map(chainSampleHtml).join('')}</div>` : emptyState('没有记录样本级启发。', 'Info')}
      </section>
      ${nextDecisionHtml(iteration.nextDecision || { decision: iteration.nextStep || '' })}
    </article>
    ${index < total - 1 ? `
      <div class="chain-transition-arrow" aria-label="该决策指导下一轮提出方法">
        <span>该决策指导下一轮提出方法</span>
        <span data-icon="ArrowDown"></span>
      </div>
    ` : ''}
  `;
}

function nextDecisionHtml(decision: JsonMap) {
  const knowledge: JsonMap[] = Array.isArray(decision.domainKnowledge) ? decision.domainKnowledge : [];
  const actions: JsonMap[] = Array.isArray(decision.actions) ? decision.actions : [];
  return `
    <section class="chain-card-section chain-next-decision">
      <div class="detail-section-title"><span class="chain-section-index">3</span><span>下轮决策</span><span class="chain-core-label">思维链核心</span></div>
      <p class="chain-decision-lead">${escapeHtml(decision.decision || '没有记录下轮决策。')}</p>
      ${decision.iterationEvidence ? `
        <div class="chain-decision-evidence">
          <strong>本轮证据</strong>
          <p>${escapeHtml(decision.iterationEvidence)}</p>
        </div>
      ` : ''}
      <div class="chain-decision-subtitle">领域知识如何指导决策</div>
      ${knowledge.length ? `
        <div class="chain-knowledge-list">
          ${knowledge.map((item, knowledgeIndex) => `
            <article class="chain-knowledge-item">
              <span class="chain-knowledge-index">K${knowledgeIndex + 1}</span>
              <div>
                <strong>${escapeHtml(item.knowledge || '未命名领域知识')}</strong>
                <p>${escapeHtml(item.guidance || '')}</p>
                ${item.sourcePath ? `<button type="button" class="artifact-item" data-chain-path="${escapeHtml(item.sourcePath)}"><span data-icon="File"></span><span>${escapeHtml(item.sourcePath)}</span></button>` : ''}
              </div>
            </article>
          `).join('')}
        </div>
      ` : `<div class="chain-decision-missing">${decision.legacy ? '这是旧版报告，未记录领域知识与决策的映射。请重新生成思维链总结。' : '未记录领域知识与决策的映射。'}</div>`}
      <div class="chain-decision-subtitle">下一轮执行与验证</div>
      ${actions.length ? `
        <div class="chain-action-list">
          ${actions.map((item, actionIndex) => `
            <article class="chain-action-item">
              <strong>${actionIndex + 1}. ${escapeHtml(item.action || '未命名动作')}</strong>
              <p><span>预期效果</span>${escapeHtml(item.expectedEffect || '')}</p>
              <p><span>验证方式</span>${escapeHtml(item.validation || '')}</p>
            </article>
          `).join('')}
        </div>
      ` : `<div class="chain-decision-missing">未记录可执行且可验证的下一轮计划。</div>`}
    </section>
  `;
}

function pairMethodResults(methods: JsonMap[], results: JsonMap[]) {
  const count = Math.max(methods.length, results.length);
  const resultByMethod = new Map<string, JsonMap>();
  for (const result of results) {
    const key = String(result.methodName || result.method || result.name || '').trim().toLowerCase();
    if (key) resultByMethod.set(key, result);
  }
  return Array.from({ length: count }, (_, index) => {
    const method = methods[index] || {};
    const key = String(method.name || '').trim().toLowerCase();
    const result = (key && resultByMethod.get(key)) || results[index] || {};
    return { method, result, index };
  });
}

function methodResultRowHtml(row: { method: JsonMap; result: JsonMap; index: number }) {
  const method = row.method || {};
  const result = row.result || {};
  const fallbackName = `Candidate ${row.index + 1}`;
  const methodName = method.name || result.methodName || result.method || fallbackName;
  const metric = result.metric || 'result';
  return `
    <div class="chain-method-result-row">
      <section class="chain-mini-card chain-method-card">
        <div class="chain-card-eyebrow">Candidate ${row.index + 1} · 方法</div>
        <strong>${escapeHtml(methodName)}</strong>
        <p>${escapeHtml(method.hypothesis || '')}</p>
        ${method.artifactPath ? `<button type="button" class="artifact-item" data-chain-path="${escapeHtml(method.artifactPath)}"><span data-icon="File"></span><span>${escapeHtml(method.artifactPath)}</span></button>` : ''}
      </section>
      <section class="chain-mini-card chain-result-card">
        <div class="chain-card-eyebrow">Candidate ${row.index + 1} · 测试结果</div>
        <strong>${escapeHtml(metric)}${result.value ? `: ${escapeHtml(result.value)}` : ''}</strong>
        <p>${escapeHtml(result.interpretation || '')}</p>
        ${result.evidencePath ? `<button type="button" class="artifact-item" data-chain-path="${escapeHtml(result.evidencePath)}"><span data-icon="File"></span><span>${escapeHtml(result.evidencePath)}</span></button>` : ''}
      </section>
    </div>
  `;
}

function chainSampleHtml(sample: JsonMap) {
  const path = String(sample.visualizationPath || '').trim();
  const previewable = isPreviewableImage(path);
  const image = previewable
    ? `<button type="button" class="chain-sample-image-button" data-chain-image="${escapeHtml(path)}" aria-label="查看 ${escapeHtml(sample.sampleId || 'sample visualization')}"><img src="/api/files/preview?path=${encodeURIComponent(path)}" alt="${escapeHtml(sample.sampleId || 'sample visualization')}" loading="lazy" /></button>`
    : '';
  return `
    <article class="chain-sample-card">
      ${image || `<div class="sample-image-placeholder"><span data-icon="File"></span></div>`}
      <div>
        <div class="chain-sample-title">${escapeHtml(sample.sampleId || 'sample')}</div>
        ${path ? `<button type="button" class="artifact-item" ${previewable ? `data-chain-image="${escapeHtml(path)}"` : `data-chain-path="${escapeHtml(path)}"`}><span data-icon="File"></span><span>${escapeHtml(path)}</span></button>` : ''}
        <p>${escapeHtml(sample.interpretation || '')}</p>
        <p class="meta">${escapeHtml(sample.nextIterationImpact || '')}</p>
      </div>
    </article>
  `;
}

function openChainImage(path: string) {
  const normalized = String(path || '').trim();
  if (!normalized || !isPreviewableImage(normalized)) return;
  state.selectedImagePath = normalized;
  state.view = 'imageViewer';
  history.pushState({}, '', `/image-viewer?path=${encodeURIComponent(normalized)}`);
  render();
}

function renderImageViewer() {
  const path = String(state.selectedImagePath || '').trim();
  if (!path) {
    els.imageViewerTitle.textContent = '未选择图片';
    els.imageViewerImage.removeAttribute('src');
    els.imageViewerImage.hidden = true;
    els.imageViewerPath.textContent = '';
    return;
  }
  els.imageViewerTitle.textContent = path.split('/').pop() || '样本可视化';
  els.imageViewerImage.src = `/api/files/preview?path=${encodeURIComponent(path)}`;
  els.imageViewerImage.alt = path;
  els.imageViewerImage.hidden = false;
  els.imageViewerPath.innerHTML = `<span data-icon="File"></span><code>${escapeHtml(path)}</code>`;
}

function renderKnowledgeGraphBuilder(data: Bootstrap) {
  const build = data.knowledgeGraphBuild || {};
  const config = data.knowledgeGraphLlmConfig?.config || {};
  const running = Boolean(data.runtime?.knowledgeGraphRunning || build.running);
  const knowledgeEnabled = data.variant?.capabilities?.knowledgeGraph !== false;
  const canContinue = !running && ['paused', 'failed'].includes(String(build.status || ''));
  els.graphBuildStatus.innerHTML = `
    <span class="mini-pill ${build.status === 'failed' ? 'failed' : running ? 'active' : build.status === 'completed' ? 'ready' : 'pending'}">
      ${running ? '<span data-icon="Loader2"></span>' : ''}
      ${escapeHtml(!knowledgeEnabled ? `disabled · ${data.variant?.id || 'variant'}` : running ? 'running' : build.status || 'idle')}
    </span>
    <span class="meta">${escapeHtml(build.message || '')}</span>
  `;
  if (els.graphAuthMode.value !== (config.authMode || 'manual')) els.graphAuthMode.value = config.authMode || 'manual';
  if (els.graphProtocol.value !== (config.protocol || '')) els.graphProtocol.value = config.protocol || '';
  if (els.graphModelInput.value !== (config.model || '')) els.graphModelInput.value = config.model || '';
  if (els.graphBaseUrlInput.value !== (config.baseUrl || '')) els.graphBaseUrlInput.value = config.baseUrl || '';
  els.buildGraphBtn.disabled = running || !knowledgeEnabled;
  els.continueGraphBtn.disabled = !canContinue || !knowledgeEnabled;
  els.pauseGraphBtn.disabled = !running || !knowledgeEnabled;
  els.graphExtractionDepthInput.disabled = running || !knowledgeEnabled;
  els.saveGraphLlmBtn.disabled = !knowledgeEnabled;
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
  if (part.type === 'tool_call' || part.type === 'tool_use' || part.type === 'tool_result') {
    const summary = toolSummary(part);
    const detail = toolDetail(part);
    const toolName = toolNameForPart(part);
    const done = part.type === 'tool_result' || part.status === 'completed';
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
  if (part.type === 'tool_call') {
    const intend = typeof part.intend === 'string' && part.intend.trim() ? part.intend.trim() : '';
    return intend || `调用工具：${toolNameForPart(part)}`;
  }
  if (part.type === 'tool_use') {
    const name = part.name || part.raw?.message?.content?.find?.((block: JsonMap) => block.type === 'tool_use')?.name || 'tool';
    const input = part.input || part.raw?.message?.content?.find?.((block: JsonMap) => block.type === 'tool_use')?.input;
    const intend = input?.intend;
    if (typeof intend === 'string' && intend.trim()) return intend.trim();
    const hint = input && typeof input === 'object' ? Object.keys(input).slice(0, 3).join(', ') : '';
    return hint ? `调用工具：${name} (${hint})` : `调用工具：${name}`;
  }
  const text = part.displayText || part.text || '';
  const firstLine = text.split('\n').find((line: string) => line.trim()) || '工具结果';
  return firstLine.length > 120 ? `${firstLine.slice(0, 117)}...` : firstLine;
}

function toolDetail(part: JsonMap) {
  if (part.type === 'tool_call') {
    const chunks = [
      `Tool: ${toolNameForPart(part)}`,
      `Status: ${part.status || 'pending'}`,
      '',
      '调用意图:',
      part.intend || '',
      '',
      '调用参数:',
      JSON.stringify(part.input ?? {}, null, 2),
    ];
    if (part.status === 'completed' || part.resultText || part.resultRaw) {
      chunks.push('', '调用结果:', part.resultText || toolResultTextFromRaw(part.resultRaw) || summarizeRaw(part.resultRaw) || '');
    } else {
      chunks.push('', '调用结果:', '等待工具返回结果。');
    }
    return chunks.join('\n');
  }
  return part.displayText || part.text || summarizeRaw(part.raw) || '';
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
    .filter((part) => !isPendingPartLogged(part, loggedUserTexts))
    .map((part) => ({ ...part, sortKey: `${part.timestamp || ''}:pending:${part.id || ''}` }));
  if (scope === 'main') return [...mainParts, ...pendingParts].sort(sortByKey);
  if (scope.startsWith('node:')) {
    const nodeId = scope.slice('node:'.length);
    return nodeParts.filter((part) => part.nodeSessionId === nodeId || part.sortKey.includes(`:node:${nodeId}:`)).sort(sortByKey);
  }
  return [...mainParts, ...nodeParts, ...pendingParts].sort(sortByKey);
}

function collectLoadingParts(): JsonMap[] {
  const scope = state.transcriptScope || 'all';
  if (!state.loadingMessage || scope.startsWith('node:')) return [];
  return normalizeChatParts([{ ...state.loadingMessage }]);
}

function reconcilePendingParts(data: Bootstrap | null): JsonMap[] {
  if (!data) return state.pendingParts;
  const loggedUserTexts = new Set((data.mainParts || [])
    .filter((part: JsonMap) => part.role === 'user' && part.text)
    .map((part: JsonMap) => normalizePendingText(part.text)));
  const unresolved = state.pendingParts.filter((part) => !isPendingPartLogged(part, loggedUserTexts));
  return data.runtime?.running ? unresolved : [];
}

function isPendingPartLogged(part: JsonMap, loggedUserTexts: Set<string>): boolean {
  return Boolean(part.role === 'user' && part.text && loggedUserTexts.has(normalizePendingText(part.text)));
}

function normalizePendingText(text: string): string {
  return String(text).trim();
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
    'thinking_tokens',
  ]);
  return parts
    .map((part: JsonMap) => ({ ...part, displayText: displayTextForPart(part) }))
    .filter((part: JsonMap) => {
      if (part.type === 'loading') return true;
      if (!part.displayText.trim()) return false;
      if (part.role === 'system' && part.type === 'raw') {
        const subtype = part.raw?.subtype || part.text || part.displayText || '';
        const normalizedSubtype = subtype.trim();
        if (SUPPRESS_SYSTEM_SUBTYPES.has(normalizedSubtype) || normalizedSubtype.endsWith('_tokens')) return false;
      }
      if (part.role === 'system' && part.type === 'result' && part.raw?.is_error !== true) return false;
      return true;
    });
}

function displayTextForPart(part: JsonMap) {
  if (part.type === 'loading') return part.text || '运行中';
  if (part.type === 'tool_call') {
    return part.intend || `调用工具：${toolNameForPart(part)}`;
  }
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
    state.busy = false;
    state.loadingMessage = null;
    render();
    showDetail('Error', { message: error instanceof Error ? error.message : String(error) });
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

function variantPill(variant: JsonMap | null | undefined) {
  if (!variant?.id) return '<span class="mini-pill pending">-</span>';
  const id = String(variant.id).toUpperCase();
  const label = `${id} · ${variant.name || 'Unknown variant'}`;
  return `<span class="mini-pill variant-pill variant-${escapeHtml(id.toLowerCase())}" title="${escapeHtml(variant.description || label)}">${escapeHtml(label)}</span>`;
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
  const leftIcon = state.leftCollapsed ? 'ChevronRight' : 'ChevronLeft';
  const rightIcon = state.rightCollapsed ? 'ChevronLeft' : 'ChevronRight';
  if (els.leftRailToggle.dataset.currentIcon !== leftIcon) {
    els.leftRailToggle.dataset.currentIcon = leftIcon;
    els.leftRailToggle.innerHTML = `<span data-icon="${leftIcon}"></span>`;
    hydrateIcons(els.leftRailToggle);
  }
  if (els.rightRailToggle.dataset.currentIcon !== rightIcon) {
    els.rightRailToggle.dataset.currentIcon = rightIcon;
    els.rightRailToggle.innerHTML = `<span data-icon="${rightIcon}"></span>`;
    hydrateIcons(els.rightRailToggle);
  }
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
  if (els.sendBtn.dataset.currentIcon !== icon) {
    els.sendBtn.dataset.currentIcon = icon;
    els.sendBtn.innerHTML = `<span data-icon="${icon}"></span>`;
    hydrateIcons(els.sendBtn);
  }
  els.sendBtn.title = activePaused ? '继续当前 node' : '发送';
  els.sendBtn.classList.toggle('ready', canSend);
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
    applyBootstrapSnapshot(result.bootstrap);
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
      try {
        await waitForRealtimeState((data) => !data.runtime?.running, 2500);
      } catch {
        await sleep(300);
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
  await waitForRealtimeState((data) => !data.runtime?.running, timeoutMs);
}

function waitForRealtimeState(predicate: (data: Bootstrap) => boolean, timeoutMs: number) {
  if (state.bootstrap && predicate(state.bootstrap)) return Promise.resolve(state.bootstrap);
  return new Promise<Bootstrap>((resolve, reject) => {
    const waiter = {
      predicate,
      resolve,
      reject,
      timer: window.setTimeout(() => {
        state.realtimeWaiters = state.realtimeWaiters.filter((candidate) => candidate !== waiter);
        reject(new Error('Timed out waiting for a realtime state update.'));
      }, timeoutMs),
    };
    state.realtimeWaiters.push(waiter);
  });
}

function resolveRealtimeWaiters(data: Bootstrap) {
  for (const waiter of [...state.realtimeWaiters]) {
    if (!waiter.predicate(data)) continue;
    window.clearTimeout(waiter.timer);
    state.realtimeWaiters = state.realtimeWaiters.filter((candidate) => candidate !== waiter);
    waiter.resolve(data);
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

function formatMetricValue(value: number) {
  if (!Number.isFinite(value)) return '';
  const abs = Math.abs(value);
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1);
  return value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
}

function isPreviewableImage(path: string) {
  return /\.(png|jpe?g|webp|gif|svg)$/i.test(path);
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

function resetChainRenderSignatures() {
  state.chainStatusSignature = '';
  state.chainChartSignature = '';
  state.chainContentSignature = '';
}

function stableStringify(value: any) {
  return JSON.stringify(value ?? null);
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

connectRealtimeEvents();
