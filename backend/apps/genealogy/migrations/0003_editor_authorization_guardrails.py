from django.db import migrations


FORWARD_SQL = """
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
              AND gc.role = 'editor'
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
                  AND gc.role = 'editor'
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
"""


class Migration(migrations.Migration):
    dependencies = [
        ("genealogy", "0002_postgres_features"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
