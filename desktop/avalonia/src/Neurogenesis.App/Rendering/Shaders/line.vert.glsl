// Synapse lines (body only; see neuron.vert.glsl for the header).
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec4 aColor;
uniform mat4 uView;
uniform mat4 uProj;
out vec4 vColor;

void main() {
    gl_Position = uProj * (uView * vec4(aPos, 1.0));
    vColor = aColor;
}
