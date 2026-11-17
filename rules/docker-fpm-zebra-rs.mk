# docker image for the zebra-rs routing stack
#
# Drop-in alternative to docker-fpm-frr: same container name (`bgp`),
# same service slot, same fpmsyncd underneath — only the control plane
# differs. Both images build; `SONIC_ROUTING_STACK = zebra-rs` selects
# which one is installed (rules/docker-fpm.mk), so the two can be built
# and compared side by side.

DOCKER_FPM_ZEBRA_RS_STEM = docker-fpm-zebra-rs
DOCKER_FPM_ZEBRA_RS = $(DOCKER_FPM_ZEBRA_RS_STEM).gz
DOCKER_FPM_ZEBRA_RS_DBG = $(DOCKER_FPM_ZEBRA_RS_STEM)-$(DBG_IMAGE_MARK).gz

$(DOCKER_FPM_ZEBRA_RS)_PATH = $(DOCKERS_PATH)/$(DOCKER_FPM_ZEBRA_RS_STEM)

$(DOCKER_FPM_ZEBRA_RS)_DEPENDS += $(ZEBRA_RS) $(SWSS)
# bgpcfgd drives zebra-rs from CONFIG_DB at runtime, as it does FRR.
$(DOCKER_FPM_ZEBRA_RS)_PYTHON_WHEELS += $(SONIC_BGPCFGD)
$(DOCKER_FPM_ZEBRA_RS)_DBG_DEPENDS = $($(DOCKER_SWSS_LAYER_TRIXIE)_DBG_DEPENDS)
$(DOCKER_FPM_ZEBRA_RS)_DBG_DEPENDS += $(SWSS_DBG) $(LIBSWSSCOMMON_DBG)

$(DOCKER_FPM_ZEBRA_RS)_DBG_IMAGE_PACKAGES = $($(DOCKER_SWSS_LAYER_TRIXIE)_DBG_IMAGE_PACKAGES)

$(DOCKER_FPM_ZEBRA_RS)_LOAD_DOCKERS += $(DOCKER_SWSS_LAYER_TRIXIE)

$(DOCKER_FPM_ZEBRA_RS)_VERSION = 1.0.0
$(DOCKER_FPM_ZEBRA_RS)_PACKAGE_NAME = fpm-zebra-rs

# Same shutdown ordering as docker-fpm-frr: the routing container has to
# stop after radv and before swss, or swss tears the dataplane down while
# routes are still being withdrawn.
$(DOCKER_FPM_ZEBRA_RS)_WARM_SHUTDOWN_BEFORE = swss
$(DOCKER_FPM_ZEBRA_RS)_WARM_SHUTDOWN_AFTER = radv
$(DOCKER_FPM_ZEBRA_RS)_FAST_SHUTDOWN_BEFORE = swss
$(DOCKER_FPM_ZEBRA_RS)_FAST_SHUTDOWN_AFTER = radv

SONIC_DOCKER_IMAGES += $(DOCKER_FPM_ZEBRA_RS)
SONIC_DOCKER_DBG_IMAGES += $(DOCKER_FPM_ZEBRA_RS_DBG)

# `bgp` deliberately: this replaces docker-fpm-frr in the same slot, so
# every consumer that talks to the routing container by name — vtysh
# wrappers, sonic-utilities, the service files — keeps working.
# rules/docker-fpm.mk installs exactly one of the two.
$(DOCKER_FPM_ZEBRA_RS)_CONTAINER_NAME = bgp
$(DOCKER_FPM_ZEBRA_RS)_RUN_OPT += -t --cap-add=NET_ADMIN --cap-add=SYS_ADMIN
$(DOCKER_FPM_ZEBRA_RS)_RUN_OPT += -v /etc/sonic:/etc/sonic:ro
$(DOCKER_FPM_ZEBRA_RS)_RUN_OPT += -v /etc/localtime:/etc/localtime:ro

# Host-side wrappers, the same two scripts docker-fpm-frr installs: they
# `docker exec` vtysh in the bgp container, which here is zebra-rs's
# FRR-compatible one. rvtysh is the read-only form `show` runs under sudo.
# FRR's idf_isolation and prefix_list are not shipped: they drive
# configuration zebra-rs has no counterpart for yet.
$(DOCKER_FPM_ZEBRA_RS)_BASE_IMAGE_FILES += vtysh:/usr/bin/vtysh
$(DOCKER_FPM_ZEBRA_RS)_BASE_IMAGE_FILES += rvtysh:/usr/bin/rvtysh
# zebra-rs's own interactive shell, which FRR has no counterpart for:
# `vty` on the host opens it in the bgp container.
$(DOCKER_FPM_ZEBRA_RS)_BASE_IMAGE_FILES += vty:/usr/bin/vty

# Traffic shift: TSA/TSB write BGP_DEVICE_GLOBAL in CONFIG_DB, which
# bgpcfgd turns into policy entries, and TSC asks the container. None of
# that depends on the routing stack, so these are docker-fpm-frr's own
# files, taken from there instead of copied. What differs is the TSC
# inside the container, which this image ships itself (Dockerfile.j2).
DOCKER_FPM_ZEBRA_RS_FRR_FILES = ../../docker-fpm-frr/base_image_files
$(DOCKER_FPM_ZEBRA_RS)_BASE_IMAGE_FILES += $(DOCKER_FPM_ZEBRA_RS_FRR_FILES)/TSA:/usr/bin/TSA
$(DOCKER_FPM_ZEBRA_RS)_BASE_IMAGE_FILES += $(DOCKER_FPM_ZEBRA_RS_FRR_FILES)/TSB:/usr/bin/TSB
$(DOCKER_FPM_ZEBRA_RS)_BASE_IMAGE_FILES += $(DOCKER_FPM_ZEBRA_RS_FRR_FILES)/TSC:/usr/bin/TSC
$(DOCKER_FPM_ZEBRA_RS)_BASE_IMAGE_FILES += $(DOCKER_FPM_ZEBRA_RS_FRR_FILES)/TS:/usr/bin/TS
$(DOCKER_FPM_ZEBRA_RS)_BASE_IMAGE_FILES += $(DOCKER_FPM_ZEBRA_RS_FRR_FILES)/platform_utils:/usr/bin/platform_utils

SONIC_TRIXIE_DOCKERS += $(DOCKER_FPM_ZEBRA_RS)
SONIC_TRIXIE_DBG_DOCKERS += $(DOCKER_FPM_ZEBRA_RS_DBG)
