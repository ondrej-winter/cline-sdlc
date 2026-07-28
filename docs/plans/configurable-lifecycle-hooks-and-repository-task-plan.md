# Implementation Plan: Configurable Lifecycle Hooks and Repository Task Recipes

## Overview

Implement the accepted configurable lifecycle hooks and repository task recipe specification by adding an orchestrator-owned, static repository-task model for the built-in `conventional-commit-staged` recipe. The first implementation slice is intentionally standalone-only: it must support standalone invocation as `cline-sdlc task conventional-commit-staged`, deterministic Conventional Commit validation, explicit accept/reject approval, and non-interactive local Git commit creation for exactly authorized staged content. Embedded reuse at the `before_slice_commit` plan-implementation hook is deferred until the standalone task boundary is proven.

This plan is an initial implementation plan only. It is based on the accepted specification at `docs/specs/configurable-lifecycle-hooks-and-repository-task-spec.md`, active repository rules, and current implementation patterns in the `src/cline_sdlc/features/*` vertical slices.

## Architecture Decisions

- Add a new feature slice under `src/cline_sdlc/features/repository_tasks/` for recipe-owned domain policy, application DTOs/use cases/ports, and task-specific adapters. This keeps recipe contracts distinct from lifecycle-stage orchestration while allowing explicit inbound calls from CLI and lifecycle hook composition.
- Keep Git inspection and Git mutation operations in the existing `repository_coordination` slice as typed outbound ports/adapters. The new recipe slice should depend on application-level ports/DTOs, not Git CLI implementations.
- Keep bounded Cline skill execution behind a recipe-specific proposal DTO/parser owned by `repository_tasks`; do not extend lifecycle-oriented `SessionOutcome` for the standalone-first implementation.
- Defer `before_slice_commit` lifecycle hook integration. When embedded mode resumes, it must be treated as an orchestrator-owned hook concept in lifecycle orchestration, not as repository-defined workflow configuration.
- Defer plan-state `recipe_evidence` changes while embedded mode is out of scope. The standalone-first implementation should rely on terminal evidence only unless a later plan revision adds run-summary evidence explicitly.
- Preserve existing flag-driven lifecycle invocations unchanged while adding only the canonical task command form `cline-sdlc task conventional-commit-staged`. Do not add `--task` as a canonical form.

## Existing Patterns and Likely Touchpoints

- Source layout: `src/cline_sdlc/features/<feature>/{domain,application,adapters}` with tests mirrored under `tests/{unit,contract,integration,e2e}/features/<feature>/...`.
- CLI entry: `src/cline_sdlc/bootstrap/cli.py` delegates to `src/cline_sdlc/features/lifecycle_orchestration/adapters/inbound/cli.py`.
- Current stage orchestration: `lifecycle_orchestration/application/use_cases/*` composes ports and returns typed terminal results.
- Current slice commit boundary: `repository_coordination/application/use_cases/commit_slice.py`, `application/dtos/slice_commit.py`, `application/ports/slice_commit.py`, and `adapters/outbound/git_slice_commit.py`.
- Current Git inspection: `repository_coordination/application/use_cases/inspect_repository.py`, `application/dtos/repository.py`, `application/ports/git.py`, and `adapters/outbound/git_cli.py`.
- Current session execution: `cline_execution/application/dtos/session.py`, `cline_execution/domain/outcome.py`, `cline_execution/adapters/outbound/terminal_outcomes.py`, and lifecycle session-attempt use cases.
- Current validation command discovery must continue to surface these authoritative final validation commands in docs and workflows:
  - `uv run ruff format --check .`
  - `uv run ruff check .`
  - `uv run mypy .`
  - `uv run pytest`
  - `uv build`

## Progress Tracking

Treat this plan as a living document during implementation. After each completed task or meaningful change:

- check off completed tasks, acceptance criteria, verification items, and checkpoints;
- leave unfinished or unverified items unchecked;
- add newly discovered work and update sequencing when scope or dependencies change;
- note blockers, deviations, and decisions that affect remaining work;
- keep task status current without waiting for a separate progress request.

Do not mark the implementation complete until all checkpoints, validation commands, tests, and documentation updates are complete or explicitly documented as blocked.

## Task List

### Phase 1: Recipe Foundation and Policy

## Task 1: Add repository task recipe domain model and built-in registry

**Description:** Create the new `repository_tasks` feature slice with domain concepts for recipe identity, invocation mode, deferred hook-point eligibility, primitive category, recipe definition, and the built-in `conventional-commit-staged` static recipe. The model must enforce the closed MVP primitive taxonomy and avoid repository-defined workflow control. Standalone mode is the only implemented invocation mode in the first slice; embedded hook execution remains represented only as deferred policy metadata.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_tasks/domain/recipe.py`
- `src/cline_sdlc/features/repository_tasks/domain/policy.py`
- `src/cline_sdlc/features/repository_tasks/application/dtos/recipe.py`
- `tests/unit/features/repository_tasks/domain/test_recipe.py`

**Acceptance criteria:**

- [ ] `conventional-commit-staged` is defined as a built-in orchestrator-owned recipe.
- [ ] The only deferred embedded hook allowed for the recipe is `before_slice_commit`; no embedded hook execution is wired in the standalone-first MVP.
- [ ] The only MVP primitive categories are skill proposal, Git inspection, validation, approval, Git mutation, and evidence.
- [ ] The recipe definition is static and linear; no branching, loops, dynamic step selection, repository-defined commands, imports, prompts, or workflow topology are represented.
- [ ] Unknown recipe ids, hook names, primitive categories, and invocation modes fail closed.

**Verification:**

- [ ] Run focused unit tests for `repository_tasks/domain`.
- [ ] Confirm no new dependencies or configuration files are introduced.

## Task 2: Add deterministic Conventional Commit validation

**Description:** Implement application/domain validation for proposed commit messages independent of the `conventional-commits` skill. Validation must support the accepted default type allowlist, optional scope, optional breaking marker, multiline body/footer rules, standard footers, `BREAKING CHANGE:` notes, `Cline-SDLC-*` trailers, and safe non-interactive Git execution constraints.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_tasks/domain/conventional_commit.py`
- `src/cline_sdlc/features/repository_tasks/application/dtos/commit_message.py`
- `tests/unit/features/repository_tasks/domain/test_conventional_commit.py`

**Acceptance criteria:**

- [ ] Empty messages are rejected.
- [ ] Messages without a Conventional Commit type are rejected.
- [ ] Malformed type/scope/description syntax is rejected.
- [ ] Types outside `build`, `chore`, `docs`, `feat`, `fix`, `refactor`, and `test` are rejected.
- [ ] `type: description`, `type(scope): description`, `type!: description`, and `type(scope)!: description` are accepted when valid.
- [ ] Scope values are limited to stable lowercase identifier characters such as letters, digits, dots, underscores, and hyphens.
- [ ] Multiline messages require a blank line after the subject before body/footer content.
- [ ] Standard footers, `BREAKING CHANGE:`, and `Cline-SDLC-*` trailers are accepted when otherwise safe.
- [ ] Unsafe control characters and message forms that cannot be passed safely to non-interactive Git commit execution are rejected.

**Verification:**

- [ ] Run focused unit tests for Conventional Commit validation.
- [ ] Include edge-case tests documenting all accepted and rejected forms from the specification.

### Checkpoint: Foundation

- [ ] Built-in recipe metadata is represented without repository-defined execution control.
- [ ] Conventional Commit validation is deterministic and independently tested.

### Phase 2: Typed Git Primitives for Staged Task Commits

## Task 3: Add staged repository inspection DTOs and port operations

**Description:** Extend repository coordination with typed read-only staged-change inspection suitable for standalone and embedded repository tasks. The inspection must verify Git repository presence, safe commit state, staged changes, staged paths, and staged diff/digest evidence without mutating repository state.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_coordination/application/dtos/task_repository.py`
- `src/cline_sdlc/features/repository_coordination/application/ports/git.py`
- `src/cline_sdlc/features/repository_coordination/application/use_cases/inspect_task_repository.py`
- `tests/unit/features/repository_coordination/application/test_inspect_task_repository.py`

**Acceptance criteria:**

- [ ] Inspection requires execution inside a Git repository.
- [ ] Inspection reports staged paths and staged diff summary or digest evidence.
- [ ] Inspection distinguishes no staged changes from unsafe repository state.
- [ ] Inspection does not stage, unstage, commit, reset, merge, rebase, clean, push, or otherwise mutate repository state.
- [ ] Embedded inspection can compare observed staged paths with authorized slice-owned paths.
- [ ] Blockers are structured with actionable codes, summaries, and safe evidence.

**Verification:**

- [ ] Run focused unit tests for the inspection use case with fake Git ports.
- [ ] Confirm repository task inspection does not reuse lifecycle preflight in a way that requires a clean working tree when standalone staged work is expected.

## Task 4: Add Git CLI staged inspection adapter and integration tests

**Description:** Implement the outbound Git CLI adapter operations needed by staged repository task inspection. Commands must be non-interactive, typed, and read-only, using `git --no-pager` and safe environment settings.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_coordination/adapters/outbound/git_cli.py`
- `tests/integration/features/repository_coordination/test_task_repository_inspection.py`

**Acceptance criteria:**

- [ ] Adapter detects repository root and HEAD.
- [ ] Adapter returns staged paths from the index only.
- [ ] Adapter returns staged diff summary or digest evidence without printing raw sensitive repository payloads by default.
- [ ] Adapter detects unsafe operation states that should block commit creation.
- [ ] Adapter does not alter the working tree or index.

**Verification:**

- [ ] Run integration tests against disposable Git repositories for no-repo, no-staged-changes, staged-only, staged-plus-unstaged, and unsafe-state scenarios.

## Task 5: Add typed Git mutation for authorized staged commit creation

**Description:** Add a repository-coordinate commit use case/port/adapter path for committing exactly already-staged authorized content with an independently validated message. This must be separate from the existing progress-plan slice committer, which writes and stages plan progress itself.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_coordination/application/dtos/task_commit.py`
- `src/cline_sdlc/features/repository_coordination/application/ports/task_commit.py`
- `src/cline_sdlc/features/repository_coordination/application/use_cases/commit_staged_task.py`
- `src/cline_sdlc/features/repository_coordination/adapters/outbound/git_task_commit.py`
- `tests/unit/features/repository_coordination/application/test_commit_staged_task.py`
- `tests/integration/features/repository_coordination/test_task_commit.py`

**Acceptance criteria:**

- [ ] Commit mutation requires validated repository inspection evidence, expected HEAD, expected staged paths, and a validated commit message.
- [ ] Commit creation uses non-interactive Git and must not open an editor.
- [ ] Commit creation must not pass hook-bypass flags such as `--no-verify`.
- [ ] Commit creation commits exactly the authorized staged paths and no unstaged/unrelated files.
- [ ] If HEAD, staged paths, or message evidence changed between inspection and mutation, the operation blocks before commit.
- [ ] On commit failure, recoverable state and blockers are reported without silently staging or unstaging unrelated paths.

**Verification:**

- [ ] Run unit tests with fake committer observations.
- [ ] Run integration tests in disposable Git repositories to verify exact committed paths, hook behavior preservation, and failure blocking.

### Checkpoint: Git Primitives

- [ ] Staged inspection is read-only and tested.
- [ ] Staged commit mutation is typed, non-interactive, hook-preserving, and tested.

### Phase 3: Recipe Execution and Skill Outcome Handling

## Task 6: Add recipe execution DTOs and structured evidence schema

**Description:** Define versioned application DTOs for recipe requests, recipe-specific skill proposal outcomes, commit-message validation results, approval decisions, recipe blockers, and completion evidence. The first implementation supports standalone mode only; embedded mode and hook-point context are deferred.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_tasks/application/dtos/execution.py`
- `src/cline_sdlc/features/repository_tasks/application/dtos/evidence.py`
- `tests/unit/features/repository_tasks/application/test_recipe_evidence.py`

**Acceptance criteria:**

- [ ] Evidence includes recipe id, standalone mode, status, staged paths, skill used, validation result, accepted commit message, commit hash when created, blocker details, and timestamp.
- [ ] Recipe skill proposal outcome is versioned and includes status, skill name, proposed commit message, rationale, validation claim, blockers/uncertainty, and staged-scope evidence.
- [ ] DTO constructors fail closed on empty ids, unsupported modes, unexpected hook-point values, missing required evidence, or unsafe commit-message fields.
- [ ] Sensitive raw payloads are not required fields for routine terminal evidence.

**Verification:**

- [ ] Run focused DTO/unit tests for evidence validation and serialization-friendly shapes.

## Task 7: Add bounded `conventional-commits` skill proposal adapter/use-case boundary

**Description:** Add a recipe-owned application boundary that requests a bounded Cline session using the `conventional-commits` skill and parses a structured versioned proposal outcome. The orchestrator must not rely on free-form prose alone.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_tasks/application/ports/commit_message_proposal.py`
- `src/cline_sdlc/features/repository_tasks/application/use_cases/propose_commit_message.py`
- `src/cline_sdlc/features/repository_tasks/adapters/outbound/cline_commit_message_proposal.py`
- `tests/unit/features/repository_tasks/application/test_propose_commit_message.py`
- `tests/contract/features/repository_tasks/test_commit_message_proposal.py`

**Acceptance criteria:**

- [ ] The generated prompt/command requires the `conventional-commits` skill.
- [ ] The request includes staged paths and staged-diff summary/digest scope evidence.
- [ ] The parsed response must be structured and versioned.
- [ ] Missing, malformed, blocked, failed, wrong-skill, or scope-mismatched proposal outcomes block before validation/mutation.
- [ ] Skill-reported validation is recorded as evidence but never treated as authoritative.

**Verification:**

- [ ] Run unit tests with fake proposal ports.
- [ ] Run contract tests using existing fake Cline patterns to verify structured proposal parsing.

## Task 8: Implement `conventional-commit-staged` application use case

**Description:** Compose built-in recipe policy, staged inspection, bounded skill proposal, deterministic commit-message validation, standalone accept/reject approval, staged commit mutation, and evidence recording into one fail-closed application use case. Manual message shortcuts, embedded execution, and interactive edit loops are deferred.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_tasks/application/use_cases/run_conventional_commit_staged.py`
- `src/cline_sdlc/features/repository_tasks/application/ports/approval.py`
- `src/cline_sdlc/features/repository_tasks/application/ports/evidence_recorder.py`
- `tests/unit/features/repository_tasks/application/test_run_conventional_commit_staged.py`

**Acceptance criteria:**

- [ ] Standalone mode requires staged changes and explicit approval before commit mutation.
- [ ] Standalone mode uses the bounded `conventional-commits` skill proposal path for MVP; manual-message shortcuts are deferred.
- [ ] Embedded mode is not wired in the standalone-first MVP.
- [ ] Interactive edit support is deferred; only accept or reject can follow a proposal.
- [ ] Malformed or unacceptable commit messages block before mutation even if the skill claims success.
- [ ] All blockers and completions return structured recipe evidence.

**Verification:**

- [ ] Run focused application unit tests for success, rejection, malformed message, no staged changes, scope mismatch, proposal blocked, and mutation failure cases.

### Checkpoint: Recipe Execution

- [ ] Recipe use case can complete with fakes without real Git or real Cline.
- [ ] Recipe use case blocks safely before mutation for all unclear authority, scope, approval, and validation conditions.

### Phase 4: Standalone CLI Entry Point

## Task 9: Introduce standalone task command parser

**Description:** Extend the inbound CLI adapter to support the canonical standalone task command `cline-sdlc task conventional-commit-staged`, while preserving existing flag-driven lifecycle invocations unchanged. Full explicit lifecycle subcommands (`idea`, `spec`, `plan`, and `implement`) are deferred.

**Likely files/components touched:**

- `src/cline_sdlc/features/lifecycle_orchestration/adapters/inbound/cli.py`
- `src/cline_sdlc/features/lifecycle_orchestration/application/dtos/invocation.py`
- `tests/unit/features/lifecycle_orchestration/adapters/inbound/test_cli.py`
- `tests/unit/bootstrap/test_cli.py`

**Acceptance criteria:**

- [ ] `cline-sdlc task conventional-commit-staged` parses as the canonical standalone repository task invocation.
- [ ] Existing `--idea`, `--idea-file`, `--spec-file`, and `--plan-file` paths continue unchanged.
- [ ] Explicit lifecycle commands `idea`, `spec`, `plan`, and `implement` remain deferred and are not required for the standalone task MVP.
- [ ] Invalid mixtures of task and lifecycle stage inputs are rejected with clear terminal blockers or parse errors.
- [ ] Shared options such as `--timeout`, `--cline-command`, `--json`, `--verbose`, and `--dry-run` remain unambiguous.

**Verification:**

- [ ] Run focused CLI parser tests and bootstrap CLI tests.

## Task 10: Wire standalone task runtime and approval adapter

**Description:** Wire `cline-sdlc task conventional-commit-staged` through the composition root/inbound adapter to repository task use cases, Git adapters, Cline proposal adapter, approval prompt adapter, evidence recording, and terminal result rendering.

**Likely files/components touched:**

- `src/cline_sdlc/features/repository_tasks/adapters/inbound/cli.py`
- `src/cline_sdlc/features/repository_tasks/adapters/inbound/terminal_approval.py`
- `src/cline_sdlc/features/lifecycle_orchestration/adapters/inbound/cli.py`
- `src/cline_sdlc/features/lifecycle_orchestration/application/dtos/terminal_result.py`
- `tests/unit/features/repository_tasks/adapters/inbound/test_cli.py`
- `tests/contract/features/repository_tasks/test_standalone_task.py`

**Acceptance criteria:**

- [ ] Standalone terminal output shows proposed commit message, staged path summary, and exact proposed mutation before approval.
- [ ] Approval options support accept and reject for MVP; interactive edit support is deferred.
- [ ] Reject blocks without mutation.
- [ ] No interactive edit path creates a commit in the MVP.
- [ ] Completion terminal result includes recipe evidence and commit hash.
- [ ] Blocked/failed terminal results map to existing exit categories where practical.
- [ ] Dry-run, if currently supported at the CLI layer, does not create commits.

**Verification:**

- [ ] Run contract tests for standalone task success, rejection, invalid edit, and no staged changes using fakes.

### Checkpoint: Standalone Task

- [ ] `cline-sdlc task conventional-commit-staged` is wired end-to-end in tests.
- [ ] Standalone state-changing behavior is always gated by explicit approval.

### Phase 5: Documentation, Safety Coverage, and End-to-End Validation

## Task 11: Update user-facing documentation and CLI examples

**Description:** Document the canonical task command, explicit command grammar, approval behavior, no repository-local configuration for MVP, Conventional Commit validation rules, and safety limitations.

**Likely files/components touched:**

- `README.md`
- `docs/specs/cline-sdlc-orchestrator-spec.md` if the normative orchestrator contract must mention the new task/hook behavior
- Optional ADR only if implementation decisions materially alter architecture beyond the accepted specification

**Acceptance criteria:**

- [ ] README documents `cline-sdlc task conventional-commit-staged`.
- [ ] README explains standalone approval and already-staged-only behavior.
- [ ] README states that embedded `before_slice_commit` behavior is deferred and not supported in the standalone-first MVP.
- [ ] README states that repository-local task configuration is deferred/not supported in MVP.
- [ ] README or linked docs list the validation commands below as the local quality gate for this feature:
  - `uv run ruff format --check .`
  - `uv run ruff check .`
  - `uv run mypy .`
  - `uv run pytest`
  - `uv build`
- [ ] Documentation does not claim unattended readiness beyond the accepted supervised boundary.

**Verification:**

- [ ] Review docs for consistency with the accepted specification and actual CLI behavior.

## Task 12: Add safety, contract, and e2e regression coverage

**Description:** Add cross-slice tests that prove the recipe model cannot be used as arbitrary workflow execution, validates messages independently, gates standalone mutation on explicit approval, preserves Git hooks, and commits exactly authorized staged content.

**Likely files/components touched:**

- `tests/contract/features/repository_tasks/test_recipe_policy.py`
- `tests/contract/features/repository_tasks/test_standalone_task.py`
- `tests/e2e/test_repository_task_conventional_commit_staged.py`

**Acceptance criteria:**

- [ ] Unknown recipe, hook, primitive category, or configuration-like workflow field fails closed.
- [ ] Skill success with malformed commit message blocks before mutation.
- [ ] Standalone task cannot commit without explicit approval.
- [ ] Standalone task commits only already staged content and never stages unrelated files.
- [ ] Embedded hook coverage is deferred until embedded mode is reactivated.
- [ ] Git hooks are not bypassed during commit creation.
- [ ] Terminal results and run summaries contain structured safe evidence.

**Verification:**

- [ ] Run new contract and e2e tests.
- [ ] Confirm tests use fake Cline executables and disposable Git repositories; no live external services are required.

## Task 13: Run full local quality gate and package build

**Description:** Execute final validation from the repository root using the authoritative commands required by the accepted specification and this plan.

**Acceptance criteria:**

- [ ] Formatting check passes.
- [ ] Ruff lint passes.
- [ ] Mypy strict type checking passes.
- [ ] Pytest suite passes.
- [ ] Package build passes.

**Verification commands:**

- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy .`
- [ ] `uv run pytest`
- [ ] `uv build`

### Checkpoint: Complete

- [ ] All task acceptance criteria are met or explicitly blocked.
- [ ] Standalone repository task success and blocker paths are covered.
- [ ] Embedded hook success and blocker paths are documented as deferred follow-up scope.
- [ ] Documentation matches implemented behavior.
- [ ] Full authoritative validation commands pass.
- [ ] Plan is ready for independent review.

## Dependencies and Sequencing Constraints

- Task 1 must precede all recipe execution work because recipe ids, hook names, and primitive categories are shared policy.
- Task 2 must precede any commit mutation because validation is authoritative and independent of skill output.
- Tasks 3 and 4 must precede recipe execution against real Git state.
- Task 5 must precede successful standalone commit creation.
- Tasks 6 and 7 must precede Task 8 because the recipe use case needs evidence and proposal contracts.
- Task 8 must precede CLI wiring.
- Tasks 9 and 10 can proceed after Task 8.
- Task 11 documentation should be finalized after behavior stabilizes but updated before the final quality gate.
- Task 12 safety coverage should be drafted once Tasks 1, 2, 6, and 8 define stable contracts, then completed after standalone CLI wiring.
- Task 13 full quality gate must run after all implementation, tests, and docs changes.

## Parallelization Opportunities

- Task 2 can be implemented in parallel with Task 1 once recipe ids/types are agreed.
- Task 4 can be implemented in parallel with Task 5 after Task 3 DTOs/ports are drafted.
- Task 9 CLI parser work can be developed in parallel with Task 7 proposal parsing if both consume stable recipe invocation DTOs.
- Task 11 documentation can be drafted in parallel after Task 9 establishes the parser shape, but final docs must wait for actual behavior.
- Task 12 broader safety tests can be drafted against fakes once Tasks 1, 2, 6, and 8 define stable contracts.

## Deferred Follow-up Scope

The following accepted-specification capabilities remain intentionally out of the standalone-first implementation slice. Reactivate them only through a later plan revision after the standalone task is proven:

- Embedded `before_slice_commit` hook definition and wiring in lifecycle orchestration.
- Embedded recipe execution inside `ImplementPlan` and reconciliation with the existing `CommitSlice` transaction.
- Plan-state or run-summary `recipe_evidence` for embedded hook execution, including any `PlanState` schema migration.
- Full explicit lifecycle subcommands (`idea`, `spec`, `plan`, and `implement`).
- Standalone interactive edit loops and manual-message shortcuts.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Existing slice commit flow writes/stages plan progress, while the new recipe commits already staged content. | High | Defer embedded integration. The standalone-first MVP uses a separate staged task commit boundary only for direct task invocation; revisit slice commit ownership before reactivating embedded mode. |
| Current terminal outcome schema is lifecycle-stage oriented and may not parse recipe proposal outcomes cleanly. | Medium | Add recipe-specific structured proposal DTOs and adapter parsing rather than relying on free-form prose or overloading stage roles. |
| CLI migration to explicit subcommands could accidentally break existing flag-driven workflows. | High | Add only `cline-sdlc task conventional-commit-staged` and preserve existing flag-driven lifecycle workflows unchanged. |
| Standalone staged work conflicts with existing lifecycle preflight assumptions about clean working trees. | Medium | Add task-specific repository inspection that permits staged changes while still blocking unsafe Git states. |
| Git commit invocation could accidentally bypass hooks or open an editor. | High | Use explicit non-interactive environment and message-file or `-m` strategy without `--no-verify`; integration-test hook behavior. |
| Evidence may expose raw diffs or sensitive repository content. | Medium | Store staged path summaries and digests by default; redact or omit raw payloads from terminal/run-summary evidence. |
| Repository configuration scope creep could turn recipes into workflow definitions. | High | Defer repository-local configuration entirely for MVP and enforce built-in registry behavior only. |

## Assumptions

- Python 3.14, `uv`, `ruff`, `mypy`, and `pytest` remain the project toolchain.
- No new runtime dependency is required for the MVP.
- Fake Cline executables and disposable Git repositories remain acceptable for default automated tests.
- The existing supervised-readiness warning remains in force; this feature must not claim full unattended readiness.
- Repository-local configuration is deferred and should not be introduced unless a later accepted specification supersedes this plan.

## Open Questions

- Resolved: embedded mode is deferred; implement the standalone task first.
- Resolved: add only `cline-sdlc task conventional-commit-staged`; preserve existing lifecycle flags unchanged.
- Resolved: parse `conventional-commits` skill output with a recipe-specific DTO/parser owned by `repository_tasks`; do not extend lifecycle `SessionOutcome` in this first pass.
- Resolved: standalone approval supports accept/reject only for MVP; interactive edit support is deferred.
- Resolved: plan-state `recipe_evidence` is deferred with embedded mode; do not change `artifact_lifecycle/domain/plan_state.py` for the standalone-first MVP.
