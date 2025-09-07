all: tailwind

tailwind:
	tailwindcss -i static/tailwind.css -o static/styles.css

tailwind-watch:
	tailwindcss -i static/tailwind.css -o static/styles.css --watch

coredump:
	coredumpctl debug --debugger lldb

