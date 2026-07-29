# Cline SDK-First SDLC Orchestrator

## Problem Statement

How might we coordinate repeatable Cline-driven SDLC work without building the
product foundation on fragile terminal probing, CLI capability inference, or
reverse-engineered Plan/Act behavior?

`cline-sdlc` should still be a Cline-oriented orchestrator. The concern is not
that Cline is the wrong runtime; the concern is that `cline-cli` is the wrong
primary integration boundary for the deeper orchestration contract. The current
probe-heavy direction asks the project to prove and maintain too much behavior at
the terminal edge before it can safely implement the actual lifecycle loop.

## Recommended Direction

Make a `cline-sdk`-shaped contract the intended execution boundary. The
orchestrator should mimic and coordinate Cline sessions through explicit SDK
concepts instead of inferring them from CLI behavior.

The core orchestrator remains responsible for durable workflow authority:

- accepted idea, specification, and plan artifacts;
- plan material digests and progress state;
- slice selection and approval boundaries;
- repository reconciliation and Git commits;
- validation evidence;
- terminal results, run summaries, and blockers.

Cline remains responsible for agent work inside bounded sessions: using skills,
planning, acting, editing files through approved tools, reviewing, and reporting
structured outcomes. The SDK contract should expose those session semantics
directly enough that the orchestrator does not depend on terminal scraping or
probe adapters as production architecture.

## Concept Model

### Cline SDK session

A Cline SDK session is a bounded unit of Cline work created by the orchestrator.
It receives explicit instructions, repository context, policy constraints, and an
outcome contract. It exposes session identity, lifecycle state, events or
evidence, and a structured terminal outcome.

### Plan/Act transition

Implementation sessions should preserve Cline's Plan/Act semantics. The SDK
contract should let the orchestrator observe a planning result, classify it as
`needs_user_input` or `ready_to_act`, and authorize Act mode only when invocation
approval and operation policy allow it.

### Tool and change evidence

The SDK boundary should expose enough information to reconcile Cline's work with
repository state. The orchestrator must still independently inspect Git state,
changed paths, validation commands, and material artifact digests before it
commits or advances lifecycle state.

## Key Assumptions to Validate

- [ ] A supported `cline-sdk` exists, is planned, or can be implemented as a
      stable local facade without relying on terminal scraping.
- [ ] The SDK can start fresh bounded sessions with explicit instructions,
      repository context, and configured skill availability.
- [ ] The SDK can represent Cline Plan/Act state transitions without relying on
      prose interpretation.
- [ ] The SDK can expose structured session outcomes for authoring, reviewing,
      implementation, remediation, and final review roles.
- [ ] The SDK can expose tool-use, file-change, approval, interruption, timeout,
      and blocker evidence suitable for independent reconciliation.
- [ ] The SDK can provide audit pointers such as session ids, logs, or checkpoint
      references without making those pointers authoritative workflow state.
- [ ] If a supported SDK does not exist yet, a deliberate architecture decision
      can choose between blocking, contributing/upstreaming an SDK, or building a
      narrow local SDK facade as an explicitly transitional adapter.

## MVP Scope

The reset MVP should prove the core SDK-backed orchestration loop, not lifecycle
hooks or repository task recipes.

In scope:

- define the `cline-sdk` execution contract in product and application terms;
- model a bounded Cline session request, planning result, Act authorization,
  event/evidence stream, and structured terminal outcome;
- run one accepted implementation slice through the SDK-shaped boundary;
- reconcile changed paths, validation evidence, plan progress, and Git state
  independently of Cline output;
- create one local atomic commit only when orchestrator-owned checks pass;
- produce a safe terminal result and run summary.

Out of scope for the reset MVP:

- lifecycle hooks and repository task recipes;
- `conventional-commit-staged` as the first proof point;
- production use of probe adapters or terminal scraping as the authoritative
  execution contract;
- generic Codex/OpenAI SDK migration;
- multiple agent runtimes;
- unattended-readiness claims before the SDK contract is proven.

## Not Doing and Why

- Building further around `cline-cli` probes — this spends effort proving the
  wrong boundary and encourages terminal behavior to become production contract.
- Treating Cline Checkpoints or chat prose as workflow authority — repository
  artifacts, Git state, validation evidence, and structured SDK outcomes remain
  the durable sources of truth.
- Continuing lifecycle hooks first — hooks and recipes are useful later, but they
  depend on a trustworthy Cline execution boundary.
- Pivoting to Codex-native orchestration — the product remains Cline-oriented and
  should preserve Cline semantics.

## Open Questions

- Does a supported `cline-sdk` currently exist, and what lifecycle/session
  primitives does it expose?
- If not, is the right next step to design a local SDK facade, contribute an
  upstream SDK, or keep `cline-sdlc` blocked at the execution boundary?
- Which SDK event fields are necessary for permission policy and reconciliation,
  and which are merely diagnostic?
- Can Plan/Act mode changes be mediated through the SDK, or must the first SDK
  contract be limited to supervised sessions?
- How should existing `cline_execution` ports and fake Cline tests be renamed or
  quarantined so they do not imply production CLI readiness?
