from datetime import date, timedelta

from django.contrib.auth.models import Group
from django.utils import timezone

from judge import queries
from judge.models import Submission
from judge.types import Verdict

from .helpers import JudgeTestCase


class QueriesTest(JudgeTestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.user("profe", staff=True, groups=["A"])
        self.ana = self.user("ana", groups=["A"])
        self.bea = self.user("bea", groups=["A"])
        self.carla = self.user("carla", groups=["A", "B"])
        self.collection_ = self.collection(author=self.teacher)
        self.p1 = self.problem(self.collection_, "P1")
        self.p2 = self.problem(self.collection_, "P2")

    def submit(self, user, problem, *verdicts, days_ago=0):
        for v in verdicts:
            s = Submission.objects.create(user=user, problem=problem, code="x", verdict=v)
            if days_ago:
                Submission.objects.filter(pk=s.pk).update(creation_date=timezone.now() - timedelta(days=days_ago))

    def test_collections_for(self):
        hidden = self.collection(name="Oculta", visible=False, author=self.teacher)
        self.collection(name="Otra")  # without author
        self.submit(self.ana, self.p1, Verdict.WA, Verdict.AC, Verdict.AC)
        rows = {c.name: (c.num_problems, c.num_solved) for c in queries.collections_for(self.ana)}
        self.assertEqual(rows, {"Listas": (2, 1), "Otra": (0, 0)})
        self.assertIn(hidden, queries.collections_for(self.teacher))
        group = Group.objects.get(name="A")
        self.assertEqual([c.name for c in queries.collections_for(self.ana, group)], ["Listas"])
        self.assertEqual(list(queries.collections_for(self.ana, Group.objects.get(name="B"))), [])
        self.assertEqual([g.name for g in queries.teacher_groups()], ["A"])

    def test_problems_and_podium(self):
        self.submit(self.bea, self.p1, Verdict.AC)
        self.submit(self.ana, self.p1, Verdict.AC)
        self.submit(self.teacher, self.p1, Verdict.AC)  # staff do not count
        self.submit(self.ana, self.p2, Verdict.WA)
        problems = queries.problems_for(self.collection_, self.ana)
        self.assertEqual([(p.num_submissions, p.solved) for p in problems], [(1, True), (1, False)])
        self.assertEqual([p.podium for p in problems], [["bea", "ana", None], [None, None, None]])
        self.assertEqual(queries.podium(self.collection_, size=1), {self.p1.pk: ["bea"]})

    def test_ranking(self):
        self.submit(self.ana, self.p1, Verdict.WA, Verdict.AC, Verdict.AC)  # first AC at attempt 2
        self.submit(self.ana, self.p2, Verdict.AC)  # 1
        self.submit(self.bea, self.p1, Verdict.AC)
        self.submit(self.bea, self.p2, Verdict.CE, Verdict.AC)  # 1 + 2 = 3, tie with ana
        self.submit(self.carla, self.p2, Verdict.WA)
        problems, rows = queries.ranking(self.collection_, Group.objects.get(name="A"))
        self.assertEqual([p.title() for p in problems], ["P1", "P2"])
        summary = [(r.position, r.user.username, r.num_solved, r.score) for r in rows]
        self.assertEqual(summary, [(1, "ana", 2, 3), (1, "bea", 2, 3), (3, "carla", 0, 0)])
        ana = rows[0].results[0]
        self.assertEqual((ana.total, ana.correct, ana.first_correct), (3, 2, 2))

    def test_ranking_dates(self):
        self.submit(self.ana, self.p1, Verdict.AC, days_ago=10)
        self.submit(self.ana, self.p2, Verdict.AC)
        group = Group.objects.get(name="A")
        today = date.today()
        _problems, rows = queries.ranking(self.collection_, group, start=today - timedelta(days=1))
        self.assertEqual(rows[0].num_solved, 1)
        _problems, rows = queries.ranking(self.collection_, group, end=today - timedelta(days=5))
        self.assertEqual(rows[0].num_solved, 1)

    def test_statistics(self):
        self.submit(self.ana, self.p1, Verdict.WA, Verdict.AC)
        self.submit(self.bea, self.p1, Verdict.WA, days_ago=1)
        self.submit(self.teacher, self.p1, Verdict.AC)
        per_verdict = queries.submissions_per_verdict()
        self.assertEqual((per_verdict["all"], per_verdict["AC"], per_verdict["WA"], per_verdict["MLE"]), (4, 2, 2, 0))

        per_day = queries.submissions_per_day()
        self.assertEqual([n for _t, n in per_day["all"]], [1, 3])
        self.assertEqual([n for _t, n in per_day["AC"]], [0, 2])

        groups = {g["group"]: g for g in queries.participation_per_group()}
        self.assertEqual(
            {k: groups["A"][k] for k in ("students", "participating", "accepted", "total", "mean", "stdev")},
            {"students": 3, "participating": 2, "accepted": 1, "total": 3, "mean": 1.5, "stdev": 0.7071067811865476},
        )
        self.assertEqual(groups["B"]["quartiles"], [])
        self.assertEqual(groups["A"]["quartiles"], [1.25, 1.5, 1.75])
