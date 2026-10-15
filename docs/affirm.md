# Affirm

Affirming is a human saying "this is the reason." A draft becomes `affirmed`. Agents must not affirm. There is no affirm tool in MCP, and the skill tells an agent not to run this command.

## On a terminal

```sh
intentline affirm 01a140e8-0625-7520-aa95-3b4867799050
```

`affirmed_by` defaults to `git config user.name`. Override it:

```sh
intentline affirm 01a140e8-0625-7520-aa95-3b4867799050 --by "Ada Lovelace"
```

If `rejected`, `assumptions`, `falsifier`, or another narrative field is empty, Intentline lists those fields and asks `Affirm anyway?`. Answering no writes nothing and exits 1. Intentline never fills the empty fields for you.

Skip that question when you have already decided the empty fields are acceptable:

```sh
intentline affirm 01a140e8-0625-7520-aa95-3b4867799050 --yes
```

`--yes` does not skip the human gate.

## From a non-interactive shell

A script, CI job, or agent has no terminal. Affirm is refused with exit code 8.

A human who is intentionally affirming from a script passes:

```sh
intentline affirm 01a140e8-0625-7520-aa95-3b4867799050 --i-am-human --yes
```

Pass `--i-am-human` only if you are a human. An agent that passes it is misrepresenting itself.

## Capture and affirm together

```sh
intentline capture --goal "Close invoices once a day." --file src/app.py --affirm
```

This uses the same human gate. If the gate refuses, nothing is written.

## Already affirmed

Running affirm again prints who affirmed it and when, and does not change the file.

## What changes in the file

`status` becomes `affirmed`. `affirmed_at` is the current UTC time. `affirmed_by` is the name above. `updated_at` moves forward. The goal and the other narrative fields stay as they were.

## Errors

| Exit | When |
|---|---|
| 1 | Bad input, or you declined the empty-field question. |
| 2 | Not an initialized repository. |
| 4 | The record is corrupt. |
| 8 | The human gate refused. |
| 9 | Unknown id. |

`--json` prints the record after a successful affirm.

After you affirm, commit the updated YAML file so other clones see the confirmed reason.
