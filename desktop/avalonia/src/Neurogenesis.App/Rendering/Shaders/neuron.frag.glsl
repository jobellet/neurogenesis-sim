// Shaded disc that looks like a sphere (body only; see neuron.vert.glsl for the header).
in vec2 vCorner;
in vec4 vColor;
in float vFlash;
layout(location = 0) out vec4 fragColor;

void main() {
    float r2 = dot(vCorner, vCorner);
    if (r2 > 1.0) discard;
    float diff = sqrt(1.0 - r2);
    vec3 col = vColor.rgb * (0.35 + 0.75 * diff) + pow(diff, 24.0) * 0.25;
    col = mix(col, vec3(1.0, 0.96, 0.7), vFlash * 0.85);
    fragColor = vec4(col, vColor.a);
}
