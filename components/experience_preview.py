"""Shared participant Experience renderer used by previews and runtime."""

import streamlit as st


def experience_participant_view(resolved):
    """Return the exact participant-facing contract without admin identifiers."""
    source = dict(resolved or {})
    assets = list(source.get("Assets", []) or [])
    character = dict(source.get("Character") or {})
    return {
        "Title": str(source.get("ParticipantTitle", "")),
        "Narrative": str(source.get("ParticipantNarrative", "")),
        "Task": str(source.get("ParticipantTask", "")),
        "EvidenceType": str(source.get("EvidenceType", "NONE")),
        "EvidenceInstructions": str(source.get("EvidenceInstructions", "")),
        "Hint": str(source.get("Hint", "")),
        "IntelligenceCredits": int(source.get("IntelligenceCredits", 0) or 0),
        "CharacterName": str(character.get("Name", "")),
        "CharacterAsset": str(character.get("AssetReference", "")),
        "ReferenceAsset": str((assets[0] if assets else {}).get("MediaReference", "")),
        "Crop": dict((assets[0] if assets else {}).get("Crop", {}) or {}),
        "MissingAssets": list(source.get("MissingAssetIDs", []) or []),
    }


def render_experience_participant(resolved):
    """Render the same contract in Experience Centre, Event Centre, and tests."""
    view = experience_participant_view(resolved)
    if view["ReferenceAsset"]:
        st.image(view["ReferenceAsset"], width="stretch")
    elif view["MissingAssets"]:
        st.info("Reference image is unavailable; the Experience remains usable.")
    if view["CharacterName"]:
        st.caption(view["CharacterName"])
    st.subheader(view["Title"] or "Experience")
    if view["Narrative"]:
        st.write(view["Narrative"])
    if view["Task"]:
        st.info(view["Task"])
    if view["EvidenceInstructions"]:
        st.caption(f"{view['EvidenceType']}: {view['EvidenceInstructions']}")
    if view["Hint"]:
        with st.expander("Hint"):
            st.write(view["Hint"])
    st.metric("Intelligence Credits", view["IntelligenceCredits"])
    return view
