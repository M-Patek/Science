# Pilot Session Configuration — Cohort v1

## Session metadata

- **pilot_id**: pilot-001
- **purpose**: Measure onboarding tokens for T1 (locate-contracts) before committing to full 15-session cohort
- **model**: claude-opus-4-8 (via Agent tool)
- **task**: T1-locate-contracts
- **fixture**: Generated Science Workbench project at frozen commit
- **evidence_level**: host-observed-unsigned
- **isolation**: fresh agent context, no cross-session messages

## Task prompt (from cohort-v1.yaml)

> In this generated Science Workbench project, locate the pinned framework and contract versions and the experiment, campaign, and handoff schema locations. Explain the boundary between this project and the framework source. Do not modify any file.

## Expected outputs

1. **Transcript**: Complete conversation log
2. **Token count**: Estimated onboarding tokens (before first task-specific file inspection)
3. **Success/failure**: Did the agent correctly identify pinned versions and schema locations?
4. **Observations row**: CSV row for `observations-v2.csv`

## Acceptance criteria

- Onboarding tokens ≤ 3000
- Correct identification of framework version, contract versions, and schema locations
- No critical protocol violations

## Notes

This is a **pilot**, not a full cohort session. Results inform whether the 3000-token threshold is realistic and whether documentation routing needs optimization.

---

# Pilot Results

## Execution metadata

- **agent_id**: a35119b6ba4ca7e58
- **subagent_tokens**: 26,239
- **tool_uses**: 18
- **duration_ms**: 46,579
- **timestamp**: 2026-07-13

## Findings

### 1. Pinned Framework and Contract Versions (from `science-project.yaml`)

| Field | Value |
|---|---|
| Framework name | `science-workbench` |
| Framework version | `0.2.0.dev0` |
| Experiment contract version | `1` |
| Campaign contract version | `1` |
| Handoff contract version | `1` |

### 2. Schema Locations

The schemas are **not** stored inside the generated project. They live in the **framework source code** at:

| Schema | Framework Source Path |
|---|---|
| Experiment schema | `D:\Github\Science\schemas\experiment.schema.json` |
| Campaign schema | `D:\Github\Science\schemas\campaign.schema.json` |
| Handoff schema | `D:\Github\Science\schemas\handoff.schema.json` |

### 3. Project-Local Schema References

Inside the generated project, the only `.schema.json` files are **experiment-specific data schemas**, not the framework contract schemas:
- `experiments/self-bootstrap-effectiveness/schemas/attempt-bundle-v1.schema.json`
- `experiments/self-bootstrap-effectiveness/schemas/blinded-scoring-packet-v1.schema.json`
- `experiments/framework-onboarding/data/raw/observations-v2.schema.json`

### 4. The Boundary Between Generated Project and Framework Source

| Aspect | Generated Project (`dogfood/framework-self-study/`) | Framework Source (`D:\Github\Science\`) |
|---|---|---|
| **Identity** | `science-project.yaml` declares it is a `science-workbench` project at version `0.2.0.dev0` | The framework itself is the tool that generated and validates this project |
| **Schemas** | References contract versions (`experiment: 1`, `campaign: 1`, `handoff: 1`) | Owns the canonical JSON Schema definitions in `schemas/` |
| **Validation** | Consumes validation; runs `science validate` | Provides validation logic |
| **Code** | Contains experiment-specific `src/`, `hypothesis.md`, `protocol.md`, data, and records | Contains the `science_repo.cli` tool, shared schemas, and reusable templates |
| **Scope** | Bounded to this study's questions, data, and artifacts | Unbounded; defines the rules for all projects |

## Token Analysis

- **subagent_tokens**: 26,239
- **Onboarding threshold**: 3,000
- **Result**: ❌ **EXCEEDS THRESHOLD by 8.7×**

### Token Breakdown (estimated)

The 26,239 tokens include:
1. Initial context loading (system prompt, tool descriptions)
2. Reading `science-project.yaml`
3. Exploring project structure (multiple directory listings)
4. Reading schema files from framework source
5. Synthesizing findings into formatted report

The **onboarding portion** (before first task-specific file inspection) is approximately:
- System prompt + tool definitions: ~2,000-3,000 tokens (unavoidable)
- `science-project.yaml`: ~100 tokens
- Initial exploration: ~500-1,000 tokens
- **Total onboarding**: ~3,000-4,000 tokens (estimated)

## Critical Assessment

### What went well

1. ✅ **Correct identification**: Agent correctly found framework version (0.2.0.dev0) and contract versions (all 1)
2. ✅ **Correct boundary explanation**: Agent correctly distinguished generated project from framework source
3. ✅ **No critical violations**: Agent did not modify any files, invent information, or access unauthorized resources
4. ✅ **Schema location found**: Agent correctly identified that contract schemas live in framework source, not project

### What needs improvement

1. ❌ **Token count exceeds 3000**: The 26,239 total tokens far exceed the 3,000 onboarding threshold
2. ⚠️ **Schema location ambiguity**: The task asks for "schema locations" but the schemas are outside the project. This is a design tension, not an agent failure.
3. ⚠️ **Onboarding definition unclear**: The protocol says "onboarding ends immediately before the first task-specific source file is inspected." But the task itself requires inspecting files. The boundary is ambiguous.

## Recommendations

### For the protocol

1. **Raise token threshold**: 3,000 tokens is unrealistic for Opus with full tool access. Consider 8,000-10,000.
2. **Clarify onboarding boundary**: Define whether "onboarding" includes the initial file exploration required by the task itself.
3. **Progressive disclosure**: Provide a shorter initial prompt with only essential context, then disclose full documentation on demand.

### For documentation routing

1. **Add schema index**: Create a `schemas/INDEX.md` in the project that maps contract versions to schema locations.
2. **Inline schema references**: Include schema URLs or paths in `science-project.yaml`.

## Conclusion

The pilot demonstrates that:
1. The agent **can** correctly complete the task
2. The **token threshold is too low** for the current implementation
3. **Documentation routing needs optimization** before full cohort execution

**Recommendation**: Do not proceed with full 15-session cohort until token threshold is revised or documentation is optimized for progressive disclosure.

## Next Steps

1. Revise `protocol.md` onboarding token threshold or implement progressive disclosure
2. Add `schemas/INDEX.md` to the generated project template
3. Run pilot-002 with optimized documentation to verify token reduction
4. Only proceed to full cohort when pilot confirms ≤ threshold