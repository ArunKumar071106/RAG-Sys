// Shared by the Playwright specs: chatting needs a name and mobile number first (LOGIN_REQUIRED),
// so each test signs in a visitor through the real /api/users and starts with that sign-in remembered.
export async function signedIn(page, request, name = "Test Parent", phone = "9876543210") {
  const response = await request.post("/api/users", { data: { name, phone } });
  const user = await response.json();
  await page.addInitScript((saved) => {
    window.localStorage.setItem("arivazhai-user", JSON.stringify(saved));
  }, { name: user.name, token: user.token });
}

export const ADMIN_PASSWORD = "e2e-admin"; // scripts/e2e_backend.sh starts the API with it
