#!/bin/sh
set -e
# Create system user if it doesn't exist
if ! getent passwd glean >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin glean
fi
mkdir -p /var/lib/glean /etc/glean
chown glean:glean /var/lib/glean
systemctl daemon-reload || true
echo "glean installed. Edit /etc/glean/feeds.yaml, then: systemctl enable --now glean"