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

import os
import subprocess
import tempfile
from hdhr_disk_space_monitor.core import binarysize, duration

cmd_base = ['python', '-m', 'hdhr_disk_space_monitor.core', '--test-mode']

class TestFunctions:

    def test_binarysize(self):

        assert binarysize(0) == '0.00 B'
        assert binarysize(0,0) == '0 B'
        assert binarysize(373,0) == '373 B'
        assert binarysize(10**3) == '1.00 KB'
        assert binarysize(10**3 * 1.5,1) == '1.5 KB'
        assert binarysize(10**3 * 678,1) == '678.0 KB'
        assert binarysize(10**6) == '1.00 MB'
        assert binarysize(10**6 * 5.25) == '5.25 MB'
        assert binarysize(10**9 * 837.33333) == '837.33 GB'
        assert binarysize(10**12 * 37.376) == '37.38 TB'

    def test_duration(self):

        assert duration(0) == '0 seconds'
        assert duration(1) == '1 second'
        assert duration(37) == '37 seconds'
        assert duration(60) == '1 minute'
        assert duration(60*3) == '3 minutes'
        assert duration((43*60) + 39) == '43 minutes, 39 seconds'
        assert duration(3600) == '1 hour'
        assert duration(3600*3) == '3 hours'
        assert duration((3600*14) + (60*15)) == '14 hours, 15 minutes'
        assert duration((3600*14) + (60*15) + 59) == '14 hours, 15 minutes, 59 seconds'
        assert duration(86400) == '1 day'
        assert duration((86400*4) + 3600) == '4 days, 1 hour'
        assert duration((86400*8) + (3600*5) + (60*34)) == '8 days, 5 hours, 34 minutes'
        assert duration((86400*3) + (3600*3) + (60*3) + 1) == '3 days, 3 hours, 3 minutes, 1 second'


class TestCLISuccess:

    def run_cli_test(self, args, expected_output, expected_stderr=['WARNING This is a dry-run. No recordings will be deleted, even if log messages indicate otherwise.']):

        args.append('--dry-run')
        cmd = [*cmd_base, *args]
        prcs = subprocess.run(cmd, capture_output=True)

        if expected_output == '':
            assert prcs.stdout.decode('UTF-8') == ''
        else:
            for item in expected_output:
                assert item in prcs.stdout.decode('UTF-8')

        if expected_stderr == '':
            assert prcs.stderr.decode('UTF-8') == ''
        else:
            for item in expected_stderr:
                assert item in prcs.stderr.decode('UTF-8')
        assert prcs.returncode == 0

    def test_cli_conf_file_good(self):

        fd, file_name = tempfile.mkstemp()
        os.close(fd)

        args = ['--verbose', '--conf-file', file_name]
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: "
                           ]
        try:
            self.run_cli_test(args, expected_output)
        finally:
            os.remove(file_name)

    def test_cli_help(self):

        args = ['--help']
        expected_output = ["Monitor disk space utilization of HDHomeRun SCRIBE, SERVIO, and RECORD"]
        expected_stderr = ''
        self.run_cli_test(args, expected_output, expected_stderr)

    def test_cli_bare(self):

        args= []
        expected_output = ["Total: "]
        self.run_cli_test(args, expected_output)

    def test_cli_interval_5(self):

        args = ['--verbose', '--interval', '5']
        expected_output = ["Disk space utilization will be reported every 5 seconds",
                           "Total: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_count_3(self):

        args = ['--verbose', '--count', '3', '--interval', '1']
        expected_output = ["Disk space utilization will be reported every 1 second, stopping after 3 reports",
                           "Total: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_count_0(self):

        args = ['--verbose', '--count', '0']
        expected_output = ""
        self.run_cli_test(args, expected_output)

    def test_cli_gigabytes_free_5(self):

        args = ['--verbose', '--gigabytes-free', '5']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 5.00 GB.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_percent_free_1(self):

        args = ['--verbose', '--percent-free', '1']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 1.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_delete_policy_age(self):

        args = ['--verbose', '--percent-free', '2', '--delete-policy', 'age']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_delete_policy_category(self):

        args = ['--verbose', '--percent-free', '2', '--delete-policy', 'category']
        expected_output = ["Recordings will be deleted according to category to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_delete_watched_first(self):

        args = ['--verbose', '--percent-free', '2', '--watched-first']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Watched recordings will be deleted first.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_delete_watched_offset_5(self):

        args = ['--verbose', '--percent-free', '2', '--watched-first', '--watched-offset', '5']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Watched recordings will be deleted first.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_delete_watched_offset_0(self):

        args = ['--verbose', '--percent-free', '2', '--watched-first', '--watched-offset', '0']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Watched recordings will be deleted first.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)

    def test_cli_device_bad(self):

        args = ['--device-id', 'AAAAAAAA']
        expected_output = []
        expected_stderr = ["ERROR Device not found: AAAAAAAA"]
        self.run_cli_test(args, expected_output, expected_stderr)

    def test_cli_device_bad_verbose(self):

        args = ['--device-id', 'AAAAAAAA', '--verbose']
        expected_output = []
        expected_stderr = ["ERROR Device not found: AAAAAAAA"]
        self.run_cli_test(args, expected_output, expected_stderr)

    def test_cli_huge_gigabytes_free(self):

        args = ['--gigabytes-free', '100000']
        expected_output = ["Total: "]
        expected_stderr = ["Minimum free space (100.00 TB) cannot be greater than device"]
        self.run_cli_test(args, expected_output, expected_stderr)


class TestCLIFailure:

    def run_cli_test(self, args, expected_stderr, expected_stdout=''):

        args.append('--dry-run')
        cmd = [*cmd_base, *args]
        prcs = subprocess.run(cmd, capture_output=True)

        if expected_stderr == '':
            assert prcs.stderr.decode('UTF-8') == ''
        else:
            for item in expected_stderr:
                assert item in prcs.stderr.decode('UTF-8')

        if expected_stdout == '':
            assert prcs.stdout.decode('UTF-8') == ''
        else:
            for item in expected_stdout:
                assert item in prcs.stdout.decode('UTF-8')

        assert prcs.returncode == 2

    def test_cli_conf_file_bad(self):

        fd, file_name = tempfile.mkstemp()
        os.close(fd)
        os.remove(file_name)

        args = ['--conf-file', file_name]
        expected_stderr = ["usage:",
                "error: argument -f/--conf-file: can't open",
                "[Errno 2] No such file or directory:"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_interval_0(self):

        args = ['--interval', '0']
        expected_stderr = ["usage:",
                           "error: argument -i/--interval: invalid interval value: '0'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_interval_neg_5(self):

        args = ['--interval', '-5']
        expected_stderr = ["usage:",
                           "error: argument -i/--interval: invalid interval value: '-5'",
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_interval_x(self):

        args = ['--interval', 'x']
        expected_stderr = ["usage:",
                           "error: argument -i/--interval: invalid interval value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_count_neg_10(self):

        args = ['--count', '-10']
        expected_stderr = ["usage:",
                           "error: argument -c/--count: invalid count value: '-10'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_count_x(self):

        args = ['--count', 'x']
        expected_stderr = ["usage:",
                           "error: argument -c/--count: invalid count value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_gigabytes_free_0(self):

        args = ['--gigabytes-free', '0']
        expected_stderr = ["usage:",
                           "error: argument -g/--gigabytes-free: invalid gigabytes value: '0'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_gigabytes_free_neg_5(self):

        args = ['--gigabytes-free', '-5']
        expected_stderr = ["usage:",
                           "error: argument -g/--gigabytes-free: invalid gigabytes value: '-5'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_gigabytes_free_x(self):

        args = ['--gigabytes-free', 'x']
        expected_stderr = ["usage:",
                           "error: argument -g/--gigabytes-free: invalid gigabytes value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_percent_free_0(self):

        args = ['--percent-free', '0']
        expected_stderr = ["usage:",
                           "error: argument -p/--percent-free: invalid percent value: '0'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_percent_free_neg_5(self):

        args = ['--percent-free', '-5']
        expected_stderr = ["usage:",
                           "error: argument -p/--percent-free: invalid percent value: '-5'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_percent_free_x(self):

        args = ['--percent-free', 'x']
        expected_stderr = ["usage:",
                           "error: argument -p/--percent-free: invalid percent value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_percent_free_and_gigabytes_free_5(self):

        args = ['--percent-free', '5',
               '--gigabytes-free', '5']
        expected_stderr = ["usage:",
                           "error: argument -g/--gigabytes-free: not allowed with argument -p/--percent-free"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_delete_policy_x(self):

        args = ['--delete-policy', 'x']
        expected_stderr = ["usage:",
                           "error: argument -s/--delete-policy: invalid delete_policy value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_delete_watched_offset_neg_5(self):

        args = ['--watched-first', '--watched-offset', '-5']
        expected_stderr = ["usage:",
                           "error: argument -o/--watched-offset: invalid watched_offset value: '-5'"
                           ]
        self.run_cli_test(args, expected_stderr)

    def test_cli_delete_watched_offset_x(self):

        args = ['--watched-first', '--watched-offset', 'x']
        expected_stderr = ["usage:",
                           "error: argument -o/--watched-offset: invalid watched_offset value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)


class TestConfSuccess:

    def run_conf_test(self, conf, args=[], expected_output='', expected_stderr=['WARNING This is a dry-run. No recordings will be deleted, even if log messages indicate otherwise.']):

        fd, file_name = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write(conf)
        #os.writev(fd, conf)
        #os.close(fd)

        args.append('--verbose')
        args.append('--dry-run')
        cmd = [*cmd_base, *args]
        cmd.append("--conf-file")
        cmd.append(file_name)
        prcs = subprocess.run(cmd, capture_output=True)

        os.remove(file_name)

        if expected_output == '':
            assert prcs.stdout.decode('UTF-8') == ''
        else:
            for item in expected_output:
                assert item in prcs.stdout.decode('UTF-8')

        if expected_stderr == '':
            assert prcs.stderr.decode('UTF-8') == ''
        else:
            for item in expected_stderr:
                assert item in prcs.stderr.decode('UTF-8')

        assert prcs.returncode == 0

    def test_conf_case_insensitive_section_match(self):

        conf = ('[DeFaUlT]\n'
                'pERcenT_frEe = 2\n'
                )
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_mode_report(self):

        conf = ('[DEFAULT]\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_interval_10(self):

        conf = ('[DEFAULT]\n'
                'interval = 10\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 seconds",
                           "Total: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_count_3(self):

        conf = ('[DEFAULT]\n'
                'interval = 1\n'
                'count = 3\n'
                )
        args = ['--verbose', '--dry-run']
        expected_output = ["Disk space utilization will be reported every 1 second, stopping after 3 reports",
                           "Total: "
                           ]
        self.run_conf_test(conf, args, expected_output=expected_output)

    def test_conf_count_empty(self):

        conf = ('[DEFAULT]\n'
                'count = \n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_count_0(self):

        conf = ('[DEFAULT]\n'
                'count = 0\n'
                )
        args = ['--verbose', '--dry-run']
        expected_output = ""
        self.run_conf_test(conf, args, expected_output=expected_output)

    def test_conf_gigabytes_free_5(self):

        conf = ('[DEFAULT]\n'
                'gigabytes_free = 5\n'
                )
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 5.00 GB.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_gigabytes_free_empty(self):

        conf = ('[DEFAULT]\n'
                'gigabytes_free = \n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_percent_free_1(self):

        conf = ('[DEFAULT]\n'
                'percent_free = 1\n'
                )
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 1.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_percent_free_empty(self):

        conf = ('[DEFAULT]\n'
                'percent_free = \n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_percent_free_and_gigabytes_free_empty(self):

        conf = ('[DEFAULT]\n'
                'gigabytes_free = \n'
                'percent_free = \n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_delete_policy_age(self):

        conf = ('[DEFAULT]\n'
                'percent_free = 2\n'
                'delete_policy = age\n'
                )
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_delete_policy_category(self):

        conf = ('[DEFAULT]\n'
                'percent_free = 2\n'
                'delete_policy = category\n'
                )
        expected_output = ["Recordings will be deleted according to category to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_watched_first_yes(self):

        conf = ('[DEFAULT]\n'
                'percent_free = 2\n'
                'watched_first = yes\n'
                )
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Watched recordings will be deleted first.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_watched_first_no(self):

        conf = ('[DEFAULT]\n'
                'percent_free = 2\n'
                'watched_first = no\n'
                )
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_watched_offset_60(self):

        conf = ('[DEFAULT]\n'
                'percent_free = 2\n'
                'watched_offset = 60\n'
                )
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_watched_offset_0(self):

        conf = ('[DEFAULT]\n'
                'percent_free = 2\n'
                'watched_offset = 0\n'
                )
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_protected_yes(self):

        conf = ('[category:news]\n'
                'protected = yes\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_protected_no(self):

        conf = ('[category:news]\n'
                'protected = no\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_rerecord_deleted_yes(self):

        conf = ('[category:news]\n'
                'rerecord_deleted = yes\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_rerecord_deleted_no(self):

        conf = ('[category:news]\n'
                'rerecord_deleted = no\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_max_episodes_0(self):

        conf = ('[category:news]\n'
                'max_episodes = 0\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_max_episodes_5(self):

        conf = ('[category:news]\n'
                'max_episodes = 5\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_max_age_days_5(self):

        conf = ('[category:news]\n'
                'max_age_days = 5\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_delete_order_5(self):

        conf = ('[category:news]\n'
                'delete_order = 5\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_delete_order_neg_1_3(self):

        conf = ('[category:news]\n'
                'delete_order = -1.3\n'
                )
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


class TestConfFailure:

    def run_conf_test(self, conf, args=[], expected_output=''):

        fd, file_name = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write(conf)
        #os.writev(fd, conf)
        #os.close(fd)

        args.append('--dry-run')
        cmd = [*cmd_base, *args]
        cmd.append("--conf-file")
        cmd.append(file_name)
        prcs = subprocess.run(cmd, capture_output=True)

        os.remove(file_name)

        if expected_output == '':
            assert prcs.stderr.decode('UTF-8') == ''
        else:
            #assert f'ERROR Configuration file section "DEFAULT":' in prcs.stderr.decode('UTF-8')
            for item in expected_output:
                assert item in prcs.stderr.decode('UTF-8')

        assert prcs.stdout.decode('UTF-8') == ''
        assert prcs.returncode == 2

    def test_conf_interval_0(self):

        conf = ('[DEFAULT]\n'
                'interval = 0\n'
                )
        expected_output = "invalid interval value: '0'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_interval_neg_10(self):

        conf = ('[DEFAULT]\n'
                'interval = -10\n'
                )
        expected_output = "invalid interval value: '-10'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_interval_x(self):

        conf = ('[DEFAULT]\n'
                'interval = x\n'
                )
        expected_output = "invalid interval value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_count_neg_10(self):

        conf = ('[DEFAULT]\n'
                'count = -10\n'
                )
        expected_output = "invalid count value: '-10'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_count_x(self):

        conf = ('[DEFAULT]\n'
                'count = x\n'
                )
        expected_output = "invalid count value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_gigabytes_free_0(self):

        conf = ('[DEFAULT]\n'
                'gigabytes_free = 0\n'
                )
        expected_output = "invalid gigabytes value: '0'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_gigabytes_free_neg_10(self):

        conf = ('[DEFAULT]\n'
                'gigabytes_free = -10\n'
                )
        expected_output = "invalid gigabytes value: '-10'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_gigabytes_free_x(self):

        conf = ('[DEFAULT]\n'
                'gigabytes_free = x\n'
                )
        expected_output = "invalid gigabytes value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_percent_free_0(self):

        conf = ('[DEFAULT]\n'
                'percent_free = 0\n'
                )
        expected_output = "invalid percent value: '0'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_percent_free_neg_10(self):

        conf = ('[DEFAULT]\n'
                'percent_free = -10\n'
                )
        expected_output = "invalid percent value: '-10'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_percent_free_x(self):

        conf = ('[DEFAULT]\n'
                'percent_free = x\n'
                )
        expected_output = "invalid percent value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_percent_free_and_gigabytes_free_5(self):

        conf = ('[DEFAULT]\n'
                'gigabytes_free = 5\n'
                'percent_free = 5\n'
                )
        expected_output = "gigabytes_free and percent_free cannot both be specified"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_delete_policy_x(self):

        conf = ('[DEFAULT]\n'
                'delete_policy = x\n'
                )
        expected_output = "invalid delete_policy value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_watched_first_x(self):

        conf = ('[DEFAULT]\n'
                'watched_first = x\n'
                )
        expected_output = "Not a boolean: x"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_watched_offset_neg_60(self):

        conf = ('[DEFAULT]\n'
                'watched_offset = -60\n'
                )
        expected_output = "invalid watched_offset value: '-60'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_watched_offset_x(self):

        conf = ('[DEFAULT]\n'
                'watched_offset = x\n'
                )
        expected_output = "invalid watched_offset value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_protected_x(self):

        conf = ('[category:news]\n'
                'protected = x\n'
                )
        expected_output = "Not a boolean: x"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_rerecord_deleted_x(self):

        conf = ('[category:news]\n'
                'rerecord_deleted = x\n'
                )
        expected_output = "Not a boolean: x"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_max_episodes_neg_60(self):

        conf = ('[category:news]\n'
                'max_episodes = -60\n'
                )
        expected_output = "invalid max_episodes value: '-60'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_max_episodes_x(self):

        conf = ('[category:news]\n'
                'max_episodes = x\n'
                )
        expected_output = "invalid max_episodes value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_max_age_days_0(self):

        conf = ('[category:news]\n'
                'max_age_days = 0\n'
                )
        expected_output = "invalid max_age_days value: '0'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_max_age_days_neg_60(self):

        conf = ('[category:news]\n'
                'max_age_days = -60\n'
                )
        expected_output = "invalid max_age_days value: '-60'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_max_age_days_x(self):

        conf = ('[category:news]\n'
                'max_age_days = x\n'
                )
        expected_output = "invalid max_age_days value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)

    def test_conf_delete_order_x(self):

        conf = ('[category:news]\n'
                'delete_order = x\n'
                )
        expected_output = "invalid delete_order value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)
