#!/usr/bin/env bash
set -e

# Automated deployment script for WordCraft on Linux server
# Domain: docs.fixmywordpress.tech

DOMAIN="${1:-docs.fixmywordpress.tech}"
EMAIL="${2:-admin@fixmywordpress.tech}"

echo "=================================================="
echo " Starting WordCraft Deployment for ${DOMAIN}"
echo "=================================================="

# 1. Update system & install prerequisites
echo "[1/5] Updating packages and installing prerequisites..."
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release certbot python3-certbot-nginx

# 2. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "[2/5] Installing Docker..."
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg || true
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs 2>/dev/null || echo "bookworm") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin || sudo apt-get install -y docker.io docker-compose
fi

# 3. Configure environment variables
echo "[3/5] Configuring environment variables..."
if [ ! -f .env ]; then
    JWT_SECRET_GEN=$(openssl rand -hex 32 2>/dev/null || echo "secret-$(date +%s)")
    cat <<EOF > .env
WEB_PORT=8080
JWT_SECRET=${JWT_SECRET_GEN}
DOMAIN=${DOMAIN}
EOF
    echo "Generated .env file with custom JWT secret."
fi

# 4. Build and start Docker containers
echo "[4/5] Building and starting Docker containers..."
sudo docker compose up -d --build

# 5. Obtain Let's Encrypt SSL certificate & configure host reverse proxy
echo "[5/5] Setting up Nginx host reverse proxy & Let's Encrypt SSL for ${DOMAIN}..."

# Install Nginx on host if not installed
if ! command -v nginx &> /dev/null; then
    sudo apt-get install -y nginx
fi

# Write Nginx host proxy configuration for port 8080
cat <<EOF | sudo tee /etc/nginx/sites-available/wordcraft
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        client_max_body_size 100M;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/wordcraft /etc/nginx/sites-enabled/wordcraft
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

# Run certbot to issue and configure SSL certificate
echo "Obtaining SSL certificate via Certbot..."
sudo certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "${EMAIL}" || echo "Certbot SSL automated issuance attempted. Verify DNS record for ${DOMAIN} points to this server IP."

echo "=================================================="
echo " Deployment Complete!"
echo " WordCraft is available at: https://${DOMAIN}"
echo "=================================================="
