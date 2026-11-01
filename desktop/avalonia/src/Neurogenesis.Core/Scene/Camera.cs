using System.Numerics;

namespace Neurogenesis.Core.Scene;

/// <summary>Orbit camera around a target: yaw / pitch in radians, distance in space units, vertical field of view
/// 45°. Matrices use System.Numerics' row-vector convention; uploaded untransposed they act as column-major GL
/// matrices.</summary>
public sealed class Camera
{
    public Vector3 Target { get; set; }
    public float Yaw { get; set; } = 0.6f;
    public float Pitch { get; set; } = 0.35f;
    public float Distance { get; set; } = 150f;
    /// <summary>Distance at which neurons have their nominal pixel size (set when framing).</summary>
    public float ReferenceDistance { get; private set; } = 150f;
    public const float FovY = MathF.PI / 4;

    public Vector3 Eye => Target + Distance * new Vector3(
        MathF.Cos(Pitch) * MathF.Sin(Yaw), MathF.Sin(Pitch), MathF.Cos(Pitch) * MathF.Cos(Yaw));

    public Matrix4x4 View => Matrix4x4.CreateLookAt(Eye, Target, Vector3.UnitY);

    public Matrix4x4 Projection(float aspect) =>
        Matrix4x4.CreatePerspectiveFieldOfView(FovY, MathF.Max(aspect, 1e-3f), Distance * 1e-3f, Distance * 20f + 1f);

    /// <summary>Centres on a sphere of <paramref name="radius"/> around <paramref name="center"/> so it fills the view.</summary>
    public void Frame(Vector3 center, float radius)
    {
        Target = center;
        Distance = ReferenceDistance = MathF.Max(radius, 1e-3f) / MathF.Sin(FovY / 2) * 1.1f;
    }

    /// <summary>Rotates by a mouse drag of (dx, dy) pixels.</summary>
    public void Orbit(float dx, float dy)
    {
        Yaw -= dx * 0.008f;
        Pitch = Math.Clamp(Pitch + dy * 0.008f, -1.55f, 1.55f);
    }

    /// <summary>Moves the target by a drag of (dx, dy) pixels in a view <paramref name="height"/> pixels high.</summary>
    public void Pan(float dx, float dy, float height)
    {
        Matrix4x4.Invert(View, out var inv);
        var right = new Vector3(inv.M11, inv.M12, inv.M13);
        var up = new Vector3(inv.M21, inv.M22, inv.M23);
        float unitsPerPixel = 2 * Distance * MathF.Tan(FovY / 2) / MathF.Max(height, 1);
        Target += (-dx * right + dy * up) * unitsPerPixel;
    }

    public void Zoom(float wheelSteps) => Distance = Math.Clamp(Distance * MathF.Pow(0.88f, wheelSteps), 1e-3f, 1e7f);

    /// <summary>Pixel radius of a neuron with size scale <paramref name="scale"/> at view depth <paramref name="w"/>
    /// (the formula of neuron.vert).</summary>
    public float PixelRadius(float pointSizePx, float attenuation, float scale, float w) =>
        MathF.Max(1f, pointSizePx * scale * float.Lerp(1f, Math.Clamp(ReferenceDistance / MathF.Max(w, 1e-3f), 0.15f, 6f), attenuation));

    /// <summary>The instance under pixel (<paramref name="x"/>, <paramref name="y"/>) of a view of
    /// <paramref name="width"/> × <paramref name="height"/>, nearest the camera among those whose disc (at least
    /// <paramref name="minPx"/>) contains it; -1 if none. O(instances).</summary>
    public int Pick(float[] instances, int stride, float width, float height, float x, float y, float pointSizePx,
                    float attenuation, float minPx = 6f)
    {
        var vp = View * Projection(width / height);
        int best = -1;
        float bestW = float.MaxValue;
        for (int k = 0, o = 0; o + 3 < instances.Length; k++, o += stride)
        {
            var c = Vector4.Transform(new Vector4(instances[o], instances[o + 1], instances[o + 2], 1), vp);
            if (c.W <= 0) continue;
            float sx = (c.X / c.W + 1) / 2 * width, sy = (1 - c.Y / c.W) / 2 * height;
            float r = MathF.Max(minPx, PixelRadius(pointSizePx, attenuation, instances[o + 3], c.W));
            float dx = sx - x, dy = sy - y;
            if (dx * dx + dy * dy <= r * r && c.W < bestW) { best = k; bestW = c.W; }
        }
        return best;
    }
}
