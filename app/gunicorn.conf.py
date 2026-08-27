"""Gunicorn configuration.

Exists for one reason: Prometheus metrics across multiple workers.

Each gunicorn worker is a separate OS process with its own metrics registry.
A scrape of /metrics is served by whichever worker the OS happens to give the
connection to, so without the multiprocess collector you see roughly 1/N of
your traffic, and counters appear to jump backwards when a different worker
answers the next scrape.

The multiprocess collector fixes this by having every worker write its samples
into a shared directory (PROMETHEUS_MULTIPROC_DIR). On scrape, the values from
all workers are aggregated. Two hooks below make that work correctly.
"""

import os
import shutil

from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics

bind = "0.0.0.0:8000"
workers = 2
accesslog = "-"          # access log to stdout, for the awslogs driver
errorlog = "-"
loglevel = "info"


def on_starting(server):
    """Clear the multiprocess directory before the first worker starts.

    Stale .db files from a previous container would otherwise be counted as
    live workers, inflating every metric after a restart.
    """
    path = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if path:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)


def child_exit(server, worker):
    """Mark a worker's metrics as dead when it exits.

    Without this, a worker that gunicorn recycles leaves its counters behind
    forever and they keep being summed into the totals.
    """
    GunicornPrometheusMetrics.mark_process_dead_on_child_exit(worker.pid)