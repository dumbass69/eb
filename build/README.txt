This is a clean replacement, not another incremental patch.

Run APPLY_CLEAN_REBUILD.bat. It assumes C:\WisemanTauri.

Fixes:
- Python sidecar is packaged with the PyInstaller windowed bootloader, so no black console/taskbar window is created. bridge.py explicitly reopens Tauri's inherited stdin/stdout pipe handles so IPC still works.
- Settings is replaced with balanced, standalone JSX, preventing the white-screen runtime crash.
- Model selector always includes all PRESET_MODELS from run_ultrafast.py, plus installed Ollama models. Installed status is shown with a green dot and missing models pull automatically when the agent launches.
- Polished animated model menu.
- Live Activity and popup console smooth auto-scroll.
- Appearance filler sentence removed.
- Thinking Mode and Adaptive Context have hover/focus explanations.
- Live Activity shows actual context and selected ceiling separately.
- Memory Manager, Lock Calendar, Hardware and popup console are included.

The script backs up the replaced source files to C:\WisemanTauri\backup-before-clean-rebuild.
