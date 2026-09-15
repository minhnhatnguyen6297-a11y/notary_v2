# Issue Tracker: GitHub / Local Specs

Issues, tickets, and specifications for this repo can live as GitHub Issues or local markdown files.

## Primary: GitHub Issues (when online / gh CLI available)

- **Create an issue**: `gh issue create --title "..." --body "..."`
- **Read an issue**: `gh issue view <number> --comments`
- **List issues**: `gh issue list --state open`
- **Comment / Edit**: `gh issue comment <number> --body "..."`, `gh issue edit <number>`
- **Close**: `gh issue close <number> --comment "..."`

Remote repository: `https://github.com/minhnhatnguyen6297-a11y/notary_v2.git`

## Fallback / Local Specs & Plans (Offline or File-based workflow)

When working locally or without `gh` CLI credentials:
- **Specs from `/to-spec`**: Write to `docs/superpowers/specs/<feature-name>.md`
- **Plans from `writing-plans`**: Write to `docs/superpowers/plans/<feature-name>.md`
- **Tickets from `/to-tickets`**: Write to `.scratch/<feature-name>/ticket-*.md` or `docs/superpowers/specs/tickets-<feature-name>.md`

## PRs as a request surface
**PRs as a request surface: no.**
