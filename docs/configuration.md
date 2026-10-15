# Configuration

Intentline reads three layers. Later layers win.

1. Built-in defaults.
2. User config: `$INTENTLINE_CONFIG_HOME`, or `$XDG_CONFIG_HOME/intentline`, or `~/.config/intentline/config.yml`.
3. Project config: `.intentline/config.yml`.

Flags on a command override both files.

`intentline init` writes a project config that sets `schema_version` and comments the defaults. It does not copy every default into the file, so a user config is not silently overridden.

## Project file

```yaml
schema_version: 1
check:
  enabled: false
  min_lines: 30
  ignore:
    - "uv.lock"
    - "package-lock.json"
    - "pnpm-lock.yaml"
    - "*.lock"
    - ".intentline/**"
    - "schema/**"
    - "*generated*"
hooks:
  trailer: true
  check: false
capture:
  default_author_name: null
```

| Key | Meaning |
|---|---|
| `check.min_lines` | Line count at which `intentline check` requires a record. Default 30. |
| `check.ignore` | Shell patterns. `*` also matches `/`, so `.intentline/**` covers that tree. A pattern with no `/` also matches the file name in any directory. |
| `check.enabled` | Reserved for turning the check on in config. The pre-commit hook uses `hooks.check`. |
| `hooks.trailer` | The prepare-commit-msg behavior. The installed hook is what actually writes the trailer. |
| `hooks.check` | `intentline install-hooks --check` sets this to true. The pre-commit hook runs only when it is true. |
| `capture.default_author_name` | Used when `capture` is not given `--author-name`. |

`--force` on `intentline init` replaces `config.yml` with the defaults. Records are not touched.

## User file

Same shape, at `~/.config/intentline/config.yml`. Use it for your name:

```yaml
schema_version: 1
capture:
  default_author_name: Ada
```

A project value for the same key wins.

## A corrupt config

Exit code 4. The message names the file. Fix the YAML, or run `intentline init --force` to reset the project config. That does not delete records.
