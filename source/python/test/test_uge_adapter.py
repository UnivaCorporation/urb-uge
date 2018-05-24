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

import socket
import gevent
import os
import sys
# add path to test util
sys.path.append('../../urb-core/source/python/test')
# add path to urb
sys.path.append('../../urb-core/source/python')
from utils import needs_uge
from utils import needs_uge_job_class
from utils import add_job_class
from utils import remove_job_class
from uge_adapter.uge_adapter import UGEAdapter
from urb.messaging.channel_factory import ChannelFactory
from urb.config.config_manager import ConfigManager
from urb.utility.framework_tracker import FrameworkTracker
from uge_adapter.gridengine import UGECommandExecError
from urb.exceptions.urb_exception import URBException
from urb.exceptions.unknown_job import UnknownJob

os.environ["URB_CONFIG_FILE"] = os.path.dirname(os.path.realpath(__file__)) + "/urb.conf"


@needs_uge
def test_job_management():
    adapter = UGEAdapter()
    print 'Submitting job'
    job_id = adapter.submit_job('-terse -b y /bin/sleep 60')
    print 'Got job id: ', job_id
    assert job_id != None
    gevent.sleep(3)
    print 'Job status: ', adapter.get_job_status(job_id)
    gevent.spawn(adapter.delete_jobs, [job_id])
    gevent.sleep(3)
    print 'Deleted job: ', job_id

#@needs_uge_job_class
def test_register_framework():
    print 'Registering framework'
    jc_name = add_job_class('TestFramework')
    cm = ConfigManager.get_instance()
    cf = ChannelFactory.get_instance()
    framework_env = {
        'URB_CONFIG_FILE' : cm.get_config_file(),
        'URB_FRAMEWORK_ID' : '1',
        'URB_MASTER' : cf.get_message_broker_connection_url(),
    }
    adapter = UGEAdapter()
    max_tasks = 5
    concurrent_tasks = 1
    job_submit_options = '-l h=%s' % socket.gethostname()
    kwargs = {"job_class":jc_name,
              "job_submit_options":job_submit_options};
    uge_id = adapter.register_framework(max_tasks, concurrent_tasks, framework_env, **kwargs)
    print 'UGE ID: ', uge_id
    framework = {
        'uge_id' : uge_id, 
        'name' : jc_name,
        'id' : {'value' : 1},
        'config' : {'mem' : 1024, 'disk' : 16384, 'cpus' : 1, 
                    'ports' : '[(30000,31000)]',
                    'max_rejected_offers' : 1,
                    'max_tasks' : 5
        }
    }
    FrameworkTracker.get_instance().add(1, framework)
    assert uge_id != None

#@needs_uge_job_class
def test_unregister_framework():
    framework = FrameworkTracker.get_instance().get(1)
    print 'Unregistering framework: ', framework
    jc_name = framework.get('name')
    uge_id = framework.get('uge_id')
    assert uge_id != None
    adapter = UGEAdapter()
    adapter.unregister_framework(framework)
    gevent.sleep(3)
    for i in range(0,12):
        try:
            job_id = list(uge_id)[0]
            job_id = job_id[0]
            adapter.get_job_status(job_id)
        except UnknownJob, ex:
            # ok
            break
        gevent.sleep(1)
    else:
        remove_job_class(jc_name)
        raise URBException('Job id %s was not deleted' % job_id)
    remove_job_class(jc_name)
    print 'Job %s was deleted' % job_id

# Testing
if __name__ == '__main__':
    pass
