# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
- Web UI to maintain configuration

## [2.0.0] - 2020-06-25

### Added
- Allow configuration of maximum recording age or maximum number of recordings per series at the category or series level. See configuration file example.
- The `-n/--dry-run` option has been added. This will prevent any recordings from being deleted, while the log messages will indicate what would have been deleted and why.
- Source distribution now available on PyPI. Install with `pip install hdhr_disk_space_monitor`.

### Changed
- Invocation is no longer via "`hdhr_monitor_disk_space.py`". Assuming installation from the source distribution via pip, invoke as "`hdhr_disk_space_monitor`".
- Device discovery default behavior has changed. Instead of finding and operating on just the first storage device found, now all storage devices found are monitored/maintained. Free space is maintained independently per device. Recordings are maintained across all devices as a whole.
- `-p/--percent-free` no longer defaults to "2". It must be set explicitly, if desired.
- Device labels in output messages now more closely align with how they appear on the device web pages.
- Device discovery no longer makes any use of the hosted API. All traffic is confined to the local network.
- Changed license to GPL2 after reusing some code from [Silicondust](https://github.com/Silicondust/script.hdhomerun.view)

### Removed
- The `-m/--mode` argument has been removed. The mode of operation is now implied by other arguments. If `-g/--gigabytes-free` or `-p/--percent-free` are specified, then disk space maintenance is performed. If `max_age_days` or `max_episodes` are set in the configuration file, then recording maintenance is performed.
- The `-d/--device-id` no longer accepts "ALL". The default behavior is now to discover all storage devices.

## [1.5.0] - 2020-06-10

### Added

- Multiple devices can be monitored by a single process. Provide multiple device IDs, IP addresses, or hostnames to monitor specific devices. Use the keyword "ALL" as a device ID to monitor all devices found with a StorageID.

### Changed

- In maintain mode, after the requested number of reports (`-c|--count`) has been shown, maintenance will continue to run. This allows a "quiet" maintain mode if the count is set to zero.

## [1.4.0] - 2020-06-09

### Removed

- "priority" has been removed as a delete policy option. This allows RECORD devices to work in maintain mode.

## [1.3.0] - 2020-06-08

### Added

- Specify IP address or hostname instead of device ID
- Support for RECORD devices/installations
- Command-line option (`-V|--version`) to display version number

### Changed

- Disk space now displayed in powers of 10 instead of powers of 2 to match what is shown by the devices themselves
- Removed some verbose device discovery messages

### Fixed

- Compatibility with recent firmware release

## [1.2.0] - 2020-05-15

### Added

- Protect currently playing recordings from deletion
- Attempt to use .local addresses before hitting my.hdhomerun.com

## [1.1.0] - 2020-05-03

### Changed

- Improve resilience of systemd service

## [1.0.0] - 2020-05-01

### Added

- Test suite
- Command-line option (`-c|--count`) to limit number of disk space reports shown

### Changed

- Improved exception handling
- Command-line option for config file is now "-f"

## [0.3.0] - 2020-04-28

### Added

- Configuration file

### Changed

- Disk space reporting and disk space maintenance now run in separate threads at independent intervals
- Cleaned up output formatting

## [0.2.0] - 2020-04-24

### Added

- Option to delete watched recordings before applying delete policy

## [0.1.1] - 2020-04-24

### Fixed

- Changed recording rules API call to HTTPS
- Exit with non-zero code on caught errors/exceptions

## [0.1.0] - 2020-04-22

### Added

- Initial version of monitor
- systemd service file
