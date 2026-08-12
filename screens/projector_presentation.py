"""Shared projector styling for full display and scaled Facilitator preview."""


PROJECTOR_STYLES = """
<style>
    .broadcast-screen {
        box-sizing:border-box;
        min-height:100vh;
        width:100%;
        padding:clamp(28px,4vw,72px);
        color:#fff;
        background-color:#082b50;
        background-position:center;
        background-size:cover;
        display:flex;
        flex-direction:column;
        justify-content:center;
        text-shadow:0 3px 12px rgba(0,0,0,.8);
    }
    .broadcast-screen[style*="background-image"] { position:relative; }
    .broadcast-brand, .broadcast-product { font-size:clamp(28px,3vw,50px); font-weight:800; }
    .broadcast-title { font-size:clamp(64px,8vw,136px); font-weight:950; line-height:1.04; }
    .broadcast-subtitle, .broadcast-tagline, .broadcast-kicker {
        color:#fff; font-size:clamp(28px,2.7vw,46px); font-weight:760; line-height:1.35;
    }
    .broadcast-kicker { color:#ffe87a; letter-spacing:.12em; text-transform:uppercase; }
    .broadcast-message { font-size:clamp(38px,3.5vw,62px); font-weight:650; line-height:1.45; }
    .broadcast-centred { align-items:center; text-align:center; }
    .broadcast-rankings { justify-content:flex-start; }
    .broadcast-ranking {
        width:min(1200px,100%); margin:clamp(10px,1.4vh,20px) auto 0;
        padding:clamp(18px,2vh,28px) clamp(24px,3vw,44px);
        border:2px solid rgba(255,255,255,.55); border-radius:20px;
        background:rgba(0,20,45,.78); display:flex; justify-content:space-between;
        gap:36px; font-size:clamp(30px,3vw,48px); font-weight:800;
    }
    .broadcast-countdown { font-size:clamp(180px,26vw,430px); font-weight:950; }
    .broadcast-logo { max-width:min(34vw,480px); max-height:20vh; object-fit:contain; margin-top:30px; }
    .broadcast-experience { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr); gap:5vw; align-items:center; }
    .broadcast-experience-image { width:100%; max-height:76vh; object-fit:contain; border-radius:24px; }
    .broadcast-custom-image { width:100%; height:calc(100vh - 40px); object-fit:contain; }
    .broadcast-blank { position:fixed; inset:0; z-index:999999; background:#000; }
    .broadcast-preview {
        min-height:420px; height:420px; max-height:420px; padding:26px;
        border:2px solid rgba(255,255,255,.45); border-radius:18px; overflow:hidden;
    }
    .broadcast-preview .broadcast-title { font-size:clamp(34px,4.2vw,64px); margin-top:10px; }
    .broadcast-preview .broadcast-message { font-size:clamp(20px,2vw,30px); margin-top:14px; }
    .broadcast-preview .broadcast-brand,
    .broadcast-preview .broadcast-product,
    .broadcast-preview .broadcast-subtitle,
    .broadcast-preview .broadcast-tagline,
    .broadcast-preview .broadcast-kicker { font-size:clamp(16px,1.7vw,25px); }
    .broadcast-preview .broadcast-ranking { font-size:clamp(16px,1.7vw,25px); padding:10px 16px; margin-top:8px; }
    .broadcast-preview .broadcast-countdown { font-size:clamp(90px,14vw,190px); }
    .broadcast-preview .broadcast-logo { max-height:90px; }
    .broadcast-preview .broadcast-experience-image { max-height:320px; }
    .projector-staging-watermark {
        position:fixed; right:14px; bottom:10px; z-index:999998;
        color:rgba(255,255,255,.48); font-size:12px; letter-spacing:.12em;
    }
    @media (max-width:900px) {
        .broadcast-experience { grid-template-columns:1fr; }
        .broadcast-experience-image { max-height:34vh; }
    }
</style>
"""


PROJECTOR_STANDALONE_STYLES = """
<style>
    .stApp { background:#082b50 !important; color:#fff !important; }
    header, footer { visibility:hidden !important; }
    .block-container { padding:0 !important; max-width:none !important; }
    [data-testid="stSidebar"], [data-testid="collapsedControl"],
    [data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="stDecoration"], #MainMenu { display:none !important; }
    .stAppViewContainer, [data-testid="stAppViewBlockContainer"] {
        margin:0 !important; padding:0 !important; max-width:none !important;
    }
</style>
"""
