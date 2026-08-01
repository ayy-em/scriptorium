# Hard Workflow Rules

- Whenever you receive a prompt, quickly and very approximately assess the task's size, scope and implementation complexity level 
- Use "Simple Workflow" if your quick assessment of the task suggests that the task satisfies at least 2 of these criteria: 
    - Easy (touches 2 files max; adjusts existing code without adding new logic; slight changes to code previously delivered in the same session)
    - Quick to implement (estimated to be up to 10 lines of code) 
    - Straightforward (little to no ambiguity in both requirements and execution; implementation specifics have little to no impact on the overall project) 
    - Does not require new dependencies to be added 
    - Only requires changes to constants, variable naming, 
- If confident that the task satisfies at least 3 of the criteria above, use "Simple Workflow" described below
- Otherwise (or in case of uncertainty about your assessment), use the "Standard Workflow" described at the bottom of this file

## Simple Workflow
General idea: Given a clearly defined, small and unambiguous task, execute it in a single go following the steps below.
1. Implement requested changes to the codebase the way you see fit.
2. Once done, run the three checks in sequence:
    - `uv run ruff format .`
    - `uv run ruff check --fix`
    - `uv run pytest -q`
3. If any of the checks fail, fix the issues and repeat the checks. If the checks still fail after 2 attempts, stop and ask the user for further instructions. Do not iterate further without explicit instruction.
4. Once all checks succeed, review if any .md files with docs, docstrings or comments in the code base need to be updated. If so, update them. Otherwise, move on to the next step.
5. Once done, report back to the user with a very concise, bullet-point summary: all files that were created, modified or deleted, what exactly was changed, risks and/or limitations of the implementation,and any assumptions made.

## Standard Workflow
General idea: Progress through a series of loops described below to complete the task, each step building on the previous one. Only move on to the next loop after successfully completing the current one.
1. Clarification loop: 
    - Ask clarifying questions, preferably in form of multiple-choice or yes/no questions
    - Upon receiving a clarification, reassess if any ambiguity remains in the task's scope or requirements
    - Completion condition: Task's scope, requirements and ways to handle edge cases are unambiguous
2. Context gathering loop: 
    - Study relevant in-repo context: any .md files, repo code, READMEs, docstrings, etc.
    — If third-party packages, APIs or any other external sources are involved, do not rely on training-data memory. Always use context7 MCP - call resolve-library-id, then get-library-docs.
    - Completion condition: All relevant documentation and context have been gathered and understood, no contradictions found
3. Solution design loop:
    - Propose a solution design summary of 5–15 bullets, explicitly mentioning: 
        - General approach to solving the task + ultra-short mention of equally viable alternative approaches
        - All the files the implementation will change, create and delete
        - Acceptance criteria to serve as completion condition 
        - Risks, limitations, caveats and assumptions (e.g.: what could break, what's out of scope, what's assumed)
        - [Conditional] If the task completion requires (or would significantly benefit from) adding new dependencies, explicitly list them and provide a quick justification.
        - [Optional] If there is significant benefit to expanding the solution to future-proof the functionality (for instance, by adding an abstraction layer, extracting a function, etc.), provide a micro-proposal. Example situation: you are given a task to add a function that performs an API call to OpenAI's tts endpoint. Example micro-proposal: "Consider adding an abstract TTSProvider class to support other providers down the line."
    - Wait for user's feedback before proceeding. If the user requests any changes to the solution design, repeat the solution design loop from the beginning.
    - Completion condition: Solution design is approved by the user.
    - [Conditional] If the provided solution design featured a scope expansion proposal, handle it this way:
        - If ignored by user: Disregard, only implement the original logic.
        - If user says "backlog", "later", "in the future": create `BACKLOG.md` in repo root if not yet present, and document the proposed scope expansion with all the relevant context.
        - If user says "expand scope as suggested", "yes to expansion proposal" or "agreed to expand": restart the solution design loop for the expanded scope.
4. Implementation loop:
    - Execute the solution design, creating and modifying only the specified files.
    - Each new or modified file should be covered by unit tests in the `tests/` folder, mirroring the file structure of the actual codebase.
    - Once done with implementation, run the three checks in sequence:
        - `uv run ruff format .`
        - `uv run ruff check --fix`
        - `uv run pytest -q`
    - If any of the checks fail, fix the issues and repeat the checks. If the checks still fail after 2 attempts, stop and ask the user for further instructions. Do not iterate further without explicit instruction.
    - Completion condition: Acceptance criteria defined in solution design are all met, all checks pass.
5. Documentation loop:
    - Document any new functionality in relevant in-repo docs (README.md, CONTRIBUTING.md, BACKLOG.md, etc.).
    - Review existing docstrings and comment blocks to ensure they reflect reality.
    - Completion condition: All in-repo docs are up to date and reflect reality.
6. Wrap up loop:
    - Summarise the changes made: all files that were created, modified or deleted, functionality added, bugs fixed, etc.
    - Propose a commit message that captures the essence of the changes made, along with a copy-paste ready git command to execute the commit.
