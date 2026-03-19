# SSH Command Playwright E2E Tests

End-to-end tests for the **SSH Command** Home Assistant custom component using
[Playwright](https://playwright.dev/python/).

## Prerequisites

- Python 3.11+
- A running Home Assistant instance (default: `http://homeassistant:8123`)
- Two SSH test servers accessible at:
  - `ssh_docker_test:2222` (user: `foo`, password: `pass`)
  - `ssh_docker_test:2223` (user: `foo`, password: `pass`)

The SSH test servers and Home Assistant are provided by the `docker-compose.yaml`
in the repository root.

## Quick Start

```bash
# 1. Start the test environment
docker-compose up -d

# 2. Wait for Home Assistant to complete its first-run setup, then create an
#    admin account (username: admin, password: admin) or set HA_USERNAME/HA_PASSWORD.

# 3. Install the SSH Command custom component into Home Assistant:
docker cp . homeassistant_test:/config/custom_components/ssh_command

# 4. Restart Home Assistant so it loads the component:
docker-compose restart homeassistant

# 5. Install Python dependencies:
pip install -r tests/playwright/requirements.txt

# 6. Install the Playwright browser:
playwright install chromium

# 7. Run all tests:
pytest tests/playwright/
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HOMEASSISTANT_URL` | `http://homeassistant:8123` | Home Assistant base URL |
| `SSH_HOST` | `ssh_docker_test` | Hostname of the SSH test servers |
| `SSH_PORT_1` | `2222` | Port for SSH Test Server 1 |
| `SSH_PORT_2` | `2223` | Port for SSH Test Server 2 |
| `SSH_USER` | `foo` | SSH username |
| `SSH_PASSWORD` | `pass` | SSH password |
| `HA_USERNAME` | `admin` | Home Assistant admin username |
| `HA_PASSWORD` | `admin` | Home Assistant admin password |

## Running on a Local Machine (outside Docker)

```bash
export HOMEASSISTANT_URL=http://localhost:8123
export SSH_HOST=localhost
export SSH_PORT_1=2222
export SSH_PORT_2=2223
export HA_USERNAME=admin
export HA_PASSWORD=admin

pytest tests/playwright/ -v
```

## Test Modules

| File | What it tests |
|---|---|
| `test_integration_setup.py` | Adding/removing the integration via the config flow |
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
| `ensure_integration` | function | Ensures SSH Command is set up; tears down after test |

## Notes

- Tests are designed to be **idempotent** – each test cleans up after itself.
- Tests do **not** depend on each other.
- Browser-based tests use a headless Chromium instance.
- API-based tests call Home Assistant's REST API directly for speed and reliability.
