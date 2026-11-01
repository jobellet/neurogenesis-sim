# CI runners

GitHub-hosted minutes are limited on a private repository, and macOS minutes count 10×, Windows 2×. Jobs can run on
our own machines instead (self-hosted runners), which use no minutes.

## How the workflows choose a runner
Repository variables (Settings → Secrets and variables → Actions → Variables), each a JSON label or list of labels.
Unset means GitHub-hosted.

| Variable | Default | Jobs in `ci.yml` |
|---|---|---|
| `LINUX_RUNNER` | `"ubuntu-latest"` | detect-changes, python, viewer, nglif-ubuntu |
| `MAC_RUNNER` | `"macos-latest"` | nglif-macos, mac-app |
| `WINDOWS_RUNNER` | `"windows-latest"` | nglif-windows |

Jobs run only when their files changed (`detect-changes`), or on manual runs (`workflow_dispatch`). On pull requests:
- macOS and Windows jobs run on a self-hosted runner, or on hosted runners only with the label `full-ci`;
- draft PRs run the Python tests only;
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
A self-hosted runner executes the code of every workflow run on that machine. Keep self-hosted runners for the
private phase. When the repository becomes public, hosted runners are free: run `--uninstall` and delete the
variables.
