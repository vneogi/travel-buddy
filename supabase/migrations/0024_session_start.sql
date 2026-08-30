-- SPEC-30: session_start signal type for retention instrumentation.
-- Models on 0021_booking_anchors.sql.

INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('session_start', 'behavioral', 'json', NULL, 'none',
     'App came to the foreground; carries trip-relative timing for retention')
ON CONFLICT (key) DO NOTHING;
