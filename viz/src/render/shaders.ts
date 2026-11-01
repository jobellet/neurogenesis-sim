/**
 * Custom GLSL Shaders for SNN Visualization
 * High-performance instanced soma rendering, synaptic lines, travelling pulses, and holographic grid.
 */

export const somaVertexShader = /* glsl */ `
  attribute vec3 aPosition;
  attribute vec2 aState; // x: vNorm in [-0.25, 1.0], y: visualFlash in [0.0, 1.0]
  attribute float aType; // 0: Excitatory, 1: Inhibitory, 2: Burster/Poisson, 3: Input, 4: Output (neuron role), 10: Custom Color
  attribute vec3 aColor; 

  varying vec3 vNormal;
  varying vec3 vWorldPos;
  varying vec3 vViewDir;
  varying vec2 vState;
  varying float vType;
  varying vec3 vColor;

  void main() {
    vNormal = normalize(normalMatrix * normal);
    vState = aState;
    vType = aType;
    vColor = aColor;

    // Radius expansion up to +35% during spike flash
    float flashScale = 1.0 + 0.35 * smoothstep(0.3, 1.0, aState.y);
    vec3 transformed = position * flashScale + aPosition;
    vec4 worldPos = modelMatrix * vec4(transformed, 1.0);
    vWorldPos = worldPos.xyz;
    vViewDir = normalize(cameraPosition - vWorldPos);

    gl_Position = projectionMatrix * viewMatrix * worldPos;
  }
`;

export const somaFragmentShader = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vWorldPos;
  varying vec3 vViewDir;
  varying vec2 vState;
  varying float vType;
  varying vec3 vColor;

  uniform vec3 uSelectedColor;
  uniform float uSelectedId;
  uniform float uCurrentInstanceId;

  void main() {
    float vNorm = vState.x;     // [-0.25, 1.0]
    float flash = vState.y;     // [0.0, 1.0]

    // Base colors according to state
    // Hyperpolarized (< 0): Deep indigo
    vec3 colorHyper = vec3(0.09, 0.05, 0.28);
    // Resting (0): Dark teal
    vec3 colorRest = vec3(0.01, 0.18, 0.23);
    // Depolarized (0 -> 1): Vibrant cyan to amber
    vec3 colorDepolLow = vec3(0.0, 0.75, 0.95);
    vec3 colorDepolHigh = vec3(1.0, 0.62, 0.05);

    vec3 baseColor;
    if (vNorm < 0.0) {
      float t = clamp(-vNorm / 0.25, 0.0, 1.0);
      baseColor = mix(colorRest, colorHyper, t);
    } else {
      float t = clamp(vNorm, 0.0, 1.0);
      if (t < 0.5) {
        baseColor = mix(colorRest, colorDepolLow, t * 2.0);
      } else {
        baseColor = mix(colorDepolLow, colorDepolHigh, (t - 0.5) * 2.0);
      }
    }

    // Type-specific tint for differentiation
    vec3 typeColor;
    if (vType < 0.5) {
      typeColor = vec3(0.0, 0.85, 1.0); // Excitatory: Cyan
    } else if (vType < 1.5) {
      typeColor = vec3(1.0, 0.1, 0.65); // Inhibitory: Magenta
    } else if (vType < 2.5) {
      typeColor = vec3(1.0, 0.85, 0.15); // Burster/Poisson: Gold
    } else if (vType < 3.5) {
      typeColor = vec3(0.3, 1.0, 0.35);  // Input (role 1): Green
    } else if (vType < 4.5) {
      typeColor = vec3(1.0, 0.5, 0.1);   // Output (role 2): Orange
    } else {
      typeColor = vColor;                // Custom Color
    }

    // Blend base state color with type characteristic
    baseColor = mix(baseColor, typeColor, 0.22);

    // Active spike flash: emissive pure white core with bloom halo
    if (flash > 0.01) {
      vec3 flashGlow = mix(typeColor, vec3(1.0, 1.0, 1.0), flash);
      baseColor = mix(baseColor, flashGlow, flash * 0.95);
    }

    // 3D Shading & Fresnel rim lighting
    vec3 lightDir = normalize(vec3(0.5, 1.0, 0.8));
    float diff = max(dot(vNormal, lightDir), 0.0) * 0.45 + 0.55;
    float fresnel = pow(1.0 - max(dot(vNormal, vViewDir), 0.0), 2.2);

    vec3 finalColor = baseColor * diff + typeColor * (fresnel * 0.35);

    // Boost emissive component on spike
    finalColor += vec3(1.0) * pow(flash, 1.8) * 0.6;

    gl_FragColor = vec4(finalColor, 0.96);
  }
`;

export const pulseVertexShader = /* glsl */ `
  attribute vec3 aStartPos;
  attribute vec3 aEndPos;
  attribute float aProgress; // [0.0, 1.0] along axon
  attribute float aWeightSign; // >0 Exc, <0 Inh

  varying float vWeightSign;
  varying float vProgress;

  void main() {
    vWeightSign = aWeightSign;
    vProgress = aProgress;

    vec3 currentPos = mix(aStartPos, aEndPos, aProgress);
    vec4 mvPos = modelViewMatrix * vec4(currentPos, 1.0);

    // Size attenuation
    gl_PointSize = (14.0 / -mvPos.z) * 12.0;
    gl_Position = projectionMatrix * mvPos;
  }
`;

export const pulseFragmentShader = /* glsl */ `
  varying float vWeightSign;
  varying float vProgress;

  void main() {
    // Soft circular particle
    vec2 coord = gl_PointCoord - vec2(0.5);
    float dist = length(coord);
    if (dist > 0.5) discard;

    float alpha = smoothstep(0.5, 0.05, dist);

    vec3 color = vWeightSign > 0.0 
      ? vec3(0.0, 1.0, 0.95)   // Cyan/Teal pulse
      : vec3(1.0, 0.15, 0.6);  // Magenta pulse

    // Brighter core
    color += vec3(1.0) * smoothstep(0.3, 0.0, dist);

    gl_FragColor = vec4(color, alpha * 0.9);
  }
`;

export const gridPlaneVertexShader = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vWorldPos;

  void main() {
    vUv = uv;
    vec4 worldPos = modelMatrix * vec4(position, 1.0);
    vWorldPos = worldPos.xyz;
    gl_Position = projectionMatrix * viewMatrix * worldPos;
  }
`;

export const gridPlaneFragmentShader = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vWorldPos;

  uniform float uPlaneY;
  uniform vec3 uGridColor;

  void main() {
    // Grid line spacing
    vec2 coord = vWorldPos.xz / 10.0;
    vec2 grid = abs(fract(coord - 0.5) - 0.5) / fwidth(coord);
    float line = min(grid.x, grid.y);
    float gridAlpha = 1.0 - min(line, 1.0);

    // Distance fade from center
    float dist = length(vWorldPos.xz);
    float radialFade = smoothstep(120.0, 20.0, dist);

    float alpha = gridAlpha * 0.45 * radialFade;
    if (alpha < 0.01) discard;

    vec3 col = mix(vec3(0.0, 0.5, 0.8), vec3(0.0, 0.95, 1.0), gridAlpha);
    gl_FragColor = vec4(col, alpha);
  }
`;
