#!/usr/bin/env bash
#
# Entry point for the zebra-rs routing container.
#
# Mirrors docker-fpm-frr/docker_init.sh in shape — render config from
# CONFIG_DB with sonic-cfggen, then hand off to supervisord — but the
# rendered artifact is a zebra-rs config rather than a set of FRR ones.

mkdir -p /etc/zebra-rs
mkdir -p /etc/supervisor/conf.d

CFGGEN_PARAMS=" \
    -d \
    -y /etc/sonic/constants.yml \
    -t /usr/share/sonic/templates/supervisord.conf.j2,/etc/supervisor/conf.d/supervisord.conf \
    -t /usr/share/sonic/templates/critical_processes.j2,/etc/supervisor/critical_processes \
    -t /usr/share/sonic/templates/zebra-rs.conf.j2,/etc/zebra-rs/zebra-rs.conf \
"
sonic-cfggen $CFGGEN_PARAMS

update_default_gw()
{
   # Carried over verbatim from docker-fpm-frr, and for the same reason:
   # the routing daemon does not run in the host namespace, so docker's
   # own default route via eth0 has to be re-added at a worse metric or
   # it beats any default the routing stack learns. 210 << 24 puts it
   # below iBGP's administrative distance.
   IP_VER=${1}
   GATEWAY_IP=$(ip -${IP_VER} route show default dev eth0 | awk '{print $3}')
   if [[ ! -z "$GATEWAY_IP" ]]; then
      ip -${IP_VER} route del default dev eth0
      CHECK_GATEWAY_IP=$(ip -${IP_VER} route show default dev eth0 | awk '{print $3}')
      if [[ -z "$CHECK_GATEWAY_IP" ]]; then
         ip -${IP_VER} route add default via $GATEWAY_IP dev eth0 metric 3523215360
      fi
   fi
}

if [[ ! -z "$NAMESPACE_ID" ]]; then
   update_default_gw 4
   update_default_gw 6
fi

mkdir -p /var/sonic
echo "# Config files managed by sonic-config-engine" > /var/sonic/config_status

exec /usr/local/bin/supervisord
