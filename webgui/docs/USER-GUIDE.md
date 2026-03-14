# User Guide

## Layout

The interface is split into three areas:

**Left sidebar** — Navigation with two sections:
- **Build** — Targets, Roles, Role Vars, Host/Grp Vars, Run
- **Manage** — Playbooks, Inventory, Schedules, Config, Git, Terminal

**Center panel** — The active tab's content.

**Right panel** — Live preview of the playbook YAML, ansible.cfg, existing playbooks, or role details. Drag the vertical bar between the center and right panels to resize.

---

## Building a Playbook

### 1. Select Targets

Click **Targets** in the sidebar. You'll see two sections:

- **Groups** — Clickable tags for each group in your inventory (`ubuntu`, `cicd`, `iten`, etc.). Click to toggle. Multiple selections are comma-joined in the YAML `hosts:` line.
- **Hosts** — Individual hosts with their `ansible_host` IP shown. Click to toggle.

Selected targets appear in the live YAML preview on the right.

### 2. Add Roles

Click **Roles**. You'll see every role in your `roles/` directory with its description and structure.

- **Filter** — Type in the search box to filter by name or description.
- **Add** — Click "Add" to include a role in your play.
- **View** — Click "View" to inspect the role's tasks, defaults, vars, handlers, and meta in the right panel. Use the sub-tabs (tasks, defaults, vars, handlers, meta) to switch between files.
- **+ New Role** — Creates a new role with the standard `ansible-galaxy init` structure.

### 3. Configure Role Variables

Click **Role Vars**. For each role you've added, you'll see its `defaults/main.yml` variables with input fields. Leave blank to use the default. Enter a value to override.

Use the ▲/▼ buttons to reorder role execution. The × button removes a role.

### 4. Review Host/Group Vars

Click **Host/Grp Vars**. Shows the `group_vars/` and `host_vars/` that apply to your selected targets. This is read-only context — the actual files are edited via the Inventory tab.

### 5. Preview and Run

The right panel shows your generated YAML in real time. You can:

- **Copy** — Click "Copy" to copy the YAML to clipboard.
- **Save** — Click "Save" to write it as a playbook file under `playbooks/`.

Click **Run** in the sidebar for execution options:

- **Run** — Executes the generated playbook without saving it to disk. Writes to a temp file, runs, cleans up.
- **Save & Run** — Saves to `playbooks/` first, then runs.
- **--check** — Dry run. No changes made on targets.

The run output (PLAY RECAP, task results) appears below the buttons.

---

## Running Existing Playbooks

Click **Playbooks** in the sidebar. Every `.yml` file under `playbooks/` is listed.

For each playbook:
- **View** — Opens the raw YAML in the right panel.
- **Target input** — Type a host or group name to target.
- **Run** — Executes the playbook with `-i inventories/{env}` and `--limit` set to your target.
- **--check** — Dry run.

---

## Editing Inventory

Click **Inventory** in the sidebar. Two modes:

### Form Mode (default)

**Add Host** — Fill in hostname, IP, and tags (comma-separated). Click Add. The host is appended to `all.hosts` in `hosts.yml`.

**Add Group** — Enter a group name and comma-separated list of hostnames. Click Add. The group is added under `all.children` in `hosts.yml`.

**Remove Host** — Click × next to any host. Removes it from `all.hosts` and all group memberships.

### Raw Mode

Click "Edit Raw" to switch to a full YAML editor showing `hosts.yml`. Edit freely. The GUI validates YAML before saving — if it's invalid, the save is rejected with an error message.

---

## Scheduling

Click **Schedules** in the sidebar.

### Create a Schedule

1. Click **+ New Schedule**
2. Fill in:
   - **Name** — Descriptive label (e.g., "Nightly STIG scan")
   - **Cron expression** — 5 fields: `min hour dom month dow`
   - **Playbook** — Select from saved playbooks
   - **Targets** — Optional `--limit` pattern
3. Click **Create**

### Cron Expression Examples

| Expression | Meaning |
|-----------|---------|
| `0 2 * * *` | Daily at 2:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 0 * * 0` | Weekly on Sunday midnight |
| `0 6 1 * *` | Monthly on the 1st at 6:00 AM |
| `0 */4 * * 1-5` | Every 4 hours, weekdays only |

### Managing Schedules

Each schedule shows:
- **Status dot** — Green = enabled, grey = disabled
- **Last run** — Status (ok/failed) and timestamp
- **Run count** — Total executions

Actions:
- **Run Now** — Execute immediately regardless of schedule
- **Logs** — View execution history with output, duration, and status
- **Disable/Enable** — Toggle without deleting
- **×** — Delete the schedule

The scheduler runs as a background task inside the app — it checks every 60 seconds and fires any matching cron jobs. No system crontab is used.

---

## Git Operations

Click **Git** in the sidebar.

- **Branch** — Shows current branch (e.g., `Dan1`)
- **Changed files** — Lists modified/added files with git status indicators
- **Commit & Push** — Enter a message, click the button. Stages all changes, commits, pushes to origin.
- **Pull** — Pulls with rebase from origin. Reloads all data after pull.
- **Recent commits** — Shows last 15 commits with short hash, message, and relative time.

---

## Terminal

Click **Terminal** in the sidebar. This is a real terminal connected via WebSocket.

**Allowed commands:** `ansible*`, `git`, `cat`, `ls`, `head`, `tail`, `grep`, `find`, `tree`, `wc`, `ping`, `hostname`, `whoami`, `pwd`, `which`, `id`, `date`.

**Blocked:** `ssh`, `bash`, `python`, `curl`, `rm`, `sudo`, and all shell operators (`;`, `|`, `&`, `` ` ``).

**Features:**
- Arrow up/down for command history
- Ctrl+C (or the red button) to kill a running process
- Quick-launch buttons for common commands
- Output streams in real-time

**Example commands:**
```
ansible-playbook playbooks/scan.yml -i inventories/prod --limit web_servers
ansible-inventory -i inventories/prod --graph
ansible-vault view inventories/prod/group_vars/all/vault.yml
git diff
git log --oneline -20
```

---

## Config

Click **Config** in the sidebar. Shows your `ansible.cfg` in a read-only view. Click **Edit** to modify. Changes are written directly to the file in your repo.

---

## Environment Selector

The **ENV** dropdown in the header switches between inventory environments (e.g., `prod`, `dev`). This controls which `inventories/{env}/` directory is used for everything — targets, group_vars, host_vars, and playbook execution.

---

## Tips

- The right panel preview updates live as you make changes. Use it to verify your YAML before running.
- You can have a role's tasks open in the right panel while configuring its vars in the center panel.
- The terminal is useful for one-off commands that don't warrant building a full play — `ansible all -m ping --limit web`.
- Git commit after making changes. The header dot turns orange when there are uncommitted changes.
- Schedules persist across container restarts (stored in `.ansible-gui/schedules.json`).
