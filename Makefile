all: tailwind

tailwind:
	tailwindcss -i static/tailwind.css -o static/styles.css
