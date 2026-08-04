#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "install-release.sh must run as root" >&2
    exit 1
fi
if [ "$#" -ne 4 ]; then
    echo "usage: install-release.sh ARCHIVE EXPECTED_SHA256 RELEASE_ID SYSTEMD_UNIT" >&2
    exit 1
fi

archive="$(readlink -f -- "$1")"
expected_sha256="$2"
release_id="$3"
unit_file="$(readlink -f -- "$4")"

case "${release_id}" in
    *[!A-Za-z0-9._-]*|'') echo "invalid release id" >&2; exit 1 ;;
esac
for file in "${archive}" "${unit_file}"; do
    [ -f "${file}" ] || { echo "missing deployment file: ${file}" >&2; exit 1; }
done

actual_sha256="$(sha256sum "${archive}" | cut -d ' ' -f 1)"
[ "${actual_sha256}" = "${expected_sha256}" ] || {
    echo "release checksum mismatch" >&2
    exit 1
}

if ! tar -tzf "${archive}" | awk '
    BEGIN { valid = 1; roots = 0 }
    /^\// || /(^|\/)\.\.($|\/)/ { valid = 0 }
    /^[^/]+\/$/ { roots += 1 }
    END { exit !(valid && roots == 1) }
'; then
    echo "release archive has an unsafe or ambiguous root" >&2
    exit 1
fi

releases_dir="/opt/gohome/releases"
release_dir="${releases_dir}/${release_id}"
[ ! -e "${release_dir}" ] || { echo "release already exists: ${release_id}" >&2; exit 1; }

install -d -o root -g gohome -m 0750 "${releases_dir}"
staging_dir="$(mktemp -d "${releases_dir}/.staging-${release_id}.XXXXXX")"
next_link=""
previous_target=""
switched=false

cleanup() {
    status="$?"
    trap - EXIT HUP INT TERM
    [ -z "${staging_dir}" ] || rm -rf -- "${staging_dir}"
    [ -z "${next_link}" ] || rm -f -- "${next_link}"
    if [ "${status}" -ne 0 ] && [ "${switched}" = true ] && [ -n "${previous_target}" ]; then
        rollback_link="/opt/gohome/.rollback-${release_id}"
        rm -f -- "${rollback_link}"
        ln -s "${previous_target}" "${rollback_link}"
        mv -Tf "${rollback_link}" /opt/gohome/current
        systemctl restart gohome-app.service || true
    fi
    if [ "${status}" -ne 0 ] && [ -d "${release_dir}" ]; then
        current_target="$(readlink -f /opt/gohome/current 2>/dev/null || true)"
        [ "${current_target}" = "${release_dir}" ] || rm -rf -- "${release_dir}"
    fi
    exit "${status}"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

tar -xzf "${archive}" --strip-components=1 -C "${staging_dir}" --no-same-owner --no-same-permissions
for file in package.json package-lock.json local-app-server/server.js scripts/export-local-app-db.js; do
    [ -f "${staging_dir}/${file}" ] || { echo "release is missing ${file}" >&2; exit 1; }
done
if find "${staging_dir}" -type f \( -name '._*' -o -name '*.backup-*' \) -print -quit | grep -q .; then
    echo "release contains backup or AppleDouble files" >&2
    exit 1
fi
if find "${staging_dir}" -type d \( -name test -o -name ios-shell -o -name edge-agent -o -name research \) -print -quit | grep -q .; then
    echo "release contains a development-only directory" >&2
    exit 1
fi

cd "${staging_dir}"
chown -R gohome:gohome "${staging_dir}"
chmod 0750 "${staging_dir}"
runuser -u gohome -- env npm_config_cache="${staging_dir}/.npm-cache" \
    npm ci --omit=dev --ignore-scripts --no-audit --no-fund
rm -rf -- "${staging_dir}/.npm-cache"
chown -R root:gohome "${staging_dir}"
find "${staging_dir}" -type d -exec chmod 0750 {} +
find "${staging_dir}" -type f -exec chmod 0640 {} +
mv "${staging_dir}" "${release_dir}"
staging_dir=""

install -o root -g root -m 0644 "${unit_file}" /etc/systemd/system/gohome-app.service
systemctl daemon-reload

previous_target="$(readlink -f /opt/gohome/current 2>/dev/null || true)"
[ -n "${previous_target}" ] || previous_target="/opt/gohome/app"
next_link="/opt/gohome/.current-${release_id}"
ln -s "${release_dir}" "${next_link}"
mv -Tf "${next_link}" /opt/gohome/current
next_link=""
switched=true

systemctl restart gohome-app.service

healthy=false
attempt=0
while [ "${attempt}" -lt 30 ]; do
    if curl -fsS --max-time 2 http://127.0.0.1:8788/health >/dev/null; then
        healthy=true
        break
    fi
    attempt=$((attempt + 1))
    sleep 1
done

if [ "${healthy}" != true ]; then
    echo "release health check failed; restoring previous release" >&2
    exit 1
fi

find "${releases_dir}" -mindepth 1 -maxdepth 1 -type d -name '[!.]*' -printf '%T@ %p\n' \
    | sort -rn \
    | awk 'NR > 3 { print $2 }' \
    | while IFS= read -r obsolete; do
        [ "${obsolete}" = "$(readlink -f /opt/gohome/current)" ] || rm -rf -- "${obsolete}"
    done

printf 'release=%s\nstatus=healthy\n' "${release_id}"
