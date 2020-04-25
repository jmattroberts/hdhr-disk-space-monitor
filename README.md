# hdhr-disk-space-monitor
Monitor disk space utilization of one HDHomeRun SCRIBE or SERVIO device. Optionally delete recordings to stay above a specified free space threshold.


# Device Selection
```
--device discover
```

Each instance of the monitor will monitor only one device. By default, devices are discovered on the local network and the first one found with a StorageID is monitored. Optionally, a specific device ID can be passed to the monitor.

# Modes of Operation

## Report Mode
```
--mode report
```

In the default "report" mode, the monitor reports disk space utilization periodically. The default reporting interval, which can be overridden, is 10 minutes.

```
Tue Apr 21 17:04:49 2020 [HDVR-4US-1TB 12345678] Total: 931.06 GiB; Used: 278.05 GiB (29.9%); Free: 653.01 GiB (70.1%)
Tue Apr 21 17:14:49 2020 [HDVR-4US-1TB 12345678] Total: 931.06 GiB; Used: 278.05 GiB (29.9%); Free: 653.01 GiB (70.1%)
```

## Maintain Mode
```
--mode maintain
```

In "maintain" mode, the monitor will report disk space utilization, and also maintain a minimum amount of free disk space.  It does this by deleting one recording per disk space check if less than the minimum of free space is available. This will continue until the minimum amount of free space is made available.

```
Tue Apr 21 17:07:31 2020 [HDVR-4US-1TB 12345678] Total: 931.06 GiB; Used: 913.06 GiB (98.1%); Free: 18.0 GiB (1.9%); Minimum Free: 18.62 GiB (2.0%)
Tue Apr 21 17:07:32 2020 [HDVR-4US-1TB 12345678] Deleting "Keeping Up Appearances" recorded on Sun Jul 28 22:30:00 2019
```
### Minimum Free Space
```
--percent-free PERCENT
--gigabytes-free GIGABYTES
```
The default amount of free space to maintain is 2%. This can be overridden with a different percentage, or with an absolute number of gigabytes (GiB).

### Delete Policies
```
--delete-policy {age,category,priority}
```

There are 3 delete policies that can be applied to select a recording to be deleted.

* **Age** - (default) The oldest recording is selected
* **Category** - Recordings are sorted first by category, then by age within category. The oldest recording in the least important category is selected. The categories, in order of increasing importance are:
  * News
  * Series
  * Sports
  * Movies
  * Specials
* **Priority** - The recordings are sorted first by recording rule priority, then by age within priority. Recordings that have no associated recording rule are given high priority. The oldest recording with the lowest priority is selected.

### Watched Recordings
```
--watched-first
--watched-offset SECONDS
```
The delete policies described above do not take into account whether recordings have been watched or not. To have watched recordings deleted first, before the selected delete policy comes into effect, use the `--watched-first` option.

A recording is considered to be watched if there are fewer than 3 minutes remaining to be watched. This can be modified using the `--watched-offset` option.

### Adaptive Interval

In "maintain" mode, the default interval between checks is not consistent. It is adaptive based on the maximum number of simultaneous recordings supported by the device model (SCRIBE: 4, SERVIO: 6), the theoretical maximum bitrate of each recording (19.4 Mb/s), and the minimum time it would take to reach the free space threshold since the last check.

The more free space is avalable, the longer it will be between checks - up to many hours. If there is very little free space available, it might be only a few seconds between checks. The time until the next check is printed in verbose mode.

If the interval is overridden, the override will be used exclusively instead of the adaptive interval.

# Listing Recordings
```
--list-recordings
```
This option is available so that, in combination with `--delete-policy` and `--watched-first`, recordings can be listed in the order that they would be deleted. This can help determine which delete policy is preferred.

No space check or deletion happens when this option is used.

# Usage Guide

```
usage: hdhr_monitor_disk_space.py [-h] [-d DEVICE_ID] [-m {report,maintain}]
                                  [-i SECONDS] [-g GIGABYTES | -p PERCENT]
                                  [-s {age,category,priority}] [-w]
                                  [-o SECONDS] [-l] [-q | -v]

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
  -i SECONDS, --interval SECONDS
                        Number of seconds between free space checks. Default
                        is 600 in report mode. In maintain mode, the default
                        is adaptive based on the maximum number of
                        simultaneous recordings supported by the device model,
                        the theoretical maximum bitrate of each recording, and
                        the minimum time it would take to reach the free space
                        threshold since the last check.
  -g GIGABYTES, --gigabytes-free GIGABYTES
                        Number of free gigabytes (GiB) of disk space below
                        which action (delete recording) will be taken. Only
                        applicable in maintain mode.
  -p PERCENT, --percent-free PERCENT
                        Percentage of free disk space below which action
                        (delete recording) will be taken. Only applicable in
                        maintain mode. Default is 2, if neither gigabytes or
                        percent are specified.
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
  -w, --watched-first   Delete watched recordings first, before applying the
                        selected delete policy / sort method. Default is to
                        apply the selected delete policy / sort method without
                        regard to whether recordings are watched or not.
  -o SECONDS, --watched-offset SECONDS
                        Number of unwatched seconds at the end of a recording
                        at which to consider it "watched". Default is 180
                        seconds (3 minutes), meaning that the recording must
                        be watched to within 180 seconds of the end to be
                        considered watched.
  -l, --list-recordings
                        List recordings in the order that they would be
                        deleted in maintain mode, and then exit. Use in
                        combination with -s/--delete-policy to determine which
                        policy works best for your situation.
  -q, --quiet           Suppress all messages except errors.
  -v, --verbose         Print more informational messages. Free space and
                        delete messages are printed by default.
```
