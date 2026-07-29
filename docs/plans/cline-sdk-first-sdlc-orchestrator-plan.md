# Implementation Plan: Cline SDK-First SDLC Orchestrator

## Status

- State: Draft implementation plan
- Source specification: `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md`
- Source SDK documentation: <https://docs.cline.bot/sdk/overview>
- Related ADR: `docs/adr/0002-use-cline-sdk-contract-instead-of-cli-probing.md`
- Supersedes active delivery sequencing from: `docs/plans/configurable-lifecycle-hooks-and-repository-task-plan.md`
- Primary gate: prove a working `@cline/sdk` adapter before continuing SDLC delivery

## Overview

Implement the SDK-first reset direction by proving a real `@cline/sdk` execution
adapter before expanding lifecycle orchestration. The official Cline SDK is a
TypeScript/Node.js SDK that exposes `@cline/sdk`, requires Node.js 22 or later,
and demonstrates an `Agent` runtime with `agent.subscribe((event) => ...)` and
`await agent.run(prompt)`. This project remains a Python hexagonal
vertical-slice application, so SDK integration must be isolated behind the
`cline_execution` outbound adapter boundary and normalized into Python-owned
application DTOs.

Do not continue with SDK-first SDLC delivery until the adapter can invoke the
documented SDK locally, integration tests pass, and scripts/examples demonstrate
the adapter path. Plan/Act mediation, permission handling, structured outcomes,
and unattended implementation-slice claims must be added only after the working
adapter proves or explicitly blocks those SDK capabilities.

## Resolved Planning Decisions

- Treat the Node/TypeScript SDK runner as part of the shipped adapter/runtime
  package, not as external contributor-only tooling.
- Place adapter-owned Node package files under
  `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/`
  so SDK runtime details remain inside the `cline_execution` outbound adapter
  boundary.
- Commit adapter-local `package.json` and a Node lockfile for reproducible
  `@cline/sdk` installation. Do not require or rely on a global `@cline/sdk`
  package.
- Install Node dependencies from the adapter runner directory. Keep generated
  dependency artifacts such as `node_modules/` untracked.
- Evolve the existing `SessionRunner` application contract and `session.py` DTOs
  in place toward SDK-shaped semantics instead of introducing a permanent
  parallel SDK-specific session port.
- Require local real-SDK smoke evidence before the SDK adapter gate can be marked
  complete. Fake-runner and protocol tests are necessary for CI-safe coverage but
  are not sufficient proof of the real SDK boundary.
- Treat Plan/Act and permission/tool-approval support as expected from
  `cline/sdk`, but require official SDK docs/API references plus local real-SDK
  smoke evidence before lifecycle delivery relies on those capabilities.
- Use the full SDK execution contract from
  `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md` as the minimum gate
  before `--plan-file` implementation can use the SDK-first path.

## Architecture Decisions

- Keep the Python application core independent of TypeScript SDK objects. Python
  ports and DTOs express normalized orchestrator semantics; Node/TypeScript SDK
  types remain inside outbound adapters.
- Add a `cline_execution` outbound adapter for `@cline/sdk` before modifying
  lifecycle delivery use cases. The adapter is the first proof point.
- Use a small adapter-owned Node/TypeScript runner to call the official SDK. The
  runner imports `Agent` from `@cline/sdk`, subscribes to events, runs prompts,
  and emits a stable JSON protocol back to Python.
- Treat official SDK documentation as authoritative source context. Start from
  the overview, then inspect Events, ClineCore, Tools, Permission Handling,
  production guidance, and API reference pages before claiming deeper lifecycle
  behavior.
- Keep existing CLI probes, subprocess session runners, and fake Cline fixtures as
  compatibility or test assets only. They must not be described as the production
  SDK execution contract.
- Fail closed for unsupported SDK primitives, malformed adapter JSON, unknown SDK
  event shapes, missing terminal results, path-unsafe evidence, timeouts,
  interruptions, and contradictory repository evidence.

## SDK Facts From Official Overview

- `@cline/sdk` is the public SDK surface and re-exports SDK packages.
- The SDK requires Node.js 22 or later.
- `@cline/core` is the Node runtime for sessions, built-in tools, persistence,
  hub support, and automation.
- `@cline/agents` provides a browser-compatible stateless agent execution loop.
- `@cline/llms` provides the provider gateway and model catalogs.
- `@cline/shared` provides types, schemas, tool helpers, hooks, and storage
  helpers.
- The documented first-agent shape constructs `new Agent({...})`, subscribes to
  events with `agent.subscribe(...)`, and invokes `await agent.run(...)`.
- The overview demonstrates an `assistant-text-delta` event.
- The docs recommend the `cline/sdk-skill` skill for deeper SDK API and best
  practice work.

## Existing Patterns and Likely Touchpoints

- Source layout: `src/cline_sdlc/features/<feature>/{domain,application,adapters}`.
- Existing Cline execution slice:
  - `src/cline_sdlc/features/cline_execution/domain/outcome.py`
  - `src/cline_sdlc/features/cline_execution/application/dtos/session.py`
  - `src/cline_sdlc/features/cline_execution/application/ports/session_runner.py`
  - `src/cline_sdlc/features/cline_execution/application/use_cases/run_session.py`
  - `src/cline_sdlc/features/cline_execution/adapters/outbound/subprocess_session_runner/`
  - `src/cline_sdlc/features/cline_execution/adapters/outbound/terminal_outcome_parser/`
- Existing lifecycle orchestration session attempts:
  - `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/run_session_attempts.py`
  - `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/execute_slice.py`
  - `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/reconcile_slice.py`
- Existing repository authority boundaries:
  - `src/cline_sdlc/features/repository_coordination/application/use_cases/reconcile_plan.py`
  - `src/cline_sdlc/features/repository_coordination/application/use_cases/commit_slice.py`
- Existing tests:
  - `tests/contract/features/cline_execution/`
  - `tests/unit/features/cline_execution/`
  - `tests/integration/features/lifecycle_orchestration/`
  - `tests/e2e/`
- Existing scripts area: `scripts/`.

## Progress Tracking

Treat this plan as a living document during implementation. After each completed
task or meaningful change:

- check off completed tasks, acceptance criteria, verification items, and
  checkpoints;
- leave unfinished or unverified items unchecked;
- add newly discovered work and update sequencing when scope or dependencies
  change;
- note blockers, deviations, and decisions that affect remaining work;
- do not mark SDK-first delivery work ready until the adapter-first gate is
  complete.

## Task List

### Phase 1: SDK Adapter Runtime Foundation

## Task 1: Confirm SDK runtime and local dependency strategy

**Description:** Define how this Python project will run the TypeScript Cline SDK
without leaking Node-specific concerns into the application core. Confirm Node.js
22+ availability, create the adapter-owned Node package under the outbound
adapter boundary, and define how the adapter locates `@cline/sdk` during tests,
examples, and local use.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/package.json`
- adapter-local Node lockfile generated by the selected package manager
- `.gitignore`
- `README.md` or focused docs if setup is reader-visible
- `tests/integration/features/cline_execution/`

**Acceptance criteria:**

- [ ] The adapter has an explicit Node.js 22+ runtime prerequisite.
- [ ] Adapter-owned Node package files live under
      `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/`.
- [ ] Adapter-local `package.json` and a Node lockfile are committed for
      reproducible `@cline/sdk` installation.
- [ ] `@cline/sdk` dependency location and install/sync workflow are documented,
      and setup installs dependencies from the adapter runner directory.
- [ ] Python application/domain modules do not import or depend on Node/TypeScript
      SDK objects.
- [ ] Missing Node.js, unsupported Node.js, or missing `@cline/sdk` produces a
      structured preflight blocker.
- [ ] No global package installation is required by automated tests.
- [ ] Generated Node dependency artifacts such as `node_modules/` are ignored and
      are not required to be committed.

**Verification:**

- [ ] Run focused preflight tests for missing/unsupported runtime cases.
- [ ] Manually verify the documented local setup command sequence.

**Dependencies:** None

**Estimated scope:** Medium

## Task 2: Evolve Python-owned session DTOs and port into SDK-shaped contract

**Description:** Evolve the existing `SessionRunner` application contract and
`session.py` DTOs in place so they express SDK-shaped session semantics. The
contract represents orchestrator-owned concepts, not raw SDK event or result
shapes, and should avoid a permanent parallel SDK-specific session port.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/application/dtos/session.py`
- `src/cline_sdlc/features/cline_execution/application/ports/session_runner.py`
- `src/cline_sdlc/features/cline_execution/application/use_cases/run_session.py`
- `tests/unit/features/cline_execution/application/`
- `tests/contract/features/cline_execution/`

**Acceptance criteria:**

- [ ] Session DTOs model session request, SDK event evidence, SDK terminal result,
      blockers, timeout/interruption evidence, and diagnostic references.
- [ ] DTOs use closed enum values for known normalized event/result/status types.
- [ ] DTOs reject unsafe repository-relative paths, missing required fields, and
      unsupported statuses.
- [ ] `SessionRunner` signatures use application DTOs and domain values only.
- [ ] No TypeScript SDK package names appear in application port signatures except
      as safe diagnostic strings.
- [ ] Existing CLI/subprocess runner assets are either adapted to the evolved
      contract for compatibility tests or explicitly quarantined as legacy
      fixtures before lifecycle code depends on the SDK-shaped path.

**Verification:**

- [ ] Run focused unit and contract tests for session DTO validation and
      `SessionRunner` compatibility.

**Dependencies:** Task 1

**Estimated scope:** Medium

## Task 3: Create adapter-owned Node SDK runner protocol

**Description:** Define the JSON protocol between Python and the adapter-owned
Node runner. The protocol must be stable, testable, and fail closed before the
runner is wired to the real SDK.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/protocol.py`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/`
- `tests/unit/features/cline_execution/adapters/outbound/test_cline_sdk_protocol.py`

**Acceptance criteria:**

- [ ] Python request serialization includes prompt/instructions, provider/model
      configuration references, timeout, working directory, role, and safe context
      fields.
- [ ] Runner output serialization supports normalized events, terminal result,
      blocker, diagnostics, and raw SDK event type when safe.
- [ ] Malformed JSON, duplicate terminal results, missing terminal result, unknown
      required fields, and unsafe paths fail closed.
- [ ] Raw prompts, secrets, API keys, and model reasoning are not logged or echoed
      by default.

**Verification:**

- [ ] Run unit tests with representative valid and invalid protocol payloads.

**Dependencies:** Task 2

**Estimated scope:** Medium

### Checkpoint: Adapter Contract Foundation

- [ ] Python session DTOs and `SessionRunner` port express SDK-shaped
      application semantics.
- [ ] Adapter-owned JSON protocol is validated independently.
- [ ] Runtime dependency strategy is documented and fail-closed.

### Phase 2: Working `@cline/sdk` Adapter

## Task 4: Implement minimal Node runner using official `@cline/sdk`

**Description:** Implement the adapter-owned Node/TypeScript runner that imports
`Agent` from `@cline/sdk`, subscribes to events, runs one prompt, and emits the
normalized JSON protocol for Python.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/package.json`
- adapter-local Node lockfile
- `tests/integration/features/cline_execution/test_cline_sdk_runner.py`

**Acceptance criteria:**

- [ ] Runner uses documented SDK shape: `new Agent(...)`, `agent.subscribe(...)`,
      and `await agent.run(...)`.
- [ ] Runner implementation cites or records the official SDK docs/API references
      used for `Agent`, subscription, run, events, Plan/Act, and permission/tool
      approval behavior.
- [ ] Runner captures documented `assistant-text-delta` events as normalized
      diagnostic or assistant-output evidence.
- [ ] Runner emits exactly one terminal JSON result for success, block, failure,
      timeout, or interruption.
- [ ] Runner never prints secrets, API keys, raw model reasoning, or raw sensitive
      repository content by default.
- [ ] Runner exits with a typed failure when SDK construction, event handling, or
      `agent.run(...)` fails.

**Verification:**

- [ ] Run CI-safe fake-runner tests for protocol behavior.
- [ ] Run a local real-SDK smoke test before marking this task complete. If the
      smoke cannot run, leave this task incomplete and record the exact blocker.

**Dependencies:** Task 3

**Estimated scope:** Medium

## Task 5: Implement Python outbound adapter for the Node runner

**Description:** Add the Python outbound adapter that invokes the Node runner with
argument-array subprocess execution, finite timeout, interruption handling, and
strict protocol parsing.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/adapter.py`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/__init__.py`
- `tests/unit/features/cline_execution/adapters/outbound/test_cline_sdk_adapter.py`
- `tests/integration/features/cline_execution/test_cline_sdk_adapter.py`

**Acceptance criteria:**

- [ ] Adapter invokes Node without shell interpolation.
- [ ] Adapter sends/receives only the adapter protocol and validates all results.
- [ ] Timeout and interruption terminate the child process safely and produce
      structured blockers.
- [ ] Nonzero runner exits retain safe diagnostic evidence.
- [ ] Unknown event/result shapes fail closed rather than being ignored.

**Verification:**

- [ ] Run unit tests with fake runner executables.
- [ ] Run integration tests against the real runner locally before marking the
      adapter gate complete. If SDK prerequisites are unavailable, document the
      blocker and do not mark Checkpoint A complete.

**Dependencies:** Task 4

**Estimated scope:** Medium

## Task 6: Add adapter preflight and capability evidence

**Description:** Add SDK-specific preflight that verifies Node.js, package
resolution, and the minimum documented SDK primitives before any lifecycle stage
can depend on the adapter.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/application/dtos/preflight.py`
- `src/cline_sdlc/features/cline_execution/application/use_cases/preflight.py`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/adapter.py`
- `tests/unit/features/cline_execution/application/test_preflight.py`

**Acceptance criteria:**

- [ ] Preflight verifies Node.js 22+.
- [ ] Preflight verifies `@cline/sdk` is resolvable by the runner environment.
- [ ] Preflight verifies the spec's full SDK execution contract before the SDK
      path can be used for `--plan-file` implementation: bounded sessions,
      explicit role/instructions/context, Plan/Act observation and authorization,
      event/evidence stream, permission/tool approval evidence, structured
      terminal outcomes, timeouts, interruptions, and diagnostic references.
- [ ] Missing Plan/Act, permission, structured-outcome, timeout/interruption, or
      diagnostic-reference primitives are reported as unproven capabilities, not
      ignored.
- [ ] CLI probing is not accepted as production-equivalent SDK readiness.

**Verification:**

- [ ] Run focused preflight unit tests and adapter integration tests.

**Dependencies:** Task 5

**Estimated scope:** Medium

### Checkpoint A: Working SDK Adapter Gate

Do not continue to SDLC delivery work until all items in this checkpoint are
complete.

- [ ] Adapter invokes documented `@cline/sdk` primitives locally.
- [ ] Python receives typed normalized events and results.
- [ ] CI-safe fake-runner and protocol tests pass.
- [ ] Local real-SDK smoke and integration tests pass. If SDK prerequisites are
      absent, this checkpoint remains incomplete and the blocker is documented.
- [ ] Runtime setup and limitations are documented.
- [ ] Plan/Act and permission support are proven with official SDK docs/API
      references plus local real-SDK smoke evidence, or the checkpoint remains
      blocked.

### Phase 3: Scripts and Examples for Adapter Proof

## Task 7: Add runnable SDK adapter example script

**Description:** Add a script under `scripts/` that exercises the Python adapter
against a simple prompt and prints safe normalized events/results. This script is
for local proof and diagnostics, not production orchestration.

**Likely files/components touched:**

- `scripts/run_cline_sdk_adapter_example.py`
- `README.md` or focused docs
- `tests/manual/cline_execution/` if a manual smoke test wrapper is appropriate

**Acceptance criteria:**

- [ ] Script uses the Python adapter path, not direct ad hoc SDK invocation from
      outside the adapter boundary.
- [ ] Script documents required environment variables with safe placeholders.
- [ ] Script redacts secrets and does not print raw model reasoning.
- [ ] Script exits with stable process categories or clear safe diagnostics.

**Verification:**

- [ ] Run the script in a configured local environment or document the exact
      unrun prerequisite.

**Dependencies:** Checkpoint A

**Estimated scope:** Small

## Task 8: Add diagnostic SDK event example

**Description:** Add a second example or mode that focuses on event capture and
normalization so contributors can inspect what the SDK actually emits without
reading raw terminal output.

**Likely files/components touched:**

- `scripts/diagnose_cline_sdk_events.py`
- `README.md` or focused docs

**Acceptance criteria:**

- [ ] Diagnostic output lists normalized event type, safe summary, and SDK event
      type where safe.
- [ ] High-cardinality or sensitive event payload fields are omitted or redacted.
- [ ] Unknown SDK events are reported as diagnostic observations and do not become
      authoritative lifecycle evidence.

**Verification:**

- [ ] Run the script in a configured local environment or document the exact
      unrun prerequisite.

**Dependencies:** Task 7

**Estimated scope:** Small

### Checkpoint: Adapter Examples Complete

- [ ] `scripts/` examples demonstrate normal adapter execution.
- [ ] `scripts/` examples demonstrate safe event diagnostics.
- [ ] Documentation explains setup, prerequisites, and limitations.

### Phase 4: SDK Capability Matrix Against SDLC Requirements

## Task 9: Create SDK capability matrix

**Description:** Inspect official SDK documentation and the working adapter to map
the SDLC spec requirements to proven, unproven, unsupported, or blocked SDK
capabilities. The full SDK execution contract in
`docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md` is the minimum gate before
`--plan-file` implementation may use the SDK-first path.

**Likely files/components touched:**

- `docs/plans/cline-sdk-first-sdlc-orchestrator-plan.md`
- optional `docs/sdk-capability-matrix.md`
- tests documenting capability preflight behavior

**Acceptance criteria:**

- [ ] Matrix covers `Agent.run`, event subscription, session identity,
      diagnostics, permission handling, tool approval, Plan/Act mediation,
      structured outcomes, timeout, interruption, and file-change evidence.
- [ ] Every capability claim includes official SDK docs/API references and local
      real-SDK smoke test evidence.
- [ ] Every reset MVP SDK requirement is mapped to documented SDK primitive,
      adapter-derived proof, or explicit blocker.
- [ ] Missing full-contract primitives block `--plan-file` delivery planning
      rather than being approximated from prose.

**Verification:**

- [ ] Review matrix against `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md`
      and official SDK docs.
- [ ] Review local real-SDK smoke evidence for every capability marked proven.

**Dependencies:** Adapter Examples Complete

**Estimated scope:** Small

## Task 10: Quarantine CLI probe readiness language

**Description:** Rename or document existing CLI probe artifacts so they are
clearly historical, compatibility, or discovery fixtures. They must not imply
production readiness for SDK-first orchestration.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/domain/capability.py`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cli_capability_probe/`
- `scripts/probe_cline_capabilities.py`
- related tests/docs

**Acceptance criteria:**

- [ ] CLI probe naming/docs do not present terminal probing as the production SDK
      execution contract.
- [ ] Useful subprocess/fake Cline tests remain available as compatibility tests.
- [ ] Documentation references ADR 0002 where appropriate.

**Verification:**

- [ ] Run focused `cline_execution` tests.
- [ ] Search for misleading CLI-readiness claims.

**Dependencies:** Task 9

**Estimated scope:** Small

### Checkpoint: Capability Gate Ready for Delivery Decision

- [ ] SDK capability matrix is complete.
- [ ] CLI probe surfaces are quarantined.
- [ ] `--plan-file` delivery can proceed only after the spec's full SDK execution
      contract is proven by official docs/API references and local real-SDK smoke
      evidence.

### Phase 5: SDK-Backed One-Slice Delivery Proof

## Task 11: Integrate SDK adapter into lifecycle session attempts

**Description:** Adapt lifecycle session attempts to consume the normalized SDK
adapter result while preserving orchestrator authority over lifecycle
classification. This task must not start until the capability matrix proves the
spec's full SDK execution contract.

**Likely files/components touched:**

- `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/run_session_attempts.py`
- `src/cline_sdlc/features/lifecycle_orchestration/application/dtos/session_attempt.py`
- `tests/unit/features/lifecycle_orchestration/application/`

**Acceptance criteria:**

- [ ] Lifecycle use cases consume normalized SDK evidence, not raw SDK events.
- [ ] SDK events do not replace artifact, digest, validation, plan progress, or
      Git checks.
- [ ] Missing/invalid SDK results produce blockers.

**Verification:**

- [ ] Run focused lifecycle session-attempt tests.

**Dependencies:** Capability Gate Ready for Delivery Decision

**Estimated scope:** Medium

## Task 12: Add Plan/Act mediation only if supported

**Description:** Implement explicit planning-result and Act-authorization handling
for implementation slices only after the adapter/capability matrix proves support
with official SDK docs/API references and local real-SDK smoke evidence. If the
full SDK execution contract is not proven, record a blocker and stop delivery at
this task.

**Likely files/components touched:**

- `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/execute_slice.py`
- `src/cline_sdlc/features/lifecycle_orchestration/application/dtos/slice_execution.py`
- `tests/contract/features/lifecycle_orchestration/test_slice_execution.py`

**Acceptance criteria:**

- [ ] `needs_user_input` stops without acting or committing.
- [ ] `ready_to_act` can authorize Act mode only for the same session, slice,
      digests, approval, and operation policy.
- [ ] Ambiguous planning evidence is treated as `needs_user_input`.
- [ ] If SDK Plan/Act support is not proven, the task records a blocker instead
      of implementing a prose-derived substitute.
- [ ] Permission/tool approval evidence is preserved as normalized SDK evidence
      and reconciled before repository-changing work is authorized.

**Verification:**

- [ ] Run focused and contract slice-execution tests.

**Dependencies:** Task 11 and proven full SDK execution contract

**Estimated scope:** Medium

## Task 13: Prove one accepted implementation slice through SDK path

**Description:** Run one accepted implementation slice through SDK-backed session
execution, evidence collection, independent reconciliation, validation evidence,
and local atomic commit gating. This proof requires the full SDK execution
contract, not a partial `Agent.run` and event-subscription proof.

**Likely files/components touched:**

- `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/implement_plan.py`
- `src/cline_sdlc/features/lifecycle_orchestration/application/use_cases/reconcile_slice.py`
- `src/cline_sdlc/features/repository_coordination/application/use_cases/commit_slice.py`
- `tests/integration/features/lifecycle_orchestration/`
- `tests/e2e/test_sdk_first_plan_implementation_slice.py`

**Acceptance criteria:**

- [ ] One accepted slice can complete through the SDK adapter path.
- [ ] Changed paths are independently reconciled against Git and plan scope.
- [ ] Validation evidence is required before commit eligibility.
- [ ] Commit creation remains orchestrator-owned and uses explicit paths.
- [ ] Invalid SDK evidence blocks without committing.

**Verification:**

- [ ] Run focused lifecycle integration tests.
- [ ] Run the new e2e proof test.

**Dependencies:** Task 12 and proven full SDK execution contract

**Estimated scope:** Medium

### Checkpoint: Reset MVP Slice Proof

- [ ] One accepted implementation slice is proven through the SDK adapter.
- [ ] Orchestrator-owned reconciliation and commit gating remain authoritative.
- [ ] No lifecycle hooks, repository task recipes, multi-agent runtime, or broad
      unattended claims enter this MVP proof.

### Phase 6: Documentation and Final Validation

## Task 14: Update user-facing documentation

**Description:** Document the SDK-first adapter, Node.js/SDK prerequisites,
scripts/examples, capability limitations, and delivery gate.

**Likely files/components touched:**

- `README.md`
- `.env.example` if examples introduce supported environment variables
- `.gitignore` if adapter-local Node artifacts need ignore coverage
- optional `docs/sdk-capability-matrix.md`
- optional updates to `docs/specs/cline-sdlc-orchestrator-spec.md` only if a
  normative mismatch is discovered

**Acceptance criteria:**

- [ ] README or linked docs explain Node.js 22+ and `@cline/sdk` setup.
- [ ] Docs explain how to run adapter scripts/examples.
- [ ] Any SDK-related environment variables are documented with safe placeholders
      and mirrored in `.env.example` when they become supported configuration.
- [ ] Generated Node artifacts such as `node_modules/` are covered by `.gitignore`
      without hiding committed adapter package files or lockfiles.
- [ ] Docs do not claim Plan/Act, permission handling, or unattended readiness
      beyond proven adapter capabilities.
- [ ] Deferred hooks and repository task recipes remain explicitly deferred.

**Verification:**

- [ ] Review docs for consistency with implementation and SDK capability matrix.

**Dependencies:** Reset MVP Slice Proof, or documented blocker if delivery stops earlier

**Estimated scope:** Small

## Task 15: Run full local quality gate

**Description:** Execute final validation from the repository root after code,
tests, scripts, and docs are updated.

During implementation, run the narrowest relevant focused checks first, including
`uv run ruff format .` before lint/type/test iteration where Python files change.
Use the final verification commands below for handoff.

**Acceptance criteria:**

- [ ] Formatting check passes.
- [ ] Ruff lint passes.
- [ ] Mypy passes.
- [ ] Pytest suite passes.
- [ ] Package build passes.

**Verification commands:**

- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy .`
- [ ] `uv run pytest`
- [ ] `uv build`

**Dependencies:** Task 14

**Estimated scope:** Small

### Checkpoint: Complete

- [ ] Adapter-first gate completed before delivery work.
- [ ] SDK capability matrix is current.
- [ ] Scripts/examples prove adapter behavior.
- [ ] One-slice delivery proof is complete or explicitly blocked by missing SDK
      capability.
- [ ] Documentation matches implemented behavior and limitations.
- [ ] Full quality gate passes or blockers are documented.

## Dependencies and Sequencing Constraints

- Tasks 1-6 are mandatory before any lifecycle delivery work.
- Tasks 7-8 are mandatory before the adapter is considered proven for local use.
- Task 9 must precede Plan/Act, permission, structured outcome, or `--plan-file`
  delivery claims.
- Task 10 can run after Task 9 but before broader delivery work to avoid confusing
  CLI probe artifacts with SDK readiness.
- Tasks 11-13 must not begin until Checkpoint A and the capability matrix are
  complete.
- Task 12 must block rather than emulate Plan/Act mediation, permission/tool
  approval, structured outcomes, timeout/interruption handling, diagnostic
  references, or any other full-contract primitive if the SDK adapter cannot
  prove it.
- Task 15 runs after implementation, tests, scripts, and docs are complete or
  explicitly blocked.

## Parallelization Opportunities

- Task 2 DTO/port evolution can proceed in parallel with Task 1 runtime setup
  once the normalized contract shape is agreed.
- Task 3 protocol validation can proceed with a fake runner before the real SDK
  runner is finished.
- Task 7 and Task 8 scripts can be drafted after Task 5, but final verification
  waits for Checkpoint A.
- Task 10 CLI-probe wording cleanup can proceed in parallel with Task 9 capability
  matrix once the adapter gate is stable.
- Documentation drafts can start after Task 7, but final docs must wait for the
  capability matrix and delivery proof/blocker.

## Deferred Follow-up Scope

- Lifecycle hooks and repository task recipes.
- `conventional-commit-staged` as a first proof point.
- Multiple agent runtimes or generic Codex/OpenAI SDK migration.
- Concurrent implementation sessions or concurrent repository writers.
- Pushes, pull requests, releases, publication, or deployment.
- Broad unattended-readiness claims beyond proven SDK capabilities.
- Any Plan/Act or permission emulation based only on assistant prose, terminal
  output, or Cline Checkpoints.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The official SDK is TypeScript/Node while this project is Python. | High | Isolate Node/TypeScript in an outbound adapter and normalize JSON into Python DTOs. |
| Node dependency management complicates Python packaging. | High | Keep adapter-owned Node package files and lockfile under `cline_execution/adapters/outbound/cline_sdk/node_runner/`; document local setup and ignore generated dependency artifacts. |
| The SDK overview proves `Agent.run` and events but deeper Plan/Act, permission, and structured-outcome behavior must be verified. | High | Add capability matrix with official SDK docs/API references and local real-SDK smoke evidence for every proven capability; block `--plan-file` delivery until the full SDK execution contract is proven. |
| Adapter examples accidentally log secrets or raw repository content. | High | Redact by default and keep raw payloads out of normal output. |
| Existing CLI probe code continues to imply production readiness. | Medium | Quarantine or rename CLI probe readiness language after adapter proof. |
| Integration tests become dependent on live providers. | Medium | Keep CI-safe fake-runner/protocol tests separate, but require local real-SDK smoke/integration evidence before adapter gates are marked complete. |
| Lifecycle delivery starts before adapter behavior is proven. | High | Enforce Checkpoint A as a hard sequencing gate in this plan. |

## Assumptions

- The project remains a Python 3.14 package managed with `uv`.
- SDK adapter implementation may introduce a local Node.js adapter package or
  runner files, but TypeScript SDK details stay outside Python application/domain
  layers.
- Default CI-safe automated tests should not require live external model providers.
  Local real-SDK smoke and integration tests are still mandatory before adapter
  gates are marked complete.
- Official SDK documentation and SDK package behavior are the source of truth for
  capability claims.
- Any environment variables used by examples must use safe placeholders in docs
  and must not be printed.

## Open Questions

- Which Node package manager and lockfile format should the adapter-local runner
  use? The plan requires a committed lockfile but leaves npm, pnpm, or another
  concrete tool to Task 1 implementation review.
- Which exact official SDK docs/API pages and local package APIs prove Plan/Act
  semantics, permission/tool approval, structured outcomes, and evidence fields?
- Which SDK event fields are reconciliation evidence versus diagnostic-only
  observations?
- Which real-provider credentials or local provider settings are required for the
  mandatory local real-SDK smoke tests, and how should they be represented safely
  in documentation and `.env.example`?
- Does implementing the full SDK execution contract reveal any normative mismatch
  requiring an update to `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md`?

## Resolved Questions

- Adapter-owned Node package files live under
  `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/`.
- The project commits adapter-local `package.json` and a Node lockfile, installs
  dependencies from the adapter runner directory, and does not rely on global
  `@cline/sdk` installation.
- The existing `SessionRunner` contract and `session.py` DTOs evolve in place into
  the SDK-shaped application contract.
- Real SDK smoke/integration evidence is required locally before the adapter gate
  can be marked complete.
- `cline/sdk` is expected to provide Plan/Act and permission/tool approval
  support, but lifecycle delivery may rely on those capabilities only after
  official SDK docs/API references and local real-SDK smoke evidence prove them.
- The full SDK execution contract from
  `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md` is the minimum gate
  before `--plan-file` implementation may use the SDK-first path.
