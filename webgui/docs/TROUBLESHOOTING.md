# Troubleshooting

## Container Won't Start

### `error: could not write config file /root/.gitconfig: Device or resource busy`

The entrypoint tries to modify the read-only mounted gitconfig. This was fixed in the entrypoint — it now copies to `/root/.gitconfig_runtime`. Make sure you have the latest `entrypoint.sh`.

### `docker-credential-desktop.exe: executable file not found`

Leftover Docker Desktop config. Fix:
```bash
echo '{}' > ~/.docker/config.json
```

### `BASIC_AUTH_PASS variable is not set`

Create your `.env` file:
```bash
cp .env.example .env
# Edit and set BASIC_AUTH_PASS
```

---

## Authentication Issues

### SAML: "invalid_response — The Message of the Response is not signed and the SP require it"

Entra signs the assertion, not the outer message. In `saml/settings.json`:
```json
"wantMessagesSigned": false
```

### SAML: 500 on `/api/auth/saml/acs`

Check `docker logs ansible-gui`. Common causes:

**`python-multipart` not installed:**
```
AssertionError: The `python-multipart` library must be installed to use form parsing.
```
Fix: Add `python-multipart>=0.0.6` to `requirements.txt` and rebuild.

**Certificate mismatch:** Verify the cert in `saml/settings.json` matches what Entra shows. Re-download and re-convert:
```bash
grep -v CERTIFICATE cert.cer | tr -d '\n'
```

**GCC/Government cloud:** URLs must use `login.microsoftonline.us` not `.com`.

### SAML: 401 on all API calls after login

If running multiple uvicorn workers, sessions are in-memory and not shared. Use `--workers 1` in the Dockerfile CMD.

### Basic Auth: can't access WebSocket terminal

The WebSocket auth check validates Basic Auth headers. Make sure your browser is sending them (it should after the initial page load prompt).

---

## SSH / Ansible Connection Issues

### `Bad owner or permissions on /root/.ssh/config`

The mounted SSH directory is read-only and owned by your host user, not root. Fix in `ansible.cfg`:
```ini
[ssh_connection]
ssh_args = -F /root/.ssh_runtime/config ...
```

### `Failed to add the host to the list of known hosts` / `unix_listener: Read-only file system`

SSH is trying to write to the read-only mounted `.ssh/`. Fix in `ansible.cfg`:
```ini
[ssh_connection]
ssh_args = -o UserKnownHostsFile=/root/.ssh_runtime/known_hosts -o ControlPath=/tmp/ansible-%%r@%%h:%%p ...
```

Full recommended `[ssh_connection]` block:
```ini
[ssh_connection]
pipelining = True
ssh_args = -o ControlMaster=auto -o ControlPersist=60s -o ControlPath=/tmp/ansible-%%r@%%h:%%p -o UserKnownHostsFile=/root/.ssh_runtime/known_hosts -o StrictHostKeyChecking=no -F /root/.ssh_runtime/config
```

### `private_key_file = /etc/ssh/.ssh/ansi_sec` not found

Mount it in `docker-compose.yml`:
```yaml
volumes:
  - /etc/ssh/.ssh:/etc/ssh/.ssh:ro
```

---

## Inventory Issues

### "No groups found in inventory"

The environment dropdown is empty. Check:
```bash
docker exec ansible-gui ls /repo/inventories/
```
If that's empty, verify `ANSIBLE_REPO_PATH` in `.env` points to the right directory.

### 500 on `/api/environments`

Usually a YAML parsing error in one of the files. Test directly:
```bash
docker exec ansible-gui python3 -c "
import yaml
# Custom loader for !vault tags
class L(yaml.SafeLoader): pass
L.add_constructor('!vault', lambda l,n: '<vault>')
for f in ['hosts.yml']:
    with open(f'/repo/inventories/prod/{f}') as fh:
        data = yaml.load(fh.read(), Loader=L)
        print(f'{f}: OK, {type(data)}')
"
```

### `!vault` tag errors

The app uses a custom YAML loader that handles `!vault`. If you're seeing `could not determine a constructor for the tag '!vault'`, you're running an older version of `server.py` that uses `yaml.safe_load()`. Update to the latest.

---

## Git Issues

### `error: could not write config file /root/.gitconfig`

The entrypoint copies gitconfig to a writable location. Verify:
```bash
docker exec ansible-gui env | grep GIT_CONFIG
# Should show: GIT_CONFIG_GLOBAL=/root/.gitconfig_runtime
```

### Push/pull fails with SSH error

Verify SSH keys are accessible:
```bash
docker exec ansible-gui ls -la /root/.ssh_runtime/
docker exec ansible-gui ssh -T git@ssh.dev.azure.com
```

---

## TLS / HTTPS Issues

### Caddy returns 404

The domain in your `Caddyfile` doesn't match the URL you're accessing. Check:
```bash
cat Caddyfile  # on host
docker exec ansible-gui-proxy cat /etc/caddy/Caddyfile  # in container
```
They should match. After editing, `docker-compose restart caddy`.

### `subject: CN=TRAEFIK DEFAULT CERT`

Another service (likely AWX/k3s Traefik) is on port 443. Either stop it or put Caddy on a different port:
```
:8443 {
    tls internal
    reverse_proxy localhost:8420
}
```

### `curl: (35) TLS error`

Caddy might not have started yet or the cert isn't provisioned. Check:
```bash
docker logs ansible-gui-proxy | tail -20
```

---

## Ansible Runtime Issues

### Missing collections

```
No module named 'ansible_collections.community'
```

Install inside the container:
```bash
docker exec ansible-gui ansible-galaxy collection install community.general
```

For persistence, add to `Dockerfile` after the `pip install ansible-core` line:
```dockerfile
RUN ansible-galaxy collection install community.general
```

### `callback plugin 'community.general.yaml' has been removed`

Update your `ansible.cfg`:
```ini
stdout_callback = ansible.builtin.default
result_format = yaml
```

### Log file not writable

```
[WARNING]: log file at '/repo/logs/ansible.log' is not writeable
```

Create the directory:
```bash
mkdir -p /auto/ansible-gui/logs
```

---

## Getting Help

### View logs
```bash
docker logs ansible-gui                        # app
docker logs ansible-gui 2>&1 | tail -100       # recent
docker logs ansible-gui 2>&1 | grep Traceback -A 20  # errors
docker logs ansible-gui-proxy                  # Caddy
```

### Test API directly
```bash
curl http://localhost:8420/api/health
curl http://localhost:8420/api/environments
```

### Test inside the container
```bash
docker exec -it ansible-gui bash
# Now you can run ansible, git, python, etc. directly
```
