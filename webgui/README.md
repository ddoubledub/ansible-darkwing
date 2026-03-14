# Ansible Playbook Builder

A lightweight web GUI that sits alongside your existing Ansible repo. Reads and writes your actual files — no separate data store.

## Architecture

```
your-ansible-repo/
├── ansible-gui/              ← drop this folder in
│   ├── server.py             ← FastAPI backend
│   ├── auth.py               ← Entra SAML auth module
│   ├── templates/index.html  ← frontend
│   ├── saml/settings.json    ← SAML config (you create from .example)
│   ├── Dockerfile
│   ├── docker-compose.yml    ← production (Caddy + TLS + SAML)
│   ├── docker-compose.simple.yml  ← dev (no auth, port 8420)
│   ├── Caddyfile
│   └── .env.example
├── inventories/
├── playbooks/
├── roles/
└── ansible.cfg
```

---

## Quick Start (no auth, local dev)

```bash
cd your-ansible-repo/ansible-gui

# Option A: Docker
docker compose -f docker-compose.simple.yml up -d
# Open http://localhost:8420

# Option B: Bare metal
pip install -r requirements.txt
python server.py
```

---

## Production Deployment with Docker + SAML

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your values:
#   ANSIBLE_REPO_PATH  — absolute path to your ansible repo on the host
#   DOMAIN             — hostname for TLS cert
#   SESSION_SECRET     — generate: python3 -c "import secrets; print(secrets.token_hex(32))"
#   VAULT_PASS_FILE    — path to your vault password file
#   SSH_KEY_PATH       — path to SSH keys for git operations
```

### 2. Configure Entra ID (Azure AD) SAML

#### In the Azure Portal:

1. Go to **Entra ID** > **Enterprise Applications** > **New Application** > **Create your own**
2. Name it "Ansible Playbook Builder", select **Integrate any other application**
3. Go to **Single sign-on** > **SAML**
4. Set **Basic SAML Configuration**:

| Field | Value |
|---|---|
| Identifier (Entity ID) | `https://your-domain/api/auth/saml/metadata` |
| Reply URL (ACS URL) | `https://your-domain/api/auth/saml/acs` |
| Sign on URL | `https://your-domain/api/auth/saml/login` |
| Logout URL | `https://your-domain/api/auth/saml/sls` |

5. Under **Attributes & Claims**, ensure these are mapped (most are defaults):

| Claim | Source Attribute |
|---|---|
| `emailaddress` | user.userprincipalname |
| `displayname` | user.displayname |
| `name` | user.userprincipalname |

6. (Optional) Under **Attributes & Claims** > **Add a group claim**, select "Groups assigned to the application" — this lets you use group-based access control later.

7. Under **SAML Signing Certificate**, download **Certificate (Base64)**.

8. Note the **Login URL** and **Azure AD Identifier** from section 4.

#### In your ansible-gui:

```bash
cp saml/settings.json.example saml/settings.json
```

Edit `saml/settings.json`:

```jsonc
{
  "sp": {
    // Replace YOUR_HOST with your actual domain
    "entityId": "https://ansible-builder.corp.local/api/auth/saml/metadata",
    "assertionConsumerService": {
      "url": "https://ansible-builder.corp.local/api/auth/saml/acs",
      ...
    }
  },
  "idp": {
    // YOUR_TENANT_ID from Entra portal
    "entityId": "https://sts.windows.net/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/",
    "singleSignOnService": {
      "url": "https://login.microsoftonline.com/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/saml2",
      ...
    },
    // Paste the Base64 cert content (open the .cer file, copy everything between BEGIN/END CERTIFICATE)
    "x509cert": "MIIC8DCCAdi..."
  }
}
```

#### Assign users:

In Entra > Enterprise Apps > your app > **Users and groups** > Add the users/groups that should have access.

### 3. Update Caddyfile

Edit `Caddyfile`, replace the domain:

```
ansible-builder.corp.local {
    tls internal              # self-signed for internal domains
    # tls /path/to/cert.pem /path/to/key.pem   # or bring your own cert
    # Remove tls line entirely for Let's Encrypt with a public domain
    reverse_proxy app:8420
}
```

### 4. Enable SAML and deploy

In your `.env`:
```bash
SAML_ENABLED=true
```

```bash
docker compose up -d --build
```

### 5. Verify

```bash
# Check health
curl -k https://ansible-builder.corp.local/api/health

# Check SP metadata (give this URL to Entra if it asks)
curl -k https://ansible-builder.corp.local/api/auth/saml/metadata
```

Open `https://ansible-builder.corp.local` in a browser — it should redirect to Entra login.

---

## Deployment Options

### Option A: Docker Compose + Caddy (recommended)
- `docker-compose.yml` — Caddy handles TLS, reverse proxy to app
- Automatic cert provisioning for public domains
- Self-signed certs for internal domains with `tls internal`

### Option B: Docker behind existing reverse proxy
If you already have nginx/HAProxy/F5:

```bash
docker compose -f docker-compose.simple.yml up -d
```

Then proxy to `http://ansible-gui-host:8420` from your existing LB. Make sure to forward:
- `X-Forwarded-Host`
- `X-Forwarded-Port`
- `X-Forwarded-Proto`

These headers are required for SAML to construct the correct callback URLs.

### Option C: Bare metal / systemd

```ini
[Unit]
Description=Ansible Playbook Builder
After=network.target

[Service]
Type=simple
User=ansible
WorkingDirectory=/opt/ansible-repo/ansible-gui
Environment=ANSIBLE_REPO=/opt/ansible-repo
Environment=SAML_ENABLED=true
Environment=SESSION_SECRET=your-random-hex
ExecStart=/usr/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8420
Restart=always

[Install]
WantedBy=multi-user.target
```

Put this behind your reverse proxy for TLS.

---

## SAML Auth Flow

```
Browser → GET / → Middleware sees no session → 302 to /api/auth/saml/login
  → 302 to Entra login.microsoftonline.com
  → User authenticates with Entra
  → Entra POST /api/auth/saml/acs with SAML assertion
  → Server validates assertion, creates session cookie
  → 302 to / → App loads, session valid
```

Session cookies are:
- `HttpOnly` (no JS access)
- `Secure` (HTTPS only)
- `SameSite=Lax`
- HMAC-signed (tamper-proof)
- 8-hour TTL (configurable via `SESSION_MAX_AGE`)

---

## API Endpoints

### Inventory
- `GET /api/environments` — list environments
- `GET /api/inventory/{env}` — hosts.yml + group_vars + host_vars
- `PUT /api/inventory/{env}/group_vars/{group}` — update group vars
- `PUT /api/inventory/{env}/host_vars/{host}` — update host vars

### Roles
- `GET /api/roles` — list roles with defaults/meta
- `GET /api/role/{name}` — full role details
- `POST /api/roles` — create role (standard ansible-galaxy structure)
- `PUT /api/role/{name}/{subpath}` — update role file

### Playbooks
- `GET /api/playbooks` — list playbooks
- `POST /api/playbooks` — write/create playbook

### Config & Vault
- `GET /api/cfg` / `PUT /api/cfg` — ansible.cfg
- `GET /api/vault/files` — find encrypted files
- `POST /api/vault/encrypt` / `POST /api/vault/decrypt/{path}`

### Git
- `GET /api/git/status` — branch, changed files, remote
- `GET /api/git/log` — commit history
- `POST /api/git/commit` — stage + commit
- `POST /api/git/push` / `POST /api/git/pull`
- `POST /api/git/checkout` — switch branch

### Execution
- `POST /api/run` — run ansible-playbook

### Auth
- `GET /api/auth/me` — current user
- `GET /api/auth/saml/metadata` — SP metadata for Entra
- `GET /api/auth/logout` — destroy session

---

## Security

- **SAML auth** via Entra ID with signed assertions
- **Path traversal blocked** — all file ops sandboxed to repo root
- **Session cookies** — HttpOnly, Secure, SameSite, HMAC-signed
- **No secrets in frontend** — vault password stays server-side
- `/api/run` executes real playbooks — consider `--check` enforcement or add approval workflow
- For multi-instance, swap the in-memory session store in `auth.py` for Redis
