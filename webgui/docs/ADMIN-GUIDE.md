# Admin Guide

## Prerequisites

- Docker and docker-compose on the host
- Your ansible repo cloned to the host
- SSH keys for git operations (Azure DevOps, GitHub, etc.)
- SSH key for ansible target access (`private_key_file` in your `ansible.cfg`)

## Deployment

### 1. Place the webgui directory in your repo

```
your-ansible-repo/
├── webgui/           ← the GUI app goes here
├── inventories/
├── playbooks/
├── roles/
└── ansible.cfg
```

### 2. Configure environment

```bash
cd your-ansible-repo/webgui
cp .env.example .env
nano .env
```

Key settings:

| Variable | Value | Notes |
|----------|-------|-------|
| `ANSIBLE_REPO_PATH` | `/auto/ansible-gui` | Absolute path to your repo on the host |
| `SSH_KEY_PATH` | `/home/ansible/.ssh` | SSH keys for git + ansible |
| `GITCONFIG_PATH` | `/home/ansible/.gitconfig` | Git author identity |
| `BASIC_AUTH_ENABLED` | `true` | Quick auth for testing |
| `BASIC_AUTH_PASS` | `<strong password>` | Required if basic auth enabled |
| `SAML_ENABLED` | `false` | Set `true` after configuring SAML |

### 3. Mount the ansible SSH key

If your SSH key lives outside your home directory, add an extra volume mount to `docker-compose.yml`:

```yaml
- /path/to/your/ssh/key:/root/.ssh/id_rsa:ro
```

### 4. Build and start

```bash
docker-compose up -d --build
```

### 5. Verify

```bash
curl http://localhost:8420/api/health
docker logs ansible-gui | tail -20
```

## Docker Compose Files

| File | Use Case |
|------|----------|
| `docker-compose.yml` | Production — Caddy reverse proxy on 443, TLS, SAML support |
| `docker-compose.simple.yml` | Dev/testing — app only on port 8420, no TLS |

Both use `network_mode: host` so ansible can SSH directly to targets using the host's network.

## Networking

The container uses **host networking** — it shares the host's IP, routes, and DNS. This means:

- `ansible-playbook` inside the container SSHes to targets exactly as if run on the host
- The app listens on port 8420 on the host's interfaces
- Caddy listens on 80/443 on the host's interfaces
- No Docker bridge networking, no port mapping needed

## TLS / HTTPS

Caddy handles TLS via the `Caddyfile`:

```
your-domain.example.com {
    tls internal           # self-signed cert for internal domains
    reverse_proxy localhost:8420
}
```

For a real domain with Let's Encrypt, remove `tls internal` — Caddy auto-provisions.

If another service already occupies port 443 (like Traefik from AWX/k3s), use a different port:

```
:8443 {
    tls internal
    reverse_proxy localhost:8420
}
```

---

## Authentication

Three options, in order of preference:

### SAML (Entra ID)

Best for production. See [SAML Setup](#saml-setup-entra-id) below.

### Basic Auth

Good for internal use or during SAML setup.

```env
BASIC_AUTH_ENABLED=true
BASIC_AUTH_USER=admin
BASIC_AUTH_PASS=<password>
SAML_ENABLED=false
```

The browser prompts for credentials. Sent as HTTP Basic Auth headers on every request including WebSocket connections.

### No Auth

Only for localhost testing. The app prints a warning at startup.

```env
BASIC_AUTH_ENABLED=false
SAML_ENABLED=false
```

---

## SAML Setup (Entra ID)

### In Azure Portal

1. **Entra ID** → Enterprise Applications → New → "Create your own"
2. Name: "Ansible Playbook Builder"
3. Single sign-on → SAML
4. Basic SAML Configuration:

| Field | Value |
|-------|-------|
| Entity ID | `https://your-domain/api/auth/saml/metadata` |
| Reply URL | `https://your-domain/api/auth/saml/acs` |
| Sign on URL | `https://your-domain/api/auth/saml/login` |
| Logout URL | `https://your-domain/api/auth/saml/sls` |

5. Download **Certificate (Base64)** from the signing certificate section.

6. Assign users/groups under Users and groups.

### On the server

Convert the certificate (strip headers, join to one line):

```bash
./setup-saml.sh ~/cert.cer YOUR_TENANT_ID your-domain
```

Or manually:

```bash
grep -v CERTIFICATE cert.cer | tr -d '\n'
# Paste output into saml/settings.json → idp → x509cert
```

**Government cloud:** If your Entra is GCC, URLs use `login.microsoftonline.us` instead of `.com`. The setup script handles this if you pass the correct tenant ID.

Enable in `.env`:

```env
SAML_ENABLED=true
BASIC_AUTH_ENABLED=false
```

### SAML settings.json notes

- `wantMessagesSigned` must be `false` — Entra signs the assertion, not the outer message
- `wantAssertionsSigned` should be `true`
- `x509cert` must be one continuous base64 string — no linebreaks, no `-----BEGIN/END CERTIFICATE-----`

### Session behavior

- Cookie-based, `HttpOnly`, `Secure`, `SameSite=Lax`
- HMAC-signed with `SESSION_SECRET`
- 8-hour TTL (configurable via `SESSION_MAX_AGE`)
- In-memory store — sessions are lost on container restart

---

## Security Model

### What's protected

- All API endpoints require authentication (SAML session or Basic Auth header)
- WebSocket terminal authenticates before accepting the connection
- No CORS — frontend and API are same-origin
- File writes are blocked to `.git/`, `.github/`, and the webgui directory itself
- Path traversal is blocked on all file operations

### Terminal restrictions

Only whitelisted binaries can execute: `ansible*`, `git`, `cat`, `ls`, `head`, `tail`, `grep`, `find`, `tree`, `wc`, `ping`, `hostname`, `whoami`, `pwd`, `which`, `id`, `date`.

Blocked: `ssh`, `bash`, `python`, `curl`, `rm`, `sudo`, `env` (leaks secrets).

Shell operators blocked at character level: `;|&`$(){}!><\`

Commands are parsed with `shlex.split()` and executed via `subprocess_exec` — no shell is ever invoked.

### Execution limits

Max 3 concurrent `ansible-playbook` executions (configurable via `MAX_CONCURRENT_RUNS` env var). Additional requests get HTTP 429.

### Container considerations

- Runs as root (required for SSH key access and repo file writes)
- `network_mode: host` — no network isolation
- SSH keys are mounted read-only, copied to a writable path at startup with correct permissions
- Auth is the perimeter — anyone with valid credentials can run ansible

---

## systemd Service

```bash
sudo tee /etc/systemd/system/ansible-gui.service << 'EOF'
[Unit]
Description=Ansible Playbook Builder
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=your-ansible-repo/webgui
ExecStart=/usr/bin/docker-compose up -d --build
ExecStop=/usr/bin/docker-compose down
User=ansible

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ansible-gui
sudo systemctl start ansible-gui
```

---

## Updating

After making changes to `server.py` or `templates/index.html`:

```bash
cd your-ansible-repo/webgui
docker-compose down && docker-compose up -d --build
```

The Dockerfile copies the app files into the image at build time. Volume-mounted files (repo, SSH keys, gitconfig, SAML config) are live — changes to those take effect on restart without rebuilding.

---

## Logs

```bash
docker logs ansible-gui              # app logs
docker logs ansible-gui-proxy        # Caddy logs (if using Caddy)
docker logs ansible-gui 2>&1 | grep "Traceback" -A 20  # Python errors
```
