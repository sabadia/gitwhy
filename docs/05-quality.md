# 05 — Quality, testing, security

**Product:** Whyline  
A change is not done until this bar is met. "100% successful delivery" here means: every acceptance criterion has an automated test, CI is green, and the failure modes in the architecture doc have a test each.

## 1. Test pyramid

| Layer | Where | What | Required |
|---|---|---|---|
| Unit | `tests/unit/` | Models, store, trailer parsing, check decision, error mapping | Yes, for every module |
| Integration | `tests/integration/` | Real git repos in `tmp_path`. Capture, commit, hook, why | Yes, for every user flow |
| Schema | `tests/unit/test_schema.py` | Example YAML validates; generated JSON Schema matches committed file | Yes |
| Hook | `tests/integration/test_hooks.py` | Install, idempotent reinstall, refuse foreign hook, uninstall leaves user lines | Yes |
| CLI | `tests/integration/test_cli.py` | Typer `CliRunner` or subprocess of the installed script | Yes |
| Bench | `tests/bench/` | 1,000-record timing, Phase 4 only | Not a CI gate |

No E2E against GitHub in CI. GitHub operations are tested manually in Phase 0 and recorded in the issue.

Coverage target: 90% line coverage on `src/whyline`, 100% on `models.py`, `store.py`, `check.py`, and the affirm gate. Enforce with `pytest-cov` and a `--cov-fail-under=90` in CI once Phase 2 is done. Before that, do not fail CI on coverage; do not lower the target later.

## 2. Required tests (do not skip)

These map to failure modes. Each needs a named test.

| Test | Expect |
|---|---|
| Capture in a non-repo | Exit 2, nothing written |
| Init twice | Second is no-op, config unchanged |
| Init `--force` | Overwrites config, does not delete records |
| Record with `../etc/passwd` link | Validation error |
| Affirmed record missing affirmed_at | Validation error |
| Draft with affirmed_at set | Validation error |
| Schema version 99 | Exit 6 |
| Corrupt YAML on list | Warning, other records still listed |
| Corrupt YAML on show | Exit 4 |
| Session file with prose that looks like a rejected alternative | rejected stays empty |
| Affirm with non-TTY and no `--i-am-human` | Exit 8 |
| Affirm with `--i-am-human` and non-TTY | Success |
| link `--amend-head` when commit is on a remote | Exit 7 |
| install-hooks when a foreign prepare-commit-msg exists | Exit 5, file unchanged |
| install-hooks twice | One managed block |
| uninstall-hooks | Managed block gone, user lines remain |
| check under min_lines | Exit 0 |
| check over min_lines, no record | Exit 3 |
| check over min_lines, pending id | Exit 0 |
| why file:line after commit with trailer | Prints goal and DRAFT or AFFIRMED banner |
| why unknown file | Exit 9 or empty result with exit 0 — pick empty result with exit 0, document it, test it |
| Stop-hook exits 0 when whyline or the session file is missing | Exit 0, no record written |
| MCP server does not expose affirm | Tool list has no affirm |
| MCP capture then why in a temp repo | Draft written, why returns it, banner would say DRAFT |
| install-agent twice | One skill copy, one AGENTS.md block |
| uninstall-agent | Managed blocks gone, user text in AGENTS.md remains |
| Skill frontmatter | `name: whyline`, description mentions when to use it |
| Extra unknown key on read of an old file | Preserved on round-trip |

## 3. Tooling

- pytest with `tmp_path` for every filesystem test. No tests write to the developer’s real home. Monkeypatch `WHYLINE_CONFIG_HOME` or pass an explicit config path.
- ruff for lint and format. Line length 100. Target `py312`.
- mypy `strict = true`. No untyped defs. Pydantic plugin enabled if it still helps on v2; verify against current pydantic docs.
- No `nox` unless needed. `uv run` is the interface.
- pre-commit optional. CI is the gate. A `Makefile` or justfile is unnecessary; document `uv run pytest` in CONTRIBUTING.

## 4. CI

`.github/workflows/ci.yml`:

- Triggers: push to `main`, pull_request.
- Matrix: Python 3.12, 3.13.
- Steps: checkout, install uv, `uv sync --all-groups`, ruff check, ruff format --check, mypy, pytest with cov.
- No deploy step.
- Dependabot or Renovate: not required for v1. A chore issue may add it later.

## 5. Security and privacy

Threat model for a local CLI:

| Threat | Mitigation |
|---|---|
| Tool invents a reason and a team treats it as fact | Draft/affirmed split. Banner on every human render. Affirm gate. Session capture fills only goal. |
| Record contains a secret the user pasted | Document in README: records are committed; do not put secrets in goals. No automatic scanning in v1 (a later issue). Do not add a network secret scanner. |
| Hook exfiltrates the diff | Hooks are local scripts we install. They call only `whyline` or `git`. Review the hook template in the PR. No curl, no wget. |
| Affirm forged by an agent | Non-TTY refusal. `--i-am-human` is an explicit override, documented as "you are lying if you are not". |
| Path traversal via links | Reject absolute and `..`. |
| Amend of published history | Refuse amend if the commit is on a remote. |
| Supply chain | Pin via `uv.lock`. CI uses the lockfile. License Apache-2.0. No postinstall network. |
| Telemetry | None in v1. Do not add. |

No authentication, no cryptography, no PII store. The user's git config name may be copied into `affirmed_by`. That is local and expected.

## 6. Documentation bar

- README: what it is, install, 60-second quickstart, principles, exit codes pointer, license.
- `--help` is the man page. Keep it accurate.
- `docs/` stays the spec. When behavior changes, change the spec in the same PR.
- CHANGELOG: Keep a Changelog, `[Unreleased]` until 0.1.0.

## 7. Definition of done (release)

v0.1.0 may be tagged only when:

- [ ] Phases 0–4 exit criteria are Done on the board
- [ ] CI green on `main`
- [ ] Coverage at or above the target
- [ ] README quickstart was run by the agent in a clean temp dir and the transcript is in the release issue
- [ ] No network calls in core (a test or a code comment plus grep in CI for `httpx|requests|urllib.request` in `src/whyline` excluding adapters — adapters also must not)
- [ ] CHANGELOG has the 0.1.0 section
- [ ] User has said the tag may be pushed

Do not publish to PyPI until the user explicitly says to.

## 8. Corner cases checklist

Handle these in code or document them as accepted limits in the README:

- Detached HEAD: capture works; link writes pending; amend-head refuses.
- Merge commit: trailer still works; why uses the commit that blamed the line.
- Shallow clone: why may miss older records; print a hint if `git rev-parse --is-shallow-repository` is true.
- Submodules: operate on the repo you are in, not the parent. Document it.
- Windows paths: use pathlib; test is best-effort (CI is Ubuntu). Do not use slash concatenation.
- Filename with spaces: quote in hook scripts.
- Concurrent capture: last write wins; ids do not collide (UUIDv7). Acceptable for v1.
- Record for a deleted file: `why` on the old path may fail; `show <id>` still works. Document it.
- Binary files in the diff: ignore for line links; do not crash.
- Empty repo (no commits): init and capture work; why exits cleanly with "no commits yet".
