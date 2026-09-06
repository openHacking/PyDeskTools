# Documentation verification report

Date: 2026-09-03. Source baseline: `c0918e8`. This is a documentation-only delivery.

## Checks performed

- Parsed the 24 source Python files and inspected package imports, plugin discovery/install logic, metaclass registry and sample tests. No GUI/runtime correctness is inferred from syntax parsing.
- Parsed the example manifest with tomllib and the descriptor/session fixtures as JSON.
- Checked initialization identity/version against the manifest, unique paired request/response IDs, descriptor equality and deactivate/shutdown ordering.
- Validated example command input/output against JSON Schema and compared the format result with Python's standard JSON formatter.
- Parsed proposed Python code blocks and checked document links, table columns, fences and English prose.
- Checked public documents for private project identifiers and machine-specific absolute paths; none were introduced.
- Verified README body preservation and reviewed all five critical runtime risks in the roadmap.

## Corrections during review

Specified that venvs are created in their final immutable path and only activation pointers are switched. Separated installed/enabled/running/removal-pending states. Added base host-call dispatch and bounded dialog deadlines. Preserved completion-unknown information when a worker disappears so an external operation cannot be misreported as safely canceled. Clarified that manifest platform labels do not replace wheel ABI/tag checks.

The existing `.gitignore` ignored the entire docs directory. Its rule is narrowed to `/docs/_build/` so documentation is visible to Git while generated documentation output remains ignored. No product source or dependency configuration is changed.

## Limits

Examples are documentation fixtures, not a real installed plugin or protocol implementation. Process isolation, cleanup, crash recovery, installer signing and GUI behavior require the future acceptance suite. Mermaid source was structurally inspected but not rendered; no full HTTP link crawl or Sphinx build was performed. No dependency security clearance is claimed.

The [roadmap](roadmap.md) identifies the product tests that still must run. Local document validation is not evidence that they pass.

## Revision verification: 2026-09-04

This revision changes design documents and fixtures only. The 2026-09-03 source audit above remains historical; no new source execution or GUI test is claimed. Across the three staged documentation sets, local checks passed for 40 design Markdown documents, 81 local links, 36 tables, 6 Python example blocks, 5 JSON fixtures and 1 TOML manifest. Six Mermaid blocks were checked for fences/type only, not rendered. Existing repository README content is excluded from the English-prose scan.

Cross-contract checks passed for manifest/session identity, request/response pairing, JSON command schemas/results, workflow references, product/major identity cases, image artifact references and subscription IDs. These are static fixture checks, not SDK, cryptographic, installer or platform integration tests. Pricing arithmetic remains illustrative and was recalculated; no profitability claim follows. No Sphinx build or complete external-link crawl was performed.

Adversarial review covered default-tool reinstalls, capture without consent, unload leaks, large image messages and runtime coupling. The design now persists uninstall decisions, denies capture during health checks, revokes subscriptions before stop, uses bounded artifacts and separates the headless runtime. Offline provisioning, process cleanup and OS permissions still require actual installer tests.
