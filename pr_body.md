This PR relaxes the SCV Sandbox to allow SCV-Coder agents to access their worktrees and execute git commands. 

Changes included:
1. Removed `--sandbox` flag when spawning agents via `gemini` in `src/adjutant/engine.py`.
2. Added `--include-directories` for `worktree_path` to provide the agent access to its workspace.
3. Updated the SCV-Coder policy in `src/adjutant/agents/scv-coder/policies/scv-coder.toml` to permit `git` commands with `run_shell_command` tool.
4. Updated tests in `src/tests/test_engine_spawning.py` to ensure the sandbox restrictions are appropriately relaxed.