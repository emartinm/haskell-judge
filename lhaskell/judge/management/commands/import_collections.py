"""Import of the collections of a backup made by export_collections.

    python manage.py import_collections backup.zip                       # dry run
    python manage.py import_collections backup.zip --save                # creates the collections
    python manage.py import_collections backup.zip --save --author profe
    python manage.py import_collections backup.zip --update              # dry run of an update
    python manage.py import_collections backup.zip --update --save

Every reference solution is validated with the executor first (as in the administration),
also in the dry run, and nothing is stored unless all of them pass. Collections whose name
already exists are skipped, so the import can be repeated, unless --update is given: then the
description, position and visibility of those collections are replaced by the ones in the ZIP and
their problems are created or updated by key (problem_io.save_problem), keeping their
submissions; problems that are not in the ZIP are left untouched. The new collections and
problems belong to --author (a teacher, so that the collections appear in the filter of their
classes) or to nobody; existing ones keep their author.
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
        parser.add_argument(
            "--update", action="store_true", help="Update the collections that already exist instead of skipping them."
        )

    def handle(self, backup, save, author, update, **options):
        author = self._author(author)
        try:
            with open(backup, "rb") as f:
                collections = problem_io.read_backup(f)
        except OSError as e:
            raise CommandError(f"Cannot read {backup}: {e}") from e
        except ValidationError as e:
            raise CommandError("\n".join(e.messages)) from e
        existing = {c.name: c for c in Collection.objects.all()}
        selected = []
        for item in collections:
            name, collection, _problems = item
            if collection["name"] in existing and not update:
                self.stdout.write(f"{name}: skipped, collection '{collection['name']}' already exists")
            else:
                selected.append(item)
        self._validate(selected)
        if not save:
            self.stdout.write("DRY RUN: nothing will be stored (use --save)")
        with transaction.atomic():
            for name, collection, problems in selected:
                stored = existing.get(collection["name"])
                if stored is None:
                    stored = Collection.objects.create(
                        name=collection["name"],
                        description_md=collection["description"],
                        position=collection.get("position", 1),
                        visible=collection.get("visible", True),
                        author=author,
                    )
                    for _name, data in problems:
                        problem_io.save_problem(stored, data, author)
                    self.stdout.write(f"{name}: created collection '{stored.name}' with {len(problems)} problems")
                else:
                    self._update(name, stored, collection, problems, author)
            if not save:
                transaction.set_rollback(True)

    def _update(self, name, stored, collection, problems, author):
        stored.description_md = collection["description"]
        stored.position = collection.get("position", stored.position)
        stored.visible = collection.get("visible", stored.visible)
        stored.save()
        created = sum(problem_io.save_problem(stored, data, author)[1] for _name, data in problems)
        untouched = stored.problems.exclude(key__in=[data.key for _name, data in problems]).count()
        self.stdout.write(
            f"{name}: updated collection '{stored.name}': {created} problems created, "
            f"{len(problems) - created} updated, {untouched} not in the ZIP (untouched)"
        )

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
