all: watch

build-zig: 
	zig build -Doptimize=Debug -freference-trace

run:
	-pkill -TERM -f "python example.py" && sleep 2 || pkill -KILL -f "python example.py"
	python example.py &

debug:
	-pkill -TERM -f "python example.py" && sleep 2 || pkill -KILL -f "python example.py"
	lldb python example.py

debug-test:
	-pkill -TERM -f "python example.py" && sleep 2 || pkill -KILL -f "python example.py"
	lldb pytest

test: build-zig
	@echo "Runnning Zig tests..."
	zig test src/volt.zig
	@echo "Runnning Python tests..."
	NO_LOGS="true" pytest

test-verbose: build-zig
	zig test src/volt.zig
	pytest -svv

inspect-coredump:
	coredumpctl debug --debugger lldb

generate:
	python -m volt.cli generate

watch: build-zig tailwind generate run 
	watchman-make \
		-p '**/*.zig' -t build run \
		-p '**/*.html' '**/*.js' -t tailwind \
		-p '**/*.html' -t generate \
		-p '**/*.py' -t run

upload-test:
	python -m twine upload --repository testpypi dist/*
