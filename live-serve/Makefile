.DEFAULT_GOAL := test
.PHONY: help build package test release publish
help:
	@printf '%s\n' 'help: list commands' 'build: build package (SUITE and ARCH required)' 'package: build package (SUITE and ARCH required)' 'test: run eight target containers' 'publish: upload validated packages to Packagecloud' 'release: tag and push a release'
build:
	./scripts/build "$(SUITE)" "$(ARCH)" "$(OUTPUT)"
package: build
test:
	python3 tests/test_regressions.py
	./scripts/matrix
release:
	./scripts/release
publish:
	./scripts/publish.py
