/**
 * Puzzle mode: `?hide=shift_v,shift_s,refractory,threshold` hides these neuron parameters in the inspector, so that a
 * student finds them by experiment (change the input, watch the raster and the voltage trace) and checks a guess.
 * Only the display changes: the network in memory and in exported files keeps every value (no hidden state).
 */
export const PUZZLE_PARAMS = ['shift_v', 'shift_s', 'refractory', 'threshold'] as const;
export type PuzzleParam = (typeof PUZZLE_PARAMS)[number];

export const PUZZLE_LABELS: Record<PuzzleParam, string> = {
  shift_v: 'membrane leak exponent k_v',
  shift_s: 'synaptic decay exponent k_s',
  refractory: 'refractory period (ticks)',
  threshold: 'firing threshold',
};

/** Hidden parameters named in a URL query string (unknown names are ignored). */
export function parseHidden(search: string): Set<PuzzleParam> {
  const raw = new URLSearchParams(search).get('hide') ?? '';
  const known = new Set<string>(PUZZLE_PARAMS);
  return new Set(
    raw
      .split(',')
      .map((s) => s.trim().toLowerCase())
      .filter((s): s is PuzzleParam => known.has(s)),
  );
}

/** Text shown for a parameter value: '?' when hidden. */
export function shown(hidden: Set<PuzzleParam>, name: PuzzleParam, value: number): string {
  return hidden.has(name) ? '?' : String(value);
}

/** Verdict on a guess of an integer parameter. */
export function checkGuess(guess: number, truth: number): 'correct' | 'too high' | 'too low' | 'not a number' {
  if (!Number.isFinite(guess)) return 'not a number';
  if (Math.round(guess) === truth) return 'correct';
  return guess > truth ? 'too high' : 'too low';
}
