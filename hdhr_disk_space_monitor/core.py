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
import logging
import math
import os
import re
import socket
import sys
import time

from configparser import DEFAULTSECT
from requests.exceptions import ConnectionError
from rich.console import Console
# from rich.pretty import pprint
from rich.table import Table
from . import __about__
from .const import ATSC_MAX_TUNER_Bps
from .const import BYTES_PER_GB
from .const import CATEGORY_LIST
from .const import CONFIG_FILE_CHECK_INTERVAL
from .const import DAY_SECONDS
from .const import DEFAULT_DELETE_POLICY
from .const import DEFAULT_DEVICE_ID
from .const import DEFAULT_REPORT_INTERVAL
from .const import DEFAULT_WATCHED_OFFSET
from .const import DELETE_BY_CATEGORY
from .const import DELETE_POLICY_OPTIONS
from .const import DEVICE_DISCOVERY_INTERVAL
from .const import DISCOVER_DEVICE_ID
from .const import INFINITE_FUTURE
from .const import MAX_STREAMS
from .const import MIN_SPACE_CHECK_INTERVAL
from .const import RECORDING_MAINT_INTERVAL
from .const import RERECORD_ALL
from .const import RERECORD_UNWATCHED
from .const import RESTART_DELAY
from .const import WILDCARD_DEVICE_ID
from .settings import Settings
from .settings import interval
from .settings import count
from .settings import delete_policy
from .settings import gigabytes
from .settings import percent
from .settings import watched_offset
from .util import decimalsize, duration
from .hdhr.devices import Devices
from .hdhr.recordings import RecordedSeries
from .hdhr.recordings import Recording
from .hdhr.recordings import MAX_RESUME_OFFSET

dry_run = False
logger = None


class DeleteProtectedRecordingError(Exception):
    pass


class DeletePlayingRecordingError(Exception):
    pass


class LessThanFilter(logging.Filter):

    def __init__(self, exclusive_maximum, name=''):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        return(1 if record.levelno < self.max_level else 0)

# End LessThanFilter


class CustomLogFormatter(logging.Formatter):

    def __init__(self):
        # If attached to systemd journal, let it take care of log timestamps
        if 'JOURNAL_STREAM' in os.environ:
            self.FORMATS = {
                logging.DEBUG: '%(msg)s',
                logging.INFO: '%(msg)s',
                logging.WARNING: '%(levelname)s %(msg)s',
                logging.ERROR: '%(levelname)s %(msg)s',
                logging.CRITICAL: '%(levelname) %(msg)s',
                }
        else:
            self.FORMATS = {
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


def configure_loggers(quiet=False, verbose=False):

    global logger

    logger = logging.getLogger()
    if verbose:
        logger.setLevel(logging.DEBUG)
    elif quiet:
        logger.setLevel(logging.WARNING)
    else:
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
      f'"{DEFAULT_DEVICE_ID}" which discovers all storage devices on '
      'the local network.'
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
      '-s', '--delete-policy', choices=DELETE_POLICY_OPTIONS,
      type=delete_policy,
      help='Delete policy / sort method. Determines how recordings are '
      'sorted when selecting one to delete to maintain free disk '
      'space. "age" sorts only on the age of the recordings and selects the '
      'oldest for deletion. "category" sorts first by category '
      f'{CATEGORY_LIST}, then by age. Category order can be customized '
      'in the configuration file. '
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
      help='List recordings in the order that they would be deleted to '
      'maintain free disk space, and then exit. Use in combination with '
      '-s/--delete-policy and -w/--watched-first to determine which '
      'policy is preferred.'
      )

    parser.add_argument(
      '-r', '--list-series', action='store_true',
      help='List recorded series in order of increasing space utilization, '
      'along with the amount of space utilized, and then exit. If watched '
      'recordings exist, the amount of space they occupy will also be printed.'
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

    # This is intended to be used in "test" mode so that the program won't
    # continue running indefinitely.
    parser.add_argument(
      '-t', '--test-mode', action='store_true',
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


def resolve_series_settings(obj, settings):

    if isinstance(obj, Recording):
        series_id = obj.series_id
        series_title = obj.series_title
        series_category = obj.category
    elif isinstance(obj, RecordedSeries):
        series_id = obj.series_id
        series_title = obj.title
        series_category = obj.category
    else:
        print(type(obj))

    # Look for match on series ID first, since that's more precise
    series_settings = settings[f'category:{series_category}'].copy()
    if settings.getConfig().has_section(f'series:{series_id}'):
        series_settings.update(settings[f'series:{series_id}'])
    elif settings.getConfig().has_section(f'series:{series_title}'):
        series_settings.update(settings[f'series:{series_title}'])

    return(series_settings)

# End resolve_series_settings


def get_monitored_devices(desired_device_id_list, devices):

    friendly_name_pattern = re.compile(r'HDHomeRun (?P<short_name>.*)')
    model_number_pattern = re.compile(r'(?P<family>[A-Z]{4})-(?P<version>.*)')

    current_devices = devices
    discovered_devices = {}
    available_devices = Devices()
    storage_devices = available_devices.storage_servers

    if desired_device_id_list is None:
        device_id_list = [DEFAULT_DEVICE_ID]
    else:
        device_id_list = desired_device_id_list.copy()

    # Find and take care of 'discover' first, so duplicate detection can be
    # handled with the explicitly-named devices below.
    if DISCOVER_DEVICE_ID.upper() in (id.upper() for id in device_id_list):
        for device in storage_devices:
            device_id = device.id or device.ip_addr
            device_id_list.append(device_id)

    for device_id in device_id_list:
        if device_id.upper() == DISCOVER_DEVICE_ID.upper():
            continue  # This was taken care of above
        if device_id.upper() == WILDCARD_DEVICE_ID.upper():
            device = storage_devices[0]
        else:
            device = available_devices.get_storage_by_id(device_id)
            if device is None:
                try:
                    ip_addr = socket.gethostbyname(device_id)
                    device = available_devices.get_storage_by_ip(ip_addr)
                except socket.gaierror:
                    pass
        if device is None:
            logger.error(f'Device not found: {device_id} (non-storage devices '
                         'are ignored)'
                         )
            continue
        for discovered_key, discovered_device in discovered_devices.items():
            if discovered_device == device:
                if discovered_key not in current_devices:
                    # The intention is to show this only once, not on every
                    # discovery cycle
                    logger.warning(f'Device "{device_id}" is the same as '
                                   f'device "{discovered_key}". Proceeding '
                                   f'with only "{discovered_key}".'
                                   )
                break
        else:
            discovered_devices[device_id] = device

    devices = {}
    for device_key, device in current_devices.copy().items():
        # Do a refresh to test response. Can't just test to see if it's 'in'
        # the discovered devices because it's possible for a port to change,
        # in which case the IP will still be found as a device key, but
        # it's no longer responding on the original port.
        # Sure, could do the 'in' test, then check for port match, but then
        # the nice exception message is not available.
        try:
            device.refresh()
        except ConnectionError as e:
            # Remove here so it doesn't cause a false match in the 'for' loop
            # below, where the IP matches, but the port does not
            del current_devices[device_key]
            logger.warning(f'{device.tag} Device is not responding: {e}')

    for device_key, device in discovered_devices.items():
        if device_key in current_devices:
            # Keep what we already have
            devices[device_key] = current_devices[device_key]
            continue

        # Add some custom attributes

        # key
        device.key = device_key

        # tag
        m = friendly_name_pattern.match(device.friendly_name)
        short_name = m.group('short_name')
        device.tag = f'[{short_name} '

        if device.id != '':
            device.tag += f'{device.id}'
            if device_key != device.id:
                device.tag += f' ({device_key})'
        else:
            device.tag += f'{device.ip_addr}:{device.http_port}'
            if device_key != device.ip_addr:
                device.tag += f' ({device_key})'
        device.tag += ']'

        # model family
        if device.model_number != '':
            m = model_number_pattern.match(device.model_number)
            model_family = m.group('family')
        else:
            model_family = short_name

        # max bit rate
        max_device_streams = (MAX_STREAMS[model_family]) or 4
        device.max_recording_Bps = ATSC_MAX_TUNER_Bps * max_device_streams

        # Defaults
        device.min_free_space = 0
        device.space_report_count = 0
        device.maintenance_due_time = INFINITE_FUTURE
        device.prior_space_report_time = 0
        device.space_report_interval = -1
        device.space_report_limit = -1
        # These are brought down to the device level solely so that an old vs.
        # new setting comparison can be done at the device level when
        # refreshing settings.
        device.global_delete_policy = None
        device.global_watched_first = None

        if device.total_space is None:
            logger.warning(f'{device.tag} Device does not report disk space '
                           'utilization'
                           )

        devices[device_key] = device

    return(devices)

# End get_monitored_devices


def sort_recordings_for_deletion(recordings, settings):

    dummy_attr_name = 'surely_there_will_never_be_an_attr_with_this_name'
    watched_attr_name = dummy_attr_name
    category_attr_name = dummy_attr_name

    if settings['global']['watched_first']:
        watched_attr_name = 'is_watched'

    if settings['global']['delete_policy'] == DELETE_BY_CATEGORY:
        category_attr_name = 'category_delete_order'

    sorted_recordings = sorted(recordings,
                               key=lambda r: (
                                 getattr(r, 'is_protected', False),
                                 -getattr(r, watched_attr_name, False),
                                 getattr(r, category_attr_name, 0),
                                 getattr(r, 'start_time')
                                 ))
    return(sorted_recordings)

# End sort_recordings_for_deletion


def is_playing_now(recording):

    playing_recordings = recording.device.playing_now()
    return(recording.filename in (r.filename for r in playing_recordings))


def is_recording_now(recording):

    recording_recordings = recording.device.recording_now()
    return(recording.filename in (r.filename for r in recording_recordings))


def get_device_series_with_episodes(device, settings):

    device_series = device.all_recorded_series()

    recorded_series = {}
    for series in device_series:
        series_settings = resolve_series_settings(series, settings)
        series_id = series.series_id
        series.is_protected = series_settings['protected']
        series.watched_offset = series_settings['watched_offset']
        series.category_delete_order = series_settings['delete_order']
        series.rerecord_deleted = series_settings['rerecord_deleted']
        series.max_episodes = series_settings['max_episodes']
        series.max_age_days = series_settings['max_age_days']
        series.min_age_days = series_settings['min_age_days'] or 0

        recorded_series[series_id] = {}
        device_recordings = series.recorded_episodes()
        for recording in device_recordings:
            recording.device = device
            recording.watched_offset = series.watched_offset
            recording.category_delete_order = series.category_delete_order

            seconds_unwatched = (recording.record_end_time
                                 - recording.record_start_time
                                 - recording.resume_offset)
            recording.is_watched = (
              (recording.resume_offset == MAX_RESUME_OFFSET)
              or (seconds_unwatched <= recording.watched_offset)
              )

            if (series.rerecord_deleted == RERECORD_ALL
                    or (series.rerecord_deleted == RERECORD_UNWATCHED
                        and not recording.is_watched
                        )):
                recording.rerecord = True
            else:
                recording.rerecord = False

            recording.is_protected = series.is_protected
            recording.age_in_days = ((time.time() - recording.end_time)
                                     / DAY_SECONDS
                                     )
            # This has the side effect of always automatically protecting
            # recordings that are currently recording. So the exception
            # DeleteRecordingRecordingError is redundant.
            if ((recording.age_in_days < series.min_age_days)
                    and (not recording.is_watched)):
                recording.is_protected = True

        series.recorded_episodes = device_recordings
        recorded_series[series_id] = series

    return(recorded_series)

# End get_device_recordings


def get_sorted_device_recordings(device, settings):

    recorded_series = get_device_series_with_episodes(device, settings)

    recordings = []
    for series_id, series in recorded_series.items():
        recordings.extend(series.recorded_episodes)

    sorted_recordings = sort_recordings_for_deletion(recordings, settings)

    return(sorted_recordings)

# End get_sorted_device_recordings


def get_all_series_with_episodes(devices, settings):

    all_series = {}
    for device_key, device in devices.items():

        device_series = get_device_series_with_episodes(device, settings)

        for series_id, series in device_series.items():
            if series_id not in all_series:
                all_series[series_id] = series
            else:
                for recording in series.recorded_episodes:
                    # Make sure we filter duplicates in case duplicate
                    # detection at the device level fails for some reason.
                    if (recording not in
                            all_series[series_id].recorded_episodes):
                        all_series[series_id].recorded_episodes.append(
                          recording
                          )
        # end series loop
    # end device loop

    return(all_series)

# End get_all_series_with_episodes


def print_recording_list(devices, settings):

    console = Console()

    for device_key in devices.keys():
        device = devices[device_key]
        table = Table(title=device.tag)
        table.add_column('Recording Started', no_wrap=True)
        table.add_column('Series Title', min_width=10)
        table.add_column('Episode Title', min_width=10)
        table.add_column('Category')
        table.add_column('W')
        table.add_column('P')

        for recording in get_sorted_device_recordings(device, settings):
            table.add_row(time.strftime('%c',
                                        time.localtime(recording.start_time)
                                        ),
                          recording.series_title,
                          recording.episode_title,
                          recording.category,
                          'W' if recording.is_watched else '',
                          'P' if recording.is_protected else ''
                          )
        console.print(table)
    print(' (W=Watched, P=Protected)')

# End print_recording_list


def print_series_list(devices, settings):

    console = Console()

    for device_key in devices.keys():
        device = devices[device_key]
        table = Table(title=device.tag, show_footer=True)
        device_total_size = 0
        device_watched_size = 0
        device_episode_count = 0
        device_watched_count = 0

        recorded_series = get_device_series_with_episodes(device, settings)

        for series_id, series in recorded_series.items():
            series.total_size = 0
            series.watched_size = 0
            series.episode_count = 0
            series.watched_count = 0

            for recording in series.recorded_episodes:
                series.total_size += recording.file_size
                series.episode_count += 1
                if recording.is_watched:
                    series.watched_size += recording.file_size
                    series.watched_count += 1
            device_total_size += series.total_size
            device_watched_size += series.watched_size
            device_episode_count += series.episode_count
            device_watched_count += series.watched_count

        sorted_series = dict(sorted(recorded_series.items(),
                             key=lambda r: (getattr(r[1], 'total_size', 0)))
                             )

        table.add_column('Series Title', device.tag, min_width=10)
        table.add_column('Category')
        table.add_column('Total Size', decimalsize(device_total_size),
                         justify='right', min_width=9, max_width=9
                         )
        table.add_column('Total Episodes', str(device_episode_count),
                         justify='right', min_width=8, max_width=8
                         )
        table.add_column('Watched Size', decimalsize(device_watched_size),
                         justify='right', min_width=9, max_width=9
                         )
        table.add_column('Watched Episodes', str(device_watched_count),
                         justify='right', min_width=8, max_width=8
                         )
        table.add_column('P')
        for series_id, series in sorted_series.items():
            table.add_row(series.title, series.category,
                          decimalsize(series.total_size),
                          str(series.episode_count),
                          decimalsize(series.watched_size),
                          str(series.watched_count),
                          'P' if series.is_protected else ''
                          )
        console.print(table)
    print(' (P=Protected)')

# End print_series_list


def print_device_space_report(device):

    used_space = device.total_space - device.free_space
    if device.free_space == 0:
        free_pct = 0.0
        used_pct = 100.0
    else:
        free_pct = (device.free_space / device.total_space) * 100
        used_pct = (used_space / device.total_space) * 100

    msg = (f'{device.tag} Total: {decimalsize(device.total_space)}; '
           f'Used: {decimalsize(used_space)} ({used_pct:.1f}%); '
           f'Free: {decimalsize(device.free_space)} ({free_pct:.1f}%)'
           )
    if (device.min_free_space > 0
            and device.min_free_space < device.total_space):
        min_free_pct = (device.min_free_space / device.total_space) * 100
        msg += (f'; Minimum Free: {decimalsize(device.min_free_space)} '
                f'({min_free_pct:.1f}%)'
                )
    logger.info(msg)

# End print_device_space_report


def delete_recording(recording, reason=''):

    episode_description = f'"{recording.series_title}'
    if len(recording.episode_title) > 0:
        episode_description += f': {recording.episode_title}'
    episode_description += f'", recorded {time.ctime(recording.start_time)},'

    if recording.is_protected:
        logger.debug(f"{recording.device.tag} Skipped deletion of "
                     f"{episode_description} because it's protected"
                     )
        raise DeleteProtectedRecordingError()
    if is_playing_now(recording):
        logger.debug(f"{recording.device.tag} Skipped deletion of "
                     f"{episode_description} because it's playing right now"
                     )
        raise DeletePlayingRecordingError()

    msg = f'{recording.device.tag} Deleting '
    if (recording.rerecord):
        msg += '(will re-record) '
    msg += f'{episode_description} {reason}'
    logger.info(msg)

    if dry_run:
        return()

    recording.delete(recording.rerecord)

# End delete_recording


def delete_aged_recordings(recordings, max_age_days):

    # Assumptions:
    # - Recordings are all of the same series (so have the same max age)
    # - Recordings are sorted by age, oldest to newest

    if max_age_days is None:
        return(recordings)

    pruned_recordings = recordings.copy()
    for recording in recordings:
        if recording.age_in_days <= max_age_days:
            break
        try:
            delete_recording(recording,
                             reason=(f"because it's older than {max_age_days} "
                                     "days"
                                     ))
            pruned_recordings.remove(recording)
        except DeleteProtectedRecordingError:
            continue
        except DeletePlayingRecordingError:
            continue
        except Exception as e:
            logger.error(e)
            continue

    return(pruned_recordings)

# End delete_aged_recordings


def delete_excess_recordings(recordings, max_episodes):

    # Assumptions:
    # - Recordings are all of the same series (so have the same max epidodes)
    # - Recordings are sorted by age, oldest to newest

    if max_episodes is None:
        return recordings

    pruned_recordings = recordings.copy()
    for recording in recordings:
        if len(pruned_recordings) <= max_episodes:
            break
        try:
            delete_recording(recording,
                             reason=('because there are '
                                     f'{len(pruned_recordings)} '
                                     'recorded episodes '
                                     f'(maximum is {max_episodes})'
                                     ))
            pruned_recordings.remove(recording)
        except DeleteProtectedRecordingError:
            continue
        except DeletePlayingRecordingError:
            continue
        except Exception as e:
            logger.error(e)
            continue

    return(pruned_recordings)

# End delete_excess_recordings


def delete_spacious_recording(device, settings):

    sorted_recordings = get_sorted_device_recordings(device, settings)

    # Because sorting is done on "is_protected" first, once a protected
    # recording is encountered, then all remaining recordings are protected.
    while sorted_recordings and not sorted_recordings[0].is_protected:
        recording = sorted_recordings.pop(0)
        try:
            delete_recording(recording, reason='to free space')
            break
        except DeletePlayingRecordingError:
            continue
        except Exception as e:
            logger.error(e)
            # continue'ing here seems dangerous - don't know what the problem
            # is
            pass
    else:
        logger.warning(f'{device.tag} No deletable recordings found. Unable '
                       'to free space.'
                       )

# End delete_spacious_recording


def report_device_space(device):

    try:
        if (device.space_report_limit is None
                or device.space_report_count < device.space_report_limit):
            device.refresh()
            print_device_space_report(device)
            device.space_report_count += 1
    except ConnectionError as e:
        logger.warning(f'{device.tag} Device is not responding: {e}')
        return()

# End report_device_space


def update_device_settings(device, settings):

    if device is None:
        return
    if f'device:{device.key}' not in settings:
        return

    old_min_free_space = device.min_free_space
    old_global_delete_policy = device.global_delete_policy
    old_global_watched_first = device.global_watched_first
    old_space_report_interval = device.space_report_interval
    old_space_report_limit = device.space_report_limit

    device_settings = settings[f'device:{device.key}']
    device.space_report_interval = device_settings["interval"]
    device.space_report_limit = device_settings["count"]
    device.min_percent_free = device_settings['percent_free']
    device.min_gigabytes_free = device_settings['gigabytes_free']
    device.global_delete_policy = settings['global']['delete_policy']
    device.global_watched_first = settings['global']['watched_first']

    if device.total_space is None:
        device.space_report_limit = 0
    elif ((device.space_report_interval != old_space_report_interval)
            or (device.space_report_limit != old_space_report_limit)):
        msg = (f'{device.tag} Disk space utilization will be reported every '
               f'{duration(device.space_report_interval)}'
               )
        if device.space_report_limit is not None:
            msg += f' and will stop after {device.space_report_limit} '
            msg += 'report' if device.space_report_limit == 1 else 'reports'
        logger.debug(msg)

    if device.total_space is None:
        device.min_free_space = 0
    elif device.min_percent_free is not None:
        device.min_free_space = (device.total_space
                                 * (device.min_percent_free / 100)
                                 )
        threshold_str = f'{device.min_percent_free:.1f}%'
    elif device.min_gigabytes_free is not None:
        device.min_free_space = (device.min_gigabytes_free * BYTES_PER_GB)
        threshold_str = decimalsize(device.min_free_space)
    else:
        device.min_free_space = 0

    if device.min_free_space <= 0:
        if old_min_free_space > 0:
            logger.debug(f'{device.tag} Discontinuing free space maintenance')
        device.maintenance_due_time = INFINITE_FUTURE
    elif device.min_free_space <= device.total_space:
        if device.min_free_space != old_min_free_space:
            device.maintenance_due_time = time.time()
        # else continue existing cadence
        if (device.min_free_space != old_min_free_space
                or device.global_delete_policy != old_global_delete_policy
                or device.global_watched_first != old_global_watched_first):
            msg = (f'{device.tag} A minimum of {threshold_str} free space '
                   'will be maintained. Recordings will be deleted according '
                   f'to {device.global_delete_policy} '
                   )
            if device.global_watched_first:
                msg += '(watched recordings will be deleted first) '
            msg += 'to maintain minimum free space.'
            logger.debug(msg)
    elif device.min_free_space > device.total_space:
        if device.min_free_space != old_min_free_space:
            logger.error(f'{device.tag} Minimum free space '
                         f'({decimalsize(device.min_free_space)}) '
                         'cannot be greater than device total space '
                         f'({decimalsize(device.total_space)})'
                         )
            device.maintenance_due_time = INFINITE_FUTURE

# End update_device_settings


def maintain_device(device, settings):

    if device.min_free_space == 0:
        return()

    try:
        device.refresh()
        logger.debug(f'{device.tag} Running free space maintenance cycle')
        if device.free_space < device.min_free_space:
            print_device_space_report(device)
            delete_spacious_recording(device, settings)
    except ConnectionError as e:
        logger.warning(f'{device.tag} Device is not responding: {e}')
        return()

# End maintain_device


def calc_maintenance_interval(device):

    try:
        device.refresh()
        bytes_to_threshold = device.free_space - device.min_free_space
        interval = math.floor(bytes_to_threshold / device.max_recording_Bps)
        if interval < MIN_SPACE_CHECK_INTERVAL:
            interval = MIN_SPACE_CHECK_INTERVAL
        return(interval)
    except ConnectionError as e:
        logger.warning(f'{device.tag} Device is not responding: {e}')
        return(MIN_SPACE_CHECK_INTERVAL)

# End calc_maintenance_interval


def is_recording_maintenance_configured(settings):

    do_recording_maintenance = False
    config_section_name_pattern = re.compile(
      r'(?P<type>[^:]+)((:(?P<id>.*))|$)'
      )

    # Do we need to run recording maintenance at all?
    # Have to examine config file contents and not resolved settings because
    # category- and series-level settings have not been resolved yet.
    for section_name, config_section in settings.getConfig().items():
        m = config_section_name_pattern.match(section_name)
        section_type = m.group('type')
        if section_type in [DEFAULTSECT, 'category', 'series']:
            if 'max_episodes' in config_section:
                if (config_section['max_episodes'] is not None
                        and config_section['max_episodes'] != ''):
                    do_recording_maintenance = True
                    break
            if 'max_age_days' in config_section:
                if (config_section['max_age_days'] is not None
                        and config_section['max_age_days'] != ''):
                    do_recording_maintenance = True
                    break
    return(do_recording_maintenance)

# End is_recording_maintenance_configured


def maintain_recordings(devices, settings):

    try:
        all_series = get_all_series_with_episodes(devices, settings)
        logger.debug('Running recording maintenance cycle')
        for series_id, series in all_series.items():
            if series.is_protected:
                continue

            recordings = sort_recordings_for_deletion(series.recorded_episodes,
                                                      settings
                                                      )
            remaining_recordings = delete_aged_recordings(recordings,
                                                          series.max_age_days
                                                          )
            recordings = remaining_recordings
            remaining_recordings = delete_excess_recordings(recordings,
                                                            series.max_episodes
                                                            )
            recordings = remaining_recordings
    except ConnectionError as e:
        logger.warning(f'Device is not responding: {e}')
        return()

# End maintain_recordings


def is_conf_file_updated(conf_file_path, settings):

    conf_file_is_updated = False

    try:
        new_mtime = os.path.getmtime(conf_file_path)
        if new_mtime > settings['timestamp']:
            if settings['timestamp'] != 0:
                logger.debug(f'{conf_file_path} has been updated')
            conf_file_is_updated = True
    except FileNotFoundError:
        # If the file gets removed after start-up, it's OK
        pass

    return(conf_file_is_updated)

# End is_conf_file_updated


def main():

    global logger
    global dry_run

    conf_file_path = None
    conf_file_check_due_time = INFINITE_FUTURE
    devices = {}
    device_discovery_due_time = time.time()
    recording_maintenance_due_time = INFINITE_FUTURE
    settings = {'timestamp': 0}
    refresh_settings = True

    try:
        args = parse_args(sys.argv[1:])

        if args.version:
            print(f'{__about__.__name__} {__about__.__version__}')
            sys.exit()

        configure_loggers(args.quiet, args.verbose)

        dry_run = args.dry_run
        if dry_run:
            logger.warning('This is a dry-run. No recordings will be deleted, '
                           'even if log messages indicate otherwise.'
                           )
        if args.conf_file is not None:
            conf_file_path = args.conf_file.name
            conf_file_check_due_time = time.time()

        while True:

            # Discover devices
            if device_discovery_due_time <= time.time():
                devices = get_monitored_devices(args.device_id_list, devices)
                for device_key, device in devices.items():
                    update_device_settings(device, settings)
                device_discovery_due_time += DEVICE_DISCOVERY_INTERVAL

            # Monitor config file for changes
            if conf_file_check_due_time <= time.time():
                refresh_settings = is_conf_file_updated(conf_file_path,
                                                        settings
                                                        )
                conf_file_check_due_time += CONFIG_FILE_CHECK_INTERVAL

            if refresh_settings:
                refresh_settings = False
                settings = Settings(args, conf_file_path)
                settings['timestamp'] = time.time()

                for device_key, device in devices.items():
                    update_device_settings(device, settings)

                if is_recording_maintenance_configured(settings):
                    if recording_maintenance_due_time >= INFINITE_FUTURE:
                        recording_maintenance_due_time = time.time()
                    # else continue on existing cadence
                else:
                    if recording_maintenance_due_time < INFINITE_FUTURE:
                        logger.debug('Discontinuing recording maintenance')
                    recording_maintenance_due_time = INFINITE_FUTURE

            # List recordings/series (one and done)
            if args.list_recordings or args.list_series:
                if args.list_recordings:
                    print_recording_list(devices, settings)
                if args.list_series:
                    print_series_list(devices, settings)
                break

            # Report device space utilization
            for device_key, device in devices.items():
                # This "due time" is handled differently than the others so it
                # can be reactive to report interval configuration changes
                if ((device.prior_space_report_time
                        + device.space_report_interval) > time.time()):
                    continue
                device.prior_space_report_time = math.floor(time.time())
                report_device_space(device)

            # Maintain device free space
            for device_key, device in devices.items():
                if device.maintenance_due_time > time.time():
                    continue
                maintain_device(device, settings)
                maintenance_interval = calc_maintenance_interval(device)
                device.maintenance_due_time += maintenance_interval
                logger.debug(f'{device.tag} Next free space maintenance cycle '
                             f'in {duration(maintenance_interval)}'
                             )

            # Maintain recordings
            if recording_maintenance_due_time <= time.time():
                maintain_recordings(devices, settings)
                recording_maintenance_due_time += RECORDING_MAINT_INTERVAL
                logger.debug(f'Next recording maintenance cycle in '
                             f'{duration(RECORDING_MAINT_INTERVAL)}'
                             )

            # Quit if just testing
            if args.test_mode:
                break

            time.sleep(0.1)

    except ValueError as value_err:
        logger.error(value_err)
        sys.exit(2)
    except KeyboardInterrupt:
        print()
        sys.exit()
    except BrokenPipeError:
        sys.exit()
    except OSError as e:
        logger.error(f'Unexpected error. Will restart in {RESTART_DELAY} '
                     f'seconds: {e}'
                     )
        time.sleep(RESTART_DELAY)
        os.execl(sys.executable, sys.executable, *sys.argv)

# End main()


if __name__ == '__main__':
    main()

# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai :
