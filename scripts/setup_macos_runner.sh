#!/usr/bin/env bash
# Install a self-hosted GitHub Actions runner for this repository on a Mac, as a background service (launchd), and
# point the macOS CI jobs at it. Self-hosted runners use no GitHub Actions minutes.
#
#   scripts/setup_macos_runner.sh                 install, register, start, set the MAC_RUNNER repository variable
#   scripts/setup_macos_runner.sh --linux-jobs    also run the Linux jobs (Python tests, viewer, nglif) on this Mac
#   scripts/setup_macos_runner.sh --status        show the service and the repository variables
#   scripts/setup_macos_runner.sh --uninstall     stop, unregister, remove, unset the variables
#
# Needs: the GitHub CLI logged in as a repository admin (gh auth login), the Xcode command line tools
# (xcode-select --install) and CMake (brew install cmake). Python and Node are provided per job by setup-python /
# setup-node. The runner lives in ~/actions-runner/neurogenesis-sim and runs jobs as your user, one at a time.
# Only use it while the repository is private, or with fork pull requests disabled: CI code from a pull request runs
# on this Mac. The workflows already refuse to run pull requests from forks on self-hosted runners.
set -euo pipefail

REPO="${NG_RUNNER_REPO:-jobellet/neurogenesis-sim}"
DIR="${NG_RUNNER_DIR:-$HOME/actions-runner/neurogenesis-sim}"
NAME="${NG_RUNNER_NAME:-$(scutil --get LocalHostName 2>/dev/null || hostname -s)-neurogenesis}"
LABELS="neurogenesis"
MAC_RUNNER='["self-hosted","macOS","neurogenesis"]'

die() { echo "error: $*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "this script is for macOS"
command -v gh >/dev/null || die "the GitHub CLI is missing: brew install gh, then gh auth login"
gh auth status >/dev/null 2>&1 || die "gh is not logged in: gh auth login"

case "${1:-}" in
  --status)
    if [[ -d "$DIR" ]]; then (cd "$DIR" && ./svc.sh status) || true; else echo "no runner in $DIR"; fi
    gh variable list -R "$REPO"
    exit 0 ;;
  --uninstall)
    if [[ -d "$DIR" ]]; then
      cd "$DIR"
      ./svc.sh stop || true
      ./svc.sh uninstall || true
      token=$(gh api -X POST "repos/$REPO/actions/runners/remove-token" --jq .token)
      ./config.sh remove --token "$token" || true
      cd "$HOME" && rm -rf "$DIR"
    fi
    gh variable delete MAC_RUNNER -R "$REPO" 2>/dev/null || true
    gh variable delete LINUX_RUNNER -R "$REPO" 2>/dev/null || true
    echo "removed; CI uses GitHub-hosted runners again"
    exit 0 ;;
  --linux-jobs|"") ;;
  *) die "unknown option $1 (see the header of this script)" ;;
esac

xcode-select -p >/dev/null 2>&1 || die "the Xcode command line tools are missing: xcode-select --install"
command -v swiftc >/dev/null || die "swiftc not found (Xcode command line tools)"
command -v cmake >/dev/null || die "cmake not found: brew install cmake"

case "$(uname -m)" in
  arm64) ARCH=osx-arm64 ;;
  x86_64) ARCH=osx-x64 ;;
  *) die "unsupported architecture $(uname -m)" ;;
esac

if [[ -f "$DIR/.runner" ]]; then
  echo "a runner is already configured in $DIR (use --uninstall first to reinstall)"
else
  echo "Latest actions/runner release…"
  version=$(gh api repos/actions/runner/releases/latest --jq .tag_name | sed 's/^v//')
  sha=$(gh api repos/actions/runner/releases/latest --jq .body | sed -n "s/.*<!-- BEGIN SHA $ARCH -->\([0-9a-f]\{64\}\)<!-- END SHA $ARCH -->.*/\1/p" | head -1)
  [[ -n "$sha" ]] || die "could not read the SHA-256 of the $ARCH package from the release notes; install by hand from Settings > Actions > Runners"
  tarball="actions-runner-$ARCH-$version.tar.gz"

  mkdir -p "$DIR" && cd "$DIR"
  echo "Downloading $tarball…"
  curl -fsSL -o "$tarball" "https://github.com/actions/runner/releases/download/v$version/$tarball"
  echo "$sha  $tarball" | shasum -a 256 -c - || die "checksum mismatch for $tarball"
  tar xzf "$tarball" && rm "$tarball"

  token=$(gh api -X POST "repos/$REPO/actions/runners/registration-token" --jq .token)
  ./config.sh --unattended --url "https://github.com/$REPO" --token "$token" --name "$NAME" --labels "$LABELS" --replace
fi

cd "$DIR"
./svc.sh install >/dev/null 2>&1 || true
./svc.sh start
./svc.sh status | tail -3

gh variable set MAC_RUNNER -R "$REPO" --body "$MAC_RUNNER"
if [[ "${1:-}" == "--linux-jobs" ]]; then
  gh variable set LINUX_RUNNER -R "$REPO" --body "$MAC_RUNNER"
fi
echo
echo "Runner '$NAME' installed in $DIR and running."
echo "CI now sends macOS jobs$([[ "${1:-}" == "--linux-jobs" ]] && echo " and Linux jobs") to this Mac (repository variables):"
gh variable list -R "$REPO"
echo "Check it on https://github.com/$REPO/settings/actions/runners (status: Idle)."
