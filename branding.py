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
BROWSER_TITLE = "EXOS"


def asset_path(name: str) -> str:
    return str(ASSETS / name)


def _data_uri(path: Path) -> str:
    mime = "image/svg+xml" if path.suffix.lower() == ".svg" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def experience_title(event: dict | None = None, fallback: str = "Mission AI") -> str:
    """Resolve the experience, never the platform, from an event record."""
    row = event or {}
    generic_names = {"team building", "countries", "programme", "event"}
    for key in ("ExperienceName", "ProgrammeName", "ProgrammeType"):
        value = str(row.get(key, "") or "").strip()
        if value and value.casefold() not in generic_names:
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


def apply_branding(*, dark: bool = False, participant_pwa: bool = False) -> None:
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
    manifest_href = manifest_uri
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
          .block-container {{padding-top:2.2rem; padding-bottom:3rem;}}
          h1 {{font-size:clamp(2.35rem,4vw,4rem) !important; letter-spacing:-.035em;}}
          h2, h3 {{letter-spacing:-.02em;}}
          [data-testid="stSidebar"] {{
            background:#FFFFFF; color:{EXOS_NAVY}; min-width:290px;
          }}
          input, textarea, select {{
            background:#FFFFFF !important; color:{EXOS_NAVY} !important;
          }}
          input::placeholder, textarea::placeholder {{
            color:{EXOS_NAVY} !important; opacity:.55;
          }}
          [data-testid="stWidgetLabel"] p, .stTextInput label p {{
            color:{EXOS_NAVY} !important;
          }}
          [role="radiogroup"] label p {{
            color:{EXOS_NAVY} !important;
          }}
          .stButton > button {{
            background:{EXOS_NAVY}; border-color:{EXOS_NAVY}; color:#FFFFFF;
          }}
          .stButton > button p {{ color:#FFFFFF !important; }}
          #MainMenu, [data-testid="stStatusWidget"], footer,
          [data-testid="stHeader"], [data-testid="stToolbar"] {{visibility:hidden;}}
          [data-testid="stSidebar"] {{
            border-right:2px solid rgba(8,45,88,.12);
          }}
          [data-testid="stSidebar"] > div:first-child::before {{
            content:""; display:block; width:220px; height:82px;
            margin:24px auto 18px; background:url('{logo}') center/contain no-repeat;
          }}
          [data-testid="stSidebar"] [role="radiogroup"] {{
            gap:.48rem; padding:.25rem .25rem .75rem;
          }}
          [data-testid="stSidebar"] [role="radiogroup"] label {{
            min-height:48px; padding:.68rem .85rem; border-radius:10px;
            border:1px solid transparent; font-size:1.08rem; font-weight:650;
          }}
          [data-testid="stSidebar"] [role="radiogroup"] label p {{
            color:{EXOS_NAVY} !important;
          }}
          [data-testid="stSidebar"] [role="radiogroup"] label:hover {{
            background:rgba(8,45,88,.06);
          }}
          [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
            background:{EXOS_NAVY}; border-color:{EXOS_NAVY};
          }}
          [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {{
            color:#FFFFFF !important;
          }}
          [data-testid="stSidebar"] p {{font-size:1rem; line-height:1.35;}}
          [data-testid="stMetric"] {{
            border:1px solid rgba(8,45,88,.12); border-radius:14px;
            padding:1rem 1.15rem; background:#FFFFFF;
          }}
          [data-testid="stMetric"] * {{color:{EXOS_NAVY} !important;}}
          [data-testid="stVerticalBlockBorderWrapper"] {{
            border-color:rgba(8,45,88,.14) !important; border-radius:16px !important;
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
          const root = (() => {{
            try {{
              if (window.top && window.top.document) return window.top;
            }} catch (error) {{}}
            return window.parent;
          }})();
          const d = root.document;
          d.title = {json.dumps(BROWSER_TITLE)};
          const titleNode=d.querySelector('title');
          if (titleNode) {{
            new MutationObserver(() => {{
              if (d.title !== 'EXOS') d.title='EXOS';
            }}).observe(titleNode, {{childList:true,characterData:true,subtree:true}});
          }}
          let icon = d.querySelector("link[rel~='icon']");
          if (!icon) {{ icon=d.createElement('link'); icon.rel='icon'; d.head.appendChild(icon); }}
          icon.href = {json.dumps(favicon)};
          let manifest = d.querySelector("link[rel='manifest']");
          if (!manifest) {{ manifest=d.createElement('link'); manifest.rel='manifest'; d.head.appendChild(manifest); }}
          manifest.href = {
              "new URL('app/static/exos-participant.webmanifest', window.parent.location.href).href"
              if participant_pwa
              else json.dumps(manifest_href)
          };
          let apple = d.querySelector("meta[name='apple-mobile-web-app-title']");
          if (!apple) {{ apple=d.createElement('meta'); apple.name='apple-mobile-web-app-title'; d.head.appendChild(apple); }}
          apple.content = 'EXOS';
          let appName = d.querySelector("meta[name='application-name']");
          if (!appName) {{ appName=d.createElement('meta'); appName.name='application-name'; d.head.appendChild(appName); }}
          appName.content = 'EXOS';
          {"const savedUrl=root.localStorage.getItem('exosParticipantSessionUrl');"
           "if (!root.location.search && savedUrl) {"
           "  const saved=new URL(savedUrl);"
           "  if (saved.origin === root.location.origin && saved.search) {"
           "    root.location.replace(saved.href);"
           "  }"
           "}" if participant_pwa else ""}
          if (!root.sessionStorage.getItem('exosSplashSeen')) {{
            root.sessionStorage.setItem('exosSplashSeen', '1');
            const splash=d.createElement('div');
            splash.id='exos-splash';
            splash.innerHTML='<div style="font:800 64px Eurostile,Arial;letter-spacing:.06em">E<span style="color:{EXOS_GOLD}">X</span>OS</div>'
              + '<div style="margin-top:18px;letter-spacing:.18em;font:15px Eurostile,Arial">eEssence eXperiential OS</div>';
            splash.style.cssText='position:fixed;inset:0;z-index:999999;display:flex;flex-direction:column;align-items:center;justify-content:center;background:{EXOS_NAVY};color:white;transition:opacity .35s ease';
            d.body.appendChild(splash);
            setTimeout(() => {{ splash.style.opacity='0'; setTimeout(() => splash.remove(), 380); }}, 850);
          }}
        </script>
        """,
        height=0,
        width=0,
    )


def participant_install_experience() -> None:
    """Offer optional installation after a participant has joined."""
    components.html(
        f"""
        <style>
          * {{ box-sizing:border-box; }}
          body {{ margin:0; font-family:Eurostile,"Arial Narrow",Arial,sans-serif; }}
          .install-card {{
            border:1px solid rgba(8,45,88,.16); border-radius:18px;
            padding:18px; background:#fff; color:{EXOS_NAVY};
          }}
          .install-row {{ display:flex; align-items:center; gap:14px; }}
          .install-icon {{ width:52px; height:52px; border-radius:12px; }}
          .install-copy {{ flex:1; min-width:0; }}
          .install-title {{ font-size:18px; font-weight:800; }}
          .install-description {{ margin-top:3px; font-size:13px; opacity:.72; }}
          .install-actions {{ display:flex; gap:9px; margin-top:15px; }}
          button {{
            border-radius:10px; padding:10px 14px; font:700 14px inherit;
            cursor:pointer;
          }}
          #install {{ color:#fff; background:{EXOS_NAVY}; border:1px solid {EXOS_NAVY}; }}
          #continue {{ color:{EXOS_NAVY}; background:#fff; border:1px solid rgba(8,45,88,.28); }}
          #instructions {{
            display:none; margin-top:14px; padding:13px 14px;
            background:rgba(8,45,88,.055); border-radius:11px;
            font-size:14px; line-height:1.55;
          }}
          #instructions strong {{ display:block; margin-bottom:4px; }}
          @media(max-width:420px) {{
            .install-actions {{ flex-direction:column; }}
            button {{ width:100%; }}
          }}
        </style>
        <div class="install-card" id="card">
          <div class="install-row">
            <img class="install-icon" src="{_data_uri(ASSETS / "exos-mobile-192.png")}" alt="EXOS">
            <div class="install-copy">
              <div class="install-title">Install EXOS</div>
              <div class="install-description">{PLATFORM_EXPANSION}</div>
            </div>
          </div>
          <div class="install-actions">
            <button id="install">Install EXOS</button>
            <button id="continue">Continue in Browser</button>
          </div>
          <div id="instructions"></div>
        </div>
        <script>
          const host=(() => {{
            try {{
              if (window.top && window.top.document) return window.top;
            }} catch (error) {{}}
            return window.parent;
          }})();
          const current=host.location.href;
          if (host.location.search) {{
            host.localStorage.setItem('exosParticipantSessionUrl', current);
          }}

          let installEvent=host.__exosInstallPrompt || null;
          if (!host.__exosInstallListenerReady) {{
            host.__exosInstallListenerReady=true;
            host.addEventListener('beforeinstallprompt', event => {{
              event.preventDefault();
              host.__exosInstallPrompt=event;
            }});
          }}

          const ua=navigator.userAgent;
          const ios=/iPad|iPhone|iPod/.test(ua)
            || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
          const android=/Android/i.test(ua);
          const instructions=document.getElementById('instructions');

          function showInstructions() {{
            if (ios) {{
              instructions.innerHTML='<strong>Install on iPhone or iPad</strong>'
                + 'Open this page in Safari. Tap <b>Share</b>, tap '
                + '<b>Add to Home Screen</b>, then tap <b>Add</b>.';
            }} else if (android) {{
              instructions.innerHTML='<strong>Install on Android</strong>'
                + 'Open this page in Chrome. Tap <b>Install App</b> or '
                + '<b>Add to Home Screen</b>, then confirm installation.';
            }} else {{
              instructions.innerHTML='<strong>Install EXOS</strong>'
                + 'Use your browser menu and choose <b>Install EXOS</b> or '
                + '<b>Add to Home Screen</b>.';
            }}
            instructions.style.display='block';
          }}

          document.getElementById('install').addEventListener('click', async () => {{
            installEvent=host.__exosInstallPrompt || installEvent;
            if (installEvent) {{
              installEvent.prompt();
              await installEvent.userChoice;
              host.__exosInstallPrompt=null;
              installEvent=null;
            }} else {{
              showInstructions();
            }}
          }});
          document.getElementById('continue').addEventListener('click', () => {{
            document.getElementById('card').style.display='none';
          }});
        </script>
        """,
        height=220,
    )


def experience_header(
    title: str,
    *,
    welcome: bool = False,
    subtitle: str = "Today's Experience",
    signature: bool = False,
) -> None:
    heading = "Welcome to EXOS" if welcome else "EXOS"
    subtitle_html = (
        f"""<div style="margin-top:1.35rem;color:inherit;opacity:.68;font-size:.86rem;
                      letter-spacing:.14em;text-transform:uppercase;">{html.escape(subtitle)}</div>"""
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div class="exos-hero">
          <div class="exos-kicker">{html.escape(heading)}</div>
          {subtitle_html}
          <div class="exos-experience">{html.escape(title)}</div>
          {"<div class='exos-powered'>by eEssence</div>" if signature else ""}
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
