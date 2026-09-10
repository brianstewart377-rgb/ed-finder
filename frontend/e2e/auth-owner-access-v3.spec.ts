import { expect, test, type Page } from '@playwright/test';

test.use({ serviceWorkers: 'block' });

type SessionBody = {
  authenticated: boolean;
  user: {
    account_id: string;
    commander_name: string | null;
    is_owner: boolean;
  } | null;
  owner_claim_available: boolean;
};

const ACCOUNT_ID = '4ff3ff94-5815-42f0-a89d-66cd87b79155';

async function mockSession(page: Page, session: SessionBody) {
  await page.route('https://fonts.googleapis.com/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/css', body: '' });
  });
  await page.route('**/api/v1/auth/session', async (route) => {
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
  await page.screenshot({ path: testInfo.outputPath('v3-signed-out-admin-gate.png'), fullPage: true });
});

test('denies Admin to an authenticated account without the owner role', async ({ page }) => {
  await mockSession(page, {
    authenticated: true,
    user: { account_id: ACCOUNT_ID, commander_name: null, is_owner: false },
    owner_claim_available: false,
  });

  await page.goto('/#admin');
  await expect(page.getByTestId('owner-access-denied')).toBeVisible();
  await expect(page.getByText('This Frontier account is signed in, but it is not linked')).toBeVisible();
});

test('opens owner controls for the assigned V3 account', async ({ page }, testInfo) => {
  await mockSession(page, {
    authenticated: true,
    user: { account_id: ACCOUNT_ID, commander_name: null, is_owner: true },
    owner_claim_available: false,
  });

  await page.goto('/#admin');
  await expect(page.getByTestId('frontier-account-name')).toContainText('Frontier account');
  await expect(page.getByTestId('owner-open-ops')).toBeVisible();
  await expect(page.getByTestId('admin-owner-session')).toBeVisible();
  await expect(page.getByTestId('owner-sign-in-required')).toHaveCount(0);
  await expect(page.getByTestId('owner-access-denied')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('v3-owner-admin.png'), fullPage: true });
});
