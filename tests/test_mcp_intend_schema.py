from __future__ import annotations

from harnessing_ts.mcp.server import _require_intend, _without_intend


def test_mcp_schema_requires_intend() -> None:
    schema = _require_intend({
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    })

    assert "intend" in schema["properties"]
    assert schema["required"] == ["question", "intend"]


def test_intend_is_removed_before_business_callback() -> None:
    assert _without_intend({"question": "Q", "intend": "说明调用意图"}) == {"question": "Q"}
