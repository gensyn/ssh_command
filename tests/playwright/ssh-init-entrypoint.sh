#!/bin/sh
# SSH test server startup script.
#
# If the /ssh-init-data directory is mounted (a shared volume also mounted
# read-only into the HA container at /ssh-test-keys), this script writes two
# files into it before starting sshd:
#
#   id_ed25519   — the test user's ed25519 private key (generated at image
#                  build time); lets the HA integration connect with
#                  key_file="/ssh-test-keys/id_ed25519" in tests.
#
#   known_hosts  — one line in OpenSSH known_hosts format containing this
#                  container's ed25519 host public key; used by tests that
#                  set check_known_hosts=True and known_hosts="/ssh-test-keys/known_hosts".
#
# The container name is injected by docker-compose via the CONTAINER_NAME
# environment variable and is used as the hostname in the known_hosts line.

set -e

if [ -d /ssh-init-data ]; then
    printf '[ssh-init] Populating /ssh-init-data/ ...\n'

    # User auth private key (generated at image build time, same across all
    # containers that share this image).
    cp /home/foo/.ssh/id_ed25519 /ssh-init-data/id_ed25519
    chmod 644 /ssh-init-data/id_ed25519

    # known_hosts line: <hostname> <algorithm> <base64-key>
    HOST="${CONTAINER_NAME:-$(hostname)}"
    awk -v h="${HOST}" '{print h " " $1 " " $2}' \
        /etc/ssh/ssh_host_ed25519_key.pub > /ssh-init-data/known_hosts

    printf '[ssh-init] Done (host=%s).\n' "${HOST}"
fi

exec /usr/sbin/sshd -D
