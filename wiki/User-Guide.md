# User Guide

Day-to-day usage of the ansible-darkwing web GUI.

---

## Interface layout

The UI has three panels:

- **Left sidebar** — navigation between sections
- **Center panel** — main content area (forms, editors, output)
- **Right panel** — live YAML preview (playbook builder) or contextual info

---

## Building a playbook

1. **Targets** — Select groups or individual hosts from your inventory. The dropdown is populated from your live `hosts.yml`.

2. **Roles** — Browse available roles from your `roles/` directory. Search by name. Add them in the order you want them to execute.

3. **Role variables** — For each added role, configure variables through the UI. Defaults are pre-populated from the role's `defaults/main.yml`.

4. **Host/group variables** — Optionally set `--extra-vars` or override specific variables for this run.

5. **Preview and run** — The right panel shows the generated YAML in real time. When ready:
   - **Run** — Execute immediately
   - **Save & Run** — Write the playbook file, then execute
   - **Dry Run** — Execute with `--check` (no changes made)

---

## Running an existing playbook

Select a playbook from the list. Optionally:
- Set a `--limit` to scope the run to specific hosts or groups
- Pass extra variables

Run output appears in the center panel. The PLAY RECAP is shown at the bottom.

---

## Inventory management

### Form mode
Add hosts and groups through structured fields. The GUI writes valid YAML to `hosts.yml` automatically.

### Raw mode
Edit `hosts.yml` directly in an in-browser editor with YAML validation. Useful for bulk edits or pasting from an existing inventory.

### Group and host variables
Navigate to a group or host to edit its `group_vars/` or `host_vars/` file in-browser.

### Environment selector
Switch between inventory environments (prod, staging, dev) using the dropdown at the top of the inventory section. All GUI operations apply to the selected environment.

---

## Scheduling

Set playbooks to run automatically on a cron schedule.

**To create a schedule:**
1. Navigate to Scheduling
2. Select a playbook and optionally a `--limit`
3. Enter a cron expression (e.g. `0 2 * * *` for daily at 02:00 UTC)
4. Enable and save

Schedules can be enabled/disabled without deleting them. View run history and output from the scheduling section.

See [Scheduling](Scheduling) for cron expression reference and limitations.

---

## Terminal

A restricted shell for read-oriented operations.

**Allowed commands:** `ansible*`, `git`, `cat`, `ls`, `head`, `tail`, `grep`, `find`, `tree`, `wc`, `ping`, `hostname`, `whoami`, `pwd`, `which`, `id`, `date`

**Examples:**
```
ansible -m ping all
ansible-inventory --list
ansible-playbook playbooks/my-run.yml --check
git log --oneline -10
```

Use arrow keys for command history. Ctrl+C to interrupt a running command.

---

## Git

| Action | What it does |
|---|---|
| Status | Shows current branch, modified files, remote URL |
| Commit | Commits staged changes with a message |
| Push | Pushes current branch to remote |
| Pull | Pulls with rebase |
| Log | Shows last 15 commits |
| Checkout | Switches branches |

Typical workflow: build a playbook → make inventory changes → commit → push.

---

## Vault

| Action | What it does |
|---|---|
| Encrypt | Takes plaintext, returns vault-encrypted string |
| Decrypt | Decrypts a vault-encrypted file for viewing |
| Find encrypted files | Lists all vault-encrypted files in the repo |

The vault password is mounted from your host at container startup — you never enter it in the UI.

---

## Tips

- The right YAML preview panel updates live as you build — use it to catch mistakes before running.
- Use **dry run** (`--check`) when running against production for the first time.
- The terminal is great for quick `ansible -m ping all` checks without leaving the browser.
- Commit and push after significant inventory or playbook changes — the GUI is just editing files, so git is your undo history.
