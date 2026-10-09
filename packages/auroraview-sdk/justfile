set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

install:
    vx bun install

build: install
    vx bun run build

typecheck: install
    vx bun run typecheck

test: install
    vx bun run test

# Consume a prebuilt npm pack archive outside this checkout, without registry access.
check-package output="package-artifacts":
    vx node@22 scripts/check_package.mjs --output "{{output}}"

test-package output="package-artifacts": build (check-package output)
