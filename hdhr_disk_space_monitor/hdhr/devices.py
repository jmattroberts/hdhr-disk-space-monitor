#!/usr/bin/env python

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

from hdhr_disk_space_monitor.hdhr import crc32c
from hdhr_disk_space_monitor.hdhr import errors
from hdhr_disk_space_monitor.hdhr import netif
from hdhr_disk_space_monitor.hdhr.recordings import RecordedSeries
from io import BytesIO
from pathlib import Path
import base64
import re
import requests
import socket
import struct
import time
import traceback

HDHOMERUN_DISCOVER_UDP_PORT = 65001
HDHOMERUN_CONTROL_TCP_PORT = 65001

HDHOMERUN_TYPE_DISCOVER_REQ = 0x0002
HDHOMERUN_TYPE_DISCOVER_RPY = 0x0003

HDHOMERUN_TAG_DEVICE_TYPE = 0x01
HDHOMERUN_TAG_DEVICE_ID = 0x02
HDHOMERUN_TAG_ERROR_MESSAGE = 0x05
HDHOMERUN_TAG_TUNER_COUNT = 0x10
HDHOMERUN_TAG_LINEUP_URL = 0x27
HDHOMERUN_TAG_STORAGE_URL = 0x28
HDHOMERUN_TAG_DEVICE_AUTH_BIN_DEPRECATED = 0x29
HDHOMERUN_TAG_BASE_URL = 0x2A
HDHOMERUN_TAG_DEVICE_AUTH_STR = 0x2B
HDHOMERUN_TAG_STORAGE_ID = 0x2C

HDHOMERUN_DEVICE_TYPE_WILDCARD = 0xFFFFFFFF
HDHOMERUN_DEVICE_TYPE_TUNER = 0x00000001
HDHOMERUN_DEVICE_TYPE_STORAGE = 0x00000005
HDHOMERUN_DEVICE_ID_WILDCARD = 0xFFFFFFFF


class Devices():

    def __init__(self):
        self.rediscover()

    def rediscover(self):
        """Forgets all devices and runs discovery again"""
        self._storage_servers = []
        self._tuner_devices = []
        self._other = []
        self.discover()

    def discover(self):
        """Discovers devices and adds them to the list if they are new"""
        self._discovery_timestamp = time.time()
        ifaces = netif.getInterfaces()
        sockets = []
        for i in ifaces:
            if not i.broadcast:
                continue
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.01)  # 10ms
            s.bind((i.ip, 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sockets.append((s, i))
        device_type = HDHOMERUN_DEVICE_TYPE_WILDCARD
        device_id = HDHOMERUN_DEVICE_ID_WILDCARD
        payload = struct.pack('>B', HDHOMERUN_TAG_DEVICE_TYPE)
        payload += struct.pack('>B', 0x04)  # Type length
        payload += struct.pack('>I', device_type)
        payload += struct.pack('>B', HDHOMERUN_TAG_DEVICE_ID)
        payload += struct.pack('>B', 0x04)  # ID length
        payload += struct.pack('>I', device_id)

        header = struct.pack('>H', HDHOMERUN_TYPE_DISCOVER_REQ)
        header += struct.pack('>H', len(payload))

        data = header + payload
        crc = crc32c.cksum(data)
        packet = data + struct.pack('>I', crc)

        for attempt in (0, 1):
            for s, i in sockets:
                s.sendto(packet, (i.broadcast, HDHOMERUN_DISCOVER_UDP_PORT))

            end = time.time() + 0.25  # 250ms

            while time.time() < end:
                for s, i in sockets:
                    try:
                        message, address = s.recvfrom(8096)
                        self._add(message, address)

                    except socket.timeout:
                        pass
                    except Exception:
                        traceback.print_exc()

    def _add(self, packet, address):
        device = self._create_device(packet, address)

        if not device or not device._valid:
            return(None)
        elif device in self:
            return(False)

        if isinstance(device, TunerDevice):
            self._tuner_devices.append(device)
        elif isinstance(device, StorageServer):
            self._storage_servers.append(device)
        else:
            self._other.append(device)

        return(True)

    def _create_device(self, packet, address):
        try:
            header = packet[:4]
            data = packet[4:-4]
            chksum = packet[-4:]

            self.response_type, packet_length = struct.unpack('>HH', header)
            if not self.response_type == HDHOMERUN_TYPE_DISCOVER_RPY:
                return(None)

            if packet_length != len(data):
                return(None)

            if chksum != struct.pack('>I', crc32c.cksum(header + data)):
                return(None)
        except Exception:
            traceback.print_exc()
            return(None)

        data_io = BytesIO(data)

        tag, length = struct.unpack('>BB', data_io.read(2))
        device_type = struct.unpack('>I', data_io.read(length))[0]

        if device_type == HDHOMERUN_DEVICE_TYPE_TUNER:
            device = self._process_data(TunerDevice(address), data_io)
        elif device_type == HDHOMERUN_DEVICE_TYPE_STORAGE:
            device = self._process_data(StorageServer(address), data_io)
        else:
            device = self._process_data(Device(address), data_io)
        device.refresh()
        return(device)

    def _process_data(self, device, data_io):

        while True:
            header = data_io.read(2)
            if not header:
                return(device)
            tag, length = struct.unpack('>BB', header)
            if tag == HDHOMERUN_TAG_DEVICE_ID:
                device._id = int.from_bytes(struct.unpack(
                                              '>{0}s'.format(length),
                                              data_io.read(length)
                                              )[0],
                                            byteorder='big'
                                            )
            elif tag == HDHOMERUN_TAG_LINEUP_URL:
                device._lineup_url = struct.unpack('>{0}s'.format(length),
                                                   data_io.read(length)
                                                   )[0].decode()
            elif tag == HDHOMERUN_TAG_STORAGE_URL:
                device._storage_url = struct.unpack('>{0}s'.format(length),
                                                    data_io.read(length)
                                                    )[0].decode()
            elif tag == HDHOMERUN_TAG_DEVICE_AUTH_BIN_DEPRECATED:
                device._device_auth = struct.unpack('>{0}s'.format(length),
                                                    data_io.read(length)
                                                    )[0].decode()
            elif tag == HDHOMERUN_TAG_DEVICE_AUTH_STR:
                device._device_auth_string = struct.unpack(
                                               '>{0}s'.format(length),
                                               data_io.read(length)
                                               )[0].decode()
            elif tag == HDHOMERUN_TAG_BASE_URL:
                device._base_url = struct.unpack('>{0}s'.format(length),
                                                 data_io.read(length)
                                                 )[0].decode()
            elif tag == HDHOMERUN_TAG_STORAGE_ID:
                device._storage_id = struct.unpack('>{0}s'.format(length),
                                                   data_io.read(length)
                                                   )[0].decode()
            elif tag == HDHOMERUN_TAG_TUNER_COUNT:
                device._tuner_count = int.from_bytes(
                                        struct.unpack('>{0}s'.format(length),
                                                      data_io.read(length)
                                                      )[0],
                                        byteorder='big'
                                        )
            else:
                data_io.read(length)
        return(device)

    def __contains__(self, device):
        for d in self.all_devices:
            if d == device:
                return(True)
        return(False)

    @property
    def storage_servers(self):
        """Returns a list of all storage servers"""
        return(self._storage_servers)

    @property
    def tuner_devices(self):
        """Returns a list of all tuner devices"""
        return(self._tuner_devices)

    @property
    def all_devices(self):
        """Returns a list of all devices"""
        return(list(self.tuner_devices) + self.storage_servers + self._other)

    @property
    def default_tuner_device(self):
        """Returns the tuner device with the most channels"""
        highest = None
        for d in self._tuner_devices:
            if not highest or highest.channel_count < d.channel_count:
                highest = d
        return(highest)

    def has_tuner_devices(self):
        """Returns True if there are any tuner devices"""
        return(bool(self._tuner_devices))

    def has_storage_servers(self):
        """Returns True if there are any storage servers"""
        return(bool(self._storage_servers))

    def get_device_by_id(self, id):
        """Returns the device with the given IP address"""
        for d in self._tuner_devices + self._storage_servers:
            if d.id == id:
                return(d)
        return(None)

    def get_device_by_ip(self, ip_addr):
        """Returns the device with the given IP address"""
        for d in self._tuner_devices + self._storage_servers:
            if d.ip_addr == ip_addr:
                return(d)
        return(None)

    def get_storage_by_id(self, id):
        """Returns the device with the given IP address"""
        for d in self._storage_servers:
            if d.id == id:
                return(d)
        return(None)

    def get_storage_by_ip(self, ip_addr):
        """Returns the device with the given IP address"""
        for d in self._storage_servers:
            if d.ip_addr == ip_addr:
                return(d)
        return(None)

    def get_tuner_by_id(self, id):
        """Returns the device with the given IP address"""
        for d in self._tuner_devices:
            if d.id == id:
                return(d)
        return(None)

    def get_tuner_by_ip(self, ip_addr):
        """Returns the device with the given IP address"""
        for d in self._tuner_devices:
            if d.ip_addr == ip_addr:
                return(d)
        return(None)

    @property
    def api_authid(self):
        """Returns the AuthID for use with the hosted API"""
        combined = ''
        ids = []
        for d in self._tuner_devices:
            ids.append(d.id)
            authid = d.device_auth
            if not authid:
                continue
            combined += authid

        if not combined:
            raise errors.NoDeviceAuthException()

        # return(base64.standard_b64encode(combined))
        return(combined)


class Device():
    _type_name = 'Unknown'
    _discover_uri = 'discover.json'
    _status_uri = 'status.json'

    # Only pull elements from the JSON that aren't part of the initial
    # discovery, or that can change. LineupURL might not be needed here.
    # Not sure.
    _json_attr_str_map = {'FriendlyName': '_friendly_name',
                          'ModelNumber': '_model_number',
                          'FirmwareName': '_firmware_name',
                          'FirmwareVersion': '_firmware_version',
                          'DeviceAuth': '_device_auth_string',
                          'Version': '_version'
                          }
    _json_attr_int_map = {'TotalSpace': '_total_space',
                          'FreeSpace': '_free_space'
                          }

    def __init__(self, address):
        self._ip_addr, self._udp_port = address

    def __ne__(self, other):
        return(not self.__eq__(other))

    def __str__(self):
        return(self.__repr__())

    def __repr__(self):
        return(f"<{self._type_name} id={getattr(self, 'id', '?')}"
               f":url={getattr(self, '_base_url', '?')}>"
               )

    @property
    def id(self):
        """Device ID"""
        if getattr(self, '_id', None) is not None:
            return(hex(self._id)[2:])
        else:
            return('')

    @property
    def ip_addr(self):
        """Device IP address"""
        return(self._ip_addr)

    @property
    def http_port(self):
        return(self._base_url[self._base_url.rfind(':') + 1:])

    def _discover_url(self):
        """HTTP URL to get json-formatted data about the device"""
        return(getattr(self, '_base_url', '') + '/' + self._discover_uri)

    def _status_url(self):
        """HTTP URL to get json-formatted device status"""
        return(getattr(self, '_base_url', '') + '/' + self._status_uri)

    @property
    def _valid(self):
        """Returns True if the device is valid"""
        return(False)

    @property
    def friendly_name(self):
        """Friendly name (e.g., HDHomeRun SCRIBE QUATRO)"""
        return(getattr(self, '_friendly_name', ''))

    @property
    def model_number(self):
        """Model number (e.g., HDVR-4US-1TB)"""
        return(getattr(self, '_model_number', ''))

    @property
    def firmware_name(self):
        """Firmware name (e.g., hdhomerun_atsc)"""
        return(getattr(self, '_firmware_name', ''))

    @property
    def firmware_version(self):
        """Firmware version (e.g., 20200521)"""
        return(getattr(self, '_firmware_version', ''))

    def refresh(self):
        """Refresh device data that can get stale (e.g., free space)"""
        response = requests.get(self._discover_url())
        response.raise_for_status()
        json = response.json()
        for key, attr in self._json_attr_str_map.items():
            if hasattr(self, attr):
                delattr(self, attr)
            if key in json:
                setattr(self, attr, json[key])
        for key, attr in self._json_attr_int_map.items():
            if hasattr(self, attr):
                delattr(self, attr)
            if key in json:
                setattr(self, attr, int(json[key]))


class TunerDevice(Device):
    _type_name = 'TunerDevice'
    _lineupURI = 'lineup.json'

    def __init__(self, address):
        Device.__init__(self, address)

    def __eq__(self, other):
        if not isinstance(other, TunerDevice):
            return(False)
        return(self._id == other._id)

    @property
    def _valid(self):
        return(hasattr(self, '_id'))

    @property
    def tuner_count(self):
        """Number of tuners on this device"""
        return(getattr(self, '_tuner_count', 0))

    @property
    def device_auth(self):
        """API auth string for this device"""
        auth_string = getattr(self, '_device_auth_string', None)
        if auth_string:
            return(auth_string)

        auth_binary = getattr(self, '_device_auth', None)
        if auth_binary:
            return(base64.standard_b64encode(auth_binary))

        return(None)

    @property
    def channel_count(self):
        """Number of channels available on this device"""
        if not hasattr(self, '_channel_count'):
            req = requests.get(self._lineup_url)

            try:
                lineup = req.json()
                self._channel_count = len(lineup)
            except Exception:
                return(None)
        return(self._channel_count)

    # To do this according to the pattern used elsewhere, we need a Channel
    # and LineUp class which are not yet implemented.
    # @property
    # def lineup(self):
    #    """Channels available on this device"""


class StorageServer(Device):
    _type_name = 'StorageServer'
    _rule_sync_uri = 'recording_events.post?sync'
    _recordings_uri = 'recorded_files.json'
    _file_basename_pattern = re.compile(r'(?P<title>.*) [0-9]{8} '
                                        r'\[[0-9]{8}-[0-9]{4}\]'
                                        )

    def __init__(self, address):
        Device.__init__(self, address)

    def __eq__(self, other):
        if not isinstance(other, StorageServer):
            return(False)
        return(self._base_url == other._base_url)

    def __repr__(self):
        return(f"<{self._type_name} id={getattr(self, 'id', '?')}"
               f":url={getattr(self, '_base_url', '?')}"
               f":storage_id={getattr(self, '_storage_id', '?')}>"
               )

    @property
    def _valid(self):
        return(hasattr(self, '_storage_id'))

    @property
    def storage_id(self):
        """Device's unique storage ID"""
        return(getattr(self, '_storage_id', ''))

    @property
    def total_space(self):
        """Total size of storage in bytes"""
        return(getattr(self, '_total_space', None))

    @property
    def free_space(self):
        """Amount of free space in bytes"""
        return(getattr(self, '_free_space', None))

    @property
    def version(self):
        """Version of software. Only applicable to RECORD software."""
        return(getattr(self, '_version', ''))

    def all_recorded_series(self):
        """Returns a list of RecordedSeries objects"""
        self._all_series = []
        response = requests.get(self._storage_url)
        response = response.json()
        for series_json in response:
            if series_json['SeriesID'] not in (s.series_id for s
                                               in self._all_series
                                               ):
                series_obj = RecordedSeries(series_json)
                self._all_series.append(series_obj)
        return(self._all_series)

    def _get_active_recordings(self, activity):
        active_recordings = []
        all_series = self.all_recorded_series()

        response = requests.get(self._status_url())
        response.raise_for_status()
        resources = response.json()

        # Comparisons below first strip out all nonalphanumeric characters

        current_streams = [resource for resource in resources
                           if resource['Resource'] == activity
                           ]
        for stream in current_streams:
            match_found = False
            for series in all_series:
                if (re.match(re.sub('[^A-Za-z0-9]+', '', series.title),
                             re.sub('[^A-Za-z0-9]+', '', stream['Name'])
                             )):
                    recordings = series.recorded_episodes()
                    for recording in recordings:
                        if (re.sub('[^A-Za-z0-9]+', '', stream['Name']) ==
                            re.sub('[^A-Za-z0-9]+', '',
                                   Path(recording.filename).stem
                                   )):
                            match_found = True
                            active_recordings.append(recording)
                            break
                    if match_found:
                        break

        return(active_recordings)

    def playing_now(self):
        """Returns a list of recording objects that are playing now."""
        return(self._get_active_recordings('playback'))

    def recording_now(self):
        """Returns a list of recording objects that are recording now."""
        return(self._get_active_recordings('record'))

    def sync_rules(self):
        """Triggers a synchronization of recording rule events"""
        requests.post(self._base_url + '/' + self._rule_sync_uri)


def main():

    devices = Devices()

    for d in devices.tuner_devices:
        print(d)
        d.channel_count
        print(d.__dict__)
        print(f'channel_count = {d.channel_count}')
        print(f'device_auth = {d.device_auth}')
        print(f'firmware_name = {d.firmware_name}')
        print(f'firmware_version = {d.firmware_version}')
        print(f'friendly_name = {d.friendly_name}')
        print(f'id = {d.id}')
        print(f'ip_addr = {d.ip_addr}')
        print(f'model_number = {d.model_number}')
        print(f'tuner_count = {d.tuner_count}')
        print()

    for d in devices.storage_servers:
        print(d)
        print(d.__dict__)
        print(f'firmware_name = {d.firmware_name}')
        print(f'firmware_version = {d.firmware_version}')
        print(f'free_space = {d.free_space}')
        print(f'friendly_name = {d.friendly_name}')
        print(f'id = {d.id}')
        print(f'ip_addr = {d.ip_addr}')
        print(f'model_number = {d.model_number}')
        print(f'storage_id = {d.storage_id}')
        print(f'total_space = {d.total_space}')
        print(f'version = {d.version}')
        print(f'playing_now() = {d.playing_now()}')
        print(f'recording_now() = {d.recording_now()}')
        print(f'all_recorded_series() = {d.all_recorded_series()}')

        print()


if __name__ == '__main__':
    main()

# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai :
