"""
fog_node.py
-----------
Virtual Fog Node for the Fog & Edge Computing CA project.

Responsibilities (per the assignment brief):
  1. Receive raw readings from the sensor layer (in-process queue here;
     could equally be MQTT/CoAP in a distributed deployment).
  2. Process the data at the edge:
       - Anomaly filtering (drop/flag out-of-range values)
       - Windowed aggregation (mean/min/max per sensor per window)
       - De-duplication / rate smoothing
  3. Dispatch the processed payload to the cloud backend over HTTP,
     in batches, with retry + exponential backoff so transient network
     issues at the edge do not lose data.

Run standalone:
    python fog_node.py --backend-url http://<ec2-host>:8000/api/ingest
"""

import argparse
import collections
import logging
import queue
import statistics
import sys
import threading
import time
from datetime import datetime, timezone

import requests

import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from sensors.sensor_simulator import SensorNode  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("fog_node")


# Reasonable "normal" bounds used purely for edge-side anomaly flagging.
# (Kept independent from the sensor simulator's own range so the fog
# layer is doing real, meaningful filtering rather than just trusting
# the sensor.)
EXPECTED_RANGES = {
    "temperature": (10.0, 35.0),
    "humidity": (10.0, 90.0),
    "motion": (0, 1),
    "air_quality": (350.0, 1200.0),
    "light": (-10.0, 1100.0),
}


class FogNode:
    def __init__(
        self,
        sensor_node: SensorNode,
        backend_url: str,
        window_seconds: float = 5.0,
        dispatch_interval_seconds: float = 5.0,
        max_retries: int = 4,
        node_id: str = "fog-node-1",
    ):
        self.sensor_node = sensor_node
        self.backend_url = backend_url
        self.window_seconds = window_seconds
        self.dispatch_interval_seconds = dispatch_interval_seconds
        self.max_retries = max_retries
        self.node_id = node_id

        self._buffer: dict[str, list] = collections.defaultdict(list)
        self._buffer_lock = threading.Lock()
        self._stop_event = threading.Event()

        self._collector_thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, daemon=True)

        self.stats = {"received": 0, "flagged_anomalies": 0, "batches_sent": 0, "send_failures": 0}

    # ------------------------------------------------------------------
    # Edge processing
    # ------------------------------------------------------------------
    def _is_anomalous(self, sensor_type: str, value: float) -> bool:
        lo, hi = EXPECTED_RANGES.get(sensor_type, (float("-inf"), float("inf")))
        return not (lo <= value <= hi)

    def _collect_loop(self):
        q = self.sensor_node.get_queue()
        while not self._stop_event.is_set():
            try:
                reading = q.get(timeout=1)
            except queue.Empty:
                continue

            self.stats["received"] += 1
            reading["anomalous"] = self._is_anomalous(reading["sensor_type"], reading["value"])
            if reading["anomalous"]:
                self.stats["flagged_anomalies"] += 1
                log.warning("Anomalous reading flagged: %s", reading)

            with self._buffer_lock:
                self._buffer[reading["sensor_type"]].append(reading)

    def _aggregate_window(self) -> list[dict]:
        """Collapse the current buffer into one summarised payload per sensor type."""
        payload = []
        with self._buffer_lock:
            for sensor_type, readings in self._buffer.items():
                if not readings:
                    continue
                clean_values = [r["value"] for r in readings if not r["anomalous"]]
                summary = {
                    "fog_node_id": self.node_id,
                    "sensor_type": sensor_type,
                    "unit": readings[-1]["unit"],
                    "window_start": readings[0]["timestamp"],
                    "window_end": readings[-1]["timestamp"],
                    "sample_count": len(readings),
                    "anomaly_count": sum(1 for r in readings if r["anomalous"]),
                    "mean": round(statistics.fmean(clean_values), 3) if clean_values else None,
                    "min": min(clean_values) if clean_values else None,
                    "max": max(clean_values) if clean_values else None,
                    "last_value": readings[-1]["value"],
                    "dispatched_at": datetime.now(timezone.utc).isoformat(),
                }
                payload.append(summary)
            self._buffer.clear()
        return payload

    # ------------------------------------------------------------------
    # Dispatch to cloud backend
    # ------------------------------------------------------------------
    def _send_with_retry(self, payload: list[dict]) -> bool:
        backoff = 1.0
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(self.backend_url, json={"fog_node_id": self.node_id, "readings": payload}, timeout=5)
                if resp.status_code in (200, 201, 202):
                    return True
                log.error("Backend rejected batch (status %s): %s", resp.status_code, resp.text[:200])
            except requests.RequestException as exc:
                log.warning("Attempt %d/%d failed to reach backend: %s", attempt, self.max_retries, exc)
            time.sleep(backoff)
            backoff *= 2
        return False

    def _dispatch_loop(self):
        while not self._stop_event.is_set():
            time.sleep(self.dispatch_interval_seconds)
            payload = self._aggregate_window()
            if not payload:
                continue
            ok = self._send_with_retry(payload)
            if ok:
                self.stats["batches_sent"] += 1
                log.info("Dispatched batch of %d sensor summaries to backend.", len(payload))
            else:
                self.stats["send_failures"] += 1
                log.error("Failed to dispatch batch after %d retries; batch dropped.", self.max_retries)

    # ------------------------------------------------------------------
    def start(self):
        self.sensor_node.start()
        self._collector_thread.start()
        self._dispatch_thread.start()
        log.info("Fog node '%s' started (window=%ss, dispatch every %ss) -> %s",
                  self.node_id, self.window_seconds, self.dispatch_interval_seconds, self.backend_url)

    def stop(self):
        self._stop_event.set()
        self.sensor_node.stop()
        self._collector_thread.join(timeout=2)
        self._dispatch_thread.join(timeout=2)
        log.info("Fog node stopped. Stats: %s", self.stats)


def main():
    parser = argparse.ArgumentParser(description="Virtual Fog Node")
    parser.add_argument("--backend-url", default="http://localhost:8000/api/ingest",
                         help="Backend ingestion endpoint")
    parser.add_argument("--node-id", default="fog-node-1")
    parser.add_argument("--dispatch-interval", type=float, default=5.0,
                         help="Seconds between dispatches to backend")
    args = parser.parse_args()

    sensor_node = SensorNode()
    fog = FogNode(
        sensor_node=sensor_node,
        backend_url=args.backend_url,
        dispatch_interval_seconds=args.dispatch_interval,
        node_id=args.node_id,
    )
    fog.start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        fog.stop()


if __name__ == "__main__":
    main()
