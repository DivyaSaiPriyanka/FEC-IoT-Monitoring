"""
queue_backend.py
-----------------
Thin abstraction over the ingestion queue that decouples the fast,
stateless HTTP ingestion path (Flask/gunicorn) from the slower,
stateful DB-write path (worker process).

This is the key "scalability" building block for the CA brief:
  - The Flask app (behind gunicorn, N workers, load-balanced across
    EC2 instances in an Auto Scaling Group) only needs to validate the
    payload and push it onto the queue -> very fast response, so it
    can absorb bursty sensor traffic.
  - One or more independent `worker.py` processes pull off the queue
    and persist to the database. You can scale the number of workers
    independently of the number of web front-ends (e.g. more workers
    during peak ingestion, more web dynos to serve dashboard reads).

Backend selection:
  - If REDIS_URL is set (recommended for real deployments / ElastiCache),
    use a Redis list as the queue (RPUSH / BLPOP).
  - Otherwise, fall back to a process-local in-memory queue. This is
    fine for local development and demoing on a single EC2 instance,
    but obviously does not work across multiple processes/instances.
"""

import json
import os
import queue as pyqueue

REDIS_URL = os.environ.get("REDIS_URL")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "fec:ingest")

_redis_client = None
if REDIS_URL:
    import redis  # imported lazily so redis-py is only required if REDIS_URL is set
    _redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Fallback in-memory queue (single-process only)
_local_queue: "pyqueue.Queue" = pyqueue.Queue()


def using_redis() -> bool:
    return _redis_client is not None


def push(payload: dict):
    data = json.dumps(payload)
    if _redis_client:
        _redis_client.rpush(QUEUE_NAME, data)
    else:
        _local_queue.put(data)


def pop(timeout: int = 5):
    """Blocking pop. Returns the parsed dict, or None on timeout."""
    if _redis_client:
        result = _redis_client.blpop(QUEUE_NAME, timeout=timeout)
        if result is None:
            return None
        _, data = result
        return json.loads(data)
    else:
        try:
            data = _local_queue.get(timeout=timeout)
            return json.loads(data)
        except pyqueue.Empty:
            return None


def queue_length() -> int:
    if _redis_client:
        return _redis_client.llen(QUEUE_NAME)
    return _local_queue.qsize()
