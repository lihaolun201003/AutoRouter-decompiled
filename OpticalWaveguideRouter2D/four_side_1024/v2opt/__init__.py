"""V2 dual-height D56 candidate-search / rip-up-reroute optimisation package.

Round ``v2_candidate_rr_v01``.  This package never changes the V2 CSV identity,
the R=40 mm fixed-radius process parameters, the D56 primitive families or the
strict acceptance policy.  It only:

* reloads a historical, already-audited plane layout as live geometry
  (exact ``D56Index`` + canonical-frame oracles) - no geometry is regenerated
  from route ids;
* expands the *search* over the same D56 geometry primitives
  (:mod:`four_side_1024.v2opt.candext`);
* adds a strengthened, transaction-safe rip-up-and-reroute driver
  (:mod:`four_side_1024.v2opt.rr`);
* writes fslw-compatible plane artefacts so the frozen independent validator
  ``four_side_1024.fslw.validate_fslw`` and the frozen statistical/combined
  tooling can audit the result.
"""
