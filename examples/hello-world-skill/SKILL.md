---
name: hello-world-skill
description: Create or update hello-world.txt with a Codex greeting. Use when you need a minimal instruction-only Agent Skill example with explicit verification.
---

# Hello World Skill

Use this skill to create or update one file with a fixed greeting and verify
the result.

## Steps

1. Inspect the current directory enough to avoid overwriting unrelated work.
2. Create or update `hello-world.txt` with exactly:

   ```text
   Hello from Codex.
   ```

3. Read `hello-world.txt` and verify that its content matches exactly.
4. Report the changed file and verification result.

## Output

Return a short final response naming `hello-world.txt` and confirming the
verification result.
