"""OpenTelemetry tracing setup.

A trace is one request's journey through the system, made of spans: the Flask
request handler is a span, the outbound call to the weather API is a child
span, and each records its own start time, duration and attributes. Jaeger
stores them and lets you view the whole tree.

Tracing initialises only when OTEL_EXPORTER_OTLP_ENDPOINT is set. With the
variable unset -- in tests, or running the app locally -- every function here
becomes a no-op, so instrumentation never changes behaviour in environments
that have nowhere to send spans.
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def init_tracing(app, version="unknown"):
    """Instrument the Flask app and start exporting spans to Jaeger."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return None

    # The resource identifies WHO produced the spans. service.name is what
    # appears in Jaeger's service dropdown, so it has to be stable and
    # meaningful.
    resource = Resource.create({
        "service.name": os.environ.get("OTEL_SERVICE_NAME", "weather-app"),
        "service.version": version,
        "deployment.environment": os.environ.get("APP_ENV", "sandbox"),
    })

    provider = TracerProvider(resource=resource)

    # BatchSpanProcessor buffers spans and exports them on a background thread.
    # The alternative, SimpleSpanProcessor, exports synchronously and would add
    # the network round-trip to every single request -- instrumentation that
    # slows the thing it measures.
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)

    # Server spans: one per incoming HTTP request, with method, route and status.
    FlaskInstrumentor().instrument_app(app)

    # Client spans: one per outbound call made with `requests`, so a slow
    # upstream weather API shows up as a child span rather than as unexplained
    # time inside the handler. This is the whole point of distributed tracing.
    RequestsInstrumentor().instrument()
    return provider