.PHONY: install dev init doctor site test lint sync seed prizes official-data products products-sync import-v130 checklist import-pages forecast forecast-update forecast-report products-report market report bao-report analyze inference backtest ml serve docker-build docker-up docker-job

PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

install:
	$(PY) -m pip install -e ".[crawler]"

dev:
	$(PY) -m pip install -e ".[dev,crawler]"

init:
	$(PY) -m vietlott_engine.cli init

doctor:
	$(PY) -m vietlott_engine.cli doctor

site:
	$(PY) scripts/build_site.py

test:
	$(PY) -m pytest

lint:
	ruff check --select F,B023 src scripts tests

seed:
	$(PY) -m vietlott_engine.cli sync --game all --source file --path data/seed

sync:
	$(PY) -m vietlott_engine.cli sync --game all

prizes:
	$(PY) -m vietlott_engine.cli prizes --game all --source canonical

official-data:
	$(PY) scripts/build_official_dataset.py --vendor .vendor --update $(if $(V130),--v130-dir $(V130),)

products:
	$(PY) -m vietlott_engine.cli products list

products-sync:
	$(PY) -m vietlott_engine.cli products sync --source $(or $(SOURCE),auto)

import-v130:
	$(PY) -m vietlott_engine.cli products sync --source v130 --path $(V130)
	$(PY) -m vietlott_engine.cli prizes --game all --source v130 --path $(V130)

forecast:
	$(PY) -m vietlott_engine.cli forecast next --product $(or $(PRODUCT),all)

forecast-update:
	$(PY) -m vietlott_engine.cli forecast update --product $(or $(PRODUCT),all)
	$(PY) -m vietlott_engine.cli forecast scoreboard

forecast-report:
	$(PY) scripts/forecast_report.py

checklist:
	$(PY) scripts/verification_checklist.py

import-pages:
	$(PY) -m vietlott_engine.cli products import-pages --path $(PAGES) $(if $(DRY),--dry-run,)

products-report:
	$(PY) scripts/products_report.py

market:
	$(PY) -m vietlott_engine.cli market

report:
	$(PY) scripts/market_report.py

bao-report:
	$(PY) scripts/bao_report.py

analyze:
	$(PY) -m vietlott_engine.cli analyze --game all

inference:
	$(PY) -m vietlott_engine.cli inference --game all --sims 2000 --out reports

backtest:
	$(PY) -m vietlott_engine.cli backtest --game all --tickets 5 --out reports \
		--strategies random hot cold overdue bayes markov gcn anti_popularity wheel

ml:
	$(PY) -m vietlott_engine.cli ml --game all

serve:
	$(PY) -m vietlott_engine.cli serve --port 8000

docker-build:
	docker compose build

docker-up:
	docker compose up -d api scheduler

docker-job:
	VQE_UID=$$(id -u) VQE_GID=$$(id -g) docker compose --profile jobs run --rm backtest
