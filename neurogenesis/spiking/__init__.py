"""Integer leaky integrate-and-fire networks: data model, reference simulator, JAX kernel (bit-identical), batched runs."""
from .network import NeuronData, SNNNetwork, SynapseData

__all__ = ["NeuronData", "SNNNetwork", "SynapseData"]
