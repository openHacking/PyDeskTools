# Storage, configuration and internationalization

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

## User directory layout

Use platformdirs with an explicit application data_namespace. Separate data, config, cache and logs; never write beneath site-packages or an application bundle. Typical roots are LOCALAPPDATA on Windows, Application Support on macOS and XDG directories on Linux, as resolved by the adapter rather than hard-coded paths.

| Area | Contents | Durability |
|---|---|---|
| data | state.sqlite3, immutable plugin install slots, per-plugin data epochs | User-owned persistent state |
| config | Nonsecret application preferences and catalog trust settings | Preserve during upgrades |
| cache | Downloads, extraction staging and replaceable plugin caches | Safe to clear when unused |
| logs | Rotated host/worker diagnostic files | Default 7 days / bounded size, user-clearable |

SQLite stores application schema version, plugins, installs, active pointers, desired enabled state, install journal, plugin settings and catalog serial/key metadata. Add default_provisioning_completed, per-default-plugin user decision and consented recording preferences to the internal schema. Persist clipboard history/text and image files only in its plugin store; apply the retention and capacity rules in [bundled-tools.md](bundled-tools.md). Runtime process IDs are diagnostic observations, not proof that a stale process is still owned. Use parameterized queries, foreign keys and short transactions; GUI callbacks do not perform slow database work.

## Minimal records

- Plugin: id, desired_enabled, active_install_id, active_data_epoch, last_error_kind.
- Install: install_id, plugin_id, version, artifact_sha256, runtime_id, path, state, created_at.
- Install operation: operation_id, plugin_id, phase, candidate_install_id, previous_install_id, outcome.
- Plugin settings: plugin_id, key, JSON value; each update is atomic.
- Catalog: source_id, URL, trusted key IDs, highest accepted serial and cached payload metadata.

The SQLite schema is internal, not a public API. Plugin authors use context services. Files owned by plugin code stay in its data epoch and have plugin-defined formats; the host tracks epoch compatibility, snapshots and quotas but cannot infer arbitrary plugin data schemas.

## Crash recovery and backups

Record installation phases before modifying externally visible pointers. Use SQLite transactions for activation records; reconcile files and database on next launch. Never try to move a venv after pip installation. Garbage-collect only unreferenced, inactive installs after confirming no worker uses them.

Application database migrations create a backup first and advance a schema version transactionally. A newer unsupported schema stops startup with a recovery message rather than rewriting it. For exports, use SQLite's backup API instead of copying a live database file and ignoring its WAL. Plugin data migration/rollback follows the lifecycle contract and explicitly addresses data written after an upgrade.

## Language and localization

Documentation is English. UI locales initially `en` and `zh-CN`, mapped to gettext `en`/`zh_CN`. Resolve user choice first, then OS language, then English. Persist user choice. Application gettext domain is `pydesktools`; each plugin's domain is its stable ID and loads from that installed plugin's resources.

Locale changes update host views and restart idle plugin sessions with the new locale. Pause active clipboard subscriptions before restarting their worker and restore only existing recording consent; show the capture gap. Active invocations finish or are explicitly canceled before restart; do not lose their input silently. Plugin results produced in the old language remain historical output rather than being incorrectly retranslated.

No process-wide locale mutation. IDs, schema fields and error kinds stay English/machine-stable. Translate messages using named placeholders and plural-aware catalogs. Use UTF-8 for files and JSON, preserve Unicode paths, and never derive filesystem paths from translated names.

## Privacy

Do not add cloud sync, remote analytics or account state to the OSS storage model. Plugin settings are not a credential vault; default tools require no service credentials, but clipboard contents and selected files can contain sensitive data. Keep contents out of settings and logs; apply the retention and deletion rules in the default-tools specification. A future secret-storage capability needs an OS-keyring adapter and explicit threat model. User export/redaction controls precede any support upload feature.
