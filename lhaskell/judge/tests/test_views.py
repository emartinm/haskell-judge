import io

import httpx
import psycopg
from django.contrib.auth.models import Group
from django.db import connection
from django.urls import reverse
from pyexcel_ods3 import get_data

from judge.models import Submission
from judge.types import Verdict
from judge.views import SUBMISSION_LOCK

from .helpers import JudgeTestCase

TOTAL = "total :: [Int] -> Int\ntotal = sum\n"


class ViewsTestCase(JudgeTestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.user("profe", staff=True, groups=["A"])
        self.ana = self.user("ana", groups=["A"])
        self.bea = self.user("bea", groups=["B"])
        self.visible = self.collection(author=self.teacher)
        self.hidden = self.collection(name="Oculta", visible=False, author=self.teacher)
        self.problem_ = self.problem(self.visible, template="total = undefined")
        self.hidden_problem = self.problem(self.hidden, "Oculto")
        self.client.force_login(self.ana)


class NavigationTest(ViewsTestCase):
    def test_login_required(self):
        self.client.logout()
        for name, args in [("judge:index", []), ("judge:collections", []), ("judge:problem", [self.problem_.pk])]:
            response = self.client.get(reverse(name, args=args))
            self.assertRedirects(response, f"{reverse('judge:login')}?next={reverse(name, args=args)}")
        self.assertContains(self.client.get(reverse("judge:login")), "@ucm.es")

    def test_pages(self):
        self.assertRedirects(self.client.get(reverse("judge:index")), reverse("judge:collections"))
        for name in ["judge:help", "judge:rankings", "judge:password_change"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertContains(self.client.get(reverse("judge:password_change_done")), "con éxito")
        self.assertContains(self.client.post(reverse("judge:logout")), "correctamente")

    def test_beta_warning(self):
        response = self.client.get(reverse("judge:help"))
        self.assertContains(response, "Learn Haskell está en fase beta")
        self.assertContains(response, f'href="{reverse("judge:help")}#beta"')
        self.assertContains(response, "(beta)</title>")
        with self.settings(JUDGE_BETA=False):
            self.assertNotContains(self.client.get(reverse("judge:help")), "beta")
        self.client.logout()
        self.assertContains(self.client.get(reverse("judge:login")), '<span class="badge beta-badge')
        with self.settings(JUDGE_BETA=False):
            self.assertNotContains(self.client.get(reverse("judge:login")), "beta")

    def test_collections(self):
        response = self.client.get(reverse("judge:collections"))
        self.assertContains(response, "Listas")
        self.assertNotContains(response, "Oculta")
        group = Group.objects.get(name="A")
        self.assertContains(self.client.get(reverse("judge:collections"), {"group": group.pk}), "para «A»")
        self.assertEqual(self.client.get(reverse("judge:collections"), {"group": "x"}).status_code, 400)
        self.assertEqual(self.client.get(reverse("judge:collections"), {"group": 999}).status_code, 404)
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("judge:collections")), "Oculta")

    def test_hidden_content_is_not_reachable_by_students(self):
        urls = [
            reverse("judge:collection", args=[self.hidden.pk]),
            reverse("judge:problem", args=[self.hidden_problem.pk]),
            reverse("judge:ranking", args=[self.hidden.pk]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404)
        response = self.client.post(reverse("judge:submit", args=[self.hidden_problem.pk]), {"code": TOTAL})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.executor.requests, [])
        self.client.force_login(self.teacher)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_collection_and_problem(self):
        Submission.objects.create(user=self.bea, problem=self.problem_, code="x", verdict=Verdict.AC)
        self.assertContains(self.client.get(reverse("judge:collection", args=[self.visible.pk])), "bea")
        response = self.client.get(reverse("judge:problem", args=[self.problem_.pk]))
        self.assertContains(response, "total []")  # visible test
        self.assertNotContains(response, "total [1,2,3]")  # hidden test
        self.assertContains(response, "hay 1 test oculto")
        self.assertEqual(response.context["initial_code"], "total = undefined")  # template
        self.assertFalse(response.context["solved"])
        Submission.objects.create(user=self.ana, problem=self.problem_, code="mine", verdict=Verdict.AC)
        response = self.client.get(reverse("judge:problem", args=[self.problem_.pk]))
        self.assertEqual(response.context["initial_code"], "mine")  # last submission
        self.assertTrue(response.context["solved"])

    def test_extra_visible_tests_start_folded(self):
        tests = [(f"total [{i}]", str(i), False) for i in range(5)]
        problem = self.problem(self.visible, title="Cinco", tests=tests)
        response = self.client.get(reverse("judge:problem", args=[problem.pk]))
        self.assertEqual([t.expr for t in response.context["examples"]], ["total [0]", "total [1]", "total [2]"])
        self.assertEqual([t.expr for t in response.context["more_examples"]], ["total [3]", "total [4]"])
        self.assertContains(response, '<tbody id="more-tests" hidden>')
        self.assertContains(response, "Mostrar 2 tests más")
        response = self.client.get(reverse("judge:problem", args=[self.problem_.pk]))
        self.assertNotContains(response, "more-tests")


class SubmitTest(ViewsTestCase):
    def submit(self, code=TOTAL):
        return self.client.post(reverse("judge:submit", args=[self.problem_.pk]), {"code": code})

    def test_accepted(self):
        response = self.submit()
        data = response.json()
        self.assertEqual((data["verdict"], data["title"]), ("AC", "Aceptado"))
        self.assertIn("supera los 2 tests", data["feedback"])
        submission = Submission.objects.get()
        self.assertEqual((submission.verdict, submission.passed, submission.total), ("AC", 2, 2))
        self.assertEqual(self.executor.requests[0]["student_code"], TOTAL)

    def test_feedback_of_each_verdict(self):
        responses = [
            {
                "status": "WRONG_ANSWER",
                "passed": 0,
                "total": 2,
                "test": {"index": 1, "expr": "total []", "expected": "0", "obtained": "<b>1</b>"},
            },
            {"status": "COMPILATION_ERROR", "source": "student", "message": "solution.hs:2:9: error: boom"},
            {
                "status": "COMPILATION_ERROR",
                "source": "student",
                "code": "pragma_not_allowed",
                "line": 1,
                "message": "solution.hs:1: pragmas are not allowed",
            },
            {
                "status": "RUNTIME_ERROR",
                "passed": 0,
                "total": 2,
                "test": {"index": 1, "expr": "total []", "exception": "solution.hs:2:1-9: Non-exhaustive"},
            },
            {"status": "TIME_LIMIT", "passed": 1, "total": 2, "test": {"index": 2, "hidden": True, "reason": "cpu"}},
        ]
        self.executor.queue(*responses)
        texts = ["&lt;b&gt;1&lt;/b&gt;", "boom", "no se permiten pragmas", "Non-exhaustive", "test oculto"]
        for text in texts:
            data = self.submit().json()
            self.assertIn(text, data["feedback"])
        self.assertEqual([s.verdict for s in Submission.objects.order_by("pk")], ["WA", "CE", "CE", "RE", "TLE"])

    def test_executor_failures_are_not_stored(self):
        self.executor.queue(
            503, httpx.ConnectError("down"), 400, {"status": "INTERNAL_ERROR", "code": "internal_error"}
        )
        with self.assertLogs("judge", "ERROR"):
            statuses = [self.submit().status_code for _ in range(4)]
        self.assertEqual(statuses, [503, 503, 500, 500])
        self.assertFalse(Submission.objects.exists())

    def test_invalid_code(self):
        for code in ["", "   \n", "x" * (64 * 1024 + 1)]:
            response = self.submit(code)
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.json())
        self.assertEqual(self.client.get(reverse("judge:submit", args=[self.problem_.pk])).status_code, 405)

    def test_concurrent_submissions_of_a_user(self):
        # Another session (another request of the same user) holds the user's lock
        db = connection.settings_dict
        conninfo = (
            f"host={db['HOST']} port={db['PORT']} user={db['USER']} password={db['PASSWORD']} dbname={db['NAME']}"
        )
        with psycopg.connect(conninfo, autocommit=True) as other:
            other.execute("SELECT pg_advisory_lock(%s, %s)", [SUBMISSION_LOCK, self.ana.pk])
            response = self.submit()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.submit().status_code, 200)  # released when the other session ends


class SubmissionsTest(ViewsTestCase):
    def setUp(self):
        super().setUp()
        self.mine = Submission.objects.create(
            user=self.ana,
            problem=self.problem_,
            code=TOTAL,
            verdict=Verdict.CE,
            result={"status": "COMPILATION_ERROR", "source": "student", "message": "solution.hs:2:9: error: boom"},
        )
        self.other = Submission.objects.create(user=self.bea, problem=self.problem_, code="x", verdict=Verdict.AC)

    def test_list_and_filters(self):
        response = self.client.get(reverse("judge:submissions"))
        self.assertEqual(list(response.context["page"]), [self.mine])
        params = {"problem_id": self.problem_.pk, "start": "2000-01-01", "end": "2999-01-01"}
        self.assertEqual(list(self.client.get(reverse("judge:submissions"), params).context["page"]), [self.mine])
        self.assertEqual(self.client.get(reverse("judge:submissions"), {"user_id": self.bea.pk}).status_code, 404)
        self.assertEqual(self.client.get(reverse("judge:submissions"), {"start": "x"}).status_code, 400)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("judge:submissions"), {"user_id": self.bea.pk})
        self.assertEqual(list(response.context["page"]), [self.other])

    def test_pagination(self):
        Submission.objects.bulk_create(
            Submission(user=self.ana, problem=self.problem_, code="x", verdict=Verdict.WA) for _ in range(60)
        )
        response = self.client.get(reverse("judge:submissions"), {"page": 2, "problem_id": self.problem_.pk})
        self.assertContains(response, "2 / 2")
        self.assertContains(response, "Anterior")

    def test_detail_and_download(self):
        response = self.client.get(reverse("judge:submission", args=[self.mine.pk]))
        self.assertContains(response, "boom")
        self.assertEqual(response.context["diagnostics"][0]["from"], [2, 9])
        response = self.client.get(reverse("judge:download_submission", args=[self.mine.pk]))
        self.assertEqual(response.content.decode(), TOTAL)
        self.assertIn(f"submission{self.mine.pk}.hs", response["Content-Disposition"])
        for name in ["judge:submission", "judge:download_submission"]:
            self.assertEqual(self.client.get(reverse(name, args=[self.other.pk])).status_code, 404)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("judge:submission", args=[self.other.pk])).status_code, 200)


class RankingTest(ViewsTestCase):
    def test_student_sees_own_groups_only(self):
        Submission.objects.create(user=self.ana, problem=self.problem_, code="x", verdict=Verdict.AC)
        url = reverse("judge:ranking", args=[self.visible.pk])
        response = self.client.get(url, {"start": "2999-01-01"})  # dates are ignored for students
        self.assertEqual(response.context["group"].name, "A")
        self.assertEqual(response.context["rows"][0].num_solved, 1)
        self.assertEqual(self.client.get(url, {"group": Group.objects.get(name="B").pk}).status_code, 404)
        self.assertEqual(self.client.get(url, {"start": "x"}).status_code, 404)
        self.client.force_login(self.user("sin_grupo"))
        self.assertContains(self.client.get(url), "No perteneces a ningún grupo")

    def test_staff_filters_and_download(self):
        Submission.objects.create(user=self.ana, problem=self.problem_, code="x", verdict=Verdict.AC)
        self.ana.username = "=cmd"
        self.ana.save()
        self.client.force_login(self.teacher)
        group = Group.objects.get(name="A")
        url = reverse("judge:ranking", args=[self.visible.pk])
        response = self.client.get(url, {"group": group.pk, "start": "2999-01-01"})
        self.assertEqual(response.context["rows"][0].num_solved, 0)
        response = self.client.get(reverse("judge:download_ranking", args=[self.visible.pk]), {"group": group.pk})
        sheet = next(iter(get_data(io.BytesIO(response.content), file_type="ods").values()))
        self.assertEqual(sheet[0][:3], ["Posición", "Usuario", "Suma"])
        self.assertEqual(sheet[1][:3], [1, "'=cmd", "1/1 (1)"])

    def test_download_requires_staff_and_group(self):
        url = reverse("judge:download_ranking", args=[self.visible.pk])
        self.assertEqual(self.client.get(url).status_code, 302)  # students are sent to the admin login
        Group.objects.all().delete()
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(url).status_code, 404)


class StatisticsTest(ViewsTestCase):
    def test_statistics(self):
        self.client.force_login(self.teacher)
        Submission.objects.create(user=self.ana, problem=self.problem_, code="x", verdict=Verdict.AC)
        self.executor.queue({"status": "ok", "ghc": "9.10.3", "workers": 3, "busy": 1, "queued": 0})
        response = self.client.get(reverse("judge:statistics"))
        self.assertContains(response, "GHC 9.10.3")
        self.assertIn((Verdict.AC, 1), response.context["verdict_counts"])
        self.executor.queue(httpx.ConnectError("down"))
        self.assertContains(self.client.get(reverse("judge:statistics")), "No disponible")
