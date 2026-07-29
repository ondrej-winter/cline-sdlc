# Implementation Plan: Cline SDK-First SDLC Orchestrator

## Status

- State: Draft implementation plan
- Source specification: `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md`
- Source SDK documentation: <https://docs.cline.bot/sdk/overview>
- Source SDK Agent reference: <https://docs.cline.bot/sdk/reference/agent.md>
- Source SDK Events reference: <https://docs.cline.bot/sdk/reference/events.md>
- Source SDK Permission Handling guide: <https://docs.cline.bot/sdk/guides/permission-handling.md>
- Source SDK ClineCore guide: <https://docs.cline.bot/sdk/clinecore.md>
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

## SDK Facts From Focused Official References

- The official Agent reference documents `Agent` as an alias for `AgentRuntime`
  from `@cline/agents`, exported from `@cline/sdk` together with
  `AgentRuntime`, `createAgent`, and `createAgentRuntime`.
- `new Agent(config: AgentRuntimeConfig)` accepts either a prebuilt model or
  `providerId`, `modelId`, and optional provider credentials such as `apiKey`,
  `baseUrl`, and `headers`.
- Documented `Agent` configuration fields include `systemPrompt`, `tools`,
  `initialMessages`, `toolPolicies`, and `hooks`.
- Documented `Agent` methods include `run(input)`, `continue(input?)`,
  `abort(reason?)`, `subscribe(listener)`, `restore(messages)`, and
  `snapshot()`.
- `AgentRunResult.status` is documented as the closed set `completed`, `aborted`,
  or `failed`; the result also includes `agentId`, optional `agentRole`, `runId`,
  `iterations`, `outputText`, `messages`, `usage`, and optional `error`.
- The Events reference documents direct `AgentRuntime` events through
  `agent.subscribe(listener)`. Runtime results use `AgentRunResult.status` rather
  than `finishReason`.
- Core/host-facing SDK events include content lifecycle events, iteration events,
  `usage`, `notice`, `done`, and `error`. A documented `done` event has reason
  values `completed`, `max_iterations`, `aborted`, `mistake_limit`, or `error`.
- `ClineCore` is the documented full Cline harness for built-in file, shell,
  search, and web tools; sessions; approvals; persistence; scheduling; hub
  support; and plugins.
- `ClineCore.start(...)` documents session-oriented configuration including
  `prompt`, `providerId`, `modelId`, `apiKey`, `systemPrompt`, `cwd`,
  `workspaceRoot`, `enableTools`, `enableSpawnAgent`, and `enableAgentTeams`.
- `ClineCore` session results document `sessionId`, `manifest`, `manifestPath`,
  `messagesPath`, and final `result` when available.
- Tool policies default to enabled and auto-approved when no policy is set. SDLC
  execution must therefore explicitly specify fail-closed tool policies rather
  than relying on SDK defaults.
- Dynamic tool approval is documented through `ClineCore.create(...)` capability
  `requestToolApproval`.
- The focused official SDK pages prove `Agent`, event subscription, `AgentRunResult`,
  `ClineCore` sessions, tool policies, and dynamic tool approval. They do not, by
  themselves, prove a direct SDK Plan/Act transition or Act-authorization API.

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

- [x] The adapter has an explicit Node.js 22+ runtime prerequisite.
- [x] Adapter-owned Node package files live under
      `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/`.
- [x] Adapter-local `package.json` and a Node lockfile are committed for
      reproducible `@cline/sdk` installation.
- [x] Adapter-local Node dependencies include the optional
      `ai-sdk-provider-codex-cli` package required by the configured
      `openai-codex-cli` SDK provider.
- [x] `@cline/sdk` dependency location and install/sync workflow are documented,
      and setup installs dependencies from the adapter runner directory.
- [x] Python application/domain modules do not import or depend on Node/TypeScript
      SDK objects.
- [x] Missing Node.js, unsupported Node.js, or missing `@cline/sdk` produces a
      structured preflight blocker.
- [x] No global package installation is required by automated tests.
- [x] Generated Node dependency artifacts such as `node_modules/` are ignored and
      are not required to be committed.

**Verification:**

- [x] Run focused preflight tests for missing/unsupported runtime cases.
- [x] Manually verify the documented local setup command sequence.

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

- [x] Session DTOs model session request, SDK event evidence, SDK terminal result,
      blockers, timeout/interruption evidence, and diagnostic references.
- [x] DTOs use closed enum values for known normalized event/result/status types.
- [x] DTOs reject unsafe repository-relative paths, missing required fields, and
      unsupported statuses.
- [x] `SessionRunner` signatures use application DTOs and domain values only.
- [x] No TypeScript SDK package names appear in application port signatures except
      as safe diagnostic strings.
- [x] Existing CLI/subprocess runner assets are either adapted to the evolved
      contract for compatibility tests or explicitly quarantined as legacy
      fixtures before lifecycle code depends on the SDK-shaped path.

**Verification:**

- [x] Run focused unit and contract tests for session DTO validation and
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

- [x] Python request serialization includes prompt/instructions, provider/model
      configuration references, timeout, working directory, role, and safe context
      fields.
- [x] Runner output serialization supports normalized events, terminal result,
      blocker, diagnostics, and raw SDK event type when safe.
- [x] Malformed JSON, duplicate terminal results, missing terminal result, unknown
      required fields, and unsafe paths fail closed.
- [x] Raw prompts, secrets, API keys, and model reasoning are not logged or echoed
      by default.

**Verification:**

- [x] Run unit tests with representative valid and invalid protocol payloads.

**Dependencies:** Task 2

**Estimated scope:** Medium

### Checkpoint: Adapter Contract Foundation

- [x] Python session DTOs and `SessionRunner` port express SDK-shaped
      application semantics.
- [x] Adapter-owned JSON protocol is validated independently.
- [ ] Runtime dependency strategy is documented and fail-closed.

### Phase 2: Working `@cline/sdk` Adapter

## Task 4a: Implement minimal `Agent` runner proof using official `@cline/sdk`

**Description:** Implement the first adapter-owned Node/TypeScript runner proof
against the narrowest officially documented SDK primitive. The runner imports
`Agent` from `@cline/sdk`, constructs it with provider/model configuration,
subscribes to runtime events, runs one prompt, normalizes `AgentRunResult`, and
emits the stable JSON protocol for Python. This task proves the SDK package,
`Agent`, event subscription, `run`, result status, and cancellation wiring; it
does not by itself prove full SDLC repository-changing capability.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/package.json`
- adapter-local Node lockfile
- `tests/integration/features/cline_execution/test_cline_sdk_runner.py`

**Acceptance criteria:**

- [x] Runner uses documented SDK shape: `new Agent(...)`, `agent.subscribe(...)`,
      and `await agent.run(...)`.
- [x] Runner implementation cites or records the official SDK docs/API references
      used for `Agent`, subscription, run, events, `abort(reason?)`, and
      `AgentRunResult` normalization.
- [x] Runner captures documented `assistant-text-delta` events as normalized
      diagnostic or assistant-output evidence.
- [x] Runner normalizes documented `AgentRunResult.status` values `completed`,
      `aborted`, and `failed` into Python-owned result statuses.
- [x] Runner preserves safe diagnostic references such as `agentId`, `runId`,
      iteration count, and usage metadata without exposing raw secrets or model
      reasoning.
- [x] Runner emits exactly one terminal JSON result for success, block, failure,
      timeout, or interruption.
- [x] Runner never prints secrets, API keys, raw model reasoning, or raw sensitive
      repository content by default.
- [x] Runner exits with a typed failure when SDK construction, event handling, or
      `agent.run(...)` fails.
- [x] Plan/Act mediation, built-in repository tools, `ClineCore` session artifacts,
      and dynamic permission approval remain explicitly unproven by this task.

Task 4a implementation note: `node_runner/runner.mjs` and `runner-lib.mjs`
provide the minimal `Agent` proof. CI-safe Node tests use a fake Agent class;
Python integration tests invoke the real runner only far enough to verify typed
fail-closed configuration blocking. Local runtime inspection on 2026-07-29 found
Node.js v22.22.3, confirmed adapter-local `@cline/sdk` resolution, and confirmed
that `.env` provides `CLINE_SDK_PROVIDER_ID`, `CLINE_SDK_MODEL_ID`, and
`CLINE_SDK_REASONING_EFFORT` without printing secret values. The first local
real-SDK smoke reached the official SDK `Agent` event stream but returned
`run-failed` because the configured `openai-codex-cli` provider required the
optional adapter-local `ai-sdk-provider-codex-cli` package. After adding that
package, a second local real-SDK smoke completed through the minimal `Agent` path.

**Verification:**

- [x] Run CI-safe fake-runner tests for protocol behavior.
- [x] Run a local real-SDK smoke test before marking this task complete. If the
      smoke cannot run, leave this task incomplete and record the exact blocker.

Real-SDK smoke evidence: the 2026-07-29 `.env`-loaded smoke invocation used the
adapter-owned `node_runner/runner.mjs` with `CLINE_SDK_DEBUG_SAFE=1` and the
configured `openai-codex-cli` provider. Safe debug diagnostics first identified
the missing optional `ai-sdk-provider-codex-cli` package as the root cause of the
previous `run-failed` result. After installing that adapter-local dependency, the
smoke emitted SDK events `run-started`, `message-added`, `turn-started`,
`assistant-text-delta`, `usage-updated`, `assistant-message`, `turn-finished`, and
`run-finished`, plus safe diagnostics for `agentId`, `runId`, iteration count,
and usage metadata, then returned terminal status `completed`. No secrets, API
keys, raw model reasoning, or raw repository content were printed by the runner.

**Dependencies:** Task 3

**Estimated scope:** Medium

## Task 4b: Implement `ClineCore` capability probe for sessions and approvals

**Description:** Add a second SDK proof path for capabilities that official docs
place under `ClineCore` rather than bare `Agent`: sessions, workspace roots,
built-in tools, session artifacts, tool policies, dynamic tool approval, and
session event subscription. This task is required before any repository-changing
SDLC lifecycle work can rely on SDK execution.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/protocol.py`
- `tests/unit/features/cline_execution/adapters/outbound/test_cline_sdk_protocol.py`
- `tests/integration/features/cline_execution/test_cline_sdk_clinecore_probe.py`

**Acceptance criteria:**

- [x] Probe uses documented `ClineCore.create(...)` and `cline.start(...)` shapes.
- [x] Probe supplies safe `cwd` and `workspaceRoot` values through adapter-owned
      configuration and never from unvalidated raw input.
- [x] Probe captures documented session diagnostics such as `sessionId`,
      `manifestPath`, `messagesPath`, and final `result` when available.
- [x] Probe explicitly configures tool policies for every tool category used by
      SDLC runs; no write, shell, or network-capable tool is left to SDK default
      auto-approval.
- [x] Probe exercises or verifies dynamic approval through documented
      `capabilities.requestToolApproval` before permission support can be marked
      proven.
- [x] Probe subscribes to session events when available and treats unknown event
      payloads as diagnostic observations unless the capability matrix promotes
      them to reconciliation evidence with proof.
- [x] Missing `ClineCore`, missing session artifacts, unsupported tool policies,
      or unavailable dynamic approval are reported as unproven or blocked
      capabilities.
- [x] A direct SDK Plan/Act transition or Act-authorization primitive remains
      blocked unless a focused official SDK reference and real smoke evidence
      prove it.

Task 4b implementation note: `node_runner/clinecore-probe.mjs` and the shared
`runner-lib.mjs` ClineCore probe path use the documented `ClineCore.create(...)`,
`cline.subscribe(...)`, and `cline.start(...)` shapes re-exported by `@cline/sdk`.
The probe configures adapter-owned `cwd` and `workspaceRoot` values from the
validated runner request, disables repository-changing tools by default,
provides explicit fail-closed tool policies for known tool/mode categories, and
installs a `capabilities.requestToolApproval` handler that records normalized
approval evidence while denying by default. CI-safe fake ClineCore tests verify
session diagnostics, event normalization, dynamic approval evidence, and blocked
capability reporting. This proves the probe contract and SDK API surface shape.
Local real-SDK smoke
on 2026-07-29 loaded the adapter-owned `.env` SDK provider/model settings
without printing values, ran `node_runner/clinecore-probe.mjs` against the
configured provider with `CLINE_SDK_DEBUG_SAFE=1`, emitted SDK session events
`status`, `session_snapshot`, `agent_event`, `chunk`, and `ended`, reported safe
diagnostics for `session`, `manifest`, `messages`, `session_result`,
`tool_policy_coverage`, and `dynamic_approval_handler`, and returned terminal
status `completed` without blocker records or detected secret leakage. This
proves local ClineCore session creation, workspace-root use, session event
subscription, and session artifact diagnostics for the probe path. The smoke did
not observe a real `requestToolApproval` callback, so dynamic approval remains
installed and CI-fake verified but not yet real-SDK exercised. No direct SDK
Plan/Act transition or Act-authorization primitive has been proven.

**Verification:**

- [x] Run CI-safe fake/protocol tests for ClineCore probe output.
- [x] Run local real-SDK smoke evidence for ClineCore session creation and
      permission handling before marking permission/session capabilities proven.
      Session creation and session artifact diagnostics are proven locally;
      permission handling remains limited to installed-deny-by-default evidence
      plus CI-safe fake-callback verification until a real SDK approval request
      is observed.

**Dependencies:** Task 4a

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

- [x] Adapter invokes Node without shell interpolation.
- [x] Adapter sends/receives only the adapter protocol and validates all results.
- [x] Timeout and interruption terminate the child process safely and produce
      structured blockers.
- [x] Nonzero runner exits retain safe diagnostic evidence.
- [x] Unknown event/result shapes fail closed rather than being ignored.

Task 5 implementation note: `cline_sdk/adapter.py` now exposes
`ClineSdkSessionRunner`, a Python outbound adapter that implements the existing
`ClineSessionRunnerPort` shape by invoking the adapter-owned `node_runner` with
argument-array subprocess execution, no shell interpolation, serialized protocol
input on stdin, bounded timeout/interruption handling, and strict
`parse_runner_output(...)` validation. CI-safe fake-runner unit tests cover
success, nonzero exit, malformed output, timeout, interruption, and startup
failure. A local integration test invokes the real adapter-owned `runner.mjs`
through the Python adapter far enough to verify structured missing-configuration
failure without live provider credentials.

**Verification:**

- [x] Run unit tests with fake runner executables.
- [x] Run integration tests against the real runner locally before marking the
      adapter gate complete. If SDK prerequisites are unavailable, document the
      blocker and do not mark Checkpoint A complete.

Verification evidence: `uv run pytest tests/unit/features/cline_execution/adapters/outbound/cline_sdk tests/integration/features/cline_execution/test_cline_sdk_runner.py`
passed locally on 2026-07-29 after adding the Python adapter tests and the real
Node-runner boundary integration check.

**Dependencies:** Task 4a for minimal Agent execution; Task 4b before any
repository-changing lifecycle use.

**Estimated scope:** Medium

## Task 6: Add adapter preflight and capability evidence

**Description:** Add SDK-specific preflight that verifies Node.js, package
resolution, and the minimum documented SDK primitives before any lifecycle stage
can depend on the adapter.

**Likely files/components touched:**

- `src/cline_sdlc/features/cline_execution/application/dtos/sdk_runtime.py`
- `src/cline_sdlc/features/cline_execution/application/use_cases/preflight_sdk_runtime.py`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/runtime_probe.py`
- `tests/unit/features/cline_execution/application/test_preflight_sdk_runtime.py`
- `tests/unit/features/cline_execution/adapters/outbound/cline_sdk/test_runtime_probe.py`

**Acceptance criteria:**

- [x] Preflight verifies Node.js 22+.
- [x] Preflight verifies `@cline/sdk` is resolvable by the runner environment.
- [x] Preflight verifies the spec's full SDK execution contract before the SDK
      path can be used for `--plan-file` implementation: bounded sessions,
      explicit role/instructions/context, Plan/Act observation and authorization,
      event/evidence stream, permission/tool approval evidence, structured
      terminal outcomes, timeouts, interruptions, and diagnostic references.
- [x] Preflight distinguishes bare `Agent`-proven capabilities from
      `ClineCore`-proven capabilities, and does not treat a successful
      `Agent.run(...)` as proof of sessions, built-in tools, tool approval,
      repository-changing execution, or session artifacts.
- [x] Tool policy coverage is explicit and fail-closed; SDK default auto-approval
      for unspecified tools is never accepted as an SDLC-safe policy.
- [x] Missing Plan/Act, permission, structured-outcome, timeout/interruption, or
      diagnostic-reference primitives are reported as unproven capabilities, not
      ignored.
- [x] CLI probing is not accepted as production-equivalent SDK readiness.

Task 6 implementation note: SDK runtime preflight now models application-owned
capability evidence in `sdk_runtime.py` and evaluates the full SDK execution
contract in `PreflightSdkRuntime`. The `cline_sdk` runtime probe emits
conservative evidence from implemented adapter/protocol behavior, local Agent
smoke proof, and local ClineCore smoke proof. Missing capabilities, unproven
capabilities, and CLI-probe-sourced claims all fail closed with typed blockers.
Plan/Act observation, Act authorization, and real permission approval remain
reported as unproven until official SDK references plus local smoke evidence
prove them directly.

**Verification:**

- [x] Run focused preflight unit tests and adapter integration tests.

Focused preflight unit test evidence: `uv run pytest tests/unit/features/cline_execution/application/test_preflight_sdk_runtime.py tests/unit/features/cline_execution/adapters/outbound/cline_sdk/test_runtime_probe.py`
passed locally on 2026-07-29.

Focused adapter gate evidence: `uv run pytest tests/unit/features/cline_execution/application/test_preflight_sdk_runtime.py tests/unit/features/cline_execution/adapters/outbound/cline_sdk/test_runtime_probe.py`
passed locally again on 2026-07-29 with 15 tests. `uv run pytest tests/unit/features/cline_execution/adapters/outbound/cline_sdk tests/integration/features/cline_execution/test_cline_sdk_runner.py tests/integration/features/cline_execution/test_cline_sdk_clinecore_probe.py`
also passed locally on 2026-07-29 with 21 tests, covering the Python SDK adapter,
protocol parser, runtime probe, real Node runner missing-configuration boundary,
and ClineCore probe missing-configuration boundary.

**Dependencies:** Task 5

**Estimated scope:** Medium

### Checkpoint A: Working SDK Adapter Gate

Do not continue to SDLC delivery work until all items in this checkpoint are
complete.

- [x] Adapter invokes documented `@cline/sdk` primitives locally.
- [x] Python receives typed normalized events and results.
- [x] Minimal `Agent` proof is complete and clearly scoped to documented
      `Agent`/`AgentRunResult` behavior.
- [x] `ClineCore` proof is complete for any session, workspace, built-in tool,
      session artifact, or dynamic approval capability claimed by lifecycle
      delivery.
- [x] CI-safe fake-runner and protocol tests pass.
- [x] Local real-SDK smoke and integration tests pass. If SDK prerequisites are
      absent, this checkpoint remains incomplete and the blocker is documented.
- [x] Runtime setup and limitations are documented.
- [ ] Plan/Act and permission support are proven with official SDK docs/API
      references plus local real-SDK smoke evidence, or the checkpoint remains
      blocked.

Checkpoint A status note: the adapter foundation is implemented and locally
validated through the documented `Agent` path, the ClineCore session/probe path,
the Python subprocess adapter, the JSONL protocol parser, and SDK runtime
preflight. The full Working SDK Adapter Gate remains blocked because official SDK
references and local real-SDK smoke evidence still do not prove direct Plan/Act
observation, Act authorization, or a real dynamic permission approval callback.
Do not start Task 7 or any repository-changing lifecycle delivery work as a
readiness claim until those full-contract blockers are resolved or this plan is
explicitly revised to split examples from Checkpoint A readiness.

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

- [x] Script uses the Python adapter path, not direct ad hoc SDK invocation from
      outside the adapter boundary.
- [x] Script documents required environment variables with safe placeholders.
- [x] Script redacts secrets and does not print raw model reasoning.
- [x] Script exits with stable process categories or clear safe diagnostics.

Task 7 implementation note: `scripts/run_cline_sdk_adapter_example.py` exercises
the Python `ClineSdkSessionRunner` path and prints safe normalized JSON containing
process status, SDK terminal status, normalized events, blockers, and diagnostic
references. The script does not call `@cline/sdk` directly, and normal output
omits raw runner stdout/stderr, raw model reasoning, secrets, and raw repository
payloads.

**Verification:**

- [x] Run the script in a configured local environment or document the exact
      unrun prerequisite.

CI-safe script test evidence: `uv run pytest tests/unit/scripts/test_run_cline_sdk_adapter_example.py`
passed locally on 2026-07-29 with 4 tests. Live-provider example execution still
requires adapter-local Node dependencies plus safe `CLINE_SDK_PROVIDER_ID` and
`CLINE_SDK_MODEL_ID` environment settings; missing live configuration remains a
structured runtime blocker, not an example failure.

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

- [x] Diagnostic output lists normalized event type, safe summary, and SDK event
      type where safe.
- [x] High-cardinality or sensitive event payload fields are omitted or redacted.
- [x] Unknown SDK events are reported as diagnostic observations and do not become
      authoritative lifecycle evidence.

Task 8 implementation note: `scripts/diagnose_cline_sdk_events.py` exercises the
Python `ClineSdkSessionRunner` path and prints event-focused safe JSON containing
normalized event type, safe summary, optional SDK event type, safe path
references, blockers, terminal status, and diagnostic references. Normal output
omits raw runner stdout/stderr, raw SDK event payloads, raw model reasoning,
secrets, and raw repository content. Unknown SDK events are surfaced in an
`unknown_sdk_event_observations` list only when the protocol has already
normalized them as diagnostic evidence, and the payload explicitly marks that it
is not authoritative lifecycle evidence.

**Verification:**

- [x] Run the script in a configured local environment or document the exact
      unrun prerequisite.

CI-safe script test evidence: `uv run pytest tests/unit/scripts/test_diagnose_cline_sdk_events.py tests/unit/scripts/test_run_cline_sdk_adapter_example.py`
passed locally on 2026-07-29 with 9 tests. Live diagnostic evidence: the
2026-07-29 `.env`-loaded invocation of `scripts/diagnose_cline_sdk_events.py`
used the Python adapter path with `--safe-context purpose=event-diagnostics` and
did not print `.env` values. A first run using the default diagnostic prompt hit
the configured 30 second bound and returned structured blocker code
`sdk_runner_timeout`. A second run with `--timeout-seconds 120` and the minimal
instruction `Reply with one short safe sentence.` completed through the real SDK
adapter path with terminal status `completed`, safe diagnostic references for the
SDK agent ID, run ID, iteration count, and usage metadata, and normalized SDK
event observations for `run-started`, `message-added`, `turn-started`,
`assistant-text-delta`, `usage-updated`, `assistant-message`, `turn-finished`,
and `run-finished`. Unknown SDK event observations remained diagnostic-only, and
the output did not include raw runner stdout/stderr, raw SDK payloads, secrets,
model reasoning, or raw repository content.

**Dependencies:** Task 7

**Estimated scope:** Small

### Checkpoint: Adapter Examples Complete

- [x] `scripts/` examples demonstrate normal adapter execution.
- [x] `scripts/` examples demonstrate safe event diagnostics.
- [x] Documentation explains setup, prerequisites, and limitations.

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

- [x] Matrix covers `Agent.run`, event subscription, session identity,
      diagnostics, permission handling, tool approval, Plan/Act mediation,
      structured outcomes, timeout, interruption, and file-change evidence.
- [x] Matrix labels each capability as `Agent`-proven, `ClineCore`-proven,
      orchestrator-owned, unproven, unsupported, or blocked.
- [x] Every capability claim includes official SDK docs/API references and local
      real-SDK smoke test evidence.
- [x] Every reset MVP SDK requirement is mapped to documented SDK primitive,
      adapter-derived proof, or explicit blocker.
- [x] Plan/Act mediation remains unproven or blocked unless a direct SDK API
      reference and real smoke evidence prove observation and authorization
      semantics without prose inference.
- [x] `AgentRunResult.outputText` and SDK messages are treated as diagnostic or
      model-output evidence, not as authoritative lifecycle state or a substitute
      for role-specific structured outcomes.
- [x] Missing full-contract primitives block `--plan-file` delivery planning
      rather than being approximated from prose.

Task 9 implementation note: `docs/sdk-capability-matrix.md` now maps the reset
MVP SDK execution requirements to official SDK references, implemented adapter
evidence, local smoke evidence, orchestrator-owned checks, and explicit blockers.
The matrix marks minimal `Agent` execution, event subscription, ClineCore session
probing, tool policy coverage, timeout/interruption handling, and safe diagnostic
references as proven only within their documented scope. It keeps Plan/Act
observation, Act authorization, real dynamic permission approval, SDK-native
role-specific structured outcomes, and authoritative SDK file-change evidence
blocked or unproven. `AgentRunResult.outputText`, SDK messages, unknown events,
terminal output, Cline Checkpoints, and CLI probe observations remain
non-authoritative diagnostic/model-output evidence.

**Verification:**

- [x] Review matrix against `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md`
      and official SDK docs.
- [x] Review local real-SDK smoke evidence for every capability marked proven.

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

- [x] CLI probe naming/docs do not present terminal probing as the production SDK
      execution contract.
- [x] Useful subprocess/fake Cline tests remain available as compatibility tests.
- [x] Documentation references ADR 0002 where appropriate.

Task 10 implementation note: legacy CLI probe modules, ports, DTOs, scripts, and
manual proof entry points now describe themselves as compatibility/discovery
surfaces rather than SDK readiness evidence. `ClineCapabilityReport` exposes
`sdk_readiness_evidence=False`, JSON script output includes the same flag, and
script help text points readers to ADR 0002. Existing subprocess/fake Cline tests
remain in place as compatibility coverage.

**Verification:**

- [x] Run focused `cline_execution` tests.
- [x] Search for misleading CLI-readiness claims.

**Dependencies:** Task 9

**Estimated scope:** Small

### Checkpoint: Capability Gate Ready for Delivery Decision

- [x] SDK capability matrix is complete.
- [x] CLI probe surfaces are quarantined.
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

- Tasks 1-4a prove the minimal documented `Agent` path but are not sufficient for
  repository-changing lifecycle delivery.
- Tasks 1-6, including the `ClineCore` proof in Task 4b, are mandatory before any
  lifecycle delivery work.
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
  prove it from official SDK references plus local real-SDK smoke evidence.
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
| A minimal `Agent` proof is mistaken for full SDLC execution readiness. | High | Split Task 4 into `Agent` and `ClineCore` proofs; require `ClineCore` proof and capability matrix completion before repository-changing lifecycle work. |
| SDK tool policies default to enabled and auto-approved when unspecified. | High | Require explicit fail-closed tool policy coverage and dynamic approval evidence before permission capabilities are considered proven. |
| Official SDK references do not prove direct Plan/Act transition APIs. | High | Mark Plan/Act mediation unproven or blocked unless a focused SDK API reference and real smoke evidence prove observation and authorization semantics. |
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

- Which exact official SDK docs/API pages and local package APIs prove Plan/Act
  semantics and structured outcomes? The currently fetched focused SDK references
  do not prove a direct Plan/Act transition or Act-authorization API.
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
- The project uses npm for the adapter-local runner because the official SDK
  overview documents `npm install @cline/sdk` and local `npm` is available. The
  project commits adapter-local `package.json` and `package-lock.json`, installs
  dependencies from the adapter runner directory, and does not rely on global
  `@cline/sdk` installation.
- The existing `SessionRunner` contract and `session.py` DTOs evolve in place into
  the SDK-shaped application contract.
- Minimal `Agent` proof is separated from `ClineCore` capability proof. A
  successful `Agent.run(...)` does not prove sessions, workspace roots, built-in
  tools, dynamic permission approval, session artifacts, repository-changing
  execution, or Plan/Act mediation.
- Real SDK smoke/integration evidence is required locally before the adapter gate
  can be marked complete.
- `cline/sdk` is expected to provide Plan/Act and permission/tool approval
  support, but lifecycle delivery may rely on those capabilities only after
  official SDK docs/API references and local real-SDK smoke evidence prove them.
  The fetched focused SDK references prove tool policies and dynamic approval via
  `ClineCore`, but do not prove direct Plan/Act mediation.
- The full SDK execution contract from
  `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md` is the minimum gate
  before `--plan-file` implementation may use the SDK-first path.
