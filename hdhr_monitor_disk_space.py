#!/usr/bin/env -S python -u

#------------------------------------------------------------------------------
# MIT License
# 
# Copyright (c) 2020 J. Matt Roberts
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#------------------------------------------------------------------------------

import argparse
import json
import math
import re
import requests
import sys
import time
from requests.exceptions import HTTPError
from json.decoder import JSONDecodeError

DEFAULT_THRESHOLD_PCT = 2
DEFAULT_DEVICE_ID = 'discover'
DEFAULT_MODE = 'report'
DEFAULT_CHECK_INTERVAL = 600
DEFAULT_DELETE_POLICY = 'age'
MODES = ['report', 'maintain']
DELETE_POLICIES = ['age', 'category', 'priority']
DISCOVER_URL = 'https://my.hdhomerun.com/discover'
RULES_URL = 'http://my.hdhomerun.com/api/recording_rules?DeviceAuth='
MAX_STREAMS = {'HDVR': 4, 'HHDD': 6}
BYTES_PER_MiB = 1024**2
BYTES_PER_GiB = 1024**3

# Deletion proceeds in the order shown below when using the category policy
CATEGORY_PRIORITY = ['news',
                     'series',
                     'sport',
                     'movie',
                     'special']

# This is the maximum bitrate for a stream (channel) as per the ATSC 1.0 
# spec. Convert it to bytes/sec for use in calcs.
ATSC_MAX_TUNER_Mbps = 19.4
ATSC_MAX_TUNER_Bps = (ATSC_MAX_TUNER_Mbps / 8) * BYTES_PER_MiB

quiet = False
verbose = False

def percent(string):

    value = float(string)

    if (value <= 0) or (value >= 100):
        msg = "%r (must be between 0 and 100, non-inclusive)" % string
        raise argparse.ArgumentTypeError(msg)

    return value

# End percent


def positive_float(string):

    value = float(string)

    if (value <= 0):
        msg = "%r (must be greater than 0)" % string
        raise argparse.ArgumentTypeError(msg)

    return value

# End positive_float


def positive_int(string):

    value = int(string)

    if (value <= 0):
        msg = "%r (must be greater than 0)" % string
        raise argparse.ArgumentTypeError(msg)

    return value

# End positive_int


def get_device(device_id):

    device_found = False

    response = requests.get(DISCOVER_URL)
    response.raise_for_status()

    devices = response.json()

    for device in devices:

        if 'DeviceID' not in device:
            if verbose:
                print(time.ctime() + " Discovered device at " + 
                  device['LocalIP'] + " has no device ID")
            continue

        elif (device_id == 'discover'):
            if ('StorageID' in device):

                if verbose:
                    print(time.ctime() + 
                      " Monitoring discovered device with ID " + device['DeviceID'])

                device_found = True
                break

            else:

                if verbose:
                    print(time.ctime() + " Discovered device " + 
                      device['DeviceID'] + " has no storage")

        elif device_id == device['DeviceID']:
            if ('StorageID' in device):

                if verbose:
                    print(time.ctime() + 
                      " Monitoring specified device " + device['DeviceID'])

                device_found = True
                break

            else:

                if verbose:
                    print(time.ctime() + " Specified device " + 
                      device['DeviceID'] + " has no storage")
                break

        else:

            if verbose:
                print(time.ctime() + " Discovered device " + 
                  device['DeviceID'] + " is not the one you are"
                  " looking for")

        # End device_id if

    # End devices loop

    if not device_found:
        return(None)

    refresh_device_data(device)
    
    return(device)

# End get_device


def refresh_device_data(device):

    response = requests.get(device['DiscoverURL'])
    response.raise_for_status()

    device.update(response.json())

    device['UsedSpace'] = device['TotalSpace'] - device['FreeSpace']

# End refresh_device_data


def get_max_device_Bps(device):

    model = re.match(r'[A-Z]{4}', device['ModelNumber']).group()

    max_device_streams = (MAX_STREAMS[model])

    return(ATSC_MAX_TUNER_Bps * max_device_streams)

# End get_max_device_streams


def parse_args():

    parser = argparse.ArgumentParser(
               description="Monitor disk space utilization of one "
                 "HDHomeRun SCRIBE or SERVIO device.  Optionally delete "
                 "recordings to stay above a specified free space "
                 "threshold.")

    parser.add_argument("-d", "--device-id", default=DEFAULT_DEVICE_ID,
      help="ID of device to monitor. Default is \"%(default)s\", which "
        "discovers devices on the local network and monitors the first found "
        "with a StorageID.")

    parser.add_argument("-m", "--mode", choices=MODES, default=DEFAULT_MODE,
      help="Mode of operation. \"report\" mode only reports free space "
        "periodically. \"maintain\" mode will maintain minimum free space by "
        "deleting recordings when the free space threshold is crossed. "
        "Deleted recordings are set to record again. "
        "Default is \"%(default)s\".")

    parser.add_argument("-s", "--delete-policy", choices=DELETE_POLICIES, 
      default=DEFAULT_DELETE_POLICY,
      help="Delete policy / sort method. Determines how recordings are "
        "sorted when selecting one to delete in maintain mode. "
        "\"age\" sorts only on the age of the recordings. \"category\" sorts "
        "first by category " + str(CATEGORY_PRIORITY) + ", then by age. "
        "\"priority\" sorts first by associated recording rule priority, then "
        "age. If no associated recording rule still exists for a recording, "
        "its priority defaults to high. "
        "Use in combination with -l/--list-recordings to determine which "
        "policy works best for your situation. "
        "Default is \"%(default)s\".")

    # Can't use the "default=" option here because we need to later test for
    # whether a value was passed in or not. If we used "default=", we would
    # not be able to differentiate between the default being set vs passed
    # in by the user.
    parser.add_argument("-i", "--interval", metavar="SECONDS", 
      type=positive_int,
      help="Number of seconds between free space checks. Default is " +
        str(DEFAULT_CHECK_INTERVAL) + " in report mode. In maintain mode, "
        "the default is adaptive based on the maximum number of simultaneous "
        "recordings supported by the device model, the theoretical maximum "
        "bitrate of each recording, and the minimum time it would take to "
        "reach the free space threshold since the last check.")

    parser.add_argument("-l", "--list-recordings", action="store_true", 
      help="List recordings in the order that they would be deleted in "
        "maintain mode, and then exit. Use in combination with "
        "-s/--delete-policy to determine which policy works best for your "
        "situation.")

    threshold_group = parser.add_mutually_exclusive_group()

    threshold_group.add_argument("-g", "--gigabytes-free", 
      metavar="GIGABYTES", type=positive_float, 
      help="Number of free gigabytes (GiB) of disk space below which "
        "action (delete recording) will be taken. Only applicable in "
        "maintain mode.")

    threshold_group.add_argument("-p", "--percent-free", metavar="PERCENT", 
      type=percent, default=DEFAULT_THRESHOLD_PCT,
      help="Percentage of free disk space below which action (delete "
        "recording) will be taken. Only applicable in maintain mode. "
        "Default is %(default)s, if neither gigabytes or percent are "
        "specified."
        )

    verbose_group = parser.add_mutually_exclusive_group()

    verbose_group.add_argument("-q", "--quiet", action="store_true", 
      help="Suppress all messages except errors.")

    verbose_group.add_argument("-v", "--verbose", action="store_true", 
      help="Print more informational messages.  Free space and delete "
        "messages are printed by default.")

    return(parser.parse_args())

# End parse_args


def get_sorted_recordings(device, delete_policy):

    default_priority = 9999

    response = requests.get(device['StorageURL'])
    response.raise_for_status()

    recordings = response.json()

    response = requests.get(RULES_URL + device['DeviceAuth'])
    response.raise_for_status()

    rules = response.json()

    if delete_policy == 'age':
        sorted_recordings = sorted(recordings, key=lambda r: r['StartTime'])

    elif delete_policy == 'category':

        for recording in recordings:
            recording['CategoryPriority'] = CATEGORY_PRIORITY.index(recording['Category'])

        sorted_recordings = sorted(recordings, key=lambda r: (r['CategoryPriority'], r['StartTime']))

    elif delete_policy == 'priority':

        for recording in recordings:

            # Assign priority to each recording based on recording rule priority
            # for that show.
            # Default to lowest priority in case no rule is found, or no priority
            # is given in the rule (i.e., on-off recordings)
            recording['RulePriority'] = default_priority

            for rule in rules:
                if rule['SeriesID'] == recording['SeriesID']:

                    if 'Priority' in rule:
                        recording['RulePriority'] = rule['Priority']
                    # End Priority if

                # End SeriesID if
            # End rules loop

        # End recordings loop

        sorted_recordings = sorted(recordings, key=lambda r: (r['RulePriority'], r['StartTime']))

    # End delete_policy if

    return(sorted_recordings)

# End get_sorted_recordings


def delete_recording(device, recording):

    if not quiet:
        print(time.ctime() + 
          " [" + device['ModelNumber'] + " " + device['DeviceID'] + "]"
          " Deleting \"" + recording['Title'] + "\"" +
          " recorded on " + time.ctime(recording['StartTime']))

    response = requests.post(recording['CmdURL'] + "&cmd=delete&rerecord=1")
    response.raise_for_status()

# End delete_recording


def report_space_utilization(device):

    # All "Space" fields are in bytes
    total_gib = device['TotalSpace'] / BYTES_PER_GiB
    free_gib = device['FreeSpace'] / BYTES_PER_GiB
    min_free_gib = device['MinimumFreeSpace'] / BYTES_PER_GiB
    used_gib = device['UsedSpace'] / BYTES_PER_GiB

    if device['FreeSpace'] == 0:
        free_pct = 0
        used_pct = 100
    else:
        free_pct = (device['FreeSpace'] / device['TotalSpace']) * 100
        used_pct = (device['UsedSpace'] / device['TotalSpace']) * 100

    min_free_pct = (device['MinimumFreeSpace'] / device['TotalSpace']) * 100

    if not(quiet):

        print(time.ctime() + 
          " [" + device['ModelNumber'] + " " + device['DeviceID'] + "]"
          " Total: " + str(round(total_gib, 2)) + " GiB;" +
          " Used: " + str(round(used_gib, 2)) + 
          " GiB (" + str(round(used_pct, 1)) + "%);" +
          " Free: " + str(round(free_gib, 2)) + 
          " GiB (" + str(round(free_pct, 1)) + "%)",
          end = '')
            
        if device['MinimumFreeSpace'] > 0:
            print("; Minimum Free: " + str(round(min_free_gib, 2)) + 
              " GiB (" + str(round(min_free_pct, 1)) + "%)")
        else:
            print(')')

    # End not quiet if

# End analyze_space


def print_recording_list(recordings):

    for recording in recordings:
        print(time.ctime(recording['StartTime']) +
             ': ' + recording['Title'])

# End print_recording_list


def main():

    global quiet
    global verbose

    check_interval = DEFAULT_CHECK_INTERVAL
    threshold_gib = None
    threshold_pct = None
    list_recordings = False

    args = parse_args()

    quiet = args.quiet
    verbose = args.verbose
    mode = args.mode
    delete_policy = args.delete_policy
    check_interval_override = args.interval
    threshold_gib = args.gigabytes_free
    threshold_pct = args.percent_free
    list_recordings = args.list_recordings


    try:

        device = get_device(args.device_id)

        if device is None:
            print("No device found to monitor", file=sys.stderr)
            sys.exit(2)

        if list_recordings:
            print_recording_list(get_sorted_recordings(device, delete_policy))
            sys.exit()

        if (mode == 'report'):

            device['MinimumFreeSpace'] = 0

            if verbose:
                print(time.ctime() + 
                  " [" + device['ModelNumber'] + " " + device['DeviceID'] + "]"
                  " Operating in " + mode + " mode. No recordings will be"
                  " deleted.")

        # End mode if

        if mode == 'maintain':

            if threshold_gib:
                device['MinimumFreeSpace'] = threshold_gib * BYTES_PER_GiB
            else:
                device['MinimumFreeSpace'] = device['TotalSpace'] * (threshold_pct / 100)

            device['MaxRecordingBps'] = get_max_device_Bps(device)

            if verbose:
                print(time.ctime() + 
                  " [" + device['ModelNumber'] + " " + device['DeviceID'] + "]"
                  " Operating in maintain mode. Recordings will be deleted"
                  " to maintain minimum free space of ", end = '')

                if threshold_gib:
                    print(str(threshold_gib) + " GiB.")
                else:
                    print(str(threshold_pct) + "%.")

           # End verbose if

        # End maintain if

        while True:

            refresh_device_data(device)

            report_space_utilization(device)

            if mode == 'maintain':

                if device['FreeSpace'] < device['MinimumFreeSpace']:

                    sorted_recordings = get_sorted_recordings(device, delete_policy)

                    if len(sorted_recordings) > 0:
                        delete_recording(device, sorted_recordings[0])
                    else:
                        if verbose:
                            print(time.ctime() + 
                              " [" + device['ModelNumber'] + " " + device['DeviceID'] + "]"
                              " No recordings found")

                    check_interval = 10

                elif device['FreeSpace'] == device['MinimumFreeSpace']:

                    check_interval = 10

                else:

                    bytes_to_threshold = device['FreeSpace'] - device['MinimumFreeSpace']
                    check_interval = math.floor(bytes_to_threshold / device['MaxRecordingBps'])

                # End FreeSpace if

                if (check_interval_override is None) and verbose:
                    print(time.ctime() + 
                      " [" + device['ModelNumber'] + " " + device['DeviceID'] + "]"
                      " Will check again in " + 
                      str(check_interval) + " seconds")

            # End maintain if

            time.sleep(check_interval_override 
              if check_interval_override is not None 
                else check_interval)

        # End while loop

    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}', file=sys.stderr)
    except JSONDecodeError as json_err:
        print(f'JSON decoding error occurred: {json_err}', file=sys.stderr)
    except KeyboardInterrupt:
        print()
        sys.exit()
    except Exception as err:
        print(f'Other error occurred: {err}', file=sys.stderr)

# End main()

if __name__ == "__main__":
    main()

# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai nu :