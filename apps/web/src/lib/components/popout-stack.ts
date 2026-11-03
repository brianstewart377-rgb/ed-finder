// Tool order is shared by Inspect and Plan. Registration follows opening order;
// hidden task panels unregister until their tools become visible again.
const panels: {
  element: HTMLElement;
  setLayer?: (layer: number) => void;
}[] = [];

function updateLayers(): void {
  panels.forEach((entry, index) => entry.setLayer?.(30 + index));
}

export function registerPopout(
  element: HTMLElement,
  setLayer?: (layer: number) => void,
): () => void {
  const entry = { element, setLayer };
  panels.push(entry);
  updateLayers();
  return () => {
    const index = panels.indexOf(entry);
    if (index !== -1) panels.splice(index, 1);
    updateLayers();
  };
}

export function isTopmostPopout(element: HTMLElement | undefined): boolean {
  return !!element && panels.at(-1)?.element === element;
}
