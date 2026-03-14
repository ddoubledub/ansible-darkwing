# Ansible Framework

ansible-darkwing ships with a structured Ansible project layout and a set of ready-to-use roles. This page covers the framework components — inventory, roles, playbooks, guardrails, and vault integration.

---

## Directory structure

```
ansible-darkwing/
├── ansible.cfg                   ← Ansible settings (forks, SSH, vault)
├── collections/
│   └── requirements.yml          ← ansible.posix and community.general
├── inventories/
│   └── example/                  ← Copy this to create your environment
│       ├── hosts.yml
│       ├── group_vars/all/main.yml
│       └── host_vars/
├── playbooks/
│   └── playbook_template.yml     ← Annotated starting point
├── roles/
│   ├── role_template/            ← Annotated starting point for new roles
│   ├── 01_reachability/
│   ├── 02_connection_sudo/
│   ├── 03_host_info/
│   ├── 04_security_audit/
│   ├── 05_Get-SSH-Users/
│   └── user_provision/
└── scripts/
    └── validate_inventory.sh
```

Actual inventories (`inventories/prod/`), custom roles (`roles/your_role/`), and custom playbooks (`playbooks/my-run.yml`) are gitignored by default so your infrastructure stays private.

---

## Inventory

### Structure

Copy `inventories/example/` for each environment you manage:

```bash
cp -r inventories/example inventories/prod
cp -r inventories/example inventories/staging
```

Each environment contains:

| File | Purpose |
|---|---|
| `hosts.yml` | Host definitions and group membership |
| `group_vars/all/main.yml` | Variables that apply to all hosts |
| `group_vars/all/vault.yml` | Encrypted secrets (ansible-vault) |
| `group_vars/{group}.yml` | Variables for a specific group |
| `host_vars/{host}.yml` | Variables for a specific host |

### Guardrails

`group_vars/all/main.yml` includes a guardrail system that prevents accidental enforcement changes. All protections are enabled by default:

```yaml
do_not_touch:
  ssh: true
  pam: true
  firewall: true
  sudoers: true
  crypto: true
  auditd: true
```

To allow enforcement on a specific host, set `enrolled: true` in its `host_vars/` file and disable only the specific guardrails you need:

```yaml
# host_vars/my-server.yml
enrolled: true
do_not_touch:
  ssh: false      # allow SSH config enforcement on this host
  pam: true
  firewall: true
  sudoers: false  # allow sudoers enforcement on this host
  crypto: true
  auditd: true
```

### Vault

Sensitive values (passwords, tokens, API keys) go in `vault.yml`, encrypted with `ansible-vault`:

```bash
ansible-vault create inventories/prod/group_vars/all/vault.yml
ansible-vault edit inventories/prod/group_vars/all/vault.yml
```

Reference vault variables in your playbooks and roles the same as any variable — Ansible decrypts them at runtime.

---

## Roles

### Assessment roles (read-only)

These roles gather information and generate reports. They do not make changes and do not require `become` side effects.

#### `01_reachability`
Tests connectivity at three layers:
- ICMP (ping)
- SSH port (TCP)
- Full Ansible connectivity (SSH + Python)

Generates a consolidated reachability report per host. Useful as the first role in any playbook to identify unreachable targets before attempting further tasks.

#### `02_connection_sudo`
Validates authentication:
- SSH connection (raw module, no Python required)
- `become`/sudo access
- Passwordless sudo availability

Reports SSH errors and sudo errors separately with remediation hints.

#### `03_host_info`
Collects system information across mixed OS (Ubuntu, Debian, AlmaLinux, Oracle 8, CentOS 7, Kali):
- OS name, version, and family
- Hostname, FQDN, IP address
- Kernel version, uptime, CPU count, RAM
- Listening ports and associated processes
- SSH-capable users (password vs key status)
- Disks over 90% capacity

#### `04_security_audit`
Runs a CIS-aligned security audit script on the target:
- Produces PASS / FAIL / WARN / SKIP counts
- Generates a scored report with remediation priorities
- Script is removed from the target after execution
- 120-second timeout

#### `05_Get-SSH-Users`
Extracts SSH and sudo configuration:
- Sudo group members
- Sudoers file entries
- SSH config values (PasswordAuthentication, PubkeyAuthentication, PermitRootLogin, etc.)
- AllowUsers, DenyUsers, AllowGroups, DenyGroups
- Per-user SSH keys and password status

Output saved to per-host files on the control node.

---

### Provisioning roles (enforce changes)

These roles make changes to target hosts. They respect the `do_not_touch` guardrails and should be used against enrolled hosts only.

#### `user_provision`
Creates and configures user accounts:
- Create users with specified shell, groups, and password hash
- Install SSH authorized keys
- Configure passwordless sudo (optional)
- Validates sudoers syntax before applying

Fully variable-driven via a `users` list:

```yaml
users:
  - username: deploy
    shell: /bin/bash
    groups: [sudo]
    password_hash: "{{ vault_deploy_password_hash }}"
    pubkeys:
      - "ssh-ed25519 AAAA..."
    sudo_nopasswd: true
```

---

### Creating a new role

```bash
cp -r roles/role_template roles/your_new_role
```

`role_template` is fully annotated with inline comments explaining each section and common task patterns. Every file is a working example, not just a skeleton.

---

## Playbooks

### Starting a new playbook

```bash
cp playbooks/playbook_template.yml playbooks/my-run.yml
```

`playbook_template.yml` is annotated with pre-tasks, role execution block, post-tasks, and variable examples.

### Running playbooks

```bash
# Run against all hosts
ansible-playbook playbooks/my-run.yml

# Limit to a group or host
ansible-playbook playbooks/my-run.yml --limit webservers

# Dry run
ansible-playbook playbooks/my-run.yml --check

# Pass extra variables
ansible-playbook playbooks/my-run.yml -e target=webservers
```

---

## ansible.cfg defaults

Pre-configured with sensible defaults. Things you must change:

| Setting | What to set |
|---|---|
| `remote_user` | Your Ansible service account |
| `private_key_file` | Path to your SSH private key |
| `vault_password_file` | Path to your vault password file (if using vault) |

SSH multiplexing is enabled by default (`ControlMaster auto`) — this significantly speeds up runs against many hosts.

---

## Collections

```bash
ansible-galaxy collection install -r collections/requirements.yml
```

| Collection | Used for |
|---|---|
| `ansible.posix` | `authorized_key`, `sysctl`, `firewalld` |
| `community.general` | `ufw`, `ini_file`, utility modules |
