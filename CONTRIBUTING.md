# Contributing

This project is in its initial design stage. Issues describing supported sensor
objects, desired chart behavior, or deployment needs are welcome.

Keep changes independent of Nevermore projects and printer control interfaces.
The monitoring service should read telemetry and never issue printer commands.

Use placeholder endpoints in examples. Do not commit API keys, local settings,
printer configuration dumps, databases, logs, or personal telemetry. When reporting
sensor behavior, provide the sensor type and a small sanitized example.

For code contributions, describe the behavior changed and how it was verified.
Tests should cover meaningful behavior such as persistence, retention, missing data,
sensor discovery, and units rather than simply reproducing the implementation.
