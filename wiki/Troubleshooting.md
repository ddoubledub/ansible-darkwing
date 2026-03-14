# Troubleshooting

Common errors and how to fix them.

---

## Container won't start

**`gitconfig` busy / credential helper errors**

Docker may fail if your `~/.gitconfig` references a credential helper that isn't available inside the container. Remove or override the credential helper in the container's git config, or add an override to your `docker-compose.yml`:

```yaml
environment:
  - GIT_CONFIG_NOSYSTEM=1
```

**Missing `.env` file**

The app fails if required environment variables are missing. Ensure you've copied `.env.example` to `.env` and populated `SESSION_SECRET` at minimum.

**Port already in use**

```
Error: address already in use :::8420
```

Something else is using port 8420. Change the port in `docker-compose.simple.yml` or stop the conflicting process.

---

## Authentication issues

**SAML: 500 error on login**

Usually a certificate mismatch or incorrect ACS URL. Check:
- The ACS URL in `settings.json` matches exactly what's registered in Azure
- The certificate in `settings.json` matches the one in the Federation Metadata XML
- The entity ID matches on both sides

**SAML: "Invalid response signature"**

The IdP is signing responses but the certificate in your `settings.json` is wrong or expired. Download the current certificate from Azure and update `settings.json`.

**SAML: Works in Chrome, fails in Safari / GCC High**

Some government/high-security Azure tenants use non-standard endpoints. Verify the `singleSignOnService.url` in your `settings.json` matches the actual login URL from Federation Metadata XML exactly.

**Basic Auth: WebSocket terminal keeps disconnecting**

WebSocket connections require the same credentials as REST requests. Ensure your browser is sending the Basic Auth header for WebSocket connections. Some browsers prompt separately for WebSocket auth.

**Session expires unexpectedly**

Default session TTL is 8 hours. Increase via `.env`:
```env
SESSION_MAX_AGE=86400
```

---

## SSH / Ansible connection issues

**`Permission denied (publickey)`**

- Verify the SSH key is mounted into the container and has permissions 600
- Check `ansible.cfg` has the correct `private_key_file` path as seen from inside the container (usually `/root/.ssh/id_ed25519`)
- Verify the key is authorized on the target host for the `remote_user`

**`Host key verification failed`**

`host_key_checking = False` is set in `ansible.cfg` by default. If you've changed it, either revert or add the host to `~/.ssh/known_hosts` inside the container.

**`SSH config file /root/.ssh/config: bad configuration`**

Your mounted SSH config has syntax errors or references options not supported by the SSH version in the container. Review the config or avoid mounting it.

**Ansible can't reach hosts**

The container uses host networking — if Ansible works from your control node CLI, it should work from the container. Check:
- The container is running in host network mode (`network_mode: host` in compose)
- `ansible_host` values in your inventory are correct
- No firewall rules blocking the container from connecting

---

## Inventory issues

**Groups missing in the playbook builder dropdown**

The GUI reads groups from `hosts.yml` at request time. If you edited the file outside the GUI, refresh the page. If groups still don't appear, validate the inventory:

```bash
bash scripts/validate_inventory.sh
```

**YAML parse error in inventory**

The raw editor in the GUI validates YAML on save, but if you edited outside the GUI, run:

```bash
ansible-inventory -i inventories/prod/hosts.yml --list
```

**`!vault` tags causing parse errors**

Vault-encrypted values use YAML tags (`!vault |`). Some YAML parsers outside of Ansible don't understand these. This is expected — use `ansible-inventory` (not a generic YAML parser) to validate inventory containing vault values.

---

## Git issues

**`git push` fails: "remote: Repository not found"**

The container's git config may not have credentials for the remote. Mount your SSH key and ensure `~/.ssh/config` (or the git remote URL) uses SSH rather than HTTPS.

**Commit fails with "Author identity unknown"**

Git requires a name and email to commit. Add to your `ansible.cfg` volume-mounted gitconfig, or set env vars:
```yaml
environment:
  - GIT_AUTHOR_NAME=Ansible GUI
  - GIT_AUTHOR_EMAIL=ansible@yourdomain.com
  - GIT_COMMITTER_NAME=Ansible GUI
  - GIT_COMMITTER_EMAIL=ansible@yourdomain.com
```

---

## TLS / HTTPS issues

**Caddy returns 404**

The `Caddyfile` hostname must match the hostname you're accessing. If you're accessing by IP, use the IP in the Caddyfile or switch to `docker-compose.simple.yml` and handle TLS externally.

**Browser warns about self-signed certificate**

This is expected for `tls internal` mode. Import the Caddy root CA into your browser's trusted store, or use Let's Encrypt if the host is publicly accessible.

---

## Ansible runtime issues

**`ERROR! the role 'some_role' was not found`**

Roles must be in the `roles/` directory relative to the repo root. Check `roles_path` in `ansible.cfg`.

**Missing collections**

```
ERROR! couldn't resolve module/action 'ansible.posix.authorized_key'
```

Install required collections:
```bash
ansible-galaxy collection install -r collections/requirements.yml
```

**Log file permission error**

If `logs/ansible.log` can't be written, check directory permissions. The `logs/` directory must be writable by the user running Ansible inside the container.

---

## Getting more information

**Container logs:**
```bash
docker compose logs -f
```

**API directly:**
```bash
curl http://localhost:8420/health
curl -u admin:password http://localhost:8420/inventory/hosts
```

**Shell inside the container:**
```bash
docker compose exec webgui bash
```

**Ansible connectivity test:**
```bash
ansible -m ping all -vvv
```
