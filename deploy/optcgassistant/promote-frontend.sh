#!/usr/bin/env bash
# Point the live Next.js tree at a staged release without deleting the
# running process's files first.
#
# Usage: promote-frontend.sh RELEASE_ID
#   OPCG_APP_ROOT  defaults to /opt/opcg/app (tests override this)
#
# Expects a finished build at:
#   $OPCG_APP_ROOT/frontend/.next/releases/RELEASE_ID/standalone/server.js
#
# The previous release's /_next/static files are copied in only when the new
# build does not already have them, and only for one generation (the previous
# release's own build, not chunks that release itself inherited). Then
# frontend/.next/standalone and frontend/.next/static become symlinks to the
# new release. Older releases are removed; the previous one is kept for rollback.
set -euo pipefail

release="${1:?release id required}"
if ! [[ "$release" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "refuse release id: $release" >&2
  exit 1
fi

app_root="${OPCG_APP_ROOT:-/opt/opcg/app}"
frontend="$app_root/frontend"
releases="$frontend/.next/releases"
release_dir="$releases/$release"
stage="$release_dir/standalone"
live="$frontend/.next/standalone"
static_link="$frontend/.next/static"

if [[ ! -f "$stage/server.js" ]]; then
  echo "missing staged server: $stage/server.js" >&2
  exit 1
fi
if [[ ! -d "$stage/.next/static" ]]; then
  echo "missing staged static: $stage/.next/static" >&2
  exit 1
fi

place_link() {
  local link="$1"
  local target="$2"
  local tmp="${link}.promoting.$$"
  ln -s "$target" "$tmp"
  mv -Tf "$tmp" "$link"
}

refuse_static_path() {
  local rel="$1"
  case "$rel" in
    /*|..|../*|*/..|*/../*)
      echo "refuse static path: $rel" >&2
      exit 1
      ;;
  esac
}

copy_retained_static() {
  local src="$1"
  local dest="$2"
  local list="${3:-}"
  local rel file
  [[ -d "$src" ]] || return 0
  mkdir -p "$dest"
  if [[ -n "$list" && -f "$list" ]]; then
    while IFS= read -r rel || [[ -n "${rel:-}" ]]; do
      [[ -z "${rel:-}" ]] && continue
      rel="${rel#./}"
      refuse_static_path "$rel"
      if [[ -f "$src/$rel" && ! -e "$dest/$rel" ]]; then
        mkdir -p "$(dirname "$dest/$rel")"
        cp -a "$src/$rel" "$dest/$rel"
      fi
    done < "$list"
  else
    while IFS= read -r -d '' file; do
      rel="${file#"$src"/}"
      refuse_static_path "$rel"
      if [[ ! -e "$dest/$rel" ]]; then
        mkdir -p "$(dirname "$dest/$rel")"
        cp -a "$file" "$dest/$rel"
      fi
    done < <(find "$src" -type f -print0)
  fi
}

prev_id=""
prev_static=""
prev_list=""
if [[ -L "$live" ]]; then
  prev_real="$(readlink -f "$live")"
  if [[ "$prev_real" != "$releases/"* ]]; then
    echo "live standalone resolves outside releases: $prev_real" >&2
    exit 1
  fi
  prev_id="$(basename "$(dirname "$prev_real")")"
  prev_static="$prev_real/.next/static"
  prev_list="$(dirname "$prev_real")/static-own.list"
  if [[ "$prev_id" == "$release" ]]; then
    echo "promote: $release is already the live standalone"
    exit 0
  fi
elif [[ -d "$live" ]]; then
  prev_static="$live/.next/static"
fi

# Record this build's own files BEFORE merging the previous generation in.
# Skip this when the release is already live (handled above) so a second run
# cannot rewrite the list to include inherited chunks.
( cd "$stage/.next/static" && find . -type f | LC_ALL=C sort ) > "$release_dir/static-own.list"

if [[ -n "$prev_static" && "$prev_id" != "$release" ]]; then
  echo "promote: keeping previous static from ${prev_id:-live directory}"
  copy_retained_static "$prev_static" "$stage/.next/static" "$prev_list"
else
  echo "promote: no previous static to retain"
fi

mkdir -p "$frontend/.next"

# First migration only: the live path is a real directory the running process
# addresses by name. Move it aside, then put the symlink in its place.
# Later deploys only replace the symlink; Node has already realpath'd the
# previous release, so the running process keeps its files until restart.
if [[ -e "$live" && ! -L "$live" ]]; then
  legacy="legacy-$(date +%Y%m%d%H%M%S)"
  mkdir -p "$releases/$legacy"
  mv "$live" "$releases/$legacy/standalone"
  prev_id="$legacy"
  echo "promote: moved live standalone directory to $releases/$legacy/standalone"
fi

if [[ -e "$static_link" && ! -L "$static_link" ]]; then
  if [[ -n "$prev_id" ]]; then
    mkdir -p "$releases/$prev_id"
    mv "$static_link" "$releases/$prev_id/retired-frontend-static"
  else
    rm -rf "${static_link}.replaced"
    mv "$static_link" "${static_link}.replaced"
  fi
fi

place_link "$live" "$stage"
place_link "$static_link" "$stage/.next/static"
echo "promote: standalone -> $stage"

shopt -s nullglob
for dir in "$releases"/*; do
  base="$(basename "$dir")"
  if [[ "$base" == "$release" || ( -n "$prev_id" && "$base" == "$prev_id" ) ]]; then
    continue
  fi
  rm -rf "$dir"
  echo "promote: pruned $base"
done

echo "promote: current=$release previous=${prev_id:-none}"
