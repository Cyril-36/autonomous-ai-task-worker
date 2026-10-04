#!/bin/bash
# EC2 user data for the public demo (Amazon Linux 2023, t3.small, 20 GB gp3).
# The security group opens ports 80 and 443. Caddy serves HTTPS with a Let's Encrypt certificate for
# the Elastic IP's sslip.io name and redirects HTTP. Replace the key placeholder before launching;
# the key then lives only in /opt/app.env on the instance (mode 600).
set -euxo pipefail
dnf install -y docker git
systemctl enable --now docker
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
git clone --depth 1 https://github.com/Cyril-36/autonomous-ai-task-worker /opt/app
install -m 600 /dev/null /opt/app.env
cat > /opt/app.env <<'ENV'
AICREDITS_API_KEY=REPLACE_WITH_KEY
LLM_MODEL=google/gemini-2.5-flash-lite
LIMIT_INR=10
ENV
docker build -t task-worker /opt/app
docker network create web
docker run -d --name task-worker --network web --restart unless-stopped --env-file /opt/app.env --shm-size 1g -v worker-data:/app/data task-worker
docker run -d --name caddy --network web --restart unless-stopped -p 80:80 -p 443:443 -v caddy-data:/data caddy:2 caddy reverse-proxy --from 15-252-104-254.sslip.io --to task-worker:8100
