/**
 * High-Performance 3D Scene Manager (Three.js WebGL2)
 * Manages instanced somas, dynamic synaptic lines, travelling action potentials,
 * 6-DOF fly-through navigation, drag-and-drop synaptic wiring, and interactive placement.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { PopulationFilter } from '../ui/PopulationFilter';
import {
  MAX_NEURONS,
  ControlIndex,
  SharedSimulationMemory,
  NeuronMode,
  ToolMode,
} from '../sim/types';
import { safeLoad, safeStore } from '../sim/memory';
import {
  somaVertexShader,
  somaFragmentShader,
  pulseVertexShader,
  pulseFragmentShader,
  gridPlaneVertexShader,
  gridPlaneFragmentShader,
} from './shaders';

export class SceneManager {
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  public renderer: THREE.WebGLRenderer | null = null;
  public controls: OrbitControls | null = null;

  // WebGL Availability and 2D Canvas Fallback
  public hasWebGL = true;
  public fallbackCanvas: HTMLCanvasElement | null = null;
  public fallbackCtx: CanvasRenderingContext2D | null = null;
  private fallbackBannerEl: HTMLElement | null = null;
  private fallbackCam = { x: 0, y: 0, zoom: 2.2 };
  private isPanningFallback = false;
  private lastMousePos = { x: 0, y: 0 };
  private mouseScreenPos = { x: 0, y: 0 };

  public instancedSomas: THREE.InstancedMesh;
  private aPosAttr: THREE.InstancedBufferAttribute;
  private aStateAttr: THREE.InstancedBufferAttribute;
  private aTypeAttr: THREE.InstancedBufferAttribute;
  private aColorAttr: THREE.InstancedBufferAttribute;

  private selectionRing: THREE.Mesh;
  private axonArrow: THREE.ArrowHelper;
  private synLinesSelected: THREE.LineSegments;
  private synLinesGlobal: THREE.LineSegments;
  private pulsePoints: THREE.Points;

  // Drag-and-drop wiring tools
  public toolMode: ToolMode = 'SELECT';
  public isDraggingWire = false;
  public wireSourceId: number | null = null;
  public wireHoverTargetId: number | null = null;
  private wirePreviewLine: THREE.Line;
  private wireTargetMarker: THREE.Mesh;
  private spawnReticle: THREE.Mesh;

  // Pulse buffer attributes
  private maxPulses = 10000;
  private pulseStartPos: Float32Array;
  private pulseEndPos: Float32Array;
  private pulseProgress: Float32Array;
  private pulseWeightSign: Float32Array;

  // Reference grid plane
  public gridPlane: THREE.Mesh;
  public planeY = 0;

  // Keyboard navigation state
  private keysDown: Record<string, boolean> = {};
  private flySpeed = 45.0;

  // Raycasting
  private raycaster = new THREE.Raycaster();
  private mouse = new THREE.Vector2();

  // Callbacks
  public onNeuronSelected: ((id: number | null) => void) | null = null;
  public onNeuronSpawnRequested: ((x: number, y: number, z: number) => void) | null = null;
  public onSynapseDragComplete: ((preId: number, postId: number, dist: number) => void) | null = null;
  public popFilter: PopulationFilter | null = null;

  public onNeuronDeleteRequested: ((id: number) => void) | null = null;

  public showGlobalSynapses = false;
  private cachedNumNeurons = 0;

  constructor(private container: HTMLElement, private mem: SharedSimulationMemory) {
    // 1. Scene & Camera
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x06070c);
    this.scene.fog = new THREE.FogExp2(0x06070c, 0.0022);

    const aspect = container.clientWidth / (container.clientHeight || 1);
    this.camera = new THREE.PerspectiveCamera(50, aspect, 0.5, 1000);
    this.camera.position.set(0, 40, 160);

    // 2. Safe WebGLRenderer Creation with Progressive Fallback
    let renderer: THREE.WebGLRenderer | null = null;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    } catch (e1) {
      try {
        renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: 'default' });
      } catch (e2) {
        console.warn('[SceneManager] WebGL creation failed in both modes:', e2);
        renderer = null;
      }
    }

    if (renderer) {
      this.hasWebGL = true;
      this.renderer = renderer;
      this.renderer.setSize(container.clientWidth, container.clientHeight);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure = 1.15;
      container.appendChild(this.renderer.domElement);

      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.target.set(0, 0, 0);
      this.controls.maxDistance = 450;
      this.controls.minDistance = 5;
    } else {
      this.hasWebGL = false;
      this.renderer = null;
      this.controls = null;
      this.initFallback2DCanvas();
    }

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0x334466, 1.2);
    this.scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xaaccff, 1.5);
    dirLight1.position.set(100, 200, 150);
    this.scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xff66aa, 0.8);
    dirLight2.position.set(-100, -100, -100);
    this.scene.add(dirLight2);

    // 5. Instanced Somas
    const somaGeom = new THREE.IcosahedronGeometry(1.25, 2);
    const somaMat = new THREE.ShaderMaterial({
      vertexShader: somaVertexShader,
      fragmentShader: somaFragmentShader,
      uniforms: {
        uSelectedId: { value: -1.0 },
      },
      transparent: true,
      depthWrite: true,
    });

    this.instancedSomas = new THREE.InstancedMesh(somaGeom, somaMat, MAX_NEURONS);
    this.instancedSomas.count = 0;
    this.instancedSomas.frustumCulled = false;

    const posData = new Float32Array(MAX_NEURONS * 3);
    const stateData = new Float32Array(MAX_NEURONS * 2);
    const typeData = new Float32Array(MAX_NEURONS);
    const colorData = new Float32Array(MAX_NEURONS * 3);

    this.aPosAttr = new THREE.InstancedBufferAttribute(posData, 3);
    this.aStateAttr = new THREE.InstancedBufferAttribute(stateData, 2);
    this.aTypeAttr = new THREE.InstancedBufferAttribute(typeData, 1);
    this.aColorAttr = new THREE.InstancedBufferAttribute(colorData, 3);

    somaGeom.setAttribute('aPosition', this.aPosAttr);
    somaGeom.setAttribute('aState', this.aStateAttr);
    somaGeom.setAttribute('aType', this.aTypeAttr);
    somaGeom.setAttribute('aColor', this.aColorAttr);

    this.scene.add(this.instancedSomas);

    // 6. Selection Ring & Axon Vector Arrow
    const ringGeom = new THREE.TorusGeometry(2.2, 0.12, 16, 48);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00ffff, wireframe: true });
    this.selectionRing = new THREE.Mesh(ringGeom, ringMat);
    this.selectionRing.visible = false;
    this.scene.add(this.selectionRing);

    this.axonArrow = new THREE.ArrowHelper(
      new THREE.Vector3(0, 1, 0),
      new THREE.Vector3(0, 0, 0),
      8.0,
      0xffbb00,
      2.0,
      1.0
    );
    this.axonArrow.visible = false;
    this.scene.add(this.axonArrow);

    // 7. Interactive Drag-and-Drop Wire Preview Line & Target Marker
    const wireGeom = new THREE.BufferGeometry();
    wireGeom.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 0, 0, 0], 3));
    const wireMat = new THREE.LineBasicMaterial({
      color: 0x00f0ff,
      linewidth: 3,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
    });
    this.wirePreviewLine = new THREE.Line(wireGeom, wireMat);
    this.wirePreviewLine.visible = false;
    this.scene.add(this.wirePreviewLine);

    const wireTargetGeom = new THREE.RingGeometry(1.8, 2.3, 32);
    const wireTargetMat = new THREE.MeshBasicMaterial({ color: 0xffd700, side: THREE.DoubleSide, wireframe: true });
    this.wireTargetMarker = new THREE.Mesh(wireTargetGeom, wireTargetMat);
    this.wireTargetMarker.visible = false;
    this.scene.add(this.wireTargetMarker);

    // Spawn reticle on grid
    const reticleGeom = new THREE.RingGeometry(1.2, 1.8, 24);
    reticleGeom.rotateX(-Math.PI / 2);
    const reticleMat = new THREE.MeshBasicMaterial({ color: 0x00ff88, side: THREE.DoubleSide });
    this.spawnReticle = new THREE.Mesh(reticleGeom, reticleMat);
    this.spawnReticle.visible = false;
    this.scene.add(this.spawnReticle);

    // 8. Synaptic Lines (Selected & Global)
    const synLineMatSelected = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      linewidth: 2,
    });
    const synGeomSelected = new THREE.BufferGeometry();
    this.synLinesSelected = new THREE.LineSegments(synGeomSelected, synLineMatSelected);
    this.synLinesSelected.frustumCulled = false;
    this.scene.add(this.synLinesSelected);

    const synLineMatGlobal = new THREE.LineBasicMaterial({
      color: 0x184466,
      transparent: true,
      opacity: 0.12,
      blending: THREE.AdditiveBlending,
    });
    const synGeomGlobal = new THREE.BufferGeometry();
    this.synLinesGlobal = new THREE.LineSegments(synGeomGlobal, synLineMatGlobal);
    this.synLinesGlobal.visible = false;
    this.synLinesGlobal.frustumCulled = false;
    this.scene.add(this.synLinesGlobal);

    // 9. Travelling Pulses
    const pulseGeom = new THREE.BufferGeometry();
    this.pulseStartPos = new Float32Array(this.maxPulses * 3);
    this.pulseEndPos = new Float32Array(this.maxPulses * 3);
    this.pulseProgress = new Float32Array(this.maxPulses);
    this.pulseWeightSign = new Float32Array(this.maxPulses);

    pulseGeom.setAttribute('aStartPos', new THREE.BufferAttribute(this.pulseStartPos, 3));
    pulseGeom.setAttribute('aEndPos', new THREE.BufferAttribute(this.pulseEndPos, 3));
    pulseGeom.setAttribute('aProgress', new THREE.BufferAttribute(this.pulseProgress, 1));
    pulseGeom.setAttribute('aWeightSign', new THREE.BufferAttribute(this.pulseWeightSign, 1));
    pulseGeom.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.maxPulses * 3), 3));

    const pulseMat = new THREE.ShaderMaterial({
      vertexShader: pulseVertexShader,
      fragmentShader: pulseFragmentShader,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    this.pulsePoints = new THREE.Points(pulseGeom, pulseMat);
    this.pulsePoints.frustumCulled = false;
    this.scene.add(this.pulsePoints);

    // 10. 3D Reference Grid Plane
    const planeGeom = new THREE.PlaneGeometry(200, 200, 2, 2);
    planeGeom.rotateX(-Math.PI / 2);
    const planeMat = new THREE.ShaderMaterial({
      vertexShader: gridPlaneVertexShader,
      fragmentShader: gridPlaneFragmentShader,
      uniforms: {
        uPlaneY: { value: 0 },
        uGridColor: { value: new THREE.Color(0x00e5ff) },
      },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    this.gridPlane = new THREE.Mesh(planeGeom, planeMat);
    this.gridPlane.position.y = this.planeY;
    this.scene.add(this.gridPlane);

    this.initEventListeners();
    this.syncPositionsFromMemory();
  }

  public syncPositionsFromMemory(): void {
    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    this.cachedNumNeurons = numNeurons;
    this.instancedSomas.count = numNeurons;
    this.instancedSomas.visible = numNeurons > 0;

    const pos = this.mem.posXYZ;
    const posAttrArray = this.aPosAttr.array as Float32Array;
    const typeAttrArray = this.aTypeAttr.array as Float32Array;

    const colorAttrArray = this.aColorAttr.array as Float32Array;

    for (let i = 0; i < numNeurons; i++) {
      const idx3 = i * 3;
      
      if (this.popFilter?.isHidden(i)) {
        posAttrArray[idx3] = 1e6;
        posAttrArray[idx3 + 1] = 1e6;
        posAttrArray[idx3 + 2] = 1e6;
        continue;
      }

      posAttrArray[idx3] = pos[idx3];
      posAttrArray[idx3 + 1] = pos[idx3 + 1];
      posAttrArray[idx3 + 2] = pos[idx3 + 2];

      const customColor = this.popFilter?.getColorRGB(i);
      if (customColor) {
        typeAttrArray[i] = 10.0; // Custom Color marker
        colorAttrArray[idx3] = customColor[0];
        colorAttrArray[idx3 + 1] = customColor[1];
        colorAttrArray[idx3 + 2] = customColor[2];
      } else {
        const mode = this.mem.neuronMode[i];
        const role = this.mem.role[i];
        if (role === 1) {
          typeAttrArray[i] = 3.0;            // input neuron (role 1)
        } else if (role === 2) {
          typeAttrArray[i] = 4.0;            // output neuron (role 2)
        } else if (mode === NeuronMode.POISSON || mode === NeuronMode.BURSTER) {
          typeAttrArray[i] = 2.0;
        } else {
          typeAttrArray[i] = this.mem.baseWeight[i] >= 0 ? 0.0 : 1.0;
        }
      }
    }

    this.aPosAttr.needsUpdate = true;
    this.aTypeAttr.needsUpdate = true;
    this.aColorAttr.needsUpdate = true;
    this.updateGlobalSynapseGeometry();

    if (numNeurons === 0) {
      this.updateSelectedNeuronVisuals(null);
      (this.pulsePoints.geometry as THREE.BufferGeometry).setDrawRange(0, 0);
    }
  }

  public updateGlobalSynapseGeometry(): void {
    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    const pos = this.mem.posXYZ;

    const lineCoords: number[] = [];
    if (numNeurons > 0 && this.showGlobalSynapses) {
      const stride = numNeurons > 3000 ? 3 : 1;

      for (let i = 0; i < numNeurons; i += stride) {
        const start = this.mem.rowPtr[i];
        const end = this.mem.rowPtr[i + 1];
        const xi = pos[i * 3];
        const yi = pos[i * 3 + 1];
        const zi = pos[i * 3 + 2];

        if (this.popFilter?.isHidden(i)) continue;
        for (let s = start; s < end; s++) {
          const j = this.mem.colIdx[s];
          if (j < numNeurons && !this.popFilter?.isHidden(j)) {
            lineCoords.push(xi, yi, zi);
            lineCoords.push(pos[j * 3], pos[j * 3 + 1], pos[j * 3 + 2]);
          }
        }
      }
    }

    const geom = this.synLinesGlobal.geometry;
    geom.setAttribute('position', new THREE.Float32BufferAttribute(lineCoords, 3));
    this.synLinesGlobal.visible = this.showGlobalSynapses && lineCoords.length > 0;
  }

  public updateSelectedNeuronVisuals(selectedId: number | null): void {
    if (selectedId === null || selectedId < 0 || selectedId >= this.cachedNumNeurons) {
      this.selectionRing.visible = false;
      this.axonArrow.visible = false;
      this.synLinesSelected.geometry.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
      this.synLinesSelected.geometry.setAttribute('color', new THREE.Float32BufferAttribute([], 3));
      return;
    }

    const pos = this.mem.posXYZ;
    const axon = this.mem.axonDirXYZ;
    const xi = pos[selectedId * 3];
    const yi = pos[selectedId * 3 + 1];
    const zi = pos[selectedId * 3 + 2];

    this.selectionRing.position.set(xi, yi, zi);
    this.selectionRing.visible = true;

    const uxi = axon[selectedId * 3];
    const uyi = axon[selectedId * 3 + 1];
    const uzi = axon[selectedId * 3 + 2];
    const dir = new THREE.Vector3(uxi, uyi, uzi).normalize();
    this.axonArrow.position.set(xi, yi, zi);
    this.axonArrow.setDirection(dir);
    this.axonArrow.setLength(10.0, 2.5, 1.2);
    this.axonArrow.visible = true;

    const lineCoords: number[] = [];
    const lineColors: number[] = [];

    // 1. Outgoing connections
    const outStart = this.mem.rowPtr[selectedId];
    const outEnd = this.mem.rowPtr[selectedId + 1];
    for (let s = outStart; s < outEnd; s++) {
      const j = this.mem.colIdx[s];
      if (j >= this.cachedNumNeurons || this.popFilter?.isHidden(j)) continue;
      const w = this.mem.weights[s];
      const xj = pos[j * 3];
      const yj = pos[j * 3 + 1];
      const zj = pos[j * 3 + 2];

      lineCoords.push(xi, yi, zi, xj, yj, zj);
      if (w >= 0) {
        lineColors.push(0.0, 1.0, 1.0, 1.0, 0.7, 0.1);
      } else {
        lineColors.push(1.0, 0.1, 0.7, 0.5, 0.0, 0.9);
      }
    }

    // 2. Incoming connections
    for (let k = 0; k < this.cachedNumNeurons; k++) {
      if (k === selectedId || this.popFilter?.isHidden(k)) continue;
      const kStart: number = this.mem.rowPtr[k];
      const kEnd: number = this.mem.rowPtr[k + 1];
      for (let s: number = kStart; s < kEnd; s++) {
        if (this.mem.colIdx[s] === selectedId) {
          const xk = pos[k * 3];
          const yk = pos[k * 3 + 1];
          const zk = pos[k * 3 + 2];
          lineCoords.push(xk, yk, zk, xi, yi, zi);
          lineColors.push(0.1, 0.8, 0.3, 0.4, 1.0, 0.6);
        }
      }
    }

    const geom = this.synLinesSelected.geometry;
    geom.setAttribute('position', new THREE.Float32BufferAttribute(lineCoords, 3));
    geom.setAttribute('color', new THREE.Float32BufferAttribute(lineColors, 3));
  }

  public setPlaneY(y: number): void {
    this.planeY = y;
    this.gridPlane.position.y = y;
    const mat = this.gridPlane.material as THREE.ShaderMaterial;
    if (mat.uniforms.uPlaneY) {
      mat.uniforms.uPlaneY.value = y;
    }
  }

  private initFallback2DCanvas(): void {
    this.fallbackCanvas = document.createElement('canvas');
    this.fallbackCanvas.className = 'scene-fallback-canvas';
    this.fallbackCanvas.width = this.container.clientWidth;
    this.fallbackCanvas.height = this.container.clientHeight;
    this.container.appendChild(this.fallbackCanvas);

    this.fallbackCtx = this.fallbackCanvas.getContext('2d');

    // Diagnostic & Solution Banner for Chrome
    this.fallbackBannerEl = document.createElement('div');
    this.fallbackBannerEl.className = 'webgl-fallback-banner';
    this.fallbackBannerEl.innerHTML = `
      <div class="banner-badge">⚠️ ACCÉLÉRATION 3D DÉSACTIVÉE DANS GOOGLE CHROME (Mode 2D Interactif Actif)</div>
      <div class="banner-body">
        Le contexte WebGL2 est inactif dans votre navigateur Chrome (accélération matérielle désactivée).<br>
        Le simulateur tourne actuellement en <strong>mode 2D interactif de secours</strong> (100% fonctionnel).<br><br>
        <strong>Pour réactiver la 3D matérielle complète à 60 FPS dans Google Chrome :</strong>
        <ol style="margin: 4px 0 6px 18px; padding: 0;">
          <li>Ouvrez un nouvel onglet et tapez : <code>chrome://settings/system</code></li>
          <li>Activez l'option <strong>« Utiliser l'accélération graphique si disponible »</strong> (Use graphics acceleration when available)</li>
          <li>Cliquez sur le bouton <strong>Relancer</strong> (Relaunch) apparu à côté de l'option.</li>
        </ol>
      </div>
      <button class="btn btn-xs btn-secondary banner-dismiss-btn" style="position: absolute; top: 10px; right: 10px; padding: 2px 8px;">✕ Fermer</button>
    `;

    this.fallbackBannerEl.querySelector('.banner-dismiss-btn')?.addEventListener('click', () => {
      this.fallbackBannerEl?.remove();
    });

    this.container.appendChild(this.fallbackBannerEl);
  }

  private initEventListeners(): void {
    window.addEventListener('resize', this.onWindowResize.bind(this));

    window.addEventListener('keydown', (e: KeyboardEvent) => {
      this.keysDown[e.code] = true;

      // Shortcut to delete selected neuron
      if (e.code === 'Delete' || e.code === 'Backspace') {
        const sel = safeLoad(this.mem.control, ControlIndex.SELECTED_NEURON);
        if (sel >= 0 && this.onNeuronDeleteRequested) {
          this.onNeuronDeleteRequested(sel);
        }
      }
    });

    window.addEventListener('keyup', (e: KeyboardEvent) => {
      this.keysDown[e.code] = false;
    });

    const dom: HTMLElement | null = (this.hasWebGL && this.renderer) ? this.renderer.domElement : this.fallbackCanvas;
    if (dom) {
      dom.addEventListener('pointerdown', this.onPointerDown.bind(this));
      dom.addEventListener('pointermove', this.onPointerMove.bind(this));
      dom.addEventListener('pointerup', this.onPointerUp.bind(this));

      dom.addEventListener('wheel', (e: WheelEvent) => {
        if (!this.hasWebGL) {
          e.preventDefault();
          const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
          this.fallbackCam.zoom = Math.max(0.5, Math.min(8.0, this.fallbackCam.zoom * zoomFactor));
        } else if (e.altKey) {
          e.preventDefault();
          const delta = e.deltaY > 0 ? -2 : 2;
          this.setPlaneY(Math.max(-80, Math.min(80, this.planeY + delta)));
        }
      }, { passive: false });
    }
  }

  private updateMouseCoords(e: MouseEvent): void {
    const dom = (this.hasWebGL && this.renderer) ? this.renderer.domElement : this.fallbackCanvas;
    if (!dom) return;
    const rect = dom.getBoundingClientRect();
    this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    this.mouseScreenPos.x = e.clientX - rect.left;
    this.mouseScreenPos.y = e.clientY - rect.top;
  }

  private onPointerDown(e: MouseEvent): void {
    if (e.button !== 0) return;
    this.updateMouseCoords(e);

    if (!this.hasWebGL) {
      this.handleFallbackPointerDown(e);
      return;
    }

    this.raycaster.setFromCamera(this.mouse, this.camera);

    if (this.toolMode === 'WIRE') {
      // Start drag-and-drop connection from clicked neuron
      const intersects = this.raycaster.intersectObject(this.instancedSomas);
      if (intersects.length > 0 && intersects[0].instanceId !== undefined) {
        const preId = intersects[0].instanceId;
        this.wireSourceId = preId;
        this.isDraggingWire = true;
        if (this.controls) this.controls.enabled = false;

        const pos = this.mem.posXYZ;
        const xi = pos[preId * 3];
        const yi = pos[preId * 3 + 1];
        const zi = pos[preId * 3 + 2];

        const wirePos = this.wirePreviewLine.geometry.getAttribute('position') as THREE.BufferAttribute;
        wirePos.setXYZ(0, xi, yi, zi);
        wirePos.setXYZ(1, xi, yi, zi);
        wirePos.needsUpdate = true;
        this.wirePreviewLine.visible = true;
      }
    } else if (this.toolMode === 'SPAWN' || e.shiftKey) {
      // Spawn neuron on reference plane
      const planeIntersect = this.raycaster.intersectObject(this.gridPlane);
      if (planeIntersect.length > 0) {
        const pt = planeIntersect[0].point;
        if (this.onNeuronSpawnRequested) {
          this.onNeuronSpawnRequested(pt.x, pt.y, pt.z);
        }
      }
    } else {
      // SELECT mode
      const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
      const intersects = numNeurons > 0 ? this.raycaster.intersectObject(this.instancedSomas) : [];
      if (intersects.length > 0 && intersects[0].instanceId !== undefined) {
        const id = intersects[0].instanceId;
        safeStore(this.mem.control, ControlIndex.SELECTED_NEURON, id);
        if (this.onNeuronSelected) this.onNeuronSelected(id);
      } else if (numNeurons === 0) {
        // When canvas is empty, clicking on reference plane immediately spawns Neuron #0
        const planeIntersect = this.raycaster.intersectObject(this.gridPlane);
        if (planeIntersect.length > 0 && this.onNeuronSpawnRequested) {
          const pt = planeIntersect[0].point;
          this.onNeuronSpawnRequested(pt.x, pt.y, pt.z);
        }
      } else {
        safeStore(this.mem.control, ControlIndex.SELECTED_NEURON, -1);
        if (this.onNeuronSelected) this.onNeuronSelected(null);
      }
    }
  }

  private onPointerMove(e: MouseEvent): void {
    this.updateMouseCoords(e);

    if (!this.hasWebGL) {
      this.handleFallbackPointerMove(e);
      return;
    }

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);

    if (this.isDraggingWire && this.wireSourceId !== null) {
      // Check if hovering over candidate target neuron
      const intersects = this.raycaster.intersectObject(this.instancedSomas);
      const wirePos = this.wirePreviewLine.geometry.getAttribute('position') as THREE.BufferAttribute;

      if (intersects.length > 0 && intersects[0].instanceId !== undefined && intersects[0].instanceId !== this.wireSourceId) {
        const targetId = intersects[0].instanceId;
        this.wireHoverTargetId = targetId;

        const xj = this.mem.posXYZ[targetId * 3];
        const yj = this.mem.posXYZ[targetId * 3 + 1];
        const zj = this.mem.posXYZ[targetId * 3 + 2];

        wirePos.setXYZ(1, xj, yj, zj);
        wirePos.needsUpdate = true;

        this.wireTargetMarker.position.set(xj, yj, zj);
        this.wireTargetMarker.lookAt(this.camera.position);
        this.wireTargetMarker.visible = true;
      } else {
        this.wireHoverTargetId = null;
        this.wireTargetMarker.visible = false;

        // Project ray onto source depth plane
        const srcPos = new THREE.Vector3(
          this.mem.posXYZ[this.wireSourceId * 3],
          this.mem.posXYZ[this.wireSourceId * 3 + 1],
          this.mem.posXYZ[this.wireSourceId * 3 + 2]
        );
        const plane = new THREE.Plane();
        plane.setFromNormalAndCoplanarPoint(this.camera.getWorldDirection(new THREE.Vector3()).negate(), srcPos);

        const targetPt = new THREE.Vector3();
        this.raycaster.ray.intersectPlane(plane, targetPt);

        wirePos.setXYZ(1, targetPt.x, targetPt.y, targetPt.z);
        wirePos.needsUpdate = true;
      }
    } else if (this.toolMode === 'SPAWN' || numNeurons === 0) {
      const planeIntersect = this.raycaster.intersectObject(this.gridPlane);
      if (planeIntersect.length > 0) {
        this.spawnReticle.position.copy(planeIntersect[0].point);
        this.spawnReticle.visible = true;
      } else {
        this.spawnReticle.visible = false;
      }
    } else {
      this.spawnReticle.visible = false;
    }
  }

  private onPointerUp(): void {
    if (!this.hasWebGL) {
      this.handleFallbackPointerUp();
      return;
    }

    if (this.isDraggingWire) {
      if (this.wireSourceId !== null && this.wireHoverTargetId !== null && this.wireSourceId !== this.wireHoverTargetId) {
        const preId = this.wireSourceId;
        const postId = this.wireHoverTargetId;

        const rx = this.mem.posXYZ[postId * 3] - this.mem.posXYZ[preId * 3];
        const ry = this.mem.posXYZ[postId * 3 + 1] - this.mem.posXYZ[preId * 3 + 1];
        const rz = this.mem.posXYZ[postId * 3 + 2] - this.mem.posXYZ[preId * 3 + 2];
        const dist = Math.sqrt(rx * rx + ry * ry + rz * rz);

        if (this.onSynapseDragComplete) {
          this.onSynapseDragComplete(preId, postId, dist);
        }
      }

      this.isDraggingWire = false;
      this.wireSourceId = null;
      this.wireHoverTargetId = null;
      this.wirePreviewLine.visible = false;
      this.wireTargetMarker.visible = false;
      if (this.controls) this.controls.enabled = true;
    }
  }

  private handleFallbackPointerDown(e: MouseEvent): void {
    if (!this.fallbackCanvas) return;
    const rect = this.fallbackCanvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    const cx = this.fallbackCanvas.width / 2 + this.fallbackCam.x;
    const cy = this.fallbackCanvas.height / 2 + this.fallbackCam.y;
    const scale = this.fallbackCam.zoom;

    const pos = this.mem.posXYZ;

    // Check hit on existing neurons
    let hitId = -1;
    let minDist = 18;
    for (let i = 0; i < numNeurons; i++) {
      const sx = cx + pos[i * 3] * scale;
      const sy = cy + pos[i * 3 + 2] * scale;
      const d = Math.hypot(mx - sx, my - sy);
      if (d < minDist) {
        minDist = d;
        hitId = i;
      }
    }

    if (this.toolMode === 'WIRE') {
      if (hitId >= 0) {
        this.wireSourceId = hitId;
        this.isDraggingWire = true;
      }
    } else if (this.toolMode === 'SPAWN' || numNeurons === 0 || e.shiftKey) {
      const worldX = (mx - cx) / scale;
      const worldZ = (my - cy) / scale;
      if (this.onNeuronSpawnRequested) {
        this.onNeuronSpawnRequested(worldX, this.planeY, worldZ);
      }
    } else {
      if (hitId >= 0) {
        safeStore(this.mem.control, ControlIndex.SELECTED_NEURON, hitId);
        if (this.onNeuronSelected) this.onNeuronSelected(hitId);
      } else {
        this.isPanningFallback = true;
        this.lastMousePos = { x: e.clientX, y: e.clientY };
        safeStore(this.mem.control, ControlIndex.SELECTED_NEURON, -1);
        if (this.onNeuronSelected) this.onNeuronSelected(null);
      }
    }
  }

  private handleFallbackPointerMove(e: MouseEvent): void {
    if (!this.fallbackCanvas) return;
    const rect = this.fallbackCanvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    this.mouseScreenPos = { x: mx, y: my };

    if (this.isPanningFallback) {
      const dx = e.clientX - this.lastMousePos.x;
      const dy = e.clientY - this.lastMousePos.y;
      this.fallbackCam.x += dx;
      this.fallbackCam.y += dy;
      this.lastMousePos = { x: e.clientX, y: e.clientY };
      return;
    }

    if (this.isDraggingWire && this.wireSourceId !== null) {
      const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
      const cx = this.fallbackCanvas.width / 2 + this.fallbackCam.x;
      const cy = this.fallbackCanvas.height / 2 + this.fallbackCam.y;
      const scale = this.fallbackCam.zoom;
      const pos = this.mem.posXYZ;

      let hitTarget = -1;
      let minDist = 20;
      for (let i = 0; i < numNeurons; i++) {
        if (i === this.wireSourceId) continue;
        const sx = cx + pos[i * 3] * scale;
        const sy = cy + pos[i * 3 + 2] * scale;
        const d = Math.hypot(mx - sx, my - sy);
        if (d < minDist) {
          minDist = d;
          hitTarget = i;
        }
      }
      this.wireHoverTargetId = hitTarget >= 0 ? hitTarget : null;
    }
  }

  private handleFallbackPointerUp(): void {
    this.isPanningFallback = false;

    if (this.isDraggingWire) {
      if (this.wireSourceId !== null && this.wireHoverTargetId !== null && this.wireSourceId !== this.wireHoverTargetId) {
        const preId = this.wireSourceId;
        const postId = this.wireHoverTargetId;
        const pos = this.mem.posXYZ;
        const rx = pos[postId * 3] - pos[preId * 3];
        const ry = pos[postId * 3 + 1] - pos[preId * 3 + 1];
        const rz = pos[postId * 3 + 2] - pos[preId * 3 + 2];
        const dist = Math.sqrt(rx * rx + ry * ry + rz * rz);

        if (this.onSynapseDragComplete) {
          this.onSynapseDragComplete(preId, postId, dist);
        }
      }

      this.isDraggingWire = false;
      this.wireSourceId = null;
      this.wireHoverTargetId = null;
    }
  }

  private onWindowResize(): void {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (this.camera) {
      this.camera.aspect = width / (height || 1);
      this.camera.updateProjectionMatrix();
    }
    if (this.hasWebGL && this.renderer) {
      this.renderer.setSize(width, height);
    }
    if (this.fallbackCanvas) {
      this.fallbackCanvas.width = width;
      this.fallbackCanvas.height = height;
    }
  }

  private updateFlyThrough(dt: number): void {
    if (!this.hasWebGL || !this.controls) return;
    const forward = new THREE.Vector3();
    this.camera.getWorldDirection(forward);
    forward.y = 0;
    forward.normalize();

    const right = new THREE.Vector3();
    right.crossVectors(this.camera.up, forward).negate().normalize();

    const move = new THREE.Vector3();
    if (this.keysDown['KeyW']) move.add(forward);
    if (this.keysDown['KeyS']) move.sub(forward);
    if (this.keysDown['KeyD']) move.add(right);
    if (this.keysDown['KeyA']) move.sub(right);
    if (this.keysDown['KeyE']) move.y += 1;
    if (this.keysDown['KeyQ']) move.y -= 1;

    if (move.lengthSq() > 0) {
      move.normalize().multiplyScalar(this.flySpeed * dt);
      this.camera.position.add(move);
      this.controls.target.add(move);
    }
  }

  public render(dt: number): void {
    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    if (numNeurons !== this.cachedNumNeurons) {
      this.syncPositionsFromMemory();
    }

    if (this.hasWebGL && this.renderer) {
      const stateArray = this.aStateAttr.array as Float32Array;
      const vMem = this.mem.vMem;
      const visualFlash = this.mem.visualFlash;

      for (let i = 0; i < numNeurons; i++) {
        const v = vMem[i];
        let flash = visualFlash[i];

        if (flash > 0) {
          flash = Math.max(0, flash - 14);
          visualFlash[i] = flash;
        }

        stateArray[i * 2] = Math.max(-0.25, Math.min(1.0, v / 1024.0));
        stateArray[i * 2 + 1] = flash / 255.0;
      }

      this.aStateAttr.needsUpdate = true;

      if (this.selectionRing.visible) {
        this.selectionRing.rotation.x += dt * 0.8;
        this.selectionRing.rotation.y += dt * 1.2;
      }

      this.updateTravellingPulses();
      this.updateFlyThrough(dt);
      if (this.controls) this.controls.update();

      this.renderer.render(this.scene, this.camera);
    } else {
      this.renderFallback2D(dt);
    }
  }

  private renderFallback2D(dt: number): void {
    if (!this.fallbackCanvas || !this.fallbackCtx) return;
    const ctx = this.fallbackCtx;
    const w = this.fallbackCanvas.width;
    const h = this.fallbackCanvas.height;

    ctx.fillStyle = '#06070c';
    ctx.fillRect(0, 0, w, h);

    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    const selectedId = safeLoad(this.mem.control, ControlIndex.SELECTED_NEURON);
    const cx = w / 2 + this.fallbackCam.x;
    const cy = h / 2 + this.fallbackCam.y;
    const scale = this.fallbackCam.zoom;

    const toX = (x: number) => cx + x * scale;
    const toY = (z: number) => cy + z * scale;

    // 1. Draw Reference Grid
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.12)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    const span = 100 * scale;
    const step = 20 * scale;
    for (let gx = -span; gx <= span; gx += step) {
      ctx.moveTo(cx + gx, cy - span);
      ctx.lineTo(cx + gx, cy + span);
    }
    for (let gz = -span; gz <= span; gz += step) {
      ctx.moveTo(cx - span, cy + gz);
      ctx.lineTo(cx + span, cy + gz);
    }
    ctx.stroke();

    const pos = this.mem.posXYZ;
    const rowPtr = this.mem.rowPtr;
    const colIdx = this.mem.colIdx;
    const weights = this.mem.weights;

    // 2. Draw Synapses
    if (numNeurons > 0) {
      for (let i = 0; i < numNeurons; i++) {
        if (this.popFilter?.isHidden(i)) continue;
        if (!this.showGlobalSynapses && i !== selectedId) continue;
        const start = rowPtr[i];
        const end = rowPtr[i + 1];
        const xi = toX(pos[i * 3]);
        const yi = toY(pos[i * 3 + 2]);

        for (let s = start; s < end; s++) {
          const j = colIdx[s];
          if (j >= numNeurons || this.popFilter?.isHidden(j)) continue;
          const xj = toX(pos[j * 3]);
          const yj = toY(pos[j * 3 + 2]);
          const isExc = weights[s] >= 0;

          ctx.strokeStyle = isExc ? 'rgba(0, 240, 255, 0.35)' : 'rgba(255, 0, 127, 0.35)';
          ctx.lineWidth = i === selectedId ? 2 : 1;
          ctx.beginPath();
          ctx.moveTo(xi, yi);
          ctx.lineTo(xj, yj);
          ctx.stroke();
        }
      }

      // 3. Draw Travelling Pulses
      for (let i = 0; i < numNeurons; i++) {
        if (this.popFilter?.isHidden(i)) continue;
        const bf = this.mem.spikeBitfield[i];
        if (bf === 0) continue;
        const start = rowPtr[i];
        const end = rowPtr[i + 1];
        const xi = toX(pos[i * 3]);
        const yi = toY(pos[i * 3 + 2]);

        for (let s = start; s < end; s++) {
          const delay = this.mem.delays[s];
          const j = colIdx[s];
          if (j >= numNeurons || this.popFilter?.isHidden(j)) continue;
          const xj = toX(pos[j * 3]);
          const yj = toY(pos[j * 3 + 2]);
          const isExc = weights[s] >= 0;

          for (let b = 1; b <= delay; b++) {
            if ((bf >>> b) & 1) {
              const prog = b / delay;
              const px = xi + (xj - xi) * prog;
              const py = yi + (yj - yi) * prog;

              ctx.fillStyle = isExc ? '#00ffff' : '#ff007f';
              ctx.beginPath();
              ctx.arc(px, py, 3.5, 0, Math.PI * 2);
              ctx.fill();
            }
          }
        }
      }

      // 4. Draw Somas
      for (let i = 0; i < numNeurons; i++) {
        if (this.popFilter?.isHidden(i)) continue;
        const sx = toX(pos[i * 3]);
        const sy = toY(pos[i * 3 + 2]);

        let flash = this.mem.visualFlash[i];
        if (flash > 0) {
          flash = Math.max(0, flash - 14);
          this.mem.visualFlash[i] = flash;
        }

        let color = '#00f0ff';
        const customColor = this.popFilter?.getColor(i);
        if (customColor) {
            color = customColor;
        } else {
            const mode = this.mem.neuronMode[i];
            if (mode === NeuronMode.POISSON || mode === NeuronMode.BURSTER) {
              color = '#ffd700';
            } else if (this.mem.baseWeight[i] < 0) {
              color = '#ff007f';
            }
        }

        const r = flash > 120 ? 8 : 5.5;

        // Flash halo
        if (flash > 0) {
          ctx.fillStyle = `rgba(255, 255, 255, ${flash / 255})`;
          ctx.beginPath();
          ctx.arc(sx, sy, r + 5, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.fillStyle = flash > 120 ? '#ffffff' : color;
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.fill();

        // Selected indicator
        if (i === selectedId) {
          ctx.strokeStyle = '#00ffff';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(sx, sy, r + 5, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Hover target in wire mode
        if (this.isDraggingWire && i === this.wireHoverTargetId) {
          ctx.strokeStyle = '#ffd700';
          ctx.lineWidth = 2.5;
          ctx.beginPath();
          ctx.arc(sx, sy, r + 7, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
    }

    // 5. Draw Wire Drag Preview in 2D
    if (this.isDraggingWire && this.wireSourceId !== null) {
      const sx0 = toX(pos[this.wireSourceId * 3]);
      const sy0 = toY(pos[this.wireSourceId * 3 + 2]);
      const sx1 = this.mouseScreenPos.x;
      const sy1 = this.mouseScreenPos.y;

      ctx.strokeStyle = '#00f0ff';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(sx0, sy0);
      ctx.lineTo(sx1, sy1);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  private updateTravellingPulses(): void {
    const selectedId = safeLoad(this.mem.control, ControlIndex.SELECTED_NEURON);
    const pos = this.mem.posXYZ;
    let pulseCount = 0;

    const startAttr = this.pulsePoints.geometry.getAttribute('aStartPos') as THREE.BufferAttribute;
    const endAttr = this.pulsePoints.geometry.getAttribute('aEndPos') as THREE.BufferAttribute;
    const progAttr = this.pulsePoints.geometry.getAttribute('aProgress') as THREE.BufferAttribute;
    const signAttr = this.pulsePoints.geometry.getAttribute('aWeightSign') as THREE.BufferAttribute;

    const sArr = startAttr.array as Float32Array;
    const eArr = endAttr.array as Float32Array;
    const pArr = progAttr.array as Float32Array;
    const wArr = signAttr.array as Float32Array;

    const evalNeuron = (i: number) => {
      const bf = this.mem.spikeBitfield[i];
      if (bf === 0) return;

      const xi = pos[i * 3];
      const yi = pos[i * 3 + 1];
      const zi = pos[i * 3 + 2];

      if (this.popFilter?.isHidden(i)) return;
      const start = this.mem.rowPtr[i];
      const end = this.mem.rowPtr[i + 1];

      for (let s = start; s < end; s++) {
        if (pulseCount >= this.maxPulses) return;

        const delay = this.mem.delays[s];
        for (let b = 1; b <= delay; b++) {
          if ((bf >>> b) & 1) {
            const j = this.mem.colIdx[s];
            if (j >= this.cachedNumNeurons || this.popFilter?.isHidden(j)) continue;

            const pIdx = pulseCount;
            const pIdx3 = pIdx * 3;

            sArr[pIdx3] = xi;
            sArr[pIdx3 + 1] = yi;
            sArr[pIdx3 + 2] = zi;

            eArr[pIdx3] = pos[j * 3];
            eArr[pIdx3 + 1] = pos[j * 3 + 1];
            eArr[pIdx3 + 2] = pos[j * 3 + 2];

            pArr[pIdx] = b / delay;
            wArr[pIdx] = this.mem.weights[s] >= 0 ? 1.0 : -1.0;

            pulseCount++;
            if (pulseCount >= this.maxPulses) return;
          }
        }
      }
    };

    if (selectedId >= 0 && selectedId < this.cachedNumNeurons) {
      evalNeuron(selectedId);
    } else {
      for (let i = 0; i < this.cachedNumNeurons; i++) {
        evalNeuron(i);
        if (pulseCount >= this.maxPulses) break;
      }
    }

    (this.pulsePoints.geometry as THREE.BufferGeometry).setDrawRange(0, pulseCount);
    startAttr.needsUpdate = true;
    endAttr.needsUpdate = true;
    progAttr.needsUpdate = true;
    signAttr.needsUpdate = true;
  }
}
