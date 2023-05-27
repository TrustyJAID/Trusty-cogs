PYTHON ?= python3

# Python Code Style
reformat:
	$(PYTHON) -m isort .
	$(PYTHON) -m black .
stylecheck:
	$(PYTHON) -m isort --check .
	$(PYTHON) -m black --check .
stylediff:
	$(PYTHON) -m isort --check --diff .
	$(PYTHON) -m black --check --diff .
