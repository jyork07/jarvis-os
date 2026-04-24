# Umbrel Community Store Submission Guide

## Prerequisites

Before submitting to the Umbrel Community Store, ensure:

1. ✅ GitHub repository is public
2. ✅ All placeholder images replaced with actual screenshots
3. ✅ `umbrel.yaml` is properly configured
4. ✅ Docker image builds successfully
5. ✅ App works correctly on Umbrel

## Testing on Umbrel

1. **Deploy to Test Umbrel**
   ```bash
   # Copy app to Umbrel apps directory
   scp -r jarvis umbrel@umbrel.local:~/umbrel-apps/
   
   # Or use Umbrel's app development tools
   ```

2. **Verify Functionality**
   - App installs without errors
   - Dashboard loads at correct port
   - Voice activation works
   - Ollama integration works
   - Obsidian integration works (if configured)

## Submission Checklist

### Files Required
- [x] `umbrel.yaml` - App manifest
- [x] `docker-compose.yml` - Docker setup
- [x] `Dockerfile` - Container build
- [x] `README.md` - Documentation
- [x] `LICENSE` - MIT License
- [x] `assets/icon.png` - 512x512 PNG
- [x] `assets/screenshot1.png` - 1280x720 PNG
- [x] `assets/screenshot2.png` - 1280x720 PNG
- [x] `assets/screenshot3.png` - 1280x720 PNG

### umbrel.yaml Verification
- [x] Name: `jarvis`
- [x] Version: `1.0.0`
- [x] Description is clear and concise
- [x] Icon URL points to GitHub raw content
- [x] Developer: OpenClaw
- [x] Website: GitHub repository
- [x] Category: AI
- [x] Ports: 7474, 11434
- [x] Permissions: STORAGE, NETWORK, MICROPHONE
- [x] Gallery images point to GitHub raw content

### Docker Verification
- [x] Dockerfile builds without errors
- [x] Docker compose starts services correctly
- [x] Services can communicate on host network
- [x] Volume mounts work correctly
- [x] Ports are exposed properly

## Submission Process

1. **Fork Umbrel App Store Repository**
   ```bash
   git clone https://github.com/getumbrel/umbrel-app-store.git
   cd umbrel-app-store
   ```

2. **Create App Directory**
   ```bash
   mkdir jarvis
   cd jarvis
   ```

3. **Copy App Files**
   ```bash
   # Copy from your jarvis repository
   cp /path/to/jarvis/umbrel.yaml .
   cp /path/to/jarvis/docker-compose.yml .
   cp /path/to/jarvis/Dockerfile .
   ```

4. **Update umbrel.yaml for Store**
   ```yaml
   # Update icon and gallery URLs to point to your GitHub
   icon: https://raw.githubusercontent.com/openclaw/jarvis/main/assets/icon.png
   gallery:
     - https://raw.githubusercontent.com/openclaw/jarvis/main/assets/screenshot1.png
     - https://raw.githubusercontent.com/openclaw/jarvis/main/assets/screenshot2.png
     - https://raw.githubusercontent.com/openclaw/jarvis/main/assets/screenshot3.png
   ```

5. **Commit and Push**
   ```bash
   git add .
   git commit -m "Add JARVIS app"
   git push origin your-branch
   ```

6. **Create Pull Request**
   - Go to https://github.com/getumbrel/umbrel-app-store
   - Create PR from your fork
   - Title: `Add JARVIS - Local AI Assistant`
   - Description: Include app features and testing notes

## Post-Submission

1. **Monitor PR**
   - Respond to review comments
   - Make requested changes
   - Update documentation as needed

2. **Promote Your App**
   - Share on social media
   - Post in Umbrel community
   - Create tutorial videos
   - Write blog posts

3. **Maintain App**
   - Fix bugs reported by users
   - Add new features
   - Update dependencies
   - Respond to issues

## Troubleshooting

### App Won't Install
- Check Docker logs: `docker logs jarvis`
- Verify port availability
- Check volume mount permissions

### Voice Not Working
- Verify microphone permissions
- Check audio device mapping
- Review Docker device settings

### Ollama Connection Failed
- Verify Ollama service is running
- Check network mode (host)
- Review port configuration

## Resources

- Umbrel App Store: https://github.com/getumbrel/umbrel-app-store
- Umbrel Documentation: https://docs.umbrel.com
- Umbrel Community: https://community.getumbrel.com
