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

SONIC_TRIXIE_DOCKERS += $(DOCKER_FPM_ZEBRA_RS)
SONIC_TRIXIE_DBG_DOCKERS += $(DOCKER_FPM_ZEBRA_RS_DBG)
