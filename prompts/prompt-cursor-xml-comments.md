# Cursor AI Prompt: Generate XML Documentation Comments for All Endpoints

## Context

You are scanning a .NET microservice codebase. Your task is to add comprehensive XML documentation comments to **every controller action method** that currently lacks proper documentation.

These comments flow through the pipeline: **C# XML → Swashbuckle → swagger.json → Apidog endpoint descriptions** (auto-sync).

---

## Step 1: Scan

For each controller, find all public action methods (`[HttpGet]`, `[HttpPost]`, `[HttpPut]`, `[HttpDelete]`, `[HttpPatch]`).

For each method, determine:
- **What it does** — from method name, route, request/response types, business logic in handler
- **Parameters** — from method signature, `[FromBody]`, `[FromQuery]`, `[FromRoute]`
- **Responses** — from return type, `ProducesResponseType` attributes, or business logic (success + error cases)
- **Flow position** — which step in the domain flow this endpoint is (look at related endpoints in the same controller)
- **Prerequisites** — what must be called before this endpoint (e.g., initiate before finish, OTP before finish)
- **Next step** — what the caller should do after this endpoint succeeds

---

## Step 2: Determine the domain flow

Group endpoints by controller / domain folder. For each group, determine the call sequence.

Example:
```
DigitalLoan domain:
  Step 1: POST /request-loan/digital-loan/initiate
  Step 2: POST /otp/send
  Step 3: POST /otp/validate  
  Step 4: POST /request-loan/digital-loan/finish
```

This flow information will be embedded in each endpoint's `<remarks>` so the reader knows where this endpoint fits.

---

## Step 3: Generate XML comments

For each action method, generate the following XML comment block **directly above the method**:

```csharp
/// <summary>
/// {One-line description of what this endpoint does}
/// </summary>
/// <remarks>
/// **Step {N} of {Total}** in {DomainName} flow: `{Step1} → {Step2} → ... → {StepN}`
/// 
/// {2-4 bullet points describing what happens internally:}
/// - {Operation 1, e.g. "Retrieves customer data from CSS"}
/// - {Operation 2, e.g. "Runs AML/KYC verification"}
/// - {Operation 3, e.g. "Creates loan application in CSS"}
/// 
/// **Prerequisites:** {What must be done before calling this endpoint}
/// 
/// **Next step:** {What to call after this endpoint, or "None — this is the final step."}
/// 
/// Sample request:
/// 
///     {HTTP_METHOD} {FULL_ROUTE}
///     {JSON body example if POST/PUT, omit for GET/DELETE}
/// 
/// </remarks>
/// <param name="{paramName}">{Description of parameter}</param>
/// <response code="200">{Success response description}</response>
/// <response code="400">{Validation error description}</response>
/// <response code="401">Missing or invalid JWT Bearer token</response>
/// <response code="422">{Business rule violation description}</response>
/// <response code="404">{Not found description, if applicable}</response>
/// <response code="500">Internal server error</response>
```

---

## Rules

### Content rules:
1. `<summary>` — ONE line, starts with a verb (Initiates, Creates, Retrieves, Validates, Generates, Submits, Cancels)
2. `<remarks>` — MUST include: flow position, internal operations list, prerequisites, next step, sample request
3. `<param>` — for EVERY parameter in the method signature
4. `<response>` — at minimum: 200, 400, 401. Add 404, 422, 500 as appropriate
5. Sample request JSON — use realistic but generic values (not real customer data)
6. Flow position — format: `**Step N of M** in {Domain} flow: \`Step1 → Step2 → Step3\``
7. Prerequisites — if this is Step 1, write: `**Prerequisites:** Customer must be authenticated (JWT Bearer).`
8. Next step — if this is the last step, write: `**Next step:** None — this completes the {Domain} flow.`

### Format rules:
9. Do NOT use Mermaid, diagrams, or HTML in XML comments — only plain text and markdown
10. Do NOT use `<` or `>` characters in remarks text — use `` ` `` backticks for code references
11. Indent JSON examples with 4 spaces (Swashbuckle renders them as code blocks)
12. Keep `<summary>` under 80 characters
13. Keep total `<remarks>` under 30 lines
14. Do NOT duplicate information already in `[SwaggerOperation]` or `[SwaggerResponse]` attributes

### Scope rules:
15. Only add/update XML comments — do NOT modify any C# logic, routes, or attributes
16. Skip methods that already have complete XML documentation (summary + remarks + params + responses)
17. For methods with partial documentation, fill in the missing parts only
18. If a method's purpose is unclear from the code, add `<!-- TODO: verify this description -->` inside the comment

---

## Step 4: Ensure Swashbuckle configuration

Verify that the project has XML documentation enabled. If not, output instructions to add:

```csharp
// In .csproj:
<PropertyGroup>
  <GenerateDocumentationFile>true</GenerateDocumentationFile>
  <NoWarn>$(NoWarn);1591</NoWarn>
</PropertyGroup>

// In Program.cs or Startup.cs:
builder.Services.AddSwaggerGen(options =>
{
    options.IncludeXmlComments(Path.Combine(
        AppContext.BaseDirectory,
        $"{Assembly.GetExecutingAssembly().GetName().Name}.xml"), true);
});
```

---

## Example output

### Before:
```csharp
[HttpPost("digital-loan/initiate")]
public async Task<ActionResult<InitiateAggregateResult>> Initiate(
    [FromBody] DigitalLoanInitiateRequest request)
{
    // ...
}
```

### After:
```csharp
/// <summary>
/// Initiates a digital loan application
/// </summary>
/// <remarks>
/// **Step 1 of 3** in Digital Loan flow: `Initiate → OTP → Finish`
/// 
/// Performs the following operations:
/// - Retrieves customer data from CSS
/// - Runs AML/KYC check
/// - Requests credit scoring from Core Banking
/// - Calculates insurance premium (if applicable)
/// - Creates loan application in CSS
/// 
/// **Prerequisites:** Customer must be authenticated (JWT Bearer).
/// 
/// **Next step:** Call `POST /otp/send` to send OTP to customer's phone.
/// 
/// Sample request:
/// 
///     POST /api/v1/request-loan/digital-loan/initiate
///     {
///         "amount": 5000,
///         "currency": "GEL",
///         "term": 12,
///         "productId": "DL-001"
///     }
/// 
/// </remarks>
/// <param name="request">Loan initiation parameters including amount, term, and product type</param>
/// <response code="200">Returns Process ID and list of required documents</response>
/// <response code="400">Invalid input — amount or term out of allowed range</response>
/// <response code="401">Missing or invalid JWT Bearer token</response>
/// <response code="422">Customer not eligible — failed credit scoring or AML check</response>
[HttpPost("digital-loan/initiate")]
public async Task<ActionResult<InitiateAggregateResult>> Initiate(
    [FromBody] DigitalLoanInitiateRequest request)
{
    // ...
}
```
