Workspace path: {workspace_path}
Locale: {locale}
文件系统和 JSONL 日志是真相源；SDK session 是短命执行载体。
优先写入约定工件路径。`problem-contract` node 可以在 `data/raw/**` 中创建任务所需且尚不存在的原始数据，但不得覆盖或改写已有原始文件；任何解压后的派生副本、清洗、转换和特征结果必须写入 `data/processed/**` 或约定工件路径。其他 node 将 `data/raw/**` 视为严格只读。
该 workspace 是独立 uv Python 项目，包含自己的 `pyproject.toml`、`uv.lock` 和 `.venv/`。
运行任何 shell/python 命令都必须在 workspace 根目录使用 `uv run`，例如 `uv run python tools/read_docx.py references/file.docx artifacts/file.txt`。
安装新的 Python 依赖必须使用 workspace 内的 uv 项目命令，例如 `uv add package-name` 或临时命令 `uv run --with package-name python script.py`；不要安装到系统 Python 或 HarnessingTS 源码项目环境。
Workspace 内置 DOCX 工具：`tools/read_docx.py`。读取 .docx 时优先使用 `uv run python tools/read_docx.py <docx> [output.txt]`，或读取系统生成的 `<docx>.txt`。
`knowledge_base/tables/*.csv`、`knowledge_base/indexes/**` 和 `knowledge_base/cache/**` 是 knowledge graph builder/reasoner 的内部存储。普通领域知识查询必须使用 MCP `mcp__ts_harness__query_knowledge`，不要直接读取这些内部文件；只有用户明确要求调试知识库文件、CSV schema 或图谱构建错误时才可以直接读取。
调用 `mcp__ts_harness__query_knowledge` 时默认保持精简返回；只有用户明确要求原文证据、citations 或审计 trace 时，才设置 `includeEvidence=true`。
