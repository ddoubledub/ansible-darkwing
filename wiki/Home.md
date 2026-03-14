# ansible-darkwing

A general-purpose Ansible automation framework with a browser-based web GUI. Designed for teams managing mixed Linux environments who want a visual interface for building playbooks, managing inventory, scheduling runs, and tracking changes — without giving up the power of raw Ansible.

---

## What it is

ansible-darkwing is two things:

1. **A web GUI** — A FastAPI + React app that wraps your Ansible project. It reads and writes your actual files. No separate database, no abstraction layer. What you build in the UI is real YAML you can run from the CLI too.

2. **An Ansible framework skeleton** — A structured starting point for Ansible projects: annotated templates for roles and playbooks, a guardrail system for safe enforcement, multi-environment inventory, and vault integration.

The web GUI is the main product. The framework is what you point it at.

---

## Quick Links

| | |
|---|---|
| [Getting Started](Getting-Started) | Clone, configure, and deploy |
| [Web GUI Overview](Web-GUI) | Features, architecture, auth options |
| [User Guide](User-Guide) | Day-to-day usage |
| [Admin Guide](Admin-Guide) | Deployment, TLS, SAML/Entra ID |
| [API Reference](API-Reference) | All endpoints with examples |
| [Ansible Framework](Ansible-Framework) | Roles, playbooks, inventory, guardrails |
| [Scheduling](Scheduling) | Cron-based automated runs |
| [Troubleshooting](Troubleshooting) | Common errors and fixes |
| [Roadmap](Roadmap) | What's planned |

---

## At a glance

**Web GUI features:**
- Visual playbook builder with live YAML preview
- Inventory management (form and raw YAML modes)
- Scheduled runs (cron expressions)
- Real-time terminal (whitelisted commands)
- Git integration (commit, push, pull, branch switching)
- Vault encrypt/decrypt
- SAML (Entra ID), Basic Auth, or no-auth modes

**Framework features:**
- Assessment roles (reachability, sudo, host info, security audit, SSH users)
- Provisioning roles (user creation, SSH key deployment)
- Guardrail system preventing accidental enforcement
- Multi-environment inventory structure
- Annotated role and playbook templates
- ansible-vault integration

**Deployment:**
- Docker Compose (recommended)
- Caddy for TLS (built-in, automatic)
- Host networking so Ansible can SSH directly to targets
- No data store — reads/writes your actual repo files
