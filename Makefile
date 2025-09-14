all: watch

build: 
	zig build -freference-trace

run:
	-pkill -TERM -f "python example.py" && sleep 2 || pkill -KILL -f "python example.py"
	python example.py &

tailwind:
	tailwindcss -i static/tailwind.css -o static/styles.css

tailwind-watch:
	tailwindcss -i static/tailwind.css -o static/styles.css --watch

inspect-coredump:
	coredumpctl debug --debugger lldb

watch: build tailwind run
	watchman-make -p '**/*.zig' -t build run -p '**/*.html' '**/*.js' -t tailwind -p '**/*.py' -t run
