format: lint
	uv run -- ruff format

lint:
	uv run -- ruff check --fix
	uv run -- ty check

run:
	uv run -- main.py

install:
	uv sync --all-extras
	uv run -- prek install

test:
	uv run -- pytest -v -n auto