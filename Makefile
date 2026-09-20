PYTHON ?= python3

.PHONY: all build probe docs verify clean

all: build docs verify

build:
	$(PYTHON) tools/build_tosc.py

probe:
	$(PYTHON) tools/build_probe.py

docs:
	$(PYTHON) tools/dump_map.py

verify: build
	$(PYTHON) tools/verify.py

clean:
	rm -f build/*.tosc build/*.xml
