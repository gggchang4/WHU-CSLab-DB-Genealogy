-- Note:
-- This file captures the core business schema for the genealogy system.
-- Django auth framework tables such as auth_group/auth_permission and their
-- relation tables are expected to be created by Django's built-in migrations.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    email VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE TABLE genealogies (
    genealogy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    surname VARCHAR(64) NOT NULL,
    compiled_at INTEGER,
    description TEXT,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_genealogies_created_by
        FOREIGN KEY (created_by)
        REFERENCES users (user_id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_genealogies_compiled_at
        CHECK (compiled_at IS NULL OR compiled_at BETWEEN 1 AND 3000)
);

CREATE TABLE genealogy_invitations (
    invitation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    genealogy_id BIGINT NOT NULL,
    inviter_user_id BIGINT NOT NULL,
    invitee_user_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    message TEXT,
    invited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    CONSTRAINT fk_genealogy_invitations_genealogy
        FOREIGN KEY (genealogy_id)
        REFERENCES genealogies (genealogy_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_genealogy_invitations_inviter
        FOREIGN KEY (inviter_user_id)
        REFERENCES users (user_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_genealogy_invitations_invitee
        FOREIGN KEY (invitee_user_id)
        REFERENCES users (user_id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_genealogy_invitations_status
        CHECK (status IN ('pending', 'accepted', 'declined', 'revoked', 'expired')),
    CONSTRAINT chk_genealogy_invitations_time
        CHECK (responded_at IS NULL OR responded_at >= invited_at),
    CONSTRAINT chk_genealogy_invitations_self
        CHECK (inviter_user_id <> invitee_user_id)
);

CREATE TABLE genealogy_collaborators (
    collaborator_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    genealogy_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    source_invitation_id BIGINT NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'editor',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    added_by BIGINT,
    CONSTRAINT fk_genealogy_collaborators_genealogy
        FOREIGN KEY (genealogy_id)
        REFERENCES genealogies (genealogy_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_genealogy_collaborators_user
        FOREIGN KEY (user_id)
        REFERENCES users (user_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_genealogy_collaborators_source_invitation
        FOREIGN KEY (source_invitation_id)
        REFERENCES genealogy_invitations (invitation_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_genealogy_collaborators_added_by
        FOREIGN KEY (added_by)
        REFERENCES users (user_id)
        ON DELETE SET NULL,
    CONSTRAINT uq_genealogy_collaborators_pair
        UNIQUE (genealogy_id, user_id),
    CONSTRAINT uq_genealogy_collaborators_source_invitation
        UNIQUE (source_invitation_id),
    CONSTRAINT chk_genealogy_collaborators_role
        CHECK (role IN ('editor', 'viewer'))
);

CREATE TABLE members (
    member_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    genealogy_id BIGINT NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    surname VARCHAR(64),
    given_name VARCHAR(128),
    gender VARCHAR(16) NOT NULL DEFAULT 'unknown',
    birth_year INTEGER,
    death_year INTEGER,
    is_living BOOLEAN NOT NULL DEFAULT TRUE,
    generation_label VARCHAR(64),
    seniority_text VARCHAR(64),
    branch_name VARCHAR(128),
    biography TEXT,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_members_genealogy
        FOREIGN KEY (genealogy_id)
        REFERENCES genealogies (genealogy_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_members_created_by
        FOREIGN KEY (created_by)
        REFERENCES users (user_id)
        ON DELETE SET NULL,
    CONSTRAINT uq_members_genealogy_member
        UNIQUE (genealogy_id, member_id),
    CONSTRAINT chk_members_gender
        CHECK (gender IN ('male', 'female', 'unknown')),
    CONSTRAINT chk_members_birth_death
        CHECK (death_year IS NULL OR birth_year IS NULL OR birth_year <= death_year),
    CONSTRAINT chk_members_living
        CHECK ((is_living AND death_year IS NULL) OR (NOT is_living) OR death_year IS NULL),
    CONSTRAINT chk_members_birth_year
        CHECK (birth_year IS NULL OR birth_year BETWEEN 1 AND 3000),
    CONSTRAINT chk_members_death_year
        CHECK (death_year IS NULL OR death_year BETWEEN 1 AND 3000)
);

CREATE TABLE member_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    genealogy_id BIGINT NOT NULL,
    member_id BIGINT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    event_year INTEGER,
    place_text VARCHAR(255),
    description TEXT,
    recorded_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_member_events_genealogy
        FOREIGN KEY (genealogy_id)
        REFERENCES genealogies (genealogy_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_member_events_member
        FOREIGN KEY (genealogy_id, member_id)
        REFERENCES members (genealogy_id, member_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_member_events_recorded_by
        FOREIGN KEY (recorded_by)
        REFERENCES users (user_id)
        ON DELETE SET NULL,
    CONSTRAINT chk_member_events_type
        CHECK (event_type IN (
            'migration',
            'residence',
            'occupation',
            'achievement',
            'burial',
            'marriage_note',
            'other'
        )),
    CONSTRAINT chk_member_events_year
        CHECK (event_year IS NULL OR event_year BETWEEN 1 AND 3000)
);

CREATE TABLE parent_child_relations (
    relation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    genealogy_id BIGINT NOT NULL,
    parent_member_id BIGINT NOT NULL,
    child_member_id BIGINT NOT NULL,
    parent_role VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT,
    CONSTRAINT fk_parent_child_relations_genealogy
        FOREIGN KEY (genealogy_id)
        REFERENCES genealogies (genealogy_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_parent_child_relations_parent
        FOREIGN KEY (genealogy_id, parent_member_id)
        REFERENCES members (genealogy_id, member_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_parent_child_relations_child
        FOREIGN KEY (genealogy_id, child_member_id)
        REFERENCES members (genealogy_id, member_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_parent_child_relations_created_by
        FOREIGN KEY (created_by)
        REFERENCES users (user_id)
        ON DELETE SET NULL,
    CONSTRAINT uq_parent_child_relations_pair
        UNIQUE (genealogy_id, parent_member_id, child_member_id, parent_role),
    CONSTRAINT chk_parent_child_relations_parent_role
        CHECK (parent_role IN ('father', 'mother')),
    CONSTRAINT chk_parent_child_relations_self
        CHECK (parent_member_id <> child_member_id)
);

CREATE TABLE marriages (
    marriage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    genealogy_id BIGINT NOT NULL,
    member_a_id BIGINT NOT NULL,
    member_b_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'married',
    start_year INTEGER,
    end_year INTEGER,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by BIGINT,
    CONSTRAINT fk_marriages_genealogy
        FOREIGN KEY (genealogy_id)
        REFERENCES genealogies (genealogy_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_marriages_member_a
        FOREIGN KEY (genealogy_id, member_a_id)
        REFERENCES members (genealogy_id, member_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_marriages_member_b
        FOREIGN KEY (genealogy_id, member_b_id)
        REFERENCES members (genealogy_id, member_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_marriages_created_by
        FOREIGN KEY (created_by)
        REFERENCES users (user_id)
        ON DELETE SET NULL,
    CONSTRAINT chk_marriages_status
        CHECK (status IN ('married', 'divorced', 'widowed', 'unknown')),
    CONSTRAINT chk_marriages_self
        CHECK (member_a_id <> member_b_id),
    CONSTRAINT chk_marriages_member_order
        CHECK (member_a_id < member_b_id),
    CONSTRAINT chk_marriages_years
        CHECK (end_year IS NULL OR start_year IS NULL OR start_year <= end_year)
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

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

CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_genealogies_set_updated_at
BEFORE UPDATE ON genealogies
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_members_set_updated_at
BEFORE UPDATE ON members
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

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

CREATE UNIQUE INDEX uq_genealogy_invitations_pending
    ON genealogy_invitations (genealogy_id, invitee_user_id)
    WHERE status = 'pending';

CREATE UNIQUE INDEX uq_parent_child_single_father
    ON parent_child_relations (genealogy_id, child_member_id)
    WHERE parent_role = 'father';

CREATE UNIQUE INDEX uq_parent_child_single_mother
    ON parent_child_relations (genealogy_id, child_member_id)
    WHERE parent_role = 'mother';

CREATE UNIQUE INDEX uq_marriages_active_pair
    ON marriages (genealogy_id, member_a_id, member_b_id)
    WHERE status = 'married';

CREATE INDEX idx_members_genealogy_full_name
    ON members (genealogy_id, full_name);

CREATE INDEX idx_members_genealogy_gender
    ON members (genealogy_id, gender);

CREATE INDEX idx_members_full_name_trgm
    ON members
    USING GIN (full_name gin_trgm_ops);

CREATE INDEX idx_parent_child_relations_parent
    ON parent_child_relations (genealogy_id, parent_member_id);

CREATE INDEX idx_parent_child_relations_child
    ON parent_child_relations (genealogy_id, child_member_id);

CREATE INDEX idx_marriages_member_a
    ON marriages (genealogy_id, member_a_id);

CREATE INDEX idx_marriages_member_b
    ON marriages (genealogy_id, member_b_id);

CREATE INDEX idx_member_events_member_type_year
    ON member_events (genealogy_id, member_id, event_type, event_year);

CREATE INDEX idx_genealogy_collaborators_user_id
    ON genealogy_collaborators (user_id);

CREATE INDEX idx_genealogy_invitations_invitee_status
    ON genealogy_invitations (invitee_user_id, status);
