# zebra-rs routing stack
#
# The SONiC port replaces FRR's control plane with zebra-rs, which speaks
# SONiC's FPM dialect directly to fpmsyncd — so everything below
# fpmsyncd (APPL_DB, orchagent, syncd, SAI) is untouched.
#
# Off by default. `SONIC_ROUTING_STACK = zebra-rs` (rules/config) installs
# it in place of docker-fpm-frr; frr remains the default. Both images
# always build, so the two can be compared side by side.

ZEBRA_RS_VERSION = 26.11.4

# zebra-rs needs a newer Rust than the slave's default toolchain. The
# slave carries this one side by side (sonic-slave-trixie/Dockerfile.j2,
# ZEBRA_RS_RUST_VERSION there) and src/sonic-zebra-rs/Makefile selects it
# with RUSTUP_TOOLCHAIN. Keep the two in sync.
ZEBRA_RS_RUST_VERSION = 1.97.0
ZEBRA_RS_SUBVERSION = 0

ZEBRA_RS = zebra-rs_$(ZEBRA_RS_VERSION)-sonic-$(ZEBRA_RS_SUBVERSION)_$(CONFIGURED_ARCH).deb
$(ZEBRA_RS)_SRC_PATH = $(SRC_PATH)/sonic-zebra-rs
SONIC_MAKE_DEBS += $(ZEBRA_RS)

export ZEBRA_RS_VERSION ZEBRA_RS_SUBVERSION ZEBRA_RS ZEBRA_RS_RUST_VERSION

# The .c/.cpp/.h sources under src/{DBG_SRC_ARCHIVE} are archived into the
# debug image. zebra-rs is Rust, so there is nothing for that archive to
# collect and it is deliberately not listed.
