from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from judge.models import Collection, Problem, Submission
from judge.types import Verdict

from .helpers import JudgeTestCase, make_zip, problem_files

WRONG = {
    "status": "WRONG_ANSWER",
    "passed": 0,
    "total": 1,
    "test": {"index": 1, "expr": "total []", "expected": "0", "obtained": "1"},
}


class AdminTestCase(JudgeTestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.user("profe", staff=True)
        self.client.force_login(self.teacher)
        self.collection_ = self.collection(author=self.teacher)


class ProblemAdminTest(AdminTestCase):
    def post_problem(self, solution="total = sum", tests=(("total []", "0", "on"),), **extra):
        data = {
            "collection": self.collection_.pk,
            "position": 1,
            "definitions": "",
            "template": "",
            "solution": solution,
            "extensions": ["LambdaCase"],
            "statements-TOTAL_FORMS": 1,
            "statements-INITIAL_FORMS": 0,
            "statements-MIN_NUM_FORMS": 1,
            "statements-MAX_NUM_FORMS": 1000,
            "statements-0-language": "es",
            "statements-0-title": "Suma",
            "statements-0-text_md": "Define `total`.",
            "tests-TOTAL_FORMS": len(tests),
            "tests-INITIAL_FORMS": 0,
            "tests-MIN_NUM_FORMS": 1,
            "tests-MAX_NUM_FORMS": 1000,
            **extra,
        }
        for i, (expr, expected, hidden) in enumerate(tests):
            data.update({f"tests-{i}-position": i + 1, f"tests-{i}-expr": expr, f"tests-{i}-expected": expected})
            if hidden:
                data[f"tests-{i}-hidden"] = hidden
        return self.client.post(reverse("admin:judge_problem_add"), data)

    def test_valid_problem_is_saved(self):
        response = self.post_problem(heap_mb=300)
        self.assertEqual(response.status_code, 302)
        problem = Problem.objects.get()
        self.assertEqual((problem.author, problem.extensions, problem.heap_mb), (self.teacher, ["LambdaCase"], 300))
        request = self.executor.requests[0]
        self.assertEqual(request["tests"], [{"expr": "total []", "expected": "0", "hidden": False}])
        self.assertEqual((request["limits"], request["extensions"]), ({"heap_mb": 300}, ["LambdaCase"]))
        self.assertContains(self.client.get(reverse("admin:judge_problem_changelist")), "Suma")

    def test_wrong_solution_is_rejected(self):
        self.executor.queue(WRONG)
        response = self.post_problem(solution="total = length")
        self.assertContains(response, "no supera los tests")
        self.assertFalse(Problem.objects.exists())

    def test_solution_is_not_validated_if_the_problem_is_invalid(self):
        response = self.post_problem(heap_mb=1)  # out of range
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.executor.requests, [])

    def test_tests_are_required(self):
        response = self.post_problem(tests=[])
        self.assertEqual(response.status_code, 200)
        tests_formset = response.context["inline_admin_formsets"][1].formset
        self.assertTrue(tests_formset.non_form_errors())  # min_num = 1
        self.assertFalse(Problem.objects.exists())
        self.assertEqual(self.executor.requests, [])


class CollectionAdminTest(AdminTestCase):
    def post_collection(self, zip_bytes=None):
        data = {"name": "Recursión", "description_md": "", "position": 1, "visible": "on"}
        if zip_bytes is not None:
            data["problems_zip"] = SimpleUploadedFile("problems.zip", zip_bytes)
        return self.client.post(reverse("admin:judge_collection_add"), data)

    def test_collection_with_problems_from_zip(self):
        outer = make_zip({"a.zip": make_zip(problem_files()), "b.zip": make_zip(problem_files())})
        response = self.post_collection(outer)
        self.assertEqual(response.status_code, 302)
        collection = Collection.objects.get(name="Recursión")
        self.assertEqual((collection.author, collection.problems.count()), (self.teacher, 2))
        self.assertEqual(len(self.executor.requests), 2)
        response = self.client.get(reverse("admin:judge_collection_changelist"))
        self.assertContains(response, "Recursión")

    def test_invalid_problems_are_not_imported(self):
        self.executor.queue(WRONG)
        response = self.post_collection(
            make_zip({"a.zip": make_zip(problem_files()), "b.zip": make_zip(problem_files())})
        )
        self.assertContains(response, "a.zip: La solución de referencia no supera los tests")
        self.assertFalse(Collection.objects.filter(name="Recursión").exists())

    def test_collection_without_zip(self):
        self.assertEqual(self.post_collection().status_code, 302)
        self.assertEqual(Collection.objects.get(name="Recursión").problems.count(), 0)


class SubmissionAdminTest(AdminTestCase):
    def test_read_only(self):
        problem = self.problem(self.collection_)
        submission = Submission.objects.create(user=self.teacher, problem=problem, code="x", verdict=Verdict.AC)
        self.assertContains(self.client.get(reverse("admin:judge_submission_changelist")), "Suma")
        self.assertEqual(self.client.get(reverse("admin:judge_submission_add")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("admin:judge_submission_change", args=[submission.pk])).status_code, 200
        )
