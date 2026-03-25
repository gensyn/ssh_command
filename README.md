# 🔐 SSH command

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/gensyn/ssh_command.svg)](https://github.com/gensyn/ssh_command/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Minimal Home Assistant custom component that exposes a single service to execute commands on remote hosts over SSH: `ssh_command.execute`.

This integration does not create devices or entities. It only registers the `ssh_command.execute` service.

---

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gensyn&repository=ssh_command&category=integration)

1. Click the badge above or search for **SSH Command** in HACS
2. Click **Download**
3. Restart Home Assistant
4. Add the integration via `Settings > Devices & Services > Add Integration`

### Manual Installation

1. Download or clone this repository
2. Copy the `ssh_command` folder to your Home Assistant `config/custom_components` directory
3. Restart Home Assistant
4. Add the integration via `Settings > Devices & Services > Add Integration`

---

### 🔧 Service: `ssh_command.execute`

- Domain: `ssh_command`
- Service: `execute`
- The service supports service responses and returns a dictionary with keys: `output`, `error`, `exit_status`.

#### Parameters

- `host` (required) — Hostname or IP address of the remote server
- `username` (required) — SSH username
- `password` — SSH password (use instead of key_file)
- `key_file` — Path to an SSH private key file (use instead of password)
- `command` — Command string to execute on the host
- `input` — Input to send to the `stdin` of the host. If this is a file path, the content of the file will be sent.
- `check_known_hosts` (default: `true`) — Verify host key against known hosts
- `known_hosts` — Path or string of the known hosts (only valid when `check_known_hosts` is `true`)
- `timeout` (default: `30`) — Timeout in seconds for the SSH command execution

All parameters are optional in the raw schema except `host` and `username` — the service enforces required combinations and file existence checks described below.

#### Validation rules enforced by the service

- Either `password` or `key_file` must be provided, but not both
- Either `command` or `input` or both must be provided
- If `key_file` is provided, the file must exist on the Home Assistant filesystem
- `known_hosts` may not be provided when `check_known_hosts` is `false`

### Return values

The service returns:
- `output` — standard output of the remote command
- `error` — standard error of the remote command
- `exit_status` — numeric exit status of the remote command

### Example: run a simple command

```yaml
service: ssh_command.execute
data:
  host: 192.0.2.10
  username: myuser
  password: mypassword
  command: uptime
```

### Example: run a local script file

```yaml
service: ssh_command.execute
data:
  host: example.local
  key_file: /config/ssh/id_rsa
  input: /config/scripts/deploy.sh
  timeout: 60
```

To capture the response in automations that support service responses, use the platform's service response features (the result contains `output`, `error`, `exit_status`).

---

## ⚠️ Known issues

- If you are using HassOS and enable `check_known_hosts` without explicitly providing `known_hosts`, this will probably fail with an error that the `known_hosts` file can not be found, as the file might not be accessible from within Home Assistant. Either disable host checking (not recommended), or provide `known_hosts` explicitly. See the [asyncssh Documentation](https://asyncssh.readthedocs.io/en/stable/api.html#known-hosts) for valid formats.
  - Similar errors might occur in `Docker` installations.

## 🚧 Future Development

Have ideas or feature requests? I'm open to suggestions!

- 🌍 **Additional Translations** - Community contributions welcome for your language
- 🎯 **Your Ideas** - Open an issue to suggest new features! 

---

## 🤝 Contributing

Contributions are welcome! Feel free to: 
- 🐛 Report bugs via [Issues](https://github.com/gensyn/ssh_command/issues)
- 💡 Suggest features
- 🌐 Contribute translations
- 📝 Improve documentation

---

## 📄 License

This project is licensed under the terms specified in the [MIT License](https://mit-license.org/).

---

## ⭐ Support

If you find SSH Command useful, please consider giving it a star on GitHub! It helps others discover the project. 