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
INFINITE_FUTURE = 999999999999  # UNIX time seconds

DISCOVER_DEVICE_ID = 'discover'
WILDCARD_DEVICE_ID = 'FFFFFFFF'
DELETE_POLICIES = ['age', 'category']
DEFAULT_DEVICE_ID = DISCOVER_DEVICE_ID
DEFAULT_REPORT_INTERVAL = 10 * MINUTE_SECONDS
DEFAULT_COUNT = None
DEFAULT_GIGABYTES_FREE = None
DEFAULT_PERCENT_FREE = None
DEFAULT_DELETE_POLICY = DELETE_POLICIES[0]
DEFAULT_WATCHED_FIRST = False
DEFAULT_WATCHED_OFFSET = 3 * MINUTE_SECONDS
DEFAULT_MAX_EPISODES = None
DEFAULT_MAX_AGE_DAYS = None
DEFAULT_RERECORD_DELETED = True
DEFAULT_PROTECTED = False
DEFAULT_GLOBAL_SETTINGS = {'delete_policy': DEFAULT_DELETE_POLICY,
                           'watched_first': DEFAULT_WATCHED_FIRST,
                           }
DEFAULT_DEVICE_SETTINGS = {'interval': DEFAULT_REPORT_INTERVAL,
                           'count': DEFAULT_COUNT,
                           'gigabytes_free': DEFAULT_GIGABYTES_FREE,
                           'percent_free': DEFAULT_PERCENT_FREE,
                           }
DEFAULT_CATEGORY_SETTINGS = {'protected': DEFAULT_PROTECTED,
                             'max_episodes': DEFAULT_MAX_EPISODES,
                             'watched_offset': DEFAULT_WATCHED_OFFSET,
                             'max_age_days': DEFAULT_MAX_AGE_DAYS,
                             'rerecord_deleted': DEFAULT_RERECORD_DELETED,
                             }
DEVICE_DISCOVERY_INTERVAL = 30
CONFIG_FILE_CHECK_INTERVAL = 3
MIN_SPACE_CHECK_INTERVAL = 3
RECORDING_MAINT_INTERVAL = 13 * MINUTE_SECONDS
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
