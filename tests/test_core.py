from ratelattice import RateLattice, TokenBucket, combine_delays, parse_retry_after


def test_token_bucket_is_deterministic_with_injected_clock() -> None:
    bucket = TokenBucket(capacity=1, refill_per_second=1)
    assert bucket.allow(now=0).allowed
    blocked = bucket.allow(now=0)
    assert not blocked.allowed
    assert blocked.retry_after == 1
    assert bucket.allow(now=1).allowed


def test_lattice_reports_blocking_limits() -> None:
    lattice = RateLattice({"fast": TokenBucket(1, 1), "slow": TokenBucket(1, 0.5)})
    assert lattice.allow(now=0).allowed
    blocked = lattice.allow(now=0)
    assert blocked.blocked_by == ("fast", "slow")
    assert blocked.retry_after == 2


def test_rejected_lattice_request_does_not_consume_other_limits() -> None:
    lattice = RateLattice({"available": TokenBucket(2, 1), "blocked": TokenBucket(1, 1)})
    assert lattice.allow(now=0).allowed
    before = lattice.limits["available"].tokens
    blocked = lattice.allow(now=0)
    assert not blocked.allowed
    assert lattice.limits["available"].tokens == before


def test_invalid_lattice_cost_is_rejected() -> None:
    lattice = RateLattice({"api": TokenBucket(1, 1)})
    try:
        lattice.allow(0, now=0)
    except ValueError as error:
        assert str(error) == "cost must be positive"
    else:
        raise AssertionError("expected ValueError")


def test_retry_after_and_delay_composition() -> None:
    assert parse_retry_after("3") == 3
    assert parse_retry_after("not-a-date") is None
    assert combine_delays(None, -1, 2.5, 1) == 2.5
