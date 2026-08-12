#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/../.." && pwd)"
output_dir="${1:-${repo_root}/dist/cloud-app}"
revision="${2:-HEAD}"

cd "${repo_root}"
commit="$(git rev-parse --verify "${revision}^{commit}")"
release_id="$(date -u +%Y%m%d%H%M%S)-$(printf '%s' "${commit}" | cut -c1-12)"
archive="${output_dir}/gohome-cloud-${release_id}.tar.gz"
checksum="${archive}.sha256"
file_manifest="${archive}.files.sha256"
manifest="$(mktemp "${TMPDIR:-/tmp}/gohome-cloud-manifest.XXXXXX")"
temporary_archive="$(mktemp "${TMPDIR:-/tmp}/gohome-cloud-release.XXXXXX")"
temporary_file_manifest="$(mktemp "${TMPDIR:-/tmp}/gohome-cloud-files.XXXXXX")"
trap 'rm -f "${manifest}" "${temporary_archive}" "${temporary_file_manifest}"' EXIT HUP INT TERM

{
    git ls-tree -r --name-only "${commit}" | awk '
        $0 == "package.json" ||
        $0 == "package-lock.json" ||
        $0 == "scripts/apply-postgres-migrations.js" ||
        $0 == "scripts/export-local-app-db.js" ||
        $0 == "scripts/reconcile-historical-media.js" { print; next }
        /^local-app-server\/test\// { next }
        /^local-app-server\// && /\.(js|sql)$/ { print; next }
        /^assets\// { print; next }
        index($0, "/") == 0 && ($0 ~ /\.html$/ || $0 == "app.webmanifest" || $0 == "service-worker.js") { print }
    '
} | LC_ALL=C sort -u > "${manifest}"

while IFS= read -r file; do
    if ! git cat-file -e "${commit}:${file}"; then
        echo "release commit entry is missing: ${file}" >&2
        exit 1
    fi
done < "${manifest}"

mkdir -p "${output_dir}"
# Release paths are tracked repository paths and contain no whitespace.
# shellcheck disable=SC2046
git archive --format=tar --prefix="gohome-cloud-${release_id}/" "${commit}" $(cat "${manifest}") \
    | gzip -9 > "${temporary_archive}"

if tar -tzf "${temporary_archive}" | grep -Eq '(^|/)(test|ios-shell|edge-agent|research|node_modules|\.git)(/|$)|(^|/)\._|\.backup-'; then
    echo "release archive contains a forbidden development or backup path" >&2
    exit 1
fi

mv "${temporary_archive}" "${archive}"
shasum -a 256 "${archive}" | awk '{print $1}' > "${checksum}"
while IFS= read -r file; do
    git show "${commit}:${file}" | shasum -a 256 | awk -v path="${file}" '{print $1 "  " path}'
done < "${manifest}" > "${temporary_file_manifest}"
mv "${temporary_file_manifest}" "${file_manifest}"
printf 'release_id=%s\narchive=%s\nchecksum=%s\nfile_manifest=%s\n' "${release_id}" "${archive}" "${checksum}" "${file_manifest}"
