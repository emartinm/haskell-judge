"""Client of haskell-test-executor (HTTP over its Unix socket).

    result = executor.run(student_code, definitions=..., tests=[...], extensions=[...], limits={...})

returns the JSON response of POST /run (see the executor README). Failures of the
service itself are raised as exceptions so that they are never stored as a verdict.
"""

import httpx
from django.conf import settings

# Transport used instead of the socket (tests replace it with httpx.MockTransport)
_transport: httpx.BaseTransport | None = None


class ExecutorError(Exception):
    """The executor could not evaluate the request."""


class ExecutorUnavailable(ExecutorError):
    """The executor is stopped, restarting or did not answer in time."""


class ExecutorBusy(ExecutorError):
    """The executor queue is full (HTTP 503)."""


class ExecutorRejected(ExecutorError):
    """The executor rejected the request as invalid (HTTP 400/422): a problem misconfiguration."""


def set_transport(transport: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = transport


def _client() -> httpx.Client:
    transport = _transport or httpx.HTTPTransport(uds=settings.EXECUTOR_SOCKET)
    return httpx.Client(transport=transport, base_url="http://haskell-test-executor", timeout=settings.EXECUTOR_TIMEOUT)


def run(student_code: str, *, tests: list[dict], definitions: str = "", extensions=(), limits=None) -> dict:
    """Evaluates student_code against the tests and returns the executor response."""
    payload = {
        "student_code": student_code,
        "definitions": definitions,
        "tests": tests,
        "extensions": list(extensions),
        "limits": limits or {},
    }
    try:
        with _client() as client:
            response = client.post("/run", json=payload)
    except httpx.TransportError as e:
        raise ExecutorUnavailable(str(e)) from e
    if response.status_code == 503:
        raise ExecutorBusy(response.text)
    if response.status_code in (400, 422):
        raise ExecutorRejected(response.text)
    if response.status_code != 200:
        raise ExecutorUnavailable(f"HTTP {response.status_code}: {response.text}")
    return response.json()


def run_problem(problem, student_code: str, *, reveal_hidden: bool = False) -> dict:
    """Evaluates student_code against the tests of a problem.

    With reveal_hidden every test is sent as visible, so that the response shows
    the details of any failure (used to validate the teacher's solution).
    """
    tests = [t.as_executor_test() for t in problem.tests.all()]
    if reveal_hidden:
        tests = [{**t, "hidden": False} for t in tests]
    return run(
        student_code,
        tests=tests,
        definitions=problem.definitions,
        extensions=problem.extensions,
        limits=problem.executor_limits(),
    )


def health() -> dict:
    """GET /health of the executor."""
    try:
        with _client() as client:
            response = client.get("/health")
    except httpx.TransportError as e:
        raise ExecutorUnavailable(str(e)) from e
    return response.json()
