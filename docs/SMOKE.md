# Provider smoke test

Status: pending local `AICREDITS_API_KEY` configuration as of 2026-10-03.

Run `make smoke` after setting the key locally. The script tests the documented
endpoint first, then the alternate endpoint; it reports model ID, usage, tool
call, estimated cost, and whether `reasoning_effort=low` is accepted. Do not
infer live provider support from the offline tests.
