## Workflow Orchestration

 ### 1. Plan Mode Default
  - Enter Plan mode for ANY non-trivial task (3+ steps or architectural decisions).
  - If something goes sideways, STOP and re-plan immediately - don't keep pushing.
  - Use plan mode for verification steps, not just building.
  - Write detailed specs upfront to reduce ambiguity.

 ### 2. Subagent Strategy
  - Use subagents liberally to keep main context window clean.
  - offload research, exploration, and parallel analysis to subagents.
  - For complex problems, throw more compute at it via subagents.
  - One tack subagents for focused execution.

 ### 3. Self-Improvement
  - After ANY correction from user: update `tasks/lesson.md` with the pattern.
  - Write rules for yourself that prevents the same mistake.
  - Ruthlessly iterate on these lessons until mistake rate drops.
  - Review lesson at session start for relevant project.


 ### 4. Verification before done
  - Never mark a task complete without proving it works.
  - Diff behavior between main and your changes when relevant.
  - Ask yourself: "Would a staff engineer approve this?"
  - Run tests, check logs, demonstrate correctness.

 ### 5. Demand Elegance (Balanced)
  - For non-trivial changes: pause and ask "Is there a more elegant way?"
  - If a fix feels hacky: "Knowing everything I know now, implement the elegant solution."
  - Skip this simple, obvious fixes - don't over-engineer.
  - Challenge your own work before presenting it.


 ### 6. Autonomous Bug Fixing
  - When given a bug report: Just fix it, don't ask for hand-holding.
  - Point at logs, errors, failing tests - then resolve them
  - Zero context switching required from the user
  - Go fix failing CU tests without being told now.

## Task Management
 1. **Plan First**: Write plan to `tasks/todo.md` with checkable items.
 2. **Verify Plan**: Check in before starting implementation.
 3. **Track Progress**: Mark items complete as you go.
 4. **Explain Changes**: High-Level summary at each step.
 5. **Document Results**: Add review summary to `tasks/todo.md`.
 6. **Capture Lessons**: Update `tasks/lesson.md` for corrections.

## Core Principles
 - **Simplicity First**: Make every change as simple as possible. Impact minimal code.
 - **No Laziness**: Find root cause, No temporary fixes. Senior developer standards.
 - **Mindset Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
 - **Self-Improvement**: Learn from mistakes and update rules.


Before editing any file, read it first. Before modifying a function, grep for all callers. Research before you edit.