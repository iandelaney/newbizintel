# newbizintel

`newbizintel` is a Codex skill for producing a new-business intelligence pack for a company or brand.

It is designed for non-technical users as well as technical ones, and it works on both Windows and macOS.

## What this skill does

`newbizintel` helps you build an internal new-business intelligence pack around a company, brand, or prospect.

In one workflow, it can:

- research the company and its market
- review current reputation and recent news
- compare competitors
- assess SEO and search visibility
- shape StoryBrand-style messaging
- gather logos and visual assets
- generate creative campaign artwork
- render a polished internal report bundle
- run quality checks before internal review or optional handoff steps
- publish the HTML report to Vercel for easy browser review

The final output is usually a branded folder containing:

- an HTML report
- a portable HTML copy
- a PowerPoint deck
- a Vercel-ready HTML handoff
- structured research and QA files behind the scenes

## How to use it

Most people will use `newbizintel` from inside the Codex app, not from a terminal.

### Normal way to use it

1. Open Codex.
2. Open the repository or working folder you want to use.
3. Start a new chat.
4. Ask Codex to use `newbizintel` for the brand you care about.

If you need to run the workflow manually from the repo, prefer the included launcher instead of calling the Python file directly:

```powershell
.\run-newbizintel.ps1 run --mode full --brand-name "Brand" --website "https://www.example.com/" --brand-folder "C:\path\to\output"
```

```bash
./run-newbizintel.sh run --mode full --brand-name "Brand" --website "https://www.example.com/" --brand-folder "/path/to/output"
```

Plain-English examples:

- `Use $newbizintel for Anaconda and produce the full report bundle.`
- `Use $newbizintel for Anaconda and deploy the HTML report to Vercel at a random URL.`
- `Use $newbizintel for <brand name> and start with research.`
- `Use $newbizintel for <brand name> and rebuild the report.`
- `Use $newbizintel for <brand name> and rerun QA only.`

You do not need to remember the internal stages unless you want to.

### What Codex will usually do for you

Depending on your request, Codex may:

- start a full end-to-end run
- refresh research only
- refresh artwork only
- rebuild the report only
- rerun QA only
- prepare a deploy handoff
- publish the report to Vercel for browser viewing

### Safe first use after install

After installation, the safest first step is to ask Codex to use the included sample data.

Example:

- `Use $newbizintel with the sample report data and make sure the render and QA path works.`

If that works, the skill is installed correctly.

### Running a real brand

Once the sample proof works, ask Codex to run the skill for a real brand.

Example:

- `Use $newbizintel for Anaconda and run the full workflow.`
- `Use $newbizintel for Anaconda and deploy the final HTML report to Vercel.`

If you want a smaller job instead of a full run, say so plainly:

- `Use $newbizintel for Anaconda and refresh the research only.`
- `Use $newbizintel for Anaconda and rerun the report render only.`
- `Use $newbizintel for Anaconda and run QA only.`

## How to install it

These steps are written for a colleague who just wants the skill working.

### Before you begin

You will need:

- Codex installed and working
- Python 3.10 or newer
- Node.js and npm
- a Tavily API key for live web research
- a Vercel account if you want Codex to publish the report to the web

Before you start the install steps, set up those accounts if you do not already have them:

- Create a Vercel account at [vercel.com/signup](https://vercel.com/signup).
- Create a Tavily account at [app.tavily.com/sign-in](https://app.tavily.com/sign-in).
- After signing in to Tavily, create an API key from the Tavily dashboard and keep it ready for the config step below.

Important:

- On Windows, use PowerShell.
- On macOS, use Terminal.
- macOS users do not need PowerShell or `pwsh`.

### Install or update Python and Node.js first

If you already know Python, Node.js, and npm are installed and up to date, you can skip this part.

If you are not sure, follow it anyway.

### Windows: install or update Python

1. Open your web browser.
2. Go to [python.org/downloads/windows](https://www.python.org/downloads/windows/).
3. Download the latest Python 3 release.
4. Open the installer.
5. Very important: tick `Add Python to PATH` before you continue.
6. Choose the standard install option.
7. Wait for the install to finish.
8. Close and reopen PowerShell.

Then check that it worked:

```powershell
py --version
```

If you see a Python version number, you are ready.

### Windows: install or update Node.js and npm

1. Open your web browser.
2. Go to [nodejs.org](https://nodejs.org/).
3. Download the current `LTS` version.
4. Open the installer.
5. Accept the default options.
6. Wait for the install to finish.
7. Close and reopen PowerShell.

Then check that it worked:

```powershell
node --version
npm --version
```

If you see version numbers for both, you are ready.

### macOS: install or update Python

1. Open your web browser.
2. Go to [python.org/downloads/macos](https://www.python.org/downloads/macos/).
3. Download the latest Python 3 release for macOS.
4. Open the installer package.
5. Follow the standard install steps.
6. When it finishes, close and reopen Terminal.

Then check that it worked:

```bash
python3 --version
```

If you see a Python version number, you are ready.

### macOS: install or update Node.js and npm

1. Open your web browser.
2. Go to [nodejs.org](https://nodejs.org/).
3. Download the current `LTS` version for macOS.
4. Open the installer package.
5. Follow the standard install steps.
6. When it finishes, close and reopen Terminal.

Then check that it worked:

```bash
node --version
npm --version
```

If you see version numbers for both, you are ready.

### If one of those version checks fails

Usually, one of these fixes is enough:

1. close the terminal window completely
2. open a fresh PowerShell window on Windows, or a fresh Terminal window on macOS
3. run the version check again

If it still fails, restart the computer and try again.

### Windows install

#### 1. Open the repository folder

Open PowerShell and move into the repo:

```powershell
cd "C:\codex projects\newbizintel-skill-repo"
```

When you want to run the workflow itself on Windows, prefer:

```powershell
.\run-newbizintel.ps1 run --mode full --brand-name "Brand" --website "https://www.example.com/" --brand-folder "C:\path\to\output"
```

#### 2. Run the readiness check

```powershell
.\scripts\qa\check_prereqs.ps1
```

This checks:

- Python
- Node.js and npm
- the skill files
- the companion skills
- whether your Codex folder can be updated

If it says the Python runtime needs repair, run:

```powershell
.\bootstrap-runtime.ps1
```

Then run the readiness check again.

#### 3. Install the skill

```powershell
.\install-local.ps1
```

This will:

- install `newbizintel`
- install the companion skills it expects
- copy a Codex config snippet
- update your Codex config when it is safe to do so
- prepare the PPTX export dependencies

#### 4. Install the Vercel CLI

If you want Codex to publish the report to a live URL, first create a Vercel account at [vercel.com/signup](https://vercel.com/signup), then install the Vercel CLI:

```powershell
npm install -g vercel
```

#### 5. Log in to Vercel

If you have not signed up yet, create your account first at [vercel.com/signup](https://vercel.com/signup).

```powershell
vercel login
```

#### 6. Add your Tavily key

If you do not already have one, create a Tavily account at [app.tavily.com/sign-in](https://app.tavily.com/sign-in), then generate an API key in the Tavily dashboard before continuing.

The installer will create or update:

- your Codex config file
- a helper snippet file called `newbizintel-config-snippet.toml`

Open the written config or snippet file and replace:

- `YOUR_TAVILY_API_KEY`

with your real Tavily key.

#### 7. Restart Codex

Close and reopen Codex so the new skill and config are picked up.

#### 8. Check it inside Codex

Restart Codex, open a chat, and ask:

- `Use $newbizintel with the sample report data and make sure the render and QA path works.`
- `Use $newbizintel with the sample report data and deploy the HTML report to Vercel at a random URL.`

If that works, installation is good.

#### 9. Clean local repo artifacts when you are done

Local install and QA work can create ignored helper folders such as `vendor`, `node_modules`, `dist`, and temporary handoff files.

If you want to return the repo to a lean state after local testing:

```powershell
.\scripts\qa\clean_local_artifacts.ps1
```

Preview what would be removed without deleting anything:

```powershell
.\scripts\qa\clean_local_artifacts.ps1 -DryRun
```

### macOS install

#### 1. Open the repository folder

Open Terminal and move into the repo:

```bash
cd "/path/to/newbizintel-skill-repo"
```

#### 2. Run the readiness check

```bash
./scripts/qa/check_prereqs.sh
```

This checks:

- Python
- Node.js and npm
- the skill files
- the companion skills
- whether your Codex folder can be updated

If it says the Python runtime needs repair, run:

```bash
./bootstrap-runtime.sh
```

Then run the readiness check again.

#### 3. Install the skill

```bash
./install-local.sh
```

This will:

- install `newbizintel`
- install the companion skills it expects
- copy a Codex config snippet
- update your Codex config when it is safe to do so
- prepare the PPTX export dependencies

#### 4. Install the Vercel CLI

If you want Codex to publish the report to a live URL, first create a Vercel account at [vercel.com/signup](https://vercel.com/signup), then install the Vercel CLI:

```bash
npm install -g vercel
```

#### 5. Log in to Vercel

If you have not signed up yet, create your account first at [vercel.com/signup](https://vercel.com/signup).

```bash
vercel login
```

#### 6. Add your Tavily key

If you do not already have one, create a Tavily account at [app.tavily.com/sign-in](https://app.tavily.com/sign-in), then generate an API key in the Tavily dashboard before continuing.

The installer will create or update:

- your Codex config file
- a helper snippet file called `newbizintel-config-snippet.toml`

Open the written config or snippet file and replace:

- `YOUR_TAVILY_API_KEY`

with your real Tavily key.

#### 7. Restart Codex

Close and reopen Codex so the new skill and config are picked up.

#### 8. Check it inside Codex

Restart Codex, open a chat, and ask:

- `Use $newbizintel with the sample report data and make sure the render and QA path works.`
- `Use $newbizintel with the sample report data and deploy the HTML report to Vercel at a random URL.`

If that works, installation is good.

#### 9. Clean local repo artifacts when you are done

Local install and QA work can create ignored helper folders such as `vendor`, `node_modules`, `dist`, and temporary handoff files.

If you want to return the repo to a lean state after local testing:

```bash
./scripts/qa/clean_local_artifacts.sh
```

Preview what would be removed without deleting anything:

```bash
DRY_RUN=true ./scripts/qa/clean_local_artifacts.sh
```

### If you only want the skill files

Sometimes you may want to install the skill itself without updating Codex config.

On Windows:

```powershell
.\install-skill.ps1
```

On macOS:

```bash
./install-skill.sh
```

## What might go wrong and how to fix it

### The readiness check fails

Most often, this means one of these is missing:

- Python
- Node.js
- npm

Install the missing tool, then run the readiness check again.

If you are not sure how to do that, go back to the `Install or update Python and Node.js first` section above and follow it step by step.

Windows:

```powershell
.\scripts\qa\check_prereqs.ps1
```

macOS:

```bash
./scripts/qa/check_prereqs.sh
```

### The readiness check says the Python runtime needs repair

Run the runtime refresh once, then rerun the check.

Windows:

```powershell
.\bootstrap-runtime.ps1
```

macOS:

```bash
./bootstrap-runtime.sh
```

### The skill installs, but live research does not work

The most common cause is a missing Tavily key.

Open your Codex config or the `newbizintel-config-snippet.toml` file and make sure `YOUR_TAVILY_API_KEY` has been replaced with a real key.

Then restart Codex.

### Codex can build the report, but cannot publish it to Vercel

Usually this means one of these is missing:

- the Vercel CLI is not installed
- you are not logged in to Vercel yet
- Codex needs restarting after the CLI was installed

Windows:

```powershell
npm install -g vercel
vercel login
```

macOS:

```bash
npm install -g vercel
vercel login
```

Then restart Codex and try again.

### Codex does not show the skill after install

Usually this means Codex has not been restarted yet.

Do this:

1. Close Codex fully.
2. Reopen it.
3. Check the skill list again.

If it still does not appear, rerun the installer and watch for any error message.

### A sample render works, but a real brand run fails

That usually means the brand folder or `report-data.json` is incomplete or inconsistent.

Start by running QA against that brand data.

On Windows:

```powershell
py .\scripts\newbizintel.py qa --data-path .\output\<brand>\report-data.json
```

On macOS:

```bash
python3 ./scripts/newbizintel.py qa --data-path ./output/<brand>/report-data.json
```

### PowerPoint output does not build

`newbizintel` uses Node.js dependencies for native PPTX generation. If PowerPoint output fails:

1. make sure Node.js and npm are installed
2. rerun the installer
3. rerun the sample proof

If the sample proof still fails, rerun the readiness check first.

### macOS users: do I need PowerShell?

No.

The default production path is Python-based and works without PowerShell. The older PowerShell renderer is only a compatibility fallback.

### Windows users: do I need to use the PowerShell runner?

No, not for normal use.

The default runner is:

```powershell
py .\scripts\newbizintel.py
```

The PowerShell wrappers still exist for compatibility, but they are not the recommended day-to-day path.

## Technical details

This section is for people who want to understand how the repo is organised.

### Main workflow modules

The skill is split into smaller modules:

- `newbizintel-orchestrator`
- `newbizintel-intake`
- `newbizintel-research`
- `newbizintel-structure`
- `newbizintel-assets`
- `newbizintel-campaign-art`
- `newbizintel-render`
- `newbizintel-qa`
- `newbizintel-deploy`

### Main files written during a run

The two main structured files are:

- `report-data.json`
- `run-state.json`

Other common outputs include:

- `research-summary.json`
- rendered HTML files
- PPTX output
- QA results

### Default runner

The default cross-platform runner is:

- `scripts/newbizintel.py`

Use it on both Windows and macOS.

### PowerShell compatibility

PowerShell scripts are still included for:

- Windows convenience
- legacy compatibility
- some wrapper and audit paths

They are not required for the default macOS path.

### Report rendering

The main production render path is Python-based.

That is why the skill can be shared cleanly across Mac and PC without depending on PowerShell.

### Companion skills

`newbizintel` installs companion skills alongside the main skill because parts of the workflow depend on them. The installer handles that for you.

### Output modes

Common run modes include:

- `full`
- `research-only`
- `render-stack`
- `qa-only`
- `deploy-handoff`
- `art-refresh`
- `assets-refresh`

### Vercel deployment

For many users, the most important output is the deployed HTML report on Vercel.

In practice, that means:

- Codex builds the report
- Codex prepares a deployable handoff folder
- Codex can then publish that HTML report to Vercel
- users review the result in the browser from a live URL

By default, NewBizIntel deployment handoff should use a randomly named preview URL rather than a brand-named one.

That default preview URL is useful for personal review, QA, and quick sharing during drafting.

If you want a stable link that is appropriate to share with other colleagues more broadly, ask Codex to deploy the site to Vercel production instead of leaving it as a preview deployment.

Inside Codex, say one of these:

- `Use $newbizintel for <brand name> and deploy the final HTML report to Vercel as a production site.`
- `Use $newbizintel for <brand name> and publish the finished Vercel handoff to production so I can share it with colleagues.`

If you do not say `production`, assume the default is the randomly named preview URL.

### Recommended release habit

Before sharing the repo with someone else:

1. run the readiness check
2. run the sample proof
3. run QA on the sample data

That gives you the quickest confidence check that both installation and rendering still work.

### Keeping the repo lean

The repo-local install smoke test now writes its proof files to the shared proof root instead of building up under `dist` in the repo itself.

If you do local bootstrap, install, or QA work repeatedly, run the cleanup helper occasionally:

Windows:

```powershell
.\scripts\qa\clean_local_artifacts.ps1
```

macOS:

```bash
./scripts/qa/clean_local_artifacts.sh
```
