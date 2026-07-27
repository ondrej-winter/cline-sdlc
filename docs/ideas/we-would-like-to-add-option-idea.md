# Configurable Lifecycle Stages and Tasks

## Problem Statement

How might we let repository maintainers define lifecycle stage sequences, stage meanings, and task granularity declaratively without turning the SDLC orchestrator into an unsafe general-purpose workflow engine?

## Recommended Direction

Add a repository-visible lifecycle configuration concept that describes the stages and tasks a repository wants the orchestrator to recognize. The strongest direction is not merely configurable prompts for the existing lifecycle; it is a constrained definition layer for repository-specific lifecycle topology: what stages exist, how they are grouped, what tasks belong inside them, which interaction mode applies, and what artifact or evidence boundary each stage or task is expected to reach.

The configuration should compose known safe primitives rather than execute arbitrary commands. A stage or task may reference allowlisted skills, bounded prompt templates, input kinds, artifact conventions, interaction policies, and completion evidence declarations. It should not become YAML-as-code, a shell runner, or a full plugin marketplace. This gives repositories enough flexibility to model different governance and delivery workflows while preserving the orchestrator’s core safety posture.

The key hardening insight is that completion semantics are the riskiest part of the idea. The first useful version should prove that declarative artifact/evidence boundaries can express “done” for configurable stages and nested tasks without being so vague that the agent merely declares success, or so rigid that real SDLC workflows cannot fit. The idea should therefore be validated around completion boundaries before committing to a broad workflow-engine design.

## Key Assumptions to Validate

- [ ] Different repositories need materially different lifecycle topologies, not just different wording for the same built-in stages. Test by collecting at least three real repository workflows and mapping their stage sequences, stage meanings, and nested tasks.
- [ ] A constrained declarative format can represent useful stage/task variation without allowing arbitrary code or shell execution. Test by modeling candidate workflows using only safe primitives such as stage identity, task identity, skill reference, prompt template, input kind, artifact convention, interaction mode, and evidence boundary.
- [ ] Declarative artifact/evidence boundaries can express “done” clearly enough for configured stages and tasks. Test by asking maintainers to review sample boundaries and predict what output would count as complete, incomplete, or blocked.
- [ ] Task-level completion and stage-level completion can be separated without overcomplicating the mental model. Test by modeling one simple single-task stage and one multi-task stage, then checking whether their completion rules remain understandable.
- [ ] Repository maintainers can debug configured lifecycle behavior from repository-visible files. Test with a sample configuration and ask a maintainer to predict the selected stage, tasks, interaction mode, artifact path, and stopping boundary.

## MVP Scope

The MVP is a minimal repository-local lifecycle configuration mechanism that can represent the current built-in lifecycle plus one repository-specific workflow with at least one multi-task stage. It should support declaring stage names, task names, stage/task grouping, input kind, interaction mode, skill or prompt primitive, artifact path convention, and completion evidence boundary.

In scope: configuration shape exploration, validation of safe declarative primitives, examples that model existing and custom workflows, and pressure-testing completion semantics for both task and stage boundaries. The MVP should focus on whether configured lifecycle definitions are understandable and safe before expanding into richer execution behavior.

Out of scope: arbitrary shell or script execution, dynamic dependency installation, marketplace-style plugins, unrestricted custom code hooks, automatic multi-stage cascading, and replacing all built-in stages before the configured model has proven it can mirror and extend current behavior.

## Not Doing and Why

- Arbitrary task execution from configuration — this would make lifecycle configuration equivalent to code execution and undermine the orchestrator’s safety model.
- A general-purpose workflow engine — the goal is SDLC lifecycle configurability, not competing with CI systems, task runners, or automation platforms.
- Automatic cascading across major lifecycle boundaries — the project’s existing safety model depends on stopping at explicit artifact boundaries instead of silently continuing into the next stage.
- A full plugin framework or marketplace — plugins introduce packaging, trust, versioning, dependency, and support burdens before the smaller repository-configuration need is validated.
- Solving completion semantics by assertion alone — “the agent says it is done” is not a sufficient boundary model for configurable stages and tasks.

## Open Questions

- What is the smallest completion model that can handle both task-level evidence and stage-level artifact boundaries?
- Should configured stages be repository-local only, or should users be able to pass an explicit lifecycle configuration file at invocation time?
- Should the configuration format be YAML, TOML, or JSON, given the project already uses `pyproject.toml` but stage/task definitions may benefit from YAML readability?
- How should conflicts between built-in lifecycle stages and repository-configured stages be resolved?
- What should be allowlisted as safe primitives: installed skills, prompt templates, artifact kinds, interaction modes, evidence checks, or something narrower?
- In unattended mode, can configured stages ever produce accepted artifacts, or should they only produce reviewable drafts and blockers?
