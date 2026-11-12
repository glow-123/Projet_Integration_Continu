"""Mécanisme de RETRY générique (utilisé pour la base et pour le S3).

retry() :
  - détecte l'échec (exceptions listées dans `retry_on`) ;
  - affiche clairement l'erreur rencontrée ;
  - attend avant une nouvelle tentative (délai multiplié par `backoff`) ;
  - effectue plusieurs tentatives, jusqu'à `max_attempts` au maximum ;
  - au-delà, lève RetryError (la pipeline s'arrête alors proprement).
Les exceptions NON listées (ex : CSV invalide) ne sont pas retentées.
"""
import sys
import time


class RetryError(RuntimeError):
    """Nombre maximal de tentatives dépassé."""

    def __init__(self, label, attempts, last_error):
        super().__init__(
            f"{label} : échec après {attempts} tentative(s). Dernière erreur : {last_error}"
        )
        self.attempts = attempts
        self.last_error = last_error


def retry(func, *, label, retry_on, max_attempts=3, delay=1.0, backoff=2.0,
          sleep=time.sleep, log=None):
    """Appelle func() et la relance en cas d'échec transitoire."""
    if max_attempts < 1:
        raise ValueError("max_attempts doit être >= 1")
    log = log or (lambda msg: print(msg, file=sys.stderr))
    wait = delay
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on as exc:
            log(f"[retry] {label} : tentative {attempt}/{max_attempts} échouée -> "
                f"{type(exc).__name__}: {exc}")
            if attempt == max_attempts:
                raise RetryError(label, attempt, exc) from exc
            log(f"[retry] {label} : nouvelle tentative dans {wait:.1f}s")
            sleep(wait)
            wait *= backoff


def fail_first_calls(func, n_failures, make_error):
    """SIMULATION d'une panne temporaire : les n premiers appels lèvent make_error().

    Sert à démontrer le retry (option --simulate-*-failures de la pipeline).
    """
    state = {"remaining": n_failures}

    def wrapper(*args, **kwargs):
        if state["remaining"] > 0:
            state["remaining"] -= 1
            raise make_error()
        return func(*args, **kwargs)

    return wrapper
