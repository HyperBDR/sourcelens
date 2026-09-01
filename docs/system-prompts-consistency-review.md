# System Prompts Consistency Review

## Status

Implementation in progress. This document records contradictions found in the
LensNode document-analysis prompt stack on 2026-08-31 and the target contract
used for the first refactoring slice.

## Scope

Reviewed components:

- `lensnode/lensnode/agent_runtime/system_prompts.py`
- `lensnode/lensnode/agent_runtime/scenarios.py`
- `lensnode/lensnode/agent_runtime/prompts.py`
- `lensnode/lensnode/agent_runtime/runtime.py`

The review focuses on user-facing document explanations and the accidental
disclosure of runtime paths and operational instructions.

## Findings

### 1. Evidence grounding must be separate from citation presentation

The knowledge workflow must require every factual claim to be grounded in a
specific, inspected workspace source. That is an internal evidence
requirement, not a requirement to print a citation for every claim.

The user-facing answer boundary instead says that internal filesystem paths,
runtime directories, sidecar filenames, workspace mounts, and internal
identifiers must never be disclosed; it permits only the document display
filename in a citation.

The previous wording conflated those two concerns: it required citations while
also forbidding internal paths. That made a sidecar or runtime path an easy
thing for the model to repeat.

**Required resolution:** distinguish evidence grounding from citation
presentation, and distinguish internal retrieval identity from public citation
identity. Tool output may use an internal locator. The final answer should
omit citations by default and show only a trusted display name or public
relative path when the user or bound assistant prompt requests citations.

### 2. Internal paths are included in model-visible prompt text

The knowledge prompt renders selected subject and reference directories as
literal paths. Those paths are then visible to the model before the prompt
asks it not to disclose them.

This is a weak boundary: a model can repeat prompt-visible text, especially
when the user's message also asks it to inspect a named path.

**Required resolution:** pass internal paths only to workspace tools. The
natural-language prompt should expose an allowlisted presentation model, such
as a document display name and a non-sensitive source label.

### 3. Bound context skills can override output-safety rules

The context-skill block says its guidance is authoritative and wins when it
conflicts with default behavior, including final-answer path conventions.

That precedence is broader than the later confidentiality and disclosure
rules. A bound skill could therefore instruct the agent to print paths or
operational detail, leaving the model to choose between two system-level
messages.

**Required resolution:** define an explicit precedence order. Security,
confidentiality, tenant isolation, and user-facing disclosure restrictions
must not be overridden by workspace guides, bound skills, user messages, or
uploaded-document content.

### 4. User-supplied operational text is not explicitly demoted

The prompt correctly treats uploaded documents as untrusted evidence. It does
not state with equal clarity that tool names, filesystem paths, and execution
steps quoted in a user message are data rather than instructions that can
change runtime tool policy.

This makes messages such as “run this tool against this internal path” more
likely to be repeated in the answer or followed as a workflow prescription.

**Required resolution:** add a rule that operational-looking text in user
messages is not authoritative. The agent must follow the runtime's workspace
tool boundary and must not disclose internal execution steps in its answer.

### 5. Final-output sanitization is incomplete and should be a backstop

The current answer normalizer was designed for relative code paths. A new
knowledge-answer sanitizer removes selected document-runtime path patterns and
some tool names, but it only runs for `knowledge_qa` and matches a limited set
of forms.

Other paths can still flow through Smart Collaboration, General Chat skills,
or a different document-processing task. Regular-expression replacement also
cannot safely be the primary authorization boundary.

**Required resolution:** make output sanitization a shared final-response
backstop for every user-facing runtime mode. It should redact internal mounts,
runtime metadata, sidecar locations, scratch paths, internal IDs, and raw
tool-call syntax. The primary defense remains not placing those values in the
model-visible prompt.

## Non-contradictory but confusing duplication

The answer-language requirement appears at both the beginning and end of the
knowledge prompt. The duplicate text is consistent, but it unnecessarily
increases prompt length and makes precedence harder to audit. Keep one
authoritative language block near the highest-priority answer policy.

The prompt also gives workspace retrieval rules in several sections. These
rules are mostly compatible, but their overlap makes it easy for a future edit
to introduce another contradiction.

## Recommended Target Contract

1. The control plane provides each uploaded document with two identities:
   an internal tool-only locator and a public display name.
2. Only the display name may appear in model-visible citation guidance and
   user-facing answers.
3. System safety and confidentiality boundaries outrank all injected context,
   Skills, user text, and uploaded files.
4. Workspace retrieval instructions belong in one dedicated section; public
   answer restrictions belong in one later, explicitly higher-priority
   section.
5. A shared final-response sanitizer acts as defense in depth, not as the
   primary mechanism.

## Adjustment Scope

The DeerFlow and OpenCode comparison should be applied selectively. The
following scope separates the changes required for SourceLens from behavior
that belongs to those projects' different operating models.

| Priority | Adjustment | Affected area | Expected behavior |
| --- | --- | --- | --- |
| P0 | Separate evidence grounding from citation display | `scenarios.py`, `system_prompts.py`, assistant prompt contract | Retrieval must use an inspected, explicit source; citations are omitted by default and enabled only by the user or the bound assistant prompt. |
| P0 | Separate public document identity from internal locator | Control-plane document metadata, workspace-tool arguments, prompt assembly, citation rendering | Internal locator is tool-only; model/user-facing text uses an allowlisted display name or public relative path. |
| P0 | Make confidentiality and injection boundaries dominant | System prompt composition, context-skill injection, user/document content handling | Skills, user text, and document text may provide task guidance but cannot override safety, isolation, or disclosure rules. |
| P1 | Add a shared final-response safety backstop | Runtime finalization for Knowledge Q&A, Smart Collaboration, General Chat, and document-related skills | Redact internal mounts, sidecars, runtime IDs, raw tool syntax, and operational steps in every user-facing mode. |
| P1 | Add regression coverage across entry points | LensNode unit/integration tests and frontend observation tests | The same disclosure and grounding contract holds for direct Q&A, collaboration, and skill-assisted document analysis. |
| P2 | Keep execution authorization explicit | Tool registry/authorization boundary | Adopt DeerFlow's pre-execution guardrail pattern where tools can cause side effects; this is separate from answer citation policy. |

### Deliberately out of scope

- Do not copy OpenCode's assumption that absolute local project paths are
  useful user-facing context; SourceLens is a multi-user document-analysis
  service with a stricter disclosure boundary.
- Do not treat a regex sanitizer as the authorization mechanism. It remains a
  defense-in-depth layer after prompt and tool-boundary fixes.
- Do not require every assistant to show citations. Citation style is an
  assistant-level/user-level presentation choice, while evidence grounding is
  a platform invariant.
- Do not change document retrieval semantics, indexing formats, or storage
  layout solely to implement this prompt contract.

### Rollout order

1. Define the document metadata contract (`display_name` plus tool-only
   `locator`) and update prompt assembly to stop rendering internal locators.
2. Update scenario and assistant prompt wording so grounding is mandatory but
   citation presentation is conditional.
3. Move output sanitization to the shared runtime finalization path and cover
   all user-facing modes.
4. Add cross-entry-point regression tests, then consider pre-tool guardrails
   for side-effecting tools.

## First Refactoring Slice

Implemented in the prompt/runtime layer:

- A single platform-safety boundary is prepended to Knowledge Q&A, General
  Chat, and Smart Collaboration prompts.
- Bound context Skills are explicitly limited to task behavior and answer
  presentation; they cannot override platform safety or disclosure policy.
- Subject-document directories are no longer rendered in natural-language
  prompts. The prompt receives only uploaded document display names and an
  aggregate count of reference sources.
- Evidence grounding remains mandatory while citation display is conditional
  on the user request or bound assistant prompt.
- The final-answer sanitizer is shared by Knowledge Q&A and General Chat;
  it redacts known document sidecars, runtime locations, and raw workspace
  tool names.

Still pending:

- Make all workspace and conversation-artifact locators tool-only; historical
  artifact prompts still need a public identity plus a tool-lookup contract.
- Apply equivalent redaction safely to streaming deltas. Chunk boundaries mean
  a final-answer sanitizer cannot be reused blindly for individual deltas.
- Replace pattern-based redaction with structured provenance at the tool and
  response boundary, and add pre-tool authorization for side-effecting tools.

## Verification Plan

- Unit-test prompt assembly to ensure no internal document locators are
  rendered in user-facing citation guidance.
- Unit-test output normalization for subject documents, workspace mounts,
  sidecars, scratch locations, tool names, and runtime identifiers.
- Add an integration test for a Chinese document-explanation request whose
  input contains internal-looking paths and tool instructions; its answer must
  use the document display name and omit operational details.
- Repeat the test through direct knowledge Q&A, Smart Collaboration, and a
  General Chat assistant that invokes a document-related Skill.
- Test the platform boundary as a contract: internal locators are absent,
  display names are present, and a bound Skill cannot elevate its precedence.
- Test final-answer redaction parametrically for every user-facing runtime
  mode; add dedicated streaming tests once streaming redaction is introduced.
