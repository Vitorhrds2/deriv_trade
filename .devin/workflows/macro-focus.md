---
description: How to approach new hypotheses and trading strategy exploration in this workspace
auto_execution_mode: 3
---

# Macro Focus Rules for This Workspace

## Core Philosophy

1. **Result > Theory**: An "accident" that makes money is as valid as a strategy with theoretical edge. Never dismiss a profit-generating mechanism just because it wasn't intentional.
2. **No absolute guarantees required**: The user accepts directional risk. Guardrails manage risk, they don't enforce conventional trading theory.
3. **Think outside the box**: Standard trading rules don't apply here. The goal is enrichment through financial automations, not academic validation.
4. **$52 test**: If a strategy can take, for example, $52 real deposit, withdraw $52, and still have open upside — it's worth pursuing.

## When Investigating a Discovery

1. **Verify the profit is real** — check via API, calculate manually if needed (entry spot vs current spot × multiplier)
2. **Understand the mechanism** — what exactly caused the profit? Was it market direction, platform behavior, rate limiting, or a bug?
3. **Don't dismiss as "luck"** — luck that makes money is worth studying. The question is: can it be repeated?
4. **Identify exploitable patterns** — is the mechanism a platform quirk? An API limitation? A structural feature?
5. **Document as a hypothesis** — create `docs/dXX-name.md` with full details

## When Building a Prototype

1. **Start from the accidental mechanism** — replicate what happened naturally
2. **Intentionalize the "bug"** — if rate limiting helped, build the "hold winners" behavior intentionally
3. **Test on Demo first** — always validate on Demo before real capital
4. **Define guardrails** — max stake, max positions, stop-loss, capital limits
5. **Monitor continuously** — track profit over time, understand when/why positions close

## What NOT to Do

- Do NOT dismiss discoveries as "directional luck" or "not edge"
- Do NOT recommend stopping bots that are generating profit
- Do NOT insist on academic validation before proceeding
- Do NOT apply standard trading theory as a filter for what's worth exploring
- Do NOT forget to check memory for perpetual winner holding context when working on multiplier strategies

## Reference Documents

- Memory: search for "perpetual winner holding" for full context on the Deriv multiplier strategy discovery
- Memory tags: `perpetual`, `winner-holding`, `deriv`, `strategy` — search these for context
