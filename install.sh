#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
desktop_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
desktop_file="$desktop_dir/c200-control.desktop"
service_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
service_file="$service_dir/c200-control-sync.service"

mkdir -p "$desktop_dir" "$service_dir"
sed "s|@EXEC@|$project_dir/c200-control|" "$project_dir/packaging/c200-control.desktop.in" >"$desktop_file"
sed "s|@PROJECT@|$project_dir|" "$project_dir/packaging/c200-control-sync.service.in" >"$service_file"
chmod +x "$project_dir/c200-control"
command -v update-desktop-database >/dev/null && update-desktop-database "$desktop_dir"
systemctl --user daemon-reload
systemctl --user enable --now c200-control-sync.service
systemctl --user restart c200-control-sync.service

printf 'Installed C200 Control in the application launcher and started settings sync.\n'
