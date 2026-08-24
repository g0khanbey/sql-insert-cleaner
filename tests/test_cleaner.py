from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cleaner import clean_sql_file, extract_insert_table, scan_insert_tables


class CleanerTests(unittest.TestCase):
    def write_sql(self, path: Path, content: str):
        path.write_text(content, encoding="utf-8")

    def test_extracts_quoted_and_qualified_table_names(self):
        self.assertEqual(extract_insert_table("INSERT INTO `users` VALUES (1);"), "users")
        self.assertEqual(
            extract_insert_table('INSERT INTO "public"."users" VALUES (1);'),
            "public.users",
        )
        self.assertEqual(
            extract_insert_table("INSERT IGNORE INTO [audit_log] VALUES (1);"),
            "audit_log",
        )

    def test_scans_multiline_inserts_and_ignores_semicolon_in_string(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "dump.sql"
            self.write_sql(
                source,
                """CREATE TABLE users (id INT, note TEXT);
INSERT INTO users
VALUES (1, 'ilk; kayıt');
INSERT INTO `orders` VALUES (10);
INSERT INTO users VALUES (2, 'ikinci');
""",
            )

            self.assertEqual(scan_insert_tables(source), {"users": 2, "orders": 1})

    def test_cleans_only_selected_tables_and_preserves_original(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "dump.sql"
            output = Path(directory) / "dump_temiz.sql"
            original = """-- kullanıcı verileri
CREATE TABLE users (id INT);
CREATE TABLE orders (id INT);
INSERT INTO users VALUES (1);
INSERT INTO orders VALUES (2);
"""
            self.write_sql(source, original)

            result = clean_sql_file(source, output, {"users"})
            cleaned = output.read_text(encoding="utf-8")

            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertNotIn("INSERT INTO users", cleaned)
            self.assertIn("INSERT INTO orders", cleaned)
            self.assertIn("CREATE TABLE users", cleaned)
            self.assertEqual(result.removed_statements, 1)
            self.assertEqual(result.removed_by_table, {"users": 1})

    def test_preserves_comments_before_removed_insert(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "dump.sql"
            output = Path(directory) / "clean.sql"
            self.write_sql(source, "-- kayıtlar\nINSERT INTO users VALUES (1);\n")

            clean_sql_file(source, output)

            self.assertEqual(output.read_text(encoding="utf-8"), "-- kayıtlar\n\n")

    def test_rejects_overwriting_source(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "dump.sql"
            self.write_sql(source, "INSERT INTO users VALUES (1);")

            with self.assertRaisesRegex(ValueError, "aynı olamaz"):
                clean_sql_file(source, source)


if __name__ == "__main__":
    unittest.main()
