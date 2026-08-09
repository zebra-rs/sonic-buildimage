#!/usr/bin/env bash
#
# Render the zebra-rs global instance template (zebra-rs.conf.j2) from
# real minigraphs and apply each result to a live zebra-rs.
#
# Companion to validate-templates.sh, which covers the bgpcfgd per-role
# families. This one covers the *instance* those peers live in — the port
# of dockers/docker-fpm-frr/frr/bgpd/bgpd.main.conf.j2 — which is rendered
# by sonic-cfggen at container start rather than by bgpcfgd.
#
# Inputs are the same minigraphs sonic-config-engine tests the FRR
# template with (src/sonic-config-engine/tests/), so both templates are
# asked the same questions. sonic-cfggen needs swsscommon, so rendering
# happens inside the FRR image; only the daemon is ours.
#
# As in validate-templates.sh, the check greps for `error reply:` because
# `vtyctl apply` exits 0 when the daemon rejects a line, and a line naming
# an `UNSUPPORTED-` token is a deliberate refusal rather than a bad path.
#
# Usage: ./validate-instance-template.sh [--keep]

set -euo pipefail

FRR_IMAGE=${FRR_IMAGE:-docker-fpm-frr:latest}
CONTAINER=${CONTAINER:-zebra-rs-instance-tmpl}
KEEP="no"
[[ "${1:-}" == "--keep" ]] && KEEP="yes"

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../.." && pwd)
TESTS="$root/src/sonic-config-engine/tests"

# minigraph:port-config:label. The same fixtures test_frr.py drives the
# FRR template with, so a divergence between the two templates shows up
# as a different verdict on identical input.
CASES=(
    "t0-sample-graph.xml:t0-sample-port-config.ini:t0"
    "t1-sample-graph-mlnx.xml:sample-port-config-mlnx.ini:t1-mlnx"
    "t2-chassis-fe-graph.xml:t2-chassis-fe-port-config.ini:t2-chassis-fe"
)

cleanup() {
    if [[ "$KEEP" == "yes" ]]; then
        echo "validate-instance-template: leaving $CONTAINER running (--keep)"
    else
        docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

if [[ -z "${ZEBRA_BIN_DIR:-}" ]]; then
    for cand in "$root/src/sonic-zebra-rs/zebra-rs/target/release" "$root/../zebra-rs/target/release"; do
        if [[ -x "$cand/zebra-rs" && -x "$cand/vtyctl" ]]; then
            ZEBRA_BIN_DIR="$cand"
            break
        fi
    done
fi
[[ -n "${ZEBRA_BIN_DIR:-}" ]] || { echo "no zebra-rs/vtyctl binaries found; set ZEBRA_BIN_DIR" >&2; exit 1; }
YANG_DIR="$(cd "$ZEBRA_BIN_DIR/../.." && pwd)/zebra-rs/yang"
[[ -d "$YANG_DIR" ]] || { echo "no YANG schemas at $YANG_DIR" >&2; exit 1; }
echo "validate-instance-template: binaries from $ZEBRA_BIN_DIR"

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" --init --cap-add NET_ADMIN \
    --entrypoint /bin/sleep "$FRR_IMAGE" infinity >/dev/null

docker cp "$ZEBRA_BIN_DIR/zebra-rs" "$CONTAINER:/usr/bin/" >/dev/null
docker cp "$ZEBRA_BIN_DIR/vtyctl" "$CONTAINER:/usr/bin/" >/dev/null
docker exec "$CONTAINER" mkdir -p /usr/share/zebra-rs/yang /tmp/tmpl /tmp/fixtures
docker cp "$YANG_DIR/." "$CONTAINER:/usr/share/zebra-rs/yang/" >/dev/null
# The whole template tree: zebra-rs.conf.j2 imports common/functions.conf.j2,
# and it must resolve from the same root production uses.
docker cp "$here/zebra-rs/." "$CONTAINER:/tmp/tmpl/" >/dev/null
# Copy only the fixtures named in CASES, plus constants.yml. The tests
# directory as a whole contains symlinks pointing outside it, which
# `docker cp` refuses.
docker exec "$CONTAINER" mkdir -p /tmp/fixtures/data
docker cp "$TESTS/data/constants.yml" "$CONTAINER:/tmp/fixtures/data/" >/dev/null
for spec in "${CASES[@]}"; do
    IFS=':' read -r graph portcfg _label <<<"$spec"
    for f in "$graph" "$portcfg"; do
        [[ -f "$TESTS/$f" ]] && docker cp "$TESTS/$f" "$CONTAINER:/tmp/fixtures/" >/dev/null
    done
done

docker exec -d "$CONTAINER" bash -c \
    'zebra-rs --yang-path /usr/share/zebra-rs/yang > /tmp/zebra-rs.log 2>&1'
sleep 4

echo
echo "validate-instance-template: rendering with sonic-cfggen, applying to zebra-rs"
pass=0; fail=0; refused=0
for spec in "${CASES[@]}"; do
    IFS=':' read -r graph portcfg label <<<"$spec"
    if ! docker exec "$CONTAINER" test -f "/tmp/fixtures/$graph"; then
        echo "  skipped   $label (no $graph)"
        continue
    fi
    out=$(docker exec "$CONTAINER" bash -c "
        sonic-cfggen -m /tmp/fixtures/$graph -p /tmp/fixtures/$portcfg \
            -y /tmp/fixtures/data/constants.yml \
            -t /tmp/tmpl/zebra-rs.conf.j2 -T /tmp/tmpl \
            > /tmp/rendered-$label.conf 2>/tmp/render-$label.err" 2>&1) || {
        echo "  RENDER-FAIL $label"
        docker exec "$CONTAINER" sed -n '1,6p' "/tmp/render-$label.err" | sed 's/^/      /'
        fail=$((fail+1)); continue
    }
    # Markers come from the rendered text, not from the apply result: a
    # commit aborts on the FIRST bad line, so asking the daemon would
    # report one refusal and hide the rest.
    markers=$(docker exec "$CONTAINER" bash -c \
        "grep -o 'UNSUPPORTED-[a-z0-9-]*' /tmp/rendered-$label.conf | sort -u || true")

    # Apply with the refused lines stripped, so the rest of the file is
    # genuinely exercised against the daemon rather than being discarded
    # by the first marker.
    apply=$(docker exec "$CONTAINER" bash -c "
        grep -v 'UNSUPPORTED-' /tmp/rendered-$label.conf > /tmp/clean-$label.conf
        vtyctl apply -f /tmp/clean-$label.conf 2>&1 || true")

    if echo "$apply" | grep -q "error reply:"; then
        echo "  REJECTED  $label"
        echo "$apply" | grep "error reply:" | sed 's/^/      /' | head -5
        fail=$((fail+1))
    elif [[ -n "$markers" ]]; then
        n=$(echo "$markers" | wc -l)
        echo "  accepted  $label (supported subset), $n construct(s) refused by design:"
        echo "$markers" | sed 's/^/      /'
        refused=$((refused+1))
        pass=$((pass+1))
    else
        echo "  accepted  $label (in full)"
        pass=$((pass+1))
    fi
done

echo
echo "  $pass accepted, $refused refused by design, $fail unexpectedly rejected"
if [[ "$fail" -eq 0 ]]; then
    echo "PASS — no unexpected rejections"
else
    echo "FAIL — some rendered cases were rejected"
    exit 1
fi
