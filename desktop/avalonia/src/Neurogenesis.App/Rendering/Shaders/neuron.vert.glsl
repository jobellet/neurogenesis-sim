// Neuron billboards: one screen-aligned disc per instance, sized in pixels (body only; the version header is
// prepended at runtime: "#version 300 es" + precision under OpenGL ES / ANGLE, "#version 330 core" on desktop GL).
layout(location = 0) in vec2 aCorner;
layout(location = 1) in vec3 aPos;
layout(location = 2) in float aSize;
layout(location = 3) in vec4 aColor;
uniform mat4 uView;
uniform mat4 uProj;
uniform vec2 uViewport;
uniform float uPointSize;
uniform float uAttenuation;
uniform float uRefDistance;
out vec2 vCorner;
out vec4 vColor;

void main() {
    vec4 clip = uProj * (uView * vec4(aPos, 1.0));
    float r = uPointSize * aSize * mix(1.0, clamp(uRefDistance / max(clip.w, 1e-3), 0.15, 6.0), uAttenuation);
    r = max(r, 1.0);
    clip.xy += aCorner * r * 2.0 / uViewport * clip.w;
    gl_Position = clip;
    vCorner = aCorner;
    vColor = aColor;
}
