all: build 

# run:
# 	-pkill -TERM -f "python example.py" && sleep 2 || pkill -KILL -f "python example.py"
# 	python example.py &

# debug:
# 	-pkill -TERM -f "python example.py" && sleep 2 || pkill -KILL -f "python example.py"
# 	lldb python example.py

# debug-test:
# 	-pkill -TERM -f "python example.py" && sleep 2 || pkill -KILL -f "python example.py"
# 	lldb pytest

test: build
	pytest

test-verbose: 
	pytest -svv

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
