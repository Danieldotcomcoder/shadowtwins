# Task runner (https://just.systems). `just --list` shows everything.

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

image := "shadowtwins:0.1.0"

# Python lint, types, tests, contract drift and independent certificate verification
check:
    uv run ruff check src tests tools
    uv run pyright
    uv run pytest -q -o addopts="" -p no:warnings
    uv run shadowtwins export-contracts --check
    uv run benchserver export-openapi --check
    uv run shadowtwins-verify --jobs 8 packs/shadowtwins-ranked-v1 packs/shadowtwins-practice-v1 packs/shadowtwins-dev-v1

# Frontend unit tests, build and Playwright end-to-end suite
frontend:
    pnpm --dir frontend install --frozen-lockfile
    pnpm --dir frontend test
    pnpm --dir frontend build
    pnpm --dir frontend e2e

# Local development: API + embedded worker (mock provider on) and the Vite dev server
dev:
    uv run benchserver dev --port 8000

# Build the release image
docker-build:
    docker build -t {{image}} .

# Container acceptance gates (throwaway volume, mock provider)
docker-accept: docker-build
    uv run python tools/container_acceptance.py --image {{image}}

# Full release matrix (writes docs/reports/RELEASE_CHECK.md)
release-check:
    uv run --extra research python tools/release_check.py --frontend

# Re-verify a pack directory without any engine code
verify pack="packs/shadowtwins-ranked-v1":
    uv run shadowtwins-verify --jobs 8 {{pack}}

# Plan (no --yes) or run the paid pilot: just pilot 2.00 --yes
pilot cap *flags:
    uv run python tools/pilot.py --cap {{cap}} {{flags}}
