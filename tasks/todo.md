# Todo

Current task planning goes here. Each session creates a new section.

---

## Template
**Goal**: [what we're building]

### Plan
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

### Review
- Result: [what was done]
- Tests: [passed/failed]
- Notes: [anything notable]

---

## Backlog (future improvements)
- [ ] **Opposing position guard per TF**: Currently a long and short on the same TF can both be open simultaneously (e.g. 30m long at 75,650 and 30m short at 75,350). Consider adding a rule in `_execute_entry` to skip a new signal if there is already an open position in the opposite direction on the same TF. Decision: keep current behavior for now, revisit later.
