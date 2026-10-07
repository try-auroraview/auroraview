#!/usr/bin/env bash
set -euo pipefail

# Keep Ubuntu's existing suites, components and signature verification settings.
for apt_source in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
    if [[ -f "$apt_source" ]]; then
        sudo sed -i -E \
            's|https?://azure\.archive\.ubuntu\.com/ubuntu/?([[:space:]]|$)|https://archive.ubuntu.com/ubuntu\1|g' \
            "$apt_source"
    fi
done

# Bound failed transfers in every apt invocation on this ephemeral runner.
sudo tee /etc/apt/apt.conf.d/80auroraview-network > /dev/null <<'APT'
Acquire::Retries "3";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
APT
