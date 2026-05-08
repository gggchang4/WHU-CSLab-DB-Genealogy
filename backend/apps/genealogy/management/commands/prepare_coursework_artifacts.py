from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.genealogy.coursework import prepare_coursework_artifacts


class Command(BaseCommand):
    help = "Prepare reproducible coursework artifact files under output/coursework."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="output/coursework",
        )
        parser.add_argument("--genealogy-id", type=int)
        parser.add_argument("--root-member-id", type=int)
        parser.add_argument(
            "--create-smoke-data",
            action="store_true",
            help="Create a small demo genealogy and use it for export/benchmark artifacts.",
        )
        parser.add_argument("--smoke-total-members", type=int, default=24)
        parser.add_argument("--smoke-generations", type=int, default=5)
        parser.add_argument("--smoke-batch-size", type=int, default=12)
        parser.add_argument("--smoke-username", default="course_smoke_operator")
        parser.add_argument("--seed", type=int, default=20260416)

    def handle(self, *args, **options):
        try:
            result = prepare_coursework_artifacts(
                output_dir=Path(options["output_dir"]),
                genealogy_id=options.get("genealogy_id"),
                root_member_id=options.get("root_member_id"),
                create_smoke_data=options["create_smoke_data"],
                smoke_total_members=options["smoke_total_members"],
                smoke_generations=options["smoke_generations"],
                smoke_batch_size=options["smoke_batch_size"],
                smoke_username=options["smoke_username"],
                seed=options["seed"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Prepared coursework artifacts under {result['output_dir']}."
            )
        )
        self.stdout.write(f"- sample CSV: {result['sample_import_path']}")
        self.stdout.write(f"- manifest: {result['manifest_path']}")
        if result["smoke_result"]:
            self.stdout.write(
                "- smoke data: "
                f"{result['smoke_result']['genealogy_count']} genealogies, "
                f"{result['smoke_result']['total_members']} members"
            )
        if result["branch_result"]:
            self.stdout.write(f"- branch export: {result['branch_result']['output_dir']}")
        if result["benchmark_result"]:
            self.stdout.write(
                f"- benchmark: {result['benchmark_result']['output_path']}"
            )
