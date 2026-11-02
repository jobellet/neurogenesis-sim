# CI runners

The repository is public, so GitHub-hosted runners (Linux, macOS and Windows) are free and are the default. Jobs can
still run on our own machines (self-hosted runners), for example for faster or specific hardware.

## How the workflows choose a runner
Repository variables (Settings → Secrets and variables → Actions → Variables), each a JSON label or list of labels.
Unset means GitHub-hosted.

| Variable | Default | Jobs in `ci.yml` |
|---|---|---|
| `LINUX_RUNNER` | `"ubuntu-latest"` | detect-changes, python, viewer, nglif-ubuntu |
| `MAC_RUNNER` | `"macos-latest"` | nglif-macos, mac-app |
| `WINDOWS_RUNNER` | `"windows-latest"` | nglif-windows |

`release.yml` has its own variables, because a release must be built on the exact OS and architecture it targets:
`RELEASE_LINUX_RUNNER`, `RELEASE_WINDOWS_RUNNER`, `MAC_X64_RUNNER` (Intel) and `MAC_ARM64_RUNNER` (Apple Silicon).

Jobs run only when their files changed (`detect-changes`), or on manual runs (`workflow_dispatch`). On pull requests:
- every job runs on every non-draft PR whose files it covers (Linux, macOS and Windows alike; no label needed);
- draft PRs run the Python tests only;
- macOS and Windows jobs stop after 30 minutes (the macOS app after 45);
- self-hosted runners never run pull requests from forks.

## A Mac as runner
```bash
scripts/setup_macos_runner.sh               # macOS jobs on this Mac
scripts/setup_macos_runner.sh --linux-jobs  # also the Linux jobs (Python tests, viewer, nglif)
scripts/setup_macos_runner.sh --status
scripts/setup_macos_runner.sh --uninstall   # back to GitHub-hosted runners
```
Needs `gh auth login` (repository admin), the Xcode command line tools and CMake. The runner is a launchd service
in `~/actions-runner/neurogenesis-sim`. It runs one job at a time, as your user, while the Mac is awake.

## A Windows PC as runner
Settings → Actions → Runners → New self-hosted runner → Windows. Follow the commands shown, with the label
`neurogenesis`, and install it as a service. Then:
```bash
gh variable set WINDOWS_RUNNER -R jobellet/neurogenesis-sim --body '["self-hosted","Windows","neurogenesis"]'
```
The PC needs Git, CMake, Visual Studio Build Tools (C++), and the .NET 8 SDK for the Avalonia app.

## Security
A self-hosted runner executes the code of every workflow run on that machine. On a public repository anyone can open a
pull request, so the workflows never run fork pull requests on self-hosted runners; hosted runners are free, so the
simplest setup is none: run `--uninstall` and delete the variables.
