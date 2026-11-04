# Parameter profiles and provenance

A **profile** is a JSON file of default parameters for a stage or an example: a species, a brain region, an age range.
The toolbox does not depend on any profile. Every value a profile gives can be replaced by a constant, a `Gene`, a
`Field` or a `Fit` parameter, and a gene can take any value in its bounds, including combinations found nowhere in nature.
A profile says only what a sensible default is, and **where each number comes from**, so that a measurement, a
derived value, an assumption and a free parameter are never mixed up.

```
python -m neurogenesis profile check --all          # every profile of examples/profiles, ./profiles, $NEUROGENESIS_PROFILES
python -m neurogenesis profile check my_profile.json --online    # also ask Crossref whether each DOI exists
python -m neurogenesis profile show cell_cycle_clock             # parameters with their status
```

## The four statuses

| status | meaning | required |
|---|---|---|
| `measured` | a value or statement in a paper | `source`, `evidence` |
| `derived` | computed from measured values (an interpolation, a fit) | `method`, and `source` + `evidence` if it uses papers |
| `assumed` | a modelling choice or an illustrative value | `note` |
| `free` | a virtual parameter with no biological counterpart | `note`, optional `bounds` |

Every entry also has a `quantity`: what the number is. An E_GABA is not an E_Cl, and a time per embryonic day is not a
time per cell cycle. Optional fields are `species`, `region`, `age`, `method`, `note` and `bounds` (`[lo, hi]`).

`source` is a list of `"doi:10.xxxx/..."` strings or `"ref:Author Year, venue"` for work without a DOI.
`evidence` says what was actually read: `full_text`, `abstract`, `title_only` or `not_checked`. An honest `abstract` is
worth more than an unverified `full_text`.

## Where the entries go

Each top-level key of a profile, apart from the metadata keys (`id`, `description`, `citations`, `age_unit`, `notes`,
`extends`, `provenance`), needs an entry in the `provenance` object. The entry is written at the key (`"k"`), or at each
element of a list or dict (`"windows[0]"`, `"params.e_mature"`), or with a `*` for key names (`"reference_*"`). A profile
that leaves a parameter unlabelled does not pass `profile check`, and a test runs the check on every profile in
`examples/profiles`.

```json
{
  "id": "my_stage_mouse_v1",
  "description": "Defaults of my_stage for the mouse visual cortex.",
  "tau": 12.5,
  "gain": 1.0,
  "provenance": {
    "tau": {"status": "measured", "quantity": "membrane time constant of L2/3 pyramidal cells (ms)",
            "species": "mouse", "region": "V1 layer 2/3", "age": "adult",
            "source": ["doi:10.xxxx/yyyy"], "evidence": "full_text",
            "note": "Table 2, whole-cell recordings at 34 C"},
    "gain": {"status": "free", "quantity": "overall gain of the stage", "note": "no data; explore freely", "bounds": [0, 4]}
  }
}
```

## Species and regions as layers

A profile may `extends` another one (an id, a file name or a path). Its keys are merged over the parent's (dicts merge,
lists and scalars are replaced) and its `provenance` entries over the parent's. A key the child sets needs its own entry:
the parent's entry would describe another species.

```json
{"id": "my_stage_rat_v1", "extends": "my_stage_mouse_v1", "tau": 18.0,
 "provenance": {"tau": {"status": "measured", "quantity": "membrane time constant of L2/3 pyramidal cells (ms)",
                        "species": "rat", "source": ["doi:10.xxxx/zzzz"], "evidence": "abstract"}}}
```

Load a resolved profile with `neurogenesis.profiles.load_parameter_profile("my_stage_rat_v1")`. `provenance_counts` tells
how much of a set of profiles is measured, derived, assumed or free.

## Adding a profile (checklist)

1. One profile per pull request, in `examples/profiles/` (or a folder you point `$NEUROGENESIS_PROFILES` at).
2. Every parameter has a status, a `quantity`, and, if measured or derived, a DOI and what was read.
3. Say which species, region and age the number is from, and write the caveat in `note` when you apply a value to
   another region.
4. `python -m neurogenesis profile check <file> --online` passes.
5. Say in the pull request which values were checked in the full text and which only in the abstract.
6. Reference outputs of a profile (tables of expected counts, say) are `derived` from its parameters: do not present them
   as measurements.

Validation against observations: when a use case claims that a simulation recovers independent observations, the
observations it compares with must not have been used to fix its parameters (see the module validation rules in
{doc}`../development/contributing`).
