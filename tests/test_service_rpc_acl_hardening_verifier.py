"""The ACL verifier must stay in lockstep with the ACL migrations.

The three existing ACL test modules read the migration SQL and prove it *says*
the right thing. None of them can prove the privilege is actually in force,
because that needs a real catalogue. ``exos_v2_service_rpc_acl_hardening_verify.sql``
is the query that proves it against installed staging or production.

A verifier is only worth having if it cannot silently fall behind the thing it
verifies. So these tests derive the expected function set from the migrations
themselves: add a function to an ACL migration without adding it to the
verifier and this fails, rather than the verifier quietly passing while a
newly-exposed RPC goes unchecked.

Both directions matter. Revoking too much is as much a live-event failure as
revoking too little -- the five participant-facing Team Formation RPCs carry
registration, reconnect and Captain claim under the participant's own key, and
if hardening ever strips those the whole Monday journey stops at the door.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = (ROOT / "supabase/verification/exos_v2_service_rpc_acl_hardening_verify.sql").read_text(
    encoding="utf-8")
MIGRATIONS = (
    "025a_standard_programme_runtime_acl_hardening.sql",
    "026a_standard_participant_access_acl_hardening.sql",
    "036a_team_formation_v1_acl_hardening.sql",
    "040a_exos_core_v2_service_rpc_acl_hardening.sql",
)
#: The participant journey. These five run under the participant's own anon
#: key on the day and must never be revoked to service_role only.
PARTICIPANT_FACING = {
    "public.exos_v2_team_formation_register_random(text,text,text,text)",
    "public.exos_v2_team_formation_claim_preassigned(text,text,text)",
    "public.exos_v2_recover_team_formation_participant(text,text,text)",
    "public.exos_v2_claim_team_formation_captain(uuid,text)",
    "public.exos_v2_recover_team_formation_captain(text,text,text)",
}


def _normalise(signature: str) -> str:
    """One spelling per signature, so SQL whitespace cannot hide a mismatch."""
    return re.sub(r"\s+", "", signature).lower()


def _granted() -> dict:
    """Every function the ACL migrations grant, mapped to its intended class."""
    granted = {}
    for name in MIGRATIONS:
        flat = " ".join((ROOT / "supabase" / name).read_text(encoding="utf-8").split())
        for match in re.finditer(
                r"grant execute on function (public\.[\w]+\s*\([^)]*\)) to ([^;]+);", flat, re.I):
            signature, roles = _normalise(match.group(1)), match.group(2).lower()
            classification = "participant" if ("anon" in roles or "authenticated" in roles) else "service"
            # A signature granted to participants anywhere is participant-facing.
            if granted.get(signature) != "participant":
                granted[signature] = classification
    return granted


def _verifier_signatures(start: str, end: str) -> set:
    """Signatures inside one VALUES block, bounded at both ends.

    Bounded deliberately: the verifier names ``expected(exact_signature)``
    twice, so an unbounded split would fold the participant block into the
    service block and report coverage the verifier does not actually have.
    """
    assert start in VERIFIER, start
    body = VERIFIER.split(start, 1)[1]
    assert end in body, end
    return {_normalise(item) for item in re.findall(r"'(public\.[\w]+\([^)]*\))'", body.split(end, 1)[0])}


#: The final pass/fail gate names its two classes unambiguously, so coverage
#: is read from there rather than from the two reporting queries above it.
_SERVICE_BLOCK = ("WITH service_only(exact_signature) AS (", "), participant_facing(exact_signature) AS (")
_PARTICIPANT_BLOCK = ("), participant_facing(exact_signature) AS (", "), service_checks AS (")


def test_the_verifier_is_read_only_and_safe_against_production() -> None:
    lowered = re.sub(r"--[^\n]*", "", VERIFIER).lower()
    for forbidden in ("insert ", "update ", "delete ", "create ", "drop ",
                      "alter ", "grant ", "revoke ", "truncate "):
        assert forbidden not in lowered, forbidden


def test_every_service_only_rpc_in_the_migrations_is_verified() -> None:
    expected = {sig for sig, kind in _granted().items() if kind == "service"}
    covered = _verifier_signatures(*_SERVICE_BLOCK)
    missing = expected - covered
    assert not missing, "ACL migrations harden RPCs the verifier never checks: {}".format(
        sorted(missing))


def test_every_participant_facing_rpc_is_verified_as_still_reachable() -> None:
    expected = {sig for sig, kind in _granted().items() if kind == "participant"}
    assert expected == {_normalise(item) for item in PARTICIPANT_FACING}
    covered = _verifier_signatures(*_PARTICIPANT_BLOCK)
    assert expected <= covered, "participant RPCs unverified: {}".format(sorted(expected - covered))


def test_the_two_privilege_classes_never_overlap() -> None:
    """A function cannot be both service-role-only and participant-facing."""
    service = _verifier_signatures(*_SERVICE_BLOCK)
    participant = _verifier_signatures(*_PARTICIPANT_BLOCK)
    assert not (service & participant), sorted(service & participant)


def test_the_monday_journey_rpcs_are_not_revoked_by_any_migration() -> None:
    """Registration, reconnect and Captain claim must survive hardening."""
    for name in MIGRATIONS:
        flat = " ".join((ROOT / "supabase" / name).read_text(encoding="utf-8").split())
        for match in re.finditer(
                r"grant execute on function (public\.[\w]+\s*\([^)]*\)) to ([^;]+);", flat, re.I):
            signature = _normalise(match.group(1))
            if signature in {_normalise(item) for item in PARTICIPANT_FACING}:
                roles = match.group(2).lower()
                assert "anon" in roles, signature
                assert "authenticated" in roles, signature


def test_the_verifier_reports_a_single_pass_fail_gate() -> None:
    """Certification needs one row to read, not twenty to interpret."""
    assert "AS passed;" in VERIFIER
    assert "service_role_only_enforced" in VERIFIER
    assert "participant_journey_preserved" in VERIFIER
