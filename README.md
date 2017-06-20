# Univa Grid Engine adapter for Universal Resource Broker (URB)

This project allows to run [Apache Mesos](http://mesos.apache.org) frameworks ([Marathon](https://mesosphere.github.io/marathon), [Chronos](https://mesos.github.io/chronos), [Spark](https://spark.apache.org), etc.) with Universal Resource Broker in [Univa Grid Engine](http://www.univa.com) cluster.

It utilizes [urb-core](https://github.com/UnivaCorporation/urb-core) project and provides Univa Grid Engine adapter for URB.

Please see [Universal Resource Broker core](https://github.com/UnivaCorporation/urb-core) project for more architectual details.


Following steps need to be done to perform a project build:

## Create docker build environment (requires docker to be installed):

```
cd urb-core/vagrant
make
```

In order to run test Mesos frameworks which are part of this project (or actual Mesos frameworks which can be installed separately) Univa Grid Engine has to be a part of this development environment. Trial version of UGE can be downloaded from [univa.com](univa.com) and copied to `uge` directory (see [uge/README.md](uge/README.md)). It will be installed in one of the subsequent steps. Without UGE the project still can be built but none of the Mesos frameworks can be run (as well as some of the test steps which rely on UGE to be present will fail).

## Start docker build container:

```
SYNCED_FOLDER=../.. vagrant up
```

## Login into docker build container:

```
vagrant ssh
```

Inside the build container:

### Install trial version of UGE (if downloaded earlier):

```
cd /scratch/urb
sudo puppet apply -t uge/uge.pp
```

### Build

```
make
```

### Test (requires UGE to be a part of the development environment)

Exit vagrant environment shell (`exit`) and login again (`vagrant ssh`, `cd /scratch/urb`) to source UGE environment (or do it manually `. /opt/uge/default/common/settings.sh` from the current shell session). Run tests:

```
make test
```

### Build UGE adapter Python egg and source archive (to be found in `source/python/dist`)

```
make dist
```

## Run URB in the development environment

Assuming that URB build (`make`) succeeded following commands will start redis server and URB service:

`source/cpp/3rdparty/redis/build/redis-2.8.18/src/redis-server&` - start redis server in background

`cd urb-core/source/python`

`. ../../../etc/urb.sh` - source URB development environment to set environment variables for URB configuration files (etc/urb.conf and etc/urb.executor_runner.conf) and Python path required by URB service

`python urb/service/urb_service.py` - run URB service

Open new host shell and login into vagrant development environment (`vagrant ssh`, `cd /scratch/urb`). Create Python virtual environment for URB executor runner:

`tools/venv.sh`

Following command will start Mesos C++ example framework with 50 tasks that ping-pong a message with the framework:

`URB_MASTER=urb://$(hostname) LD_LIBRARY_PATH=/scratch/urb/urb-core/source/cpp/liburb/build /scratch/urb/urb-core/source/cpp/liburb/build/example_framework.test`

Grid Engine jobs submission as a result of Mesos tasks deployment on the cluster can be monitored in separate guest shell session with `watch -n1 qstat -f`.

Following command will start Mesos Python example framework with 50 tasks that ping-pong a message with the framework:

`. venv/bin/activate`

`LD_LIBRARY_PATH=/scratch/urb/urb-core/source/cpp/liburb/build /scratch/urb/urb-core/source/cpp/liburb/python-bindings/test/test_framework.py urb://$(hostname)`
