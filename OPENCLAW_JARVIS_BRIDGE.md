# OpenClaw JARVIS Bridge

Use this from OpenClaw sessions when you want OpenClaw to report into the local JARVIS HUD.

## Location

`C:\Users\jamie\jarvis_clean\jarvis-final\openclaw_jarvis_integration.py`

## What it does

- reports OpenClaw health/status to JARVIS
- logs improvements/tasks into the JARVIS improvement map
- toggles JARVIS capabilities
- registers services with the JARVIS HUD

## Current local integration targets

- JARVIS HUD: `http://127.0.0.1:7474`
- OpenClaw gateway: `http://127.0.0.1:18789`
- Ollama: `http://127.0.0.1:11434`
- Obsidian vault: `C:\Users\jamie\Documents\JARVIS-Brain`

## Notes

JARVIS now prefers OpenClaw on port `18789` when present, and falls back to local Ollama when OpenClaw chat relay is unavailable.
