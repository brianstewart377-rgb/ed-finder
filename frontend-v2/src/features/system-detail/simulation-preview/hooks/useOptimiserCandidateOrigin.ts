import { useState } from 'react';

export interface UseOptimiserCandidateOriginResult {
  optimiserCandidateOriginLabel: string | null;
  optimiserCandidateWasEdited: boolean;
  setLoadedOptimiserCandidate: (label: string) => void;
  clearOptimiserCandidateOrigin: () => void;
  markOptimiserCandidateEdited: () => void;
}

export function useOptimiserCandidateOrigin(): UseOptimiserCandidateOriginResult {
  const [optimiserCandidateOriginLabel, setOptimiserCandidateOriginLabel] = useState<string | null>(null);
  const [optimiserCandidateWasEdited, setOptimiserCandidateWasEdited] = useState(false);

  const setLoadedOptimiserCandidate = (label: string) => {
    setOptimiserCandidateOriginLabel(label);
    setOptimiserCandidateWasEdited(false);
  };

  const clearOptimiserCandidateOrigin = () => {
    setOptimiserCandidateOriginLabel(null);
    setOptimiserCandidateWasEdited(false);
  };

  const markOptimiserCandidateEdited = () => {
    if (optimiserCandidateOriginLabel) {
      setOptimiserCandidateWasEdited(true);
    }
  };

  return {
    optimiserCandidateOriginLabel,
    optimiserCandidateWasEdited,
    setLoadedOptimiserCandidate,
    clearOptimiserCandidateOrigin,
    markOptimiserCandidateEdited,
  };
}
