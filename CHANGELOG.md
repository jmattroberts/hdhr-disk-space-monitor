# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
- Monitor multiple devices in a single process
- Allow configuration of maximum recording age or number of recordings based on category
- Allow configuration of maximum recording age or number of recordings per recording rule or series
- Web UI to maintain configuration

## [1.4.0] - 2020-06-09

### Removed

- "priority" has been removed as a delete policy option. This allows RECORD devices to work in maintain mode.

## [1.3.0] - 2020-06-08

### Added

- Specify IP address or hostname instead of device ID
- Support for RECORD devices/installations
- Command-line option (-V|--version) to display version number

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
- Command-line option (-c|--count) to limit number of disk space reports shown

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
