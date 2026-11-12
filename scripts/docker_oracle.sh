#!/bin/bash
# Check every task inside its own container, following the same contract Harbor uses:
#   build environment/Dockerfile -> run the agent in /app -> copy tests/ to /tests -> run tests/test.sh
#   -> read the reward from /logs/verifier/reward.txt
# Here the "agent" is the reference solution (what Harbor calls the oracle agent). Each task must score 0
# before it and 1 after it. Needs Docker; uses no network inside the containers.
set -euo pipefail
cd "$(dirname "$0")/.."

reward() { # container -> the number the verifier wrote
  docker exec "$1" bash /tests/test.sh > /dev/null 2>&1 || true
  docker exec "$1" cat /logs/verifier/reward.txt
}

failed=0
printf '%-22s %-10s %-15s %s\n' task untouched "after solve.sh" usable
for dir in tasks/*/; do
  name=$(basename "$dir")
  image="agentlab-task-$name"
  docker build --quiet --tag "$image" "$dir/environment" > /dev/null
  container=$(docker run --detach --network none "$image" sleep 300)
  docker cp --quiet "$dir/tests" "$container:/tests"
  before=$(reward "$container")
  docker cp --quiet "$dir/solution" "$container:/solution"
  docker exec "$container" bash /solution/solve.sh
  after=$(reward "$container")
  docker rm --force "$container" > /dev/null
  if [ "$before" = "0" ] && [ "$after" = "1" ]; then usable=yes; else usable=NO; failed=1; fi
  printf '%-22s %-10s %-15s %s\n' "$name" "$before" "$after" "$usable"
done
exit $failed
