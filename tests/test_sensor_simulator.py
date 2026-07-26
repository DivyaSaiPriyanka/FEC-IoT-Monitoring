"""
test_sensor_simulator.py
-------------------------
Unit tests for the mock sensor layer.
"""
import os
import sys
import queue as pyqueue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.sensor_simulator import BaseSensor, SensorConfig, SensorNode


def test_reading_has_expected_shape():
    cfg = SensorConfig(sensor_type="temperature", unit="C", value_range=(18.0, 28.0), frequency_hz=1.0)
    sensor = BaseSensor(cfg, pyqueue.Queue(), __import__("threading").Event())
    reading = sensor.read()

    assert reading["sensor_type"] == "temperature"
    assert reading["unit"] == "C"
    assert "timestamp" in reading
    assert "sensor_id" in reading
    assert isinstance(reading["value"], float)


def test_values_are_mostly_within_range_when_anomaly_probability_zero():
    cfg = SensorConfig(
        sensor_type="humidity", unit="%RH", value_range=(30.0, 70.0),
        frequency_hz=1.0, anomaly_probability=0.0,
    )
    sensor = BaseSensor(cfg, pyqueue.Queue(), __import__("threading").Event())
    values = [sensor.read()["value"] for _ in range(200)]
    assert all(30.0 <= v <= 70.0 for v in values)


def test_anomalies_occur_when_probability_is_one():
    cfg = SensorConfig(
        sensor_type="air_quality", unit="ppm_CO2", value_range=(400.0, 1000.0),
        frequency_hz=1.0, anomaly_probability=1.0,
    )
    sensor = BaseSensor(cfg, pyqueue.Queue(), __import__("threading").Event())
    values = [sensor.read()["value"] for _ in range(20)]
    assert any(v < 400.0 or v > 1000.0 for v in values)


def test_sensor_node_starts_and_produces_readings_from_all_types():
    node = SensorNode()
    node.start()
    try:
        seen_types = set()
        import time
        deadline = time.time() + 6
        while time.time() < deadline and len(seen_types) < len(node.definitions):
            try:
                r = node.get_queue().get(timeout=1)
                seen_types.add(r["sensor_type"])
            except pyqueue.Empty:
                continue
        assert seen_types == {d.sensor_type for d in node.definitions}
    finally:
        node.stop()
