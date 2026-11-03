// Synapse lines (body only; see neuron.vert.glsl for the header).
in vec4 vColor;
layout(location = 0) out vec4 fragColor;

void main() {
    fragColor = vColor;
}
