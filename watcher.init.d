#!/bin/bash
### BEGIN INIT INFO
# Provides:          watcher
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Start/stop Watcher that watches specified files/folders for changes
### END INIT INFO

PATH=/sbin:/usr/sbin:/bin:/usr/bin
DESC="Watches specified files/folders for changes"
NAME="watcher"
DAEMON="/usr/bin/watcher.py"
DAEMON_CONFIG="/etc/watcher.ini"


# Exit if the package is not installed
[ -x "$DAEMON" ] || exit 0

start() {
    $DAEMON start -c $DAEMON_CONFIG
}

stop() {
    $DAEMON stop -c $DAEMON_CONFIG
}

restart() {
    $DAEMON restart -c $DAEMON_CONFIG
}

case "$1" in
    start)
        start
        ;;

    stop)
        stop
        ;;
        
    restart|force-reload)
        restart
        ;;
        
    status)
        ;;
    *)
        echo "Usage: $SCRIPTNAME {start|stop|status|restart|force-reload}" >&2
        exit 3
        ;;
esac
