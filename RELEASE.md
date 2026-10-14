# Manual release

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

For a first-time release, create the project on PyPI with the exact distribution name `ratelattice`, then upload the generated wheel and source distribution. Never commit PyPI tokens; use `twine` environment variables or its interactive prompt.
