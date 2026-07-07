import type { SimulateBuildResponse } from '@/types/api';

export function purityLabel(value: number): string {
  if (value >= 0.75) return 'High';
  if (value >= 0.55) return 'Medium';
  return 'Low';
}

export function purityTone(value: number): string {
  if (value >= 0.75) return 'text-green';
  if (value >= 0.55) return 'text-gold';
  return 'text-red';
}

export function repairSeverityTone(severity: string): 'good' | 'warn' | 'default' {
  if (severity === 'critical' || severity === 'high' || severity === 'medium') return 'warn';
  if (severity === 'low') return 'good';
  return 'default';
}

export function serviceTone(status: string): string {
  if (status === 'active') return 'text-green';
  if (status === 'locked') return 'text-gold';
  return 'text-silver-dk';
}

export function levelTone(value: string): 'default' | 'good' | 'warn' {
  if (value === 'observed' || value === 'verified' || value === 'community_observed') return 'good';
  if (value === 'estimated' || value === 'speculative' || value === 'unknown' || value === 'predicted') return 'warn';
  return 'default';
}

export function confidenceLevelTone(value: string): string {
  if (value === 'observed' || value === 'verified' || value === 'community_observed') return 'text-green';
  if (value === 'estimated' || value === 'speculative') return 'text-gold';
  if (value === 'unknown') return 'text-silver-dk';
  return 'text-cyan';
}

export function confidenceTone(value: number): 'green' | 'gold' | 'red' {
  if (value >= 0.75) return 'green';
  if (value >= 0.55) return 'gold';
  return 'red';
}

export function complexityTone(value: SimulateBuildResponse['build_complexity']): 'green' | 'gold' | 'orange' | 'red' {
  if (value === 'simple') return 'green';
  if (value === 'moderate') return 'gold';
  if (value === 'advanced') return 'orange';
  return 'red';
}
