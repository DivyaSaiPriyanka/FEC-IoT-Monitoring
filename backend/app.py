"""
app.py
------
Scalable cloud backend for the Fog & Edge Computing CA project.

Design summary (see project report for full justification):
  - Flask app served by gunicorn (multi-worker, sync/gthread) behind
    nginx on EC2; horizontally scalable via an Auto Scaling Group +
    Application Load Balancer (stateless app tier).
  - Ingestion endpoint (`POST /api/ingest`) does minimal work: validate
    -> push to queue -> return 202. This keeps request latency low even
    under bursty fog-node traffic.
  - A separate `worker.py` process drains the queue and writes to the
    database, so ingestion throughput and processing throughput scale
    independently (run more worker processes/instances under load).
  - Dashboard reads (`/api/summary`, `/api/timeseries/<type>`) hit the
    database directly since read load is much lighter than ingestion.
"""

import logging
import os

from flask import Flask, jsonify, request, render_template
from sqlalchemy import func, desc

from models import init_db, get_session, SensorReading
import queue_backend as qb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("backend")

app = Flask(__name__)

RUN_WORKER_INLINE = os.environ.get("RUN_WORKER_INLINE", "false").lower() == "true"

init_db()

if RUN_WORKER_INLINE:
    # Convenience for local/demo single-instance runs: spin up an
    # in-process worker thread instead of a separate `worker.py`
    # process. Not recommended for the real scalable deployment.
    import threading
    from worker import process_forever

    threading.Thread(target=process_forever, daemon=True, name="inline-worker").start()
    log.info("Inline worker thread started (RUN_WORKER_INLINE=true).")


# ----------------------------------------------------------------------
# Health check (used by ALB / EC2 target group health checks)
# ----------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "queue_backend": "redis" if qb.using_redis() else "in-memory"}), 200


# ----------------------------------------------------------------------
# Ingestion endpoint - called by fog node(s)
# ----------------------------------------------------------------------
@app.route("/api/ingest", methods=["POST"])
def ingest():
    body = request.get_json(silent=True)
    if not body or "readings" not in body:
        return jsonify({"error": "expected JSON body with a 'readings' list"}), 400

    fog_node_id = body.get("fog_node_id", "unknown")
    readings = body["readings"]
    if not isinstance(readings, list) or not readings:
        return jsonify({"error": "'readings' must be a non-empty list"}), 400

    for reading in readings:
        reading.setdefault("fog_node_id", fog_node_id)
        qb.push(reading)

    return jsonify({"accepted": len(readings), "queue_length": qb.queue_length()}), 202


# ----------------------------------------------------------------------
# Dashboard data APIs
# ----------------------------------------------------------------------
@app.route("/api/summary")
def api_summary():
    """Latest reading + basic stats per sensor type."""
    session = get_session()
    try:
        sensor_types = [row[0] for row in session.query(SensorReading.sensor_type).distinct()]
        summary = []
        for st in sensor_types:
            latest = (
                session.query(SensorReading)
                .filter(SensorReading.sensor_type == st)
                .order_by(desc(SensorReading.received_at))
                .first()
            )
            count = session.query(func.count(SensorReading.id)).filter(SensorReading.sensor_type == st).scalar()
            total_anomalies = (
                session.query(func.sum(SensorReading.anomaly_count))
                .filter(SensorReading.sensor_type == st)
                .scalar()
                or 0
            )
            summary.append({
                "sensor_type": st,
                "latest": latest.to_dict() if latest else None,
                "total_batches": count,
                "total_anomalies": int(total_anomalies),
            })
        return jsonify({"sensor_types": summary, "queue_length": qb.queue_length()})
    finally:
        session.close()


@app.route("/api/timeseries/<sensor_type>")
def api_timeseries(sensor_type):
    limit = int(request.args.get("limit", 50))
    session = get_session()
    try:
        rows = (
            session.query(SensorReading)
            .filter(SensorReading.sensor_type == sensor_type)
            .order_by(desc(SensorReading.received_at))
            .limit(limit)
            .all()
        )
        rows.reverse()
        return jsonify([r.to_dict() for r in rows])
    finally:
        session.close()


@app.route("/api/nodes")
def api_nodes():
    session = get_session()
    try:
        nodes = [row[0] for row in session.query(SensorReading.fog_node_id).distinct()]
        return jsonify({"fog_nodes": nodes})
    finally:
        session.close()


# ----------------------------------------------------------------------
# Dashboard UI
# ----------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


if __name__ == "__main__":
    # Local dev server only. In production, gunicorn imports `app` directly
    # (see deployment/gunicorn_config.py and the systemd unit file).
    app.run(host="0.0.0.0", port=8000, debug=True)
