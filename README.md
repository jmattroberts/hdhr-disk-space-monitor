# hdhr-disk-space-monitor
Monitor disk space utilization of one HDHomeRun SCRIBE or SERVIO device. Optionally delete recordings to stay above a specified minimum free space.


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
2020-05-01 22:26:54,844 [HDVR-4US-1TB 12345678] Total: 931.06 GiB; Used: 588.58 GiB (63.2%); Free: 342.48 GiB (36.8%)
2020-05-01 22:36:54,956 [HDVR-4US-1TB 12345678] Total: 931.06 GiB; Used: 589.44 GiB (63.3%); Free: 341.61 GiB (36.7%)
```

## Maintain Mode
```
--mode maintain
```

In "maintain" mode, the monitor will report disk space utilization as it does in report mode, as well as maintain a minimum amount of free disk space.  It does this by deleting one recording per disk space check if less than the minimum amount of free space is available. This will continue until the minimum is made available.

When the minimum free space threshold is crossed, an "off-interval" report will be written, and then a recording will be deleted.

```
2020-05-01 23:53:49,885 [HDVR-4US-1TB 12345678] Total: 931.06 GiB; Used: 913.06 GiB (98.1%); Free: 18.0 GiB (1.9%); Minimum Free: 18.62 GiB (2.0%)
2020-05-01 23:53:50,637 [HDVR-4US-1TB 12345678] Deleting "Keeping Up Appearances" recorded on Sun Jul 28 22:30:00 2019

```
The disk space checks for free space maintenance are separate from those for the report. They happen in the background at an interval determined by the amount of free disk space as of the last maintenance check. The more disk space is available, the longer it will be until the next check - up to many hours. If there is very little free space left, the maintenance checks can be as often as every few seconds. This can be observed in verbose mode, but it can get very... verbose.

```
2020-05-01 23:53:49,885 [HDVR-4US-1TB 12345678] Running maintenance cycle - checking free space
2020-05-01 23:53:49,901 [HDVR-4US-1TB 12345678] Next maintenance cycle in 9 hours, 28 minutes, 17 seconds
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

# Listing Recordings
```
--list-recordings
```
This option is available so that, in combination with `--delete-policy` and `--watched-first`, recordings can be listed in the order that they would be deleted. This can help determine which delete policy is preferred.

No space check or deletion happens when this option is used.

# Usage Guide

```
usage: hdhr_monitor_disk_space.py [-h] [-f FILE] [-d DEVICE_ID]
                                  [-m {report,maintain}] [-i SECONDS]
                                  [-c NUMBER] [-g GIGABYTES | -p PERCENT]
                                  [-s {age,category,priority}] [-w]
                                  [-o SECONDS] [-l] [-q | -v]

Monitor disk space utilization of one HDHomeRun SCRIBE or SERVIO device.
Optionally delete recordings to stay above a specified free space minimum.

optional arguments:
  -h, --help            show this help message and exit
  -f FILE, --conf-file FILE
                        Path to configuration file. The configuration file
                        supports overriding the built-in defaults, as well as
                        per-device settings. See example. Per-device settings
                        are applied when a device ID is specified using
                        -d/--device-id. Options given on the command-line
                        override those in the configuration file.
  -d DEVICE_ID, --device-id DEVICE_ID
                        ID of device to monitor. Default is "discover" which
                        discovers devices on the local network and monitors
                        the first device found with a StorageID.
  -m {report,maintain}, --mode {report,maintain}
                        Mode of operation. "report" mode reports disk space
                        utilization periodically. "maintain" mode reports disk
                        space utilization, and also maintains a minimum amount
                        of free space by deleting recordings when less than
                        the minimum amount of free space is available. Deleted
                        recordings are set to record again. Default is
                        "report".
  -i SECONDS, --interval SECONDS
                        Number of seconds between space utilization reports.
                        Default is 600.
  -c NUMBER, --count NUMBER
                        Number of space utilization reports to print before
                        stopping. Default is to continue forever.
  -g GIGABYTES, --gigabytes-free GIGABYTES
                        Minimum number of free gigabytes (GiB) of disk space
                        to maintain. Only applicable in maintain mode. Cannot
                        be used in combination with -p/--percent-free.
  -p PERCENT, --percent-free PERCENT
                        Minimum percentage of free disk space to maintain.
                        Only applicable in maintain mode. Cannot be used in
                        combination with -g/--gigabytes-free. Default is 2.0,
                        if neither gigabytes or percent are specified.
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
                        selected delete policy. Default is to apply the
                        selected delete policy without regard to whether
                        recordings are watched or not.
  -o SECONDS, --watched-offset SECONDS
                        Threshold for considering a recording "watched". This
                        is the number of seconds remaining to be watched at
                        the end of a recording below which it is considered
                        "watched". Default is 180 seconds (3 minutes).
  -l, --list-recordings
                        List recordings in the order that they would be
                        deleted in maintain mode, and then exit. Use in
                        combination with -s/--delete-policy and -w/--watched-
                        first to determine which policy works best for your
                        situation.
  -q, --quiet           Suppress all messages except errors.
  -v, --verbose         Print more informational messages. Free space and
                        delete messages are printed by default.

The interval for free space checks in maintain mode is independent from the
interval for disk utilization reports (-i/--interval). The maintenance runs in
the background at an interval based on the amount of free space found during
the last check. If there is a lot of space available, it will be a long time -
maybe many hours - before the next check. If there is little free space
available, it might be only a few seconds until the next check. This can be
observed with verbose output enabled (-v/--verbose).
```
