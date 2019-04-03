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

from urb.adapters.adapter_interface import Adapter
from urb.messaging.channel_factory import ChannelFactory
from gridengine import GridEngine
from urb.log.log_manager import LogManager
from urb.config.config_manager import ConfigManager
from urb.exceptions.unknown_job import UnknownJob
from urb.exceptions.pending_job import PendingJob
from urb.utility.value_utility import ValueUtility
import gevent
import xmltodict
import json
import time
import socket
import os
import re

class UGEAdapter(Adapter):
    """ UGE Adapter class. """

    QDEL_WAIT_PERIOD_IN_SECONDS = 2.0

    def __init__(self):
        self.logger = LogManager.get_instance().get_logger(
            self.__class__.__name__)
        self.uge = GridEngine("SGE")
        self.channel_name = None
        self.configure()
        cf = ChannelFactory.get_instance()
        self.redis_host = cf.get_message_broker_connection_host()
        self.redis_ip = socket.gethostbyname(self.redis_host)

    def configure(self):
        cm = ConfigManager.get_instance()
        use_sudo = cm.get_config_option('UGEAdapter', 'use_sudo', 
            default_value='True')
        self.use_sudo = ValueUtility.to_boolean(use_sudo)
        self.logger.debug('Using sudo: %s' % self.use_sudo)
        self.urb_root = cm.get_root()

    def set_channel_name(self, channel_name):
        self.channel_name = channel_name

    def authenticate(self, request):
        self.logger.trace('Authenticate: %s' % request)

    def deactivate_framework(self, request):
        self.logger.trace('Deactivate framework: %s' % request)

    def exited_executor(self, request):
        self.logger.trace('Exited executor: %s' % request)

    def kill_task(self, request):
        self.logger.trace('Kill task: %s' % request)

    def launch_tasks(self, framework_id, tasks, *args, **kwargs):
        self.logger.trace('Launch tasks for framework id: %s' % framework_id)

    def reconcile_tasks(self, request):
        self.logger.trace('Reconcile tasks: %s' % request)
        # indicate that job status reasonably can be retrieved on adapter level (get_job_status)
        # after some time
        return (True, 2)

    def register_executor_runner(self, framework_id, slave_id, *args, 
            **kwargs):
        self.logger.trace(
            'Register executor runner for framework id %s, slave id %s' %
            (framework_id, slave_id))

    def register_framework(self, max_tasks, concurrent_tasks, framework_env, user=None, *args, **kwargs):
        self.logger.info("register_framework: kwargs: %s" % kwargs)
        job_class = kwargs.get('job_class')
        if job_class is None:
            self.logger.error("UGEAdapter: job class is not defined")
            return
        self.logger.debug('Job class: %s' % job_class)
        options = []
        job_submit_options = kwargs.get("job_submit_options")
        # remove spaces if any from the beginning and end
        if job_submit_options:
            job_submit_options = job_submit_options.strip()
            if '-cwd' in job_submit_options:
                self.logger.info('UGE option -cwd filtered out form job_submit_options')
                job_submit_options = job_submit_options.replace('-cwd', '')
            if '-wd' in job_submit_options:
                self.logger.info('UGE option -wd filtered out form job_submit_options')
                job_submit_options = re.sub('-wd\s+(.+?)(\.[^.]*\s|\s|$)', '', job_submit_options)
            if len(job_submit_options) != 0:
                options.append(job_submit_options)

        tasks = kwargs.get('tasks')
        if tasks is not None:
            if len(tasks) > 1:
                self.logger.warn("multiple tasks per submission")
            task = tasks[0]
            resources = task.get('resources')
            resource_mapping = kwargs.get('resource_mapping')
            if resources is not None and len(resource_mapping) > 0:
                resource_mapping_list = resource_mapping.split(';')
                self.logger.debug("resource_mapping_list=%s" % resource_mapping_list)
                resourse_options = []
                mem = None
                slots = None
                gpus = None
                for resource in resources:
                    if resource['name'] == 'mem':
                        mem = int(resource['scalar']['value'])
                    elif resource['name'] == 'cpus':
                        cpus = float(resource['scalar']['value'])
                        if cpus >= 1.5:
                            slots = int(round(cpus))
                    elif resource['name'] == 'gpus':
                        gpus = int(resource['scalar']['value'])

                if slots is not None:
                    if 'soft' in resource_mapping_list:
                        self.logger.debug("For soft resource mapping parallel environment will not be used")
                    elif 'hard' in resource_mapping_list:
                        resourse_options.append("-pe URBDefaultPE %s" % str(slots))
                if mem is not None:
                    if 'soft' in resource_mapping_list:
                        resourse_options.append("-soft -l m_mem_free=%sM" % mem)
                    elif 'hard' in resource_mapping_list:
                        # scale down to number of slots
                        if slots is not None:
                            mem = int(round(mem/slots))
                        resourse_options.append("-hard -l m_mem_free=%sM" % mem)
                if gpus is not None:
                    rsmap = None
                    for l in resource_mapping_list:
                        self.logger.debug("gpus l=%s" % l)
                        if l.startswith("gpus:"):
                            rsmap = l[5:]
                            self.logger.debug("rsmap=%s" % rsmap)
                            break
                    if rsmap:
                        resourse_options.append("-hard -l %s=%d" % (rsmap, gpus))
                    else:
                        self.logger.error("Cannot find 'gpus' specifier for UGE RSMAP in resource_mapping")
                        return []

                for r in [ "soft", "hard" ]:
                    if r in resource_mapping_list:
                        resource_mapping_list.remove(r)

                for custom_resource in kwargs.get("custom_resources", {}):
                    for rm in resource_mapping_list:
                        self.logger.debug("custom_resource=%s, rm=%s" % (custom_resource, rm))
                        rm_elements = rm.split(':')
                        rm_len = len(rm_elements)
                        idx = 0
                        name = rm_elements[idx] if idx < rm_len else None
                        if custom_resource != name:
                            continue
                        idx = idx + 1
                        rsmap = rm_elements[idx] if idx < rm_len else None
                        if not rsmap:
                            continue
                        idx = idx + 1
                        val = rm_elements[idx] if idx < rm_len else None
                        if not val:
                            val = "1"
                        self.logger.debug("name=%s, rsmap=%s, val=%s" % (name, rsmap, val))
                        resourse_options.append("-hard -l %s=%s" % (rsmap, val))

                options.extend(resourse_options)

            if 'container' in task:
                self.logger.debug("container: %s" % task['container'])
                container_type = task['container'].get('type')
                if container_type is not None and container_type == 'DOCKER':
                    docker = task['container'].get('docker')
                    if docker is not None and 'image' in docker:
                        # -soft enables downloading remote images but requires tag
                        # make sure that not -q or -l options appended after it so they
                        # do not become soft requirements
                        image = docker['image']
                        pos = image.rfind('/')
                        if pos != -1:
                            pos = image.rfind(':', pos)
                        else:
                            pos = image.rfind(':')
                        if pos == -1:
                            image += ':latest'

                        docker_args = '-l docker -soft -l docker_images=*%s*' % image

                        if 'network' in task['container']['docker']:
                            network = task['container']['docker']['network']
                            docker_args += ' -xd --net=%s' % network.lower()

                        if 'port_mappings' in task['container']['docker']:
                            for port_mapping in task['container']['docker']['port_mappings']:
                                host_port = port_mapping['host_port']
                                container_port = port_mapping['container_port']
                                docker_args += ' -xd --publish=%s:%s' % (host_port, container_port)
                                if 'protocol' in port_mapping:
                                    protocol = port_mapping['protocol']
                                    docker_args += '/%s' % protocol

                        if 'privileged' in task['container']['docker']:
                            privileged = task['container']['docker']['privileged']
                            if privileged == True:
                                docker_args += ' -xd --privileged'

                        parameters = task['container']['docker'].get('parameters', [])
                        for parameter in parameters:
                            key = parameter['key']
                            value = parameter['value']
                            docker_args += ' -xd --%s=%s' % (key, value)

                        force_pull_image = True if 'force_pull_image' in task['container']['docker'] else False

                        #volume_driver = task['container']['docker'].get('volume_driver', '')

                        uge_root = self.get_uge_root()
                        # mount user home directory
                        user_home = os.path.expanduser('~' + user)
                        docker_args += ' -xd --volume=%s:%s:rw' % (user_home, user_home)
                        # mount URB root directory
                        docker_args += ' -xd --volume=%s:%s:rw' % (self.urb_root, self.urb_root)
                        # mount UGE root directory
                        docker_args += ' -xd --volume=%s:%s:rw' % (uge_root, uge_root)

                        if 'volumes' in task['container']:
                            for volume in task['container']['volumes']:
                                container_path = volume.get('container_path', '')
                                host_path = volume.get('host_path', container_path)
                                mode = volume.get('mode', 'rw').lower()
                                docker_args += ' -xd --volume=%s:%s:%s' % (host_path, container_path, mode)

                        if 'hostname' in task['container']:
                            docker_args += ' -xd --hostname=%s' % task['container']['hostname']

                        network_infos = task['container'].get('network_infos', [])
                        for network_info in network_infos:
                            for ip_address in network_info.get('ip_addresses', []):
                                if 'ip_address' in ip_address:
                                    ip_addr = ip_address['ip_address']
                                    docker_args += ' -xd --ip=%s' % ip_addr

                        # put UGE output files to home directory
                        docker_args += " -o %s -e %s" % (user_home, user_home)

                        # add redis host
                        docker_args += ' -xd --add-host=%s:%s' % (self.redis_host, self.redis_ip)

                        # allocate pseudo tty to be able to run sudo in container (use UGE option instead of docker -t)
                        docker_args += ' -pty y'
                        self.logger.debug("Docker args: %s" % docker_args)
                        options.append(docker_args)
                    else:
                        self.logger.error("Container image is not specified")
                else:
                    self.logger.debug("Not DOCKER container type: %s" % container_type)

        job_submit_clear = kwargs.get("job_submit_clear", True)
        return self.__submit_jobs(job_class, max_tasks, concurrent_tasks, options, framework_env, job_submit_clear, user)

    def __submit_jobs(self, job_class, max_tasks, concurrent_tasks, options, env, job_submit_clear, user=None):
        uge_cmd = ''
        if job_submit_clear:
            uge_cmd += '-clear '
        uge_cmd += '-v %s -terse -jc %s' % (" -v ".join([k+"="+v for k, v in env.items()]), job_class)
        if len(options) > 0:
            uge_cmd = "%s %s" % (uge_cmd, " ".join(options))
        uge_ids = []
        for i in range(0,concurrent_tasks):
            if i >= max_tasks:
                break
            self.logger.info('Submit job: user=%s, UGE command: %s' % (user, uge_cmd))
            ret_str = self.uge.sub_cmd(str(uge_cmd), use_sudo=self.use_sudo, user=user)
            self.logger.debug('Got job id string: %s' % ret_str)
            # it may contain some extra output from jsv script, the last non empty line should be a job id
            job_id_str = [s for s in ret_str.split('\n') if s != ''][-1]
            parts = job_id_str.split(".",1)
            job_id = parts[0].strip()
            if len(parts) > 1:
                task_str = parts[1]
                task_range,task_step = task_str.split(":")
                task_range = task_range.split("-")
                task_range = (int(task_range[0].strip()), int(task_range[1].strip()))
                task_step = int(task_step.strip())
                uge_id = (job_id,task_range,task_step)
            else:
                uge_id = (job_id,None,None)
            self.logger.info('Submitted job to UGE, got id: %s' % uge_id[0])
            uge_ids.append(uge_id)
        return uge_ids

    def register_slave(self, request):
        self.logger.trace('Register slave: %s' % request)

    def reregister_framework(self, request):
        self.logger.trace('Reregister framework: %s' % request)

    def reregister_slave(self, request):
        self.logger.trace('Reregister slave: %s' % request)

    def resource_request(self, request):
        self.logger.trace('Resource request: %s' % request)

    def revive_offers(self, request):
        self.logger.trace('Revive offers: %s' % request)

    def submit_scheduler_request(self, request):
        self.logger.trace('Submit scheduler request: %s' % request)

    def status_update_acknowledgement(self, request):
        self.logger.trace('Status update acknowledgement: %s' % request)

    def status_update(self, request):
        self.logger.trace('Status update: %s' % request)

    def scale(self, framework, count):
        return
        if framework.has_key('job_ids'):
            self.logger.debug('Scaling framework: %s by: %d' % (framework['name'],count))
            current_count = framework.get('concurrent_tasks',1)
            framework['concurrent_tasks'] = current_count + count
            self.uge.qalter("-tc %d %s" % (framework['concurrent_tasks'],framework['job_ids'][0]))

    def unregister_framework(self, framework):
        self.logger.debug('Unregister framework: %s' % framework['name'])
        self.delete_jobs_delay(framework)

    def delete_jobs_delay(self, framework):
        # Delete all of the uge jobs
        uge_ids = framework.get('job_ids')
        if uge_ids is not None:
            # Spawn job to make sure the actual executors exit...
            gevent.spawn(self.delete_jobs_tuple, uge_ids)

    def delete_jobs_tuple(self, job_ids):
        # take an id as first element of the tuple
        jobs_id_list = [str(j[0]) for j in job_ids]
        try:
            self.delete_jobs(jobs_id_list)
        except Exception, ex:
            self.logger.warn("Error deleteing job: %s" % ex)

    def delete_jobs(self, job_ids):
        self.logger.debug('Deleting jobs: %s', job_ids)
        jobs_str = ",".join(job_ids)
        if len(str(jobs_str)) != 0:
            try:
                self.uge.qhold('%s' % jobs_str)
            except Exception, ex:
                self.logger.warn("Error holding job: %s" % ex)
                #self.logger.exception(ex)
            gevent.sleep(UGEAdapter.QDEL_WAIT_PERIOD_IN_SECONDS)
            try:
                self.uge.del_cmd('%s' % jobs_str)
            except Exception, ex:
                self.logger.warn("Error calling qdel: %s" % ex)
                #self.logger.exception(ex)
        else:
            self.logger.warn("Deleting jobs: '%s' - empty job id string", job_ids)

    def submit_job(self, job_command):
        self.logger.debug('Submitting job: %s', job_command)
        job_id_str = self.uge.sub_cmd(str(job_command))
        job_id_str = job_id_str.replace('\n', '')
        self.logger.debug('Job id: %s', job_id_str)
        return job_id_str

    def get_job_id_tuple(self, job_id):
        # Try to get job status and extract task array info
        # If things do not work, assume no task array
        uge_id = (job_id,None,None)
        try:
            job_status_dict = self.get_job_status(job_id)
            is_array = job_status_dict.get('detailed_job_info').get('djob_info').get('element').get('JB_is_array', False)
            is_array = ValueUtility.to_boolean(is_array)
            if is_array is True:
                self.logger.debug('Determining ja structure for job %s' % job_id)
                ja_structure = job_status_dict.get('detailed_job_info').get('djob_info').get('element').get('JB_ja_structure').get('element')
                rn_min = ja_structure.get('RN_min')
                rn_max = ja_structure.get('RN_max')
                rn_step = ja_structure.get('RN_step')
                task_range = (int(rn_min.strip()), int(rn_max.strip()))
                task_step = int(rn_step.strip())
                uge_id = (job_id,task_range,task_step)
                self.logger.debug("Determined job id %s tuple: %s-%s:%s" % (job_id, rn_min, rn_max, rn_step))
            else:
                self.logger.debug("Job id %s is not array job" % (job_id))
        except Exception, ex:
            self.logger.warn("Cannot determine job id %s tuple: %s" % (job_id, ex))
        return uge_id

    def get_job_status(self, job_id):
        self.logger.info('Getting status for job: %s', job_id)
        status = self.uge.qstat('-j %s -xml' % str(job_id))

        # Parse xml
        job_status_dict = xmltodict.parse(status)

        # Convert to json and back is the simplest way to turn 
        # ordered dicts into standard dicts
        # Strinctly speaking this is not needed, but OrderedDicts
        # look more complex when printed out 
        job_status_dict = json.loads(json.dumps(job_status_dict))
        if job_status_dict.get('unknown_jobs') is not None:
            raise UnknownJob('Unknown job id: %s' % job_id)

        self.logger.trace('Job status: %s', job_status_dict)

        if not job_status_dict.get('detailed_job_info').get('djob_info').get('element').get('JB_ja_tasks'):
            raise PendingJob('Pending job: %s' % job_id)

        return job_status_dict

    def get_job_accounting(self, job_id):
        self.logger.info('Getting accounting for job: %s', job_id)
        acct = {}
        try:
            acct_str = self.uge.qacct('-j %s' % str(job_id))
            acct_line_list = acct_str.split('\n')
            for line in acct_line_list:
                if not line:
                    break
                if not line.startswith('='):
                    word_list = line.split()
                    key = word_list[0]
                    value = ' '.join(word_list[1:])
                    acct[key] = value.strip()
        except Exception, ex:
            self.logger.debug('Failed to get accounting for job %s: %s' % (ex, job_id))
        return acct

    def unregister_slave(self, request):
        self.logger.debug('Unregister slave: %s' % request)

    def analyze_job_status_for_host(self, job_status_dict, host):
        djob_info = job_status_dict.get('detailed_job_info').get('djob_info').get('element')
        is_array = djob_info.get('JB_is_array')
        tasks = djob_info.get('JB_ja_tasks').get('ulong_sublist')
        if is_array == 'false':
            tasks = [tasks]
        now = time.time()
        cpu_average = 0
        mem_average = 0
        for t in tasks:
            start_time = float(t.get('JAT_start_time'))
            delta_t = now - start_time
            task_number = t.get('JAT_task_number')
            usage_list = t.get('JAT_scaled_usage_list').get('scaled')
            identifier_list = t.get('JAT_granted_destin_identifier_list').get('element')
            task_host = identifier_list.get('JG_qhostname')
            # Only analyze tasks on a given host
            if task_host != host:
                continue
            for u in usage_list:
                u_name = u.get('UA_name')
                if u_name == 'cpu':
                    u_value = float(u.get('UA_value'))
                    # value is integrated cpu seconds, so divide by time
                    # to get average cpu used
                    task_cpu_average = u_value/delta_t
                    cpu_average += task_cpu_average
                elif u_name == 'mem':
                    # value is integrated GB seconds, so divide by time
                    # to get average GB used
                    u_value = float(u.get('UA_value'))
                    task_mem_average = u_value/delta_t
                    mem_average += task_mem_average
        return {'cpu_average' : cpu_average, 'mem_average' : mem_average}

    def config_update(self):
        self.logger.debug("Configuration update")

    def get_uge_root(self):
        return self.uge.get_uge_root()


# Testing
if __name__ == '__main__':
    adapter = UGEAdapter()
    #print adapter.get_job_id_tuple(431)
    #job_id = adapter.submit_job('-terse -b y /bin/sleep 15')
    #print 'Sleeping for 10 seconds'
    #gevent.sleep(10)
    #print adapter.get_job_status(job_id)
    #gevent.sleep(30)
    #print adapter.get_job_accounting(job_id)
    #job_id = gevent.spawn(adapter.delete_job, job_id)
    #print 'Sleeping for 5 seconds'
    #gevent.sleep(5)
    print 'Done'


