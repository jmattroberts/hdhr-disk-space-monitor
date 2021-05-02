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

import collections.abc
import configparser
import re

from hdhr_disk_space_monitor import const

config_section_name_pattern = re.compile(r'(?P<type>[^:]+)((:(?P<id>.*))|$)')


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

    def copy(self):
        return self._d.copy()

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
    if string not in const.DELETE_POLICIES:
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
    if (value < 0):
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

# End duration


class Settings(collections.UserDict):
    _config = None

    def __init__(self, args, conf_file_path=None):
        super().__init__(self)
        self._args = args
        if conf_file_path is not None:
            self._config = configparser.ConfigParser(
                             dict_type=CaseInsensitiveDict
                             )
            try:
                self._config.read(conf_file_path)
                for section_name, config_section in self._config.items():
                    if 'delete_policy' in config_section:
                        validate_delete_policy(self._config.get(
                                                 section_name, 'delete_policy'
                                                 ))
                    if 'watched_first' in config_section:
                        self._config.getboolean(section_name, 'watched_first')
                    if 'interval' in config_section:
                        validate_interval(self._config.get(section_name,
                                                           'interval'
                                                           ))
                    if 'count' in config_section:
                        validate_count(self._config.get(section_name, 'count'))
                    if 'gigabytes_free' in config_section:
                        validate_gigabytes(self._config.get(section_name,
                                                            'gigabytes_free'
                                                            ))
                    if 'percent_free' in config_section:
                        validate_percent(self._config.get(section_name,
                                                          'percent_free'
                                                          ))
                    if 'protected' in config_section:
                        self._config.getboolean(section_name, 'protected')
                    if 'max_episodes' in config_section:
                        validate_max_episodes(self._config.get(section_name,
                                                               'max_episodes'
                                                               ))
                    if 'watched_offset' in config_section:
                        validate_watched_offset(self._config.get(
                                                  section_name,
                                                  'watched_offset'
                                                  ))
                    if 'max_age_days' in config_section:
                        validate_max_age_days(self._config.get(section_name,
                                                               'max_age_days'
                                                               ))
                    if 'rerecord_deleted' in config_section:
                        self._config.getboolean(section_name,
                                                'rerecord_deleted'
                                                )
                    if 'delete_order' in config_section:
                        validate_delete_order(self._config.get(section_name,
                                                               'delete_order'
                                                               ))
            except ValueError as e:
                raise ValueError('Configuration file section '
                                 f'"{section_name}": {str(e)}'
                                 )

    # End __init__

    def getConfig(self):
        if self._config is None:
            return {}
        else:
            return(self._config)

    def __getitem__(self, key):
        if key not in self.data:
            m = config_section_name_pattern.match(key)
            section_type = m.group('type')
            section_id = m.group('id')
            if section_type == 'global':
                self._resolve_global_settings()
            elif section_type == 'device':
                self._resolve_device_settings(section_id)
            elif section_type == 'category':
                self._resolve_category_settings(section_id)
            elif section_type == 'series':
                self._resolve_series_settings(section_id)

        return self.data[key]

    def _parse_global_conf(self, global_settings):

        section = configparser.DEFAULTSECT

        global_settings['delete_policy'] = validate_delete_policy(
                                self._config.get(
                                  section, 'delete_policy',
                                  fallback=global_settings['delete_policy']
                                      ))
        global_settings['watched_first'] = self._config.getboolean(
                                  section, 'watched_first',
                                  fallback=global_settings['watched_first']
                                      )

    # End parse_global_conf

    def _parse_device_conf(self, device_key, device_settings):

        # Parsing through a name section of the config file will take the
        # DEFAULT section into account automatically. If the device section is
        # not in the file, the DEFAULT section has to be parsed explicitly.
        if self._config.has_section(f'device:{device_key}'):
            section = f'device:{device_key}'
        elif self._config.has_section(device_key):
            section = device_key
        else:
            section = configparser.DEFAULTSECT

        device_settings['interval'] = validate_interval(
                                   self._config.get(
                                     section, 'interval',
                                     fallback=device_settings['interval']
                                     ))
        device_settings['count'] = validate_count(
                                   self._config.get(
                                     section, 'count',
                                     fallback=device_settings['count']
                                     ))
        device_settings['gigabytes_free'] = validate_gigabytes(
                                   self._config.get(
                                     section, 'gigabytes_free',
                                     fallback=device_settings['gigabytes_free']
                                     ))
        device_settings['percent_free'] = validate_percent(
                                   self._config.get(
                                     section, 'percent_free',
                                     fallback=device_settings['percent_free']
                                     ))

    # End parse_device_conf

    def _parse_category_conf(self, category_name, category_settings):

        # Parsing through a name section of the config file will take the
        # DEFAULT section into account automatically. If the device section is
        # not in the file, the DEFAULT section has to be parsed explicitly.
        if self._config.has_section(f'category:{category_name}'):
            section = f'category:{category_name}'
        else:
            section = configparser.DEFAULTSECT

        category_settings['protected'] = self._config.getboolean(
                                 section, 'protected',
                                 fallback=category_settings['protected']
                                 )
        category_settings['max_episodes'] = validate_max_episodes(
                               self._config.get(
                                 section, 'max_episodes',
                                 fallback=category_settings['max_episodes']
                                 ))
        category_settings['watched_offset'] = validate_watched_offset(
                               self._config.get(
                                 section, 'watched_offset',
                                 fallback=category_settings['watched_offset']
                                 ))
        category_settings['max_age_days'] = validate_max_age_days(
                               self._config.get(
                                 section, 'max_age_days',
                                 fallback=category_settings['max_age_days']
                                 ))
        category_settings['rerecord_deleted'] = self._config.getboolean(
                                 section, 'rerecord_deleted',
                                 fallback=category_settings['rerecord_deleted']
                                 )
        category_settings['delete_order'] = validate_delete_order(
                               self._config.get(
                                 section, 'delete_order',
                                 fallback=category_settings['delete_order']
                                 ))

    # End parse_category_conf

    def _parse_series_conf(self, series_id, series_settings):

        # Parsing through a name section of the config file will take the
        # DEFAULT section into account automatically. If the device section is
        # not in the file, the DEFAULT section has to be parsed explicitly.
        if self._config.has_section(f'series:{series_id}'):
            section = f'series:{series_id}'
        else:
            section = configparser.DEFAULTSECT

        protected = self._config.getboolean(section, 'protected',
                                            fallback=None
                                            )
        if protected is not None:
            series_settings['protected'] = protected
        max_episodes = self._config.get(section, 'max_episodes', fallback=None)
        if max_episodes is not None:
            series_settings['max_episodes'] = validate_max_episodes(
                                                max_episodes
                                                )
        watched_offset = self._config.get(section, 'watched_offset',
                                          fallback=None
                                          )
        if watched_offset is not None:
            series_settings['watched_offset'] = validate_watched_offset(
                                                  watched_offset
                                                  )
        max_age_days = self._config.get(section, 'max_age_days', fallback=None)
        if max_age_days is not None:
            series_settings['max_age_days'] = validate_max_age_days(
                                                max_age_days
                                                )
        rerecord_deleted = self._config.getboolean(section, 'rerecord_deleted',
                                                   fallback=None
                                                   )
        if rerecord_deleted is not None:
            series_settings['rerecord_deleted'] = rerecord_deleted

    # End parse_series_conf

    def _resolve_global_settings(self):

        global_settings = const.DEFAULT_GLOBAL_SETTINGS.copy()
        if self._config is not None:
            self._parse_global_conf(global_settings)
        if self._args.delete_policy is not None:
            global_settings['delete_policy'] = self._args.delete_policy
        if self._args.watched_first is not None:
            global_settings['watched_first'] = self._args.watched_first

        self.data['global'] = global_settings

    # End _resolve_global_settings

    def _resolve_device_settings(self, device_key):

        device_settings = const.DEFAULT_DEVICE_SETTINGS.copy()
        if self._config is not None:
            self._parse_device_conf(device_key, device_settings)
        if self._args.interval is not None:
            device_settings['interval'] = self._args.interval
        if self._args.count is not None:
            device_settings['count'] = self._args.count
        if self._args.gigabytes_free is not None:
            device_settings['gigabytes_free'] = self._args.gigabytes_free
        if self._args.percent_free is not None:
            device_settings['percent_free'] = self._args.percent_free

        if (device_settings['gigabytes_free'] is not None
                and device_settings['percent_free'] is not None):
            raise ValueError('gigabytes_free and percent_free cannot both be '
                             'specified'
                             )

        self.data[f'device:{device_key}'] = device_settings

    # End update_device_settings

    def _resolve_category_settings(self, category_name):

        category_settings = const.DEFAULT_CATEGORY_SETTINGS.copy()
        category_settings['delete_order'] = const.CATEGORY_LIST.index(
                                              category_name
                                              )
        if self._config is not None:
            self._parse_category_conf(category_name, category_settings)
        if self._args.watched_offset is not None:
            category_settings['watched_offset'] = self._args.watched_offset

        self.data[f'category:{category_name}'] = category_settings

    # End update_category_settings

    def _resolve_series_settings(self, series_id):

        series_settings = {}
        if self._config is not None:
            self._parse_series_conf(series_id, series_settings)
        if self._args.watched_offset is not None:
            series_settings['watched_offset'] = self._args.watched_offset

        self.data[f'series:{series_id}'] = series_settings

    # End resolve_series_settings

    # vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab ai :
