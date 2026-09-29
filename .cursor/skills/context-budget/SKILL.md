---
name: context-budget
description: Audits Cursor context overhead from skills, rules, AGENTS.md files, and MCP config. Use only when the user runs /context-budget.
disable-model-invocation: true
metadata:
  origin: ECC
---

<!-- Adapted from affaan-m/ECC@d3b8a3e skills/context-budget (MIT, © 2026 Affaan Mustafa). See .cursor/skills/THIRD_PARTY_NOTICES.md -->

# Context budget

Manual audit. Run it when the user invokes `/context-budget`, not on your own.

Estimate tokens as words × 1.3 for prose, and characters ÷ 4 for code-heavy files. Count each MCP tool schema as about 500 tokens.

## Inventory

| Path | Flag when |
|---|---|
| `.cursor/skills/*/SKILL.md` | one file is over 400 lines |
| `.cursor/rules/*.mdc` | one file is over 100 lines; call out every `alwaysApply: true` |
| `AGENTS.md` and `CLAUDE.md` at the root and in subdirectories | the chain together is over 300 lines |
| `.cursor/mcp.json` | more than 10 servers, or more than 20 tools in total |

Skip a second copy of a skill when the file contents match, so it is not counted twice.

## Classify

| Bucket | Meaning | Action |
|---|---|---|
| Always needed | Named by the root `AGENTS.md`, or required for the current task | Keep |
| Sometimes needed | Domain-specific and not always loaded | Leave it as a skill that loads on trigger |
| Rarely needed | Overlaps another file, or does not match this repo | Remove it, or stop applying it |

## Steps

1. List the files in the inventory table. Record line counts. Do not read large JSON or generated locale files while counting.
2. Apply the flags above. A rule with `alwaysApply: true` is loaded every turn, so treat it as more expensive than its line count.
3. Sort each file into a bucket. A skill that repeats `AGENTS.md` or `docs/INDEX.md` is redundant.
4. Write the report below. Do not add a `.cursor/rules` file or set `alwaysApply` as part of this audit.

## Report

```
Context budget
skills: N files, M flagged (>400 lines)
rules:  N files, M flagged (>100 lines); alwaysApply: …
AGENTS: N files, chain lines … (>300 is a warning)
mcp:    servers …, tools … (>10 servers or >20 tools is a warning)
```

List each flagged path with its line count. Then give the top three cuts and a rough token saving. Rank MCP first: one extra tool schema costs more than a short skill. After a skill, rule, or MCP server is added, run this audit again.

## What not to flag

- A skill under 400 lines that loads only when its description matches is already cheap. Do not move it into an always-on rule.
- `docs/INDEX.md` is the map agents read on purpose. Do not split it to chase a lower line count unless it passes 120 lines.
- Generated locale files and `index/*.json` are data, not context config. Leave them out of this report.
- Do not recommend copying a short skill into the root `AGENTS.md`. That file is loaded every turn; the skill is not.

## Example cut

A 12-tool MCP server is about 6,000 tokens of schema before any result comes back. One 70-line skill is a few hundred tokens, and only after it is triggered. Prefer deleting an unused server over shortening a skill that is already under 400 lines.
