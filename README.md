# Univa Grid Engine Adapter for Universal Resource Broker (URB)

This project allows one to run [Apache Mesos](http://mesos.apache.org) frameworks ([Marathon](https://mesosphere.github.io/marathon), [Chronos](https://mesos.github.io/chronos), [Spark](https://spark.apache.org), Hadoop MapReduce, etc.) with Universal Resource Broker on a [Univa Grid Engine](http://www.univa.com) cluster.

It utilizes the [urb-core](https://github.com/UnivaCorporation/urb-core) project and provides a Univa Grid Engine adapter for URB.

Please see [Universal Resource Broker core](https://github.com/UnivaCorporation/urb-core) project for more architectual details.

URB can be installed in [Tortuga](https://github.com/UnivaCorporation/tortuga) environment with [tortuga-kit-urb-uge](https://github.com/UnivaCorporation/tortuga-kit-urb-uge).


The following steps need to be done to perform a project build:

## Create docker build environment (requires docker to be installed):

```
cd urb-core/vagrant
make
```

In order to run the test Mesos frameworks that are part of this project (or actual Mesos frameworks which can be installed separately) Univa Grid Engine has to be a part of this development environment. A trial version of UGE can be downloaded from [univa.com](univa.com) and copied to `uge` directory (see [uge/README.md](uge/README.md)). It will be installed in one of the subsequent steps. Without UGE the project still can be built but none of the Mesos frameworks can be run (as well as some of the test steps which rely on UGE to be present will fail).

## Start docker build container:

```
SYNCED_FOLDER=../.. vagrant up --provider=docker
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

Assuming that URB build (`make`) succeeded the following commands will start a Redis server and the URB service:

`urb-core/source/cpp/3rdparty/redis/build/redis-2.8.18/src/redis-server&` - start redis server in background

`cd urb-core/source/python`

`. ../../../etc/urb.sh` - source URB development environment to set environment variables for URB configuration files (etc/urb.conf and etc/urb.executor_runner.conf) and Python path required by URB service

`python urb/service/urb_service.py` - run URB service

Open a new host shell and login into vagrant development environment (`vagrant ssh`, `cd /scratch/urb`). Create a new Python virtual environment for the URB executor runner:

`tools/venv.sh`

The following command will start the Mesos C++ example framework with 50 tasks that ping-pong a message with the framework:

`URB_MASTER=urb://$(hostname) LD_LIBRARY_PATH=/scratch/urb/urb-core/source/cpp/liburb/build /scratch/urb/urb-core/source/cpp/liburb/build/example_framework.test`

Grid Engine jobs submitted as a result of Mesos tasks deployment on the cluster can be monitored in separate guest shell session with `watch -n1 qstat -f`.

The following commands will start the Mesos Python example framework with 50 tasks that ping-pong a message with the framework:

```
. venv/bin/activate
LD_LIBRARY_PATH=/scratch/urb/urb-core/source/cpp/liburb/build /scratch/urb/urb-core/source/cpp/liburb/python-bindings/test/test_framework.py urb://$(hostname)
deactivate
```

## Cleaning/Erasing development environment

Shutdown the environment by running the following command on the host:

```
cd urb-core/vagrant
vagrant halt
```

If you want to completely remove development environment and underlying docker image run:

```
cd urb-core/vagrant
vagrant destroy
make clean
```

This will remove all traces of the machine from the host system.
