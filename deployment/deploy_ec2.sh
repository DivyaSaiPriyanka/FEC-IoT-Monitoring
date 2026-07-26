#!/usr/bin/env bash
# ----------------------------------------------------------------------
# deploy_ec2.sh
#
# Provisions a fresh Amazon Linux 2023 EC2 instance to run the FEC
# backend (Flask + gunicorn), a local Redis queue, and the queue
# worker, fronted by nginx.
#
# Usage (on the EC2 instance, as ec2-user, after uploading the repo):
#   sudo bash deployment/deploy_ec2.sh
#
# Assumes the project has already been copied to /opt/fec_project
# (see README.md for the scp/git clone step).
# ----------------------------------------------------------------------
set -euo pipefail

PROJECT_DIR="/opt/fec_project"
BACKEND_DIR="${PROJECT_DIR}/backend"

echo ">>> Installing system packages (python, nginx, redis, git)"
sudo dnf update -y
sudo dnf install -y python3.11 python3.11-pip nginx redis6 git

echo ">>> Enabling and starting Redis"
sudo systemctl enable --now redis6

echo ">>> Creating Python virtual environment"
cd "${BACKEND_DIR}"
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

echo ">>> Writing environment file (edit as needed)"
if [ ! -f "${BACKEND_DIR}/.env" ]; then
  cat > "${BACKEND_DIR}/.env" <<EOF
PORT=8000
REDIS_URL=redis://127.0.0.1:6379/0
DATABASE_URL=sqlite:///${BACKEND_DIR}/fec_data.db
GUNICORN_WORKERS=3
GUNICORN_THREADS=4
EOF
fi

echo ">>> Installing systemd unit files"
sudo cp "${PROJECT_DIR}/deployment/fec-web.service" /etc/systemd/system/fec-web.service
sudo cp "${PROJECT_DIR}/deployment/fec-worker@.service" /etc/systemd/system/fec-worker@.service
sudo systemctl daemon-reload
sudo systemctl enable --now fec-web.service
sudo systemctl enable --now fec-worker@1.service

echo ">>> Configuring nginx reverse proxy"
sudo cp "${PROJECT_DIR}/deployment/nginx_fec.conf" /etc/nginx/conf.d/fec.conf
sudo rm -f /etc/nginx/conf.d/default.conf 2>/dev/null || true
sudo systemctl enable --now nginx
sudo systemctl reload nginx

echo ">>> Opening firewall (if firewalld is active)"
if systemctl is-active --quiet firewalld; then
  sudo firewall-cmd --permanent --add-service=http
  sudo firewall-cmd --reload
fi

echo ""
echo "=========================================================="
echo " Deployment complete."
echo " Remember to also open inbound port 80 (and 22) in the"
echo " EC2 Security Group attached to this instance."
echo ""
echo " Check status:"
echo "   sudo systemctl status fec-web"
echo "   sudo systemctl status fec-worker@1"
echo "   curl http://localhost/healthz"
echo "=========================================================="
