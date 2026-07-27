from pathlib import Path

path = Path('/Users/owinter/Documents/Projects/ondrej-winter.nosync/cline-sdlc/docs/specs/configurable-lifecycle-hooks-and-repository-task-spec.md')
text = path.read_text(encoding='utf-8')

text = text.replace(
"""- Decision state: accepted specification\n- Lifecycle stage: specification creation\n- Intended scope: built-in repository task recipes with safe lifecycle-hook reuse\n""",
"""- Decision state: accepted specification, hardened by interview on 2026-07-27\n- Lifecycle stage: specification creation\n- Intended scope: built-in repository task recipes with safe lifecycle-hook reuse\n""",
)

text = text.replace(
"""6. Repository-local configuration may eventually enable or parameterize known\n   recipes and hook placements, but the MVP can start with built-in behavior\n   before exposing a durable configuration file.\n""",
"""6. Repository-local configuration may eventually enable or parameterize known\n   recipes and hook placements, but the MVP can start with built-in behavior\n   before exposing a durable configuration file.\n7. Recipes are static linear orchestrator-owned contracts, not configurable\n   workflows. Branching, loops, dynamic step selection, and repository-defined\n   control flow are intentionally out of scope.\n8. Every new recipe and every new primitive category requires its own accepted\n   specification before implementation, even if the recipe appears read-only or\n   uses already-approved primitive categories.\n""",
)

text = text.replace(
"""## Desired behavior\n\n### Recipe registry\n""",
"""## Desired behavior\n\n### Recipe contract and composition model\n\nA recipe must be a static, linear, orchestrator-owned contract. Its step sequence\nmust be declared in orchestrator-controlled code or data bundled with the\norchestrator, not in repository-local configuration. The recipe model must not\ninclude branching, loops, dynamic step selection, user- or model-generated step\ninsertion, repository-defined dependencies between steps, or any other\nworkflow-engine semantics.\n\nA recipe step may return structured statuses such as completed, blocked, failed,\nor skipped when the recipe contract explicitly allows that primitive to decide\nits own internal policy outcome. Those statuses are not recipe-level control\nflow. They may only stop the recipe, report evidence, or allow the next fixed\nstep to run according to the orchestrator-owned contract.\n\nRetries must not be represented as recipe loops. If a primitive needs retry\nbehavior, the retry policy must be owned by that primitive's orchestrator\nimplementation, have bounded limits, produce evidence, and remain invisible to\nrepository configuration except through explicitly accepted parameters.\n\nRepository configuration must not alter recipe topology, step order, step count,\nprimitive selection, branch conditions, retry count, or failure handling.\n\n### Recipe registry\n""",
)

text = text.replace(
"""- ordered trusted primitives;\n- state-changing operations, if any;\n- approval requirements by mode;\n- completion evidence requirements.\n""",
"""- ordered trusted primitives from the closed approved set;\n- state-changing operations, if any;\n- approval requirements by mode;\n- completion evidence requirements;\n- whether each primitive is read-only or state-changing;\n- the accepted specification that authorized the recipe.\n""",
)

text = text.replace(
"""Unknown recipe identifiers must fail closed. Unknown operation names, hook names,\nfields, schema versions, enum values, or unsupported configuration values must\nalso fail closed.\n""",
"""Unknown recipe identifiers must fail closed. Unknown operation names, hook names,\nfields, schema versions, enum values, unsupported configuration values, dynamic\nstep definitions, and attempts to alter recipe topology must also fail closed.\n\nEvery new recipe, including a read-only recipe and including a recipe composed\nonly from already-approved primitive categories, must have an accepted\nspecification before implementation. The accepted specification must define the\nrecipe objective, invocation modes, hook eligibility, primitive sequence,\nauthority boundaries, input and output schemas, state-change policy, completion\nevidence, failure behavior, and tests.\n""",
)

text = text.replace(
"""### Invocation modes\n""",
"""### Approved primitive categories\n\nThe MVP primitive taxonomy is closed. The `conventional-commit-staged` recipe may\nuse only these primitive categories:\n\n1. **Skill proposal primitive**: starts a bounded Cline session with a named\n   installed skill and returns a structured recommendation or finding. It is\n   read-only with respect to repository state.\n2. **Git inspection primitive**: reads repository metadata, staged paths, and\n   staged diffs through typed Git operations. It must not stage, unstage, commit,\n   reset, merge, rebase, clean, push, or otherwise mutate repository state.\n3. **Validation primitive**: evaluates structured inputs against orchestrator\n   policy and returns pass/fail/blocker evidence. It must be deterministic for\n   the same inputs unless the accepted specification explicitly allows external\n   state.\n4. **Approval primitive**: captures explicit human acceptance, rejection, or\n   edited input in standalone mode. It must not infer approval from free-form\n   prose outside the approved prompt surface.\n5. **Git mutation primitive**: performs a narrowly scoped typed Git mutation\n   after all preconditions, authorization, and validation checks pass. For the\n   MVP, the only allowed Git mutation is non-interactive commit creation for the\n   authorized staged content.\n6. **Evidence primitive**: records structured recipe results, blockers, and run\n   summary entries without changing source artifacts except for orchestrator-owned\n   logs or summaries.\n\nNo implementation may introduce a new primitive category without an accepted\nspecification for that category. A primitive-category specification must define:\n\n- the category's purpose and trust boundary;\n- whether it is read-only or state-changing;\n- allowed inputs, outputs, and schemas;\n- prohibited inputs and operations;\n- authority and approval requirements;\n- configuration exposure, if any;\n- failure, retry, timeout, and cancellation semantics;\n- required evidence;\n- required unit, integration, contract, and safety tests.\n\nAdding a new operation inside an existing primitive category is allowed only when\nit stays inside that category's accepted specification and the recipe using it\nhas its own accepted specification.\n\n### Invocation modes\n""",
)

text = text.replace(
"""### Configuration authority model\n\nRepository-local configuration, when introduced, may only select from known\norchestrator-owned capabilities. It may enable, disable, or parameterize built-in\nrecipes and allowed hook placements.\n""",
"""### Configuration authority model\n\nRepository-local configuration, when introduced, may only select from known\norchestrator-owned capabilities. It may enable or disable accepted recipes and\naccepted hook placements. It may parameterize a recipe only through fields\nexplicitly allowed by that recipe's accepted specification.\n\nConfiguration is not a recipe definition language. It must not create recipes,\ncreate primitives, select primitive categories, add steps, remove steps, reorder\nsteps, define branches, define loops, set dynamic retry behavior, override\nfailure handling, or alter approval policy.\n""",
)

text = text.replace(
"""- lifecycle-stage topology changes.\n""",
"""- lifecycle-stage topology changes;\n- recipe topology changes;\n- step ordering or dependency declarations;\n- branch, loop, retry, or dynamic step-selection rules.\n""",
)

text = text.replace(
"""If configuration is included in the MVP, it must be minimal and limited to\nknown-recipe enablement and allowed hook placement.\n""",
"""If configuration is included in the MVP, it must be minimal and limited to\nknown-recipe enablement and allowed hook placement. Any configurable field must\nbe listed in the recipe's accepted specification with its type, default, allowed\nvalues, and safety rationale.\n""",
)

text = text.replace(
"""- Repository content and configuration must not become a workflow engine.\n""",
"""- Repository content and configuration must not become a workflow engine.\n- Recipe contracts must remain static and linear; no branching, loops, dynamic\n  step selection, or repository-defined control flow is allowed.\n""",
)

text = text.replace(
"""- additional hook points beyond `before_slice_commit` unless needed to complete\n  the MVP safely.\n""",
"""- additional hook points beyond `before_slice_commit` unless needed to complete\n  the MVP safely;\n- adding any recipe without a dedicated accepted specification;\n- adding any primitive category beyond the closed MVP set without a dedicated\n  accepted specification.\n""",
)

text = text.replace(
"""- **Full configurable lifecycle topology**: The immediate value is reusable task\n  recipes and hook placement, not replacing stage selection.\n""",
"""- **Full configurable lifecycle topology**: The immediate value is reusable task\n  recipes and hook placement, not replacing stage selection.\n- **Recipe workflow language**: Static linear recipes are sufficient for the MVP\n  and safer to reason about. Branching, loops, dynamic step selection, and\n  repository-defined control flow would blur recipe execution into workflow\n  execution.\n- **Spec-free recipe expansion**: Even read-only recipes shape trust boundaries\n  and user expectations. Every new recipe must have an accepted specification.\n""",
)

text = text.replace(
"""- Unknown recipe ids, hook names, operation names, schema versions, fields, or\n  enum values fail closed.\n""",
"""- Unknown recipe ids, hook names, operation names, schema versions, fields, enum\n  values, dynamic steps, and topology changes fail closed.\n- The MVP primitive taxonomy is closed, and every new primitive category requires\n  an accepted specification before implementation.\n- Every new recipe requires an accepted specification before implementation, even\n  when it uses only existing primitive categories.\n""",
)

text = text.replace(
"""- unit tests for recipe registry lookup and fail-closed behavior;\n""",
"""- unit tests for recipe registry lookup and fail-closed behavior;\n- unit tests proving recipe contracts are static and reject dynamic topology;\n- unit tests proving configuration cannot alter step order, primitive selection,\n  branching, loops, retry behavior, or approval policy;\n""",
)

text = text.replace(
"""7. How should embedded recipe evidence be represented in the existing\n   plan-implementation progress artifacts if current schemas are too narrow?\n""",
"""7. How should embedded recipe evidence be represented in the existing\n   plan-implementation progress artifacts if current schemas are too narrow?\n8. What template should future accepted recipe specifications use so each one\n   consistently captures authority boundaries, primitive sequence, evidence, and\n   safety tests?\n9. What template should future accepted primitive-category specifications use so\n   each one consistently captures trust boundaries, configuration exposure,\n   failure semantics, and required tests?\n""",
)

path.write_text(text, encoding='utf-8')
print(path)
