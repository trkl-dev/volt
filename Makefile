all: tailwind

tailwind:
	tailwindcss -i static/tailwind.css -o static/styles.css

coredump:
	coredumpctl debug --debugger lldb

