from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

from django.conf import settings
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


SAMPLE_IMPORT_HEADERS = [
    "full_name",
    "surname",
    "given_name",
    "gender",
    "birth_year",
    "death_year",
    "is_living",
    "generation_label",
    "seniority_text",
    "branch_name",
    "biography",
]

SAMPLE_IMPORT_ROWS = [
    {
        "full_name": "李承安",
        "surname": "李",
        "given_name": "承安",
        "gender": "male",
        "birth_year": "1940",
        "death_year": "2001",
        "is_living": "false",
        "generation_label": "第1世·承字辈",
        "seniority_text": "长房",
        "branch_name": "样例导入支",
        "biography": "用于 PostgreSQL COPY 导入演示的中文族谱样例成员。",
    },
    {
        "full_name": "李宗宁",
        "surname": "李",
        "given_name": "宗宁",
        "gender": "female",
        "birth_year": "1968",
        "death_year": "",
        "is_living": "true",
        "generation_label": "第2世·宗字辈",
        "seniority_text": "次女",
        "branch_name": "样例导入支",
        "biography": "用于课程验收材料的小规模中文成员样例。",
    },
    {
        "full_name": "李宗和",
        "surname": "李",
        "given_name": "宗和",
        "gender": "male",
        "birth_year": "1970",
        "death_year": "",
        "is_living": "true",
        "generation_label": "第2世·宗字辈",
        "seniority_text": "幼子",
        "branch_name": "样例导入支",
        "biography": "用于课程验收材料的小规模中文成员样例。",
    },
]


CHINESE_GENEALOGY_PROFILES = [
    ("李", "陇西李氏宗谱", "陇西堂"),
    ("王", "太原王氏族谱", "太原堂"),
    ("张", "清河张氏家乘", "清河堂"),
    ("刘", "彭城刘氏宗谱", "彭城堂"),
    ("陈", "颍川陈氏族谱", "颍川堂"),
    ("杨", "弘农杨氏宗谱", "弘农堂"),
    ("黄", "江夏黄氏家谱", "江夏堂"),
    ("赵", "天水赵氏族谱", "天水堂"),
    ("周", "汝南周氏宗谱", "汝南堂"),
    ("吴", "延陵吴氏家乘", "延陵堂"),
]

GENERATION_CHARS = list(
    "承宗世泽光大文明仁义礼智信家国永昌盛修齐治平安康福寿和顺兴"
    "德本敦厚敬贤立志绍祖荣先培元启后"
)
MALE_NAME_CHARS = list(
    "安邦成达栋恩峰刚国瀚恒宏华建杰俊康坤良林明宁鹏谦庆瑞森涛"
    "伟文武贤翔新旭彦耀毅勇泽振正志忠"
)
FEMALE_NAME_CHARS = list(
    "安婉宁雅慧兰芳萍蓉珍琳娜敏静洁琴雪霞秀娟英梅华丽云清"
    "怡然欣悦嘉宜淑贞"
)
SPOUSE_SURNAMES = list("林何郭罗郑梁谢宋唐许韩冯邓曹彭曾萧田董袁潘于蒋蔡余杜叶程苏魏吕丁沈任姚")
BRANCH_NAMES = ["长房", "二房", "三房", "四房", "五房", "东支", "南支", "西支", "北支"]
MALE_SENIORITY = ["长子", "次子", "三子", "四子", "幼子"]
FEMALE_SENIORITY = ["长女", "次女", "三女", "四女", "幼女"]
MAX_GENERATED_CHILDREN_PER_FATHER = 6


def ensure_operator_user(username: str):
    defaults = {
        "display_name": "课程数据操作员",
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


def _pick_from(values, index: int):
    return values[index % len(values)]


def _genealogy_profile(*, index: int, title_prefix: str, surname_prefix: str):
    use_default_chinese_profiles = (
        title_prefix == "Course Genealogy" and surname_prefix == "Course"
    )
    if use_default_chinese_profiles:
        surname, title, hall_name = CHINESE_GENEALOGY_PROFILES[
            (index - 1) % len(CHINESE_GENEALOGY_PROFILES)
        ]
        return {
            "title": title,
            "surname": surname,
            "hall_name": hall_name,
            "description": (
                f"{hall_name}{surname}氏课程规模模拟族谱，姓名、字辈、婚配与代际关系"
                "由脚本按中国族谱常见规则生成，用于递归查询、统计分析和性能测试。"
            ),
        }

    surname = f"{surname_prefix}{index:02d}"
    return {
        "title": f"{title_prefix} {index:02d}",
        "surname": surname,
        "hall_name": f"{surname}堂",
        "description": "Generated course dataset for recursion and benchmark validation.",
    }


def _life_fields(*, birth_year: int, sequence: int, current_year: int):
    age = current_year - birth_year
    if age <= 82 or (age <= 94 and sequence % 9 == 0):
        return True, None

    lifespan = 58 + (sequence * 7) % 34
    death_year = min(birth_year + lifespan, current_year - 1 - (sequence % 5))
    return False, max(birth_year, death_year)


def _generation_char(generation_depth: int):
    return _pick_from(GENERATION_CHARS, generation_depth - 1)


def _blood_given_name(*, sequence: int, generation_depth: int, gender: str):
    generation_char = _generation_char(generation_depth)
    name_pool = FEMALE_NAME_CHARS if gender == "female" else MALE_NAME_CHARS
    name_index = sequence + generation_depth * 997
    name_char = _pick_from(name_pool, name_index)
    if name_char == generation_char:
        name_char = _pick_from(name_pool, sequence * 13 + generation_depth * 7 + 1)
    return f"{generation_char}{name_char}"


def _spouse_surname(*, family_surname: str, sequence: int):
    choices = [surname for surname in SPOUSE_SURNAMES if surname != family_surname]
    return _pick_from(choices, sequence * 7)


def _spouse_given_name(*, sequence: int):
    name_index = sequence * 3
    first = _pick_from(FEMALE_NAME_CHARS, name_index)
    second = _pick_from(FEMALE_NAME_CHARS, name_index // len(FEMALE_NAME_CHARS) + 11)
    if second == first:
        second = _pick_from(FEMALE_NAME_CHARS, sequence * 13 + 9)
    return f"{first}{second}"


def _seniority_text(*, sequence: int, gender: str):
    labels = FEMALE_SENIORITY if gender == "female" else MALE_SENIORITY
    return _pick_from(labels, sequence - 1)


def _branch_name(*, sequence: int, parent_branch: str | None = None):
    if parent_branch and parent_branch != "始迁祖支":
        return parent_branch
    return _pick_from(BRANCH_NAMES, sequence - 1)


def _father_child_capacity(*, sequence: int, generation_depth: int):
    return 2 + ((sequence + generation_depth * 3) % (MAX_GENERATED_CHILDREN_PER_FATHER - 1))


def _reserve_unique_member_defaults(defaults: dict, used_full_names: set[str]):
    used_full_names.add(defaults["full_name"])
    return defaults


def _set_parent_cycle_trigger(*, enabled: bool):
    if connection.vendor != "postgresql":
        return

    action = "ENABLE" if enabled else "DISABLE"
    with connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE parent_child_relations {action} TRIGGER "
            "trg_parent_child_relations_no_cycle"
        )


def _assert_parent_edges_increase_birth_year():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM parent_child_relations pcr
            INNER JOIN members parent_member
                ON parent_member.member_id = pcr.parent_member_id
            INNER JOIN members child_member
                ON child_member.member_id = pcr.child_member_id
            WHERE parent_member.birth_year IS NOT NULL
              AND child_member.birth_year IS NOT NULL
              AND parent_member.birth_year >= child_member.birth_year
            """
        )
        invalid_edges = cursor.fetchone()[0]

    if invalid_edges:
        raise ValueError(
            "Generated parent-child data contains non-increasing birth years; "
            "this would violate genealogy chronology and may imply a cycle."
        )


def _assert_no_parent_child_isolated_members(*, genealogy_ids: list[int]):
    if not genealogy_ids:
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM members m
            WHERE m.genealogy_id = ANY(%s)
              AND NOT EXISTS (
                  SELECT 1
                  FROM parent_child_relations pcr
                  WHERE pcr.genealogy_id = m.genealogy_id
                    AND (
                        pcr.parent_member_id = m.member_id
                        OR pcr.child_member_id = m.member_id
                    )
              )
            """,
            [genealogy_ids],
        )
        isolated_members = cursor.fetchone()[0]

    if isolated_members:
        raise ValueError(
            "Generated genealogy data contains members without any parent-child "
            "connection; every generated member must have at least a parent or child."
        )


def _build_member_defaults(
    *,
    surname: str,
    sequence: int,
    birth_year: int,
    gender: str,
    generation_depth: int,
    branch_name: str,
    current_year: int,
):
    is_living, death_year = _life_fields(
        birth_year=birth_year,
        sequence=sequence,
        current_year=current_year,
    )
    given_name = _blood_given_name(
        sequence=sequence,
        generation_depth=generation_depth,
        gender=gender,
    )

    return {
        "full_name": f"{surname}{given_name}",
        "surname": surname,
        "given_name": given_name,
        "gender": gender,
        "birth_year": birth_year,
        "death_year": death_year,
        "is_living": is_living,
        "generation_label": f"第{generation_depth}世·{_generation_char(generation_depth)}字辈",
        "seniority_text": _seniority_text(sequence=sequence, gender=gender),
        "branch_name": branch_name,
        "biography": (
            f"{surname}{given_name}，{surname}氏第{generation_depth}世，属{branch_name}。"
            "本记录由课程数据脚本生成，用于展示中文姓名、字辈、分支和亲子链路。"
        ),
    }


def _build_spouse_defaults(
    *,
    family_surname: str,
    sequence: int,
    birth_year: int,
    generation_depth: int,
    spouse_surname: str,
    branch_name: str,
    current_year: int,
):
    is_living, death_year = _life_fields(
        birth_year=birth_year,
        sequence=sequence,
        current_year=current_year,
    )
    given_name = _spouse_given_name(sequence=sequence)
    full_name = f"{spouse_surname}{given_name}"
    return {
        "full_name": full_name,
        "surname": spouse_surname,
        "given_name": given_name,
        "gender": "female",
        "birth_year": birth_year,
        "death_year": death_year,
        "is_living": is_living,
        "generation_label": f"配偶·第{generation_depth}世",
        "seniority_text": "配偶",
        "branch_name": f"{family_surname}氏{branch_name}姻亲",
        "biography": (
            f"{full_name}为{family_surname}氏{branch_name}第{generation_depth}世配偶。"
            "配偶采用外姓生成，避免同姓近亲婚配，用于婚姻关系与亲缘路径演示。"
        ),
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
    max_parent_depth = generations + 6
    base_birth_year = max(960, current_year - (generations - 1) * 28 - 65)
    spouse_target = min(
        max(1, total_members // 25),
        max(0, total_members - generations),
    )
    blood_target = total_members - spouse_target
    next_sequence = 1
    used_full_names: set[str] = set()

    root_member = Member.objects.create(
        genealogy=genealogy,
        created_by=operator,
        **_reserve_unique_member_defaults(
            _build_member_defaults(
                surname=genealogy.surname,
                sequence=next_sequence,
                birth_year=base_birth_year,
                gender="male",
                generation_depth=1,
                branch_name="始迁祖支",
                current_year=current_year,
            ),
            used_full_names,
        ),
    )
    next_sequence += 1

    member_count = 1
    lineage_parent = root_member
    candidate_parents = [(root_member, 1, "长房")]
    marriage_male_pool = [(root_member, 1, "长房")]
    child_counts_by_father_id: dict[int, int] = defaultdict(int)
    child_capacity_by_father_id = {
        root_member.member_id: _father_child_capacity(sequence=1, generation_depth=1)
    }
    children_by_father_id: dict[int, list[Member]] = defaultdict(list)

    for depth in range(2, generations + 1):
        if member_count >= blood_target:
            break
        child_sequence = next_sequence
        branch_name = "长房"
        child_birth_year = base_birth_year + (depth - 1) * 28
        child = Member.objects.create(
            genealogy=genealogy,
            created_by=operator,
            **_reserve_unique_member_defaults(
                _build_member_defaults(
                    surname=genealogy.surname,
                    sequence=child_sequence,
                    birth_year=child_birth_year,
                    gender="male",
                    generation_depth=depth,
                    branch_name=branch_name,
                    current_year=current_year,
                ),
                used_full_names,
            ),
        )
        ParentChildRelation.objects.create(
            genealogy=genealogy,
            parent_member=lineage_parent,
            child_member=child,
            parent_role="father",
            created_by=operator,
        )
        child_counts_by_father_id[lineage_parent.member_id] += 1
        children_by_father_id[lineage_parent.member_id].append(child)
        lineage_parent = child
        if child.birth_year <= current_year - 36:
            candidate_parents.append((child, depth, branch_name))
            child_capacity_by_father_id[child.member_id] = _father_child_capacity(
                sequence=child_sequence,
                generation_depth=depth,
            )
        marriage_male_pool.append((child, depth, branch_name))
        next_sequence += 1
        member_count += 1

    parent_cursor = 0

    def available_parent_slots():
        return sum(
            max(
                0,
                child_capacity_by_father_id.get(parent.member_id, 0)
                - child_counts_by_father_id[parent.member_id],
            )
            for parent, _depth, _branch in candidate_parents
        )

    def next_parent_with_capacity():
        nonlocal parent_cursor

        checked = 0
        while checked < len(candidate_parents):
            parent_member, parent_depth, parent_branch = candidate_parents[
                parent_cursor % len(candidate_parents)
            ]
            parent_cursor += 1
            checked += 1
            if (
                child_counts_by_father_id[parent_member.member_id]
                < child_capacity_by_father_id.get(parent_member.member_id, 0)
            ):
                return parent_member, parent_depth, parent_branch

        raise ValueError(
            "Generated parent pool ran out of realistic child capacity before "
            "reaching the target member count."
        )

    while member_count < blood_target:
        members_to_create = min(
            batch_size,
            blood_target - member_count,
            available_parent_slots(),
        )
        if members_to_create <= 0:
            raise ValueError(
                "Generated parent pool ran out of realistic child capacity before "
                "reaching the target member count."
            )

        staged_members = []
        staged_parent_links = []

        for _ in range(members_to_create):
            parent_member, parent_depth, parent_branch = next_parent_with_capacity()

            gender = "male" if randomizer.random() < 0.58 else "female"
            child_birth_year = parent_member.birth_year + 22 + randomizer.randint(0, 10)
            if child_birth_year > current_year:
                child_birth_year = current_year - randomizer.randint(0, 2)
            child_depth = parent_depth + 1
            branch_name = _branch_name(
                sequence=next_sequence,
                parent_branch=parent_branch,
            )
            child_sequence = next_sequence
            member = Member(
                genealogy=genealogy,
                created_by=operator,
                **_reserve_unique_member_defaults(
                    _build_member_defaults(
                        surname=genealogy.surname,
                        sequence=child_sequence,
                        birth_year=child_birth_year,
                        gender=gender,
                        generation_depth=child_depth,
                        branch_name=branch_name,
                        current_year=current_year,
                    ),
                    used_full_names,
                ),
            )
            staged_members.append(member)
            staged_parent_links.append(
                (parent_member, child_depth, branch_name, child_sequence)
            )
            child_counts_by_father_id[parent_member.member_id] += 1
            next_sequence += 1

        created_members = Member.objects.bulk_create(
            staged_members,
            batch_size=batch_size,
        )
        relation_batch = []
        for member, (parent_member, depth, branch_name, child_sequence) in zip(
            created_members,
            staged_parent_links,
            strict=False,
        ):
            relation_batch.append(
                ParentChildRelation(
                    genealogy=genealogy,
                    parent_member=parent_member,
                    child_member=member,
                    parent_role="father",
                    created_by=operator,
                )
            )
            children_by_father_id[parent_member.member_id].append(member)
            if member.gender == "male":
                marriage_male_pool.append((member, depth, branch_name))
                if depth < max_parent_depth and member.birth_year <= current_year - 36:
                    candidate_parents.append((member, depth, branch_name))
                    child_capacity_by_father_id[member.member_id] = _father_child_capacity(
                        sequence=child_sequence,
                        generation_depth=depth,
                    )

        ParentChildRelation.objects.bulk_create(
            relation_batch,
            batch_size=batch_size,
        )
        member_count += len(created_members)

    remaining_spouses = total_members - member_count
    eligible_marriage_males = [
        item
        for item in marriage_male_pool
        if item[0].birth_year <= current_year - 22
        and children_by_father_id.get(item[0].member_id)
    ]
    max_marriages = min(len(eligible_marriage_males), remaining_spouses)
    selected_males = []
    if max_marriages:
        step = max(1, len(eligible_marriage_males) // max_marriages)
        for index in range(0, len(eligible_marriage_males), step):
            selected_males.append(eligible_marriage_males[index])
            if len(selected_males) >= max_marriages:
                break

    spouse_members = []
    spouse_links = []
    for male_member, generation_depth, branch_name in selected_males:
        spouse_birth_year = male_member.birth_year + randomizer.randint(-4, 4)
        spouse_birth_year = min(spouse_birth_year, current_year - 18)
        spouse_surname = _spouse_surname(
            family_surname=genealogy.surname,
            sequence=next_sequence,
        )
        spouse_members.append(
            Member(
                genealogy=genealogy,
                created_by=operator,
                **_reserve_unique_member_defaults(
                    _build_spouse_defaults(
                        family_surname=genealogy.surname,
                        sequence=next_sequence,
                        birth_year=spouse_birth_year,
                        generation_depth=generation_depth,
                        spouse_surname=spouse_surname,
                        branch_name=branch_name,
                        current_year=current_year,
                    ),
                    used_full_names,
                ),
            )
        )
        spouse_links.append(male_member)
        next_sequence += 1

    created_spouses = []
    if spouse_members:
        created_spouses = Member.objects.bulk_create(
            spouse_members,
            batch_size=batch_size,
        )

    marriage_batch = []
    mother_relation_batch = []
    for male_member, female_member in zip(spouse_links, created_spouses, strict=False):
        member_a, member_b = sorted(
            [male_member, female_member],
            key=lambda member: member.member_id,
        )
        start_year = max(
            (male_member.birth_year or base_birth_year) + 22,
            (female_member.birth_year or base_birth_year) + 18,
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
        for child_member in children_by_father_id.get(male_member.member_id, []):
            mother_relation_batch.append(
                ParentChildRelation(
                    genealogy=genealogy,
                    parent_member=female_member,
                    child_member=child_member,
                    parent_role="mother",
                    created_by=operator,
                )
            )

    if marriage_batch:
        Marriage.objects.bulk_create(
            marriage_batch,
            batch_size=batch_size,
            ignore_conflicts=True,
        )
    if mother_relation_batch:
        ParentChildRelation.objects.bulk_create(
            mother_relation_batch,
            batch_size=batch_size,
            ignore_conflicts=True,
        )

    return {
        "genealogy_id": genealogy.genealogy_id,
        "title": genealogy.title,
        "member_count": member_count + len(created_spouses),
        "marriage_count": len(marriage_batch),
        "mother_relation_count": len(mother_relation_batch),
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
    clear_existing: bool = False,
):
    operator = ensure_operator_user(username)
    targets = build_generation_targets(
        genealogy_count=genealogy_count,
        total_members=total_members,
        large_members=large_members,
        generations=generations,
    )

    results = []
    cycle_trigger_disabled = False
    use_fast_parent_load = (
        connection.vendor == "postgresql"
        and not connection.in_atomic_block
        and total_members >= 1000
    )
    if use_fast_parent_load:
        _set_parent_cycle_trigger(enabled=False)
        cycle_trigger_disabled = True
    try:
        with transaction.atomic():
            if clear_existing:
                Genealogy.objects.all().delete()

            for index, target in enumerate(targets, start=1):
                profile = _genealogy_profile(
                    index=index,
                    title_prefix=title_prefix,
                    surname_prefix=surname_prefix,
                )
                genealogy = Genealogy.objects.create(
                    title=profile["title"],
                    surname=profile["surname"],
                    compiled_at=timezone.now().year,
                    description=profile["description"],
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
            _assert_parent_edges_increase_birth_year()
            _assert_no_parent_child_isolated_members(
                genealogy_ids=[item["genealogy_id"] for item in results]
            )
    finally:
        if cycle_trigger_disabled:
            _set_parent_cycle_trigger(enabled=True)

    return {
        "operator_username": operator.username,
        "genealogy_count": len(results),
        "total_members": sum(item["member_count"] for item in results),
        "results": results,
    }


def _get_genealogy_or_error(genealogy_id: int):
    try:
        return Genealogy.objects.get(genealogy_id=genealogy_id)
    except Genealogy.DoesNotExist as exc:
        raise ValueError(f"Genealogy {genealogy_id} does not exist.") from exc


def _get_member_or_error(*, genealogy_id: int, member_id: int):
    try:
        return Member.objects.get(genealogy_id=genealogy_id, member_id=member_id)
    except Member.DoesNotExist as exc:
        raise ValueError(
            f"Root member {member_id} does not exist in genealogy {genealogy_id}."
        ) from exc


def _find_root_member_id(genealogy_id: int):
    genealogy = _get_genealogy_or_error(genealogy_id)
    root = (
        Member.objects.filter(genealogy_id=genealogy_id)
        .filter(surname__in=[genealogy.surname, ""])
        .exclude(parent_relations__genealogy_id=genealogy_id)
        .filter(children_relations__genealogy_id=genealogy_id)
        .order_by("birth_year", "member_id")
        .first()
    )
    if root is None:
        return None
    return root.member_id


def write_sample_import_csv(output_dir: Path):
    sample_dir = Path(output_dir) / "sample-import"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_path = sample_dir / "members.csv"
    with sample_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_IMPORT_HEADERS)
        writer.writeheader()
        writer.writerows(SAMPLE_IMPORT_ROWS)
    return sample_path


def _artifact_command(command_name: str, **options):
    parts = [r".\.venv\Scripts\python.exe", r"backend\manage.py", command_name]
    for name, value in options.items():
        if value is None:
            continue
        parts.extend([f"--{name.replace('_', '-')}", str(value)])
    return " ".join(parts)


def write_artifact_manifest(
    *,
    output_dir: Path,
    sample_import_path: Path,
    genealogy_id: int | None,
    root_member_id: int | None,
    branch_export_dir: Path | None,
    benchmark_path: Path | None,
    smoke_result: dict | None,
):
    manifest_path = Path(output_dir) / "artifact-manifest.md"
    db_settings = settings.DATABASES["default"]
    database_lines = [
        f"- Engine: `{db_settings.get('ENGINE', '')}`",
        f"- Name: `{db_settings.get('NAME', '')}`",
        f"- User: `{db_settings.get('USER', '')}`",
        f"- Host: `{db_settings.get('HOST', '')}`",
        f"- Port: `{db_settings.get('PORT', '')}`",
        "- Password: omitted intentionally",
    ]
    generated_paths = [
        f"- Sample import CSV: `{sample_import_path}`",
        f"- Manifest: `{manifest_path}`",
    ]
    if branch_export_dir is not None:
        generated_paths.extend(
            [
                f"- Branch export directory: `{branch_export_dir}`",
                f"- Branch members CSV: `{branch_export_dir / 'branch_members.csv'}`",
                "- Branch parent-child CSV: "
                f"`{branch_export_dir / 'branch_parent_child_relations.csv'}`",
                f"- Branch marriages CSV: `{branch_export_dir / 'branch_marriages.csv'}`",
            ]
        )
    if benchmark_path is not None:
        generated_paths.append(f"- Parent lookup benchmark: `{benchmark_path}`")

    commands = [
        _artifact_command(
            "prepare_coursework_artifacts",
            genealogy_id=genealogy_id,
            root_member_id=root_member_id,
        ),
        _artifact_command(
            "import_members_copy",
            genealogy_id=genealogy_id or "<genealogy_id>",
            csv=sample_import_path,
        ),
        _artifact_command(
            "export_branch_copy",
            genealogy_id=genealogy_id or "<genealogy_id>",
            root_member_id=root_member_id or "<root_member_id>",
            output_dir=branch_export_dir or "output/coursework/branch-export",
        ),
        _artifact_command(
            "benchmark_parent_lookup",
            genealogy_id=genealogy_id or "<genealogy_id>",
            root_member_id=root_member_id or "<root_member_id>",
            output=benchmark_path or "output/coursework/benchmarks/parent_lookup.md",
        ),
        _artifact_command("generate_course_dataset"),
    ]

    smoke_lines = ["- Smoke data: not created"]
    if smoke_result is not None:
        smoke_lines = [
            f"- Smoke operator: `{smoke_result['operator_username']}`",
            f"- Smoke genealogies: `{smoke_result['genealogy_count']}`",
            f"- Smoke members: `{smoke_result['total_members']}`",
        ]
        for item in smoke_result["results"]:
            smoke_lines.append(
                "- Smoke genealogy: "
                f"`{item['genealogy_id']}` / `{item['title']}` / "
                f"`{item['member_count']}` members"
            )

    manifest = f"""# Coursework Artifact Manifest

Generated at: {timezone.now().isoformat()}

## Database

{chr(10).join(database_lines)}

## Artifact Inputs

- Genealogy ID: `{genealogy_id if genealogy_id is not None else 'not selected'}`
- Root member ID: `{root_member_id if root_member_id is not None else 'not selected'}`

## Generated Paths

{chr(10).join(generated_paths)}

## Smoke Data

{chr(10).join(smoke_lines)}

## Reproduction Commands

```powershell
{chr(10).join(commands)}
```
"""
    manifest_path.write_text(manifest, encoding="utf-8")
    return manifest_path


def prepare_coursework_artifacts(
    *,
    output_dir: Path,
    genealogy_id: int | None = None,
    root_member_id: int | None = None,
    create_smoke_data: bool = False,
    smoke_total_members: int = 24,
    smoke_generations: int = 5,
    smoke_batch_size: int = 12,
    smoke_username: str = "course_smoke_operator",
    seed: int = 20260416,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_import_path = write_sample_import_csv(output_dir)

    smoke_result = None
    if create_smoke_data:
        smoke_result = generate_course_dataset(
            genealogy_count=1,
            total_members=smoke_total_members,
            large_members=smoke_total_members,
            generations=smoke_generations,
            batch_size=smoke_batch_size,
            username=smoke_username,
            title_prefix="Course Smoke Genealogy",
            surname_prefix="Smoke",
            seed=seed,
        )
        if genealogy_id is None:
            genealogy_id = smoke_result["results"][0]["genealogy_id"]

    if genealogy_id is not None:
        _get_genealogy_or_error(genealogy_id)
        if root_member_id is None:
            root_member_id = _find_root_member_id(genealogy_id)
        if root_member_id is not None:
            _get_member_or_error(
                genealogy_id=genealogy_id,
                member_id=root_member_id,
            )

    branch_export_dir = None
    benchmark_path = None
    branch_result = None
    benchmark_result = None
    if genealogy_id is not None and root_member_id is not None:
        branch_export_dir = output_dir / "branch-export"
        benchmark_path = output_dir / "benchmarks" / "parent_lookup.md"
        branch_result = export_branch_via_copy(
            genealogy_id=genealogy_id,
            root_member_id=root_member_id,
            output_dir=branch_export_dir,
        )
        benchmark_result = benchmark_parent_lookup(
            genealogy_id=genealogy_id,
            root_member_id=root_member_id,
            output_path=benchmark_path,
        )

    manifest_path = write_artifact_manifest(
        output_dir=output_dir,
        sample_import_path=sample_import_path,
        genealogy_id=genealogy_id,
        root_member_id=root_member_id,
        branch_export_dir=branch_export_dir,
        benchmark_path=benchmark_path,
        smoke_result=smoke_result,
    )

    return {
        "output_dir": str(output_dir),
        "sample_import_path": str(sample_import_path),
        "manifest_path": str(manifest_path),
        "genealogy_id": genealogy_id,
        "root_member_id": root_member_id,
        "branch_result": branch_result,
        "benchmark_result": benchmark_result,
        "smoke_result": smoke_result,
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
    _get_genealogy_or_error(genealogy_id)

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
    _get_genealogy_or_error(genealogy_id)
    _get_member_or_error(genealogy_id=genealogy_id, member_id=root_member_id)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    members_path = output_dir / "branch_members.csv"
    relations_path = output_dir / "branch_parent_child_relations.csv"
    marriages_path = output_dir / "branch_marriages.csv"

    branch_cte = f"""
    WITH RECURSIVE descendant_members AS (
        SELECT {root_member_id}::bigint AS member_id

        UNION ALL

        SELECT pcr.child_member_id
        FROM descendant_members dm
        INNER JOIN parent_child_relations pcr
            ON pcr.genealogy_id = {genealogy_id}
           AND pcr.parent_member_id = dm.member_id
    ),
    branch_members AS (
        SELECT member_id
        FROM descendant_members

        UNION

        SELECT
            CASE
                WHEN ma.member_a_id = dm.member_id THEN ma.member_b_id
                ELSE ma.member_a_id
            END AS member_id
        FROM descendant_members dm
        INNER JOIN marriages ma
            ON ma.genealogy_id = {genealogy_id}
           AND ma.status = 'married'
           AND (ma.member_a_id = dm.member_id OR ma.member_b_id = dm.member_id)
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
          AND pcr.child_member_id IN (SELECT member_id FROM descendant_members)
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
          AND (
              ma.member_a_id IN (SELECT member_id FROM descendant_members)
              OR ma.member_b_id IN (SELECT member_id FROM descendant_members)
          )
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
              AND indexdef ILIKE '%%parent_member_id%%'
            ORDER BY indexname
            """
        )
        return [row[0] for row in cursor.fetchall()]


def benchmark_parent_lookup(*, genealogy_id: int, root_member_id: int, output_path: Path):
    _get_genealogy_or_error(genealogy_id)
    _get_member_or_error(genealogy_id=genealogy_id, member_id=root_member_id)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    index_names = _discover_parent_lookup_indexes()

    with_index_plan = _fetch_explain_plan(
        FOURTH_GENERATION_QUERY,
        [genealogy_id, root_member_id, genealogy_id],
    )

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_indexscan = off")
            cursor.execute("SET LOCAL enable_bitmapscan = off")
            cursor.execute("SET LOCAL enable_indexonlyscan = off")
        without_index_plan = _fetch_explain_plan(
            FOURTH_GENERATION_QUERY,
            [genealogy_id, root_member_id, genealogy_id],
        )

    report = f"""# Parent Lookup Benchmark

Genealogy ID: {genealogy_id}
Root Member ID: {root_member_id}
Indexes compared: {", ".join(index_names) if index_names else "none found"}
Without-index method: PostgreSQL index and bitmap scans are disabled with SET LOCAL inside a transaction, so schema indexes remain intact.

## With Index

```text
{with_index_plan}
```

## Without Index Scan

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
