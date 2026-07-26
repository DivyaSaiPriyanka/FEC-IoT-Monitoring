"""
sensor_simulator.py
--------------------
Mock sensor layer for the Fog & Edge Computing CA project.

Simulates 5 heterogeneous sensor types, each with its own sampling
frequency and realistic value distributions (including occasional
noise / anomalies so the fog layer has something to filter).

Each sensor exposes a `read()` method returning a single reading dict:
    {
        "sensor_id": str,
        "sensor_type": str,
        "value": float,
        "unit": str,
        "timestamp": ISO-8601 str
    }

Sensors are run in their own thread by SensorNode, pushing readings
onto a thread-safe queue that the Fog Node consumes from.
"""

import random
import threading
import queue
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SensorConfig:
    sensor_type: str
    unit: str
    value_range: tuple          # (min, max) normal operating range
    frequency_hz: float         # readings per second
    anomaly_probability: float = 0.03   # chance of an out-of-range spike
    sensor_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


class BaseSensor(threading.Thread):
    """A single simulated sensor running on its own thread."""

    def __init__(self, config: SensorConfig, out_queue: "queue.Queue", stop_event: threading.Event):
        super().__init__(daemon=True, name=f"sensor-{config.sensor_type}-{config.sensor_id}")
        self.config = config
        self.out_queue = out_queue
        self.stop_event = stop_event

    def _generate_value(self) -> float:
        lo, hi = self.config.value_range
        if random.random() < self.config.anomaly_probability:
            # Simulate a faulty/anomalous reading (spike outside normal range)
            spread = (hi - lo) or 1
            return round(random.choice([lo - spread, hi + spread]) + random.uniform(-1, 1), 2)
        return round(random.uniform(lo, hi), 2)

    def read(self) -> dict:
        return {
            "sensor_id": self.config.sensor_id,
            "sensor_type": self.config.sensor_type,
            "value": self._generate_value(),
            "unit": self.config.unit,
            "timestamp": _now_iso(),
        }

    def run(self):
        interval = 1.0 / max(self.config.frequency_hz, 0.001)
        while not self.stop_event.is_set():
            reading = self.read()
            try:
                self.out_queue.put_nowait(reading)
            except queue.Full:
                pass  # drop reading if fog node cannot keep up
            time.sleep(interval)


# ----------------------------------------------------------------------
# Concrete sensor type factory
# ----------------------------------------------------------------------

DEFAULT_SENSOR_DEFINITIONS = [
    SensorConfig(sensor_type="temperature", unit="C", value_range=(18.0, 28.0), frequency_hz=1.0),
    SensorConfig(sensor_type="humidity", unit="%RH", value_range=(30.0, 70.0), frequency_hz=0.5),
    SensorConfig(sensor_type="motion", unit="binary", value_range=(0, 1), frequency_hz=2.0, anomaly_probability=0.0),
    SensorConfig(sensor_type="air_quality", unit="ppm_CO2", value_range=(400.0, 1000.0), frequency_hz=0.2),
    SensorConfig(sensor_type="light", unit="lux", value_range=(0.0, 1000.0), frequency_hz=0.5),
]


class SensorNode:
    """
    Manages the full set of simulated sensors for one physical/virtual
    location (e.g. one 'room' or one 'edge device').
    """

    def __init__(self, definitions=None, queue_maxsize: int = 10_000):
        self.definitions = definitions or DEFAULT_SENSOR_DEFINITIONS
        self.reading_queue: "queue.Queue" = queue.Queue(maxsize=queue_maxsize)
        self._stop_event = threading.Event()
        self._sensors = [BaseSensor(cfg, self.reading_queue, self._stop_event) for cfg in self.definitions]

    def start(self):
        for s in self._sensors:
            s.start()

    def stop(self):
        self._stop_event.set()
        for s in self._sensors:
            s.join(timeout=2)

    def get_queue(self) -> "queue.Queue":
        return self.reading_queue


if __name__ == "__main__":
    # Quick manual test: print readings for 5 seconds
    node = SensorNode()
    node.start()
    start = time.time()
    try:
        while time.time() - start < 5:
            try:
                r = node.get_queue().get(timeout=1)
                print(r)
            except queue.Empty:
                pass
    finally:
        node.stop()
