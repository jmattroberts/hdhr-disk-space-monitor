#!/usr/bin/env python

# -----------------------------------------------------------------------------
# Copyright (c) 2020 J. Matt Roberts
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor,
# Boston, MA  02110-1301, USA.
# -----------------------------------------------------------------------------

import argparse
import collections.abc
import configparser
import logging
import math
import re
import socket
import sys
import threading
import time

from hdhr_disk_space_monitor import __about__
from hdhr_disk_space_monitor.hdhr.devices import Devices
from hdhr_disk_space_monitor.hdhr.recordings import MAX_RESUME_OFFSET

VERSION = __about__.__version__

BYTES_PER_KiB = 2**10
BYTES_PER_MiB = 2**20
BYTES_PER_GiB = 2**30
BYTES_PER_TiB = 2**40
BYTES_PER_KB = 10**3
BYTES_PER_MB = 10**6
BYTES_PER_GB = 10**9
BYTES_PER_TB = 10**12
MINUTE_SECONDS = 60
HOUR_SECONDS = MINUTE_SECONDS * 60
DAY_SECONDS = HOUR_SECONDS * 24

DISCOVER_DEVICE_ID = 'discover'
WILDCARD_DEVICE_ID = 'FFFFFFFF'
DELETE_POLICIES = ['age', 'category']
DEFAULT_DEVICE_ID = DISCOVER_DEVICE_ID
DEFAULT_REPORT_INTERVAL = 10 * MINUTE_SECONDS
DEFAULT_DELETE_POLICY = DELETE_POLICIES[0]
DEFAULT_WATCHED_OFFSET = 3 * MINUTE_SECONDS
DEFAULT_GLOBAL_SETTINGS = {'delete_policy': DEFAULT_DELETE_POLICY,
                           'watched_first': False
                           }
DEFAULT_DEVICE_SETTINGS = {'interval': DEFAULT_REPORT_INTERVAL,
                           'count': None,
                           'gigabytes_free': None,
                           'percent_free': None,
                           }
DEFAULT_CATEGORY_SETTINGS = {'protected': False,
                             'max_episodes': None,
                             'watched_offset': DEFAULT_WATCHED_OFFSET,
                             'max_age_days': None,
                             'rerecord_deleted': True
                             }
MIN_SPACE_CHECK_INTERVAL = 3
RECORDING_MAINT_INTERVAL = 13 * MINUTE_SECONDS
MAX_RESUME_OFFSET = MAX_RESUME_OFFSET
MAX_STREAMS = {'HDVR': 4,
               'HHDD': 6,
               'RECORD': 16
               }

# Deletion proceeds in the order shown below when using the category
# delete policy, unless overridden by category.delete_order configuration
CATEGORY_LIST = ['news',
                 'series',
                 'sport',
                 'movie',
                 'special'
                 ]

# This is the maximum bitrate for a stream (channel) as per the ATSC 1.0
# spec. Convert it to bytes/sec for use in calcs.
# TODO: Update for ATSC 3.0
ATSC_MAX_TUNER_Mbps = 19.4
ATSC_MAX_TUNER_Bps = (ATSC_MAX_TUNER_Mbps / 8) * BYTES_PER_MiB

args = None
config = None
dry_run = False
logger = None
t_lock = threading.Lock()
run_event = threading.Event()

friendly_name_pattern = re.compile(r'HDHomeRun (?P<family>.*)')
model_number_pattern = re.compile(r'(?P<family>[A-Z]{4})-(?P<version>.*)')
any_thread_name_pattern = re.compile(r'(^report-|^maintenance-)')
report_thread_name_pattern = re.compile(r'^report-')
config_section_name_pattern = re.compile(r'(((?P<type>[^:]+):)|^)(?P<id>.*)')


class DuplicateDeviceError(Exception):
    pass


class DeviceNotFoundError(Exception):
    pass


class NoDevicesFoundError(Exception):
    pass


class DeleteProtectedRecordingError(Exception):
    pass


class DeletePlayingRecordingError(Exception):
    pass


class DeleteRecordingRecordingError(Exception):
    pass


class LessThanFilter(logging.Filter):

    def __init__(self, exclusive_maximum, name=''):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        return(1 if record.levelno < self.max_level else 0)

# End LessThanFilter


class CustomLogFormatter(logging.Formatter):

    FORMATS = {
        logging.DEBUG: '%(asctime)s %(msg)s',
        logging.INFO: '%(asctime)s %(msg)s',
        logging.WARNING: '%(asctime)s %(levelname)s %(msg)s',
        logging.ERROR: '%(asctime)s %(levelname)s %(msg)s',
        logging.CRITICAL: '%(asctime)s %(levelname) %(msg)s',
        }

    def format(self, record):
        formatter = logging.Formatter(self.FORMATS.get(record.levelno))
        return(formatter.format(record))

# End CustomLogFormatter


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


def gigabytes(string):
    try:
        value = float(string)
    except Exception:
        raise ValueError()
    if (value <= 0):
        raise ValueError()
    return(value)


def validate_gigabytes(string):
    try:
        if string is None or string == '':
            return(None)
        else:
            value = gigabytes(string)
            return(value)
    except Exception:
        raise ValueError(f'invalid gigabytes value: {string!r}')


def percent(string):
    try:
        value = float(string)
    except Exception:
        raise ValueError()
    if (value <= 0) or (value >= 100):
        raise ValueError()
    return(value)


def validate_percent(string):
    try:
        if string is None or string == '':
            return(None)
        else:
            value = percent(string)
            return(value)
    except Exception:
        raise ValueError(f'invalid percent value: {string!r}')


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


def delete_order(string):
    try:
        value = float(string)
    except Exception:
        raise ValueError()
    return(value)


def validate_delete_order(string):
    try:
        value = delete_order(string)
        return(value)
    except Exception:
        raise ValueError(f'invalid delete_order value: {string!r}')


def max_episodes(string):
    try:
        value = int(string)
    except Exception:
        raise ValueError()
    if (value < 1):
        raise ValueError()
    return(value)


def validate_max_episodes(string):
    try:
        if string is None or string == '':
            return(None)
        else:
            value = max_episodes(string)
            return(value)
    except Exception:
        raise ValueError(f'invalid max_episodes value: {string!r}')


def max_age_days(string):
    try:
        value = int(string)
    except Exception:
        raise ValueError()
    if (value < 1):
        raise ValueError()
    return(value)


def validate_max_age_days(string):
    try:
        if string is None or string == '':
            return(None)
        else:
            value = max_age_days(string)
            return(value)
    except Exception:
        raise ValueError(f'invalid max_age_days value: {string!r}')


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

        if duration_text:
            duration_text += ', '
        duration_text += f'{hours} '
        duration_text += ('hour' if hours == 1 else 'hours')

    if remaining_seconds >= MINUTE_SECONDS:
        minutes = math.floor(remaining_seconds/MINUTE_SECONDS)
        remaining_seconds = remaining_seconds - (minutes * MINUTE_SECONDS)

        if duration_text:
            duration_text += ', '
        duration_text += f'{minutes} '
        duration_text += ('minute' if minutes == 1 else 'minutes')

    if remaining_seconds > 0:
        seconds = remaining_seconds

        if duration_text:
            duration_text += ', '
        duration_text += f'{seconds} '
        duration_text += ('second' if seconds == 1 else 'seconds')

    return(duration_text)

# End duration


def configure_loggers():

    global logger

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    custom_formatter = CustomLogFormatter()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(custom_formatter)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(LessThanFilter(logging.WARNING))
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(custom_formatter)
    stderr_handler.setLevel(logging.WARNING)
    logger.addHandler(stderr_handler)

    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

# End configure_loggers


def parse_args(argv):

    parser = argparse.ArgumentParser(prog=__about__.__name__,
                                     description=__about__.__description__
                                     )
    parser.SECTCRE = re.compile(r"\[ *(?P<header>[^]]+?) *\]")

    parser.add_argument(
      '-d', '--device-id', action='extend', nargs='+', type=str,
      dest='device_id_list', metavar='DEVICE_ID|IP|HOSTNAME',
      help='ID, IP address, or hostname of device(s) to monitor. Default is '
      f'"{DEFAULT_DEVICE_ID}" which discovers all storage devices on the '
      'local network.'
      )

    parser.add_argument(
      '-f', '--conf-file', metavar='FILE', type=argparse.FileType('r'),
      help='Path to configuration file. The configuration file supports '
      'overriding the built-in defaults, per-device settings, as well as '
      'some settings not available on the command-line. See example. '
      'Options given on the command-line override those in the '
      'configuration file.'
      )

    parser.add_argument(
      '-i', '--interval', metavar='SECONDS', type=interval,
      help='Number of seconds between space utilization reports. Default is '
      f'{DEFAULT_REPORT_INTERVAL}. '
      'This can be set per-device in the configuration file.'
      )

    parser.add_argument(
      '-c', '--count', metavar='NUMBER', type=count,
      help='Number of space utilization reports to print before stopping. '
      'Default is to continue forever. To disable regular reports, set '
      'this to zero (0). '
      'This can be set per-device in the configuration file.'
      )

    threshold_group = parser.add_mutually_exclusive_group()

    threshold_group.add_argument(
      '-g', '--gigabytes-free', metavar='GIGABYTES', type=gigabytes,
      help='Minimum number of gigabytes (GB) of free disk space to maintain. '
      'Causes a maintenance cycle to be run which will delete recordings when '
      'the minimum amount of free space is not available. '
      'Cannot be used in combination with -p/--percent-free. '
      'This can be set per-device in the configuration file.'
      )

    threshold_group.add_argument(
      '-p', '--percent-free', metavar='PERCENT', type=percent,
      help='Minimum percentage of free disk space to maintain. '
      'Causes a maintenance cycle to be run which will delete recordings when '
      'the minimum amount of free space is not available. '
      'Cannot be used in combination with -g/--gigabytes-free. '
      'This can be set per-device in the configuration file.'
      )

    parser.add_argument(
      '-s', '--delete-policy', choices=DELETE_POLICIES, type=delete_policy,
      help='Delete policy / sort method. Determines how recordings are '
      'sorted when selecting one to delete when maintaining free disk '
      'space. "age" sorts only on the age of the recordings and selects the '
      ' oldest for deletion. "category" sorts first by category '
      f'{CATEGORY_LIST}, then by age. Category order can be customized in the '
      'configuration file. '
      'Use in combination with -l/--list-recordings to determine which '
      f'policy is preferred. Default is "{DEFAULT_DELETE_POLICY}".'
      )

    parser.add_argument(
      '-w', '--watched-first', action='store_const', const=True,
      help='Delete watched recordings first, before applying the selected '
      'delete policy. Default is to apply the selected delete policy '
      'without regard to whether recordings are watched or not. '
      'This can be set per-category in the configuration file.'
      )

    parser.add_argument(
      '-o', '--watched-offset', metavar='SECONDS', type=watched_offset,
      help='Threshold for considering a recording "watched". This is the '
      'number of seconds remaining to be watched at the end of a recording '
      'below which it is considered "watched". Default is '
      f'{DEFAULT_WATCHED_OFFSET} seconds '
      f'({duration(DEFAULT_WATCHED_OFFSET)}). '
      'This can be set per-category in the configuration file.'
      )

    parser.add_argument(
      '-l', '--list-recordings', action='store_true',
      help='List recordings in the order that they would be deleted when '
      'maintaining free disk space, and then exit. Use in combination with '
      '-s/--delete-policy and -w/--watched-first to determine which '
      'policy is preferred.'
      )

    parser.add_argument(
      '-n', '--dry-run', action='store_true',
      help='Run without actually deleting any recordings. Log messages will '
      'indicate that recordings are being deleted, but none will actually '
      'be deleted.'
      )

    parser.add_argument(
      '-V', '--version', action='store_true',
      help='Show version number and exit.'
      )

    # This is intended to be used in "test" mode so that the maintenance does
    # not continue running indefinitely after the report count has been
    # satisfied.
    parser.add_argument(
      '-t', '--stop-after-reports', action='store_true',
      help=argparse.SUPPRESS
      )

    verbose_group = parser.add_mutually_exclusive_group()

    verbose_group.add_argument(
      '-q', '--quiet', action='store_true',
      help='Suppress all messages except errors.'
      )

    verbose_group.add_argument(
      '-v', '--verbose', action='store_true',
      help='Print more informational messages.  Free space and delete '
      'messages are printed by default.'
      )

    args = parser.parse_args(argv)
    return(args)

# End parse_args


def parse_global_conf(settings):

    global config
    section = configparser.DEFAULTSECT

    try:
        settings['delete_policy'] = validate_delete_policy(config.get(
                                      section, 'delete_policy',
                                      fallback=settings['delete_policy']
                                      ))
        settings['watched_first'] = config.getboolean(
                                      section, 'watched_first',
                                      fallback=settings['watched_first']
                                      )

    except ValueError as e:
        raise ValueError(f'Configuration file section "{section}": {str(e)}')

# End parse_global_conf


def parse_device_conf(device_key, settings):

    global config

    # Parsing through a name section of the config file will take the DEFAULT
    # section into account automatically. If the device section is not in the
    # file, the DEFAULT section has to be parsed explicitly.
    if config.has_section(f'device:{device_key}'):
        section = f'device:{device_key}'
    elif config.has_section(device_key):
        section = device_key
    else:
        section = configparser.DEFAULTSECT

    try:
        settings['interval'] = validate_interval(config.get(
                                 section, 'interval',
                                 fallback=settings['interval']
                                 ))
        settings['count'] = validate_count(config.get(
                              section, 'count',
                              fallback=settings['count']
                              ))
        settings['gigabytes_free'] = validate_gigabytes(config.get(
                                       section, 'gigabytes_free',
                                       fallback=settings['gigabytes_free']
                                       ))
        settings['percent_free'] = validate_percent(config.get(
                                     section, 'percent_free',
                                     fallback=settings['percent_free']
                                     ))

    except ValueError as e:
        raise ValueError(f'Configuration file section "{section}": {str(e)}')

# End parse_device_conf


def parse_category_conf(category_name, settings):

    global config

    # Parsing through a name section of the config file will take the DEFAULT
    # section into account automatically. If the device section is not in the
    # file, the DEFAULT section has to be parsed explicitly.
    if config.has_section(f'category:{category_name}'):
        section = f'category:{category_name}'
    else:
        section = configparser.DEFAULTSECT

    try:
        settings['protected'] = config.getboolean(
                                  section, 'protected',
                                  fallback=settings['protected']
                                  )
        settings['max_episodes'] = validate_max_episodes(config.get(
                                     section, 'max_episodes',
                                     fallback=settings['max_episodes']
                                     ))
        settings['watched_offset'] = validate_watched_offset(config.get(
                                       section, 'watched_offset',
                                       fallback=settings['watched_offset']
                                       ))
        settings['max_age_days'] = validate_max_age_days(config.get(
                                     section, 'max_age_days',
                                     fallback=settings['max_age_days']
                                     ))
        settings['rerecord_deleted'] = config.getboolean(
                                         section, 'rerecord_deleted',
                                         fallback=settings['rerecord_deleted']
                                         )
        settings['delete_order'] = validate_delete_order(config.get(
                                     section, 'delete_order',
                                     fallback=settings['delete_order']
                                     ))

    except ValueError as e:
        raise ValueError(f'Configuration file section "{section}": {str(e)}')

# End parse_category_conf


def parse_series_conf(series, settings):

    global config

    # Parsing through a name section of the config file will take the DEFAULT
    # section into account automatically. If the device section is not in the
    # file, the DEFAULT section has to be parsed explicitly.
    if config.has_section(f'series:{series.series_id}'):
        section = f'series:{series.series_id}'
    elif config.has_section(f'series:{series.title}'):
        section = f'series:{series.title}'
    else:
        section = configparser.DEFAULTSECT

    try:
        settings['protected'] = config.getboolean(
                                  section, 'protected',
                                  fallback=settings['protected']
                                  )
        settings['max_episodes'] = validate_max_episodes(config.get(
                                     section, 'max_episodes',
                                     fallback=settings['max_episodes']
                                     ))
        settings['watched_offset'] = validate_watched_offset(config.get(
                                       section, 'watched_offset',
                                       fallback=settings['watched_offset']
                                       ))
        settings['max_age_days'] = validate_max_age_days(config.get(
                                     section, 'max_age_days',
                                     fallback=settings['max_age_days']
                                     ))
        settings['rerecord_deleted'] = config.getboolean(
                                         section, 'rerecord_deleted',
                                         fallback=settings['rerecord_deleted']
                                         )

    except ValueError as e:
        raise ValueError(f'Configuration file section "{section}": {str(e)}')

# End parse_series_conf


def get_global_settings(defaults):

    global args
    global config

    global_settings = DEFAULT_GLOBAL_SETTINGS.copy()
    if config is not None:
        parse_global_conf(global_settings)
    if args.delete_policy is not None:
        global_settings['delete_policy'] = args.delete_policy
    if args.watched_first is not None:
        global_settings['watched_first'] = args.watched_first

    return(global_settings)

# End get_global_settings


def get_device_settings(device_key, defaults):

    global args
    global config

    device_settings = defaults.copy()
    if config is not None:
        parse_device_conf(device_key, device_settings)
    if args.interval is not None:
        device_settings['interval'] = args.interval
    if args.count is not None:
        device_settings['count'] = args.count
    if args.gigabytes_free is not None:
        device_settings['gigabytes_free'] = args.gigabytes_free
    if args.percent_free is not None:
        device_settings['percent_free'] = args.percent_free

    if (device_settings['gigabytes_free'] is not None
            and device_settings['percent_free'] is not None):
        raise ValueError('gigabytes_free and percent_free cannot both be '
                         'specified'
                         )

    return(device_settings)

# End get_device_settings


def get_category_settings(category_name, defaults):

    global args
    global config

    category_settings = defaults.copy()
    category_settings['delete_order'] = CATEGORY_LIST.index(category_name)
    if config is not None:
        parse_category_conf(category_name, category_settings)
    if args.watched_offset is not None:
        category_settings['watched_offset'] = args.watched_offset

    if (category_settings['protected']
            and ((category_settings['max_episodes'] is not None)
                 or (category_settings['max_age_days'] is not None)
                 )):
        logger.warning(f'"{category_name}" settings: Setting "protected" and '
                       f'either of "max_age_days" or "max_episodes" might '
                       'give unexpected results.'
                       )

    return(category_settings)

# End get_category_settings


def get_series_settings(series, defaults):

    global args
    global config

    series_settings = defaults.copy()
    if config is not None:
        parse_series_conf(series, series_settings)
    if args.watched_offset is not None:
        series_settings['watched_offset'] = args.watched_offset

    return(series_settings)

# End get_series_settings


def get_monitored_devices(device_id_list):

    monitored_devices = {}
    all_devices = Devices()
    storage_devices = all_devices.storage_servers

    if not storage_devices:
        raise NoDevicesFoundError

    if device_id_list is None:
        device_id_list = [DEFAULT_DEVICE_ID]

    # We find and take care of 'discover' first, so we can save duplicate
    # detection for the explcitly-named devices later.
    if DISCOVER_DEVICE_ID.upper() in (id.upper() for id in device_id_list):
        for device in storage_devices:
            if device.id != '':
                device_key = device.id
            else:
                device_key = device.ip_addr
            monitored_devices[device_key] = device

    for device_id in device_id_list:
        if device_id.upper() == DISCOVER_DEVICE_ID.upper():
            continue  # This was taken care of above
        if device_id.upper() == WILDCARD_DEVICE_ID.upper():
            device = storage_devices[0]
        else:
            device = all_devices.get_storage_by_id(device_id)
            if device is None:
                try:
                    ip_addr = socket.gethostbyname(device_id)
                    device = all_devices.get_storage_by_ip(ip_addr)
                except socket.gaierror:
                    pass
        if device is None:
            raise DeviceNotFoundError(device_id)
        for monitored_key, monitored_device in monitored_devices.items():
            if device == monitored_device:
                raise DuplicateDeviceError(f'{device_id}, {monitored_key}')
        monitored_devices[device_id] = device

    for device_key, device in monitored_devices.items():
        # Add some custom attributes
        device.tag = f'[{device.friendly_name} '
        if device.id != '':
            device.tag += f'{device.id}'
            if device_key != device.id:
                device.tag += f' ({device_key})'
        else:
            device.tag += f'{device.ip_addr}'
            if device_key != device.ip_addr:
                device.tag += f' ({device_key})'
        device.tag += ']'
        device.min_free_space = 0
        if device.model_number != '':
            m = model_number_pattern.match(device.model_number)
        else:
            m = friendly_name_pattern.match(device.friendly_name)
        model_family = m.group('family')
        max_device_streams = (MAX_STREAMS[model_family])
        device.max_recording_Bps = ATSC_MAX_TUNER_Bps * max_device_streams

    return(monitored_devices)

# End get_monitored_devices


def refresh_device_data(device):

    device.refresh()
    device.used_space = device.total_space - device.free_space

# End refresh_device_data


def sort_recordings_by_age(recordings, watched_first):

    if watched_first:
        sorted_recordings = sorted(recordings,
                                   key=lambda r: (
                                     getattr(r, 'is_protected', False),
                                     -getattr(r, 'is_watched', False),
                                     getattr(r, 'start_time')
                                     ))
    else:
        sorted_recordings = sorted(recordings,
                                   key=lambda r: (
                                     getattr(r, 'is_protected', False),
                                     getattr(r, 'start_time')
                                     ))
    return(sorted_recordings)

# End sort_recordings_by_age


def sort_recordings_by_category(recordings, watched_first):

    if watched_first:
        sorted_recordings = sorted(recordings,
                                   key=lambda r: (
                                     getattr(r, 'is_protected', False),
                                     -getattr(r, 'is_watched', False),
                                     getattr(r, 'category_delete_order'),
                                     getattr(r, 'start_time')
                                     ))
    else:
        sorted_recordings = sorted(recordings,
                                   key=lambda r: (
                                     getattr(r, 'is_protected', False),
                                     getattr(r, 'category_delete_order'),
                                     getattr(r, 'start_time')
                                     ))
    return(sorted_recordings)

# End sort_recordings_by_category


def set_watched_flag(recording, settings):

    recording.is_watched = False

    if recording.resume_offset == MAX_RESUME_OFFSET:
        recording.is_watched = True
    else:
        series_settings = settings[f'series:{recording.series_id}']
        seconds_unwatched = (recording.record_end_time
                             - recording.record_start_time
                             - recording.resume_offset)
        if (seconds_unwatched <= series_settings['watched_offset']):
            recording.is_watched = True

# End set_watched_flag


def set_playing_flag(recording, playing_recordings):

    if recording.filename in (r.filename for r in playing_recordings):
        recording.is_playing = True
    else:
        recording.is_playing = False


def set_recording_flag(recording, recording_recordings):

    if recording.filename in (r.filename for r in recording_recordings):
        recording.is_recording = True
    else:
        recording.is_recording = False


def get_sorted_device_recordings(device, settings):

    recorded_series = device.all_recorded_series()

    recordings = []
    for series in recorded_series:
        recordings.extend(series.recorded_episodes())
        if f'series:{series.series_id}' not in settings.keys():
            settings[f'series:{series.series_id}'] = get_series_settings(
                    series,
                    settings[f'category:{series.category}']
                    )

    playing_recordings = device.playing_now()
    recording_recordings = device.recording_now()

    for recording in recordings:
        recording.device = device
        series_settings = settings[f'series:{recording.series_id}']
        recording.is_protected = series_settings['protected']
        recording.category_delete_order = series_settings['delete_order']
        set_watched_flag(recording, settings)
        set_playing_flag(recording, playing_recordings)
        set_recording_flag(recording, recording_recordings)

    if settings['global']['delete_policy'] == 'age':
        sorted_recordings = sort_recordings_by_age(
                              recordings,
                              settings['global']['watched_first']
                              )
    elif settings['global']['delete_policy'] == 'category':
        sorted_recordings = sort_recordings_by_category(
                              recordings,
                              settings['global']['watched_first']
                              )

    return(sorted_recordings)

# End get_sorted_device_recordings


def get_all_series_with_episodes(devices, settings):

    all_series = {}
    for device_key in devices.keys():
        device = devices[device_key]

        device_series = device.all_recorded_series()

        for series in device_series:
            series_id = series.series_id
            if f'series:{series_id}' not in settings.keys():
                settings[f'series:{series_id}'] = get_series_settings(
                        series,
                        settings[f'category:{series.category}']
                        )
            if series_id not in all_series:
                all_series[series_id] = {}
                all_series[series_id]['Title'] = series.title
                all_series[series_id]['Category'] = series.category
                all_series[series_id]['Recordings'] = []
            series_recordings = series.recorded_episodes()

            for recording in series_recordings:
                recording.device = device

            all_series[series_id]['Recordings'].extend(series_recordings)

    return(all_series)

# End get_all_series_with_episodes


def print_recording_list(devices, settings):

    for device_key in devices.keys():
        device = devices[device_key]

        bumper_char = '#'
        header_width = 78
        tag_width = len(device.tag) + 2
        left_bumper_width = math.floor((header_width - tag_width) / 2)
        right_bumper_width = header_width - left_bumper_width - tag_width

        for i in range(1, left_bumper_width):
            print(bumper_char, end='')
        print(f' {device.tag} ', end='')
        for i in range(1, right_bumper_width):
            print(bumper_char, end='')
        print()

        recordings = get_sorted_device_recordings(device, settings)

        for recording in recordings:
            msg = (f'{time.ctime(recording.start_time)}: '
                   f'{recording.series_title}'
                   )
            if recording.is_watched:
                msg += ' (watched)'
            if recording.is_protected:
                msg += ' (protected)'
            print(msg)

# End print_recording_list


def print_device_space_report(device):

    if device.free_space == 0:
        free_pct = 0.0
        used_pct = 100.0
    else:
        free_pct = (device.free_space / device.total_space) * 100
        used_pct = (device.used_space / device.total_space) * 100

    msg = (f'{device.tag} Total: {binarysize(device.total_space)}; '
           f'Used: {binarysize(device.used_space)} ({used_pct:.1f}%); '
           f'Free: {binarysize(device.free_space)} ({free_pct:.1f}%)'
           )
    if device.min_free_space > 0:
        min_free_pct = (device.min_free_space / device.total_space) * 100
        msg += (f'; Minimum Free: {binarysize(device.min_free_space)} '
                f'({min_free_pct:.1f}%)'
                )
    logger.info(msg)

# End print_device_space_report


def delete_recording(recording, settings, reason=''):

    logger.info(f'{recording.device.tag} '
                f'Deleting "{recording.series_title}" recorded '
                f'{time.ctime(recording.start_time)} {reason}')

    if settings[f'series:{recording.series_id}']['protected']:
        raise DeleteProtectedRecordingError()
    if not hasattr(recording, 'is_playing'):
        playing_recordings = recording.device.playing_now()
        set_playing_flag(recording, playing_recordings)
    if recording.is_playing:
        raise DeletePlayingRecordingError()
    if not hasattr(recording, 'is_recording'):
        recording_recordings = recording.device.recording_now()
        set_recording_flag(recording, recording_recordings)
    if recording.is_recording:
        raise DeleteRecordingRecordingError()
    if dry_run:
        return()

    recording.delete(
      settings[f'series:{recording.series_id}']['rerecord_deleted']
      )

# End delete_recording


def delete_aged_recordings(recordings, settings):

    pruned_recordings = recordings.copy()

    for recording in recordings:
        series_id = recording.series_id
        max_age_days = settings[f'series:{series_id}']['max_age_days']
        min_end_time = (time.time() - (max_age_days * DAY_SECONDS))
        if recording.end_time < min_end_time:
            try:
                delete_recording(recording, settings,
                                 reason=("because it's older than "
                                         f'{max_age_days} days'
                                         ))
                pruned_recordings.remove(recording)
            except DeletePlayingRecordingError:
                logger.warning(
                  f'Failed to delete "{recording.series_title}" '
                  f'recorded {time.ctime(recording.start_time)} '
                  "because it's playing right now"
                  )
                continue
            except Exception as e:
                logger.error(e)
                continue
            # No need to catch DeleteProtectedRecordingError since
            # we don't get this far if the series is protected.
            # No need to catch DeleteRecordingRecordingError since
            # min value for max_age_days is '1', and we have to be
            # past the end time of the recording for its age to be
            # positive.

    return(pruned_recordings)

# End delete_aged_recordings


def delete_excess_recordings(recordings, settings):

    watched_first = settings['global']['watched_first']
    # Assumption: all recordings passed in are of the same series
    if recordings:
        max_episodes = (
          settings[f'series:{recordings[0].series_id}']['max_episodes']
          )

    for recording in recordings:
        set_watched_flag(recording, settings)
    sorted_recordings = sort_recordings_by_age(recordings, watched_first)

    while len(sorted_recordings) > max_episodes:
        recording = sorted_recordings.pop(0)
        try:
            delete_recording(recording, settings,
                             reason=('because there are '
                                     f'{len(sorted_recordings)+1} recorded '
                                     f'episodes (maximum is {max_episodes})'
                                     ))
        except DeletePlayingRecordingError:
            logger.warning(f'Failed to delete "{recording.series_title}" '
                           f'recorded {time.ctime(recording.start_time)} '
                           "because it's playing right now"
                           )
            continue
        except DeleteRecordingRecordingError:
            logger.warning(f'Failed to delete "{recording.series_title}" '
                           f'recorded {time.ctime(recording.start_time)} '
                           "because it's recording right now"
                           )
            continue
        except Exception as e:
            logger.error(e)
            continue
        # No need to catch DeleteProtectedRecordingError since
        # we don't get this far if the series is protected.

    return(sorted_recordings)

# End delete_excess_recordings


def delete_spacious_recording(device, settings):

    sorted_recordings = get_sorted_device_recordings(device, settings)
    # Because sorting is done on "is_protected" first, if the
    # first recording is protected, then all remaining recordings
    # are protected.
    while sorted_recordings and not sorted_recordings[0].is_protected:
        recording = sorted_recordings.pop(0)
        try:
            delete_recording(recording,
                             settings,
                             reason='to free space'
                             )
            break
        except DeletePlayingRecordingError:
            logger.warning(f'Failed to delete "{recording.series_title}" '
                           f'recorded {time.ctime(recording.start_time)} '
                           "because it's playing right now"
                           )
            continue
        except DeleteRecordingRecordingError:
            logger.warning(f'Failed to delete "{recording.series_title}" '
                           f'recorded {time.ctime(recording.start_time)} '
                           "because it's recording right now"
                           )
            continue
        except Exception as e:
            logger.error(e)
            # continue'ing here seems dangerous - don't know what the problem
            # is
            pass
    else:
        logger.warning(f'{device.tag} No deletable recordings '
                       'found. Unable to free space.')

# End delete_spacious_recording


def report_device_space(device, device_settings):

    check_interval = device_settings['interval']
    report_count = 0

    while (device_settings['count'] is None
            or report_count < device_settings['count']):

        if report_count > 0:
            wake_time = time.time() + check_interval
            while wake_time - time.time() > 0.5:
                if run_event.is_set():
                    time.sleep(1)
                else:
                    return()

        with t_lock:
            refresh_device_data(device)
            print_device_space_report(device)

        report_count += 1

# End report_device_space


def maintain_device(device, settings):

    check_interval = 0

    while True:

        logger.debug(f'{device.tag} Running maintenance cycle - checking free '
                     'space')

        with t_lock:
            refresh_device_data(device)

            if device.free_space < device.min_free_space:
                print_device_space_report(device)
                delete_spacious_recording(device, settings)
                refresh_device_data(device)
        # End t_lock

        bytes_to_threshold = (device.free_space
                              - device.min_free_space
                              )
        check_interval = math.floor(bytes_to_threshold
                                    / device.max_recording_Bps
                                    )
        if check_interval < MIN_SPACE_CHECK_INTERVAL:
            check_interval = MIN_SPACE_CHECK_INTERVAL

        logger.debug(f'{device.tag} Next maintenance cycle in '
                     f'{duration(check_interval)}'
                     )

        wake_time = time.time() + check_interval
        while wake_time - time.time() > 0.5:
            if run_event.is_set():
                time.sleep(1)
            else:
                return()

# End maintain_device


def maintain_recordings(devices, settings):

    check_interval = RECORDING_MAINT_INTERVAL

    while True:

        with t_lock:
            recorded_series = get_all_series_with_episodes(devices, settings)

            for series_id, series in recorded_series.items():
                series_settings = settings[f'series:{series_id}']
                if series_settings['protected']:
                    continue

                if series_settings['max_age_days'] is not None:
                    remaining_recordings = delete_aged_recordings(
                                             series['Recordings'], settings
                                             )
                    series['Recordings'] = remaining_recordings
                if series_settings['max_episodes'] is not None:
                    remaining_recordings = delete_excess_recordings(
                                             series['Recordings'], settings
                                             )
                    series['Recordings'] = remaining_recordings

        wake_time = time.time() + check_interval
        while wake_time - time.time() > 0.5:
            if run_event.is_set():
                time.sleep(1)
            else:
                return()

# End maintain_recordings


def start_device_report_threads(devices, settings):

    for device_key in devices.keys():
        device = devices[device_key]
        device_settings = settings[f'device:{device_key}']
        if device_settings['count'] == 0:
            break

        msg = (f'{device.tag} Disk space utilization will be reported every '
               f"{duration(device_settings['interval'])}"
               )
        if device_settings['count'] is not None:
            msg += f", stopping after {device_settings['count']} "
            msg += ('report'
                    if device_settings['count'] == 1
                    else 'reports'
                    )
        logger.debug(msg)

        report_thread = threading.Thread(
                          target=report_device_space,
                          name=f'report-{device.tag}',
                          args=(device, device_settings,),
                          )
        report_thread.start()

# End start_device_report_threads


def start_device_maintenance_threads(devices, settings):

    for device_key in devices.keys():
        device = devices[device_key]
        device_settings = settings[f'device:{device_key}']
        if (device_settings['gigabytes_free'] is None
                and device_settings['percent_free'] is None):
            break

        if device_settings['percent_free'] is not None:
            device.min_free_space = (device.total_space
                                     * (device_settings['percent_free'] / 100)
                                     )
            threshold_str = f"{device_settings['percent_free']:.1f}%"
        elif device_settings['gigabytes_free'] is not None:
            device.min_free_space = (device_settings['gigabytes_free']
                                     * BYTES_PER_GB
                                     )
            threshold_str = binarysize(device.min_free_space)

        if device.min_free_space > device.total_space:
            raise ValueError(
              f'Minimum free space ({binarysize(device.min_free_space)}) '
              f'cannot be greater than device {device.tag} total space '
              f'({binarysize(device.total_space)})'
              )

        msg = (f'{device.tag} Recordings will be deleted according to '
               f"{settings['global']['delete_policy']} to maintain minimum "
               f'free space of {threshold_str}.'
               )
        if settings['global']['watched_first']:
            msg += ' Watched recordings will be deleted first.'
        logger.debug(msg)

        maintenance_thread = threading.Thread(
                               target=maintain_device,
                               name=f'maintenance-{device.tag}',
                               args=(device, settings,)
                               )
        maintenance_thread.start()

# End start_device_maintenance_threads


def start_recording_maintenance_thread(devices, settings):

    run_maintenance = False
    for section_name, section_settings in settings.items():
        m = config_section_name_pattern.match(section_name)
        section_type = m.group('type')
        if section_type in [configparser.DEFAULTSECT, 'category', 'series']:
            if 'max_episodes' in section_settings:
                if section_settings['max_episodes'] is not None:
                    run_maintenance = True
            if 'max_age_days' in section_settings:
                if section_settings['max_age_days'] is not None:
                    run_maintenance = True

    if not run_maintenance:
        return()

    maintenance_thread = threading.Thread(
                           target=maintain_recordings,
                           name='maintenance-recordings',
                           args=(devices, settings,)
                           )
    maintenance_thread.start()

# End start_recording_maintenance_threads


def stop_threads():

    run_event.clear()
    for thread in threading.enumerate():
        if any_thread_name_pattern.match(thread.name):
            thread.join()

# End stop_threads


def main():

    global logger
    global dry_run
    global args
    global config
    settings = {}
    config = configparser.ConfigParser(dict_type=CaseInsensitiveDict)

    try:
        args = parse_args(sys.argv[1:])

        if args.version:
            print(f'{__about__.__name__} {VERSION}')
            sys.exit()

        configure_loggers()
        if args.quiet:
            logger.setLevel(logging.WARNING)
        if args.verbose:
            logger.setLevel(logging.DEBUG)

        dry_run = args.dry_run
        if dry_run:
            logger.warning('This is a dry-run. No recordings will be deleted, '
                           'even if log messages indicate that they are.'
                           )

        devices = get_monitored_devices(args.device_id_list)

        if args.conf_file is not None:
            config.read(args.conf_file.name)

        settings['global'] = get_global_settings(DEFAULT_GLOBAL_SETTINGS)
        for device_key in devices.keys():
            settings[f'device:{device_key}'] = get_device_settings(
                                                device_key,
                                                DEFAULT_DEVICE_SETTINGS
                                                )
        for category_name in CATEGORY_LIST:
            settings[f'category:{category_name}'] = get_category_settings(
                                                      category_name,
                                                      DEFAULT_CATEGORY_SETTINGS
                                                      )

        if args.list_recordings:
            print_recording_list(devices, settings)
            sys.exit()

        run_event.set()
        start_device_report_threads(devices, settings)
        start_device_maintenance_threads(devices, settings)
        start_recording_maintenance_thread(devices, settings)

        safe_to_quit = False
        if (args.stop_after_reports):
            thread_name_pattern = report_thread_name_pattern
        else:
            thread_name_pattern = any_thread_name_pattern
        while not safe_to_quit:
            time.sleep(0.5)
            safe_to_quit = True
            for thread in threading.enumerate():
                if thread_name_pattern.match(thread.name):
                    safe_to_quit = False
                    break

        stop_threads()

    except ValueError as value_err:
        logger.error(value_err)
        sys.exit(2)
    except DeviceNotFoundError as device_err:
        logger.error(f'Device not found: {device_err} '
                     '(non-storage devices are ignored)'
                     )
        sys.exit(2)
    except NoDevicesFoundError:
        logger.error('No devices found to monitor')
        sys.exit(2)
    except DuplicateDeviceError as dupe_err:
        logger.error('Specified devices are not unique. The following device '
                     f'IDs refer to the same device: {dupe_err}. '
                     f'This can be caused by using "{DISCOVER_DEVICE_ID}" '
                     'alongside explicit device IDs.')
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
