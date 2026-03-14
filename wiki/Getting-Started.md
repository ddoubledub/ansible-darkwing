# Getting Started

This page covers everything you need to go from zero to a running ansible-darkwing deployment.

---

## Prerequisites

**Control node (where you run this):**
- Docker and Docker Compose
- Git
- SSH key with access to your target hosts
- Ansible Core 2.14+ (if running Ansible from the CLI in addition to the GUI)

**Target hosts:**
- Python 3 (Ansible auto-detects)
- A service account with SSH access and sudo

---

## 1. Clone the repo

```bash
git clone https://github.com/your-org/ansible-darkwing.git
cd ansible-darkwing
```

If you want to track your own changes separately, use the template repo button on GitHub to create your own copy first.

---

## 2. Configure Ansible

Edit `ansible.cfg` — at minimum set your SSH key and remote user:

```ini
remote_user = your_ansible_service_account
private_key_file = /path/to/your/ssh/key
```

If you use ansible-vault, also set:

```ini
vault_password_file = /path/to/.vault_pass
```

---

## 3. Build your inventory

Copy the example inventory and populate it:

```bash
cp -r inventories/example inventories/prod
```

Edit `inventories/prod/hosts.yml`:

```yaml
all:
  children:
    linux:
      hosts:
        my-server:
          ansible_host: 10.0.0.10
    ubuntu:
      hosts:
        my-server:
```

Validate it:

```bash
bash scripts/validate_inventory.sh
```

---

## 4. Configure the web GUI

```bash
cp webgui/.env.example webgui/.env
```

Edit `webgui/.env`:

```env
SESSION_SECRET=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
BASIC_AUTH_USER=admin
BASIC_AUTH_PASS=your-password-here
ANSIBLE_REPO_PATH=/repo
```

For SAML/Entra ID auth, see [Admin Guide](Admin-Guide).

---

## 5. Start the GUI

**Development (no TLS):**

```bash
cd webgui
docker compose -f docker-compose.simple.yml up -d
```

Open `http://localhost:8420`.

**Production (TLS via Caddy):**

```bash
cd webgui
docker compose up -d
```

See [Admin Guide](Admin-Guide) for Caddy and SAML configuration.

---

## 6. Install Ansible collections

If running Ansible from the CLI or control node:

```bash
ansible-galaxy collection install -r collections/requirements.yml
```

---

## 7. Verify connectivity

From the terminal in the GUI or your CLI:

```bash
ansible -m ping all
```

---

## Next steps

- [User Guide](User-Guide) — how to use the GUI day-to-day
- [Ansible Framework](Ansible-Framework) — roles, playbooks, inventory, guardrails
- [Admin Guide](Admin-Guide) — production deployment, SAML, TLS
