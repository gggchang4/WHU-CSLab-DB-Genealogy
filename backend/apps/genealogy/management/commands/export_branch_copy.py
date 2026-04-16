from pathlib import Path

from django.core.management.base import BaseCommand

from apps.genealogy.coursework import export_branch_via_copy


class Command(BaseCommand):
    help = "Export one descendant branch to CSV files via PostgreSQL COPY."

    def add_arguments(self, parser):
        parser.add_argument("--genealogy-id", type=int, required=True)
        parser.add_argument("--root-member-id", type=int, required=True)
        parser.add_argument(
            "--output-dir",
            default="output/coursework/branch-export",
        )

    def handle(self, *args, **options):
        result = export_branch_via_copy(
            genealogy_id=options["genealogy_id"],
            root_member_id=options["root_member_id"],
            output_dir=Path(options["output_dir"]),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported branch rooted at member {result['root_member_id']} to {result['output_dir']}."
            )
        )
        for file_path in result["files"]:
            self.stdout.write(f"- {file_path}")

