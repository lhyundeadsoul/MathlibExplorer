#!/usr/bin/env bash
# One-command launcher for macOS / Linux.
#
# Usage:
#   ./run.sh 2d   - launch the original bgfx import-graph explorer
#   ./run.sh 3d   - launch the 3D "mathematical kingdom" map

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"

usage() {
  echo "Usage: ./run.sh [2d|3d]" >&2
  echo "  2d - launch the original bgfx import-graph explorer" >&2
  echo "  3d - launch the 3D \"mathematical kingdom\" map" >&2
  exit 1
}

run_2d() {
  local OS BIN_DIR
  OS="$(uname -s)"
  case "$OS" in
    Darwin) BIN_DIR="$DIR/release/bin_osx" ;;
    Linux)  BIN_DIR="$DIR/release/bin_linux" ;;
    *)
      echo "Unsupported OS: $OS" >&2
      exit 1
      ;;
  esac
  if [ ! -d "$BIN_DIR" ]; then
    available="$(cd "$DIR/release" && ls -d bin_* 2>/dev/null | tr '\n' ' ')"
    echo "No prebuilt MathlibExplorer binary for $OS yet." >&2
    echo "Available platform builds: ${available:-none}" >&2
    if [ "$OS" = "Linux" ]; then
      echo "There is currently no Linux build in this repo (only macOS and Windows are published)." >&2
    fi
    exit 1
  fi
  local EXE="$BIN_DIR/MathlibExplorer"
  [ -x "$EXE" ] || chmod +x "$EXE"
  cd "$BIN_DIR"
  exec "./MathlibExplorer"
}

run_3d() {
  local HTML="$DIR/kingdom/viewer/index.html"
  if [ ! -f "$HTML" ]; then
    echo "No 3D viewer found at $HTML" >&2
    exit 1
  fi
  local URL="file://$HTML"

  # Prefer an "app mode" window (no tabs/address bar) for a closer-to-native
  # feel matching the bgfx MathlibExplorer window; fall back to whatever the
  # system's default browser association is.
  if [ "$(uname -s)" = "Darwin" ]; then
    if [ -d "/Applications/Google Chrome.app" ]; then
      open -na "Google Chrome" --args --app="$URL"
      return
    fi
    if [ -d "/Applications/Microsoft Edge.app" ]; then
      open -na "Microsoft Edge" --args --app="$URL"
      return
    fi
    open "$HTML"
    return
  fi

  for b in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge; do
    if command -v "$b" >/dev/null 2>&1; then
      "$b" --app="$URL" >/dev/null 2>&1 &
      return
    fi
  done

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$HTML"
  else
    echo "Could not find a way to open a browser automatically." >&2
    echo "Please open this file manually: $HTML" >&2
    exit 1
  fi
}

case "$MODE" in
  2d) run_2d ;;
  3d) run_3d ;;
  *) usage ;;
esac
