# Strategies

Generic trading strategy source files, organized by runner platform.

Each runner subdirectory holds strategy files in the platform's native format. Strategies are kept generic — no firm-specific defaults. All foundational parameters (account size, risk %, daily limits, entry hours) are injected at run time from the active ruleset via the command center.

See `CLAUDE.md` for standing instructions, the current strategy list, and the deployment workflow (scanner → Deploy button → Compile All).
