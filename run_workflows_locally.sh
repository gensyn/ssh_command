#!/usr/bin/env bash
# run_workflows_locally.sh
#
# Runs all GitHub Actions workflows in this repository locally using Docker and
# act (https://github.com/nektos/act).
#
# Both tools are installed automatically if they are not already present.
#
# Usage:
#   ./run_workflows_locally.sh [--include-hassfest] [--include-validate] [--include-release]
#
#   --include-hassfest  Also run hassfest.yaml (may fail locally because act sets
#                       GITHUB_WORKSPACE to the host path, causing hassfest's
#                       directory-name check to fail).
#   --include-validate  Also run validate.yaml (HACS validation fetches data from
#                       the live GitHub repository and may not behave identically
#                       when run locally via act).
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
        info "Docker is already installed: $(sudo docker --version)"
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
    if sudo docker info &>/dev/null; then
        return 0
    fi

    warn "Docker daemon is not running – attempting to start it…"
    if command_exists systemctl; then
        sudo systemctl start docker
    else
        sudo service docker start
    fi
    sleep 3

    if ! sudo docker info &>/dev/null; then
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

    if sudo act "$event" \
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
    local include_hassfest="${1:-false}"
    local include_validate="${2:-false}"
    local include_release="${3:-false}"

    # List of workflows and the event used to trigger each one locally.
    # Parallel arrays: workflow_files[i] uses workflow_events[i].
    local workflow_files=(
        "test.yml"
        "pylint.yml"
        "integration-tests.yml"
    )
    local workflow_events=(
        "push"
        "push"
        "push"
    )

    local passed=()
    local failed=()
    local skipped=()

    # hassfest: skipped by default because act sets GITHUB_WORKSPACE to the
    # host filesystem path, which causes hassfest's directory-name check to
    # fail even though the integration is valid (works fine on GitHub).
    if [[ "$include_hassfest" == "true" ]]; then
        workflow_files+=("hassfest.yaml")
        workflow_events+=("push")
    else
        skipped+=("hassfest.yaml (skipped by default – pass --include-hassfest to run it)")
    fi

    # validate (HACS): skipped by default because it fetches live data from
    # the GitHub repository and may not behave identically when run locally.
    if [[ "$include_validate" == "true" ]]; then
        workflow_files+=("validate.yaml")
        workflow_events+=("workflow_dispatch")
    else
        skipped+=("validate.yaml (skipped by default – pass --include-validate to run it)")
    fi

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
    local include_hassfest="false"
    local include_validate="false"
    local include_release="false"

    for arg in "$@"; do
        case "$arg" in
            --include-hassfest) include_hassfest="true" ;;
            --include-validate) include_validate="true" ;;
            --include-release)  include_release="true" ;;
            *)
                error "Unknown argument: $arg"
                echo "Usage: $0 [--include-hassfest] [--include-validate] [--include-release]"
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
    run_all_workflows "$include_hassfest" "$include_validate" "$include_release"
}

main "$@"
