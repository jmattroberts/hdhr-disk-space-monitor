#!/usr/bin/env -S python -u

# -----------------------------------------------------------------------------
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
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# -----------------------------------------------------------------------------

import argparse
import configparser
import math
import re
import requests
import sys
import threading
import time
from requests.exceptions import HTTPError
from json.decoder import JSONDecodeError

DEFAULT_DEVICE_ID = 'discover'
DEFAULT_MODE = 'report'
DEFAULT_CHECK_INTERVAL = 600
DEFAULT_THRESHOLD_PCT = 2
DEFAULT_DELETE_POLICY = 'age'
DEFAULT_WATCHED_OFFSET = 180
MIN_CHECK_INTERVAL = 3
MODES = ['report', 'maintain']
DELETE_POLICIES = ['age', 'category', 'priority']
DISCOVER_URL = 'https://my.hdhomerun.com/discover'
RULES_URL = 'https://my.hdhomerun.com/api/recording_rules?DeviceAuth='
MAX_STREAMS = {'HDVR': 4, 'HHDD': 6}
BYTES_PER_KiB = 1024
BYTES_PER_MiB = 1024**2
BYTES_PER_GiB = 1024**3
BYTES_PER_TiB = 1024**4

# When a recording has been watched all the way to the end, the Resume
# value is set to this constant.
MAX_RESUME = 2**32 - 1

# Deletion proceeds in the order shown below when using the category
# delete policy
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
t_lock = threading.Lock()


def mode(string):

    if string not in MODES:
        raise ValueError()
    return(string)


def validate_mode(string):

    try:
        mode(string)
    except Exception:
        raise ValueError('invalid mode value: %r' % string)


def interval(string):

    try:
        value = int(string)
    except Exception:
        raise ValueError()
    if (value <= 0):
        raise ValueError()
    return value


def validate_interval(string):

    try:
        interval(string)
    except Exception:
        raise ValueError('invalid interval value: %r' % string)


def delete_policy(string):

    if string not in DELETE_POLICIES:
        raise ValueError()
    return(string)


def validate_delete_policy(string):

    try:
        delete_policy(string)
    except Exception:
        raise ValueError('invalid delete policy value: %r' % string)


def gigabytes_free(string):

    try:
        value = float(string)
    except Exception:
        raise ValueError()
    if (value <= 0):
        raise ValueError()
    return value


def validate_gigabytes_free(string):

    try:
        if string is not None:
            gigabytes_free(string)
    except Exception:
        raise ValueError('invalid gigabytes_free value: %r' % string)


def percent_free(string):

    try:
        value = float(string)
    except Exception:
        raise ValueError()
    if (value <= 0) or (value >= 100):
        raise ValueError()
    return value


def validate_percent_free(string):

    try:
        percent_free(string)
    except Exception:
        raise ValueError('invalid percent_free value: %r' % string)


def watched_offset(string):

    try:
        value = int(string)
    except Exception:
        raise ValueError()
    if (value < 0):
        raise ValueError()
    return value


def validate_watched_offset(string):

    try:
        watched_offset(string)
    except Exception:
        raise ValueError('invalid watched_offset value: %r' % string)


def binarysize(bytes, digits=2):

    fmt = '{:.' + str(digits) + 'f}'

    if bytes >= BYTES_PER_TiB:
        fmt = fmt + ' TiB'
        divisor = BYTES_PER_TiB
    elif bytes >= BYTES_PER_GiB:
        fmt = fmt + ' GiB'
        divisor = BYTES_PER_GiB
    elif bytes >= BYTES_PER_MiB:
        fmt = fmt + ' MiB'
        divisor = BYTES_PER_MiB
    elif bytes >= BYTES_PER_KiB:
        fmt = fmt + ' KiB'
        divisor = BYTES_PER_KiB
    else:
        fmt = fmt + ' B'
        divisor = 1

    return(fmt.format(bytes / divisor))

# End binarysize


def duration(seconds):

    MINUTE_SECONDS = 60
    HOUR_SECONDS = MINUTE_SECONDS * 60
    DAY_SECONDS = HOUR_SECONDS * 24

    duration_text = ''
    remaining_seconds = seconds

    if remaining_seconds == 0:
        duration_text = duration_text + str(remaining_seconds) + ' seconds'

    if remaining_seconds >= DAY_SECONDS:
        days = math.floor(remaining_seconds/DAY_SECONDS)
        duration_text = duration_text + str(days)

        if days == 1:
            duration_text = duration_text + ' day'
        else:
            duration_text = duration_text + ' days'

        remaining_seconds = remaining_seconds - (days * DAY_SECONDS)

    if remaining_seconds >= HOUR_SECONDS:
        hours = math.floor(remaining_seconds/HOUR_SECONDS)

        if len(duration_text) > 0:
            duration_text = duration_text + ', '
        duration_text = duration_text + str(hours)

        if hours == 1:
            duration_text = duration_text + ' hour'
        else:
            duration_text = duration_text + ' hours'

        remaining_seconds = remaining_seconds - (hours * HOUR_SECONDS)

    if remaining_seconds >= MINUTE_SECONDS:
        minutes = math.floor(remaining_seconds/MINUTE_SECONDS)

        if len(duration_text) > 0:
            duration_text = duration_text + ', '
        duration_text = duration_text + str(minutes)

        if minutes == 1:
            duration_text = duration_text + ' minute'
        else:
            duration_text = duration_text + ' minutes'

        remaining_seconds = remaining_seconds - (minutes * MINUTE_SECONDS)

    if remaining_seconds > 0:
        seconds = remaining_seconds

        if len(duration_text) > 0:
            duration_text = duration_text + ', '
        duration_text = duration_text + str(seconds)

        if seconds == 1:
            duration_text = duration_text + ' second'
        else:
            duration_text = duration_text + ' seconds'

    return(duration_text)

# End duration


def parse_args():

    config = None

    defaults = {'mode': DEFAULT_MODE,
                'interval': DEFAULT_CHECK_INTERVAL,
                'delete_policy': DEFAULT_DELETE_POLICY,
                'gigabytes_free': None,
                'percent_free': DEFAULT_THRESHOLD_PCT,
                'watched_first': False,
                'watched_offset': DEFAULT_WATCHED_OFFSET,
                'list_recordings': False,
                'verbose': False,
                'quiet': False
                }

    conf_parser = argparse.ArgumentParser(add_help=False)

    conf_parser.add_argument(
      '-c', '--conf-file', metavar='FILE', type=argparse.FileType('r'),
      help='Path to configuration file. The configuration file supports '
      + 'overriding default settings described below in a general way, as '
      + 'well as per-device settings. See example. Per-device settings are '
      + 'only applied when a specific device ID is provided using '
      + '-d/--device-id. Options given on the command-line override those in '
      + 'the configuration file.'
      )

    conf_parser.add_argument(
      '-d', '--device-id', default=DEFAULT_DEVICE_ID,
      help='ID of device to monitor. Default is "' + DEFAULT_DEVICE_ID
      + '" which discovers devices on the local network and monitors the '
      + 'first found with a StorageID.'
      )

    parser = argparse.ArgumentParser(
               parents=[conf_parser],
               description='Monitor disk space utilization of one '
               + 'HDHomeRun SCRIBE or SERVIO device.  Optionally delete '
               + 'recordings to stay above a specified free space '
               + 'threshold.'
               )
    parser.set_defaults(**defaults)

    parser.add_argument(
      '-m', '--mode', choices=MODES, type=mode,
      help='Mode of operation. "report" mode only reports free space '
      + 'periodically. "maintain" mode will maintain minimum free space by '
      + 'deleting recordings when the free space threshold is crossed. '
      + 'Deleted recordings are set to record again. '
      + 'Default is "%(default)s".'
      )

    parser.add_argument(
      '-i', '--interval', metavar='SECONDS', type=interval,
      help='Number of seconds between space utilization reports. Default is '
      + '%(default)s. In maintain mode, the maintenance cycle runs '
      + 'independently with an adaptive interval. The maintenance interval '
      + 'is calculated based on the maximum number of simultaneous recordings '
      + 'supported by the device model, the theoretical maximum bitrate of '
      + 'each recording, and the minimum time it would take to reach the free '
      + 'space threshold since the last check.'
      )

    threshold_group = parser.add_mutually_exclusive_group()

    threshold_group.add_argument(
      '-g', '--gigabytes-free', metavar='GIGABYTES', type=gigabytes_free,
      help='Number of free gigabytes (GiB) of disk space below which '
      + 'action (delete recording) will be taken. Only applicable in '
      + 'maintain mode.'
      )

    threshold_group.add_argument(
      '-p', '--percent-free', metavar='PERCENT', type=percent_free,
      help='Percentage of free disk space below which action (delete '
      + 'recording) will be taken. Only applicable in maintain mode. '
      + 'Default is %(default)s, if neither gigabytes '
      + 'or percent are specified.'
      )

    parser.add_argument(
      '-s', '--delete-policy', choices=DELETE_POLICIES, type=delete_policy,
      help='Delete policy / sort method. Determines how recordings are '
      + 'sorted when selecting one to delete in maintain mode. '
      + '"age" sorts only on the age of the recordings. "category" sorts '
      + 'first by category ' + str(CATEGORY_PRIORITY) + ', then by age. '
      + '"priority" sorts first by associated recording rule priority, then '
      + 'age. If no associated recording rule still exists for a recording, '
      + 'its priority defaults to high. '
      + 'Use in combination with -l/--list-recordings to determine which '
      + 'policy works best for your situation. '
      + 'Default is "%(default)s".'
      )

    parser.add_argument(
      '-w', '--watched-first', action='store_true',
      help='Delete watched recordings first, before applying the selected '
      + 'delete policy / sort method. Default is to apply the selected delete '
      + 'policy / sort method without regard to whether recordings are '
      + 'watched or not.'
      )

    parser.add_argument(
      '-o', '--watched-offset', metavar='SECONDS', type=watched_offset,
      help='Number of unwatched seconds at the end of a recording at which to '
      + 'consider it "watched". Default is %(default)s seconds ('
      + duration(DEFAULT_WATCHED_OFFSET) + '), meaning that '
      + 'the recording must be watched to within %(default)s seconds of the '
      + 'end to be considered watched.'
      )

    parser.add_argument(
      '-l', '--list-recordings', action='store_true',
      help='List recordings in the order that they would be deleted in '
      + 'maintain mode, and then exit. Use in combination with '
      + '-s/--delete-policy to determine which policy works best for your '
      + 'situation.'
      )

    verbose_group = parser.add_mutually_exclusive_group()

    verbose_group.add_argument(
      '-q', '--quiet', action='store_true',
      help='Suppress all messages except errors.'
      )

    verbose_group.add_argument(
      '-v', '--verbose', action='store_true',
      help='Print more informational messages.  Free space and delete '
      + 'messages are printed by default.'
      )

    # Try to pull a config file and device ID off the command-line first
    args, remaining_argv = conf_parser.parse_known_args()

    if args.conf_file is not None:
        config = configparser.ConfigParser()
        config.read(args.conf_file.name)

        if (args.device_id != DEFAULT_DEVICE_ID
                and config.has_section(args.device_id)):
            # Parsing through a device section of the config file will
            # take the DEFAULT section into account automatically.
            section = args.device_id
        else:
            # If the device section is not in the file, the DEFAULT
            # section has to be parsed explicitly.
            section = configparser.DEFAULTSECT

        try:
            defaults['mode'] = config.get(
                                 section, 'mode',
                                 fallback=defaults['mode']
                                 )
            validate_mode(defaults['mode'])
            defaults['interval'] = config.get(
                                     section, 'interval',
                                     fallback=defaults['interval']
                                     )
            validate_interval(defaults['interval'])
            defaults['delete_policy'] = config.get(
                                          section, 'delete_policy',
                                          fallback=defaults['delete_policy']
                                          )
            validate_delete_policy(defaults['delete_policy'])
            defaults['gigabytes_free'] = config.get(
                                           section, 'gigabytes_free',
                                           fallback=defaults['gigabytes_free']
                                           )
            validate_gigabytes_free(defaults['gigabytes_free'])
            defaults['percent_free'] = config.get(
                                         section, 'percent_free',
                                         fallback=defaults['percent_free']
                                         )
            validate_percent_free(defaults['percent_free'])
            defaults['watched_first'] = config.getboolean(
                                          section, 'watched_first',
                                          fallback=defaults['watched_first']
                                          )
            defaults['watched_offset'] = config.get(
                                           section, 'watched_offset',
                                           fallback=defaults['watched_offset']
                                           )
            validate_watched_offset(defaults['watched_offset'])

            parser.set_defaults(**defaults)

        except ValueError as e:
            print(sys.argv[0] + ': error in ' + args.conf_file.name + ': '
                  + str(e), file=sys.stderr
                  )
            sys.exit(2)

    # End conf_file if

    args = parser.parse_args(args=remaining_argv, namespace=args)
    return(args)

# End parse_args


def get_device(device_id):

    device_found = False

    response = requests.get(DISCOVER_URL)
    response.raise_for_status()
    devices = response.json()

    for device in devices:

        if 'DeviceID' not in device:
            if verbose:
                print(time.ctime() + ' Discovered device at '
                      + device['LocalIP'] + ' has no device ID'
                      )
            continue

        elif (device_id == 'discover'):
            if ('StorageID' in device):
                device_found = True
                if verbose:
                    print(time.ctime()
                          + ' Monitoring discovered device with ID '
                          + device['DeviceID']
                          )
                break
            else:
                if verbose:
                    print(time.ctime() + ' Discovered device '
                          + device['DeviceID'] + ' has no storage'
                          )

        elif device_id == device['DeviceID']:
            if ('StorageID' in device):
                device_found = True
                if verbose:
                    print(time.ctime() + ' Monitoring specified device '
                          + device['DeviceID']
                          )
                break
            else:
                if verbose:
                    print(time.ctime() + ' Specified device '
                          + device['DeviceID'] + ' has no storage'
                          )
                break

        else:
            if verbose:
                print(time.ctime() + ' Discovered device '
                      + device['DeviceID'] + ' is not the one you are looking '
                      + 'for'
                      )

        # End device_id if

    # End devices loop

    if not device_found:
        return(None)

    refresh_device_data(device)

    model = re.match(r'[A-Z]{4}', device['ModelNumber']).group()
    max_device_streams = (MAX_STREAMS[model])
    device['MaxRecordingBps'] = ATSC_MAX_TUNER_Bps * max_device_streams

    return(device)

# End get_device


def refresh_device_data(device):

    response = requests.get(device['DiscoverURL'])
    response.raise_for_status()
    device.update(response.json())

    device['UsedSpace'] = device['TotalSpace'] - device['FreeSpace']

# End refresh_device_data


def get_sorted_recordings(device, sort_method, watched_first,
                          watched_threshold
                          ):

    default_priority = 9999

    response = requests.get(device['StorageURL'])
    response.raise_for_status()
    recordings = response.json()

    response = requests.get(RULES_URL + device['DeviceAuth'])
    response.raise_for_status()
    rules = response.json()

    for recording in recordings:
        if 'Resume' in recording:
            if recording['Resume'] == MAX_RESUME:
                recording['Watched'] = 1
            else:
                seconds_unwatched = (recording['RecordEndTime']
                                     - recording['RecordStartTime']
                                     - recording['Resume'])
                if (seconds_unwatched <= watched_threshold):
                    recording['Watched'] = 1
                else:
                    recording['Watched'] = 0
        else:
            recording['Watched'] = 0

    if sort_method == 'age':
        if watched_first:
            sorted_recordings = sorted(recordings,
                                       key=lambda r: (-r['Watched'],
                                                      r['StartTime']
                                                      )
                                       )
        else:
            sorted_recordings = sorted(recordings,
                                       key=lambda r: r['StartTime']
                                       )

    elif sort_method == 'category':
        for recording in recordings:
            recording['CategoryPriority'] = CATEGORY_PRIORITY.index(
                                              recording['Category']
                                              )
        if watched_first:
            sorted_recordings = sorted(recordings,
                                       key=lambda r: (-r['Watched'],
                                                      r['CategoryPriority'],
                                                      r['StartTime']
                                                      ))
        else:
            sorted_recordings = sorted(recordings,
                                       key=lambda r: (r['CategoryPriority'],
                                                      r['StartTime']
                                                      ))

    elif sort_method == 'priority':

        for recording in recordings:

            # Default to highest priority in case no rule is found, or no
            # priority is given in the rule (i.e., one-off recordings)
            recording['RulePriority'] = default_priority

            for rule in rules:
                if rule['SeriesID'] == recording['SeriesID']:
                    if 'Priority' in rule:
                        recording['RulePriority'] = rule['Priority']

        # End recordings loop

        if watched_first:
            sorted_recordings = sorted(recordings,
                                       key=lambda r: (-r['Watched'],
                                                      r['RulePriority'],
                                                      r['StartTime']
                                                      ))
        else:
            sorted_recordings = sorted(recordings,
                                       key=lambda r: (r['RulePriority'],
                                                      r['StartTime']
                                                      ))

    # End sort_method if

    return(sorted_recordings)

# End get_sorted_recordings


def print_recording_list(recordings):

    for recording in recordings:
        print(time.ctime(recording['StartTime']) + ': ' + recording['Title'],
              end=''
              )
        if recording['Watched'] == 1:
            print(' (watched)')
        else:
            print('')

# End print_recording_list


def delete_recording(device, delete_policy, watched_first, watched_offset):

    sorted_recordings = get_sorted_recordings(device, delete_policy,
                                              watched_first, watched_offset
                                              )
    if len(sorted_recordings) > 0:
        recording = sorted_recordings[0]
        if not quiet:
            print(time.ctime() + ' [' + device['ModelNumber'] + ' '
                  + device['DeviceID'] + ']' ' Deleting "' + recording['Title']
                  + '"' + ' recorded at ' + time.ctime(recording['StartTime'])
                  )

        response = requests.post(recording['CmdURL']
                                 + '&cmd=delete&rerecord=1'
                                 )
        response.raise_for_status()
    else:
        if verbose:
            print(time.ctime() + ' [' + device['ModelNumber']
                  + ' ' + device['DeviceID'] + '] '
                  + 'No recordings found. Unable to free more '
                  + 'space.'
                  )

# End delete_recording


def maintain(device, delete_policy, watched_first, watched_offset):

    while True:
        with t_lock:
            if verbose:
                print(time.ctime() + ' [' + device['ModelNumber'] + ' '
                      + device['DeviceID'] + '] Running maintenance cycle'
                      )

            refresh_device_data(device)

            if device['FreeSpace'] < device['MinimumFreeSpace']:
                report_space_utilization(device)
                delete_recording(device, delete_policy, watched_first,
                                 watched_offset
                                 )
                check_interval = MIN_CHECK_INTERVAL

            elif device['FreeSpace'] == device['MinimumFreeSpace']:
                check_interval = MIN_CHECK_INTERVAL

            else:
                bytes_to_threshold = (device['FreeSpace']
                                      - device['MinimumFreeSpace']
                                      )
                check_interval = math.floor(bytes_to_threshold
                                            / device['MaxRecordingBps']
                                            )
                if check_interval < MIN_CHECK_INTERVAL:
                    check_interval = MIN_CHECK_INTERVAL

            if verbose:
                print(time.ctime() + ' [' + device['ModelNumber'] + ' '
                      + device['DeviceID'] + '] Next maintenance cycle in '
                      + duration(check_interval)
                      )
        # End t_lock

        time.sleep(check_interval)

# End maintain


def report_space_utilization(device):

    if quiet:
        return()

    if device['FreeSpace'] == 0:
        free_pct = 0.0
        used_pct = 100.0
    else:
        free_pct = (device['FreeSpace'] / device['TotalSpace']) * 100
        used_pct = (device['UsedSpace'] / device['TotalSpace']) * 100

    print(time.ctime() + ' [' + device['ModelNumber'] + ' '
          + device['DeviceID'] + ']'
          + ' Total: ' + binarysize(device['TotalSpace']) + ';'
          + ' Used: ' + binarysize(device['UsedSpace'])
          + ' ({:.1f}%);'.format(used_pct)
          + ' Free: ' + binarysize(device['FreeSpace'])
          + ' ({:.1f}%)'.format(free_pct),
          end=''
          )

    if device['MinimumFreeSpace'] > 0:
        min_free_pct = (device['MinimumFreeSpace']
                        / device['TotalSpace']
                        ) * 100
        print('; Minimum Free: '
              + binarysize(device['MinimumFreeSpace'])
              + ' ({:.1f}%)'.format(min_free_pct)
              )
    else:
        print('')

# End report_space_utilization


def main():

    global quiet
    global verbose

    args = parse_args()

    quiet = args.quiet
    verbose = args.verbose
    mode = args.mode
    check_interval = args.interval
    delete_policy = args.delete_policy
    threshold_gib = args.gigabytes_free
    threshold_pct = args.percent_free
    watched_first = args.watched_first
    watched_offset = args.watched_offset
    list_recordings = args.list_recordings

    try:

        device = get_device(args.device_id)

        if device is None:
            print('No device found to monitor', file=sys.stderr)
            sys.exit(2)

        if list_recordings:
            print_recording_list(get_sorted_recordings(device, delete_policy,
                                                       watched_first,
                                                       watched_offset
                                                       ))
            sys.exit()

        if mode == 'report':
            device['MinimumFreeSpace'] = 0
            if not quiet:
                print(time.ctime() + ' [' + device['ModelNumber'] + ' '
                      + device['DeviceID'] + '] Operating in ' + mode
                      + ' mode. No recordings will be deleted.'
                      )

        elif mode == 'maintain':

            if threshold_gib:
                device['MinimumFreeSpace'] = threshold_gib * BYTES_PER_GiB
                threshold_str = str(threshold_gib) + ' GiB'
            else:
                device['MinimumFreeSpace'] = (device['TotalSpace']
                                              * (threshold_pct / 100)
                                              )
                threshold_str = str(threshold_pct) + '%'

            if not quiet:
                print(time.ctime() + ' [' + device['ModelNumber'] + ' '
                      + device['DeviceID'] + '] Operating in maintain mode. '
                      + 'Recordings will be deleted by ' + delete_policy + ' '
                      + 'to maintain minimum free space of ' + threshold_str
                      + '.', end=''
                      )
                if watched_first:
                    print(' Watched recordings will be deleted first.')
                else:
                    print('')

            if device['MinimumFreeSpace'] > device['TotalSpace']:
                print(time.ctime() + ' [' + device['ModelNumber'] + ' '
                      + device['DeviceID'] + '] Minimum free space ('
                      + binarysize(device['MinimumFreeSpace'])
                      + ') is greater than total space ('
                      + binarysize(device['TotalSpace'])
                      + ')', file=sys.stderr
                      )
                sys.exit(2)

            # Start new thread for maintenance
            maintenance = threading.Thread(
                            target=maintain,
                            args=(device, delete_policy,
                                  watched_first, watched_offset
                                  ),
                            daemon=True
                            )
            maintenance.start()

        # End mode if

        while True:
            with t_lock:
                refresh_device_data(device)
                report_space_utilization(device)
            time.sleep(check_interval)

    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}', file=sys.stderr)
        sys.exit(2)
    except JSONDecodeError as json_err:
        print(f'JSON decoding error occurred: {json_err}', file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print()
        sys.exit()
    except Exception as err:
        print(f'Other error occurred: {err}', file=sys.stderr)
        sys.exit(2)

# End main()


if __name__ == '__main__':
    main()

# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai nu hls :
