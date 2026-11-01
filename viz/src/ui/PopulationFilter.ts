import { SharedSimulationMemory } from '../sim/types';

export type ColorMode = 'role' | 'compartment' | 'mode';

interface NetworkMetadata {
  compartmentNames?: Record<number, string>;
  cellTypeNames?: Record<number, string>;
  neuronCompartment?: Int32Array;
  neuronCellType?: Int32Array;
  synapseProjections?: Record<string, number>;
}

export class PopulationFilter {
  private mem: SharedSimulationMemory;
  private container: HTMLElement;
  private panel: HTMLElement;
  
  public colorMode: ColorMode = 'role';
  public hiddenCompartments = new Set<number>();
  public hiddenCellTypes = new Set<number>();
  
  private meta: NetworkMetadata = {};
  
  public onFilterChanged: (() => void) | null = null;
  
  // A simple static palette for compartments/types
  private palette = [
    '#ff4444', '#44ff44', '#4444ff', '#ffff44', '#ff44ff', '#44ffff',
    '#ff8844', '#88ff44', '#4488ff', '#ff4488', '#8844ff', '#44ff88'
  ];

  constructor(container: HTMLElement, mem: SharedSimulationMemory) {
    this.container = container;
    this.mem = mem;
    
    this.panel = document.createElement('div');
    this.panel.className = 'population-filter-panel';
    this.panel.style.position = 'absolute';
    this.panel.style.bottom = '200px';
    this.panel.style.right = '10px';
    this.panel.style.background = 'rgba(8, 9, 17, 0.85)';
    this.panel.style.border = '1px solid #151a2d';
    this.panel.style.padding = '10px';
    this.panel.style.borderRadius = '6px';
    this.panel.style.color = '#fff';
    this.panel.style.fontFamily = 'monospace';
    this.panel.style.fontSize = '11px';
    this.panel.style.zIndex = '100';
    this.panel.style.maxHeight = '400px';
    this.panel.style.overflowY = 'auto';
    this.panel.style.display = 'none'; // Hidden until a network with metadata is loaded
    
    this.container.appendChild(this.panel);
    this.renderPanel();
    
    // Monkey-patch importNetwork globally to intercept raw JSON metadata
    const originalImport = (window as any).importNetwork;
    if (originalImport) {
      (window as any).importNetwork = (net: any) => {
        this.loadMetadata(net);
        originalImport(net);
        this.renderPanel();
      };
    }
  }
  
  public loadMetadata(net: any) {
    this.meta = {};
    this.hiddenCompartments.clear();
    this.hiddenCellTypes.clear();
    this.colorMode = 'role';
    
    if (!net || !net.neurons || net.neurons.length === 0) {
      this.panel.style.display = 'none';
      return;
    }
    
    const count = net.neurons.length;
    let hasCompartments = false;
    let hasCellTypes = false;
    
    const compArray = new Int32Array(count).fill(-1);
    const typeArray = new Int32Array(count).fill(-1);
    
    for (let i = 0; i < count; i++) {
      const n = net.neurons[i];
      if (n.compartment !== undefined && n.compartment !== -1) {
        compArray[i] = n.compartment;
        hasCompartments = true;
      }
      if (n.cellType !== undefined && n.cellType !== -1) {
        typeArray[i] = n.cellType;
        hasCellTypes = true;
      }
    }
    
    if (hasCompartments || hasCellTypes) {
      this.meta.neuronCompartment = compArray;
      this.meta.neuronCellType = typeArray;
      this.meta.compartmentNames = net.compartmentNames || {};
      this.meta.cellTypeNames = net.cellTypeNames || {};
      
      // Compute projections
      if (hasCompartments && net.synapses) {
        this.meta.synapseProjections = {};
        for (const s of net.synapses) {
          const cPre = compArray[s.pre];
          const cPost = compArray[s.post];
          if (cPre !== -1 && cPost !== -1) {
            const key = `${cPre}->${cPost}`;
            this.meta.synapseProjections[key] = (this.meta.synapseProjections[key] || 0) + 1;
          }
        }
      }
      
      this.panel.style.display = 'block';
    } else {
      this.panel.style.display = 'none';
    }
  }

  private renderPanel() {
    this.panel.innerHTML = '<strong>Population Filter</strong><br><hr style="border-color:#151a2d; margin: 4px 0;">';
    
    if (Object.keys(this.meta).length === 0) {
      this.panel.innerHTML += '<i>No metadata</i>';
      return;
    }
    
    // Color Mode
    const modeDiv = document.createElement('div');
    modeDiv.style.marginBottom = '10px';
    modeDiv.innerHTML = `
      <label><input type="radio" name="colorMode" value="role" ${this.colorMode === 'role' ? 'checked' : ''}> Role/Sign</label><br>
      <label><input type="radio" name="colorMode" value="compartment" ${this.colorMode === 'compartment' ? 'checked' : ''}> Compartment</label><br>
      <label><input type="radio" name="colorMode" value="mode" ${this.colorMode === 'mode' ? 'checked' : ''}> Cell Type/Mode</label>
    `;
    modeDiv.addEventListener('change', (e) => {
      this.colorMode = (e.target as HTMLInputElement).value as ColorMode;
      if (this.onFilterChanged) this.onFilterChanged();
    });
    this.panel.appendChild(modeDiv);
    
    // Compartments
    if (this.meta.neuronCompartment) {
      const compSet = new Set(this.meta.neuronCompartment);
      compSet.delete(-1);
      if (compSet.size > 0) {
        this.panel.innerHTML += '<strong>Compartments</strong><br>';
        const cList = Array.from(compSet).sort((a, b) => a - b);
        for (const c of cList) {
          const name = this.meta.compartmentNames?.[c] || `Comp ${c}`;
          const color = this.palette[c % this.palette.length];
          const label = document.createElement('label');
          label.style.display = 'block';
          label.innerHTML = `
            <input type="checkbox" data-type="comp" value="${c}" ${!this.hiddenCompartments.has(c) ? 'checked' : ''}>
            <span style="color:${color}; font-size:14px;">■</span> ${name}
          `;
          this.panel.appendChild(label);
        }
      }
    }
    
    // Projections
    if (this.meta.synapseProjections && Object.keys(this.meta.synapseProjections).length > 0) {
        this.panel.innerHTML += '<br><strong>Projections (Count)</strong><br>';
        for (const [key, count] of Object.entries(this.meta.synapseProjections)) {
            const [pre, post] = key.split('->').map(Number);
            const preName = this.meta.compartmentNames?.[pre] || `C${pre}`;
            const postName = this.meta.compartmentNames?.[post] || `C${post}`;
            this.panel.innerHTML += `<div>${preName} → ${postName}: ${count}</div>`;
        }
    }
    
    this.panel.addEventListener('change', (e) => {
      const target = e.target as HTMLInputElement;
      if (target.type === 'checkbox') {
        const val = parseInt(target.value);
        if (target.dataset.type === 'comp') {
          if (target.checked) this.hiddenCompartments.delete(val);
          else this.hiddenCompartments.add(val);
        }
        if (this.onFilterChanged) this.onFilterChanged();
      }
    });
  }
  
  public isHidden(i: number): boolean {
    if (this.meta.neuronCompartment && this.meta.neuronCompartment[i] !== -1) {
      if (this.hiddenCompartments.has(this.meta.neuronCompartment[i])) return true;
    }
    if (this.meta.neuronCellType && this.meta.neuronCellType[i] !== -1) {
      if (this.hiddenCellTypes.has(this.meta.neuronCellType[i])) return true;
    }
    return false;
  }
  
  public getColor(i: number): string | null {
    if (this.colorMode === 'role') return null;
    
    if (this.colorMode === 'compartment') {
      const c = this.meta.neuronCompartment?.[i];
      if (c !== undefined && c !== -1) {
        return this.palette[c % this.palette.length];
      }
    }
    
    if (this.colorMode === 'mode') {
      const t = this.meta.neuronCellType?.[i];
      if (t !== undefined && t !== -1) {
        return this.palette[(t + 5) % this.palette.length];
      }
    }
    
    return null;
  }
  
  public getColorRGB(i: number): [number, number, number] | null {
    const hex = this.getColor(i);
    if (!hex) return null;
    
    const r = parseInt(hex.slice(1, 3), 16) / 255.0;
    const g = parseInt(hex.slice(3, 5), 16) / 255.0;
    const b = parseInt(hex.slice(5, 7), 16) / 255.0;
    return [r, g, b];
  }
}
