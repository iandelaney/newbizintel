---
name: vercel-deploy
description: Deploy applications and websites to Vercel. Use when the user requests deployment actions like "deploy my app", "deploy and give me the link", "push this live", or "create a preview deployment".
---

# Vercel Deploy

Deploy any project to Vercel instantly. **Always deploy as preview** (not production) unless the user explicitly asks for production.

## Prerequisites

- Check whether the Vercel CLI is installed **without** escalated permissions.
- On Windows, prefer `Get-Command vercel -ErrorAction SilentlyContinue` or `Get-Command vercel.cmd -ErrorAction SilentlyContinue`.
- On Unix-like shells, `command -v vercel` is fine.
- Only escalate the actual deploy command if sandboxing blocks the deployment network calls (`sandbox_permissions=require_escalated`).
- The deployment might take a few minutes. Use appropriate timeout values.

## Quick Start

1. Check whether the Vercel CLI is installed (no escalation for this check).

Windows PowerShell:

```powershell
Get-Command vercel -ErrorAction SilentlyContinue
Get-Command vercel.cmd -ErrorAction SilentlyContinue
```

Unix-like shells:

```bash
command -v vercel
```

2. If `vercel` is installed, deploy with the CLI first.

Windows PowerShell:

```powershell
vercel deploy <path> -y
```

If `vercel` is only available as a command shim, this is also acceptable:

```powershell
vercel.cmd deploy <path> -y
```

Unix-like shells:

```bash
vercel deploy <path> -y
```

**Important:** Use a 10 minute (600000ms) timeout for the deploy command since builds can take a while.

3. If `vercel` is not installed, or if the CLI fails with an auth error such as `No existing credentials found`, use the fallback script.

## Fallback (No Auth)

On Windows, use the PowerShell fallback first:

```powershell
& '<path-to-skill>\scripts\deploy.ps1' '<path-to-project>'
```

On Unix-like shells, use the Bash fallback:

```bash
bash "$skill_dir/scripts/deploy.sh" /path/to/project
```

The fallback scripts handle framework detection, packaging, and deployment. They wait for the deployment to respond successfully and return JSON with `previewUrl` and `claimUrl`.

**Tell the user:** "Your deployment is ready at [previewUrl]. Claim it at [claimUrl] to manage your deployment."

## Production Deploys

Only if user explicitly asks.

Windows PowerShell:

```powershell
vercel deploy <path> --prod -y
```

Unix-like shells:

```bash
vercel deploy <path> --prod -y
```

## Output

Show the user the deployment URL. For fallback deployments, also show the claim URL.

**Do not** curl or fetch the deployed URL to verify it works beyond the fallback script's own readiness check.

## Troubleshooting

### Windows notes

- If you installed the Vercel CLI recently and Codex still cannot see `vercel`, restart Codex so the updated `PATH` is picked up.
- Prefer PowerShell-native commands on Windows. Do not depend on Git Bash unless you already know it works in the current environment.
- If Git Bash fails with a signal-pipe or permission error, switch to `scripts\deploy.ps1` instead of `scripts\deploy.sh`.

### Escalated Network Access

If deployment fails due to network issues, rerun the actual deploy command with escalated permissions. Do not escalate the CLI installation check. The deploy requires escalated network access when sandbox networking blocks outbound requests.
