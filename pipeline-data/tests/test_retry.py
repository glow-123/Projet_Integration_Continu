import pytest

from retry import RetryError, fail_first_calls, retry


class Transient(Exception):
    pass


def run(func, **kwargs):
    """retry() sans vraie attente : on enregistre les délais demandés."""
    waits, logs = [], []
    params = dict(label="test", retry_on=(Transient,), max_attempts=3, delay=1.0,
                  sleep=waits.append, log=logs.append)
    params.update(kwargs)
    return retry(func, **params), waits, logs


def test_success_first_try_does_not_wait():
    result, waits, logs = run(lambda: "ok")
    assert result == "ok" and waits == [] and logs == []


def test_succeeds_after_temporary_failures_with_backoff():
    flaky = fail_first_calls(lambda: "ok", 2, lambda: Transient("panne"))
    result, waits, logs = run(flaky, max_attempts=3)
    assert result == "ok"
    assert waits == [1.0, 2.0]  # attente avant chaque nouvelle tentative, x2
    assert "tentative 1/3" in logs[0] and "panne" in logs[0]


def test_gives_up_after_max_attempts_with_clear_error():
    calls = []

    def always_fails():
        calls.append(1)
        raise Transient("base injoignable")

    waits = []
    with pytest.raises(RetryError, match="échec après 3 tentative.*base injoignable") as info:
        retry(always_fails, label="insert", retry_on=(Transient,), max_attempts=3,
              delay=0.5, sleep=waits.append, log=lambda m: None)
    assert len(calls) == 3 and waits == [0.5, 1.0]
    assert isinstance(info.value.last_error, Transient)


def test_non_transient_error_is_not_retried():
    calls = []

    def bug():
        calls.append(1)
        raise ValueError("CSV invalide")

    with pytest.raises(ValueError):
        run(bug)
    assert len(calls) == 1
