# ADR 0002: Use a Cline SDK contract instead of CLI probing as the execution boundary

## Status

Accepted

## Context

`cline-sdlc` is intended to coordinate Cline-driven SDLC work: idea refinement,
specification, planning, implementation slices, reviews, validation, and local
commits. The product should preserve Cline semantics, especially bounded fresh
sessions, Plan/Act transitions, tool permissions, task progress, and structured
completion evidence.

The current implementation direction was accumulating probe scripts, fake CLI
contracts, terminal outcome parsing, and repository task machinery to compensate
for missing or unproven `cline-cli` execution guarantees. That approach risks
turning reverse-engineered CLI behavior into the production contract. It also
pulls attention toward lifecycle hooks and repository task recipes before the
core Cline execution boundary is stable.

ADR 0001 allowed a supervised workflow-runner boundary while keeping stricter
unattended Cline-authored outcome claims blocked. This decision supersedes the
next architecture direction: the project should not deepen production reliance
on CLI probing when what it actually needs is an SDK-shaped Cline session
contract.

## Decision

Use a `cline-sdk`-shaped contract as the intended primary execution boundary for
future `cline-sdlc` orchestration.

The application core should depend on Cline execution ports that express SDK
semantics directly, including:

- session creation with bounded instructions and repository context;
- observable planning results and Plan/Act authorization;
- structured terminal outcomes for author, reviewer, implementation,
  remediation, and final-review roles;
- tool-use, file-change, validation, approval, timeout, interruption, and blocker
  evidence;
- session identity and diagnostic log/checkpoint references that aid audit but do
  not become authoritative workflow state.

The orchestrator remains authoritative for durable lifecycle state: artifacts,
material digests, plan progress, Git reconciliation, validation evidence, local
commits, terminal results, and run summaries.

`cline-cli` adapters, probe scripts, and fake terminal runners may be retained as
temporary discovery, compatibility, or test fixtures, but they must not be
described as the production execution contract for SDK-first orchestration.

## Consequences

- The configurable lifecycle hooks and repository task recipe plan is deferred as
  active implementation work until the SDK execution boundary is specified.
- Future implementation planning should start with SDK-shaped application ports
  in the `cline_execution` slice before adding or expanding adapters.
- If a supported `cline-sdk` does not exist, the project must explicitly decide
  whether to block, contribute/upstream an SDK, or build a narrow transitional SDK
  facade. It must not silently treat CLI probing as equivalent.
- Documentation and specs must distinguish Cline product semantics from the
  transport mechanism used to drive Cline.
- Unattended-readiness claims still require proven structured outcomes,
  permission evidence, interruption recovery, and reconciliation. Moving to an
  SDK contract does not weaken fail-closed behavior.
