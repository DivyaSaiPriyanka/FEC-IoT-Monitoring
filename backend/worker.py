"""
worker.py
---------
Independent worker process that drains the ingestion queue and persists
readings to the database.

Run one or more of these alongside the Flask/gunicorn web tier to scale
processing throughput independently of HTTP ingestion throughput:

    python worker.py
    # or run N of them (systemd template unit, separate EC2 instances,
    # or a small worker Auto Scaling Group of their own).
"""

import logging
import signal
import sys

from models import init_db, get_session, SensorReading
import queue_backend as qb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("worker")

_running = True


def _handle_stop(signum, frame):
    global _running
    log.info("Received signal %s, shutting down worker...", signum)
    _running = False


def persist_reading(session, data: dict):
    row = SensorReading(
        fog_node_id=data.get("fog_node_id", "unknown"),
        sensor_type=data.get("sensor_type", "unknown"),
        unit=data.get("unit"),
        window_start=data.get("window_start"),
        window_end=data.get("window_end"),
        sample_count=data.get("sample_count", 0),
        anomaly_count=data.get("anomaly_count", 0),
        mean=data.get("mean"),
        min_value=data.get("min"),
        max_value=data.get("max"),
        last_value=data.get("last_value"),
    )
    session.add(row)
    session.commit()


def process_forever():
    init_db()
    processed = 0
    while _running:
        data = qb.pop(timeout=5)
        if data is None:
            continue
        session = get_session()
        try:
            persist_reading(session, data)
            processed += 1
            if processed % 20 == 0:
                log.info("Worker has persisted %d readings so far.", processed)
        except Exception:
            session.rollback()
            log.exception("Failed to persist reading: %s", data)
        finally:
            session.close()


def main():
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    log.info("Worker starting (queue backend: %s)", "redis" if qb.using_redis() else "in-memory")
    process_forever()
    log.info("Worker stopped.")


if __name__ == "__main__":
    sys.exit(main() or 0)
