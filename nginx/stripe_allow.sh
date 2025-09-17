#!/usr/bin/env bash
set -euo pipefail
TMP=$(mktemp)
curl -fsSL https://stripe.com/files/ips/ips_webhooks.txt > "$TMP"
{
  echo "# Auto-gerado a partir de ips_webhooks.txt"
  while read -r ip; do
    [[ -z "$ip" ]] && continue
    echo "allow $ip;"
  done < "$TMP"
  echo "deny all;"
} > nginx/conf.d/stripe_webhooks_allow.conf
