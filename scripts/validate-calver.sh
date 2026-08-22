#!/usr/bin/env bash
# validate-calver.sh — Validate a CalVer release tag of the form vYYYY.MM.DD
#
# Usage: validate-calver.sh <tag>
#   tag  Must match vYYYY.MM.DD and represent a real calendar date.
#
# Exits 0 on success; writes a concise message to stderr and exits non-zero on
# any validation failure.  Compatible with Bash 3.2+.
set -euo pipefail

# ---------------------------------------------------------------------------
# Usage guard
# ---------------------------------------------------------------------------
if [ "${1-}" = "" ]; then
    echo "Usage: $(basename "$0") vYYYY.MM.DD" >&2
    exit 1
fi

TAG="$1"

# ---------------------------------------------------------------------------
# Format check: must be vYYYY.MM.DD with all-digit components
# ---------------------------------------------------------------------------
case "$TAG" in
    v[0-9][0-9][0-9][0-9].[0-9][0-9].[0-9][0-9]) ;;  # pattern matches
    *)
        echo "error: tag '${TAG}' is not in vYYYY.MM.DD format" >&2
        exit 1
        ;;
esac

# Strip the leading 'v' and split on '.'
BARE="${TAG#v}"
YEAR="${BARE%%.*}"
REST="${BARE#*.}"
MONTH="${REST%%.*}"
DAY="${REST#*.}"

# ---------------------------------------------------------------------------
# Numeric range checks (Bash 3.2 compatible — no [[ ]] arithmetic needed)
# ---------------------------------------------------------------------------
# Remove leading zeros so the shell arithmetic doesn't treat them as octal
YEAR_N=$((10#$YEAR))
MONTH_N=$((10#$MONTH))
DAY_N=$((10#$DAY))

if [ "$MONTH_N" -lt 1 ] || [ "$MONTH_N" -gt 12 ]; then
    echo "error: month ${MONTH_N} is out of range (1–12)" >&2
    exit 1
fi

if [ "$DAY_N" -lt 1 ] || [ "$DAY_N" -gt 31 ]; then
    echo "error: day ${DAY_N} is out of range (1–31)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Calendar validity via python3
# ---------------------------------------------------------------------------
if ! command -v python3 > /dev/null 2>&1; then
    echo "error: python3 is required for date validation but was not found" >&2
    exit 1
fi

python3 - "$YEAR_N" "$MONTH_N" "$DAY_N" <<'PYEOF'
import sys
import datetime
year, month, day = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
try:
    datetime.date(year, month, day)
except ValueError as exc:
    print(f"error: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo "ok: ${TAG} is a valid CalVer tag"
