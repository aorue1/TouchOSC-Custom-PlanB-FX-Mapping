PYTHON ?= python3

.PHONY: all build boris probe docs verify clean

all: build docs verify

build:
	$(PYTHON) tools/build_tosc.py
	$(PYTHON) tools/build_boris.py

# Just the Boris gig layout.
boris:
	$(PYTHON) tools/build_boris.py
	$(PYTHON) tools/verify.py build/boris-landscape.xml

probe:
	$(PYTHON) tools/build_probe.py

docs:
	$(PYTHON) tools/dump_map.py

verify: build
	$(PYTHON) tools/verify.py

clean:
	rm -f build/*.tosc build/*.xml
