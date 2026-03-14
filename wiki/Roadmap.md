# Roadmap

This page tracks planned features, known limitations, and areas under active consideration. It is not a commitment or timeline — it reflects current thinking.

---

## Recently Shipped

- Cron-based playbook scheduling with per-run logging
- WebSocket terminal with whitelisted command set
- Git integration (commit, push, pull, log, branch switching)
- SAML authentication via Entra ID / Azure AD
- Vault encrypt/decrypt via UI
- Multi-environment inventory switching
- Live YAML preview in playbook builder
- Docker Compose + Caddy deployment with automatic TLS

---

## In Progress / Near Term

### Container image distribution
Publish pre-built images to GHCR (GitHub Container Registry) so users can pull rather than build. Compose files updated to reference versioned image tags. GitHub Actions workflow for automated builds on release.

### Role variable schema
Allow roles to declare their variables with types and descriptions (via a `schema.yml` in the role). The UI would render typed input fields instead of raw YAML, making it easier to configure roles without knowing the variable names.

### Playbook output improvements
Better parsing of Ansible PLAY RECAP — highlight failures, skips, and changed counts visually rather than showing raw terminal output.

---

## Under Consideration

### Multi-user / RBAC
Currently all authenticated users have full access. A role-based system (read-only vs. operator vs. admin) is a natural next step for teams. SAML group claims are already available in the auth layer.

### Notifications
Post-run notifications (email, Slack webhook, Teams) for scheduled runs. Currently the scheduler logs to JSON files only — no push alerts on failure.

### Inventory import
Import existing inventory from CSV or scan results (e.g. Nmap XML output) to seed hosts.yml without manual entry.

### Run history / audit log
Persistent record of who ran what, when, against which targets, and what the result was. Currently execution output is ephemeral (shown in the terminal, not stored).

### Diff view for inventory changes
Before committing inventory edits, show a structured diff of what changed — hosts added/removed, variables modified.

### Role marketplace / community roles
Browse and install roles from Ansible Galaxy or a curated list directly from the UI without touching the CLI.

### Dark mode
The UI is currently light-only.

---

## Known Limitations

| Limitation | Notes |
|---|---|
| Single instance only | The scheduler and WebSocket terminal are in-process. Running multiple container replicas is not supported. |
| UTC only for scheduling | All cron expressions are evaluated in UTC. No per-schedule timezone support. |
| No job chaining | Schedules are independent. You cannot trigger one playbook after another completes. |
| 30-minute execution timeout | Long-running playbooks will be killed. Not currently configurable via the UI. |
| No output streaming for scheduled runs | Scheduled run output is captured to a log file after completion, not streamed in real time. |
| Terminal is read-mostly | The terminal runs whitelisted read-oriented commands only. It is not a full shell. |
| No diff before git push | Git operations are atomic — there is no pre-push review step in the UI. |

---

## Contributing

Have a feature request or found a bug? Open an issue on GitHub. PRs are welcome — see the contributing notes in the README for conventions.
