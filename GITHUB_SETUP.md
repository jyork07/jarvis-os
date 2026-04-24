# GitHub Repository Setup Guide

## Initial Setup

1. **Create GitHub Repository**
   - Go to https://github.com/new
   - Repository name: `jarvis`
   - Description: `J.A.R.V.I.S - Just A Rather Very Intelligent System. Local AI assistant with voice activation.`
   - Public repository
   - Initialize with README (skip, we have one)
   - Add .gitignore (skip, we have one)
   - Choose license: MIT

2. **Initialize Local Git Repository**
   ```bash
   cd C:\Users\jamie\Documents\Obsidian Vault\OpenClaw\Jarvis
   git init
   git add .
   git commit -m "Initial commit: JARVIS v1.0"
   ```

3. **Add Remote and Push**
   ```bash
   git remote add origin https://github.com/openclaw/jarvis.git
   git branch -M main
   git push -u origin main
   ```

## Repository Structure

```
jarvis/
├── src/                    # Source code
│   ├── main.py            # Main application
│   ├── obsidian_integration.py
│   └── static/            # Static assets
│       ├── assets/
│       ├── dashboard.html
│       └── templates/
├── assets/                # Images for GitHub/Umbrel
│   ├── icon.png
│   ├── screenshot1.png
│   ├── screenshot2.png
│   └── screenshot3.png
├── jarvis.cfg            # Configuration file
├── docker-compose.yml    # Docker setup
├── Dockerfile            # Docker image
├── umbrel.yaml          # Umbrel app manifest
├── requirements.txt     # Python dependencies
├── README.md            # Project documentation
├── LICENSE              # MIT License
├── CONTRIBUTING.md      # Contribution guidelines
├── .gitignore           # Git ignore rules
└── GITHUB_SETUP.md      # This file
```

## After Pushing to GitHub

1. **Add Screenshots**
   - Take screenshots of the dashboard at http://localhost:7474
   - Replace placeholder files in `assets/` directory:
     - `icon.png` (512x512 PNG)
     - `screenshot1.png` (1280x720 PNG)
     - `screenshot2.png` (1280x720 PNG)
     - `screenshot3.png` (1280x720 PNG)
   - Commit and push:
     ```bash
     git add assets/
     git commit -m "Add actual screenshots and icon"
     git push
     ```

2. **Enable GitHub Features**
   - Go to repository Settings
   - Enable Issues
   - Enable Discussions
   - Enable Actions (for CI/CD)
   - Add repository topics: `ai`, `voice-assistant`, `ollama`, `umbrel`, `local-llm`

3. **Create Releases**
   - Go to Releases → Create new release
   - Tag: `v1.0.0`
   - Release title: `JARVIS v1.0.0 - Initial Release`
   - Description: Add release notes
   - Attach built executable if desired

## Umbrel Community Store Submission

See `UMBREL_SUBMISSION.md` for detailed instructions.

## Continuous Integration (Optional)

Create `.github/workflows/ci.yml`:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: python -m pytest tests/
```
