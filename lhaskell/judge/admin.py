"""Administration of collections, problems and submissions.

When a problem is saved, its reference solution is evaluated by the executor against
the tests and the problem is only stored if it passes all of them. Problems can also
be added to a collection from a ZIP (see problem_io).
"""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _

from . import problem_io
from .models import EXTENSIONS, Collection, Problem, ProblemTest, Statement, Submission


class CollectionAdminForm(forms.ModelForm):
    problems_zip = forms.FileField(
        label=_("Añadir problemas desde ZIP"),
        required=False,
        help_text=_("ZIP de un problema o ZIP con varios ZIPs de problemas. Se valida cada solución de referencia."),
    )

    class Meta:
        model = Collection
        fields = ["name", "description_md", "position", "visible"]

    def clean_problems_zip(self):
        uploaded = self.cleaned_data["problems_zip"]
        self.problems = problem_io.read_zip(uploaded) if uploaded else []
        errors = []
        for name, data in self.problems:
            try:
                problem_io.validate_data(name, data)
            except ValidationError as e:
                errors.extend(e.messages)
        if errors:
            raise ValidationError(errors)
        return uploaded


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    form = CollectionAdminForm
    list_display = ["name", "position", "visible", "author", "num_problems", "creation_date"]
    list_filter = ["visible", "author"]
    search_fields = ["name"]

    @admin.display(description=_("problemas"))
    def num_problems(self, collection):
        return collection.problems.count()

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        for _name, data in form.problems:
            problem_io.create_problem(form.instance, data, request.user)
        if form.problems:
            self.message_user(request, _("Se han añadido %(n)d problemas.") % {"n": len(form.problems)})


class ProblemAdminForm(forms.ModelForm):
    extensions = forms.MultipleChoiceField(
        label=_("Extensiones"),
        choices=[(e, e) for e in EXTENSIONS],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Problem
        fields = ["collection", "position", "definitions", "template", "solution", "extensions", *Problem.LIMIT_FIELDS]
        widgets = {
            "definitions": forms.Textarea(attrs={"class": "code", "rows": 10, "cols": 100}),
            "template": forms.Textarea(attrs={"class": "code", "rows": 6, "cols": 100}),
            "solution": forms.Textarea(attrs={"class": "code", "rows": 10, "cols": 100}),
        }

    def _post_clean(self):
        super()._post_clean()
        # The tests formset only validates the solution if the rest of the problem is valid
        self.instance._form_is_valid = not self.errors


class StatementInline(admin.StackedInline):
    model = Statement
    extra = 0
    min_num = 1
    validate_min = True


class ProblemTestFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors) or not getattr(self.instance, "_form_is_valid", False):
            return
        forms_ = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        forms_.sort(key=lambda f: f.cleaned_data["position"])
        tests = [
            {"expr": f.cleaned_data["expr"], "expected": f.cleaned_data["expected"], "hidden": f.cleaned_data["hidden"]}
            for f in forms_
        ]
        problem = self.instance
        limits = {name: getattr(problem, name) for name in Problem.LIMIT_FIELDS if getattr(problem, name) is not None}
        problem_io.validate_solution(
            solution=problem.solution,
            tests=tests,
            definitions=problem.definitions,
            extensions=problem.extensions,
            limits=limits,
        )


class ProblemTestInline(admin.TabularInline):
    model = ProblemTest
    formset = ProblemTestFormSet
    extra = 1
    min_num = 1
    validate_min = True
    formfield_overrides = {
        ProblemTest._meta.get_field("expr"): {"widget": forms.TextInput(attrs={"size": 60, "class": "code"})},
        ProblemTest._meta.get_field("expected"): {"widget": forms.TextInput(attrs={"size": 40, "class": "code"})},
    }


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    form = ProblemAdminForm
    inlines = [StatementInline, ProblemTestInline]
    list_display = ["pk", "title_es", "collection", "position", "num_tests", "author", "creation_date"]
    list_display_links = ["pk", "title_es"]
    list_filter = ["collection"]
    search_fields = ["statements__title"]
    fieldsets = [
        (None, {"fields": ["collection", "position"]}),
        (_("Código"), {"fields": ["definitions", "template", "solution", "extensions"]}),
        (
            _("Límites (vacío = valor por defecto del ejecutor)"),
            {"classes": ["collapse"], "fields": Problem.LIMIT_FIELDS},
        ),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("statements", "tests").select_related("collection")

    @admin.display(description=_("título"))
    def title_es(self, problem):
        return problem.title()

    @admin.display(description=_("tests"))
    def num_tests(self, problem):
        return len(problem.tests.all())

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ["pk", "creation_date", "user", "problem", "verdict", "passed", "total"]
    list_filter = ["verdict", "creation_date", "problem__collection"]
    search_fields = ["user__username"]
    readonly_fields = ["user", "problem", "creation_date", "code", "verdict", "passed", "total", "result"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "problem").prefetch_related("problem__statements")

    def has_add_permission(self, request):
        return False
