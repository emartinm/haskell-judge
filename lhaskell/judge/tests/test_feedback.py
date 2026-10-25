from django.test import SimpleTestCase

from judge import feedback
from judge.types import Verdict

GHC_ERROR = """\
solution.hs:3:29: error: [GHC-83865]
    • Couldn't match expected type ‘Int’ with actual type ‘Bool’
  |
3 | total (x:xs) = x + total xs + True
  |                             ^^^^

solution.hs:(5,1)-(6,10): error: [GHC-62161]
    Pattern match(es) are non-exhaustive
solution.hs:7:1-4: warning: something"""


class SummaryTest(SimpleTestCase):
    def test_every_verdict(self):
        cases = [
            (Verdict.AC, {"total": 1}, "Tu solución supera el único test."),
            (Verdict.AC, {"total": 3}, "Tu solución supera los 3 tests."),
            (Verdict.WA, {"total": 3, "test": {"index": 2}}, "Tu solución falla el test 2 de 3."),
            (Verdict.CE, {"source": "student"}, "Tu solución no compila."),
            (Verdict.CE, {"source": "tests", "test": {"index": 4}}, "Tu solución no es compatible con el test 4"),
            (Verdict.RE, {"total": 3, "test": {"index": 1}}, "Error en ejecución en el test 1 de 3."),
            (
                Verdict.TLE,
                {"test": {"index": 1, "reason": "allocation"}},
                "El test 1 ha excedido el límite de cálculo: tu solución hace demasiado trabajo.",
            ),
            (Verdict.TLE, {"test": {"index": 2, "reason": "cpu"}}, "El test 2 ha hecho que se agote el tiempo total"),
            (Verdict.TLE, {"test": {"index": 2, "reason": "wall"}}, "El test 2 ha hecho que se agote el tiempo total"),
            (Verdict.TLE, {"test": {"index": 1, "reason": "timeout"}}, "El test 1 ha excedido el tiempo límite."),
            (Verdict.TLE, {"test": {"index": 1}}, "El test 1 ha excedido el tiempo límite."),
            (Verdict.MLE, {"test": {"index": 2}}, "El test 2 ha excedido la memoria"),
            (Verdict.IE, {}, "error interno"),
        ]
        for verdict, result, text in cases:
            with self.subTest(verdict=verdict, result=result):
                self.assertIn(text, feedback.summary(verdict, result))


class MessageTest(SimpleTestCase):
    def test_codes_are_localized(self):
        cases = {
            "pragma_not_allowed": "Línea 2: no se permiten pragmas",
            "module_declaration_not_allowed": "Línea 2: no incluyas la declaración 'module'",
            "hidden_test_type_mismatch": "test oculto",
            "compile_limits_exceeded": "límites de tiempo o memoria",
            "program_crashed": "terminó de forma inesperada",
            "internal_error": "Error interno del juez",
        }
        for code, text in cases.items():
            with self.subTest(code=code):
                self.assertIn(text, feedback.message({"code": code, "line": 2, "message": "English default"}))

    def test_without_code_the_executor_message_is_kept(self):
        self.assertIsNone(feedback.message_for_code({"message": "GHC says"}))
        self.assertEqual(feedback.message({"message": "GHC says"}), "GHC says")
        self.assertEqual(feedback.message({}), "")


class DiagnosticsTest(SimpleTestCase):
    def test_compilation_errors(self):
        diags = feedback.diagnostics({"status": "COMPILATION_ERROR", "source": "student", "message": GHC_ERROR})
        self.assertEqual(
            [(d["from"], d["to"], d["severity"]) for d in diags],
            [([3, 29], [3, 30], "error"), ([5, 1], [6, 11], "error"), ([7, 1], [7, 5], "warning")],
        )
        self.assertTrue(diags[0]["message"].startswith("solution.hs:3:29: error"))
        self.assertTrue(diags[0]["message"].endswith("^^^^"))

    def test_runtime_error_location(self):
        result = {"status": "RUNTIME_ERROR", "test": {"exception": "solution.hs:2:1-25: Non-exhaustive patterns"}}
        self.assertEqual(feedback.diagnostics(result)[0]["from"], [2, 1])

    def test_no_diagnostics(self):
        for result in [
            {"status": "OK"},
            {"status": "COMPILATION_ERROR", "source": "tests", "message": "tests:2:3: error"},
            {"status": "COMPILATION_ERROR", "source": "student", "code": "pragma_not_allowed", "message": "x"},
            {"status": "RUNTIME_ERROR", "test": {"hidden": True}},
        ]:
            self.assertEqual(feedback.diagnostics(result), [])
