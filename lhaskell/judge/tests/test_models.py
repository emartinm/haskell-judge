from django.core.exceptions import ValidationError
from django.utils import translation

from judge.markdown import markdown_to_html
from judge.models import ProblemTest, Statement, Submission, validate_single_line
from judge.types import Verdict

from .helpers import JudgeTestCase


class MarkdownTest(JudgeTestCase):
    def test_renders_and_sanitizes(self):
        html = markdown_to_html(
            "**hola** <script>alert(1)</script> <a href='x' onclick='y'>l</a>\n\n```haskell\nf = 1\n```"
        )
        self.assertIn("<strong>hola</strong>", html)
        self.assertNotIn("script", html)
        self.assertNotIn("onclick", html)
        self.assertIn('<code class="language-haskell">', html)

    def test_collection_and_statement_render_on_save(self):
        collection = self.collection()
        collection.description_md = "*x*"
        collection.save()
        self.assertEqual(collection.description_html, "<p><em>x</em></p>")
        problem = self.problem(collection)
        self.assertEqual(problem.statements.get().text_html, "<p>Define <code>total</code>.</p>")


class ProblemTest_(JudgeTestCase):
    def test_statement_language_fallback(self):
        problem = self.problem(self.collection(), title="Suma")
        Statement.objects.create(problem=problem, language="en", title="Sum", text_md="Define it.")
        self.assertEqual(problem.title("en"), "Sum")
        self.assertEqual(problem.title("fr"), "Suma")  # default language
        with translation.override("en"):
            self.assertEqual(problem.title(), "Sum")
        problem.statements.filter(language="es").delete()
        self.assertEqual(problem.title("fr"), "Sum")  # any statement
        problem.statements.all().delete()
        self.assertEqual(problem.title(), f"#{problem.pk}")
        self.assertIsNone(problem.statement())

    def test_executor_limits_only_set_ones(self):
        problem = self.problem(self.collection(), heap_mb=300, run_time_s=5)
        self.assertEqual(problem.executor_limits(), {"heap_mb": 300, "run_time_s": 5})

    def test_str(self):
        collection = self.collection(name="Listas")
        problem = self.problem(collection, title="Suma")
        test = problem.tests.first()
        user = self.user("ana")
        submission = Submission.objects.create(user=user, problem=problem, code="x", verdict=Verdict.AC)
        self.assertEqual(
            [str(collection), str(problem), str(problem.statements.get()), str(test), str(submission)],
            ["Listas", "Suma", "Suma (es)", "total [] == 0", f"{submission.pk} (AC)"],
        )
        self.assertEqual(submission.verdict_enum, Verdict.AC)
        self.assertEqual(test.as_executor_test(), {"expr": "total []", "expected": "0", "hidden": False})

    def test_single_line_validator(self):
        validate_single_line("f 1")
        with self.assertRaises(ValidationError):
            validate_single_line("f\n1")
        test = ProblemTest(problem=self.problem(self.collection()), expr="f\r1", expected="1")
        with self.assertRaises(ValidationError):
            test.full_clean()


class VerdictTest(JudgeTestCase):
    def test_from_executor(self):
        self.assertEqual(Verdict.from_executor("OK"), Verdict.AC)
        self.assertEqual(Verdict.from_executor("MEMORY_LIMIT"), Verdict.MLE)
        self.assertEqual(Verdict.from_executor("SOMETHING_NEW"), Verdict.IE)
        self.assertEqual({v.css_class for v in Verdict} - {""}, {v.css_class for v in Verdict})
