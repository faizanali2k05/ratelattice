# ratelattice

Compose local rate limits with remote `Retry-After` signals and inspectable decisions.

```bash
python -m pip install ratelattice
```

```python
from ratelattice import RateLattice, TokenBucket, combine_delays, parse_retry_after

lattice = RateLattice({
    "per-second": TokenBucket(capacity=5, refill_per_second=5),
    "per-minute": TokenBucket(capacity=60, refill_per_second=1),
})

decision = lattice.allow()
if not decision.allowed:
    delay = combine_delays(decision.retry_after, parse_retry_after("2"))
    print(f"retry in {delay:.2f}s; blocked by {decision.blocked_by}")
```

`TokenBucket` supports deterministic clock injection through `now=`, which keeps policy tests fast and stable. `RateLattice` previews every configured limit before consuming any tokens, so a rejected multi-limit request does not partially consume an earlier limit. Both types are safe to use from multiple threads.

Use `preview()` when a caller needs to inspect a bucket without changing its state, and `reset()` to restore a bucket or lattice after a test or administrative reset.
