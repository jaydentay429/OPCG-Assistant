---
name: strategic-compact
description: Wraps up a Cursor session at phase boundaries. Use when a long task is near the context limit and research, planning, debugging, or a failed approach has just finished.
metadata:
  origin: ECC
---

<!-- Adapted from affaan-m/ECC@d3b8a3e skills/strategic-compact (MIT, © 2026 Affaan Mustafa). See .cursor/skills/THIRD_PARTY_NOTICES.md -->

# Strategic compact

At a phase boundary, write the plan to a file, then summarize the current state into `docs/` or the task file and start a new session (or let Cursor summarize). Do not stop in the middle of an implementation.

## Phase transitions

| Transition | Wrap up? | Why |
|---|---|---|
| Research → planning | Yes | Research is bulky; the plan is what should remain |
| Planning → implementation | Yes | The plan is already in a file; free the window for code |
| Implementation → testing | Maybe | Stay if the tests refer to the code just written |
| Debugging → next feature | Yes | Debug traces crowd out the next task |
| Mid-implementation | No | Paths, names, and partial edits are still needed |
| After a failed approach | Yes | Clear the dead end before trying another approach |

## Write the plan first

A chat summary is not the record. Before ending the session:

1. Write the plan, decisions, open questions, and the next step into `docs/` or the task file.
2. Name the files already changed and the check that should be run next.
3. Commit work that should survive.
4. Start a new session, or let Cursor summarize. The next session reads the file.

## Duplicate instructions

The same rule in two places wastes the window and drifts:

- Root `AGENTS.md` copied into a nested `AGENTS.md`
- A skill that restates `AGENTS.md` or `docs/INDEX.md`
- Overlapping `.cursor/rules/*.mdc` and `.cursor/skills/*/SKILL.md`

Keep one copy. Point the other file at it. Nested `AGENTS.md` files should not repeat the root sync table.

If two instructions disagree, follow `docs/INDEX.md` and the nearest `AGENTS.md`, then delete or shorten the duplicate.

## What the next session can see

Files on disk, git commits, and `docs/` or the task file survive. Chat reasoning, earlier file reads, and tool output do not. If it matters, it belongs in the file written in the step above.
