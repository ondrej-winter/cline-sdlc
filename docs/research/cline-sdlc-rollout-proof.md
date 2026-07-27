# Cline SDLC rollout proof

## Status

- Date: 2026-07-27
- Related plan task: `6.4` in `docs/plans/cline-sdlc-orchestrator-plan.md`
- Related specification section: `docs/specs/cline-sdlc-orchestrator-spec.md` — “Rollout and proof of concept”
- Decision: **supervised workflow-runner MVP accepted; not unattended-ready**

## Purpose

Task 6.4 records rollout evidence for the Cline SDLC workflow. The MVP execution
boundary is supervised and follows the same product class as
`../clinerules/tools/skills/run_cline_skill_workflow.py`: explicit argument-array
Cline invocations, repository working directory selection, optional isolated data
directories, logs, dry-run/review-only style controls, and operator-visible review
of results. The stricter proof matrix remains the gate only for describing the
plan-implementation mode as unattended-ready.

The proof is intentionally separate from the automated suite. Unit, contract,
integration, and portable end-to-end tests use fake Cline executables and
disposable Git repositories; they do not prove that the installed Cline CLI can
provide the runtime contracts needed for unattended execution.

## Unattended-readiness matrix result

| # | Required rollout exercise | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Run all four stage inputs in a disposable non-production repository. | Not executed with real Cline. | Current console composition remains `dry_run_only`; automated portable-host tests cover application behavior only. |
| 2 | Complete at least three serial low-risk implementation slices with one commit per slice. | Not executed with real Cline. | Application-level serial fixture coverage exists, but no real CLI-to-host rollout run was completed. |
| 3 | Interrupt one slice and resume it from a new orchestrator process. | Not executed with real Cline. | Deterministic fake-backed recovery coverage exists; real Cline interruption evidence remains absent. |
| 4 | Inject one malformed session outcome and verify bounded retry. | Not executed with real Cline. | Contract tests cover malformed outcomes with fake Cline only. |
| 5 | Trigger one prohibited operation and verify stop behavior. | Not executed with real Cline. | Operation-policy tests cover classification; the prior Cline CLI spike did not prove pre-execution permission mediation. |
| 6 | Alter material plan content after approval and verify invalidation. | Not executed with real Cline. | Application-level digest and reconciliation tests cover material drift. |
| 7 | Run final review with one remediable and one material finding. | Not executed with real Cline. | End-to-end fake-backed tests cover remediation and material blockers. |
| 8 | Confirm logs, artifacts, and commits contain no injected test secret. | Not executed with real Cline. | Redaction and portable-host tests cover deterministic fake-backed summaries and fixture Git history. |

## Blocking evidence

The unattended-readiness proof is blocked by the same runtime boundary documented in the
[Cline CLI capability spike](cline-cli-capability-spike.md): real Cline `3.0.46`
did not prove exactly one machine-detectable terminal outcome, pre-execution
permission mediation, interruption recovery observability, or required-skill
availability without unintended network behavior.

The supervised capability proof was rerun on 2026-07-27 after confirming `cline`
was available at `/Users/owinter/.nvm/versions/node/v22.22.3/bin/cline` and still
reported version `3.0.46`. The run used ignored disposable proof directory
`.cline-sdlc-proof/runs/20260727T103618Z/` and exited unsuccessfully: required
skills were still reported missing for `idea-refine`, `spec-driven-development`,
`planning-and-task-breakdown`, and `code-review-and-quality`; the supervised
session emitted `0` parseable terminal outcomes; and pre-execution permission
mediation plus interruption recovery observability remained unproven.

The current installed `cline-sdlc` console boundary also reports a `dry_run_only`
blocker instead of composing the implemented lifecycle use cases into real Cline
execution. That behavior is intentionally documented in `README.md`; it prevents
claiming a successful real-Cline rollout from the current entry point.

The supervised workflow-runner MVP may be described as accepted for its bounded
operator-supervised execution model. The project **must not be described as
unattended-ready** until a future supervised non-production proof demonstrates the
full unattended-readiness matrix with real Cline or an approved architecture
decision replaces the CLI execution boundary.

[ADR 0001](../adr/0001-keep-cline-cli-rollout-blocked-until-execution-contracts-are-proven.md)
records the current decision to separate the accepted supervised workflow-runner
MVP from the still-blocked unattended-ready claim.

## Checkpoint F review

Checkpoint F was initially reviewed as blocked on 2026-07-26 because the review
applied the unattended-ready proof bar to the whole MVP. The product boundary was
clarified on 2026-07-27: Tasks 6.1–6.4 are sufficient for the supervised
workflow-runner MVP, while the failed real-Cline proof remains evidence against
unattended readiness only.

The 2026-07-27 rerun confirms the blocker is still current for Cline `3.0.46` in
this environment.

The proof tooling was updated on 2026-07-27 to recognize repository-local
skills under `.agents/skills/<skill>/SKILL.md` when the supervised proof runs
against a disposable repository. This removes the previous false-negative skill
availability blocker for repositories that vendor the required skills locally,
but it does not change the unattended-readiness decision: terminal outcomes,
pre-execution permission mediation, and interruption recovery observability still
require a future successful real-Cline proof or a superseding execution-boundary
ADR before any unattended-ready claim.

This is not a waiver for autonomous execution. It preserves the specification
requirement that failure to demonstrate structured outcomes, bounded permissions,
or reliable dirty-tree recovery blocks unattended readiness instead of weakening
those contracts.

## Next action

Before claiming unattended readiness, choose one of these paths:

1. configure or upgrade real Cline so the missing CLI contracts can be proven,
   then rerun the supervised proof in a disposable repository; or
2. record an architecture decision that redirects execution to a boundary capable
   of providing terminal outcomes, permission mediation, interruption recovery,
   and skill availability evidence.

ADR 0001 covers the current supervised-MVP and unattended-readiness decision. A future replacement-boundary
proposal must be recorded as a new ADR rather than modifying the proof result in
place.
