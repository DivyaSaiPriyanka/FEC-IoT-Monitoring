"""
models.py
---------
SQLAlchemy models for persisted sensor summaries.

Uses SQLite by default (zero-config, fine for CA demo purposes) but the
connection string is driven entirely by the DATABASE_URL environment
variable, so swapping in AWS RDS Postgres/MySQL for a "real" scalable
deployment is a one-line config change with no code change.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///fec_data.db")

# check_same_thread only needed/valid for sqlite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fog_node_id = Column(String(64), index=True, nullable=False)
    sensor_type = Column(String(32), index=True, nullable=False)
    unit = Column(String(16), nullable=True)
    window_start = Column(String(64), nullable=True)
    window_end = Column(String(64), nullable=True)
    sample_count = Column(Integer, default=0)
    anomaly_count = Column(Integer, default=0)
    mean = Column(Float, nullable=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    last_value = Column(Float, nullable=True)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "fog_node_id": self.fog_node_id,
            "sensor_type": self.sensor_type,
            "unit": self.unit,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "sample_count": self.sample_count,
            "anomaly_count": self.anomaly_count,
            "mean": self.mean,
            "min": self.min_value,
            "max": self.max_value,
            "last_value": self.last_value,
            "received_at": self.received_at.isoformat() if self.received_at else None,
        }


def init_db():
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
