# FEC — Fog & Edge Computing CA Project

Scalable IoT architecture: mock sensors → virtual fog node (edge processing)
→ cloud backend (queue + workers + dashboard), deployable on AWS EC2 behind
gunicorn + nginx.

See **readme.txt** for full install/run instructions (local, Docker, and AWS
EC2 deployment). This file gives a quick architectural summary for the report.

## Architecture

```
 ┌───────────┐      ┌────────────────┐      ┌─────────────────────────────┐
 │  Sensors  │      │   Fog Node     │      │        Cloud Backend        │
 │ (5 types, │─────▶│ filter/flag    │─────▶│  Flask API (gunicorn)       │
 │ threaded  │      │ anomalies,     │ HTTP │   └─▶ Redis queue           │
 │ sim.)     │      │ window-       │ POST  │        └─▶ worker(s)         │
 └───────────┘      │ aggregate,    │      │              └─▶ DB (SQLite/  │
                     │ retry+backoff │      │                  RDS)        │
                     └────────────────┘      │  Dashboard (polls REST API) │
                                              └─────────────────────────────┘
```

- **Sensors** (`sensors/`): 5 simulated sensor types (temperature, humidity,
  motion, air quality, light), each on its own thread with configurable
  sampling frequency and an injected anomaly rate.
- **Fog node** (`fog/`): consumes raw readings, flags out-of-range values,
  aggregates into per-type windowed summaries (mean/min/max/anomaly count),
  and dispatches batches to the backend over HTTP with exponential-backoff
  retries — the edge layer keeps working even if the cloud link is briefly
  unavailable.
- **Backend** (`backend/`): Flask app served by gunicorn. The ingestion
  endpoint does minimal work (validate + push to a Redis queue), so it stays
  responsive under bursty traffic. One or more independent `worker.py`
  processes drain the queue and write to the database — ingestion and
  processing throughput scale independently. A live dashboard polls a small
  REST API and renders per-sensor tiles with sparkline history.
- **Deployment** (`deployment/`): gunicorn config, systemd units (including a
  template unit so you can run `fec-worker@2`, `fec-worker@3`, ... to scale
  processing), nginx reverse-proxy config, and a one-shot EC2 provisioning
  script.

## Scalability mechanisms (for the report)

1. **Decoupled ingestion via queue** — Redis sits between the web tier and
   the persistence tier, absorbing bursts and letting each tier scale on its
   own axis.
2. **Stateless web tier** — the Flask app holds no in-memory state beyond the
   optional demo fallback queue, so it can run behind an ALB with an Auto
   Scaling Group across multiple EC2 instances.
3. **Horizontally scalable workers** — the worker is a plain script with no
   shared state other than the queue and DB, so N instances can run
   concurrently (multiple systemd units, or on separate machines).
4. **Config-driven backing services** — `DATABASE_URL` / `REDIS_URL` env vars
   mean swapping SQLite → RDS or local Redis → ElastiCache is a config change,
   not a code change.
5. **gunicorn worker/thread tuning** — `GUNICORN_WORKERS` / `GUNICORN_THREADS`
   let the web tier use multiple cores per instance before you even need to
   add instances.

## Repo layout

```
sensors/            Mock sensor layer
fog/                 Virtual fog node
backend/             Flask API, queue abstraction, worker, dashboard
deployment/          gunicorn, systemd, nginx, EC2 provisioning script
docker-compose.yml   One-command local stack
readme.txt           Full installation & run instructions (required by CA brief)
```


## UI refresh included

This refreshed version includes a cleaner **cloud-blue dashboard UI** with:

- a hero header for the AWS / fog-computing context
- top overview cards for sensor count, fog nodes, persisted batches, and anomalies
- a visible **process flow** section explaining sensor → fog → API → queue → workers → dashboard
- redesigned live sensor cards with icons, trend charts, min/max values, sample counts, node names, and status labels
- an AWS EC2 deployment summary aligned with **Gunicorn + Nginx** hosting

The backend behaviour remains the same, so the updated interface can still be deployed directly to EC2 using the provided provisioning script and systemd services.
