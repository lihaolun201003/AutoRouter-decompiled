# Step 8.5-C: restricted special Z double-arc model

## Evidence versus new model
Legacy evidence supports a special structure for dx<2r and no ordinary horizontal segment after smoothing. The source circle-center interpretation was ambiguous. This implementation is a NEW PROJECT mathematical model, not a claim of reproducing the legacy EXE.

## Independent construction
Let d=abs(xt-xs), e=sign(xt-xs), q=sign(yt-ys), M=(S+T)/2. Endpoint vertical tangency places C1.x=xs+e*r and C2.x=xt-e*r. Mutual external tangency requires center distance 2r; with half vertical displacement h this gives (2r-d)^2+(2h)^2=(2r)^2, so h=sqrt(r*d-d*d/4). The join M is the midpoint of the centers.
A=(xs,M.y-q*h), B=(xt,M.y+q*h), C1=(xs+e*r,A.y), C2=(xt-e*r,B.y). Travel: S to A line, A to M arc, M to B arc, B to T line. Sweeps are -e*q*theta and +e*q*theta, with theta=2*asin(sqrt(d/r)/2). This equivalent stable angle avoids acos cancellation for small d. Circle radius remains r. M tangent is (e*sin(theta),q*cos(theta)); endpoint tangents are (0,q). End inward geometry is interpreted opposite to path travel when viewed from the destination port.

The join height is explicitly the endpoint midpoint, a new symmetric placement decision, not an assigned track. Require tol<d<2r and abs(yt-ys)>=2h; invalid cases raise ValueError, no radius shrinking or track relocation. Exactly zero-length outer lines are omitted. dx near zero is rejected at tol. Existing allocator A+G1+S1 and all 58 unsupported statuses remain unchanged; these independent analytic results are not allocator-approved new routes.

## Legacy experiment
Radius=5.0 in the legacy mm coordinate interpretation; geometry is unit-neutral.
```json
{
  "stats": {
    "input_special_z": 58,
    "success": 58,
    "unsupported": 0,
    "geometry_error": 0,
    "endpoint_errors": 0,
    "continuity_errors": 0,
    "tangent_errors": 0,
    "radius_errors": 0,
    "arc_count": 116,
    "line_count": 116
  },
  "directions": {
    "top_to_bottom": {
      "input": 28,
      "success": 28,
      "failed": 0
    },
    "bottom_to_top": {
      "input": 30,
      "success": 30,
      "failed": 0
    }
  },
  "failures": []
}
```
All successful cases passed analytic radius/rotation validation, exact endpoint preservation, segment continuity, line-arc and arc-arc tangency, vertical terminal tangent checks and finite positive length checks. No tolerance was enlarged.

## Regression
{'models': 18, 'geometry': 63, 'router_2d': 48, 'collision': 44, 'loss': 26, 'io': 28}; total 227 passed by direct test-function execution. Includes four direction/mirror combinations, small dx, near 2r, invalid spans, insufficient height, reverse symmetry, exact vertical fit and no input mutation. No new dependencies.

## Limits
No line/arc collisions, clearance, width, loss or integration with prior 454 curves was evaluated. All special curves use their midpoint placement, which may interact with other routes; geometric construction success is not global feasibility. No Step 8.5-D work performed.
