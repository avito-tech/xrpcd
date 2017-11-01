BUILD_NUMBER?=manual
PYTHON?=python2.7
PYTHONPATH=./
SOURCE_DIR=./
PACKAGE_VERSION := $(shell ${PYTHON} -c 'import xrpcd; print(xrpcd.__version__)')

.PHONY : all help clean clean-pyc clean-build build install sdist upload test image push

all: help

help:
	@echo "clean        - remove artifacts"
	@echo "build        - build python package"
	@echo "install      - install python package"
	@echo "sdist        - make source distribution tarball"
	@echo "upload       - upload source distribution tarball to PYPI"
	@echo "image        - build docker image"
	@echo "push         - push docker image to local registry"

clean: clean-pyc clean-build

clean-pyc:
	find . -name '*.py[cod]' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '*$py.class' -exec rm -rf {} +

clean-build:
	rm -rf build/
	rm -rf dist/
	rm -rf .eggs/
	rm -rf .egg-info
	find . -name '*.egg-info' -exec rm -rf {} +
	find . -name '*.egg' -exec rm -f {} +

build:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) setup.py build

install:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) setup.py install

sdist:
	$(PYTHON) ./setup.py sdist

upload:
	$(PYTHON) ./setup.py sdist upload -r $(PYPI_NAME)

test:
	$(PYTHON) -m unittest discover --start-directory tests --pattern "*_test.py" --buffer

image:
	docker build \
		--no-cache \
		-t avitotech/xrpcd:${PACKAGE_VERSION}-${BUILD_NUMBER} \
		.

	docker tag \
		avitotech/xrpcd:${PACKAGE_VERSION}-${BUILD_NUMBER} \
		avitotech/xrpcd:latest

push:
	docker push avitotech/xrpcd:${PACKAGE_VERSION}-${BUILD_NUMBER}
	docker push avitotech/xrpcd:latest
