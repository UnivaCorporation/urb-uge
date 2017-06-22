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
import sys
import struct
import socket
import redis
import json
import time
import threading
import signal
import subprocess
import datetime

# Endpoint constants
base_endpoint = 'urb.endpoint.'
master_endpoint = base_endpoint+ '0'
mesos_channel = master_endpoint + ".mesos"

# Some globals
master_hostname = socket.gethostname()
sub_id = 0
available_cores = 1

frameworks = {}
executors = {}
slaves = {}
tasks = {}
running_tasks = {}
executor_runners = {}
launched_runners = {}
schedulers = {}
offers = {}
uge_jobs = {}

timers = {}

def sig_handler(signum,frame):
    print "Got sig int... canceling timers"
    for k,v in timers.items():
        v.cancel()
    sys.exit(0)

# Helper to print common messages
def print_message(message):
    print "<", datetime.datetime.now().time(), "> ", message
    print

def send_offer(r,response_channel,id,framework_id,slave_id):
    global sub_id


    # Now send some offers...
    offer = {}
    offer['id'] = { 'value': 'offer-'+id +'.' + str(sub_id) }
    offer['framework_id'] = framework_id
    offer['slave_id'] = slave_id
    offer['hostname'] = master_hostname

    resource_cpu = {}
    resource_cpu['name'] = "cpus"
    resource_cpu['scalar'] = { 'value': available_cores }
    resource_cpu['type'] = "SCALAR"
    resource_cpu['role'] = "*"

    resource_mem = {}
    resource_mem['name'] = "mem"
    resource_mem['scalar'] = { 'value': 19200 }
    resource_mem['type'] = "SCALAR"
    resource_mem['role'] = "*"

    resource_disk = {}
    resource_disk['name'] = "disk"
    resource_disk['scalar'] = { 'value': 10000 }
    resource_disk['type'] = "SCALAR"
    resource_disk['role'] = "*"

    resource_ports = {}
    resource_ports['name'] = "ports"
    resource_ports['ranges'] = { 'range': [{'begin': 31000, 'end':32000 }]}
    resource_ports['type'] = "RANGES"
    resource_ports['role'] = "*"

    offer['resources'] = [ resource_cpu, resource_mem,resource_disk,resource_ports ]

    offers[offer['id']['value']] = offer
    # Build som response messages
    offer_message = {}
    offer_message['offers'] = [offer]
    payload = offer_message
    resp = { 'source_id' : mesos_channel, 'target':"ResourceOffersMessage", 'payload_type':"json",
             'payload': payload }
    print_message( "Sending offer message to " + response_channel + ": " + str(resp))
    r.lpush(response_channel, json.dumps(resp))
    sub_id += 1
    if timers.get(slave_id['value']):
        timers[slave_id['value']].cancel()
    timers[slave_id['value']] = threading.Timer(10.0, send_offer, [r,response_channel,id,framework_id,slave_id])
    timers[slave_id['value']].start()
def run_task(r,response_channel,framework_id):
    global available_cores
    # Now we can push the runTasks to the executor
    for executor_runner_channel,task in tasks.items():
        executor_channel = executors.get(executor_runner_channel)
        if executor_channel != response_channel:
            # Not for us
            continue

        # This task is for us...
        run_task = {
            'framework_id' : framework_id,
            'framework'    : frameworks[framework_id['value']],
            'pid'          : "1234",
            'task'         : task
        }
        payload =  run_task
        resp = { 'source_id' : mesos_channel, 'target':"RunTaskMessage", 'payload_type':"json",
             'payload': payload }
        # Can be huge...
        #print_message( "Sending RunTask message: " + str(resp))
        print_message( "Sending RunTask message")
        r.lpush(response_channel, json.dumps(resp))
        running_tasks[executor_runner_channel] = task
        del tasks[executor_runner_channel]
        available_cores -= 1

# Main application logic
def main(one_shot=False):
    #install signal handler
    signal.signal(signal.SIGINT, sig_handler)

    global available_cores
    # Connect to redis
    r = redis.StrictRedis(host=master_hostname, port=6379, db=0)
    progress = 1

    # My directory
    mydir = os.path.dirname(os.path.realpath(__file__))

    sys.stdout.write("Waiting for clients.... -\r")
    sys.stdout.flush()
    # Loop forever
    while True:
        didWork = False
        # Lets wait for some register messages
        m = r.brpop(mesos_channel,1)
        if m:
            m=m[1]
        # No message... Print some progress and try again later
        if m == None:
            progress_array = [ '-', '\\', '|', '/' ]
            sys.stdout.write("Waiting for clients.... %s   \r" % (progress_array[progress]) )
            sys.stdout.flush()
            #time.sleep(1);
            progress = (progress + 1) % 4
            continue

        # Common message handling
        urb_message = {}
        try:
            urb_message = json.loads(m)
        except:
            print_message( "Error Parsing json.  Storing to redis error list")
            r.lpush('urb_errors',m)
            continue
        base1, base2, id = urb_message['source_id'].split('.')
        # Channel global callback
        notify_response_channel = "urb.endpoint." + id + ".notify"
        # Override reply channel if supplied
        response_channel = urb_message.get("reply_to")
        if response_channel == None:
            response_channel = notify_response_channel
        print

        # Handle Register message
        if  urb_message['target'] == "RegisterFrameworkMessage" or urb_message['target'] == "ReregisterFrameworkMessage":
            target = "FrameworkRegisteredMessage"
            if urb_message['target'] == "RegisterFrameworkMessage":
                print_message( "Received register message: " + str(urb_message))
                framework_id = {}
                framework_id['value'] = 'framework-' + id;
                frameworks[framework_id['value']] = urb_message['payload']['mesos.internal.RegisterFrameworkMessage']['framework']
                frameworks[framework_id['value']]["id"] = framework_id
                # Keep track of allocated slaves
                launched_runners[framework_id['value']] = set()
            else:
                print_message( "Received reregister message: " + str(urb_message))
                target = "FrameworkReregisteredMessage"
                f = urb_message['payload']['mesos.internal.ReregisterFrameworkMessage']
                framework_id = {}
                framework_id['value'] = 'framework-' + id;
                frameworks[framework_id['value']] = f['framework']

            schedulers[framework_id['value']] = response_channel
            int_addr = struct.unpack("!I", socket.inet_aton(socket.gethostbyname(r.connection_pool.connection_kwargs['host'])))[0]
            master_info = {}
            master_info["id"] = 'master-' + r.connection_pool.connection_kwargs['host']
            master_info["ip"] = int_addr
            master_info["port"] = int(r.connection_pool.connection_kwargs['port'])
            master_info["hostname"] = r.connection_pool.connection_kwargs['host']

            # Build response message
            register_message = {
              'framework_id' : framework_id,
              'master_info'  : master_info,
            }
            payload = register_message
            resp = { 'source_id' : mesos_channel, 'target':target, 'payload_type':"json",
                     'payload': payload }
            print_message( "Sending registered/reregistered message: " + str(resp))
            r.lpush(response_channel, json.dumps(resp))

            #TODO: On regregister you may not have to do this....
            # Now submit our executor runner...
            print_message("Submitting ExecutorRunner for framework: " + framework_id["value"])
            master_url = "urb://%s:%s" % (r.connection_pool.connection_kwargs['host'],
                                    r.connection_pool.connection_kwargs['port'])
            task_env = [ "URB_MASTER="+master_url,
                         "URB_FRAMEWORK_ID="+framework_id['value'],
                         "PYTHONUNBUFFERED=1",
                       ]
            ld_path = os.environ.get("LD_LIBRARY_PATH")
            if ld_path:
                task_env.append("URB_LIB_PATH="+ld_path)
            cmd = "qsub -terse -t 1-10:1 -tc 1 -l h=" + master_hostname + " -v " + " -v ".join(task_env) + " " + mydir +"/executor_runner.py "
            p = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE)
            job_id_str = p.communicate()[0]
            # Could be of the form 447.1-10:1
            job_id, task_str = job_id_str.split(".",1)
            job_id = int(job_id.strip())
            print_message( "Grid Engine job id: " + str(job_id))
            if task_str:
                task_range,task_step = task_str.split(":")
                task_range = task_range.split("-")
                task_range = (int(task_range[0].strip()), int(task_range[1].strip()))
                task_step = int(task_step.strip())
                print_message( "Task start [%d] stop [%d] step [%d]" % ( task_range[0],task_range[1],task_step)) 
                uge_jobs[ framework_id["value"] ] = (job_id,task_range,task_step)

        elif urb_message['target'] == "LaunchTasksMessage":
            # This can be huge...so don't  print it
            #print_message( "Received launch tasks message: " + str(urb_message))
            print_message( "Received launch tasks message" )

            if urb_message['payload']['mesos.internal.LaunchTasksMessage'].has_key('filters'):
                m = urb_message['payload']['mesos.internal.LaunchTasksMessage']
                f = m['filters']
                if f and f.has_key('refuse_seconds'):
                    scheduler_channel = schedulers[m['framework_id']['value']]
                    #send_offer(r,scheduler_channel,id,m['framework_id'],offers[m['offer_id']['value']]['slave_id'])
            if not urb_message['payload']['mesos.internal.LaunchTasksMessage'].has_key('tasks'):
                print_message("No tasks to launch")
                continue
            for t in urb_message['payload']['mesos.internal.LaunchTasksMessage']['tasks']:
                #print_message ( "Launching tasks " + str(t))
                if t.has_key('command') or not t['slave_id']['value'] in launched_runners[t['executor']['framework_id']['value']]:
                    # We need to forward this on to our executor runners....
                    executor_runner_channel = executor_runners[t['slave_id']['value']]
                    resp = { 'source_id' : master_endpoint, 'target':"LaunchTasksMessage", 'payload_type':"json",
                         'payload': urb_message['payload'] }
                    # Could be huge...
                    #print_message( "Channel " + executor_runner_channel  + " Sending LaunchTasks message: " + str(resp))
                    print_message( "Channel " + executor_runner_channel  + " Sending LaunchTasks message")
                    r.lpush(executor_runner_channel, json.dumps(resp))
                    if not t.has_key('command'):
                        launched_runners[t['executor']['framework_id']['value']].add(t['slave_id']['value'])


                # If our executor is registered we can run tasks now.  This message has to go to
                # the executor though...
                executor_runner_channel = executor_runners[t['slave_id']['value']]
                executor_channel = executors.get(executor_runner_channel)
                # Now save all of the tasks
                tasks[executor_runner_channel] = t
                if executor_channel:
                    run_task(r,executor_channel,urb_message['payload']['mesos.internal.LaunchTasksMessage']['framework_id'])
        elif urb_message['target'] == "KillTaskMessage":
            print_message( "Received KillTask message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.KillTaskMessage']
            for channel,task in running_tasks.items() + tasks.items():
                if task['task_id']['value'] == m['task_id']['value']:
                    print "Found channel", channel
                    # We know about this task... lets remove it
                    # If we know about this tasks executor we should send it along
                    executor_channel = executors.get(channel)
                    if executor_channel:
                        kill_task = {}
                        kill_task['task_id'] = m['task_id']
                        kill_task['framework_id'] = m['framework_id']
                        payload = kill_task
                        resp = { 'source_id' : mesos_channel, 'target':"KillTaskMessage", 'payload_type':"json",
                           'payload': payload }
                        print_message( " Sending killtask message: " + str(resp))
                        r.lpush(executor_channel, json.dumps(resp))
                    if tasks.get(channel):
                        del tasks[channel]
                    if running_tasks.get(channel):
                        del running_tasks[channel]
            status_update = {}
            status_update['framework_id'] = m['framework_id']
            status_update['timestamp'] = time.time()
            status_update['uuid'] = "1234"
            status_update['status'] = { 'task_id' : m['task_id'], 'state' : "TASK_KILLED" }
            payload = { 'update' : status_update }
            resp = { 'source_id' : mesos_channel, 'target':"StatusUpdateMessage", 'payload_type':"json",
                     'payload': payload }
            # This needs to go to out scheduler...
            #scheduler_channel = schedulers[status_update['framework_id']['value']]
            print_message( " Sending status update message: " + str(resp))
            r.lpush(response_channel, json.dumps(resp))

        elif urb_message['target'] == "ReviveOffersMessage":
            print_message( "Received ReviveOffers message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.ReviveOffersMessage']
            for k,v in offers.items():
                if v['framework_id']['value'] == m['framework_id']['value']:
                    #This is one of my offers
                    send_offer(r,response_channel,id,m['framework_id'],offers[k]['slave_id'])

        elif urb_message['target'] == "ExecutorRegisteredMessage":
            print_message( "Received ExecutorRegisterd message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.ExecutorRegisteredMessage']
            # This came from the executor runner forward to executor
            executor_channel = executors[notify_response_channel]

            # Set the proper info
            m["framework_info"] = frameworks[m['framework_id']['value']]

            # Send to the executor
            resp = { 'source_id' : master_endpoint, 'target':"ExecutorRegisteredMessage", 'payload_type':"json",
                 'payload': m }
            print_message( "To " + executor_channel + " Sending ExecutorRegistered message: " + str(resp))
            r.lpush(executor_channel, json.dumps(resp))

            # Now we can push tasks as well
            run_task(r,executor_channel,m['framework_id'])

        elif urb_message['target'] == "RegisterExecutorMessage":
            print_message( "Received RegisterExecutor message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.RegisterExecutorMessage']

            # Save a mapping between this channel and our executor channel
            executors[response_channel] = notify_response_channel

            # Just forward to the executor runner... its endpoint should be in the reply to
            resp = { 'source_id' : master_endpoint, 'target':"RegisterExecutorMessage", 'payload_type':"json",
                 'payload': urb_message['payload'] }
            print_message( "Sending RegisterExecutor message: " + str(resp))
            r.lpush(response_channel, json.dumps(resp))
            """
            executor_key = m['executor_id']['value'] + "*" + m['framework_id']['value']
            executor_registered = {
              'executor_info' : executors[executor_key],
              'framework_id' : { 'value': m['framework_id']['value'] },
              'framework_info' : frameworks[m['framework_id']['value']],
              'slave_id' : slaves[slave_id]['id'],
              'slave_info' : slaves[slave_id],
            }
            # Make sure that our framework info Id is correct
            executor_registered['framework_info']['id'] = executor_registered['framework_id']

            # Record the executors channel
            registered_executors[m['executor_id']['value'] + "*" + m['framework_id']['value']] = \
                response_channel

            payload =  executor_registered
            resp = { 'source_id' : mesos_channel, 'target':"ExecutorRegisteredMessage", 'payload_type':"json",
                 'payload': payload }
            print_message( "Sending ExecutorRegistered message: " + str(resp))
            r.lpush(response_channel, json.dumps(resp))

            # Now we can push the runTasks to the executor
            run_task(r,response_channel,m['executor_id'],m['framework_id'])
            """
        elif urb_message['target'] == 'ReconcileTasksMessage':
            print_message( "Received Reconcile tasks message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.ReconcileTasksMessage']
            for channel,task in tasks.items():
                if task.has_key("command") or task['executor']['framework_id']['value'] != m['framework_id']["value"]:
                    #This task is not for our framework
                    continue
                # Need to send a status update message
                # Todo

        elif urb_message['target'] == 'StatusUpdateMessage':
            print_message( "Received StatusUpdate message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.StatusUpdateMessage']
            status_update = {}
            status_update['slave_id'] = m['update']['slave_id']
            status_update['framework_id'] = m['update']['framework_id']
            status_update['executor_id'] = m['update']['executor_id']
            status_update['timestamp'] = m['update']['timestamp']
            status_update['uuid'] = m['update']["uuid"]
            status_update['status'] = m['update']['status']
            payload = { 'update' : status_update }
            resp = { 'source_id' : mesos_channel, 'target':"StatusUpdateMessage", 'payload_type':"json",
                     'payload': payload }
            # This needs to go to out scheduler...
            scheduler_channel = schedulers[status_update['framework_id']['value']]
            print_message( "To channel " + scheduler_channel + " Sending status update message: " + str(resp))
            r.lpush(scheduler_channel, json.dumps(resp))
            if status_update['status']['state'] == "TASK_FINISHED":
                # This task is finished we can send some more offers
                available_cores = 1
                if available_cores > 10:
                    availabe_cores = 10
                # If the task was a command we need to mark the executor as gone...
                if not launched_runners.get(m['update']['framework_id']['value']):
                    del executor_runners[m['update']['slave_id']['value']]
                    if timers.has_key(m['update']['slave_id']['value']):
                        timers[m['update']['slave_id']['value']].cancel()
                        del timers[m['update']['slave_id']['value']]
                else:
                     timers[m['update']['slave_id']['value']].cancel()
                     del timers[m['update']['slave_id']['value']]
                     send_offer(r,scheduler_channel,id,status_update['framework_id'],status_update['slave_id'])
        elif urb_message['target'] == 'HelloMessage':
            print_message( "Received hello message: " + str(urb_message))
            m = urb_message['payload']

            # Save this slave...
            slaves[m['slave_id']['value']] = {
                'hostname' : r.connection_pool.connection_kwargs['host'],
                'port' : r.connection_pool.connection_kwargs['port'],
                'id' : m['slave_id']
            }
            #TODO: Fix this name
            executor_runners[m['slave_id']['value']] = response_channel
            # This triggers our first offer...
            # This needs to go to out scheduler...
            scheduler_channel = schedulers[m['framework_id']['value']]
            send_offer(r,scheduler_channel,id,m['framework_id'],m['slave_id'])

        elif urb_message['target'] == 'ExecutorToFrameworkMessage':
            print_message( "Received ExecutorToFramework message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.ExecutorToFrameworkMessage']
            # Forward this to the framework...
            executor_to_framework = m
            resp = { 'source_id' : mesos_channel, 'target':"ExecutorToFrameworkMessage", 'payload_type':"json",
                     'payload': m }
            scheduler_channel = schedulers[m['framework_id']['value']]
            print_message( "Sending ExecutorToFrameworkMessage: " + str(resp))
            r.lpush(scheduler_channel, json.dumps(resp))
        elif urb_message['target'] == 'FrameworkToExecutorMessage':
            print_message( "Received FrameworkToExecutor message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.FrameworkToExecutorMessage']
            # Forward this to the framework...
            framework_to_executor = m
            resp = { 'source_id' : mesos_channel, 'target':"FrameworkToExecutorMessage", 'payload_type':"json",
                     'payload': m }
            executor_runner_channel = executor_runners[m['slave_id']['value']]
            executor_channel = executors.get(executor_runner_channel)
            print_message( "Sending FrameworkToExecutorMessage: " + str(resp))
            r.lpush(executor_channel, json.dumps(resp))
        elif urb_message['target'] == 'UnregisterFrameworkMessage':
            print_message( "Received UnregisterFramework message: " + str(urb_message))
            m = urb_message['payload']['mesos.internal.UnregisterFrameworkMessage']

            # Need to delete all of our stuff
            for k in launched_runners[m['framework_id']['value']]:
                # This needs to go to the executor
                executor_runner_channel = executor_runners.get(k)
                if not executor_runner_channel:
                    continue
                executor_channel = executors.get(executor_runner_channel)
                if executor_channel:
                    # Send the shutdown message
                    executor_shutdown = {}
                    payload = executor_shutdown
                    resp = { 'source_id' : mesos_channel, 'target':"ShutdownExecutorMessage", 'payload_type':"json",
                        'payload': payload }
                    print_message( "Sending ShutdownExecutor message: " + str(resp))
                    r.lpush(executor_channel, json.dumps(resp))
                del executor_runners[k]

            del launched_runners[m['framework_id']['value']]
            del frameworks[m['framework_id']['value']]
            if uge_jobs.get(m['framework_id']['value']):
                job_id = uge_jobs[m['framework_id']['value']][0]
                print_message( "Deleting UGE Job %s" % job_id)
                os.system("qhold %s" % job_id)
                t = threading.Timer(2.0,os.system, ["qdel %s" % job_id])
                t.start()
                del uge_jobs[m['framework_id']['value']]
            # TODO:  This cleanup needs to be fixed
            #for k,t in tasks.items():
            #    if t['executor']['framework_id']['value'] == m['framework_id']['value']:
            #        del tasks[k]
            #

            print launched_runners,executor_runners,frameworks,tasks
            if one_shot:
                for t in timers.values():
                    t.cancel()
                break


        else:
            print_message( "Received unknown message: " + str(urb_message))

if __name__ == '__main__':
    one_shot = False
    if(len(sys.argv) == 2):
        one_shot=True
    main(one_shot)
