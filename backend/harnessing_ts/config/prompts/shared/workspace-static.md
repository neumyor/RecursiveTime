Workspace path: {workspace_path}
Locale: {locale}
文件系统和 JSONL 日志是真相源；SDK session 是短命执行载体。
优先写入约定工件路径；不要修改 data/raw/**。
该 workspace 是独立 uv Python 项目，包含自己的 `pyproject.toml`、`uv.lock` 和 `.venv/`。
运行任何 shell/python 命令都必须在 workspace 根目录使用 `uv run`，例如 `uv run python tools/read_docx.py references/file.docx artifacts/file.txt`。
安装新的 Python 依赖必须使用 workspace 内的 uv 项目命令，例如 `uv add package-name` 或临时命令 `uv run --with package-name python script.py`；不要安装到系统 Python 或 HarnessingTS 源码项目环境。
Workspace 内置 DOCX 工具：`tools/read_docx.py`。读取 .docx 时优先使用 `uv run python tools/read_docx.py <docx> [output.txt]`，或读取系统生成的 `<docx>.txt`。
