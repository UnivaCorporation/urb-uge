/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#include <iostream>
#include <string>

#include <redis3m/redis3m.hpp>
#include <mesos/scheduler.hpp>

#include <gtest/gtest.h>
#include <glog/logging.h>
#include <stout/os.hpp>
#include <stout/net.hpp>

using namespace mesos;

using std::cerr;
using std::cout;
using std::endl;
using std::flush;
using std::string;
using std::vector;

const int32_t CPUS_PER_TASK = 1;
const int32_t MEM_PER_TASK = 32;



// Stub test scheduler
class TestScheduler : public Scheduler
{
public:
    TestScheduler(const ExecutorInfo& _executor, const string& _role)
        : executor(_executor),
          role(_role),
          tasksLaunched(0),
          tasksFinished(0),
          totalTasks(5) {}

    virtual ~TestScheduler() {}

    virtual void registered(SchedulerDriver*,
                            const FrameworkID&,
                            const MasterInfo&)
    {
        cout << "Registered!" << endl;
    }

    virtual void reregistered(SchedulerDriver*, const MasterInfo&)
    {
        cout << "Reregistered!" << endl;
    }

    virtual void disconnected(SchedulerDriver*) {}

    virtual void resourceOffers(SchedulerDriver* driver,
                                const vector<Offer>&)
    {
        cout << "." << flush;
        driver->stop();
    }

    virtual void offerRescinded(SchedulerDriver*,
                                const OfferID&) {}

    virtual void statusUpdate(SchedulerDriver* driver, const TaskStatus& status)
    {
        cout << "Task " << status.task_id().value() << " is in state " << status.state() << endl;

        if (status.state() == TASK_FINISHED)
            tasksFinished++;

        if (tasksFinished == totalTasks)
            driver->stop();
    }

    virtual void frameworkMessage(SchedulerDriver* /*driver*/,
                                  const ExecutorID& /*executorId*/,
                                  const SlaveID& /*slaveId*/,
                                  const string& /*data*/) {}

    virtual void slaveLost(SchedulerDriver*, const SlaveID&) {}

    virtual void executorLost(SchedulerDriver* /*driver*/,
                              const ExecutorID& /*executorID*/,
                              const SlaveID& /*slaveID*/,
                              int /*status*/) {}

    virtual void error(SchedulerDriver*, const string& message)
    {
        cout << message << endl;
    }

private:
    const ExecutorInfo executor;
    string role;
    int tasksLaunched;
    int tasksFinished;
    int totalTasks;
};
using namespace mesos;


// To use a test fixture, derive a class from testing::Test.
static bool loggingInitialized = false;
class SchedTest : public testing::Test {
protected:  // You should make the members protected s.t. they can be
    // accessed from sub-classes.

    // First time through clean up any existing log directory and set up
    // glog.
    void initializeLogging() {
        if (!loggingInitialized) {
            os::system("rm -rf /tmp/test_framework");
            os::system("mkdir /tmp/test_framework");
            FLAGS_log_dir = "/tmp/test_framework";
            os::setenv("URB_LOGLEVEL","0");
            //os::setenv("GLOG_vmodule", "sched=1"); // enable VLOG(1) for sched module only (doesn't work)
            //FLAGS_vmodule = "sched=1"; // doesn't compile contrary to documentation
            FLAGS_v = 1; // this test relies on log output (some of which is VLOG(1))
            //FLAGS_logtostderr = 1;
            loggingInitialized = true;
            DLOG(INFO) << "Initializing logging.";
        }
    }

    // Make a driver instance and make sure logging is configured for our tests
    virtual void SetUp() {
        // Initialize logging
        initializeLogging();

        // Create test driver
        ExecutorInfo executor;
        executor.mutable_executor_id()->set_value("default");
        executor.mutable_command()->set_value("127.0.0.1:5050");
        executor.set_name("Test Executor (C++)");
        executor.set_source("cpp_test");
        Environment* environment = executor.mutable_command()->mutable_environment();
        Environment_Variable* variable = environment->add_variables();
        variable->set_name("URB_LOGLEVEL");
        variable->set_value("0");
        Option<string> glog_val = os::getenv("GLOG_v");
        if (!glog_val.isNone()) {
            Environment_Variable* variable_glog = environment->add_variables();
            variable_glog->set_name("GLOG_v");
            variable_glog->set_value(glog_val.get());
        }

        scheduler = new TestScheduler(executor, "*");

        FrameworkInfo framework;
        framework.set_user("");
        framework.set_name("Test Framework (C++)");
        framework.set_role("*");

        bool implicitAcknowlegements = true;
        driver = new MesosSchedulerDriver(
            scheduler, framework, "urb://127.0.0.1", implicitAcknowlegements);
    }

    // Truncate the log file at the end of every test and clean up any allocated driver objects.
    virtual void TearDown() {
        char buffer[512];
        int count  = readlink("/tmp/test_framework/Test Framework (C++).INFO", buffer, sizeof(buffer));
        if (count > 0) {
            // Make sure it is null terminated
            buffer[count] = '\0';

            std::string fullPath;
            if(buffer[0] == '/') {
                fullPath = "";
            } else {
                fullPath = "/tmp/test_framework/";
            }
            fullPath += buffer;
            // Always flush before truncate to make sure we have something
            google::FlushLogFiles(google::GLOG_INFO);
            google::TruncateLogFile(fullPath.c_str(),0,0);
        }
        if (driver != NULL ) {
            delete driver;
            driver = NULL;
        }
        if(scheduler != NULL) {
            delete scheduler;
        }
    }
/*
    // Get the last line from a file.  Return "" if there is no last
    // line.
    static string getLastLine(const char *fileName) {
        std::ifstream read(fileName, std::ios_base::ate );//open file
        std::string tmp;
        int length = 0;

        if( read )
        {
            char c = '\0';
            length = read.tellg();//Get file size

            // loop backward over the file

            for (int i = length-2; i > 0; i--)
            {
                read.seekg(i);
                c = read.get();
                if( c == '\r' || c == '\n' )//new line?
                    break;
            }

            std::getline(read, tmp);//read last line
            return tmp;
        }
        return "";
    }

    // Check if the last line of the log file contains a passed in value
    static bool lastLogMessageContains(const char *value) {
        //Make sure or logs are flushed
        size_t index;
        std::string line;
        google::FlushLogFiles(google::GLOG_INFO);
        line = getLastLine("/tmp/test_framework/Test Framework (C++).INFO");
        if( line.empty() ) {
            cout << "Couldn't find last line" << "\n";
            return false;
        }
        index = line.find(value);
        if (index == string::npos) {
            cout << "Couldn't find: " << value << "\n";
            cout << "Last line is: " << line << "\n";
            return false;
        }
        return true;
    }
*/
    // not necesseraly needs to be last message - just grep
    // reducing test case dependency on changes in logging in liburb
    static bool lastLogMessageContains(const char *value) {
        //Make sure or logs are flushed
        google::FlushLogFiles(google::GLOG_INFO);
        std::string grep("grep '");
        grep += value;
        grep += "' /tmp/test_framework/Test\\ Framework\\ \\(C++\\).INFO";
        auto ret = os::system(grep);
        return (ret==0)?true:false;
    }

    ~SchedTest() {
        os::system("chmod -R a+w /tmp/test_framework");
    }

    // Each test will have a driver created
    MesosSchedulerDriver* driver;
    TestScheduler* scheduler;
};

// Test driver functions by calling the methods and making sure log lines
// show up.

#ifndef NDEBUG1

// Test the first constructor
TEST_F(SchedTest,DefaultConstructor) {
    ASSERT_NE((MesosSchedulerDriver*)NULL, driver);
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::MesosSchedulerDriver(): 1 end: status=1"));
}

// And the second constructor
TEST_F(SchedTest,Constructor2) {
    ExecutorInfo executor;
    executor.mutable_executor_id()->set_value("default");
    executor.mutable_command()->set_value("127.0.0.1:5050");
    executor.set_name("Test Executor (C++)");
    executor.set_source("cpp_test");

    TestScheduler scheduler(executor, "*");

    FrameworkInfo framework;
    framework.set_user(""); // Have Mesos fill in the current user.
    framework.set_name("Test Framework (C++)");
    framework.set_role("*");

    Credential credential;
    bool implicitAcknowlegements = true;
    MesosSchedulerDriver *driver2 = new MesosSchedulerDriver(
        &scheduler, framework, "127.0.0.1:5050", implicitAcknowlegements, credential);
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::MesosSchedulerDriver(): 2 end: status=1"));
    delete driver2;
}

// Test the destructor
TEST_F(SchedTest,Destructor) {
    delete driver;
    driver = NULL;
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::~MesosSchedulerDriver(): end: status=1"));
}

TEST_F(SchedTest,RunMethod) {
    // We should get a log message
    Try<std::string> host = net::hostname();
    redis3m::connection::ptr_t conn = redis3m::connection::create(host.get(), 6379);

    redis3m::reply r = conn->run(redis3m::command("DEL") << "urb.endpoint.0.mesos");
    Option<string> py = os::getenv("PYTHON");
    std::string cmd = py.isNone() ? "python" : py.get();
    cmd += " test/simple_master.py one_shot &";
    system(cmd.c_str());
    google::FlushLogFiles(google::GLOG_INFO);
    ASSERT_EQ(DRIVER_STOPPED, driver->run());
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::run(): end: status=4"));
}

TEST_F(SchedTest,StartMethod) {
    // We should get a log message
    ASSERT_EQ(DRIVER_RUNNING, driver->start());
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::start(): end: status=2"));
    driver->stop();
    driver->join();
}

TEST_F(SchedTest,JoinMethod) {
    // We should get a log message
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->join());
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::join(): end: status=1"));
}

TEST_F(SchedTest,launchTasks1) {
    // We should get a log message
    OfferID offerId;
    vector<TaskInfo> tasks;
    Filters filters;
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->launchTasks(offerId,tasks,filters));
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::launchTasks(): 1 end: status=1"));
}

TEST_F(SchedTest,launchTasks2) {
    // We should get a log message
    vector<OfferID> offerIds;
    vector<TaskInfo> tasks;
    Filters filters;
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->launchTasks(offerIds,tasks,filters));
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::launchTasks(): 2 end: status=1"));
}

TEST_F(SchedTest,acceptOffers) {
    // We should get a log message
    vector<OfferID> offerIds;
    vector<Offer::Operation> operations;
    Filters filters;
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->acceptOffers(offerIds,operations,filters));
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::acceptOffers(): end: status=1"));
}

TEST_F(SchedTest,DeclineOffer) {
    // We should get a log message
    OfferID offerId;
    Filters filters;
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->declineOffer(offerId,filters));
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::declineOffer(): end: status=1"));
}

TEST_F(SchedTest,RequestResources) {
    // We should get a log message
    vector<Request> requests;
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->requestResources(requests));
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::requestResources(): end: status=1"));
}

TEST_F(SchedTest,ReconcileTasks) {
    // We should get a log message
    vector<TaskStatus> statuses;
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->reconcileTasks(statuses));
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::reconcileTasks(): end: status=1"));
}

TEST_F(SchedTest,KillTask) {
    // We should get a log message
    TaskID taskId;
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->killTask(taskId));
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::killTask(): end: status=1"));
}

TEST_F(SchedTest,SendFrameworkMessage) {
    // We should get a log message
    ExecutorID executorId;
    SlaveID slaveId;
    string data;
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->sendFrameworkMessage(executorId,slaveId,data));
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::sendFrameworkMessage(): end: status=1"));
}

TEST_F(SchedTest,ReviveOffers) {
    // We should get a log message
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->reviveOffers());
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::reviveOffers(): end: status=1"));
}

TEST_F(SchedTest,AbortMethod) {
    // We should get a log message
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->abort());
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::abort(): end: status=1"));
}

TEST_F(SchedTest,StopMethod) {
    // We should get a log message
    ASSERT_EQ(DRIVER_NOT_STARTED, driver->stop());
    ASSERT_TRUE(lastLogMessageContains("MesosSchedulerDriver::stop(): end: status=1, aborted=0"));
}
#else
TEST_F(SchedTest,Dummy) {
   ASSERT_EQ(0,0);
}
#endif
