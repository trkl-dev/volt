import sys
from .generator import generate

def main():
    if len(sys.argv) < 2:
        print("Usage: volt <command>")
        print("Commands:")
        print("  generate - Generate components from jinja2 templates")
        print("  tailwind - Generate tailwind static css")
        sys.exit(1)
    
    command = sys.argv[1]
    
    match command:
        case "generate":
            generate()
        case _:
            print(f"Unknown command: {command}")
            sys.exit(1)

if __name__ == "__main__":
    main()
