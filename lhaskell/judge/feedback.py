"""Presentation of the executor responses to students: summary messages, texts for
the executor message codes and diagnostics to mark GHC errors in the editor."""

import re

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .types import Verdict

# Texts for the stable message codes of haskell-test-executor (see its README)
_CODE_MESSAGES = {
    "pragma_not_allowed": lambda r: _("Línea %(line)s: no se permiten pragmas ({-# ... #-}) en la solución.") % r,
    "module_declaration_not_allowed": lambda r: (
        _("Línea %(line)s: no incluyas la declaración 'module'; escribe solo las importaciones y las definiciones.") % r
    ),
    "hidden_test_type_mismatch": lambda r: _(
        "Tu solución no es compatible con un test oculto: revisa que los tipos de tus funciones "
        "coinciden con los del enunciado."
    ),
    "compile_limits_exceeded": lambda r: _("La compilación ha excedido los límites de tiempo o memoria."),
    "program_crashed": lambda r: _("El programa terminó de forma inesperada."),
    "internal_error": lambda r: _("Error interno del juez. Vuelve a intentarlo más tarde."),
}


# TIME_LIMIT reasons. "allocation" is the deterministic limit on the memory allocated by
# a test, which measures the amount of work: it is explained to students as computation.
def _total_time():
    return _("El test %(index)s ha hecho que se agote el tiempo total disponible para todos los tests.")


_REASONS = {
    "timeout": lambda: _(
        "El test %(index)s ha excedido el tiempo límite. Probablemente no termina o es muy ineficiente."
    ),
    "allocation": lambda: _(
        "El test %(index)s ha excedido el límite de cálculo: tu solución hace demasiado trabajo. "
        "Probablemente no termina o es muy ineficiente."
    ),
    "cpu": _total_time,
    "wall": _total_time,
}


def message_for_code(result: dict) -> str | None:
    """Localized text for an executor message with a code, or None if it has no code."""
    text = _CODE_MESSAGES.get(result.get("code"))
    return text(result) if text else None


def message(result: dict) -> str:
    """Message to show: our text for the code if there is one, otherwise the executor
    message as is (GHC errors, which are in English)."""
    return message_for_code(result) or result.get("message", "")


def summary(verdict: Verdict, result: dict) -> str:
    """One sentence describing the verdict."""
    test = result.get("test") or {}
    index, total = test.get("index"), result.get("total")
    if verdict == Verdict.AC:
        return ngettext("Tu solución supera el único test.", "Tu solución supera los %(total)s tests.", total or 0) % {
            "total": total
        }
    if verdict == Verdict.WA:
        return _("Tu solución falla el test %(index)s de %(total)s.") % {"index": index, "total": total}
    if verdict == Verdict.CE:
        if result.get("source") == "tests":
            return _("Tu solución no es compatible con el test %(index)s: revisa los tipos de tus funciones.") % {
                "index": index
            }
        return _("Tu solución no compila.")
    if verdict == Verdict.RE:
        return _("Error en ejecución en el test %(index)s de %(total)s.") % {"index": index, "total": total}
    if verdict == Verdict.TLE:
        return _REASONS.get(test.get("reason"), _REASONS["timeout"])() % {"index": index}
    if verdict == Verdict.MLE:
        return _("El test %(index)s ha excedido la memoria disponible.") % {"index": index}
    return _("Se ha producido un error interno al evaluar tu solución. Vuelve a intentarlo más tarde.")


# GHC locations in the student file: solution.hs:L:C, solution.hs:L:C1-C2, solution.hs:(L1,C1)-(L2,C2)
_LOCATION = re.compile(
    r"^solution\.hs:(?:(?P<line>\d+):(?P<col>\d+)(?:-(?P<end_col>\d+))?"
    r"|\((?P<line1>\d+),(?P<col1>\d+)\)-\((?P<line2>\d+),(?P<col2>\d+)\)):(?P<rest>.*)$"
)

# Calls in the student file inside the call stack of a runtime error (error, undefined,
# head [] ...): "undefined, called at solution.hs:3:11 in main:Student"
_CALLED_AT = re.compile(r"called at solution\.hs:(\d+):(\d+)")


def diagnostics(result: dict) -> list[dict]:
    """Locations of the errors in the student code (1-based lines and columns) with
    their message, to mark them in the editor."""
    if result.get("status") == "COMPILATION_ERROR" and result.get("source") == "student" and "code" not in result:
        text = result.get("message", "")
    elif result.get("status") == "RUNTIME_ERROR":
        text = (result.get("test") or {}).get("exception", "")
    else:
        return []
    found = []
    for line in text.splitlines():
        m = _LOCATION.match(line)
        if m:
            if m["line"]:
                start_line, start_col = int(m["line"]), int(m["col"])
                end_line, end_col = start_line, int(m["end_col"] or m["col"])
            else:
                start_line, start_col = int(m["line1"]), int(m["col1"])
                end_line, end_col = int(m["line2"]), int(m["col2"])
            found.append(
                {
                    "from": [start_line, start_col],
                    "to": [end_line, end_col + 1],
                    "severity": "warning" if "warning" in m["rest"] else "error",
                    "message": [line],
                }
            )
        elif found:
            found[-1]["message"].append(line)
    for d in found:
        d["message"] = "\n".join(d["message"]).rstrip()
    if result.get("status") == "RUNTIME_ERROR":
        for m in _CALLED_AT.finditer(text):
            position = [int(m[1]), int(m[2])]
            # A single position: the editor extends the mark to the whole word
            found.append({"from": position, "to": position, "severity": "error", "message": text.strip()})
    return found
