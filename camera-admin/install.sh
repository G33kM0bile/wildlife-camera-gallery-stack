#!/bin/bash
set -euo pipefail

readonly SOURCE_DIR=${1:-/tmp/viltkamera-camera-admin}
readonly APP_DIR=/opt/viltkamera-camera-admin
readonly CONFIG_DIR=/etc/viltkamera-metadata
readonly CONFIG_FILE=$CONFIG_DIR/cameras.json
readonly CONFIG_GROUP=viltkamera-config
readonly APP_USER=viltkamera-admin

for required in app.py viltkamera-metadata.py viltkamera-camera-admin.service config/cameras.json static/index.html static/styles.css static/app.js static/vendor/leaflet/leaflet.css static/vendor/leaflet/leaflet.js; do
  test -f "$SOURCE_DIR/$required"
done

/usr/bin/python3 -m py_compile "$SOURCE_DIR/app.py" "$SOURCE_DIR/viltkamera-metadata.py"

if ! getent group "$CONFIG_GROUP" >/dev/null; then
  groupadd --system "$CONFIG_GROUP"
fi
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --gid "$CONFIG_GROUP" --home-dir /nonexistent --shell /usr/sbin/nologin "$APP_USER"
fi
usermod --append --groups "$CONFIG_GROUP" sftpgo

install -d -o root -g root -m 0755 "$APP_DIR" "$APP_DIR/static" "$APP_DIR/static/vendor" "$APP_DIR/static/vendor/leaflet" "$APP_DIR/static/vendor/leaflet/images"
install -o root -g root -m 0644 "$SOURCE_DIR/app.py" "$APP_DIR/app.py"
install -o root -g root -m 0644 "$SOURCE_DIR/static/index.html" "$APP_DIR/static/index.html"
install -o root -g root -m 0644 "$SOURCE_DIR/static/styles.css" "$APP_DIR/static/styles.css"
install -o root -g root -m 0644 "$SOURCE_DIR/static/app.js" "$APP_DIR/static/app.js"
install -o root -g root -m 0644 "$SOURCE_DIR/static/vendor/leaflet/leaflet.css" "$APP_DIR/static/vendor/leaflet/leaflet.css"
install -o root -g root -m 0644 "$SOURCE_DIR/static/vendor/leaflet/leaflet.js" "$APP_DIR/static/vendor/leaflet/leaflet.js"
for image in "$SOURCE_DIR"/static/vendor/leaflet/images/*; do
  install -o root -g root -m 0644 "$image" "$APP_DIR/static/vendor/leaflet/images/$(basename "$image")"
done

install -d -o root -g "$CONFIG_GROUP" -m 2770 "$CONFIG_DIR"
install -d -o "$APP_USER" -g "$CONFIG_GROUP" -m 2770 "$CONFIG_DIR/history"
if [[ ! -e "$CONFIG_FILE" ]]; then
  install -o root -g "$CONFIG_GROUP" -m 0660 "$SOURCE_DIR/config/cameras.json" "$CONFIG_FILE"
else
  chgrp "$CONFIG_GROUP" "$CONFIG_FILE"
  chmod 0660 "$CONFIG_FILE"
fi

if [[ -f /usr/local/sbin/viltkamera-metadata && ! -e /usr/local/sbin/viltkamera-metadata.pre-webgui-20260826 ]]; then
  cp --preserve=all /usr/local/sbin/viltkamera-metadata /usr/local/sbin/viltkamera-metadata.pre-webgui-20260826
fi
install -o root -g root -m 0755 "$SOURCE_DIR/viltkamera-metadata.py" /usr/local/sbin/viltkamera-metadata
install -o root -g root -m 0644 "$SOURCE_DIR/viltkamera-camera-admin.service" /etc/systemd/system/viltkamera-camera-admin.service

systemctl daemon-reload
systemctl restart viltkamera-metadata.service
systemctl enable viltkamera-camera-admin.service
systemctl restart viltkamera-camera-admin.service
