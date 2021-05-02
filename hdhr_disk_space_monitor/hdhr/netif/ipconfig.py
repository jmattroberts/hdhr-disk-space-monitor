# -----------------------------------------------------------------------------
# Copyright (c) 2020 J. Matt Roberts
# Copyright (c) 2015-2019 Silicondust, Inc.
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

import subprocess


def parse(data=None):
    data = data or subprocess.check_output('ipconfig /all',
                                           startupinfo=getStartupInfo()
                                           )
    dlist = [d.rstrip() for d in data.split('\n')]
    mode = None
    sections = []
    while dlist:
        d = dlist.pop(0)
        try:
            if not d:
                continue
            elif not d.startswith(' '):
                sections.append({'name': d.strip('.: ')})
            elif d.startswith(' '):
                if d.endswith(':'):
                    k = d.strip(':. ')
                    mode = 'VALUE:' + k
                    sections[-1][k] = ''
                elif ':' in d:
                    k, v = d.split(':', 1)
                    k = k.strip(':. ')
                    mode = 'VALUE:' + k
                    v = v.replace('(Preferred)', '')
                    sections[-1][k] = v.strip()
            elif mode and mode.startswith('VALUE:'):
                if not d.startswith('        '):
                    mode = None
                    dlist.insert(0, d)
                    continue
                k = mode.split(':', 1)[-1]
                v = d.replace('(Preferred)', '')
                sections[-1][k] += ',' + v.strip()
        except Exception:
            print(d)
            raise

    return sections[1:]


def getStartupInfo():
    if hasattr(subprocess, 'STARTUPINFO'):  # Windows
        startupinfo = subprocess.STARTUPINFO()
        try:
            # Suppress terminal window
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        except Exception:
            startupinfo.dwFlags |= 1
        return startupinfo

    return None
