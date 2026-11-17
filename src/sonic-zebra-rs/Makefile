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

	# Two things differ from a plain `cargo build`, both because zebra-rs
	# is newer than the slave's default Rust (see the zebra-rs block in
	# sonic-slave-trixie/Dockerfile.j2):
	#  - RUSTUP_TOOLCHAIN selects the second, pinned toolchain.
	#  - the slave's /usr/local/bin/cargo wrapper routes `build` through
	#    cargo-auditable 0.6.4, which cannot parse an edition-2024
	#    manifest. The newer cargo-auditable is called by path instead;
	#    CARGO_AUDITABLE_WRAPPED makes the wrapper pass through when
	#    cargo-auditable re-invokes `cargo`. The result still carries the
	#    .dep-v0 section the SBOM tooling reads.
	RUSTUP_TOOLCHAIN=$(ZEBRA_RS_RUST_VERSION) CARGO_AUDITABLE_WRAPPED=1 \
	    /usr/.cargo-zebra-rs/bin/cargo-auditable auditable build --release --locked \
	    --bin zebra-rs --bin vtyctl --bin vtyhelper

	# vty, the interactive shell: GNU bash with zebra-rs's CLI hooks, which
	# calls vtyhelper for every command. Its Makefile fetches the bash
	# tarball (checked against a pinned SHA-256) and applies the patches
	# kept in the tree. The cache is kept inside the build directory: the
	# default is under $$HOME, which is not a place a package build in the
	# slave should write to. bison, xxd and the ncurses headers it needs
	# are already in the slave.
	$(MAKE) -C vty CACHE_DIR=$(shell pwd)/.vty-cache

	popd

	rm -rf $(STAGE)
	mkdir -p $(STAGE)/DEBIAN
	mkdir -p $(STAGE)/usr/bin
	mkdir -p $(STAGE)/usr/share/zebra-rs/yang
	mkdir -p $(STAGE)/etc/zebra-rs

	install -m 0755 zebra-rs/target/release/zebra-rs  $(STAGE)/usr/bin/
	install -m 0755 zebra-rs/target/release/vtyctl    $(STAGE)/usr/bin/
	install -m 0755 zebra-rs/target/release/vtyhelper $(STAGE)/usr/bin/
	install -m 0755 zebra-rs/vty/vty                  $(STAGE)/usr/bin/

	# FRR's vtysh, as far as SONiC's tooling uses it: started under this
	# name vtyctl takes FRR's command line (`-c 'show bgp summary json'`)
	# and answers the json forms in FRR's schema. bgpmon, route_check and
	# sonic-utilities' `show ip bgp`/`show ip route` all run `vtysh`.
	ln -s vtyctl $(STAGE)/usr/bin/vtysh

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
	    $(STAGE)/usr/bin/vtyhelper $(STAGE)/usr/bin/vty || true

	dpkg-deb --build --root-owner-group $(STAGE) $(DEST)/$(MAIN_TARGET)
	rm -rf $(STAGE)

$(addprefix $(DEST)/, $(DERIVED_TARGETS)): $(DEST)/% : $(DEST)/$(MAIN_TARGET)
