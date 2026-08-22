import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

type SessionBody = {
  authenticated: boolean;
  user: { commander_name: string | null; is_owner: boolean } | null;
  owner_claim_available: boolean;
};

async function mockSession(page: Page, session: SessionBody) {
  // The sandbox blocks remote fonts. Fulfil the stylesheet locally so the
  // production CSS preload can complete and the application can mount.
  await page.route('https://fonts.googleapis.com/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/css', body: '' });
  });
  await page.route('**/api/auth/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(session),
    });
  });
}

test('asks a signed-out visitor to use Frontier before opening Admin', async ({ page }, testInfo) => {
  await mockSession(page, {
    authenticated: false,
    user: null,
    owner_claim_available: false,
  });

  await page.goto('/#admin');

  await expect(page.getByTestId('owner-sign-in-required')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in with Frontier' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('signed-out-admin-gate.png'), fullPage: true });
});

test('denies Admin to an authenticated non-owner commander', async ({ page }) => {
  await mockSession(page, {
    authenticated: true,
    user: { commander_name: 'Visiting Cmdr', is_owner: false },
    owner_claim_available: false,
  });

  await page.goto('/#admin');

  await expect(page.getByTestId('owner-access-denied')).toBeVisible();
  await expect(page.getByText('This Frontier account is signed in, but it is not linked')).toBeVisible();
});

test('opens owner controls for the linked Frontier commander', async ({ page }, testInfo) => {
  await mockSession(page, {
    authenticated: true,
    user: { commander_name: 'Owner Cmdr', is_owner: true },
    owner_claim_available: false,
  });

  await page.goto('/#admin');

  await expect(page.getByTestId('frontier-account-name')).toContainText('CMDR Owner Cmdr');
  await expect(page.getByTestId('owner-open-ops')).toBeVisible();
  await expect(page.getByTestId('owner-sign-in-required')).toHaveCount(0);
  await expect(page.getByTestId('owner-access-denied')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('owner-admin.png'), fullPage: true });
});
