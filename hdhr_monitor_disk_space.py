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
import logging
import math
import re
import requests
import sys
import threading
import time
from requests.exceptions import HTTPError, ConnectionError
from json.decoder import JSONDecodeError

DEFAULT_DEVICE_ID = 'discover'
DEFAULT_MODE = 'report'
DEFAULT_REPORT_INTERVAL = 600
DEFAULT_THRESHOLD_PCT = 2.0
DEFAULT_DELETE_POLICY = 'age'
DEFAULT_WATCHED_OFFSET = 180
MIN_CHECK_INTERVAL = 3
MODES = ['report', 'maintain']
DELETE_POLICIES = ['age', 'category', 'priority']
GENERIC_LOCAL_URL = 'http://hdhomerun.local/discover.json'
NETWORK_DISCOVER_URL = 'https://my.hdhomerun.com/discover'
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

logger = None
t_lock = threading.Lock()


class NoDeviceFoundError(Exception):

    # Constructor or Initializer
    def __init__(self, value=None):
        if value is None:
            value = ''
        else:
            self.value = value

    # __str__ is to print() the value
    def __str__(self):
        return(repr(self.value))

# End NoDeviceFoundError


class LessThanFilter(logging.Filter):

    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        return 1 if record.levelno < self.max_level else 0

# End LessThanFilter


class CustomFormatter(logging.Formatter):

    FORMATS = {
        logging.DEBUG: "%(asctime)s %(msg)s",
        logging.INFO: "%(asctime)s %(msg)s",
        logging.WARNING: "%(asctime)s %(levelname)s %(msg)s",
        logging.ERROR: "%(asctime)s %(levelname)s %(msg)s",
        logging.CRITICAL: "%(asctime)s %(levelname) %(msg)s",
        }

    def format(self, record):
        formatter = logging.Formatter(self.FORMATS.get(record.levelno))
        return formatter.format(record)

# End CustomFormatter


def mode(string):

    if string not in MODES:
        raise ValueError()
    return(string)


def validate_mode(string):

    try:
        mode(string)
    except Exception:
        raise ValueError(f'invalid mode value: {string!r}')


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
        raise ValueError(f'invalid interval value: {string!r}')


def count(string):

    try:
        value = int(string)
    except Exception:
        raise ValueError()
    if (value < 0):
        raise ValueError()
    return value


def validate_count(string):

    try:
        if string is not None:
            count(string)
    except Exception:
        raise ValueError(f'invalid count value: {string!r}')


def delete_policy(string):

    if string not in DELETE_POLICIES:
        raise ValueError()
    return(string)


def validate_delete_policy(string):

    try:
        delete_policy(string)
    except Exception:
        raise ValueError(f'invalid delete_policy value: {string!r}')


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
        raise ValueError(f'invalid gigabytes_free value: {string!r}')


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
        if string is not None:
            percent_free(string)
    except Exception:
        raise ValueError(f'invalid percent_free value: {string!r}')


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
        raise ValueError(f'invalid watched_offset value: {string!r}')


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
        duration_text += f'{remaining_seconds} seconds'

    if remaining_seconds >= DAY_SECONDS:
        days = math.floor(remaining_seconds/DAY_SECONDS)
        remaining_seconds = remaining_seconds - (days * DAY_SECONDS)

        duration_text += f'{days} '
        duration_text += ('day' if days == 1 else 'days')

    if remaining_seconds >= HOUR_SECONDS:
        hours = math.floor(remaining_seconds/HOUR_SECONDS)
        remaining_seconds = remaining_seconds - (hours * HOUR_SECONDS)

        if len(duration_text) > 0:
            duration_text += ', '
        duration_text += f'{hours} '
        duration_text += ('hour' if hours == 1 else 'hours')

    if remaining_seconds >= MINUTE_SECONDS:
        minutes = math.floor(remaining_seconds/MINUTE_SECONDS)
        remaining_seconds = remaining_seconds - (minutes * MINUTE_SECONDS)

        if len(duration_text) > 0:
            duration_text += ', '
        duration_text += f'{minutes} '
        duration_text += ('minute' if minutes == 1 else 'minutes')

    if remaining_seconds > 0:
        seconds = remaining_seconds

        if len(duration_text) > 0:
            duration_text += ', '
        duration_text += f'{seconds} '
        duration_text += ('second' if seconds == 1 else 'seconds')

    return(duration_text)

# End duration


def configure_loggers():

    global logger

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    custom_formatter = CustomFormatter()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(custom_formatter)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(LessThanFilter(logging.WARNING))
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(custom_formatter)
    stderr_handler.setLevel(logging.WARNING)
    logger.addHandler(stderr_handler)

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# End configure_loggers


def parse_args(argv):

    defaults = {'mode': DEFAULT_MODE,
                'interval': DEFAULT_REPORT_INTERVAL,
                'count': None,
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
      '-f', '--conf-file', metavar='FILE', type=argparse.FileType('r'),
      help='Path to configuration file. The configuration file supports '
      + 'overriding the built-in defaults, as well as per-device settings. '
      + 'See example. Per-device settings are applied when a device '
      + 'ID is specified using -d/--device-id. Options given on the '
      + 'command-line override those in the configuration file.'
      )

    conf_parser.add_argument(
      '-d', '--device-id', default=DEFAULT_DEVICE_ID,
      help='ID of device to monitor. Default is "' + DEFAULT_DEVICE_ID
      + '" which discovers devices on the local network and monitors the '
      + 'first device found with a StorageID.'
      )

    parser = argparse.ArgumentParser(
               parents=[conf_parser],
               description='Monitor disk space utilization of one '
               + 'HDHomeRun SCRIBE or SERVIO device.  Optionally delete '
               + 'recordings to stay above a specified free space '
               + 'minimum.',
               epilog='The interval for free space checks in maintain mode '
               + 'is independent from the interval for disk utilization '
               + 'reports (-i/--interval). The maintenance runs in the '
               + 'background at an interval based on the amount of free space '
               + 'found during the last check. If there is a lot of space '
               + 'available, it will be a long time - maybe many hours - '
               + 'before the next check. If there is little free space '
               + 'available, it might be only a few seconds until the next '
               + 'check. This can be observed with verbose output enabled '
               + '(-v/--verbose).'
               )
    parser.set_defaults(**defaults)

    parser.add_argument(
      '-m', '--mode', choices=MODES, type=mode,
      help='Mode of operation. "report" mode reports disk space utilization '
      + 'periodically. "maintain" mode reports disk space utilization, and '
      + 'also maintains a minimum amount of free space by deleting recordings '
      + 'when less than the minimum amount of free space is available. '
      + 'Deleted recordings are set to record again. Default is "%(default)s".'
      )

    parser.add_argument(
      '-i', '--interval', metavar='SECONDS', type=interval,
      help='Number of seconds between space utilization reports. Default is '
      + '%(default)s.'
      )

    parser.add_argument(
      '-c', '--count', metavar='NUMBER', type=count,
      help='Number of space utilization reports to print before stopping. '
      + 'Default is to continue forever.'
      )

    threshold_group = parser.add_mutually_exclusive_group()

    threshold_group.add_argument(
      '-g', '--gigabytes-free', metavar='GIGABYTES', type=gigabytes_free,
      help='Minimum number of free gigabytes (GiB) of disk space to maintain. '
      + 'Only applicable in maintain mode. Cannot be used in combination with '
      + '-p/--percent-free.'
      )

    threshold_group.add_argument(
      '-p', '--percent-free', metavar='PERCENT', type=percent_free,
      help='Minimum percentage of free disk space to maintain. '
      + 'Only applicable in maintain mode. Cannot be used in combination with '
      + '-g/--gigabytes-free. Default is %(default)s, if neither gigabytes '
      + 'or percent are specified.'
      )

    parser.add_argument(
      '-s', '--delete-policy', choices=DELETE_POLICIES, type=delete_policy,
      help='Delete policy / sort method. Determines how recordings are '
      + 'sorted when selecting one to delete in maintain mode. '
      + '"age" sorts only on the age of the recordings. "category" sorts '
      + f'first by category {CATEGORY_PRIORITY}, then by age. '
      + '"priority" sorts first by associated recording rule priority, then '
      + 'age. If no associated recording rule still exists for a recording, '
      + 'its priority defaults to high. '
      + 'Use in combination with -l/--list-recordings to determine which '
      + 'policy works best for your situation. Default is "%(default)s".'
      )

    parser.add_argument(
      '-w', '--watched-first', action='store_true',
      help='Delete watched recordings first, before applying the selected '
      + 'delete policy. Default is to apply the selected delete policy '
      + 'without regard to whether recordings are watched or not.'
      )

    parser.add_argument(
      '-o', '--watched-offset', metavar='SECONDS', type=watched_offset,
      help='Threshold for considering a recording "watched". This is the '
      + 'number of seconds remaining to be watched at the end of a recording '
      + 'below which it is considered "watched". Default is %(default)s '
      + f'seconds ({duration(DEFAULT_WATCHED_OFFSET)}).'
      )

    parser.add_argument(
      '-l', '--list-recordings', action='store_true',
      help='List recordings in the order that they would be deleted in '
      + 'maintain mode, and then exit. Use in combination with '
      + '-s/--delete-policy and -w/--watched-first to determine which '
      + 'policy works best for your situation.'
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
    args, remaining_argv = conf_parser.parse_known_args(argv)

    if args.conf_file is not None:
        # defaults comes back modified with config file settings
        parse_conf(args.conf_file, args.device_id, defaults)

    parser.set_defaults(**defaults)

    args = parser.parse_args(args=remaining_argv, namespace=args)
    return(args)

# End parse_args


def parse_conf(conf_file, device_id, defaults):

    config = configparser.ConfigParser()
    config.read(conf_file.name)

    if (device_id != DEFAULT_DEVICE_ID and config.has_section(device_id)):
        # Parsing through a device section of the config file will
        # take the DEFAULT section into account automatically.
        section = device_id
    else:
        # If the device section is not in the file, the DEFAULT
        # section has to be parsed explicitly.
        section = configparser.DEFAULTSECT

    try:

        if (config.get(section, 'gigabytes_free', fallback='') != ''
                and config.get(section, 'percent_free', fallback='') != ''):
            raise ValueError('gigabytes_free and percent_free cannot both be '
                             'specified'
                             )

        defaults['mode'] = config.get(section, 'mode',
                                      fallback=defaults['mode']
                                      )
        validate_mode(defaults['mode'])
        defaults['interval'] = config.get(section, 'interval',
                                          fallback=defaults['interval']
                                          )
        validate_interval(defaults['interval'])
        defaults['count'] = config.get(section, 'count',
                                       fallback=defaults['count']
                                       )
        if defaults['count'] == '':
            defaults['count'] = None
        validate_count(defaults['count'])
        defaults['delete_policy'] = config.get(
                                      section, 'delete_policy',
                                      fallback=defaults['delete_policy']
                                      )
        validate_delete_policy(defaults['delete_policy'])
        defaults['gigabytes_free'] = config.get(
                                       section, 'gigabytes_free',
                                       fallback=defaults['gigabytes_free']
                                       )
        if defaults['gigabytes_free'] == '':
            defaults['gigabytes_free'] = None
        validate_gigabytes_free(defaults['gigabytes_free'])
        defaults['percent_free'] = config.get(
                                     section, 'percent_free',
                                     fallback=defaults['percent_free']
                                     )
        if defaults['percent_free'] == '':
            defaults['percent_free'] = None
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

        if (defaults['gigabytes_free'] is None
                and defaults['percent_free'] is None):
            defaults['percent_free'] = DEFAULT_THRESHOLD_PCT

    except ValueError as e:
        raise ValueError(f'Configuration file {conf_file.name}: {str(e)}')

# End parse_conf


def get_device(device_id):

    device_found = False

    # Try to use the .local URLs, first.  But don't count on it since
    # .local name resolution won't work everywhere. And even if this
    # works, we'll still have to go to the internet later to get the
    # recordings. But if it does work, it will minimize required
    # internet access.
    try:
        if device_id == DEFAULT_DEVICE_ID:
            logger.debug(f'Trying {GENERIC_LOCAL_URL}')
            response = requests.get(GENERIC_LOCAL_URL)
            response.raise_for_status()
            device = response.json()
        else:
            device_local_url = f'http://hdhr-{device_id}.local/discover.json'
            logger.debug(f'Trying {device_local_url}')
            response = requests.get(device_local_url)
            response.raise_for_status()
            device = response.json()

        device_found = verify_device(device, device_id)
        if device_found:
            device['DiscoverURL'] = f"{device['BaseURL']}/discover.json"

    except ConnectionError as conn_err:
        logger.debug(f"That didn't work: {conn_err}")
        pass

    if not device_found:
        logger.debug(f'Trying {NETWORK_DISCOVER_URL}')
        response = requests.get(NETWORK_DISCOVER_URL)
        response.raise_for_status()
        devices = response.json()

        for device in devices:
            device_found = verify_device(device, device_id)
            if device_found:
                refresh_device_data(device)
                break

        if not device_found:
            raise NoDeviceFoundError

    # Custom elements
    device['StatusURL'] = f"{device['BaseURL']}/status.json"
    device['MinimumFreeSpace'] = 0
    device['Tag'] = f"[{device['ModelNumber']} {device['DeviceID']}]"

    model_family = re.match(r'[A-Z]{4}', device['ModelNumber']).group()
    max_device_streams = (MAX_STREAMS[model_family])
    device['MaxRecordingBps'] = ATSC_MAX_TUNER_Bps * max_device_streams

    return(device)

# End get_device


def verify_device(device, requested_device_id):

    device_is_good = True

    if 'DeviceID' not in device:
        device_is_good = False
        if 'LocalIP' in device:
            logger.debug(f'Device at {device["LocalIP"]} has no device ID')
    else:
        if ((requested_device_id != DEFAULT_DEVICE_ID)
                and (device['DeviceID'] != requested_device_id)):
            device_is_good = False
            logger.debug(f'Device {device["DeviceID"]} is not the one you are '
                         'looking for'
                         )

    if (device_is_good) and ('StorageID' not in device):
        device_is_good = False
        logger.debug(f'Device {device["DeviceID"]} has no storage')

    return(device_is_good)

# End verify_device


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

    response = requests.get(device['StatusURL'])
    response.raise_for_status()
    resources = response.json()

    current_streams = [resource for resource in resources
                       if resource['Resource'] == 'playback'
                       ]

    for recording in recordings:
        recording['Playing'] = False
        recording['Watched'] = False

        for stream in current_streams:
            if f"{stream['Name']}.mpg" == recording['Filename']:
                recording['Playing'] = True

        if 'Resume' in recording:
            if recording['Resume'] == MAX_RESUME:
                recording['Watched'] = True
            else:
                seconds_unwatched = (recording['RecordEndTime']
                                     - recording['RecordStartTime']
                                     - recording['Resume'])
                if (seconds_unwatched <= watched_threshold):
                    recording['Watched'] = True

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
        msg = f'{time.ctime(recording["StartTime"])}: {recording["Title"]}'
        if recording['Watched']:
            msg += ' (watched)'
        if recording['Playing']:
            msg += ' (playing)'
        print(msg)

# End print_recording_list


def delete_recording(device, delete_policy, watched_first, watched_offset):

    try:
        sorted_recordings = get_sorted_recordings(device, delete_policy,
                                                  watched_first, watched_offset
                                                  )
    except ConnectionError as conn_err:
        logger.error(f'Failed to get list of recordings: {conn_err}')
        pass

    if len(sorted_recordings) > 0:

        deletable_recordings = [recording for recording in sorted_recordings
                                if not recording['Playing']
                                ]
        recording = deletable_recordings[0]

        logger.info(f'{device["Tag"]} '
                    + f'Deleting "{recording["Title"]}" recorded at '
                    + f'{time.ctime(recording["StartTime"])}',
                    )

        try:
            response = requests.post(f'{recording["CmdURL"]}'
                                     + '&cmd=delete&rerecord=1'
                                     )
            response.raise_for_status()

        except ConnectionError as conn_err:
            logger.error(f'Failed to delete recording: {conn_err}')
            pass

    else:
        logger.warning(f'{device["Tag"]} No recordings found. Unable to free '
                       + 'more space.')

# End delete_recording


def maintain(device, delete_policy, watched_first, watched_offset):

    check_interval = 0

    while True:

        time.sleep(check_interval)

        with t_lock:
            logger.debug(f'{device["Tag"]} Running maintenance cycle - '
                         + 'checking free space')

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

            logger.debug(f'{device["Tag"]} Next maintenance cycle in '
                         + f'{duration(check_interval)}'
                         )
        # End t_lock

# End maintain


def report_space_utilization(device):

    if device['FreeSpace'] == 0:
        free_pct = 0.0
        used_pct = 100.0
    else:
        free_pct = (device['FreeSpace'] / device['TotalSpace']) * 100
        used_pct = (device['UsedSpace'] / device['TotalSpace']) * 100

    msg = (f'{device["Tag"]} Total: {binarysize(device["TotalSpace"])}; '
           + f'Used: {binarysize(device["UsedSpace"])} ({used_pct:.1f}%); '
           + f'Free: {binarysize(device["FreeSpace"])} ({free_pct:.1f}%)'
           )

    if device['MinimumFreeSpace'] > 0:
        min_free_pct = (device['MinimumFreeSpace'] / device['TotalSpace'])*100
        msg += (f'; Minimum Free: {binarysize(device["MinimumFreeSpace"])} '
                + f'({min_free_pct:.1f}%)'
                )

    logger.info(msg)

# End report_space_utilization


def main():

    global logger

    try:
        configure_loggers()

        args = parse_args(sys.argv[1:])

        quiet = args.quiet
        verbose = args.verbose
        mode = args.mode
        report_interval = args.interval
        report_count_limit = args.count
        delete_policy = args.delete_policy
        threshold_gib = args.gigabytes_free
        threshold_pct = args.percent_free
        watched_first = args.watched_first
        watched_offset = args.watched_offset
        list_recordings = args.list_recordings

        if quiet:
            logger.setLevel(logging.WARNING)
        if verbose:
            logger.setLevel(logging.DEBUG)

        device = get_device(args.device_id)

        logger.debug(f'Monitoring device {device["DeviceID"]}')

        if list_recordings:
            print_recording_list(get_sorted_recordings(device, delete_policy,
                                                       watched_first,
                                                       watched_offset
                                                       ))
            sys.exit()

        if report_count_limit == 0:
            sys.exit()

        if mode == 'maintain':

            if threshold_gib is None:
                device['MinimumFreeSpace'] = (device['TotalSpace']
                                              * (threshold_pct / 100)
                                              )
                threshold_str = f'{threshold_pct:.1f}%'
            else:
                device['MinimumFreeSpace'] = threshold_gib * BYTES_PER_GiB
                threshold_str = binarysize(device['MinimumFreeSpace'])

            if device['MinimumFreeSpace'] > device['TotalSpace']:
                raise ValueError(
                  'Minimum free space '
                  + f'({binarysize(device["MinimumFreeSpace"])}) '
                  + f'cannot be greater than device {device["DeviceID"]} '
                  + f'total space ({binarysize(device["TotalSpace"])})'
                  )

            msg = (f'{device["Tag"]} Recordings will be deleted according to '
                   + f'{delete_policy} to maintain minimum free space of '
                   + f'{threshold_str}.'
                   )
            if watched_first:
                msg += ' Watched recordings will be deleted first.'
            logger.info(msg)

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

        msg = (f'{device["Tag"]} Disk space utilization will be reported '
               + f'every {duration(report_interval)}'
               )
        if report_count_limit is not None:
            msg += f', stopping after {report_count_limit} '
            msg += ('report' if report_count_limit == 1 else 'reports')
        logger.info(msg)

        report_count = 0
        while report_count_limit is None or report_count < report_count_limit:
            report_count += 1
            if report_count > 1:
                time.sleep(report_interval)
            with t_lock:
                refresh_device_data(device)
                report_space_utilization(device)

    except ConnectionError as conn_err:
        logger.error(f'Failed to connect: {conn_err}')
    except HTTPError as http_err:
        logger.error(f'HTTP error occurred: {http_err}')
        sys.exit(2)
    except JSONDecodeError as json_err:
        logger.error(f'JSON decoding error occurred: {json_err}')
        sys.exit(2)
    except ValueError as value_err:
        logger.error(value_err)
        sys.exit(2)
    except NoDeviceFoundError:
        msg = 'No device found to monitor'
        if not verbose:
            msg += '. Run with "--verbose" for more information.'
        logger.error(msg)
        sys.exit(2)
    except KeyboardInterrupt:
        print()
        sys.exit()
    except BrokenPipeError:
        sys.exit()

# End main()


if __name__ == '__main__':
    main()

# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai nu hls :
