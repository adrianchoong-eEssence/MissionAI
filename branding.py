"""Shared EXOS brand system for every Streamlit surface."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "Assets" / "exos"

EXOS_NAVY = "#082D58"
EXOS_BLUE = "#082D58"
EXOS_GOLD = "#B59A37"
EXOS_INK = "#082D58"
EXOS_PAPER = "#FFFFFF"
PLATFORM_NAME = "EXOS"
PLATFORM_EXPANSION = "eEssence eXperiential OS"
COMPANY_NAME = "eEssence"
BROWSER_TITLE = "EXOS | eEssence eXperiential OS"


def asset_path(name: str) -> str:
    return str(ASSETS / name)


def _data_uri(path: Path) -> str:
    mime = "image/svg+xml" if path.suffix.lower() == ".svg" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def experience_title(event: dict | None = None, fallback: str = "Mission AI") -> str:
    """Resolve the experience, never the platform, from an event record."""
    row = event or {}
    for key in ("ExperienceName", "ProgrammeName", "ProgrammeType"):
        value = str(row.get(key, "") or "").strip()
        if value:
            return value
    name = str(row.get("EventName", "") or "").strip()
    for known in (
        "Formula R.A.C.E.",
        "Formula RACE",
        "Road Hunt",
        "Catalyst Challenge",
        "Catalyst",
        "Mission AI",
    ):
        if known.casefold() in name.casefold():
            return "Formula R.A.C.E." if known == "Formula RACE" else known
    return fallback


def configure_page(layout: str = "wide") -> None:
    st.set_page_config(
        page_title=BROWSER_TITLE,
        page_icon=asset_path("exos-favicon-32.png"),
        layout=layout,
    )


def apply_branding(*, dark: bool = False) -> None:
    """Install visual tokens plus title, favicon and install metadata."""
    logo = _data_uri(ASSETS / ("exos-horizontal-dark.svg" if dark else "exos-horizontal-light.svg"))
    manifest = {
        "name": PLATFORM_NAME,
        "short_name": PLATFORM_NAME,
        "description": PLATFORM_EXPANSION,
        "display": "standalone",
        "start_url": ".",
        "background_color": EXOS_INK if dark else EXOS_PAPER,
        "theme_color": EXOS_NAVY,
        "icons": [
            {"src": _data_uri(ASSETS / "exos-mobile-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": _data_uri(ASSETS / "exos-desktop-512.png"), "sizes": "512x512", "type": "image/png"},
        ],
    }
    manifest_uri = "data:application/manifest+json;base64," + base64.b64encode(
        json.dumps(manifest).encode()
    ).decode()
    favicon = _data_uri(ASSETS / "exos-favicon-32.png")

    st.markdown(
        f"""
        <style>
          :root {{
            --exos-navy:{EXOS_NAVY}; --exos-blue:{EXOS_BLUE};
            --exos-gold:{EXOS_GOLD}; --exos-ink:{EXOS_INK};
          }}
          html, body, [class*="css"], .stApp, button, input, textarea, select {{
            font-family:Eurostile, "Arial Narrow", Arial, sans-serif;
          }}
          html {{ color-scheme:light; }}
          .stApp {{ background:#FFFFFF; color:{EXOS_NAVY}; }}
          [data-testid="stSidebar"] {{ background:#FFFFFF; color:{EXOS_NAVY}; }}
          input, textarea, select {{
            background:#FFFFFF !important; color:{EXOS_NAVY} !important;
          }}
          [data-testid="stWidgetLabel"] p, .stTextInput label p {{
            color:{EXOS_NAVY} !important;
          }}
          .stButton > button {{
            background:{EXOS_NAVY}; border-color:{EXOS_NAVY}; color:#FFFFFF;
          }}
          .stButton > button p {{ color:#FFFFFF !important; }}
          #MainMenu, [data-testid="stStatusWidget"], footer {{visibility:hidden;}}
          [data-testid="stHeader"] {{background:transparent;}}
          [data-testid="stSidebar"] {{
            border-right:1px solid rgba(8,45,88,.12);
          }}
          [data-testid="stSidebar"] > div:first-child::before {{
            content:""; display:block; width:172px; height:54px;
            margin:22px auto 8px; background:url('{logo}') center/contain no-repeat;
          }}
          .exos-kicker {{
            color:{EXOS_BLUE}; font-size:.76rem; font-weight:800;
            letter-spacing:.18em; text-transform:uppercase;
          }}
          .exos-experience {{
            color:{EXOS_NAVY}; font-size:clamp(2rem,5vw,4.3rem);
            font-weight:800; line-height:1.02; margin:.3rem 0 .7rem;
          }}
          .exos-powered {{
            color:inherit; opacity:.68; font-size:.82rem; letter-spacing:.08em;
          }}
          .exos-footer {{
            border-top:1px solid rgba(8,45,88,.14); margin-top:3.5rem;
            padding:1.2rem 0 1.8rem; text-align:center; color:{EXOS_NAVY};
          }}
          .exos-footer strong {{letter-spacing:.08em;}}
          .stButton > button[kind="primary"] {{
            background:{EXOS_NAVY}; border-color:{EXOS_NAVY};
          }}
          .stButton > button[kind="primary"]:hover {{
            background:{EXOS_BLUE}; border-color:{EXOS_BLUE};
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    components.html(
        f"""
        <script>
          const d = window.parent.document;
          d.title = {json.dumps(BROWSER_TITLE)};
          let icon = d.querySelector("link[rel~='icon']");
          if (!icon) {{ icon=d.createElement('link'); icon.rel='icon'; d.head.appendChild(icon); }}
          icon.href = {json.dumps(favicon)};
          let manifest = d.querySelector("link[rel='manifest']");
          if (!manifest) {{ manifest=d.createElement('link'); manifest.rel='manifest'; d.head.appendChild(manifest); }}
          manifest.href = {json.dumps(manifest_uri)};
          let apple = d.querySelector("meta[name='apple-mobile-web-app-title']");
          if (!apple) {{ apple=d.createElement('meta'); apple.name='apple-mobile-web-app-title'; d.head.appendChild(apple); }}
          apple.content = 'EXOS';
          if (!window.parent.sessionStorage.getItem('exosSplashSeen')) {{
            window.parent.sessionStorage.setItem('exosSplashSeen', '1');
            const splash=d.createElement('div');
            splash.id='exos-splash';
            splash.innerHTML='<div style="font:800 64px Arial;letter-spacing:.16em">EX<span style="color:{EXOS_BLUE}">O</span>S</div>'
              + '<div style="margin-top:18px;letter-spacing:.18em;font:15px Arial">eEssence eXperiential OS</div>'
              + '<div style="margin-top:38px;opacity:.72;font:12px Eurostile,Arial;letter-spacing:.12em">by eEssence</div>';
            splash.style.cssText='position:fixed;inset:0;z-index:999999;display:flex;flex-direction:column;align-items:center;justify-content:center;background:{EXOS_NAVY};color:white;transition:opacity .35s ease';
            d.body.appendChild(splash);
            setTimeout(() => {{ splash.style.opacity='0'; setTimeout(() => splash.remove(), 380); }}, 850);
          }}
        </script>
        """,
        height=0,
        width=0,
    )


def experience_header(
    title: str,
    *,
    welcome: bool = False,
    subtitle: str = "Today's Experience",
) -> None:
    heading = "Welcome to EXOS" if welcome else "EXOS"
    st.markdown(
        f"""
        <div class="exos-hero">
          <div class="exos-kicker">{html.escape(heading)}</div>
          <div style="margin-top:1.35rem;color:inherit;opacity:.68;font-size:.86rem;
                      letter-spacing:.14em;text-transform:uppercase;">{html.escape(subtitle)}</div>
          <div class="exos-experience">{html.escape(title)}</div>
          <div class="exos-powered">by eEssence</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def footer(*, report: bool = False) -> None:
    second_line = "Designed by eEssence Consultants" if report else PLATFORM_EXPANSION
    st.markdown(
        f"""
        <div class="exos-footer">
          <strong>EXOS</strong><br>
          <span style="font-size:.78rem;opacity:.72;">{html.escape(second_line)}</span>
          <br><span style="font-size:.72rem;opacity:.62;">by eEssence</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
