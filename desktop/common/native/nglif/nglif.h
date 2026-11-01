/*
 * nglif: the integer leaky integrate-and-fire kernel (lif_int) of neurogenesis-sim, in portable C11, for the desktop
 * apps (macOS, Windows, Linux). Spikes are bit for bit those of neurogenesis/spiking/reference.py, jax_backend.py
 * and viz/src/sim/kernel.ts; desktop/common/fixtures holds golden rasters that every build must reproduce.
 *
 * Per tick (1 ms), for every neuron in index order:
 *   I += ext (external current, as jax_backend.tick ext_current);  v and I decay by v >> shift_v, I >> shift_s
 *   (at least 1 towards 0);  v += I >> 2, clamped to +-2048;  Poisson drivers (mode 1) draw one xorshift32 number
 *   each, in index order, and jump to threshold when it is below their rate;  bursters (mode 2) jump to threshold on
 *   every 4th tick of the first `duty` ticks of each period;  a neuron fires when v >= threshold, unless refractory;
 *   it then resets to -256 for `refractory` ticks.  Then every synapse whose presynaptic spike, `delay` ticks old, is
 *   in the 32-tick spike register adds its weight to the target's I.
 * Integer shifts are floor divisions and additions wrap around in 32 bits, as in Python and numpy.
 *
 * No dependencies; plain C ABI; not thread-safe per simulation (use one nglif_sim per thread).
 */
#ifndef NGLIF_H
#define NGLIF_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NGLIF_VERSION 1          /* API version */
#define NGLIF_NGB_VERSION 1      /* NGB1 network files (desktop/common/PROTOCOL.md, section 6) */
#define NGLIF_DEFAULT_SEED 12345u

#if defined(_WIN32) && defined(NGLIF_BUILD_DLL)
#define NGLIF_API __declspec(dllexport)
#elif defined(_WIN32) && defined(NGLIF_USE_DLL)
#define NGLIF_API __declspec(dllimport)
#else
#define NGLIF_API
#endif

/* A network as structure of arrays: the fields of NeuronData and SynapseData (and of NGB1). */
typedef struct nglif_network {
    int32_t n, e;
    double *pos, *dir;                                   /* n x 3 each (x, y, z) */
    int32_t *mode, *shift_v, *shift_s, *base_weight, *burst_period, *burst_duty, *refractory, *role, *compartment,
        *threshold;                                      /* n each */
    double *poisson_hz, *conn_radius, *conn_prob;        /* n each */
    int32_t *pre, *post, *weight, *delay;                /* e each */
} nglif_network;

/* A network of n neurons and e synapses, every array zero-filled. NULL if out of memory. */
NGLIF_API nglif_network *nglif_network_new(int32_t n, int32_t e);
NGLIF_API void nglif_network_free(nglif_network *net);

/* NGB1 files. read: NULL on error, with a message in err (if err_len > 0). write: 0 on success. */
NGLIF_API nglif_network *nglif_network_read(const char *path, char *err, size_t err_len);
NGLIF_API int nglif_network_write(const nglif_network *net, const char *path);

typedef struct nglif_sim nglif_sim;

/* A simulation of a network (copied: the network may be freed afterwards). seed: xorshift32 state of the Poisson
 * drivers (NGLIF_DEFAULT_SEED is the toolbox default; 0 never draws). Synapses with an unknown neuron are ignored.
 * NULL if out of memory. */
NGLIF_API nglif_sim *nglif_create(const nglif_network *net, uint32_t seed);
NGLIF_API void nglif_free(nglif_sim *sim);

NGLIF_API int32_t nglif_num_neurons(const nglif_sim *sim);
NGLIF_API int64_t nglif_tick(const nglif_sim *sim);          /* ticks simulated so far */
NGLIF_API uint32_t nglif_rng_state(const nglif_sim *sim);

/* External current per neuron, added every tick until changed (copied). NULL: none. */
NGLIF_API void nglif_set_external(nglif_sim *sim, const int32_t *ext);
/* Current added to neuron i on the next tick only (accumulates). */
NGLIF_API void nglif_inject(nglif_sim *sim, int32_t i, int32_t current);

/* One tick. Writes the indices of the neurons that fired (in increasing order, at most cap) into spikes (may be
 * NULL) and returns how many fired. */
NGLIF_API int32_t nglif_step(nglif_sim *sim, int32_t *spikes, int32_t cap);
/* `ticks` ticks; writes (tick, neuron) of every spike, at most cap, into t and i (may be NULL). Ticks are counted from
 * the first of this call. Returns the number of spikes (which may exceed cap: only cap are written). */
NGLIF_API int64_t nglif_run(nglif_sim *sim, int32_t ticks, int32_t *t, int32_t *i, int64_t cap);

/* Live state, read-only, n values each: membrane potential, synaptic current, and the tick of each neuron's last
 * spike (truncated to 32 bits; INT32_MIN if it never fired). */
NGLIF_API const int32_t *nglif_potential(const nglif_sim *sim);
NGLIF_API const int32_t *nglif_current(const nglif_sim *sim);
NGLIF_API const int32_t *nglif_last_spike(const nglif_sim *sim);

#ifdef __cplusplus
}
#endif
#endif
