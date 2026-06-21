export type JsonMap = Record<string, any>;

export type FileTreeNode = {
  kind: 'dir' | 'file';
  name: string;
  path: string;
  size?: number;
  children?: FileTreeNode[];
};

export type Bootstrap = {
  variant?: JsonMap;
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
  chainSummary?: JsonMap;
  chainSummaryBuild?: JsonMap;
  chainSummaryParts?: JsonMap[];
  dryRun?: boolean;
  debugEnabled?: boolean;
  runtime?: {
    running?: boolean;
    knowledgeGraphRunning?: boolean;
    chainSummaryRunning?: boolean;
    workspaceUv?: JsonMap | null;
  };
  knowledgeGraphBuild?: JsonMap;
  knowledgeGraphLlmConfig?: JsonMap;
};
