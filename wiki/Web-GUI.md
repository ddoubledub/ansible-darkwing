# Web GUI

The web GUI is a FastAPI + React application that wraps your Ansible project. It is the primary interface for building playbooks, managing inventory, scheduling runs, and operating your environment day-to-day.

---

## Key design principle

**No separate data store.** The GUI reads and writes your actual YAML files — `hosts.yml`, `group_vars`, `host_vars`, playbooks. What you do in the UI is the same as editing files in your editor. Git is still your source of truth.

---

## Architecture

```
Browser
  └── React SPA (served by FastAPI)
        └── REST API + WebSocket (FastAPI / Uvicorn)
              └── Host filesystem (your Ansible repo)
              └── ansible-playbook, ansible-inventory, git (subprocesses)
```

The container runs with **host networking** so Ansible can SSH to your target hosts exactly as it would from your control node. No port forwarding gymnastics, no NAT issues.

---

## Features

### Playbook Builder
Build playbooks visually without writing YAML by hand.
- Select target groups or individual hosts from your inventory
- Browse and add roles from your `roles/` directory
- Configure role variables through the UI
- Live YAML preview updates as you build
- Run directly, save and run, or dry run (`--check`)

### Inventory Management
- **Form mode** — add hosts and groups through structured input fields
- **Raw mode** — edit `hosts.yml` directly with YAML validation
- Edit `group_vars` and `host_vars` files in-browser
- Switch between environments (prod, staging, dev) with the environment selector

### Scheduling
Cron-based playbook scheduling without a separate scheduler service.
- Standard 5-field cron expressions (`min hour dom month dow`)
- Enable/disable schedules without deleting them
- Per-run log files (JSON) with output, duration, and success status
- View run history in the UI
- See [Scheduling](Scheduling) for details

### Terminal
A restricted shell for read-oriented Ansible operations.
- Whitelisted commands: `ansible*`, `git`, `cat`, `ls`, `head`, `tail`, `grep`, `find`, `tree`, `wc`, `ping`, `hostname`, `whoami`, `pwd`, `which`, `id`, `date`
- Blocked: `ssh`, `bash`, `python`, `curl`, `rm`, `sudo`
- Shell operators blocked: `;`, `|`, `&`, `$`, `(`, `)`, backticks
- Command history (arrow up/down)
- Ctrl+C to kill running processes
- WebSocket-based for real-time output

### Git Integration
- View current branch, modified files, and remote status
- Commit staged changes
- Push to remote
- Pull with rebase
- View last 15 commits
- Switch branches

### Vault
- Encrypt plaintext values to vault-encrypted format
- Decrypt vault-encrypted files for viewing
- Discover encrypted files in the repo
- Vault password file mounted from host — never entered in the UI

### Configuration
- View and edit `ansible.cfg` in-browser

---

## Authentication

Three modes, evaluated in priority order:

| Mode | When to use |
|---|---|
| SAML (Entra ID / Azure AD) | Production — SSO, group-based access, session management |
| Basic Auth | Internal use — shared username and password |
| No auth | Local development only — do not expose externally |

Sessions use HMAC-signed cookies (HttpOnly, Secure, SameSite=Lax) with an 8-hour TTL by default.

See [Admin Guide](Admin-Guide) for setup instructions.

---

## Deployment

| Option | Description |
|---|---|
| Docker Compose + Caddy | Recommended. Automatic TLS, Caddy as reverse proxy. |
| Docker behind your own proxy | Use `docker-compose.simple.yml`, proxy via nginx/HAProxy/F5. |
| Bare metal / systemd | Run Uvicorn directly on the host with a systemd unit. |

Quick start (no auth, local dev):

```bash
cd webgui
docker compose -f docker-compose.simple.yml up -d
# open http://localhost:8420
```

See [Admin Guide](Admin-Guide) for production deployment.

---

## Tech Stack

| Component | Technology |
|---|---|
| API framework | FastAPI |
| ASGI server | Uvicorn |
| Frontend | React SPA |
| Reverse proxy | Caddy |
| Container | Docker |
| Auth | SAML 2.0 / python3-saml |
| No database | File-based only |
