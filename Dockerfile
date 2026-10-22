FROM python:3.12-slim

# Node.js for the MCP servers started via npx
COPY --from=node:20-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g @modelcontextprotocol/server-filesystem @modelcontextprotocol/server-github \
    && npm cache clean --force

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p workspace

ENV PYTHONUNBUFFERED=1 \
    MY_AGENT_MCP_CONNECT_TIMEOUT=30

# Memory, reminders and audit log live in ~/.my-agent; mount a volume there
# APP_MODE=web runs the web UI, otherwise the Telegram bot
CMD ["sh", "start.sh"]
