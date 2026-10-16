# WordCraft - Self-Hosted Cloud Document Workspace

Self-hostable, WebAssembly-powered "Google Docs / Microsoft Word Online" alternative built on [WordCraft](https://github.com/storytold/wordcraft).

WordCraft runs in the web browser via WebAssembly (`wasm32-unknown-unknown`) and connects to a high-performance Python FastAPI document management backend backed by SQLite metadata storage and persistent disk blob storage.

---

## System Architecture

```
                                  +-------------------------------------------------------+
                                  |                     Linux Server                      |
                                  |                                                       |
   User Browser                   |   +-----------------------------------------------+   |
+-----------------+   HTTP/80     |   |               wordcraft-web                   |   |
|                 | ------------> |   |              (Nginx Alpine)                   |   |
| - WASM Canvas   |               |   |                                               |   |
| - Dashboard UI  |               |   | - Serves static WASM/JS/HTML assets          |   |
|                 |               |   | - Sets COOP / COEP WASM isolation headers     |   |
+-----------------+               |   | - Reverse proxies /api/* -> wordcraft-backend |   |
                                  |   +-----------------------+-----------------------+   |
                                  |                           |                           |
                                  |                           | Internal HTTP             |
                                  |                           v                           |
                                  |   +-----------------------------------------------+   |
                                  |   |              wordcraft-backend                |   |
                                  |   |              (Python FastAPI)                 |   |
                                  |   |                                               |   |
                                  |   | - Multi-user auth (Bcrypt & PyJWT)            |   |
                                  |   | - Document CRUD & file sync APIs              |   |
                                  |   | - SQLite metadata DB & local file storage     |   |
                                  |   +-----------+-----------------------+-----------+   |
                                  |               |                       |               |
                                  +---------------|-----------------------|---------------+
                                                  |                       |
                                                  v                       v
                                        [wordcraft-db-data]     [wordcraft-doc-storage]
                                          (Named Volume)          (Named Volume)
```

---

## Features

- **Browser Document Editor**: Pure Rust WASM compiled engine capable of editing and saving `.docx`, `.odt`, `.md`, and `.pdf` files directly in web browsers.
- **Document Workspace Dashboard**: Integrated user dashboard for listing, creating, uploading, downloading, renaming, and deleting documents.
- **Multi-User Auth**: Token-based authentication (Bcrypt hashed passwords, JWT Bearer tokens).
- **Persistent Storage**: Named Docker volumes for document files and SQLite database metadata.
- **Cross-Origin WASM Security**: Pre-configured Nginx headers (`Cross-Origin-Embedder-Policy: require-corp` and `Cross-Origin-Opener-Policy: same-origin`) for WebAssembly performance and threading compatibility.
- **Automation / MCP Service Profile**: Optional CLI container profile for server-side document conversions and Model Context Protocol (MCP) workflows.

---

## Linux Deployment Guide (Ubuntu / Debian)

### 1. Prerequisites & Server Setup

Ensure your Linux server has Docker and Docker Compose installed:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker prerequisites
sudo apt install -y ca-certificates curl gnupg lsb-release

# Add Docker official GPG key and repository
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine & Compose plugin
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Enable and start Docker service
sudo systemctl enable --now docker
```

---

### 2. Firewall Configuration (UFW)

Ensure HTTP (80) and HTTPS (443) ports are open:

```bash
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'
sudo ufw enable
```

---

### 3. Deploying WordCraft Stack

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/salehgaliwala/google-doc-open-source.git wordcraft-server
   cd wordcraft-server
   ```

2. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   # Edit .env to set a unique secret key
   nano .env
   ```

3. **Start Docker Stack**:
   ```bash
   docker compose up -d --build
   ```

4. **Verify Container Status**:
   ```bash
   docker compose ps
   docker compose logs -f
   ```

Access WordCraft by navigating to `http://YOUR_SERVER_IP` in your browser.

---

### 4. Optional: Running the MCP / Automation Service Profile

To launch the automated CLI / MCP server service:

```bash
docker compose --profile mcp up -d wordcraft-mcp
```

---

### 5. Persistent Volume Backups & Restores

To back up database metadata and document files:

```bash
# Backup document storage and SQLite database to a tar archive
docker run --rm \
  -v wordcraft-doc-storage:/docs \
  -v wordcraft-db-data:/db \
  -v $(pwd):/backup \
  alpine tar -czvf /backup/wordcraft-backup-$(date +%F).tar.gz /docs /db
```

To restore from a backup tar archive:

```bash
docker run --rm \
  -v wordcraft-doc-storage:/docs \
  -v wordcraft-db-data:/db \
  -v $(pwd):/backup \
  alpine sh -c "tar -xzvf /backup/wordcraft-backup-YYYY-MM-DD.tar.gz -C /"
```

---

## License

WordCraft is dual-licensed under Apache 2.0 and MIT.
