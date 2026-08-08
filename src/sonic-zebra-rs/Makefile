.ONESHELL:
SHELL = /bin/bash
.SHELLFLAGS += -e

MAIN_TARGET = $(ZEBRA_RS)
STAGE = $(shell pwd)/.stage

# zebra-rs ships its own cargo-deb packaging upstream, but cargo-deb is
# not in the SONiC build slave and adding a build-time cargo plugin for
# one package is a poor trade. The tree is assembled by hand and sealed
# with dpkg-deb, which is always present. The layout below matches what
# upstream's cargo-deb produces for the pieces SONiC actually uses.
$(addprefix $(DEST)/, $(MAIN_TARGET)): $(DEST)/% :

	# zebra-rs gitignores its Cargo.lock upstream, so the submodule SHA
	# alone does not pin the dependency graph — the same commit can
	# resolve different crate versions as the registry moves. Pin it here
	# instead, which is what a distro packager does: Cargo.lock is
	# committed alongside this Makefile and copied in before the build,
	# so `--locked` below has something to enforce and a rebuild of a
	# given SONiC commit is reproducible. Refresh it deliberately (cargo
	# generate-lockfile in the submodule) when bumping the SHA.
	cp Cargo.lock zebra-rs/Cargo.lock

	pushd zebra-rs

	cargo build --release --locked --bin zebra-rs --bin vtyctl --bin vtyhelper

	popd

	rm -rf $(STAGE)
	mkdir -p $(STAGE)/DEBIAN
	mkdir -p $(STAGE)/usr/bin
	mkdir -p $(STAGE)/usr/share/zebra-rs/yang
	mkdir -p $(STAGE)/etc/zebra-rs

	install -m 0755 zebra-rs/target/release/zebra-rs  $(STAGE)/usr/bin/
	install -m 0755 zebra-rs/target/release/vtyctl    $(STAGE)/usr/bin/
	install -m 0755 zebra-rs/target/release/vtyhelper $(STAGE)/usr/bin/

	# The daemon loads its YANG schemas at runtime and refuses to start
	# without them; they are program data, not operator config, hence
	# /usr/share.
	install -m 0644 zebra-rs/zebra-rs/yang/*.yang $(STAGE)/usr/share/zebra-rs/yang/

	# Ship an empty config. The container's docker_init.sh renders the
	# real one; a comment-only file is treated as "no configuration",
	# which is the right state for a daemon that has not been told
	# anything yet.
	echo "# Rendered by docker_init.sh from CONFIG_DB." > $(STAGE)/etc/zebra-rs/zebra-rs.conf

	sed -e 's/@VERSION@/$(ZEBRA_RS_VERSION)-sonic-$(ZEBRA_RS_SUBVERSION)/' \
	    -e 's/@ARCH@/$(CONFIGURED_ARCH)/' \
	    debian-control.in > $(STAGE)/DEBIAN/control

	# Strip: a release Rust binary still carries substantial symbol data,
	# and zebra-rs is ~44 MB unstripped.
	strip --strip-unneeded $(STAGE)/usr/bin/zebra-rs $(STAGE)/usr/bin/vtyctl \
	    $(STAGE)/usr/bin/vtyhelper || true

	dpkg-deb --build --root-owner-group $(STAGE) $(DEST)/$(MAIN_TARGET)
	rm -rf $(STAGE)

$(addprefix $(DEST)/, $(DERIVED_TARGETS)): $(DEST)/% : $(DEST)/$(MAIN_TARGET)
