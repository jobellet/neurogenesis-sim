/**
 * Accessibility helpers: a text summary of the activity for screen readers (an ARIA live region updated every few
 * seconds) and keyboard shortcuts (Space: run / pause, S: one step, [ and ]: previous / next neuron, Escape: deselect).
 */

/** One sentence that describes the network and its mean firing rate over the last window. */
export function activitySummary(neurons: number, synapses: number, dSpikes: number, dTicks: number, running: boolean): string {
  if (neurons === 0) return 'Empty network. Add neurons or load a network.';
  const rate = dTicks > 0 ? (dSpikes * 1000) / (dTicks * neurons) : 0;
  const state = running ? 'running' : 'paused';
  return `${neurons} neurons, ${synapses} synapses, ${state}; mean rate ${rate.toFixed(1)} Hz over the last ${dTicks} ms.`;
}

/** A visually hidden polite live region appended to `parent`. */
export function createStatusRegion(parent: HTMLElement): HTMLElement {
  const el = document.createElement('div');
  el.id = 'a11y-status';
  el.setAttribute('role', 'status');
  el.setAttribute('aria-live', 'polite');
  el.className = 'visually-hidden';
  parent.appendChild(el);
  return el;
}

export interface ShortcutActions {
  togglePlay: () => void;
  step: () => void;
  selectRelative: (delta: number) => void;
  deselect: () => void;
}

/** True when a key press goes to a text field or control and must not trigger a shortcut. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button' || el.isContentEditable === true;
}

export function installKeyboardShortcuts(actions: ShortcutActions): void {
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if (isTypingTarget(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.code === 'Space') {
      e.preventDefault();
      actions.togglePlay();
    } else if (e.key === 's' || e.key === 'S') {
      actions.step();
    } else if (e.key === ']') {
      actions.selectRelative(1);
    } else if (e.key === '[') {
      actions.selectRelative(-1);
    } else if (e.key === 'Escape') {
      actions.deselect();
    }
  });
}
