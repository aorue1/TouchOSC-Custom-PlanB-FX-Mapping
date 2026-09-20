PYTHON ?= python3

.PHONY: all build docs verify clean

all: build docs verify

build:
	$(PYTHON) tools/build_tosc.py

docs:
	$(PYTHON) tools/dump_map.py

verify: build
	$(PYTHON) tools/verify.py

clean:
	rm -f build/vj-control.tosc build/vj-control.xml
