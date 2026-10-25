"""Validation of problems against haskell-test-executor and import from ZIP files.

Problem ZIP (all files UTF-8):

    problem.json      {"title": "..." | {"es": "...", "en": "..."}, "position": 1,
                       "extensions": ["LambdaCase"], "limits": {"time_per_test_ms": 1000}}
    statement.md      statement in Spanish (required)
    statement.en.md   statement in another language (optional, one per language)
    definitions.hs    teacher definitions imported by the student code (optional)
    template.hs       initial code of the editor (optional)
    solution.hs       reference solution (required; it must pass every test)
    tests.json        [{"expr": "...", "expected": "...", "hidden": false}, ...]

A collection ZIP contains several problem ZIPs (one per problem) and, optionally,

    collection.json   {"name": "...", "description": "..."}   (description in Markdown, optional)

which replace the name and description of the collection where the ZIP is imported.
"""

import io
import json
import re
import zipfile
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from . import executor
from .models import (
    EXTENSIONS,
    MAX_CODE,
    MAX_COLLECTION_DESCRIPTION,
    MAX_COLLECTION_NAME,
    MAX_EXPECTED,
    MAX_EXPR,
    Problem,
    ProblemTest,
    Statement,
)

MAX_ZIP_ENTRIES = 500
MAX_ZIP_SIZE = 20 * 1024 * 1024  # uncompressed bytes in a ZIP (protection against ZIP bombs)
_STATEMENT_FILE = re.compile(r"^statement(?:\.(?P<lang>[a-z]{2}))?\.md$")
_LIMIT_RANGES = {
    "time_per_test_ms": (100, 10000),
    "alloc_per_test_mb": (10, 40000),
    "heap_mb": (16, 1024),
    "stack_mb": (1, 1024),
    "run_time_s": (0.1, 60),
}


@dataclass
class ProblemData:
    """Contents of a problem independent of how it is stored."""

    statements: dict = field(default_factory=dict)  # language -> (title, text_md)
    definitions: str = ""
    template: str = ""
    solution: str = ""
    tests: list = field(default_factory=list)  # [{"expr", "expected", "hidden"}]
    extensions: list = field(default_factory=list)
    limits: dict = field(default_factory=dict)
    position: int = 1


# --- Validation against the executor ------------------------------------------------


def validate_solution(*, solution, tests, definitions="", extensions=(), limits=None) -> None:
    """Raises ValidationError unless the reference solution passes every test.

    Every test is sent as visible so that the error shows all the details to the teacher.
    """
    if not tests:
        raise ValidationError(_("El problema debe tener al menos un test."))
    visible = [{**t, "hidden": False} for t in tests]
    try:
        result = executor.run(solution, tests=visible, definitions=definitions, extensions=extensions, limits=limits)
    except executor.ExecutorRejected as e:
        raise ValidationError(_("El ejecutor rechaza el problema: %(detail)s") % {"detail": e}) from e
    except executor.ExecutorError as e:
        raise ValidationError(
            _("No se ha podido validar la solución porque el ejecutor no está disponible. Inténtalo más tarde.")
        ) from e
    if result.get("status") != "OK":
        raise ValidationError(
            _("La solución de referencia no supera los tests:\n%(detail)s") % {"detail": describe(result)}
        )


def describe(result: dict) -> str:
    """Full textual description of an executor response, for teachers."""
    lines = [result.get("status", "?")]
    if "passed" in result:
        lines.append(_("Tests superados: %(passed)s de %(total)s") % result)
    test = result.get("test") or {}
    if "expr" in test:
        lines.append(_("Test %(index)s: %(expr)s") % test)
    for key, label in (("expected", _("Esperado")), ("obtained", _("Obtenido")), ("exception", _("Excepción"))):
        if key in test:
            lines.append(f"{label}: {test[key]}")
    if "reason" in test:
        lines.append(_("Motivo: %(reason)s") % test)
    if "message" in result:
        lines.append(result["message"])
    return "\n".join(lines)


# --- Reading ZIP files ----------------------------------------------------------------


def read_zip(uploaded) -> tuple[dict, list[tuple[str, ProblemData]]]:
    """Reads a problem ZIP or a ZIP of problem ZIPs. Returns (collection, [(name, ProblemData)]),
    where collection is {} or the {"name", "description"} of the collection.json in the ZIP."""
    archive = _open_zip(uploaded, _("el fichero"))
    names = archive.namelist()
    if "problem.json" in names:
        return {}, [(getattr(uploaded, "name", "problem.zip"), read_problem(archive, "problem.zip"))]
    inner = sorted(n for n in names if n.lower().endswith(".zip") and not n.startswith("__MACOSX/"))
    if not inner:
        raise ValidationError(_("El ZIP no contiene ni un problema (problem.json) ni ZIPs de problemas."))
    problems = [
        (name, read_problem(_open_zip(io.BytesIO(archive.read(name)), name), name, default_position=position))
        for position, name in enumerate(inner, start=1)
    ]
    return _read_collection(archive), problems


def _read_collection(archive: zipfile.ZipFile) -> dict:
    if "collection.json" not in archive.namelist():
        return {}
    try:
        meta = json.loads(archive.read("collection.json").decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValidationError(_("collection.json no es JSON válido en UTF-8.")) from e
    name = meta.get("name") if isinstance(meta, dict) else None
    description = meta.get("description", "") if isinstance(meta, dict) else None
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > MAX_COLLECTION_NAME
        or not isinstance(description, str)
        or len(description) > MAX_COLLECTION_DESCRIPTION
    ):
        raise ValidationError(
            _("collection.json debe ser un objeto con 'name' (texto no vacío) y, opcionalmente, 'description'.")
        )
    return {"name": name.strip(), "description": description}


def _open_zip(file, name) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(file)
    except zipfile.BadZipFile as e:
        raise ValidationError(_("%(name)s no es un fichero ZIP válido.") % {"name": name}) from e
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_ZIP_SIZE:
        raise ValidationError(_("%(name)s es demasiado grande.") % {"name": name})
    return archive


def read_problem(archive: zipfile.ZipFile, name: str, default_position: int = 1) -> ProblemData:
    """Reads a problem ZIP already opened. Its position is default_position unless
    problem.json sets one."""

    def error(msg, **params):
        return ValidationError(f"{name}: " + msg % params)

    def text(filename, required=False, max_length=MAX_CODE) -> str:
        if filename not in archive.namelist():
            if required:
                raise error(_("falta el fichero %(file)s."), file=filename)
            return ""
        try:
            content = archive.read(filename).decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise error(_("%(file)s no está en UTF-8."), file=filename) from e
        if len(content) > max_length:
            raise error(_("%(file)s es demasiado largo."), file=filename)
        return content

    def json_file(filename):
        try:
            return json.loads(text(filename, required=True))
        except json.JSONDecodeError as e:
            raise error(_("%(file)s no es JSON válido: %(detail)s"), file=filename, detail=e) from e

    meta = json_file("problem.json")
    if not isinstance(meta, dict):
        raise error(_("problem.json debe ser un objeto JSON."))
    data = ProblemData(
        definitions=text("definitions.hs"),
        template=text("template.hs"),
        solution=text("solution.hs", required=True),
    )

    # Statements
    titles = meta.get("title", "")
    if isinstance(titles, str):
        titles = {settings.LANGUAGE_CODE: titles}
    languages = dict(settings.STATEMENT_LANGUAGES)
    for filename in archive.namelist():
        m = _STATEMENT_FILE.match(filename)
        if m:
            lang = m["lang"] or settings.LANGUAGE_CODE
            if lang not in languages:
                raise error(_("idioma no admitido en %(file)s."), file=filename)
            title = titles.get(lang) or titles.get(settings.LANGUAGE_CODE)
            if not title:
                raise error(_("falta el título en problem.json."))
            data.statements[lang] = (title, text(filename, max_length=20000))
    if settings.LANGUAGE_CODE not in data.statements:
        raise error(_("falta el fichero statement.md."))

    # Tests
    tests = json_file("tests.json")
    if not isinstance(tests, list) or not tests:
        raise error(_("tests.json debe ser una lista no vacía de tests."))
    for i, t in enumerate(tests, start=1):
        if not isinstance(t, dict) or not isinstance(t.get("expr"), str) or not isinstance(t.get("expected"), str):
            raise error(_("el test %(i)s de tests.json debe tener 'expr' y 'expected' (texto)."), i=i)
        if any(c in t["expr"] + t["expected"] for c in "\r\n") or not t["expr"].strip() or not t["expected"].strip():
            raise error(_("el test %(i)s debe tener 'expr' y 'expected' no vacíos y de una sola línea."), i=i)
        if len(t["expr"]) > MAX_EXPR or len(t["expected"]) > MAX_EXPECTED:
            raise error(_("el test %(i)s es demasiado largo."), i=i)
        data.tests.append({"expr": t["expr"], "expected": t["expected"], "hidden": bool(t.get("hidden", False))})

    # Configuration
    data.extensions = meta.get("extensions", [])
    if not isinstance(data.extensions, list) or any(e not in EXTENSIONS for e in data.extensions):
        raise error(_("extensiones no válidas: %(ext)s."), ext=data.extensions)
    data.limits = meta.get("limits", {})
    if not isinstance(data.limits, dict):
        raise error(_("'limits' debe ser un objeto JSON."))
    for key, value in data.limits.items():
        low, high = _LIMIT_RANGES.get(key, (None, None))
        if low is None or not isinstance(value, (int, float)) or not low <= value <= high:
            raise error(_("límite no válido: %(key)s = %(value)s."), key=key, value=value)
    position = meta.get("position", default_position)
    if not isinstance(position, int) or position < 0:
        raise error(_("'position' debe ser un entero no negativo."))
    data.position = position
    return data


def validate_data(name: str, data: ProblemData) -> None:
    """Validates the reference solution of a problem read from a ZIP."""
    try:
        validate_solution(
            solution=data.solution,
            tests=data.tests,
            definitions=data.definitions,
            extensions=data.extensions,
            limits=data.limits,
        )
    except ValidationError as e:
        raise ValidationError([f"{name}: {m}" for m in e.messages]) from e


@transaction.atomic
def create_problem(collection, data: ProblemData, author) -> Problem:
    """Stores a problem already validated."""
    problem = Problem.objects.create(
        collection=collection,
        author=author,
        position=data.position,
        definitions=data.definitions,
        template=data.template,
        solution=data.solution,
        extensions=data.extensions,
        **data.limits,
    )
    for lang, (title, text_md) in data.statements.items():
        Statement.objects.create(problem=problem, language=lang, title=title, text_md=text_md)
    ProblemTest.objects.bulk_create(
        ProblemTest(problem=problem, position=i, **t) for i, t in enumerate(data.tests, start=1)
    )
    return problem
