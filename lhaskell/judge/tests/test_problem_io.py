import io
import json
import zipfile
from unittest import mock

import httpx
from django.core.exceptions import ValidationError

from judge import problem_io
from judge.problem_io import ProblemData

from .helpers import JudgeTestCase, make_zip, problem_files


def read(files) -> list:
    collection, problems = problem_io.read_zip(io.BytesIO(make_zip(files)))
    assert collection == {}
    return problems


class ReadZipTest(JudgeTestCase):
    def test_single_problem(self):
        [(name, data)] = read(problem_files(**{"statement.en.md": "Define it.", "definitions.hs": "data T = T"}))
        self.assertEqual(name, "problem.zip")
        self.assertEqual(
            data.statements, {"es": ("Suma", "Define `total :: [Int] -> Int`."), "en": ("Suma", "Define it.")}
        )
        self.assertEqual(data.tests[1], {"expr": "total [1]", "expected": "1", "hidden": True})
        self.assertEqual((data.position, data.extensions, data.definitions), (2, ["LambdaCase"], "data T = T"))
        self.assertTrue(data.template.startswith("total ::"))

    def test_titles_per_language_and_bom(self):
        meta = json.dumps({"title": {"es": "Suma", "en": "Sum"}})
        files = problem_files(**{"problem.json": meta, "statement.en.md": "x", "solution.hs": "﻿f = 1".encode()})
        [(_name, data)] = read(files)
        self.assertEqual(data.statements["en"][0], "Sum")
        self.assertEqual(data.solution, "f = 1")
        self.assertEqual(data.position, 1)

    def test_collection_zip(self):
        no_position = problem_files(**{"problem.json": json.dumps({"title": "B"})})
        outer = make_zip({"b.zip": make_zip(no_position), "a.zip": make_zip(problem_files()), "__MACOSX/a.zip": b"x"})
        collection, problems = problem_io.read_zip(io.BytesIO(outer))
        self.assertEqual(collection, {})
        self.assertEqual([(name, d.position) for name, d in problems], [("a.zip", 2), ("b.zip", 2)])

    def test_collection_metadata(self):
        problems = {"a.zip": make_zip(problem_files())}
        cases = [
            ({"name": " Listas ", "description": "*Md*"}, {"name": "Listas", "description": "*Md*"}),
            ({"name": "Listas"}, {"name": "Listas", "description": ""}),
            ({"name": "Listas", "position": 3}, {"name": "Listas", "description": "", "position": 3}),
        ]
        for meta, expected in cases:
            with self.subTest(meta=meta):
                outer = make_zip({**problems, "collection.json": json.dumps(meta)})
                collection, _problems = problem_io.read_zip(io.BytesIO(outer))
                self.assertEqual(collection, expected)
        for content in [
            "{",
            b"\xff",
            "[]",
            "{}",
            json.dumps({"name": "  "}),
            json.dumps({"name": "x" * 101}),
            json.dumps({"name": "x", "description": 3}),
            json.dumps({"name": "x", "position": -1}),
            json.dumps({"name": "x", "position": True}),
        ]:
            with self.subTest(content=content), self.assertRaisesMessage(ValidationError, "collection.json"):
                problem_io.read_zip(io.BytesIO(make_zip({**problems, "collection.json": content})))

    def test_errors(self):
        cases = [
            (b"not a zip", "no es un fichero ZIP válido"),
            (make_zip({"readme.txt": "x"}), "no contiene ni un problema"),
            (problem_files(**{"solution.hs": None}), "falta el fichero solution.hs"),
            (problem_files(**{"statement.md": None}), "falta el fichero statement.md"),
            (problem_files(**{"statement.fr.md": "x"}), "idioma no admitido"),
            (problem_files(**{"problem.json": json.dumps({})}), "falta el título"),
            (problem_files(**{"problem.json": "{"}), "no es JSON válido"),
            (problem_files(**{"problem.json": "[]"}), "debe ser un objeto JSON"),
            (problem_files(**{"solution.hs": b"\xff\xfe"}), "no está en UTF-8"),
            (problem_files(**{"solution.hs": "x" * (64 * 1024 + 1)}), "es demasiado largo"),
            (problem_files(**{"tests.json": "[]"}), "lista no vacía"),
            (problem_files(**{"tests.json": json.dumps([{"expr": "f"}])}), "debe tener 'expr' y 'expected'"),
            (problem_files(**{"tests.json": json.dumps([{"expr": "f\n", "expected": "1"}])}), "una sola línea"),
            (problem_files(**{"tests.json": json.dumps([{"expr": "f" * 4001, "expected": "1"}])}), "demasiado largo"),
            (problem_files(**{"problem.json": json.dumps({"title": "t", "extensions": ["CPP"]})}), "extensiones"),
            (problem_files(**{"problem.json": json.dumps({"title": "t", "limits": []})}), "'limits' debe ser"),
            (problem_files(**{"problem.json": json.dumps({"title": "t", "limits": {"heap_mb": 9999}})}), "límite"),
            (problem_files(**{"problem.json": json.dumps({"title": "t", "limits": {"other": 1}})}), "límite"),
            (problem_files(**{"problem.json": json.dumps({"title": "t", "position": -1})}), "'position'"),
        ]
        for content, message in cases:
            with self.subTest(message=message):
                content = content if isinstance(content, bytes) else make_zip(content)
                with self.assertRaisesMessage(ValidationError, message):
                    problem_io.read_zip(io.BytesIO(content))

    def test_too_big(self):
        with mock.patch.object(problem_io, "MAX_ZIP_ENTRIES", 3), self.assertRaisesMessage(ValidationError, "grande"):
            read(problem_files())


class ValidateTest(JudgeTestCase):
    def data(self):
        return ProblemData(
            statements={"es": ("Suma", "x")},
            solution="total = sum",
            tests=[{"expr": "total []", "expected": "0", "hidden": True}],
            limits={"heap_mb": 100},
        )

    def test_valid_solution_is_sent_with_every_test_visible(self):
        problem_io.validate_data("p.zip", self.data())
        request = self.executor.requests[0]
        self.assertEqual((request["tests"][0]["hidden"], request["limits"]), (False, {"heap_mb": 100}))

    def test_failures(self):
        wrong = {
            "status": "WRONG_ANSWER",
            "passed": 0,
            "total": 1,
            "test": {"index": 1, "expr": "total []", "expected": "0", "obtained": "1", "exception": "e", "reason": "r"},
            "message": "msg",
        }
        self.executor.queue(wrong, 400, httpx.ConnectError("down"))
        expected = ["no supera los tests", "rechaza el problema", "no está disponible"]
        for text in expected:
            with self.subTest(text=text), self.assertRaisesMessage(ValidationError, text):
                problem_io.validate_data("p.zip", self.data())
        with self.assertRaisesMessage(ValidationError, "al menos un test"):
            problem_io.validate_solution(solution="f", tests=[])

    def test_describe(self):
        text = problem_io.describe({"status": "TIME_LIMIT", "test": {"index": 1, "expr": "f", "reason": "cpu"}})
        self.assertEqual(text, "TIME_LIMIT\nTest 1: f\nMotivo: cpu")
        self.assertEqual(problem_io.describe({}), "?")

    def test_create_problem(self):
        teacher = self.user("profe", staff=True)
        data = self.data()
        data.statements["en"] = ("Sum", "y")
        problem = problem_io.create_problem(self.collection(), data, teacher)
        self.assertEqual((problem.author, problem.heap_mb, problem.title("en")), (teacher, 100, "Sum"))
        self.assertEqual([t.position for t in problem.tests.all()], [1])


class WriteZipTest(JudgeTestCase):
    def test_round_trip(self):
        """A collection exported and read again gives the same problems and metadata."""
        collection = self.collection("Árboles y listas", position=4)
        collection.description_md = "Con *Markdown*."
        collection.save()
        first = self.problem(collection, "Suma", position=2, definitions="data T = T", heap_mb=100)
        first.extensions = ["LambdaCase"]
        first.save()
        first.statements.create(language="en", title="Sum", text_md="Define `total`.")
        self.problem(collection, "¿?", position=1, template="total = undefined\n")

        meta, problems = problem_io.read_zip(io.BytesIO(problem_io.collection_zip(collection)))
        self.assertEqual(meta, {"name": "Árboles y listas", "description": "Con *Markdown*.", "position": 4})
        self.assertEqual([name for name, _data in problems], ["01_sin-titulo.zip", "02_suma.zip"])
        [(_name, untitled), (_name2, suma)] = problems
        self.assertEqual(suma.statements, {"es": ("Suma", "Define `total`."), "en": ("Sum", "Define `total`.")})
        self.assertEqual(
            (suma.position, suma.extensions, suma.limits, suma.definitions, suma.template),
            (2, ["LambdaCase"], {"heap_mb": 100}, "data T = T", ""),
        )
        self.assertEqual(
            suma.tests,
            [
                {"expr": "total []", "expected": "0", "hidden": False},
                {"expr": "total [1,2,3]", "expected": "6", "hidden": True},
            ],
        )
        self.assertEqual(suma.solution, first.solution)
        self.assertEqual((untitled.position, untitled.template, untitled.limits), (1, "total = undefined\n", {}))

    def test_optional_files_are_omitted(self):
        problem = self.problem(self.collection())
        with zipfile.ZipFile(io.BytesIO(problem_io.problem_zip(problem))) as archive:
            self.assertEqual(sorted(archive.namelist()), ["problem.json", "solution.hs", "statement.md", "tests.json"])

    def test_read_backup(self):
        listas = self.collection("Listas", position=3)
        self.problem(listas)
        backup = make_zip({"01_listas.zip": problem_io.collection_zip(listas), "__MACOSX/01_listas.zip": b"x"})
        [(name, collection, problems)] = problem_io.read_backup(io.BytesIO(backup))
        self.assertEqual((name, collection["name"], collection["position"]), ("01_listas.zip", "Listas", 3))
        self.assertEqual([data.statements["es"][0] for _name, data in problems], ["Suma"])

    def test_read_backup_errors(self):
        collection = make_zip({"collection.json": json.dumps({"name": "L"}), "a.zip": make_zip(problem_files())})
        cases = [
            (collection, "impórtalo desde la administración"),
            (make_zip(problem_files()), "impórtalo desde la administración"),
            (make_zip({"notes.txt": "x"}), "no contiene ZIPs de colecciones"),
            (make_zip({"01_l.zip": make_zip(problem_files())}), "01_l.zip: falta collection.json"),
            (make_zip({"01_l.zip": b"not a zip"}), "01_l.zip: el fichero no es un fichero ZIP válido"),
        ]
        for content, message in cases:
            with self.subTest(message=message), self.assertRaisesMessage(ValidationError, message):
                problem_io.read_backup(io.BytesIO(content))
