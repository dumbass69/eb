from pathlib import Path
import json, re, shutil, sys
root=Path(sys.argv[1] if len(sys.argv)>1 else r'C:\WisemanTauri'); here=Path(__file__).resolve().parent
if not (root/'package.json').exists(): raise SystemExit(f'Project not found: {root}')
backup=root/'backup-before-stop-installer-fix'; backup.mkdir(exist_ok=True)
for rel in ('src/App.tsx','backend/bridge.py','src-tauri/tauri.conf.json'):
 p=root/rel
 if p.exists(): shutil.copy2(p,backup/p.name)
# Correct Tauri v2 icon/NSIS schema. iconPath is not valid under bundle.windows.
p=root/'src-tauri/tauri.conf.json'; cfg=json.loads(p.read_text(encoding='utf-8'))
b=cfg.setdefault('bundle',{}); b['icon']=['icons/icon.ico','icons/icon.png']
windows=b.setdefault('windows',{}); windows.pop('iconPath',None)
nsis=windows.setdefault('nsis',{})
nsis.update({'installerIcon':'icons/icon.ico','uninstallerIcon':'icons/icon.ico','headerImage':'nsis/installer-header.bmp','sidebarImage':'nsis/installer-sidebar.bmp','installMode':'currentUser','compression':'lzma','startMenuFolder':'Wiseman Autopilot'})
p.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
icons=root/'src-tauri/icons'; art=root/'src-tauri/nsis'; icons.mkdir(parents=True,exist_ok=True); art.mkdir(parents=True,exist_ok=True)
for name,dst in [('icon.ico',icons),('icon.png',icons),('installer-header.bmp',art),('installer-sidebar.bmp',art)]: shutil.copy2(here/'assets'/name,dst/name)
# Make Stop optimistic and authoritative in React.
p=root/'src/App.tsx'; s=p.read_text(encoding='utf-8')
# Replace the one-line toggle definition regardless of minor formatting.
pattern=r"const toggle=\(\)=>invoke\(status\.running\?'stop_agent':'start_agent',\{config\}\)\.catch\(e=>setLogs\(v=>\[\.\.\.v,`\[Agent\] \$\{e\}`\]\)\);"
replacement="""const toggle=async()=>{\n  if(status.running){\n    setStatus(current=>({...current,running:false}));\n    try{await invoke('stop_agent')}catch(e){setStatus(current=>({...current,running:true}));setLogs(v=>[...v,`[Agent] ${e}`])}\n  }else{\n    setStatus(current=>({...current,running:true}));\n    try{await invoke('start_agent',{config})}catch(e){setStatus(current=>({...current,running:false}));setLogs(v=>[...v,`[Agent] ${e}`])}\n  }\n};"""
s,n=re.subn(pattern,replacement,s,count=1)
if n!=1:
 # Broad fallback between toggle and nav declarations.
 s,n=re.subn(r"const toggle=.*?;\s*\n\s*const nav=",replacement+'\n const nav=',s,count=1,flags=re.S)
if n!=1: raise SystemExit('Could not locate toggle handler in App.tsx')
p.write_text(s,encoding='utf-8')
# Backend stop waits briefly, emits final false status, and clears worker handle.
p=root/'backend/bridge.py'; b=p.read_text(encoding='utf-8')
old="if cmd=='stop_agent':stop_event.set();return True"
new="""if cmd=='stop_agent':\n  global worker\n  stop_event.set()\n  current=worker\n  if current and current.is_alive(): current.join(timeout=8.0)\n  worker=None\n  emit('status',status())\n  emit('log','Agent stopped by user.')\n  return True"""
if old in b: b=b.replace(old,new,1)
else:
 b,n=re.subn(r"if cmd==['\"]stop_agent['\"]:[^\n]*(?:\n(?:\s{2,}[^\n]+)){0,5}",new,b,count=1)
 if n!=1: raise SystemExit('Could not locate stop_agent handler in bridge.py')
p.write_text(b,encoding='utf-8')
print('Stop-state and installer schema fixes applied.')
