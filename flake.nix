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
          watchman
        ];
        buildInputs = with pkgs; [];

        jinja2-fragments = python.pkgs.buildPythonPackage rec {
        pname = "jinja2_fragments";
        version = "1.9.0"; # Check PyPI for latest version
        format = "wheel";

        src = python.pkgs.fetchPypi rec {
          inherit pname version;
          format = "wheel";
          dist = python;
          python = "py3";
          sha256 = "sha256-abkefi8yXqfjkeNqmrzFctuWfivzr9NfdPy3j8n4xsU=";
          # build-system = [ setuptools ];
        };

        propagatedBuildInputs = with python.pkgs; [
          jinja2
        ];

        doCheck = false; # Skip tests to avoid potential issues
        };

        python = pkgs.python3;
        pythonEnv = python.withPackages (ps: [
          ps.pywatchman
          ps.jinja2
          jinja2-fragments
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
