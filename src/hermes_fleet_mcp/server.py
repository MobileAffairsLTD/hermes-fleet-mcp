"""FastMCP server exposing the Hermes deployment surface, behind bearer auth."""

from __future__ import annotations

import os
import secrets

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from .chat import ChatRunner
from .state import HermesState


def _load_token(token: str | None, token_file: str | None) -> str:
    if token:
        return token.strip()
    if token_file:
        with open(token_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return (os.environ.get("HERMES_FLEET_MCP_TOKEN") or "").strip()


class _BearerAuthMiddleware:
    """Reject every HTTP request that doesn't carry the configured bearer token."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            auth = headers.get("authorization", "")
            if not secrets.compare_digest(auth, f"Bearer {self.token}"):
                response = JSONResponse(
                    {"jsonrpc": "2.0", "error": {"code": -32001, "message": "unauthorized"}, "id": None},
                    status_code=401,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_mcp(state: HermesState, runner: ChatRunner) -> FastMCP:
    mcp = FastMCP(
        "hermes-fleet",
        instructions=(
            "Hermes deployment introspection + chat surface. Read-only observability "
            "(agents, sessions, crons, skills, tools) plus a chat tool that runs a "
            "remote agent and returns a session handle to poll."
        ),
        # The Bridge is a server-to-server MCP endpoint (reached by the dmops runtime
        # over host.docker.internal / a real hostname), not a browser client — so DNS
        # rebinding Host-header allowlisting would reject non-localhost callers with 421.
        # Security is the per-node bearer token (+ TLS in front), not Host pinning.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool()
    def node_status() -> dict:
        """Node health: hermes version, home, counts, configured toolsets, bridge uptime."""
        return state.node_status()

    @mcp.tool()
    def list_agents() -> dict:
        """List the node's agents (Hermes profiles) with model, provider, toolsets."""
        agents = state.list_agents()
        return {"agents": agents, "count": len(agents)}

    @mcp.tool()
    def get_agent(name: str) -> dict:
        """Detail for one agent plus its recent sessions (what it's been working on)."""
        agent = state.get_agent(name)
        if not agent:
            return {"ok": False, "error": f"agent '{name}' not found"}
        agent = dict(agent)
        agent["recent_sessions"] = state.list_sessions(agent=name, limit=10)
        return {"ok": True, "agent": agent}

    @mcp.tool()
    def list_sessions(agent: str = "", limit: int = 20, active_only: bool = False) -> dict:
        """Recent sessions (optionally scoped to one agent, or active-only)."""
        sessions = state.list_sessions(agent=agent or None, limit=limit, active_only=active_only)
        return {"sessions": sessions, "count": len(sessions)}

    @mcp.tool()
    def list_crons(agent: str = "") -> dict:
        """Configured cron jobs (optionally scoped to one agent)."""
        crons = state.list_crons(agent=agent or None)
        return {"crons": crons, "count": len(crons)}

    @mcp.tool()
    def list_skills(agent: str = "") -> dict:
        """Installed skills (optionally scoped to one agent)."""
        skills = state.list_skills(agent=agent or None)
        return {"skills": skills, "count": len(skills)}

    @mcp.tool()
    def list_tools() -> dict:
        """The union of toolsets configured across the node's agents."""
        return state.list_toolsets()

    @mcp.tool()
    def chat(agent: str, message: str, caller: str = "") -> dict:
        """Run an agent on the box. Returns a session handle; poll get_session for the reply."""
        if not state.get_agent(agent):
            return {"ok": False, "error": f"agent '{agent}' not found"}
        result = runner.start(agent, message, caller)
        return {"ok": True, **result}

    @mcp.tool()
    def get_session(session_id: str) -> dict:
        """Poll a chat session started by the chat tool."""
        return {"ok": True, **runner.get(session_id)}

    return mcp


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    token: str | None = None,
    token_file: str | None = None,
    hermes_home: str | None = None,
    hermes_bin: str = "hermes",
) -> None:
    import uvicorn

    tok = _load_token(token, token_file)
    if not tok:
        raise SystemExit(
            "No bearer token configured. Run 'hermes-fleet-mcp gen-key' then pass "
            "--token / --token-file, or set HERMES_FLEET_MCP_TOKEN."
        )

    state = HermesState(hermes_home=hermes_home, hermes_bin=hermes_bin)
    runner = ChatRunner(hermes_bin=hermes_bin)
    mcp = build_mcp(state, runner)
    app = _BearerAuthMiddleware(mcp.streamable_http_app(), tok)

    print(f"hermes-fleet-mcp serving MCP at http://{host}:{port}/mcp", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")
