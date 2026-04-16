from pathlib import Path

from django.core.management.base import BaseCommand

from apps.genealogy.coursework import benchmark_parent_lookup


class Command(BaseCommand):
    help = "Compare fourth-generation descendant lookup with and without the parent lookup index."

    def add_arguments(self, parser):
        parser.add_argument("--genealogy-id", type=int, required=True)
        parser.add_argument("--root-member-id", type=int, required=True)
        parser.add_argument(
            "--output",
            default="output/coursework/benchmarks/parent_lookup.md",
        )

    def handle(self, *args, **options):
        result = benchmark_parent_lookup(
            genealogy_id=options["genealogy_id"],
            root_member_id=options["root_member_id"],
            output_path=Path(options["output"]),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Benchmark report written to {result['output_path']}."
            )
        )
        if result["index_names"]:
            self.stdout.write(f"Indexes compared: {', '.join(result['index_names'])}")
        else:
            self.stdout.write("No matching parent lookup indexes were found; benchmark still completed.")
