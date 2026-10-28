#!/usr/bin/env bash
set -Eeuo pipefail
bash /opt/vla/scripts/init-workspace.sh
# Conda activation scripts may refer to unset variables.
set +u
source /opt/vla/scripts/profile.sh
set -u
exec "$@"
