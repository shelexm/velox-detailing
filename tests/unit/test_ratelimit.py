import pytest

from app.core.errors import RateLimitedError
from app.core.ratelimit import Limiters, RateLimiter


def test_blocks_after_the_limit_and_frees_after_the_window() -> None:
    limiter = RateLimiter(2, 60)
    limiter.check("a", now=0)
    limiter.check("a", now=1)
    with pytest.raises(RateLimitedError):
        limiter.check("a", now=2)
    limiter.check("a", now=61.5)  # the first two hits left the window


def test_checking_a_key_never_creates_it() -> None:
    limiter = RateLimiter(2, 60)
    for index in range(100):
        assert not limiter.is_blocked(f"probe-{index}", now=0)
    assert limiter._hits == {}


def test_idle_keys_are_forgotten_so_unique_keys_cannot_grow_memory() -> None:
    limiter = RateLimiter(5, 60, max_keys=100)
    for index in range(500):
        limiter.hit(f"ip-{index}", now=index * 0.01)  # all inside one window: nothing to forget yet
    assert len(limiter._hits) == 500
    limiter.hit("late", now=1000)  # far later: every older key is idle and goes
    assert set(limiter._hits) == {"late"}


def test_one_address_cannot_lock_an_account_for_everyone() -> None:
    limiters = Limiters()
    attacker, owner = "owner@velox.test|203.0.113.7", "owner@velox.test|198.51.100.4"
    for _ in range(5):
        limiters.login_by_email_and_ip.hit(attacker)
        limiters.login_by_email.hit("owner@velox.test")
    assert limiters.login_by_email_and_ip.is_blocked(attacker)
    assert not limiters.login_by_email_and_ip.is_blocked(owner)
    assert not limiters.login_by_email.is_blocked("owner@velox.test")  # the account-wide limit is higher
