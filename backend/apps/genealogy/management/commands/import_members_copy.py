from pathlib import Path

from django.core.management.base import BaseCommand

from apps.genealogy.coursework import import_members_via_copy


class Command(BaseCommand):
    help = "Bulk import member records into one genealogy via PostgreSQL COPY."

    def add_arguments(self, parser):
        parser.add_argument("--genealogy-id", type=int, required=True)
        parser.add_argument("--csv", required=True)
        parser.add_argument("--created-by-id", type=int)

    def handle(self, *args, **options):
        result = import_members_via_copy(
            genealogy_id=options["genealogy_id"],
            csv_path=Path(options["csv"]),
            created_by_id=options.get("created_by_id"),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {result['imported_count']} members from {result['csv_path']} "
                f"into genealogy {result['genealogy_id']}."
            )
        )

