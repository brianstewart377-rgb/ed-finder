import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

type SelectedRouteState = {
  selectedRouteId: string | null;
  selectRoute: (routeId: string | null) => void;
};

export const useSelectedRouteStore = create<SelectedRouteState>()(
  persist(
    (set) => ({
      selectedRouteId: null,
      selectRoute: (selectedRouteId) => set({ selectedRouteId }),
    }),
    {
      name: 'ed_selected_route',
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
