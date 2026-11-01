/* Golden-fixture test of nglif: nglif_test <fixtures dir>. Every fixture of MANIFEST.txt must give exactly its
 * expected spikes; NGB1 files must survive a write / read round trip; the live API (inject, set_external) must match
 * nglif_run. Exit status 0 when everything passes. */
#include "nglif.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int32_t *read_i32(const char *path, long *count) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long bytes = ftell(f);
    fseek(f, 0, SEEK_SET);
    int32_t *a = (int32_t *)malloc((size_t)bytes + 4);
    size_t got = a ? fread(a, 1, (size_t)bytes, f) : 0;
    fclose(f);
    if (!a || got != (size_t)bytes) { free(a); return NULL; }
    const uint16_t one = 1;
    if (*(const uint8_t *)&one != 1)          /* big-endian host: files are little endian */
        for (long k = 0; k < bytes / 4; k++) {
            uint8_t *b = (uint8_t *)&a[k], t;
            t = b[0]; b[0] = b[3]; b[3] = t; t = b[1]; b[1] = b[2]; b[2] = t;
        }
    *count = bytes / 4;
    return a;
}

static int same_network(const nglif_network *a, const nglif_network *b) {
    if (a->n != b->n || a->e != b->e) return 0;
    size_t N = (size_t)a->n, E = (size_t)a->e;
    const int32_t *ai[] = {a->mode, a->shift_v, a->shift_s, a->base_weight, a->burst_period, a->burst_duty, a->refractory, a->role, a->compartment, a->threshold};
    const int32_t *bi[] = {b->mode, b->shift_v, b->shift_s, b->base_weight, b->burst_period, b->burst_duty, b->refractory, b->role, b->compartment, b->threshold};
    for (int k = 0; k < 10; k++) if (memcmp(ai[k], bi[k], N * 4)) return 0;
    const double *ad[] = {a->pos, a->dir, a->poisson_hz, a->conn_radius, a->conn_prob};
    const double *bd[] = {b->pos, b->dir, b->poisson_hz, b->conn_radius, b->conn_prob};
    for (int k = 0; k < 5; k++) if (memcmp(ad[k], bd[k], (k < 2 ? 3 : 1) * N * 8)) return 0;
    const int32_t *as[] = {a->pre, a->post, a->weight, a->delay}, *bs[] = {b->pre, b->post, b->weight, b->delay};
    for (int k = 0; k < 4; k++) if (memcmp(as[k], bs[k], E * 4)) return 0;
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s <fixtures dir>\n", argv[0]); return 2; }
    const char *dir = argv[1];
    char path[4096], err[512], line[1024];
    snprintf(path, sizeof path, "%s/MANIFEST.txt", dir);
    FILE *m = fopen(path, "r");
    if (!m) { fprintf(stderr, "cannot open %s\n", path); return 2; }
    int failures = 0, cases = 0;
    while (fgets(line, sizeof line, m)) {
        char name[256], ext_name[256];
        int ticks;
        unsigned long seed;
        if (line[0] == '#' || sscanf(line, "%255s %d %lu %255s", name, &ticks, &seed, ext_name) != 4) continue;
        cases++;
        snprintf(path, sizeof path, "%s/%s.ngb", dir, name);
        nglif_network *net = nglif_network_read(path, err, sizeof err);
        if (!net) { printf("FAIL %s: %s\n", name, err); failures++; continue; }

        int32_t *ext = NULL;
        long n_ext = 0;
        if (strcmp(ext_name, "-") != 0) {
            snprintf(path, sizeof path, "%s/%s", dir, ext_name);
            ext = read_i32(path, &n_ext);
            if (!ext || n_ext != net->n) { printf("FAIL %s: bad external currents\n", name); failures++; nglif_network_free(net); free(ext); continue; }
        }
        long n_exp = 0;
        snprintf(path, sizeof path, "%s/%s.spikes.i32", dir, name);
        int32_t *expected = read_i32(path, &n_exp);
        if (!expected) { printf("FAIL %s: no expected spikes\n", name); failures++; nglif_network_free(net); free(ext); continue; }
        long want = n_exp / 2;

        /* 1. nglif_run */
        nglif_sim *sim = nglif_create(net, (uint32_t)seed);
        nglif_set_external(sim, ext);
        int32_t *t = (int32_t *)malloc(((size_t)want + 1) * 4), *i = (int32_t *)malloc(((size_t)want + 1) * 4);
        int64_t got = nglif_run(sim, ticks, t, i, want);
        int ok = got == want;
        for (long k = 0; ok && k < want; k++) ok = t[k] == expected[2 * k] && i[k] == expected[2 * k + 1];
        if (!ok) {
            long k = 0;
            while (k < want && k < got && t[k] == expected[2 * k] && i[k] == expected[2 * k + 1]) k++;
            printf("FAIL %s: %lld spikes, expected %ld; first difference at spike %ld\n", name, (long long)got, want, k);
            failures++;
        }
        nglif_free(sim);

        /* 2. the live API: external current as a per-tick pulse on half the ticks must give the same raster */
        sim = nglif_create(net, (uint32_t)seed);
        long k = 0;
        int live_ok = 1;
        int32_t *buf = (int32_t *)malloc(((size_t)net->n + 1) * 4);
        for (int tick = 0; tick < ticks && live_ok; tick++) {
            if (ext && (tick & 1)) {
                nglif_set_external(sim, NULL);
                for (int32_t j = 0; j < net->n; j++) if (ext[j]) nglif_inject(sim, j, ext[j]);
            } else {
                nglif_set_external(sim, ext);
            }
            int32_t c = nglif_step(sim, buf, net->n);
            for (int32_t j = 0; j < c && live_ok; j++, k++)
                live_ok = k < want && expected[2 * k] == tick && expected[2 * k + 1] == buf[j] && nglif_last_spike(sim)[buf[j]] == tick;
        }
        if (!live_ok || k != want) { printf("FAIL %s: live API (step, inject, set_external) differs\n", name); failures++; }
        free(buf);
        nglif_free(sim);

        /* 3. NGB1 round trip */
        snprintf(path, sizeof path, "%s/%s.roundtrip.tmp", dir, name);
        nglif_network *back = NULL;
        if (nglif_network_write(net, path) == 0) back = nglif_network_read(path, err, sizeof err);
        remove(path);
        if (!back || !same_network(net, back)) { printf("FAIL %s: NGB1 round trip\n", name); failures++; }
        else if (ok && live_ok) printf("ok   %s: %ld spikes in %d ticks (%d neurons, %d synapses)\n", name, want, ticks, net->n, net->e);

        nglif_network_free(back);
        nglif_network_free(net);
        free(ext); free(expected); free(t); free(i);
    }
    fclose(m);
    if (!cases) { printf("FAIL: no fixtures in %s\n", dir); return 1; }
    printf("%d fixtures, %d failures\n", cases, failures);
    return failures ? 1 : 0;
}
