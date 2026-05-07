import React from 'react';
import { KeyHint } from '../UI/Hud';

export function StatusStrip({ visible, watched, topScore, topName }) {
  return (
    <footer
      className="h-7 flex items-center justify-between px-4 border-t border-[hsla(232,22%,60%,0.22)] bg-[hsla(232,18%,10%,0.78)] backdrop-blur-xl text-[10px] font-mono text-[var(--steel-400)]"
      data-testid="status-strip"
    >
      <div className="flex items-center gap-4">
        <span>
          <span className="text-[var(--steel-200)] tabular-nums">{visible}</span> visible
        </span>
        <span className="text-[var(--steel-700)]">·</span>
        <span>
          <span className="text-[var(--steel-200)] tabular-nums">{watched}</span> watchlisted
        </span>
        <span className="text-[var(--steel-700)]">·</span>
        <span>
          top score{' '}
          <span className="text-[var(--ed-orange-lt)] text-glow-orange tabular-nums">{topScore}</span>{' '}
          <span className="text-[var(--steel-300)]">{topName}</span>
        </span>
      </div>
      <div className="flex items-center gap-3">
        <span className="hidden md:inline-block font-mono text-[8px] text-[var(--steel-500)] opacity-70" title="Background: Coalsack Nebula · ESO release 1539a · imaged with the Wide Field Imager on the MPG/ESO 2.2-metre telescope">
          BG · COALSACK NEBULA · ESO/WFI · CC BY 4.0
        </span>
        <span className="hidden lg:flex items-center gap-3">
          <KeyHint k="1-7" label="layers" />
          <KeyHint k="R"   label="reset" />
          <KeyHint k="M"   label="measure" />
          <KeyHint k="?"   label="help" />
        </span>
      </div>
    </footer>
  );
}
