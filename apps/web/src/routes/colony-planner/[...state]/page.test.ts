import { describe, expect, it } from 'vitest';
import { load } from './+page';

function run(state: string, search = '') {
  return load({
    params: { state },
    url: new URL(`http://localhost/colony-planner/${state}${search}`),
  } as Parameters<typeof load>[0]);
}

function captureThrown(runRoute: () => unknown): {
  status?: number;
  location?: string;
  body?: { message?: string };
} {
  try {
    runRoute();
  } catch (thrown) {
    return thrown as {
      status?: number;
      location?: string;
      body?: { message?: string };
    };
  }
  throw new Error('Expected the planner route loader to throw');
}

describe('Colony Planner route loader', () => {
  it('parses the canonical system, project, and mode grammar losslessly', () => {
    expect(
      run('system/18446744073709551615/project/project%20one/mode/preview'),
    ).toEqual({
      system: '18446744073709551615',
      project: 'project one',
      mode: 'preview',
    });
  });

  it('redirects a legacy detail segment to the canonical overlay query', () => {
    const thrown = captureThrown(() =>
      run(
        'system/18446744073709551615/project/project%20one/mode/preview/detail/9007199254740993',
        '?view=compact&system=42',
      ),
    );

    expect(thrown).toMatchObject({
      status: 307,
      location:
        '/colony-planner/system/18446744073709551615/project/project%20one/mode/preview?view=compact&system=9007199254740993',
    });
  });

  it.each([
    ['out-of-range system', 'system/18446744073709551616'],
    ['missing mode', 'system/42/mode'],
    ['unknown mode with trailing data', 'system/42/mode/not-a-mode/extra'],
    ['missing project identifier', 'system/42/project'],
    ['invalid detail id', 'system/42/detail/not-an-id'],
    ['trailing detail data', 'system/42/detail/99/extra'],
  ])('rejects %s', (_label, state) => {
    expect(captureThrown(() => run(state))).toMatchObject({ status: 404 });
  });

  it('rejects an unknown planner mode explicitly', () => {
    expect(captureThrown(() => run('system/42/mode/not-a-mode'))).toMatchObject(
      {
        status: 404,
        body: { message: 'Invalid planner mode' },
      },
    );
  });
});
