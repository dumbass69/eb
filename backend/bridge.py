"""Consoleless JSON-lines bridge for the Tauri sidecar."""
import os, sys
# PyInstaller --windowed suppresses Python's wrappers, but Tauri still supplies pipe handles.
def _pipe(fd, mode):
    try: return os.fdopen(os.dup(fd), mode, buffering=1, encoding='utf-8', errors='replace')
    except Exception: return open(os.devnull, mode, encoding='utf-8')
IN=_pipe(0,'r'); OUT=_pipe(1,'w'); ERR=_pipe(2,'w')
import json, threading, traceback
from pathlib import Path
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE))
import run_ultrafast as engine
# Store mutable state outside the one-file sidecar extraction/build directory.
_appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "WisemanAutopilot"
_appdata.mkdir(parents=True, exist_ok=True)
engine.BASE_DIR = _appdata
engine.MEMORY_FILE = _appdata / "ui_memory.json"
engine.ISOLATED_PROFILE_DIR = _appdata / "chrome-profile"
engine.LOCAL_OLLAMA_DIR = _appdata / "ollama"
engine.LOCAL_OLLAMA_MODELS = _appdata / "ollama_models"
engine.DIAGNOSTICS_DIR = _appdata / "diagnostics"
SETUP_SCHEMA_VERSION = 2
lock=threading.Lock(); worker=None; stop_event=threading.Event()
PRESETS=list(engine.PRESET_MODELS)
def emit(kind,payload=None):
    with lock: OUT.write(json.dumps({'type':kind,'payload':payload},ensure_ascii=False)+'\n');OUT.flush()
class Stream:
    def __init__(self):self.buf=''
    def write(self,text):
        self.buf+=str(text)
        while '\n' in self.buf:
            line,self.buf=self.buf.split('\n',1)
            if line.strip():emit('log',line)
    def flush(self):
        if self.buf.strip():emit('log',self.buf.strip());self.buf=''
sys.stdout=Stream();sys.stderr=Stream()
def memory():return engine.load_memory()
def status():
 m=memory();t=engine.TELEMETRY.snapshot();model=m.get('selected_model',engine.PREFERRED_MODEL);profile=m.get('vram_profile',engine.DEFAULT_VRAM_PROFILE);mx=int(engine.VRAM_PROFILES.get(profile,engine.VRAM_PROFILES[engine.DEFAULT_VRAM_PROFILE])['num_ctx']);return {'running':bool(worker and worker.is_alive()),'engineOnline':engine.is_ollama_running(),'modelReady':engine.is_model_installed(engine.get_installed_models(),model),'model':model,'today':engine.count_lessons_today(m),'questions':t['questions'],'correct':t['correct'],'incorrect':t['incorrect'],'context':t['context'],'contextMax':mx,'adaptive':bool(m.get('adaptive_context',True))}
def prefs():
 m=memory();return {'thinking':m.get('thinking_mode',False),'adaptive':m.get('adaptive_context',True),'errorRate':m.get('student_profile',{}).get('incorrect_rate_pct',15),'vramProfile':m.get('vram_profile',engine.DEFAULT_VRAM_PROFILE),'theme':m.get('theme_mode','light'),'firstLaunchComplete':bool(m.get('first_launch_complete',False) and int(m.get('setup_schema_version',0))>=SETUP_SCHEMA_VERSION)}
def save(p):
 m=memory();m['thinking_mode']=bool(p.get('thinking',False));m['adaptive_context']=bool(p.get('adaptive',True));m['vram_profile']=p.get('vramProfile',engine.DEFAULT_VRAM_PROFILE);m['theme_mode']=p.get('theme','light');m.setdefault('student_profile',{})['incorrect_rate_pct']=int(p.get('errorRate',15));engine.ADAPTIVE_CONTEXT_ENABLED=bool(m['adaptive_context']);engine.save_memory(m)
def start(config):
 global worker
 if worker and worker.is_alive():return True
 save(config);stop_event.clear();m=memory();model=m.get('selected_model',engine.PREFERRED_MODEL)
 def run():
  try:engine.run_agent_session(model,stop_event,lambda _n:emit('status',status()),lambda s,c,t:emit('progress',{'status':s,'completed':c,'total':t}),lambda:int(config.get('errorRate',15)),config.get('vramProfile',engine.DEFAULT_VRAM_PROFILE),bool(config.get('thinking',False)))
  except BaseException as e:emit('log',f'[Backend Error] {e}\n{traceback.format_exc()}')
  finally:emit('status',status())
 worker=threading.Thread(target=run,daemon=True);worker.start();emit('status',status());return True
def handle(cmd,data):
 if cmd=='status':return status()
 if cmd=='prepare_environment':
  exe,_=engine.find_ollama_executable()
  if not exe and not engine.is_ollama_running(): engine.download_and_install_ollama_from_github(lambda s,c,t:emit('progress',{'status':s,'completed':c,'total':t}),stop_event)
  engine.ensure_ollama_server(stop_event);installed=engine.get_installed_models();model=installed[0] if installed else engine.PREFERRED_MODEL
  if not installed: engine.pull_ollama_model_stream(model,lambda s,c,t:emit('progress',{'status':s,'completed':c,'total':t}),stop_event)
  m=memory();m['selected_model']=model;engine.save_memory(m);return {'model':model}
 if cmd=='complete_setup':
  save(data.get('preferences') or {});m=memory();m['first_launch_complete']=True;m['setup_schema_version']=SETUP_SCHEMA_VERSION;m['wiseman_login_name']=str(data.get('username') or '').strip();pwd=str(data.get('password') or '');m['wiseman_password_dpapi']=engine._protect_secret(pwd) if pwd and hasattr(engine,'_protect_secret') else '';engine.save_memory(m);return True

 if cmd=='load_preferences':return prefs()
 if cmd=='save_preferences':save(data);return True
 if cmd=='list_models':
  installed=engine.get_installed_models();names=list(dict.fromkeys(installed+PRESETS));return [{'name':n,'installed':engine.is_model_installed(installed,n),'preferred':n==engine.PREFERRED_MODEL} for n in names]
 if cmd=='set_model':m=memory();m['selected_model']=str(data.get('model') or engine.PREFERRED_MODEL);engine.save_memory(m);emit('status',status());return True
 if cmd=='memory_data':
  m=memory();return {'completed':m.get('completed_items',[]),'quarantined':m.get('quarantined_items',{}),'corrections':m.get('learned_answer_corrections',[])}
 if cmd=='lock_calendar':
  m=memory();return [{'name':k,'releaseDate':v.get('release_date',''),'evidence':v.get('evidence','')} for k,v in sorted(m.get('locked_items',{}).items(),key=lambda x:x[1].get('release_date',''))]
 if cmd=='hardware_info':return engine.detect_hardware_capabilities()
 if cmd=='start_agent':return start(data)
 if cmd=='stop_agent':
  global worker
  stop_event.set()
  current=worker
  if current and current.is_alive(): current.join(timeout=8.0)
  worker=None
  emit('status',status())
  emit('log','Agent stopped by user.')
  return True
 raise ValueError(f'Unknown command: {cmd}')
emit('ready',status())
for line in IN:
 try:
  req=json.loads(line);emit('response',{'id':req.get('id'),'ok':True,'result':handle(req.get('cmd'),req.get('data') or {})})
 except Exception as e:emit('response',{'id':req.get('id') if 'req' in locals() else None,'ok':False,'error':str(e)})
