#!/usr/bin/env bash
#
# Bifrost bootstrap installer.
#
# Installs the runtimes Bifrost needs (node >= 22 and bun) if they are missing,
# then installs the Bifrost CLI globally straight from the git repo.
#
# This script is published to the PUBLIC bootstrap repo (callmedraxx/bifrost),
# so the curl|bash link needs no token to fetch. The CLI source repo
# (callmedraxx/bifrost-code) stays PRIVATE, so installing it still needs a
# GitHub credential — pass one of:
#
#   # 1) GitHub PAT (repo read) — true one-liner on a bare machine:
#   GITHUB_TOKEN=ghp_xxx bash -c "$(curl -fsSL \
#     https://raw.githubusercontent.com/callmedraxx/bifrost/main/install.sh)"
#
#   # 2) SSH key already on the machine's GitHub account:
#   curl -fsSL https://raw.githubusercontent.com/callmedraxx/bifrost/main/install.sh \
#     | USE_SSH=1 bash
#
#   # 3) gh CLI already authenticated (gh auth login):
#   curl -fsSL https://raw.githubusercontent.com/callmedraxx/bifrost/main/install.sh | bash
#
# Overrides (env vars):
#   BIFROST_REPO   repo slug (default: callmedraxx/bifrost-code)
#   BIFROST_REF    branch/tag/commit to install (default: main)
#   GITHUB_TOKEN   token injected into the https clone URL for private repos
#   USE_SSH=1      clone over ssh (git@github.com:...) instead of https
#
set -euo pipefail

REPO="${BIFROST_REPO:-callmedraxx/bifrost-code}"
REF="${BIFROST_REF:-main}"
NODE_MAJOR_MIN=22

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarn:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

node_major() {
  have node || return 1
  node -p 'process.versions.node.split(".")[0]' 2>/dev/null || return 1
}

ensure_node() {
  local major
  if major="$(node_major)" && [ "${major:-0}" -ge "$NODE_MAJOR_MIN" ]; then
    log "node $(node --version) already present"
    return
  fi

  if have node; then
    warn "node $(node --version) is older than v${NODE_MAJOR_MIN}; installing a newer one via nvm"
  else
    log "node not found; installing via nvm (no root required)"
  fi

  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
  fi
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh"
  nvm install "$NODE_MAJOR_MIN"
  nvm use "$NODE_MAJOR_MIN"
  nvm alias default "$NODE_MAJOR_MIN" >/dev/null 2>&1 || true

  have node || die "node install failed"
  log "node $(node --version) ready"
}

ensure_bun() {
  if have bun; then
    log "bun $(bun --version) already present"
    return
  fi
  log "bun not found; installing"
  curl -fsSL https://bun.sh/install | bash
  export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
  export PATH="$BUN_INSTALL/bin:$PATH"
  have bun || die "bun install failed (open a new shell and re-run, or add \$HOME/.bun/bin to PATH)"
  log "bun $(bun --version) ready"
}

build_spec() {
  if [ "${USE_SSH:-0}" = "1" ]; then
    printf 'git+ssh://git@github.com/%s.git#%s' "$REPO" "$REF"
  elif [ -n "${GITHUB_TOKEN:-}" ]; then
    printf 'git+https://%s@github.com/%s.git#%s' "$GITHUB_TOKEN" "$REPO" "$REF"
  else
    printf 'git+https://github.com/%s.git#%s' "$REPO" "$REF"
  fi
}

main() {
  have curl || die "curl is required to bootstrap; install curl and re-run"
  have git  || warn "git not found — npm may need it to clone the repo; install git if the next step fails"

  ensure_bun
  ensure_node

  local spec
  spec="$(build_spec)"
  log "installing bifrost from ${REPO}#${REF}"
  # bun's build runs via the package's "prepare" script during install.
  npm install -g "$spec"

  if have bifrost; then
    log "done — run: bifrost"
  else
    warn "bifrost installed but not on PATH yet. Open a new shell, or ensure your node/npm global bin dir is on PATH."
    warn "  npm global bin: $(npm prefix -g 2>/dev/null)/bin"
  fi
}

main "$@"
