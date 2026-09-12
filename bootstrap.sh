#!/usr/bin/env bash
set -euo pipefail

# Download only for this installation; no Git checkout is created or retained.
for command in curl tar mktemp; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf '[smriti] Required command not found: %s\n' "$command" >&2
        exit 1
    fi
done

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/smriti-install.XXXXXXXX")"
trap 'rm -rf -- "$temp_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

curl --fail --silent --show-error --location \
    https://codeload.github.com/creasac/smriti/tar.gz/refs/heads/master \
    --output "$temp_dir/source.tar.gz"
mkdir "$temp_dir/source"
tar -xzf "$temp_dir/source.tar.gz" -C "$temp_dir/source" --strip-components=1
bash "$temp_dir/source/install.sh" "$@"
