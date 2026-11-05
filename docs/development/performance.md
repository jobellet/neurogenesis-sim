# Performance rules for population simulations

These rules come from measurements on one workload: populations of 256 to 4096 small networks of the integer kernel
(256 neurons, 3-8 k synapses, 1 ms ticks) with per-synapse plasticity (STDP, a three-factor rule, short-term
plasticity), simulated online for hours. They were measured on NVIDIA A100 (40 MB L2) and RTX PRO 6000 Blackwell
(128 MB L2) GPUs in November 2026. The numbers are specific to that workload; the rules should carry over to any
simulation where many small networks run in parallel, tick by tick.

## Measured speeds (network-seconds simulated per wall-clock second)

| Implementation | A100 | RTX PRO 6000 |
|---|---|---|
| `jax.lax.scan` over ticks, `vmap` over 256 networks, synapses padded to 8192 | 657 | ~1,500 |
| same, 4096 networks, padding 6144, `scan(unroll=4)` | 1,712 | not measured |
| fused CUDA kernel (one thread block per network), global memory, 1024 networks | 5,478 | 24,272 |
| fused CUDA kernel, synapses in shared memory, 4096 networks | 8,264 | 17,194 |

The fused kernel gives the same spikes, rewards and integer state as the JAX path over 10-20 s of simulated time
(16 networks each, plasticity on); float weights differ by at most 1e-3 where a sum is taken in a different order.

## Rules

1. **Measure before optimising, and do not trust "GPU utilisation".** `nvidia-smi` showed 99 % while the JAX path
   used under 1 % of the GPU's arithmetic throughput. Utilisation only says that some kernel is running. Compute the
   achieved operations or bytes per second and compare them with the device's peak.

2. **A tick-by-tick `lax.scan` is limited by its many small steps, not by arithmetic.** Each tick runs dozens of
   small kernels and moves every array through memory. Larger batches and `unroll=4` gave ×2.6 at most; beyond about
   1024 networks the JAX path is limited by memory traffic.

3. **For small networks, fuse the whole time loop into one kernel, with one thread block per network.** The network
   state stays on chip for a whole chunk (here 5 s of simulated time), and the host only intervenes between chunks
   (births, deaths, logging). This gave ×8-16 over the JAX path.

4. **Never compute on padding.** Stacking networks of different sizes needs padded arrays, but the kernel should loop
   to each network's own synapse count. Padding then costs memory, not time.

5. **Pack static data; share coefficients that genes share.** A synapse's pre, post, delay, plasticity group and sign
   fit in one 32-bit word. Plasticity coefficients that are set per group by the genome are stored per group, not
   per synapse. Fewer bytes per synapse per tick means a faster memory-bound kernel.

6. **Choose shared versus global memory by measuring on each device: autotune it.** Keeping each network's synapses in
   shared memory was ×1.5 faster on the A100 (the state does not fit in its L2) but ×1.6 slower on the RTX PRO 6000
   (its L2 already holds the state, and shared memory limits how many blocks run at once). Run the first chunks
   both ways and keep the faster one; both give identical results.

7. **Integer state is exact on any backend; floats need the same operations in the same order.**
   - Integer currents can be accumulated with atomics in any order and stay exact.
   - Float plasticity matches XLA bit for bit only with the same operation order and no fused multiply-add (`nvcc
     --fmad=false`).
   - Reductions (dot products, sums over neurons) are the remaining source of last-bit differences. Test them with
     tolerances, and test spikes and rewards for equality.

8. **Use counter-based random numbers.** A stateless hash of (key, tick, neuron) is cheap, parallel and identical on
   every backend. `jax.random.fold_in` per tick is expensive. The kernel's sequential xorshift for Poisson neurons is
   exact but serial: one thread draws for all Poisson neurons. A per-neuron counter-based draw would remove that
   serial step; it changes the random stream, so it should be a new, versioned option.

9. **Keep the host out of the time loop and buffers on the device.** Pass the start time as a device buffer, not as
   a compile-time attribute (otherwise every chunk recompiles). Donate state buffers so that they are updated in
   place. Replace an individual by writing its slice, never by rebuilding the population.

10. **Expose fused kernels through the XLA FFI.** The kernel then runs inside `jax.jit`, uses JAX's stream and
    buffers, and needs no extra dependency: the CUDA wheels that JAX installs include `nvcc`.

11. **Request the resources the job really uses.** A GPU population job used one CPU core and about 1 GB of host
    memory; 4 cores and 48 GB had been reserved.

12. **Event-driven updates are the next large step, but they are not bit-exact.** At about 5 Hz, almost all
    per-synapse work is decay of traces. Computing the decay in closed form only when a synapse is used would cut
    the work several-fold. But `x * d**n` does not round like n multiplications, so such a kernel must be validated
    statistically rather than spike for spike.

## Where this could go in the toolbox

- `neurogenesis.spiking.cuda`: the integer tick plus generic per-synapse plasticity hooks as a fused, FFI-registered
  kernel, with the JAX tick as its reference and a spike-for-spike test.
- A population runner that owns device buffers, runs chunks, autotunes the memory mode and replaces individuals in
  place.
- A counter-based Poisson option in the kernel (versioned, since it changes the random stream).

A first implementation for one model lives in the who-carries-anticipation project (`src/wca/cuda/forage_kernel.cu`,
`src/wca/forage_cuda.py`, `scripts/validate_cuda.py`).
