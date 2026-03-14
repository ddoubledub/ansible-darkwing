# API Reference

Base URL: `https://your-domain` or `http://localhost:8420`

All endpoints require authentication (SAML session cookie or Basic Auth header) except `/api/health`.

---

## Inventory

### List environments
```
GET /api/environments
→ { "environments": ["prod"] }
```

### Get inventory
```
GET /api/inventory/{env}
→ { "hosts_raw": "...", "hosts_parsed": {...}, "group_vars": {...}, "host_vars": {...} }
```

### Update hosts.yml (raw)
```
PUT /api/inventory/{env}/hosts_raw
Body: { "content": "all:\n  hosts:\n    ..." }
→ { "status": "ok" }
```
Validates YAML before writing. Returns 400 if invalid.

### Add host
```
POST /api/inventory/{env}/host
Body: { "hostname": "new-server", "ansible_host": "10.0.0.5", "tags": ["linux", "prod"] }
→ { "status": "ok", "hostname": "new-server" }
```

### Remove host
```
DELETE /api/inventory/{env}/host/{hostname}
→ { "status": "ok", "removed_from": ["all.hosts", "ubuntu", "iten"] }
```

### Add group
```
POST /api/inventory/{env}/group
Body: { "group_name": "new_group", "hosts": ["host1", "host2"] }
→ { "status": "ok", "group": "new_group", "host_count": 2 }
```

### Update group_vars
```
PUT /api/inventory/{env}/group_vars/{group}
Body: { "vars": { "http_port": "443", "ssl": "true" } }
→ { "status": "ok" }
```

### Update host_vars
```
PUT /api/inventory/{env}/host_vars/{host}
Body: { "vars": { "ansible_host": "10.0.0.5" } }
→ { "status": "ok" }
```

---

## Roles

### List roles
```
GET /api/roles
→ { "roles": [{ "name": "stig_hardening", "vars": {...}, "meta": {...}, "has_tasks": true, "structure": ["tasks","defaults","handlers"] }] }
```

### Get role details
```
GET /api/role/{name}
→ { "name": "stig_hardening", "files": { "tasks/main.yml": "---\n...", "defaults/main.yml": "..." } }
```

### Create role
```
POST /api/roles
Body: { "name": "my_role", "description": "Does things", "defaults": { "var1": "value" } }
→ { "status": "created", "name": "my_role" }
```
Creates standard structure: tasks/, defaults/, handlers/, vars/, meta/, templates/, files/.

### Update role file
```
PUT /api/role/{name}/{subpath}
Body: { "content": "---\n- name: task\n  ..." }
→ { "status": "ok" }
```

---

## Playbooks

### List playbooks
```
GET /api/playbooks
→ { "playbooks": [{ "path": "scan.yml", "name": "Security Scan", "raw": "---\n..." }] }
```

### Get playbook
```
GET /api/playbook/{path}
→ { "path": "scan.yml", "raw": "...", "parsed": [...] }
```

### Write playbook
```
POST /api/playbooks
Body: { "path": "new_play.yml", "content": "---\n- name: ..." }
→ { "status": "ok" }
```

---

## Execution

### Run playbook
```
POST /api/run
Body: {
  "playbook": "scan.yml",        // OR "yaml_content": "---\n..."
  "inventory": "prod",
  "limit": "web_servers",
  "tags": "",
  "check": false,
  "diff": false,
  "verbose": 0
}
→ { "success": true, "stdout": "...", "stderr": "...", "returncode": 0, "command": "..." }
```

Use `yaml_content` to run without saving. Use `playbook` to run a saved file. Use `check: true` for dry run.

### Execute command (non-streaming)
```
POST /api/exec
Body: { "cmd": "ansible --version", "timeout": 120 }
→ { "success": true, "stdout": "...", "returncode": 0 }
```
Only whitelisted commands. No shell operators.

### Terminal (WebSocket)
```
WS /api/ws/terminal
Send: { "cmd": "ansible-playbook playbooks/scan.yml -i inventories/prod" }
Recv: { "type": "stdout", "data": "PLAY [scan] ***" }
Recv: { "type": "exit", "code": 0 }
Send: { "cmd": "SIGINT" }  ← kill running process
```

---

## Schedules

### List schedules
```
GET /api/schedules
→ { "schedules": [{ "id": "a1b2c3d4", "name": "Nightly STIG", "cron_expr": "0 2 * * *", "enabled": true, "last_run": "...", "last_status": "ok", "run_count": 5 }] }
```

### Create schedule
```
POST /api/schedules
Body: { "name": "Nightly STIG", "playbook": "scan.yml", "cron_expr": "0 2 * * *", "targets": "linux_all", "inventory": "prod", "enabled": true }
→ { "status": "created", "schedule": {...} }
```

### Update schedule
```
PUT /api/schedules/{id}
Body: { same fields as create }
→ { "status": "updated" }
```

### Delete schedule
```
DELETE /api/schedules/{id}
→ { "status": "deleted" }
```

### Run schedule now
```
POST /api/schedules/{id}/run
→ { "success": true, "output": "...", "duration_seconds": 45.2 }
```

### Get schedule logs
```
GET /api/schedules/{id}/logs?count=10
→ { "logs": [{ "started": "...", "finished": "...", "success": true, "output": "...", "duration_seconds": 45.2 }] }
```

---

## Config

### Get ansible.cfg
```
GET /api/cfg
→ { "content": "[defaults]\ninventory = ...", "exists": true }
```

### Update ansible.cfg
```
PUT /api/cfg
Body: { "content": "[defaults]\n..." }
→ { "status": "ok" }
```

---

## Git

### Status
```
GET /api/git/status
→ { "branch": "Dan1", "dirty_files": [{"status": "M", "path": "roles/..."}], "remote": "git@ssh.dev.azure.com:..." }
```

### Log
```
GET /api/git/log?count=15
→ { "commits": [{ "hash": "a3f7c21", "author": "ansible", "message": "...", "time": "2 hours ago" }] }
```

### Branches
```
GET /api/git/branches
→ { "branches": ["main", "origin/main"] }
```

### Commit
```
POST /api/git/commit
Body: { "message": "Updated STIG role" }
→ { "success": true, "stdout": "..." }
```

### Push
```
POST /api/git/push
→ { "success": true, "stdout": "..." }
```

### Pull
```
POST /api/git/pull
→ { "success": true, "stdout": "Already up to date." }
```

### Checkout branch
```
POST /api/git/checkout
Body: { "branch": "main" }
→ { "success": true }
```

---

## Vault

### Find encrypted files
```
GET /api/vault/files
→ { "vault_files": ["inventories/prod/group_vars/all/vault.yml"] }
```

### Encrypt file
```
POST /api/vault/encrypt
Body: { "content": "secret_password: hunter2", "path": "inventories/prod/group_vars/all/vault.yml" }
→ { "success": true }
```

### Decrypt file
```
POST /api/vault/decrypt/{path}
→ { "success": true, "content": "secret_password: hunter2" }
```

---

## Utility

### Health check (no auth required)
```
GET /api/health
→ { "status": "ok", "repo": "/repo", "saml": true }
```

### Repo tree
```
GET /api/tree
→ { "tree": { "inventories": { "type": "dir", "children": [...] }, ... } }
```

### List scripts
```
GET /api/scripts
→ { "scripts": [{ "name": "validate_inventory.sh", "executable": true, "size": 1234 }] }
```

### Current user
```
GET /api/auth/me
→ { "email": "user@example.com", "name": "Your Name", "groups": [...] }
```
