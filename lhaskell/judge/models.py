"""Models of the judge: collections of problems, problems with their statements and
tests, and submissions with the response of haskell-test-executor."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from .markdown import markdown_to_html
from .types import Verdict

# Same limits as haskell-test-executor
MAX_CODE = 64 * 1024
MAX_COLLECTION_NAME = 100
MAX_COLLECTION_DESCRIPTION = 10000
MAX_EXPR = 4000
MAX_EXPECTED = 20000

# Extensions that haskell-test-executor allows a problem to enable
EXTENSIONS = [
    "BlockArguments",
    "DataKinds",
    "FunctionalDependencies",
    "GADTs",
    "LambdaCase",
    "MonadComprehensions",
    "MultiWayIf",
    "NoImplicitPrelude",
    "OverloadedStrings",
    "ParallelListComp",
    "RecordWildCards",
    "TypeFamilies",
    "ViewPatterns",
]


def validate_single_line(value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ValidationError(_("Debe ocupar una sola línea."))


class Collection(models.Model):
    """Group of problems, e.g. one topic of the course."""

    name = models.CharField(_("nombre"), max_length=MAX_COLLECTION_NAME)
    description_md = models.TextField(_("descripción (Markdown)"), blank=True, max_length=MAX_COLLECTION_DESCRIPTION)
    description_html = models.TextField(blank=True, editable=False)
    position = models.PositiveIntegerField(_("posición"), default=1)
    visible = models.BooleanField(_("visible"), default=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("autor"), null=True, blank=True, on_delete=models.SET_NULL
    )
    creation_date = models.DateTimeField(_("fecha de creación"), auto_now_add=True)

    class Meta:
        ordering = ["position", "-creation_date"]
        verbose_name = _("colección")
        verbose_name_plural = _("colecciones")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.description_html = markdown_to_html(self.description_md)
        super().save(*args, **kwargs)


class Problem(models.Model):
    """Problem solved with Haskell code and evaluated by haskell-test-executor.

    Everything that depends on the language of the student (title and statement)
    lives in Statement; definitions, solution, tests and limits are shared.
    """

    collection = models.ForeignKey(
        Collection, verbose_name=_("colección"), related_name="problems", on_delete=models.CASCADE
    )
    position = models.PositiveIntegerField(_("posición"), default=1)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("autor"), null=True, blank=True, on_delete=models.SET_NULL
    )
    creation_date = models.DateTimeField(_("fecha de creación"), auto_now_add=True)
    definitions = models.TextField(
        _("definiciones"),
        blank=True,
        max_length=MAX_CODE,
        help_text=_("Código Haskell del profesor (tipos, funciones auxiliares) que importa la solución del alumno."),
    )
    template = models.TextField(
        _("plantilla"),
        blank=True,
        max_length=MAX_CODE,
        help_text=_("Código inicial que aparece en el editor del alumno."),
    )
    solution = models.TextField(
        _("solución de referencia"),
        max_length=MAX_CODE,
        help_text=_("Debe superar todos los tests: se comprueba al guardar el problema."),
    )
    extensions = models.JSONField(_("extensiones"), default=list, blank=True)
    # Limits for haskell-test-executor; empty means the executor default
    time_per_test_ms = models.PositiveIntegerField(
        _("tiempo por test (ms)"), null=True, blank=True, validators=[MinValueValidator(100), MaxValueValidator(10000)]
    )
    alloc_per_test_mb = models.PositiveIntegerField(
        _("memoria reservada por test (MB)"),
        null=True,
        blank=True,
        validators=[MinValueValidator(10), MaxValueValidator(40000)],
    )
    heap_mb = models.PositiveIntegerField(
        _("heap (MB)"), null=True, blank=True, validators=[MinValueValidator(16), MaxValueValidator(1024)]
    )
    stack_mb = models.PositiveIntegerField(
        _("pila (MB)"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(1024)]
    )
    run_time_s = models.FloatField(
        _("tiempo total de CPU (s)"), null=True, blank=True, validators=[MinValueValidator(0.1), MaxValueValidator(60)]
    )

    LIMIT_FIELDS = ["time_per_test_ms", "alloc_per_test_mb", "heap_mb", "stack_mb", "run_time_s"]

    class Meta:
        ordering = ["collection", "position", "pk"]
        verbose_name = _("problema")
        verbose_name_plural = _("problemas")

    def __str__(self):
        return self.title()

    def statement(self, language=None):
        """Statement in the given language (by default, the active one), falling back
        to the default language and then to any statement. Uses prefetched statements."""
        statements = {s.language: s for s in self.statements.all()}
        for lang in (language or get_language(), settings.LANGUAGE_CODE):
            if lang in statements:
                return statements[lang]
        return next(iter(statements.values()), None)

    def title(self, language=None) -> str:
        statement = self.statement(language)
        return statement.title if statement else f"#{self.pk}"

    def executor_limits(self) -> dict:
        """Limits to send to the executor (only those set in the problem)."""
        return {name: getattr(self, name) for name in self.LIMIT_FIELDS if getattr(self, name) is not None}


class Statement(models.Model):
    """Title and statement of a problem in one language."""

    problem = models.ForeignKey(Problem, related_name="statements", on_delete=models.CASCADE)
    language = models.CharField(
        _("idioma"), max_length=7, choices=settings.STATEMENT_LANGUAGES, default=settings.LANGUAGE_CODE
    )
    title = models.CharField(_("título"), max_length=200)
    text_md = models.TextField(_("enunciado (Markdown)"), max_length=20000)
    text_html = models.TextField(blank=True, editable=False)

    class Meta:
        ordering = ["language"]
        verbose_name = _("enunciado")
        verbose_name_plural = _("enunciados")
        constraints = [models.UniqueConstraint(fields=["problem", "language"], name="unique_statement_language")]

    def __str__(self):
        return f"{self.title} ({self.language})"

    def save(self, *args, **kwargs):
        self.text_html = markdown_to_html(self.text_md)
        super().save(*args, **kwargs)


class ProblemTest(models.Model):
    """Unit test: a Haskell expression and its expected value, compared with ==."""

    problem = models.ForeignKey(Problem, related_name="tests", on_delete=models.CASCADE)
    position = models.PositiveIntegerField(_("posición"), default=1)
    expr = models.TextField(_("expresión"), max_length=MAX_EXPR, validators=[validate_single_line])
    expected = models.TextField(_("valor esperado"), max_length=MAX_EXPECTED, validators=[validate_single_line])
    hidden = models.BooleanField(
        _("oculto"), default=False, help_text=_("Los alumnos no ven ni la expresión ni el resultado.")
    )

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = _("test")
        verbose_name_plural = _("tests")

    def __str__(self):
        return f"{self.expr} == {self.expected}"

    def as_executor_test(self) -> dict:
        return {"expr": self.expr, "expected": self.expected, "hidden": self.hidden}


class Submission(models.Model):
    """Solution sent by a student, with the verdict and the full executor response."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("usuario"), on_delete=models.CASCADE)
    problem = models.ForeignKey(
        Problem, verbose_name=_("problema"), related_name="submissions", on_delete=models.CASCADE
    )
    creation_date = models.DateTimeField(_("fecha"), auto_now_add=True, db_index=True)
    code = models.TextField(_("código"), max_length=MAX_CODE)
    verdict = models.CharField(_("veredicto"), max_length=3, choices=Verdict.choices)
    passed = models.PositiveIntegerField(_("tests superados"), null=True, blank=True)
    total = models.PositiveIntegerField(_("tests"), null=True, blank=True)
    # Response of haskell-test-executor, so that any past submission shows its feedback
    result = models.JSONField(_("respuesta del ejecutor"), default=dict)

    class Meta:
        ordering = ["-creation_date", "-pk"]
        verbose_name = _("envío")
        verbose_name_plural = _("envíos")
        indexes = [
            models.Index(fields=["problem", "user", "verdict"]),
            models.Index(fields=["user", "-creation_date"]),
        ]

    def __str__(self):
        return f"{self.pk} ({self.verdict})"

    @property
    def verdict_enum(self) -> Verdict:
        return Verdict(self.verdict)
