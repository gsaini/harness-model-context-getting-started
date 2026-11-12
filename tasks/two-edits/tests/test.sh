#!/bin/bash
# Harbor runs this inside the task's container after the agent stops.
# The contract: leave a number in /logs/verifier/reward.txt (1 = solved, 0 = not).
mkdir -p /logs/verifier
if python3 /tests/verify.py /app > /logs/verifier/details.json; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
