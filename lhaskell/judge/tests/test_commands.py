import io
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from judge import problem_io
from judge.models import Collection, Problem

from .helpers import OK, JudgeTestCase

HEADER = "FOTOGRAFÍA,NOMBRE COMPLETO,DOCUMENTO,ASIGNATURA,CORREO\n"
ROWS = '"","García Pérez, Ana",12345678A,PD,anagar@ucm.es\n"","López, Bea",87654321B,PD,BEALOP@UCM.ES\n'


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CreateUsersTest(TestCase):
    def run_command(self, content, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "estudiantes.csv"
            path.write_text(content, encoding="utf-8-sig")
            out = io.StringIO()
            call_command("create_users", str(path), "Grupo A", *args, stdout=out)
            return out.getvalue()

    def test_dry_run_stores_nothing(self):
        output = self.run_command(HEADER + ROWS)
        self.assertIn("DRY RUN", output)
        self.assertIn("Created user anagar", output)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Group.objects.exists())

    def test_save(self):
        self.run_command(HEADER + ROWS, "--save")
        ana = get_user_model().objects.get(username="anagar")
        self.assertEqual((ana.first_name, ana.last_name, ana.email), ("Ana", "García Pérez", "anagar@ucm.es"))
        self.assertTrue(ana.check_password("12345678A"))
        self.assertEqual(list(ana.groups.values_list("name", flat=True)), ["Grupo A"])
        self.assertTrue(get_user_model().objects.filter(username="bealop").exists())
        # Second time: existing users keep their password and are added to the group
        ana.set_password("new-password")
        ana.save()
        output = self.run_command(HEADER + ROWS, "--save")
        self.assertIn("Existing user anagar", output)
        self.assertIn("Existing group", output)
        ana.refresh_from_db()
        self.assertTrue(ana.check_password("new-password"))

    def test_errors(self):
        with self.assertRaisesMessage(CommandError, "invalid UCM e-mail"):
            self.run_command(HEADER + '"","X, Y",1,PD,someone@gmail.com\n', "--save")
        with self.assertRaisesMessage(CommandError, "Missing columns"):
            self.run_command("NOMBRE,CORREO\nx,y@ucm.es\n")
        with self.assertRaisesMessage(CommandError, "Cannot read"):
            call_command("create_users", "/nonexistent.csv", "Grupo A")
        self.assertFalse(get_user_model().objects.exists())


class ExportCollectionsTest(JudgeTestCase):
    def test_export(self):
        self.problem(self.collection("Listas", position=2))
        self.collection("Funciones", position=1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backup.zip"
            path.write_bytes(b"old backup")
            path.chmod(0o644)
            out = io.StringIO()
            call_command("export_collections", str(path), stdout=out)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.namelist(), ["01_funciones.zip", "02_listas.zip"])
                meta, problems = problem_io.read_zip(io.BytesIO(archive.read("02_listas.zip")))
        self.assertEqual((meta["name"], len(problems)), ("Listas", 1))
        self.assertIn("01_funciones.zip: 0 problems", out.getvalue())
        self.assertIn("2 collections written", out.getvalue())

    def test_cannot_write(self):
        with self.assertRaisesMessage(CommandError, "Cannot write"):
            call_command("export_collections", "/nonexistent/backup.zip", stdout=io.StringIO())


class ImportCollectionsTest(JudgeTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "backup.zip"
        listas = self.collection("Listas", position=2)
        self.problem(listas)
        self.problem(listas, "Producto")
        funciones = self.collection("Funciones", position=1, visible=False)
        self.problem(funciones, "Doble")
        call_command("export_collections", str(self.path), stdout=io.StringIO())
        Collection.objects.all().delete()

    def run_command(self, *args):
        out = io.StringIO()
        call_command("import_collections", str(self.path), *args, stdout=out)
        return out.getvalue()

    def test_dry_run_validates_and_stores_nothing(self):
        output = self.run_command()
        self.assertIn("DRY RUN", output)
        self.assertIn("created collection 'Listas' with 2 problems", output)
        self.assertEqual(len(self.executor.requests), 3)
        self.assertFalse(Collection.objects.exists())

    def test_save(self):
        teacher = self.user("profe", staff=True)
        self.run_command("--save", "--author", "profe")
        listas = Collection.objects.get(name="Listas")
        self.assertEqual((listas.position, listas.author, listas.visible), (2, teacher, True))
        self.assertFalse(Collection.objects.get(name="Funciones").visible)
        self.assertEqual([p.title() for p in listas.problems.all()], ["Suma", "Producto"])
        self.assertEqual(listas.problems.first().author, teacher)
        self.assertEqual(Problem.objects.count(), 3)

    def test_existing_collections_are_skipped(self):
        self.run_command("--save")
        self.assertIsNone(Collection.objects.get(name="Funciones").author)
        Collection.objects.get(name="Listas").delete()
        output = self.run_command("--save")
        self.assertIn("02_listas.zip: created collection 'Listas'", output)
        self.assertIn("01_funciones.zip: skipped, collection 'Funciones' already exists", output)
        self.assertEqual((Collection.objects.count(), Problem.objects.count()), (2, 3))

    def test_invalid_solution_imports_nothing(self):
        wrong = {"status": "WRONG_ANSWER", "passed": 0, "total": 2, "test": {"index": 1, "expr": "e"}}
        self.executor.queue(OK, wrong, wrong)
        with self.assertRaises(CommandError) as raised:
            self.run_command("--save")
        message = str(raised.exception)
        self.assertTrue(message.startswith("Nothing has been imported:\n02_listas.zip/01_suma.zip: "))
        self.assertIn("\n02_listas.zip/02_producto.zip: ", message)
        self.assertFalse(Collection.objects.exists())

    def test_errors(self):
        self.user("estudiante")
        for author in ["estudiante", "nadie"]:
            with self.subTest(author=author), self.assertRaisesMessage(CommandError, "There is no teacher"):
                self.run_command("--author", author)
        self.path.write_bytes(b"not a zip")
        with self.assertRaisesMessage(CommandError, "no es un fichero ZIP válido"):
            self.run_command()
        with self.assertRaisesMessage(CommandError, "Cannot read"):
            call_command("import_collections", "/nonexistent.zip")
