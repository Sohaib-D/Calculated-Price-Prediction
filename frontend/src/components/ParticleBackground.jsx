import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Points, PointMaterial } from "@react-three/drei";

function buildSpherePointCloud(totalPoints = 3200, radius = 1.8) {
  const points = new Float32Array(totalPoints * 3);
  for (let i = 0; i < totalPoints; i += 1) {
    const i3 = i * 3;
    const u = Math.random();
    const v = Math.random();
    const theta = 2 * Math.PI * u;
    const phi = Math.acos(2 * v - 1);
    const r = Math.cbrt(Math.random()) * radius;

    points[i3] = r * Math.sin(phi) * Math.cos(theta);
    points[i3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    points[i3 + 2] = r * Math.cos(phi);
  }
  return points;
}

function FloatingParticles() {
  const ref = useRef(null);
  const points = useMemo(() => buildSpherePointCloud(), []);

  useFrame((state, delta) => {
    if (!ref.current) return;
    ref.current.rotation.x -= delta * 0.015;
    ref.current.rotation.y -= delta * 0.02;
    ref.current.position.x += (state.pointer.x * 0.12 - ref.current.position.x) * 0.04;
    ref.current.position.y += (state.pointer.y * 0.12 - ref.current.position.y) * 0.04;
  });

  return (
    <group rotation={[0, 0, Math.PI / 6]}>
      <Points ref={ref} positions={points} stride={3} frustumCulled={false}>
        <PointMaterial
          transparent
          color="#7dd3fc"
          size={0.0055}
          sizeAttenuation
          depthWrite={false}
          opacity={0.72}
        />
      </Points>
    </group>
  );
}

export default function ParticleBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 opacity-60">
      <Canvas
        dpr={[1, 1.8]}
        camera={{ position: [0, 0, 1.2] }}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      >
        <FloatingParticles />
      </Canvas>
    </div>
  );
}
