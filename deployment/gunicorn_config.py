"""
gunicorn_config.py
-------------------
Production gunicorn configuration for the FEC backend.

Usage (from the backend/ directory, with the venv activated):
    gunicorn -c ../deployment/gunicorn_config.py app:app

Worker count follows the standard (2 x CPU cores) + 1 recommendation.
Using the 'gthread' worker class so each worker can also serve a few
concurrent slow requests (e.g. dashboard polling) without needing a
process per connection.
"""

import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.environ.get("GUNICORN_THREADS", 4))
worker_class = "gthread"
timeout = 30
graceful_timeout = 30
keepalive = 5

accesslog = "-"          # stdout -> captured by systemd/journald
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Recycle workers periodically to guard against memory creep
max_requests = 2000
max_requests_jitter = 200
