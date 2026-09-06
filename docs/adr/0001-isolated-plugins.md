# ADR 0001: Use isolated plugin workers and host-rendered views

> Design baseline: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

Status: accepted design direction; implementation pending. Date: 2026-09-03.

## Context

Users must install, disable and uninstall plugins while the application remains open. Python module reload and list clearing cannot reliably remove existing references, threads or native libraries. Plugins also need conflicting dependency versions.

## Decision

Each active plugin runs in a separate process with its own version-specific environment. The host imports no plugin code, renders bounded declarative views through PyDeskUI and communicates through local JSON-RPC pipes. There is no dynamic in-process plugin mode in v1. Trusted build-time application extensions are a separate distribution-level composition interface.

## Alternatives

In-process Python hooks are simpler and permit arbitrary Tk widgets but cannot offer the required cleanup/fault behavior. Supporting both modes initially doubles contract and safety complexity. Containers or OS sandboxes add substantial desktop deployment cost and are not necessary to establish process cleanup; they would address a different trust boundary.

## Consequences

Plugin UI is limited to the supported view vocabulary. Active workers consume extra memory and per-version environments consume disk. Hosts must ship or locate a real Python runtime and manage updates carefully. Venv/process isolation is not a malicious-code sandbox. This limitation is a product-facing fact, not a documentation footnote.

## Revisit trigger

Expand view types when reference/user plugins demonstrate unmet needs. Revisit sandboxing only with a separate OS capability/enforcement design. Do not add an in-process escape hatch to work around a missing view widget.
