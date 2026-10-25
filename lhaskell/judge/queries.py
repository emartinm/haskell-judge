"""Read-only aggregated queries: collections with progress, podiums, rankings and
statistics. Each one runs a fixed number of SQL queries, independent of the number of
users, problems or collections."""

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time

from django.contrib.auth.models import Group
from django.db.models import Count, Exists, Min, OuterRef, Q
from django.db.models.functions import TruncDate

from .models import Collection, Problem, Submission
from .types import Verdict


def collections_for(user, group=None):
    """Collections that the user can see, with num_problems and num_solved (by the user).
    With a group, only those authored by teachers of that group."""
    collections = Collection.objects.all() if user.is_staff else Collection.objects.filter(visible=True)
    if group is not None:
        collections = collections.filter(author__groups=group, author__is_staff=True)
    return collections.annotate(
        num_problems=Count("problems", distinct=True),
        num_solved=Count(
            "problems",
            filter=Q(problems__submissions__user=user, problems__submissions__verdict=Verdict.AC),
            distinct=True,
        ),
    ).order_by("position", "-creation_date")


def teacher_groups():
    """Groups with at least one teacher (used to filter collections by class)."""
    return Group.objects.filter(user__is_staff=True).distinct().order_by("name")


def problems_for(collection, user):
    """Problems of a collection with the user's num_submissions and solved, plus the
    podium: usernames of the first 3 students to solve it (None for empty places)."""
    problems = list(
        collection.problems.prefetch_related("statements").annotate(
            num_submissions=Count("submissions", filter=Q(submissions__user=user)),
            solved=Exists(Submission.objects.filter(problem=OuterRef("pk"), user=user, verdict=Verdict.AC)),
        )
    )
    podiums = podium(collection)
    for p in problems:
        p.podium = (podiums.get(p.pk, []) + [None, None, None])[:3]
    return problems


def podium(collection, size=3) -> dict[int, list[str]]:
    """{problem_id: usernames of the first `size` students who solved it, in order}."""
    rows = (
        Submission.objects.filter(problem__collection=collection, verdict=Verdict.AC, user__is_staff=False)
        .values("problem_id", "user__username")
        .annotate(first=Min("creation_date"))
        .order_by("problem_id", "first", "user__username")
    )
    result = defaultdict(list)
    for row in rows:
        if len(result[row["problem_id"]]) < size:
            result[row["problem_id"]].append(row["user__username"])
    return result


# --- Ranking --------------------------------------------------------------------------


@dataclass
class ProblemResult:
    total: int = 0  # submissions
    correct: int = 0  # accepted submissions
    first_correct: int | None = None  # attempt number of the first accepted one


@dataclass
class RankingRow:
    user: object
    results: list = field(default_factory=list)  # ProblemResult per problem, in order
    num_solved: int = 0
    score: int = 0  # sum of first_correct of the solved problems (lower is better)
    position: int = 0


def ranking(collection, group, start: date | None = None, end: date | None = None):
    """Ranking of the students of a group in a collection: more solved problems first,
    then lower score; equal (num_solved, score) share position. Returns (problems, rows)."""
    problems = list(Problem.objects.filter(collection=collection).prefetch_related("statements"))
    users = list(group.user_set.filter(is_staff=False, is_active=True).order_by("username"))
    submissions = Submission.objects.filter(problem__collection=collection, user__in=users)
    if start:
        submissions = submissions.filter(creation_date__date__gte=start)
    if end:
        submissions = submissions.filter(creation_date__date__lte=end)
    results = defaultdict(ProblemResult)
    for user_id, problem_id, verdict in submissions.order_by("creation_date", "pk").values_list(
        "user_id", "problem_id", "verdict"
    ):
        r = results[(user_id, problem_id)]
        r.total += 1
        if verdict == Verdict.AC:
            r.correct += 1
            if r.first_correct is None:
                r.first_correct = r.total
    rows = []
    for user in users:
        row = RankingRow(user, [results.get((user.pk, p.pk), ProblemResult()) for p in problems])
        solved = [r for r in row.results if r.correct]
        row.num_solved = len(solved)
        row.score = sum(r.first_correct for r in solved)
        rows.append(row)
    rows.sort(key=lambda r: (-r.num_solved, r.score, r.user.username))
    for i, row in enumerate(rows):
        same = i > 0 and (row.num_solved, row.score) == (rows[i - 1].num_solved, rows[i - 1].score)
        row.position = rows[i - 1].position if same else i + 1
    return problems, rows


# --- Statistics -----------------------------------------------------------------------


def submissions_per_verdict() -> dict[str, int]:
    counts = dict(Submission.objects.values_list("verdict").annotate(n=Count("pk")).order_by())
    return {"all": sum(counts.values()), **{v.value: counts.get(v.value, 0) for v in Verdict}}


def submissions_per_day() -> dict[str, list]:
    """Series for the chart: {"all"|verdict: [[timestamp_ms, count], ...]} with every day
    that has submissions."""
    rows = (
        Submission.objects.annotate(day=TruncDate("creation_date"))
        .values_list("day", "verdict")
        .annotate(n=Count("pk"))
        .order_by("day")
    )
    per_day = defaultdict(lambda: defaultdict(int))
    for day, verdict, n in rows:
        per_day[day][verdict] += n
        per_day[day]["all"] += n
    series = {key: [] for key in ["all", *Verdict.values]}
    for day in sorted(per_day):
        timestamp = int(datetime.combine(day, time(), tzinfo=UTC).timestamp()) * 1000
        for key, points in series.items():
            points.append([timestamp, per_day[day][key]])
    return series


def participation_per_group() -> list[dict]:
    """Per group: students, students with submissions (and with an accepted one), total
    submissions and submissions per participating student (mean, stdev, quartiles)."""
    groups = Group.objects.annotate(students=Count("user", filter=Q(user__is_staff=False), distinct=True)).order_by(
        "name"
    )
    rows = (
        Submission.objects.filter(user__is_staff=False)
        .values_list("user__groups", "user_id")
        .annotate(n=Count("pk"), accepted=Count("pk", filter=Q(verdict=Verdict.AC)))
        .order_by()
    )
    per_group = defaultdict(list)
    for group_id, _user_id, n, accepted in rows:
        per_group[group_id].append((n, accepted))
    result = []
    for group in groups:
        counts = [n for n, _ in per_group[group.pk]]
        result.append(
            {
                "group": group.name,
                "students": group.students,
                "participating": len(counts),
                "accepted": sum(1 for _, a in per_group[group.pk] if a),
                "total": sum(counts),
                "mean": statistics.mean(counts) if counts else 0,
                "stdev": statistics.stdev(counts) if len(counts) > 1 else 0,
                # "inclusive" keeps the quartiles within the data, also for small groups
                "quartiles": statistics.quantiles(counts, n=4, method="inclusive") if len(counts) > 1 else counts,
            }
        )
    return result
