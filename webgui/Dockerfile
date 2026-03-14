FROM python:3.12-slim

# ── System deps ──────────────────────────────────────────────
# xmlsec1: required by python3-saml for SAML signature validation
# git: for git operations against the mounted repo
# openssh-client: for git push/pull over SSH (Azure DevOps, etc.)
# ansible: for vault encrypt/decrypt and playbook execution
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    xmlsec1 \
    pkg-config \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    && rm -rf /var/lib/apt/lists/*
# Install ansible separately (keeps layer caching cleaner)
ARG ANSIBLE_VERSION
RUN pip install --no-cache-dir ansible-core${ANSIBLE_VERSION:+==$ANSIBLE_VERSION}
RUN ansible-galaxy collection install ansible.posix community.general
# ── App ──────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

# ── Runtime ──────────────────────────────────────────────────
# The ansible repo gets mounted at /repo
ENV ANSIBLE_REPO=/repo
ENV SAML_ENABLED=false
ENV ANSIBLE_VAULT_PASSWORD_FILE=/run/secrets/vault_pass
ENV SESSION_SECRET=""
ENV PYTHONUNBUFFERED=1

EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8420/api/health')" || exit 1

# Entrypoint handles: SSH known_hosts, git safe.directory, key perms
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8420", "--workers", "1"]
