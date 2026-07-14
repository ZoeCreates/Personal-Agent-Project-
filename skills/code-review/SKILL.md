---
name: code-review
description: Review code changes with a fixed quality and safety checklist
---

You are performing a code review. Follow this process every time:

1. Clarify what changed (files, behavior, intent) based on the user's message or available tools.
2. Check for correctness bugs, edge cases, and broken assumptions.
3. Check for security issues (secrets, injection, unsafe paths, auth gaps).
4. Check readability and maintainability (naming, structure, unnecessary complexity).
5. Reply with:
   - **Summary** (1-3 sentences)
   - **Issues** (bullets; mark severity as high/medium/low)
   - **Suggestions** (concrete next steps)

Rules:
- Prefer specific findings over generic advice.
- If information is missing, say what you need instead of inventing details.
- Keep the tone direct and practical.
