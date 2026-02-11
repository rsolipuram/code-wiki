---
name: ask-gemini
description: Collaborate with Google Gemini for research, code review, feedback, validation, or second opinions
---

# Ask Gemini Skill

Collaborate with Google Gemini for research, code review, feedback, validation, or second opinions.

## Purpose

This skill enables model collaboration where Claude can delegate work to Gemini to get:
- Alternative perspectives on architectural decisions
- Code review from a different model
- Research validation and enhancement
- Edge case identification
- Performance and security feedback

## When to Use

Use this skill when:
- You need a second opinion on important decisions
- You want to validate code quality before committing
- You're researching complex topics and want multiple perspectives
- You need to identify blind spots or edge cases
- You want to enhance specifications or documentation
- A subagent needs expert consultation

## Parameters

The user will invoke this with:
```
/ask-gemini "prompt" "context"
```

Or from a subagent:
```
Skill: ask-gemini
Args: prompt="Review this code" context="src/file.js"
```

**Required:**
- `prompt` - The question or task for Gemini (what you want Gemini to do)

**Optional:**
- `context` - Files, code, or additional information for Gemini to consider
  - Can be file paths (e.g., `src/parser.js`)
  - Can be directory paths (e.g., `specs/`)
  - Can be multiple files (space-separated)
  - Can be text/code snippets

## Execution Instructions

### Step 1: Parse Input

Extract the prompt and context from user input:
- If args provided, use those
- Otherwise parse from natural language

### Step 2: Gather Context

If context includes file paths:
1. Use `Read` tool to read the files
2. If directory, use `Glob` to find relevant files
3. Limit to reasonable size (don't send 100+ files)
4. Summarize if files are very large

### Step 3: Craft Enhanced Prompt for Gemini

Create a rich prompt that includes:
1. The user's original prompt
2. Relevant context from files
3. Project information (if helpful)
4. Specific questions or focus areas

**Example Enhanced Prompt:**
```
[User's Question]
Review this specification for completeness and edge cases.

[Context]
File: specs/001-code-wiki/spec.md
```markdown
[file contents here]
```

[Additional Context]
- This is part of a documentation generation system
- Target audience: developers
- Performance requirements: handle repos up to 100k files

[Specific Focus]
Please identify:
1. Missing edge cases
2. Unclear requirements
3. Potential performance issues
4. Security considerations
5. Suggested improvements
```

### Step 4: Call Gemini via CLI

Use the Gemini CLI directly via Bash tool:

```bash
# Create a temporary file with the enhanced prompt
echo "[enhanced prompt with context]" > /tmp/gemini-prompt.txt

# Call Gemini CLI
gemini --model gemini-3-pro-preview < /tmp/gemini-prompt.txt

# Or with streaming:
gemini --model gemini-3-pro-preview --stream < /tmp/gemini-prompt.txt
```

**Alternative: Direct pipe**
```bash
echo "[enhanced prompt]" | gemini --model gemini-3-pro-preview
```

**Model Selection:**
- Default: `gemini-3-pro-preview` (most capable, deep reasoning)
- For quick questions: `gemini-2.5-flash` (ultra-fast)
- For code generation: `gemini-3-pro-preview`
- For latest features: `gemini-2.0-flash` (audio/video support)

**CLI Flags:**
- `--model` - Specify Gemini model
- `--stream` - Stream response (optional)
- `--temperature` - Control randomness (0-1)
- `--json` - Output JSON format (if needed)

### Step 5: Process Response

1. Capture Gemini's CLI output
2. Format it nicely with markdown
3. Extract key points (if response is long)
4. Save conversation context for follow-ups (if needed)

### Step 6: Present to User

Format output as:

```markdown
## Gemini's Analysis

[Gemini's response, formatted nicely]

---

## Summary (if response is long)

**Key Points:**
- [bullet point 1]
- [bullet point 2]
- [bullet point 3]

**Recommendations:**
- [action item 1]
- [action item 2]

---

## Next Steps

Would you like me to:
1. [Specific action based on Gemini's feedback]
2. [Another specific action]
3. Ask Gemini a follow-up question
```

### Step 7: Offer Actions

Based on Gemini's response, offer to:
- Implement suggestions
- Update files with feedback
- Create tasks for follow-up work
- Ask Gemini follow-up questions (preserve continuation_id)

## Examples

### Example 1: Code Review

**Input:**
```
/ask-gemini "Review for bugs and security issues" src/parser.js
```

**What Claude Does:**
1. Reads `src/parser.js`
2. Creates prompt: "Review this code for bugs, security vulnerabilities, and best practices..."
3. Calls Gemini with code context
4. Returns formatted review
5. Offers to fix identified issues

### Example 2: Spec Enhancement

**Input:**
```
/ask-gemini "Identify missing requirements and edge cases" specs/spec.md
```

**What Claude Does:**
1. Reads `specs/spec.md`
2. Analyzes current spec structure
3. Asks Gemini for gaps, edge cases, unclear areas
4. Returns comprehensive feedback
5. Offers to update spec with improvements

### Example 3: Architecture Decision

**Input:**
```
/ask-gemini "Compare REST vs GraphQL for our documentation API"
```

**What Claude Does:**
1. Gathers project context
2. Creates structured comparison prompt
3. Gets Gemini's analysis with pros/cons
4. Returns detailed comparison
5. Offers to create decision document

### Example 4: Research Validation

**Input:**
```
/ask-gemini "Validate this research and suggest additional sources" research-notes.md
```

**What Claude Does:**
1. Reads research notes
2. Asks Gemini to validate facts and add perspectives
3. Gets additional sources and corrections
4. Returns enhanced research
5. Offers to update notes

## Advanced Usage

### Follow-up Questions

For follow-up questions, Claude can maintain context by:
1. Saving previous conversation in a temporary file
2. Including it in subsequent prompts to Gemini
3. Building on previous responses

```
User: /ask-gemini "What about performance?"
Claude: [Includes previous Q&A context in new prompt to Gemini]
```

### Multi-file Context

```
/ask-gemini "Compare these implementations" src/v1.js src/v2.js
```

### Directory Analysis

```
/ask-gemini "Review architecture patterns" src/
```

## Tips for Effective Use

1. **Be Specific:** "Review for security issues" > "Review this"
2. **Provide Context:** Include relevant files, not entire codebase
3. **Ask Focused Questions:** Narrow scope = better responses
4. **Use for Important Decisions:** Two perspectives = better outcomes
5. **Iterate:** Use continuation for follow-up questions

## Error Handling

If Gemini CLI fails:
1. Check if Gemini CLI is installed (`which gemini` or `gemini --version`)
2. Verify API key is set in environment (usually `GOOGLE_API_KEY` or `GEMINI_API_KEY`)
3. Check if model name is correct
4. Try with smaller context (if prompt too large)
5. Check for rate limiting or quota issues
6. Fall back to Claude-only analysis with note to user

## Technical Notes

- Uses Gemini CLI directly via Bash tool
- Context maintained via conversation history in prompts
- Context window: Gemini supports 1M tokens (model dependent)
- Model selection: Defaults to `gemini-3-pro-preview`
- Can be invoked by subagents via `Skill` tool
- Requires Gemini CLI to be installed and configured

## Output Format

Always return structured output:
1. Clear heading
2. Gemini's response (formatted)
3. Summary of key points
4. Actionable next steps
5. Offer to implement or follow up

---

**Remember:** This skill enables model collaboration for better outcomes. Use it when a second perspective adds value!
