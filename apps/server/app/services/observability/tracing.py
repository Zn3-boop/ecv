from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from typing import Any

TRACE_ENABLE = os.getenv("OTEL_TRACE_ENABLE", "false").lower() == "true"

if TRACE_ENABLE:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider = TracerProvider()
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if otlp_endpoint:
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
    else:
        processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("desktop-agent.genai")

    @contextmanager
    def traced_execution(span_name: str, attributes: dict[str, Any]):
        with tracer.start_as_current_span(span_name, attributes=attributes) as span:
            yield span
else:
    class _DummyTracer:
        def start_as_current_span(self, *a, **kw):
            class _DummySpan:
                def __enter__(self):
                    return self
                def __exit__(self, *a, **kw):
                    pass
                def set_attribute(self, *a, **kw):
                    pass
            return _DummySpan()

    tracer = _DummyTracer()

    @contextmanager
    def traced_execution(span_name: str, attributes: dict[str, Any]):
        class _DummySpan:
            def set_attribute(self, *a, **kw):
                pass
        yield _DummySpan()


def compute_args_hash(args: dict[str, Any]) -> str:
    raw = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_trace_safe_tool_attrs(
    tool_name: str,
    tool_args: dict[str, Any],
    call_id: str = "",
) -> dict[str, Any]:
    args_hash = compute_args_hash(tool_args)
    return {
        "gen_ai.tool.name": tool_name,
        "gen_ai.tool.args_hash": args_hash,
        "gen_ai.tool.call_id": call_id,
    }


def init_tracing() -> None:
    pass


@contextmanager
def traced_multimodal_execution(span_name: str, attributes: dict[str, Any] | None = None):
    with traced_execution(span_name, attributes or {}) as span:
        yield span


def set_multimodal_attributes(span: Any, *, input_mime_type: str = "", output_mime_type: str = "") -> None:
    if input_mime_type:
        try:
            span.set_attribute("gen_ai.input.mime_type", input_mime_type)
        except Exception:
            pass
    if output_mime_type:
        try:
            span.set_attribute("gen_ai.output.mime_type", output_mime_type)
        except Exception:
            pass


def record_span_error(span: Any, error: Exception) -> None:
    try:
        span.set_attribute("error.type", type(error).__name__)
        span.set_attribute("error.message", str(error)[:200])
    except Exception:
        pass