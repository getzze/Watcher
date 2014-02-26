#!/usr/bin/python
# -*- coding: utf-8 -*-

##/usr/bin/env python

# Modified by Bertrand Lacoste
# Copyright (c) 2010 Greggory Hernandez

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

### BEGIN INIT INFO
# Provides:          watcher.py
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Monitor directories for file changes
# Description:       Monitor directories specified in /etc/watcher.ini for
#                    changes using the Kernel's inotify mechanism and run
#                    jobs when files or directories change
### END INIT INFO

import sys, os
import atexit
import datetime, signal, errno
import pyinotify
from types import *
import argparse, ConfigParser, string
import logging, time

#third party libs
try:
    from subliminal import VIDEO_EXTENSIONS
except ImportError:
    VIDEO_EXTENSIONS = None



class Daemon:
    """
    A generic daemon class

    Usage: subclass the Daemon class and override the run method
    """
    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced Programming in the
        UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try:
            pid = os.fork()
            if pid > 0:
                #exit first parent
                sys.exit(0)
        except OSError, e:
            logger.warning("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0)
        except OSError, e:
            logger.warning("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        #redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        se = file(self.stderr, 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        #write pid file
        #self.delpid()
        atexit.register(self.force_delpid)
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    def force_delpid(self):
        os.remove(self.pidfile)

    def delpid(self):
        self.del_pidfile(self.pidfile)

    def start(self):
        """
        Start the daemon
        """
        ## Get daemon status
        status = self.status()
        
        if status[0] == 0:
            # Start the Daemon
            self.daemonize()
            logger.info('Daemon started')
            self.run()
        elif status[0] == 1:
            self.delpid()
            # Start the Daemon
            self.daemonize()
            logger.info('Daemon started')
            self.run()
        elif status[0] == 2:
            logger.info("pidfile %s already exists. Daemon already running."%(self.pidfile))
            sys.exit(1)
            #return
        else:
            logger.warning('Unknown error %r with pid %r: %r'%(status[0], status[1], status[2]))

    def stop(self):
        """
        Stop the daemon
        """
        ## Get daemon status
        status = self.status()
        
        if status[0] == 0:
            logger.info("pidfile %s does not exist. Daemon not running?"% self.pidfile)
            return # not an error in a restart
        elif status[0] == 1:
            self.delpid()
            logger.info("pid %i is a stale pid."% status[1])
            return # not an error in a restart
        elif status[0] == 2:
            try:
                self.kill_pid(status[1])
            except:
                raise
            else:
                self.delpid()
                logger.info('Daemon stopped')
        else:
            logger.warning('Unknown error %r with pid %r: %r'%(status[0], status[1], status[2]))

        ## Get daemon status to check that everything went well
        status = self.status()
        if status[0] != 0:
            logger.warning('!! Daemon not stopped with error %r with pid %r: %r'%(status[0], status[1], status[2]))
            raise OSError

    def status(self):
        """
        Return the status of the daemon as a tuple (CODE, PID, ERROR).
        0 : no pidfile found
        1 : pidfile found with pid corresponding to no running process, `stale` pid
        2 : pid corresponding to running process
        9 : undefined status.
        """
        # get the pid from the pidfile
        status = [9, None, None]
        pid = self.get_pid(self.pidfile)

        if not pid:
            status = [0, None, None]
            return status
            
        try:
            os.kill(pid, 0)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                # The specified PID does not exist
                status = [1, pid, '%r'%(exc)]
        except:
            raise
            #status = [9, pid,'%r'%(e)]
        else:
            status = [2, pid, None]
        
        return status

    def get_pid(self, pidfile):
        """
        Return pid from pidfile. Return None if pidfile does not exist
        """
        # get the pid from the pidfile
        try:
            with file(self.pidfile, 'r') as pf:
                pid = int(pf.read().strip())
        except IOError:
            pid = None
        except Exception:
            raise
        return pid
        
    def kill_pid(self,pid):
        """
        Kill pid with sigterm.
        """
        if type(pid) != int:
            logger.warning()
            raise TypeError
        first_attempt = True
        
        try:
            while 1:
                os.kill(pid, signal.SIGTERM)
                first_attempt = False
                time.sleep(0.1)
        except IOError as ioe:
            logger.warning('%r' % e)
            #status = [1, None, '%r'%(e)]
        except OSError as e:
            if first_attempt:
                raise
            else:
                pass
                #status = [1, None, '%r'%(e)]
        except:  
            logger.warning('Error with pid %r' % pid)
            raise
            #status = [9, pid, '%r'%(e)]
        #return status

    def del_pidfile(self,pidfile):
        if os.path.exists(self.pidfile):
            os.remove(pidfile)
        else:
            logger.debug('Pidfile does not exist anymore.')


    def restart(self):
        """
        Restart the daemon
        """
        self.stop()
        self.start()


    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """
    
class WatcherDaemon(Daemon):

    def __init__(self, config):
        self.stdin = '/dev/null'
        self.stdout = config.get('DEFAULT','logfile')
        self.stderr = config.get('DEFAULT','logfile')
        self.pidfile =  config.get('DEFAULT','pidfile')
        self.pidfile_timeout = 5
        self.config  = config


    def run(self):
        wdds      = dict()
        notifiers = dict()

        # read jobs from config file
        for section in self.config.sections():
            # get the basic config info
            mask      = self._parseMask(self.config.get(section,'events').split(','))
            folder    = self.config.get(section,'watch')
            recursive = self.config.getboolean(section,'recursive')
            autoadd   = self.config.getboolean(section,'autoadd')
            excluded  = None if '' in self.config.get(section,'excluded').split(',') else set(self.config.get(section,'excluded').split(','))
            include_extensions = None if '' in self.config.get(section,'include_extensions').split(',') else set(self.config.get(section,'include_extensions').split(','))
            exclude_extensions = None if '' in self.config.get(section,'exclude_extensions').split(',') else set(self.config.get(section,'exclude_extensions').split(','))
            command   = self.config.get(section,'command')

            logger.info(section + ": " + folder)

            # parse include_extensions
            if 'video' in include_extensions:
                include_extensions.discard('video')
                include_extensions |= set(VIDEO_EXTENSIONS)
          
            wm = pyinotify.WatchManager()
            handler = EventHandler(command, include_extensions, exclude_extensions)

            wdds[section] = wm.add_watch(folder, mask, rec=recursive,auto_add=autoadd)
            # Remove watch about excluded dir. Not the perfect solution as they would
            # just have to not be added in first place...
            if excluded:
                for excluded_dir in excluded :
                    for (k,v) in wdds[section].iteritems():
                        if k.startswith(excluded_dir):
                            wm.rm_watch(v)
                            wdds[section].pop(v) 
                    #wdds[-1] = dict((k,v) for (k,v) in wdds[-1].iteritems() if not k.startswith(excluded_dir))
                    logger.debug("Excluded dirs : " + excluded_dir)
            # BUT we need a new ThreadNotifier so I can specify a different
            # EventHandler instance for each job
            # this means that each job has its own thread as well (I think)
            notifiers[section] = pyinotify.ThreadedNotifier(wm, handler)

        # now we need to start ALL the notifiers.
        for notifier in notifiers.values():
            try:
                notifier.start()
                # close threads when the program is exited
                atexit.register(notifier.stop)
                logger.debug('Notifier for %s is instanciated'%(section))
            except pyinotify.NotifierError, err:
                logger.warning( '%r %r'%(sys.stderr, err))

    def _parseMask(self, masks):
        ret = False;

        for mask in masks:
            mask = mask.strip()

            if 'access' == mask:
                ret = self._addMask(pyinotify.IN_ACCESS, ret)
            elif 'attribute_change' == mask:
                ret = self._addMask(pyinotify.IN_ATTRIB, ret)
            elif 'write_close' == mask:
                ret = self._addMask(pyinotify.IN_CLOSE_WRITE, ret)
            elif 'nowrite_close' == mask:
                ret = self._addMask(pyinotify.IN_CLOSE_NOWRITE, ret)
            elif 'create' == mask:
                ret = self._addMask(pyinotify.IN_CREATE, ret)
            elif 'delete' == mask:
                ret = self._addMask(pyinotify.IN_DELETE, ret)
            elif 'self_delete' == mask:
                ret = self._addMask(pyinotify.IN_DELETE_SELF, ret)
            elif 'modify' == mask:
                ret = self._addMask(pyinotify.IN_MODIFY, ret)
            elif 'self_move' == mask:
                ret = self._addMask(pyinotify.IN_MOVE_SELF, ret)
            elif 'move_from' == mask:
                ret = self._addMask(pyinotify.IN_MOVED_FROM, ret)
            elif 'move_to' == mask:
                ret = self._addMask(pyinotify.IN_MOVED_TO, ret)
            elif 'open' == mask:
                ret = self._addMask(pyinotify.IN_OPEN, ret)
            elif 'all' == mask:
                m = pyinotify.IN_ACCESS | pyinotify.IN_ATTRIB | pyinotify.IN_CLOSE_WRITE | \
                    pyinotify.IN_CLOSE_NOWRITE | pyinotify.IN_CREATE | pyinotify.IN_DELETE | \
                    pyinotify.IN_DELETE_SELF | pyinotify.IN_MODIFY | pyinotify.IN_MOVE_SELF | \
                    pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO | pyinotify.IN_OPEN
                ret = self._addMask(m, ret)
            elif 'move' == mask:
                ret = self._addMask(pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO, ret)
            elif 'close' == mask:
                ret = self._addMask(pyinotify.IN_CLOSE_WRITE | pyinotify.IN_CLOSE_NOWRITE, ret)

        return ret

    def _addMask(self, new_option, current_options):
        if not current_options:
            return new_option
        else:
            return current_options | new_option
  
class EventHandler(pyinotify.ProcessEvent):
    def __init__(self, command, include_extensions, exclude_extensions):
        pyinotify.ProcessEvent.__init__(self)
        self.command = command
        self.include_extensions = include_extensions
        self.exclude_extensions = exclude_extensions
        
    # from http://stackoverflow.com/questions/35817/how-to-escape-os-system-calls-in-python
    def shellquote(self,s):
        s = str(s)
        return "'" + s.replace("'", "'\\''") + "'"

    def runCommand(self, event):
        # if specified, exclude extensions, or include extensions.
        if self.include_extensions and all(not event.pathname.endswith(ext) for ext in self.include_extensions):
            #print "File %s excluded because its exension is not in the included extensions %r"%(event.pathname, self.include_extensions)
            logger.debug("File %s excluded because its extension is not in the included extensions %r"%(event.pathname, self.include_extensions))
            return
        if self.exclude_extensions and any(event.pathname.endswith(ext) for ext in self.exclude_extensions):
            #print "File %s excluded because its extension is in the excluded extensions %r"%(event.pathname, self.exclude_extensions)
            logger.debug("File %s excluded because its extension is in the excluded extensions %r"%(event.pathname, self.exclude_extensions))
            return

        t = string.Template(self.command)
        command = t.substitute(watched=self.shellquote(event.path),
                               filename=self.shellquote(event.pathname),
                               tflags=self.shellquote(event.maskname),
                               nflags=self.shellquote(event.mask),
                               cookie=self.shellquote(event.cookie if hasattr(event, "cookie") else 0))
        try:
            os.system(command)
            #print "Run command print: %s" % (command)
            logger.info("Run command log: %s" % (command))
        except OSError, err:
            #print "Failed to run command '%s' %s" % (command, str(err))
            logger.info("Failed to run command '%s' %s" % (command, str(err)))




    def process_IN_ACCESS(self, event):
        #print "Access: %s"%(event.pathname)
        logger.info("Access: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_ATTRIB(self, event):
        #print "Attrib: %s"%(event.pathname)
        logger.info("Attrib: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_CLOSE_WRITE(self, event):
        #print "Close write: %s"%(event.pathname)
        logger.info("Close write: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_CLOSE_NOWRITE(self, event):
        #print "Close nowrite: %s"%(event.pathname)
        logger.info("Close nowrite: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_CREATE(self, event):
        #print "Creating: %s"%(event.pathname)
        logger.info("Creating: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_DELETE(self, event):
        #print "Deleting: %s"%(event.pathname)
        logger.info("Deleting: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_MODIFY(self, event):
        #print "Modify: %s"%(event.pathname)
        logger.info("Modify: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_MOVE_SELF(self, event):
        #print "Move self: %s"%(event.pathname)
        logger.info("Move self: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_MOVED_FROM(self, event):
        #print "Moved from: %s"%(event.pathname)
        logger.info("Moved from: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_MOVED_TO(self, event):
        #print "Moved to: %s"%(event.pathname)
        logger.info("Moved to: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_OPEN(self, event):
        #print "Opened: %s"%(event.pathname)
        logger.info("Opened: %s"%(event.pathname))
        self.runCommand(event)


if __name__ == "__main__":
    # Parse commandline arguments
    parser = argparse.ArgumentParser(
                description='A daemon to monitor changes within specified directories and run commands on these changes.',
             )
    parser.add_argument('-c','--config',
                        action='store',
                        help='Path to the config file (default: %(default)s)')
    parser.add_argument('command',
                        action='store',
                        choices=['start','stop','restart','debug'],
                        help='What to do.')
    args = parser.parse_args()

    # Parse the config file
    config = ConfigParser.ConfigParser()
    if args.config:
        # load config file specified by commandline
        confok = config.read(args.config)
    else:
        # load config file from default locations
        confok = config.read(['/etc/watcher.ini', os.path.expanduser('~/.watcher.ini')]);
    if not confok:
        sys.stderr.write("Failed to read config file. Try -c parameter\n")
        sys.exit(4);

    # Initialize logging
    logger = logging.getLogger("daemonlog")
    logger.setLevel(logging.INFO)
    logformatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    if args.command == 'debug':
        loghandler = logging.StreamHandler()
        logger.setLevel(logging.DEBUG)
    else: 
        loghandler = logging.FileHandler(config.get('DEFAULT','logfile'))
    loghandler.setFormatter(logformatter)
    logger.addHandler(loghandler)

    # Initialize the daemon
    daemon = WatcherDaemon(config)

    # Execute the command
    if 'start' == args.command:
        daemon.start()
        #logger.info('Daemon started')
    elif 'stop' == args.command:
        daemon.stop()
        #logger.info('Daemon stopped')
    elif 'restart' == args.command:
        daemon.restart()
        #logger.info('Daemon restarted')
    elif 'debug' == args.command:
        logger.warning('Press Control+C to quit...')
        daemon.run()
        ## Stay awake until Control+C is hit
        try:
            while 1:
                time.sleep(0.1)
        except KeyboardInterrupt:
            # Kill the process
            daemon.kill_pid(os.getpid())
    else:
        print "Unkown Command"
        sys.exit(2)
    sys.exit(0)
