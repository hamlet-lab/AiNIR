# AiNIR public launch kit

This document is a launch-facing companion to the technical README. It is designed to make AiNIR understandable quickly **without widening the public claim boundary**.

## Core positioning

### One-line identity

> **Model output is a claim, not a fact.** AiNIR checks AI-generated workflow semantics before a host is allowed to move them toward execution.

### Short repository description

> Semantic preflight for AI-agent actions before execution.

### Slightly fuller description

> AiNIR is a bounded semantic trust layer that checks AI-generated actions, evidence, capabilities, effects, and host-owned context before the host decides whether they may proceed toward execution.

### The simple mental model

```text
AI proposes
    ↓
AiNIR checks the proposal
    ↓
PASS ─────→ host may continue
REFUSE ───→ stop + explain why
```

AiNIR does not execute the action itself. The host still owns authentication, authorization, sandboxing, resource access, transaction enforcement, and the final side effect.

## 30-second explanation

AI agents can generate outputs that are syntactically valid and still unsafe to execute.

A schema can tell you whether a tool call has the right shape. Authorization can tell you whether an actor has access. A sandbox can constrain where execution happens.

AiNIR asks a different question **before execution**:

> Has this proposed action been sufficiently evidenced, bounded, and semantically validated to move forward at all?

The public demo shows both sides: destructive account deletion, real payments, raw reset-token persistence, and unsafe PII export are refused; a reviewed transaction-bound outbox path passes and can issue a replayable `TrustReceipt`.

## Suggested GitHub metadata

### Description

`Semantic preflight for AI-agent actions before execution.`

### Topics

Prioritize existing discovery language first:

- `ai-agents`
- `agent-safety`
- `llm`
- `mcp`
- `tool-calling`
- `ai-security`
- `runtime-safety`
- `agent-governance`
- `policy-as-code`
- `semantic-verification`

Avoid relying only on project-internal vocabulary for discovery.

### Social preview

Use `assets/ainir-social-preview.png` once the repository social-preview setting is updated.

Suggested preview copy:

> **AiNIR**  
> Model output is a claim, not a fact.  
> Semantic preflight for AI-generated actions before execution.

## Show HN-style launch draft

### Title

`Show HN: AiNIR – semantic preflight for AI-agent actions before execution`

### Body

I built AiNIR around a simple premise: **model output is a claim, not a fact**.

When an agent proposes an action, syntactic validity alone does not tell us whether that action has earned the right to happen. AiNIR sits between an AI-generated proposal and the host execution layer and checks reviewed operation contracts, effects, capabilities, evidence bindings, trusted host context, and transaction requirements.

The public repo is intentionally bounded and fail-closed rather than claiming to verify arbitrary generated code. Its demo includes destructive account deletion, a real payment effect, raw reset-token persistence, and unsafe PII export as refusal cases, plus a transaction-bound outbox workflow as a passing case.

There is also a bounded MCP `tools/call` preflight profile and an adapter for already-observed OpenAI Responses `function_call` artifacts. Neither path contacts the provider or executes the tool; the host remains responsible for time-of-use authorization and execution.

The part I am most interested in feedback on is the boundary itself: **what semantic information should an agent have to prove before a host lets its proposal cross into an executable system?**

This is a pre-v1 / v1.0 RC public demo, not a production runtime or a universal verifier.

## Reddit / developer-community draft

### Title

`I built a semantic checkpoint between AI agents and tool execution`

### Body

A lot of agent safety discussion starts after a tool call has already been selected: schema validation, authorization, sandboxing, runtime policy, and so on.

I wanted to explore an earlier boundary.

If a model proposes `delete_user`, `charge_payment`, `export_pii`, or an MCP `tools/call`, what would it mean for the proposal itself to be **semantically eligible** to move toward execution?

AiNIR treats the model output as a claim. The public implementation checks a bounded registry of reviewed workflows against effects, capabilities, evidence bindings, trusted host context, and transaction requirements. Unknown workflows fail closed.

The README now has a short animated demo showing a destructive workflow refused next to a bounded safe path passing.

I would especially value criticism around:

- where this layer overlaps too much with existing policy engines;
- which claims should remain host-owned rather than model-provided;
- what a useful TrustReceipt / replay model should prove;
- how an MCP preflight boundary should interact with time-of-use authorization.

The repo is pre-v1 and intentionally does not claim production readiness or arbitrary-code verification.

## Short-form posts

### Very short

> Model output is a claim, not a fact.  
> AiNIR adds semantic preflight between an AI agent's proposed action and the host that could execute it.

### Short with contrast

> JSON Schema asks: "Is this shaped correctly?"  
> Authorization asks: "May this actor access it?"  
> AiNIR asks: **"Has this proposed action earned the right to move toward execution?"**

### Demo-led

> AI proposes permanent account deletion → AiNIR: **REFUSED**.  
> AI proposes a reviewed transaction-bound outbox workflow → **PASSED** + TrustReceipt.  
> Same agent boundary, different semantic evidence.

## Likely questions and concise answers

### Is this just a policy engine?

Not exactly. Policy engines are complementary and often evaluate configured rules over an already-formed request. AiNIR's public claim is narrower: it evaluates bounded AI-generated workflow semantics against reviewed operation/effect/capability contracts, evidence bindings, trusted host context, and transaction requirements before lowering or execution eligibility.

### Is this a sandbox?

No. A sandbox constrains execution. AiNIR is a semantic preflight layer before execution. A production system would still need sandboxing and runtime controls.

### Does a PASS mean the action is safe?

No. A pass means the bounded AiNIR checks passed for that exact proposal and context. The host must still perform time-of-use authorization, resource validation, and execution controls.

### Can it verify arbitrary AI-generated code?

No. The public implementation is intentionally closed-world and fail-closed. Unknown workflows are refused rather than guessed.

### Does AiNIR execute MCP or OpenAI tool calls?

No. The public MCP and OpenAI examples consume host-observed artifacts and emit semantic assessments. They do not contact the provider or execute the tool.

### Why is TrustReceipt useful?

It makes a passing semantic decision inspectable and replayable against the registry state that supported it, instead of reducing trust to an ephemeral model response.

## Claim-boundary rules for public writing

Keep these statements explicit:

- this is a **pre-v1 / v1.0 RC public demo**;
- it is **not a v1.0 final**;
- it is **not a production runtime**;
- it does **not** verify arbitrary AI-generated code;
- the public implementation is **closed-world** and unknown workflows fail closed;
- PASS is not equivalent to execution or proof that the external tool/server is benign;
- the host still owns real execution and time-of-use controls.

Avoid claims such as:

- "AiNIR makes AI agents safe";
- "AiNIR solves hallucinations";
- "AiNIR verifies any generated program";
- "AiNIR replaces authorization, sandboxes, or policy engines";
- "a TrustReceipt proves the external side effect is safe".

## Launch sequence

1. Merge and re-check the public README rendering.
2. Apply the repository description and discovery topics recorded above.
3. Set `assets/ainir-social-preview.png` as the GitHub social preview.
4. Verify the minimal Quick Start from a clean environment.
5. Publish one problem-led launch post, not several simultaneous copies.
6. Watch questions and confusion points before rewriting the technical model.
7. Prefer real integration attempts, issues, and forks over star count alone when deciding what to improve next.

The goal is not to simplify AiNIR's architecture. The goal is to make the first useful idea visible before asking a reader to understand the architecture.
