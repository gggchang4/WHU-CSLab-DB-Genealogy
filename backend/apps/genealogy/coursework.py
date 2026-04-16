from __future__ import annotations

from pathlib import Path
import random

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from apps.genealogy.models import Genealogy, Marriage, Member, ParentChildRelation


User = get_user_model()


FOURTH_GENERATION_QUERY = """
WITH RECURSIVE descendant_levels AS (
    SELECT
        pcr.child_member_id AS member_id,
        1 AS depth
    FROM parent_child_relations pcr
    WHERE pcr.genealogy_id = %s
      AND pcr.parent_member_id = %s

    UNION ALL

    SELECT
        pcr.child_member_id AS member_id,
        dl.depth + 1 AS depth
    FROM descendant_levels dl
    INNER JOIN parent_child_relations pcr
        ON pcr.genealogy_id = %s
       AND pcr.parent_member_id = dl.member_id
    WHERE dl.depth < 4
)
SELECT
    m.member_id,
    m.full_name,
    dl.depth
FROM descendant_levels dl
INNER JOIN members m
    ON m.member_id = dl.member_id
WHERE dl.depth = 4
ORDER BY m.member_id;
""".strip()


class RollbackBenchmark(Exception):
    pass


def ensure_operator_user(username: str):
    defaults = {
        "display_name": "Course Operator",
        "email": f"{username}@example.local",
        "is_active": True,
    }
    user, created = User.objects.get_or_create(username=username, defaults=defaults)
    if created:
        user.set_password("CourseOperator123!")
        user.save(update_fields=["password"])
    return user


def build_generation_targets(*, genealogy_count: int, total_members: int, large_members: int, generations: int):
    if genealogy_count < 1:
        raise ValueError("genealogy_count must be at least 1")
    minimum_required = large_members + (genealogy_count - 1) * generations
    if total_members < minimum_required:
        raise ValueError(
            "total_members is too small for the requested genealogy_count, "
            "large_members, and generations"
        )

    if genealogy_count == 1:
        return [total_members]

    remaining = total_members - large_members
    small_genealogy_count = genealogy_count - 1
    base_members = remaining // small_genealogy_count
    extra_members = remaining % small_genealogy_count

    targets = [large_members]
    for index in range(small_genealogy_count):
        target = base_members + (1 if index < extra_members else 0)
        targets.append(target)
    return targets


def _build_member_defaults(*, surname: str, sequence: int, birth_year: int, gender: str):
    current_year = timezone.now().year
    is_living = birth_year >= current_year - 80
    death_year = None
    if not is_living:
        death_year = min(birth_year + 45 + (sequence % 25), current_year - (sequence % 7))

    return {
        "full_name": f"{surname} Member {sequence:06d}",
        "surname": surname,
        "given_name": f"Member {sequence:06d}",
        "gender": gender,
        "birth_year": birth_year,
        "death_year": death_year,
        "is_living": is_living,
        "generation_label": f"G{sequence}",
        "seniority_text": f"No.{sequence}",
        "branch_name": "course-seeded",
        "biography": "Generated for the WHU database coursework benchmark dataset.",
    }


def generate_genealogy_dataset(
    *,
    genealogy: Genealogy,
    operator,
    total_members: int,
    generations: int,
    batch_size: int,
    seed: int,
):
    randomizer = random.Random(seed)
    current_year = timezone.now().year
    base_birth_year = max(1000, current_year - generations * 24 - 120)
    next_sequence = 1

    root_member = Member.objects.create(
        genealogy=genealogy,
        created_by=operator,
        **_build_member_defaults(
            surname=genealogy.surname,
            sequence=next_sequence,
            birth_year=base_birth_year,
            gender="male",
        ),
    )
    next_sequence += 1

    member_count = 1
    lineage_parent = root_member
    candidate_parents = [(root_member, 1)]
    marriage_male_pool = [root_member]
    marriage_female_pool = []

    for depth in range(2, generations + 1):
        child_birth_year = base_birth_year + (depth - 1) * 24
        child = Member.objects.create(
            genealogy=genealogy,
            created_by=operator,
            **_build_member_defaults(
                surname=genealogy.surname,
                sequence=next_sequence,
                birth_year=child_birth_year,
                gender="male",
            ),
        )
        ParentChildRelation.objects.create(
            genealogy=genealogy,
            parent_member=lineage_parent,
            child_member=child,
            parent_role="father",
            created_by=operator,
        )
        lineage_parent = child
        candidate_parents.append((child, depth))
        marriage_male_pool.append(child)
        next_sequence += 1
        member_count += 1

    max_parent_depth = generations + 6
    parent_cursor = 0

    while member_count < total_members:
        members_to_create = min(batch_size, total_members - member_count)
        staged_members = []
        staged_parent_links = []

        for _ in range(members_to_create):
            parent_member, parent_depth = candidate_parents[parent_cursor % len(candidate_parents)]
            parent_cursor += 1

            gender = "male" if randomizer.random() < 0.58 else "female"
            child_birth_year = parent_member.birth_year + 18 + randomizer.randint(0, 11)
            member = Member(
                genealogy=genealogy,
                created_by=operator,
                **_build_member_defaults(
                    surname=genealogy.surname,
                    sequence=next_sequence,
                    birth_year=child_birth_year,
                    gender=gender,
                ),
            )
            staged_members.append(member)
            staged_parent_links.append((parent_member, parent_depth + 1))
            next_sequence += 1

        created_members = Member.objects.bulk_create(
            staged_members,
            batch_size=batch_size,
        )
        relation_batch = []
        for member, (parent_member, depth) in zip(created_members, staged_parent_links, strict=False):
            relation_batch.append(
                ParentChildRelation(
                    genealogy=genealogy,
                    parent_member=parent_member,
                    child_member=member,
                    parent_role="father",
                    created_by=operator,
                )
            )
            if member.gender == "male":
                marriage_male_pool.append(member)
                if depth < max_parent_depth:
                    candidate_parents.append((member, depth))
            else:
                marriage_female_pool.append(member)

        ParentChildRelation.objects.bulk_create(
            relation_batch,
            batch_size=batch_size,
        )
        member_count += len(created_members)

    max_marriages = min(
        len(marriage_male_pool),
        len(marriage_female_pool),
        max(1, total_members // 25),
    )
    marriage_batch = []
    for male_member, female_member in zip(
        marriage_male_pool[:max_marriages],
        marriage_female_pool[:max_marriages],
        strict=False,
    ):
        member_a, member_b = sorted(
            [male_member, female_member],
            key=lambda member: member.member_id,
        )
        start_year = max(
            (member_a.birth_year or base_birth_year) + 20,
            (member_b.birth_year or base_birth_year) + 20,
        )
        marriage_batch.append(
            Marriage(
                genealogy=genealogy,
                member_a=member_a,
                member_b=member_b,
                status="married",
                start_year=start_year,
                created_by=operator,
            )
        )

    if marriage_batch:
        Marriage.objects.bulk_create(
            marriage_batch,
            batch_size=batch_size,
            ignore_conflicts=True,
        )

    return {
        "genealogy_id": genealogy.genealogy_id,
        "title": genealogy.title,
        "member_count": member_count,
        "marriage_count": len(marriage_batch),
        "generations": generations,
    }


def generate_course_dataset(
    *,
    genealogy_count: int,
    total_members: int,
    large_members: int,
    generations: int,
    batch_size: int,
    username: str,
    title_prefix: str,
    surname_prefix: str,
    seed: int,
):
    operator = ensure_operator_user(username)
    targets = build_generation_targets(
        genealogy_count=genealogy_count,
        total_members=total_members,
        large_members=large_members,
        generations=generations,
    )

    results = []
    with transaction.atomic():
        for index, target in enumerate(targets, start=1):
            genealogy = Genealogy.objects.create(
                title=f"{title_prefix} {index:02d}",
                surname=f"{surname_prefix}{index:02d}",
                compiled_at=timezone.now().year,
                description="Generated course dataset for recursion and benchmark validation.",
                created_by=operator,
            )
            result = generate_genealogy_dataset(
                genealogy=genealogy,
                operator=operator,
                total_members=target,
                generations=generations,
                batch_size=batch_size,
                seed=seed + index,
            )
            results.append(result)

    return {
        "operator_username": operator.username,
        "genealogy_count": len(results),
        "total_members": sum(item["member_count"] for item in results),
        "results": results,
    }


def _normalize_bool_text(value: str | None):
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    return None


def import_members_via_copy(*, genealogy_id: int, csv_path: Path, created_by_id: int | None = None):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    with transaction.atomic():
        connection.ensure_connection()
        raw_conn = connection.connection
        with raw_conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TEMP TABLE tmp_member_import (
                    full_name text,
                    surname text,
                    given_name text,
                    gender text,
                    birth_year text,
                    death_year text,
                    is_living text,
                    generation_label text,
                    seniority_text text,
                    branch_name text,
                    biography text
                )
                ON COMMIT DROP
                    """
                )
            csv_content = csv_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
            with cursor.copy(
                """
                COPY tmp_member_import (
                    full_name,
                    surname,
                    given_name,
                    gender,
                    birth_year,
                    death_year,
                    is_living,
                    generation_label,
                    seniority_text,
                    branch_name,
                    biography
                )
                FROM STDIN WITH (FORMAT csv, HEADER true)
                """
            ) as copy:
                copy.write(csv_content)

            cursor.execute("SELECT * FROM tmp_member_import")
            rows = cursor.fetchall()

        members = []
        for row in rows:
            full_name, surname, given_name, gender, birth_year, death_year, is_living, generation_label, seniority_text, branch_name, biography = row
            normalized_gender = (gender or "").strip().lower()
            if normalized_gender not in {"male", "female", "unknown"}:
                normalized_gender = "unknown"

            normalized_living = _normalize_bool_text(is_living)
            parsed_death_year = int(death_year) if death_year else None
            if normalized_living is None:
                normalized_living = parsed_death_year is None

            members.append(
                Member(
                    genealogy_id=genealogy_id,
                    full_name=full_name,
                    surname=surname or "",
                    given_name=given_name or "",
                    gender=normalized_gender,
                    birth_year=int(birth_year) if birth_year else None,
                    death_year=parsed_death_year,
                    is_living=normalized_living,
                    generation_label=generation_label or "",
                    seniority_text=seniority_text or "",
                    branch_name=branch_name or "",
                    biography=biography or "",
                    created_by_id=created_by_id,
                )
            )

        created_members = Member.objects.bulk_create(members, batch_size=2000)

    return {
        "genealogy_id": genealogy_id,
        "csv_path": str(csv_path),
        "imported_count": len(created_members),
    }


def export_branch_via_copy(*, genealogy_id: int, root_member_id: int, output_dir: Path):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    members_path = output_dir / "branch_members.csv"
    relations_path = output_dir / "branch_parent_child_relations.csv"
    marriages_path = output_dir / "branch_marriages.csv"

    branch_cte = f"""
    WITH RECURSIVE branch_members AS (
        SELECT {root_member_id}::bigint AS member_id

        UNION ALL

        SELECT pcr.child_member_id
        FROM branch_members bm
        INNER JOIN parent_child_relations pcr
            ON pcr.genealogy_id = {genealogy_id}
           AND pcr.parent_member_id = bm.member_id
    )
    """

    member_copy_sql = f"""
    COPY (
        {branch_cte}
        SELECT DISTINCT
            m.member_id,
            m.full_name,
            m.surname,
            m.given_name,
            m.gender,
            m.birth_year,
            m.death_year,
            m.is_living,
            m.generation_label,
            m.seniority_text,
            m.branch_name,
            m.biography
        FROM branch_members bm
        INNER JOIN members m
            ON m.genealogy_id = {genealogy_id}
           AND m.member_id = bm.member_id
        ORDER BY m.member_id
    ) TO STDOUT WITH (FORMAT csv, HEADER true)
    """
    relation_copy_sql = f"""
    COPY (
        {branch_cte}
        SELECT
            pcr.relation_id,
            pcr.parent_member_id,
            pcr.child_member_id,
            pcr.parent_role,
            pcr.created_at
        FROM parent_child_relations pcr
        WHERE pcr.genealogy_id = {genealogy_id}
          AND pcr.parent_member_id IN (SELECT member_id FROM branch_members)
          AND pcr.child_member_id IN (SELECT member_id FROM branch_members)
        ORDER BY pcr.relation_id
    ) TO STDOUT WITH (FORMAT csv, HEADER true)
    """
    marriage_copy_sql = f"""
    COPY (
        {branch_cte}
        SELECT
            ma.marriage_id,
            ma.member_a_id,
            ma.member_b_id,
            ma.status,
            ma.start_year,
            ma.end_year,
            ma.description
        FROM marriages ma
        WHERE ma.genealogy_id = {genealogy_id}
          AND ma.member_a_id IN (SELECT member_id FROM branch_members)
          AND ma.member_b_id IN (SELECT member_id FROM branch_members)
        ORDER BY ma.marriage_id
    ) TO STDOUT WITH (FORMAT csv, HEADER true)
    """

    connection.ensure_connection()
    raw_conn = connection.connection
    with raw_conn.cursor() as cursor:
        for copy_sql, output_path in (
            (member_copy_sql, members_path),
            (relation_copy_sql, relations_path),
            (marriage_copy_sql, marriages_path),
        ):
            with output_path.open("wb") as handle:
                with cursor.copy(copy_sql) as copy:
                    for data in copy:
                        if isinstance(data, str):
                            handle.write(data.encode("utf-8"))
                        else:
                            handle.write(bytes(data))

    return {
        "genealogy_id": genealogy_id,
        "root_member_id": root_member_id,
        "output_dir": str(output_dir),
        "files": [
            str(members_path),
            str(relations_path),
            str(marriages_path),
        ],
    }


def _fetch_explain_plan(sql: str, params: list[int]):
    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) {sql}"
    with connection.cursor() as cursor:
        cursor.execute(explain_sql, params)
        return "\n".join(row[0] for row in cursor.fetchall())


def _discover_parent_lookup_indexes():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'parent_child_relations'
              AND indexname IN ('pcr_parent_lookup_idx', 'idx_parent_child_relations_parent')
            ORDER BY indexname
            """
        )
        return [row[0] for row in cursor.fetchall()]


def benchmark_parent_lookup(*, genealogy_id: int, root_member_id: int, output_path: Path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    index_names = _discover_parent_lookup_indexes()

    with_index_plan = _fetch_explain_plan(
        FOURTH_GENERATION_QUERY,
        [genealogy_id, root_member_id, genealogy_id],
    )

    without_index_plan = ""
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                for index_name in index_names:
                    cursor.execute(f'DROP INDEX IF EXISTS "{index_name}"')
            without_index_plan = _fetch_explain_plan(
                FOURTH_GENERATION_QUERY,
                [genealogy_id, root_member_id, genealogy_id],
            )
            raise RollbackBenchmark
    except RollbackBenchmark:
        pass

    report = f"""# Parent Lookup Benchmark

Genealogy ID: {genealogy_id}
Root Member ID: {root_member_id}
Indexes compared: {", ".join(index_names) if index_names else "none found"}

## With Index

```text
{with_index_plan}
```

## Without Index

```text
{without_index_plan}
```
"""
    output_path.write_text(report, encoding="utf-8")

    return {
        "genealogy_id": genealogy_id,
        "root_member_id": root_member_id,
        "index_names": index_names,
        "output_path": str(output_path),
    }
