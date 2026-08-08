# Docker-fpm rule-file is simply a wrapper containing routing-stack selection logic.

ifeq ($(SONIC_ROUTING_STACK), frr)
SONIC_INSTALL_DOCKER_IMAGES += $(DOCKER_FPM_FRR)
SONIC_INSTALL_DOCKER_DBG_IMAGES += $(DOCKER_FPM_FRR_DBG)
else ifeq ($(SONIC_ROUTING_STACK), zebra-rs)
# Same container name and service slot as docker-fpm-frr, so the two are
# mutually exclusive by construction — which is exactly what this
# selector is for.
SONIC_INSTALL_DOCKER_IMAGES += $(DOCKER_FPM_ZEBRA_RS)
SONIC_INSTALL_DOCKER_DBG_IMAGES += $(DOCKER_FPM_ZEBRA_RS_DBG)
else
SONIC_INSTALL_DOCKER_IMAGES += $(DOCKER_FPM_GOBGP)
endif
