#!/usr/bin/env bash
set -euo pipefail

# Keep Ubuntu's existing suites, components and signature verification settings.
# Hosted runners may resolve their Ubuntu URI through this mirror list.
for apt_source in /etc/apt/sources.list \
    /etc/apt/sources.list.d/*.list \
    /etc/apt/sources.list.d/*.sources \
    /etc/apt/apt-mirrors.txt; do
    if [[ -f "$apt_source" ]]; then
        sudo sed -i -E \
            's#https?://azure\.archive\.ubuntu\.com/ubuntu/?([[:space:]]|$)#https://archive.ubuntu.com/ubuntu\1#g' \
            "$apt_source"
    fi
done

# Bound failed transfers in every apt invocation on this ephemeral runner.
# Runner images already have zz-retries; this file must sort after it.
sudo tee /etc/apt/apt.conf.d/zzzz-auroraview-network > /dev/null <<'APT'
Acquire::Retries "3";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
APT

apt-config dump | awk '/^Acquire::(Retries|http::Timeout|https::Timeout) /'
