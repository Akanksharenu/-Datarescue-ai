# Demo script (5 minutes)

Everything shown is simulated data. Nothing here represents real customers or real money.

## Setup (before the demo)

```powershell
docker compose up --build
```

Wait for `backend` to log `Application startup complete`, then open http://localhost:5173.

## 1. The problem (30 seconds)

"A retail pipeline copies payment transactions into report tables. When it silently drops rows,
yesterday's raw total says $255,052 and the revenue report says $184,000. Nobody notices until
finance asks. DataRescue detects that, explains it, and lets a person approve a safe fix."

## 2. Seed and break it (1 minute)

1. **Demo control** → **Reset and seed**. Point at the green box: 1,000 transactions, expected
   total shown in dollars but stored as integer cents.
2. **Run missing**. The transformation dropped 280 rows. Click **Open incident #1**.

## 3. Detect (1 minute)

On the incident page:

- Evidence: raw 1,000 rows, processed 720, shortfall in cents, the first missing IDs.
- Lineage: `payment_source → raw` is green, `process_batch` is marked failed, everything
  downstream is red. "The revenue report cannot be trusted; the raw copy can."
- Say: "This came from SQL checks comparing raw and processed. No AI was involved in deciding
  that something is wrong."

## 4. Investigate (1 minute)

Click **Investigate (auto)**.

- Badge says `rules` (or `LLM: <model>` if a key is configured). Likely cause, confidence,
  what the evidence cannot establish, the evidence paths it cites, next steps for a human.
- Say: "The investigator only reads the evidence JSON. It cannot touch the database. If a model
  cites evidence that does not exist, the claim is listed as unsupported."

## 5. Approve and recover (1.5 minutes)

1. **Propose recovery**. Show the plan: replay the batch, 280 expected inserts, five
   preconditions all green.
2. **Try execute without approval**. Red 409 error; "Refused execution attempts" appears below.
   Say: "Refusals are recorded as failed pipeline runs. The audit trail shows the attempt."
3. Type your name, **Approve**, then **Execute replay**.
4. Proof: 720 → 1,000 rows, totals match to the cent, six checks green, incident **resolved**.
5. **Execute again**. Inserted this run: 0. "Replay is idempotent. Running it twice cannot
   double-count revenue."

## 6. The other two failures (30 seconds, optional)

- **Run duplicate**: the database's unique constraint rejected all 40 re-sent rows; the incident
  is a warning, lineage shows "at risk" not "affected", and recovery is refused with the reason
  "processed data is intact".
- **Run schema**: the source renamed `amount_cents` to `amount`; nothing loaded, the incident
  names both fields, and recovery says a corrected extract is needed, not a replay.

## Closing line

"Detect with SQL, explain with rules or AI but label which, approve with a named person, recover
idempotently, verify with the same SQL. The AI never writes to the database."
