# ContextBase Restricted Sharing — Design Doc

```text
Metadata
Project: contextbase
Page Type: Research Note
Status: Draft
Owner: Le Xu
Last Updated: 2026-06-29
Summary: Make ContextBase (self-hosted Outline) default-deny by realm. Short-term: configure existing Outline features. Long-term: enforce private-by-default + a thin "realm" layer on top of Outline's group ACLs.
Tags: access-control, outline, security, sharing, posix-acl
Related Links: code @ /Users/lexu/Project/contextbase (Outline fork); upstream https://github.com/outline/outline
```

## 1. Problem

ContextBase is a self-hosted [Outline](https://github.com/outline/outline) instance used as the ED-AISYS research group knowledge base. One collection per project. Two access problems make it leak context across project boundaries:

1. **Internal over-exposure.** Pages are visible to *every member of the group* by default. When a project member uploads a page, everyone in the workspace can read it. There is no per-project access boundary — the whole group is one flat audience.
2. **Public web sharing is easy and on by default.** The Share button on a collection/document exposes a "Publish to web" toggle that makes content reachable by *anyone with the link*, no login. Any member can do this; nothing org-level prevents it.

### What we want

Default-deny access scoped by **realm**, analogous to OS access groups:

- A page is only accessible to members of its realm (e.g., a project's members), **not** the whole group, from the moment it is created.
- A realm = a named set of people. Realms compose: a collection may be exposed to **multiple** realms at once (union access), without inventing a merged group.
- **Personal collections** — data only the owner can see — are a first-class case.
- Public web sharing is restricted (off by default, gated by policy).

### Granularity decision

The access boundary lives at the **collection** level (one collection ≈ one project ≈ one realm). Documents inherit their collection's access. This was chosen over per-document or cross-cutting tag granularity because "project member" needs are satisfied by collection-level grants, and finer models add complexity Outline's data model does not need. (Revisit only if a concrete per-subtree case appears.)

## 2. Mental model: POSIX ACL → ContextBase/Outline

We reason about the target using POSIX file ACLs, because Outline's existing model is already an ACL system and maps onto it almost one-to-one.

POSIX has two layers. **Traditional Unix** permissions give a file exactly one owner and one owning group (owner/group/other triads); sharing with two groups forces you to create a merged group. **POSIX ACLs** (`setfacl`/`getfacl`) extend this with a list of *named user* and *named group* entries, each with its own `rwx`; effective access is the **union** of matching entries, and a directory's **default ACL** is inherited by new files. We want the ACL model, not the traditional one.

### Mapping table

| POSIX ACL entry | Meaning | ContextBase / Outline realization | Code |
| --- | --- | --- | --- |
| `user::rw-` (owner) | file owner | Collection/document **creator** (owner role) | `policies/utils.ts` `isOwner` |
| `user:alice:rw-` | named user | Per-user grant `UserMembership{userId, collectionId, permission}` | `models/UserMembership.ts:76-108` |
| `group:proj-a:r--` | named group | Per-group grant `GroupMembership{groupId, collectionId, permission}` | `models/GroupMembership.ts:60-112` |
| `group:proj-b:r--` (2nd group) | another named group | A second `GroupMembership` on the same collection → **union** | `policies/collection.ts:210-243` |
| `other::---` | everyone else | **Default-deny** for non-members | `policies/cancan.ts:82-120` |
| default ACL on a directory | inherited by new files | Collection grants auto-propagated to child documents via `sourceId` | `models/UserMembership.ts:323-390` |
| `chgrp` / `setfacl` (promote) | widen/narrow after creation | `collections.add_group` / `add_user` / permission update | routes `collections.*` |

### Permission levels

Outline's `CollectionPermission` enum is `Read = "read"`, `ReadWrite = "read_write"`, `Admin = "admin"` (`shared/types.ts`). These are the `rwx`-equivalent levels on each ACL entry. Effective permission for a user = the **highest** level among all matching owner/user/group entries; no match = deny.

### Resolution semantics (already implemented)

`includesMembership()` (`policies/collection.ts:210-243`, `policies/document.ts:275-308`) collects all matching **user** and **group** memberships and returns the set — this is the union evaluator. Documents fall back to their collection via `can(actor, "readDocument", document.collection)` (`policies/document.ts:31`). The cancan framework is **default-deny**: an action is allowed only if some registered rule's condition matches (`policies/cancan.ts:82-120`). Every policy is team-scoped via `isTeamModel` (`policies/utils.ts`).

### Worked example

Collection **"Hybrid Serve"** carries:

```text
owner:  lexu            (rw, manages grants)
group:  hybrid-members  (read_write)
group:  reviewers       (read)        # second realm, union
user:   yeqi            (read)        # one-off named user
other:  (deny)
```

Effective access = `owner ∪ (any granted group the user belongs to) ∪ (named-user grant)`, highest level wins, else deny. A new document created inside inherits this whole set automatically. A **personal collection** is the degenerate case — only `owner: lexu (rw)`, no group entries.

## 3. The gap

The target model is *already what Outline implements* at collection granularity. The data model needs **no change**. The gaps are defaults, enforcement, and UX:

| # | Gap | Detail | Evidence |
| --- | --- | --- | --- |
| G1 | Collections grant the whole workspace | ContextBase collections carry a team-wide grant (`collection.permission = read`/`read_write`, the "All members" row), so every member reads everything. The *code* default is private (`permission: null`), but our instance's collections were created/imported with a team-wide grant. | `models/Collection.ts:258-260,754`; `components/Sharing/Collection/AccessControlList.tsx` "All members" |
| G2 | Public web sharing on by default | `team.sharing` defaults `true`; each collection's `sharing` defaults `true` (`collection?.sharing ?? true`). Any member can "Publish to web". | `models/Team.ts:185`; `components/Collection/CollectionForm.tsx:113`; `components/Sharing/Collection/PublicAccess.tsx` |
| G3 | No enforcement of default-deny | Nothing prevents a member from re-adding "All members" or flipping a collection public. Private-by-default is a UI default, not an invariant. | `routes/api/collections/schema.ts:37-40` (permission is free-form nullish) |
| G4 | No "realm" concept in the product | Groups exist but are generic. There is no convention binding a project collection to a backing group, nor UI language of "realm". | n/a (convention gap) |
| G5 | Request-access flow is dormant | `AccessRequest` model exists (status Pending/Approved/Dismissed) but has **no route and no UI** — non-members cannot ask into a realm. | `models/AccessRequest.ts` (model only) |

**Conclusion:** This is primarily a configuration + thin-enforcement problem, **not** an access-control system to build from scratch. That shapes the staged plan: fix defaults first (no code), then make default-deny an enforced invariant with a realm layer.

## 4. Fixing approaches

### Approach 1 — Configure existing features (short term)

Operational change only; no code; fully upstream-compatible and reversible.

- **Disable public sharing org-wide**: set `team.sharing = false` in Security settings (kill-switch for all "Publish to web"). Re-enable per collection only when deliberately needed.
- **Make collections private**: sweep existing collections to `permission: null` (removes the "All members" grant). Verified by `collection.isPrivate === true`.
- **Model realms as Groups**: create one Outline **Group** per project (the realm); add project members; grant the group `read_write` (or `read`) on its collection via `collections.add_group`. Two realms on one collection = two group grants (union).
- **Personal collections**: create a private collection and add no group — owner-only by construction.

*Limits:* relies on admin discipline. Nothing prevents a member from re-widening a collection or flipping it public; no realm UX; no audit; no request-access path. Addresses G1, G2 operationally; leaves G3–G5.

### Approach 2 — Enforced defaults + realm layer (long term, recommended)

Approach 1 made durable by thin code in our fork, plus a one-time migration. Reuses Outline's union + inheritance engine; adds enforcement and product surface.

- **Enforce private-by-default** (G1, G3): add a team setting `defaultCollectionPrivate` (default `true`). On `collections.create`, coerce `permission → null` unless an admin explicitly opts the collection into a workspace-wide grant. Makes default-deny an invariant, not a UI default.
- **Lock down public sharing** (G2, G3): default `team.sharing = false` for this deployment; optionally require admin role (not member) to enable per-collection `sharing`. Surface a clear "restricted" lock indicator.
- **Realm convention** (G4): when a project collection is created, auto-provision a backing **Group** ("realm") and grant it on the collection; manage realm membership = collection access. Relabel the People/Access panel to speak in "realm" terms. Keeps multi-group union and personal-collection cases intact.
- **Request-access flow** (G5): wire the dormant `AccessRequest` model to a route + a "Request access" button shown when a user hits a realm they cannot see; realm owner/admin approves (creates a `UserMembership`).
- **Migration**: set existing collections to `permission: null`; create realm groups from current memberships; report any collection that loses access so owners can re-grant.

*Costs:* divergence from upstream (rebase maintenance), a data migration, and test coverage for the enforced defaults.

### Approach 3 — Cross-cutting realm/tag subsystem (research track)

A POSIX-style "named group anywhere" model: realm **labels** attached to any document/collection independent of the collection tree, with a label-aware resolver replacing collection-rooted access. Maximal flexibility, closest to OS ACLs and information-flow control, **but** it does not fit Outline's architecture cleanly and is a research effort rather than a feature. Treated as a separate, non-urgent track — see **§8** for the full expansion. Not on the staged roadmap (§5).

## 5. Staged roadmap — what each stage achieves

| Stage | Goal | Scope | Done when | Closes |
| --- | --- | --- | --- | --- |
| **0 — Audit** | Know current exposure | Inventory every collection's `permission` and `sharing`; list which are workspace-wide or web-published; identify project↔member mapping | A table of all collections with current access state | — |
| **1 — Configure (Approach 1)** | Stop the bleeding, no code | `team.sharing = false`; set leaking collections to `permission: null`; create one Group per active project + grant on its collection; convert intended-personal collections to owner-only | No collection grants "All members" unless deliberate; no live public shares except approved ones; each active project has a realm group | G1, G2 (operationally) |
| **2 — Enforce defaults** | Default-deny becomes an invariant | `defaultCollectionPrivate` team setting + server-side coercion on `collections.create`; default `team.sharing=false`; restricted lock indicator in UI; tests | A new collection is private without any user action; a member cannot silently create a workspace-wide or public collection | G3 (+ hardens G1, G2) |
| **3 — Realm layer** | Realm is a product concept | Auto-provision backing group per project collection; "realm" language in the access panel; admin view of realms↔collections; migration of existing collections → realm groups | Creating a project collection creates its realm; access is managed as realm membership; existing collections migrated | G4 |
| **4 — Request access** | Non-members can ask in | Wire `AccessRequest` to a route + UI; "Request access" button; owner/admin approve → `UserMembership` | A user hitting a realm they lack can request and be granted without admin spelunking | G5 |
| **5 — Govern (optional)** | Visibility & audit | Audit log of grant changes and publishes; periodic report of workspace-wide / publicly-shared collections | Admins get a recurring exposure report | hardening |

**Sequencing logic:** Stage 1 is pure configuration and can ship immediately (days). Stages 2–4 are the long-term fork work, each independently shippable; default-deny enforcement (Stage 2) is the highest-value code change and should precede the realm UX. Stage 5 is optional governance. Approach 3 is explicitly out of scope unless a cross-cutting realm need emerges.

## 6. Open questions

- **Default permission level for a realm group** — `read_write` for all members, or `read` with a smaller `read_write` editor set?
- **Who may create realms / collections** — keep `team.memberCollectionCreate`, or restrict to admins so every realm is provisioned deliberately?
- **Personal collection UX** — explicit "Personal / only me" button at creation, or implicit (private + no group)?
- **Existing public shares** — revoke all on Stage 1 and re-grant on request, or grandfather current ones?
- **Upstream strategy** — carry Stage 2–4 as a maintained fork, or attempt to upstream the `defaultCollectionPrivate` setting to reduce rebase burden?

## 7. References (Outline source)

Paths relative to `/Users/lexu/Project/contextbase`.

- Collection model & `isPrivate`: `server/models/Collection.ts:258-260,754`
- Collection policy (resolution): `server/policies/collection.ts:34-47,98-115,210-243`
- Document policy (inheritance): `server/policies/document.ts:21-33,86-102,275-308`
- Membership models: `server/models/UserMembership.ts:76-108,323-390`; `server/models/GroupMembership.ts:60-112,327-393`
- Authorization framework: `server/policies/cancan.ts:36-71,82-120,182-191`; `server/policies/utils.ts`
- Share model & gating: `server/models/Share.ts:109-261`; `server/commands/shareLoader.ts:84-89`; `server/routes/api/shares/shares.ts:251-335`
- Team kill-switches: `server/models/Team.ts:185-187,204-206`
- Access request (dormant): `server/models/AccessRequest.ts`
- Frontend: `app/components/Collection/CollectionForm.tsx`; `app/components/Sharing/Collection/{SharePopover,PublicAccess,AccessControlList}.tsx`; `app/scenes/Settings/Security.tsx`
- Create schema/route: `server/routes/api/collections/schema.ts:37-40`; `server/routes/api/collections/collections.ts:76-90`
- Access-scoping lynchpin: `server/models/User.ts:490` (`collectionIds()`); backlink scoping `server/routes/api/documents/documents.ts:165,612-626`; export `server/commands/collectionExporter.ts`

---

## 8. Approach 3 expanded — cross-cutting realm subsystem (research track)

**Status: research direction, not urgent, not on the §5 roadmap.** Approaches 1–2 solve ContextBase's actual problem (default-deny by realm at collection granularity). Approach 3 is the more ambitious model worth exploring as a research project: access labels that cut *across* the collection tree, moving Outline from collection-rooted ACLs toward label-based / information-flow access control. This section scopes that project — motivation, model, why Outline resists it, the hard problems, a prototyping plan, evaluation, and related work.

### 8.1 Motivation — what collection-granularity cannot express

Approach 2 binds one realm to one collection. Real organizations have access needs that cut across that tree:

- **One document, two unrelated realms.** A design note that belongs to both `project-hybrid` and `security-review`, where those realms otherwise share nothing. Under collection-granularity you must duplicate the doc or widen a collection.
- **Sensitivity tiers orthogonal to projects.** A `confidential` label that applies to scattered documents in many collections, enforced uniformly regardless of where a doc lives.
- **Need-to-know subsets inside a shared collection.** A mostly-open project collection with a handful of restricted documents, without splitting the collection.
- **Mandatory (non-discretionary) constraints.** "Anything labeled `embargoed` is unreadable outside the embargo realm, and a member cannot widen it" — a policy the owner cannot override, unlike discretionary collection grants.

These are the cases POSIX *default* ACLs and OS information-flow systems handle and that collection-rooted ACLs cannot. If ContextBase never needs them, Approach 3 stays shelved.

### 8.2 Conceptual model — from ACL to labels and information flow

The progression:

1. **Discretionary ACL (today / Approach 2).** Each resource carries an owner-managed list of user/group grants. Access = union of grants. This is what Outline implements.
2. **Label-based / ABAC.** A resource carries a set of **realm labels**; a subject carries a set of realm **memberships** (clearances). Access is a predicate over (resource labels, subject clearances) — typically "subject holds *every* label" (intersection/clearance, AND-semantics) or "subject holds *any* label" (union, OR-semantics). Note this differs from Approach 2's pure union: a clearance model is **AND across labels**, which is what gives "need-to-know" and sensitivity tiers their teeth.
3. **Information-flow control (IFC).** Labels form a **lattice**; data can only flow from lower to higher (or equal) sensitivity unless explicitly **declassified** by an authorized principal. This is the Denning lattice / Bell–LaPadula lineage, and the OS analogues are Asbestos/HiStar/Flume and the Jif language. Full IFC is almost certainly more than ContextBase wants, but it is the correct frame for reasoning about *leaks* (§8.4), which is the real research content.

A pragmatic target is **(2) with selectable AND/OR per label and an optional "mandatory" flag**, deliberately stopping short of full transitive IFC. The research question is how far up this ladder you must climb before the leak vectors (§8.4) are actually closed.

### 8.3 Why Outline's architecture resists this

The central obstacle is that Outline's entire read path is **collection-rooted**. `User.collectionIds()` (`server/models/User.ts:490`) computes a user's accessible set as *whole collection IDs* — collections with a workspace-wide `permission`, plus those reachable by user or group membership. Document listing, **search**, and **backlinks** all gate on that set (`server/routes/api/documents/documents.ts:165` "filter by all collections the user has access to"; backlinks via `Relationship.findSourceDocumentIdsForUser`). Document policy itself ultimately delegates to the parent collection (`server/policies/document.ts:31`). Inheritance is tree-shaped too: `recreateSourcedMemberships()` propagates a root grant *down the document tree* via `sourceId` (`server/models/UserMembership.ts:323-390`).

A cross-cutting label model violates every one of these assumptions: access is no longer "which collections" but "which documents satisfy a label predicate," and labels do not follow the parent tree. So Approach 3 is not an additive policy rule — it requires **replacing the access-scoping primitive** and every query that funnels through it. That is the core of the work and the core of the risk.

### 8.4 The hard problem — leak vectors

The interesting research is not the access check on a document open; cancan already does that. It is the **many secondary paths** by which restricted content escapes. Each must be made label-aware, and each is a place Outline currently assumes collection-scoping:

| Vector | How it can leak | Where in code |
| --- | --- | --- |
| **Full-text search** | A restricted doc surfaces in results / snippets | search queries gated by `collectionIds()` today; must become label-aware |
| **Backlinks** | "Linked from" reveals existence/title of a doc in another realm | `documents.ts:165,612-626`, `Relationship.findSourceDocumentIds*` |
| **Mentions & link unfurls** | `@mention` or pasted link renders a title/preview across realms | document presenters / unfurl path |
| **Exports** | Collection/zip export bundles documents regardless of per-doc labels | `server/commands/collectionExporter.ts` |
| **Public shares** | `includeChildDocuments` publishes a subtree spanning labels | `server/models/Share.ts`, `shareLoader.ts:84-89` |
| **Embeds / API / webhooks** | Programmatic reads bypass UI-level filtering | `team.documentEmbeds`, REST API, webhook deliveries |
| **Revisions & comments** | History/comments inherit the doc but may resolve access differently | `Revision`, `Comment` models/policies |
| **Notifications / subscriptions** | Update emails quote restricted content to non-members | notification + subscription pipeline |

A correct label system must close *all* of these consistently — the classic IFC observation that confidentiality is only as strong as the leakiest channel. Enumerating and sealing these is the bulk of the project.

### 8.5 Design dimensions (decisions a prototype must make)

- **Label data model.** New `Realm` entity + `ResourceLabel(documentId|collectionId, realmId)` join, vs. reusing `Group` as the label and adding document-level `GroupMembership` rows (which already exist). Reuse minimizes new surface but conflates "group of people" with "label."
- **Combination semantics.** Per-label AND (clearance) vs OR (union) vs a mix; whether labels are a flat set or a lattice with ordering.
- **Discretionary vs mandatory.** Can a doc owner remove a label? A `mandatory` flag makes certain labels non-removable except by realm admins — the MAC vs DAC distinction.
- **Default labels (inheritance).** When a doc is created, which labels does it inherit — from collection, from parent doc, from creator's "current realm"? This is the POSIX *default ACL* question, re-posed without a tree.
- **Resolver & performance.** Replace `collectionIds()` with an accessible-*document* predicate. Options: precomputed per-user accessible-document set (fast reads, expensive invalidation), label-join at query time (simple, slower search), or a Zanzibar-style relationship index (scales, large build). Search integration is the bottleneck.
- **Conflict resolution.** A doc in a permissive collection but bearing a restrictive label — does label win (mandatory) or union win (discretionary)? Must be defined precisely and uniformly across all §8.4 vectors.

### 8.6 Prototyping plan (phased, exploratory)

1. **Model & resolver spike.** Add `Realm` + `ResourceLabel`; implement an `accessibleDocumentIds(user)` resolver alongside (not replacing) `collectionIds()`. Gate only the document-open policy. Measure correctness on a seeded dataset.
2. **Close the read path.** Make document listing, search, and backlinks label-aware. This is where the collection-rooted assumptions break; expect the most churn.
3. **Close the secondary vectors.** Exports, shares/`includeChildDocuments`, mentions/unfurls, API/webhooks, notifications — one at a time, each with a leak test.
4. **Semantics & mandatory labels.** Add AND/OR per label and the `mandatory` flag; define and test conflict resolution.
5. **UX.** Label management, a "current realm" context for authoring, and a visible classification indicator.

Each phase is independently evaluable and abandonable — the project earns its keep only if Phase 2–3 prove tractable on a maintained fork.

### 8.7 Evaluation (what a research result would show)

- **Correctness / no-leak.** A red-team suite that attempts to read restricted content through every §8.4 vector and asserts denial; coverage as the headline metric.
- **Performance.** Search and list latency under the label-aware resolver vs the collection-scoped baseline, across realm-count and document-count scaling.
- **Expressiveness vs Approach 2.** Concrete scenarios (§8.1) expressible in Approach 3 but not 2, and the authoring cost of each.
- **Maintenance cost.** Rebase burden against upstream Outline over time — a real axis given how deep the changes cut.

### 8.8 Related work

- **POSIX ACLs / NFSv4 ACLs** — named-user/named-group entries, default ACLs (the §2 mental model).
- **RBAC / ABAC** (NIST) — role- and attribute-based access control; the label predicate is ABAC.
- **Information-flow control** — Denning's lattice model; Bell–LaPadula (confidentiality); language-level (Jif/FlowCaml) and OS-level (Asbestos, HiStar, Flume) IFC; the source of the leak-vector framing and declassification.
- **Relationship-based access control** — Google **Zanzibar** — a scalable model for "is subject related to object" that is a candidate resolver architecture if the label graph grows.
- **Capability systems** — an alternative to ACLs (unforgeable references) worth contrasting, though further from Outline's model.

### 8.9 Research questions

- How far up the §8.2 ladder (ACL → ABAC → IFC) is actually required to close the §8.4 leak vectors for a wiki workload?
- Can a label-aware resolver match collection-scoped search latency, or is a precomputed/Zanzibar index unavoidable?
- What is the minimal, *upstreamable* extension to Outline that supports labels without forking the entire read path?
- Where is the usability cliff — at what point does per-document labeling cost more author effort than splitting collections (Approach 2)?

### 8.10 Risks & why it stays non-urgent

Approach 3 cuts through Outline's most load-bearing assumption (collection-rooted access), so it carries the highest divergence and rebase cost, the largest correctness surface (every leak vector), and real performance risk in search. It should begin only as a **time-boxed spike (Phase 1–2)** to test tractability, and only once Approaches 1–2 are in place and a concrete cross-cutting need (§8.1) has actually surfaced.
