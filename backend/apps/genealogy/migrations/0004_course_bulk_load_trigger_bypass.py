from django.db import migrations

FORWARD_SQL = """
CREATE OR REPLACE FUNCTION validate_parent_child_relation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    parent_gender VARCHAR(16);
    parent_birth_year INTEGER;
    child_birth_year INTEGER;
BEGIN
    IF current_setting('genealogy.trust_course_bulk_load', true) = 'on' THEN
        RETURN NEW;
    END IF;

    SELECT m.gender, m.birth_year
    INTO parent_gender, parent_birth_year
    FROM members m
    WHERE m.genealogy_id = NEW.genealogy_id
      AND m.member_id = NEW.parent_member_id;

    SELECT m.birth_year
    INTO child_birth_year
    FROM members m
    WHERE m.genealogy_id = NEW.genealogy_id
      AND m.member_id = NEW.child_member_id;

    IF NEW.parent_role = 'father' AND parent_gender <> 'male' THEN
        RAISE EXCEPTION 'father relation requires parent gender male';
    END IF;

    IF NEW.parent_role = 'mother' AND parent_gender <> 'female' THEN
        RAISE EXCEPTION 'mother relation requires parent gender female';
    END IF;

    IF parent_birth_year IS NOT NULL
       AND child_birth_year IS NOT NULL
       AND parent_birth_year >= child_birth_year THEN
        RAISE EXCEPTION 'parent birth_year must be earlier than child birth_year';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION prevent_parent_child_cycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    has_cycle BOOLEAN;
BEGIN
    IF current_setting('genealogy.trust_course_bulk_load', true) = 'on' THEN
        RETURN NEW;
    END IF;

    WITH RECURSIVE descendants AS (
        SELECT pcr.child_member_id
        FROM parent_child_relations pcr
        WHERE pcr.genealogy_id = NEW.genealogy_id
          AND pcr.parent_member_id = NEW.child_member_id
          AND (TG_OP <> 'UPDATE' OR pcr.relation_id <> NEW.relation_id)

        UNION

        SELECT pcr.child_member_id
        FROM parent_child_relations pcr
        INNER JOIN descendants d
            ON pcr.parent_member_id = d.child_member_id
        WHERE pcr.genealogy_id = NEW.genealogy_id
          AND (TG_OP <> 'UPDATE' OR pcr.relation_id <> NEW.relation_id)
    )
    SELECT EXISTS (
        SELECT 1
        FROM descendants
        WHERE child_member_id = NEW.parent_member_id
    )
    INTO has_cycle;

    IF has_cycle THEN
        RAISE EXCEPTION 'parent-child relation would create a cycle';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_marriage_relation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF current_setting('genealogy.trust_course_bulk_load', true) = 'on' THEN
        RETURN NEW;
    END IF;

    IF NEW.status = 'married' AND EXISTS (
        SELECT 1
        FROM marriages m
        WHERE m.genealogy_id = NEW.genealogy_id
          AND m.status = 'married'
          AND (TG_OP <> 'UPDATE' OR m.marriage_id <> NEW.marriage_id)
          AND (
              m.member_a_id IN (NEW.member_a_id, NEW.member_b_id)
              OR m.member_b_id IN (NEW.member_a_id, NEW.member_b_id)
          )
    ) THEN
        RAISE EXCEPTION 'member already has another active marriage in genealogy %',
            NEW.genealogy_id;
    END IF;

    RETURN NEW;
END;
$$;
"""


REVERSE_SQL = """
CREATE OR REPLACE FUNCTION validate_parent_child_relation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    parent_gender VARCHAR(16);
    parent_birth_year INTEGER;
    child_birth_year INTEGER;
BEGIN
    SELECT m.gender, m.birth_year
    INTO parent_gender, parent_birth_year
    FROM members m
    WHERE m.genealogy_id = NEW.genealogy_id
      AND m.member_id = NEW.parent_member_id;

    SELECT m.birth_year
    INTO child_birth_year
    FROM members m
    WHERE m.genealogy_id = NEW.genealogy_id
      AND m.member_id = NEW.child_member_id;

    IF NEW.parent_role = 'father' AND parent_gender <> 'male' THEN
        RAISE EXCEPTION 'father relation requires parent gender male';
    END IF;

    IF NEW.parent_role = 'mother' AND parent_gender <> 'female' THEN
        RAISE EXCEPTION 'mother relation requires parent gender female';
    END IF;

    IF parent_birth_year IS NOT NULL
       AND child_birth_year IS NOT NULL
       AND parent_birth_year >= child_birth_year THEN
        RAISE EXCEPTION 'parent birth_year must be earlier than child birth_year';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION prevent_parent_child_cycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    has_cycle BOOLEAN;
BEGIN
    WITH RECURSIVE descendants AS (
        SELECT pcr.child_member_id
        FROM parent_child_relations pcr
        WHERE pcr.genealogy_id = NEW.genealogy_id
          AND pcr.parent_member_id = NEW.child_member_id
          AND (TG_OP <> 'UPDATE' OR pcr.relation_id <> NEW.relation_id)

        UNION

        SELECT pcr.child_member_id
        FROM parent_child_relations pcr
        INNER JOIN descendants d
            ON pcr.parent_member_id = d.child_member_id
        WHERE pcr.genealogy_id = NEW.genealogy_id
          AND (TG_OP <> 'UPDATE' OR pcr.relation_id <> NEW.relation_id)
    )
    SELECT EXISTS (
        SELECT 1
        FROM descendants
        WHERE child_member_id = NEW.parent_member_id
    )
    INTO has_cycle;

    IF has_cycle THEN
        RAISE EXCEPTION 'parent-child relation would create a cycle';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_marriage_relation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'married' AND EXISTS (
        SELECT 1
        FROM marriages m
        WHERE m.genealogy_id = NEW.genealogy_id
          AND m.status = 'married'
          AND (TG_OP <> 'UPDATE' OR m.marriage_id <> NEW.marriage_id)
          AND (
              m.member_a_id IN (NEW.member_a_id, NEW.member_b_id)
              OR m.member_b_id IN (NEW.member_a_id, NEW.member_b_id)
          )
    ) THEN
        RAISE EXCEPTION 'member already has another active marriage in genealogy %',
            NEW.genealogy_id;
    END IF;

    RETURN NEW;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("genealogy", "0003_editor_authorization_guardrails"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
