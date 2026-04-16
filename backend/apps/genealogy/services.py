from collections import defaultdict

from django.db import connection


MEMBER_FAMILY_LOOKUP_SQL = """
WITH member_family AS (
    SELECT
        'spouse'::text AS relation_kind,
        CASE
            WHEN ma.member_a_id = %s THEN ma.member_b_id
            ELSE ma.member_a_id
        END AS related_member_id,
        '配偶'::text AS relation_label,
        ma.status AS marriage_status,
        ma.start_year,
        ma.end_year,
        NULL::varchar(16) AS parent_role
    FROM marriages ma
    WHERE ma.genealogy_id = %s
      AND ma.status = 'married'
      AND (%s = ma.member_a_id OR %s = ma.member_b_id)

    UNION ALL

    SELECT
        'child'::text AS relation_kind,
        pcr.child_member_id AS related_member_id,
        '子女'::text AS relation_label,
        NULL::varchar(16) AS marriage_status,
        NULL::integer AS start_year,
        NULL::integer AS end_year,
        pcr.parent_role
    FROM parent_child_relations pcr
    WHERE pcr.genealogy_id = %s
      AND pcr.parent_member_id = %s
)
SELECT
    mf.relation_kind,
    mf.relation_label,
    mf.parent_role,
    mf.marriage_status,
    mf.start_year,
    mf.end_year,
    m.member_id,
    m.full_name,
    m.gender,
    m.birth_year,
    m.death_year
FROM member_family mf
INNER JOIN members m
    ON m.genealogy_id = %s
   AND m.member_id = mf.related_member_id
ORDER BY mf.relation_kind, m.member_id;
""".strip()


GENERATION_CTE_SQL = """
WITH RECURSIVE root_members AS (
    SELECT m.member_id
    FROM members m
    WHERE m.genealogy_id = %s
      AND NOT EXISTS (
          SELECT 1
          FROM parent_child_relations pcr
          WHERE pcr.genealogy_id = m.genealogy_id
            AND pcr.child_member_id = m.member_id
      )
),
generation_tree AS (
    SELECT
        rm.member_id,
        1 AS generation_depth,
        ARRAY[rm.member_id]::bigint[] AS path
    FROM root_members rm

    UNION ALL

    SELECT
        pcr.child_member_id,
        gt.generation_depth + 1,
        gt.path || pcr.child_member_id
    FROM generation_tree gt
    INNER JOIN parent_child_relations pcr
        ON pcr.genealogy_id = %s
       AND pcr.parent_member_id = gt.member_id
    WHERE NOT pcr.child_member_id = ANY(gt.path)
),
generation_assignment AS (
    SELECT
        member_id,
        MIN(generation_depth) AS generation_depth
    FROM generation_tree
    GROUP BY member_id
)
"""


COURSE_SQL_SNIPPETS = {
    "member_family_lookup": MEMBER_FAMILY_LOOKUP_SQL.replace("%s", ":param"),
    "gender_summary": """
SELECT
    COUNT(*) AS total_members,
    COUNT(*) FILTER (WHERE gender = 'male') AS male_members,
    COUNT(*) FILTER (WHERE gender = 'female') AS female_members,
    COUNT(*) FILTER (WHERE gender = 'unknown') AS unknown_gender_members,
    COUNT(*) FILTER (WHERE is_living = TRUE) AS living_members
FROM members
WHERE genealogy_id = :genealogy_id;
""".strip(),
    "generation_lifespan": f"""
{GENERATION_CTE_SQL}
SELECT
    ga.generation_depth,
    COUNT(*) AS member_count,
    ROUND(AVG(m.death_year - m.birth_year)::numeric, 2) AS avg_lifespan
FROM generation_assignment ga
INNER JOIN members m
    ON m.member_id = ga.member_id
WHERE m.genealogy_id = %s
  AND m.birth_year IS NOT NULL
  AND m.death_year IS NOT NULL
GROUP BY ga.generation_depth
ORDER BY avg_lifespan DESC NULLS LAST, ga.generation_depth
LIMIT 1;
""".strip(),
    "unmarried_males_over_50": """
SELECT
    m.member_id,
    m.full_name,
    m.birth_year,
    EXTRACT(YEAR FROM CURRENT_DATE)::int - m.birth_year AS age_years
FROM members m
WHERE m.genealogy_id = :genealogy_id
  AND m.gender = 'male'
  AND m.is_living = TRUE
  AND m.birth_year IS NOT NULL
  AND EXTRACT(YEAR FROM CURRENT_DATE)::int - m.birth_year > 50
  AND NOT EXISTS (
      SELECT 1
      FROM marriages ma
      WHERE ma.genealogy_id = m.genealogy_id
        AND ma.status = 'married'
        AND (ma.member_a_id = m.member_id OR ma.member_b_id = m.member_id)
  )
ORDER BY age_years DESC, m.member_id;
""".strip(),
    "early_birth_members": f"""
{GENERATION_CTE_SQL}
, generation_birth_avg AS (
    SELECT
        ga.generation_depth,
        ROUND(AVG(m.birth_year)::numeric, 2) AS avg_birth_year
    FROM generation_assignment ga
    INNER JOIN members m
        ON m.member_id = ga.member_id
    WHERE m.genealogy_id = %s
      AND m.birth_year IS NOT NULL
    GROUP BY ga.generation_depth
)
SELECT
    m.member_id,
    m.full_name,
    ga.generation_depth,
    m.birth_year,
    gba.avg_birth_year
FROM generation_assignment ga
INNER JOIN members m
    ON m.member_id = ga.member_id
INNER JOIN generation_birth_avg gba
    ON gba.generation_depth = ga.generation_depth
WHERE m.genealogy_id = %s
  AND m.birth_year IS NOT NULL
  AND m.birth_year < gba.avg_birth_year
ORDER BY ga.generation_depth, m.birth_year, m.member_id;
""".strip(),
}


def fetchone_dict(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column.name for column in cursor.description]
        row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip(columns, row))


def fetchall_dicts(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column.name for column in cursor.description]
        rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def fetch_genealogy_analytics(genealogy_id):
    gender_summary_sql = """
    SELECT
        COUNT(*) AS total_members,
        COUNT(*) FILTER (WHERE gender = 'male') AS male_members,
        COUNT(*) FILTER (WHERE gender = 'female') AS female_members,
        COUNT(*) FILTER (WHERE gender = 'unknown') AS unknown_gender_members,
        COUNT(*) FILTER (WHERE is_living = TRUE) AS living_members
    FROM members
    WHERE genealogy_id = %s
    """
    generation_lifespan_sql = f"""
    {GENERATION_CTE_SQL}
    SELECT
        ga.generation_depth,
        COUNT(*) AS member_count,
        ROUND(AVG(m.death_year - m.birth_year)::numeric, 2) AS avg_lifespan
    FROM generation_assignment ga
    INNER JOIN members m
        ON m.member_id = ga.member_id
    WHERE m.genealogy_id = %s
      AND m.birth_year IS NOT NULL
      AND m.death_year IS NOT NULL
    GROUP BY ga.generation_depth
    ORDER BY avg_lifespan DESC NULLS LAST, ga.generation_depth
    LIMIT 1
    """
    unmarried_males_sql = """
    SELECT
        m.member_id,
        m.full_name,
        m.birth_year,
        EXTRACT(YEAR FROM CURRENT_DATE)::int - m.birth_year AS age_years
    FROM members m
    WHERE m.genealogy_id = %s
      AND m.gender = 'male'
      AND m.is_living = TRUE
      AND m.birth_year IS NOT NULL
      AND EXTRACT(YEAR FROM CURRENT_DATE)::int - m.birth_year > 50
      AND NOT EXISTS (
          SELECT 1
          FROM marriages ma
          WHERE ma.genealogy_id = m.genealogy_id
            AND ma.status = 'married'
            AND (ma.member_a_id = m.member_id OR ma.member_b_id = m.member_id)
      )
    ORDER BY age_years DESC, m.member_id
    """
    early_birth_members_sql = f"""
    {GENERATION_CTE_SQL}
    , generation_birth_avg AS (
        SELECT
            ga.generation_depth,
            ROUND(AVG(m.birth_year)::numeric, 2) AS avg_birth_year
        FROM generation_assignment ga
        INNER JOIN members m
            ON m.member_id = ga.member_id
        WHERE m.genealogy_id = %s
          AND m.birth_year IS NOT NULL
        GROUP BY ga.generation_depth
    )
    SELECT
        m.member_id,
        m.full_name,
        ga.generation_depth,
        m.birth_year,
        gba.avg_birth_year
    FROM generation_assignment ga
    INNER JOIN members m
        ON m.member_id = ga.member_id
    INNER JOIN generation_birth_avg gba
        ON gba.generation_depth = ga.generation_depth
    WHERE m.genealogy_id = %s
      AND m.birth_year IS NOT NULL
      AND m.birth_year < gba.avg_birth_year
    ORDER BY ga.generation_depth, m.birth_year, m.member_id
    """

    gender_summary = fetchone_dict(gender_summary_sql, [genealogy_id]) or {
        "total_members": 0,
        "male_members": 0,
        "female_members": 0,
        "unknown_gender_members": 0,
        "living_members": 0,
    }
    generation_lifespan = fetchone_dict(
        generation_lifespan_sql,
        [genealogy_id, genealogy_id, genealogy_id],
    )
    unmarried_males_over_50 = fetchall_dicts(unmarried_males_sql, [genealogy_id])
    early_birth_members = fetchall_dicts(
        early_birth_members_sql,
        [genealogy_id, genealogy_id, genealogy_id, genealogy_id],
    )

    total_members = gender_summary["total_members"] or 0
    male_members = gender_summary["male_members"] or 0
    female_members = gender_summary["female_members"] or 0
    gender_ratio = None
    if female_members:
        gender_ratio = round(male_members / female_members, 2)

    return {
        "gender_summary": {
            **gender_summary,
            "gender_ratio_male_to_female": gender_ratio,
        },
        "generation_lifespan": generation_lifespan,
        "unmarried_males_over_50": unmarried_males_over_50,
        "early_birth_members": early_birth_members,
        "sql_snippets": COURSE_SQL_SNIPPETS,
    }


def fetch_member_family_lookup(*, genealogy_id, member_id):
    rows = fetchall_dicts(
        MEMBER_FAMILY_LOOKUP_SQL,
        [
            member_id,
            genealogy_id,
            member_id,
            member_id,
            genealogy_id,
            member_id,
            genealogy_id,
        ],
    )
    spouses = []
    children = []
    for row in rows:
        relation = {
            "member_id": row["member_id"],
            "full_name": row["full_name"],
            "gender": row["gender"],
            "birth_year": row["birth_year"],
            "death_year": row["death_year"],
            "relation_label": row["relation_label"],
        }
        if row["relation_kind"] == "spouse":
            spouses.append(
                {
                    **relation,
                    "status": row["marriage_status"],
                    "start_year": row["start_year"],
                    "end_year": row["end_year"],
                }
            )
        else:
            children.append(
                {
                    **relation,
                    "parent_role": row["parent_role"],
                }
            )
    return {
        "spouses": spouses,
        "children": children,
        "sql": COURSE_SQL_SNIPPETS["member_family_lookup"],
    }


def fetch_root_member_candidates(genealogy_id, limit=20):
    sql = """
    SELECT
        m.member_id,
        m.full_name,
        m.birth_year,
        m.death_year
    FROM members m
    WHERE m.genealogy_id = %s
      AND NOT EXISTS (
          SELECT 1
          FROM parent_child_relations pcr
          WHERE pcr.genealogy_id = m.genealogy_id
            AND pcr.child_member_id = m.member_id
      )
    ORDER BY m.birth_year NULLS FIRST, m.member_id
    LIMIT %s
    """
    return fetchall_dicts(sql, [genealogy_id, limit])


def fetch_ancestor_tree(*, genealogy_id, member_id):
    root_member_sql = """
    SELECT
        member_id,
        full_name,
        gender,
        birth_year,
        death_year
    FROM members
    WHERE genealogy_id = %s
      AND member_id = %s
    """
    ancestor_sql = """
    WITH RECURSIVE ancestor_tree AS (
        SELECT
            pcr.parent_member_id AS ancestor_member_id,
            pcr.child_member_id AS source_member_id,
            pcr.parent_role,
            1 AS depth,
            ARRAY[pcr.child_member_id, pcr.parent_member_id]::bigint[] AS path
        FROM parent_child_relations pcr
        WHERE pcr.genealogy_id = %s
          AND pcr.child_member_id = %s

        UNION ALL

        SELECT
            pcr.parent_member_id AS ancestor_member_id,
            pcr.child_member_id AS source_member_id,
            pcr.parent_role,
            at.depth + 1 AS depth,
            at.path || pcr.parent_member_id
        FROM parent_child_relations pcr
        INNER JOIN ancestor_tree at
            ON pcr.child_member_id = at.ancestor_member_id
        WHERE pcr.genealogy_id = %s
          AND NOT pcr.parent_member_id = ANY(at.path)
    )
    SELECT
        at.depth,
        at.ancestor_member_id AS member_id,
        at.source_member_id,
        at.parent_role,
        m.full_name,
        m.gender,
        m.birth_year,
        m.death_year
    FROM ancestor_tree at
    INNER JOIN members m
        ON m.genealogy_id = %s
       AND m.member_id = at.ancestor_member_id
    ORDER BY at.depth, at.ancestor_member_id
    """
    root_member = fetchone_dict(root_member_sql, [genealogy_id, member_id])
    if root_member is None:
        return None

    flat_nodes = fetchall_dicts(
        ancestor_sql,
        [genealogy_id, member_id, genealogy_id, genealogy_id],
    )
    member_map = {
        root_member["member_id"]: {
            **root_member,
            "relation_to_child": None,
        }
    }
    parent_rows_by_child = defaultdict(list)
    for row in flat_nodes:
        member_map[row["member_id"]] = {
            "member_id": row["member_id"],
            "full_name": row["full_name"],
            "gender": row["gender"],
            "birth_year": row["birth_year"],
            "death_year": row["death_year"],
            "relation_to_child": row["parent_role"],
        }
        parent_rows_by_child[row["source_member_id"]].append(row)

    def build_node(current_member_id, seen=None):
        seen = seen or set()
        member = member_map[current_member_id]
        label_parts = [f"{member['member_id']} - {member['full_name']}"]
        if member["birth_year"] or member["death_year"]:
            birth = member["birth_year"] or "?"
            death = member["death_year"] or "?"
            label_parts.append(f"({birth}-{death})")
        node = {
            "member_id": member["member_id"],
            "full_name": member["full_name"],
            "gender": member["gender"],
            "birth_year": member["birth_year"],
            "death_year": member["death_year"],
            "name": " ".join(label_parts),
            "relation_to_child": member["relation_to_child"],
            "parents": [],
        }
        next_seen = seen | {current_member_id}
        for parent_row in parent_rows_by_child.get(current_member_id, []):
            parent_id = parent_row["member_id"]
            if parent_id in next_seen:
                continue
            node["parents"].append(build_node(parent_id, next_seen))
        return node

    return {
        "root": build_node(root_member["member_id"]),
        "node_count": len(flat_nodes) + 1,
        "max_depth": max((row["depth"] for row in flat_nodes), default=0),
        "flat_nodes": flat_nodes,
    }


def fetch_descendant_tree(*, genealogy_id, root_member_id, max_depth):
    sql = """
    WITH RECURSIVE descendant_candidates AS (
        SELECT
            m.member_id,
            NULL::bigint AS parent_member_id,
            m.full_name,
            m.gender,
            m.birth_year,
            m.death_year,
            0 AS depth,
            ARRAY[m.member_id]::bigint[] AS path
        FROM members m
        WHERE m.genealogy_id = %s
          AND m.member_id = %s

        UNION ALL

        SELECT
            child.member_id,
            pcr.parent_member_id,
            child.full_name,
            child.gender,
            child.birth_year,
            child.death_year,
            dt.depth + 1,
            dt.path || child.member_id
        FROM descendant_candidates dt
        INNER JOIN parent_child_relations pcr
            ON pcr.genealogy_id = %s
           AND pcr.parent_member_id = dt.member_id
        INNER JOIN members child
            ON child.genealogy_id = %s
           AND child.member_id = pcr.child_member_id
        WHERE dt.depth < %s
          AND NOT child.member_id = ANY(dt.path)
    ),
    descendant_tree AS (
        SELECT DISTINCT ON (member_id)
            member_id,
            parent_member_id,
            full_name,
            gender,
            birth_year,
            death_year,
            depth
        FROM descendant_candidates
        ORDER BY member_id, depth, parent_member_id NULLS FIRST
    )
    SELECT
        member_id,
        parent_member_id,
        full_name,
        gender,
        birth_year,
        death_year,
        depth
    FROM descendant_tree
    ORDER BY depth, member_id
    """
    rows = fetchall_dicts(
        sql,
        [genealogy_id, root_member_id, genealogy_id, genealogy_id, max_depth],
    )
    if not rows:
        return None

    node_map = {}
    children_map = defaultdict(list)
    for row in rows:
        label_parts = [f"{row['member_id']} - {row['full_name']}"]
        if row["birth_year"] or row["death_year"]:
            birth = row["birth_year"] or "?"
            death = row["death_year"] or "?"
            label_parts.append(f"({birth}-{death})")
        node_map[row["member_id"]] = {
            "member_id": row["member_id"],
            "parent_member_id": row["parent_member_id"],
            "full_name": row["full_name"],
            "gender": row["gender"],
            "birth_year": row["birth_year"],
            "death_year": row["death_year"],
            "depth": row["depth"],
            "name": " ".join(label_parts),
            "children": [],
        }
        if row["parent_member_id"] is not None:
            children_map[row["parent_member_id"]].append(row["member_id"])

    for parent_id, child_ids in children_map.items():
        node_map[parent_id]["children"] = [node_map[child_id] for child_id in child_ids]

    root_node = node_map[root_member_id]
    return {
        "root": root_node,
        "node_count": len(rows),
        "max_depth": max(row["depth"] for row in rows),
        "flat_nodes": rows,
    }
