DECOMPOSITION_A_VERSION = "decomposition-a-v1"
DECOMPOSITION_B_VERSION = "decomposition-b-v1"
DECOMPOSITION_A_INSTRUCTION = """Decompose independently from supplied idea only.
Focus on the smallest independently meaningful/comparable contributions. Reject
over-bundling: independent contributions must remain separate even in one sentence.
Do not split to isolated words/ingredients where the relationship is the contribution.
No novelty or prior-art judgment. Material MCU statements/mechanisms must be verbatim
supported excerpts. Features trace to excerpts; all relationship endpoints are feature IDs.
Keep missing mechanisms unknown. Preserve contradictions. Separate meaningful
combinations with member IDs and supported statements. No arbitrary-specificity MCU.
"""
DECOMPOSITION_B_INSTRUCTION = """Independently derive mechanism/relationship MCUs
from the supplied idea, not another decomposition. Preserve functional, causal,
architectural and procedural relationships creating differentiation. Restore a causal
contribution if sentence fragmentation obscures it. Split independently comparable
contributions, not ordinary ingredients. Separate meaningful combinations from members.
Never infer withheld mechanisms or novelty. Material MCU statements/mechanisms must
be verbatim supported excerpts. Features trace to excerpts, endpoints are feature IDs.
Keep disagreement/unknowns explicit. Arbitrary contextual detail is not a contribution.
"""
CRITIC_VERSION = "structural-critic-v1"
CRITIC_INSTRUCTION = """Criticize MCU structure, never judge novelty or prior art.
Execute REMOVAL (does removing unit remove meaningful claimed contribution),
INDEPENDENCE (independently comparable), RELATIONSHIP_PRESERVATION (essential links
survive), MERGE (independent units not bundled), PARAPHRASE_STABILITY (meaning preserved
across independently derived views), SPECIFICITY (not only arbitrary contextual detail).
Return one result per test, referenced IDs from proposed graph only. Unknown is null,
not pass; explanations and source support required for meaning-level judgments.
If fragmented ingredients are not independently meaningful, propose grounded restored
units; if oversized bundle contains independent contributions, propose grounded split.
Preserve meaningful combinations and every contribution/relationship from both views,
or explicitly retain unresolved disagreements. Never force consensus. Genuine unresolved
relationship/granularity disagreement is MATERIAL. State rationale for all changes.
"""
