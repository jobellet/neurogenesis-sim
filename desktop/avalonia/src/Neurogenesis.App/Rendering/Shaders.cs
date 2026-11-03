using Silk.NET.OpenGL;

namespace Neurogenesis.App.Rendering;

/// <summary>Builds GL programs from the embedded GLSL bodies (Rendering/Shaders/*.glsl). One source serves both
/// dialects; only the version header differs.</summary>
public static class Shaders
{
    public const string EsHeader = "#version 300 es\nprecision highp float;\n";
    public const string DesktopHeader = "#version 330 core\n";

    /// <summary>The full source of <paramref name="file"/> (e.g. "neuron.vert.glsl") for OpenGL ES or desktop GL.</summary>
    public static string Source(string file, bool es)
    {
        using var s = typeof(Shaders).Assembly.GetManifestResourceStream(file)
            ?? throw new InvalidOperationException($"shader {file} is not embedded");
        using var r = new StreamReader(s);
        return (es ? EsHeader : DesktopHeader) + r.ReadToEnd();
    }

    /// <summary>Compiles and links <paramref name="name"/>.vert.glsl and <paramref name="name"/>.frag.glsl.</summary>
    public static uint Program(GL gl, bool es, string name)
    {
        uint vs = Compile(gl, ShaderType.VertexShader, name + ".vert.glsl", es);
        uint fs = Compile(gl, ShaderType.FragmentShader, name + ".frag.glsl", es);
        uint p = gl.CreateProgram();
        gl.AttachShader(p, vs);
        gl.AttachShader(p, fs);
        gl.LinkProgram(p);
        gl.GetProgram(p, ProgramPropertyARB.LinkStatus, out int ok);
        gl.DeleteShader(vs);
        gl.DeleteShader(fs);
        if (ok == 0) throw new InvalidOperationException($"linking {name}: {gl.GetProgramInfoLog(p)}");
        return p;
    }

    private static uint Compile(GL gl, ShaderType type, string file, bool es)
    {
        uint id = gl.CreateShader(type);
        gl.ShaderSource(id, Source(file, es));
        gl.CompileShader(id);
        gl.GetShader(id, ShaderParameterName.CompileStatus, out int ok);
        if (ok == 0) throw new InvalidOperationException($"compiling {file}: {gl.GetShaderInfoLog(id)}");
        return id;
    }
}
