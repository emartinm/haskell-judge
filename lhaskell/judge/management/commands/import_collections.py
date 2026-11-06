"""Import of the collections of a backup made by export_collections.

    python manage.py import_collections backup.zip                       # dry run
    python manage.py import_collections backup.zip --save                # creates the collections
    python manage.py import_collections backup.zip --save --author profe

Every reference solution is validated with the executor first (as in the administration),
also in the dry run, and nothing is stored unless all of them pass. Collections whose name
already exists are skipped, so the import can be repeated. The collections and problems
belong to --author (a teacher, so that the collections appear in the filter of their
classes) or to nobody.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from judge import problem_io
from judge.models import Collection


class Command(BaseCommand):
    help = "Imports the collections of a ZIP made by export_collections."

    def add_arguments(self, parser):
        parser.add_argument("backup")
        parser.add_argument("--save", action="store_true", help="Store the changes (by default it is a dry run).")
        parser.add_argument("--author", help="Username of the author of the imported collections and problems.")

    def handle(self, backup, save, author, **options):
        author = self._author(author)
        try:
            with open(backup, "rb") as f:
                collections = problem_io.read_backup(f)
        except OSError as e:
            raise CommandError(f"Cannot read {backup}: {e}") from e
        except ValidationError as e:
            raise CommandError("\n".join(e.messages)) from e
        existing = set(Collection.objects.values_list("name", flat=True))
        new = [c for c in collections if c[1]["name"] not in existing]
        for name, collection, _problems in collections:
            if collection["name"] in existing:
                self.stdout.write(f"{name}: skipped, collection '{collection['name']}' already exists")
        self._validate(new)
        if not save:
            self.stdout.write("DRY RUN: nothing will be stored (use --save)")
        with transaction.atomic():
            for name, collection, problems in new:
                stored = Collection.objects.create(
                    name=collection["name"],
                    description_md=collection["description"],
                    position=collection.get("position", 1),
                    visible=collection.get("visible", True),
                    author=author,
                )
                for _name, data in problems:
                    problem_io.create_problem(stored, data, author)
                self.stdout.write(f"{name}: created collection '{stored.name}' with {len(problems)} problems")
            if not save:
                transaction.set_rollback(True)

    @staticmethod
    def _author(username):
        if username is None:
            return None
        try:
            return get_user_model().objects.get(username=username, is_staff=True)
        except get_user_model().DoesNotExist as e:
            raise CommandError(f"There is no teacher (staff user) {username}") from e

    def _validate(self, collections):
        errors = []
        for name, _collection, problems in collections:
            for problem_name, data in problems:
                try:
                    problem_io.validate_data(f"{name}/{problem_name}", data)
                except ValidationError as e:
                    errors.extend(e.messages)
        if errors:
            raise CommandError("Nothing has been imported:\n" + "\n".join(errors))
