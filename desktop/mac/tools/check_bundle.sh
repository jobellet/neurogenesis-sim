#!/bin/bash
# Checks that an app bundle runs on a clean Mac: every Mach-O inside links only to macOS itself (/usr/lib, /System)
# or to files inside the bundle (@rpath, @loader_path, @executable_path); none to Homebrew, conda, /usr/local or a
# Python.org framework. Then runs the embedded bridge with an empty environment.
#   tools/check_bundle.sh build/Neurogenesis.app
set -euo pipefail
APP="${1:?usage: check_bundle.sh Neurogenesis.app}"
bad=0
while IFS= read -r -d '' f; do
  file -b "$f" | grep -q "Mach-O" || continue
  self="$(otool -D "$f" | tail -n +2 | head -1)"         # a library's own install name is not a dependency
  while read -r dep; do
    [[ "$dep" == "$self" ]] && continue
    case "$dep" in
      /usr/lib/*|/System/*|@rpath/*|@loader_path/*|@executable_path/*) ;;
      *) echo "outside dependency: $f -> $dep"; bad=1 ;;
    esac
  done < <(otool -L "$f" | tail -n +2 | awk '{print $1}')
done < <(find "$APP" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -u+x \) -print0)
PY="$APP/Contents/Resources/python/bin/python3"
[[ -x "$PY" ]] || { echo "no embedded Python in $APP"; exit 1; }
out="$(echo '{"id": 1, "method": "capabilities"}' | env -i HOME="${HOME}" TMPDIR="${TMPDIR:-/tmp}" JAX_PLATFORMS=cpu PYTHONNOUSERSITE=1 "$PY" -m neurogenesis.bridge 2>/dev/null)"
echo "$out" | grep -q '"protocol"' || { echo "the embedded bridge did not answer"; bad=1; }
where="$(env -i HOME="$HOME" "$PY" -c 'import neurogenesis, sys; print(neurogenesis.__file__, sys.prefix)')"
case "$where" in *"$APP"*) ;; *) echo "toolbox imported from outside the bundle: $where"; bad=1 ;; esac
[[ $bad == 0 ]] && echo "bundle ok: no outside dependencies; the embedded bridge answers ($where)"
exit $bad
