from __future__ import annotations

from typing import Any

from app.services.session_store import SessionStore

def _get_traced_execution():
    try:
        from app.services.observability.tracing import traced_execution
        return traced_execution
    except Exception:
        return None

def _get_trace_safe_tool_attrs():
    try:
        from app.services.observability.tracing import build_trace_safe_tool_attrs
        return build_trace_safe_tool_attrs
    except Exception:
        return None

def _get_langfuse_span_helpers():
    try:
        from app.services.observability.langfuse_client import create_langfuse_span
        return create_langfuse_span
    except Exception:
        return None

class SubAgentBase:
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}
    required_keys: list[str] = []

    def validate_args(self, args: dict[str, Any]) -> None:
        for k in self.required_keys:
            if k not in args:
                raise ValueError(f"子Agent[{self.name}]缺少必填参数: {k}")

    async def run(self, args: dict[str, Any], session: SessionStore) -> dict[str, Any]:
        raise NotImplementedError

    async def traced_tool_execute(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        session: SessionStore,
        lf_trace: Any = None,
        lf_parent_span: Any = None,
    ) -> dict[str, Any]:
        """
        执行底层工具，带 OTel + LangFuse 双埋点。
        OTel span 使用 build_trace_safe_tool_attrs：只存 args_hash，不存完整原始参数。
        """
        from app.services.tools.executor import _execute_single_tool

        traced_execution = _get_traced_execution()
        build_safe_attrs = _get_trace_safe_tool_attrs()
        create_lf_span = _get_langfuse_span_helpers()

        lf_span = None
        span_parent = lf_parent_span or lf_trace
        if span_parent and create_lf_span:
            try:
                lf_span = create_lf_span(
                    span_parent,
                    f"execute_tool:{tool_name}",
                    input_data={"args_hash": "redacted"},
                )
            except Exception:
                lf_span = None

        result: dict[str, Any] = {}
        if traced_execution:
            safe_attrs = build_safe_attrs(tool_name, tool_args) if build_safe_attrs else {
                "gen_ai.tool.name": tool_name,
                "gen_ai.tool.args_hash": "unavailable",
            }
            with traced_execution("execute_tool", {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.system.name": "desktop-agent",
                **safe_attrs,
            }) as span:
                try:
                    result = await _execute_single_tool(tool_name, tool_args)
                    span.set_attribute("gen_ai.tool.ok", str(result.get("ok", True)))
                    result_summary = str(result)[:200]
                    span.set_attribute("gen_ai.tool.result_summary", result_summary)
                except Exception as e:
                    result = {"ok": False, "error": str(e)}
                    span.set_attribute("gen_ai.tool.ok", "False")
        else:
            try:
                result = await _execute_single_tool(tool_name, tool_args)
            except Exception as e:
                result = {"ok": False, "error": str(e)}

        if lf_span:
            try:
                lf_span.end(output={"ok": result.get("ok", True)})
            except (TypeError, AttributeError):
                try:
                    lf_span.output = {"ok": result.get("ok", True)}
                    lf_span.end()
                except Exception:
                    pass
            except Exception:
                pass

        return result

    def to_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }