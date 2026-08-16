import type { Meta, StoryObj } from '@storybook/react';
import { Canvas } from '@react-three/fiber';
import { VolumetricGalaxy } from './VolumetricGalaxy';

const meta: Meta = {
  title: 'Map/VolumetricGalaxy',
  component: VolumetricGalaxy,
  render: (args) => (
    <Canvas
      style={{ width: '100%', height: '600px', background: '#000' }}
      orthographic={false}
      camera={{ position: [0, 0, 100], fov: 75 }}
    >
      <VolumetricGalaxy opacity={args.opacity} />
      <ambientLight intensity={0.1} />
    </Canvas>
  ),
  argTypes: {
    opacity: {
      control: { type: 'range', min: 0, max: 1, step: 0.1 },
      description: 'Opacity of the volumetric galaxy rendering',
    },
  },
};

export default meta;
type Story = StoryObj<typeof VolumetricGalaxy>;

export const Default: Story = {
  args: {
    opacity: 1,
  },
};

export const FadingOut: Story = {
  args: {
    opacity: 0.5,
  },
};

export const Hidden: Story = {
  args: {
    opacity: 0,
  },
};
