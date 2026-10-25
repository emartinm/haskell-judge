"""Views of the judge. Students only see visible collections and their own submissions;
staff (teachers) see everything."""

import io
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db import connection
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from pyexcel_ods3 import save_data

from . import executor, feedback, queries
from .forms import CollectionFilterForm, RankingFilterForm, SubmissionFilterForm, SubmitForm
from .models import Collection, Problem, Submission
from .types import Verdict

log = logging.getLogger(__name__)

# Namespace of the PostgreSQL advisory locks that serialize the submissions of each user
SUBMISSION_LOCK = 1

# Visible tests shown on the problem page before the "show all" button
SHOWN_TESTS = 3


def _visible_problem_or_404(request, problem_id) -> Problem:
    problems = Problem.objects.select_related("collection").prefetch_related("statements", "tests")
    problem = get_object_or_404(problems, pk=problem_id)
    if not request.user.is_staff and not problem.collection.visible:
        raise Http404
    return problem


def _visible_collection_or_404(request, collection_id) -> Collection:
    collection = get_object_or_404(Collection, pk=collection_id)
    if not request.user.is_staff and not collection.visible:
        raise Http404
    return collection


def _feedback_context(result: dict, verdict: Verdict) -> dict:
    return {
        "verdict": verdict,
        "result": result,
        "test": result.get("test") or {},
        "summary": feedback.summary(verdict, result),
        "message": feedback.message(result),
    }


@login_required
def index(request):
    return redirect("judge:collections")


@login_required
def help_page(request):
    return render(request, "judge/help.html")


@login_required
def show_collections(request):
    form = CollectionFilterForm(request.GET)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())
    group = get_object_or_404(Group, pk=form.cleaned_data["group"]) if form.cleaned_data["group"] else None
    return render(
        request,
        "judge/collections.html",
        {
            "collections": queries.collections_for(request.user, group),
            "filter_groups": queries.teacher_groups(),
            "group": group,
        },
    )


@login_required
def show_collection(request, collection_id):
    collection = _visible_collection_or_404(request, collection_id)
    return render(
        request,
        "judge/collection.html",
        {"collection": collection, "problems": queries.problems_for(collection, request.user)},
    )


@login_required
def show_problem(request, problem_id):
    problem = _visible_problem_or_404(request, problem_id)
    user_submissions = Submission.objects.filter(problem=problem, user=request.user)
    last = user_submissions.only("code").first()
    examples = [t for t in problem.tests.all() if not t.hidden]
    return render(
        request,
        "judge/problem.html",
        {
            "problem": problem,
            "statement": problem.statement(),
            "examples": examples[:SHOWN_TESTS],
            "more_examples": examples[SHOWN_TESTS:],
            "num_hidden": sum(1 for t in problem.tests.all() if t.hidden),
            "solved": user_submissions.filter(verdict=Verdict.AC).exists(),
            # The editor starts with the last submission or, if there is none, the template
            "initial_code": last.code if last else problem.template,
        },
    )


@login_required
@require_POST
def submit(request, problem_id):
    """Evaluates a solution and returns the verdict as JSON. Failures of the executor are
    not stored as submissions, so they never count as attempts."""
    problem = _visible_problem_or_404(request, problem_id)
    form = SubmitForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": " ".join(form.errors["code"])}, status=400)
    code = form.cleaned_data["code"]

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [SUBMISSION_LOCK, request.user.pk])
        if not cursor.fetchone()[0]:
            return JsonResponse({"error": _("Ya tienes otro envío en evaluación. Espera a que termine.")}, status=429)
        try:
            result = executor.run_problem(problem, code)
        except executor.ExecutorBusy:
            return JsonResponse({"error": _("El juez está muy ocupado. Vuelve a enviar en unos segundos.")}, status=503)
        except executor.ExecutorUnavailable:
            log.exception("executor unavailable")
            return JsonResponse({"error": _("El evaluador no está disponible. Inténtalo más tarde.")}, status=503)
        except executor.ExecutorRejected:
            log.exception("the executor rejected problem %s", problem.pk)
            return JsonResponse({"error": _("El problema está mal configurado. Avisa a tu profesor.")}, status=500)
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [SUBMISSION_LOCK, request.user.pk])

    verdict = Verdict.from_executor(result.get("status"))
    if verdict == Verdict.IE:
        log.error("internal executor error in problem %s: %s", problem.pk, result)
        return JsonResponse({"error": feedback.message(result) or str(Verdict.IE.label)}, status=500)
    Submission.objects.create(
        user=request.user,
        problem=problem,
        code=code,
        verdict=verdict,
        passed=result.get("passed"),
        total=result.get("total"),
        result=result,
    )
    return JsonResponse(
        {
            "verdict": verdict.value,
            "title": str(verdict.label),
            "summary": feedback.summary(verdict, result),
            "feedback": render_to_string("judge/feedback.html", _feedback_context(result, verdict), request),
            "diagnostics": feedback.diagnostics(result),
        }
    )


@login_required
def show_submissions(request):
    """Submissions of the user (staff: of any user), filtered by problem, user and dates."""
    form = SubmissionFilterForm(request.GET)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())
    data = form.cleaned_data
    user = request.user
    if data["user_id"] and data["user_id"] != user.pk:
        if not user.is_staff:
            raise Http404
        user = get_object_or_404(get_user_model(), pk=data["user_id"])
    submissions = Submission.objects.filter(user=user).select_related("problem").prefetch_related("problem__statements")
    if data["problem_id"]:
        submissions = submissions.filter(problem_id=data["problem_id"])
    if data["start"]:
        submissions = submissions.filter(creation_date__date__gte=data["start"])
    if data["end"]:
        submissions = submissions.filter(creation_date__date__lte=data["end"])
    page = Paginator(submissions.defer("code", "result"), 50).get_page(request.GET.get("page"))
    return render(request, "judge/submissions.html", {"page": page, "shown_user": user})


def _own_submission_or_404(request, submission_id) -> Submission:
    submission = get_object_or_404(
        Submission.objects.select_related("problem", "user").prefetch_related("problem__statements"),
        pk=submission_id,
    )
    if submission.user != request.user and not request.user.is_staff:
        raise Http404
    return submission


@login_required
def show_submission(request, submission_id):
    submission = _own_submission_or_404(request, submission_id)
    verdict = submission.verdict_enum
    context = {
        "submission": submission,
        "diagnostics": feedback.diagnostics(submission.result),
        **_feedback_context(submission.result, verdict),
    }
    return render(request, "judge/submission.html", context)


@login_required
def download_submission(request, submission_id):
    submission = _own_submission_or_404(request, submission_id)
    response = HttpResponse(submission.code, content_type="text/x-haskell; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="submission{submission.pk}.hs"'
    return response


# --- Rankings -------------------------------------------------------------------------


@login_required
def show_rankings(request):
    collections = Collection.objects.all() if request.user.is_staff else Collection.objects.filter(visible=True)
    return render(request, "judge/rankings.html", {"collections": collections})


def _ranking_parameters(request, collection_id):
    """Collection, available groups, chosen group and dates (only staff can choose dates)."""
    collection = _visible_collection_or_404(request, collection_id)
    form = RankingFilterForm(request.GET)
    if not form.is_valid():
        raise Http404
    groups = Group.objects.all() if request.user.is_staff else request.user.groups.all()
    groups = list(groups.order_by("name"))
    group_id = form.cleaned_data["group"]
    group = next((g for g in groups if g.pk == group_id), None) if group_id else (groups[0] if groups else None)
    if group_id and group is None:
        raise Http404
    start = form.cleaned_data["start"] if request.user.is_staff else None
    end = form.cleaned_data["end"] if request.user.is_staff else None
    return collection, groups, group, start, end


@login_required
def show_ranking(request, collection_id):
    collection, groups, group, start, end = _ranking_parameters(request, collection_id)
    problems, rows = queries.ranking(collection, group, start, end) if group else ([], [])
    return render(
        request,
        "judge/ranking.html",
        {
            "collection": collection,
            "groups": groups,
            "group": group,
            "start": start,
            "end": end,
            "problems": problems,
            "rows": rows,
        },
    )


def _ods_cell(value):
    """Prevents formula injection: text cells starting with a formula character."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


@staff_member_required
def download_ranking(request, collection_id):
    collection, _groups, group, start, end = _ranking_parameters(request, collection_id)
    if group is None:
        raise Http404
    problems, rows = queries.ranking(collection, group, start, end)
    table = [[_("Posición"), _("Usuario"), *[p.title() for p in problems], _("Puntuación"), _("Resueltos")]]
    for row in rows:
        cells = [f"{r.correct}/{r.total}" + (f" ({r.first_correct})" if r.correct else "") for r in row.results]
        table.append([row.position, row.user.username, *cells, row.score, row.num_solved])
    buffer = io.BytesIO()
    save_data(buffer, {_("Clasificación"): [[_ods_cell(c) for c in line] for line in table]})
    response = HttpResponse(buffer.getvalue(), content_type="application/vnd.oasis.opendocument.spreadsheet")
    response["Content-Disposition"] = f'attachment; filename="ranking_{collection.pk}_{group.pk}.ods"'
    return response


# --- Statistics -----------------------------------------------------------------------


@staff_member_required
def show_statistics(request):
    try:
        executor_status = executor.health()
    except executor.ExecutorError:
        executor_status = None
    per_verdict = queries.submissions_per_verdict()
    return render(
        request,
        "judge/statistics.html",
        {
            "executor": executor_status,
            "per_verdict": per_verdict,
            "verdict_counts": [(v, per_verdict[v.value]) for v in Verdict],
            "per_day": queries.submissions_per_day(),
            "per_group": queries.participation_per_group(),
        },
    )


@login_required
def password_change_done(request):
    return render(request, "judge/password_change_done.html")
