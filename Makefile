# Copyright 2017 Univa Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

SUBDIRS=urb-core source/python
SHELL:=$(shell which bash)

include urb-core/util/include.mk 

PYPLATFORM=$(shell PATH=$(PYENV_HOME)/bin:$(PATH) python -c "from distutils.util import get_platform; print get_platform()")
SHORT_NAME=urb
URB_NAME=$(SHORT_NAME)-$(VERSION)
URB_UGE_NAME=$(SHORT_NAME)-uge-$(VERSION)
DIST_DIR=dist/$(URB_NAME)

# full target
dist:   urb_core_dist dist_urb_uge
	cd dist && ln -sf ../urb-core/dist/urb-core-$(VERSION).tar.gz
	# merge two archives into final one
	mkdir -p dist/tmp && cd dist/tmp && $(TAR) xzf ../urb-core-$(VERSION).tar.gz && $(TAR) xzf ../urb-uge-$(VERSION).tar.gz && GZIP=-9 $(TAR) czf ../urb-$(VERSION).tar.gz urb-$(VERSION) && cd - && rm -rf dist/tmp

# local dist target
dist_urb_uge:   $(DIST_DIR)/../.dummy
	cd source/python && $(MAKE) dist
	cp source/python/dist/uge_adapter-*.egg $(DIST_DIR)/pkg
	# create final archive
	cd $(DIST_DIR)/..; $(TAR) czf $(URB_UGE_NAME).tar.gz $(URB_NAME)
	# This will make dist always rebuild
	rm -f $(DIST_DIR)/../.dummy

# core dist target
urb_core_dist:
	cd urb-core && $(MAKE) dist

# Make all of the dist directories
$(DIST_DIR)/../.dummy:
	rm -rf $(DIST_DIR)
	mkdir -p $(DIST_DIR)/bin
	mkdir -p $(DIST_DIR)/pkg
