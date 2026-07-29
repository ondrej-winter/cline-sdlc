# Spec: Cline SDK-First SDLC Orchestrator

## Status

- Artifact type: product and behavior specification
- Date: 2026-07-29
- Source brief: `docs/ideas/cline-sdk-first-sdlc-orchestrator-idea.md`
- Related ADR: `docs/adr/0002-use-cline-sdk-contract-instead-of-cli-probing.md`
- Related product spec: `docs/specs/cline-sdlc-orchestrator-spec.md`
- Decision state: draft specification from accepted SDK-first direction
- Lifecycle stage: specification creation
- Intended scope: SDK-shaped Cline execution boundary for the reset MVP

## Objective

Define the SDK-first execution boundary required for `cline-sdlc` to coordinate
repeatable Cline-driven SDLC work without relying on fragile terminal probing,
CLI capability inference, or reverse-engineered Plan/Act behavior.

The feature is for engineers using `cline-sdlc` who want the orchestrator to
preserve Cline semantics while making durable workflow authority explicit:
accepted artifacts, material digests, plan progress, repository reconciliation,
validation evidence, Git commits, run summaries, and blockers.

The reset MVP must prove the core SDK-backed orchestration loop before adding
lifecycle hooks, repository task recipes, multiple agent runtimes, or unattended
readiness claims beyond the proven SDK contract.

## Current context

`cline-sdlc` is a Cline-oriented orchestrator. The problem is not that Cline is
the wrong runtime; the problem is that `cline-cli` terminal behavior is the wrong
primary integration boundary for deeper orchestration guarantees.

The prior probe-heavy direction asked the project to infer too much behavior from
the terminal edge before implementing the lifecycle loop. That direction risks
turning reverse-engineered CLI behavior, terminal scraping, fake capability
signals, and chat prose interpretation into production architecture.

ADR 0002 accepts a `cline-sdk`-shaped contract as the intended primary execution
boundary. The broader orchestrator specification already incorporates this pivot:
the application core should coordinate bounded Cline sessions through explicit
SDK semantics while retaining independent authority over lifecycle state,
repository state, validation evidence, and local commits.

The configurable lifecycle hooks and repository task recipe work is intentionally
deferred until this execution boundary is specified and proven. Hooks and recipes
may become useful later, but they depend on a trustworthy Cline execution
contract.

## Assumptions

1. A supported `cline-sdk` exists, is planned, or can be implemented as a stable
   local facade without relying on terminal scraping as its production contract.
2. The SDK can start fresh bounded sessions with explicit instructions,
   repository context, policy constraints, configured skill availability, and a
   structured outcome contract.
3. The SDK can represent Cline Plan/Act state transitions without requiring the
   orchestrator to infer readiness from ordinary assistant prose.
4. The SDK can expose structured session outcomes for authoring, reviewing,
   implementation, remediation, and final-review roles.
5. The SDK can expose tool-use, file-change, approval, interruption, timeout,
   blocker, and validation evidence suitable for independent reconciliation.
6. SDK diagnostic pointers such as session identifiers, logs, transcripts, or
   checkpoint references are useful for audit and troubleshooting but are not
   authoritative lifecycle state.
7. If a supported SDK is not available, the project must explicitly choose
   between blocking, contributing or upstreaming an SDK, or building a narrow
   transitional SDK facade.
8. CLI probing, terminal scraping, and chat prose parsing must not be treated as
   production-equivalent substitutes for the SDK execution contract.

## Vocabulary

- **Cline SDK session**: A bounded unit of Cline work created by the orchestrator.
  It receives explicit instructions, repository context, policy constraints, and
  an outcome contract. It exposes session identity, lifecycle state, events or
  evidence, and a structured terminal outcome.
- **Plan/Act transition**: The Cline session boundary where inspection and
  planning ends and repository-changing work may begin. The SDK must expose this
  transition so the orchestrator can classify a planning result and authorize Act
  mode only when approved policy allows it.
- **Planning result**: A structured SDK observation indicating either
  `needs_user_input` or `ready_to_act` for an implementation session.
- **Act authorization**: Orchestrator approval for a specific bounded session to
  perform repository-changing work within the accepted specification, plan slice,
  invocation approval, and operation policy.
- **SDK evidence**: Structured observations from the Cline SDK, such as tool-use,
  changed-path, validation, approval, timeout, interruption, blocker, and
  diagnostic-reference events.
- **Structured session outcome**: The role-specific machine-readable outcome
  returned by a Cline session. It is evidence for reconciliation, not the sole
  authority for lifecycle advancement.
- **Authoritative workflow state**: Repository artifacts, material digests, plan
  progress, Git state, validation evidence, local commits, terminal results, and
  run summaries owned by the orchestrator.
- **Transitional SDK facade**: A narrow local adapter that presents SDK-shaped
  semantics while an official SDK is unavailable. It must be explicitly
  documented as transitional and must not depend on terminal scraping for
  production-grade guarantees.

## Desired behavior

### SDK-shaped execution boundary

The application core must depend on Cline execution ports that express SDK
semantics directly. The boundary must describe Cline sessions in product and
application terms rather than terminal process details.

The SDK-shaped boundary must support:

- fresh bounded session creation;
- explicit session role selection;
- explicit instructions and repository context;
- configured skill availability requirements;
- operation policy and permission constraints;
- Plan/Act observation and authorization for implementation sessions;
- structured event or evidence streams;
- structured role-specific terminal outcomes;
- timeouts and interruption handling;
- diagnostic references for audit and troubleshooting.

The orchestrator must not treat raw terminal output, chat prose, or Cline
Checkpoint existence as sufficient evidence that a stage or slice completed.

### Orchestrator authority

The orchestrator remains responsible for durable workflow authority. It must
independently inspect and reconcile:

- accepted idea, specification, and plan artifacts;
- specification and plan material digests;
- plan progress and active slice state;
- repository status, changed paths, and Git history;
- validation command evidence;
- local atomic commits;
- terminal results, run summaries, and blockers.

SDK observations are inputs to reconciliation. They do not replace artifact,
digest, validation, and Git checks.

### Plan/Act mediation

Implementation sessions must preserve Cline's Plan/Act semantics.

Each implementation session starts in a planning state. Before Act mode is
authorized, the SDK must expose one of these planning results:

- `needs_user_input`: Cline asked a material question, identified missing context,
  proposed a decision outside accepted material, or produced ambiguous planning
  evidence.
- `ready_to_act`: Cline has no material questions and the proposed approach fits
  the accepted specification, assigned plan slice, invocation approval, and
  operation policy.

When the planning result is `needs_user_input`, the invocation must stop without
acting or committing. When the result is `ready_to_act`, the orchestrator may
authorize Act mode for that same bounded session if operation policy also allows
it.

The orchestrator must not infer `ready_to_act` from ordinary prose.

### Session evidence and outcomes

The SDK contract must expose enough evidence to reconcile Cline's work with the
repository. Evidence should include, where applicable:

- session identity and role;
- lifecycle state transitions;
- tool-use requests and results;
- file-change observations;
- validation commands and outcomes;
- permission checks and approval requests;
- blockers and material questions;
- timeouts, cancellations, and interruptions;
- diagnostic pointers such as logs, transcripts, or checkpoint references.

Structured session outcomes must be role-specific and machine-readable. At
minimum, the contract must support outcomes for:

- idea refinement;
- specification authoring;
- plan authoring;
- plan review;
- implementation;
- remediation;
- final review.

Missing, invalid, duplicate, contradictory, or path-unsafe structured outcomes
must fail closed.

### Reset MVP loop

The reset MVP must prove one accepted implementation slice through the
SDK-shaped boundary:

1. verify accepted specification and plan material digests;
2. select one accepted implementation slice;
3. start a fresh SDK-backed Cline session with bounded instructions;
4. observe the planning result;
5. authorize Act mode only for `ready_to_act` within policy;
6. collect SDK evidence and structured outcome;
7. independently reconcile changed paths, plan progress, validation evidence, and
   Git state;
8. create one local atomic commit only when orchestrator-owned checks pass;
9. produce a safe terminal result and run summary.

The MVP may stop after proving this core loop. It must not claim broader
unattended readiness until the SDK contract, reconciliation, permission evidence,
interruption handling, and recovery behavior are proven.

## SDK execution contract requirements

### Session request

The application port for starting a Cline session must accept a request object
that can represent:

- stable session role;
- repository root or explicit working directory;
- accepted artifact paths and digests;
- current plan slice or review assignment;
- instructions and outcome contract;
- required skills;
- allowed operation profile;
- timeout;
- read-only versus write-capable mode;
- optional diagnostic or data-directory settings.

Transport schemas, terminal-specific arguments, and framework objects must remain
inside adapters. Application ports should use application DTOs or domain values.

### Planning result

Implementation-capable sessions must expose a structured planning result before
repository-changing work starts. The result must include:

- status: `needs_user_input` or `ready_to_act`;
- safe summary;
- material questions or missing context, when present;
- proposed operation summary, when relevant;
- diagnostic reference, when available.

Unsupported, missing, or ambiguous planning results must be treated as
`needs_user_input`.

### Act authorization

The SDK boundary must let the orchestrator authorize Act mode explicitly for a
single bounded session. Authorization must include the accepted artifact digests,
assigned slice identity, operation policy, and timeout envelope. Authorization
must not be reusable across sessions, slices, material plan revisions, or changed
specification digests.

### Event and evidence stream

The SDK should provide either a structured event stream or an equivalent evidence
collection. The contract must distinguish diagnostic events from reconciliation
evidence so the orchestrator can avoid treating non-authoritative logs as durable
state.

### Terminal outcome

Every session role that contributes artifact, review, implementation, or
validation claims must return a structured terminal outcome. The outcome must use
closed enum values for status and role, safe repository-relative paths, and
explicit blocker information when incomplete.

## MVP scope

### In scope

- Define the SDK execution contract in product and application terms.
- Model bounded Cline session requests.
- Model planning results and Act authorization.
- Model event or evidence streams.
- Model structured terminal outcomes.
- Run one accepted implementation slice through the SDK-shaped boundary.
- Reconcile changed paths, validation evidence, plan progress, and Git state
  independently of Cline output.
- Create one local atomic commit only when orchestrator-owned checks pass.
- Produce a safe terminal result and run summary.

### Out of scope

- Lifecycle hooks and repository task recipes.
- `conventional-commit-staged` as the first proof point.
- Production use of probe adapters or terminal scraping as the authoritative
  execution contract.
- Generic Codex/OpenAI SDK migration.
- Multiple agent runtimes.
- Concurrent implementation sessions or concurrent repository writers.
- Pushes, pull requests, releases, publication, or deployment.
- Unattended-readiness claims before the SDK contract is proven.

## Project structure

- Spec: `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md`
- Source idea: `docs/ideas/cline-sdk-first-sdlc-orchestrator-idea.md`
- ADR: `docs/adr/0002-use-cline-sdk-contract-instead-of-cli-probing.md`
- Related broad spec: `docs/specs/cline-sdlc-orchestrator-spec.md`
- Application ports and DTOs: `src/cline_sdlc/features/cline_execution/application/`
- SDK adapters: `src/cline_sdlc/features/cline_execution/adapters/outbound/`
- Orchestration use cases: `src/cline_sdlc/features/lifecycle_orchestration/application/`
- Unit tests: `tests/unit/features/cline_execution/` and
  `tests/unit/features/lifecycle_orchestration/`
- Contract tests: `tests/contract/features/cline_execution/` and
  `tests/contract/features/lifecycle_orchestration/`
- Integration tests: `tests/integration/features/lifecycle_orchestration/`

Implementation should start with SDK-shaped application ports in the
`cline_execution` slice before adding or expanding adapters. Existing CLI probes,
subprocess runners, and fake Cline components may remain as discovery or test
fixtures, but they must be named and documented so they do not imply production
CLI readiness.

## Conventions

- Follow hexagonal vertical-slice boundaries: application ports express the Cline
  execution contract; adapters contain SDK, CLI, subprocess, or transport details.
- Use application DTOs under the owning slice's `application/dtos/` for command,
  request, result, and evidence shapes crossing the application boundary.
- Keep business workflow authority in lifecycle orchestration use cases, not SDK
  adapters.
- Fail closed for unsupported SDK capabilities, missing structured outcomes,
  ambiguous planning results, unsafe paths, and evidence contradicted by Git.
- Do not log secrets, raw prompts with sensitive repository content, or model
  reasoning by default.
- Do not treat Cline Checkpoints, chat prose, terminal output, or diagnostic logs
  as authoritative lifecycle state.
- Do not add lifecycle hooks, repository task recipes, generic multi-agent
  abstractions, or Codex-native orchestration as part of this reset MVP.

## Testing strategy

- Add application-level contract tests for SDK session request construction,
  planning result handling, Act authorization, and terminal outcome validation.
- Add fake SDK tests that prove the orchestrator responds correctly to
  `needs_user_input`, `ready_to_act`, missing outcomes, invalid outcomes,
  timeouts, interruptions, and approval requests.
- Add reconciliation tests proving that SDK-reported changed paths and validation
  evidence are checked against Git state and plan progress before commits.
- Add fail-closed tests for unsupported capabilities, terminal-scraping-only
  adapters, ambiguous Plan/Act evidence, path traversal, duplicate outcomes, and
  reviewer writes.
- Add integration tests only where adapter behavior or Git reconciliation requires
  real filesystem or repository interactions.
- Keep most tests fast, isolated, and deterministic with hand-written fakes rather
  than broad mocks of domain or application objects.

## Commands and validation

- Format: `uv run ruff format .`
- Lint: `uv run ruff check .`
- Type check: `uv run mypy .`
- Test: `uv run pytest`
- Focused SDK contract tests, once implemented:
  `uv run pytest tests/contract/features/cline_execution tests/contract/features/lifecycle_orchestration`

## Boundaries

- Always: define SDK-facing contracts in application terms before adding concrete
  adapters.
- Always: independently reconcile artifacts, digests, validation evidence, and
  Git state before advancing lifecycle state or committing.
- Always: preserve fresh-session isolation for implementation, remediation,
  review, and final-review responsibilities.
- Ask first: choose a transitional local SDK facade, contribute upstream SDK work,
  or block implementation if no supported SDK exists.
- Ask first: weaken protected operation policy, branch protection defaults,
  outcome schema strictness, or evidence requirements.
- Never: make terminal scraping, CLI probe output, chat prose, or Cline
  Checkpoints the production execution contract.
- Never: claim unattended readiness without proven structured outcomes,
  permission evidence, interruption recovery, and repository reconciliation.

## Success criteria

- The SDK-first execution contract is documented in product and application terms.
- The spec clearly separates Cline responsibilities from orchestrator workflow
  authority.
- Plan/Act mediation is defined without relying on prose interpretation.
- Required SDK session request, planning result, Act authorization, evidence, and
  terminal outcome concepts are explicit.
- MVP scope proves one accepted implementation slice before deferred hooks,
  recipes, or broader unattended claims.
- Out-of-scope items prevent `cline-cli` probes, lifecycle hooks, repository task
  recipes, and multi-runtime migration from entering the reset MVP.
- Project structure points future implementation toward the `cline_execution`
  application ports and focused tests.
- Open questions identify the decisions that must be resolved before production
  implementation can rely on the SDK boundary.

## Open questions

- Does a supported `cline-sdk` currently exist, and what lifecycle, session,
  Plan/Act, event, and outcome primitives does it expose?
- If no supported SDK exists, should `cline-sdlc` block, contribute or upstream an
  SDK, or build a narrow transitional SDK facade?
- Which SDK event fields are necessary for permission policy and reconciliation,
  and which are diagnostic only?
- Can Plan/Act mode changes be mediated directly through the SDK, or must the
  first SDK contract be limited to supervised sessions?
- Which existing `cline_execution` ports, fake Cline tests, subprocess runners, or
  probe scripts should be renamed, quarantined, or deprecated so they do not imply
  production CLI readiness?
- What is the minimum SDK capability set required before the orchestrator may
  safely run the first implementation-slice proof?
