---
name: hermes-fleet-mcp-operator
description: "Use when managing the hermes-fleet-mcp Node Bridge on this box — start/stop/restart, rotate the bearer token, debug, and answer questions about it."
version: 1.0.0
author: Dynamics Mobile OOD
license: MIT
metadata:
  hermes:
    tags: [mcp, hermes-fleet-mcp, node-bridge, operations, dmops]
    related_skills: []
---

# Operating the hermes-fleet-mcp Node Bridge

## Overview

`hermes-fleet-mcp` is the **Node Bridge** installed on this box: an MCP server that
exposes this Hermes deployment's state (agents, sessions, crons, skills, tools) and a
chat surface, so a control plane (DMOps) can observe and drive this box over MCP. It
runs as a local HTTP service behind a single bearer token.

This skill is your operating runbook for that service — keep it running, rotate its
secret, diagnose it when DMOps can't connect, and answer the human's questions about it.

## When to Use

- The human asks about the bridge: "is it running?", "why can't DMOps connect?",
  "how do I change the token?", "what's on this box?"
- You need to start, stop, or restart the bridge.
- You need to rotate the bearer token.
- Something is failing (401 / 421 / connection refused) and you must diagnose it.

Don't use for: changing what the bridge *exposes* (a code change to the
`hermes-fleet-mcp` repo), or DMOps-side configuration (the control plane's job).

## Recall: how it's installed here

- **Service name:** `hermes-fleet-mcp` (systemd on Linux; launchd on macOS; a
  Scheduled Task on Windows; `docker compose` if containerized).
- **Binary:** `hermes-fleet-mcp` (on `PATH`, or `$HERMES_HOME/hermes-fleet-mcp/venv/bin/hermes-fleet-mcp`).
- **Token file:** `$HERMES_HOME/hermes-fleet-mcp.key` (the bearer secret).
- **Endpoint:** `http://<BIND>:<PORT>/mcp` (default `127.0.0.1:8000`).
- **Auth:** every request must send `Authorization: Bearer <token>`.

If you don't know which installer was used, detect it before acting — see step 1 of
`INSTALL.md` in the repo.

## Start / stop / restart

**Linux (systemd):**

```bash
systemctl status hermes-fleet-mcp           # is-active + recent logs
systemctl start  hermes-fleet-mcp
systemctl stop   hermes-fleet-mcp
systemctl restart hermes-fleet-mcp
journalctl -u hermes-fleet-mcp -n 100 -f    # follow logs
```

**macOS (launchd):**

```bash
launchctl list | grep hermes-fleet
launchctl start com.dmops.hermes-fleet-mcp
launchctl stop  com.dmops.hermes-fleet-mcp
launchctl kickstart -k gui/$(id -u)/com.dmops.hermes-fleet-mcp   # restart
```

**Windows:** use the Scheduled Task the installer created (Start/Stop/Restart, or
`Get-ScheduledTask` / `Start-ScheduledTask` / `Stop-ScheduledTask`).

**Docker:**

```bash
docker compose -f /tmp/hermes-fleet-mcp/docker-compose.yml ps
docker compose -f /tmp/hermes-fleet-mcp/docker-compose.yml restart
docker compose -f /tmp/hermes-fleet-mcp/docker-compose.yml logs -f
```

## Is it up? (quick health check)

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/mcp
```

- `401` → up, waiting for a valid token. **`401` is the healthy signal** for an
  unauthenticated probe.
- `000` / connection refused → not running; start it (see above).
- `421` → DNS-rebinding Host rejection (see Common Pitfalls).

## Rotate the bearer token

```bash
TOKEN=$(hermes-fleet-mcp gen-key)
umask 077 && printf '%s\n' "$TOKEN" > "$HERMES_HOME/hermes-fleet-mcp.key"
systemctl restart hermes-fleet-mcp        # (or the OS equivalent)
```

⚠️ **Coordinate with the human.** The control plane (DMOps) holds the OLD token in its
Node connection. After you rotate, the human must update the node's token in DMOps or
the box will show `offline`. Report the new token to the human (never commit it — it's
a secret).

## Debugging "DMOps can't connect"

Work top-down:

1. **Is it running?** `systemctl is-active hermes-fleet-mcp` + the health check above.
2. **Is it bound where DMOps can reach it?** `ss -tlnp | grep 8000` (Linux). Bound to
   `127.0.0.1` → reachable only locally; a reverse proxy must be in front.
3. **Token match?** DMOps' stored token must equal `$HERMES_HOME/hermes-fleet-mcp.key`.
   Mismatch → `401`.
4. **`421 Misdirected`?** The bridge's DNS-rebinding protection rejected the Host
   header (a proxy/ngrok domain). Add `--allowed-host <domain>` to the service command
   (or keep ngrok's `host_header: rewrite`). See Common Pitfalls.
5. **Read the logs:** `journalctl -u hermes-fleet-mcp -n 200` — it logs the Host header
   on rejection and every tool call.

## Answering the human's questions

- **"Is the bridge running?"** → `systemctl status hermes-fleet-mcp` + the curl check.
- **"What agents are on this box?"** → read `$HERMES_HOME/config.yaml` and
  `$HERMES_HOME/profiles/*/config.yaml` (each is an agent), or call the bridge's
  `list_agents` tool.
- **"How do I connect a new control plane?"** → hand over the URL + the token from
  `$HERMES_HOME/hermes-fleet-mcp.key`; remind them to front it with TLS.
- **"Rotate the token."** → run the rotate steps above, then report the new token.

## Common Pitfalls

1. **Reading `000` as success.** Connection refused means the service is DOWN. `401` is
   the healthy signal for an unauthenticated probe.
2. **Rotating the token without telling the human.** Breaks the DMOps connection until
   they update it. Always report the new token.
3. **The `421` / DNS-rebinding trap.** When a reverse proxy (nginx/caddy/ngrok) fronts
   the bridge under its own domain, the SDK rejects the Host header with `421`. Fix it
   by adding `--allowed-host <domain>` to the service command (repeatable; a bare host
   also allows any port) — not by disabling auth.
4. **Treating the token as disposable.** It's a secret: never print it into logs, commit
   it, or paste it anywhere except the control plane's credential field.

## Verification Checklist

- [ ] `curl http://127.0.0.1:8000/mcp` returns `401` (up + auth enforced).
- [ ] `systemctl is-active hermes-fleet-mcp` (or OS equivalent) reports `active`.
- [ ] After a token rotation, the human has the new token and DMOps reconnected.
- [ ] `journalctl -u hermes-fleet-mcp -n 50` shows no repeating errors.
