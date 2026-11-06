"""Backup of every collection of problems in a ZIP file.

    python manage.py export_collections backup.zip

The backup contains one ZIP per collection (01_<name>.zip, 02_<name>.zip... in the order
of the collection list) in the import format of problem_io, so each one can be imported
again from the administration. Users, groups and submissions are not included.

It contains the reference solutions and the hidden tests: the file is created readable
only by its owner.
"""

import os
import zipfile

from django.core.management.base import BaseCommand, CommandError

from judge.models import Collection
from judge.problem_io import collection_zip, zip_name


class Command(BaseCommand):
    help = "Writes a ZIP with every collection of problems, in the import format."

    def add_arguments(self, parser):
        parser.add_argument("output", help="ZIP file to write (it is replaced if it exists).")

    def handle(self, output, **options):
        try:
            # Created with mode 600 even if it exists, before writing anything into it
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
        except OSError as e:
            raise CommandError(f"Cannot write {output}: {e}") from e
        collections = list(Collection.objects.all())
        with os.fdopen(fd, "wb") as f, zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as archive:
            for number, collection in enumerate(collections, start=1):
                name = zip_name(number, collection.name)
                archive.writestr(name, collection_zip(collection))
                self.stdout.write(f"{name}: {collection.problems.count()} problems")
        self.stdout.write(f"{len(collections)} collections written to {output}")
