# Copilot Review Fixes

Fix all actionable Copilot review comments across PR #7 and PR #8. Work autonomously. Angular commits. Push when done.

## PR #7 fixes — branch `feat/framework-extraction`

`git checkout feat/framework-extraction`

### Fix 1: Deadlock in TrilaterationServer (CRITICAL)
File: `src/trilateration/server.py`
Problem: `_process_group()` is called while `buffer_lock` is held in `_processing_loop()`. Since `_process_group()` also tries to acquire `buffer_lock`, this deadlocks.
Fix: In `_processing_loop()`, copy out the groups under the lock, then release the lock BEFORE calling `_process_group()`. Pattern:
```python
with self.buffer_lock:
    # copy groups to process
    groups_to_process = list(current_groups)
    # clear processed detections from buffer
    ...
# lock released — now process without holding it
for group in groups_to_process:
    self._process_group(group)
```

### Fix 2: Memory leak — detection_buffer never pruned
File: `src/trilateration/server.py`
Problem: `detection_buffer` accumulates detections forever.
Fix: At the start of each processing cycle, drop detections older than `newest_timestamp - time_window * 2`. Add this before grouping logic.

### Fix 3: O(n²) grouping — use set for node_id membership
File: `src/trilateration/server.py`
Problem: `other.node_id not in [d.node_id for d in group]` rebuilds a list each iteration.
Fix: Track `group_node_ids = set()` alongside each group, use `other.node_id not in group_node_ids`.

### Fix 4: Packaging mismatch — strix top-level vs src/ layout
Problem: `strix/__init__.py` is at repo root but `setup.py` only discovers packages under `src/`. `import strix` won't work when installed.
Fix: Move `strix/__init__.py` to `src/strix/__init__.py` (creating `src/strix/` as the public namespace package). Update `setup.py` so `find_packages(where="src")` picks it up. Update any imports that reference it.

### Fix 5: Console script entry points
File: `setup.py`
Problem: Entry points reference `main:main` and `scripts/...` which aren't installed packages.
Fix: Add `src/strix/cli.py` with a `main()` that calls `main.main()`, and a `trilateration_cli()` that calls the trilateration server. Update entry points to `strix.cli:main` and `strix.cli:trilateration`.

After all fixes: `python3 -m pytest tests/ -q 2>&1 | tail -5`
Commit: `fix(framework): resolve deadlock, memory leak, O(n²) grouping, and packaging layout`
Push: `git push origin feat/framework-extraction`

---

## PR #8 fixes — branch `docs/documentation-sprint`

`git checkout docs/documentation-sprint`

### Fix 6: GPIO pin wrong in SETUP.md
File: `docs/SETUP.md`
Problem: PPS wiring shows GPIO 18. The validated Adafruit GPS HAT #2324 uses GPIO 4. GPIO 18 is I2S clock — conflict.
Fix: Change all references from `gpiopin=18` to `gpiopin=4`. Add note: "GPIO 18 is reserved for I2S audio on Pi boards — do not use for PPS."

### Fix 7: Wrong UART in SETUP.md
File: `docs/SETUP.md`
Problem: Examples use `/dev/ttyAMA0`. Pi 3B+ assigns ttyAMA0 to Bluetooth; GPS is on `/dev/ttyS0`.
Fix: Change `/dev/ttyAMA0` to `/dev/ttyS0` in gpsd config examples. Add note explaining the Pi 3B+ UART assignment and why this matters.

### Fix 8: QUICKSTART.md missing --scenario arg
File: `docs/QUICKSTART.md`
Problem: `python tools/run_simulation.py` called without required `--scenario` arg. Also references `--list` flag that doesn't exist.
Fix: Change to `python tools/run_simulation.py --scenario basic_4node`. Replace `--list` reference with `python tools/run_simulation.py --help`.

### Fix 9: QUICKSTART.md sample output wrong
File: `docs/QUICKSTART.md`
Problem: Sample output block doesn't match actual runner output format.
Fix: Run `python3 tools/run_simulation.py --scenario basic_4node` and use the ACTUAL output as the example block.

### Fix 10: CONTRIBUTING.md classifier example uses wrong classes
File: `CONTRIBUTING.md`
Problem: Classifier section references `AcousticClassifier`/`ClassificationResult` which don't exist yet (they're in PR #7, not merged).
Fix: Add a note that the classifier interface is coming in the framework extraction PR. For now, show the pattern conceptually with a TODO marker, or reference the base.py file location that will exist after merge.

### Fix 11: CONTRIBUTING.md output node pattern confusion
File: `CONTRIBUTING.md`
Problem: Output node section says subclass `AudioNode`, but most outputs (MQTTOutputNode, FileLoggerNode) are event-bus subscribers, not AudioNode subclasses. Only BufferSaverNode is an AudioNode.
Fix: Clarify the two patterns:
- **Pipeline node** (buffer processing): subclass `AudioNode`, gets called with audio buffers
- **Event subscriber** (reacting to detections): subscribe to EventBus DETECTION events
Show a correct example of each.

### Fix 12: CONTRIBUTING.md scenario example uses wrong dataclasses
File: `CONTRIBUTING.md`
Problem: Scenario example uses `Scenario`/`NodeDef`/`EventDef` but actual API uses `SimulationScenario`/`SimulatedNode`/`AcousticEvent`.
Fix: Open `tests/simulation/scenarios.py` and `tests/simulation/acoustic_simulator.py`, read the actual dataclasses, rewrite the example to match exactly.

### Fix 13: ARCHITECTURE.md references non-existent packages
File: `docs/ARCHITECTURE.md`
Problem: Package table and examples reference `src/trilateration/` and `src/classification/` which don't exist on this branch (they're in PR #7).
Fix: Add a note that these packages exist on the `feat/framework-extraction` branch pending merge. Update the package table to show current state with a "coming soon" marker.

### Fix 14: ARCHITECTURE.md AudioNode event bus claim
File: `docs/ARCHITECTURE.md`
Problem: Says audio pipeline emits `AUDIO` event, but `EventType` has no AUDIO type and the pipeline doesn't do this.
Fix: Correct the description to match actual behavior — audio flows through pipeline nodes via direct method calls, not event bus. Event bus is used for DETECTION/HEALTH/CONFIG/TIMING events only.

After all fixes:
Commit: `fix(docs): correct GPIO pin, UART path, CLI args, API examples, architecture accuracy`
Push: `git push origin docs/documentation-sprint`

---

## When done
`openclaw system event --text "Copilot review fixes complete. Both PRs updated. Sparky has summary." --mode now`
