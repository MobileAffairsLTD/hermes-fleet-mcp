# INSTALL — instructions for a Hermes agent on the box

> **Read this file as your task.** You are a Hermes agent running on the machine
> that should host the `hermes-fleet-mcp` **Node Bridge**. Install it on THIS
> machine, run it as a service that survives reboots, and report the connection
> details back to the human.

Do the steps in order. Resolve each value before you use it. Prefer the defaults;
only ask the human the questions in **step 6** — everything else you decide and
report.

---

## 0. What you are installing

`hermes-fleet-mcp` is an MCP server that exposes this Hermes deployment's state
(agents, sessions, crons, skills, tools) and a chat surface, so a control plane
(DMOps) can observe and drive this box. It runs as a local HTTP service and is
protected by a single bearer token.

- Repo / source of truth: https://github.com/MobileAffairsLTD/hermes-fleet-mcp
- Requires Python 3.10+ and a working `hermes` CLI (you are one).

---

## 1. Detect the environment

```bash
uname -s                      # Linux | Darwin | MINGW* (Windows)
whoami                        # the user Hermes runs as
command -v hermes && hermes --version
echo "${HERMES_HOME:-$HOME/.hermes}"     # the Hermes home this bridge must read
command -v python3 && python3 --version
command -v uv; command -v pipx; command -v systemctl; command -v launchctl
```

Record:

- `OS` = Linux / macOS / Windows
- `HERMES_USER` = the user running Hermes (install + run the bridge as this same user)
- `HERMES_HOME` = as above
- `HERMES_BIN` = full path to the `hermes` executable
  (`command -v hermes`, or `$HERMES_HOME/hermes-agent/venv/bin/hermes` if not on PATH)

---

## 2. Install the package

Install into an isolated tool env so Hermes' own venv stays untouched. Try in
order, use the first that succeeds:

```bash
# (a) uv
uv tool install git+https://github.com/MobileAffairsLTD/hermes-fleet-mcp.git

# (b) pipx
pipx install git+https://github.com/MobileAffairsLTD/hermes-fleet-mcp.git

# (c) dedicated venv (last resort)
python3 -m venv "$HOME/.hermes-fleet-mcp/venv" \
  && "$HOME/.hermes-fleet-mcp/venv/bin/pip" install \
       git+https://github.com/MobileAffairsLTD/hermes-fleet-mcp.git
```

After install, resolve the binary path and record it as `HERMES_FLEET_BIN`:

```bash
HERMES_FLEET_BIN=$(command -v hermes-fleet-mcp || echo "$HOME/.hermes-fleet-mcp/venv/bin/hermes-fleet-mcp")
"$HERMES_FLEET_BIN" --version      # expect: hermes-fleet-mcp 0.1.0
```

---

## 3. Generate the bearer token

```bash
TOKEN=$("$HERMES_FLEET_BIN" gen-key)
printf '%s\n' "$TOKEN"            # save this — you report it in step 7, store it in the service env
```

Store it somewhere the service can read it, owned by `HERMES_USER`:

```bash
umask 077 && printf '%s\n' "$TOKEN" > "$HERMES_HOME/hermes-fleet-mcp.key"
```

---

## 4. Configure the service (survives reboots)

Pick the `BIND` and `PORT` in **step 6** first, then write the service. Default:
`BIND=127.0.0.1`, `PORT=8000`.

### 4a. Linux + systemd

```bash
sudo tee /etc/systemd/system/hermes-fleet-mcp.service >/dev/null <<UNIT
[Unit]
Description=hermes-fleet-mcp (Node Bridge)
After=network.target

[Service]
User=$HERMES_USER
Environment=HERMES_FLEET_MCP_TOKEN_FILE=$HERMES_HOME/hermes-fleet-mcp.key
Environment=HERMES_HOME=$HERMES_HOME
ExecStart=$HERMES_FLEET_BIN serve --host $BIND --port $PORT --token-file $HERMES_HOME/hermes-fleet-mcp.key
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now hermes-fleet-mcp
systemctl --no-pager status hermes-fleet-mcp | head -20
```

### 4b. macOS + launchd

Write `$HOME/Library/LaunchAgents/com.dmops.hermes-fleet-mcp.plist` with
`ProgramArguments = [$HERMES_FLEET_BIN, "serve", "--host", $BIND, "--port", $PORT, "--token-file", "$HERMES_HOME/hermes-fleet-mcp.key"]`,
`RunAtLoad=true`, `KeepAlive=true`, then `launchctl load -w <plist>` and
`launchctl start com.dmops.hermes-fleet-mcp`.

### 4c. Windows

Create a Scheduled Task that runs at logon / startup with the same command
(`$HERMES_FLEET_BIN serve --host $BIND --port $PORT --token-file ...`), run as
`HERMES_USER`, with "Restart on failure". (No systemd here.)

---

## 5. Verify

```bash
# (a) service state
systemctl is-active hermes-fleet-mcp          # Linux → expect: active
# macOS: launchctl list | grep hermes-fleet ; Windows: Get-ScheduledTask

# (b) auth is enforced — no token must be rejected with 401
curl -s -o /dev/null -w '%{http_code}\n' "http://$BIND:$PORT/mcp"          # expect 401

# (c) with the token the server answers (status won't be 401)
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" "http://$BIND:$PORT/mcp"
```

`(b)` must be `401` and `(c)` must NOT be `401`. If either is wrong, stop and fix
before reporting.

---

## Docker alternative (skip steps 2–5 if you use containers)

If this box prefers containers over a native install, replace steps 2–5 with:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_FLEET_MCP_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
git clone https://github.com/MobileAffairsLTD/hermes-fleet-mcp.git /tmp/hermes-fleet-mcp
cd /tmp/hermes-fleet-mcp
HERMES_HOME="$HERMES_HOME" HERMES_FLEET_MCP_TOKEN="$HERMES_FLEET_MCP_TOKEN" docker compose up -d --build
docker compose ps
```

Notes:

- Read tools work with `HERMES_HOME` mounted read-only.
- The `chat` tool + version need the `hermes` CLI in the container — build FROM a
  Hermes image, or mount the host install and pass `--hermes-bin` (see `docker-compose.yml`).
- Verify: `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/mcp` must be `401`
  without a token.

Then continue at step 6 below.

## 6. Ask the human (only these, and only if you can't safely default)

1. **Bind address** — default `127.0.0.1` (safe; needs a TLS reverse proxy for
   remote access). Ask for `0.0.0.0` only if the human wants to reach it directly
   from another host and confirms the network path is private. If a reverse proxy
   exposes the bridge under its own domain, pass `--allowed-host <domain>`
   (repeatable) to re-enable DNS-rebinding protection and whitelist that domain —
   optional, but recommended when the domain is public.
2. **Port** — default `8000`. Ask only if `8000` is already in use.

Everything else (installer, token, service name, user) you decide — do not ask.

---

## 7. Report back to the human (use this format)

```
✅ hermes-fleet-mcp installed — v0.1.0

Service:      hermes-fleet-mcp (systemd: active + enabled, survives reboot)
Endpoint:     http://<HOST>:<PORT>/mcp   ← DMOps MCP URL
Bind:         <BIND>:<PORT>
Auth token:   <TOKEN>                    ⚠️ secret — store in DMOps, never commit

To connect DMOps to this box, give it exactly two facts:
  1. URL:  https://<reachable-host>/mcp   (put a TLS reverse proxy in front)
  2. Token: <TOKEN>

Manage it:
  logs:        journalctl -u hermes-fleet-mcp -f        (or the OS equivalent)
  restart:     systemctl restart hermes-fleet-mcp
  change token: hermes-fleet-mcp gen-key | sudo tee <HERMES_HOME>/hermes-fleet-mcp.key, then restart
  uninstall:   <the installer's remove cmd> && sudo systemctl disable --now hermes-fleet-mcp

⚠️ TLS: the token travels in the clear over plain HTTP. For production, expose
   the service only through a TLS reverse proxy (or a private network), never
   directly on the public internet.

   Optional hardening: `--allowed-host <domain>` (repeatable) re-enables
   DNS-rebinding protection with your domain whitelisted. Without it the bridge
   accepts any Host header — fine for server-to-server, since the bearer token is
   the real gate.
```

Fill `<HOST>` with the machine's hostname/IP that DMOps can reach
(`hostname -f` or `hostname -I`). If you bound `127.0.0.1`, remind the human the
reverse proxy is required for remote access.
