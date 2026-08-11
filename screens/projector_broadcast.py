import html
import json
from urllib.parse import quote

import streamlit as st

from branding import PLATFORM_EXPANSION, PLATFORM_TAGLINE
from data.mission_media import (
    get_mission_media_url,
    upload_library_asset,
)
from engines.stage_timer import remaining_seconds
from engines.canonical_performance import load_performance_snapshot


BROADCAST_MODES = [
    "Welcome",
    "Current Activity",
    "Multiple Activities",
    "Leaderboard",
    "Scores",
    "Timer",
    "Instructions",
    "Results",
    "Championship",
    "Custom Message",
    "Blank",
]

LEGACY_BROADCAST_MODES = {
    "Story",
    "Experience",
    "Countdown",
    "Credits",
    "Announcement",
    "Sync AI",
    "The King",
    "Custom Image",
    "Custom Video",
}

_LEGACY_MODE_MAP = {
    "Story": "Current Activity",
    "Experience": "Current Activity",
    "Countdown": "Timer",
    "Credits": "Scores",
    "Announcement": "Custom Message",
    "Sync AI": "Instructions",
    "The King": "Results",
    "Custom Image": "Custom Message",
    "Custom Video": "Custom Message",
}


def _normalise_mode(mode):
    if not mode:
        return "Welcome"
    return _LEGACY_MODE_MAP.get(str(mode).strip(), str(mode).strip())

DEFAULT_BROADCAST = {
    "Mode": "Welcome",
    "PresentationMode": True,
    "Title": "",
    "Message": "",
    "BackgroundReference": "",
    "LogoReference": "",
    "CharacterReference": "",
    "CustomImageReference": "",
    "Theme": "Default",
}


def projector_broadcast_state(event):
    metadata = dict((event or {}).get("_EventPayload") or {})
    if not metadata:
        try:
            parsed = json.loads(str((event or {}).get("Notes", "") or "{}"))
            metadata = parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            metadata = {}
    stored = metadata.get("ProjectorBroadcast", {}) or {}
    state = dict(DEFAULT_BROADCAST)
    state.update({
        key: value
        for key, value in dict(stored).items()
        if key in state
    })
    state["Mode"] = _normalise_mode(state.get("Mode"))
    if state["Mode"] not in BROADCAST_MODES:
        state["Mode"] = "Welcome"
    state["PresentationMode"] = bool(state.get("PresentationMode", True))
    branding = dict(metadata.get("ProjectorBranding", {}) or {})
    if not stored:
        state["Mode"] = _normalise_mode(branding.get("DefaultBroadcast", state["Mode"]))
    state["BackgroundReference"] = state.get("BackgroundReference") or branding.get("ProjectorBackground", "")
    state["LogoReference"] = state.get("LogoReference") or branding.get("ClientLogo") or branding.get("EventLogo", "")
    state["Theme"] = branding.get("ProjectorTheme", state.get("Theme", "Default"))
    return state


def _asset_choices(assets, categories):
    allowed = {category.casefold() for category in categories}
    choices = {"None": ""}
    for asset in assets:
        if str(asset.get("Category", "")).strip().casefold() not in allowed:
            continue
        name = str(asset.get("Name", "Untitled asset")).strip()
        asset_id = str(asset.get("AssetID", "")).strip()
        label = f"{name} · {asset_id}" if asset_id else name
        choices[label] = str(asset.get("MediaReference", "")).strip()
    return choices


def _choice_index(choices, reference):
    values = list(choices.values())
    try:
        return values.index(str(reference or "").strip())
    except ValueError:
        return 0


def render_broadcast_controller(db, event_id, control=None):
    event = db.get_event(event_id) or {}
    branding = dict((event.get("_EventPayload", {}) or {}).get("ProjectorBranding", {}) or {})
    state = dict(DEFAULT_BROADCAST)
    state.update({
        key: value for key, value in db.get_broadcast_state(event_id).items()
        if key in state
    })
    if not db.get_broadcast_state(event_id):
        state["Mode"] = branding.get("DefaultBroadcast", state["Mode"])
    db.ensure_existing_assets_catalogue()
    assets = db.get_assets()
    backgrounds = _asset_choices(
        assets,
        ("Backgrounds", "Mission Images"),
    )
    logos = _asset_choices(assets, ("Logos",))
    characters = _asset_choices(assets, ("Characters",))

    st.subheader("Broadcast")
    st.caption(
        "Controls the projector only. Participant screens are not changed."
    )
    mode = st.selectbox(
        "Broadcast",
        BROADCAST_MODES,
        index=BROADCAST_MODES.index(state["Mode"]),
        key=f"projector_broadcast_mode_{event_id}",
    )
    presentation_mode = st.toggle(
        "Presentation Mode",
        value=state["PresentationMode"],
        key=f"projector_presentation_mode_{event_id}",
        help=(
            "Maximum type and image sizes, high contrast and ballroom-ready "
            "text wrapping."
        ),
    )

    title = str(state.get("Title", ""))
    message = str(state.get("Message", ""))
    if mode in {"Instructions", "Custom Message", "Results"}:
        title = st.text_input(
            "Broadcast title",
            value=title,
            placeholder=(
                "Projector Message"
                if mode == "Custom Message"
                else mode
            ),
            key=f"projector_broadcast_title_{event_id}_{mode}",
        )
    if mode in {"Instructions", "Custom Message", "Results", "Championship"}:
        message = st.text_area(
            "Broadcast message",
            value=message,
            placeholder=(
                "Return at 2:00 PM"
                if mode == "Custom Message"
                else "Enter the full-screen transmission."
            ),
            key=f"projector_broadcast_message_{event_id}_{mode}",
        )

    background_reference = str(state.get("BackgroundReference") or branding.get("ProjectorBackground", ""))
    logo_reference = str(state.get("LogoReference") or branding.get("ClientLogo") or branding.get("EventLogo", ""))
    character_reference = str(state.get("CharacterReference", ""))
    custom_image_reference = str(state.get("CustomImageReference", ""))

    if mode in {"Welcome", "Instructions", "Results", "Championship"} and len(backgrounds) > 1:
        background_label = st.selectbox(
            "Background image",
            list(backgrounds),
            index=_choice_index(backgrounds, background_reference),
            key=f"projector_background_{event_id}_{mode}",
        )
        background_reference = backgrounds[background_label]
    if mode == "Welcome" and len(logos) > 1:
        logo_label = st.selectbox(
            "Client logo",
            list(logos),
            index=_choice_index(logos, logo_reference),
            key=f"projector_logo_{event_id}",
        )
        logo_reference = logos[logo_label]
    if mode in {"Instructions", "Results", "Championship"} and len(characters) > 1:
        character_label = st.selectbox(
            "Character portrait",
            list(characters),
            index=_choice_index(characters, character_reference),
            key=f"projector_character_{event_id}_{mode}",
        )
        character_reference = characters[character_label]

    uploaded_image = None
    if mode in {"Current Activity", "Instructions", "Results", "Championship"}:
        uploaded_image = st.file_uploader(
            "Optional projector image",
            type=["jpg", "jpeg", "png", "webp", "heic"],
            key=f"projector_custom_image_{event_id}_{mode}",
        )
        if custom_image_reference:
            preview = get_mission_media_url(custom_image_reference)
            if preview:
                st.image(preview, width="stretch")

    if control is None:
        st.info("Broadcast controls are read-only outside Control Centre.")
        return
    payload = {
        "Mode": mode,
        "PresentationMode": bool(presentation_mode),
        "Title": title,
        "Message": message,
        "BackgroundReference": background_reference,
        "LogoReference": logo_reference,
        "CharacterReference": character_reference,
        "CustomImageReference": custom_image_reference,
        "Theme": branding.get("ProjectorTheme", "Default"),
    }
    preview, apply = st.columns(2)
    if preview.button(
        "Preview Broadcast", width="stretch", key=f"preview_projector_broadcast_{event_id}",
    ):
        st.session_state[f"projector_preview_{event_id}"] = payload
    if apply.button(
        "Apply Broadcast", type="primary", width="stretch",
        key=f"apply_projector_broadcast_{event_id}",
    ):
        if uploaded_image is not None:
            custom_image_reference = upload_library_asset(
                uploaded_image,
                f"PROJECTOR-{event_id}",
                current_reference=custom_image_reference,
            )
        payload["CustomImageReference"] = custom_image_reference
        control.broadcast(event_id, payload)
        st.success(f"{mode} is now live on the projector.")
        st.rerun()
    st.link_button(
        "Open Projector",
        f"?view=projector&event_id={quote(str(event_id))}",
        width="stretch",
    )
    preview_state = st.session_state.get(f"projector_preview_{event_id}")
    if preview_state:
        st.markdown("#### Broadcast Preview — not live")
        performance = load_performance_snapshot(db, event_id)
        preview_leaderboard = [
            (row["TeamIdentity"], row["TotalScore"]) for row in performance["Teams"]
        ]
        mission = db.get_current_mission(event_id)
        stage = (mission or {}).get("_RuntimeStage", {})
        timer = db.get_stage_timer(
            event_id, stage.get("StageNo", ""), stage.get("DurationMinutes", 0),
        )
        render_projector_broadcast(
            preview_state,
            event=event,
            mission=mission,
            leaderboard=preview_leaderboard,
            wallet_status={},
            timer=timer,
            performance_snapshot=performance,
        )


def _media_url(reference):
    return html.escape(
        get_mission_media_url(str(reference or "").strip()),
        quote=True,
    )


def _background_style(reference):
    url = _media_url(reference)
    return (
        f"background-image:linear-gradient(rgba(2,12,27,.28),"
        f"rgba(2,12,27,.76)),url('{url}');"
        if url else ""
    )


def _image(reference, class_name, alt):
    url = _media_url(reference)
    if not url:
        return ""
    return (
        f'<img class="{class_name}" src="{url}" '
        f'alt="{html.escape(alt, quote=True)}">'
    )


def render_projector_broadcast(
    state,
    *,
    event,
    mission,
    leaderboard,
    wallet_status,
    timer,
    performance_snapshot=None,
):
    mode = str(state.get("Mode", "Welcome"))
    presentation = bool(state.get("PresentationMode", True))
    theme = "".join(character for character in str(state.get("Theme", "Default")).casefold() if character.isalnum() or character == "-")
    presentation_class = (" broadcast-presentation" if presentation else "") + f" broadcast-theme-{theme or 'default'}"
    event_title = html.escape(
        str(
            event.get("ProgrammeName")
            or event.get("ExperienceName")
            or event.get("ProgrammeType")
            or event.get("EventName")
            or "Live Experience"
        )
    )
    client = html.escape(str(event.get("Client", "")))
    title = html.escape(str(state.get("Title", "")).strip())
    message = html.escape(str(state.get("Message", "")).strip()).replace(
        "\n",
        "<br>",
    )

    if mode == "Blank":
        st.markdown(
            '<div class="broadcast-blank" aria-label="Blank projector"></div>',
            unsafe_allow_html=True,
        )
        return True

    if mode == "Welcome":
        logo = _image(state.get("LogoReference"), "broadcast-logo", "Client logo")
        st.markdown(
            f"""
            <div class="broadcast-screen{presentation_class}"
                 style="{_background_style(state.get('BackgroundReference'))}">
              <div class="broadcast-brand">EXOS</div>
              <div class="broadcast-product">{PLATFORM_EXPANSION}</div>
              <div class="broadcast-title">{event_title}</div>
              <div class="broadcast-subtitle">{client}</div>
              {logo}
              <div class="broadcast-tagline">{PLATFORM_TAGLINE}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode in {"Current Activity", "Multiple Activities"}:
        if not mission:
            st.markdown(
                f"""
                <div class="broadcast-screen broadcast-centred{presentation_class}">
                  <div class="broadcast-message">No activity selected.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return True

        if mode == "Current Activity":
            mission_title = html.escape(
                str((mission or {}).get("Title", "Waiting for Activity"))
            )
            instructions = html.escape(
                str(
                    (mission or {}).get("ParticipantInstructions")
                    or (mission or {}).get("Description")
                    or "Stand by for the next Activity."
                )
            ).replace("\n", "<br>")
            image = _image(
                (mission or {}).get("ReferenceImageURL", ""),
                "broadcast-experience-image",
                "Activity reference",
            )
            st.markdown(
                f"""
                <div class="broadcast-screen broadcast-experience{presentation_class}">
                  <div class="broadcast-experience-copy">
                    <div class="broadcast-kicker">Current Activity</div>
                    <div class="broadcast-title">{mission_title}</div>
                    <div class="broadcast-message">{instructions}</div>
                  </div>
                  {image}
                </div>
                """,
                unsafe_allow_html=True,
            )
            return True

        rows = "".join(
            f"""
            <div class="broadcast-ranking">
              <span>{position}. {html.escape(str(activity.get('Title', 'Activity')))}</span>
              <strong>{html.escape(str(activity.get('DurationMinutes', '')))} min</strong>
            </div>
            """
            for position, activity in enumerate(
                mission.get("Activities", []) if isinstance(mission, dict) else mission, start=1
            )
            if position <= 6
        ) or '<div class="broadcast-message">No activities are active.</div>'
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}">
              <div class="broadcast-title">Multiple Activities</div>
              {rows}
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Timer":
        remaining = remaining_seconds(timer or {})
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}">
              <div class="broadcast-kicker">Timer</div>
              <div class="broadcast-countdown">
                {remaining // 60:02d}:{remaining % 60:02d}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Leaderboard":
        performance_teams = (performance_snapshot or {}).get("Teams", [])
        rows = "".join(
            f"""
            <div class="broadcast-ranking">
              <span>{row.get('Rank', position)}. {html.escape(str(row.get('TeamIdentity', '')))}</span>
              <strong>{html.escape(str(row.get('TotalScore', 0)))} pts · {html.escape(str(round(row.get('PerformancePercentage'), 1)) if row.get('PerformancePercentage') is not None else '—')}%</strong>
            </div>
            """
            for position, row in enumerate(performance_teams[:8], start=1)
        ) or '<div class="broadcast-message">No approved scores yet.</div>'
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-rankings{presentation_class}">
              <div class="broadcast-title">Live Leaderboard</div>
              {rows}
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Scores":
        wallets = sorted(
            (wallet_status or {}).get("Wallets", []) or [],
            key=lambda row: -float(row.get("EarnedCredits", 0) or 0),
        )
        rows = "".join(
            f"""
            <div class="broadcast-ranking">
              <span>{position}. {html.escape(str(wallet.get('TeamName', '')))}</span>
              <strong>{html.escape(str(wallet.get('EarnedCredits', 0)))} Credits</strong>
            </div>
            """
            for position, wallet in enumerate(wallets[:8], start=1)
        ) or '<div class="broadcast-message">No Intelligence Credits yet.</div>'
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-rankings{presentation_class}">
              <div class="broadcast-title">Intelligence Credits</div>
              {rows}
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Custom Message":
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}">
              <div class="broadcast-title">{title or 'Projector Message'}</div>
              <div class="broadcast-message">{message}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Instructions":
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}"
                 style="{_background_style(state.get('BackgroundReference'))}">
              <div class="broadcast-kicker">Instructions</div>
              <div class="broadcast-title">{title or 'Instructions'}</div>
              <div class="broadcast-message">{message}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Results":
        portrait = _image(
            state.get("CharacterReference"),
            "broadcast-king",
            "Champion",
        )
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}"
                 style="{_background_style(state.get('BackgroundReference'))}">
              {portrait}
              <div>
                <div class="broadcast-kicker">Results</div>
                <div class="broadcast-title">{title or 'Live Results'}</div>
                <div class="broadcast-message">{message}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Championship":
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-rankings{presentation_class}">
              <div class="broadcast-title">Championship</div>
              <div class="broadcast-message">{message or 'Top team by competitive score.'}</div>
              <div class="broadcast-metric">{title}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    return False
