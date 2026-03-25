#!/bin/sh
# ha-init-wrapper.sh — pre-populates /etc/hosts before handing off to the
# real Home Assistant init script (/init).
#
# Alpine Linux (musl libc) cannot resolve Docker container hostnames via
# Python's socket module because musl's DNS resolver fails against Docker's
# embedded DNS server (127.0.0.11) in some CI environments, even though
# busybox's nslookup (which makes direct UDP queries) works fine.
#
# By adding /etc/hosts entries via nslookup first, Python's resolver uses the
# "files" path from nsswitch.conf and succeeds without touching DNS at all.

set -u

add_host() {
    local name="$1"
    local ip
    ip=$(nslookup "$name" 127.0.0.11 2>/dev/null | sed -n 's/^Address: //p' | tail -1)
    if [ -n "$ip" ]; then
        # Avoid duplicate entries on container restart
        if ! grep -q " $name" /etc/hosts 2>/dev/null; then
            printf '%s\t%s\n' "$ip" "$name" >> /etc/hosts
            echo "[ha-init-wrapper] Added /etc/hosts entry: $ip $name"
        fi
    else
        echo "[ha-init-wrapper] WARNING: could not resolve $name via nslookup"
    fi
}

for host in ssh_docker_test_1 ssh_docker_test_2; do
    add_host "$host"
done

# Hand off to the original HA init process
exec /init
