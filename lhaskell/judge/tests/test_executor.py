import httpx

from judge import executor

from .helpers import JudgeTestCase


class ExecutorClientTest(JudgeTestCase):
    def test_run_sends_the_request(self):
        result = executor.run("f = 1", tests=[{"expr": "f", "expected": "1"}], definitions="d", extensions=["GADTs"])
        self.assertEqual(result["status"], "OK")
        self.assertEqual(
            self.executor.requests[0],
            {
                "student_code": "f = 1",
                "definitions": "d",
                "tests": [{"expr": "f", "expected": "1"}],
                "extensions": ["GADTs"],
                "limits": {},
            },
        )

    def test_errors(self):
        self.executor.queue(httpx.ConnectError("no socket"), 503, 400, 422, 500, httpx.ReadTimeout("slow"))
        expected = [
            executor.ExecutorUnavailable,
            executor.ExecutorBusy,
            executor.ExecutorRejected,
            executor.ExecutorRejected,
            executor.ExecutorUnavailable,
            executor.ExecutorUnavailable,
        ]
        for error in expected:
            with self.assertRaises(error):
                executor.run("f = 1", tests=[])

    def test_run_problem(self):
        problem = self.problem(self.collection(), heap_mb=100, extensions=["LambdaCase"], definitions="data T = T")
        executor.run_problem(problem, "code")
        executor.run_problem(problem, "code", reveal_hidden=True)
        hidden_flags = [[t["hidden"] for t in r["tests"]] for r in self.executor.requests]
        self.assertEqual(hidden_flags, [[False, True], [False, False]])
        self.assertEqual(self.executor.requests[0]["limits"], {"heap_mb": 100})
        self.assertEqual(self.executor.requests[0]["definitions"], "data T = T")

    def test_health(self):
        self.executor.queue({"status": "ok", "ghc": "9.10.3"}, httpx.ConnectError("down"))
        self.assertEqual(executor.health()["ghc"], "9.10.3")
        self.assertEqual(self.executor.requests[0], "/health")
        with self.assertRaises(executor.ExecutorUnavailable):
            executor.health()

    def test_default_transport_uses_the_socket(self):
        executor.set_transport(None)
        with (
            self.settings(EXECUTOR_SOCKET="/nonexistent/executor.sock"),
            self.assertRaises(executor.ExecutorUnavailable),
        ):
            executor.run("f = 1", tests=[])
