# Implementation Plan: Cline SDLC Orchestrator

<!-- cline-sdlc-material:start -->

## Objective and specification

Implement the standalone Python 3.14 `cline-sdlc` command-line application defined by
[`docs/specs/cline-sdlc-orchestrator-spec.md`](../specs/cline-sdlc-orchestrator-spec.md).
The application will coordinate exactly one bounded SDLC stage per invocation through
the Cline CLI, preserve human approval at major artifact and risk boundaries, and use
repository-visible artifacts plus Git history as authoritative workflow state.

Implementation must stop after the artifact boundary selected by the explicit input:

| Input | Stage | Required boundary |
| --- | --- | --- |
| `--idea` | Idea refinement | Accepted idea brief |
| `--idea-file` | Specification creation | Accepted specification |
| `--spec-file` | Plan creation and review | Ready plan or explicit blocker |
| `--plan-file` | Plan implementation | Complete plan or explicit blocker |

The implementation is complete only after the specification acceptance criteria,
rollout exercises, packaging smoke test, and repository quality gate pass.

## Scope

- A `cline-sdlc` console entry point installable and runnable through `uvx`.
- Typed CLI inputs, terminal results, stable exit categories, and JSON-only output.
- Capability-based Cline CLI preflight and skill availability checks.
- Strict session outcome, finding, blocker, validation evidence, and plan-state schemas.
- Deterministic specification and plan material digests.
- Balanced-profile operation classification and fail-closed permission handling.
- Git preflight, reconciliation, explicit staging, atomic slice commits, and resumption.
- Interactive idea and specification stages.
- Unattended bounded plan authoring and independent review.
- Serial fresh-session implementation, final review, remediation, and finalization.
- Redacted local run summaries and portable temporary-repository test fixtures.

## Non-goals

- Cascading automatically across multiple major lifecycle stages.
- Cline SDK or Agent Team orchestration unless the Phase 0 viability gate rejects the
  CLI-wrapper architecture.
- Pushes, pull requests, releases, publishing, deployment, or other remote effects.
- Concurrent implementation sessions or repository writers.
- Database-backed state, arbitrary approval profiles, or automatic dependency changes.
- Reimplementing the detailed procedures already owned by stage-specific Agent Skills.
- Imposing this repository's architecture or validation commands on host repositories.

## Repository context and constraints

- The repository currently contains an application shell under `src/cline_sdlc/` with
  `features/`, `shared_kernel/`, and `bootstrap/` packages but no business behavior.
- New capabilities must use feature-owned vertical slices with hexagonal boundaries.
- Application and domain behavior must be testable without real Cline sessions, the
  developer's Git repository, wall-clock dependence, or uncontrolled filesystem effects.
- Use `uv`, Ruff, mypy, and pytest through the project configuration in `pyproject.toml`.
- Runtime dependencies belong in `[project].dependencies`; dependency changes must update
  `pyproject.toml` and `uv.lock` together and require explicit approval.
- The implementation must use argument-array subprocess execution and explicit working
  directories; it must not use shell interpolation for untrusted values.
- The default implementation branch cannot be a protected branch. Disposable Git
  repositories or a non-protected feature branch must be used for write/commit tests.
- The current baseline has a known version mismatch: package metadata reports `0.0.1`
  while `tests/unit/test_package.py` expects `0.1.0`. Task 0.1 resolves this before feature
  validation so subsequent checkpoints have a trustworthy baseline.
- The specification artifact still labels itself “draft for review and acceptance.” This
  plan may be prepared and reviewed, but Checkpoint A cannot authorize production feature
  implementation until the specification is explicitly accepted without material changes.
- Installed Cline CLI `3.0.46` exposes JSON output, finite timeouts, isolated data
  directories, hooks, and skill commands, but its public help does not by itself prove the
  outcome, permission-mediation, or interruption contracts required by the specification.

## Architecture

Use feature-owned slices and expose collaboration only through published application
ports. The expected ownership map is:

```text
src/cline_sdlc/
├── bootstrap/                         # composition root and console startup
├── shared_kernel/                     # genuinely shared pure values only
└── features/
    ├── cline_execution/               # capability probes and subprocess sessions
    ├── artifact_lifecycle/            # state, findings, artifacts, and digests
    ├── repository_coordination/       # Git inspection, reconciliation, and commits
    ├── operation_policy/              # balanced-profile operation classification
    ├── run_audit/                     # redacted ignored summaries and run records
    └── lifecycle_orchestration/       # stage selection and bounded workflows
```

Each slice may contain `domain/`, `application/ports/`, `application/dtos/`,
`application/use_cases/`, and `adapters/` packages as needed. Empty packages should not
be created in advance. `lifecycle_orchestration` may depend only on published application
APIs from collaborating slices, never their private services or adapters.

The composition root owns concrete adapter construction. Cline, Git, filesystem, clock,
signal, terminal, and process effects remain behind replaceable application-owned ports.
Transport JSON, subprocess event objects, and command-line parser types stay in adapters.

### Public contract ownership

Cross-slice collaboration must use the following published application contracts. A type
remains in its owning slice unless it is a pure value with stable semantics genuinely shared
by at least two slices; convenience alone does not justify moving it to `shared_kernel`.

| Contract | Owner | Published consumers |
| --- | --- | --- |
| Session request, process observation, capability result | `cline_execution` | `lifecycle_orchestration` |
| Artifact kind, normalized managed path, plan state, finding, digest result | `artifact_lifecycle` | `lifecycle_orchestration`, `repository_coordination` through explicit DTOs |
| Repository snapshot, changed-path set, commit request/result | `repository_coordination` | `lifecycle_orchestration`, `run_audit` for safe summaries |
| Executable/argument command specification and policy decision | `operation_policy` | `lifecycle_orchestration`, execution adapters through orchestration |
| Validation command, result, and evidence record | `lifecycle_orchestration` | `artifact_lifecycle` only through its progress-update API; `run_audit` through summary DTOs |
| Invocation approval and terminal result | `lifecycle_orchestration` | bootstrap CLI and `run_audit` |
| Run identifier, redacted event, and summary reference | `run_audit` | `lifecycle_orchestration` |

Clock and identifier generation are application-owned ports in the slice that needs them.
Filesystem paths exposed across application boundaries are normalized repository-relative
values rather than adapter-native `Path` objects. The orchestration slice may import only
these published APIs; it must not import another slice's domain internals, concrete use cases,
or adapters.

## Material decisions

1. **CLI viability is a hard gate.** Before full implementation, a supervised spike must
   prove machine-detectable outcomes, enforceable permission boundaries, interruption
   recovery, and changed-path attribution. Failure triggers specification review and an
   SDK decision; it must not lead to weakened contracts.
2. **Default session timeout is 30 minutes.** It is finite, configurable, and below the
   specification's 60-minute maximum.
3. **Findings are embedded in the plan progress region by default.** This keeps review
   state and findings atomic unless the capability spike reveals a concrete reason to use
   one adjacent artifact.
4. **YAML parsing must be strict and safe.** Select the smallest dependency that supports
   duplicate-key rejection and safe loading. Aliases, custom tags, unknown fields, and
   unsupported versions remain rejected by application validation.
5. **Real Cline exercises are supervised proof tests.** The default automated suite uses a
   fake Cline executable and temporary Git repositories and performs no network access.
6. **One application use case owns each transaction boundary.** Adapters report effects;
   only application orchestration decides whether state may advance or a commit may occur.
7. **Progress cannot prove success by itself.** Session outcomes, observed Git state,
   validation results, digest checks, and commit trailers must reconcile before advancing.
8. **Artifact lifecycle owns portable artifact policy.** It publishes artifact-type and
   path-selection contracts; orchestration requests paths through that API rather than
   embedding repository conventions or defaults in individual stage workflows.
9. **Transport does not decide workflow retries.** `cline_execution` reports typed process
   and protocol observations. `lifecycle_orchestration` combines those observations with
   repository state and attempt limits to decide whether one retry is safe.
10. **Preflight is one ordered transaction.** Orchestration validates runtime and invocation,
    inspects artifact and repository state, establishes a safely ignored audit destination,
    probes Cline capabilities and required skills, and only then authorizes a stage session.
    Failure starts no stage session and writes no lifecycle artifact.
11. **Invocation approval is explicit audit state.** A `--plan-file` run records an immutable
    approval record containing the run ID, profile, starting HEAD, timestamp, and exact
    specification and material digests before implementation reconciliation. Every slice,
    remediation, and finalization decision is tied to that record and stops on divergence.

## Readiness and authorization labels

- **Phase 0 — ready for supervised implementation:** Tasks 0.1–0.3 may proceed to establish
  the baseline and collect capability evidence.
- **Phases 1–6 — gated:** Tasks 1.1 and later are unauthorized until the specification is
  explicitly accepted and Checkpoint A passes without weakening its contracts.
- **Unattended-ready claim — gated:** The implementation must not be described as
  unattended-ready until Checkpoint F evidence is reviewed and accepted by the product owner.

## Dependency graph and sequencing

```text
Trustworthy baseline
  -> Fake-Cline harness
    -> Real CLI viability gate
      -> Typed schemas and digest contracts
        -> Cline, policy, Git, and audit adapters
          -> Interactive stages
          -> Plan author/review stage
            -> Slice reconciliation and commits
              -> Final review, remediation, and finalization
                -> Portable end-to-end proof
```

Tasks are intentionally ordered by dependency and risk. Work must not proceed beyond a
checkpoint with unresolved blocking criteria. Each task should remain a focused session
of roughly three to five production/test files; if discovery makes it larger, split it
without combining independent responsibilities.

## Phase 0: Baseline and CLI-wrapper viability

### Task 0.1: Restore a trustworthy project baseline

**Description:** Resolve the existing package-version mismatch by confirming the canonical
project version and aligning its test. Establish the pre-feature quality and packaging
baseline without changing product behavior.

**Acceptance criteria:**

- Package metadata and the package-version test assert the same canonical version.
- The existing test suite, Ruff checks, mypy, build, and package import pass.
- No lifecycle feature behavior is introduced in this task.

**Verification:**

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv build`

**Dependencies:** None.

**Likely paths:** `pyproject.toml`, `tests/unit/test_package.py`.

**Estimated scope:** Small.

### Task 0.2: Add a deterministic fake-Cline contract harness

**Description:** Create a test-only executable and fixture API that can emit valid,
missing, malformed, duplicate, conflicting, approval-required, delayed, and interrupted
session outcomes without invoking real Cline.

**Acceptance criteria:**

- Scenarios are selected through explicit arguments or fixture configuration, not ambient
  developer state.
- The harness can write controlled repository paths and report matching or contradictory
  changed paths.
- Tests can exercise process exit, timeout, signal, and outcome-stream behavior on macOS
  and Linux.

**Verification:**

- `uv run pytest tests/contract/features/cline_execution/`

**Dependencies:** Task 0.1.

**Likely paths:** `tests/contract/features/cline_execution/fake_cline.py`,
`tests/contract/features/cline_execution/conftest.py`,
`tests/contract/features/cline_execution/test_fake_cline.py`.

**Estimated scope:** Medium.

### Task 0.3: Prove the real Cline CLI contracts

**Description:** Build a narrowly scoped capability-spike adapter and supervised proof
fixture using a temporary repository and isolated Cline data directory. Determine whether
the CLI can enforce the non-negotiable session protocol and permission contracts.

**Acceptance criteria:**

- A session produces exactly one machine-detectable terminal outcome without prose
  scraping.
- The parent can enforce read-only review and argument-aware allow/deny policy before a
  prohibited operation executes.
- Timeout or interruption provides bounded child termination and sufficient observable
  state to attribute partial writes from a fresh process.
- Required skill availability can be probed before artifact writes.
- Results and limitations are recorded in a committed capability report with no secrets.

**Verification:**

- Run the supervised spike against installed Cline in a disposable repository.
- Review the captured redacted event/outcome report against specification sections
  “Structured Cline session protocol,” “Permission boundaries,” and “Failure handling.”

**Dependencies:** Task 0.2.

**Likely paths:** `src/cline_sdlc/features/cline_execution/`,
`tests/manual/cline_execution/`, `docs/research/cline-cli-capability-spike.md`.

**Estimated scope:** Medium, split into probe and report subtasks if more than five files.

### Checkpoint A: Architecture viability

- The repository quality baseline is green.
- The fake harness covers the protocol failure matrix deterministically.
- The supervised spike proves all critical CLI-wrapper contracts.
- The specification is explicitly accepted, or material changes are incorporated into a
  new plan revision and independently reviewed.
- If any critical contract fails, implementation stops for specification review and an
  SDK/CLI product decision; Tasks 1.1 and later remain unauthorized.
- The product owner reviews the evidence before implementation proceeds.

## Phase 1: Stable contracts and pure lifecycle behavior

### Task 1.1: Define CLI invocation and terminal result contracts

**Description:** Add the console entry point, typed input selection, stable exit categories,
terminal result model, and adapter mapping for help, version, timeout, explicit Cline
command, JSON-only output, and verbose diagnostics.

**Acceptance criteria:**

- Exactly one of `--idea`, `--idea-file`, `--spec-file`, or `--plan-file` is required.
- Invalid inputs return usage code 2 and do not call a Cline port.
- Every explicit input maps to exactly one stage without content guessing.
- `--json` emits one JSON terminal result and no other stdout content.

**Verification:**

- `uv run pytest tests/unit/features/lifecycle_orchestration/adapters/inbound/`
- `uvx --from . cline-sdlc --help`

**Dependencies:** Checkpoint A.

**Likely paths:** `pyproject.toml`, `src/cline_sdlc/bootstrap/cli.py`,
`src/cline_sdlc/features/lifecycle_orchestration/application/dtos/`,
`tests/unit/features/lifecycle_orchestration/adapters/inbound/test_cli.py`.

**Estimated scope:** Medium.

**Required implementation slices:**

- `1.1a` — input parsing, mutually exclusive selection, and stage mapping;
- `1.1b` — terminal-result JSON serialization, diagnostics, and exit-category mapping;
- `1.1c` — bootstrap wiring, console entry point, and local packaging smoke.

Implement and verify these slices in order rather than treating Task 1.1 as one change set.

### Task 1.2: Define session outcome and finding schemas

**Description:** Model session roles, statuses, findings, blockers, validation evidence,
and terminal outcomes as explicit domain/application values with role-specific invariants.

**Acceptance criteria:**

- Schema version, enum, path, required-empty/null, and role-specific rules fail closed.
- Reviewer writes, duplicate outcomes, invalid paths, and contradictory fields are invalid.
- Findings preserve stable IDs and allow only documented severity/status combinations.

**Verification:**

- `uv run pytest tests/unit/features/cline_execution/domain/`
- `uv run pytest tests/unit/features/artifact_lifecycle/domain/test_findings.py`

**Dependencies:** Task 1.1.

**Likely paths:** `src/cline_sdlc/features/cline_execution/domain/outcome.py`,
`src/cline_sdlc/features/artifact_lifecycle/domain/findings.py`, corresponding unit tests.

**Estimated scope:** Medium.

### Task 1.3: Parse and validate plan lifecycle state

**Description:** Add strict extraction and validation for the single
`cline-sdlc-state` YAML block, including all version-1 fields, normalized paths, and legal
phase transitions.

**Acceptance criteria:**

- Duplicate keys, aliases, custom tags, unknown fields, unexpected types, traversal,
  unsupported versions, and invalid transitions are rejected.
- Active/blocked/complete state invariants match the specification.
- Parsing is independent of Git and subprocess adapters.

**Verification:**

- `uv run pytest tests/unit/features/artifact_lifecycle/domain/test_plan_state.py`
- Parameterized malicious-YAML and transition-matrix tests pass.

**Dependencies:** Task 1.2 and explicit approval for the selected YAML dependency.

**Likely paths:** `pyproject.toml`, `uv.lock`,
`src/cline_sdlc/features/artifact_lifecycle/domain/plan_state.py`,
`src/cline_sdlc/features/artifact_lifecycle/adapters/inbound/state_yaml.py`, tests.

**Estimated scope:** Medium; dependency metadata may be committed separately if required.

### Task 1.4: Implement artifact regions and deterministic digests

**Description:** Parse non-nesting material/progress regions and implement exact
specification and plan-material canonicalization and SHA-256 formatting.

**Acceptance criteria:**

- Region count, placement, nesting, overlap, and outside-content rules are enforced.
- LF, CRLF, and CR source forms produce the specified canonical specification digest.
- Progress-only edits preserve the material digest.
- Material whitespace, revision, specification identity, or material content changes alter
  the material digest.

**Verification:**

- `uv run pytest tests/unit/features/artifact_lifecycle/domain/test_regions.py`
- `uv run pytest tests/unit/features/artifact_lifecycle/domain/test_digests.py`

**Dependencies:** Task 1.3.

**Likely paths:** `src/cline_sdlc/features/artifact_lifecycle/domain/regions.py`,
`src/cline_sdlc/features/artifact_lifecycle/domain/digests.py`, corresponding tests.

**Estimated scope:** Medium.

### Task 1.5: Discover artifact locations and portable defaults

**Description:** Publish an artifact-location policy that discovers explicit host
conventions without executing repository configuration and otherwise selects the portable
`docs/ideas/`, `docs/specs/`, and `docs/plans/` defaults. Normalize every selected path for
comparison and reporting.

**Acceptance criteria:**

- Explicit user-selected paths take precedence over discovered host conventions.
- Safe documented repository conventions take precedence over portable defaults.
- Defaults do not require this repository's project name, architecture, or layout.
- Path traversal, symlink escape for managed writes, ambiguous conventions, and unsafe
  destinations fail with an actionable result before a stage writes an artifact.

**Verification:**

- `uv run pytest tests/unit/features/artifact_lifecycle/application/test_artifact_locations.py`
- Temporary-host parameterized tests cover custom paths and every fallback default.

**Dependencies:** Tasks 1.1 and 1.2.

**Likely paths:**
`src/cline_sdlc/features/artifact_lifecycle/application/dtos/artifact_location.py`,
`src/cline_sdlc/features/artifact_lifecycle/application/use_cases/select_artifact_location.py`,
repository-inspection port, tests.

**Estimated scope:** Medium.

### Checkpoint B: Artifact and public contract

- CLI contract tests pass without launching real Cline.
- Outcome and plan-state schemas reject all documented invalid forms.
- Digest golden vectors and line-ending/property matrices pass.
- Artifact locations honor explicit paths, safe host conventions, and portable defaults.
- Public application functions and DTOs are fully typed and documented where non-obvious.
- Full repository quality gate passes.

## Phase 2: Replaceable external boundaries and safety services

### Task 2.1: Implement the Cline subprocess adapter

**Description:** Implement argument-array process execution with explicit working and data
directories, finite timeout, bounded termination, structured event capture, and exactly-one
terminal outcome validation.

**Acceptance criteria:**

- Startup, normal exit, malformed output, duplicate output, timeout, interruption, and
  child termination are represented as typed outcomes.
- The adapter performs no workflow retry and does not inspect Git; it returns enough typed
  observations for orchestration to make that decision.
- Complete prompts, secrets, and raw model reasoning are absent from default diagnostics.

**Verification:**

- `uv run pytest tests/contract/features/cline_execution/`

**Dependencies:** Checkpoint B and the proven Phase 0 transport contract.

**Likely paths:** `src/cline_sdlc/features/cline_execution/application/ports/`,
`src/cline_sdlc/features/cline_execution/application/use_cases/run_session.py`,
`src/cline_sdlc/features/cline_execution/adapters/outbound/subprocess_client.py`, tests.

**Estimated scope:** Medium.

### Task 2.2: Coordinate bounded session attempts

**Description:** Add an orchestration use case that records pre-session repository state,
invokes one Cline session, reconciles post-session observations, and permits the one
documented protocol or transient-startup retry only when no unsafe or ambiguous write
occurred.

**Acceptance criteria:**

- Attempt counters and retry reasons are explicit in run summaries and terminal results.
- Missing/malformed/duplicate outcomes receive at most one fresh-session retry.
- Startup failure receives at most one retry only when repository state is unchanged and
  the failure is classified transient.
- Any ambiguous write, prohibited operation, timeout, or interruption prevents retry and
  starts no later session.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_session_attempts.py`

**Dependencies:** Tasks 2.1, 2.4, and 2.5. This task is implemented after those dependencies
even though it is documented here beside the subprocess contract it coordinates.

**Likely paths:**
`src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/run_session_attempts.py`,
attempt DTOs, contract tests.

**Estimated scope:** Medium.

### Task 2.3: Add capability and skill preflight

**Description:** Probe behavior instead of accepting a version string, validate finite
timeout support and required session transport, and verify stage skill availability before
artifact-writing sessions.

**Acceptance criteria:**

- Missing executable, failed capability, incompatible behavior, or missing skill returns an
  actionable preflight result.
- A failed preflight starts no stage session and changes no lifecycle artifact.
- Cline executable selection supports the explicit `--cline-command` path safely.

**Verification:**

- `uv run pytest tests/contract/features/cline_execution/test_capability_preflight.py`

**Dependencies:** Task 2.1.

**Likely paths:** `src/cline_sdlc/features/cline_execution/application/use_cases/preflight.py`,
`src/cline_sdlc/features/cline_execution/application/dtos/capabilities.py`, adapter tests.

**Estimated scope:** Small.

### Task 2.4: Implement the balanced operation policy

**Description:** Classify structured executable and argument arrays against the balanced
profile. Permit only documented low-risk local operations and fail closed on prohibited or
unclassifiable requests.

**Acceptance criteria:**

- Network, dependencies, credentials, destructive operations, external effects, history
  rewriting, hook bypass, streamed scripts, and material decisions are denied.
- Known repository inspection and configured local validation commands can be allowed.
- Classifier output records the rule and safe proposed operation without secret values.

**Verification:**

- `uv run pytest tests/unit/features/operation_policy/`
- Table-driven adversarial cases cover shell wrappers, alternate paths, quoting, Git
  subcommands, interpreters, and network-capable executables.

**Dependencies:** Task 1.2 and the proven Phase 0 mediation mechanism.

**Likely paths:** `src/cline_sdlc/features/operation_policy/domain/policy.py`,
`src/cline_sdlc/features/operation_policy/application/use_cases/classify_operation.py`, tests.

**Estimated scope:** Medium.

### Task 2.5: Implement Git inspection and branch safety

**Description:** Add Git ports and an argument-array adapter for repository root, HEAD,
branch, operation state, tracked/committed inputs, status, diffs, nested repositories, and
protected branch matching.

**Acceptance criteria:**

- Detached HEAD, protected branches, unresolved Git operations, missing HEAD, unsupported
  nested changes, and dirty initial trees fail preflight as specified.
- File inputs must be tracked, committed at HEAD, readable, regular files, and identical to
  committed content.
- Tests never mutate the developer's Git configuration or real repository.

**Verification:**

- `uv run pytest tests/integration/features/repository_coordination/test_preflight.py`

**Dependencies:** Task 1.1.

**Likely paths:** `src/cline_sdlc/features/repository_coordination/application/ports/git.py`,
`src/cline_sdlc/features/repository_coordination/application/use_cases/inspect_repository.py`,
`src/cline_sdlc/features/repository_coordination/adapters/outbound/git_cli.py`, tests.

**Estimated scope:** Medium.

**Required implementation slices:**

- `2.5a` — repository root, tracked/committed input, HEAD, status, and diff observations;
- `2.5b` — branch protection, operation-state, nested-repository, and symlink/path safety.

The second slice depends on the first slice's published repository snapshot contract.

### Task 2.6: Add ignored run audit and redaction

**Description:** Create per-invocation run directories, safely establish an ignore rule,
redact sensitive values, and persist versioned summaries of sessions, attempts, command
classifications, reconciliation decisions, and terminal status.

**Acceptance criteria:**

- `.cline-sdlc/runs/<run-id>/` or the host convention is ignored before sensitive logs are
  written inside a repository.
- Existing ignore content is preserved; log files are never candidate commit paths.
- Injected tokens, credentials, and sensitive prompt fragments are absent from summaries
  and normal terminal output.

**Verification:**

- `uv run pytest tests/unit/features/run_audit/`
- `uv run pytest tests/integration/features/run_audit/`

**Dependencies:** Tasks 1.2 and 2.5.

**Likely paths:** `src/cline_sdlc/features/run_audit/application/`,
`src/cline_sdlc/features/run_audit/adapters/outbound/filesystem_writer.py`, tests.

**Estimated scope:** Medium.

### Task 2.7: Discover, classify, and execute validation commands

**Description:** Add shared orchestration behavior for discovering authoritative focused and
broad validation commands, representing them as structured executable/argument arrays,
classifying them through the balanced policy, executing permitted commands, and recording
truthful redacted evidence. Discovery follows specification/plan, repository instructions,
CI/task runners, language metadata, then blocker precedence.

**Acceptance criteria:**

- Plan authoring can request authoritative focused and broad commands without executing
  repository configuration or inventing successful evidence.
- Focused and broad runners preserve the actual command, result, exit code, and timestamp;
  commands not run are recorded as `not_run`, never `passed`.
- Unsafe, ambiguous, interactive, network-capable, or unavailable required commands block
  with actionable evidence.
- The same evidence contract is used by slice verification, final broad checks, audit
  summaries, and plan progress updates.

**Verification:**

- `uv run pytest tests/unit/features/lifecycle_orchestration/test_validation_discovery.py`
- `uv run pytest tests/integration/features/lifecycle_orchestration/test_validation_execution.py`

**Dependencies:** Tasks 2.4 and 2.5.

**Likely paths:**
`src/cline_sdlc/features/lifecycle_orchestration/application/dtos/validation.py`,
`src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/discover_validation.py`,
`src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/run_validation.py`, tests.

**Estimated scope:** Medium, implemented as separate discovery and execution slices.

### Task 2.8: Coordinate ordered no-write preflight

**Description:** Compose invocation/runtime validation, artifact and managed-path validation,
Git inspection, ignored audit setup, Cline capability probing, and required-skill probing into
one ordered preflight use case that returns an explicit stage authorization.

**Acceptance criteria:**

- Invalid invocation or artifact state is rejected before Cline probing where no probe is
  needed; repository and path safety are established before any stage-owned write.
- Audit setup may create only the minimum ignored local run destination needed to record the
  failure; no lifecycle artifact is modified.
- Any failed check starts no stage session and returns one typed, actionable preflight result.
- Contract tests assert ordering and the no-session/no-lifecycle-write guarantee for every
  failure point.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_preflight.py`

**Dependencies:** Tasks 1.5, 2.3, 2.5, and 2.6.

**Likely paths:**
`src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/preflight_stage.py`,
preflight DTOs, contract tests.

**Estimated scope:** Medium.

### Task 2.9: Add attached interactive Cline execution

**Description:** Define and implement the terminal boundary used by idea and specification
stages. Attach inherited standard streams or a portable terminal mechanism while preserving
the dedicated machine-detectable terminal outcome, finite timeout, bounded termination, and
signal behavior proven by Phase 0.

**Acceptance criteria:**

- The user can participate directly in a live Cline interview on supported macOS and Linux.
- Human conversation output cannot be mistaken for the structured terminal outcome.
- EOF, timeout, SIGINT, SIGTERM, child failure, and malformed outcome produce typed results
  and bounded cleanup.
- Contract tests use the fake executable and do not require credentials, network access, or
  an interactive CI terminal.

**Verification:**

- `uv run pytest tests/contract/features/cline_execution/test_interactive_session.py`

**Dependencies:** Tasks 2.1, 2.3, and the Phase 0 interactive transport evidence.

**Likely paths:** `src/cline_sdlc/features/cline_execution/application/ports/terminal.py`,
`src/cline_sdlc/features/cline_execution/adapters/outbound/interactive_process.py`, tests.

**Estimated scope:** Medium.

### Checkpoint C: Safe execution boundaries

- Fake-Cline subprocess contract matrix passes.
- Capability and skill failures cause no lifecycle writes.
- Retry eligibility is decided by orchestration from process and repository observations;
  the subprocess adapter has no Git dependency.
- Permission policy fails closed for the complete prohibited-operation matrix.
- Temporary-Git preflight matrix passes on supported platforms.
- Run records are ignored, redacted, and excluded from staged-path candidates.
- Ordered preflight failures start no session and modify no lifecycle artifact.
- Attached interactive execution preserves terminal access and a separate structured outcome.
- Validation discovery and execution produce truthful reusable evidence before slice work.
- Full repository quality gate passes.

## Phase 3: Artifact-producing lifecycle stages

### Task 3.1: Implement rough idea to accepted idea brief

**Description:** Compose one attached interactive idea-refinement session, require the
`idea-refine` procedure, and verify explicit acceptance plus exactly one changed artifact.

**Acceptance criteria:**

- Empty ideas fail before Cline starts.
- Completion requires an accepted outcome and a changed brief containing all required
  sections.
- Declined acceptance or declined save is blocked, not completed.
- No specification or later-stage session starts.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_idea_stage.py`

**Dependencies:** Checkpoint C.

**Additional dependencies:** Task 1.5 supplies the accepted output location; Task 2.8 owns
ordered preflight; Task 2.9 supplies attached interactive execution.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/refine_idea.py`,
stage prompt/DTO modules, contract tests.

**Estimated scope:** Medium.

### Task 3.2: Implement idea artifact to accepted specification

**Description:** Compose one attached interactive specification-author session with file
and Git preflight, repository inspection permission, explicit acceptance, and artifact
verification.

**Acceptance criteria:**

- The idea input passes tracked/committed and clean-tree checks before Cline starts.
- Completion requires an accepted, changed specification with all required sections and no
  planning-blocking unresolved decision.
- Ending without acceptance returns blocked.
- No plan author or implementation session starts.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_spec_stage.py`

**Dependencies:** Task 3.1 patterns and Checkpoint C.

**Additional dependencies:** Task 1.5 supplies the accepted output location; Task 2.8 owns
ordered preflight; Task 2.9 supplies attached interactive execution.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/create_specification.py`,
stage prompt/DTO modules, contract tests.

**Estimated scope:** Medium.

### Task 3.3: Implement initial plan authoring

**Description:** Compose a fresh plan-author session, validate the resulting material and
progress regions, state, stable slices, validation commands, and digests, and prepare the
artifact for independent review without starting implementation.

**Acceptance criteria:**

- The author inspects the specification, repository rules, existing patterns, affected
  files, and authoritative validation commands.
- The resulting plan contains all required human-readable sections, one valid state block,
  independently verifiable stable slices, and current digests.
- Generated artifacts contain enough objective, scope, decisions, verification, state, and
  recovery context to be understood without prior Cline sessions or checkpoints.
- No reviewer or implementation session starts inside this task.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_plan_authoring.py`

**Dependencies:** Checkpoint C, Tasks 1.3–1.5, Task 2.7 for authoritative validation
discovery, and Task 2.8 for ordered preflight.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/author_plan.py`,
author prompt/DTO modules, tests.

**Estimated scope:** Medium.

### Task 3.4: Implement initial independent plan review

**Description:** Start one fresh read-only reviewer session, validate its complete findings
outcome, reconcile findings into progress content, and mark the plan ready or
changes-required without allowing reviewer writes.

**Acceptance criteria:**

- Author and reviewer use separate fresh contexts.
- Reviewer input excludes author private reasoning, and observed reviewer writes block the
  stage.
- A ready first review marks the plan ready without an unnecessary revision.
- Finding records pass schema validation, retain stable IDs, and include evidence and
  required correction.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_plan_review.py -k initial`

**Dependencies:** Task 3.3.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/review_plan.py`,
reviewer prompt/DTO modules, tests.

**Estimated scope:** Medium.

### Task 3.5: Add bounded revision and blocked-plan behavior

**Description:** Revise material plan content in fresh author sessions, re-review each
material revision in a fresh reviewer context, and enforce the initial review plus at most
two revision/re-review cycles.

**Acceptance criteria:**

- Material revision increments revision and recomputes the digest.
- Prior findings and dispositions are verified; IDs are not silently reused.
- Unattended flow cannot accept blocking/major risk or not-applicable dispositions.
- Exhaustion records unresolved findings, marks the plan blocked, returns blocked exit
  category, and starts no implementation session.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_plan_review.py -k revision`

**Dependencies:** Task 3.4.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/revise_plan.py`,
review-loop service, tests.

**Estimated scope:** Medium.

### Checkpoint D: Artifact boundaries

- Every valid input implemented so far stops at exactly its next boundary.
- Interactive stages require explicit acceptance.
- Plan review is independent, read-only, bounded, and findings remain traceable.
- Artifacts are left uncommitted for human review as specified.
- Generated artifacts are understandable from committed content without chat history or
  Cline Checkpoints.
- Full repository quality gate passes.

## Phase 4: Serial implementation transactions

### Task 4.1: Reconcile progress and select the next slice

**Description:** Recompute plan/specification digests, derive unique owning commits from
trailers, record the bounded invocation approval, verify progress/evidence, reconcile partial
state and dirty paths, and select a resumable or earliest dependency-ready slice.

**Acceptance criteria:**

- A valid partial slice is selected before all other work.
- Completed slices require one unique reachable owning commit with the expected trailers
  and committed plan transition.
- Ambiguous ownership, missing files, conflicting evidence, or material divergence stops
  without writes.
- Re-running after a committed slice never repeats it.
- Before reconciliation or any implementation session, the ignored run summary records one
  immutable invocation approval containing the run ID, balanced profile, starting HEAD, UTC
  timestamp, specification digest, material digest, and remediation-envelope applicability.
- Every later slice, remediation, broad-check, and finalization decision references that
  approval record and stops when either digest diverges.

**Verification:**

- `uv run pytest tests/unit/features/lifecycle_orchestration/test_slice_selection.py`
- `uv run pytest tests/integration/features/repository_coordination/test_reconciliation.py`

**Dependencies:** Checkpoints C and D, including Task 2.8 ordered preflight.

**Likely paths:** `src/cline_sdlc/features/repository_coordination/application/use_cases/reconcile_plan.py`,
`src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/select_slice.py`, tests.

**Estimated scope:** Medium, split pure selection from Git reconciliation.

### Task 4.2: Execute one bounded slice session

**Description:** Start a fresh session containing only the approved current slice, collect
its typed outcome and operation records, and permit at most one bounded focused-validation
repair attempt without deciding commit eligibility.

**Acceptance criteria:**

- Session context is bounded to the accepted specification, ready plan, current slice,
  required repository context, policy, verification, and outcome contract.
- The session reports changed paths and every validation it ran through the typed outcome.
- Focused validation executes through Task 2.7 and passes or one bounded repair attempt is
  exhausted.
- Failed or interrupted writes are left uncommitted and attributable recovery state is
  recorded safely.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_slice_execution.py`

**Dependencies:** Task 4.1 and Tasks 2.1–2.9.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/execute_slice.py`,
slice-session DTOs, tests.

**Estimated scope:** Medium.

### Task 4.3: Independently reconcile one slice

**Description:** Compare the typed session outcome with observed changed paths, validation
evidence, HEAD, approved material, and permitted operation records. Produce either an
explicit commit candidate or attributable partial-slice recovery state.

**Acceptance criteria:**

- Reported changed paths equal observed in-scope paths; unexpected paths, ambiguous
  ownership, prohibited operations, or HEAD movement reject the commit candidate.
- Passing focused evidence is verified independently rather than accepted from prose or
  checkboxes.
- Material or specification drift invalidates invocation approval and starts no later slice.
- Failed reconciliation leaves all writes uncommitted and records safe recovery details.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_slice_reconciliation.py`

**Dependencies:** Task 4.2.

**Likely paths:**
`src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/reconcile_slice.py`,
reconciliation DTOs, tests.

**Estimated scope:** Medium.

### Task 4.4: Create one explicit atomic slice commit

**Description:** Apply progress-only plan updates, stage explicit reconciled paths, create
one non-interactive commit with required trailers and hooks enabled, and verify ownership.

**Acceptance criteria:**

- One commit contains exactly one slice, its tests/docs/configuration, evidence, and plan
  progress; unrelated paths and run logs are excluded.
- Required work, slice, kind, and digest trailers are present and unique.
- Hook failure leaves verified changes uncommitted, records partial state when safe, and
  returns failure without bypassing hooks.
- No commit embeds its own object identifier in plan state.

**Verification:**

- `uv run pytest tests/integration/features/repository_coordination/test_slice_commit.py`

**Dependencies:** Task 4.3.

**Likely paths:** `src/cline_sdlc/features/repository_coordination/application/use_cases/commit_slice.py`,
Git adapter commit support, tests.

**Estimated scope:** Medium.

### Task 4.5: Add serial transaction looping

**Description:** Repeat fresh-session transactions while approved digests remain valid,
selecting no later work after a blocked or failed transaction.

**Acceptance criteria:**

- At least three low-risk slices run serially with one fresh session and commit per slice.
- A terminal non-completed result starts no later slice.
- The invocation approval record remains unchanged and valid for every iteration.
- Unrelated later human commits are preserved when they do not alter approved assumptions.

**Verification:**

- `uv run pytest tests/e2e/test_plan_implementation_serial.py`

**Dependencies:** Task 4.4.

**Likely paths:**
`src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/implement_plan.py`,
end-to-end tests.

**Estimated scope:** Medium.

### Task 4.6: Add signal handling and cross-process resume

**Description:** Handle SIGINT/SIGTERM and timeout with bounded child termination, reconcile
observable state, and resume valid partial slice or partial finalization work from a new
process before selecting any new work.

**Acceptance criteria:**

- Interruption starts no later slice, creates no commit, and records observable state.
- Resume requires exact or explainable HEAD and dirty-path reconciliation and resumes the
  same slice first.
- Abrupt termination recovery relies on plan, Git, and optional ignored summaries rather
  than treating process identifiers or lock files as authoritative.
- Conflicting ownership stops without modifying lifecycle artifacts.

**Verification:**

- `uv run pytest tests/e2e/test_plan_implementation_resume.py`

**Dependencies:** Task 4.5.

**Likely paths:**
`src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/resume_plan.py`,
bootstrap signal adapter, end-to-end tests.

**Estimated scope:** Medium.

### Checkpoint E: Core implementation loop

- A disposable repository completes three serial slices with one attributable commit each.
- Injected timeout, signal, malformed outcome, validation failure, hook failure, and
  material drift stop at their documented limits.
- A valid partial slice resumes before new work; completed slices are not repeated.
- No unrelated change or run log enters an orchestrator commit.
- Full repository quality gate passes.

## Phase 5: Final quality, remediation, and completion

### Task 5.1: Execute and verify final broad validation

**Description:** Reuse Task 2.7 discovery, classification, execution, and evidence contracts
to run every required repository-wide check after planned slices and before final review.

**Acceptance criteria:**

- Missing safe authoritative broad checks becomes a blocker.
- Commands are recorded without secrets and retain actual exit/result status; a command that
  was not run is never marked passed.
- Final completion requires every required broad check to pass.
- The broad evidence set is tied to the current invocation approval and commit range.

**Verification:**

- `uv run pytest tests/integration/features/lifecycle_orchestration/test_final_validation.py`

**Dependencies:** Checkpoint E and Task 2.7.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/run_final_validation.py`,
tests.

**Estimated scope:** Medium.

### Task 5.2: Run fresh final review and classify remediation

**Description:** Run a fresh read-only final reviewer with approved artifacts, relevant
commit range, repository rules, and broad results. Convert only eligible non-conformance
findings into bounded progress-only remediation records.

**Acceptance criteria:**

- Reviewer writes are rejected and findings use stable `FINAL-` IDs.
- Each remediation cites an approved requirement, bounded paths, correction, verification,
  status, and attempt count.
- New scope, architecture, dependencies, contracts, migrations, or sequencing decisions
  block rather than becoming remediation.

**Verification:**

- `uv run pytest tests/contract/features/lifecycle_orchestration/test_final_review.py`

**Dependencies:** Task 5.1.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/final_review.py`,
remediation DTO/domain module, tests.

**Estimated scope:** Medium.

### Task 5.3: Execute remediation and confirmation review

**Description:** Execute each accepted remediation once under normal fresh-session,
validation, reconciliation, and atomic commit rules, then run exactly one fresh read-only
confirmation review and affected broad checks.

**Acceptance criteria:**

- Remediation preserves the originally approved material digest and uses its finding ID as
  stable slice identity.
- Each finding receives at most one implementation attempt.
- Repeated, new blocking, material, or unresolved major findings block completion.
- Latest passing affected broad evidence supersedes earlier evidence.

**Verification:**

- `uv run pytest tests/e2e/test_final_review_remediation.py`

**Dependencies:** Task 5.2 and Tasks 4.2–4.4 transaction behavior.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/remediate.py`,
confirmation review orchestration, tests.

**Estimated scope:** Medium.

### Task 5.4: Finalize the plan and support complete no-op

**Description:** Create exactly one progress-only finalization commit after clean review and
broad checks, and verify already-complete plans through state, digest, and reachable commit
history without starting a session.

**Acceptance criteria:**

- Finalization records complete phase, final evidence, UTC completion time, and required
  finalization trailers.
- Commit failure leaves a recoverable partial finalization and never reports complete.
- A complete plan requires one unique reachable finalization commit whose plan blob
  introduced completion.
- A verified complete plan returns completed with no writes, Cline session, or commit.

**Verification:**

- `uv run pytest tests/integration/features/repository_coordination/test_finalization.py`
- `uv run pytest tests/e2e/test_complete_plan_noop.py`

**Dependencies:** Task 5.3.

**Likely paths:** `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/finalize_plan.py`,
repository finalization support, tests.

**Estimated scope:** Medium.

## Phase 6: Portability, documentation, and rollout evidence

### Task 6.1: Build portable end-to-end host fixtures

**Description:** Add disposable host-repository fixtures that exercise all four input
forms, use artifact locations and validation commands different from this repository, and
inject the required stop, recovery, and secret-safety scenarios without external effects.

**Acceptance criteria:**

- Every input reaches only its specified artifact boundary.
- One unrelated host fixture uses non-default artifact paths and a different project
  command surface without importing this repository's architecture or tooling assumptions.
- Scenarios cover malformed outcome, prohibited operation, interruption/resume, material
  drift, remediable finding, material finding, and an injected test secret.
- Generated artifacts and summaries remain understandable without prior session history.

**Verification:**

- `uv run pytest tests/e2e/`
- Inspect fixture Git histories for exact slice/finalization commit ownership and absence of
  the injected secret.

**Dependencies:** Task 5.4.

**Likely paths:** `tests/e2e/conftest.py`, input-stage workflow tests,
`tests/e2e/fixtures/external_host/`, fixture documentation.

**Estimated scope:** Medium per workflow increment; split the four inputs and implementation
recovery scenarios into separate test changes rather than one large task pass.

### Task 6.2: Complete user and operator documentation

**Description:** Update project-facing documentation for installation, invocation,
defaults, stage boundaries, balanced permissions, exit categories, run logs, recovery,
configuration, limitations, and the supervised proof requirement.

**Acceptance criteria:**

- `README.md` documents `uvx` installation/execution, every supported option, the 30-minute
  default timeout, examples for all four inputs, JSON output, and stable exit categories.
- Documentation explains protected branches, prohibited operations, artifact commit
  requirements, ignored logs, blockers, partial-slice recovery, and no automatic network or
  dependency installation.
- Capability-spike conclusions and the current unattended-readiness status are linked from
  the README.
- Any environment-backed configuration is synchronized with a canonical settings reference
  and `.env.example`; otherwise documentation states that none is required.

**Verification:**

- Review every documented command against `--help` output and packaging smoke execution.
- `git --no-pager diff --check`

**Dependencies:** Tasks 6.1 and 2.6.

**Likely paths:** `README.md`, `docs/` capability/operations references, `.env.example` only
if runtime environment settings exist.

**Estimated scope:** Medium.

### Task 6.3: Add cross-platform packaging and quality CI

**Description:** Extend CI to prove supported Python/platform behavior, distribution build,
the local console entry point through `uvx`, and the automated test layers that do not need
real Cline credentials or network access.

**Acceptance criteria:**

- CI covers supported macOS and Linux execution with Python 3.14.
- Formatting, linting, mypy, unit, contract, Git integration, portable end-to-end, build,
  and `uvx --from . cline-sdlc --help` checks are explicit.
- Default CI does not invoke real Cline, require credentials, mutate global Git config, or
  perform remote lifecycle effects.
- Dependency installation uses the locked project state and fails on drift.

**Verification:**

- Validate workflow syntax and run the equivalent full local quality and packaging gate.
- Confirm CI test selection includes the external-host portability fixture.

**Dependencies:** Tasks 6.1 and 6.2.

**Likely paths:** `.github/workflows/ci-cd.yaml`, `pyproject.toml` test markers/configuration,
packaging smoke tests.

**Estimated scope:** Medium.

### Task 6.4: Execute and record the supervised rollout proof

**Description:** Run the specification's manual proof matrix against a disposable
non-production repository using the supported real Cline CLI and record redacted evidence
for the architecture and unattended-readiness decision.

**Acceptance criteria:**

- All four stage inputs are exercised, and at least three serial low-risk implementation
  slices create one local commit each.
- One interrupted slice resumes from a new process; one malformed outcome is bounded; one
  prohibited operation stops; and one post-approval material edit invalidates execution.
- Final review exercises one eligible remediation and one material blocker.
- Artifacts, run summaries, terminal output, and commits contain no injected test secret.
- Failure of structured outcomes, permission enforcement, or dirty-tree recovery records a
  blocked readiness decision and triggers SDK-direction review instead of a waiver.

**Verification:**

- Review the redacted proof report, run summaries, plan transitions, and Git history against
  specification rollout steps 1–8.
- Product owner records whether the CLI implementation may be described as unattended-ready.

**Dependencies:** Tasks 6.1–6.3 and successful Checkpoint A capability evidence.

**Likely paths:** `docs/research/cline-sdlc-rollout-proof.md` and ignored local run records.

**Estimated scope:** Medium, performed as a supervised validation session rather than an
automated default-suite test.

### Checkpoint F: Portable MVP proof

- All four input forms reach only their intended artifact boundary.
- The rollout scenarios in the specification are exercised in disposable repositories,
  including malformed output, prohibited operation, interruption/resume, material drift,
  remediable finding, material finding, and injected secret.
- An unrelated host fixture uses different artifact paths and project validation commands.
- macOS and Linux CI run formatting, linting, mypy, unit, contract, integration, end-to-end,
  build, and packaging smoke checks as appropriate.
- `uvx --from . cline-sdlc --help` succeeds.
- A manually supervised non-production proof confirms at least three serial low-risk slices.
- The project is not described as unattended-ready until all rollout evidence is reviewed.
- Tasks 6.1–6.4 are complete and their evidence is linked from project documentation.

## Specification acceptance traceability

This matrix maps each specification acceptance group to the tasks that establish the
behavior and the checkpoint that authorizes dependent work. Detailed scenario assertions
remain in the task-level tests rather than being duplicated here.

| Specification acceptance group | Primary tasks | Checkpoint/evidence |
| --- | --- | --- |
| CLI and stage boundaries | 1.1, 2.8, 3.1–3.5, 6.1 | B, D, F |
| Idea and specification stages | 1.5, 2.9, 3.1–3.2 | C, D, F |
| Plan authoring and review | 1.2–1.5, 2.7–2.8, 3.3–3.5 | B, D |
| State and approval | 1.3–1.4, 4.1, 4.3, 5.3–5.4 | B, E, F |
| Implementation and Git safety | 2.5, 4.1–4.6, 5.4 | C, E, F |
| Permissions and stop behavior | 0.3, 2.2–2.4, 2.7–2.9, 4.3 | A, C, E |
| Failure and resumption | 0.2–0.3, 2.1–2.2, 4.2–4.6 | A, C, E, F |
| Final quality gate | 2.7, 5.1–5.4 | E, F |
| Auditability and portability | 1.5, 2.6, 4.1, 6.1–6.4 | C, F |
| Packaging and rollout proof | 1.1c, 6.1–6.4 | F |

## Cross-cutting test strategy

- **Unit:** CLI selection, schemas, state transitions, digests, policy, path normalization,
  branch protection, retry limits, and slice selection.
- **Property/parameterized:** line endings, malicious paths, duplicate keys, state invariant
  matrices, command-classifier evasions, and digest stability.
- **Subprocess contract:** fake Cline success, malformed/duplicate/conflicting outcomes,
  timeout, interruption, approval request, and controlled writes.
- **Git integration:** disposable repositories for status, operation state, hooks, commits,
  trailers, HEAD movement, partial slices, resume, and finalization.
- **End-to-end:** all four inputs and stop boundaries with no external effects.
- **Portability:** an external-host fixture with different paths, language metadata, and
  validation commands.
- **Packaging:** wheel/sdist build and local `uvx --from .` console invocation.
- **Manual proof:** isolated real Cline exercises; never part of the default test suite.

Tests must not use live remote services, production credentials, deployment, remote pushes,
or the developer's global Git configuration.

## Documentation and operational deliverables

- Update `README.md` with installation, all CLI options/defaults, stage boundaries, balanced
  permissions, exit categories, examples, and troubleshooting.
- Document supported configuration and protected-branch customization; add `.env.example`
  only if environment-backed settings are introduced.
- Maintain the capability-spike report and proof-of-concept limitations.
- Record a durable ADR if the Phase 0 gate changes the CLI-wrapper architecture or if an
  implementation discovery changes a material boundary.
- Keep run-log format and redaction behavior documented without exposing sensitive data.
- Update CI for the final packaging smoke and supported platform matrix.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Cline CLI cannot mediate operations before execution | Critical | Phase 0 hard gate; stop and review SDK direction |
| No dedicated reliable terminal outcome channel | Critical | Prove transport before implementation; never infer success from prose |
| Interrupted writes cannot be attributed safely | Critical | Temporary-repo signal spike and fail-closed reconciliation |
| Plan Markdown parser becomes permissive or ambiguous | High | Strict regions, schema validation, golden vectors, malicious-input tests |
| Git commits include unrelated human work | High | Explicit path staging and observed/reported ownership reconciliation |
| Command classifier is bypassed through wrappers | High | Structured argv inspection, adversarial matrix, deny unknown operations |
| Plan implementation tasks grow beyond reviewable scope | Medium | Keep each increment near 3–5 files and split adapters/use cases separately |
| Real-Cline tests become flaky or require credentials | Medium | Keep them supervised; default suite uses fake Cline only |
| Host repositories lack authoritative validation commands | Medium | Apply discovery precedence and block rather than invent evidence |
| Sensitive content leaks into logs or commits | High | Allowlisted fields, redaction tests, ignored run directory before writes |

## Assumptions

- This plan treats the supplied specification as the authoritative planning source. Its
  current draft status must become explicitly accepted before Checkpoint A authorizes
  production feature implementation.
- The user will explicitly approve any runtime dependency before it is added.
- Development and automated commits will occur on a non-protected feature branch or in
  disposable repositories, not on `master`.
- The host provides Git, Python 3.14+, `uvx`, and a separately installed compatible Cline
  CLI where real execution is requested.
- The Phase 0 capability evidence determines whether Tasks 1.1 onward remain valid.

## Open questions requiring resolution during planned work

1. Which concrete safe YAML library best satisfies duplicate-key rejection on Python 3.14?
2. Which Cline hook or event mechanism can enforce operation policy before execution?
3. What minimum Cline CLI version first satisfies every proven capability?
4. Does the CLI provide a dedicated outcome file/channel, or must a supported hook supply it?
5. Can required skills be probed without invoking network-backed `npx` behavior?
6. Does the capability spike justify embedded findings, or is one adjacent artifact safer?
7. What ignore-file insertion strategy is portable when `.git/info/exclude` or repository
   policy is preferred over modifying `.gitignore`?

Questions 2–5 are Phase 0 gate questions. Any answer that changes approval semantics,
state ownership, artifact boundaries, allowed effects, Git safety, or recovery requires
specification review before implementation proceeds.

## Required implementation discipline

- Treat this plan as a living document. Update progress, evidence, blockers, deviations,
  and newly discovered work after every completed task or meaningful scope change.
- Preserve stable task identifiers. Add or supersede work explicitly; do not silently reuse
  an identifier for different material work.
- Write focused tests before or with behavior changes, run the narrowest relevant check
  first, and run the full quality gate at every checkpoint.
- Do not mix opportunistic refactors with the active task.
- Do not proceed through a blocked checkpoint or silently broaden a slice.
- Do not weaken structured outcomes, permissions, Git safety, approval, or recovery when
  implementation proves difficult.

<!-- cline-sdlc-material:end -->

<!-- cline-sdlc-progress:start -->

## Progress tracking

### Phase 0

- [x] Task 0.1: Restore a trustworthy project baseline.
- [x] Task 0.2: Add a deterministic fake-Cline contract harness.
- [x] Task 0.3: Prove the real Cline CLI contracts.
- [ ] Checkpoint A: Architecture viability accepted.

### Phase 1

- [ ] Task 1.1: Define CLI invocation and terminal result contracts.
- [ ] Task 1.2: Define session outcome and finding schemas.
- [ ] Task 1.3: Parse and validate plan lifecycle state.
- [ ] Task 1.4: Implement artifact regions and deterministic digests.
- [ ] Task 1.5: Discover artifact locations and portable defaults.
- [ ] Checkpoint B: Artifact and public contract accepted.

### Phase 2

- [ ] Task 2.1: Implement the Cline subprocess adapter.
- [ ] Task 2.2: Coordinate bounded session attempts.
- [ ] Task 2.3: Add capability and skill preflight.
- [ ] Task 2.4: Implement the balanced operation policy.
- [ ] Task 2.5: Implement Git inspection and branch safety.
- [ ] Task 2.6: Add ignored run audit and redaction.
- [ ] Task 2.7: Discover, classify, and execute validation commands.
- [ ] Task 2.8: Coordinate ordered no-write preflight.
- [ ] Task 2.9: Add attached interactive Cline execution.
- [ ] Checkpoint C: Safe execution boundaries accepted.

### Phase 3

- [ ] Task 3.1: Implement rough idea to accepted idea brief.
- [ ] Task 3.2: Implement idea artifact to accepted specification.
- [ ] Task 3.3: Implement initial plan authoring.
- [ ] Task 3.4: Implement initial independent plan review.
- [ ] Task 3.5: Add bounded revision and blocked-plan behavior.
- [ ] Checkpoint D: Artifact boundaries accepted.

### Phase 4

- [ ] Task 4.1: Reconcile progress and select the next slice.
- [ ] Task 4.2: Execute one bounded slice session.
- [ ] Task 4.3: Independently reconcile one slice.
- [ ] Task 4.4: Create one explicit atomic slice commit.
- [ ] Task 4.5: Add serial transaction looping.
- [ ] Task 4.6: Add signal handling and cross-process resume.
- [ ] Checkpoint E: Core implementation loop accepted.

### Phase 5

- [ ] Task 5.1: Execute and verify final broad validation.
- [ ] Task 5.2: Run fresh final review and classify remediation.
- [ ] Task 5.3: Execute remediation and confirmation review.
- [ ] Task 5.4: Finalize the plan and support complete no-op.

### Phase 6

- [ ] Task 6.1: Build portable end-to-end host fixtures.
- [ ] Task 6.2: Complete user and operator documentation.
- [ ] Task 6.3: Add cross-platform packaging and quality CI.
- [ ] Task 6.4: Execute and record the supervised rollout proof.
- [ ] Checkpoint F: Portable MVP proof accepted.

### Current planning status

- The specification and repository baseline were inspected on 2026-07-23.
- The redundant hard-coded package-version test was removed by explicit user decision.
  Release tag `v0.0.1`, package metadata, built distributions, and an import smoke check
  agree on version `0.0.1`; Ruff formatting and linting, mypy, and the package build pass.
- Task 0.2 added a deterministic test-only fake Cline executable and typed fixture API. Its
  explicit scenarios cover valid, missing, malformed, duplicate, conflicting,
  approval-required, delayed, interrupted, controlled-write, and non-zero-exit behavior
  without real Cline, network access, or developer repository state.
- The focused fake-Cline contract suite passes 11 tests on macOS, including timeout and
  SIGTERM behavior. The full project test suite is now green, so Task 0.1 is complete under
  the documented package-version-test waiver and Task 0.2 is complete.
- Task 0.3 is the next authorized implementation slice. It must remain a supervised
  capability proof and may not weaken the specification contracts if real Cline behavior
  is insufficient.
- Task 0.3 started with a minimal `cline_execution` capability-evidence slice:
  typed capability observations, a capability report, an application-owned probe port,
  the `ProveClineCliContracts` use case, and a subprocess-backed help/version probe that
  uses argument-array execution with a finite timeout.
- The local supervised probe observed Cline CLI `3.0.46` at
  `/Users/owinter/.nvm/versions/node/v22.22.3/bin/cline`. Its help output advertises
  JSON output, finite timeout configuration, explicit working directory selection,
  isolated data directories, hook directories, and skill management.
- Task 0.3 recorded the initial `docs/research/cline-cli-capability-spike.md` evidence
  report. The full task remains incomplete and Checkpoint A remains blocked because
  help/version probes do not prove exactly-one terminal outcome emission, pre-execution
  permission mediation, interruption recovery observability, or skill probing without
  unintended network-backed behavior.
- The focused `cline_execution` unit suite passes 4 tests, and the full project test suite
  passes 15 tests. Ruff formatting, Ruff linting, mypy, and `git --no-pager diff --check`
  pass for the current Task 0.3 slice.
- Task 0.3 continued with deterministic required-skill probing in the subprocess capability
  adapter. The existing `CapabilityProbeRequest.required_skills` field now produces typed
  per-skill observations from a `skill list` subprocess check, proves available fake skills,
  and fails closed for missing or unsuccessful skill probes.
- This follow-up strengthens the automated evidence model but does not complete Checkpoint A:
  real Cline skill probing without unintended network-backed behavior, terminal outcome
  emission, pre-execution permission mediation, and interruption observability remain
  supervised proof requirements.
- The focused `cline_execution` unit suite now passes 6 tests after the required-skill
  follow-up slice.
- The follow-up slice quality gate passed: Ruff fixes/checks and formatting, mypy, the full
  17-test suite, and `git --no-pager diff --check` completed successfully.
- Task 0.3 continued with an explicit fake-backed supervised session probe path. The
  `CapabilityProbeRequest.supervised_session_probe` option now lets callers supply isolated
  repository, data, and hook directories plus a bounded timeout for a session probe. The
  subprocess adapter can prove exactly-one terminal outcome detection, permission-mediation
  evidence, and interruption-recovery evidence from deterministic fake output while failing
  closed for duplicate outcomes and timeouts.
- This slice still does not complete Task 0.3 or Checkpoint A: the proof path is automated and
  deterministic, but real installed Cline behavior for terminal outcome emission,
  pre-execution permission mediation, interruption recovery, and network-free skill probing
  still needs supervised evidence and product-owner review.
- The focused `cline_execution` unit suite now passes 9 tests after the fake-backed supervised
  session probe slice.
- The fake-backed supervised session probe slice quality gate passed: Ruff fixes/checks and
  formatting, mypy, the full 20-test suite, and `git --no-pager diff --check` completed
  successfully.
- Task 0.3 continued with a manual supervised real-Cline proof command under
  `tests/manual/cline_execution/prove_real_cline_capability.py`. The command requires an
  explicit Cline command plus disposable repository, isolated data, and hook directories;
  invokes the existing capability proof use case and subprocess adapter; and emits one
  redacted JSON capability report with blocking observations and an exit code suitable for
  supervised review.
- The new proof command is covered by fake-backed unit tests and does not run real Cline,
  require credentials, require network access, or touch developer repository state during
  automated validation. Task 0.3 and Checkpoint A remain incomplete until the command is run
  against the installed Cline executable in a disposable repository and the resulting evidence
  proves or rejects the critical contracts.
- Task 0.3 completed the supervised real-Cline proof on 2026-07-23 using Cline `3.0.46` at
  `/Users/owinter/.nvm/versions/node/v22.22.3/bin/cline`, a disposable Git repository, and
  isolated Cline data and hook directories under the ignored `.cline-sdlc-proof/` proof
  directory. The command exited `1` with a redacted typed report: required skills were
  reported missing for `idea-refine`, `spec-driven-development`, `planning-and-task-breakdown`,
  and `code-review-and-quality`; the session emitted `0` parseable terminal outcomes; and
  pre-execution permission mediation plus interruption recovery observability remained
  unproven.
- Task 0.3 is therefore complete as a proof/rejection slice, but Checkpoint A remains blocked.
  Tasks 1.1 and later are still unauthorized until the product owner reviews the evidence and
  either revises the CLI-wrapper proof path, establishes supported Cline configuration that
  proves the critical contracts, or makes an SDK-direction decision.
- Independent review iteration 1 found sequencing, boundary, sizing, and traceability gaps.
  Plan revision 2 resolves those findings through earlier validation support, ordered
  preflight, attached-interactive execution, explicit invocation approval, public contract
  ownership, smaller Phase 4 transactions, and acceptance traceability.
- No implementation task is authorized beyond Phase 0 before Checkpoint A passes.

### Plan-review findings

- id: PLAN-001
  severity: blocking
  status: resolved
  summary: Focused validation support was scheduled after slice execution required it.
  evidence: Revision 1 placed validation discovery and execution only in Task 5.1.
  required_correction: Establish reusable discovery, execution, and evidence contracts before plan authoring and slice execution.
  affected_sections:
    - Phase 2
    - Task 3.3
    - Task 4.2
    - Task 5.1
  disposition: Added Task 2.7 and narrowed Task 5.1 to final broad validation.
- id: PLAN-002
  severity: major
  status: resolved
  summary: The plan did not define one ordered no-write preflight transaction or attached interactive transport boundary.
  evidence: Capability, Git, audit, artifact, and terminal responsibilities were distributed without an orchestration order or interactive contract.
  required_correction: Add explicit preflight and interactive-execution tasks with failure-order and platform tests.
  affected_sections:
    - Phase 2
    - Tasks 3.1 and 3.2
  disposition: Added Tasks 2.8 and 2.9 and made interactive stages depend on them.
- id: PLAN-003
  severity: major
  status: resolved
  summary: Invocation approval and cross-slice contract ownership were insufficiently explicit.
  evidence: Revision 1 recomputed digests but did not persist the bounded approval record or assign several shared boundary types.
  required_correction: Define the approval audit record and a public contract ownership map.
  affected_sections:
    - Architecture
    - Material decisions
    - Task 4.1
  disposition: Added the ownership table, approval decision, and Task 4.1 acceptance criteria.
- id: PLAN-004
  severity: major
  status: resolved
  summary: Several implementation tasks were too broad and acceptance coverage lacked a concise mapping.
  evidence: Tasks 1.1, 2.5, 4.2, and 4.4 combined unrelated responsibilities, and no specification acceptance matrix existed.
  required_correction: Split broad transactions and add task-to-acceptance traceability.
  affected_sections:
    - Tasks 1.1 and 2.5
    - Phase 4
    - Specification acceptance traceability
  disposition: Added required sub-slices, split Phase 4 into Tasks 4.2–4.6, and added the traceability matrix.

```cline-sdlc-state
schema_version: 1
work_id: cline-sdlc-orchestrator
profile: balanced
phase: reviewing
specification: docs/specs/cline-sdlc-orchestrator-spec.md
specification_digest: sha256:07f4125ea4b2a860595fccd87f6d049f9f01b2ab716e36536095fb4be0d3d962
plan_revision: 2
review_iteration: 1
review_readiness: changes_required
digest_schema_version: 1
material_digest: sha256:4f3efa4a1dbf4705cc33e6260196b4dbf36495f9863fcf1c718998a6011f18c3
current_task: null
current_slice: null
slice_start_commit: null
partial_slice_paths: []
completed_slices: []
remediation_records: []
validation_evidence:
  - slice_id: task-0.1
    command: uv run ruff format --check .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:31:40Z
  - slice_id: task-0.1
    command: uv run ruff check .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:31:40Z
  - slice_id: task-0.1
    command: uv run mypy .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:31:40Z
  - slice_id: task-0.1
    command: uv run pytest
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:41:00Z
  - slice_id: task-0.1
    command: uv build
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:31:40Z
  - slice_id: task-0.1
    command: >-
      uv run python -c "import cline_sdlc; assert cline_sdlc.__version__ == '0.0.1'; print(cline_sdlc.__version__)"
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:31:40Z
  - slice_id: task-0.2
    command: uv run pytest tests/contract/features/cline_execution/
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:41:00Z
  - slice_id: task-0.2
    command: uv run ruff format --check .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:41:00Z
  - slice_id: task-0.2
    command: uv run ruff check .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:41:00Z
  - slice_id: task-0.2
    command: uv run mypy .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:41:00Z
  - slice_id: task-0.2
    command: uv run pytest
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:41:00Z
  - slice_id: task-0.2
    command: uv build
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:41:00Z
  - slice_id: task-0.2
    command: git --no-pager diff --check
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:41:00Z
  - slice_id: task-0.3
    command: uv run pytest tests/unit/features/cline_execution/
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:57:50Z
  - slice_id: task-0.3
    command: uv run ruff check . --fix
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:57:50Z
  - slice_id: task-0.3
    command: uv run ruff format .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:57:50Z
  - slice_id: task-0.3
    command: uv run ruff check .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:57:50Z
  - slice_id: task-0.3
    command: uv run mypy .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:57:50Z
  - slice_id: task-0.3
    command: uv run pytest
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:57:58Z
  - slice_id: task-0.3
    command: git --no-pager diff --check
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T20:57:58Z
  - slice_id: task-0.3-required-skill-probing
    command: uv run pytest tests/unit/features/cline_execution/
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:03:40Z
  - slice_id: task-0.3-required-skill-probing
    command: uv run ruff check . --fix
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:04:20Z
  - slice_id: task-0.3-required-skill-probing
    command: uv run ruff format .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:04:20Z
  - slice_id: task-0.3-required-skill-probing
    command: uv run ruff check .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:04:20Z
  - slice_id: task-0.3-required-skill-probing
    command: uv run mypy .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:04:20Z
  - slice_id: task-0.3-required-skill-probing
    command: uv run pytest
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:04:20Z
  - slice_id: task-0.3-required-skill-probing
    command: git --no-pager diff --check
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:04:20Z
  - slice_id: task-0.3-fake-backed-supervised-session-probe
    command: uv run pytest tests/unit/features/cline_execution/
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:08:42Z
  - slice_id: task-0.3-fake-backed-supervised-session-probe
    command: uv run ruff check . --fix
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:10:07Z
  - slice_id: task-0.3-fake-backed-supervised-session-probe
    command: uv run ruff format .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:10:07Z
  - slice_id: task-0.3-fake-backed-supervised-session-probe
    command: uv run ruff check .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:10:07Z
  - slice_id: task-0.3-fake-backed-supervised-session-probe
    command: uv run mypy .
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:10:07Z
  - slice_id: task-0.3-fake-backed-supervised-session-probe
    command: uv run pytest
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:10:07Z
  - slice_id: task-0.3-fake-backed-supervised-session-probe
    command: git --no-pager diff --check
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:10:07Z
  - slice_id: task-0.3-real-cline-proof-command
    command: uv run pytest tests/unit/features/cline_execution/manual/test_prove_real_cline_capability.py
    result: passed
    exit_code: 0
    recorded_at: 2026-07-23T21:17:05Z
  - slice_id: task-0.3-supervised-real-cline-proof
    command: >-
      uv run python tests/manual/cline_execution/prove_real_cline_capability.py --cline-command /Users/owinter/.nvm/versions/node/v22.22.3/bin/cline --repository-root .cline-sdlc-proof/runs/20260723T212225Z/repo --data-directory .cline-sdlc-proof/runs/20260723T212225Z/data --hooks-directory .cline-sdlc-proof/runs/20260723T212225Z/hooks --required-skill idea-refine --required-skill spec-driven-development --required-skill planning-and-task-breakdown --required-skill code-review-and-quality
    result: failed
    exit_code: 1
    recorded_at: 2026-07-23T21:22:57Z
blocker:
  code: cline_cli_critical_contracts_rejected
  summary: The supervised real-Cline proof command ran against Cline 3.0.46 in a disposable repository with isolated data and hooks and exited 1; required skills were reported missing, the session emitted 0 parseable terminal outcomes, and pre-execution permission mediation plus interruption recovery observability remained unproven. Task 0.3 is complete as a proof/rejection slice, but Checkpoint A cannot authorize Tasks 1.1 and later until product review decides whether to revise the CLI-wrapper proof path, configure/prove supported Cline behavior, or move toward an SDK direction.
  details_path: docs/research/cline-cli-capability-spike.md
  proposed_operation: null
  recorded_at: 2026-07-23T21:22:57Z
created_at: 2026-07-23T19:23:00Z
updated_at: 2026-07-23T21:22:57Z
completed_at: null
```

<!-- cline-sdlc-progress:end -->
