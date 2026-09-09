# Security policy

Report vulnerabilities through GitHub private vulnerability reporting when enabled,
or ask maintainers for a private route. Do not post sensitive input or exploit
material publicly. No unmonitored email address is advertised.

Plugins execute with the current user's OS authority. Separate environments and
processes isolate dependencies/lifetime; they are **not an OS security sandbox**.
Local bundles require consent and are not authenticated by their own hashes.
The application never logs JSON documents or arbitrary plugin stderr content.
Offline default bundles inherit the application's distribution trust.

0.1.0 is experimental. Online catalogs and updates/data migrations are not enabled.
The Windows installer is an unsigned beta, and Linux native Wayland behavior is not
certified. Verify release hashes and GitHub provenance before running downloaded code.
