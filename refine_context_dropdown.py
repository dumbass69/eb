from pathlib import Path
import re, shutil, sys
root=Path(sys.argv[1] if len(sys.argv)>1 else r'C:\WisemanTauri')
app=root/'src'/'App.tsx'; cssp=root/'src'/'styles.css'
if not app.exists() or not cssp.exists(): raise SystemExit('C:\\WisemanTauri React source was not found')
backup=root/'backup-before-context-dropdown'; backup.mkdir(exist_ok=True)
shutil.copy2(app,backup/'App.tsx'); shutil.copy2(cssp,backup/'styles.css')
s=app.read_text(encoding='utf-8')
# Add Gauge/Check icons if the import is compatible.
if "from 'lucide-react'" in s:
    first=s.find("from 'lucide-react'")
    begin=s.rfind('import {',0,first); end=s.find('}',begin)
    names=s[begin+8:end]
    for icon in ('Gauge','Check','ChevronDown'):
        if icon not in names: names += ', '+icon
    s=s[:begin+8]+names+s[end:]
# Insert component before ModelSelect.
component=r'''const CONTEXT_PROFILES=[
 {value:'Eco · lowest VRAM',title:'Eco',context:'4K',detail:'Lowest VRAM · best for 4–6 GB GPUs',tone:'eco'},
 {value:'Balanced · recommended',title:'Balanced',context:'8K',detail:'Recommended for most questions',tone:'balanced',recommended:true},
 {value:'Performance · 16K',title:'Performance',context:'16K',detail:'Long passages and visual questions',tone:'performance'},
 {value:'Overkill · 32K',title:'Overkill',context:'32K',detail:'Large lessons · high VRAM use',tone:'overkill'},
 {value:'Overkill · 64K',title:'Maximum',context:'64K',detail:'Extreme context · 24 GB+ VRAM advised',tone:'maximum'}
] as const;
function ContextProfileSelect({value,onChange,adaptive}:{value:string;onChange:(v:string)=>void;adaptive:boolean}){const [open,setOpen]=useState(false);const ref=useRef<HTMLDivElement>(null);useEffect(()=>{const close=(e:MouseEvent)=>{if(!ref.current?.contains(e.target as Node))setOpen(false)};document.addEventListener('mousedown',close);return()=>document.removeEventListener('mousedown',close)},[]);const current=CONTEXT_PROFILES.find(p=>p.value===value)||CONTEXT_PROFILES[1];return <div className="context-select" ref={ref}><button type="button" className="context-trigger" onClick={()=>setOpen(v=>!v)} aria-expanded={open}><span className={'context-icon '+current.tone}><Gauge/></span><span className="context-current"><span><b>{current.title}</b><em>{current.context}</em>{current.recommended&&<i>Recommended</i>}</span><small>{adaptive?`${current.detail} · adaptive ceiling`:`${current.detail} · fixed allocation`}</small></span><ChevronDown className={open?'rotated':''}/></button><AnimatePresence>{open&&<motion.div className="context-menu" initial={{opacity:0,y:-7,scale:.985}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:-5,scale:.985}} transition={{duration:.15}}>{CONTEXT_PROFILES.map(p=><button type="button" key={p.value} className={p.value===value?'selected':''} onClick={()=>{onChange(p.value);setOpen(false)}}><span className={'context-icon '+p.tone}><Gauge/></span><span className="context-option"><span><b>{p.title}</b><em>{p.context}</em>{p.recommended&&<i>Recommended</i>}</span><small>{p.detail}</small></span>{p.value===value&&<Check className="context-check"/>}</button>)}<div className="context-note"><Info/><span>{adaptive?'Adaptive Context can use less than this maximum when a question is short.':'Adaptive Context is off, so the selected allocation is requested directly.'}</span></div></motion.div>}</AnimatePresence></div>}
'''
if 'function ContextProfileSelect(' not in s:
    marker='function ModelSelect('
    if marker not in s: raise SystemExit('ModelSelect component was not found')
    s=s.replace(marker,component+'\n'+marker,1)
# Replace native select block for exact profile options.
pat=r'''<select value=\{config\.vramProfile\} onChange=\{e=>save\(\{\.\.\.config,vramProfile:e\.target\.value\}\)\}>\s*<option>Eco · lowest VRAM</option>\s*<option>Balanced · recommended</option>\s*<option>Performance · 16K</option>\s*<option>Overkill · 32K</option>\s*<option>Overkill · 64K</option>\s*</select>'''
rep="<ContextProfileSelect value={config.vramProfile} adaptive={config.adaptive} onChange={v=>save({...config,vramProfile:v})}/>"
s,n=re.subn(pat,rep,s,count=1)
if n!=1 and '<ContextProfileSelect ' not in s: raise SystemExit('Existing context select was not found')
app.write_text(s,encoding='utf-8')
css=cssp.read_text(encoding='utf-8')
if '.context-select{' not in css:
 css+=r'''
.context-select{position:relative;z-index:12}.context-trigger{width:100%;min-height:62px;border:1px solid var(--line);background:var(--soft);color:var(--text);border-radius:14px;padding:9px 12px;display:flex;align-items:center;gap:11px;text-align:left;cursor:pointer;transition:border-color .16s,box-shadow .16s,transform .16s}.context-trigger:hover,.context-trigger[aria-expanded=true]{border-color:color-mix(in srgb,var(--accent) 58%,var(--line));box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 12%,transparent)}.context-trigger:active{transform:scale(.997)}.context-trigger>svg{width:18px;margin-left:auto;color:var(--muted);transition:transform .18s}.context-trigger>svg.rotated{transform:rotate(180deg)}.context-icon{width:37px;height:37px;min-width:37px;border-radius:11px;display:grid;place-items:center;background:var(--panel);color:var(--accent)}.context-icon svg{width:18px}.context-icon.eco{color:#059669;background:#d1fae5}.context-icon.balanced{color:#7c3aed;background:#ede9fe}.context-icon.performance{color:#2563eb;background:#dbeafe}.context-icon.overkill{color:#d97706;background:#fef3c7}.context-icon.maximum{color:#dc2626;background:#fee2e2}.context-current,.context-option{min-width:0;flex:1}.context-current>span,.context-option>span{display:flex;align-items:center;gap:8px}.context-current b,.context-option b{font-size:13px}.context-current em,.context-option em{font-style:normal;color:var(--accent);font-size:11px;font-weight:800;background:var(--panel);border:1px solid var(--line);padding:2px 6px;border-radius:999px}.context-current i,.context-option i{font-style:normal;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;color:#15803d;background:#dcfce7;padding:3px 6px;border-radius:999px}.context-current small,.context-option small{display:block;color:var(--muted);font-size:10px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.context-menu{position:absolute;left:0;right:0;top:calc(100% + 7px);background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:6px;box-shadow:0 22px 60px rgba(30,18,62,.23);overflow:hidden}.context-menu>button{width:100%;border:0;background:transparent;color:var(--text);padding:9px 10px;border-radius:11px;display:flex;align-items:center;gap:10px;text-align:left;cursor:pointer}.context-menu>button:hover,.context-menu>button.selected{background:var(--soft)}.context-check{width:17px;color:var(--accent);margin-left:auto}.context-note{display:flex;gap:8px;align-items:flex-start;margin:6px;padding:9px 10px;border-radius:10px;background:color-mix(in srgb,var(--accent) 8%,var(--panel));color:var(--muted);font-size:10px;line-height:1.4}.context-note svg{width:14px;min-width:14px;color:var(--accent)}
'''
cssp.write_text(css,encoding='utf-8')
print('Context profile selector refined.')
