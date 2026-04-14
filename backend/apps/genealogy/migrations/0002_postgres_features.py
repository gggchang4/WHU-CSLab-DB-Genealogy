from django.db import migrations


FORWARD_SQL = """
ALTER TABLE members
    ADD CONSTRAINT uq_members_genealogy_member UNIQUE (genealogy_id, member_id);

ALTER TABLE member_events
    ADD CONSTRAINT fk_member_events_member_pair
    FOREIGN KEY (genealogy_id, member_id)
    REFERENCES members (genealogy_id, member_id)
    ON DELETE CASCADE;

ALTER TABLE parent_child_relations
    ADD CONSTRAINT fk_parent_child_relations_parent_pair
    FOREIGN KEY (genealogy_id, parent_member_id)
    REFERENCES members (genealogy_id, member_id)
    ON DELETE CASCADE;

ALTER TABLE parent_child_relations
    ADD CONSTRAINT fk_parent_child_relations_child_pair
    FOREIGN KEY (genealogy_id, child_member_id)
    REFERENCES members (genealogy_id, member_id)
    ON DELETE CASCADE;

ALTER TABLE marriages
    ADD CONSTRAINT fk_marriages_member_a_pair
    FOREIGN KEY (genealogy_id, member_a_id)
    REFERENCES members (genealogy_id, member_id)
    ON DELETE CASCADE;

ALTER TABLE marriages
    ADD CONSTRAINT fk_marriages_member_b_pair
    FOREIGN KEY (genealogy_id, member_b_id)
    REFERENCES members (genealogy_id, member_id)
    ON DELETE CASCADE;

CREATE OR REPLACE FUNCTION validate_genealogy_invitation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    inviter_is_authorized BOOLEAN;
    genealogy_owner BIGINT;
BEGIN
    SELECT g.created_by
    INTO genealogy_owner
    FROM genealogies g
    WHERE g.genealogy_id = NEW.genealogy_id;

    inviter_is_authorized := (
        genealogy_owner = NEW.inviter_user_id
        OR EXISTS (
            SELECT 1
            FROM genealogy_collaborators gc
            WHERE gc.genealogy_id = NEW.genealogy_id
              AND gc.user_id = NEW.inviter_user_id
        )
    );

    IF NOT inviter_is_authorized THEN
        RAISE EXCEPTION 'inviter % is not authorized for genealogy %',
            NEW.inviter_user_id, NEW.genealogy_id;
    END IF;

    IF genealogy_owner = NEW.invitee_user_id THEN
        RAISE EXCEPTION 'genealogy owner % cannot be invited as collaborator',
            NEW.invitee_user_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM genealogy_collaborators gc
        WHERE gc.genealogy_id = NEW.genealogy_id
          AND gc.user_id = NEW.invitee_user_id
    ) THEN
        RAISE EXCEPTION 'invitee % is already a collaborator of genealogy %',
            NEW.invitee_user_id, NEW.genealogy_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_genealogy_collaborator()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    invitation_genealogy_id BIGINT;
    invitation_invitee_user_id BIGINT;
    invitation_status VARCHAR(16);
    actor_is_authorized BOOLEAN;
    genealogy_owner BIGINT;
BEGIN
    SELECT gi.genealogy_id, gi.invitee_user_id, gi.status
    INTO invitation_genealogy_id, invitation_invitee_user_id, invitation_status
    FROM genealogy_invitations gi
    WHERE gi.invitation_id = NEW.source_invitation_id;

    IF invitation_genealogy_id IS NULL THEN
        RAISE EXCEPTION 'source invitation % does not exist', NEW.source_invitation_id;
    END IF;

    IF invitation_genealogy_id <> NEW.genealogy_id THEN
        RAISE EXCEPTION 'source invitation genealogy does not match collaborator genealogy';
    END IF;

    IF invitation_invitee_user_id <> NEW.user_id THEN
        RAISE EXCEPTION 'source invitation invitee does not match collaborator user';
    END IF;

    IF invitation_status <> 'accepted' THEN
        RAISE EXCEPTION 'source invitation % must be accepted before collaborator activation',
            NEW.source_invitation_id;
    END IF;

    IF NEW.added_by IS NOT NULL THEN
        SELECT g.created_by
        INTO genealogy_owner
        FROM genealogies g
        WHERE g.genealogy_id = NEW.genealogy_id;

        actor_is_authorized := (
            genealogy_owner = NEW.added_by
            OR NEW.user_id = NEW.added_by
            OR EXISTS (
                SELECT 1
                FROM genealogy_collaborators gc
                WHERE gc.genealogy_id = NEW.genealogy_id
                  AND gc.user_id = NEW.added_by
            )
        );

        IF NOT actor_is_authorized THEN
            RAISE EXCEPTION 'added_by % is not authorized for genealogy %',
                NEW.added_by, NEW.genealogy_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

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

CREATE TRIGGER trg_genealogy_invitations_validate
BEFORE INSERT OR UPDATE ON genealogy_invitations
FOR EACH ROW
EXECUTE FUNCTION validate_genealogy_invitation();

CREATE TRIGGER trg_genealogy_collaborators_validate
BEFORE INSERT OR UPDATE ON genealogy_collaborators
FOR EACH ROW
EXECUTE FUNCTION validate_genealogy_collaborator();

CREATE TRIGGER trg_parent_child_relations_validate
BEFORE INSERT OR UPDATE ON parent_child_relations
FOR EACH ROW
EXECUTE FUNCTION validate_parent_child_relation();

CREATE TRIGGER trg_parent_child_relations_no_cycle
BEFORE INSERT OR UPDATE ON parent_child_relations
FOR EACH ROW
EXECUTE FUNCTION prevent_parent_child_cycle();

CREATE TRIGGER trg_marriages_validate
BEFORE INSERT OR UPDATE ON marriages
FOR EACH ROW
EXECUTE FUNCTION validate_marriage_relation();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_marriages_validate ON marriages;
DROP TRIGGER IF EXISTS trg_parent_child_relations_no_cycle ON parent_child_relations;
DROP TRIGGER IF EXISTS trg_parent_child_relations_validate ON parent_child_relations;
DROP TRIGGER IF EXISTS trg_genealogy_collaborators_validate ON genealogy_collaborators;
DROP TRIGGER IF EXISTS trg_genealogy_invitations_validate ON genealogy_invitations;

DROP FUNCTION IF EXISTS validate_marriage_relation();
DROP FUNCTION IF EXISTS prevent_parent_child_cycle();
DROP FUNCTION IF EXISTS validate_parent_child_relation();
DROP FUNCTION IF EXISTS validate_genealogy_collaborator();
DROP FUNCTION IF EXISTS validate_genealogy_invitation();

ALTER TABLE marriages
    DROP CONSTRAINT IF EXISTS fk_marriages_member_b_pair;

ALTER TABLE marriages
    DROP CONSTRAINT IF EXISTS fk_marriages_member_a_pair;

ALTER TABLE parent_child_relations
    DROP CONSTRAINT IF EXISTS fk_parent_child_relations_child_pair;

ALTER TABLE parent_child_relations
    DROP CONSTRAINT IF EXISTS fk_parent_child_relations_parent_pair;

ALTER TABLE member_events
    DROP CONSTRAINT IF EXISTS fk_member_events_member_pair;

ALTER TABLE members
    DROP CONSTRAINT IF EXISTS uq_members_genealogy_member;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("genealogy", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
