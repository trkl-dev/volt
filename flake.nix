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
        # python = pkgs.python3;

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

        # requests = python.pkgs.buildPythonPackage rec {
        #   pname = "requests";
        #   version = "2.32.5"; # Check PyPI for latest version
        #   format = "setuptools";
        #
        #   src = python.pkgs.fetchPypi rec {
        #     inherit pname version;
        #     # format = "setuptools";
        #     # dist = python;
        #     # python = "py3";
        #     # sha256 = "sha256-JGL5RjejT9UyJkKV4YaXbbD11FPRzdMUc8haahYa/7Y=";
        #     sha256 = "sha256-27oLrFbhAIU9sOpxuCtN/V/iv203VKiJPDr1AM7H188=";
        #     # build-system = [ setuptools ];
        #   };

          # propagatedBuildInputs = with python.pkgs; [
          #   idna
          #   urllib3 
          # ];

        #   doCheck = true; # Skip tests to avoid potential issues
        # };

        pythonEnv = python.withPackages (ps: [
          ps.pywatchman
          ps.jinja2
          ps.pytest
          ps.requests

          # requests
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
