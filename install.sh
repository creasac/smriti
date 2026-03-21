#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.local/share/smriti"
BIN_DIR="${HOME}/.local/bin"
APPLICATIONS_DIR="${HOME}/.local/share/applications"
BASHRC="${HOME}/.bashrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

mkdir -p "${INSTALL_DIR}" "${BIN_DIR}" "${APPLICATIONS_DIR}"

install -m 755 "${SCRIPT_DIR}/recorder.py" "${INSTALL_DIR}/recorder.py"
install -m 755 "${SCRIPT_DIR}/smriti" "${INSTALL_DIR}/smriti"
install -m 644 "${SCRIPT_DIR}/smriti_logo.png" "${INSTALL_DIR}/smriti_logo.png"
ln -sfn "${INSTALL_DIR}/smriti" "${BIN_DIR}/smriti"

cat > "${APPLICATIONS_DIR}/smriti.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=smriti
Comment=Small X11 desktop recorder
Exec=${BIN_DIR}/smriti
Icon=${INSTALL_DIR}/smriti_logo.png
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
    PATH_UPDATED=1
else
    PATH_UPDATED=0
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APPLICATIONS_DIR}" >/dev/null 2>&1 || true
fi

printf "Installed smriti.\n"
printf "Command: %s\n" "${BIN_DIR}/smriti"
printf "Desktop entry: %s\n" "${APPLICATIONS_DIR}/smriti.desktop"

if [[ "${PATH_UPDATED}" -eq 1 ]]; then
    printf "Added ~/.local/bin to ~/.bashrc. Run 'source ~/.bashrc' or open a new shell.\n"
else
    printf "~/.local/bin was already on your PATH configuration.\n"
fi
