# Cursor AI Prompt: Generate Microservice Introduction Page for Apidog

## Context

You are scanning a .NET microservice codebase. Your task is to generate an **Introduction page** (hub page) in Apidog Markdown format for this specific microservice.

This page is the **first thing** a reader sees when they open the microservice folder in Apidog. It provides:
- What this service does (for PO/BDM/SA/Dev — all audiences)
- Visual architecture overview
- Products/features table
- Navigation cards to each domain folder (where Swagger endpoints live)
- Technical reference summary

**This page does NOT contain:**
- Sequence diagrams (those go into Overview pages inside each domain folder)
- Detailed endpoint descriptions (those are auto-imported from Swagger)
- Full integration specs (those go into a separate Technical Reference page if needed)

---

## Step 1: Scan the codebase

Find and extract the following information:

### 1.1 Service identity
- Service name → from `.csproj` or solution folder (e.g. `MyCredo.Retail.Loan`)
- Purpose → from existing `README.md`, `Program.cs` description, or XML doc comments
- Tech stack → from `.csproj` dependencies (runtime, frameworks, caching, logging, etc.)

### 1.2 Domain folders (controllers / endpoint groups)
Scan all controllers and group them by domain. Each domain = one folder in Apidog sidebar.

For each domain find:
- **Folder name** → from controller name or existing Apidog folder structure
- **Short description** → from controller XML comments or action method names
- **Key operations** → list 3-5 main actions (from method names / routes)
- **Route prefix** → from `[Route]` attribute

Example output:
```
Domain: DigitalLoan
Description: Fully online consumer loans with automated approval
Key operations: Initiate, Finish, Calculate, GetStatus
Route prefix: /api/v1/request-loan/digital-loan
```

### 1.3 Products / features
Scan for product types, enums, or configuration classes that define what products this service manages.
Build a table of: Product Name | Description

### 1.4 External integrations
Scan `Infrastructure` layer for HTTP clients, gRPC clients, or service references.
Build a table of: System Name | Purpose | Client Class

### 1.5 Architecture layers
Identify the project structure layers:
- API layer (controllers)
- Application layer (business logic, MediatR handlers, CQRS)
- Infrastructure layer (external clients, DB access)
- Domain layer (entities, value objects)

### 1.6 Authentication
From middleware, attributes like `[Authorize]`, or auth configuration — determine:
- Auth method (JWT Bearer, API Key, etc.)
- Are there role-based restrictions?
- Is OTP used for sensitive operations?

### 1.7 Response format
From base response classes or middleware — extract the standard response envelope structure.

---

## Step 2: Generate the Introduction page

Using the extracted data, generate a single `.md` file following the template below.

### OUTPUT RULES — Apidog compatibility

#### ✅ USE (proven to work):
- Standard Markdown: `#`, `##`, `###`, `---`, `**bold**`, `` `code` ``, tables, lists
- `<CardGroup cols={N}>` + `<Card>` — for navigation to domain folders
- `:::tip`, `:::info`, `:::warning`, `:::note` — admonition blocks
- HTML `<table>` with **inline `style=""`** — ONLY for architecture visualization
- `<p className="...">` — for Apidog Markdown styled subtitle text

#### ❌ DO NOT USE (broken in Apidog published pages):
- **Mermaid diagrams** — text in nodes is invisible on published pages
- **`className` on HTML tags** like `<div>`, `<td>`, `<span>` — Apidog ignores these
- **Tailwind classes on raw HTML** — only works inside Apidog custom components
- **`<Columns>` / `<Column>`** — renders inconsistently
- **Sequence diagrams** — these belong in domain folder Overview pages, NOT here

---

## Step 3: Page template

Generate the page following this exact structure:

### Section 1 — Title

```markdown
# {emoji} {ServiceName}

<p className="text-lg text-gray-500 text-center">{One-line description of what this service does}</p>

---
```

Pick emoji based on service domain: 💳 loans/payments, 🔐 auth/security, 📦 general, 🛒 commerce, 📊 analytics, 🔔 notifications, ⚙️ infrastructure.

### Section 2 — Overview

```markdown
## Overview

{2-3 paragraphs in plain language explaining:}
{- What this service does and why it exists}
{- Who uses it (mobile app, web app, internal services, admin panel)}
{- What business value it provides}
```

### Section 3 — Architecture (HTML table with inline styles)

Build an HTML `<table>` showing the layered architecture.

**Rules:**
- Use `border-collapse:separate; border-spacing:8px;` on the table
- Each layer is a row with colored cells
- Cell format: `<small style="color:{small}">{layer_label}</small><br/><b style="color:{text}">{component_name}</b>`
- Each cell has: `border`, `border-radius:8px`, `background`, `text-align:center`, `padding:10px 16px`
- Below the table: `<p style="text-align:center; font-size:12px; color:#9CA3AF; font-style:italic;">{request flow description}</p>`

**Layer color scheme:**

| Layer | border | bg | text | small |
|-------|--------|----|------|-------|
| Clients | #D1D5DB | #F9FAFB | #374151 | #9CA3AF |
| API Gateway | #A5B4FC | #EEF2FF | #4338CA | #818CF8 |
| This Service (API) | #93C5FD | #EFF6FF | #1D4ED8 | #60A5FA |
| Business Logic | #C4B5FD | #F5F3FF | #6D28D9 | #A78BFA |
| Infrastructure | #FCD34D | #FFFBEB | #B45309 | #F59E0B |
| External Systems | #FCA5A5 | #FEF2F2 | #B91C1C | #F87171 |

**Architecture table template:**
```html
<table style="width:100%; border-collapse:separate; border-spacing:8px; border:none;">
  <tr>
    <td colspan="4" style="text-align:center; padding:10px 16px; border:1px solid #D1D5DB; border-radius:8px; background:#F9FAFB;">
      <small style="color:#9CA3AF;">Clients</small><br/>
      <b style="color:#374151;">📱 Mobile App · 🌐 Web App</b>
    </td>
  </tr>
  <tr>
    <td colspan="4" style="text-align:center; padding:10px 16px; border:2px solid #93C5FD; border-radius:8px; background:#EFF6FF;">
      <small style="color:#60A5FA;">API Layer</small><br/>
      <b style="color:#1D4ED8;">{ServiceName}.Api</b>
    </td>
  </tr>
  <tr>
    <td colspan="4" style="text-align:center; padding:10px 16px; border:2px solid #C4B5FD; border-radius:8px; background:#F5F3FF;">
      <small style="color:#A78BFA;">Business Logic</small><br/>
      <b style="color:#6D28D9;">{ServiceName}.Application</b>
    </td>
  </tr>
  <tr>
    <td colspan="4" style="text-align:center; padding:10px 16px; border:2px solid #FCD34D; border-radius:8px; background:#FFFBEB;">
      <small style="color:#F59E0B;">Infrastructure</small><br/>
      <b style="color:#B45309;">{ServiceName}.Infrastructure</b>
    </td>
  </tr>
  <tr>
    <!-- Generate one <td> per external system, adjust colspan if needed -->
    <td style="text-align:center; padding:8px 12px; border:1px solid #FCA5A5; border-radius:8px; background:#FEF2F2;">
      <small style="color:#F87171;">External</small><br/>
      <b style="color:#B91C1C;">{SystemName}</b>
    </td>
    <!-- repeat for each external system, max 4 per row -->
  </tr>
</table>

<p style="text-align:center; font-size:12px; color:#9CA3AF; font-style:italic;">
  {Flow description, e.g.: "Client → API Gateway → Service API → Business Logic → Infrastructure → External Systems"}
</p>
```

If there are more than 4 external systems, split into 2 rows.

### Section 4 — Products / Features

```markdown
## Key Features

### {Category 1, e.g. "Loan Products"}

| Product | Description |
|---------|-------------|
| **{Name}** | {Short description} |
...

### {Category 2, e.g. "Insurance Products"}

| Product | Description |
|---------|-------------|
| **{Name}** | {Short description} |
...
```

### Section 5 — Domain Navigation (CardGroup)

```markdown
---

## 📦 API Domains

<CardGroup cols={3}>

<Card title="{emoji} {DomainName}" href="apidog://link/pages/{PAGE_ID}" icon="{icon}">

{Short description}

`{Operation1}` · `{Operation2}` · `{Operation3}`

</Card>

<!-- repeat for each domain -->

</CardGroup>
```

**Rules for CardGroup:**
- Use `cols={3}` for 6+ domains, `cols={2}` for 2-5 domains
- If `PAGE_ID` is unknown, use `href="#"` as placeholder and add a comment `<!-- TODO: replace with actual page ID -->`
- Pick icon from: `material-two-tone-credit_card`, `material-two-tone-payments`, `material-two-tone-security`, `material-two-tone-receipt`, `material-two-tone-shield`, `material-two-tone-account_balance`, `material-two-tone-shopping_cart`, `material-two-tone-local_hospital`, `material-two-tone-description`, `material-two-tone-swap_horiz`
- Pick emoji: 💳 cards, 💰 loans, 🛡️ insurance, 📋 applications, 🔑 OTP/auth, 📊 products, 🏪 shop, ⚙️ config, 🔄 limits

### Section 6 — External Integrations

```markdown
---

## 🔗 External Integrations

| System | Purpose | Client |
|--------|---------|--------|
| **{SystemName}** | {What it does} | `{ClientClassName}` |
...
```

### Section 7 — Authentication & Response Format

```markdown
---

## 🔐 Authentication

{1-2 sentences about auth method}

:::warning
{Any important auth notes, e.g. "All endpoints except health check require JWT Bearer token. Sensitive operations require OTP verification."}
:::

---

## 📋 Response Format

All responses follow a standard envelope:

\`\`\`json
{
  "isSuccess": true,
  "data": { ... },
  "errors": null
}
\`\`\`

| Status Code | Meaning |
|-------------|---------|
| `200` | Request successful |
| `400` | Invalid input parameters |
| `401` | Missing or invalid authentication |
| `404` | Resource not found |
| `422` | Business rule validation failed |
| `500` | Server-side error |
```

### Section 8 — Tech Stack & Support

```markdown
---

## ⚙️ Tech Stack

| Component | Technology |
|-----------|------------|
| Runtime | {e.g. .NET 8.0} |
| Architecture | {e.g. Clean Architecture + CQRS with MediatR} |
| Caching | {e.g. Redis + In-Memory Cache} |
| API Docs | Swagger/OpenAPI |
| Logging | {e.g. Serilog} |
...

---

## 🛠️ Support

| Role | Contact |
|------|---------|
| **Tech Owner** | {from CODEOWNERS or git config} |
| **Last Updated** | {today YYYY-MM-DD} |

:::note
For detailed endpoint specifications and testing, browse the endpoint folders in the sidebar or use the Swagger UI at `/swagger`.
:::
```

---

## Step 4: Save

Save the output as `introduction.md` in the working directory.

---

## Final Rules

1. Output ONLY the markdown content — no explanations, no wrapping code fences
2. Architecture MUST use HTML `<table>` with inline `style=""` — NEVER use Mermaid
3. Do NOT include sequence diagrams — those go into domain folder Overview pages
4. Do NOT include detailed endpoint documentation — that comes from Swagger
5. Never mention any specific bank name in the output — keep it generic
6. Keep the page scannable — a reader should understand the service in 30 seconds
7. Products and integrations tables should be complete — scan the entire codebase
8. All `apidog://link/pages/{id}` should use `#` placeholder if page ID is unknown
9. CardGroup should list ALL domain folders that appear in the Apidog sidebar
10. If information cannot be determined from codebase, use `TBD` placeholder
