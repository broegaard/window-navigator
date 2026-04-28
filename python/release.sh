#!/usr/bin/env bash
# Usage: ./release.sh [major|minor|patch|<version>]
# Defaults to patch bump. Pass an explicit version like "1.2.3" to pin it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BUMP="${1:-patch}"

# ── helpers ────────────────────────────────────────────────────────────────────

die() { echo "error: $*" >&2; exit 1; }

require() {
    for cmd in "$@"; do
        command -v "$cmd" &>/dev/null || die "'$cmd' not found on PATH"
    done
}

# ── preflight ──────────────────────────────────────────────────────────────────

require python3 gh git

# build is a runtime dep only needed here; check separately so the error is clear
python3 -c "import build" 2>/dev/null || die "'build' not installed — run: pip install build"

if [[ -n "$(git status --porcelain)" ]]; then
    die "working tree is dirty — commit or stash changes first"
fi

# ── compute new version ────────────────────────────────────────────────────────

CURRENT=$(python3 - <<'EOF'
import re, pathlib
text = pathlib.Path("pyproject.toml").read_text()
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
print(m.group(1))
EOF
)

if [[ "$BUMP" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    NEW_VERSION="$BUMP"
else
    NEW_VERSION=$(python3 - "$CURRENT" "$BUMP" <<'EOF'
import sys
ver, part = sys.argv[1], sys.argv[2]
major, minor, patch = map(int, ver.split("."))
if part == "major":   major += 1; minor = 0; patch = 0
elif part == "minor": minor += 1; patch = 0
elif part == "patch": patch += 1
else: sys.exit(f"unknown bump '{part}' — use major, minor, patch, or an explicit x.y.z")
print(f"{major}.{minor}.{patch}")
EOF
    )
fi

echo "releasing $CURRENT → $NEW_VERSION"

# ── quality gates ──────────────────────────────────────────────────────────────

echo "--- lint"
python3 -m ruff check .

echo "--- tests"
python3 -m pytest -q

# ── bump version in pyproject.toml ─────────────────────────────────────────────

python3 - "$CURRENT" "$NEW_VERSION" <<'EOF'
import sys, pathlib, re
old, new = sys.argv[1], sys.argv[2]
p = pathlib.Path("pyproject.toml")
text = p.read_text()
updated = re.sub(
    r'^(version\s*=\s*)"[^"]+"',
    rf'\g<1>"{new}"',
    text,
    count=1,
    flags=re.MULTILINE,
)
assert updated != text, "version line not found in pyproject.toml"
p.write_text(updated)
EOF

echo "bumped pyproject.toml to $NEW_VERSION"

# ── build wheel + sdist ────────────────────────────────────────────────────────

rm -rf dist/
python3 -m build
WHEEL=$(ls dist/*.whl)
SDIST=$(ls dist/*.tar.gz)

echo "built: $WHEEL"
echo "built: $SDIST"

# ── commit + tag ───────────────────────────────────────────────────────────────

git add pyproject.toml
git commit -m "chore: release v${NEW_VERSION}"
git tag "v${NEW_VERSION}"
git push origin HEAD "v${NEW_VERSION}"

echo "pushed tag v${NEW_VERSION}"

# ── github release ─────────────────────────────────────────────────────────────

gh release create "v${NEW_VERSION}" \
    --title "v${NEW_VERSION}" \
    --generate-notes \
    "$WHEEL" \
    "$SDIST"

echo "done — https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/v${NEW_VERSION}"
