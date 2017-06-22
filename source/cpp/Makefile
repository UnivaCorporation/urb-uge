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

include ../../urb-core/util/include.mk

DISABLED_WARNINGS=-Wno-unused-local-typedefs -Wno-unused-parameter
ENABLED_WARNINGS=-Wredundant-decls -Wswitch-default # -Wshadow -Wundef -Wfloat-equal -Wconversion
PICOJSON_FLAGS=-DPICOJSON_USE_INT64 -D__STDC_FORMAT_MACROS
CFLAGS=-Wall -fPIC -Wextra $(DISABLED_WARNINGS) $(ENABLED_WARNINGS) $(PICOJSON_FLAGS)
ifdef DEBUG_BUILD
  CFLAGS += -DDEBUG -O0 -g3
else
  CFLAGS += -DNDEBUG -O2
endif

ifeq ($(shell uname -s),SunOS)
  CFLAGS += -pthreads
else
  CFLAGS += -pthread
  LD_WARN_COMMON=-Wl,-warn-common
endif

ifeq ($(STDCPP11),true)
  CFLAGS += -std=c++11 -std=c++1y
else
  CFLAGS += -std=c++0x -DGTEST_HAS_TR1_TUPLE=0 # required to build tests with gtest
endif


# Local Environment
CPP_BASE=$(TOP)/../source/cpp
CORE_CPP_BASE=$(TOP)/source/cpp
DIR=$(CPP_BASE)
TEST_DIR=$(DIR)/test
BUILD_DIR=$(DIR)/$(BUILDDIR)
CORE_BUILD_DIR=$(CORE_CPP_BASE)/liburb/build
LIB_PATH=$(CORE_BUILD_DIR)
INC_DIR=$(CORE_BUILD_DIR)/include
LOCAL_INC=-I$(INC_DIR) -I$(INC_DIR)/common

MESOS_DIR=$(INC_DIR)/mesos

 ## Test Sources and programs
# randomize test order
TEST_SRCS=$(shell for f in `find $(TEST_DIR) -name '*.cpp' -print`; do echo "$$RANDOM $$f"; done | sort -n | cut -d' ' -f2)
#TEST_SRCS=$(shell find $(TEST_DIR) -name '*.cpp')
TESTS=$(subst $(TEST_DIR)/,,$(TEST_SRCS))
TEST_PROGS=$(addprefix $(BUILD_DIR)/,$(subst .cpp,.test, $(TESTS)))
TEST_OUTPUTS=$(filter $(BUILD_DIR)/test_%,$(addsuffix .xml,$(TEST_PROGS)))
VALGRIND_OUTPUTS=$(filter $(BUILD_DIR)/test_%,$(addsuffix .valgrind,$(TEST_PROGS)))

REDIS3M_BASE=$(CORE_CPP_BASE)/3rdparty/redis3m
REDIS3M_INC=-I$(REDIS3M_BASE)/include
PROTO_NAME=protobuf-2.6.1
PROTO_BASE=$(CORE_CPP_BASE)/3rdparty/$(PROTO_NAME)/build/$(PROTO_NAME)
PROTO_INC=-I$(PROTO_BASE)/src
GTEST_BASE=$(PROTO_BASE)
GTEST_INC=-I$(GTEST_BASE)/gtest/include
GTEST_LIB=-L$(GTEST_BASE)/gtest/lib/.libs -lgtest -lgtest_main
GLOG_BASE=$(CORE_CPP_BASE)/3rdparty/glog-0.3.3
GLOGINC=-I$(GLOG_BASE)/src -I$(GLOG_BASE)/$(BUILDDIR)/src
REDIS_BASE=$(CORE_CPP_BASE)/3rdparty/redis
REDIS_BIN=$(REDIS_BASE)/build/redis-2.8.18/src
ifdef BOOST_ROOT
BOOST_INC=-I$(BOOST_ROOT)
endif

EXT_INC=$(GLOGINC) $(PROTO_INC) $(REDIS3M_INC)
INCS=$(LOCAL_INC) $(EXT_INC) $(BOOST_INC)
TEST_INCS=$(INCS) $(GTEST_INC) -I$(MESOS_DIR)

ifeq ($(shell uname -s),SunOS)
TEST_LIBS=$(GTEST_LIB) -lpthread -lev -lsocket -lnsl -lresolv
else
TEST_LIBS=$(GTEST_LIB) -lpthread -lev
endif

# Build everthing
default: $(BUILDDIR) $(TEST_PROGS)

# Make the root build directory, copy mesos include file dependencies and apply stout patch
$(BUILDDIR):
	mkdir -p $@

# Link our test programs
$(BUILD_DIR)/%.test: $(TEST_DIR)/%.cpp
	cd $(BUILD_DIR) && g++ $(CFLAGS) $(TEST_INCS) $(LD_WARN_COMMON) -Wl,-rpath,`pwd` $< -L$(LIB_PATH) -lurb $(TEST_LIBS) -o $@

# Standard clean rules
distclean clean:
	rm -rf $(BUILDDIR)

start_redis:
	if [ "$$($(REDIS_BIN)/redis-cli ping)" != "PONG" ]; then $(REDIS_BIN)/redis-server& fi

stop_redis:
	if [ "$$($(REDIS_BIN)/redis-cli ping)" = "PONG" ]; then $(REDIS_BIN)/redis-cli shutdown fi

# Run our test programs.  Always remove the outputs so we allways will rerun
test: $(BUILDDIR) start_redis rmtest $(TEST_OUTPUTS)
#	-qdel executor_runner.py
	-jobid=$(qstat -f -q *@$$(hostname) | grep '^[ \t]\+[0-9]\+[ \t]' | awk '/executor_runner.py/ {print $$1}') ; if [ ! -z "$$jobid" ]; then for j in $$jobid; do qdel $$j; done; fi
	$(REDIS_BIN)/redis-cli flushdb; $(REDIS_BIN)/redis-cli shutdown

# Remove test results so we can always rerun tests
rmtest: start_redis
	rm -f $(TEST_OUTPUTS)
#	-qdel executor_runner.py
	-jobid=$(qstat -f -q *@$$(hostname) | grep '^[ \t]\+[0-9]\+[ \t]' | awk '/executor_runner.py/ {print $$1}') ; if [ ! -z "$$jobid" ]; then for j in $$jobid; do qdel $$j; done; fi
	$(REDIS_BIN)/redis-cli flushdb

# Run all of the test programs trying to build XML test output
$(BUILD_DIR)/%.test.xml: $(BUILDDIR)/%.test
	PYTHON=$(PYTHON) LD_LIBRARY_PATH=$(LIB_PATH) $< --gtest_output=xml:$@

# Run tests with valgrind
$(BUILD_DIR)/%.test.valgrind: $(BUILDDIR)/%.test
	PYTHON=$(PYTHON) LD_LIBRARY_PATH=$(LIB_PATH) valgrind --read-var-info=yes --track-origins=yes --xml=yes --xml-file=$@ $<
#	PYTHON=$(PYTHON) LD_LIBRARY_PATH=$(BUILDDIR) valgrind --leak-check=full --log-file=$@ $<

valgrind: $(VALGRIND_OUTPUTS)


# Helper goal to print environment
env:
	@echo TOP: $(TOP)
	@echo TEST_SRCS: $(TEST_SRCS)
	@echo TESTS: $(TESTS)
	@echo TEST_PROGS: $(TEST_PROGS)
	@echo BUILDDIR: $(BUILDDIR)
	@echo TEST_OUTPUTS: $(TEST_OUTPUTS)
	@echo DIR: $(DIR)
	@echo MESOS_DIR: $(MESOS_DIR)
	@echo INC_DIR: $(INC_DIR)
	@echo CPP_BASE: $(CPP_BASE)
	@echo CFLAGS: $(CFLAGS)
	@echo CXXFLAGS: $(CXXFLAGS)
	@echo GCCVERSION: $(GCCVERSION)
	@echo EXT_MESOS_VERSION: $(EXT_MESOS_VERSION)
