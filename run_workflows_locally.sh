#!/usr/bin/env bash
# run_workflows_locally.sh
#
# Runs all GitHub Actions workflows in this repository locally using Docker and
# act (https://github.com/nektos/act).
#
# Both tools are installed automatically if they are not already present.
#
# Usage:
#   ./run_workflows_locally.sh [--include-release]
#
#   --include-release   Also run release.yaml (requires a GITHUB_TOKEN env var
#                       with write permissions to the repository and will upload
#                       artefacts to the real GitHub release – use with care).

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[PASS]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[FAIL]${NC}  $*"; }
header()  { echo -e "\n${BOLD}$*${NC}"; }

command_exists() { command -v "$1" &>/dev/null; }

# ── Docker installation ───────────────────────────────────────────────────────
install_docker() {
    if command_exists docker; then
        info "Docker is already installed: $(docker --version)"
        return 0
    fi

    header "Installing Docker…"
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER" || true
    warn "Docker installed. You may need to run 'newgrp docker' or re-login for group membership to take effect."
}

# ── act installation ──────────────────────────────────────────────────────────
install_act() {
    if command_exists act; then
        info "act is already installed: $(act --version)"
        return 0
    fi

    header "Installing act…"
    curl -fsSL https://raw.githubusercontent.com/nektos/act/master/install.sh \
        | sudo bash -s -- -b /usr/local/bin
}

# ── Docker daemon check ───────────────────────────────────────────────────────
ensure_docker_running() {
    if docker info &>/dev/null; then
        return 0
    fi

    warn "Docker daemon is not running – attempting to start it…"
    if command_exists systemctl; then
        sudo systemctl start docker
    else
        sudo service docker start
    fi
    sleep 3

    if ! docker info &>/dev/null; then
        error "Docker daemon is still not running. Please start Docker manually and re-run this script."
        exit 1
    fi
}

# ── Workflow runner ───────────────────────────────────────────────────────────

# Ubuntu runner image used by act.  The "act-latest" tag is a medium-sized
# image that supports most common Actions without requiring the 20 GB+ full
# image.
ACT_IMAGE="catthehacker/ubuntu:act-latest"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_DIR="$SCRIPT_DIR/.github/workflows"

# run_workflow <workflow-file> <event>
# Returns 0 on success, 1 on failure.
run_workflow() {
    local workflow_file="$1"
    local event="$2"
    local name
    name="$(basename "$workflow_file")"

    info "Running [$name] with event '$event'…"

    if act "$event" \
        -W "$workflow_file" \
        -P "ubuntu-latest=$ACT_IMAGE" \
        --rm \
        2>&1; then
        success "$name passed"
        return 0
    else
        error "$name failed"
        return 1
    fi
}

run_all_workflows() {
    local include_release="${1:-false}"

    # List of workflows and the event used to trigger each one locally.
    # Parallel arrays: workflow_files[i] uses workflow_events[i].
    local workflow_files=(
        "test.yml"
        "pylint.yml"
        "integration-tests.yml"
        "hassfest.yaml"
        "validate.yaml"
    )
    local workflow_events=(
        "push"
        "push"
        "push"
        "push"
        "workflow_dispatch"
    )

    local passed=()
    local failed=()
    local skipped=()

    # Optionally include the release workflow
    if [[ "$include_release" == "true" ]]; then
        workflow_files+=("release.yaml")
        workflow_events+=("release")
        warn "Including release.yaml – this uploads artefacts to a real GitHub release."
    else
        skipped+=("release.yaml (skipped by default – pass --include-release to run it)")
    fi

    local i
    for i in "${!workflow_files[@]}"; do
        local workflow="${workflow_files[$i]}"
        local event="${workflow_events[$i]}"
        local workflow_path="$WORKFLOWS_DIR/$workflow"

        if [[ ! -f "$workflow_path" ]]; then
            warn "Workflow file not found, skipping: $workflow"
            skipped+=("$workflow (file not found)")
            continue
        fi

        if run_workflow "$workflow_path" "$event"; then
            passed+=("$workflow")
        else
            failed+=("$workflow")
        fi
    done

    # ── Summary ───────────────────────────────────────────────────────────────
    header "══════════════════════════════════════════════"
    header " Results"
    header "══════════════════════════════════════════════"

    if [[ ${#passed[@]} -gt 0 ]]; then
        success "Passed  (${#passed[@]}): ${passed[*]}"
    fi
    if [[ ${#skipped[@]} -gt 0 ]]; then
        warn    "Skipped (${#skipped[@]}): ${skipped[*]}"
    fi
    if [[ ${#failed[@]} -gt 0 ]]; then
        error   "Failed  (${#failed[@]}): ${failed[*]}"
        return 1
    fi

    echo ""
    success "All runnable workflows completed successfully."
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    local include_release="false"

    for arg in "$@"; do
        case "$arg" in
            --include-release) include_release="true" ;;
            *)
                error "Unknown argument: $arg"
                echo "Usage: $0 [--include-release]"
                exit 1
                ;;
        esac
    done

    header "════════════════════════════════════════════════════"
    header " Running GitHub Actions workflows locally with act"
    header "════════════════════════════════════════════════════"

    install_docker
    install_act
    ensure_docker_running
    run_all_workflows "$include_release"
}

main "$@"
