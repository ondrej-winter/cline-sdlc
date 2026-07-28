# Spec: Configurable Lifecycle Hooks and Repository Task Recipes

## Status

- Artifact type: product and behavior specification
- Date: 2026-07-27
- Source brief: `docs/ideas/configurable-lifecycle-hooks-and-repository-task-recipes-idea.md`
- Decision state: accepted specification, hardened by interview on 2026-07-27
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
7. Recipes are static linear orchestrator-owned contracts, not configurable
   workflows. Branching, loops, dynamic step selection, and repository-defined
   control flow are intentionally out of scope.
8. Every new recipe and every new primitive category requires its own accepted
   specification before implementation, even if the recipe appears read-only or
   uses already-approved primitive categories.

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

### Recipe contract and composition model

A recipe must be a static, linear, orchestrator-owned contract. Its step sequence
must be declared in orchestrator-controlled code or data bundled with the
orchestrator, not in repository-local configuration. The recipe model must not
include branching, loops, dynamic step selection, user- or model-generated step
insertion, repository-defined dependencies between steps, or any other
workflow-engine semantics.

A recipe step may return structured statuses such as completed, blocked, failed,
or skipped when the recipe contract explicitly allows that primitive to decide
its own internal policy outcome. Those statuses are not recipe-level control
flow. They may only stop the recipe, report evidence, or allow the next fixed
step to run according to the orchestrator-owned contract.

Retries must not be represented as recipe loops. If a primitive needs retry
behavior, the retry policy must be owned by that primitive's orchestrator
implementation, have bounded limits, produce evidence, and remain invisible to
repository configuration except through explicitly accepted parameters.

Repository configuration must not alter recipe topology, step order, step count,
primitive selection, branch conditions, retry count, or failure handling.

### Recipe registry

The orchestrator must own a registry of known recipe definitions. Each recipe
definition must declare:

- a stable recipe identifier;
- the recipe kind;
- allowed invocation modes;
- required preconditions;
- ordered trusted primitives from the closed approved set;
- state-changing operations, if any;
- approval requirements by mode;
- completion evidence requirements;
- whether each primitive is read-only or state-changing;
- the accepted specification that authorized the recipe.

Unknown recipe identifiers must fail closed. Unknown operation names, hook names,
fields, schema versions, enum values, unsupported configuration values, dynamic
step definitions, and attempts to alter recipe topology must also fail closed.

Every new recipe, including a read-only recipe and including a recipe composed
only from already-approved primitive categories, must have an accepted
specification before implementation. The accepted specification must define the
recipe objective, invocation modes, hook eligibility, primitive sequence,
authority boundaries, input and output schemas, state-change policy, completion
evidence, failure behavior, and tests.

### Approved primitive categories

The MVP primitive taxonomy is closed. The `conventional-commit-staged` recipe may
use only these primitive categories:

1. **Skill proposal primitive**: starts a bounded Cline session with a named
   installed skill and returns a structured recommendation or finding. It is
   read-only with respect to repository state.
2. **Git inspection primitive**: reads repository metadata, staged paths, and
   staged diffs through typed Git operations. It must not stage, unstage, commit,
   reset, merge, rebase, clean, push, or otherwise mutate repository state.
3. **Validation primitive**: evaluates structured inputs against orchestrator
   policy and returns pass/fail/blocker evidence. It must be deterministic for
   the same inputs unless the accepted specification explicitly allows external
   state.
4. **Approval primitive**: captures explicit human acceptance, rejection, or
   edited input in standalone mode. It must not infer approval from free-form
   prose outside the approved prompt surface.
5. **Git mutation primitive**: performs a narrowly scoped typed Git mutation
   after all preconditions, authorization, and validation checks pass. For the
   MVP, the only allowed Git mutation is non-interactive commit creation for the
   authorized staged content.
6. **Evidence primitive**: records structured recipe results, blockers, and run
   summary entries without changing source artifacts except for orchestrator-owned
   logs or summaries.

No implementation may introduce a new primitive category without an accepted
specification for that category. A primitive-category specification must define:

- the category's purpose and trust boundary;
- whether it is read-only or state-changing;
- allowed inputs, outputs, and schemas;
- prohibited inputs and operations;
- authority and approval requirements;
- configuration exposure, if any;
- failure, retry, timeout, and cancellation semantics;
- required evidence;
- required unit, integration, contract, and safety tests.

Adding a new operation inside an existing primitive category is allowed only when
it stays inside that category's accepted specification and the recipe using it
has its own accepted specification.

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

The default Conventional Commit type allowlist is:

- `build`;
- `chore`;
- `docs`;
- `feat`;
- `fix`;
- `refactor`;
- `test`.

The validator must accept an optional scope and optional breaking-change marker
in the subject line, using the conventional shape `type(scope)!: description` or
`type!: description`. The description must be non-empty. Scope values should be
restricted to stable lowercase identifier characters such as letters, digits,
dots, underscores, and hyphens.

Multiline commit messages are allowed. When a body or footer is present, the
subject must be separated from the body/footer by a blank line. Standard
Conventional Commit footers, `BREAKING CHANGE:` notes, and orchestrator-owned
trailers such as `Cline-SDLC-*` are allowed. The validator must reject unsafe
control characters and message forms that cannot be passed safely to
non-interactive Git commit execution. These rules must be documented in tests.

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
orchestrator-owned capabilities. It may enable or disable accepted recipes and
accepted hook placements. It may parameterize a recipe only through fields
explicitly allowed by that recipe's accepted specification.

Configuration is not a recipe definition language. It must not create recipes,
create primitives, select primitive categories, add steps, remove steps, reorder
steps, define branches, define loops, set dynamic retry behavior, override
failure handling, or alter approval policy.

Configuration must not define:

- shell commands;
- arbitrary script paths;
- remote URLs to execute or load;
- Python import paths;
- arbitrary model-selected tools;
- broad or raw Git command strings;
- unrestricted prompt text;
- custom executable workflows;
- lifecycle-stage topology changes;
- recipe topology changes;
- step ordering or dependency declarations;
- branch, loop, retry, or dynamic step-selection rules.

Configuration parsing must fail closed on unknown schema versions, recipe ids,
hook names, operation names, fields, or enum values.

The MVP does not require repository configuration if the built-in standalone task
and embedded `before_slice_commit` behavior can be delivered safely without it.
If configuration is included in the MVP, it must be minimal and limited to
known-recipe enablement and allowed hook placement. Any configurable field must
be listed in the recipe's accepted specification with its type, default, allowed
values, and safety rationale.

## Interfaces

### Standalone repository task entry point

The CLI must expose a repository task entry point for the built-in recipe. The
canonical invocation form is:

```text
cline-sdlc task conventional-commit-staged
```

This task command should be introduced as part of, or after, a broader migration
from input-flag-driven lifecycle invocation to explicit subcommands. The intended
command grammar is:

```text
cline-sdlc idea --prompt "rough idea text"
cline-sdlc spec --idea-file docs/ideas/example-idea.md
cline-sdlc plan --spec-file docs/specs/example-spec.md
cline-sdlc implement --plan-file docs/plans/example-plan.md
cline-sdlc task conventional-commit-staged
```

The command name should select the lifecycle stage or repository task. Input
flags should provide command-specific inputs instead of implicitly selecting the
stage by their presence. Shared options such as `--timeout`, `--cline-command`,
`--json`, `--verbose`, and `--dry-run` may remain global or command-local, but
the selected parser shape must be documented and unambiguous.

Existing flag-driven lifecycle invocations, such as `cline-sdlc --idea ...` or
`cline-sdlc --spec-file ...`, may remain temporarily as compatibility aliases if
that makes migration safer. Compatibility aliases must not obscure the canonical
subcommand shape and should be marked for later deprecation once the explicit
command grammar is stable.

The MVP must not add `cline-sdlc --task conventional-commit-staged` as a
canonical form because it would extend the current ambiguous input-flag model
rather than establishing a repository-task command family.

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

If current plan-progress schemas are too narrow, embedded recipe evidence should
be represented as a dedicated, versioned `recipe_evidence` collection rather than
being overloaded into validation evidence. Each item should record at least:

- recipe id;
- invocation mode;
- hook point;
- status;
- slice id or plan section id when embedded;
- staged paths or authorized path summary;
- skill used;
- commit-message validation result;
- accepted commit message when a commit is created;
- commit hash when a commit is created;
- blocker details when blocked;
- recorded timestamp;
- optional path to an ignored run summary artifact.

### Skill interaction

The `conventional-commit-staged` recipe must invoke a bounded Cline session that
uses the `conventional-commits` skill. The recipe-oriented skill session must
return a versioned structured outcome containing at least:

- schema version;
- terminal status, such as proposed, blocked, or failed;
- skill name;
- proposed commit message;
- rationale or summary suitable for human review;
- whether the skill considered the message valid;
- any blockers or uncertainty;
- staged-path or authorized-path scope used to generate the message;
- staged-diff summary or digest reference sufficient to prove the proposal scope.

The orchestrator must not rely on free-form prose alone to decide that the skill
completed successfully.

Standalone mode may support an explicitly user-provided commit message that skips
proposal generation. That manual-message path must still inspect the staged
scope, run deterministic Conventional Commit validation, show the exact proposed
mutation, and capture explicit user acceptance before committing. Embedded mode
must use the bounded `conventional-commits` skill session unless a later accepted
specification permits a deterministic unattended alternative.

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
- Recipe contracts must remain static and linear; no branching, loops, dynamic
  step selection, or repository-defined control flow is allowed.
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
  the MVP safely;
- adding any recipe without a dedicated accepted specification;
- adding any primitive category beyond the closed MVP set without a dedicated
  accepted specification.

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
- **Recipe workflow language**: Static linear recipes are sufficient for the MVP
  and safer to reason about. Branching, loops, dynamic step selection, and
  repository-defined control flow would blur recipe execution into workflow
  execution.
- **Spec-free recipe expansion**: Even read-only recipes shape trust boundaries
  and user expectations. Every new recipe must have an accepted specification.
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
- Unknown recipe ids, hook names, operation names, schema versions, fields, enum
  values, dynamic steps, and topology changes fail closed.
- The MVP primitive taxonomy is closed, and every new primitive category requires
  an accepted specification before implementation.
- Every new recipe requires an accepted specification before implementation, even
  when it uses only existing primitive categories.
- Recipe completion or blocking is visible in terminal results and run summaries
  with structured evidence.
- Tests cover standalone blocking and success paths, embedded policy checks,
  Conventional Commit validation, Git preflight behavior, and evidence reporting.

## Validation expectations

Implementation should be verified with:

- unit tests for recipe registry lookup and fail-closed behavior;
- unit tests proving recipe contracts are static and reject dynamic topology;
- unit tests proving configuration cannot alter step order, primitive selection,
  branching, loops, retry behavior, or approval policy;
- unit tests for Conventional Commit message validation;
- unit tests for standalone approval policy;
- unit tests for embedded `before_slice_commit` authorization policy;
- Git-adapter or integration tests using temporary repositories for staged-diff
  inspection and non-interactive commit creation;
- contract or integration coverage showing plan implementation records embedded
  recipe evidence in slice summaries;
- the project quality gate configured for `ruff`, `mypy`, and `pytest`.

## Resolved implementation decisions

The original open questions are resolved as follows:

1. The canonical standalone task invocation is
   `cline-sdlc task conventional-commit-staged`. It should be introduced as part
   of, or after, a broader explicit CLI command grammar with lifecycle commands
   such as `idea`, `spec`, `plan`, and `implement`.
2. Standalone recipe mode operates only on already staged changes for the MVP.
   Optional user-confirmed staging is out of scope and requires a later accepted
   specification because it introduces path selection and an additional Git
   mutation.
3. Recipe-oriented Cline skill sessions return a versioned structured outcome
   with status, skill name, proposed commit message, human-review rationale,
   validation claim, blockers or uncertainty, and staged-scope evidence.
4. Standalone mode may support an explicitly user-provided commit message that
   skips proposal generation, but the orchestrator must still inspect staged
   scope, validate the message deterministically, show the exact proposed
   mutation, and capture explicit acceptance before committing. Embedded mode
   must use the bounded `conventional-commits` skill session unless a later
   accepted specification permits a deterministic unattended alternative.
5. Repository configuration is deferred until after the built-in recipe and hook
   model work. The MVP should rely on built-in registry behavior rather than a
   repository-local enablement or hook-placement file.
6. The default Conventional Commit type allowlist is `build`, `chore`, `docs`,
   `feat`, `fix`, `refactor`, and `test`. Multiline messages, standard footers,
   `BREAKING CHANGE:` notes, and `Cline-SDLC-*` trailers are allowed when the
   message remains safe for non-interactive Git execution.
7. Embedded recipe evidence should be represented as a dedicated, versioned
   `recipe_evidence` collection in plan progress artifacts when current schemas
   are too narrow, rather than being overloaded into validation evidence.
8. Future recipe specifications should use the template in this document's
   "Future accepted recipe specification template" section.
9. Future primitive-category specifications should use the template in this
   document's "Future accepted primitive-category specification template"
   section.

## Future accepted recipe specification template

Each new recipe specification must capture:

- objective and intended user value;
- allowed invocation modes;
- allowed lifecycle hook placements, if any;
- static primitive sequence;
- authority and approval boundaries;
- input schema and validation rules;
- output and completion-evidence schema;
- state-changing operations and exact mutation scope;
- configuration exposure, if any;
- failure, blocking, timeout, retry, and cancellation semantics;
- safety requirements and prohibited behavior;
- required unit, integration, contract, and safety tests.

## Future accepted primitive-category specification template

Each new primitive-category specification must capture:

- purpose and trust boundary;
- read-only or state-changing classification;
- allowed inputs, outputs, and schemas;
- prohibited inputs, operations, and side effects;
- authority and approval requirements;
- configuration exposure, if any;
- failure, retry, timeout, and cancellation semantics;
- required evidence and terminal-result representation;
- observability, redaction, and sensitive-data handling;
- required unit, integration, contract, and safety tests.
