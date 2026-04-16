from django.core.management.base import BaseCommand

from apps.genealogy.coursework import generate_course_dataset


class Command(BaseCommand):
    help = "Generate course-scale genealogy datasets for recursion and benchmark validation."

    def add_arguments(self, parser):
        parser.add_argument("--genealogy-count", type=int, default=10)
        parser.add_argument("--total-members", type=int, default=100000)
        parser.add_argument("--large-members", type=int, default=50000)
        parser.add_argument("--generations", type=int, default=30)
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument("--username", default="course_operator")
        parser.add_argument("--title-prefix", default="Course Genealogy")
        parser.add_argument("--surname-prefix", default="Course")
        parser.add_argument("--seed", type=int, default=20260416)

    def handle(self, *args, **options):
        result = generate_course_dataset(
            genealogy_count=options["genealogy_count"],
            total_members=options["total_members"],
            large_members=options["large_members"],
            generations=options["generations"],
            batch_size=options["batch_size"],
            username=options["username"],
            title_prefix=options["title_prefix"],
            surname_prefix=options["surname_prefix"],
            seed=options["seed"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Generated {result['genealogy_count']} genealogies with "
                f"{result['total_members']} members in total."
            )
        )
        for item in result["results"]:
            self.stdout.write(
                f"- genealogy_id={item['genealogy_id']} "
                f"title={item['title']} "
                f"members={item['member_count']} "
                f"marriages={item['marriage_count']} "
                f"generations={item['generations']}"
            )

