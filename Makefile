all: test run

run:
	python3 example.py

test: build
	pytest

test-verbose: 
	pytest -svv --log-cli-level=DEBUG

generate:
	python -m volt.cli generate

watch: build generate run 
	watchman-make \
		-p '**/*.zig' -t build run \
		-p '**/*.html' '**/*.js' -t tailwind \
		-p '**/*.html' -t generate \
		-p '**/*.py' -t run

upload-test:
	python -m twine upload --repository testpypi dist/*
