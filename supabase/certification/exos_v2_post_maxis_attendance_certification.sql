-- Disposable P0-A attendance certification.
--
-- Run only after 042 is installed, against the authorised dedicated project.
-- It creates one exact CERT-P0A-* fixture, verifies its canonical lifecycle,
-- then deletes only that fixture inside the same transaction. It never writes
-- to MAXIS-20260907-MISSION-AI or any non-CERT-P0A event.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.events_v2
         WHERE event_id LIKE 'CERT-P0A-%'
    ) OR EXISTS (
        SELECT 1 FROM public.participant_attendance_v2
         WHERE event_id LIKE 'CERT-P0A-%'
    ) OR EXISTS (
        SELECT 1 FROM public.audit_log_v2
         WHERE event_id LIKE 'CERT-P0A-%'
    ) THEN
        RAISE EXCEPTION 'CERT-P0A residue exists; refusing to touch an ambiguous fixture';
    END IF;
END;
$$;

CREATE TEMP TABLE cert_p0a_maxis_sentinel ON COMMIT DROP AS
SELECT 'events_v2'::text AS table_name, count(*)::integer AS row_count,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY') AS digest
  FROM public.events_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
UNION ALL
SELECT 'teams_v2', count(*)::integer,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
  FROM public.teams_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
UNION ALL
SELECT 'participants_v2', count(*)::integer,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
  FROM public.participants_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
UNION ALL
SELECT 'activity_runtime_v2', count(*)::integer,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
  FROM public.activity_runtime_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
UNION ALL
SELECT 'submissions_v2', count(*)::integer,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
  FROM public.submissions_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
UNION ALL
SELECT 'reviews_v2', count(*)::integer,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
  FROM public.reviews_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
UNION ALL
SELECT 'score_transactions_v2', count(*)::integer,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
  FROM public.score_transactions_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
UNION ALL
SELECT 'credit_transactions_v2', count(*)::integer,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
  FROM public.credit_transactions_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
UNION ALL
SELECT 'audit_log_v2', count(*)::integer,
       coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
  FROM public.audit_log_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI';

INSERT INTO public.events_v2(
    event_id, event_name, join_code, event_type, programme_type,
    lifecycle_status, event_payload, published_at
) VALUES (
    'CERT-P0A-ATTENDANCE-20260908', 'CERT P0-A Attendance', 'CERTP0A8',
    'STANDARD', 'STANDARD', 'DRAFT', '{}'::jsonb, now()
);

INSERT INTO public.teams_v2(team_id, event_id, team_name, country, team_flag)
VALUES
    ('CERT-P0A-ATTENDANCE-20260908-JP', 'CERT-P0A-ATTENDANCE-20260908', 'Japan', 'Japan', '🇯🇵'),
    ('CERT-P0A-ATTENDANCE-20260908-KR', 'CERT-P0A-ATTENDANCE-20260908', 'Korea', 'South Korea', '🇰🇷');

CREATE TEMP TABLE cert_p0a_people(
    label text PRIMARY KEY,
    participant_id uuid NOT NULL,
    team_id text NOT NULL
) ON COMMIT DROP;

WITH inserted AS (
    INSERT INTO public.participants_v2(
        event_id, team_id, normalized_name, display_name, country, flag
    )
    SELECT
        'CERT-P0A-ATTENDANCE-20260908', source.team_id, source.normalized_name,
        source.display_name, source.country, source.flag
    FROM (VALUES
        ('P1', 'CERT-P0A-ATTENDANCE-20260908-JP', 'cert p0a one', 'CERT P0A One', 'Japan', '🇯🇵'),
        ('P2', 'CERT-P0A-ATTENDANCE-20260908-JP', 'cert p0a two', 'CERT P0A Two', 'Japan', '🇯🇵'),
        ('P3', 'CERT-P0A-ATTENDANCE-20260908-KR', 'cert p0a three', 'CERT P0A Three', 'South Korea', '🇰🇷'),
        ('P4', 'CERT-P0A-ATTENDANCE-20260908-KR', 'cert p0a four', 'CERT P0A Four', 'South Korea', '🇰🇷')
    ) AS source(label, team_id, normalized_name, display_name, country, flag)
    RETURNING participant_id, team_id, display_name
)
INSERT INTO cert_p0a_people(label, participant_id, team_id)
SELECT
    CASE display_name
        WHEN 'CERT P0A One' THEN 'P1'
        WHEN 'CERT P0A Two' THEN 'P2'
        WHEN 'CERT P0A Three' THEN 'P3'
        ELSE 'P4'
    END,
    participant_id,
    team_id
FROM inserted;

SELECT public.exos_v2_configure_attendance(
    'CERT-P0A-ATTENDANCE-20260908', 'CERT-P0A-FACILITATOR'
);

DO $$
DECLARE
    v_summary jsonb;
BEGIN
    SELECT public.exos_v2_attendance_summary('CERT-P0A-ATTENDANCE-20260908') INTO v_summary;
    IF (v_summary ->> 'Registered')::integer <> 4
       OR (v_summary ->> 'Preassigned')::integer <> 4
       OR (v_summary ->> 'Present')::integer <> 0
       OR (v_summary ->> 'Absent')::integer <> 0 THEN
        RAISE EXCEPTION 'initial PREASSIGNED attendance state is not canonical: %', v_summary;
    END IF;
END;
$$;

-- PREASSIGNED -> PRESENT; PREASSIGNED -> ABSENT -> PRESENT; and
-- PREASSIGNED -> PRESENT -> ABSENT prove both correction directions.
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0A-ATTENDANCE-20260908',
    (SELECT participant_id FROM cert_p0a_people WHERE label = 'P1'),
    'PRESENT', 'CERT-P0A-FACILITATOR', 'arrived'
);
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0A-ATTENDANCE-20260908',
    (SELECT participant_id FROM cert_p0a_people WHERE label = 'P2'),
    'ABSENT', 'CERT-P0A-FACILITATOR', 'initial check-in correction'
);
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0A-ATTENDANCE-20260908',
    (SELECT participant_id FROM cert_p0a_people WHERE label = 'P2'),
    'PRESENT', 'CERT-P0A-FACILITATOR', 'arrived after check-in'
);
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0A-ATTENDANCE-20260908',
    (SELECT participant_id FROM cert_p0a_people WHERE label = 'P3'),
    'PRESENT', 'CERT-P0A-FACILITATOR', 'arrived'
);
SELECT public.exos_v2_set_participant_attendance(
    'CERT-P0A-ATTENDANCE-20260908',
    (SELECT participant_id FROM cert_p0a_people WHERE label = 'P3'),
    'ABSENT', 'CERT-P0A-FACILITATOR', 'left before mission'
);

DO $$
DECLARE
    v_summary jsonb;
    v_japan jsonb;
BEGIN
    SELECT public.exos_v2_attendance_summary('CERT-P0A-ATTENDANCE-20260908') INTO v_summary;
    SELECT value INTO v_japan
      FROM jsonb_array_elements(v_summary -> 'Teams')
     WHERE value ->> 'TeamID' = 'CERT-P0A-ATTENDANCE-20260908-JP';
    IF (v_summary ->> 'Registered')::integer <> 4
       OR (v_summary ->> 'Present')::integer <> 2
       OR (v_summary ->> 'Absent')::integer <> 1
       OR (v_summary ->> 'Preassigned')::integer <> 1
       OR coalesce((v_japan ->> 'PresentTeamSize')::integer, -1) <> 2 THEN
        RAISE EXCEPTION 'canonical attendance totals or present team size are incorrect: %', v_summary;
    END IF;

    IF (SELECT count(*) FROM public.audit_log_v2
          WHERE event_id = 'CERT-P0A-ATTENDANCE-20260908'
            AND action = 'PARTICIPANT_ATTENDANCE_CHANGED') <> 5 THEN
        RAISE EXCEPTION 'attendance correction audit history is incomplete';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM cert_p0a_people c
          JOIN public.participants_v2 p ON p.participant_id = c.participant_id
         WHERE p.event_id <> 'CERT-P0A-ATTENDANCE-20260908'
            OR p.team_id <> c.team_id
    ) THEN
        RAISE EXCEPTION 'attendance mutation altered a participant identity or team assignment';
    END IF;

    IF has_function_privilege('anon',
            'public.exos_v2_set_participant_attendance(text,uuid,text,text,text)', 'EXECUTE')
       OR has_function_privilege('authenticated',
            'public.exos_v2_set_participant_attendance(text,uuid,text,text,text)', 'EXECUTE')
       OR has_function_privilege('public',
            'public.exos_v2_set_participant_attendance(text,uuid,text,text,text)', 'EXECUTE') THEN
        RAISE EXCEPTION 'unauthorised attendance mutation role retains EXECUTE';
    END IF;
END;
$$;

-- Exact-fixture cleanup only. The attendance trigger intentionally blocks
-- direct writes unless the transaction-local canonical capability is present.
SELECT set_config('exos.attendance_mutation', 'v1', true);
DELETE FROM public.participant_attendance_v2
 WHERE event_id = 'CERT-P0A-ATTENDANCE-20260908';
DELETE FROM public.audit_log_v2 WHERE event_id = 'CERT-P0A-ATTENDANCE-20260908';
DELETE FROM public.participants_v2 WHERE event_id = 'CERT-P0A-ATTENDANCE-20260908';
DELETE FROM public.teams_v2 WHERE event_id = 'CERT-P0A-ATTENDANCE-20260908';
DELETE FROM public.events_v2 WHERE event_id = 'CERT-P0A-ATTENDANCE-20260908';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id LIKE 'CERT-P0A-%')
       OR EXISTS (SELECT 1 FROM public.participant_attendance_v2 WHERE event_id LIKE 'CERT-P0A-%')
       OR EXISTS (SELECT 1 FROM public.audit_log_v2 WHERE event_id LIKE 'CERT-P0A-%') THEN
        RAISE EXCEPTION 'CERT-P0A cleanup residue remains';
    END IF;

    IF EXISTS (
        WITH current_sentinel AS (
            SELECT 'events_v2'::text AS table_name, count(*)::integer AS row_count,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY') AS digest
              FROM public.events_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
            UNION ALL SELECT 'teams_v2', count(*)::integer,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
              FROM public.teams_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
            UNION ALL SELECT 'participants_v2', count(*)::integer,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
              FROM public.participants_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
            UNION ALL SELECT 'activity_runtime_v2', count(*)::integer,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
              FROM public.activity_runtime_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
            UNION ALL SELECT 'submissions_v2', count(*)::integer,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
              FROM public.submissions_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
            UNION ALL SELECT 'reviews_v2', count(*)::integer,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
              FROM public.reviews_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
            UNION ALL SELECT 'score_transactions_v2', count(*)::integer,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
              FROM public.score_transactions_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
            UNION ALL SELECT 'credit_transactions_v2', count(*)::integer,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
              FROM public.credit_transactions_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
            UNION ALL SELECT 'audit_log_v2', count(*)::integer,
                   coalesce(md5(string_agg(to_jsonb(t)::text, chr(10) ORDER BY to_jsonb(t)::text)), 'EMPTY')
              FROM public.audit_log_v2 AS t WHERE t.event_id = 'MAXIS-20260907-MISSION-AI'
        )
        SELECT 1
          FROM current_sentinel c
          FULL OUTER JOIN cert_p0a_maxis_sentinel b USING (table_name)
         WHERE c.row_count IS DISTINCT FROM b.row_count
            OR c.digest IS DISTINCT FROM b.digest
    ) THEN
        RAISE EXCEPTION 'MAXIS historical sentinel changed during P0-A certification';
    END IF;
END;
$$;

COMMIT;

SELECT
    'P0-A attendance disposable certification passed' AS certification,
    NOT EXISTS (SELECT 1 FROM public.events_v2 WHERE event_id LIKE 'CERT-P0A-%')
        AS zero_cert_fixture_residue;
