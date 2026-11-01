/**
 * Zero-GC 2D Scrolling Raster Plot Overlay
 * Plots population spike rasters at 60 FPS using hardware-accelerated canvas shifts.
 */

import {
  ControlIndex,
  NeuronMode,
  SharedSimulationMemory,
} from '../sim/types';
import { safeLoad } from '../sim/memory';

export class RasterCanvas {
  private container: HTMLElement;
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private overlayInfoEl: HTMLElement;

  private width = 0;
  private height = 180;
  private shiftDx = 2; // Pixels shifted per frame

  // Zero-GC color constants
  private colorExcitatory = '#00f0ff';
  private colorInhibitory = '#ff007f';
  private colorPacemaker = '#ffd700';

  // Population rate metrics
  private populationSpikeCount = 0;
  private lastRateCheck = performance.now();
  private currentPopRate = 0;

  constructor(container: HTMLElement, private mem: SharedSimulationMemory) {
    this.container = container;

    const wrapper = document.createElement('div');
    wrapper.className = 'raster-plot-wrapper';

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'raster-plot-canvas';
    this.canvas.height = this.height;

    const ctx = this.canvas.getContext('2d', { alpha: false });
    if (!ctx) throw new Error('Could not acquire 2D context for raster plot');
    this.ctx = ctx;

    this.overlayInfoEl = document.createElement('div');
    this.overlayInfoEl.className = 'raster-overlay-info';

    wrapper.appendChild(this.canvas);
    wrapper.appendChild(this.overlayInfoEl);
    this.container.appendChild(wrapper);

    this.resize();
    window.addEventListener('resize', this.resize.bind(this));
  }

  private resize(): void {
    const parentWidth = this.container.clientWidth;
    if (parentWidth !== this.width) {
      this.width = parentWidth;
      this.canvas.width = this.width;
      this.canvas.height = this.height;

      // Dark background fill on resize
      this.ctx.fillStyle = '#080911';
      this.ctx.fillRect(0, 0, this.width, this.height);

      // Draw subtle horizontal boundary guides
      this.drawGuides();
    }
  }

  private drawGuides(): void {
    this.ctx.strokeStyle = '#151a2d';
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.moveTo(0, this.height * 0.25);
    this.ctx.lineTo(this.width, this.height * 0.25);
    this.ctx.moveTo(0, this.height * 0.50);
    this.ctx.lineTo(this.width, this.height * 0.50);
    this.ctx.moveTo(0, this.height * 0.75);
    this.ctx.lineTo(this.width, this.height * 0.75);
    this.ctx.stroke();
  }

  public render(): void {
    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    const w = this.width;
    const h = this.height;
    const ctx = this.ctx;

    if (numNeurons === 0) {
      ctx.fillStyle = '#080911';
      ctx.fillRect(0, 0, w, h);
      this.drawGuides();
      this.overlayInfoEl.innerHTML = `
        <span class="raster-stat" style="color: var(--accent-cyan);">🌱 BLANK CANVAS (0 NEURONS) — Click reference plane to place Neuron #0</span>
      `;
      return;
    }

    const dx = this.shiftDx;

    // 1. Hardware-accelerated bitmap scroll: shift left by dx pixels
    ctx.drawImage(this.canvas, -dx, 0);

    // 2. Clear rightmost new strip
    ctx.fillStyle = '#080911';
    ctx.fillRect(w - dx, 0, dx, h);

    // Subtle background guides on the new slice
    ctx.fillStyle = '#151a2d';
    ctx.fillRect(w - dx, Math.floor(h * 0.25), dx, 1);
    ctx.fillRect(w - dx, Math.floor(h * 0.50), dx, 1);
    ctx.fillRect(w - dx, Math.floor(h * 0.75), dx, 1);

    // 3. Scan bit 0 of spikeBitfield for all neurons and draw spikes in the rightmost column
    const spikeBitfield = this.mem.spikeBitfield;
    const neuronMode = this.mem.neuronMode;
    const baseWeight = this.mem.baseWeight;
    const selectedId = safeLoad(this.mem.control, ControlIndex.SELECTED_NEURON);

    let frameSpikes = 0;
    const xPos = w - dx;

    for (let i = 0; i < numNeurons; i++) {
      if ((spikeBitfield[i] & 1) === 1) {
        frameSpikes++;
        // Map neuron ID [0, numNeurons - 1] to canvas Y [0, h - 2]
        const yPos = Math.floor((i / numNeurons) * (h - 2));

        const mode = neuronMode[i];
        if (mode === NeuronMode.POISSON || mode === NeuronMode.BURSTER) {
          ctx.fillStyle = this.colorPacemaker;
        } else if (baseWeight[i] < 0) {
          ctx.fillStyle = this.colorInhibitory;
        } else {
          ctx.fillStyle = this.colorExcitatory;
        }

        ctx.fillRect(xPos, yPos, dx, 2);
      }
    }

    this.populationSpikeCount += frameSpikes;

    // 4. Draw horizontal indicator line for selected neuron
    if (selectedId >= 0 && selectedId < numNeurons) {
      const selectedY = Math.floor((selectedId / numNeurons) * (h - 2));
      ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.fillRect(w - dx, selectedY, dx, 1);
    }

    // 5. Update population rate telemetry overlay
    const now = performance.now();
    if (now - this.lastRateCheck >= 250) {
      const elapsedSec = (now - this.lastRateCheck) / 1000.0;
      this.currentPopRate = Math.round(this.populationSpikeCount / elapsedSec);
      this.populationSpikeCount = 0;
      this.lastRateCheck = now;

      const selectedInfo = selectedId >= 0 ? ` | SELECTED: #${selectedId}` : '';
      this.overlayInfoEl.innerHTML = `
        <span class="raster-legend-item"><span class="legend-dot dot-cyan"></span> Exc</span>
        <span class="raster-legend-item"><span class="legend-dot dot-magenta"></span> Inh</span>
        <span class="raster-legend-item"><span class="legend-dot dot-gold"></span> Burster/Poisson</span>
        <span class="raster-legend-item"><span class="legend-dot" style="background:#4dff59"></span> Input</span>
        <span class="raster-legend-item"><span class="legend-dot" style="background:#ff801a"></span> Output</span>
        <span class="raster-legend-sep">|</span>
        <span class="raster-stat">POPULATION: <strong>${this.currentPopRate.toLocaleString()} spikes/sec</strong></span>
        <span class="raster-stat">${selectedInfo}</span>
        <span class="raster-scale">TIME SCALE: 1 col = 1 frame (~16ms)</span>
      `;
    }
  }
}
