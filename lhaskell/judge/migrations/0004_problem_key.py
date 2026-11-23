"""Adds Problem.key and fills it for the existing problems with the slug of their title in the
default language (models.default_key), numbered when it is repeated within a collection
(suma, suma-2...), in the order of the collection. 0005 makes it unique per collection."""

from django.conf import settings
from django.db import migrations, models
from django.utils.text import slugify

MAX_KEY = 50


def default_key(title):
    # Frozen copy of models.default_key: the migration must not change if that function does
    return slugify(title)[:MAX_KEY].strip("-") or "problema"


def fill_keys(apps, schema_editor):
    Problem = apps.get_model("judge", "Problem")
    Statement = apps.get_model("judge", "Statement")
    titles = {}
    for problem_id, language, title in Statement.objects.values_list("problem_id", "language", "title"):
        if language == settings.LANGUAGE_CODE or problem_id not in titles:
            titles[problem_id] = title
    taken = set()
    for problem in Problem.objects.order_by("collection_id", "position", "pk"):
        base = default_key(titles.get(problem.pk, ""))
        key, n = base, 1
        while (problem.collection_id, key) in taken:
            n += 1
            suffix = f"-{n}"
            key = base[: MAX_KEY - len(suffix)] + suffix
        taken.add((problem.collection_id, key))
        problem.key = key
        problem.save(update_fields=["key"])


class Migration(migrations.Migration):
    dependencies = [
        ("judge", "0003_problem_require_signatures"),
    ]

    operations = [
        migrations.AddField(
            model_name="problem",
            name="key",
            field=models.SlugField(
                blank=True,
                help_text=(
                    "Identifica el problema dentro de su colección: al subir de nuevo un ZIP con esta clave "
                    "se actualiza este problema sin perder sus envíos. Vacía: se genera a partir del título."
                ),
                max_length=50,
                verbose_name="clave",
            ),
        ),
        migrations.RunPython(fill_keys, migrations.RunPython.noop),
    ]
