-- READ ONLY. Safe before Sprint 010 migration. Replace EVT-0004 if required.
-- This script performs SELECT statements only and changes no production rows.

with participant_audit as (
    select
        p.participant_id,
        p.event_id,
        p.display_name,
        lower(trim(regexp_replace(
            regexp_replace(p.display_name, '[[:punct:]]+', ' ', 'g'),
            '\s+', ' ', 'g'
        ))) as canonical_name,
        p.normalized_name,
        p.team_name,
        p.status,
        p.points,
        p.joined_at,
        p.session_token,
        p.idempotency_key
    from public.runtime_participants p
    where p.event_id = 'EVT-0004'
), duplicate_groups as (
    select canonical_name, count(*) as record_count,
           jsonb_agg(jsonb_build_object(
               'ParticipantID', participant_id,
               'DisplayName', display_name,
               'Team', team_name,
               'Status', status,
               'Points', points,
               'JoinedAt', joined_at,
               'IdempotencyKey', idempotency_key
           ) order by joined_at, participant_id) as records
    from participant_audit
    group by canonical_name
    having count(*) > 1
), team_mutations as (
    select p.participant_id, p.display_name, p.team_name,
           array_agg(t.team_id order by t.position) as matching_team_ids
    from participant_audit p
    left join public.runtime_teams t
      on t.event_id=p.event_id and t.team_name=p.team_name
    group by p.participant_id,p.display_name,p.team_name
    having count(t.team_id) <> 1
), leader_inconsistencies as (
    select p.team_name,
           count(*) filter (where p.status like '%|LEADER%') as leader_count,
           jsonb_agg(jsonb_build_object(
               'ParticipantID',p.participant_id,
               'Name',p.display_name,
               'Status',p.status
           ) order by p.joined_at) as participants
    from participant_audit p
    group by p.team_name
    having count(*) filter (where p.status like '%|LEADER%') <> 1
), orphaned_submissions as (
    select s.submission_id,s.mission_id,s.participant_id,
           s.participant_name,s.team_name,s.status,s.submitted_at
    from public.runtime_submissions s
    left join public.runtime_participants p on p.participant_id=s.participant_id
    where s.event_id='EVT-0004'
      and (s.participant_id is null or p.participant_id is null)
), duplicate_credit_risk as (
    select s.mission_id,s.participant_id,count(*) record_count,
           jsonb_agg(s.submission_id order by s.created_at) submission_ids
    from public.runtime_submissions s
    where s.event_id='EVT-0004' and s.participant_id is not null
    group by s.mission_id,s.participant_id
    having count(*) > 1
)
select jsonb_pretty(jsonb_build_object(
    'EventID','EVT-0004',
    'DuplicateIdentityCandidates',coalesce((select jsonb_agg(to_jsonb(d)) from duplicate_groups d),'[]'),
    'AmbiguousSameNameCandidates',coalesce((select jsonb_agg(to_jsonb(d)) from duplicate_groups d),'[]'),
    'TeamMutationCandidates',coalesce((select jsonb_agg(to_jsonb(t)) from team_mutations t),'[]'),
    'LeaderInconsistencies',coalesce((select jsonb_agg(to_jsonb(l)) from leader_inconsistencies l),'[]'),
    'OrphanedSubmissions',coalesce((select jsonb_agg(to_jsonb(o)) from orphaned_submissions o),'[]'),
    'DuplicateCreditRisks',coalesce((select jsonb_agg(to_jsonb(c)) from duplicate_credit_risk c),'[]'),
    'ProductionRecordsChanged',false
));
