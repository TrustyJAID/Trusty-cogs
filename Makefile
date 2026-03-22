PYTHON ?= python3

# Python Code Style
reformat:
	$(PYTHON) -m ruff format .
stylecheck:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
stylediff:
	$(PYTHON) -m ruff check . --diff
	$(PYTHON) -m ruff format . --diff
