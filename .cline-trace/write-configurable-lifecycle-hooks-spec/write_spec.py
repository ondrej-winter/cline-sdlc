from pathlib import Path

spec_path = Path('/Users/owinter/Documents/Projects/ondrej-winter.nosync/cline-sdlc/docs/specs/configurable-lifecycle-hooks-and-repository-task-spec.md')
spec_path.parent.mkdir(parents=True, exist_ok=True)
spec_path.write_text("""# Spec: Configurable Lifecycle Hooks and Repository Task Recipes

## Status

- Artifact type: product and behavior specification
- Date: 2026-07-27
- Source brief: `docs/ideas/configurable-lifecycle-hooks-and-repository-task-recipes-idea.md`
- Decision state: accepted specification
- Lifecycle stage: specification creation
- Intended scope: built-in repository task recipes with safe lifecycle-hook reuse

## Objective

Add an orchestrator-owned repository task recipe model that lets maintainers run
bounded SDLC helper procedures either directly on demand or at safe, predefined
lifecycle hook points.

The first supported recipe is `conventional-commit-staged`. It must inspect the
currently staged repository changes, use the `conventional-commits` skill to
produce or check a proposed Conventional Commit message, independently validate
that message, and create a non-interactive Git commit of exactly the authorized
staged content.

The feature is for engineers using `cline-sdlc` who want reusable, evidence-rich
repository tasks after ordinary human work and during automated implementation
slices without turning repository configuration into arbitrary executable
workflow control.

## Current context

The orchestrator already treats lifecycle stages as major approval-relevant
artifact transitions, such as idea refinement, specification creation, plan
creation and review, and plan implementation. Those stage boundaries remain the
primary safety model: one major stage per invocation, explicit artifact outputs,
structured terminal results, and fail-closed behavior when decisions or approval
boundaries are unclear.

Plan implementation already has a bounded slice-commit concept. The new recipe
model must fit into that existing authorization boundary rather than replace it.
A recipe may help prepare evidence, propose messages, validate policy, and
perform typed state-changing operations, but it must not allow repository content
to define arbitrary shell commands, imports, prompts, or executable workflows.

The accepted idea brief intentionally separates three concepts:

- **Lifecycle stages**: major artifact-boundary transformations.
- **Lifecycle hooks**: orchestrator-owned extension points inside stages.
- **Repository task recipes**: bounded reusable procedures composed from trusted
  primitives and usable either standalone or at allowed hooks.

## Assumptions

1. The primary user is a repository maintainer or engineer running `cline-sdlc`
   from a local Git working tree.
2. The initial valuable workflow is committing already staged local changes with
   a valid Conventional Commit message.
3. Existing lifecycle-stage safety rules, artifact boundaries, Git
   reconciliation behavior, command execution safety, and fail-closed defaults
   remain in force.
4. Embedded recipe execution is safe only when it occurs inside an already
   authorized plan-implementation slice commit boundary.
5. Skills may provide reasoning, review, findings, and structured proposals, but
   the Python orchestrator remains authoritative for validation and mutation.
6. Repository-local configuration may eventually enable or parameterize known
   recipes and hook placements, but the MVP can start with built-in behavior
   before exposing a durable configuration file.

## Vocabulary

- **Repository task recipe**: A named, orchestrator-owned, bounded procedure
  composed from trusted primitives. A recipe can run directly as a task or be
  attached to an allowed lifecycle hook.
- **Standalone recipe mode**: A direct user invocation of a recipe outside a
  broader lifecycle stage. State-changing operations require explicit user
  acceptance.
- **Embedded recipe mode**: Invocation of a recipe from an orchestrator-owned
  lifecycle hook inside an already authorized stage. State-changing operations
  may proceed unattended only when the enclosing stage policy authorizes them.
- **Lifecycle hook**: A named extension point owned by the orchestrator. Hooks
  identify safe moments when a recipe may run without giving configuration
  free-form control flow.
- **Trusted primitive**: An orchestrator-approved operation type, such as an
  installed Agent Skill session, typed Git operation, validation operation,
  artifact operation, or evidence collection operation.
- **Typed operation**: A Python orchestrator operation with explicit inputs,
  policy checks, and structured results. State-changing typed operations are the
  only way recipes may mutate repository state.
- **Completion evidence**: Structured data proving whether a recipe completed or
  blocked, including recipe id, mode, hook point, skill use, paths, validation
  results, commit hash, and blocker details where applicable.

## Desired behavior

### Recipe registry

The orchestrator must own a registry of known recipe definitions. Each recipe
definition must declare:

- a stable recipe identifier;
- the recipe kind;
- allowed invocation modes;
- required preconditions;
- ordered trusted primitives;
- state-changing operations, if any;
- approval requirements by mode;
- completion evidence requirements.

Unknown recipe identifiers must fail closed. Unknown operation names, hook names,
fields, schema versions, enum values, or unsupported configuration values must
also fail closed.

### Invocation modes

A recipe must be runnable in two conceptual modes:

1. **Standalone task mode** for direct user-invoked repository tasks.
2. **Embedded lifecycle-hook mode** for reuse at orchestrator-owned hook points.

Standalone mode must not infer approval from prose, a successful skill response,
or the mere existence of staged changes. Any state-changing operation, including
creating a commit, requires explicit user acceptance after the proposed action is
shown.

Embedded mode may proceed without a new prompt only when all of the following are
true:

- the enclosing lifecycle stage has already authorized the specific boundary;
- the hook point is allowed for the recipe;
- the relevant artifact, plan, or slice material remains reconciled;
- path ownership checks pass;
- validation evidence required by the enclosing stage passes;
- recipe-specific validation passes;
- the operation stays inside the already authorized slice or artifact boundary.

### Lifecycle hooks

Lifecycle hooks must be named extension points defined by the orchestrator.
Configuration may eventually select allowed hook placements, but it must not
create new hook semantics or arbitrary control flow.

The MVP embedded hook is `before_slice_commit` for plan implementation. The hook
runs after slice work and validation have produced acceptable evidence and before
the orchestrator creates the local slice commit.

The broader model may reserve or later expose additional hook names, such as:

- `after_artifact_written`;
- `after_stage_review`;
- `after_slice_validation`;
- `before_finalization_commit`.

Those additional hooks are not required for the MVP unless an implementation plan
later justifies them.

### Built-in recipe: `conventional-commit-staged`

The MVP must include a built-in `conventional-commit-staged` recipe.

Its behavior is:

1. Require execution inside a Git repository.
2. Require staged changes, or in embedded mode require the orchestrator's
   reconciled slice-owned staged content.
3. Inspect only the staged diff or the orchestrator-authorized staged paths.
4. Start a bounded Cline session that must use the `conventional-commits` skill
   to propose or verify a commit message.
5. Capture a structured commit-message proposal outcome.
6. Independently validate the message against Conventional Commit rules.
7. In standalone mode, ask the user to accept, reject, or edit the proposed
   message before committing.
8. In embedded mode, proceed unattended only when the enclosing slice commit is
   already authorized and all recipe and slice checks pass.
9. Create a non-interactive Git commit for exactly the staged content.
10. Report structured completion evidence or a structured blocker.

The recipe must not:

- stage arbitrary files;
- broaden the current implementation slice;
- include unstaged or unrelated files in the commit;
- rewrite history;
- bypass Git hooks;
- open an interactive editor;
- push, publish, release, or deploy;
- treat skill output as sufficient authority to mutate state.

### Conventional Commit validation

The orchestrator must independently validate any proposed commit message before
running `git commit`. Validation must be separate from the `conventional-commits`
skill response.

Validation must reject at least:

- an empty message;
- a message without a Conventional Commit type;
- malformed type/scope/description syntax;
- disallowed or unsupported type values, if the project defines an allowlist;
- messages that cannot be passed safely to non-interactive Git commit execution.

The exact type allowlist and multiline body/footer rules may be selected during
implementation, but the selected rules must be documented and covered by tests.

### Git behavior

Git operations must be typed orchestrator operations. The recipe must use
non-interactive Git commands and must disable editor-based commit flows.

Before committing, the orchestrator must verify:

- the current directory is inside a Git repository;
- the repository is in a safe state for commit creation;
- there are staged changes eligible for the selected mode;
- embedded mode paths are reconciled with the authorized slice;
- no unstaged or unrelated paths are silently included;
- commit-message validation passed.

Commit creation must preserve normal Git hook behavior. The recipe must not pass
flags whose purpose is to bypass local hooks.

### Configuration authority model

Repository-local configuration, when introduced, may only select from known
orchestrator-owned capabilities. It may enable, disable, or parameterize built-in
recipes and allowed hook placements.

Configuration must not define:

- shell commands;
- arbitrary script paths;
- remote URLs to execute or load;
- Python import paths;
- arbitrary model-selected tools;
- broad or raw Git command strings;
- unrestricted prompt text;
- custom executable workflows;
- lifecycle-stage topology changes.

Configuration parsing must fail closed on unknown schema versions, recipe ids,
hook names, operation names, fields, or enum values.

The MVP does not require repository configuration if the built-in standalone task
and embedded `before_slice_commit` behavior can be delivered safely without it.
If configuration is included in the MVP, it must be minimal and limited to
known-recipe enablement and allowed hook placement.

## Interfaces

### Standalone repository task entry point

The CLI must expose a repository task entry point for the built-in recipe. The
accepted idea brief leaves the exact shape unresolved. Candidate shapes include:

```text
cline-sdlc task conventional-commit-staged
cline-sdlc --task conventional-commit-staged
```

The implementation must choose and document one canonical invocation form. It may
support aliases only if they do not make lifecycle-stage inputs ambiguous.

Standalone task invocation must be mutually understandable with existing CLI
stage invocations. It must reject invalid combinations such as asking for a major
lifecycle stage and a standalone repository task in the same invocation unless a
future specification explicitly permits that composition.

### Embedded lifecycle hook interface

Plan implementation must be able to invoke `conventional-commit-staged` at the
`before_slice_commit` hook. The hook interface must provide enough structured
context to enforce policy, including:

- recipe id;
- invocation mode;
- hook point;
- repository root;
- staged paths or reconciled slice-owned paths;
- slice identifier or plan section identifier when embedded;
- relevant material digests or reconciliation evidence;
- validation evidence from the enclosing slice;
- timeout and Cline command settings inherited from the parent invocation.

The embedded recipe result must flow back into the plan-implementation run
summary and terminal result evidence.

### Skill interaction

The `conventional-commit-staged` recipe must invoke a bounded Cline session that
uses the `conventional-commits` skill. The recipe-oriented skill session must
return a structured outcome containing at least:

- proposed commit message;
- rationale or summary suitable for human review;
- whether the skill considered the message valid;
- any blockers or uncertainty;
- references to the staged diff scope used to generate the message.

The orchestrator must not rely on free-form prose alone to decide that the skill
completed successfully.

## Terminal result and evidence

Recipe invocations must produce structured results that can be consumed by
humans, tests, and run summaries.

At minimum, recipe evidence should include:

- `recipe_id`;
- `mode`;
- `hook_point`, when embedded;
- `status`;
- `staged_paths` or authorized path summary;
- `skill_used`;
- commit-message validation result;
- accepted commit message when a commit is created;
- `commit_hash` when a commit is created;
- blocker reason when blocked;
- path to any recipe run log or summary artifact when available.

Existing process exit code categories should be reused where practical. A blocked
recipe should map to the orchestrator's blocked category; failed preconditions
should map to preflight failure; unexpected invariant violations should map to
internal error.

## Constraints and safety requirements

- The orchestrator owns recipe definitions, allowed hooks, typed operations,
  permission policy, and completion checks.
- Repository content and configuration must not become a workflow engine.
- State-changing operations must be implemented by Python orchestrator code, not
  by raw skill instructions or repository-defined commands.
- The feature must fail closed when scope, approval, configuration, staged paths,
  Git state, or validation evidence is unclear.
- Standalone commit creation requires explicit user acceptance.
- Embedded commit creation is allowed only inside already authorized slice commit
  boundaries.
- Remote publication and deployment are out of scope.
- Dynamic dependency installation is out of scope.
- Secrets, credentials, raw sensitive prompts, and private data must not be
  printed or persisted in routine recipe evidence.
- Command execution must remain non-interactive and must not open editors or
  prompts during commit creation.

## MVP scope

In scope for the MVP:

- a repository task entry point for `conventional-commit-staged`;
- an orchestrator-owned built-in recipe definition;
- Git preflight requiring a repository and staged or reconciled slice-owned
  changes;
- staged-diff inspection that avoids unstaged and unrelated files;
- a bounded Cline session that must use the `conventional-commits` skill;
- structured commit-message proposal capture;
- independent Conventional Commit validation;
- explicit user acceptance or editing in standalone mode;
- unattended embedded execution at `before_slice_commit` only when slice commit
  authorization and reconciliation checks pass;
- non-interactive Git commit creation of exactly the authorized staged content;
- structured terminal result and run-summary evidence for completion or blocking;
- focused tests for recipe policy, validation, Git preflight, and result
  evidence.

Out of scope for the MVP:

- repository-defined custom recipe steps;
- arbitrary lifecycle-stage topology changes;
- arbitrary prompt strings in configuration;
- repository-defined shell commands or scripts;
- dynamic dependency installation;
- plugin marketplace behavior;
- automatic staging of unrelated changes;
- optional staging of a user-confirmed path list unless explicitly added later;
- remote publication, pushes, pull requests, releases, or deployment;
- additional hook points beyond `before_slice_commit` unless needed to complete
  the MVP safely.

## Not doing and why

- **Repository-defined executable workflows**: They would turn lifecycle
  configuration into code execution and conflict with the orchestrator's
  fail-closed safety model.
- **Arbitrary shell or Git commands from YAML**: State-changing operations need
  typed inputs, permission checks, and independent evidence.
- **Raw unrestricted prompt strings as recipe definitions**: Repository prompt
  text can become a policy-bypass and prompt-injection surface before the
  primitive model is proven.
- **Full configurable lifecycle topology**: The immediate value is reusable task
  recipes and hook placement, not replacing stage selection.
- **Skill output as mutation authority**: Skills may recommend, review, or
  generate structured output, but the orchestrator must validate and execute
  state-changing operations.
- **Auto-approval for standalone commits**: Outside a broader approved
  implementation invocation, committing staged work requires explicit user
  acceptance.
- **Push or publish after commit creation**: Local commit creation is useful and
  bounded; remote side effects introduce different approval and security
  boundaries.

## Success criteria

- A user can run the built-in `conventional-commit-staged` repository task in
  standalone mode against already staged changes.
- Standalone mode shows the proposed commit message and requires explicit user
  acceptance or editing before creating a commit.
- Plan implementation can invoke the same recipe at `before_slice_commit` without
  weakening existing slice authorization, reconciliation, validation, and path
  ownership checks.
- The recipe commits exactly the authorized staged content and does not stage
  unrelated files.
- Commit creation is non-interactive, does not open an editor, and does not
  bypass Git hooks.
- A malformed or unacceptable commit message blocks before mutation, even if a
  skill proposed it.
- Unknown recipe ids, hook names, operation names, schema versions, fields, or
  enum values fail closed.
- Recipe completion or blocking is visible in terminal results and run summaries
  with structured evidence.
- Tests cover standalone blocking and success paths, embedded policy checks,
  Conventional Commit validation, Git preflight behavior, and evidence reporting.

## Validation expectations

Implementation should be verified with:

- unit tests for recipe registry lookup and fail-closed behavior;
- unit tests for Conventional Commit message validation;
- unit tests for standalone approval policy;
- unit tests for embedded `before_slice_commit` authorization policy;
- Git-adapter or integration tests using temporary repositories for staged-diff
  inspection and non-interactive commit creation;
- contract or integration coverage showing plan implementation records embedded
  recipe evidence in slice summaries;
- the project quality gate configured for `ruff`, `mypy`, and `pytest`.

## Open questions

These questions remain non-blocking for the accepted specification but must be
resolved before or during implementation planning:

1. What exact standalone CLI shape should be canonical:
   `cline-sdlc task conventional-commit-staged`,
   `cline-sdlc --task conventional-commit-staged`, or another subcommand shape?
2. Should standalone recipe mode operate only on already staged changes for the
   MVP, or should a later version optionally stage a user-confirmed path list?
3. What exact structured outcome schema should recipe-oriented Cline skill
   sessions return?
4. Should `conventional-commit-staged` always require a real Cline skill session,
   or may it fall back to deterministic validation when a user provides a message
   manually?
5. Should repository configuration be deferred until after the built-in recipe
   works, or should the MVP include a minimal enable/disable hook-placement file?
6. Which Conventional Commit type values and multiline body/footer rules should
   the validator enforce by default?
7. How should embedded recipe evidence be represented in the existing
   plan-implementation progress artifacts if current schemas are too narrow?
""", encoding='utf-8')
print(spec_path)
