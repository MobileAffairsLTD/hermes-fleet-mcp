# hermes-fleet-mcp — Node Bridge
#
# The read tools (agents/sessions/crons/skills/toolsets) only need HERMES_HOME
# mounted read-only. The `chat` tool and the version field in `node_status` shell
# out to the `hermes` CLI, which must be reachable inside the container:
#   - build FROM a Hermes image that already ships `hermes`, or
#   - mount the host Hermes install and pass --hermes-bin, or
#   - accept read-only observability (chat returns an error).

FROM python:3.11-slim

LABEL org.opencontainers.image.title="hermes-fleet-mcp"
LABEL org.opencontainers.image.description="MCP server exposing a Hermes deployment's state + chat"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

EXPOSE 8000

ENTRYPOINT ["hermes-fleet-mcp"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
