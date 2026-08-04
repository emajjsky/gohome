#!/bin/sh
set -eu

domain="${GOHOME_MEDIA_TLS_DOMAIN:-gohome.ai2shx.club}"
source_dir="/etc/letsencrypt/live/${domain}"
target_dir="/etc/gohome/media/tls"

install -d -o root -g mediamtx -m 0750 "${target_dir}"
staging_dir="$(mktemp -d "${target_dir}/.renew.XXXXXX")"
trap 'rm -rf "${staging_dir}"' EXIT HUP INT TERM

install -o root -g mediamtx -m 0640 "${source_dir}/fullchain.pem" "${staging_dir}/server.crt"
install -o root -g mediamtx -m 0640 "${source_dir}/privkey.pem" "${staging_dir}/server.key"

cert_key_hash="$(openssl x509 -in "${staging_dir}/server.crt" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum | cut -d ' ' -f 1)"
private_key_hash="$(openssl pkey -in "${staging_dir}/server.key" -pubout -outform DER | sha256sum | cut -d ' ' -f 1)"
if [ "${cert_key_hash}" != "${private_key_hash}" ]; then
    echo "certificate and private key do not match" >&2
    exit 1
fi

mv -f "${staging_dir}/server.crt" "${target_dir}/server.crt"
mv -f "${staging_dir}/server.key" "${target_dir}/server.key"
chown root:mediamtx "${target_dir}/server.crt" "${target_dir}/server.key"
chmod 0640 "${target_dir}/server.crt" "${target_dir}/server.key"

systemctl try-restart gohome-mediamtx.service
