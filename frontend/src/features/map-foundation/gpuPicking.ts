export function encodeGpuPickColor(index: number): [number, number, number] {
  const id = index + 1;
  return [(id & 255) / 255, ((id >> 8) & 255) / 255, ((id >> 16) & 255) / 255];
}

export function decodeGpuPickColor(pixel: Uint8Array): number | null {
  const id = pixel[0] | (pixel[1] << 8) | (pixel[2] << 16);
  return id === 0 ? null : id - 1;
}
