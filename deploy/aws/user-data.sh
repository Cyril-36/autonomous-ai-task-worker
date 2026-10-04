#!/bin/bash
# EC2 user data for the public demo (Amazon Linux 2023, t3.small, 20 GB gp3).
# The security group opens only port 80. Replace the key placeholder before launching;
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
docker run -d --name task-worker --restart unless-stopped -p 80:8100 --env-file /opt/app.env --shm-size 1g -v worker-data:/app/data task-worker
