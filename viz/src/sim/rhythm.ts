/**
 * Population rhythm of the running network, at 1-tick (1 ms) resolution, computed in the simulation worker.
 *
 * The page samples the shared memory about once per display frame (~15-30 simulated ms), too coarsely to resolve
 * alpha or gamma rhythms, so the worker keeps the last WINDOW per-tick spike counts and, every UPDATE_EVERY ticks,
 * publishes:
 *   - the dominant frequency (Hz of simulated time): 1000 / the first lag between MIN_LAG and MAX_LAG ms (100 Hz down
 *     to 4 Hz) where the autocorrelation of the population count has a local maximum within 80 % of its largest value
 *     (a periodic signal peaks at every multiple of its period); 0 without a positive peak or with a silent network;
 *   - a variability index: coefficient of variation of the population count in BIN-ms bins (0 for a constant rate,
 *     larger for bursty, synchronous activity).
 * Cost: O(WINDOW x (MAX_LAG - MIN_LAG)) operations per update, about 2,400 per tick.
 */
export const WINDOW = 1000;
export const UPDATE_EVERY = 100;
export const MIN_LAG = 10;
export const MAX_LAG = 250;
export const BIN = 5;

export class PopulationRhythm {
  private counts = new Float64Array(WINDOW);
  private head = 0;
  private filled = 0;
  private sinceUpdate = 0;
  public peakHz = 0;
  public variability = 0;

  reset(): void {
    this.counts.fill(0);
    this.head = 0;
    this.filled = 0;
    this.sinceUpdate = 0;
    this.peakHz = 0;
    this.variability = 0;
  }

  /** Adds one tick's spike count; returns true when the published values were recomputed. */
  push(count: number): boolean {
    this.counts[this.head] = count;
    this.head = (this.head + 1) % WINDOW;
    if (this.filled < WINDOW) this.filled++;
    if (++this.sinceUpdate < UPDATE_EVERY || this.filled < WINDOW) return false;
    this.sinceUpdate = 0;
    this.update();
    return true;
  }

  private update(): void {
    const x = new Float64Array(WINDOW);
    let mean = 0;
    for (let i = 0; i < WINDOW; i++) {
      x[i] = this.counts[(this.head + i) % WINDOW];     // oldest first
      mean += x[i];
    }
    mean /= WINDOW;
    let bm = 0, bv = 0;
    const nb = Math.floor(WINDOW / BIN);
    const bins = new Float64Array(nb);
    for (let b = 0; b < nb; b++) {
      for (let k = 0; k < BIN; k++) bins[b] += x[b * BIN + k];
      bm += bins[b];
    }
    bm /= nb;
    for (let b = 0; b < nb; b++) bv += (bins[b] - bm) * (bins[b] - bm);
    this.variability = bm > 0 ? Math.sqrt(bv / nb) / bm : 0;
    if (mean <= 0) {
      this.peakHz = 0;
      return;
    }
    for (let i = 0; i < WINDOW; i++) x[i] -= mean;
    // autocorrelation from MIN_LAG - 1 to MAX_LAG + 1 (neighbours for the local-maximum test)
    const ac = new Float64Array(MAX_LAG + 2);
    let best = 0;
    for (let lag = MIN_LAG - 1; lag <= MAX_LAG + 1; lag++) {
      let c = 0;
      for (let t = 0; t + lag < WINDOW; t++) c += x[t] * x[t + lag];
      ac[lag] = c / (WINDOW - lag);
      if (lag >= MIN_LAG && lag <= MAX_LAG && ac[lag] > best) best = ac[lag];
    }
    // a periodic signal peaks at every multiple of its period: take the first local maximum within 80 % of the largest
    let bestLag = 0;
    for (let lag = MIN_LAG; lag <= MAX_LAG && best > 0; lag++) {
      if (ac[lag] >= 0.8 * best && ac[lag] >= ac[lag - 1] && ac[lag] >= ac[lag + 1]) {
        bestLag = lag;
        break;
      }
    }
    this.peakHz = bestLag > 0 ? 1000 / bestLag : 0;
  }
}
