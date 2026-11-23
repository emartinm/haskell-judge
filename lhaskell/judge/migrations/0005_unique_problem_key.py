from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("judge", "0004_problem_key"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="problem",
            constraint=models.UniqueConstraint(fields=("collection", "key"), name="unique_problem_key"),
        ),
    ]
