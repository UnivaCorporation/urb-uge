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

"""
Use this class to run Grid Engine and License Orchestrator commands. See
class doc string for usage.
"""

import os
import sys
import pwd
import re
import datetime
import subprocess
import xml.parsers.expat

def demote(user_uid, user_gid):
   def __result():
      os.setgid(user_gid)
      os.setuid(user_uid)
   return __result


class UGEException(Exception):
   def __init__(self, code, msg):
      self.name = self.__class__.__name__
      self.code = code
      self.msg = msg

   def __str__(self):
      return "Got exception " + self.name + " with error code " \
         + str(self.code) + " and error message:\n" + str(self.msg)

class UGEProductMissmatch(UGEException):
   pass

class UGEMissingBinary(UGEException):
   pass

class UGEExceptionEnvMiss(UGEException):
   pass

class UGECommandExecError(UGEException):
   pass

class UGECommandTypeError(UGEException):
   pass

class INF(object):
   """
   Class for setting infinity constants for int and float with appropriate
   comparison operator handling.
   """
   def __init__(self, t):
      if t == int:
         self.maxv = sys.maxint
      elif t == float:
         self.maxv = float('inf')
      elif t == datetime.date:
         self.maxv = datetime.date(datetime.MAXYEAR, 12, 31)
      else:
         raise UGECommandTypeError(99, "Type for INF class either needs to be "
            + "'int' or 'float'. Got: " + str(t))
   def __lt__(self, other):
      return self.maxv < other
   def __le__(self, other):
      return self.maxv <= other
   def __gt__(self, other):
      return self.maxv > other
   def __ge__(self, other):
      return self.maxv >= other
   def __eq__(self, other):
      return self.maxv == other
   def __ne__(self, other):
      return self.maxv <> other
   def __str__(self):
      return "infinity"

class GridEngine(object):
   """
   Class for running Grid Engine or License Orchestrator CLI commands. The
   optional constructor parameter 'product' controls which product is being
   talked to. The default is "SGE". Use "LO" instead.

   Exports class functions for all binaries contained in the Grid Engine
   binary directory plus for the ge/lo_share_mon binary, i.e. instantiation
   creates a function qconf(args) with which you can run the qconf command
   with the arguments in 'args'. The same is true for qstat and so on. Note
   that 'args' can either be a string or a list containing the CLI options
   as string elements.

   Usage Examples:
      from gridengine import *
      g = GridEngine()
      g.qstat("-f")

      or for LO

      g = GridEngine(product="LO")
      g.loconf("-f")

      For product independent code aliases are being set-up for the commands, e.g.

      g.stat_cmd("-f")

      See 'print g.binaryMap' for information on available aliases and what
      they are currently aliased to in this instance of the GridEngine class.
      Further commands are either the same for Grid Engine or LO or do not
      exist for the product in use.

   The class also provides a generic and static run() method which can be used
   to run any script or executable. See 'print GridEngine.run.__doc__' or
   help(GridEngine.run) after importing the gridengine module.
   """

   # Static class variables:
   #    print_warnings: controls whether warnings, if any, get printed or not.
   #       Only has an effect if 'return_errors' has been reset to false in run call.
   #       Otherwise the warning messages get returned to the caller which
   #       needs to decide how to handle them.
   #    INFINITY_INT: Integer infinity value
   #    INFINITY_FLOAT: Float infinity value
   #    INFINITY_TIME: Time infinity value
   print_warnings = True
   INFINITY_INT = INF(int)
   INFINITY_FLOAT = INF(float)
   INFINITY_TIME = INF(datetime.date)

   def __init__(self, product="SGE"):
      # Store product prefix ... either default "SGE" or "LO".
      # And also a lowercase version for things like sge_* commands or scripts.
      if product == "SGE" or product == "LO":
         self.prefixUC = product
         self.prefixLC = product.lower()
      else:
         raise UGEProductMissmatch(1, "Unknown product " + product
            + ". Must either be SGE or LO.")

      # Get environment variables SGE_ROOT and SGE_CELL and save to instance
      # variables self.root and self.cell
      self.__get_ge_environ()

      # Get Grid Engine binary paths
      ge_path,utilbin_path = self.__get_bin_path()

      # A factory to set class functions for all binaries in the binary
      # directory:
      #    First we need a closure so we can pass the cmd to be executed to each
      #    function instance without it being overwritten
      def setter(c):
         def func(x,**kwargs):
            return GridEngine.run(c,x,**kwargs) # c will be the command & x the args
         return func 
      # Now the factory:
      for cmd in os.listdir(ge_path):
         # Now create all the functions passing the full path to the executable 
         # to each
         setattr(self, cmd, setter(ge_path + "/" + cmd))
      # And set sge/lo_share_mon access method as well
      share_mon = self.prefixLC + "_share_mon"
      setattr(self, share_mon, setter(utilbin_path + "/" + share_mon))

      # Set up maps for aliasing commands if product independent (SGE or LO) code
      # needs to be written.
      if self.prefixUC == "SGE":
         self.binaryMap = {
            "acct_cmd" :      "qacct",
            "conf_cmd" :      "qconf",
            "del_cmd" :       "qdel",
            "execd_cmd" :     "sge_execd",
            "master_cmd" :    "sge_qmaster",
            "shadowd_cmd" :   "sge_shadowd",
            "shepherd_cmd" :  "sge_shepherd",
            "stat_cmd" :      "qstat",
            "sub_cmd" :       "qsub",
            "share_mon_cmd" : "sge_share_mon"
         }
      else:
         self.binaryMap = {
            "acct_cmd" :      "loacct",
            "conf_cmd" :      "loconf",
            "del_cmd" :       "lodel",
            "execd_cmd" :     "lo_execd",
            "master_cmd" :    "lo_master",
            "shadowd_cmd" :   "lo_shadowd",
            "shepherd_cmd" :  "lo_shepherd",
            "stat_cmd" :      "lostat",
            "sub_cmd" :       "losub",
            "share_mon_cmd" : "lo_share_mon"
         }
      # And set generic alias methods for the commands
      for alias,cmd in self.binaryMap.items():
         try:
            setattr(self, alias, getattr(self, cmd))
         except:
            raise UGEMissingBinary(1, "Missing access methods for "
               + self.prefixUC + " '" + cmd + "' binary. "
               + "Maybe issue with readability of "
               + "the binary directory '" + ge_path
               + "' or with file access permission? Or binary " \
               + "directory is incomplete?")
          
      # Check whether everything went well and we have Grid Engine command
      # access methods. If not then print an informative error message. Use
      # some of the more important commands for this test and use their
      # aliases for product independence.
      try:
         # just a few prominent examples
         getattr(self, "conf_cmd")
         getattr(self, "stat_cmd")
      except:
         raise UGEMissingBinary(1, "failed to setup access methods for Grid "
            + "Engine binaries. Maybe issue with readability of the binary "
            + "directory or with file access permission?")

   # The following function arguably could be put outside of the GridEngine
   # class. Have chosen to use a static method instead to avoid potential
   # naming conflicts. Also enables us to use the class variables
   # 'print_warnings' to control error and output handling
   #    return_errors: controls output/error handling (print and, if error,
   #       exit --or-- return infos to caller). Default is "print and exit if
   #       required" = False. 
   @staticmethod
   def run(cmd, args="", return_errors=False, use_sudo=True, user=None):
      """
      Generic function which runs a command defined in the string 'cmd' with
      the optional arguments in args. Args can either be a string or a list
      with individual strings containing the positional parameters. The
      variable 'return_errors' controls whether errors are to
      printed out by the function (the default 'False') or whether a triple of
      stdout, error output and error status is to be returned. And the static
      class variable 'print_warnings' controls whether warning messages, if
      any come up, are printed or suppressed.

      Can be used for running scripts and executables outside of a Grid Engine
      context for the error and output handling this function provides. We need
      it here for the factory creating Grid Engine command methods in __init__
      and also for running the Grid Engine 'arch' script so we know the Grid
      Engine binary path.

      Almost all of the functionality of run() is provided by __run() which is
      called right away. run() itself only implements how 'return_errors'
      and 'print_warnings' influence error and warning treatment.
      """
      def __run(cmd, args=""):
         """
         Implements logic for run(). See decription there.
         """
         # Depending on argument type, assemble command to be run in list 'cmdl'
         cmdl = [cmd]
         if args:
            if type(args) == str:
               cmdl += args.split(" ")
            elif type(args) == list:
               cmdl += args
            else:
               errmsg = "Can't run command: unsupported argument type of " \
                     + str(args) + " = " + str(type(args))
               return "", errmsg, 2
 
         if use_sudo:
            if user:
               cmdl = [ 'sudo','-E','-u', user ] + cmdl
            #print("__run: cmdl %s" % cmdl)
            # Run the command
            try:
               p = subprocess.Popen(cmdl, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
               so,se = p.communicate()
            except:
               errmsg = "With sudo: got exception while invoking " + " ".join(cmdl)
               return "", errmsg, 2
         else:
            set_user = "nobody"
            if user:
               set_user = user
            else:
               if 'USER' in os.environ:
                  set_user = os.environ['USER']

            pw_record = pwd.getpwnam(set_user)
            user_name = pw_record.pw_name
            user_home_dir = pw_record.pw_dir
            user_uid = pw_record.pw_uid
            user_gid = pw_record.pw_gid
            env = os.environ.copy()
            env['HOME'] = user_home_dir
            env['LOGNAME'] = user_name
            #env['PWD'] = cwd
            env['USER'] = user_name
            #print("__run: cmdl=%s, user=%s" % (cmdl, user_name))
            try:
               p = subprocess.Popen(cmdl, preexec_fn=demote(user_uid, user_gid), \
                                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
               so,se = p.communicate()
            except:
               errmsg = "Without sudo: got exception while invoking " + " ".join(cmdl)
               return "", errmsg, 2

         # Check for error codes
         if p.returncode:
            errmsg = "Running '" + " ".join(cmdl) + "' resulted in error code: " \
               + str(p.returncode) + "\nError Output:\n" + se
            return "", errmsg, 2

         # And for error output
         if se:
            errmsg = "Command " + " ".join(cmd) + \
               " has returned the following stderr output: " + se
            return so, errmsg, 0

         # Return stdout
         return so, "", 0

      #print("cmd=%s, args=%s, use_sudo=%s, user=%s" % (cmd, args, use_sudo, user))
      # The main code of run(). Just error and output handling after the call
      # to __run()
      so, errmsg, retval = __run(cmd, args)
      if return_errors:
         return so, errmsg, retval
      else:
         if retval:
            raise UGECommandExecError(retval, errmsg)
         else:
            if errmsg and GridEngine.print_warnings:
               sys.stderr.write(errmsg + "\n")
            return so

   def __get_ge_environ(self):
      """
      Check presence of required environment variables and store them in
      instance variables.
      """
      root_env = self.prefixUC + "_ROOT"
      cell_env = self.prefixUC + "_CELL"
      try:
         self.root = os.environ[root_env]
         self.cell = os.environ[cell_env]
      except:
         raise UGEExceptionEnvMiss(5, "Environment variables " + root_env
            + " and/or " + cell_env + " not set!")

   def __get_bin_path(self):
      """
      Determine binary paths for Grid Engine commands via the arch script
      Requires SGE_ROOT env var to be set
      """
      # Run 'arch' and get the arch string
      so = GridEngine.run(self.root + "/util/arch")
      arch = so.split('\n')[0]
      # return bin and utilbin path
      return self.root + '/bin/' + arch, self.root + '/utilbin/' + arch

   def getCplxAttrs(self, attrName=""):
      """
      Parse the output of qconf/loconf -sc and represent it with Python data
      structures.

      The optional parameter 'attrName' trigger to return only the information
      about the complex attribute with this name. Otherwise the info for all
      attributes gets returned.

      The returned format for a single attribute (attrName<>"") is:
         {attrName : {colHdr1 : colVal1, colHdr2 : colVal2, ...}}
      where colHdr1, colHdr2, ... taken from the first (commented) line in the
      qconf -sc output.
      If attrName=="" and thus the info of all complex attributes is to be
      returned then there is a dictionary entry like the above for each
      attribute with the key being the attribute name.

      Yes, this carries the redundant colHdrs for each attribute but it
      allows for the easiest access and the amount of data is not large
      anyhow.
      """
      def __getCols(l):
         # strip redundant, separating blanks in a string 'l' and split up its
         # elements into a list which is returned.
         return re.sub(r"  *", " ", l).split(" ")

      cplxAttrs = {} # Will contain the dict to be returned

      # Execute qconf/loconf -sc
      so = self.conf_cmd("-sc")

      firstLine = True 
      for line in so.split("\n"):
         if firstLine:
            # 1st line contains headers ==> special handling
            line = line[1:]  # strip leading '#'
            cols = __getCols(line)   # get the column headers
            colNames = cols[1:]   # drop the 1st which is 'name'
            firstLine = False
            continue
         if not line or line[0] == '#':
            # skip empty and comment lines
            continue

         # For all other lines
         cols = __getCols(line)  # get the column entries
         # Build a dict from the column headers and the column entries
         attr = dict(zip(colNames, cols[1:]))
         if attrName:
            if attrName == cols[0]:
               # if attrName was specified and we have found it then return a
               # dict with that one entry
               return {attrName : attr}
         else:
            # Otherwise build the dict
            cplxAttrs[cols[0]] = attr
      # And return it when done with the output parsing
      return cplxAttrs

   def get_uge_root(self):
      return self.root

class FindJobQstat():
   def __init__(self):
      self.ctr = 0
      self.jobL = []
      self.jobFound = False
      self.p = xml.parsers.expat.ParserCreate()
      self.p.StartElementHandler = self._findJob
      self.p.EndElementHandler = self._endJob
      self.p.CharacterDataHandler = self._getCharData

   def _findJob(self, name, attrs):
      if name == "JB_job_number":
         self.jobFound = True

   def _endJob(self, name):
      if name == "JB_job_number":
         self.jobFound = False

   def _getCharData(self, data):
      if self.jobFound:
         self.jobL.append(data)

   def parse(self, doc):
      self.jobL = []
      self.jobFound = False
      self.p.Parse(doc)
      # print "ACTIVE JOBS", self.jobL

   def isJobInQstat(self, jid):
      return jid in self.jobL
