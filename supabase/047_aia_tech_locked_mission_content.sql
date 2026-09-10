-- Locked AIA Tech UAT MissionBoard content only.
--
-- This migration is intentionally restricted to the disposable AIA UAT event.
-- It refuses to overwrite a launched, selected, submitted, or scored board.
BEGIN;

DO $guard$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.events_v2
         WHERE event_id = 'AIA-TECH-20261023-UAT'
    ) THEN
        RAISE EXCEPTION 'AIA UAT event is not installed';
    END IF;
    IF coalesce((SELECT event_payload #>> '{RaceConfiguration,RuntimePhase}'
                   FROM public.events_v2
                  WHERE event_id = 'AIA-TECH-20261023-UAT'), 'READY') <> 'READY' THEN
        RAISE EXCEPTION 'AIA locked MissionBoard update is allowed only while RuntimePhase is READY';
    END IF;
    IF EXISTS (SELECT 1 FROM public.activity_runtime_v2 WHERE event_id = 'AIA-TECH-20261023-UAT')
       OR EXISTS (SELECT 1 FROM public.submissions_v2 WHERE event_id = 'AIA-TECH-20261023-UAT')
       OR EXISTS (SELECT 1 FROM public.score_transactions_v2 WHERE event_id = 'AIA-TECH-20261023-UAT') THEN
        RAISE EXCEPTION 'AIA locked MissionBoard update is frozen after runtime, submission, or score state exists';
    END IF;
END
$guard$;

-- ``(module_id, activity_order)`` is unique. Move the untouched UAT-only
-- rows out of the target order range before assigning the locked order.
UPDATE public.activities_v2 AS activity
   SET activity_order = activity.activity_order + 100
  FROM public.programmes_v2 AS programme
 WHERE programme.programme_id = activity.programme_id
   AND programme.event_id = 'AIA-TECH-20261023-UAT'
   AND activity.is_active
   AND activity.activity_payload ? 'race_station';

-- These identifiers have no runtime/submission references because of the
-- guard above. Renaming removes superseded mission names from the canonical
-- AIA board rather than retaining hidden duplicate candidates.
UPDATE public.activities_v2
   SET activity_id = CASE activity_id
        WHEN 'AIA-TECH-20261023-UAT-RIDE-ACORN' THEN 'AIA-TECH-20261023-UAT-RIDE-RIVET-TOWN-ROLLER'
        WHEN 'AIA-TECH-20261023-UAT-AI-LAB' THEN 'AIA-TECH-20261023-UAT-HUMAN-MACHINE'
        WHEN 'AIA-TECH-20261023-UAT-INSIGHT' THEN 'AIA-TECH-20261023-UAT-TECH-WILD'
        WHEN 'AIA-TECH-20261023-UAT-SECRET-MOMENTUM' THEN 'AIA-TECH-20261023-UAT-SECRET-01'
        WHEN 'AIA-TECH-20261023-UAT-SECRET-SIGNAL' THEN 'AIA-TECH-20261023-UAT-SECRET-02'
        ELSE activity_id
   END
 WHERE activity_id IN (
    'AIA-TECH-20261023-UAT-RIDE-ACORN',
    'AIA-TECH-20261023-UAT-AI-LAB',
    'AIA-TECH-20261023-UAT-INSIGHT',
    'AIA-TECH-20261023-UAT-SECRET-MOMENTUM',
    'AIA-TECH-20261023-UAT-SECRET-SIGNAL'
 );

WITH locked_missions(
    activity_id, display_name, display_order, mission_class, category,
    evidence_type, participation_prorated, scoring_mode, rubric, maximum,
    zone, location_description, participant_instruction, secret_state
) AS (
    VALUES
    ('AIA-TECH-20261023-UAT-RIDE-RIVET-TOWN-ROLLER', 'Rivet Town Roller', 1, 'RIDE', 'RIDES / PHYSICAL', 'PHOTO', true, 'PARTICIPATION_PRORATED', false, 150, 'Robots Rivet Town', 'Robots Rivet Town', 'CONTROL THE CHAOS. Take on the rider-controlled challenge with as many PRESENT team members as possible. Your score is based on participation.', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-RIDE-APES', 'Invasion of the Planet of the Apes', 2, 'RIDE', 'RIDES / PHYSICAL', 'PHOTO_OR_VIDEO', true, 'PARTICIPATION_PRORATED', false, 150, '', '', '', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-RIDE-INDEPENDENCE', 'Independence Day: Defiance', 3, 'RIDE', 'RIDES / PHYSICAL', 'PHOTO_OR_VIDEO', true, 'PARTICIPATION_PRORATED', false, 150, '', '', '', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-RIDE-SAMBA', 'Samba Gliders', 4, 'RIDE', 'RIDES / PHYSICAL', 'PHOTO', true, 'PARTICIPATION_PRORATED', false, 120, '', '', '', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-BOOT-CAMP', 'Boot Camp Training', 5, 'STANDARD', 'RIDES / PHYSICAL', 'PHOTO_OR_VIDEO', true, 'PARTICIPATION_PRORATED', false, 250, 'Andromeda Base', 'Andromeda Base', 'HIGH REWARD · HIGH TIME COMMITMENT. This mission can take considerably longer than other challenges. Choose wisely. You do NOT need to complete every mission. Score is participation prorated against the canonical PRESENT team size. At 9 PRESENT: 9/9 = 250; 8/9 = 222; 7/9 = 194; 6/9 = 167. Canonical rounding is HALF_UP.', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-HUMAN-MACHINE', 'Human + Machine', 6, 'STANDARD', 'TASKS', 'PHOTO', false, 'FACILITATOR_RUBRIC', true, 120, '', '', '', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-MANNEQUIN', 'Mannequin Challenge', 7, 'BONUS', 'TASKS', 'PHOTO_OR_VIDEO', false, 'FACILITATOR_RUBRIC', true, 140, '', '', '', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-TECH-WILD', 'Tech in the Wild', 8, 'STANDARD', 'TASKS', 'PHOTO', false, 'TEAM_FULL', false, 120, '', '', '', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-SECRET-01', 'Secret Mission 01', 9, 'SECRET', 'SECRETS', 'PHOTO_OR_VIDEO', false, 'TEAM_FULL', false, 100, '', '', '', 'RELEASED'),
    ('AIA-TECH-20261023-UAT-SECRET-02', 'Secret Mission 02', 10, 'SECRET', 'SECRETS', 'VIDEO', false, 'FACILITATOR_RUBRIC', true, 150, '', '', '', 'RELEASED')
)
UPDATE public.activities_v2 AS activity
   SET activity_name = mission.display_name,
       activity_order = mission.display_order,
       activity_payload = jsonb_build_object('race_station', jsonb_build_object(
           'Enabled', true,
           'DisplayOrder', mission.display_order,
           'DisplayName', mission.display_name,
           'MissionClass', mission.mission_class,
           'Category', mission.category,
           'Zone', mission.zone,
           'LocationDescription', mission.location_description,
           'ParticipantInstruction', mission.participant_instruction,
           'EvidenceType', mission.evidence_type,
           'AIHelpEnabled', true,
           'Evidence', jsonb_build_object(
               'Text', jsonb_build_object('Required', false, 'Label', 'Team response'),
               'Photo', jsonb_build_object('Required', mission.evidence_type IN ('PHOTO', 'PHOTO_OR_VIDEO'), 'Label', 'Private team photo'),
               'Video', jsonb_build_object('Required', mission.evidence_type IN ('VIDEO', 'PHOTO_OR_VIDEO'), 'Label', 'Private short video', 'MaximumBytes', 52428800),
               'NumericResult', jsonb_build_object('Required', false, 'Label', 'Result')
           ),
           'ParticipationProrated', mission.participation_prorated,
           'ScoringMode', mission.scoring_mode,
           'Rubric', mission.rubric,
           'Scoring', jsonb_build_object(
               'Mode', mission.scoring_mode,
               'Maximum', mission.maximum,
               'Rounding', 'HALF_UP',
               'Rubric', CASE WHEN mission.rubric THEN jsonb_build_object('Criteria', jsonb_build_array(
                   jsonb_build_object('ID', 'creativity', 'Label', 'Creativity', 'Weight', 1),
                   jsonb_build_object('ID', 'collaboration', 'Label', 'Collaboration', 'Weight', 1),
                   jsonb_build_object('ID', 'clarity', 'Label', 'Clarity', 'Weight', 1)
               )) ELSE '{}'::jsonb END
           ),
           'RideParticipation', CASE WHEN mission.mission_class = 'RIDE' THEN jsonb_build_object(
               'RequiredPercent', 80, 'Rounding', 'CEILING',
               'EvidencePathways', jsonb_build_array('GROUND_CONTROL', 'FULL_TEAM', 'FACILITATOR_VERIFIED'),
               'FullParticipationBonus', 0
           ) ELSE '{}'::jsonb END,
           'ReviewRequired', true,
           'ContentStatus', 'CONFIGURABLE_UAT_CANDIDATE',
           'SafetyNote', 'Facilitator must confirm safe, permitted mission placement before enabling.'
       ))
  FROM locked_missions AS mission,
       public.programmes_v2 AS programme
 WHERE activity.activity_id = mission.activity_id
   AND programme.programme_id = activity.programme_id
   AND programme.event_id = 'AIA-TECH-20261023-UAT';

-- Use the existing guarded configuration RPC so the operation map remains
-- canonical and no team-count/capacity decision is introduced.
SELECT public.exos_v2_theme_park_race_save_configuration(
    'AIA-TECH-20261023-UAT',
    (
        SELECT jsonb_set(
            event_payload->'RaceConfiguration',
            '{MissionBoard,MissionOperations}',
            (
                SELECT jsonb_object_agg(
                    activity.activity_id,
                    jsonb_build_object('OperationalStatus', 'AVAILABLE', 'SecretState', 'RELEASED')
                )
                  FROM public.activities_v2 AS activity
                  JOIN public.programmes_v2 AS programme ON programme.programme_id = activity.programme_id
                 WHERE programme.event_id = 'AIA-TECH-20261023-UAT'
                   AND activity.is_active
                   AND activity.activity_payload ? 'race_station'
            ),
            true
        )
          FROM public.events_v2
         WHERE event_id = 'AIA-TECH-20261023-UAT'
    ),
    'aia_locked_content_update'
);

DO $assert$
BEGIN
    IF (SELECT count(*) FROM public.activities_v2 AS activity
          JOIN public.programmes_v2 AS programme ON programme.programme_id = activity.programme_id
         WHERE programme.event_id = 'AIA-TECH-20261023-UAT'
           AND activity.is_active AND activity.activity_payload ? 'race_station') <> 10 THEN
        RAISE EXCEPTION 'AIA locked board must contain exactly ten missions';
    END IF;
    IF EXISTS (SELECT 1 FROM public.activities_v2 WHERE activity_id = 'AIA-TECH-20261023-UAT-RIDE-ACORN')
       OR NOT EXISTS (SELECT 1 FROM public.activities_v2 WHERE activity_id = 'AIA-TECH-20261023-UAT-RIDE-RIVET-TOWN-ROLLER'
                       AND activity_payload #>> '{race_station,Scoring,Maximum}' = '150')
       OR NOT EXISTS (SELECT 1 FROM public.activities_v2 WHERE activity_id = 'AIA-TECH-20261023-UAT-BOOT-CAMP'
                       AND activity_payload #>> '{race_station,Scoring,Maximum}' = '250') THEN
        RAISE EXCEPTION 'AIA locked ride or Boot Camp content assertion failed';
    END IF;
    IF (SELECT coalesce(sum((activity_payload #>> '{race_station,Scoring,Maximum}')::integer), 0)
          FROM public.activities_v2 AS activity
          JOIN public.programmes_v2 AS programme ON programme.programme_id = activity.programme_id
         WHERE programme.event_id = 'AIA-TECH-20261023-UAT'
           AND activity.is_active AND activity.activity_payload ? 'race_station') <> 1450 THEN
        RAISE EXCEPTION 'AIA locked board maximum must be 1450';
    END IF;
END
$assert$;

INSERT INTO public.audit_log_v2(event_id, actor, action, entity_type, entity_id, after_state)
VALUES (
    'AIA-TECH-20261023-UAT', 'aia_locked_content_update',
    'AIA_UAT_LOCKED_CONTENT_APPLIED', 'events_v2', 'AIA-TECH-20261023-UAT',
    jsonb_build_object('MissionCount', 10, 'MaximumTheoreticalScore', 1450, 'RuntimePhase', 'READY')
);

COMMIT;
