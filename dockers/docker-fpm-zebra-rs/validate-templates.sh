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
FIXTURE_ROOT="$root/src/sonic-bgpcfgd/tests/data/general"
# Every template ported so far, paired with the fixture directory
# bgpcfgd's own tests drive the FRR version with.
TEMPLATES="instance.conf peer-group.conf policies.conf"

cleanup() {
    if [[ "$KEEP" == "yes" ]]; then
        echo "validate-templates: leaving $CONTAINER running (--keep)"
    else
        docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# Binaries: the submodule's own target/ if it has been built there,
# otherwise a sibling zebra-rs checkout, otherwise ZEBRA_BIN_DIR. The
# submodule is normally a pristine checkout — building in it dirties a
# tree that is meant to be a pinned reference — so a developer's own
# working copy is the common case.
if [[ -z "${ZEBRA_BIN_DIR:-}" ]]; then
    for cand in "$ZEBRA_SRC/target/release" "$root/../zebra-rs/target/release"; do
        if [[ -x "$cand/zebra-rs" && -x "$cand/vtyctl" ]]; then
            ZEBRA_BIN_DIR="$cand"
            break
        fi
    done
fi
if [[ -z "${ZEBRA_BIN_DIR:-}" ]]; then
    echo "no zebra-rs/vtyctl binaries found." >&2
    echo "  build in the submodule, or a sibling checkout, or set ZEBRA_BIN_DIR" >&2
    exit 1
fi
echo "validate-templates: using binaries from $ZEBRA_BIN_DIR"

# YANG schemas must match the binary, so take them from the same tree.
YANG_DIR="$(cd "$ZEBRA_BIN_DIR/../.." && pwd)/zebra-rs/yang"
[[ -d "$YANG_DIR" ]] || { echo "no YANG schemas at $YANG_DIR" >&2; exit 1; }

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" --init --cap-add NET_ADMIN \
    --entrypoint /bin/sleep "$FRR_IMAGE" infinity >/dev/null

docker cp "$ZEBRA_BIN_DIR/zebra-rs" "$CONTAINER:/usr/bin/" >/dev/null
docker cp "$ZEBRA_BIN_DIR/vtyctl" "$CONTAINER:/usr/bin/" >/dev/null
docker exec "$CONTAINER" mkdir -p /usr/share/zebra-rs/yang
docker cp "$YANG_DIR/." "$CONTAINER:/usr/share/zebra-rs/yang/" >/dev/null

docker exec -d "$CONTAINER" bash -c \
    'zebra-rs --yang-path /usr/share/zebra-rs/yang > /tmp/zebra-rs.log 2>&1'
sleep 4

# Render on the host (bgpcfgd's TemplateFabric lives here), apply in the
# container.
render_dir=$(mktemp -d /tmp/zrs-render.XXXXXX)
python3 - "$here/zebra-rs/bgpd/templates/general" "$FIXTURE_ROOT" "$render_dir" "$TEMPLATES" <<'PY'
import json, os, sys
sys.path.insert(0, os.path.abspath("src/sonic-bgpcfgd"))
from bgpcfgd.template import TemplateFabric

tmpl_dir, fixture_root, out_dir, templates = sys.argv[1:5]
fabric = TemplateFabric(tmpl_dir)

failures = 0
for template in templates.split():
    tmpl = fabric.from_file(template + ".j2")
    fixtures = os.path.join(fixture_root, template)
    for name in sorted(os.listdir(fixtures)):
        if not name.startswith("param_"):
            continue
        case = "%s__%s" % (template, name.replace("param_", "").replace(".json", ""))
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
            failures += 1
            continue
        with open(os.path.join(out_dir, case + ".conf"), "w") as fp:
            fp.write(text)
        print("rendered %s" % case)
sys.exit(1 if failures else 0)
PY

docker exec "$CONTAINER" mkdir -p /tmp/rendered
docker cp "$render_dir/." "$CONTAINER:/tmp/rendered/" >/dev/null

echo
echo "validate-templates: applying each rendered case to a live zebra-rs"
docker exec "$CONTAINER" bash -c '
pass=0; fail=0; expected=0
for f in /tmp/rendered/*.conf; do
    case=$(basename "$f" .conf)
    out=$(vtyctl apply -f "$f" 2>&1 || true)
    if echo "$out" | grep -q "error reply:"; then
        # A rejection naming an UNSUPPORTED- sentinel is the template
        # deliberately refusing a construct zebra-rs lacks. Anything else
        # is a wrong config path — the failure this rig exists to catch.
        if echo "$out" | grep "error reply:" | grep -q "UNSUPPORTED-"; then
            echo "  refused   $case (unsupported construct, by design)"
            echo "$out" | grep "error reply:" | grep "UNSUPPORTED-" | sed "s/^/      /" | head -1
            expected=$((expected+1))
        else
            echo "  REJECTED  $case"
            echo "$out" | grep "error reply:" | sed "s/^/      /" | head -3
            fail=$((fail+1))
        fi
    else
        echo "  accepted  $case"
        pass=$((pass+1))
    fi
done
echo
echo "  $pass accepted, $expected refused by design, $fail unexpectedly rejected"
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
