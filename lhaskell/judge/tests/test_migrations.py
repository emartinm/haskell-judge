from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ProblemKeyMigrationTest(TransactionTestCase):
    """0004 fills the keys of the problems that already exist, 0005 makes them unique per
    collection, and both can be reverted."""

    before = [("judge", "0003_problem_require_signatures")]
    after = [("judge", "0005_unique_problem_key")]

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_keys_of_existing_problems(self):
        apps = self.migrate(self.before)
        Collection = apps.get_model("judge", "Collection")
        Problem = apps.get_model("judge", "Problem")
        Statement = apps.get_model("judge", "Statement")
        listas, arboles = Collection.objects.create(name="Listas"), Collection.objects.create(name="Árboles")

        def problem(collection, position, *statements):
            p = Problem.objects.create(collection=collection, position=position, solution="f = 1")
            for language, title in statements:
                Statement.objects.create(problem=p, language=language, title=title, text_md="x")
            return p.pk

        second = problem(listas, 2, ("es", "Suma"))
        first = problem(listas, 1, ("en", "Sum"), ("es", "Suma"))
        english = problem(listas, 3, ("en", "Only English"))
        untitled = problem(listas, 4)
        long_title = problem(listas, 5, ("es", "Ñ" * 60))
        other = problem(arboles, 1, ("es", "Suma"))

        apps = self.migrate(self.after)
        keys = dict(apps.get_model("judge", "Problem").objects.values_list("pk", "key"))
        self.assertEqual(
            [keys[pk] for pk in (first, second, english, untitled, long_title, other)],
            ["suma", "suma-2", "only-english", "problema", "n" * 50, "suma"],
        )
        Problem = apps.get_model("judge", "Problem")
        with self.assertRaises(IntegrityError):
            Problem.objects.create(collection_id=Problem.objects.get(pk=first).collection_id, key="suma")

        apps = self.migrate(self.before)  # reversible
        self.assertEqual(apps.get_model("judge", "Problem").objects.count(), 6)
