# Alfred status and staged roadmap

Last reviewed: 2026-08-27

> Implementation status is reconciled against code and passing tests. Unchecked service items remain
> in progress until that evidence exists.

Alfred is an original local household-manager-style assistant: discreet, concise, respectful, and
deliberately cautious. The product does not reproduce dialogue, catchphrases, biography, or
characterization from Batman-related works.

## Safety rule

**Every desktop mutation, launch, navigation, or clipboard write requires an exact preview and an
explicit approval before execution.** Approval is per action, per user, and per session. There is no
blanket approval, conversational shortcut, or autonomous execution mode.

Read-only inspection is labeled as such. It is bounded to non-sensitive summaries and configured
roots; it never returns environment dumps, arbitrary file contents, secrets, or process command
lines.

## Current-state checklist

### Implemented now

- [x] The root Flask site retains a deterministic `local_reply` helper for portfolio questions.
  It has no model or action path and remains separate from the local Alfred service.
- [x] Root Flask coding/HUD proposals remain disabled by default, session-owned, metadata-only,
  non-reading, and non-writing.
- [x] The Operations Platform retains its approval-pending Alfred intent boundary. Those intents
  never generate content or execute actions.
- [x] A separate typed FastAPI service runs natively on loopback, independently of the public Flask
  portfolio service deployed by the Render Blueprint.
- [x] Health, readiness, capabilities, sanitized configuration, provider status, index status,
  chat, inspection, action, and audit APIs are available.
- [x] Alfred can answer bounded portfolio questions from a curated allowlist of repository
  documents and returns repository-relative citations.
- [x] Indexed content is treated as untrusted reference text, not as instructions. No arbitrary
  path or file-reading request is accepted through chat.
- [x] A useful deterministic router and original composed voice work without a language model.
- [x] Ordinary safe questions outside portfolio keywords route to a configured reasoning provider;
  approval-bypass, destructive execution, credential-theft, and malware requests are refused before
  model or web use.
- [x] A typed reasoning-provider boundary supports opt-in local Ollama and an optional generic
  OpenAI-compatible endpoint. Structured history, prompts, context, responses, and timeouts are
  bounded; provider/model/status are visible; deterministic fallback is explicitly non-AI.
- [x] An explicit knowledge pipeline combines curated website evidence, optional reasoning, and
  safe web retrieval with provenance labels. Providers may cite only sources retrieved for that
  answer.
- [x] Keyless Wikipedia research works without an API key. Optional Brave Search broadens current
  web results only when separately configured; its absence is reported honestly.
- [x] Research results normalize title, HTTPS URL, source, excerpt, and retrieval time. Concise and
  deep research modes return numbered citations and disclose whether website, web, model, or
  deterministic knowledge was used.
- [x] Web fetches enforce an HTTPS destination policy, DNS/IP and redirect revalidation,
  nonstandard-port and credential denial, private/metadata destination denial, content-type and
  byte limits, strict timeouts, and result limits.
- [x] A versioned persona policy is isolated from user, website, and web content and applies to
  ordinary answers, research, uncertainty, refusals, errors, and action previews.
- [x] Read-only inspection covers sanitized OS/Python/service status, configured-root disk usage,
  metadata-only directory listings, and redacted process summaries.
- [x] Typed desktop proposals cover approved-root folder creation, single-file move/rename,
  bounded extension organization, allowlisted application launch, allowlisted HTTPS URL launch,
  and optional clipboard text.
- [x] Every desktop action follows `propose -> exact preview -> approve -> execute once -> audit`.
- [x] Approvals use unguessable identifiers, short expiry, canonical payload hashes, authenticated
  user/session ownership, revalidation, and single-use state transitions.
- [x] Paths are canonicalized and confined to configured roots. UNC/device paths, traversal,
  escaping links/reparse points, collisions, overwrites, deletes, and recursive actions are denied.
- [x] Desktop execution is disabled by default and configuration rejects public/non-loopback bind.
- [x] Action APIs require a high-entropy local token; tokens and sensitive request content are not
  placed in audit records.
- [x] SQLite schema initialization and retention cleanup are deterministic.
- [x] The accessible local console exposes real provider/index/health state, cited chat, typed task
  building, exact previews, approval confirmation, execution state, and immutable audit history.
- [x] Tests mock application/URL/clipboard launches and restrict filesystem mutation to temporary
  approved roots.
- [x] Alfred is the fourth Primary Work case study; all three existing flagships and all 20 legacy
  prototype folders remain present.
- [x] A separate public Flask showcase provides deterministic answers from a fixed evidence set,
  visible local citations, and three recruiter scenarios over synthetic data.
- [x] Public scenarios demonstrate `propose -> exact preview -> explicit approval -> simulated
  result -> session-local audit` without importing, proxying, or invoking the local Alfred service,
  model providers, research, inspection, repository readers, or desktop executors.
- [x] The public site applies a nonce-free same-origin CSP, framing denial, MIME sniffing denial,
  restrictive browser permissions, no-referrer policy, no-store API caching, and production HSTS.

### Partial

- [~] **Model-assisted conversation:** Ollama or a compatible endpoint can add bounded reasoning
  and broad safe conversation when deliberately configured, but Alfred is not a general autonomous agent and typed,
  deterministic validation remains the safety source of truth.
- [~] **Web research:** keyless reference lookup and optional broad search are available, but this
  is not an unrestricted browser, crawler, paywalled-content reader, or guarantee of freshness or
  factual completeness.
- [~] **Windows integration:** approved typed skills work natively, but there is no installer,
  signed binary, tray application, service registration, or startup persistence.
- [~] **Website knowledge:** the curated portfolio index covers selected first-party evidence. It
  does not crawl the repository, web, private files, or dynamically ingest arbitrary documents.
- [~] **Memory:** SQLite retains action/audit state for a configurable period. There is no personal
  semantic memory, profile inference, or cloud synchronization.
- [~] **Observability:** readiness, explicit errors, state transitions, and an audit timeline exist.
  Metrics export, tracing, alerting, and log shipping do not.

### Not started

- [ ] Wake-word detection, speech capture, speech recognition, and text-to-speech product UX.
- [ ] Email, calendar, messaging, smart-home, browser-extension, or ticketing integrations.
- [ ] General-purpose browser navigation, arbitrary URL fetching, or model-selected network tools.
- [ ] General application automation, screen reading, mouse/keyboard control, or arbitrary scripts.
- [ ] Background autonomous tasks, recurring jobs, unattended approvals, or self-modification.
- [ ] Cloud-hosted desktop control, remote access, multi-machine coordination, or account sync.
- [ ] Personal long-term memory, embeddings/vector database, or user-profile learning.
- [ ] Packaged/signed Windows installer, automatic update channel, or enterprise policy templates.

## Prioritized roadmap

### Stage 1 - Harden the safe local service

Completion criteria:

1. Threat-model review produces no unresolved high-confidence critical/high findings.
2. Windows reparse-point and path-swap tests run on a Windows CI runner in addition to portable
   symlink tests.
3. Authentication-token rotation, explicit session revocation, rate limits, and bounded concurrent
   action handling have documented tests.
4. SQLite backup/restore and retention behavior are exercised with a documented recovery drill.
5. A native-only operator guide explains firewall, loopback, token, allowlist, and filesystem
   permissions without enabling persistence.

### Stage 2 - Expand typed desktop skills

Completion criteria:

1. Each new skill has a typed schema, canonical preview, per-action approval, execution
   revalidation, immutable result, and denial tests.
2. Undo is added only where it can be transactional and collision-safe; delete remains absent.
3. Windows app identities and file-type rules are managed through a validated configuration UI,
   never chat-provided commands.
4. Failure recovery is deterministic and never reports success for a partial action.

### Stage 3 - Improve optional model use

Completion criteria:

1. Model output remains advisory and cannot create an executable payload outside a typed,
   revalidated proposal.
2. Provider health, model identity, latency, timeout, truncation, and fallback are visible.
3. Prompt-injection, tool-confusion, data-exfiltration, and misleading-status evaluations are
   repeatable and versioned.
4. Multiple local providers are considered only behind the same explicit configuration and honest
   availability contract.
5. Citation-faithfulness evaluations prove that generated citations are a subset of the sources
   retrieved for that answer.

### Stage 4 - Deepen website knowledge

Completion criteria:

1. A versioned manifest controls every indexed path, size, parser, and trust label.
2. Index freshness and source commit are visible, with deterministic rebuild tests.
3. Answers quote or summarize only retrieved evidence and always cite a safe repository-relative
   source.
4. Unsupported questions receive an uncertainty response rather than invented portfolio claims.

### Stage 5 - Add privacy-preserving memory

Completion criteria:

1. Memory is opt-in, local, inspectable, editable, exportable, and erasable.
2. Retention, encryption-at-rest expectations, field-level redaction, and backup behavior are
   documented before personal data is stored.
3. Action approval can never be inferred from memory.
4. Tests prove separation between users/sessions and complete deletion of expired records.

### Stage 6 - Explore voice

Completion criteria:

1. Push-to-talk ships before any wake word, with a visible capture indicator and local processing
   preference.
2. Transcripts are previewed and editable; a spoken request can propose but never approve an
   action.
3. Microphone permission, retention, offline behavior, errors, and accessibility are documented.
4. Text-only operation remains fully supported.

### Stage 7 - Add integrations selectively

Completion criteria:

1. Each integration is separately enabled, least-privilege, revocable, and excluded from logs.
2. External side effects use the same exact-preview and explicit-approval rule.
3. Read/write scopes, data flow, retention, failure behavior, and provider status are visible.
4. Email/calendar/message sending is not implemented until recipient/content/time previews and
   idempotency tests are complete.

### Stage 8 - Package and observe

Completion criteria:

1. A signed native Windows package has reproducible builds, explicit data locations, clean
   uninstall, and no surprise startup task.
2. Updates are signed, user-initiated by default, and rollback-safe.
3. Local metrics exclude prompts, tokens, paths, clipboard text, and other sensitive content.
4. Operational dashboards distinguish service health, provider availability, proposal state, and
   execution outcomes without implying autonomy.

## Threat model

| Threat | Current control |
|---|---|
| Remote access to desktop APIs | Loopback-only binding validation; separate from public Flask/Render services |
| Cross-site/browser action request | High-entropy bearer token plus user/session ownership; no token in URLs |
| Approval forgery or replay | Unguessable ID, payload hash, short expiry, explicit state machine, single use |
| Payload changed after preview | Canonical payload hash checked at approval and execution |
| Path traversal or root escape | Resolved-root confinement; UNC/device/traversal/escaping-link rejection |
| TOCTOU/path swap | Paths and allowlists revalidated immediately before execution; no overwrite |
| Arbitrary command execution | No shell/PowerShell endpoint; fixed typed actions and exact app allowlist only |
| Malicious indexed instructions | Curated fixed manifest; content treated as evidence, never executable instructions |
| SSRF through research | Fixed search APIs; HTTPS/DNS/IP/redirect/port/content limits; no arbitrary client/model URL fetch |
| Malicious web instructions | Retrieved text is delimited as untrusted evidence and cannot alter persona or action policy |
| Secret disclosure | No environment dumps, file content tools, process command lines, or token logging |
| Model hallucination/tool confusion | Provider status is explicit; model output cannot bypass typed proposal validation |
| Denial of service/storage growth | Request, response, listing, manifest, prompt, audit, and retention bounds |
| Public demo reaches local capabilities | Separate fixed-data module; no local-service imports, proxy, provider, filesystem, process, browser, clipboard, inspection, or research adapter |
| Public demo XSS or hostile URL input | DOM construction with `textContent`; fixed local citations/scenarios; no user HTML or URL fields; same-origin CSP |
| Cross-session public approval | Signed SameSite session state, unguessable proposal IDs, exact scenario preview, explicit JSON approval, bounded audit, reset |

Residual risks include a compromised local user account, malicious software already running with
the same OS privileges, filesystem races that cannot be eliminated without OS-level handles, and
misconfigured approved roots or application allowlists. Alfred is a convenience boundary, not a
malware sandbox or privilege-separation system.

## Non-goals

- General autonomous desktop control.
- Arbitrary shell, PowerShell, script, argument, SQL, or filesystem execution.
- Recursive deletion, secure deletion, overwrite-by-default, or privilege elevation.
- Remote/public action APIs or deployment of desktop skills in Render/Docker.
- Surveillance, employee monitoring, covert recording, or credential collection.
- A claim of human-level reasoning, complete portfolio knowledge, or guaranteed model accuracy.
- Replacement for endpoint security, backups, access control, or administrator review.
