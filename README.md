# cline-sdlc

`cline-sdlc` is a Python command-line orchestrator for bounded, Cline-assisted
software-development lifecycle stages. Each invocation accepts one rough idea or
repository artifact, coordinates only the stage selected by that input, and stops at
the next major artifact boundary.

The project uses repository-visible Markdown artifacts and Git history as workflow
state. Structured session outcomes, validation evidence, and Git reconciliation—not
assistant prose—determine whether work completed.

> [!IMPORTANT]
> The project is **not currently described as unattended-ready**. The supervised
> Cline CLI capability proof found blocking gaps in structured outcomes, pre-execution
> permission mediation, and interruption evidence. ADR 0001 records the accepted
> supervised workflow-runner boundary and the still-blocked unattended-readiness claim.
> A successful supervised rollout proof or superseding execution-boundary ADR is still
> required before changing this status.
>
> The installed console boundary currently validates inputs and renders the bounded
> dry-run terminal result; it does not yet compose the implemented lifecycle use cases
> into real Cline execution. The stage descriptions below document the application
> contract and operator model being prepared for rollout, not a claim that real Cline
> execution is production-ready through the current entry point.

## Requirements

- Python 3.14 or newer
- [uv](https://docs.astral.sh/uv/), including `uvx`
- Git for every file-backed stage and in-repository artifact write
- A separately installed compatible Cline CLI for real lifecycle sessions
- Node.js 22 or newer for the experimental adapter-local `@cline/sdk` runner
- The stage-specific Agent Skills required by the selected workflow

## Install and run

Run the console entry point directly from a local checkout:

```bash
uvx --from . cline-sdlc --help
```

For development, install the application and development dependencies from the
locked project state:

```bash
uv sync --frozen --all-groups
uv run cline-sdlc --help
```

Show the installed package version with:

```bash
uvx --from . cline-sdlc --version
```

## Lifecycle inputs and boundaries

Exactly one input is required. The explicit option selects the stage; file content is
not guessed to override that selection.

| Input | Stage | Required stopping boundary | Interaction |
| --- | --- | --- | --- |
| `--idea` | Idea refinement | Accepted idea brief | Live user session |
| `--idea-file` | Specification creation | Accepted specification | Live user session |
| `--spec-file` | Plan creation and independent review | Ready plan or explicit blocker | Unattended unless blocked |
| `--plan-file` | Serial plan implementation | Complete plan or explicit blocker | Unattended within approved material |

The orchestrator does not automatically cascade into the next major stage.

### Refine a rough idea

```bash
uvx --from . cline-sdlc --idea "Add a safe repository cleanup workflow"
```

The session must use the idea-refinement procedure, obtain explicit acceptance, and
save exactly one accepted idea brief. It does not create a specification.

### Create a specification from an idea artifact

```bash
uvx --from . cline-sdlc --idea-file docs/ideas/repository-cleanup.md
```

The input must pass file and Git preflight. The interactive session must obtain
explicit acceptance and save one specification. It does not author a plan.

### Author and review a plan from a specification

```bash
uvx --from . cline-sdlc --spec-file docs/specs/repository-cleanup-spec.md
```

The orchestrator uses separate fresh author and read-only reviewer contexts. It stops
with a review-ready plan or a bounded blocker and does not begin implementation.

### Implement a ready plan

```bash
uvx --from . cline-sdlc --plan-file docs/plans/repository-cleanup-plan.md
```

Invoking `--plan-file` approves the plan's exact current specification and material
digests for that invocation. Remaining dependency-ready slices run serially in fresh
contexts. Each successful slice is independently reconciled, validated, explicitly
staged, and committed locally before later work starts. Final broad validation,
read-only review, bounded remediation, and a progress-only finalization commit follow.

## Options and defaults

| Option | Meaning | Default |
| --- | --- | --- |
| `--timeout <seconds>` | Finite maximum duration for one Cline session | `1800` seconds (30 minutes) |
| `--cline-command <path>` | Explicit Cline executable used for capability checks and sessions | `cline` |
| `--json` | Emit only one terminal JSON result on standard output | Disabled |
| `--verbose` | Emit additional subprocess and reconciliation diagnostics | Disabled |
| `--dry-run` | Preview the bounded invocation without starting lifecycle work | Disabled |
| `--version` | Print the orchestrator version and exit | — |
| `-h`, `--help` | Print command usage and exit | — |

Timeout values must be finite positive seconds. File paths are resolved from the
current working directory unless absolute.

## Terminal results and exit categories

Every lifecycle invocation ends with one versioned terminal result. In normal mode it
may follow a concise human diagnostic. With `--json`, it is the only standard-output
content.

```bash
uvx --from . cline-sdlc --plan-file docs/plans/example-plan.md --json
```

Example shape:

```json
{
  "schema_version": 1,
  "status": "completed",
  "stage": "plan_implementation",
  "reason": "plan_complete",
  "input_path": "docs/plans/example-plan.md",
  "output_paths": ["docs/plans/example-plan.md"],
  "specification_digest": "sha256:<hex>",
  "plan_material_digest": "sha256:<hex>",
  "blocker": null
}
```

| Exit code | Category | Meaning |
| --- | --- | --- |
| `0` | `completed` | The selected stage reached its required boundary. |
| `2` | `usage_error` | Input or command syntax is invalid. |
| `3` | `preflight_failed` | Runtime, Cline, skill, Git, or artifact prerequisites failed. |
| `4` | `blocked` | Human clarification, approval, or manual reconciliation is required. |
| `5` | `stage_failed` | A bounded stage, review, validation, or repair attempt failed. |
| `6` | `interrupted` | The process or Cline session was interrupted or timed out safely. |
| `7` | `internal_error` | The orchestrator encountered an unexpected invariant failure. |

The terminal JSON `reason` and optional `blocker` provide a more specific diagnosis
without creating a new process exit code for every failure.

## Repository and artifact safety

File-backed stages require a valid Git repository and resolvable `HEAD`. Inputs must
be readable regular files, tracked, committed at `HEAD`, and unchanged from their
committed content. Artifact-writing stages start from a clean working tree except for
a safely reconciled partial implementation or finalization transaction.

Automated implementation is denied on detached `HEAD` and protected branch defaults:

- `main`
- `master`
- `trunk`
- `production`
- `release`
- `release/*`

Protected-branch customization is an explicit host configuration decision outside an
unattended session. The current CLI does not expose an environment-backed override.

Implementation commits stage explicit reconciled paths rather than the entire working
tree. Run logs, secrets, unrelated changes, and work from another slice are excluded.
The orchestrator never pushes, opens pull requests, publishes, releases, or deploys.

Idea, specification, and plan-authoring stages leave accepted artifacts uncommitted for
human review. Commit those artifacts before using them as the input to the next
file-backed stage. Only plan implementation creates local commits automatically.

## Balanced operation permissions

The balanced profile classifies executable and argument arrays and fails closed when a
request cannot be classified confidently.

Automatically permitted operations include:

- read-only repository and file inspection;
- in-scope workspace writes required by the accepted slice;
- repository-defined formatting, linting, type checking, tests, and builds;
- non-interactive Git inspection;
- explicit local slice and finalization commits after reconciliation;
- writes to the ignored run-audit directory.

An accepted current plan slice may additionally authorize a specifically classifiable
local dependency change or bounded network operation. Dependency changes must own both
`pyproject.toml` and `uv.lock`. The accepted plan is not blanket authorization: the
executable, arguments, operation class, and destination must still match the recorded
requirement.

The orchestrator stops for unplanned dependency or network access, credentials,
production data, destructive or system operations, remote publication, deployment,
history rewriting, hook bypass, material plan changes, or any operation whose risk is
unclear. It never treats arbitrary shell text or model output as permission.

## Run logs and redaction

Repository-backed runs store versioned summaries under:

```text
.cline-sdlc/runs/<run-id>/summary.json
```

Plan implementation also stores the immutable invocation approval in the same ignored
run directory. The `.cline-sdlc/` rule is established before sensitive run records are
written, and these files are never candidate commit paths.

Summaries record safe operational events, attempts, classifications, reconciliation
decisions, and terminal status. Known tokens, credentials, bearer values, and explicit
sensitive fragments are redacted. Complete prompts, raw model reasoning, secrets, and
raw repository payloads are not normal terminal or summary content.

## Blockers, interruption, and recovery

The runner stops rather than guessing when preflight, permission, artifact, validation,
digest, changed-path, or Git ownership evidence is unsafe or ambiguous. Terminal
blockers contain an actionable code and summary; detailed sensitive diagnostics remain
in the ignored run directory.

On timeout, `SIGINT`, or `SIGTERM`, the runner stops launching work, terminates the
active child within a bounded grace period, reconciles observable paths, records safe
recovery state, creates no commit, and returns exit code `6`.

If a slice or commit fails after attributable writes, the plan records the current
slice, start commit, changed paths, validation evidence, blocker, and summary location
when safe. A later process must reconcile the exact `HEAD`, dirty paths, approved
digests, and owning commit evidence, then resume that partial slice before selecting new
work. Conflicting or unrelated changes require manual reconciliation.

A plan already marked complete is a no-op only when its state, digests, and unique
reachable finalization commit all agree. Verification then starts no Cline session and
creates no commit.

## Configuration

`cline-sdlc` currently has **no environment-backed runtime settings** and requires no
`.env` file. Runtime choices are explicit CLI options, accepted artifact content, or
application defaults. Consequently, this version does not maintain an `.env.example`
or a separate environment-settings reference.

## Experimental Cline SDK adapter foundation

The SDK-first execution boundary is being introduced behind the `cline_execution`
outbound adapter boundary. The adapter-local Node.js package lives under:

```text
src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/
```

Install its local Node dependencies from that directory, not globally:

```bash
cd src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner
npm ci
```

The package declares a Node.js `>=22` engine and depends on `@cline/sdk` through the
adapter-local `package.json` and `package-lock.json`. Generated `node_modules/`
content is ignored and must not be committed.

This foundation only proves the local dependency strategy and structured runtime
preflight blockers for missing Node.js, unsupported Node.js, or an unresolvable
`@cline/sdk` package. It does not yet prove SDK-backed lifecycle execution, Plan/Act
mediation, permission handling, or unattended readiness.

## Current limitations and supervised proof

The default automated suite uses fake Cline executables and disposable Git repositories;
it does not require credentials, network access, or real lifecycle effects. Real
Cline execution remains limited by unproven machine-detectable terminal outcomes,
pre-execution permission mediation, and interruption recovery evidence.

The project must not be represented as unattended-ready until a supervised
non-production rollout proof demonstrates those contracts or a superseding
execution-boundary ADR replaces the current Cline CLI boundary. See
[`docs/adr/0001-keep-cline-cli-rollout-blocked-until-execution-contracts-are-proven.md`](docs/adr/0001-keep-cline-cli-rollout-blocked-until-execution-contracts-are-proven.md).

## Development

Run the full local quality gate before handoff:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy .
uv run pytest
uv build
uvx --from . cline-sdlc --help
git --no-pager diff --check
```

Install optional Git pre-commit hooks with:

```bash
uv run pre-commit install
```

## Architecture

The source uses a `src/` layout with feature-owned vertical slices and hexagonal
boundaries:

```text
src/cline_sdlc/
├── bootstrap/          # composition root and console startup
├── features/           # business capabilities owned end to end
└── shared_kernel/      # genuinely shared pure domain values
```

Each feature keeps domain behavior, application ports/use cases/DTOs, and external
adapters separate. Dependencies point inward; framework, filesystem, subprocess, Git,
clock, and terminal effects remain behind application-owned boundaries.

The normative behavior contract is
[`docs/specs/cline-sdlc-orchestrator-spec.md`](docs/specs/cline-sdlc-orchestrator-spec.md).
