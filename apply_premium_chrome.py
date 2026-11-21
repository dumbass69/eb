from pathlib import Path
import json, re, shutil, sys
root=Path(sys.argv[1] if len(sys.argv)>1 else r'C:\WisemanTauri')
here=Path(__file__).resolve().parent
if not (root/'package.json').exists(): raise SystemExit(f'Project not found: {root}')
# Backups
backup=root/'backup-before-premium-chrome'; backup.mkdir(exist_ok=True)
for rel in ('src/App.tsx','src/styles.css','src-tauri/tauri.conf.json','src-tauri/capabilities/default.json'):
 p=root/rel
 if p.exists(): shutil.copy2(p,backup/p.name)
# Assets
icons=root/'src-tauri/icons'; nsis=root/'src-tauri/nsis'; icons.mkdir(parents=True,exist_ok=True); nsis.mkdir(parents=True,exist_ok=True)
shutil.copy2(here/'assets/icon.ico',icons/'icon.ico'); shutil.copy2(here/'assets/icon.png',icons/'icon.png')
shutil.copy2(here/'assets/installer-header.bmp',nsis/'installer-header.bmp'); shutil.copy2(here/'assets/installer-sidebar.bmp',nsis/'installer-sidebar.bmp')
# Tauri config
p=root/'src-tauri/tauri.conf.json'; cfg=json.loads(p.read_text(encoding='utf-8'))
for w in cfg.setdefault('app',{}).setdefault('windows',[{}]):
    w['decorations']=False; w['resizable']=True; w.setdefault('shadow',True)
b=cfg.setdefault('bundle',{}); b['icon']=['icons/icon.ico','icons/icon.png']
win=b.setdefault('windows',{}); win['iconPath']='icons/icon.ico'
ns=win.setdefault('nsis',{}); ns.update({'installerIcon':'icons/icon.ico','uninstallerIcon':'icons/icon.ico','headerImage':'nsis/installer-header.bmp','sidebarImage':'nsis/installer-sidebar.bmp','installMode':'currentUser','compression':'lzma','startMenuFolder':'Wiseman Autopilot'})
p.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
# Window permissions
p=root/'src-tauri/capabilities/default.json'; cap=json.loads(p.read_text(encoding='utf-8')); perms=cap.setdefault('permissions',[])
for v in ['core:window:default','core:window:allow-close','core:window:allow-minimize','core:window:allow-toggle-maximize','core:window:allow-start-dragging']:
    if v not in perms: perms.append(v)
p.write_text(json.dumps(cap,indent=2),encoding='utf-8')
# React titlebar
p=root/'src/App.tsx'; s=p.read_text(encoding='utf-8')
if "@tauri-apps/api/window" not in s:
    lines=s.splitlines(); pos=0
    while pos<len(lines) and lines[pos].startswith('import '): pos+=1
    lines.insert(pos,"import { getCurrentWindow } from '@tauri-apps/api/window';")
    s='\n'.join(lines)+'\n'
component=r'''function AppTitleBar(){
 const win=getCurrentWindow();
 return <div className="app-titlebar" data-tauri-drag-region onDoubleClick={()=>void win.toggleMaximize()}>
   <div className="titlebar-brand" data-tauri-drag-region><img src="/logo.png"/><span data-tauri-drag-region>Wiseman Autopilot</span></div>
   <div className="window-controls">
     <button aria-label="Minimize" title="Minimize" onClick={()=>void win.minimize()}><span>−</span></button>
     <button aria-label="Maximize or restore" title="Maximize or restore" onClick={()=>void win.toggleMaximize()}><span>□</span></button>
     <button className="window-close" aria-label="Close" title="Close" onClick={()=>void win.close()}><span>×</span></button>
   </div>
 </div>
}
'''
if 'function AppTitleBar()' not in s:
    marker='export function App()'
    if marker not in s: raise SystemExit('Could not find App component')
    s=s.replace(marker,component+'\n'+marker,1)
# Put titlebar above app shell without disturbing existing application tree.
if '<AppTitleBar/>' not in s:
    start=re.search(r'return\s+<div className="app-shell">',s)
    if not start: raise SystemExit('Could not find app-shell return')
    s=s[:start.start()]+s[start.start():].replace('return <div className="app-shell">','return <div className="window-root"><AppTitleBar/><div className="app-shell">',1)
    # Close wrapper at final App return immediately before next component.
    boundary=s.find('\nfunction ',start.start()+50)
    segment=s[start.start():boundary]
    last=segment.rfind('</div>')
    if last<0: raise SystemExit('Could not close window-root')
    absolute=start.start()+last+len('</div>')
    s=s[:absolute]+'</div>'+s[absolute:]
p.write_text(s,encoding='utf-8')
# CSS
p=root/'src/styles.css'; css=p.read_text(encoding='utf-8')
if '.app-titlebar{' not in css:
 css+='''\n.window-root{height:100vh;overflow:hidden;background:var(--bg);border-radius:12px}.app-titlebar{height:36px;background:var(--panel);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;user-select:none;-webkit-user-select:none}.titlebar-brand{height:100%;display:flex;align-items:center;gap:9px;padding-left:11px;font-size:11px;font-weight:700;color:var(--text)}.titlebar-brand img{width:22px;height:22px;object-fit:cover;border-radius:7px}.window-controls{height:100%;display:flex}.window-controls button{width:46px;height:36px;border:0;border-radius:0;background:transparent;color:var(--muted);display:grid;place-items:center;cursor:pointer}.window-controls button span{font-size:17px;line-height:1;pointer-events:none}.window-controls button:hover{background:var(--soft);color:var(--text)}.window-controls .window-close:hover{background:#e81123;color:white}.window-root>.app-shell{height:calc(100vh - 36px)}\n'''
p.write_text(css,encoding='utf-8')
print('Premium installer and in-app window chrome applied.')
