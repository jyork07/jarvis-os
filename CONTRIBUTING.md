# Contributing to JARVIS

Thank you for your interest in contributing to JARVIS!

## How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Commit your changes (`git commit -m 'Add some amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/your-username/jarvis.git
cd jarvis

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python src/main.py
```

## Code Style

- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to functions
- Keep functions focused and small

## Testing

```bash
# Run tests
python -m pytest tests/

# Run with coverage
python -m pytest tests/ --cov=src
```

## Submitting Changes

- Ensure all tests pass
- Update documentation if needed
- Add your name to the contributors list
- Submit a clear description of your changes

## Questions?

Open an issue on GitHub for any questions or discussions.
