# Spec: Cline SDLC Orchestrator

## Status

- Artifact type: product and behavior specification
- Date: 2026-07-23
- Source brief: `docs/ideas/cline-sdlc-orchestrator.md`
- Decision state: draft for review and acceptance
- Intended scope: portable standalone Cline tooling

## Objective

Build a standalone Python 3 command-line application that coordinates one
bounded software development lifecycle stage per invocation through Cline CLI.
The application must accept one rough idea or one repository artifact, invoke
the existing stage-specific Agent Skills in controlled Cline sessions, persist
durable progress in human-reviewable repository artifacts, and stop at the next
major artifact boundary.

The application is for engineers who want to reduce manual coordination between
idea refinement, specification, planning, plan review, and incremental
implementation without surrendering approval at major lifecycle or risk
boundaries.

The package must be installable and runnable as a Python CLI through `uvx`.
This specification calls the executable `cline-sdlc`; the final package name may
differ only if the implementation plan records the reason and preserves an
equivalent console entry point.

## Current context

Focused Agent Skills already define the detailed procedures for idea refinement,
specification, planning, plan review, incremental implementation, testing, and
quality gates. The missing capability is a durable lifecycle contract around
those skills: input selection, subprocess coordination, approval policy, review
limits, structured outcomes, Git safety, failure recovery, and resumption.

Cline CLI is the execution engine for the MVP. The orchestrator owns process and
state coordination but does not replace Cline, reproduce specialist skill
instructions, or interpret free-form prose as authoritative completion state.

Repository-visible Markdown artifacts are the portable source of truth. Cline
session identifiers, CLI event logs, and Checkpoints may support diagnosis and
recovery but do not establish lifecycle phase, plan readiness, approval, or
completed work.

## Assumptions

1. The host workspace is a local Git repository.
2. Cline CLI provides non-interactive invocation, structured event output,
   bounded timeouts, and isolated or resumable sessions needed by this spec.
3. The required stage skills are installed or discoverable by each Cline
   session.
4. Markdown artifacts can contain a fenced YAML state block that is readable by
   humans and parsed safely by the orchestrator.
5. A fresh Cline session can produce the structured terminal outcome defined in
   this specification.
6. The initial release supports one balanced approval profile and local commits
   only.
7. The application may depend on Git, `uvx`, Python, and Cline CLI, but must not
   require this repository's directory layout or maintenance tooling when used
   in another repository.

If assumptions 2, 4, or 5 fail during a proof of concept, implementation must
stop for a product decision rather than weakening the state, outcome, or safety
contracts silently. An SDK-based orchestrator is the preferred fallback when
CLI orchestration cannot enforce these contracts reliably.

## Product boundaries

### In scope

- one `cline-sdlc` entry point runnable through `uvx`;
- rough-idea, idea-file, specification-file, and implementation-plan-file inputs;
- exactly one major lifecycle stage per invocation;
- direct attachment to interactive idea and specification sessions;
- unattended specification-to-plan authoring and bounded independent review;
- serial, fresh-session implementation of plan slices;
- repository-specific validation discovery and execution;
- one local atomic commit for each successful implementation or remediation
  slice;
- final fresh-context review and repository-wide quality gate;
- versioned state embedded in the implementation plan;
- structured Cline session outcomes;
- balanced approval, permission, Git, and recovery policy;
- machine-readable terminal CLI results and actionable human diagnostics.

### Out of scope

- automatic cascading across two or more major lifecycle stages;
- Cline SDK or Agent Team orchestration;
- Ritebook or other product-specific integration;
- pushes, pull requests, issue updates, releases, publication, or deployment;
- concurrent implementation sessions or concurrent repository writers;
- database-backed workflow state;
- arbitrary approval profiles;
- automatic dependency installation or network access;
- fully unattended execution in an untrusted workspace;
- mandatory architecture, language, test framework, or artifact directory
  conventions in host repositories;
- using Cline Checkpoints as authoritative workflow state.

## Terminology

- **Major stage**: one of idea refinement, specification creation, plan creation
  and review, or plan implementation.
- **Artifact boundary**: the accepted or ready artifact at which an invocation
  must stop.
- **Material plan content**: specification-derived scope, acceptance criteria,
  contracts, architecture, dependencies, risks, sequencing, and slice
  definitions that determine what execution is authorized.
- **Progress content**: execution state, checkboxes, timestamps, validation
  evidence, commit identifiers, blockers, and implementation notes that report
  work without changing its authorized meaning.
- **Plan material digest**: a SHA-256 digest of canonical material plan content,
  excluding progress content and the digest field itself.
- **Invocation approval**: approval created when a user deliberately invokes the
  implementation stage with a ready plan whose current material digest is known.
- **Remediation envelope**: the part of invocation approval that permits one
  bounded correction attempt for a final-review finding proving non-conformance
  with already approved material requirements.
- **Slice**: the smallest plan unit implemented, validated, and committed as one
  transaction.
- **Partial slice**: uncommitted work left by an interrupted or failed slice and
  recorded in plan state for exclusive resumption.
- **Protected branch**: a branch on which automated implementation and commits
  are prohibited by default.

## Command-line interface

### Invocation

The executable must provide these mutually exclusive input forms:

```text
cline-sdlc --idea "<rough idea>"
cline-sdlc --idea-file <path>
cline-sdlc --spec-file <path>
cline-sdlc --plan-file <path>
```

The package must support an equivalent `uvx` invocation:

```text
uvx <package-name> --idea "<rough idea>"
uvx <package-name> --idea-file <path>
uvx <package-name> --spec-file <path>
uvx <package-name> --plan-file <path>
```

Exactly one input option is required. Empty rough ideas, missing files,
directories where files are required, unreadable files, unsupported artifact
versions, and multiple input options are usage errors and must not start Cline.

Paths are interpreted relative to the current working directory unless absolute.
The orchestrator must normalize paths for comparison and reporting without
requiring artifacts to use a repository-specific default directory.

### Common options

The MVP must support:

```text
--timeout <duration>       Maximum duration for one Cline session.
--cline-command <path>    Explicit Cline CLI executable for capability testing.
--json                    Emit only the terminal result as JSON on stdout.
--verbose                 Emit subprocess and reconciliation diagnostics.
--version                 Print orchestrator version and exit.
--help                    Print usage and exit.
```

Defaults must be documented by the application. A timeout must be finite. The
implementation plan must select a default no longer than 60 minutes per session.
Secrets, complete prompts containing sensitive repository content, and raw model
reasoning must not be printed by default.

### Process exit codes

The CLI must use stable process exit categories:

| Code | Category         | Meaning                                                                    |
| ---- | ---------------- | -------------------------------------------------------------------------- |
| 0    | completed        | The selected stage reached its required artifact boundary.                 |
| 2    | usage_error      | Input or command syntax is invalid.                                        |
| 3    | preflight_failed | Runtime, Cline, skill, Git, or artifact prerequisites failed.              |
| 4    | blocked          | Human clarification, approval, or manual reconciliation is required.       |
| 5    | stage_failed     | A bounded stage, review, validation, or repair attempt failed.             |
| 6    | interrupted      | The process or Cline session was interrupted or timed out safely.          |
| 7    | internal_error   | The orchestrator violated an invariant or encountered an unexpected error. |

The terminal JSON result must distinguish more specific reasons without adding a
new exit code for every failure.

### Terminal result

Every invocation must finish with one structured result. In normal mode it may
follow concise human output; in `--json` mode it is the only stdout content.

```json
{
  "schema_version": 1,
  "status": "completed",
  "stage": "plan_implementation",
  "reason": "plan_complete",
  "input_path": "docs/plans/example-plan.md",
  "output_paths": ["docs/plans/example-plan.md"],
  "plan_material_digest": "sha256:<hex>",
  "blocker": null
}
```

Allowed terminal statuses and exit categories map as follows:

| Terminal status                  | Exit category      |
| -------------------------------- | ------------------ |
| `completed`                      | `completed`        |
| `invalid_invocation`             | `usage_error`      |
| `preflight_failed`               | `preflight_failed` |
| `blocked` or `approval_required` | `blocked`          |
| `failed`                         | `stage_failed`     |
| `interrupted`                    | `interrupted`      |
| `internal_error`                 | `internal_error`   |

Unknown fields may be added compatibly; consumers must not be required to infer
success from prose. The terminal result schema must reject unknown status values.

## Preflight requirements

Before starting any Cline session, the orchestrator must:

1. verify its supported Python runtime;
2. locate and execute a non-interactive Cline CLI capability or version check;
3. verify required CLI capabilities rather than accepting an untested version
   string alone;
4. verify the input and artifact schema appropriate to the selected stage;
5. locate the Git repository root when the stage can modify repository files;
6. inspect branch, HEAD, and working-tree state;
7. detect an in-progress Git merge, rebase, cherry-pick, or bisect;
8. verify required stage skills are available to the session, or require the
   session to report a structured `required_context_unavailable` blocker;
9. establish a workspace-local run-log directory excluded from commits when the
   host repository has no suitable convention;
10. record the stage, input identity, starting commit, and orchestrator version.

Preflight failure must not modify lifecycle artifacts or start a stage session.
Rough-idea processing may run outside Git only when its resulting artifact is
saved outside a repository. All file-based stages and all in-repository artifact
writes require Git for the MVP.

Every artifact-writing stage requires a clean working tree at session start. The
only dirty-tree exception is a plan implementation invocation that reconciles an
existing partial slice or partial finalization transaction under the recovery
rules. Every file input used in Git must be tracked, committed at `HEAD`, and
identical to its committed content at invocation start. Interactive stages must
save their accepted artifact before completion but do not create a Git commit.
Plan authoring and review likewise leave the ready or blocked plan and findings
uncommitted for human review. Before invoking the next file-based stage, the user
must review and commit the input artifact and any referenced findings. Only plan
implementation creates commits automatically in the MVP.

## Lifecycle stage selection

The input determines the stage; content guessing must not override an explicit
input option.

| Input         | Stage                    | Required boundary                      | Interaction                      |
| ------------- | ------------------------ | -------------------------------------- | -------------------------------- |
| `--idea`      | idea refinement          | accepted idea brief                    | live user session                |
| `--idea-file` | specification creation   | accepted specification                 | live user session                |
| `--spec-file` | plan creation and review | ready implementation plan and findings | unattended unless blocked        |
| `--plan-file` | plan implementation      | complete plan or explicit blocker      | unattended within approved scope |

After reaching the boundary, the process must stop. It must not invoke the next
major stage even if the next artifact path is known.

## Stage requirements

### Rough idea to accepted idea brief

The orchestrator must start one interactive Cline session, attach the user's
terminal to it, provide the rough idea, and require use of the `idea-refine`
procedure. The session must not create a specification or implementation plan.

The stage completes only when:

- the user has explicitly accepted the refined direction in the live session;
- an idea brief has been written to a user-confirmed or host-conventional path;
- the brief identifies the problem, recommended direction, assumptions to test,
  MVP scope, exclusions with reasons, and open questions;
- the session returns a valid `completed` outcome naming the idea artifact; and
- the orchestrator verifies the artifact exists and was changed by the session.

If the user does not accept a direction, ends the interview, or declines to save
the artifact, the stage is blocked rather than completed.

### Idea file to accepted specification

The orchestrator must start one interactive Cline session, attach the user's
terminal, provide the idea artifact, and require the
`spec-driven-development` procedure for specification only. The session may
inspect the host repository and interview the user. It must not create an
implementation plan or begin implementation.

The stage completes only when:

- the user explicitly accepts the specification in the live session;
- a specification artifact is written to a user-confirmed or host-conventional
  path;
- the specification defines objective, current context, desired behavior,
  boundaries, testing strategy, and testable success criteria;
- unresolved decisions that block planning are absent or explicitly mark the
  stage blocked;
- the session returns a valid `completed` outcome naming the specification; and
- the orchestrator verifies the artifact exists and was changed by the session.

### Specification to ready implementation plan

The orchestrator must use separate Cline sessions for plan authoring and review.
Routine user intervention is not required.

The author session must inspect the accepted specification, relevant repository
rules, existing implementation patterns, validation commands, and affected
files. It must produce a plan with ordered, dependency-aware, independently
verifiable slices and the state block defined by this specification.

The reviewer session must be fresh and read-only. Its prompt may include the
specification, proposed plan, relevant repository constraints and files, known
failure modes, and required findings schema. It must not include the author's
private reasoning or instruct the reviewer to confirm the author's conclusion.

Review follows this bounded loop:

1. author plan revision 1;
2. independently review revision 1;
3. if not ready, revise the plan in an author session;
4. re-review material changes in a new reviewer session;
5. perform at most two revision and re-review cycles after the initial review.

The stage completes when the latest review has readiness `ready`, all blocking
findings have accepted dispositions, the plan state records the latest revision
and review iteration, and the material digest matches current plan content.

If readiness is not achieved within the loop, the plan must be marked `blocked`
with unresolved findings and the invocation must stop. The orchestrator must not
waive findings, allow the author session to act as reviewer, or begin
implementation.

### Ready plan to completed implementation

Invoking `--plan-file` deliberately approves the exact current material digest
for the duration of that invocation. Preflight must reject a plan that is not
review-ready, has unresolved blocking findings, has an invalid state block, or
has a stored material digest that does not match canonical material content.

The orchestrator must then:

1. reconcile plan progress, Git history, and the working tree;
2. resume a valid partial slice before selecting other work;
3. otherwise select the earliest incomplete slice whose dependencies are
   complete;
4. start a fresh Cline session for that slice only;
5. require implementation, focused tests, validation, progress update, and a
   structured outcome;
6. independently verify the outcome against Git status and required evidence;
7. create one local atomic commit containing implementation, tests or
   documentation, validation evidence in the plan, and updated progress state,
   with machine-readable work and slice trailers;
8. repeat serially while the approved digest remains valid;
9. after all planned slices complete, run a final fresh-context read-only review
   and repository-wide quality gate;
10. create explicit progress-only remediation records for in-scope fixable
    findings within the invocation remediation envelope;
11. implement, validate, and commit remediation slices using the same rules;
12. after remediation, run one fresh read-only confirmation review and rerun
    affected broad checks;
13. create one finalization commit that marks the plan complete only when the
    latest final review has no unresolved blocking or major findings and the
    broad quality gate passes.

A plan already marked complete must be verified for schema and digest consistency
and then return `completed` without starting a Cline session or creating a commit.

## Implementation plan artifact

### Human-readable sections

The plan must contain, at minimum:

- objective and specification reference;
- scope and non-goals;
- relevant repository context and constraints;
- material decisions and risks;
- ordered tasks and slices with stable identifiers;
- dependencies, acceptance criteria, likely paths, and verification for each
  slice;
- plan-review findings or a link to their committed artifact;
- validation and implementation evidence;
- the versioned lifecycle state block.

Task and slice identifiers must remain stable across progress updates. Material
revision may add or supersede identifiers but must not silently reuse one for
different work.

### Embedded state block

The plan must contain exactly one fenced YAML block labelled
`cline-sdlc-state`. The MVP state schema is:

```cline-sdlc-state
schema_version: 1
work_id: example-work
profile: balanced
phase: ready
specification: docs/specs/example-spec.md
plan_revision: 2
review_iteration: 2
review_readiness: ready
material_digest: sha256:<hex>
current_task: null
current_slice: null
slice_start_commit: null
partial_slice_paths: []
completed_slices: []
remediation_records: []
validation_evidence: []
blocker: null
created_at: 2026-07-23T17:00:00Z
updated_at: 2026-07-23T17:00:00Z
completed_at: null
```

Required field rules:

- `schema_version` is the integer `1` for the MVP.
- `work_id` is a stable, non-empty kebab-case identifier within the repository.
- `profile` is `balanced`.
- `phase` is one of `drafting`, `reviewing`, `ready`, `implementing`, `blocked`,
  or `complete`.
- `specification` is a normalized repository-relative path to the accepted spec.
- `plan_revision` starts at 1 and increases for every material revision.
- `review_iteration` starts at 1 after initial review and is at most 3.
- `review_readiness` is `not_reviewed`, `changes_required`, `ready`, or `blocked`.
- `material_digest` uses `sha256:<lowercase hexadecimal>`.
- `current_task` and `current_slice` are null unless a slice is active or blocked.
- `slice_start_commit` is the full Git commit at which the current slice began.
- `partial_slice_paths` contains normalized repository-relative paths owned by an
  uncommitted partial slice. Directories must end in `/`; paths must not escape
  the repository.
- `completed_slices` is an ordered list of stable slice identifiers.
- `remediation_records` contains progress-only final-review correction records
  defined under final review and remediation.
- `validation_evidence` contains structured evidence records defined below.
- `blocker` is null or a structured blocker defined below.
- timestamps are UTC RFC 3339 values. `completed_at` is non-null only in phase
  `complete`.

Allowed phase transitions are `drafting -> reviewing`, `reviewing -> ready`,
`reviewing -> blocked`, `ready -> implementing`, `implementing -> blocked`,
`blocked -> implementing` after successful reconciliation, and
`implementing -> complete` through the finalization transaction. Material plan
revision resets phase to `reviewing`, clears invocation approval and active
progress fields, and requires review readiness to become `ready` again. Other
transitions are invalid in schema version 1.

The parser must reject duplicate YAML keys, aliases, custom tags, unexpected
types, path traversal, unknown required enum values, and unsupported schema
versions. Unknown top-level fields must be rejected in schema version 1 so stale
or misspelled state cannot be silently ignored.

### Material digest

The plan authoring format must identify material and progress sections
unambiguously. The implementation plan must choose one deterministic marker
syntax and test it. At minimum, material content includes objective, scope,
non-goals, acceptance criteria, decisions, contracts, dependencies, risks,
sequencing, task definitions, and slice definitions.

The following are progress-only when they do not alter material text:

- lifecycle state fields other than `plan_revision`, specification identity, and
  material digest algorithm/version;
- completion checkboxes;
- current task and slice;
- completed-slice and remediation records;
- validation evidence;
- timestamps;
- blocker and recovery notes;
- factual implementation notes tied to completed slices.

Canonicalization must normalize UTF-8 text and line endings, use a documented
stable section order, and exclude the stored digest value. Whitespace changes
inside material sections are material in the MVP. A changed material digest
ends inherited invocation approval and blocks further slices.

### Validation evidence

Each evidence record must include:

```yaml
- slice_id: slice-1.1
  command: python3 -m pytest tests/example_test.py
  result: passed
  exit_code: 0
  recorded_at: 2026-07-23T17:30:00Z
```

`result` is `passed`, `failed`, or `not_run`. Commands must be recorded without
secrets. A successful slice requires at least one focused verification result,
unless the plan explicitly defines a manual documentation-only check. Owning
commit identity is derived from Git trailers and the committed plan transition;
it must not be embedded in the commit that creates it.

### Blocker

A blocker must include:

```yaml
blocker:
  code: validation_failed
  summary: Focused tests still fail after the permitted repair attempt.
  slice_id: slice-1.1
  details_path: .cline-sdlc/runs/<run-id>/summary.json
  recorded_at: 2026-07-23T17:40:00Z
```

The summary must be safe to commit. Logs that may contain sensitive repository
content remain in the ignored run-log directory and are referenced, not embedded.

## Plan-review findings

Findings must be stored in the plan or a repository artifact referenced by it.
Each finding has this schema:

```yaml
- id: PLAN-001
  severity: blocking
  status: open
  summary: The migration rollback behavior is undefined.
  evidence: The specification requires rollback but slice 2 has no rollback step.
  required_correction: Add rollback implementation and verification to slice 2.
  affected_sections:
    - Slice 2
  disposition: null
```

Allowed severities are `blocking`, `major`, and `minor`. Allowed statuses are
`open`, `resolved`, `accepted_risk`, and `not_applicable`. A `blocking` finding
must be `resolved` or explicitly accepted by a human before readiness can be
`ready`. The unattended review loop may resolve findings through plan changes but
must not mark a blocking finding `accepted_risk` or `not_applicable` without
human intervention.

Finding identifiers remain stable through review iterations. A reviewer must
verify prior dispositions and may add new findings. Readiness is:

- `ready`: no open blocking or major findings and the plan can be executed
  without inventing material decisions;
- `changes_required`: correctable blocking or major findings remain within the
  review limit;
- `blocked`: the review limit is exhausted or human input is required.

## Structured Cline session protocol

### Session isolation

Every author, reviewer, implementation, final-review, and remediation session
must have a fresh Cline context. A failed partial slice may use a new session on
resume; repository artifacts and the recorded diff, not prior conversation, must
provide the recovery context.

Reviewer sessions are read-only. Implementation sessions receive only the
accepted specification, ready plan, current slice, necessary repository context,
permission policy, validation expectations, and outcome contract. They must not
be authorized to work on later slices.

### Terminal outcome envelope

Each Cline session must emit exactly one terminal outcome in a machine-detectable
channel or file. The orchestrator must not scrape ordinary assistant prose to
decide completion.

```json
{
  "schema_version": 1,
  "session_role": "implementation",
  "status": "completed",
  "reason": "slice_verified",
  "artifact_paths": ["docs/plans/example-plan.md"],
  "changed_paths": ["src/example.py", "tests/test_example.py"],
  "validation": [
    {
      "command": "python3 -m pytest tests/test_example.py",
      "exit_code": 0,
      "result": "passed"
    }
  ],
  "finding_ids": [],
  "risk": null,
  "blocker": null,
  "retryable": false
}
```

Allowed `session_role` values are `idea_refiner`, `spec_author`, `plan_author`,
`plan_reviewer`, `implementation`, and `final_reviewer`. Allowed statuses are:

- `completed`: the assigned bounded responsibility is complete;
- `blocked`: ambiguity, drift, missing context, or repeated failure requires
  human resolution;
- `approval_required`: a proposed operation exceeds the session's permission;
- `failed`: the responsibility did not complete but repository state is known;
- `invalid_output`: the session cannot satisfy the protocol.

The `reason` must be a stable snake-case identifier. `changed_paths` must match
repository-relative paths observed by Git after the session. A reviewer must
report an empty changed-path list. The orchestrator independently checks artifact
existence, changed paths, validation exit codes, and repository state before
accepting `completed`.

### Invalid, missing, and conflicting outcomes

Missing terminal outcomes, invalid JSON, unsupported schema versions, duplicate
outcomes, path traversal, reviewer writes, and outcomes contradicted by Git are
protocol failures. The orchestrator may make one fresh-session protocol retry
when no unsafe or ambiguous writes occurred. Otherwise it must record a blocker
and stop.

A timed-out or externally interrupted session must be terminated with a bounded
grace period. The orchestrator then inspects Git state, records any attributable
partial slice, emits `interrupted`, and stops. It must not start another slice.

## Permission boundaries

### Automatically allowed in the balanced profile

Within the current repository and assigned slice, the orchestrator may allow:

- read-only file and repository inspection;
- creation and modification of non-sensitive workspace files required by the
  accepted plan;
- creation of test fixtures that do not contain credentials or production data;
- local formatting, linting, static analysis, tests, and builds already defined
  by the repository;
- non-interactive Git status, diff, log, show, and branch inspection;
- the orchestrator's local slice commit after independent reconciliation;
- writes to the ignored run-log directory;
- progress-only updates to the implementation plan.

Commands must be executed without interactive prompts, pagers, or editors. The
implementation must use an explicit allow/deny classifier and command argument
inspection; prompt instructions alone are insufficient permission enforcement.

### Always stop for approval or manual action

The MVP must not automatically execute:

- network access, downloads, remote API calls, or package-index access;
- dependency addition, removal, upgrade, or lockfile regeneration caused by a
  dependency decision;
- credential, token, keychain, secret-store, or production-data access;
- destructive filesystem operations outside narrowly scoped generated files;
- database migrations against non-ephemeral data;
- privilege escalation or system configuration changes;
- pushes, pull requests, remote branch changes, publication, releases, signing,
  deployment, or external side effects;
- force operations, history rewriting, branch deletion, `git reset --hard`, or
  bypassing hooks;
- material plan changes;
- newly discovered architecture, schema, security, migration, dependency, or
  compatibility decisions;
- commands whose risk cannot be classified confidently.

An `approval_required` outcome must describe the exact proposed operation and
reason. For the MVP, approval does not resume that operation inside the same
unattended run. The invocation stops so the user can act manually or revise and
reapprove the plan.

### Never allowed

The orchestrator must never expose secrets in logs, commit run logs by default,
disable host security controls, execute remote content by piping it directly to
an interpreter, or interpret a model request as permission to exceed this
specification.

## Git safety and commits

### Initial requirements

Plan implementation requires:

- a valid Git repository with a resolvable HEAD;
- no merge, rebase, cherry-pick, revert, or bisect in progress;
- a named, non-detached branch;
- a branch not matching protected defaults `main`, `master`, `trunk`,
  `production`, `release`, or `release/*`;
- a clean working tree, except for a reconciled partial slice recorded by this
  plan;
- the plan and specification available in the working tree;
- no submodule or nested-repository changes unless explicitly included in the
  accepted plan and supported by a later specification revision.

Protected branch matching must be configurable, but weakening it is explicit
user configuration outside an unattended session.

### Slice reconciliation

Before a slice starts, record full `slice_start_commit`, current tree status, and
the expected path scope. After the session, compare the actual diff with the
session outcome and plan scope.

The orchestrator must stop without committing when:

- changed-path ownership is ambiguous;
- unrelated pre-existing changes appear;
- a changed path is outside the slice scope and cannot be justified by required
  generated output;
- the plan or specification has a material unapproved change;
- Git HEAD moved unexpectedly;
- validation evidence is missing or failed;
- prohibited operations were attempted.

### Atomic slice commits

After successful reconciliation, the orchestrator must stage explicit paths, not
the entire repository implicitly. One commit contains:

- implementation for exactly one slice;
- corresponding tests, documentation, or configuration;
- progress-only plan updates and validation evidence;
- no run logs, secrets, unrelated files, or changes from another slice.

Every slice commit must include these trailers:

```text
Cline-SDLC-Work-ID: <work-id>
Cline-SDLC-Slice-ID: <slice-id>
Cline-SDLC-Slice-Kind: implementation
Cline-SDLC-Material-Digest: sha256:<hex>
```

`Cline-SDLC-Slice-Kind` is `implementation` or `remediation`. The commit owning a
completed slice is the unique reachable commit whose trailers identify the work,
slice, kind, and approved digest and whose committed plan blob introduces that
completion transition. The orchestrator must reject missing, duplicate, or
conflicting owning commits. Persisted plan state must not contain a commit's own
object identifier.

The default commit message is:

```text
feat(sdlc): complete <slice-id> <short-description>
```

The type may be `fix`, `test`, `docs`, `refactor`, `build`, or `chore` when that
better represents the slice. Remediation commits use:

```text
fix(sdlc): remediate <finding-id> <short-description>
```

The commit must use non-interactive Git behavior and must not bypass hooks. A
hook failure is a slice failure. If commit creation fails, leave the verified
changes uncommitted, record the partial slice and blocker when possible, and
stop.

After all implementation and remediation work passes final review and the broad
quality gate, the orchestrator creates exactly one progress-only finalization
commit. It updates the plan to phase `complete`, records final evidence and
`completed_at`, and includes these trailers:

```text
Cline-SDLC-Work-ID: <work-id>
Cline-SDLC-Plan-Finalization: true
Cline-SDLC-Material-Digest: sha256:<hex>
```

The finalization commit is not a slice and is not subject to the one-commit-per-
slice count. If finalization fails, the plan remains not complete and the
verified progress-only change is left recoverable under the same reconciliation
principles. A partial finalization uses reserved `current_task: finalization` and
`current_slice: finalization`, records the pre-finalization HEAD in
`slice_start_commit`, and lists only the plan and any adjacent findings artifact
in `partial_slice_paths`.
Phase `complete` is authoritative only when one unique finalization commit is
reachable from `HEAD`, its committed plan blob introduces the complete
transition, and the current plan preserves that completed state and material
digest. Later unrelated commits may move `HEAD` without invalidating completion.
A complete-looking uncommitted plan is a partial finalization, not a completed
plan. A complete-plan no-op verifies the unique reachable finalization commit as
well as current state and digest consistency.

## Failure handling and recovery

### Attempt limits

- Plan review permits the initial review plus at most two revision/re-review
  cycles.
- A malformed session outcome permits at most one fresh-session retry when no
  ambiguous write exists.
- A failing focused validation permits at most one automatic repair attempt in
  the same bounded slice session contract.
- Final-review remediation may address each accepted in-scope finding once; a
  repeated finding or failed remediation blocks completion.
- Process startup failures may be retried once only when repository state is
  unchanged and the failure is classified as transient.

Limits are per invocation and must be visible in logs and terminal results.

### Partial-slice recording

When an implementation or commit fails after attributable writes, the
orchestrator must leave changes uncommitted and record, when safely possible:

- current task and slice;
- slice start commit;
- normalized changed paths;
- blocker code and summary;
- completed and failed validations;
- run summary location;
- updated timestamp.

Updating the plan itself makes it part of the partial slice. If the plan cannot
be updated without obscuring the original diff, the ignored run summary must
capture equivalent recovery data and the terminal result must instruct manual
reconciliation.

### Resume algorithm

On every implementation invocation, the orchestrator must:

1. parse and validate plan state;
2. recompute the material digest;
3. inspect current HEAD, branch, operation state, status, and diff;
4. derive each completed slice's unique owning commit from trailers and verify it
   is an ancestor of HEAD;
5. verify completed checkboxes and evidence agree with the derived owning
   commits;
6. when a partial slice exists, require current HEAD to equal
   `slice_start_commit` and the dirty paths to equal or be an explainable subset
   of `partial_slice_paths` plus the plan itself;
7. stop when existing changes are unrelated, ownership is unclear, or recorded
   files disappeared unexpectedly;
8. resume the partial slice before selecting new work;
9. otherwise select the earliest dependency-ready incomplete slice;
10. preserve unrelated human commits made after completed slices when they do
    not alter material content or planned path assumptions;
11. invalidate approval and stop if reconciliation reveals material divergence.

Resume must be idempotent: rerunning against a complete plan performs no writes,
and rerunning after a committed slice must not repeat that slice.

### Signals and abrupt termination

On `SIGINT` or `SIGTERM`, the orchestrator must stop launching work, terminate
the active child with a bounded grace period, reconcile observable state, write
an ignored run summary, and return the interrupted exit category. Signal
handling must not create a commit.

Abrupt termination that prevents cleanup is recovered by the next invocation
through plan, Git, and run-summary reconciliation. Process identifiers or lock
files alone must not be treated as proof that a run is active.

## Final review and remediation

The final reviewer uses a fresh read-only session with the accepted spec, ready
plan, implementation diff or relevant commit range, repository rules, and broad
validation results. It reports stable findings using the review schema, with IDs
prefixed `FINAL-`.

The orchestrator may create a remediation slice only when the finding:

- demonstrates non-conformance with accepted scope or quality requirements;
- can be corrected without a material plan decision;
- has an explicit acceptance check and bounded changed-path scope; and
- does not require a prohibited operation.

Invocation approval for an exact material digest includes a remediation envelope
for these corrections because they restore conformance to already approved
requirements. A remediation record is progress content, not an ordinary material
plan slice. It must include a stable `FINAL-` finding ID, affected accepted
requirement or acceptance criterion, bounded changed-path scope, correction,
verification, status, and attempt count. The orchestrator may not create a
remediation record that adds capability, changes a contract, alters architecture
or dependencies, changes sequencing of incomplete planned work, or cannot cite
the approved material requirement it restores.

New product features, architecture changes, dependency decisions, migrations,
or broadened acceptance criteria are blockers, not remediation. Every remediation
slice follows fresh-session, validation, reconciliation, and atomic commit rules.
It retains the originally approved material digest, uses the corresponding
finding ID as its stable slice ID, and is limited to one implementation attempt.
After one or more remediation commits, the orchestrator must run exactly one
fresh read-only confirmation review. Any repeated, new blocking, or material
finding blocks completion. Any unresolved major finding also blocks completion.
Broad checks affected by remediation must be rerun; their latest passing
evidence supersedes earlier results for finalization.

## Audit and run logs

The orchestrator must keep per-invocation diagnostic records under a
workspace-local ignored directory, defaulting to `.cline-sdlc/runs/<run-id>/`.
The directory must contain a machine-readable summary with:

- orchestrator and detected Cline versions;
- run identifier, stage, timestamps, and starting commit;
- input and artifact paths;
- session roles and terminal outcomes;
- attempt counters and timeout events;
- command classifications and redacted command results;
- reconciliation decisions;
- final status and blocker.

Raw Cline event streams may be retained locally when needed for diagnosis but
must be treated as potentially sensitive. The orchestrator must create or verify
an ignore rule before writing logs inside a Git repository. It must not modify an
existing ignore file destructively or commit log content.

## Portability and compatibility

- The application and generated contracts must not depend on this repository's
  paths, project name, language, architecture, or validation commands.
- Existing host conventions determine artifact locations when discoverable; the
  defaults are `docs/ideas/`, `docs/specs/`, and `docs/plans/`.
- The application must support macOS and Linux for the MVP.
- The implementation plan must select and document a minimum supported Python 3
  version compatible with current `uvx` packaging.
- Cline compatibility must be capability-based. Unsupported or missing required
  behavior produces an actionable preflight error naming the failed capability.
- File writes must use UTF-8 and preserve host line endings where practical;
  digest canonicalization remains deterministic across supported platforms.
- Structured schemas are versioned. Unsupported versions fail closed; migrations
  require a future specification.

## Security and privacy requirements

- Treat artifact paths, branch names, Cline output, repository files, and command
  text as untrusted input.
- Avoid shell string interpolation; use argument arrays and explicit working
  directories for subprocesses.
- Prevent path traversal and symlink escapes for orchestrator-managed writes.
- Redact environment values and command arguments identified as secrets.
- Do not send repository data anywhere except through the user-configured Cline
  CLI execution path.
- Do not load executable configuration from the target repository merely to
  classify permissions.
- Validation discovery may inspect documented project commands, but execution is
  still subject to permission classification.
- Fail closed when operation risk, outcome validity, or change ownership is
  uncertain.

## Validation discovery

The plan-author session must record focused verification for each slice and the
repository-wide final quality gate. Discovery should prefer, in order:

1. explicit commands in the accepted spec or plan;
2. repository instructions and contributor documentation;
3. CI configuration and task runners;
4. language-standard project metadata;
5. a blocker when safe authoritative commands cannot be established.

The orchestrator must not invent successful evidence. A command that was not run
is `not_run`. Final completion requires every required broad check to pass, or an
explicit human-approved exception outside unattended execution.

## Acceptance criteria

### CLI and stage boundaries

- [ ] Given no input or multiple input options, the CLI exits with usage code 2,
      emits an actionable error, and starts no Cline session.
- [ ] Given each valid input option, the CLI selects the corresponding stage
      without content-based ambiguity.
- [ ] A file input that is untracked, differs from `HEAD`, or has uncommitted
      referenced findings fails preflight before Cline starts.
- [ ] Each successful invocation stops at its next artifact boundary and never
      starts the following major stage.
- [ ] The package can be installed and executed through `uvx` on supported macOS
      and Linux environments.
- [ ] `--json` emits one valid terminal result and no non-JSON stdout content.
- [ ] Every terminal status maps to exactly one documented process exit category.

### Idea and specification stages

- [ ] A rough idea starts an attached interactive refinement session and can
      complete only with explicit user acceptance and a verified idea brief.
- [ ] An idea-file invocation starts an attached interactive specification
      session and can complete only with explicit user acceptance and a verified
      specification.
- [ ] Ending either interview without acceptance returns blocked and does not
      report the artifact as accepted.
- [ ] Neither interactive stage creates or invokes the next lifecycle stage.

### Plan authoring and review

- [ ] A specification produces a plan with stable slices, verification steps,
      the embedded version-1 state block, and a valid material digest.
- [ ] Plan authoring and every review run in separate fresh sessions.
- [ ] Reviewer permissions reject writes and any observed reviewer write blocks
      the stage.
- [ ] A ready initial review ends the stage without unnecessary revision.
- [ ] Changes-required reviews preserve finding IDs and run no more than two
      revision/re-review cycles after the initial review.
- [ ] Exhausting the review loop records unresolved findings, marks the plan
      blocked, and returns exit code 4.
- [ ] No implementation session starts from a specification-file invocation.

### State and approval

- [ ] Invalid, duplicate-keyed, path-traversing, unknown-field, or unsupported
      plan state fails closed before Cline starts.
- [ ] Material digest calculation is deterministic across supported platforms and
      excludes documented progress-only content.
- [ ] Progress-only updates preserve the material digest.
- [ ] Scope, acceptance, contract, dependency, architecture, security, migration,
      or material sequencing changes alter the digest.
- [ ] A plan-file invocation records the exact verified material digest as its
      bounded invocation approval.
- [ ] Material divergence during execution stops before another slice or commit.

### Implementation and Git safety

- [ ] Implementation rejects a dirty initial tree unless it reconciles exactly
      with the recorded partial slice.
- [ ] Implementation rejects detached HEAD, protected branches, unresolved Git
      operations, and unexpected HEAD movement.
- [ ] Each slice uses a fresh session and receives only its bounded assignment.
- [ ] A completed outcome is independently reconciled with Git paths and passing
      validation before commit.
- [ ] Every successful slice creates exactly one local commit containing its code,
      tests or docs, evidence, and progress state but no unrelated files.
- [ ] Slice commit ownership is derived from unique Git trailers without requiring
      a commit to contain its own hash.
- [ ] Commit hooks are not bypassed, and hook failure leaves attributable changes
      uncommitted and recoverable.
- [ ] Completed slices are not repeated after restart.
- [ ] A complete plan produces a successful no-op with no session and no commit.
- [ ] Successful final completion creates one progress-only finalization commit,
      and a failed finalization never reports the plan complete.

### Permissions and stop behavior

- [ ] Read-only inspection, bounded workspace edits, known local validation, and
      the orchestrator's slice commit can proceed without routine approval.
- [ ] Network, dependencies, credentials, destructive actions, external effects,
      material decisions, and unclassified commands stop with the exact proposed
      operation recorded.
- [ ] The orchestrator never pushes, publishes, deploys, rewrites history, deletes
      branches, or executes streamed remote scripts.
- [ ] Ambiguity, spec contradiction, material drift, unavailable context, or
      exhausted attempts stops automation rather than broadening scope.

### Failure and resumption

- [ ] One malformed session outcome may be retried only when no ambiguous writes
      exist; a second failure blocks the stage.
- [ ] Timeout or interruption terminates the child, records observable state, does
      not commit, and returns exit code 6.
- [ ] A failed slice records its start commit, owned paths, evidence, and blocker
      while leaving changes uncommitted.
- [ ] Resume continues the recorded partial slice before any other slice when its
      HEAD and diff reconcile.
- [ ] Resume stops without modifying files when partial-slice ownership conflicts
      with the actual working tree.
- [ ] Unrelated human changes are never staged into an orchestrator commit.
- [ ] Repeated validation, review, protocol, or remediation failures stop at their
      defined limits.

### Final quality gate

- [ ] After planned slices, a fresh read-only final review and all discovered
      broad quality checks run before completion.
- [ ] In-scope fixable findings become explicit bounded remediation slices with
      acceptance checks.
- [ ] Every remediation cites an approved requirement, preserves the approved
      material digest, and cannot introduce new product scope or decisions.
- [ ] Material or scope-expanding final findings block rather than becoming silent
      remediation.
- [ ] Each successful remediation is independently validated and committed.
- [ ] Remediation is followed by one fresh confirmation review and rerun of
      affected broad checks before finalization.
- [ ] The plan reaches `complete` only with no unresolved blocking or major
      findings and a passing final quality gate.

### Auditability and portability

- [ ] Every invocation produces a redacted structured run summary and terminal
      result sufficient to explain its stage, attempts, decisions, and status.
- [ ] Run logs are ignored and excluded from commits by default.
- [ ] Generated artifacts remain understandable without access to prior Cline
      sessions or Checkpoints.
- [ ] A fresh orchestrator process can resume solely from repository artifacts,
      Git state, and optional ignored run summaries.
- [ ] Host artifact and validation conventions are used when present; otherwise
      portable defaults and actionable blockers apply.
- [ ] An end-to-end fixture in an unrelated temporary repository with different
      artifact paths and project commands passes without relying on this
      repository's layout or tooling.

## Testing strategy

Implementation planning must cover these test levels:

- unit tests for CLI parsing, schema validation, digest canonicalization, branch
  protection, permission classification, outcome parsing, attempt limits, and
  slice selection;
- property or parameterized tests for path normalization, malicious paths,
  duplicate keys, digest stability, and state invariants;
- subprocess contract tests with a fake Cline executable emitting successful,
  malformed, conflicting, timed-out, and approval-required outcomes;
- temporary-Git-repository integration tests for clean and dirty trees, protected
  branches, commits, hook failures, HEAD movement, partial slices, and resume;
- end-to-end fixture workflows covering all four input types and every required
  stop boundary without real external side effects;
- an external-host fixture with different artifact locations and validation
  commands to prove drop-in portability;
- packaging smoke tests that install and invoke the console entry point through
  `uvx` on supported platforms;
- a manually supervised proof of concept against a small non-production
  repository before unattended use is recommended.

Tests must not require production credentials, remote pushes, deployment, or
mutation of the developer's real Git configuration.

## Project structure constraints

The implementation plan may choose the precise source layout but must preserve
these responsibilities:

- CLI adapter for arguments, terminal attachment, JSON output, and exit codes;
- lifecycle application service and explicit state transitions;
- Cline subprocess adapter and capability detection;
- artifact parser, schema validation, and digest service;
- Git status, reconciliation, staging, and commit adapter;
- permission policy and command classifier;
- run-log and terminal-result writer;
- tests separated by unit, subprocess contract, Git integration, and end-to-end
  concerns;
- Python packaging metadata with a console script runnable by `uvx`.

Domain lifecycle logic must be testable without launching real Cline or invoking
the developer's Git repository. Subprocess, clock, filesystem, and Git effects
must be behind replaceable boundaries.

## Implementation constraints

- Prefer the smallest dependency set that safely supports CLI parsing, strict
  schema parsing, and subprocess control.
- Pin supported schema behavior in tests rather than relying on permissive model
  output.
- Use typed Python interfaces and explicit domain values for phases, outcomes,
  findings, and exit categories.
- Do not use shell execution when argument-array subprocess execution is
  available.
- Keep prompts and stage adapters compositional so existing Agent Skills remain
  the procedural source rather than copied prompt text.
- Detect required skills by stable skill name and a capability probe that asks
  the session to confirm it can load the required procedure before allowing
  artifact writes. Skills are external prerequisites in the MVP, not bundled by
  the Python package; missing or incompatible skills fail preflight or return the
  structured `required_context_unavailable` blocker before writes.
- Keep all retries bounded and visible.
- Make every state transition validate its preconditions and postconditions.
- Do not implement fallback behavior that converts an invalid structured outcome
  into success from prose.

## Commands and validation

Exact implementation commands will be selected in the implementation plan after
the Python package layout and minimum version are chosen. The completed project
must expose documented equivalents of:

```text
uv run <formatter-command>
uv run <lint-command>
uv run <type-check-command>
uv run <test-command>
uvx --from . cline-sdlc --help
```

CI and local validation must exercise formatting, linting, static type checking,
unit tests, integration tests, and packaging smoke tests. Network-dependent tests
must not be part of the default local unit suite.

## Rollout and proof of concept

Before describing implementation mode as unattended-ready:

1. run all four stage inputs in a disposable non-production repository;
2. complete at least three serial low-risk implementation slices with one commit
   per slice;
3. interrupt one slice and resume it from a new orchestrator process;
4. inject one malformed session outcome and verify bounded retry;
5. trigger one prohibited operation and verify stop behavior;
6. alter material plan content after approval and verify invalidation;
7. run final review with one remediable and one material finding;
8. confirm logs, artifacts, and commits contain no injected test secret.

Failure to demonstrate structured outcomes, bounded permissions, or reliable
dirty-tree recovery triggers reconsideration of the Cline SDK direction.

## Success measures

The MVP is useful when the proof of concept demonstrates:

- all four inputs reach only their intended artifact boundaries;
- plan review and at least three low-risk slices require no routine coordination
  after invocation;
- every automated commit is attributable to one accepted slice;
- all injected risk, drift, ambiguity, and failure cases stop at the required
  boundary;
- interrupted work resumes without repeating completed slices or including
  unrelated changes;
- a maintainer can determine why a run completed or stopped from artifacts and
  structured summaries without reconstructing chat history.

Operational metrics should count stage completions, human interventions by
reason, retries, timeouts, blocked runs, resumed slices, validation failures,
remediation slices, and reconciliation failures. The MVP does not require remote
telemetry; local summaries are sufficient.

## Open questions for implementation planning

These choices do not change the product contract and may be resolved in the
implementation plan:

- the package distribution name and source directory within its repository;
- the minimum supported Python 3 and Cline CLI versions after capability spikes;
- the concrete Python libraries for CLI parsing and strict YAML handling;
- the exact material/progress section marker syntax;
- the default finite session timeout within the specified limit;
- the exact ignored run-log insertion strategy for repositories with different
  ignore conventions;
- whether plan-review findings are embedded in the plan or kept in one adjacent
  committed artifact;
- the exact fake-Cline harness and cross-platform packaging test matrix.

Any implementation discovery that changes approval semantics, state ownership,
artifact boundaries, allowed effects, Git safety, or recovery behavior requires
specification review before implementation continues.
