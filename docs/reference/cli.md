---
title: "CLI — glean Reference"
description: All glean command-line subcommands and options.
---

# `glean`

glean — pluggable feed digester for Telegram.

**Usage**:

```console
$ glean [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `version`: Print version and exit.
* `migrate`: Apply any pending state schema migrations.
* `validate-config`: Parse feeds.yaml and exit 0 if valid, 1...
* `list-feeds`: Show configured feeds and their last-run...
* `test-feed`: Run a feed once.
* `send-now`: Run a feed off-schedule and actually send...
* `run`: Run the scheduler daemon.

## `glean version`

Print version and exit.

**Usage**:

```console
$ glean version [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `glean migrate`

Apply any pending state schema migrations.

**Usage**:

```console
$ glean migrate [OPTIONS]
```

**Options**:

* `--db PATH`: Path to SQLite state DB  [env var: GLEAN_DB; default: /data/state.db]
* `--help`: Show this message and exit.

## `glean validate-config`

Parse feeds.yaml and exit 0 if valid, 1 otherwise.

**Usage**:

```console
$ glean validate-config [OPTIONS]
```

**Options**:

* `-c, --config PATH`: Path to feeds.yaml  [env var: GLEAN_CONFIG; default: /etc/glean/feeds.yaml]
* `--log-level TEXT`: [env var: LOG_LEVEL; default: WARNING]
* `--help`: Show this message and exit.

## `glean list-feeds`

Show configured feeds and their last-run state.

**Usage**:

```console
$ glean list-feeds [OPTIONS]
```

**Options**:

* `-c, --config PATH`: Path to feeds.yaml  [env var: GLEAN_CONFIG; default: /etc/glean/feeds.yaml]
* `--db PATH`: Path to SQLite state DB  [env var: GLEAN_DB; default: /data/state.db]
* `--log-level TEXT`: [env var: LOG_LEVEL; default: WARNING]
* `--help`: Show this message and exit.

## `glean test-feed`

Run a feed once. Default is dry-run (no Telegram, no state writes).

**Usage**:

```console
$ glean test-feed [OPTIONS] NAME
```

**Arguments**:

* `NAME`: [required]

**Options**:

* `-c, --config PATH`: Path to feeds.yaml  [env var: GLEAN_CONFIG; default: /etc/glean/feeds.yaml]
* `--db PATH`: Path to SQLite state DB  [env var: GLEAN_DB; default: /data/state.db]
* `--send`: Actually send to Telegram.
* `--log-level TEXT`: [env var: LOG_LEVEL; default: INFO]
* `--help`: Show this message and exit.

## `glean send-now`

Run a feed off-schedule and actually send to Telegram.

**Usage**:

```console
$ glean send-now [OPTIONS] NAME
```

**Arguments**:

* `NAME`: [required]

**Options**:

* `-c, --config PATH`: Path to feeds.yaml  [env var: GLEAN_CONFIG; default: /etc/glean/feeds.yaml]
* `--db PATH`: Path to SQLite state DB  [env var: GLEAN_DB; default: /data/state.db]
* `--log-level TEXT`: [env var: LOG_LEVEL; default: INFO]
* `--help`: Show this message and exit.

## `glean run`

Run the scheduler daemon.

**Usage**:

```console
$ glean run [OPTIONS]
```

**Options**:

* `-c, --config PATH`: Path to feeds.yaml  [env var: GLEAN_CONFIG; default: /etc/glean/feeds.yaml]
* `--db PATH`: Path to SQLite state DB  [env var: GLEAN_DB; default: /data/state.db]
* `--health-port INTEGER`: [env var: HEALTH_PORT; default: 9090]
* `--log-level TEXT`: [env var: LOG_LEVEL; default: INFO]
* `--help`: Show this message and exit.
