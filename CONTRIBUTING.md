# Contributing

Use Python 3.12 and the pinned requirements. Install the package editable, run `pytest -q`, and use the pinned OSS CAD Suite for hardware tests. Tests skip hardware-specific checks when tools are absent; a skipped integration check is not a verified circuit. CI installs the tools and exercises a real synthesis/routing smoke build.

Keep the model subset explicit. Extend validation, the independent integer reference, HDL generation and meaningful boundary/protocol tests together. A new operation requires demonstrated behavior before it appears in documentation. Preserve deterministic HDL and keep arithmetic semantics in docs/arithmetic.md synchronized with implementation.

Measurements need source model/config, tool versions, exact commands, routing seed, logs and input/output evidence. Include failed attempts in benchmark denominators. Explain LUT counting and clock/IO constraints. Keep validation and test data separate. Baseline comparisons need matched candidate spaces and charged compilation costs, with acquisition overhead disclosed.

For observatory changes, inspect current-source desktop and narrow-width previews and verify candidate selection, budgets, evidence links and waveform replay. Public mode is recorded; live compiler work belongs to the loopback service. Never add a fabricated fallback dataset of performance values.

Open an issue with the smallest reproducible model, configuration and logs. Do not include credentials or confidential datasets. Contributions are under Apache-2.0 unless identified otherwise; retain required third-party attribution.
