#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
desktop_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
desktop_file="$desktop_dir/c200-control.desktop"

mkdir -p "$desktop_dir"
sed "s|@EXEC@|$project_dir/c200-control|" "$project_dir/packaging/c200-control.desktop.in" >"$desktop_file"
chmod +x "$project_dir/c200-control"
command -v update-desktop-database >/dev/null && update-desktop-database "$desktop_dir"

printf 'Installed C200 Control in the application launcher.\n'
