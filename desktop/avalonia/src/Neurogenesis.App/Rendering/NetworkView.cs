using System.Numerics;
using Avalonia;
using Avalonia.Input;
using Avalonia.OpenGL;
using Avalonia.OpenGL.Controls;
using Neurogenesis.Core.Scene;
using Silk.NET.OpenGL;

namespace Neurogenesis.App.Rendering;

/// <summary>The 3D network view: neurons as instanced billboards, synapses as lines, through Silk.NET.OpenGL on
/// Avalonia's GL context (ANGLE / OpenGL ES 3.0 on Windows by default, desktop GL 3.3 elsewhere). Drag to orbit,
/// shift-, right- or middle-drag to pan, wheel to zoom, F to frame, click to pick a neuron. Renders only when
/// something changed.</summary>
public sealed unsafe class NetworkView : OpenGlControlBase
{
    public static readonly StyledProperty<SceneData?> SceneProperty =
        AvaloniaProperty.Register<NetworkView, SceneData?>(nameof(Scene));
    public static readonly StyledProperty<float[]> InstancesProperty =
        AvaloniaProperty.Register<NetworkView, float[]>(nameof(Instances), Array.Empty<float>());

    public SceneData? Scene { get => GetValue(SceneProperty); set => SetValue(SceneProperty, value); }
    /// <summary>Neuron instance data, <see cref="SceneData.InstanceStride"/> floats each.</summary>
    public float[] Instances { get => GetValue(InstancesProperty); set => SetValue(InstancesProperty, value); }

    /// <summary>Raised with the neuron index under a click, or -1 when the click hits none.</summary>
    public event Action<int>? NeuronClicked;

    /// <summary>"OpenGL ES 3.0 (GLSL ES 3.00)" or "OpenGL 3.3 (GLSL 3.30)" once initialised; for the status bar and
    /// tests.</summary>
    public string? GlDescription { get; private set; }
    public event Action<string>? GlError;

    public Camera Camera { get; } = new();

    private GL? _gl;
    private uint _neuronProg, _lineProg, _neuronVao, _lineVao, _quadVbo, _instVbo, _lineVbo;
    private int _instCount, _lineVertCount;
    private bool _instDirty, _linesDirty;
    private Point _pressAt, _last;
    private bool _dragging;

    static NetworkView()
    {
        FocusableProperty.OverrideDefaultValue<NetworkView>(true);
    }

    protected override void OnPropertyChanged(AvaloniaPropertyChangedEventArgs change)
    {
        base.OnPropertyChanged(change);
        if (change.Property == SceneProperty)
        {
            _linesDirty = true;
            Frame();
        }
        else if (change.Property == InstancesProperty)
        {
            _instDirty = true;
            RequestNextFrameRendering();
        }
        else if (change.Property == BoundsProperty)
        {
            RequestNextFrameRendering();
        }
    }

    /// <summary>Points the camera at the whole network.</summary>
    public void Frame()
    {
        if (Scene is { } s) Camera.Frame(Vector3.Zero, s.Radius);
        RequestNextFrameRendering();
    }

    protected override void OnOpenGlInit(GlInterface gl)
    {
        _gl = GL.GetApi(gl.GetProcAddress);
        bool es = GlVersion.Type == GlProfileType.OpenGLES;
        GlDescription = es ? $"OpenGL ES {GlVersion.Major}.{GlVersion.Minor} (GLSL ES 3.00)"
                           : $"OpenGL {GlVersion.Major}.{GlVersion.Minor} (GLSL 3.30)";
        try
        {
            _neuronProg = Shaders.Program(_gl, es, "neuron");
            _lineProg = Shaders.Program(_gl, es, "line");
        }
        catch (InvalidOperationException e)
        {
            GlError?.Invoke(e.Message);
            return;
        }

        _quadVbo = _gl.GenBuffer();
        _gl.BindBuffer(BufferTargetARB.ArrayBuffer, _quadVbo);
        _gl.BufferData<float>(BufferTargetARB.ArrayBuffer, new float[] { -1, -1, 1, -1, -1, 1, 1, 1 }, BufferUsageARB.StaticDraw);
        _instVbo = _gl.GenBuffer();
        _neuronVao = _gl.GenVertexArray();
        _gl.BindVertexArray(_neuronVao);
        _gl.BindBuffer(BufferTargetARB.ArrayBuffer, _quadVbo);
        Attrib(0, 2, 2, 0);
        _gl.BindBuffer(BufferTargetARB.ArrayBuffer, _instVbo);
        const int s = SceneData.InstanceStride;
        Attrib(1, 3, s, 0, divisor: 1);
        Attrib(2, 1, s, 3, divisor: 1);
        Attrib(3, 4, s, 4, divisor: 1);

        _lineVbo = _gl.GenBuffer();
        _lineVao = _gl.GenVertexArray();
        _gl.BindVertexArray(_lineVao);
        _gl.BindBuffer(BufferTargetARB.ArrayBuffer, _lineVbo);
        Attrib(0, 3, SceneData.LineStride, 0);
        Attrib(1, 4, SceneData.LineStride, 3);
        _gl.BindVertexArray(0);
        _instDirty = _linesDirty = true;
    }

    private void Attrib(uint index, int size, int strideFloats, int offsetFloats, uint divisor = 0)
    {
        _gl!.EnableVertexAttribArray(index);
        _gl.VertexAttribPointer(index, size, VertexAttribPointerType.Float, false, (uint)(strideFloats * 4), (void*)(offsetFloats * 4));
        if (divisor != 0) _gl.VertexAttribDivisor(index, divisor);
    }

    protected override void OnOpenGlDeinit(GlInterface gl)
    {
        if (_gl is null) return;
        _gl.DeleteBuffer(_quadVbo);
        _gl.DeleteBuffer(_instVbo);
        _gl.DeleteBuffer(_lineVbo);
        _gl.DeleteVertexArray(_neuronVao);
        _gl.DeleteVertexArray(_lineVao);
        _gl.DeleteProgram(_neuronProg);
        _gl.DeleteProgram(_lineProg);
        _gl = null;
    }

    protected override void OnOpenGlRender(GlInterface gl, int fb)
    {
        if (_gl is null || _neuronProg == 0) return;
        var g = _gl;
        double scaling = VisualRoot?.RenderScaling ?? 1.0;
        int w = Math.Max(1, (int)(Bounds.Width * scaling)), h = Math.Max(1, (int)(Bounds.Height * scaling));
        g.Viewport(0, 0, (uint)w, (uint)h);
        var style = Scene?.Style ?? Core.Style.VisualStyle.Default;
        var bg = style.Background;
        g.ClearColor(bg.X, bg.Y, bg.Z, bg.W);
        g.Clear(ClearBufferMask.ColorBufferBit | ClearBufferMask.DepthBufferBit);
        Upload();

        var view = Camera.View;
        var proj = Camera.Projection((float)w / h);
        g.Enable(EnableCap.DepthTest);
        g.Enable(EnableCap.Blend);
        g.BlendFunc(BlendingFactor.SrcAlpha, BlendingFactor.OneMinusSrcAlpha);

        if (_instCount > 0)
        {
            g.UseProgram(_neuronProg);
            Matrix(_neuronProg, "uView", view);
            Matrix(_neuronProg, "uProj", proj);
            g.Uniform2(g.GetUniformLocation(_neuronProg, "uViewport"), (float)w, (float)h);
            g.Uniform1(g.GetUniformLocation(_neuronProg, "uPointSize"), style.PointSizePx * (float)scaling);
            g.Uniform1(g.GetUniformLocation(_neuronProg, "uAttenuation"), style.Attenuation);
            g.Uniform1(g.GetUniformLocation(_neuronProg, "uRefDistance"), Camera.ReferenceDistance);
            g.BindVertexArray(_neuronVao);
            g.DrawArraysInstanced(PrimitiveType.TriangleStrip, 0, 4, (uint)_instCount);
        }
        if (_lineVertCount > 0)
        {
            g.DepthMask(false);
            g.UseProgram(_lineProg);
            Matrix(_lineProg, "uView", view);
            Matrix(_lineProg, "uProj", proj);
            g.BindVertexArray(_lineVao);
            g.DrawArrays(PrimitiveType.Lines, 0, (uint)_lineVertCount);
            g.DepthMask(true);
        }
        g.BindVertexArray(0);
        g.UseProgram(0);
        g.Disable(EnableCap.DepthTest);
        g.Disable(EnableCap.Blend);
    }

    private void Upload()
    {
        var g = _gl!;
        if (_instDirty)
        {
            var a = Instances;
            g.BindBuffer(BufferTargetARB.ArrayBuffer, _instVbo);
            g.BufferData<float>(BufferTargetARB.ArrayBuffer, a, BufferUsageARB.DynamicDraw);
            _instCount = a.Length / SceneData.InstanceStride;
            _instDirty = false;
        }
        if (_linesDirty)
        {
            var a = Scene?.LineVertices ?? Array.Empty<float>();
            g.BindBuffer(BufferTargetARB.ArrayBuffer, _lineVbo);
            g.BufferData<float>(BufferTargetARB.ArrayBuffer, a, BufferUsageARB.StaticDraw);
            _lineVertCount = a.Length / SceneData.LineStride;
            _linesDirty = false;
        }
    }

    private void Matrix(uint prog, string name, Matrix4x4 m) =>
        _gl!.UniformMatrix4(_gl.GetUniformLocation(prog, name), 1, false, (float*)&m);

    protected override void OnPointerPressed(PointerPressedEventArgs e)
    {
        base.OnPointerPressed(e);
        Focus();
        _pressAt = _last = e.GetPosition(this);
        _dragging = true;
        e.Pointer.Capture(this);
    }

    protected override void OnPointerMoved(PointerEventArgs e)
    {
        base.OnPointerMoved(e);
        if (!_dragging) return;
        var p = e.GetPosition(this);
        var d = p - _last;
        _last = p;
        var props = e.GetCurrentPoint(this).Properties;
        bool pan = props.IsRightButtonPressed || props.IsMiddleButtonPressed || e.KeyModifiers.HasFlag(KeyModifiers.Shift);
        if (pan) Camera.Pan((float)d.X, (float)d.Y, (float)Bounds.Height);
        else Camera.Orbit((float)d.X, (float)d.Y);
        RequestNextFrameRendering();
    }

    protected override void OnPointerReleased(PointerReleasedEventArgs e)
    {
        base.OnPointerReleased(e);
        _dragging = false;
        e.Pointer.Capture(null);
        var p = e.GetPosition(this);
        if (e.InitialPressMouseButton == MouseButton.Left && Math.Abs(p.X - _pressAt.X) + Math.Abs(p.Y - _pressAt.Y) < 4)
            NeuronClicked?.Invoke(PickAt(p));
    }

    /// <summary>The neuron under point <paramref name="p"/> (in this control's coordinates), or -1.</summary>
    public int PickAt(Point p)
    {
        if (Scene is not { } s) return -1;
        var style = s.Style;
        int k = Camera.Pick(Instances, SceneData.InstanceStride, (float)Bounds.Width, (float)Bounds.Height,
                            (float)p.X, (float)p.Y, style.PointSizePx, style.Attenuation);
        return k >= 0 ? s.InstanceNeuron[k] : -1;
    }

    protected override void OnPointerWheelChanged(PointerWheelEventArgs e)
    {
        base.OnPointerWheelChanged(e);
        Camera.Zoom((float)e.Delta.Y);
        RequestNextFrameRendering();
        e.Handled = true;
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        if (e.Key == Key.F) { Frame(); e.Handled = true; }
    }


}
