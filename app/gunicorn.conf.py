"""Gunicorn config. The two hooks below exist for one reason: Prometheus
metrics across multiple worker processes, each with its own registry --
without them a scrape only sees whichever worker answered it, and counters
appear to jump backwards. PROMETHEUS_MULTIPROC_DIR is the shared directory
workers write samples into for scrape-time aggregation.
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
    # Stale .db files from a previous container would otherwise be counted
    # as live workers, inflating every metric after a restart.
    path = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if path:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)


def child_exit(server, worker):
    # Without this, a recycled worker's counters live forever and keep
    # being summed into the totals.
    GunicornPrometheusMetrics.mark_process_dead_on_child_exit(worker.pid)