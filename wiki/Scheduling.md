# Scheduling

ansible-darkwing includes a built-in cron-style scheduler for automated playbook runs — no external scheduler required.

---

## How it works

The scheduler runs as an asyncio background task inside the FastAPI process. Every 60 seconds it checks all enabled schedules against the current UTC time. When a schedule matches, it runs the playbook as a subprocess and captures the output to a log file.

Schedules are stored in `.ansible-gui/schedules.json` in your repo directory. Run logs are stored in `.ansible-gui/logs/`.

---

## Cron expression format

Standard 5-field cron format, evaluated in UTC:

```
min  hour  dom  month  dow
 *    *     *     *     *
```

| Field | Range | Special characters |
|---|---|---|
| Minute | 0–59 | `*` `,` `-` |
| Hour | 0–23 | `*` `,` `-` |
| Day of month | 1–31 | `*` `,` `-` |
| Month | 1–12 | `*` `,` `-` |
| Day of week | 0–6 (0 = Sunday) | `*` `,` `-` |

### Common patterns

| Expression | Meaning |
|---|---|
| `0 2 * * *` | Daily at 02:00 UTC |
| `0 8 * * 1` | Every Monday at 08:00 UTC |
| `*/30 * * * *` | Every 30 minutes |
| `0 */4 * * *` | Every 4 hours |
| `0 9 * * 1-5` | Weekdays at 09:00 UTC |
| `0 0 1 * *` | First of every month at midnight |

---

## Creating a schedule

Via the UI:
1. Navigate to **Scheduling**
2. Select a playbook from the dropdown
3. Optionally set a `--limit` for scoping
4. Enter a cron expression
5. Enable and save

Via the API:
```bash
curl -X POST http://localhost:8420/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "playbook": "playbooks/my-run.yml",
    "cron": "0 2 * * *",
    "limit": "webservers",
    "enabled": true
  }'
```

---

## Run history

Each run produces a JSON log file in `.ansible-gui/logs/`. Log entries include:

- `schedule_id`
- `started_at` / `finished_at`
- `duration_seconds`
- `success` (boolean)
- `output` (truncated at 10,000 characters)

View run history in the UI under the Scheduling section, or inspect the log files directly.

---

## Limitations

| Limitation | Detail |
|---|---|
| UTC only | All cron expressions are evaluated in UTC. No per-schedule timezone. |
| Single instance | The scheduler is in-process. Multiple container replicas are not supported. |
| No job chaining | Schedules are independent. You cannot trigger a playbook after another completes. |
| 30-minute timeout | Playbooks that exceed 30 minutes are killed. |
| No output streaming | Scheduled run output is captured after completion, not streamed in real time. |
| Re-fire prevention | A schedule won't re-fire if the previous run finished less than 90 seconds ago. |
| No notifications | Failures write to log files only. No email/Slack/webhook alerts (on the roadmap). |
