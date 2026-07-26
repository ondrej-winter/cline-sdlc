# Cline SDLC rollout proof

## Status

- Date: 2026-07-26
- Related plan task: `6.4` in `docs/plans/cline-sdlc-orchestrator-plan.md`
- Related specification section: `docs/specs/cline-sdlc-orchestrator-spec.md` — “Rollout and proof of concept”
- Decision: **not unattended-ready**

## Purpose

Task 6.4 records the supervised rollout proof required before describing the
plan-implementation mode as unattended-ready. The proof must exercise the
specification’s rollout matrix in a disposable non-production repository using a
supported real Cline CLI, then record redacted evidence for the architecture and
readiness decision.

The proof is intentionally separate from the automated suite. Unit, contract,
integration, and portable end-to-end tests use fake Cline executables and
disposable Git repositories; they do not prove that the installed Cline CLI can
provide the runtime contracts needed for unattended execution.

## Rollout matrix result

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

The rollout proof is blocked by the same runtime boundary documented in the
[Cline CLI capability spike](cline-cli-capability-spike.md): real Cline `3.0.46`
did not prove exactly one machine-detectable terminal outcome, pre-execution
permission mediation, interruption recovery observability, or required-skill
availability without unintended network behavior.

The current installed `cline-sdlc` console boundary also reports a `dry_run_only`
blocker instead of composing the implemented lifecycle use cases into real Cline
execution. That behavior is intentionally documented in `README.md`; it prevents
claiming a successful real-Cline rollout from the current entry point.

## Readiness decision

The project **must not be described as unattended-ready**. Checkpoint F remains
open until a future supervised non-production proof demonstrates the full rollout
matrix with real Cline or an approved architecture decision replaces the CLI
execution boundary.

## Checkpoint F review

Checkpoint F was reviewed as blocked on 2026-07-26. Tasks 6.1–6.4 are complete,
and their automated or documentary evidence is linked from the implementation
plan, but the checkpoint cannot be accepted because the required real-Cline
rollout proof was not executed successfully. This review records the blocked
state explicitly; it is not a waiver of the rollout requirement.

This blocked result is not a waiver. It preserves the specification requirement
that failure to demonstrate structured outcomes, bounded permissions, or reliable
dirty-tree recovery triggers product/architecture review instead of weakening the
contracts.

## Next action

Before reopening the rollout proof, choose one of these paths:

1. configure or upgrade real Cline so the missing CLI contracts can be proven,
   then rerun the supervised proof in a disposable repository; or
2. record an architecture decision that redirects execution to a boundary capable
   of providing terminal outcomes, permission mediation, interruption recovery,
   and skill availability evidence.
