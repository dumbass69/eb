# - Removed the six-screenshot cap; long passages now capture to the actual bottom with overlap and stall recovery.
# - Raised vision-image budgets so captured passage pages are not discarded before AI analysis.
# - Video fallback and corrected compact sidebar integrated.
# CHANGELOG - 2026-11-21
# - Added exercise-level theme verification and persistent verified-theme locks to stop completed-theme click loops.
# - Added guaranteed window-close cleanup: unload selected Ollama model, stop app-owned server, terminate worker, and register process-exit fallbacks.
# - Fixed score-screen X handling: score pages are now always considered open, and the large top-right X can be clicked by DOM, coordinates, or Escape.
# - State is reset only after verified navigation away from the score screen.
# - Fixed Memory Manager displaying literal \n text and reduced duplicate release entries.
# - Fixed false overlay-close failure logs by verifying the lesson across every frame and by not retrying hidden stale X elements.
# - Fixed AMD VRAM detection: Windows AdapterRAM is 32-bit and falsely reports 4 GB on modern 16 GB cards.
# - Added 64-bit driver-registry VRAM detection with DirectX fallback.
# - Added animated collapsible sidebar, friendly settings/memory views, adaptive-context toggle, verified overlay closing, and multi-method Windows GPU detection.
# - Rebuilt feature navigation as a persistent left sidebar.
# - Fixed hierarchy completion: child/module/skill records no longer complete their parent topic.
# - Added strict level-aware completion keys and legacy-memory migration; top-level completion uses explicit THEME :: title markers.
# - Fixed unavailable-transcript deathloops with persistent skill quarantine and same-session reopen blocking.
# - Added dashboard, decision inspector, memory/lock calendar, diagnostic bundles, hardware detection, adaptive context, image selection, pre-submit validation, and repeated-action circuit breaking.
# - Redesigned the desktop UI as a compact "Midnight Glass" control center.
# - Added GPU Memory Mode: Eco, Balanced, and Performance.
# - Eco mode uses a 4096-token context and unloads the model after each response.
# - Balanced mode uses an 8192-token context with a short 2-minute cache.
# - Performance mode keeps the prior 16384-token context and a 10-minute cache.
# - Added an explicit Release VRAM control and automatic release after sessions.
# - Fixed Ollama HTTP 400 failures with adaptive context/image retries and error-body logging.
# - Added 32K and 64K Overkill context modes.
# - Added release-date lock memory so unavailable exercises are skipped until their date.
# - Fixed locked-skill detection: prior code searched for "blocked", omitted the locked field, and still attached click targets.
# - Added a page-level future-release gate before any skill-card click plus a defensive click circuit breaker.
# - Fixed multi-word phrase truncation and added post-type value verification/retry.
# - AI model selector uses gemma4:e4b as the preferred/default model.
# - Removed the lesson-run cap and all max-lessons UI/runtime handling.
# - Ollama processes started by this app are terminated during application shutdown.
# - Fixed false completion from partial progress percentages; only 100% is complete.
# - Transcript failures are no longer saved as completed lessons.
# - Added safe ZIP path checks and atomic memory-file writes.
# - Completion records prefer scoped theme/module/skill keys.

import base64
import datetime
import json
import math
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from tkinter import messagebox
import urllib.request
import urllib.error
import zipfile
import platform
import atexit
import signal
import tempfile
import traceback
import uuid
from collections import defaultdict, deque
from pathlib import Path

try:
    import customtkinter as ctk
except ImportError as exc:
    raise SystemExit(
        "customtkinter is not installed. Run: pip install customtkinter"
    ) from exc

# Prefer Patchright (patches Playwright's Runtime.enable CDP leak) with automatic fallback to Playwright
try:
    from patchright.sync_api import sync_playwright
    USING_PATCHRIGHT = True
except ImportError:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sync_playwright = None
    USING_PATCHRIGHT = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

# === CONFIGURATION ===
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
CDP_URL = f"http://{CDP_HOST}:{CDP_PORT}"
OLLAMA_URL = "http://127.0.0.1:11434"
OWNED_OLLAMA_PROCESS = None

PREFERRED_MODEL = "gemma4:e4b"
PREFERRED_MODEL_LABEL = "gemma4:e4b (preferred)"
CUSTOM_MODEL_OPTION = "Custom model tag..."

PRESET_MODELS = (
    "gemma4:e4b",
    "gemma4:12b",
    "gemma4:26b",
    "gemma3:12b",
    "gemma3:27b",
    "qwen3-vl:8b",
    "qwen2.5vl:7b",
)


VRAM_PROFILES = {
    "Eco · lowest VRAM": {"num_ctx": 4096, "keep_alive": "0s", "num_batch": 64, "max_images": 12},
    "Balanced · recommended": {"num_ctx": 8192, "keep_alive": "2m", "num_batch": 128, "max_images": 24},
    "Performance · 16K": {"num_ctx": 16384, "keep_alive": "10m", "num_batch": 256, "max_images": 32},
    "Overkill · 32K": {"num_ctx": 32768, "keep_alive": "10m", "num_batch": 256, "max_images": 48},
    "Overkill · 64K": {"num_ctx": 65536, "keep_alive": "10m", "num_batch": 256, "max_images": 64},
}
DEFAULT_VRAM_PROFILE = "Balanced · recommended"

OLLAMA_GITHUB_API = "https://api.github.com/repos/ollama/ollama/releases/latest"
OLLAMA_GITHUB_DIRECT_ZIP = "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = BASE_DIR

MEMORY_FILE = BASE_DIR / "ui_memory.json"
ISOLATED_PROFILE_DIR = BASE_DIR / "chrome-profile"
LOCAL_OLLAMA_DIR = BASE_DIR / "ollama"
LOCAL_OLLAMA_MODELS = BASE_DIR / "ollama_models"
WISEMAN_START_URL = "https://wiseman.com.hk/en/"

# Workload & human-pacing guardrails
DEFAULT_INCORRECT_RATE = 15      # Default % chance to intentionally miss a question (~85% score)
SIMULATE_HUMAN_TIMING = True     # Brisk, natural biometric kinematics & reading delays
BRING_TO_FRONT_ON_ACTION = True  # Restores genuine OS focus (document.hasFocus() === true) before input

SKILL_ORDER = ("Listening", "Reading", "Writing", "Speaking")

DEFAULT_RULES = [
    "On the Wiseman homepage (wiseman.com.hk/en/), click 'Login' (or 'Student Login' / 'English Builder') in the header/menu to enter the learning portal.",
    "Once inside the Wiseman portal, open 'English Builder' if not already inside it, then click 'Lesson Library' in the left sidebar to open the Themes grid.",
    "Ignore contact/footer boxes like 'Service Hours' or 'Need help? Talk to us.' — they are not themes or modules.",
    "NEVER click anything inside 'Extended Section' (including 'Extended Listening', 'Extended Reading', 'Extended Speaking', 'Extended Writing', or its 'Start Lesson' button).",
    "Pick uncompleted Themes/Modules from bottom to top (largest pos.y first), skipping ANY card whose state contains 'completed' or whose title is in ALREADY COMPLETED ITEMS.",
    "Inside a module, complete only the 4 main skill cards (Listening, Reading, Writing, Speaking) — skip any card marked 'Completed' and NEVER click 'Extended Section'. Only click 'Back to Modules' after all 4 main skills are completed.",
    "When 'LEVEL OF DIFFICULTY' is open, NEVER click 'Close Popup (X)'. First click 'Challenging' (never 'Easy'), then click 'Start Lessons'.",
    "Multiple-choice options (<label> or radio buttons) MUST use action 'click' (only use 'select' on actual <select> dropdowns).",
    "When a sentence has multiple text boxes ([BLANK #1], [BLANK #2], etc.), put ONLY ONE WORD per box — split multi-word answers across consecutive boxes in order before clicking 'Submit'.",
    "NEVER click 'Submit' until all required answers/blanks for the current question are filled. After 'Submit' becomes disabled, NEVER click answer options again — click 'Next Question'.",
    "On 'Student Voice' at the end of a lesson: pick an option + click 'Submit', then click 'Results'. On the 'Your Score:' screen, finish the lesson so 'X' closes back to the submenus.",
]

YT_ID_RE = re.compile(
    r"(?:(?:youtube(?:-nocookie)?\.com/(?:(?:watch|embed|shorts|v|live)/|(?:watch\?[^\"'\s<>#]*&)?v=))|youtu\.be/)([A-Za-z0-9_-]{11})"
)
YT_RAW_ID_RE = re.compile(r'["\'](?:video_id|videoId)["\']\s*:\s*["\']([A-Za-z0-9_-]{11})["\']')
TEXT_REF_RE = re.compile(r"\bText\s+(\d+)\b", re.IGNORECASE)
LESSONS_SUFFIX_RE = re.compile(r"\b\d+\s+lessons?\b", re.IGNORECASE)
EXTENDED_SECTION_RE = re.compile(
    r"\bextended\s+(section|listening|reading|speaking|writing)\b", re.IGNORECASE
)

COMMON_DIGRAPHS = frozenset({
    "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
    "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
    "st", "to", "nt", "ng", "se", "ha", "ou", "io", "le", "ve",
    "co", "me", "de", "hi", "ri", "ro", "ic", "ne", "ea", "ra", "ce",
})

_VISION_CACHE: dict[str, bool] = {}

# === UI THEMES (DARK + WHITE & GREEN LIGHT MODE) ===
THEMES = {
    "dark": {
        "bg_root": "#070B14",
        "bg_card": "#101827",
        "bg_inset": "#0A1120",
        "bg_term": "#050913",
        "border": "#24324A",
        "text_primary": "#f8fafc",
        "text_card": "#f1f5f9",
        "text_secondary": "#94a3b8",
        "text_muted": "#cbd5e1",
        "text_log": "#e2e8f0",
        "accent": "#8B5CF6",
        "accent_hover": "#7C3AED",
        "accent_pill_bg": "#241A43",
        "accent_pill_fg": "#C4B5FD",
        "btn_primary_bg": "#7C3AED",
        "btn_primary_hover": "#8B5CF6",
        "btn_primary_fg": "#ffffff",
        "btn_secondary_bg": "#1e293b",
        "btn_secondary_hover": "#334155",
        "btn_secondary_fg": "#e2e8f0",
        "btn_secondary_border": "#334155",
        "start_bg": "#7C3AED",
        "start_hover": "#8B5CF6",
        "stop_bg": "#dc2626",
        "stop_hover": "#ef4444",
        "ok_pill_bg": "#0d281e",
        "ok_pill_fg": "#34d399",
        "warn_pill_bg": "#292111",
        "warn_pill_fg": "#fbbf24",
        "err_pill_bg": "#2c1218",
        "err_pill_fg": "#f87171",
        "idle_pill_bg": "#1e293b",
        "idle_pill_fg": "#94a3b8",
        "switch_progress": "#8B5CF6",
        "switch_btn": "#f8fafc",
        "entry_bg": "#111827",
        "entry_border": "#334155",
        "dropdown_bg": "#111827",
        "dropdown_hover": "#1e293b",
    },
    "light": {
        "bg_root": "#F5F3FF",
        "bg_card": "#FFFFFF",
        "bg_inset": "#F8F7FF",
        "bg_term": "#ffffff",
        "border": "#DDD6FE",
        "text_primary": "#0f172a",
        "text_card": "#2E1065",
        "text_secondary": "#475569",
        "text_muted": "#1e293b",
        "text_log": "#0f172a",
        "accent": "#7C3AED",
        "accent_hover": "#6D28D9",
        "accent_pill_bg": "#EDE9FE",
        "accent_pill_fg": "#6D28D9",
        "btn_primary_bg": "#7C3AED",
        "btn_primary_hover": "#6D28D9",
        "btn_primary_fg": "#ffffff",
        "btn_secondary_bg": "#F5F3FF",
        "btn_secondary_hover": "#EDE9FE",
        "btn_secondary_fg": "#4C1D95",
        "btn_secondary_border": "#C4B5FD",
        "start_bg": "#7C3AED",
        "start_hover": "#6D28D9",
        "stop_bg": "#dc2626",
        "stop_hover": "#b91c1c",
        "ok_pill_bg": "#dcfce7",
        "ok_pill_fg": "#15803d",
        "warn_pill_bg": "#fef3c7",
        "warn_pill_fg": "#b45309",
        "err_pill_bg": "#fee2e2",
        "err_pill_fg": "#b91c1c",
        "idle_pill_bg": "#e2e8f0",
        "idle_pill_fg": "#475569",
        "switch_progress": "#7C3AED",
        "switch_btn": "#ffffff",
        "entry_bg": "#ffffff",
        "entry_border": "#C4B5FD",
        "dropdown_bg": "#ffffff",
        "dropdown_hover": "#EDE9FE",
    },
}


def model_to_display_label(model_name: str) -> str:
    clean = (model_name or PREFERRED_MODEL).strip()
    if clean == PREFERRED_MODEL:
        return PREFERRED_MODEL_LABEL
    return clean


def display_label_to_model(label: str) -> str:
    clean = (label or PREFERRED_MODEL).strip()
    if clean.endswith(" (preferred)"):
        return clean[: -len(" (preferred)")].strip()
    return clean


# === OBSERVABILITY, HARDWARE, DIAGNOSTICS & SAFETY ===
DIAGNOSTICS_DIR = BASE_DIR / "diagnostics"
ADAPTIVE_CONTEXT_DEFAULT = True
ADAPTIVE_CONTEXT_ENABLED = True

class RuntimeTelemetry:
    def __init__(self):
        self.reset()
    def reset(self):
        self.started_at = time.time()
        self.questions = 0
        self.correct = 0
        self.incorrect = 0
        self.ai_retries = 0
        self.blocked_actions = 0
        self.images_sent = 0
        self.last_context = 0
        self.ai_latencies = deque(maxlen=40)
        self.last_decision = {}
        self.last_validation = {}
        self.last_state = {}
        self.action_failures = defaultdict(deque)
    def snapshot(self):
        avg = sum(self.ai_latencies) / len(self.ai_latencies) if self.ai_latencies else 0.0
        return {
            "questions": self.questions, "correct": self.correct, "incorrect": self.incorrect,
            "ai_retries": self.ai_retries, "blocked_actions": self.blocked_actions,
            "images_sent": self.images_sent, "context": self.last_context,
            "avg_latency": round(avg, 1), "uptime_sec": int(time.time()-self.started_at),
        }

TELEMETRY = RuntimeTelemetry()

def _powershell_json(script: str, timeout: int = 8):
    raw = subprocess.check_output(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        text=True, timeout=timeout, errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).strip()
    return json.loads(raw) if raw else None


def _detect_registry_vram(gpu_name: str = "") -> tuple[float, str]:
    script = r"""
$items = Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Video' -Recurse -ErrorAction SilentlyContinue |
  Where-Object { $_.PSChildName -eq '0000' } | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    $raw = $p.'HardwareInformation.qwMemorySize'
    if ($null -ne $raw) {
      if ($raw -is [byte[]]) {
        if ($raw.Length -ge 8) { $bytes=[BitConverter]::ToUInt64($raw,0) }
        elseif ($raw.Length -ge 4) { $bytes=[BitConverter]::ToUInt32($raw,0) }
        else { $bytes=0 }
      } else { $bytes=[uint64]$raw }
      [pscustomobject]@{Name=[string]$p.DriverDesc;Bytes=[uint64]$bytes}
    }
  }
$items | Sort-Object Bytes -Descending | ConvertTo-Json -Compress
"""
    try:
        data=_powershell_json(script)
        rows=data if isinstance(data,list) else ([data] if data else [])
        wanted=(gpu_name or "").lower()
        rows.sort(key=lambda r:int(r.get("Bytes") or 0),reverse=True)
        matches=[r for r in rows if wanted and str(r.get("Name") or "").lower() in wanted]
        row=(matches or rows)[0] if (matches or rows) else None
        value=int((row or {}).get("Bytes") or 0)
        if value >= 1024**3: return round(value/1024**3,1),str((row or {}).get("Name") or "Windows graphics driver")
    except Exception: pass
    return 0.0,""


def _detect_dxdiag_vram(gpu_name: str = "") -> tuple[float, str]:
    tmp=Path(tempfile.gettempdir())/f"wiseman_dxdiag_{os.getpid()}.xml"
    try:
        subprocess.run(["dxdiag","/whql:off","/x",str(tmp)],timeout=18,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        raw=tmp.read_bytes()
        text=raw.decode("utf-16",errors="ignore") if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode("utf-8",errors="ignore")
        choices=[]
        for block in re.findall(r"<DisplayDevice>(.*?)</DisplayDevice>",text,re.S|re.I):
            nm=re.search(r"<CardName>(.*?)</CardName>",block,re.S|re.I)
            mm=re.search(r"<DedicatedMemory>([0-9,]+)\s*MB",block,re.I)
            if mm: choices.append((float(mm.group(1).replace(',',''))/1024,(nm.group(1).strip() if nm else "DirectX adapter")))
        wanted=(gpu_name or "").lower(); matches=[x for x in choices if wanted and x[1].lower() in wanted]
        if matches or choices:
            gb,name=max(matches or choices,key=lambda x:x[0]); return round(gb,1),name
    except Exception: pass
    finally:
        try: tmp.unlink(missing_ok=True)
        except Exception: pass
    return 0.0,""


def detect_hardware_capabilities() -> dict:
    info={"os":platform.platform(),"cpu":platform.processor() or "Unknown processor","ram_gb":0.0,"gpu":"Graphics hardware not identified","gpu_vendor":"Unknown","vram_total_gb":0.0,"vram_free_gb":0.0,"recommended_ctx":4096,"source":"Windows system information","warning":""}
    try:
        import psutil; info["ram_gb"]=round(psutil.virtual_memory().total/1024**3,1)
    except Exception: pass
    for exe in ("nvidia-smi",r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        try:
            out=subprocess.check_output([exe,"--query-gpu=name,memory.total,memory.free","--format=csv,noheader,nounits"],text=True,timeout=6,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)).splitlines()[0]
            name,total,free=[x.strip() for x in out.split(',')[:3]]; info.update(gpu=name,gpu_vendor="NVIDIA",vram_total_gb=round(float(total)/1024,1),vram_free_gb=round(float(free)/1024,1),source="NVIDIA driver"); break
        except Exception: pass
    if info["gpu"]=="Graphics hardware not identified":
        try:
            data=_powershell_json("Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress")
            rows=data if isinstance(data,list) else [data]; rows=[r for r in rows if r]
            rows.sort(key=lambda r:(2 if any(x in str(r.get('Name','')).lower() for x in ('radeon','nvidia')) else 1),reverse=True)
            item=rows[0]; name=str(item.get("Name") or "Windows display adapter"); vendor="AMD" if any(x in name.lower() for x in ('amd','radeon')) else "Intel" if 'intel' in name.lower() else "Unknown"; info.update(gpu=name,gpu_vendor=vendor)
            legacy=round(float(item.get("AdapterRAM") or 0)/1024**3,1)
            if 0 < legacy < 3.9: info["vram_total_gb"]=legacy
        except Exception: pass
    if info["vram_total_gb"]<=0:
        gb,name=_detect_registry_vram(info["gpu"])
        if gb: info.update(vram_total_gb=gb,source="AMD/Windows 64-bit driver memory value")
    if info["vram_total_gb"]<=0:
        gb,name=_detect_dxdiag_vram(info["gpu"])
        if gb: info.update(vram_total_gb=gb,source="DirectX diagnostics")
    v=info["vram_total_gb"]; info["recommended_ctx"]=32768 if v>=16 else 16384 if v>=12 else 8192 if v>=8 else 4096
    if not v: info["warning"]="The graphics card was found, but Windows did not provide its dedicated-memory amount."
    elif info["gpu_vendor"]=="AMD" and not info["vram_free_gb"]: info["warning"]="Total AMD graphics memory detected. Windows does not reliably expose live free VRAM for AMD, so no false zero-free value is shown."
    return info

def hardware_summary(info: dict) -> str:
    vram=(f"{info['vram_free_gb']:.1f} GB free of {info['vram_total_gb']:.1f} GB" if info.get('vram_free_gb') else f"about {info['vram_total_gb']:.1f} GB" if info.get('vram_total_gb') else "amount unavailable")
    return (f"Graphics: {info.get('gpu','Unknown')}\n"
            f"Graphics memory: {vram}\n"
            f"Computer memory: {info.get('ram_gb',0):.1f} GB\n"
            f"Recommended AI context limit: {info.get('recommended_ctx',4096)//1024}K\n"
            f"Detected using: {info.get('source','system information')}\n"
            f"{info.get('warning','')}").strip()

def choose_adaptive_context(prompt: str, images: list[str], requested: int, hardware: dict | None = None) -> int:
    """Choose the smallest useful context. The selected profile remains a hard ceiling."""
    hw = hardware or detect_hardware_capabilities()
    approx_tokens = max(1024, len(prompt) // 4 + len(images) * 900)
    need = 4096 if approx_tokens <= 3000 else 8192 if approx_tokens <= 6500 else 16384 if approx_tokens <= 13000 else 32768 if approx_tokens <= 26000 else 65536
    return max(4096, min(requested, need, int(hw.get("recommended_ctx", requested))))

def select_relevant_images(images: list[str], question_text: str, max_images: int) -> list[str]:
    """Use question references to avoid sending every passage slice."""
    if len(images) <= max_images:
        return images
    text_no = TEXT_REF_RE.search(question_text or "")
    if text_no:
        # Text tabs are normally contiguous; retain broad first/middle/last coverage.
        idxs = sorted(set([0, len(images)//2, len(images)-1]))[:max_images]
    else:
        # Preserve top and bottom context, then evenly spaced middle slices.
        idxs = [round(i*(len(images)-1)/(max_images-1)) for i in range(max_images)] if max_images > 1 else [0]
    selected = [images[i] for i in dict.fromkeys(idxs)]
    print(f"[Vision] Selected {len(selected)}/{len(images)} relevant passage image(s).")
    return selected

def _action_signature(state: dict, meta: dict, kind: str, value="") -> str:
    page = state.get("url", "").split("?")[0]
    step = state.get("lesson_progress", {}).get("current_step", "Unknown")
    return f"{page}|{step}|{kind}|{meta.get('text','')[:80]}|{value}"

def circuit_breaker_allows(signature: str, window_sec: int = 45, limit: int = 2) -> bool:
    now = time.time()
    q = TELEMETRY.action_failures[signature]
    while q and now-q[0] > window_sec:
        q.popleft()
    if len(q) >= limit:
        TELEMETRY.blocked_actions += 1
        print(f"[Circuit Breaker] Blocked repeated unchanged action after {len(q)} attempts.")
        return False
    q.append(now)
    return True

def circuit_breaker_clear(signature: str) -> None:
    TELEMETRY.action_failures.pop(signature, None)

def validate_pre_submit(page, state: dict, frame_map: dict, planned_actions: list[dict], intentional_miss: bool = False) -> tuple[bool, dict]:
    """Validate completeness and DOM retention, not correctness. Intentional misses remain permitted."""
    lookup = {e["id"]: e for e in state.get("elements", [])}
    planned = {a.get("id"): a for a in planned_actions if a.get("action") in ("fill", "select")}
    required = [e for e in state.get("elements", []) if (e.get("tag") == "select" or _is_text_input_tag(e.get("tag", ""))) and "disabled" not in e.get("state", "")]
    errors, values = [], {}
    for el in required:
        cid = el["id"]
        expected = str((planned.get(cid) or {}).get("value", "")).strip()
        frame = frame_map.get(cid)
        actual = ""
        if frame:
            try:
                loc = frame.locator(f'[data-ai-id="{cid}"]').first
                actual = loc.input_value(timeout=1500) if el.get("tag") != "select" else loc.locator("option:checked").inner_text(timeout=1500)
            except Exception:
                actual = ""
        actual = re.sub(r"\s+", " ", str(actual)).strip()
        values[str(cid)] = {"expected": expected, "actual": actual}
        if not actual or actual.lower().startswith(("--", "select")):
            errors.append(f"[{cid}] is empty")
        elif expected and actual != expected:
            errors.append(f"[{cid}] expected {expected!r}, retained {actual!r}")
    option_controls = [e for e in state.get("elements", []) if e.get("is_answer_option")]
    planned_option_click = any(a.get("action") == "click" and lookup.get(a.get("id"), {}).get("is_answer_option") for a in planned_actions)
    if option_controls and not (state.get("has_checked_option") or planned_option_click):
        errors.append("No answer option is selected")
    result = {"ok": not errors, "intentional_miss": intentional_miss, "errors": errors, "values": values,
              "note": "Validator checks completeness and execution fidelity only; deliberate wrong answers are allowed."}
    TELEMETRY.last_validation = result
    if errors:
        TELEMETRY.blocked_actions += 1
        print("[Pre-submit Validator] BLOCKED: " + "; ".join(errors))
    else:
        suffix = " (intentional miss preserved)" if intentional_miss else ""
        print(f"[Pre-submit Validator] PASS{suffix}: all required controls retained their planned values.")
    return not errors, result

def create_diagnostic_bundle(reason: str, state: dict | None = None, decision: dict | None = None,
                             exc: Exception | None = None, page=None) -> Path:
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path(tempfile.mkdtemp(prefix="wiseman_diag_"))
    try:
        safe_state = dict(state or {})
        safe_state.pop("cookies", None)
        (root/"summary.json").write_text(json.dumps({"created": datetime.datetime.now().isoformat(), "reason": reason,
            "telemetry": TELEMETRY.snapshot(), "hardware": detect_hardware_capabilities()}, indent=2), encoding="utf-8")
        (root/"observation.json").write_text(json.dumps(safe_state, indent=2, ensure_ascii=False), encoding="utf-8")
        (root/"decision.json").write_text(json.dumps(decision or TELEMETRY.last_decision, indent=2, ensure_ascii=False), encoding="utf-8")
        (root/"memory-summary.json").write_text(json.dumps(load_memory(), indent=2, ensure_ascii=False), encoding="utf-8")
        if exc:
            (root/"error.txt").write_text("".join(traceback.format_exception(exc)), encoding="utf-8")
        if page:
            try: page.screenshot(path=str(root/"current-screen.png"), full_page=False)
            except Exception: pass
        out = DIAGNOSTICS_DIR / f"wiseman-diagnostic-{stamp}.zip"
        shutil.make_archive(str(out.with_suffix("")), "zip", root)
        print(f"[Diagnostics] Exported sanitized bundle: {out}")
        return out
    finally:
        shutil.rmtree(root, ignore_errors=True)

# === THREAD-SAFE LOGGING & INTERRUPTIBLE SLEEP ===
class LogRouter:
    """Routes print() calls safely into both the GUI log queue and the real terminal."""

    def __init__(self, msg_queue: queue.Queue, mirror_stream=None):
        self.msg_queue = msg_queue
        self.mirror_stream = mirror_stream
        self._buf = ""

    def write(self, text: str) -> None:
        if not text:
            return
        if self.mirror_stream is not None:
            try:
                self.mirror_stream.write(text)
                self.mirror_stream.flush()
            except Exception:
                pass
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self.msg_queue.put(("log", line))

    def flush(self) -> None:
        if self.mirror_stream is not None:
            try:
                self.mirror_stream.flush()
            except Exception:
                pass
        if self._buf.strip():
            self.msg_queue.put(("log", self._buf.strip()))
            self._buf = ""


def interruptible_sleep(seconds: float, stop_event: threading.Event | None = None) -> None:
    if seconds <= 0:
        return
    if stop_event is None:
        time.sleep(seconds)
        return
    end_t = time.time() + seconds
    while not stop_event.is_set():
        rem = end_t - time.time()
        if rem <= 0:
            break
        time.sleep(min(0.2, rem))


# === ISOLATED CHROME & GITHUB PORTABLE OLLAMA HELPERS ===
def find_chrome_executable() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def find_ollama_executable() -> tuple[str | None, bool]:
    """Returns (executable_path, is_portable_folder)."""
    portable_candidates = [
        LOCAL_OLLAMA_DIR / "ollama.exe",
        BUNDLE_DIR / "ollama" / "ollama.exe",
    ]
    for path in portable_candidates:
        if path.exists():
            return str(path), True

    system_candidate = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"))
    if system_candidate.exists():
        return str(system_candidate), False

    which_path = shutil.which("ollama")
    if which_path:
        return which_path, False

    return None, False


def _resolve_latest_ollama_github_zip() -> tuple[str, str]:
    """Returns (version_tag, download_url) for ollama-windows-amd64.zip."""
    try:
        req = urllib.request.Request(
            OLLAMA_GITHUB_API,
            headers={
                "User-Agent": "WisemanAgent-Updater/1.0",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read().decode("utf-8"))
        tag = release.get("tag_name", "latest")
        for asset in release.get("assets", []):
            if asset.get("name") == "ollama-windows-amd64.zip":
                url = asset.get("browser_download_url")
                if url:
                    return tag, url
    except Exception:
        pass
    return "latest", OLLAMA_GITHUB_DIRECT_ZIP


def download_and_install_ollama_from_github(
    on_progress,
    stop_event: threading.Event | None = None,
) -> Path:
    """Downloads ollama-windows-amd64.zip from GitHub and extracts into BASE_DIR / 'ollama'."""
    tag, download_url = _resolve_latest_ollama_github_zip()
    print(f"[GitHub Setup] Fetching Ollama ({tag}) from: {download_url}")

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_zip = BASE_DIR / "ollama-windows-amd64.zip.part"
    if tmp_zip.exists():
        try:
            tmp_zip.unlink()
        except Exception:
            pass

    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": "WisemanAgent-Updater/1.0"},
    )
    start_t = time.time()
    last_emit = 0.0
    downloaded = 0

    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        with open(tmp_zip, "wb") as f_out:
            while True:
                if stop_event and stop_event.is_set():
                    raise RuntimeError("Ollama download cancelled.")
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                f_out.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last_emit >= 0.25 or (total and downloaded >= total):
                    elapsed = max(0.05, now - start_t)
                    speed_mb = (downloaded / (1024 * 1024)) / elapsed
                    on_progress(
                        f"Downloading Ollama ({tag}) from GitHub · {speed_mb:.1f} MB/s",
                        downloaded,
                        total,
                    )
                    last_emit = now

    print("[GitHub Setup] Download complete. Extracting Ollama files...")
    on_progress("Extracting Ollama runtime...", downloaded, downloaded)

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "ollama.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        time.sleep(0.5)
    except Exception:
        pass

    LOCAL_OLLAMA_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(tmp_zip, "r") as zf:
        members = zf.infolist()
        total_files = max(1, len(members))
        for idx, member in enumerate(members, 1):
            if stop_event and stop_event.is_set():
                raise RuntimeError("Ollama extraction cancelled.")
            destination = (LOCAL_OLLAMA_DIR / member.filename).resolve()
            root = LOCAL_OLLAMA_DIR.resolve()
            if destination != root and root not in destination.parents:
                raise RuntimeError(f"Unsafe path in Ollama archive: {member.filename}")
            zf.extract(member, LOCAL_OLLAMA_DIR)
            if idx % 15 == 0 or idx == total_files:
                on_progress(
                    f"Extracting Ollama ({idx}/{total_files} files)...",
                    idx,
                    total_files,
                )

    try:
        tmp_zip.unlink()
    except Exception:
        pass

    exe_path = LOCAL_OLLAMA_DIR / "ollama.exe"
    if not exe_path.exists():
        raise RuntimeError("Extraction finished, but ollama.exe was not found in the archive.")

    print(f"[GitHub Setup] Ollama installed at: {exe_path}")
    return exe_path


def ensure_isolated_chrome(stop_event: threading.Event | None = None) -> None:
    """Connects to an existing debug Chrome on 127.0.0.1:9222, or launches an isolated profile."""
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1.5):
            return
    except Exception:
        pass

    chrome_exe = find_chrome_executable()
    if not chrome_exe:
        raise RuntimeError(
            "Google Chrome was not found on this PC. Please install Google Chrome first."
        )

    ISOLATED_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Launching isolated Chrome profile at: {ISOLATED_PROFILE_DIR}")
    subprocess.Popen(
        [
            chrome_exe,
            f"--remote-debugging-port={CDP_PORT}",
            f"--remote-debugging-address={CDP_HOST}",
            f"--user-data-dir={ISOLATED_PROFILE_DIR}",
            "--mute-audio",
            "--disable-backgrounding-occluded-windows",
            "--no-first-run",
            "--no-default-browser-check",
            WISEMAN_START_URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(20):
        if stop_event and stop_event.is_set():
            return
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1.5):
                print("Isolated debug Chrome started (audio muted). Log in to Wiseman if prompted.")
                return
        except Exception:
            continue
    raise RuntimeError("Timed out waiting for isolated Chrome to open debugging port 9222.")


def is_ollama_running() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=1.2):
            return True
    except Exception:
        return False


def get_installed_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2.5) as resp:
            return [m["name"] for m in json.loads(resp.read()).get("models", [])]
    except Exception:
        return []


def is_model_installed(installed: list[str], target: str) -> bool:
    clean = (target or "").strip()
    if not clean:
        return False
    return any(
        m == clean
        or m.startswith(clean + "-")
        or (":" not in clean and m == f"{clean}:latest")
        for m in installed
    )


def build_ollama_env(is_portable: bool = True) -> dict[str, str]:
    env = os.environ.copy()
    if is_portable or LOCAL_OLLAMA_MODELS.exists():
        LOCAL_OLLAMA_MODELS.mkdir(parents=True, exist_ok=True)
        env["OLLAMA_MODELS"] = str(LOCAL_OLLAMA_MODELS)
    if LOCAL_OLLAMA_DIR.exists():
        env["PATH"] = f"{LOCAL_OLLAMA_DIR};{env.get('PATH', '')}"
    return env


def ensure_ollama_server(stop_event: threading.Event | None = None) -> None:
    global OWNED_OLLAMA_PROCESS
    """Starts portable or system 'ollama.exe serve' silently if not running."""
    if is_ollama_running():
        return

    ollama_bin, is_portable = find_ollama_executable()
    if not ollama_bin:
        raise RuntimeError("Ollama engine not installed yet.")

    env = build_ollama_env(is_portable)
    print(f"Starting Ollama background engine ({ollama_bin})...")
    OWNED_OLLAMA_PROCESS = subprocess.Popen(
        [ollama_bin, "serve"],
        env=env,
        cwd=str(Path(ollama_bin).parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    for _ in range(24):
        if stop_event and stop_event.is_set():
            return
        time.sleep(0.5)
        if is_ollama_running():
            print("Ollama engine is online.")
            return

    raise RuntimeError("Timed out waiting for Ollama engine to start on 127.0.0.1:11434.")


def stop_owned_ollama_server(timeout: float = 6.0) -> None:
    """Stop only an Ollama server launched by this app, releasing its VRAM."""
    global OWNED_OLLAMA_PROCESS
    proc = OWNED_OLLAMA_PROCESS
    OWNED_OLLAMA_PROCESS = None
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
        print("Ollama background engine stopped; model VRAM released.")
    except Exception as exc:
        print(f"[Shutdown Warning] Could not stop owned Ollama cleanly: {exc}")


def pull_ollama_model_stream(
    model_name: str,
    on_progress,
    stop_event: threading.Event | None = None,
) -> None:
    """Pulls an Ollama model via streaming HTTP API and reports progress callbacks."""
    ensure_ollama_server(stop_event)

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/pull",
        data=json.dumps({"name": model_name, "stream": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw_line in resp:
            if stop_event and stop_event.is_set():
                raise RuntimeError("Download cancelled.")
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            evt = json.loads(line)
            if "error" in evt:
                raise RuntimeError(evt["error"])
            status = evt.get("status", "Downloading...")
            total = int(evt.get("total") or 0)
            completed = int(evt.get("completed") or 0)
            on_progress(status, completed, total)
            if status == "success":
                return


def ensure_foreground_focus(page) -> None:
    if not BRING_TO_FRONT_ON_ACTION:
        return
    try:
        has_focus = page.evaluate("() => document.hasFocus()")
        if not has_focus:
            page.bring_to_front()
            time.sleep(random.uniform(0.10, 0.22))
    except Exception:
        try:
            page.bring_to_front()
            time.sleep(0.15)
        except Exception:
            pass


# === MEMORY, COMPLETED-TITLE NORMALIZATION & LESSON LOGGING ===
def normalize_item_title(text: str) -> str:
    if not text:
        return ""
    s = re.sub(r"\s*->.*$", "", text)
    s = LESSONS_SUFFIX_RE.sub("", s)
    s = re.sub(r"\b(completed|new|passed|submitted|release|expiry)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b\d{1,3}%\b", "", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _split_completion_key(raw: str) -> list[str]:
    return [normalize_item_title(p) for p in str(raw).split("::") if normalize_item_title(p)]


def get_completed_title_set(memory: dict, extra_completed: set[str] | None = None) -> set[str]:
    """Return only exact completion keys. Never flatten descendants into parent titles."""
    done: set[str] = set()
    raw_items = list(memory.get("completed_items", []))
    if extra_completed:
        raw_items.extend(extra_completed)
    for raw in raw_items:
        parts = _split_completion_key(raw)
        if not parts:
            continue
        done.add(" :: ".join(parts))
    return done


def is_title_completed(
    title: str,
    completed_norms: set[str],
    active_theme: str = "",
    active_module: str = "",
    level: str = "auto",
) -> bool:
    """Check completion at the current hierarchy level only.

    theme card: Theme
    module card: Theme :: Module
    skill card: Theme :: Module :: Skill
    lesson: Theme :: Module :: Skill :: Lesson
    """
    title_norm = normalize_item_title(title)
    if len(title_norm) < 4:
        return False
    theme_norm = normalize_item_title(active_theme)
    module_norm = normalize_item_title(active_module)
    if level == "theme" or (level == "auto" and not theme_norm):
        # A parent topic is complete only when that exact top-level key was recorded.
        return f"theme :: {title_norm}" in completed_norms
    if level == "module" or (level == "auto" and theme_norm and not module_norm):
        return f"{theme_norm} :: {title_norm}" in completed_norms
    if level == "skill" or module_norm:
        return f"{theme_norm} :: {module_norm} :: {title_norm}" in completed_norms
    return False


def migrate_legacy_completion_memory(data: dict) -> bool:
    """Remove no records, but flag ambiguous bare parents so they are not trusted blindly."""
    items = [str(x).strip() for x in data.get("completed_items", []) if str(x).strip()]
    scoped_parts = {_split_completion_key(x)[0] for x in items if "::" in x and _split_completion_key(x)}
    ambiguous = sorted({normalize_item_title(x) for x in items if "::" not in x and normalize_item_title(x) in scoped_parts})
    previous = data.get("ambiguous_legacy_parents", [])
    data["ambiguous_legacy_parents"] = ambiguous
    return previous != ambiguous

def load_memory() -> dict:
    if MEMORY_FILE.exists():
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        cleaned = [
            r for r in data.get("learned_ui_rules", [])
            if "ONLY select 'Reading'" not in r
            and "ANY uncompleted skill card" not in r
            and "overlay-close" not in r
            and "Q1-Q12" not in r
        ]
        for r in DEFAULT_RULES:
            if r not in cleaned:
                cleaned.append(r)
        data["learned_ui_rules"] = cleaned
        data.setdefault("completed_items", [])
        data.setdefault("theme_verification", {})
        data.setdefault("learned_answer_corrections", [])
        migrate_legacy_completion_memory(data)
        data.setdefault("lesson_log", [])
        data.setdefault("selected_model", PREFERRED_MODEL)
        data.setdefault("theme_mode", "dark")
        data.setdefault("vram_profile", DEFAULT_VRAM_PROFILE)
        data.setdefault("locked_items", {})
        data.setdefault("quarantined_actions", {})
        data.setdefault("quarantined_items", {})
        data.setdefault("adaptive_context", True)
        profile = data.setdefault(
            "student_profile",
            {
                "typing_wpm_mean": random.randint(52, 72),
                "reading_wpm_mean": random.randint(275, 340),
                "incorrect_rate_pct": DEFAULT_INCORRECT_RATE,
            },
        )
        profile.setdefault("incorrect_rate_pct", DEFAULT_INCORRECT_RATE)
        return data

    return {
        "learned_ui_rules": list(DEFAULT_RULES),
        "completed_items": [],
        "theme_verification": {},
        "learned_answer_corrections": [],
        "ambiguous_legacy_parents": [],
        "lesson_log": [],
        "selected_model": PREFERRED_MODEL,
        "theme_mode": "dark",
        "vram_profile": DEFAULT_VRAM_PROFILE,
        "locked_items": {},
        "quarantined_actions": {},
        "quarantined_items": {},
        "adaptive_context": True,
        "student_profile": {
            "typing_wpm_mean": random.randint(52, 72),
            "reading_wpm_mean": random.randint(275, 340),
            "incorrect_rate_pct": DEFAULT_INCORRECT_RATE,
        },
    }


def save_memory(mem: dict) -> None:
    """Persist memory atomically to avoid a partially written JSON file."""
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MEMORY_FILE.with_suffix(MEMORY_FILE.suffix + ".tmp")
    tmp_path.write_text(json.dumps(mem, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, MEMORY_FILE)


def _parse_release_date(text: str) -> str | None:
    """Return an ISO date for common Wiseman release-date labels."""
    if not text:
        return None
    patterns = [
        r"release\s*date\s*[:\-]?\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})",
        r"release\s*[:\-]?\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})",
        r"available\s+(?:on|from)\s+(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.datetime.strptime(" ".join(m.groups()), fmt).date().isoformat()
            except ValueError:
                pass
    return None


def remember_locked_item(memory: dict, key: str, release_date: str | None, evidence: str = "") -> None:
    clean = (key or "").strip()
    if not clean:
        return
    locks = memory.setdefault("locked_items", {})
    # No known date means retry tomorrow rather than creating a permanent lock.
    unlock = release_date or (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    locks[clean] = {
        "release_date": unlock,
        "detected_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "evidence": evidence[:300],
    }
    save_memory(memory)
    print(f"[Locked] Remembered '{clean}' until {unlock}.")


def is_item_locked(memory: dict, *keys: str) -> tuple[bool, str]:
    today = datetime.date.today()
    locks = memory.setdefault("locked_items", {})
    changed = False
    for key in keys:
        clean = (key or "").strip()
        if not clean or clean not in locks:
            continue
        raw_date = str(locks[clean].get("release_date", ""))
        try:
            release = datetime.date.fromisoformat(raw_date)
        except ValueError:
            del locks[clean]
            changed = True
            continue
        if today < release:
            return True, release.isoformat()
        del locks[clean]
        changed = True
    if changed:
        save_memory(memory)
    return False, ""


def _safe_iso_date(value) -> datetime.date | None:
    try: return datetime.date.fromisoformat(str(value))
    except Exception: return None

def quarantine_learning_item(memory: dict, key: str, reason: str, hours: int = 24, evidence: str = "") -> None:
    clean = re.sub(r"\s*::\s*", "::", str(key).strip())
    if not clean:
        return
    until = datetime.datetime.now() + datetime.timedelta(hours=max(1, hours))
    store = memory.setdefault("quarantined_items", {})
    previous = store.get(clean, {})
    store[clean] = {
        "reason": reason,
        "retry_after": until.isoformat(timespec="seconds"),
        "detected_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "attempts": int(previous.get("attempts", 0)) + 1,
        "evidence": evidence[:500],
    }
    save_memory(memory)
    print(f"[Quarantine] {clean} blocked until {until.isoformat(timespec='minutes')} ({reason}).")


def is_learning_item_quarantined(memory: dict, *keys: str) -> tuple[bool, str, str]:
    now = datetime.datetime.now()
    store = memory.setdefault("quarantined_items", {})
    changed = False
    for key in keys:
        clean = re.sub(r"\s*::\s*", "::", str(key).strip())
        item = store.get(clean)
        if not item:
            continue
        try:
            retry = datetime.datetime.fromisoformat(str(item.get("retry_after", "")))
        except ValueError:
            store.pop(clean, None); changed = True; continue
        if now < retry:
            return True, retry.isoformat(timespec="minutes"), str(item.get("reason", "unavailable"))
        store.pop(clean, None); changed = True
    if changed:
        save_memory(memory)
    return False, "", ""


def clear_legacy_transcript_quarantines(memory: dict) -> int:
    """Remove obsolete broad caption-failure locks created by older builds."""
    store = memory.setdefault("quarantined_items", {})
    doomed = [k for k, v in store.items() if str(v.get("reason", "")) == "transcript_unavailable"]
    for key in doomed: store.pop(key, None)
    if doomed:
        save_memory(memory)
        print(f"[Migration] Cleared {len(doomed)} obsolete transcript quarantine record(s).")
    return len(doomed)


def count_lessons_today(memory: dict) -> int:
    today_str = datetime.date.today().isoformat()
    return sum(
        1 for entry in memory.get("lesson_log", [])
        if str(entry.get("date", "")).startswith(today_str)
    )


def is_theme_verified_complete(memory: dict, theme_name: str) -> bool:
    """Return True only for a theme previously verified from its full module list."""
    theme_norm = normalize_item_title(theme_name)
    if not theme_norm:
        return False
    exact_key = f"theme :: {theme_norm}"
    if exact_key in get_completed_title_set(memory):
        return True
    entry = memory.get("theme_verification", {}).get(theme_norm, {})
    return bool(entry.get("completed") and entry.get("module_count", 0) > 0)


def record_verified_theme(memory: dict, theme_name: str, cards: list[dict], session_completed: set[str] | None = None) -> None:
    """Persist theme completion only after every discovered module is positively complete."""
    theme_clean = (theme_name or "").strip()
    theme_norm = normalize_item_title(theme_clean)
    verified_modules = [str(c.get("title", "")).strip() for c in cards if c.get("done")]
    if not theme_norm or not cards or len(verified_modules) != len(cards):
        raise ValueError("Refusing to complete a theme without a non-empty, fully verified module list.")
    memory.setdefault("theme_verification", {})[theme_norm] = {
        "completed": True,
        "verified_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "module_count": len(cards),
        "modules": verified_modules,
    }
    record_completed(memory, [f"THEME :: {theme_clean}"], session_completed=session_completed)
    # record_completed may not save when the exact key already existed, so save the audit record explicitly.
    save_memory(memory)
    print(f"[Theme Verify] '{theme_clean}' locked complete after verifying all {len(cards)} module(s).")


def record_completed(
    memory: dict,
    labels: list[str],
    lesson_name: str = "",
    duration_sec: float = 0.0,
    session_completed: set[str] | None = None,
) -> None:
    changed = False
    for lbl in labels:
        clean = (lbl or "").strip()
        if not clean:
            continue
        if session_completed is not None:
            session_completed.add(clean)
        if clean not in memory["completed_items"]:
            memory["completed_items"].append(clean)
            changed = True
            print(f"   -> Saved to completed memory: '{clean}'")

    if lesson_name:
        memory.setdefault("lesson_log", []).append({
            "date": datetime.datetime.now().isoformat(timespec="seconds"),
            "lesson": lesson_name,
            "duration_sec": round(duration_sec, 1),
        })
        changed = True

    if changed:
        save_memory(memory)


def annotate_completed_menu_items(
    state: dict,
    memory: dict,
    active_theme: str = "",
    session_completed: set[str] | None = None,
) -> None:
    completed_norms = get_completed_title_set(memory, session_completed)
    if not completed_norms:
        return

    reserved_nav = {
        "home", "lesson library", "my learning", "students' voice", "rewards",
        "return to portal", "back to modules", "login", "english builder",
    }

    for el in state.get("elements", []):
        norm_el = normalize_item_title(el.get("text", ""))
        if len(norm_el) < 4 or norm_el in reserved_nav:
            continue

        page_type = state.get("page_type", "")
        level = "theme" if page_type == "theme_list" else "module" if page_type == "module_list" else "auto"
        if is_title_completed(el.get("text", ""), completed_norms, active_theme, level=level):
            st = el.get("state", "")
            if "completed" not in st:
                el["state"] = f"{st}, completed".strip(", ")


# === HELPERS: MODELS & YOUTUBE TRANSCRIPTS ===
def is_vision_model(model: str) -> bool:
    if model in _VISION_CACHE:
        return _VISION_CACHE[model]

    detected = False
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/show",
            data=json.dumps({"name": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            info = json.loads(resp.read())
        caps = [str(c).lower() for c in info.get("capabilities", [])]
        if "vision" in caps:
            detected = True
        elif any(k in json.dumps(info.get("model_info", {})).lower() for k in ("vision", "mmproj", "siglip", "clip")):
            detected = True
    except Exception:
        pass

    if not detected:
        m = model.lower()
        detected = any(
            k in m
            for k in ("gemma4", "gemma3", "vl", "vision", "llava", "minicpm-v", "pixtral", "mistral-small3")
        )

    _VISION_CACHE[model] = detected
    return detected


def extract_youtube_id(text: str) -> str | None:
    if not text:
        return None
    match = YT_ID_RE.search(text)
    if match:
        return match.group(1)
    raw_match = YT_RAW_ID_RE.search(text)
    if raw_match:
        return raw_match.group(1)
    return None


def fetch_youtube_transcript_with_duration(video_id: str) -> tuple[str, float]:
    if YouTubeTranscriptApi is None:
        raise RuntimeError("youtube-transcript-api is not installed.")

    langs = ["en", "en-US", "en-GB", "en-AU", "en-CA"]
    api = YouTubeTranscriptApi()

    if hasattr(api, "fetch"):
        fetched = None
        try:
            fetched = list(api.fetch(video_id, languages=langs))
        except Exception:
            try:
                t_list = api.list(video_id)
                chosen = None
                for t in t_list:
                    if str(getattr(t, "language_code", "")).startswith("en"):
                        chosen = t
                        break
                if chosen is None:
                    first_t = next(iter(t_list))
                    chosen = first_t.translate("en") if getattr(first_t, "is_translatable", False) else first_t
                fetched = list(chosen.fetch())
            except Exception:
                fetched = list(api.fetch(video_id))

        parts = [getattr(s, "text", str(s)) for s in fetched]
        if fetched:
            last = fetched[-1]
            est_dur = float(getattr(last, "start", 0.0)) + float(getattr(last, "duration", 5.0))
        else:
            est_dur = 120.0
    else:
        try:
            fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        except Exception:
            fetched = YouTubeTranscriptApi.get_transcript(video_id)
        parts = [s["text"] for s in fetched]
        if fetched:
            last = fetched[-1]
            est_dur = float(last.get("start", 0.0)) + float(last.get("duration", 5.0))
        else:
            est_dur = 120.0

    cleaned = " ".join(p.replace("\n", " ").strip() for p in parts if p)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        raise RuntimeError("Transcript returned empty text.")
    return cleaned, max(30.0, est_dur)


def release_ollama_model(model: str) -> None:
    """Ask Ollama to unload a model immediately and release its GPU allocation."""
    if not model or not is_ollama_running():
        return
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps({"model": model, "prompt": "", "keep_alive": 0, "stream": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        print(f"[GPU] Released model memory for {model}.")
    except Exception as exc:
        print(f"[GPU Warning] Could not unload {model}: {exc}")


def _shrink_data_url_image(image_b64: str, max_bytes: int = 900_000) -> str:
    """Downscale large screenshots before sending them to a vision model."""
    try:
        raw = base64.b64decode(image_b64)
        if len(raw) <= max_bytes:
            return image_b64
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(raw)).convert("RGB")
        img.thumbnail((1280, 1280))
        out = BytesIO()
        img.save(out, format="JPEG", quality=68, optimize=True)
        return base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return image_b64


def release_all_ollama_models(timeout: float = 5.0) -> None:
    """Unload every model currently resident in Ollama, including one loaded before the UI opened."""
    if not is_ollama_running():
        return
    names: list[str] = []
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=timeout) as resp:
            data = json.loads(resp.read())
        names = [str(m.get("name") or m.get("model") or "").strip() for m in data.get("models", [])]
    except Exception as exc:
        print(f"[Shutdown] Could not list loaded Ollama models: {exc}")
    for name in dict.fromkeys(x for x in names if x):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/generate",
                data=json.dumps({"model": name, "prompt": "", "stream": False, "keep_alive": 0}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read()
            print(f"[Shutdown] Unloaded {name} from VRAM.")
        except Exception as exc:
            print(f"[Shutdown Warning] Could not unload {name}: {exc}")


def emergency_ollama_cleanup() -> None:
    """Best-effort final cleanup used by window close, atexit, and signals."""
    try:
        release_all_ollama_models(timeout=3.0)
    except Exception:
        pass
    try:
        stop_owned_ollama_server(timeout=3.0)
    except Exception:
        pass


def call_ollama(prompt: str, model: str, images_b64: list[str] | None = None, vram_profile: str = DEFAULT_VRAM_PROFILE) -> dict:
    """Call Ollama with bounded payloads and recover from context/payload HTTP 400 errors."""
    cfg = VRAM_PROFILES.get(vram_profile, VRAM_PROFILES[DEFAULT_VRAM_PROFILE])
    max_images = int(cfg.get("max_images", 24))
    selected_images = select_relevant_images(images_b64 or [], prompt[-6000:], max_images)
    prepared_images = [_shrink_data_url_image(x) for x in selected_images]
    requested_ctx = int(cfg["num_ctx"])
    adaptive_ctx = choose_adaptive_context(prompt, prepared_images, requested_ctx) if ADAPTIVE_CONTEXT_ENABLED else requested_ctx
    TELEMETRY.images_sent += len(prepared_images)
    TELEMETRY.last_context = adaptive_ctx
    attempts = [
        (adaptive_ctx, prepared_images, prompt),
        (min(int(cfg["num_ctx"]), 8192), prepared_images[:2], prompt[-45_000:]),
        (4096, prepared_images[:1], prompt[-24_000:]),
        (4096, [], prompt[-16_000:]),
    ]
    last_error = None
    for attempt_no, (ctx, imgs, attempt_prompt) in enumerate(attempts, 1):
        started = time.time()
        if attempt_no > 1: TELEMETRY.ai_retries += 1
        msg: dict = {"role": "user", "content": attempt_prompt}
        if imgs:
            msg["images"] = imgs
        payload = json.dumps({
            "model": model,
            "messages": [msg],
            "format": "json",
            "think": False,
            "stream": False,
            "keep_alive": cfg["keep_alive"],
            "options": {
                "num_ctx": ctx,
                "temperature": 0.1,
                "num_batch": int(cfg.get("num_batch", 128)),
            },
        }).encode("utf-8")
        req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            content = data.get("message", {}).get("content", "")
            if not content:
                raise RuntimeError("Ollama returned an empty message.")
            TELEMETRY.ai_latencies.append(time.time()-started)
            return json.loads(content)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:1200]
            last_error = RuntimeError(f"Ollama HTTP {exc.code}: {body}")
            if exc.code not in (400, 413, 500, 503):
                raise last_error
            print(f"[AI Recovery] Attempt {attempt_no} rejected ({exc.code}); reducing context/images and retrying.")
        except urllib.error.URLError as exc:
            last_error = exc
            print(f"[AI Recovery] Ollama connection failed on attempt {attempt_no} ({exc}); restarting if needed and reducing the request.")
            try:
                ensure_ollama_server()
            except Exception:
                pass
        except (json.JSONDecodeError, TimeoutError) as exc:
            last_error = exc
            print(f"[AI Recovery] Attempt {attempt_no} failed ({exc}); retrying with a smaller payload.")
    raise RuntimeError(f"AI request failed after adaptive retries: {last_error}")

# === BIOMETRIC INPUT KINEMATICS (CURVED POINTER + DIGRAPH TYPING) ===
class HumanKinematics:
    """Simulates brisk, natural human pointer curves (cubic Bézier) and digraph typing."""

    def __init__(self, typing_wpm: int = 62):
        self.x = random.uniform(380.0, 720.0)
        self.y = random.uniform(260.0, 520.0)
        chars_per_sec = max(3.5, (typing_wpm * 5.0) / 60.0)
        self.base_flight = 1.0 / chars_per_sec

    @staticmethod
    def _cubic_bezier(
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        p3: tuple[float, float],
        t: float,
    ) -> tuple[float, float]:
        u = 1.0 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t
        x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
        y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
        return x, y

    @staticmethod
    def _min_jerk_progress(tau: float) -> float:
        return tau**3 * (10.0 - 15.0 * tau + 6.0 * tau**2)

    def move_to(self, page, target_x: float, target_y: float) -> None:
        ensure_foreground_focus(page)
        if not SIMULATE_HUMAN_TIMING:
            page.mouse.move(target_x, target_y)
            self.x, self.y = target_x, target_y
            return

        vp = page.viewport_size or {"width": 1280, "height": 900}
        max_w = max(100, vp["width"] - 2)
        max_h = max(100, vp["height"] - 2)

        start = (self.x, self.y)
        end = (max(2.0, min(max_w, target_x)), max(2.0, min(max_h, target_y)))
        dist = math.hypot(end[0] - start[0], end[1] - start[1])
        if dist < 3.0:
            return

        dx = end[0] - start[0]
        dy = end[1] - start[1]
        nx, ny = -dy / dist, dx / dist
        arc_mag = min(70.0, dist * random.uniform(0.06, 0.18)) * random.choice([-1.0, 1.0])

        c1 = (
            start[0] + dx * random.uniform(0.24, 0.38) + nx * arc_mag * random.uniform(0.5, 1.0),
            start[1] + dy * random.uniform(0.24, 0.38) + ny * arc_mag * random.uniform(0.5, 1.0),
        )
        c2 = (
            start[0] + dx * random.uniform(0.62, 0.80) + nx * arc_mag * random.uniform(0.2, 0.5),
            start[1] + dy * random.uniform(0.62, 0.80) + ny * arc_mag * random.uniform(0.2, 0.5),
        )

        steps = max(8, min(20, int(dist / 35.0) + random.randint(4, 7)))
        total_duration = max(0.09, min(0.32, (dist / 2400.0) + random.uniform(0.06, 0.14)))
        step_sleep = total_duration / steps

        for i in range(1, steps + 1):
            tau = i / steps
            t = self._min_jerk_progress(tau)
            px, py = self._cubic_bezier(start, c1, c2, end, t)
            px = max(2.0, min(max_w, px + random.uniform(-0.5, 0.5)))
            py = max(2.0, min(max_h, py + random.uniform(-0.5, 0.5)))
            page.mouse.move(px, py)
            time.sleep(step_sleep * random.uniform(0.8, 1.2))

        self.x, self.y = end

    def click_locator(self, page, loc) -> None:
        ensure_foreground_focus(page)
        loc.scroll_into_view_if_needed(timeout=3000)
        box = loc.bounding_box()
        if box and box["width"] > 0 and box["height"] > 0:
            tx = box["x"] + box["width"] * random.uniform(0.30, 0.70)
            ty = box["y"] + box["height"] * random.uniform(0.30, 0.70)
            self.move_to(page, tx, ty)
            if SIMULATE_HUMAN_TIMING:
                time.sleep(random.uniform(0.03, 0.09))
            page.mouse.down()
            time.sleep(random.uniform(0.035, 0.085))
            page.mouse.up()
        else:
            loc.click(timeout=5000)

    def _press_key_with_dwell(self, page, loc, ch: str) -> None:
        dwell = random.uniform(0.028, 0.068)
        try:
            page.keyboard.down(ch)
            time.sleep(dwell)
            page.keyboard.up(ch)
        except Exception:
            loc.press_sequentially(ch, delay=int(dwell * 1000))

    def type_text(self, page, loc, text: str) -> None:
        self.click_locator(page, loc)
        time.sleep(random.uniform(0.08, 0.18))

        page.keyboard.press("Control+A")
        time.sleep(random.uniform(0.03, 0.08))
        page.keyboard.press("Backspace")
        time.sleep(random.uniform(0.07, 0.15))

        text_str = str(text)
        for i, ch in enumerate(text_str):
            self._press_key_with_dwell(page, loc, ch)
            if SIMULATE_HUMAN_TIMING and i < len(text_str) - 1:
                next_ch = text_str[i + 1]
                digraph = (ch + next_ch).lower()
                flight = random.lognormvariate(math.log(self.base_flight), 0.28)
                if digraph in COMMON_DIGRAPHS:
                    flight *= random.uniform(0.62, 0.78)
                elif next_ch.isupper() or not next_ch.isalnum():
                    flight *= random.uniform(1.15, 1.45)
                time.sleep(max(0.018, min(0.24, flight)))

    def smooth_wheel_scroll(self, page, delta_y: int) -> None:
        ensure_foreground_focus(page)
        direction = 1 if delta_y >= 0 else -1
        remaining = abs(delta_y)
        while remaining > 0:
            chunk = min(remaining, random.randint(95, 180))
            page.mouse.wheel(0, direction * chunk)
            remaining -= chunk
            time.sleep(random.uniform(0.02, 0.055))


# === MEDIA PLAYBACK TELEMETRY MANAGER ===
class MediaSessionTracker:
    def __init__(self):
        self.active = False
        self.started_at = 0.0
        self.track_duration = 0.0
        self.min_required_watch = 0.0

    def reset(self) -> None:
        self.active = False
        self.started_at = 0.0
        self.track_duration = 0.0
        self.min_required_watch = 0.0

    def start_playback(self, page, kinematics: HumanKinematics, estimated_duration: float) -> None:
        self.active = True
        self.started_at = time.time()
        self.track_duration = max(25.0, estimated_duration)
        self.min_required_watch = min(45.0, self.track_duration * random.uniform(0.45, 0.65))

        try:
            for f in page.frames:
                f_url = (f.url or "").lower()
                if "youtube" in f_url or f.locator(".ytp-large-play-button").count() > 0:
                    play_btn = f.locator(".ytp-large-play-button, button[aria-label*='Play' i]").first
                    if play_btn.count() > 0 and play_btn.is_visible():
                        kinematics.click_locator(page, play_btn)
                        print(
                            f"   -> Started YouTube player (track ~{int(self.track_duration)}s, "
                            f"min watch >= {int(self.min_required_watch)}s)."
                        )
                        return

            dur = page.evaluate("""
            () => {
                const m = document.querySelector('video, audio');
                if (!m) return 0;
                m.muted = true;
                if (m.paused) m.play().catch(() => {});
                return Number.isFinite(m.duration) ? m.duration : 0;
            }
            """)
            if dur and dur > 10:
                self.track_duration = float(dur)
                self.min_required_watch = min(45.0, self.track_duration * random.uniform(0.45, 0.65))
        except Exception:
            pass

    def ensure_minimum_watch_completed(self, stop_event: threading.Event | None = None) -> None:
        if not self.active or not SIMULATE_HUMAN_TIMING:
            return
        elapsed = time.time() - self.started_at
        remaining = self.min_required_watch - elapsed
        if remaining > 0:
            wait_sec = min(45.0, remaining)
            print(
                f"   -> Waiting {wait_sec:.1f}s for media playback telemetry "
                f"({elapsed:.0f}s / {self.min_required_watch:.0f}s)..."
            )
            interruptible_sleep(wait_sec, stop_event)


# === DOM OBSERVATION, MENU INSPECTOR, SCROLLER & CLEANUP ===
CLEANUP_IDS_JS = """
() => {
    document.querySelectorAll('[data-ai-id]').forEach(el => el.removeAttribute('data-ai-id'));
}
"""

INSPECT_MENU_CARDS_JS = r"""
(mode) => {
    document.querySelectorAll('[data-menu-nav]').forEach(el => el.removeAttribute('data-menu-nav'));

    const NOISE_RE = /^(new|release|expiry|completed|passed|submitted|4 lessons|\\d+\\s+lessons?|\\d{1,3}%|chevron_right|navigate_next|arrow_forward|>)$/i;
    const EXCLUDE_RE = /(service hours|need help|talk to us|wecare@|\\+852|lesson library|my learning|students' voice|rewards|return to portal|back to modules|current level|extended section|extended listening|extended reading|extended speaking|extended writing)/i;
    const SIDEBAR_EXACT = new Set(['home', 'lesson library', 'my learning', "students' voice", 'rewards', 'return to portal']);

    const cards = [];
    const seenContainers = [];

    const allEls = Array.from(document.querySelectorAll('a, div, section, article, li'));
    for (const el of allEls) {
        const r = el.getBoundingClientRect();
        if (r.left < 180 || r.top < 110) continue;
        if (r.width < 155 || r.width > 480 || r.height < 160 || r.height > 540) continue;

        const st = window.getComputedStyle(el);
        if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') continue;

        const rawText = (el.innerText || '').trim();
        if (!rawText || EXCLUDE_RE.test(rawText)) continue;

        const hasLessonsTag = /\\b\\d+\\s+lessons?\\b/i.test(rawText);
        if (mode === 'module_list' && !hasLessonsTag) continue;

        const hasMediaOrPointer = Boolean(el.querySelector('img, svg, canvas'))
            || st.cursor === 'pointer'
            || el.tagName === 'A'
            || el.hasAttribute('onclick');
        if (!hasMediaOrPointer && !hasLessonsTag) continue;

        if (seenContainers.some(prev => prev.contains(el) || el.contains(prev))) continue;

        const lines = rawText
            .split('\\n')
            .map(s => s.trim())
            .filter(s => s && !NOISE_RE.test(s) && !SIDEBAR_EXACT.has(s.toLowerCase()));

        if (lines.length === 0) continue;
        const title = lines[0].slice(0, 120);
        if (SIDEBAR_EXACT.has(title.toLowerCase())) continue;

        const domCompleted = /\\b(completed|passed|submitted)\\b/i.test(rawText)
            || /\\b100%\\b/.test(rawText);

        seenContainers.push(el);
        cards.push({
            el,
            title,
            domCompleted,
            x: Math.round(r.left),
            y: Math.round(r.top + window.scrollY),
        });
    }

    const pageText = (document.body?.innerText || '').replace(/\\s+/g, ' ');
    const dateMatch = pageText.match(/release\s*date\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})/i);
    const pageReleaseDate = dateMatch ? dateMatch[1] : '';
    cards.forEach(c => {
          const raw = (c.el.innerText || '');
          c.locked = /\b(?:locked|blocked)\b/i.test(raw) || Boolean(c.el.querySelector('[class*="lock" i], [aria-label*="lock" i]'));
          c.releaseDate = pageReleaseDate;
    });
    cards.forEach((c, idx) => {
        c.el.setAttribute('data-menu-nav', String(idx));
        c.navIndex = idx;
    });

    return cards.map(c => ({
        navIndex: c.navIndex,
        title: c.title,
        domCompleted: c.domCompleted,
        x: c.x,
        y: c.y,
    }));
}
"""

INSPECT_SKILL_CARDS_JS = """
() => {
    document.querySelectorAll('[data-skill-nav]').forEach(el => el.removeAttribute('data-skill-nav'));
    const SKILLS = ['Listening', 'Reading', 'Writing', 'Speaking'];
    const found = {};

    const isInExtendedSection = (node) => {
        let cur = node;
        const vh = window.innerHeight || 900;
        for (let i = 0; i < 10 && cur && cur !== document.body; i++) {
            const t = (cur.innerText || '');
            if (/\\bextended\\s+section\\b/i.test(t)) {
                const r = cur.getBoundingClientRect();
                if (r.height < vh * 0.78) return true;
            }
            cur = cur.parentElement;
        }
        return false;
    };

    const allNodes = Array.from(document.querySelectorAll('div, span, p, h1, h2, h3, h4, strong, b, label'));
    for (const skill of SKILLS) {
        for (const el of allNodes) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            if (isInExtendedSection(el)) continue;

            const directTxt = (el.innerText || '').replace(/\\s+/g, ' ').trim();
            if (directTxt.toLowerCase() !== skill.toLowerCase()) continue;

            let bestCard = null;
            let parent = el.parentElement;
            for (let i = 0; i < 8 && parent; i++) {
                const pr = parent.getBoundingClientRect();
                if (pr.width >= 150 && pr.width <= 460 && pr.height >= 160 && pr.height <= 540) {
                    bestCard = parent;
                }
                parent = parent.parentElement;
            }
            if (!bestCard) continue;

            const cardText = (bestCard.innerText || '').replace(/\\s+/g, ' ').trim();
            if (/\\bextended\\s+(section|listening|reading|speaking|writing)\\b/i.test(cardText)) continue;

            const isCompleted = /\\bcompleted\\b/i.test(cardText);
            const isNew = /\\bnew\\b/i.test(cardText);
            const isLocked = /\\b(?:locked|blocked)\\b/i.test(cardText)
                || Boolean(bestCard.querySelector('[class*="lock" i], [aria-label*="lock" i], [title*="lock" i]'));

            let clickTarget = null;
            for (const btn of bestCard.querySelectorAll('button, a, [role="button"], [onclick], div, span')) {
                const br = btn.getBoundingClientRect();
                if (br.width < 18 || br.height < 18 || br.width > 120 || br.height > 120) continue;
                const btxt = (btn.innerText || '').trim();
                const bstyle = window.getComputedStyle(btn);
                if (
                    ['>', 'chevron_right', 'navigate_next', 'arrow_forward'].includes(btxt)
                    || (bstyle.cursor === 'pointer' && br.top > r.top)
                ) {
                    clickTarget = btn;
                    break;
                }
            }
            if (!clickTarget) clickTarget = bestCard;
            if (!isLocked) clickTarget.setAttribute('data-skill-nav', skill);

            found[skill] = {
                name: skill,
                completed: isCompleted,
                locked: isLocked,
                badge: isCompleted ? 'Completed' : (isLocked ? 'Locked' : (isNew ? 'New' : 'Unknown')),
            };
            break;
        }
    }

    const ordered = SKILLS.map(s => found[s]).filter(Boolean);
    return {
        all_four_present: ordered.length === 4,
        skills: ordered,
    };
}
"""

OBSERVE_UI_JS = """
(startId) => {
    document.querySelectorAll('[data-ai-id]').forEach(el => el.removeAttribute('data-ai-id'));

    const isTopWindow = (window === window.top);
    const topCutoff = isTopWindow ? 110 : 0;
    const vw = window.innerWidth || document.documentElement.clientWidth || 1280;
    const vh = window.innerHeight || document.documentElement.clientHeight || 900;
    const midX = vw * 0.52;

    let nextId = startId;
    const elements = [];
    const seenBoxes = new Set();
    const ICON_NAMES = /^(chevron_right|chevron_left|arrow_forward|arrow_back|close|expand_more|navigate_next|bar_chart|equalizer|assessment|>|<|×|✕)$/i;
    const NOISE_LABELS = /^(New|RELEASE|EXPIRY|--|students_pick|teachers_pick)$/i;
    const EXTENDED_RE = /\\bextended\\s+(section|listening|reading|speaking|writing)\\b/i;

    const isInsideExtendedSection = (el) => {
        if (!el) return false;
        const ownTxt = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
        if (EXTENDED_RE.test(ownTxt)) return true;
        let cur = el.parentElement;
        for (let i = 0; i < 10 && cur && cur !== document.body && cur !== document.documentElement; i++) {
            const t = (cur.innerText || '');
            if (/\\bextended\\s+section\\b/i.test(t)) {
                const r = cur.getBoundingClientRect();
                if (r.height < vh * 0.78) {
                    return true;
                }
            }
            cur = cur.parentElement;
        }
        return false;
    };

    const isVisibleNode = (node) => {
        if (!node) return false;
        const r = node.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
        const st = window.getComputedStyle(node);
        return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
    };

    const isFillableControl = (node) => {
        if (!node || !node.tagName) return false;
        const t = node.tagName.toLowerCase();
        if (t === 'select' || t === 'textarea') return true;
        if (t === 'input') {
            const it = (node.type || 'text').toLowerCase();
            return !['radio', 'checkbox', 'submit', 'button', 'hidden', 'file', 'image', 'reset'].includes(it);
        }
        return false;
    };

    const getCardContainer = (el) => {
        let bestCard = null;
        let parent = el.parentElement;
        for (let i = 0; i < 8 && parent; i++) {
            const r = parent.getBoundingClientRect();
            if (r.width >= 150 && r.width <= 460 && r.height >= 160 && r.height <= 540) {
                bestCard = parent;
            }
            parent = parent.parentElement;
        }
        return bestCard;
    };

    const isCardCompleted = (card) => {
        if (!card) return false;
        const txt = (card.innerText || '');
        if (/\\b100%\\b/.test(txt)) return true;
        if (/\\b(completed|passed|submitted)\\b/i.test(txt)) return true;
        const cls = (typeof card.className === 'string' ? card.className : '').toLowerCase();
        if (/complete|done|passed|finished/.test(cls)) return true;
        const icons = Array.from(card.querySelectorAll('i, span, svg')).map(n => (n.innerText || '').trim().toLowerCase());
        if (icons.some(t => ['check', 'check_circle', 'done', 'done_all'].includes(t))) return true;
        return false;
    };

    const isElementDisabled = (el) => {
        if (!el) return false;
        if (el.disabled || el.getAttribute('aria-disabled') === 'true') return true;
        const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
        if (/\\b(disabled|btn-disabled|is-disabled|inactive)\\b/.test(cls)) return true;
        const style = window.getComputedStyle(el);
        if (style.pointerEvents === 'none' || style.cursor === 'not-allowed') return true;
        return false;
    };

    const getAssociatedInput = (el) => {
        if (!el) return null;
        if (el.tagName === 'LABEL') {
            if (el.control) return el.control;
            const htmlFor = el.getAttribute('for');
            if (htmlFor) {
                const target = document.getElementById(htmlFor);
                if (target) return target;
            }
            return el.querySelector('input');
        }
        if (el.hasAttribute('option-type') || el.classList.contains('c_entry-field')) {
            return el.querySelector('input');
        }
        return null;
    };

    const getOptionType = (el) => {
        const wrapper = el.closest('[option-type]');
        return wrapper ? (wrapper.getAttribute('option-type') || '').toLowerCase() : '';
    };

    const getState = (el) => {
        const states = [];
        if (isElementDisabled(el)) states.push('disabled');

        const assocInput = getAssociatedInput(el);
        if (el.checked || (assocInput && assocInput.checked) || el.getAttribute('aria-checked') === 'true') {
            states.push('checked');
        }
        if (el.getAttribute('aria-selected') === 'true') states.push('selected');
        if (el.tagName === 'SELECT') {
            const opt = el.options[el.selectedIndex];
            if (opt && opt.text.trim()) states.push(`selected="${opt.text.trim()}"`);
        } else if ((el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && el.value) {
            states.push(`value="${el.value}"`);
        }
        const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
        if (/active|selected|checked|chosen|current/.test(cls) && !cls.includes('c_answer-neutral')) {
            states.push('highlighted');
        }
        if (/complete|done|passed|finished/.test(cls) || isCardCompleted(getCardContainer(el))) {
            states.push('completed');
        }
        return states.join(', ');
    };

    const findSentenceContainer = (el) => {
        let cur = el.parentElement;
        let fallback = cur;
        for (let i = 0; i < 8 && cur; i++) {
            const txt = (cur.innerText || '').replace(/\\s+/g, ' ').trim();
            if (txt.length >= 6) {
                fallback = cur;
                const tag = cur.tagName.toLowerCase();
                if (['p', 'li', 'tr', 'td', 'th'].includes(tag) || txt.length >= 12) {
                    return cur;
                }
            }
            cur = cur.parentElement;
        }
        return fallback;
    };

    const getBlankPositionInfo = (el) => {
        const block = findSentenceContainer(el);
        if (!block) return { index: 1, total: 1, context: '' };

        const origControls = Array.from(block.querySelectorAll('input, select, textarea'))
            .filter(c => isFillableControl(c) && isVisibleNode(c));
        const idx = origControls.indexOf(el);
        const total = Math.max(1, origControls.length);

        const clone = block.cloneNode(true);
        const allOrig = Array.from(block.querySelectorAll('input, select, textarea'));
        const allClone = Array.from(clone.querySelectorAll('input, select, textarea'));

        origControls.forEach((origCtrl, k) => {
            const rawPos = allOrig.indexOf(origCtrl);
            if (rawPos !== -1 && allClone[rawPos]) {
                const isThis = (origCtrl === el);
                const tagHint = origCtrl.tagName === 'SELECT'
                    ? 'DROPDOWN'
                    : (total > 1 ? '1 word' : 'blank');
                const labelToken = isThis
                    ? ` [[[THIS_BLANK #${k + 1} of ${total} (${tagHint})]]] `
                    : ` [BLANK #${k + 1}] `;
                allClone[rawPos].replaceWith(document.createTextNode(labelToken));
            }
        });

        return {
            index: idx === -1 ? 1 : idx + 1,
            total,
            context: (clone.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 320),
        };
    };

    const getCardContext = (el) => {
        const card = getCardContainer(el);
        if (!card) return '';
        const lines = (card.innerText || '')
            .split('\\n')
            .map(s => s.trim())
            .filter(s => s && !ICON_NAMES.test(s) && !NOISE_LABELS.test(s));
        const skill = lines.find(l => /^(Listening|Reading|Speaking|Writing)$/i.test(l));
        const score = lines.find(l => /\\b\\d{1,3}%?\\b/.test(l));
        if (skill) return score ? `${skill} (${score})` : skill;
        if (lines.length > 0) return lines[0].slice(0, 60);
        return '';
    };

    const getLabel = (el) => {
        if (isFillableControl(el)) {
            const info = getBlankPositionInfo(el);
            if (info.context) return info.context;
        }

        if (el.id) {
            const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (lbl && lbl.innerText.trim()) return lbl.innerText.trim();
        }
        const parentLbl = el.closest('label');
        if (parentLbl && parentLbl.innerText.trim()) return parentLbl.innerText.trim();

        const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
        if (cls.includes('overlay-close') || cls.includes('modal-close') || el.closest('.overlay-close, .modal-close')) {
            return 'Close Popup (X)';
        }

        let text = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('btn-text') || el.title || '')
            .replace(/\\s+/g, ' ').trim();

        text = text.replace(/^(bar_chart|equalizer|assessment|chevron_right|chevron_left|arrow_forward|arrow_back)\\s+/i, '').trim();

        if (!text || ICON_NAMES.test(text)) {
            const ctx = getCardContext(el);
            if (ctx) return text ? `${ctx} -> ${text}` : ctx;
            const rect = el.getBoundingClientRect();
            const side = rect.left < midX ? 'Left Passage' : 'Right Question';
            if (text) return `${side} -> ${text}`;
        }
        if (text) return text.slice(0, 180);

        const row = el.closest('tr, li, .option, .question, .form-group, p, div');
        return row ? row.innerText.replace(/\\s+/g, ' ').trim().slice(0, 180) : '';
    };

    const progressSteps = [];
    const seenStepLabels = new Set();
    for (const el of document.querySelectorAll('div, span, li, a, button')) {
        const r = el.getBoundingClientRect();
        if (r.top < 0 || r.top > 280 || r.width === 0 || r.height === 0) continue;
        const txt = (el.innerText || '').replace(/\\s+/g, ' ').trim();
        if (/^(Q?\\d+|Student Voice|Summary|Result)$/i.test(txt) && !seenStepLabels.has(txt)) {
            seenStepLabels.add(txt);
            const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
            const parentCls = (typeof el.parentElement?.className === 'string' ? el.parentElement.className : '').toLowerCase();
            const combo = cls + ' ' + parentCls;
            const isCurrent = /active|current|selected/.test(combo);
            const isWrong = /wrong|incorrect|red|fail|cross/.test(combo);
            const isCorrect = /correct|green|pass|tick/.test(combo) && !isWrong;
            const isAnswered = isWrong || isCorrect || /done|complete|answered|submitted/.test(combo);
            progressSteps.push({
                label: txt,
                current: isCurrent,
                answered: isAnswered,
                wrong: isWrong,
                correct: isCorrect,
            });
        }
    }

    let overlayLessonBanner = '';
    for (const hdr of document.querySelectorAll('header, [class*="header"], [class*="top-bar"], [class*="overlay"] > div, .c_course-head')) {
        const r = hdr.getBoundingClientRect();
        if (r.top >= 0 && r.top < 110 && r.height >= 36 && r.height <= 140 && r.width > 400) {
            const lines = (hdr.innerText || '').split('\\n').map(s => s.trim()).filter(s => s && !ICON_NAMES.test(s));
            if (lines.length >= 2 && /^(Listening|Reading|Speaking|Writing)$/i.test(lines[0])) {
                overlayLessonBanner = `${lines[0]} :: ${lines[1]}`;
                break;
            }
        }
    }

    const ytUrls = [];
    for (const a of document.querySelectorAll('a[href*="youtube"], a[href*="youtu.be"]')) {
        if (a.href) ytUrls.push(a.href);
    }
    for (const ifr of document.querySelectorAll('iframe[src*="youtube"], iframe[data-src*="youtube"], iframe[src*="youtu.be"]')) {
        if (ifr.src) ytUrls.push(ifr.src);
        const dsrc = ifr.getAttribute('data-src');
        if (dsrc) ytUrls.push(dsrc);
    }
    for (const meta of document.querySelectorAll('link[rel="canonical"][href*="youtube"], meta[property="og:url"][content*="youtube"]')) {
        const val = meta.href || meta.content;
        if (val) ytUrls.push(val);
    }
    if ((window.location.href || '').includes('youtube') || document.querySelector('.ytp-title-link, #movie_player')) {
        const titleLink = document.querySelector('a.ytp-title-link');
        if (titleLink && titleLink.href) ytUrls.push(titleLink.href);
        const htmlSnippet = (document.documentElement?.innerHTML || '').slice(0, 60000);
        const idMatches = htmlSnippet.match(/(?:watch\\?[^"'\\s<>]*v=|embed\\/|youtu\\.be\\/|"video_id"\\s*:\\s*")[A-Za-z0-9_-]{11}/g);
        if (idMatches) ytUrls.push(...idMatches);
    }

    const candidates = document.querySelectorAll(
        'a, button, input, select, textarea, label, [role="button"], [role="radio"], [role="checkbox"], [role="tab"], [onclick], [tabindex], div, span, li'
    );

    let hasDisabledSubmit = false;
    let hasEnabledNextOrResults = false;

    for (const el of candidates) {
        const rect = el.getBoundingClientRect();
        if (rect.width < 12 || rect.height < 12) continue;
        if (rect.width > 950 && rect.height > 500) continue;

        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

        if (isInsideExtendedSection(el)) continue;

        const tag = el.tagName.toLowerCase();
        const isNativeInteractive = ['a', 'button', 'input', 'select', 'textarea', 'label'].includes(tag)
            || ['button', 'radio', 'checkbox', 'tab'].includes(el.getAttribute('role'))
            || el.hasAttribute('onclick')
            || (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1');
        const isPointerCard = !isNativeInteractive && style.cursor === 'pointer';

        const rawText = (el.innerText || '').replace(/\\s+/g, ' ').trim();
        const isActionBox = !isNativeInteractive && !isPointerCard
            && rect.width >= 36 && rect.width <= 550
            && rect.height >= 20 && rect.height <= 320
            && /^(Challenging|Easy|Start Lessons?|Begin|Next Question|Next|Continue|Submit|Results?|Finish|Check|Confirm|OK|Back to Modules|Text \\d+|Transcript|Tapescript)\\b/i.test(rawText);

        if (!isNativeInteractive && !isPointerCard && !isActionBox) continue;

        const label = getLabel(el);
        if (!label || EXTENDED_RE.test(label)) continue;

        const boxKey = `${Math.round(rect.left)}_${Math.round(rect.top)}_${Math.round(rect.width)}_${label.slice(0, 30)}`;
        if (seenBoxes.has(boxKey)) continue;
        seenBoxes.add(boxKey);

        const id = nextId++;
        el.setAttribute('data-ai-id', String(id));

        const state = getState(el);
        const lowLbl = label.trim().toLowerCase();
        if (lowLbl.startsWith('submit') && state.includes('disabled')) {
            hasDisabledSubmit = true;
        }
        if ((lowLbl.startsWith('next question') || lowLbl === 'next' || lowLbl.startsWith('results')) && !state.includes('disabled')) {
            hasEnabledNextOrResults = true;
        }

        const normTag = el.getAttribute('role') || (tag === 'input' ? `input:${(el.type || 'text').toLowerCase()}` : tag);
        const item = {
            id,
            tag: normTag,
            text: label,
            pos: { x: Math.round(rect.left), y: Math.round(rect.top + window.scrollY) },
        };
        if (isFillableControl(el)) {
            const bInfo = getBlankPositionInfo(el);
            item.blank_index = bInfo.index;
            item.total_blanks = bInfo.total;
            if (bInfo.total > 1 && tag !== 'select') {
                item.one_word_only = true;
            }
        }
        const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
        const optType = getOptionType(el);
        if (cls.includes('c_answer') || optType) {
            item.is_answer_option = true;
            if (optType) item.option_type = optType;
        }
        if (state) item.state = state;
        if (el.name) item.group = el.name;
        if (tag === 'select') {
            item.options = Array.from(el.options).map(o => o.text.trim()).filter(Boolean);
        }
        elements.push(item);
    }

    const wrongNodes = Array.from(document.querySelectorAll(
        '[class*="c_answer-wrong"], [class*="answer-wrong"], [class*="is-wrong"], [class*="incorrect"]'
    )).filter(isVisibleNode);
    const correctNodes = Array.from(document.querySelectorAll(
        '[class*="c_answer-correct"], [class*="answer-correct"], [class*="is-correct"]'
    )).filter(isVisibleNode);

    const hasGradedOption = wrongNodes.length > 0 || correctNodes.length > 0;
    const questionComplete = hasDisabledSubmit || hasEnabledNextOrResults || hasGradedOption;

    let isWrong = wrongNodes.length > 0;
    let isCorrect = correctNodes.length > 0 && !isWrong;
    const submittedValues = [];
    const revealedAnswers = [];

    const curStepObj = progressSteps.find(s => s.current);
    if (curStepObj) {
        if (curStepObj.wrong) isWrong = true;
        else if (curStepObj.correct && !isWrong) isCorrect = true;
    }

    const parseRgb = (rgbStr) => {
        const m = String(rgbStr || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
        return m ? [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10)] : null;
    };

    const qScope = document.querySelector('[name="question"], .c_question-body') || document.body;
    if (qScope) {
        for (const ctrl of qScope.querySelectorAll('input, select, textarea')) {
            if (!isFillableControl(ctrl) || !isVisibleNode(ctrl)) continue;
            let val = '';
            if (ctrl.tagName === 'SELECT') {
                const opt = ctrl.options[ctrl.selectedIndex];
                if (opt) val = opt.text.trim();
            } else {
                val = (ctrl.value || '').trim();
            }
            if (val && !val.startsWith('--') && !submittedValues.includes(val)) {
                submittedValues.push(val);
            }
            if (questionComplete) {
                const st = window.getComputedStyle(ctrl);
                const parentSt = ctrl.parentElement ? window.getComputedStyle(ctrl.parentElement) : null;
                for (const rgb of [parseRgb(st.borderColor), parseRgb(st.color), parentSt && parseRgb(parentSt.borderColor)]) {
                    if (!rgb) continue;
                    const [r, g, b] = rgb;
                    if (r > 175 && g < 110 && b < 110) isWrong = true;
                    else if (g > 135 && r < 110 && !isWrong) isCorrect = true;
                }
            }
        }
        for (const optEl of qScope.querySelectorAll('[class*="c_answer"], [option-type] label')) {
            if (!isVisibleNode(optEl)) continue;
            const cls = (typeof optEl.className === 'string' ? optEl.className : '').toLowerCase();
            const inp = getAssociatedInput(optEl);
            const txt = (optEl.innerText || '').replace(/\\s+/g, ' ').trim();
            if (!txt) continue;
            if ((inp && inp.checked) || /active|selected|checked|chosen/.test(cls)) {
                if (!submittedValues.includes(txt)) submittedValues.push(txt);
            }
            if (/c_answer-correct|answer-correct|is-correct/.test(cls)) {
                if (!revealedAnswers.includes(txt)) revealedAnswers.push(txt);
            }
        }
        for (const rev of qScope.querySelectorAll('[class*="correct-answer"], [class*="answer-key"]')) {
            if (!isVisibleNode(rev)) continue;
            const txt = (rev.innerText || '').replace(/\\s+/g, ' ').trim();
            if (txt && txt.length <= 80 && !revealedAnswers.includes(txt)) {
                revealedAnswers.push(txt);
            }
        }
    }

    const checkedOptionInputs = Array.from(document.querySelectorAll('[option-type] input:checked, .c_entry-field input:checked'));
    const hasCheckedOption = checkedOptionInputs.length > 0;
    const hasCheckedRadio = checkedOptionInputs.some(inp => (inp.type || '').toLowerCase() === 'radio');

    const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
        .map(h => h.innerText.replace(/\\s+/g, ' ').trim())
        .filter(Boolean)
        .slice(0, 8);

    let leftPaneEl = null;
    let rightPaneEl = null;
    let bestLeftScore = -1;
    let bestRightScore = -1;

    const paneCandidates = document.querySelectorAll(
        '[name="resource"], [name="question"], .c_resource-body, .c_question-body, view, part, div, section, article, main'
    );

    for (const el of paneCandidates) {
        const r = el.getBoundingClientRect();
        if (r.top < topCutoff || r.height < 140 || r.width < 200) continue;
        if (r.width > vw * 0.68) continue;

        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') continue;

        const centerX = r.left + r.width * 0.5;
        const isResource = el.getAttribute('name') === 'resource' || el.classList.contains('c_resource-body');
        const isQuestion = el.getAttribute('name') === 'question' || el.classList.contains('c_question-body');
        const isScrollable = ['auto', 'scroll', 'overlay'].includes(style.overflowY) && el.scrollHeight > el.clientHeight + 10;
        const textLen = (el.innerText || '').trim().length;
        const hasMedia = Boolean(el.querySelector('img, canvas, svg, iframe'));

        if (centerX < midX || isResource) {
            if (isQuestion) continue;
            const score = (isResource ? 50000 : 0) + (isScrollable ? 10000 : 0) + (hasMedia ? 3000 : 0) + textLen + r.height;
            if (score > bestLeftScore && (textLen > 0 || hasMedia || isResource)) {
                bestLeftScore = score;
                leftPaneEl = el;
            }
        } else {
            if (isResource) continue;
            const score = (isQuestion ? 50000 : 0) + (isScrollable ? 10000 : 0) + textLen + r.height;
            if (score > bestRightScore && textLen > 0) {
                bestRightScore = score;
                rightPaneEl = el;
            }
        }
    }

    const extractPaneWithBlankMarkers = (paneEl) => {
        if (!paneEl) return '';
        const origInputs = Array.from(paneEl.querySelectorAll('input, select, textarea'));
        const visibleFillables = origInputs.filter(c => isFillableControl(c) && isVisibleNode(c));
        if (visibleFillables.length === 0) {
            return (paneEl.innerText || '').replace(/\\n{3,}/g, '\\n\\n').trim();
        }
        const clone = paneEl.cloneNode(true);
        const cloneInputs = Array.from(clone.querySelectorAll('input, select, textarea'));
        const total = visibleFillables.length;
        visibleFillables.forEach((origCtrl, k) => {
            const rawPos = origInputs.indexOf(origCtrl);
            if (rawPos !== -1 && cloneInputs[rawPos]) {
                const valHint = origCtrl.value ? `="${origCtrl.value}"` : '';
                const unitHint = origCtrl.tagName === 'SELECT'
                    ? 'DROPDOWN'
                    : (total > 1 ? '1 word' : 'blank');
                cloneInputs[rawPos].replaceWith(
                    document.createTextNode(` [BLANK #${k + 1} (${unitHint})${valHint}] `)
                );
            }
        });
        return (clone.innerText || '').replace(/\\n{3,}/g, '\\n\\n').trim();
    };

    const leftPaneText = extractPaneWithBlankMarkers(leftPaneEl);
    const rightPaneText = extractPaneWithBlankMarkers(rightPaneEl);

    const leftPaneHasMedia = Boolean(leftPaneEl && leftPaneEl.querySelector('img, canvas, svg'));
    const fullBody = (document.body?.innerText || '').replace(/\\n{3,}/g, '\\n\\n').trim();

    return {
        nextId,
        isTopWindow,
        overlayLessonBanner,
        questionComplete,
        gradingResult: {
            isWrong,
            isCorrect,
            submittedValues,
            revealedAnswers,
        },
        hasCheckedOption,
        hasCheckedRadio,
        ytUrls,
        headings,
        progressSteps,
        leftPaneText: leftPaneText.slice(0, 12000),
        leftPaneHasMedia,
        rightPaneText: rightPaneText.slice(0, 4500),
        fallbackBodyText: fullBody.slice(0, 8000),
        elements,
    };
}
"""

SCROLL_PROBE_JS = """
(args) => {
    const mode = args.mode || 'inspect';
    const delta = args.delta || 0;
    const isTopWindow = (window === window.top);
    const vw = window.innerWidth || document.documentElement.clientWidth || 1280;
    const midX = vw * 0.54;

    const validTargets = [];
    const candidates = Array.from(document.querySelectorAll('view, [name="resource"], .p_body, div, section, article, main, aside'));
    if (!isTopWindow && document.scrollingElement) {
        candidates.push(document.scrollingElement);
    }

    for (const el of candidates) {
        const maxScroll = el.scrollHeight - el.clientHeight;
        if (maxScroll <= 20) continue;

        const isDocRoot = (el === document.scrollingElement || el === document.documentElement || el === document.body);
        const style = window.getComputedStyle(el);
        const oy = (style.overflowY || '').toLowerCase();

        if (!isDocRoot && !['auto', 'scroll', 'overlay'].includes(oy)) continue;
        if (isDocRoot && oy === 'hidden') continue;

        let rect = null;
        if (isDocRoot) {
            rect = { left: 0, top: 0, width: vw, height: window.innerHeight || 600 };
        } else {
            const r = el.getBoundingClientRect();
            if (r.height < 140 || r.width < 180) continue;
            if (r.width > vw * 0.70) continue;
            if ((r.left + r.width * 0.5) > midX) continue;
            rect = { left: r.left, top: r.top, width: r.width, height: r.height };
        }

        const isResource = Boolean(el.querySelector('[name="resource"]') || el.getAttribute('name') === 'resource');
        const score = (isResource ? 20000 : 0) + maxScroll * 5 + rect.height;
        validTargets.push({ el, rect, maxScroll, score });
    }

    if (validTargets.length === 0) return null;
    validTargets.sort((a, b) => b.score - a.score);

    const best = validTargets[0];
    const target = best.el;

    if (mode === 'set_top') {
        target.scrollTop = 0;
    } else if (mode === 'scroll_by') {
        target.scrollTop = Math.max(0, Math.min(target.scrollHeight - target.clientHeight, target.scrollTop + delta));
    }

    const maxScroll = Math.max(1, target.scrollHeight - target.clientHeight);
    return {
        scrollTop: Math.round(target.scrollTop),
        scrollHeight: Math.round(target.scrollHeight),
        clientHeight: Math.round(target.clientHeight),
        pct: Math.round((target.scrollTop / maxScroll) * 100),
        atBottom: (target.scrollTop + target.clientHeight >= target.scrollHeight - 12),
        rect: {
            x: Math.max(0, best.rect.left),
            y: Math.max(0, best.rect.top),
            width: best.rect.width,
            height: best.rect.height,
        },
    };
}
"""

PASSAGE_READY_JS = """
() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    if (imgs.length > 0 && !imgs.every(img => img.complete && img.naturalWidth > 0)) {
        return false;
    }
    const res = document.querySelector('[name="resource"], .c_resource-body');
    if (res) {
        const hasText = (res.innerText || '').trim().length > 20;
        const hasLoadedImg = Array.from(res.querySelectorAll('img')).some(i => i.complete && i.naturalWidth > 40);
        const hasCanvasOrSvg = Boolean(res.querySelector('canvas, svg'));
        return hasText || hasLoadedImg || hasCanvasOrSvg;
    }
    return true;
}
"""


def cleanup_dom_markers(page) -> None:
    for f in page.frames:
        try:
            f.evaluate(CLEANUP_IDS_JS)
        except Exception:
            continue


def clamp_clip(page, clip: dict) -> dict:
    vp = page.viewport_size or {"width": 1280, "height": 900}
    vw, vh = vp["width"], vp["height"]
    x = max(0, min(vw - 120, int(clip.get("x", 0))))
    y = max(0, min(vh - 120, int(clip.get("y", 150))))
    w = max(120, min(vw - x, int(clip.get("width", int(vw * 0.5)))))
    h = max(120, min(vh - y, int(clip.get("height", vh - y))))
    return {"x": x, "y": y, "width": w, "height": h}


def wait_for_passage_ready(page) -> None:
    for _ in range(15):
        all_ready = True
        for f in page.frames:
            if "youtube" in (f.url or "").lower():
                continue
            try:
                if not f.evaluate(PASSAGE_READY_JS):
                    all_ready = False
            except Exception:
                continue
        if all_ready:
            return
        time.sleep(0.25)


def get_left_pane_clip(page) -> dict:
    vp = page.viewport_size or {"width": 1280, "height": 900}
    default_clip = clamp_clip(
        page,
        {"x": 0, "y": 145, "width": int(vp["width"] * 0.50), "height": vp["height"] - 150},
    )
    for f in page.frames:
        if "youtube" in (f.url or "").lower():
            continue
        try:
            frame_offset_x = 0.0
            frame_offset_y = 0.0
            if f != page.main_frame:
                fe = f.frame_element()
                fbox = fe.bounding_box()
                if not fbox or fbox["width"] < 200 or fbox["height"] < 150:
                    continue
                frame_offset_x = fbox["x"]
                frame_offset_y = fbox["y"]

            rect = f.evaluate("""
            () => {
                const vw = window.innerWidth || 1280;
                const el = document.querySelector('[name="resource"], .c_resource-body')
                    || Array.from(document.querySelectorAll('view')).find(v => {
                        const r = v.getBoundingClientRect();
                        return r.width > 200 && r.width < vw * 0.65 && (r.left + r.width * 0.5) < vw * 0.52;
                    });
                if (!el) return null;
                const r = el.getBoundingClientRect();
                if (r.width < 150 || r.height < 140) return null;
                return { x: r.left, y: r.top, width: r.width, height: r.height };
            }
            """)
            if rect:
                return clamp_clip(
                    page,
                    {
                        "x": frame_offset_x + rect["x"],
                        "y": frame_offset_y + rect["y"],
                        "width": rect["width"],
                        "height": rect["height"],
                    },
                )
        except Exception:
            continue
    return default_clip


def find_left_scroll_target(page) -> tuple[object | None, dict, dict | None]:
    default_clip = get_left_pane_clip(page)

    best_candidate = None
    best_max_scroll = -1

    for f in page.frames:
        if "youtube" in (f.url or "").lower():
            continue
        try:
            frame_offset_x = 0.0
            frame_offset_y = 0.0
            if f != page.main_frame:
                fe = f.frame_element()
                box = fe.bounding_box()
                if not box or box["width"] < 180 or box["height"] < 150:
                    continue
                frame_offset_x = box["x"]
                frame_offset_y = box["y"]

            info = f.evaluate(SCROLL_PROBE_JS, {"mode": "inspect"})
            if info:
                max_scroll = info["scrollHeight"] - info["clientHeight"]
                if max_scroll > best_max_scroll:
                    best_max_scroll = max_scroll
                    r = info["rect"]
                    clip = clamp_clip(
                        page,
                        {
                            "x": frame_offset_x + r["x"],
                            "y": frame_offset_y + r["y"],
                            "width": r["width"],
                            "height": r["height"],
                        },
                    ) if r else default_clip
                    best_candidate = (f, clip, info)
        except Exception:
            continue

    if best_candidate:
        return best_candidate
    return None, default_clip, None


def capture_passage_with_natural_scroll(page, kinematics: HumanKinematics) -> list[str]:
    ensure_foreground_focus(page)
    wait_for_passage_ready(page)
    target_frame, clip, info = find_left_scroll_target(page)

    pane_x = clip["x"] + clip["width"] * random.uniform(0.32, 0.68)
    pane_y = clip["y"] + clip["height"] * random.uniform(0.32, 0.68)
    kinematics.move_to(page, pane_x, pane_y)

    if not target_frame or not info:
        raw = page.screenshot(type="jpeg", quality=70, clip=clip)
        return [base64.b64encode(raw).decode("ascii")]

    if info["scrollTop"] > 5:
        kinematics.smooth_wheel_scroll(page, -(info["scrollTop"] + 300))
        time.sleep(0.1)
        info = target_frame.evaluate(SCROLL_PROBE_JS, {"mode": "set_top"})

    images: list[str] = []
    # Capture until the actual bottom. 64 is a runaway safeguard, not a normal limit.
    max_slices = 64
    last_top = -1
    stagnant_rounds = 0

    for _idx in range(1, max_slices + 1):
        info = target_frame.evaluate(SCROLL_PROBE_JS, {"mode": "inspect"})
        if not info:
            break

        current_top = int(info.get("scrollTop", 0))
        stagnant_rounds = stagnant_rounds + 1 if current_top == last_top else 0
        last_top = current_top

        raw = page.screenshot(type="jpeg", quality=74, clip=clip)
        encoded = base64.b64encode(raw).decode("ascii")
        if not images or encoded != images[-1]:
            images.append(encoded)
            print(f"   -> Captured passage slice {len(images)} (depth={info['pct']}%)")

        if info["atBottom"]:
            print(f"   -> Full passage reached at depth={info['pct']}%.")
            break

        prev_top = current_top
        # 18% overlap prevents lines at viewport boundaries from being omitted.
        step_px = max(220, int(info["clientHeight"] * 0.82))
        kinematics.smooth_wheel_scroll(page, step_px)
        time.sleep(0.14)
        after = target_frame.evaluate(SCROLL_PROBE_JS, {"mode": "inspect"})

        # Some Wiseman panes ignore wheel events; force their DOM scroll position.
        if stagnant_rounds >= 2 or not after or (after["scrollTop"] - prev_top) < 25:
            target_frame.evaluate(SCROLL_PROBE_JS, {"mode": "scroll_by", "delta": step_px})
            time.sleep(0.10)
    else:
        print(f"[Passage Capture Warning] Reached {max_slices} slices before the pane reported its bottom.")

    info = target_frame.evaluate(SCROLL_PROBE_JS, {"mode": "inspect"})
    if info and info["scrollTop"] > 5:
        kinematics.smooth_wheel_scroll(page, -(info["scrollTop"] + 300))
        time.sleep(0.1)
        target_frame.evaluate(SCROLL_PROBE_JS, {"mode": "set_top"})

    return images


def ensure_referenced_text_tab(
    page,
    state: dict,
    frame_map: dict,
    kinematics: HumanKinematics,
    current_text_tab: str,
) -> tuple[bool, str]:
    q_text = state.get("right_question_pane") or state.get("full_page_fallback") or ""
    match = TEXT_REF_RE.search(q_text)
    if not match:
        return False, current_text_tab

    wanted = f"text {match.group(1)}".lower()
    if current_text_tab == wanted:
        return False, current_text_tab

    for el in state.get("elements", []):
        lbl = (el.get("text") or "").strip().lower()
        if lbl == wanted or lbl.startswith(wanted + " "):
            if any(k in el.get("state", "") for k in ("active", "selected", "highlighted")):
                return False, wanted
            frame = frame_map.get(el["id"])
            if frame:
                try:
                    loc = frame.locator(f'[data-ai-id="{el["id"]}"]').first
                    kinematics.click_locator(page, loc)
                    print(f"   -> Switched passage tab to '{el['text']}' as referenced by question.")
                    time.sleep(0.45)
                    return True, wanted
                except Exception:
                    pass
    return False, current_text_tab


def try_open_builtin_transcript(page, state: dict, frame_map: dict, kinematics: HumanKinematics) -> bool:
    for el in state.get("elements", []):
        lbl = (el.get("text") or "").strip().lower()
        if lbl in ("transcript", "tapescript", "show transcript", "view transcript"):
            frame = frame_map.get(el["id"])
            if frame:
                try:
                    loc = frame.locator(f'[data-ai-id="{el["id"]}"]').first
                    kinematics.click_locator(page, loc)
                    print(f"   -> Opened Wiseman built-in '{el['text']}' panel.")
                    time.sleep(0.5)
                    return True
                except Exception:
                    pass
    return False


def simulate_reading_delay(
    text_content: str,
    image_count: int,
    reading_wpm: int,
    pacing_style: str,
    stop_event: threading.Event | None = None,
) -> None:
    if not SIMULATE_HUMAN_TIMING:
        return
    words = len((text_content or "").split())
    wpm = float(max(220, reading_wpm))
    if pacing_style == "relaxed":
        wpm *= 0.90
    elif pacing_style == "focused":
        wpm *= 1.15

    if words > 0:
        est = (words / wpm) * 60.0
        wait_sec = max(7.0, min(16.0, est * random.uniform(0.75, 1.0)))
    else:
        wait_sec = random.uniform(7.5, 11.5) + min(4.0, image_count * 0.8)

    print(f"Skimming passage ({wait_sec:.1f}s, style={pacing_style})...")
    interruptible_sleep(wait_sec, stop_event)


def get_question_think_delay(pacing_style: str) -> float:
    if pacing_style == "focused":
        mean_sec = 2.0
    elif pacing_style == "relaxed":
        mean_sec = 3.4
    else:
        mean_sec = 2.6
    delay = random.lognormvariate(math.log(mean_sec), 0.28)
    return max(1.4, min(4.8, delay))


def _detect_page_type(url: str) -> str:
    u = (url or "").lower()
    if "select_skill" in u:
        return "skill_list"
    if "select_module" in u:
        return "module_list"
    if "select_theme" in u:
        return "theme_list"
    return "portal_or_exercise"


def scan_once(
    context,
    memory: dict | None = None,
    active_theme: str = "",
    session_completed: set[str] | None = None,
) -> tuple[object, dict, dict]:
    wiseman_pages = [pg for pg in context.pages if "wiseman" in pg.url.lower()]
    lms_pages = [pg for pg in wiseman_pages if "lms" in pg.url.lower()]
    if lms_pages:
        page = lms_pages[-1]
    elif wiseman_pages:
        page = wiseman_pages[-1]
    else:
        page = context.pages[-1]

    all_headings = []
    all_progress = []
    left_texts = []
    right_texts = []
    fallback_texts = []
    all_elements = []
    yt_candidates = []
    frame_map = {}
    lesson_banner = ""
    question_complete = False
    has_checked_option = False
    has_checked_radio = False
    left_has_media = False
    grading_wrong = False
    grading_correct = False
    grading_submitted_vals: list[str] = []
    grading_revealed_vals: list[str] = []
    next_id = 0

    for frame in page.frames:
        if "youtube" in (frame.url or "").lower():
            yt_candidates.append(frame.url)
        try:
            obs = frame.evaluate(OBSERVE_UI_JS, next_id)
            next_id = obs["nextId"]
            if obs["overlayLessonBanner"]:
                lesson_banner = obs["overlayLessonBanner"]
            if obs.get("questionComplete"):
                question_complete = True
            if obs.get("hasCheckedOption"):
                has_checked_option = True
            if obs.get("hasCheckedRadio"):
                has_checked_radio = True
            if obs.get("leftPaneHasMedia"):
                left_has_media = True
            gr = obs.get("gradingResult") or {}
            if gr.get("isWrong"):
                grading_wrong = True
            if gr.get("isCorrect"):
                grading_correct = True
            for v in gr.get("submittedValues", []):
                if v and v not in grading_submitted_vals:
                    grading_submitted_vals.append(v)
            for v in gr.get("revealedAnswers", []):
                if v and v not in grading_revealed_vals:
                    grading_revealed_vals.append(v)
            yt_candidates.extend(obs.get("ytUrls", []))
            all_headings.extend(obs["headings"])
            all_progress.extend(obs["progressSteps"])
            if obs["leftPaneText"]:
                left_texts.append(obs["leftPaneText"])
            if obs["rightPaneText"]:
                right_texts.append(obs["rightPaneText"])
            if obs["fallbackBodyText"]:
                fallback_texts.append(obs["fallbackBodyText"])
            for el in obs["elements"]:
                all_elements.append(el)
                frame_map[el["id"]] = frame
        except Exception:
            continue

    joined_left = "\n---\n".join(left_texts)[:12000]
    joined_fallback = "\n---\n".join(fallback_texts)[:8000]

    yt_video_id = None
    for candidate in yt_candidates + [joined_left, joined_fallback]:
        yt_video_id = extract_youtube_id(candidate)
        if yt_video_id:
            break

    q_steps = [s for s in all_progress if s["label"].upper().lstrip("Q").isdigit()]
    answered_q_steps = [s["label"] for s in q_steps if s.get("answered")]
    current_step = next((s["label"] for s in all_progress if s["current"]), "Unknown")

    state = {
        "url": page.url,
        "page_type": _detect_page_type(page.url),
        "title": page.title(),
        "lesson_banner": lesson_banner,
        "question_complete": question_complete,
        "grading_result": {
            "is_wrong": grading_wrong,
            "is_correct": grading_correct and not grading_wrong,
            "submitted_values": grading_submitted_vals,
            "revealed_answers": grading_revealed_vals,
            "feedback_text": "\n---\n".join(right_texts)[:1800] if (grading_wrong or grading_correct) else "",
        },
        "has_checked_option": has_checked_option,
        "has_checked_radio": has_checked_radio,
        "left_has_media": left_has_media,
        "youtube_video_id": yt_video_id,
        "headings": list(dict.fromkeys(all_headings)),
        "lesson_progress": {
            "total_questions_detected": len(q_steps),
            "already_answered_questions": answered_q_steps,
            "current_step": current_step,
            "all_steps": [s["label"] for s in all_progress],
        },
        "elements": all_elements[:120],
        "left_passage_pane": joined_left,
        "right_question_pane": "\n---\n".join(right_texts)[:4500],
        "full_page_fallback": joined_fallback,
    }
    if memory is not None:
        annotate_completed_menu_items(state, memory, active_theme, session_completed)
    return page, state, frame_map


def observe_browser(
    context,
    memory: dict | None = None,
    active_theme: str = "",
    session_completed: set[str] | None = None,
) -> tuple[object, dict, dict]:
    page, state, frame_map = scan_once(context, memory, active_theme, session_completed)
    for _ in range(6):
        if len(state["elements"]) > 2:
            break
        time.sleep(0.35)
        page, state, frame_map = scan_once(context, memory, active_theme, session_completed)
    return page, state, frame_map


def summarize_diff(before: dict, after: dict) -> str:
    notes = []
    if before["url"] != after["url"]:
        notes.append(f"URL changed to {after['url']}")
    if before["headings"] != after["headings"]:
        notes.append(f"Headings changed to {after['headings']}")
    if before["lesson_progress"]["current_step"] != after["lesson_progress"]["current_step"]:
        notes.append(
            f"Progress moved {before['lesson_progress']['current_step']} -> {after['lesson_progress']['current_step']}"
        )

    before_states = {e["text"]: e.get("state", "") for e in before["elements"]}
    for e in after["elements"]:
        prev = before_states.get(e["text"])
        curr = e.get("state", "")
        if prev is not None and prev != curr and curr:
            notes.append(f"'{e['text'][:40]}' state became [{curr}]")

    if len(after["elements"]) != len(before["elements"]):
        notes.append(f"Visible controls changed ({len(before['elements'])} -> {len(after['elements'])})")

    if not notes:
        return "No major DOM/URL change detected."
    return "; ".join(notes)


def is_login_screen(state: dict) -> bool:
    return any(e.get("tag") == "input:password" for e in state.get("elements", []))


def is_difficulty_modal_open(state: dict) -> bool:
    body_lower = state.get("full_page_fallback", "").lower()
    if "level of difficulty" in body_lower:
        return True
    el_texts = {(el.get("text") or "").strip().lower() for el in state.get("elements", [])}
    if "challenging" in el_texts or "easy" in el_texts:
        return True
    if state.get("page_type") != "skill_list" and ("start lessons" in el_texts or "start lesson" in el_texts):
        return True
    return False


def handle_difficulty_modal(
    page,
    state: dict,
    frame_map: dict,
    kinematics: HumanKinematics,
) -> bool:
    if not is_difficulty_modal_open(state):
        return False

    ensure_foreground_focus(page)
    challenging_el = next(
        (e for e in state["elements"] if e.get("text", "").strip().lower() == "challenging"),
        None,
    )
    if challenging_el and not any(k in challenging_el.get("state", "") for k in ("active", "selected", "highlighted", "checked")):
        frame = frame_map.get(challenging_el["id"])
        if frame:
            try:
                kinematics.click_locator(page, frame.locator(f'[data-ai-id="{challenging_el["id"]}"]').first)
                print("   -> [Difficulty Modal] Selected 'Challenging'")
                time.sleep(random.uniform(0.30, 0.55))
            except Exception:
                pass

    start_el = next(
        (
            e for e in state["elements"]
            if e.get("text", "").strip().lower() in ("start lessons", "start lesson")
            and "disabled" not in e.get("state", "")
        ),
        None,
    )
    if start_el:
        frame = frame_map.get(start_el["id"])
        if frame:
            try:
                kinematics.click_locator(page, frame.locator(f'[data-ai-id="{start_el["id"]}"]').first)
                print(f"   -> [Difficulty Modal] Clicked '{start_el['text']}'")
                return True
            except Exception:
                pass
    return False


def manage_submenu_navigation(
    page,
    state: dict,
    frame_map: dict,
    kinematics: HumanKinematics,
    memory: dict,
    active_theme: str,
    session_completed: set[str],
) -> tuple[bool, str]:
    ptype = state.get("page_type", "")
    if ptype not in ("theme_list", "module_list"):
        return False, ""

    cards = None
    for _ in range(6):
        try:
            cards = page.evaluate(INSPECT_MENU_CARDS_JS, ptype)
        except Exception:
            cards = []
        if cards:
            break
        time.sleep(0.35)

    if not cards:
        return False, ""

    completed_norms = get_completed_title_set(memory, session_completed)
    if ptype == "theme_list":
        ambiguous = set(memory.get("ambiguous_legacy_parents", []))
        completed_norms -= ambiguous
    theme_ctx = active_theme if ptype == "module_list" else ""

    evaluated_cards: list[dict] = []
    for c in cards:
        lock_key = " :: ".join(x for x in (active_theme, c["title"]) if x)
        remembered_locked, remembered_date = is_item_locked(memory, lock_key, c["title"])
        if c.get("locked"):
            release_iso = _parse_release_date(c.get("releaseDate", "") or state.get("full_page_fallback", ""))
            remember_locked_item(memory, lock_key, release_iso, c.get("releaseDate", "") or "Locked card")
            remembered_locked, remembered_date = True, release_iso or (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        hierarchy_level = "theme" if ptype == "theme_list" else "module"
        done = bool(c.get("domCompleted")) or is_title_completed(
            c["title"], completed_norms, active_theme=theme_ctx, level=hierarchy_level
        )
        if ptype == "theme_list" and is_theme_verified_complete(memory, c["title"]):
            done = True
        evaluated_cards.append({**c, "done": done, "locked_until": remembered_date if remembered_locked else ""})

    header_label = active_theme or (state["headings"][0] if state["headings"] else ptype)
    summary_str = " | ".join(
        f"{c['title']}: {('Locked until ' + c['locked_until']) if c.get('locked_until') else ('Done (skipped)' if c['done'] else 'Pending')}"
        for c in evaluated_cards
    )
    print(f"\n[{'Submenu' if ptype == 'module_list' else 'Topic'} Check] {header_label} -> {summary_str}")

    pending = [c for c in evaluated_cards if not c["done"] and not c.get("locked_until")]
    locked_pending = [c for c in evaluated_cards if not c["done"] and c.get("locked_until")]

    if not pending and locked_pending:
        nearest = min(c["locked_until"] for c in locked_pending)
        print(f"[Locked] All remaining cards are unavailable until at least {nearest}; leaving this screen without marking it complete.")
        if ptype == "module_list":
            try:
                lib_loc = page.locator("a, button, div, span").filter(has_text=re.compile(r"^\s*Lesson Library\s*$", re.I)).first
                if lib_loc.count() > 0:
                    kinematics.click_locator(page, lib_loc)
                    return True, ""
            except Exception:
                pass
        return False, ""

    if not pending:
        if ptype == "module_list":
            print(f"[Full Check Passed] All {len(evaluated_cards)} submenus in '{header_label}' are completed! Avoiding it.")
            if header_label and header_label != "module_list":
                record_verified_theme(memory, header_label, evaluated_cards, session_completed)

            lib_el = next(
                (e for e in state["elements"] if e.get("text", "").strip().lower() == "lesson library"),
                None,
            )
            if lib_el:
                frame = frame_map.get(lib_el["id"])
                if frame:
                    try:
                        kinematics.click_locator(page, frame.locator(f'[data-ai-id="{lib_el["id"]}"]').first)
                        print("   -> Returning to 'Lesson Library' to pick next uncompleted Topic...")
                        return True, ""
                    except Exception:
                        pass
            try:
                lib_loc = page.locator("a, button, div, span").filter(has_text=re.compile(r"^\s*Lesson Library\s*$", re.I)).first
                if lib_loc.count() > 0:
                    kinematics.click_locator(page, lib_loc)
                    print("   -> Returning to 'Lesson Library' to pick next uncompleted Topic...")
                    return True, ""
            except Exception:
                pass
        else:
            kinematics.smooth_wheel_scroll(page, 550)
            print("   -> All visible Topics in view are completed; scrolling for more...")
            return True, ""

        return False, ""

    pending.sort(key=lambda c: (c["y"], c["x"]), reverse=True)
    chosen = pending[0]
    if ptype == "theme_list" and is_theme_verified_complete(memory, chosen["title"]):
        print(f"[Click Guard] Rejected completed theme: '{chosen['title']}'.")
        return True, ""
    loc = page.locator(f'[data-menu-nav="{chosen["navIndex"]}"]').first
    if loc.count() > 0:
        try:
            kinematics.click_locator(page, loc)
            print(f"   -> Opening next pending {'submenu' if ptype == 'module_list' else 'topic'}: '{chosen['title']}'")
            return True, chosen["title"]
        except Exception as e:
            print(f"   -> Failed clicking '{chosen['title']}': {e}")

    return False, ""


def manage_module_skills(
    page,
    state: dict,
    frame_map: dict,
    kinematics: HumanKinematics,
    memory: dict,
    active_theme: str,
    active_module: str,
    session_verified_skills: set[str],
    session_completed: set[str],
) -> tuple[bool, str]:
    if "select_skill" not in state["url"].lower():
        return False, ""

    # Hard gate: the page heading is more reliable than individual card DOM structure.
    # This runs before assigning or clicking any skill navigation target.
    page_evidence = " ".join(
        x for x in [
            " ".join(state.get("headings", [])),
            state.get("full_page_fallback", ""),
            active_module,
        ] if x
    )
    release_iso = _parse_release_date(page_evidence)
    if release_iso:
        try:
            release_day = datetime.date.fromisoformat(release_iso)
        except ValueError:
            release_day = None
        if release_day and datetime.date.today() < release_day:
            module_label = active_module or next(
                (h for h in state.get("headings", []) if "release date" in h.lower()),
                "Locked module",
            )
            for skill_name in ("Listening", "Reading", "Speaking", "Writing"):
                key = f"{active_theme}::{module_label}::{skill_name}"
                remember_locked_item(memory, key, release_iso, page_evidence)
            remember_locked_item(memory, f"{active_theme}::{module_label}", release_iso, page_evidence)
            print(f"[Release Gate] '{module_label}' is unavailable until {release_iso}. No skill card will be clicked.")
            try:
                lib_loc = page.locator("a, button, div, span").filter(
                    has_text=re.compile(r"^\s*Lesson Library\s*$", re.I)
                ).first
                if lib_loc.count() > 0:
                    kinematics.click_locator(page, lib_loc)
                    return True, ""
            except Exception as exc:
                print(f"[Release Gate] Lesson Library navigation failed: {exc}")
            try:
                page.go_back(wait_until="domcontentloaded", timeout=10000)
                return True, ""
            except Exception:
                return False, ""

    try:
        info = page.evaluate(INSPECT_SKILL_CARDS_JS)
    except Exception:
        return False, ""

    if not info or not info.get("all_four_present"):
        return False, ""

    mod_name = active_module or (state["headings"][0] if state["headings"] else "Current Module")
    skills_info = info["skills"]

    effective_status: list[tuple[str, bool, str]] = []
    for item in skills_info:
        sname = item["name"]
        mod_skill_key = f"{active_theme}::{mod_name}::{sname}"
        remembered_locked, release_date = is_item_locked(memory, mod_skill_key)
        quarantined, retry_after, quarantine_reason = is_learning_item_quarantined(memory, mod_skill_key)
        if item.get("locked"):
            release_iso = _parse_release_date(state.get("full_page_fallback", ""))
            remember_locked_item(memory, mod_skill_key, release_iso, state.get("full_page_fallback", ""))
            remembered_locked, release_date = True, release_iso or (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        done = bool(item["completed"]) or (mod_skill_key in session_verified_skills)
        unavailable = remembered_locked or quarantined
        badge_label = "Completed" if done else (("Locked until " + release_date) if remembered_locked else (("Quarantined until " + retry_after + " · " + quarantine_reason) if quarantined else item.get("badge", "New")))
        effective_status.append((sname, done, badge_label, unavailable))

    status_line = " | ".join(f"{name}: {badge}" for name, _, badge, _ in effective_status)
    print(f"\n[Module 4-Skill Check] {mod_name} -> {status_line}")

    next_skill = next((name for name, done, _, locked in effective_status if not done and not locked), None)

    if next_skill:
        loc = page.locator(f'[data-skill-nav="{next_skill}"]').first
        if loc.count() > 0:
            try:
                live_locked = loc.evaluate(r"""el => {
                    let cur = el;
                    for (let i = 0; i < 8 && cur; i++, cur = cur.parentElement) {
                        const text = (cur.innerText || '').replace(/\s+/g, ' ');
                        if (/\b(?:locked|blocked)\b/i.test(text)) return true;
                        if (cur.querySelector && cur.querySelector('[class*="lock" i], [aria-label*="lock" i], [title*="lock" i]')) return true;
                    }
                    return false;
                }""")
                if live_locked:
                    release_iso = _parse_release_date(page_evidence)
                    key = f"{active_theme}::{mod_name}::{next_skill}"
                    remember_locked_item(memory, key, release_iso, page_evidence)
                    print(f"   -> BLOCKED stale skill click: '{next_skill}' is locked.")
                    return True, ""
                kinematics.click_locator(page, loc)
                print(f"   -> Starting next uncompleted task: '{next_skill}'")
                return True, next_skill
            except Exception as e:
                print(f"   -> Failed clicking '{next_skill}' card: {e}")
        return False, ""

    if any(locked and not done for _, done, _, locked in effective_status):
        print(f"[Unavailable] No currently actionable skill remains in '{mod_name}'. Returning without marking it complete.")
        try:
            back_loc = page.locator("a, button").filter(has_text=re.compile(r"Back to Modules", re.I)).first
            if back_loc.count() > 0:
                kinematics.click_locator(page, back_loc)
                return True, ""
        except Exception:
            pass
        return False, ""
    print(f"[Full Check Passed] All 4 tasks (Listening, Reading, Writing, Speaking) completed for '{mod_name}'!")
    full_mod_tag = " :: ".join(x for x in (active_theme, mod_name) if x)
    record_completed(
        memory,
        [full_mod_tag or mod_name],
        session_completed=session_completed,
    )

    back_el = next(
        (e for e in state["elements"] if "back to modules" in e.get("text", "").lower()),
        None,
    )
    if back_el:
        frame = frame_map.get(back_el["id"])
        if frame:
            try:
                kinematics.click_locator(page, frame.locator(f'[data-ai-id="{back_el["id"]}"]').first)
                print("   -> Moving on to next module via 'Back to Modules'...")
                return True, ""
            except Exception:
                pass

    try:
        back_loc = page.locator("a, button").filter(has_text=re.compile(r"Back to Modules", re.I)).first
        if back_loc.count() > 0:
            kinematics.click_locator(page, back_loc)
            print("   -> Moving on to next module via 'Back to Modules'...")
            return True, ""
    except Exception:
        pass

    return False, ""


def is_score_screen(state: dict) -> bool:
    return "your score:" in state["full_page_fallback"].lower()


def is_submit_disabled(state: dict) -> bool:
    submit_els = [
        e for e in state["elements"]
        if e.get("text", "").strip().lower().startswith("submit")
    ]
    return bool(submit_els) and all("disabled" in e.get("state", "") for e in submit_els)


def is_question_already_complete(state: dict) -> bool:
    if state.get("question_complete") or is_submit_disabled(state):
        return True
    for el in state["elements"]:
        if "disabled" in el.get("state", ""):
            continue
        txt = el.get("text", "").strip().lower()
        if txt.startswith("next question") or txt == "next" or txt.startswith("results"):
            return True
    return False


def is_lesson_already_finished(state: dict, submitted_count_in_session: int) -> tuple[bool, str]:
    if submitted_count_in_session > 0:
        return False, ""

    prog = state["lesson_progress"]
    total_q = prog["total_questions_detected"]
    already_answered = prog["already_answered_questions"]
    cur = prog["current_step"].lower()
    body_lower = state["full_page_fallback"].lower()

    if is_score_screen(state):
        return True, "Already on 'Your Score' screen"

    if "student voice" in cur:
        submit_el = next(
            (e for e in state["elements"] if e["text"].strip().lower().startswith("submit")),
            None,
        )
        if not submit_el or "disabled" in submit_el.get("state", ""):
            return True, "Already at finished Student Voice screen"

    if total_q > 0 and len(already_answered) >= total_q:
        return True, f"All {total_q}/{total_q} questions already completed"

    if "level of difficulty" in body_lower and any(
        phrase in body_lower for phrase in ("already completed", "view result", "review lesson")
    ):
        return True, "Difficulty/intro screen indicates lesson is already completed"

    return False, ""


def _is_text_input_tag(tag: str) -> bool:
    return tag == "textarea" or (
        tag.startswith("input:")
        and tag not in ("input:radio", "input:checkbox", "input:submit", "input:button", "input:hidden", "input:file", "input:image", "input:reset")
    )


def has_unfilled_blanks(state: dict) -> bool:
    for el in state["elements"]:
        tag = el.get("tag", "")
        st = el.get("state", "")
        if "disabled" in st:
            continue
        if tag == "select":
            if 'selected="' not in st or 'selected="--' in st or 'selected="select' in st.lower():
                return True
        elif _is_text_input_tag(tag):
            if "value=" not in st:
                return True
    return False


def has_existing_answer(state: dict) -> bool:
    if state.get("has_checked_option") or state.get("has_checked_radio"):
        return True
    for el in state["elements"]:
        tag = el.get("tag", "")
        st = el.get("state", "")
        if tag in ("radio", "checkbox", "input:radio", "input:checkbox") and "checked" in st:
            return True
        if tag == "select" and 'selected="' in st and 'selected="--' not in st:
            return True
        if _is_text_input_tag(tag) and "value=" in st:
            return True
        if el.get("is_answer_option") and any(k in st for k in ("checked", "selected", "highlighted")):
            return True
    return False


def is_answer_already_chosen(state: dict) -> bool:
    if is_question_already_complete(state) or is_submit_disabled(state):
        return False
    has_enabled_submit = any(
        e.get("text", "").strip().lower().startswith("submit") and "disabled" not in e.get("state", "")
        for e in state["elements"]
    )
    if not has_enabled_submit or has_unfilled_blanks(state):
        return False

    if state.get("has_checked_radio"):
        return True

    option_els = [e for e in state["elements"] if e.get("is_answer_option")]
    if option_els:
        is_multi_checkbox = any(e.get("option_type") == "checkbox" for e in option_els)
        if not is_multi_checkbox and any(
            any(k in e.get("state", "") for k in ("checked", "selected", "highlighted"))
            for e in option_els
        ):
            return True
        return False

    blank_els = [
        e for e in state["elements"]
        if (e.get("tag") == "select" or _is_text_input_tag(e.get("tag", ""))) and "disabled" not in e.get("state", "")
    ]
    return bool(blank_els) and has_existing_answer(state)


def submit_chosen_answer(
    page,
    state: dict,
    frame_map: dict,
    kinematics: HumanKinematics,
    media_tracker: MediaSessionTracker,
    stop_event: threading.Event | None = None,
) -> dict | None:
    cur_step = state["lesson_progress"]["current_step"].lower()
    if "student voice" in cur_step and media_tracker.active:
        media_tracker.ensure_minimum_watch_completed(stop_event)

    if SIMULATE_HUMAN_TIMING:
        interruptible_sleep(random.uniform(0.35, 0.80), stop_event)

    submit_el = next(
        (
            e for e in state["elements"]
            if e.get("text", "").strip().lower().startswith("submit")
            and "disabled" not in e.get("state", "")
        ),
        None,
    )
    if submit_el:
        frame = frame_map.get(submit_el["id"])
        if frame:
            loc = frame.locator(f'[data-ai-id="{submit_el["id"]}"]').first
            try:
                kinematics.click_locator(page, loc)
                print(f"   -> [Answer already chosen] Clicked [{submit_el['id']}] '{submit_el['text'][:45]}'")
                return submit_el
            except Exception:
                pass

    for f in page.frames:
        if "youtube" in (f.url or "").lower():
            continue
        try:
            cand = f.locator('button[btn-for="submit"]:not(:disabled), button[aria-label="Submit"]:not(:disabled)').first
            if cand.count() > 0:
                kinematics.click_locator(page, cand)
                print("   -> [Answer already chosen] Clicked 'Submit'")
                return {"text": "Submit"}
        except Exception:
            continue

    return None


def advance_completed_question(
    page,
    state: dict,
    frame_map: dict,
    kinematics: HumanKinematics,
    media_tracker: MediaSessionTracker,
    stop_event: threading.Event | None = None,
) -> dict | None:
    if not is_question_already_complete(state):
        return None

    cur_step = state["lesson_progress"]["current_step"].lower()
    is_sv = "student voice" in cur_step
    target_prefixes = ("results", "result") if is_sv else ("next question", "next", "results", "result")

    if is_sv and media_tracker.active:
        media_tracker.ensure_minimum_watch_completed(stop_event)

    if SIMULATE_HUMAN_TIMING:
        interruptible_sleep(random.uniform(0.75, 1.45), stop_event)

    target_el = None
    for el in state["elements"]:
        st = el.get("state", "")
        if "disabled" in st or "completed" in st:
            continue
        txt = el.get("text", "").strip().lower()
        if "previous" in txt:
            continue
        if any(txt == p or txt.startswith(p) for p in target_prefixes):
            target_el = el
            break

    if target_el:
        frame = frame_map.get(target_el["id"])
        if frame:
            loc = frame.locator(f'[data-ai-id="{target_el["id"]}"]').first
            try:
                kinematics.click_locator(page, loc)
                print(f"   -> [Complete -> Next] Clicked [{target_el['id']}] '{target_el['text'][:45]}'")
                return target_el
            except Exception:
                pass

    pattern = re.compile(r"^\s*(Results?|Next Question|Next)\b", re.IGNORECASE)
    for f in page.frames:
        if "youtube" in (f.url or "").lower():
            continue
        try:
            cand = f.locator("button, a, div[role='button'], [onclick], div, span").filter(has_text=pattern).last
            if cand.count() > 0:
                txt = (cand.inner_text() or "").strip().splitlines()[0]
                if "previous" in txt.lower():
                    continue
                kinematics.click_locator(page, cand)
                print(f"   -> [Complete -> Next] Clicked '{txt[:45]}'")
                return {"text": txt}
        except Exception:
            continue

    return None


def _lesson_overlay_evidence(page, lesson_banner: str = "") -> dict:
    """A score screen is an open lesson even when normal question controls disappeared."""
    banner_tail=(lesson_banner or "").split("::")[-1].strip().lower()
    frames=[]; strong_open=False; score_open=False
    for idx,frame in enumerate(page.frames):
        try:
            ev=frame.evaluate(r"""banner=>{
                const vis=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>8&&r.height>8&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0'};
                const body=(document.body?.innerText||'').replace(/\s+/g,' ').trim();
                const score=/\bYour Score\s*:?\s*\d*%?/i.test(body)||/\bEXCELLENT!\b/i.test(body);
                const exercise=/\bSubmit\b|\bDictionary\b|\bQ\d+\b/i.test(body);
                const bannerMatch=Boolean(banner&&body.toLowerCase().includes(banner));
                const explicit=[...document.querySelectorAll('[class*="lesson-overlay" i],[class*="course-overlay" i],[role="dialog"]')].some(vis);
                const close=[...document.querySelectorAll('.overlay-close,.modal-close,button[aria-label*="close" i],[title*="close" i]')].some(vis);
                return {bodySample:body.slice(0,300),score,exercise,bannerMatch,explicit,close,open:score||explicit||(close&&(exercise||score))||(bannerMatch&&(exercise||score))};
            }""",banner_tail)
            ev["frame_index"]=idx;ev["url"]=frame.url;frames.append(ev)
            strong_open=strong_open or bool(ev.get("open"));score_open=score_open or bool(ev.get("score"))
        except Exception: pass
    return {"open":strong_open,"score":score_open,"frames":frames}


def _overlay_still_open(page, lesson_banner: str = "") -> bool:
    return bool(_lesson_overlay_evidence(page,lesson_banner).get("open"))


def _click_score_screen_x_by_position(page) -> bool:
    """Target the conspicuous top-right X shown on score screens, including non-semantic div/svg controls."""
    for frame in page.frames:
        try:
            point=frame.evaluate(r"""()=>{
                const vis=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>=18&&r.height>=18&&s.display!=='none'&&s.visibility!=='hidden'};
                const W=window.innerWidth,H=window.innerHeight;
                const els=[...document.querySelectorAll('button,a,div,span,svg,path,[role="button"],[onclick]')];
                const scored=[];
                for(const e of els){if(!vis(e))continue;const r=e.getBoundingClientRect();const txt=((e.innerText||e.textContent||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.getAttribute('title')||'')).trim();
                    const cross=/^(x|×|✕|close)$/i.test(txt)||/close/i.test(txt)||e.matches('[class*="close" i],[id*="close" i]');
                    const topRight=r.left>W*.72&&r.top<H*.28; const compact=r.width<100&&r.height<100;
                    if(cross&&topRight&&compact)scored.push({x:r.left+r.width/2,y:r.top+r.height/2,score:(r.left/W)*3-(r.top/H)+(txt?2:0)});
                }
                scored.sort((a,b)=>b.score-a.score);return scored[0]||null;
            }""")
            if point:
                frame.locator('body').press('Escape') if False else None
                page.mouse.click(float(point['x']),float(point['y']))
                return True
        except Exception: pass
    return False


def close_overlay_and_exit(page, state: dict, frame_map: dict, kinematics: HumanKinematics) -> bool:
    ensure_foreground_focus(page);banner=state.get("lesson_banner","")
    evidence=_lesson_overlay_evidence(page,banner)
    if not evidence.get("open"):
        # Do not claim success merely because ordinary question controls vanished on the score screen.
        if is_score_screen(state):
            evidence["open"]=True;evidence["score"]=True
        else:
            print("   -> Lesson was already closed.");return True
    candidates=[]
    for el in state.get("elements",[]):
        label=el.get("text","")
        if any(x in label.lower() for x in ("close popup","close","×","✕")):
            frame=frame_map.get(el.get("id"))
            if frame:candidates.append((label or "close",frame.locator(f'[data-ai-id="{el["id"]}"]').first))
    selectors=(".overlay-close:visible",".modal-close:visible","button[aria-label*='close' i]:visible","[role='button'][aria-label*='close' i]:visible","[class*='close' i]:visible","[id*='close' i]:visible","text=/^[×✕X]$/")
    for frame in page.frames:
        for sel in selectors:
            try:
                loc=frame.locator(sel).first
                if loc.count()>0 and loc.is_visible(timeout=250):candidates.append((sel,loc))
            except Exception:pass
    for label,loc in candidates:
        for method in ("normal","force","dom"):
            try:
                if method=="normal":loc.click(timeout=1200)
                elif method=="force":loc.click(force=True,timeout=1200)
                else:loc.evaluate("el=>{el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));el.click();}")
                for _ in range(12):
                    time.sleep(.15)
                    if not _overlay_still_open(page,banner):print(f"   -> Verified score/lesson closed via {method} click on '{label}'.");return True
            except Exception:pass
    if evidence.get("score") and _click_score_screen_x_by_position(page):
        for _ in range(15):
            time.sleep(.15)
            if not _overlay_still_open(page,banner):print("   -> Verified score screen closed via top-right X coordinates.");return True
    # Last-resort key handling used by many modal libraries.
    try:
        page.keyboard.press("Escape");time.sleep(.5)
        if not _overlay_still_open(page,banner):print("   -> Verified lesson closed with Escape.");return True
    except Exception:pass
    print("[Close Guard] Score/lesson screen remains open; local lesson state will be preserved.")
    return False


# === LLM DECISION ENGINE ===
def decide_next_actions(
    model: str,
    state: dict,
    history: list[str],
    memory: dict,
    passage_images: list[str],
    yt_transcript: str,
    intentional_miss: bool = False,
    is_writing_task: bool = False,
    confirmed_used_words: list[str] | None = None,
    reusable_wrong_words: list[dict] | None = None,
    vram_profile: str = DEFAULT_VRAM_PROFILE,
) -> dict:
    cur_step = state["lesson_progress"]["current_step"].lower()
    is_student_voice = "student voice" in cur_step
    modal_open = is_difficulty_modal_open(state)
    in_question = (
        (state["lesson_progress"]["total_questions_detected"] > 0 or bool(state["lesson_banner"]))
        and not is_student_voice
        and not modal_open
    )
    apply_miss = bool(intentional_miss and in_question and not is_writing_task)

    has_dom_passage = bool((state.get("left_passage_pane") or "").strip())
    has_images = bool(passage_images)

    if yt_transcript and in_question and not yt_transcript.startswith("[CAPTIONS UNAVAILABLE"):
        stimulus_text = f"""=== YOUTUBE VIDEO TRANSCRIPT (Video ID: {state['youtube_video_id']}) ===
{yt_transcript[:14000]}"""
    elif yt_transcript and yt_transcript.startswith("[CAPTIONS UNAVAILABLE") and in_question:
        stimulus_text = f"""=== VIDEO WITHOUT CAPTIONS (Video ID: {state['youtube_video_id']}) ===
Use the attached screenshot(s), visible question, answer options, title/thumbnail, and careful reasoning. Missing captions do not make the lesson unavailable.
{yt_transcript}"""
    elif in_question:
        img_note = (
            f"({len(passage_images)} screenshot(s) of the left passage pane are attached—read every word in the images carefully.)"
            if has_images
            else "(No passage images attached.)"
        )
        dom_block = (
            state["left_passage_pane"]
            if has_dom_passage
            else "(No plain-text DOM passage extracted; read the attached screenshot(s) of the left pane.)"
        )
        stimulus_text = f"""{img_note}
Extracted DOM text:
{dom_block}"""
    else:
        stimulus_text = "(Passage omitted for menu / Difficulty popup / Student Voice step)"

    if in_question or state["right_question_pane"]:
        content_section = f"""=== LEFT PANE (PASSAGE / VIDEO TRANSCRIPT) ===
{stimulus_text}

=== RIGHT PANE (CURRENT QUESTION & INSTRUCTIONS) ===
{state["right_question_pane"] or state["full_page_fallback"]}"""
    else:
        content_section = f"""=== PAGE TEXT ===
{state["full_page_fallback"]}"""

    if apply_miss:
        grounding_rule = (
            "1. **INTENTIONAL HUMAN ERROR MODE (ACTIVE FOR THIS QUESTION ONLY):** "
            "First read the passage/transcript to determine what the TRUE answer is, and then **DELIBERATELY CHOOSE A PLAUSIBLE BUT INCORRECT ANSWER** "
            "(for example: pick a tempting distractor option in multiple choice, flip True/False/Not Given to a wrong choice, pick a wrong dropdown option, "
            "or enter a realistic but wrong English word/phrase from the topic into blanks). "
            "NEVER leave blanks empty and NEVER type gibberish—still fill every required blank cleanly and click 'Submit'. "
            "Set 'evidence_quote' to 'Intentional human error mode: selected plausible distractor'."
        )
    elif has_dom_passage or has_images or yt_transcript:
        grounding_rule = (
            "1. Read the provided passage text, attached passage screenshot(s), or YouTube video transcript carefully. "
            "Base your answer STRICTLY on the passage/transcript evidence (copy a short supporting quote into 'evidence_quote', "
            "or state 'Not stated in the passage/transcript' for Not Given items). Do NOT claim the passage is missing when text or screenshots are provided."
        )
    else:
        grounding_rule = (
            "1. Neither DOM text nor passage screenshots could be captured for this item. "
            "Answer using careful reasoning and common sense, and set 'evidence_quote': 'No passage text/image captured'."
        )

    writing_section = ""
    if is_writing_task and in_question:
        used_list = confirmed_used_words or []
        reusable_list = reusable_wrong_words or []
        writing_section = f"""
=== WRITING TASK RULES (100% ACCURACY + WORD-BANK REUSE ON WRONG ANSWERS) ===
- **GOAL:** Answer EVERY Writing question 100% accurately. Verify grammar, tense, part of speech, and surrounding sentence context before choosing a word.
- **WORD-BANK REUSE RULE (CRITICAL):**
  * Normally, each word in the Writing word bank is used once across the lesson.
  * **HOWEVER, IF A WORD WAS USED IN A PREVIOUS QUESTION THAT WAS GRADED WRONG, THAT WORD WAS NOT THE RIGHT ANSWER FOR THAT QUESTION — YOU ARE EXPLICITLY ALLOWED AND ENCOURAGED TO REUSE IT IN LATER QUESTIONS!**
  * Never avoid a word just because it appeared in an earlier step if that earlier step was graded WRONG.
  * **REUSABLE WORDS FROM PREVIOUS WRONG ANSWERS (ALLOWED TO REUSE):** {json.dumps(reusable_list, ensure_ascii=False)}
  * **CONFIRMED USED WORDS FROM CORRECT ANSWERS (DO NOT REUSE):** {json.dumps(used_list, ensure_ascii=False)}
"""

    prompt = f"""You are a smart browser agent operating Wiseman English Builder across multiple lessons.

=== WORKFLOW ===
1. NAVIGATION (wiseman.com.hk/en/ -> Login -> English Builder -> Lesson Library -> Theme -> Module -> 4 Skills -> Rinse & Repeat):
   - From https://wiseman.com.hk/en/, click 'Login' (or 'Student Login' / 'English Builder') to open the Wiseman portal.
   - Inside the portal, open 'English Builder' (if needed) and click 'Lesson Library'.
   - NEVER click anything inside 'Extended Section' (including 'Extended Listening', 'Extended Reading', 'Extended Speaking', 'Extended Writing', or its 'Start Lesson' button).
   - NEVER click any card whose state contains 'completed' or whose title is in ALREADY COMPLETED ITEMS. Ignore 'Service Hours' or 'Need help? Talk to us.'.
   - When 'LEVEL OF DIFFICULTY' is shown: NEVER click 'Close Popup (X)'. Click 'Challenging' (never 'Easy'), then click 'Start Lessons'.

2. ANSWERING QUESTIONS & FINISHING THE LESSON:
   - Check LESSON PROGRESS ({json.dumps(state["lesson_progress"])}).
   - **CRITICAL RULE WHEN QUESTION IS ALREADY COMPLETE / 'Submit' IS DISABLED:** If 'Submit' has state 'disabled' or 'Next Question' is already visible, the current question is ALREADY complete! **NEVER** click any answer option or 'Submit' again. Your ONLY action must be clicking 'Next Question' (or 'Results' on Student Voice).
   - **CRITICAL RULE WHEN AN OPTION ALREADY HAS 'checked':** If an answer option already has state 'checked' and 'Submit' is enabled, do NOT click the option again — click 'Submit' immediately!
   - **CRITICAL RULE FOR FILL-IN-THE-BLANK:**
     * Preserve the complete answer phrase. If the answer is `slippery slope`, never shorten it to `slippery`.
     * If the sentence has ONE input box, put the ENTIRE word or phrase into that one box, including spaces.
     * Only split a multi-word phrase when the same sentence visibly has MULTIPLE consecutive input boxes. Split across those boxes in reading order.
     * `one_word_only` is only a weak layout hint, not permission to discard words from an answer.
     * Emit one `"fill"` action for EVERY required blank box in the sentence BEFORE clicking `'Submit'`.
   - WHEN ANSWERING A NEW QUESTION ('Submit' is enabled):
     {grounding_rule}
     2. If a question says 'Refer to Text 2' (or 'Text 1' / 'Text 3') and that tab is currently unselected in VISIBLE INTERACTIVE ELEMENTS, click that Text tab first.
     3. Otherwise, select/fill ALL required answers AND click 'Submit' in the SAME "actions" list!
   - ACTION TYPES:
     * Use "action": "click" for radio buttons, multiple-choice <label> options, checkboxes, poll choices, tabs, and buttons.
     * ONLY use "action": "select" when the element's tag is literally "select".
     * Use "action": "fill" for text inputs or textareas (typed character-by-character).
   - CASE C (Current step is 'Student Voice'):
     * If 'Submit' is enabled: click ANY one of the Students' Voices poll options FIRST, followed by clicking 'Submit'.
     * If 'Submit' is disabled: click the 'Results' button!
   - CASE D ('Your Score:' screen is visible): Return status="lesson_finished" so the script clicks 'X' and moves to the next task!
{writing_section}
=== LEARNED UI KNOWLEDGE ===
{json.dumps(memory["learned_ui_rules"], indent=2)}

=== LEARNED CORRECTIONS FROM GENUINE ERRORS ONLY ===
{json.dumps(memory.get("learned_answer_corrections", [])[-30:], indent=2)}
Apply a matching correction and its lightbulb explanation when the same question or concept reappears. Never learn answer content from an intentional miss.

=== ALREADY COMPLETED ITEMS (NEVER CLICK ANY CARD MATCHING THESE) ===
{json.dumps(memory["completed_items"], indent=2)}

=== ACTIONS ALREADY TAKEN THIS SESSION ===
{json.dumps(history[-10:], indent=2)}

=== CURRENT SCREEN ===
URL: {state["url"]}
Page Type: {state["page_type"]}
Lesson Banner: {state["lesson_banner"] or "None"}
Headings: {json.dumps(state["headings"])}
Lesson Progress: {json.dumps(state["lesson_progress"])}

{content_section}

=== VISIBLE INTERACTIVE ELEMENTS ===
{json.dumps(state["elements"], indent=2, ensure_ascii=False)}

Respond with ONLY valid JSON:
{{
  "task_type": "menu_navigation | true_false | multiple_choice | fill_in_blank | multi_word_blank | dropdown_cloze | student_voice | lesson_finished",
  "evidence_quote": "Exact supporting quote from passage/transcript, or 'N/A' on menus",
  "thought": "Concise reasoning using passage/transcript evidence, word-by-word split if multi-blank, plus next button to press",
  "status": "continue" | "lesson_finished",
  "actions": [
    {{"id": <int>, "action": "click"}},
    {{"id": <int>, "action": "select", "value": "<exact option text>"}},
    {{"id": <int>, "action": "fill", "value": "<answer text>"}}
  ]
}}
Rules:
- NEVER click any element whose state includes 'disabled' or 'completed'.
- NEVER click anything related to 'Extended Section' or 'Extended Speaking/Listening/Reading/Writing'.
- Never click 'Close Popup (X)' while on 'LEVEL OF DIFFICULTY' or mid-exercise.
"""
    transcript_is_fallback = bool(yt_transcript and yt_transcript.startswith("[CAPTIONS UNAVAILABLE"))
    imgs_to_send = passage_images if (in_question and has_images and (not yt_transcript or transcript_is_fallback)) else None
    return call_ollama(prompt, model, images_b64=imgs_to_send, vram_profile=vram_profile)


def _expand_multiword_blank_actions(actions: list[dict], state: dict) -> list[dict]:
    el_lookup = {e["id"]: e for e in state["elements"]}
    targeted_ids = {act.get("id") for act in actions if act.get("action") == "fill"}

    blank_els = sorted(
        [
            e for e in state["elements"]
            if _is_text_input_tag(e.get("tag", ""))
            and "disabled" not in e.get("state", "")
        ],
        key=lambda e: (e.get("blank_index", 0), e["id"]),
    )

    expanded: list[dict] = []
    for act in actions:
        if act.get("action") != "fill":
            expanded.append(act)
            continue

        cid = act.get("id")
        meta = el_lookup.get(cid)
        val_str = str(act.get("value", "")).strip()
        words = [w for w in val_str.split() if w]

        if (
            meta
            and meta.get("total_blanks", 1) > 1
            and len(words) > 1
            and cid in [b["id"] for b in blank_els]
        ):
            start_pos = next(i for i, b in enumerate(blank_els) if b["id"] == cid)
            available_seq = [blank_els[start_pos]]
            for nxt in blank_els[start_pos + 1:]:
                if nxt["id"] in targeted_ids or "value=" in nxt.get("state", ""):
                    break
                available_seq.append(nxt)

            if len(available_seq) >= 2:
                limit = min(len(words), len(available_seq))
                print(
                    f"   -> [Auto-Split] Distributing {limit} words across "
                    f"{limit} consecutive boxes: {words[:limit]}"
                )
                for idx_offset in range(limit):
                    target_box = available_seq[idx_offset]
                    targeted_ids.add(target_box["id"])
                    expanded.append({
                        "id": target_box["id"],
                        "action": "fill",
                        "value": words[idx_offset],
                    })
                continue

        expanded.append(act)

    return expanded


def _is_explicit_nav_control(label: str) -> bool:
    low = (label or "").strip().lower()
    if re.match(r"^text\s+\d+\b", low):
        return True
    return low in {
        "next",
        "next question",
        "results",
        "result",
        "close popup (x)",
        "back to modules",
        "lesson library",
        "start lessons",
        "start lesson",
        "challenging",
    } or "chevron" in low


def execute_actions(
    page,
    actions: list[dict],
    state: dict,
    frame_map: dict,
    kinematics: HumanKinematics,
    media_tracker: MediaSessionTracker,
    pacing_style: str,
    stop_event: threading.Event | None = None,
    intentional_miss: bool = False,
) -> tuple[list[dict], bool, list[str]]:
    actions = _expand_multiword_blank_actions(actions, state)
    el_lookup = {e["id"]: e for e in state["elements"]}
    executed = []
    submitted_values: list[str] = []
    answered_in_batch = has_existing_answer(state)
    selected_single_choice = False
    submitted_now = False
    already_complete = is_question_already_complete(state)

    filled_blank_ids = {
        e["id"] for e in state["elements"]
        if (e.get("tag") == "select" or _is_text_input_tag(e.get("tag", "")))
        and ("value=" in e.get("state", "") or ('selected="' in e.get("state", "") and 'selected="--' not in e.get("state", "")))
    }
    required_blank_ids = {
        e["id"] for e in state["elements"]
        if (e.get("tag") == "select" or _is_text_input_tag(e.get("tag", "")))
        and "disabled" not in e.get("state", "")
    }

    prog = state["lesson_progress"]
    cur_step_lower = prog["current_step"].lower()
    in_question = (prog["total_questions_detected"] > 0 or bool(state["lesson_banner"])) and "student voice" not in cur_step_lower

    if in_question and not answered_in_batch and not already_complete and SIMULATE_HUMAN_TIMING:
        interruptible_sleep(get_question_think_delay(pacing_style), stop_event)

    if "student voice" in cur_step_lower and media_tracker.active:
        media_tracker.ensure_minimum_watch_completed(stop_event)

    ensure_foreground_focus(page)

    for act in actions:
        if stop_event and stop_event.is_set():
            break

        kind = act.get("action")
        cid = act.get("id")
        frame = frame_map.get(cid)
        meta = el_lookup.get(cid, {"text": f"id={cid}"})
        if not frame:
            continue

        label = meta.get("text", "")
        tag = meta.get("tag", "")
        st = meta.get("state", "")
        is_submit = label.strip().lower().startswith("submit")
        is_nav_btn = _is_explicit_nav_control(label)

        if EXTENDED_SECTION_RE.search(label):
            print(f"   -> BLOCKED click on Extended Section item [{cid}] '{label[:45]}'")
            continue

        if re.search(r"\b(?:locked|blocked)\b", f"{label} {st}", re.I):
            print(f"   -> BLOCKED click on locked item [{cid}] '{label[:45]}'")
            continue

        if "disabled" in st:
            print(f"   -> BLOCKED click on disabled [{cid}] '{label[:45]}'")
            continue

        if "completed" in st and not is_nav_btn:
            print(f"   -> BLOCKED click on already-completed item [{cid}] '{label[:45]}'")
            continue

        if already_complete and not is_nav_btn:
            print(f"   -> BLOCKED click on already-complete question [{cid}] '{label[:45]}'")
            continue

        if kind == "select" and tag != "select":
            kind = "click"

        if is_submit and not answered_in_batch:
            print("   -> BLOCKED premature 'Submit' click (no answer option was selected yet!)")
            executed.append({"text": "BLOCKED Submit (no answer selected)"})
            continue

        if is_submit and required_blank_ids and not required_blank_ids.issubset(filled_blank_ids):
            missing_cnt = len(required_blank_ids - filled_blank_ids)
            print(f"   -> BLOCKED premature 'Submit' click ({missing_cnt} blank box(es) still empty!)")
            executed.append({"text": f"BLOCKED Submit ({missing_cnt} blanks still empty)"})
            continue

        signature = _action_signature(state, meta, kind, act.get("value", ""))
        if not circuit_breaker_allows(signature):
            try: create_diagnostic_bundle("repeated-action circuit breaker", state, TELEMETRY.last_decision, page=page)
            except Exception: pass
            executed.append({"text": "BLOCKED repeated action"})
            continue
        loc = frame.locator(f'[data-ai-id="{cid}"]').first
        try:
            if kind == "click":
                if is_submit:
                    ok_to_submit, _validation = validate_pre_submit(
                        page, state, frame_map, actions, intentional_miss=intentional_miss
                    )
                    if not ok_to_submit:
                        executed.append({"text": "BLOCKED Submit (validation failed)"})
                        continue
                if is_submit and SIMULATE_HUMAN_TIMING:
                    interruptible_sleep(random.uniform(0.35, 0.85), stop_event)
                kinematics.click_locator(page, loc)
                print(f"   -> Clicked [{cid}] '{label[:55]}'")
                if is_submit:
                    submitted_now = True
                elif not is_nav_btn:
                    answered_in_batch = True
                    if label and label not in submitted_values:
                        submitted_values.append(label)
                    if meta.get("is_answer_option") and meta.get("option_type") != "checkbox":
                        selected_single_choice = True
            elif kind == "select":
                ensure_foreground_focus(page)
                loc.scroll_into_view_if_needed(timeout=3000)
                if SIMULATE_HUMAN_TIMING:
                    interruptible_sleep(random.uniform(0.18, 0.42), stop_event)
                loc.select_option(label=act["value"], timeout=5000)
                print(f"   -> Selected '{act['value']}' on [{cid}]")
                answered_in_batch = True
                filled_blank_ids.add(cid)
                sel_val = str(act["value"]).strip()
                if sel_val and sel_val not in submitted_values:
                    submitted_values.append(sel_val)
            elif kind == "fill":
                val_to_type = re.sub(r"\s+", " ", str(act["value"])).strip()
                if not val_to_type:
                    print(f"   -> BLOCKED empty fill for [{cid}]")
                    continue
                # Do not truncate phrases merely because the DOM labels an input one-word-only.
                # Some Wiseman activities use a single input for vocabulary phrases such as
                # "slippery slope" while still exposing the same generic input metadata.
                kinematics.type_text(page, loc, val_to_type)
                try:
                    actual = str(loc.input_value(timeout=2000))
                except Exception:
                    try:
                        actual = str(loc.evaluate("el => el.value ?? el.textContent ?? ''"))
                    except Exception:
                        actual = val_to_type
                if re.sub(r"\s+", " ", actual).strip() != val_to_type:
                    print(f"   -> Input verification mismatch on [{cid}] ({actual!r}); retrying exact phrase.")
                    try:
                        loc.fill(val_to_type, timeout=3000)
                        loc.dispatch_event("input")
                        loc.dispatch_event("change")
                        actual = str(loc.input_value(timeout=2000))
                    except Exception:
                        kinematics.type_text(page, loc, val_to_type)
                        try:
                            actual = str(loc.input_value(timeout=2000))
                        except Exception:
                            actual = ""
                if re.sub(r"\s+", " ", actual).strip() != val_to_type:
                    raise RuntimeError(f"Input [{cid}] did not retain complete phrase: expected {val_to_type!r}, got {actual!r}")
                print(f"   -> Typed and verified '{val_to_type}' into [{cid}]")
                answered_in_batch = True
                if val_to_type:
                    filled_blank_ids.add(cid)
                    if val_to_type not in submitted_values:
                        submitted_values.append(val_to_type)
            executed.append(meta)
            if SIMULATE_HUMAN_TIMING:
                interruptible_sleep(random.uniform(0.20, 0.48), stop_event)
        except Exception as e:
            print(f"   -> Failed action on [{cid}]: {e}")

    if selected_single_choice and not submitted_now and not already_complete:
        if not required_blank_ids or required_blank_ids.issubset(filled_blank_ids):
            sub_meta = submit_chosen_answer(
                page, state, frame_map, kinematics, media_tracker, stop_event
            )
            if sub_meta:
                executed.append(sub_meta)
                submitted_now = True

    return executed, submitted_now, submitted_values


# === AGENT WORKER ===
def run_agent_session(
    selected_model: str,
    stop_event: threading.Event,
    on_lesson_count_changed,
    on_pull_progress=None,
    get_incorrect_rate_pct=DEFAULT_INCORRECT_RATE,
    vram_profile: str = DEFAULT_VRAM_PROFILE,
) -> None:
    if sync_playwright is None:
        raise RuntimeError(
            f"Playwright is not installed in {sys.executable}. "
            f"Run: \"{sys.executable}\" -m pip install playwright youtube-transcript-api"
        )

    model = (selected_model or PREFERRED_MODEL).strip()
    memory = load_memory()

    ensure_isolated_chrome(stop_event)
    ensure_ollama_server(stop_event)
    if stop_event.is_set():
        return

    installed = get_installed_models()
    if not is_model_installed(installed, model):
        print(f"Selected model '{model}' is not installed locally yet — pulling automatically...")
        pull_ollama_model_stream(
            model,
            on_pull_progress or (lambda s, c, t: None),
            stop_event,
        )
        print(f"Model '{model}' downloaded and ready!")
        if stop_event.is_set():
            return

    vision_enabled = is_vision_model(model)
    profile = memory.get("student_profile", {})

    def _current_err_rate() -> int:
        val = get_incorrect_rate_pct() if callable(get_incorrect_rate_pct) else get_incorrect_rate_pct
        return max(0, min(100, int(val)))

    kinematics = HumanKinematics(typing_wpm=int(profile.get("typing_wpm_mean", 62)))
    media_tracker = MediaSessionTracker()
    history: list[str] = []
    session_verified_skills: set[str] = set()
    session_completed: set[str] = set()
    question_miss_decisions: dict[str, bool] = {}

    confirmed_used_words: list[str] = []
    reusable_wrong_words: list[dict] = []
    graded_q_keys: set[str] = set()
    last_submitted_words: list[str] = []
    last_submitted_step: str = ""

    def _record_grading_outcome(
        state_obj: dict,
        fallback_words: list[str],
        fallback_step: str,
        writing_active: bool,
        was_intentional_miss: bool = False,
    ) -> None:
        gr = state_obj.get("grading_result") or {}
        is_wrong = bool(gr.get("is_wrong"))
        is_correct = bool(gr.get("is_correct"))
        if not is_wrong and not is_correct:
            return

        step_label = state_obj.get("lesson_progress", {}).get("current_step") or fallback_step or "Unknown"
        q_sig = f"{step_label}::{(state_obj.get('right_question_pane') or '')[:60]}"
        if q_sig in graded_q_keys:
            return
        graded_q_keys.add(q_sig)

        dom_vals = [v for v in gr.get("submitted_values", []) if v]
        used_words = dom_vals if dom_vals else list(fallback_words)
        revealed = [v for v in gr.get("revealed_answers", []) if v]
        feedback_text = re.sub(r"\s+", " ", gr.get("feedback_text", "") or "").strip()

        TELEMETRY.questions += 1
        if is_wrong:
            TELEMETRY.incorrect += 1
            for w in used_words:
                confirmed_used_words[:] = [x for x in confirmed_used_words if x.lower() != w.lower()]
                if not any(item.get("word", "").lower() == w.lower() for item in reusable_wrong_words):
                    reusable_wrong_words.append({
                        "question": step_label,
                        "word": w,
                        "note": "Submitted on an INCORRECT question — still available to reuse!",
                    })
            for rev in revealed:
                if not any(x.lower() == rev.lower() for x in confirmed_used_words):
                    confirmed_used_words.append(rev)
                reusable_wrong_words[:] = [
                    item for item in reusable_wrong_words
                    if item.get("word", "").lower() != rev.lower()
                ]
            if not was_intentional_miss:
                question_text = (state_obj.get("right_question_pane") or "").strip()
                learned = memory.setdefault("learned_answer_corrections", [])
                dedupe_key = normalize_item_title(f"{active_lesson_id} {step_label} {question_text[:160]}")
                learned[:] = [item for item in learned if item.get("dedupe_key") != dedupe_key]
                learned.append({
                    "dedupe_key": dedupe_key,
                    "lesson": active_lesson_id,
                    "question": step_label,
                    "question_text": question_text[:700],
                    "submitted": used_words,
                    "correct_answer": revealed,
                    "explanation": feedback_text[:1800],
                    "learned_at": datetime.datetime.now().isoformat(timespec="seconds"),
                })
                if len(learned) > 250:
                    del learned[:-250]
                save_memory(memory)
                print(f"   -> [Correction Learning] Genuine mistake on {step_label}: wrong={used_words}, correct={revealed or ['shown in feedback']}.")
                if feedback_text:
                    print(f"      Lightbulb/answer feedback: {feedback_text[:420]}")
                history.append(
                    f"[LEARNED GENUINE ERROR] question={question_text[:350]!r}; wrong={used_words}; "
                    f"correct={revealed}; explanation={feedback_text[:900]!r}"
                )
            else:
                print(f"   -> [Intentional Miss] {step_label}: not added to correction memory.")

            if writing_active and used_words:
                print(
                    f"   -> [Writing Word-Bank Recovery] {step_label} graded WRONG — "
                    f"word(s) {used_words} released and ALLOWED FOR REUSE!"
                )
                history.append(
                    f"[GRADED WRONG on {step_label}] Word(s) {used_words} were INCORRECT — "
                    f"DO NOT lock them out; they are STILL UNUSED and CAN be reused!"
                )
        elif is_correct:
            TELEMETRY.correct += 1
            for w in used_words:
                reusable_wrong_words[:] = [
                    item for item in reusable_wrong_words
                    if item.get("word", "").lower() != w.lower()
                ]
                if not any(x.lower() == w.lower() for x in confirmed_used_words):
                    confirmed_used_words.append(w)
            if writing_active and used_words:
                print(
                    f"   -> [Writing Word-Bank] {step_label} graded CORRECT — "
                    f"locking used word(s) {used_words}."
                )

    cached_images: list[str] = []
    cached_yt_id = ""
    cached_yt_transcript = ""
    active_text_tab = ""
    active_lesson_id = ""
    active_theme = ""
    active_module = ""
    active_skill = ""
    active_skill_category = ""
    pacing_style = "focused"
    lesson_started_at = 0.0
    submitted_in_lesson = 0
    lessons_completed_this_run = 0
    simulated_reading_done = False
    login_notice_shown = False

    init_err_rate = _current_err_rate()
    print(
        f"Driver: {'Patchright (stealth CDP)' if USING_PATCHRIGHT else 'Playwright'} | "
        f"Selected Model: {model} (vision={'on' if vision_enabled else 'off'}) | "
        f"Run mode: unlimited | GPU mode: {vram_profile} | Error rate: {init_err_rate}%"
    )

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]

        if not any("wiseman" in (pg.url or "").lower() for pg in context.pages):
            target_pg = context.pages[0] if context.pages else context.new_page()
            target_pg.goto(WISEMAN_START_URL, wait_until="domcontentloaded")

        step = 0
        while True:
            step += 1
            if stop_event.is_set():
                print("\nAgent stopped by user.")
                break


            page, state, frame_map = observe_browser(
                context, memory, active_theme, session_completed
            )

            if is_login_screen(state):
                if not login_notice_shown:
                    print("\n[Login Required] Please log in to your Wiseman account in Chrome...")
                    login_notice_shown = True
                cleanup_dom_markers(page)
                interruptible_sleep(1.5, stop_event)
                continue
            login_notice_shown = False

            prog = state["lesson_progress"]
            total_q = prog["total_questions_detected"]
            modal_open = is_difficulty_modal_open(state)
            in_exercise = (total_q > 0 or bool(state["lesson_banner"])) and not modal_open

            if not in_exercise and not modal_open:
                if state["page_type"] == "module_list" and state["headings"]:
                    active_theme = state["headings"][0]
                    annotate_completed_menu_items(state, memory, active_theme, session_completed)
                elif state["page_type"] == "skill_list" and state["headings"]:
                    active_module = state["headings"][0]

            if state["lesson_banner"]:
                active_skill = state["lesson_banner"]
                prefix = state["lesson_banner"].split("::")[0].strip().capitalize()
                if prefix in SKILL_ORDER:
                    active_skill_category = prefix

            is_writing_task = (
                active_skill_category.lower() == "writing"
                or state.get("lesson_banner", "").strip().lower().startswith("writing")
            )

            lesson_id = state["lesson_banner"] or (f"{active_module}::{total_q}" if in_exercise else "")
            if in_exercise and lesson_id and lesson_id != active_lesson_id:
                active_lesson_id = lesson_id
                submitted_in_lesson = 0
                cached_images = []
                cached_yt_id = ""
                cached_yt_transcript = ""
                active_text_tab = ""
                simulated_reading_done = False
                question_miss_decisions.clear()
                confirmed_used_words.clear()
                reusable_wrong_words.clear()
                graded_q_keys.clear()
                last_submitted_words.clear()
                last_submitted_step = ""
                media_tracker.reset()
                lesson_started_at = time.time()

                pacing_style = random.choice(["focused", "relaxed", "careful"])
                q_label = f" ({total_q} Qs)" if total_q > 0 else ""
                acc_note = (
                    "100% accuracy (Writing mode + wrong-answer word reuse)"
                    if is_writing_task
                    else f"Error rate: {_current_err_rate()}%"
                )
                print(
                    f"\n=== Entered Lesson: {active_lesson_id}{q_label} | "
                    f"Pacing: {pacing_style} | {acc_note} ==="
                )

            if modal_open:
                if handle_difficulty_modal(page, state, frame_map, kinematics):
                    cleanup_dom_markers(page)
                    interruptible_sleep(random.uniform(0.70, 1.20), stop_event)
                    continue

            if not in_exercise and not modal_open and state["page_type"] in ("theme_list", "module_list"):
                handled_menu, chosen_title = manage_submenu_navigation(
                    page,
                    state,
                    frame_map,
                    kinematics,
                    memory,
                    active_theme,
                    session_completed,
                )
                if handled_menu:
                    if chosen_title:
                        if state["page_type"] == "theme_list":
                            active_theme = chosen_title
                        elif state["page_type"] == "module_list":
                            active_module = chosen_title
                    cleanup_dom_markers(page)
                    history.clear()
                    interruptible_sleep(random.uniform(0.75, 1.25), stop_event)
                    continue

            if not in_exercise and not modal_open and state["page_type"] == "skill_list":
                handled, chosen_skill = manage_module_skills(
                    page,
                    state,
                    frame_map,
                    kinematics,
                    memory,
                    active_theme,
                    active_module,
                    session_verified_skills,
                    session_completed,
                )
                if handled:
                    if chosen_skill:
                        active_skill_category = chosen_skill
                    cleanup_dom_markers(page)
                    history.clear()
                    interruptible_sleep(random.uniform(0.65, 1.15), stop_event)
                    continue

            if in_exercise:
                already_done, reason = is_lesson_already_finished(state, submitted_in_lesson)
                if already_done:
                    print(f"\n[Bailout] Task already finished ({reason}). Clicking 'X' to pick another task...")
                    full_tag = " :: ".join(x for x in (active_theme, active_module, active_skill) if x)
                    record_completed(
                        memory,
                        [full_tag or active_skill],
                        session_completed=session_completed,
                    )
                    if active_skill_category:
                        session_verified_skills.add(f"{active_theme}::{active_module}::{active_skill_category}")
                    if not close_overlay_and_exit(page, state, frame_map, kinematics):
                        create_diagnostic_bundle("score-screen X close failed", state, TELEMETRY.last_decision, page=page)
                        stop_event.set()
                        break
                    cleanup_dom_markers(page)
                    media_tracker.reset()
                    active_lesson_id = ""
                    cached_images = []
                    cached_yt_transcript = ""
                    history.clear()
                    interruptible_sleep(random.uniform(1.0, 1.8), stop_event)
                    continue

            if in_exercise and submitted_in_lesson > 0 and is_score_screen(state):
                lessons_completed_this_run += 1
                elapsed_lesson = time.time() - lesson_started_at if lesson_started_at else 0.0
                full_tag = " :: ".join(x for x in (active_theme, active_module, active_skill) if x)
                print(
                    f"\n=== Lesson #{lessons_completed_this_run} Complete ({elapsed_lesson:.0f}s)! "
                    f"Clicking 'X' to return to submenus... ==="
                )
                record_completed(
                    memory,
                    [full_tag or active_skill],
                    lesson_name=full_tag or active_lesson_id,
                    duration_sec=elapsed_lesson,
                    session_completed=session_completed,
                )
                on_lesson_count_changed(count_lessons_today(memory))
                if active_skill_category:
                    session_verified_skills.add(f"{active_theme}::{active_module}::{active_skill_category}")
                if not close_overlay_and_exit(page, state, frame_map, kinematics):
                    create_diagnostic_bundle("score-screen X close failed", state, TELEMETRY.last_decision, page=page)
                    stop_event.set()
                    break
                cleanup_dom_markers(page)
                media_tracker.reset()
                active_lesson_id = ""
                cached_images = []
                cached_yt_transcript = ""
                history.clear()
                if SIMULATE_HUMAN_TIMING:
                    interruptible_sleep(random.uniform(2.0, 4.5), stop_event)
                continue

            if in_exercise and is_question_already_complete(state):
                _record_grading_outcome(
                    state, last_submitted_words, last_submitted_step, is_writing_task
                )
                print(f"\n--- Step {step} | Question already complete -> advancing ---")
                next_el = advance_completed_question(
                    page, state, frame_map, kinematics, media_tracker, stop_event
                )
                if next_el:
                    cleanup_dom_markers(page)
                    if SIMULATE_HUMAN_TIMING:
                        interruptible_sleep(random.uniform(0.45, 0.90), stop_event)
                    _, after_state, _ = observe_browser(context, memory, active_theme, session_completed)
                    diff_summary = summarize_diff(state, after_state)
                    history.append(f"Step {step}: Pressed ['{next_el.get('text', '')[:35]}'] -> {diff_summary}")
                    print(f"Verified Result: {diff_summary}")
                    cleanup_dom_markers(page)
                    continue

            if in_exercise and is_answer_already_chosen(state):
                print(f"\n--- Step {step} | Answer already chosen -> submitting ---")
                pre_vals = list((state.get("grading_result") or {}).get("submitted_values", []))
                sub_el = submit_chosen_answer(
                    page, state, frame_map, kinematics, media_tracker, stop_event
                )
                if sub_el:
                    submitted_in_lesson += 1
                    last_submitted_words = pre_vals
                    last_submitted_step = prog["current_step"]
                    cleanup_dom_markers(page)
                    if SIMULATE_HUMAN_TIMING:
                        interruptible_sleep(random.uniform(0.45, 0.90), stop_event)
                    _, after_state, _ = observe_browser(context, memory, active_theme, session_completed)
                    _record_grading_outcome(
                        after_state, last_submitted_words, last_submitted_step, is_writing_task
                    )
                    diff_summary = summarize_diff(state, after_state)
                    history.append(f"Step {step}: Submitted already-chosen answer ['{sub_el.get('text', '')[:35]}'] -> {diff_summary}")
                    print(f"Verified Result: {diff_summary}")
                    cleanup_dom_markers(page)
                    continue

            yt_id = state.get("youtube_video_id")
            if in_exercise and yt_id:
                # Caption failure is not a hard media failure and must never block an entire skill.
                quarantined_now, retry_now, reason_now = is_learning_item_quarantined(memory, f"youtube::{yt_id}")
                if quarantined_now and reason_now != "transcript_unavailable":
                    print(f"[Media Guard] This exact video is unavailable until {retry_now} ({reason_now}).")
                    if not close_overlay_and_exit(page, state, frame_map, kinematics):
                        create_diagnostic_bundle("overlay close verification failed", state, TELEMETRY.last_decision, page=page)
                        stop_event.set(); break
                    cleanup_dom_markers(page); media_tracker.reset(); active_lesson_id = ""; cached_yt_id = ""; cached_yt_transcript = ""; history.clear()
                    continue
                if yt_id != cached_yt_id:
                    cached_yt_id = yt_id
                    print(f"Detected YouTube video ({yt_id}). Fetching English transcript & duration...")
                    try:
                        cached_yt_transcript, est_dur = fetch_youtube_transcript_with_duration(yt_id)
                        print(f"Fetched transcript ({len(cached_yt_transcript)} chars, ~{int(est_dur)}s).")
                        media_tracker.start_playback(page, kinematics, est_dur)
                        if not simulated_reading_done:
                            lead_in = min(12.0, max(5.0, est_dur * 0.08))
                            if SIMULATE_HUMAN_TIMING:
                                print(f"Listening lead-in ({lead_in:.1f}s) before Q1...")
                                interruptible_sleep(lead_in, stop_event)
                            simulated_reading_done = True
                    except Exception as e:
                        print(f"[Warning] Could not fetch YouTube transcript ({e}). Trying built-in transcript...")
                        if try_open_builtin_transcript(page, state, frame_map, kinematics):
                            page, state, frame_map = observe_browser(context, memory, active_theme, session_completed)
                            cached_yt_transcript = state.get("left_passage_pane", "")
                        if not cached_yt_transcript:
                            print("[Video Fallback] Captions unavailable. Keeping the lesson open and using the visible video frame, question, options, and reasoning.")
                            cached_yt_transcript = "[CAPTIONS UNAVAILABLE — use attached screenshot and visible question/options; do not skip or quarantine.]"
                            media_tracker.start_playback(page, kinematics, 180.0)
                            if vision_enabled:
                                try:
                                    wait_for_passage_ready(page)
                                    cached_images = capture_passage_with_natural_scroll(page, kinematics)
                                    print(f"[Video Fallback] Captured {len(cached_images)} visual context image(s).")
                                except Exception as capture_exc:
                                    print(f"[Video Fallback] Visual capture failed ({capture_exc}); continuing with question text.")
                            simulated_reading_done = True
            elif in_exercise and not modal_open and not is_question_already_complete(state):
                switched_tab, active_text_tab = ensure_referenced_text_tab(
                    page, state, frame_map, kinematics, active_text_tab
                )
                if switched_tab:
                    cached_images = []
                    page, state, frame_map = observe_browser(context, memory, active_theme, session_completed)

                need_capture = (
                    not cached_images
                    and (vision_enabled or state.get("left_has_media") or not state.get("left_passage_pane"))
                )
                if need_capture:
                    wait_for_passage_ready(page)
                    page, state, frame_map = observe_browser(context, memory, active_theme, session_completed)
                    print("Capturing passage screenshots...")
                    cached_images = capture_passage_with_natural_scroll(page, kinematics)
                    print(f"Captured {len(cached_images)} passage screenshot(s).")
                    if not simulated_reading_done:
                        simulate_reading_delay(
                            state["left_passage_pane"],
                            len(cached_images),
                            int(profile.get("reading_wpm_mean", 300)),
                            pacing_style,
                            stop_event,
                        )
                        simulated_reading_done = True
            elif not in_exercise and not modal_open:
                cached_images = []
                cached_yt_id = ""
                cached_yt_transcript = ""
                active_text_tab = ""
                active_lesson_id = ""
                media_tracker.reset()

            cur_step_raw = prog["current_step"]
            is_student_voice = "student voice" in cur_step_raw.lower()
            in_gradable_q = (
                in_exercise
                and not modal_open
                and not is_student_voice
                and not is_writing_task
            )
            intentional_miss = False
            if in_gradable_q:
                q_step_id = (
                    cur_step_raw
                    if cur_step_raw.lower() != "unknown"
                    else (state.get("right_question_pane") or "")[:90]
                )
                q_key = f"{active_lesson_id}::{q_step_id}"
                if q_key not in question_miss_decisions:
                    err_rate = _current_err_rate()
                    roll = random.random() * 100.0
                    should_miss = (err_rate > 0) and (roll < err_rate)
                    question_miss_decisions[q_key] = should_miss
                    if should_miss:
                        print(
                            f"[Humanize] Intentional error triggered on {cur_step_raw} "
                            f"(rate={err_rate}%, roll={roll:.1f}) -> selecting plausible distractor"
                        )
                intentional_miss = question_miss_decisions[q_key]

            prog_str = f" | {cur_step_raw}/{total_q} Qs" if total_q else ""
            miss_tag = " [INTENTIONAL MISS]" if intentional_miss else (" [WRITING 100%]" if is_writing_task and in_exercise else "")
            print(f"\n--- Step {step}{prog_str}{miss_tag} | {len(state['elements'])} elements ---")

            decision = decide_next_actions(
                model,
                state,
                history,
                memory,
                cached_images,
                cached_yt_transcript,
                intentional_miss=intentional_miss,
                is_writing_task=is_writing_task,
                confirmed_used_words=confirmed_used_words,
                reusable_wrong_words=reusable_wrong_words,
                vram_profile=vram_profile,
            )
            TELEMETRY.last_decision = decision
            TELEMETRY.last_state = state
            task_type = decision.get("task_type", "")
            quote = decision.get("evidence_quote", "")
            if task_type:
                print(f"Task Type: {task_type}")
            if quote and quote != "N/A":
                print(f"Evidence: {quote}")
            print(f"AI Thought: {decision.get('thought', '')}")

            if decision.get("status") == "lesson_finished":
                lessons_completed_this_run += 1
                elapsed_lesson = time.time() - lesson_started_at if lesson_started_at else 0.0
                full_tag = " :: ".join(x for x in (active_theme, active_module, active_skill) if x)
                print(
                    f"\n=== Lesson #{lessons_completed_this_run} Complete ({elapsed_lesson:.0f}s)! "
                    f"Clicking 'X' to return to submenus... ==="
                )
                record_completed(
                    memory,
                    [full_tag or active_skill],
                    lesson_name=full_tag or active_lesson_id,
                    duration_sec=elapsed_lesson,
                    session_completed=session_completed,
                )
                on_lesson_count_changed(count_lessons_today(memory))
                if active_skill_category:
                    session_verified_skills.add(f"{active_theme}::{active_module}::{active_skill_category}")
                close_overlay_and_exit(page, state, frame_map, kinematics)
                cleanup_dom_markers(page)
                media_tracker.reset()
                active_lesson_id = ""
                cached_images = []
                cached_yt_transcript = ""
                history.clear()
                if SIMULATE_HUMAN_TIMING:
                    interruptible_sleep(random.uniform(2.0, 4.5), stop_event)
                continue

            actions = decision.get("actions", [])
            if not actions:
                print("No actions returned; stopping.")
                break

            executed, submitted_now, step_sub_vals = execute_actions(
                page, actions, state, frame_map, kinematics, media_tracker, pacing_style, stop_event,
                intentional_miss=intentional_miss,
            )
            cleanup_dom_markers(page)

            if submitted_now:
                submitted_in_lesson += 1
                last_submitted_words = step_sub_vals
                last_submitted_step = cur_step_raw
            if SIMULATE_HUMAN_TIMING:
                interruptible_sleep(random.uniform(0.45, 0.90), stop_event)

            _, after_state, _ = observe_browser(context, memory, active_theme, session_completed)
            if submitted_now:
                _record_grading_outcome(
                    after_state, last_submitted_words, last_submitted_step, is_writing_task,
                    was_intentional_miss=intentional_miss,
                )
            diff_summary = summarize_diff(state, after_state)
            pressed_desc = ", ".join(f"'{e.get('text', '')[:35]}'" for e in executed)
            history.append(f"Step {step}: Pressed [{pressed_desc}] -> {diff_summary}")
            print(f"Verified Result: {diff_summary}")
            cleanup_dom_markers(page)


# === MODERN CUSTOMTKINTER UI ===
def _find_icon_path() -> Path | None:
    for candidate in (BUNDLE_DIR / "logo.ico", BASE_DIR / "logo.ico"):
        if candidate.exists():
            return candidate
    return None


class ConsolePopupWindow:
    """Dedicated CustomTkinter pop-up console window for live setup and execution logs."""

    def __init__(self, parent: ctk.CTk, theme: dict):
        self.parent = parent
        self.theme = theme
        self.win = ctk.CTkToplevel(parent)
        icon_path = _find_icon_path()
        if icon_path:
            self.win.after(250, lambda p=str(icon_path): self.win.iconbitmap(p))
        self.win.title("Wiseman Agent — Live Console & Setup Output")
        self.win.geometry("780x460")
        self.win.minsize(580, 340)
        self.win.configure(fg_color=theme["bg_root"])
        self.win.protocol("WM_DELETE_WINDOW", self.hide)

        self.win.grid_columnconfigure(0, weight=1)
        self.win.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(self.win, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        top.grid_columnconfigure(0, weight=1)

        self.banner_lbl = ctk.CTkLabel(
            top,
            text="Live Console Output",
            text_color=theme["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w",
        )
        self.banner_lbl.grid(row=0, column=0, sticky="w")

        self.hide_btn = ctk.CTkButton(
            top,
            text="Hide Pop-up",
            command=self.hide,
            width=105,
            height=28,
            corner_radius=8,
            fg_color=theme["btn_secondary_bg"],
            hover_color=theme["btn_secondary_hover"],
            text_color=theme["btn_secondary_fg"],
            border_width=1,
            border_color=theme["btn_secondary_border"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.hide_btn.grid(row=0, column=1, sticky="e")

        self.prog_box = ctk.CTkFrame(
            self.win,
            fg_color=theme["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=theme["border"],
        )
        self.prog_box.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.prog_box.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            self.prog_box,
            height=8,
            corner_radius=4,
            fg_color=theme["bg_inset"],
            progress_color=theme["accent"],
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))

        self.status_lbl = ctk.CTkLabel(
            self.prog_box,
            text="Initializing...",
            text_color=theme["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            anchor="w",
        )
        self.status_lbl.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))

        self.text = ctk.CTkTextbox(
            self.win,
            fg_color=theme["bg_term"],
            text_color=theme["text_log"],
            border_width=1,
            border_color=theme["border"],
            corner_radius=12,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            state="disabled",
        )
        self.text.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 16))

    def apply_theme(self, theme: dict) -> None:
        self.theme = theme
        self.win.configure(fg_color=theme["bg_root"])
        self.banner_lbl.configure(text_color=theme["accent"])
        self.hide_btn.configure(
            fg_color=theme["btn_secondary_bg"],
            hover_color=theme["btn_secondary_hover"],
            text_color=theme["btn_secondary_fg"],
            border_color=theme["btn_secondary_border"],
        )
        self.prog_box.configure(fg_color=theme["bg_card"], border_color=theme["border"])
        self.progress_bar.configure(fg_color=theme["bg_inset"], progress_color=theme["accent"])
        self.status_lbl.configure(text_color=theme["text_secondary"])
        self.text.configure(
            fg_color=theme["bg_term"],
            text_color=theme["text_log"],
            border_color=theme["border"],
        )

    def show(self, banner: str | None = None) -> None:
        if banner:
            self.banner_lbl.configure(text=banner)
        self.win.deiconify()
        self.win.lift()

    def hide(self) -> None:
        self.win.withdraw()

    def set_progress(self, pct: float, status_text: str) -> None:
        self.progress_bar.set(max(0.0, min(1.0, pct / 100.0)))
        self.status_lbl.configure(text=status_text)

    def append_line(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class WisemanAgentApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        mem = load_memory()
        saved_theme = str(mem.get("theme_mode", "dark")).lower()
        self.theme_name = "light" if saved_theme == "light" else "dark"
        ctk.set_appearance_mode(self.theme_name)
        ctk.set_default_color_theme("green" if self.theme_name == "light" else "blue")

        t = self._theme()
        self.root.title("EB AI Autocomplete Control Panel")
        self.root.geometry("1280x820")
        self.root.minsize(1080, 720)
        self.root.configure(fg_color=t["bg_root"])

        self.ui_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.is_running = False
        self.is_busy_setup = False
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

        saved_model = str(mem.get("selected_model", PREFERRED_MODEL)).strip() or PREFERRED_MODEL
        self.active_model_var = ctk.StringVar(value=saved_model)
        saved_vram = str(mem.get("vram_profile", DEFAULT_VRAM_PROFILE))
        if saved_vram not in VRAM_PROFILES:
            saved_vram = DEFAULT_VRAM_PROFILE
        self.vram_profile_var = ctk.StringVar(value=saved_vram)
        self.known_models: list[str] = list(PRESET_MODELS)
        if saved_model not in self.known_models:
            self.known_models.insert(1, saved_model)

        self._engine_online = False
        self._model_ready = False
        self._run_pill_state = "idle"

        self._build_ui(mem)
        icon_path = _find_icon_path()
        if icon_path:
            self.root.after(250, lambda p=str(icon_path): self.root.iconbitmap(p))
        self.console_popup = ConsolePopupWindow(self.root, t)
        self.console_popup.show("Wiseman Agent — Startup & Live Console")

        self._closing = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Covers Alt+F4 and window-manager closes; atexit covers interpreter exits.
        atexit.register(emergency_ollama_cleanup)

        sys.stdout = LogRouter(self.ui_queue, self._orig_stdout)
        sys.stderr = LogRouter(self.ui_queue, self._orig_stderr)

        self._poll_ui_queue()
        threading.Thread(target=self._bootstrap_environment, daemon=True).start()

    def _theme(self) -> dict:
        return THEMES[self.theme_name]

    def _build_model_dropdown_values(self) -> list[str]:
        vals = [model_to_display_label(m) for m in self.known_models]
        vals.append(CUSTOM_MODEL_OPTION)
        return vals

    def _build_ui(self, mem: dict) -> None:
        t = self._theme()
        self.root.grid_columnconfigure(0, weight=0, minsize=190)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(3, weight=1)
        self.sidebar = ctk.CTkFrame(self.root, width=180, corner_radius=0, fg_color=t["bg_card"], border_width=0)
        self.sidebar.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar_expanded=True; self.sidebar_animating=False; self.sidebar_width=180
        self.sidebar_toggle=ctk.CTkButton(self.sidebar,text="‹  Hide menu",command=self._toggle_sidebar,height=38,corner_radius=9,anchor="w",fg_color="transparent",hover_color=t["bg_inset"],text_color=t["text_muted"],font=ctk.CTkFont(family="Segoe UI",size=12,weight="bold"))
        self.sidebar_toggle.grid(row=0,column=0,sticky="ew",padx=10,pady=(18,16))
        self.sidebar_buttons = []
        def add_nav(row, text, command, active=False):
            btn=ctk.CTkButton(self.sidebar, text=text, command=command, anchor="w", height=40, corner_radius=9,
                fg_color=t["accent_pill_bg"] if active else "transparent", hover_color=t["bg_inset"],
                text_color=t["accent_pill_fg"] if active else t["text_muted"], font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
            btn.grid(row=row,column=0,sticky="ew",padx=10,pady=3); btn.full_text=text; self.sidebar_buttons.append(btn); return btn
        add_nav(1,"▣  Dashboard",lambda: self._focus_dashboard(),True)
        add_nav(2,"◉  Decision Inspector",self._show_decision_inspector)
        add_nav(3,"▤  Memory Manager",self._show_memory_manager)
        add_nav(4,"▦  Lock Calendar",self._show_lock_calendar)
        add_nav(5,"◇  Hardware",self._show_hardware_panel)
        add_nav(6,"⬡  Diagnostics",self._export_diagnostics)
        add_nav(7,"⌁  Live Console",lambda: self.console_popup.show("Wiseman Agent — Live Console"))
        self.sidebar_status = ctk.CTkLabel(self.sidebar,text="Adaptive context  ON\nLocal runtime",justify="left",anchor="w",text_color=t["text_secondary"],font=ctk.CTkFont(family="Consolas",size=10))
        self.sidebar_status.grid(row=8,column=0,sticky="sew",padx=18,pady=18)
        self.sidebar.grid_rowconfigure(8,weight=1)

        # === 0. TOP HEADER BAR ===
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", padx=22, pady=(16, 12))
        header.grid_columnconfigure(0, weight=1)

        title_stack = ctk.CTkFrame(header, fg_color="transparent")
        title_stack.grid(row=0, column=0, sticky="w")

        title_line = ctk.CTkFrame(title_stack, fg_color="transparent")
        title_line.pack(anchor="w")

        self.accent_bar = ctk.CTkFrame(
            title_line, width=5, height=22, corner_radius=3, fg_color=t["accent"]
        )
        self.accent_bar.pack(side="left", padx=(0, 10))

        self.title_lbl = ctk.CTkLabel(
            title_line,
            text="EB AI Autocomplete Control Panel",
            text_color=t["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
        )
        self.title_lbl.pack(side="left")

        self.subtitle_lbl = ctk.CTkLabel(
            title_stack,
            text="LOCAL AI / FUCK ENGLISH BUILDER - peppy :3",
            text_color=t["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.subtitle_lbl.pack(anchor="w", padx=(15, 0), pady=(2, 0))

        header_right = ctk.CTkFrame(header, fg_color="transparent")
        header_right.grid(row=0, column=1, sticky="e")

        self.light_mode_var = ctk.BooleanVar(value=(self.theme_name == "light"))
        self.theme_switch = ctk.CTkSwitch(
            header_right,
            text="LIGHT" if self.theme_name == "light" else "DARK",
            variable=self.light_mode_var,
            onvalue=True,
            offvalue=False,
            command=self._on_theme_toggle,
            progress_color=t["switch_progress"],
            button_color=t["switch_btn"],
            button_hover_color=t["accent"],
            text_color=t["text_muted"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.theme_switch.pack(side="left", padx=(0, 12))

        self.driver_badge = ctk.CTkLabel(
            header_right,
            text="Stealth CDP (required)" if USING_PATCHRIGHT else "Playwright CDP",
            fg_color=t["accent_pill_bg"],
            text_color=t["accent_pill_fg"],
            corner_radius=999,
            padx=12,
            pady=4,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.driver_badge.pack(side="left")

        # === 1. TWO-COLUMN CONFIGURATION DECK ===
        deck = ctk.CTkFrame(self.root, fg_color="transparent")
        deck.grid(row=1, column=1, sticky="ew", padx=22, pady=(0, 12))
        deck.grid_columnconfigure(0, weight=1, uniform="deck")
        deck.grid_columnconfigure(1, weight=1, uniform="deck")

        # --- LEFT CARD: AI Engine & Model Selector ---
        self.engine_card = ctk.CTkFrame(
            deck,
            fg_color=t["bg_card"],
            corner_radius=16,
            border_width=1,
            border_color=t["border"],
        )
        self.engine_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.engine_card.grid_columnconfigure(0, weight=1)

        self.engine_card_title = ctk.CTkLabel(
            self.engine_card,
            text="01  AI ENGINE",
            text_color=t["text_card"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w",
        )
        self.engine_card_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))

        # Model Selector Row
        model_sel_row = ctk.CTkFrame(self.engine_card, fg_color="transparent")
        model_sel_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        model_sel_row.grid_columnconfigure(1, weight=1)

        self.model_sel_lbl = ctk.CTkLabel(
            model_sel_row,
            text="AI Model",
            text_color=t["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.model_sel_lbl.grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.selected_model_label_var = ctk.StringVar(
            value=model_to_display_label(self.active_model_var.get())
        )
        self.model_combo = ctk.CTkOptionMenu(
            model_sel_row,
            variable=self.selected_model_label_var,
            values=self._build_model_dropdown_values(),
            command=self._on_model_selected,
            height=30,
            corner_radius=8,
            fg_color=t["bg_inset"],
            button_color=t["btn_secondary_bg"],
            button_hover_color=t["btn_secondary_hover"],
            dropdown_fg_color=t["dropdown_bg"],
            dropdown_hover_color=t["dropdown_hover"],
            text_color=t["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.model_combo.grid(row=0, column=1, sticky="ew")

        self.status_panel = ctk.CTkFrame(
            self.engine_card,
            fg_color=t["bg_inset"],
            corner_radius=12,
            border_width=1,
            border_color=t["border"],
        )
        self.status_panel.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.status_panel.grid_columnconfigure(1, weight=1)

        self.ollama_key_lbl = ctk.CTkLabel(
            self.status_panel,
            text="Ollama Engine",
            text_color=t["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.ollama_key_lbl.grid(row=0, column=0, sticky="w", padx=12, pady=(9, 4))

        self.ollama_status_lbl = ctk.CTkLabel(
            self.status_panel,
            text="Checking...",
            fg_color=t["warn_pill_bg"],
            text_color=t["warn_pill_fg"],
            corner_radius=999,
            padx=10,
            pady=2,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.ollama_status_lbl.grid(row=0, column=1, sticky="e", padx=12, pady=(9, 4))

        self.model_key_lbl = ctk.CTkLabel(
            self.status_panel,
            text="Model Status",
            text_color=t["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.model_key_lbl.grid(row=1, column=0, sticky="w", padx=12, pady=(4, 9))

        self.model_status_lbl = ctk.CTkLabel(
            self.status_panel,
            text="Checking...",
            fg_color=t["warn_pill_bg"],
            text_color=t["warn_pill_fg"],
            corner_radius=999,
            padx=10,
            pady=2,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.model_status_lbl.grid(row=1, column=1, sticky="e", padx=12, pady=(4, 9))

        self.progress_bar = ctk.CTkProgressBar(
            self.engine_card,
            height=8,
            corner_radius=4,
            fg_color=t["bg_inset"],
            progress_color=t["accent"],
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 5))

        self.progress_lbl = ctk.CTkLabel(
            self.engine_card,
            text="Checking Ollama runtime & AI model...",
            text_color=t["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            anchor="w",
        )
        self.progress_lbl.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 10))

        setup_btns = ctk.CTkFrame(self.engine_card, fg_color="transparent")
        setup_btns.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 16))
        setup_btns.grid_columnconfigure((0, 1), weight=1)

        self.ollama_install_btn = ctk.CTkButton(
            setup_btns,
            text="Install / Update Ollama",
            command=self._start_ollama_github_install,
            height=34,
            corner_radius=10,
            fg_color=t["btn_secondary_bg"],
            hover_color=t["btn_secondary_hover"],
            text_color=t["btn_secondary_fg"],
            border_width=1,
            border_color=t["btn_secondary_border"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.ollama_install_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.pull_btn = ctk.CTkButton(
            setup_btns,
            text=f"Pull {self.active_model_var.get()}",
            command=self._start_model_download,
            height=34,
            corner_radius=10,
            fg_color=t["btn_primary_bg"],
            hover_color=t["btn_primary_hover"],
            text_color=t["btn_primary_fg"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.pull_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        # --- RIGHT CARD: Session & Humanization ---
        self.ctrl_card = ctk.CTkFrame(
            deck,
            fg_color=t["bg_card"],
            corner_radius=16,
            border_width=1,
            border_color=t["border"],
        )
        self.ctrl_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self.ctrl_card.grid_columnconfigure(0, weight=1)

        today_done = count_lessons_today(mem)
        saved_err_rate = int(
            mem.get("student_profile", {}).get("incorrect_rate_pct", DEFAULT_INCORRECT_RATE)
        )
        saved_err_rate = max(0, min(100, saved_err_rate))

        ctrl_hdr = ctk.CTkFrame(self.ctrl_card, fg_color="transparent")
        ctrl_hdr.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 12))
        ctrl_hdr.grid_columnconfigure(0, weight=1)

        self.ctrl_card_title = ctk.CTkLabel(
            ctrl_hdr,
            text="02  SESSION PROFILE",
            text_color=t["text_card"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w",
        )
        self.ctrl_card_title.grid(row=0, column=0, sticky="w")

        self.daily_lbl = ctk.CTkLabel(
            ctrl_hdr,
            text=f"Today: {today_done} completed",
            fg_color=t["accent_pill_bg"],
            text_color=t["accent_pill_fg"],
            corner_radius=999,
            padx=10,
            pady=2,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.daily_lbl.grid(row=0, column=1, sticky="e")
        self.gpu_panel = ctk.CTkFrame(self.ctrl_card, fg_color=t["bg_inset"], corner_radius=12, border_width=1, border_color=t["border"])
        self.gpu_panel.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.gpu_panel.grid_columnconfigure(1, weight=1)
        self.gpu_label = ctk.CTkLabel(self.gpu_panel, text="GPU MEMORY", text_color=t["text_secondary"], font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self.gpu_label.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 5))
        self.gpu_combo = ctk.CTkOptionMenu(self.gpu_panel, variable=self.vram_profile_var, values=list(VRAM_PROFILES), command=self._on_vram_profile_selected, height=30, corner_radius=8, fg_color=t["bg_card"], button_color=t["btn_secondary_bg"], button_hover_color=t["btn_secondary_hover"], dropdown_fg_color=t["dropdown_bg"], dropdown_hover_color=t["dropdown_hover"], text_color=t["text_primary"], font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self.gpu_combo.grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=(10, 5))
        self.release_vram_btn = ctk.CTkButton(self.gpu_panel, text="RELEASE", command=self._release_vram_now, width=78, height=30, corner_radius=8, fg_color=t["btn_secondary_bg"], hover_color=t["btn_secondary_hover"], text_color=t["accent"], border_width=1, border_color=t["btn_secondary_border"], font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"))
        self.release_vram_btn.grid(row=0, column=2, padx=(0, 12), pady=(10, 5))
        self.gpu_hint = ctk.CTkLabel(self.gpu_panel, text="8K context · cached for 2m", text_color=t["text_secondary"], font=ctk.CTkFont(family="Segoe UI", size=10), anchor="w")
        self.gpu_hint.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 4))
        hw = detect_hardware_capabilities()
        hw_mem=f"{hw['vram_free_gb']:.1f}/{hw['vram_total_gb']:.1f} GB free" if hw.get('vram_free_gb') else f"{hw['vram_total_gb']:.1f} GB graphics memory"
        self.hardware_lbl = ctk.CTkLabel(self.gpu_panel, text=f"{hw['gpu']} · {hw_mem} · recommended limit {hw['recommended_ctx']//1024}K", text_color=t["text_secondary"], font=ctk.CTkFont(family="Segoe UI", size=9), anchor="w")
        self.hardware_lbl.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 4))
        saved_adaptive=bool(mem.get("adaptive_context",True)); self.adaptive_var=ctk.BooleanVar(value=saved_adaptive)
        global ADAPTIVE_CONTEXT_ENABLED; ADAPTIVE_CONTEXT_ENABLED=saved_adaptive
        self.adaptive_switch=ctk.CTkSwitch(self.gpu_panel,text="Automatically choose a safe context size",variable=self.adaptive_var,command=self._on_adaptive_toggle,text_color=t["text_secondary"],progress_color=t["accent"])
        self.adaptive_switch.grid(row=3,column=0,columnspan=3,sticky="w",padx=12,pady=(2,10))
        self._refresh_gpu_hint()
        self.err_panel = ctk.CTkFrame(
            self.ctrl_card,
            fg_color=t["bg_inset"],
            corner_radius=12,
            border_width=1,
            border_color=t["border"],
        )
        self.err_panel.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        self.err_panel.grid_columnconfigure(0, weight=1)

        err_top = ctk.CTkFrame(self.err_panel, fg_color="transparent")
        err_top.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        err_top.grid_columnconfigure(0, weight=1)

        self.err_title_lbl = ctk.CTkLabel(
            err_top,
            text="Intentional Error Rate",
            text_color=t["text_muted"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.err_title_lbl.grid(row=0, column=0, sticky="w")

        self.accuracy_pill = ctk.CTkLabel(
            err_top,
            text="",
            fg_color=t["ok_pill_bg"],
            text_color=t["ok_pill_fg"],
            corner_radius=999,
            padx=10,
            pady=2,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.accuracy_pill.grid(row=0, column=1, sticky="e")

        err_ctrl = ctk.CTkFrame(self.err_panel, fg_color="transparent")
        err_ctrl.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 14))
        err_ctrl.grid_columnconfigure(0, weight=1)

        self.incorrect_rate_var = ctk.IntVar(value=saved_err_rate)
        self.error_slider = ctk.CTkSlider(
            err_ctrl,
            from_=0,
            to=100,
            number_of_steps=100,
            height=16,
            progress_color=t["accent"],
            button_color=t["switch_btn"],
            button_hover_color=t["accent"],
            command=self._on_error_slider_move,
        )
        self.error_slider.set(saved_err_rate)
        self.error_slider.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.error_entry_var = ctk.StringVar(value=str(saved_err_rate))
        self.error_entry = ctk.CTkEntry(
            err_ctrl,
            textvariable=self.error_entry_var,
            width=46,
            height=26,
            corner_radius=6,
            justify="center",
            fg_color=t["entry_bg"],
            border_color=t["entry_border"],
            text_color=t["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.error_entry.grid(row=0, column=1)
        self.error_entry.bind("<Return>", self._on_error_entry_commit)
        self.error_entry.bind("<FocusOut>", self._on_error_entry_commit)

        self.pct_lbl = ctk.CTkLabel(
            err_ctrl,
            text="%",
            text_color=t["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.pct_lbl.grid(row=0, column=2, padx=(4, 0))

        self._refresh_accuracy_pill(saved_err_rate, persist=False)

        # === 2. PRIMARY ACTION STRIP ===
        self.action_bar = ctk.CTkFrame(
            self.root,
            fg_color=t["bg_card"],
            corner_radius=14,
            border_width=1,
            border_color=t["border"],
        )
        self.action_bar.grid(row=2, column=1, sticky="ew", padx=22, pady=(0, 12))
        self.action_bar.grid_columnconfigure(2, weight=1)

        self.start_btn = ctk.CTkButton(
            self.action_bar,
            text="▶   START SESSION",
            command=self._start_agent,
            width=160,
            height=38,
            corner_radius=10,
            fg_color=t["start_bg"],
            hover_color=t["start_hover"],
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        )
        self.start_btn.grid(row=0, column=0, padx=(14, 8), pady=10)

        self.stop_btn = ctk.CTkButton(
            self.action_bar,
            text="■   STOP",
            command=self._stop_agent,
            width=110,
            height=38,
            corner_radius=10,
            fg_color=t["stop_bg"],
            hover_color=t["stop_hover"],
            text_color="#ffffff",
            text_color_disabled="#64748b",
            state="disabled",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        )
        self.stop_btn.grid(row=0, column=1, padx=(0, 8), pady=10)

        right_tools = ctk.CTkFrame(self.action_bar, fg_color="transparent")
        right_tools.grid(row=0, column=3, sticky="e", padx=(0, 14), pady=10)

        self.popup_btn = ctk.CTkButton(
            right_tools,
            text="DETACH CONSOLE",
            command=lambda: self.console_popup.show("Wiseman Agent — Live Console"),
            width=125,
            height=34,
            corner_radius=9,
            fg_color=t["btn_secondary_bg"],
            hover_color=t["btn_secondary_hover"],
            text_color=t["accent"],
            border_width=1,
            border_color=t["btn_secondary_border"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.popup_btn.pack(side="left", padx=(0, 8))

        self.clear_btn = ctk.CTkButton(
            right_tools,
            text="CLEAR",
            command=self._clear_log,
            width=95,
            height=34,
            corner_radius=9,
            fg_color=t["btn_secondary_bg"],
            hover_color=t["btn_secondary_hover"],
            text_color=t["btn_secondary_fg"],
            border_width=1,
            border_color=t["btn_secondary_border"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.clear_btn.pack(side="left")
        self.memory_btn = ctk.CTkButton(right_tools, text="MEMORY", command=self._show_memory_manager, width=86, height=34, corner_radius=9, fg_color=t["btn_secondary_bg"], hover_color=t["btn_secondary_hover"], text_color=t["btn_secondary_fg"], border_width=1, border_color=t["btn_secondary_border"])
        self.inspect_btn = ctk.CTkButton(right_tools, text="INSPECT", command=self._show_decision_inspector, width=86, height=34, corner_radius=9, fg_color=t["btn_secondary_bg"], hover_color=t["btn_secondary_hover"], text_color=t["accent"], border_width=1, border_color=t["btn_secondary_border"])
        self.diag_btn = ctk.CTkButton(right_tools, text="DIAG", command=self._export_diagnostics, width=70, height=34, corner_radius=9, fg_color=t["btn_secondary_bg"], hover_color=t["btn_secondary_hover"], text_color=t["accent"], border_width=1, border_color=t["btn_secondary_border"])

        # === 3. LIVE ACTIVITY LOG CARD ===
        self.log_card = ctk.CTkFrame(
            self.root,
            fg_color=t["bg_card"],
            corner_radius=16,
            border_width=1,
            border_color=t["border"],
        )
        self.log_card.grid(row=3, column=1, sticky="nsew", padx=22, pady=(0, 18))
        self.log_card.grid_columnconfigure(0, weight=1)
        self.log_card.grid_rowconfigure(2, weight=1)

        log_hdr = ctk.CTkFrame(self.log_card, fg_color="transparent")
        log_hdr.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 8))
        log_hdr.grid_columnconfigure(0, weight=1)

        self.log_card_title = ctk.CTkLabel(
            log_hdr,
            text="SYSTEM ACTIVITY",
            text_color=t["text_card"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w",
        )
        self.log_card_title.grid(row=0, column=0, sticky="w")

        self.run_state_pill = ctk.CTkLabel(
            log_hdr,
            text="●  Idle",
            fg_color=t["idle_pill_bg"],
            text_color=t["idle_pill_fg"],
            corner_radius=999,
            padx=10,
            pady=2,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.run_state_pill.grid(row=0, column=1, sticky="e")
        self.dashboard_lbl = ctk.CTkLabel(self.log_card, text="Q 0  ·  ✓ 0  ·  ✕ 0  ·  Retries 0  ·  Context 0K  ·  Images 0  ·  AI 0.0s", text_color=t["text_secondary"], fg_color=t["bg_inset"], corner_radius=8, anchor="w", padx=10, pady=5, font=ctk.CTkFont(family="Consolas", size=11))
        self.dashboard_lbl.grid(row=1, column=0, sticky="ew", padx=16, pady=(0,8))

        self.log_box = ctk.CTkTextbox(
            self.log_card,
            fg_color=t["bg_inset"],
            text_color=t["text_log"],
            border_width=1,
            border_color=t["border"],
            corner_radius=12,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            state="disabled",
        )
        self.log_box.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))

    # === THEME SWITCHING (DARK <-> WHITE & GREEN LIGHT MODE) ===
    def _on_theme_toggle(self) -> None:
        self.theme_name = "light" if self.light_mode_var.get() else "dark"
        ctk.set_appearance_mode(self.theme_name)
        self.theme_switch.configure(
            text="LIGHT" if self.theme_name == "light" else "DARK"
        )
        self._apply_theme()
        try:
            mem = load_memory()
            mem["theme_mode"] = self.theme_name
            save_memory(mem)
        except Exception:
            pass

    def _apply_theme(self) -> None:
        t = self._theme()
        self.root.configure(fg_color=t["bg_root"])
        self.sidebar.configure(fg_color=t["bg_card"])
        self.sidebar_status.configure(text_color=t["text_secondary"])
        for idx, btn in enumerate(self.sidebar_buttons):
            btn.configure(hover_color=t["bg_inset"], text_color=t["accent_pill_fg"] if idx == 0 else t["text_muted"], fg_color=t["accent_pill_bg"] if idx == 0 else "transparent")
        self.accent_bar.configure(fg_color=t["accent"])
        self.title_lbl.configure(text_color=t["text_primary"])
        self.subtitle_lbl.configure(text_color=t["text_secondary"])
        self.theme_switch.configure(
            progress_color=t["switch_progress"],
            button_color=t["switch_btn"],
            button_hover_color=t["accent"],
            text_color=t["text_muted"],
        )
        self.driver_badge.configure(fg_color=t["accent_pill_bg"], text_color=t["accent_pill_fg"])

        self.engine_card.configure(fg_color=t["bg_card"], border_color=t["border"])
        self.engine_card_title.configure(text_color=t["text_card"])
        self.model_sel_lbl.configure(text_color=t["text_secondary"])
        self.model_combo.configure(
            fg_color=t["bg_inset"],
            button_color=t["btn_secondary_bg"],
            button_hover_color=t["btn_secondary_hover"],
            dropdown_fg_color=t["dropdown_bg"],
            dropdown_hover_color=t["dropdown_hover"],
            text_color=t["text_primary"],
        )
        self.status_panel.configure(fg_color=t["bg_inset"], border_color=t["border"])
        self.ollama_key_lbl.configure(text_color=t["text_secondary"])
        self.model_key_lbl.configure(text_color=t["text_secondary"])
        self.progress_bar.configure(fg_color=t["bg_inset"], progress_color=t["accent"])
        self.progress_lbl.configure(text_color=t["text_secondary"])

        self.ollama_install_btn.configure(
            fg_color=t["btn_secondary_bg"],
            hover_color=t["btn_secondary_hover"],
            text_color=t["btn_secondary_fg"],
            border_color=t["btn_secondary_border"],
        )
        self.pull_btn.configure(
            fg_color=t["btn_primary_bg"],
            hover_color=t["btn_primary_hover"],
            text_color=t["btn_primary_fg"],
        )

        self.ctrl_card.configure(fg_color=t["bg_card"], border_color=t["border"])
        self.ctrl_card_title.configure(text_color=t["text_card"])
        self.daily_lbl.configure(fg_color=t["accent_pill_bg"], text_color=t["accent_pill_fg"])

        self.gpu_panel.configure(fg_color=t["bg_inset"], border_color=t["border"])
        self.gpu_label.configure(text_color=t["text_secondary"])
        self.gpu_combo.configure(fg_color=t["bg_card"], button_color=t["btn_secondary_bg"], button_hover_color=t["btn_secondary_hover"], dropdown_fg_color=t["dropdown_bg"], dropdown_hover_color=t["dropdown_hover"], text_color=t["text_primary"])
        self.release_vram_btn.configure(fg_color=t["btn_secondary_bg"], hover_color=t["btn_secondary_hover"], text_color=t["accent"], border_color=t["btn_secondary_border"])
        self.gpu_hint.configure(text_color=t["text_secondary"])
        self.hardware_lbl.configure(text_color=t["text_secondary"])
        self.adaptive_switch.configure(text_color=t["text_secondary"], progress_color=t["accent"])
        self.err_panel.configure(fg_color=t["bg_inset"], border_color=t["border"])
        self.err_title_lbl.configure(text_color=t["text_muted"])
        self.error_slider.configure(
            progress_color=t["accent"],
            button_color=t["switch_btn"],
            button_hover_color=t["accent"],
        )
        self.error_entry.configure(
            fg_color=t["entry_bg"],
            border_color=t["entry_border"],
            text_color=t["text_primary"],
        )
        self.pct_lbl.configure(text_color=t["text_secondary"])
        self._refresh_accuracy_pill(self._get_current_incorrect_rate(), persist=False)

        self.action_bar.configure(fg_color=t["bg_card"], border_color=t["border"])
        self.start_btn.configure(fg_color=t["start_bg"], hover_color=t["start_hover"])
        self.stop_btn.configure(fg_color=t["stop_bg"], hover_color=t["stop_hover"])
        self.popup_btn.configure(
            fg_color=t["btn_secondary_bg"],
            hover_color=t["btn_secondary_hover"],
            text_color=t["accent"],
            border_color=t["btn_secondary_border"],
        )
        for btn in (self.memory_btn, self.inspect_btn, self.diag_btn):
            btn.configure(fg_color=t["btn_secondary_bg"], hover_color=t["btn_secondary_hover"], border_color=t["btn_secondary_border"])
        self.dashboard_lbl.configure(fg_color=t["bg_inset"], text_color=t["text_secondary"])
        self.clear_btn.configure(
            fg_color=t["btn_secondary_bg"],
            hover_color=t["btn_secondary_hover"],
            text_color=t["btn_secondary_fg"],
            border_color=t["btn_secondary_border"],
        )

        self.log_card.configure(fg_color=t["bg_card"], border_color=t["border"])
        self.log_card_title.configure(text_color=t["text_card"])
        self.log_box.configure(
            fg_color=t["bg_inset"],
            text_color=t["text_log"],
            border_color=t["border"],
        )
        self._refresh_status_badges()
        if hasattr(self, "console_popup"):
            self.console_popup.apply_theme(t)

    def _refresh_status_badges(self) -> None:
        t = self._theme()
        if self._engine_online:
            self.ollama_status_lbl.configure(
                text="Online · 127.0.0.1:11434",
                fg_color=t["ok_pill_bg"],
                text_color=t["ok_pill_fg"],
            )
        else:
            self.ollama_status_lbl.configure(
                text="Not Installed / Offline",
                fg_color=t["err_pill_bg"],
                text_color=t["err_pill_fg"],
            )

        cur_model = self.active_model_var.get()
        if self._model_ready:
            self.model_status_lbl.configure(
                text=f"Ready · {cur_model}",
                fg_color=t["ok_pill_bg"],
                text_color=t["ok_pill_fg"],
            )
            self.pull_btn.configure(text=f"Update {cur_model}")
        else:
            self.model_status_lbl.configure(
                text=f"Missing · {cur_model}",
                fg_color=t["warn_pill_bg"],
                text_color=t["warn_pill_fg"],
            )
            self.pull_btn.configure(text=f"Pull {cur_model}")

        if self._run_pill_state == "idle":
            self.run_state_pill.configure(
                text="●  Idle", fg_color=t["idle_pill_bg"], text_color=t["idle_pill_fg"]
            )
        elif self._run_pill_state == "running":
            self.run_state_pill.configure(
                text="●  Running", fg_color=t["ok_pill_bg"], text_color=t["ok_pill_fg"]
            )
        elif self._run_pill_state == "busy":
            self.run_state_pill.configure(
                fg_color=t["accent_pill_bg"], text_color=t["accent_pill_fg"]
            )
        elif self._run_pill_state == "stopping":
            self.run_state_pill.configure(
                text="●  Stopping...", fg_color=t["warn_pill_bg"], text_color=t["warn_pill_fg"]
            )

    # === MODEL SELECTOR ===
    def _on_model_selected(self, chosen_label: str) -> None:
        if chosen_label == CUSTOM_MODEL_OPTION:
            dialog = ctk.CTkInputDialog(
                text="Enter Ollama model tag (e.g. gemma4:e4b, qwen3-vl:8b, llava:13b):",
                title="Custom Ollama Model",
            )
            custom_tag = (dialog.get_input() or "").strip()
            if not custom_tag:
                self.selected_model_label_var.set(
                    model_to_display_label(self.active_model_var.get())
                )
                return
            model_name = custom_tag
        else:
            model_name = display_label_to_model(chosen_label)

        if model_name not in self.known_models:
            self.known_models.append(model_name)
        self.model_combo.configure(values=self._build_model_dropdown_values())
        self.selected_model_label_var.set(model_to_display_label(model_name))
        self.active_model_var.set(model_name)

        try:
            mem = load_memory()
            mem["selected_model"] = model_name
            save_memory(mem)
        except Exception:
            pass

        self._append_log(f"[Model Selector] Active model set to: '{model_name}'")

        if self.is_busy_setup or self.is_running:
            self._append_log(
                f"[Model Selector] Another task is active — '{model_name}' will be checked/pulled when idle."
            )
            return

        # Automatically verify and pull the newly selected model if not installed
        threading.Thread(
            target=self._verify_and_pull_selected_model,
            args=(model_name,),
            daemon=True,
        ).start()

    def _verify_and_pull_selected_model(self, model_name: str) -> None:
        try:
            if not find_ollama_executable()[0] and not is_ollama_running():
                self.ui_queue.put(("setup_busy", (True, "Downloading Ollama from GitHub...")))
                print("[Model Selector] Ollama not found — downloading Ollama first...")
                download_and_install_ollama_from_github(
                    lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                    self.stop_event,
                )

            ensure_ollama_server(self.stop_event)
            installed = get_installed_models()
            if is_model_installed(installed, model_name):
                print(f"[Model Selector] '{model_name}' is already installed and ready!")
                self.ui_queue.put(("setup_done", (True, f"{model_name} is ready!")))
                self.ui_queue.put(("env_status", (True, True, installed)))
                return

            self.ui_queue.put(("setup_busy", (True, f"Pulling AI Model: {model_name}")))
            print(f"[Model Selector] '{model_name}' not found locally — pulling automatically...")
            pull_ollama_model_stream(
                model_name,
                lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                self.stop_event,
            )
            updated_installed = get_installed_models()
            self.ui_queue.put(("setup_done", (True, f"{model_name} pulled and ready!")))
            self.ui_queue.put(("env_status", (True, True, updated_installed)))
        except Exception as exc:
            self.ui_queue.put(("setup_done", (False, f"Failed to pull {model_name}: {exc}")))
            self.ui_queue.put(("env_status", (is_ollama_running(), False, get_installed_models())))


    def _refresh_gpu_hint(self) -> None:
        name = self.vram_profile_var.get()
        cfg = VRAM_PROFILES.get(name, VRAM_PROFILES[DEFAULT_VRAM_PROFILE])
        keep = cfg["keep_alive"]
        desc = "unloads after every response" if keep == "0s" else f"cached for {keep}"
        self.gpu_hint.configure(text=f"{cfg['num_ctx'] // 1024}K context · {desc}")

    def _on_vram_profile_selected(self, profile: str) -> None:
        if profile not in VRAM_PROFILES:
            profile = DEFAULT_VRAM_PROFILE
            self.vram_profile_var.set(profile)
        self._refresh_gpu_hint()
        mem = load_memory()
        mem["vram_profile"] = profile
        save_memory(mem)
        self._append_log(f"[GPU] Memory mode set to {profile}.")

    def _release_vram_now(self) -> None:
        model = self.active_model_var.get()
        threading.Thread(target=lambda: release_ollama_model(model), daemon=True).start()
        self._append_log(f"[GPU] Requested immediate VRAM release for {model}.")

    def _on_error_slider_move(self, raw_val: float) -> None:
        rate = max(0, min(100, int(round(float(raw_val)))))
        if self.incorrect_rate_var.get() != rate:
            self.incorrect_rate_var.set(rate)
        if self.error_entry_var.get() != str(rate):
            self.error_entry_var.set(str(rate))
        self._refresh_accuracy_pill(rate, persist=True)

    def _on_error_entry_commit(self, _event=None) -> None:
        try:
            rate = max(0, min(100, int(float(self.error_entry_var.get().strip()))))
        except Exception:
            rate = self.incorrect_rate_var.get()
        self.incorrect_rate_var.set(rate)
        self.error_entry_var.set(str(rate))
        self.error_slider.set(rate)
        self._refresh_accuracy_pill(rate, persist=True)

    def _refresh_accuracy_pill(self, rate: int, persist: bool = True) -> None:
        t = self._theme()
        target_score = 100 - rate
        if rate == 0:
            self.accuracy_pill.configure(
                text="100% target (All correct)",
                text_color=t["warn_pill_fg"],
                fg_color=t["warn_pill_bg"],
            )
        elif rate <= 35:
            self.accuracy_pill.configure(
                text=f"~{target_score}% target · Natural",
                text_color=t["ok_pill_fg"],
                fg_color=t["ok_pill_bg"],
            )
        else:
            self.accuracy_pill.configure(
                text=f"~{target_score}% target · High miss",
                text_color=t["accent_pill_fg"],
                fg_color=t["accent_pill_bg"],
            )

        if persist:
            try:
                mem = load_memory()
                mem.setdefault("student_profile", {})["incorrect_rate_pct"] = rate
                save_memory(mem)
            except Exception:
                pass

    def _get_current_incorrect_rate(self) -> int:
        try:
            return max(0, min(100, int(self.incorrect_rate_var.get())))
        except Exception:
            return DEFAULT_INCORRECT_RATE

    def _append_log(self, msg: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        if hasattr(self, "console_popup"):
            self.console_popup.append_line(msg)

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        if hasattr(self, "console_popup"):
            self.console_popup.clear()

    def _toggle_sidebar(self) -> None:
        """Smooth 180↔64 px transition with visible compact navigation symbols."""
        if self.sidebar_animating: return
        self.sidebar_animating = True
        collapsing = self.sidebar_expanded
        start, target = (180, 64) if collapsing else (64, 180)
        frames, frame_ms = 14, 16
        if not collapsing:
            self.sidebar_toggle.configure(text="‹  Hide menu", anchor="w")
            self.sidebar_toggle.grid_configure(padx=10)
            for btn in self.sidebar_buttons:
                btn.configure(text=btn.full_text, anchor="w"); btn.grid_configure(padx=10)
            self.sidebar_status.configure(text=f"Adaptive context  {'ON' if ADAPTIVE_CONTEXT_ENABLED else 'OFF'}\nLocal runtime")
        def finish():
            self.sidebar_expanded = not collapsing; self.sidebar_animating = False; self.sidebar_width = target
            self.sidebar.configure(width=target); self.root.grid_columnconfigure(0, minsize=target)
            if collapsing:
                self.sidebar_toggle.configure(text="›", anchor="center"); self.sidebar_toggle.grid_configure(padx=7)
                for btn in self.sidebar_buttons:
                    btn.configure(text=btn.full_text.split(maxsplit=1)[0], anchor="center"); btn.grid_configure(padx=7)
                self.sidebar_status.configure(text="")
            self.root.update_idletasks()
        def tick(i=0):
            t=min(1.0,i/frames); eased=t*t*(3-2*t); width=round(start+(target-start)*eased)
            self.sidebar_width=width; self.sidebar.configure(width=width); self.root.grid_columnconfigure(0,minsize=width)
            self.root.after(frame_ms,lambda:tick(i+1)) if i<frames else finish()
        tick()

    def _on_adaptive_toggle(self) -> None:
        global ADAPTIVE_CONTEXT_ENABLED
        ADAPTIVE_CONTEXT_ENABLED=bool(self.adaptive_var.get()); mem=load_memory(); mem["adaptive_context"]=ADAPTIVE_CONTEXT_ENABLED; save_memory(mem)
        self._append_log(f"[Context] Adaptive context {'enabled' if ADAPTIVE_CONTEXT_ENABLED else 'disabled'}.")
        self.sidebar_status.configure(text=(f"Adaptive context  {'ON' if ADAPTIVE_CONTEXT_ENABLED else 'OFF'}\nLocal runtime") if self.sidebar_expanded else "")

    def _focus_dashboard(self) -> None:
        self.root.deiconify(); self.root.lift(); self.log_box.focus_set()

    def _show_lock_calendar(self) -> None:
        locks=load_memory().get("locked_items", {})
        lines=["LOCK CALENDAR", ""]
        if not locks: lines.append("No future release locks are stored.")
        for key,val in sorted(locks.items(), key=lambda kv: kv[1].get("release_date","")):
            lines.append(f"{val.get('release_date','?')}  {key}")
        self._open_text_window("Lock Calendar", "\n".join(lines), "780x500")

    def _show_hardware_panel(self) -> None:
        hw=detect_hardware_capabilities(); profile=self.vram_profile_var.get(); cfg=VRAM_PROFILES.get(profile,{})
        status="Automatic context sizing is ON." if ADAPTIVE_CONTEXT_ENABLED else "Automatic context sizing is OFF. The selected GPU Memory profile is used directly."
        text=f"YOUR COMPUTER\n\n{hardware_summary(hw)}\n\nAI SETTINGS\nSelected mode: {profile}\nMaximum context in this mode: {int(cfg.get('num_ctx',4096))//1024}K\n{status}\n\nCURRENT SESSION\nQuestions handled: {TELEMETRY.snapshot()['questions']}\nAI context most recently used: {TELEMETRY.snapshot()['context']//1024}K"
        self._open_text_window("Hardware & AI memory", text, "700x500")

    def _open_text_window(self, title: str, content: str, geometry="820x560") -> None:
        win = ctk.CTkToplevel(self.root); win.title(title); win.geometry(geometry); win.configure(fg_color=self._theme()["bg_root"])
        box = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=12), wrap="word")
        box.pack(fill="both", expand=True, padx=14, pady=14); box.insert("1.0", content); box.configure(state="disabled")

    def _show_decision_inspector(self) -> None:
        content = json.dumps({"decision": TELEMETRY.last_decision, "validation": TELEMETRY.last_validation,
                              "telemetry": TELEMETRY.snapshot()}, indent=2, ensure_ascii=False)
        self._open_text_window("Decision Inspector", content)

    def _show_memory_manager(self) -> None:
        win=ctk.CTkToplevel(self.root); win.title("Saved progress and unavailable lessons"); win.geometry("920x650"); win.configure(fg_color=self._theme()["bg_root"]); win.grid_columnconfigure(0,weight=1); win.grid_rowconfigure(2,weight=1)
        ctk.CTkLabel(win,text="Saved progress",anchor="w",font=ctk.CTkFont(size=22,weight="bold")).grid(row=0,column=0,sticky="ew",padx=20,pady=(20,2))
        summary=ctk.CTkLabel(win,text="",anchor="w",justify="left",text_color=self._theme()["text_secondary"]); summary.grid(row=1,column=0,sticky="ew",padx=20,pady=(0,12))
        tabs=ctk.CTkTabview(win); tabs.grid(row=2,column=0,sticky="nsew",padx=20,pady=(0,12)); [tabs.add(x) for x in ("Upcoming releases","Try again later","Completed work")]
        boxes={};
        for name in ("Upcoming releases","Try again later","Completed work"):
            boxes[name]=ctk.CTkTextbox(tabs.tab(name),wrap="word",font=ctk.CTkFont(family="Segoe UI",size=12)); boxes[name].pack(fill="both",expand=True,padx=8,pady=8)
        bar=ctk.CTkFrame(win,fg_color="transparent"); bar.grid(row=3,column=0,sticky="ew",padx=20,pady=(0,18))
        def fill(box,text): box.configure(state="normal"); box.delete("1.0","end"); box.insert("1.0",text); box.configure(state="disabled")
        def refresh():
            mem=load_memory(); locks=mem.get("locked_items",{}); qs=mem.get("quarantined_items",{}); done=mem.get("completed_items",[])
            summary.configure(text=f"{len(done)} completed items  •  {len(locks)} future releases  •  {len(qs)} temporary skips")
            releases=[]; seen_release_rows=set()
            for key,val in sorted(locks.items(),key=lambda kv:kv[1].get("release_date","")):
                parts=[part.strip() for part in key.split("::") if part.strip()]
                cleaned=[]
                for part in parts:
                    if cleaned and (part==cleaned[-1] or part in cleaned[-1] or cleaned[-1] in part):
                        if len(part)>len(cleaned[-1]): cleaned[-1]=part
                    else: cleaned.append(part)
                friendly="  ›  ".join(cleaned)
                row_key=(val.get("release_date",""),friendly)
                if row_key in seen_release_rows: continue
                seen_release_rows.add(row_key)
                releases.append(f"Available {val.get('release_date','Unknown date')}\n{friendly}\n")
            retries=[]
            for key,val in sorted(qs.items(),key=lambda kv:kv[1].get("retry_after","")):
                friendly="  ›  ".join(part.strip() for part in key.split("::") if part.strip()); reason={"transcript_unavailable":"No transcript was available"}.get(val.get("reason"),str(val.get("reason","Temporarily unavailable")).replace("_"," ").title()); retries.append(f"Try again after {str(val.get('retry_after','')).replace('T',' ')}\n{friendly}\nReason: {reason}\n")
            completed=["  ›  ".join(part.strip() for part in str(x).split("::") if part.strip()) for x in done]
            fill(boxes["Upcoming releases"],"\n".join(releases) or "No future releases are being skipped."); fill(boxes["Try again later"],"\n".join(retries) or "Nothing is temporarily skipped."); fill(boxes["Completed work"],"\n".join(completed) or "No completed work has been saved yet.")
        def clear(name,key,msg):
            if messagebox.askyesno("Are you sure?",msg): mem=load_memory(); mem[key]={} if isinstance(mem.get(key),dict) else []; save_memory(mem); refresh()
        ctk.CTkButton(bar,text="Refresh",command=refresh,width=90).pack(side="left")
        ctk.CTkButton(bar,text="Retry temporary skips now",command=lambda:clear("q","quarantined_items","Retry every temporarily skipped lesson now?"),width=180).pack(side="left",padx=8)
        ctk.CTkButton(bar,text="Forget release dates",command=lambda:clear("l","locked_items","Remove all future-release reminders?"),width=160).pack(side="left")
        ctk.CTkButton(bar,text="Reset completed progress",command=lambda:clear("c","completed_items","Forget all saved completed work? Lessons may be revisited."),width=170,fg_color="#b91c1c").pack(side="right")
        refresh()

    def _export_diagnostics(self) -> None:
        try:
            path = create_diagnostic_bundle("manual export", TELEMETRY.last_state, TELEMETRY.last_decision)
            self._append_log(f"[Diagnostics] Bundle saved: {path}")
            messagebox.showinfo("Diagnostics exported", str(path))
        except Exception as exc:
            messagebox.showerror("Diagnostics failed", str(exc))

    def _refresh_dashboard(self) -> None:
        if not hasattr(self, "dashboard_lbl"): return
        d=TELEMETRY.snapshot(); txt=(f"Q {d['questions']}  ·  ✓ {d['correct']}  ·  ✕ {d['incorrect']}  ·  "
            f"Retries {d['ai_retries']}  ·  Blocked {d['blocked_actions']}  ·  Context {d['context']//1024}K  ·  "
            f"Images {d['images_sent']}  ·  AI {d['avg_latency']:.1f}s")
        self.dashboard_lbl.configure(text=txt)

    # === STARTUP BOOTSTRAP (AUTO-CHECK + AUTO-INSTALL OLLAMA + AUTO-PULL MODEL) ===
    def _bootstrap_environment(self) -> None:
        """Checks Ollama & selected AI model with clear console results; auto-pulls both if missing."""
        target_model = self.active_model_var.get()
        try:
            hw = detect_hardware_capabilities()
            mem_text=(f"{hw['vram_free_gb']:.1f}/{hw['vram_total_gb']:.1f} GB free" if hw.get('vram_free_gb') else f"{hw['vram_total_gb']:.1f} GB total")
            print(f"[Hardware] {hw['gpu']} | Graphics memory: {mem_text} | RAM: {hw['ram_gb']:.1f} GB | Recommended context ceiling: {hw['recommended_ctx']//1024}K")
            if hw['warning']: print(f"[Hardware] {hw['warning']}")
            print(f"[Adaptive Context] {'Enabled' if ADAPTIVE_CONTEXT_ENABLED else 'Disabled'}; change this with the switch under GPU Memory.")
            print("[Startup Check 1/3] Checking for Ollama runtime...")
            ollama_bin, _ = find_ollama_executable()
            if ollama_bin:
                print(f"[Result] Ollama executable found: {ollama_bin}")
            elif is_ollama_running():
                print("[Result] Ollama service is already running on 127.0.0.1:11434.")
            else:
                print("[Result] Ollama NOT found — starting automatic GitHub download...")
                self.ui_queue.put(("setup_busy", (True, "Downloading Ollama from GitHub...")))
                download_and_install_ollama_from_github(
                    lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                    self.stop_event,
                )
                print("[Result] Ollama downloaded and installed successfully.")

            if self.stop_event.is_set():
                return

            print("[Startup Check 2/3] Starting/verifying Ollama background server...")
            ensure_ollama_server(self.stop_event)
            print("[Result] Ollama server is ONLINE at http://127.0.0.1:11434.")

            if self.stop_event.is_set():
                return

            target_model = self.active_model_var.get()
            print(f"[Startup Check 3/3] Checking installed AI models for '{target_model}'...")
            installed = get_installed_models()
            print(f"[Result] Installed models: {installed if installed else 'None'}")

            if is_model_installed(installed, target_model):
                print(f"[Result] '{target_model}' is installed and ready!")
                self.ui_queue.put(("setup_done", (True, f"{target_model} is installed and ready!")))
                self.ui_queue.put(("env_status", (True, True, installed)))
            else:
                print(f"[Result] '{target_model}' NOT found — automatically pulling '{target_model}' now...")
                self.ui_queue.put(("setup_busy", (True, f"Pulling AI Model: {target_model}")))
                pull_ollama_model_stream(
                    target_model,
                    lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                    self.stop_event,
                )
                updated_installed = get_installed_models()
                print(f"[Result] '{target_model}' pulled successfully and ready!")
                self.ui_queue.put(("setup_done", (True, f"{target_model} downloaded and ready!")))
                self.ui_queue.put(("env_status", (True, True, updated_installed)))
        except Exception as e:
            print(f"[Startup Error] {e}")
            self.ui_queue.put(("setup_done", (False, f"Setup error: {e}")))
            self.ui_queue.put(("env_status", (is_ollama_running(), False, get_installed_models())))

    def _start_ollama_github_install(self) -> None:
        if self.is_busy_setup or self.is_running:
            return
        self.is_busy_setup = True
        self._run_pill_state = "busy"
        self.stop_event.clear()
        self._set_action_buttons_enabled(False)
        self.stop_btn.configure(state="normal")
        self.run_state_pill.configure(text="●  Installing Ollama")
        self._refresh_status_badges()
        self.console_popup.show("Downloading Ollama Runtime from GitHub...")
        self.progress_bar.set(0.0)
        self.progress_lbl.configure(text="Connecting to GitHub Releases for Ollama...")

        def _worker():
            try:
                download_and_install_ollama_from_github(
                    lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                    self.stop_event,
                )
                ensure_ollama_server(self.stop_event)
                target_model = self.active_model_var.get()
                installed = get_installed_models()
                if not is_model_installed(installed, target_model):
                    print(f"[Setup] Pulling selected model '{target_model}' automatically...")
                    pull_ollama_model_stream(
                        target_model,
                        lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                        self.stop_event,
                    )
                    installed = get_installed_models()
                ready = is_model_installed(installed, target_model)
                self.ui_queue.put(("setup_done", (True, f"Ollama & {target_model} ready!")))
                self.ui_queue.put(("env_status", (True, ready, installed)))
            except Exception as exc:
                self.ui_queue.put(("setup_done", (False, f"Ollama install failed: {exc}")))

        threading.Thread(target=_worker, daemon=True).start()

    def _start_model_download(self) -> None:
        if self.is_busy_setup or self.is_running:
            return
        target_model = self.active_model_var.get()
        self.is_busy_setup = True
        self._run_pill_state = "busy"
        self.stop_event.clear()
        self._set_action_buttons_enabled(False)
        self.stop_btn.configure(state="normal")
        self.run_state_pill.configure(text="●  Pulling Model")
        self._refresh_status_badges()
        self.console_popup.show(f"Pulling AI Model: {target_model}")
        self.progress_bar.set(0.0)
        self.progress_lbl.configure(text=f"Connecting to Ollama to pull {target_model}...")
        self._append_log(f"[Setup] Pulling {target_model}...")

        def _worker():
            try:
                if not find_ollama_executable()[0] and not is_ollama_running():
                    download_and_install_ollama_from_github(
                        lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                        self.stop_event,
                    )

                pull_ollama_model_stream(
                    target_model,
                    lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                    self.stop_event,
                )
                self.ui_queue.put(("setup_done", (True, f"{target_model} downloaded and ready!")))
                self.ui_queue.put(("env_status", (True, True, get_installed_models())))
            except Exception as exc:
                self.ui_queue.put(("setup_done", (False, f"Model pull failed: {exc}")))

        threading.Thread(target=_worker, daemon=True).start()

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        st = "normal" if enabled else "disabled"
        self.start_btn.configure(state=st)
        self.pull_btn.configure(state=st)
        self.ollama_install_btn.configure(state=st)
        self.model_combo.configure(state=st)
        self.gpu_combo.configure(state=st)

    def _start_agent(self) -> None:
        if self.is_running or self.is_busy_setup:
            return
        self.is_running = True
        TELEMETRY.reset()
        self._run_pill_state = "running"
        self.stop_event.clear()
        self._set_action_buttons_enabled(False)
        self.stop_btn.configure(state="normal")
        self._refresh_status_badges()

        chosen_model = self.active_model_var.get()
        err_rate = self._get_current_incorrect_rate()
        vram_profile = self.vram_profile_var.get()
        self.console_popup.show(f"Running Agent · Model: {chosen_model}")
        self.console_popup.set_progress(
            100, f"Model: {chosen_model} · {vram_profile} · Error rate: {err_rate}%"
        )
        self._append_log(
            f"=== Starting Agent (model={chosen_model}, GPU={vram_profile}, error rate={err_rate}%) ==="
        )

        def _worker():
            try:
                run_agent_session(
                    selected_model=chosen_model,
                    stop_event=self.stop_event,
                    on_lesson_count_changed=lambda cnt: self.ui_queue.put(("daily_count", cnt)),
                    on_pull_progress=lambda s, c, t: self.ui_queue.put(("progress", (s, c, t))),
                    get_incorrect_rate_pct=self._get_current_incorrect_rate,
                    vram_profile=vram_profile,
                )
            except Exception as exc:
                try: create_diagnostic_bundle("agent exception", TELEMETRY.last_state, TELEMETRY.last_decision, exc)
                except Exception: pass
                self.ui_queue.put(("log", f"[Error] {exc}"))
            finally:
                release_ollama_model(chosen_model)
                self.ui_queue.put(("agent_stopped", None))

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_agent(self) -> None:
        self.stop_event.set()
        self._run_pill_state = "stopping"
        self.stop_btn.configure(state="disabled")
        self._refresh_status_badges()
        self._append_log("Stopping...")

    def _on_close(self) -> None:
        """Handle the title-bar X exactly like Stop, then release Ollama VRAM before exit."""
        if self._closing:
            return
        if self.is_running or self.is_busy_setup:
            if not messagebox.askyesno("Quit", "A task is currently running. Stop it, release AI memory, and exit?"):
                return
        self._closing = True
        self.stop_event.set()
        try:
            self.root.withdraw()
        except Exception:
            pass
        # Run cleanup outside Tk's event callback so HTTP/process waits cannot freeze or skip destruction.
        def shutdown_worker():
            try:
                selected = self.active_model_var.get() if hasattr(self, "active_model_var") else ""
                if selected:
                    release_ollama_model(selected)
                release_all_ollama_models(timeout=5.0)
                stop_owned_ollama_server(timeout=5.0)
            finally:
                def finish():
                    try:
                        sys.stdout = self._orig_stdout
                        sys.stderr = self._orig_stderr
                    finally:
                        try: self.root.destroy()
                        except Exception: pass
                try: self.root.after(0, finish)
                except Exception: finish()
        threading.Thread(target=shutdown_worker, daemon=False, name="ollama-shutdown").start()

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "setup_busy":
                    busy, banner_txt = payload
                    self.is_busy_setup = busy
                    self._set_action_buttons_enabled(not busy)
                    if busy:
                        self._run_pill_state = "busy"
                        self.stop_btn.configure(state="normal")
                        self.run_state_pill.configure(text="●  Setup Busy")
                        self.console_popup.show(banner_txt)
                    else:
                        self._run_pill_state = "idle"
                        self.stop_btn.configure(state="disabled")
                    self._refresh_status_badges()
                elif kind == "env_status":
                    engine_ok, model_ok, installed_list = payload
                    self._engine_online = bool(engine_ok)
                    self._model_ready = bool(model_ok)

                    if isinstance(installed_list, list):
                        for m in installed_list:
                            if m and m not in self.known_models:
                                self.known_models.append(m)
                        self.model_combo.configure(values=self._build_model_dropdown_values())

                    self._refresh_status_badges()
                    cur_model = self.active_model_var.get()
                    if engine_ok and model_ok:
                        self.progress_bar.set(1.0)
                        self.progress_lbl.configure(text=f"{cur_model} is installed and ready to run.")
                        self.console_popup.set_progress(100, f"Ready: Ollama online & {cur_model} installed.")
                    elif engine_ok and not model_ok:
                        self.progress_lbl.configure(
                            text=f"Ollama is ready! Pulling {cur_model}..."
                        )
                elif kind == "progress":
                    status, completed, total = payload
                    if total > 0:
                        pct = min(100.0, (completed / total) * 100.0)
                        if total > 10 * 1024 * 1024:
                            mb_done = completed / (1024**2)
                            mb_tot = total / (1024**2)
                            txt = f"{status} — {pct:.1f}% ({mb_done:.0f} MB / {mb_tot:.0f} MB)"
                        else:
                            txt = f"{status} — {pct:.1f}%"
                        self.progress_bar.set(pct / 100.0)
                        self.progress_lbl.configure(text=txt)
                        self.console_popup.set_progress(pct, txt)
                    else:
                        self.progress_lbl.configure(text=f"{status}...")
                        self.console_popup.set_progress(0, f"{status}...")
                elif kind == "setup_done":
                    ok, msg = payload
                    self.is_busy_setup = False
                    self._run_pill_state = "idle"
                    self._set_action_buttons_enabled(True)
                    self.stop_btn.configure(state="disabled")
                    self._refresh_status_badges()
                    if ok:
                        self.progress_bar.set(1.0)
                        self.progress_lbl.configure(text=msg)
                        self.console_popup.set_progress(100, msg)
                        self._append_log(f"[Setup] {msg}")
                    else:
                        self.progress_lbl.configure(text=msg)
                        self.console_popup.set_progress(0, msg)
                        self._append_log(f"[Setup Error] {msg}")
                elif kind == "daily_count":
                    self.daily_lbl.configure(text=f"Today: {payload} completed")
                elif kind == "agent_stopped":
                    self.is_running = False
                    self._run_pill_state = "idle"
                    self._set_action_buttons_enabled(True)
                    self.stop_btn.configure(state="disabled")
                    self._refresh_status_badges()
                    self.console_popup.set_progress(100, "Session finished.")
                    self._append_log("=== Session finished ===")
        except queue.Empty:
            pass

        self._refresh_dashboard()
        self.root.after(100, self._poll_ui_queue)


def main():
    print("Starting Wiseman AI Control Center...")
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("wiseman.agent.gui")
    root = ctk.CTk()
    app = WisemanAgentApp(root)
    def _signal_exit(_signum, _frame):
        try: root.after(0, app._on_close)
        except Exception: emergency_ollama_cleanup()
    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try: signal.signal(sig, _signal_exit)
            except Exception: pass
    try:
        root.mainloop()
    finally:
        emergency_ollama_cleanup()


if __name__ == "__main__":
    main()

