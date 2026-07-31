import streamlit as st

from data.google_sheets import GoogleSheetsDB
from data.mission_media import get_mission_media_url


CATEGORIES = ["Characters", "Mission Images", "Logos", "Backgrounds"]


def show_asset_library():
    st.title("Asset Library")
    st.caption(
        "Upload once, then reuse the same private media asset across Experiences."
    )
    db = GoogleSheetsDB()
    db.ensure_existing_assets_catalogue()

    category = st.segmented_control(
        "Category",
        CATEGORIES,
        default=CATEGORIES[0],
        key="asset_library_category",
    ) or CATEGORIES[0]

    with st.expander(f"Upload {category.rstrip('s')}", expanded=False):
        name = st.text_input(
            "Asset Name",
            key=f"asset_upload_name_{category}",
        )
        uploaded = st.file_uploader(
            "Drop image here or browse",
            type=["jpg", "jpeg", "png", "webp", "heic"],
            key=f"asset_upload_file_{category}",
            help="Stored once in the existing EXOS private media bucket.",
        )
        if st.button(
            "Upload Asset",
            type="primary",
            width="stretch",
            key=f"asset_upload_button_{category}",
        ):
            try:
                db.create_asset(category, name, uploaded)
            except Exception as error:
                st.error(str(error))
            else:
                st.success(f"{name.strip()} added to {category}.")
                st.rerun()

    assets = db.get_assets(category)
    st.subheader(category)
    if not assets:
        st.info(f"No {category.lower()} in the library yet.")
        return

    columns = st.columns(4)
    for index, asset in enumerate(assets):
        asset_id = str(asset.get("AssetID", "")).strip()
        asset_name = str(asset.get("Name", "Untitled asset")).strip()
        reference = str(asset.get("MediaReference", "")).strip()
        preview = get_mission_media_url(reference)
        with columns[index % len(columns)]:
            with st.container(border=True):
                if preview:
                    try:
                        st.image(preview, width="stretch")
                    except Exception:
                        st.warning("Preview unavailable.")
                st.markdown(f"**{asset_name}**")

                with st.popover("Manage", width="stretch"):
                    renamed = st.text_input(
                        "Name",
                        value=asset_name,
                        key=f"asset_rename_{asset_id}",
                    )
                    replacement = st.file_uploader(
                        "Replace image",
                        type=["jpg", "jpeg", "png", "webp", "heic"],
                        key=f"asset_replace_{asset_id}",
                    )
                    if st.button(
                        "Save Changes",
                        width="stretch",
                        key=f"asset_save_{asset_id}",
                    ):
                        try:
                            db.update_asset(
                                asset_id,
                                name=renamed,
                                uploaded_file=replacement,
                            )
                        except Exception as error:
                            st.error(str(error))
                        else:
                            st.success("Asset updated.")
                            st.rerun()

                    st.divider()
                    confirm_delete = st.checkbox(
                        "I understand this removes the stored asset",
                        key=f"asset_delete_confirm_{asset_id}",
                    )
                    if st.button(
                        "Delete",
                        type="primary",
                        disabled=not confirm_delete,
                        width="stretch",
                        key=f"asset_delete_{asset_id}",
                    ):
                        try:
                            db.delete_asset(asset_id)
                        except Exception as error:
                            st.error(str(error))
                        else:
                            st.success("Asset deleted.")
                            st.rerun()
