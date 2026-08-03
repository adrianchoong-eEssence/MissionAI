"""Enforce the EXOS Foundation runtime ownership boundary.

Google Sheets is configuration and a read-only/reporting projection. Supabase
is the sole authority for live state after publication. In-memory and browser
state are caches only and may never originate a live mutation.
"""

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum


class RuntimeAuthorityError(RuntimeError):
    """Raised when a live operation would bypass its authoritative store."""


_CONTROL_MUTATION = ContextVar("exos_control_mutation", default=False)


@contextmanager
def control_centre_mutation():
    """Grant a narrowly scoped capability to the Control Centre service."""
    token = _CONTROL_MUTATION.set(True)
    try:
        yield
    finally:
        _CONTROL_MUTATION.reset(token)


def require_control_centre(operation):
    """Reject facilitator/live mutations which bypass Control Centre."""
    if not _CONTROL_MUTATION.get():
        raise RuntimeAuthorityError(
            f"{operation} must originate from Control Centre. Direct runtime "
            "mutation from screens, utilities, and legacy consoles is forbidden."
        )


class RuntimeEntity(str, Enum):
    PARTICIPANT = "Participant"
    TEAM = "Team"
    LEADER = "Leader"
    CURRENT_EVENT = "Current Event"
    PROGRAMME_STATE = "Programme State"
    CURRENT_ACTIVITY = "Current Activity"
    CURRENT_EXPERIENCE = "Current Experience"
    SUBMISSION_STATE = "Submission State"
    CREDITS = "Credits"
    LEADERBOARD = "Leaderboard"
    BROADCAST_STATE = "Broadcast State"


@dataclass(frozen=True)
class AuthorityRule:
    owner: str
    authority: str
    sheets_role: str
    memory_role: str = "cache_only"
    mutation_owner: str = "Control Centre"


RUNTIME_AUTHORITY = {
    RuntimeEntity.PARTICIPANT: AuthorityRule("Identity Centre", "runtime_participants", "reporting_projection"),
    RuntimeEntity.TEAM: AuthorityRule("Identity Centre", "runtime_teams", "configuration_before_publish"),
    RuntimeEntity.LEADER: AuthorityRule("Identity Centre", "runtime_participants", "none"),
    RuntimeEntity.CURRENT_EVENT: AuthorityRule("Event Centre", "runtime_events", "configuration_before_publish"),
    RuntimeEntity.PROGRAMME_STATE: AuthorityRule("Control Centre", "runtime_events", "reporting_projection"),
    RuntimeEntity.CURRENT_ACTIVITY: AuthorityRule("Control Centre", "runtime_events", "programme_configuration"),
    RuntimeEntity.CURRENT_EXPERIENCE: AuthorityRule("Control Centre", "runtime_events/runtime_missions", "experience_configuration"),
    RuntimeEntity.SUBMISSION_STATE: AuthorityRule("Intelligence Centre", "runtime_submissions", "reporting_projection"),
    RuntimeEntity.CREDITS: AuthorityRule("Intelligence Centre", "runtime_credit_transactions", "none"),
    RuntimeEntity.LEADERBOARD: AuthorityRule("Intelligence Centre", "derived_from_runtime_submissions_and_credits", "export_projection"),
    RuntimeEntity.BROADCAST_STATE: AuthorityRule("Control Centre", "runtime_events.runtime_control_state", "none"),
}


def require_runtime(runtime, operation, *, admin=False):
    """Fail closed instead of mutating a Sheet or process-local fallback."""
    ready = runtime.can_publish if admin else runtime.is_configured
    if not ready:
        credential = "service credential" if admin else "runtime configuration"
        raise RuntimeAuthorityError(
            f"{operation} requires the authoritative Supabase {credential}; "
            "Google Sheets and memory fallback are forbidden."
        )


def authority_manifest():
    return {
        entity.value: {
            "Owner": rule.owner,
            "Authority": rule.authority,
            "SheetsRole": rule.sheets_role,
            "MemoryRole": rule.memory_role,
            "MutationOwner": rule.mutation_owner,
        }
        for entity, rule in RUNTIME_AUTHORITY.items()
    }
