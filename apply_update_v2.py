from pathlib import Path
import re, sys, shutil
proj=Path(sys.argv[1] if len(sys.argv)>1 else r'C:\WisemanTauri')
if not (proj/'package.json').exists(): raise SystemExit(f'Project not found: {proj}')
for rel in ['src/App.tsx','src/styles.css','backend/bridge.py','backend/run_ultrafast.py','src-tauri/src/lib.rs','build-sidecar.bat','build.bat']:
 p=proj/rel
 if p.exists() and not p.with_suffix(p.suffix+'.v2.bak').exists(): shutil.copy2(p,p.with_suffix(p.suffix+'.v2.bak'))

# ----- Python: robust YouTube URL/ID parsing -----
p=proj/'backend/run_ultrafast.py'; s=p.read_text(encoding='utf-8')
# imports
s=s.replace('import urllib.request\nimport urllib.error', 'import urllib.request\nimport urllib.error\nimport urllib.parse\nimport html',1)
start=s.index('def extract_youtube_id(text: str) -> str | None:')
end=s.index('\ndef fetch_youtube_transcript_with_duration',start)
new=r'''def extract_youtube_id(text: str) -> str | None:
    """Extract a YouTube video ID from broken embeds, wrapped links, HTML, or plain IDs."""
    if not text:
        return None
    raw = html.unescape(str(text)).replace('\\/', '/')
    raw = re.sub(r'[\r\n\t]+', '', raw)
    candidates = [raw]
    candidates.extend(re.findall(r'https?://[^\s"\'<>]+', raw, re.I))
    # JSON and HTML attributes are often percent encoded or contain a nested URL.
    for value in list(candidates):
        try:
            decoded = urllib.parse.unquote(value)
            if decoded != value:
                candidates.append(decoded)
        except Exception:
            pass
    for value in candidates:
        cleaned = value.strip('()[]{}.,;\'"')
        try:
            parsed = urllib.parse.urlparse(cleaned if '://' in cleaned else 'https://' + cleaned)
            host = parsed.netloc.lower().split(':')[0]
            path = parsed.path.strip('/')
            if host.endswith('youtu.be') and path:
                vid = path.split('/')[0]
                if re.fullmatch(r'[A-Za-z0-9_-]{11}', vid): return vid
            if host.endswith('youtube.com') or host.endswith('youtube-nocookie.com'):
                query = urllib.parse.parse_qs(parsed.query)
                for key in ('v', 'vi', 'video_id', 'videoId'):
                    for vid in query.get(key, []):
                        if re.fullmatch(r'[A-Za-z0-9_-]{11}', vid): return vid
                parts = path.split('/')
                if parts and parts[0] in ('embed','shorts','live','v') and len(parts) > 1:
                    vid = parts[1]
                    if re.fullmatch(r'[A-Za-z0-9_-]{11}', vid): return vid
                # attribution_link and similar wrappers contain the real URL.
                for key in ('u','url','q'):
                    for nested in query.get(key, []):
                        found = extract_youtube_id(nested)
                        if found: return found
        except Exception:
            pass
    # Last-resort patterns for malformed JavaScript and line-wrapped site links.
    patterns = (
        r'(?:[?&](?:v|vi|video_id)=|/embed/|/shorts/|/live/|youtu\.be/)([A-Za-z0-9_-]{11})',
        r'["\'](?:video_id|videoId)["\']\s*:\s*["\']([A-Za-z0-9_-]{11})',
    )
    for pattern in patterns:
        m = re.search(pattern, raw, re.I)
        if m: return m.group(1)
    return raw if re.fullmatch(r'[A-Za-z0-9_-]{11}', raw.strip()) else None
'''
s=s[:start]+new+s[end:]
p.write_text(s,encoding='utf-8')

# ----- Python bridge: profile ceiling in status -----
p=proj/'backend/bridge.py'; b=p.read_text(encoding='utf-8')
old='return {"running":bool(worker and worker.is_alive()),"engineOnline":engine.is_ollama_running(),"modelReady":engine.is_model_installed(engine.get_installed_models(),model),"model":model,"today":engine.count_lessons_today(m),"questions":tele["questions"],"correct":tele["correct"],"incorrect":tele["incorrect"],"context":tele["context"]}'
new='profile=m.get("vram_profile",engine.DEFAULT_VRAM_PROFILE); ceiling=int(engine.VRAM_PROFILES.get(profile,engine.VRAM_PROFILES[engine.DEFAULT_VRAM_PROFILE])["num_ctx"]); return {"running":bool(worker and worker.is_alive()),"engineOnline":engine.is_ollama_running(),"modelReady":engine.is_model_installed(engine.get_installed_models(),model),"model":model,"today":engine.count_lessons_today(m),"questions":tele["questions"],"correct":tele["correct"],"incorrect":tele["incorrect"],"context":tele["context"],"contextMax":ceiling,"adaptive":bool(m.get("adaptive_context",True))}'
if old in b: b=b.replace(old,new,1)
else: print('WARNING: status return signature differed; contextMax not inserted')
p.write_text(b,encoding='utf-8')

# ----- React UI -----
p=proj/'src/App.tsx'; a=p.read_text(encoding='utf-8')
a=a.replace('context:number};','context:number;contextMax:number;adaptive:boolean};',1)
a=a.replace('context:0};','context:0,contextMax:8192,adaptive:true};',1)
# Console autoscroll: imports + ref/effect
if "useRef" not in a.split('\n',1)[0]: a=a.replace("import { useEffect, useMemo, useState } from 'react';","import { useEffect, useMemo, useRef, useState } from 'react';",1)
a=a.replace("function ActivityPage({logs,status}:{logs:string[];status:Status}){return", "function ActivityPage({logs,status}:{logs:string[];status:Status}){const end=useRef<HTMLDivElement>(null);useEffect(()=>end.current?.scrollIntoView({behavior:'smooth',block:'end'}),[logs]);return",1)
a=a.replace("{logs.length?logs.join('\\n'):'Backend events will appear here.'}</pre>","{logs.length?logs.join('\\n'):'Backend events will appear here.'}<div ref={end}/></pre>",1)
a=a.replace("<span>Context <b>{Math.round(status.context/1024)}K</b></span>","<span title={status.adaptive?'Adaptive context uses the smallest sufficient size, up to the selected profile ceiling.':'Adaptive context is off, so the selected profile size is requested directly.'}>Context used <b>{Math.round(status.context/1024)}K / {Math.round(status.contextMax/1024)}K max</b></span>",1)
# Popup autoscroll
old="function ConsolePopup({logs,close,clear}:{logs:string[];close:()=>void;clear:()=>void}){return"
new="function ConsolePopup({logs,close,clear}:{logs:string[];close:()=>void;clear:()=>void}){const end=useRef<HTMLDivElement>(null);useEffect(()=>end.current?.scrollIntoView({behavior:'smooth',block:'end'}),[logs]);return"
a=a.replace(old,new,1)
a=a.replace("{logs.length?logs.join('\\n'):'Waiting for backend output…'}</pre>","{logs.length?logs.join('\\n'):'Waiting for backend output…'}<div ref={end}/></pre>",1)
# Remove appearance sentence
for text in ['<p className="muted">Theme changes animate without rebuilding or destroying the interface.</p>','Theme changes animate without rebuilding or destroying the interface.']:
 a=a.replace(text,'')
# Add tooltip intros on settings switches (native hover + info chip)
a=a.replace('<Switch label="AI Thinking Mode" value={config.thinking}', '<div className="setting-help" title="Lets supported Ollama models perform a private reasoning pass before returning the structured answer. This is slower but can improve inference, author-purpose, and multi-step questions."><span className="info-chip">i</span><Switch label="AI Thinking Mode" value={config.thinking}',1)
a=a.replace('onChange={v=>save({...config,thinking:v})}/><Switch label="Adaptive Context"', 'onChange={v=>save({...config,thinking:v})}/></div><div className="setting-help" title="Automatically selects the smallest useful context for each request, capped by the GPU memory profile. A 32K profile may report 4K when only 4K is needed."><span className="info-chip">i</span><Switch label="Adaptive Context"',1)
a=a.replace('onChange={v=>save({...config,adaptive:v})}/></Card></div>}', 'onChange={v=>save({...config,adaptive:v})}/></div></Card></div>}',1)
p.write_text(a,encoding='utf-8')

# CSS
p=proj/'src/styles.css'; css=p.read_text(encoding='utf-8')
css += '\n.setting-help{position:relative;padding-left:27px}.setting-help .switch-row{margin:0}.info-chip{position:absolute;left:0;top:50%;transform:translateY(-50%);width:18px;height:18px;border-radius:50%;display:grid;place-items:center;background:var(--soft);border:1px solid var(--line);color:var(--accent);font-size:11px;font-weight:800;cursor:help}.console>div{height:1px}.popup-console{overflow:auto}\n'
p.write_text(css,encoding='utf-8')

# Hide PyInstaller sidecar console: both build scripts
for name in ('build-sidecar.bat','build.bat'):
 p=proj/name
 if p.exists():
  x=p.read_text(encoding='utf-8',errors='ignore').replace('--onefile --console --name wiseman-backend','--onefile --windowed --name wiseman-backend')
  p.write_text(x,encoding='utf-8')
print('V2 update applied.')
