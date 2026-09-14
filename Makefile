# Reproduce the analysis. Cricsheet updates its archive daily; data/cricsheet_SHA256SUMS
# records the files used for v0.1.0-alpha, so a fresh download may not match it.
RUN = uv run --no-project --with pandas --with pyarrow --with pyfixest --with scipy python

.PHONY: data roster gates estimate lint

raw/all_json.zip:
	mkdir -p raw
	curl -sL -o raw/all_json.zip https://cricsheet.org/downloads/all_json.zip
	curl -sL -o raw/people.csv https://cricsheet.org/register/people.csv
	curl -sL -o raw/names.csv https://cricsheet.org/register/names.csv
	cd raw && shasum -a 256 all_json.zip people.csv names.csv

data: raw/all_json.zip
	$(RUN) scripts/parse_cricsheet.py
	$(RUN) scripts/build_innings.py

roster:
	$(RUN) scripts/merge_roster.py data/collection/*.txt
	$(RUN) scripts/match_registry.py

gates:
	cd scripts && $(RUN) matched_pairs.py p1 --reps 100 --raw ../raw --data ../data --out ../results
	cd scripts && $(RUN) matched_pairs.py p2 --raw ../raw --data ../data --out ../results

estimate:
	cd scripts && $(RUN) matched_pairs.py estimate --raw ../raw --data ../data --out ../results

lint:
	uvx black --check --target-version py312 scripts
	uvx isort --check scripts
	uvx flake8 scripts
