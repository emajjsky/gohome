#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/../.." && pwd)"
output_dir="${1:-${repo_root}/dist/cloud-app}"

cd "${repo_root}"
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "tracked worktree changes must be committed before building a release" >&2
    exit 1
fi

commit="$(git rev-parse --verify HEAD)"
release_id="$(date -u +%Y%m%d%H%M%S)-$(printf '%s' "${commit}" | cut -c1-12)"
archive="${output_dir}/gohome-cloud-${release_id}.tar.gz"
checksum="${archive}.sha256"
manifest="$(mktemp "${TMPDIR:-/tmp}/gohome-cloud-manifest.XXXXXX")"
temporary_archive="$(mktemp "${TMPDIR:-/tmp}/gohome-cloud-release.XXXXXX")"
trap 'rm -f "${manifest}" "${temporary_archive}"' EXIT HUP INT TERM

{
    printf '%s\n' package.json package-lock.json scripts/export-local-app-db.js
    git ls-files local-app-server | awk '
        /^local-app-server\/test\// { next }
        /\.(js|sql)$/ { print }
    '
    git ls-files assets
    git ls-files | awk '
        index($0, "/") == 0 && ($0 ~ /\.html$/ || $0 == "app.webmanifest" || $0 == "service-worker.js") { print }
    '
} | LC_ALL=C sort -u > "${manifest}"

while IFS= read -r file; do
    if [ ! -f "${file}" ]; then
        echo "release manifest entry is missing: ${file}" >&2
        exit 1
    fi
done < "${manifest}"

mkdir -p "${output_dir}"
# Release paths are tracked repository paths and contain no whitespace.
# shellcheck disable=SC2046
git archive --format=tar --prefix="gohome-cloud-${release_id}/" HEAD $(cat "${manifest}") \
    | gzip -9 > "${temporary_archive}"

if tar -tzf "${temporary_archive}" | grep -Eq '(^|/)(test|ios-shell|edge-agent|research|node_modules|\.git)(/|$)|(^|/)\._|\.backup-'; then
    echo "release archive contains a forbidden development or backup path" >&2
    exit 1
fi

mv "${temporary_archive}" "${archive}"
shasum -a 256 "${archive}" | awk '{print $1}' > "${checksum}"
printf 'release_id=%s\narchive=%s\nchecksum=%s\n' "${release_id}" "${archive}" "${checksum}"
