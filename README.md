# J.A.R.V.I.S - Just A Rather Very Intelligent System

A local AI assistant with voice activation, speech recognition, and text-to-speech capabilities. Integrates with Ollama for local LLM inference and Obsidian for persistent memory.

![JARVIS Dashboard](assets/screenshot1.png)

## Features

- **Voice Activation**: Hold space bar or click mic button to activate
- **Speech Recognition**: Uses Whisper for accurate transcription
- **Text-to-Speech**: Natural voice responses
- **Local LLM**: Integrates with Ollama for private, offline AI inference
- **Persistent Memory**: Integrates with Obsidian for long-term memory storage
- **Futuristic Dashboard**: Modern UI with real-time system monitoring
- **Service Discovery**: Auto-discovers and connects to local AI services
- **Chat History**: Persistent SQLite database for conversation history
- **Hotkey Support**: Ctrl+Space to wake up from any window
- **System Tray**: Runs in background with tray icon

## Installation

### Umbrel (Recommended)

1. Install from Umbrel Community Store
2. Configure your Obsidian vault path in settings
3. Start the app from Umbrel dashboard

### Docker

```bash
docker-compose up -d
```

### Manual

Requirements: Python 3.10+

```bash
pip install -r requirements.txt
python src/main.py
```

## Configuration

Edit `jarvis.cfg` to customize:

```ini
[hud]
port = 7474
open_browser = true
kiosk_mode = false

[ollama]
ports = 11434
default_model = gemma3:1b
fallback_models = gemma3:1b

[obsidian]
vault_path = /path/to/your/vault
api_key = your_api_key
api_url = http://localhost:27124
```

## Usage

1. Open http://localhost:7474 in your browser
2. Allow microphone access when prompted
3. Hold space bar or click the mic button to speak
4. Jarvis will respond with voice and text

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ollama/generate` | POST | Generate AI response |
| `/api/voice/transcribe` | POST | Transcribe audio to text |
| `/api/tts` | POST | Text-to-speech synthesis |
| `/api/sysinfo` | GET | System information |
| `/api/history` | GET | Chat history |
| `/api/openclaw/map` | GET | Service topology |

## Development

### Building for Umbrel

```bash
docker build -t jarvis:latest .
```

### Testing

```bash
python -m pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

- GitHub Issues: https://github.com/jyork07/jarvis-os/issues
- Documentation: https://github.com/jyork07/jarvis-os/wiki

## Acknowledgments

- Ollama for local LLM inference
- Whisper for speech recognition
- Obsidian for persistent memory
- Umbrel for home server platform
