FEC PROJECT - INSTALLATION & RUN INSTRUCTIONS
==============================================
H9FECC Fog and Edge Computing - CA Project

PROJECT LAYOUT
--------------
sensors/            Mock sensor layer (5 sensor types, threaded simulators)
fog/                Virtual fog node: collects, filters, aggregates, dispatches to backend
backend/            Scalable cloud backend: Flask API + Redis queue + worker(s) + dashboard
deployment/         gunicorn config, systemd units, nginx config, EC2 provisioning script
docker-compose.yml  One-command local stack (redis + backend + worker + fog node)




UI REFRESH (cloud-blue dashboard)
---------------------------------
This refreshed version includes a redesigned dashboard with:
  - cloud-blue visual theme
  - overview metric cards
  - process-flow section for the end-to-end architecture
  - richer live sensor tiles with charts, status, min/max, sample count,
    fog node name, and anomaly totals
  - deployment and scalability summary blocks inside the dashboard

No backend deployment steps change. You can still deploy to AWS EC2 using
Gunicorn + Nginx exactly as shown below.

OPTION A - QUICK LOCAL RUN WITH DOCKER (recommended for testing)
------------------------------------------------------------------
Requirements: Docker + Docker Compose installed.

    docker compose up --build

This starts:
  - redis            (queue)
  - backend web      (Flask via gunicorn on http://localhost:8000)
  - backend worker   (drains queue -> SQLite)
  - fog_node         (generates sensors + dispatches to backend every 5s)

Open the dashboard at:  http://localhost:8000


OPTION B - MANUAL LOCAL RUN (no Docker)
------------------------------------------------------------------
Requires Python 3.10+ and (optionally) a local Redis server.
If Redis is not running, the backend automatically falls back to an
in-memory queue for single-process demo purposes.

1) Create and activate a virtual environment:
       python3 -m venv venv
       source venv/bin/activate        (Windows: venv\Scripts\activate)

2) Install backend dependencies:
       pip install -r backend/requirements.txt

3) Run the backend (dev server, with an inline worker thread so you
   don't need a separate terminal):
       cd backend
       set RUN_WORKER_INLINE=true      (Windows)
       export RUN_WORKER_INLINE=true   (Mac/Linux)
       python app.py

   The dashboard is now live at http://localhost:8000

4) In a second terminal, install and run the fog node (which starts
   the sensor layer internally):
       pip install -r fog/requirements.txt
       cd fog
       python fog_node.py --backend-url http://localhost:8000/api/ingest

   Sensor readings will start appearing on the dashboard within
   ~5-10 seconds (one dispatch cycle).


OPTION C - DEPLOY TO AWS EC2 (gunicorn + nginx, production layout)
------------------------------------------------------------------
1) Launch an EC2 instance (Amazon Linux 2023, t3.small or larger).
   Security group: allow inbound TCP 22 (SSH) and 80 (HTTP).

2) Copy the project to the instance, e.g.:
       scp -r -i your-key.pem fec_project ec2-user@<EC2-PUBLIC-IP>:/tmp/fec_project
       ssh -i your-key.pem ec2-user@<EC2-PUBLIC-IP>
       sudo mv /tmp/fec_project /opt/fec_project

3) Run the provisioning script (installs Python, Redis, nginx;
   creates the venv; installs systemd services for the web app and
   the queue worker; configures nginx as a reverse proxy):
       sudo bash /opt/fec_project/deployment/deploy_ec2.sh

4) Visit the dashboard at:  http://<EC2-PUBLIC-IP>/

5) Point the fog node (run on the same or a different machine, e.g.
   your laptop or a second EC2 instance acting as the "edge") at the
   public backend:
       cd fog
       pip install -r requirements.txt
       python fog_node.py --backend-url http://<EC2-PUBLIC-IP>/api/ingest

SCALING NOTES (see report for full justification):
  - Web tier: increase GUNICORN_WORKERS in backend/.env, or add more
    EC2 instances behind an Application Load Balancer / Auto Scaling
    Group (the app is stateless; state lives in Redis + the database).
  - Processing tier: start additional worker instances independently,
    e.g.  sudo systemctl enable --now fec-worker@2
                                        fec-worker@3
  - For a fully managed production setup, swap DATABASE_URL to an RDS
    endpoint and REDIS_URL to an ElastiCache endpoint - no code changes
    required.


CONFIGURATION (environment variables, backend/.env)
------------------------------------------------------------------
PORT              Port gunicorn/Flask listens on (default 8000)
REDIS_URL         e.g. redis://127.0.0.1:6379/0 (omit to use in-memory fallback)
DATABASE_URL      SQLAlchemy connection string (default sqlite:///fec_data.db)
GUNICORN_WORKERS  Number of gunicorn worker processes
GUNICORN_THREADS  Threads per gunicorn worker
RUN_WORKER_INLINE Set "true" to run the queue worker inside the Flask
                  process itself (dev/demo convenience only)


TROUBLESHOOTING
------------------------------------------------------------------
- Dashboard shows "Waiting for the first batch..." indefinitely:
    confirm the fog node's --backend-url points at the correct host/port
    and that /healthz returns {"status": "ok"}.
- 502 from nginx: check `sudo systemctl status fec-web` and
    `sudo journalctl -u fec-web -n 50`.
- Queue length keeps growing: start more worker instances
    (fec-worker@2, fec-worker@3, ...).
