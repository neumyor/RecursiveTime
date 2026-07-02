import './styles.css';
import { deleteJson, fetchJson, postForm, postJson } from './api';
import DOMPurify from 'dompurify';
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force';
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
  RotateCcw,
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
  knowledgeGraphTab: 'graph' as 'graph' | 'trace',
  graphInfoCollapsed: false,
  chainNavCollapsed: false,
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
        <p>时间序列智能工作台</p>
      </div>
    </section>

    <div class="main-left-content">
    <section class="panel status-panel">
      <div class="panel-heading">
        <span data-icon="Gauge"></span>
        <span>工作区</span>
      </div>
      <dl class="kv">
        <dt>状态</dt>
        <dd id="statusText">加载中</dd>
        <dt>模式</dt>
        <dd id="modeText">-</dd>
        <dt>流程</dt>
        <dd id="variantText">-</dd>
        <dt>模型</dt>
        <dd id="modelText">-</dd>
        <dt>环境</dt>
        <dd id="runtimeUvText">-</dd>
      </dl>
      <button id="settingsBtn" type="button" class="workspace-settings-btn"><span data-icon="SlidersHorizontal"></span><span>工作区设置</span></button>
    </section>

    <section id="pendingControlPanel" class="panel control-panel" hidden>
      <div class="panel-heading">
        <span data-icon="ShieldCheck"></span>
        <span>等待确认</span>
      </div>
      <div id="pendingControlBody" class="control-body"></div>
      <div class="split-actions">
        <button id="approveControlBtn" type="button" class="success-btn"><span data-icon="Check"></span><span>同意</span></button>
        <button id="rejectControlBtn" type="button" class="danger ghost"><span data-icon="X"></span><span>拒绝</span></button>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <span data-icon="GitBranch"></span>
        <span>节点流程</span>
      </div>
      <div id="nodeList" class="node-list"></div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <span data-icon="Boxes"></span>
        <span>当前节点</span>
      </div>
      <div id="nodeDetail" class="node-detail"></div>
    </section>

    <details class="panel timeline-panel">
      <summary class="panel-heading">
        <span data-icon="Clock3"></span>
        <span>时间线</span>
      </summary>
      <div id="timeline" class="timeline"></div>
    </details>
    </div>

    <div class="graph-left-content">
      <section class="panel graph-control-card">
        <div class="panel-heading">
          <span data-icon="Settings2"></span>
          <span>构建设置</span>
        </div>
        <div id="graphBuildStatus" class="graph-build-status"></div>
        <div id="graphLeftActions" class="graph-left-actions">
          <button id="buildGraphBtn" type="button"><span data-icon="RefreshCw"></span><span>构建</span></button>
          <button id="rebuildGraphBtn" type="button" class="rebuild" hidden><span data-icon="RotateCcw"></span><span>重建</span></button>
          <button id="continueGraphBtn" type="button" class="secondary"><span data-icon="Play"></span><span>继续</span></button>
          <button id="pauseGraphBtn" type="button" class="danger ghost"><span data-icon="Pause"></span><span>暂停</span></button>
        </div>
      </section>

      <details class="panel graph-settings-card">
        <summary class="panel-heading">
          <span data-icon="SlidersHorizontal"></span>
          <span>详细设置</span>
        </summary>
        <div class="graph-settings-body">
        <label>
          <span>抽取深度</span>
          <input id="graphExtractionDepthInput" type="number" min="1" max="4" step="1" />
        </label>
        <label>
          <span>认证方式</span>
          <select id="graphAuthMode">
            <option value="manual">手动配置</option>
            <option value="sdk-default">SDK 默认</option>
          </select>
        </label>
        <label>
          <span>协议</span>
          <select id="graphProtocol">
            <option value="">自动</option>
            <option value="anthropic">anthropic</option>
            <option value="openai-compat">openai-compat</option>
          </select>
        </label>
        <label>
          <span>模型</span>
          <input id="graphModelInput" type="text" placeholder="默认继承主模型" />
        </label>
        <label>
          <span>接口地址</span>
          <input id="graphBaseUrlInput" type="text" placeholder="默认继承主接口地址" />
        </label>
        <label>
          <span>API 密钥</span>
          <input id="graphApiKeyInput" type="password" placeholder="留空表示保持当前密钥" />
        </label>
        <button id="saveGraphLlmBtn" type="button" class="secondary full-width"><span data-icon="Check"></span><span>保存构建模型</span></button>
        </div>
      </details>

      <section class="panel">
        <div class="panel-heading">
          <span data-icon="Gauge"></span>
          <span>知识库</span>
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
          <div class="eyebrow"><span data-icon="Bot"></span><span>主会话</span></div>
          <h2 id="mainTitle">任务编排</h2>
        </div>
        <label class="transcript-filter">
          <span>记录范围</span>
          <select id="transcriptScope"></select>
        </label>
      </div>
      <div class="toolbar-actions">
        <button id="resetChatBtn" type="button" class="ghost debug-only"><span data-icon="RefreshCw"></span><span>重置会话</span></button>
        <button id="clearAllLogsBtn" type="button" class="danger ghost debug-only"><span data-icon="Trash2"></span><span>重置工作区</span></button>
      </div>
    </header>

    <section id="chatStream" class="chat-stream"></section>
    <button id="chatTopBtn" type="button" class="chat-top-btn" title="回到顶部" aria-label="回到顶部"><span data-icon="ArrowUp"></span></button>

    <section id="settingsView" class="settings-view" hidden>
      <header class="settings-header">
        <div class="settings-header-inner">
          <div class="settings-header-text">
            <div class="settings-eyebrow"><span data-icon="SlidersHorizontal"></span><span>工作区</span></div>
            <h1 class="settings-title">设置</h1>
            <p class="settings-subtitle">这里集中管理当前工作区的运行参数和模型配置。部分改动会立即生效，部分会在下一条消息后生效。</p>
          </div>
          <div class="settings-header-actions">
            <button id="settingsDoneBtn" type="button" class="settings-done-btn"><span data-icon="ChevronLeft"></span><span>返回主会话</span></button>
          </div>
        </div>
      </header>
      <div id="settingsContent" class="settings-content"></div>
    </section>
    <section id="knowledgeGraphView" class="knowledge-graph-view" hidden>
      <div class="graph-header">
        <div class="graph-title-block">
          <div class="eyebrow"><span data-icon="Network"></span><span>知识图谱</span></div>
          <h2 id="graphTitle">参考知识</h2>
        </div>
        <div class="graph-header-actions">
          <button id="backToChatBtn" type="button" class="graph-back-button"><span data-icon="ChevronLeft"></span><span>返回主会话</span></button>
        </div>
      </div>
      <nav class="graph-tabs" aria-label="知识图谱页面切换">
        <button id="graphTabTrace" type="button" class="graph-tab" data-graph-tab="trace"><span data-icon="TerminalSquare"></span><span>构建过程</span></button>
        <button id="graphTabGraph" type="button" class="graph-tab active" data-graph-tab="graph"><span data-icon="Network"></span><span>知识图谱</span></button>
      </nav>
      <div id="graphTracePanel" class="graph-tab-panel graph-trace-panel" hidden>
        <section class="builder-trace-panel">
          <div class="panel-heading">
            <span data-icon="TerminalSquare"></span>
            <span>构建过程记录</span>
          </div>
          <div id="builderTrace" class="builder-trace"></div>
        </section>
      </div>
      <div id="graphKnowledgePanel" class="graph-tab-panel graph-knowledge-panel">
        <div id="graphLayout" class="graph-layout">
          <div id="graphCanvas" class="graph-canvas"></div>
          <button id="graphInfoToggle" class="graph-info-toggle" type="button" title="折叠图谱信息"><span data-icon="ChevronRight"></span></button>
          <aside id="graphInfoPanel" class="graph-inspector-shell">
            <header class="graph-inspector-header">
              <span data-icon="Info"></span>
              <span>图谱信息</span>
            </header>
            <section id="graphInspector" class="graph-inspector"></section>
          </aside>
        </div>
      </div>
    </section>

    <section id="chainSummaryView" class="chain-summary-view" hidden>
      <header class="chain-header">
        <div class="chain-title-block">
          <div class="eyebrow"><span data-icon="Activity"></span><span>流程总结</span></div>
          <h2>思维链总结</h2>
          <p>把当前工作区的日志、迭代报告、运行结果和样本证据组织成一条可审计的决策链。</p>
        </div>
        <div class="chain-header-actions">
          <button id="backToChatFromChainBtn" type="button" class="chain-back-btn"><span data-icon="ChevronLeft"></span><span>返回主会话</span></button>
          <button id="buildChainSummaryBtn" type="button" class="chain-generate-btn"><span data-icon="RefreshCw"></span><span>生成思维链总结</span></button>
        </div>
      </header>
      <div id="chainBody" class="chain-body">
        <button id="chainNavToggle" class="chain-nav-toggle" type="button" title="折叠目录"><span data-icon="ChevronLeft"></span></button>
        <aside id="chainNav" class="chain-nav">
          <div class="chain-nav-heading"><span data-icon="GitBranch"></span><span>导航窗格</span></div>
          <nav id="chainNavContent" class="chain-nav-content" aria-label="思维链总结目录"></nav>
        </aside>
        <div id="chainMainScroll" class="chain-main-scroll">
          <section id="chainBuildStatus" class="chain-build-status chain-anchor"></section>
          <section id="chainMetricChart" class="chain-chart-panel"></section>
          <section id="chainSummaryContent" class="chain-content-panel"></section>
        </div>
      </div>
    </section>

    <section id="imageViewerView" class="image-viewer-view" hidden>
      <header class="image-viewer-header">
        <div>
          <div class="eyebrow"><span data-icon="Activity"></span><span>总结图片</span></div>
          <h2 id="imageViewerTitle">样本可视化</h2>
        </div>
        <button id="backToChainFromImageBtn" type="button" class="chain-back-btn"><span data-icon="ChevronLeft"></span><span>返回思维链总结</span></button>
      </header>
      <section class="image-viewer-stage">
        <img id="imageViewerImage" alt="流程总结可视化图片" />
      </section>
      <div id="imageViewerPath" class="image-viewer-path"></div>
    </section>

    <form id="sendForm" class="composer">
      <div class="composer-shell">
        <textarea id="messageInput" rows="1" placeholder="向任务编排器发送消息"></textarea>
        <button id="interruptBtn" type="button" class="composer-stop-btn" title="暂停回答" hidden><span data-icon="Square"></span></button>
        <button id="sendBtn" type="submit" class="send-round" title="发送" disabled><span data-icon="ArrowUp"></span></button>
      </div>
    </form>
  </main>

  <aside class="right-rail">
    <button id="kgCta" class="kg-cta" type="button" data-state="idle" aria-label="打开知识图谱">
      <div class="kg-cta-icon"><span data-icon="Network"></span></div>
      <div class="kg-cta-body">
        <div class="kg-cta-eyebrow">参考知识</div>
        <div class="kg-cta-title">知识图谱</div>
        <div class="kg-cta-meta">
          <span class="kg-cta-pill" id="kgCtaPill">空闲</span>
          <span class="kg-cta-stats" id="kgCtaStats">尚未构建</span>
        </div>
      </div>
      <div class="kg-cta-arrow"><span data-icon="ChevronRight"></span></div>
    </button>
    <button id="chainCta" class="kg-cta chain-cta" type="button" data-state="idle" aria-label="打开流程总结">
      <div class="kg-cta-icon"><span data-icon="Activity"></span></div>
      <div class="kg-cta-body">
        <div class="kg-cta-eyebrow">执行轨迹</div>
        <div class="kg-cta-title">思维链总结</div>
        <div class="kg-cta-meta">
          <span class="kg-cta-pill" id="chainCtaPill">空闲</span>
          <span class="kg-cta-stats" id="chainCtaStats">尚未生成</span>
        </div>
      </div>
      <div class="kg-cta-arrow"><span data-icon="ChevronRight"></span></div>
    </button>
    <section class="panel files-panel">
      <div class="panel-heading">
        <span data-icon="FolderTree"></span>
        <span>工作区文件</span>
      </div>
      <div id="workspacePath" class="workspace-path"></div>
      <form id="uploadForm" class="upload-form">
        <button id="uploadBtn" type="button" class="upload-pick-button">
          <span class="upload-pick-icon" data-icon="Upload"></span>
          <span class="upload-pick-copy">
            <span class="upload-pick-title">上传参考文件</span>
            <span class="upload-pick-subtitle">选择一个或多个文件后自动上传</span>
          </span>
        </button>
        <input id="referenceFiles" class="sr-only-file" type="file" multiple />
      </form>
      <form id="rawZipUploadForm" class="upload-form">
        <button id="rawZipUploadBtn" type="button" class="upload-pick-button">
          <span class="upload-pick-icon" data-icon="HardDriveUpload"></span>
          <span class="upload-pick-copy">
            <span class="upload-pick-title">导入原始数据压缩包</span>
            <span class="upload-pick-subtitle">选择 .zip 后自动解压到 data/raw/</span>
          </span>
        </button>
        <input id="rawZipFile" class="sr-only-file" type="file" accept=".zip" />
      </form>
      <div id="fileTree" class="file-tree"></div>
    </section>
  </aside>

  <dialog id="detailDialog">
    <form method="dialog">
      <header>
        <h3 id="dialogTitle">详情</h3>
        <div class="dialog-actions">
          <button id="deleteReferenceBtn" value="" class="dialog-delete-btn" type="button" hidden><span data-icon="Trash2"></span><span>删除参考文献</span></button>
          <button value="close" class="icon-btn ghost" type="submit" title="关闭"><span data-icon="X"></span></button>
        </div>
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
  RotateCcw,
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
  chatTopBtn: query<HTMLButtonElement>('#chatTopBtn'),
  knowledgeGraphView: query<HTMLElement>('#knowledgeGraphView'),
  chainSummaryView: query<HTMLElement>('#chainSummaryView'),
  imageViewerView: query<HTMLElement>('#imageViewerView'),
  imageViewerTitle: query<HTMLElement>('#imageViewerTitle'),
  imageViewerImage: query<HTMLImageElement>('#imageViewerImage'),
  imageViewerPath: query<HTMLElement>('#imageViewerPath'),
  backToChainFromImageBtn: query<HTMLButtonElement>('#backToChainFromImageBtn'),
  backToChatFromChainBtn: query<HTMLButtonElement>('#backToChatFromChainBtn'),
  buildChainSummaryBtn: query<HTMLButtonElement>('#buildChainSummaryBtn'),
  chainBody: query<HTMLElement>('#chainBody'),
  chainNav: query<HTMLElement>('#chainNav'),
  chainNavToggle: query<HTMLButtonElement>('#chainNavToggle'),
  chainNavContent: query<HTMLElement>('#chainNavContent'),
  chainMainScroll: query<HTMLElement>('#chainMainScroll'),
  chainBuildStatus: query<HTMLElement>('#chainBuildStatus'),
  chainMetricChart: query<HTMLElement>('#chainMetricChart'),
  chainSummaryContent: query<HTMLElement>('#chainSummaryContent'),
  graphTitle: query('#graphTitle'),
  graphTabTrace: query<HTMLButtonElement>('#graphTabTrace'),
  graphTabGraph: query<HTMLButtonElement>('#graphTabGraph'),
  graphTracePanel: query<HTMLElement>('#graphTracePanel'),
  graphKnowledgePanel: query<HTMLElement>('#graphKnowledgePanel'),
  graphLayout: query<HTMLElement>('#graphLayout'),
  graphInfoPanel: query<HTMLElement>('#graphInfoPanel'),
  graphInfoToggle: query<HTMLButtonElement>('#graphInfoToggle'),
  graphCanvas: query('#graphCanvas'),
  graphInspector: query('#graphInspector'),
  graphBuildStatus: query('#graphBuildStatus'),
  graphLeftActions: query<HTMLElement>('#graphLeftActions'),
  graphAuthMode: query<HTMLSelectElement>('#graphAuthMode'),
  graphProtocol: query<HTMLSelectElement>('#graphProtocol'),
  graphModelInput: query<HTMLInputElement>('#graphModelInput'),
  graphApiKeyInput: query<HTMLInputElement>('#graphApiKeyInput'),
  graphBaseUrlInput: query<HTMLInputElement>('#graphBaseUrlInput'),
  graphExtractionDepthInput: query<HTMLInputElement>('#graphExtractionDepthInput'),
  saveGraphLlmBtn: query<HTMLButtonElement>('#saveGraphLlmBtn'),
  buildGraphBtn: query<HTMLButtonElement>('#buildGraphBtn'),
  rebuildGraphBtn: query<HTMLButtonElement>('#rebuildGraphBtn'),
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
  settingsBtn: query<HTMLButtonElement>('#settingsBtn'),
  settingsView: query<HTMLElement>('#settingsView'),
  settingsContent: query<HTMLElement>('#settingsContent'),
  settingsDoneBtn: query<HTMLButtonElement>('#settingsDoneBtn'),
  resetChatBtn: query<HTMLButtonElement>('#resetChatBtn'),
  clearAllLogsBtn: query<HTMLButtonElement>('#clearAllLogsBtn'),
  dialog: query<HTMLDialogElement>('#detailDialog'),
  dialogTitle: query('#dialogTitle'),
  dialogBody: query('#dialogBody'),
  deleteReferenceBtn: query<HTMLButtonElement>('#deleteReferenceBtn'),
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
els.chatStream.addEventListener('scroll', updateChatTopButton);
els.chatTopBtn.addEventListener('click', () => {
  els.chatStream.scrollTo({ top: 0, behavior: 'smooth' });
});
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
els.rebuildGraphBtn.addEventListener('click', async () => {
  await postJson('/api/knowledge-graph/build', { trigger: 'rebuild' });
});
els.continueGraphBtn.addEventListener('click', async () => {
  await postJson('/api/knowledge-graph/continue', {});
});
els.pauseGraphBtn.addEventListener('click', async () => {
  await postJson('/api/knowledge-graph/pause', { reason: '用户从知识图谱页面暂停。' });
});
els.saveGraphLlmBtn.addEventListener('click', async () => {
  await saveKnowledgeGraphLlmConfig();
});
els.graphTabTrace.addEventListener('click', () => {
  state.knowledgeGraphTab = 'trace';
  renderKnowledgeGraphTabState();
});
els.graphTabGraph.addEventListener('click', () => {
  state.knowledgeGraphTab = 'graph';
  renderKnowledgeGraphTabState();
});
els.graphInfoToggle.addEventListener('click', () => {
  state.graphInfoCollapsed = !state.graphInfoCollapsed;
  renderGraphInfoState();
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
els.chainNavToggle.addEventListener('click', () => {
  state.chainNavCollapsed = !state.chainNavCollapsed;
  renderChainNavState();
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
  if (!confirm('这将重置整个工作区，删除参考资料、知识图谱、日志、运行产物、报告和临时工具。设置中的 API 密钥、接口地址、模型与 k 会保留。是否继续？')) return;
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
els.deleteReferenceBtn.addEventListener('click', async () => {
  const path = els.deleteReferenceBtn.dataset.path || '';
  if (!path) return;
  if (!confirm(`确定删除这篇参考文献吗？\n\n${path}`)) return;
  const typed = prompt('二次确认：请输入 DELETE 删除该参考文献。');
  if (typed !== 'DELETE') return;
  els.deleteReferenceBtn.disabled = true;
  try {
    const result = await deleteJson<JsonMap>('/api/references', { path });
    applyBootstrapSnapshot(result.bootstrap);
    els.dialog.close();
  } catch (error) {
    showDetail('删除失败', { message: error instanceof Error ? error.message : String(error) });
  } finally {
    els.deleteReferenceBtn.disabled = false;
  }
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

els.uploadForm.addEventListener('submit', (event) => event.preventDefault());
els.rawZipUploadForm.addEventListener('submit', (event) => event.preventDefault());

els.uploadBtn.addEventListener('click', () => {
  if (!state.busy) els.referenceFiles.click();
});

els.rawZipUploadBtn.addEventListener('click', () => {
  if (!state.busy) els.rawZipFile.click();
});

els.referenceFiles.addEventListener('change', async () => {
  await uploadReferenceFiles();
});

els.rawZipFile.addEventListener('change', async () => {
  await uploadRawZipFile();
});

async function uploadReferenceFiles() {
  const files = [...(els.referenceFiles.files || [])];
  if (!files.length) return;
  try {
    await runAction(async () => {
      const form = new FormData();
      for (const file of files) form.append('files', file);
      await postForm('/api/references/upload', form);
    });
  } finally {
    els.referenceFiles.value = '';
  }
}

async function uploadRawZipFile() {
  const file = els.rawZipFile.files?.[0];
  if (!file) return;
  try {
    await runAction(async () => {
      const form = new FormData();
      form.append('file', file);
      const result = await postForm('/api/data/raw/upload-zip', form);
      showDetail('原始数据压缩包已上传', {
        archive: result.uploaded?.archive,
        targetDir: result.uploaded?.targetDir,
        extractedCount: result.uploaded?.extracted?.length || 0,
        extracted: result.uploaded?.extracted || [],
      });
    });
  } finally {
    els.rawZipFile.value = '';
  }
}

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
  if (eventType === 'knowledge_graph_snapshot') {
    if (payload.knowledgeGraph) state.bootstrap.knowledgeGraph = payload.knowledgeGraph;
    if (payload.knowledgeBaseSummary) state.bootstrap.knowledgeBaseSummary = payload.knowledgeBaseSummary;
    if (payload.knowledgeGraphBuild) state.bootstrap.knowledgeGraphBuild = payload.knowledgeGraphBuild;
    render();
    return;
  }
  if (eventType === 'chain_summary_parts') {
    state.bootstrap.chainSummaryParts = payload.chainSummaryParts || [];
    render();
    return;
  }
  if (eventType === 'reference_feature_parts') {
    state.bootstrap.referenceFeatureParts = payload.referenceFeatureParts || [];
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
    syncRuntimeBusy(state.bootstrap);
    state.pendingParts = reconcilePendingParts(state.bootstrap);
    render();
    resolveRealtimeWaiters(state.bootstrap);
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
  syncRuntimeBusy(data);
  state.pendingParts = reconcilePendingParts(data);
  state.loadingMessage = state.busy
    ? state.loadingMessage || loadingPart('后端运行中，正在实时接收最新消息')
    : null;
  render();
  resolveRealtimeWaiters(data);
}

function syncRuntimeBusy(data: Bootstrap | null) {
  if (data && isPipelineComplete(data)) {
    data.runtime = { ...(data.runtime || {}), running: false, pipelineComplete: true };
  }
  state.busy = isBackendRunning(data);
  if (!state.busy) {
    state.loadingMessage = null;
  }
}

function isBackendRunning(data: Bootstrap | null): boolean {
  if (!data) return false;
  return Boolean(data.runtime?.running) && !isPipelineComplete(data);
}

function isPipelineComplete(data: Bootstrap | null): boolean {
  const ws = data?.state || {};
  const completedNodes = Array.isArray(ws.completedNodes) ? ws.completedNodes : [];
  return Boolean(data?.runtime?.pipelineComplete)
    || (completedNodes.includes('final-summary') && !ws.activeNode && !ws.activeNodeSessionId);
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
  setHtmlIfChanged(els.statusText, statusPill(activeNode ? `执行中：${nodeDisplayName(activeNode)}` : '就绪', activeNode ? 'active' : 'ready'));
  els.modeText.textContent = data.dryRun ? `${modeLabel(ws.controlMode || ws.mode)} / 试运行` : modeLabel(ws.controlMode || ws.mode || '-');
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
  renderKnowledgeGraphTabState();
  renderChainSummary(data);
  renderImageViewer();
  renderStable('settings', [state.view, data.llmConfig, data.knowledgeGraphLlmConfig, data.runtimeSettings], () => renderSettings(data));
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
    { value: 'all', label: '全部记录' },
    { value: 'main', label: '仅主会话' },
    ...(nodes || []).slice().reverse().map((node) => ({
      value: `node:${node.id}`,
      label: `${nodeDisplayName(node.nodeType)} · ${statusLabel(node.status)} · ${formatTime(node.startedAt)}`,
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
  document.querySelector<HTMLElement>('.toolbar')?.classList.toggle('compact', !enabled);
}

function renderNodes(specs: JsonMap[], ws: JsonMap, sessions: JsonMap[]) {
  const latestByType = new Map<string, JsonMap>();
  for (const session of sessions) latestByType.set(session.nodeType, session);
  const completedNodes = ws.completedNodes || [];

  els.nodeList.innerHTML = specs.map((spec, index) => {
    const session = latestByType.get(spec.type);
    const active = ws.activeNode === spec.type;
    const done = completedNodes.includes(spec.type);
    const failed = session?.status === 'failed';
    const status = active ? 'active' : failed ? 'failed' : done ? 'done' : 'pending';
    const isOpen = state.selectedNodeType === spec.type;
    return `
      <details class="node-item" data-node="${escapeHtml(spec.type)}" ${isOpen ? 'open' : ''}>
        <summary class="node-header">
          <span class="node-index">${index + 1}</span>
          <span class="node-name">${escapeHtml(nodeDisplayName(spec.type))}</span>
          <span class="badge ${status}">${statusIcon(status)}${statusLabel(status)}</span>
          <span class="node-chevron" data-icon="ChevronRight"></span>
        </summary>
        <div class="node-body">
          <div class="node-purpose">${escapeHtml(nodePhaseLabel(spec.phase))} · ${escapeHtml(nodePurposeText(spec))}</div>
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
    <div class="node-detail-title">${escapeHtml(nodeDisplayName(spec.type))}</div>
    <div class="meta">${escapeHtml(nodePurposeText(spec))}</div>
    <div class="detail-section-title">产物</div>
    ${produced.length ? `<div class="artifact-list">${produced.map((path) => `
      <button class="artifact-item" data-path="${escapeHtml(path)}"><span data-icon="File"></span><span>${escapeHtml(path)}</span></button>
    `).join('')}</div>` : emptyState('暂无节点产物。', 'File')}
    <div class="detail-section-title">执行记录</div>
    ${sessions.length ? `<div class="session-list">${sessions.map((node) => `
      <button class="session-item" data-session="${escapeHtml(node.id)}">
        <span class="session-title">${escapeHtml(statusLabel(node.status))} · ${formatTime(node.startedAt)}</span>
        <span class="meta">${escapeHtml(node.summary || node.rationale || '')}</span>
      </button>
    `).join('')}</div>` : emptyState('暂无 node session。', 'Activity')}
  `;

  for (const item of els.nodeDetail.querySelectorAll<HTMLElement>('.session-item')) {
    item.addEventListener('click', async () => {
      const log = await fetchJson(`/api/nodes/${item.dataset.session}/log`);
      showDetail(`节点日志 ${item.dataset.session}`, log);
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
          <h3>可以开始时间序列任务</h3>
          <p>发送任务后，任务编排器会读取工作区、规划节点，并把执行过程同步到这里。</p>
        </div>
      `;
      hydrateIcons(els.chatStream);
    }
    updateChatTopButton();
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
  updateChatTopButton();
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
  let label = '空闲';
  if (build.status === 'failed') {
    state = 'failed';
    label = '失败';
  } else if (running) {
    state = 'building';
    label = '构建中';
  } else if (build.status === 'completed' && classes > 0) {
    state = 'built';
    label = '已构建';
  }
  els.kgCta.dataset.state = state;
  els.kgCtaPill.textContent = label;
  els.kgCtaPill.className = `kg-cta-pill ${state}`;
  els.kgCtaStats.textContent = classes > 0 || relations > 0
    ? `${classes} 个概念 · ${relations} 条关系`
    : '尚未构建';
}

function renderChainCta(data: Bootstrap) {
  if (!data) return;
  const build = data.chainSummaryBuild || {};
  const summary = data.chainSummary || {};
  const running = Boolean(data.runtime?.chainSummaryRunning || build.running);
  const iterations = Array.isArray(summary.iterations) ? summary.iterations.length : 0;
  const metrics = Array.isArray(summary.metricSeries) ? summary.metricSeries.length : 0;
  let ctaState: 'idle' | 'building' | 'built' | 'failed' = 'idle';
  let label = '空闲';
  if (build.status === 'failed') {
    ctaState = 'failed';
    label = '失败';
  } else if (running) {
    ctaState = 'building';
    label = '生成中';
  } else if (build.status === 'completed' || iterations > 0 || metrics > 0) {
    ctaState = 'built';
    label = '可查看';
  }
  els.chainCta.dataset.state = ctaState;
  els.chainCtaPill.textContent = label;
  els.chainCtaPill.className = `kg-cta-pill ${ctaState}`;
  const featureBuild = data.referenceFeatureBuild || {};
  const featureCount = Number(featureBuild.featureCount || data.referenceFeatureTool?.featureCount || 0);
  let featureLabel: string | null = null;
  if (featureBuild.status === 'completed' && featureBuild.ready !== false) {
    featureLabel = `特征：${featureCount}`;
  } else if (featureBuild.status === 'failed') {
    featureLabel = '特征：失败';
  } else if (data.variant?.capabilities?.referenceFeatureExtractor === false) {
    featureLabel = `特征：已禁用 · ${data.variant?.id || 'variant'}`;
  }
  const base = iterations || metrics ? `${iterations} 轮迭代 · ${metrics} 个指标` : '尚未生成';
  els.chainCtaStats.textContent = featureLabel ? `${base} · ${featureLabel}` : base;
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

  // The reference feature extractor is built by the main session; no
  // independent LLM config is needed. The validated tool status is
  // surfaced through the node detail panel and the chain CTA.
}

function renderSettings(data: Bootstrap) {
  if (state.view !== 'settings') return;
  if (!data) return;
  syncSettingsFromBootstrap(data);
  const ws = data.state || {};

  const workspaceRows = [
    { label: '流程版本', value: variantPill(data.variant) },
    { label: '当前节点', value: ws.activeNode
      ? `<span class="settings-readout-pill active">${escapeHtml(nodeDisplayName(ws.activeNode))}</span>`
      : `<span class="settings-readout-pill">—</span>` },
    { label: '控制模式', value: `<span class="settings-readout-pill ${ws.controlMode === 'auto' ? 'active' : ''}">${escapeHtml(modeLabel(ws.controlMode || ws.mode || 'manual'))}</span>` },
    { label: '试运行', value: data.dryRun
      ? `<span class="settings-readout-pill active">开启</span>`
      : `<span class="settings-readout-pill">关闭</span>` },
    { label: '调试操作', value: data.debugEnabled
      ? `<span class="settings-readout-pill active">已启用</span>`
      : `<span class="settings-readout-pill">未启用</span>` },
    { label: '运行环境', value: runtimePill(data.runtime?.workspaceUv) },
    { label: '工作区路径', value: `<span class="settings-readout-mono">${escapeHtml(data.runtime?.workspaceUv?.workspace || '')}</span>`, copyable: data.runtime?.workspaceUv?.workspace || '' },
  ];

  const kOptions = [1, 2, 3, 4, 5, 6, 7, 8];
  const depthOptions = [1, 2, 3, 4];

  els.settingsContent.innerHTML = `
    <div class="settings-section">
      <div class="settings-section-header">工作区</div>
      <div class="settings-card">
        ${workspaceRows.map((row) => `
          <div class="settings-row">
            <div class="settings-row-label">${escapeHtml(row.label)}</div>
            <div class="settings-row-control">${row.value}${row.copyable ? `<button class="settings-icon-btn" type="button" data-copy="${escapeHtml(row.copyable)}" title="复制"><span data-icon="Archive"></span></button>` : ''}</div>
          </div>
        `).join('')}
        <div class="settings-row">
          <div class="settings-row-label">详细信息</div>
          <div class="settings-row-control settings-inline-actions">
            <button class="settings-secondary-btn" type="button" data-settings-detail="state"><span data-icon="Archive"></span><span>查看状态文件</span></button>
            <button class="settings-secondary-btn" type="button" data-settings-detail="llm"><span data-icon="Settings2"></span><span>查看模型配置</span></button>
          </div>
        </div>
      </div>
      <p class="settings-section-foot">这些项目由服务启动参数决定，例如 <code>TS_HARNESS_VARIANT</code>、<code>TS_HARNESS_CONTROL_MODE</code>、<code>TS_HARNESS_DRY_RUN</code> 和 <code>TS_HARNESS_DEBUG</code>。如需修改，请重启服务。</p>
    </div>

    <div class="settings-section">
      <div class="settings-section-header">运行参数</div>
      <div class="settings-card">
        <div class="settings-row">
          <div class="settings-row-label">
            <div>每轮候选方案数（k）</div>
            <div class="settings-row-help">迭代求解节点每一轮会并行提出多少个方法候选。</div>
          </div>
          <div class="settings-row-control">
            ${segmentedHtml('iterativeK', kOptions.map(String), String(state.settings.iterativeK), (v) => v)}
          </div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">
            <div>知识图谱抽取深度</div>
            <div class="settings-row-help">参考知识构建器从每个来源向外追踪的层数。</div>
          </div>
          <div class="settings-row-control">
            ${segmentedHtml('graphDepth', depthOptions.map(String), String(state.settings.graphDepth), (v) => v)}
          </div>
        </div>
      </div>
    </div>

    ${renderLlmSection('graph', '知识图谱构建模型', '供参考知识图谱构建器使用。留空时继承主模型配置。')}
    ${renderLlmSection('main', '主模型', '供编排器和所有节点智能体使用。保存到 <code>&lt;workspace&gt;/config.llm.json</code>，通常在下一条消息后生效。', true)}
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
    { value: 'manual', label: '手动配置' },
    { value: 'sdk-default', label: 'SDK 默认' },
  ];
  const protocolOptions = [
    { value: '', label: '自动' },
    { value: 'anthropic', label: 'anthropic' },
    { value: 'openai-compat', label: 'openai-compat' },
  ];
  const contextOptions = [
    { value: '', label: '默认' },
    { value: '200k', label: '200k' },
    { value: '1m', label: '1m' },
  ];
  const modelPlaceholder = isMain ? '例如 deepseek-v4-pro' : '默认继承主模型';
  const baseUrlPlaceholder = isMain ? 'https://api.example.com/anthropic' : '默认继承主接口地址';
  const apiKeyPlaceholder = '留空表示保持当前密钥';
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
          <div class="settings-row-label">认证方式</div>
          <div class="settings-row-control">${segmentedHtml(`${prefix}AuthMode`, authOptions.map((o) => o.value), authValue, (v) => v, authOptions.map((o) => o.label))}</div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">接口协议</div>
          <div class="settings-row-control">${segmentedHtml(`${prefix}Protocol`, protocolOptions.map((o) => o.value), protocolValue, (v) => v, protocolOptions.map((o) => o.label))}</div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">上下文窗口</div>
          <div class="settings-row-control">${segmentedHtml(`${prefix}Context`, contextOptions.map((o) => o.value), contextValue, (v) => v, contextOptions.map((o) => o.label))}</div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">模型</div>
          <div class="settings-row-control"><input class="settings-input" type="text" id="${modelId}" value="${escapeHtml(modelValue)}" placeholder="${escapeHtml(modelPlaceholder)}" /></div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">接口地址</div>
          <div class="settings-row-control"><input class="settings-input" type="text" id="${baseUrlId}" value="${escapeHtml(baseUrlValue)}" placeholder="${escapeHtml(baseUrlPlaceholder)}" /></div>
        </div>
        <div class="settings-row">
          <div class="settings-row-label">API 密钥</div>
          <div class="settings-row-control"><input class="settings-input" type="password" id="${apiKeyId}" value="" placeholder="${escapeHtml(apiKeyPlaceholder)}" autocomplete="off" /></div>
        </div>
        <div class="settings-card-footer">
          <button id="${saveBtnId}" type="button" class="settings-primary-btn"><span data-icon="Check"></span><span>${escapeHtml(isMain ? '保存主模型' : '保存构建模型')}</span></button>
          ${isMain ? `<button id="${resetBtnId}" type="button" class="settings-secondary-btn"><span data-icon="RefreshCw"></span><span>恢复文件默认值</span></button>` : ''}
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
  for (const detailBtn of els.settingsContent.querySelectorAll<HTMLButtonElement>('[data-settings-detail]')) {
    detailBtn.addEventListener('click', () => {
      if (detailBtn.dataset.settingsDetail === 'state') {
        showDetail('工作区状态文件', state.bootstrap?.state);
      } else {
        showDetail('模型配置', state.bootstrap?.llmConfig);
      }
    });
  }
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
        showDetail('复制失败', { message: error instanceof Error ? error.message : String(error) });
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
      status.textContent = '已保存';
      status.classList.add('saved');
      window.setTimeout(() => {
        status.textContent = '';
        status.classList.remove('saved');
      }, 1800);
    }
  } catch (error) {
    showDetail(isMain ? '保存主模型失败' : '保存构建模型失败', { message: error instanceof Error ? error.message : String(error) });
  }
}

async function resetMainLlmConfig() {
  if (!confirm('是否将主模型恢复为文件默认值？这会清空保存在 <workspace>/config.llm.json 中的模型、接口地址、协议和上下文窗口设置；API 密钥会保留。')) return;
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
    showDetail('恢复主模型失败', { message: error instanceof Error ? error.message : String(error) });
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
  query('#mainTitle').textContent = graphMode ? '知识图谱' : chainMode ? '思维链总结' : imageMode ? '图片查看' : settingsMode ? '设置' : '任务编排';
  document.body.classList.toggle('knowledge-page', graphMode);
  document.body.classList.toggle('chain-page', chainMode);
  document.body.classList.toggle('image-page', imageMode);
  document.body.classList.toggle('settings-page', settingsMode);
  updateChatTopButton();
}

function updateChatTopButton() {
  const visible = state.view === 'chat' && !els.chatStream.hidden && els.chatStream.scrollTop > 220;
  els.chatTopBtn.classList.toggle('visible', visible);
}

function renderKnowledgeGraphTabState() {
  const graphActive = state.knowledgeGraphTab === 'graph';
  els.graphTabGraph.classList.toggle('active', graphActive);
  els.graphTabTrace.classList.toggle('active', !graphActive);
  els.graphKnowledgePanel.hidden = !graphActive;
  els.graphTracePanel.hidden = graphActive;
  if (els.graphLayout.classList.contains('graph-empty')) {
    els.graphLayout.classList.remove('info-collapsed');
    els.graphInfoPanel.hidden = true;
    els.graphInfoToggle.hidden = true;
    return;
  }
  renderGraphInfoState();
}

function renderGraphInfoState() {
  els.graphLayout.classList.toggle('info-collapsed', state.graphInfoCollapsed);
  els.graphInfoPanel.hidden = state.graphInfoCollapsed;
  els.graphInfoToggle.hidden = false;
  els.graphInfoToggle.title = state.graphInfoCollapsed ? '展开图谱信息' : '折叠图谱信息';
  els.graphInfoToggle.setAttribute('aria-label', els.graphInfoToggle.title);
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
        ${escapeHtml(running ? '运行中' : statusLabel(build.status || 'idle'))}
      </span>
      <span class="meta">${escapeHtml(chainSummaryBuildMessage(build.message || '') || '流程总结会读取当前工作区的日志和产物。')}</span>
    </div>
    <div class="chain-status-stats">
      <span><strong>${escapeHtml(iterations)}</strong><small>迭代</small></span>
      <span><strong>${escapeHtml(metrics)}</strong><small>指标</small></span>
      <span><strong>${escapeHtml(samples)}</strong><small>样本</small></span>
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
  renderChainNav(summary, build);
  renderChainNavState();
}

function renderChainNav(summary: JsonMap, build: JsonMap = {}) {
  const iterations: JsonMap[] = Array.isArray(summary.iterations) ? summary.iterations : [];
  const generated = build.status === 'completed' || Boolean(summary.overview) || iterations.length > 0;
  const links = [
    { target: 'chainBuildStatus', label: '状态概览', icon: 'Activity' },
    { target: 'chain-metrics-section', label: '指标变化', icon: 'Gauge' },
    ...(generated ? [{ target: 'chain-overview-section', label: '总结摘要', icon: 'Sparkles' }] : []),
    ...iterations.map((iteration, index) => ({
      target: `chain-iteration-${index + 1}`,
      label: `第 ${iterationAxisLabel(iteration.iterationId || index + 1, index)} 轮`,
      icon: 'GitBranch',
    })),
  ];
  els.chainNavContent.innerHTML = links.map((link) => `
    <button type="button" class="chain-nav-link" data-chain-target="${escapeHtml(link.target)}">
      <span data-icon="${link.icon}"></span>
      <span>${escapeHtml(link.label)}</span>
    </button>
  `).join('');
  for (const item of els.chainNavContent.querySelectorAll<HTMLButtonElement>('[data-chain-target]')) {
    item.addEventListener('click', () => {
      const target = document.getElementById(item.dataset.chainTarget || '');
      if (!target) return;
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
  hydrateIcons(els.chainNavContent);
}

function renderChainNavState() {
  els.chainBody.classList.toggle('nav-collapsed', state.chainNavCollapsed);
  els.chainNav.hidden = state.chainNavCollapsed;
  els.chainNavToggle.title = state.chainNavCollapsed ? '展开目录' : '折叠目录';
  els.chainNavToggle.setAttribute('aria-label', els.chainNavToggle.title);
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
    <div id="chain-metrics-section" class="panel-heading chain-anchor"><span data-icon="Activity"></span><span>指标随迭代变化</span></div>
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
  const width = Math.max(640, (values.length - 1) * 118 + 132);
  const height = 240;
  const padLeft = 58;
  const padRight = 38;
  const padTop = 48;
  const axisY = height - 52;
  const plotHeight = axisY - padTop - 22;
  const gridTicks = [0, 0.5, 1];
  const points = values.map((item, index) => {
    const value = Number(item.value);
    const x = values.length === 1 ? width / 2 : padLeft + (index * (width - padLeft - padRight)) / (values.length - 1);
    const rawY = axisY - 22 - ((value - min) / spread) * plotHeight;
    const y = Math.max(padTop, Math.min(axisY - 22, rawY));
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
            ${gridTicks.map((tick) => {
              const y = padTop + (1 - tick) * plotHeight;
              return `<line class="metric-grid-line" x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}"></line>`;
            }).join('')}
            <line class="metric-axis" x1="${padLeft}" y1="${axisY}" x2="${width - padRight}" y2="${axisY}"></line>
            ${points.map((point) => `
              <line class="metric-tick" x1="${point.x}" y1="${axisY}" x2="${point.x}" y2="${axisY + 7}"></line>
              <text class="metric-x-label" x="${point.x}" y="${axisY + 30}">${escapeHtml(point.label)}</text>
            `).join('')}
            <polyline class="metric-line" points="${polyline}"></polyline>
            ${points.map((point) => `
              <g class="metric-point" transform="translate(${point.x} ${point.y})">
                <circle r="5"></circle>
                <text y="-11">${escapeHtml(formatMetricValue(point.value))}</text>
              </g>
            `).join('')}
          </svg>
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
        <p>${escapeHtml(build.status === 'failed' ? chainSummaryBuildMessage(build.message || '') || '生成失败，请检查流程总结构建日志。' : '点击上方按钮后，流程总结构建器会读取当前工作区的日志、报告、运行记录和样本可视化，生成完整决策链。')}</p>
      </div>
    `;
    return;
  }
  if (!iterations.length && !summary.overview) {
    els.chainSummaryContent.innerHTML = emptyState('流程总结构建器已完成，但没有可展示的总结内容。', 'Info');
    return;
  }
  els.chainSummaryContent.innerHTML = `
    <article id="chain-overview-section" class="chain-overview chain-anchor">
      <header class="chain-overview-head">
        <div class="panel-heading"><span data-icon="Sparkles"></span><span>${escapeHtml(summary.title || '思维链总结')}</span></div>
        ${summary.generatedAt ? `<div class="meta">生成时间 ${escapeHtml(formatTime(summary.generatedAt))}</div>` : ''}
      </header>
      <div class="markdown-body chain-overview-body">${renderMarkdown(summary.overview || '')}</div>
      ${Array.isArray(summary.uncertainty) && summary.uncertainty.length ? `
        <details class="chain-uncertainty">
          <summary><span data-icon="AlertTriangle"></span><span>风险与信息缺口</span><span class="chain-warning-count">${summary.uncertainty.length}</span></summary>
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
    <article id="chain-iteration-${index + 1}" class="chain-iteration-card chain-anchor">
      <header class="chain-iteration-head">
        <div class="chain-iteration-id"><span>迭代</span>${escapeHtml(iteration.iterationId || 'iteration')}</div>
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
      <div class="chain-sample-media">${image || `<div class="sample-image-placeholder"><span data-icon="File"></span></div>`}</div>
      <div class="chain-sample-body">
        <div class="chain-sample-title">${escapeHtml(sample.sampleId || 'sample')}</div>
        ${path ? `<button type="button" class="artifact-item" ${previewable ? `data-chain-image="${escapeHtml(path)}"` : `data-chain-path="${escapeHtml(path)}"`}><span data-icon="File"></span><span>${escapeHtml(path)}</span></button>` : ''}
        <section class="chain-sample-note">
          <span>描述</span>
          <p>${escapeHtml(sample.interpretation || '没有记录样本描述。')}</p>
        </section>
        <section class="chain-sample-note impact">
          <span>启发</span>
          <p>${escapeHtml(sample.nextIterationImpact || '没有记录对下一轮的启发。')}</p>
        </section>
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
  const hasGraph = hasKnowledgeGraph(data.knowledgeGraph);
  els.graphBuildStatus.innerHTML = `
    <span class="mini-pill ${build.status === 'failed' ? 'failed' : running ? 'active' : build.status === 'completed' ? 'ready' : 'pending'}">
      ${running ? '<span data-icon="Loader2"></span>' : ''}
      ${escapeHtml(!knowledgeEnabled ? `已禁用 · ${data.variant?.id || 'variant'}` : running ? '运行中' : statusLabel(build.status || 'idle'))}
    </span>
    <span class="meta">${escapeHtml(graphBuildMessage(build.message || ''))}</span>
  `;
  if (els.graphAuthMode.value !== (config.authMode || 'manual')) els.graphAuthMode.value = config.authMode || 'manual';
  if (els.graphProtocol.value !== (config.protocol || '')) els.graphProtocol.value = config.protocol || '';
  if (els.graphModelInput.value !== (config.model || '')) els.graphModelInput.value = config.model || '';
  if (els.graphBaseUrlInput.value !== (config.baseUrl || '')) els.graphBaseUrlInput.value = config.baseUrl || '';
  els.buildGraphBtn.querySelector('span:last-child')!.textContent = hasGraph ? '更新' : '构建';
  els.graphLeftActions.classList.toggle('has-graph', hasGraph);
  els.buildGraphBtn.disabled = running || !knowledgeEnabled;
  els.rebuildGraphBtn.hidden = !hasGraph;
  els.rebuildGraphBtn.disabled = running || !knowledgeEnabled;
  els.continueGraphBtn.disabled = !canContinue || !knowledgeEnabled;
  els.pauseGraphBtn.disabled = !running || !knowledgeEnabled;
  els.graphExtractionDepthInput.disabled = running || !knowledgeEnabled;
  els.saveGraphLlmBtn.disabled = !knowledgeEnabled;
}

function hasKnowledgeGraph(graph: JsonMap | null | undefined) {
  if (!graph) return false;
  const nodes = Array.isArray(graph.nodes) ? graph.nodes.length : 0;
  const edges = Array.isArray(graph.edges) ? graph.edges.length : 0;
  return nodes > 0 || edges > 0;
}

function renderKnowledgeWorkbench(data: Bootstrap) {
  const summary = data.knowledgeBaseSummary || data.knowledgeGraph?.summary || {};
  els.knowledgeSummary.innerHTML = `
    <div class="knowledge-depth">深度 ${escapeHtml(summary.extractionDepth ?? data.runtimeSettings?.knowledgeGraphExtractionDepth ?? 2)}</div>
    ${knowledgeStatHtml('knowledge', summary.knowledgeCount ?? 0, '知识')}
    ${knowledgeStatHtml('evidence', summary.evidenceCount ?? 0, '证据')}
    ${knowledgeStatHtml('classes', summary.classCount ?? 0, '概念')}
    ${knowledgeStatHtml('relations', summary.relationCount ?? 0, '关系')}
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
        <button class="icon-btn ghost" type="button" data-kb-close title="关闭"><span data-icon="X"></span></button>
      </div>
      ${emptyState('正在加载卡片...', 'Loader2')}
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
        <div class="meta">已显示 ${escapeHtml(cards.length)} 条${payload.count ? ` · 共 ${escapeHtml(payload.count)} 条` : ''}</div>
      </div>
      <button class="icon-btn ghost" type="button" data-kb-close title="关闭"><span data-icon="X"></span></button>
    </div>
    ${payload.error ? `<div class="empty"><span data-icon="AlertTriangle"></span><span>${escapeHtml(payload.error)}</span></div>` : ''}
    ${cards.length ? `<div class="kb-cards">${cards.map(knowledgeBaseCardHtml).join('')}</div>` : emptyState('暂无卡片。', 'Info')}
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
        <span>${escapeHtml(card.title || card.id || '卡片')}</span>
        <span class="meta">${escapeHtml(card.id || '')}</span>
      </div>
      ${card.subtitle ? `<div class="meta">${escapeHtml(card.subtitle)}</div>` : ''}
      ${card.body ? `<p>${escapeHtml(card.body)}</p>` : ''}
      ${metaItems.length ? `<div class="graph-mini-list">${metaItems.map(([key, value]) => `<span>${escapeHtml(key)}: ${escapeHtml(Array.isArray(value) ? value.join(', ') : value)}</span>`).join('')}</div>` : ''}
    </article>
  `;
}

function renderBuilderTrace(parts: JsonMap[], target: HTMLElement = els.builderTrace) {
  const wasNearBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 120;
  const savedScroll = target.scrollTop;
  const visible = normalizeChatParts((parts || []).map((part) => ({ ...part, sourceLabel: 'builder' }))).slice(-80);
  if (!visible.length) {
    target.innerHTML = emptyState('暂无构建记录。点击“构建”开始。', 'TerminalSquare');
    return;
  }
  target.innerHTML = visible.map((part) => messageHtml(part)).join('');
  bindToolCards(target);
  if (wasNearBottom) {
    target.scrollTop = target.scrollHeight;
  } else if (savedScroll < target.scrollHeight) {
    target.scrollTop = Math.min(savedScroll, target.scrollHeight - target.clientHeight);
  }
}

function renderKnowledgeGraph(graph: JsonMap | null | undefined) {
  const nodes: JsonMap[] = graph?.nodes || [];
  const edges: JsonMap[] = graph?.edges || [];
  els.graphTitle.textContent = graphTitleLabel(graph);
  if (!nodes.length) {
    els.graphLayout.classList.add('graph-empty');
    els.graphInfoPanel.hidden = true;
    els.graphInfoToggle.hidden = true;
    els.graphCanvas.innerHTML = graphEmptyStateHtml(graph);
    els.graphInspector.innerHTML = '';
    return;
  }
  els.graphLayout.classList.remove('graph-empty');
  renderGraphInfoState();

  const selected = nodes.find((node) => node.id === state.selectedGraphNodeId) || nodes[0];
  state.selectedGraphNodeId = selected?.id || null;
  const layout = graphNetworkLayout(nodes, edges, String(selected?.id || ''));
  const { width, height, positions, degrees, labelIds } = layout;

  els.graphCanvas.innerHTML = `
    <svg class="graph-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Knowledge graph">
      <g class="graph-edges">
        ${edges.map((edge) => {
          const source = positions.get(String(edge.source));
          const target = positions.get(String(edge.target));
          if (!source || !target) return '';
          return `<line x1="${source.x.toFixed(1)}" y1="${source.y.toFixed(1)}" x2="${target.x.toFixed(1)}" y2="${target.y.toFixed(1)}" />`;
        }).join('')}
      </g>
      <g class="graph-nodes">
        ${nodes.map((node) => {
          const position = positions.get(String(node.id));
          if (!position) return '';
          const selectedClass = node.id === state.selectedGraphNodeId ? ' selected' : '';
          const degree = degrees.get(String(node.id)) || 0;
          const radius = graphNodeRadius(degree, node.id === state.selectedGraphNodeId);
          const showLabel = labelIds.has(String(node.id));
          const label = shortGraphLabel(node.label || node.id, showLabel ? 22 : 14);
          return `
            <g class="graph-node${selectedClass}${showLabel ? ' labeled' : ''}" data-node-id="${escapeHtml(node.id)}" transform="translate(${position.x.toFixed(1)} ${position.y.toFixed(1)})">
              <title>${escapeHtml(node.label || node.id)}</title>
              <circle r="${radius.toFixed(1)}"></circle>
              ${showLabel ? `<text y="${(radius + 15).toFixed(1)}">${escapeHtml(label)}</text>` : ''}
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

function graphTitleLabel(graph: JsonMap | null | undefined) {
  const raw = String(graph?.taskGoal || '').trim();
  if (!raw) return '参考知识';
  if (raw === 'Knowledge Base') return '参考知识库';
  if (raw === 'Time-Series Domain Knowledge') return '时间序列领域知识';
  if (raw === 'Domain Brief: Time-Series Domain Knowledge') return '时间序列领域知识';
  if (/^Domain Brief:/i.test(raw)) return raw.replace(/^Domain Brief:\s*/i, '').trim() || '参考知识';
  return raw;
}

function graphEmptyStateHtml(graph: JsonMap | null | undefined) {
  return `
    <div class="graph-empty-state" role="status" aria-live="polite">
      <div class="graph-empty-orbit" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
        <i></i>
      </div>
      <div class="graph-empty-copy">
        <div class="graph-empty-title">知识图谱尚未构建</div>
        <p>${escapeHtml(graphEmptyNotes(graph))}</p>
      </div>
    </div>
  `;
}

function graphEmptyNotes(graph: JsonMap | null | undefined) {
  const raw = String(graph?.notes || '').trim();
  if (!raw) return '点击左侧“构建”后，系统会从参考资料中抽取概念、证据和关系，并在这里生成可浏览的知识网络。';
  if (raw === 'CSV knowledge base: evidence, knowledge, class nodes, and relation edges.') {
    return '当前还没有可展示的概念和关系。点击左侧“构建”开始生成知识网络。';
  }
  return raw;
}

const graphNodeTypes = ['task', 'concept', 'observable', 'method', 'metric', 'risk', 'assumption', 'data_field', 'case_pattern', 'reference'];

function graphNetworkLayout(nodes: JsonMap[], edges: JsonMap[], selectedId: string) {
  const width = 1280;
  const height = 820;
  const pad = 72;
  const centerX = width / 2;
  const centerY = height / 2;
  const ids = nodes.map((node) => String(node.id));
  const degrees = new Map<string, number>(ids.map((id) => [id, 0]));
  const adjacency = new Map<string, Set<string>>(ids.map((id) => [id, new Set<string>()]));
  for (const edge of edges) {
    const source = String(edge.source || '');
    const target = String(edge.target || '');
    if (!degrees.has(source) || !degrees.has(target)) continue;
    degrees.set(source, (degrees.get(source) || 0) + 1);
    degrees.set(target, (degrees.get(target) || 0) + 1);
    adjacency.get(source)?.add(target);
    adjacency.get(target)?.add(source);
  }

  const sorted = ids.slice().sort((a, b) => (degrees.get(b) || 0) - (degrees.get(a) || 0));
  const anchor = selectedId || sorted[0] || '';
  const simNodes = nodes.map((node, index) => {
    const id = String(node.id);
    const angle = index * 2.399963229728653;
    const radius = Math.sqrt(index + 1) * 30;
    return {
      id,
      degree: degrees.get(id) || 0,
      r: graphNodeRadius(degrees.get(id) || 0, id === anchor),
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius,
    };
  });
  const simLinks = edges
    .map((edge) => ({ source: String(edge.source || ''), target: String(edge.target || '') }))
    .filter((edge) => degrees.has(edge.source) && degrees.has(edge.target));

  forceSimulation(simNodes as any)
    .force('link', forceLink(simLinks as any)
      .id((node: any) => node.id)
      .distance((link: any) => {
        const sourceDegree = degrees.get(String(link.source?.id || link.source)) || 0;
        const targetDegree = degrees.get(String(link.target?.id || link.target)) || 0;
        return Math.max(70, 145 - Math.min(60, (sourceDegree + targetDegree) * 3));
      })
      .strength(0.36))
    .force('charge', forceManyBody().strength((node: any) => -210 - Math.min(220, node.degree * 20)))
    .force('collide', forceCollide((node: any) => node.r + 28).strength(0.9).iterations(3))
    .force('center', forceCenter(centerX, centerY).strength(0.18))
    .force('x', forceX(centerX).strength((node: any) => node.id === anchor ? 0.08 : 0.025 + Math.min(0.045, node.degree * 0.004)))
    .force('y', forceY(centerY).strength((node: any) => node.id === anchor ? 0.08 : 0.025 + Math.min(0.045, node.degree * 0.004)))
    .stop()
    .tick(420);

  const xValues = simNodes.map((node: any) => Number(node.x));
  const yValues = simNodes.map((node: any) => Number(node.y));
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  const scale = Math.min(
    1,
    (width - pad * 2) / Math.max(1, maxX - minX),
    (height - pad * 2) / Math.max(1, maxY - minY),
  );
  const offsetX = centerX - ((minX + maxX) / 2) * scale;
  const offsetY = centerY - ((minY + maxY) / 2) * scale;

  const finalPositions = new Map(simNodes.map((node: any) => {
    const x = Math.max(pad, Math.min(width - pad, node.x * scale + offsetX));
    const y = Math.max(pad, Math.min(height - pad, node.y * scale + offsetY));
    return [node.id, { x, y }];
  }));
  const labelIds = graphLabelSelection(nodes, finalPositions, degrees, anchor);

  return {
    width,
    height,
    degrees,
    labelIds,
    positions: finalPositions,
  };
}

function graphNodeRadius(degree: number, selected = false) {
  return Math.min(selected ? 34 : 30, 12 + Math.sqrt(degree + 1) * 4.4);
}

function graphLabelSelection(
  nodes: JsonMap[],
  positions: Map<string, { x: number; y: number }>,
  degrees: Map<string, number>,
  selectedId: string,
) {
  const selected = new Set<string>();
  const boxes: Array<{ x1: number; y1: number; x2: number; y2: number }> = [];
  const candidates = nodes
    .map((node) => {
      const id = String(node.id);
      return { id, label: String(node.label || node.id || ''), degree: degrees.get(id) || 0 };
    })
    .filter((node) => positions.has(node.id) && (node.degree > 0 || node.id === selectedId))
    .sort((a, b) => (b.id === selectedId ? 1 : 0) - (a.id === selectedId ? 1 : 0) || b.degree - a.degree);

  for (const node of candidates) {
    const position = positions.get(node.id)!;
    const radius = graphNodeRadius(node.degree, node.id === selectedId);
    const label = shortGraphLabel(node.label, 22);
    const width = Math.min(164, Math.max(32, label.length * 7.2));
    const height = 17;
    const box = {
      x1: position.x - width / 2 - 5,
      y1: position.y + radius + 5,
      x2: position.x + width / 2 + 5,
      y2: position.y + radius + 5 + height,
    };
    const overlaps = boxes.some((other) =>
      box.x1 < other.x2 && box.x2 > other.x1 && box.y1 < other.y2 && box.y2 > other.y1
    );
    if (!overlaps || node.id === selectedId) {
      selected.add(node.id);
      boxes.push(box);
    }
  }
  return selected;
}

function graphMetadataHtml(graph: JsonMap | null | undefined, nodes: JsonMap[], edges: JsonMap[]) {
  return `
    <div class="node-detail-title">图谱信息</div>
    <dl class="kv graph-kv">
      <dt>概念</dt><dd>${nodes.length}</dd>
      <dt>关系</dt><dd>${edges.length}</dd>
      <dt>更新时间</dt><dd>${escapeHtml(graph?.updatedAt || '-')}</dd>
    </dl>
  `;
}

function graphInspectorHtml(graph: JsonMap | null | undefined, selected: JsonMap | undefined, nodes: JsonMap[], edges: JsonMap[]) {
  if (!selected) return graphMetadataHtml(graph, nodes, edges);
  const related = edges.filter((edge) => edge.source === selected.id || edge.target === selected.id);
  return `
    ${graphMetadataHtml(graph, nodes, edges)}
    <div class="detail-section-title">选中概念</div>
    <div class="graph-selected">
      <div class="node-detail-title">${escapeHtml(selected.label || selected.id)}</div>
      <div class="meta">${escapeHtml(selected.type || '概念')} · ${escapeHtml(selected.id || '')}</div>
      ${classDescriptionHtml(selected.summary || '')}
    </div>
    <div class="detail-section-title">来源知识</div>
    ${idListHtml(selected.knowledgeIds || [], '知识')}
    <div class="detail-section-title">证据</div>
    ${graphEvidenceHtml(selected.evidence || [])}
    <div class="detail-section-title">关系</div>
    ${related.length ? `<div class="graph-relations">${related.map((edge) => `
      <div class="graph-relation">
        <div class="timeline-type">${escapeHtml(edge.relation || 'related')}</div>
        <div class="meta">${escapeHtml(edge.sourceLabel || edge.source)} -> ${escapeHtml(edge.targetLabel || edge.target)}</div>
        <div>${escapeHtml(edge.summary || '')}</div>
        ${edge.knowledgeIds?.length ? idListHtml(edge.knowledgeIds, '知识') : ''}
      </div>
    `).join('')}</div>` : emptyState('暂无关联边。', 'GitBranch')}
  `;
}

function idListHtml(items: string[], label: string) {
  if (!items.length) return emptyState(`暂无相关${label}。`, 'Info');
  return `<div class="graph-mini-list">${items.map((item) => `<span>${escapeHtml(item)}</span>`).join('')}</div>`;
}

function classDescriptionHtml(summary: string) {
  if (!summary) return emptyState('暂无描述。', 'Info');
  return `
    <details class="class-description">
      <summary>描述</summary>
      <p>${escapeHtml(summary)}</p>
    </details>
  `;
}

function graphEvidenceHtml(items: JsonMap[]) {
  if (!items.length) return emptyState('暂无证据。', 'File');
  return `<div class="graph-evidence">${items.slice(0, 6).map((item) => `
    <button class="artifact-item evidence-item" type="button" data-path="${escapeHtml(item.sourcePath || '')}" data-preview-url="${escapeHtml(item.previewUrl || '')}">
      <span data-icon="File"></span>
      <span>${escapeHtml(item.sourcePath || '来源')}: ${escapeHtml(item.quote || item.summary || '')}</span>
    </button>
  `).join('')}</div>`;
}

function shortGraphLabel(value: string, maxLength = 18) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value;
}

function messageHtml(part: JsonMap) {
  const role = part.role || 'system';
  const roleClass = ['user', 'assistant', 'system', 'tool'].includes(role) ? role : 'system';
  const text = part.displayText || part.text || summarizeRaw(part.raw) || '';
  const source = part.sourceLabel ? `${sourceLabel(part.sourceLabel)} · ` : '';
  if (part.type === 'loading') {
    return `
      <article class="message assistant loading">
        <div class="message-role"><span data-icon="Loader2"></span>${escapeHtml(source)}助手 · 运行中 · ${formatTime(part.timestamp)}</div>
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
            <span class="tool-meta">${escapeHtml(source)}${escapeHtml(toolName)} · ${escapeHtml(partTypeLabel(part.type || 'tool'))} · ${formatTime(part.timestamp)}</span>
          </span>
          <span class="tool-chevron" data-icon="ChevronRight"></span>
        </button>
        <pre class="tool-detail" ${expanded ? '' : 'hidden'}>${escapeHtml(detail)}</pre>
      </article>
    `;
  }
  return `
    <article class="message ${escapeHtml(roleClass)}">
      <div class="message-role"><span data-icon="${role === 'user' ? 'Send' : role === 'assistant' ? 'Bot' : 'Info'}"></span>${escapeHtml(source)}${escapeHtml(roleLabel(role))} · ${escapeHtml(partTypeLabel(part.type || 'text'))} · ${formatTime(part.timestamp)}</div>
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
      `工具：${toolNameForPart(part)}`,
      `状态：${statusLabel(part.status || 'pending')}`,
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
  return isBackendRunning(data) ? unresolved : [];
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
      if (isReasoningOnlyPart(part)) return false;
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

function isReasoningOnlyPart(part: JsonMap): boolean {
  if (part.role !== 'assistant' || part.type !== 'text') return false;
  if (typeof part.text === 'string' && part.text.trim()) return false;
  const content = Array.isArray(part.raw?.message?.content)
    ? part.raw.message.content
    : Array.isArray(part.raw?.content)
      ? part.raw.content
      : [];
  if (!content.length) return false;
  return content.every((item: JsonMap | string) => {
    if (typeof item === 'string') return !item.trim();
    if (!item || typeof item !== 'object') return false;
    if (typeof item.text === 'string' && item.text.trim()) return false;
    if (item.type === 'tool_use' || item.type === 'tool_result' || item.name || item.input || item.tool_use_id) return false;
    return Boolean(item.thinking || item.signature || item.redacted_thinking);
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
      return result.filenames.length ? `工具结果：\n${files}${more}` : '工具结果：未找到文件';
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
    if (part.raw?.is_error) return part.raw?.result || part.text || '错误';
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
    els.fileTree.innerHTML = emptyState('暂无工作区文件。', 'FolderTree');
    return;
  }
  els.workspacePath.textContent = fileTree.root || '';
  els.fileTree.innerHTML = renderTreeNode(fileTree.tree, true);
  if (fileTree.truncated) {
    const limit = fileTree.maxChildrenPerDir
      ? `（每个目录最多 ${fileTree.maxChildrenPerDir} 项，最多 ${fileTree.maxDepth || 5} 层）`
      : '';
    els.fileTree.insertAdjacentHTML('beforeend', emptyState(`部分目录已截断显示${limit}。`, 'AlertTriangle'));
  }
  for (const item of els.fileTree.querySelectorAll<HTMLElement>('.file-node.file')) {
    item.addEventListener('click', async () => showWorkspaceFile(item.dataset.path || ''));
  }
}

function renderTreeNode(node: FileTreeNode | undefined, root = false): string {
  if (!node) return '';
  if (node.kind === 'dir') {
    const open = root || ['user', 'artifacts', 'data', 'tools', 'runs', 'reports'].includes(node.path);
    const truncation = node.truncated
      ? `<div class="file-tree-note">${escapeHtml(fileTreeTruncationText(node))}</div>`
      : '';
    return `
      <details class="file-dir" ${open ? 'open' : ''}>
        <summary><span data-icon="ChevronRight"></span><span>${escapeHtml(node.name || '工作区')}</span></summary>
        <div class="file-children">
          ${(node.children || []).map((child) => renderTreeNode(child)).join('')}
          ${truncation}
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

function fileTreeTruncationText(node: FileTreeNode) {
  if ((node.childCount || 0) > (node.maxChildren || 0)) {
    return `已显示前 ${node.maxChildren} / ${node.childCount} 项`;
  }
  return `已达到 ${node.maxDepth || 5} 层显示深度`;
}

async function showWorkspaceFile(path: string) {
  if (!path) return;
  try {
    const file = await fetchJson<JsonMap>(`/api/files/content?path=${encodeURIComponent(path)}`);
    if (file.binary) {
      showDetail(path, { message: 'Binary file preview is not supported.', size: file.size }, path);
      return;
    }
    if (file.truncated) {
      showDetail(path, { message: 'File is too large to preview.', size: file.size }, path);
      return;
    }
    showTextDetail(path, file.text || '', path);
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
    : '向任务编排器发送消息';
  els.interruptBtn.disabled = !state.busy && !activeRunning;
  els.interruptBtn.hidden = !state.busy && !activeRunning;
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
    showDetail('错误', { message: error instanceof Error ? error.message : String(error) });
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
    showDetail('错误', { message: error instanceof Error ? error.message : String(error) });
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
  const label = `${id} · ${variantNameLabel(variant)}`;
  const isDefault = id === 'NOD-KGR-KTL-CRV-SUB-ADA';
  const features = Array.isArray(variant.features) ? `功能：${variant.features.join(', ')}` : '';
  const title = [variant.description || label, features].filter(Boolean).join('\n');
  return `<span class="mini-pill variant-pill ${isDefault ? 'variant-default' : 'variant-ablation'}" title="${escapeHtml(title)}">${escapeHtml(label)}</span>`;
}

function variantNameLabel(variant: JsonMap) {
  const id = String(variant.id || '').toUpperCase();
  if (id === 'NOD-KGR-KTL-CRV-SUB-ADA') return '完整流程';
  return String(variant.name || '未命名流程');
}

function formatRuntimeUv(runtimeUv: JsonMap | null | undefined) {
  if (!runtimeUv) return '-';
  const runtimeState = runtimeUv.state || 'unknown';
  if (runtimeState === 'ready') return `就绪 · Python ${runtimeUv.pythonVersion || ''}`.trim();
  if (runtimeState === 'skipped') return '已跳过';
  if (runtimeState === 'failed') return '失败';
  return runtimeState;
}

function runtimePill(runtimeUv: JsonMap | null | undefined) {
  const text = formatRuntimeUv(runtimeUv);
  const tone = text.startsWith('就绪') ? 'ready' : text === '失败' ? 'failed' : 'pending';
  return `<span class="mini-pill ${tone}">${escapeHtml(text)}</span>`;
}

function statusPill(text: string, tone: string) {
  return `<span class="mini-pill ${tone}">${escapeHtml(text)}</span>`;
}

function statusIcon(status: string) {
  const icon = status === 'done' ? 'Check' : status === 'active' ? 'Loader2' : status === 'failed' ? 'XCircle' : 'Circle';
  return `<span data-icon="${icon}"></span>`;
}

function statusLabel(status: any) {
  const value = String(status || 'idle');
  if (value === 'done' || value === 'completed' || value === 'ready') return '已完成';
  if (value === 'active' || value === 'running' || value === 'building') return '运行中';
  if (value === 'failed') return '失败';
  if (value === 'paused') return '已暂停';
  if (value === 'waiting_approval') return '等待确认';
  if (value === 'pending') return '待执行';
  if (value === 'idle') return '空闲';
  return value;
}

function modeLabel(mode: any) {
  const value = String(mode || '-');
  if (value === 'auto') return '自动';
  if (value === 'manual') return '手动';
  return value;
}

function graphBuildMessage(message: string) {
  if (!message) return '';
  if (message === 'Knowledge graph updated.') return '知识图谱已更新。';
  return message;
}

function chainSummaryBuildMessage(message: string) {
  if (!message) return '';
  if (message === 'Chain summary updated.') return '思维链总结已更新。';
  return message;
}

function nodeDisplayName(type: any) {
  const value = String(type || '');
  if (value === 'problem-contract') return '问题定义';
  if (value === 'knowledge-to-tools') return '知识转工具';
  if (value === 'iterative-solving') return '迭代求解';
  if (value === 'final-summary') return '最终总结';
  return value;
}

function nodePurposeText(spec: JsonMap) {
  const type = String(spec?.type || '');
  if (type === 'problem-contract') return '根据用户输入和参考资料获取并处理数据，通过数据探索明确当前要解决的问题，并给出整个流程的问题契约。';
  if (type === 'knowledge-to-tools') return '在主会话中，根据问题契约、数据规范、参考资料目录以及知识图谱（若已构建），生成并校验确定性的参考特征提取器，作为后续案例复盘的数值证据来源。';
  if (type === 'iterative-solving') return '根据任务契约每轮提出多个候选方案，分别做可行性测试与案例复盘，再综合证据选择本轮执行对象或下一轮优化方向。';
  if (type === 'final-summary') return '当迭代优化结束后，总结整个优化历程、最终工具使用方案、最终结果和系统边界。';
  return String(spec?.purpose || '');
}

function nodePhaseLabel(phase: any) {
  const value = String(phase || '');
  if (value === 'setup') return '准备';
  if (value === 'solve') return '求解';
  if (value === 'iteration') return '迭代';
  if (value === 'summary') return '总结';
  return value;
}

function roleLabel(role: any) {
  const value = String(role || '');
  if (value === 'user') return '用户';
  if (value === 'assistant') return '助手';
  if (value === 'system') return '系统';
  return value;
}

function partTypeLabel(type: any) {
  const value = String(type || '');
  if (value === 'text') return '文本';
  if (value === 'tool_call') return '工具调用';
  if (value === 'tool_use') return '工具使用';
  if (value === 'tool_result') return '工具结果';
  if (value === 'tool') return '工具';
  if (value === 'loading') return '运行中';
  if (value === 'raw') return '原始事件';
  if (value === 'result') return '结果';
  return value;
}

function sourceLabel(source: any) {
  const value = String(source || '');
  if (value === 'main') return '主会话';
  if (value === 'builder') return '构建器';
  if (value === 'harness') return '系统';
  if (value.startsWith('node:')) return `节点：${nodeDisplayName(value.slice(5))}`;
  return value;
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
  els.sendBtn.hidden = !els.interruptBtn.hidden;
  const icon = state.busy ? 'Square' : activePaused ? 'Play' : 'ArrowUp';
  if (els.sendBtn.dataset.currentIcon !== icon) {
    els.sendBtn.dataset.currentIcon = icon;
    els.sendBtn.innerHTML = `<span data-icon="${icon}"></span>`;
    hydrateIcons(els.sendBtn);
  }
  els.sendBtn.title = activePaused ? '继续当前节点' : '发送';
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
      try {
        await waitForBackendIdle(5000);
      } catch {
        // The backend may need longer to let the interrupted SDK task
        // unwind. Pause has already been recorded, so do not leave a
        // permanent loading row or show this settling delay as an error.
      }
    }
    state.loadingMessage = null;
    state.pendingParts = reconcilePendingParts(state.bootstrap);
    render();
  } catch (error) {
    state.loadingMessage = null;
    render();
    showDetail('暂停失败', { message: error instanceof Error ? error.message : String(error) });
  } finally {
    els.interruptBtn.disabled = false;
    updateControls(state.bootstrap || emptyBootstrap());
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

function showDetail(title: string, value: any, path = '') {
  els.dialogTitle.textContent = title;
  els.dialogBody.textContent = JSON.stringify(value ?? null, null, 2);
  updateReferenceDeleteButton(path);
  els.dialog.showModal();
}

function showTextDetail(title: string, text: string, path = '') {
  els.dialogTitle.textContent = title;
  els.dialogBody.textContent = text;
  updateReferenceDeleteButton(path);
  els.dialog.showModal();
}

function updateReferenceDeleteButton(path: string) {
  const normalized = String(path || '').trim().replace(/^\/+/, '');
  const deletable = isReferenceFilePath(normalized);
  els.deleteReferenceBtn.hidden = !deletable;
  els.deleteReferenceBtn.dataset.path = deletable ? normalized : '';
}

function isReferenceFilePath(path: string) {
  return path.startsWith('references/') && !path.endsWith('/');
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
