# GoHome Native iOS App Redesign

Status: approved design baseline  
Date: 2026-07-21  
Target: TestFlight-installable iOS application  
Minimum OS: iOS 16

## 1. Decision

The competition deliverable will be a native SwiftUI application, not a remote
HTML application wrapped in `WKWebView`.

The existing cloud API, PostgreSQL data, device synchronization, event evidence,
and video endpoints remain reusable. The existing household-user HTML application
is a migration-time comparison surface only and is retired from public product
delivery after native parity is accepted. Final web surfaces are limited to the
edge installation/admin console, cloud operations console, privacy terms, and help.
None of these web surfaces is the runtime UI of the iOS user application.

The edge-device visual algorithms are explicitly outside this branch. The iOS
application consumes their existing camera, event, verification, and stream
contracts without changing edge inference behavior.

## 2. Product Goal

Build an iOS product that:

- launches and switches tabs without full-page loading states;
- shows only persisted account and family data owned by the signed-in user;
- presents real weather, calendar, distance, editorial content, camera, and event data;
- closes the return-home reminder workflow from push to contact action;
- provides curated non-medical products for older adults without pretending to be a store;
- can be signed, archived, and distributed through TestFlight.

## 3. Non-Goals

- Rewriting the edge vision pipeline or changing detection thresholds.
- Building checkout, orders, payment, inventory, logistics, or refunds.
- Recommending medicines, supplements, medical devices, or products with medical claims.
- Automatically sending a private WeChat message or selecting a WeChat recipient.
- Migrating the cloud operations, edge administration, legal, or help pages to SwiftUI.
- Replacing working cloud video transport during the initial native migration.

## 4. Current Problems Being Removed

The current user application consists of separate HTML documents. Each document
reconnects to the API and renders temporary reading or synchronization states.
Whole-page HTML snapshots in `localStorage` and stale-while-revalidate HTML in the
Service Worker can race, causing stale content, flashes, and state resets.

The current home page also discards useful fields returned by content search. It
replaces real titles, summaries, images, and links with generic copy. Several cards
therefore look actionable but have no meaningful action.

Return-home reminders are currently derived as display copy rather than persisted
messages with actions and outcomes. WeChat handling only opens `weixin://` and does
not prepare shareable content.

The PostgreSQL adapter currently treats an in-memory object graph as authoritative
and deletes and reinserts complete tables on each save. This is unsuitable for
concurrent accounts and must not be the final data path.

## 5. Native Architecture

### 5.1 Application structure

The native target uses SwiftUI and Swift 5.10 with these boundaries:

- `AppSessionCoordinator`: decides signed-out, onboarding, and main-app state.
- `APIClient` actor: typed requests, authentication headers, decoding, retry policy,
  and request cancellation.
- `AuthStore`: stores the session token in Keychain and exposes no token to views.
- `AppRepository` actor: account-scoped server data and synchronization policy.
- `AppModel` on the main actor: publishes view-ready state to SwiftUI.
- Feature modules: `Auth`, `Onboarding`, `Home`, `Guard`, `Events`, `Discover`, and
  `Profile`.
- Shared components: image loading, empty/error states, share sheet, phone action,
  map, badges, and bottom navigation.

Views do not call endpoints directly. They issue intents to feature models, which
use the repository. This prevents each tab from independently repeating session,
family, and device bootstrap calls.

### 5.2 Local state

iOS 16 does not provide SwiftData. The first release uses:

- Keychain for authentication secrets;
- an actor-protected, Codable disk cache for account-scoped view data;
- `URLCache` plus an account-scoped image cache for media;
- `UserDefaults` only for non-sensitive UI preferences.

Cache keys include the authenticated user ID and family ID. Logout and account
switching clear the active in-memory state and detach the previous account cache.

### 5.3 Refresh behavior

The application renders the last successful state immediately, then revalidates in
the background. A successful refresh updates only changed modules. A failed refresh
keeps the last successful state and places a small contextual indicator inside the
affected module.

No primary tab is allowed to replace its complete content with a spinner, reading
screen, synchronization screen, or launch screen after it has rendered once.

## 6. Authentication And Onboarding

The signed-out flow uses phone-number authentication.

1. Request SMS verification code.
2. Verify the code and create or restore the account session.
3. For a new account, create or join a family.
4. Add the cared-for family member profile and contact numbers.
5. Bind the household box.
6. Add and verify at least one camera.
7. Enter the main application.

The production server rejects the fixed `000000` code. A demo code may exist only
behind an explicit non-production server configuration and must be visibly marked
in internal builds.

The server, not the client, enforces family membership and creator permissions.
Only the family creator can change device algorithms and core guard rules. A new
phone account never inherits another account's family, device, camera, message, or
event data.

## 7. Main Navigation

The five native tabs are:

1. Home
2. Guard
3. Events
4. Discover
5. Profile

Each tab owns an independent `NavigationStack` so returning to a tab preserves its
scroll position and navigation state. Switching tabs does not rebuild repositories
or restart camera discovery.

## 8. Home

Home is an editorial and planning surface, not a device-status dashboard.

### 8.1 Header

- current date;
- real weather for the configured family location;
- notification button with unread count;
- a compact critical-event strip only when a real event needs attention.

### 8.2 Calendar module

- seven-day strip;
- next meaningful family date or plan;
- tap opens the native calendar detail;
- no explanatory marketing copy.

### 8.3 Distance module

- MapKit map with current phone location and configured household location;
- distance and estimated travel time;
- clear permission-denied and location-not-configured states;
- return-home reminder settings are accessible from the module but are not rendered
  as a fake distance when location permission is absent.

### 8.4 Editorial feed

- two-column masonry layout implemented as an iOS 16 custom `Layout`;
- real image, category, title, concise summary, source, and publication date;
- filter chips for all, local, health lifestyle, culture, and selected interests;
- tap opens the original HTTPS source in an in-app Safari view;
- cards without a valid source URL are not shown;
- failed images use a restrained category treatment, not an empty grey rectangle.

Safety incidents and anti-fraud alerts do not masquerade as editorial articles.
Safety incidents belong to Events. Optional anti-fraud education may be editorial
content only when it has a valid official source and is not tied to a household
incident.

## 9. Guard

Guard prioritizes one stable, selected live stream.

- selected camera stream fills the primary 16:9 stage;
- camera selector changes the selected stream without rebuilding the screen;
- non-selected cameras show recent thumbnails and do not play simultaneous streams;
- room, online state, and last update appear as compact overlays;
- native controls cover camera selection, fullscreen, retry, and settings;
- camera errors are handled in place and do not navigate to unrelated tabs;
- pending safety events appear below the stream only when they exist.

The initial release consumes the current cloud stream API. The native stream layer
isolates MJPEG parsing and lifecycle management so a later HLS or WebRTC transport
can replace it without changing Guard views.

## 10. Events

Events contains only real safety events that may require family action.

- segmented states: pending, handled, and false positive;
- chronological evidence list with screenshot, room, time, event type, cloud review,
  and action state;
- detail shows the evidence timeline and human-readable verification outcome;
- internal threshold names, raw metrics, and serialized algorithm objects are not
  shown to users;
- actions: confirm safe, mark false positive, call, and share contact message;
- optimistic action state is reconciled with the server and can recover after a
  failed request.

## 11. Discover

Discover replaces the overlapping Companion tab. It is a curated recommendation
surface, not a store.

### 11.1 Scope

Allowed first-release categories include:

- non-slip and household safety;
- lighting and visibility;
- daily living and storage assistance;
- communication and simple electronics;
- non-medical travel and mobility accessories.

Medicines, supplements, medical devices, diagnostic products, and products making
medical claims are excluded.

### 11.2 Product contract

Every recommendation must contain:

- verified product and brand name;
- category and suitability labels;
- real image with a recorded source;
- concise reason based on user-selected needs;
- merchant or official-brand source;
- valid HTTPS purchase or information link;
- last verification time;
- sponsorship or affiliate disclosure when applicable.

The application does not infer a sales recommendation from camera events. It does
not use fear, diagnoses, falls, or household incidents as sales copy.

The detail screen explains suitability and limitations, then opens the external
merchant or brand page. There is no cart, checkout, payment, order history, or fake
purchase success state.

## 12. Profile

Profile contains:

- account and logout;
- family members and roles;
- cared-for family member profile and phone numbers;
- household box and cameras;
- notification permissions and quiet hours;
- return-home and content preferences;
- product recommendation interests;
- privacy, data export, and deletion.

The word "administrator" is not used as a personal identity label. Roles appear
only inside family-member management as creator or member.

## 13. Return-Home Message Workflow

Return-home is a message and notification workflow, not a decorative home card.

### 13.1 Triggers

Supported triggers are:

- configured days since the last visit;
- upcoming weekend, holiday, anniversary, or family calendar event;
- a manual reminder created by the user.

Triggers respect quiet hours, reminder frequency, idempotency, and user settings.
Normal safety events do not generate a commercial or casual return-home message.

### 13.2 Generated content

The persisted message includes:

- trigger reason;
- suggested time or date;
- two or three natural conversation topics;
- two editable message variants;
- the context used, such as real weather, calendar, selected interests, and verified
  local content;
- available actions and current action state.

Generated text must not claim that the user is physically present. It must not tell
the user to hand over tea, water, medicine, or another physical object while away.

### 13.3 User flow

1. Scheduler creates an idempotent `return_home` app message.
2. The server records an in-app delivery and queues APNs when configured.
3. Notification tap deep-links to the native message detail.
4. The user edits or selects a reference message.
5. The native share sheet presents available targets, including WeChat when installed.
6. The user records contacted, remind later, dismissed, or returned home.
7. The server stores the action and schedules or closes the reminder.

iOS cannot guarantee that a private WeChat message was sent or select a recipient.
The product records the user's explicit follow-up action, not a fabricated send receipt.

## 14. Cloud API And Persistence

### 14.1 API aggregation

Add a versioned native bootstrap endpoint that returns the signed-in user, primary
family, onboarding state, permissions, unread count, and stable revision identifiers.
Feature endpoints remain independently refreshable.

Required native-facing contracts include:

- `GET /api/v2/app/bootstrap`
- `GET /api/v2/home`
- `GET /api/v2/messages`
- `GET /api/v2/messages/:id`
- `POST /api/v2/messages/:id/actions`
- `GET /api/v2/products`
- `GET /api/v2/products/:id`
- `GET /api/v2/product-preferences`
- `PUT /api/v2/product-preferences`

Existing camera, stream, event, profile, family, device, and notification endpoints
may be adapted behind typed native repositories. Compatibility must be preserved for
the edge agent, operational consoles, and migration-time browser verification until
native parity is accepted.

### 14.2 Database behavior

Replace full-table delete-and-reinsert persistence with entity-level SQL repositories
and transactions. Mutations use server-side authorization, database constraints,
idempotency keys where appropriate, and audit timestamps.

Add persisted message action records and curated product catalog records. Product
catalog changes are server-managed so product recommendations can be updated without
releasing a new App binary.

Passwords or SMS codes are never stored in plaintext. Session tokens are stored only
as hashes on the server and expire or revoke independently.

## 15. Push And Native Integrations

- APNs registration is native and associated with user, family, installation, and
  environment.
- Push payloads contain typed deep-link data, not arbitrary external URLs.
- Notification permissions are requested in context after onboarding.
- Native share sheet handles reference-message sharing.
- `tel:` handling validates the configured number and displays a confirmation.
- external product and article links use HTTPS and an allowlisted in-app Safari view.

APNs delivery requires the Apple Developer team, App Store Connect application,
Bundle ID, push entitlement, and APNs Auth Key. The application must still provide
complete in-app messages when APNs is not configured.

## 16. Visual System

Design read: a native family-care utility for younger family members, combining a
clean editorial feed with quiet operational surfaces.

Design dials:

- design variance: 6;
- motion intensity: 4;
- visual density: 7.

Rules:

- white primary surface, true near-black text, and one ginger-yellow accent;
- no gradients, decorative blobs, glass-card stacks, or oversized display copy;
- cards use a maximum 8-point radius;
- borders are used only for separation, not around every section;
- typography uses the system San Francisco family with Dynamic Type support;
- familiar SF Symbols are used for actions;
- all screens respect the safe area and home indicator;
- motion is 150-220ms and never blocks interaction;
- skeletons match module geometry and are used only when no cached state exists;
- empty states contain one relevant action and no feature-description copy.

## 17. Failure And Offline States

- Invalid session: clear Keychain credentials and return to native login.
- Network timeout: keep cached data and mark the affected module stale.
- No cache on first launch: show module-shaped skeletons, not an app-wide spinner.
- Image failure: show a category fallback and retain the real title and source.
- Stream failure: keep the Guard layout stable and offer retry or camera selection.
- Location denied: show configuration state without invented distance.
- WeChat unavailable: keep copy and system sharing available.
- APNs unavailable: retain the in-app inbox and expose notification setup status.
- Product link expired: hide the action, record the catalog item for re-verification,
  and never route to an unrelated page.

## 18. Acceptance Criteria

### 18.1 Experience

- Warm launch renders the cached primary screen without a network loading page.
- Tab selection changes visible content in under 100ms on the target device.
- Returning to a tab preserves scroll and navigation state.
- Background refresh never clears already visible content.
- No primary action is a `#` link, placeholder toast, or unrelated page jump.

### 18.2 Data

- Two registered phone accounts cannot read each other's family data.
- A new account starts with no family, device, camera, event, or message ownership.
- Server restart preserves sessions and data without full-table replacement.
- Logout and account switching do not display the previous account's cached content.

### 18.3 Workflows

- New-user onboarding can reach a bound device and configured camera without browser pages.
- A return-home trigger creates one persisted message and one idempotent delivery per target.
- Notification deep-link opens the correct native detail.
- A reference message can be edited, shared, and marked with a persisted outcome.
- Every visible editorial and product card has a real source and a functioning action.
- Guard shows one selected live stream and can switch cameras without recreating the tab.
- Event actions update the server and survive relaunch.

### 18.4 Distribution

- Debug and Release builds compile without the remote web UI as a runtime dependency.
- Release has no fixed verification code or development credentials.
- Archive passes signing, entitlement, privacy-manifest, and TestFlight upload checks.

## 19. Delivery Sequence

1. Stabilize cloud identity and entity-level PostgreSQL persistence.
2. Create native app foundation, authentication, cache, and onboarding.
3. Build native tab shell and Home.
4. Build Guard stream lifecycle and camera switching.
5. Build Events and event actions.
6. Build return-home messages, native sharing, and notification deep links.
7. Build Discover with curated real-product catalog.
8. Build Profile and permission/settings flows.
9. Complete APNs configuration, device QA, accessibility checks, and TestFlight archive.

Each phase must preserve edge-agent and operational-console API compatibility. The
household-user web screens remain available only during migration and are removed
from public navigation after native parity. The TestFlight release is not accepted
until all five primary tabs and onboarding are native.
