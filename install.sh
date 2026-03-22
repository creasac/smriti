#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.local/share/smriti"
BIN_DIR="${HOME}/.local/bin"
APPLICATIONS_DIR="${HOME}/.local/share/applications"
ICON_THEME_DIR="${HOME}/.local/share/icons/hicolor"
BASHRC="${HOME}/.bashrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
PATH_MARKER="${INSTALL_DIR}/.path_modified"

mkdir -p "${INSTALL_DIR}" "${INSTALL_DIR}/assets" "${BIN_DIR}" "${APPLICATIONS_DIR}"

install -m 755 "${SCRIPT_DIR}/recorder.py" "${INSTALL_DIR}/recorder.py"
install -m 755 "${SCRIPT_DIR}/smriti" "${INSTALL_DIR}/smriti"
install -m 755 "${SCRIPT_DIR}/uninstall.sh" "${INSTALL_DIR}/uninstall.sh"
install -m 644 "${SCRIPT_DIR}/assets/"*.png "${INSTALL_DIR}/assets/"
ln -sfn "${INSTALL_DIR}/smriti" "${BIN_DIR}/smriti"
ln -sfn "${INSTALL_DIR}/uninstall.sh" "${BIN_DIR}/smriti-uninstall"

python3 - "${SCRIPT_DIR}/assets/smriti_logo.png" "${ICON_THEME_DIR}" <<'PY'
from pathlib import Path
import sys

try:
    from PIL import Image
except ImportError:
    Image = None

source = Path(sys.argv[1])
theme_dir = Path(sys.argv[2])

if Image is None:
    output_dir = theme_dir / "256x256" / "apps"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.joinpath("smriti.png").write_bytes(source.read_bytes())
else:
    sizes = (32, 48, 64, 128, 256)
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
        for size in sizes:
            output_dir = theme_dir / f"{size}x{size}" / "apps"
            output_dir.mkdir(parents=True, exist_ok=True)
            resized = rgba.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(output_dir / "smriti.png")
PY

cat > "${APPLICATIONS_DIR}/smriti.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=smriti
Comment=Small X11 desktop recorder
Exec=${BIN_DIR}/smriti
Icon=smriti
StartupWMClass=smriti
Terminal=false
Categories=AudioVideo;Utility;
StartupNotify=true
EOF

if [[ ! -f "${BASHRC}" ]]; then
    touch "${BASHRC}"
fi

if ! grep -Fqx "${PATH_LINE}" "${BASHRC}"; then
    {
        printf "\n# Added by smriti installer\n"
        printf "%s\n" "${PATH_LINE}"
    } >> "${BASHRC}"
    touch "${PATH_MARKER}"
    PATH_UPDATED=1
else
    rm -f "${PATH_MARKER}"
    PATH_UPDATED=0
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPLICATIONS_DIR}" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "${ICON_THEME_DIR}" >/dev/null 2>&1 || true
fi

printf "Installed smriti.\n"
printf "Command: %s\n" "${BIN_DIR}/smriti"
printf "Uninstall: %s\n" "${BIN_DIR}/smriti-uninstall"
printf "Desktop entry: %s\n" "${APPLICATIONS_DIR}/smriti.desktop"

if [[ "${PATH_UPDATED}" -eq 1 ]]; then
    printf "Added ~/.local/bin to ~/.bashrc. Run 'source ~/.bashrc' or open a new shell.\n"
else
    printf "~/.local/bin was already on your PATH configuration.\n"
fi
