# hdhr-disk-space-monitor

Monitor disk space utilization of HDHomeRun SCRIBE, SERVIO, and RECORD devices. Optionally delete recordings to stay above a specified free space minimum, get rid of recordings older than a maximum age, or keep only a certain number of episodes.


 - [Use Cases](#use-cases)
	 - [Disk Space Reporting](#disk-space-reporting)
	 - [Disk Space Maintenance](#disk-space-maintenance)
	 - [Recording Maintenance](#recording-maintenance)
 - [General Configuration](#general-configuration)
	 - [Device Discovery/Selection](#device-discoveryselection)
	 - [Space Maintenance Delete Policies](#space-maintenance-delete-policies)
	 - [Watched Recordings](#watched-recordings)
	 - [Delete Protection](#delete-protection)
	 - [Listing Recordings](#listing-recordings)
	 - [Listing Series](#listing-series)
 - [Command-Line Usage](#command-line-usage)

Also see the example configuration file available in the code. There are many configuration options related to recording maintenance that are only available in the configuration file.

# Use Cases

## Disk Space Reporting

### "I want to see how much space is being used by my storage devices."

If not told to do anything else, the monitor will simply report disk space utilization every 10 minutes for all HDHomeRun storage devices found on the network.

```
$ hdhr_monitor_disk_space
2020-06-19 22:08:51,967 [HDHomeRun SCRIBE QUATRO 12345678] Total: 999.71 GB; Used: 402.27 GB (40.2%); Free: 597.45 GB (59.8%)
2020-06-19 22:08:51,983 [HDHomeRun RECORD 192.168.1.100:43206] Total: 1.07 TB; Used: 218.65 GB (20.4%); Free: 854.56 GB (79.6%)
```

## Disk Space Maintenance

### "I want to make sure that my storage devices do not fill up."

Tell the monitor the amount of free space to maintain, either by percentage (`-p/--percent-free`) or absolute gigabytes (`-g/--gigabytes-free`), and it will delete a recording according to the [delete policy](#space-maintenance-delete-policies) when that amount is no longer free.

```
$ hdhr_monitor_disk_space --gigabytes-free 10
2020-06-19 22:08:51,967 [HDHomeRun SCRIBE QUATRO 12345678] Total: 999.71 GB; Used: 402.27 GB (40.2%); Free: 597.45 GB (59.8%); Minimum Free: 10.00 GB (1.0%)
2020-06-19 22:08:51,983 [HDHomeRun RECORD 192.168.1.100:43206] Total: 1.07 TB; Used: 218.65 GB (20.4%); Free: 854.56 GB (79.6%); Minimum Free: 10.00 GB (0.9%)
```

Whenever a recording is deleted, it is reported, along with the reason.

```
2020-05-01 23:53:50,637 [HDHomeRun SCRIBE QUATRO 12345678] Deleting "Keeping Up Appearances" recorded Sun Jul 28 22:30:00 2019 to free space
```

### "I want to make sure that my storage devices do not fill up, but I want to use different settings for each device."

The configuration file can be used for this. If one device needs to maintain 10GB free, and the other needs to maintain 25% free, there are a few options.

#### Option 1: Set 10GB as the default and override one device with 25%.

```
[DEFAULT]
gigabytes_free: 10

[device:192.168.1.100]
# Override the default
gigabytes_free:
percent_free: 25
```

#### Option 2: Configure each device individually.

```
[device:12345678]
gigabytes_free: 10

[device:192.168.1.100]
percent_free: 25
```

In either case above, if the configuration file is named /etc/hdhr_disk_space_monitor.conf, then the following would get it started:

```
$ hdhr_monitor_disk_space --conf-file /etc/hdhr_disk_space_monitor.conf
2020-06-19 22:08:51,967 [HDHomeRun SCRIBE QUATRO 12345678] Total: 999.71 GB; Used: 402.27 GB (40.2%); Free: 597.45 GB (59.8%); Minimum Free: 10.00 GB (1.0%)
2020-06-19 22:08:51,983 [HDHomeRun RECORD 192.168.1.100] Total: 1.07 TB; Used: 218.65 GB (20.4%); Free: 854.56 GB (79.6%); Minimum Free: 267.50 GB (25.0%)
```

#### Option 3: Independent processes without configuration file.

```
$ hdhr_monitor_disk_space --device-id 12345678 --gigabytes-free 10
2020-06-19 22:08:51,967 [HDHomeRun SCRIBE QUATRO 12345678] Total: 999.71 GB; Used: 402.27 GB (40.2%); Free: 597.45 GB (59.8%); Minimum Free: 10.00 GB (1.0%)
```

```
$ hdhr_monitor_disk_space --device-id 192.168.1.100 --percent-free 25
2020-06-19 22:08:51,983 [HDHomeRun RECORD 192.168.1.100] Total: 1.07 TB; Used: 218.65 GB (20.4%); Free: 854.56 GB (79.6%); Minimum Free: 267.50 GB (25.0%)
```

## Recording Maintenance

Recording maintenance is configured entirely in the configuration file. See the example configuration file for a description of all options. The recordings are maintained as a whole across all storage devices, so it's best **not** to split this across multiple processes as in Option 3 above.

### "I want 'news' category recordings to be deleted after 2 days, 'sport' category recordings to be protected from any automatic deletion, and no more than 5 episodes of 'The Masked Singer'.

```
[category:news]
max_age_days: 2

[category:sport]
protected: yes

[series:The Masked Singer]
max_episodes: 5
```

# General Configuration

## Device Discovery/Selection

```
--device discover|device_id|ip_address|hostname ...
```

Each instance of the monitor can monitor one or several devices. By default, it will discover all storage devices on the network and monitor/maintain them all according to the options and configuration provided. Optionally, specific device IDs, IP addresses, and/or hostnames can be passed to the monitor, and it will only monitor/maintain those.

## Space Maintenance Delete Policies

```
--delete-policy {age,category}
```

There are 2 delete policies that can be applied to select a recording to be deleted to maintain the free space minimum.

* **Age** - (default) The oldest recording is selected
* **Category** - Recordings are sorted first by category, then by age within category. The oldest recording in the least important category is selected. The categories, in order of increasing importance are:

  * News
  * Series
  * Sports
  * Movies
  * Specials

That category order can be altered by modifying the `delete_order` setting in the configuration file.

## Watched Recordings

```
--watched-first
--watched-offset SECONDS
```

The delete policies described above do not take into account whether recordings have been watched or not. To have watched recordings deleted first, before the selected delete policy comes into effect, use the `--watched-first` option.

A recording is considered to be watched if there are fewer than 3 minutes remaining to be watched. This can be modified using the `--watched-offset` option.

## Delete Protection

In the configuration file, any category or specific series can have `protected: yes` set. This will cause all episodes of that category or series to be protected from deletion by this program. This setting has no effect on the ability to delete recordings in the DVR UI,

Also, any recording that is currently playing or is in the process of being recorded is automatically protected from deletion.

## Listing Recordings

```
--list-recordings
```

This option is available so that, in combination with `--delete-policy` and `--watched-first`, recordings can be listed in the order that they would be deleted. This can help determine which delete policy is preferred.

No space check or deletion happens when this option is used.

An alternative to this is to run with the `-n/--dry-run` argument. This will prevent the program from actually deleting anything, while showing what it would delete.

## Listing Series

```
--list-series
```

List recorded series in order of increasing space utilization, along with the amount of space utilized and number of episodes. If watched recordings exist, the amount of space they occupy will also be printed.

No space check or deletion happens when this option is used.

# Command-Line Usage

```
usage: hdhr_disk_space_monitor [-h]
                               [-d DEVICE_ID|IP|HOSTNAME [DEVICE_ID|IP|HOSTNAME ...]]
                               [-f FILE] [-i SECONDS] [-c NUMBER]
                               [-g GIGABYTES | -p PERCENT] [-s {age,category}]
                               [-w] [-o SECONDS] [-l] [-r] [-n] [-V] [-q | -v]

Monitor disk space utilization of HDHomeRun SCRIBE, SERVIO, and RECORD
devices. Optionally delete recordings to stay above a specified free space
minimum, get rid of recordings older than a maximum age, or keep only a
certain number of episodes.

optional arguments:
  -h, --help            show this help message and exit
  -d DEVICE_ID|IP|HOSTNAME [DEVICE_ID|IP|HOSTNAME ...], --device-id DEVICE_ID|IP|HOSTNAME [DEVICE_ID|IP|HOSTNAME ...]
                        ID, IP address, or hostname of device(s) to monitor.
                        Default is "discover" which discovers all storage
                        devices on the local network.
  -f FILE, --conf-file FILE
                        Path to configuration file. The configuration file
                        supports overriding the built-in defaults, per-device
                        settings, as well as some settings not available on
                        the command-line. See example. Options given on the
                        command-line override those in the configuration file.
  -i SECONDS, --interval SECONDS
                        Number of seconds between space utilization reports.
                        Default is 600. This can be set per-device in the
                        configuration file.
  -c NUMBER, --count NUMBER
                        Number of space utilization reports to print before
                        stopping. Default is to continue forever. To disable
                        regular reports, set this to zero (0). This can be set
                        per-device in the configuration file.
  -g GIGABYTES, --gigabytes-free GIGABYTES
                        Minimum number of gigabytes (GB) of free disk space to
                        maintain. Causes a maintenance cycle to be run which
                        will delete recordings when the minimum amount of free
                        space is not available. Cannot be used in combination
                        with -p/--percent-free. This can be set per-device in
                        the configuration file.
  -p PERCENT, --percent-free PERCENT
                        Minimum percentage of free disk space to maintain.
                        Causes a maintenance cycle to be run which will delete
                        recordings when the minimum amount of free space is
                        not available. Cannot be used in combination with
                        -g/--gigabytes-free. This can be set per-device in the
                        configuration file.
  -s {age,category}, --delete-policy {age,category}
                        Delete policy / sort method. Determines how recordings
                        are sorted when selecting one to delete when
                        maintaining free disk space. "age" sorts only on the
                        age of the recordings and selects the oldest for
                        deletion. "category" sorts first by category ['news',
                        'series', 'sport', 'movie', 'special'], then by age.
                        Category order can be customized in the configuration
                        file. Use in combination with -l/--list-recordings to
                        determine which policy is preferred. Default is "age".
  -w, --watched-first   Delete watched recordings first, before applying the
                        selected delete policy. Default is to apply the
                        selected delete policy without regard to whether
                        recordings are watched or not. This can be set per-
                        category in the configuration file.
  -o SECONDS, --watched-offset SECONDS
                        Threshold for considering a recording "watched". This
                        is the number of seconds remaining to be watched at
                        the end of a recording below which it is considered
                        "watched". Default is 180 seconds (3 minutes). This
                        can be set per-category in the configuration file.
  -l, --list-recordings
                        List recordings in the order that they would be
                        deleted when maintaining free disk space, and then
                        exit. Use in combination with -s/--delete-policy and
                        -w/--watched-first to determine which policy is
                        preferred.
  -r, --list-series     List recorded series in order of increasing space
                        utilization, along with the amount of space utilized,
                        and then exit. If watched recordings exist, the amount
                        of space they occupy will also be printed.
  -n, --dry-run         Run without actually deleting any recordings. Log
                        messages will indicate that recordings are being
                        deleted, but none will actually be deleted.
  -V, --version         Show version number and exit.
  -q, --quiet           Suppress all messages except errors.
  -v, --verbose         Print more informational messages. Free space and
                        delete messages are printed by default.```
