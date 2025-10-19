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
          python313
          sqlc
          postgresql
          lldb
          watchman
        ];

        python = pkgs.python313;

        buildInputs = with pkgs; [];

        pythonEnv = python.withPackages (ps: [
          ps.pywatchman
          ps.jinja2
          ps.pytest
          ps.requests
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
