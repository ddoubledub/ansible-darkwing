#!/usr/bin/env bash
set -euo pipefail
ansible-inventory -i inventories/prod/hosts.yml --list >/dev/null
echo "Inventory OK"