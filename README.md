# tb2-temp

One Terminal-Bench (Harbor) task for **Scientific Computing / Research Engineering — Engineering**:
[`transient-heater-panel-prediction/`](transient-heater-panel-prediction/).

An agent gets raw logs from a two-block transient heater test (supply current and terminal
voltage, four embedded thermocouples read by an integrating logger, radiograph-measured bead depths)
and must recover a potting compound's `k` and `ρc`, then predict temperatures in a different
configuration: panels under a stated net heat flux with convective cooling. Three stated apparatus
facts change the answer while leaving the fit untouched:

- the heater power is not V·I;
- the heat splits between the two blocks by effusivity;
- radiograph depths are magnified.

Every tempting default therefore fits the data at the noise floor, yet recovers `k`/`ρc` 12–190 %
off and fails at least 34 of the 36 graded temperatures.

## Where each requested deliverable lives

| # | Deliverable | Location |
|---|---|---|
| 1 | Exact task statement | [`instruction.md`](transient-heater-panel-prediction/instruction.md) |
| 2 | Environment, files, input data | [`environment/Dockerfile`](transient-heater-panel-prediction/environment/Dockerfile), [`environment/data/`](transient-heater-panel-prediction/environment/data/), [`task.toml`](transient-heater-panel-prediction/task.toml) |
| 3 | Expected deliverables | `/app/answer.json` contract in `instruction.md`; schema checked by [`tests/answer_format.py`](transient-heater-panel-prediction/tests/answer_format.py) |
| 4 | Hidden-verifier strategy, exact grading criteria | [`README.md` § Verification](transient-heater-panel-prediction/README.md#verification), [`tests/`](transient-heater-panel-prediction/tests/) |
| 5 | Gold / reference methodology | [`README.md` § Reference solution](transient-heater-panel-prediction/README.md#reference-solution) |
| 6 | Expected failure modes of frontier models | [`README.md` § Expected frontier-model behaviour](transient-heater-panel-prediction/README.md#expected-frontier-model-behaviour-predicted-not-yet-measured) |
| 7 | Why each failure is hard to detect | [`README.md` § Difficulty](transient-heater-panel-prediction/README.md#difficulty) ("Why the defaults are silent") |
| 8 | Difficulty calibration | [`README.md` § Difficulty calibration](transient-heater-panel-prediction/README.md#difficulty-calibration), [`authoring/evidence/`](transient-heater-panel-prediction/authoring/evidence/) |
| 9 | Reference implementation | [`solution/solve.py`](transient-heater-panel-prediction/solution/solve.py), plus an independent finite-volume solver in [`authoring/evidence/independent_solver.py`](transient-heater-panel-prediction/authoring/evidence/independent_solver.py) |
| 10 | Adversarial hidden tests | 30 held-out scenarios in [`tests/instance.py`](transient-heater-panel-prediction/tests/instance.py); attack battery and results in [`authoring/evidence/calibration_run.log`](transient-heater-panel-prediction/authoring/evidence/calibration_run.log) |

## Validate locally

```
cd transient-heater-panel-prediction
python3 authoring/check_package.py            # static gates (45 checks)
python3 authoring/evidence/variants.py         # wrong-method discriminator harness (numpy/scipy)
bash authoring/evidence/run_evidence.sh        # builds both images, runs 52 calibration runs
```
