# #FUCK EB

A Windows desktop automation tool for Wiseman English Builder. It combines Chrome automation, local Ollama models, visual passage reading, persistent progress memory, and a CustomTkinter control panel.



## Main features

### End-to-end lesson automation
- Opens or connects to an isolated Google Chrome profile through CDP on port `9222`.
- Uses Patchright when available, with Playwright as a fallback.
- Navigates from the Wiseman website through Login, English Builder, Lesson Library, themes, modules, skills, difficulty selection, questions, Student Voice, results, and back to the library.
- Selects the Challenging difficulty automatically.
- Runs continuously until stopped rather than using a fixed lesson cap.
- Waits for manual login when a password screen is detected.
- Keeps the browser in the foreground before input when required.

### Deterministic menu and skill navigation
- Detects theme, module, skill, portal, and exercise page types.
- Inspects theme and module cards directly instead of relying only on an AI choice.
- Picks pending cards from bottom to top.
- Handles the four main skills in this order: Listening, Reading, Writing, Speaking.
- Excludes Extended Section activities from observation and clicking.
- Skips completed, locked, quarantined, and future-release items.
- Verifies all modules before recording a theme as complete.
- Uses hierarchy-aware completion keys so completing a child does not incorrectly complete its parent.

### Local AI and model management
- Uses the local Ollama chat API at `127.0.0.1:11434`.
- Defaults to `gemma4:e4b` and supports preset or custom Ollama model tags.
- Detects whether a selected model supports vision.
- Automatically checks, starts, installs, updates, or downloads Ollama and the selected model.
- Supports a portable Ollama runtime and local model directory.
- Streams model and runtime download progress into the UI.
- Retries rejected AI requests with progressively smaller contexts and image payloads.
- Logs useful Ollama HTTP error bodies.

### GPU and context management
- Provides five memory profiles:
  - Eco: 4K context, zero-second keep-alive, up to 12 images.
  - Balanced: 8K context, two-minute keep-alive, up to 24 images.
  - Performance: 16K context, ten-minute keep-alive, up to 32 images.
  - Overkill 32K: 32K context, up to 48 images.
  - Overkill 64K: 64K context, up to 64 images.
- Detects NVIDIA, AMD, and Intel graphics hardware where Windows exposes it.
- Uses NVIDIA SMI, Windows CIM, 64-bit driver-registry values, and DirectX diagnostics as detection methods.
- Recommends a context ceiling from detected VRAM.
- Can adapt context size to prompt length, image count, and hardware limits.
- Downscales oversized screenshots before inference.
- Offers an immediate Release VRAM control.
- Unloads models after sessions and performs best-effort cleanup on Stop, window close, process exit, and termination signals.

### Passage and image handling
- Extracts passage and question text from the DOM when possible.
- Detects the actual resource pane across frames and captures only the relevant left-side region.
- Waits for text and media to load before capture.
- Captures long passages until the real bottom of the pane, using a 64-slice runaway ceiling.
- Uses approximately 18% overlap between screenshots to avoid losing boundary lines.
- Detects stalled wheel scrolling and forces DOM scroll progression.
- Avoids immediately duplicated screenshots.
- Restores the passage to the top after capture.
- Selects a bounded, representative set of passage images according to the active memory profile.
- Switches to a referenced Text 1, Text 2, or Text 3 tab before recapturing when a question requests it.

### Video and transcript handling
- Detects YouTube links and IDs from URLs, embeds, metadata, and page HTML.
- Fetches English captions and estimates media duration using `youtube-transcript-api`.
- Starts embedded playback and observes a minimum watch interval.
- Tries the Wiseman built-in Transcript or Tapescript panel when external captions fail.
- Keeps uncaptioned lessons open and falls back to visible video frames, question text, answer options, and model reasoning.
- Does not mark transcript failures as completed lessons.

### Question answering
- Supports multiple choice, true/false, radio buttons, checkboxes, dropdown cloze, text input, multi-blank phrases, and Student Voice.
- Detects already selected answers and submits without re-clicking them.
- Detects completed questions and advances directly to Next Question or Results.
- Automatically distributes a multi-word phrase across consecutive blank boxes when appropriate.
- Preserves the complete phrase when only one input box exists.
- Verifies that typed text remains in the field and retries exact entry after a mismatch.
- Requires all visible required blanks to be filled before submission.
- Uses a pre-submit validator to confirm that planned values were retained in the DOM.
- Detects grading results, submitted values, revealed answers, and feedback.
- Learns corrections from genuine mistakes while excluding deliberately incorrect answers from correction memory.

### Accuracy and humanisation controls
- Includes a configurable intentional error-rate slider from 0% to 100%.
- Chooses plausible distractors for intentional misses rather than leaving fields empty or typing nonsense.
- Keeps Writing activities in 100%-accuracy mode.
- Tracks Writing word-bank entries, locks words used in correct answers, and releases words used in wrong answers for later reuse.
- Simulates brisk curved pointer movement, dwell time, typing cadence, scrolling, reading delays, thinking delays, and media lead-in time.
- Uses interruptible sleep so Stop can respond while the worker is waiting.

### Persistent memory
- Stores completed work, lesson history, preferences, model choice, theme, VRAM profile, adaptive-context setting, release locks, temporary quarantines, theme verification, and learned answer corrections in `ui_memory.json`.
- Writes memory atomically to reduce corruption risk.
- Normalises completion titles and uses scoped theme/module/skill/lesson keys.
- Migrates ambiguous legacy completion memory without blindly trusting parent records.
- Remembers future release dates and removes expired locks automatically.
- Temporarily quarantines unavailable items with a retry time and reason.

### Safety, validation, and recovery
- Blocks clicks on disabled, completed, locked, or Extended Section controls.
- Prevents premature Submit actions.
- Uses an action circuit breaker to stop repeated unchanged clicks.
- Generates a diagnostic ZIP when important actions repeatedly fail or the agent crashes.
- Verifies score-screen and lesson-overlay closure across frames.
- Closes overlays through semantic controls, forced clicks, DOM events, top-right coordinates, or Escape.
- Preserves lesson state if closure cannot be verified.
- Uses safe ZIP extraction paths for the portable Ollama installer.

### Desktop control panel
- Provides a CustomTkinter desktop interface with dark and light themes.
- Includes model selection, custom model tags, Ollama/model status, installation and pull controls.
- Includes Start, Stop, clear log, detached live console, and session progress controls.
- Provides an animated collapsible sidebar that retains compact navigation icons.
- Shows a live dashboard with questions, correct and incorrect counts, retries, blocked actions, context, images, and average AI latency.
- Includes dedicated views for:
  - Decision Inspector
  - Memory Manager
  - Lock Calendar
  - Hardware information
  - Diagnostics export
  - Live Console
- The Memory Manager separates upcoming releases, temporary skips, and completed work, and provides reset/retry controls.

## New features relative to the first version

The following capabilities are present in `run_ultrafast.py` but absent from, or materially expanded beyond, `first version.py`.

### Application and UI
- Full CustomTkinter desktop control panel instead of a terminal-only script.
- Dark/light themes with saved preference.
- Persistent animated sidebar and compact collapsed navigation.
- Detached setup/live-console window with progress reporting.
- Live telemetry dashboard, Decision Inspector, Memory Manager, Lock Calendar, Hardware panel, and one-click diagnostics.
- Threaded worker, thread-safe log routing, responsive Stop handling, and setup/session state indicators.

### Self-contained setup
- Automatic discovery, download, safe extraction, update, startup, and shutdown of Ollama.
- Automatic model installation with streamed progress.
- GUI model selector with preset and custom model tags.
- Portable Ollama and local model-storage support.

### Resource control
- Eco, Balanced, Performance, 32K, and 64K GPU-memory profiles.
- Adaptive context sizing based on workload and detected hardware.
- Multi-method GPU/VRAM detection, including fixes for Windows AMD AdapterRAM truncation.
- Image downscaling and relevant-image selection.
- Adaptive request retry after Ollama 400, 413, 500, 503, connection, timeout, or malformed-response errors.
- Manual VRAM release plus guaranteed best-effort cleanup on normal stop and application exit.

### Navigation reliability
- First-class page-type detection.
- Dedicated deterministic theme/module card inspection.
- Dedicated four-skill card inspection and ordered completion.
- Complete exclusion of Extended Section controls.
- Release-date detection and click blocking before skill navigation.
- Future-release lock calendar and temporary item quarantine.
- Full theme verification before a theme is marked complete.
- Hierarchy-safe completion records and legacy-memory migration.
- Repeated-action circuit breaker.

### Passage and media reliability
- Resource-pane-specific clipping across nested frames.
- Passage readiness checks for text, images, canvas, and SVG.
- Capture to the actual bottom with a 64-slice safety ceiling, overlap, duplicate suppression, and stalled-scroll recovery.
- Larger per-profile image budgets, compared with the earlier fixed request behaviour.
- Automatic Text 1/Text 2/Text 3 tab switching.
- Expanded YouTube ID detection.
- Built-in transcript/tapescript fallback.
- Visual fallback for uncaptioned videos instead of abandoning and recording the lesson as completed.

### Answer execution and learning
- Explicit detection of already-complete questions and already-chosen answers.
- Robust option-state detection for Wiseman-specific wrappers.
- Multi-blank indexing, automatic phrase splitting, and complete-phrase preservation.
- Post-type value verification and exact retry.
- Pre-submit DOM validation for every required control.
- Automatic submission after a single-choice selection if the AI omitted Submit.
- DOM-based correctness detection and grading telemetry.
- Persistent correction learning from genuine mistakes.
- Writing-specific 100%-accuracy mode and word-bank reuse after wrong answers.
- Configurable intentional miss rate with plausible distractor selection.

### Completion and shutdown correctness
- Only 100% counts as completion; partial percentage badges no longer do.
- Scoped completion keys prevent child records from completing a parent theme or module.
- Score-screen closure is verified across every frame.
- Top-right score-screen X fallback by coordinates and Escape.
- Local lesson state resets only after navigation away is verified.
- Window-close cleanup unloads all resident Ollama models, stops an app-owned Ollama server, signals the worker, and registers process-exit fallbacks.

## Requirements

- Windows 10 or Windows 11
- Google Chrome
- Python 3.10 or newer recommended
- A Wiseman English Builder account
- Packages:

```bash
pip install customtkinter patchright playwright youtube-transcript-api pillow psutil
```

If Patchright is not installed, the program can fall back to Playwright. Install the Chromium automation components required by the selected browser package if the local environment requests them.

## Running

```bash
python run_ultrafast.py
```
otherwise download a precompiled version in releases
At startup, the application checks Chrome, Ollama, hardware, and the selected model. If the Wiseman login page appears, complete the login manually in Chrome and leave the browser open.

## Files and generated data

- `run_ultrafast.py`: current application.
- `first version.py`: original terminal-based baseline.
- `ui_memory.json`: persistent progress and preferences.
- `chrome-profile/`: isolated Chrome user profile.
- `ollama/`: optional portable Ollama runtime.
- `ollama_models/`: optional local model storage.
- `diagnostics/`: exported diagnostic ZIP files.

## Operational notes

- The current run mode is unlimited and continues until Stop is pressed or the program exits.
- The selected context profile is a ceiling. Adaptive context may choose a smaller value.
- Overkill modes can exceed the practical capacity of smaller GPUs. The Hardware panel shows the detected recommendation.
- The 64-image passage ceiling is a runaway safeguard. Normal capture stops as soon as the pane reports its bottom.
- Closing the window may take several seconds while the worker is signalled and Ollama models are unloaded.
