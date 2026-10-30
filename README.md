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

1. Clone this repository into `config/custom_components/ssh_command` (create `custom_components` if needed):
   ```sh
   git clone https://github.com/gensyn/ssh_command.git config/custom_components/ssh_command
   ```
2. Restart Home Assistant
3. Add the integration via `Settings > Devices & Services > Add Integration`

---

### 🔧 Service: `ssh_command.execute`

- Domain: `ssh_command`
- Service: `execute`
- The service supports service responses and returns a dictionary with keys: `output`, `error`, `exit_status`.

#### Parameters

- `host` (required) — Hostname or IP address of the remote server
- `port` (default: `22`) — SSH port of the remote server (`1`–`65535`)
- `username` (required) — SSH username
- `password` — SSH password (use instead of key_file)
- `key_file` — Path to an SSH private key file (use instead of password)
- `passphrase` — Passphrase for an encrypted private key file (only valid when `key_file` is used)
- `command` — Command string to execute on the host
- `input` — Input to send to the `stdin` of the host. If this is a file path, the content of the file will be sent.
- `check_known_hosts` (default: `true`) — Verify host key against known hosts
- `known_hosts` — Path to a known_hosts file or OpenSSH-format known_hosts contents (only valid when `check_known_hosts` is `true`)
- `timeout` (default: `30`) — Positive timeout in seconds for SSH connection and command execution

The service schema requires `host` and `username`. It also enforces the authentication, command/input, key-file, and host-verification rules below.

#### Validation rules enforced by the service

- Either `password` or `key_file` must be provided, but not both
- `passphrase` may only be provided when `key_file` is used
- Either `command` or `input` or both must be provided
- If `key_file` is provided, the file must exist on the Home Assistant filesystem
- `known_hosts` may not be provided when `check_known_hosts` is `false`
- `port` must be between `1` and `65535`; `timeout` must be greater than zero

`input` is sent as literal stdin text unless it names an existing file, in which case that file's contents are sent. SSH host-key verification is enabled by default; disabling it removes protection against connecting to an impersonated host and should only be used when you understand that risk.

### Return values

The service response contains:
- `output` — standard output of the remote command
- `error` — standard error of the remote command
- `exit_status` — numeric exit status of the remote command, or `null` if it ended without an exit status

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
  username: myuser
  key_file: /config/ssh/id_rsa
  input: /config/scripts/deploy.sh
  timeout: 60
```

To capture the response in an automation, use a response variable:

```yaml
action:
  - action: ssh_command.execute
    data:
      host: 192.0.2.10
      username: myuser
      password: !secret ssh_password
      command: uptime
    response_variable: ssh_result
```

`ssh_result` contains `output`, `error`, and `exit_status`.

---

## ⚠️ Known issues

- If you are using HassOS and enable `check_known_hosts` without explicitly providing `known_hosts`, this may fail if the default `~/.ssh/known_hosts` file is not available to Home Assistant. Provide a known_hosts file path or OpenSSH-format contents instead. See the [AsyncSSH documentation](https://asyncssh.readthedocs.io/en/stable/api.html#known-hosts) for valid formats.
  - Similar errors might occur in `Docker` installations.

## Removal

Remove **SSH Command** from `Settings > Devices & Services`. If installed manually, delete `config/custom_components/ssh_command` and restart Home Assistant. If installed through HACS, uninstall it there and restart Home Assistant.

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

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/M5G61ZZY8D)
