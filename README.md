# Klipper Temperature History

A standalone temperature-history monitor for Klipper printers using Moonraker.

## Project status

This repository currently contains the project documentation and license. The logger,
database, web dashboard, and installer are planned and are not implemented yet.

## Purpose

Keep temperature history over several days, including when the browser is closed,
without adding code to a printer control UI or a Nevermore project. The setup will
run independently on the printer's Linux host or another always-on Linux machine.

## Planned features

- Discover temperature sensors exposed by Moonraker, including heaters,
  temperature sensors, temperature fans, and supported temperature monitors.
- Record temperatures every 10 seconds in a persistent SQLite database.
- Retain 30 days of history by default, with configurable sampling and retention.
- Provide live readings and 1-hour, 24-hour, 7-day, and 30-day chart views.
- Select sensors and group heaters, motors, and electronics for readable charts.
- Record heater targets and print-state changes alongside temperatures.
- Show gaps for missing or disconnected sensors rather than inventing readings.
- Export recorded data as CSV.
- Run as its own systemd service and serve a dashboard on a configurable port.

## Design boundaries

The monitor will read telemetry from Moonraker. It will not send G-code, change
heater targets, control fans, or modify printer configuration. It will have its own
configuration, database, service, and web assets. It will not depend on or modify
Nevermore software. Any future integration with an additional telemetry source
will be optional.

Not every value presented through a Klipper temperature interface is a temperature.
Power sensors and other non-temperature telemetry must be identified and labeled
with their actual units before appearing in charts.

## Planned configuration

Settings will include the Moonraker endpoint, an optional API credential, sample
interval, retention period, database location, and dashboard bind address and port.
Examples will use placeholders such as `http://printer.local:7125`; personal IP
addresses, credentials, and captured telemetry do not belong in this repository.

## Installation

There is no installable release yet. Installation instructions will be added when
the first logger and dashboard are implemented and verified.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests are welcome.

## License

[MIT](LICENSE).
