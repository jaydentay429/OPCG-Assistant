#!/usr/bin/env bash
# Poll a URL until it returns HTTP 200.
# Usage: wait-http.sh URL SYSTEMD_UNIT [ATTEMPTS]
# ATTEMPTS defaults to 60. One try per second (the probe itself is capped at 2s).
# On timeout, print `journalctl -u SYSTEMD_UNIT -n 50` and exit 1.
set -euo pipefail

url="${1:?url required}"
unit="${2:?systemd unit required}"
attempts="${3:-60}"

if ! [[ "$attempts" =~ ^[0-9]+$ ]] || [[ "$attempts" -lt 1 ]]; then
  echo "attempts must be a positive integer" >&2
  exit 1
fi

probe() {
  python3 - "$1" << 'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


opener = urllib.request.build_opener(NoRedirect)
try:
    with opener.open(url, timeout=2) as resp:
        print(resp.status)
except urllib.error.HTTPError as exc:
    print(exc.code)
except Exception:
    print("000")
PY
}

for ((i = 1; i <= attempts; i++)); do
  code="$(probe "$url")"
  if [[ "$code" == "200" ]]; then
    echo "ready: $unit $url -> 200 (attempt ${i}/${attempts})"
    exit 0
  fi
  echo "waiting: $unit $url -> ${code} (attempt ${i}/${attempts})"
  if [[ "$i" -lt "$attempts" ]]; then
    sleep 1
  fi
done

echo "timed out after ${attempts} attempts waiting for $url to return 200" >&2
journalctl -u "$unit" -n 50 --no-pager || true
exit 1
