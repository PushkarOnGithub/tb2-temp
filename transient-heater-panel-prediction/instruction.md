# Two-block transient heater test: recover k and ρc, predict panel temperatures

A filled-epoxy potting compound is being qualified for heater-mat panels. Its thermal conductivity k and volumetric heat capacity ρc were measured in a two-block transient heater test. Recover them from the raw logs in `/app/data` and predict panel temperatures.

Apparatus constants are in `/app/data/apparatus.json`. A foil heater of negligible heat capacity, 80 mm × 80 mm, is clamped between the specimen block and a borosilicate-glass base block. Both blocks are 60 mm thick with insulated outer faces and guarded edges, so conduction is one-dimensional normal to the heater; contact resistances are negligible, all properties are constant, and each run starts from a uniform temperature. The heater element's resistance is temperature-independent. A DC supply fed the heater through 1.5 m leads and logged its output current and the voltage across its own output terminals; the current changed only at logged timestamps. Four thermocouples with instantaneous response are embedded in the specimen. Their depths below the heater plane, listed in `/app/data/sensors.csv`, were measured at the detector on an edge-on radiograph whose central ray lay in the heater plane, with the X-ray focal spot and the bead plane at the distances from the detector given in `apparatus.json`. The logger integrates: every value in `/app/data/run_A.csv` and `/app/data/run_B.csv` (columns `t_s`, `I_A`, `V_supply_V`, `TC1_C` to `TC4_C`) is the mean over the 2 s interval ending at its timestamp.

Each entry of `/app/data/queries.json` is a slab of the specimen material `L_mm` thick, initially uniform at `T_init_C`. From t = 0 its face x = 0 absorbs the net heat flux given by `flux_segments` (`[start_s, q_W_per_m2]` pairs; each flux holds from its start until the next start, the last indefinitely), and its face x = L loses heat by convection with coefficient `h_W_per_m2K` to air at `T_init_C`; nothing else exchanges heat. Predict the temperature at depth `x_mm` below the heated face at time `t_s`.

Write `/app/answer.json`, a regular file of at most 64 KiB holding one JSON object with exactly three keys:

- `k`: the specimen's conductivity in W/(m·K), a JSON number between 0.01 and 100;
- `rho_c`: its volumetric heat capacity in J/(m³·K), a JSON number between 1e5 and 1e8;
- `predictions`: an object whose keys are exactly the six scenario ids in `queries.json` and whose values are the predicted temperatures in °C, as JSON numbers.

A temperature counts as correct when it is within 0.5 % of the true rise above `T_init_C` plus 0.01 K. Your six predictions are checked, and so are 30 hidden scenarios of the same family (L 4–18 mm, h 6–70 W/(m²·K), T_init 18–30 °C, one to three flux segments with fluxes 0–5000 W/m², any depth, t 8–1500 s and at least 2 s from a flux change, rise 1–100 K), computed exactly from your reported `k` and `rho_c`. The reward is 1 if the file meets this contract and all 36 temperatures are correct, and 0 otherwise.

You have 600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
