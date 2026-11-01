# Golden fixtures

These are small networks (NGB1) with the spike rasters the Python reference kernel produces. Every native kernel must
reproduce them bit for bit. The format and how they are made are described in `make_fixtures.py`.

```bash
JAX_PLATFORMS=cpu python desktop/common/fixtures/make_fixtures.py     # regenerate; also checks the rasters against JAX
```

`tests/test_nglif_fixtures.py` regenerates the fixtures in CI and fails if they differ from the committed files.

| Fixture | Covers |
|---|---|
| `column_saturated` | default column preset: strong recurrent excitation |
| `column_unsaturated` | weight scale 0.2, refractory period 3 |
| `column_external` | the same network with positive and negative external currents |
| `microcircuit`, `layered` | the other presets |
| `drivers_delays` | every feature: Poisson rates 0–1000 Hz, bursters (default and custom period and duty), shifts 1–10, refractory 0–5, delays 0–31, inhibition |
| `drivers_delays_seed` | another kernel seed |
| `drivers_delays_external` | random external currents |
