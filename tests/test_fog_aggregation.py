"""
test_fog_aggregation.py
------------------------
Unit tests for the fog node's edge-processing logic: anomaly flagging
and windowed aggregation. These exercise the pure logic without needing
a live backend or real sensor threads.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fog"))

from fog.fog_node import FogNode
from sensors.sensor_simulator import SensorNode


def make_fog_node():
    # A FogNode instance whose background threads are never started;
    # we drive its buffer/methods directly for deterministic tests.
    sensor_node = SensorNode()
    return FogNode(sensor_node=sensor_node, backend_url="http://unused.invalid/api/ingest")


def test_is_anomalous_flags_out_of_range_temperature():
    fog = make_fog_node()
    assert fog._is_anomalous("temperature", 5.0) is True     # below expected 10-35C
    assert fog._is_anomalous("temperature", 22.0) is False    # within range


def test_is_anomalous_unknown_sensor_type_never_flagged():
    fog = make_fog_node()
    assert fog._is_anomalous("unknown_sensor", 999999) is False


def test_aggregate_window_computes_mean_min_max_and_excludes_anomalies():
    fog = make_fog_node()
    readings = [
        {"sensor_type": "temperature", "value": 20.0, "unit": "C", "timestamp": "t1", "anomalous": False},
        {"sensor_type": "temperature", "value": 22.0, "unit": "C", "timestamp": "t2", "anomalous": False},
        {"sensor_type": "temperature", "value": 500.0, "unit": "C", "timestamp": "t3", "anomalous": True},
    ]
    for r in readings:
        fog._buffer[r["sensor_type"]].append(r)

    payload = fog._aggregate_window()
    assert len(payload) == 1
    summary = payload[0]

    assert summary["sensor_type"] == "temperature"
    assert summary["sample_count"] == 3
    assert summary["anomaly_count"] == 1
    # Anomalous reading (500.0) must be excluded from mean/min/max
    assert summary["mean"] == 21.0
    assert summary["min"] == 20.0
    assert summary["max"] == 22.0


def test_aggregate_window_clears_buffer_after_call():
    fog = make_fog_node()
    fog._buffer["humidity"].append(
        {"sensor_type": "humidity", "value": 45.0, "unit": "%RH", "timestamp": "t1", "anomalous": False}
    )
    fog._aggregate_window()
    assert fog._buffer["humidity"] == []


def test_aggregate_window_all_anomalous_yields_null_stats():
    fog = make_fog_node()
    fog._buffer["motion"].append(
        {"sensor_type": "motion", "value": 5, "unit": "binary", "timestamp": "t1", "anomalous": True}
    )
    payload = fog._aggregate_window()
    summary = payload[0]
    assert summary["mean"] is None
    assert summary["min"] is None
    assert summary["max"] is None
    assert summary["anomaly_count"] == 1
