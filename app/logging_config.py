"""Structured JSON logging with the current trace/span ID attached to every
record -- the join key between a Jaeger trace and its CloudWatch log lines.
Hex-formatted (32/16 chars) to match how Jaeger displays and searches IDs.
"""

import logging
import os
import sys

from opentelemetry import trace
from pythonjsonlogger import jsonlogger


class TraceJsonFormatter(jsonlogger.JsonFormatter):
    """JSON formatter that adds the current trace context to every record."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)

        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["service"] = os.environ.get("OTEL_SERVICE_NAME", "weather-app")

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            # Invalid means no active span (startup, background thread,
            # tracing disabled) -- omit rather than log IDs that look real.
            log_record["trace_id"] = format(ctx.trace_id, "032x")
            log_record["span_id"] = format(ctx.span_id, "016x")


def configure_logging(level=None):
    """Send JSON logs to stdout, where the awslogs driver collects them."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        TraceJsonFormatter("%(asctime)s %(level)s %(name)s %(message)s")
    )

    root = logging.getLogger()
    # Replace, don't append -- gunicorn/Flask's own handlers would otherwise
    # print every line twice.
    root.handlers = [handler]
    root.setLevel(level or os.environ.get("LOG_LEVEL", "INFO"))

    return root