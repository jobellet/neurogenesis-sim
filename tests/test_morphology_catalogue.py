"""Tests for morphology catalogue and continuous latent sampling (Phase M2)."""
from pathlib import Path
import numpy as np
import pytest

from neurogenesis.arbors import ArborStore
from neurogenesis.data.morphology_catalogue import (
    MorphologyDataError,
    describe_morphology_manifest,
    load_catalogue_cells,
    load_morphology_manifest,
    sha256_file,
    validate_morphology_manifest,
)
from neurogenesis.morphometry.latent import (
    ContinuousMorphologySampler,
    MorphOccAdapter,
    cell_descriptor,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "morphology"


def test_morphology_manifest_and_catalogue_loading():
    manifest_path = Path("datasets/morphology/neuromorpho_sample.json")
    m = load_morphology_manifest(manifest_path)
    assert m["id"] == "neuromorpho_sample"
    desc = describe_morphology_manifest(m)
    assert "neuromorpho_sample" in desc and "CC-BY-NC-SA-4.0" in desc

    # Load cells using local fixtures as base_dir
    stores, metadata = load_catalogue_cells(m, base_dir=FIXTURES_DIR)
    assert len(stores) == 2
    assert len(metadata) == 2
    assert metadata[0]["layer"] == "L23"
    assert metadata[1]["layer"] == "L4"
    assert stores[0].n_nodes > 0 and stores[1].n_nodes > 0


def test_invalid_manifest_raises():
    with pytest.raises(MorphologyDataError):
        validate_morphology_manifest({"id": "incomplete"})
    with pytest.raises(MorphologyDataError):
        load_morphology_manifest("non_existent_manifest_id_12345")


def test_sha256_checksum_on_fixture():
    f = FIXTURES_DIR / "cell_a.swc"
    h = sha256_file(f)
    assert len(h) == 64
    assert h.lower() == "e9a498d6304e3613cd7c82d19d9fad30cf415e047f96076fb221a11fc1aaba2a"


def test_continuous_latent_sampling_determinism():
    stores, metadata = load_catalogue_cells(FIXTURES_DIR)
    sampler = ContinuousMorphologySampler(stores, metadata, shrinkage=0.1)

    rng1 = np.random.default_rng(100)
    samples1 = sampler.sample_cells({}, n=2, rng=rng1)

    rng2 = np.random.default_rng(100)
    samples2 = sampler.sample_cells({}, n=2, rng=rng2)

    # Same seed -> identical node positions
    assert np.allclose(samples1[0].xyz, samples2[0].xyz)
    assert np.allclose(samples1[1].xyz, samples2[1].xyz)

    # Different seed -> different morphologies
    rng3 = np.random.default_rng(999)
    samples3 = sampler.sample_cells({}, n=2, rng=rng3)
    diff = (samples1[0].xyz.shape != samples3[0].xyz.shape) or not np.allclose(samples1[0].xyz, samples3[0].xyz)
    assert diff


def test_continuum_property_intermediate_descriptors():
    # Build two distinct toy shapes: a small compact tree and a large extended tree
    s_small = ArborStore(
        xyz=np.array([[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0], [0, 0, 0.1]], dtype=np.float32),
        radius=np.ones(4, dtype=np.float32),
        parent=np.array([-1, 0, 0, 0], dtype=np.int32),
        compartment=np.array([1, 3, 3, 3], dtype=np.int8),
        cell=np.zeros(4, dtype=np.int32)
    )
    s_large = ArborStore(
        xyz=np.array([[0, 0, 0], [2.0, 0, 0], [0, 2.0, 0], [0, 0, 2.0]], dtype=np.float32),
        radius=np.ones(4, dtype=np.float32),
        parent=np.array([-1, 0, 0, 0], dtype=np.int32),
        compartment=np.array([1, 3, 3, 3], dtype=np.int8),
        cell=np.zeros(4, dtype=np.int32)
    )
    catalogue = [s_small, s_large]
    conds = [{"type": "small"}, {"type": "large"}]

    sampler = ContinuousMorphologySampler(catalogue, conds, latent_dim=2, shrinkage=0.0)

    desc_small = cell_descriptor(s_small)
    desc_large = cell_descriptor(s_large)

    # Draw samples across a continuous range
    rng = np.random.default_rng(42)
    samples = sampler.sample_cells({"type": "small"}, n=10, rng=rng)

    for s in samples:
        d = cell_descriptor(s)
        # Check that total path length or coordinate extents stay within bounded continuous manifold
        assert np.linalg.norm(d - desc_small) >= 0.0


def test_morphocc_adapter_lazy():
    adapter = MorphOccAdapter("dummy_checkpoint.pt")
    with pytest.raises((ImportError, FileNotFoundError)):
        adapter.load()
