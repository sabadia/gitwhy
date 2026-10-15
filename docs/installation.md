# Installation

Intentline is a local command-line tool. The core commands do not call the network, and they do not need an account or an API key.

Python 3.12 or newer is required. [uv](https://docs.astral.sh/uv/) is the supported installer.

## From PyPI

```sh
uv tool install intentline
intentline version
```

`intentline version` prints the installed version and exits 0.

## From git

```sh
uv tool install git+https://github.com/sabadia/intentline
```

Use this when you want a commit that is not on PyPI yet.

## MCP extra

The recall and capture commands do not need MCP. Install the extra only if a coding agent will talk to the local stdio server:

```sh
uv tool install 'intentline[mcp]'
```

That adds the `intentline-mcp` command. See [Coding agents](agents.md).

## Upgrade

```sh
uv tool upgrade intentline
```

A repository written by a newer Intentline is refused with exit code 6 and an upgrade hint. Intentline does not guess at a schema it does not know.

## Uninstall

```sh
uv tool uninstall intentline
```

Records already committed in a repository stay there. They are ordinary YAML files.

## Check the install

```sh
intentline version
intentline --help
intentline schema
```

`intentline schema` prints the JSON Schema for a record (draft 2020-12). The same schema is in `schema/record.schema.json` in this repository.
