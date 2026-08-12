#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/../.." && pwd)"
output_dir="$(mktemp -d "${TMPDIR:-/tmp}/gohome-cloud-build-test.XXXXXX")"
trap 'rm -rf "${output_dir}"' EXIT HUP INT TERM

current_commit="$(git -C "${repo_root}" rev-parse HEAD)"
parent_commit="$(git -C "${repo_root}" rev-parse HEAD^)"
current_output="$(${script_dir}/build-release.sh "${output_dir}/current" "${current_commit}")"
parent_output="$(${script_dir}/build-release.sh "${output_dir}/parent" "${parent_commit}")"

current_archive="$(printf '%s\n' "${current_output}" | sed -n 's/^archive=//p')"
parent_archive="$(printf '%s\n' "${parent_output}" | sed -n 's/^archive=//p')"
current_root="$(tar -tzf "${current_archive}" | sed -n '1s#/.*##p')"
parent_root="$(tar -tzf "${parent_archive}" | sed -n '1s#/.*##p')"

[ "${current_root}" = "gohome-cloud-$(basename "${current_archive}" .tar.gz | sed 's/^gohome-cloud-//')" ]
[ "${parent_root}" = "gohome-cloud-$(basename "${parent_archive}" .tar.gz | sed 's/^gohome-cloud-//')" ]
tar -xOf "${current_archive}" "${current_root}/local-app-server/vision-verification-runtime.js" \
    | grep -q 'DEFAULT_VERIFICATION_DEADLINE_SECONDS = 90'
if tar -xOf "${parent_archive}" "${parent_root}/local-app-server/vision-verification-runtime.js" \
    | grep -q 'DEFAULT_VERIFICATION_DEADLINE_SECONDS = 90'; then
    echo "explicit parent revision unexpectedly contains the current deadline change" >&2
    exit 1
fi

printf 'current_commit=%s\nparent_commit=%s\nstatus=passed\n' "${current_commit}" "${parent_commit}"
