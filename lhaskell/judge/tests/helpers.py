"""Test helpers: a simulated haskell-test-executor and factories of test data."""

import io
import json
import zipfile

import httpx
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from judge import executor
from judge.models import Collection, Problem, ProblemTest, Statement

OK = {"status": "OK", "passed": 2, "total": 2}


class FakeExecutor:
    """Replaces the executor socket. Each request gets the next queued response
    (a dict is returned as JSON with HTTP 200; an int is an HTTP status; an exception
    is raised); when the queue is empty, it answers OK."""

    def __init__(self):
        self.responses = []
        self.requests = []

    def queue(self, *responses):
        self.responses.extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content) if request.content else request.url.path)
        response = self.responses.pop(0) if self.responses else OK
        if isinstance(response, Exception):
            raise response
        if isinstance(response, int):
            return httpx.Response(response, json={"detail": f"HTTP {response}"})
        return httpx.Response(200, json=response)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], AXES_VERBOSE=False)
class JudgeTestCase(TestCase):
    """TestCase with a simulated executor (self.executor) and some data factories.
    It uses a fast password hasher: the real one dominates the test time."""

    def setUp(self):
        self.executor = FakeExecutor()
        executor.set_transport(httpx.MockTransport(self.executor.handler))
        self.addCleanup(executor.set_transport, None)

    @staticmethod
    def user(username, staff=False, groups=()):
        user = get_user_model().objects.create_user(
            username, f"{username}@ucm.es", "password-123", is_staff=staff, is_superuser=staff
        )
        for name in groups:
            user.groups.add(Group.objects.get_or_create(name=name)[0])
        return user

    @staticmethod
    def collection(name="Listas", visible=True, author=None, position=1):
        return Collection.objects.create(name=name, visible=visible, author=author, position=position)

    @staticmethod
    def problem(collection, title="Suma", tests=(("total []", "0", False), ("total [1,2,3]", "6", True)), **fields):
        fields.setdefault("solution", "total :: [Int] -> Int\ntotal = sum\n")
        problem = Problem.objects.create(collection=collection, **fields)
        Statement.objects.create(problem=problem, language="es", title=title, text_md="Define `total`.")
        for i, (expr, expected, hidden) in enumerate(tests, start=1):
            ProblemTest.objects.create(problem=problem, position=i, expr=expr, expected=expected, hidden=hidden)
        return problem


def make_zip(files: dict) -> bytes:
    """ZIP with {name: str | bytes}."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buffer.getvalue()


def problem_files(**overrides) -> dict:
    """Files of a valid problem ZIP; overrides replace (or with None, remove) files."""
    files = {
        "problem.json": json.dumps({"title": "Suma", "position": 2, "extensions": ["LambdaCase"]}),
        "statement.md": "Define `total :: [Int] -> Int`.",
        "solution.hs": "total :: [Int] -> Int\ntotal = sum\n",
        "template.hs": "total :: [Int] -> Int\ntotal = undefined\n",
        "tests.json": json.dumps(
            [{"expr": "total []", "expected": "0"}, {"expr": "total [1]", "expected": "1", "hidden": True}]
        ),
    }
    files.update(overrides)
    return {k: v for k, v in files.items() if v is not None}
