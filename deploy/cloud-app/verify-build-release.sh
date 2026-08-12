#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/../.." && pwd)"
output_dir="$(mktemp -d "${TMPDIR:-/tmp}/gohome-cloud-build-test.XXXXXX")"
trap 'rm -rf "${output_dir}"' EXIT HUP INT TERM

verify_revision() {
    name="$1"
    revision="$2"
    commit="$(git -C "${repo_root}" rev-parse "${revision}^{commit}")"
    output="$(${script_dir}/build-release.sh "${output_dir}/${name}" "${commit}")"
    archive="$(printf '%s\n' "${output}" | sed -n 's/^archive=//p')"
    file_manifest="$(printf '%s\n' "${output}" | sed -n 's/^file_manifest=//p')"
    root="$(tar -tzf "${archive}" | sed -n '1s#/.*##p')"
    archived_paths="${output_dir}/${name}.paths"
    manifest_paths="${output_dir}/${name}.manifest-paths"

    short_commit="$(printf '%s' "${commit}" | cut -c1-12)"
    case "${root}" in
        *-"${short_commit}") ;;
        *) echo "archive root does not identify selected commit: ${commit}" >&2; exit 1 ;;
    esac
    tar -tzf "${archive}" \
        | awk -v prefix="${root}/" 'substr($0, length($0), 1) != "/" { sub("^" prefix, ""); print }' \
        | LC_ALL=C sort > "${archived_paths}"
    sed 's/^[^ ]*  //' "${file_manifest}" | LC_ALL=C sort > "${manifest_paths}"
    cmp -s "${archived_paths}" "${manifest_paths}" || {
        echo "archive paths differ from commit manifest: ${commit}" >&2
        exit 1
    }
    while IFS= read -r line; do
        expected="${line%%  *}"
        path="${line#*  }"
        [ "${expected}" != "${line}" ] && [ "${path}" != "${line}" ] || {
            echo "invalid file manifest" >&2
            exit 1
        }
        commit_hash="$(git -C "${repo_root}" show "${commit}:${path}" | shasum -a 256 | awk '{print $1}')"
        archive_hash="$(tar -xOf "${archive}" "${root}/${path}" | shasum -a 256 | awk '{print $1}')"
        [ "${expected}" = "${commit_hash}" ] && [ "${expected}" = "${archive_hash}" ] || {
            echo "archive content differs from selected commit: ${commit}:${path}" >&2
            exit 1
        }
    done < "${file_manifest}"
    printf '%s_commit=%s\n' "${name}" "${commit}"
}

verify_revision current HEAD
verify_revision parent HEAD^
printf 'status=passed\n'
