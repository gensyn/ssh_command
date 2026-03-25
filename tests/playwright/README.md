# SSH Command Playwright E2E Tests

End-to-end tests for the **SSH Command** Home Assistant custom component using
[Playwright](https://playwright.dev/python/).

## Running with Docker (recommended)

The repository ships a `docker-compose.yaml` that starts Home Assistant, the
SSH test servers, and a self-contained Playwright test-runner — no local Python
environment or browser installation required.

```bash
# From the repository root:

# First run: build the images (only needed once, or after code changes)
docker compose build

# Run the full E2E suite
docker compose run --rm playwright-tests

# Stop background services and remove volumes when done
docker compose down -v
```

On the **first run** the test-runner container automatically creates the HA
admin user via the onboarding API, so no manual UI interaction is needed.

Test results (JUnit XML) are written to `playwright-results/` in the repository
root and can be used by CI or inspected locally.

## Running the full CI suite locally

`run_workflows_locally.sh` now includes the Playwright E2E tests.  It calls
`docker compose run` directly instead of going through `act`:

```bash
./run_workflows_locally.sh
```

## Running without Docker (advanced)

If you prefer to run outside the container (e.g. against a pre-existing HA
instance), install dependencies on the host and point the env vars at your
services:

```bash
# Install dependencies
pip install -r tests/playwright/requirements.txt
playwright install chromium

# Point at your services
export HOMEASSISTANT_URL=http://localhost:8123
export SSH_HOST=localhost
export SSH_PORT_1=2222
export SSH_PORT_2=2223
export HA_USERNAME=admin
export HA_PASSWORD=admin

pytest tests/playwright/ -v
```

## GitHub Actions

The `.github/workflows/playwright-tests.yml` workflow runs the full suite on
every push.  It builds the images, calls `docker compose run playwright-tests`,
and uploads `playwright-results/junit.xml` as a workflow artifact.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HOMEASSISTANT_URL` | `http://homeassistant:8123` | Home Assistant base URL |
| `SSH_HOST` | `ssh_docker_test` | Hostname of the SSH test servers |
| `SSH_PORT_1` | `2222` | Port for SSH Test Server 1 (fixture metadata only) |
| `SSH_PORT_2` | `2223` | Port for SSH Test Server 2 (fixture metadata only) |
| `SSH_USER` | `foo` | SSH username |
| `SSH_PASSWORD` | `pass` | SSH password |
| `HA_USERNAME` | `admin` | Home Assistant admin username |
| `HA_PASSWORD` | `admin` | Home Assistant admin password |

## Docker image layout

| File | Purpose |
|---|---|
| `Dockerfile` | Playwright test-runner (Python 3.12 + Chromium) |
| `Dockerfile.ssh` | SSH test server (Ubuntu 24.04 + two sshd daemons on ports 2222/2223) |
| `entrypoint.sh` | Container startup: wait for HA → onboard → run pytest |
| `docker-compose.yaml` | (repo root) Orchestrates all three services |

## Test Modules

| File | What it tests |
|---|---|
| `test_integration_setup.py` | Add/assert duplicate blocked/remove lifecycle |
| `test_command_execution.py` | Executing SSH commands against real test servers |
| `test_services.py` | The `ssh_command.execute` HA service interface |
| `test_frontend.py` | Home Assistant frontend pages and UI interactions |
| `test_configuration.py` | Configuration options (timeout, auth, known hosts, …) |
| `test_security.py` | Security properties (auth validation, unauthenticated access, …) |

## Fixtures (`conftest.py`)

| Fixture | Scope | Description |
|---|---|---|
| `playwright_instance` | session | Playwright instance |
| `browser` | session | Headless Chromium browser |
| `ha_base_url` | session | Configured HA URL |
| `ha_token` | session | Long-lived HA access token |
| `context` | function | Authenticated browser context |
| `page` | function | Fresh page within the authenticated context |
| `ssh_server_1` | session | Connection params for SSH server 1 |
| `ssh_server_2` | session | Connection params for SSH server 2 |
| `ha_api` | function | `requests.Session` for the HA REST API |
| `ensure_integration` | function | Ensures SSH Command is set up; fully restores state after test |

## Notes

- Tests are **idempotent** – each test cleans up after itself.
- Tests do **not** depend on each other.
- Browser-based tests use a headless Chromium instance.
- API-based tests call Home Assistant's REST API directly for speed.

