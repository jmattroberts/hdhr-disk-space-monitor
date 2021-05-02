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
# import pprint
import re
import socket
import sys
import time

from configparser import DEFAULTSECT
from requests.exceptions import ConnectionError
from hdhr_disk_space_monitor import __about__
from hdhr_disk_space_monitor.const import ATSC_MAX_TUNER_Bps
from hdhr_disk_space_monitor.const import BYTES_PER_GB
from hdhr_disk_space_monitor.const import CATEGORY_LIST
from hdhr_disk_space_monitor.const import DAY_SECONDS
from hdhr_disk_space_monitor.const import DEFAULT_DELETE_POLICY
from hdhr_disk_space_monitor.const import DEFAULT_DEVICE_ID
from hdhr_disk_space_monitor.const import DEFAULT_REPORT_INTERVAL
from hdhr_disk_space_monitor.const import DEFAULT_WATCHED_OFFSET
from hdhr_disk_space_monitor.const import DELETE_POLICIES
from hdhr_disk_space_monitor.const import DEVICE_DISCOVERY_INTERVAL
from hdhr_disk_space_monitor.const import DISCOVER_DEVICE_ID
from hdhr_disk_space_monitor.const import INFINITE_FUTURE
from hdhr_disk_space_monitor.const import MAX_STREAMS
from hdhr_disk_space_monitor.const import MIN_SPACE_CHECK_INTERVAL
from hdhr_disk_space_monitor.const import RECORDING_MAINT_INTERVAL
from hdhr_disk_space_monitor.const import WILDCARD_DEVICE_ID
from hdhr_disk_space_monitor.settings import Settings
from hdhr_disk_space_monitor.settings import interval
from hdhr_disk_space_monitor.settings import count
from hdhr_disk_space_monitor.settings import delete_policy
from hdhr_disk_space_monitor.settings import gigabytes
from hdhr_disk_space_monitor.settings import percent
from hdhr_disk_space_monitor.settings import watched_offset
from hdhr_disk_space_monitor.util import binarysize, duration
from hdhr_disk_space_monitor.hdhr.devices import Devices
from hdhr_disk_space_monitor.hdhr.recordings import RecordedSeries
from hdhr_disk_space_monitor.hdhr.recordings import Recording
from hdhr_disk_space_monitor.hdhr.recordings import MAX_RESUME_OFFSET

args = None
dry_run = False
logger = None

friendly_name_pattern = re.compile(r'HDHomeRun (?P<family>.*)')
model_number_pattern = re.compile(r'(?P<family>[A-Z]{4})-(?P<version>.*)')
config_section_name_pattern = re.compile(r'(?P<type>[^:]+)((:(?P<id>.*))|$)')


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
      '-s', '--delete-policy', choices=DELETE_POLICIES,
      type=delete_policy,
      help='Delete policy / sort method. Determines how recordings are '
      'sorted when selecting one to delete when maintaining free disk '
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
      help='List recordings in the order that they would be deleted when '
      'maintaining free disk space, and then exit. Use in combination with '
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

    series_settings = settings[f'category:{series_category}'].copy()
    if settings[f'series:{series_id}']:
        series_settings.update(settings[f'series:{series_id}'])
    elif settings[f'series:{series_title}']:
        series_settings.update(settings[f'series:{series_title}'])

    return(series_settings)

# End resolve_series_settings


def get_monitored_devices(desired_device_id_list, devices):

    current_devices = devices
    discovered_devices = {}
    available_devices = Devices()
    storage_devices = available_devices.storage_servers

    if desired_device_id_list is None:
        device_id_list = [DEFAULT_DEVICE_ID]
    else:
        device_id_list = desired_device_id_list.copy()

    # We find and take care of 'discover' first, so we can save duplicate
    # detection for the explicitly-named devices later.
    if DISCOVER_DEVICE_ID.upper() in (id.upper() for id in device_id_list):
        for device in storage_devices:
            if device.id != '':
                device_id = device.id
            else:
                device_id = device.ip_addr
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
                logger.debug(f'Device {device_id} is the same as device '
                             f'{discovered_key}. Proceeding with only '
                             f'{discovered_key}.'
                             )
                break
        else:
            discovered_devices[device_id] = device

    devices = {}
    for device_key, device in current_devices.items():
        if device_key in discovered_devices:
            # Refigure this in case the device suddenly STARTS reporting disk
            # space (due to reconfig and restart between discoveries). If it
            # suddenly STOPS, we'll let the main loop report that.
            original_total_space = device.total_space
            device.refresh()
            if original_total_space is None and device.total_space is not None:
                if device.space_report_due_time == INFINITE_FUTURE:
                    device.space_report_due_time = time.time()
                if device.maintenance_due_time == INFINITE_FUTURE:
                    device.maintenance_due_time = time.time()
            devices[device_key] = device  # Keep what we already have
        else:
            logger.warning(f'{device.tag} Device is no longer responding and '
                           'will no longer be monitored'
                           )

    for device_key, device in discovered_devices.items():
        if device_key in current_devices:
            continue  # Keep what we already have from above
        else:
            # Add some custom attributes
            device.key = device_key
            device.tag = f'[{device.friendly_name} '

            if device.id != '':
                device.tag += f'{device.id}'
                if device_key != device.id:
                    device.tag += f' ({device_key})'
            else:
                device.tag += f'{device.ip_addr}:{device.http_port}'
                if device_key != device.ip_addr:
                    device.tag += f' ({device_key})'
            device.tag += ']'

            if device.model_number != '':
                m = model_number_pattern.match(device.model_number)
            else:
                m = friendly_name_pattern.match(device.friendly_name)
            model_family = m.group('family')

            max_device_streams = (MAX_STREAMS[model_family])
            device.max_recording_Bps = (ATSC_MAX_TUNER_Bps
                                        * max_device_streams
                                        )
            device.space_report_count = 0
            device.maintenance_count = 0
            device.space_report_due_time = time.time()
            device.maintenance_due_time = time.time()

            devices[device_key] = device

    return(devices)

# End get_monitored_devices


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
        series_settings = resolve_series_settings(recording, settings)
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

    playing_recordings = device.playing_now()
    recording_recordings = device.recording_now()

    last_series_id = ""
    for recording in recordings:
        recording.device = device
        if recording.series_id != last_series_id:
            series_settings = resolve_series_settings(recording, settings)
        recording.is_protected = series_settings['protected']
        recording.category_delete_order = series_settings['delete_order']
        set_watched_flag(recording, settings)
        set_playing_flag(recording, playing_recordings)
        set_recording_flag(recording, recording_recordings)
        last_series_id = recording.series_id

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
    for device_key, device in devices.items():

        device_series = device.all_recorded_series()

        for series in device_series:
            series_id = series.series_id
            device_recordings = series.recorded_episodes()
            for recording in device_recordings:
                recording.device = device
            if series_id not in all_series:
                # This series object will only have episodes from one
                # device. The 'episodes' element will have episodes
                # from all devices.
                all_series[series_id] = {}
                all_series[series_id]['series'] = series
                all_series[series_id]['recorded_episodes'] = device_recordings
            else:
                for recording in device_recordings:
                    # Make sure we filter duplicates in case duplicate
                    # detection at the device level fails for some reason.
                    if (recording not in
                            all_series[series_id]['recorded_episodes']):
                        all_series[series_id]['recorded_episodes'].append(
                          recording
                          )
        # end series loop
    # end device loop

    return(all_series)

# End get_all_series_with_episodes


def print_recording_list(devices, settings):

    for device_key in devices.keys():
        device = devices[device_key]
        print_device_header(device)

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


def print_series_list(devices, settings):

    for device_key in devices.keys():
        device = devices[device_key]
        print_device_header(device)
        device_total_size = 0
        device_watched_size = 0
        device_episode_count = 0
        device_watched_count = 0

        recorded_series = device.all_recorded_series()

        for series in recorded_series:
            series.total_size = 0
            series.watched_size = 0
            series.episode_count = 0
            series.watched_count = 0

            for recording in series.recorded_episodes():
                series.total_size += recording.file_size
                series.episode_count += 1
                set_watched_flag(recording, settings)
                if recording.is_watched:
                    series.watched_size += recording.file_size
                    series.watched_count += 1
            device_total_size += series.total_size
            device_watched_size += series.watched_size
            device_episode_count += series.episode_count
            device_watched_count += series.watched_count

        sorted_series = sorted(recorded_series,
                               key=lambda r: (getattr(r, 'total_size'))
                               )

        for series in sorted_series:
            msg = (f"{series.title}: "
                   f"Total {binarysize(series.total_size)} "
                   f"({series.episode_count} "
                   )
            msg += ('episode)' if series.episode_count == 1 else 'episodes)')
            if series.watched_size > 0:
                msg += (f", Watched {binarysize(series.watched_size)} "
                        f"({series.watched_count} "
                        )
                msg += ('episode)' if series.watched_count == 1
                        else 'episodes)'
                        )
            series_settings = resolve_series_settings(series, settings)
            if series_settings['protected']:
                msg += ' (protected)'
            print(msg)
            msg = (f"{series.title}: "
                   f"Total {binarysize(series.total_size)} "
                   f"({series.episode_count} "
                   )
            msg += ('episode)' if series.episode_count == 1 else 'episodes)')
            if series.watched_size > 0:
                msg += (f", Watched {binarysize(series.watched_size)} "
                        f"({series.watched_count} "
                        )
                msg += ('episode)' if series.watched_count == 1
                        else 'episodes)'
                        )

        msg = (f"{device.tag} Total {binarysize(device_total_size)} "
               f"({device_episode_count} "
               )
        msg += ('episode)' if device_episode_count == 1 else 'episodes)')
        if device_watched_size > 0:
            msg += (f", Watched {binarysize(device_watched_size)} "
                    f"({device_watched_count} "
                    )
            msg += ('episode)' if device_watched_count == 1 else 'episodes)')
        print(msg)

# End print_series_list


def print_device_header(device):

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

# End print_device_header


def print_device_space_report(device, settings):

    used_space = device.total_space - device.free_space
    if device.free_space == 0:
        free_pct = 0.0
        used_pct = 100.0
    else:
        free_pct = (device.free_space / device.total_space) * 100
        used_pct = (used_space / device.total_space) * 100

    msg = (f'{device.tag} Total: {binarysize(device.total_space)}; '
           f'Used: {binarysize(used_space)} ({used_pct:.1f}%); '
           f'Free: {binarysize(device.free_space)} ({free_pct:.1f}%)'
           )
    if (device.min_free_space > 0 and
            device.min_free_space < device.total_space):
        min_free_pct = (device.min_free_space / device.total_space) * 100
        msg += (f'; Minimum Free: {binarysize(device.min_free_space)} '
                f'({min_free_pct:.1f}%)'
                )
    logger.info(msg)

# End print_device_space_report


def delete_recording(recording, settings, reason=''):

    series_settings = resolve_series_settings(recording, settings)

    logger.info(f'{recording.device.tag} '
                f'Deleting "{recording.series_title}" recorded '
                f'{time.ctime(recording.start_time)} {reason}')

    if series_settings['protected']:
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

    recording.delete(series_settings['rerecord_deleted'])

# End delete_recording


def delete_aged_recordings(recordings, settings):

    # Assumption: all recordings passed in are of the same series
    series_settings = resolve_series_settings(recordings[0], settings)
    max_age_days = series_settings['max_age_days']
    min_end_time = (time.time() - (max_age_days * DAY_SECONDS))

    pruned_recordings = recordings.copy()
    for recording in recordings:
        if recording.end_time < min_end_time:
            try:
                delete_recording(recording, settings,
                                 reason=(
                                   "because it's older than "
                                   f'{duration(max_age_days*DAY_SECONDS)}'
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
            # this function is not called if the series is protected.
            # No need to catch DeleteRecordingRecordingError since
            # min value for max_age_days is '1', and we have to be
            # past the end time of the recording for its age to be
            # positive.
    # End for

    return(pruned_recordings)

# End delete_aged_recordings


def delete_excess_recordings(recordings, settings):

    max_episodes = 99999

    watched_first = settings['global']['watched_first']
    # Assumption: all recordings passed in are of the same series
    series_settings = resolve_series_settings(recordings[0], settings)
    max_episodes = series_settings['max_episodes']

    if len(recordings) <= max_episodes:
        return(recordings)

    for recording in recordings:
        set_watched_flag(recording, settings)
    sorted_recordings = sort_recordings_by_age(recordings, watched_first)
    pruned_recordings = recordings.copy()

    for recording in sorted_recordings:
        if len(pruned_recordings) <= max_episodes:
            break
        try:
            delete_recording(recording, settings,
                             reason=('because there are '
                                     f'{len(pruned_recordings)} recorded '
                                     f'episodes (maximum is {max_episodes})'
                                     ))
            pruned_recordings.remove(recording)
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
        # this function is not called if the series is protected.

    return(pruned_recordings)

# End delete_excess_recordings


def delete_spacious_recording(device, settings):

    sorted_recordings = get_sorted_device_recordings(device, settings)
    # Because sorting is done on "is_protected" first, if the
    # first recording is protected, then all remaining recordings
    # are protected.
    while sorted_recordings and not sorted_recordings[0].is_protected:
        recording = sorted_recordings.pop(0)
        try:
            delete_recording(recording, settings, reason='to free space')
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


def report_device_space(device, settings):

    device.space_report_count += 1

    device_settings = settings[f'device:{device.key}']
    report_limit = device_settings['count']

    try:
        if report_limit is None or device.space_report_count <= report_limit:
            if device.space_report_count == 1:
                msg = (f'{device.tag} Disk space utilization will be reported '
                       f"every {duration(device_settings['interval'])}"
                       )
                if report_limit is not None:
                    msg += f", stopping after {report_limit} "
                    msg += 'report' if report_limit == 1 else 'reports'
                logger.debug(msg)
            device.refresh()
            print_device_space_report(device, settings)
    except ConnectionError as e:
        logger.error(f'{device.tag} Device is not responding: {e}')
        return()

# End report_device_space


def set_min_free_space(devices, settings):

    for device_key, device in devices.items():
        if device.total_space is None:
            continue
        min_free_space = 0
        device_settings = settings[f'device:{device.key}']
        if device_settings['percent_free'] is not None:
            min_free_space = (device.total_space
                              * (device_settings['percent_free'] / 100)
                              )
        elif device_settings['gigabytes_free'] is not None:
            min_free_space = (device_settings['gigabytes_free']
                              * BYTES_PER_GB
                              )
        device.min_free_space = min_free_space

# End set_min_free_space


def maintain_device(device, settings):

    device.maintenance_count += 1

    device_settings = settings[f'device:{device.key}']
    if device.min_free_space == 0:
        return()

    if device.maintenance_count == 1:
        if device_settings['percent_free'] is not None:
            threshold_str = f"{device_settings['percent_free']:.1f}%"
        elif device_settings['gigabytes_free'] is not None:
            threshold_str = binarysize(device.min_free_space)

        msg = (f'{device.tag} Recordings will be deleted according to '
               f"{settings['global']['delete_policy']} to maintain "
               f'minimum free space of {threshold_str}.'
               )
        if settings['global']['watched_first']:
            msg += ' Watched recordings will be deleted first.'
        logger.debug(msg)

    try:
        device.refresh()
        logger.debug(f'{device.tag} Running maintenance cycle - '
                     'checking free space'
                     )
        if device.free_space < device.min_free_space:
            print_device_space_report(device, settings)
            delete_spacious_recording(device, settings)
    except ConnectionError as e:
        logger.error(f'{device.tag} Device is not responding: {e}')
        return()

# End maintain_device


def calc_maintenance_interval(device, settings):

    try:
        device.refresh()
        bytes_to_threshold = device.free_space - device.min_free_space
        interval = math.floor(bytes_to_threshold / device.max_recording_Bps)
        if interval < MIN_SPACE_CHECK_INTERVAL:
            interval = MIN_SPACE_CHECK_INTERVAL
        return(interval)
    except ConnectionError as e:
        logger.error(f'{device.tag} Device is not responding: {e}')
        return(MIN_SPACE_CHECK_INTERVAL)

# End calc_maintenance_interval


def maintain_recordings(devices, settings):

    # Do we need to run maintenance?
    # Have to examine config file contents and not resolved settings because
    # category- and series-level settings have not been resolved yet.
    for section_name, config_section in settings.getConfig().items():
        m = config_section_name_pattern.match(section_name)
        section_type = m.group('type')
        if section_type in [DEFAULTSECT, 'category', 'series']:
            if 'max_episodes' in config_section:
                if (config_section['max_episodes'] is not None
                        and config_section['max_episodes'] != ''):
                    break
            if 'max_age_days' in config_section:
                if (config_section['max_age_days'] is not None
                        and config_section['max_age_days'] != ''):
                    break
    else:
        return

    try:
        all_series = get_all_series_with_episodes(devices, settings)
        for series_id in all_series.keys():
            series = all_series[series_id]['series']
            series_settings = resolve_series_settings(series, settings)
            if series_settings['protected']:
                continue

            recordings = all_series[series_id]['recorded_episodes']
            if (series_settings['max_age_days'] is not None and
                    len(recordings) > 0):
                remaining_recordings = delete_aged_recordings(
                                         recordings, settings
                                         )
                recordings = remaining_recordings
            if (series_settings['max_episodes'] is not None and
                    len(recordings) > 0):
                remaining_recordings = delete_excess_recordings(
                                         recordings, settings
                                         )
                recordings = remaining_recordings
    except ConnectionError as e:
        logger.error(f'Device is not responding: {e}')
        return()

# End maintain_recordings


def main():

    global logger
    global dry_run
    global args
    conf_file_path = None
    devices = {}
    device_discovery_due_time = time.time()
    recording_maintenance_due_time = time.time()

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
            conf_file_mtime = os.path.getmtime(conf_file_path)
        settings = Settings(args, conf_file_path)

        while True:

            # Discover devices
            if device_discovery_due_time <= time.time():
                devices = get_monitored_devices(args.device_id_list, devices)
                set_min_free_space(devices, settings)
                device_discovery_due_time += DEVICE_DISCOVERY_INTERVAL

            # List recordings/series (one and done)
            if args.list_recordings or args.list_series:
                if args.list_recordings:
                    print_recording_list(devices, settings)
                if args.list_series:
                    print_series_list(devices, settings)
                break

            # Report device space utilization
            for device_key, device in devices.items():
                if device.space_report_due_time <= time.time():
                    device.refresh()
                    if device.total_space is None:
                        logger.warning(f'{device.tag} Device does not report '
                                       'disk space utilization figures, so '
                                       'space utilization reports cannot be '
                                       'printed'
                                       )
                        device.space_report_due_time = INFINITE_FUTURE
                        continue
                    report_device_space(device, settings)
                    device_settings = settings[f'device:{device_key}']
                    device.space_report_due_time += device_settings['interval']

            # Maintain device free space
            for device_key, device in devices.items():
                if device.maintenance_due_time <= time.time():
                    device.refresh()
                    if device.total_space is None:
                        logger.warning(f'{device.tag} Device does not report '
                                       'disk space utilization figures, so '
                                       'recordings will not be deleted to '
                                       'maintain free space'
                                       )
                        device.maintenance_due_time = INFINITE_FUTURE
                        continue
                    if device.min_free_space > device.total_space:
                        logger.error(f'{device.tag} Minimum free space '
                                     f'({binarysize(device.min_free_space)}) '
                                     'cannot be greater than device total '
                                     'space '
                                     f'({binarysize(device.total_space)})'
                                     )
                        device.maintenance_due_time = INFINITE_FUTURE
                        continue
                    if device.min_free_space == 0:
                        continue
                    maintain_device(device, settings)
                    maintenance_interval = calc_maintenance_interval(
                                             device, settings
                                             )
                    device.maintenance_due_time += maintenance_interval
                    logger.debug(f'{device.tag} Next maintenance cycle in '
                                 f'{duration(maintenance_interval)}'
                                 )

            # Maintain recordings
            if recording_maintenance_due_time <= time.time():
                maintain_recordings(devices, settings)
                recording_maintenance_due_time += RECORDING_MAINT_INTERVAL

            # Quit if just testing
            if args.test_mode:
                break

            # Monitor config file for changes
            if conf_file_path is not None:
                try:
                    new_mtime = os.path.getmtime(conf_file_path)
                    if new_mtime > conf_file_mtime:
                        logger.debug('Configuration file has been '
                                     'updated. Reading new settings.'
                                     )
                        settings = Settings(args, conf_file_path)
                        set_min_free_space(devices, settings)
                        conf_file_mtime = new_mtime
                except FileNotFoundError:
                    # If the file gets removed after start-up, it's OK
                    pass

            time.sleep(0.1)

    except ValueError as value_err:
        logger.error(value_err)
        sys.exit(2)
    except KeyboardInterrupt:
        print()
        sys.exit()
    except BrokenPipeError:
        sys.exit()

# End main()


if __name__ == '__main__':
    main()

# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai :
