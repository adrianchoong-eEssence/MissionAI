import html

import streamlit as st

from branding import PLATFORM_EXPANSION, PLATFORM_TAGLINE
from data.mission_media import (
    get_mission_media_url,
    upload_library_asset,
)
from engines.stage_timer import remaining_seconds


BROADCAST_MODES = [
    "Welcome",
    "Story",
    "Experience",
    "Countdown",
    "Leaderboard",
    "Credits",
    "Announcement",
    "Sync AI",
    "The King",
    "Blank",
    "Custom Image",
    "Custom Video",
]

DEFAULT_BROADCAST = {
    "Mode": "Welcome",
    "PresentationMode": True,
    "Title": "",
    "Message": "",
    "BackgroundReference": "",
    "LogoReference": "",
    "CharacterReference": "",
    "CustomImageReference": "",
}


def projector_broadcast_state(event):
    from data.google_sheets import GoogleSheetsDB

    metadata = GoogleSheetsDB.event_metadata(event)
    stored = metadata.get("ProjectorBroadcast", {}) or {}
    state = dict(DEFAULT_BROADCAST)
    state.update({
        key: value
        for key, value in dict(stored).items()
        if key in state
    })
    if state["Mode"] not in BROADCAST_MODES:
        state["Mode"] = "Welcome"
    state["PresentationMode"] = bool(state.get("PresentationMode", True))
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


def render_broadcast_controller(db, event_id):
    event = db.get_event(event_id) or {}
    state = projector_broadcast_state(event)
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
    if mode in {"Announcement", "Sync AI", "The King"}:
        title = st.text_input(
            "Broadcast title",
            value=title,
            placeholder=(
                "Lunch Break"
                if mode == "Announcement"
                else mode
            ),
            key=f"projector_broadcast_title_{event_id}_{mode}",
        )
    if mode in {"Story", "Announcement", "The King"}:
        message = st.text_area(
            "Broadcast message",
            value=message,
            placeholder=(
                "Return at 2:00 PM"
                if mode == "Announcement"
                else "Enter the full-screen transmission."
            ),
            key=f"projector_broadcast_message_{event_id}_{mode}",
        )

    background_reference = str(state.get("BackgroundReference", ""))
    logo_reference = str(state.get("LogoReference", ""))
    character_reference = str(state.get("CharacterReference", ""))
    custom_image_reference = str(state.get("CustomImageReference", ""))

    if mode in {"Welcome", "Sync AI", "The King"}:
        background_label = st.selectbox(
            "Background image",
            list(backgrounds),
            index=_choice_index(backgrounds, background_reference),
            key=f"projector_background_{event_id}_{mode}",
        )
        background_reference = backgrounds[background_label]
    if mode == "Welcome":
        logo_label = st.selectbox(
            "Client logo",
            list(logos),
            index=_choice_index(logos, logo_reference),
            key=f"projector_logo_{event_id}",
        )
        logo_reference = logos[logo_label]
    if mode in {"Story", "The King"}:
        character_label = st.selectbox(
            "Character portrait",
            list(characters),
            index=_choice_index(characters, character_reference),
            key=f"projector_character_{event_id}_{mode}",
        )
        character_reference = characters[character_label]

    uploaded_image = None
    if mode == "Custom Image":
        uploaded_image = st.file_uploader(
            "Upload projector image",
            type=["jpg", "jpeg", "png", "webp", "heic"],
            key=f"projector_custom_image_{event_id}",
        )
        if custom_image_reference:
            preview = get_mission_media_url(custom_image_reference)
            if preview:
                st.image(preview, width="stretch")
    elif mode == "Custom Video":
        st.info("Custom Video is reserved. Playback is not enabled yet.")

    if st.button(
        "Apply Broadcast",
        type="primary",
        width="stretch",
        key=f"apply_projector_broadcast_{event_id}",
    ):
        if uploaded_image is not None:
            custom_image_reference = upload_library_asset(
                uploaded_image,
                f"PROJECTOR-{event_id}",
                current_reference=custom_image_reference,
            )
        payload = {
            "Mode": mode,
            "PresentationMode": bool(presentation_mode),
            "Title": title,
            "Message": message,
            "BackgroundReference": background_reference,
            "LogoReference": logo_reference,
            "CharacterReference": character_reference,
            "CustomImageReference": custom_image_reference,
        }
        db.update_event_metadata(event_id, {"ProjectorBroadcast": payload})
        st.success(f"{mode} is now live on the projector.")
        st.rerun()


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
):
    mode = str(state.get("Mode", "Welcome"))
    presentation = bool(state.get("PresentationMode", True))
    presentation_class = " broadcast-presentation" if presentation else ""
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

    if mode == "Story":
        portrait_reference = (
            state.get("CharacterReference")
            or (mission or {}).get("CharacterPortraitURL", "")
        )
        portrait = _image(
            portrait_reference,
            "broadcast-character",
            str((mission or {}).get("CharacterSource", "Character")),
        )
        transmission = message or html.escape(
            str((mission or {}).get("Transmission", "Incoming transmission…"))
        ).replace("\n", "<br>")
        character_name = html.escape(
            str((mission or {}).get("CharacterSource", "Transmission"))
        )
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-story{presentation_class}">
              {portrait}
              <div class="broadcast-story-copy">
                <div class="broadcast-kicker">{character_name}</div>
                <div class="broadcast-message">{transmission}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Experience":
        image = _image(
            (mission or {}).get("ReferenceImageURL", ""),
            "broadcast-experience-image",
            "Experience reference",
        )
        mission_title = html.escape(
            str((mission or {}).get("Title", "Waiting for Experience"))
        )
        instructions = html.escape(
            str(
                (mission or {}).get("ParticipantInstructions")
                or (mission or {}).get("Description")
                or "Stand by for the next Experience."
            )
        ).replace("\n", "<br>")
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-experience{presentation_class}">
              <div class="broadcast-experience-copy">
                <div class="broadcast-kicker">Current Experience</div>
                <div class="broadcast-title">{mission_title}</div>
                <div class="broadcast-message">{instructions}</div>
              </div>
              {image}
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Countdown":
        remaining = remaining_seconds(timer or {})
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}">
              <div class="broadcast-kicker">Countdown</div>
              <div class="broadcast-countdown">
                {remaining // 60:02d}:{remaining % 60:02d}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Leaderboard":
        rows = "".join(
            f"""
            <div class="broadcast-ranking">
              <span>{position}. {html.escape(str(team))}</span>
              <strong>{html.escape(str(score))} pts</strong>
            </div>
            """
            for position, (team, score) in enumerate(leaderboard[:8], start=1)
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

    if mode == "Credits":
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

    if mode == "Announcement":
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}">
              <div class="broadcast-title">{title or 'Announcement'}</div>
              <div class="broadcast-message">{message}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Sync AI":
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}"
                 style="{_background_style(state.get('BackgroundReference'))}">
              <div class="broadcast-kicker">EXOS</div>
              <div class="broadcast-title">{title or 'Sync AI'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "The King":
        portrait = _image(
            state.get("CharacterReference"),
            "broadcast-king",
            "The King",
        )
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-king-screen{presentation_class}"
                 style="{_background_style(state.get('BackgroundReference'))}">
              {portrait}
              <div class="broadcast-king-copy">
                <div class="broadcast-kicker">The King</div>
                <div class="broadcast-title">{title or 'The King'}</div>
                <div class="broadcast-message">{message}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Custom Image":
        image = _image(
            state.get("CustomImageReference"),
            "broadcast-custom-image",
            "Custom projector broadcast",
        )
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}">
              {image or '<div class="broadcast-message">No custom image selected.</div>'}
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    if mode == "Custom Video":
        st.markdown(
            f"""
            <div class="broadcast-screen broadcast-centred{presentation_class}">
              <div class="broadcast-title">Custom Video</div>
              <div class="broadcast-message">Playback will be enabled in a future release.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return True

    return False

