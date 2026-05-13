{
  description = "glean — self-hosted RSS/LLM digest daemon for Telegram";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
      in {
        packages.default = python.pkgs.buildPythonApplication {
          pname = "glean";
          version = "1.0.0";
          pyproject = true;
          src = ./.;

          build-system = [ python.pkgs.hatchling ];

          dependencies = with python.pkgs; [
            python-telegram-bot
            httpx
            pydantic
            pydantic-settings
            aiosqlite
            structlog
            typer
            aiohttp
            feedparser
            apscheduler
          ];

          # Skip tests in nix build (they require network)
          doCheck = false;

          meta = with pkgs.lib; {
            description = "Self-hosted RSS/LLM digest daemon for Telegram";
            homepage = "https://github.com/jaypetez/glean";
            license = licenses.mit;
            mainProgram = "glean";
          };
        };

        devShells.default = pkgs.mkShell {
          packages = [
            python
            pkgs.uv
          ];
        };
      }
    );
}
