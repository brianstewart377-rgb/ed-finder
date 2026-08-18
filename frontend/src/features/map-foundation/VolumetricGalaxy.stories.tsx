import { Canvas } from '@react-three/fiber';
import { useState } from 'react';
import { VolumetricGalaxy } from './VolumetricGalaxy';
import { GalaxyBackdrop } from './GalaxyBackdrop';

export default {
  title: 'Map/VolumetricGalaxy',
  component: VolumetricGalaxy,
};

function VolumetricGalaxyCanvas({ opacity }: { opacity: number }) {
  return (
    <Canvas camera={{ position: [0, 10000, 0], fov: 42 }}>
      <color attach="background" args={['#03070b']} />
      <fog attach="fog" args={['#03070b', 5000, 50000]} />

      {/* Background galaxy for reference */}
      <GalaxyBackdrop spatial zoom={100} />

      {/* Volumetric rendering — should appear at same location */}
      <VolumetricGalaxy opacity={opacity} />
    </Canvas>
  );
}

export const Default = () => {
  const [opacity, setOpacity] = useState(0.8);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100vh' }}>
      <div style={{ height: '80%' }}>
        <VolumetricGalaxyCanvas opacity={opacity} />
      </div>
      <div style={{
        height: '20%',
        background: '#1a1a1a',
        padding: '20px',
        overflowY: 'auto',
        color: '#fff',
        fontFamily: 'monospace',
      }}>
        <label>
          Volumetric Opacity:
          {' '}
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={opacity}
            onChange={(e) => setOpacity(parseFloat(e.target.value))}
          />
          {' '}
          {opacity.toFixed(2)}
        </label>
        <p>Expected: Volumetric glow appears at galactic center, aligned with star backdrop</p>
        <p>Camera: [0, 10000, 0], looking at galaxy center [25.2, 0, 25899.9]</p>
      </div>
    </div>
  );
};
