#!/usr/bin/env python

import os
import subprocess
import tempfile
import hdhr_monitor_disk_space


class TestFunctions:


    def test_binarysize(self):

        assert hdhr_monitor_disk_space.binarysize(0) == '0.00 B'
        assert hdhr_monitor_disk_space.binarysize(0,0) == '0 B'
        assert hdhr_monitor_disk_space.binarysize(373,0) == '373 B'
        assert hdhr_monitor_disk_space.binarysize(1024) == '1.00 KiB'
        assert hdhr_monitor_disk_space.binarysize(1024 * 1.5,1) == '1.5 KiB'
        assert hdhr_monitor_disk_space.binarysize(1024 * 678,1) == '678.0 KiB'
        assert hdhr_monitor_disk_space.binarysize(1024**2) == '1.00 MiB'
        assert hdhr_monitor_disk_space.binarysize(1024**2 * 5.25) == '5.25 MiB'
        assert hdhr_monitor_disk_space.binarysize(1024**3 * 837.33333) == '837.33 GiB'
        assert hdhr_monitor_disk_space.binarysize(1024**4 * 37.376) == '37.38 TiB'


    def test_duration(self):

        assert hdhr_monitor_disk_space.duration(0) == '0 seconds'
        assert hdhr_monitor_disk_space.duration(1) == '1 second'
        assert hdhr_monitor_disk_space.duration(37) == '37 seconds'
        assert hdhr_monitor_disk_space.duration(60) == '1 minute'
        assert hdhr_monitor_disk_space.duration(60*3) == '3 minutes'
        assert hdhr_monitor_disk_space.duration((43*60) + 39) == '43 minutes, 39 seconds'
        assert hdhr_monitor_disk_space.duration(3600) == '1 hour'
        assert hdhr_monitor_disk_space.duration(3600*3) == '3 hours'
        assert hdhr_monitor_disk_space.duration((3600*14) + (60*15)) == '14 hours, 15 minutes'
        assert hdhr_monitor_disk_space.duration((3600*14) + (60*15) + 59) == '14 hours, 15 minutes, 59 seconds'
        assert hdhr_monitor_disk_space.duration(86400) == '1 day'
        assert hdhr_monitor_disk_space.duration((86400*4) + 3600) == '4 days, 1 hour'
        assert hdhr_monitor_disk_space.duration((86400*8) + (3600*5) + (60*34)) == '8 days, 5 hours, 34 minutes'
        assert hdhr_monitor_disk_space.duration((86400*3) + (3600*3) + (60*3) + 1) == '3 days, 3 hours, 3 minutes, 1 second'


class TestCLISuccess:


    def run_cli_test(self, args, expected_output):

        cmd = ['./hdhr_monitor_disk_space.py', *args]
        prcs = subprocess.run(cmd, capture_output=True)

        if expected_output == '':
            assert prcs.stdout.decode('UTF-8') == ''
        else:
            for item in expected_output:
                assert item in prcs.stdout.decode('UTF-8')

        assert prcs.stderr.decode('UTF-8') == ''
        assert prcs.returncode == 0


    def test_cli_conf_file_good(self):

        fd, file_name = tempfile.mkstemp()
        os.close(fd)

        args = ['--count', '1', '--conf-file', file_name]
        expected_output = ["Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: "
                           ]

        try:
            self.run_cli_test(args, expected_output)
        finally:
            os.remove(file_name)


    def test_cli_help(self):

        args = ['--help']
        expected_output = ["Monitor disk space utilization of one HDHomeRun SCRIBE or SERVIO device."]
        self.run_cli_test(args, expected_output)


    def test_cli_device_discover(self):

        args= ['--count', '1', '--device-id', 'discover']
        expected_output = ["Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_mode_report(self):

        args = ['--count', '1', '--mode', 'report']
        expected_output = ["Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_mode_maintain(self):

        args = ['--count', '1', '--mode', 'maintain']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_mode_maintain_verbose(self):

        args = ['--count', '1', '--mode', 'maintain', '--verbose']
        expected_output = ["Monitoring device",
                           "Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Running maintenance cycle - checking free space",
                           "Next maintenance cycle in",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_interval_5(self):

        args = ['--count', '1', '--interval', '5']
        expected_output = ["Disk space utilization will be reported every 5 seconds, stopping after 1 report",
                           "Total: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_count_3(self):

        args = ['--count', '3', '--interval', '1']
        expected_output = ["Disk space utilization will be reported every 1 second, stopping after 3 reports",
                           "Total: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_count_0(self):

        args = ['--count', '0']
        expected_output = ""
        self.run_cli_test(args, expected_output)


    def test_cli_gigabytes_free_5(self):

        args = ['--count', '1', '--mode', 'maintain', '--gigabytes-free', '5']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 5.00 GiB.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_percent_free_5(self):

        args = ['--count', '1', '--mode', 'maintain', '--percent-free', '5']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 5.0%.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_delete_policy_age(self):

        args = ['--count', '1', '--mode', 'maintain', '--delete-policy', 'age']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_delete_policy_category(self):

        args = ['--count', '1', '--mode', 'maintain', '--delete-policy', 'category']
        expected_output = ["Recordings will be deleted according to category to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_delete_policy_priority(self):

        args = ['--count', '1', '--mode', 'maintain', '--delete-policy', 'priority']
        expected_output = ["Recordings will be deleted according to priority to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_delete_watched_first(self):

        args = ['--count', '1', '--mode', 'maintain', '--watched-first']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Watched recordings will be deleted first.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_delete_watched_offset_5(self):

        args = ['--count', '1', '--mode', 'maintain', '--watched-first', '--watched-offset', '5']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Watched recordings will be deleted first.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


    def test_cli_delete_watched_offset_0(self):

        args = ['--count', '1', '--mode', 'maintain', '--watched-first', '--watched-offset', '0']
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Watched recordings will be deleted first.",
                           "Disk space utilization will be reported every 10 minutes, stopping after 1 report",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_cli_test(args, expected_output)


class TestCLIFailure:


    def run_cli_test(self, args, expected_stderr, expected_stdout=''):

        cmd = ['./hdhr_monitor_disk_space.py', *args]
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

        args = ['--count', '1', '--conf-file', file_name]
        expected_stderr = ["usage:",
                           f"hdhr_monitor_disk_space.py: error: argument -f/--conf-file: can't open '{file_name}': [Errno 2] No such file or directory: '{file_name}'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_device_bad(self):

        args = ['--count', '1', '--device-id', 'FFFFFFFF']
        expected_stderr = ['ERROR No device found to monitor. Run with "--verbose" for more information.']
        self.run_cli_test(args, expected_stderr)


    def test_cli_device_bad_verbose(self):

        args = ['--count', '1', '--device-id', 'FFFFFFFF', '--verbose']
        expected_stderr = ['ERROR No device found to monitor']
        expected_stdout = ['is not the one you are looking for']
        self.run_cli_test(args, expected_stderr, expected_stdout)


    def test_cli_mode_x(self):

        args = ['--count', '1', '--mode', 'x']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -m/--mode: invalid mode value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_interval_0(self):

        args = ['--count', '1', '--interval', '0']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -i/--interval: invalid interval value: '0'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_interval_neg_5(self):

        args = ['--count', '1', '--interval', '-5']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -i/--interval: invalid interval value: '-5'",
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_interval_x(self):

        args = ['--count', '1', '--interval', 'x']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -i/--interval: invalid interval value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_count_neg_10(self):

        args = ['--count', '-10']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -c/--count: invalid count value: '-10'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_count_x(self):

        args = ['--count', 'x']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -c/--count: invalid count value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_gigabytes_free_0(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--gigabytes-free', '0']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -g/--gigabytes-free: invalid gigabytes_free value: '0'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_gigabytes_free_neg_5(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--gigabytes-free', '-5']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -g/--gigabytes-free: invalid gigabytes_free value: '-5'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_gigabytes_free_x(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--gigabytes-free', 'x']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -g/--gigabytes-free: invalid gigabytes_free value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_percent_free_0(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--percent-free', '0']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -p/--percent-free: invalid percent_free value: '0'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_percent_free_neg_5(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--percent-free', '-5']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -p/--percent-free: invalid percent_free value: '-5'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_percent_free_x(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--percent-free', 'x']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -p/--percent-free: invalid percent_free value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_percent_free_and_gigabytes_free_5(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--percent-free', '5',
               '--gigabytes-free', '5']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -g/--gigabytes-free: not allowed with argument -p/--percent-free"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_delete_policy_x(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--delete-policy', 'x']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -s/--delete-policy: invalid delete_policy value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_delete_watched_offset_neg_5(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--watched-first', '--watched-offset', '-5']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -o/--watched-offset: invalid watched_offset value: '-5'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_cli_delete_watched_offset_x(self):

        args = ['--count', '1', '--mode', 'maintain',
               '--watched-first', '--watched-offset', 'x']
        expected_stderr = ["usage:",
                           "hdhr_monitor_disk_space.py: error: argument -o/--watched-offset: invalid watched_offset value: 'x'"
                           ]
        self.run_cli_test(args, expected_stderr)


    def test_huge_gigabytes_free(self):

        args = ['--count', '1', '--mode', 'maintain', '--gigabytes-free', '102400']
        expected_stderr = ["ERROR Minimum free space (100.00 TiB) cannot be greater than device"]
        self.run_cli_test(args, expected_stderr)


class TestConfSuccess:


    def run_conf_test(self, conf, args=['--count', '1'], expected_output=''):

        fd, file_name = tempfile.mkstemp()
        os.writev(fd, conf)
        os.close(fd)

        cmd = ['./hdhr_monitor_disk_space.py', *args]
        cmd.append("--conf-file")
        cmd.append(file_name)
        prcs = subprocess.run(cmd, capture_output=True)

        os.remove(file_name)

        if expected_output == '':
            assert prcs.stdout.decode('UTF-8') == ''
        else:
            for item in expected_output:
                assert item in prcs.stdout.decode('UTF-8')

        assert prcs.stderr.decode('UTF-8') == ''
        assert prcs.returncode == 0


    def test_conf_mode_report(self):

        conf = [b'[DEFAULT]\n',
                b'mode = report\n',
                ]
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_mode_maintain(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_interval_10(self):

        conf = [b'[DEFAULT]\n',
                b'interval = 10\n',
                ]
        expected_output = ["Disk space utilization will be reported every 10 seconds",
                           "Total: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_count_3(self):

        conf = [b'[DEFAULT]\n',
                b'interval = 1\n',
                b'count = 3\n',
                ]
        args = []
        expected_output = ["Disk space utilization will be reported every 1 second, stopping after 3 reports",
                           "Total: "
                           ]
        self.run_conf_test(conf, args, expected_output=expected_output)


    def test_conf_count_empty(self):

        conf = [b'[DEFAULT]\n',
                b'count = \n',
                ]
        expected_output = ["Disk space utilization will be reported every 10 minutes",
                           "Total: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_count_0(self):

        conf = [b'[DEFAULT]\n',
                b'count = 0\n',
                ]
        args = []
        expected_output = ""
        self.run_conf_test(conf, args, expected_output=expected_output)


    def test_conf_gigabytes_free_5(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'gigabytes_free = 5\n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 5.00 GiB.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_gigabytes_free_empty(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'gigabytes_free = \n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_percent_free_5(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'percent_free = 5\n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 5.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_percent_free_empty(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'percent_free = \n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_percent_free_and_gigabytes_free_empty(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'gigabytes_free = \n',
                b'percent_free = \n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_delete_policy_age(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'delete_policy = age\n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_delete_policy_category(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'delete_policy = category\n',
                ]
        expected_output = ["Recordings will be deleted according to category to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_delete_policy_priority(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'delete_policy = priority\n',
                ]
        expected_output = ["Recordings will be deleted according to priority to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_watched_first_yes(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'watched_first = yes\n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Watched recordings will be deleted first.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_watched_first_no(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'watched_first = no\n',
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_watched_offset_60(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'watched_offset = 60\n'
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_watched_offset_0(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'watched_offset = 0\n'
                ]
        expected_output = ["Recordings will be deleted according to age to maintain minimum free space of 2.0%.",
                           "Disk space utilization will be reported every 10 minutes",
                           "Total: ",
                           "Minimum Free: "
                           ]
        self.run_conf_test(conf, expected_output=expected_output)


class TestConfFailure:


    def run_conf_test(self, conf, args=['--count', '1'], expected_output=''):

        fd, file_name = tempfile.mkstemp()
        os.writev(fd, conf)
        os.close(fd)

        cmd = ['./hdhr_monitor_disk_space.py', *args]
        cmd.append("--conf-file")
        cmd.append(file_name)
        prcs = subprocess.run(cmd, capture_output=True)

        os.remove(file_name)

        if expected_output == '':
            assert prcs.stderr.decode('UTF-8') == ''
        else:
            assert f"ERROR Configuration file {file_name}:" in prcs.stderr.decode('UTF-8')
            for item in expected_output:
                assert item in prcs.stderr.decode('UTF-8')

        assert prcs.stdout.decode('UTF-8') == ''
        assert prcs.returncode == 2


    def test_conf_mode_x(self):

        conf = [b'[DEFAULT]\n',
                b'mode = x\n',
                ]
        expected_output = "invalid mode value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_interval_0(self):

        conf = [b'[DEFAULT]\n',
                b'interval = 0\n',
                ]
        expected_output = "invalid interval value: '0'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_interval_neg_10(self):

        conf = [b'[DEFAULT]\n',
                b'interval = -10\n',
                ]
        expected_output = "invalid interval value: '-10'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_interval_x(self):

        conf = [b'[DEFAULT]\n',
                b'interval = x\n',
                ]
        expected_output = "invalid interval value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_count_neg_10(self):

        conf = [b'[DEFAULT]\n',
                b'count = -10\n',
                ]
        expected_output = "invalid count value: '-10'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_count_x(self):

        conf = [b'[DEFAULT]\n',
                b'count = x\n',
                ]
        expected_output = "invalid count value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_gigabytes_free_0(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'gigabytes_free = 0\n',
                ]
        expected_output = "invalid gigabytes_free value: '0'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_gigabytes_free_neg_10(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'gigabytes_free = -10\n',
                ]
        expected_output = "invalid gigabytes_free value: '-10'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_gigabytes_free_x(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'gigabytes_free = x\n',
                ]
        expected_output = "invalid gigabytes_free value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_percent_free_0(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'percent_free = 0\n',
                ]
        expected_output = "invalid percent_free value: '0'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_percent_free_neg_10(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'percent_free = -10\n',
                ]
        expected_output = "invalid percent_free value: '-10'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_percent_free_x(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'percent_free = x\n',
                ]
        expected_output = "invalid percent_free value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_percent_free_and_gigabytes_free_5(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'gigabytes_free = 5\n',
                b'percent_free = 5\n',
                ]
        expected_output = "gigabytes_free and percent_free cannot both be specified"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_delete_policy_x(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'delete_policy = x\n',
                ]
        expected_output = "invalid delete_policy value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_watched_first_x(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'watched_first = x\n',
                ]
        expected_output = "Not a boolean: x"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_watched_offset_neg_60(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'watched_offset = -60\n'
                ]
        expected_output = "invalid watched_offset value: '-60'"
        self.run_conf_test(conf, expected_output=expected_output)


    def test_conf_watched_offset_neg_x(self):

        conf = [b'[DEFAULT]\n',
                b'mode = maintain\n',
                b'watched_offset = x\n'
                ]
        expected_output = "invalid watched_offset value: 'x'"
        self.run_conf_test(conf, expected_output=expected_output)
