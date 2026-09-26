-- SPEC-44 Phase A1-A3: atomic trip graph writes, optimistic concurrency,
-- and durable idempotency. state_json remains the authoritative read model.

ALTER TABLE trip_states
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1
    CHECK (version >= 1);

CREATE TABLE IF NOT EXISTS trip_command (
    command_id TEXT NOT NULL CHECK (char_length(command_id) BETWEEN 1 AND 128),
    user_id UUID NOT NULL REFERENCES user_tiers(user_id),
    trip_id UUID NOT NULL REFERENCES trip_states(trip_id) ON DELETE CASCADE,
    command_type TEXT NOT NULL CHECK (char_length(command_type) BETWEEN 1 AND 64),
    payload_hash TEXT NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    outcome JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, command_id)
);

CREATE INDEX IF NOT EXISTS idx_trip_command_trip ON trip_command(trip_id);

ALTER TABLE trip_command ENABLE ROW LEVEL SECURITY;
-- No policy needed: service_role (the only grantee) bypasses RLS.
-- All mutations go through the SECURITY DEFINER RPC which runs as owner.
REVOKE ALL ON trip_command FROM PUBLIC, anon, authenticated;
GRANT SELECT ON trip_command TO service_role;

CREATE OR REPLACE FUNCTION commit_trip_command(
    p_trip_id UUID,
    p_user_id UUID,
    p_command_id TEXT,
    p_command_type TEXT,
    p_payload_hash TEXT,
    p_expected_version INTEGER,
    p_state_json JSONB,
    p_nodes JSONB,
    p_edges JSONB,
    p_party JSONB DEFAULT NULL,
    p_response_data JSONB DEFAULT NULL,
    p_consume_reroute BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_prior trip_command%ROWTYPE;
    v_current_version INTEGER;
    v_current_user UUID;
    v_next_version INTEGER;
    v_state JSONB;
    v_party_id UUID;
    v_party JSONB;
    v_outcome JSONB;
    v_response_data JSONB := p_response_data;
    v_observed JSONB := '{}'::JSONB;
    v_reroute_count INTEGER;
    v_reroutes_remaining INTEGER;
    v_role TEXT;
BEGIN
    v_role := COALESCE(
        NULLIF(current_setting('request.jwt.claim.role', true), ''),
        NULLIF(current_setting('request.jwt.claims', true), '')::JSONB->>'role'
    );
    IF v_role IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'commit_trip_command requires service_role'
            USING ERRCODE = '42501';
    END IF;
    IF p_state_json IS NULL
       OR octet_length(p_state_json::TEXT) > 2097152
       OR jsonb_typeof(p_nodes) IS DISTINCT FROM 'array'
       OR jsonb_typeof(p_edges) IS DISTINCT FROM 'array'
       OR jsonb_array_length(p_nodes) > 500
       OR jsonb_array_length(p_edges) > 500
       OR octet_length(COALESCE(p_party, '{}'::JSONB)::TEXT) > 65536
       OR octet_length(COALESCE(p_response_data, '{}'::JSONB)::TEXT) > 262144
       OR char_length(p_command_id) NOT BETWEEN 1 AND 128
       OR char_length(p_command_type) NOT BETWEEN 1 AND 64
       OR p_payload_hash !~ '^[0-9a-f]{64}$'
       OR (p_party IS NOT NULL AND jsonb_array_length(COALESCE(p_party->'members', '[]')) > 50)
    THEN
        RAISE EXCEPTION 'invalid bounded trip command input'
            USING ERRCODE = '22023';
    END IF;

    -- Serialize retries of the same identity/command before checking the ledger.
    PERFORM pg_advisory_xact_lock(
        hashtextextended(p_user_id::TEXT || ':' || p_command_id, 0)
    );

    SELECT * INTO v_prior
      FROM trip_command
     WHERE user_id = p_user_id AND command_id = p_command_id;
    IF FOUND THEN
        IF v_prior.command_type <> p_command_type OR v_prior.payload_hash <> p_payload_hash THEN
            RETURN jsonb_build_object(
                'status', 'command_payload_mismatch',
                'message', 'command_id was already used with another payload'
            );
        END IF;
        RETURN v_prior.outcome || jsonb_build_object('status', 'replayed');
    END IF;

    SELECT version, user_id
      INTO v_current_version, v_current_user
      FROM trip_states
     WHERE trip_id = p_trip_id
     FOR UPDATE;

    IF NOT FOUND THEN
        IF p_expected_version IS NOT NULL THEN
            RETURN jsonb_build_object(
                'status', 'trip_version_conflict',
                'message', 'trip does not exist at the expected version'
            );
        END IF;
        v_next_version := 1;
        v_state := jsonb_set(p_state_json, '{version}', to_jsonb(v_next_version), true);
        INSERT INTO trip_states (
            trip_id, user_id, state_json, version, is_active, updated_at
        ) VALUES (
            p_trip_id, p_user_id, v_state, v_next_version, true, NOW()
        );
    ELSE
        IF v_current_user <> p_user_id
           OR v_current_version <> COALESCE(
               p_expected_version,
               NULLIF(p_state_json->>'version', '')::INTEGER,
               1
           )
        THEN
            RETURN jsonb_build_object(
                'status', 'trip_version_conflict',
                'message', 'stored trip version does not match expected_version'
            );
        END IF;
        v_next_version := v_current_version + 1;
        IF p_consume_reroute THEN
            v_reroute_count := consume_reroute(p_user_id);
            IF v_reroute_count IS NULL THEN
                RETURN jsonb_build_object(
                    'status', 'daily_reroute_limit_reached',
                    'message', 'daily reroute limit reached'
                );
            END IF;
            SELECT max_daily_reroutes - v_reroute_count
              INTO v_reroutes_remaining
              FROM user_tiers
             WHERE user_id = p_user_id;
            v_response_data := jsonb_set(
                COALESCE(v_response_data, '{}'::JSONB),
                '{reroutes_remaining}',
                to_jsonb(v_reroutes_remaining),
                true
            );
        END IF;
        v_state := jsonb_set(p_state_json, '{version}', to_jsonb(v_next_version), true);
        UPDATE trip_states
           SET state_json = v_state,
               version = v_next_version,
               updated_at = NOW()
         WHERE trip_id = p_trip_id;
    END IF;

    SELECT COALESCE(
        jsonb_object_agg(from_node_id || '|' || to_node_id, observed_duration_minutes),
        '{}'::JSONB
    )
      INTO v_observed
      FROM trip_edge
     WHERE trip_id = p_trip_id
       AND observed_duration_minutes IS NOT NULL;

    DELETE FROM trip_edge WHERE trip_id = p_trip_id;
    DELETE FROM trip_node WHERE trip_id = p_trip_id;

    INSERT INTO trip_node (
        node_id, trip_id, day_index, seq, node_type, venue_ref, title,
        scheduled_start, scheduled_end, duration_minutes, is_locked, status,
        geo_region, micro_location, lat, lng, vibe_tags, opening_hours,
        node_kind, booking_type, confirmation_code, booking_notes, import_source,
        names_local, landmarks_local, nearest_landmark
    )
    SELECT
        n.node_id, p_trip_id, n.day_index, n.seq, n.node_type, n.venue_ref,
        n.title, n.scheduled_start, n.scheduled_end, n.duration_minutes,
        n.is_locked, n.status, n.geo_region, n.micro_location, n.lat, n.lng,
        CASE WHEN jsonb_typeof(n.vibe_tags) = 'array'
             THEN COALESCE(
                 (SELECT array_agg(t.val) FROM jsonb_array_elements_text(n.vibe_tags) AS t(val)),
                 ARRAY[]::TEXT[]
             )
             ELSE ARRAY[]::TEXT[]
        END, n.opening_hours,
        COALESCE(n.node_kind, 'activity'), n.booking_type, n.confirmation_code, n.booking_notes,
        n.import_source, n.names_local, n.landmarks_local, n.nearest_landmark
    FROM jsonb_to_recordset(p_nodes) AS n(
        node_id TEXT, trip_id UUID, day_index INTEGER, seq INTEGER, node_type TEXT,
        venue_ref UUID, title TEXT, scheduled_start TIMESTAMPTZ,
        scheduled_end TIMESTAMPTZ, duration_minutes INTEGER, is_locked BOOLEAN,
        status TEXT, geo_region TEXT, micro_location TEXT, lat DOUBLE PRECISION,
        lng DOUBLE PRECISION, vibe_tags JSONB, opening_hours TEXT, node_kind TEXT,
        booking_type TEXT, confirmation_code TEXT, booking_notes TEXT,
        import_source TEXT, names_local JSONB, landmarks_local JSONB,
        nearest_landmark TEXT
    );

    INSERT INTO trip_edge (
        edge_id, trip_id, from_node_id, to_node_id, transport_mode,
        expected_duration_minutes, observed_duration_minutes,
        expected_cost_band, notes
    )
    SELECT
        e.edge_id, p_trip_id, e.from_node_id, e.to_node_id, e.transport_mode,
        e.expected_duration_minutes,
        COALESCE(
            e.observed_duration_minutes,
            (v_observed->>(e.from_node_id || '|' || e.to_node_id))::INTEGER
        ),
        e.expected_cost_band, e.notes
    FROM jsonb_to_recordset(p_edges) AS e(
        edge_id TEXT, trip_id UUID, from_node_id TEXT, to_node_id TEXT,
        transport_mode TEXT, expected_duration_minutes INTEGER,
        observed_duration_minutes INTEGER, expected_cost_band TEXT, notes TEXT
    );

    IF p_party IS NOT NULL THEN
        DELETE FROM trip_party WHERE trip_id = p_trip_id::TEXT;
        v_party_id := gen_random_uuid();
        INSERT INTO trip_party (party_id, trip_id, party_type, size, notes)
        VALUES (
            v_party_id, p_trip_id::TEXT, p_party->>'party_type',
            COALESCE((p_party->>'size')::INTEGER, 1), p_party->>'notes'
        );
        INSERT INTO party_member (
            party_id, role, age_band, needs, dietary_constraints
        )
        SELECT
            v_party_id, m.role, m.age_band, COALESCE(m.needs, ARRAY[]::TEXT[]),
            COALESCE(m.dietary_constraints, ARRAY[]::TEXT[])
        FROM jsonb_to_recordset(COALESCE(p_party->'members', '[]')) AS m(
            role TEXT, age_band TEXT, needs TEXT[], dietary_constraints TEXT[]
        );
        v_party := p_party
            || jsonb_build_object(
                'party_id', v_party_id,
                'trip_id', p_trip_id::TEXT
            );
    END IF;

    v_outcome := jsonb_build_object(
        'trip_state', v_state,
        'party', v_party,
        'response_data', v_response_data
    );
    INSERT INTO trip_command (
        command_id, user_id, trip_id, command_type, payload_hash, outcome
    ) VALUES (
        p_command_id, p_user_id, p_trip_id, p_command_type, p_payload_hash, v_outcome
    );

    RETURN v_outcome || jsonb_build_object('status', 'committed');
END;
$$;

REVOKE ALL ON FUNCTION commit_trip_command(
    UUID, UUID, TEXT, TEXT, TEXT, INTEGER, JSONB, JSONB, JSONB, JSONB, JSONB, BOOLEAN
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION commit_trip_command(
    UUID, UUID, TEXT, TEXT, TEXT, INTEGER, JSONB, JSONB, JSONB, JSONB, JSONB, BOOLEAN
) TO service_role;

-- Manual rollback:
-- DROP FUNCTION IF EXISTS commit_trip_command(UUID, UUID, TEXT, TEXT, TEXT, INTEGER, JSONB, JSONB, JSONB, JSONB, JSONB, BOOLEAN);
-- DROP TABLE IF EXISTS trip_command;
-- ALTER TABLE trip_states DROP COLUMN IF EXISTS version;
