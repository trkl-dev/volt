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
        # pkgs = nixpkgs.legacyPackages.${system};
        pkgs = import nixpkgs { system = "x86_64-linux"; config.allowUnfree = true; };
        nativeBuildInputs = with pkgs; [
          zig
          python3
        ];
        buildInputs = with pkgs; [];
      in {
        devShells.default = pkgs.mkShell {inherit nativeBuildInputs buildInputs;};
      }
    );
}
