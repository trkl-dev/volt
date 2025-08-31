{
  description = "Volt";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    nixpkgs,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = import nixpkgs { system = system; config.allowUnfree = true; };
        nativeBuildInputs = with pkgs; [
          tailwindcss_4
          python3
          sqlc
          postgresql
          lldb
        ];
        buildInputs = with pkgs; [];

        python = pkgs.python3;
        pythonEnv = python.withPackages (ps: [
          ps.psycopg
          ps.psycopg2-binary
          ps.psycopg-pool
          ps.sqlalchemy
          ps.jinja2
        ]);
      in {
        devShells.default = pkgs.mkShell {
          name = "volt-shell";

          inherit nativeBuildInputs;

          buildInputs = [
            pythonEnv
          ];
        };
      }
    );
}
