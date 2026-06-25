export type JsonMap = Record<string, any>;

export type FileTreeNode = {
  kind: 'dir' | 'file';
  name: string;
  path: string;
  size?: number;
  truncated?: boolean;
  childCount?: number;
  maxChildren?: number;
  maxDepth?: number;
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
  fileTree: { root?: string; tree?: FileTreeNode; truncated?: boolean; entryCount?: number; maxDepth?: number; maxChildrenPerDir?: number } | null;
  llmConfig?: JsonMap;
  runtimeSettings?: JsonMap;
  knowledgeGraph?: JsonMap;
  knowledgeBaseSummary?: JsonMap;
  knowledgeGraphParts?: JsonMap[];
  chainSummary?: JsonMap;
  chainSummaryBuild?: JsonMap;
  chainSummaryParts?: JsonMap[];
  referenceFeatureBuild?: JsonMap;
  referenceFeatureTool?: JsonMap;
  referenceFeatureParts?: JsonMap[];
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
