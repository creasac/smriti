#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${HOME}/.local/share/smriti"
BIN_DIR="${HOME}/.local/bin"
APPLICATIONS_DIR="${HOME}/.local/share/applications"
ICON_THEME_DIR="${HOME}/.local/share/icons/hicolor"
BASHRC="${HOME}/.bashrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
PATH_MARKER="${INSTALL_DIR}/.path_modified"

remove_path_block() {
    if [[ ! -f "${BASHRC}" || ! -f "${PATH_MARKER}" ]]; then
        return
    fi

    python3 - "${BASHRC}" "${PATH_LINE}" <<'PY'
from pathlib import Path
import sys

bashrc_path = Path(sys.argv[1])
path_line = sys.argv[2]
comment_line = "# Added by smriti installer"
lines = bashrc_path.read_text().splitlines()
result: list[str] = []
i = 0

while i < len(lines):
    if (
        i + 1 < len(lines)
        and lines[i] == comment_line
        and lines[i + 1] == path_line
    ):
        i += 2
        continue
    result.append(lines[i])
    i += 1

text = "\n".join(result)
if text:
    text += "\n"
bashrc_path.write_text(text)
PY
}

remove_icon_files() {
    local size
    for size in 32 48 64 128 256; do
        rm -f "${ICON_THEME_DIR}/${size}x${size}/apps/smriti.png"
        rmdir "${ICON_THEME_DIR}/${size}x${size}/apps" 2>/dev/null || true
        rmdir "${ICON_THEME_DIR}/${size}x${size}" 2>/dev/null || true
    done
}

if [[ $# -gt 0 ]]; then
    if [[ $# -eq 1 && ( "$1" == --help || "$1" == -h ) ]]; then
        printf 'Usage: smriti-uninstall\nRemoves the application; recordings are always preserved.\n'
        exit 0
    fi
    printf 'Unknown option: %s\n' "$1" >&2
    exit 1
fi

remove_path_block

# Remove only known, user-owned UI scratch files, never recovery recordings.
python3 - <<'PY_CLEANUP'
import os
from pathlib import Path
import tempfile

for directory in {Path("/tmp"), Path(tempfile.gettempdir())}:
    for name in ("smriti_env.log", "smriti_transparent.svg", "smriti_stop_maxed.png"):
        path = directory / name
        try:
            if path.lstat().st_uid == os.getuid():
                path.unlink()
        except FileNotFoundError:
            pass
PY_CLEANUP

rm -f "${BIN_DIR}/smriti" "${BIN_DIR}/smriti-uninstall"
rm -f "${APPLICATIONS_DIR}/smriti.desktop" "${APPLICATIONS_DIR}/smriti-local.desktop"
remove_icon_files
rm -rf "${INSTALL_DIR}"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPLICATIONS_DIR}" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "${ICON_THEME_DIR}" >/dev/null 2>&1 || true
fi

printf "Removed smriti from your local user install. Recordings in ~/Videos/smriti were preserved.\n"
