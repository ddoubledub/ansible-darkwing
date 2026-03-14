# Getting Started

This repo is a ready-to-fork Ansible framework with an optional web GUI. Fork it, configure three files, and you have a working environment — either on your laptop or served over HTTPS from a control node.

---

## 1. Fork and clone

Fork this repo on GitHub so you can pull upstream improvements while keeping your own inventory and config.

```bash
git clone https://github.com/YOUR_USERNAME/ansible-darkwing
cd ansible-darkwing
```

Install Ansible collection dependencies:

```bash
ansible-galaxy collection install -r collections/requirements.yml
```

---

## 2. Configure — three files

### `ansible.cfg`

Set your service account and SSH key:

```ini
remote_user = your_ansible_user
private_key_file = /path/to/your/ssh/key

# Optional — only needed if using ansible-vault
vault_password_file = /path/to/.vault_pass
```

### `inventories/<your-env>/hosts.yml`

Copy the included example inventory as your starting point, then populate it with your real hosts:

```bash
cp -r inventories/example inventories/prod
```

```yaml
all:
  hosts:
    my-server-01:
      ansible_host: 10.0.1.10
      host_tags: "ubuntu,web"

  children:
    ubuntu:
      hosts:
        my-server-01:
```

Run the inventory validator to catch YAML errors:

```bash
bash scripts/validate_inventory.sh
```

### `webgui/.env`

```bash
cd webgui
cp .env.example .env
```

At minimum, set these three:

```env
ANSIBLE_REPO_PATH=/absolute/path/to/ansible-darkwing
SESSION_SECRET=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
BASIC_AUTH_PASS=<your password>
```

---

## 3. Choose your deployment

### Option A — Local / laptop (no TLS)

Best for development or personal use. Runs on port 8420 with basic auth.

```bash
cd webgui
docker compose -f docker-compose.simple.yml up -d --build
```

Open `http://localhost:8420` — you'll be prompted for the username/password you set in `.env`.

To stop:
```bash
docker compose -f docker-compose.simple.yml down
```

---

### Option B — Control node over HTTPS

Best for a team or always-on setup. Caddy handles TLS automatically.

**Prerequisites on the control node:**
- Docker + Docker Compose
- Port 443 open (or whichever port you configure in `Caddyfile`)
- Your ansible SSH key accessible on the node

**1. Set your domain in `.env`:**

```env
DOMAIN=ansible.your-company.com
```

**2. Review `webgui/Caddyfile`:**

```
your-domain.example.com {
    tls internal    # ← self-signed for internal domains
                    #   remove this line for Let's Encrypt (public domain)
    reverse_proxy localhost:8420
}
```

For a public domain with automatic Let's Encrypt cert, delete the `tls internal` line. For an internal hostname, keep it — Caddy generates a self-signed cert and you'll need to trust it in your browser.

**3. Start:**

```bash
cd webgui
docker compose up -d --build
```

Open `https://your-domain` — basic auth prompt will appear.

**To update after making changes:**

```bash
docker compose down && docker compose up -d --build
```

---

## 4. Add your hosts to the GUI

Once running, open the **Inventory** tab. The GUI reads and writes the inventory configured in `ansible.cfg` (default: `inventories/prod/hosts.yml`) and its `group_vars`/`host_vars` directly — no separate data store.

Add a host, assign it to a group, and set `ansible_host` to its IP. Then test from the **Terminal** tab:

```bash
ansible all -m ping
```

---

## 5. Optional — Enable SAML (Entra ID / Azure AD)

For team deployments where you want SSO instead of a shared password:

1. Follow the setup steps in [webgui/docs/ADMIN-GUIDE.md](webgui/docs/ADMIN-GUIDE.md#saml-setup-entra-id)
2. Configure `webgui/saml/settings.json` from the `.example` file
3. In `.env`:
   ```env
   SAML_ENABLED=true
   BASIC_AUTH_ENABLED=false
   ```
4. `docker compose down && docker compose up -d --build`

---

## 6. Staying up to date

Because you forked, you can pull upstream changes without losing your inventory or config:

```bash
git remote add upstream https://github.com/ORIGINAL_OWNER/ansible-darkwing
git fetch upstream
git merge upstream/main
```

Your inventory, `.env`, and `ansible.cfg` are gitignored or in your branch — they won't be overwritten.

---

## What's next

| Goal | Where to start |
|------|----------------|
| Understand the role pattern | [roles/role_template/](roles/role_template/) — fully annotated skeleton |
| Build a new role | Copy `roles/role_template/`, see README for example roles |
| Build a new playbook | Copy `playbooks/playbook_template.yml` |
| Provision users | Build a `user_provision` role; see README for the pattern |
| GUI docs | [webgui/docs/](webgui/docs/) |
