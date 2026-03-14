# API Reference

The web GUI exposes a REST API. All endpoints are relative to the base URL (e.g. `http://localhost:8420`).

Authentication applies to all endpoints — Basic Auth credentials or SAML session cookie depending on your configuration.

Full interactive docs available at `/docs` (FastAPI Swagger UI) when the server is running.

---

## Inventory

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/inventory/hosts` | List all hosts and groups |
| `GET` | `/inventory/raw` | Get raw hosts.yml content |
| `PUT` | `/inventory/raw` | Write raw hosts.yml content |
| `POST` | `/inventory/hosts` | Add a host |
| `DELETE` | `/inventory/hosts/{host}` | Remove a host |
| `GET` | `/inventory/group-vars/{group}` | Get group_vars for a group |
| `PUT` | `/inventory/group-vars/{group}` | Write group_vars for a group |
| `GET` | `/inventory/host-vars/{host}` | Get host_vars for a host |
| `PUT` | `/inventory/host-vars/{host}` | Write host_vars for a host |

---

## Roles

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/roles` | List available roles |
| `GET` | `/roles/{role}/defaults` | Get role defaults (defaults/main.yml) |

---

## Playbooks

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/playbooks` | List available playbooks |
| `GET` | `/playbooks/{playbook}` | Get playbook content |
| `PUT` | `/playbooks/{playbook}` | Write playbook content |

---

## Execution

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/run` | Run a playbook |
| `WebSocket` | `/ws/terminal` | Interactive terminal session |

**POST /run request body:**
```json
{
  "playbook": "playbooks/my-run.yml",
  "limit": "webservers",
  "check": false,
  "extra_vars": {}
}
```

---

## Schedules

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/schedules` | List all schedules |
| `POST` | `/schedules` | Create a schedule |
| `PUT` | `/schedules/{id}` | Update a schedule |
| `DELETE` | `/schedules/{id}` | Delete a schedule |
| `GET` | `/schedules/{id}/logs` | Get run history for a schedule |

**POST /schedules request body:**
```json
{
  "playbook": "playbooks/my-run.yml",
  "cron": "0 2 * * *",
  "limit": "webservers",
  "enabled": true
}
```

---

## Configuration

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/config` | Get ansible.cfg content |
| `PUT` | `/config` | Write ansible.cfg content |

---

## Git

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/git/status` | Current branch, modified files, remote |
| `POST` | `/git/commit` | Commit staged changes |
| `POST` | `/git/push` | Push to remote |
| `POST` | `/git/pull` | Pull with rebase |
| `GET` | `/git/log` | Last 15 commits |
| `GET` | `/git/branches` | List branches |
| `POST` | `/git/checkout` | Switch branch |

**POST /git/commit request body:**
```json
{
  "message": "Update inventory for webservers"
}
```

---

## Vault

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/vault/encrypt` | Encrypt a plaintext value |
| `POST` | `/vault/decrypt` | Decrypt a vault-encrypted file |
| `GET` | `/vault/files` | Find encrypted files in the repo |

---

## Utility

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/environments` | List available inventory environments |
| `POST` | `/environments` | Switch active environment |
| `GET` | `/health` | Health check |

---

## Auth

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/saml/login` | Initiate SAML login flow |
| `POST` | `/saml/acs` | SAML assertion consumer service |
| `GET` | `/saml/metadata` | SP metadata XML |
| `GET` | `/logout` | Invalidate session |
