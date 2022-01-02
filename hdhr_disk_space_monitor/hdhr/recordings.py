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

import requests

# When a recording has been watched all the way to the end, the Resume
# value is set to this constant.
MAX_RESUME_OFFSET = 0xFFFFFFFF


class RecordedSeries:
    _type_name = 'RecordedSeries'
    _json_attr_str_map = {'SeriesID': '_series_id',
                          'Title': '_title',
                          'Category': '_category',
                          'ImageURL': '_image_url',
                          'EpisodesURL': '_episodes_url'
                          }

    # SeriesID	"C184249ENDJE6"
    # Title	"America's Funniest Home Videos"
    # Category	"series"
    # ImageURL	"http://img.hdhomerun.com/titles/C184249ENDJE6.jpg"
    # StartTime	1591570800
    # EpisodesURL       "http://192.168.1.104:80/recorded_files.json?SeriesI...
    # UpdateID	3033907720

    def __init__(self, json):
        self._recordings = []
        for key, attr in self._json_attr_str_map.items():
            if key in json:
                setattr(self, attr, json[key])

    def __repr__(self):
        return(f"<{self._type_name} id={getattr(self, '_series_id', '?')}"
               f":title={getattr(self, '_title', '?')}>"
               )

    @property
    def series_id(self):
        """Unique series ID"""
        return(getattr(self, '_series_id', ''))

    @property
    def title(self):
        """Series title"""
        return(getattr(self, '_title', ''))

    @property
    def category(self):
        """Series category"""
        return(getattr(self, '_category', ''))

    @property
    def image_url(self):
        """HTTP URL for the series image"""
        return(getattr(self, '_image_url', ''))

    def recorded_episodes(self):
        """List of recorded episodes for the series"""
        self._recordings = []
        response = requests.get(self._episodes_url)
        response.raise_for_status()
        for recording_json in response.json():
            recording_obj = Recording(recording_json)
            self._recordings.append(recording_obj)
        return(self._recordings)


class Recording:
    _type_name = 'Recording'
    _json_attr_str_map = {'Category': '_category',
                          'ChannelName': '_channel_name',
                          'ChannelNumber': '_channel_number',
                          'ImageURL': '_image_url',
                          'ProgramID': '_program_id',
                          'SeriesID': '_series_id',
                          'Synopsis': '_synopsis',
                          'Title': '_series_title',
                          'Filename': '_filename',
                          'PlayURL': '_play_url',
                          'CmdURL': '_command_url',
                          'ChannelAffiliate': '_channel_affiliate',
                          'ChannelImageURL': '_channel_image_url',
                          'EpisodeTitle': '_episode_title',
                          'EpisodeNumber': '_episode_number'
                          }
    _json_attr_int_map = {'OriginalAirdate': '_original_airdate',
                          'RecordEndTime': '_record_end_time',
                          'RecordStartTime': '_record_start_time',
                          'Resume': '_resume_offset',
                          'StartTime': '_start_time',
                          'EndTime': '_end_time',
                          }
    _json_attr_bool_map = {'FirstAiring': '_first_airing',
                           'RecordSuccess': '_record_success'
                           }

    # Category	"series"
    # ChannelAffiliate	"ABC"
    # ChannelImageURL	"http://img.hdhomerun.com/channels/US19626.png"
    # ChannelName	"WFAADT"
    # ChannelNumber	"8.1"
    # EndTime	1591574400
    # EpisodeNumber	"S30E21"
    # FirstAiring	1
    # ImageURL	"http://img.hdhomerun.com/titles/C184249ENDJE6.jpg"
    # OriginalAirdate	1591488000
    # ProgramID	"EP000168930995"
    # RecordEndTime	1591574430
    # RecordStartTime	1591570772
    # Resume	1610
    # SeriesID	"C184249ENDJE6"
    # StartTime	1591570800
    # Synopsis	"Nine finalists compete for the $100,000 prize; basketball b...
    # Title	"America's Funniest Home Videos"
    # Filename	"America's Funniest Home Videos S30E21 20200607 [20200607-23...
    # PlayURL	"http://192.168.1.104:80/recorded/play?id=a156f919"
    # CmdURL	"http://192.168.1.104:80/recorded/cmd?id=a156f919"

    def __init__(self, json):
        for key, attr in self._json_attr_str_map.items():
            if key in json:
                setattr(self, attr, json[key])
        for key, attr in self._json_attr_int_map.items():
            if key in json:
                setattr(self, attr, int(json[key]))
        for key, attr in self._json_attr_bool_map.items():
            if key in json:
                setattr(self, attr, True)
            else:
                setattr(self, attr, False)

    def __repr__(self):
        return(f"<{self._type_name} "
               f"filename={getattr(self, '_filename', '?')}>"
               )

    def __eq__(self, other):
        if not isinstance(other, Recording):
            return(False)
        return(self._filename == other._filename)

    def __ne__(self, other):
        return(not self.__eq__(other))

    @property
    def category(self):
        """Category of the recording"""
        return(getattr(self, '_category', ''))

    @property
    def channel_affiliate(self):
        """Channel affiliate (e.g., ABC)"""
        return(getattr(self, '_channel_affiliate', ''))

    @property
    def channel_image_url(self):
        """HTTP URL for the channel image"""
        return(getattr(self, '_channel_image_url', ''))

    @property
    def channel_name(self):
        """Channel name/call-sign (e.g., WFAADT)"""
        return(getattr(self, '_channel_name', ''))

    @property
    def channel_number(self):
        """Channel number"""
        return(getattr(self, '_channel_number', ''))

    @property
    def end_time(self):
        """Scheduled end time of the program"""
        return(getattr(self, '_end_time', None))

    @property
    def episode_number(self):
        """Episode number (e.g., S30E21)"""
        return(getattr(self, '_episode_number', ''))

    @property
    def episode_title(self):
        """Episode title"""
        return(getattr(self, '_episode_title', ''))

    @property
    def first_airing(self):
        """Indicator for whether this is the first airing"""
        return(getattr(self, '_first_airing', None))

    @property
    def image_url(self):
        """HTTP URL for the recording image"""
        return(getattr(self, '_image_url', ''))

    @property
    def original_airdate(self):
        """Original airdate of this episode"""
        return(getattr(self, '_original_airdate', None))

    @property
    def program_id(self):
        """Unique ID for this episode"""
        return(getattr(self, '_program_id', ''))

    @property
    def record_end_time(self):
        """End time of the recording"""
        return(getattr(self, '_record_end_time', None))

    @property
    def record_start_time(self):
        """Start time of the recording"""
        return(getattr(self, '_record_start_time', None))

    @property
    def record_success(self):
        """Indicator if whether the recording was successful or not"""
        return(getattr(self, '_resume_offset', None))

    @property
    def resume_offset(self):
        """Number of seconds from the beginning to resume playing"""
        return(getattr(self, '_resume_offset', 0))

    @property
    def series_id(self):
        """Unique series ID"""
        return(getattr(self, '_series_id', ''))

    @property
    def start_time(self):
        """Scheduled start time of the program"""
        return(getattr(self, '_start_time', None))

    @property
    def synopsis(self):
        """Synopsis of the episode"""
        return(getattr(self, '_synopsis', ''))

    @property
    def series_title(self):
        """Series title"""
        return(getattr(self, '_series_title', ''))

    @property
    def filename(self):
        """File name of the recording"""
        return(getattr(self, '_filename', ''))

    @property
    def play_url(self):
        """HTTP URL to initiate playback"""
        return(getattr(self, '_play_url', ''))

    def delete(self, rerecord=False):
        url = f'{self._command_url}&cmd=delete'
        if rerecord:
            url += '&rerecord=1'
        requests.post(url)

    @property
    def file_size(self):
        """Size of file"""
        if getattr(self, '_file_size', -1) == -1:
            response = requests.head(self._play_url)
            response.raise_for_status()
            if 'Content-Length' in response.headers:
                self._file_size = int(response.headers['Content-Length'])
            else:
                self._file_size = 0

        return self._file_size


def main():

    from hdhr_disk_space_monitor.hdhr.devices import Devices

    devices = Devices()

    for d in devices.storage_servers:
        print(d)
        all_series = d.all_recorded_series()
        for s in all_series:
            print(s)
            print(s.__dict__)
            print(f'category = {s.category}')
            print(f'image_url = {s.image_url}')
            print(f'series_id = {s.series_id}')
            print(f'title = {s.title}')
            print()
            recordings = s.recorded_episodes()
            for r in recordings:
                print(r)
                print(r.__dict__)
                print(f'category = {r.category}')
                print(f'channel_affiliate = {r.channel_affiliate}')
                print(f'channel_image_url = {r.channel_image_url}')
                print(f'channel_name = {r.channel_name}')
                print(f'channel_number = {r.channel_number}')
                print(f'end_time = {r.end_time}')
                print(f'episode_number = {r.episode_number}')
                print(f'episode_title = {r.episode_title}')
                print(f'filename = {r.filename}')
                print(f'first_airing = {r.first_airing}')
                print(f'image_url = {r.image_url}')
                print(f'original_airdate = {r.original_airdate}')
                print(f'play_url = {r.play_url}')
                print(f'program_id = {r.program_id}')
                print(f'record_end_time = {r.record_end_time}')
                print(f'record_start_time = {r.record_start_time}')
                print(f'record_success = {r.record_success}')
                print(f'resume_offset = {r.resume_offset}')
                print(f'series_id = {r.series_id}')
                print(f'series_title = {r.series_title}')
                print(f'start_time = {r.start_time}')
                print(f'synopsis = {r.synopsis}')
                print()
            print()


if __name__ == '__main__':
    main()

# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai :
