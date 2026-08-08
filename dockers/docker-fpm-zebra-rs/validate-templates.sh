#!/usr/bin/env bash
#
# Render the zebra-rs bgpcfgd templates against bgpcfgd's own test
# fixtures and apply each result to a live zebra-rs.
#
# Unit tests compare rendered output to a hand-written expectation, which
# only proves the template matches what the author believed. This proves
# the stronger thing: that the daemon *accepts* the config. That matters
# more than usual here because `vtyctl apply` exits 0 even when a line is
# rejected — it reports `error reply:` on the stream and returns success
# — so a wrong config path is silently inert until something checks for
# that string. This does.
#
# Reuses dockers/docker-fpm-frr's fixtures verbatim (src/sonic-bgpcfgd/
# tests/data/general/instance.conf/param_*.json): same inputs as the FRR
# templates, so the two are being asked the same questions.
#
# Usage: ./validate-templates.sh [--keep]

set -euo pipefail

FRR_IMAGE=${FRR_IMAGE:-docker-fpm-frr:latest}
CONTAINER=${CONTAINER:-zebra-rs-tmpl}
KEEP="no"
[[ "${1:-}" == "--keep" ]] && KEEP="yes"

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../.." && pwd)
ZEBRA_SRC="$root/src/sonic-zebra-rs/zebra-rs"
FIXTURES="$root/src/sonic-bgpcfgd/tests/data/general/instance.conf"

cleanup() {
    if [[ "$KEEP" == "yes" ]]; then
        echo "validate-templates: leaving $CONTAINER running (--keep)"
    else
        docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

for b in "$ZEBRA_SRC/target/release/zebra-rs" "$ZEBRA_SRC/target/release/vtyctl"; do
    [[ -x "$b" ]] || { echo "missing $b — build zebra-rs first" >&2; exit 1; }
done

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" --init --cap-add NET_ADMIN \
    --entrypoint /bin/sleep "$FRR_IMAGE" infinity >/dev/null

docker cp "$ZEBRA_SRC/target/release/zebra-rs" "$CONTAINER:/usr/bin/" >/dev/null
docker cp "$ZEBRA_SRC/target/release/vtyctl" "$CONTAINER:/usr/bin/" >/dev/null
docker exec "$CONTAINER" mkdir -p /usr/share/zebra-rs/yang
docker cp "$ZEBRA_SRC/zebra-rs/yang/." "$CONTAINER:/usr/share/zebra-rs/yang/" >/dev/null

docker exec -d "$CONTAINER" bash -c \
    'zebra-rs --yang-path /usr/share/zebra-rs/yang > /tmp/zebra-rs.log 2>&1'
sleep 4

# Render on the host (bgpcfgd's TemplateFabric lives here), apply in the
# container.
render_dir=$(mktemp -d /tmp/zrs-render.XXXXXX)
python3 - "$here/zebra-rs/bgpd/templates/general/instance.conf.j2" "$FIXTURES" "$render_dir" <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(sys.argv[3]), ""))
sys.path.insert(0, os.path.abspath("src/sonic-bgpcfgd"))
from bgpcfgd.template import TemplateFabric

tmpl_path, fixtures, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
fabric = TemplateFabric(os.path.dirname(tmpl_path))
tmpl = fabric.from_file(os.path.basename(tmpl_path))

for name in sorted(os.listdir(fixtures)):
    if not name.startswith("param_"):
        continue
    case = name.replace("param_", "").replace(".json", "")
    raw = json.load(open(os.path.join(fixtures, name)))
    params = {}
    for k, v in raw.items():
        if k.startswith("CONFIG_DB__") and isinstance(v, dict):
            params[k] = {tuple(ek.split("|")) if "|" in ek else ek: ev
                         for ek, ev in v.items()}
        else:
            params[k] = v
    try:
        text = tmpl.render(**params)
    except Exception as e:
        print("RENDER-FAIL %s: %s" % (case, e))
        continue
    with open(os.path.join(out_dir, case + ".conf"), "w") as fp:
        fp.write(text)
    print("rendered %s" % case)
PY

docker exec "$CONTAINER" mkdir -p /tmp/rendered
docker cp "$render_dir/." "$CONTAINER:/tmp/rendered/" >/dev/null

echo
echo "validate-templates: applying each rendered case to a live zebra-rs"
docker exec "$CONTAINER" bash -c '
pass=0; fail=0
for f in /tmp/rendered/*.conf; do
    case=$(basename "$f" .conf)
    out=$(vtyctl apply -f "$f" 2>&1 || true)
    if echo "$out" | grep -q "error reply:"; then
        echo "  REJECTED  $case"
        echo "$out" | grep "error reply:" | sed "s/^/      /" | head -3
        fail=$((fail+1))
    else
        echo "  accepted  $case"
        pass=$((pass+1))
    fi
done
echo
echo "  $pass accepted, $fail rejected"
[ "$fail" -eq 0 ]
'
rc=$?

rm -rf "$render_dir"
echo
if [[ "$rc" -eq 0 ]]; then
    echo "PASS — every rendered case was accepted by zebra-rs"
else
    echo "FAIL — some rendered cases were rejected"
fi
exit $rc
