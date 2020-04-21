# hdhr-disk-space-monitor
Monitor disk space utilization of one HDHomeRun SCRIBE or SERVIO device. Optionally delete recordings to stay above a specified free space threshold.
```
usage: hdhr_monitor_disk_space.py [-h] [-d DEVICE_ID] [-m {report,maintain}]
                                  [-s {age,category,priority}] [-i SECONDS]
                                  [-l] [-g GIGABYTES | -p PERCENT] [-q | -v]

optional arguments:
  -h, --help            show this help message and exit
  -d DEVICE_ID, --device-id DEVICE_ID
                        ID of device to monitor. Default is "discover", which
                        discovers devices on the local network and monitors
                        the first found with a StorageID.
  -m {report,maintain}, --mode {report,maintain}
                        Mode of operation. "report" mode only reports free
                        space periodically. "maintain" mode will maintain
                        minimum free space by deleting recordings when the
                        free space threshold is crossed. Deleted recordings
                        are set to record again. Default is "report".
  -s {age,category,priority}, --delete-policy {age,category,priority}
                        Delete policy / sort method. Determines how recordings
                        are sorted when selecting one to delete in maintain
                        mode. "age" sorts only on the age of the recordings.
                        "category" sorts first by category ['news', 'series',
                        'sport', 'movie', 'special'], then by age. "priority"
                        sorts first by associated recording rule priority,
                        then age. If no associated recording rule still exists
                        for a recording, its priority defaults to high. Use in
                        combination with -l/--list-recordings to determine
                        which policy works best for your situation. Default is
                        "age".
  -i SECONDS, --interval SECONDS
                        Number of seconds between free space checks. Default
                        is 600 in report mode. In maintain mode, the default
                        is adaptive based on the maximum number of
                        simultaneous recordings supported by the device model,
                        the theoretical maximum bitrate of each recording, and
                        the minimum time it would take to reach the free space
                        threshold since the last check.
  -l, --list-recordings
                        List recordings in the order that they would be
                        deleted in maintain mode, and then exit. Use in
                        combination with -s/--delete-policy to determine which
                        policy works best for your situation.
  -g GIGABYTES, --gigabytes-free GIGABYTES
                        Number of free gigabytes (GiB) of disk space below
                        which action (delete recording) will be taken. Only
                        applicable in maintain mode.
  -p PERCENT, --percent-free PERCENT
                        Percentage of free disk space below which action
                        (delete recording) will be taken. Only applicable in
                        maintain mode. Default is 2, if neither gigabytes or
                        percent are specified.
  -q, --quiet           Suppress all messages except errors.
  -v, --verbose         Print more informational messages. Free space and
                        delete messages are printed by default.
```
