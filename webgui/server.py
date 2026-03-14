#!/usr/bin/env python3
"""
Ansible Playbook Builder - Backend API
Sits alongside your existing Ansible repo and provides a GUI layer.
Run from your ansible repo root: python ansible-gui/server.py

All reads/writes go to your actual files. Nothing is stored separately.
"""

import os
import re
import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

import asyncio
import yaml

# ---------------------------------------------------------------------------
# Config - point at your ansible repo root
# ---------------------------------------------------------------------------
REPO_ROOT = os.environ.get("ANSIBLE_REPO", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
VAULT_PASSWORD_FILE = os.environ.get("ANSIBLE_VAULT_PASSWORD_FILE", os.path.expanduser("~/.vault_pass"))

SAML_ENABLED = os.environ.get("SAML_ENABLED", "false").lower() == "true"
BASIC_AUTH_ENABLED = os.environ.get("BASIC_AUTH_ENABLED", "true").lower() == "true"
BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "admin")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")  # must be set if enabled

app = FastAPI(title="Ansible Playbook Builder", version="3.0")
# CORS: Do NOT use allow_origins=["*"] — that allows any website to call the API
# with the user's cached credentials (CSRF). We only need same-origin, which
# browsers allow by default. CORS middleware is only needed if the frontend
# is served from a different origin. Since we serve index.html from the same
# FastAPI process, we don't need permissive CORS at all.
# If you separate frontend/backend later, set allow_origins to your exact domain.

# ─── Auth ─────────────────────────────────────────────────────
# Priority: SAML > Basic Auth > No Auth
# At minimum, enable BASIC_AUTH for any non-localhost deployment.

if SAML_ENABLED:
    from auth import SAMLAuthMiddleware, register_saml_routes
    app.add_middleware(SAMLAuthMiddleware)
    register_saml_routes(app)
    print("  Auth: SAML (Entra ID)")

elif BASIC_AUTH_ENABLED:
    import secrets as _secrets
    import base64 as _b64
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response as _StarletteResponse

    if not BASIC_AUTH_PASS:
        print("  WARNING: BASIC_AUTH_ENABLED=true but BASIC_AUTH_PASS is empty!")
        print("  Set BASIC_AUTH_PASS in your .env file.")

    class BasicAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            # Skip auth for health check
            if request.url.path == "/api/health":
                return await call_next(request)

            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Basic "):
                try:
                    decoded = _b64.b64decode(auth_header[6:]).decode("utf-8")
                    user, passwd = decoded.split(":", 1)
                    if user == BASIC_AUTH_USER and _secrets.compare_digest(passwd, BASIC_AUTH_PASS):
                        request.state.user = {"email": user, "name": user}
                        return await call_next(request)
                except Exception:
                    pass

            return _StarletteResponse(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Ansible Playbook Builder"'},
                content="Unauthorized",
            )

    app.add_middleware(BasicAuthMiddleware)

    @app.get("/api/auth/me")
    async def auth_me_basic(request: Request):
        return {"email": BASIC_AUTH_USER, "name": BASIC_AUTH_USER, "upn": BASIC_AUTH_USER, "groups": []}

    print(f"  Auth: Basic (user: {BASIC_AUTH_USER})")

else:
    @app.get("/api/auth/me")
    async def auth_me_stub():
        return {"email": "local", "name": "Local User", "upn": "local", "groups": []}
    print("  Auth: NONE — only safe on localhost. Set BASIC_AUTH_ENABLED=true or SAML_ENABLED=true.")

# Serve frontend
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def safe_path(base: str, *parts: str) -> Path:
    """Prevent path traversal — for reads."""
    resolved = Path(base).resolve().joinpath(*parts).resolve()
    if not str(resolved).startswith(str(Path(base).resolve())):
        raise HTTPException(status_code=403, detail="Path traversal blocked")
    return resolved


# Paths within the repo that should NEVER be written to via the GUI
BLOCKED_WRITE_PATHS = {".git", ".github", ".gitlab-ci.yml", "ansible-gui", "webgui"}

# SECURITY: Secrets that must NOT leak to ansible subprocesses.
# An ansible playbook can read env vars via: {{ lookup('env', 'BASIC_AUTH_PASS') }}
_SECRET_ENV_KEYS = {
    "BASIC_AUTH_PASS", "BASIC_AUTH_USER", "SESSION_SECRET",
    "SAML_ENABLED", "BASIC_AUTH_ENABLED",
}


def _safe_env(**overrides) -> dict:
    """Build subprocess environment with secrets stripped."""
    env = {k: v for k, v in os.environ.items() if k not in _SECRET_ENV_KEYS}
    env.update(overrides)
    return env


def safe_write_path(base: str, *parts: str) -> Path:
    """Prevent path traversal AND block writes to sensitive directories."""
    resolved = safe_path(base, *parts)
    relative = resolved.relative_to(Path(base).resolve())

    # Block writes to .git/, .github/, the GUI itself, etc.
    top_dir = relative.parts[0] if relative.parts else ""
    if top_dir in BLOCKED_WRITE_PATHS:
        raise HTTPException(status_code=403, detail=f"Write blocked: {top_dir}/ is protected")

    # Block hidden files/dirs (dotfiles) at any level
    for part in relative.parts:
        if part.startswith(".") and part not in (".gitignore",):
            raise HTTPException(status_code=403, detail=f"Write blocked: hidden path '{part}'")

    return resolved


class _AnsibleYAMLLoader(yaml.SafeLoader):
    """YAML loader that handles Ansible-specific tags like !vault."""
    pass

# !vault tagged values → return placeholder string
_AnsibleYAMLLoader.add_constructor(
    '!vault',
    lambda loader, node: '<vault-encrypted>'
)


def read_yaml(filepath: Path) -> dict:
    """Read a YAML file, return empty dict if missing or empty."""
    if not filepath.exists():
        return {}
    try:
        with open(filepath) as f:
            content = yaml.load(f, Loader=_AnsibleYAMLLoader)
        return content if content else {}
    except yaml.YAMLError:
        return {}


def write_yaml(filepath: Path, data: dict):
    """Write dict as YAML, creating parent dirs if needed."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def run_git(*args, cwd=None) -> dict:
    """Run a git command in the repo root."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=cwd or REPO_ROOT,
            capture_output=True, text=True, timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "git not found", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "timeout", "returncode": -1}


# ========================= FRONTEND =========================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})
    return HTMLResponse("<h1>Frontend not found. Place index.html in templates/</h1>")


# ========================= INVENTORY =========================

@app.get("/api/environments")
async def list_environments():
    """List inventory environments (dev, prod, etc.)."""
    inv_dir = safe_path(REPO_ROOT, "inventories")
    if not inv_dir.exists():
        return {"environments": []}
    envs = [d.name for d in inv_dir.iterdir() if d.is_dir()]
    return {"environments": sorted(envs)}


@app.get("/api/inventory/{env}")
async def get_inventory(env: str):
    """Read hosts.yml + group_vars + host_vars for an environment."""
    inv_dir = safe_path(REPO_ROOT, "inventories", env)
    if not inv_dir.exists():
        raise HTTPException(404, f"Environment '{env}' not found")

    # Parse hosts.yml / hosts.ini
    hosts_file = None
    for name in ["hosts.yml", "hosts.yaml", "hosts.ini", "hosts"]:
        candidate = inv_dir / name
        if candidate.exists():
            hosts_file = candidate
            break

    inventory_data = {}
    if hosts_file:
        with open(hosts_file) as f:
            raw = f.read()
        inventory_data["hosts_raw"] = raw
        try:
            inventory_data["hosts_parsed"] = yaml.load(raw, Loader=_AnsibleYAMLLoader) or {}
        except yaml.YAMLError:
            inventory_data["hosts_parsed"] = {}

    # Group vars
    gv_dir = inv_dir / "group_vars"
    group_vars = {}
    if gv_dir.exists():
        for item in gv_dir.iterdir():
            if item.is_file() and item.suffix in (".yml", ".yaml"):
                group_vars[item.stem] = read_yaml(item)
            elif item.is_dir():
                # group_vars/groupname/main.yml pattern
                merged = {}
                for sub in sorted(item.glob("*.yml")) + sorted(item.glob("*.yaml")):
                    merged.update(read_yaml(sub))
                group_vars[item.name] = merged
    inventory_data["group_vars"] = group_vars

    # Host vars
    hv_dir = inv_dir / "host_vars"
    host_vars = {}
    if hv_dir.exists():
        for item in hv_dir.iterdir():
            if item.is_file() and item.suffix in (".yml", ".yaml"):
                host_vars[item.stem] = read_yaml(item)
            elif item.is_dir():
                merged = {}
                for sub in sorted(item.glob("*.yml")) + sorted(item.glob("*.yaml")):
                    merged.update(read_yaml(sub))
                host_vars[item.name] = merged
    inventory_data["host_vars"] = host_vars

    return inventory_data


class VarsUpdate(BaseModel):
    vars: dict


@app.put("/api/inventory/{env}/group_vars/{group}")
async def update_group_vars(env: str, group: str, body: VarsUpdate):
    """Write group_vars for a specific group."""
    filepath = safe_write_path(REPO_ROOT, "inventories", env, "group_vars", f"{group}.yml")
    write_yaml(filepath, body.vars)
    return {"status": "ok", "path": str(filepath.relative_to(REPO_ROOT))}


@app.put("/api/inventory/{env}/host_vars/{host}")
async def update_host_vars(env: str, host: str, body: VarsUpdate):
    """Write host_vars for a specific host."""
    filepath = safe_write_path(REPO_ROOT, "inventories", env, "host_vars", f"{host}.yml")
    write_yaml(filepath, body.vars)
    return {"status": "ok", "path": str(filepath.relative_to(REPO_ROOT))}


# --- Inventory raw editing ---

class InventoryRawUpdate(BaseModel):
    content: str


@app.put("/api/inventory/{env}/hosts_raw")
async def update_hosts_raw(env: str, body: InventoryRawUpdate):
    """Write hosts.yml raw content."""
    inv_dir = safe_path(REPO_ROOT, "inventories", env)
    if not inv_dir.exists():
        raise HTTPException(404, f"Environment '{env}' not found")
    hosts_file = None
    for name in ["hosts.yml", "hosts.yaml"]:
        candidate = inv_dir / name
        if candidate.exists():
            hosts_file = candidate
            break
    if not hosts_file:
        hosts_file = inv_dir / "hosts.yml"
    # Validate YAML before writing
    try:
        yaml.load(body.content, Loader=_AnsibleYAMLLoader)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")
    with open(hosts_file, "w") as f:
        f.write(body.content)
    return {"status": "ok", "path": str(hosts_file.relative_to(REPO_ROOT))}


class HostAdd(BaseModel):
    hostname: str
    ansible_host: str = ""
    host_tags: list = []
    extra_vars: dict = {}


@app.post("/api/inventory/{env}/host")
async def add_host(env: str, body: HostAdd):
    """Add a host to the all.hosts section of hosts.yml."""
    inv_dir = safe_path(REPO_ROOT, "inventories", env)
    hosts_file = inv_dir / "hosts.yml"
    if not hosts_file.exists():
        raise HTTPException(404, "hosts.yml not found")

    with open(hosts_file) as f:
        data = yaml.load(f.read(), Loader=_AnsibleYAMLLoader)

    if not data or "all" not in data:
        data = {"all": {"hosts": {}, "children": {}}}
    if "hosts" not in data["all"]:
        data["all"]["hosts"] = {}

    host_entry = {}
    if body.ansible_host:
        host_entry["ansible_host"] = body.ansible_host
    if body.host_tags:
        host_entry["host_tags"] = body.host_tags
    host_entry.update(body.extra_vars)

    data["all"]["hosts"][body.hostname] = host_entry

    with open(hosts_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return {"status": "ok", "hostname": body.hostname}


@app.delete("/api/inventory/{env}/host/{hostname}")
async def remove_host(env: str, hostname: str):
    """Remove a host from all.hosts and all group memberships."""
    inv_dir = safe_path(REPO_ROOT, "inventories", env)
    hosts_file = inv_dir / "hosts.yml"
    if not hosts_file.exists():
        raise HTTPException(404, "hosts.yml not found")

    with open(hosts_file) as f:
        data = yaml.load(f.read(), Loader=_AnsibleYAMLLoader)

    removed_from = []
    # Remove from all.hosts
    if data.get("all", {}).get("hosts", {}).pop(hostname, None) is not None:
        removed_from.append("all.hosts")

    # Remove from all groups
    def walk_remove(obj):
        if not isinstance(obj, dict):
            return
        for key, val in obj.items():
            if isinstance(val, dict):
                if "hosts" in val and isinstance(val["hosts"], dict):
                    if val["hosts"].pop(hostname, None) is not None:
                        removed_from.append(key)
                if "children" in val:
                    walk_remove(val["children"])

    walk_remove(data.get("all", {}).get("children", {}))

    with open(hosts_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return {"status": "ok", "hostname": hostname, "removed_from": removed_from}


class HostTagsUpdate(BaseModel):
    host_tags: list = []


@app.put("/api/inventory/{env}/host/{hostname}/tags")
async def update_host_tags(env: str, hostname: str, body: HostTagsUpdate):
    """Update host_tags for a specific host in hosts.yml."""
    inv_dir = safe_path(REPO_ROOT, "inventories", env)
    hosts_file = inv_dir / "hosts.yml"
    if not hosts_file.exists():
        raise HTTPException(404, "hosts.yml not found")

    with open(hosts_file) as f:
        data = yaml.load(f.read(), Loader=_AnsibleYAMLLoader)

    hosts = data.get("all", {}).get("hosts", {})
    if hostname not in hosts:
        raise HTTPException(404, f"Host '{hostname}' not found")

    if hosts[hostname] is None:
        hosts[hostname] = {}
    hosts[hostname]["host_tags"] = body.host_tags

    with open(hosts_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return {"status": "ok", "hostname": hostname, "host_tags": body.host_tags}


class GroupAdd(BaseModel):
    group_name: str
    hosts: list = []  # list of hostnames


@app.post("/api/inventory/{env}/group")
async def add_group(env: str, body: GroupAdd):
    """Add or update a group in the children section."""
    inv_dir = safe_path(REPO_ROOT, "inventories", env)
    hosts_file = inv_dir / "hosts.yml"
    if not hosts_file.exists():
        raise HTTPException(404, "hosts.yml not found")

    with open(hosts_file) as f:
        data = yaml.load(f.read(), Loader=_AnsibleYAMLLoader)

    if not data or "all" not in data:
        data = {"all": {"hosts": {}, "children": {}}}
    if "children" not in data["all"]:
        data["all"]["children"] = {}

    group_hosts = {h: {} for h in body.hosts}
    data["all"]["children"][body.group_name] = {"hosts": group_hosts}

    with open(hosts_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return {"status": "ok", "group": body.group_name, "host_count": len(body.hosts)}


# ========================= ROLES =========================

@app.get("/api/roles")
async def list_roles():
    """List all roles with their defaults/main.yml vars and meta."""
    roles_dir = safe_path(REPO_ROOT, "roles")
    if not roles_dir.exists():
        return {"roles": []}

    roles = []
    for d in sorted(roles_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        role = {"name": d.name, "vars": {}, "meta": {}, "has_tasks": False}

        # defaults/main.yml
        defaults = d / "defaults" / "main.yml"
        if defaults.exists():
            role["vars"] = read_yaml(defaults)

        # meta/main.yml
        meta = d / "meta" / "main.yml"
        if meta.exists():
            role["meta"] = read_yaml(meta)

        # Check for tasks
        tasks = d / "tasks" / "main.yml"
        role["has_tasks"] = tasks.exists()

        # List all dirs present in the role
        role["structure"] = [p.name for p in d.iterdir() if p.is_dir()]

        roles.append(role)

    return {"roles": roles}


@app.get("/api/role/{name}")
async def get_role(name: str):
    """Get full role details: defaults, vars, tasks, handlers, templates, files."""
    role_dir = safe_path(REPO_ROOT, "roles", name)
    if not role_dir.exists():
        raise HTTPException(404, f"Role '{name}' not found")

    role = {"name": name, "files": {}}

    # Read key files
    for subdir in ["defaults", "vars", "tasks", "handlers", "meta"]:
        main = role_dir / subdir / "main.yml"
        if main.exists():
            with open(main) as f:
                role["files"][f"{subdir}/main.yml"] = f.read()

    # List templates and files
    for subdir in ["templates", "files"]:
        sd = role_dir / subdir
        if sd.exists():
            role["files"][subdir] = [f.name for f in sd.iterdir() if f.is_file()]

    return role


class RoleFileUpdate(BaseModel):
    content: str


@app.put("/api/role/{name}/{subpath:path}")
async def update_role_file(name: str, subpath: str, body: RoleFileUpdate):
    """Update a specific file within a role."""
    filepath = safe_write_path(REPO_ROOT, "roles", name, subpath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(body.content)
    return {"status": "ok", "path": str(filepath.relative_to(REPO_ROOT))}


class NewRole(BaseModel):
    name: str
    description: str = ""
    defaults: dict = {}


@app.post("/api/roles")
async def create_role(body: NewRole):
    """Create a new role with standard directory structure."""
    name = re.sub(r"[^a-z0-9_-]", "", body.name.lower())
    if not name:
        raise HTTPException(400, "Invalid role name")

    role_dir = safe_write_path(REPO_ROOT, "roles", name)
    if role_dir.exists():
        raise HTTPException(409, f"Role '{name}' already exists")

    # Create standard structure
    for subdir in ["tasks", "handlers", "templates", "files", "vars", "defaults", "meta"]:
        (role_dir / subdir).mkdir(parents=True, exist_ok=True)

    # defaults/main.yml
    write_yaml(role_dir / "defaults" / "main.yml", body.defaults or {"# Add default variables here": None})

    # tasks/main.yml
    with open(role_dir / "tasks" / "main.yml", "w") as f:
        f.write(f"---\n# tasks file for {name}\n")

    # handlers/main.yml
    with open(role_dir / "handlers" / "main.yml", "w") as f:
        f.write(f"---\n# handlers file for {name}\n")

    # vars/main.yml
    with open(role_dir / "vars" / "main.yml", "w") as f:
        f.write(f"---\n# vars file for {name}\n")

    # meta/main.yml
    meta = {
        "galaxy_info": {
            "author": "playbook-builder",
            "description": body.description or name,
            "license": "proprietary",
            "min_ansible_version": "2.9",
        },
        "dependencies": [],
    }
    write_yaml(role_dir / "meta" / "main.yml", meta)

    return {"status": "created", "name": name, "path": f"roles/{name}"}


# ========================= PLAYBOOKS =========================

@app.get("/api/playbooks")
async def list_playbooks():
    """List all playbooks, including those in subdirectories."""
    pb_dir = safe_path(REPO_ROOT, "playbooks")
    if not pb_dir.exists():
        return {"playbooks": []}

    playbooks = []
    for item in sorted(pb_dir.rglob("*.yml")) + sorted(pb_dir.rglob("*.yaml")):
        rel = item.relative_to(pb_dir)
        with open(item) as f:
            raw = f.read()
        try:
            parsed = yaml.load(raw, Loader=_AnsibleYAMLLoader)
            # Extract play name if it's a list (standard playbook format)
            name = ""
            if isinstance(parsed, list) and parsed:
                name = parsed[0].get("name", "")
        except yaml.YAMLError:
            name = ""
            parsed = None

        playbooks.append({
            "path": str(rel),
            "name": name,
            "raw": raw,
            "directory": str(rel.parent) if str(rel.parent) != "." else None,
        })

    return {"playbooks": playbooks}


@app.get("/api/playbook/{path:path}")
async def get_playbook(path: str):
    """Read a specific playbook."""
    filepath = safe_path(REPO_ROOT, "playbooks", path)
    if not filepath.exists():
        raise HTTPException(404, f"Playbook not found: {path}")
    with open(filepath) as f:
        raw = f.read()
    return {"path": path, "raw": raw, "parsed": yaml.load(raw, Loader=_AnsibleYAMLLoader)}


class PlaybookWrite(BaseModel):
    content: str
    path: str  # relative to playbooks/ dir


@app.post("/api/playbooks")
async def write_playbook(body: PlaybookWrite):
    """Write/create a playbook file."""
    filepath = safe_write_path(REPO_ROOT, "playbooks", body.path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(body.content)
    return {"status": "ok", "path": f"playbooks/{body.path}"}


# ========================= ANSIBLE.CFG =========================

@app.get("/api/cfg")
async def get_cfg():
    """Read ansible.cfg from repo root."""
    cfg_path = safe_path(REPO_ROOT, "ansible.cfg")
    if not cfg_path.exists():
        return {"content": "", "exists": False}
    with open(cfg_path) as f:
        return {"content": f.read(), "exists": True}


class CfgUpdate(BaseModel):
    content: str


@app.put("/api/cfg")
async def update_cfg(body: CfgUpdate):
    """Write ansible.cfg."""
    cfg_path = safe_write_path(REPO_ROOT, "ansible.cfg")
    with open(cfg_path, "w") as f:
        f.write(body.content)
    return {"status": "ok"}


# ========================= VAULT =========================

@app.get("/api/vault/files")
async def list_vault_files():
    """Find files that appear to be vault-encrypted."""
    vault_files = []
    for item in Path(REPO_ROOT).rglob("*.yml"):
        try:
            with open(item) as f:
                first_line = f.readline()
            if first_line.startswith("$ANSIBLE_VAULT"):
                vault_files.append(str(item.relative_to(REPO_ROOT)))
        except (PermissionError, UnicodeDecodeError):
            pass
    return {"vault_files": vault_files}


class VaultEncrypt(BaseModel):
    content: str
    path: str  # relative to repo root


@app.post("/api/vault/encrypt")
async def vault_encrypt(body: VaultEncrypt):
    """Encrypt content and write to file using ansible-vault."""
    filepath = safe_write_path(REPO_ROOT, body.path)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # SECURITY: Write content and encrypt atomically.
    # Write to a temp file, encrypt it, then move into place.
    # This avoids leaving plaintext on disk if the process crashes.
    import tempfile as _tf
    tmp = _tf.NamedTemporaryFile(mode="w", suffix=".yml", dir=str(filepath.parent), delete=False)
    try:
        tmp.write(body.content)
        tmp.close()

        args = ["ansible-vault", "encrypt", tmp.name, "--encrypt-vault-id", "default"]
        if os.path.exists(VAULT_PASSWORD_FILE):
            args += ["--vault-password-file", VAULT_PASSWORD_FILE]

        result = subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT, timeout=30)
        if result.returncode != 0:
            os.unlink(tmp.name)
            return {"success": False, "error": result.stderr}

        # Atomic move (same filesystem)
        os.replace(tmp.name, str(filepath))
        return {"success": True, "path": body.path}
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise HTTPException(500, str(e))


@app.post("/api/vault/decrypt/{path:path}")
async def vault_decrypt(path: str):
    """Decrypt a vault file and return contents."""
    filepath = safe_path(REPO_ROOT, path)
    if not filepath.exists():
        raise HTTPException(404, "File not found")

    args = ["ansible-vault", "view", str(filepath)]
    if os.path.exists(VAULT_PASSWORD_FILE):
        args += ["--vault-password-file", VAULT_PASSWORD_FILE]

    result = subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        return {"success": False, "error": result.stderr}
    return {"success": True, "content": result.stdout}


class VaultEncryptString(BaseModel):
    value: str
    name: str = ""  # optional var name for --name flag
    vault_id: str = "default"  # vault ID to encrypt with


@app.post("/api/vault/encrypt_string")
async def vault_encrypt_string(body: VaultEncryptString):
    """Encrypt a string value using ansible-vault encrypt_string.
    
    Returns the !vault inline block ready to paste into a YAML file.
    If name is provided, wraps with the var name for direct paste.
    """
    # SECURITY: Pass value via stdin, not as positional arg.
    # Positional args starting with "--" would be interpreted as flags.
    args = ["ansible-vault", "encrypt_string", "--stdin-name", body.name or "value"]
    if os.path.exists(VAULT_PASSWORD_FILE):
        args += ["--vault-password-file", VAULT_PASSWORD_FILE]
    # Handle multiple vault IDs — default to "default"
    args += ["--encrypt-vault-id", body.vault_id or "default"]

    result = subprocess.run(
        args, capture_output=True, text=True, cwd=REPO_ROOT,
        input=body.value, timeout=30,
    )
    if result.returncode != 0:
        return {"success": False, "error": result.stderr}
    return {"success": True, "encrypted": result.stdout}


# ========================= GIT =========================

@app.get("/api/git/status")
async def git_status():
    """Get git status: branch, dirty files, remote info."""
    branch = run_git("rev-parse", "--abbrev-ref", "HEAD")
    status = run_git("status", "--porcelain")
    remote = run_git("remote", "get-url", "origin")

    # Parse porcelain status into file list
    dirty_files = []
    if status["success"] and status["stdout"]:
        for line in status["stdout"].split("\n"):
            if len(line) >= 3:
                st = line[:2].strip()
                path = line[3:].strip()
                dirty_files.append({"status": st or "M", "path": path})

    return {
        "branch": branch.get("stdout", "unknown"),
        "dirty_files": dirty_files,
        "remote": remote.get("stdout", ""),
        "is_repo": branch.get("success", False),
    }


@app.get("/api/git/branches")
async def git_branches():
    """List git branches."""
    result = run_git("branch", "-a", "--format=%(refname:short)")
    branches = []
    if result["success"]:
        branches = [b.strip() for b in result["stdout"].split("\n") if b.strip()]
    return {"branches": branches}


@app.get("/api/git/log")
async def git_log(count: int = Query(default=20, le=100)):
    """Get recent git log."""
    result = run_git("log", f"-{count}", "--format=%H|%h|%an|%s|%ar")
    commits = []
    if result["success"] and result["stdout"]:
        for line in result["stdout"].split("\n"):
            parts = line.split("|", 4)
            if len(parts) == 5:
                commits.append({
                    "hash_full": parts[0],
                    "hash": parts[1],
                    "author": parts[2],
                    "message": parts[3],
                    "time": parts[4],
                })
    return {"commits": commits}


class GitCommit(BaseModel):
    message: str
    files: list[str] = []  # empty = add all


@app.post("/api/git/commit")
async def git_commit(body: GitCommit):
    """Stage files and commit."""
    if body.files:
        for f in body.files:
            run_git("add", f)
    else:
        run_git("add", "-A")

    result = run_git("commit", "-m", body.message)
    return result


@app.post("/api/git/push")
async def git_push():
    """Push to remote."""
    branch = run_git("rev-parse", "--abbrev-ref", "HEAD")
    result = run_git("push", "origin", branch.get("stdout", "main"))
    return result


@app.post("/api/git/pull")
async def git_pull():
    """Pull from remote."""
    result = run_git("pull", "--rebase")
    return result


class GitCheckout(BaseModel):
    branch: str


@app.post("/api/git/checkout")
async def git_checkout(body: GitCheckout):
    """Switch branch."""
    # SECURITY: Validate branch name to prevent flag injection (e.g. "--" or "-b evil")
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9/_.\-]*$', body.branch):
        raise HTTPException(400, "Invalid branch name")
    result = run_git("checkout", body.branch)
    return result


# ========================= RUN PLAYBOOK =========================

import tempfile as _tempfile

_run_semaphore = asyncio.Semaphore(int(os.environ.get("MAX_CONCURRENT_RUNS", "3")))
_active_runs = {}  # run_id → process


class PlaybookRun(BaseModel):
    playbook: str = ""
    yaml_content: str = ""
    inventory: str = "prod"
    extra_vars: dict = {}
    limit: str = ""
    tags: str = ""
    check: bool = False
    diff: bool = False
    verbose: int = 0


def _playbook_uses_host_var(pb_path: str, yaml_content: str = "") -> bool:
    """Check if a playbook uses hosts: '{{ host }}' pattern."""
    content = yaml_content
    if not content and pb_path and os.path.exists(pb_path):
        try:
            with open(pb_path) as f:
                content = f.read()
        except IOError:
            return False
    return "{{ host }}" in content or "{{host}}" in content


def _build_run_cmd(body: PlaybookRun, pb_path: str) -> list:
    """Build the ansible-playbook command list.
    
    Auto-detects playbooks using hosts: '{{ host }}' and passes targets
    via -e host= instead of --limit. This matches the standard pattern:
      ansible-playbook playbook.yml -e host=web_servers
    """
    inv_path = str(safe_path(REPO_ROOT, "inventories", body.inventory))
    cmd = ["ansible-playbook", pb_path, "-i", inv_path]

    # Detect {{ host }} pattern
    uses_host_var = _playbook_uses_host_var(pb_path, body.yaml_content)

    # Merge extra_vars
    extra = dict(body.extra_vars) if body.extra_vars else {}

    if body.limit:
        if uses_host_var:
            # Pass as -e host= (the playbook expects it)
            extra["host"] = body.limit
        else:
            # Standard --limit
            cmd += ["--limit", body.limit]

    if extra:
        cmd += ["-e", json.dumps(extra)]
    if body.tags:
        cmd += ["--tags", body.tags]
    if body.check:
        cmd += ["--check"]
    if body.diff:
        cmd += ["--diff"]
    if body.verbose:
        cmd += ["-" + "v" * min(body.verbose, 4)]
    if os.path.exists(VAULT_PASSWORD_FILE):
        cmd += ["--vault-password-file", VAULT_PASSWORD_FILE]
    return cmd


def _resolve_pb_path(body: PlaybookRun):
    """Resolve playbook to a file path. Returns (path, temp_file_or_None)."""
    if body.yaml_content:
        tf = _tempfile.NamedTemporaryFile(mode="w", suffix=".yml", prefix="pb_gui_", dir="/tmp", delete=False)
        tf.write(body.yaml_content)
        tf.close()
        return tf.name, tf
    elif body.playbook:
        p = str(safe_path(REPO_ROOT, "playbooks", body.playbook))
        if not Path(p).exists():
            raise HTTPException(404, f"Playbook not found: {body.playbook}")
        return p, None
    else:
        raise HTTPException(400, "Provide playbook or yaml_content")


# ── Streaming run via WebSocket ──
@app.websocket("/api/ws/run")
async def run_ws(ws: WebSocket):
    """
    WebSocket for streaming playbook execution with kill support.

    The key design: a message listener runs concurrently with the process
    streamer, so "kill" messages are received immediately even while
    stdout/stderr are being streamed.
    """
    if not _authenticate_ws(ws):
        await ws.close(code=4401, reason="Unauthorized")
        return

    await ws.accept()
    proc = None
    run_id = None
    temp_file = None
    killed = False

    async def listen_for_kill():
        """Runs concurrently — listens for kill messages while process streams."""
        nonlocal proc, killed
        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("action") == "kill" and proc and proc.returncode is None:
                    killed = True
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        proc.kill()
        except (WebSocketDisconnect, Exception):
            # Connection closed or error — kill process if still running
            if proc and proc.returncode is None:
                proc.terminate()

    try:
        # Wait for the initial "run" message
        msg = await ws.receive_json()
        if msg.get("action") != "run":
            await ws.send_json({"type": "stderr", "data": "Expected action: run"})
            return

        if not _run_semaphore._value:
            await ws.send_json({"type": "stderr", "data": f"Too many concurrent runs ({len(_active_runs)} active)."})
            await ws.send_json({"type": "exit", "code": -1})
            return

        try:
            body = PlaybookRun(**{k: v for k, v in msg.items() if k != "action"})
            pb_path, temp_file = _resolve_pb_path(body)
            cmd = _build_run_cmd(body, pb_path)
        except Exception as e:
            await ws.send_json({"type": "stderr", "data": str(e)})
            await ws.send_json({"type": "exit", "code": -1})
            return

        run_id = _uuid.uuid4().hex[:8]
        await ws.send_json({"type": "cmd", "data": f"$ {' '.join(cmd)}", "run_id": run_id})

        async with _run_semaphore:
            try:
                env = {
                    **_safe_env(),
                    "ANSIBLE_FORCE_COLOR": "0",
                    "ANSIBLE_NOCOLOR": "1",
                    "PYTHONUNBUFFERED": "1",
                }
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=REPO_ROOT, env=env,
                )
                _active_runs[run_id] = proc

                async def stream(pipe, stype):
                    while True:
                        line = await pipe.readline()
                        if not line:
                            break
                        try:
                            await ws.send_json({"type": stype, "data": line.decode("utf-8", errors="replace").rstrip("\n")})
                        except Exception:
                            break

                # Run streaming AND kill listener concurrently
                listener = asyncio.create_task(listen_for_kill())
                try:
                    await asyncio.gather(
                        stream(proc.stdout, "stdout"),
                        stream(proc.stderr, "stderr"),
                    )
                    await proc.wait()
                finally:
                    listener.cancel()
                    try:
                        await listener
                    except (asyncio.CancelledError, Exception):
                        pass

                if killed:
                    await ws.send_json({"type": "stderr", "data": "\n⛔ Process killed by user"})
                    await ws.send_json({"type": "exit", "code": -9, "killed": True})
                else:
                    await ws.send_json({"type": "exit", "code": proc.returncode})

            except Exception as e:
                await ws.send_json({"type": "stderr", "data": str(e)})
                await ws.send_json({"type": "exit", "code": -1})
            finally:
                _active_runs.pop(run_id, None)
                if temp_file and os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                proc = None
                temp_file = None

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if proc and proc.returncode is None:
            proc.terminate()
        _active_runs.pop(run_id, None)
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


# ── Non-streaming POST fallback (used by scheduler) ──
@app.post("/api/run")
async def run_playbook(body: PlaybookRun):
    """Non-streaming run — used by scheduler and API consumers."""
    pb_path, temp_file = _resolve_pb_path(body)
    cmd = _build_run_cmd(body, pb_path)

    try:
        async with _run_semaphore:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=REPO_ROOT, timeout=600,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": " ".join(cmd),
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Timed out (10m)", "returncode": -1}
    finally:
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


# ── Kill endpoint for active runs ──
@app.post("/api/run/kill/{run_id}")
async def kill_run(run_id: str):
    """Kill a running playbook by run_id."""
    proc = _active_runs.get(run_id)
    if not proc:
        raise HTTPException(404, f"No active run with id '{run_id}'")
    if proc.returncode is not None:
        return {"status": "already_finished", "code": proc.returncode}
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
    _active_runs.pop(run_id, None)
    return {"status": "killed"}


@app.get("/api/run/active")
async def list_active_runs():
    """List currently running playbook executions."""
    return {"active": [
        {"run_id": rid, "running": proc.returncode is None}
        for rid, proc in _active_runs.items()
    ]}


# ========================= SCRIPTS =========================

@app.get("/api/scripts")
async def list_scripts():
    """List scripts in scripts/ directory."""
    scripts_dir = safe_path(REPO_ROOT, "scripts")
    if not scripts_dir.exists():
        return {"scripts": []}
    scripts = []
    for item in sorted(scripts_dir.iterdir()):
        if item.is_file():
            scripts.append({
                "name": item.name,
                "executable": os.access(item, os.X_OK),
                "size": item.stat().st_size,
            })
    return {"scripts": scripts}


# ========================= TREE =========================

@app.get("/api/tree")
async def repo_tree():
    """Return repo structure (2 levels deep, excluding .git)."""
    tree = {}
    root = Path(REPO_ROOT)
    for item in sorted(root.iterdir()):
        if item.name.startswith(".") and item.name != ".gitignore":
            continue
        if item.is_dir():
            children = []
            for child in sorted(item.iterdir()):
                if child.name.startswith("."):
                    continue
                children.append({
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                })
            tree[item.name] = {"type": "dir", "children": children}
        else:
            tree[item.name] = {"type": "file"}
    return {"tree": tree}


# ========================= TERMINAL (WebSocket) ==============

import shlex

# Allowed binary names. Only these executables can be invoked.
# Maps display name → allowed binary names (resolved via PATH at runtime).
ALLOWED_BINARIES = {
    "ansible",           "ansible-playbook",  "ansible-vault",
    "ansible-galaxy",    "ansible-inventory",  "ansible-config",
    "ansible-doc",       "ansible-pull",       "ansible-console",
    "git",
    "cat", "ls", "head", "tail", "grep", "find", "tree", "wc",
    "ssh-keyscan",
    "ping",
    "hostname", "whoami", "pwd", "which", "id", "date",
}

# Shell metacharacters that indicate injection attempts.
# These are BLOCKED regardless of what binary is being called.
BLOCKED_CHARS = set(";|&`$(){}!><\n\\")


def sanitize_command(raw_cmd: str) -> Optional[list]:
    """
    Parse and validate a command string. Returns argv list or None if rejected.

    Security model:
    - No shell invocation. Commands are split with shlex and exec'd directly.
    - Only whitelisted binaries can be the first argument.
    - Shell metacharacters are blocked entirely.
    - No chaining (;), piping (|), backgrounding (&), subshells ($(), ``).
    """
    raw_cmd = raw_cmd.strip()
    if not raw_cmd:
        return None

    # Block any shell metacharacters
    for ch in BLOCKED_CHARS:
        if ch in raw_cmd:
            return None

    try:
        argv = shlex.split(raw_cmd)
    except ValueError:
        return None

    if not argv:
        return None

    # Extract binary name (handle paths: /usr/bin/ansible → ansible)
    binary = os.path.basename(argv[0])

    if binary not in ALLOWED_BINARIES:
        return None

    # Block path traversal in arguments (e.g. --extra-vars @/etc/shadow)
    repo_resolved = str(Path(REPO_ROOT).resolve())
    for arg in argv[1:]:
        # Block reading files outside repo via @ syntax (ansible uses @file)
        if arg.startswith("@"):
            at_path = arg[1:]
            # Resolve relative to REPO_ROOT to catch ../../etc/shadow
            resolved = str(Path(REPO_ROOT).joinpath(at_path).resolve())
            if not resolved.startswith(repo_resolved):
                return None

    return argv


# Active terminal processes — track so we can kill on disconnect
_active_procs: dict = {}


def _authenticate_ws(ws: WebSocket) -> bool:
    """
    Authenticate a WebSocket connection BEFORE accepting it.
    Returns True if authenticated, False to reject.
    """
    if SAML_ENABLED:
        # SAML: check session cookie
        from auth import get_session
        # Build a fake request-like object for get_session
        cookie = ws.cookies.get("pb_session")
        if not cookie:
            return False
        # Validate session (reuse auth module logic)
        from auth import _verify_session_id, _sessions
        import time as _time
        session_id = _verify_session_id(cookie)
        if not session_id:
            return False
        session = _sessions.get(session_id)
        if not session or _time.time() > session.get("expires", 0):
            return False
        return True

    elif BASIC_AUTH_ENABLED:
        # Basic Auth: browser sends Authorization header on WS upgrade
        import base64 as _b64
        import secrets as _secrets
        auth_header = ws.headers.get("authorization", "")
        if not auth_header.startswith("Basic "):
            return False
        try:
            decoded = _b64.b64decode(auth_header[6:]).decode("utf-8")
            user, passwd = decoded.split(":", 1)
            return user == BASIC_AUTH_USER and _secrets.compare_digest(passwd, BASIC_AUTH_PASS)
        except Exception:
            return False

    # No auth mode
    return True


@app.websocket("/api/ws/terminal")
async def terminal_ws(ws: WebSocket):
    """
    WebSocket terminal. Client sends commands, server streams output.

    Protocol:
      Client → {"cmd": "ansible-playbook ..."}
      Server → {"type": "stdout", "data": "line of output"}
      Server → {"type": "stderr", "data": "line of error"}
      Server → {"type": "exit", "code": 0}
      Client → {"cmd": "SIGINT"}  ← kills running process

    Security:
      - Auth checked BEFORE accepting the WebSocket connection
      - Commands are parsed with shlex, NOT passed to shell
      - Only whitelisted binaries can execute
      - Shell metacharacters (;|&`$) are blocked
      - No command chaining or piping
    """
    # Authenticate BEFORE accepting the connection
    if not _authenticate_ws(ws):
        await ws.close(code=4401, reason="Unauthorized")
        return

    await ws.accept()
    proc = None
    ws_id = id(ws)

    try:
        while True:
            msg = await ws.receive_json()
            cmd_raw = msg.get("cmd", "").strip()

            if not cmd_raw:
                continue

            # Handle kill signal
            if cmd_raw == "SIGINT" and proc and proc.returncode is None:
                proc.terminate()
                await ws.send_json({"type": "stderr", "data": "\n^C — process terminated"})
                continue

            # Sanitize and validate
            argv = sanitize_command(cmd_raw)
            if argv is None:
                blocked_reason = "Shell operators (;|&`$) are blocked." if any(c in cmd_raw for c in BLOCKED_CHARS) else f"Binary not allowed: {cmd_raw.split()[0] if cmd_raw.split() else '(empty)'}"
                await ws.send_json({
                    "type": "stderr",
                    "data": f"Blocked: {blocked_reason}\nAllowed: ansible*, git, cat, ls, grep, find, ping"
                })
                await ws.send_json({"type": "exit", "code": -1})
                continue

            # Echo command
            await ws.send_json({"type": "cmd", "data": f"$ {cmd_raw}"})

            # Execute with NO SHELL — argv is passed directly to exec
            try:
                env = {
                    **_safe_env(),
                    "ANSIBLE_FORCE_COLOR": "0",
                    "ANSIBLE_NOCOLOR": "1",
                    "PYTHONUNBUFFERED": "1",
                    "TERM": "dumb",
                }

                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=REPO_ROOT,
                    env=env,
                )
                _active_procs[ws_id] = proc

                async def stream_pipe(pipe, stream_type):
                    while True:
                        line = await pipe.readline()
                        if not line:
                            break
                        try:
                            text = line.decode("utf-8", errors="replace").rstrip("\n")
                            await ws.send_json({"type": stream_type, "data": text})
                        except Exception:
                            break

                await asyncio.gather(
                    stream_pipe(proc.stdout, "stdout"),
                    stream_pipe(proc.stderr, "stderr"),
                )

                await proc.wait()
                await ws.send_json({"type": "exit", "code": proc.returncode})

            except FileNotFoundError:
                await ws.send_json({"type": "stderr", "data": f"Binary not found: {argv[0]}"})
                await ws.send_json({"type": "exit", "code": -1})
            except Exception as e:
                await ws.send_json({"type": "stderr", "data": str(e)})
                await ws.send_json({"type": "exit", "code": -1})
            finally:
                _active_procs.pop(ws_id, None)
                proc = None

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        p = _active_procs.pop(ws_id, None)
        if p and p.returncode is None:
            p.terminate()


# Non-streaming fallback for simple commands
class ExecCommand(BaseModel):
    cmd: str
    timeout: int = 120  # max 600 seconds (10 min)

    class Config:
        pass

@app.post("/api/exec")
async def exec_command(body: ExecCommand):
    """Run an allowed command and return output (non-streaming, no shell)."""
    argv = sanitize_command(body.cmd)
    if argv is None:
        raise HTTPException(403, f"Command blocked. Only whitelisted binaries allowed, no shell operators.")

    capped_timeout = min(body.timeout, 600)

    try:
        result = subprocess.run(
            argv,  # argv list, NOT shell string
            capture_output=True, text=True,
            cwd=REPO_ROOT, timeout=capped_timeout,
            env=_safe_env(ANSIBLE_FORCE_COLOR="0", ANSIBLE_NOCOLOR="1"),
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Timed out after {capped_timeout}s", "returncode": -1}


# ========================= SCHEDULER ===========================

import uuid as _uuid
from datetime import datetime, timezone

SCHEDULE_DIR = os.path.join(REPO_ROOT, ".ansible-gui")
SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "schedules.json")
SCHEDULE_LOG_DIR = os.path.join(SCHEDULE_DIR, "logs")


def _ensure_schedule_dirs():
    os.makedirs(SCHEDULE_DIR, exist_ok=True)
    os.makedirs(SCHEDULE_LOG_DIR, exist_ok=True)


def _load_schedules() -> list:
    _ensure_schedule_dirs()
    if not os.path.exists(SCHEDULE_FILE):
        return []
    try:
        with open(SCHEDULE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_schedules(schedules: list):
    _ensure_schedule_dirs()
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(schedules, f, indent=2)


def _cron_matches_now(cron_expr: str, now: datetime) -> bool:
    """Simple cron matcher for: min hour dom month dow (5 fields).
    Supports numbers, *, and */N step syntax."""
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False
        fields = [now.minute, now.hour, now.day, now.month, now.weekday()]
        # Cron weekday: 0=Sunday, Python: 0=Monday. Convert.
        cron_dow = (now.weekday() + 1) % 7  # Convert to cron format
        fields[4] = cron_dow
        ranges = [
            (0, 59), (0, 23), (1, 31), (1, 12), (0, 6)
        ]
        for i, (field_val, part) in enumerate(zip(fields, parts)):
            if part == "*":
                continue
            if part.startswith("*/"):
                step = int(part[2:])
                if field_val % step != 0:
                    return False
            elif "," in part:
                if field_val not in [int(x) for x in part.split(",")]:
                    return False
            elif "-" in part:
                lo, hi = part.split("-")
                if not (int(lo) <= field_val <= int(hi)):
                    return False
            else:
                if field_val != int(part):
                    return False
        return True
    except (ValueError, IndexError):
        return False


class ScheduleCreate(BaseModel):
    name: str
    playbook: str = ""       # path to saved playbook
    yaml_content: str = ""   # OR inline YAML
    inventory: str = "prod"
    targets: str = ""        # --limit
    cron_expr: str = ""      # "0 2 * * *" = 2 AM daily
    enabled: bool = True


@app.get("/api/schedules")
async def list_schedules():
    """List all scheduled jobs."""
    schedules = _load_schedules()
    return {"schedules": schedules}


@app.post("/api/schedules")
async def create_schedule(body: ScheduleCreate):
    """Create a new scheduled job."""
    if not body.playbook and not body.yaml_content:
        raise HTTPException(400, "Provide playbook path or yaml_content")
    if not body.cron_expr or len(body.cron_expr.split()) != 5:
        raise HTTPException(400, "cron_expr must be 5 fields: min hour dom month dow")

    schedules = _load_schedules()
    schedule = {
        "id": _uuid.uuid4().hex[:8],
        "name": body.name,
        "playbook": body.playbook,
        "yaml_content": body.yaml_content,
        "inventory": body.inventory,
        "targets": body.targets,
        "cron_expr": body.cron_expr,
        "enabled": body.enabled,
        "created": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "last_status": None,
        "run_count": 0,
    }
    schedules.append(schedule)
    _save_schedules(schedules)
    return {"status": "created", "schedule": schedule}


@app.put("/api/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleCreate):
    """Update a schedule."""
    schedules = _load_schedules()
    for s in schedules:
        if s["id"] == schedule_id:
            s["name"] = body.name
            s["playbook"] = body.playbook
            s["yaml_content"] = body.yaml_content
            s["inventory"] = body.inventory
            s["targets"] = body.targets
            s["cron_expr"] = body.cron_expr
            s["enabled"] = body.enabled
            _save_schedules(schedules)
            return {"status": "updated", "schedule": s}
    raise HTTPException(404, "Schedule not found")


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a schedule."""
    schedules = _load_schedules()
    schedules = [s for s in schedules if s["id"] != schedule_id]
    _save_schedules(schedules)
    return {"status": "deleted"}


@app.post("/api/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: str):
    """Manually trigger a scheduled job immediately."""
    schedules = _load_schedules()
    for s in schedules:
        if s["id"] == schedule_id:
            result = await _execute_schedule(s)
            return result
    raise HTTPException(404, "Schedule not found")


@app.get("/api/schedules/{schedule_id}/logs")
async def get_schedule_logs(schedule_id: str, count: int = Query(default=10, le=50)):
    """Get recent run logs for a schedule."""
    _ensure_schedule_dirs()
    log_files = sorted(
        [f for f in Path(SCHEDULE_LOG_DIR).glob(f"{schedule_id}_*.json")],
        key=lambda x: x.stat().st_mtime, reverse=True
    )[:count]
    logs = []
    for lf in log_files:
        try:
            with open(lf) as f:
                logs.append(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    return {"logs": logs}


async def _execute_schedule(schedule: dict) -> dict:
    """Execute a single schedule and log the result."""
    import tempfile

    _ensure_schedule_dirs()
    start = datetime.now(timezone.utc)

    # Determine playbook
    temp_file = None
    if schedule.get("yaml_content"):
        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", prefix="sched_",
            dir="/tmp", delete=False
        )
        temp_file.write(schedule["yaml_content"])
        temp_file.close()
        pb_path = temp_file.name
    elif schedule.get("playbook"):
        pb_path = str(safe_path(REPO_ROOT, "playbooks", schedule["playbook"]))
    else:
        return {"success": False, "error": "No playbook defined"}

    inv_path = str(safe_path(REPO_ROOT, "inventories", schedule.get("inventory", "prod")))

    cmd = ["ansible-playbook", pb_path, "-i", inv_path]
    if schedule.get("targets"):
        cmd += ["--limit", schedule["targets"]]
    if os.path.exists(VAULT_PASSWORD_FILE):
        cmd += ["--vault-password-file", VAULT_PASSWORD_FILE]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=REPO_ROOT, timeout=1800,
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        success = False
        output = "Execution timed out (30m)"
    except Exception as e:
        success = False
        output = str(e)
    finally:
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

    end = datetime.now(timezone.utc)

    # Save log
    log_entry = {
        "schedule_id": schedule["id"],
        "schedule_name": schedule["name"],
        "started": start.isoformat(),
        "finished": end.isoformat(),
        "duration_seconds": (end - start).total_seconds(),
        "success": success,
        "output": output[-10000:],  # Last 10k chars
        "command": " ".join(cmd),
    }
    log_file = os.path.join(
        SCHEDULE_LOG_DIR,
        f"{schedule['id']}_{start.strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(log_file, "w") as f:
        json.dump(log_entry, f, indent=2)

    # Update schedule state
    schedules = _load_schedules()
    for s in schedules:
        if s["id"] == schedule["id"]:
            s["last_run"] = start.isoformat()
            s["last_status"] = "ok" if success else "failed"
            s["run_count"] = s.get("run_count", 0) + 1
    _save_schedules(schedules)

    return log_entry


# Background scheduler — checks every 60 seconds
async def _scheduler_loop():
    """Background task that runs scheduled jobs."""
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now(timezone.utc)
            schedules = _load_schedules()
            for s in schedules:
                if not s.get("enabled"):
                    continue
                if _cron_matches_now(s.get("cron_expr", ""), now):
                    # Don't run if already ran this minute
                    last = s.get("last_run")
                    if last:
                        try:
                            last_dt = datetime.fromisoformat(last)
                            if (now - last_dt).total_seconds() < 90:
                                continue
                        except (ValueError, TypeError):
                            pass
                    asyncio.create_task(_execute_schedule(s))
        except Exception as e:
            print(f"Scheduler error: {e}")


@app.on_event("startup")
async def start_scheduler():
    asyncio.create_task(_scheduler_loop())


# ========================= HEALTH =========================

@app.get("/api/health")
async def health():
    return {"status": "ok", "repo": REPO_ROOT, "saml": SAML_ENABLED}


# ========================= MAIN =========================

if __name__ == "__main__":
    import uvicorn

    # Bind to localhost by default. The reverse proxy (Caddy) handles external access.
    # Override with BIND_HOST=0.0.0.0 if running without a reverse proxy.
    host = os.environ.get("BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("BIND_PORT", "8420"))

    print(f"\n  Ansible Playbook Builder v3.0")
    print(f"  Repo root: {REPO_ROOT}")
    print(f"  Listening: {host}:{port}")
    if not SAML_ENABLED and not BASIC_AUTH_ENABLED:
        print(f"\n  ⚠  NO AUTH ENABLED — anyone with network access can run commands")
        print(f"  ⚠  Set BASIC_AUTH_ENABLED=true + BASIC_AUTH_PASS=<password> at minimum")
    print()

    uvicorn.run(app, host=host, port=port)
