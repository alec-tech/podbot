# Contributing to PodBot

Thanks for your interest in contributing! PodBot is an open-source AI podcast platform and we welcome contributions of all kinds.

## Getting Started

1. **Fork and clone** the repository
2. **Run setup**: `chmod +x setup.sh && ./setup.sh`
3. **Configure** `.env` with at least `ANTHROPIC_API_KEY` and one TTS provider key
4. **Test with a dry run**: `python orchestrator.py --show example-show --edition morning --dry-run`

## Development Workflow

### Project Structure

- `agents/` — Core pipeline agents (curator, scriptwriter, voice producer, publisher)
- `shows/{slug}/` — Per-show configuration (show.json, personas, feeds, prompts, sponsors)
- `orchestrator.py` — Main pipeline runner
- `admin.py` — FastAPI admin server
- `website/` — Static site + dashboard

### Running Tests

```bash
# Dry run (curation only — no TTS cost, no publishing)
python orchestrator.py --show example-show --edition morning --dry-run

# Resume from a specific stage
python orchestrator.py --show example-show --edition morning --start-from script

# Verify imports
python3 -c "from agents.show_loader import load_show; print(load_show().name)"
```

### Code Style

- Python 3.10+
- Use type hints for function signatures
- Keep agents stateless — all state flows through `ShowConfig`
- Use lazy client initialization (`_get_client()`) to avoid import-time crashes
- Prefer editing existing files over creating new ones

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Test with `--dry-run` to verify nothing breaks
4. Ensure Python files import cleanly
5. Submit a PR with a clear description of what changed and why

## Areas for Contribution

- **New TTS providers** — Add a provider in `agents/tts/` implementing the `TTSProvider` ABC
- **Feed sources** — Support new news aggregation sources beyond RSS and NewsAPI
- **Show templates** — Pre-built show configs for common podcast formats
- **Dashboard improvements** — Enhance `admin/index.html` or `website/dashboard.html`
- **Documentation** — Improve README, add examples, write guides

## Reporting Issues

Use the GitHub issue templates:
- **Bug reports**: Include your show config, Python version, and relevant logs
- **Feature requests**: Describe the use case and proposed solution

## License

By contributing, you agree that your contributions will be licensed under the AGPLv3 license.
