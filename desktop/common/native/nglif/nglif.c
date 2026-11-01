/* nglif: portable integer LIF kernel and NGB1 I/O. See nglif.h. */
#include "nglif.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------------------------------------------ integer helpers */

/* x >> k with floor semantics (Python, numpy), whatever the compiler does with negative operands. */
static int32_t asr(int32_t x, int32_t k) {
    if (k <= 0) return x;
    if (k > 31) return x < 0 ? -1 : 0;
    return x >= 0 ? (int32_t)((uint32_t)x >> k) : (int32_t)~((uint32_t)~x >> k);
}

/* a + b wrapping around in 32 bits, without undefined behaviour. */
static int32_t wadd(int32_t a, int32_t b) {
    uint32_t s = (uint32_t)a + (uint32_t)b;
    return s <= (uint32_t)INT32_MAX ? (int32_t)s : (int32_t)(s - 2147483648u) - (int32_t)2147483647 - 1;
}

/* x - max(1, x >> k) for x > 0; x - min(-1, x >> k) for x < 0 (reference _decay). */
static int32_t decay(int32_t x, int32_t k) {
    if (x > 0) { int32_t s = asr(x, k); return x - (s > 1 ? s : 1); }
    if (x < 0) { int32_t s = asr(x, k); return x - (s < -1 ? s : -1); }
    return 0;
}

/* min(2^32 - 1, int(hz / 1000 * 2^32)), as reference.py (0 for negative or NaN rates). */
static uint32_t poisson_threshold(double hz) {
    double x = (hz / 1000.0) * 4294967296.0;
    if (!(x > 0.0)) return 0;
    if (x >= 4294967295.0) return 4294967295u;
    return (uint32_t)x;
}

/* ------------------------------------------------------------------------------------------------------- networks */

nglif_network *nglif_network_new(int32_t n, int32_t e) {
    if (n < 0 || e < 0) return NULL;
    nglif_network *net = (nglif_network *)calloc(1, sizeof *net);
    if (!net) return NULL;
    net->n = n; net->e = e;
    size_t N = (size_t)n + 1, E = (size_t)e + 1;            /* +1: never a zero-size allocation */
    net->pos = (double *)calloc(3 * N, sizeof(double));
    net->dir = (double *)calloc(3 * N, sizeof(double));
    int32_t **ints[] = {&net->mode, &net->shift_v, &net->shift_s, &net->base_weight, &net->burst_period, &net->burst_duty,
                        &net->refractory, &net->role, &net->compartment, &net->threshold};
    int ok = net->pos && net->dir;
    for (size_t k = 0; k < sizeof ints / sizeof *ints; k++) ok = ok && (*ints[k] = (int32_t *)calloc(N, sizeof(int32_t)));
    double **dbls[] = {&net->poisson_hz, &net->conn_radius, &net->conn_prob};
    for (size_t k = 0; k < sizeof dbls / sizeof *dbls; k++) ok = ok && (*dbls[k] = (double *)calloc(N, sizeof(double)));
    int32_t **syn[] = {&net->pre, &net->post, &net->weight, &net->delay};
    for (size_t k = 0; k < sizeof syn / sizeof *syn; k++) ok = ok && (*syn[k] = (int32_t *)calloc(E, sizeof(int32_t)));
    if (!ok) { nglif_network_free(net); return NULL; }
    return net;
}

void nglif_network_free(nglif_network *net) {
    if (!net) return;
    void *p[] = {net->pos, net->dir, net->mode, net->shift_v, net->shift_s, net->base_weight, net->burst_period,
                 net->burst_duty, net->refractory, net->role, net->compartment, net->threshold, net->poisson_hz,
                 net->conn_radius, net->conn_prob, net->pre, net->post, net->weight, net->delay};
    for (size_t k = 0; k < sizeof p / sizeof *p; k++) free(p[k]);
    free(net);
}

static int little_endian(void) { const uint16_t one = 1; return *(const uint8_t *)&one == 1; }

static void swap_bytes(void *p, size_t width, size_t count) {
    uint8_t *b = (uint8_t *)p;
    for (size_t k = 0; k < count; k++, b += width)
        for (size_t i = 0; i < width / 2; i++) { uint8_t t = b[i]; b[i] = b[width - 1 - i]; b[width - 1 - i] = t; }
}

/* Reads `count` little-endian values of `width` bytes. */
static int read_le(FILE *f, void *dst, size_t width, size_t count) {
    if (count && fread(dst, width, count, f) != count) return -1;
    if (!little_endian()) swap_bytes(dst, width, count);
    return 0;
}

static int write_le(FILE *f, const void *src, size_t width, size_t count) {
    if (!count) return 0;
    if (little_endian()) return fwrite(src, width, count, f) == count ? 0 : -1;
    uint8_t *tmp = (uint8_t *)malloc(width * count);
    if (!tmp) return -1;
    memcpy(tmp, src, width * count);
    swap_bytes(tmp, width, count);
    int r = fwrite(tmp, width, count, f) == count ? 0 : -1;
    free(tmp);
    return r;
}

static void set_err(char *err, size_t len, const char *msg, const char *path) {
    if (err && len) snprintf(err, len, "%s: %s", path ? path : "", msg);
}

nglif_network *nglif_network_read(const char *path, char *err, size_t err_len) {
    FILE *f = fopen(path, "rb");
    if (!f) { set_err(err, err_len, "cannot open", path); return NULL; }
    char magic[4];
    int32_t head[3];
    if (fread(magic, 1, 4, f) != 4 || memcmp(magic, "NGB1", 4) != 0 || read_le(f, head, 4, 3) != 0 || head[0] < 0 || head[1] < 0) {
        fclose(f); set_err(err, err_len, "not an NGB1 network file", path); return NULL;
    }
    int32_t n = head[0], e = head[1];
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); set_err(err, err_len, "cannot seek", path); return NULL; }
    long size = ftell(f);
    double expected = 16.0 + 112.0 * n + 16.0 * e;
    if (size < 0 || (double)size != expected) { fclose(f); set_err(err, err_len, "wrong size for its neuron and synapse counts", path); return NULL; }
    fseek(f, 16, SEEK_SET);
    nglif_network *net = nglif_network_new(n, e);
    if (!net) { fclose(f); set_err(err, err_len, "out of memory", path); return NULL; }
    size_t N = (size_t)n, E = (size_t)e;
    int bad = read_le(f, net->pos, 8, 3 * N) || read_le(f, net->dir, 8, 3 * N);
    int32_t *ints[] = {net->mode, net->shift_v, net->shift_s, net->base_weight, net->burst_period, net->burst_duty,
                       net->refractory, net->role, net->compartment, net->threshold};
    for (size_t k = 0; k < 10; k++) bad = bad || read_le(f, ints[k], 4, N);
    double *dbls[] = {net->poisson_hz, net->conn_radius, net->conn_prob};
    for (size_t k = 0; k < 3; k++) bad = bad || read_le(f, dbls[k], 8, N);
    int32_t *syn[] = {net->pre, net->post, net->weight, net->delay};
    for (size_t k = 0; k < 4; k++) bad = bad || read_le(f, syn[k], 4, E);
    fclose(f);
    if (bad) { nglif_network_free(net); set_err(err, err_len, "truncated file", path); return NULL; }
    return net;
}

int nglif_network_write(const nglif_network *net, const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    int32_t head[3] = {net->n, net->e, 0};
    size_t N = (size_t)net->n, E = (size_t)net->e;
    int bad = fwrite("NGB1", 1, 4, f) != 4 || write_le(f, head, 4, 3) || write_le(f, net->pos, 8, 3 * N) || write_le(f, net->dir, 8, 3 * N);
    const int32_t *ints[] = {net->mode, net->shift_v, net->shift_s, net->base_weight, net->burst_period, net->burst_duty,
                             net->refractory, net->role, net->compartment, net->threshold};
    for (size_t k = 0; k < 10; k++) bad = bad || write_le(f, ints[k], 4, N);
    const double *dbls[] = {net->poisson_hz, net->conn_radius, net->conn_prob};
    for (size_t k = 0; k < 3; k++) bad = bad || write_le(f, dbls[k], 8, N);
    const int32_t *syn[] = {net->pre, net->post, net->weight, net->delay};
    for (size_t k = 0; k < 4; k++) bad = bad || write_le(f, syn[k], 4, E);
    return (fclose(f) != 0 || bad) ? -1 : 0;
}

/* --------------------------------------------------------------------------------------------------- simulation */

struct nglif_sim {
    int32_t n;
    int64_t tick;
    uint32_t rng;
    /* parameters */
    int32_t *shift_v, *shift_s, *mode, *period, *duty, *refractory, *threshold;
    uint32_t *poisson;
    /* CSR by presynaptic neuron */
    int32_t *row, *col, *weight;
    uint32_t *delay;
    /* state */
    int32_t *v, *isyn, *phase, *refr, *last, *ext, *pulse;
    uint32_t *bits;
    int has_ext, has_pulse;
};

void nglif_free(nglif_sim *s) {
    if (!s) return;
    void *p[] = {s->shift_v, s->shift_s, s->mode, s->period, s->duty, s->refractory, s->threshold, s->poisson, s->row,
                 s->col, s->weight, s->delay, s->v, s->isyn, s->phase, s->refr, s->last, s->ext, s->pulse, s->bits};
    for (size_t k = 0; k < sizeof p / sizeof *p; k++) free(p[k]);
    free(s);
}

nglif_sim *nglif_create(const nglif_network *net, uint32_t seed) {
    if (!net || net->n < 0) return NULL;
    nglif_sim *s = (nglif_sim *)calloc(1, sizeof *s);
    if (!s) return NULL;
    int32_t n = net->n;
    size_t N = (size_t)n + 1;
    s->n = n; s->rng = seed;
    int32_t **i32[] = {&s->shift_v, &s->shift_s, &s->mode, &s->period, &s->duty, &s->refractory, &s->threshold,
                       &s->v, &s->isyn, &s->phase, &s->refr, &s->last, &s->ext, &s->pulse, &s->row};
    int ok = 1;
    for (size_t k = 0; k < sizeof i32 / sizeof *i32; k++) ok = ok && (*i32[k] = (int32_t *)calloc(N + 1, sizeof(int32_t)));
    ok = ok && (s->poisson = (uint32_t *)calloc(N, sizeof(uint32_t))) && (s->bits = (uint32_t *)calloc(N, sizeof(uint32_t)));
    if (!ok) { nglif_free(s); return NULL; }
    for (int32_t i = 0; i < n; i++) {
        s->shift_v[i] = net->shift_v[i]; s->shift_s[i] = net->shift_s[i]; s->mode[i] = net->mode[i];
        s->period[i] = net->burst_period[i]; s->duty[i] = net->burst_duty[i]; s->refractory[i] = net->refractory[i];
        s->threshold[i] = net->threshold[i]; s->poisson[i] = poisson_threshold(net->poisson_hz[i]);
        s->last[i] = INT32_MIN;
    }
    /* CSR: count synapses per presynaptic neuron, then fill in input order */
    int32_t e = 0;
    for (int32_t k = 0; k < net->e; k++)
        if (net->pre[k] >= 0 && net->pre[k] < n && net->post[k] >= 0 && net->post[k] < n) { s->row[net->pre[k] + 1]++; e++; }
    for (int32_t i = 0; i < n; i++) s->row[i + 1] += s->row[i];
    size_t E = (size_t)e + 1;
    s->col = (int32_t *)calloc(E, sizeof(int32_t));
    s->weight = (int32_t *)calloc(E, sizeof(int32_t));
    s->delay = (uint32_t *)calloc(E, sizeof(uint32_t));
    int32_t *fill = (int32_t *)calloc(N, sizeof(int32_t));
    if (!s->col || !s->weight || !s->delay || !fill) { free(fill); nglif_free(s); return NULL; }
    memcpy(fill, s->row, (size_t)n * sizeof(int32_t));
    for (int32_t k = 0; k < net->e; k++) {
        int32_t a = net->pre[k], b = net->post[k];
        if (a < 0 || a >= n || b < 0 || b >= n) continue;
        int32_t j = fill[a]++;
        s->col[j] = b; s->weight[j] = net->weight[k];
        s->delay[j] = (net->delay[k] < 0 || net->delay[k] > 31) ? 32u : (uint32_t)net->delay[k];   /* 32: never arrives */
    }
    free(fill);
    return s;
}

int32_t nglif_num_neurons(const nglif_sim *s) { return s->n; }
int64_t nglif_tick(const nglif_sim *s) { return s->tick; }
uint32_t nglif_rng_state(const nglif_sim *s) { return s->rng; }
const int32_t *nglif_potential(const nglif_sim *s) { return s->v; }
const int32_t *nglif_current(const nglif_sim *s) { return s->isyn; }
const int32_t *nglif_last_spike(const nglif_sim *s) { return s->last; }

void nglif_set_external(nglif_sim *s, const int32_t *ext) {
    s->has_ext = 0;
    for (int32_t i = 0; i < s->n; i++) {
        s->ext[i] = ext ? ext[i] : 0;
        if (s->ext[i]) s->has_ext = 1;
    }
}

void nglif_inject(nglif_sim *s, int32_t i, int32_t current) {
    if (i < 0 || i >= s->n) return;
    s->pulse[i] = wadd(s->pulse[i], current);
    s->has_pulse = 1;
}

int32_t nglif_step(nglif_sim *s, int32_t *spikes, int32_t cap) {
    int32_t n = s->n, count = 0;
    int32_t now = (int32_t)(uint32_t)(uint64_t)s->tick;
    for (int32_t i = 0; i < n; i++) {
        int32_t cur = s->isyn[i];
        if (s->has_ext) cur = wadd(cur, s->ext[i]);
        if (s->has_pulse) { cur = wadd(cur, s->pulse[i]); s->pulse[i] = 0; }
        int32_t v = decay(s->v[i], s->shift_v[i]);
        cur = decay(cur, s->shift_s[i]);
        s->isyn[i] = cur;
        v += asr(cur, 2);
        if (v > 2048) v = 2048; else if (v < -2048) v = -2048;
        if (s->mode[i] == 1) {
            uint32_t x = s->rng;
            x ^= x << 13; x ^= x >> 17; x ^= x << 5;
            s->rng = x;
            if (x < s->poisson[i]) v = s->threshold[i];
        } else if (s->mode[i] == 2) {
            int32_t period = s->period[i] ? s->period[i] : 200, duty = s->duty[i] ? s->duty[i] : 24;
            int32_t ph = (s->phase[i] + 1) % period;
            s->phase[i] = ph;
            if (ph < duty && (ph & 3) == 0) v = s->threshold[i];
        }
        uint32_t fired = v >= s->threshold[i] ? 1u : 0u;
        if (s->refr[i] > 0) { s->refr[i] -= 1; fired = 0; v = -256; }
        if (fired) {
            s->refr[i] = s->refractory[i];
            s->v[i] = -256;
            s->last[i] = now;
            if (spikes && count < cap) spikes[count] = i;
            count++;
        } else {
            s->v[i] = v;
        }
        s->bits[i] = (s->bits[i] << 1) | fired;
    }
    s->has_pulse = 0;
    for (int32_t i = 0; i < n; i++) {
        uint32_t bf = s->bits[i];
        if (!bf) continue;
        for (int32_t k = s->row[i]; k < s->row[i + 1]; k++)
            if (s->delay[k] < 32u && ((bf >> s->delay[k]) & 1u)) s->isyn[s->col[k]] = wadd(s->isyn[s->col[k]], s->weight[k]);
    }
    s->tick++;
    return count;
}

int64_t nglif_run(nglif_sim *s, int32_t ticks, int32_t *t, int32_t *i, int64_t cap) {
    int32_t *buf = (int32_t *)malloc(((size_t)s->n + 1) * sizeof(int32_t));
    if (!buf) return -1;
    int64_t total = 0;
    for (int32_t k = 0; k < ticks; k++) {
        int32_t c = nglif_step(s, buf, s->n);
        for (int32_t j = 0; j < c; j++, total++)
            if (total < cap) { if (t) t[total] = k; if (i) i[total] = buf[j]; }
    }
    free(buf);
    return total;
}
