# Scheduling Guide

The scheduler runs inside the app container as a background asyncio task. It checks every 60 seconds and fires any jobs whose cron expression matches the current time.

## How It Works

1. Schedules are stored in `.ansible-gui/schedules.json` in your repo root (gitignored).
2. Execution logs are stored in `.ansible-gui/logs/` as individual JSON files.
3. The scheduler runs in UTC. Keep this in mind when writing cron expressions.
4. If the container restarts, schedules persist (file-based). Active executions are lost.

## Creating a Schedule

From the **Schedules** tab:

1. Click **+ New Schedule**
2. **Name** — Human-readable identifier
3. **Cron expression** — Standard 5-field format: `minute hour day-of-month month day-of-week`
4. **Playbook** — Select from saved playbooks in `playbooks/`
5. **Targets** — Optional `--limit` value (host or group name)
6. Click **Create**

## Cron Expression Reference

```
┌───────── minute (0-59)
│ ┌─────── hour (0-23)
│ │ ┌───── day of month (1-31)
│ │ │ ┌─── month (1-12)
│ │ │ │ ┌─ day of week (0-6, 0=Sunday)
│ │ │ │ │
* * * * *
```

### Supported Syntax

| Syntax | Meaning | Example |
|--------|---------|---------|
| `*` | Any value | `* * * * *` = every minute |
| `5` | Exact value | `5 * * * *` = at minute 5 |
| `*/N` | Every N | `*/15 * * * *` = every 15 min |
| `1,3,5` | List | `0 1,3,5 * * *` = 1am, 3am, 5am |
| `1-5` | Range | `0 9 * * 1-5` = 9am weekdays |

### Common Patterns

| Expression | Schedule |
|-----------|----------|
| `0 2 * * *` | Daily at 2:00 AM |
| `0 0 * * 0` | Weekly, Sunday midnight |
| `0 6 1 * *` | Monthly, 1st at 6:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 */4 * * 1-5` | Every 4 hours, Mon-Fri |
| `0 22 * * *` | Daily at 10:00 PM |
| `30 2 * * 1` | Monday at 2:30 AM |
| `0 9,17 * * *` | 9 AM and 5 PM daily |

## Execution Details

When a schedule fires:

- If it references a saved playbook, that file is used directly
- If it has inline YAML content, a temp file is written, executed, and cleaned up
- The vault password file is included if it exists
- Output is capped at 10,000 characters per run (last 10k)
- Timeout is 30 minutes per execution
- The scheduler won't re-fire a job if it already ran within the last 90 seconds

## Logs

Each execution creates a JSON file in `.ansible-gui/logs/`:

```
.ansible-gui/logs/a1b2c3d4_20260312_020000.json
```

Contents:
```json
{
  "schedule_id": "a1b2c3d4",
  "schedule_name": "Nightly STIG",
  "started": "2026-03-12T02:00:00+00:00",
  "finished": "2026-03-12T02:02:45+00:00",
  "duration_seconds": 165.3,
  "success": true,
  "output": "PLAY [scan] ***...",
  "command": "ansible-playbook /repo/playbooks/scan.yml -i /repo/inventories/prod --limit linux_all"
}
```

View logs in the GUI by clicking **Logs** on any schedule.

## Managing via API

See the [API Reference](API-REFERENCE.md#schedules) for programmatic access.

## Limitations

- No chained/dependent jobs — each schedule is independent
- No timezone support — cron expressions are evaluated in UTC
- In-process scheduler — if the container is down, nothing runs
- Single-instance only — running multiple app containers would duplicate job execution
- No notifications — check logs manually or build a webhook
