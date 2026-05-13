# Xushi Optimization Notes

Use this when real xushi usage exposes a product issue, confusing behavior, missing guide, or repeated workaround. The goal is to preserve high-quality feedback for the user to share manually later.

## Rules

- Record only things that actually happened while using xushi. Do not invent speculative issues.
- Be detailed enough that a maintainer can reconstruct the sequence without asking for the whole chat.
- Include the expected behavior in concrete terms.
- Include why the note helps improve xushi: agent ergonomics, reliability, API shape, docs, data cleanup, safety, or user experience.
- Do not upload, post, email, or create public issues automatically. Share the note only when the user asks.
- Do not include secrets, tokens, private URLs, personal contact details, or sensitive message contents. Redact when needed.

## Where To Keep The Draft

If file writes are available, append to `docs/xushi-feedback-notes.md` in the active workspace. If that file does not exist, create it with a short title and then append entries. If there is no suitable workspace, keep a concise draft in the conversation and offer it when the user asks for feedback material.

## Entry Template

```markdown
## YYYY-MM-DD HH:mm - Short title

### Actual Context

- User goal:
- Task or run involved:
- Environment:

### Timeline

1. What the user asked or configured.
2. What xushi or the agent did.
3. What result exposed the issue.

### Actual Behavior

Describe the observed behavior, including statuses, API calls, records, or commands when useful.

### Expected Behavior

Describe the specific outcome that would have been better.

### Impact

Explain how this affected the user or agent workflow.

### Current Workaround

Describe how the agent handled it today, if any.

### Suggested Direction

Describe a possible product, API, skill, or documentation improvement.
```

## Good Note Shape

A good note says "At 10:20 the user said they had drunk water and stood up, but I only replied conversationally and did not record completion in xushi. When the user asked, I had to list recent runs and manually identify what was pending. Expected: if the task id is known, the agent should call the task-level complete operation so early completion and pending-run confirmation both work." This is actual, detailed, and points to an actionable API/skill improvement.
