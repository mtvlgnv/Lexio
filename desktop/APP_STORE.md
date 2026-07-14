# Lexio — Mac App Store build & submission

The MAS build is the same codebase as Lexio Glance with a runtime flag
(`lib/mas.js`, `process.mas` or `LEXIO_MAS=1` in dev). Differences from the
DMG build:

| | DMG (Developer ID) | App Store (MAS) |
|---|---|---|
| Trigger | double-tap ⌃ (uiohook) + hotkey | **hotkey only** (⌘⇧L, Carbon — sandbox-legal) |
| Accessibility | required for double-tap | **not used, not requested** |
| Screen Recording | required (capture) | required — works sandboxed |
| Updates | electron-updater + GitHub | **App Store** (updater disabled) |
| Pro purchase | Stripe via lexio.site | **Apple In-App Purchase** (3.1.1) |
| Bundle id | site.lexio.glance | **site.lexio.app** |
| Product name | Lexio Glance | **Lexio** |

Dev simulation: `LEXIO_MAS=1 npm run start-overlay`.

## One-time setup (your Apple Developer account)

1. **Certificates** (developer.apple.com → Certificates):
   - *Apple Distribution* (signs the .app)
   - *Mac Installer Distribution* (signs the .pkg)
   Download both into Keychain. (Your existing *Developer ID Application*
   cert is for the DMG only — MAS needs these two.)
2. **Identifier**: register App ID `site.lexio.app` (no special capabilities;
   App Groups uses the implicit team prefix).
3. **Provisioning profile**: Profiles → new **Mac App Store Connect**
   distribution profile for `site.lexio.app` → download as
   `desktop/build/embedded.provisionprofile`. (Optionally a *Development*
   profile as `build/dev.provisionprofile` for `npm run dist:mas-dev`
   sandbox testing.)
4. **App Store Connect app record**: My Apps → **+** → macOS, name
   **Lexio — Instant Word Definitions**, bundle id `site.lexio.app`,
   SKU `lexio-mac-01`.
5. **IAP subscriptions** (app record → Monetization → Subscriptions):
   - Group "Lexio Pro" →
     - `site.lexio.pro.monthly` — auto-renewable, 1 month, $4.99 tier
     - `site.lexio.pro.yearly` — auto-renewable, 1 year, $39.99 tier
   Product ids must match `IAP_PRODUCTS` in `main-overlay.js` and
   `_PRODUCT_IDS` in `app/routers/apple_billing.py`.
6. **Shared secret**: app record → App Information → App-Specific Shared
   Secret → generate, then on the server add `APPLE_SHARED_SECRET=...` to
   `/var/www/lexio/.env` and restart lexio.
7. **Nginx**: the deployed nginx allowlist must include the `apple` prefix
   (this repo's nginx.conf already does — mirror it on the server + reload).
8. **Sandbox tester** (App Store Connect → Users → Sandbox Testers): a test
   Apple ID for purchasing in the mas-dev build without real money.

## Build & upload

```bash
cd desktop
npm run dist:mas          # → dist/Lexio-1.x.x.pkg (signed, sandboxed)
xcrun altool --validate-app -f dist/*.pkg -t macos ...   # or just use Transporter
```
Upload the .pkg with the **Transporter** app (sign in with your Apple ID).
Then in App Store Connect select the build, fill the listing, and submit.

Local sandbox check before uploading:
`npm run dist:mas-dev`, install, verify: launches, hotkey lookup works,
Screen Recording prompt appears, IAP sheet appears with the sandbox tester.

## Listing copy (ready to paste)

- **Name**: Lexio — Instant Word Definitions
- **Subtitle**: Point at any word. Understand it.
- **Category**: Education (secondary: Reference)
- **Keywords**: dictionary,definition,vocabulary,reading,language,learn
  english,lookup,translate,words,study
- **Description**:
  > Point your cursor at any word — in any app — and press one hotkey.
  > Lexio reads the sentence around it and explains what the word means
  > *right there*, the way the author used it. Not a generic dictionary
  > entry — a contextual definition.
  >
  > • Works everywhere: articles, PDFs, subtitles, email, code reviews
  > • Contextual definitions with IPA pronunciation and etymology
  > • 11 interface languages; definitions explained in your language
  > • Word bank: save words, sync across devices, export to Anki
  > • Reader profile: tell Lexio what you do and definitions land in your world
  >
  > Free to try. Lexio Pro (optional subscription) unlocks unlimited
  > lookups and all three reading modes.
- **Privacy nutrition label**: Data linked to you: email (account),
  purchase history (subscription status). Data not linked: usage data
  (anonymized analytics, opt-out in Settings). No tracking across apps.
- **Review notes**: "Lexio captures the screen region near the cursor when
  the user presses the lookup hotkey, to identify and define the word being
  pointed at (Screen Recording permission, requested in onboarding). No
  captures happen without an explicit hotkey press. A demo account is
  available: [create one and paste credentials here]."

## Compliance guardrails already enforced in code

- No Stripe/website purchase links anywhere in the MAS build: the Hub's
  Upgrade button opens the native IAP card, the panel's quota errors point
  at the Hub (`compact.html` `mas=1` flag), `app:open-pricing` is a no-op
  redirect to the Hub.
- Sign-in with an existing lexio.site account is allowed (multiplatform
  services, 3.1.3(b)); Pro bought on the website unlocks in the app.
- Encryption: `ITSAppUsesNonExemptEncryption=false` (HTTPS only).

## Server-side receipt flow

App launch and every purchase POST the app receipt to
`POST /apple/verify-receipt` (Bearer auth). The backend validates with
Apple (prod → sandbox on 21007), grants `is_pro` until the subscription
expiry, and revokes Apple-sourced Pro when expired — never touching
Stripe/family Pro. Tests: `tests/test_apple_billing.py`.
