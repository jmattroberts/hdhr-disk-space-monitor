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

import math
from hdhr_disk_space_monitor.const import DAY_SECONDS
from hdhr_disk_space_monitor.const import HOUR_SECONDS
from hdhr_disk_space_monitor.const import MINUTE_SECONDS
from hdhr_disk_space_monitor.const import BYTES_PER_TB
from hdhr_disk_space_monitor.const import BYTES_PER_GB
from hdhr_disk_space_monitor.const import BYTES_PER_MB
from hdhr_disk_space_monitor.const import BYTES_PER_KB


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
