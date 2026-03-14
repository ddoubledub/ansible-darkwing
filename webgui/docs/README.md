# Ansible Playbook Builder

A web GUI for building, running, and managing Ansible playbooks — sits alongside your existing repo and reads/writes your actual files.

## What This Is

A FastAPI + React single-page app that provides a browser interface for your Ansible workflow. It does not replace your CLI — it wraps it. Every file you edit in the GUI is the same file on disk. You can switch between GUI and terminal at any time.

## Quick Start

```bash
cd your-ansible-repo/webgui
cp .env.example .env          # edit with your values
docker compose up -d --build
```

Access at `https://your-domain` (SAML) or `http://localhost:8420` (no auth / Basic Auth).

## Documentation

| Doc | What It Covers |
|-----|---------------|
| [User Guide](docs/USER-GUIDE.md) | Day-to-day usage — building plays, running playbooks, managing inventory |
| [Admin Guide](docs/ADMIN-GUIDE.md) | Deployment, auth config, Docker, SAML, security |
| [API Reference](docs/API-REFERENCE.md) | Every endpoint with examples — for scripting or extending |
| [Scheduling](docs/SCHEDULING.md) | Setting up automated cron-style playbook runs |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common errors and fixes |

## Architecture

```
/auto/ansible-gui/                  ← your ansible repo (git-managed)
├── inventories/prod/
│   ├── hosts.yml                   ← GUI reads/writes this
│   ├── group_vars/*.yml            ← GUI reads/writes these
│   └── host_vars/*.yml             ← GUI reads/writes these
├── playbooks/*.yml                 ← GUI creates/runs these
├── roles/*/                        ← GUI lists, creates, views these
├── ansible.cfg                     ← GUI reads/edits this
├── .ansible-gui/                   ← schedule data (gitignored)
│   ├── schedules.json
│   └── logs/*.json
└── webgui/                         ← the GUI application
    ├── server.py                   ← FastAPI backend
    ├── templates/index.html        ← frontend
    ├── auth.py                     ← SAML auth module
    ├── Dockerfile
    ├── docker-compose.yml
    └── saml/settings.json          ← Entra SAML config
```

The GUI never stores data separately. It reads your files, writes your files, and runs `ansible-playbook` / `git` / `ansible-vault` as subprocesses.
