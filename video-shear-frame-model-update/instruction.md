A shaker at floor 1 drove a four-storey laboratory shear frame with an unrecorded broadband random force while a video camera filmed it face-on for 600 s; a tracker followed one target fixed to each floor.

- `/app/data/tracks.csv`: one row per video frame with the frame timestamp `t_s` (s) and the horizontal image position, in pixels, of targets `T1` to `T4`.
- `/app/data/targets.json`: for each target, the floor it is fixed to, the image row of its centre and its image scale in millimetres per pixel.
- `/app/data/test_record.json`: the design floor masses, the items mounted on the floors during the test, the shaker floor and the camera's row period tau.

Treat the specimen as a shear frame. Floor j (1 to 4; floor 0 is the rigid base) is a rigid lumped mass m_j equal to its design mass plus everything mounted on it during the test. Storey j, between floors j-1 and j, is a massless lateral spring of stiffness k_j. Damping is classical, C = a0*M + a1*K with unknown a0 >= 0 and a1 >= 0. The camera has a rolling shutter: in frame n, image row r is captured at t_n + r*tau, where t_n is the frame timestamp; a target's position is captured at the time of its centre row, and every capture is instantaneous. The camera has no anti-aliasing filter, and natural frequencies may exceed half the frame rate; a folded mode's identified shape carries the rolling-shutter phase of its signed continuous-time frequency, which is negative when the fold is reflected. Several stiffness vectors share the frame's four natural frequencies; the specimen's k is the one whose mode shapes also match the measured ones.

Write `/app/output/model.json`, a regular file of at most 64 KiB holding a JSON object whose only key is `k`: a list of four JSON numbers giving the storey stiffnesses k_1 to k_4 in N/m, in storey order, each between 1 and 10^9.

The verifier builds M from the as-tested masses and K from your `k`, then evaluates 41 configurations: the frame as tested and 40 held-out variants that are not given to you. Nineteen variants add between 0.3 and 2.5 kg to one or two floors; the other twenty-one do the same and also multiply one storey's stiffness by a factor between 0.6 and 1.6. For every configuration, each of the four undamped natural frequencies, taken in ascending order, must be within 3 % (relative) of the true value. The reward is 1 if all 164 frequencies pass and 0 otherwise.

You have 600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
