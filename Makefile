PYTHON ?= python3

.PHONY: all build docs clean

all: build docs

build:
	$(PYTHON) tools/build_tosc.py

docs:
	$(PYTHON) tools/dump_map.py

clean:
	rm -f build/vj-control.tosc build/vj-control.xml
