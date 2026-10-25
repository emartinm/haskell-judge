"""Verdicts of the judge and their correspondence with haskell-test-executor statuses."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Verdict(models.TextChoices):
    AC = "AC", _("Aceptado")
    WA = "WA", _("Respuesta incorrecta")
    CE = "CE", _("Error de compilación")
    RE = "RE", _("Error en ejecución")
    TLE = "TLE", _("Tiempo límite excedido")
    MLE = "MLE", _("Memoria límite excedida")
    IE = "IE", _("Error interno")

    @classmethod
    def from_executor(cls, status: str) -> "Verdict":
        """Verdict for an executor status (unknown statuses are internal errors)."""
        return _FROM_EXECUTOR.get(status, cls.IE)

    @property
    def css_class(self) -> str:
        """Bootstrap background class used to show the verdict."""
        return _CSS_CLASS[self]


_FROM_EXECUTOR = {
    "OK": Verdict.AC,
    "WRONG_ANSWER": Verdict.WA,
    "COMPILATION_ERROR": Verdict.CE,
    "RUNTIME_ERROR": Verdict.RE,
    "TIME_LIMIT": Verdict.TLE,
    "MEMORY_LIMIT": Verdict.MLE,
    "INTERNAL_ERROR": Verdict.IE,
}

_CSS_CLASS = {
    Verdict.AC: "text-bg-success",
    Verdict.WA: "text-bg-danger",
    Verdict.CE: "text-bg-warning",
    Verdict.RE: "text-bg-danger",
    Verdict.TLE: "text-bg-info",
    Verdict.MLE: "text-bg-info",
    Verdict.IE: "text-bg-secondary",
}
