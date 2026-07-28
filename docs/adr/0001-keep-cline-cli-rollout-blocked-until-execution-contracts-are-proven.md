# ADR 0001: Separate supervised Cline workflow execution from unattended readiness

## Status

Accepted

## Context

`cline-sdlc` is designed to coordinate bounded lifecycle stages through Cline while
using repository artifacts, validation evidence, and Git history as authoritative
workflow state. Earlier proof notes treated machine-detectable terminal outcomes,
enforceable operation mediation, observable interruption recovery, and required-skill
availability as prerequisites for accepting the MVP.

The product scope has since been clarified: the MVP is a supervised workflow runner
modeled after `../clinerules/tools/skills/run_cline_skill_workflow.py`, with more
structured artifact, validation, and lifecycle boundaries. That reference runner
builds explicit argument-array Cline commands, uses `--cwd`, optional `--data-dir`,
logs stdout/stderr, supports dry-run/review-only operation, and leaves supervision
and result interpretation to the operator instead of claiming that Cline-authored
terminal output is independently authoritative.

The supervised Cline CLI capability proof and the 2026-07-27 rerun against Cline
`3.0.46` did not prove the stricter unattended contracts. The rerun reported `0`
parseable terminal outcomes and unproven permission/interruption evidence; local
skill discovery is now covered through `.agents/skills/<skill>/SKILL.md` probing.

Those missing contracts remain blockers for any future claim that Cline itself
provides machine-authoritative unattended terminal outcomes, but they do not block
the supervised workflow-runner MVP because that mode makes the orchestrator's
transaction classification authoritative after process observation, repository
reconciliation, validation evidence, and operator-visible review points.

## Decision

Accept the supervised Cline workflow-runner boundary as the MVP execution model.
This boundary may invoke real Cline through explicit argument arrays, repository
working directories, logs, bounded prompts, and operator-visible stage stops, following
the same product class as `run_cline_skill_workflow.py` while adding SDLC-specific
artifact and validation structure.

Keep only the **Cline-authored unattended terminal outcome** claim blocked until
one of these conditions is satisfied:

1. a future configured or upgraded real Cline CLI supervised proof demonstrates the
   full rollout matrix in a disposable non-production repository; or
2. a follow-up architecture decision replaces the CLI execution boundary with an
   execution mechanism that can provide terminal outcomes, permission mediation,
   interruption recovery evidence, and required-skill availability without weakening
   the accepted contracts.

Until then, the repository must continue to distinguish orchestrator-owned
supervised slice transactions from Cline-authored autonomous terminal outcomes.
The console boundary may be presented as a supervised workflow runner once
composed and validated against that boundary, but not as autonomous real-Cline
orchestration whose lifecycle state is proven solely by Cline output.

## Consequences

- The failed unattended-contract proof is no longer an MVP blocker for supervised
  workflow-runner execution.
- Future implementation work may improve proof tooling or compose additional dry-run
  surfaces, but it must not claim unattended readiness without successful proof or a
  superseding execution-boundary ADR.
- Documentation must keep linking the blocked unattended-readiness evidence so
  operators can distinguish supervised workflow execution from autonomous execution.
- If a replacement boundary is proposed, it must preserve the same safety properties
  and define how outcomes, permissions, interruption recovery, and skill availability
  are independently verified.
