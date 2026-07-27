# Configurable Lifecycle Hooks and Repository Task Recipes

## Problem Statement

How might we let repository maintainers run reusable SDLC helper recipes on demand and at safe lifecycle hook points without turning lifecycle configuration into an unsafe workflow engine or repository-controlled code execution surface?

## Recommended Direction

Add an orchestrator-owned recipe model for bounded repository tasks that can run in two modes: standalone task mode and embedded lifecycle-hook mode. A recipe is a named, reusable procedure composed from trusted primitives such as installed Agent Skills, typed Git operations, validation operations, artifact operations, and completion evidence rules. Recipes should be usable after ordinary human work, such as proofreading and staging an idea artifact, and also from inside orchestrated plan implementation slices, such as before each slice commit.

The motivating recipe is `conventional-commit-staged`: inspect the currently staged changes, use the `conventional-commits` skill to propose or verify a commit message, validate the message, and create a non-interactive commit of exactly the staged content. The same recipe should be runnable directly by a user and reusable by the plan-implementation stage before each automated slice commit.

The key hardening decision is to separate three concepts: lifecycle stages, lifecycle hooks, and recipes. Lifecycle stages remain major artifact-boundary transformations such as idea refinement, specification creation, plan creation and review, and plan implementation. Lifecycle hooks are orchestrator-owned extension points inside those stages, such as `before_slice_commit`. Recipes are bounded capabilities that may run at those hook points or as standalone tasks. Configuration may enable, disable, or parameterize known recipes and hook placements; it must not define arbitrary shell commands, Python imports, unrestricted prompts, or custom executable workflows.

## Concept Model

### Lifecycle stages

Lifecycle stages are still major, approval-relevant artifact transitions. They preserve the existing orchestrator safety model: one major stage per invocation, explicit artifact boundaries, structured outcomes, and fail-closed behavior when material decisions or approval boundaries are unclear.

Examples:

- rough idea to accepted idea brief;
- idea brief to accepted specification;
- specification to reviewed implementation plan;
- ready implementation plan to completed implementation.

### Lifecycle hooks

Lifecycle hooks are named extension points owned by the orchestrator. They identify safe moments when a recipe may run without giving configuration free-form control flow.

Examples:

- `after_artifact_written`;
- `after_stage_review`;
- `after_slice_validation`;
- `before_slice_commit`;
- `before_finalization_commit`.

### Repository task recipes

Recipes are reusable bounded procedures. They can be invoked directly by a user or attached to allowed lifecycle hooks. A recipe may use skills for reasoning, review, message generation, proofreading, or findings, but state-changing operations must be implemented by the Python orchestrator through typed, policy-checked operations.

Examples:

- `conventional-commit-staged`;
- `proofread-artifact`;
- `review-staged-diff`;
- `run-local-quality-gate`;
- `summarize-changes`.

## Example Recipe: Conventional Commit Staged Changes

The first recipe should prove the model against a valuable real workflow: after proofreading an artifact or after completing an implementation slice, commit the staged changes with a valid Conventional Commit message.

Illustrative built-in recipe contract:

```yaml
id: conventional-commit-staged
kind: repository_task
inputs:
  requires_git_repo: true
  requires_staged_changes: true
interaction:
  standalone: interactive
  embedded: unattended_with_policy
steps:
  - id: inspect_staged_diff
    operation: orchestrator.git.diff_staged
  - id: propose_message
    skill: conventional-commits
    output: commit_message
  - id: validate_message
    operation: orchestrator.commit_message.validate_conventional
  - id: commit
    operation: orchestrator.git.commit_staged
    approval:
      standalone: user_acceptance_required
      embedded: allowed_when_slice_commit_authorized
completion:
  evidence:
    - commit_hash
    - commit_message
    - staged_paths
```

In standalone mode, the recipe should require user acceptance or editing of the proposed commit message before committing. In embedded slice mode, the current plan-implementation invocation already authorizes the orchestrator's bounded slice commit, so the recipe may proceed without a new prompt only when slice reconciliation, validation evidence, path ownership, and commit-message validation all pass.

The recipe must commit exactly the staged content or the reconciled slice-owned paths selected by the orchestrator. It must not stage arbitrary files, broaden the slice, rewrite history, bypass hooks, open an interactive editor, or infer approval from prose.

## Configuration Authority Model

Configuration should select from known primitives rather than define new executable behavior. Repository-local configuration may eventually enable or parameterize built-in recipes, but the orchestrator owns the recipe registry, allowed hook points, operation implementations, permission policy, and completion checks.

Illustrative future configuration:

```yaml
schema_version: 1
recipes:
  conventional-commit-staged:
    enabled: true
    hooks:
      - before_slice_commit
    mode: require_conventional_commit
```

Unknown recipe identifiers, hook names, operation names, schema versions, fields, or enum values should fail closed. Configuration must not contain shell commands, arbitrary script paths, remote URLs, Python import paths, model-selected tools, broad Git operations, or unrestricted prompt text.

## Key Assumptions to Validate

- [ ] Standalone repository task mode is useful after human-driven work such as proofreading an idea or specification artifact. Test by manually staging an artifact change, running a prototype `conventional-commit-staged` flow, and checking whether the interaction feels safer than writing the commit manually.
- [ ] The same recipe can be embedded before each implementation slice commit without weakening slice authorization. Test by mapping the existing plan-implementation commit flow to a `before_slice_commit` hook and verifying that staged paths, validation evidence, and material digest checks remain authoritative.
- [ ] Skills are useful recipe steps when they produce structured recommendations or findings, not when they execute operations. Test with the `conventional-commits` skill returning a structured commit-message proposal that the orchestrator validates independently.
- [ ] A small built-in recipe registry is enough before supporting repository-defined recipe YAML. Test with two or three built-in recipes and see whether configuration pressure is mostly enablement and hook placement rather than custom control flow.
- [ ] Users can understand why a recipe completed or blocked from structured evidence. Test terminal results and run summaries that include recipe id, mode, hook point, skill used, changed paths, validation results, commit hash, and blocker when applicable.

## MVP Scope

The MVP is a built-in `conventional-commit-staged` recipe with standalone task mode and an embedded `before_slice_commit` use inside plan implementation.

In scope:

- a repository task entry point for the built-in recipe;
- Git preflight requiring a repository and staged or reconciled slice-owned changes;
- staged-diff inspection that avoids unstaged or unrelated files;
- a bounded Cline session that must use the `conventional-commits` skill;
- a structured commit-message proposal outcome;
- independent Conventional Commit message validation;
- interactive user acceptance in standalone mode;
- unattended execution in embedded mode only within already authorized slice-commit boundaries;
- non-interactive Git commit creation without opening an editor or bypassing hooks;
- terminal result and run-summary evidence for recipe completion or blocking.

Out of scope for the MVP:

- repository-defined custom recipe steps;
- arbitrary lifecycle-stage topology changes;
- arbitrary prompt strings in configuration;
- repository-defined shell commands or scripts;
- dynamic dependency installation;
- plugin marketplace behavior;
- automatic staging of unrelated changes;
- remote publication, pushes, pull requests, releases, or deployment.

## Not Doing and Why

- Repository-defined executable workflows — this would turn lifecycle configuration into code execution and conflict with the orchestrator's fail-closed safety model.
- Arbitrary shell or Git commands from YAML — state-changing operations need typed inputs, permission checks, and independent evidence.
- Raw unrestricted prompt strings as recipe definitions — repository prompt text can become a policy-bypass and prompt-injection surface before the primitive model is proven.
- Full configurable lifecycle topology in the first implementation — the immediate user value is reusable task recipes and hook placement, especially commits, not replacing the whole stage-selection model.
- Treating skill output as authority to mutate state — skills may recommend, review, or generate structured outputs, but the orchestrator must validate and execute state-changing operations.
- Auto-approval for standalone commits — outside a broader approved implementation invocation, committing staged work should require explicit user acceptance.
- Pushing or publishing after commit creation — local commit creation is useful and bounded; remote side effects introduce a different approval and security boundary.

## Open Questions

- What should the standalone CLI shape be: `cline-sdlc task conventional-commit-staged`, `cline-sdlc --task conventional-commit-staged`, or a dedicated subcommand group?
- Should standalone recipe mode operate only on already staged changes, or should it optionally stage a user-confirmed path list?
- What structured outcome schema should recipe-oriented skill sessions return, especially for commit-message proposals?
- Should the `conventional-commit-staged` recipe always require a real Cline skill session, or can it fall back to deterministic validation when a user provides a message manually?
- Which lifecycle hooks are safe enough to expose first besides `before_slice_commit`?
- Should repository configuration be introduced only after the built-in recipe works, or should the MVP include a minimal enable/disable file for hook placement?
- How should embedded recipe evidence be represented in the existing implementation plan progress and run summaries?
