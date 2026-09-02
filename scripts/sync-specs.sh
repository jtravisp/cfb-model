#!/usr/bin/env bash
#
# Refresh the read-only SPEC copies in docs/reference/ from the upstream repo.
#
# The specs are authored in travispollard.com/cfb/docs/ and that copy governs
# (docs/PRD.md: "SPEC-phase2.md ... supplies all substance"). The copies here
# exist so research can read them offline, and they carry a header naming the
# commit they were taken at.
#
# **They drifted because nothing prompted the update.** The first sync happened
# by hand at bootstrap and pinned commit 46a9421; by the time Phase 2 shipped,
# the copy of SPEC-phase2 was 77 lines behind and still said ELO_PER_POINT was
# 20. The pin header made that discoverable, which is what it is for -- but only
# for someone who went looking. This script is the thing that prompts it.
#
# Usage:
#   scripts/sync-specs.sh                    # default upstream: ../travispollard.com
#   scripts/sync-specs.sh /path/to/repo
#   CHECK=1 scripts/sync-specs.sh            # report drift, change nothing, exit 1 if stale
#
set -euo pipefail

UPSTREAM="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/travispollard.com}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$UPSTREAM/cfb/docs"
DEST="$HERE/docs/reference"
CHECK="${CHECK:-}"

if [ ! -d "$SRC" ]; then
  echo "error: no spec directory at $SRC" >&2
  echo "       pass the upstream repo path: scripts/sync-specs.sh /path/to/travispollard.com" >&2
  exit 2
fi

# The commit the copies are taken at. Read from the upstream working tree rather
# than assumed, and refused if that tree is dirty -- a copy pinned to a commit
# whose files have uncommitted edits is pinned to nothing.
COMMIT="$(git -C "$UPSTREAM" rev-parse HEAD)"
if [ -n "$(git -C "$UPSTREAM" status --porcelain -- cfb/docs)" ]; then
  echo "error: $UPSTREAM has uncommitted changes under cfb/docs" >&2
  echo "       commit them first, or the pin below would name a commit that does not" >&2
  echo "       contain what was copied" >&2
  exit 2
fi

mkdir -p "$DEST"
stale=0

for path in "$SRC"/SPEC-phase*.md; do
  name="$(basename "$path")"
  target="$DEST/$name"

  tmp="$(mktemp)"
  {
    printf '> **Note:** Read-only reference copy from `travispollard.com` at commit `%s`. ' "$COMMIT"
    printf 'The original file in `travispollard.com/cfb/docs/` governs.\n\n'
    cat "$path"
  } > "$tmp"

  if [ -f "$target" ] && cmp -s "$tmp" "$target"; then
    printf '  %-18s up to date\n' "$name"
    rm -f "$tmp"
    continue
  fi

  stale=1
  if [ -n "$CHECK" ]; then
    printf '  %-18s STALE\n' "$name"
    rm -f "$tmp"
  else
    mv "$tmp" "$target"
    printf '  %-18s synced\n' "$name"
  fi
done

echo
if [ -n "$CHECK" ]; then
  if [ "$stale" -eq 1 ]; then
    echo "reference copies are behind $UPSTREAM @ ${COMMIT:0:7}; run scripts/sync-specs.sh"
    exit 1
  fi
  echo "reference copies match $UPSTREAM @ ${COMMIT:0:7}"
else
  echo "pinned to $UPSTREAM @ ${COMMIT:0:7}"
fi
