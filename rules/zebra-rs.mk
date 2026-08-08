# zebra-rs routing stack
#
# The SONiC port replaces FRR's control plane with zebra-rs, which speaks
# SONiC's FPM dialect directly to fpmsyncd — so everything below
# fpmsyncd (APPL_DB, orchagent, syncd, SAI) is untouched.
#
# Off by default. Set INCLUDE_ZEBRA_RS=y to build it; docker-fpm-frr
# remains the shipping routing container either way, so the two can be
# built and compared side by side.

ZEBRA_RS_VERSION = 26.8.2
ZEBRA_RS_SUBVERSION = 0

ZEBRA_RS = zebra-rs_$(ZEBRA_RS_VERSION)-sonic-$(ZEBRA_RS_SUBVERSION)_$(CONFIGURED_ARCH).deb
$(ZEBRA_RS)_SRC_PATH = $(SRC_PATH)/sonic-zebra-rs
SONIC_MAKE_DEBS += $(ZEBRA_RS)

export ZEBRA_RS_VERSION ZEBRA_RS_SUBVERSION ZEBRA_RS

# The .c/.cpp/.h sources under src/{DBG_SRC_ARCHIVE} are archived into the
# debug image. zebra-rs is Rust, so there is nothing for that archive to
# collect and it is deliberately not listed.
