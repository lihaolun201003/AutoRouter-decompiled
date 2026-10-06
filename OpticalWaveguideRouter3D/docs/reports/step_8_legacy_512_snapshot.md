# Step 8 legacy 512 endpoint snapshot

## Scope and association
This implementation reproduces this legacy 512 endpoint snapshot only, not a general PMT layout generator, independent 256 layout, complete legacy slot assignment, or complete Router.
The unnamed first column joins the original zero-based connection index. Duplicates, missing/out-of-range indices, mismatched pairs and invalid coordinates raise ValueError. Same-direction rows map (sx,sy) to start; reversed rows map (lx,ly) to start. Original waveguide and port IDs and PMT direction are preserved. local_id stays None; index1/index2 are not local IDs.
Coordinates are used as legacy snapshot values; snapshot and thesis evidence jointly support mm. Point2D remains unit-neutral.

## Actual sources
C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard512.xlsx
C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard0data.xlsx

## Results
```json
{
  "waveguides": 512,
  "pmt_count": 64,
  "direction": {
    "reversed": 141,
    "same": 371
  },
  "snapshot_sides": {
    "150->0": 173,
    "0->150": 115,
    "150->150": 112,
    "0->0": 112
  },
  "restored_sides": {
    "0->150": 144,
    "0->0": 112,
    "150->0": 144,
    "150->150": 112
  },
  "same_side": 224,
  "opposite_side": 288,
  "all_local_id_none": true,
  "y_values": [
    0.0,
    150.0
  ],
  "endpoint_checks": {
    "1": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "2": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "6": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "8": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "9": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "10": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "11": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "12": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "13": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "14": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "16": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "17": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "18": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "19": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "20": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "21": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "24": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "26": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "29": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "33": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "38": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "39": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "41": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "47": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "48": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "49": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "51": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "53": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "54": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "56": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "57": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "58": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "61": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "62": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "66": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "68": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "69": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "70": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "71": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "72": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "73": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "74": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "76": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "77": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "78": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "79": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "80": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "81": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "84": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "86": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "89": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        0.0
      ],
      "pitch_0175": true
    },
    "93": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "98": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "99": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "101": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "107": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "108": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "109": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "111": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "113": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "114": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "116": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "117": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    },
    "118": {
      "count": 16,
      "unique_x": 16,
      "y_values": [
        150.0
      ],
      "pitch_0175": true
    }
  },
  "source_sha256_unchanged": [
    "71a19ec1739de75453608d1d9bd0bb2b9ad102140e4af5057c12e60c0accd7ff",
    "6901bd1f15388cf15831b57297be9a6a6f51ef1d661196e282dc5f1bbd6a8770"
  ]
}
```

## Direction interpretation
The previous 112/112/173/115 four-way count refers to snapshot orientation, not restored input orientation. Both are reported above; reversing a connection changes the two opposite-side directional buckets, without changing same-side/opposite-side totals. This is not a reconstruction failure.

## Verification
Every one of 64 PMTs has 16 endpoints, 16 unique x coordinates, a fixed y and 0.175 spacing within absolute tolerance 1e-8. Source hashes are unchanged. All positions are constructed as Point2D, all local_id values remain None. Coverage checks in the loader passed for all 512 indices.
Tests executed directly (pytest not installed): {'io': 28, 'models': 15, 'geometry': 45, 'router_2d': 15, 'collision': 34, 'loss': 26}; total 163 passed. No dependencies installed this turn.

## Limits and next stage
No Route generation, track search, loss or slot assignment was performed. Self-connections are rejected because endpoint identity cannot be unambiguously recovered from identical PMT IDs. The schema supports small fixtures for testing but only this 512 snapshot is validated as real legacy data.
Re-run from project root: python -B -m scripts.validate_legacy_512_snapshot <fiberboard.xlsx> <snapshot.xlsx>.
Endpoint reconstruction has no remaining blocker; future routing still requires separately specified tracks and routing preparation.
