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
- [ ] **Multi-broker support**: Currently only Coinbase Advanced Trade is supported. Add support for additional brokers (e.g. Bybit, Binance Futures). Abstract the executor layer behind a `BrokerAdapter` interface so brokers are pluggable without touching scanner logic.
- [ ] In Settings screen Move Broker section to top and default is set to empty. Once user selectes one from the broker dropdown then show the fields to add theier api key. Also add a link its official link to fetch api's keys. and step if possible.
- [ ] Remove this text.
- [ ] Now Coinbase Exchange and Coinbase Credentials are been shown all the time remove those. 
- [ ] For Coinbase the Contract Size (BTC) is set to 0.002 what about other broker which are already implemented.
- [ ] XM, Vantage, and Pepperstone are MT4/MT5 brokers Need to look for these broker as well.
