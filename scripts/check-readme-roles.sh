#!/bin/sh
# README's role table must list every role in main.yml, in the same order.
#
# Order is the load-bearing half. An unordered table is what let four rows that
# were not roles at all sit in it for months (DECISIONS Q102) — nothing could be
# checked against anything. Keeping the sequence identical to main.yml turns the
# table into a diff: a role added to the playbook and not to README shows up as
# one line here instead of as a silent omission.
#
# Note `sed -E` with [[:space:]] rather than \s — BSD/macOS sed does not
# understand \s, and fails open by not matching, which reads as "no roles found".
set -eu

cd "$(dirname "$0")/.."

order=$(mktemp) || exit 1
table=$(mktemp) || exit 1
trap 'rm -f "$order" "$table"' EXIT

# roles: block of main.yml, unwrapping `- role: x` as well as `- x`
awk '/^  roles:/ { f = 1; next } f && /^[^ ]/ { exit } f' main.yml \
  | sed -E 's/^[[:space:]]*-[[:space:]]*(role:[[:space:]]*)?//' \
  | grep -E '^[a-z][a-z0-9-]*$' > "$order"

# first column of the role table
sed -n '/^| Role |/,/^$/p' README.md \
  | grep -E '^\| [a-z]' \
  | awk -F'|' '{ gsub(/ /, "", $2); print $2 }' > "$table"

if [ ! -s "$order" ]; then
  echo "could not parse the roles: block out of main.yml — check this script, not main.yml"
  exit 1
fi

if ! diff -u "$order" "$table" > /tmp/roles-diff.$$ 2>&1; then
  echo "README role table does not match main.yml (-main.yml +README):"
  sed -n '3,$p' /tmp/roles-diff.$$ | sed 's/^/  /'
  rm -f /tmp/roles-diff.$$
  exit 1
fi
rm -f /tmp/roles-diff.$$

# a row naming a directory that does not exist passes the diff only if main.yml
# names it too, which would be a broken playbook — but check anyway, cheaply.
missing=""
while read -r r; do
  [ -d "roles/$r" ] || missing="$missing $r"
done < "$table"
if [ -n "$missing" ]; then
  echo "README rows with no roles/ directory:$missing"
  exit 1
fi

echo "README role table: $(wc -l < "$table" | tr -d ' ') roles, order matches main.yml"
