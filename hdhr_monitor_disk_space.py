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
import collections.abc
import configparser
import logging
import math
import os
import re
import requests
import socket
import sys
import threading
import time
from pathlib import Path
from requests.exceptions import HTTPError, ConnectionError
from json.decoder import JSONDecodeError

VERSION = '1.5.0'
DISCOVER_DEVICE_ID = 'discover'
WILDCARD_DEVICE_ID = 'FFFFFFFF'
WILDCARD_HOST = 'hdhomerun.local'
MODES = ['report', 'maintain']
DELETE_POLICIES = ['age', 'category']
DEFAULT_DEVICE_ID = DISCOVER_DEVICE_ID
DEFAULT_MODE = MODES[0]
DEFAULT_REPORT_INTERVAL = 600
DEFAULT_THRESHOLD_PCT = 2.0
DEFAULT_DELETE_POLICY = DELETE_POLICIES[0]
DEFAULT_WATCHED_OFFSET = 180
DEFAULT_SETTINGS = {'mode': DEFAULT_MODE,
                    'interval': DEFAULT_REPORT_INTERVAL,
                    'count': None,
                    'delete_policy': DEFAULT_DELETE_POLICY,
                    'gigabytes_free': None,
                    'percent_free': None,
                    'watched_first': False,
                    'watched_offset': DEFAULT_WATCHED_OFFSET
                    }
MIN_CHECK_INTERVAL = 3
API_HOST = 'api.hdhomerun.com'
API_DISCOVER_URL = f'https://{API_HOST}/discover'
RECORDING_RULES_URL = f'https://{API_HOST}/api/recording_rules?DeviceAuth='
MAX_STREAMS = {'HDVR': 4, 'HHDD': 6, 'RECORD': 16}
BYTES_PER_KiB = 2**10
BYTES_PER_MiB = 2**20
BYTES_PER_GiB = 2**30
BYTES_PER_TiB = 2**40
BYTES_PER_KB = 10**3
BYTES_PER_MB = 10**6
BYTES_PER_GB = 10**9
BYTES_PER_TB = 10**12

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
run_event = threading.Event()


class DuplicateDeviceError(Exception):

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


class DeviceNotFoundError(Exception):

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


class NoDeviceStorageError(Exception):

    # Constructor or Initializer
    def __init__(self, value=None):
        if value is None:
            value = ''
        else:
            self.value = value

    # __str__ is to print() the value
    def __str__(self):
        return(repr(self.value))


class LessThanFilter(logging.Filter):

    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        return(1 if record.levelno < self.max_level else 0)

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
        return(formatter.format(record))

# End CustomFormatter


class CaseInsensitiveDict(collections.abc.MutableMapping):
    """ Ordered case insensitive mutable mapping class. """
    def __init__(self, *args, **kwargs):
        self._d = collections.OrderedDict(*args, **kwargs)
        self._convert_keys()
    def _convert_keys(self):
        for k in list(self._d.keys()):
            v = self._d.pop(k)
            self._d.__setitem__(k, v)
    def __len__(self):
        return len(self._d)
    def __iter__(self):
        return iter(self._d)
    def __setitem__(self, k, v):
        self._d[k.lower()] = v
    def __getitem__(self, k):
        return self._d[k.lower()]
    def __delitem__(self, k):
        del self._d[k.lower()]

# End CaseInsensitiveDict


def mode(string):

    if string not in MODES:
        raise ValueError()
    return(string)


def validate_mode(string):

    try:
        value = mode(string)
        return(value)
    except Exception:
        raise ValueError(f'invalid mode value: {string!r}')


def interval(string):

    try:
        value = int(string)
    except Exception:
        raise ValueError()
    if (value <= 0):
        raise ValueError()
    return(value)


def validate_interval(string):

    try:
        value = interval(string)
        return(value)
    except Exception:
        raise ValueError(f'invalid interval value: {string!r}')


def count(string):

    try:
        value = int(string)
    except Exception:
        raise ValueError()
    if (value < 0):
        raise ValueError()
    return(value)


def validate_count(string):

    try:
        if string is None or string == '':
            return(None)
        else:
            value = count(string)
            return(value)
    except Exception:
        raise ValueError(f'invalid count value: {string!r}')


def delete_policy(string):

    if string not in DELETE_POLICIES:
        raise ValueError()
    return(string)


def validate_delete_policy(string):

    try:
        value = delete_policy(string)
        return(value)
    except Exception:
        raise ValueError(f'invalid delete_policy value: {string!r}')


def gigabytes_free(string):

    try:
        value = float(string)
    except Exception:
        raise ValueError()
    if (value <= 0):
        raise ValueError()
    return(value)


def validate_gigabytes_free(string):

    try:
        if string is None or string == '':
            return(None)
        else:
            value = gigabytes_free(string)
            return(value)
    except Exception:
        raise ValueError(f'invalid gigabytes_free value: {string!r}')


def percent_free(string):

    try:
        value = float(string)
    except Exception:
        raise ValueError()
    if (value <= 0) or (value >= 100):
        raise ValueError()
    return(value)


def validate_percent_free(string):

    try:
        if string is None or string == '':
            return(None)
        else:
            value = percent_free(string)
            return(value)
    except Exception:
        raise ValueError(f'invalid percent_free value: {string!r}')


def watched_offset(string):

    try:
        value = int(string)
    except Exception:
        raise ValueError()
    if (value < 0):
        raise ValueError()
    return(value)


def validate_watched_offset(string):

    try:
        value = watched_offset(string)
        return(value)
    except Exception:
        raise ValueError(f'invalid watched_offset value: {string!r}')


def binarysize(bytes, digits=2):

    fmt = '{:.' + str(digits) + 'f}'

    if bytes >= BYTES_PER_TB:
        fmt = fmt + ' TB'
        divisor = BYTES_PER_TB
    elif bytes >= BYTES_PER_GB:
        fmt = fmt + ' GB'
        divisor = BYTES_PER_GB
    elif bytes >= BYTES_PER_MB:
        fmt = fmt + ' MB'
        divisor = BYTES_PER_MB
    elif bytes >= BYTES_PER_KB:
        fmt = fmt + ' KB'
        divisor = BYTES_PER_KB
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
    remaining_seconds = int(seconds)

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

    parser = argparse.ArgumentParser(
               description='Monitor disk space utilization of one or more '
               + 'HDHomeRun SCRIBE, SERVIO, and/or RECORD devices. Optionally '
               + 'delete recordings to stay above a specified free space '
               + 'minimum.',
               epilog='The interval for free space checks in maintain mode '
               + 'is independent from the interval for disk utilization '
               + 'reports (-i/--interval). The maintenance runs in the '
               + 'background at an interval based on the amount of free space '
               + 'found during the last check. If there is a lot of space '
               + 'available, it will be a long time - maybe many hours - '
               + 'until the next check. If there is little free space '
               + 'available, it might be only a few seconds until the next '
               + 'check. This can be observed with verbose output enabled '
               + '(-v/--verbose).'
               )

    parser.add_argument(
      '-d', '--device-id', action='extend', nargs="+", type=str,
      dest='device_list', metavar='DEVICE_ID|IP|HOSTNAME|ALL',
      help='ID, IP address, or hostname of device(s) to monitor. Default is '
      + f'"{DEFAULT_DEVICE_ID}" which discovers devices on the local network '
      + 'and monitors the first device found with a StorageID. If "ALL" is '
      + 'specified, then all devices found with StorageID will be monitored.'
      )

    parser.add_argument(
      '-f', '--conf-file', metavar='FILE', type=argparse.FileType('r'),
      help='Path to configuration file. The configuration file supports '
      + 'overriding the built-in defaults, as well as per-device settings. '
      + 'See example. Per-device settings are applied when a device '
      + 'ID is specified using -d/--device-id. Options given on the '
      + 'command-line override those in the configuration file.'
      )

    parser.add_argument(
      '-m', '--mode', choices=MODES, type=mode,
      help='Mode of operation. "report" mode reports disk space utilization '
      + 'periodically. "maintain" mode reports disk space utilization, and '
      + 'also maintains a minimum amount of free space by deleting recordings '
      + 'when less than the minimum amount of free space is available. '
      + 'Deleted recordings are set to record again. Default is '
      + f'"{DEFAULT_MODE}".'
      )

    parser.add_argument(
      '-i', '--interval', metavar='SECONDS', type=interval,
      help='Number of seconds between space utilization reports. Default is '
      + f'{DEFAULT_REPORT_INTERVAL}.'
      )

    parser.add_argument(
      '-c', '--count', metavar='NUMBER', type=count,
      help='Number of space utilization reports to print before stopping. '
      + 'Default is to continue forever. To disable regular reports in '
      + 'maintain mode, set this to zero (0).'
      )

    threshold_group = parser.add_mutually_exclusive_group()

    threshold_group.add_argument(
      '-g', '--gigabytes-free', metavar='GIGABYTES', type=gigabytes_free,
      help='Minimum number of free gigabytes (GB) of disk space to maintain. '
      + 'Only applicable in maintain mode. Cannot be used in combination with '
      + '-p/--percent-free.'
      )

    threshold_group.add_argument(
      '-p', '--percent-free', metavar='PERCENT', type=percent_free,
      help='Minimum percentage of free disk space to maintain. '
      + 'Only applicable in maintain mode. Cannot be used in combination with '
      + f'-g/--gigabytes-free. Default is {DEFAULT_THRESHOLD_PCT}, if '
      + 'neither gigabytes or percent are specified.'
      )

    parser.add_argument(
      '-s', '--delete-policy', choices=DELETE_POLICIES, type=delete_policy,
      help='Delete policy / sort method. Determines how recordings are '
      + 'sorted when selecting one to delete in maintain mode. '
      + '"age" sorts only on the age of the recordings. "category" sorts '
      + f'first by category {CATEGORY_PRIORITY}, then by age. '
      + 'Use in combination with -l/--list-recordings to determine which '
      + 'policy works best for your situation. Default is '
      + f'"{DEFAULT_DELETE_POLICY}".'
      )

    parser.add_argument(
      '-w', '--watched-first', action='store_const', const=True,
      help='Delete watched recordings first, before applying the selected '
      + 'delete policy. Default is to apply the selected delete policy '
      + 'without regard to whether recordings are watched or not.'
      )

    parser.add_argument(
      '-o', '--watched-offset', metavar='SECONDS', type=watched_offset,
      help='Threshold for considering a recording "watched". This is the '
      + 'number of seconds remaining to be watched at the end of a recording '
      + 'below which it is considered "watched". Default is '
      + f'{DEFAULT_WATCHED_OFFSET} seconds '
      + f'({duration(DEFAULT_WATCHED_OFFSET)}).'
      )

    parser.add_argument(
      '-l', '--list-recordings', action='store_true',
      help='List recordings in the order that they would be deleted in '
      + 'maintain mode, and then exit. Use in combination with '
      + '-s/--delete-policy and -w/--watched-first to determine which '
      + 'policy works best for your situation.'
      )

    parser.add_argument(
      '-V', '--version', action='store_true',
      help='Show version number and exit.'
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

    args = parser.parse_args(argv)
    return(args)

# End parse_args


def parse_conf(conf_file, device_id, settings):

    config = configparser.ConfigParser(dict_type=CaseInsensitiveDict)
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

        settings['mode'] = validate_mode(config.get(
                             section, 'mode',
                             fallback=settings['mode']
                             ))
        settings['interval'] = validate_interval(config.get(
                                 section, 'interval',
                                 fallback=settings['interval']
                                 ))
        settings['count'] = validate_count(config.get(
                              section, 'count',
                              fallback=settings['count']
                              ))
        settings['delete_policy'] = validate_delete_policy(config.get(
                                      section, 'delete_policy',
                                      fallback=settings['delete_policy']
                                      ))
        settings['gigabytes_free'] = validate_gigabytes_free(config.get(
                                       section, 'gigabytes_free',
                                       fallback=settings['gigabytes_free']
                                       ))
        settings['percent_free'] = validate_percent_free(config.get(
                                     section, 'percent_free',
                                     fallback=settings['percent_free']
                                     ))
        settings['watched_first'] = config.getboolean(
                                      section, 'watched_first',
                                      fallback=settings['watched_first']
                                      )
        settings['watched_offset'] = validate_watched_offset(config.get(
                                       section, 'watched_offset',
                                       fallback=settings['watched_offset']
                                       ))

        if (settings['gigabytes_free'] is not None
                and settings['percent_free'] is not None):
            raise ValueError('gigabytes_free and percent_free cannot both be '
                             'specified'
                             )

    except ValueError as e:
        raise ValueError(f'Configuration file {conf_file.name}: {str(e)}')

# End parse_conf


def get_all_device_ids():

    device_id_list = []

    local_ip_pattern = re.compile(r'(?P<ip_addr>[^:]+)(?P<port>(:|\d+))')

    response = requests.get(API_DISCOVER_URL)
    response.raise_for_status()
    devices = response.json()

    for device in devices:
        if 'StorageID' in device:
            if 'DeviceID' in device:
                device_id_list.append(device['DeviceID'])
            elif 'LocalIP' in device:
                m = local_ip_pattern.match(device['LocalIP'])
                device_id_list.append(m.group('ip_addr'))

    return(device_id_list)


def get_device(device_id):

    device_found = False
    device_id_pattern = re.compile(r'^[0-9A-F]{8}$', re.IGNORECASE)
    model_number_pattern = re.compile(r'(?P<family>[A-Z]{4})-(?P<version>.*)')
    friendly_name_pattern = re.compile(r'HDHomeRun (?P<family>.*)')
    local_ip_pattern = re.compile(r'(?P<ip_addr>[^:]+)(?P<port>(:|\d+))')

    # Try to use the .local URLs, first.  But don't count on it since
    # .local name resolution won't work everywhere. And even if this
    # works, we'll still have to go to the internet later to get the
    # recordings. But if it does work, it will minimize required
    # internet access.
    if device_id.upper() == WILDCARD_DEVICE_ID.upper():
        host = WILDCARD_HOST
    elif device_id_pattern.match(device_id):
        host = f'hdhr-{device_id}.local'
    else:
        host = device_id

    try:
        socket.gethostbyname(host)
        url = f'http://{host}/discover.json'
        logger.debug(f'Trying {url}')
        response = requests.get(url)
        response.raise_for_status()
        device = response.json()

        device_found = verify_device(device, device_id)
        if device_found:
            device['DiscoverURL'] = f"{device['BaseURL']}/discover.json"

    except socket.gaierror:
        logger.debug(f'Bad hostname or device ID: {host}')
        pass
    except ConnectionError as conn_err:
        logger.debug(f"That didn't work: {conn_err}")
        pass

    if not device_found:
        logger.debug(f'Trying {API_DISCOVER_URL}')
        response = requests.get(API_DISCOVER_URL)
        response.raise_for_status()
        devices = response.json()

        for device in devices:
            device_found = verify_device(device, device_id)
            if device_found:
                refresh_device_data(device)
                break

    if not device_found:
        raise DeviceNotFoundError(device_id)

    # Custom elements
    device['StatusURL'] = f"{device['BaseURL']}/status.json"
    device['MinimumFreeSpace'] = 0
    if 'ModelNumber' in device:
        device['Tag'] = f"[{device['ModelNumber']} "
        m = model_number_pattern.match(device['ModelNumber'])
        model_family = m.group('family')
    else:
        m = friendly_name_pattern.match(device['FriendlyName'])
        model_family = m.group('family')
        device['Tag'] = f'[{model_family} '

    if device_id.upper() in [DISCOVER_DEVICE_ID.upper(),
                             WILDCARD_DEVICE_ID.upper(),
                             WILDCARD_HOST.upper()]:
        if 'DeviceID' in device:
            device['Tag'] += device['DeviceID']
        elif 'LocalIP' in device:
            m = local_ip_pattern.match(device['LocalIP'])
            device['Tag'] += m.group('ip_addr')
    else:
        device['Tag'] += device_id

    device['Tag'] += ']'
    max_device_streams = (MAX_STREAMS[model_family])
    device['MaxRecordingBps'] = ATSC_MAX_TUNER_Bps * max_device_streams

    return(device)

# End get_device


def get_device_settings(device_id, conf_file, cli_settings):

    settings = DEFAULT_SETTINGS.copy()
    if conf_file is not None:
        parse_conf(conf_file, device_id, settings
                   )
    settings.update(cli_settings)

    if (settings['gigabytes_free'] is None
            and settings['percent_free'] is None):
        settings['percent_free'] = DEFAULT_THRESHOLD_PCT

    return(settings)

# End get_device_settings


def verify_device(device, requested_device_id):

    device_is_good = False

    if requested_device_id.upper() in [DISCOVER_DEVICE_ID.upper(),
                                       WILDCARD_DEVICE_ID.upper(),
                                       WILDCARD_HOST.upper()]:
        device_is_good = True

    if not device_is_good and 'DeviceID' in device:
        if device['DeviceID'].upper() == requested_device_id.upper():
            device_is_good = True

    if not device_is_good and (('LocalIP' in device) or ('BaseURL' in device)):
        try:
            requested_device_ip_addr = socket.gethostbyname(
                                         requested_device_id
                                         )
            local_ip_pattern = re.compile(requested_device_ip_addr
                                          + r'($|:\d+)'
                                          )
            if 'LocalIP' in device:
                if local_ip_pattern.match(device['LocalIP']):
                    device_is_good = True
            elif 'BaseURL' in device:
                if local_ip_pattern.search(device['BaseURL']):
                    device_is_good = True

        except socket.gaierror:
            pass

    if (device_is_good) and ('StorageID' not in device):
        # If we're discover-ing (looking for the first device with a
        # StorageID), we can skip this one. Otherwise, it's a hard reject.
        if requested_device_id.upper() == DISCOVER_DEVICE_ID.upper():
            device_is_good = False
            logger.debug(f'Device {device["DeviceID"]} has no storage')
        else:
            raise NoDeviceStorageError(requested_device_id)

    return(device_is_good)

# End verify_device


def refresh_device_data(device):

    response = requests.get(device['DiscoverURL'])
    response.raise_for_status()
    device.update(response.json())

    device['UsedSpace'] = device['TotalSpace'] - device['FreeSpace']

# End refresh_device_data


def get_sorted_recordings(device):

    response = requests.get(device['StorageURL'])
    response.raise_for_status()
    recorded_series = response.json()

    response = requests.get(device['StatusURL'])
    response.raise_for_status()
    resources = response.json()

    current_streams = [resource for resource in resources
                       if resource['Resource'] == 'playback'
                       ]

    recordings = []
    for series in recorded_series:
        response = requests.get(series['EpisodesURL'])
        response.raise_for_status()
        series_recordings = response.json()
        recordings.extend(series_recordings)

    for recording in recordings:
        recording['Playing'] = False
        recording['Watched'] = False

        for stream in current_streams:
            if f"{stream['Name']}" == Path(recording['Filename']).stem:
                recording['Playing'] = True

        if 'Resume' in recording:
            if recording['Resume'] == MAX_RESUME:
                recording['Watched'] = True
            else:
                seconds_unwatched = (recording['RecordEndTime']
                                     - recording['RecordStartTime']
                                     - recording['Resume'])
                if (seconds_unwatched <= device['settings']['watched_offset']):
                    recording['Watched'] = True

    if device['settings']['delete_policy'] == 'age':
        if device['settings']['watched_first']:
            sorted_recordings = sorted(recordings,
                                       key=lambda r: (-r['Watched'],
                                                      r['StartTime']
                                                      )
                                       )
        else:
            sorted_recordings = sorted(recordings,
                                       key=lambda r: r['StartTime']
                                       )

    elif device['settings']['delete_policy'] == 'category':
        for recording in recordings:
            recording['CategoryPriority'] = CATEGORY_PRIORITY.index(
                                              recording['Category']
                                              )
        if device['settings']['watched_first']:
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
    # End delete_policy if

    return(sorted_recordings)

# End get_sorted_recordings


def print_recording_list(device):

    bumper_char = '#'
    header_width = 78
    tag_width = len(device['Tag']) + 2
    left_bumper_width = math.floor((header_width - tag_width) / 2)
    right_bumper_width = header_width - left_bumper_width - tag_width

    for i in range(1, left_bumper_width):
        print(bumper_char, end='')
    print(f' {device["Tag"]} ', end='')
    for i in range(1, right_bumper_width):
        print(bumper_char, end='')
    print()

    recordings = get_sorted_recordings(device)

    for recording in recordings:
        msg = f'{time.ctime(recording["StartTime"])}: {recording["Title"]}'
        if recording['Watched']:
            msg += ' (watched)'
        if recording['Playing']:
            msg += ' (playing)'
        print(msg)

# End print_recording_list


def delete_recording(device):

    try:
        sorted_recordings = get_sorted_recordings(device)
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
                    + time.ctime(recording["StartTime"]),
                    )

        try:
            response = requests.post(recording["CmdURL"]
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


def maintain(device):

    check_interval = 0

    while True:

        seconds_slept = 0
        while seconds_slept < check_interval:
            if run_event.is_set():
                time.sleep(1)
                seconds_slept += 1
            else:
                return()

        with t_lock:
            logger.debug(f'{device["Tag"]} Running maintenance cycle - '
                         + 'checking free space')

            refresh_device_data(device)

            if device['FreeSpace'] < device['MinimumFreeSpace']:
                report_space_utilization(device)
                delete_recording(device)
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
                         + duration(check_interval)
                         )
        # End t_lock

# End maintain


def start_maintenance_thread(device):

    if device['settings']['gigabytes_free'] is None:
        device['MinimumFreeSpace'] = (device['TotalSpace']
                                      * (device['settings']['percent_free']
                                      / 100)
                                      )
        threshold_str = f"{device['settings']['percent_free']:.1f}%"
    else:
        device['MinimumFreeSpace'] = (device['settings']['gigabytes_free']
                                      * BYTES_PER_GB
                                      )
        threshold_str = binarysize(device['MinimumFreeSpace'])

    if device['MinimumFreeSpace'] > device['TotalSpace']:
        raise ValueError(
          'Minimum free space '
          + f'({binarysize(device["MinimumFreeSpace"])}) '
          + f'cannot be greater than device {device["Tag"]} '
          + f'total space ({binarysize(device["TotalSpace"])})'
          )

    msg = (f'{device["Tag"]} Recordings will be deleted according to '
           + f"{device['settings']['delete_policy']} to maintain minimum free "
           + f'space of {threshold_str}.'
           )
    if device['settings']['watched_first']:
        msg += ' Watched recordings will be deleted first.'
    logger.info(msg)

    # Start new thread for maintenance
    maintenance_thread = threading.Thread(
                           target=maintain,
                           name=f'maintenance-{device["Tag"]}',
                           args=(device,)
                           )
    maintenance_thread.start()

# End start_maintenance_thread


def report(device):

    report_count = 0
    while (device['settings']['count'] is None
            or report_count < device['settings']['count']):
        report_count += 1
        seconds_slept = 0
        if report_count > 1:
            while seconds_slept < device['settings']['interval']:
                if run_event.is_set():
                    time.sleep(1)
                    seconds_slept += 1
                else:
                    return()
        with t_lock:
            refresh_device_data(device)
            report_space_utilization(device)

# End report


def start_report_thread(device):

    if device['settings']['count'] != 0:
        msg = (f'{device["Tag"]} Disk space utilization will be reported '
               + f'every {duration(device["settings"]["interval"])}'
               )
        if device['settings']['count'] is not None:
            msg += f', stopping after {device["settings"]["count"]} '
            msg += ('report'
                    if device['settings']['count'] == 1
                    else 'reports'
                    )
        logger.info(msg)

        report_thread = threading.Thread(
                          target=report,
                          name=f'report-{device["Tag"]}',
                          args=(device,),
                          )
        report_thread.start()

# End start_report_thread


def stop_threads():

    run_event.clear()
    for thread in threading.enumerate():
        if (re.match(r'(^report-|^maintenance-)', thread.name)):
            thread.join()

# End stop_threads


def main():

    global logger

    try:
        configure_loggers()

        args = parse_args(sys.argv[1:])

        if args.version:
            print(f'{os.path.basename(sys.argv[0])} {VERSION}')
            sys.exit()
        if args.quiet:
            logger.setLevel(logging.WARNING)
        if args.verbose:
            logger.setLevel(logging.DEBUG)

        if args.device_list is None:
            device_list = [DEFAULT_DEVICE_ID]
        elif 'ALL' in (device_id.upper() for device_id in args.device_list):
            device_list = get_all_device_ids()
        else:
            device_list = args.device_list

        # Populate a dictionary of values only where they were given on the
        # command-line. No defaults should be included. These will be used to
        # override Defaults and config file settings later.
        cli_settings = {}
        if args.mode is not None:
            cli_settings['mode'] = args.mode
        if args.interval is not None:
            cli_settings['interval'] = args.interval
        if args.count is not None:
            cli_settings['count'] = args.count
        if args.delete_policy is not None:
            cli_settings['delete_policy'] = args.delete_policy
        if args.gigabytes_free is not None:
            cli_settings['gigabytes_free'] = args.gigabytes_free
        if args.percent_free is not None:
            cli_settings['percent_free'] = args.percent_free
        if args.watched_first is not None:
            cli_settings['watched_first'] = args.watched_first
        if args.watched_offset is not None:
            cli_settings['watched_offset'] = args.watched_offset

        devices = {}
        storage_ids = {}
        for device_id in device_list:
            device = get_device(device_id)
            device['settings'] = get_device_settings(device_id, args.conf_file,
                                                     cli_settings
                                                     )
            # Make sure the same device is not listed twice
            if device['StorageID'] in storage_ids.keys():
                raise DuplicateDeviceError(
                  f'{device_id}, {storage_ids[device["StorageID"]]}'
                  )
            else:
                storage_ids[device['StorageID']] = device_id
                logger.debug(f'Monitoring device {device["Tag"]}')
                devices[device_id] = device

        if len(devices) == 0:
            raise NoDeviceFoundError

        if args.list_recordings:
            for device_id in devices.keys():
                print_recording_list(devices[device_id])
            sys.exit()

        run_event.set()
        for device_id in devices.keys():
            start_report_thread(devices[device_id])
            if devices[device_id]['settings']['mode'] == 'maintain':
                start_maintenance_thread(devices[device_id])

        safe_to_quit = False
        while not safe_to_quit:
            time.sleep(0.5)
            safe_to_quit = True
            for thread in threading.enumerate():
                if (re.match(r'(^report-|^maintenance-)', thread.name)):
                # if (re.match(r'(^report-)', thread.name)):  # For testing
                    safe_to_quit = False
                    break

        stop_threads()

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
    except DeviceNotFoundError as device_err:
        logger.error(f'Device not found: {device_err}')
        sys.exit(2)
    except NoDeviceFoundError:
        logger.error('No device found to monitor')
        sys.exit(2)
    except NoDeviceStorageError as storage_err:
        logger.error(f'Device has no storage: {storage_err}')
        sys.exit(2)
    except DuplicateDeviceError as dupe_err:
        logger.error('The following device IDs refer to the same device: '
                     + f'{dupe_err}. Specified devices must be unique.')
        sys.exit(2)
    except KeyboardInterrupt:
        stop_threads()
        print()
        sys.exit()
    except BrokenPipeError:
        sys.exit()

# End main()


if __name__ == '__main__':
    main()

# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai nu hls :
