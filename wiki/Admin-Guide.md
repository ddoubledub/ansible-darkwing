# Admin Guide

Deployment, TLS, and authentication configuration for ansible-darkwing.

---

## Prerequisites

- Docker and Docker Compose on the host
- The ansible-darkwing repo cloned and configured (see [Getting Started](Getting-Started))
- SSH private key accessible on the host
- DNS entry pointing to the host (for TLS with real certs)

---

## Deployment options

### Option A: Docker Compose + Caddy (recommended)

Caddy handles TLS automatically — either Let's Encrypt for public domains or self-signed for internal use.

```bash
cd webgui
cp .env.example .env
# edit .env
docker compose up -d
```

Caddy serves on port 443 (HTTPS) and 80 (redirects to HTTPS). Edit `Caddyfile` to set your hostname.

**For an internal domain with self-signed cert:**
```
your-host.internal {
    tls internal
    reverse_proxy localhost:8420
}
```

**For a public domain with Let's Encrypt:**
```
ansible.yourdomain.com {
    reverse_proxy localhost:8420
}
```

### Option B: Docker behind your own reverse proxy

Use `docker-compose.simple.yml` and proxy through your existing nginx, HAProxy, or F5:

```bash
docker compose -f docker-compose.simple.yml up -d
```

The app listens on port 8420. Your proxy should forward to `http://localhost:8420` and pass `X-Forwarded-For`, `X-Forwarded-Proto` headers.

### Option C: Bare metal / systemd

Run Uvicorn directly on the host:

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8420
```

Create a systemd unit for persistent operation. Manage TLS separately via your existing infrastructure.

---

## Environment configuration (`.env`)

| Variable | Required | Description |
|---|---|---|
| `SESSION_SECRET` | Yes | HMAC secret for session cookies. Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ANSIBLE_REPO_PATH` | Yes | Path to your Ansible repo inside the container (usually `/repo`) |
| `BASIC_AUTH_USER` | No | Username for Basic Auth mode |
| `BASIC_AUTH_PASS` | No | Password for Basic Auth mode |
| `SESSION_MAX_AGE` | No | Session TTL in seconds (default: 28800 = 8 hours) |
| `SAML_*` | No | SAML configuration (see below) |

---

## Authentication

Authentication modes are evaluated in priority order. If SAML is configured, it takes precedence. If Basic Auth credentials are set, that's used next. If neither is configured, the app starts with no authentication (development only).

### SAML (Entra ID / Azure AD) — recommended for production

**In Azure Portal:**
1. Register a new Enterprise Application
2. Set up Single Sign-On → SAML
3. Set the Reply URL (ACS URL) to `https://your-host/saml/acs`
4. Set the Entity ID to `https://your-host/saml/metadata`
5. Download the Federation Metadata XML

**Convert the certificate:**
```bash
openssl x509 -in your-cert.cer -out your-cert.pem
```

**Create `webgui/saml/settings.json`** (copy from `settings.json.example`) and populate:
- `sp.entityId` — your Entity ID
- `sp.assertionConsumerService.url` — your ACS URL
- `idp.entityId` — from Federation Metadata XML
- `idp.singleSignOnService.url` — from Federation Metadata XML
- `idp.x509cert` — certificate content (without headers)

**In `.env`:**
```env
SAML_SP_ENTITY_ID=https://your-host/saml/metadata
SAML_ACS_URL=https://your-host/saml/acs
```

### Basic Auth — good for internal use

```env
BASIC_AUTH_USER=admin
BASIC_AUTH_PASS=your-strong-password
```

All requests (including WebSocket connections for the terminal) require these credentials.

### No auth — development only

If neither SAML nor Basic Auth is configured, the app starts unauthenticated. A warning is printed at startup. Do not expose this externally.

---

## SSH key setup

The container uses host networking — Ansible runs as if it's on your host. Mount your SSH private key into the container:

```yaml
# in docker-compose.yml
volumes:
  - /home/youruser/.ssh/id_ed25519:/root/.ssh/id_ed25519:ro
```

The entrypoint script sets correct file permissions (600) on startup.

---

## Vault password file

Mount your vault password file if using ansible-vault:

```yaml
volumes:
  - /path/to/.vault_pass:/root/.vault_pass:ro
```

Reference it in `ansible.cfg`:

```ini
vault_password_file = /root/.vault_pass
```

---

## Updating

When new container images are published:

```bash
docker compose pull
docker compose up -d
```

Your inventory, playbooks, and configuration files are mounted from the host — they are not inside the container and are not affected by updates.

---

## Logging

Application logs:
```bash
docker compose logs -f
```

Scheduled run logs are stored in `.ansible-gui/logs/` in your repo directory as JSON files.

Ansible execution logs go to `logs/ansible.log` (set in `ansible.cfg`).

---

## Security considerations

- Run behind TLS in all non-development environments
- Use SAML or Basic Auth — never leave auth disabled in production
- The terminal is restricted to whitelisted commands — it cannot be used as a general shell
- The container uses host networking for Ansible SSH access; ensure your firewall limits inbound access to the GUI port
- Vault passwords and SSH keys are mounted read-only and never exposed through the API
