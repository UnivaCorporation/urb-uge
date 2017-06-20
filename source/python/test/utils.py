#!/usr/bin/env python
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

import os
import os.path
import sys
import subprocess
import socket
from tempfile import NamedTemporaryFile

from nose import SkipTest
from nose.tools import make_decorator

REDIS_HOST = "localhost"
REDIS_PORT = 6379

#CONFIG_FILE = '/tmp/urb.test.conf'
CONFIG_FILE = 'urb.cfg'
LOG_FILE = '/tmp/urb.test.log'


sys.path.append('../../urb-core/source/python/test')
from common_utils import run_command
from common_utils import read_last_line


def add_job_class(name="TestFramework"):
    host = socket.gethostname().split(".")[0]
    jc_name = "%s_%s" % (name, host)
    print "Adding %s job class" % jc_name
    run_command("qconf -sjc template | sed 's|jcname.*|jcname          %s|;s|CMDNAME.*$|CMDNAME         /opt/uge/examples/jobs/sleeper.sh|;s|CMDARG.*$|CMDARG          1|' > /tmp/%s.jc" % (jc_name, jc_name))
    run_command("qconf -Ajc /tmp/%s.jc" % jc_name)
    return jc_name

def remove_job_class(jc_name="TestFramework_%s" % socket.gethostname().split(".")[0]):
    print "Removing %s job class" % jc_name
    run_command("qconf -djc %s" % jc_name)
    run_command("rm -f /tmp/%s.jc" % jc_name)

def needs_uge(func):
    def inner(*args,**kwargs):
#        from urb.adapters.gridengine import GridEngine
        from uge_adapter.gridengine import GridEngine
        try:
            uge = GridEngine("SGE")
            uge.qstat('-f')
        except:
            raise SkipTest('UGE is not available.')
        return func(*args,**kwargs)
    return make_decorator(func)(inner)

def needs_uge_job_class(func, name="TestFramework"):
    def inner(*args,**kwargs):
        from urb.adapters.gridengine import GridEngine
        try:
            uge = GridEngine("SGE")
            host = socket.gethostname().split(".")[0]
            jc_name = "%s_%s" % (name, host)
            uge.qconf('-sjc %s' % jc_name)
        except:
            raise SkipTest('UGE %s job class is not available.' % jc_name)
        return func(*args,**kwargs)
    return make_decorator(func)(inner)

# Testing
if __name__ == '__main__':
    print 'Last line: ', read_last_line('/tmp/urb.log')

